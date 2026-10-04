"""Summarise local Data Workbench evidence without making readiness claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.data_workbench.local_service import LocalDataWorkbenchService
from gridform_core.data_workbench.state import resolve_data_workbench_root


def audit_release(state_root: Path) -> dict[str, object]:
    state = Path(state_root).expanduser().resolve()
    service = LocalDataWorkbenchService(state)
    source_ids = [str(row["source_id"]) for row in service.sources()["sources"]]
    revisions = list(service.revisions()["revisions"])
    pinned = {
        str(row.get("source_id"))
        for row in revisions
        if isinstance(row, dict) and row.get("object_key")
    }
    rights_pending: list[str] = []
    accepted_rights = {"redistributable", "pointer_only", "local_use_only"}
    for path in sorted((state / "receipts").glob("*/*.json")):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if str(receipt.get("redistribution_decision") or "") not in accepted_rights:
            rights_pending.append(
                f"{receipt.get('source_id') or path.parent.name}@{receipt.get('revision_id') or path.stem}"
            )
    candidates = list(service.candidates()["candidates"])
    bundles = list(service.bundles()["bundles"])
    candidate_status: list[dict[str, object]] = []
    for row in candidates:
        candidate_id = str(row.get("candidate_id") or "")
        validation = service.validate(candidate_id)
        candidate_status.append(
            {
                "candidate_id": candidate_id,
                "status": validation["status"],
                "gate_results": validation["gate_results"],
                "blocking_codes": [issue["code"] for issue in validation["issues"]],
            }
        )
    if pinned != set(source_ids):
        decision = "stopped_missing_official_sources"
    elif not candidates:
        decision = "stopped_before_candidate_build"
    elif not bundles:
        decision = "stopped_awaiting_owner_promotion"
    else:
        decision = "local_bundle_installed_not_scientific_baseline"
    return {
        "schema_version": "value.data-workbench-release-audit/v1",
        "decision": decision,
        "scientific_readiness_claim": False,
        "official_sources": {
            "registered": len(source_ids),
            "pinned": len(pinned),
            "missing_or_unpinned": sorted(set(source_ids) - pinned),
            "rights_review_pending": rights_pending,
        },
        "candidates": candidate_status,
        "installed_bundles": len(bundles),
        "owner_promotion_required": not bool(bundles),
        "solver_validation": "out_of_scope",
        "annual_and_ten_year_runs": "out_of_scope",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=resolve_data_workbench_root())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_release(args.state_root)
    encoded = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
