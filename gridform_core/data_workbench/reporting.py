"""Human and machine evidence emitted by Data Workbench stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import SourceDefinition, SourceRevision
from .registry import JsonSourceRegistry, package_registry_root


def render_discovery_reports(
    revisions_by_source: Mapping[str, Sequence[SourceRevision]],
    output_root: Path,
    *,
    source_definitions: Mapping[str, SourceDefinition] | None = None,
) -> dict[str, str]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    packaged = JsonSourceRegistry(package_registry_root("uk-network"))
    known = {item.source_id: item for item in packaged.list_sources()}
    known.update(source_definitions or {})
    candidate_inventory: list[dict[str, object]] = []
    revision_rows: list[dict[str, object]] = []
    for source_id in sorted(revisions_by_source):
        source = known.get(source_id)
        for revision in revisions_by_source[source_id]:
            revision_rows.append(revision.to_dict())
            uses = list(source.candidate_uses) if source else ["source-specific review"]
            candidate_inventory.append(
                {
                    "item_id": f"{source_id}:{revision.revision_id}",
                    "status": revision.status,
                    "usable_for": uses,
                    "not_usable_for": ["formal benchmark before fetch, validation and promotion"],
                    "blocking_reasons": ["raw object is not pinned"] if revision.status == "new" else [],
                    "required_actions": ["fetch and validate selected revision"] if revision.status == "new" else [],
                }
            )
    payload = {
        "schema_version": "value.data-discovery-report/v1",
        "revisions": revision_rows,
        "candidate_inventory": candidate_inventory,
    }
    machine = output_root / "source_discovery_report.json"
    human = output_root / "source_discovery_report.md"
    machine.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Source discovery report", "", "## Candidate inventory", ""]
    for row in candidate_inventory:
        lines.append(f"- **{row['item_id']}** — {row['status']}; usable for: {', '.join(row['usable_for'])}")
    human.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"machine_report": machine.name, "human_report": human.name}
