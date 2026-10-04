"""Independent PuLP/CBC formulation for public PSM contracts.

This file intentionally imports no production solver, merit-order, storage
dispatch, constraint-builder or compatibility-replay function.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pulp

from gridform_core.v2.contracts import ChronologicalPSMData


ORACLE_ID = "value.independent-pulp-cbc-oracle/v1"


@dataclass(frozen=True)
class OracleResult:
    status: str
    objective_gbp: float
    resource_dispatch_mwh: np.ndarray
    storage_charge_mwh: np.ndarray
    storage_discharge_mwh: np.ndarray
    storage_soc_mwh: np.ndarray
    blackout_mwh: np.ndarray
    max_balance_residual_mwh: float
    max_soc_residual_mwh: float
    max_bound_violation: float


def _profile(values, fallback: float, periods: int, label: str) -> np.ndarray:
    if not values:
        return np.repeat(float(fallback), periods)
    if len(values) == 1:
        return np.repeat(float(values[0]), periods)
    if len(values) != periods:
        raise ValueError(f"{label} requires 0, 1 or {periods} values")
    return np.asarray(values, dtype=float)


def _cbc() -> pulp.LpSolver:
    solver = pulp.COIN_CMD(msg=False, mip=False, threads=1)
    if not solver.available():
        raise RuntimeError("Independent CBC executable is unavailable; validation is NOT_INDEPENDENT")
    return solver


def solver_identity() -> dict[str, object]:
    solver = _cbc()
    binary = str(solver.path)
    resolved_binary = shutil.which(binary) or binary
    version = "not_reported"
    try:
        completed = subprocess.run(
            [resolved_binary, "-version"], capture_output=True, text=True, timeout=10, check=False
        )
        version = (completed.stdout or completed.stderr).strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    return {
        "oracle_id": ORACLE_ID,
        "modeler": f"PuLP {pulp.__version__}",
        "solver": "COIN-OR CBC",
        "solver_version": version,
        "solver_binary_sha256": (
            hashlib.sha256(Path(resolved_binary).read_bytes()).hexdigest()
            if Path(resolved_binary).is_file() else None
        ),
        "python": platform.python_version(),
        "license": {"PuLP": "MIT", "CBC": "EPL-2.0"},
    }


def solve_chronology(data: ChronologicalPSMData, period_hours: float) -> OracleResult:
    periods = len(data.period_ids)
    problem = pulp.LpProblem("independent_chronological_dispatch", pulp.LpMinimize)
    resource = {
        (index, period): pulp.LpVariable(f"g_{index}_{period}", lowBound=0)
        for index in range(len(data.resources)) for period in range(periods)
    }
    charge = {
        (index, period): pulp.LpVariable(f"ch_{index}_{period}", lowBound=0)
        for index in range(len(data.storage)) for period in range(periods)
    }
    discharge = {
        (index, period): pulp.LpVariable(f"dis_{index}_{period}", lowBound=0)
        for index in range(len(data.storage)) for period in range(periods)
    }
    soc = {
        (index, period): pulp.LpVariable(f"soc_{index}_{period}", lowBound=0)
        for index in range(len(data.storage)) for period in range(periods)
    }
    blackout = {
        period: pulp.LpVariable(f"blackout_{period}", lowBound=0)
        for period in range(periods)
    }
    costs = []
    throughput = []
    availability_profiles = []
    marginal_profiles = []
    for index, item in enumerate(data.resources):
        availability = _profile(item.availability, 1.0, periods, f"{item.asset_id}.availability")
        marginal = _profile(
            item.marginal_cost_profile_gbp_per_mwh,
            item.marginal_cost_gbp_per_mwh,
            periods,
            f"{item.asset_id}.marginal_cost",
        )
        availability_profiles.append(availability)
        marginal_profiles.append(marginal)
        for period in range(periods):
            problem += resource[index, period] <= (
                item.capacity_mw * period_hours * availability[period]
            ), f"resource_bound_{index}_{period}"
            costs.append(resource[index, period] * marginal[period])
    for index, item in enumerate(data.storage):
        for period in range(periods):
            problem += charge[index, period] <= item.charge_power_mw * period_hours
            problem += discharge[index, period] <= item.discharge_power_mw * period_hours
            problem += soc[index, period] <= item.energy_capacity_mwh
            previous = item.initial_soc_mwh if period == 0 else soc[index, period - 1]
            problem += soc[index, period] == (
                previous
                + item.charge_efficiency * charge[index, period]
                - discharge[index, period] / item.discharge_efficiency
            ), f"soc_balance_{index}_{period}"
            costs.append(
                discharge[index, period]
                * item.variable_degradation_gbp_per_mwh_discharged
            )
            throughput.extend((charge[index, period], discharge[index, period]))
        if data.terminal_soc_rule == "cyclic":
            problem += soc[index, periods - 1] == item.initial_soc_mwh
        elif data.terminal_soc_rule == "fixed":
            problem += soc[index, periods - 1] == data.terminal_soc_mwh_by_asset[item.asset_id]
    for period in range(periods):
        problem += blackout[period] <= (
            float(data.demand_mwh[period]) if data.allow_blackout else 0.0
        )
        problem += (
            pulp.lpSum(resource[index, period] for index in range(len(data.resources)))
            + pulp.lpSum(discharge[index, period] for index in range(len(data.storage)))
            + blackout[period]
            - pulp.lpSum(charge[index, period] for index in range(len(data.storage)))
            == float(data.demand_mwh[period])
        ), f"demand_balance_{period}"
        costs.append(blackout[period] * data.voll_gbp_per_mwh)
    primary = pulp.lpSum(costs)
    problem.setObjective(primary)
    status = problem.solve(_cbc())
    if status != pulp.LpStatusOptimal:
        raise RuntimeError(f"Independent CBC oracle status: {pulp.LpStatus[status]}")
    optimum = float(pulp.value(primary))
    problem += primary <= optimum + max(1e-7, abs(optimum) * 1e-10), "primary_optimum"
    problem.setObjective(pulp.lpSum(throughput))
    status = problem.solve(_cbc())
    if status != pulp.LpStatusOptimal:
        raise RuntimeError(f"Independent CBC tie-break status: {pulp.LpStatus[status]}")
    arrays = {
        "resource": np.asarray([
            [float(pulp.value(resource[index, period])) for period in range(periods)]
            for index in range(len(data.resources))
        ]),
        "charge": np.asarray([
            [float(pulp.value(charge[index, period])) for period in range(periods)]
            for index in range(len(data.storage))
        ]),
        "discharge": np.asarray([
            [float(pulp.value(discharge[index, period])) for period in range(periods)]
            for index in range(len(data.storage))
        ]),
        "soc": np.asarray([
            [float(pulp.value(soc[index, period])) for period in range(periods)]
            for index in range(len(data.storage))
        ]),
        "blackout": np.asarray([float(pulp.value(blackout[period])) for period in range(periods)]),
    }
    audit = audit_solution(data, period_hours, arrays)
    objective = float(sum(
        arrays["resource"][index, period] * marginal_profiles[index][period]
        for index in range(len(data.resources)) for period in range(periods)
    ) + sum(
        arrays["discharge"][index, period]
        * data.storage[index].variable_degradation_gbp_per_mwh_discharged
        for index in range(len(data.storage)) for period in range(periods)
    ) + arrays["blackout"].sum() * data.voll_gbp_per_mwh)
    return OracleResult(
        "optimal",
        objective,
        arrays["resource"],
        arrays["charge"],
        arrays["discharge"],
        arrays["soc"],
        arrays["blackout"],
        audit["max_balance_residual_mwh"],
        audit["max_soc_residual_mwh"],
        audit["max_bound_violation"],
    )


def audit_solution(
    data: ChronologicalPSMData,
    period_hours: float,
    arrays: Mapping[str, np.ndarray],
) -> dict[str, float | bool]:
    resource = np.asarray(arrays["resource"], dtype=float)
    charge = np.asarray(arrays["charge"], dtype=float)
    discharge = np.asarray(arrays["discharge"], dtype=float)
    soc = np.asarray(arrays["soc"], dtype=float)
    blackout = np.asarray(arrays["blackout"], dtype=float)
    periods = len(data.period_ids)
    balance = resource.sum(axis=0) + discharge.sum(axis=0) + blackout - charge.sum(axis=0) - np.asarray(data.demand_mwh)
    soc_residuals = []
    bound_violations = [0.0]
    for index, item in enumerate(data.resources):
        availability = _profile(item.availability, 1.0, periods, item.asset_id)
        upper = item.capacity_mw * period_hours * availability
        bound_violations.extend(np.maximum(resource[index] - upper, 0.0))
        bound_violations.extend(np.maximum(-resource[index], 0.0))
    for index, item in enumerate(data.storage):
        previous = item.initial_soc_mwh
        for period in range(periods):
            expected = previous + item.charge_efficiency * charge[index, period] - discharge[index, period] / item.discharge_efficiency
            soc_residuals.append(soc[index, period] - expected)
            previous = soc[index, period]
        bound_violations.extend(np.maximum(charge[index] - item.charge_power_mw * period_hours, 0.0))
        bound_violations.extend(np.maximum(discharge[index] - item.discharge_power_mw * period_hours, 0.0))
        bound_violations.extend(np.maximum(soc[index] - item.energy_capacity_mwh, 0.0))
        bound_violations.extend(np.maximum(-soc[index], 0.0))
        if data.terminal_soc_rule == "cyclic":
            soc_residuals.append(soc[index, -1] - item.initial_soc_mwh)
        elif data.terminal_soc_rule == "fixed":
            soc_residuals.append(soc[index, -1] - data.terminal_soc_mwh_by_asset[item.asset_id])
    bound_violations.extend(np.maximum(-blackout, 0.0))
    if not data.allow_blackout:
        bound_violations.extend(np.abs(blackout))
    result = {
        "max_balance_residual_mwh": float(np.max(np.abs(balance), initial=0.0)),
        "max_soc_residual_mwh": float(np.max(np.abs(soc_residuals), initial=0.0)),
        "max_bound_violation": float(np.max(bound_violations, initial=0.0)),
    }
    result["feasible"] = max(result.values()) <= 1e-6
    return result


def write_validation_report(path: Path, report: Mapping[str, object]) -> Path:
    payload = {
        "schema_version": "value.independent-psm-validation/v1",
        "oracle": solver_identity(),
        **dict(report),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path
