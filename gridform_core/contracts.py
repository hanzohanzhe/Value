"""Versioned, implementation-neutral contracts between data, PSM and CEM.

The contracts deliberately contain no file paths from the original research
folder. Engines receive resolved datasets and typed state from the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "value.contracts/v1"


@dataclass(frozen=True)
class DatasetBinding:
    role: str
    uri: str
    format: str
    unit: str | None = None
    checksum: str | None = None
    mapping: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DataPack:
    id: str
    name: str
    country: str
    timezone: str
    datasets: Mapping[str, DatasetBinding]
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class AssetState:
    id: str
    technology: str
    capacity_mw: float
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelState:
    year: int
    assets: Sequence[AssetState]
    planning_pipeline: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    cumulative_metrics: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class YearContext:
    project_id: str
    scenario_id: str
    year: int
    data_pack: DataPack
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class PSMInput:
    context: YearContext
    state: ModelState


@dataclass(frozen=True)
class PSMResult:
    year: int
    market_income_gbp: Mapping[str, float]
    generation_mwh: Mapping[str, float]
    prices_gbp_per_mwh: Sequence[float]
    demand_mwh: Sequence[float]
    vre_generation_mwh: Sequence[float]
    storage_discharge_mwh: Sequence[float]
    metrics: Mapping[str, float] = field(default_factory=dict)
    artifacts: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CapacityDecision:
    module_id: str
    additions_mw: Mapping[str, float] = field(default_factory=dict)
    retirements_mw: Mapping[str, float] = field(default_factory=dict)
    pipeline_projects: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    evidence: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class YearResult:
    year: int
    psm: PSMResult
    decisions: Sequence[CapacityDecision]
    next_state: ModelState

