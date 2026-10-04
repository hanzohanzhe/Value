"""Manifest and callable-shape conformance checks for installed modules."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Mapping

from .parameters import REGISTRY
from .v2.module_manifest import ModuleManifest, ModuleRegistryV2, workspace_registry
from .runtime_paths import external_modules_root


REQUIRED_METHODS = {
    "psm": ("run",),
    "investment": ("decide",),
    "pipeline": ("advance_year", "admit_projects"),
    "vre_cap": ("evaluate",),
    "storage_cap": ("evaluate",),
    "network_expansion": (
        "advance_year", "propose", "admit", "transition", "annual_resource_costs",
    ),
    "balancing": ("clear",),
    "transition": ("apply",),
    "storage_cost": ("create",),
    "weather_spatializer": ("build",),
}


def check_storage_lifecycle(model) -> None:
    """Exercise actual Battery consumers, without a simulation or runtime mutation."""
    from math import isfinite
    from .builtin.scheme_c_1000twh.runtime_compat.modular_simulation_model import Battery, physical_period_hours

    period_hours = physical_period_hours()
    if not isfinite(period_hours) or period_hours <= 0:
        raise ValueError("physical period hours must be finite and positive")

    # Bypass runtime-dependent construction only; all lifecycle calls are real.
    battery = Battery.__new__(Battery)
    battery.name = "conformance-fixture"
    battery.cost_recovery = model
    battery.capital_cost = 1_000_000.0
    battery.power_capacity_mw = battery.energy_capacity_mwh = 1.0
    battery.duration_hours = 1.0
    battery.n_1 = battery.n_2 = 0.9
    battery.stored_energy = {}

    def finite_nonnegative(value):
        if not isfinite(float(value)) or float(value) < 0:
            raise ValueError("storage lifecycle values must be finite and non-negative")

    def report(year):
        result = battery.storage_cost_report()
        if result.get("prepared_year") != year or not result.get("method"):
            raise ValueError("report must identify method and prepared_year")
        for key in ("cycle_depreciation_gbp_per_mwh",
                    "previous_year_sold_mwh", "current_year_sold_mwh", "current_year_average_dwell_periods"):
            finite_nonnegative(result[key])
        return result

    battery.prepare_operating_year(2025)
    if model.prepared_year != 2025:
        raise ValueError("prepare_year must update prepared_year")
    finite_nonnegative(battery.storage_fee)
    finite_nonnegative(battery.per_storage_fee)
    battery.charge(0, 1.0)
    finite_nonnegative(battery.storage_bid_price(2, 0))
    output = battery.discharge(0, 0.4, 2)
    first = report(2025)
    if output <= 0 or abs(float(first["current_year_sold_mwh"]) - output * period_hours) > 1e-9:
        raise ValueError("report must observe actual non-zero Battery discharge")
    battery.prepare_operating_year(2025)
    if report(2025)["current_year_sold_mwh"] != first["current_year_sold_mwh"]:
        raise ValueError("same-year preparation must preserve observations")
    battery.prepare_operating_year(2026)
    second = report(2026)
    if second["previous_year_sold_mwh"] != first["current_year_sold_mwh"] or second["current_year_sold_mwh"] != 0:
        raise ValueError("next-year preparation must carry sales and reset current observations")
    finite_nonnegative(battery.storage_bid_price(0, -1))


def check_manifest(registry: ModuleRegistryV2, manifest: ModuleManifest) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    unknown_parameters = sorted(set(manifest.parameters).difference(REGISTRY))
    if unknown_parameters:
        errors.append("undeclared parameter IDs: " + ", ".join(unknown_parameters))
    if not manifest.units:
        warnings.append("no explicit units declared; semantic role units remain authoritative")
    try:
        instance = registry.resolve(manifest.id, expected_slot=manifest.slot)
    except Exception as exc:
        errors.append(f"implementation resolution failed: {exc}")
        instance = None
    if instance is not None:
        for method in REQUIRED_METHODS[manifest.slot]:
            if not callable(getattr(instance, method, None)):
                errors.append(f"implementation does not provide callable {method}")
        if manifest.slot == "storage_cost" and not errors:
            try:
                from .builtin.scheme_c_1000twh.runtime_compat.modular_simulation_model import physical_period_hours
                model = instance.create(
                    battery_type="1c",
                    period_hours=physical_period_hours(),
                    legacy_storage_fee=2.0,
                    legacy_holding_fee=0.1,
                )
                check_storage_lifecycle(model)
            except Exception as exc:
                errors.append(f"minimal storage-cost fixture failed: {exc}")
    return {
        "module_id": manifest.id,
        "slot": manifest.slot,
        "version": manifest.version,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
    }


def conformance_report(registry: ModuleRegistryV2) -> dict[str, object]:
    modules = [
        check_manifest(registry, manifest)
        for manifest in registry.manifests().values()
    ]
    return {
        "schema_version": "value.module-conformance/v1",
        "passed": all(row["status"] == "passed" for row in modules),
        "modules": sorted(modules, key=lambda row: (str(row["slot"]), str(row["module_id"]))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate installed VALUE modules")
    parser.add_argument("--modules", type=Path, default=external_modules_root())
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = conformance_report(workspace_registry(args.modules))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
