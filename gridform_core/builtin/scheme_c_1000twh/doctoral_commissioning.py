"""Doctoral annual schedule and independently evidenced financial allocations.

The helpers do not alter representative weather points, weather weights, source
files, nuclear policy, or the network method. Runtime interpretation of the
source's reversed pumped-storage limit names is a separate explicit boundary.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from ...asset_economics import capital_recovery_factor, validate_asset_economics
from ...v2.contracts import OperatingState, YearState


SCHEDULE_PATH = Path(__file__).resolve().parents[2] / "data/doctoral_alignment/pumped_hydro_schedule.json"
SCHEDULE_SCHEMA = "value.doctoral-pumped-hydro-schedule/v1"
SOURCE_ASSET_ID = "pumpedhydro_battery"


def _nonnegative(value, name):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"doctoral commissioning {name} must be finite and nonnegative")
    return number


def load_pumped_hydro_schedule() -> dict[int, dict[str, float]]:
    """Read the versioned source-literal schedule, including its separate units."""
    payload = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEDULE_SCHEMA or payload.get("source_asset_id") != SOURCE_ASSET_ID:
        raise ValueError("invalid doctoral pumped hydro schedule identity")
    result = {}
    for raw in payload["rows"]:
        year = int(raw["year"])
        if year in result or year != raw["year"]:
            raise ValueError("invalid or duplicated doctoral pumped schedule year")
        row = {key: _nonnegative(raw[key], key) for key in (
            "power_mw", "energy_mwh", "capital_cost_gbp", "source_pool_limit", "source_per_pool_limit")}
        if row["power_mw"] <= 0 or row["energy_mwh"] <= 0 or row["capital_cost_gbp"] <= 0:
            raise ValueError("doctoral pumped schedule quantities must be positive")
        if row["source_pool_limit"] != row["power_mw"] or row["source_per_pool_limit"] != row["energy_mwh"]:
            raise ValueError("doctoral pumped source literal assignment drift")
        result[year] = row
    if not result:
        raise ValueError("empty doctoral pumped hydro schedule")
    return result


def pumped_hydro_schedule_identity() -> dict[str, str]:
    return {"schema_version": SCHEDULE_SCHEMA,
            "sha256": hashlib.sha256(SCHEDULE_PATH.read_bytes()).hexdigest()}


def apply_doctoral_pumped_schedule(
    state: YearState | OperatingState, *, validation_mode: bool = False,
) -> YearState | OperatingState:
    """Apply the declared MW/MWh/CAPEX table to its existing named asset only.

    Mirrors the forward-only annual assignment boundary; absent assets and years
    outside the source table pass through. Physical attributes use the table's
    declared units. ``doctoral_pumped_source_assignment`` independently retains
    the actual original variable values for the runtime factory's unit policy.
    Existing life, discount, fixed O&M, weather, owner and other assets survive.
    """
    if validation_mode:
        return state
    row = load_pumped_hydro_schedule().get(state.year)
    if row is None:
        return state
    matching = [asset for asset in state.assets if asset.asset_id == SOURCE_ASSET_ID]
    if not matching:
        return state
    if len(matching) != 1 or matching[0].technology != "pumped_hydro":
        raise ValueError("doctoral pumped schedule requires one matching pumped_hydro asset")
    original = matching[0]
    ext = dict(original.extensions)
    power, energy, capital = row["power_mw"], row["energy_mwh"], row["capital_cost_gbp"]
    # The schedule is a whole-fleet capital amount, not a new-build catalogue
    # quote. Keep all representations internally consistent for typed ledgers.
    life = float(ext["economic_lifetime_years"])
    rate = float(ext["capital_discount_rate"])
    crf = capital_recovery_factor(rate, life)
    ext.update({
        "capital_cost_per_mw": capital / power, "capital_cost_per_mwh": 0.0,
        "total_capex_gbp": capital, "capital_recovery_factor": crf,
        "annualized_capital_cost_gbp": capital * crf,
        "energy_capacity_mwh_basis": energy, "duration_hours": energy / power,
        "doctoral_pumped_schedule_year": state.year,
        "doctoral_pumped_schedule_identity": pumped_hydro_schedule_identity(),
        "doctoral_pumped_source_assignment": {
            "pool_limit": row["source_pool_limit"], "per_pool_limit": row["source_per_pool_limit"],
            "capital_cost": capital,
        },
        "capital_cost_scope": "doctoral_exogenous_whole_fleet_schedule",
        "doctoral_pumped_units_basis": "declared_table_MW_MWh_separate_from_source_runtime_limits",
        "investment_eligible": False,
    })
    updated = replace(original, capacity_mw=power, energy_capacity_mwh=energy, extensions=ext)
    validate_asset_economics(updated)
    return replace(state, assets=tuple(updated if asset is original else asset for asset in state.assets))


def apply_thesis96_pumped_schedule(state: YearState | OperatingState) -> YearState | OperatingState:
    """Table 10 costs are already annual, unlike the old source CAPEX variable.

    The equivalent total-capital value is derived solely to satisfy the typed
    economic contract; it is not a claim about historical project expenditure.
    Annual OPEX and annualised CAPEX remain at the thesis's reported precision.
    """
    from ...doctoral_contract import load_thesis96_contract, thesis96_contract_identity
    rows = load_thesis96_contract()["pumped_hydro"]["rows"]
    row = next((row for row in rows if row["year"] == state.year), None)
    if row is None or not any(a.asset_id == SOURCE_ASSET_ID for a in state.assets):
        return state
    scheduled = apply_doctoral_pumped_schedule(state)
    original = next(a for a in scheduled.assets if a.asset_id == SOURCE_ASSET_ID)
    ext = dict(original.extensions)
    annual = _nonnegative(row["annualized_capital_gbp"], "annualized capital")
    fixed = _nonnegative(row["annual_opex_gbp"], "annual OPEX")
    crf = capital_recovery_factor(float(ext["capital_discount_rate"]), float(ext["economic_lifetime_years"]))
    equivalent_capital = annual / crf
    ext.update({"total_capex_gbp": equivalent_capital,
        "capital_cost_per_mw": equivalent_capital / original.capacity_mw,
        "annualized_capital_cost_gbp": annual, "annual_fixed_opex_gbp": fixed,
        "fixed_om_basis": "thesis_final9.6_table10_annual_opex",
        "capital_cost_scope": "equivalent_capital_from_thesis_annualized_cost_not_historical_expenditure",
        "annualized_capital_basis": "thesis_final9.6_table10_no_second_annuitization",
        "doctoral_thesis_identity": thesis96_contract_identity()})
    asset = replace(original, extensions=ext)
    validate_asset_economics(asset)
    return replace(scheduled, assets=tuple(asset if a is original else a for a in scheduled.assets))


def allocate_doctoral_vre_owners(
    existing_capacity_mw_by_agent: Mapping[str, float], projects: Sequence[Mapping[str, object]], *,
    capital_cost_per_mw: float = 0.0,
) -> dict[str, object]:
    """Run Case 3's financial owner allocation for one VRE technology.

    Source lines 1872--1909 credit assigned_generator objects first. Lines
    1917--1969 aggregate unassigned projects and allocate using the updated
    original agents' capacities, in name order with the last agent receiving
    the arithmetic remainder. Only additions above 1e-6 MW land. Source lines
    1973--1992 separately record project allocations from pre-addition shares.

    Inputs are original financial agent capacities and independently mapped
    ``assigned_generator`` fields, never weather IDs. This function only returns
    allocation evidence; it creates no assets and rewrites no frozen weather.
    Unknown assigned agents remain unresolved, matching the original branch.
    """
    capacities = {str(name): _nonnegative(value, "agent capacity") for name, value in existing_capacity_mw_by_agent.items()}
    capex = _nonnegative(capital_cost_per_mw, "CAPEX per MW")
    additions = {name: 0.0 for name in capacities}
    capital = {name: 0.0 for name in capacities}
    records: dict[str, dict[str, float]] = {}
    unresolved = []
    unassigned = []
    seen = set()
    for project in projects:
        project_id = str(project["project_id"])
        if not project_id or project_id in seen:
            raise ValueError("doctoral commissioning project IDs must be unique and nonempty")
        seen.add(project_id)
        amount = _nonnegative(project["capacity_mw"], "project capacity")
        owner = project.get("assigned_generator")
        records[project_id] = {}
        if owner is None:
            unassigned.append((project_id, amount))
        elif str(owner) in capacities:
            name = str(owner)
            capacities[name] += amount
            additions[name] += amount
            capital[name] += amount * capex
            records[project_id] = {name: amount}
        else:
            unresolved.append(project_id)
    unallocated = 0.0
    if unassigned:
        total_new = sum(amount for _, amount in unassigned)
        total_existing = sum(capacities.values())
        if capacities and total_existing > 0:
            ordered = sorted(capacities)
            remaining = total_new
            for index, name in enumerate(ordered):
                amount = remaining if index == len(ordered) - 1 else total_new * (capacities[name] / total_existing)
                if index != len(ordered) - 1:
                    remaining -= amount
                if amount > 1e-6:
                    additions[name] += amount
                    capital[name] += amount * capex
                else:
                    unallocated += amount
            # These are source per-project records, not a fabricated renormalized
            # allocation: a tiny record can be absent while the aggregate lands.
            for project_id, amount in unassigned:
                for name in ordered:
                    part = amount * (capacities[name] / total_existing)
                    if part > 1e-6:
                        records[project_id][name] = part
        elif capacities:
            name = next(iter(capacities))
            additions[name] += total_new
            capital[name] += total_new * capex
            for project_id, amount in unassigned:
                records[project_id] = {name: amount}
        else:
            unresolved.extend(project_id for project_id, _ in unassigned)
    return {"agent_additions_mw": additions, "agent_capital_additions_gbp": capital,
            "project_owner_allocations_mw": records, "unresolved_project_ids": unresolved,
            "unallocated_capacity_mw": unallocated,
            "source_allocation_rule": "assigned_first_then_post_assignment_capacity_proportions",
            "source_micro_capacity_threshold_mw": 1e-6}
