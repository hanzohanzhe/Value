"""Independent DC-OPF oracle using angle-eliminated branch equations.

The oracle consumes plain serialized fixtures and imports no production network
contract, layout, branch-flow or constraint-builder code.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, lil_matrix


def solve_dc_oracle(case: Mapping[str, object]) -> dict[str, object]:
    buses = list(case["buses"])  # type: ignore[arg-type]
    branches = list(case.get("branches") or [])  # type: ignore[arg-type]
    resources = list(case.get("resources") or [])  # type: ignore[arg-type]
    stores = list(case.get("storage") or [])  # type: ignore[arg-type]
    demand = dict(case["demand_mwh_by_bus"])  # type: ignore[arg-type]
    period_hours = float(case["period_hours"])
    periods = len(next(iter(demand.values())))
    bus_id = [str(item["bus_id"]) for item in buses]
    bus_index = {value: index for index, value in enumerate(bus_id)}
    base_mva = float(case.get("base_mva", 100.0))
    cursor = 0

    def block(count: int):
        nonlocal cursor
        result = {}
        for period in range(periods):
            for item in range(count):
                result[period, item] = cursor
                cursor += 1
        return result

    generation = block(len(resources))
    charge = block(len(stores))
    discharge = block(len(stores))
    soc = block(len(stores))
    blackout = block(len(buses))
    angle = block(len(buses))
    size = cursor
    objective = np.zeros(size)
    bounds = [(None, None)] * size
    for period in range(periods):
        for index, resource in enumerate(resources):
            available = resource.get("availability", [1.0])
            value = float(available[period] if len(available) > 1 else available[0])
            bounds[generation[period, index]] = (
                0, float(resource["capacity_mw"]) * period_hours * value
            )
            costs = resource.get("marginal_cost_profile_gbp_per_mwh") or [resource["cost"]]
            objective[generation[period, index]] = float(
                costs[period] if len(costs) > 1 else costs[0]
            )
        for index, store in enumerate(stores):
            bounds[charge[period, index]] = (0, float(store["charge_power_mw"]) * period_hours)
            bounds[discharge[period, index]] = (0, float(store["discharge_power_mw"]) * period_hours)
            bounds[soc[period, index]] = (0, float(store["energy_capacity_mwh"]))
            objective[discharge[period, index]] = float(store.get("degradation_cost", 0))
        for index, bus in enumerate(buses):
            load = float(demand[bus["bus_id"]][period])
            bounds[blackout[period, index]] = (0, load)
            objective[blackout[period, index]] = float(case["voll"])
            bounds[angle[period, index]] = (
                (0, 0) if bus.get("is_reference") else (-math.pi, math.pi)
            )
    for index, store in enumerate(stores):
        target = float(store["initial_soc_mwh"])
        bounds[soc[periods - 1, index]] = (target, target)

    # Nodal balance substitutes f=B(theta_i-theta_j-phase), unlike production,
    # which creates explicit flow variables and equality rows.
    equality = lil_matrix((periods * (len(buses) + len(stores)), size))
    rhs = np.zeros(equality.shape[0])
    row = 0
    for period in range(periods):
        for index, bus in enumerate(buses):
            this_bus = str(bus["bus_id"])
            for resource_index, resource in enumerate(resources):
                if resource["bus_id"] == this_bus:
                    equality[row, generation[period, resource_index]] += 1
            for storage_index, store in enumerate(stores):
                if store["bus_id"] == this_bus:
                    equality[row, discharge[period, storage_index]] += 1
                    equality[row, charge[period, storage_index]] -= 1
            equality[row, blackout[period, index]] += 1
            phase_constant = 0.0
            for branch in branches:
                if not branch.get("in_service", True):
                    continue
                if this_bus not in {branch["from_bus"], branch["to_bus"]}:
                    continue
                tap = float(branch.get("tap_ratio") or 1.0)
                b = base_mva / (float(branch["reactance_pu"]) * tap)
                sign = 1.0 if branch["from_bus"] == this_bus else -1.0
                equality[row, angle[period, bus_index[branch["from_bus"]]]] -= sign * b * period_hours
                equality[row, angle[period, bus_index[branch["to_bus"]]]] += sign * b * period_hours
                phase_constant += sign * b * math.radians(float(branch.get("phase_shift_degrees") or 0)) * period_hours
            rhs[row] = float(demand[this_bus][period]) - phase_constant
            row += 1
        for index, store in enumerate(stores):
            equality[row, soc[period, index]] = 1
            equality[row, charge[period, index]] = -float(store["charge_efficiency"])
            equality[row, discharge[period, index]] = 1 / float(store["discharge_efficiency"])
            if period:
                equality[row, soc[period - 1, index]] = -1
            else:
                rhs[row] = float(store["initial_soc_mwh"])
            row += 1
    inequalities = []
    upper = []
    for period in range(periods):
        for branch in branches:
            if not branch.get("in_service", True):
                continue
            tap = float(branch.get("tap_ratio") or 1.0)
            b = base_mva / (float(branch["reactance_pu"]) * tap)
            phase = math.radians(float(branch.get("phase_shift_degrees") or 0))
            rating = float(branch["thermal_rating_mw"]) * int(branch.get("circuits", 1))
            for sign in (1.0, -1.0):
                constraint = np.zeros(size)
                constraint[angle[period, bus_index[branch["from_bus"]]]] = sign * b
                constraint[angle[period, bus_index[branch["to_bus"]]]] = -sign * b
                inequalities.append(constraint)
                upper.append(rating + sign * b * phase)
    solved = linprog(
        objective,
        A_ub=csr_matrix(np.asarray(inequalities)) if inequalities else None,
        b_ub=np.asarray(upper) if inequalities else None,
        A_eq=csr_matrix(equality), b_eq=rhs, bounds=bounds, method="highs",
    )
    if not solved.success:
        return {"success": False, "status": int(solved.status), "message": solved.message}
    x = solved.x
    dispatch = {
        str(resource["asset_id"]): float(sum(x[generation[p, index]] for p in range(periods)))
        for index, resource in enumerate(resources)
    }
    branch_flows = []
    for period in range(periods):
        values = {}
        for branch in branches:
            if not branch.get("in_service", True):
                values[str(branch["branch_id"])] = 0.0
                continue
            b = base_mva / (
                float(branch["reactance_pu"]) * float(branch.get("tap_ratio") or 1.0)
            )
            values[str(branch["branch_id"])] = float(
                b * (
                    x[angle[period, bus_index[branch["from_bus"]]]]
                    - x[angle[period, bus_index[branch["to_bus"]]]]
                    - math.radians(float(branch.get("phase_shift_degrees") or 0))
                )
            )
        branch_flows.append(values)
    return {
        "success": True,
        "objective_gbp": float(solved.fun),
        "dispatch_mwh_by_asset": dispatch,
        "branch_flows_mw": branch_flows,
        "maximum_equality_residual": float(
            np.max(np.abs(csr_matrix(equality) @ x - rhs), initial=0.0)
        ),
    }
