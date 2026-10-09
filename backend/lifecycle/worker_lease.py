"""Worker liveness: a lease held as an exclusive lock on ``<run>/worker.lock``.

The worker takes the lock before importing anything heavy and keeps it until
the process ends; the operating system releases it on any exit, including
SIGKILL and OOM.  Liveness is therefore "can the lock be taken?", never "does
a process with the recorded pid exist?" (pids are reused, and a recorded pid
can name an unrelated process in another namespace).

Files in the run root (never sealed, exported or downloadable):

``worker.lock``        the lease lock itself
``worker.json``        spawn record written by the server (v2: nonce first,
                        pid and process identity after spawn)
``worker-lease.json``  the worker's own record once it holds the lease
``worker-exit.json``   the server's record of its own child's exit status
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .file_locks import FileLock, LockTimeout, probe_lock
from .run_status import WORKER_LOCK

SPAWN_RECORD = "worker.json"
LEASE_RECORD = "worker-lease.json"
EXIT_RECORD = "worker-exit.json"
SPAWN_SCHEMA_V1 = "value.worker-identity/v1"
SPAWN_SCHEMA_V2 = "value.worker-identity/v2"
LEASE_SCHEMA = "value.worker-lease/v1"
EXIT_SCHEMA = "value.worker-exit/v1"
LEASE_ACQUIRE_SECONDS = 2.0

# Exit codes of the worker entry point.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_SECOND_WORKER = 75  # EX_TEMPFAIL: another worker already holds the lease

LIVENESS_ALIVE = "alive"
LIVENESS_GONE = "gone"
LIVENESS_NOT_STARTED = "not_started"


class WorkerTerminated(BaseException):
    """A termination signal reached the worker (SIGTERM, SIGHUP, SIGBREAK).

    A ``BaseException`` so that model code's ``except Exception`` blocks do not
    swallow it; the worker records ``GF_WORKER_TERMINATED`` and exits 128+n.
    """

    def __init__(self, signum: int) -> None:
        super().__init__(f"The model worker received signal {signum}")
        self.signum = int(signum)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_nonce() -> str:
    return secrets.token_hex(16)


def lease_path(run_dir: os.PathLike[str] | str) -> Path:
    return Path(run_dir) / WORKER_LOCK


def acquire_lease(run_dir: os.PathLike[str] | str, *, timeout: float = LEASE_ACQUIRE_SECONDS) -> FileLock | None:
    """Take the lease; ``None`` when another live worker holds it."""

    try:
        return FileLock(lease_path(run_dir)).acquire(timeout)
    except LockTimeout:
        return None


def lease_state(run_dir: os.PathLike[str] | str) -> str:
    """``held`` (a live worker), ``free`` (no live holder) or ``absent``."""

    return probe_lock(lease_path(run_dir))


def read_json_object(path: Path) -> dict[str, Any] | None:
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def read_spawn_record(run_dir: os.PathLike[str] | str) -> dict[str, Any] | None:
    return read_json_object(Path(run_dir) / SPAWN_RECORD)


def write_lease_record(run_dir: Path, *, run_id: str, nonce: str, startup_seconds: float) -> None:
    atomic_write_json(run_dir / LEASE_RECORD, {
        "schema_version": LEASE_SCHEMA,
        "run_id": run_id,
        "lease_nonce": nonce,
        "pid": os.getpid(),
        "acquired_at": now(),
        "startup_seconds": round(startup_seconds, 4),
        "heavy_modules_loaded": "numpy" in sys.modules,
        "python": sys.version.split()[0],
    })


def linux_boot_id() -> str | None:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError:
        return None


def linux_process_identity(pid: int) -> dict[str, Any] | None:
    """Return start time, state and argv of a Linux process, or ``None``."""

    directory = Path("/proc") / str(int(pid))
    try:
        fields = (directory / "stat").read_text(encoding="ascii", errors="replace").rsplit(")", 1)[1].split()
        argv = [
            part.decode("utf-8", errors="replace")
            for part in (directory / "cmdline").read_bytes().rstrip(b"\0").split(b"\0")
        ]
    except (OSError, IndexError):
        return None
    if len(fields) < 20:
        return None
    return {"state": fields[0], "start_time": fields[19], "argv": argv}


def v1_worker_matches(record: dict[str, Any], run_id: str) -> bool | None:
    """Judge a pre-lease (v1) worker on Linux by its /proc argv.

    ``True`` when a non-zombie process with the recorded pid runs this run's
    ``backend.model_runner``; ``False`` when no such process exists; ``None``
    when that cannot be verified on this platform.
    """

    if not sys.platform.startswith("linux"):
        return None
    try:
        pid = int(record.get("pid"))
    except (TypeError, ValueError):
        return False
    identity = linux_process_identity(pid)
    if identity is None or identity["state"] == "Z":
        return False
    argv = identity["argv"]
    return "backend.model_runner" in argv and run_id in argv
