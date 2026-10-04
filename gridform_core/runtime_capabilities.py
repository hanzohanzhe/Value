"""Evidence-bounded runtime capabilities for VALUE and retained comparison."""

from __future__ import annotations

import importlib.util
import platform
import sys
from typing import Iterable

from .errors import RuntimeCapabilityError


VALUE_NATIVE = "value-native"
DOCTORAL_REPRODUCTION = "doctoral-reproduction"
SUPPORTED_NATIVE_PYTHON = ((3, 10),)
SUPPORTED_REFERENCE_PYTHON = ((3, 10),)

NATIVE_BASE_IMPORTS = ("numpy", "pandas")
NATIVE_VALUE_IMPORTS = ("xarray", "netCDF4", "pyproj", "dateutil")
PERFECT_FORESIGHT_IMPORTS = ("scipy",)
SCIPY_EXTENSION_MODULES = {
    "value-perfect-foresight-lp",
    "value-reference-dc-network",
    "value-reference-ac-feasibility",
}
REFERENCE_ONLY_IMPORTS = ("matplotlib", "openpyxl", "seaborn")


def _version_label(values: Iterable[tuple[int, int]]) -> list[str]:
    return [f"{major}.{minor}" for major, minor in values]


def capability_status(
    capability: str,
    *,
    selected_module_ids: Iterable[str] = (),
) -> dict[str, object]:
    selected = set(selected_module_ids)
    if capability == VALUE_NATIVE:
        supported = SUPPORTED_NATIVE_PYTHON
        imports = list(NATIVE_BASE_IMPORTS)
        if "value-bid-at-cost-psm" in selected:
            imports.extend(NATIVE_VALUE_IMPORTS)
        if selected.intersection(SCIPY_EXTENSION_MODULES):
            imports.extend(PERFECT_FORESIGHT_IMPORTS)
        scope = (
            "v2 orchestrator, manifest-resolved live modules and public/synthetic "
            "data contracts"
        )
        evidence = "Prompt 29-33 package, contract, live two-year smoke and module tests"
    elif capability == DOCTORAL_REPRODUCTION:
        supported = SUPPORTED_REFERENCE_PYTHON
        imports = [
            *NATIVE_BASE_IMPORTS,
            *NATIVE_VALUE_IMPORTS,
            *REFERENCE_ONLY_IMPORTS,
        ]
        scope = "preserved whole-kernel VALUE retained-output comparison"
        evidence = "2026-07-18 retained-output environment and Prompt 33 explicit comparison"
    else:
        raise ValueError(f"Unknown runtime capability: {capability}")
    imports = list(dict.fromkeys(imports))
    missing = [name for name in imports if importlib.util.find_spec(name) is None]
    interpreter = sys.version_info[:2]
    python_supported = interpreter in supported
    available = python_supported and not missing
    action = None
    if not python_supported:
        action = (
            f"Use a supported {capability} interpreter: "
            + ", ".join(_version_label(supported))
            + ". No broader Python support is claimed without numerical evidence."
        )
    elif missing:
        lock = (
            "requirements/value-native-py310.lock"
            if capability == VALUE_NATIVE
            else "requirements/value-doctoral-reproduction-py310.lock"
        )
        action = f"Install the missing capability packages from {lock}: {', '.join(missing)}."
    return {
        "schema_version": "value.runtime-capability/v1",
        "capability": capability,
        "scope": scope,
        "available": available,
        "python_supported": python_supported,
        "supported_python": _version_label(supported),
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "required_imports": imports,
        "missing_imports": missing,
        "selected_module_ids": sorted(selected),
        "evidence_basis": evidence,
        "corrective_action": action,
    }


def capability_matrix(*, selected_module_ids: Iterable[str] = ()) -> dict[str, object]:
    return {
        "schema_version": "value.runtime-capability-matrix/v1",
        "selected": VALUE_NATIVE,
        "capabilities": {
            VALUE_NATIVE: capability_status(
                VALUE_NATIVE, selected_module_ids=selected_module_ids
            ),
            DOCTORAL_REPRODUCTION: capability_status(DOCTORAL_REPRODUCTION),
        },
    }


def require_runtime_capability(
    capability: str,
    *,
    selected_module_ids: Iterable[str] = (),
) -> dict[str, object]:
    status = capability_status(capability, selected_module_ids=selected_module_ids)
    if not status["available"]:
        raise RuntimeCapabilityError(
            f"Runtime capability '{capability}' is unavailable on Python "
            f"{status['python']}. {status['corrective_action']}"
        )
    return status
