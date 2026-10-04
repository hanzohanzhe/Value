"""Atomic lifecycle rules for local scientific runs.

The state table lives in :mod:`backend.lifecycle.states` (standard library
only, importable by the light worker entry point); this module re-exports it
under its historical names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from backend.lifecycle.run_status import update_status
from backend.lifecycle.states import (  # noqa: F401 - public re-exports
    ACTIVE_STATES,
    LifecycleError,
    STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    check_transition,
)


def atomic_status_transition(
    status_path: Path,
    target: str,
    *,
    reason_code: str,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Historical name for one locked, merged state transition (see run_status)."""

    return update_status(
        Path(status_path).parent, transition=target, reason_code=reason_code, details=details,
    )


def cancellation_requested(run_root: Path) -> bool:
    request = run_root / "cancel-request.json"
    if not request.is_file():
        return False
    try:
        payload = json.loads(request.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("schema_version") == "value.cancel-request/v1"
