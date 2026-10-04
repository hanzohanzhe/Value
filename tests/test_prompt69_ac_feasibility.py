from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.network_ac import (
    ACFeasibilityOutput,
    ACNetworkInputError,
    ACNetworkSolveError,
    ReferenceACFeasibilityPSM,
    _parse_input,
    load_ac_data_from_pack,
    validate_ac_result,
)
from gridform_core.network_contracts import (
    AssetBusMapping,
    NetworkBranch,
    NetworkBus,
    NetworkPSMInput,
    NetworkTopology,
)
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
)
from gridform_core.v2.module_manifest import workspace_registry
from gridform_validation.network_ac_oracle import solve_rectangular_ac_oracle


ROOT = Path(__file__).resolve().parents[1]
BASE_ROLES = (
    "value.network.buses", "value.network.branches",
    "value.network.asset-map", "value.network.nodal-demand",
)
AC_ROLES = (
    "value.network.ac.generators", "value.network.ac.reactive-demand",
    "value.network.ac.active-schedule",
)
MODULES = {
    "psm": "value-reference-ac-feasibility",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "transition": "value-annual-state-transition",
}


def _bus(bus_id: str, kind: str, *, setpoint: float = 1.0):
    return NetworkBus(
        bus_id, 400.0, bus_id,
        reference_eligible=kind == "slack", is_reference=kind == "slack",
        voltage_min_pu=0.9, voltage_max_pu=1.1, bus_type=kind,
    )


def _branch(
    branch_id: str,
    from_bus: str,
    to_bus: str,
    *,
    r: float = 0.01,
    x: float = 0.1,
    b: float = 0.0,
    rating: float = 200.0,
    tap: float | None = None,
    phase: float | None = None,
):
    return NetworkBranch(
        branch_id, from_bus, to_bus,
        "transformer" if tap is not None else "ac_line", True, rating,
        reactance_pu=x, resistance_pu=r, charging_susceptance_pu=b,
        tap_ratio=tap, phase_shift_degrees=phase,
        apparent_power_rating_mva=rating,
    )


def _resource(asset_id: str, cost: float, capacity: float):
    return DispatchResource(asset_id, "thermal", "thermal", capacity, cost, (1.0,))


def _model(
    *,
    buses,
    branches,
    demand,
    reactive,
    resources,
    resource_bus,
    specs,
    schedule,
    periods: int = 1,
    artifact_root: Path | None = None,
):
    nodal = {
        bus: tuple(float(value) for value in (values if isinstance(values, (list, tuple)) else [values] * periods))
        for bus, values in demand.items()
    }
    chronology = ChronologicalPSMData(
        tuple(f"p{period}" for period in range(periods)),
        tuple(sum(values[period] for values in nodal.values()) for period in range(periods)),
        tuple(resources), (), 10_000.0,
    )
    topology = NetworkTopology(
        tuple(buses), tuple(branches),
        tuple(AssetBusMapping(asset, bus, "generator") for asset, bus in resource_bus.items()),
        100.0,
    )
    reactive_series = {
        bus: tuple(float(value) for value in (values if isinstance(values, (list, tuple)) else [values] * periods))
        for bus, values in reactive.items()
    }
    schedule_series = {
        asset: tuple(float(value) for value in (values if isinstance(values, (list, tuple)) else [values] * periods))
        for asset, values in schedule.items()
    }
    network = NetworkPSMInput(
        "prompt69", 2025, 1.0, chronology, topology, nodal,
        "domain.network.ac", "declared_schedule_ac_feasibility",
        extensions={
            "generator_specs": specs,
            "reactive_demand_mvar_by_bus": reactive_series,
            "active_schedule_mwh_by_asset": schedule_series,
            "initial_voltage": {bus.bus_id: {"magnitude_pu": 1.0, "angle_degrees": 0.0} for bus in buses},
            "residual_tolerance": 1e-7,
            "equipment_tolerance": 1e-6,
        },
    )
    network.validate()
    extensions = {"network_input": network.to_dict()}
    if artifact_root is not None:
        extensions["artifact_directory"] = str(artifact_root / "solver")
    wrapped = PSMInput(
        network.run_id, network.year, "prompt69-fixture", OperatingState(2025, (), ()),
        1.0, {}, chronology=chronology, extensions=extensions,
    )
    return network, wrapped


def _two_bus(periods: int = 1, *, rating: float = 200.0, q_limit: float = 100.0, artifact_root=None):
    buses = [_bus("A", "slack"), _bus("B", "pq")]
    return _model(
        buses=buses,
        branches=[_branch("AB", "A", "B", rating=rating)],
        demand={"A": 0.0, "B": 50.0},
        reactive={"A": 0.0, "B": 20.0},
        resources=[_resource("slack", 50.0, 150.0)],
        resource_bus={"slack": "A"},
        specs=[{
            "asset_id": "slack", "active_min_mw": 0.0, "active_max_mw": 150.0,
            "reactive_min_mvar": -q_limit, "reactive_max_mvar": q_limit,
            "voltage_setpoint_pu": 1.0, "slack_balancer": True,
        }],
        schedule={"slack": 50.0}, periods=periods, artifact_root=artifact_root,
    )


def _oracle_case(network: NetworkPSMInput, *, period: int = 0):
    specs = {item["asset_id"]: item for item in network.extensions["generator_specs"]}
    mappings = network.topology.mapping_by_asset()
    p_spec = {
        bus.bus_id: -network.demand_mwh_by_bus[bus.bus_id][period] / network.period_hours
        for bus in network.topology.buses
    }
    q_spec = {
        bus.bus_id: -network.extensions["reactive_demand_mvar_by_bus"][bus.bus_id][period]
        for bus in network.topology.buses
    }
    voltage = {}
    for resource in network.chronology.resources:
        spec = specs[resource.asset_id]
        bus = mappings[resource.asset_id].bus_id
        voltage[bus] = spec["voltage_setpoint_pu"]
        if not spec["slack_balancer"]:
            p_spec[bus] += network.extensions["active_schedule_mwh_by_asset"][resource.asset_id][period]
    return {
        "buses": [item.to_dict() for item in network.topology.buses],
        "branches": [item.to_dict() for item in network.topology.branches],
        "base_mva": network.topology.base_mva,
        "p_spec_mw": p_spec,
        "q_spec_mvar": q_spec,
        "voltage_setpoint_pu": voltage,
    }


class Prompt69ACFeasibilityTests(unittest.TestCase):
    def test_two_bus_matches_independent_rectangular_oracle_and_accounts_losses(self):
        network, wrapped = _two_bus()
        result = ReferenceACFeasibilityPSM().run(wrapped)
        output = ACFeasibilityOutput.from_dict(result.extensions["ac"])
        oracle = solve_rectangular_ac_oracle(_oracle_case(network))
        self.assertTrue(oracle["success"], oracle)
        period = output.periods[0]
        for bus in ("A", "B"):
            self.assertAlmostEqual(period.voltage_magnitude_pu[bus], oracle["voltage_magnitude_pu"][bus], places=7)
            self.assertAlmostEqual(period.voltage_angle_radians[bus], oracle["voltage_angle_radians"][bus], places=7)
        self.assertGreater(result.extensions["network_losses_mwh"], 0.0)
        self.assertEqual(output.convergence_class, "LOCAL_SOLUTION_VALIDATED")
        self.assertIn("NOT_EVALUATED", output.unsupported["ac_opf"])
        self.assertIn("NOT_CLAIMED", output.unsupported["global_optimum"])
        validate_ac_result(_parse_input(wrapped), output)

    def test_meshed_pv_case_fixed_transformer_tap_and_independent_oracle(self):
        buses = [_bus("A", "slack"), _bus("B", "pv"), _bus("C", "pq")]
        network, wrapped = _model(
            buses=buses,
            branches=[
                _branch("AB", "A", "B", r=0.01, x=0.08, b=0.02, tap=1.02),
                _branch("BC", "B", "C", r=0.015, x=0.10, b=0.02),
                _branch("AC", "A", "C", r=0.02, x=0.12, b=0.01),
            ],
            demand={"A": 0.0, "B": 0.0, "C": 100.0},
            reactive={"A": 0.0, "B": 0.0, "C": 30.0},
            resources=[_resource("slack", 50.0, 200.0), _resource("pv", 40.0, 100.0)],
            resource_bus={"slack": "A", "pv": "B"},
            specs=[
                {"asset_id": "slack", "active_min_mw": 0.0, "active_max_mw": 200.0, "reactive_min_mvar": -150.0, "reactive_max_mvar": 150.0, "voltage_setpoint_pu": 1.0, "slack_balancer": True},
                {"asset_id": "pv", "active_min_mw": 0.0, "active_max_mw": 100.0, "reactive_min_mvar": -100.0, "reactive_max_mvar": 100.0, "voltage_setpoint_pu": 1.02, "slack_balancer": False},
            ],
            schedule={"slack": 50.0, "pv": 50.0},
        )
        result = ReferenceACFeasibilityPSM().run(wrapped)
        output = ACFeasibilityOutput.from_dict(result.extensions["ac"])
        oracle = solve_rectangular_ac_oracle(_oracle_case(network))
        self.assertTrue(oracle["success"], oracle)
        for bus in ("A", "B", "C"):
            self.assertAlmostEqual(output.periods[0].voltage_magnitude_pu[bus], oracle["voltage_magnitude_pu"][bus], places=6)
        self.assertAlmostEqual(output.periods[0].voltage_magnitude_pu["B"], 1.02, places=8)
        self.assertGreater(sum(output.periods[0].active_loss_mw_by_branch.values()), 0.0)

    def test_24_and_168_hour_start_sensitivity_and_bounded_artifact(self):
        for periods in (24, 168):
            with tempfile.TemporaryDirectory(prefix="force-p69-") as temporary:
                root = Path(temporary)
                _, wrapped = _two_bus(periods, artifact_root=root)
                result = ReferenceACFeasibilityPSM().run(wrapped)
                output = ACFeasibilityOutput.from_dict(result.extensions["ac"])
                self.assertEqual(len(output.periods), periods)
                self.assertTrue(all(item.solver_metadata["start_solution_spread"] < 1e-5 for item in output.periods))
                self.assertEqual(len(result.artifacts), 1)
                self.assertTrue((root / result.artifacts[0].uri).is_file())

    def test_limits_bad_data_and_forced_dc_fallback_fail_closed(self):
        _, low_rating = _two_bus(rating=10.0)
        with self.assertRaisesRegex(ACNetworkSolveError, "INFEASIBLE_EQUIPMENT_LIMIT"):
            ReferenceACFeasibilityPSM().run(low_rating)
        _, low_q = _two_bus(q_limit=1.0)
        with self.assertRaisesRegex(ACNetworkSolveError, "INFEASIBLE_EQUIPMENT_LIMIT"):
            ReferenceACFeasibilityPSM().run(low_q)
        network, wrapped = _two_bus()
        missing_q = replace(network, extensions={key: value for key, value in network.extensions.items() if key != "reactive_demand_mvar_by_bus"})
        with self.assertRaisesRegex(ACNetworkInputError, "reactive demand"):
            ReferenceACFeasibilityPSM().run(replace(wrapped, extensions={"network_input": missing_q.to_dict()}))
        dc = replace(network, capability="domain.network.dc")
        with self.assertRaisesRegex(ACNetworkInputError, "not a DC"):
            ReferenceACFeasibilityPSM().run(replace(wrapped, extensions={"network_input": dc.to_dict()}))
        bad_bus = replace(network.topology.buses[1], voltage_min_pu=None)
        with self.assertRaisesRegex(ValueError, "voltage bounds"):
            replace(network, topology=replace(network.topology, buses=(network.topology.buses[0], bad_bus))).validate()
        bad_branch = replace(network.topology.branches[0], resistance_pu=0.0, reactance_pu=0.0)
        with self.assertRaisesRegex(ValueError, "impedance"):
            replace(network, topology=replace(network.topology, branches=(bad_branch,))).validate()

    def test_mutated_reactive_balance_and_loss_evidence_fail_validation(self):
        _, wrapped = _two_bus()
        result = ReferenceACFeasibilityPSM().run(wrapped)
        output = ACFeasibilityOutput.from_dict(result.extensions["ac"])
        period = output.periods[0]
        residuals = dict(period.residuals)
        residuals.pop("reactive_balance_mvar")
        with self.assertRaisesRegex(ValueError, "reactive"):
            validate_ac_result(_parse_input(wrapped), replace(output, periods=(replace(period, residuals=residuals),)))
        losses = dict(period.active_loss_mw_by_branch)
        losses["AB"] = 0.0
        with self.assertRaisesRegex(ValueError, "loss"):
            validate_ac_result(_parse_input(wrapped), replace(output, periods=(replace(period, active_loss_mw_by_branch=losses),)))

    def test_registry_selection_requires_both_conditional_data_contracts(self):
        registry = workspace_registry(
            ROOT / "missing-local-modules",
            include_internal_experimental=True,
        )
        with self.assertRaisesRegex(ValueError, "missing"):
            registry.resolve_selection(MODULES)
        graph = registry.resolve_selection(
            MODULES,
            selected_extensions=("value-network-contract-extension", "value-ac-data-extension"),
            available_data_roles=BASE_ROLES + AC_ROLES,
        )
        self.assertIsInstance(graph.implementation("psm"), ReferenceACFeasibilityPSM)
        _, wrapped = _two_bus()
        result = graph.implementation("psm").run(wrapped)
        self.assertEqual(result.module_id, "value-reference-ac-feasibility")

    def test_pack_adapter_reads_real_conditional_roles(self):
        network, wrapped = _two_bus()
        with tempfile.TemporaryDirectory(prefix="force-p69-pack-") as temporary:
            root = Path(temporary)
            (root / "generators.json").write_text(
                json.dumps({"generator_specs": network.extensions["generator_specs"]}),
                encoding="utf-8",
            )
            (root / "reactive.csv").write_text(
                "period_id,bus_id,reactive_demand_mvar\np0,A,0\np0,B,20\n",
                encoding="utf-8",
            )
            (root / "schedule.csv").write_text(
                "period_id,asset_id,active_schedule_mwh\np0,slack,50\n",
                encoding="utf-8",
            )
            manifest = {"bindings": {
                "value.network.ac.generators": {"uri": "generators.json"},
                "value.network.ac.reactive-demand": {"uri": "reactive.csv"},
                "value.network.ac.active-schedule": {"uri": "schedule.csv"},
            }}
            loaded = load_ac_data_from_pack(root, manifest, replace(network, extensions={}))
            result = ReferenceACFeasibilityPSM().run(
                replace(wrapped, extensions={"network_input": loaded.to_dict()})
            )
            self.assertEqual(result.module_id, "value-reference-ac-feasibility")
            self.assertIn("ac_data_source_sha256", loaded.extensions)


if __name__ == "__main__":
    unittest.main()
