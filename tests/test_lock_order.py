"""Global lock order assertions (C6, P0_CONVENTIONS section 5).

    .backend.lock -> STUDY_LIFECYCLE_LOCK -> RUN_ACTION_LOCKS[run]
      -> MODULE_LIFECYCLE_LOCK -> <runs>/.reservation.lock -> <run>/status.lock

P0-3 lands the run-side part: every acquisition made while starting,
cancelling, archiving and deleting runs is recorded per thread and must never
take a lock ranked before one it already holds.  P0-2 adds
MODULE_LIFECYCLE_LOCK and the interleaved start/stop-module stress test here.
"""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import server
from backend.lifecycle import file_locks
from tests.local_api_harness import start_local_api

RANKS = {"backend": 0, "study": 1, "run_action": 2, "module": 3, "reservation": 4, "status": 5}


class _Recorder:
    def __init__(self) -> None:
        self.local = threading.local()
        self.violations: list[str] = []
        self.events: list[str] = []
        self.guard = threading.Lock()

    def _stack(self) -> list[int]:
        stack = getattr(self.local, "stack", None)
        if stack is None:
            stack = self.local.stack = []
        return stack

    def acquired(self, name: str) -> None:
        rank = RANKS[name]
        stack = self._stack()
        with self.guard:
            self.events.append(name)
            if stack and rank < max(stack):
                self.violations.append(f"{name} taken while holding rank {max(stack)} ({self.events[-6:]})")
        stack.append(rank)

    def released(self, name: str) -> None:
        stack = self._stack()
        rank = RANKS[name]
        for index in range(len(stack) - 1, -1, -1):
            if stack[index] == rank:
                del stack[index]
                return


class _RecordingRLock:
    def __init__(self, recorder: _Recorder, name: str, inner=None) -> None:
        self.recorder, self.name, self.inner = recorder, name, inner or threading.RLock()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        got = self.inner.acquire(blocking, timeout)
        if got:
            self.recorder.acquired(self.name)
        return got

    def release(self) -> None:
        self.recorder.released(self.name)
        self.inner.release()

    __enter__ = acquire

    def __exit__(self, *exc) -> None:
        self.release()


class LockOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, _ = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.recorder = recorder = _Recorder()
        (self.home / "projects" / "study").mkdir(parents=True)
        (self.home / "projects" / "study" / "project.json").write_text(json.dumps({
            "id": "study", "name": "Study", "data_pack_id": "pack", "start_year": 2025, "end_year": 2025,
            "modules": {"psm": "value-bid-at-cost-psm"},
        }), "utf-8")
        (self.home / "data-packs" / "pack").mkdir(parents=True)
        (self.home / "data-packs" / "pack" / "manifest.json").write_text(json.dumps({"id": "pack"}), "utf-8")
        run_locks: dict[str, _RecordingRLock] = {}

        def run_action_lock(run_id: str) -> _RecordingRLock:
            return run_locks.setdefault(run_id, _RecordingRLock(recorder, "run_action"))

        real_acquire = file_locks.FileLock.acquire
        real_release = file_locks.FileLock.release

        def name_of(path: Path) -> str | None:
            return {"status.lock": "status", ".reservation.lock": "reservation", ".backend.lock": "backend"}.get(path.name)

        def acquire(lock, timeout=None, *, poll=file_locks.DEFAULT_POLL_SECONDS):
            result = real_acquire(lock, timeout, poll=poll)
            if name_of(lock.path):
                recorder.acquired(name_of(lock.path))
            return result

        def release(lock):
            if lock.held and name_of(lock.path):
                recorder.released(name_of(lock.path))
            return real_release(lock)

        class _Spawned(Exception):
            pass

        stubs = {
            "STUDY_LIFECYCLE_LOCK": _RecordingRLock(recorder, "study"),
            "run_action_lock": run_action_lock,
            "validate_project": lambda project: {"valid": True, "errors": []},
            "verify_recovered_configuration": lambda *a, **k: None,
            "verify_recovered_inputs": lambda *a, **k: None,
            "resolve_zonal_pack_selection": lambda *a, **k: SimpleNamespace(network_pack_root=None, revision_manifest={}),
            "attach_revision_identity": lambda project, *a, **k: project,
            "run_preflight": lambda *a, **k: {"accepted": True, "estimates": {"disk_bytes": 100}, "warnings": []},
            "current_execution": lambda **k: {"identity_sha256": "e" * 64},
            "bind_run_execution": lambda project, run_dir, record: project,
            "create_run_input_snapshot": lambda **k: {"snapshot_id": "s", "input_tree_sha256": "t"},
            "MODULE_REGISTRY": SimpleNamespace(manifest=lambda *a, **k: SimpleNamespace(requires_capabilities=())),
        }
        patches = [patch.object(server, name, value) for name, value in stubs.items()]
        patches += [
            patch.object(file_locks.FileLock, "acquire", acquire),
            patch.object(file_locks.FileLock, "release", release),
            patch.object(server.RunSupervisor, "spawn_worker", lambda self, **k: {"pid": 0}),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def _post(self, route: str, body: dict) -> int:
        request = urllib.request.Request(self.origin + route, method="POST", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def test_run_side_acquisitions_follow_the_global_order(self) -> None:
        statuses = [self._post("/api/projects/study/runs", {"mode": "value_101_day"}) for _ in range(3)]
        self.assertEqual(statuses, [202, 202, 202])
        runs = sorted(path.name for path in (self.home / "runs").iterdir() if path.is_dir())
        self.assertEqual(self._post(f"/api/runs/{runs[0]}/cancel", {}), 202)
        from backend.lifecycle.run_status import update_status
        update_status(self.home / "runs" / runs[1], transition="failed", reason_code="TEST")
        self.assertEqual(self._post(f"/api/runs/{runs[1]}/delete", {"confirm_run_id": runs[1]}), 200)
        threads = [threading.Thread(target=self._post, args=("/api/projects/study/runs", {"mode": "value_101_day"}))
                   for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive())
        self.assertEqual(self.recorder.violations, [])
        for name in ("study", "run_action", "reservation", "status"):
            self.assertIn(name, self.recorder.events)

    def _runs(self) -> list[Path]:
        return sorted(path for path in (self.home / "runs").iterdir() if path.is_dir())

    def test_start_creates_the_run_under_its_action_lock(self) -> None:
        """Review M1-P0-3 #3: a supervisor tick right after the first status
        write must find the run's action lock held and leave it alone."""

        from backend.lifecycle.run_status import read_status

        real_create = server.create_status
        seen: list[str] = []

        def create_then_tick(run_dir, initial):
            created = real_create(run_dir, initial)
            ticker = threading.Thread(target=server.run_supervisor().tick)
            ticker.start(); ticker.join(timeout=30)
            seen.append(read_status(run_dir)["status"])
            return created

        with patch.object(server, "create_status", create_then_tick):
            self.assertEqual(self._post("/api/projects/study/runs", {"mode": "value_101_day"}), 202)
        self.assertEqual(seen, ["snapshotting"])
        [run_dir] = self._runs()
        status = read_status(run_dir)
        self.assertEqual(status["status"], "queued")
        self.assertEqual([entry["to"] for entry in status["lifecycle_history"]], ["snapshotting", "queued"])
        self.assertNotIn("worker_outcome", status)

    def test_client_gone_during_the_202_keeps_the_spawned_run(self) -> None:
        """Review M1-P0-3 #4: the 202 is sent outside the start's failure
        boundary, so a broken pipe there never fails a spawned run."""

        from backend.lifecycle.run_status import read_status

        real_json = server.Handler._json

        def broken_202(handler, payload, status=200):
            if status == 202:
                raise BrokenPipeError("client went away")
            return real_json(handler, payload, status)

        with patch.object(server.Handler, "_json", broken_202):
            try:
                self._post("/api/projects/study/runs", {"mode": "value_101_day"})
            except (OSError, urllib.error.URLError, http.client.HTTPException):
                pass  # the client sees the dropped connection
        [run_dir] = self._runs()
        status = read_status(run_dir)
        self.assertEqual(status["status"], "queued")
        self.assertNotIn("GF_RUN_START_FAILED", json.dumps(status))


class RecorderSelfTest(unittest.TestCase):
    def test_recorder_flags_an_inverted_acquisition(self) -> None:
        recorder = _Recorder()
        recorder.acquired("status")
        recorder.acquired("run_action")
        self.assertEqual(len(recorder.violations), 1)
        recorder.released("run_action")
        recorder.released("status")
        recorder.acquired("study")
        recorder.acquired("study")  # re-entrant RLock: same rank is fine
        self.assertEqual(len(recorder.violations), 1)


if __name__ == "__main__":
    unittest.main()
