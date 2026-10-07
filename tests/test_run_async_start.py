"""Asynchronous Run start and the split Study lock (A24-5).

O-1, N-4, L-4, F5-08, P1-11: ``POST /api/projects/<id>/runs`` answers 202 as
soon as the Run exists in ``snapshotting``; the execution archive, the input
snapshot, the disk reservation and the worker spawn run in a background
preparation that reports its stage in ``status.json`` and never holds
STUDY_LIFECYCLE_LOCK.  Covered here:

* a clone and a second Study's start return at once while one Run freezes;
* the stage and the elapsed time are visible while it freezes, and the stages
  are kept once the Run is queued;
* a failure inside the preparation is reported on the Run (stage, code,
  message), never left in ``snapshotting``;
* a backend that stops during the preparation leaves a Run that the next
  start-up reconciler fails with GF_RUN_PREPARATION_INTERRUPTED, and the ticks
  of a live backend never judge a Run that is being prepared;
* a cancellation during the preparation ends the Run before any worker;
* a Study saved while its readiness is checked starts no Run;
* a data-pack file being frozen cannot be replaced meanwhile.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import server
from backend.lifecycle.run_status import create_status, read_status
from backend.run_supervisor import PREPARATION_INTERRUPTED, RunSupervisor
from tests.local_api_harness import start_local_api


class AsyncRunStartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, _ = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        for study in ("study", "other"):
            (self.home / "projects" / study).mkdir(parents=True)
            (self.home / "projects" / study / "project.json").write_text(json.dumps({
                "id": study, "name": study.title(), "data_pack_id": "pack", "start_year": 2025, "end_year": 2025,
                "modules": {"psm": "value-bid-at-cost-psm"},
            }), "utf-8")
        (self.home / "data-packs" / "pack").mkdir(parents=True)
        (self.home / "data-packs" / "pack" / "manifest.json").write_text(json.dumps({"id": "pack"}), "utf-8")
        # The snapshot of "study" waits for this event; "other" never waits.
        self.release = threading.Event()
        self.snapshot_entered = threading.Event()
        self.spawned: list[str] = []

        def snapshot(**kwargs):
            if kwargs["project"]["id"] == "study":
                self.snapshot_entered.set()
                if not self.release.wait(timeout=60):
                    raise AssertionError("the test never released the snapshot")
            return {"snapshot_id": "s", "input_tree_sha256": "t"}

        stubs = {
            "validate_project": lambda project: {"valid": True, "errors": []},
            "verify_recovered_configuration": lambda *a, **k: None,
            "verify_recovered_inputs": lambda *a, **k: None,
            "resolve_zonal_pack_selection": lambda *a, **k: SimpleNamespace(
                network_pack_root=None, revision_manifest={}),
            "attach_revision_identity": lambda project, *a, **k: project,
            "run_preflight": lambda *a, **k: {"accepted": True, "estimates": {"disk_bytes": 100}, "warnings": []},
            "current_execution": lambda **k: {"identity_sha256": "e" * 64},
            "bind_run_execution": lambda project, run_dir, record: project,
            "create_run_input_snapshot": snapshot,
            "MODULE_REGISTRY": SimpleNamespace(
                manifest=lambda *a, **k: SimpleNamespace(requires_capabilities=()),
                manifests=lambda: {}, extension_manifests=lambda: {},
            ),
        }
        patches = [patch.object(server, name, value) for name, value in stubs.items()]
        patches.append(patch.object(
            server.RunSupervisor, "spawn_worker",
            lambda supervisor, **kwargs: self.spawned.append(kwargs["run_id"]) or {"pid": 0},
        ))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        # Cleanups run in reverse: release, let the preparation finish, then
        # remove the stubs.
        self.addCleanup(server.wait_for_run_preparation, None, 60)
        self.addCleanup(self.release.set)

    # -- helpers -----------------------------------------------------------
    def _request(self, method: str, route: str, body: dict | None = None, *, timeout: float = 30,
                 headers: dict | None = None, data: bytes | None = None) -> tuple[int, dict]:
        payload = data if data is not None else (None if body is None else json.dumps(body).encode())
        request = urllib.request.Request(self.origin + route, method=method, data=payload,
                                         headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def _start(self, study: str = "study") -> tuple[int, dict, float]:
        began = time.monotonic()
        status, payload = self._request("POST", f"/api/projects/{study}/runs", {"mode": "value_101_day"})
        return status, payload, time.monotonic() - began

    def _start_blocked(self) -> str:
        status, payload, seconds = self._start()
        self.assertEqual(status, 202, payload)
        self.assertLess(seconds, 5.0)
        self.assertTrue(self.snapshot_entered.wait(timeout=30), "the preparation never reached the snapshot")
        return str(payload["run"]["id"])

    # -- tests -------------------------------------------------------------
    def test_start_answers_at_once_with_a_preparing_run(self) -> None:
        status, payload, seconds = self._start()
        self.assertEqual(status, 202, payload)
        self.assertLess(seconds, 5.0)
        run = payload["run"]
        self.assertEqual(run["status"], "snapshotting")
        self.assertEqual(run["preparation"]["schema_version"], "value.run-preparation/v1")
        self.assertEqual(run["preparation"]["state"], "preparing")
        self.assertEqual(run["preparation"]["stage_count"], 4)
        self.assertEqual(run["worker_liveness"], "not_started")
        self.release.set()
        self.assertTrue(server.wait_for_run_preparation(run["id"], timeout=30))
        self.assertEqual(self.spawned, [run["id"]])

    def test_clone_save_and_other_studies_are_not_blocked_while_a_run_freezes(self) -> None:
        run_id = self._start_blocked()
        # The Study lock is free while the inputs are frozen (F5-08, N-4).
        self.assertTrue(server.STUDY_LIFECYCLE_LOCK.acquire(timeout=2))
        server.STUDY_LIFECYCLE_LOCK.release()
        clones: list[str] = []

        def clone(source_id, body, *, packs_root):
            clones.append(source_id)
            return {"ok": True, "pack_id": "pack-copy"}

        with patch.object(server, "clone_data_pack", clone):
            began = time.monotonic()
            status, payload = self._request("POST", "/api/data-packs/pack/clone", {}, timeout=10)
            self.assertLess(time.monotonic() - began, 3.0)
        self.assertEqual((status, payload), (201, {"ok": True, "pack_id": "pack-copy"}))
        self.assertEqual(clones, ["pack"])
        # Another Study starts, freezes and is queued while the first waits.
        status, payload, seconds = self._start("other")
        self.assertEqual(status, 202, payload)
        self.assertLess(seconds, 5.0)
        other = str(payload["run"]["id"])
        self.assertTrue(server.wait_for_run_preparation(other, timeout=30))
        self.assertEqual(read_status(self.home / "runs" / other)["status"], "queued")
        self.assertEqual(read_status(self.home / "runs" / run_id)["status"], "snapshotting")
        self.release.set()
        self.assertTrue(server.wait_for_run_preparation(run_id, timeout=30))
        self.assertEqual(sorted(self.spawned), sorted([run_id, other]))

    def test_progress_is_visible_while_the_inputs_freeze(self) -> None:
        run_id = self._start_blocked()
        status, run = self._request("GET", f"/api/runs/{run_id}")
        self.assertEqual(status, 200, run)
        self.assertEqual(run["status"], "snapshotting")
        preparation = run["preparation"]
        self.assertEqual((preparation["stage"], preparation["stage_index"]), ("snapshot", 2))
        self.assertEqual(run["current_stage"], "Freezing the Study's inputs")
        self.assertTrue(preparation["in_progress"])
        self.assertGreaterEqual(preparation["elapsed_seconds"], 0)
        self.assertGreaterEqual(preparation["stage_elapsed_seconds"], 0)
        self.assertEqual([row["stage"] for row in preparation["stages"]], ["execution"])
        status, listing = self._request("GET", "/api/runs")
        self.assertEqual(status, 200)
        listed = {row["id"]: row for row in listing["runs"]}
        self.assertEqual(listed[run_id]["preparation"]["stage"], "snapshot")
        status, workspace = self._request("GET", "/api/workspace")
        self.assertEqual(status, 200)
        [row] = [row for row in workspace["runs"] if row["id"] == run_id]
        self.assertEqual(row["preparation"]["stage"], "snapshot")
        self.release.set()
        self.assertTrue(server.wait_for_run_preparation(run_id, timeout=30))
        final = read_status(self.home / "runs" / run_id)
        self.assertEqual(final["status"], "queued")
        self.assertEqual(final["preparation"]["state"], "queued")
        self.assertEqual([row["stage"] for row in final["preparation"]["stages"]],
                         ["execution", "snapshot", "resources", "worker"])
        self.assertGreaterEqual(final["preparation"]["elapsed_seconds"], 0)
        self.assertEqual([entry["to"] for entry in final["lifecycle_history"]], ["snapshotting", "queued"])

    def test_a_failure_while_freezing_is_reported_on_the_run(self) -> None:
        def broken(**kwargs):
            raise RuntimeError("the snapshot copy crashed")

        with patch.object(server, "create_run_input_snapshot", broken):
            status, payload, _ = self._start()
            self.assertEqual(status, 202, payload)
            self.assertTrue(server.wait_for_run_preparation(payload["run"]["id"], timeout=30))
        run_id = payload["run"]["id"]
        self.assertFalse(server.run_is_preparing(run_id))
        status, run = self._request("GET", f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        self.assertEqual((run["status"], run["error_code"]), ("failed", "GF_RUN_PREPARATION_FAILED"))
        self.assertIn("the snapshot copy crashed", run["error"])
        self.assertEqual(run["current_stage"], "Run preparation failed")
        self.assertEqual((run["preparation"]["state"], run["preparation"]["failed_stage"]), ("failed", "snapshot"))
        self.assertEqual(self.spawned, [])

    def test_a_backend_stopped_while_freezing_leaves_an_interrupted_run(self) -> None:
        run_dir = self.home / "runs" / "study-interrupted"
        run_dir.mkdir(parents=True)
        create_status(run_dir, {
            "id": "study-interrupted", "project_id": "study", "status": "snapshotting",
            "execution_status": "queued", "execution_engine": "value-annual-orchestrator/v2",
            "current_stage": "Freezing the Study's inputs", "results": [],
            "preparation": server._preparation_record(time.time() - 30),
        })
        preparing = {"study-interrupted"}
        live = RunSupervisor(self.home / "runs", run_lock=server.run_action_lock,
                             preparing=lambda run_id: run_id in preparing)
        live.tick()  # a live backend that is still preparing it leaves it alone
        self.assertEqual(read_status(run_dir)["status"], "snapshotting")
        restarted = RunSupervisor(self.home / "runs", run_lock=server.run_action_lock)
        report = restarted.reconcile_all()
        status = read_status(run_dir)
        self.assertEqual((status["status"], status["error_code"]), ("failed", PREPARATION_INTERRUPTED))
        self.assertEqual(status["current_stage"], "Run preparation interrupted")
        self.assertEqual(status["preparation"]["state"], "interrupted")
        self.assertIn("freezing this Run's inputs", status["error"])
        self.assertEqual([row["reason_code"] for row in report.settled], [PREPARATION_INTERRUPTED])

    def test_mark_lost_is_refused_while_the_run_is_prepared(self) -> None:
        run_id = self._start_blocked()
        status, payload = self._request("POST", f"/api/runs/{run_id}/mark-lost", {"confirm_run_id": run_id})
        self.assertEqual((status, payload["error_code"]), (409, "GF_RUN_PREPARING"))
        self.release.set()

    def test_cancelling_while_freezing_ends_the_run_before_any_worker(self) -> None:
        run_id = self._start_blocked()
        status, payload = self._request("POST", f"/api/runs/{run_id}/cancel", {}, timeout=5)
        self.assertEqual(status, 202, payload)
        self.assertEqual(payload["run"]["status"], "cancel_requested")
        self.release.set()
        self.assertTrue(server.wait_for_run_preparation(run_id, timeout=30))
        final = read_status(self.home / "runs" / run_id)
        self.assertEqual(final["status"], "cancelled")
        self.assertEqual(final["preparation"]["state"], "cancelled")
        self.assertEqual(final["lifecycle_history"][-1]["reason_code"], "GF_RUN_CANCELLED_BEFORE_WORKER")
        self.assertEqual(self.spawned, [])

    def test_a_study_saved_during_the_readiness_check_starts_no_run(self) -> None:
        record = self.home / "projects" / "study" / "project.json"

        def preflight(*args, **kwargs):
            record.write_text(record.read_text("utf-8").replace('"Study"', '"Study renamed"'), "utf-8")
            return {"accepted": True, "estimates": {"disk_bytes": 100}, "warnings": []}

        with patch.object(server, "run_preflight", preflight):
            status, payload, _ = self._start()
        self.assertEqual((status, payload["error_code"]), (409, "GF_RUN_START_STUDY_CHANGED"))
        self.assertFalse((self.home / "runs").exists() and any((self.home / "runs").iterdir()))

    def test_a_pack_being_frozen_cannot_be_replaced_meanwhile(self) -> None:
        run_id = self._start_blocked()
        self.assertIn("pack", server.packs_being_frozen())
        slot = server.DATASET_SLOTS[0]
        file_format = tuple(slot.get("supported_formats") or slot["formats"])[0]
        status, payload = self._request(
            "POST", f"/api/data-packs/pack/files/{slot['role']}", data=b"a,b\n1,2\n", timeout=10,
            headers={"Content-Type": "application/octet-stream", "X-Filename": f"replacement.{file_format}"},
        )
        self.assertEqual((status, payload.get("error_code")), (409, "GF_DATA_PACK_FREEZING"))
        self.release.set()
        self.assertTrue(server.wait_for_run_preparation(run_id, timeout=30))
        self.assertNotIn("pack", server.packs_being_frozen())


if __name__ == "__main__":
    unittest.main()
