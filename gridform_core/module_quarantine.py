"""Fault isolation for locally installed modules and extensions (P0-2).

Built-in manifests stay fail-closed: a broken built-in still stops the
process.  External (installer-owned) manifests are fail-isolated: a broken
external entry is quarantined in memory, never written into the scanned
``modules/`` tree, and no external entry silently wins a conflict.

One re-entrant ``MODULE_LIFECYCLE_LOCK`` serialises every install, enable,
disable and catalogue refresh in the process.  Global lock order
(P0_CONVENTIONS section 5): ``.backend.lock -> STUDY_LIFECYCLE_LOCK ->
RUN_ACTION_LOCKS[run] -> MODULE_LIFECYCLE_LOCK -> .reservation.lock ->
status.lock``; while it is held no STUDY_LIFECYCLE_LOCK may be requested.

This module only depends on the standard library and ``errors`` so the
registry, the extension framework and the worker can import it cheaply.
"""

from __future__ import annotations

import threading

from .errors import ContractError

MODULE_LIFECYCLE_LOCK = threading.RLock()


class ModuleQuarantinedError(ContractError):
    """A coded module-lifecycle or quarantine failure.

    A ``ValueError`` (through ``ContractError``) so every existing handler
    still catches it; ``code`` is per instance and doubles as the public
    failure code a worker records.
    """

    category = "contract"

    def __init__(self, code: str, message: str, *, entries: tuple = ()) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.entries = tuple(entries)
