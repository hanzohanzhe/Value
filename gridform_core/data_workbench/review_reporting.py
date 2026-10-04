"""Deterministic machine and human review artifacts for candidate promotion."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import ValidationReport


def _write(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def render_candidate_review(
    candidate_root: Path,
    report: ValidationReport,
    output_root: Path,
) -> dict[str, str]:
    candidate = json.loads(
        (Path(candidate_root) / "workbench-candidate.json").read_text(encoding="utf-8")
    )
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "candidate_inventory": candidate.get("candidate_inventory", []),
        "validation": report.to_dict(),
        "version_diff": {
            "parent_candidate_id": candidate.get("parent_candidate_id"),
            "current_candidate_id": candidate.get("candidate_id"),
            "status": "initial_candidate" if not candidate.get("parent_candidate_id") else "comparison_required",
        },
        "rights": candidate.get("source_rights", []),
        "assumptions": {
            "requested_waivers": candidate.get("requested_waivers", []),
        },
        "reconciliation": candidate.get("scientific_reconciliation", {}),
    }
    artifact_files: dict[str, str] = {}
    for name, payload in artifacts.items():
        filename = name.replace("_", "-") + ".json"
        _write(output / filename, payload)
        artifact_files[name] = filename
    blocking = [issue.code for issue in report.issues]
    actions = sorted({issue.repair for issue in report.issues})
    package = {
        "schema_version": "value.data-candidate-review/v1",
        "candidate_id": report.candidate_id,
        "status": report.status,
        "candidate_inventory": candidate.get("candidate_inventory", []),
        "blocking_reasons": blocking,
        "required_actions": actions,
        "artifacts": artifact_files,
    }
    _write(output / "candidate-review.json", package)
    lines = [
        "# Data candidate review",
        "",
        f"Candidate: `{report.candidate_id}`",
        "",
        f"Status: **{report.status}**",
        "",
        "## What can be used now",
        "",
    ]
    inventory = candidate.get("candidate_inventory", [])
    for item in inventory:
        lines.append(
            f"- {item.get('item_id')}: {', '.join(str(value) for value in item.get('usable_for', []))}"
        )
    lines.extend(["", "## What is blocked", ""])
    lines.extend(f"- {issue.code}: {issue.message}" for issue in report.issues)
    lines.extend(["", "## Required actions", ""])
    lines.extend(f"- {action}" for action in actions)
    (output / "candidate-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "machine_review": "candidate-review.json",
        "human_review": "candidate-review.md",
        **artifact_files,
    }
