"""Stable public surface for VALUE model engines and data packs."""

from .contracts import (
    CapacityDecision,
    DataPack,
    ModelState,
    PSMInput,
    PSMResult,
    YearContext,
    YearResult,
)
from .orchestrator import AnnualModelOrchestrator
from .builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM
from .v2.module_manifest import workspace_registry


def __getattr__(name: str):
    # Keep the CLI module importable with ``python -m gridform_core.application``
    # without pre-importing it through the package and triggering runpy's
    # duplicate-module warning.
    if name == "run_project_application":
        from .application import run_project_application

        return run_project_application
    raise AttributeError(name)

__all__ = [
    "AnnualModelOrchestrator",
    "SchemeCNativePSM",
    "CapacityDecision",
    "DataPack",
    "ModelState",
    "PSMInput",
    "PSMResult",
    "YearContext",
    "YearResult",
    "run_project_application",
    "workspace_registry",
]
