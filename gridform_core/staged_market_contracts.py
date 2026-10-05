"""Immutable public contracts for staged national clearing and balancing."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence

from .module_context import RunContextRef, YearContextRef
from .v2.contracts import ArtifactReference, JsonContract


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REALISED_AHEAD_KEYS = {
    "actual_demand_mwh",
    "actual_dispatch_mwh",
    "final_dispatch_mwh_by_asset",
    "real_demand_mwh",
    "realised_availability_mw_by_asset",
    "realised_demand_mwh",
    "realized_availability_mw_by_asset",
    "realized_demand_mwh",
}


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _freeze_fields(instance: object, *names: str) -> None:
    for name in names:
        object.__setattr__(instance, name, _freeze_json(getattr(instance, name)))


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _finite(name: str, value: float, *, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and float(value) < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _positive(name: str, value: float) -> None:
    _finite(name, value)
    if float(value) <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _require_sha256(name: str, value: str) -> None:
    if not _SHA256.fullmatch(str(value)):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _reject_realised_ahead_information(value: object, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in _REALISED_AHEAD_KEYS:
                raise ValueError(
                    f"{path}.{key_text} contains realised information at the ahead stage"
                )
            _reject_realised_ahead_information(item, f"{path}.{key_text}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _reject_realised_ahead_information(item, f"{path}[{index}]")


def _validate_numeric_mapping(
    name: str,
    values: Mapping[str, float],
    *,
    minimum: float | None = None,
) -> None:
    for key, value in values.items():
        _require_text(f"{name} key", str(key))
        _finite(f"{name}.{key}", value, minimum=minimum)


def contract_sha256(value: JsonContract | Mapping[str, object]) -> str:
    """Return the canonical scientific identity of a staged-market contract."""

    payload = value.to_dict() if isinstance(value, JsonContract) else dict(value)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class AheadMarketInput(JsonContract):
    run_id: str
    year: int
    period: int
    period_id: str
    period_hours: float
    information_scope: str
    forecast_demand_mwh: float
    offers: Sequence[Mapping[str, object]]
    storage_state_mwh: Mapping[str, float]
    schema_version: str = "value.ahead-market-input/v1"
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _freeze_fields(self, "offers", "storage_state_mwh", "extensions")
        _require_text("run_id", self.run_id)
        _require_text("period_id", self.period_id)
        if self.information_scope != "forecast_only":
            raise ValueError("AheadMarketInput information_scope must be forecast_only")
        if self.period < 0:
            raise ValueError("period must be non-negative")
        _positive("period_hours", self.period_hours)
        _finite("forecast_demand_mwh", self.forecast_demand_mwh, minimum=0.0)
        _validate_numeric_mapping("storage_state_mwh", self.storage_state_mwh, minimum=0.0)
        _reject_realised_ahead_information(self.offers, "offers")
        _reject_realised_ahead_information(self.extensions, "extensions")
        if self.schema_version != "value.ahead-market-input/v1":
            raise ValueError("AheadMarketInput schema_version is unsupported")


@dataclass(frozen=True)
class AheadMarketResult(JsonContract):
    run_id: str
    year: int
    period: int
    period_id: str
    information_scope: str
    schedule_mwh_by_asset: Mapping[str, float]
    clearing_price_gbp_per_mwh: float
    accepted_volume_mwh: float
    settlement_mwh_by_asset: Mapping[str, float]
    storage_scheduled_action_mwh_by_asset: Mapping[str, float]
    source_input_sha256: str
    schema_version: str = "value.ahead-market-result/v1"
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _freeze_fields(
            self,
            "schedule_mwh_by_asset",
            "settlement_mwh_by_asset",
            "storage_scheduled_action_mwh_by_asset",
            "extensions",
        )
        _require_text("run_id", self.run_id)
        _require_text("period_id", self.period_id)
        if self.information_scope != "forecast_only":
            raise ValueError("AheadMarketResult information_scope must be forecast_only")
        _validate_numeric_mapping("schedule_mwh_by_asset", self.schedule_mwh_by_asset)
        _finite("clearing_price_gbp_per_mwh", self.clearing_price_gbp_per_mwh)
        _finite("accepted_volume_mwh", self.accepted_volume_mwh, minimum=0.0)
        _validate_numeric_mapping("settlement_mwh_by_asset", self.settlement_mwh_by_asset)
        _validate_numeric_mapping(
            "storage_scheduled_action_mwh_by_asset",
            self.storage_scheduled_action_mwh_by_asset,
        )
        _require_sha256("source_input_sha256", self.source_input_sha256)
        _reject_realised_ahead_information(self.extensions, "extensions")
        if self.schema_version != "value.ahead-market-result/v1":
            raise ValueError("AheadMarketResult schema_version is unsupported")


def _reject_annual_series(value: object, path: str = "period_slice") -> None:
    if isinstance(value, (tuple, list)):
        raise ValueError(f"{path} must not contain an annual array")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_annual_series(item, f"{path}.{key}")


@dataclass(frozen=True)
class ZonalRedispatchPeriodSlice(JsonContract):
    """The complete zonal redispatch input for one declared market period."""

    period_id: str
    ahead_result: AheadMarketResult
    zonal_real_demand_mwh: Mapping[str, float]
    zonal_forecast_demand_mwh: Mapping[str, float]
    forward_boundary_capacity_mwh: Mapping[str, float]
    reverse_boundary_capacity_mwh: Mapping[str, float]
    interconnector_envelopes: Mapping[str, Mapping[str, float]]
    schema_version: str = "value.zonal-redispatch-period-slice/v2"
    # P0-8 S8/S9: the period's unit-cost table (GBP/MWh by asset).  When it is
    # declared, every case of the network counterfactual prices dispatch with
    # it; when it is absent (older callers) the field is not serialised, so
    # their contract hashes are unchanged.
    resource_cost_gbp_per_mwh_by_asset: Mapping[str, float] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        if payload.get("resource_cost_gbp_per_mwh_by_asset") is None:
            payload.pop("resource_cost_gbp_per_mwh_by_asset", None)
        return payload

    def __post_init__(self) -> None:
        if not isinstance(self.ahead_result, AheadMarketResult):
            raise ValueError("ZonalRedispatchPeriodSlice requires an AheadMarketResult")
        if self.resource_cost_gbp_per_mwh_by_asset is not None:
            _freeze_fields(self, "resource_cost_gbp_per_mwh_by_asset")
            _reject_annual_series(
                self.resource_cost_gbp_per_mwh_by_asset, "resource_cost_gbp_per_mwh_by_asset"
            )
            _validate_numeric_mapping(
                "resource_cost_gbp_per_mwh_by_asset", self.resource_cost_gbp_per_mwh_by_asset
            )
        _freeze_fields(
            self,
            "zonal_real_demand_mwh",
            "zonal_forecast_demand_mwh",
            "forward_boundary_capacity_mwh",
            "reverse_boundary_capacity_mwh",
            "interconnector_envelopes",
        )
        _require_text("period_id", self.period_id)
        if self.ahead_result.period_id != self.period_id:
            raise ValueError("period slice ahead_result must match period_id")
        for name in (
            "zonal_real_demand_mwh",
            "zonal_forecast_demand_mwh",
            "forward_boundary_capacity_mwh",
            "reverse_boundary_capacity_mwh",
        ):
            values = getattr(self, name)
            _reject_annual_series(values, name)
            _validate_numeric_mapping(name, values, minimum=0.0)
        _reject_annual_series(self.interconnector_envelopes, "interconnector_envelopes")
        for interconnector_id, envelope in self.interconnector_envelopes.items():
            _require_text("interconnector_envelopes key", interconnector_id)
            _validate_numeric_mapping(
                f"interconnector_envelopes.{interconnector_id}", envelope, minimum=0.0
            )
        if self.schema_version != "value.zonal-redispatch-period-slice/v2":
            raise ValueError("ZonalRedispatchPeriodSlice schema_version is unsupported")


@dataclass(frozen=True)
class ZonalRedispatchDomainV2(JsonContract):
    run_context_ref: RunContextRef
    year_context_ref: YearContextRef
    period_slice: ZonalRedispatchPeriodSlice
    schema_version: str = "value.zonal-redispatch-domain/v2"

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        payload["period_slice"] = self.period_slice.to_dict()
        return payload

    def __post_init__(self) -> None:
        if not isinstance(self.run_context_ref, RunContextRef):
            raise ValueError("ZonalRedispatchDomainV2 requires a RunContextRef")
        if not isinstance(self.year_context_ref, YearContextRef):
            raise ValueError("ZonalRedispatchDomainV2 requires a YearContextRef")
        if not isinstance(self.period_slice, ZonalRedispatchPeriodSlice):
            raise ValueError("ZonalRedispatchDomainV2 requires a ZonalRedispatchPeriodSlice")
        if self.schema_version != "value.zonal-redispatch-domain/v2":
            raise ValueError("ZonalRedispatchDomainV2 schema_version is unsupported")


@dataclass(frozen=True)
class FlexibilityBid(JsonContract):
    bid_id: str
    agent_id: str
    asset_id: str
    technology: str
    zone_id: str
    period_id: str
    direction: str
    available_mw: float
    price_gbp_per_mwh: float
    baseline_mw: float
    physical_cost_gbp_per_mwh: float
    network_effect_id: str
    provenance: Mapping[str, object]
    schema_version: str = "value.flexibility-bid/v1"
    units: Mapping[str, str] = field(
        default_factory=lambda: {
            "available_mw": "MW",
            "price_gbp_per_mwh": "GBP/MWh",
            "baseline_mw": "MW",
            "physical_cost_gbp_per_mwh": "GBP/MWh",
        }
    )
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _freeze_fields(self, "provenance", "units", "extensions")
        for name in (
            "bid_id",
            "agent_id",
            "asset_id",
            "technology",
            "zone_id",
            "period_id",
            "network_effect_id",
        ):
            _require_text(name, str(getattr(self, name)))
        if self.direction not in {"up", "down"}:
            raise ValueError("direction must be up or down")
        _positive("available_mw", self.available_mw)
        _finite("price_gbp_per_mwh", self.price_gbp_per_mwh)
        _finite("baseline_mw", self.baseline_mw)
        _finite("physical_cost_gbp_per_mwh", self.physical_cost_gbp_per_mwh)
        if self.schema_version != "value.flexibility-bid/v1":
            raise ValueError("FlexibilityBid schema_version is unsupported")


@dataclass(frozen=True)
class BalancingInput(JsonContract):
    run_id: str
    year: int
    period: int
    period_id: str
    ahead_result_sha256: str
    real_demand_mwh: float
    realised_availability_mw_by_asset: Mapping[str, float]
    initial_soc_mwh_by_asset: Mapping[str, float]
    bids: Sequence[FlexibilityBid]
    period_hours: float
    voll_gbp_per_mwh: float
    domain_payload: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.balancing-input/v1"
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _freeze_fields(
            self,
            "realised_availability_mw_by_asset",
            "initial_soc_mwh_by_asset",
            "bids",
            "domain_payload",
            "extensions",
        )
        _require_text("run_id", self.run_id)
        _require_text("period_id", self.period_id)
        _require_sha256("ahead_result_sha256", self.ahead_result_sha256)
        if self.period < 0:
            raise ValueError("period must be non-negative")
        _finite("real_demand_mwh", self.real_demand_mwh, minimum=0.0)
        _validate_numeric_mapping(
            "realised_availability_mw_by_asset",
            self.realised_availability_mw_by_asset,
            minimum=0.0,
        )
        _validate_numeric_mapping(
            "initial_soc_mwh_by_asset", self.initial_soc_mwh_by_asset, minimum=0.0
        )
        _positive("period_hours", self.period_hours)
        _positive("voll_gbp_per_mwh", self.voll_gbp_per_mwh)
        bid_ids = [bid.bid_id for bid in self.bids]
        if len(set(bid_ids)) != len(bid_ids):
            raise ValueError("Duplicate bid_id in BalancingInput")
        if any(bid.period_id != self.period_id for bid in self.bids):
            raise ValueError("Every bid period_id must match BalancingInput period_id")
        if self.schema_version != "value.balancing-input/v1":
            raise ValueError("BalancingInput schema_version is unsupported")


@dataclass(frozen=True)
class AcceptedAdjustment(JsonContract):
    bid_id: str
    agent_id: str
    asset_id: str
    zone_id: str
    accepted_delta_mwh: float
    bid_price_gbp_per_mwh: float
    cashflow_to_agent_gbp: float
    reason_code: str
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _freeze_fields(self, "extensions")
        for name in ("bid_id", "agent_id", "asset_id", "zone_id", "reason_code"):
            _require_text(name, str(getattr(self, name)))
        _finite("accepted_delta_mwh", self.accepted_delta_mwh)
        _finite("bid_price_gbp_per_mwh", self.bid_price_gbp_per_mwh)
        _finite("cashflow_to_agent_gbp", self.cashflow_to_agent_gbp)
        expected = self.accepted_delta_mwh * self.bid_price_gbp_per_mwh
        if not math.isclose(
            self.cashflow_to_agent_gbp, expected, rel_tol=1e-12, abs_tol=1e-9
        ):
            raise ValueError(
                "cashflow_to_agent_gbp must equal accepted_delta_mwh times bid price"
            )
@dataclass(frozen=True)
class BalancingResult(JsonContract):
    run_id: str
    year: int
    period: int
    period_id: str
    ahead_result_sha256: str
    source_input_sha256: str
    accepted_adjustments: Sequence[AcceptedAdjustment]
    final_dispatch_mwh_by_asset: Mapping[str, float]
    final_soc_mwh_by_asset: Mapping[str, float]
    curtailment_mwh_by_class: Mapping[str, float]
    blackout_mwh: float
    settlement_cashflow_gbp_by_agent: Mapping[str, float]
    resource_cost_gbp_by_class: Mapping[str, float]
    energy_balance_residual_mwh: float
    schema_version: str = "value.balancing-result/v1"
    artifacts: Sequence[ArtifactReference] = field(default_factory=tuple)
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _freeze_fields(
            self,
            "accepted_adjustments",
            "final_dispatch_mwh_by_asset",
            "final_soc_mwh_by_asset",
            "curtailment_mwh_by_class",
            "settlement_cashflow_gbp_by_agent",
            "resource_cost_gbp_by_class",
            "artifacts",
            "extensions",
        )
        _require_text("run_id", self.run_id)
        _require_text("period_id", self.period_id)
        _require_sha256("ahead_result_sha256", self.ahead_result_sha256)
        _require_sha256("source_input_sha256", self.source_input_sha256)
        adjustment_ids = [row.bid_id for row in self.accepted_adjustments]
        if len(set(adjustment_ids)) != len(adjustment_ids):
            raise ValueError("Duplicate accepted bid_id in BalancingResult")
        _validate_numeric_mapping(
            "final_dispatch_mwh_by_asset", self.final_dispatch_mwh_by_asset
        )
        _validate_numeric_mapping(
            "final_soc_mwh_by_asset", self.final_soc_mwh_by_asset, minimum=0.0
        )
        _validate_numeric_mapping(
            "curtailment_mwh_by_class", self.curtailment_mwh_by_class, minimum=0.0
        )
        _finite("blackout_mwh", self.blackout_mwh, minimum=0.0)
        _validate_numeric_mapping(
            "settlement_cashflow_gbp_by_agent", self.settlement_cashflow_gbp_by_agent
        )
        expected_cashflows: dict[str, float] = {}
        for adjustment in self.accepted_adjustments:
            expected_cashflows[adjustment.agent_id] = (
                expected_cashflows.get(adjustment.agent_id, 0.0)
                + adjustment.cashflow_to_agent_gbp
            )
        for agent_id in set(expected_cashflows) | set(
            self.settlement_cashflow_gbp_by_agent
        ):
            if not math.isclose(
                expected_cashflows.get(agent_id, 0.0),
                self.settlement_cashflow_gbp_by_agent.get(agent_id, 0.0),
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    "settlement_cashflow_gbp_by_agent must reconcile accepted adjustments"
                )
        _validate_numeric_mapping(
            "resource_cost_gbp_by_class", self.resource_cost_gbp_by_class
        )
        _finite("energy_balance_residual_mwh", self.energy_balance_residual_mwh)
        if self.schema_version != "value.balancing-result/v1":
            raise ValueError("BalancingResult schema_version is unsupported")


@dataclass(frozen=True)
class StagedMarketYearResult(JsonContract):
    result_id: str
    run_id: str
    year: int
    psm_module_id: str
    psm_module_version: str
    balancing_module_id: str
    balancing_module_version: str
    ahead_result_sha256_by_period: Mapping[str, str]
    balancing_result_sha256_by_period: Mapping[str, str]
    schema_version: str = "value.staged-market-year-result/v1"
    artifacts: Sequence[ArtifactReference] = field(default_factory=tuple)
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _freeze_fields(
            self,
            "ahead_result_sha256_by_period",
            "balancing_result_sha256_by_period",
            "artifacts",
            "extensions",
        )
        for name in (
            "result_id",
            "run_id",
            "psm_module_id",
            "psm_module_version",
            "balancing_module_id",
            "balancing_module_version",
        ):
            _require_text(name, str(getattr(self, name)))
        if set(self.ahead_result_sha256_by_period) != set(
            self.balancing_result_sha256_by_period
        ):
            raise ValueError("Ahead and balancing hashes must cover the same periods")
        for period_id, digest in self.ahead_result_sha256_by_period.items():
            _require_text("period_id", period_id)
            _require_sha256(f"ahead_result_sha256_by_period.{period_id}", digest)
        for period_id, digest in self.balancing_result_sha256_by_period.items():
            _require_sha256(f"balancing_result_sha256_by_period.{period_id}", digest)
        if self.schema_version != "value.staged-market-year-result/v1":
            raise ValueError("StagedMarketYearResult schema_version is unsupported")
