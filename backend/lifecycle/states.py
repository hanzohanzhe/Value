"""The run state table: the single source of truth for every run status.

``gridform_core.run_lifecycle`` and ``gridform_core.study_lifecycle`` re-export
these names; nothing else defines run states.

Changes from the 0.6.0a2 table (P0-3, F5-02/F5-03/F5-12):

* ``queued -> cancelled`` and ``running -> cancelled``: cancellation is now a
  request file (``cancel-request.json``) read by the worker; the worker records
  ``cancelled`` directly from the state it was in.  ``cancel_requested`` stays
  a valid persisted state so historical runs remain readable and finishable.
* ``snapshotting -> cancelled`` for a run cancelled before its worker started.
* ``failed -> cancelled`` remains forbidden (a failure is never rewritten as a
  user cancellation).
* ``deleting`` still has no ordinary exit.  A historical run left in
  ``deleting`` by an interrupted move is repaired only by the startup
  reconciler through :data:`REPAIR_TRANSITIONS`.
* ``unknown`` is not a state: it names a missing, unreadable or unrecognised
  ``status.json``.  Only the ``record_*`` writers may replace it.
"""

from __future__ import annotations


STATES = frozenset({
    "queued", "snapshotting", "running", "cancel_requested", "cancelled",
    "failed", "completed", "archived", "deleting",
})
UNKNOWN = "unknown"

ACTIVE_STATES = frozenset({"queued", "snapshotting", "running", "cancel_requested"})
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
DELETABLE_STATES = frozenset({"completed", "failed", "cancelled", "archived"})

TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"snapshotting", "running", "cancel_requested", "cancelled", "failed"}),
    "snapshotting": frozenset({"queued", "cancelled", "failed"}),
    "running": frozenset({"cancel_requested", "cancelled", "failed", "completed"}),
    "cancel_requested": frozenset({"cancelled", "failed", "completed"}),
    "cancelled": frozenset({"queued", "archived", "deleting"}),
    "failed": frozenset({"queued", "archived", "deleting"}),
    "completed": frozenset({"archived", "deleting"}),
    "archived": frozenset({"completed", "failed", "cancelled", "deleting"}),
    "deleting": frozenset(),
}

# Used only by the startup reconciler for runs a pre-P0-3 delete left behind.
REPAIR_TRANSITIONS: dict[str, frozenset[str]] = {
    "deleting": frozenset({"completed", "failed", "cancelled", "archived"}),
}


class LifecycleError(ValueError):
    """A run lifecycle request violates the state table or writer contract."""


def classify(value: object) -> str:
    """Return the state of a decoded ``status.json`` payload or ``unknown``."""

    if not isinstance(value, dict):
        return UNKNOWN
    state = value.get("status")
    return state if isinstance(state, str) and state in STATES else UNKNOWN


def check_transition(source: str, target: str, *, repair: bool = False) -> None:
    if target not in STATES:
        raise LifecycleError(f"Unknown run state {target}")
    if source not in STATES:
        raise LifecycleError(f"Run has unknown current state {source}")
    allowed = REPAIR_TRANSITIONS.get(source, frozenset()) if repair else TRANSITIONS[source]
    if target not in allowed:
        raise LifecycleError(f"Run cannot transition from {source} to {target}")
