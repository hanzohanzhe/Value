"""Project-composed Scheme C annual-run boundary.

This module runs a modular copy of the verified Scheme C research kernel.
The original compatibility copy remains untouched.  Research-project module
IDs are resolved to executable stages before the copied annual loop starts.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ...errors import CompatibilityError, DeprecatedRouteError
from ...execution_identity import scheme_c_execution_identity
from ...parameters import (
    ResolvedParameterSet,
    SchemeCLegacyParameterAdapter,
    resolve_scheme_c_parameters,
    scheme_c_model_card,
)
from ...storage_audit import export_storage_cost_audit
from ...v2.module_manifest import ResolvedModuleGraph
from .scheme_c_modules import build_retained_reference_runtime
from .runtime_overlay import verify_runtime_overlay
from .scheme_c_context import (
    LegacyConfigSession,
    build_scheme_c_run_context,
    persist_or_verify_context,
    stage_reference_named_inputs,
)


@dataclass(frozen=True)
class ModularRunRequest:
    pack_root: Path
    output_dir: Path
    module_ids: Mapping[str, str]
    start_year: int = 2025
    end_year: int = 2026
    periods: int = 17_520
    scenario: str = "existing_decarb_base"
    parameter_overrides: Mapping[str, object] = field(default_factory=dict)
    runtime_options: Mapping[str, object] = field(default_factory=dict)
    project_id: str = "direct-run"
    run_id: str = "direct-run"
    resolution_graph: ResolvedModuleGraph | None = field(default=None, repr=False, compare=False)
    explicit_reference_comparison: bool = False


def run_modular_scheme_c(request: ModularRunRequest) -> dict:
    """Resolve selected modules, run the copied yearly chain, and parse results."""

    if not request.explicit_reference_comparison:
        raise DeprecatedRouteError(
            "The copied Scheme C loop is no longer a project execution route. "
            "Use gridform_core.application.run_project_application, or invoke "
            "gridform_core.reference_comparison explicitly for retained evidence."
        )

    if sys.version_info[:2] != (3, 10):
        raise CompatibilityError(
            "Authoritative Scheme C runs require Python 3.10, matching the "
            "2026-07-18 retained-output environment. Refusing an unverified "
            f"Python {sys.version_info.major}.{sys.version_info.minor} run."
        )
    if request.end_year < request.start_year:
        raise ValueError("end_year must be greater than or equal to start_year")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    overlay = verify_runtime_overlay()
    (request.output_dir / "runtime-overlay.json").write_text(
        json.dumps(overlay, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    overrides = dict(request.parameter_overrides)
    if request.scenario != "existing_decarb_base" and not {
        "scenario", "scenario.id"
    }.intersection(overrides):
        overrides["scenario.id"] = request.scenario
    resolved = resolve_scheme_c_parameters(
        request.pack_root,
        overrides,
        request.runtime_options,
        periods_per_year=int(request.periods),
    )
    execution_identity = scheme_c_execution_identity()
    resolved_run = {
        "schema_version": "gridform.resolved-run/v2",
        "run_id": request.run_id,
        "project_id": request.project_id,
        "data_pack": str(request.pack_root.resolve()),
        "start_year": int(request.start_year),
        "end_year": int(request.end_year),
        "modules": dict(request.module_ids),
        "execution_source_identity": {
            "artifact_id": "execution-identity.json",
            "sha256": execution_identity["sha256"],
        },
        **resolved.to_dict(),
    }
    resume_identity_sha256 = hashlib.sha256(
        json.dumps(
            {
                "project_id": request.project_id,
                "data_pack_manifest": json.loads((request.pack_root / "manifest.json").read_text(encoding="utf-8")),
                "start_year": request.start_year,
                "end_year": request.end_year,
                "modules": dict(sorted(request.module_ids.items())),
                "scientific_parameters": resolved.to_dict()["scientific_parameters"],
                "runtime_options": resolved.to_dict()["runtime_options"],
                "execution_source_sha256": execution_identity["sha256"],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    execution_identity["resume_identity_sha256"] = resume_identity_sha256
    (request.output_dir / "execution-identity.json").write_text(
        json.dumps(execution_identity, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # The complete effective configuration exists before any model import or
    # execution, so a validation/launch failure still leaves reproducible evidence.
    (request.output_dir / "resolved-run.json").write_text(
        json.dumps(resolved_run, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (request.output_dir / "scheme-c-model-card.json").write_text(
        json.dumps(scheme_c_model_card(resolved), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence_path = request.output_dir / "module-events.jsonl"
    runtime = build_retained_reference_runtime(
        request.module_ids,
        evidence_path,
        resolved.scientific.values,
    )
    parameter_adapter = SchemeCLegacyParameterAdapter(resolved)
    work = stage_reference_named_inputs(request.pack_root, request.output_dir)
    env = {
        "PYTHONHASHSEED": "0",
        "START_YEAR": str(request.start_year),
        "END_YEAR": str(request.end_year),
        "OUTPUT_DIR": str(request.output_dir.resolve()),
        "CAPITAL_COST_PROFILE": "arup_medium",
        "FAST_ANALYSIS_OUTPUT": "1",
        "TRACE_FORMAT": "sqlite",
        "PYTHONIOENCODING": "utf-8",
        "VALIDATION_MODE": "0",
        "VALIDATION_DISABLE_EXTERNAL_PROJECTS": "0",
        "VALIDATION_HISTORICAL_DECARB": "0",
        "VALIDATION_INITIAL_CAPACITY_YEAR": "",
        "VALIDATION_REPD_FILE": "",
        "RUN_SUITE": "",
        "GRIDFORM_RESUME_IDENTITY_SHA256": resume_identity_sha256,
    }
    env.update(parameter_adapter.environment(start_year=request.start_year))
    context = build_scheme_c_run_context(
        run_id=request.run_id,
        project_id=request.project_id,
        start_year=request.start_year,
        end_year=request.end_year,
        periods=request.periods,
        scenario_id=request.scenario,
        pack_root=request.pack_root,
        output_dir=request.output_dir,
        reference_work_dir=work,
        module_ids=request.module_ids,
        scientific_parameters=resolved.scientific.values,
        runtime_options=resolved.runtime.values,
        environment=env,
    )
    persist_or_verify_context(context)
    resolved_run["scheme_c_run_context_sha256"] = context.context_sha256
    execution_identity["scheme_c_run_context_sha256"] = context.context_sha256
    (request.output_dir / "resolved-run.json").write_text(
        json.dumps(resolved_run, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (request.output_dir / "execution-identity.json").write_text(
        json.dumps(execution_identity, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    try:
        with LegacyConfigSession(context, parameter_adapter, runtime):
            # A web worker normally launches each scientific run in a fresh
            # process.  Library users and the full test suite may execute more
            # than one run in one interpreter, so re-evaluate environment-bound
            # year/scenario/output constants and clear module-level histories.
            from .runtime_compat import modular_case3
            modular_case3 = importlib.reload(modular_case3)
            modular_case3.main()
    finally:
        # SQLite keeps an exclusive Windows file handle until explicitly closed.
        # Closing here also guarantees all batched planning events are durable.
        runtime.close()
    storage_audit_path = export_storage_cost_audit(
        request.output_dir / "checkpoints",
        request.output_dir / "storage" / "cost-audit.json",
        trust_local_checkpoints=True,
        run_id=request.run_id,
    )
    result = load_modular_results(request.output_dir, request.scenario)
    market_metadata_path = request.output_dir / "market" / "metadata.json"
    market_metadata = (
        json.loads(market_metadata_path.read_text(encoding="utf-8"))
        if market_metadata_path.exists()
        else {"trace_level": "off", "rows": 0, "bytes": 0, "writer_seconds": 0.0}
    )
    result["runtime"] = {
        "engine": "scheme-c-project-composed/v1",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "periods_per_year": int(request.periods),
        "start_year": int(request.start_year),
        "end_year": int(request.end_year),
        "data_pack": str(request.pack_root.resolve()),
        "modules": runtime.selected,
        "module_evidence": str(evidence_path.resolve()),
        "resolved_run": str((request.output_dir / "resolved-run.json").resolve()),
        "model_card": str((request.output_dir / "scheme-c-model-card.json").resolve()),
        "market_ledger": market_metadata,
        "storage_cost_audit": {
            "artifact_id": storage_audit_path.relative_to(request.output_dir).as_posix(),
        },
    }
    (request.output_dir / "modular-run.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _numbers(row: dict) -> dict:
    converted = {}
    for key, value in row.items():
        try:
            converted[key] = float(value)
        except (TypeError, ValueError):
            converted[key] = value
    return converted


def load_modular_results(output_dir: Path, scenario: str) -> dict:
    suffix = f"case3_v2_{scenario}"
    costs = [_numbers(row) for row in _read_csv(output_dir / f"system_cost_history_{suffix}.csv")]
    capacities = [_numbers(row) for row in _read_csv(output_dir / f"capacity_history_{suffix}.csv")]
    investment_path = output_dir / "investment_analysis_trace.sqlite"
    investments: list[dict] = []
    if investment_path.exists():
        with sqlite3.connect(investment_path) as connection:
            query = """
                SELECT year, asset_type,
                       SUM(current_capacity),
                       SUM(suggested_new_capacity),
                       SUM(suggested_new_capacity - current_capacity)
                FROM investment_analysis
                GROUP BY year, asset_type
                ORDER BY year, asset_type
            """
            for year, technology, current, suggested, addition in connection.execute(query):
                investments.append({
                    "year": int(year),
                    "technology": technology,
                    "current_capacity_mw": float(current or 0),
                    "suggested_capacity_mw": float(suggested or 0),
                    "suggested_addition_mw": float(addition or 0),
                })
    return {
        "engine": "scheme-c-authoritative-packaged-kernel",
        "scenario": scenario,
        "system_cost_history": costs,
        "capacity_history": capacities,
        "investment_decisions": investments,
    }
