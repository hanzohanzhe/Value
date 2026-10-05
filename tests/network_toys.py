"""Shared small network fixtures for the P0-8 network and zonal tests.

Every builder returns plain, self-contained declarations so the production
solver and the independent CBC oracles read the same numbers:

* ``two_zone_declaration`` / ``three_zone_remote_upward_declaration`` and
  ``gb_chain_declaration`` return ``value.zonal-redispatch-domain/v1`` oracle
  declarations (bind them to production with
  ``gridform_validation.zonal_case_generator.bind_production_input``);
* ``dc_case`` builds a nodal DC input whose asset map may split an asset
  across buses with explicit shares;
* ``eleven_zone_topology`` returns a topology-only copy of the public 11-zone
  CP30 overlay (zones, corridors, raw cut sets including their declared
  partitions).
"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence

from gridform_core.network_contracts import (
    AssetBusMapping,
    NetworkBranch,
    NetworkBus,
    NetworkPSMInput,
    NetworkTopology,
)
from gridform_core.staged_market_contracts import (
    AheadMarketResult,
    BalancingInput,
    FlexibilityBid,
    contract_sha256,
)
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
    StorageDispatchResource,
)
from gridform_core.zonal_contracts import (
    CutsetMember,
    ETYSBoundary,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZonalDemand,
    ZonalNetworkPack,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "network_toys"
VOLL_GBP_PER_MWH = 17_000.0


# ---------------------------------------------------------------- zonal ----

def zonal_bid(
    bid_id: str,
    asset_id: str,
    zone_id: str,
    direction: str,
    available_mwh: float,
    price: float,
    *,
    period_id: str = "p0",
    period_hours: float = 1.0,
    baseline_mwh: float = 0.0,
    resource_class: str = "thermal",
) -> FlexibilityBid:
    return FlexibilityBid(
        bid_id=bid_id,
        agent_id=asset_id,
        asset_id=asset_id,
        technology=resource_class,
        zone_id=zone_id,
        period_id=period_id,
        direction=direction,
        available_mw=available_mwh / period_hours,
        price_gbp_per_mwh=price,
        baseline_mw=baseline_mwh / period_hours,
        physical_cost_gbp_per_mwh=price,
        network_effect_id=f"{zone_id}:injection",
        provenance={"resource_class": resource_class},
        extensions={"available_mwh": available_mwh},
    )


def zonal_pack(
    demand: Mapping[str, float],
    *,
    corridors: Sequence[TransportCorridor] = (),
    cutsets: Sequence[ETYSBoundary] = (),
    period_id: str = "p0",
    pack_id: str = "network-toys",
) -> ZonalNetworkPack:
    pack = ZonalNetworkPack(
        network_pack_id=pack_id,
        scientific_sha256="",
        zones=tuple(
            NetworkZone(zone, zone, "fixture DSO", "England") for zone in demand
        ),
        corridors=tuple(corridors),
        cutsets=tuple(cutsets),
        asset_mappings=(),
        zonal_demand=ZonalDemand(
            (period_id,),
            {zone: (float(value),) for zone, value in demand.items()},
            (sum(float(value) for value in demand.values()),),
        ),
        rating_profiles=(),
        interconnector_landings=(),
        spatial_audit=SpatialAudit((), {}, {}, 1e-9),
        loss_capability_absent_reason="lossless_v1",
        provenance={"fixture": "tests/network_toys.py"},
    )
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


def zonal_declaration(
    demand: Mapping[str, float],
    schedule: Mapping[str, float],
    zones: Mapping[str, str],
    bids: Sequence[FlexibilityBid],
    *,
    pack: ZonalNetworkPack | None = None,
    availability_mwh: Mapping[str, float] | None = None,
    classes: Mapping[str, str] | None = None,
    costs: Mapping[str, float] | None = None,
    storage: Mapping[str, Mapping[str, object]] | None = None,
    opening_soc: Mapping[str, float] | None = None,
    corridor_limits: Mapping[str, Mapping[str, float]] | None = None,
    period_id: str = "p0",
    period_hours: float = 1.0,
    voll: float = VOLL_GBP_PER_MWH,
    run_id: str = "network-toys",
) -> dict[str, object]:
    """Return a self-contained v1 oracle declaration for one period."""

    pack = pack or zonal_pack(demand, period_id=period_id)
    ahead = AheadMarketResult(
        run_id=run_id,
        year=2025,
        period=0,
        period_id=period_id,
        information_scope="forecast_only",
        schedule_mwh_by_asset=dict(schedule),
        clearing_price_gbp_per_mwh=50.0,
        accepted_volume_mwh=sum(max(value, 0.0) for value in schedule.values()),
        settlement_mwh_by_asset=dict(schedule),
        storage_scheduled_action_mwh_by_asset={},
        source_input_sha256="a" * 64,
    )
    assets = set(schedule) | {bid.asset_id for bid in bids}
    available = dict(availability_mwh or {
        asset: max(1_000.0, schedule.get(asset, 0.0)) for asset in assets
    })
    model_input = BalancingInput(
        run_id=run_id,
        year=2025,
        period=0,
        period_id=period_id,
        ahead_result_sha256=contract_sha256(ahead),
        real_demand_mwh=sum(float(value) for value in demand.values()),
        realised_availability_mw_by_asset={
            asset: value / period_hours for asset, value in available.items()
        },
        initial_soc_mwh_by_asset=dict(opening_soc or {}),
        bids=tuple(bids),
        period_hours=period_hours,
        voll_gbp_per_mwh=voll,
        domain_payload={
            "schema_version": "value.zonal-redispatch-domain/v1",
            "zonal_demand_mode": "network_pack_absolute_demand",
            "ahead_result": ahead.to_dict(),
            "network_pack": pack.to_dict(),
            "real_demand_mwh_by_zone": dict(demand),
            "asset_zone_id_by_asset": dict(zones),
            "resource_class_by_asset": dict(
                classes or {asset: "thermal" for asset in assets}
            ),
            "resource_cost_gbp_per_mwh_by_asset": dict(
                costs or {asset: 0.0 for asset in assets}
            ),
            "storage": {key: dict(value) for key, value in (storage or {}).items()},
            "interconnector_envelope_mwh_by_asset": {},
            "corridor_limits_mw_by_id": {
                key: dict(value) for key, value in (corridor_limits or {}).items()
            },
        },
    )
    return model_input.to_dict()


def two_zone_declaration(
    *,
    forward_limit_mw: float | None = None,
    voll: float = VOLL_GBP_PER_MWH,
) -> dict[str, object]:
    """North has cheap upward flexibility, south has the demand."""

    demand = {"north": 0.0, "south": 10.0}
    corridor = TransportCorridor("north-south", "north", "south", "from_to_positive")
    cutsets = ()
    if forward_limit_mw is not None:
        cutsets = (ETYSBoundary(
            "B_TEST", "Fixture boundary", (CutsetMember("north-south", 1),),
            forward_limit_mw, forward_limit_mw,
            reverse_limit_method="assumed_symmetric_from_forward",
        ),)
    return zonal_declaration(
        demand,
        {"cheap": 0.0, "local": 0.0},
        {"cheap": "north", "local": "south"},
        (
            zonal_bid("cheap-up", "cheap", "north", "up", 10.0, 10.0),
            zonal_bid("local-up", "local", "south", "up", 10.0, 50.0),
        ),
        pack=zonal_pack(demand, corridors=(corridor,), cutsets=cutsets),
        voll=voll,
    )


def three_zone_remote_upward_declaration(
    *, voll: float = VOLL_GBP_PER_MWH
) -> dict[str, object]:
    """Upward energy must travel two uncongested corridors to the demand."""

    demand = {"north": 0.0, "mid": 0.0, "south": 2.0}
    corridors = (
        TransportCorridor("north-mid", "north", "mid", "from_to_positive"),
        TransportCorridor("mid-south", "mid", "south", "from_to_positive"),
    )
    return zonal_declaration(
        demand,
        {"remote": 0.0},
        {"remote": "north"},
        (zonal_bid("remote-up", "remote", "north", "up", 5.0, 66.5),),
        pack=zonal_pack(demand, corridors=corridors),
        voll=voll,
    )


def scarce_two_zone_declaration(*, voll: float = VOLL_GBP_PER_MWH) -> dict[str, object]:
    """Ten MWh of demand behind a 1 MWh boundary with no local flexibility."""

    demand = {"north": 0.0, "south": 10.0}
    corridor = TransportCorridor("north-south", "north", "south", "from_to_positive")
    boundary = ETYSBoundary(
        "B_TEST", "Fixture boundary", (CutsetMember("north-south", 1),), 1.0, 1.0,
        reverse_limit_method="assumed_symmetric_from_forward",
    )
    return zonal_declaration(
        demand,
        {"cheap": 0.0},
        {"cheap": "north"},
        (zonal_bid("cheap-up", "cheap", "north", "up", 10.0, 10.0),),
        pack=zonal_pack(demand, corridors=(corridor,), cutsets=(boundary,)),
        voll=voll,
    )


GB_CHAIN_ZONES = tuple(f"Z{index:02d}" for index in range(1, 24))
GB_CHAIN_BOUNDARY_AFTER = (4, 8, 12, 16, 20)


def gb_chain_declaration(seed: int, *, scarce: bool) -> dict[str, object]:
    """A GB-scale 23-zone north-to-south chain for one half-hour.

    Wind in the north is scheduled ahead on a copper plate; five single
    member ETYS-style boundaries bind, so the north is turned down and
    southern thermal plant is turned up.  ``scarce=True`` adds a realised
    southern demand excess larger than all southern upward headroom, so the
    primary solution sheds load (GB-scale scarcity).
    """

    rng = random.Random(10_000 + seed)
    period_hours = 0.5
    zones = GB_CHAIN_ZONES
    weights = [0.25 + 0.75 * index / (len(zones) - 1) for index in range(len(zones))]
    weights = [value * (0.9 + 0.2 * rng.random()) for value in weights]
    national_forecast = round(14_000.0 + 3_000.0 * rng.random(), 3)
    total_weight = sum(weights)
    forecast = {
        zone: round(national_forecast * weight / total_weight, 6)
        for zone, weight in zip(zones, weights)
    }
    demand = dict(forecast)
    if scarce:
        for zone in zones[14:]:
            demand[zone] = round(demand[zone] * (2.8 + 0.4 * rng.random()), 6)
    corridors = tuple(
        TransportCorridor(f"C{zones[index]}-{zones[index + 1]}", zones[index], zones[index + 1], "from_to_positive")
        for index in range(len(zones) - 1)
    )
    cutsets = tuple(
        ETYSBoundary(
            f"B_GB_{after:02d}",
            f"Chain boundary after {zones[after - 1]}",
            (CutsetMember(corridors[after - 1].corridor_id, 1),),
            round(6_000.0 + 5_000.0 * rng.random(), 3),
            round(6_000.0 + 5_000.0 * rng.random(), 3),
            reverse_limit_method="independent_source",
        )
        for after in GB_CHAIN_BOUNDARY_AFTER
    )
    pack = zonal_pack(
        demand, corridors=corridors, cutsets=cutsets, pack_id="gb-chain-23"
    )

    schedule: dict[str, float] = {}
    asset_zone: dict[str, str] = {}
    classes: dict[str, str] = {}
    costs: dict[str, float] = {}
    available: dict[str, float] = {}
    bids: list[FlexibilityBid] = []

    def add(asset: str, zone: str, resource_class: str, scheduled: float,
            headroom: float, up_price: float | None, down_price: float | None,
            cost: float) -> None:
        schedule[asset] = round(scheduled, 6)
        asset_zone[asset] = zone
        classes[asset] = resource_class
        costs[asset] = cost
        available[asset] = round(scheduled + headroom, 6)
        if up_price is not None and headroom > 0:
            bids.append(zonal_bid(
                f"{asset}-up", asset, zone, "up", round(headroom, 6), up_price,
                period_id="p0", period_hours=period_hours,
                baseline_mwh=schedule[asset], resource_class=resource_class,
            ))
        if down_price is not None and scheduled > 0:
            bids.append(zonal_bid(
                f"{asset}-down", asset, zone, "down", schedule[asset], down_price,
                period_id="p0", period_hours=period_hours,
                baseline_mwh=schedule[asset], resource_class=resource_class,
            ))

    # Northern wind covers more than half of national demand ahead.
    wind_total = national_forecast * (0.55 + 0.1 * rng.random())
    wind_zones = zones[:8]
    for index, zone in enumerate(wind_zones):
        share = (1.0 + rng.random()) / (1.5 * len(wind_zones))
        add(f"wind-{zone}", zone, "vre", wind_total * share, 0.0, None,
            round(-20.0 - 60.0 * rng.random(), 2), 0.0)
    for zone in (zones[10], zones[14], zones[19]):
        add(f"nuclear-{zone}", zone, "nuclear", 600.0, 0.0, None,
            round(-5.0 - 10.0 * rng.random(), 2), 10.0)
    scheduled_so_far = sum(schedule.values())
    remaining = national_forecast - scheduled_so_far
    ccgt_zones = zones[8:]
    for index, zone in enumerate(ccgt_zones):
        scheduled = max(remaining, 0.0) / len(ccgt_zones)
        price = round(75.0 + 45.0 * rng.random(), 2)
        add(f"ccgt-{zone}", zone, "thermal", scheduled,
            round(450.0 + 300.0 * rng.random(), 3), price, round(price - 5.0, 2), price)
    for zone in zones[12:]:
        price = round(150.0 + 120.0 * rng.random(), 2)
        add(f"ocgt-{zone}", zone, "thermal", 0.0,
            round(40.0 + 80.0 * rng.random(), 3), price, None, price)
    for zone in zones[18:]:
        price = round(300.0 + 300.0 * rng.random(), 2)
        add(f"dsr-{zone}", zone, "dsr", 0.0,
            round(10.0 + 30.0 * rng.random(), 3), price, None, price)
    # Rebalance the ahead schedule exactly to the national forecast.
    imbalance = national_forecast - sum(schedule.values())
    last = f"ccgt-{zones[-1]}"
    schedule[last] = round(schedule[last] + imbalance, 6)
    available[last] = round(available[last] + imbalance, 6)
    bids = [
        replace(bid, baseline_mw=schedule[bid.asset_id] / period_hours)
        if bid.asset_id == last else bid
        for bid in bids
    ]
    bids = [
        replace(
            bid,
            available_mw=schedule[last] / period_hours,
            extensions={"available_mwh": schedule[last]},
        )
        if bid.bid_id == f"{last}-down" else bid
        for bid in bids
    ]
    return zonal_declaration(
        demand,
        schedule,
        asset_zone,
        tuple(bids),
        pack=pack,
        availability_mwh=available,
        classes=classes,
        costs=costs,
        period_hours=period_hours,
        run_id=f"gb-chain-{'scarce' if scarce else 'normal'}-{seed}",
    )


# ---------------------------------------------------------------- nodal ----

def dc_case(
    demand_mwh_by_bus: Mapping[str, Sequence[float]],
    resources: Sequence[Mapping[str, object]],
    *,
    branches: Sequence[Mapping[str, object]] = (),
    storage: Sequence[Mapping[str, object]] = (),
    reference_bus: str | None = None,
    period_hours: float = 1.0,
    voll: float = 10_000.0,
    terminal_soc_rule: str = "cyclic",
) -> tuple[NetworkPSMInput, PSMInput]:
    """Build a nodal DC input; each asset carries ``buses=[(bus, share), ...]``."""

    buses = tuple(demand_mwh_by_bus)
    reference = reference_bus or buses[0]
    periods = len(next(iter(demand_mwh_by_bus.values())))
    chronology = ChronologicalPSMData(
        tuple(f"p{period}" for period in range(periods)),
        tuple(
            sum(float(values[period]) for values in demand_mwh_by_bus.values())
            for period in range(periods)
        ),
        tuple(
            DispatchResource(
                str(item["asset_id"]),
                str(item.get("technology", item.get("resource_type", "thermal"))),
                str(item.get("resource_type", "thermal")),
                float(item["capacity_mw"]),
                float(item.get("cost", 0.0)),
                tuple(float(value) for value in item.get("availability", (1.0,))),
            )
            for item in resources
        ),
        tuple(
            StorageDispatchResource(
                str(item["asset_id"]),
                str(item.get("technology", "battery")),
                float(item["power_mw"]),
                float(item["power_mw"]),
                float(item["energy_mwh"]),
                float(item.get("efficiency", 0.9)),
                float(item.get("efficiency", 0.9)),
                float(item.get("initial_soc_mwh", 0.0)),
                float(item.get("degradation_cost", 0.0)),
            )
            for item in storage
        ),
        voll,
        terminal_soc_rule=terminal_soc_rule,
    )
    mappings: list[AssetBusMapping] = []
    for item in resources:
        asset_class = "boundary_import" if item.get("resource_type") == "import" else "generator"
        for bus, share in item["buses"]:  # type: ignore[union-attr]
            mappings.append(AssetBusMapping(str(item["asset_id"]), str(bus), asset_class, float(share)))
    for item in storage:
        for bus, share in item["buses"]:  # type: ignore[union-attr]
            mappings.append(AssetBusMapping(str(item["asset_id"]), str(bus), "storage", float(share)))
    topology = NetworkTopology(
        tuple(
            NetworkBus(bus, 400.0, bus, bus == reference, bus == reference)
            for bus in buses
        ),
        tuple(
            NetworkBranch(
                str(item["branch_id"]), str(item["from_bus"]), str(item["to_bus"]),
                "ac_line", True, float(item["rating_mw"]),
                reactance_pu=float(item.get("reactance_pu", 0.1)),
            )
            for item in branches
        ),
        tuple(mappings),
        100.0,
    )
    network = NetworkPSMInput(
        "network-toys", 2025, period_hours, chronology, topology,
        {bus: tuple(float(value) for value in values) for bus, values in demand_mwh_by_bus.items()},
        "domain.network.dc", "perfect_foresight",
    )
    wrapped = PSMInput(
        network.run_id, network.year, "network-toys", OperatingState(network.year, (), ()),
        period_hours, {}, chronology=chronology,
        extensions={"network_input": network.to_dict()},
    )
    return network, wrapped


def three_bus_dc_case(*, split: bool, swap_rows: bool = False):
    """Wind split 50/50 between A and B (or two explicit units), AB rated 30 MW."""

    if split:
        wind = [{
            "asset_id": "wind", "resource_type": "vre", "technology": "wind",
            "capacity_mw": 200.0, "cost": 0.0,
            "buses": [("B", 0.5), ("A", 0.5)] if swap_rows else [("A", 0.5), ("B", 0.5)],
        }]
    else:
        wind = [
            {"asset_id": "wind-a", "resource_type": "vre", "technology": "wind",
             "capacity_mw": 100.0, "cost": 0.0, "buses": [("A", 1.0)]},
            {"asset_id": "wind-b", "resource_type": "vre", "technology": "wind",
             "capacity_mw": 100.0, "cost": 0.0, "buses": [("B", 1.0)]},
        ]
    return dc_case(
        {"A": [100.0], "B": [100.0], "C": [0.0]},
        wind + [{"asset_id": "gas", "capacity_mw": 300.0, "cost": 80.0, "buses": [("C", 1.0)]}],
        branches=[
            {"branch_id": "AB", "from_bus": "A", "to_bus": "B", "rating_mw": 30.0},
            {"branch_id": "BC", "from_bus": "B", "to_bus": "C", "rating_mw": 500.0},
        ],
    )


# ---------------------------------------------------------------- 11-zone --

def eleven_zone_topology() -> dict[str, object]:
    """Raw zones, corridors and cut sets (with declared partitions) of 11-zone."""

    return json.loads(
        (FIXTURES / "eleven-zone-topology.json").read_text(encoding="utf-8")
    )
