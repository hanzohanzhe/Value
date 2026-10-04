"""Serializable, implementation-neutral VALUE v2 contracts."""

from __future__ import annotations

import types
from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Mapping, Sequence, TypeVar, Union, get_args, get_origin, get_type_hints


T = TypeVar("T", bound="JsonContract")


def _json_value(value: object) -> object:
    if is_dataclass(value):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, MappingABC):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _decode(expected: object, value: object) -> object:
    if value is None:
        return None
    if expected is object:
        return value
    if isinstance(expected, type) and issubclass(expected, Enum):
        return expected(value)
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in (Union, types.UnionType):
        for option in args:
            if option is type(None):
                continue
            try:
                return _decode(option, value)
            except (TypeError, ValueError):
                continue
        return value
    if origin in (tuple, Sequence, SequenceABC, list):
        item_type = args[0] if args else object
        return tuple(_decode(item_type, item) for item in value)  # type: ignore[arg-type]
    if origin in (dict, Mapping, MappingABC):
        key_type, item_type = args if len(args) == 2 else (str, object)
        return {
            _decode(key_type, key): _decode(item_type, item)
            for key, item in value.items()  # type: ignore[union-attr]
        }
    if isinstance(expected, type) and is_dataclass(expected):
        if not isinstance(value, MappingABC):
            raise TypeError(f"Expected an object for {expected.__name__}")
        hints = get_type_hints(expected)
        return expected(
            **{
                item.name: _decode(hints.get(item.name, object), value[item.name])
                for item in fields(expected)
                if item.name in value
            }
        )
    return value


class JsonContract:
    """Small standard-library JSON boundary used by every v2 dataclass."""

    def to_dict(self) -> dict[str, object]:
        return _json_value(self)  # type: ignore[return-value]

    @classmethod
    def from_dict(cls: type[T], payload: Mapping[str, object]) -> T:
        decoded = _decode(cls, payload)
        if not isinstance(decoded, cls):
            raise TypeError(f"Could not decode {cls.__name__}")
        return decoded


class PlanningEventType(str, Enum):
    SOURCE_IMPORTED = "source_imported"
    ADMITTED_EXTERNAL = "admitted_external"
    ADMITTED_MODEL_INVESTMENT = "admitted_model_investment"
    EXCLUDED_EXISTING_STOCK = "excluded_existing_stock"
    FILTERED_STATUS_ZOMBIE = "filtered_status_zombie"
    FILTERED_SCHEDULE_ZOMBIE = "filtered_schedule_zombie"
    FILTERED_BELOW_MINIMUM_SIZE = "filtered_below_minimum_size"
    FILTERED_OUTSIDE_HORIZON = "filtered_outside_horizon"
    FILTERED_ELIGIBILITY = "filtered_eligibility"
    SUCCESS_EVALUATED = "success_evaluated"
    FAILED_PLANNING = "failed_planning"
    DEFERRED = "deferred"
    ALLOCATION_ASSIGNED = "allocation_assigned"
    STAGE_ADVANCED = "stage_advanced"
    COMMISSIONED = "commissioned"
    DEPLETED_OR_RETIRED = "depleted_or_retired"
    OUTSIDE_SCOPE = "outside_scope"


class PlanningReasonCode(str, Enum):
    SOURCE_REPD = "source_repd"
    SOURCE_MODEL_INVESTMENT = "source_model_investment"
    EXISTING_OPERATIONAL_STOCK = "existing_operational_stock"
    STATUS_STAGNANT = "status_stagnant"
    SCHEDULE_OVERDUE = "schedule_overdue"
    ZOMBIE_UNCLASSIFIED = "zombie_unclassified"
    BELOW_MINIMUM_SIZE = "below_minimum_size"
    UNSUPPORTED_TECHNOLOGY = "unsupported_technology"
    UNCERTAIN_STATUS_EXCLUDED = "uncertain_status_excluded"
    UNKNOWN_STATUS = "unknown_status"
    UNKNOWN_TIMELINE = "unknown_timeline"
    BEFORE_START_YEAR = "before_start_year"
    AFTER_SIMULATION_HORIZON = "after_simulation_horizon"
    EXPECTED_CAPACITY = "expected_capacity"
    SEEDED_STOCHASTIC = "seeded_stochastic"
    SUCCESS_PROBABILITY = "success_probability"
    ZERO_CAPACITY = "zero_capacity"
    START_YEAR_STOCK_DEFERMENT = "start_year_stock_deferment"
    LOCATION_MATCH = "location_match"
    PROPORTIONAL_ALLOCATION = "proportional_allocation"
    COMMISSIONED_TO_FLEET = "commissioned_to_fleet"
    EXOGENOUS_PUMPED_HYDRO = "exogenous_pumped_hydro"
    MISSING_SITE_OR_HYDROLOGY_DATA = "missing_site_or_hydrology_data"
    NEGATIVE_CAPACITY_DEPLETION = "negative_capacity_depletion"
    UNCERTAIN_REPD_REPACKAGED = "uncertain_repd_repackaged"
    NO_MATCHING_ASSET = "no_matching_asset"


@dataclass(frozen=True)
class ArtifactReference(JsonContract):
    artifact_id: str
    kind: str
    uri: str
    media_type: str
    schema_version: str = "value.artifact/v2"
    checksum_sha256: str | None = None
    size_bytes: int | None = None
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ModuleSelection(JsonContract):
    slot: str
    module_id: str
    module_version: str
    contract_version: str
    schema_version: str = "value.module-selection/v2"


@dataclass(frozen=True)
class ResolvedRun(JsonContract):
    run_id: str
    project_id: str
    scenario_id: str
    data_pack_id: str
    start_year: int
    end_year: int
    modules: Mapping[str, ModuleSelection]
    scientific_parameters: Mapping[str, object]
    runtime_controls: Mapping[str, object]
    schema_version: str = "value.resolved-run/v2"
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetStateV2(JsonContract):
    asset_id: str
    technology: str
    capacity_mw: float
    energy_capacity_mwh: float | None = None
    region: str | None = None
    status: str = "operating"
    schema_version: str = "value.asset-state/v2"
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CommissionedAssetRecord(JsonContract):
    """Versioned physical/economic record created at project commissioning."""

    asset_id: str
    source_project_id: str
    technology: str
    region: str
    commissioning_year: int
    capacity_mw: float
    energy_capacity_mwh: float | None
    capital_cost_per_mw_gbp: float
    capital_cost_per_mwh_gbp: float
    total_capex_gbp: float
    annual_fixed_opex_gbp: float
    economic_lifetime_years: float
    discount_rate: float
    annualized_capital_cost_gbp: float
    schema_version: str = "value.commissioned-asset/v1"
    retirement_year: int | None = None
    charge_efficiency: float | None = None
    discharge_efficiency: float | None = None
    source_catalogue_id: str | None = None
    source_record_id: str | None = None
    investment_owner_id: str | None = None
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanningProject(JsonContract):
    project_id: str
    name: str
    source: str
    technology: str
    capacity_mw: float
    original_capacity_mw: float
    region: str
    development_stage: str
    status: str
    decision_year: int
    expected_completion_year: int
    success_mode: str
    success_probability: float
    schema_version: str = "value.planning-project/v2"
    latitude: float | None = None
    longitude: float | None = None
    random_draw: float | None = None
    outcome: str = "active"
    failure_reason_code: str | None = None
    assigned_asset_id: str | None = None
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanningEvent(JsonContract):
    event_id: str
    project_id: str
    year: int
    event_type: PlanningEventType
    event_sequence: int
    schema_version: str = "value.planning-event/v2"
    reason_code: PlanningReasonCode | None = None
    from_stage: str | None = None
    to_stage: str | None = None
    capacity_mw: float | None = None
    region: str | None = None
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class YearState(JsonContract):
    year: int
    assets: Sequence[AssetStateV2]
    planning_projects: Sequence[PlanningProject]
    schema_version: str = "value.year-state/v2"
    cumulative_metrics: Mapping[str, float] = field(default_factory=dict)
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatingState(JsonContract):
    year: int
    assets: Sequence[AssetStateV2]
    active_planning_projects: Sequence[PlanningProject]
    schema_version: str = "value.operating-state/v2"
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanningAdvanceResult(JsonContract):
    year: int
    operating_state: OperatingState
    active_projects: Sequence[PlanningProject]
    commissioned_projects: Sequence[PlanningProject]
    failed_projects: Sequence[PlanningProject]
    deferred_projects: Sequence[PlanningProject]
    events: Sequence[PlanningEvent]
    schema_version: str = "value.planning-advance-result/v2"
    artifacts: Sequence[ArtifactReference] = field(default_factory=tuple)


@dataclass(frozen=True)
class DispatchResource(JsonContract):
    """Chronological non-storage resource offered to a single-node PSM.

    ``availability`` is a per-unit bound for each period.  Capacity is power
    (MW); the engine converts it to period energy with ``period_hours``.
    """

    asset_id: str
    technology: str
    resource_type: str
    capacity_mw: float
    marginal_cost_gbp_per_mwh: float
    availability: Sequence[float]
    marginal_cost_profile_gbp_per_mwh: Sequence[float] = field(default_factory=tuple)
    schema_version: str = "value.dispatch-resource/v1"
    region: str | None = None
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StorageDispatchResource(JsonContract):
    """Physical storage limits in MW and MWh for chronological dispatch."""

    asset_id: str
    technology: str
    charge_power_mw: float
    discharge_power_mw: float
    energy_capacity_mwh: float
    charge_efficiency: float
    discharge_efficiency: float
    initial_soc_mwh: float
    variable_degradation_gbp_per_mwh_discharged: float = 0.0
    schema_version: str = "value.storage-dispatch-resource/v1"
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ChronologicalPSMData(JsonContract):
    """Implementation-neutral single-node chronological PSM data."""

    period_ids: Sequence[str]
    demand_mwh: Sequence[float]
    resources: Sequence[DispatchResource]
    storage: Sequence[StorageDispatchResource]
    voll_gbp_per_mwh: float
    terminal_soc_rule: str = "cyclic"
    terminal_soc_mwh_by_asset: Mapping[str, float] = field(default_factory=dict)
    allow_blackout: bool = True
    schema_version: str = "value.chronological-psm-data/v1"
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PSMInput(JsonContract):
    run_id: str
    year: int
    data_pack_id: str
    operating_state: OperatingState
    period_hours: float
    parameters: Mapping[str, object]
    schema_version: str = "value.psm-input/v2"
    units: Mapping[str, str] = field(
        default_factory=lambda: {"capacity": "MW", "energy": "MWh", "price": "GBP/MWh"}
    )
    chronology: ChronologicalPSMData | None = None
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PeriodSummary(JsonContract):
    period_id: str
    year: int
    period: int
    market_stage: str
    forecast_demand_mwh: float
    real_demand_mwh: float
    accepted_supply_mwh: float
    storage_charge_mwh: float
    storage_discharge_mwh: float
    vre_available_mwh: float
    vre_accepted_mwh: float
    curtailed_mwh: float
    import_mwh: float
    clearing_price_gbp_per_mwh: float
    physical_resource_cost_gbp: float
    market_payment_gbp: float
    blackout_mwh: float
    energy_balance_residual_mwh: float
    schema_version: str = "value.period-summary/v2"
    units: Mapping[str, str] = field(
        default_factory=lambda: {"energy": "MWh/period", "price": "GBP/MWh", "cost": "GBP"}
    )


@dataclass(frozen=True)
class MarketYearResult(JsonContract):
    result_id: str
    year: int
    module_id: str
    module_version: str
    generation_mwh_by_asset: Mapping[str, float]
    market_income_gbp_by_agent: Mapping[str, float]
    total_system_cost_gbp: float
    total_operational_cost_gbp: float
    total_levelized_capital_cost_gbp: float
    total_demand_mwh: float
    total_generation_mwh: float
    total_blackout_mwh: float
    total_excess_mwh: float
    schema_version: str = "value.market-year-result/v2"
    period_summaries: Sequence[PeriodSummary] = field(default_factory=tuple)
    artifacts: Sequence[ArtifactReference] = field(default_factory=tuple)
    units: Mapping[str, str] = field(
        default_factory=lambda: {"energy": "MWh", "capacity": "MW", "cost": "GBP"}
    )
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpansionHeadroom(JsonContract):
    headroom_id: str
    year: int
    module_id: str
    allowed_additions_mw: Mapping[str, float]
    schema_version: str = "value.expansion-headroom/v2"
    method: str = "declared_expansion_policy"
    evidence: Mapping[str, float] = field(default_factory=dict)
    units: Mapping[str, str] = field(default_factory=lambda: {"capacity": "MW"})
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class InvestmentProposal(JsonContract):
    proposal_id: str
    year: int
    agent_id: str
    technology: str
    capacity_mw: float
    region: str
    expected_completion_year: int
    schema_version: str = "value.investment-proposal/v2"
    evidence: Mapping[str, float] = field(default_factory=dict)
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class InvestmentDecision(JsonContract):
    decision_id: str
    year: int
    module_id: str
    proposals: Sequence[InvestmentProposal]
    retirements_mw: Mapping[str, float]
    schema_version: str = "value.investment-decision/v2"
    artifacts: Sequence[ArtifactReference] = field(default_factory=tuple)
    extensions: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanningAdmissionResult(JsonContract):
    year: int
    admitted_projects: Sequence[PlanningProject]
    rejected_proposals: Sequence[InvestmentProposal]
    next_pipeline: Sequence[PlanningProject]
    events: Sequence[PlanningEvent]
    schema_version: str = "value.planning-admission-result/v2"
    artifacts: Sequence[ArtifactReference] = field(default_factory=tuple)


@dataclass(frozen=True)
class YearResult(JsonContract):
    result_id: str
    year: int
    planning_advance: PlanningAdvanceResult
    market: MarketYearResult
    expansion_headroom: Sequence[ExpansionHeadroom]
    investment: InvestmentDecision
    planning_admission: PlanningAdmissionResult
    next_state: YearState
    schema_version: str = "value.year-result/v2"
    artifacts: Sequence[ArtifactReference] = field(default_factory=tuple)
    extensions: Mapping[str, object] = field(default_factory=dict)
