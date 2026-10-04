"""P0-3 S5 (F5-12): deleting a run never leaves it stuck in 'deleting'."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from backend.lifecycle.run_status import create_status, read_status, update_status
from tests.local_api_harness import start_local_api

ROOT = Path(__file__).resolve().parents[1]

HOLDER = """
import sys, time
from backend.lifecycle.file_locks import FileLock
lock = FileLock(sys.argv[1]).acquire()
print("held", flush=True)
time.sleep(60)
"""


def _request(url: str, *, method: str = "GET", body: object | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _json(raw: bytes):
    return json.loads(raw.decode("utf-8"))


class RunDeleteSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, _ = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.runs = self.home / "runs"
        self.trash = self.home / "trash"

    def _run(self, run_id: str, state: str = "completed") -> Path:
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True)
        create_status(run_dir, {"id": run_id, "project_id": "study", "status": state,
                                "execution_engine": "value-annual-orchestrator/v2", "results": []})
        (run_dir / "model-output").mkdir()
        (run_dir / "model-output" / "result.json").write_text("{}", "utf-8")
        return run_dir

    def _delete(self, run_id: str):
        return _request(f"{self.origin}/api/runs/{run_id}/delete", method="POST", body={"confirm_run_id": run_id})

    def test_delete_moves_first_and_records_deleting_only_in_the_trash(self) -> None:
        self._run("done-run")
        status, raw = self._delete("done-run")
        self.assertEqual(status, 200, raw)
        self.assertFalse((self.runs / "done-run").exists())
        [copy] = list(self.trash.iterdir())
        trashed = read_status(copy)
        self.assertEqual(trashed["status"], "deleting")
        self.assertEqual(trashed["lifecycle_history"][-1]["from"], "completed")

    def test_failed_rename_leaves_the_run_unchanged(self) -> None:
        run_dir = self._run("stuck-run", "failed")
        before = hashlib.sha256((run_dir / "status.json").read_bytes()).hexdigest()
        with patch.object(server.os, "rename", side_effect=OSError("device busy")):
            status, raw = self._delete("stuck-run")
        self.assertEqual(status, 409)
        self.assertEqual(_json(raw)["error_code"], "GF_RUN_TRASH_MOVE_FAILED")
        self.assertEqual(hashlib.sha256((run_dir / "status.json").read_bytes()).hexdigest(), before)
        self.assertEqual(read_status(run_dir)["status"], "failed")
        status, raw = self._delete("stuck-run")
        self.assertEqual(status, 200, raw)

    def test_two_deletes_in_the_same_second(self) -> None:
        self._run("twice-run")
        stem = None
        results: list[int] = []
        barrier = threading.Barrier(2)

        def delete() -> None:
            barrier.wait(5)
            results.append(self._delete("twice-run")[0])

        threads = [threading.Thread(target=delete) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(sorted(results), [200, 404])
        self.assertEqual(len(list(self.trash.iterdir())), 1)
        # A same-second name collision in the trash gets a suffix, never a refusal.
        self._run("twice-run")
        stem = next(self.trash.iterdir()).name
        with patch.object(server, "datetime") as clock:
            clock.now.return_value.strftime.return_value = stem.removeprefix("twice-run-")
            status, raw = self._delete("twice-run")
        self.assertEqual(status, 200, raw)
        self.assertEqual(sorted(path.name for path in self.trash.iterdir()), [stem, f"{stem}-2"])

    def test_active_or_leased_runs_are_refused(self) -> None:
        self._run("active-run", "running")
        status, raw = self._delete("active-run")
        self.assertEqual((status, _json(raw)["error_code"]), (409, "GF_RUN_NOT_TERMINAL"))
        run_dir = self._run("leased-run", "failed")
        environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        holder = subprocess.Popen([sys.executable, "-B", "-c", HOLDER, str(run_dir / "worker.lock")],
                                  cwd=ROOT, env=environment, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            status, raw = self._delete("leased-run")
            self.assertEqual((status, _json(raw)["error_code"]), (409, "GF_WORKER_ALIVE"))
            status, raw = _request(f"{self.origin}/api/runs/leased-run/archive", method="POST", body={})
            self.assertEqual(status, 409)
        finally:
            holder.kill(); holder.wait(10); holder.stdout.close()
        self.assertTrue(run_dir.is_dir())

    def test_legacy_deleting_is_repaired_and_then_deletable(self) -> None:
        run_dir = self._run("legacy-deleting", "cancelled")
        update_status(run_dir, transition="deleting", reason_code="GF_RUN_MOVING_TO_TRASH")
        report = server.run_supervisor().reconcile_all()
        self.assertEqual(report.repaired, [{"run_id": "legacy-deleting", "to": "cancelled"}])
        status, raw = self._delete("legacy-deleting")
        self.assertEqual(status, 200, raw)

    def test_lock_and_lifecycle_files_are_not_downloadable(self) -> None:
        run_dir = self._run("files-run")
        (run_dir / "worker.lock").write_bytes(b"")
        (run_dir / "status.invalid-20261005T000000-1-abcdef.json").write_text("{", "utf-8")
        (run_dir / "late-worker-20261005T000000-1-abcdef.json").write_text("{}", "utf-8")
        (run_dir / "model-output" / "nested.lock").write_bytes(b"")
        status, raw = _request(f"{self.origin}/api/runs/files-run/artifacts")
        listed = {row["id"] for row in _json(raw)["items"]}
        self.assertEqual(listed, {"status.json", "model-output/result.json"})
        for name in ("status.lock", "worker.lock", "status.invalid-20261005T000000-1-abcdef.json",
                     "model-output/nested.lock"):
            status, _ = _request(f"{self.origin}/api/runs/files-run/artifacts/{name}")
            self.assertEqual(status, 404, name)
        status, _ = _request(f"{self.origin}/api/runs/files-run/artifacts/model-output/result.json")
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
