"""GBP1 doctoral before/after comparison (decision A12).

Read-only summaries of kept run outputs of the GBP1 doctoral golden project
(``tests/golden/projects/D5.json``) and of the interconnector inputs the
retained kernel sees, so that ``docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md`` can
be regenerated and checked::

    python -B scripts/gbp1_doctoral_before_after.py summarise --run LABEL OUTPUT_DIR [--run ...] [--out FILE]
    python -B scripts/gbp1_doctoral_before_after.py boundary-inputs --pack GBP1_PUBLIC1_DIR [--out FILE]

``summarise`` reads ``market/market.sqlite`` (``mode=ro``), the year results,
the cost and carbon ledgers and the validation report of each run.  Nothing
is written into a run output or a pack.

Emissions: the doctoral carbon scenario (``doctoral_reproduction_2026_07_18``)
reports no physical tCO2 (its legacy storage scalars have no declared unit),
so the summary applies the current authoritative factor set
(``value_current_authoritative_v1``) to every run's annual generation by
asset, direct operation and imports separately (no embodied lines).  The
same factors are used for every run, so differences are dispatch differences
only.

Stress events (decision A2): runs that record a ``stress_event`` table report
it; for every run the read-only energy-balance oracle
(:mod:`gridform_core.energy_balance_oracle`) gives the same per-period
shortfall (exact on a declared boundary, lower/upper bounds on a 35aadb3
ledger, which declares none).

``boundary-inputs`` compares, per kernel Connection, what the retained
kernel is fed over one 17520-period year: at 35aadb3 (another country's
files on three Connections, prices from the first CSV column, row p // 2 in
period p), with only the P6-24 clock corrected, and with the universal
reading of today (Q9/A3 and A5).
"""

from __future__ import annotations

import sys as _sys

_sys.dont_write_bytecode = True

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PERIOD_HOURS = 0.5
# Spelling of the retained kernel's Connection objects -> country.
CONNECTION_COUNTRY = {
    "Interconnect_France": "france",
    "Interconnect_Beligum": "belgium",
    "Interconnect_Netherland": "netherlands",
    "Interconnect_Norway": "norway",
    "Interconnect_Ireland": "ireland",
}
# 35aadb3: which country's files each kernel Connection read (P6-03; see
# scripts/capture_p0_5_baseline.py HEAD_KERNEL_CONNECTION_FEEDS).
HEAD_CONNECTION_FEEDS = {
    "Interconnect_France": "france",
    "Interconnect_Netherland": "belgium",
    "Interconnect_Ireland": "netherlands",
    "Interconnect_Norway": "norway",
    "Interconnect_Beligum": "ireland",
}
THERMAL = ("ccgt", "ocgt", "biomass_and_waste", "nuclear")


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _round(value: float | None, digits: int = 3) -> float | None:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return value
    return round(float(value), digits)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = min(len(ordered) - 1, max(0, int(math.ceil(fraction * len(ordered))) - 1))
    return ordered[index]


def _market(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT real_demand_mwh, clearing_price_gbp_per_mwh, blackout_mwh, curtailed_mwh, excess_mwh, "
        "vre_available_mwh, vre_accepted_mwh, import_mwh, export_mwh, storage_charge_mwh, storage_discharge_mwh "
        "FROM period_summary ORDER BY year, period"
    ).fetchall()
    demand = [float(row[0]) for row in rows]
    prices = [float(row[1]) for row in rows]
    total_demand = sum(demand)
    weighted = sum(d * p for d, p in zip(demand, prices)) / total_demand if total_demand else float("nan")
    flows: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_technology: dict[str, float] = defaultdict(float)
    for technology, flow_type, asset_id, energy in connection.execute(
        "SELECT technology, flow_type, asset_id, SUM(energy_mwh) FROM physical_dispatch GROUP BY 1, 2, 3"
    ):
        if technology == "boundary_import":
            flows["import_mwh"][CONNECTION_COUNTRY.get(asset_id, asset_id)] += float(energy)
        elif technology == "boundary_export":
            flows["export_mwh"][CONNECTION_COUNTRY.get(asset_id, "all (one aggregate export row)")] += float(energy)
        elif flow_type == "generation":
            by_technology[technology] += float(energy)
    return {
        "periods": len(rows),
        "real_demand_mwh": _round(total_demand),
        "price_gbp_per_mwh": {
            "mean": _round(sum(prices) / len(prices) if prices else float("nan"), 4),
            "demand_weighted_mean": _round(weighted, 4),
            "max": _round(max(prices), 4),
            "min": _round(min(prices), 4),
            "p99": _round(_percentile(prices, 0.99), 4),
            "periods_above_100": sum(1 for p in prices if p > 100.0),
            "periods_above_1000": sum(1 for p in prices if p > 1000.0),
        },
        "boundary": {
            "import_mwh_by_country": {k: _round(v) for k, v in sorted(flows["import_mwh"].items())},
            "import_mwh": _round(sum(float(row[7]) for row in rows)),
            "export_mwh_by_country": {k: _round(v) for k, v in sorted(flows["export_mwh"].items())},
            "export_mwh": _round(sum(float(row[8]) for row in rows)),
        },
        "generation_mwh_by_technology": {k: _round(v) for k, v in sorted(by_technology.items())},
        "recorded_blackout_mwh": _round(sum(float(row[2]) for row in rows)),
        "vre_available_mwh": _round(sum(float(row[5]) for row in rows)),
        "vre_accepted_mwh": _round(sum(float(row[6]) for row in rows)),
        "curtailed_mwh": _round(sum(float(row[3]) for row in rows)),
        "excess_mwh": _round(sum(float(row[4]) for row in rows)),
        "storage_charge_mwh": _round(sum(float(row[9]) for row in rows)),
        "storage_discharge_mwh": _round(sum(float(row[10]) for row in rows)),
    }


def _stress(output_dir: Path, connection: sqlite3.Connection) -> dict[str, Any]:
    from gridform_core.energy_balance_oracle import evaluate_run_ledger

    oracle = evaluate_run_ledger(output_dir)
    stress = oracle.get("stress") or {}
    years = stress.get("by_year") or [{}]
    result: dict[str, Any] = {
        "oracle_status": oracle.get("status"),
        "oracle_reasons": oracle.get("reasons"),
        "oracle_basis": stress.get("basis"),
        "oracle_boundary_id": stress.get("boundary_id"),
        "oracle_event_count": stress.get("event_count"),
        "oracle_stress_periods": years[0].get("stress_periods"),
        "oracle_possible_stress_periods": years[0].get("possible_stress_periods"),
        "oracle_shortfall_lower_mwh": _round(years[0].get("shortfall_lower_mwh")),
        "oracle_shortfall_upper_mwh": _round(years[0].get("shortfall_upper_mwh")),
    }
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "stress_event" in tables:
        count, periods, shortfall, recorded, hidden = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(periods), 0), COALESCE(SUM(shortfall_mwh), 0), "
            "COALESCE(SUM(recorded_unserved_mwh), 0), COALESCE(SUM(hidden_unserved_mwh), 0) FROM stress_event"
        ).fetchone()
        longest = connection.execute("SELECT COALESCE(MAX(periods), 0) FROM stress_event").fetchone()[0]
        result["ledger_stress_event"] = {
            "events": int(count), "stress_periods": int(periods), "shortfall_mwh": _round(shortfall),
            "recorded_unserved_mwh": _round(recorded), "hidden_unserved_mwh": _round(hidden),
            "longest_event_periods": int(longest),
        }
    else:
        result["ledger_stress_event"] = None
    return result


def _costs(output_dir: Path, year_result: Mapping[str, Any]) -> dict[str, Any]:
    market = year_result["market"]
    extensions = market.get("extensions") or {}
    ledger = json.loads((output_dir / "ledgers" / "annual-cost-ledger.json").read_text(encoding="utf-8"))
    year = ledger["years"][0]
    lines = {line["id"]: line for line in year["lines"]}
    headline_operation = sum(
        float(line["amount_gbp"]) for line in year["lines"]
        if line.get("included_in_cem_system_cost") and line["id"].startswith("operation.")
    )
    headline_capital = sum(
        float(line["amount_gbp"]) for line in year["lines"]
        if line.get("included_in_cem_system_cost") and not line["id"].startswith("operation.")
    )
    return {
        "cost_ledger_schema": ledger.get("schema_version"),
        "cem_system_cost_gbp": _round(year["cem_system_cost_gbp"], 2),
        "cem_system_cost_gbp_per_mwh_served": _round(year["cem_system_cost_gbp_per_mwh_served"], 4),
        "headline_operation_gbp": _round(headline_operation, 2),
        "headline_capital_gbp": _round(headline_capital, 2),
        "memo_lines_gbp": {
            line_id: _round(line["amount_gbp"], 2) for line_id, line in lines.items() if not line.get("included_in_cem_system_cost")
        },
        "market_total_system_cost_gbp": _round(market["total_system_cost_gbp"], 2),
        "market_total_operational_cost_gbp": _round(market["total_operational_cost_gbp"], 2),
        "market_total_levelized_capital_cost_gbp": _round(market["total_levelized_capital_cost_gbp"], 2),
        "operating_cost_detail_gbp": extensions.get("physical_operating_cost_detail_gbp"),
    }


def _emissions(year_result: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    from gridform_core.carbon_ledger import CURRENT_SCENARIO, build_operational_carbon_ledger

    market = year_result["market"]
    technology = {
        str(asset["asset_id"]): str(asset["technology"])
        for asset in year_result["planning_advance"]["operating_state"]["assets"]
    }
    generation = {
        asset_id: float(value)
        for asset_id, value in (market.get("generation_mwh_by_asset") or {}).items()
    }
    ledger = build_operational_carbon_ledger(
        year=int(year_result["year"]), scenario_id=CURRENT_SCENARIO,
        generation_mwh_by_asset=generation, technology_by_asset=technology,
        delivered_demand_mwh=float(market["total_demand_mwh"]),
    )
    by_technology: dict[str, float] = defaultdict(float)
    for line in ledger.get("lines") or []:
        if line.get("component") == "direct_operational" and line.get("emissions_tco2e"):
            by_technology[technology.get(line["line_id"], line["line_id"])] += float(line["emissions_tco2e"])
    components = ledger.get("components_tco2e") or {}
    run_ledger = json.loads((output_dir / "ledgers" / "annual-carbon-ledger.json").read_text(encoding="utf-8"))
    run_year = (run_ledger.get("years") or [{}])[0]
    return {
        "factor_scenario_applied": CURRENT_SCENARIO,
        "direct_operational_tco2e": _round(components.get("direct_operational"), 1),
        "imported_electricity_tco2e": _round(components.get("imported_electricity"), 1),
        "direct_operational_tco2e_by_technology": {k: _round(v, 1) for k, v in sorted(by_technology.items())},
        "run_carbon_ledger_status": run_year.get("status"),
        "run_carbon_ledger_reason": run_year.get("reason_code"),
    }


def _investment(year_result: Mapping[str, Any]) -> dict[str, Any]:
    investment = year_result["investment"]
    proposals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for proposal in investment.get("proposals") or []:
        proposals[str(proposal["technology"])] += float(proposal["capacity_mw"])
        counts[str(proposal["technology"])] += 1
    admitted: dict[str, float] = defaultdict(float)
    for project in year_result["planning_admission"].get("admitted_projects") or []:
        admitted[str(project["technology"])] += float(project["capacity_mw"])
    commissioned: dict[str, float] = defaultdict(float)
    for project in year_result["planning_advance"].get("commissioned_projects") or []:
        commissioned[str(project["technology"])] += float(project["capacity_mw"])
    opening: dict[str, float] = defaultdict(float)
    for asset in year_result["planning_advance"]["operating_state"]["assets"]:
        opening[str(asset["technology"])] += float(asset["capacity_mw"])
    closing: dict[str, float] = defaultdict(float)
    for asset in year_result["next_state"]["assets"]:
        closing[str(asset["technology"])] += float(asset["capacity_mw"])
    completion = sorted({int(p["expected_completion_year"]) for p in investment.get("proposals") or []})
    return {
        "proposal_count": len(investment.get("proposals") or []),
        "proposal_mw_by_technology": {k: _round(v) for k, v in sorted(proposals.items())},
        "proposal_count_by_technology": dict(sorted(counts.items())),
        "proposal_mw": _round(sum(proposals.values())),
        "proposal_expected_completion_years": completion,
        "admitted_mw_by_technology": {k: _round(v) for k, v in sorted(admitted.items())},
        "commissioned_in_year_mw_by_technology": {k: _round(v) for k, v in sorted(commissioned.items())},
        "commissioned_in_year_mw": _round(sum(commissioned.values())),
        "operating_capacity_change_mw": _round(sum(closing.values()) - sum(opening.values())),
        "retirements_mw": investment.get("retirements_mw") or {},
        "a4_net_revenue_recorded": "a4_net_revenue" in (investment.get("extensions") or {}),
    }


def _validation(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "validation" / "scientific-validation.json"
    if not path.is_file():
        return {"scientific_validation_status": None}
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("raw_invariants") or {}
    gate = payload.get("validation_gate") or {}
    deviations = payload.get("declared_deviations") or {}
    energy = payload.get("energy_balance") or {}
    return {
        "schema_version": payload.get("schema_version"),
        "scientific_validation_status": payload.get("scientific_validation_status"),
        "raw_invariants_status": raw.get("status"),
        "gates": gate.get("gates"),
        "unexplained_checks": deviations.get("unexplained_checks"),
        "matched_deviations": sorted({item for row in deviations.get("matched") or [] for item in row.get("deviation_ids") or []}),
        "energy_balance_envelope_lower_violations": energy.get("envelope_lower_violations"),
        "energy_balance_maximum_envelope_violation_mwh": _round(energy.get("maximum_envelope_violation_mwh")),
    }


def summarise(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    year_results = json.loads((output_dir / "year-results-v2.json").read_text(encoding="utf-8"))
    if len(year_results) != 1:
        raise SystemExit(f"{output_dir}: expected one model year, found {len(year_results)}")
    year_result = year_results[0]
    with _connect(output_dir / "market" / "market.sqlite") as connection:
        market = _market(connection)
        stress = _stress(output_dir, connection)
    return {
        "year": int(year_result["year"]),
        "market": market,
        "stress": stress,
        "costs": _costs(output_dir, year_result),
        "emissions": _emissions(year_result, output_dir),
        "investment": _investment(year_result),
        "validation": _validation(output_dir),
    }


# ------------------------------------------------------------ boundary inputs

def _feed_stats(flow: Any, price: Any, periods: int, clock: str) -> dict[str, float]:
    import numpy as np

    index = np.arange(periods)
    rows = index // 2 if clock == "stretched" else index
    flow = np.asarray(flow, dtype=float)
    price = np.asarray(price, dtype=float)
    f = flow[rows % len(flow)]
    p = price[rows % len(price)]
    positive = np.clip(f, 0.0, None)
    weighted = float((positive * p).sum() / positive.sum()) if positive.sum() > 0 else float("nan")
    return {
        "import_limit_mwh": _round(float(positive.sum()) * PERIOD_HOURS),
        "export_limit_mwh": _round(float(np.clip(-f, 0.0, None).sum()) * PERIOD_HOURS),
        "mean_price_gbp_per_mwh": _round(float(p.mean()), 4),
        "import_weighted_price_gbp_per_mwh": _round(weighted, 4),
        "zero_price_periods": int((p == 0).sum()),
    }


def boundary_inputs(pack_root: Path, periods: int = 17_520) -> dict[str, Any]:
    """What each kernel Connection is fed over ``periods`` (35aadb3, P6-24 only, today)."""

    from gridform_core.builtin.scheme_c_1000twh.kernel_boundary import from_pack
    from gridform_core.data_method import policy_for_profile
    from gridform_core.methodology import REFERENCE_PROFILE_ID

    script = ROOT / "scripts" / "capture_p0_5_baseline.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location("capture_p0_5_baseline", script)
    capture = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(capture)
    pack_root = Path(pack_root).resolve()
    manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    today = from_pack(pack_root, manifest, policy_for_profile(REFERENCE_PROFILE_ID, manifest), periods)
    result: dict[str, Any] = {"periods": periods, "connections": {}}
    for connection, feed in HEAD_CONNECTION_FEEDS.items():
        flow = capture.kernel_profile_read(capture.binding_path(pack_root, manifest, f"market.{feed}.profile"))
        price = capture.kernel_price_read(capture.binding_path(pack_root, manifest, f"market.{feed}.price"))
        country = CONNECTION_COUNTRY[connection]
        result["connections"][connection] = {
            "country": country,
            "head_35aadb3": {"feed": feed, **_feed_stats(flow, price, periods, "stretched")},
            "head_feed_period_clock": {"feed": feed, **_feed_stats(flow, price, periods, "period")},
            "universal_reading": {
                "feed": country,
                **_feed_stats(today.flow_mw[country], today.price_gbp_per_mwh[country], periods, "period"),
            },
        }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    summary = sub.add_parser("summarise")
    summary.add_argument("--run", nargs=2, action="append", metavar=("LABEL", "OUTPUT_DIR"), required=True)
    summary.add_argument("--out", type=Path)
    inputs = sub.add_parser("boundary-inputs")
    inputs.add_argument("--pack", type=Path, required=True)
    inputs.add_argument("--periods", type=int, default=17_520)
    inputs.add_argument("--out", type=Path)
    arguments = parser.parse_args(argv)
    if arguments.command == "summarise":
        payload: Any = {label: summarise(Path(directory)) for label, directory in arguments.run}
    else:
        payload = boundary_inputs(arguments.pack, arguments.periods)
    text = json.dumps(payload, indent=1, sort_keys=True, default=str)
    if arguments.out:
        arguments.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
