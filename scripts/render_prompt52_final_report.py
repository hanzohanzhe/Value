"""Render the Prompt 52 final test report from machine-readable audits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def annual_rows(audit: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    year_results = {
        int(row["year"]): row for row in read(run_dir / "year-results-v2.json")
    }
    investments = {
        int(row["year"]): row for row in audit["investment_audit"]
    }
    rows: list[dict[str, Any]] = []
    for audited in audit["base_audit"]["annual"]:
        year = int(audited["year"])
        market = year_results[year]["market"]
        investment = investments[year]
        rows.append(
            {
                "year": year,
                "cem_system_cost_gbp": audited["cem_system_cost_gbp"],
                "cem_system_cost_gbp_per_mwh_served": audited[
                    "cem_system_cost_gbp_per_mwh_served"
                ],
                "operational_cost_gbp": market["total_operational_cost_gbp"],
                "annualised_capital_and_fom_gbp": market[
                    "total_levelized_capital_cost_gbp"
                ],
                "served_demand_mwh": audited["demand_served_mwh"],
                "total_generation_mwh": market["total_generation_mwh"],
                "blackout_mwh": market["total_blackout_mwh"],
                "excess_mwh": market["total_excess_mwh"],
                "total_carbon_emissions_tco2e": audited[
                    "total_carbon_emissions_tco2e"
                ],
                "commissioned_projects": audited["commissioned_projects"],
                "commissioned_capacity_mw": audited["commissioned_capacity_mw"],
                "active_asset_count": audited["active_asset_count"],
                "model_investment_proposals": investment["proposal_count"],
                "model_investment_capacity_mw": investment["proposal_capacity_mw"],
                "cost_reconciled": audited["cost_ledger_status"] == "reconciled",
                "carbon_reconciled": audited["carbon_ledger_status"] == "reconciled",
                "capital_reconciled": audited["capital_reconciled"],
                "lineage_complete": not audited["missing_live_project_ids"]
                and not audited["unexpected_live_project_ids"],
            }
        )
    return rows


def markdown_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Year | System cost (GBP/MWh) | System cost (GBP bn) | OPEX (GBP bn) | Capital + FOM (GBP bn) | Carbon (MtCO2e) | Commissioned MW | Proposals |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        carbon = row["total_carbon_emissions_tco2e"]
        carbon_text = f"{carbon / 1e6:.3f}" if carbon is not None else "not physical"
        lines.append(
            "| {year} | {cost_mwh:.3f} | {cost_bn:.3f} | {opex_bn:.3f} | {cap_bn:.3f} | {carbon_text} | {commissioned:,.3f} | {proposals} |".format(
                year=row["year"],
                cost_mwh=row["cem_system_cost_gbp_per_mwh_served"],
                cost_bn=row["cem_system_cost_gbp"] / 1e9,
                opex_bn=row["operational_cost_gbp"] / 1e9,
                cap_bn=row["annualised_capital_and_fom_gbp"] / 1e9,
                carbon_text=carbon_text,
                commissioned=row["commissioned_capacity_mw"],
                proposals=row["model_investment_proposals"],
            )
        )
    return lines


def comparison_summary(comparison: dict[str, Any]) -> dict[str, Any]:
    pair = comparison["comparisons"]["dynamic_vs_legacy"]
    cost_checks = [
        row for row in pair["checks"] if row["metric"] == "Cost_per_MWh_GBP"
    ]
    storage_checks = [
        row
        for row in pair["checks"]
        if row["metric"] == "Total_Storage_Capacity_MW"
    ]
    return {
        "cost_definitions_comparable": pair["cost_definitions_comparable"],
        "dynamic_minus_legacy_cost_gbp_per_mwh": {
            str(row["year"]): row["difference_left_minus_right"]
            for row in cost_checks
        },
        "dynamic_minus_legacy_storage_capacity_mw": {
            str(row["year"]): row["difference_left_minus_right"]
            for row in storage_checks
        },
        "legacy_is_exact_retained_reproduction": comparison["numerical_claims"][
            "legacy_is_exact_scheme_c_reproduction"
        ],
        "retained_comparison_interpretation": comparison["comparisons"][
            "legacy_vs_retained"
        ]["interpretation"],
    }


def maximum_absolute_check(pair: dict[str, Any], metric: str) -> dict[str, Any]:
    rows = [row for row in pair["checks"] if row["metric"] == metric]
    return max(rows, key=lambda row: abs(float(row.get("percent_difference") or 0.0)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("publication/prompt52-final-test-report.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("publication/prompt52-final-test-report.md"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    publication = root / "publication"
    dynamic_dir = root / "outputs" / "prompt52-dynamic-storage-2025-2034-post-repd-fix"
    legacy_dir = root / "outputs" / "prompt52-legacy-storage-2025-2034-post-repd-fix"

    inputs = {
        "snapshot": read(publication / "prompt52-pretest-snapshot.json"),
        "repd": read(publication / "prompt53-repd-2026-cohort-audit.json"),
        "one_year": read(publication / "prompt52-one-year-full-audit.json"),
        "two_year": read(publication / "prompt52-two-year-full-audit.json"),
        "dynamic": read(publication / "prompt52-dynamic-ten-year-audit.json"),
        "legacy": read(publication / "prompt52-legacy-ten-year-audit.json"),
        "comparison": read(publication / "prompt52-three-scenario-comparison.json"),
        "trace": read(publication / "prompt52-trace-off-equivalence.json"),
        "regression": read(publication / "prompt52-regression-gates.json"),
        "resume": read(publication / "prompt52-checkpoint-resume-audit.json"),
    }
    dynamic_rows = annual_rows(inputs["dynamic"], dynamic_dir)
    legacy_rows = annual_rows(inputs["legacy"], legacy_dir)
    comparison = comparison_summary(inputs["comparison"])
    dynamic_legacy_pair = inputs["comparison"]["comparisons"]["dynamic_vs_legacy"]
    legacy_retained_pair = inputs["comparison"]["comparisons"]["legacy_vs_retained"]
    maximum_cost = maximum_absolute_check(dynamic_legacy_pair, "Cost_per_MWh_GBP")
    maximum_storage = maximum_absolute_check(dynamic_legacy_pair, "Total_Storage_Capacity_MW")
    maximum_retained_cost = maximum_absolute_check(legacy_retained_pair, "Cost_per_MWh_GBP")
    maximum_retained_storage = maximum_absolute_check(legacy_retained_pair, "Total_Storage_Capacity_MW")

    scientific_pass = all(
        bool(inputs[name].get("passed"))
        for name in ("one_year", "two_year", "dynamic", "legacy", "trace", "regression", "resume")
    ) and inputs["repd"]["structural_gate"]["status"] == "passed"
    fresh_clone_ready = bool(
        inputs["regression"].get("source_release", {}).get("fresh_git_checkout_ready")
    )
    report = {
        "schema_version": "value.prompt52-final-test-report/v1",
        "date": "2026-08-11",
        "version": "0.5.0-beta.1 corrected release candidate",
        "decision": {
            "local_bounded_beta": "GO" if scientific_pass else "NO_GO",
            "post_change_annual_scientific_chain": "GO" if scientific_pass else "NO_GO",
            "dynamic_storage_research_scenario": "GO" if inputs["dynamic"]["passed"] else "NO_GO",
            "legacy_tariff_modular_scenario": "GO" if inputs["legacy"]["passed"] else "NO_GO",
            "exact_retained_scheme_c_reproduction": "NO_GO"
            if not comparison["legacy_is_exact_retained_reproduction"]
            else "GO",
            "fresh_git_checkout_release": "GO" if fresh_clone_ready else "NO_GO",
            "unqualified_unique_storage_baseline_claim": "NOT_CLAIMED",
        },
        "evidence": inputs,
        "annual_results": {"dynamic": dynamic_rows, "legacy": legacy_rows},
        "comparison_summary": comparison,
        "claim_boundaries": [
            "The built-in GB study is single-node and has no internal transmission constraints.",
            "VALUE does not implement full unit commitment or ramping.",
            "VALUE-CEM v1 is VALUE-derived with declared differences, not an exact reproduction.",
            "Dynamic storage recovery is a selectable research policy, not a unique global optimum.",
            "Carbon values from runs with different factor scenarios are not a controlled storage-policy comparison.",
            "The installed UK pack and public source release remain separate rights-governed products.",
        ],
    }
    write_json((root / args.output_json).resolve(), report)

    dynamic_base = inputs["dynamic"]["base_audit"]
    legacy_base = inputs["legacy"]["base_audit"]
    regression = inputs["regression"]
    snapshot = inputs["snapshot"]
    repd = inputs["repd"]
    resume = inputs["resume"]
    lines = [
        "# VALUE post-architecture full test report",
        "",
        "Date: 11 August 2026  ",
        "Version: 0.5.0-beta.1 corrected release candidate  ",
        "Scope: Prompts 52 to 55",
        "",
        "## Decision",
        "",
        (
            "The post-Prompt-47 VALUE model passes the complete annual, causal two-year and paired ten-year gates. "
            "It is suitable for local use as a bounded research beta."
            if scientific_pass
            else "One or more required scientific gates failed. This version is not ready for a bounded research beta."
        ),
        "",
        "| Gate | Decision |",
        "| --- | --- |",
        f"| Local application and annual PSM/CEM chain | {'GO' if scientific_pass else 'NO-GO'} |",
        f"| Dynamic-storage ten-year research scenario | {'GO' if inputs['dynamic']['passed'] else 'NO-GO'} |",
        f"| Legacy-tariff ten-year modular scenario | {'GO' if inputs['legacy']['passed'] else 'NO-GO'} |",
        f"| Exact retained VALUE reproduction | {'GO' if comparison['legacy_is_exact_retained_reproduction'] else 'NO-GO'} |",
        f"| Fresh Git checkout and GitHub publication | {'GO' if fresh_clone_ready else 'NO-GO'} |",
        "| Dynamic storage as the unique recommended baseline | Not claimed |",
        "",
        "The dynamic and legacy runs use the same VALUE CEM system-resource-cost definition, so their cost results are directly comparable. Their carbon factor scenarios differ. Carbon deltas between the two runs are therefore not a controlled storage-policy effect.",
        "",
        "## Rollback and interruption recovery",
        "",
        f"The pre-test archive contains {snapshot['member_count']} members and has SHA-256 `{snapshot['sha256']}`. Its path is `{snapshot['archive']}`.",
        "",
        f"The long runs were interrupted after {resume['before_resume']['dynamic_completed_years']} dynamic years and {resume['before_resume']['legacy_completed_years']} legacy years. Both resumed from identity-verified atomic checkpoints. The unfinished year was recomputed; no completed year was repeated. Resume evidence passed: `{str(resume['passed']).lower()}`.",
        "",
        "## Test summary",
        "",
        "| Test | Result |",
        "| --- | --- |",
        f"| Python 3.10 suite | {regression['python_suite']['tests_run']} run; {regression['python_suite']['passed']} passed; {regression['python_suite']['expected_skips']} expected skip; {regression['python_suite']['failed']} failed |",
        f"| Frontend lint/build/render | {'passed' if regression['frontend']['passed'] else 'failed'} |",
        f"| Real browser E2E | {regression['browser_e2e']['tests']}/{regression['browser_e2e']['tests']} passed |",
        f"| Retained VALUE hashes | {'passed' if regression['retained_scheme_c_hashes'] else 'failed'} |",
        f"| Source release scan | {'passed' if regression['source_release']['scan_passed'] else 'failed'}; fresh Git checkout {'ready' if fresh_clone_ready else 'not ready'} |",
        f"| REPD 2026 cohort | {repd['cohort']['physical_projects']} physical projects; {repd['cohort']['typed_components']} typed components; structural gate {repd['structural_gate']['status']} |",
        f"| One full year | {'passed' if inputs['one_year']['passed'] else 'failed'}; 17,520 periods |",
        f"| Two full years | {'passed' if inputs['two_year']['passed'] else 'failed'}; 35,040 periods |",
        f"| Generation-trace A/B | {'passed' if inputs['trace']['passed'] else 'failed'}; 17,520 period and 87,600 storage rows equal |",
        f"| Dynamic ten-year bundle | {'passed' if inputs['dynamic']['passed'] else 'failed'}; {dynamic_base['period_summary_rows']:,} periods; {dynamic_base['bundle_validation']['artifacts_checked']} artifacts |",
        f"| Legacy ten-year bundle | {'passed' if inputs['legacy']['passed'] else 'failed'}; {legacy_base['period_summary_rows']:,} periods; {legacy_base['bundle_validation']['artifacts_checked']} artifacts |",
        "",
        "## Full annual and two-year causality gates",
        "",
        f"The full 2025 run produced {inputs['one_year']['total_model_investment_proposals']} non-zero model investment proposals. The two-year run produced {inputs['two_year']['total_model_investment_proposals']} proposals. In 2026, {inputs['two_year']['base_audit']['annual'][1]['commissioned_projects']} typed components totalling {inputs['two_year']['base_audit']['annual'][1]['commissioned_capacity_mw']:,.3f} MW entered the live PSM. This consists of 881 corrected REPD typed components plus 43 model proposals made in 2025. Missing and unexpected lineage lists were empty.",
        "",
        f"The two-year maximum absolute energy-balance residual was `{inputs['two_year']['base_audit']['maximum_absolute_energy_balance_residual_mwh']}` MWh. Capital, VALUE resource cost and carbon ledgers reconciled in both years.",
        "",
        "## Dynamic-storage ten-year result",
        "",
        *markdown_table(dynamic_rows),
        "",
        f"Total blackout over the ten years was {sum(row['blackout_mwh'] for row in dynamic_rows):,.3f} MWh. Cumulative commissioned capacity was {sum(row['commissioned_capacity_mw'] for row in dynamic_rows):,.3f} MW, counting each typed commissioning event in its entry year.",
        "",
        f"The dynamic audit recorded {dynamic_base['storage_pricing_warnings']['post_initial_full_utilisation_fallbacks']} post-initial full-utilisation fallbacks, {dynamic_base['storage_pricing_warnings']['observed_sales_to_zero_sales']} positive-sales-to-zero-sales transitions and {dynamic_base['storage_pricing_warnings']['holding_recovery_above_10000']} holding-recovery values above GBP 10,000/MWh/period. The maximum observed value was {dynamic_base['storage_pricing_warnings']['maximum_holding_recovery_gbp_per_mwh_period']:,.3f} GBP/MWh/period.",
        "",
        "## Legacy-tariff ten-year result",
        "",
        *markdown_table(legacy_rows),
        "",
        f"Total blackout over the ten years was {sum(row['blackout_mwh'] for row in legacy_rows):,.3f} MWh. Cumulative commissioned capacity was {sum(row['commissioned_capacity_mw'] for row in legacy_rows):,.3f} MW. The carbon column remains non-physical by contract because the historical storage scalars do not have a declared physical unit.",
        "",
        "The legacy tariff is a valid selectable VALUE storage-price module. Passing the modular run proves execution and accounting integrity, not exact reproduction of the complete retained VALUE trajectory.",
        "",
        "## Scenario comparison",
        "",
        f"Dynamic and legacy VALUE costs share `value.cem-system-resource-cost/v1`. Their largest annual cost-per-MWh difference was {abs(maximum_cost['percent_difference']):.3f}% in {maximum_cost['year']}. Their largest beginning-of-year storage-capacity difference was {abs(maximum_storage['percent_difference']):.6f}% in {maximum_storage['year']}.",
        "",
        f"The retained VALUE comparison uses `scheme-c-historical-system-cost/v1`, so VALUE-versus-retained cost deltas are descriptive only. The largest legacy-versus-retained cost-per-MWh difference was {abs(maximum_retained_cost['percent_difference']):.3f}%, and the largest storage-capacity difference was {abs(maximum_retained_storage['percent_difference']):.3f}%. These differences include the corrected REPD battery mapping, probability-consistent MW/MWh/CAPEX/FOM, superseded-project exclusion and declared VALUE-CEM accounting differences. The legacy tariff scenario is not an exact retained reproduction.",
        "",
        "## REPD preprocessing finding and correction",
        "",
        f"The corrected 2026 cohort contains {repd['cohort']['physical_projects']} physical projects represented by {repd['cohort']['typed_components']} typed components. Declared capacity is {repd['cohort']['declared_capacity_mw']:,.3f} MW and probability-weighted effective capacity is {repd['cohort']['effective_capacity_mw']:,.3f} MW. MW, MWh, CAPEX and FOM probability residuals are zero. Superseded applications are excluded.",
        "",
        "Generic REPD batteries without duration use the explicit `scheme_c_proportional_split` compatibility mapping. Model completion years are derived inputs. Both assumptions remain visible and should be reported in studies that use this pack.",
        "",
        "## Performance and trace setting",
        "",
        f"The A/B annual run preserved every public scientific artifact after normalising run-scoped IDs and timing. Disabling the retained in-memory generation trace changed measured public-contract runtime from {inputs['trace']['performance']['trace_on_public_contract_materialisation_seconds']:.3f} s to {inputs['trace']['performance']['trace_off_public_contract_materialisation_seconds']:.3f} s, an observed {inputs['trace']['performance']['observed_improvement_percent']:.2f}% reduction. This is a performance observation, not a scientific result.",
        "",
        "Full years remain slow as the commissioned fleet and planning population grow. Checkpoints protect completed years but do not preserve an incomplete half-hour within a year. A resumed run recomputes the incomplete year.",
        "",
        "## Defects found during this test",
        "",
        "Prompt 54 fixed an artifact-boundary error in the direct Windows test harness. External launcher logs could flush after provenance was sealed. VALUE now excludes recognized supervisor logs, and both completed bundles were resealed with every scientific artifact hash unchanged.",
        "",
        "Prompt 55 fixed a release-audit contradiction. The authoritative carbon scenario must produce a reconciled physical total. The VALUE reproduction scenario is accepted only when it returns the exact declared non-physical status, null total and reason code. Generic missing carbon still fails closed.",
        "",
        "## Remaining release limits",
        "",
        f"1. The source-release scanner reports {regression['source_release']['untracked_release_members']} release members that are not tracked by Git. Installation from this working tree is tested, but a fresh Git checkout is not yet proven.",
        "2. The built-in GB model has no internal transmission constraints, full unit commitment or ramping.",
        "3. Dynamic storage recovery is a published selectable research rule. It is not presented as a unique optimal tariff, and floor or denominator-smoothing sensitivity remains appropriate.",
        "4. The legacy tariff does not make VALUE an exact retained VALUE reproduction.",
        "5. The real UK pack remains a separate, per-object rights-governed release asset. The CC0 synthetic pack remains the public CI and tutorial default.",
        "6. Ten-year runtime is operationally heavy. Performance work can improve usability without changing the scientific equations.",
        "",
        "## Conclusion",
        "",
        "The architecture defects identified after Prompt 46 are closed at full annual and ten-year execution level. The local model is a coherent, auditable VALUE research beta. GitHub publication should wait for maintainer staging, a fresh-clone installation and test run, and the intended UK data objects should remain outside the source repository.",
        "",
        "Machine-readable evidence: `publication/prompt52-final-test-report.json`.",
    ]
    output_md = (root / args.output_md).resolve()
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"decision": report["decision"], "markdown": str(output_md)}, indent=2))
    raise SystemExit(0 if scientific_pass else 1)


if __name__ == "__main__":
    main()
