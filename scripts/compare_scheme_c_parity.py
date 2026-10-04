"""Compare an exact VALUE run with the retained authoritative fixture."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def close(actual: float, expected: float, *, absolute: float = 1e-6, relative: float = 1e-10) -> bool:
    return math.isclose(float(actual), float(expected), abs_tol=absolute, rel_tol=relative)


def compare(actual: dict, fixture: dict) -> dict:
    costs = {str(int(row["Year"])): row for row in actual["system_cost_history"]}
    capacities = {str(int(row["Year"])): row for row in actual["capacity_history"]}
    investments = {
        (str(int(row["year"])), row["technology"]): row
        for row in actual["investment_decisions"]
    }
    checks = []

    def check(year: str, metric: str, value: float, expected: float, tolerance: float = 1e-6) -> None:
        checks.append({
            "year": int(year),
            "metric": metric,
            "actual": float(value),
            "expected": float(expected),
            "absolute_difference": abs(float(value) - float(expected)),
            "pass": close(value, expected, absolute=tolerance),
        })

    for year, expected in fixture["years"].items():
        cost = costs[year]
        capacity = capacities[year]
        check(year, "total_system_cost_gbp", cost["Total_System_Cost_GBP"], expected["total_system_cost_gbp"], 0.01)
        check(year, "cost_per_mwh_gbp", cost["Cost_per_MWh_GBP"], expected["cost_per_mwh_gbp"], 1e-8)
        check(year, "total_energy_generated_mwh", cost["Total_Energy_Generated_MWh"], expected["total_energy_generated_mwh"], 0.01)
        check(year, "solar_capacity_mw", capacity["Solar_Capacity_MW"], expected["solar_capacity_mw"], 1e-6)
        check(year, "onshore_capacity_mw", capacity["Onshore_Capacity_MW"], expected["onshore_capacity_mw"], 1e-6)
        check(year, "offshore_capacity_mw", capacity["Offshore_Capacity_MW"], expected["offshore_capacity_mw"], 1e-6)
        check(year, "quarter_c_battery_capacity_mw", capacity["0.25c_battery_Capacity_MW"], expected["quarter_c_battery_capacity_mw"], 1e-6)
        addition_key = "quarter_c_battery_suggested_addition_mw"
        if addition_key in expected:
            check(year, addition_key, investments[(year, "0.25c_battery")]["suggested_addition_mw"], expected[addition_key], 0.01)
        for technology in ("solar", "onshore", "offshore"):
            key = f"{technology}_suggested_addition_mw"
            if key in expected:
                check(year, key, investments[(year, technology)]["suggested_addition_mw"], expected[key], 0.01)
    return {
        "source_run": fixture["source_run"],
        "passed": all(item["pass"] for item in checks),
        "checks_passed": sum(1 for item in checks if item["pass"]),
        "checks_total": len(checks),
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests" / "fixtures" / "scheme_c_2025_2026_authoritative.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    actual = json.loads(args.actual.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    report = compare(actual, fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "checks_passed", "checks_total")}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
