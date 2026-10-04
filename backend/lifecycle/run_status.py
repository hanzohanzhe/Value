"""The only writer API for a run's ``status.json`` (standard library only).

Every write happens under the run's own ``status.lock``: the file is re-read
inside the lock, changed field by field and atomically replaced with a unique
temporary (P0_CONVENTIONS section 7).  Nothing rewrites the whole file from a
stale in-memory copy any more, so fields written by another party (the
application's ``subannual_recovery*`` evidence, the server's quota record,
other packages' additions) survive every later write (P7-08).

Writers by phase (single writer per phase, P0-3 plan point 3):

* before the worker is spawned, and after the worker's lease is known to be
  released, the server writes (``writer=WRITER_SERVER``; refused with
  :class:`LeaseHeldError` while a live worker holds ``worker.lock``);
* while the worker holds its lease only the worker, ``model_runner`` and the
  application write (``writer=WRITER_WORKER``).

A worker write that arrives after the run has left the active states is *late*:
the status and every sealed artifact stay untouched and the attempt is recorded
in a root-level ``late-worker-*.json`` (never under ``diagnostics/``, which is
part of the sealed evidence).  :class:`LateWriteRejected` is then raised so the
worker stops.

A missing, unreadable, non-object or unrecognised status is ``unknown``.  Only
the ``record_*`` writers may replace it (``legacy_replace=True``); an
unreadable file is preserved as ``status.invalid-<time>.json`` first.

``mutate`` callbacks change fields in place and must not change ``status`` or
``lifecycle_history``; state changes go through ``transition`` so that every
change appends one entry with a consecutive ``sequence`` to
``lifecycle_history``.  The check is an explicit ``raise`` and holds under
``python -O``.
"""

from __future__ import annotations

import copy
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .atomic_io import TERMINAL_REPLACE_RETRY_SECONDS, atomic_write_bytes, atomic_write_json
from .file_locks import LOCK_HELD, hold_lock, probe_lock
from .states import (
    ACTIVE_STATES,
    STATES,
    TERMINAL_STATES,
    UNKNOWN,
    LifecycleError,
    check_transition,
    classify,
)

STATUS_FILE = "status.json"
STATUS_LOCK = "status.lock"
WORKER_LOCK = "worker.lock"
STATUS_LOCK_TIMEOUT_SECONDS = 10.0
LATE_WRITE_SCHEMA = "value.late-worker-write/v1"

WRITER_SERVER = "server"
WRITER_WORKER = "worker"
_WRITERS = {None, WRITER_SERVER, WRITER_WORKER}

# Root-level lifecycle files that are never sealed, exported or downloadable.
LIFECYCLE_ROOT_FILES = (
    STATUS_LOCK, WORKER_LOCK, "worker-lease.json", "worker-exit.json",
)
LIFECYCLE_ROOT_PREFIXES = ("late-worker-", "status.invalid-")


class StatusExistsError(LifecycleError):
    """``create_status`` found an existing ``status.json``."""


class LegacyStatusError(LifecycleError):
    """The status is ``unknown`` and the caller may not replace it."""


class LeaseHeldError(LifecycleError):
    """A server-side write was refused because a live worker holds the lease."""


class LateWriteRejected(LifecycleError):
    """A worker wrote after the run left the active states; nothing changed."""

    def __init__(self, message: str, *, record: Path | None, observed: str) -> None:
        super().__init__(message)
        self.record = record
        self.observed = observed


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def status_path(run_dir: os.PathLike[str] | str) -> Path:
    return Path(run_dir) / STATUS_FILE


def is_lifecycle_root_file(name: str) -> bool:
    return name in LIFECYCLE_ROOT_FILES or name.startswith(LIFECYCLE_ROOT_PREFIXES) or name.endswith(".lock")


def _load(path: Path) -> tuple[str, Any]:
    """Return (kind, value): kind is missing, invalid, not_object or object."""

    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return "missing", None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "invalid", raw
    if not isinstance(value, dict):
        return "not_object", raw
    return "object", value


def read_status(run_dir: os.PathLike[str] | str) -> dict[str, Any] | None:
    """Read without locking; ``None`` when missing, unreadable or not an object."""

    kind, value = _load(status_path(run_dir))
    return value if kind == "object" else None


def status_state(run_dir: os.PathLike[str] | str) -> str:
    return classify(read_status(run_dir))


def _unique_suffix() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}-{secrets.token_hex(3)}"


def _preserve_invalid(run_dir: Path, raw: bytes) -> Path:
    path = run_dir / f"status.invalid-{_unique_suffix()}.json"
    atomic_write_bytes(path, raw)
    return path


def _record_late_write(
    run_dir: Path,
    *,
    observed: str,
    attempted_transition: str | None,
    reason_code: str | None,
    fields: list[str],
    details: Mapping[str, object] | None,
) -> Path | None:
    record = {
        "schema_version": LATE_WRITE_SCHEMA,
        "recorded_at": now(),
        "pid": os.getpid(),
        "observed_status": observed,
        "attempted_transition": attempted_transition,
        "reason_code": reason_code,
        "attempted_fields": sorted(fields),
        "details": dict(details or {}),
    }
    path = run_dir / f"late-worker-{_unique_suffix()}.json"
    try:
        atomic_write_json(path, record)
    except OSError:
        return None  # the run directory itself has gone (moved to the trash)
    return path


def _history(status: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = status.get("lifecycle_history")
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _append_history(
    status: dict[str, Any],
    *,
    source: str | None,
    target: str,
    reason_code: str,
    details: Mapping[str, object] | None,
) -> None:
    history = _history(status)
    history.append({
        "sequence": len(history) + 1,
        "from": source,
        "to": target,
        "reason_code": reason_code,
        "at": now(),
        "details": dict(details or {}),
    })
    status["lifecycle_history"] = history
    status["status"] = target
    status["lifecycle_reason_code"] = reason_code


def assert_history_chain(status: Mapping[str, Any]) -> None:
    """Raise LifecycleError unless lifecycle_history is a consecutive chain.

    Each entry has ``sequence == index + 1`` and starts where the previous one
    ended (``unknown`` restarts a chain after a legacy replacement); the last
    entry ends at the current status.
    """

    history = status.get("lifecycle_history")
    if history is None:
        return
    if not isinstance(history, list):
        raise LifecycleError("lifecycle_history is not a list")
    previous: str | None = None
    for index, entry in enumerate(history):
        if not isinstance(entry, Mapping) or entry.get("sequence") != index + 1:
            raise LifecycleError(f"lifecycle_history entry {index + 1} has a broken sequence")
        source = entry.get("from")
        if index and source not in {previous, UNKNOWN}:
            raise LifecycleError(f"lifecycle_history entry {index + 1} does not continue the chain")
        previous = entry.get("to")
    if history and previous != status.get("status"):
        raise LifecycleError("lifecycle_history does not end at the current status")


def _check_writer(writer: str | None) -> None:
    if writer not in _WRITERS:
        raise LifecycleError(f"Unknown status writer {writer!r}")


def create_status(run_dir: os.PathLike[str] | str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create ``status.json`` for a new run; refuse when it already exists."""

    directory = Path(run_dir)
    initial = copy.deepcopy(dict(payload))
    state = initial.get("status")
    if state not in STATES:
        raise LifecycleError(f"A new run status needs a known state, not {state!r}")
    if "lifecycle_history" in initial:
        raise LifecycleError("A new run status starts its own lifecycle_history")
    with hold_lock(directory / STATUS_LOCK, timeout=STATUS_LOCK_TIMEOUT_SECONDS):
        if status_path(directory).exists():
            raise StatusExistsError(f"Run status already exists: {directory.name}")
        initial.pop("status")
        _append_history(initial, source=None, target=str(state), reason_code="GF_RUN_CREATED", details=None)
        initial.setdefault("updated_at", now())
        atomic_write_json(status_path(directory), initial)
    return initial


def update_status(
    run_dir: os.PathLike[str] | str,
    *,
    mutate: Callable[[dict[str, Any]], None] | None = None,
    transition: str | None = None,
    reason_code: str | None = None,
    details: Mapping[str, object] | None = None,
    writer: str | None = None,
    legacy_replace: bool = False,
    merge_unknown: bool = False,
    repair: bool = False,
) -> dict[str, Any]:
    """Read, change and atomically replace ``status.json`` under ``status.lock``.

    ``legacy_replace`` lets a ``record_*`` writer replace an ``unknown`` status
    (it must then pass ``transition``).  ``merge_unknown`` keeps the
    application's historical behaviour for its recovery evidence: fields are
    merged into an object whose state is unrecognised, or into a new object
    when ``status.json`` is missing (the run directory itself must exist),
    without any transition.  ``repair`` uses the reconciler-only repair edges.
    """

    _check_writer(writer)
    if transition is not None and not reason_code:
        raise LifecycleError("A status transition needs a reason_code")
    directory = Path(run_dir)
    path = status_path(directory)
    with hold_lock(directory / STATUS_LOCK, timeout=STATUS_LOCK_TIMEOUT_SECONDS):
        kind, loaded = _load(path)
        source = classify(loaded) if kind == "object" else UNKNOWN
        if source == UNKNOWN:
            merge_ok = merge_unknown and kind in {"object", "missing"} and transition is None
            if not (legacy_replace or merge_ok):
                raise LegacyStatusError(
                    f"Run status of {directory.name} is missing or unrecognised ({kind})"
                )
            if legacy_replace and transition is None:
                raise LifecycleError("Replacing a legacy status requires a transition")
            if kind in {"invalid", "not_object"}:
                _preserve_invalid(directory, loaded)
            status: dict[str, Any] = dict(loaded) if kind == "object" else {}
        else:
            status = loaded
        if writer == WRITER_WORKER and source != UNKNOWN and source not in ACTIVE_STATES:
            fields: list[str] = []
            if mutate is not None:
                probe = copy.deepcopy(status)
                try:
                    mutate(probe)
                except Exception:  # noqa: BLE001 - only used to name attempted fields
                    probe = status
                fields = [key for key in probe if probe.get(key) != status.get(key)]
            record = _record_late_write(
                directory, observed=source, attempted_transition=transition,
                reason_code=reason_code, fields=fields, details=details,
            )
            raise LateWriteRejected(
                f"Late worker write ignored: run {directory.name} is already {source}",
                record=record, observed=source,
            )
        if writer == WRITER_SERVER and source in ACTIVE_STATES and probe_lock(directory / WORKER_LOCK) == LOCK_HELD:
            raise LeaseHeldError(f"The worker of run {directory.name} still holds its lease")
        if mutate is not None:
            before_state = status.get("status")
            before_history = copy.deepcopy(status.get("lifecycle_history"))
            mutate(status)
            if status.get("status") != before_state:
                raise LifecycleError("A status mutate callback may not change 'status'; use transition")
            if status.get("lifecycle_history") != before_history:
                raise LifecycleError("A status mutate callback may not change 'lifecycle_history'")
        if transition is not None:
            if source != UNKNOWN:
                check_transition(source, transition, repair=repair)
            elif transition not in STATES:
                raise LifecycleError(f"Unknown run state {transition}")
            _append_history(
                status, source=source if source != UNKNOWN or kind != "missing" else None,
                target=transition, reason_code=str(reason_code), details=details,
            )
        status["updated_at"] = now()
        retry = TERMINAL_REPLACE_RETRY_SECONDS if status.get("status") in TERMINAL_STATES else 0.0
        atomic_write_json(path, status, replace_retry_seconds=retry)
    return status


def guard_worker_write(
    run_dir: os.PathLike[str] | str,
    *,
    attempted_transition: str,
    reason_code: str,
    details: Mapping[str, object] | None = None,
) -> str:
    """First phase of a ``record_*`` writer: refuse a late write before any
    diagnostic or provenance artifact is touched.

    Returns the observed load kind (``object``, ``missing``, ``invalid`` or
    ``not_object``) so the writer can explain a legacy replacement; raises
    :class:`LateWriteRejected` (after recording it) when the run is no longer
    active.
    """

    directory = Path(run_dir)
    with hold_lock(directory / STATUS_LOCK, timeout=STATUS_LOCK_TIMEOUT_SECONDS):
        kind, loaded = _load(status_path(directory))
        source = classify(loaded) if kind == "object" else UNKNOWN
        if source != UNKNOWN and source not in ACTIVE_STATES:
            record = _record_late_write(
                directory, observed=source, attempted_transition=attempted_transition,
                reason_code=reason_code, fields=[], details=details,
            )
            raise LateWriteRejected(
                f"Late worker write ignored: run {directory.name} is already {source}",
                record=record, observed=source,
            )
    return kind


def record_light_failure(
    run_dir: os.PathLike[str] | str,
    *,
    run_id: str,
    project_id: str | None,
    mode: str | None,
    error_code: str,
    message: str,
    exception: BaseException | None = None,
    traceback_text: str | None = None,
    details: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Record a worker failure without importing the scientific stack.

    Used by the light worker entry for failures before ``model_runner`` could
    be imported (``GF_WORKER_IMPORT_FAILED``) and for termination signals.  No
    provenance is sealed here; the status records that it is missing.
    """

    directory = Path(run_dir)
    kind = guard_worker_write(
        directory, attempted_transition="failed", reason_code=error_code, details=details,
    )
    diagnostics = directory / "diagnostics"
    diagnostics.mkdir(exist_ok=True)
    atomic_write_json(diagnostics / "error.json", {
        "schema_version": "value.run-diagnostic/v1",
        "run_id": run_id,
        "error_code": error_code,
        "category": "runtime",
        "exception_type": type(exception).__name__ if exception is not None else None,
        "exception_message": str(exception) if exception is not None else message,
        "traceback": traceback_text or "",
        "recorded_at": now(),
    })

    def mutate(status: dict[str, Any]) -> None:
        status.update({
            "id": run_id,
            "execution_status": "failed",
            "current_stage": "Run failed",
            "error": message,
            "error_code": error_code,
            "error_category": "runtime",
            "diagnostic_artifact": "diagnostics/error.json",
            "finished_at": now(),
        })
        if project_id is not None:
            status["project_id"] = project_id
        if mode is not None:
            status["mode"] = mode
        status.pop("provenance_artifact", None)
        if kind in {"invalid", "not_object"}:
            warnings = status.get("warnings") if isinstance(status.get("warnings"), list) else []
            status["warnings"] = [*warnings, {
                "schema_version": "value.warning/v1", "code": "GF_STATUS_READ_WARNING",
                "category": "artifact", "severity": "warning",
                "message": "The previous public status could not be read; a new failure status was created.",
            }]

    return update_status(
        directory, mutate=mutate, transition="failed", reason_code=error_code,
        details=details, writer=WRITER_WORKER, legacy_replace=True,
    )
