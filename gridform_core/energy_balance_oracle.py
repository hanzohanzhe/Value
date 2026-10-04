"""Read-only, report-only energy-balance oracle for market ledgers (P0-4 S1).

The oracle recomputes the per-period energy balance of a run from its
``market.sqlite`` ledger rows alone, using the identities in
:mod:`gridform_core.energy_balance_contract`.  It never trusts the
self-reported (compatibility-adjusted) residual, never writes to the ledger
and never changes a run's status: it only produces a report.

* The database is opened with ``mode=ro&immutable=1``; the file's sha256 is
  taken before and after and both are recorded.  A non-empty ``-wal`` (or
  ``-journal``) file means the main file may not hold every committed row, so
  the verdict is ``not_evaluated``.
* Boundary resolution: ledger metadata (``energy_balance_boundary``) ->
  ``BOUNDARY_REGISTRY`` (module id, version, rule set) -> ``unknown``.
* Only a boundary *declared in the ledger metadata*, with every input it needs
  present, can yield ``passed``.  A ledger without that declaration (every
  ledger written before P0-4 S6) is checked against the necessary envelope
  only, so it is ``failed`` (envelope violated or self-report inconsistent)
  or ``not_evaluated`` - never ``passed``.
* Stress events (decision A2) are reported for every ledger: exact when the
  surplus routing is recorded, otherwise as lower/upper bounds.

CLI::

    python -B -m gridform_core.energy_balance_oracle <market.sqlite | run output dir>
        [--output report.json] [--quiet]

Exit codes: 0 passed, 1 failed, 2 not_evaluated, 3 usage or input error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import energy_balance_contract as contract

REPORT_SCHEMA_VERSION = "value.energy-balance-oracle/v1"
PASSED = "passed"
FAILED = "failed"
NOT_EVALUATED = "not_evaluated"
EXIT_CODES = {PASSED: 0, FAILED: 1, NOT_EVALUATED: 2}
EXIT_USAGE = 3

# Reason codes (stable; consumed by S2/S3 presentation and tests).
R_WAL = "GF_ENERGY_BALANCE_UNCHECKPOINTED_WAL"
R_NO_TABLE = "GF_ENERGY_BALANCE_NO_PERIOD_SUMMARY"
R_NO_ROWS = "GF_ENERGY_BALANCE_NO_PERIODS"
R_MISSING_COLUMN = "GF_ENERGY_BALANCE_MISSING_COLUMN"
R_NON_FINITE = "GF_ENERGY_BALANCE_NON_FINITE"
R_ENVELOPE = "GF_ENERGY_BALANCE_ENVELOPE_VIOLATED"
R_SELF_INCONSISTENT = "GF_LEDGER_RESIDUAL_SELF_INCONSISTENT"
R_BOUNDARY_RESIDUAL = "GF_ENERGY_BALANCE_RESIDUAL_ABOVE_TOLERANCE"
R_SURPLUS_CONSERVATION = "GF_ENERGY_BALANCE_SURPLUS_NOT_CONSERVED"
R_ADJUSTMENT_CAP = "GF_COMPAT_ADJUSTMENT_ABOVE_CAP"
R_LEGACY = "GF_ENERGY_BALANCE_LEGACY_ENVELOPE_ONLY"
R_UNKNOWN_BOUNDARY = "GF_ENERGY_BALANCE_BOUNDARY_UNKNOWN"
R_ROUTING_MISSING = "GF_ENERGY_BALANCE_SURPLUS_ROUTING_MISSING"
R_LEDGER_CHANGED = "GF_ENERGY_BALANCE_LEDGER_CHANGED_DURING_READ"
R_AMBIGUOUS_STAGE = "GF_ENERGY_BALANCE_AMBIGUOUS_PERIOD_STAGE"
FINAL_STAGE = "final_dispatch"

WORST_PERIODS = 10


class OracleInputError(ValueError):
    """The path is not a readable market ledger."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_ledger_path(path: Path) -> Path:
    path = Path(path)
    if path.is_dir():
        for candidate in (path / "market" / "market.sqlite", path / "market.sqlite"):
            if candidate.is_file():
                return candidate
        raise OracleInputError(f"no market/market.sqlite under {path}")
    if not path.is_file():
        raise OracleInputError(f"{path} does not exist")
    return path


def _side_files(path: Path) -> dict[str, int]:
    found = {}
    for suffix in ("-wal", "-journal"):
        side = path.with_name(path.name + suffix)
        if side.exists():
            found[suffix] = side.stat().st_size
    return found


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _metadata(connection: sqlite3.Connection) -> dict[str, Any]:
    try:
        rows = connection.execute("SELECT key, value FROM metadata").fetchall()
    except sqlite3.DatabaseError:
        return {}
    values: dict[str, Any] = {}
    for key, value in rows:
        try:
            values[str(key)] = json.loads(value)
        except (TypeError, ValueError):
            values[str(key)] = value
    return values


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]


def resolve_boundary(metadata: Mapping[str, Any]) -> dict[str, Any]:
    declared = metadata.get(contract.METADATA_BOUNDARY_KEY)
    rule_set = metadata.get(contract.METADATA_RULE_SET_KEY)
    module_id = metadata.get("psm_module_id")
    module_version = metadata.get("psm_module_version")
    entry = contract.registry_lookup(
        str(module_id) if module_id else None,
        str(module_version) if module_version else None,
        str(rule_set) if rule_set else None,
    )
    if declared:
        boundary_id = str(declared)
        source = "metadata"
        if boundary_id not in contract.BOUNDARIES or not contract.BOUNDARIES[boundary_id].verdict_basis:
            return {
                "boundary_id": boundary_id, "source": "metadata", "known": False,
                "tolerance_tier": contract.LP_SOLVER, "registry_entry": None,
                "module_id": module_id, "module_version": module_version, "rule_set": rule_set,
            }
    elif entry is not None:
        boundary_id = entry.boundary_id
        source = "registry"
    else:
        boundary_id = contract.UNKNOWN_BOUNDARY
        source = "unknown"
    tier = entry.tolerance_tier if entry is not None else contract.LP_SOLVER
    if source == "metadata" and entry is None:
        tier = contract.EXACT_ARITHMETIC if boundary_id == contract.DEFAULT_PSM_SURPLUS_NODE_V1 else contract.LP_SOLVER
    return {
        "boundary_id": boundary_id,
        "source": source,
        "known": boundary_id in contract.BOUNDARIES,
        "tolerance_tier": tier,
        "registry_entry": None if entry is None else {
            "module_id": entry.module_id,
            "minimum_version": entry.minimum_version,
            "maximum_version_exclusive": entry.maximum_version_exclusive,
            "rule_sets": list(entry.rule_sets),
            "boundary_id": entry.boundary_id,
            "tolerance_tier": entry.tolerance_tier,
            "legacy_raw_basis": entry.legacy_raw_basis,
        },
        "module_id": module_id,
        "module_version": module_version,
        "rule_set": rule_set,
    }


def _read_routing(connection: sqlite3.Connection) -> tuple[dict[tuple[int, int], list[contract.SurplusRoutingRow]] | None, list[str]]:
    if contract.SURPLUS_ROUTING_TABLE not in _tables(connection):
        return None, []
    columns = _columns(connection, contract.SURPLUS_ROUTING_TABLE)
    missing = [name for name in contract.SURPLUS_ROUTING_COLUMNS if name not in columns]
    if missing:
        return None, missing
    rows: dict[tuple[int, int], list[contract.SurplusRoutingRow]] = defaultdict(list)
    query = "SELECT {} FROM {}".format(
        ", ".join(contract.SURPLUS_ROUTING_COLUMNS), contract.SURPLUS_ROUTING_TABLE
    )
    for raw in connection.execute(query):
        row = contract.SurplusRoutingRow(
            int(raw[0]), int(raw[1]), str(raw[2]), *(float(value) for value in raw[3:])
        )
        rows[(row.year, row.period)].append(row)
    return dict(rows), []


class _Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, check_id: str, check_class: str, status: str, **detail: Any) -> None:
        self.items.append({"id": check_id, "class": check_class, "status": status, **detail})


def _round(value: float) -> float:
    return float(f"{value:.12g}")


def evaluate_ledger(path: Path | str) -> dict[str, Any]:
    """Evaluate one ledger and return the report (never raises on bad data)."""

    ledger_path = resolve_ledger_path(Path(path))
    sha_before = _sha256(ledger_path)
    side_files = _side_files(ledger_path)
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "contract_version": contract.CONTRACT_VERSION,
        "report_only": True,
        "ledger": {
            "path": str(ledger_path),
            "sha256_before": sha_before,
            "side_files": side_files,
        },
        "status": NOT_EVALUATED,
        "reasons": [],
        "checks": [],
        "metrics": {},
        "stress": None,
    }
    reasons: list[str] = report["reasons"]
    checks = _Checks()
    try:
        if any(size > 0 for size in side_files.values()):
            reasons.append(R_WAL)
            checks.add("ledger.checkpointed", "integrity", NOT_EVALUATED, side_files=side_files)
            return report
        try:
            connection = _connect_read_only(ledger_path)
        except sqlite3.DatabaseError as exc:
            raise OracleInputError(f"cannot open {ledger_path}: {exc}") from exc
        try:
            _evaluate(connection, report, checks)
        finally:
            connection.close()
    finally:
        report["checks"] = checks.items
        sha_after = _sha256(ledger_path)
        report["ledger"]["sha256_after"] = sha_after
        report["ledger"]["unchanged"] = sha_after == sha_before
        if sha_after != sha_before:
            reasons.append(R_LEDGER_CHANGED)
            report["status"] = NOT_EVALUATED
    return report


def _evaluate(connection: sqlite3.Connection, report: dict[str, Any], checks: _Checks) -> None:
    reasons: list[str] = report["reasons"]
    try:
        tables = _tables(connection)
    except sqlite3.DatabaseError as exc:
        raise OracleInputError(f"not a SQLite market ledger: {exc}") from exc
    metadata = _metadata(connection)
    report["ledger"]["schema_version"] = metadata.get("schema_version")
    boundary = resolve_boundary(metadata)
    report["boundary"] = boundary
    if "period_summary" not in tables:
        reasons.append(R_NO_TABLE)
        checks.add("ledger.period_summary", "integrity", NOT_EVALUATED)
        return
    columns = _columns(connection, "period_summary")
    missing = [name for name in contract.PERIOD_COLUMNS if name not in columns]
    if missing:
        reasons.append(R_MISSING_COLUMN)
        checks.add("ledger.period_columns", "integrity", NOT_EVALUATED, missing_columns=missing)
        return
    query = "SELECT {} FROM period_summary ORDER BY year, period, stage".format(", ".join(contract.PERIOD_COLUMNS))
    raw_rows = connection.execute(query).fetchall()
    if not raw_rows:
        reasons.append(R_NO_ROWS)
        checks.add("ledger.periods", "integrity", NOT_EVALUATED, periods=0)
        return

    # One balance per (year, period): when a ledger records several stages of
    # one period, only the final dispatch is the realised balance.
    by_period: dict[tuple[int, int], list[tuple]] = defaultdict(list)
    for raw in raw_rows:
        by_period[(int(raw[0]), int(raw[1]))].append(raw)
    ambiguous = []
    selected = []
    for key in sorted(by_period):
        rows = by_period[key]
        if len(rows) > 1:
            rows = [row for row in rows if str(row[2]) == FINAL_STAGE]
        if len(rows) != 1:
            ambiguous.append({"year": key[0], "period": key[1]})
            continue
        selected.append(rows[0])
    if ambiguous:
        reasons.append(R_AMBIGUOUS_STAGE)
        checks.add("ledger.period_stage", "integrity", NOT_EVALUATED,
                   periods=ambiguous[:WORST_PERIODS], count=len(ambiguous))
        return
    raw_rows = selected

    routing, routing_missing = _read_routing(connection)
    declared = boundary["source"] == "metadata" and boundary["known"]
    boundary_id = boundary["boundary_id"]
    tier = boundary["tolerance_tier"]
    needs_routing = boundary_id == contract.DEFAULT_PSM_SURPLUS_NODE_V1
    routing_available = routing is not None
    # The envelope uses the declared boundary only; registry-derived or
    # unknown boundaries get the widest (surplus-node family) envelope.
    envelope_boundary = boundary_id if declared else contract.UNKNOWN_BOUNDARY

    flows_list: list[contract.PeriodFlows] = []
    non_finite: list[dict[str, int]] = []
    for raw in raw_rows:
        values = dict(zip(contract.PERIOD_COLUMNS, raw))
        year, period = int(values["year"]), int(values["period"])
        u_out = w_in = None
        if routing_available:
            u_out, w_in = contract.surplus_terms((routing or {}).get((year, period), []))
        flows = contract.PeriodFlows(
            year=year, period=period, stage=str(values["stage"]),
            supply_mwh=float(values["accepted_supply_mwh"]),
            blackout_mwh=float(values["blackout_mwh"]),
            demand_mwh=float(values["real_demand_mwh"]),
            storage_charge_mwh=float(values["storage_charge_mwh"]),
            export_mwh=float(values["export_mwh"]),
            flexible_demand_mwh=float(values["flexible_demand_mwh"]),
            excess_mwh=float(values["excess_mwh"]),
            curtailed_mwh=float(values["curtailed_mwh"]),
            forecast_demand_mwh=float(values["forecast_demand_mwh"]),
            u_out_mwh=u_out, w_in_mwh=w_in,
            reported_raw_residual_mwh=float(values["raw_energy_balance_residual_mwh"]),
            reported_adjustment_mwh=float(values["compatibility_adjustment_mwh"]),
            reported_residual_mwh=float(values["energy_balance_residual_mwh"]),
        )
        if not flows.is_finite():
            non_finite.append({"year": year, "period": period})
            continue
        flows_list.append(flows)
    if non_finite:
        reasons.append(R_NON_FINITE)
        checks.add("period.finite", "integrity", FAILED, periods=non_finite[:WORST_PERIODS], count=len(non_finite))

    metrics: dict[str, Any] = report["metrics"]
    sum_demand = sum(item.demand_mwh for item in flows_list)
    metrics["periods"] = len(flows_list)
    metrics["years"] = sorted({item.year for item in flows_list})
    metrics["sum_demand_mwh"] = _round(sum_demand)
    metrics["sum_supply_mwh"] = _round(sum(item.supply_mwh for item in flows_list))
    metrics["sum_storage_charge_mwh"] = _round(sum(item.storage_charge_mwh for item in flows_list))
    metrics["sum_export_mwh"] = _round(sum(item.export_mwh for item in flows_list))
    metrics["sum_flexible_demand_mwh"] = _round(sum(item.flexible_demand_mwh for item in flows_list))
    metrics["sum_blackout_mwh"] = _round(sum(item.blackout_mwh for item in flows_list))
    metrics["sum_excess_mwh"] = _round(sum(item.excess_mwh for item in flows_list))
    metrics["sum_curtailed_mwh"] = _round(sum(item.curtailed_mwh for item in flows_list))

    # 1. Full-node residual and the necessary envelope.
    envelopes = [contract.check_envelope(envelope_boundary, item, tier) for item in flows_list]
    full = [result.full_node_residual_mwh for result in envelopes]
    metrics["full_node"] = _series_metrics(full, [item.demand_mwh for item in flows_list], tier)
    lower = [(item, result) for item, result in zip(flows_list, envelopes) if result.lower_violation_mwh > 0]
    upper = [(item, result) for item, result in zip(flows_list, envelopes) if result.upper_violation_mwh > 0]
    envelope_metrics = {
        "boundary_used": envelope_boundary,
        "lower_violations": len(lower),
        "upper_violations": len(upper),
        "max_lower_violation_mwh": _round(max((result.lower_violation_mwh for _, result in lower), default=0.0)),
        "max_upper_violation_mwh": _round(max((result.upper_violation_mwh for _, result in upper), default=0.0)),
        "sum_lower_violation_mwh": _round(sum(result.lower_violation_mwh for _, result in lower)),
        "sum_upper_violation_mwh": _round(sum(result.upper_violation_mwh for _, result in upper)),
    }
    violations = sorted(
        lower + upper,
        key=lambda pair: (-max(pair[1].lower_violation_mwh, pair[1].upper_violation_mwh), pair[0].year, pair[0].period),
    )
    envelope_metrics["worst_periods"] = [
        {
            "year": item.year, "period": item.period,
            "full_node_residual_mwh": _round(result.full_node_residual_mwh),
            "lower_bound_mwh": _round(result.lower_mwh), "upper_bound_mwh": _round(result.upper_mwh),
            "side": "lower" if result.lower_violation_mwh > 0 else "upper",
            "violation_mwh": _round(max(result.lower_violation_mwh, result.upper_violation_mwh)),
        }
        for item, result in violations[:WORST_PERIODS]
    ]
    metrics["envelope"] = envelope_metrics
    if lower or upper:
        reasons.append(R_ENVELOPE)
        checks.add("period.envelope", "independent", FAILED,
                   lower_violations=len(lower), upper_violations=len(upper))
    else:
        checks.add("period.envelope", "independent", NOT_EVALUATED if not declared else PASSED,
                   note="necessary condition only" if not declared else "declared boundary envelope")

    # 2. Self-report consistency of the ledger's own residual columns.
    adjusted = [item for item in flows_list if abs(item.reported_adjustment_mwh or 0.0) > 1e-9]
    sum_abs_adjustment = sum(abs(item.reported_adjustment_mwh or 0.0) for item in flows_list)
    share = (sum_abs_adjustment / sum_demand) if sum_demand > 0 else (0.0 if sum_abs_adjustment == 0 else math.inf)
    metrics["reported"] = {
        "sum_abs_raw_residual_mwh": _round(sum(abs(item.reported_raw_residual_mwh or 0.0) for item in flows_list)),
        "max_abs_raw_residual_mwh": _round(max((abs(item.reported_raw_residual_mwh or 0.0) for item in flows_list), default=0.0)),
        "sum_abs_adjustment_mwh": _round(sum_abs_adjustment),
        "adjusted_periods": len(adjusted),
        "adjusted_energy_share": _round(share) if math.isfinite(share) else None,
        "adjusted_energy_share_cap": contract.ANNUAL_ADJUSTMENT_SHARE_CAP,
        "exceeds_cap": share > contract.ANNUAL_ADJUSTMENT_SHARE_CAP,
    }
    self_inconsistent: list[dict[str, Any]] = []
    raw_basis: str | None
    if declared:
        # A ledger that declares its boundary reports raw on that boundary;
        # without the routing table it cannot be recomputed here.
        raw_basis = boundary_id if (routing_available or not needs_routing) else None
    elif boundary["registry_entry"] is not None:
        raw_basis = boundary["registry_entry"]["legacy_raw_basis"]
    else:
        raw_basis = None
    for item in flows_list:
        tol = contract.tolerance(tier, item.demand_mwh, item.supply_mwh)
        closing = (item.reported_raw_residual_mwh or 0.0) + (item.reported_adjustment_mwh or 0.0)
        recomputed_raw = contract.boundary_residual(raw_basis, item) if raw_basis else None
        problems = []
        if abs(closing - (item.reported_residual_mwh or 0.0)) > tol:
            problems.append("residual != raw + adjustment")
        if recomputed_raw is not None and abs(recomputed_raw - (item.reported_raw_residual_mwh or 0.0)) > tol:
            problems.append(f"raw residual != {raw_basis} recomputation")
        if problems:
            self_inconsistent.append({
                "year": item.year, "period": item.period, "problems": problems,
                "reported_raw_mwh": _round(item.reported_raw_residual_mwh or 0.0),
                "recomputed_raw_mwh": None if recomputed_raw is None else _round(recomputed_raw),
            })
    metrics["self_report"] = {"raw_residual_basis": raw_basis, "inconsistent_periods": len(self_inconsistent)}
    if self_inconsistent:
        reasons.append(R_SELF_INCONSISTENT)
        checks.add("ledger.self_report", "integrity", FAILED,
                   periods=self_inconsistent[:WORST_PERIODS], count=len(self_inconsistent))
    else:
        checks.add("ledger.self_report", "integrity", PASSED, raw_residual_basis=raw_basis)

    # 3. Retained-boundary decomposition (diagnostic only).
    retained = [contract.retained_residual(item) for item in flows_list]
    metrics["retained_demand_serving"] = _series_metrics(retained, [item.demand_mwh for item in flows_list], tier)

    # 4. Declared boundary residual and surplus conservation.
    boundary_evaluable = declared and (routing_available or not needs_routing)
    if declared and needs_routing and not routing_available:
        reasons.append(R_ROUTING_MISSING)
        checks.add("period.boundary_residual", "independent", NOT_EVALUATED,
                   missing_routing_columns=routing_missing or None)
    if boundary_evaluable:
        residuals = [contract.boundary_residual(boundary_id, item) for item in flows_list]
        metrics["boundary_residual"] = _series_metrics(residuals, [item.demand_mwh for item in flows_list], tier)
        above = [
            {"year": item.year, "period": item.period, "residual_mwh": _round(value)}
            for item, value in zip(flows_list, residuals)
            if abs(value) > contract.tolerance(tier, item.demand_mwh, item.supply_mwh)
        ]
        if above:
            reasons.append(R_BOUNDARY_RESIDUAL)
            checks.add("period.boundary_residual", "independent", FAILED, periods=above[:WORST_PERIODS], count=len(above))
        else:
            checks.add("period.boundary_residual", "independent", PASSED, boundary_id=boundary_id)
        if needs_routing:
            gaps = []
            for key, rows in sorted((routing or {}).items()):
                for row in rows:
                    gap = row.conservation_gap_mwh()
                    if abs(gap) > contract.tolerance(tier, row.available_mwh):
                        gaps.append({"year": key[0], "period": key[1], "source_class": row.source_class, "gap_mwh": _round(gap)})
                    if row.source_class not in contract.SURPLUS_SOURCE_CLASSES:
                        gaps.append({"year": key[0], "period": key[1], "source_class": row.source_class, "gap_mwh": None})
            if gaps:
                reasons.append(R_SURPLUS_CONSERVATION)
                checks.add("period.surplus_conservation", "independent", FAILED, periods=gaps[:WORST_PERIODS], count=len(gaps))
            else:
                checks.add("period.surplus_conservation", "independent", PASSED)
        if share > contract.ANNUAL_ADJUSTMENT_SHARE_CAP:
            reasons.append(R_ADJUSTMENT_CAP)
            checks.add("run.adjustment_share", "independent", FAILED, share=_round(share) if math.isfinite(share) else None)
        else:
            checks.add("run.adjustment_share", "independent", PASSED, share=_round(share))
    elif not declared:
        reasons.append(R_LEGACY if boundary["source"] == "registry" else R_UNKNOWN_BOUNDARY)

    # 5. Stress events (decision A2).
    report["stress"] = _stress_report(flows_list, tier, boundary_id if boundary_evaluable else None)

    hard_failures = {R_ENVELOPE, R_SELF_INCONSISTENT, R_BOUNDARY_RESIDUAL, R_SURPLUS_CONSERVATION, R_ADJUSTMENT_CAP, R_NON_FINITE}
    if any(reason in hard_failures for reason in reasons):
        report["status"] = FAILED
    elif boundary_evaluable and all(check["status"] == PASSED for check in checks.items):
        report["status"] = PASSED
    else:
        report["status"] = NOT_EVALUATED


def _series_metrics(values: Sequence[float], demand: Sequence[float], tier: str) -> dict[str, Any]:
    if not values:
        return {"periods": 0}
    above = sum(1 for value, scale in zip(values, demand) if abs(value) > contract.tolerance(tier, scale))
    index = max(range(len(values)), key=lambda position: abs(values[position]))
    return {
        "periods": len(values),
        "min_mwh": _round(min(values)),
        "max_mwh": _round(max(values)),
        "max_abs_mwh": _round(abs(values[index])),
        "sum_abs_mwh": _round(sum(abs(value) for value in values)),
        "sum_mwh": _round(sum(values)),
        "periods_above_tolerance": above,
    }


def _stress_report(flows_list: Sequence[contract.PeriodFlows], tier: str, boundary_id: str | None) -> dict[str, Any]:
    if boundary_id == contract.FULL_NODE_V1:
        estimates = [
            contract.ShortfallEstimate(item.year, item.period, value, value, item.blackout_mwh, True)
            for item in flows_list
            for value in (contract.full_node_shortfall(item),)
        ]
    else:
        estimates = [contract.period_shortfall(item) for item in flows_list]
    scale = {(item.year, item.period): max(item.demand_mwh, item.supply_mwh) for item in flows_list}
    summary = contract.stress_events(estimates, tier=tier, scale=scale)
    stressed = [item for item in estimates if item.upper_mwh > contract.tolerance(tier, scale[(item.year, item.period)])]
    return {
        "decision": "A2",
        "basis": summary.basis,
        "boundary_id": boundary_id,
        "periods_evaluated": summary.periods_evaluated,
        "stress_periods": summary.stress_periods,
        "possible_stress_periods": summary.possible_stress_periods,
        "event_count": len(summary.events),
        "shortfall_lower_mwh": _round(sum(item.lower_mwh for item in estimates)),
        "shortfall_upper_mwh": _round(sum(item.upper_mwh for item in estimates)),
        "shortfall_mwh": _round(sum(item.lower_mwh for item in estimates)) if summary.basis == "exact" else None,
        "recorded_unserved_mwh": _round(sum(item.recorded_unserved_mwh for item in estimates)),
        "by_year": [
            {"year": year, **{key: (_round(value) if isinstance(value, float) else value) for key, value in values.items()}}
            for year, values in sorted(summary.by_year.items())
        ],
        "events": [
            {
                "year": event.year, "first_period": event.first_period, "last_period": event.last_period,
                "periods": event.periods,
                "shortfall_lower_mwh": _round(event.shortfall_lower_mwh),
                "shortfall_upper_mwh": _round(event.shortfall_upper_mwh),
                "recorded_unserved_mwh": _round(event.recorded_unserved_mwh),
            }
            for event in summary.events
        ],
        "periods": [
            {
                "year": item.year, "period": item.period,
                "shortfall_lower_mwh": _round(item.lower_mwh), "shortfall_upper_mwh": _round(item.upper_mwh),
                "recorded_unserved_mwh": _round(item.recorded_unserved_mwh),
            }
            for item in stressed
        ],
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse would exit 2 (= not_evaluated)
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(
        prog="python -B -m gridform_core.energy_balance_oracle",
        description="Read-only energy-balance oracle for a VALUE market ledger (report only).",
    )
    parser.add_argument("ledger", type=Path, help="market.sqlite or a run output directory")
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    parser.add_argument("--quiet", action="store_true", help="print only the status line")
    arguments = parser.parse_args(argv)
    try:
        report = evaluate_ledger(arguments.ledger)
    except OracleInputError as exc:
        sys.stderr.write(f"energy-balance oracle: {exc}\n")
        return EXIT_USAGE
    text = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(text + "\n", encoding="utf-8")
    if arguments.quiet:
        sys.stdout.write(f"{report['status']} {' '.join(report['reasons'])}\n")
    else:
        sys.stdout.write(text + "\n")
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
