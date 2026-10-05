"""Read-only comparison of dynamic, legacy-tariff and retained VALUE runs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Mapping

from .bundle_validator import validate_run_bundle


METRICS = {
    "Total_System_Cost_GBP": ("GBP", 0.01),
    "Cost_per_MWh_GBP": ("GBP/MWh", 1e-8),
    "Total_Operational_Cost_GBP": ("GBP", 0.01),
    "Total_Levelized_Capital_Cost_GBP": ("GBP", 0.01),
    "Total_Energy_Generated_MWh": ("MWh", 0.01),
}
CAPACITIES = {
    "Solar_Capacity_MW": ("MW", 1e-6),
    "Onshore_Capacity_MW": ("MW", 1e-6),
    "Offshore_Capacity_MW": ("MW", 1e-6),
    "Total_Storage_Capacity_MW": ("MW", 1e-6),
    "0.25c_battery_Capacity_MW": ("MW", 1e-6),
}


def _output(path: Path) -> Path:
    return path / "model-output" if (path / "model-output" / "modular-run.json").is_file() else path


def _modular(path: Path) -> dict[str, object]:
    output = _output(path)
    resolved = json.loads((output / "resolved-run.json").read_text(encoding="utf-8"))
    modular_path = output / "modular-run.json"
    if modular_path.is_file():
        payload = json.loads(modular_path.read_text(encoding="utf-8"))
        costs = {int(row["Year"]): row for row in payload["system_cost_history"]}
        capacities = {int(row["Year"]): row for row in payload["capacity_history"]}
        cost_definition_id = "scheme-c-historical-system-cost/v1"
    else:
        annual = json.loads((output / "year-results-v2.json").read_text(encoding="utf-8"))
        ledger = json.loads(
            (output / "ledgers" / "annual-cost-ledger.json").read_text(encoding="utf-8")
        )
        costs = {}
        capacities = {}
        ledger_by_year = {int(row["year"]): row for row in ledger["years"]}
        storage_technologies = {
            "1c_battery", "0.5c_battery", "0.25c_battery",
            "hydrogen_battery", "pumped_hydro",
        }
        for result in annual:
            year = int(result["year"])
            market = result["market"]
            cost = ledger_by_year[year]
            costs[year] = {
                "Year": year,
                "Total_System_Cost_GBP": cost["cem_system_cost_gbp"],
                "Cost_per_MWh_GBP": cost["cem_system_cost_gbp_per_mwh_served"],
                "Total_Operational_Cost_GBP": market["total_operational_cost_gbp"],
                "Total_Levelized_Capital_Cost_GBP": (
                    cost["headline_capital_gbp"]
                    if cost.get("headline_capital_gbp") is not None
                    else market["total_levelized_capital_cost_gbp"]
                ),
                "Total_Energy_Generated_MWh": market["total_generation_mwh"],
            }
            assets = result["planning_advance"]["operating_state"]["assets"]
            by_technology: dict[str, float] = {}
            for asset in assets:
                technology = str(asset["technology"])
                by_technology[technology] = by_technology.get(technology, 0.0) + float(
                    asset["capacity_mw"]
                )
            capacities[year] = {
                "Year": year,
                "Solar_Capacity_MW": by_technology.get("solar", 0.0),
                "Onshore_Capacity_MW": by_technology.get("onshore", 0.0),
                "Offshore_Capacity_MW": by_technology.get("offshore", 0.0),
                "Total_Storage_Capacity_MW": sum(
                    by_technology.get(technology, 0.0)
                    for technology in storage_technologies
                ),
                "0.25c_battery_Capacity_MW": by_technology.get("0.25c_battery", 0.0),
            }
        cost_definition_id = str(ledger.get("definition_id") or "unknown")
    modules = resolved.get("modules") or {}
    storage_module = modules.get("storage_cost")
    return {
        "label": path.name,
        "output": str(output),
        "storage_cost_policy": storage_module.get("module_id") if isinstance(storage_module, Mapping) else storage_module,
        "cost_definition_id": cost_definition_id,
        "costs": costs,
        "capacities": capacities,
    }


def _csv_rows(path: Path) -> dict[int, dict[str, float | str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            rows.append({key: float(value) if key != "Year" and value not in {"", None} else int(float(value)) if key == "Year" else value for key, value in row.items()})
    return {int(row["Year"]): row for row in rows}


def _retained(path: Path) -> dict[str, object]:
    cost_files = list(path.glob("system_cost_history_case3_v2_existing_decarb_base.csv"))
    capacity_files = list(path.glob("capacity_history_case3_v2_existing_decarb_base.csv"))
    if not cost_files or not capacity_files:
        raise FileNotFoundError("Retained output must contain the VALUE system-cost and capacity-history CSV files")
    return {
        "label": "retained-scheme-c-2026-07-18",
        "output": str(path.resolve()),
        "storage_cost_policy": "retained_scheme_c_fixed_tariff",
        "cost_definition_id": "scheme-c-historical-system-cost/v1",
        "costs": _csv_rows(cost_files[0]),
        "capacities": _csv_rows(capacity_files[0]),
    }


def _pair(name: str, left: Mapping[str, object], right: Mapping[str, object]) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    left_costs, right_costs = left["costs"], right["costs"]
    left_caps, right_caps = left["capacities"], right["capacities"]
    years = sorted(set(left_costs).intersection(right_costs))  # type: ignore[arg-type]
    for year in years:
        for group, first, second, definitions in (
            ("annual_cost_and_energy", left_costs[year], right_costs[year], METRICS),  # type: ignore[index]
            ("beginning_capacity", left_caps[year], right_caps[year], CAPACITIES),  # type: ignore[index]
        ):
            for metric, (unit, tolerance) in definitions.items():
                if metric not in first or metric not in second:
                    continue
                actual, reference = float(first[metric]), float(second[metric])
                difference = actual - reference
                checks.append({
                    "year": year, "group": group, "metric": metric, "unit": unit,
                    "left": actual, "right": reference,
                    "difference_left_minus_right": difference,
                    "percent_difference": (difference / reference * 100.0) if reference else None,
                    "absolute_tolerance": tolerance,
                    "within_declared_tolerance": math.isclose(actual, reference, abs_tol=tolerance, rel_tol=1e-10),
                })
    cost_definitions_comparable = left.get("cost_definition_id") == right.get("cost_definition_id")
    return {
        "name": name,
        "left": left["label"], "right": right["label"],
        "left_storage_cost_policy": left["storage_cost_policy"],
        "right_storage_cost_policy": right["storage_cost_policy"],
        "left_cost_definition_id": left.get("cost_definition_id"),
        "right_cost_definition_id": right.get("cost_definition_id"),
        "cost_definitions_comparable": cost_definitions_comparable,
        "interpretation": (
            "numerically_comparable"
            if cost_definitions_comparable
            else "descriptive_only_cost_definition_mismatch"
        ),
        "years": years,
        "all_declared_metrics_within_tolerance": cost_definitions_comparable and bool(checks) and all(row["within_declared_tolerance"] for row in checks),
        "checks_passed": sum(bool(row["within_declared_tolerance"]) for row in checks),
        "checks_total": len(checks),
        "checks": checks,
    }


def compare_three_scenarios(dynamic: Path, legacy: Path, retained: Path) -> dict[str, object]:
    dynamic_data, legacy_data, retained_data = _modular(dynamic), _modular(legacy), _retained(retained)
    dynamic_bundle = dynamic if (dynamic / "provenance.json").is_file() else _output(dynamic)
    legacy_bundle = legacy if (legacy / "provenance.json").is_file() else _output(legacy)
    functional = {
        "dynamic_bundle": validate_run_bundle(dynamic_bundle),
        "legacy_bundle": validate_run_bundle(legacy_bundle),
    }
    legacy_retained = _pair("legacy_vs_retained", legacy_data, retained_data)
    return {
        "schema_version": "value.three-scenario-comparison/v1",
        "functional_release": {
            "go": functional["dynamic_bundle"]["valid"] and functional["legacy_bundle"]["valid"],
            "bundle_validation": functional,
        },
        "numerical_claims": {
            "legacy_is_exact_scheme_c_reproduction": legacy_retained["all_declared_metrics_within_tolerance"],
            "dynamic_is_expected_to_match_retained": False,
            "note": "The dynamic policy is an explicit scientific alternative. A difference is not a software failure after functional and invariant gates pass.",
        },
        "comparisons": {
            "dynamic_vs_legacy": _pair("dynamic_vs_legacy", dynamic_data, legacy_data),
            "legacy_vs_retained": legacy_retained,
            "dynamic_vs_retained": _pair("dynamic_vs_retained", dynamic_data, retained_data),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two VALUE storage-cost scenarios with retained VALUE")
    parser.add_argument("--dynamic", required=True, type=Path)
    parser.add_argument("--legacy", required=True, type=Path)
    parser.add_argument("--retained", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = compare_three_scenarios(args.dynamic, args.legacy, args.retained)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "functional_go": report["functional_release"]["go"],
        "legacy_exact_reproduction": report["numerical_claims"]["legacy_is_exact_scheme_c_reproduction"],
    }, indent=2))
    raise SystemExit(0 if report["functional_release"]["go"] else 1)


if __name__ == "__main__":
    main()
