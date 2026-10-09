"""Replaceable single-node current-period balancing implementation."""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping

from ...network_method_rules import bid_dec_rank, dec_price_band
from ...staged_market_contracts import (
    AcceptedAdjustment,
    AheadMarketResult,
    BalancingInput,
    BalancingResult,
    FlexibilityBid,
    contract_sha256,
)


def _is_storage(bid: FlexibilityBid) -> bool:
    return str(bid.provenance.get("resource_class") or "") == "storage"


def _price_groups(
    bids: list[FlexibilityBid], *, descending: bool, tie_rule: str
) -> list[list[FlexibilityBid]]:
    """Merit groups of one direction (1.1.0, P0-8 S7 and its M6 review).

    ``pro_rata_v1``: bids at exactly the same price and of the same class form
    one group whose acceptance is shared pro rata to their available energy,
    so renaming an asset never moves dispatch between equal-price assets
    (P2-05/P3-04).

    * Up (``descending=False``): ascending price; at an equal price storage
      comes after the generators and imports (Q8, as the zonal LP's physical
      tie phase).
    * Down (``descending=True``): descending 0.01-rounded dec price, then the
      shared dec class order ``network_method_rules.DEC_CLASSES`` (fuel,
      import, storage, run-of-river, VRE, nuclear; C15), then the exact price.
      Storage charging therefore absorbs a surplus before VRE is curtailed
      even when its dec price is capped at a GBP 0 inc of the same period.

    ``bid_id_v1`` is the 1.0.0 rule (one bid at a time, ties by bid id).
    """

    sign = -1.0 if descending else 1.0
    if tie_rule == "bid_id_v1":
        ordered = sorted(bids, key=lambda bid: (sign * bid.price_gbp_per_mwh, bid.bid_id))
        return [[bid] for bid in ordered]
    if tie_rule != "pro_rata_v1":
        raise ValueError(f"Unknown copperplate tie rule {tie_rule}")
    groups: dict[tuple[float, ...], list[FlexibilityBid]] = {}
    if descending:
        for bid in bids:
            price = float(bid.price_gbp_per_mwh)
            key = (-dec_price_band(price), float(bid_dec_rank(bid)), -price)
            groups.setdefault(key, []).append(bid)
        keys = sorted(groups)
    else:
        for bid in bids:
            key = (float(bid.price_gbp_per_mwh), 1.0 if _is_storage(bid) else 0.0)
            groups.setdefault(key, []).append(bid)
        keys = sorted(groups)
    return [sorted(groups[key], key=lambda bid: bid.bid_id) for key in keys]


class CopperplateBalancing:
    id = "force-copperplate-balancing"
    version = "1.1.0"

    def __init__(self, tie_rule: str = "pro_rata_v1") -> None:
        if tie_rule not in {"pro_rata_v1", "bid_id_v1"}:
            raise ValueError(f"Unknown copperplate tie rule {tie_rule}")
        self._tie_rule = tie_rule
        self._consumed_input_sha256: set[str] = set()

    @staticmethod
    def _payload(model_input: BalancingInput) -> tuple[AheadMarketResult, dict[str, object]]:
        payload = dict(model_input.domain_payload)
        if payload.get("schema_version") != "force.copperplate-balancing-domain/v1":
            raise ValueError("Copperplate balancing domain payload is unsupported")
        raw_ahead = payload.get("ahead_result")
        if not isinstance(raw_ahead, Mapping):
            raise ValueError("Copperplate balancing requires the frozen ahead result")
        ahead = AheadMarketResult.from_dict(raw_ahead)
        if contract_sha256(ahead) != model_input.ahead_result_sha256:
            raise ValueError("Declared ahead result hash does not match its payload")
        if (
            ahead.run_id,
            ahead.year,
            ahead.period,
            ahead.period_id,
        ) != (
            model_input.run_id,
            model_input.year,
            model_input.period,
            model_input.period_id,
        ):
            raise ValueError("Balancing input and ahead result identities do not match")
        return ahead, payload

    @staticmethod
    def _available_energy(bid: FlexibilityBid, period_hours: float) -> float:
        raw = bid.extensions.get("available_mwh")
        return max(
            float(raw) if raw is not None else bid.available_mw * period_hours,
            0.0,
        )

    def clear(self, model_input: BalancingInput) -> BalancingResult:
        ahead, payload = self._payload(model_input)
        input_sha256 = contract_sha256(model_input)
        if input_sha256 in self._consumed_input_sha256:
            raise ValueError("This balancing input has already been balanced")

        final_dispatch = {
            str(asset_id): float(value)
            for asset_id, value in ahead.schedule_mwh_by_asset.items()
        }
        accepted: list[AcceptedAdjustment] = []
        cashflows: defaultdict[str, float] = defaultdict(float)
        curtailment: defaultdict[str, float] = defaultdict(float)
        scheduled_supply = sum(final_dispatch.values())
        gap_mwh = float(model_input.real_demand_mwh) - scheduled_supply

        if gap_mwh > 1e-12:
            # 1.1.0: an up bid above VOLL is never accepted (shedding is
            # cheaper), the same economic rule as the zonal LP.
            candidates = [
                bid for bid in model_input.bids
                if bid.direction == "up"
                and (
                    self._tie_rule == "bid_id_v1"
                    or bid.price_gbp_per_mwh <= float(model_input.voll_gbp_per_mwh)
                )
            ]
            for group in _price_groups(candidates, descending=False, tie_rule=self._tie_rule):
                if gap_mwh <= 1e-12:
                    break
                capacities = [
                    self._available_energy(bid, model_input.period_hours) for bid in group
                ]
                total = sum(capacities)
                if total <= 1e-12:
                    continue
                fraction = min(gap_mwh / total, 1.0)
                for bid, capacity in zip(group, capacities):
                    delta = capacity if fraction >= 1.0 else capacity * fraction
                    if delta <= 1e-12:
                        continue
                    final_dispatch[bid.asset_id] = final_dispatch.get(bid.asset_id, 0.0) + delta
                    cashflow = delta * bid.price_gbp_per_mwh
                    accepted.append(AcceptedAdjustment(
                        bid.bid_id,
                        bid.agent_id,
                        bid.asset_id,
                        bid.zone_id,
                        delta,
                        bid.price_gbp_per_mwh,
                        cashflow,
                        "copperplate_up_balance",
                        extensions={"network_effect_id": bid.network_effect_id},
                    ))
                    cashflows[bid.agent_id] += cashflow
                gap_mwh = 0.0 if fraction < 1.0 else gap_mwh - total
        elif gap_mwh < -1e-12:
            surplus_mwh = -gap_mwh
            candidates = [bid for bid in model_input.bids if bid.direction == "down"]
            for group in _price_groups(candidates, descending=True, tie_rule=self._tie_rule):
                if surplus_mwh <= 1e-12:
                    break
                capacities = [
                    self._available_energy(bid, model_input.period_hours) for bid in group
                ]
                total = sum(capacities)
                if total <= 1e-12:
                    continue
                fraction = min(surplus_mwh / total, 1.0)
                for bid, capacity in zip(group, capacities):
                    volume = capacity if fraction >= 1.0 else capacity * fraction
                    if volume <= 1e-12:
                        continue
                    delta = -volume
                    final_dispatch[bid.asset_id] = final_dispatch.get(bid.asset_id, 0.0) + delta
                    cashflow = delta * bid.price_gbp_per_mwh
                    accepted.append(AcceptedAdjustment(
                        bid.bid_id,
                        bid.agent_id,
                        bid.asset_id,
                        bid.zone_id,
                        delta,
                        bid.price_gbp_per_mwh,
                        cashflow,
                        "copperplate_down_balance",
                        extensions={"network_effect_id": bid.network_effect_id},
                    ))
                    cashflows[bid.agent_id] += cashflow
                    curtailment_class = str(
                        bid.provenance.get("curtailment_class") or ""
                    )
                    if curtailment_class:
                        curtailment[curtailment_class] += volume
                surplus_mwh = 0.0 if fraction < 1.0 else surplus_mwh - total
            gap_mwh = -surplus_mwh

        blackout_mwh = max(gap_mwh, 0.0)
        if gap_mwh < -1e-8:
            raise ValueError(
                "Copperplate balancing has insufficient down flexibility for the declared surplus"
            )

        storage_payload = dict(payload.get("storage") or {})
        final_soc: dict[str, float] = {}
        for asset_id, opening in model_input.initial_soc_mwh_by_asset.items():
            specification = dict(storage_payload.get(asset_id) or {})
            dispatch = final_dispatch.get(asset_id, 0.0)
            charge_efficiency = float(specification.get("charge_efficiency", 1.0))
            discharge_efficiency = float(
                specification.get("discharge_efficiency", 1.0)
            )
            energy_capacity = float(
                specification.get("energy_capacity_mwh", opening)
            )
            soc = float(opening)
            if dispatch >= 0:
                soc -= dispatch / max(discharge_efficiency, 1e-12)
            else:
                soc += (-dispatch) * charge_efficiency
            if soc < -1e-8 or soc > energy_capacity + 1e-8:
                raise ValueError(f"Final SOC for {asset_id} violates its energy bound")
            final_soc[asset_id] = min(max(soc, 0.0), energy_capacity)

        cost_by_asset = {
            str(key): float(value)
            for key, value in dict(
                payload.get("resource_cost_gbp_per_mwh_by_asset") or {}
            ).items()
        }
        class_by_asset = {
            str(key): str(value)
            for key, value in dict(payload.get("resource_class_by_asset") or {}).items()
        }
        resource_costs: defaultdict[str, float] = defaultdict(float)
        for asset_id, dispatch_mwh in final_dispatch.items():
            if dispatch_mwh <= 0:
                continue
            resource_costs[class_by_asset.get(asset_id, "other")] += (
                dispatch_mwh * cost_by_asset.get(asset_id, 0.0)
            )
        residual = sum(final_dispatch.values()) + blackout_mwh - model_input.real_demand_mwh
        if abs(residual) > 1e-8:
            raise ValueError(f"Copperplate energy balance residual is {residual} MWh")

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
            curtailment_mwh_by_class=dict(curtailment),
            blackout_mwh=blackout_mwh,
            settlement_cashflow_gbp_by_agent=dict(cashflows),
            resource_cost_gbp_by_class=dict(resource_costs),
            energy_balance_residual_mwh=residual,
            extensions={
                "method": "lossless_single_node_pay_as_bid",
                "ahead_scheduled_supply_mwh": scheduled_supply,
            },
        )
        self._consumed_input_sha256.add(input_sha256)
        return result
