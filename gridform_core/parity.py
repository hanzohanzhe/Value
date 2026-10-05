"""Release-gate comparisons for a completed VALUE run bundle (stage parity v3).

The comparison is deliberately read-only.  It compares the copied VALUE
session artifacts with their public v2 contract materialisation, then checks the
durable planning and market ledgers.  It never re-runs or rewrites a fixture.

Stage parity v3 (P0-4 S2, finding P7-01):

* ``contract_parity_passed`` is the conjunction of the checks this report
  actually executed and lists in ``checks``; with no executed check it is
  ``None`` (not evaluated), never ``True``.  Every check row carries its
  ``actual``, ``expected`` and ``absolute_tolerance`` so a reader can
  recompute it (:mod:`gridform_core.scientific_validation` does).
* The energy balance is not judged here from the ledger's self-reported,
  compatibility-adjusted residual (finding P7-10): the market evidence
  delegates to the read-only oracle
  (:mod:`gridform_core.energy_balance_oracle`), whose verdict is reported with
  severity ``report`` until P0-4 S7 makes it a gate.
* :func:`build_native_parity_report` is the parity of the native public
  contract path (``application.run_project_application``), which used to
  write a literal ``passed``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


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


SCHEMA_VERSION = "value.stage-parity-report/v3"
ORACLE_ARTIFACT = "validation/energy-balance-oracle.json"
RUN_INVARIANTS_ARTIFACT = "validation/run-invariants.json"
# The core annual stages every year must complete, in this order; optional
# stages (expansion policies, network expansion) may sit between them.
CORE_ANNUAL_STAGES = (
    "planning.advance_year", "psm.run", "investment.decide",
    "planning.admit_projects", "state_transition.apply",
)
COST_CLOSURE_RELATIVE = 1e-6


def recompute_check(row: Mapping[str, Any]) -> bool | None:
    """Recompute one parity check row from its recorded values (None: malformed)."""

    if not isinstance(row, Mapping) or "actual" not in row or "expected" not in row:
        return None
    actual, expected = row["actual"], row["expected"]
    tolerance = row.get("absolute_tolerance", 0.0)
    numeric = all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in (actual, expected)
    )
    if numeric:
        if (
            isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
            or not math.isfinite(float(tolerance)) or float(tolerance) < 0
            or not math.isfinite(float(actual)) or not math.isfinite(float(expected))
        ):
            return False
        return _close(float(actual), float(expected), float(tolerance))
    return actual == expected


def _ledger_period_rows(database: Path) -> int:
    wal = database.with_name(database.name + "-wal")
    # immutable=1 would skip rows still in a write-ahead log.
    flags = "?mode=ro" if wal.is_file() and wal.stat().st_size > 0 else "?mode=ro&immutable=1"
    connection = sqlite3.connect(database.resolve().as_uri() + flags, uri=True)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM period_summary").fetchone()[0])
    finally:
        connection.close()


def oracle_report_for(output_dir: Path) -> dict[str, Any] | None:
    """The stored oracle report of a run, or a fresh read-only evaluation."""

    stored = output_dir / ORACLE_ARTIFACT
    if stored.is_file():
        try:
            value = _read_json(stored)
        except ValueError:
            value = None
        if isinstance(value, Mapping):
            return dict(value)
    from .energy_balance_oracle import evaluate_run_ledger

    return evaluate_run_ledger(output_dir)


def energy_balance_evidence(report: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compact energy-balance evidence for a parity report (severity report)."""

    if not isinstance(report, Mapping):
        return {"status": "not_evaluated", "severity": "report", "reasons": ["GF_ENERGY_BALANCE_LEDGER_NOT_RECORDED"]}
    metrics = dict(report.get("metrics") or {})
    reported = dict(metrics.get("reported") or {})
    full_node = dict(metrics.get("full_node") or {})
    return {
        "status": report.get("status"),
        "severity": "report",
        "artifact": ORACLE_ARTIFACT,
        "boundary_id": dict(report.get("boundary") or {}).get("boundary_id"),
        "reasons": list(report.get("reasons") or []),
        "periods": metrics.get("periods"),
        "maximum_absolute_full_node_residual_mwh": full_node.get("max_abs_mwh"),
        "maximum_absolute_raw_residual_mwh": reported.get("max_abs_raw_residual_mwh"),
        "compatibility_adjustment_periods": reported.get("adjusted_periods"),
        "sum_abs_compatibility_adjustment_mwh": reported.get("sum_abs_adjustment_mwh"),
    }


def _stage_order_checks(events: list[dict[str, Any]], years: list[int], scope: str) -> list[dict[str, Any]]:
    rows = []
    for year in years:
        stages = [str(event.get("stage")) for event in events if event.get("year") == year]
        if scope == "psm_only":
            observed = [stage for stage in stages if stage == "psm.run"]
            expected: list[str] = ["psm.run"]
        else:
            core = [stage for stage in stages if stage in CORE_ANNUAL_STAGES]
            # A year recomputed after a cancellation repeats its stages; the
            # last attempt (from the last planning advance) is the one that
            # produced the result.
            starts = [index for index, stage in enumerate(core) if stage == CORE_ANNUAL_STAGES[0]]
            observed = core[starts[-1]:] if starts else core
            expected = list(CORE_ANNUAL_STAGES)
        rows.append(_row("contract_lifecycle", year, "core_stage_order", observed, expected))
    return rows


def _row(stage: str, year: int | None, metric: str, actual: Any, expected: Any,
         tolerance: float = 0.0) -> dict[str, Any]:
    numeric = all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in (actual, expected)
    )
    row = {
        "stage": stage,
        "year": year,
        "metric": metric,
        "class": "contract",
        "actual": actual,
        "expected": expected,
        "absolute_difference": abs(float(actual) - float(expected)) if numeric and all(
            math.isfinite(float(value)) for value in (actual, expected)) else None,
        "absolute_tolerance": tolerance,
    }
    row["pass"] = bool(recompute_check(row))
    return row


def build_native_parity_report(
    output_dir: Path,
    *,
    year_results: list[Mapping[str, Any]],
    expected_years: list[int],
    periods_per_year: int,
    selected_psm: str,
    execution_scope: str = "annual",
    energy_balance: Mapping[str, Any] | None = None,
    run_invariants: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stage parity v3 of the native public-contract path, recomputed from artifacts.

    ``year_results`` are the typed results as written (``year-results-v2.json``
    rows; for a PSM-only run ``{"year", "market"}``).  The contract checks
    compare the typed contracts with the durable ledgers and the stage-event
    log; the energy balance and run invariants are attached as reported
    evidence and do not decide ``contract_parity_passed``.
    """

    output_dir = Path(output_dir)
    checks: list[dict[str, Any]] = []
    typed_years = sorted(int(row["year"]) for row in year_results)
    checks.append(_row("contract_lifecycle", None, "typed_result_years", typed_years, list(expected_years)))
    events = [
        row for row in (
            json.loads(line) for line in (
                (output_dir / "orchestrator-events.jsonl").read_text(encoding="utf-8").splitlines()
                if (output_dir / "orchestrator-events.jsonl").is_file() else []
            ) if line.strip()
        ) if isinstance(row, dict)
    ]
    checks.extend(_stage_order_checks(events, list(expected_years), execution_scope))

    market_db = output_dir / "market" / "market.sqlite"
    metadata_path = output_dir / "market" / "metadata.json"
    market_evidence: dict[str, Any]
    if market_db.is_file() and metadata_path.is_file():
        metadata = _read_json(metadata_path)
        row_count = _ledger_period_rows(market_db)
        checks.append(_row(
            "market_ledger", None, "period_row_count",
            row_count, int(dict(metadata.get("rows") or {}).get("period_summary", -1)),
        ))
        market_evidence = {
            "available": True,
            "periods": row_count,
            "trace_level": metadata.get("trace_level"),
            "database_artifact": "market/market.sqlite",
            "source": "sqlite_ledger",
        }
    else:
        market_evidence = {
            "available": True,
            "periods": sum(
                len(dict(row.get("market") or {}).get("period_summaries") or [])
                for row in year_results
            ),
            "database_artifact": None,
            "source": "typed_contract",
        }
    market_evidence["energy_balance"] = energy_balance_evidence(energy_balance)

    if execution_scope != "psm_only":
        cost_path = output_dir / "ledgers" / "annual-cost-ledger.json"
        cost_years = {}
        if cost_path.is_file():
            payload = _read_json(cost_path)
            cost_years = {
                int(row["year"]): row for row in payload.get("years", [])
                if isinstance(row, Mapping) and isinstance(row.get("year"), int)
            }
        checks.append(_row("cost_ledger", None, "years", sorted(cost_years), list(expected_years)))
        for year in expected_years:
            row = cost_years.get(year)
            if row is None:
                continue
            included = math.fsum(
                float(line.get("amount_gbp") or 0.0)
                for line in row.get("lines", [])
                if isinstance(line, Mapping) and line.get("included_in_cem_system_cost")
            )
            total = row.get("cem_system_cost_gbp")
            total_value = float(total) if isinstance(total, (int, float)) and not isinstance(total, bool) else math.nan
            tolerance = COST_CLOSURE_RELATIVE * max(1.0, abs(total_value)) if math.isfinite(total_value) else 0.0
            checks.append(_row("cost_ledger", year, "included_lines_equal_cem_system_cost", included, total_value, tolerance))

    failed = [row for row in checks if not row["pass"]]
    executed = bool(checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "native typed contracts, stage-event log and durable ledgers",
        "target": "VALUE v2 public contracts and durable ledgers",
        "execution_path": "native_public_contracts",
        "execution_scope": execution_scope,
        "selected_psm": selected_psm,
        "periods_per_year": int(periods_per_year),
        "passed": (not failed) if executed else None,
        "contract_parity_passed": (not failed) if executed else None,
        "retained_numerical_parity_passed": None,
        "release_gate_passed": None,
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "first_divergence": failed[0] if failed else None,
        "checks": checks,
        "market_evidence": market_evidence,
        "run_invariants": (
            {
                "status": run_invariants.get("status"),
                "severity": run_invariants.get("severity", "report"),
                "artifact": RUN_INVARIANTS_ARTIFACT,
            }
            if isinstance(run_invariants, Mapping) else {"status": "not_evaluated", "artifact": None}
        ),
        "planning_evidence": {
            "available": execution_scope != "psm_only",
            "years": len(year_results) if execution_scope != "psm_only" else 0,
            "database_artifact": "planning/project-index.sqlite" if execution_scope != "psm_only" else None,
        },
        "agent_economics_evidence": {
            "available": False,
            "reason": "Native typed investment decisions are recorded directly; the legacy investment-analysis replay table is reference-only.",
        },
    }


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
            "class": "contract",
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

    # The persisted period rows must be the rows the metadata declares.  The
    # balance itself is recomputed by the read-only oracle, never taken from
    # the self-reported (compatibility-adjusted) residual column, which is zero
    # by construction (P7-10); its verdict is reported, not gated (until S7).
    market_evidence: dict[str, Any] = {"trace_level": "off", "periods": 0}
    market_db = output_dir / "market" / "market.sqlite"
    if market_db.is_file():
        row_count = _ledger_period_rows(market_db)
        metadata = _read_json(output_dir / "market" / "metadata.json")
        check("market_ledger", None, "period_row_count", row_count, int(metadata["rows"]["period_summary"]))
        market_evidence = {
            "trace_level": metadata["trace_level"],
            "periods": row_count,
            "database_artifact": "market/market.sqlite",
            "energy_balance": energy_balance_evidence(oracle_report_for(output_dir)),
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
        "schema_version": SCHEMA_VERSION,
        "source": "copied VALUE project-composed session artifacts",
        "target": "VALUE v2 public contracts and durable ledgers",
        "passed": (not failed) if checks else None,
        "contract_parity_passed": (not failed) if checks else None,
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
    raise SystemExit(0 if report["passed"] is True else 1)


if __name__ == "__main__":
    main()
