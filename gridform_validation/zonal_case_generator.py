"""Deterministic independent-validation cases for VALUE zonal redispatch."""

from __future__ import annotations

import random
from dataclasses import replace

from gridform_core.staged_market_contracts import (
    AheadMarketResult,
    BalancingInput,
    FlexibilityBid,
    contract_sha256,
)
from gridform_core.zonal_contracts import (
    BoundaryRatingProfile,
    CutsetMember,
    ETYSBoundary,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZonalDemand,
    ZonalNetworkPack,
)
from gridform_core.zonal_redispatch import ZonalRedispatchBalancing


def _bid(
    bid_id: str,
    asset_id: str,
    zone_id: str,
    direction: str,
    available_mwh: float,
    price: float,
    *,
    baseline_mwh: float = 0.0,
    resource_class: str = "thermal",
    network_effect_id: str | None = None,
) -> FlexibilityBid:
    return FlexibilityBid(
        bid_id=bid_id,
        agent_id=asset_id,
        asset_id=asset_id,
        technology=resource_class,
        zone_id=zone_id,
        period_id="p0",
        direction=direction,
        available_mw=available_mwh,
        price_gbp_per_mwh=price,
        baseline_mw=baseline_mwh,
        physical_cost_gbp_per_mwh=price,
        network_effect_id=network_effect_id or f"{zone_id}:injection",
        provenance={"resource_class": resource_class},
        extensions={"available_mwh": available_mwh},
    )


def _pack(
    demand: dict[str, float],
    *,
    corridors: tuple[TransportCorridor, ...] = (),
    cutsets: tuple[ETYSBoundary, ...] = (),
    profiles: tuple[BoundaryRatingProfile, ...] = (),
) -> ZonalNetworkPack:
    pack = ZonalNetworkPack(
        network_pack_id="prompt103-independent-fixture",
        scientific_sha256="",
        zones=tuple(
            NetworkZone(zone, zone.replace("-", " ").title(), "fixture DSO", "England")
            for zone in demand
        ),
        corridors=corridors,
        cutsets=cutsets,
        asset_mappings=(),
        zonal_demand=ZonalDemand(
            ("p0",),
            {zone: (value,) for zone, value in demand.items()},
            (sum(demand.values()),),
        ),
        rating_profiles=profiles,
        interconnector_landings=(),
        spatial_audit=SpatialAudit((), {}, {}, 1e-9),
        loss_capability_absent_reason="lossless_v1",
        provenance={"fixture": "Prompt 103 independent validation"},
    )
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


def _two_zone_pack(
    demand: dict[str, float],
    forward: float,
    reverse: float,
) -> ZonalNetworkPack:
    corridor = TransportCorridor(
        "north-south", "north", "south", "from_to_positive"
    )
    boundary = ETYSBoundary(
        "B_TEST",
        "Hand-solvable boundary",
        (CutsetMember("north-south", 1),),
        forward,
        reverse,
        reverse_limit_method="independent_source",
    )
    return _pack(demand, corridors=(corridor,), cutsets=(boundary,))


def _input(
    demand: dict[str, float],
    schedule: dict[str, float],
    zones: dict[str, str],
    bids: tuple[FlexibilityBid, ...],
    *,
    pack: ZonalNetworkPack | None = None,
    availability: dict[str, float] | None = None,
    classes: dict[str, str] | None = None,
    storage: dict[str, dict[str, object]] | None = None,
    opening_soc: dict[str, float] | None = None,
    envelopes: dict[str, dict[str, float]] | None = None,
    corridor_limits: dict[str, dict[str, float]] | None = None,
    run_id: str = "prompt103",
) -> dict[str, object]:
    pack = pack or _pack(demand)
    ahead = AheadMarketResult(
        run_id=run_id,
        year=2025,
        period=0,
        period_id="p0",
        information_scope="forecast_only",
        schedule_mwh_by_asset=schedule,
        clearing_price_gbp_per_mwh=50.0,
        accepted_volume_mwh=sum(max(value, 0.0) for value in schedule.values()),
        settlement_mwh_by_asset=schedule,
        storage_scheduled_action_mwh_by_asset={},
        source_input_sha256="a" * 64,
    )
    assets = set(schedule) | {bid.asset_id for bid in bids}
    resource_classes = classes or {asset: "thermal" for asset in assets}
    available = availability or {
        asset: max(1_000.0, max(schedule.get(asset, 0.0), 0.0)) for asset in assets
    }
    model_input = BalancingInput(
        run_id=run_id,
        year=2025,
        period=0,
        period_id="p0",
        ahead_result_sha256=contract_sha256(ahead),
        real_demand_mwh=sum(demand.values()),
        realised_availability_mw_by_asset=available,
        initial_soc_mwh_by_asset=opening_soc or {},
        bids=bids,
        period_hours=1.0,
        voll_gbp_per_mwh=17_000.0,
        domain_payload={
            "schema_version": "value.zonal-redispatch-domain/v1",
            "zonal_demand_mode": "network_pack_absolute_demand",
            "ahead_result": ahead.to_dict(),
            "network_pack": pack.to_dict(),
            "real_demand_mwh_by_zone": demand,
            "asset_zone_id_by_asset": zones,
            "resource_class_by_asset": resource_classes,
            "resource_cost_gbp_per_mwh_by_asset": {
                asset: 0.0 for asset in assets
            },
            "storage": storage or {},
            "interconnector_envelope_mwh_by_asset": envelopes or {},
            "corridor_limits_mw_by_id": corridor_limits or {},
        },
    )
    return model_input.to_dict()


def analytical_cases() -> dict[str, dict[str, object]]:
    """Return small cases whose expected direction and binding limits are evident."""

    unconstrained_demand = {"north": 0.0, "south": 10.0}
    unconstrained = _input(
        unconstrained_demand,
        {"cheap": 0.0, "local": 0.0},
        {"cheap": "north", "local": "south"},
        (
            _bid("cheap-up", "cheap", "north", "up", 10.0, 10.0),
            _bid("local-up", "local", "south", "up", 10.0, 50.0),
        ),
        pack=_two_zone_pack(unconstrained_demand, 1_000.0, 1_000.0),
    )
    binding = _input(
        unconstrained_demand,
        {"cheap": 10.0, "local": 0.0},
        {"cheap": "north", "local": "south"},
        (
            _bid("cheap-down", "cheap", "north", "down", 10.0, 10.0, baseline_mwh=10.0),
            _bid("local-up", "local", "south", "up", 10.0, 100.0),
        ),
        pack=_two_zone_pack(unconstrained_demand, 4.0, 2.0),
    )
    reverse_demand = {"north": 5.0, "south": 0.0}
    reverse = _input(
        reverse_demand,
        {"south-gen": 5.0, "north-gen": 0.0},
        {"south-gen": "south", "north-gen": "north"},
        (
            _bid("south-down", "south-gen", "south", "down", 5.0, 0.0, baseline_mwh=5.0),
            _bid("north-up", "north-gen", "north", "up", 5.0, 80.0),
        ),
        pack=_two_zone_pack(reverse_demand, 9.0, 3.0),
        corridor_limits={
            "north-south": {"forward_limit_mw": 8.0, "reverse_limit_mw": 2.0}
        },
    )
    signed_import = _input(
        {"gb": 5.0},
        {"import-fr": 2.0},
        {"import-fr": "gb"},
        (_bid("import-up", "import-fr", "gb", "up", 10.0, 30.0, baseline_mwh=2.0, resource_class="import"),),
        classes={"import-fr": "import"},
        envelopes={"import-fr": {"minimum_mwh": -2.0, "maximum_mwh": 5.0}},
    )
    storage_specification = {
        "battery": {
            "charge_power_mw": 4.0,
            "discharge_power_mw": 4.0,
            "energy_capacity_mwh": 5.0,
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.8,
            "bid_contract": "convex_net_power_v1",
        }
    }
    storage = _input(
        {"gb": 3.0},
        {"battery": 0.0},
        {"battery": "gb"},
        (_bid("battery-up", "battery", "gb", "up", 10.0, 20.0, resource_class="storage"),),
        classes={"battery": "storage"},
        storage=storage_specification,
        opening_soc={"battery": 2.0},
    )
    return {
        "unconstrained": unconstrained,
        "binding-forward-cut": binding,
        "binding-reverse-corridor": reverse,
        "signed-import": signed_import,
        "storage-efficiency": storage,
    }


def random_convex_case(seed: int) -> dict[str, object]:
    """Return a reproducible convex three-zone case with overlapping cut sets."""

    rng = random.Random(seed)
    demand = {
        "north": round(2.0 + rng.random() * 2.0, 3),
        "mid": round(4.0 + rng.random() * 2.0, 3),
        "south": round(8.0 + rng.random() * 3.0, 3),
    }
    national = sum(demand.values())
    wind_schedule = 8.0
    import_schedule = 2.0
    mid_schedule = national - wind_schedule - import_schedule
    schedule = {
        "wind-north": wind_schedule,
        "thermal-mid": mid_schedule,
        "thermal-south": 0.0,
        "import-fr": import_schedule,
        "battery": 0.0,
        "dsr": 0.0,
    }
    zones = {
        "wind-north": "north",
        "thermal-mid": "mid",
        "thermal-south": "south",
        "import-fr": "south",
        "battery": "mid",
        "dsr": "south",
    }
    corridors = (
        TransportCorridor("north-mid", "north", "mid", "from_to_positive"),
        TransportCorridor("mid-south", "mid", "south", "from_to_positive"),
        TransportCorridor("north-south", "north", "south", "from_to_positive"),
    )
    profiles = (BoundaryRatingProfile("seasonal", ("p0",), (0.9,)),)
    cutsets = (
        ETYSBoundary(
            "B_NORTH",
            "North export",
            (CutsetMember("north-mid", 1), CutsetMember("north-south", 1)),
            4.0,
            3.0,
            "seasonal",
            "independent_source",
        ),
        ETYSBoundary(
            "B_SOUTH",
            "South import",
            (CutsetMember("mid-south", 1), CutsetMember("north-south", 1)),
            4.0,
            4.0,
            "seasonal",
            "independent_source",
        ),
    )
    pack = _pack(demand, corridors=corridors, cutsets=cutsets, profiles=profiles)
    bids = (
        _bid("wind-down", "wind-north", "north", "down", 8.0, 0.0, baseline_mwh=wind_schedule, resource_class="vre"),
        _bid("mid-up", "thermal-mid", "mid", "up", 5.0, 55.0, baseline_mwh=mid_schedule),
        _bid("mid-down", "thermal-mid", "mid", "down", min(5.0, mid_schedule), 55.0, baseline_mwh=mid_schedule),
        _bid("south-up", "thermal-south", "south", "up", 12.0, 80.0),
        _bid("import-up", "import-fr", "south", "up", 3.0, 65.0, baseline_mwh=import_schedule, resource_class="import"),
        _bid("import-down", "import-fr", "south", "down", 4.0, 25.0, baseline_mwh=import_schedule, resource_class="import"),
        _bid("battery-up", "battery", "mid", "up", 3.0, 45.0, resource_class="storage"),
        _bid("battery-down", "battery", "mid", "down", 3.0, 0.0, resource_class="storage"),
        _bid("dsr-up", "dsr", "south", "up", 2.0, 500.0, resource_class="dsr"),
    )
    storage = {
        "battery": {
            "charge_power_mw": 3.0,
            "discharge_power_mw": 3.0,
            "energy_capacity_mwh": 6.0,
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
            "bid_contract": "convex_net_power_v1",
        }
    }
    return _input(
        demand,
        schedule,
        zones,
        bids,
        pack=pack,
        availability={
            "wind-north": 8.0,
            "thermal-mid": mid_schedule + 5.0,
            "thermal-south": 12.0,
            "import-fr": 5.0,
            "battery": 3.0,
            "dsr": 2.0,
        },
        classes={
            "wind-north": "vre",
            "thermal-mid": "thermal",
            "thermal-south": "thermal",
            "import-fr": "import",
            "battery": "storage",
            "dsr": "dsr",
        },
        storage=storage,
        opening_soc={"battery": round(2.0 + rng.random() * 2.0, 3)},
        envelopes={"import-fr": {"minimum_mwh": -2.0, "maximum_mwh": 5.0}},
        corridor_limits={
            "north-mid": {"forward_limit_mw": 7.0, "reverse_limit_mw": 2.0},
            "mid-south": {"forward_limit_mw": 6.0, "reverse_limit_mw": 3.0},
            "north-south": {"forward_limit_mw": 3.0, "reverse_limit_mw": 1.5},
        },
        run_id=f"prompt103-random-{seed}",
    )


def production_solution(declaration: dict[str, object]) -> dict[str, object]:
    """Normalize the live VALUE result into the oracle comparison schema."""

    model_input = BalancingInput.from_dict(declaration)
    result = ZonalRedispatchBalancing().clear(model_input)
    extensions = dict(result.extensions)
    accepted = {bid.bid_id: 0.0 for bid in model_input.bids}
    signed = {bid.bid_id: 0.0 for bid in model_input.bids}
    for row in result.accepted_adjustments:
        accepted[row.bid_id] = abs(float(row.accepted_delta_mwh))
        signed[row.bid_id] = float(row.accepted_delta_mwh)
    storage_dispatch = {
        str(asset): dict(values)
        for asset, values in dict(extensions.get("storage_dispatch_mwh_by_asset", {})).items()
    }
    return {
        "success": True,
        "status": "optimal",
        "solver": "force-production",
        "primary_objective_gbp": float(extensions["primary_objective_gbp"]),
        "secondary_objective_mwh": float(extensions["secondary_objective_mwh"]),
        "physical_tie_objective": float(extensions["physical_tie_objective"]),
        "stable_tie_objective": float(extensions["stable_tie_objective"]),
        "accepted_mwh_by_bid": accepted,
        "accepted_adjustment_mwh_by_bid": signed,
        "final_dispatch_mwh_by_asset": dict(result.final_dispatch_mwh_by_asset),
        "final_soc_mwh_by_asset": dict(result.final_soc_mwh_by_asset),
        "storage_charge_mwh_by_asset": {
            asset: float(values.get("charge_mwh", 0.0))
            for asset, values in storage_dispatch.items()
        },
        "storage_discharge_mwh_by_asset": {
            asset: float(values.get("discharge_mwh", 0.0))
            for asset, values in storage_dispatch.items()
        },
        "corridor_flow_mwh_by_id": dict(extensions["corridor_flow_mwh_by_id"]),
        "boundary_transfer_mwh_by_id": dict(extensions["boundary_transfer_mwh_by_id"]),
        "load_shedding_mwh_by_zone": dict(extensions["load_shedding_mwh_by_zone"]),
        "blackout_mwh": float(result.blackout_mwh),
    }


def _chronology_declaration(
    *,
    step: int,
    opening_soc_mwh: float,
    seed: int,
) -> dict[str, object]:
    """Create one half-hour declaration using only information for that period."""

    period_id = f"p{step:04d}"
    period_hours = 0.5
    rng = random.Random(seed * 100_003 + step)
    charging_period = step % 4 in {0, 1}
    demand = round((0.75 if charging_period else 2.25) + rng.uniform(-0.08, 0.08), 6)
    wind_schedule = 1.5
    pack = ZonalNetworkPack(
        network_pack_id="prompt103-chronology-fixture",
        scientific_sha256="",
        zones=(NetworkZone("gb", "GB", "fixture DSO", "England"),),
        corridors=(),
        cutsets=(),
        asset_mappings=(),
        zonal_demand=ZonalDemand((period_id,), {"gb": (demand,)}, (demand,)),
        rating_profiles=(),
        interconnector_landings=(),
        spatial_audit=SpatialAudit((), {}, {}, 1e-9),
        loss_capability_absent_reason="lossless_v1",
        provenance={"information_scope": "current_period_only"},
    )
    pack = replace(pack, scientific_sha256=pack.compute_scientific_sha256())
    ahead = AheadMarketResult(
        run_id=f"prompt103-chronology-{seed}",
        year=2025,
        period=step,
        period_id=period_id,
        information_scope="forecast_only",
        schedule_mwh_by_asset={"wind": wind_schedule, "thermal": 0.0, "battery": 0.0},
        clearing_price_gbp_per_mwh=0.0,
        accepted_volume_mwh=wind_schedule,
        settlement_mwh_by_asset={"wind": wind_schedule, "thermal": 0.0, "battery": 0.0},
        storage_scheduled_action_mwh_by_asset={},
        source_input_sha256="b" * 64,
    )

    def bid(
        bid_id: str,
        asset: str,
        direction: str,
        available_mwh: float,
        price: float,
        resource_class: str,
        baseline_mwh: float,
    ) -> FlexibilityBid:
        return FlexibilityBid(
            bid_id=bid_id,
            agent_id=asset,
            asset_id=asset,
            technology=resource_class,
            zone_id="gb",
            period_id=period_id,
            direction=direction,
            available_mw=available_mwh / period_hours,
            price_gbp_per_mwh=price,
            baseline_mw=baseline_mwh / period_hours,
            physical_cost_gbp_per_mwh=price,
            network_effect_id="gb:injection",
            provenance={"resource_class": resource_class},
            extensions={"available_mwh": available_mwh},
        )

    bids = (
        bid("wind-down", "wind", "down", wind_schedule, 0.0, "vre", wind_schedule),
        bid("thermal-up", "thermal", "up", 2.5, 70.0, "thermal", 0.0),
        bid("battery-up", "battery", "up", 1.0, 30.0, "storage", 0.0),
        bid("battery-down", "battery", "down", 1.0, 10.0, "storage", 0.0),
    )
    model_input = BalancingInput(
        run_id=ahead.run_id,
        year=2025,
        period=step,
        period_id=period_id,
        ahead_result_sha256=contract_sha256(ahead),
        real_demand_mwh=demand,
        realised_availability_mw_by_asset={"wind": 3.0, "thermal": 5.0, "battery": 2.0},
        initial_soc_mwh_by_asset={"battery": opening_soc_mwh},
        bids=bids,
        period_hours=period_hours,
        voll_gbp_per_mwh=17_000.0,
        domain_payload={
            "schema_version": "value.zonal-redispatch-domain/v1",
            "zonal_demand_mode": "network_pack_absolute_demand",
            "ahead_result": ahead.to_dict(),
            "network_pack": pack.to_dict(),
            "real_demand_mwh_by_zone": {"gb": demand},
            "asset_zone_id_by_asset": {"wind": "gb", "thermal": "gb", "battery": "gb"},
            "resource_class_by_asset": {"wind": "vre", "thermal": "thermal", "battery": "storage"},
            "resource_cost_gbp_per_mwh_by_asset": {"wind": 0.0, "thermal": 70.0, "battery": 30.0},
            "storage": {
                "battery": {
                    "charge_power_mw": 2.0,
                    "discharge_power_mw": 2.0,
                    "energy_capacity_mwh": 4.0,
                    "charge_efficiency": 0.9,
                    "discharge_efficiency": 0.9,
                    "bid_contract": "convex_net_power_v1",
                }
            },
            "interconnector_envelope_mwh_by_asset": {},
            "corridor_limits_mw_by_id": {},
            "chronology_contract": {
                "information_scope": "current_period_only",
                "future_period_data_supplied": False,
                "soc_source": "previous_period_final_soc",
            },
        },
    )
    return model_input.to_dict()


def run_sequential_soc_case(
    hours: int,
    *,
    seed: int,
    tolerances: dict[str, float] | None = None,
) -> dict[str, object]:
    """Compare a chronological half-hour sequence with no future information."""

    from gridform_validation.zonal_oracle import (
        compare_zonal_solutions,
        solve_zonal_oracle,
    )

    if hours not in {24, 168}:
        raise ValueError("Prompt 103 chronology accepts only 24 or 168 hours")
    opening_soc = 2.0
    comparisons: list[dict[str, object]] = []
    for step in range(hours * 2):
        declaration = _chronology_declaration(
            step=step,
            opening_soc_mwh=opening_soc,
            seed=seed,
        )
        production = production_solution(declaration)
        oracle = solve_zonal_oracle(declaration)
        comparison = compare_zonal_solutions(
            declaration,
            production,
            oracle,
            tolerances=tolerances,
        )
        comparisons.append({
            "period": step,
            "period_id": declaration["period_id"],
            "passed": comparison["passed"],
            "classification": comparison["classification"],
            "opening_soc_mwh": opening_soc,
            "production_final_soc_mwh": production["final_soc_mwh_by_asset"]["battery"],
            "oracle_final_soc_mwh": oracle["final_soc_mwh_by_asset"]["battery"],
            "maximum_mapping_gaps": comparison["maximum_mapping_gaps"],
            "objective_gaps": comparison["objective_gaps"],
        })
        opening_soc = float(production["final_soc_mwh_by_asset"]["battery"])
    return {
        "hours": hours,
        "period_hours": 0.5,
        "periods": hours * 2,
        "seed": seed,
        "information_scope": "current_period_only",
        "future_period_data_supplied": False,
        "passed": all(bool(row["passed"]) for row in comparisons),
        "failure_count": sum(not bool(row["passed"]) for row in comparisons),
        "final_soc_mwh": opening_soc,
        "comparisons": comparisons,
    }
