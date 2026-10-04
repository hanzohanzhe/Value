"""Open reference chronological DC network PSM using SciPy/HiGHS."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .network_contracts import (
    NetworkPSMInput,
    NetworkPSMOutput,
    NetworkPeriodResult,
    network_clearing_input_row,
)
from .v2.contracts import ArtifactReference, MarketYearResult, PSMInput, PeriodSummary


FORMULATION_ID = "value.reference-chronological-dc-opf/v1"
TOLERANCE = 1e-7


class DCNetworkInputError(ValueError):
    pass


class DCNetworkSolveError(RuntimeError):
    pass


@dataclass(frozen=True)
class _Layout:
    generation: Mapping[tuple[int, int], int]
    charge: Mapping[tuple[int, int], int]
    discharge: Mapping[tuple[int, int], int]
    soc: Mapping[tuple[int, int], int]
    blackout: Mapping[tuple[int, int], int]
    angle: Mapping[tuple[int, int], int]
    flow: Mapping[tuple[int, int], int]
    size: int


def _layout(model: NetworkPSMInput) -> _Layout:
    periods = len(model.chronology.period_ids)
    cursor = 0

    def block(count: int) -> dict[tuple[int, int], int]:
        nonlocal cursor
        result = {}
        for item in range(count):
            for period in range(periods):
                result[item, period] = cursor
                cursor += 1
        return result

    generation = block(len(model.chronology.resources))
    charge = block(len(model.chronology.storage))
    discharge = block(len(model.chronology.storage))
    soc = block(len(model.chronology.storage))
    blackout = block(len(model.topology.buses))
    angle = block(len(model.topology.buses))
    flow = block(len(model.topology.branches))
    return _Layout(generation, charge, discharge, soc, blackout, angle, flow, cursor)


def _series(values: Sequence[float], periods: int, label: str) -> np.ndarray:
    if len(values) == 1:
        result = np.repeat(float(values[0]), periods)
    elif len(values) == periods:
        result = np.asarray(values, dtype=float)
    else:
        raise DCNetworkInputError(f"{label} has {len(values)} values; expected 1 or {periods}")
    if not np.all(np.isfinite(result)):
        raise DCNetworkInputError(f"{label} contains non-finite values")
    return result


def _network_input(model_input: PSMInput) -> NetworkPSMInput:
    value = model_input.extensions.get("network_input")
    if not isinstance(value, Mapping):
        raise DCNetworkInputError(
            "value-reference-dc-network requires PSMInput.extensions.network_input; no copper-plate fallback is allowed"
        )
    network = NetworkPSMInput.from_dict(value)
    network.validate()
    if network.capability != "domain.network.dc":
        raise DCNetworkInputError("Reference DC module requires domain.network.dc")
    if network.run_id != model_input.run_id or network.year != model_input.year:
        raise DCNetworkInputError("Network input run/year identity mismatch")
    return network


def _artifacts(
    model_input: PSMInput, network_input: NetworkPSMInput, output: NetworkPSMOutput
) -> tuple[ArtifactReference, ...]:
    raw = model_input.extensions.get("artifact_directory")
    if not raw:
        return ()
    root = Path(str(raw)).resolve() / "network"
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"dc-network-{model_input.year}.json"
    json_path.write_text(json.dumps(output.to_dict(), indent=2), encoding="utf-8")
    input_path = root / f"declared-network-inputs-{model_input.year}.jsonl"
    with input_path.open("w", encoding="utf-8", newline="\n") as handle:
        for period in range(len(network_input.chronology.period_ids)):
            handle.write(json.dumps(network_clearing_input_row(network_input, period=period).__dict__) + "\n")
    sqlite_path = root / f"dc-network-{model_input.year}.sqlite"
    with closing(sqlite3.connect(sqlite_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE period_bus(period_id TEXT, bus_id TEXT, injection_mwh REAL,
              withdrawal_mwh REAL, blackout_mwh REAL, angle_rad REAL, price_gbp_per_mwh REAL,
              PRIMARY KEY(period_id,bus_id));
            CREATE TABLE period_branch(period_id TEXT, branch_id TEXT, flow_mw REAL,
              PRIMARY KEY(period_id,branch_id));
            """
        )
        for period in output.periods:
            for bus in period.nodal_injection_mwh:
                connection.execute(
                    "INSERT INTO period_bus VALUES (?,?,?,?,?,?,?)",
                    (
                        period.period_id, bus, period.nodal_injection_mwh[bus],
                        period.nodal_withdrawal_mwh[bus], period.blackout_mwh_by_bus[bus],
                        (period.voltage_angle_radians or {})[bus],
                        (period.nodal_price_gbp_per_mwh or {})[bus],
                    ),
                )
            for branch, flow in period.branch_flow_mw.items():
                connection.execute(
                    "INSERT INTO period_branch VALUES (?,?,?)",
                    (period.period_id, branch, flow),
                )
        connection.commit()
    result = []
    for path, kind, media in (
        (json_path, "network-result", "application/json"),
        (input_path, "declared-network-input", "application/x-ndjson"),
        (sqlite_path, "network-period-ledger", "application/x-sqlite3"),
    ):
        content = path.read_bytes()
        result.append(
            ArtifactReference(
                f"network/{path.name}", kind, f"solver/network/{path.name}", media,
                hashlib.sha256(content).hexdigest(), len(content),
            )
        )
    return tuple(result)


class ReferenceDCNetworkPSM:
    id = "value-reference-dc-network"
    version = "1.0.0"

    def run(self, model_input: PSMInput) -> MarketYearResult:
        # SciPy is an optional solver capability.  Keep this import at the
        # execution boundary so the base VALUE registry and single-node model
        # remain usable in a value-native installation that did not request
        # the solver extra.  Normal preflight reports the missing capability
        # before this method is called; this message is the fail-closed guard
        # for direct API callers.
        try:
            from scipy.optimize import linprog
            from scipy.sparse import csr_matrix, lil_matrix
        except ModuleNotFoundError as exc:
            raise DCNetworkSolveError(
                "The reference DC network PSM requires the optional SciPy "
                "solver capability; install the solver extra before running it"
            ) from exc
        model = _network_input(model_input)
        chronology = model.chronology
        periods = len(chronology.period_ids)
        buses = tuple(model.topology.buses)
        branches = tuple(model.topology.branches)
        bus_index = {item.bus_id: index for index, item in enumerate(buses)}
        mapping = model.topology.mapping_by_asset()
        layout = _layout(model)
        objective = np.zeros(layout.size)
        bounds: list[tuple[float | None, float | None]] = [(None, None)] * layout.size
        availability = []
        marginal_costs = []
        for resource_index, resource in enumerate(chronology.resources):
            available = _series(resource.availability, periods, f"availability {resource.asset_id}")
            if np.any(available < 0) or np.any(available > 1):
                raise DCNetworkInputError(f"Resource {resource.asset_id} availability is outside [0,1]")
            costs = _series(
                resource.marginal_cost_profile_gbp_per_mwh or (resource.marginal_cost_gbp_per_mwh,),
                periods, f"marginal cost {resource.asset_id}",
            )
            if np.any(costs < 0):
                raise DCNetworkInputError("Negative bids require a separately declared formulation")
            availability.append(available)
            marginal_costs.append(costs)
            for period in range(periods):
                index = layout.generation[resource_index, period]
                bounds[index] = (
                    0.0, resource.capacity_mw * model.period_hours * available[period]
                )
                objective[index] = costs[period]
        for storage_index, storage in enumerate(chronology.storage):
            if not 0 < storage.charge_efficiency <= 1 or not 0 < storage.discharge_efficiency <= 1:
                raise DCNetworkInputError(f"Storage {storage.asset_id} has invalid efficiency")
            if storage.initial_soc_mwh > storage.energy_capacity_mwh:
                raise DCNetworkInputError(f"Storage {storage.asset_id} initial SOC exceeds capacity")
            for period in range(periods):
                bounds[layout.charge[storage_index, period]] = (
                    0.0, storage.charge_power_mw * model.period_hours
                )
                bounds[layout.discharge[storage_index, period]] = (
                    0.0, storage.discharge_power_mw * model.period_hours
                )
                bounds[layout.soc[storage_index, period]] = (0.0, storage.energy_capacity_mwh)
                objective[layout.discharge[storage_index, period]] = (
                    storage.variable_degradation_gbp_per_mwh_discharged
                )
            if chronology.terminal_soc_rule != "free":
                target = (
                    storage.initial_soc_mwh
                    if chronology.terminal_soc_rule == "cyclic"
                    else float(chronology.terminal_soc_mwh_by_asset[storage.asset_id])
                )
                bounds[layout.soc[storage_index, periods - 1]] = (target, target)
        for bus_number, bus in enumerate(buses):
            for period in range(periods):
                demand = float(model.demand_mwh_by_bus[bus.bus_id][period])
                bounds[layout.blackout[bus_number, period]] = (
                    0.0, demand if chronology.allow_blackout else 0.0
                )
                objective[layout.blackout[bus_number, period]] = chronology.voll_gbp_per_mwh
                bounds[layout.angle[bus_number, period]] = (
                    (0.0, 0.0) if bus.is_reference else (-math.pi, math.pi)
                )
        for branch_number, branch in enumerate(branches):
            capacity = branch.thermal_rating_mw * branch.circuits if branch.in_service else 0.0
            for period in range(periods):
                bounds[layout.flow[branch_number, period]] = (-capacity, capacity)

        nodal_rows = periods * len(buses)
        storage_rows = periods * len(chronology.storage)
        angle_branches = [
            index for index, item in enumerate(branches)
            if item.in_service and item.branch_type in {"ac_line", "transformer"}
        ]
        flow_rows = periods * len(angle_branches)
        equality = lil_matrix((nodal_rows + storage_rows + flow_rows, layout.size))
        rhs = np.zeros(nodal_rows + storage_rows + flow_rows)
        row = 0
        for period in range(periods):
            for bus_number, bus in enumerate(buses):
                for resource_index, resource in enumerate(chronology.resources):
                    if mapping[resource.asset_id].bus_id == bus.bus_id:
                        equality[row, layout.generation[resource_index, period]] = 1
                for storage_index, storage in enumerate(chronology.storage):
                    if mapping[storage.asset_id].bus_id == bus.bus_id:
                        equality[row, layout.discharge[storage_index, period]] = 1
                        equality[row, layout.charge[storage_index, period]] = -1
                equality[row, layout.blackout[bus_number, period]] = 1
                for branch_index, branch in enumerate(branches):
                    if branch.from_bus == bus.bus_id:
                        equality[row, layout.flow[branch_index, period]] -= model.period_hours
                    if branch.to_bus == bus.bus_id:
                        equality[row, layout.flow[branch_index, period]] += model.period_hours
                rhs[row] = float(model.demand_mwh_by_bus[bus.bus_id][period])
                row += 1
        for storage_index, storage in enumerate(chronology.storage):
            for period in range(periods):
                equality[row, layout.soc[storage_index, period]] = 1
                equality[row, layout.charge[storage_index, period]] = -storage.charge_efficiency
                equality[row, layout.discharge[storage_index, period]] = 1 / storage.discharge_efficiency
                if period:
                    equality[row, layout.soc[storage_index, period - 1]] = -1
                else:
                    rhs[row] = storage.initial_soc_mwh
                row += 1
        for period in range(periods):
            for branch_index in angle_branches:
                branch = branches[branch_index]
                tap = branch.tap_ratio or 1.0
                susceptance = model.topology.base_mva / (float(branch.reactance_pu) * tap)
                phase = math.radians(branch.phase_shift_degrees or 0.0)
                equality[row, layout.flow[branch_index, period]] = 1
                equality[row, layout.angle[bus_index[branch.from_bus], period]] = -susceptance
                equality[row, layout.angle[bus_index[branch.to_bus], period]] = susceptance
                rhs[row] = -susceptance * phase
                row += 1
        matrix = csr_matrix(equality)
        solved = linprog(
            objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs",
            options={"primal_feasibility_tolerance": 1e-8, "dual_feasibility_tolerance": 1e-8},
        )
        if not solved.success or solved.status != 0:
            raise DCNetworkSolveError(
                f"HiGHS did not return an optimal DC solution ({solved.status}): {solved.message}"
            )
        solution = np.asarray(solved.x)
        residual = np.asarray(matrix @ solution - rhs)
        if np.max(np.abs(residual), initial=0.0) > TOLERANCE:
            raise DCNetworkSolveError("DC equality residual exceeds publication tolerance")

        generation = {
            resource.asset_id: float(sum(solution[layout.generation[index, p]] for p in range(periods)))
            for index, resource in enumerate(chronology.resources)
        }
        for index, storage in enumerate(chronology.storage):
            generation[storage.asset_id] = float(
                sum(solution[layout.discharge[index, p]] for p in range(periods))
            )
        incomes = {asset_id: 0.0 for asset_id in generation}
        network_periods = []
        summaries = []
        total_vre_available = total_vre_accepted = total_import = 0.0
        total_blackout = total_charge = total_discharge = 0.0
        storage_details = {storage.asset_id: {"charge": [], "discharge": [], "soc": []}
                           for storage in chronology.storage}
        nodal_duals = np.asarray(solved.eqlin.marginals[:nodal_rows]).reshape(periods, len(buses))
        for period in range(periods):
            injection = {bus.bus_id: 0.0 for bus in buses}
            withdrawal = {
                bus.bus_id: float(model.demand_mwh_by_bus[bus.bus_id][period])
                for bus in buses
            }
            blackout = {
                bus.bus_id: float(solution[layout.blackout[index, period]])
                for index, bus in enumerate(buses)
            }
            for bus in buses:
                withdrawal[bus.bus_id] -= blackout[bus.bus_id]
            vre_available = vre_accepted = imports = physical_cost = 0.0
            for index, resource in enumerate(chronology.resources):
                value = float(solution[layout.generation[index, period]])
                bus = mapping[resource.asset_id].bus_id
                injection[bus] += value
                price = float(nodal_duals[period, bus_index[bus]])
                incomes[resource.asset_id] += value * price
                physical_cost += value * marginal_costs[index][period]
                if resource.resource_type == "vre":
                    available = resource.capacity_mw * model.period_hours * availability[index][period]
                    vre_available += available
                    vre_accepted += value
                if resource.resource_type == "import":
                    imports += value
            charge_total = discharge_total = 0.0
            for index, storage in enumerate(chronology.storage):
                charge = float(solution[layout.charge[index, period]])
                discharge = float(solution[layout.discharge[index, period]])
                soc = float(solution[layout.soc[index, period]])
                bus = mapping[storage.asset_id].bus_id
                injection[bus] += discharge
                withdrawal[bus] += charge
                price = float(nodal_duals[period, bus_index[bus]])
                incomes[storage.asset_id] += discharge * price - charge * price
                physical_cost += discharge * storage.variable_degradation_gbp_per_mwh_discharged
                charge_total += charge
                discharge_total += discharge
                storage_details[storage.asset_id]["charge"].append(charge)
                storage_details[storage.asset_id]["discharge"].append(discharge)
                storage_details[storage.asset_id]["soc"].append(soc)
            blackout_total = sum(blackout.values())
            physical_cost += blackout_total * chronology.voll_gbp_per_mwh
            flows = {
                branch.branch_id: float(solution[layout.flow[index, period]])
                for index, branch in enumerate(branches)
            }
            angles = {
                bus.bus_id: float(solution[layout.angle[index, period]])
                for index, bus in enumerate(buses)
            }
            prices = {
                bus.bus_id: float(nodal_duals[period, index])
                for index, bus in enumerate(buses)
            }
            kcl = {}
            for bus in buses:
                net_export = sum(
                    flows[branch.branch_id]
                    * model.period_hours
                    * (1 if branch.from_bus == bus.bus_id else -1)
                    for branch in branches
                    if bus.bus_id in {branch.from_bus, branch.to_bus}
                )
                kcl[bus.bus_id] = injection[bus.bus_id] - withdrawal[bus.bus_id] - net_export
            network_periods.append(
                NetworkPeriodResult(
                    chronology.period_ids[period], injection, withdrawal, flows, blackout,
                    {
                        bus.bus_id: sum(
                            max(
                                resource.capacity_mw * model.period_hours * availability[index][period]
                                - solution[layout.generation[index, period]], 0.0,
                            )
                            for index, resource in enumerate(chronology.resources)
                            if resource.resource_type == "vre"
                            and mapping[resource.asset_id].bus_id == bus.bus_id
                        )
                        for bus in buses
                    },
                    voltage_angle_radians=angles, nodal_price_gbp_per_mwh=prices,
                    unsupported={
                        "network_losses_mwh": "Linear DC approximation is lossless",
                        "voltage_magnitude_pu": "Linear DC approximation does not model voltage magnitude",
                        "reactive_injection_mvarh": "Linear DC approximation does not model reactive power",
                    },
                    residuals={
                        "maximum_nodal_balance_mwh": max(abs(value) for value in kcl.values()),
                        "maximum_solver_equality": float(np.max(np.abs(residual), initial=0.0)),
                    },
                )
            )
            demand_total = sum(model.demand_mwh_by_bus[bus.bus_id][period] for bus in buses)
            served = demand_total - blackout_total
            weighted_price = (
                sum(prices[bus.bus_id] * model.demand_mwh_by_bus[bus.bus_id][period] for bus in buses)
                / demand_total if demand_total else 0.0
            )
            summaries.append(
                PeriodSummary(
                    chronology.period_ids[period], model_input.year, period, "dc_network",
                    demand_total, demand_total, sum(injection.values()), charge_total,
                    discharge_total, vre_available, vre_accepted,
                    max(vre_available - vre_accepted, 0.0), imports, weighted_price,
                    physical_cost, weighted_price * served, blackout_total,
                    max(abs(value) for value in kcl.values()),
                )
            )
            total_vre_available += vre_available
            total_vre_accepted += vre_accepted
            total_import += imports
            total_blackout += blackout_total
            total_charge += charge_total
            total_discharge += discharge_total
        network_output = NetworkPSMOutput(
            model.run_id, model.year, self.id, self.version, "domain.network.dc",
            "optimal", model.information_structure, tuple(network_periods),
            float(solved.fun), float(np.max(np.abs(residual), initial=0.0)),
            "GLOBAL_OPTIMUM_VALIDATED_LINEAR_PROGRAM",
            extensions={
                "formulation_id": FORMULATION_ID,
                "solver": "scipy.optimize.linprog/HiGHS",
                "storage": storage_details,
            },
        )
        validate_dc_solution(model, network_output)
        artifacts = _artifacts(model_input, model, network_output)
        return MarketYearResult(
            f"{model.run_id}:{model.year}:dc", model.year, self.id, self.version,
            generation, incomes, float(solved.fun), float(solved.fun), 0.0,
            float(sum(chronology.demand_mwh)), float(sum(generation.values())),
            total_blackout, max(total_vre_available - total_vre_accepted, 0.0),
            period_summaries=tuple(summaries), artifacts=artifacts,
            extensions={
                "network": network_output.to_dict(),
                "pricing_rule": "nodal_balance_lp_dual",
                "system_price_display": "demand_weighted_nodal_price",
                "boundary_import_mwh": total_import,
                "storage_charge_mwh": total_charge,
                "storage_discharge_mwh": total_discharge,
            },
        )


def validate_dc_solution(
    model: NetworkPSMInput, result: NetworkPSMOutput, *, tolerance: float = 1e-6
) -> dict[str, float]:
    model.validate()
    if result.solver_status != "optimal" or len(result.periods) != len(model.chronology.period_ids):
        raise ValueError("DC result is incomplete or not optimal")
    maximum_kcl = maximum_flow_relation = maximum_branch_violation = maximum_reference = 0.0
    branches = {item.branch_id: item for item in model.topology.branches}
    buses = {item.bus_id: item for item in model.topology.buses}
    for period in result.periods:
        for bus in buses:
            net_export = sum(
                flow * model.period_hours * (1 if branches[branch].from_bus == bus else -1)
                for branch, flow in period.branch_flow_mw.items()
                if bus in {branches[branch].from_bus, branches[branch].to_bus}
            )
            residual = period.nodal_injection_mwh[bus] - period.nodal_withdrawal_mwh[bus] - net_export
            maximum_kcl = max(maximum_kcl, abs(residual))
            if buses[bus].is_reference:
                maximum_reference = max(
                    maximum_reference, abs((period.voltage_angle_radians or {})[bus])
                )
        for branch_id, flow in period.branch_flow_mw.items():
            branch = branches[branch_id]
            rating = branch.thermal_rating_mw * branch.circuits if branch.in_service else 0.0
            maximum_branch_violation = max(maximum_branch_violation, max(abs(flow) - rating, 0.0))
            if branch.in_service and branch.branch_type in {"ac_line", "transformer"}:
                tap = branch.tap_ratio or 1.0
                expected = model.topology.base_mva / (float(branch.reactance_pu) * tap) * (
                    (period.voltage_angle_radians or {})[branch.from_bus]
                    - (period.voltage_angle_radians or {})[branch.to_bus]
                    - math.radians(branch.phase_shift_degrees or 0.0)
                )
                maximum_flow_relation = max(maximum_flow_relation, abs(flow - expected))
    storage = dict(result.extensions.get("storage") or {})
    maximum_soc = maximum_soc_bound = 0.0
    maximum_charge_power = maximum_discharge_power = maximum_terminal_soc = 0.0
    for asset in model.chronology.storage:
        values = storage.get(asset.asset_id)
        if not isinstance(values, Mapping):
            raise ValueError(f"DC result lacks storage chronology for {asset.asset_id}")
        charge_values = tuple(values.get("charge") or ())
        discharge_values = tuple(values.get("discharge") or ())
        soc_values = tuple(values.get("soc") or ())
        if not (
            len(charge_values) == len(discharge_values) == len(soc_values)
            == len(model.chronology.period_ids)
        ):
            raise ValueError(f"DC result has incomplete storage chronology for {asset.asset_id}")
        previous = asset.initial_soc_mwh
        for charge, discharge, soc in zip(charge_values, discharge_values, soc_values):
            charge = float(charge)
            discharge = float(discharge)
            soc = float(soc)
            expected = previous + charge * asset.charge_efficiency - discharge / asset.discharge_efficiency
            maximum_soc = max(maximum_soc, abs(soc - expected))
            maximum_soc_bound = max(
                maximum_soc_bound,
                max(-soc, soc - asset.energy_capacity_mwh, 0.0),
            )
            maximum_charge_power = max(
                maximum_charge_power,
                max(charge - asset.charge_power_mw * model.period_hours, -charge, 0.0),
            )
            maximum_discharge_power = max(
                maximum_discharge_power,
                max(discharge - asset.discharge_power_mw * model.period_hours, -discharge, 0.0),
            )
            previous = soc
        if model.chronology.terminal_soc_rule == "cyclic":
            target = asset.initial_soc_mwh
        elif model.chronology.terminal_soc_rule == "fixed":
            target = float(model.chronology.terminal_soc_mwh_by_asset[asset.asset_id])
        else:
            target = previous
        maximum_terminal_soc = max(maximum_terminal_soc, abs(previous - target))
    metrics = {
        "maximum_nodal_balance_mwh": maximum_kcl,
        "maximum_angle_flow_mw": maximum_flow_relation,
        "maximum_branch_bound_mw": maximum_branch_violation,
        "maximum_reference_angle": maximum_reference,
        "maximum_soc_residual_mwh": maximum_soc,
        "maximum_soc_bound_mwh": maximum_soc_bound,
        "maximum_charge_power_mwh": maximum_charge_power,
        "maximum_discharge_power_mwh": maximum_discharge_power,
        "maximum_terminal_soc_mwh": maximum_terminal_soc,
    }
    failures = {key: value for key, value in metrics.items() if value > tolerance}
    if failures:
        raise ValueError("DC validation failed: " + ", ".join(f"{key}={value}" for key, value in failures.items()))
    return metrics
