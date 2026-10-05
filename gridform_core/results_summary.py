"""Bounded server-side result summaries and compatibility-aware comparisons."""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Mapping, Sequence
from .comparison_identity import build_comparison_identity, review_comparison_identities

from .result_coverage import ANNUAL_PERIODS, NON_ANNUAL_MODES
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
) -> dict[str, object]:
    """Strictly admit complete annual attribution evidence, or expose no values."""

    if str(mode) in _NONANNUAL_MODES:
        return _unavailable_attribution(
            "annual_evidence_withheld_for_nonannual_run", status="withheld"
        )
    if periods_per_year != ANNUAL_PERIODS:
        return _unavailable_attribution(
            "annual_evidence_withheld_for_nonannual_run", status="withheld"
        )
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
    )
    curtailment_by_year = curtailment_validation["annual_by_year"]
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
        lines = {str(item.get("id")): item.get("amount_gbp") for item in row.get("lines", []) if isinstance(item, Mapping)}
        annual.append({
            "year": year,
            "metrics": {
                "cem_system_cost_gbp": {"value": row.get("cem_system_cost_gbp"), "unit": "GBP", "definition_id": row.get("definition_id"), "denominator": None, "source": "ledgers/annual-cost-ledger.json"},
                "cem_system_cost_gbp_per_mwh_served": {"value": row.get("cem_system_cost_gbp_per_mwh_served"), "unit": "GBP/MWh", "definition_id": row.get("definition_id"), "denominator": "demand_served_mwh", "source": "ledgers/annual-cost-ledger.json"},
                "annualised_capital_gbp": {"value": lines.get("commissioned_fleet.annualised_capital"), "unit": "GBP", "definition_id": row.get("definition_id"), "denominator": None, "source": "ledgers/annual-cost-ledger.json"},
                "operating_resource_cost_gbp": {"value": sum(float(value or 0.0) for key, value in lines.items() if key.startswith("operation.")), "unit": "GBP", "definition_id": row.get("definition_id"), "denominator": None, "source": "ledgers/annual-cost-ledger.json"},
                "total_carbon_emissions_tco2e": {"value": carbon_row.get("total_carbon_emissions_tco2e"), "unit": "tCO2e", "definition_id": (carbon_row.get("scenario") or {}).get("scenario_id") if isinstance(carbon_row.get("scenario"), Mapping) else None, "denominator": None, "source": "ledgers/annual-carbon-ledger.json", "status": carbon_row.get("status", "not_evaluated")},
                "unserved_energy_mwh": {"value": None, "unit": "MWh", "definition_id": "value.adequacy-unserved-energy/v1", "denominator": None, "source": "status.results"},
                "vre_curtailment_mwh": {"value": vre_curtailment_mwh, "unit": "MWh", "definition_id": "value.vre-curtailment-attribution/v2", "denominator": None, "source": "network/vre-curtailment-attribution.json", "status": curtailment_status, "reason_code": curtailment_reason},
                "vre_curtailment_rate": {"value": vre_curtailment_rate, "unit": "fraction", "definition_id": "value.vre-curtailment-attribution/v2", "denominator": "realised_available_vre_mwh", "source": "network/vre-curtailment-attribution.json", "status": curtailment_status, "reason_code": curtailment_reason},
                "redispatch_net_impact_mwh": {"value": redispatch_net_impact_mwh, "unit": "MWh", "definition_id": "value.vre-curtailment-attribution/v2", "denominator": None, "source": "network/vre-curtailment-attribution.json", "status": curtailment_status, "reason_code": curtailment_reason},
            },
        })
    status_results = {int(row.get("year")): row for row in status.get("results", []) if isinstance(row, Mapping) and row.get("year") is not None}
    for row in annual:
        source = status_results.get(int(row["year"]), {})
        metrics = source.get("metrics", {}) if isinstance(source, Mapping) else {}
        row["metrics"]["unserved_energy_mwh"]["value"] = metrics.get("blackout_mwh") if isinstance(metrics, Mapping) else None
        row["capacity_mw"] = source.get("capacity_mw", {}) if isinstance(source, Mapping) else {}
    modules = resolved.get("modules", status.get("modules", {})) if isinstance(resolved, Mapping) else status.get("modules", {})
    scientific = resolved.get("scientific_parameters", {}) if isinstance(resolved, Mapping) else {}
    return {
        "schema_version": "value.run-results-summary/v1",
        "comparison_identity": build_comparison_identity(run_root, status, resolved),
        "run": {
            "run_id": status.get("id", run_root.name), "name": status.get("project_name"),
            "project_id": status.get("project_id"), "project_revision": (resolved.get("extensions") or {}).get("project_revision_sha256") if isinstance(resolved, Mapping) and isinstance(resolved.get("extensions"), Mapping) else None,
            "input_snapshot_id": status.get("input_snapshot_id"), "timestamp": status.get("finished_at", status.get("updated_at")),
            "mode": status.get("mode"), "status": status.get("status"),
            "scientific_status": status.get("scientific_scenario_status", status.get("scientific_validation_status")),
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
        "terminal": {
            key: terminal.get(key) for key in (
                "terminal_policy", "outstanding_project_count", "outstanding_capacity_mw",
                "post_horizon_project_count", "post_horizon_capacity_mw", "warning",
            )
        } if isinstance(terminal, Mapping) else {},
        "audit_links": {
            "provenance": f"/api/runs/{run_root.name}/provenance",
            "artifacts": f"/api/runs/{run_root.name}/artifacts",
            "planning": f"/api/runs/{run_root.name}/planning/projects",
            "market": f"/api/runs/{run_root.name}/market/periods",
        },
        "bounded": {"annual_rows": len(annual), "maximum_annual_rows": MAX_ANNUAL_ROWS, "full_ledgers_embedded": False},
    }


def compare_run_summaries(summaries: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if not 2 <= len(summaries) <= 6:
        raise ValueError("A comparison requires 2 to 6 runs")
    run_modes = [str(row.get("run", {}).get("mode") or "") for row in summaries]  # type: ignore[union-attr]
    tutorial_count = sum(mode in {"tutorial", "value_101_day"} for mode in run_modes)
    annual_metrics_withheld = tutorial_count > 0
    comparison_scope = (
        "teaching_diagnostic" if tutorial_count == len(summaries)
        else "mixed_tutorial_and_annual" if tutorial_count
        else "annual_scientific"
    )
    dimensions = {}
    for key in ("cost", "carbon", "terminal_policy", "currency_base_year"):
        values = [row.get("definitions", {}).get(key) for row in summaries]  # type: ignore[union-attr]
        if len(set(json.dumps(value, sort_keys=True) for value in values)) > 1:
            dimensions[f"definition.{key}"] = values
    for key in ("periods_per_year", "scientific_status", "mode"):
        values = [row.get("run", {}).get(key) for row in summaries]  # type: ignore[union-attr]
        if len(set(json.dumps(value, sort_keys=True) for value in values)) > 1:
            dimensions[f"run.{key}"] = values
    module_sets = [dict(row.get("modules", {})) for row in summaries]
    module_slots = sorted(set().union(*(set(value) for value in module_sets)))
    for slot in module_slots:
        values = [modules.get(slot) for modules in module_sets]
        if len(set(json.dumps(value, sort_keys=True) for value in values)) > 1:
            dimensions[f"module.{slot}"] = values
    review = review_comparison_identities(summaries)
    for key in review["changed_dimensions"]:
        dimensions[f"identity.{key}"] = review["dimensions"][key]["values"]
    non_storage_differences = [key for key in dimensions if key != "module.storage_cost"]
    method_values = review["dimensions"]["method"]["values"]
    storage_only_method = False
    if review["evidence_complete"]:
        base_method = method_values[0]
        storage_only_method = all(
            value.get("extensions") == base_method.get("extensions")
            and {slot: row for slot, row in value.get("modules", {}).items() if slot != "storage_cost"}
            == {slot: row for slot, row in base_method.get("modules", {}).items() if slot != "storage_cost"}
            for value in method_values[1:]
        )
    causal_storage_comparison = (
        review["evidence_complete"] and storage_only_method
        and review["changed_dimensions"] == ["method"]
        and not [key for key in non_storage_differences if key != "identity.method"]
        and "module.storage_cost" in dimensions
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
    deltas_allowed = (
        not any(key.startswith("definition.") for key in dimensions)
        and not annual_metrics_withheld
        and bool(curtailment_comparison["metric_deltas_allowed"])
    )
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
            values = []
            for summary in summaries:
                annual = next((row for row in summary.get("annual", []) if int(row["year"]) == year), None)  # type: ignore[index]
                metric = (annual or {}).get("metrics", {}).get(metric_id, {})
                values.append({
                    "run_id": summary.get("run", {}).get("run_id"),  # type: ignore[union-attr]
                    "value": metric.get("value"), "unit": metric.get("unit"),
                    "definition_id": metric.get("definition_id"), "denominator": metric.get("denominator"),
                })
            base_value = values[0]["value"]
            for item in values:
                value = item["value"]
                if deltas_allowed and isinstance(value, (int, float)) and isinstance(base_value, (int, float)):
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
        if annual_metrics_withheld:
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
            if annual_metrics_withheld else
            "Recorded configuration matches; no storage-policy change is available for causal attribution."
        )
    elif len(review["changed_dimensions"]) > 1:
        warning = "Changed dimensions must be interpreted jointly; an isolated storage-policy causal claim is blocked."
    else:
        warning = "A recorded change is present, but it does not establish an isolated storage-policy causal effect."
    if review["unknown_dimensions"]:
        warning = review["warning"]
    storage_interpretation = (
        "configuration_evidence_unknown" if review["unknown_dimensions"] else
        "not_applicable_different_psm_formulation" if formulation_changed else
        "controlled_teaching_configuration" if causal_storage_comparison and comparison_scope == "teaching_diagnostic" else
        "controlled_storage_cost_module_change" if causal_storage_comparison else
        "matching_teaching_configuration" if not dimensions and annual_metrics_withheld else
        "matching_recorded_configuration" if not dimensions else
        "multiple_dimensions_changed" if len(review["changed_dimensions"]) > 1 else
        "recorded_configuration_changed"
    )
    return {
        "schema_version": "value.run-comparison/v1",
        "run_ids": [row.get("run", {}).get("run_id") for row in summaries],  # type: ignore[union-attr]
        "comparison_scope": comparison_scope,
        "comparison_review": review,
        "annual_metrics_withheld": annual_metrics_withheld,
        "changed_dimensions": dimensions,
        "metric_deltas_allowed": deltas_allowed,
        "clean_storage_policy_comparison": causal_storage_comparison,
        "network_comparison": network_comparison,
        "curtailment_comparison": curtailment_comparison,
        "network_cost_attribution_allowed": network_cost_attribution_allowed,
        "storage_pricing_interpretation": storage_interpretation,
        "causal_claim_allowed": (
            review["evidence_complete"]
            and (causal_storage_comparison or network_cost_attribution_allowed)
            and not annual_metrics_withheld
        ),
        "warning": warning,
        "annual_comparison": annual_comparison,
        "runs": public_summaries,
    }


def comparison_csv(comparison: Mapping[str, object]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["schema_version", comparison.get("schema_version")])
    writer.writerow(["run_id", "year", "metric_id", "value", "unit", "definition_id", "denominator", "source"])
    for summary in comparison.get("runs", []):
        for annual in summary.get("annual", []):
            for metric_id, metric in annual.get("metrics", {}).items():
                writer.writerow([summary["run"]["run_id"], annual["year"], metric_id, metric.get("value"), metric.get("unit"), metric.get("definition_id"), metric.get("denominator"), metric.get("source")])
    return output.getvalue()
