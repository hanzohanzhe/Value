"""P0-3 S6 (F5-04, R1-03, R1-13): run quota accounting, hand-computed.

T1  a completed run holds no reservation
T2  an active run holds max(0, reserved - model-output bytes)
T3  output beyond the reservation never makes it negative
T4  200 completed small runs do not exhaust the quota
T5  a legacy O_EXCL lock file does not block; start-up removes it
T6  a held reservation lock times out as LockTimeout (HTTP 503) and the
    started run is left visibly failed
T7  hard-linked files count once (independent inode oracle)
T8  resume needs only its own unwritten reservation (boundary +-1)
T9  a run directory without status (being created) keeps its reservation
T10 an unreadable status keeps its reservation (conservative)
T11 preflight's non-staged branch applies the same quota rule
T12 every entry point agrees on the boundary (+-1)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import server
from backend.lifecycle.file_locks import LockTimeout
from backend.lifecycle.run_status import create_status, read_status
from gridform_core import run_quota
from gridform_core.preflight_resources import ResourceEstimate, evaluate_resource_gate
from gridform_core.run_quota import (
    QuotaUsage,
    RunQuotaPolicy,
    global_quota_reasons,
    quarantine_orphan_run_directories,
    quota_usage,
    remove_legacy_reservation_lock,
    reserve_run_space,
)
from tests.local_api_harness import start_local_api

ROOT = Path(__file__).resolve().parents[1]
FREE = SimpleNamespace(free=10 ** 12, total=2 * 10 ** 12, used=10 ** 12)

HOLDER = """
import sys, time
from backend.lifecycle.file_locks import FileLock
lock = FileLock(sys.argv[1]).acquire()
print("held", flush=True)
time.sleep(60)
"""


class QuotaAccountingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.runs = Path(self.folder.name) / "runs"
        self.runs.mkdir()

    def _run(self, run_id: str, state: str | None, *, reserved: int = 0, output: int = 0) -> Path:
        run_dir = self.runs / run_id
        run_dir.mkdir()
        if state is not None:
            create_status(run_dir, {"id": run_id, "status": state})
        if reserved:
            (run_dir / "reservation.json").write_text(json.dumps({"reserved_bytes": reserved}), "utf-8")
        if output:
            (run_dir / "model-output").mkdir()
            (run_dir / "model-output" / "out.bin").write_bytes(b"x" * output)
        return run_dir

    def _bytes(self, *paths: Path) -> int:
        return sum(path.stat().st_size for path in paths)

    def test_t1_t2_t3_reservations_by_state(self) -> None:
        done = self._run("done", "completed", reserved=604_156_896, output=9_600)
        running = self._run("running", "running", reserved=1_000, output=300)
        over = self._run("over", "running", reserved=100, output=250)
        usage = quota_usage(self.runs)
        self.assertEqual(usage.outstanding_reserved_bytes, 700 + 0)
        expected_existing = self._bytes(*(path for run in (done, running, over) for path in run.rglob("*") if path.is_file()
                                          and path.name != ".reservation.lock"))
        self.assertEqual(usage.existing_run_bytes, expected_existing)
        self.assertEqual({row["run_id"]: row["outstanding_bytes"] for row in usage.active_runs},
                         {"running": 700, "over": 0})

    def test_t4_two_hundred_completed_runs_still_reserve(self) -> None:
        for index in range(200):
            self._run(f"done-{index:03d}", "completed", reserved=604_156_896, output=96)
        existing = quota_usage(self.runs).existing_run_bytes
        policy = RunQuotaPolicy(global_quota_bytes=existing + 1_000, per_run_quota_bytes=1_000, minimum_free_bytes=0)
        with patch.object(run_quota.shutil, "disk_usage", return_value=FREE):
            report = reserve_run_space(self.runs, "new-run", 1_000 - 64, policy=policy)
        self.assertTrue(report["accepted"], report)
        self.assertEqual(report["already_reserved_bytes"], 0)
        self.assertEqual(report["schema_version"], "value.run-space-reservation/v2")

    def test_t5_legacy_lock_file_neither_blocks_nor_survives_start_up(self) -> None:
        legacy = self.runs / ".reservation.lock"
        legacy.write_text("4242", "ascii")
        started = time.monotonic()
        with patch.object(run_quota.shutil, "disk_usage", return_value=FREE):
            report = reserve_run_space(self.runs, "r", 10, policy=RunQuotaPolicy(minimum_free_bytes=0))
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertTrue(report["accepted"])
        self.assertTrue(remove_legacy_reservation_lock(self.runs))
        self.assertFalse(legacy.exists())
        legacy.write_bytes(b"")  # the new, empty flock file is left alone
        self.assertFalse(remove_legacy_reservation_lock(self.runs))
        legacy.write_bytes(b"0")  # the Windows flock file holds the locked byte
        self.assertFalse(remove_legacy_reservation_lock(self.runs))
        self.assertEqual(legacy.read_bytes(), b"0")

    def test_t6_held_lock_times_out_as_lock_timeout(self) -> None:
        environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        holder = subprocess.Popen([sys.executable, "-B", "-c", HOLDER, str(self.runs / ".reservation.lock")],
                                  cwd=ROOT, env=environment, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            with patch.object(run_quota, "RESERVATION_LOCK_TIMEOUT_SECONDS", 0.2):
                with self.assertRaises(LockTimeout) as caught:
                    reserve_run_space(self.runs, "blocked", 10)
            self.assertIsInstance(caught.exception, OSError)
            self.assertFalse((self.runs / "blocked").exists())
        finally:
            holder.kill(); holder.wait(10); holder.stdout.close()

    def test_t7_hard_links_count_once(self) -> None:
        first = self._run("first", "completed")
        second = self._run("second", "completed")
        (first / "model-output").mkdir()
        (second / "model-output").mkdir()
        shared = first / "model-output" / "shared.bin"
        shared.write_bytes(b"s" * 1_000)
        os.link(shared, second / "model-output" / "shared.bin")
        os.link(shared, first / "model-output" / "again.bin")
        oracle_inodes: dict[tuple[int, int], int] = {}
        for path in self.runs.rglob("*"):
            if path.is_file() and not path.is_symlink():
                info = path.stat()
                oracle_inodes[(info.st_dev, info.st_ino)] = info.st_size
        self.assertEqual(quota_usage(self.runs).existing_run_bytes, sum(oracle_inodes.values()))
        logical = sum(path.stat().st_size for path in self.runs.rglob("*") if path.is_file())
        self.assertEqual(logical - quota_usage(self.runs).existing_run_bytes, 2_000)

    def test_t8_resume_counts_only_its_own_remaining_reservation(self) -> None:
        resumed = self._run("resumed", "failed", reserved=1_000, output=400)
        self._run("other", "running", reserved=500)
        usage = quota_usage(self.runs, exclude_run="resumed")
        _reserved, _written, own = run_quota.run_outstanding_bytes(resumed)
        self.assertEqual((own, usage.outstanding_reserved_bytes), (600, 500))
        limit = usage.existing_run_bytes + 500 + 600
        self.assertEqual(global_quota_reasons(usage, own, RunQuotaPolicy(limit, 10_000, 0)), [])
        self.assertEqual(global_quota_reasons(usage, own, RunQuotaPolicy(limit - 1, 10_000, 0)), ["global_quota_exceeded"])

    def test_t9_t10_missing_or_unreadable_status_keeps_its_reservation(self) -> None:
        self._run("creating", None, reserved=300)
        broken = self._run("broken", None, reserved=200)
        (broken / "status.json").write_text("{oops", "utf-8")
        self.assertEqual(quota_usage(self.runs).outstanding_reserved_bytes, 500)

    def test_reservation_race_allows_one_winner_with_status_accounting(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        barrier = Barrier(8)
        policy = RunQuotaPolicy(global_quota_bytes=100, per_run_quota_bytes=100, minimum_free_bytes=0)

        def claim(index: int):
            barrier.wait()
            return reserve_run_space(self.runs, f"run-{index}", 75, policy=policy)

        with patch.object(run_quota.shutil, "disk_usage", return_value=FREE):
            with ThreadPoolExecutor(max_workers=8) as executor:
                reports = list(executor.map(claim, range(8)))
        self.assertEqual(sum(bool(row["accepted"]) for row in reports), 1)
        self.assertTrue(all(row["accepted"] or "global_quota_exceeded" in row["reason_codes"] for row in reports))
        refused = next(row for row in reports if not row["accepted"])
        self.assertIn("corrective_actions", refused)

    def test_orphan_directories_move_to_the_trash(self) -> None:
        self._run("orphan", None, reserved=10)
        self._run("normal", "completed")
        trash = Path(self.folder.name) / "trash"
        self.assertEqual(quarantine_orphan_run_directories(self.runs, trash), ["orphan"])
        self.assertEqual(sorted(path.name for path in self.runs.iterdir()), ["normal"])
        self.assertEqual(len(list((trash / "orphan-runs").iterdir())), 1)

    def test_t12_every_entry_point_agrees_on_the_boundary(self) -> None:
        usage = QuotaUsage(existing_run_bytes=600, outstanding_reserved_bytes=300, active_runs=())
        estimate = ResourceEstimate(persisted_bytes=70, temporary_bytes=30, reserve_bytes=0, runtime_seconds=1.0,
                                    trace_profile="summary", calibration_basis={}, row_cardinality={})
        for global_quota, accepted in ((1_000, True), (999, False)):
            policy = RunQuotaPolicy(global_quota_bytes=global_quota, per_run_quota_bytes=10_000, minimum_free_bytes=0)
            shared = global_quota_reasons(usage, 100, policy)
            gate = evaluate_resource_gate(estimate, free_bytes=10 ** 9, quota_policy=policy,
                                          existing_run_bytes=600, already_reserved_bytes=300)
            self.assertEqual(not shared, accepted)
            self.assertEqual(gate["accepted"], accepted)
            self.assertEqual(gate["reason_codes"], shared)
        policy = RunQuotaPolicy(global_quota_bytes=10 ** 6, per_run_quota_bytes=99, minimum_free_bytes=0)
        self.assertEqual(global_quota_reasons(usage, 100, policy), ["per_run_quota_exceeded"])


class PreflightQuotaTests(unittest.TestCase):
    def test_t11_non_staged_preflight_reports_the_same_quota_refusal(self) -> None:
        from tests.test_preflight import MODULES, PINNED_DISK_USAGE, ResolvedFixture
        from gridform_core.preflight import run_preflight
        from gridform_core.v2.module_manifest import workspace_registry

        project = {
            "schema_version": "value.project/v1", "id": "project", "name": "Project", "data_pack_id": "pack",
            "start_year": 2025, "end_year": 2034, "modules": MODULES, "parameters": {}, "runtime_options": {},
        }
        with tempfile.TemporaryDirectory() as folder:
            runs = Path(folder) / "runs"
            (runs / "busy").mkdir(parents=True)
            create_status(runs / "busy", {"id": "busy", "status": "running"})
            (runs / "busy" / "reservation.json").write_text(json.dumps({"reserved_bytes": 10 ** 9}), "utf-8")

            def run(policy):
                with patch("gridform_core.preflight.validate_data_pack", return_value={
                    "schema_version": "value.data-pack-validation/v1", "valid": True,
                    "errors": [], "warnings": [], "bindings": [], "summary": {"passed": 0, "failed": 0, "total": 0},
                }), patch("gridform_core.preflight.resolve_scheme_c_parameters", return_value=ResolvedFixture()), \
                        patch("gridform_core.preflight.shutil.disk_usage", return_value=PINNED_DISK_USAGE):
                    return run_preflight(project, mode="full", pack_root=Path(folder), pack_manifest={"id": "pack", "bindings": {}},
                                         dataset_slots=[], registry=workspace_registry(Path(folder) / "none"),
                                         output_root=Path(folder), runs_root=runs, resource_quota_policy=policy,
                                         preflight_run_id="new-run")

            refused = run(RunQuotaPolicy(global_quota_bytes=10 ** 9, per_run_quota_bytes=10 ** 12, minimum_free_bytes=0))
            self.assertIn("GF_PREFLIGHT_RUN_QUOTA", {row["code"] for row in refused["errors"]})
            self.assertEqual(refused["checks"]["quota"]["outstanding_reserved_bytes"], 10 ** 9)
            accepted = run(RunQuotaPolicy())
            self.assertNotIn("GF_PREFLIGHT_RUN_QUOTA", {row["code"] for row in accepted["errors"]})


class StartRunQuotaHttpTests(unittest.TestCase):
    """The start path with its heavy collaborators stubbed (snapshot, identity)."""

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, _ = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        (self.home / "projects" / "study").mkdir(parents=True)
        (self.home / "projects" / "study" / "project.json").write_text(json.dumps({
            "id": "study", "name": "Study", "data_pack_id": "pack", "start_year": 2025, "end_year": 2025,
            "modules": {"psm": "value-bid-at-cost-psm"},
        }), "utf-8")
        (self.home / "data-packs" / "pack").mkdir(parents=True)
        (self.home / "data-packs" / "pack" / "manifest.json").write_text(json.dumps({"id": "pack"}), "utf-8")
        stubs = {
            "validate_project": lambda project: {"valid": True, "errors": []},
            "verify_recovered_configuration": lambda *a, **k: None,
            "verify_recovered_inputs": lambda *a, **k: None,
            "resolve_zonal_pack_selection": lambda *a, **k: SimpleNamespace(network_pack_root=None, revision_manifest={}),
            "attach_revision_identity": lambda project, *a, **k: project,
            "run_preflight": lambda *a, **k: {"accepted": True, "estimates": {"disk_bytes": 100}, "warnings": []},
            "current_execution": lambda **k: {"identity_sha256": "e" * 64},
            "bind_run_execution": lambda project, run_dir, record: project,
            "create_run_input_snapshot": lambda **k: {"snapshot_id": "s", "input_tree_sha256": "t"},
        }
        for name, value in stubs.items():
            item = patch.object(server, name, value)
            item.start()
            self.addCleanup(item.stop)
        registry = patch.object(server, "MODULE_REGISTRY", SimpleNamespace(
            manifest=lambda *a, **k: SimpleNamespace(requires_capabilities=())))
        registry.start()
        self.addCleanup(registry.stop)

    def _start(self):
        """POST a start and wait for its background preparation (A24-5)."""

        request = urllib.request.Request(f"{self.origin}/api/projects/study/runs", method="POST",
                                         data=json.dumps({"mode": "value_101_day"}).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                answer = response.status, json.loads(response.read()), dict(response.headers)
        except urllib.error.HTTPError as error:
            answer = error.code, json.loads(error.read()), dict(error.headers)
        self.assertTrue(server.wait_for_run_preparation(timeout=60))
        return answer

    def _only_run(self) -> dict:
        [run_dir] = [path for path in (self.home / "runs").iterdir() if path.is_dir()]
        return read_status(run_dir)

    # A24-5: these outcomes arise after the 202, in the background
    # preparation; each leaves a visible failed Run with its code and stage.
    def test_t6_lock_timeout_leaves_a_visible_failed_run(self) -> None:
        with patch.object(server, "reserve_run_space", side_effect=LockTimeout(self.home / "runs" / ".reservation.lock", 5)):
            status, payload, _ = self._start()
        self.assertEqual(status, 202, payload)
        self.assertEqual(payload["run"]["status"], "snapshotting")
        run = self._only_run()
        self.assertEqual((run["status"], run["error_code"]), ("failed", "GF_RUN_RESERVATION_LOCK_TIMEOUT"))
        self.assertEqual((run["preparation"]["state"], run["preparation"]["failed_stage"]), ("failed", "resources"))

    def test_refused_reservation_leaves_a_failed_run(self) -> None:
        with patch.object(server, "reserve_run_space", return_value={"accepted": False, "reason_codes": ["global_quota_exceeded"]}):
            status, _payload, _ = self._start()
        self.assertEqual(status, 202)
        run = self._only_run()
        self.assertEqual((run["status"], run["error_code"]), ("failed", "VALUE_PREFLIGHT_DISK_SPACE"))
        self.assertEqual(run["quota"]["reason_codes"], ["global_quota_exceeded"])

    def test_spawn_failure_leaves_a_failed_run(self) -> None:
        with patch.object(server.RunSupervisor, "spawn_worker", side_effect=server.WorkerSpawnError("no exec")):
            status, _payload, _ = self._start()
        self.assertEqual(status, 202)
        run = self._only_run()
        self.assertEqual((run["status"], run["error_code"]), ("failed", "GF_WORKER_SPAWN_FAILED"))
        self.assertEqual([entry["to"] for entry in run["lifecycle_history"]], ["snapshotting", "queued", "failed"])

    def test_unexpected_preparation_error_never_leaves_snapshotting(self) -> None:
        with patch.object(server, "create_run_input_snapshot", side_effect=RuntimeError("boom")):
            status, _payload, _ = self._start()
        self.assertEqual(status, 202)
        run = self._only_run()
        self.assertEqual((run["status"], run["error_code"]), ("failed", "GF_RUN_PREPARATION_FAILED"))
        self.assertIn("boom", run["error"])


if __name__ == "__main__":
    unittest.main()
