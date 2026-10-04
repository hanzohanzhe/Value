"""P0-3 S1: standard-library lifecycle primitives (locks, atomic writes, states)."""

from __future__ import annotations

import ast
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

from backend.lifecycle import atomic_io, file_locks, states
from backend.lifecycle.atomic_io import atomic_write_json, write_new_json
from backend.lifecycle.file_locks import (
    LOCK_ABSENT,
    LOCK_FREE,
    LOCK_HELD,
    FileLock,
    LockReentryError,
    LockTimeout,
    hold_lock,
    probe_lock,
    try_acquire,
)

ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "backend" / "lifecycle"


def _child_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _python(code: str, *arguments: str, **options) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-B", "-c", code, *arguments],
        cwd=ROOT, env=_child_environment(), **options,
    )


COUNTER_WORKER = """
import json, sys
from pathlib import Path
from backend.lifecycle.atomic_io import atomic_write_json
from backend.lifecycle.file_locks import hold_lock
path = Path(sys.argv[1]); lock = path.with_name("counter.lock")
failures = 0
for _ in range(int(sys.argv[2])):
    try:
        with hold_lock(lock, timeout=30):
            value = json.loads(path.read_text(encoding="utf-8"))
            value["count"] += 1
            atomic_write_json(path, value)
    except Exception:
        failures += 1
print(failures)
"""

HOLDER = """
import sys, time
from backend.lifecycle.file_locks import FileLock
lock = FileLock(sys.argv[1]).acquire()
print("locked", flush=True)
time.sleep(60)
"""

INHERIT = """
import os, subprocess, sys
from backend.lifecycle.file_locks import FileLock
lock = FileLock(sys.argv[1]).acquire()
child = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(30)"])
print(child.pid, flush=True)
os._exit(0)
"""


class FakeMsvcrt:
    """A tiny stand-in for msvcrt byte-range locking keyed by file identity."""

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self) -> None:
        self.owners: dict[tuple[int, int], int] = {}
        self.calls: list[tuple[int, int]] = []

    def locking(self, descriptor: int, mode: int, length: int) -> None:
        info = os.fstat(descriptor)
        key = (info.st_dev, info.st_ino)
        self.calls.append((mode, length))
        if mode == self.LK_UNLCK:
            if self.owners.get(key) != descriptor:
                raise OSError("not locked by this handle")
            del self.owners[key]
            return
        owner = self.owners.get(key)
        if owner is not None and owner != descriptor:
            raise OSError(36, "Resource deadlock avoided")
        self.owners[key] = descriptor


class FileLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        self.started: list[subprocess.Popen] = []
        self.addCleanup(self._stop_started)

    def _stop_started(self) -> None:
        for process in self.started:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

    def test_four_processes_count_exactly_1200(self) -> None:
        counter = self.root / "counter.json"
        counter.write_text(json.dumps({"count": 0}), encoding="utf-8")
        workers = [
            _python(COUNTER_WORKER, str(counter), "300", stdout=subprocess.PIPE, text=True)
            for _ in range(4)
        ]
        self.started.extend(workers)
        failures = [int(worker.communicate(timeout=120)[0].strip()) for worker in workers]
        self.assertEqual(failures, [0, 0, 0, 0])
        self.assertEqual(json.loads(counter.read_text(encoding="utf-8"))["count"], 1200)
        leftovers = [path.name for path in self.root.iterdir() if path.suffix == ".tmp"]
        self.assertEqual(leftovers, [])

    def test_eight_threads_are_mutually_exclusive(self) -> None:
        lock_path = self.root / "threads.lock"
        inside = 0
        peak = 0
        total = 0
        guard = threading.Lock()

        def work() -> None:
            nonlocal inside, peak, total
            for _ in range(25):
                with hold_lock(lock_path, timeout=30):
                    with guard:
                        inside += 1
                        peak = max(peak, inside)
                    snapshot = total
                    time.sleep(0.0005)
                    total = snapshot + 1
                    with guard:
                        inside -= 1

        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertEqual(peak, 1)
        self.assertEqual(total, 200)

    def test_reentry_is_reported_within_50_ms(self) -> None:
        lock_path = self.root / "reentry.lock"
        with hold_lock(lock_path):
            started = time.perf_counter()
            with self.assertRaises(LockReentryError):
                FileLock(lock_path).acquire(timeout=5)
            self.assertLess(time.perf_counter() - started, 0.05)
            self.assertEqual(probe_lock(lock_path), LOCK_HELD)
        self.assertEqual(probe_lock(lock_path), LOCK_FREE)
        # Released cleanly: the same thread may take it again.
        with hold_lock(lock_path, timeout=1):
            pass

    def test_timeout_is_an_os_error_and_carries_the_path(self) -> None:
        lock_path = self.root / "busy.lock"
        holder = _python(HOLDER, str(lock_path), stdout=subprocess.PIPE, text=True)
        self.started.append(holder)
        self.assertEqual(holder.stdout.readline().strip(), "locked")
        started = time.monotonic()
        with self.assertRaises(LockTimeout) as caught:
            FileLock(lock_path).acquire(timeout=0.2)
        self.assertGreaterEqual(time.monotonic() - started, 0.19)
        self.assertIsInstance(caught.exception, OSError)
        self.assertIsInstance(caught.exception, TimeoutError)
        self.assertEqual(caught.exception.path, str(lock_path))
        self.assertIsNone(try_acquire(lock_path))
        self.assertEqual(probe_lock(lock_path), LOCK_HELD)

    def test_sigkill_releases_the_lock(self) -> None:
        lock_path = self.root / "killed.lock"
        holder = _python(HOLDER, str(lock_path), stdout=subprocess.PIPE, text=True)
        self.started.append(holder)
        self.assertEqual(holder.stdout.readline().strip(), "locked")
        self.assertEqual(probe_lock(lock_path), LOCK_HELD)
        os.kill(holder.pid, signal.SIGKILL)
        holder.wait(timeout=10)
        self.assertEqual(probe_lock(lock_path), LOCK_FREE)
        self.assertTrue(lock_path.is_file(), "lock files are never unlinked")

    def test_child_process_does_not_inherit_the_lock(self) -> None:
        lock_path = self.root / "inherit.lock"
        parent = _python(INHERIT, str(lock_path), stdout=subprocess.PIPE, text=True)
        self.started.append(parent)
        grandchild_pid = int(parent.stdout.readline().strip())
        parent.wait(timeout=10)
        try:
            os.kill(grandchild_pid, 0)  # still alive
            self.assertEqual(probe_lock(lock_path), LOCK_FREE)
        finally:
            try:
                os.kill(grandchild_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_probe_never_creates_a_lock_file_or_directory(self) -> None:
        missing = self.root / "gone" / "worker.lock"
        self.assertEqual(probe_lock(missing), LOCK_ABSENT)
        self.assertFalse(missing.parent.exists())
        with self.assertRaises(FileNotFoundError):
            FileLock(missing).acquire(timeout=0)
        self.assertFalse(missing.parent.exists())

    def test_windows_branch_with_mocked_msvcrt(self) -> None:
        fake = FakeMsvcrt()
        lock_path = self.root / "windows.lock"
        with patch.object(file_locks, "_msvcrt", fake), patch.object(file_locks, "_fcntl", None):
            first = FileLock(lock_path).acquire(timeout=1)
            self.assertEqual(lock_path.read_bytes(), b"0")
            self.assertEqual(probe_lock(lock_path), LOCK_HELD)
            other = threading.Thread(target=lambda: self.assertIsNone(try_acquire(lock_path)))
            other.start(); other.join()
            with self.assertRaises(LockTimeout):
                worker_result: list[BaseException] = []

                def contend() -> None:
                    try:
                        FileLock(lock_path).acquire(timeout=0.05)
                    except BaseException as exc:  # noqa: BLE001 - re-raised below
                        worker_result.append(exc)

                thread = threading.Thread(target=contend)
                thread.start(); thread.join()
                raise worker_result[0]
            first.release()
            self.assertEqual(probe_lock(lock_path), LOCK_FREE)
            with hold_lock(lock_path, timeout=1):
                pass
        self.assertIn((FakeMsvcrt.LK_NBLCK, 1), fake.calls)
        self.assertIn((FakeMsvcrt.LK_UNLCK, 1), fake.calls)


class AtomicWriteTests(unittest.TestCase):
    def test_missing_directory_is_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "moved-run" / "status.json"
            with self.assertRaises(FileNotFoundError):
                atomic_write_json(target, {"status": "failed"})
            self.assertFalse(target.parent.exists())

    def test_unique_temporary_names_and_no_leftovers(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "status.json"
            names: list[str] = []
            real = os.replace

            def spy(source, destination):
                names.append(Path(source).name)
                return real(source, destination)

            with patch.object(atomic_io.os, "replace", side_effect=spy):
                atomic_write_json(target, {"a": 1})
                atomic_write_json(target, {"a": 2})
            self.assertEqual(len(set(names)), 2)
            self.assertTrue(all(name.startswith(".status.json.") and name.endswith(".tmp") for name in names))
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"a": 2})
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ["status.json"])

    def test_failed_replace_leaves_destination_and_no_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "status.json"
            atomic_write_json(target, {"keep": True})
            with patch.object(atomic_io.os, "replace", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    atomic_write_json(target, {"keep": False})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"keep": True})
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ["status.json"])

    def test_windows_terminal_replace_retries_permission_errors(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "status.json"
            real = os.replace
            attempts = {"count": 0}

            def flaky(source, destination):
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise PermissionError("sharing violation")
                return real(source, destination)

            with patch.object(atomic_io, "_IS_WINDOWS", True), \
                    patch.object(atomic_io.os, "replace", side_effect=flaky):
                atomic_write_json(target, {"done": True}, replace_retry_seconds=10)
            self.assertEqual(attempts["count"], 3)
            with patch.object(atomic_io, "_IS_WINDOWS", False), \
                    patch.object(atomic_io.os, "replace", side_effect=PermissionError("no")):
                with self.assertRaises(PermissionError):
                    atomic_write_json(target, {"done": False}, replace_retry_seconds=10)

    def test_write_new_json_refuses_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "status.json"
            write_new_json(target, {"first": True})
            with self.assertRaises(FileExistsError):
                write_new_json(target, {"first": False})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"first": True})


class StateTableTests(unittest.TestCase):
    def test_gridform_core_re_exports_the_single_table(self) -> None:
        from gridform_core import run_lifecycle, study_lifecycle

        self.assertIs(run_lifecycle.TRANSITIONS, states.TRANSITIONS)
        self.assertIs(run_lifecycle.STATES, states.STATES)
        self.assertIs(run_lifecycle.LifecycleError, states.LifecycleError)
        self.assertIs(study_lifecycle.ACTIVE_RUN_STATUSES, states.ACTIVE_STATES)
        for name in ("atomic_status_transition", "cancellation_requested"):
            self.assertTrue(callable(getattr(run_lifecycle, name)))

    def test_failed_never_becomes_cancelled_and_deleting_is_a_sink(self) -> None:
        with self.assertRaises(states.LifecycleError):
            states.check_transition("failed", "cancelled")
        self.assertEqual(states.TRANSITIONS["deleting"], set())
        with self.assertRaises(states.LifecycleError):
            states.check_transition("deleting", "failed")
        states.check_transition("deleting", "failed", repair=True)
        for source in ("queued", "running"):
            states.check_transition(source, "cancelled")
        self.assertEqual(set(states.TRANSITIONS), set(states.STATES))
        for targets in states.TRANSITIONS.values():
            self.assertTrue(targets <= states.STATES)

    def test_classify_marks_legacy_payloads_unknown(self) -> None:
        self.assertEqual(states.classify({"status": "running"}), "running")
        for value in ([], None, {"status": "exploded"}, {"id": "run"}, {"status": 3}):
            self.assertEqual(states.classify(value), states.UNKNOWN)


class StandardLibraryOnlyTests(unittest.TestCase):
    def test_package_imports_only_the_standard_library(self) -> None:
        allowed_local = "backend.lifecycle"
        stdlib = set(sys.stdlib_module_names) | {"__future__"}
        offenders: list[str] = []
        for path in sorted(LIFECYCLE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if path.name == "worker_entry.py":
                # Phase two's deliberate, function-local ``from backend import
                # model_runner`` is the only heavy import, after the lease.
                lazy = [
                    node for function in ast.walk(tree) if isinstance(function, ast.FunctionDef)
                    for node in ast.walk(function)
                    if isinstance(node, ast.ImportFrom) and node.module == "backend"
                ]
                self.assertEqual([[alias.name for alias in node.names] for node in lazy], [["model_runner"]])
                for node in lazy:
                    node.module = allowed_local
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        names = [allowed_local]
                    else:
                        names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if name.startswith(allowed_local):
                        continue
                    if name.split(".")[0] not in stdlib:
                        offenders.append(f"{path.name}: {name}")
        self.assertEqual(offenders, [])

    def test_import_is_fast_and_never_loads_numpy(self) -> None:
        code = (
            "import sys, time, json\n"
            "start = time.perf_counter()\n"
            "import backend.lifecycle.file_locks, backend.lifecycle.atomic_io, backend.lifecycle.states\n"
            "import backend.lifecycle.run_status, backend.lifecycle.worker_lease, backend.lifecycle.python_argv\n"
            "import backend.lifecycle.worker_entry, backend.worker_entry\n"
            "elapsed = time.perf_counter() - start\n"
            "print(json.dumps({'seconds': elapsed, 'numpy': 'numpy' in sys.modules,"
            " 'gridform_core': any(m.startswith('gridform_core') for m in sys.modules)}))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", code], cwd=ROOT, env=_child_environment(),
            capture_output=True, text=True, timeout=60, check=True,
        )
        report = json.loads(completed.stdout)
        self.assertLess(report["seconds"], 0.3)
        self.assertFalse(report["numpy"])
        self.assertFalse(report["gridform_core"])


if __name__ == "__main__":
    unittest.main()
