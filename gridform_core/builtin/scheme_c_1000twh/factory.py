"""Deprecated pre-v2 Scheme C factory.

The factory used a separate orchestrator and bypassed manifest resolution.  It
is preserved solely to return an actionable migration error.
"""

from __future__ import annotations

from ...errors import DeprecatedRouteError


def build(*args, **kwargs):
    del args, kwargs
    raise DeprecatedRouteError(
        "gridform_core.builtin.scheme_c_1000twh.factory.build is retired. "
        "Call gridform_core.application.run_project_application; select "
        "'scheme-c-psm' through the project module graph. For retained-output "
        "comparison use `python -m gridform_core.reference_comparison`. "
        "Removal is scheduled for FORCE 0.7.0."
    )
