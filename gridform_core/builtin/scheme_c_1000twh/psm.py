"""Deprecated pre-v2 Scheme C adapter.

The public ``scheme-c-psm`` identity is implemented only by
``SchemeCNativePSM`` and resolved through the workspace registry.  This module
is kept for import-level migration diagnostics; it never clears a market.
"""

from __future__ import annotations

from ...errors import DeprecatedRouteError


REPLACEMENT = "gridform_core.application.run_project_application"
REMOVAL_VERSION = "0.7.0"


class SchemeCPSM:
    """Retired direct adapter; not a registered module implementation."""

    id = "scheme-c-direct-adapter-deprecated"
    version = "0.5.0-deprecated"
    execution_kind = "deprecated"

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs
        raise DeprecatedRouteError(
            "gridform_core.builtin.scheme_c_1000twh.psm.SchemeCPSM is retired. "
            f"Use {REPLACEMENT} with module ID 'scheme-c-psm'. "
            f"Removal is scheduled for FORCE {REMOVAL_VERSION}."
        )
