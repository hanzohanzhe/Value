"""Independent PuLP/CBC oracle and residual audit for zonal redispatch."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy

import pulp

from gridform_validation.cbc import cbc_identity, cbc_path


DOMAIN_SCHEMA = "value.zonal-redispatch-domain/v1"
PACK_SCHEMA = "value.zonal-network-pack/v1"
EPSILON = 1e-8


def _canonical_sha256(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _number(value: object, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{label} is outside its valid range")
    return result


def _objects(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} contains a non-object")
        rows.append(dict(item))
    return rows


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _numeric_mapping(value: object, label: str) -> dict[str, float]:
    return {
        key: _number(item, f"{label}.{key}")
        for key, item in _mapping(value, label).items()
    }


def _read_case(declaration: Mapping[str, object]) -> dict[str, object]:
    data = dict(declaration)
    if data.get("schema_version") != "value.balancing-input/v1":
        raise ValueError("Unsupported balancing-input schema")
    domain = _mapping(data.get("domain_payload"), "domain_payload")
    if domain.get("schema_version") != DOMAIN_SCHEMA:
        raise ValueError("Unsupported zonal-domain schema")
    ahead = _mapping(domain.get("ahead_result"), "ahead_result")
    if ahead.get("schema_version") != "value.ahead-market-result/v1":
        raise ValueError("Unsupported ahead-result schema")
    if _canonical_sha256(ahead) != str(data.get("ahead_result_sha256") or ""):
        raise ValueError("Ahead-result payload does not match its declared digest")
    for key in ("run_id", "year", "period", "period_id"):
        if ahead.get(key) != data.get(key):
            raise ValueError(f"Ahead and balancing identities differ at {key}")

    pack = _mapping(domain.get("network_pack"), "network_pack")
    if pack.get("schema_version") != PACK_SCHEMA:
        raise ValueError("Unsupported network-pack schema")
    if pack.get("loss_capability_absent_reason") != "lossless_v1":
        raise ValueError("The v1 oracle accepts only a declared lossless network")
    hash_payload = deepcopy(pack)
    declared_pack_hash = str(hash_payload.get("scientific_sha256") or "")
    hash_payload["scientific_sha256"] = ""
    if _canonical_sha256(hash_payload) != declared_pack_hash:
        raise ValueError("Network pack fails its scientific-identity check")

    zones_raw = _objects(pack.get("zones"), "zones")
    zones = [str(row.get("zone_id") or "") for row in zones_raw]
    if not zones or any(not zone for zone in zones) or len(set(zones)) != len(zones):
        raise ValueError("Network zones must have unique non-empty IDs")
    zone_set = set(zones)
    corridors = sorted(
        _objects(pack.get("corridors", ()), "corridors"),
        key=lambda row: str(row.get("corridor_id") or ""),
    )
    corridor_ids: set[str] = set()
    adjacency = {zone: set() for zone in zones}
    for corridor in corridors:
        corridor_id = str(corridor.get("corridor_id") or "")
        start = str(corridor.get("from_zone_id") or "")
        end = str(corridor.get("to_zone_id") or "")
        if (
            not corridor_id
            or corridor_id in corridor_ids
            or start not in zone_set
            or end not in zone_set
            or start == end
            or corridor.get("positive_direction") != "from_to_positive"
        ):
            raise ValueError("Invalid computational corridor")
        corridor_ids.add(corridor_id)
        adjacency[start].add(end)
        adjacency[end].add(start)
    if len(zones) > 1:
        visited: set[str] = set()
        pending = [zones[0]]
        while pending:
            zone = pending.pop()
            if zone in visited:
                continue
            visited.add(zone)
            pending.extend(adjacency[zone].difference(visited))
        explained = {
            str(row.get("zone_id"))
            for row in zones_raw
            if row.get("is_unconstrained_fallback") or row.get("island_reason")
        }
        if zone_set.difference(visited).difference(explained):
            raise ValueError("Network contains an unexplained isolated zone")

    period_id = str(data.get("period_id") or "")
    period_hours = _number(data.get("period_hours"), "period_hours", minimum=0.0)
    if period_hours <= 0:
        raise ValueError("period_hours must be positive")
    zonal_demand = _mapping(pack.get("zonal_demand"), "zonal_demand")
    period_ids = [str(value) for value in zonal_demand.get("period_ids", ())]
    if period_id not in period_ids:
        raise ValueError("The period is absent from the network-pack clock")
    period_index = period_ids.index(period_id)
    demand = _numeric_mapping(domain.get("real_demand_mwh_by_zone"), "zonal demand")
    if set(demand) != zone_set or any(value < 0 for value in demand.values()):
        raise ValueError("Zonal demand must name every zone and be non-negative")
    declared_demand = _number(data.get("real_demand_mwh"), "real_demand_mwh", minimum=0.0)
    if abs(sum(demand.values()) - declared_demand) > EPSILON:
        raise ValueError("Zonal demand does not reconcile to national demand")
    demand_series = _mapping(zonal_demand.get("demand_mwh_by_zone"), "demand series")
    for zone in zones:
        values = demand_series.get(zone)
        if not isinstance(values, Sequence) or period_index >= len(values):
            raise ValueError(f"Demand series for {zone} is incomplete")
        if abs(_number(values[period_index], f"demand series {zone}") - demand[zone]) > EPSILON:
            raise ValueError("Declared demand differs from the signed pack")

    schedule = _numeric_mapping(ahead.get("schedule_mwh_by_asset"), "ahead schedule")
    asset_zones = {
        key: str(value)
        for key, value in _mapping(
            domain.get("asset_zone_id_by_asset"), "asset zone map"
        ).items()
    }
    bids = sorted(_objects(data.get("bids", ()), "bids"), key=lambda row: str(row.get("bid_id") or ""))
    bid_ids: set[str] = set()
    assets = set(schedule)
    for bid in bids:
        bid_id = str(bid.get("bid_id") or "")
        asset = str(bid.get("asset_id") or "")
        zone = str(bid.get("zone_id") or "")
        direction = str(bid.get("direction") or "")
        if not bid_id or bid_id in bid_ids or not asset or direction not in {"up", "down"}:
            raise ValueError("Invalid or duplicate flexibility bid")
        bid_ids.add(bid_id)
        assets.add(asset)
        if zone not in zone_set or asset_zones.get(asset) != zone:
            raise ValueError(f"Bid {bid_id} has no valid frozen zone")
        if str(bid.get("period_id") or "") != period_id:
            raise ValueError(f"Bid {bid_id} uses the wrong period")
        baseline = _number(bid.get("baseline_mw"), f"{bid_id} baseline")
        if abs(baseline - schedule.get(asset, 0.0) / period_hours) > EPSILON:
            raise ValueError(f"Bid {bid_id} baseline differs from the ahead schedule")
        extension = _mapping(bid.get("extensions", {}), f"{bid_id} extensions")
        available = extension.get("available_mwh")
        if available is None:
            available = _number(bid.get("available_mw"), f"{bid_id} available MW") * period_hours
        if _number(available, f"{bid_id} available energy", minimum=0.0) <= 0:
            raise ValueError(f"Bid {bid_id} has no available energy")
        _number(bid.get("price_gbp_per_mwh"), f"{bid_id} price")
    if assets.difference(asset_zones):
        raise ValueError("At least one asset lacks a frozen zone")
    if {asset_zones[asset] for asset in assets}.difference(zone_set):
        raise ValueError("At least one asset maps to an unknown zone")

    classes = {
        key: str(value)
        for key, value in _mapping(
            domain.get("resource_class_by_asset", {}), "resource classes"
        ).items()
    }
    storage_raw = _mapping(domain.get("storage", {}), "storage")
    storage: dict[str, dict[str, object]] = {}
    opening_soc = _numeric_mapping(data.get("initial_soc_mwh_by_asset", {}), "opening SOC")
    for asset, value in storage_raw.items():
        specification = _mapping(value, f"storage {asset}")
        if specification.get("bid_contract") != "convex_net_power_v1":
            raise ValueError(f"Storage {asset} uses an unsupported bid contract")
        for key in ("charge_power_mw", "discharge_power_mw", "energy_capacity_mwh"):
            if _number(specification.get(key), f"{asset} {key}", minimum=0.0) <= 0:
                raise ValueError(f"Storage {asset} has non-positive capacity")
        for key in ("charge_efficiency", "discharge_efficiency"):
            efficiency = _number(specification.get(key), f"{asset} {key}")
            if not 0 < efficiency <= 1:
                raise ValueError(f"Storage {asset} has invalid efficiency")
        capacity = float(specification["energy_capacity_mwh"])
        if asset not in opening_soc or opening_soc[asset] > capacity + EPSILON:
            raise ValueError(f"Storage {asset} has an impossible opening SOC")
        asset_bids = [bid for bid in bids if str(bid.get("asset_id")) == asset]
        direction_rows = {
            direction: [bid for bid in asset_bids if bid.get("direction") == direction]
            for direction in ("up", "down")
        }
        if any(len(rows) > 1 for rows in direction_rows.values()):
            raise ValueError(f"Storage {asset} has duplicate directional bids")
        if direction_rows["up"] and direction_rows["down"]:
            down_price = float(direction_rows["down"][0]["price_gbp_per_mwh"])
            up_price = float(direction_rows["up"][0]["price_gbp_per_mwh"])
            if down_price > up_price + EPSILON:
                raise ValueError(f"Storage {asset} has a non-convex bid curve")
        storage[asset] = specification
    for bid in bids:
        provenance = _mapping(bid.get("provenance", {}), "bid provenance")
        if provenance.get("resource_class") == "storage" and str(bid["asset_id"]) not in storage:
            raise ValueError("A storage bid lacks its physical declaration")

    availability = _numeric_mapping(
        data.get("realised_availability_mw_by_asset", {}), "realised availability"
    )
    if any(value < 0 for value in availability.values()):
        raise ValueError("Realised availability cannot be negative")
    envelopes_raw = _mapping(
        domain.get("interconnector_envelope_mwh_by_asset", {}),
        "interconnector envelopes",
    )
    envelopes: dict[str, tuple[float, float]] = {}
    for asset, value in envelopes_raw.items():
        envelope = _mapping(value, f"interconnector {asset}")
        minimum = _number(envelope.get("minimum_mwh"), f"{asset} minimum")
        maximum = _number(envelope.get("maximum_mwh"), f"{asset} maximum")
        if minimum > maximum or asset not in assets:
            raise ValueError(f"Interconnector envelope for {asset} is invalid")
        envelopes[asset] = (minimum, maximum)

    corridor_limits_raw = _mapping(
        domain.get("corridor_limits_mw_by_id", {}), "corridor limits"
    )
    if set(corridor_limits_raw).difference(corridor_ids):
        raise ValueError("A corridor limit names an unknown corridor")
    corridor_limits: dict[str, tuple[float | None, float | None]] = {}
    for corridor in corridors:
        corridor_id = str(corridor["corridor_id"])
        raw = corridor_limits_raw.get(corridor_id)
        if raw is None:
            corridor_limits[corridor_id] = (None, None)
        else:
            limit = _mapping(raw, f"corridor limit {corridor_id}")
            forward = _number(limit.get("forward_limit_mw"), "forward limit", minimum=0.0)
            reverse = _number(limit.get("reverse_limit_mw"), "reverse limit", minimum=0.0)
            corridor_limits[corridor_id] = (-reverse * period_hours, forward * period_hours)

    profiles = {
        str(row.get("profile_id")): row
        for row in _objects(pack.get("rating_profiles", ()), "rating profiles")
    }
    cutsets = _objects(pack.get("cutsets", ()), "cutsets")
    seen_boundaries: set[str] = set()
    for cutset in cutsets:
        boundary_id = str(cutset.get("boundary_id") or "")
        if not boundary_id or boundary_id in seen_boundaries:
            raise ValueError("Invalid or duplicate boundary")
        seen_boundaries.add(boundary_id)
        members = _objects(cutset.get("members", ()), f"boundary {boundary_id}")
        if not members:
            raise ValueError(f"Boundary {boundary_id} has no members")
        member_ids: set[str] = set()
        for member in members:
            corridor_id = str(member.get("corridor_id") or "")
            coefficient = int(member.get("coefficient", 0))
            if corridor_id not in corridor_ids or corridor_id in member_ids or coefficient not in {-1, 1}:
                raise ValueError(f"Boundary {boundary_id} has an invalid signed incidence")
            member_ids.add(corridor_id)
        _number(cutset.get("forward_limit_mw"), "boundary forward limit", minimum=0.0)
        _number(cutset.get("reverse_limit_mw"), "boundary reverse limit", minimum=0.0)
        profile_id = cutset.get("rating_profile_id")
        if profile_id and str(profile_id) not in profiles:
            raise ValueError(f"Boundary {boundary_id} has an unknown rating profile")

    return {
        "data": data,
        "domain": domain,
        "ahead": ahead,
        "pack": pack,
        "zones": zones,
        "corridors": corridors,
        "cutsets": cutsets,
        "profiles": profiles,
        "period_index": period_index,
        "period_hours": period_hours,
        "demand": demand,
        "schedule": schedule,
        "asset_zones": asset_zones,
        "classes": classes,
        "bids": bids,
        "storage": storage,
        "opening_soc": opening_soc,
        "availability": availability,
        "envelopes": envelopes,
        "corridor_limits": corridor_limits,
        "voll": _number(data.get("voll_gbp_per_mwh"), "VOLL", minimum=0.0),
    }


def _forced_down_parts(
    case: Mapping[str, object], bid_capacity: Mapping[str, float]
) -> dict[str, float]:
    """Down volume each bid must release because realised availability is short.

    Only assets that carry the realised-availability bound are concerned
    (storage, exports and interconnector envelopes are bound otherwise).  An
    asset's shortfall, ahead schedule minus available energy, is spread over
    its down bids in proportion to their capacity and never exceeds a bid's
    capacity.
    """

    period_hours = float(case["period_hours"])
    schedule = case["schedule"]
    storage = case["storage"]
    envelopes = case["envelopes"]
    classes = case["classes"]
    result: dict[str, float] = {}
    for asset, available_mw in sorted(case["availability"].items()):
        if asset in storage or asset in envelopes or classes.get(asset, "other") == "export":
            continue
        shortfall = float(schedule.get(asset, 0.0)) - float(available_mw) * period_hours
        if shortfall <= 0.0:
            continue
        down_ids = [
            str(bid["bid_id"])
            for bid in case["bids"]
            if str(bid["asset_id"]) == asset and bid["direction"] == "down"
        ]
        capacity = math.fsum(bid_capacity[bid_id] for bid_id in down_ids)
        if capacity <= 0.0:
            continue
        for bid_id in down_ids:
            result[bid_id] = min(bid_capacity[bid_id], shortfall * bid_capacity[bid_id] / capacity)
    return result


def _cbc() -> pulp.COIN_CMD:
    try:
        solver = pulp.COIN_CMD(msg=False, mip=False, threads=1, path=cbc_path())
    except RuntimeError:
        solver = None
    if solver is None or not solver.available():
        raise RuntimeError("The independent CBC executable is unavailable")
    return solver


def solve_zonal_oracle(declaration: Mapping[str, object]) -> dict[str, object]:
    """Solve one declared period without calling VALUE's production formulation."""

    case = _read_case(declaration)
    bids = case["bids"]
    corridors = case["corridors"]
    zones = case["zones"]
    storage = case["storage"]
    period_hours = float(case["period_hours"])
    demand = case["demand"]
    schedule = case["schedule"]
    asset_zones = case["asset_zones"]

    problem = pulp.LpProblem("independent_zonal_redispatch", pulp.LpMinimize)
    ordered_variables: list[pulp.LpVariable] = []

    def variable(name: str, low: float | None, high: float | None) -> pulp.LpVariable:
        result = pulp.LpVariable(name, lowBound=low, upBound=high, cat="Continuous")
        ordered_variables.append(result)
        return result

    bid_vars: dict[str, pulp.LpVariable] = {}
    bid_capacity: dict[str, float] = {}
    for bid in bids:
        bid_id = str(bid["bid_id"])
        extensions = _mapping(bid.get("extensions", {}), f"{bid_id} extensions")
        capacity = extensions.get("available_mwh")
        if capacity is None:
            capacity = float(bid["available_mw"]) * period_hours
        bid_capacity[bid_id] = float(capacity)
        bid_vars[bid_id] = variable(f"bid__{bid_id}", 0.0, float(capacity))

    flow_vars: dict[str, pulp.LpVariable] = {}
    for corridor in corridors:
        corridor_id = str(corridor["corridor_id"])
        low, high = case["corridor_limits"][corridor_id]
        flow_vars[corridor_id] = variable(f"flow__{corridor_id}", low, high)
    shedding_vars = {
        zone: variable(f"shed__{zone}", 0.0, float(demand[zone]))
        for zone in sorted(zones)
    }
    discharge_vars = {
        asset: variable(
            f"discharge__{asset}",
            0.0,
            float(spec["discharge_power_mw"]) * period_hours,
        )
        for asset, spec in sorted(storage.items())
    }
    charge_vars = {
        asset: variable(
            f"charge__{asset}",
            0.0,
            float(spec["charge_power_mw"]) * period_hours,
        )
        for asset, spec in sorted(storage.items())
    }
    absolute_flow_vars = {
        corridor_id: variable(f"absolute_flow__{corridor_id}", 0.0, None)
        for corridor_id in sorted(flow_vars)
    }

    base_by_zone: dict[str, float] = defaultdict(float)
    for asset, value in schedule.items():
        base_by_zone[asset_zones[asset]] += float(value)
    for zone in zones:
        bid_effect = pulp.lpSum(
            (1.0 if bid["direction"] == "up" else -1.0)
            * bid_vars[str(bid["bid_id"])]
            for bid in bids
            if bid["zone_id"] == zone
        )
        flow_effect = pulp.lpSum(
            (-1.0 if corridor["from_zone_id"] == zone else 0.0)
            * flow_vars[str(corridor["corridor_id"])]
            + (1.0 if corridor["to_zone_id"] == zone else 0.0)
            * flow_vars[str(corridor["corridor_id"])]
            for corridor in corridors
        )
        problem += (
            bid_effect + shedding_vars[zone] + flow_effect
            == float(demand[zone]) - base_by_zone.get(zone, 0.0),
            f"zonal_balance__{zone}",
        )

    for asset in sorted(storage):
        net_bid = pulp.lpSum(
            (-1.0 if bid["direction"] == "up" else 1.0)
            * bid_vars[str(bid["bid_id"])]
            for bid in bids
            if bid["asset_id"] == asset
        )
        problem += (
            discharge_vars[asset] - charge_vars[asset] + net_bid
            == float(schedule.get(asset, 0.0)),
            f"storage_bid_identity__{asset}",
        )

    # Equal-price rule of solver contract v4, derived here from the declared
    # data rather than from the production builder.  Bids in the same
    # direction, zone, network effect and price are economically identical
    # whatever their technology, so the resource class is not in the key;
    # storage keeps its own convex identity and stays out.  A down bid whose
    # asset is bound by realised availability below its ahead schedule must
    # release that shortfall whatever the prices are: that forced part is
    # carved out first and only the remaining free volume is shared:
    #     (x_i - f_i) * free_1 == (x_1 - f_1) * free_i,   free = capacity - f.
    classes = case["classes"]
    forced_by_bid = _forced_down_parts(case, bid_capacity)
    groups: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for bid in bids:
        bid_id = str(bid["bid_id"])
        provenance = _mapping(bid.get("provenance", {}), "bid provenance")
        resource_class = str(provenance.get("resource_class") or classes.get(str(bid["asset_id"]), "other"))
        if resource_class == "storage":
            continue
        if bid_capacity[bid_id] - forced_by_bid.get(bid_id, 0.0) <= EPSILON:
            continue
        groups[(
            bid["direction"], bid["zone_id"], bid["network_effect_id"],
            float(bid["price_gbp_per_mwh"]),
        )].append(bid)
    for index, rows in enumerate(groups.values()):
        if len(rows) < 2:
            continue
        first_id = str(rows[0]["bid_id"])
        first_forced = forced_by_bid.get(first_id, 0.0)
        first_free = bid_capacity[first_id] - first_forced
        for row_index, bid in enumerate(rows[1:]):
            bid_id = str(bid["bid_id"])
            forced = forced_by_bid.get(bid_id, 0.0)
            free = bid_capacity[bid_id] - forced
            problem += (
                (bid_vars[bid_id] - forced) * first_free
                == (bid_vars[first_id] - first_forced) * free,
                f"pro_rata__{index}__{row_index}",
            )

    def adjustment(asset: str) -> pulp.LpAffineExpression:
        return pulp.lpSum(
            (1.0 if bid["direction"] == "up" else -1.0)
            * bid_vars[str(bid["bid_id"])]
            for bid in bids
            if bid["asset_id"] == asset
        )

    for asset, (minimum, maximum) in case["envelopes"].items():
        final = float(schedule.get(asset, 0.0)) + adjustment(asset)
        problem += final <= maximum, f"interconnector_max__{asset}"
        problem += final >= minimum, f"interconnector_min__{asset}"
    for asset, available_mw in case["availability"].items():
        if asset in storage or case["classes"].get(asset, "other") == "export" or asset in case["envelopes"]:
            continue
        final = float(schedule.get(asset, 0.0)) + adjustment(asset)
        problem += final <= float(available_mw) * period_hours, f"availability_max__{asset}"
        problem += final >= 0.0, f"availability_min__{asset}"

    for asset, specification in sorted(storage.items()):
        opening = float(case["opening_soc"][asset])
        final_soc = (
            opening
            - discharge_vars[asset] / float(specification["discharge_efficiency"])
            + charge_vars[asset] * float(specification["charge_efficiency"])
        )
        problem += final_soc >= 0.0, f"soc_min__{asset}"
        problem += final_soc <= float(specification["energy_capacity_mwh"]), f"soc_max__{asset}"

    profiles = case["profiles"]
    for boundary in case["cutsets"]:
        boundary_id = str(boundary["boundary_id"])
        transfer = pulp.lpSum(
            int(member["coefficient"]) * flow_vars[str(member["corridor_id"])]
            for member in _objects(boundary.get("members", ()), f"boundary {boundary_id}")
        )
        multiplier = 1.0
        if boundary.get("rating_profile_id"):
            profile = profiles[str(boundary["rating_profile_id"])]
            multiplier = float(profile["multipliers"][case["period_index"]])
        problem += transfer <= float(boundary["forward_limit_mw"]) * period_hours * multiplier, f"cut_forward__{boundary_id}"
        problem += transfer >= -float(boundary["reverse_limit_mw"]) * period_hours * multiplier, f"cut_reverse__{boundary_id}"

    for corridor_id in sorted(flow_vars):
        problem += absolute_flow_vars[corridor_id] >= flow_vars[corridor_id], f"abs_positive__{corridor_id}"
        problem += absolute_flow_vars[corridor_id] >= -flow_vars[corridor_id], f"abs_negative__{corridor_id}"

    primary = pulp.lpSum(
        (float(bid["price_gbp_per_mwh"]) if bid["direction"] == "up" else -float(bid["price_gbp_per_mwh"]))
        * bid_vars[str(bid["bid_id"])]
        for bid in bids
    ) + float(case["voll"]) * pulp.lpSum(shedding_vars.values())
    secondary = pulp.lpSum(bid_vars.values()) + pulp.lpSum(shedding_vars.values())
    physical = (
        pulp.lpSum(discharge_vars.values())
        + pulp.lpSum(charge_vars.values())
        + pulp.lpSum(absolute_flow_vars.values())
    )
    stable = pulp.lpSum(
        (index + 1) * value for index, value in enumerate(ordered_variables)
    )

    optima: dict[str, float] = {}
    for phase, expression in (
        ("primary", primary),
        ("secondary", secondary),
        ("physical", physical),
        ("stable", stable),
    ):
        problem.setObjective(expression)
        status = problem.solve(_cbc())
        if status != pulp.LpStatusOptimal:
            raise RuntimeError(f"Independent CBC {phase} solve was {pulp.LpStatus[status]}")
        optimum = float(pulp.value(expression) or 0.0)
        optima[phase] = optimum
        if phase != "stable":
            problem += expression == optimum, f"fix_{phase}_optimum"

    def value(variable_: pulp.LpVariable) -> float:
        result = float(variable_.value() or 0.0)
        return 0.0 if abs(result) <= EPSILON else result

    accepted = {bid_id: value(variable_) for bid_id, variable_ in bid_vars.items()}
    accepted_adjustment = {
        str(bid["bid_id"]): (
            accepted[str(bid["bid_id"])]
            if bid["direction"] == "up"
            else -accepted[str(bid["bid_id"])]
        )
        for bid in bids
    }
    final_dispatch = dict(schedule)
    for bid in bids:
        asset = str(bid["asset_id"])
        final_dispatch[asset] = final_dispatch.get(asset, 0.0) + accepted_adjustment[str(bid["bid_id"])]
    storage_charge = {asset: value(variable_) for asset, variable_ in charge_vars.items()}
    storage_discharge = {asset: value(variable_) for asset, variable_ in discharge_vars.items()}
    final_soc: dict[str, float] = {}
    for asset, specification in storage.items():
        final_dispatch[asset] = storage_discharge[asset] - storage_charge[asset]
        final_soc[asset] = (
            float(case["opening_soc"][asset])
            - storage_discharge[asset] / float(specification["discharge_efficiency"])
            + storage_charge[asset] * float(specification["charge_efficiency"])
        )
    flows = {corridor_id: value(variable_) for corridor_id, variable_ in flow_vars.items()}
    transfers = {
        str(boundary["boundary_id"]): sum(
            int(member["coefficient"]) * flows[str(member["corridor_id"])]
            for member in _objects(boundary.get("members", ()), "boundary members")
        )
        for boundary in case["cutsets"]
    }
    shedding = {zone: value(variable_) for zone, variable_ in shedding_vars.items()}
    result: dict[str, object] = {
        "success": True,
        "status": "optimal",
        "solver": "independent-pulp-cbc",
        "solver_locator": cbc_identity(),
        "primary_objective_gbp": optima["primary"],
        "secondary_objective_mwh": optima["secondary"],
        "physical_tie_objective": optima["physical"],
        "stable_tie_objective": optima["stable"],
        "accepted_mwh_by_bid": accepted,
        "accepted_adjustment_mwh_by_bid": accepted_adjustment,
        "final_dispatch_mwh_by_asset": final_dispatch,
        "final_soc_mwh_by_asset": final_soc,
        "storage_charge_mwh_by_asset": storage_charge,
        "storage_discharge_mwh_by_asset": storage_discharge,
        "corridor_flow_mwh_by_id": flows,
        "boundary_transfer_mwh_by_id": transfers,
        "load_shedding_mwh_by_zone": shedding,
        "blackout_mwh": sum(shedding.values()),
    }
    result["audit"] = audit_zonal_candidate(declaration, result)
    return result


def audit_zonal_candidate(
    declaration: Mapping[str, object],
    candidate: Mapping[str, object],
    *,
    tolerance: float = 1e-6,
) -> dict[str, object]:
    """Recalculate every declared physical and objective identity."""

    case = _read_case(declaration)
    violations: list[dict[str, object]] = []

    def violation(constraint: str, residual: float, detail: str) -> None:
        if abs(residual) > tolerance:
            violations.append({
                "constraint": constraint,
                "residual": residual,
                "detail": detail,
            })

    accepted = _numeric_mapping(candidate.get("accepted_mwh_by_bid", {}), "accepted bids")
    signed = _numeric_mapping(candidate.get("accepted_adjustment_mwh_by_bid", {}), "signed bids")
    final_dispatch = _numeric_mapping(candidate.get("final_dispatch_mwh_by_asset", {}), "final dispatch")
    flows = _numeric_mapping(candidate.get("corridor_flow_mwh_by_id", {}), "corridor flow")
    transfers = _numeric_mapping(candidate.get("boundary_transfer_mwh_by_id", {}), "boundary transfer")
    shedding = _numeric_mapping(candidate.get("load_shedding_mwh_by_zone", {}), "load shedding")
    charge = _numeric_mapping(candidate.get("storage_charge_mwh_by_asset", {}), "storage charge")
    discharge = _numeric_mapping(candidate.get("storage_discharge_mwh_by_asset", {}), "storage discharge")
    final_soc = _numeric_mapping(candidate.get("final_soc_mwh_by_asset", {}), "final SOC")

    expected_bid_ids = {str(bid["bid_id"]) for bid in case["bids"]}
    if set(accepted) != expected_bid_ids or set(signed) != expected_bid_ids:
        violations.append({"constraint": "bid_coverage", "residual": 1.0, "detail": "Candidate omits or adds bid IDs"})
    expected_final = dict(case["schedule"])
    for bid in case["bids"]:
        bid_id = str(bid["bid_id"])
        asset = str(bid["asset_id"])
        magnitude = accepted.get(bid_id, 0.0)
        extensions = _mapping(bid.get("extensions", {}), "bid extensions")
        capacity = extensions.get("available_mwh")
        if capacity is None:
            capacity = float(bid["available_mw"]) * float(case["period_hours"])
        if magnitude < -tolerance or magnitude > float(capacity) + tolerance:
            violations.append({"constraint": "bid_bound", "residual": max(-magnitude, magnitude - float(capacity)), "detail": bid_id})
        expected_signed = magnitude if bid["direction"] == "up" else -magnitude
        violation("bid_sign", signed.get(bid_id, 0.0) - expected_signed, bid_id)
        expected_final[asset] = expected_final.get(asset, 0.0) + expected_signed

    for asset, specification in case["storage"].items():
        storage_charge = charge.get(asset, 0.0)
        storage_discharge = discharge.get(asset, 0.0)
        period_hours = float(case["period_hours"])
        if storage_charge < -tolerance or storage_charge > float(specification["charge_power_mw"]) * period_hours + tolerance:
            violations.append({"constraint": "storage_charge_power", "residual": storage_charge, "detail": asset})
        if storage_discharge < -tolerance or storage_discharge > float(specification["discharge_power_mw"]) * period_hours + tolerance:
            violations.append({"constraint": "storage_discharge_power", "residual": storage_discharge, "detail": asset})
        net_dispatch = storage_discharge - storage_charge
        expected_final[asset] = net_dispatch
        bid_net = float(case["schedule"].get(asset, 0.0)) + sum(
            signed.get(str(bid["bid_id"]), 0.0)
            for bid in case["bids"]
            if bid["asset_id"] == asset
        )
        violation("storage_bid_identity", net_dispatch - bid_net, asset)
        computed_soc = (
            float(case["opening_soc"][asset])
            - storage_discharge / float(specification["discharge_efficiency"])
            + storage_charge * float(specification["charge_efficiency"])
        )
        violation("storage_efficiency_identity", final_soc.get(asset, 0.0) - computed_soc, asset)
        if final_soc.get(asset, 0.0) < -tolerance or final_soc.get(asset, 0.0) > float(specification["energy_capacity_mwh"]) + tolerance:
            violations.append({"constraint": "storage_energy", "residual": final_soc.get(asset, 0.0), "detail": asset})

    for asset, expected in expected_final.items():
        violation("final_dispatch_identity", final_dispatch.get(asset, 0.0) - expected, asset)
    for asset, (minimum, maximum) in case["envelopes"].items():
        value_ = final_dispatch.get(asset, 0.0)
        if value_ < minimum - tolerance or value_ > maximum + tolerance:
            violations.append({"constraint": "signed_interconnector_envelope", "residual": max(minimum - value_, value_ - maximum), "detail": asset})
    for asset, available_mw in case["availability"].items():
        if asset in case["storage"] or case["classes"].get(asset, "other") == "export" or asset in case["envelopes"]:
            continue
        value_ = final_dispatch.get(asset, 0.0)
        maximum = float(available_mw) * float(case["period_hours"])
        if value_ < -tolerance or value_ > maximum + tolerance:
            violations.append({"constraint": "realised_availability", "residual": max(-value_, value_ - maximum), "detail": asset})

    corridor_by_id = {str(row["corridor_id"]): row for row in case["corridors"]}
    if set(flows) != set(corridor_by_id):
        violations.append({"constraint": "corridor_coverage", "residual": 1.0, "detail": "Candidate corridor IDs differ"})
    for corridor_id, (minimum, maximum) in case["corridor_limits"].items():
        value_ = flows.get(corridor_id, 0.0)
        if minimum is not None and value_ < minimum - tolerance:
            violations.append({"constraint": "corridor_reverse_limit", "residual": minimum - value_, "detail": corridor_id})
        if maximum is not None and value_ > maximum + tolerance:
            violations.append({"constraint": "corridor_forward_limit", "residual": value_ - maximum, "detail": corridor_id})

    base_by_zone: dict[str, float] = defaultdict(float)
    for asset, value_ in final_dispatch.items():
        if asset in case["asset_zones"]:
            base_by_zone[case["asset_zones"][asset]] += value_
    for zone in case["zones"]:
        net_flow = 0.0
        for corridor_id, corridor in corridor_by_id.items():
            if corridor["from_zone_id"] == zone:
                net_flow -= flows.get(corridor_id, 0.0)
            if corridor["to_zone_id"] == zone:
                net_flow += flows.get(corridor_id, 0.0)
        residual = base_by_zone.get(zone, 0.0) + shedding.get(zone, 0.0) + net_flow - float(case["demand"][zone])
        violation("zonal_energy_balance", residual, zone)
        shed = shedding.get(zone, 0.0)
        if shed < -tolerance or shed > float(case["demand"][zone]) + tolerance:
            violations.append({"constraint": "load_shedding_bound", "residual": shed, "detail": zone})

    profiles = case["profiles"]
    for boundary in case["cutsets"]:
        boundary_id = str(boundary["boundary_id"])
        computed = sum(
            int(member["coefficient"]) * flows.get(str(member["corridor_id"]), 0.0)
            for member in _objects(boundary.get("members", ()), "boundary members")
        )
        violation("cutset_incidence", transfers.get(boundary_id, 0.0) - computed, boundary_id)
        multiplier = 1.0
        if boundary.get("rating_profile_id"):
            multiplier = float(profiles[str(boundary["rating_profile_id"])]["multipliers"][case["period_index"]])
        maximum = float(boundary["forward_limit_mw"]) * float(case["period_hours"]) * multiplier
        minimum = -float(boundary["reverse_limit_mw"]) * float(case["period_hours"]) * multiplier
        if computed > maximum + tolerance:
            violations.append({"constraint": "cutset_forward_limit", "residual": computed - maximum, "detail": boundary_id})
        if computed < minimum - tolerance:
            violations.append({"constraint": "cutset_reverse_limit", "residual": minimum - computed, "detail": boundary_id})

    expected_primary = sum(
        (float(bid["price_gbp_per_mwh"]) if bid["direction"] == "up" else -float(bid["price_gbp_per_mwh"]))
        * accepted.get(str(bid["bid_id"]), 0.0)
        for bid in case["bids"]
    ) + float(case["voll"]) * sum(shedding.values())
    expected_secondary = sum(accepted.values()) + sum(shedding.values())
    expected_physical = sum(charge.values()) + sum(discharge.values()) + sum(abs(value_) for value_ in flows.values())
    violation("primary_objective_voll", _number(candidate.get("primary_objective_gbp"), "primary objective") - expected_primary, "objective")
    violation("secondary_tie_breaking", _number(candidate.get("secondary_objective_mwh"), "secondary objective") - expected_secondary, "objective")
    violation("physical_tie_breaking", _number(candidate.get("physical_tie_objective"), "physical objective") - expected_physical, "objective")
    violation("blackout_identity", _number(candidate.get("blackout_mwh"), "blackout") - sum(shedding.values()), "national blackout")

    maximum = max((abs(float(row["residual"])) for row in violations), default=0.0)
    return {
        "passed": not violations,
        "maximum_constraint_violation": maximum,
        "violation_count": len(violations),
        "violations": violations,
    }


def _maximum_mapping_gap(left: object, right: object) -> float:
    left_map = _numeric_mapping(left, "left comparison mapping")
    right_map = _numeric_mapping(right, "right comparison mapping")
    return max(
        (abs(left_map.get(key, 0.0) - right_map.get(key, 0.0)) for key in set(left_map) | set(right_map)),
        default=0.0,
    )


def compare_zonal_solutions(
    declaration: Mapping[str, object],
    production: Mapping[str, object],
    oracle: Mapping[str, object],
    *,
    tolerances: Mapping[str, float] | None = None,
) -> dict[str, object]:
    """Compare two results after independently auditing each result."""

    limits = {
        "energy_mwh": 1e-6,
        "cost_gbp": 1e-5,
        "objective_relative": 1e-8,
        **dict(tolerances or {}),
    }
    production_audit = audit_zonal_candidate(declaration, production, tolerance=limits["energy_mwh"])
    oracle_audit = audit_zonal_candidate(declaration, oracle, tolerance=limits["energy_mwh"])
    objective_gaps: dict[str, float] = {}
    objective_pass = True
    for key, absolute_tolerance in (
        ("primary_objective_gbp", limits["cost_gbp"]),
        ("secondary_objective_mwh", limits["energy_mwh"]),
        ("physical_tie_objective", limits["energy_mwh"]),
        ("stable_tie_objective", limits["energy_mwh"]),
    ):
        left = _number(production.get(key), f"production {key}")
        right = _number(oracle.get(key), f"oracle {key}")
        gap = abs(left - right)
        objective_gaps[key] = gap
        allowed = max(absolute_tolerance, limits["objective_relative"] * max(abs(left), abs(right), 1.0))
        objective_pass = objective_pass and gap <= allowed
    mapping_fields = (
        "accepted_mwh_by_bid",
        "accepted_adjustment_mwh_by_bid",
        "final_dispatch_mwh_by_asset",
        "final_soc_mwh_by_asset",
        "storage_charge_mwh_by_asset",
        "storage_discharge_mwh_by_asset",
        "corridor_flow_mwh_by_id",
        "boundary_transfer_mwh_by_id",
        "load_shedding_mwh_by_zone",
    )
    mapping_gaps = {
        field: _maximum_mapping_gap(production.get(field, {}), oracle.get(field, {}))
        for field in mapping_fields
    }
    mapping_pass = all(gap <= limits["energy_mwh"] for gap in mapping_gaps.values())
    passed = bool(production_audit["passed"] and oracle_audit["passed"] and objective_pass and mapping_pass)
    if passed:
        classification = "independent_match"
    elif not production_audit["passed"] and oracle_audit["passed"]:
        classification = "production_constraint_defect"
    elif production_audit["passed"] and not oracle_audit["passed"]:
        classification = "oracle_constraint_defect"
    elif production_audit["passed"] and oracle_audit["passed"] and objective_pass:
        classification = "degenerate_solution_or_tie_break_difference"
    else:
        classification = "unresolved_solver_difference"
    return {
        "passed": passed,
        "classification": classification,
        "production_audit": production_audit,
        "oracle_audit": oracle_audit,
        "objective_gaps": objective_gaps,
        "maximum_mapping_gaps": mapping_gaps,
        "tolerances": limits,
    }
