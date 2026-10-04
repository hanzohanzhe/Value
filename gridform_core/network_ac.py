"""Experimental AC feasibility checker for a declared active-power schedule.

This module is deliberately not an AC optimal-power-flow implementation.  It
solves the nonlinear polar power-flow equations, balances each island with one
declared slack asset, and rejects solutions that breach residual or equipment
gates.  Successful results therefore carry ``LOCAL_SOLUTION_VALIDATED`` only.
"""

from __future__ import annotations

import hashlib
import json
import math
import csv
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .network_contracts import NetworkPSMInput
from .v2.contracts import ArtifactReference, JsonContract, MarketYearResult, PSMInput, PeriodSummary


FORMULATION_ID = "value.ac-feasibility-polar-power-flow/v1"
INPUT_SCHEMA = "value.ac-feasibility-input/v1"
OUTPUT_SCHEMA = "value.ac-feasibility-output/v1"
DEFAULT_RESIDUAL_TOLERANCE = 1e-7
DEFAULT_EQUIPMENT_TOLERANCE = 1e-6


class ACNetworkInputError(ValueError):
    pass


class ACNetworkSolveError(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        self.status = status
        super().__init__(f"{status}: {message}")


@dataclass(frozen=True)
class ACGeneratorSpec(JsonContract):
    asset_id: str
    active_min_mw: float
    active_max_mw: float
    reactive_min_mvar: float
    reactive_max_mvar: float
    voltage_setpoint_pu: float
    slack_balancer: bool = False
    schema_version: str = "value.ac-generator-spec/v1"


@dataclass(frozen=True)
class ACPeriodResult(JsonContract):
    period_id: str
    status: str
    voltage_magnitude_pu: Mapping[str, float]
    voltage_angle_radians: Mapping[str, float]
    active_generation_mw_by_asset: Mapping[str, float]
    reactive_generation_mvar_by_bus: Mapping[str, float]
    branch_from_active_mw: Mapping[str, float]
    branch_from_reactive_mvar: Mapping[str, float]
    branch_to_active_mw: Mapping[str, float]
    branch_to_reactive_mvar: Mapping[str, float]
    active_loss_mw_by_branch: Mapping[str, float]
    residuals: Mapping[str, float]
    violations: Mapping[str, float]
    solver_metadata: Mapping[str, object]
    schema_version: str = "value.ac-period-result/v1"


@dataclass(frozen=True)
class ACFeasibilityOutput(JsonContract):
    run_id: str
    year: int
    module_id: str
    module_version: str
    formulation_id: str
    solver_status: str
    convergence_class: str
    periods: Sequence[ACPeriodResult]
    capabilities: Sequence[str]
    unsupported: Mapping[str, str]
    maximum_active_residual_mw: float
    maximum_reactive_residual_mvar: float
    maximum_equipment_violation: float
    schema_version: str = OUTPUT_SCHEMA
    solver: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _ACInput:
    network: NetworkPSMInput
    generator_specs: Sequence[ACGeneratorSpec]
    reactive_demand_mvar_by_bus: Mapping[str, Sequence[float]]
    active_schedule_mwh_by_asset: Mapping[str, Sequence[float]]
    initial_voltage: Mapping[str, Mapping[str, float]]
    residual_tolerance: float
    equipment_tolerance: float


def load_ac_data_from_pack(
    pack_root: Path,
    manifest: Mapping[str, object],
    network: NetworkPSMInput,
) -> NetworkPSMInput:
    """Attach the three required AC roles and optional initial state to a network input."""

    bindings = dict(manifest.get("bindings") or {})

    def path_for(role: str, *, required: bool = True) -> Path | None:
        binding = bindings.get(role)
        if not isinstance(binding, Mapping):
            if required:
                raise ACNetworkInputError(f"AC data role is not bound: {role}")
            return None
        path = (pack_root / str(binding.get("uri") or "")).resolve()
        try:
            path.relative_to(pack_root.resolve())
        except ValueError as exc:
            raise ACNetworkInputError(f"AC binding escapes pack root: {role}") from exc
        if not path.is_file():
            raise ACNetworkInputError(f"AC binding is missing: {role}")
        return path

    generator_path = path_for("value.network.ac.generators")
    generator_payload = json.loads(generator_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
    generator_specs = (
        generator_payload.get("generator_specs")
        if isinstance(generator_payload, Mapping)
        else generator_payload
    )
    if not isinstance(generator_specs, list):
        raise ACNetworkInputError("AC generator role must contain a generator_specs array")
    period_ids = tuple(network.chronology.period_ids)

    def read_long(role: str, id_field: str, value_field: str):
        path = path_for(role)
        result: dict[str, dict[str, float]] = {}
        with path.open("r", encoding="utf-8-sig", newline="") as handle:  # type: ignore[union-attr]
            for row in csv.DictReader(handle):
                identity = str(row.get(id_field) or "")
                period_id = str(row.get("period_id") or "")
                if not identity or period_id not in period_ids:
                    raise ACNetworkInputError(f"{role} has an unknown identity or period")
                values = result.setdefault(identity, {})
                if period_id in values:
                    raise ACNetworkInputError(f"{role} duplicates {identity}/{period_id}")
                values[period_id] = float(row[value_field])
        return {
            identity: tuple(values.get(period, float("nan")) for period in period_ids)
            for identity, values in result.items()
        }

    reactive = read_long(
        "value.network.ac.reactive-demand", "bus_id", "reactive_demand_mvar"
    )
    schedule = read_long(
        "value.network.ac.active-schedule", "asset_id", "active_schedule_mwh"
    )
    initial_path = path_for("value.network.ac.initial-voltage", required=False)
    initial = {}
    if initial_path is not None:
        value = json.loads(initial_path.read_text(encoding="utf-8"))
        initial = value.get("initial_voltage", value) if isinstance(value, Mapping) else value
        if not isinstance(initial, Mapping):
            raise ACNetworkInputError("AC initial-voltage role must be a JSON object")
    role_paths = [generator_path, path_for("value.network.ac.reactive-demand"), path_for("value.network.ac.active-schedule")]
    if initial_path is not None:
        role_paths.append(initial_path)
    source_hashes = {
        path.relative_to(pack_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in role_paths if path is not None
    }
    return replace(
        network,
        extensions={
            **dict(network.extensions),
            "generator_specs": generator_specs,
            "reactive_demand_mvar_by_bus": reactive,
            "active_schedule_mwh_by_asset": schedule,
            "initial_voltage": dict(initial),
            "ac_data_source_sha256": source_hashes,
            "ac_assumptions": {
                "transformer_control": "fixed_input_tap_and_phase",
                "storage_reactive_support": "not_supported",
                "slack_semantics": "one declared balancing asset per connected island",
                "initial_state": "flat_and_alternate_starts plus optional declared start",
            },
        },
    )


def _series(values: Sequence[float], periods: int, label: str) -> tuple[float, ...]:
    if len(values) == 1:
        result = tuple(float(values[0]) for _ in range(periods))
    elif len(values) == periods:
        result = tuple(float(value) for value in values)
    else:
        raise ACNetworkInputError(f"{label} has {len(values)} values; expected 1 or {periods}")
    if any(not math.isfinite(value) for value in result):
        raise ACNetworkInputError(f"{label} contains a non-finite value")
    return result


def _parse_input(model_input: PSMInput) -> _ACInput:
    raw = model_input.extensions.get("network_input")
    if not isinstance(raw, Mapping):
        raise ACNetworkInputError(
            "force-ac-feasibility requires extensions.network_input; DC fallback is forbidden"
        )
    network = NetworkPSMInput.from_dict(raw)
    network.validate()
    if network.capability != "domain.network.ac":
        raise ACNetworkInputError("AC feasibility requires domain.network.ac, not a DC input")
    if network.run_id != model_input.run_id or network.year != model_input.year:
        raise ACNetworkInputError("AC network input run/year identity mismatch")
    ext = dict(network.extensions)
    raw_specs = ext.get("generator_specs")
    raw_reactive = ext.get("reactive_demand_mvar_by_bus")
    raw_schedule = ext.get("active_schedule_mwh_by_asset")
    if not isinstance(raw_specs, Sequence) or isinstance(raw_specs, (str, bytes)):
        raise ACNetworkInputError("AC generator specifications are required")
    if not isinstance(raw_reactive, Mapping):
        raise ACNetworkInputError("AC reactive demand is required")
    if not isinstance(raw_schedule, Mapping):
        raise ACNetworkInputError("The declared AC active-power schedule is required")
    specs = tuple(ACGeneratorSpec.from_dict(item) for item in raw_specs)
    periods = len(network.chronology.period_ids)
    reactive = {
        str(bus): _series(values, periods, f"reactive demand {bus}")
        for bus, values in raw_reactive.items()
    }
    if set(reactive) != set(network.topology.bus_by_id()):
        raise ACNetworkInputError("Reactive demand must name every and only canonical AC bus")
    if any(value < 0 for values in reactive.values() for value in values):
        raise ACNetworkInputError("Reactive demand cannot be negative in this formulation")
    expected_assets = {
        item.asset_id for item in network.chronology.resources
    } | {item.asset_id for item in network.chronology.storage}
    schedule = {
        str(asset): _series(values, periods, f"active schedule {asset}")
        for asset, values in raw_schedule.items()
    }
    if set(schedule) != expected_assets:
        missing = sorted(expected_assets.difference(schedule))
        extra = sorted(set(schedule).difference(expected_assets))
        raise ACNetworkInputError(
            f"AC schedule asset identity mismatch; missing={missing}, extra={extra}"
        )
    by_asset = {item.asset_id: item for item in specs}
    resource_assets = {item.asset_id for item in network.chronology.resources}
    if set(by_asset) != resource_assets:
        raise ACNetworkInputError("Every AC resource requires exactly one generator specification")
    if len(by_asset) != len(specs):
        raise ACNetworkInputError("AC generator specifications contain duplicate asset IDs")
    mappings = network.topology.mapping_by_asset()
    by_bus: dict[str, list[ACGeneratorSpec]] = {item.bus_id: [] for item in network.topology.buses}
    for spec in specs:
        if not (
            math.isfinite(spec.active_min_mw)
            and math.isfinite(spec.active_max_mw)
            and 0 <= spec.active_min_mw <= spec.active_max_mw
            and math.isfinite(spec.reactive_min_mvar)
            and math.isfinite(spec.reactive_max_mvar)
            and spec.reactive_min_mvar <= spec.reactive_max_mvar
            and math.isfinite(spec.voltage_setpoint_pu)
        ):
            raise ACNetworkInputError(f"Invalid AC limits for {spec.asset_id}")
        bus = mappings[spec.asset_id].bus_id
        by_bus[bus].append(spec)
    for bus in network.topology.buses:
        specs_at_bus = by_bus[bus.bus_id]
        if bus.bus_type in {"slack", "pv"} and not specs_at_bus:
            raise ACNetworkInputError(f"AC {bus.bus_type} bus {bus.bus_id} has no generator")
        if bus.bus_type == "pq" and specs_at_bus:
            raise ACNetworkInputError(
                f"Generators at PQ bus {bus.bus_id} require an explicit reactive-control mode"
            )
        for spec in specs_at_bus:
            if not bus.voltage_min_pu <= spec.voltage_setpoint_pu <= bus.voltage_max_pu:  # type: ignore[operator]
                raise ACNetworkInputError(f"Voltage setpoint for {spec.asset_id} is outside bus limits")
        if specs_at_bus and max(item.voltage_setpoint_pu for item in specs_at_bus) - min(
            item.voltage_setpoint_pu for item in specs_at_bus
        ) > 1e-10:
            raise ACNetworkInputError(f"Generators at {bus.bus_id} have conflicting voltage setpoints")
    for island in network.topology.islands():
        slack_specs = [
            spec for bus in island for spec in by_bus[bus] if spec.slack_balancer
        ]
        if len(slack_specs) != 1:
            raise ACNetworkInputError(
                f"Every AC island requires exactly one slack-balancing asset; {island} has {len(slack_specs)}"
            )
        slack_bus = mappings[slack_specs[0].asset_id].bus_id
        if network.topology.bus_by_id()[slack_bus].bus_type != "slack":
            raise ACNetworkInputError(f"Slack asset {slack_specs[0].asset_id} is not on a slack bus")
    initial = ext.get("initial_voltage") or {}
    if not isinstance(initial, Mapping):
        raise ACNetworkInputError("AC initial voltage must be an object")
    residual_tolerance = float(ext.get("residual_tolerance", DEFAULT_RESIDUAL_TOLERANCE))
    equipment_tolerance = float(ext.get("equipment_tolerance", DEFAULT_EQUIPMENT_TOLERANCE))
    if residual_tolerance <= 0 or equipment_tolerance <= 0:
        raise ACNetworkInputError("AC tolerances must be positive")
    return _ACInput(
        network, specs, reactive, schedule,
        {str(key): dict(value) for key, value in initial.items()},  # type: ignore[arg-type]
        residual_tolerance, equipment_tolerance,
    )


def _ybus(model: _ACInput):
    topology = model.network.topology
    buses = tuple(topology.buses)
    index = {item.bus_id: position for position, item in enumerate(buses)}
    matrix = np.zeros((len(buses), len(buses)), dtype=complex)
    branch_terms: dict[str, tuple[complex, complex, complex, complex]] = {}
    for branch in topology.branches:
        if not branch.in_service:
            branch_terms[branch.branch_id] = (0j, 0j, 0j, 0j)
            continue
        impedance = complex(float(branch.resistance_pu), float(branch.reactance_pu))
        series = 1.0 / impedance
        charging = 1j * float(branch.charging_susceptance_pu or 0.0) / 2.0
        tap = float(branch.tap_ratio or 1.0) * np.exp(
            1j * math.radians(float(branch.phase_shift_degrees or 0.0))
        )
        yff = (series + charging) / (tap * np.conjugate(tap))
        yft = -series / np.conjugate(tap)
        ytf = -series / tap
        ytt = series + charging
        f, t = index[branch.from_bus], index[branch.to_bus]
        matrix[f, f] += yff
        matrix[f, t] += yft
        matrix[t, f] += ytf
        matrix[t, t] += ytt
        branch_terms[branch.branch_id] = (yff, yft, ytf, ytt)
    for position, bus in enumerate(buses):
        matrix[position, position] += complex(
            bus.shunt_conductance_pu, bus.shunt_susceptance_pu
        )
    return matrix, branch_terms


def _write_artifact(model_input: PSMInput, output: ACFeasibilityOutput):
    raw = model_input.extensions.get("artifact_directory")
    if not raw:
        return ()
    root = Path(str(raw)).resolve() / "ac"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"ac-feasibility-{model_input.year}.json"
    content = json.dumps(output.to_dict(), indent=2).encode("utf-8")
    path.write_bytes(content)
    return (
        ArtifactReference(
            f"ac-feasibility/{model_input.year}", "ac-feasibility-result",
            f"solver/ac/{path.name}", "application/json",
            hashlib.sha256(content).hexdigest(), len(content),
        ),
    )


class ReferenceACFeasibilityPSM:
    id = "value-reference-ac-feasibility"
    version = "0.1.0"

    def run(self, model_input: PSMInput) -> MarketYearResult:
        # AC feasibility is optional and must not make the default
        # single-node runtime depend on SciPy merely because its manifest is
        # present in the catalogue.  Selection preflight checks the solver
        # capability; direct callers still fail with a domain-specific error.
        try:
            from scipy.optimize import least_squares
        except ModuleNotFoundError as exc:
            raise ACNetworkSolveError(
                "MISSING_SOLVER_CAPABILITY",
                "the experimental AC feasibility module requires the optional SciPy solver extra",
            ) from exc
        model = _parse_input(model_input)
        network = model.network
        topology = network.topology
        buses = tuple(topology.buses)
        bus_index = {item.bus_id: index for index, item in enumerate(buses)}
        mapping = topology.mapping_by_asset()
        resources = {item.asset_id: item for item in network.chronology.resources}
        stores = {item.asset_id: item for item in network.chronology.storage}
        specs = {item.asset_id: item for item in model.generator_specs}
        specs_by_bus = {
            bus.bus_id: [item for item in model.generator_specs if mapping[item.asset_id].bus_id == bus.bus_id]
            for bus in buses
        }
        ybus, branch_terms = _ybus(model)
        non_reference = [index for index, bus in enumerate(buses) if bus.bus_type != "slack"]
        pq = [index for index, bus in enumerate(buses) if bus.bus_type == "pq"]
        fixed_vm = np.ones(len(buses))
        for index, bus in enumerate(buses):
            if bus.bus_type in {"slack", "pv"}:
                fixed_vm[index] = specs_by_bus[bus.bus_id][0].voltage_setpoint_pu

        period_results: list[ACPeriodResult] = []
        summaries: list[PeriodSummary] = []
        generation_totals = {asset: 0.0 for asset in resources}
        storage_discharge_totals = {asset: 0.0 for asset in stores}
        total_cost = total_loss_mwh = total_vre_available = total_vre_accepted = 0.0
        total_import = total_charge = total_discharge = 0.0
        max_p_residual = max_q_residual = max_violation = 0.0
        period_hours = network.period_hours
        periods = len(network.chronology.period_ids)

        for period in range(periods):
            p_fixed = np.zeros(len(buses))
            q_spec = np.array(
                [-model.reactive_demand_mvar_by_bus[bus.bus_id][period] for bus in buses],
                dtype=float,
            )
            active_by_asset: dict[str, float] = {}
            slack_assets: dict[int, str] = {}
            for asset, resource in resources.items():
                scheduled_mwh = model.active_schedule_mwh_by_asset[asset][period]
                scheduled_mw = scheduled_mwh / period_hours
                if scheduled_mw < -model.equipment_tolerance:
                    raise ACNetworkInputError(f"Generator schedule is negative for {asset}")
                available = _series(resource.availability, periods, f"availability {asset}")[period]
                if scheduled_mw > resource.capacity_mw * available + model.equipment_tolerance:
                    raise ACNetworkInputError(f"Generator schedule exceeds availability for {asset}")
                bus = bus_index[mapping[asset].bus_id]
                if specs[asset].slack_balancer:
                    slack_assets[bus] = asset
                    active_by_asset[asset] = scheduled_mw
                else:
                    p_fixed[bus] += scheduled_mw
                    active_by_asset[asset] = scheduled_mw
            storage_net_mw: dict[str, float] = {}
            for asset in stores:
                value = model.active_schedule_mwh_by_asset[asset][period] / period_hours
                storage_net_mw[asset] = value
                p_fixed[bus_index[mapping[asset].bus_id]] += value
            demand_mw = np.array(
                [network.demand_mwh_by_bus[bus.bus_id][period] / period_hours for bus in buses],
                dtype=float,
            )
            p_fixed -= demand_mw

            def unpack(vector: np.ndarray):
                theta = np.zeros(len(buses))
                vm = fixed_vm.copy()
                theta[non_reference] = vector[: len(non_reference)]
                vm[pq] = vector[len(non_reference):]
                return vm, theta

            def mismatch(vector: np.ndarray):
                vm, theta = unpack(vector)
                voltage = vm * np.exp(1j * theta)
                injection = voltage * np.conjugate(ybus @ voltage) * topology.base_mva
                return np.concatenate(
                    ((injection.real - p_fixed)[non_reference], (injection.imag - q_spec)[pq])
                )

            lower = np.concatenate(
                (np.full(len(non_reference), -math.pi), np.array([buses[i].voltage_min_pu for i in pq]))
            )
            upper = np.concatenate(
                (np.full(len(non_reference), math.pi), np.array([buses[i].voltage_max_pu for i in pq]))
            )
            flat = np.concatenate((np.zeros(len(non_reference)), np.ones(len(pq))))
            alternate = np.concatenate(
                (
                    np.linspace(0.01, 0.03, len(non_reference)) if non_reference else np.array([]),
                    np.array([(buses[i].voltage_min_pu + buses[i].voltage_max_pu) / 2 for i in pq]),
                )
            )
            starts = [np.clip(flat, lower, upper), np.clip(alternate, lower, upper)]
            if model.initial_voltage:
                declared = flat.copy()
                for position, index in enumerate(non_reference):
                    declared[position] = math.radians(
                        float(model.initial_voltage.get(buses[index].bus_id, {}).get("angle_degrees", 0.0))
                    )
                for position, index in enumerate(pq, start=len(non_reference)):
                    declared[position] = float(
                        model.initial_voltage.get(buses[index].bus_id, {}).get("magnitude_pu", 1.0)
                    )
                starts.append(np.clip(declared, lower, upper))
            attempts = [
                least_squares(
                    mismatch, start, bounds=(lower, upper), xtol=1e-12, ftol=1e-12,
                    gtol=1e-12, max_nfev=2_000,
                )
                for start in starts
            ]
            residuals = [float(np.max(np.abs(item.fun), initial=0.0)) for item in attempts]
            acceptable = [
                (residual, index, attempt)
                for index, (residual, attempt) in enumerate(zip(residuals, attempts))
                if attempt.success and residual <= model.residual_tolerance
            ]
            if not acceptable:
                status = "ITERATION_LIMIT" if any(item.status == 0 for item in attempts) else "NUMERICAL_FAILURE"
                raise ACNetworkSolveError(status, f"all AC starts failed residual gate: {residuals}")
            _, selected_index, solved = min(acceptable, key=lambda item: item[0])
            vm, theta = unpack(solved.x)
            voltage = vm * np.exp(1j * theta)
            injection = voltage * np.conjugate(ybus @ voltage) * topology.base_mva
            converged_voltages = [
                unpack(item.x) for residual, item in zip(residuals, attempts)
                if item.success and residual <= model.residual_tolerance
            ]
            start_spread = max(
                (
                    max(
                        float(np.max(np.abs(other_vm - vm), initial=0.0)),
                        float(np.max(np.abs(other_theta - theta), initial=0.0)),
                    )
                    for other_vm, other_theta in converged_voltages
                ),
                default=0.0,
            )
            if start_spread > 1e-5:
                raise ACNetworkSolveError(
                    "AMBIGUOUS_LOCAL_SOLUTION",
                    f"flat/alternate starts disagree by {start_spread}",
                )
            jacobian_condition = float(np.linalg.cond(solved.jac)) if solved.jac.size else 0.0
            if not math.isfinite(jacobian_condition) or jacobian_condition > 1e12:
                raise ACNetworkSolveError(
                    "NUMERICAL_FAILURE", f"AC Jacobian condition is {jacobian_condition}"
                )

            for bus, asset in slack_assets.items():
                actual = float(injection.real[bus] - p_fixed[bus])
                active_by_asset[asset] = actual
            p_residual = float(np.max(np.abs(mismatch(solved.x)[: len(non_reference)]), initial=0.0))
            q_residual = float(np.max(np.abs(mismatch(solved.x)[len(non_reference):]), initial=0.0))
            q_generation = {
                bus.bus_id: float(injection.imag[index] + model.reactive_demand_mvar_by_bus[bus.bus_id][period])
                if specs_by_bus[bus.bus_id] else 0.0
                for index, bus in enumerate(buses)
            }
            voltage_violation = max(
                max(
                    float(bus.voltage_min_pu) - vm[index],
                    vm[index] - float(bus.voltage_max_pu),
                    0.0,
                )
                for index, bus in enumerate(buses)
            )
            q_violation = 0.0
            for bus in buses:
                at_bus = specs_by_bus[bus.bus_id]
                if not at_bus:
                    continue
                low = sum(item.reactive_min_mvar for item in at_bus)
                high = sum(item.reactive_max_mvar for item in at_bus)
                q_violation = max(q_violation, low - q_generation[bus.bus_id], q_generation[bus.bus_id] - high)
            p_limit_violation = 0.0
            for asset, value in active_by_asset.items():
                spec = specs[asset]
                resource = resources[asset]
                physical_max = resource.capacity_mw * _series(
                    resource.availability, periods, f"availability {asset}"
                )[period]
                p_limit_violation = max(
                    p_limit_violation,
                    spec.active_min_mw - value,
                    value - min(spec.active_max_mw, physical_max),
                )
            branch_from_p: dict[str, float] = {}
            branch_from_q: dict[str, float] = {}
            branch_to_p: dict[str, float] = {}
            branch_to_q: dict[str, float] = {}
            losses: dict[str, float] = {}
            branch_violation = 0.0
            for branch in topology.branches:
                f, t = bus_index[branch.from_bus], bus_index[branch.to_bus]
                yff, yft, ytf, ytt = branch_terms[branch.branch_id]
                if branch.in_service:
                    s_from = voltage[f] * np.conjugate(yff * voltage[f] + yft * voltage[t]) * topology.base_mva
                    s_to = voltage[t] * np.conjugate(ytf * voltage[f] + ytt * voltage[t]) * topology.base_mva
                else:
                    s_from = s_to = 0j
                branch_from_p[branch.branch_id] = float(s_from.real)
                branch_from_q[branch.branch_id] = float(s_from.imag)
                branch_to_p[branch.branch_id] = float(s_to.real)
                branch_to_q[branch.branch_id] = float(s_to.imag)
                losses[branch.branch_id] = float(s_from.real + s_to.real)
                rating = float(branch.apparent_power_rating_mva or 0.0) * branch.circuits
                branch_violation = max(
                    branch_violation, abs(s_from) - rating, abs(s_to) - rating, 0.0
                )
            equipment_violation = max(
                voltage_violation, q_violation, p_limit_violation, branch_violation, 0.0
            )
            if equipment_violation > model.equipment_tolerance:
                raise ACNetworkSolveError(
                    "INFEASIBLE_EQUIPMENT_LIMIT",
                    f"maximum violation is {equipment_violation}",
                )
            loss_mw = sum(losses.values())
            source_mw = sum(active_by_asset.values()) + sum(max(value, 0.0) for value in storage_net_mw.values())
            charge_mw = sum(max(-value, 0.0) for value in storage_net_mw.values())
            identity = source_mw - charge_mw - float(demand_mw.sum()) - loss_mw
            if abs(identity) > model.residual_tolerance * max(1, len(buses)):
                raise ACNetworkSolveError("NUMERICAL_FAILURE", f"real-power loss identity is {identity}")

            for asset, value in active_by_asset.items():
                generation_totals[asset] += value * period_hours
            for asset, value in storage_net_mw.items():
                storage_discharge_totals[asset] += max(value, 0.0) * period_hours
            period_cost = 0.0
            vre_available = vre_accepted = imports = 0.0
            for asset, resource in resources.items():
                output_mwh = active_by_asset[asset] * period_hours
                costs = resource.marginal_cost_profile_gbp_per_mwh or (
                    resource.marginal_cost_gbp_per_mwh,
                )
                cost = _series(costs, periods, f"marginal cost {asset}")[period]
                period_cost += output_mwh * cost
                if resource.resource_type == "vre":
                    available = resource.capacity_mw * _series(
                        resource.availability, periods, f"availability {asset}"
                    )[period] * period_hours
                    vre_available += available
                    vre_accepted += output_mwh
                if resource.resource_type == "import":
                    imports += output_mwh
            for asset, store in stores.items():
                discharge = max(storage_net_mw[asset], 0.0) * period_hours
                period_cost += discharge * store.variable_degradation_gbp_per_mwh_discharged
            total_cost += period_cost
            total_loss_mwh += loss_mw * period_hours
            total_vre_available += vre_available
            total_vre_accepted += vre_accepted
            total_import += imports
            total_charge += charge_mw * period_hours
            total_discharge += sum(max(value, 0.0) for value in storage_net_mw.values()) * period_hours
            max_p_residual = max(max_p_residual, p_residual, abs(identity))
            max_q_residual = max(max_q_residual, q_residual)
            max_violation = max(max_violation, equipment_violation)
            period_results.append(
                ACPeriodResult(
                    network.chronology.period_ids[period], "CONVERGED",
                    {bus.bus_id: float(vm[index]) for index, bus in enumerate(buses)},
                    {bus.bus_id: float(theta[index]) for index, bus in enumerate(buses)},
                    active_by_asset, q_generation, branch_from_p, branch_from_q,
                    branch_to_p, branch_to_q, losses,
                    {
                        "active_balance_mw": p_residual,
                        "reactive_balance_mvar": q_residual,
                        "real_power_loss_identity_mw": abs(identity),
                    },
                    {
                        "voltage_pu": voltage_violation,
                        "reactive_limit_mvar": max(q_violation, 0.0),
                        "active_limit_mw": max(p_limit_violation, 0.0),
                        "branch_mva": branch_violation,
                    },
                    {
                        "backend": "scipy.optimize.least_squares",
                        "selected_start": selected_index,
                        "attempt_residuals": residuals,
                        "start_solution_spread": start_spread,
                        "jacobian_condition": jacobian_condition,
                        "nfev": int(solved.nfev),
                    },
                )
            )
            demand_mwh = float(demand_mw.sum() * period_hours)
            supply_mwh = source_mw * period_hours
            summaries.append(
                PeriodSummary(
                    network.chronology.period_ids[period], network.year, period,
                    "ac_feasibility", demand_mwh, demand_mwh, supply_mwh,
                    charge_mw * period_hours,
                    sum(max(value, 0.0) for value in storage_net_mw.values()) * period_hours,
                    vre_available, vre_accepted, max(vre_available - vre_accepted, 0.0),
                    imports, 0.0, period_cost, 0.0, 0.0, identity * period_hours,
                )
            )

        output = ACFeasibilityOutput(
            network.run_id, network.year, self.id, self.version, FORMULATION_ID,
            "CONVERGED", "LOCAL_SOLUTION_VALIDATED", tuple(period_results),
            (
                "domain.network.ac", "domain.network.losses",
                "domain.network.reactive-balance", "domain.network.voltage-magnitude",
                "domain.network.fixed-transformer-taps",
            ),
            {
                "ac_opf": "NOT_EVALUATED: this module checks feasibility of a declared active schedule",
                "global_optimum": "NOT_CLAIMED: nonlinear local power-flow convergence has no global certificate",
                "contingencies": "NOT_EVALUATED",
                "discrete_controls": "NOT_EVALUATED; taps are fixed inputs",
                "storage_reactive_support": "NOT_SUPPORTED; storage contributes declared real power only",
                "nodal_prices": "NOT_APPLICABLE to a feasibility check",
            },
            max_p_residual, max_q_residual, max_violation,
            solver={
                "backend": "scipy.optimize.least_squares",
                "formulation": "polar Newton trust-region least squares",
                "licence": "SciPy BSD-3-Clause",
                "residual_tolerance": model.residual_tolerance,
                "equipment_tolerance": model.equipment_tolerance,
            },
        )
        validate_ac_result(model, output)
        artifacts = _write_artifact(model_input, output)
        generation = {**generation_totals, **storage_discharge_totals}
        return MarketYearResult(
            f"{network.run_id}:{network.year}:ac-feasibility", network.year,
            self.id, self.version, generation, {asset: 0.0 for asset in generation},
            total_cost, total_cost, 0.0, sum(network.chronology.demand_mwh),
            sum(generation.values()), 0.0,
            max(total_vre_available - total_vre_accepted, 0.0),
            period_summaries=tuple(summaries), artifacts=artifacts,
            extensions={
                "ac": output.to_dict(),
                "network_losses_mwh": total_loss_mwh,
                "boundary_import_mwh": total_import,
                "storage_charge_mwh": total_charge,
                "storage_discharge_mwh": total_discharge,
                "pricing_rule": "not_applicable_ac_feasibility",
            },
        )


def validate_ac_result(
    model: _ACInput, result: ACFeasibilityOutput
) -> dict[str, float]:
    if result.solver_status != "CONVERGED":
        raise ValueError("AC result is not converged")
    if result.convergence_class != "LOCAL_SOLUTION_VALIDATED":
        raise ValueError("AC result overstates or misstates its convergence class")
    if "domain.network.ac" not in result.capabilities:
        raise ValueError("AC result omits its AC capability")
    if len(result.periods) != len(model.network.chronology.period_ids):
        raise ValueError("AC result has incomplete chronology")
    maximum_p = maximum_q = maximum_equipment = maximum_loss_error = 0.0
    for period in result.periods:
        if period.status != "CONVERGED":
            raise ValueError("AC period is not converged")
        if "active_balance_mw" not in period.residuals or "reactive_balance_mvar" not in period.residuals:
            raise ValueError("AC result omits active or reactive balance evidence")
        maximum_p = max(maximum_p, abs(float(period.residuals["active_balance_mw"])))
        maximum_q = max(maximum_q, abs(float(period.residuals["reactive_balance_mvar"])))
        maximum_equipment = max(
            maximum_equipment, *(max(float(value), 0.0) for value in period.violations.values())
        )
        for branch in model.network.topology.branches:
            calculated = (
                period.branch_from_active_mw[branch.branch_id]
                + period.branch_to_active_mw[branch.branch_id]
            )
            maximum_loss_error = max(
                maximum_loss_error,
                abs(calculated - period.active_loss_mw_by_branch[branch.branch_id]),
            )
        for bus in model.network.topology.buses:
            vm = period.voltage_magnitude_pu[bus.bus_id]
            maximum_equipment = max(
                maximum_equipment,
                float(bus.voltage_min_pu) - vm,
                vm - float(bus.voltage_max_pu),
            )
    metrics = {
        "maximum_active_residual_mw": maximum_p,
        "maximum_reactive_residual_mvar": maximum_q,
        "maximum_equipment_violation": maximum_equipment,
        "maximum_loss_accounting_error_mw": maximum_loss_error,
    }
    if maximum_p > model.residual_tolerance or maximum_q > model.residual_tolerance:
        raise ValueError(f"AC balance validation failed: {metrics}")
    if maximum_equipment > model.equipment_tolerance:
        raise ValueError(f"AC equipment validation failed: {metrics}")
    if maximum_loss_error > model.residual_tolerance:
        raise ValueError(f"AC loss validation failed: {metrics}")
    return metrics
