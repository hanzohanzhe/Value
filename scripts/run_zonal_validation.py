"""Run and publish the Prompt 103 independent zonal validation gate."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pulp

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_validation.cbc import cbc_identity
from gridform_validation.zonal_case_generator import (
    analytical_cases,
    production_solution,
    random_convex_case,
    run_sequential_soc_case,
)
from gridform_validation.zonal_oracle import (
    audit_zonal_candidate,
    compare_zonal_solutions,
    solve_zonal_oracle,
)


JSON_REPORT = ROOT / "publication" / "prompt103-independent-zonal-validation-report.json"
MARKDOWN_REPORT = ROOT / "docs" / "scientific-readiness" / "PROMPT103_INDEPENDENT_ZONAL_VALIDATION_REPORT.md"
SEEDS = (7, 19, 101, 2026)
TOLERANCES = {
    "energy_mwh": 1e-6,
    "cost_gbp": 1e-5,
    "objective_relative": 1e-8,
}


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _comparison_record(name: str, declaration: dict[str, object]) -> dict[str, object]:
    production = production_solution(declaration)
    oracle = solve_zonal_oracle(declaration)
    comparison = compare_zonal_solutions(
        declaration, production, oracle, tolerances=TOLERANCES
    )
    record: dict[str, object] = {
        "name": name,
        "declaration_sha256": _digest(declaration),
        "declaration": declaration,
        "comparison": comparison,
    }
    if not comparison["passed"]:
        record["disagreement_evidence"] = {
            "production_declaration": declaration,
            "oracle_declaration": declaration,
            "production_result": production,
            "oracle_result": oracle,
        }
    return record


def _mutation_records(declaration: dict[str, object]) -> list[dict[str, object]]:
    valid = solve_zonal_oracle(declaration)
    mutations = {
        "zonal_balance": ("final_dispatch_mwh_by_asset", "thermal-south", 1.0),
        "forward_limit": ("corridor_flow_mwh_by_id", "north-mid", 100.0),
        "reverse_limit": ("corridor_flow_mwh_by_id", "north-mid", -100.0),
        "cutset_incidence": ("boundary_transfer_mwh_by_id", "B_NORTH", 100.0),
        "storage_efficiency": ("final_soc_mwh_by_asset", "battery", 0.321),
        "storage_power": ("storage_discharge_mwh_by_asset", "battery", 100.0),
        "storage_energy": ("final_soc_mwh_by_asset", "battery", 100.0),
        "interconnector_sign": ("final_dispatch_mwh_by_asset", "import-fr", 100.0),
        "realised_availability": ("final_dispatch_mwh_by_asset", "thermal-south", 100.0),
        "voll": ("primary_objective_gbp", None, -1.0),
        "secondary_tie_breaking": ("secondary_objective_mwh", None, 1e6),
    }
    records: list[dict[str, object]] = []
    for name, (field, key, value) in mutations.items():
        candidate = copy.deepcopy(valid)
        if key is None:
            candidate[field] = value
        else:
            candidate[field][key] = value
        audit = audit_zonal_candidate(declaration, candidate)
        records.append({
            "name": name,
            "detected": not audit["passed"],
            "mutated_field": field,
            "mutated_key": key,
            "audit": audit,
        })
    return records


def _failure_records() -> list[dict[str, object]]:
    base = random_convex_case(9)
    cases: list[tuple[str, dict[str, object], type[Exception]]] = []
    malformed = copy.deepcopy(base)
    malformed["domain_payload"]["schema_version"] = "wrong"
    cases.append(("malformed_schema", malformed, ValueError))
    impossible = copy.deepcopy(base)
    impossible["initial_soc_mwh_by_asset"]["battery"] = 1e6
    cases.append(("impossible_opening_soc", impossible, ValueError))
    isolated = copy.deepcopy(base)
    isolated["domain_payload"]["network_pack"]["corridors"] = []
    isolated["domain_payload"]["network_pack"]["cutsets"] = []
    cases.append(("unexplained_isolated_zone", isolated, ValueError))

    records: list[dict[str, object]] = []
    for name, declaration, expected in cases:
        try:
            solve_zonal_oracle(declaration)
        except Exception as exc:  # the exact type and declaration are evidence
            records.append({
                "name": name,
                "passed": isinstance(exc, expected),
                "expected_exception": expected.__name__,
                "actual_exception": type(exc).__name__,
                "message": str(exc),
                "declaration_sha256": _digest(declaration),
                "declaration": declaration,
            })
        else:
            records.append({
                "name": name,
                "passed": False,
                "expected_exception": expected.__name__,
                "actual_exception": None,
                "declaration_sha256": _digest(declaration),
                "declaration": declaration,
            })

    zero_flex = copy.deepcopy(analytical_cases()["signed-import"])
    zero_flex["bids"] = []
    zero_result = solve_zonal_oracle(zero_flex)
    records.append({
        "name": "all_zero_flexibility_uses_voll",
        "passed": bool(audit_zonal_candidate(zero_flex, zero_result)["passed"]),
        "blackout_mwh": zero_result["blackout_mwh"],
        "declaration_sha256": _digest(zero_flex),
        "declaration": zero_flex,
    })

    infeasible = copy.deepcopy(analytical_cases()["signed-import"])
    infeasible["bids"] = []
    infeasible["real_demand_mwh"] = 0.0
    infeasible["domain_payload"]["real_demand_mwh_by_zone"] = {"gb": 0.0}
    network = infeasible["domain_payload"]["network_pack"]
    network["zonal_demand"]["demand_mwh_by_zone"] = {"gb": [0.0]}
    network["zonal_demand"]["national_demand_mwh"] = [0.0]
    network["scientific_sha256"] = ""
    network["scientific_sha256"] = _digest(network)
    try:
        solve_zonal_oracle(infeasible)
    except RuntimeError as exc:
        records.append({
            "name": "physically_infeasible_surplus_without_downward_action",
            "passed": True,
            "expected_exception": "RuntimeError",
            "actual_exception": type(exc).__name__,
            "message": str(exc),
            "declaration_sha256": _digest(infeasible),
            "declaration": infeasible,
        })
    else:
        records.append({
            "name": "physically_infeasible_surplus_without_downward_action",
            "passed": False,
            "declaration_sha256": _digest(infeasible),
            "declaration": infeasible,
        })
    return records


def build_report(*, run_chronology: bool = True) -> dict[str, object]:
    analytical = [
        _comparison_record(name, declaration)
        for name, declaration in analytical_cases().items()
    ]
    random_cases = [
        _comparison_record(f"seed-{seed}", random_convex_case(seed))
        for seed in SEEDS
    ]
    mutation_cases = _mutation_records(random_convex_case(41))
    failures = _failure_records()
    chronology = (
        [
            run_sequential_soc_case(24, seed=24, tolerances=TOLERANCES),
            run_sequential_soc_case(168, seed=168, tolerances=TOLERANCES),
        ]
        if run_chronology
        else []
    )
    valid_pass = all(
        bool(row["comparison"]["passed"])
        for row in analytical + random_cases
    )
    chronology_pass = run_chronology and all(bool(row["passed"]) for row in chronology)
    mutation_pass = all(bool(row["detected"]) for row in mutation_cases)
    failure_pass = all(bool(row["passed"]) for row in failures)
    gate = valid_pass and chronology_pass and mutation_pass and failure_pass
    try:
        import scipy
        scipy_version: str | None = scipy.__version__
    except ModuleNotFoundError:
        scipy_version = None
    return {
        "schema_version": "value.prompt103-independent-zonal-validation-report/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": "GO" if gate else "NO-GO",
        "release_gate": {
            "prompt_104_allowed": gate,
            "blocking": True,
            "reason": (
                "Independent zonal formulation matches and all adversarial gates pass."
                if gate
                else "At least one independent zonal validation gate failed."
            ),
        },
        "scope": {
            "production_solver": "SciPy/HiGHS",
            "independent_oracle": "PuLP/CBC",
            "chronology_semantics": "independent half-hour solves with prior-period SOC only",
            "future_information_used": False,
        },
        "versions": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pulp": pulp.__version__,
            "cbc": cbc_identity(),
            "scipy": scipy_version,
        },
        "tolerances": TOLERANCES,
        "seeds": list(SEEDS),
        "analytical_cases": analytical,
        "random_convex_cases": random_cases,
        "chronology_cases": chronology,
        "mutation_cases": mutation_cases,
        "failure_cases": failures,
        "classifications": sorted({
            str(row["comparison"]["classification"])
            for row in analytical + random_cases
        } | {
            str(period["classification"])
            for case in chronology for period in case["comparisons"]
        }),
        "summary": {
            "analytical_passed": sum(bool(row["comparison"]["passed"]) for row in analytical),
            "analytical_total": len(analytical),
            "random_passed": sum(bool(row["comparison"]["passed"]) for row in random_cases),
            "random_total": len(random_cases),
            "chronology_periods_passed": sum(
                bool(period["passed"]) for case in chronology for period in case["comparisons"]
            ),
            "chronology_periods_total": sum(int(case["periods"]) for case in chronology),
            "mutations_detected": sum(bool(row["detected"]) for row in mutation_cases),
            "mutations_total": len(mutation_cases),
            "failure_behaviours_passed": sum(bool(row["passed"]) for row in failures),
            "failure_behaviours_total": len(failures),
        },
    }


def _markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    gate = report["release_gate"]
    return f"""# VALUE independent zonal solver validation

Date: {report['generated_at_utc']}

Scope: Prompt 103

## Decision

**{report['decision']}** — {gate['reason']}

This validation independently rebuilds the declared zonal redispatch problem in
PuLP and solves it with CBC. It does not import the production formulation or
its HiGHS matrices. The chronological cases remain separate half-hour auctions:
only the previous period's realised SOC is carried forward.

## Results

| Gate | Result |
| --- | ---: |
| Hand-solvable cases | {summary['analytical_passed']} / {summary['analytical_total']} |
| Seeded random convex cases | {summary['random_passed']} / {summary['random_total']} |
| Sequential half-hours (24 h + 168 h) | {summary['chronology_periods_passed']} / {summary['chronology_periods_total']} |
| Deliberate mutations detected | {summary['mutations_detected']} / {summary['mutations_total']} |
| Malformed, zero-flexibility and infeasible behaviours | {summary['failure_behaviours_passed']} / {summary['failure_behaviours_total']} |

## Declared tolerances

- Energy and physical quantities: `{report['tolerances']['energy_mwh']}` MWh
- Absolute objective tolerance: `{report['tolerances']['cost_gbp']}` GBP
- Relative objective tolerance: `{report['tolerances']['objective_relative']}`

## Interpretation

Passing this gate validates the implemented lossless transport/cut-set
redispatch problem against an independently assembled LP. It does not convert
the model into AC or DC power flow, validate GB security constraints, or add
perfect foresight. Prompt 104 may proceed only when the machine-readable
`prompt_104_allowed` field is true.

Machine-readable evidence: `publication/prompt103-independent-zonal-validation-report.json`.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-chronology",
        action="store_true",
        help="Developer-only fast check; always yields a blocking NO-GO report.",
    )
    args = parser.parse_args()
    report = build_report(run_chronology=not args.skip_chronology)
    JSON_REPORT.parent.mkdir(parents=True, exist_ok=True)
    MARKDOWN_REPORT.parent.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    MARKDOWN_REPORT.write_text(_markdown(report), encoding="utf-8", newline="")
    print(json.dumps({
        "decision": report["decision"],
        "summary": report["summary"],
        "json_report": str(JSON_REPORT),
        "markdown_report": str(MARKDOWN_REPORT),
    }, indent=2))
    return 0 if report["release_gate"]["prompt_104_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
