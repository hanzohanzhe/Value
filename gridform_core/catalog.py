"""Manifest-derived module catalog and stable data-contract slots."""

from .dataset_slots import DATASET_SLOTS  # noqa: F401  (re-export, C27)
from .module_conformance import conformance_report
from .module_installation import list_module_installations
from .module_quarantine import MODULE_LIFECYCLE_LOCK, quarantine_report
from .v2.module_manifest import workspace_registry

_LIFECYCLE_ORDER = {
    "pipeline": 10,
    "storage_cost": 15,
    "weather_spatializer": 18,
    "psm": 20,
    "balancing": 21,
    "vre_cap": 30,
    "storage_cap": 31,
    "network_expansion": 35,
    "investment": 40,
    "transition": 50,
}


def _catalog_row(
    row: dict[str, object],
    conformance: dict[str, dict[str, object]],
    installations: dict[str, dict[str, object]],
) -> dict[str, object]:
    result = dict(row)
    result["kind"] = "psm" if row["slot"] in {"psm", "balancing"} else "system" if row["slot"] == "transition" else "cem"
    result["order"] = _LIFECYCLE_ORDER[str(row["slot"])]
    result["conformance"] = conformance.get(str(row["id"]), {"status": "not_evaluated"})
    installation = installations.get(str(row["id"]))
    result["origin"] = "local_bundle" if installation else "built_in"
    if installation:
        result["installation"] = {
            key: installation.get(key)
            for key in ("installed_at", "bundle_sha256", "source_sha256", "execution_boundary")
        }
    result["execution"] = {
        "native_v2": result["conformance"].get("status") == "passed",
        "reference_comparison": False,
        "internal_reference_bridge": "scheme-c.reference-bridge/v1" in tuple(row.get("provides_capabilities") or ()),
        "reference_unavailable_reason": (
            "Reference comparison is not a project module. Use the explicit, Python-3.10-only comparison command."
            if "scheme-c.reference-bridge/v1" in tuple(row.get("provides_capabilities") or ())
            else "This module is executable through the native v2 orchestrator but has no private retained-kernel bridge."
        ),
    }
    # The versioned interface and historical reference implementation stay in
    # source for reproducibility, but transmission CEM is deliberately outside
    # the production Study builder until a supported executable is released.
    result["user_selectable"] = row["slot"] != "network_expansion"
    return result


def module_catalog_snapshot() -> dict[str, object]:
    registry = workspace_registry()
    conformance = {
        str(row["module_id"]): row
        for row in conformance_report(registry)["modules"]
    }
    installations = {
        str(row["module_id"]): row
        for row in list_module_installations()
        if row.get("enabled")
    }
    modules = [
        _catalog_row(row, conformance, installations)
        for row in registry.catalog()
    ]
    slot_by_id = {str(row["id"]): str(row["slot"]) for row in modules}
    required_slots = tuple(sorted(
        {
            str(row["slot"])
            for row in modules
            if row.get("selection_required")
        },
        key=lambda slot: _LIFECYCLE_ORDER[slot],
    ))
    return {
        "registry": registry,
        "modules": modules,
        "slot_by_id": slot_by_id,
        "required_slots": required_slots,
        "quarantine": quarantine_report(registry),
    }


_SNAPSHOT: dict[str, object] | None = None
_LEGACY_NAMES = {
    "MODULE_REGISTRY": "registry",
    "MODULES": "modules",
    "MODULE_SLOT_BY_ID": "slot_by_id",
    "REQUIRED_MODULE_SLOTS": "required_slots",
}


def get_catalog_snapshot(*, refresh: bool = False) -> dict[str, object]:
    """The cached catalogue; built on first use, never at import (G4-02).

    Takes MODULE_LIFECYCLE_LOCK (the same lock as every module lifecycle
    change, so there is no ABBA ordering between them).
    """

    global _SNAPSHOT
    with MODULE_LIFECYCLE_LOCK:
        if refresh or _SNAPSHOT is None:
            _SNAPSHOT = module_catalog_snapshot()
        return _SNAPSHOT


def __getattr__(name: str) -> object:
    """PEP 562: the former module constants resolve lazily to the snapshot."""

    if name in _LEGACY_NAMES:
        return get_catalog_snapshot()[_LEGACY_NAMES[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
