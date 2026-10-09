"""Bounded server-side result summaries and compatibility-aware comparisons."""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Mapping, Sequence
from .comparison_identity import build_comparison_identity, comparison_key, review_comparison_identities
from .result_advisories import NEEDS_REVIEW_SEVERITIES, present_scientific_status

from .result_coverage import ANNUAL_PERIODS, NON_ANNUAL_MODES, REASON_NON_ANNUAL, is_non_annual, stopped_reason
from .comparison_eligibility import (
    evaluate_curtailment_comparison,
    evaluate_network_comparison,
)


MAX_ANNUAL_ROWS = 200
# One shared rule for non-annual modes (P0-9 S5): derived from the run policies.
_NONANNUAL_MODES = NON_ANNUAL_MODES
_ATTRIBUTION_SCHEMA = "value.vre-curtailment-run-evidence/v1"
_ATTRIBUTION_CONTRACT = "value.vre-curtailment-attribution/v2"


def _read(path: Path, fallback: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _a2_balance_by_year(path: Path) -> dict[int, dict[str, float]]:
    """Annual demand and A2 unserved energy (recorded + stress shortfall) from the market metadata (R5)."""

    metadata = _read(path, {})
    balance = metadata.get("energy_balance") if isinstance(metadata, Mapping) else None
    rows = balance.get("by_year") if isinstance(balance, Mapping) else None
    result: dict[int, dict[str, float]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping) or row.get("year") is None:
            continue
        demand = _finite_number(row.get("demand_mwh"))
        recorded = _finite_number(row.get("recorded_unserved_mwh"))
        hidden = _finite_number(row.get("hidden_unserved_mwh"))
        if hidden is not None and row.get("stress_periods") == 0:
            hidden = 0.0  # sub-tolerance noise only (cost_ledger.a2_hidden_unserved_mwh)
        result[int(row["year"])] = {
            **({"demand_mwh": demand} if demand is not None else {}),
            **({"unserved_mwh": recorded + hidden} if recorded is not None and hidden is not None else {}),
        }
    return result


UNUSED_VRE_DEFINITION = "value.unused-vre/v1"
PRE_BALANCING_EXCESS_DEFINITION = "value.pre-balancing-excess/v1"

# R5-2 review: where a ledger measures accepted VRE, from its semantic metadata
# (the same fields market_replay.query_vre_curtailment_summary reads).  Unused
# VRE measured at different boundaries is not one quantity across Runs.
VRE_BOUNDARY_FULL_NODE = "full_node_gross_vre_output"
VRE_BOUNDARY_AFTER_PREBALANCING = "after_separate_prebalancing_excess"
VRE_BOUNDARY_UNSPLIT = "unsplit_unused_vre"
VRE_BOUNDARY_UNKNOWN = "not_recorded"
VRE_BOUNDARY_METRICS = frozenset({
    "unused_vre_mwh", "unused_vre_share_percent", "pre_balancing_excess_mwh",
})


def vre_measurement_boundary(semantic: Mapping[str, object]) -> str:
    """The PSM boundary at which a ledger records accepted VRE."""

    from .market_replay import CORRECTED_CURTAILMENT_SEMANTICS

    if str(semantic.get("curtailment_semantics")) == CORRECTED_CURTAILMENT_SEMANTICS:
        return VRE_BOUNDARY_FULL_NODE
    relationship = str(semantic.get("excess_relationship", ""))
    if relationship == "separate_prebalancing":
        return VRE_BOUNDARY_AFTER_PREBALANCING
    if relationship == "alias_of_unused_vre":
        return VRE_BOUNDARY_UNSPLIT
    return VRE_BOUNDARY_UNKNOWN


def annual_unused_vre(database: Path) -> dict[int, dict[str, object]]:
    """Annual unused VRE at the PSM boundary, as the VRE page reports it (R5 R-中2).

    Unused VRE is the sum over periods of max(available VRE - accepted VRE, 0)
    (``market_replay.query_vre_curtailment_summary``).  It is recorded by
    every market ledger with VRE columns, unlike the v2 curtailment
    attribution, which needs matched counterfactual snapshots (zonal PSM).
    Each year also carries ``vre_boundary`` (where accepted VRE is measured)
    and, for a ledger that separates pre-balancing excess from the balancing
    stage (doctoral rules), that excess as ``pre_balancing_excess_mwh``
    (None otherwise), as the VRE page reports them (G1-08).
    {} when the ledger or its columns are missing.
    """

    import sqlite3

    from .market_ledger import _read_only_connection
    from .market_replay import _semantic_metadata

    if not database.is_file():
        return {}
    try:
        semantic = _semantic_metadata(database)
    except (OSError, ValueError, sqlite3.Error):
        semantic = {}
    boundary = vre_measurement_boundary(semantic)
    try:
        with _read_only_connection(database) as connection:
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(period_summary)")}
            if not {"year", "vre_available_mwh", "vre_accepted_mwh"}.issubset(columns):
                return {}
            excess_sql = "SUM(excess_mwh)" if "excess_mwh" in columns else "NULL"
            rows = connection.execute(
                "SELECT year, SUM(vre_available_mwh), "
                "SUM(MAX(vre_available_mwh - vre_accepted_mwh, 0.0)), "
                f"{excess_sql} "
                "FROM period_summary GROUP BY year ORDER BY year"
            ).fetchall()
    except sqlite3.Error:
        return {}
    result: dict[int, dict[str, object]] = {}
    for year, available, unused, excess in rows:
        available_value, unused_value = _finite_number(available), _finite_number(unused)
        if available_value is None or unused_value is None:
            continue
        result[int(year)] = {
            "available_vre_mwh": available_value,
            "unused_vre_mwh": unused_value,
            "vre_boundary": boundary,
            "pre_balancing_excess_mwh": (
                _finite_number(excess) if boundary == VRE_BOUNDARY_AFTER_PREBALANCING else None
            ),
        }
    return result


def _unavailable_attribution(reason_code: str, *, status: str = "unavailable") -> dict[str, object]:
    return {"status": status, "reason_code": reason_code, "annual_by_year": {}}


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _expected_years_from_run_policy(policy: object) -> tuple[int, ...] | None:
    if not isinstance(policy, Mapping):
        return None
    start = policy.get("start_year")
    end = policy.get("end_year")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or end < start
    ):
        return None
    return tuple(range(start, end + 1))


def _expected_years_from_summary(summary: Mapping[str, object]) -> tuple[int, ...] | None:
    run = summary.get("run")
    return _expected_years_from_run_policy(run)


def validate_vre_curtailment_attribution(
    artifact: object,
    *,
    mode: object,
    periods_per_year: object,
    expected_years: Sequence[int],
    run_status: object = None,
) -> dict[str, object]:
    """Strictly admit complete annual attribution evidence, or expose no values.

    The non-annual and stopped-Run verdicts come from the shared annual-coverage
    rule (gridform_core.result_coverage, P0-9 S5).  ``run_status`` is the Run's
    status record (or its status string) when the caller reads a finished
    Run; the worker validates while the Run is still running and passes None,
    so only the per-year period proof below applies there.  A missing
    ``periods_per_year`` is still withheld (stricter than ``is_non_annual``)."""

    policy_view = {"mode": mode, "run_policy": {"periods_per_year": periods_per_year}}
    if is_non_annual(policy_view) or periods_per_year != ANNUAL_PERIODS:
        return _unavailable_attribution(REASON_NON_ANNUAL, status="withheld")
    if run_status is not None:
        stopped = stopped_reason(
            run_status if isinstance(run_status, Mapping) else {"status": run_status}
        )
        if stopped is not None:
            return _unavailable_attribution(stopped, status="withheld")
    if not isinstance(artifact, Mapping):
        return _unavailable_attribution("vre_curtailment_attribution_artifact_missing")
    if artifact.get("schema_version") != _ATTRIBUTION_SCHEMA:
        return _unavailable_attribution("vre_curtailment_artifact_schema_unsupported")
    if artifact.get("contract_version") != _ATTRIBUTION_CONTRACT:
        return _unavailable_attribution("vre_curtailment_artifact_contract_unsupported")
    capability_status = str(artifact.get("capability_status") or "unavailable")
    reason_code = artifact.get("reason_code")
    if capability_status != "reconciled":
        return _unavailable_attribution(
            str(reason_code or "vre_curtailment_attribution_not_reconciled"),
            status=capability_status,
        )
    if (
        isinstance(expected_years, (str, bytes))
        or any(isinstance(year, bool) or not isinstance(year, int) for year in expected_years)
        or len(set(expected_years)) != len(expected_years)
        or not expected_years
    ):
        return _unavailable_attribution("vre_curtailment_expected_year_set_invalid")
    proof = artifact.get("matched_counterfactual_proof")
    expected_year_set = set(expected_years)
    expected_period_count = len(expected_year_set) * 17520
    if (
        not isinstance(proof, Mapping)
        or proof.get("period_sets_match") is not True
        or proof.get("realised_input_hashes_match") is not True
        or proof.get("period_count") != expected_period_count
        or not isinstance(proof.get("period_identity_set_sha256"), str)
        or not isinstance(artifact.get("counterfactual_realised_input_set_sha256"), str)
    ):
        return _unavailable_attribution("vre_curtailment_counterfactual_proof_invalid")
    totals = artifact.get("annual_totals")
    if not isinstance(totals, Sequence) or isinstance(totals, (str, bytes)):
        return _unavailable_attribution("vre_curtailment_annual_evidence_missing")
    maximum_residual = _finite_number(
        artifact.get("maximum_absolute_period_residual_mwh")
    )
    maximum_tolerance = _finite_number(artifact.get("maximum_period_tolerance_mwh"))
    if (
        maximum_residual is None
        or maximum_tolerance is None
        or maximum_residual < 0.0
        or maximum_tolerance < 0.0
        or maximum_residual > maximum_tolerance
    ):
        return _unavailable_attribution("vre_curtailment_maximum_period_residual_invalid")
    rows_by_year: dict[int, Mapping[str, object]] = {}
    for row in totals:
        if not isinstance(row, Mapping) or isinstance(row.get("year"), bool):
            return _unavailable_attribution("vre_curtailment_annual_year_set_invalid")
        try:
            year = int(row["year"])
        except (KeyError, TypeError, ValueError):
            return _unavailable_attribution("vre_curtailment_annual_year_set_invalid")
        if year in rows_by_year:
            return _unavailable_attribution("vre_curtailment_annual_year_set_invalid")
        rows_by_year[year] = row
    if set(rows_by_year) != expected_year_set:
        return _unavailable_attribution("vre_curtailment_annual_year_set_invalid")
    annual_by_year: dict[int, dict[str, float]] = {}
    for year in sorted(expected_year_set):
        row = rows_by_year[year]
        if row.get("period_count") != 17520:
            return _unavailable_attribution("vre_curtailment_period_count_invalid")
        values = {
            field: _finite_number(row.get(field))
            for field in (
                "available_mwh", "economic_mwh", "forecast_added_mwh",
                "forecast_avoided_mwh", "redispatch_added_mwh",
                "redispatch_avoided_mwh", "total_mwh", "rate",
                "redispatch_net_mwh", "identity_residual_mwh",
                "aggregate_tolerance_mwh",
            )
        }
        if any(value is None for value in values.values()):
            return _unavailable_attribution("vre_curtailment_annual_value_nonfinite")
        available = float(values["available_mwh"])
        economic = float(values["economic_mwh"])
        forecast_added = float(values["forecast_added_mwh"])
        forecast_avoided = float(values["forecast_avoided_mwh"])
        redispatch_added = float(values["redispatch_added_mwh"])
        redispatch_avoided = float(values["redispatch_avoided_mwh"])
        total = float(values["total_mwh"])
        rate = float(values["rate"])
        redispatch_net = float(values["redispatch_net_mwh"])
        residual = float(values["identity_residual_mwh"])
        tolerance = float(values["aggregate_tolerance_mwh"])
        if available < 0.0 or total < 0.0 or tolerance < 0.0:
            return _unavailable_attribution("vre_curtailment_annual_range_invalid")
        if total > available + tolerance:
            return _unavailable_attribution("vre_curtailment_annual_range_invalid")
        expected_rate = 0.0 if available == 0.0 else total / available
        if not 0.0 <= rate <= 1.0 or not math.isclose(
            rate, expected_rate, rel_tol=1e-9, abs_tol=1e-12
        ):
            return _unavailable_attribution("vre_curtailment_rate_invalid")
        if abs(redispatch_net - (redispatch_added - redispatch_avoided)) > tolerance:
            return _unavailable_attribution("vre_curtailment_redispatch_net_inconsistent")
        recomputed_residual = (
            economic
            + forecast_added
            - forecast_avoided
            + redispatch_added
            - redispatch_avoided
            - total
        )
        if not math.isclose(
            residual, recomputed_residual, rel_tol=1e-9, abs_tol=1e-12
        ):
            return _unavailable_attribution("vre_curtailment_identity_residual_inconsistent")
        if abs(recomputed_residual) > tolerance:
            return _unavailable_attribution("vre_curtailment_identity_residual_invalid")
        annual_by_year[year] = {
            "total_mwh": total,
            "rate": rate,
            "redispatch_net_mwh": redispatch_net,
        }
    return {
        "status": "reconciled",
        "reason_code": "reconciled",
        "annual_by_year": annual_by_year,
    }


def _runtime_fallback_summary(market_dir: Path) -> dict[str, object] | None:
    from .zonal_results import guarded_runtime_fallback_audit

    return guarded_runtime_fallback_audit(market_dir)


def _vre_cf_disclosure(run_root: Path, methodology: object) -> dict[str, object] | None:
    from .vre_cf_disclosure import run_disclosure

    try:
        return run_disclosure(run_root, methodology if isinstance(methodology, Mapping) else None)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def build_run_summary(run_root: Path) -> dict[str, object]:
    status = _read(run_root / "status.json", {})
    if not isinstance(status, Mapping):
        raise ValueError("Run status is invalid")
    output = run_root / "model-output"
    resolved = _read(output / "resolved-run.json", {})
    costs = _read(output / "ledgers" / "annual-cost-ledger.json", {"years": []})
    carbon = _read(output / "ledgers" / "annual-carbon-ledger.json", {"years": []})
    terminal = _read(output / "terminal" / "terminal-state.json", {})
    planning = _read(output / "planning" / "typed-summary.json", _read(output / "planning" / "summary.json", {}))
    comparison_eligibility = _read(output / "comparison-eligibility.json", None)
    curtailment_attribution = _read(
        output / "network" / "vre-curtailment-attribution.json", None
    )
    cost_years = list(costs.get("years", []))[:MAX_ANNUAL_ROWS] if isinstance(costs, Mapping) else []
    carbon_years = list(carbon.get("years", []))[:MAX_ANNUAL_ROWS] if isinstance(carbon, Mapping) else []
    carbon_by_year = {int(row["year"]): row for row in carbon_years if isinstance(row, Mapping) and row.get("year") is not None}
    periods_per_year = (
        (status.get("run_policy") or {}).get("periods_per_year")
        if isinstance(status.get("run_policy"), Mapping)
        else None
    )
    expected_years = _expected_years_from_run_policy(status.get("run_policy"))
    curtailment_validation = validate_vre_curtailment_attribution(
        curtailment_attribution,
        mode=status.get("mode"),
        periods_per_year=periods_per_year,
        expected_years=expected_years or (),
        run_status=status,
    )
    curtailment_by_year = curtailment_validation["annual_by_year"]
    balance_by_year = _a2_balance_by_year(output / "market" / "metadata.json")
    unused_vre_by_year = annual_unused_vre(output / "market" / "market.sqlite")
    annual = []
    for row in cost_years:
        if not isinstance(row, Mapping):
            continue
        year = int(row["year"])
        curtailment = curtailment_by_year.get(year)
        vre_curtailment_mwh = curtailment.get("total_mwh") if curtailment else None
        vre_curtailment_rate = curtailment.get("rate") if curtailment else None
        redispatch_net_impact_mwh = (
            curtailment.get("redispatch_net_mwh") if curtailment else None
        )
        curtailment_status = str(curtailment_validation["status"])
        curtailment_reason = str(curtailment_validation["reason_code"])
        carbon_row = carbon_by_year.get(year, {})
        unused_vre = unused_vre_by_year.get(year) or {}
        vre_boundary = unused_vre.get("vre_boundary") or VRE_BOUNDARY_UNKNOWN
        unused_share = (
            100.0 * unused_vre["unused_vre_mwh"] / unused_vre["available_vre_mwh"]
            if unused_vre and unused_vre["available_vre_mwh"] > 0 else None
        )
        lines = {str(item.get("id")): item.get("amount_gbp") for item in row.get("lines", []) if isinstance(item, Mapping)}
        annual.append({
            "year": year,
            "metrics": {
                "cem_system_cost_gbp": {"value": row.get("cem_system_cost_gbp"), "unit": "GBP", "definition_id": row.get("definition_id"), "denominator": None, "source": "ledgers/annual-cost-ledger.json"},
                "cem_system_cost_gbp_per_mwh_served": {"value": row.get("cem_system_cost_gbp_per_mwh_served"), "unit": "GBP/MWh", "definition_id": row.get("definition_id"), "denominator": "demand_served_mwh", "source": "ledgers/annual-cost-ledger.json"},
                "annualised_capital_gbp": {"value": lines.get("commissioned_fleet.annualised_capital"), "unit": "GBP", "definition_id": row.get("definition_id"), "denominator": None, "source": "ledgers/annual-cost-ledger.json"},
                "operating_resource_cost_gbp": {"value": sum(float(value or 0.0) for key, value in lines.items() if key.startswith("operation.")), "unit": "GBP", "definition_id": row.get("definition_id"), "denominator": None, "source": "ledgers/annual-cost-ledger.json"},
                "total_carbon_emissions_tco2e": {"value": carbon_row.get("total_carbon_emissions_tco2e"), "unit": "tCO2e", "definition_id": (carbon_row.get("scenario") or {}).get("scenario_id") if isinstance(carbon_row.get("scenario"), Mapping) else None, "denominator": None, "source": "ledgers/annual-carbon-ledger.json", "status": carbon_row.get("status", "not_evaluated")},
                # R5 (S-F-高1/中2): annual demand, the served energy the per-MWh
                # cost divides by, all unserved energy of the A2 account
                # (recorded blackout plus stress shortfall) and the
                # PSM-recorded part on its own.
                "demand_mwh": {"value": (balance_by_year.get(year) or {}).get("demand_mwh"), "unit": "MWh", "definition_id": "value.annual-demand/v1", "denominator": None, "source": "market/metadata.json"},
                "demand_served_mwh": {"value": row.get("demand_served_mwh"), "unit": "MWh", "definition_id": row.get("definition_id"), "denominator": None, "source": "ledgers/annual-cost-ledger.json"},
                "unserved_energy_mwh": {"value": (balance_by_year.get(year) or {}).get("unserved_mwh"), "unit": "MWh", "definition_id": "value.adequacy-unserved-energy/v2", "denominator": None, "source": "market/metadata.json"},
                "recorded_unserved_energy_mwh": {"value": None, "unit": "MWh", "definition_id": "value.adequacy-unserved-energy/v1", "denominator": None, "source": "status.results"},
                # R5 R-中2: the physical unused VRE of the VRE page, which every
                # PSM records; the three v2 attribution metrics below need
                # matched counterfactual snapshots (zonal PSM only).
                # R5-2 review: vre_boundary says where accepted VRE is measured;
                # Compare withholds deltas between different boundaries.
                "unused_vre_mwh": {"value": unused_vre.get("unused_vre_mwh"), "unit": "MWh", "definition_id": UNUSED_VRE_DEFINITION, "denominator": None, "source": "market/market.sqlite period_summary", "vre_boundary": vre_boundary},
                "unused_vre_share_percent": {"value": unused_share, "unit": "%", "definition_id": UNUSED_VRE_DEFINITION, "denominator": "available_vre_mwh", "source": "market/market.sqlite period_summary", "vre_boundary": vre_boundary},
                # The doctoral ledger routes pre-balancing surplus (VRE and
                # inflexible supply) to storage, export or spill before accepted
                # VRE is measured; it is reported on its own, as on the VRE page.
                "pre_balancing_excess_mwh": {"value": unused_vre.get("pre_balancing_excess_mwh"), "unit": "MWh", "definition_id": PRE_BALANCING_EXCESS_DEFINITION, "denominator": None, "source": "market/market.sqlite period_summary", "vre_boundary": vre_boundary, **({} if vre_boundary == VRE_BOUNDARY_AFTER_PREBALANCING else {"status": "not_applicable", "reason_code": "ledger_does_not_separate_prebalancing_excess"})},
                "vre_curtailment_mwh": {"value": vre_curtailment_mwh, "unit": "MWh", "definition_id": "value.vre-curtailment-attribution/v2", "denominator": None, "source": "network/vre-curtailment-attribution.json", "status": curtailment_status, "reason_code": curtailment_reason},
                "vre_curtailment_rate": {"value": vre_curtailment_rate, "unit": "fraction", "definition_id": "value.vre-curtailment-attribution/v2", "denominator": "realised_available_vre_mwh", "source": "network/vre-curtailment-attribution.json", "status": curtailment_status, "reason_code": curtailment_reason},
                "redispatch_net_impact_mwh": {"value": redispatch_net_impact_mwh, "unit": "MWh", "definition_id": "value.vre-curtailment-attribution/v2", "denominator": None, "source": "network/vre-curtailment-attribution.json", "status": curtailment_status, "reason_code": curtailment_reason},
            },
        })
    status_results = {int(row.get("year")): row for row in status.get("results", []) if isinstance(row, Mapping) and row.get("year") is not None}
    for row in annual:
        source = status_results.get(int(row["year"]), {})
        metrics = source.get("metrics", {}) if isinstance(source, Mapping) else {}
        row["metrics"]["recorded_unserved_energy_mwh"]["value"] = metrics.get("blackout_mwh") if isinstance(metrics, Mapping) else None
        if row["metrics"]["demand_mwh"]["value"] is None and isinstance(metrics, Mapping):
            row["metrics"]["demand_mwh"]["value"] = metrics.get("demand_mwh")
            row["metrics"]["demand_mwh"]["source"] = "status.results"
        if row["metrics"]["unserved_energy_mwh"]["value"] is None and isinstance(metrics, Mapping):
            # A Run without the A2 account: the recorded blackout is all there is.
            row["metrics"]["unserved_energy_mwh"].update({
                "value": metrics.get("unserved_energy_a2_mwh", metrics.get("blackout_mwh")),
                "definition_id": "value.adequacy-unserved-energy/v2" if metrics.get("unserved_energy_a2_mwh") is not None
                else "value.adequacy-unserved-energy/v1",
                "source": "status.results"})
        row["capacity_mw"] = source.get("capacity_mw", {}) if isinstance(source, Mapping) else {}
    modules = resolved.get("modules", status.get("modules", {})) if isinstance(resolved, Mapping) else status.get("modules", {})
    scientific = resolved.get("scientific_parameters", {}) if isinstance(resolved, Mapping) else {}
    # The same read-time presentation as /api/runs (X0 S10, C7): status
    # vocabulary, advisories, methodology and the Q14 publication rule.
    presented = present_scientific_status(json.loads(json.dumps(status)), run_root)
    publication = presented["result_publication"]
    publication_withheld = publication.get("status") == "withheld"
    withheld_annual_rows = len(annual) if publication_withheld else 0
    withheld_fields: list[str] = []
    if publication_withheld:
        # Q14: the summary serves no annual result of a withheld run - neither
        # the annual rows nor the planning summary, the curtailment attribution
        # or the terminal capacity they are derived from (the same planning
        # data /planning/summary refuses with 409).  Identity and eligibility
        # stay, so the run can still be listed and refused in comparisons.
        annual = []
        withheld_fields = ["annual", "planning", "vre_curtailment_attribution", "terminal"]
        planning = None
        curtailment_attribution = None
        terminal = None
    return {
        "schema_version": "value.run-results-summary/v1",
        "comparison_identity": build_comparison_identity(run_root, status, resolved),
        "run": {
            "run_id": status.get("id", run_root.name), "name": status.get("project_name"),
            "project_id": status.get("project_id"), "project_revision": (resolved.get("extensions") or {}).get("project_revision_sha256") if isinstance(resolved, Mapping) and isinstance(resolved.get("extensions"), Mapping) else None,
            "input_snapshot_id": status.get("input_snapshot_id"), "timestamp": status.get("finished_at", status.get("updated_at")),
            "mode": status.get("mode"), "status": status.get("status"),
            "scientific_status": presented["scientific_scenario_status"],
            "recorded_scientific_status": status.get("scientific_scenario_status", status.get("scientific_validation_status")),
            # P0-4 S3: recomputed validation evidence (v2 report or read-time oracle).
            "run_invariant_status": presented.get("run_invariant_status"),
            "energy_balance_status": presented.get("energy_balance_status"),
            "stress": {
                key: (presented.get("stress") or {}).get(key)
                for key in ("shortfall_basis", "stress_periods", "event_count", "shortfall_mwh", "shortfall_upper_mwh")
            } if isinstance(presented.get("stress"), Mapping) else None,
            "periods_per_year": (status.get("run_policy") or {}).get("periods_per_year") if isinstance(status.get("run_policy"), Mapping) else None,
            "start_year": (status.get("run_policy") or {}).get("start_year") if isinstance(status.get("run_policy"), Mapping) else None,
            "end_year": (status.get("run_policy") or {}).get("end_year") if isinstance(status.get("run_policy"), Mapping) else None,
        },
        "definitions": {
            "cost": costs.get("definition_id") if isinstance(costs, Mapping) else None,
            "carbon": scientific.get("carbon.factor_scenario") if isinstance(scientific, Mapping) else None,
            "terminal_policy": scientific.get("terminal.policy", terminal.get("terminal_policy") if isinstance(terminal, Mapping) else None) if isinstance(scientific, Mapping) else None,
            "currency_base_year": "mixed_as_declared_in_asset_sources",
        },
        "modules": modules,
        "methodology": presented["methodology"],
        "advisories": presented["advisories"],
        "advisory_summary": presented["advisory_summary"],
        "result_publication": {
            **publication,
            "withheld_annual_rows": withheld_annual_rows,
            "withheld_fields": withheld_fields,
            # R4 R-中2: the comparison states which raw invariants withheld it.
            "raw_invariant_failures": [
                {key: row.get(key) for key in ("gate", "check", "name", "count", "unit", "deviation_ids")}
                for row in (presented.get("raw_invariant_failures") or [])[:10]
                if isinstance(row, Mapping)
            ] if publication_withheld else [],
        },
        "annual": annual,
        "planning": planning,
        "comparison_eligibility": (
            comparison_eligibility
            if isinstance(comparison_eligibility, Mapping)
            else None
        ),
        "vre_curtailment_attribution": (
            curtailment_attribution
            if isinstance(curtailment_attribution, Mapping)
            else None
        ),
        # P0-8 S12: share of each technology placed in a fallback zone;
        # None when the Run is not zonal or predates the audit.
        "zonal_runtime_fallback": _runtime_fallback_summary(output / "market"),
        # A9/A13: model pre-curtailment wind/solar CF of the Run's weather and
        # weather method next to DUKES load factors, with the stated reasons.
        # A methodology disclosure, not an annual result: kept when withheld.
        "vre_capacity_factor_disclosure": _vre_cf_disclosure(run_root, presented.get("methodology")),
        "terminal": {
            key: terminal.get(key) for key in (
                "terminal_policy", "outstanding_project_count", "outstanding_capacity_mw",
                "post_horizon_project_count", "post_horizon_capacity_mw", "warning",
            )
        } if isinstance(terminal, Mapping) else (None if publication_withheld else {}),
        "audit_links": {
            "provenance": f"/api/runs/{run_root.name}/provenance",
            "artifacts": f"/api/runs/{run_root.name}/artifacts",
            "planning": f"/api/runs/{run_root.name}/planning/projects",
            "market": f"/api/runs/{run_root.name}/market/periods",
        },
        "bounded": {"annual_rows": len(annual), "maximum_annual_rows": MAX_ANNUAL_ROWS, "full_ledgers_embedded": False},
    }


# S-D9/F-D5 (four-role report): the comparison names what changed instead of
# a fixed storage-policy sentence.  Depth at which each identity dimension's
# differences are reported (data: pack directory, roles, role name).
_DIMENSION_LABELS = {
    "data": "data inputs",
    "method": "model method (modules, extensions, methodology)",
    "config": "parameters and extension configuration",
    "years": "model years",
    "scope": "run scope",
}
# The name a dimension has inside a sentence (AF3-2: the long label already
# carries a parenthesis, so "label (paths)" read "... methodology) (extensions)").
_DIMENSION_NAMES = {
    "data": "data inputs",
    "method": "model method",
    "config": "parameters and extension configuration",
    "years": "model years",
    "scope": "run scope",
}
_DIMENSION_DEPTH = {"data": 3, "method": 2, "config": 2, "years": 1, "scope": 1}
_MAX_LISTED_PATHS = 12


def _differing_paths(values: Sequence[object], depth: int, prefix: str = "") -> list[str]:
    if depth > 0 and values and all(isinstance(value, Mapping) for value in values):
        keys = sorted({str(key) for value in values for key in value})  # type: ignore[union-attr]
        paths: list[str] = []
        for key in keys:
            children = [value.get(key) for value in values]  # type: ignore[union-attr]
            if len({comparison_key(child) for child in children}) > 1:
                paths.extend(_differing_paths(children, depth - 1, f"{prefix}.{key}" if prefix else key))
        return paths
    return [prefix or "(value)"]


def _module_field_paths(values: Sequence[object], path: str) -> list[str]:
    """R3M-6: a module slot whose id and version are the same in every Run is
    named by the fields that differ (``modules.storage_cost.source_sha256``
    for a module edited in place), not by the bare slot."""

    parts = path.split(".")
    if len(parts) != 2 or parts[0] != "modules":
        return [path]
    rows = [
        (value.get("modules") or {}).get(parts[1]) if isinstance(value, Mapping) else None  # type: ignore[union-attr]
        for value in values
    ]
    if not all(isinstance(row, Mapping) for row in rows):
        return [path]
    if len({(row.get("module_id"), row.get("module_version")) for row in rows}) != 1:  # type: ignore[union-attr]
        return [path]
    return _differing_paths(rows, 1, path)


def changed_dimension_details(review: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Per changed identity dimension: a label and the differing paths (bounded)."""

    details: dict[str, dict[str, object]] = {}
    dimensions = review.get("dimensions") if isinstance(review.get("dimensions"), Mapping) else {}
    for key in review.get("changed_dimensions") or []:  # type: ignore[union-attr]
        values = list((dimensions.get(key) or {}).get("values") or [])  # type: ignore[union-attr]
        paths = _differing_paths(values, _DIMENSION_DEPTH.get(str(key), 2))
        if key == "method":
            paths = [item for path in paths for item in _module_field_paths(values, path)]
        details[str(key)] = {
            "label": _DIMENSION_LABELS.get(str(key), str(key)),
            "name": _DIMENSION_NAMES.get(str(key), str(key)),
            "paths": paths[:_MAX_LISTED_PATHS],
            "more_paths": max(0, len(paths) - _MAX_LISTED_PATHS),
        }
    return details


def _change_sentence(details: Mapping[str, Mapping[str, object]]) -> str:
    parts = []
    for row in details.values():
        paths = [str(item) for item in row.get("paths") or []]
        more = int(row.get("more_paths") or 0)
        listed = ", ".join(paths) + (f" and {more} more" if more else "")
        name = str(row.get("name") or row["label"])
        parts.append(f"{name}: {listed}" if listed else name)
    return "; ".join(parts)


# AF3-1 (DECISIONS A23): annual deltas are gated per metric.  A metric's delta
# is withheld only for a reason that concerns that metric: a definition it is
# computed under differs, or (curtailment metrics only) the Runs lack matching
# reconciled VRE-curtailment attribution evidence.
_DEFINITION_KEYS = ("cost", "carbon", "terminal_policy", "currency_base_year")
_COST_DEFINITIONS = ("cost", "terminal_policy", "currency_base_year")
_METRIC_DEFINITIONS: dict[str, tuple[str, ...]] = {
    "cem_system_cost_gbp": _COST_DEFINITIONS,
    "cem_system_cost_gbp_per_mwh_served": _COST_DEFINITIONS,
    "annualised_capital_gbp": _COST_DEFINITIONS,
    "operating_resource_cost_gbp": _COST_DEFINITIONS,
    "total_carbon_emissions_tco2e": ("carbon",),
    "unserved_energy_mwh": (),
    "recorded_unserved_energy_mwh": (),
    "demand_mwh": (),
    "demand_served_mwh": (),
    "unused_vre_mwh": (),
    "unused_vre_share_percent": (),
    "pre_balancing_excess_mwh": (),
    "vre_curtailment_mwh": (),
    "vre_curtailment_rate": (),
    "redispatch_net_impact_mwh": (),
}
CURTAILMENT_EVIDENCE_METRICS = frozenset({
    "vre_curtailment_mwh", "vre_curtailment_rate", "redispatch_net_impact_mwh",
})


def metric_delta_gate(
    metric_id: str,
    differing_definitions: Sequence[str],
    curtailment_comparison: Mapping[str, object],
    vre_boundaries: Sequence[object] = (),
) -> dict[str, object]:
    """Whether one metric's annual deltas are shown, and why not (AF3-1).

    A metric this function does not know depends on every definition
    (conservative).  The reason is a code plus a sentence for the page.
    """

    needed = _METRIC_DEFINITIONS.get(metric_id, _DEFINITION_KEYS)
    blocking = [key for key in differing_definitions if key in needed]
    if blocking:
        return {
            "allowed": False,
            "reason_code": "metric_definition_differs",
            "definitions": blocking,
            "reason": "The Runs compute this metric under different "
            + ", ".join(key.replace("_", " ") for key in blocking) + " definitions.",
        }
    # R5-2 review: unused VRE measured at different PSM boundaries (doctoral
    # after separate pre-balancing excess, corrected at the full node) is not
    # one quantity; its delta is withheld, the per-Run values stay.
    if metric_id in VRE_BOUNDARY_METRICS and len({str(value) for value in vre_boundaries}) > 1:
        return {
            "allowed": False,
            "reason_code": "unused_vre_boundary_differs",
            "definitions": [],
            "reason": "Unused VRE is measured at different PSM boundaries ("
            + ", ".join(sorted({str(value).replace("_", " ") for value in vre_boundaries}))
            + "); the doctoral pre-balancing excess is reported separately.",
        }
    if metric_id in CURTAILMENT_EVIDENCE_METRICS and not curtailment_comparison.get("metric_deltas_allowed"):
        code = str(curtailment_comparison.get("reason_code") or "curtailment_evidence_unavailable")
        return {
            "allowed": False,
            "reason_code": code,
            "definitions": [],
            "reason": "VRE-curtailment differences need matching, reconciled curtailment-attribution "
            "evidence in every Run (" + code.replace("_", " ") + ").",
        }
    return {"allowed": True, "reason_code": None, "definitions": [], "reason": None}


def _summary_vre_boundary(summary: Mapping[str, object]) -> str:
    """The VRE measurement boundary a Run summary records (R5-2 review)."""

    for row in summary.get("annual", []) or []:  # type: ignore[union-attr]
        metric = (row.get("metrics") or {}).get("unused_vre_mwh") if isinstance(row, Mapping) else None
        if isinstance(metric, Mapping) and metric.get("vre_boundary"):
            return str(metric["vre_boundary"])
    return VRE_BOUNDARY_UNKNOWN


def compare_run_summaries(summaries: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if not 2 <= len(summaries) <= 6:
        raise ValueError("A comparison requires 2 to 6 runs")
    run_modes = [str(row.get("run", {}).get("mode") or "") for row in summaries]  # type: ignore[union-attr]
    tutorial_count = sum(mode in {"tutorial", "value_101_day"} for mode in run_modes)
    # Q14: a run whose annual results are withheld from result pages cannot
    # contribute annual deltas either.
    publication_withheld = [
        row.get("run", {}).get("run_id")  # type: ignore[union-attr]
        for row in summaries
        if isinstance(row.get("result_publication"), Mapping)
        and row["result_publication"].get("status") == "withheld"  # type: ignore[index]
    ]
    annual_metrics_withheld = tutorial_count > 0 or bool(publication_withheld)
    # R4 R-中2: an annual comparison withheld by Q14 is not an annual
    # scientific comparison, and the page states the actual reason.
    comparison_scope = (
        "teaching_diagnostic" if tutorial_count == len(summaries)
        else "mixed_tutorial_and_annual" if tutorial_count
        else "annual_publication_withheld" if publication_withheld
        else "annual_scientific"
    )
    annual_withholding = annual_withholding_reasons(summaries, run_modes)
    dimensions = {}
    for key in ("cost", "carbon", "terminal_policy", "currency_base_year"):
        values = [row.get("definitions", {}).get(key) for row in summaries]  # type: ignore[union-attr]
        if len({comparison_key(value) for value in values}) > 1:
            dimensions[f"definition.{key}"] = values
    for key in ("periods_per_year", "scientific_status", "mode", "energy_balance_status", "run_invariant_status"):
        values = [row.get("run", {}).get(key) for row in summaries]  # type: ignore[union-attr]
        if len({comparison_key(value) for value in values}) > 1:
            dimensions[f"run.{key}"] = values
    module_sets = [dict(row.get("modules", {})) for row in summaries]
    module_slots = sorted(set().union(*(set(value) for value in module_sets)))
    for slot in module_slots:
        values = [modules.get(slot) for modules in module_sets]
        if len({comparison_key(value) for value in values}) > 1:
            dimensions[f"module.{slot}"] = values
    review = review_comparison_identities(summaries)
    dimension_details = changed_dimension_details(review)
    for key in review["changed_dimensions"]:
        dimensions[f"identity.{key}"] = review["dimensions"][key]["values"]
    non_storage_differences = [key for key in dimensions if key != "module.storage_cost"]
    method_values = review["dimensions"]["method"]["values"]
    storage_only_method = False
    if review["evidence_complete"]:
        base_method = method_values[0]
        storage_only_method = all(
            value.get("extensions") == base_method.get("extensions")
            # Runs under different methodologies never form a controlled
            # storage-policy comparison (X0 S9).
            and value.get("methodology") == base_method.get("methodology")
            and {slot: row for slot, row in value.get("modules", {}).items() if slot != "storage_cost"}
            == {slot: row for slot, row in base_method.get("modules", {}).items() if slot != "storage_cost"}
            for value in method_values[1:]
        )
    # R3M-6: a storage-cost module edited in place (same id and version, new
    # source) is the same controlled storage-cost change as a module swap.
    storage_identity_changed = bool(review["evidence_complete"]) and len({
        comparison_key((value.get("modules") or {}).get("storage_cost")) for value in method_values
    }) > 1
    causal_storage_comparison = (
        review["evidence_complete"] and storage_only_method
        and review["changed_dimensions"] == ["method"]
        and not [key for key in non_storage_differences if key != "identity.method"]
        and ("module.storage_cost" in dimensions or storage_identity_changed)
    )
    eligibility_artifacts = [
        row.get("comparison_eligibility")
        for row in summaries
        if isinstance(row.get("comparison_eligibility"), Mapping)
    ]
    network_comparison = (
        evaluate_network_comparison(eligibility_artifacts)  # type: ignore[arg-type]
        if len(eligibility_artifacts) == len(summaries)
        else {
            "schema_version": "value.network-comparison-eligibility/v1",
            "network_cost_attribution_allowed": False,
            "reason_code": "comparison_eligibility_artifact_missing",
            "demand_authority_modes": [],
            "matched_input_identity_sha256": None,
        }
    )
    network_cost_attribution_allowed = bool(
        review["evidence_complete"]
        and network_comparison["network_cost_attribution_allowed"]
    )
    attribution_artifacts = [
        row.get("vre_curtailment_attribution")
        if isinstance(row.get("vre_curtailment_attribution"), Mapping)
        else {}
        for row in summaries
    ]
    curtailment_comparison = evaluate_curtailment_comparison(
        network_pair=network_comparison,
        attribution_artifacts=attribution_artifacts,  # type: ignore[arg-type]
    )
    evidence_validations = [
        validate_vre_curtailment_attribution(
            artifact,
            mode=(summary.get("run") or {}).get("mode")
            if isinstance(summary.get("run"), Mapping)
            else None,
            periods_per_year=(summary.get("run") or {}).get("periods_per_year")
            if isinstance(summary.get("run"), Mapping)
            else None,
            expected_years=_expected_years_from_summary(summary) or (),
            run_status=(summary.get("run") or {}).get("status")
            if isinstance(summary.get("run"), Mapping)
            else None,
        )
        for summary, artifact in zip(summaries, attribution_artifacts)
    ]
    failed_evidence = next(
        (result for result in evidence_validations if result["status"] != "reconciled"),
        None,
    )
    if failed_evidence is not None:
        curtailment_comparison = {
            **curtailment_comparison,
            "metric_deltas_allowed": False,
            "reason_code": failed_evidence["reason_code"],
        }
    formulation_changed = "module.psm" in dimensions
    differing_definitions = [key.split(".", 1)[1] for key in dimensions if key.startswith("definition.")]
    # metric_deltas_allowed keeps its meaning: every metric's delta is shown.
    # metric_delta_gates says, per metric, which ones are and why the others
    # are withheld (AF3-1).
    deltas_allowed = (
        not differing_definitions
        and not annual_metrics_withheld
        and bool(curtailment_comparison["metric_deltas_allowed"])
    )
    metric_delta_gates: dict[str, dict[str, object]] = {}
    vre_boundaries = [_summary_vre_boundary(summary) for summary in summaries]
    base = summaries[0]
    base_annual = {int(row["year"]): row for row in base.get("annual", [])}  # type: ignore[index]
    annual_comparison = []
    years = sorted(set().union(*(
        {int(row["year"]) for row in summary.get("annual", [])}  # type: ignore[index]
        for summary in summaries
    )))
    for year in ([] if annual_metrics_withheld else years):
        metric_ids = sorted(set().union(*(
            set(next((row.get("metrics", {}) for row in summary.get("annual", []) if int(row["year"]) == year), {}))  # type: ignore[index]
            for summary in summaries
        )))
        metrics = {}
        for metric_id in metric_ids:
            gate = metric_delta_gates.setdefault(
                metric_id, metric_delta_gate(
                    metric_id, differing_definitions, curtailment_comparison, vre_boundaries,
                )
            )
            values = []
            for summary in summaries:
                annual = next((row for row in summary.get("annual", []) if int(row["year"]) == year), None)  # type: ignore[index]
                metric = (annual or {}).get("metrics", {}).get(metric_id, {})
                values.append({
                    "run_id": summary.get("run", {}).get("run_id"),  # type: ignore[union-attr]
                    "value": metric.get("value"), "unit": metric.get("unit"),
                    "definition_id": metric.get("definition_id"), "denominator": metric.get("denominator"),
                    **({"vre_boundary": metric["vre_boundary"]} if metric.get("vre_boundary") else {}),
                })
            base_value = values[0]["value"]
            for item in values:
                value = item["value"]
                if gate["allowed"] and isinstance(value, (int, float)) and isinstance(base_value, (int, float)):
                    item["delta_from_base"] = float(value) - float(base_value)
                    item["percentage_delta_from_base"] = ((float(value) - float(base_value)) / float(base_value) * 100.0) if base_value else None
                else:
                    item["delta_from_base"] = None
                    item["percentage_delta_from_base"] = None
            metrics[metric_id] = values
        annual_comparison.append({"year": year, "metrics": metrics})
    public_summaries = []
    for summary in summaries:
        public_summary = json.loads(json.dumps(summary))
        # A teaching comparison carries no annual metrics.  Under Q14 only the
        # withheld Run has none (build_run_summary removed them); a published
        # Run keeps its own annual values for the export, without deltas.
        if tutorial_count:
            public_summary["annual"] = []
        public_summaries.append(public_summary)
    if comparison_scope == "teaching_diagnostic" and causal_storage_comparison:
        warning = "Only the storage-cost module differs. This is a controlled teaching diagnostic, not annual economics; annual cost and carbon deltas are withheld."
    elif comparison_scope == "mixed_tutorial_and_annual":
        warning = "Tutorial and annual runs cannot be compared as one economic experiment. Annual deltas are withheld."
    elif network_cost_attribution_allowed:
        warning = None
    elif causal_storage_comparison:
        warning = None
    elif not dimensions:
        warning = (
            "Recorded configuration matches. These short teaching runs do not establish annual economics or a storage-policy causal effect; annual deltas are withheld."
            if tutorial_count else
            "Recorded configuration matches; annual deltas are withheld because the annual results of "
            + ", ".join(str(run_id) for run_id in publication_withheld) + " are withheld (Q14)."
            if publication_withheld else
            "Recorded configuration matches; no storage-policy change is available for causal attribution."
        )
    elif len(review["changed_dimensions"]) > 1:
        warning = (
            "Several recorded dimensions differ - " + _change_sentence(dimension_details)
            + ". Interpret the differences jointly; no isolated causal claim is made."
        )
    elif dimension_details:
        # S-低7(a): the sentence names the change that was made; it no longer
        # calls every single-dimension change "not a storage-cost experiment".
        warning = (
            "Only one recorded dimension differs - " + _change_sentence(dimension_details) + ". The comparison "
            "describes the effect of this one change."
        )
    else:
        warning = (
            "Recorded run fields differ (" + ", ".join(sorted(dimensions)) + "); interpret the differences with "
            "that in mind."
        )
    if review["unknown_dimensions"]:
        warning = review["warning"]
    storage_interpretation = (
        "configuration_evidence_unknown" if review["unknown_dimensions"] else
        "not_applicable_different_psm_formulation" if formulation_changed else
        "controlled_teaching_configuration" if causal_storage_comparison and comparison_scope == "teaching_diagnostic" else
        "controlled_storage_cost_module_change" if causal_storage_comparison else
        "matching_teaching_configuration" if not dimensions and tutorial_count else
        "matching_recorded_configuration" if not dimensions else
        "multiple_dimensions_changed" if len(review["changed_dimensions"]) > 1 else
        "recorded_configuration_changed"
    )
    # X0 S10b comparison gate (C9): an advisory of severity high or above, a
    # failed validation, or different methodologies put the comparison under
    # review and forbid causal conclusions.
    review_reasons: list[dict[str, object]] = []
    for summary in summaries:
        run_id = summary.get("run", {}).get("run_id")  # type: ignore[union-attr]
        advisories = summary.get("advisories") if isinstance(summary.get("advisories"), list) else []
        for advisory in advisories:  # type: ignore[union-attr]
            if isinstance(advisory, Mapping) and advisory.get("severity") in NEEDS_REVIEW_SEVERITIES:
                review_reasons.append({"run_id": run_id, "reason": "advisory", "advisory_id": advisory.get("id"), "severity": advisory.get("severity")})
        if summary.get("run", {}).get("scientific_status") == "failed":  # type: ignore[union-attr]
            review_reasons.append({"run_id": run_id, "reason": "validation_failed"})
        # P0-4 S3: a failed independent check rules out causal conclusions
        # even while it is reported rather than gated.
        for field, reason in (("energy_balance_status", "energy_balance_failed"), ("run_invariant_status", "run_invariants_failed")):
            if summary.get("run", {}).get(field) == "failed":  # type: ignore[union-attr]
                review_reasons.append({"run_id": run_id, "reason": reason})
    # The whole method identity, not only the profile id: the same profile at
    # another version, definition or applied-correction set is another method.
    identity_keys = ("profile_id", "profile_version", "profile_definition_sha256", "applied_corrections_sha256")
    profiles = [
        (row.get("methodology") or {}).get("profile_id") if isinstance(row.get("methodology"), Mapping) else None
        for row in summaries
    ]
    identities = [
        tuple((row.get("methodology") or {}).get(key) for key in identity_keys)  # type: ignore[union-attr]
        if isinstance(row.get("methodology"), Mapping) else None
        for row in summaries
    ]
    if any(isinstance(row.get("methodology"), Mapping) for row in summaries) and len(set(identities)) > 1:
        differing = sorted({
            key for index, key in enumerate(identity_keys)
            if len({item[index] if item else None for item in identities}) > 1
        })
        review_reasons.append({"reason": "methodology_differs", "profile_ids": profiles, "differing_fields": differing})
    for run_id in publication_withheld:
        review_reasons.append({"run_id": run_id, "reason": "annual_results_withheld"})
    attribution_status = "needs_review" if review_reasons else "reviewable"
    if review_reasons:
        network_cost_attribution_allowed = False
        if warning is None:
            warning = "This comparison needs review: an advisory, a failed validation or a methodology difference rules out causal conclusions."
    return {
        "schema_version": "value.run-comparison/v1",
        "attribution_status": attribution_status,
        "attribution_review_reasons": review_reasons,
        "run_ids": [row.get("run", {}).get("run_id") for row in summaries],  # type: ignore[union-attr]
        "comparison_scope": comparison_scope,
        "comparison_review": review,
        "annual_metrics_withheld": annual_metrics_withheld,
        "annual_withholding": annual_withholding,
        "changed_dimensions": dimensions,
        "changed_dimension_details": dimension_details,
        "metric_deltas_allowed": deltas_allowed,
        "metric_delta_gates": metric_delta_gates,
        "withheld_metric_deltas": sorted(key for key, gate in metric_delta_gates.items() if not gate["allowed"]),
        "clean_storage_policy_comparison": causal_storage_comparison,
        "network_comparison": network_comparison,
        "curtailment_comparison": curtailment_comparison,
        "network_cost_attribution_allowed": network_cost_attribution_allowed,
        "storage_pricing_interpretation": storage_interpretation,
        "causal_claim_allowed": (
            review["evidence_complete"]
            and (causal_storage_comparison or network_cost_attribution_allowed)
            and not annual_metrics_withheld
            and not review_reasons
        ),
        "warning": warning,
        "annual_comparison": annual_comparison,
        "runs": public_summaries,
    }


def annual_withholding_reasons(
    summaries: Sequence[Mapping[str, object]], run_modes: Sequence[str]
) -> list[dict[str, object]]:
    """Why annual deltas are withheld, one row per cause (R4 R-中2).

    ``teaching_run``: the one-day lesson has no annual economics.
    ``result_publication_withheld``: Q14 withholds a Run's annual results;
    the row names the raw invariants that failed (or that none was evaluated).
    """

    reasons: list[dict[str, object]] = []
    run_ids = [(row.get("run") or {}).get("run_id") if isinstance(row.get("run"), Mapping) else None for row in summaries]
    teaching = [run_id for run_id, mode in zip(run_ids, run_modes) if mode in {"tutorial", "value_101_day"}]
    if teaching:
        reasons.append({
            "reason_code": "teaching_run",
            "run_ids": teaching,
            "text": "contains one 48-period VALUE 101 market day, which has no annual economics",
        })
    for run_id, row in zip(run_ids, summaries):
        publication = row.get("result_publication")
        if not isinstance(publication, Mapping) or publication.get("status") != "withheld":
            continue
        failures = [item for item in publication.get("raw_invariant_failures") or [] if isinstance(item, Mapping)]
        methodology = row.get("methodology") if isinstance(row.get("methodology"), Mapping) else {}
        if failures:
            checks = ", ".join(
                str(item.get("check") or item.get("name"))
                + (f" ({item.get('count')} {item.get('unit') or 'rows'})" if item.get("count") is not None else "")
                for item in failures
            )
            text = f"is a reproduction Run whose annual results are withheld (Q14): raw invariant {checks} failed"
        elif publication.get("raw_invariants_status") == "pending":
            text = "is a reproduction Run that is still running; its raw invariants are checked when it finishes (Q14)"
        else:
            text = "is a reproduction Run whose annual results are withheld (Q14): its raw invariants were not evaluated"
        reasons.append({
            "reason_code": "result_publication_withheld",
            "run_ids": [run_id],
            "decision": publication.get("decision", "Q14"),
            "publication_reason_code": publication.get("reason_code"),
            "profile_id": methodology.get("profile_id"),  # type: ignore[union-attr]
            "raw_invariant_failures": [dict(item) for item in failures],
            "text": text,
        })
    return reasons


def comparison_csv(comparison: Mapping[str, object]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["schema_version", comparison.get("schema_version")])
    # R4 R-中2: an export without annual rows says why.
    writer.writerow(["comparison_scope", comparison.get("comparison_scope")])
    writer.writerow(["annual_metrics_withheld", "true" if comparison.get("annual_metrics_withheld") else "false"])
    for reason in comparison.get("annual_withholding") or []:  # type: ignore[union-attr]
        if isinstance(reason, Mapping):
            writer.writerow([
                "annual_withheld_reason", reason.get("reason_code"),
                ";".join(str(item) for item in reason.get("run_ids") or []), reason.get("text"),
            ])
    # R5 R-低12: an empty value or a withheld delta says why, as the page does:
    # value_status/value_reason_code for the value, delta_shown and
    # delta_withheld_reason for the per-metric delta gate (AF3-1).
    writer.writerow(["run_id", "year", "metric_id", "value", "unit", "definition_id", "denominator", "source",
                     "value_status", "value_reason_code", "delta_shown", "delta_withheld_reason"])
    gates = comparison.get("metric_delta_gates") if isinstance(comparison.get("metric_delta_gates"), Mapping) else {}
    annual_withheld = bool(comparison.get("annual_metrics_withheld"))
    for summary in comparison.get("runs", []):
        for annual in summary.get("annual", []):
            for metric_id, metric in annual.get("metrics", {}).items():
                value = metric.get("value")
                status = metric.get("status") or ("recorded" if value is not None else "not_recorded")
                gate = gates.get(metric_id) if isinstance(gates, Mapping) else None  # type: ignore[union-attr]
                if annual_withheld:
                    delta_shown, delta_reason = "false", "annual_metrics_withheld"
                elif isinstance(gate, Mapping):
                    delta_shown = "true" if gate.get("allowed") else "false"
                    delta_reason = None if gate.get("allowed") else (gate.get("reason") or gate.get("reason_code"))
                else:
                    delta_shown, delta_reason = None, None
                writer.writerow([summary["run"]["run_id"], annual["year"], metric_id, value, metric.get("unit"),
                                 metric.get("definition_id"), metric.get("denominator"), metric.get("source"),
                                 status, metric.get("reason_code"), delta_shown, delta_reason])
    return output.getvalue()
