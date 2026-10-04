"""Manifest-derived module catalog and stable data-contract slots."""

from .module_conformance import conformance_report
from .module_installation import list_module_installations
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
    }


_SNAPSHOT = module_catalog_snapshot()
MODULE_REGISTRY = _SNAPSHOT["registry"]
MODULES = _SNAPSHOT["modules"]
MODULE_SLOT_BY_ID = _SNAPSHOT["slot_by_id"]
REQUIRED_MODULE_SLOTS = _SNAPSHOT["required_slots"]

DATASET_SLOTS = [
    {"role": "fleet.generators", "group": "PSM", "label": "Existing generator fleet", "formats": ["json"], "required": True},
    {"role": "demand.forecast", "group": "PSM", "label": "Forecast demand profile", "formats": ["csv", "parquet"], "required": True, "unit": "MW", "interval_minutes": 30},
    {"role": "demand.real", "group": "PSM", "label": "Real demand profile", "formats": ["csv", "parquet"], "required": True, "unit": "MW", "interval_minutes": 30},
    {"role": "weather.wind", "group": "PSM", "label": "Wind weather field", "formats": ["nc", "zarr"], "required": True},
    {"role": "weather.solar", "group": "PSM", "label": "Solar weather field", "formats": ["nc", "zarr"], "required": True},
    {"role": "market.france.profile", "group": "PSM", "label": "France import availability", "formats": ["csv"], "required": True},
    {"role": "market.france.price", "group": "PSM", "label": "France external price", "formats": ["csv"], "required": True},
    {"role": "market.belgium.profile", "group": "PSM", "label": "Belgium import availability", "formats": ["csv"], "required": True},
    {"role": "market.belgium.price", "group": "PSM", "label": "Belgium external price", "formats": ["csv"], "required": True},
    {"role": "market.netherlands.profile", "group": "PSM", "label": "Netherlands import availability", "formats": ["csv"], "required": True},
    {"role": "market.netherlands.price", "group": "PSM", "label": "Netherlands external price", "formats": ["csv"], "required": True},
    {"role": "market.norway.profile", "group": "PSM", "label": "Norway import availability", "formats": ["csv"], "required": True},
    {"role": "market.norway.price", "group": "PSM", "label": "Norway external price", "formats": ["csv"], "required": True},
    {"role": "market.ireland.profile", "group": "PSM", "label": "Ireland import availability", "formats": ["csv"], "required": True},
    {"role": "market.ireland.price", "group": "PSM", "label": "Ireland external price", "formats": ["csv"], "required": True},
    {"role": "profiles.vre_solar", "group": "CEM", "label": "System-average solar profile", "formats": ["csv"], "required": True},
    {"role": "profiles.vre_onshore", "group": "CEM", "label": "System-average onshore profile", "formats": ["csv"], "required": True},
    {"role": "profiles.vre_offshore", "group": "CEM", "label": "System-average offshore profile", "formats": ["csv"], "required": True},
    {"role": "projects.repd", "group": "CEM", "label": "Normalized planning projects", "formats": ["csv", "parquet"], "required": True},
    {"role": "source.repd_raw", "group": "CEM", "label": "Raw UK REPD source", "formats": ["csv"], "required": True},
    {"role": "costs.capital", "group": "CEM", "label": "Technology capital costs", "formats": ["csv", "json"], "required": True, "unit": "GBP/MW"},
    {"role": "policy.support", "group": "CEM", "label": "Policy and support mechanisms", "formats": ["csv", "json", "xlsx"], "required": True},
    {"role": "planning.timelines", "group": "CEM", "label": "Planning stage timelines", "formats": ["csv", "json"], "required": True},
    {"role": "planning.success_rates", "group": "CEM", "label": "Regional technology success rates", "formats": ["csv", "json"], "required": True},
    {"role": "config.model_parameters", "group": "CEM", "label": "VALUE investment and policy parameters", "formats": ["json"], "required": True},
]
