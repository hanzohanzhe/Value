"""Spawn, reap, supervise and reconcile model workers (P0-3 S4, Q4).

Lifecycle of a worker:

1. ``spawn_worker`` writes ``worker.json`` (v2, with a fresh lease nonce)
   *before* the process exists, starts ``python -m backend.worker_entry`` in
   its own session/process group (so stopping the backend's process group
   never kills it: DECISIONS Q4 lets a worker outlive the backend), then
   records its pid and Linux process identity.  Spawning never happens under
   a status lock.
2. A reaper thread per own child blocks in ``proc.wait()`` (no zombies, the
   exit status is kept in ``worker-exit.json``).  If the run is still active
   when its worker has exited, it becomes ``failed`` (or ``cancelled`` when a
   cancellation was requested) with ``GF_WORKER_EXITED``.
3. Every ``interval`` seconds ``tick`` looks only at *orphans*: active runs
   whose worker is not this backend's child (a previous backend spawned it).
   Liveness is the lease lock, never the pid.  A held lease means alive (the
   new backend has taken over supervision); a free lease means the worker is
   gone and the run becomes ``failed``/``cancelled`` with ``GF_WORKER_LOST``.
   Windows needs two free probes at least 5 s apart (asynchronous lock
   release); a worker spawned less than ``SPAWN_GRACE_SECONDS`` ago that is
   still starting is given time to take its lease.
4. ``reconcile_all`` runs once at start-up, synchronously, before the API
   binds: the same judgement for every active run, repair of runs a pre-P0-3
   delete left in ``deleting``, and nothing slow (no hashing, no tree walks).
   Failed-provenance sealing for runs it settles is queued for the background
   sealer thread.

Pre-lease (v1) workers have no lock.  On Linux their ``/proc`` argv decides;
elsewhere they are ``unverifiable`` and only a confirmed manual mark-lost after
a quiet period settles them.

``VALUE_RUN_RECONCILER=observe`` makes the reconciler, the ticks and the reaper
report what they would do without writing anything (rollback switch).
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.lifecycle.atomic_io import atomic_write_json
from backend.lifecycle.file_locks import LOCK_ABSENT, LOCK_FREE, LOCK_HELD
from backend.lifecycle.python_argv import (
    isolated_environment,
    new_pycache_prefix,
    remove_empty_prefix,
    worker_python_argv,
)
from backend.lifecycle.run_status import (
    WRITER_SERVER,
    LeaseHeldError,
    read_status,
    update_status,
)
from backend.lifecycle.states import ACTIVE_STATES, REPAIR_TRANSITIONS, LifecycleError, classify
from backend.lifecycle.worker_lease import (
    EXIT_RECORD,
    EXIT_SCHEMA,
    SPAWN_RECORD,
    SPAWN_SCHEMA_V1,
    SPAWN_SCHEMA_V2,
    lease_state,
    linux_boot_id,
    linux_process_identity,
    new_nonce,
    read_spawn_record,
    v1_worker_matches,
)

TICK_SECONDS = 5.0
SPAWN_GRACE_SECONDS = 30.0
WINDOWS_CONFIRM_SECONDS = 5.0
MARK_LOST_QUIET_SECONDS = 15 * 60
RECONCILER_ENV = "VALUE_RUN_RECONCILER"

LIVENESS_ALIVE = "alive"
LIVENESS_STARTING = "starting"
LIVENESS_LOST = "lost"
LIVENESS_UNVERIFIABLE = "unverifiable"
LIVENESS_NOT_STARTED = "not_started"
LIVENESS_NONE = "not_active"


class WorkerSpawnError(RuntimeError):
    """The worker process could not be started (GF_WORKER_SPAWN_FAILED)."""


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _log(message: str) -> None:
    print(f"VALUE supervisor: {message}", file=sys.stderr, flush=True)


def cancellation_pending(run_dir: Path, status: Mapping[str, Any] | None) -> bool:
    return (run_dir / "cancel-request.json").is_file() or (status or {}).get("status") == "cancel_requested"


def _created_epoch(record: Mapping[str, Any]) -> float | None:
    value = record.get("created_epoch")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _pid_running(pid: Any) -> bool | None:
    """Linux only: is a non-zombie process with this pid running?"""

    if not sys.platform.startswith("linux"):
        return None
    try:
        identity = linux_process_identity(int(pid))
    except (TypeError, ValueError):
        return False
    return identity is not None and identity["state"] != "Z"


def worker_liveness(run_dir: Path, status: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Return (liveness, public worker summary) for presentation; never writes."""

    status = read_status(run_dir) if status is None else status
    spawn = read_spawn_record(run_dir) or {}
    summary: dict[str, Any] = {}
    if spawn:
        summary = {
            "schema_version": spawn.get("schema_version"),
            "pid": spawn.get("pid"),
            "created_at": spawn.get("created_at"),
        }
    if classify(status) not in ACTIVE_STATES:
        return LIVENESS_NONE, summary
    lease = lease_state(run_dir)
    summary["lease"] = lease
    if lease == LOCK_HELD:
        return LIVENESS_ALIVE, summary
    if not spawn:
        return LIVENESS_NOT_STARTED, summary
    if spawn.get("schema_version") == SPAWN_SCHEMA_V1 or lease == LOCK_ABSENT and spawn.get("schema_version") != SPAWN_SCHEMA_V2:
        verdict = v1_worker_matches(spawn, str(run_dir.name))
        if verdict is None:
            return LIVENESS_UNVERIFIABLE, summary
        return (LIVENESS_ALIVE if verdict else LIVENESS_LOST), summary
    created = _created_epoch(spawn)
    if created is not None and time.time() - created < SPAWN_GRACE_SECONDS and _pid_running(spawn.get("pid")) is not False:
        return LIVENESS_STARTING, summary
    return LIVENESS_LOST, summary


def newest_activity_epoch(run_dir: Path, *, limit: int = 20000) -> float:
    """Latest mtime among the run's files (bounded walk, for the quiet gate)."""

    newest = 0.0
    seen = 0
    stack = [run_dir]
    while stack and seen < limit:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                else:
                    newest = max(newest, entry.stat(follow_symlinks=False).st_mtime)
            except OSError:
                continue
    return newest


@dataclass
class _Child:
    process: subprocess.Popen
    prefix: Path
    run_dir: Path
    thread: threading.Thread | None = None


@dataclass
class ReconcileReport:
    observed_only: bool
    settled: list[dict[str, Any]] = field(default_factory=list)
    alive: list[str] = field(default_factory=list)
    unverifiable: list[str] = field(default_factory=list)
    repaired: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "value.run-reconcile-report/v1",
            "observed_only": self.observed_only,
            "settled": self.settled, "alive": self.alive,
            "unverifiable": self.unverifiable, "repaired": self.repaired,
            **self.extra,
        }


class RunSupervisor:
    def __init__(
        self,
        runs_root: Path,
        *,
        run_lock: Callable[[str], Any],
        interval: float = TICK_SECONDS,
        reconciler_mode: str | None = None,
        windows: bool | None = None,
        sealer: Callable[[Path, Mapping[str, Any]], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.runs_root = Path(runs_root)
        self.run_lock = run_lock
        self.interval = float(interval)
        mode = os.environ.get(RECONCILER_ENV, "") if reconciler_mode is None else reconciler_mode
        self.observe_only = mode.strip().lower() == "observe"
        self.windows = (os.name == "nt") if windows is None else bool(windows)
        self.clock = clock
        self._sealer = sealer
        self._children: dict[str, _Child] = {}
        self._children_lock = threading.Lock()
        self._free_seen: dict[str, float] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._seal_queue: "queue.Queue[tuple[Path, dict[str, Any]] | None]" = queue.Queue()
        self.observations: list[dict[str, Any]] = []

    # -- spawning and reaping -------------------------------------------------
    def owns(self, run_id: str) -> bool:
        with self._children_lock:
            return run_id in self._children

    def spawn_worker(
        self,
        *,
        run_dir: Path,
        run_id: str,
        project_id: str,
        mode: str,
        python: str,
        cwd: Path,
        log_mode: str = "w",
        environment: Mapping[str, str] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start one detached worker for a queued run; return its spawn record."""

        run_dir = Path(run_dir)
        nonce = new_nonce()
        prefix = new_pycache_prefix()
        argv = [
            *worker_python_argv(python, prefix, match_parent_user_site=True),
            "--run-dir", str(run_dir), "--lease-nonce", nonce,
            "--project", project_id, "--run", run_id, "--mode", mode,
        ]
        record: dict[str, Any] = {
            "schema_version": SPAWN_SCHEMA_V2,
            "run_id": run_id,
            "lease_nonce": nonce,
            "created_at": now(),
            "created_epoch": time.time(),
            "executable": python,
            "argv": argv,
            "ownership": "detached_worker_with_lease",
            "state": "spawning",
            **dict(extra or {}),
        }
        atomic_write_json(run_dir / SPAWN_RECORD, record)
        env = isolated_environment(dict(environment if environment is not None else os.environ), prefix)
        env["VALUE_DATA_HOME"] = str(run_dir.parent.parent)
        options: dict[str, Any]
        if os.name == "nt":  # pragma: no cover - Windows only
            options = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                       | getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        else:
            options = {"start_new_session": True}
        try:
            with (run_dir / "model.log").open(log_mode, encoding="utf-8") as log:
                process = subprocess.Popen(
                    argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=env,
                    close_fds=True, **options,
                )
        except OSError as exc:
            remove_empty_prefix(prefix)
            raise WorkerSpawnError(f"The model worker could not be started: {exc}") from exc
        identity = linux_process_identity(process.pid) if sys.platform.startswith("linux") else None
        record.update({
            "pid": process.pid,
            "process_group": process.pid if os.name != "nt" else None,
            "start_time": identity["start_time"] if identity else None,
            "boot_id": linux_boot_id(),
            "state": "spawned",
        })
        atomic_write_json(run_dir / SPAWN_RECORD, record)
        child = _Child(process=process, prefix=prefix, run_dir=run_dir)
        with self._children_lock:
            self._children[run_id] = child
        child.thread = threading.Thread(
            target=self._reap, args=(run_id, child), name=f"value-reaper-{run_id[-8:]}", daemon=True,
        )
        child.thread.start()
        return record

    def _reap(self, run_id: str, child: _Child) -> None:
        returncode = child.process.wait()
        remove_empty_prefix(child.prefix)
        try:
            atomic_write_json(child.run_dir / EXIT_RECORD, {
                "schema_version": EXIT_SCHEMA,
                "run_id": run_id,
                "pid": child.process.pid,
                "returncode": returncode,
                "signal": -returncode if returncode < 0 else None,
                "exited_at": now(),
            })
        except OSError as exc:  # the run may have been moved meanwhile
            _log(f"could not record the exit of {run_id}: {exc}")
        try:
            with self.run_lock(run_id):
                self.settle(child.run_dir, "GF_WORKER_EXITED", {
                    "returncode": returncode,
                    "signal": -returncode if returncode < 0 else None,
                })
        finally:
            with self._children_lock:
                if self._children.get(run_id) is child:
                    del self._children[run_id]

    # -- settling ---------------------------------------------------------------
    def settle(self, run_dir: Path, reason_code: str, details: Mapping[str, Any]) -> dict[str, Any] | None:
        """Finish an active run whose worker is gone; ``None`` when not needed."""

        status = read_status(run_dir)
        state = classify(status)
        if state not in ACTIVE_STATES:
            return None
        target = "cancelled" if cancellation_pending(run_dir, status) else "failed"
        observation = {"run_id": run_dir.name, "from": state, "to": target,
                       "reason_code": reason_code, "details": dict(details)}
        if self.observe_only:
            self.observations.append(observation)
            _log(f"observe: would move {run_dir.name} {state} -> {target} ({reason_code})")
            return None
        message = {
            "GF_WORKER_EXITED": "The model worker exited before recording a final state.",
            "GF_WORKER_LOST": "The model worker is no longer running.",
            "GF_WORKER_MARKED_LOST": "The model worker was marked lost after confirmation.",
        }.get(reason_code, "The model worker stopped.")

        def apply(current: dict[str, Any]) -> None:
            current.update({
                "execution_status": target,
                "current_stage": "Model worker stopped" if target == "failed" else "Cancelled; the model worker stopped",
                "finished_at": now(),
                "worker_outcome": {"reason_code": reason_code, **dict(details)},
            })
            if target == "failed":
                current.update({"error": message, "error_code": reason_code, "error_category": "runtime"})

        try:
            updated = update_status(
                run_dir, mutate=apply, transition=target, reason_code=reason_code,
                details=details, writer=WRITER_SERVER,
            )
        except LeaseHeldError:
            _log(f"{run_dir.name}: a worker took the lease meanwhile; left running")
            return None
        except (LifecycleError, OSError) as exc:
            _log(f"{run_dir.name}: could not record {reason_code}: {exc}")
            return None
        self._free_seen.pop(run_dir.name, None)
        if target == "failed" and not (run_dir / "provenance.json").is_file():
            self._seal_queue.put((run_dir, dict(updated)))
        return updated

    # -- orphan judgement -------------------------------------------------------
    def judge(self, run_dir: Path, *, startup: bool, report: ReconcileReport | None = None) -> str:
        status = read_status(run_dir)
        run_id = run_dir.name
        liveness, _summary = worker_liveness(run_dir, status)
        if liveness in {LIVENESS_ALIVE, LIVENESS_STARTING}:
            self._free_seen.pop(run_id, None)
            if report is not None:
                report.alive.append(run_id)
            return liveness
        if liveness == LIVENESS_UNVERIFIABLE:
            if report is not None:
                report.unverifiable.append(run_id)
            return liveness
        if self.windows and not startup:
            first = self._free_seen.setdefault(run_id, self.clock())
            if self.clock() - first < WINDOWS_CONFIRM_SECONDS:
                return LIVENESS_STARTING
        details = {"liveness": liveness, "lease": lease_state(run_dir), "at_startup": startup}
        settled = self.settle(run_dir, "GF_WORKER_LOST", details)
        if report is not None and (settled is not None or self.observe_only):
            report.settled.append({"run_id": run_id, "reason_code": "GF_WORKER_LOST", **details})
        return LIVENESS_LOST

    def tick(self) -> None:
        if not self.runs_root.is_dir():
            return
        for run_dir in sorted(path for path in self.runs_root.iterdir() if path.is_dir()):
            run_id = run_dir.name
            if self.owns(run_id):
                continue
            if classify(read_status(run_dir)) not in ACTIVE_STATES:
                self._free_seen.pop(run_id, None)
                continue
            lock = self.run_lock(run_id)
            if not lock.acquire(blocking=False):
                continue  # a request of this backend is starting or changing it
            try:
                if not self.owns(run_id):
                    self.judge(run_dir, startup=False)
            finally:
                lock.release()

    def repair_interrupted_delete(self, run_dir: Path, report: ReconcileReport) -> None:
        status = read_status(run_dir) or {}
        history = status.get("lifecycle_history") if isinstance(status.get("lifecycle_history"), list) else []
        previous = next((entry.get("from") for entry in reversed(history)
                         if isinstance(entry, Mapping) and entry.get("to") == "deleting"), None)
        target = previous if previous in REPAIR_TRANSITIONS["deleting"] else "failed"
        if self.observe_only:
            self.observations.append({"run_id": run_dir.name, "from": "deleting", "to": target})
            report.repaired.append({"run_id": run_dir.name, "to": target, "observed_only": True})
            return
        update_status(
            run_dir, transition=target, reason_code="GF_RUN_DELETE_INTERRUPTED_REPAIRED",
            details={"previous_state": previous}, writer=WRITER_SERVER, repair=True,
        )
        report.repaired.append({"run_id": run_dir.name, "to": target})

    def reconcile_all(self, extra_steps: list[Callable[[ReconcileReport], None]] | None = None) -> ReconcileReport:
        """Synchronous start-up reconciliation (call before the API binds)."""

        report = ReconcileReport(observed_only=self.observe_only)
        if self.runs_root.is_dir():
            for run_dir in sorted(path for path in self.runs_root.iterdir() if path.is_dir()):
                state = classify(read_status(run_dir))
                try:
                    if state == "deleting":
                        self.repair_interrupted_delete(run_dir, report)
                    elif state in ACTIVE_STATES:
                        self.judge(run_dir, startup=True, report=report)
                except (LifecycleError, OSError) as exc:
                    _log(f"could not reconcile {run_dir.name}: {exc}")
        for step in extra_steps or []:
            step(report)
        return report

    # -- manual mark-lost -------------------------------------------------------
    def mark_lost(self, run_dir: Path, *, confirm_run_id: str, quiet_seconds: float = MARK_LOST_QUIET_SECONDS) -> tuple[int, dict[str, Any]]:
        """Settle a run whose worker cannot be verified, after two gates.

        Returns (http_status, payload).  The confirmation gate needs the exact
        run id; the quiet gate needs no file in the run to have changed for
        ``quiet_seconds``.  A live lease or a verified live v1 worker refuses.
        """

        run_id = run_dir.name
        status = read_status(run_dir)
        if classify(status) not in ACTIVE_STATES:
            return 409, {"error": "Only an active run can be marked lost", "error_code": "GF_RUN_NOT_ACTIVE"}
        liveness, summary = worker_liveness(run_dir, status)
        if liveness in {LIVENESS_ALIVE, LIVENESS_STARTING}:
            return 409, {"error": "The model worker is alive", "error_code": "GF_WORKER_ALIVE",
                         "worker_liveness": liveness}
        if confirm_run_id != run_id:
            return 409, {"error": "Exact run ID confirmation is required", "error_code": "GF_MARK_LOST_CONFIRMATION_REQUIRED",
                         "run_id": run_id, "worker_liveness": liveness}
        quiet_for = time.time() - newest_activity_epoch(run_dir)
        if quiet_for < quiet_seconds:
            return 409, {"error": "The run changed recently; wait for the quiet period", "error_code": "GF_MARK_LOST_NOT_QUIET",
                         "quiet_seconds": round(quiet_for, 1), "required_quiet_seconds": quiet_seconds}
        updated = self.settle(run_dir, "GF_WORKER_MARKED_LOST", {"worker_liveness": liveness, "worker": summary})
        if updated is None:
            return 409, {"error": "The run could not be marked lost", "error_code": "GF_MARK_LOST_REFUSED"}
        return 200, {"ok": True, "run": updated}

    # -- background threads -----------------------------------------------------
    def _tick_loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - the supervisor must survive one bad run
                _log(f"tick failed: {type(exc).__name__}: {exc}")

    def _seal_loop(self) -> None:
        while True:
            item = self._seal_queue.get()
            if item is None:
                return
            run_dir, status = item
            if self._sealer is None:
                continue
            try:
                self._sealer(run_dir, status)
            except Exception as exc:  # noqa: BLE001 - sealing is best effort, recorded by the sealer
                _log(f"could not seal failed provenance for {run_dir.name}: {exc}")

    def start(self) -> None:
        for target, name in ((self._tick_loop, "value-run-supervisor"), (self._seal_loop, "value-run-sealer")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        self._seal_queue.put(None)

    def drain_seals(self) -> None:
        """Seal queued runs synchronously (tests and shutdown)."""

        while True:
            try:
                item = self._seal_queue.get_nowait()
            except queue.Empty:
                return
            if item is None:
                self._seal_queue.put(None)
                return
            if self._sealer is not None:
                try:
                    self._sealer(*item)
                except Exception as exc:  # noqa: BLE001
                    _log(f"could not seal failed provenance for {item[0].name}: {exc}")

    def background_runs(self) -> list[str]:
        """Active runs whose worker holds its lease (they outlive the backend)."""

        if not self.runs_root.is_dir():
            return []
        return [
            path.name for path in sorted(self.runs_root.iterdir())
            if path.is_dir() and classify(read_status(path)) in ACTIVE_STATES
            and lease_state(path) == LOCK_HELD
        ]


__all__ = [
    "LIVENESS_ALIVE", "LIVENESS_LOST", "LIVENESS_NONE", "LIVENESS_NOT_STARTED",
    "LIVENESS_STARTING", "LIVENESS_UNVERIFIABLE", "LOCK_FREE", "MARK_LOST_QUIET_SECONDS",
    "ReconcileReport", "RunSupervisor", "WorkerSpawnError", "newest_activity_epoch", "worker_liveness",
]
