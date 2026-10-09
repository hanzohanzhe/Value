"""Independent PuLP/CBC oracle for recorded VALUE single-stage clearing inputs.

This module imports neither the VALUE runtime nor its bid construction and merit
order functions.  Its only production input is the immutable SQLite declaration
artifact written before clearing.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pulp

from gridform_validation.cbc import cbc_identity, cbc_path


ORACLE_ID = "value.declared-clearing-pulp-cbc-oracle/v1"


@dataclass(frozen=True)
class DeclaredClearingResult:
    status: str
    offer_cost_gbp: float
    shortage_power_mw: float
    accepted_power_mw: float
    dispatch_power_mw_by_offer: dict[str, float]
    dispatch_power_mw_by_asset: dict[str, float]
    max_constraint_violation_mw: float


def _cbc() -> pulp.LpSolver:
    try:
        solver = pulp.COIN_CMD(msg=False, mip=False, threads=1, path=cbc_path())
    except RuntimeError:
        solver = None
    if solver is None or not solver.available():
        raise RuntimeError("Independent CBC executable is unavailable")
    return solver


def _supply_problem(payload: Mapping[str, Any]) -> tuple[float, float, list[dict[str, Any]]]:
    if "target_power_mw" in payload:
        target = float(payload["target_power_mw"])
    else:
        target = float(payload.get("remaining_target_power_mw", 0.0))
    period_hours = float(payload["period_hours"])
    offers = [
        dict(offer)
        for offer in payload.get("offers", [])
        if str(offer.get("side")) == "supply"
        and float(offer.get("maximum_power_mw", 0.0)) > 0
    ]
    return max(target, 0.0), period_hours, offers


def solve_declared_supply(payload: Mapping[str, Any], *, voll_gbp_per_mwh: float = 10_000.0) -> DeclaredClearingResult:
    target, period_hours, offers = _supply_problem(payload)
    problem = pulp.LpProblem("independent_force_declared_clearing", pulp.LpMinimize)
    dispatch = {
        index: pulp.LpVariable(
            f"offer_{index}",
            lowBound=max(float(offer.get("minimum_power_mw", 0.0)), 0.0),
            upBound=max(float(offer["maximum_power_mw"]), 0.0),
        )
        for index, offer in enumerate(offers)
    }
    shortage = pulp.LpVariable("shortage", lowBound=0.0, upBound=target)
    problem += pulp.lpSum(dispatch.values()) + shortage == target, "power_balance"
    offer_cost = pulp.lpSum(
        dispatch[index] * float(offer["offer_price_gbp_per_mwh"]) * period_hours
        for index, offer in enumerate(offers)
    )
    primary = offer_cost + shortage * float(voll_gbp_per_mwh) * period_hours
    problem.setObjective(primary)
    status = problem.solve(_cbc())
    if status != pulp.LpStatusOptimal:
        raise RuntimeError(f"Independent CBC status: {pulp.LpStatus[status]}")
    # Dispatch identity can differ under exact price ties. Scientific acceptance
    # therefore compares the independently optimal cost, served power and
    # shortage, rather than introducing a production-order-dependent tie-break.
    by_offer = {
        str(offer["offer_id"]): float(pulp.value(dispatch[index]) or 0.0)
        for index, offer in enumerate(offers)
    }
    by_asset: defaultdict[str, float] = defaultdict(float)
    for offer, power in zip(offers, by_offer.values()):
        by_asset[str(offer["asset_id"])] += power
    shortage_value = float(pulp.value(shortage) or 0.0)
    accepted = sum(by_offer.values())
    violations = [abs(accepted + shortage_value - target)]
    for offer, power in zip(offers, by_offer.values()):
        violations.extend((
            max(float(offer.get("minimum_power_mw", 0.0)) - power, 0.0),
            max(power - float(offer["maximum_power_mw"]), 0.0),
        ))
    return DeclaredClearingResult(
        status="optimal",
        offer_cost_gbp=float(sum(
            by_offer[str(offer["offer_id"])]
            * float(offer["offer_price_gbp_per_mwh"])
            * period_hours
            for offer in offers
        )),
        shortage_power_mw=shortage_value,
        accepted_power_mw=accepted,
        dispatch_power_mw_by_offer=by_offer,
        dispatch_power_mw_by_asset=dict(by_asset),
        max_constraint_violation_mw=max(violations, default=0.0),
    )


def audit_declared_solution(
    payload: Mapping[str, Any],
    *,
    dispatch_power_mw_by_offer: Mapping[str, float],
    shortage_power_mw: float,
    tolerance_mw: float = 1e-6,
) -> dict[str, Any]:
    target, _period_hours, offers = _supply_problem(payload)
    violations: list[dict[str, Any]] = []
    accepted = 0.0
    for offer in offers:
        offer_id = str(offer["offer_id"])
        power = float(dispatch_power_mw_by_offer.get(offer_id, 0.0))
        accepted += power
        lower = max(float(offer.get("minimum_power_mw", 0.0)), 0.0)
        upper = max(float(offer["maximum_power_mw"]), 0.0)
        if power < lower - tolerance_mw or power > upper + tolerance_mw:
            violations.append({"constraint": "offer_bound", "offer_id": offer_id, "value": power, "lower": lower, "upper": upper})
    residual = accepted + float(shortage_power_mw) - target
    if abs(residual) > tolerance_mw:
        violations.append({"constraint": "power_balance", "residual_mw": residual})
    if float(shortage_power_mw) < -tolerance_mw:
        violations.append({"constraint": "shortage_nonnegative", "value": shortage_power_mw})
    return {
        "passed": not violations,
        "max_balance_residual_mw": abs(residual),
        "violations": violations,
    }


def audit_declared_storage_limits(payload: Mapping[str, Any], *, tolerance_mw: float = 1e-6) -> dict[str, Any]:
    """Independently check SOC, efficiency, MW/MWh and tranche offer limits."""
    period_hours = float(payload["period_hours"])
    states = (
        payload.get("storage_pre_clearing_state")
        or payload.get("storage_pre_state")
        or []
    )
    by_asset = {str(row["asset_id"]): dict(row) for row in states}
    violations: list[dict[str, Any]] = []
    discharge_offer_by_asset: defaultdict[str, float] = defaultdict(float)
    for offer in payload.get("offers", []):
        if offer.get("resource_kind") != "storage_discharge":
            continue
        asset_id = str(offer["asset_id"])
        maximum = float(offer["maximum_power_mw"])
        discharge_offer_by_asset[asset_id] += maximum
        state = by_asset.get(asset_id)
        if state is None:
            violations.append({"constraint": "storage_state_present", "asset_id": asset_id})
            continue
        charge_period = offer.get("charge_period")
        if charge_period is not None:
            tranches = {
                int(item["charge_period"]): float(item["stored_mwh"])
                for item in state.get("stored_tranches_mwh", [])
            }
            tranche_limit = tranches.get(int(charge_period), 0.0) * float(state["discharge_efficiency"]) / period_hours
            if maximum > tranche_limit + tolerance_mw:
                violations.append({
                    "constraint": "storage_tranche_energy",
                    "asset_id": asset_id,
                    "charge_period": int(charge_period),
                    "offered_power_mw": maximum,
                    "upper_power_mw": tranche_limit,
                })
    for asset_id, state in by_asset.items():
        soc = float(state["state_of_charge_mwh"])
        capacity = float(state["energy_capacity_mwh"])
        power = float(state["discharge_power_limit_mw"])
        charge_efficiency = float(state["charge_efficiency"])
        discharge_efficiency = float(state["discharge_efficiency"])
        if soc < -tolerance_mw or soc > capacity + tolerance_mw:
            violations.append({"constraint": "soc_bound", "asset_id": asset_id, "soc_mwh": soc, "capacity_mwh": capacity})
        if not 0 < charge_efficiency <= 1 or not 0 < discharge_efficiency <= 1:
            violations.append({"constraint": "storage_efficiency", "asset_id": asset_id})
        upper = min(power, max(soc, 0.0) * discharge_efficiency / period_hours)
        if discharge_offer_by_asset[asset_id] > upper + tolerance_mw:
            violations.append({
                "constraint": "shared_storage_power_and_energy",
                "asset_id": asset_id,
                "offered_power_mw": discharge_offer_by_asset[asset_id],
                "upper_power_mw": upper,
            })
    return {"passed": not violations, "violations": violations}


def audit_storage_transition(
    payload: Mapping[str, Any],
    outcome: Mapping[str, Any],
    *,
    tolerance_mwh: float = 1e-3,
) -> dict[str, Any]:
    """Check storage conservation from declared pre-state to recorded post-state."""
    stage = str(outcome.get("stage"))
    if stage == "balancing":
        pre_rows = payload.get("storage_pre_clearing_state", [])
    else:
        pre_rows = payload.get("storage_pre_state", [])
    post_rows = outcome.get("storage_post_state", [])
    pre = {str(row["asset_id"]): dict(row) for row in pre_rows}
    post = {str(row["asset_id"]): dict(row) for row in post_rows}
    violations: list[dict[str, Any]] = []
    if set(pre) != set(post):
        violations.append({"constraint": "storage_asset_set", "pre": sorted(pre), "post": sorted(post)})
    period_hours = float(payload["period_hours"])
    if stage in {"ahead", "balancing"}:
        discharged: defaultdict[str, float] = defaultdict(float)
        for row in outcome.get("accepted", []):
            if str(row.get("asset_type")) == "Battery":
                discharged[str(row["asset_id"])] += float(row["accepted_power_mw"])
        for asset_id in set(pre) & set(post):
            expected = (
                float(pre[asset_id]["state_of_charge_mwh"])
                - discharged[asset_id] * period_hours / float(pre[asset_id]["discharge_efficiency"])
            )
            residual = float(post[asset_id]["state_of_charge_mwh"]) - expected
            if abs(residual) > tolerance_mwh:
                violations.append({"constraint": "storage_discharge_soc", "asset_id": asset_id, "residual_mwh": residual})
    elif stage == "curtailment":
        inferred_input_power = 0.0
        for asset_id in set(pre) & set(post):
            delta = float(post[asset_id]["state_of_charge_mwh"]) - float(pre[asset_id]["state_of_charge_mwh"])
            if delta < -tolerance_mwh:
                violations.append({"constraint": "curtailment_storage_non_decreasing", "asset_id": asset_id, "delta_mwh": delta})
            inferred_input_power += max(delta, 0.0) / float(pre[asset_id]["charge_efficiency"]) / period_hours
        residual = inferred_input_power - float(outcome.get("storage_charge_power_mw", 0.0))
        if abs(residual) > max(tolerance_mwh / period_hours, 1e-6):
            violations.append({"constraint": "storage_charge_soc", "residual_power_mw": residual})
    return {"passed": not violations, "violations": violations}


def validate_declared_database(database: Path, *, tolerance: float = 1e-3) -> dict[str, Any]:
    database = database.resolve()
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT i.*, o.outcome_json FROM clearing_inputs i "
            "LEFT JOIN clearing_outcomes o USING(input_sha256) "
            "ORDER BY i.year, i.period, i.stage"
        ).fetchall()
    cases = []
    supported = 0
    passed = 0
    resource_kinds: set[str] = set()
    excluded_import_periods = 0
    storage_transition_failed_rows = 0
    for row in rows:
        envelope = json.loads(row["payload_json"])
        payload = envelope["payload"]
        stage = str(row["stage"])
        hash_valid = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() == row["input_sha256"]
        if payload.get("excluded_import_options"):
            excluded_import_periods += 1
        resource_kinds.update(str(item.get("resource_kind")) for item in payload.get("offers", []))
        if stage not in {"ahead", "balancing"}:
            outcome = json.loads(row["outcome_json"]) if row["outcome_json"] else None
            transition = audit_storage_transition(payload, outcome) if outcome else {"passed": False, "violations": [{"constraint": "missing_outcome"}]}
            storage_transition_failed_rows += int(not transition["passed"])
            cases.append({
                "year": row["year"], "period": row["period"], "stage": stage,
                "decision": "INFORMATION_STRUCTURE_NOT_LP",
                "hash_valid": hash_valid,
                "reason": "The retained curtailment stage is an explicit storage/export/flexible-demand/down-regulation waterfall, not a simultaneous cost-minimising supply LP.",
                "storage_transition_passed": transition["passed"],
                "storage_transition_violations": transition["violations"],
            })
            continue
        supported += 1
        storage_audit = audit_declared_storage_limits(payload)
        oracle = solve_declared_supply(payload)
        outcome = json.loads(row["outcome_json"]) if row["outcome_json"] else None
        if outcome is None:
            cases.append({
                "year": row["year"], "period": row["period"], "stage": stage,
                "decision": "MISSING_OUTCOME", "hash_valid": hash_valid,
            })
            continue
        transition = audit_storage_transition(payload, outcome)
        storage_transition_failed_rows += int(not transition["passed"])
        actual_cost = float(outcome.get("objective_gbp", 0.0))
        actual_shortage = float(outcome.get("unserved_target_power_mw", 0.0))
        actual_accepted = float(outcome.get("accepted_supply_power_mw", 0.0))
        cost_gap = actual_cost - oracle.offer_cost_gbp
        shortage_gap = actual_shortage - oracle.shortage_power_mw
        accepted_gap = actual_accepted - oracle.accepted_power_mw
        scale = max(abs(actual_cost), abs(oracle.offer_cost_gbp), 1.0)
        case_passed = (
            hash_valid
            and abs(cost_gap) <= max(0.05, scale * 1e-8)
            and abs(shortage_gap) <= tolerance
            and abs(accepted_gap) <= tolerance
            and oracle.max_constraint_violation_mw <= tolerance
            and storage_audit["passed"]
            and transition["passed"]
        )
        passed += int(case_passed)
        cases.append({
            "year": row["year"], "period": row["period"], "stage": stage,
            "decision": "MATCH" if case_passed else "DIFFERENCE",
            "hash_valid": hash_valid,
            "actual_offer_cost_gbp": actual_cost,
            "oracle_offer_cost_gbp": oracle.offer_cost_gbp,
            "offer_cost_gap_gbp": cost_gap,
            "actual_shortage_power_mw": actual_shortage,
            "oracle_shortage_power_mw": oracle.shortage_power_mw,
            "accepted_power_gap_mw": accepted_gap,
            "oracle_max_constraint_violation_mw": oracle.max_constraint_violation_mw,
            "storage_constraints_passed": storage_audit["passed"],
            "storage_constraint_violations": storage_audit["violations"],
            "storage_transition_passed": transition["passed"],
            "storage_transition_violations": transition["violations"],
        })
    return {
        "schema_version": "value.declared-clearing-validation/v1",
        "oracle_id": ORACLE_ID,
        "solver_locator": cbc_identity(),
        "power_tolerance_mw": tolerance,
        "cost_tolerance_gbp": "max(0.05, 1e-8 * comparison scale)",
        "database": str(database),
        "declared_rows": len(rows),
        "lp_supported_rows": supported,
        "lp_passed_rows": passed,
        "lp_failed_rows": supported - passed,
        "non_lp_information_structure_rows": len(rows) - supported,
        "excluded_import_periods": excluded_import_periods,
        "storage_transition_failed_rows": storage_transition_failed_rows,
        "resource_kinds": sorted(resource_kinds),
        "passed": supported > 0 and passed == supported and storage_transition_failed_rows == 0,
        "cases": cases,
    }
