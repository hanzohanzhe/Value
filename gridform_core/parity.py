"""Release-gate comparisons for a completed VALUE run bundle.

The comparison is deliberately read-only.  It compares the copied VALUE
session artifacts with their public v2 contract materialisation, then checks the
durable planning and market ledgers.  It never re-runs or rewrites a fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


CAPACITY_COLUMNS = {
    "solar": "Solar_Capacity_MW",
    "onshore": "Onshore_Capacity_MW",
    "offshore": "Offshore_Capacity_MW",
    "storage": "Total_Storage_Capacity_MW",
    "CCGT": "CCGT_Capacity_MW",
    "OCGT": "OCGT_Capacity_MW",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _close(actual: float, expected: float, tolerance: float) -> bool:
    return math.isclose(
        float(actual), float(expected), abs_tol=float(tolerance), rel_tol=1e-10
    )


def compare_run_bundle(
    output_dir: Path,
    *,
    retained_fixture: Path | None = None,
) -> dict[str, Any]:
    """Compare one already-completed output directory without executing code."""

    output_dir = output_dir.resolve()
    modular = _read_json(output_dir / "modular-run.json")
    typed = _read_json(output_dir / "year-results-v2.json")
    module_events = _read_jsonl(output_dir / "module-events.jsonl")
    stage_events = _read_jsonl(output_dir / "orchestrator-events.jsonl")
    costs = {int(row["Year"]): row for row in modular["system_cost_history"]}
    capacities = {int(row["Year"]): row for row in modular["capacity_history"]}
    typed_years = {int(row["year"]): row for row in typed}
    checks: list[dict[str, Any]] = []

    def check(
        stage: str,
        year: int | None,
        metric: str,
        actual: Any,
        expected: Any,
        tolerance: float = 0.0,
    ) -> None:
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            passed = _close(float(actual), float(expected), tolerance)
            difference: float | None = abs(float(actual) - float(expected))
        else:
            passed = actual == expected
            difference = None
        checks.append({
            "stage": stage,
            "year": year,
            "metric": metric,
            "actual": actual,
            "expected": expected,
            "absolute_difference": difference,
            "absolute_tolerance": tolerance,
            "pass": passed,
        })

    # Beginning fleet and public PSM annual summaries.
    for year, source in costs.items():
        target = typed_years[year]
        operating_assets = {
            row["technology"]: row for row in target["planning_advance"]["operating_state"]["assets"]
        }
        for technology, column in CAPACITY_COLUMNS.items():
            check(
                "beginning_fleet",
                year,
                f"{technology}_capacity_mw",
                operating_assets[technology]["capacity_mw"],
                capacities[year][column],
                1e-6,
            )
        market = target["market"]
        for public_name, source_name, tolerance in (
            ("total_system_cost_gbp", "Total_System_Cost_GBP", 0.01),
            ("total_operational_cost_gbp", "Total_Operational_Cost_GBP", 0.01),
            ("total_levelized_capital_cost_gbp", "Total_Levelized_Capital_Cost_GBP", 0.01),
            ("total_generation_mwh", "Total_Energy_Generated_MWh", 0.01),
            ("total_blackout_mwh", "Total_Energy_Deficit_MWh", 0.01),
        ):
            check("psm_annual_summary", year, public_name, market[public_name], source[source_name], tolerance)

    # Expansion headroom is recorded at the real invocation boundary.
    source_headroom = {
        (int(event["year"]), str(event["module_id"])): event["limits_mw"]
        for event in module_events
        if event.get("action") in {"vre_cap.complete", "storage_cap.complete"}
    }
    for year, target in typed_years.items():
        for row in target["expansion_headroom"]:
            source = source_headroom[(year, row["module_id"])]
            for technology in sorted(set(source) | set(row["allowed_additions_mw"])):
                check(
                    "expansion_headroom", year,
                    f"{row['module_id']}:{technology}_mw",
                    row["allowed_additions_mw"].get(technology, 0.0),
                    source.get(technology, 0.0), 1e-9,
                )

    # Investment proposals/retirements must be the same non-zero recommendations
    # recorded by the copied scientific session.
    source_investments = {
        (int(row["year"]), str(row["technology"])): float(row["suggested_addition_mw"])
        for row in modular["investment_decisions"]
        if abs(float(row["suggested_addition_mw"])) > 1e-12
    }
    for year, target in typed_years.items():
        public_investments = {
            str(row["technology"]): float(row["capacity_mw"])
            for row in target["investment"]["proposals"]
        }
        public_investments.update({
            str(technology): -float(value)
            for technology, value in target["investment"]["retirements_mw"].items()
        })
        expected = {
            technology: value
            for (item_year, technology), value in source_investments.items()
            if item_year == year
        }
        check("agent_investment", year, "nonzero_technology_set", sorted(public_investments), sorted(expected))
        for technology, value in expected.items():
            check("agent_investment", year, f"{technology}_addition_mw", public_investments[technology], value, 1e-6)

    # Durable pipeline reconciliation is authoritative for individual projects.
    planning_summary_path = output_dir / "planning" / "summary.json"
    planning_evidence: dict[str, Any] = {"available": planning_summary_path.is_file()}
    if planning_summary_path.is_file():
        planning_summary = _read_json(planning_summary_path)
        complete = {
            int(event["year"]): event
            for event in module_events
            if event.get("action") == "pipeline.complete_year"
        }
        begin = {
            int(event["year"]): event
            for event in module_events
            if event.get("action") == "pipeline.begin_year"
        }
        for summary in planning_summary.get("years", []):
            year = int(summary["year"])
            active = int(summary.get("breakdowns", {}).get("outcome", {}).get("active", {}).get("projects", 0))
            check("planning_reconciliation", year, "introduced_equals_accounted", int(summary["introduced_projects"]), int(summary["accounted_projects"]))
            check("planning_reconciliation", year, "summary_reconciled", bool(summary["reconciled"]), True)
            check("planning_reconciliation", year, "active_pipeline_count", int(complete[year]["projects"]), active)
            if year + 1 in begin:
                check("next_year_pipeline", year, "ending_equals_next_beginning", int(complete[year]["projects"]), int(begin[year + 1]["projects"]))
        planning_evidence.update({
            "years": len(planning_summary.get("years", [])),
            "database_artifact": "planning/pipeline.sqlite",
            "summary_artifact": "planning/summary.json",
        })

    # The transition contract must expose the copied session's next-year fleet.
    for year, target in typed_years.items():
        if year + 1 not in capacities:
            continue
        next_assets = {row["technology"]: row for row in target["next_state"]["assets"]}
        for technology, column in CAPACITY_COLUMNS.items():
            check("next_year_fleet", year, f"{technology}_capacity_mw", next_assets[technology]["capacity_mw"], capacities[year + 1][column], 1e-6)

    # Stage-event completeness and contract continuity.
    expected_stages = [
        "planning.advance_year", "psm.run", "expansion.evaluate",
        "expansion.evaluate", "investment.decide", "planning.admit_projects",
        "state_transition.apply",
    ]
    for year in typed_years:
        observed = [event["stage"] for event in stage_events if int(event["year"]) == year]
        check("contract_lifecycle", year, "stage_order", observed, expected_stages)

    # Check every persisted market period with the same absolute/relative rule as
    # the writer.  This is independent of the metadata summary.
    market_evidence: dict[str, Any] = {"trace_level": "off", "periods": 0}
    market_db = output_dir / "market" / "market.sqlite"
    if market_db.is_file():
        with sqlite3.connect(market_db) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(period_summary)")
            }
            if "raw_energy_balance_residual_mwh" in columns:
                rows = connection.execute(
                    "SELECT year, period, stage, real_demand_mwh, accepted_supply_mwh, energy_balance_residual_mwh, raw_energy_balance_residual_mwh, compatibility_adjustment_mwh FROM period_summary"
                ).fetchall()
            else:
                rows = [(*row, row[-1], 0.0) for row in connection.execute(
                    "SELECT year, period, stage, real_demand_mwh, accepted_supply_mwh, energy_balance_residual_mwh FROM period_summary"
                ).fetchall()]
        maximum = 0.0
        maximum_raw = 0.0
        adjusted_periods = 0
        invalid = 0
        for _year, _period, _stage, demand, supply, residual, raw_residual, adjustment in rows:
            absolute = abs(float(residual))
            maximum = max(maximum, absolute)
            maximum_raw = max(maximum_raw, abs(float(raw_residual)))
            adjusted_periods += int(abs(float(adjustment)) > 1e-9)
            allowed = max(1e-5, 0.001 * max(abs(float(demand)), abs(float(supply)), 1.0))
            invalid += int(absolute > allowed)
        metadata = _read_json(output_dir / "market" / "metadata.json")
        check("market_balance", None, "invalid_periods", invalid, 0)
        check("market_balance", None, "period_row_count", len(rows), int(metadata["rows"]["period_summary"]))
        market_evidence = {
            "trace_level": metadata["trace_level"],
            "periods": len(rows),
            "maximum_absolute_residual_mwh": maximum,
            "maximum_absolute_raw_residual_mwh": maximum_raw,
            "compatibility_adjustment_periods": adjusted_periods,
            "relative_tolerance": 0.001,
            "database_artifact": "market/market.sqlite",
        }

    # Agent economics are retained as a compact checksum/count summary while the
    # public decision contract contains only the decision-relevant additions.
    agent_evidence: dict[str, Any] = {"available": False}
    investment_db = output_dir / "investment_analysis_trace.sqlite"
    if investment_db.is_file():
        with sqlite3.connect(investment_db) as connection:
            rows = connection.execute(
                "SELECT year, asset_name, electricity_income, hydrogen_income, operational_cost, total_income, net_revenue, recommendation, current_capacity, suggested_new_capacity FROM investment_analysis ORDER BY year, asset_name"
            ).fetchall()
        encoded = json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        agent_evidence = {
            "available": True,
            "rows": len(rows),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "recommendations": dict(sorted(Counter(str(row[7]) for row in rows).items())),
            "total_income_gbp": sum(float(row[5] or 0.0) for row in rows),
            "total_operational_cost_gbp": sum(float(row[4] or 0.0) for row in rows),
            "database_artifact": "investment_analysis_trace.sqlite",
        }
        source_by_year: dict[int, list[tuple[Any, ...]]] = {}
        for row in rows:
            source_by_year.setdefault(int(row[0]), []).append(row)
        for year, source_rows in source_by_year.items():
            public = (
                typed_years[year]["investment"]
                .get("extensions", {})
                .get("agent_economics", {})
            )
            check("agent_economics", year, "agent_rows", public.get("agent_rows"), len(source_rows))
            check(
                "agent_economics", year, "total_income_gbp",
                public.get("total_income_gbp"),
                sum(float(row[5] or 0.0) for row in source_rows), 0.01,
            )
            check(
                "agent_economics", year, "total_operational_cost_gbp",
                public.get("total_operational_cost_gbp"),
                sum(float(row[4] or 0.0) for row in source_rows), 0.01,
            )
            check(
                "agent_economics", year, "recommendations",
                public.get("recommendations"),
                dict(sorted(Counter(str(row[7]) for row in source_rows).items())),
            )

    retained: dict[str, Any] = {"evaluated": False}
    if retained_fixture and retained_fixture.is_file():
        fixture = _read_json(retained_fixture)
        retained_checks = []
        retained_investments = {
            (int(row["year"]), str(row["technology"])): float(row["suggested_addition_mw"])
            for row in modular["investment_decisions"]
        }
        for year_text, expected in fixture.get("years", {}).items():
            year = int(year_text)
            if year not in costs:
                continue
            mapping = (
                ("total_system_cost_gbp", costs[year]["Total_System_Cost_GBP"], 0.01),
                ("cost_per_mwh_gbp", costs[year]["Cost_per_MWh_GBP"], 1e-8),
                ("total_energy_generated_mwh", costs[year]["Total_Energy_Generated_MWh"], 0.01),
                ("solar_capacity_mw", capacities[year]["Solar_Capacity_MW"], 1e-6),
                ("onshore_capacity_mw", capacities[year]["Onshore_Capacity_MW"], 1e-6),
                ("offshore_capacity_mw", capacities[year]["Offshore_Capacity_MW"], 1e-6),
                ("quarter_c_battery_capacity_mw", capacities[year]["0.25c_battery_Capacity_MW"], 1e-6),
            )
            for metric, actual, tolerance in mapping:
                retained_checks.append({
                    "year": year, "metric": metric, "actual": float(actual),
                    "expected": float(expected[metric]),
                    "absolute_difference": abs(float(actual) - float(expected[metric])),
                    "absolute_tolerance": tolerance,
                    "pass": _close(actual, expected[metric], tolerance),
                })
            for technology, metric in (
                ("0.25c_battery", "quarter_c_battery_suggested_addition_mw"),
                ("solar", "solar_suggested_addition_mw"),
                ("onshore", "onshore_suggested_addition_mw"),
                ("offshore", "offshore_suggested_addition_mw"),
            ):
                if metric not in expected:
                    continue
                actual = retained_investments.get((year, technology), 0.0)
                retained_checks.append({
                    "year": year,
                    "metric": metric,
                    "actual": actual,
                    "expected": float(expected[metric]),
                    "absolute_difference": abs(actual - float(expected[metric])),
                    "absolute_tolerance": 1e-6,
                    "pass": _close(actual, expected[metric], 1e-6),
                })
        retained = {
            "evaluated": bool(retained_checks),
            "source_run": fixture.get("source_run"),
            "checks": retained_checks,
            "passed": bool(retained_checks) and all(row["pass"] for row in retained_checks),
        }

    failed = [row for row in checks if not row["pass"]]
    retained_failed = retained.get("evaluated") and not retained.get("passed")
    retained_divergence = next(
        (row for row in retained.get("checks", []) if not row.get("pass")),
        None,
    )
    first_divergence = failed[0] if failed else retained_divergence
    if first_divergence is retained_divergence and first_divergence is not None:
        first_divergence = {
            "stage": "retained_numerical_comparison",
            **first_divergence,
        }
    return {
        "schema_version": "value.stage-parity-report/v1",
        "source": "copied VALUE project-composed session artifacts",
        "target": "VALUE v2 public contracts and durable ledgers",
        "passed": not failed,
        "contract_parity_passed": not failed,
        "retained_numerical_parity_passed": (
            retained.get("passed") if retained.get("evaluated") else None
        ),
        "release_gate_passed": (
            not failed and not retained_failed
            if retained.get("evaluated")
            else None
        ),
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "first_divergence": first_divergence,
        "checks": checks,
        "planning_evidence": planning_evidence,
        "market_evidence": market_evidence,
        "agent_economics_evidence": agent_evidence,
        "retained_numerical_comparison": retained,
    }


def write_stage_parity_report(
    output_dir: Path, *, retained_fixture: Path | None = None
) -> Path:
    report = compare_run_bundle(output_dir, retained_fixture=retained_fixture)
    path = output_dir / "parity" / "stage-parity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a completed VALUE stage transition")
    parser.add_argument("output", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = compare_run_bundle(args.output, retained_fixture=args.fixture)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "checks_passed": report["checks_passed"],
        "checks_total": report["checks_total"],
        "first_divergence": report["first_divergence"],
    }, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
