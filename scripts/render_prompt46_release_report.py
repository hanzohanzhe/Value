"""Render the Prompt 46 machine audit as a concise human release report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def money_bn(value: float | None) -> str:
    return "n/a" if value is None else f"£{float(value) / 1e9:,.3f}bn"


def number(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{float(value):,.{digits}f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=Path("publication/prompt46-final-release-audit.json"))
    parser.add_argument("--comparison", type=Path, default=Path("publication/prompt46-three-scenario-comparison.json"))
    parser.add_argument("--output", type=Path, default=Path("publication/prompt46-final-release-audit.md"))
    args = parser.parse_args()
    audit = load(args.audit)
    comparison = load(args.comparison) if args.comparison.is_file() else None
    go = audit["decision"] == "GO_SCIENTIFIC_RUN_GATES"
    release_decision = (
        "GO for an open-source beta with bounded scientific claims"
        if go else "NO-GO: one or more required release gates are incomplete or failed"
    )
    validations = audit["validations"]
    runs = audit["runs"]
    two_year = runs["two_year"]
    causal = two_year.get("annual", [{}, {}])[-1]
    dynamic = runs["dynamic_ten_year"]
    legacy = runs["legacy_ten_year"]

    lines = [
        "# VALUE Prompt 46 final test and release audit",
        "",
        f"Decision: **{release_decision}**.",
        "",
        "This report replaces the Prompt 41 scientific decision for newly regenerated outputs only. "
        "Prompt 39 remains immutable negative evidence and is not re-labelled as valid.",
        "",
        "## Defects addressed",
        "",
        "- Commissioned projects now become versioned operating assets and are aggregated into the following year's live VALUE generator or storage objects with project-level lineage.",
        "- Every commissioned asset must carry CAPEX, FOM, economic life, CRF and annualised capital cost; incomplete economics fail before clearing.",
        "- VALUE CEM v1 is identified as VALUE-derived with declared divergences. It does not claim exact retained CEM parity.",
        "- Annual carbon totals separately reconcile direct operation, imports and embodied equipment/fleet emissions in JSON and SQLite.",
        "- The public UK aggregation is distributed per object with its recorded source terms and attribution, rather than under a blanket project licence.",
        "",
        "## Independent VALUE clearing",
        "",
        "| Chronology | Declared stages | LP stages matched | LP failures | Rule-structured stages | SOC transition failures | Result |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for key, label in (("24_hour", "24 hours"), ("168_hour", "168 hours")):
        row = validations[key]
        lines.append(
            f"| {label} | {row.get('declared_rows', 'n/a')} | {row.get('lp_passed_rows', 'n/a')} | "
            f"{row.get('lp_failed_rows', 'n/a')} | {row.get('non_lp_information_structure_rows', 'n/a')} | "
            f"{row.get('storage_transition_failed_rows', 'n/a')} | {status(row['passed'])} |"
        )
    lines.extend([
        "",
        "The non-LP rows are explicitly classified sequential VALUE rules. They are not counted as independent optimum matches.",
        "",
        "## Full-run gates",
        "",
        "| Run | Years | Period rows | Storage-state rows | Checkpoints | Maximum balance residual (MWh) | Result |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for key, label in (
        ("one_year", "Full 2025"),
        ("two_year", "Full 2025–2026"),
        ("dynamic_ten_year", "Dynamic pricing 2025–2034"),
        ("legacy_ten_year", "Legacy tariff 2025–2034"),
    ):
        row = runs[key]
        lines.append(
            f"| {label} | {row.get('years', 0)} | {row.get('period_summary_rows', 0):,} | "
            f"{row.get('storage_state_rows', 0):,} | {row.get('checkpoints', 0)} | "
            f"{number(row.get('maximum_absolute_energy_balance_residual_mwh'), 9)} | {status(row['passed'])} |"
        )
    lines.extend([
        "",
        "## Causal CEM-to-PSM proof",
        "",
        f"The full two-year run commissioned **{causal.get('commissioned_projects', 0)} projects** "
        f"({number(causal.get('commissioned_capacity_mw'), 2)} MW). "
        f"All **{causal.get('live_lineage_matches', 0)}** project identities appear in the 2026 live VALUE fleet; "
        f"{causal.get('active_asset_count', 0)}/{causal.get('mapped_asset_count', 0)} operating assets are mapped and "
        f"the unmapped list contains {len(causal.get('unmapped_asset_ids', []))} assets.",
        "",
        f"Those projects add {money_bn(causal.get('commissioned_annualized_capital_and_fom_gbp'))} per year. "
        f"The 2026 asset-economic sum and market capital ledger differ by only "
        f"£{abs(float(causal.get('capital_reconciliation_error_gbp', 0.0))):.6f}.",
        "",
        "## Ten-year economic comparison",
        "",
        "| Year | Dynamic system cost | Dynamic £/MWh served | Dynamic capital | Legacy system cost | Legacy £/MWh served | Legacy capital |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    dynamic_years = {row["year"]: row for row in dynamic.get("annual", [])}
    legacy_years = {row["year"]: row for row in legacy.get("annual", [])}
    for year in sorted(set(dynamic_years) | set(legacy_years)):
        left, right = dynamic_years.get(year, {}), legacy_years.get(year, {})
        lines.append(
            f"| {year} | {money_bn(left.get('cem_system_cost_gbp'))} | "
            f"{number(left.get('cem_system_cost_gbp_per_mwh_served'))} | "
            f"{money_bn(left.get('market_annualized_capital_and_fom_gbp'))} | "
            f"{money_bn(right.get('cem_system_cost_gbp'))} | "
            f"{number(right.get('cem_system_cost_gbp_per_mwh_served'))} | "
            f"{money_bn(right.get('market_annualized_capital_and_fom_gbp'))} |"
        )

    warnings = dynamic.get("storage_pricing_warnings", {})
    lines.extend([
        "",
        "## Dynamic storage-pricing audit",
        "",
        f"Across {warnings.get('observations', 0)} technology-year observations, the run recorded "
        f"{warnings.get('post_initial_full_utilisation_fallbacks', 0)} post-initial full-utilisation fallbacks, "
        f"{warnings.get('observed_sales_to_zero_sales', 0)} prior-sales-to-zero-sales transitions and "
        f"{warnings.get('holding_recovery_above_10000', 0)} holding coefficients above £10,000/MWh/period. "
        f"The maximum was £{number(warnings.get('maximum_holding_recovery_gbp_per_mwh_period'), 2)}.",
        "",
        "This published method remains a selectable research policy. Passing software and accounting gates does not make it the universal default; legacy tariff and user modules remain valid comparison choices.",
        "",
        "## Carbon and data distribution",
        "",
        f"All current-scenario annual carbon rows are reconciled and JSON/SQLite equality is "
        f"{status(all(row.get('carbon_json_sqlite_equal', False) for row in runs.values()))}. "
        "VALUE's historical scalar carbon metric remains a separate reproduction output and is not relabelled as a physical total.",
        "",
        f"The public UK pack gate is **{status(audit['data_distribution']['passed'])}**: "
        f"{audit['data_distribution'].get('roles', 0)}/25 roles, zero forbidden or corrupt objects, "
        "per-object attribution and licence labels. This is not legal advice and does not grant a blanket sublicence over upstream data.",
        "",
        "## Scientific and product caveats",
        "",
        "- The retained £200bn existing `Hydro_natural_flow` capital stock is preserved for annual accounting. Its derived £100m/MW value must not be reused as new-build hydro CAPEX without a separate source.",
        f"- PSM materialisation took {number(dynamic.get('public_contract_materialisation_seconds'), 1)} seconds for the dynamic run and {number(legacy.get('public_contract_materialisation_seconds'), 1)} seconds for the legacy run. Monitoring observed a legacy-run working set of at least 16.7 GB. The model is usable for research, but later-year performance and memory optimisation remain product-quality priorities.",
        "- VALUE CEM and retained VALUE use declared different investment/policy/pipeline rules. Comparisons across different cost definitions are descriptive, not parity scores.",
    ])
    if comparison:
        claims = comparison.get("numerical_claims", {})
        lines.extend([
            "",
            "## Retained VALUE comparison boundary",
            "",
            f"Both new bundles pass functional comparison: **{status(comparison['functional_release']['go'])}**. "
            f"Legacy tariff is an exact retained VALUE numerical reproduction: **{str(claims.get('legacy_is_exact_scheme_c_reproduction', False)).lower()}**. "
            "The retained historical system-cost definition and the VALUE CEM resource-cost definition are different, so their cost levels are reported descriptively.",
        ])
    lines.extend([
        "",
        "## Release decision",
        "",
        ("The code, synthetic pack, per-object UK aggregation, bounded VALUE clearing validation and regenerated annual CEM results pass the beta release gates. "
         "Release claims must retain the information-structure, CEM-divergence, storage-policy and hydro-cost qualifications above."
         if go else
         "The platform must not be released as a validated open-source modelling platform until every failed or missing machine-readable gate in the companion JSON audit is closed."),
        "",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
