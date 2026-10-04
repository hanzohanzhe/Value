"""Independent reservoir LP oracle; does not import VALUE hydrology builders."""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import linprog


def solve_reservoir_oracle(
    case: Mapping[str, float | None],
    inflow: Sequence[float],
    prices: Sequence[float],
) -> dict[str, object]:
    """Use a storage-recursion formulation distinct from production variable order."""

    count = len(inflow)
    # Variables are end storage first, then turbine, spill, bypass.
    storage, turbine, spill, bypass = 0, count, 2 * count, 3 * count
    objective = np.zeros(4 * count)
    conversion = float(case["conversion"]) * float(case["efficiency"])
    objective[turbine:turbine + count] = -np.asarray(prices) * conversion
    equality = np.zeros((count, 4 * count))
    right = np.asarray(inflow, dtype=float)
    for t in range(count):
        equality[t, storage + t] = 1
        equality[t, turbine + t] = 1
        equality[t, spill + t] = 1
        equality[t, bypass + t] = 1
        if t:
            equality[t, storage + t - 1] = -1
        else:
            right[t] += float(case["initial"])
    inequality = []
    upper = []
    for t in range(count):
        row = np.zeros(4 * count)
        row[turbine + t] = -1
        row[bypass + t] = -1
        inequality.append(row)
        upper.append(-float(case["minimum_environmental_release"]))
        row = np.zeros(4 * count)
        row[turbine + t] = 1
        row[bypass + t] = 1
        inequality.append(row)
        upper.append(float(case["max_total_release"]))
    storage_bounds = [(float(case["minimum"]), float(case["maximum"]))] * count
    terminal = case.get("terminal")
    if terminal is not None:
        storage_bounds[-1] = (float(terminal), float(terminal))
    bounds = (
        storage_bounds
        + [(0, float(case["max_turbine_release"]))] * count
        + [(0, None)] * count
        + [(0, float(case["max_total_release"]))] * count
    )
    result = linprog(
        objective, A_ub=np.asarray(inequality), b_ub=np.asarray(upper),
        A_eq=equality, b_eq=right, bounds=bounds, method="highs",
    )
    return {
        "success": bool(result.success),
        "objective_gbp": float(-result.fun) if result.success else None,
        "max_equality_residual": (
            float(np.max(np.abs(equality @ result.x - right))) if result.success else None
        ),
    }
