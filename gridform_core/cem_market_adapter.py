"""Adapters between physical staged-market results and unchanged CEM contracts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Mapping

from .v2.contracts import InvestmentDecision, MarketYearResult, OperatingState


def _owner(asset: object) -> str:
    extensions = dict(getattr(asset, "extensions", {}) or {})
    return str(
        extensions.get("investment_owner_id")
        or extensions.get("source_agent_id")
        or getattr(asset, "asset_id")
    )


def adapt_market_for_investment(
    market: MarketYearResult, state: OperatingState
) -> MarketYearResult:
    """Allocate one owner settlement across its assets only for the CEM call."""

    if market.extensions.get("market_income_identity") != "economic_owner":
        return market
    grouped: dict[str, list[object]] = defaultdict(list)
    for asset in state.assets:
        grouped[_owner(asset)].append(asset)
    allocated: dict[str, float] = {}
    for owner, assets in grouped.items():
        income = float(market.market_income_gbp_by_agent.get(owner, 0.0) or 0.0)
        capacity = sum(float(getattr(asset, "capacity_mw")) for asset in assets)
        if capacity <= 0:
            continue
        for asset in assets:
            allocated[str(getattr(asset, "asset_id"))] = (
                income * float(getattr(asset, "capacity_mw")) / capacity
            )
    return replace(
        market,
        market_income_gbp_by_agent=allocated,
        extensions={
            **dict(market.extensions),
            "cem_income_adapter": "owner_settlement_allocated_once_by_operating_mw",
            "source_owner_income_gbp": dict(market.market_income_gbp_by_agent),
        },
    )


def inherit_frozen_zone_shares(
    decision: InvestmentDecision, state: OperatingState
) -> InvestmentDecision:
    """Attach owner-weighted immutable zone shares to new abstract capacity."""

    members: dict[tuple[str, str, str], list[object]] = defaultdict(list)
    for asset in state.assets:
        members[(_owner(asset), str(asset.technology), str(asset.region or "GB"))].append(asset)
    proposals = []
    for proposal in decision.proposals:
        rows = members.get((proposal.agent_id, proposal.technology, proposal.region), [])
        total = sum(float(getattr(asset, "capacity_mw")) for asset in rows)
        zone_mw: defaultdict[str, float] = defaultdict(float)
        revisions: set[str] = set()
        mapped = 0.0
        for asset in rows:
            raw = getattr(asset, "extensions").get("frozen_zone_shares")
            if not isinstance(raw, Mapping):
                continue
            shares = {str(key): float(value) for key, value in raw.items()}
            if abs(sum(shares.values()) - 1.0) > 1e-8:
                raise ValueError(f"Asset {asset.asset_id} has unreconciled frozen zone shares")
            mapped += float(asset.capacity_mw)
            for zone_id, share in shares.items():
                zone_mw[zone_id] += float(asset.capacity_mw) * share
            revision = str(asset.extensions.get("spatial_pack_revision") or "")
            if revision:
                revisions.add(revision)
        if not zone_mw:
            proposals.append(proposal)
            continue
        if total <= 0 or abs(mapped - total) > 1e-8:
            raise ValueError(f"Investment owner {proposal.agent_id} mixes mapped and unmapped capacity")
        if len(revisions) != 1:
            raise ValueError(f"Investment owner {proposal.agent_id} mixes spatial pack revisions")
        proposals.append(replace(
            proposal,
            extensions={
                **dict(proposal.extensions),
                "frozen_zone_shares": {
                    zone_id: value / total for zone_id, value in sorted(zone_mw.items())
                },
                "spatial_pack_revision": next(iter(revisions)),
                "zonal_allocation_inheritance": "owner_capacity_weighted_frozen_shares",
            },
        ))
    return replace(decision, proposals=tuple(proposals))
