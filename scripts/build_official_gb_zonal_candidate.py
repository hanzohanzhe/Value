"""Attempt a frozen official GB zonal build without inventing missing inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.data_workbench.local_service import LocalDataWorkbenchService
from gridform_core.data_workbench.state import resolve_data_workbench_root


BUILD_LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")


def attempt_official_build(
    *, state_root: Path, build_label: str, inventory_key: str
) -> dict[str, object]:
    state = Path(state_root).expanduser().resolve()
    if not BUILD_LABEL.fullmatch(build_label):
        raise ValueError("Build label must be a short portable identifier")
    inventory = state / "inventories" / inventory_key
    if not inventory.is_file():
        return {
            "schema_version": "value.data-official-build-attempt/v1",
            "status": "stopped_missing_normalized_inventory",
            "candidate_built": False,
            "build_label": build_label,
            "inventory_key": inventory_key,
            "required_actions": [
                "Fetch and review every required official revision",
                "Transform official and model-local evidence into value.gb-zonal-source-inventory/v1",
                "Record object hashes, provenance and redistribution decisions before retrying",
            ],
        }
    service = LocalDataWorkbenchService(state)
    result = service.compile(
        {
            "schema_version": "value.data-compile-request/v1",
            "recipe_id": "prompt98-gb-zonal",
            "inventory_key": inventory_key,
            "candidate_name": build_label,
        }
    )
    return {
        "schema_version": "value.data-official-build-attempt/v1",
        "status": "candidate_built_awaiting_review",
        "candidate_built": True,
        "build_label": build_label,
        "inventory_key": inventory_key,
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-label", required=True)
    parser.add_argument("--inventory-key", default="official-uk-network-v1.json")
    parser.add_argument("--state-root", type=Path, default=resolve_data_workbench_root())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = attempt_official_build(
        state_root=args.state_root,
        build_label=args.build_label,
        inventory_key=args.inventory_key,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["candidate_built"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
