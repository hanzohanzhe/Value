"""Explicit retained VALUE comparison command; never a project PSM module."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .builtin.scheme_c_1000twh.modular_run import ModularRunRequest, run_modular_scheme_c
from .v2.module_manifest import workspace_registry
from .runtime_capabilities import SCHEME_C_REFERENCE, require_runtime_capability


REFERENCE_ID = "doctoral-reproduction-comparison"


def run_reference_comparison(
    project: dict[str, object], *, pack_root: Path, output_dir: Path,
    run_id: str, start_year: int, end_year: int, periods: int,
) -> dict[str, object]:
    runtime_capability = require_runtime_capability(SCHEME_C_REFERENCE)
    pack_root = pack_root.resolve()
    output_dir = output_dir.resolve()
    selected = dict(project.get("modules") or {})
    selected.pop("transition", None)
    selected.setdefault("storage_cost", "dynamic-annual-storage-cost")
    graph = workspace_registry().resolve_selection({
        **selected,
        "transition": str(dict(project.get("modules") or {}).get("transition") or "value-annual-state-transition"),
    })
    result = run_modular_scheme_c(ModularRunRequest(
        pack_root=pack_root,
        output_dir=output_dir,
        module_ids=selected,
        start_year=start_year,
        end_year=end_year,
        periods=periods,
        scenario=str(project.get("scenario_id") or "existing_decarb_base"),
        parameter_overrides=dict(project.get("parameters") or {}),
        runtime_options=dict(project.get("runtime_options") or {}),
        project_id=str(project.get("id") or "reference"),
        run_id=run_id,
        resolution_graph=graph,
        explicit_reference_comparison=True,
    ))
    result.update({
        "execution_kind": "reference_comparison",
        "reference_identity": REFERENCE_ID,
        "artifact_classification": "reference_compatibility",
        "selectable_as_project_psm": False,
        "runtime_capability": runtime_capability,
    })
    (output_dir / "reference-comparison.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return result


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run the retained VALUE reference comparison")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="doctoral-reproduction")
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--periods", type=int, default=2)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    project = json.loads(args.project.read_text(encoding="utf-8"))
    run_reference_comparison(
        project, pack_root=args.pack, output_dir=args.output, run_id=args.run_id,
        start_year=args.start_year, end_year=args.end_year, periods=args.periods,
    )


if __name__ == "__main__":
    main()
