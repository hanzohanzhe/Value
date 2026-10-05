"""Lossless single-period zonal redispatch with SciPy/HiGHS.

This is a transport/cut-set balancing model, not a DC or AC power-flow model.
The national ahead result remains immutable.  The solver accepts signed
pay-as-bid flexibility adjustments, routes their zonal effects through a
computational corridor graph and enforces the installed ETYS cut-set limits.
"""

from __future__ import annotations

import json
import math
import platform
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .failure_evidence import FailureEvidenceRequest, write_first_failure_bundle
from .staged_market_contracts import (
    AcceptedAdjustment,
    AheadMarketResult,
    BalancingInput,
    BalancingResult,
    FlexibilityBid,
    ZonalRedispatchDomainV2,
    contract_sha256,
)
from .module_context import (
    ImmutableContextResolver,
    RunContextRef,
    RunStaticContext,
    YearContext,
    YearContextRef,
    canonical_context_sha256,
)
from .zonal_demand_alignment import (
    SUPPORTED_ZONAL_DEMAND_MODES,
)
from .zonal_contracts import ZonalNetworkPack
from .zonal_solver_contract import (
    DEFAULT_ZONAL_SOLVER_SETTINGS,
    ObjectiveLockDiagnostic,
    ZonalSolverContractError,
    ZonalSolverSettings,
    classify_lock,
    compute_lock_tolerance,
    solver_stack_identity,
    validate_solver_settings,
)


FORMULATION_ID = "value.lossless-zonal-redispatch/v2"
DOMAIN_SCHEMA = "value.zonal-redispatch-domain/v2"
TOLERANCE = 1e-8
# A lock repair reserves at most this fraction of the lock's own computed
# tolerance as its solver guard (see ``_tighten_violated_objective_cap``).
LOCK_REPAIR_GUARD_FRACTION = 0.25


class ZonalRedispatchInputError(ValueError):
    """The declared zonal balancing input is malformed or non-conforming."""


class ZonalRedispatchSolveError(RuntimeError):
    """HiGHS did not produce a valid zonal redispatch result."""

    def __init__(self, message: str, diagnostics: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


@dataclass(frozen=True)
class SinglePeriodProblem:
    model_input: BalancingInput
    ahead: AheadMarketResult
    network_pack: ZonalNetworkPack
    bids: tuple[FlexibilityBid, ...]
    demand_mwh_by_zone: Mapping[str, float]
    asset_zone_id_by_asset: Mapping[str, str]
    resource_class_by_asset: Mapping[str, str]
    resource_cost_gbp_per_mwh_by_asset: Mapping[str, float]
    storage: Mapping[str, Mapping[str, object]]
    variable_names: tuple[str, ...]
    bounds: tuple[tuple[float | None, float | None], ...]
    primary_objective: np.ndarray
    secondary_objective: np.ndarray
    physical_tie_objective: np.ndarray
    stable_tie_objective: np.ndarray
    equality_matrix: np.ndarray
    equality_rhs: np.ndarray
    inequality_matrix: np.ndarray
    inequality_rhs: np.ndarray
    bid_index: Mapping[str, int]
    flow_index: Mapping[str, int]
    shedding_index: Mapping[str, int]
    storage_discharge_index: Mapping[str, int]
    storage_charge_index: Mapping[str, int]
    flow_absolute_index: Mapping[str, int]
    input_sha256: str


@dataclass(frozen=True)
class SinglePeriodSolution:
    values: np.ndarray
    primary_objective_gbp: float
    secondary_objective_mwh: float
    physical_tie_objective: float
    stable_tie_objective: float
    diagnostics: Mapping[str, object]
    network_solver_diagnostics: tuple[ObjectiveLockDiagnostic, ...] = ()


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ZonalRedispatchInputError(f"{label} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ZonalRedispatchInputError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ZonalRedispatchInputError(f"{label} must be finite")
    return result


def _nonnegative(value: object, label: str) -> float:
    result = _finite(value, label)
    if result < 0:
        raise ZonalRedispatchInputError(f"{label} cannot be negative")
    return result


def _available_energy(bid: FlexibilityBid, period_hours: float) -> float:
    raw = bid.extensions.get("available_mwh")
    value = bid.available_mw * period_hours if raw is None else raw
    result = _nonnegative(value, f"available energy for bid {bid.bid_id}")
    if result <= 0:
        raise ZonalRedispatchInputError(f"Bid {bid.bid_id} has no available energy")
    return result


def _domain(
    model_input: BalancingInput,
    *,
    run_context_ref: RunContextRef,
    year_context_ref: YearContextRef,
) -> tuple[ZonalRedispatchDomainV2, AheadMarketResult]:
    payload = dict(model_input.domain_payload)
    try:
        domain = ZonalRedispatchDomainV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise ZonalRedispatchInputError(f"Expected {DOMAIN_SCHEMA}: {exc}") from exc
    if domain.run_context_ref != run_context_ref:
        raise ZonalRedispatchInputError("Run context reference is not bound")
    if domain.year_context_ref != year_context_ref:
        raise ZonalRedispatchInputError("Year context reference is not bound")
    ahead = domain.period_slice.ahead_result
    if contract_sha256(ahead) != model_input.ahead_result_sha256:
        raise ZonalRedispatchInputError("Declared ahead result hash does not match its payload")
    if (ahead.run_id, ahead.year, ahead.period, ahead.period_id) != (
        model_input.run_id,
        model_input.year,
        model_input.period,
        model_input.period_id,
    ):
        raise ZonalRedispatchInputError("Balancing input and ahead result identities do not match")
    if domain.period_slice.period_id != model_input.period_id:
        raise ZonalRedispatchInputError("Balancing input and period slice identities do not match")
    return domain, ahead


def _row(size: int) -> np.ndarray:
    return np.zeros(size, dtype=float)


def _as_matrix(rows: Sequence[np.ndarray], size: int) -> np.ndarray:
    return np.vstack(rows) if rows else np.empty((0, size), dtype=float)


def build_single_period_problem(
    model_input: BalancingInput,
    *,
    network_pack: ZonalNetworkPack | None = None,
    run_context_ref: RunContextRef | None = None,
    year_context_ref: YearContextRef | None = None,
    annual_metadata: Mapping[str, object] | None = None,
    demand_mode: str = "",
    network_period_index: int | None = None,
) -> SinglePeriodProblem:
    """Validate and assemble the production single-period LP matrices."""

    if (
        network_pack is None
        or run_context_ref is None
        or year_context_ref is None
        or annual_metadata is None
    ):
        raise ZonalRedispatchInputError("Zonal redispatch contexts are not bound")
    domain, ahead = _domain(
        model_input,
        run_context_ref=run_context_ref,
        year_context_ref=year_context_ref,
    )
    network = network_pack
    period_slice = domain.period_slice
    zone_ids = tuple(zone.zone_id for zone in network.zones)
    known_zones = set(zone_ids)
    demand = {
        str(zone): _finite(value, f"zonal_real_demand_mwh.{zone}")
        for zone, value in period_slice.zonal_real_demand_mwh.items()
    }
    if set(demand) != known_zones or any(value < 0 for value in demand.values()):
        raise ZonalRedispatchInputError("Real zonal demand must name every declared zone and be non-negative")
    demand_total = math.fsum(demand[zone] for zone in sorted(demand))
    if abs(demand_total - model_input.real_demand_mwh) > TOLERANCE:
        raise ZonalRedispatchInputError("Real zonal demand does not reconcile to the balancing input")
    if demand_mode not in SUPPORTED_ZONAL_DEMAND_MODES:
        raise ZonalRedispatchInputError(
            "Zonal redispatch requires an explicit supported zonal_demand_mode"
        )
    if network_period_index is None:
        try:
            network_period_index = {
                str(period_id): index
                for index, period_id in enumerate(network.zonal_demand.period_ids)
            }[model_input.period_id]
        except KeyError as exc:
            raise ZonalRedispatchInputError(
                "Balancing period is absent from the network-pack clock"
            ) from exc
    pack_demand = {
        zone: float(
            network.zonal_demand.demand_mwh_by_zone[zone][network_period_index]
        )
        for zone in zone_ids
    }
    pack_national = float(
        network.zonal_demand.national_demand_mwh[network_period_index]
    )
    if demand_mode == "network_pack_absolute_demand":
        expected_demand = pack_demand
    else:
        if pack_national == 0.0 and model_input.real_demand_mwh > 0.0:
            raise ZonalRedispatchInputError(
                "Signed network-pack period has zero national demand and no fallback weights"
            )
        scale = (
            1.0
            if pack_national == 0.0
            else model_input.real_demand_mwh / pack_national
        )
        expected_demand: dict[str, float] = {}
        remaining = model_input.real_demand_mwh
        for zone in zone_ids[:-1]:
            expected_demand[zone] = pack_demand[zone] * scale
            remaining -= expected_demand[zone]
        expected_demand[zone_ids[-1]] = remaining
    if max(
        (abs(expected_demand[zone] - demand[zone]) for zone in zone_ids),
        default=0.0,
    ) > TOLERANCE:
        raise ZonalRedispatchInputError(
            "Real zonal demand does not match the declared signed-pack demand mode"
        )
    forecast_demand = {
        str(zone): _finite(value, f"zonal_forecast_demand_mwh.{zone}")
        for zone, value in period_slice.zonal_forecast_demand_mwh.items()
    }
    if set(forecast_demand) != known_zones or any(
        value < 0 for value in forecast_demand.values()
    ):
        raise ZonalRedispatchInputError(
            "Forecast zonal demand must name every declared zone and be non-negative"
        )

    raw_zones = annual_metadata.get("asset_zone_id_by_asset")
    if not isinstance(raw_zones, Mapping):
        raise ZonalRedispatchInputError("Zonal domain requires asset_zone_id_by_asset")
    asset_zones = {str(asset): str(zone) for asset, zone in raw_zones.items()}
    raw_envelopes = period_slice.interconnector_envelopes
    bids = tuple(sorted(model_input.bids, key=lambda bid: bid.bid_id))
    assets = (
        set(ahead.schedule_mwh_by_asset)
        | {bid.asset_id for bid in bids}
        | {str(asset) for asset in model_input.realised_availability_mw_by_asset}
        | {str(asset) for asset in raw_envelopes}
    )
    missing_assets = sorted(assets.difference(asset_zones))
    if missing_assets:
        raise ZonalRedispatchInputError("Assets lack frozen zone assignments: " + ", ".join(missing_assets))
    unknown_zones = sorted({asset_zones[asset] for asset in assets}.difference(known_zones))
    if unknown_zones:
        raise ZonalRedispatchInputError("Assets refer to unknown zones: " + ", ".join(unknown_zones))
    for bid in bids:
        if bid.zone_id != asset_zones[bid.asset_id]:
            raise ZonalRedispatchInputError(f"Bid {bid.bid_id} changed its frozen asset zone")
        expected_baseline = float(ahead.schedule_mwh_by_asset.get(bid.asset_id, 0.0)) / model_input.period_hours
        if abs(bid.baseline_mw - expected_baseline) > TOLERANCE:
            raise ZonalRedispatchInputError(f"Bid {bid.bid_id} baseline does not match the frozen ahead schedule")

    raw_classes = annual_metadata.get("resource_class_by_asset")
    raw_costs = annual_metadata.get("resource_cost_gbp_per_mwh_by_asset")
    classes = {str(key): str(value) for key, value in dict(raw_classes or {}).items()}
    costs = {str(key): _finite(value, f"resource cost {key}") for key, value in dict(raw_costs or {}).items()}
    period_costs: dict[str, list[float]] = {}
    for bid in bids:
        physical_cost = _finite(
            bid.physical_cost_gbp_per_mwh,
            f"physical resource cost for bid {bid.bid_id}",
        )
        period_costs.setdefault(bid.asset_id, []).append(physical_cost)
    costs.update({
        asset_id: values[0]
        for asset_id, values in period_costs.items()
        if all(abs(value - values[0]) <= TOLERANCE for value in values[1:])
    })
    raw_storage = annual_metadata.get("storage")
    if not isinstance(raw_storage, Mapping):
        raise ZonalRedispatchInputError("Zonal domain storage declaration must be an object")
    storage: dict[str, Mapping[str, object]] = {
        str(asset): dict(specification) for asset, specification in raw_storage.items()
        if isinstance(specification, Mapping)
    }
    if len(storage) != len(raw_storage):
        raise ZonalRedispatchInputError("Every storage declaration must be an object")
    for asset, specification in storage.items():
        if specification.get("bid_contract") != "convex_net_power_v1":
            raise ZonalRedispatchInputError(f"Storage {asset} must declare convex_net_power_v1")
        charge_power = _nonnegative(specification.get("charge_power_mw"), f"{asset} charge power")
        discharge_power = _nonnegative(specification.get("discharge_power_mw"), f"{asset} discharge power")
        capacity = _nonnegative(specification.get("energy_capacity_mwh"), f"{asset} energy capacity")
        charge_efficiency = _finite(specification.get("charge_efficiency"), f"{asset} charge efficiency")
        discharge_efficiency = _finite(specification.get("discharge_efficiency"), f"{asset} discharge efficiency")
        if charge_power <= 0 or discharge_power <= 0 or capacity <= 0:
            raise ZonalRedispatchInputError(f"Storage {asset} power and energy capacities must be positive")
        if not 0 < charge_efficiency <= 1 or not 0 < discharge_efficiency <= 1:
            raise ZonalRedispatchInputError(f"Storage {asset} efficiencies must be within (0, 1]")
        if asset not in model_input.initial_soc_mwh_by_asset:
            raise ZonalRedispatchInputError(f"Storage {asset} lacks an opening SOC")
        opening = float(model_input.initial_soc_mwh_by_asset[asset])
        if opening > capacity + TOLERANCE:
            raise ZonalRedispatchInputError(f"Storage {asset} opening SOC exceeds capacity")
        storage_bids = [bid for bid in bids if bid.asset_id == asset]
        if any(str(bid.provenance.get("resource_class") or "") != "storage" for bid in storage_bids):
            raise ZonalRedispatchInputError(f"Storage {asset} has a bid with a non-storage class")
        by_direction = {
            direction: [bid for bid in storage_bids if bid.direction == direction]
            for direction in ("up", "down")
        }
        if any(len(rows) > 1 for rows in by_direction.values()):
            raise ZonalRedispatchInputError(f"Storage {asset} v1 accepts at most one bid per direction")
        if by_direction["up"] and by_direction["down"]:
            if by_direction["down"][0].price_gbp_per_mwh > by_direction["up"][0].price_gbp_per_mwh + TOLERANCE:
                raise ZonalRedispatchInputError(
                    f"Storage {asset} bid curve is not convex and could self-cycle"
                )
    undeclared_storage = sorted(
        bid.asset_id for bid in bids
        if str(bid.provenance.get("resource_class") or "") == "storage"
        and bid.asset_id not in storage
    )
    if undeclared_storage:
        raise ZonalRedispatchInputError("Storage bids lack physical declarations: " + ", ".join(undeclared_storage))

    bid_index: dict[str, int] = {}
    flow_index: dict[str, int] = {}
    shedding_index: dict[str, int] = {}
    storage_discharge_index: dict[str, int] = {}
    storage_charge_index: dict[str, int] = {}
    flow_absolute_index: dict[str, int] = {}
    names: list[str] = []
    bounds: list[tuple[float | None, float | None]] = []

    def variable(name: str, bound: tuple[float | None, float | None]) -> int:
        index = len(names)
        names.append(name)
        bounds.append(bound)
        return index

    bid_capacity: dict[str, float] = {}
    for bid in bids:
        capacity = _available_energy(bid, model_input.period_hours)
        bid_capacity[bid.bid_id] = capacity
        bid_index[bid.bid_id] = variable(f"bid:{bid.bid_id}", (0.0, capacity))

    forward_capacity = dict(period_slice.forward_boundary_capacity_mwh)
    reverse_capacity = dict(period_slice.reverse_boundary_capacity_mwh)
    corridor_ids = {corridor.corridor_id for corridor in network.corridors}
    for corridor in sorted(network.corridors, key=lambda item: item.corridor_id):
        if corridor.corridor_id in forward_capacity:
            bound = (
                -_nonnegative(
                    reverse_capacity.get(corridor.corridor_id),
                    f"{corridor.corridor_id} reverse corridor capacity",
                ),
                _nonnegative(
                    forward_capacity[corridor.corridor_id],
                    f"{corridor.corridor_id} forward corridor capacity",
                ),
            )
        else:
            bound = (None, None)
        flow_index[corridor.corridor_id] = variable(
            f"flow:{corridor.corridor_id}", bound
        )
    for zone in sorted(zone_ids):
        shedding_index[zone] = variable(f"load-shedding:{zone}", (0.0, demand[zone]))
    for asset in sorted(storage):
        specification = storage[asset]
        storage_discharge_index[asset] = variable(
            f"storage-discharge:{asset}",
            (0.0, float(specification["discharge_power_mw"]) * model_input.period_hours),
        )
        storage_charge_index[asset] = variable(
            f"storage-charge:{asset}",
            (0.0, float(specification["charge_power_mw"]) * model_input.period_hours),
        )
    for corridor in sorted(network.corridors, key=lambda item: item.corridor_id):
        flow_absolute_index[corridor.corridor_id] = variable(
            f"absolute-flow:{corridor.corridor_id}", (0.0, None)
        )

    size = len(names)
    primary = np.zeros(size, dtype=float)
    secondary = np.zeros(size, dtype=float)
    physical = np.zeros(size, dtype=float)
    for bid in bids:
        index = bid_index[bid.bid_id]
        primary[index] = bid.price_gbp_per_mwh if bid.direction == "up" else -bid.price_gbp_per_mwh
        secondary[index] = 1.0
    for index in shedding_index.values():
        primary[index] = model_input.voll_gbp_per_mwh
        secondary[index] = 1.0
    for index in storage_discharge_index.values():
        physical[index] = 1.0
    for index in storage_charge_index.values():
        physical[index] = 1.0
    for index in flow_absolute_index.values():
        physical[index] = 1.0
    stable = np.arange(1, size + 1, dtype=float)

    equality_rows: list[np.ndarray] = []
    equality_rhs: list[float] = []
    base_terms_by_zone: defaultdict[str, list[float]] = defaultdict(list)
    for asset in sorted(ahead.schedule_mwh_by_asset):
        base_terms_by_zone[asset_zones[asset]].append(
            float(ahead.schedule_mwh_by_asset[asset])
        )
    base_by_zone = {
        zone: math.fsum(base_terms_by_zone[zone])
        for zone in sorted(base_terms_by_zone)
    }
    corridor_by_id = {corridor.corridor_id: corridor for corridor in network.corridors}
    for zone in zone_ids:
        row = _row(size)
        for bid in bids:
            if bid.zone_id == zone:
                row[bid_index[bid.bid_id]] += 1.0 if bid.direction == "up" else -1.0
        row[shedding_index[zone]] += 1.0
        for corridor in network.corridors:
            if corridor.from_zone_id == zone:
                row[flow_index[corridor.corridor_id]] -= 1.0
            if corridor.to_zone_id == zone:
                row[flow_index[corridor.corridor_id]] += 1.0
        equality_rows.append(row)
        equality_rhs.append(demand[zone] - base_by_zone.get(zone, 0.0))

    for asset, specification in sorted(storage.items()):
        row = _row(size)
        row[storage_discharge_index[asset]] = 1.0
        row[storage_charge_index[asset]] = -1.0
        for bid in bids:
            if bid.asset_id == asset:
                row[bid_index[bid.bid_id]] += -1.0 if bid.direction == "up" else 1.0
        equality_rows.append(row)
        equality_rhs.append(float(ahead.schedule_mwh_by_asset.get(asset, 0.0)))

    # Equal-price bids with the same direction and network effect share
    # their acceptance pro rata to available energy.  Since v4 the resource
    # class is not part of the key: two technologies offering the same price
    # at the same place are economically identical (P2-01 asset-ID shift).
    groups: defaultdict[tuple[object, ...], list[FlexibilityBid]] = defaultdict(list)
    for bid in bids:
        resource_class = str(bid.provenance.get("resource_class") or classes.get(bid.asset_id, "other"))
        if resource_class == "storage":
            continue
        groups[(
            bid.direction,
            bid.zone_id,
            bid.network_effect_id,
            bid.price_gbp_per_mwh,
        )].append(bid)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        first = rows[0]
        first_capacity = bid_capacity[first.bid_id]
        for bid in rows[1:]:
            row = _row(size)
            row[bid_index[bid.bid_id]] = first_capacity
            row[bid_index[first.bid_id]] = -bid_capacity[bid.bid_id]
            equality_rows.append(row)
            equality_rhs.append(0.0)

    inequality_rows: list[np.ndarray] = []
    inequality_rhs: list[float] = []

    def final_dispatch_expression(asset: str) -> np.ndarray:
        row = _row(size)
        for bid in bids:
            if bid.asset_id == asset:
                row[bid_index[bid.bid_id]] += 1.0 if bid.direction == "up" else -1.0
        return row

    for asset_id in sorted(map(str, raw_envelopes)):
        raw_envelope = raw_envelopes[asset_id]
        if not isinstance(raw_envelope, Mapping):
            raise ZonalRedispatchInputError(f"Interconnector envelope {asset_id} must be an object")
        import_capacity = _nonnegative(
            raw_envelope.get("import_capacity_mwh"),
            f"{asset_id} import capacity",
        )
        export_capacity = _nonnegative(
            raw_envelope.get("export_capacity_mwh"),
            f"{asset_id} export capacity",
        )
        minimum = -export_capacity
        maximum = import_capacity
        if asset_id not in assets:
            raise ZonalRedispatchInputError(f"Interconnector envelope {asset_id} has no declared asset")
        expression = final_dispatch_expression(asset_id)
        ahead_value = float(ahead.schedule_mwh_by_asset.get(asset_id, 0.0))
        inequality_rows.extend((expression, -expression))
        inequality_rhs.extend((maximum - ahead_value, ahead_value - minimum))

    for asset in sorted(model_input.realised_availability_mw_by_asset):
        available_mw = model_input.realised_availability_mw_by_asset[asset]
        resource_class = classes.get(asset, "other")
        if asset in storage or resource_class == "export" or asset in raw_envelopes:
            continue
        expression = final_dispatch_expression(asset)
        ahead_value = float(ahead.schedule_mwh_by_asset.get(asset, 0.0))
        upper = float(available_mw) * model_input.period_hours
        inequality_rows.extend((expression, -expression))
        inequality_rhs.extend((upper - ahead_value, ahead_value))

    for asset, specification in sorted(storage.items()):
        opening = float(model_input.initial_soc_mwh_by_asset[asset])
        capacity = float(specification["energy_capacity_mwh"])
        charge_efficiency = float(specification["charge_efficiency"])
        discharge_efficiency = float(specification["discharge_efficiency"])
        upper = _row(size)
        upper[storage_discharge_index[asset]] = 1.0 / discharge_efficiency
        upper[storage_charge_index[asset]] = -charge_efficiency
        inequality_rows.append(upper)
        inequality_rhs.append(opening)
        lower = -upper
        inequality_rows.append(lower)
        inequality_rhs.append(capacity - opening)

    boundary_ids = {boundary.boundary_id for boundary in network.cutsets}
    permitted_capacity_ids = boundary_ids | corridor_ids
    if (
        not boundary_ids.issubset(forward_capacity)
        or not boundary_ids.issubset(reverse_capacity)
        or set(forward_capacity).difference(permitted_capacity_ids)
        or set(reverse_capacity).difference(permitted_capacity_ids)
    ):
        raise ZonalRedispatchInputError(
            "Current-period boundary capacities must name every declared cutset"
        )
    for boundary in network.cutsets:
        transfer = _row(size)
        for member in boundary.members:
            transfer[flow_index[member.corridor_id]] += member.coefficient
        inequality_rows.extend((transfer, -transfer))
        inequality_rhs.extend((
            _nonnegative(
                forward_capacity[boundary.boundary_id],
                f"{boundary.boundary_id} forward boundary capacity",
            ),
            _nonnegative(
                reverse_capacity[boundary.boundary_id],
                f"{boundary.boundary_id} reverse boundary capacity",
            ),
        ))

    for corridor_id, flow in flow_index.items():
        absolute = flow_absolute_index[corridor_id]
        positive = _row(size)
        positive[flow] = 1.0
        positive[absolute] = -1.0
        negative = _row(size)
        negative[flow] = -1.0
        negative[absolute] = -1.0
        inequality_rows.extend((positive, negative))
        inequality_rhs.extend((0.0, 0.0))

    return SinglePeriodProblem(
        model_input=model_input,
        ahead=ahead,
        network_pack=network,
        bids=bids,
        demand_mwh_by_zone=demand,
        asset_zone_id_by_asset=asset_zones,
        resource_class_by_asset=classes,
        resource_cost_gbp_per_mwh_by_asset=costs,
        storage=storage,
        variable_names=tuple(names),
        bounds=tuple(bounds),
        primary_objective=primary,
        secondary_objective=secondary,
        physical_tie_objective=physical,
        stable_tie_objective=stable,
        equality_matrix=_as_matrix(equality_rows, size),
        equality_rhs=np.asarray(equality_rhs, dtype=float),
        inequality_matrix=_as_matrix(inequality_rows, size),
        inequality_rhs=np.asarray(inequality_rhs, dtype=float),
        bid_index=bid_index,
        flow_index=flow_index,
        shedding_index=shedding_index,
        storage_discharge_index=storage_discharge_index,
        storage_charge_index=storage_charge_index,
        flow_absolute_index=flow_absolute_index,
        input_sha256=contract_sha256(model_input),
    )


def _run_highs(
    problem: SinglePeriodProblem,
    objective: np.ndarray,
    *,
    extra_inequalities: Sequence[tuple[np.ndarray, float]] = (),
    extra_equalities: Sequence[tuple[np.ndarray, float]] = (),
    phase: str,
    settings: ZonalSolverSettings = DEFAULT_ZONAL_SOLVER_SETTINGS,
    locks: Sequence["_ObjectiveCap"] = (),
) -> tuple[np.ndarray, dict[str, object]]:
    try:
        import scipy
        from scipy.optimize import linprog
    except ModuleNotFoundError as exc:
        raise ZonalRedispatchSolveError(
            "Zonal redispatch requires the optional SciPy solver capability",
            {"phase": phase, "status": "missing_solver"},
        ) from exc
    rows = [row for row in problem.inequality_matrix]
    rhs = [float(value) for value in problem.inequality_rhs]
    for lock in locks:
        rows.append(np.asarray(lock.coefficients, dtype=float))
        rhs.append(lock.rhs)
    for row, value in extra_inequalities:
        rows.append(np.asarray(row, dtype=float))
        rhs.append(float(value))
    matrix = _as_matrix(rows, len(problem.variable_names))
    equality_rows = [row for row in problem.equality_matrix]
    equality_rhs = [float(value) for value in problem.equality_rhs]
    for row, value in extra_equalities:
        equality_rows.append(np.asarray(row, dtype=float))
        equality_rhs.append(float(value))
    equality_matrix = _as_matrix(equality_rows, len(problem.variable_names))
    options: dict[str, object] = {
        "presolve": settings.presolve,
        "primal_feasibility_tolerance": settings.primal_feasibility_tolerance,
        "dual_feasibility_tolerance": settings.dual_feasibility_tolerance,
    }
    if settings.method in {"highs", "highs-ipm"}:
        options["ipm_optimality_tolerance"] = settings.ipm_optimality_tolerance
    try:
        stack = solver_stack_identity().to_dict()
    except ZonalSolverContractError as exc:
        raise ZonalRedispatchSolveError(
            "Zonal redispatch solver identity is unavailable",
            {
                "phase": phase,
                "error_code": exc.code,
                "solver_settings": settings.to_dict(),
                "completed_phase_optima": [_cap_payload(lock) for lock in locks],
            },
        ) from exc
    result = linprog(
        objective,
        A_ub=matrix if len(matrix) else None,
        b_ub=np.asarray(rhs, dtype=float) if rhs else None,
        A_eq=equality_matrix if len(equality_matrix) else None,
        b_eq=np.asarray(equality_rhs, dtype=float) if equality_rhs else None,
        bounds=problem.bounds,
        method=settings.method,
        options=options,
    )
    diagnostics: dict[str, object] = {
        "phase": phase,
        "method": settings.method,
        "api": "scipy.optimize.linprog",
        "scipy_version": scipy.__version__,
        "solver_stack": stack,
        "solver_settings": settings.to_dict(),
        "completed_phase_optima": [_cap_payload(lock) for lock in locks],
        "status": int(result.status),
        "success": bool(result.success),
        "message": str(result.message),
        "iterations": int(getattr(result, "nit", 0) or 0),
    }
    if not result.success or result.x is None:
        diagnostics["error_code"] = "GF_ZONAL_SOLVER_FAILURE"
        raise ZonalRedispatchSolveError(
            f"Zonal redispatch {phase} solve is infeasible or failed: {result.message}",
            diagnostics,
        )
    values = np.asarray(result.x, dtype=float)
    objective_value = float(np.dot(objective, values))
    if not np.all(np.isfinite(values)) or not math.isfinite(objective_value):
        diagnostics["error_code"] = "GF_ZONAL_SOLVER_NONFINITE_RESULT"
        raise ZonalRedispatchSolveError(
            f"Zonal redispatch {phase} solve returned non-finite diagnostics",
            diagnostics,
        )
    diagnostics["objective_value"] = objective_value
    return values, diagnostics


@dataclass(frozen=True)
class _ObjectiveCap:
    coefficients: np.ndarray
    objective_key: str
    phase_id: str
    objective_unit: str
    optimum: float
    rhs: float
    computed_tolerance: float
    nonzero_terms: int
    absolute_term_scale: float


def _reconstruction_allowance(
    nonzero_terms: int,
    absolute_term_scale: float,
) -> float:
    if nonzero_terms <= 0:
        return 0.0
    epsilon = float(np.finfo(float).eps)
    gamma_n = nonzero_terms * epsilon / (1.0 - nonzero_terms * epsilon)
    return float(gamma_n * absolute_term_scale)


def _cap_payload(lock: _ObjectiveCap) -> dict[str, object]:
    return {
        "objective_key": lock.objective_key,
        "phase_id": lock.phase_id,
        "objective_unit": lock.objective_unit,
        "optimum": lock.optimum,
        "computed_tolerance": lock.computed_tolerance,
        "nonzero_terms": lock.nonzero_terms,
        "absolute_term_scale": lock.absolute_term_scale,
        "reconstruction_allowance": _reconstruction_allowance(
            lock.nonzero_terms, lock.absolute_term_scale
        ),
        "rhs": lock.rhs,
    }


_OBJECTIVE_CONTRACT = {
    "primary_bid_cost_gbp": ("primary_bid_cost", "GBP", 1e-8),
    "secondary_schedule_deviation_mwh": (
        "secondary_schedule_deviation", "MWh", 1e-9,
    ),
    "physical_throughput_mwh": ("physical_throughput", "MWh", 1e-9),
}

# Solver contract v4 (Q5): every lock right-hand side uses the
# coefficient-aware numerical tolerance.  The GBP 1 study policy is only the
# validated/absolute ceiling used by ``classify_lock``; v3 used it as the lock
# allowance and later phases spent it on spurious shedding (P2-01).


def _active_solver_tolerance(settings: ZonalSolverSettings) -> float:
    values = [
        settings.primal_feasibility_tolerance,
        settings.dual_feasibility_tolerance,
    ]
    if settings.method in {"highs", "highs-ipm"}:
        values.append(settings.ipm_optimality_tolerance)
    return max(values)


def _lock_solver_tolerance(settings: ZonalSolverSettings, objective_key: str) -> float:
    """Solver scale used by one lock's coefficient-aware tolerance.

    v4 bid-cost lock: the declared solver feasibility tolerance itself, so the
    allowance later phases may spend is a numerical one (about 1e-9 of the
    bid-cost scale) and the exact-lock CBC oracle agrees within 1e-6 MWh.
    MWh locks keep the module's 1e-8 floor, which HiGHS needs to certify the
    stacked lock rows in the unscaled model.
    """

    active = _active_solver_tolerance(settings)
    if objective_key == "primary_bid_cost_gbp":
        return active
    return max(active, TOLERANCE)


def _objective_cap(
    coefficients: np.ndarray,
    optimum_values: np.ndarray,
    settings: ZonalSolverSettings,
    objective_key: str,
    *,
    allow_constant: bool = False,
) -> _ObjectiveCap:
    phase_id, unit, unit_floor = _OBJECTIVE_CONTRACT[objective_key]
    coefficient_array = np.asarray(coefficients, dtype=float)
    optimum_array = np.asarray(optimum_values, dtype=float)
    is_constant = not np.count_nonzero(coefficient_array)
    if allow_constant and is_constant:
        if (
            coefficient_array.ndim != 1
            or coefficient_array.shape != optimum_array.shape
            or not np.all(np.isfinite(coefficient_array))
            or not np.all(np.isfinite(optimum_array))
        ):
            raise ZonalSolverContractError(
                "GF_ZONAL_LOCK_TOLERANCE_INVALID",
                f"{phase_id} objective vectors are invalid",
            )
        computed_tolerance = unit_floor
        nonzero_terms = 0
        absolute_term_scale = 0.0
    else:
        tolerance = compute_lock_tolerance(
            coefficient_array,
            optimum_array,
            unit_floor,
            _lock_solver_tolerance(settings, objective_key),
        )
        computed_tolerance = tolerance.tolerance
        nonzero_terms = tolerance.nonzero_terms
        absolute_term_scale = tolerance.absolute_term_scale
    optimum = float(np.dot(coefficients, optimum_values))
    if not math.isfinite(optimum):
        raise ZonalSolverContractError(
            "GF_ZONAL_LOCK_TOLERANCE_INVALID",
            f"{phase_id} optimum is not finite",
        )
    reconstruction_allowance = _reconstruction_allowance(
        nonzero_terms, absolute_term_scale
    )
    rhs = math.nextafter(
        optimum + computed_tolerance - reconstruction_allowance,
        -math.inf,
    )
    if rhs < optimum:
        raise ZonalSolverContractError(
            "GF_ZONAL_LOCK_TOLERANCE_INVALID",
            f"{phase_id} tolerance cannot be represented as a one-sided cap",
        )
    return _ObjectiveCap(
        np.asarray(coefficients, dtype=float).copy(),
        objective_key,
        phase_id,
        unit,
        optimum,
        rhs,
        computed_tolerance,
        nonzero_terms,
        absolute_term_scale,
    )


def _contract_solve_error(
    error: ZonalSolverContractError,
    *,
    phase: str,
    settings: ZonalSolverSettings,
    locks: Sequence[_ObjectiveCap],
    completed_phases: Mapping[str, object] | None = None,
) -> ZonalRedispatchSolveError:
    return ZonalRedispatchSolveError(
        f"Zonal redispatch numerical contract failed: {error}",
        {
            "phase": phase,
            "error_code": error.code,
            "solver_settings": settings.to_dict(),
            "completed_phase_optima": [_cap_payload(lock) for lock in locks],
            "phases": dict(completed_phases or {}),
        },
    )


def _objective_diagnostic_payload(
    row: ObjectiveLockDiagnostic,
) -> dict[str, object]:
    """Keep the v7 public row shape while retaining its effective threshold."""

    payload = asdict(row)
    payload.pop("warning_fraction")
    return payload


def _finalise_lexicographic_solution(
    problem: SinglePeriodProblem,
    final_values: np.ndarray,
    phase_diagnostics: Mapping[str, object],
    locks: Sequence[_ObjectiveCap],
    settings: ZonalSolverSettings,
) -> SinglePeriodSolution:
    raw = SinglePeriodSolution(
        np.asarray(final_values, dtype=float),
        float(np.dot(problem.primary_objective, final_values)),
        float(np.dot(problem.secondary_objective, final_values)),
        float(np.dot(problem.physical_tie_objective, final_values)),
        float(np.dot(problem.stable_tie_objective, final_values)),
        {},
    )
    try:
        bounded = _canonicalize_solution_bounds(problem, raw)
    except ZonalRedispatchSolveError as exc:
        diagnostics = {
            **dict(exc.diagnostics),
            "error_code": exc.diagnostics.get(
                "error_code", "GF_ZONAL_SOLUTION_BOUND_VIOLATION"
            ),
            "solver_settings": settings.to_dict(),
            "completed_phase_optima": [_cap_payload(lock) for lock in locks],
            "phases": dict(phase_diagnostics),
        }
        raise ZonalRedispatchSolveError(str(exc), diagnostics) from exc
    diagnostics: list[ObjectiveLockDiagnostic] = []
    for lock in locks:
        achieved = float(np.dot(lock.coefficients, bounded.values))
        degradation = max(0.0, achieved - lock.optimum)
        try:
            classification = classify_lock(
                degradation,
                lock.computed_tolerance,
                settings.validated_ceilings[lock.objective_key],
                settings.warning_fraction,
                settings.absolute_ceilings[lock.objective_key],
            )
        except ZonalSolverContractError as exc:
            failure = _contract_solve_error(
                exc,
                phase="final_objective_validation",
                settings=settings,
                locks=locks,
                completed_phases=phase_diagnostics,
            )
            failure.diagnostics.update({
                "objective_key": lock.objective_key,
                "phase_id": lock.phase_id,
                "objective_unit": lock.objective_unit,
                "optimum": lock.optimum,
                "achieved_final_value": achieved,
                "degradation": degradation,
                "computed_tolerance": lock.computed_tolerance,
                "excess_degradation": max(
                    0.0, degradation - lock.computed_tolerance
                ),
            })
            raise failure from exc
        diagnostics.append(ObjectiveLockDiagnostic(
            phase_id=lock.phase_id,
            objective_unit=lock.objective_unit,
            optimum=lock.optimum,
            achieved_final_value=achieved,
            degradation=degradation,
            computed_tolerance=lock.computed_tolerance,
            validated_ceiling=settings.validated_ceilings[lock.objective_key],
            absolute_ceiling=settings.absolute_ceilings[lock.objective_key],
            nonzero_terms=lock.nonzero_terms,
            absolute_term_scale=lock.absolute_term_scale,
            validation_class=classification.status,
            warning_fraction=settings.warning_fraction,
        ))
    stack = solver_stack_identity().to_dict()
    return SinglePeriodSolution(
        bounded.values,
        float(np.dot(problem.primary_objective, bounded.values)),
        float(np.dot(problem.secondary_objective, bounded.values)),
        float(np.dot(problem.physical_tie_objective, bounded.values)),
        float(np.dot(problem.stable_tie_objective, bounded.values)),
        {
            "solver_contract": settings.to_dict(),
            "solver_stack": stack,
            "phases": dict(phase_diagnostics),
            "bound_canonicalization": bounded.diagnostics["bound_canonicalization"],
            "automatic_copperplate_fallback": False,
            "network_solver_diagnostics": [
                _objective_diagnostic_payload(row) for row in diagnostics
            ],
        },
        tuple(diagnostics),
    )


def _tighten_violated_objective_cap(
    locks: Sequence[_ObjectiveCap],
    diagnostics: Mapping[str, object],
    settings: ZonalSolverSettings,
) -> tuple[_ObjectiveCap, ...]:
    """Tighten exactly one failed lock without changing its declared tolerance."""

    objective_key = diagnostics.get("objective_key")
    try:
        excess = float(diagnostics["excess_degradation"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ZonalSolverContractError(
            "GF_ZONAL_LOCK_TOLERANCE_INVALID",
            "objective lock repair diagnostics are incomplete",
        ) from exc
    if not isinstance(objective_key, str) or not math.isfinite(excess) or excess <= 0.0:
        raise ZonalSolverContractError(
            "GF_ZONAL_LOCK_TOLERANCE_INVALID",
            "objective lock repair requires a positive finite excess",
        )

    repaired: list[_ObjectiveCap] = []
    matched = False
    for lock in locks:
        if lock.objective_key != objective_key:
            repaired.append(lock)
            continue
        matched = True
        # HiGHS may return a successful solution with a lock-row residual at
        # its primal feasibility scale.  Reserve several declared tolerance
        # units at the magnitude of this row's RHS, but never more than a
        # quarter of the lock's own computed tolerance: the v4 bid-cost lock
        # uses the declared 1e-9 solver scale, so its whole headroom is about
        # 1e-9 x |rhs| and an |rhs|-scaled guard (8e-9 x |rhs|) would make
        # every GB-scale primary repair impossible (M2-P0-8a review).
        solver_guard = min(
            8.0
            * settings.primal_feasibility_tolerance
            * max(1.0, abs(lock.rhs)),
            LOCK_REPAIR_GUARD_FRACTION * lock.computed_tolerance,
        )
        guard = max(
            solver_guard,
            _reconstruction_allowance(lock.nonzero_terms, lock.absolute_term_scale),
            math.ulp(lock.rhs),
        )
        tightened_rhs = math.nextafter(lock.rhs - excess - guard, -math.inf)
        if not math.isfinite(tightened_rhs):
            raise ZonalSolverContractError(
                "GF_ZONAL_LOCK_TOLERANCE_INVALID",
                f"{lock.phase_id} repaired cap is not finite",
            )
        if tightened_rhs < lock.optimum:
            raise ZonalSolverContractError(
                "GF_ZONAL_LOCK_TOLERANCE_INVALID",
                f"{lock.phase_id} lock repair requires {excess + guard} "
                f"but only {lock.rhs - lock.optimum} cap headroom is available",
            )
        repaired.append(replace(lock, rhs=tightened_rhs))
    if not matched:
        raise ZonalSolverContractError(
            "GF_ZONAL_LOCK_TOLERANCE_INVALID",
            f"objective lock repair target is unknown: {objective_key}",
        )
    return tuple(repaired)


_LEXICOGRAPHIC_LOCK_ORDER = (
    "primary_bid_cost_gbp",
    "secondary_schedule_deviation_mwh",
    "physical_throughput_mwh",
)


def _resolve_downstream_locks(
    problem: SinglePeriodProblem,
    locks: tuple[_ObjectiveCap, ...],
    repaired_key: str,
    settings: ZonalSolverSettings,
    phases: dict[str, object],
    *,
    attempt: int,
) -> tuple[tuple[_ObjectiveCap, ...], tuple[_ObjectiveCap, ...]]:
    """Re-solve every phase after a tightened lock and recompute its cap.

    A later phase's optimum was reached while spending the earlier lock's
    allowance (the secondary phase typically uses the whole bid-cost
    tolerance).  Tightening only the earlier cap would leave the later caps
    unreachable and the stable re-solve infeasible, so each later phase is
    solved again under the tightened caps and its own coefficient-aware cap is
    rebuilt from the new optimum.  Tolerances are never widened: each cap is
    recomputed by the same formula as in ``solve_lexicographic``.
    """

    order = [lock.objective_key for lock in locks]
    if order != list(_LEXICOGRAPHIC_LOCK_ORDER[: len(order)]):
        # Hand-built lock sets (tests, partial solves) keep the old
        # single-cap behaviour.
        return locks, ()
    position = order.index(repaired_key)
    kept = list(locks[: position + 1])
    rebuilt: list[_ObjectiveCap] = []
    for lock in locks[position + 1:]:
        if lock.objective_key == "secondary_schedule_deviation_mwh":
            objective, allow_constant = problem.secondary_objective, False
        else:
            objective, allow_constant = problem.physical_tie_objective, True
        phase = f"{lock.phase_id}_lock_repair_{attempt}"
        values, phases[phase] = _run_highs(
            problem,
            objective,
            phase=phase,
            settings=settings,
            locks=tuple(kept),
        )
        try:
            cap = _objective_cap(
                objective,
                values,
                settings,
                lock.objective_key,
                allow_constant=allow_constant,
            )
        except ZonalSolverContractError as exc:
            raise _contract_solve_error(
                exc,
                phase=f"{lock.phase_id}_lock_repair_{attempt}",
                settings=settings,
                locks=kept,
                completed_phases=phases,
            ) from exc
        kept.append(cap)
        rebuilt.append(cap)
    return tuple(kept), tuple(rebuilt)


def _finalise_with_lock_repair(
    problem: SinglePeriodProblem,
    final_values: np.ndarray,
    phases: dict[str, object],
    locks: tuple[_ObjectiveCap, ...],
    settings: ZonalSolverSettings,
) -> SinglePeriodSolution:
    """Retry only a final lock violation with a deterministically tighter cap."""

    values = final_values
    active_locks = locks
    repairs: list[dict[str, object]] = []
    # At most one targeted repair per declared objective is normally needed;
    # permit three repairs so each of the three locks can be corrected once.
    for attempt in range(4):
        try:
            return _finalise_lexicographic_solution(
                problem, values, phases, active_locks, settings
            )
        except ZonalRedispatchSolveError as exc:
            if (
                exc.diagnostics.get("error_code")
                != "GF_ZONAL_OBJECTIVE_LOCK_VIOLATION"
                or attempt >= 3
            ):
                raise
            try:
                tightened = _tighten_violated_objective_cap(
                    active_locks, exc.diagnostics, settings
                )
            except ZonalSolverContractError as repair_error:
                exc.diagnostics["lock_repair_error"] = {
                    "error_code": repair_error.code,
                    "message": str(repair_error),
                    "attempt": attempt + 1,
                    "repair_history": tuple(repairs),
                }
                raise exc from repair_error
            before = next(
                lock for lock in active_locks
                if lock.objective_key == exc.diagnostics["objective_key"]
            )
            after = next(
                lock for lock in tightened
                if lock.objective_key == exc.diagnostics["objective_key"]
            )
            repairs.append({
                "attempt": attempt + 1,
                "objective_key": before.objective_key,
                "phase_id": before.phase_id,
                "achieved_final_value": exc.diagnostics["achieved_final_value"],
                "degradation": exc.diagnostics["degradation"],
                "computed_tolerance": exc.diagnostics["computed_tolerance"],
                "excess_degradation": exc.diagnostics["excess_degradation"],
                "previous_rhs": before.rhs,
                "tightened_rhs": after.rhs,
                "available_headroom": before.rhs - before.optimum,
            })
            active_locks = tightened
            try:
                active_locks, downstream = _resolve_downstream_locks(
                    problem,
                    active_locks,
                    before.objective_key,
                    settings,
                    phases,
                    attempt=attempt + 1,
                )
                repairs[-1]["recomputed_downstream_locks"] = tuple(
                    _cap_payload(lock) for lock in downstream
                )
                phases["stable_lock_repairs"] = tuple(repairs)
                values, retry_diagnostics = _run_highs(
                    problem,
                    problem.stable_tie_objective,
                    phase=f"stable_key_lock_repair_{attempt + 1}",
                    settings=settings,
                    locks=active_locks,
                )
            except ZonalRedispatchSolveError as retry_error:
                retry_error.diagnostics.update({
                    "phase": f"stable_key_lock_repair_{attempt + 1}",
                    "original_lock_violation": {
                        key: exc.diagnostics[key]
                        for key in (
                            "objective_key", "phase_id", "objective_unit",
                            "optimum", "achieved_final_value", "degradation",
                            "computed_tolerance", "excess_degradation",
                        )
                        if key in exc.diagnostics
                    },
                    "lock_repair_history": tuple(repairs),
                })
                raise
            phases[f"stable_lock_repair_{attempt + 1}"] = retry_diagnostics
    raise AssertionError("unreachable objective lock repair state")


def bid_cost_coefficients(problem: SinglePeriodProblem) -> np.ndarray:
    """The primary objective without its VOLL x shedding terms."""

    coefficients = np.asarray(problem.primary_objective, dtype=float).copy()
    for index in problem.shedding_index.values():
        coefficients[index] = 0.0
    return coefficients


def lock_primary_shedding(
    problem: SinglePeriodProblem,
    primary_values: np.ndarray,
) -> tuple[SinglePeriodProblem, dict[str, object]]:
    """Lock total load shedding at its primary optimum before any later phase.

    No primary shedding fixes every shedding variable to exactly zero, so no
    later phase can trade VOLL against flow or tie-break terms (P2-01: v3
    created 1/(VOLL-p) MWh of shedding in the physical phase).  Positive
    primary shedding adds one row ``sum(shed) <= shed*``; the primary point
    satisfies it, so it is always feasible, and how the shed total is spread
    across zones (degenerate in the primary) is left to the later phases.
    """

    indices = sorted(problem.shedding_index.values())
    shed_total = math.fsum(float(primary_values[index]) for index in indices)
    if shed_total <= TOLERANCE:
        bounds = list(problem.bounds)
        for index in indices:
            bounds[index] = (0.0, 0.0)
        return replace(problem, bounds=tuple(bounds)), {
            "mode": "fixed_zero",
            "primary_shed_total_mwh": shed_total,
            "rhs_mwh": 0.0,
        }
    row = np.zeros(len(problem.variable_names), dtype=float)
    row[indices] = 1.0
    rhs = max(shed_total, 0.0)
    return replace(
        problem,
        inequality_matrix=np.vstack([problem.inequality_matrix, row])
        if len(problem.inequality_matrix)
        else row.reshape(1, -1),
        inequality_rhs=np.append(problem.inequality_rhs, rhs),
    ), {
        "mode": "total_cap",
        "primary_shed_total_mwh": shed_total,
        "rhs_mwh": rhs,
    }


def solve_lexicographic(
    problem: SinglePeriodProblem,
    settings: ZonalSolverSettings,
) -> SinglePeriodSolution:
    """Run the four fixed HiGHS phases: shed lock, then numerical caps."""

    settings = validate_solver_settings(settings.to_dict())
    locks: list[_ObjectiveCap] = []
    phases: dict[str, object] = {}
    primary_values, phases["primary"] = _run_highs(
        problem,
        problem.primary_objective,
        phase="primary_bid_cost",
        settings=settings,
    )
    problem, phases["primary_shed_lock"] = lock_primary_shedding(
        problem, primary_values
    )
    try:
        locks.append(_objective_cap(
            bid_cost_coefficients(problem),
            primary_values,
            settings,
            "primary_bid_cost_gbp",
            allow_constant=True,
        ))
    except ZonalSolverContractError as exc:
        raise _contract_solve_error(
            exc,
            phase="primary_bid_cost_lock",
            settings=settings,
            locks=locks,
            completed_phases=phases,
        ) from exc
    secondary_values, phases["secondary"] = _run_highs(
        problem,
        problem.secondary_objective,
        phase="secondary_schedule_deviation",
        settings=settings,
        locks=tuple(locks),
    )
    try:
        locks.append(_objective_cap(
            problem.secondary_objective,
            secondary_values,
            settings,
            "secondary_schedule_deviation_mwh",
        ))
    except ZonalSolverContractError as exc:
        raise _contract_solve_error(
            exc,
            phase="secondary_schedule_deviation_lock",
            settings=settings,
            locks=locks,
            completed_phases=phases,
        ) from exc
    physical_values, phases["physical"] = _run_highs(
        problem,
        problem.physical_tie_objective,
        phase="physical_throughput",
        settings=settings,
        locks=tuple(locks),
    )
    try:
        locks.append(_objective_cap(
            problem.physical_tie_objective,
            physical_values,
            settings,
            "physical_throughput_mwh",
            allow_constant=True,
        ))
    except ZonalSolverContractError as exc:
        raise _contract_solve_error(
            exc,
            phase="physical_throughput_lock",
            settings=settings,
            locks=locks,
            completed_phases=phases,
        ) from exc
    final_values, phases["stable"] = _run_highs(
        problem,
        problem.stable_tie_objective,
        phase="stable_key",
        settings=settings,
        locks=tuple(locks),
    )
    return _finalise_with_lock_repair(
        problem, final_values, phases, tuple(locks), settings
    )


def solve_primary(problem: SinglePeriodProblem) -> SinglePeriodSolution:
    values, diagnostics = _run_highs(
        problem, problem.primary_objective, phase="primary_bid_cost"
    )
    objective = float(np.dot(problem.primary_objective, values))
    return SinglePeriodSolution(values, objective, math.nan, math.nan, math.nan, {
        "primary": diagnostics,
    })


def solve_secondary(
    problem: SinglePeriodProblem, primary: SinglePeriodSolution
) -> SinglePeriodSolution:
    settings = validate_solver_settings(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
    problem, shed_lock = lock_primary_shedding(problem, primary.values)
    locks = [
        _objective_cap(
            bid_cost_coefficients(problem),
            primary.values,
            settings,
            "primary_bid_cost_gbp",
            allow_constant=True,
        )
    ]
    phases: dict[str, object] = {
        "primary": dict(primary.diagnostics.get("primary") or {}),
        "primary_shed_lock": shed_lock,
    }
    secondary_values, secondary_diagnostics = _run_highs(
        problem,
        problem.secondary_objective,
        locks=tuple(locks),
        phase="secondary_schedule_deviation",
        settings=settings,
    )
    phases["secondary"] = secondary_diagnostics
    locks.append(_objective_cap(
        problem.secondary_objective,
        secondary_values,
        settings,
        "secondary_schedule_deviation_mwh",
    ))
    physical_values, physical_diagnostics = _run_highs(
        problem,
        problem.physical_tie_objective,
        locks=tuple(locks),
        phase="physical_throughput",
        settings=settings,
    )
    phases["physical"] = physical_diagnostics
    locks.append(_objective_cap(
        problem.physical_tie_objective,
        physical_values,
        settings,
        "physical_throughput_mwh",
        allow_constant=True,
    ))
    stable_values, stable_diagnostics = _run_highs(
        problem,
        problem.stable_tie_objective,
        locks=tuple(locks),
        phase="stable_key",
        settings=settings,
    )
    phases["stable"] = stable_diagnostics
    return _finalise_with_lock_repair(
        problem,
        stable_values,
        phases,
        tuple(locks),
        settings,
    )


def _canonicalize_solution_bounds(
    problem: SinglePeriodProblem,
    solution: SinglePeriodSolution,
) -> SinglePeriodSolution:
    """Map tolerance-sized LP bound noise back to the declared feasible boundary."""

    values = np.asarray(solution.values, dtype=float).copy()
    corrections: list[dict[str, object]] = []
    for index, (value, bound) in enumerate(zip(values, problem.bounds)):
        lower, upper = bound
        target: float | None = None
        if lower is not None and value < lower:
            violation = float(lower - value)
            if violation > TOLERANCE:
                raise ZonalRedispatchSolveError(
                    f"Solver variable {problem.variable_names[index]} violated its declared bound",
                    {
                        "phase": "solution_bound_canonicalization",
                        "error_code": "GF_ZONAL_SOLUTION_BOUND_VIOLATION",
                        "variable": problem.variable_names[index],
                        "value": float(value),
                        "lower_bound": float(lower),
                        "violation": violation,
                        "tolerance": TOLERANCE,
                    },
                )
            target = float(lower)
        elif upper is not None and value > upper:
            violation = float(value - upper)
            if violation > TOLERANCE:
                raise ZonalRedispatchSolveError(
                    f"Solver variable {problem.variable_names[index]} violated its declared bound",
                    {
                        "phase": "solution_bound_canonicalization",
                        "error_code": "GF_ZONAL_SOLUTION_BOUND_VIOLATION",
                        "variable": problem.variable_names[index],
                        "value": float(value),
                        "upper_bound": float(upper),
                        "violation": violation,
                        "tolerance": TOLERANCE,
                    },
                )
            target = float(upper)
        if target is not None:
            corrections.append({
                "variable": problem.variable_names[index],
                "raw_value": float(value),
                "canonical_value": target,
                "absolute_correction": abs(target - float(value)),
            })
            values[index] = target

    physical = np.zeros(len(problem.variable_names), dtype=float)
    for index in problem.storage_discharge_index.values():
        physical[index] = 1.0
    for index in problem.storage_charge_index.values():
        physical[index] = 1.0
    for index in problem.flow_absolute_index.values():
        physical[index] = 1.0
    stable = np.arange(1, len(problem.variable_names) + 1, dtype=float)
    return SinglePeriodSolution(
        values,
        float(np.dot(problem.primary_objective, values)),
        float(np.dot(problem.secondary_objective, values)),
        float(np.dot(physical, values)),
        float(np.dot(stable, values)),
        {
            **dict(solution.diagnostics),
            "bound_canonicalization": {
                "tolerance": TOLERANCE,
                "correction_count": len(corrections),
                "maximum_absolute_correction": max(
                    (float(row["absolute_correction"]) for row in corrections),
                    default=0.0,
                ),
                "corrections": corrections,
            },
        },
    )


def validate_solution(
    problem: SinglePeriodProblem, solution: SinglePeriodSolution
) -> dict[str, object]:
    values = solution.values
    equality = (
        problem.equality_matrix @ values - problem.equality_rhs
        if len(problem.equality_matrix)
        else np.asarray([], dtype=float)
    )
    inequality = (
        problem.inequality_matrix @ values - problem.inequality_rhs
        if len(problem.inequality_matrix)
        else np.asarray([], dtype=float)
    )
    bound_violation = 0.0
    for value, (lower, upper) in zip(values, problem.bounds):
        if lower is not None:
            bound_violation = max(bound_violation, lower - value)
        if upper is not None:
            bound_violation = max(bound_violation, value - upper)
    simultaneous: dict[str, dict[str, float]] = {}
    for asset in problem.storage:
        discharge = float(values[problem.storage_discharge_index[asset]])
        charge = float(values[problem.storage_charge_index[asset]])
        if discharge > TOLERANCE and charge > TOLERANCE:
            simultaneous[asset] = {
                "charge_mwh": charge,
                "discharge_mwh": discharge,
            }
    maximum = max(
        float(np.max(np.abs(equality))) if equality.size else 0.0,
        float(np.max(np.maximum(inequality, 0.0))) if inequality.size else 0.0,
        max(bound_violation, 0.0),
    )
    if simultaneous:
        raise ZonalRedispatchSolveError(
            "Convex storage solution contains simultaneous charge and discharge",
            {"simultaneous_storage": simultaneous},
        )
    if maximum > 1e-7:
        raise ZonalRedispatchSolveError(
            f"Zonal redispatch residual {maximum} exceeds tolerance",
            {"maximum_residual": maximum},
        )
    return {
        "maximum_residual": maximum,
        "maximum_equality_residual": (
            float(np.max(np.abs(equality))) if equality.size else 0.0
        ),
        "maximum_inequality_violation": (
            float(np.max(np.maximum(inequality, 0.0))) if inequality.size else 0.0
        ),
        "maximum_bound_violation": max(bound_violation, 0.0),
        "simultaneous_storage": simultaneous,
    }


def _sorted_scientific_numeric_mapping(
    value: object,
    label: str,
) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    result: dict[str, float] = {}
    for key in sorted(map(str, value)):
        number = float(value[key])
        if not math.isfinite(number):
            raise ValueError(f"{label}.{key} must be finite")
        result[key] = number
    return result


def normalized_zonal_scientific_result_payload(
    result: BalancingResult,
) -> dict[str, object]:
    """Return the exact scientific identity, excluding audit provenance and paths."""

    extensions = result.extensions
    raw_storage = extensions.get("storage_dispatch_mwh_by_asset", {})
    if not isinstance(raw_storage, Mapping):
        raise ValueError("storage_dispatch_mwh_by_asset must be a mapping")
    storage_dispatch: dict[str, dict[str, float]] = {}
    for asset in sorted(map(str, raw_storage)):
        storage_dispatch[asset] = _sorted_scientific_numeric_mapping(
            raw_storage[asset], f"storage_dispatch_mwh_by_asset.{asset}"
        )
    objective_keys = (
        "primary_objective_gbp",
        "secondary_objective_mwh",
        "physical_tie_objective",
        "stable_tie_objective",
    )
    objectives: dict[str, float] = {}
    for key in objective_keys:
        number = float(extensions[key])
        if not math.isfinite(number):
            raise ValueError(f"{key} must be finite")
        objectives[key] = number
    return {
        "schema_version": "value.zonal-scientific-result/v1",
        "accepted_adjustments": [
            row.to_dict()
            for row in sorted(
                result.accepted_adjustments,
                key=lambda row: (row.bid_id, row.agent_id, row.asset_id, row.zone_id),
            )
        ],
        "final_dispatch_mwh_by_asset": _sorted_scientific_numeric_mapping(
            result.final_dispatch_mwh_by_asset, "final_dispatch_mwh_by_asset"
        ),
        "final_soc_mwh_by_asset": _sorted_scientific_numeric_mapping(
            result.final_soc_mwh_by_asset, "final_soc_mwh_by_asset"
        ),
        "curtailment_mwh_by_class": _sorted_scientific_numeric_mapping(
            result.curtailment_mwh_by_class, "curtailment_mwh_by_class"
        ),
        "blackout_mwh": float(result.blackout_mwh),
        "settlement_cashflow_gbp_by_agent": _sorted_scientific_numeric_mapping(
            result.settlement_cashflow_gbp_by_agent,
            "settlement_cashflow_gbp_by_agent",
        ),
        "resource_cost_gbp_by_class": _sorted_scientific_numeric_mapping(
            result.resource_cost_gbp_by_class, "resource_cost_gbp_by_class"
        ),
        "energy_balance_residual_mwh": float(result.energy_balance_residual_mwh),
        "corridor_flow_mwh_by_id": _sorted_scientific_numeric_mapping(
            extensions.get("corridor_flow_mwh_by_id", {}),
            "corridor_flow_mwh_by_id",
        ),
        "boundary_transfer_mwh_by_id": _sorted_scientific_numeric_mapping(
            extensions.get("boundary_transfer_mwh_by_id", {}),
            "boundary_transfer_mwh_by_id",
        ),
        "load_shedding_mwh_by_zone": _sorted_scientific_numeric_mapping(
            extensions.get("load_shedding_mwh_by_zone", {}),
            "load_shedding_mwh_by_zone",
        ),
        "storage_dispatch_mwh_by_asset": storage_dispatch,
        "objectives": objectives,
    }


def normalized_zonal_scientific_result_sha256(result: BalancingResult) -> str:
    """Hash the normalized scientific output without weakening result provenance."""

    return contract_sha256(normalized_zonal_scientific_result_payload(result))


class ZonalRedispatchBalancing:
    id = "value-zonal-redispatch-balancing"
    version = "4.0.0"

    def __init__(
        self,
        solver_settings: ZonalSolverSettings | None = None,
        evidence_root: Path | None = None,
    ) -> None:
        supplied = solver_settings or DEFAULT_ZONAL_SOLVER_SETTINGS
        self._solver_settings = validate_solver_settings(supplied.to_dict())
        self._evidence_root = Path(evidence_root).resolve() if evidence_root else None
        self._consumed_input_sha256: set[str] = set()
        self._consumed_input_sha256_sequence: list[tuple[int, str]] = []
        self._resolver: ImmutableContextResolver | None = None
        self._run_context: RunStaticContext | None = None
        self._year_context: YearContext | None = None
        self._run_context_ref: RunContextRef | None = None
        self._year_context_ref: YearContextRef | None = None
        self._network_pack: ZonalNetworkPack | None = None
        self._annual_metadata: Mapping[str, object] | None = None
        self._zonal_demand_mode = ""
        self._period_index_by_id: dict[str, int] = {}

    def configure_run(self, *, output_dir: Path | None) -> None:
        self._evidence_root = Path(output_dir).resolve() if output_dir else None

    def export_runtime_state(self) -> Mapping[str, object]:
        """Export only the solver-neutral one-use input history."""

        consumed = [
            {"period_index": period_index, "input_sha256": input_sha256}
            for period_index, input_sha256 in self._consumed_input_sha256_sequence
        ]
        next_period_index = (
            max(
                period_index
                for period_index, _input_sha256 in self._consumed_input_sha256_sequence
            )
            + 1
            if consumed
            else 0
        )
        return {
            "schema_version": "value.zonal-redispatch-runtime-state/v1",
            "next_period_index": next_period_index,
            "consumed_inputs": consumed,
        }

    def restore_runtime_state(self, state: Mapping[str, object]) -> None:
        """Restore a validated one-use input history without solver objects."""

        expected = {"schema_version", "next_period_index", "consumed_inputs"}
        if not isinstance(state, Mapping) or set(state) != expected:
            raise ValueError(
                f"Zonal runtime-state fields must be exactly {sorted(expected)}"
            )
        if state["schema_version"] != "value.zonal-redispatch-runtime-state/v1":
            raise ValueError("Unsupported zonal runtime-state schema_version")
        next_period_index = state["next_period_index"]
        if (
            isinstance(next_period_index, bool)
            or not isinstance(next_period_index, int)
            or next_period_index < 0
        ):
            raise ValueError("next_period_index must be a non-negative integer")
        raw_consumed = state["consumed_inputs"]
        if not isinstance(raw_consumed, (list, tuple)):
            raise ValueError("consumed_inputs must be an array")
        sequence: list[tuple[int, str]] = []
        hashes: set[str] = set()
        for item in raw_consumed:
            if not isinstance(item, Mapping) or set(item) != {
                "period_index",
                "input_sha256",
            }:
                raise ValueError(
                    "Each consumed input must contain period_index and input_sha256"
                )
            period_index = item["period_index"]
            input_sha256 = item["input_sha256"]
            if (
                isinstance(period_index, bool)
                or not isinstance(period_index, int)
                or period_index < 0
                or period_index >= next_period_index
            ):
                raise ValueError(
                    "Consumed-input period must be strictly before next_period_index"
                )
            if (
                not isinstance(input_sha256, str)
                or len(input_sha256) != 64
                or any(character not in "0123456789abcdef" for character in input_sha256)
            ):
                raise ValueError("Consumed input hash must be a lowercase SHA-256")
            if input_sha256 in hashes:
                raise ValueError("Consumed input hashes must be unique")
            sequence.append((period_index, input_sha256))
            hashes.add(input_sha256)
        if [period_index for period_index, _input_sha256 in sequence] != list(
            range(next_period_index)
        ):
            raise ValueError(
                "Consumed inputs must be the ordered sequence 0..next_period_index-1"
            )
        self._consumed_input_sha256_sequence = sequence
        self._consumed_input_sha256 = hashes

    def configure(
        self,
        run_context: RunStaticContext,
        resolver: ImmutableContextResolver,
    ) -> None:
        if not isinstance(run_context, RunStaticContext):
            raise ZonalRedispatchInputError("Zonal balancing requires a RunStaticContext")
        if not isinstance(resolver, ImmutableContextResolver):
            raise ZonalRedispatchInputError(
                "Zonal balancing requires an ImmutableContextResolver"
            )
        reference = RunContextRef(canonical_context_sha256(run_context))
        if resolver.resolve_run(reference) != run_context:
            raise ZonalRedispatchInputError("Run context is not bound")
        if resolver.resolve_module("balancing") is not self:
            raise ZonalRedispatchInputError(
                "Zonal balancing is not the exact bound module instance"
            )
        if run_context.network_pack is None:
            raise ZonalRedispatchInputError("Run context has no zonal network pack")
        try:
            network = ZonalNetworkPack.from_dict(run_context.network_pack)
        except (TypeError, ValueError) as exc:
            raise ZonalRedispatchInputError(f"Invalid bound zonal network pack: {exc}") from exc
        demand_mode = str(
            run_context.market_configuration.get("zonal_demand_mode") or ""
        )
        if demand_mode not in SUPPORTED_ZONAL_DEMAND_MODES:
            raise ZonalRedispatchInputError(
                "Run context has no supported zonal demand mode"
            )
        self._resolver = resolver
        self._run_context = run_context
        self._year_context = None
        self._run_context_ref = reference
        self._year_context_ref = None
        self._annual_metadata = None
        self._network_pack = network
        self._zonal_demand_mode = demand_mode
        self._period_index_by_id = {
            str(period_id): index
            for index, period_id in enumerate(network.zonal_demand.period_ids)
        }

    def bind_resume_run_context(self, run_context_sha256: str) -> None:
        """Use an authorized historical ledger lineage with the current runtime."""

        if self._run_context is None or self._resolver is None:
            raise ZonalRedispatchInputError(
                "Zonal balancing must be configured before resume lineage"
            )
        self._run_context_ref = RunContextRef(run_context_sha256)

    def start_year(self, year_context: YearContext) -> None:
        if self._resolver is None or self._run_context_ref is None:
            raise ZonalRedispatchInputError(
                "Zonal balancing must be configured before start_year"
            )
        if year_context.run_context_sha256 != self._run_context_ref.sha256:
            raise ZonalRedispatchInputError(
                "Year context does not reference the bound run context"
            )
        if self._run_context is None or year_context.run_id != self._run_context.run_id:
            raise ZonalRedispatchInputError(
                "Year context run does not match the bound run context"
            )
        reference = YearContextRef(
            year_context.year, canonical_context_sha256(year_context)
        )
        if self._resolver.resolve_year(reference) != year_context:
            raise ZonalRedispatchInputError("Year context is not bound")
        annual = year_context.operating_state
        for key in (
            "asset_zone_id_by_asset",
            "resource_class_by_asset",
            "resource_cost_gbp_per_mwh_by_asset",
            "storage",
        ):
            if not isinstance(annual.get(key), Mapping):
                raise ZonalRedispatchInputError(
                    f"Year context lacks annual zonal metadata: {key}"
                )
        self._year_context = year_context
        self._year_context_ref = reference
        self._annual_metadata = annual
        self._consumed_input_sha256_sequence = []

    @staticmethod
    def _environment() -> dict[str, object]:
        try:
            import scipy
            scipy_version: str | None = scipy.__version__
        except ModuleNotFoundError:
            scipy_version = None
        return {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy_version,
            "platform": platform.platform(),
        }

    def _failure(
        self,
        model_input: BalancingInput,
        error: Exception,
        *,
        stage: str,
    ) -> None:
        if self._evidence_root is None:
            return
        if self._run_context is None or self._year_context is None:
            raise ZonalRedispatchInputError(
                "Failure evidence requires bound run and year contexts"
            )
        diagnostics = dict(getattr(error, "diagnostics", {}) or {})
        try:
            stack: Mapping[str, object] = solver_stack_identity().to_dict()
        except ZonalSolverContractError as stack_error:
            stack = {
                "error_code": stack_error.code,
                "error": str(stack_error),
            }
        residuals = {
            str(name): float(value)
            for name, value in diagnostics.items()
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and ("residual" in str(name) or "violation" in str(name))
        }
        solver = {
            "formulation_id": FORMULATION_ID,
            "solver_contract": self._solver_settings.to_dict(),
            "solver_stack": dict(stack),
            "method": self._solver_settings.method,
            "completed_phases": diagnostics.get("completed_phase_optima", []),
            "diagnostics": diagnostics,
            "environment": self._environment(),
        }
        write_first_failure_bundle(
            FailureEvidenceRequest(
                run_context=self._run_context,
                year_context=self._year_context,
                period_input=model_input,
                stage=stage,
                error=error,
                solver=solver,
                residuals=residuals,
            ),
            self._evidence_root / "market" / "failures" / "first-failure",
        )

    def clear(self, model_input: BalancingInput) -> BalancingResult:
        if (
            self._network_pack is None
            or self._run_context is None
            or self._year_context is None
            or self._run_context_ref is None
            or self._year_context_ref is None
            or self._annual_metadata is None
        ):
            raise ZonalRedispatchInputError("Zonal redispatch contexts are not bound")
        if self._run_context.run_id != model_input.run_id:
            raise ZonalRedispatchInputError(
                "Balancing input run does not match the bound run context"
            )
        if self._year_context.run_id != model_input.run_id:
            raise ZonalRedispatchInputError(
                "Balancing input run does not match the bound year context"
            )
        if (
            self._year_context.year != model_input.year
            or self._year_context_ref.year != model_input.year
        ):
            raise ZonalRedispatchInputError(
                "Balancing input year does not match the bound year context"
            )
        input_sha256 = contract_sha256(model_input)
        if input_sha256 in self._consumed_input_sha256:
            raise ZonalRedispatchInputError("This balancing input has already been balanced")
        stage = "build"
        try:
            try:
                network_period_index = self._period_index_by_id[model_input.period_id]
            except KeyError as exc:
                raise ZonalRedispatchInputError(
                    "Balancing period is absent from the network-pack clock"
                ) from exc
            problem = build_single_period_problem(
                model_input,
                network_pack=self._network_pack,
                run_context_ref=self._run_context_ref,
                year_context_ref=self._year_context_ref,
                annual_metadata=self._annual_metadata,
                demand_mode=self._zonal_demand_mode,
                network_period_index=network_period_index,
            )
            stage = "lexicographic_solve"
            solution = solve_lexicographic(problem, self._solver_settings)
            if "bound_canonicalization" not in solution.diagnostics:
                stage = "solution_bound_canonicalization"
                solution = _canonicalize_solution_bounds(problem, solution)
            stage = "validation"
            validation = validate_solution(problem, solution)
        except (ZonalRedispatchInputError, ZonalRedispatchSolveError) as exc:
            self._failure(model_input, exc, stage=stage)
            raise
        except Exception as exc:
            wrapped = ZonalRedispatchSolveError(
                f"Unexpected zonal redispatch failure: {exc}",
                {"phase": stage, "status": "unexpected_failure"},
            )
            self._failure(model_input, wrapped, stage=stage)
            raise wrapped from exc

        values = solution.values
        accepted: list[AcceptedAdjustment] = []
        cashflow_terms: defaultdict[str, list[float]] = defaultdict(list)
        curtailment_terms: defaultdict[str, list[float]] = defaultdict(list)
        dispatch_adjustment_terms: defaultdict[str, list[float]] = defaultdict(list)
        bid_by_id = {bid.bid_id: bid for bid in problem.bids}
        for bid_id in sorted(problem.bid_index):
            magnitude = float(values[problem.bid_index[bid_id]])
            if magnitude <= TOLERANCE:
                continue
            bid = bid_by_id[bid_id]
            delta = magnitude if bid.direction == "up" else -magnitude
            dispatch_adjustment_terms[bid.asset_id].append(delta)
            cashflow = delta * bid.price_gbp_per_mwh
            accepted.append(AcceptedAdjustment(
                bid.bid_id,
                bid.agent_id,
                bid.asset_id,
                bid.zone_id,
                delta,
                bid.price_gbp_per_mwh,
                cashflow,
                f"zonal_redispatch_{bid.direction}",
                extensions={
                    "network_effect_id": bid.network_effect_id,
                    "resource_class": str(bid.provenance.get("resource_class") or "other"),
                },
            ))
            cashflow_terms[bid.agent_id].append(cashflow)
            if bid.direction == "down":
                curtailment_class = str(bid.provenance.get("curtailment_class") or "")
                if curtailment_class:
                    curtailment_terms[curtailment_class].append(magnitude)

        dispatch_assets = set(problem.ahead.schedule_mwh_by_asset) | set(
            dispatch_adjustment_terms
        )
        final_dispatch = {
            asset: math.fsum((
                float(problem.ahead.schedule_mwh_by_asset.get(asset, 0.0)),
                *dispatch_adjustment_terms.get(asset, ()),
            ))
            for asset in sorted(dispatch_assets)
        }
        cashflows = {
            agent: math.fsum(cashflow_terms[agent])
            for agent in sorted(cashflow_terms)
        }
        curtailment = {
            resource_class: math.fsum(curtailment_terms[resource_class])
            for resource_class in sorted(curtailment_terms)
        }

        final_soc: dict[str, float] = {}
        storage_dispatch: dict[str, dict[str, float]] = {}
        for asset, specification in sorted(problem.storage.items()):
            discharge = float(values[problem.storage_discharge_index[asset]])
            charge = float(values[problem.storage_charge_index[asset]])
            net_injection = math.fsum((discharge, -charge))
            final_dispatch[asset] = net_injection
            final_soc[asset] = math.fsum((
                float(model_input.initial_soc_mwh_by_asset[asset]),
                -discharge / float(specification["discharge_efficiency"]),
                charge * float(specification["charge_efficiency"]),
            ))
            if abs(final_soc[asset]) <= TOLERANCE:
                final_soc[asset] = 0.0
            storage_dispatch[asset] = {
                "charge_mwh": charge,
                "discharge_mwh": discharge,
                "net_injection_mwh": net_injection,
            }
        final_dispatch = {
            asset: final_dispatch[asset] for asset in sorted(final_dispatch)
        }

        # |shed| <= TOLERANCE is LP noise, mapped to exactly zero like the
        # SOC above (P0-8 S6); v4 already fixes it at zero when the primary
        # sheds nothing.
        load_shedding = {
            zone: (0.0 if abs(float(values[index])) <= TOLERANCE else float(values[index]))
            for zone, index in sorted(problem.shedding_index.items())
        }
        blackout = math.fsum(
            load_shedding[zone] for zone in sorted(load_shedding)
        )
        corridor_flow = {
            corridor: float(values[index])
            for corridor, index in sorted(problem.flow_index.items())
        }
        boundary_transfer = {
            boundary.boundary_id: math.fsum(
                member.coefficient * corridor_flow[member.corridor_id]
                for member in sorted(
                    boundary.members,
                    key=lambda item: (item.corridor_id, item.coefficient),
                )
            )
            for boundary in sorted(
                problem.network_pack.cutsets, key=lambda item: item.boundary_id
            )
        }

        resource_cost_terms: defaultdict[str, list[float]] = defaultdict(list)
        fallback_cost = {
            bid.asset_id: bid.physical_cost_gbp_per_mwh for bid in problem.bids
        }
        for asset in sorted(final_dispatch):
            dispatch = final_dispatch[asset]
            if dispatch <= 0:
                continue
            resource_class = problem.resource_class_by_asset.get(asset, "other")
            unit_cost = problem.resource_cost_gbp_per_mwh_by_asset.get(
                asset, fallback_cost.get(asset, 0.0)
            )
            resource_cost_terms[resource_class].append(dispatch * unit_cost)
        if blackout > 0:
            resource_cost_terms["load_shedding"].append(
                blackout * model_input.voll_gbp_per_mwh
            )
        resource_costs = {
            resource_class: math.fsum(resource_cost_terms[resource_class])
            for resource_class in sorted(resource_cost_terms)
        }
        global_residual = math.fsum((
            *(final_dispatch[asset] for asset in sorted(final_dispatch)),
            blackout,
            -model_input.real_demand_mwh,
        ))
        if abs(global_residual) > 1e-7:
            error = ZonalRedispatchSolveError(
                f"Zonal redispatch global energy residual is {global_residual} MWh"
            )
            self._failure(model_input, error, stage="result_assembly")
            raise error
        result = BalancingResult(
            run_id=model_input.run_id,
            year=model_input.year,
            period=model_input.period,
            period_id=model_input.period_id,
            ahead_result_sha256=model_input.ahead_result_sha256,
            source_input_sha256=input_sha256,
            accepted_adjustments=tuple(accepted),
            final_dispatch_mwh_by_asset=final_dispatch,
            final_soc_mwh_by_asset=final_soc,
            curtailment_mwh_by_class=curtailment,
            blackout_mwh=blackout,
            settlement_cashflow_gbp_by_agent=cashflows,
            resource_cost_gbp_by_class=resource_costs,
            energy_balance_residual_mwh=global_residual,
            artifacts=(),
            extensions={
                "method": FORMULATION_ID,
                "network_semantics": "lossless_computational_transport_with_etys_cutsets",
                "network_pack_id": problem.network_pack.network_pack_id,
                "network_pack_scientific_sha256": problem.network_pack.scientific_sha256,
                "corridor_flow_mwh_by_id": corridor_flow,
                "boundary_transfer_mwh_by_id": boundary_transfer,
                "load_shedding_mwh_by_zone": load_shedding,
                "storage_dispatch_mwh_by_asset": storage_dispatch,
                "primary_objective_gbp": solution.primary_objective_gbp,
                "secondary_objective_mwh": solution.secondary_objective_mwh,
                "physical_tie_objective": solution.physical_tie_objective,
                "stable_tie_objective": solution.stable_tie_objective,
                "solver": dict(solution.diagnostics),
                "network_solver_diagnostics": [
                    _objective_diagnostic_payload(row)
                    for row in solution.network_solver_diagnostics
                ],
                "validation": dict(validation),
                "automatic_copperplate_fallback": False,
            },
        )
        self._consumed_input_sha256.add(input_sha256)
        self._consumed_input_sha256_sequence.append(
            # Runtime checkpoints use the PSM year-local period, while the
            # network clock may span several years and remains a data index.
            (model_input.period, input_sha256)
        )
        return result
