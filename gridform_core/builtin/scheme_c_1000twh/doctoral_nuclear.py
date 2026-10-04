"""A national dispatch view of the authoritative, year-updated station register.

This projection never commissions, retires, spatialises or redistributes income.
Keep the original station state for annual policy/planning. Use the returned
state consistently for national dispatch, cashflow and checkpoint identity.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import math
from typing import Mapping

from gridform_core.asset_economics import validate_asset_economics
from gridform_core.v2.contracts import AssetStateV2, OperatingState

PROFILE = "value.doctoral-national/v1"
AGGREGATION_SCHEMA = "value.doctoral-national-nuclear-aggregation/v1"
REGISTER_KEY = "doctoral_nuclear_register"
AGGREGATION_MARKERS = {"doctoral_nuclear_aggregation_schema", "doctoral_nuclear_register_sha256"}


def register_hash(register: Mapping) -> str:
    return hashlib.sha256(json.dumps(register, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def aggregate_doctoral_nuclear_state(state: OperatingState, *, policy_evidence: Mapping | None = None) -> OperatingState:
    """Project once, after policy retirement and current-year commissioning.

    Raw station economics are preserved in provenance. Aggregate economics sum
    only primary-ledger-included active members; externally financed project
    cost evidence stays separate, including its original price-year labels.
    The raw source Nuclear constructor CAPEX/ramp/startup are NOT these sums.
    """
    if state.extensions.get("doctoral_alignment_profile") != PROFILE:
        raise ValueError("Explicit doctoral national profile required for nuclear aggregation")
    if REGISTER_KEY in state.extensions or AGGREGATION_MARKERS.intersection(state.extensions) or any(
            AGGREGATION_MARKERS.intersection(a.extensions) for a in state.assets):
        raise ValueError("Nuclear dispatch view already aggregated; use the authoritative station register")
    ids = [a.asset_id for a in state.assets]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate station/state asset IDs")
    members = [a for a in state.assets if a.technology == "Nuclear"]
    projects = [p for p in state.active_planning_projects if p.technology == "Nuclear"]
    if any(p.status == "active" and p.expected_completion_year <= state.year for p in projects):
        raise ValueError("Nuclear commissioning must be applied before aggregation")
    if not members and not projects:
        return state
    if any(a.asset_id == "Nuclear" for a in members) and len(members) != 1:
        raise ValueError("Mixed national Nuclear object and station register")
    if "Nuclear" in ids and all(a.asset_id != "Nuclear" for a in members):
        raise ValueError("National Nuclear identity collides with a non-nuclear asset")
    active = []
    for asset in members:
        capacity = float(asset.capacity_mw)
        if not math.isfinite(capacity) or capacity < 0:
            raise ValueError(f"Invalid nuclear capacity for {asset.asset_id}")
        ext = asset.extensions
        if ext.get("doctoral_parameter_source_id", asset.asset_id) != "Nuclear":
            raise ValueError(f"Nuclear national parameter source required: {asset.asset_id}")
        if ext.get("investment_eligible") is not False:
            raise ValueError(f"Registered nuclear endogenous investment must be disabled: {asset.asset_id}")
        if asset.status not in {"operating", "commissioned", "retired"}:
            raise ValueError(f"Nuclear asset status is not a post-planning state: {asset.asset_id}")
        if asset.status == "retired" and capacity > 0:
            raise ValueError(f"Nuclear retirement has not cleared capacity: {asset.asset_id}")
        if capacity == 0:
            continue
        if ext.get("model_unavailable_from_year") is not None and state.year >= int(ext["model_unavailable_from_year"]):
            raise ValueError(f"Nuclear retirement must be applied before aggregation: {asset.asset_id}")
        if ext.get("model_first_full_operating_year") is not None and state.year < int(ext["model_first_full_operating_year"]):
            raise ValueError(f"Nuclear commissioning is premature: {asset.asset_id}")
        validate_asset_economics(asset)
        active.append(asset)
    register = copy.deepcopy({
        "schema_version": AGGREGATION_SCHEMA, "model_year": state.year,
        "station_assets": [a.to_dict() for a in members],
        "pipeline_projects": [p.to_dict() for p in projects],
        "policy_evidence": dict(policy_evidence) if policy_evidence is not None else None,
        "active_station_ids": [a.asset_id for a in active],
        "national_capacity_mw": math.fsum(a.capacity_mw for a in active),
        "income_allocation": "national_only; station allocation deferred",
        "financial_boundary": "primary included members only; external evidence remains in component records",
    })
    digest = register_hash(register)
    state_extensions = {**copy.deepcopy(dict(state.extensions)), REGISTER_KEY: register,
                        "doctoral_nuclear_register_sha256": digest}
    if not active:
        return replace(state, assets=tuple(a for a in state.assets if a.technology != "Nuclear"), extensions=state_extensions)
    included = [a for a in active if a.extensions.get("primary_cost_ledger_included") is not False]
    basis = included[0] if included else active[0]
    for asset in included:
        for key in ("economic_lifetime_years", "capital_discount_rate"):
            if float(asset.extensions[key]) != float(basis.extensions[key]):
                raise ValueError(f"Incompatible nuclear primary economics {key}; cannot merge different bases")
    total = register["national_capacity_mw"]
    capex = math.fsum(float(a.extensions["total_capex_gbp"]) for a in included)
    extensions = {
        "doctoral_parameter_source_id": "Nuclear",
        "doctoral_nuclear_aggregation_schema": AGGREGATION_SCHEMA,
        "doctoral_nuclear_register_sha256": digest,
        "investment_owner_id": "Nuclear", "investment_eligible": False,
        "source_record_id": "Nuclear", "source": "national dispatch view of registered stations",
        "capital_cost_per_mw": capex / total, "capital_cost_per_mwh": 0.0,
        "total_capex_gbp": capex,
        "annual_fixed_opex_gbp": math.fsum(float(a.extensions["annual_fixed_opex_gbp"]) for a in included),
        "annualized_capital_cost_gbp": math.fsum(float(a.extensions["annualized_capital_cost_gbp"]) for a in included),
        "economic_lifetime_years": float(basis.extensions["economic_lifetime_years"]),
        "capital_discount_rate": float(basis.extensions["capital_discount_rate"]),
        "asset_economics_schema_version": basis.extensions["asset_economics_schema_version"],
        "fixed_om_basis": "sum of primary-included registered station fixed O&M",
        "primary_cost_ledger_included": bool(included),
    }
    aggregate = AssetStateV2("Nuclear", "Nuclear", total, region="GB", extensions=extensions)
    validate_asset_economics(aggregate)
    assets, inserted = [], False
    for asset in state.assets:
        if asset.technology != "Nuclear":
            assets.append(asset)
        elif not inserted:
            assets.append(aggregate)
            inserted = True
    return replace(state, assets=tuple(assets), extensions=state_extensions)


def validate_doctoral_nuclear_view(state: OperatingState) -> None:
    """Verify the complete view, not just a caller-supplied hash string."""
    register = state.extensions.get(REGISTER_KEY)
    if register is None:
        if REGISTER_KEY in state.extensions or AGGREGATION_MARKERS.intersection(state.extensions) or any(
                AGGREGATION_MARKERS.intersection(a.extensions) for a in state.assets):
            raise ValueError("Nuclear register is missing from an aggregated dispatch view")
        return
    if not isinstance(register, Mapping) or register.get("schema_version") != AGGREGATION_SCHEMA:
        raise ValueError("Unsupported nuclear register schema")
    digest = register_hash(register)
    if digest != state.extensions.get("doctoral_nuclear_register_sha256") or register.get("model_year") != state.year:
        raise ValueError("Nuclear register identity/year mismatch")
    assets = [a for a in state.assets if a.technology == "Nuclear"]
    # Reconcile all economic fields and the still-active pipeline, not only MW.
    # A caller cannot change totals while retaining the same provenance hash.
    restored = replace(state,
        assets=tuple(a for a in state.assets if a.technology != "Nuclear") +
               tuple(AssetStateV2.from_dict(row) for row in register["station_assets"]),
        extensions={key: value for key, value in state.extensions.items()
                    if key not in {REGISTER_KEY, "doctoral_nuclear_register_sha256"}})
    expected = aggregate_doctoral_nuclear_state(restored, policy_evidence=register.get("policy_evidence"))
    expected_assets = [a.to_dict() for a in expected.assets if a.technology == "Nuclear"]
    if expected.extensions["doctoral_nuclear_register_sha256"] != digest:
        raise ValueError("Nuclear register content/identity mismatch")
    if [a.to_dict() for a in assets] != expected_assets:
        raise ValueError("Nuclear dispatch view capacity/economics/identity mismatch")
