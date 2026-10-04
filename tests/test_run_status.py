"""P0-3 S2: the single status.json writer API and its migrated callers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from backend.lifecycle import run_status
from backend.lifecycle.run_status import (
    WRITER_SERVER,
    WRITER_WORKER,
    LateWriteRejected,
    LeaseHeldError,
    LegacyStatusError,
    StatusExistsError,
    assert_history_chain,
    create_status,
    record_light_failure,
    update_status,
)
from backend.lifecycle.states import LifecycleError

ROOT = Path(__file__).resolve().parents[1]


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


RACE_WRITER = """
import sys
from pathlib import Path
from backend.lifecycle.run_status import update_status
run_dir = Path(sys.argv[1]); field = sys.argv[2]; count = int(sys.argv[3])
errors = 0
for _ in range(count):
    try:
        update_status(run_dir, mutate=lambda s: s.__setitem__(field, int(s.get(field, 0)) + 1))
    except Exception as exc:
        errors += 1
        print(type(exc).__name__, exc, file=sys.stderr)
print(errors)
"""

HOLD_WORKER_LOCK = """
import sys, time
from backend.lifecycle.file_locks import FileLock
lock = FileLock(sys.argv[1]).acquire()
print("held", flush=True)
time.sleep(60)
"""


class RunStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.run_dir = Path(self.folder.name) / "run-a"
        self.run_dir.mkdir()

    def _create(self, state: str = "snapshotting", **fields) -> dict:
        return create_status(self.run_dir, {"id": "run-a", "project_id": "p", "status": state, **fields})

    def test_transitions_build_a_consecutive_history_chain(self) -> None:
        self._create()
        with self.assertRaises(StatusExistsError):
            self._create()
        update_status(self.run_dir, transition="queued", reason_code="GF_RUN_QUEUED", writer=WRITER_SERVER)
        update_status(self.run_dir, mutate=lambda s: s.update(stage="x"), writer=WRITER_SERVER)
        update_status(self.run_dir, transition="running", reason_code="GF_WORKER_STARTED", writer=WRITER_WORKER)
        final = update_status(self.run_dir, transition="completed", reason_code="GF_RUN_COMPLETED", writer=WRITER_WORKER)
        assert_history_chain(final)
        self.assertEqual([entry["to"] for entry in final["lifecycle_history"]],
                         ["snapshotting", "queued", "running", "completed"])
        self.assertEqual([entry["sequence"] for entry in final["lifecycle_history"]], [1, 2, 3, 4])
        self.assertIsNone(final["lifecycle_history"][0]["from"])
        self.assertEqual(final["stage"], "x")
        self.assertEqual(json.loads((self.run_dir / "status.json").read_text("utf-8")), final)
        with self.assertRaises(LifecycleError):
            update_status(self.run_dir, transition="running", reason_code="X")
        broken = dict(final, lifecycle_history=final["lifecycle_history"][:2])
        with self.assertRaises(LifecycleError):
            assert_history_chain(broken)

    def test_mutate_may_not_change_status_or_history_even_under_python_O(self) -> None:
        self._create("running")
        with self.assertRaises(LifecycleError):
            update_status(self.run_dir, mutate=lambda s: s.__setitem__("status", "completed"))
        with self.assertRaises(LifecycleError):
            update_status(self.run_dir, mutate=lambda s: s.__setitem__("lifecycle_history", []))
        self.assertEqual(json.loads((self.run_dir / "status.json").read_text("utf-8"))["status"], "running")
        code = (
            "import sys\n"
            "from backend.lifecycle.run_status import update_status\n"
            "from backend.lifecycle.states import LifecycleError\n"
            "try:\n"
            "    update_status(sys.argv[1], mutate=lambda s: s.__setitem__('status', 'completed'))\n"
            "except LifecycleError:\n"
            "    print('refused')\n"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-O", "-c", code, str(self.run_dir)], cwd=ROOT,
            env=_environment(), capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(completed.stdout.strip(), "refused", completed.stderr)

    def test_legacy_unknown_status_is_replaced_only_by_record_writers(self) -> None:
        with self.assertRaises(LegacyStatusError):
            update_status(self.run_dir, transition="failed", reason_code="X")
        (self.run_dir / "status.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(LegacyStatusError):
            update_status(self.run_dir, mutate=lambda s: s.update(a=1), merge_unknown=True)
        failed = record_light_failure(
            self.run_dir, run_id="run-a", project_id="p", mode="smoke",
            error_code="GF_WORKER_IMPORT_FAILED", message="numpy is broken",
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["lifecycle_history"][-1]["from"], "unknown")
        self.assertEqual(failed["warnings"][-1]["code"], "GF_STATUS_READ_WARNING")
        preserved = list(self.run_dir.glob("status.invalid-*.json"))
        self.assertEqual(len(preserved), 1)
        self.assertEqual(preserved[0].read_text("utf-8"), "{not json")
        self.assertTrue((self.run_dir / "diagnostics" / "error.json").is_file())
        # A state that is not in the table is unknown as well.
        other = Path(self.folder.name) / "run-b"
        other.mkdir()
        (other / "status.json").write_text(json.dumps({"id": "run-b", "status": "exploded"}), "utf-8")
        with self.assertRaises(LegacyStatusError):
            update_status(other, transition="failed", reason_code="X")
        merged = update_status(other, mutate=lambda s: s.update(evidence=1), merge_unknown=True)
        self.assertEqual(merged["status"], "exploded")
        self.assertEqual(merged["evidence"], 1)

    def test_late_worker_writes_change_nothing_sealed(self) -> None:
        from backend.model_runner import record_run_cancelled, record_run_failure

        self._create("running")
        update_status(self.run_dir, transition="failed", reason_code="GF_WORKER_LOST")
        (self.run_dir / "diagnostics").mkdir()
        artifacts = {
            "status.json": None,
            "provenance.json": b'{"sealed": true}',
            "diagnostics/error.json": b'{"error_code": "GF_WORKER_LOST"}',
            "project-snapshot.json": b'{"id": "p"}',
            "data-pack-snapshot.json": b'{"id": "pack"}',
            "preflight.json": b'{"accepted": true}',
        }
        for name, data in artifacts.items():
            if data is not None:
                (self.run_dir / name).write_bytes(data)
        before = {name: _sha(self.run_dir / name) for name in artifacts}
        diagnostics_before = sorted(path.name for path in (self.run_dir / "diagnostics").iterdir())
        status_path = self.run_dir / "status.json"
        with self.assertRaises(LateWriteRejected):
            record_run_failure(status_path, run_id="run-a", project_id="p", mode="smoke",
                               error=RuntimeError("late"))
        with self.assertRaises(LateWriteRejected):
            record_run_cancelled(status_path, run_id="run-a", project_id="p", mode="smoke",
                                 message="Cancellation accepted before worker execution")
        with self.assertRaises(LateWriteRejected):
            update_status(self.run_dir, mutate=lambda s: s.update(results=[1]),
                          transition="completed", reason_code="GF_RUN_COMPLETED", writer=WRITER_WORKER)
        with self.assertRaises(LateWriteRejected):
            record_light_failure(self.run_dir, run_id="run-a", project_id="p", mode="smoke",
                                 error_code="GF_WORKER_TERMINATED", message="late")
        self.assertEqual({name: _sha(self.run_dir / name) for name in artifacts}, before)
        self.assertEqual(sorted(path.name for path in (self.run_dir / "diagnostics").iterdir()), diagnostics_before)
        late = sorted(self.run_dir.glob("late-worker-*.json"))
        self.assertEqual(len(late), 4)
        record = json.loads(late[0].read_text("utf-8"))
        self.assertEqual(record["schema_version"], "value.late-worker-write/v1")
        self.assertEqual(record["observed_status"], "failed")
        self.assertTrue(any(
            json.loads(path.read_text("utf-8"))["attempted_fields"] == ["results"] for path in late
        ))

    def test_late_write_never_recreates_a_moved_run_directory(self) -> None:
        self._create("failed")
        moved = Path(self.folder.name) / "trash-copy"
        self.run_dir.rename(moved)
        with self.assertRaises(FileNotFoundError):
            update_status(self.run_dir, mutate=lambda s: s.update(x=1), writer=WRITER_WORKER)
        self.assertFalse(self.run_dir.exists())

    def test_server_write_refused_while_worker_holds_the_lease(self) -> None:
        self._create("queued")
        holder = subprocess.Popen(
            [sys.executable, "-B", "-c", HOLD_WORKER_LOCK, str(self.run_dir / "worker.lock")],
            cwd=ROOT, env=_environment(), stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            with self.assertRaises(LeaseHeldError):
                update_status(self.run_dir, transition="failed", reason_code="GF_WORKER_LOST", writer=WRITER_SERVER)
            # The worker itself (and an unspecified internal caller) may write.
            update_status(self.run_dir, transition="running", reason_code="GF_WORKER_STARTED", writer=WRITER_WORKER)
        finally:
            holder.kill()
            holder.wait(timeout=10)
            holder.stdout.close()
        update_status(self.run_dir, transition="failed", reason_code="GF_WORKER_LOST", writer=WRITER_SERVER)

    def test_completion_merges_and_keeps_application_and_server_fields(self) -> None:
        self._create("queued", quota={"reserved_bytes": 10}, extensions={"value_101": {"x": 1}})
        update_status(self.run_dir, transition="running", reason_code="GF_WORKER_STARTED", writer=WRITER_WORKER)
        # The application records recovery evidence while the worker runs.
        update_status(self.run_dir, writer=WRITER_WORKER, merge_unknown=True,
                      mutate=lambda s: s.update(subannual_recovery={"id": "c1"},
                                                subannual_recovery_authorization={"state": "consumed"}))
        final = update_status(self.run_dir, writer=WRITER_WORKER, transition="completed",
                              reason_code="GF_RUN_COMPLETED",
                              mutate=lambda s: s.update(results=[], current_stage="Run completed"))
        for key in ("subannual_recovery", "subannual_recovery_authorization", "quota", "extensions"):
            self.assertIn(key, final)

    def test_concurrent_writers_lose_no_update_and_readers_never_see_partial_json(self) -> None:
        self._create("running")
        stop = threading.Event()
        reader_errors: list[str] = []

        def reader() -> None:
            while not stop.is_set():
                try:
                    json.loads((self.run_dir / "status.json").read_text("utf-8"))
                except (FileNotFoundError, json.JSONDecodeError) as exc:
                    reader_errors.append(type(exc).__name__)

        thread = threading.Thread(target=reader)
        thread.start()
        writers = [
            subprocess.Popen([sys.executable, "-B", "-c", RACE_WRITER, str(self.run_dir), f"field{i}", "300"],
                             cwd=ROOT, env=_environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for i in range(3)
        ]
        try:
            outputs = [writer.communicate(timeout=300) for writer in writers]
        finally:
            stop.set()
            thread.join(timeout=30)
        self.assertEqual([int(out.strip()) for out, _ in outputs], [0, 0, 0], [err for _, err in outputs])
        final = json.loads((self.run_dir / "status.json").read_text("utf-8"))
        self.assertEqual([final[f"field{i}"] for i in range(3)], [300, 300, 300])
        self.assertEqual(reader_errors, [])
        self.assertEqual([path.name for path in self.run_dir.iterdir() if path.suffix == ".tmp"], [])


class WriterMigrationStaticTests(unittest.TestCase):
    WRITERS = (
        "backend/model_runner.py", "backend/server.py", "backend/run_execution.py",
        "gridform_core/application.py", "gridform_core/provenance.py", "gridform_core/run_lifecycle.py",
    )

    def test_no_fixed_temporary_names_remain_in_status_writers(self) -> None:
        pattern = re.compile(r"with_suffix\([^)]*\.tmp[\"']\)|suffix \+ [\"']\.tmp[\"']")
        offenders = [
            name for name in self.WRITERS
            if pattern.search((ROOT / name).read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])

    def test_no_silent_exception_swallowing_in_lifecycle_code(self) -> None:
        pattern = re.compile(r"except (?:Exception|BaseException)(?: as \w+)?:\s*\n\s*pass\b")
        names = [*(path.relative_to(ROOT).as_posix() for path in (ROOT / "backend" / "lifecycle").glob("*.py")),
                 "backend/model_runner.py", "backend/server.py"]
        supervisor = ROOT / "backend" / "run_supervisor.py"
        if supervisor.is_file():
            names.append("backend/run_supervisor.py")
        offenders = [name for name in names if pattern.search((ROOT / name).read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_status_json_is_written_only_through_run_status(self) -> None:
        offenders = []
        for name in self.WRITERS:
            text = (ROOT / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                if re.search(r"(atomic_json|write_json|_atomic_json_artifact)\([^)]*status(_path\b|\.json)", line):
                    offenders.append(f"{name}: {line.strip()}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
