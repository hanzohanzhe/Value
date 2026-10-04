"""Executable Scheme C stage modules used by the modular copied kernel.

The equations remain in the packaged Scheme C copy.  These adapters are the
replaceable invocation boundary: a research project selects their IDs and the
runtime records every stage call with its version and year.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from ...errors import ContractError
from ...market_ledger import (
    MarketLedger,
    create_market_ledger,
    set_active_market_ledger,
)
from ...planning_ledger import PlanningLedger, ensure_project_id
from ...v2.contracts import PlanningEventType, PlanningReasonCode
from ...v2.module_manifest import ResolvedModuleGraph, workspace_registry


MODULE_KINDS = {
    "psm": "psm",
    "investment": "investment",
    "pipeline": "pipeline",
    "vre_cap": "vre_cap",
    "storage_cap": "storage_cap",
    "storage_cost": "storage_cost",
}


class StageEvidence:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, module_id: str, version: str, action: str, **details: Any) -> None:
        row = {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "year": int(os.getenv("SIMULATION_YEAR", os.getenv("START_YEAR", "2025"))),
            "module_id": module_id,
            "module_version": version,
            "action": action,
            **details,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


@dataclass
class ReferenceSchemeCPSMBridge:
    """Private wrapper used only by the explicit retained-kernel command."""

    evidence: StageEvidence
    id: str = "scheme-c-reference-kernel-bridge"
    project_module_id: str = "scheme-c-psm"
    version: str = "5.0.0"
    execution_kind: str = "reference_comparison"
    market_ledger: MarketLedger | None = field(init=False, default=None)
    storage_cost_module_id: str = "dynamic-annual-storage-cost"

    def run(self, implementation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self.market_ledger is None:
            self.market_ledger = create_market_ledger(
                self.evidence.path.parent / "market" / "market.sqlite",
                os.getenv("MARKET_LEDGER_LEVEL", "summary"),
                batch_size=int(os.getenv("MARKET_LEDGER_BATCH_SIZE", "500")),
                balance_tolerance_mwh=float(
                    os.getenv("MARKET_BALANCE_TOLERANCE_MWH", "1e-5")
                ),
                storage_cost_module_id=self.storage_cost_module_id,
                export_format=os.getenv("MARKET_EXPORT_FORMAT", "sqlite"),
            )
            set_active_market_ledger(self.market_ledger)
        self.evidence.record(
            self.id, self.version, "psm.start",
            storage_cost_module_id=self.storage_cost_module_id,
        )
        started = time.perf_counter()
        result = implementation(*args, **kwargs)
        self.evidence.record(
            self.id, self.version, "psm.complete",
            duration_seconds=time.perf_counter() - started,
        )
        return result

    def close(self) -> dict[str, object]:
        if self.market_ledger is None:
            return {}
        metadata = self.market_ledger.close()
        set_active_market_ledger(None)
        self.market_ledger = None
        return metadata


@dataclass
class SchemeCAgentInvestmentModule:
    evidence: StageEvidence
    id: str = "agent-investment"
    version: str = "2.0.0"

    def run(self, implementation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        self.evidence.record(self.id, self.version, "investment.start")
        started = time.perf_counter()
        result = implementation(*args, **kwargs)
        self.evidence.record(
            self.id, self.version, "investment.complete", assets=int(len(result)),
            duration_seconds=time.perf_counter() - started,
        )
        return result


@dataclass
class SchemeCVREExpansionCapModule:
    evidence: StageEvidence
    id: str = "vre-expansion-cap"
    version: str = "2.0.0"
    fraction: float = 0.20

    def calculate(
        self,
        implementation: Callable[..., float],
        real_demand_path: str,
        profile_paths: Mapping[str, str],
    ) -> dict[str, float]:
        started = time.perf_counter()
        limits = {
            technology: self.fraction
            * implementation(real_demand_path, profile_path, negative_threshold=200)
            for technology, profile_path in profile_paths.items()
        }
        self.evidence.record(
            self.id, self.version, "vre_cap.complete", limits_mw=limits,
            duration_seconds=time.perf_counter() - started,
        )
        return limits


@dataclass
class SchemeCStorageExpansionCapModule:
    evidence: StageEvidence
    id: str = "storage-expansion-scheme-c"
    version: str = "4.0.0"
    storage_cost_module_id: str = "dynamic-annual-storage-cost"

    def calculate(
        self, implementation: Callable[..., dict[str, float]], *args: Any, **kwargs: Any
    ) -> dict[str, float]:
        started = time.perf_counter()
        limits = implementation(*args, **kwargs)
        self.evidence.record(
            self.id, self.version, "storage_cap.complete", limits_mw=limits,
            storage_cost_module_id=self.storage_cost_module_id,
            duration_seconds=time.perf_counter() - started,
        )
        return limits


@dataclass
class SchemeCPlanningPipelineModule:
    evidence: StageEvidence
    id: str = "planning-pipeline"
    version: str = "2.0.0"
    ledger: PlanningLedger = field(init=False)

    def __post_init__(self) -> None:
        self.ledger = PlanningLedger(self.evidence.path.parent / "planning")

    @staticmethod
    def _year() -> int:
        return int(os.getenv("SIMULATION_YEAR", os.getenv("START_YEAR", "2025")))

    def begin_year(self, projects: list[dict] | int) -> None:
        project_count = len(projects) if isinstance(projects, list) else int(projects)
        if isinstance(projects, list):
            for project in projects:
                self.ledger.upsert_project(project)
            self.ledger.flush()
        self.evidence.record(
            self.id, self.version, "pipeline.begin_year", projects=project_count
        )

    def record_imports(self, projects: list[dict], *, year: int) -> None:
        self.ledger.record_imports(projects, year=year)

    def record_source_import(self, project: dict, *, year: int) -> None:
        self.ledger.record_source_import(project, year=year)

    def record_source_filter(
        self,
        project: dict,
        *,
        year: int,
        event_type: PlanningEventType,
        reason_code: PlanningReasonCode,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.ledger.record_source_filter(
            project,
            year=year,
            event_type=event_type,
            reason_code=reason_code,
            details=details,
        )

    def record_external_admission(self, project: dict, *, year: int) -> None:
        self.ledger.record_external_admission(project, year=year)

    def record_removed(
        self,
        before: list[dict],
        after: list[dict],
        *,
        year: int,
        event_type: PlanningEventType,
        reason_code: PlanningReasonCode,
        outcome: str,
    ) -> None:
        self.ledger.record_removed(
            before, after, year=year, event_type=event_type,
            reason_code=reason_code, outcome=outcome,
        )

    def record_deferred(self, before: list[dict], after: list[dict], *, year: int) -> None:
        self.ledger.record_deferred(before, after, year=year)

    def record_success_evaluations(self, projects: list[dict], *, year: int) -> None:
        self.ledger.record_success_evaluations(projects, year=year)

    def record_allocations(self, projects: list[dict], *, year: int) -> None:
        self.ledger.record_allocations(projects, year=year)

    def record_model_admissions(self, projects: list[dict], *, year: int) -> None:
        self.ledger.record_model_admissions(projects, year=year)

    def remove(
        self,
        pipeline: list[dict],
        project: dict,
        *,
        year: int,
        event_type: PlanningEventType,
        reason_code: PlanningReasonCode,
        outcome: str,
        assigned_asset_id: str | None = None,
    ) -> None:
        self.ledger.remove_project(
            pipeline, project, year=year, event_type=event_type,
            reason_code=reason_code, outcome=outcome,
            assigned_asset_id=assigned_asset_id,
        )

    def append(
        self, implementation: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        pipeline = args[0] if args and isinstance(args[0], list) else None
        before_ids = (
            {ensure_project_id(project) for project in pipeline} if pipeline is not None else set()
        )
        result = implementation(*args, **kwargs)
        if pipeline is not None:
            added = [project for project in pipeline if ensure_project_id(project) not in before_ids]
            self.ledger.record_model_admissions(added, year=self._year())
        self.evidence.record(
            self.id,
            self.version,
            "pipeline.investment_added",
            technology=kwargs.get("technology_type"),
            capacity_mw=float(kwargs.get("capacity", 0.0)),
        )
        return result

    def complete_year(self, projects: list[dict] | int) -> None:
        project_count = len(projects) if isinstance(projects, list) else int(projects)
        if isinstance(projects, list):
            summary = self.ledger.complete_year(self._year(), projects)
        else:
            summary = {"reconciled": False}
        self.evidence.record(
            self.id,
            self.version,
            "pipeline.complete_year",
            projects=project_count,
            reconciled=summary.get("reconciled"),
        )

    def close(self) -> None:
        self.ledger.close()


@dataclass(frozen=True)
class SchemeCModuleRuntime:
    psm: SchemeCPSMModule
    investment: SchemeCAgentInvestmentModule
    pipeline: SchemeCPlanningPipelineModule
    vre_cap: SchemeCVREExpansionCapModule
    storage_cap: SchemeCStorageExpansionCapModule
    storage_cost: object

    def close(self) -> None:
        self.psm.close()
        self.pipeline.close()

    @property
    def selected(self) -> dict[str, dict[str, str]]:
        return {
            kind: {"id": getattr(self, kind).id, "version": getattr(self, kind).version}
            for kind in MODULE_KINDS
        }


class ManifestStorageCostRuntimeAdapter:
    """Attach manifest identity/evidence to an installed v2 cost implementation."""

    def __init__(self, module_id, version, implementation, evidence, parameters):
        self.id = module_id
        self.version = version
        self.implementation = implementation
        if hasattr(implementation, "parameters"):
            implementation.parameters = dict(parameters or {})
        evidence.record(
            module_id, version, "storage_cost.selected",
            scientific_version=getattr(implementation, "scientific_version", None),
        )

    def create(self, **kwargs):
        return self.implementation.create(**kwargs)


REFERENCE_BRIDGE_CAPABILITY = "scheme-c.reference-bridge/v1"
REFERENCE_BRIDGES = {
    ("psm", "scheme-c-psm", "5.0.0"): ReferenceSchemeCPSMBridge,
    ("investment", "agent-investment", "2.0.0"): SchemeCAgentInvestmentModule,
    ("pipeline", "planning-pipeline", "2.0.0"): SchemeCPlanningPipelineModule,
    ("vre_cap", "vre-expansion-cap", "2.0.0"): SchemeCVREExpansionCapModule,
    (
        "storage_cap",
        "storage-expansion-scheme-c",
        "4.0.0",
    ): SchemeCStorageExpansionCapModule,
}


def _reference_bridge(
    slot: str,
    graph: ResolvedModuleGraph,
    evidence: StageEvidence,
    scientific_parameters: Mapping[str, object] | None,
) -> object:
    manifest = graph.manifest(slot)
    if slot == "storage_cost":
        return ManifestStorageCostRuntimeAdapter(
            manifest.id,
            manifest.version,
            graph.implementation(slot),
            evidence,
            scientific_parameters,
        )
    key = (slot, manifest.id, manifest.version)
    factory = REFERENCE_BRIDGES.get(key)
    if REFERENCE_BRIDGE_CAPABILITY not in manifest.provides_capabilities or factory is None:
        raise ContractError(
            f"Module {manifest.id} ({slot}) is valid for the native v2 runtime but "
            "has no Scheme C reference-session bridge. Run it through the native orchestrator."
        )
    instance = factory(evidence=evidence)
    represented_id = getattr(instance, "project_module_id", instance.id)
    if represented_id != manifest.id or instance.version != manifest.version:
        raise ContractError(
            f"Reference bridge identity differs from resolved manifest for {manifest.id}"
        )
    return instance


def build_scheme_c_runtime(
    module_ids: Mapping[str, str],
    evidence_path: Path,
    scientific_parameters: Mapping[str, object] | None = None,
    resolution_graph: ResolvedModuleGraph | None = None,
) -> SchemeCModuleRuntime:
    # Compatibility migration for pre-storage-policy callers. Saved v2
    # research projects always persist this slot explicitly.
    module_ids = dict(module_ids)
    module_ids.setdefault("storage_cost", "dynamic-annual-storage-cost")
    evidence = StageEvidence(evidence_path)
    missing = [kind for kind in MODULE_KINDS if not module_ids.get(kind)]
    if missing:
        raise ValueError(f"Research project is missing module selections: {', '.join(missing)}")
    graph = resolution_graph or workspace_registry().resolve_selection(module_ids)
    for slot, module_id in module_ids.items():
        if graph.manifest(slot).id != module_id:
            raise ContractError(
                f"Resolved module graph differs from the requested {slot}: {module_id}"
            )
    storage_cost = _reference_bridge(
        "storage_cost", graph, evidence, scientific_parameters
    )
    runtime = SchemeCModuleRuntime(
        psm=_reference_bridge("psm", graph, evidence, scientific_parameters),
        investment=_reference_bridge("investment", graph, evidence, scientific_parameters),
        pipeline=_reference_bridge("pipeline", graph, evidence, scientific_parameters),
        vre_cap=_reference_bridge("vre_cap", graph, evidence, scientific_parameters),
        storage_cap=_reference_bridge("storage_cap", graph, evidence, scientific_parameters),
        storage_cost=storage_cost,
    )
    runtime.psm.storage_cost_module_id = module_ids["storage_cost"]
    runtime.storage_cap.storage_cost_module_id = module_ids["storage_cost"]
    if scientific_parameters is not None:
        runtime.vre_cap.fraction = float(
            scientific_parameters.get("expansion.vre_cap_fraction", 0.20)
        )
    return runtime


def build_retained_reference_runtime(
    module_ids: Mapping[str, str],
    evidence_path: Path,
    scientific_parameters: Mapping[str, object] | None = None,
) -> SchemeCModuleRuntime:
    """Build the fixed historical bridge for the explicit comparison command.

    This deliberately does not resolve the live FORCE PSM/CEM manifests.  The
    bridge represents the retained 2026-07-18 equations and versions, while the
    only selectable policy is the storage tariff used by that retained run.
    """

    expected = {
        "psm": "scheme-c-psm",
        "investment": "agent-investment",
        "pipeline": "planning-pipeline",
        "vre_cap": "vre-expansion-cap",
        "storage_cap": "storage-expansion-scheme-c",
    }
    incompatible = [
        f"{slot}={module_ids.get(slot)!r}"
        for slot, module_id in expected.items()
        if module_ids.get(slot) != module_id
    ]
    if incompatible:
        raise ContractError(
            "The retained comparison supports only its fixed historical stage set: "
            + ", ".join(incompatible)
        )
    evidence = StageEvidence(evidence_path)
    storage_id = str(module_ids.get("storage_cost") or "dynamic-annual-storage-cost")
    registry = workspace_registry()
    storage_manifest = registry.manifest(storage_id, expected_slot="storage_cost")
    storage_cost = ManifestStorageCostRuntimeAdapter(
        storage_manifest.id,
        storage_manifest.version,
        registry.resolve(storage_id, expected_slot="storage_cost"),
        evidence,
        scientific_parameters,
    )
    runtime = SchemeCModuleRuntime(
        psm=ReferenceSchemeCPSMBridge(evidence=evidence),
        investment=SchemeCAgentInvestmentModule(evidence=evidence),
        pipeline=SchemeCPlanningPipelineModule(evidence=evidence),
        vre_cap=SchemeCVREExpansionCapModule(evidence=evidence),
        storage_cap=SchemeCStorageExpansionCapModule(evidence=evidence),
        storage_cost=storage_cost,
    )
    runtime.psm.storage_cost_module_id = storage_id
    runtime.storage_cap.storage_cost_module_id = storage_id
    if scientific_parameters is not None:
        runtime.vre_cap.fraction = float(
            scientific_parameters.get("expansion.vre_cap_fraction", 0.20)
        )
    return runtime
