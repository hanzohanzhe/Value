"""Build the machine-readable Prompt 46 scientific release audit.

The audit reads completed run artifacts only.  It does not run, replay or repair
models, and it fails closed when an expected artifact is absent.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from gridform_core.bundle_validator import validate_run_bundle  # noqa: E402


ECONOMIC_FIELDS = (
    "total_capex_gbp",
    "annual_fixed_opex_gbp",
    "economic_lifetime_years",
    "annualized_capital_cost_gbp",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def close(left: float, right: float, *, absolute: float = 1e-3) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=absolute)


def carbon_sqlite_matches(json_path: Path) -> tuple[bool, list[int]]:
    collection = load_json(json_path)
    expected = {int(row["year"]): row for row in collection["years"]}
    database = json_path.with_suffix(".sqlite")
    if not database.is_file():
        return False, sorted(expected)
    with sqlite3.connect(database) as connection:
        actual = {
            int(year): json.loads(payload)
            for year, payload in connection.execute(
                "SELECT year, ledger_json FROM annual_carbon_ledger ORDER BY year"
            )
        }
    mismatches = sorted(year for year in set(expected) | set(actual) if expected.get(year) != actual.get(year))
    return not mismatches, mismatches


def commissioned_lineage(result: Mapping[str, Any]) -> dict[str, Any]:
    planning = result["planning_advance"]
    commissioned = list(planning["commissioned_projects"])
    operating_assets = list(planning["operating_state"]["assets"])
    coupling = result["market"]["extensions"]["state_coupling"]
    objects = list(coupling["generator_objects"].values()) + list(coupling["storage_objects"].values())
    live_project_ids = {
        asset_id[len("commissioned:"):]
        for row in objects
        for asset_id in row["source_asset_capacity_mw"]
        if asset_id.startswith("commissioned:")
    }
    project_ids = {str(row["project_id"]) for row in commissioned}
    cumulative_project_ids = {
        str(row["asset_id"])[len("commissioned:"):]
        for row in operating_assets
        if str(row.get("asset_id", "")).startswith("commissioned:")
    }
    economics_complete = all(
        all(field in row.get("extensions", {}) for field in ECONOMIC_FIELDS)
        and float(row["extensions"]["economic_lifetime_years"]) > 0
        and float(row["extensions"]["total_capex_gbp"]) >= 0
        for row in commissioned
    )
    return {
        "commissioned_projects": len(commissioned),
        "commissioned_capacity_mw": sum(float(row["capacity_mw"]) for row in commissioned),
        "commissioned_annualized_capital_and_fom_gbp": sum(
            float(row["extensions"]["annualized_capital_cost_gbp"])
            + float(row["extensions"]["annual_fixed_opex_gbp"])
            for row in commissioned
        ),
        "economics_complete": economics_complete,
        "live_lineage_matches": len(project_ids & live_project_ids),
        "cumulative_live_lineage_matches": len(cumulative_project_ids & live_project_ids),
        "cumulative_commissioned_project_ids": len(cumulative_project_ids),
        # Live VALUE must contain every commissioned project in the current
        # operating state, not only projects commissioned during this one year.
        "missing_live_project_ids": sorted(cumulative_project_ids - live_project_ids),
        "unexpected_live_project_ids": sorted(live_project_ids - cumulative_project_ids),
        "active_asset_count": int(coupling["active_asset_count"]),
        "mapped_asset_count": int(coupling["mapped_asset_count"]),
        "unmapped_asset_ids": list(coupling["unmapped_asset_ids"]),
    }


def asset_economic_total(result: Mapping[str, Any]) -> float:
    assets = result["planning_advance"]["operating_state"]["assets"]
    return sum(
        float(row["extensions"]["annualized_capital_cost_gbp"])
        + float(row["extensions"]["annual_fixed_opex_gbp"])
        for row in assets
    )


def storage_warnings(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[Mapping[str, Any]] = []
    for result in results:
        observations = result["market"]["extensions"].get("storage_cost_observations", {})
        rows.extend(observations.values())
    post_initial_fallback = sum(
        int(row.get("prepared_year", 0)) > results[0]["year"]
        and row.get("pricing_basis") == "full_utilisation_initialisation"
        for row in rows
    )
    zero_after_observed = sum(
        float(row.get("previous_year_sold_mwh", 0.0)) > 0
        and float(row.get("current_year_sold_mwh", 0.0)) == 0
        for row in rows
    )
    holding = [float(row.get("holding_recovery_gbp_per_mwh_period", 0.0)) for row in rows]
    return {
        "observations": len(rows),
        "post_initial_full_utilisation_fallbacks": post_initial_fallback,
        "observed_sales_to_zero_sales": zero_after_observed,
        "holding_recovery_above_10000": sum(value > 10_000 for value in holding),
        "maximum_holding_recovery_gbp_per_mwh_period": max(holding, default=0.0),
    }


def carbon_gate(row: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the declared physical or legacy-reproduction carbon boundary."""

    status = row.get("status")
    scenario = row.get("scenario") or {}
    scenario_id = scenario.get("scenario_id") if isinstance(scenario, Mapping) else None
    unresolved = list(row.get("unresolved_activities", []))
    total = row.get("total_carbon_emissions_tco2e")
    reason = row.get("reason_code")
    if status == "reconciled":
        passed = isinstance(total, (int, float)) and not unresolved
        interpretation = "physical_total_reconciled" if passed else "invalid_reconciled_record"
    elif status == "not_physically_interpretable":
        passed = (
            scenario_id == "scheme_c_reproduction_2026_07_18"
            and total is None
            and not unresolved
            and reason == "legacy_storage_scalars_have_no_declared_physical_unit"
        )
        interpretation = (
            "declared_legacy_nonphysical_boundary"
            if passed
            else "invalid_nonphysical_status"
        )
    else:
        passed = False
        interpretation = "carbon_not_evaluated_or_failed"
    return {
        "passed": passed,
        "scenario_id": scenario_id,
        "status": status,
        "reason_code": reason,
        "interpretation": interpretation,
    }


def audit_run(path: Path, expected_years: int) -> dict[str, Any]:
    required = {
        "results": path / "year-results-v2.json",
        "cost": path / "ledgers" / "annual-cost-ledger.json",
        "carbon": path / "ledgers" / "annual-carbon-ledger.json",
        "market": path / "market" / "metadata.json",
        "validation": path / "validation" / "scientific-validation.json",
        "cem_identity": path / "cem-model-identity.json",
        "performance": path / "performance.json",
    }
    missing = [name for name, artifact in required.items() if not artifact.is_file()]
    if missing:
        return {"path": str(path), "passed": False, "missing_artifacts": missing}

    results = load_json(required["results"])
    cost = load_json(required["cost"])["years"]
    carbon = load_json(required["carbon"])["years"]
    market = load_json(required["market"])
    validation = load_json(required["validation"])
    identity = load_json(required["cem_identity"])
    performance = load_json(required["performance"])
    cost_by_year = {int(row["year"]): row for row in cost}
    carbon_by_year = {int(row["year"]): row for row in carbon}
    annual: list[dict[str, Any]] = []
    for result in results:
        year = int(result["year"])
        lineage = commissioned_lineage(result)
        asset_total = asset_economic_total(result)
        market_total = float(result["market"]["total_levelized_capital_cost_gbp"])
        cost_row = cost_by_year.get(year, {})
        carbon_row = carbon_by_year.get(year, {})
        carbon_acceptance = carbon_gate(carbon_row)
        annual.append({
            "year": year,
            **lineage,
            "asset_annualized_capital_and_fom_gbp": asset_total,
            "market_annualized_capital_and_fom_gbp": market_total,
            "capital_reconciliation_error_gbp": asset_total - market_total,
            "capital_reconciled": close(asset_total, market_total),
            "cost_ledger_status": cost_row.get("status"),
            "cem_system_cost_gbp": cost_row.get("cem_system_cost_gbp"),
            "cem_system_cost_gbp_per_mwh_served": cost_row.get("cem_system_cost_gbp_per_mwh_served"),
            "demand_served_mwh": cost_row.get("demand_served_mwh"),
            "cost_reconciliation_residual_gbp": cost_row.get("physical_reconciliation_residual_gbp"),
            "carbon_ledger_status": carbon_row.get("status"),
            "carbon_unresolved_activities": list(carbon_row.get("unresolved_activities", [])),
            "total_carbon_emissions_tco2e": carbon_row.get("total_carbon_emissions_tco2e"),
            "carbon_scenario_id": carbon_acceptance["scenario_id"],
            "carbon_reason_code": carbon_acceptance["reason_code"],
            "carbon_gate_passed": carbon_acceptance["passed"],
            "carbon_gate_interpretation": carbon_acceptance["interpretation"],
        })

    carbon_equal, carbon_mismatches = carbon_sqlite_matches(required["carbon"])
    bundle = validate_run_bundle(path)
    input_assumption_warnings: list[dict[str, Any]] = []
    if results:
        for asset in results[0]["planning_advance"]["operating_state"]["assets"]:
            if asset.get("asset_id") != "Hydro_natural_flow":
                continue
            economics = asset.get("extensions", {})
            input_assumption_warnings.append({
                "id": "GF_DATA_HYDRO_EXISTING_STOCK_CAPEX_SCOPE",
                "severity": "scientific_input_warning",
                "asset_id": "Hydro_natural_flow",
                "capacity_mw": asset.get("capacity_mw"),
                "existing_stock_total_capex_gbp": economics.get("total_capex_gbp"),
                "derived_existing_stock_capex_gbp_per_mw": economics.get("capital_cost_per_mw"),
                "treatment": "preserved VALUE existing-fleet capital stock for annual accounting",
                "restriction": "do not use the derived per-MW value as new-build hydro CAPEX without a separately sourced input",
            })
    expected_periods = expected_years * 17_520
    checkpoint_count = len(list((path / "checkpoints-v2").glob("state-*.json")))
    annual_pass = all(
        row["economics_complete"]
        and not row["missing_live_project_ids"]
        and not row["unexpected_live_project_ids"]
        and not row["unmapped_asset_ids"]
        and row["active_asset_count"] == row["mapped_asset_count"]
        and row["capital_reconciled"]
        and row["cost_ledger_status"] == "reconciled"
        and row["carbon_gate_passed"]
        for row in annual
    )
    passed = (
        len(results) == expected_years
        and len(cost) == expected_years
        and len(carbon) == expected_years
        and int(market["rows"]["period_summary"]) == expected_periods
        and validation.get("scientific_validation_status") == "passed"
        and identity.get("relationship_to_retained_scheme_c") == "scheme_c_derived_declared_divergence"
        and carbon_equal
        and bundle.get("valid") is True
        and checkpoint_count == expected_years
        and annual_pass
    )
    return {
        "path": str(path),
        "passed": passed,
        "years": len(results),
        "period_summary_rows": int(market["rows"]["period_summary"]),
        "storage_state_rows": int(market["rows"]["storage_state"]),
        "maximum_absolute_energy_balance_residual_mwh": market.get("maximum_absolute_energy_balance_residual_mwh"),
        "public_contract_materialisation_seconds": performance.get("phases_seconds", {}).get("public_contract_materialisation"),
        "psm_hot_paths": [
            row for row in performance.get("observed_hot_paths", [])
            if row.get("stage") == "psm.run"
        ],
        "scientific_validation": validation.get("scientific_validation_status"),
        "cem_identity": identity.get("model_id"),
        "relationship_to_retained_scheme_c": identity.get("relationship_to_retained_scheme_c"),
        "carbon_json_sqlite_equal": carbon_equal,
        "carbon_json_sqlite_mismatch_years": carbon_mismatches,
        "checkpoints": checkpoint_count,
        "bundle_validation": bundle,
        "storage_pricing_warnings": storage_warnings(results),
        "input_assumption_warnings": input_assumption_warnings,
        "annual": annual,
    }


def audit_validation(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "passed": False, "missing": True}
    report = load_json(path)
    return {
        "path": str(path),
        "passed": bool(report.get("clearing_validation_passed")),
        "declared_rows": report.get("declared_rows"),
        "lp_passed_rows": report.get("lp_passed_rows"),
        "lp_failed_rows": report.get("lp_failed_rows"),
        "non_lp_information_structure_rows": report.get("non_lp_information_structure_rows"),
        "storage_transition_failed_rows": report.get("storage_transition_failed_rows"),
        "missing_required_resource_kinds": report.get("missing_required_resource_kinds"),
        "oracle": report.get("oracle"),
    }


def audit_data_distribution(root: Path) -> dict[str, Any]:
    scan_path = root / "publication" / "value-uk-open-data-pack" / "public-artifact-scan.json"
    inventory_path = root / "publication" / "value-uk-open-data-pack" / "local-source-inventory.json"
    if not scan_path.is_file() or not inventory_path.is_file():
        return {"passed": False, "missing": [str(path) for path in (scan_path, inventory_path) if not path.is_file()]}
    scan = load_json(scan_path)
    inventory = load_json(inventory_path)
    passed = (
        scan.get("decision") == "GO"
        and int(scan.get("roles", 0)) == 25
        and int(scan.get("forbidden_or_corrupt_objects", -1)) == 0
        and inventory.get("publication_status") == "PUBLIC_REDISTRIBUTION_GO_PER_OBJECT_WITH_ATTRIBUTION"
        and inventory.get("file_integrity_verified") is True
        and int(inventory.get("roles_source_identified", 0)) == 25
        and int(inventory.get("roles_with_licence_label", 0)) == 25
    )
    return {
        "passed": passed,
        "decision": scan.get("decision"),
        "roles": scan.get("roles"),
        "forbidden_or_corrupt_objects": scan.get("forbidden_or_corrupt_objects"),
        "publication_status": inventory.get("publication_status"),
        "file_integrity_verified": inventory.get("file_integrity_verified"),
        "licence_scope": "per-object with recorded attribution; not a blanket relicensing of upstream data",
    }


def audit_regression_gates(root: Path) -> dict[str, Any]:
    path = root / "publication" / "prompt46-regression-gates.json"
    if not path.is_file():
        return {"passed": False, "path": str(path), "missing": True}
    report = load_json(path)
    required = (
        "python_full_suite",
        "frontend_lint",
        "frontend_build",
        "render_contract",
        "browser_e2e",
        "package_install",
        "synthetic_pack_two_year",
        "snapshot_integrity",
    )
    missing = [gate for gate in required if gate not in report.get("gates", {})]
    failed = [
        gate for gate in required
        if gate in report.get("gates", {}) and not report["gates"][gate].get("passed")
    ]
    return {
        "passed": not missing and not failed,
        "path": str(path),
        "missing_gates": missing,
        "failed_gates": failed,
        "gates": report.get("gates", {}),
    }


def audit_three_scenario_comparison(root: Path) -> dict[str, Any]:
    path = root / "publication" / "prompt46-three-scenario-comparison.json"
    if not path.is_file():
        return {"passed": False, "path": str(path), "missing": True}
    report = load_json(path)
    comparisons = report.get("comparisons", {})
    dynamic_legacy = comparisons.get("dynamic_vs_legacy", {})
    legacy_retained = comparisons.get("legacy_vs_retained", {})
    dynamic_retained = comparisons.get("dynamic_vs_retained", {})
    passed = (
        report.get("functional_release", {}).get("go") is True
        and dynamic_legacy.get("cost_definitions_comparable") is True
        and legacy_retained.get("cost_definitions_comparable") is False
        and dynamic_retained.get("cost_definitions_comparable") is False
        and legacy_retained.get("interpretation") == "descriptive_only_cost_definition_mismatch"
        and dynamic_retained.get("interpretation") == "descriptive_only_cost_definition_mismatch"
        and report.get("numerical_claims", {}).get("legacy_is_exact_scheme_c_reproduction") is False
    )
    return {
        "passed": passed,
        "path": str(path),
        "functional_release": report.get("functional_release"),
        "numerical_claims": report.get("numerical_claims"),
        "dynamic_vs_legacy_costs_comparable": dynamic_legacy.get("cost_definitions_comparable"),
        "legacy_vs_retained_interpretation": legacy_retained.get("interpretation"),
        "dynamic_vs_retained_interpretation": dynamic_retained.get("interpretation"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("publication/prompt46-final-release-audit.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    validations = {
        "24_hour": audit_validation(root / "publication" / "prompt46-force-24h-independent-validation.json"),
        "168_hour": audit_validation(root / "publication" / "prompt46-force-168h-independent-validation.json"),
    }
    runs = {
        "one_year": audit_run(root / "outputs" / "prompt46-one-year-full-post-cem-fix", 1),
        "two_year": audit_run(root / "outputs" / "prompt46-two-year-full-post-cem-fix", 2),
        "dynamic_ten_year": audit_run(root / "outputs" / "prompt46-dynamic-storage-2025-2034-post-cem-fix", 10),
        "legacy_ten_year": audit_run(root / "outputs" / "prompt46-legacy-storage-2025-2034-post-cem-fix", 10),
    }
    distribution = audit_data_distribution(root)
    regression = audit_regression_gates(root)
    comparison = audit_three_scenario_comparison(root)
    gates = (
        [item["passed"] for item in validations.values()]
        + [item["passed"] for item in runs.values()]
        + [distribution["passed"], regression["passed"], comparison["passed"]]
    )
    report = {
        "schema_version": "value.prompt46-release-audit/v1",
        "decision": "GO_SCIENTIFIC_RUN_GATES" if all(gates) else "NO_GO_INCOMPLETE_OR_FAILED_GATES",
        "validations": validations,
        "runs": runs,
        "data_distribution": distribution,
        "regression_gates": regression,
        "three_scenario_comparison": comparison,
        "claim_boundary": {
            "force_clearing": "independently matched for declared convex stages; sequential rule stages are classified separately",
            "cem": "VALUE CEM v1 is VALUE-derived with declared divergences; no exact retained numerical parity claim",
            "dynamic_storage_pricing": "published selectable research method, not a universal default",
            "uk_data": "redistribution is per object under its recorded source terms and attribution",
        },
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"decision": report["decision"], "output": str(output)}, indent=2))
    raise SystemExit(0 if all(gates) else 1)


if __name__ == "__main__":
    main()
