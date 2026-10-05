"""Auditable accounting and bounded read models for zonal redispatch.

SQLite remains the authoritative store.  This module defines the scientific
identities used before rows are written and exposes read-only, paginated views.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .market_ledger import (
    ATTRIBUTION_SCHEMA_VERSIONS,
    _read_only_connection,
    market_ledger_capabilities,
    network_solver_evidence_errors,
)
from .zonal_solver_contract import (
    V3_SOLVER_CONTRACT_VERSION,
    RECORDED_REFERENCE_THRESHOLDS,
    DEFAULT_VALIDATED_CEILINGS,
    ObjectiveLockDiagnostic,
    load_solver_validation_registry,
    solver_stack_is_validated,
    solver_stack_identity,
    summarise_solver_diagnostics,
    validate_stored_lock_evidence,
)


ACCOUNTING_SCHEMA = "value.zonal-period-accounting/v1"
ANNUAL_BRIEF_SCHEMA = "value.zonal-annual-brief/v2"
LEGACY_ATTRIBUTION_REASON = (
    "legacy_contract_did_not_measure_avoided_curtailment"
)
SHADOW_VALUE_SEMANTICS = (
    "diagnostic_marginal_value_in_accepted_bid_objective_not_zonal_price_or_cash_cost"
)
# One declared reporting threshold for load shedding (P0-8 S6).  Shedding at
# or below it is numerical residue, never a reliability event or an affected
# zone; it is reported separately as numerical_residual_unserved_mwh.
LOAD_SHEDDING_REPORTING_THRESHOLD_MWH = 1e-6
# Known method defects of historical ledgers, derived when reading; stored
# values are never rewritten (P0-8 S6).
V3_LOCK_DEFECT = {
    "defect_id": "p08.zonal-v3-gbp1-lock",
    "finding_ids": ["P2-01", "F3-01", "P3-09", "R2-02", "P2-07"],
    "severity": "critical",
    "summary": (
        "Recorded under zonal solver contract v3: later lexicographic phases "
        "could spend the GBP 1 primary allowance, creating about "
        "1/(VOLL - price) MWh of spurious load shedding per redispatch period, "
        "spurious reliability events and asset-ID dependent dispatch shifts."
    ),
    "affected_outputs": [
        "reliability_event", "zone_period_summary.load_shedding_mwh",
        "physical_dispatch", "network_solver_diagnostics.validation_class",
    ],
    "remedy": "Re-run with solver contract v4 (migration recovery).",
}


def query_runtime_fallback_audit(market_dir: Path) -> dict[str, object] | None:
    """Read the per-year run-time fallback audits written beside the ledger.

    ``None`` when the Run wrote none (copperplate, or a ledger from before
    P0-8 S12; status ``not_recorded`` is for the caller to show).
    """

    paths = sorted(Path(market_dir).glob("runtime-fallback-audit-*.json"))
    if not paths:
        return None
    years = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or payload.get("schema_version") != "value.zonal-runtime-fallback-audit/v1":
            raise ValueError(f"Invalid runtime fallback audit: {path.name}")
        years.append(dict(payload))
    indicative = [
        {
            "year": int(year["year"]),
            "technology": str(row["technology"]),
            "fallback_fraction": float(row["fallback_fraction"]),
            "fallback_mw": float(row["fallback_mw"]),
            "fallback_zone_ids": list(year.get("fallback_zone_ids") or []),
        }
        for year in years
        for row in year.get("by_technology", ())
        if row.get("spatially_indicative")
    ]
    return {
        "schema_version": "value.zonal-runtime-fallback-summary/v1",
        "years": years,
        "spatially_indicative": bool(indicative),
        "spatially_indicative_technologies": indicative,
    }


def guarded_runtime_fallback_audit(market_dir: Path) -> dict[str, object] | None:
    """``query_runtime_fallback_audit`` that degrades instead of raising.

    A malformed or wrong-schema audit file must not take down the read models
    that show it (capabilities, run summary): it becomes ``status: invalid``
    with the error text, and the ledger stays readable (M2-P0-8a review).
    """

    try:
        return query_runtime_fallback_audit(market_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {
            "schema_version": "value.zonal-runtime-fallback-summary/v1",
            "status": "invalid",
            "error": str(exc),
        }


def is_reportable_shedding(value: object) -> bool:
    """True when a load-shedding quantity is above the reporting threshold."""

    return float(value) > LOAD_SHEDDING_REPORTING_THRESHOLD_MWH


def ledger_known_defects(connection: sqlite3.Connection, tables: set[str]) -> list[dict[str, object]]:
    """Known method defects of one ledger, from its recorded solver evidence."""

    defects: list[dict[str, object]] = []
    if "network_solver_diagnostics" in tables:
        row = connection.execute(
            "SELECT COUNT(*) FROM network_solver_diagnostics "
            "WHERE solver_contract_version=?",
            (V3_SOLVER_CONTRACT_VERSION,),
        ).fetchone()
        if row and int(row[0] or 0):
            defects.append({**V3_LOCK_DEFECT, "evidence_rows": int(row[0])})
    return defects


def _decoded_metadata(connection: sqlite3.Connection) -> dict[str, object]:
    rows = connection.execute("SELECT key, value FROM metadata").fetchall()
    result: dict[str, object] = {}
    for key, value in rows:
        try:
            result[str(key)] = json.loads(str(value))
        except (TypeError, json.JSONDecodeError):
            result[str(key)] = value
    return result


def build_solver_validation_summary(
    rows: Iterable[object],
    *,
    inherited: Mapping[str, object] | None = None,
    evidence_errors: Sequence[str] = (),
) -> dict[str, object]:
    """Stream annual/study status without weakening any validator."""

    validation_errors = list(dict.fromkeys(str(item) for item in evidence_errors))

    def add_validation_error(code: str, identity: tuple[object, ...]) -> None:
        if not any(item.startswith(code) for item in validation_errors):
            validation_errors.append(
                f"{code}:{':'.join(str(item) for item in identity)}"
            )

    phase_order = {
        "primary_bid_cost": 0,
        "secondary_schedule_deviation": 1,
        "physical_throughput": 2,
    }
    objective_key_by_phase = {
        "primary_bid_cost": "primary_bid_cost_gbp",
        "secondary_schedule_deviation": "secondary_schedule_deviation_mwh",
        "physical_throughput": "physical_throughput_mwh",
    }
    try:
        registry_entries = load_solver_validation_registry()
    except (OSError, ValueError):
        registry_entries = ()
    row_count = 0
    warning_periods = 0
    unvalidated_periods = 0
    maximum_ceiling_use = 0.0
    builtin_stack_validated = True
    first_payload: dict[str, object] | None = None
    earliest_stack_payload: tuple[tuple[object, ...], dict[str, object]] | None = None
    causal_payload: tuple[tuple[object, ...], dict[str, object]] | None = None
    current_group: tuple[str, int, int] | None = None
    group_count = 0
    group_phases: set[str] = set()
    group_period_ids: set[str] = set()
    group_stacks: set[tuple[object, ...]] = set()
    group_inputs: set[str] = set()
    group_warning = False
    group_unvalidated = False

    def finish_group() -> None:
        nonlocal warning_periods, unvalidated_periods
        if current_group is None:
            return
        if group_count != 3 or group_phases != set(phase_order):
            add_validation_error(
                "solver_diagnostics_incomplete_phase_group", current_group
            )
        if len(group_period_ids) != 1:
            add_validation_error(
                "solver_diagnostics_inconsistent_period_identity", current_group
            )
        if len(group_stacks) != 1:
            add_validation_error(
                "solver_diagnostics_inconsistent_stack_identity", current_group
            )
        if len(group_inputs) != 1:
            add_validation_error(
                "solver_diagnostics_inconsistent_input_identity", current_group
            )
        warning_periods += int(group_warning)
        unvalidated_periods += int(group_unvalidated)

    def diagnostics() -> Iterable[ObjectiveLockDiagnostic]:
        nonlocal row_count, maximum_ceiling_use, builtin_stack_validated
        nonlocal first_payload, earliest_stack_payload, causal_payload
        nonlocal current_group, group_count, group_phases, group_period_ids
        nonlocal group_stacks, group_inputs, group_warning, group_unvalidated
        for source_row in rows:
            if isinstance(source_row, Mapping):
                row = source_row
            elif isinstance(source_row, sqlite3.Row):
                row = {key: source_row[key] for key in source_row.keys()}
            else:
                row = vars(source_row)
            run_id = str(row["run_id"])
            year = int(row["year"])
            period = int(row["period"])
            phase_id = str(row["phase_id"])
            identity = (run_id, year, period)
            if current_group is not None and identity != current_group:
                finish_group()
                group_count = 0
                group_phases = set()
                group_period_ids = set()
                group_stacks = set()
                group_inputs = set()
                group_warning = False
                group_unvalidated = False
            current_group = identity
            group_count += 1
            group_phases.add(phase_id)
            group_period_ids.add(str(row["period_id"]))
            group_inputs.add(str(row["declared_input_sha256"]))
            stack_signature = (
                str(row["module_id"]), str(row["module_version"]),
                str(row["solver_contract_version"]), str(row["scipy_version"]),
                str(row["highs_identity"]), str(row["highs_binary_sha256"]),
                str(row["method"]), bool(row["presolve"]),
                float(row["primal_feasibility_tolerance"]),
                float(row["dual_feasibility_tolerance"]),
                row.get("ipm_optimality_tolerance"),
            )
            group_stacks.add(stack_signature)
            stored_validation_class = str(row["validation_class"])
            stored_validation = validate_stored_lock_evidence(row)
            for code in stored_validation.errors:
                add_validation_error(code, (*identity, phase_id))
            validation_class = (
                "COMPLETED_WITH_NUMERICAL_WARNING"
                if stored_validation.errors
                else stored_validation_class
            )
            group_warning = group_warning or validation_class != "GO"
            group_unvalidated = group_unvalidated or (
                validation_class == "COMPLETED_WITH_NUMERICAL_WARNING"
            )
            digest = str(row["highs_binary_sha256"])
            identity_matches_sha = str(row["highs_identity"]) == (
                f"scipy-embedded-highs:{digest}"
            )
            if not identity_matches_sha:
                add_validation_error(
                    "solver_diagnostics_identity_sha_mismatch", identity
                )
            objective_key = objective_key_by_phase.get(phase_id)
            row_is_builtin = bool(
                identity_matches_sha
                and solver_stack_is_validated(
                    registry_entries,
                    module_id=str(row["module_id"]),
                    module_version=str(row["module_version"]),
                    solver_contract_version=str(row["solver_contract_version"]),
                    scipy_version=str(row["scipy_version"]),
                    highs_binary_sha256=digest,
                    highs_identity=str(row["highs_identity"]),
                )
                and str(row["method"]) == "highs-ds"
                and bool(row["presolve"])
                and float(row["primal_feasibility_tolerance"]) == 1e-9
                and float(row["dual_feasibility_tolerance"]) == 1e-9
                and row.get("ipm_optimality_tolerance") is None
                and objective_key is not None
                and float(row["validated_ceiling"])
                == float(DEFAULT_VALIDATED_CEILINGS[objective_key])
                and float(row["absolute_ceiling"])
                == float(RECORDED_REFERENCE_THRESHOLDS[objective_key])
                and float(row["warning_ceiling"])
                == 0.1 * float(row["validated_ceiling"])
            )
            builtin_stack_validated = builtin_stack_validated and row_is_builtin
            order_key = (year, period, phase_order.get(phase_id, 99), run_id)
            causal = {
                "year": year,
                "period": period,
                "period_id": str(row["period_id"]),
                "phase_id": phase_id,
                "validation_class": validation_class,
            }
            if earliest_stack_payload is None or order_key < earliest_stack_payload[0]:
                earliest_stack_payload = (order_key, causal)
            if validation_class == "COMPLETED_WITH_NUMERICAL_WARNING" and (
                causal_payload is None or order_key < causal_payload[0]
            ):
                causal_payload = (order_key, causal)
            if first_payload is None:
                first_payload = {
                    "method": str(row["method"]),
                    "solver_contract_version": str(row["solver_contract_version"]),
                    "scipy_version": str(row["scipy_version"]),
                    "highs_identity": str(row["highs_identity"]),
                }
            ceiling_use = max(
                float(row["degradation"]), float(row["computed_tolerance"])
            ) / float(row["validated_ceiling"])
            maximum_ceiling_use = max(maximum_ceiling_use, ceiling_use)
            row_count += 1
            yield ObjectiveLockDiagnostic(
                phase_id=phase_id,
                objective_unit=str(row["objective_unit"]),
                optimum=float(row["optimum"]),
                achieved_final_value=float(row["achieved_final_value"]),
                degradation=float(row["degradation"]),
                computed_tolerance=float(row["computed_tolerance"]),
                validated_ceiling=float(row["validated_ceiling"]),
                absolute_ceiling=float(row["absolute_ceiling"]),
                nonzero_terms=int(
                    row.get("nonzero_term_count", row.get("nonzero_terms", 0))
                ),
                absolute_term_scale=float(row["absolute_term_scale"]),
                validation_class=validation_class,
                warning_fraction=(
                    float(row["warning_ceiling"])
                    / float(row["validated_ceiling"])
                ),
                error_code=(
                    str(row["error_code"]) if row.get("error_code") else None
                ),
            )
        finish_group()

    aggregate = summarise_solver_diagnostics(diagnostics())
    inherited_unvalidated = bool(
        inherited and inherited.get("solver_validated") is False
    )
    if row_count == 0:
        invalid = bool(validation_errors)
        if inherited_unvalidated:
            return {
                **dict(inherited or {}),
                "annual_status": "NOT_RECORDED",
                "solver_validated": False,
                "inherited_unvalidated": True,
                "evidence_status": "invalid" if invalid else "not_recorded",
                "evidence_errors": validation_errors,
            }
        return {
            "schema_version": "value.solver-validation-summary/v1",
            "annual_status": "NOT_RECORDED",
            "study_status": "solver_evidence_invalid" if invalid else "NOT_RECORDED",
            "solver_validated": False,
            "solver_stack_validation_status": "solver_stack_not_yet_validated",
            "inherited_unvalidated": False,
            "first_causal_period": None,
            "row_count": 0,
            "warning_periods": 0,
            "unvalidated_periods": 0,
            "maximum_validated_ceiling_use": 0.0,
            "phases": {},
            "evidence_status": "invalid" if invalid else "not_recorded",
            "evidence_errors": validation_errors,
        }
    first_causal = (
        inherited.get("first_causal_period")
        if inherited_unvalidated
        else None
    )
    if first_causal is None and causal_payload is not None:
        first_causal = causal_payload[1]
    if first_causal is None and not builtin_stack_validated:
        first_causal = {
            **dict(earliest_stack_payload[1] if earliest_stack_payload else {}),
            "validation_class": "solver_stack_not_yet_validated",
        }
    annual_status = str(aggregate["study_status"])
    own_validated = (
        unvalidated_periods == 0
        and builtin_stack_validated
        and not validation_errors
    )
    solver_validated = own_validated and not inherited_unvalidated
    prior_study_status = str(
        inherited.get("study_status") if inherited else ""
    )
    if validation_errors:
        study_status = "solver_evidence_invalid"
    elif (
        unvalidated_periods
        or prior_study_status == "COMPLETED_WITH_NUMERICAL_WARNING"
    ):
        study_status = "COMPLETED_WITH_NUMERICAL_WARNING"
    elif not solver_validated:
        study_status = "solver_stack_not_yet_validated"
    else:
        study_status = annual_status
    solver_stack_validation_status = (
        "solver_stack_not_yet_validated"
        if (
            not builtin_stack_validated
            or (
                inherited_unvalidated
                and inherited
                and inherited.get("solver_stack_validation_status")
                == "solver_stack_not_yet_validated"
            )
        )
        else "builtin_validated_baseline"
    )
    first = first_payload or {}
    return {
        "schema_version": "value.solver-validation-summary/v1",
        "annual_status": annual_status,
        "study_status": study_status,
        "solver_validated": solver_validated,
        "solver_stack_validation_status": solver_stack_validation_status,
        "inherited_unvalidated": inherited_unvalidated,
        "first_causal_period": first_causal,
        "row_count": row_count,
        "warning_periods": warning_periods,
        "unvalidated_periods": unvalidated_periods,
        "maximum_validated_ceiling_use": maximum_ceiling_use,
        "method": str(first["method"]),
        "solver_contract_version": str(first["solver_contract_version"]),
        "scipy_version": str(first["scipy_version"]),
        "highs_identity": str(first["highs_identity"]),
        "phases": dict(aggregate["phases"]),
        "detail_view": "solver-diagnostics",
        "evidence_status": "invalid" if validation_errors else "valid",
        "evidence_errors": validation_errors,
    }


def query_solver_validation_summary(
    database: Path,
    *,
    year: int | None = None,
    inherited: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    """Return the compact status from authoritative v7 rows, if present."""

    with _read_only_connection(database) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='network_solver_diagnostics'"
        ).fetchone()
        if table is None:
            return None
        evidence_errors = network_solver_evidence_errors(connection, year=year)
        where = "WHERE year=?" if year is not None else ""
        values: tuple[object, ...] = (year,) if year is not None else ()
        rows = connection.execute(
            "SELECT * FROM network_solver_diagnostics "
            f"{where} ORDER BY run_id, year, period, CASE phase_id "
            "WHEN 'primary_bid_cost' THEN 0 "
            "WHEN 'secondary_schedule_deviation' THEN 1 "
            "WHEN 'physical_throughput' THEN 2 ELSE 3 END",
            values,
        )
        summary = build_solver_validation_summary(
            rows,
            inherited=inherited,
            evidence_errors=evidence_errors,
        )
    return summary if summary["row_count"] or evidence_errors else None


def zonal_workspace_capabilities(database: Path) -> dict[str, object]:
    """Describe the bounded Network & redispatch read model."""

    ledger_capabilities = market_ledger_capabilities(database)
    ledger_schema_version = str(ledger_capabilities["ledger_schema_version"])
    with _read_only_connection(database) as connection:
        metadata = _decoded_metadata(connection)
        tables = {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        period_table = (
            "zonal_period_accounting"
            if ledger_schema_version in ATTRIBUTION_SCHEMA_VERSIONS
            else "zonal_period_summary"
        )
        years = [
            int(row[0]) for row in connection.execute(
                f"SELECT DISTINCT year FROM {period_table} ORDER BY year"
            )
        ] if period_table in tables else []
        row_counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "zonal_period_summary", "zonal_period_accounting",
                "vre_curtailment_period", "vre_curtailment_detail",
                "zone_period_summary",
                "boundary_period_summary", "zonal_resource_dispatch",
                "redispatch_settlement", "reliability_event",
                "solver_declaration_link",
                "network_solver_diagnostics",
                "zonal_demand_alignment",
            )
            if table in tables
        }
        demand_alignment: dict[str, object] | None = None
        if "zonal_demand_alignment" in tables:
            alignment_row = connection.execute("""
                SELECT COUNT(*) AS period_count,
                    MIN(demand_mode) AS minimum_mode,
                    MAX(demand_mode) AS maximum_mode,
                    SUM(research_real_demand_mwh) AS research_real_demand_mwh,
                    SUM(research_forecast_demand_mwh) AS research_forecast_demand_mwh,
                    SUM(network_national_demand_mwh) AS network_national_demand_mwh,
                    SUM(aligned_zonal_total_mwh) AS aligned_zonal_total_mwh,
                    MIN(scale_factor) AS scale_factor_min,
                    MAX(scale_factor) AS scale_factor_max,
                    AVG(scale_factor) AS scale_factor_mean,
                    MAX(ABS(conservation_residual_mwh))
                        AS maximum_absolute_conservation_residual_mwh
                FROM zonal_demand_alignment
            """).fetchone()
            if alignment_row and int(alignment_row[0] or 0):
                minimum_mode, maximum_mode = str(alignment_row[1]), str(alignment_row[2])
                demand_alignment = {
                    "mode": minimum_mode if minimum_mode == maximum_mode else "mixed_invalid",
                    "period_count": int(alignment_row[0]),
                    "research_real_demand_mwh": float(alignment_row[3]),
                    "research_forecast_demand_mwh": float(alignment_row[4]),
                    "network_national_demand_mwh": float(alignment_row[5]),
                    "aligned_zonal_total_mwh": float(alignment_row[6]),
                    "scale_factor_min": float(alignment_row[7]),
                    "scale_factor_max": float(alignment_row[8]),
                    "scale_factor_mean": float(alignment_row[9]),
                    "maximum_absolute_conservation_residual_mwh": float(
                        alignment_row[10]
                    ),
                    "detail_location": "market.sqlite:zonal_demand_alignment",
                }
        known_defects = ledger_known_defects(connection, tables)
    trace_level = str(metadata.get("trace_level") or "off")
    return {
        "schema_version": "value.zonal-workspace-capabilities/v1",
        "ledger_schema_version": ledger_schema_version,
        "attribution_status": ledger_capabilities["attribution_status"],
        "redispatch_avoided_curtailment_available": ledger_capabilities[
            "redispatch_avoided_curtailment_available"
        ],
        "trace_level": trace_level,
        "years": years,
        "network_pack_id": str(metadata.get("network_pack_id") or ""),
        "data_pack_id": str(metadata.get("data_pack_id") or ""),
        "module_ids": list(metadata.get("module_ids") or []),
        "period_hours": float(metadata.get("period_hours") or 0.5),
        "available_views": [
            view for view, table in (
                ("period", period_table),
                ("curtailment", "vre_curtailment_period"),
                ("curtailment-detail", "vre_curtailment_detail"),
                ("zone", "zone_period_summary"),
                ("boundary", "boundary_period_summary"),
                ("resource", "zonal_resource_dispatch"),
                ("agent", "redispatch_settlement"),
                ("reliability", "reliability_event"),
                ("solver", "solver_declaration_link"),
                ("solver-diagnostics", "network_solver_diagnostics"),
            )
            if table in tables
        ],
        "row_counts": row_counts,
        "solver_validation_summary": query_solver_validation_summary(database),
        "demand_alignment": demand_alignment,
        "bid_replay_available": trace_level == "full",
        "network_semantics": str(
            metadata.get("network_semantics")
            or "lossless_computational_transport_with_etys_cutsets"
        ),
        "boundary_value_semantics": SHADOW_VALUE_SEMANTICS,
        "reliability_semantics": "observed_chronology_not_statistical_lole",
        "load_shedding_reporting_threshold_mwh": LOAD_SHEDDING_REPORTING_THRESHOLD_MWH,
        "known_defects": known_defects,
        "runtime_fallback_audit": guarded_runtime_fallback_audit(Path(database).parent),
        "security_scope": "not_a_security_analysis",
        "unsupported_scope": [
            "AC_power_flow", "voltage_security", "contingency_security", "dynamic_stability"
        ],
    }


def zonal_year_bounds(database: Path) -> dict[int, tuple[int, int, int]]:
    """``{year: (first, last, distinct periods)}`` of the zonal accounting table (P0-9 S5)."""

    ledger_schema_version = str(market_ledger_capabilities(database)["ledger_schema_version"])
    period_table = "zonal_period_accounting" if ledger_schema_version in ATTRIBUTION_SCHEMA_VERSIONS else "zonal_period_summary"
    with _read_only_connection(database) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if period_table not in tables:
            return {}
        rows = connection.execute(
            f"SELECT year, MIN(period), MAX(period), COUNT(DISTINCT period) FROM {period_table} GROUP BY year ORDER BY year"
        ).fetchall()
    return {int(year): (int(first), int(last), int(count)) for year, first, last, count in rows}


def query_zonal_annual_brief(database: Path) -> dict[str, object]:
    """Return annual scientific totals plus congestion and reliability counts."""

    ledger_capabilities = market_ledger_capabilities(database)
    ledger_schema_version = str(ledger_capabilities["ledger_schema_version"])
    is_v6 = ledger_schema_version in ATTRIBUTION_SCHEMA_VERSIONS
    period_table = "zonal_period_accounting" if is_v6 else "zonal_period_summary"
    with _read_only_connection(database) as connection:
        connection.row_factory = sqlite3.Row
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if period_table not in tables:
            base: list[dict[str, object]] = []
        else:
            base = [dict(row) for row in connection.execute(f"""
                SELECT year,
                    COUNT(*) AS period_count,
                    SUM(system_resource_cost_gbp) AS system_resource_cost_gbp,
                    SUM(network_constraint_cost_gbp) AS network_constraint_cost_gbp,
                    SUM(national_settlement_gbp) AS national_settlement_gbp,
                    SUM(redispatch_settlement_gbp) AS redispatch_settlement_gbp,
                    SUM(policy_transfer_gbp) AS policy_transfer_gbp,
                    SUM(forecast_error_cost_gbp) AS forecast_error_cost_gbp,
                    SUM(total_deviation_cost_gbp) AS total_deviation_cost_gbp,
                    SUM(blackout_mwh) AS unserved_energy_mwh
                FROM {period_table} GROUP BY year ORDER BY year
            """).fetchall()]

        curtailment_by_year: dict[int, dict[str, object]] = {}
        detail_by_year: dict[int, list[dict[str, object]]] = {}
        technology_by_year: dict[int, list[dict[str, object]]] = {}
        accounting_period_identities: set[tuple[int, int, str]] = set()
        attribution_period_identities: set[tuple[int, int, str]] = set()
        complete_period_sets_match = True
        if is_v6 and "vre_curtailment_period" in tables:
            for row in connection.execute(
                "SELECT year, period, period_id FROM zonal_period_accounting "
                "ORDER BY year, period, period_id"
            ):
                accounting_period_identities.add(
                    (int(row[0]), int(row[1]), str(row[2]))
                )
            for row in connection.execute(
                "SELECT year, period, period_id FROM vre_curtailment_period "
                "ORDER BY year, period, period_id"
            ):
                attribution_period_identities.add(
                    (int(row[0]), int(row[1]), str(row[2]))
                )
            complete_period_sets_match = (
                accounting_period_identities == attribution_period_identities
            )
            for row in connection.execute("""
                SELECT year,
                    COUNT(*) AS period_count,
                    SUM(realised_available_vre_mwh) AS available_mwh,
                    SUM(economic_curtailment_mwh) AS economic_mwh,
                    SUM(forecast_added_curtailment_mwh) AS forecast_added_mwh,
                    SUM(forecast_avoided_curtailment_mwh) AS forecast_avoided_mwh,
                    SUM(redispatch_added_curtailment_mwh) AS redispatch_added_mwh,
                    SUM(redispatch_avoided_curtailment_mwh) AS redispatch_avoided_mwh,
                    SUM(redispatch_net_impact_mwh) AS redispatch_net_mwh,
                    SUM(total_curtailment_mwh) AS total_mwh,
                    MAX(ABS(identity_residual_mwh)) AS maximum_absolute_residual_mwh,
                    SUM(validation_tolerance_mwh) AS aggregate_tolerance_mwh,
                    COUNT(DISTINCT accounting_status) AS status_count,
                    MIN(accounting_status) AS minimum_status,
                    COUNT(DISTINCT attribution_method_id) AS method_count,
                    MIN(attribution_method_id) AS attribution_method_id
                FROM vre_curtailment_period GROUP BY year ORDER BY year
            """).fetchall():
                item = dict(row)
                year = int(item.pop("year"))
                available = float(item["available_mwh"] or 0.0)
                total = float(item["total_mwh"] or 0.0)
                status_count = int(item.pop("status_count"))
                status = str(item.pop("minimum_status"))
                method_count = int(item.pop("method_count"))
                if not complete_period_sets_match:
                    item["attribution_status"] = "incomplete"
                    item["reason_code"] = "attribution_period_set_incomplete"
                elif status_count == 1 and status == "reconciled" and method_count == 1:
                    item["attribution_status"] = "reconciled"
                    item["reason_code"] = None
                else:
                    item["attribution_status"] = "invalid"
                    item["reason_code"] = "attribution_period_status_invalid"
                item["rate"] = total / available if available > 0 else 0.0
                curtailment_by_year[year] = item
            if "vre_curtailment_detail" in tables:
                for row in connection.execute("""
                    SELECT year, zone_id, technology,
                        SUM(realised_available_vre_mwh) AS available_mwh,
                        SUM(economic_curtailment_mwh) AS economic_mwh,
                        SUM(forecast_added_curtailment_mwh) AS forecast_added_mwh,
                        SUM(forecast_avoided_curtailment_mwh) AS forecast_avoided_mwh,
                        SUM(redispatch_added_curtailment_mwh) AS redispatch_added_mwh,
                        SUM(redispatch_avoided_curtailment_mwh) AS redispatch_avoided_mwh,
                        SUM(redispatch_net_impact_mwh) AS redispatch_net_mwh,
                        SUM(total_curtailment_mwh) AS total_mwh
                    FROM vre_curtailment_detail
                    GROUP BY year, zone_id, technology
                    ORDER BY year, zone_id, technology
                """).fetchall():
                    item = dict(row)
                    detail_by_year.setdefault(int(item["year"]), []).append(item)
                for row in connection.execute("""
                    SELECT year, technology,
                        SUM(realised_available_vre_mwh) AS available_mwh,
                        SUM(economic_curtailment_mwh) AS economic_mwh,
                        SUM(forecast_added_curtailment_mwh) AS forecast_added_mwh,
                        SUM(forecast_avoided_curtailment_mwh) AS forecast_avoided_mwh,
                        SUM(redispatch_added_curtailment_mwh) AS redispatch_added_mwh,
                        SUM(redispatch_avoided_curtailment_mwh) AS redispatch_avoided_mwh,
                        SUM(redispatch_net_impact_mwh) AS redispatch_net_mwh,
                        SUM(total_curtailment_mwh) AS total_mwh
                    FROM vre_curtailment_detail
                    GROUP BY year, technology
                    ORDER BY year, technology
                """).fetchall():
                    item = dict(row)
                    technology_by_year.setdefault(int(item["year"]), []).append(item)

        congestion = {
            int(row["year"]): dict(row) for row in connection.execute("""
                SELECT year,
                    SUM(CASE WHEN utilisation_fraction >= 0.999999 THEN 1 ELSE 0 END)
                        AS congested_boundary_periods,
                    MAX(utilisation_fraction) AS maximum_boundary_utilisation_fraction
                FROM boundary_period_summary GROUP BY year
            """).fetchall()
        } if "boundary_period_summary" in tables else {}
        reliability = {
            int(row["year"]): dict(row) for row in connection.execute("""
                SELECT year,
                    SUM(event_duration_hours) AS observed_loss_of_load_hours,
                    COUNT(*) AS observed_loss_of_load_events
                FROM reliability_event GROUP BY year
            """).fetchall()
        } if "reliability_event" in tables else {}
        affected = {
            int(row["year"]): int(row["zones"])
            for row in connection.execute("""
                SELECT year, COUNT(DISTINCT zone_id) AS zones
                FROM zone_period_summary
                WHERE load_shedding_mwh > ? GROUP BY year
            """, (LOAD_SHEDDING_REPORTING_THRESHOLD_MWH,)).fetchall()
        } if "zone_period_summary" in tables else {}
        residual_shedding = {
            int(row["year"]): float(row["residual"] or 0.0)
            for row in connection.execute("""
                SELECT year, SUM(load_shedding_mwh) AS residual
                FROM zone_period_summary
                WHERE load_shedding_mwh > 0 AND load_shedding_mwh <= ?
                GROUP BY year
            """, (LOAD_SHEDDING_REPORTING_THRESHOLD_MWH,)).fetchall()
        } if "zone_period_summary" in tables else {}
        known_defects = ledger_known_defects(connection, tables)
    if is_v6:
        recorded_years = {int(row["year"]) for row in base}
        evidence_years = {
            identity[0]
            for identity in accounting_period_identities
            | attribution_period_identities
        }
        for orphan_year in sorted(evidence_years.difference(recorded_years)):
            base.append({
                "year": orphan_year,
                "period_count": 0,
                "system_resource_cost_gbp": None,
                "network_constraint_cost_gbp": None,
                "national_settlement_gbp": None,
                "redispatch_settlement_gbp": None,
                "policy_transfer_gbp": None,
                "forecast_error_cost_gbp": None,
                "total_deviation_cost_gbp": None,
                "unserved_energy_mwh": None,
            })
        base.sort(key=lambda row: int(row["year"]))
    years = []
    inherited_solver_summary: dict[str, object] | None = None
    for row in base:
        year = int(row["year"])
        row.update(congestion.get(year, {
            "congested_boundary_periods": 0,
            "maximum_boundary_utilisation_fraction": 0.0,
        }))
        row.update(reliability.get(year, {
            "observed_loss_of_load_hours": 0.0,
            "observed_loss_of_load_events": 0,
        }))
        row["affected_load_shedding_zones"] = affected.get(year, 0)
        row["numerical_residual_unserved_mwh"] = residual_shedding.get(year, 0.0)
        year_solver_summary = query_solver_validation_summary(
            database,
            year=year,
            inherited=inherited_solver_summary,
        )
        if year_solver_summary is not None:
            inherited_solver_summary = year_solver_summary
            row["solver_validation_summary"] = inherited_solver_summary
        if is_v6:
            attribution = curtailment_by_year.get(year)
            if attribution is None:
                attribution = {
                    "attribution_status": (
                        "incomplete"
                        if not complete_period_sets_match
                        else "not_recorded"
                    ),
                    "reason_code": (
                        "attribution_period_set_incomplete"
                        if not complete_period_sets_match
                        else "attribution_evidence_not_recorded"
                    ),
                    "period_count": 0,
                    "available_mwh": None,
                    "economic_mwh": None,
                    "forecast_added_mwh": None,
                    "forecast_avoided_mwh": None,
                    "redispatch_added_mwh": None,
                    "redispatch_avoided_mwh": None,
                    "redispatch_net_mwh": None,
                    "total_mwh": None,
                    "rate": None,
                    "maximum_absolute_residual_mwh": None,
                    "aggregate_tolerance_mwh": None,
                    "attribution_method_id": None,
                }
            attribution["by_zone_technology"] = detail_by_year.get(year, [])
            attribution["by_technology"] = technology_by_year.get(year, [])
            row["vre_curtailment"] = attribution
        else:
            row["vre_curtailment"] = {
                "attribution_status": "legacy_partial",
                "reason_code": LEGACY_ATTRIBUTION_REASON,
                "available_mwh": None,
                "economic_mwh": None,
                "forecast_added_mwh": None,
                "forecast_avoided_mwh": None,
                "redispatch_added_mwh": None,
                "redispatch_avoided_mwh": None,
                "redispatch_net_mwh": None,
                "total_mwh": row.get("total_curtailment_vre_mwh"),
                "rate": None,
                "by_zone_technology": [],
                "by_technology": [],
            }
            # Preserve historical values under their original names without
            # relabelling them as v2 counterfactual quantities.
            if period_table in tables:
                with _read_only_connection(database) as legacy_connection:
                    legacy_connection.row_factory = sqlite3.Row
                    legacy = legacy_connection.execute("""
                        SELECT
                            SUM(economic_ahead_unused_vre_mwh) AS economic_ahead_unused_vre_mwh,
                            SUM(realised_availability_change_vre_mwh) AS realised_availability_change_vre_mwh,
                            SUM(network_added_curtailment_vre_mwh) AS network_added_curtailment_vre_mwh,
                            SUM(total_curtailment_vre_mwh) AS total_curtailment_vre_mwh
                        FROM zonal_period_summary WHERE year=?
                    """, (year,)).fetchone()
                legacy_values = dict(legacy) if legacy is not None else {}
                row["vre_curtailment"]["legacy_measurements"] = legacy_values
                row["vre_curtailment"]["total_mwh"] = legacy_values.get(
                    "total_curtailment_vre_mwh"
                )
        years.append(row)
    return {
        "schema_version": ANNUAL_BRIEF_SCHEMA,
        "ledger_schema_version": ledger_schema_version,
        "years": years,
        "solver_validation_summary": query_solver_validation_summary(database),
        "cost_semantics": {
            "system_resource_cost": "final physical resource cost",
            "settlements": "payments kept outside system resource cost",
            "constraint_resource_cost": "matched zonal minus realised copperplate physical cost",
            "boundary_shadow_value": SHADOW_VALUE_SEMANTICS,
        },
        "reliability_semantics": "observed_chronology_not_statistical_lole",
        "load_shedding_reporting_threshold_mwh": LOAD_SHEDDING_REPORTING_THRESHOLD_MWH,
        "known_defects": known_defects,
        "security_scope": "not_a_security_analysis",
    }


def _finite(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if isinstance(value, bool) or not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _nonnegative(value: object, label: str) -> float:
    result = _finite(value, label)
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


@dataclass(frozen=True)
class ZonalPeriodAccounting:
    year: int
    period: int
    period_id: str
    system_resource_cost_gbp: float
    transmission_constraint_resource_cost_gbp: float
    national_settlement_gbp: float
    redispatch_settlement_gbp: float
    policy_transfer_gbp: float
    boundary_shadow_value_gbp_per_mwh: Mapping[str, float]
    perfect_forecast_resource_cost_gbp: float
    realised_copperplate_resource_cost_gbp: float
    zonal_resource_cost_gbp: float
    forecast_error_cost_gbp: float
    total_deviation_cost_gbp: float
    blackout_mwh: float
    counterfactual_realised_input_sha256: str
    accounting_status: str
    boundary_shadow_value_semantics: str = SHADOW_VALUE_SEMANTICS
    schema_version: str = ACCOUNTING_SCHEMA


def build_zonal_period_accounting(
    *,
    year: int,
    period: int,
    period_id: str,
    realised_input_sha256: str,
    perfect_forecast_resource_cost_gbp: float,
    realised_copperplate_resource_cost_gbp: float,
    zonal_resource_cost_gbp: float,
    ahead_settlement_mwh_by_asset: Mapping[str, float],
    national_clearing_price_gbp_per_mwh: float,
    redispatch_cashflow_gbp_by_agent: Mapping[str, float],
    policy_transfer_gbp: float,
    boundary_shadow_value_gbp_per_mwh: Mapping[str, float],
    blackout_mwh: float,
    tolerance: float = 1e-7,
) -> ZonalPeriodAccounting:
    """Build cost, settlement and reliability counterfactual identities.

    The three physical-cost cases share ``realised_input_sha256``.  Settlement
    transfers are deliberately not added to physical resource cost.  VRE
    curtailment is reconciled independently by the v2 attribution component.
    """

    if len(realised_input_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in realised_input_sha256
    ):
        raise ValueError("realised_input_sha256 must be a lowercase SHA-256")
    case_1 = _nonnegative(
        perfect_forecast_resource_cost_gbp,
        "perfect-forecast copperplate resource cost",
    )
    case_2 = _nonnegative(
        realised_copperplate_resource_cost_gbp,
        "forecast-schedule realised copperplate resource cost",
    )
    case_3 = _nonnegative(zonal_resource_cost_gbp, "zonal resource cost")
    clearing_price = _finite(
        national_clearing_price_gbp_per_mwh, "national clearing price"
    )
    ahead_volume = sum(
        _finite(value, f"ahead settlement MWh for {asset}")
        for asset, value in ahead_settlement_mwh_by_asset.items()
    )
    national_settlement = ahead_volume * clearing_price
    redispatch_settlement = sum(
        _finite(value, f"redispatch cashflow for {agent}")
        for agent, value in redispatch_cashflow_gbp_by_agent.items()
    )
    policy = _finite(policy_transfer_gbp, "policy transfer")
    shadow_values = {
        str(boundary): _finite(value, f"boundary shadow value {boundary}")
        for boundary, value in boundary_shadow_value_gbp_per_mwh.items()
    }
    forecast_error = case_2 - case_1
    constraint_cost = case_3 - case_2
    total_deviation = case_3 - case_1
    algebra_residual = forecast_error + constraint_cost - total_deviation
    status = "reconciled" if abs(algebra_residual) <= tolerance else "failed"
    if status != "reconciled":
        raise ValueError("Counterfactual cost algebra does not reconcile")
    return ZonalPeriodAccounting(
        year=int(year),
        period=int(period),
        period_id=str(period_id),
        system_resource_cost_gbp=case_3,
        transmission_constraint_resource_cost_gbp=constraint_cost,
        national_settlement_gbp=national_settlement,
        redispatch_settlement_gbp=redispatch_settlement,
        policy_transfer_gbp=policy,
        boundary_shadow_value_gbp_per_mwh=shadow_values,
        perfect_forecast_resource_cost_gbp=case_1,
        realised_copperplate_resource_cost_gbp=case_2,
        zonal_resource_cost_gbp=case_3,
        forecast_error_cost_gbp=forecast_error,
        total_deviation_cost_gbp=total_deviation,
        blackout_mwh=_nonnegative(blackout_mwh, "blackout MWh"),
        counterfactual_realised_input_sha256=realised_input_sha256,
        accounting_status=status,
    )


def build_reliability_events(
    period_rows: Sequence[Mapping[str, object]], *, period_hours: float
) -> tuple[object, ...]:
    """Collapse observed consecutive load-shedding periods into events.

    The return annotation avoids a module import cycle; concrete rows are
    ``market_ledger.ReliabilityEventRow`` instances.
    """

    from .market_ledger import ReliabilityEventRow

    duration = _nonnegative(period_hours, "period_hours")
    if duration <= 0:
        raise ValueError("period_hours must be positive")
    ordered = sorted(period_rows, key=lambda row: (int(row["year"]), int(row["period"])))
    events: list[ReliabilityEventRow] = []
    active: list[Mapping[str, object]] = []

    def finish(rows: Sequence[Mapping[str, object]]) -> None:
        if not rows:
            return
        affected: set[str] = set()
        period_deficits: list[float] = []
        for row in rows:
            raw = row.get("load_shedding_mwh_by_zone") or {}
            if not isinstance(raw, Mapping):
                raise ValueError("load_shedding_mwh_by_zone must be an object")
            # Validate every recorded value before the reporting threshold
            # filter, so negative or non-finite shedding still fails closed.
            checked = {
                str(zone): _nonnegative(value, f"load shedding in {zone}")
                for zone, value in raw.items()
            }
            deficits = {
                zone: value
                for zone, value in checked.items()
                if is_reportable_shedding(value)
            }
            affected.update(deficits)
            period_deficits.append(sum(deficits.values()))
        year = int(rows[0]["year"])
        start = int(rows[0]["period"])
        end = int(rows[-1]["period"])
        events.append(ReliabilityEventRow(
            event_id=f"observed-{year}-{start}-{end}",
            year=year,
            start_period=start,
            end_period=end,
            observed_half_hours=len(rows),
            event_duration_hours=len(rows) * duration,
            unserved_mwh=sum(period_deficits),
            affected_zones_json=json.dumps(sorted(affected), separators=(",", ":")),
            maximum_deficit_mwh=max(period_deficits),
            metric_semantics="observed_loss_of_load_chronology_not_statistical_lole",
        ))

    previous: tuple[int, int] | None = None
    for row in ordered:
        year, period = int(row["year"]), int(row["period"])
        raw = row.get("load_shedding_mwh_by_zone") or {}
        if not isinstance(raw, Mapping):
            raise ValueError("load_shedding_mwh_by_zone must be an object")
        checked = [_nonnegative(value, "load shedding") for value in raw.values()]
        total = sum(value for value in checked if is_reportable_shedding(value))
        consecutive = previous is not None and previous == (year, period - 1)
        if total > 0:
            if active and not consecutive:
                finish(active)
                active = []
            active.append(row)
        elif active:
            finish(active)
            active = []
        previous = (year, period)
    finish(active)
    return tuple(events)


_VIEW_TABLE = {
    "zone": "zone_period_summary",
    "boundary": "boundary_period_summary",
    "agent": "redispatch_settlement",
    "reliability": "reliability_event",
    "resource": "zonal_resource_dispatch",
    "solver": "solver_declaration_link",
    "solver-diagnostics": "network_solver_diagnostics",
    "curtailment": "vre_curtailment_period",
    "curtailment-detail": "vre_curtailment_detail",
}

_FILTER_COLUMN = {
    "year": "year",
    "period": "period",
    "zone": "zone_id",
    "zone_id": "zone_id",
    "boundary_id": "boundary_id",
    "agent_id": "agent_id",
    "asset": "asset_id",
    "asset_id": "asset_id",
    "technology": "technology",
    "bid_tranche": "bid_tranche_id",
    "bid_tranche_id": "bid_tranche_id",
    "status": "status",
    "event_id": "event_id",
    "run": "run_id",
    "phase": "phase_id",
}

_CURTAILMENT_FILTERS = {
    "year", "period", "zone", "technology", "asset", "bid_tranche",
}
_SOLVER_DIAGNOSTIC_FILTERS = {"run", "year", "period", "phase"}


def _table_for_view(database: Path, view: str) -> str | None:
    if view == "period":
        capabilities = market_ledger_capabilities(database)
        return (
            "zonal_period_accounting"
            if capabilities["ledger_schema_version"] in ATTRIBUTION_SCHEMA_VERSIONS
            else "zonal_period_summary"
        )
    return _VIEW_TABLE.get(view)


def query_zonal_results(
    database: Path, query: Mapping[str, object]
) -> dict[str, object]:
    """Query a bounded public zonal result view without accepting raw SQL."""

    view = str(query.get("view") or "period")
    if view == "annual":
        unsupported = sorted(set(query).difference({"view"}))
        if unsupported:
            raise ValueError(
                "Annual zonal results do not accept filters: " + ", ".join(unsupported)
            )
        return query_zonal_annual_brief(database)
    table = _table_for_view(database, view)
    if table is None:
        raise ValueError("Unsupported zonal results view")
    if view in {"curtailment", "curtailment-detail"}:
        allowed_filters = _CURTAILMENT_FILTERS
    elif view == "solver-diagnostics":
        allowed_filters = _SOLVER_DIAGNOSTIC_FILTERS
    else:
        allowed_filters = set(_FILTER_COLUMN).difference({"run", "phase"})
    unsupported = sorted(
        set(query).difference({
            "view", "limit", "offset", "period_from", "period_to",
            *allowed_filters,
        })
    )
    if unsupported:
        raise ValueError("Unsupported zonal query field: " + ", ".join(unsupported))
    try:
        limit = int(query.get("limit", 100))
        offset = int(query.get("offset", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be integers") from exc
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    if offset < 0:
        raise ValueError("offset cannot be negative")
    if query.get("period") is not None and (
        query.get("period_from") is not None or query.get("period_to") is not None
    ):
        raise ValueError("period cannot be combined with period_from or period_to")
    try:
        period_from = (
            int(query["period_from"]) if query.get("period_from") is not None else None
        )
        period_to = (
            int(query["period_to"]) if query.get("period_to") is not None else None
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("period_from and period_to must be integers") from exc
    if period_from is not None and period_from < 0:
        raise ValueError("period_from cannot be negative")
    if period_to is not None and period_to < 0:
        raise ValueError("period_to cannot be negative")
    if period_from is not None and period_to is not None and period_to < period_from:
        raise ValueError("period_to must be at least period_from")
    with _read_only_connection(database) as connection:
        connection.row_factory = sqlite3.Row
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not columns:
            raise ValueError(f"Zonal results view {view} is not available")
        filters: list[str] = []
        values: list[object] = []
        observed_columns: set[str] = set()
        for public_name in sorted(allowed_filters):
            column = _FILTER_COLUMN[public_name]
            if query.get(public_name) is None:
                continue
            if column not in columns:
                raise ValueError(
                    f"Filter {public_name} is not available for zonal view {view}"
                )
            if column in observed_columns:
                raise ValueError(f"Duplicate aliases supplied for filter {column}")
            observed_columns.add(column)
            filters.append(f"{column}=?")
            values.append(query[public_name])
        if period_from is not None:
            if view == "reliability" and "end_period" in columns:
                filters.append("end_period>=?")
            elif "period" in columns:
                filters.append("period>=?")
            else:
                raise ValueError(
                    f"Filter period_from is not available for zonal view {view}"
                )
            values.append(period_from)
        if period_to is not None:
            if view == "reliability" and "start_period" in columns:
                filters.append("start_period<=?")
            elif "period" in columns:
                filters.append("period<=?")
            else:
                raise ValueError(
                    f"Filter period_to is not available for zonal view {view}"
                )
            values.append(period_to)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        # F3-07: reliability events page in chronological order (start_period
        # is numeric; the TEXT event_id sorted "observed-2025-10" before "-2").
        order_columns = [name for name in (
            "run_id", "year", "start_period", "period", "phase_id", "zone_id", "technology", "boundary_id",
            "agent_id", "asset_id", "bid_tranche_id", "bid_id", "event_id",
        ) if name in columns]
        order = ", ".join(order_columns) or "rowid"
        total = int(connection.execute(f"SELECT COUNT(*) FROM {table}{where}", values).fetchone()[0])
        rows = connection.execute(
            f"SELECT * FROM {table}{where} ORDER BY {order} LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
    return {
        "schema_version": "value.zonal-results-page/v1",
        "view": view,
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(rows),
        "has_more": offset + len(rows) < total,
        "items": [dict(row) for row in rows],
    }


def export_zonal_results(
    database: Path,
    query: Mapping[str, object],
    destination: Path,
    *,
    output_format: str = "jsonl",
) -> dict[str, object]:
    """Stream a filtered public zonal view to JSONL or CSV."""

    if str(query.get("view") or "period") == "annual":
        raise ValueError("Annual results are already a compact JSON read model")
    if output_format not in {"jsonl", "csv"}:
        raise ValueError("output_format must be jsonl or csv")
    destination.parent.mkdir(parents=True, exist_ok=True)
    selected_query = dict(query)
    selected_query.setdefault("limit", 1000)
    selected_query.setdefault("offset", 0)
    page = query_zonal_results(database, selected_query)
    items = list(page["items"])
    writer: csv.DictWriter[str] | None = None
    with destination.open("w", encoding="utf-8", newline="") as handle:
        for raw in items:
            row = dict(raw)
            if output_format == "jsonl":
                handle.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                )
            else:
                if writer is None:
                    writer = csv.DictWriter(handle, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
    return {
        "schema_version": "value.zonal-results-export/v1",
        "view": str(query.get("view") or "period"),
        "format": output_format,
        "rows": len(items),
        "total_matching_rows": int(page["total"]),
        "limit": int(page["limit"]),
        "offset": int(page["offset"]),
        "bytes": destination.stat().st_size,
        "uri": str(destination),
    }
