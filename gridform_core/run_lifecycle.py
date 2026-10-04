"""Atomic lifecycle rules for local scientific runs.

The state table lives in :mod:`backend.lifecycle.states` (standard library
only, importable by the light worker entry point); this module re-exports it
under its historical names.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Mapping

from backend.lifecycle.atomic_io import atomic_write_json
from backend.lifecycle.file_locks import hold_lock
from backend.lifecycle.states import (  # noqa: F401 - public re-exports
    ACTIVE_STATES,
    LifecycleError,
    STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    check_transition,
)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_status_transition(
    status_path: Path,
    target: str,
    *,
    reason_code: str,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    status_path = Path(status_path)
    with hold_lock(status_path.with_name("status.lock"), timeout=10.0):
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(status, dict):
            raise LifecycleError("Run status is not a JSON object")
        source = str(status.get("status") or "")
        check_transition(source, target)
        history = list(status.get("lifecycle_history") or [])
        history.append({
            "sequence": len(history) + 1, "from": source, "to": target,
            "reason_code": reason_code, "at": _now(), "details": dict(details or {}),
        })
        status.update({
            "status": target, "updated_at": _now(), "lifecycle_reason_code": reason_code,
            "lifecycle_history": history,
        })
        atomic_write_json(status_path, status)
    return status


def cancellation_requested(run_root: Path) -> bool:
    request = run_root / "cancel-request.json"
    if not request.is_file():
        return False
    try:
        payload = json.loads(request.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("schema_version") == "value.cancel-request/v1"
