"""P0-3 S3: the light worker entry point and its lease."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from backend.lifecycle.python_argv import isolated_python_argv, worker_python_argv
from backend.lifecycle.run_status import create_status, read_status
from backend.lifecycle.worker_lease import SPAWN_SCHEMA_V2

ROOT = Path(__file__).resolve().parents[1]

DRIVER = """
import sys, time
import backend.model_runner as model_runner
from backend.lifecycle.run_status import update_status
from gridform_core.v2.orchestrator import CancellationRequested
behaviour = sys.argv[1]
def run(project_id, run_id, mode):
    if behaviour == "sleep":
        print("running", flush=True)
        time.sleep(60)
    elif behaviour == "interrupt":
        raise KeyboardInterrupt
    elif behaviour == "cancel":
        raise CancellationRequested("Cancellation accepted before worker execution")
    elif behaviour == "complete":
        run_dir = model_runner.STATE_ROOT / "runs" / run_id
        update_status(run_dir, transition="running", reason_code="GF_WORKER_STARTED", writer="worker")
        update_status(run_dir, transition="completed", reason_code="GF_RUN_COMPLETED", writer="worker")
model_runner.run = run
from backend.lifecycle.worker_entry import main
raise SystemExit(main(sys.argv[2:]))
"""

HOLDER = """
import sys, time
from backend.lifecycle.file_locks import FileLock
lock = FileLock(sys.argv[1]).acquire()
print("held", flush=True)
time.sleep(60)
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WorkerEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.state = Path(self.folder.name) / "state"
        self.run_id = "study-20261005-000000-abcdef12"
        self.run_dir = self.state / "runs" / self.run_id
        self.run_dir.mkdir(parents=True)
        self.prefix = Path(self.folder.name) / "pycache"
        self.prefix.mkdir()
        self.nonce = "a" * 32
        create_status(self.run_dir, {"id": self.run_id, "project_id": "study", "mode": "smoke", "status": "queued"})
        (self.run_dir / "worker.json").write_text(json.dumps({
            "schema_version": SPAWN_SCHEMA_V2, "lease_nonce": self.nonce,
        }), encoding="utf-8")
        self.processes: list[subprocess.Popen] = []
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=30)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

    def _environment(self, *front: Path) -> dict[str, str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join([*(str(path) for path in front), str(ROOT)])
        environment["VALUE_DATA_HOME"] = str(self.state)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return environment

    def _entry_arguments(self, nonce: str | None = None) -> list[str]:
        return ["--run-dir", str(self.run_dir), "--lease-nonce", nonce or self.nonce,
                "--project", "study", "--run", self.run_id, "--mode", "smoke"]

    def _worker(self, *front: Path, nonce: str | None = None) -> subprocess.Popen:
        process = subprocess.Popen(
            [*worker_python_argv(sys.executable, self.prefix), *self._entry_arguments(nonce)],
            cwd=ROOT, env=self._environment(*front), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.processes.append(process)
        return process

    def _driver(self, behaviour: str) -> subprocess.Popen:
        process = subprocess.Popen(
            [*isolated_python_argv(sys.executable, self.prefix), "-c", DRIVER, behaviour, *self._entry_arguments()],
            cwd=ROOT, env=self._environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.processes.append(process)
        return process

    def test_argv_helpers_follow_the_conventions(self) -> None:
        self.assertEqual(isolated_python_argv("py", "/p"), ["py", "-B", "-s", "-X", "pycache_prefix=/p"])
        self.assertEqual(worker_python_argv("py", "/p")[-2:], ["-m", "backend.worker_entry"])

    def test_phase_one_takes_the_lease_fast_without_numpy(self) -> None:
        started = time.monotonic()
        process = self._worker()
        lease = self.run_dir / "worker-lease.json"
        while not lease.is_file() and process.poll() is None and time.monotonic() - started < 30:
            time.sleep(0.005)
        wall = time.monotonic() - started
        process.communicate(timeout=300)
        record = json.loads(lease.read_text(encoding="utf-8"))
        self.assertFalse(record["heavy_modules_loaded"])
        # In-process time from the entry module to the held lease (<0.5 s); the
        # wall-clock bound includes interpreter start-up and a loaded test host.
        self.assertLess(record["startup_seconds"], 0.5)
        self.assertLess(wall, 5.0)
        self.assertEqual(record["lease_nonce"], self.nonce)
        # The fixture has no frozen inputs: phase two fails and records it.
        self.assertEqual(process.returncode, 1)
        status = read_status(self.run_dir)
        self.assertEqual(status["status"], "failed")
        self.assertTrue((self.run_dir / "diagnostics" / "error.json").is_file())

    def test_broken_numpy_is_recorded_as_import_failure(self) -> None:
        broken = Path(self.folder.name) / "broken"
        (broken / "numpy").mkdir(parents=True)
        (broken / "numpy" / "__init__.py").write_text("raise ImportError('deliberately broken numpy')\n", "utf-8")
        process = self._worker(broken)
        _, stderr = process.communicate(timeout=300)
        self.assertEqual(process.returncode, 1, stderr)
        status = read_status(self.run_dir)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error_code"], "GF_WORKER_IMPORT_FAILED")
        diagnostic = json.loads((self.run_dir / "diagnostics" / "error.json").read_text("utf-8"))
        self.assertIn("deliberately broken numpy", diagnostic["exception_message"])

    def test_sigterm_records_termination_and_exits_143(self) -> None:
        process = self._driver("sleep")
        self.assertEqual(process.stdout.readline().strip(), "running")
        os.kill(process.pid, signal.SIGTERM)
        process.communicate(timeout=300)
        self.assertEqual(process.returncode, 143)
        status = read_status(self.run_dir)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error_code"], "GF_WORKER_TERMINATED")

    def test_keyboard_interrupt_is_recorded(self) -> None:
        process = self._driver("interrupt")
        process.communicate(timeout=300)
        self.assertEqual(process.returncode, 130)
        self.assertEqual(read_status(self.run_dir)["error_code"], "GF_WORKER_TERMINATED")

    def test_cancellation_and_completion_exit_zero(self) -> None:
        process = self._driver("cancel")
        process.communicate(timeout=300)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(read_status(self.run_dir)["status"], "cancelled")
        # A resumed run completes normally.
        from backend.lifecycle.run_status import update_status
        update_status(self.run_dir, transition="queued", reason_code="GF_RUN_RESUME_QUEUED", writer="server")
        process = self._driver("complete")
        process.communicate(timeout=300)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(read_status(self.run_dir)["status"], "completed")

    def test_second_worker_exits_75_without_writing(self) -> None:
        holder = subprocess.Popen(
            [sys.executable, "-B", "-c", HOLDER, str(self.run_dir / "worker.lock")],
            cwd=ROOT, env=self._environment(), stdout=subprocess.PIPE, text=True,
        )
        self.processes.append(holder)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        before = _sha(self.run_dir / "status.json")
        process = self._worker()
        process.communicate(timeout=60)
        self.assertEqual(process.returncode, 75)
        self.assertEqual(_sha(self.run_dir / "status.json"), before)
        self.assertFalse((self.run_dir / "worker-lease.json").exists())

    def test_stale_or_late_worker_stands_down_silently(self) -> None:
        before = _sha(self.run_dir / "status.json")
        process = self._worker(nonce="b" * 32)
        process.communicate(timeout=60)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(_sha(self.run_dir / "status.json"), before)
        self.assertFalse((self.run_dir / "worker-lease.json").exists())
        from backend.lifecycle.run_status import update_status
        update_status(self.run_dir, transition="failed", reason_code="GF_WORKER_LOST", writer="server")
        before = _sha(self.run_dir / "status.json")
        process = self._worker()
        process.communicate(timeout=60)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(_sha(self.run_dir / "status.json"), before)
        self.assertFalse((self.run_dir / "diagnostics").exists())


if __name__ == "__main__":
    unittest.main()
