"""Atomic lifecycle rules for local scientific runs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Mapping


STATES = {
    "queued", "snapshotting", "running", "cancel_requested", "cancelled",
    "failed", "completed", "archived", "deleting",
}
TRANSITIONS = {
    "queued": {"snapshotting", "running", "cancel_requested", "failed"},
    "snapshotting": {"queued", "failed"},
    "running": {"cancel_requested", "failed", "completed"},
    "cancel_requested": {"cancelled", "failed", "completed"},
    "cancelled": {"queued", "archived", "deleting"},
    "failed": {"queued", "archived", "deleting"},
    "completed": {"archived", "deleting"},
    "archived": {"completed", "failed", "cancelled", "deleting"},
    "deleting": set(),
}


class LifecycleError(ValueError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_status_transition(
    status_path: Path,
    target: str,
    *,
    reason_code: str,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if target not in STATES:
        raise LifecycleError(f"Unknown run state {target}")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    source = str(status.get("status") or "")
    if source not in STATES:
        raise LifecycleError(f"Run has unknown current state {source}")
    if target not in TRANSITIONS[source]:
        raise LifecycleError(f"Run cannot transition from {source} to {target}")
    history = list(status.get("lifecycle_history") or [])
    history.append({
        "sequence": len(history) + 1, "from": source, "to": target,
        "reason_code": reason_code, "at": _now(), "details": dict(details or {}),
    })
    status.update({
        "status": target, "updated_at": _now(), "lifecycle_reason_code": reason_code,
        "lifecycle_history": history,
    })
    temporary = status_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(status_path)
    return status


def cancellation_requested(run_root: Path) -> bool:
    request = run_root / "cancel-request.json"
    if not request.is_file():
        return False
    try:
        payload = json.loads(request.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("schema_version") == "value.cancel-request/v1"
