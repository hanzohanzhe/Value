"""Run-level invariants recomputed from a run's own artifacts (P0-4 S2).

Every conclusion of the scientific-validation report must trace back to a
check that was actually executed on the run (finding P7-01).  This module
holds the run-level checks; the per-period energy balance is the read-only
oracle (:mod:`gridform_core.energy_balance_oracle`), the contract parity is
:mod:`gridform_core.parity`.

Checks (each carries ``class`` and ``severity``):

* ``run.period_coverage`` (integrity): every expected year has exactly the
  expected number of periods in the market ledger (and in the typed result).
* ``run.demand_input_reconciliation`` (cross_path): the demand and forecast
  totals that the run's input factory built for each year (recorded in
  ``validation/input-tally/year-<Y>.json`` when the chronology was built) equal
  the totals the PSM wrote to its ledger and the typed result.  The retained
  kernel reads its own copy of the source series, so this compares two read
  paths of the same data.
* ``run.generation_cross_path`` (cross_path): the typed per-asset generation
  equals the per-asset physical dispatch rows of the ledger.
* ``run.state_chain`` (integrity): the state handed from year to year is the
  state the transition produced; with network expansion enabled the network
  advance sits between them and is checked on its own.

Statuses: passed, failed, not_evaluated, not_applicable.  The run status is
``failed`` when any check failed, ``passed`` only when every applicable check
passed and at least one independent or cross-path check ran, and
``not_evaluated`` otherwise (nothing executed is never evidence of success).

Severity is ``gate`` (P0-4 S7): a failed run invariant fails the run under
the production policy and is never a declared deviation of a reproduction
profile (:mod:`gridform_core.scientific_validation`).
Reading is strictly read-only: the ledger is opened ``mode=ro&immutable=1``.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import energy_balance_contract as contract

SCHEMA_VERSION = "value.run-invariants/v1"
INPUT_TALLY_SCHEMA = "value.input-tally/v1"
INPUT_TALLY_DIR = "validation/input-tally"
REPORT_ARTIFACT = "validation/run-invariants.json"

PASSED = "passed"
FAILED = "failed"
NOT_EVALUATED = "not_evaluated"
NOT_APPLICABLE = "not_applicable"

INDEPENDENT = "independent"
CROSS_PATH = "cross_path"
INTEGRITY = "integrity"
COUNTED_CLASSES = (INDEPENDENT, CROSS_PATH)

SEVERITY = "gate"
ENFORCEMENT = "gate_p0_4_s7"
FINAL_STAGE = "final_dispatch"
TOLERANCE_TIER = contract.EXACT_ARITHMETIC

R_NO_LEDGER = "GF_INVARIANT_LEDGER_NOT_RECORDED"
R_LEDGER_UNREADABLE = "GF_INVARIANT_LEDGER_UNREADABLE"
R_LEDGER_UNCHECKPOINTED = "GF_INVARIANT_LEDGER_UNCHECKPOINTED_WAL"
R_AMBIGUOUS_STAGE = "GF_INVARIANT_AMBIGUOUS_PERIOD_STAGE"
R_NO_TALLY = "GF_INVARIANT_INPUT_TALLY_MISSING"
R_DEMAND_AUTHORITY = "GF_INVARIANT_DEMAND_AUTHORITY_NOT_CHRONOLOGY"
R_NO_ASSET_DETAIL = "GF_INVARIANT_LEDGER_ASSET_DETAIL_NOT_RECORDED"
R_NO_TYPED = "GF_INVARIANT_TYPED_RESULT_MISSING"
R_NO_EVENTS = "GF_INVARIANT_STAGE_EVENTS_MISSING"
R_SINGLE_YEAR = "GF_INVARIANT_NO_YEAR_TRANSITION"

GENERATION_FLOWS = ("generation", "import", "storage_discharge")
PRIMARY_FLOWS = ("generation", "import")


def _fsum(values: Iterable[float]) -> float:
    return math.fsum(float(value) for value in values)


def _finite(value: object) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _round(value: float) -> float:
    return float(f"{float(value):.12g}")


def _canonical_hash(value: object) -> str:
    # The orchestrator's contract_hash (sorted keys, compact separators).
    from .v2.orchestrator import contract_hash

    return contract_hash(value)


# --- input tally ---------------------------------------------------------------

def input_tally(
    *,
    year: int,
    demand_mwh: Sequence[float],
    forecast_demand_mwh: Sequence[float] | None,
    source: str,
    demand_authority: str,
) -> dict[str, Any]:
    """The demand totals the input factory handed to the PSM for one year."""

    demand = [float(value) for value in demand_mwh]
    forecast = None if forecast_demand_mwh is None else [float(value) for value in forecast_demand_mwh]
    return {
        "schema_version": INPUT_TALLY_SCHEMA,
        "year": int(year),
        "periods": len(demand),
        "sum_demand_mwh": _fsum(demand),
        "sum_forecast_demand_mwh": None if forecast is None else _fsum(forecast),
        "forecast_periods": None if forecast is None else len(forecast),
        "source": source,
        "demand_authority": demand_authority,
    }


def chronology_tally(model_input: object, *, source: str, demand_authority: str) -> dict[str, Any] | None:
    """Tally of a PSMInput's chronology, or None when it carries none."""

    chronology = getattr(model_input, "chronology", None)
    if chronology is None:
        return None
    forecast = dict(getattr(chronology, "extensions", None) or {}).get("forecast_demand_mwh")
    return input_tally(
        year=int(getattr(model_input, "year")),
        demand_mwh=chronology.demand_mwh,
        forecast_demand_mwh=forecast if isinstance(forecast, (list, tuple)) else None,
        source=source,
        demand_authority=demand_authority,
    )


def record_input_tally(output_dir: Path, tally: Mapping[str, Any]) -> Path:
    from backend.lifecycle.atomic_io import atomic_write_json

    path = Path(output_dir) / INPUT_TALLY_DIR / f"year-{int(tally['year'])}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, dict(tally), indent=2, ensure_ascii=False, sort_keys=True)


def read_input_tallies(output_dir: Path) -> dict[int, dict[str, Any]]:
    folder = Path(output_dir) / INPUT_TALLY_DIR
    tallies: dict[int, dict[str, Any]] = {}
    if not folder.is_dir():
        return tallies
    for path in sorted(folder.glob("year-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, Mapping) and payload.get("schema_version") == INPUT_TALLY_SCHEMA:
            tallies[int(payload["year"])] = dict(payload)
    return tallies


# --- ledger reading --------------------------------------------------------------

class _Ledger:
    """Per-year ledger totals read once, read-only."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.reason: str | None = None
        self.periods: dict[int, int] = {}
        self.demand: dict[int, float] = {}
        self.forecast: dict[int, float] = {}
        self.ambiguous: list[dict[str, int]] = []
        self.asset_flows: dict[int, dict[str, dict[str, float]]] | None = None
        if path is None or not path.is_file():
            self.reason = R_NO_LEDGER
            return
        if any(
            path.with_name(path.name + suffix).is_file()
            and path.with_name(path.name + suffix).stat().st_size > 0
            for suffix in ("-wal", "-journal")
        ):
            # immutable=1 would ignore rows still in the write-ahead log.
            self.reason = R_LEDGER_UNCHECKPOINTED
            return
        try:
            self._read(path)
        except sqlite3.DatabaseError:
            self.reason = R_LEDGER_UNREADABLE

    def _read(self, path: Path) -> None:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "period_summary" not in tables:
                self.reason = R_NO_LEDGER
                return
            rows: dict[tuple[int, int], list[tuple[str, float, float]]] = defaultdict(list)
            for year, period, stage, demand, forecast in connection.execute(
                "SELECT year, period, stage, real_demand_mwh, forecast_demand_mwh FROM period_summary"
            ):
                rows[(int(year), int(period))].append((str(stage), float(demand), float(forecast)))
            demand_values: dict[int, list[float]] = defaultdict(list)
            forecast_values: dict[int, list[float]] = defaultdict(list)
            for key in sorted(rows):
                candidates = rows[key]
                if len(candidates) > 1:
                    candidates = [row for row in candidates if row[0] == FINAL_STAGE]
                if len(candidates) != 1:
                    self.ambiguous.append({"year": key[0], "period": key[1]})
                    continue
                demand_values[key[0]].append(candidates[0][1])
                forecast_values[key[0]].append(candidates[0][2])
            for year in demand_values:
                self.periods[year] = len(demand_values[year])
                self.demand[year] = _fsum(demand_values[year])
                self.forecast[year] = _fsum(forecast_values[year])
            if "physical_dispatch" in tables:
                flows: dict[int, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
                placeholders = ",".join("?" for _ in GENERATION_FLOWS)
                for year, asset_id, flow_type, energy in connection.execute(
                    "SELECT year, asset_id, flow_type, SUM(energy_mwh) FROM physical_dispatch "
                    f"WHERE flow_type IN ({placeholders}) GROUP BY year, asset_id, flow_type",
                    GENERATION_FLOWS,
                ):
                    flows[int(year)][str(asset_id)][str(flow_type)] = float(energy)
                self.asset_flows = {year: dict(value) for year, value in flows.items()}
        finally:
            connection.close()


# --- checks --------------------------------------------------------------------

class _Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, check_id: str, check_class: str, status: str, **detail: Any) -> None:
        self.items.append({
            "id": check_id, "class": check_class, "severity": SEVERITY, "status": status, **detail,
        })


def _close(actual: float, expected: float) -> tuple[bool, float]:
    tol = contract.tolerance(TOLERANCE_TIER, actual, expected)
    return abs(float(actual) - float(expected)) <= tol, tol


def _check_period_coverage(checks: _Checks, ledger: _Ledger, typed: Mapping[int, Mapping[str, Any]],
                           expected_years: Sequence[int], periods_per_year: int) -> None:
    for year in expected_years:
        market = dict(typed.get(year, {}).get("market") or {})
        summaries = market.get("period_summaries")
        typed_periods = len(summaries) if isinstance(summaries, list) and summaries else None
        if ledger.reason is not None and typed_periods is None:
            checks.add("run.period_coverage", INTEGRITY, NOT_EVALUATED, year=year,
                       reason_code=ledger.reason, expected=periods_per_year)
            continue
        if ledger.ambiguous:
            checks.add("run.period_coverage", INTEGRITY, NOT_EVALUATED, year=year,
                       reason_code=R_AMBIGUOUS_STAGE, ambiguous_periods=ledger.ambiguous[:10])
            continue
        observed = {}
        if ledger.reason is None:
            observed["ledger_periods"] = ledger.periods.get(year, 0)
        if typed_periods is not None:
            observed["typed_periods"] = typed_periods
        passed = all(value == periods_per_year for value in observed.values())
        checks.add("run.period_coverage", INTEGRITY, PASSED if passed else FAILED,
                   year=year, expected=periods_per_year, **observed)


def _check_demand(checks: _Checks, ledger: _Ledger, typed: Mapping[int, Mapping[str, Any]],
                  tallies: Mapping[int, Mapping[str, Any]], expected_years: Sequence[int]) -> None:
    for year in expected_years:
        tally = tallies.get(year)
        if tally is None:
            checks.add("run.demand_input_reconciliation", CROSS_PATH, NOT_EVALUATED, year=year,
                       reason_code=R_NO_TALLY)
            continue
        if tally.get("demand_authority") != "chronology":
            checks.add("run.demand_input_reconciliation", CROSS_PATH, NOT_EVALUATED, year=year,
                       reason_code=R_DEMAND_AUTHORITY, demand_authority=tally.get("demand_authority"))
            continue
        comparisons: list[dict[str, Any]] = []
        input_demand = float(tally["sum_demand_mwh"])
        input_forecast = tally.get("sum_forecast_demand_mwh")
        if ledger.reason is None and not ledger.ambiguous and year in ledger.demand:
            comparisons.append({"metric": "sum_demand_mwh", "path": "ledger.period_summary",
                                "input": input_demand, "recorded": ledger.demand[year]})
            if input_forecast is not None:
                comparisons.append({"metric": "sum_forecast_demand_mwh", "path": "ledger.period_summary",
                                    "input": float(input_forecast), "recorded": ledger.forecast[year]})
            comparisons.append({"metric": "periods", "path": "ledger.period_summary",
                                "input": int(tally["periods"]), "recorded": ledger.periods[year]})
        market = dict(typed.get(year, {}).get("market") or {})
        if _finite(market.get("total_demand_mwh")):
            comparisons.append({"metric": "sum_demand_mwh", "path": "typed.market.total_demand_mwh",
                                "input": input_demand, "recorded": float(market["total_demand_mwh"])})
        if not comparisons:
            checks.add("run.demand_input_reconciliation", CROSS_PATH, NOT_EVALUATED, year=year,
                       reason_code=ledger.reason or R_NO_TYPED)
            continue
        failed = False
        for row in comparisons:
            if row["metric"] == "periods":
                ok = row["input"] == row["recorded"]
                row["tolerance"] = 0
            else:
                ok, tol = _close(row["input"], row["recorded"])
                row["tolerance"] = tol
                row["difference"] = _round(row["recorded"] - row["input"])
            row["status"] = PASSED if ok else FAILED
            failed = failed or not ok
        checks.add("run.demand_input_reconciliation", CROSS_PATH, FAILED if failed else PASSED,
                   year=year, input_source=tally.get("source"), comparisons=comparisons)


def _check_generation(checks: _Checks, ledger: _Ledger, typed: Mapping[int, Mapping[str, Any]],
                      expected_years: Sequence[int]) -> None:
    for year in expected_years:
        market = dict(typed.get(year, {}).get("market") or {})
        by_asset = market.get("generation_mwh_by_asset")
        if not isinstance(by_asset, Mapping):
            checks.add("run.generation_cross_path", CROSS_PATH, NOT_EVALUATED, year=year, reason_code=R_NO_TYPED)
            continue
        if ledger.reason is not None or ledger.asset_flows is None:
            checks.add("run.generation_cross_path", CROSS_PATH, NOT_EVALUATED, year=year,
                       reason_code=ledger.reason or R_NO_ASSET_DETAIL)
            continue
        flows = ledger.asset_flows.get(year, {})
        typed_total = _fsum(by_asset.values())
        if not flows and abs(typed_total) > 0:
            # Summary-trace ledgers keep no per-asset rows.
            checks.add("run.generation_cross_path", CROSS_PATH, NOT_EVALUATED, year=year,
                       reason_code=R_NO_ASSET_DETAIL)
            continue
        mismatches = []
        compared = 0
        assets = set(by_asset) | {
            asset for asset, row in flows.items() if any(flow in row for flow in PRIMARY_FLOWS)
        }
        for asset in sorted(assets):
            typed_value = float(by_asset.get(asset, 0.0))
            ledger_value = _fsum(flows.get(asset, {}).values()) if asset in by_asset else _fsum(
                value for flow, value in flows.get(asset, {}).items() if flow in PRIMARY_FLOWS
            )
            ok, tol = _close(typed_value, ledger_value)
            compared += 1
            if not ok:
                mismatches.append({"asset_id": asset, "typed_mwh": _round(typed_value),
                                   "ledger_mwh": _round(ledger_value), "tolerance": tol})
        total_typed = market.get("total_generation_mwh")
        total_ok = True
        if _finite(total_typed):
            total_ok, _ = _close(float(total_typed), typed_total)
        checks.add(
            "run.generation_cross_path", CROSS_PATH, PASSED if not mismatches and total_ok else FAILED,
            year=year, assets_compared=compared, mismatches=mismatches[:20], mismatch_count=len(mismatches),
            typed_total_generation_mwh=_round(float(total_typed)) if _finite(total_typed) else None,
            typed_sum_by_asset_mwh=_round(typed_total), typed_total_consistent=total_ok,
        )


def _events_by_year(events: Sequence[Mapping[str, Any]]) -> dict[int, list[Mapping[str, Any]]]:
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        year = event.get("year")
        if isinstance(year, int) and not isinstance(year, bool):
            grouped[year].append(event)
    return grouped


def _last(events: Sequence[Mapping[str, Any]], stage: str) -> Mapping[str, Any] | None:
    for event in reversed(events):
        if event.get("stage") == stage:
            return event
    return None


def _check_state_chain(checks: _Checks, typed: Mapping[int, Mapping[str, Any]], expected_years: Sequence[int],
                       *, initial_state_sha256: str | None, network_expansion: bool,
                       events: Sequence[Mapping[str, Any]] | None) -> None:
    years = [year for year in expected_years if year in typed]
    if not years:
        checks.add("run.state_chain", INTEGRITY, NOT_EVALUATED, reason_code=R_NO_TYPED)
        return
    grouped = _events_by_year(events or [])
    links: list[dict[str, Any]] = []

    def link(kind: str, year: int, actual: object, expected: object) -> None:
        links.append({"link": kind, "year": year, "actual": actual, "expected": expected,
                      "status": PASSED if actual == expected and actual is not None else FAILED})

    previous_output: str | None = initial_state_sha256
    for year in years:
        result = typed[year]
        extensions = dict(result.get("extensions") or {})
        annual_input = extensions.get("annual_input_state_sha256")
        next_state = result.get("next_state")
        output = _canonical_hash(next_state) if isinstance(next_state, Mapping) else None
        if network_expansion:
            network = dict(extensions.get("network_expansion") or {})
            advanced_state = dict(network.get("advance") or {}).get("state")
            advanced = _canonical_hash(advanced_state) if isinstance(advanced_state, Mapping) else None
            link("network_advance_output_is_annual_input", year, advanced, annual_input)
            advance_event = _last(grouped.get(year, []), "network_expansion.advance_year")
            if previous_output is not None and advance_event is not None:
                link("previous_state_is_network_advance_input", year,
                     advance_event.get("input_state_sha256"), previous_output)
            elif previous_output is not None and events:
                link("previous_state_is_network_advance_input", year, None, previous_output)
        elif previous_output is not None:
            link("previous_state_is_annual_input", year, annual_input, previous_output)
        transition = _last(grouped.get(year, []), "state_transition.apply")
        if transition is not None:
            link("transition_event_output_is_next_state", year, transition.get("output_state_sha256"), output)
        advance = _last(grouped.get(year, []), "planning.advance_year")
        if advance is not None:
            link("planning_advance_input_is_annual_input", year, advance.get("input_state_sha256"), annual_input)
        next_year = (next_state or {}).get("year") if isinstance(next_state, Mapping) else None
        links.append({"link": "next_state_year", "year": year, "actual": next_year, "expected": year + 1,
                      "status": PASSED if next_year == year + 1 else FAILED})
        previous_output = output
    failed = [row for row in links if row["status"] == FAILED]
    detail: dict[str, Any] = {
        "network_expansion": network_expansion,
        "links_checked": len(links),
        "failed_links": failed[:20],
    }
    if not events:
        detail["reason_code"] = R_NO_EVENTS
    checks.add("run.state_chain", INTEGRITY, FAILED if failed else PASSED, **detail)


def summarise(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    applicable = [item for item in items if item.get("status") != NOT_APPLICABLE]
    counted = [item for item in applicable if item.get("class") in COUNTED_CLASSES]
    integrity = [item for item in applicable if item.get("class") == INTEGRITY]
    if any(item.get("status") == FAILED for item in applicable):
        status = FAILED
    elif counted and all(item.get("status") == PASSED for item in applicable):
        status = PASSED
    else:
        status = NOT_EVALUATED
    return {
        "status": status,
        "checks_passed": sum(item.get("status") == PASSED for item in counted),
        "checks_total": len(counted),
        "integrity_checks_passed": sum(item.get("status") == PASSED for item in integrity),
        "integrity_checks_total": len(integrity),
        "failed_checks": sorted({str(item["id"]) for item in applicable if item.get("status") == FAILED}),
        "not_evaluated_checks": sorted({str(item["id"]) for item in applicable if item.get("status") == NOT_EVALUATED}),
    }


def evaluate_run_invariants(
    output_dir: Path,
    *,
    year_results: Sequence[Mapping[str, Any]],
    expected_years: Sequence[int],
    periods_per_year: int,
    execution_scope: str = "annual",
    initial_state_sha256: str | None = None,
    network_expansion: bool = False,
    events: Sequence[Mapping[str, Any]] | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate the run-level invariants of one completed output directory.

    ``year_results`` are the typed annual results as written to
    ``year-results-v2.json`` (or, for a PSM-only run, ``{"year", "market"}``
    rows).  Nothing is written; the caller stores the report.
    """

    output_dir = Path(output_dir)
    typed = {int(row["year"]): row for row in year_results if isinstance(row, Mapping) and "year" in row}
    ledger = _Ledger(ledger_path if ledger_path is not None else output_dir / "market" / "market.sqlite")
    tallies = read_input_tallies(output_dir)
    checks = _Checks()
    _check_period_coverage(checks, ledger, typed, expected_years, periods_per_year)
    _check_demand(checks, ledger, typed, tallies, expected_years)
    _check_generation(checks, ledger, typed, expected_years)
    if execution_scope == "psm_only":
        checks.add("run.state_chain", INTEGRITY, NOT_APPLICABLE, reason_code=R_SINGLE_YEAR,
                   note="a PSM-only run has no annual state transition")
    else:
        _check_state_chain(checks, typed, expected_years, initial_state_sha256=initial_state_sha256,
                           network_expansion=network_expansion, events=events)
    summary = summarise(checks.items)
    return {
        "schema_version": SCHEMA_VERSION,
        "severity": SEVERITY,
        "enforcement": ENFORCEMENT,
        "execution_scope": execution_scope,
        "expected_years": list(expected_years),
        "periods_per_year": int(periods_per_year),
        "tolerance_tier": TOLERANCE_TIER,
        "tolerance": dict(contract.TOLERANCE_TIERS[TOLERANCE_TIER]),
        "ledger_artifact": (
            "market/market.sqlite" if ledger.reason is None else None
        ),
        **summary,
        "checks": checks.items,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not Path(path).is_file():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows
