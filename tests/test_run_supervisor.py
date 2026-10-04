"""P0-3 S4: worker spawning, reaping, orphan supervision, reconciliation."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import run_supervisor as supervisor_module
from backend.lifecycle.file_locks import LOCK_FREE, probe_lock
from backend.lifecycle.run_status import create_status, read_status, update_status
from backend.lifecycle.worker_lease import SPAWN_SCHEMA_V1, SPAWN_SCHEMA_V2
from backend.run_supervisor import (
    LIVENESS_ALIVE,
    LIVENESS_LOST,
    LIVENESS_STARTING,
    LIVENESS_UNVERIFIABLE,
    RunSupervisor,
    WorkerSpawnError,
    worker_liveness,
)

ROOT = Path(__file__).resolve().parents[1]

HOLDER = """
import sys, time
from backend.lifecycle.file_locks import FileLock
lock = FileLock(sys.argv[1]).acquire()
print("held", flush=True)
time.sleep(120)
"""

SINGLETON_SPAWNER = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from backend import run_supervisor
from backend.lifecycle.file_locks import FileLock
state = Path(sys.argv[1]); run_dir = state / "runs" / "r1"
lock = FileLock(state / ".backend.lock").acquire(timeout=0)
fake = lambda python, prefix, **_options: [python, "-c", "import time; time.sleep(60)"]
with patch.object(run_supervisor, "worker_python_argv", fake):
    record = run_supervisor.RunSupervisor(state / "runs", run_lock=lambda _r: None).spawn_worker(
        run_dir=run_dir, run_id="r1", project_id="p", mode="smoke", python=sys.executable, cwd=Path.cwd())
print(record["pid"], flush=True)
os._exit(0)
"""


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _fake_argv(code: str):
    return lambda python, prefix, **_options: [python, "-B", "-c", code]


def _zombie_children() -> list[int]:
    zombies = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if fields[0] == "Z" and int(fields[1]) == os.getpid():
            zombies.append(int(entry.name))
    return zombies


class _Locks:
    def __init__(self) -> None:
        self.locks: dict[str, threading.RLock] = {}
        self.guard = threading.Lock()

    def __call__(self, run_id: str) -> threading.RLock:
        with self.guard:
            return self.locks.setdefault(run_id, threading.RLock())


@unittest.skipUnless(sys.platform.startswith("linux"), "uses /proc and POSIX signals")
class RunSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.state = Path(self.folder.name) / "state"
        self.runs = self.state / "runs"
        self.runs.mkdir(parents=True)
        self.locks = _Locks()
        self.supervisor = RunSupervisor(self.runs, run_lock=self.locks, reconciler_mode="apply", windows=False)
        self.extra_pids: list[int] = []
        self.processes: list[subprocess.Popen] = []
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=30)
            if process.stdout is not None:
                process.stdout.close()
        for pid in self.extra_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def _run(self, run_id: str, state: str = "queued", **fields) -> Path:
        run_dir = self.runs / run_id
        run_dir.mkdir()
        create_status(run_dir, {"id": run_id, "project_id": "p", "mode": "smoke", "status": state, **fields})
        return run_dir

    def _spawn(self, run_dir: Path, code: str) -> dict:
        with patch.object(supervisor_module, "worker_python_argv", _fake_argv(code)):
            return self.supervisor.spawn_worker(
                run_dir=run_dir, run_id=run_dir.name, project_id="p", mode="smoke",
                python=sys.executable, cwd=ROOT, environment=_environment(),
            )

    def _wait_status(self, run_dir: Path, states: set[str], timeout: float = 30.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = read_status(run_dir) or {}
            if status.get("status") in states:
                return status
            time.sleep(0.02)
        self.fail(f"{run_dir.name} did not reach {states}: {read_status(run_dir)}")

    def _holder(self, run_dir: Path) -> subprocess.Popen:
        holder = subprocess.Popen(
            [sys.executable, "-B", "-c", HOLDER, str(run_dir / "worker.lock")],
            cwd=ROOT, env=_environment(), stdout=subprocess.PIPE, text=True,
        )
        self.processes.append(holder)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        return holder

    def test_exit_3_is_recorded_reaped_and_leaves_no_zombie(self) -> None:
        run_dir = self._run("r-exit")
        record = self._spawn(run_dir, "import sys; sys.exit(3)")
        self.assertEqual(record["schema_version"], SPAWN_SCHEMA_V2)
        self.assertEqual(len(record["lease_nonce"]), 32)
        status = self._wait_status(run_dir, {"failed"})
        self.assertEqual(status["lifecycle_reason_code"], "GF_WORKER_EXITED")
        self.assertEqual(status["worker_outcome"]["returncode"], 3)
        exit_record = json.loads((run_dir / "worker-exit.json").read_text("utf-8"))
        self.assertEqual(exit_record["returncode"], 3)
        with self.assertRaises(ChildProcessError):
            os.waitpid(record["pid"], os.WNOHANG)
        self.assertEqual(_zombie_children(), [])
        argv = record["argv"]
        self.assertFalse(any("unused-bytecode-cache" in part for part in argv))

    def test_sigkill_of_own_worker_fails_within_six_seconds(self) -> None:
        run_dir = self._run("r-kill")
        record = self._spawn(run_dir, "import time; time.sleep(60)")
        started = time.monotonic()
        os.kill(record["pid"], signal.SIGKILL)
        status = self._wait_status(run_dir, {"failed"}, timeout=6)
        self.assertLess(time.monotonic() - started, 6)
        self.assertEqual(status["worker_outcome"]["signal"], 9)
        self.assertEqual(status["error_code"], "GF_WORKER_EXITED")
        self.assertEqual(_zombie_children(), [])

    def test_pending_cancellation_ends_cancelled(self) -> None:
        run_dir = self._run("r-cancel")
        (run_dir / "cancel-request.json").write_text(json.dumps({"schema_version": "value.cancel-request/v1"}), "utf-8")
        self._spawn(run_dir, "import sys; sys.exit(0)")
        status = self._wait_status(run_dir, {"cancelled", "failed"})
        self.assertEqual(status["status"], "cancelled")

    def test_worker_is_detached_in_its_own_session(self) -> None:
        run_dir = self._run("r-session")
        record = self._spawn(run_dir, "import time; time.sleep(60)")
        try:
            self.assertEqual(os.getsid(record["pid"]), record["pid"])
            self.assertNotEqual(os.getpgid(record["pid"]), os.getpgid(0))
        finally:
            os.kill(record["pid"], signal.SIGKILL)
        self._wait_status(run_dir, {"failed"})

    def test_spawn_failure_raises_and_leaves_no_prefix(self) -> None:
        run_dir = self._run("r-spawn")
        with patch.object(supervisor_module.subprocess, "Popen", side_effect=OSError("no exec")), \
                patch.object(supervisor_module, "new_pycache_prefix", return_value=Path(self.folder.name) / "prefix") as made:
            (Path(self.folder.name) / "prefix").mkdir()
            with self.assertRaises(WorkerSpawnError):
                self.supervisor.spawn_worker(run_dir=run_dir, run_id="r-spawn", project_id="p", mode="smoke",
                                             python=sys.executable, cwd=ROOT)
            self.assertTrue(made.called)
        self.assertFalse((Path(self.folder.name) / "prefix").exists())

    def test_orphan_with_live_lease_is_kept_and_lost_after_its_death(self) -> None:
        run_dir = self._run("r-orphan", "running")
        (run_dir / "worker.json").write_text(json.dumps({
            "schema_version": SPAWN_SCHEMA_V2, "lease_nonce": "n" * 32, "created_epoch": time.time() - 3600,
        }), "utf-8")
        holder = self._holder(run_dir)
        self.supervisor.tick()
        self.assertEqual(read_status(run_dir)["status"], "running")
        self.assertEqual(worker_liveness(run_dir)[0], LIVENESS_ALIVE)
        holder.kill(); holder.wait(timeout=10)
        self.supervisor.tick()
        status = read_status(run_dir)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["lifecycle_reason_code"], "GF_WORKER_LOST")
        self.supervisor.drain_seals()  # no sealer configured: nothing to do

    def test_tick_skips_runs_whose_action_lock_is_held(self) -> None:
        run_dir = self._run("r-busy", "snapshotting")
        lock = self.locks("r-busy")
        acquired = threading.Event(); release = threading.Event()

        def hold() -> None:
            with lock:
                acquired.set(); release.wait(10)

        thread = threading.Thread(target=hold); thread.start(); acquired.wait(5)
        try:
            self.supervisor.tick()
            self.assertEqual(read_status(run_dir)["status"], "snapshotting")
        finally:
            release.set(); thread.join()
        self.supervisor.tick()
        self.assertEqual(read_status(run_dir)["status"], "failed")

    def test_grace_period_for_a_starting_worker(self) -> None:
        run_dir = self._run("r-grace")
        sleeper = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(60)"])
        self.processes.append(sleeper)
        (run_dir / "worker.json").write_text(json.dumps({
            "schema_version": SPAWN_SCHEMA_V2, "lease_nonce": "n" * 32,
            "created_epoch": time.time(), "pid": sleeper.pid,
        }), "utf-8")
        self.assertEqual(worker_liveness(run_dir)[0], LIVENESS_STARTING)
        self.supervisor.tick()
        self.assertEqual(read_status(run_dir)["status"], "queued")
        with patch.object(supervisor_module, "SPAWN_GRACE_SECONDS", 0.0):
            self.supervisor.tick()
        self.assertEqual(read_status(run_dir)["status"], "failed")

    def test_v1_worker_judged_by_proc_argv(self) -> None:
        alive_dir = self._run("r-v1-alive", "running")
        lookalike = subprocess.Popen(
            [sys.executable, "-B", "-c", "import time; time.sleep(60)", "-m", "backend.model_runner", "--run", "r-v1-alive"],
        )
        self.processes.append(lookalike)
        time.sleep(0.2)
        (alive_dir / "worker.json").write_text(json.dumps({"schema_version": SPAWN_SCHEMA_V1, "pid": lookalike.pid}), "utf-8")
        dead_dir = self._run("r-v1-dead", "running")
        (dead_dir / "worker.json").write_text(json.dumps({"schema_version": SPAWN_SCHEMA_V1, "pid": os.getpid()}), "utf-8")
        self.assertEqual(worker_liveness(alive_dir)[0], LIVENESS_ALIVE)
        self.assertEqual(worker_liveness(dead_dir)[0], LIVENESS_LOST)
        report = self.supervisor.reconcile_all()
        self.assertIn("r-v1-alive", report.alive)
        self.assertEqual(read_status(alive_dir)["status"], "running")
        self.assertEqual(read_status(dead_dir)["status"], "failed")
        with patch.object(supervisor_module, "v1_worker_matches", return_value=None):
            self.assertEqual(worker_liveness(alive_dir)[0], LIVENESS_UNVERIFIABLE)

    def test_reconcile_is_fast_with_a_one_gib_sparse_file_and_observe_writes_nothing(self) -> None:
        for index in range(5):
            run_dir = self._run(f"r-sparse-{index}", "running")
            output = run_dir / "model-output"
            output.mkdir()
            with (output / "big.bin").open("wb") as handle:
                handle.truncate(1024 ** 3)
        before = {path.name: (path / "status.json").read_bytes() for path in self.runs.iterdir()}
        observer = RunSupervisor(self.runs, run_lock=self.locks, reconciler_mode="observe", windows=False)
        report = observer.reconcile_all()
        self.assertTrue(report.observed_only)
        self.assertEqual(len(report.settled), 5)
        self.assertEqual({path.name: (path / "status.json").read_bytes() for path in self.runs.iterdir()}, before)
        started = time.monotonic()
        report = self.supervisor.reconcile_all()
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(len(report.settled), 5)
        self.assertTrue(all(read_status(path)["status"] == "failed" for path in self.runs.iterdir()))

    def test_repairs_a_run_left_in_deleting(self) -> None:
        run_dir = self._run("r-deleting", "completed")
        update_status(run_dir, transition="deleting", reason_code="GF_RUN_MOVING_TO_TRASH")
        report = self.supervisor.reconcile_all()
        status = read_status(run_dir)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["lifecycle_reason_code"], "GF_RUN_DELETE_INTERRUPTED_REPAIRED")
        self.assertEqual(report.repaired, [{"run_id": "r-deleting", "to": "completed"}])

    def test_windows_needs_two_free_probes_five_seconds_apart(self) -> None:
        run_dir = self._run("r-win", "running")
        (run_dir / "worker.json").write_text(json.dumps({
            "schema_version": SPAWN_SCHEMA_V2, "created_epoch": time.time() - 3600,
        }), "utf-8")
        clock = [100.0]
        windows = RunSupervisor(self.runs, run_lock=self.locks, reconciler_mode="apply", windows=True,
                                clock=lambda: clock[0])
        windows.tick()
        self.assertEqual(read_status(run_dir)["status"], "running")
        clock[0] += 4.9
        windows.tick()
        self.assertEqual(read_status(run_dir)["status"], "running")
        clock[0] += 0.2
        windows.tick()
        self.assertEqual(read_status(run_dir)["status"], "failed")

    def test_mark_lost_confirmation_and_quiet_gates(self) -> None:
        run_dir = self._run("r-mark", "running")
        (run_dir / "worker.json").write_text(json.dumps({"schema_version": SPAWN_SCHEMA_V1, "pid": 1}), "utf-8")
        with patch.object(supervisor_module, "v1_worker_matches", return_value=None):
            code, payload = self.supervisor.mark_lost(run_dir, confirm_run_id="wrong")
            self.assertEqual((code, payload["error_code"]), (409, "GF_MARK_LOST_CONFIRMATION_REQUIRED"))
            code, payload = self.supervisor.mark_lost(run_dir, confirm_run_id="r-mark")
            self.assertEqual((code, payload["error_code"]), (409, "GF_MARK_LOST_NOT_QUIET"))
            self.assertEqual(read_status(run_dir)["status"], "running")
            old = time.time() - 16 * 60
            for path in run_dir.rglob("*"):
                os.utime(path, (old, old))
            code, payload = self.supervisor.mark_lost(run_dir, confirm_run_id="r-mark")
        self.assertEqual(code, 200)
        self.assertEqual(payload["run"]["status"], "failed")
        self.assertEqual(payload["run"]["lifecycle_reason_code"], "GF_WORKER_MARKED_LOST")
        live_dir = self._run("r-live", "running")
        self._holder(live_dir)
        code, payload = self.supervisor.mark_lost(live_dir, confirm_run_id="r-live", quiet_seconds=0)
        self.assertEqual((code, payload["error_code"]), (409, "GF_WORKER_ALIVE"))

    def test_reaper_and_tick_interleaved_fifty_times_give_one_reason(self) -> None:
        stop = threading.Event()

        def ticking() -> None:
            while not stop.is_set():
                self.supervisor.tick()

        thread = threading.Thread(target=ticking)
        thread.start()
        try:
            run_dirs = []
            for index in range(50):
                run_id = f"r-loop-{index:02d}"
                # As in the server: creation and spawn happen under the run's
                # action lock, which the tick never waits for.
                with self.locks(run_id):
                    run_dir = self._run(run_id)
                    self._spawn(run_dir, "import sys; sys.exit(5)")
                run_dirs.append(run_dir)
            reasons = {self._wait_status(path, {"failed"})["lifecycle_reason_code"] for path in run_dirs}
        finally:
            stop.set()
            thread.join(timeout=30)
        self.assertEqual(reasons, {"GF_WORKER_EXITED"})
        deadline = time.monotonic() + 10
        while _zombie_children() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(_zombie_children(), [])

    def test_singleton_lock_is_not_inherited_by_a_spawned_worker(self) -> None:
        run_dir = self._run("r1")
        spawner = subprocess.Popen(
            [sys.executable, "-B", "-c", SINGLETON_SPAWNER, str(self.state)],
            cwd=ROOT, env=_environment(), stdout=subprocess.PIPE, text=True,
        )
        self.processes.append(spawner)
        worker_pid = int(spawner.stdout.readline().strip())
        self.extra_pids.append(worker_pid)
        spawner.wait(timeout=30)
        os.kill(worker_pid, 0)  # the detached worker is still running
        self.assertEqual(probe_lock(self.state / ".backend.lock"), LOCK_FREE)
        self.assertTrue(run_dir.is_dir())


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX process groups")
class BackendSingletonTests(unittest.TestCase):
    def test_second_backend_on_the_same_data_directory_exits_3(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            environment = _environment()
            environment["VALUE_DATA_HOME"] = str(Path(folder) / "state")
            first = subprocess.Popen(
                [sys.executable, "-B", "-m", "backend.server", "--port", "0"],
                cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                line = first.stdout.readline()
                self.assertIn("VALUE modular API", line, first.stderr.read() if first.poll() is not None else "")
                second = subprocess.run(
                    [sys.executable, "-B", "-m", "backend.server", "--port", "0"],
                    cwd=ROOT, env=environment, capture_output=True, text=True, timeout=120,
                )
                self.assertEqual(second.returncode, 3, second.stderr)
                self.assertIn("another VALUE backend", second.stderr)
                self.assertIsNone(first.poll())
            finally:
                first.send_signal(signal.SIGTERM)
                first.communicate(timeout=60)
            self.assertEqual(first.returncode, 0)


if __name__ == "__main__":
    unittest.main()
