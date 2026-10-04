"""Audit full-scale VALUE runs used by Prompt 52.

This layers investment-owner, shared-headroom and planning-carry checks over the
existing Prompt 46 physical, cost, carbon and bundle audit.  It reads completed
artifacts only and fails closed when a required relationship cannot be proved.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from audit_prompt46_release import ECONOMIC_FIELDS, audit_run, load_json


TOLERANCE_MW = 1e-6


def _close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=TOLERANCE_MW)


def _investment_year(result: Mapping[str, Any]) -> dict[str, Any]:
    investment = result["investment"]
    extensions = investment.get("extensions", {})
    proposals = list(investment.get("proposals", []))
    admission = result["planning_admission"]
    admitted = list(admission.get("admitted_projects", []))
    next_projects = list(result["next_state"].get("planning_projects", []))

    proposed_mw: dict[str, float] = defaultdict(float)
    proposal_counts: dict[str, int] = defaultdict(int)
    owner_ids: set[str] = set()
    missing_economics: list[str] = []
    missing_owner: list[str] = []
    for proposal in proposals:
        technology = str(proposal["technology"])
        proposed_mw[technology] += float(proposal["capacity_mw"])
        proposal_counts[technology] += 1
        economic = proposal.get("extensions", {})
        owner = economic.get("investment_owner_id")
        if owner:
            owner_ids.add(str(owner))
        else:
            missing_owner.append(str(proposal["proposal_id"]))
        if any(field not in economic for field in ECONOMIC_FIELDS):
            missing_economics.append(str(proposal["proposal_id"]))

    initial = {
        str(key): float(value)
        for key, value in extensions.get("initial_headroom_mw_by_technology", {}).items()
    }
    remaining = {
        str(key): float(value)
        for key, value in extensions.get("remaining_headroom_mw_by_technology", {}).items()
    }
    headroom_rows: dict[str, Any] = {}
    for technology in sorted(set(initial) | set(remaining)):
        before = initial.get(technology, 0.0)
        used = proposed_mw.get(technology, 0.0)
        after = remaining.get(technology, 0.0)
        expected = max(0.0, before - used)
        headroom_rows[technology] = {
            "initial_mw": before,
            "proposed_mw": used,
            "remaining_mw": after,
            "expected_remaining_mw": expected,
            "within_shared_budget": used <= before + TOLERANCE_MW,
            "reconciled": _close(after, expected),
        }

    proposal_ids = {str(row["proposal_id"]) for row in proposals}
    admitted_ids = {str(row["project_id"]) for row in admitted}
    next_project_ids = {str(row["project_id"]) for row in next_projects}
    rejected_ids = {str(row["proposal_id"]) for row in admission.get("rejected_proposals", [])}
    accepted_ids = proposal_ids - rejected_ids
    missing_from_admission = sorted(accepted_ids - admitted_ids)
    missing_from_next_state = sorted(admitted_ids - next_project_ids)

    passed = (
        not missing_economics
        and not missing_owner
        and not missing_from_admission
        and not missing_from_next_state
        and all(row["within_shared_budget"] and row["reconciled"] for row in headroom_rows.values())
    )
    return {
        "year": int(result["year"]),
        "passed": passed,
        "grouped_investment_owners": int(extensions.get("grouped_investment_owners", 0)),
        "owners_with_proposals": len(owner_ids),
        "proposal_count": len(proposals),
        "proposal_capacity_mw": sum(proposed_mw.values()),
        "proposals_by_technology": {
            technology: {
                "count": proposal_counts[technology],
                "capacity_mw": proposed_mw[technology],
            }
            for technology in sorted(proposed_mw)
        },
        "ineligible_groups": list(extensions.get("ineligible_groups", [])),
        "missing_economic_records": missing_economics,
        "missing_investment_owner_ids": missing_owner,
        "admitted_projects": len(admitted),
        "rejected_proposals": len(rejected_ids),
        "missing_from_admission": missing_from_admission,
        "missing_from_next_state": missing_from_next_state,
        "shared_headroom": headroom_rows,
    }


def audit_prompt52_run(path: Path, expected_years: int) -> dict[str, Any]:
    base = audit_run(path, expected_years)
    results_path = path / "year-results-v2.json"
    if not results_path.is_file():
        return {
            "schema_version": "value.prompt52-run-audit/v1",
            "path": str(path),
            "passed": False,
            "base_audit": base,
            "missing_artifact": str(results_path),
        }
    results = load_json(results_path)
    investment = [_investment_year(row) for row in results]
    total_proposals = sum(row["proposal_count"] for row in investment)
    passed = bool(base.get("passed")) and all(row["passed"] for row in investment) and total_proposals > 0
    return {
        "schema_version": "value.prompt52-run-audit/v1",
        "path": str(path),
        "expected_years": expected_years,
        "passed": passed,
        "decision": "PASS" if passed else "FAIL",
        "gate_requirements": {
            "base_physical_cost_carbon_bundle_audit": bool(base.get("passed")),
            "investment_and_headroom_closure": all(row["passed"] for row in investment),
            "at_least_one_model_investment_proposal": total_proposals > 0,
        },
        "total_model_investment_proposals": total_proposals,
        "base_audit": base,
        "investment_audit": investment,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-years", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_prompt52_run(args.run_dir.resolve(), args.expected_years)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"decision": report["decision"], "output": str(output)}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
