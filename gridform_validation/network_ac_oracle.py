"""Independent rectangular-coordinate AC power-flow oracle.

The production checker uses polar variables and bounded nonlinear least squares.
This validation oracle uses rectangular voltage variables and ``scipy.root``;
it imports no production AC equations, layouts or admittance builder.
"""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np
from scipy.optimize import root


def solve_rectangular_ac_oracle(case: Mapping[str, object]) -> dict[str, object]:
    buses = list(case["buses"])  # type: ignore[arg-type]
    branches = list(case["branches"])  # type: ignore[arg-type]
    base = float(case.get("base_mva", 100.0))
    ids = [str(bus["bus_id"]) for bus in buses]
    index = {bus: position for position, bus in enumerate(ids)}
    slack = [position for position, bus in enumerate(buses) if bus["bus_type"] == "slack"]
    if len(slack) != 1:
        raise ValueError("Rectangular oracle fixture requires one connected island")
    slack_index = slack[0]
    non_slack = [position for position in range(len(buses)) if position != slack_index]
    pq = [position for position, bus in enumerate(buses) if bus["bus_type"] == "pq"]
    pv = [position for position, bus in enumerate(buses) if bus["bus_type"] == "pv"]
    matrix = np.zeros((len(buses), len(buses)), dtype=complex)
    terms = {}
    for branch in branches:
        if not branch.get("in_service", True):
            continue
        impedance = complex(float(branch["resistance_pu"]), float(branch["reactance_pu"]))
        series = 1 / impedance
        charging = 1j * float(branch.get("charging_susceptance_pu") or 0.0) / 2
        tap = float(branch.get("tap_ratio") or 1.0) * np.exp(
            1j * math.radians(float(branch.get("phase_shift_degrees") or 0.0))
        )
        ff = (series + charging) / (tap * np.conjugate(tap))
        ft = -series / np.conjugate(tap)
        tf = -series / tap
        tt = series + charging
        f, t = index[str(branch["from_bus"])], index[str(branch["to_bus"])]
        matrix[f, f] += ff
        matrix[f, t] += ft
        matrix[t, f] += tf
        matrix[t, t] += tt
        terms[str(branch["branch_id"])] = (f, t, ff, ft, tf, tt)
    for position, bus in enumerate(buses):
        matrix[position, position] += complex(
            float(bus.get("shunt_conductance_pu") or 0.0),
            float(bus.get("shunt_susceptance_pu") or 0.0),
        )
    setpoint = {str(key): float(value) for key, value in dict(case["voltage_setpoint_pu"]).items()}
    p_spec = np.array([float(dict(case["p_spec_mw"])[bus]) for bus in ids])
    q_spec = np.array([float(dict(case["q_spec_mvar"])[bus]) for bus in ids])
    slack_voltage = setpoint[ids[slack_index]] + 0j

    def unpack(vector):
        voltage = np.ones(len(buses), dtype=complex)
        voltage[slack_index] = slack_voltage
        for position, bus in enumerate(non_slack):
            voltage[bus] = complex(vector[position], vector[len(non_slack) + position])
        return voltage

    def equations(vector):
        voltage = unpack(vector)
        injection = voltage * np.conjugate(matrix @ voltage) * base
        values = [injection.real[bus] - p_spec[bus] for bus in non_slack]
        values.extend(injection.imag[bus] - q_spec[bus] for bus in pq)
        values.extend(abs(voltage[bus]) ** 2 - setpoint[ids[bus]] ** 2 for bus in pv)
        return np.asarray(values)

    initial = np.concatenate((np.ones(len(non_slack)), np.zeros(len(non_slack))))
    solved = root(equations, initial, method="hybr", options={"xtol": 1e-11, "maxfev": 5000})
    residual = float(np.max(np.abs(equations(solved.x)), initial=0.0))
    if not solved.success or residual > 1e-7:
        return {"success": False, "message": solved.message, "maximum_residual": residual}
    voltage = unpack(solved.x)
    injection = voltage * np.conjugate(matrix @ voltage) * base
    branch_losses = {}
    for branch_id, (f, t, ff, ft, tf, tt) in terms.items():
        from_power = voltage[f] * np.conjugate(ff * voltage[f] + ft * voltage[t]) * base
        to_power = voltage[t] * np.conjugate(tf * voltage[f] + tt * voltage[t]) * base
        branch_losses[branch_id] = float(from_power.real + to_power.real)
    return {
        "success": True,
        "maximum_residual": residual,
        "voltage_magnitude_pu": {bus: float(abs(voltage[index[bus]])) for bus in ids},
        "voltage_angle_radians": {bus: float(np.angle(voltage[index[bus]])) for bus in ids},
        "active_injection_mw": {bus: float(injection.real[index[bus]]) for bus in ids},
        "reactive_injection_mvar": {bus: float(injection.imag[index[bus]]) for bus in ids},
        "active_loss_mw_by_branch": branch_losses,
    }
