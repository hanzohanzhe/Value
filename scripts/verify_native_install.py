"""Verify an installed VALUE-native wheel without importing repository helpers."""

from __future__ import annotations

import argparse
import importlib.util
import json

from gridform_core.runtime_capabilities import VALUE_NATIVE, capability_matrix
from gridform_core.v2.module_manifest import workspace_registry


SELECTION = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "storage_cost": "dynamic-annual-storage-cost",
    "transition": "value-annual-state-transition",
}
REFERENCE_IMPORTS = ("matplotlib", "openpyxl", "seaborn")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-no-reference", action="store_true")
    args = parser.parse_args()
    matrix = capability_matrix(selected_module_ids=SELECTION.values())
    native = matrix["capabilities"][VALUE_NATIVE]
    if not native["available"]:
        raise SystemExit(f"VALUE native capability unavailable: {native['corrective_action']}")
    present_reference = [
        name for name in REFERENCE_IMPORTS if importlib.util.find_spec(name) is not None
    ]
    if args.require_no_reference and present_reference:
        raise SystemExit(
            "Reference-only packages unexpectedly installed: "
            + ", ".join(present_reference)
        )
    graph = workspace_registry().resolve_selection(SELECTION)
    if graph.manifest("psm").execution_kind != "live_module":
        raise SystemExit("The installed VALUE PSM is not the live module")
    print(json.dumps({
        "schema_version": "value.native-install-verification/v1",
        "force_native_available": True,
        "python": native["python"],
        "reference_only_imports_present": present_reference,
        "psm": graph.identity("psm").to_dict(),
    }, indent=2))


if __name__ == "__main__":
    main()
