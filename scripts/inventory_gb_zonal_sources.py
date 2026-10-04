"""Inventory pinned local inputs for the Prompt 98 GB zonal benchmark.

This command performs no network access and does not copy source data.  It
checks the candidate locations declared in the source plan, records hashes for
objects that are present, and writes a privacy-safe readiness inventory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.gb_zonal_pack_builder import (  # noqa: E402
    REQUIRED_SOURCE_ROLES,
    canonical_json,
    sha256_file,
)


DEFAULT_PLAN = ROOT / "publication" / "prompt98-gb-zonal-source-plan.json"
DEFAULT_OUTPUT = ROOT / "publication" / "prompt98-gb-zonal-source-inventory.json"


def _expand(locator: str) -> Path:
    expanded = Path(os.path.expandvars(locator)).expanduser()
    return expanded if expanded.is_absolute() else ROOT / expanded


def inventory(plan_path: Path) -> dict[str, object]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    gaps: list[dict[str, object]] = []
    for role in REQUIRED_SOURCE_ROLES:
        source = dict(plan.get("sources", {}).get(role, {}))
        locators = [str(item) for item in source.pop("candidate_locations", [])]
        found: list[tuple[str, Path]] = []
        for locator in locators:
            path = _expand(locator)
            if path.is_file():
                found.append((locator, path))
        preferred = found[0] if found else None
        builder_ready = bool(source.pop("builder_ready", False)) and preferred is not None
        access_result = (
            "present" if builder_ready else
            "candidate_found_requires_transform" if preferred is not None else
            "missing"
        )
        row: dict[str, object] = {
            "role": role,
            "required": True,
            **source,
            "access_result": access_result,
            "candidate_locator": preferred[0] if preferred else None,
            "sha256": sha256_file(preferred[1]) if preferred else None,
            "bytes": preferred[1].stat().st_size if preferred else None,
            "duplicate_candidates_found": len(found),
            "local_path": None,
        }
        rows.append(row)
        if access_result != "present":
            gaps.append({
                "role": role,
                "reason": access_result,
                "required_action": source.get("required_action"),
            })
    return {
        "schema_version": "value.gb-zonal-source-readiness/v1",
        "inventory_id": "prompt98-local-source-readiness-20260821",
        "offline_only": True,
        "runtime_downloads": False,
        "status": "ready_for_candidate_build" if not gaps else "stopped_missing_or_unprepared_sources",
        "required_roles": len(REQUIRED_SOURCE_ROLES),
        "builder_ready_roles": len(REQUIRED_SOURCE_ROLES) - len(gaps),
        "gaps": gaps,
        "objects": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = inventory(args.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(result), encoding="utf-8", newline="")
    print(canonical_json({
        "status": result["status"],
        "builder_ready_roles": result["builder_ready_roles"],
        "required_roles": result["required_roles"],
        "output": args.output.as_posix(),
    }), end="")


if __name__ == "__main__":
    main()
