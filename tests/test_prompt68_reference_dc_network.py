from __future__ import annotations

import json
import random
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from gridform_core.network_contracts import (
    AssetBusMapping,
    NetworkBranch,
    NetworkBus,
    NetworkPSMInput,
    NetworkPSMOutput,
    NetworkTopology,
)
from gridform_core.network_dc import ReferenceDCNetworkPSM, validate_dc_solution
from gridform_core.perfect_foresight_psm import PerfectForesightPSM
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
    StorageDispatchResource,
)
from gridform_core.v2.module_manifest import workspace_registry
from gridform_validation.network_dc_oracle import solve_dc_oracle


ROOT = Path(__file__).resolve().parents[1]
NETWORK_ROLES = (
    "value.network.buses",
    "value.network.branches",
    "value.network.asset-map",
    "value.network.nodal-demand",
)
BASE_MODULES = {
    "psm": "value-reference-dc-network",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "transition": "value-annual-state-transition",
}


def _resource(
    asset_id: str,
    bus_id: str,
    cost: float,
    capacity: float,
    *,
    resource_type: str = "thermal",
    availability: tuple[float, ...] = (1.0,),
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "bus_id": bus_id,
        "technology": "wind" if resource_type == "vre" else resource_type,
        "resource_type": resource_type,
        "capacity_mw": capacity,
        "cost": cost,
        "availability": list(availability),
    }


def _store(
    asset_id: str,
    bus_id: str,
    technology: str,
    *,
    power: float = 4.0,
    energy: float = 8.0,
    efficiency: float = 0.9,
    initial: float = 0.0,
    degradation: float = 0.0,
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "bus_id": bus_id,
        "technology": technology,
        "charge_power_mw": power,
        "discharge_power_mw": power,
        "energy_capacity_mwh": energy,
        "charge_efficiency": efficiency,
        "discharge_efficiency": efficiency,
        "initial_soc_mwh": initial,
        "degradation_cost": degradation,
    }


def _case(
    demand: dict[str, list[float]],
    resources: list[dict[str, object]],
    *,
    branches: list[dict[str, object]] | None = None,
    storage: list[dict[str, object]] | None = None,
    reference_buses: set[str] | None = None,
    period_hours: float = 1.0,
) -> dict[str, object]:
    reference_buses = reference_buses or {next(iter(demand))}
    return {
        "buses": [
            {
                "bus_id": bus,
                "voltage_kv": 400.0,
                "region": bus,
                "reference_eligible": bus in reference_buses,
                "is_reference": bus in reference_buses,
            }
            for bus in demand
        ],
        "branches": branches or [],
        "resources": resources,
        "storage": storage or [],
        "demand_mwh_by_bus": demand,
        "period_hours": period_hours,
        "voll": 10_000.0,
        "base_mva": 100.0,
    }


def _line(
    branch_id: str,
    from_bus: str,
    to_bus: str,
    rating: float,
    reactance: float = 0.1,
) -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "from_bus": from_bus,
        "to_bus": to_bus,
        "branch_type": "ac_line",
        "in_service": True,
        "thermal_rating_mw": rating,
        "reactance_pu": reactance,
        "circuits": 1,
    }


def _inputs(case: dict[str, object], *, artifact_directory: Path | None = None):
    resource_specs = list(case["resources"])
    storage_specs = list(case.get("storage") or [])
    resources = tuple(
        DispatchResource(
            str(item["asset_id"]),
            str(item["technology"]),
            str(item["resource_type"]),
            float(item["capacity_mw"]),
            float(item["cost"]),
            tuple(float(value) for value in item["availability"]),
        )
        for item in resource_specs
    )
    storage = tuple(
        StorageDispatchResource(
            str(item["asset_id"]),
            str(item["technology"]),
            float(item["charge_power_mw"]),
            float(item["discharge_power_mw"]),
            float(item["energy_capacity_mwh"]),
            float(item["charge_efficiency"]),
            float(item["discharge_efficiency"]),
            float(item["initial_soc_mwh"]),
            float(item.get("degradation_cost", 0.0)),
        )
        for item in storage_specs
    )
    nodal = {
        str(bus): tuple(float(value) for value in values)
        for bus, values in dict(case["demand_mwh_by_bus"]).items()
    }
    periods = len(next(iter(nodal.values())))
    chronology = ChronologicalPSMData(
        tuple(f"p{period}" for period in range(periods)),
        tuple(sum(values[period] for values in nodal.values()) for period in range(periods)),
        resources,
        storage,
        float(case["voll"]),
        terminal_soc_rule="cyclic",
    )
    buses = tuple(NetworkBus.from_dict(item) for item in case["buses"])
    branches = tuple(NetworkBranch.from_dict(item) for item in case.get("branches") or [])
    mappings = tuple(
        AssetBusMapping(
            str(item["asset_id"]),
            str(item["bus_id"]),
            "boundary_import" if item["resource_type"] == "import" else "generator",
        )
        for item in resource_specs
    ) + tuple(
        AssetBusMapping(str(item["asset_id"]), str(item["bus_id"]), "storage")
        for item in storage_specs
    )
    network = NetworkPSMInput(
        "prompt68",
        2025,
        float(case["period_hours"]),
        chronology,
        NetworkTopology(buses, branches, mappings, float(case.get("base_mva", 100.0))),
        nodal,
        "domain.network.dc",
        "perfect_foresight",
    )
    network.validate()
    extensions: dict[str, object] = {"network_input": network.to_dict()}
    if artifact_directory is not None:
        extensions["artifact_directory"] = str(artifact_directory)
    wrapped = PSMInput(
        network.run_id,
        network.year,
        "prompt68-public-fixture",
        OperatingState(network.year, (), ()),
        network.period_hours,
        {},
        chronology=chronology,
        extensions=extensions,
    )
    return network, wrapped


def _solve(case: dict[str, object], *, artifact_directory: Path | None = None):
    network, wrapped = _inputs(case, artifact_directory=artifact_directory)
    result = ReferenceDCNetworkPSM().run(wrapped)
    network_result = NetworkPSMOutput.from_dict(result.extensions["network"])
    return network, result, network_result


class Prompt68ReferenceDCNetworkTests(unittest.TestCase):
    def assert_oracle(self, case: dict[str, object], *, places: int = 6):
        network, result, network_result = _solve(case)
        oracle = solve_dc_oracle(case)
        self.assertTrue(oracle["success"], oracle)
        self.assertAlmostEqual(
            result.total_operational_cost_gbp, oracle["objective_gbp"], places=places
        )
        self.assertLessEqual(validate_dc_solution(network, network_result)["maximum_nodal_balance_mwh"], 1e-7)
        return network, result, network_result, oracle

    def test_one_bus_matches_existing_copper_plate_lp(self):
        case = _case(
            {"A": [12.0]},
            [
                _resource("thermal", "A", 50.0, 5.0),
                _resource("import", "A", 30.0, 5.0, resource_type="import"),
            ],
        )
        _, wrapped = _inputs(case)
        dc = ReferenceDCNetworkPSM().run(wrapped)
        copper = PerfectForesightPSM().run(replace(wrapped, extensions={}))
        self.assertAlmostEqual(dc.total_operational_cost_gbp, copper.total_operational_cost_gbp)
        self.assertEqual(dc.generation_mwh_by_asset, copper.generation_mwh_by_asset)
        self.assertAlmostEqual(dc.total_blackout_mwh, 2.0)
        self.assert_oracle(case)

    def test_two_bus_uncongested_and_binding_limit_with_price_separation(self):
        resources = [
            _resource("cheap", "A", 10.0, 20.0),
            _resource("local", "B", 100.0, 20.0),
        ]
        uncongested = _case(
            {"A": [0.0], "B": [10.0]}, resources,
            branches=[_line("AB", "A", "B", 100.0)],
        )
        _, first, _, _ = self.assert_oracle(uncongested)
        self.assertAlmostEqual(first.generation_mwh_by_asset["cheap"], 10.0)
        binding = {**uncongested, "branches": [_line("AB", "A", "B", 4.0)]}
        _, second, output, _ = self.assert_oracle(binding)
        self.assertAlmostEqual(second.generation_mwh_by_asset["cheap"], 4.0)
        self.assertAlmostEqual(second.generation_mwh_by_asset["local"], 6.0)
        prices = output.periods[0].nodal_price_gbp_per_mwh
        self.assertLess(prices["A"], prices["B"])
        self.assertAlmostEqual(abs(output.periods[0].branch_flow_mw["AB"]), 4.0)

    def test_three_bus_mesh_thermal_vre_import_and_oracle(self):
        case = _case(
            {"A": [0.0, 2.0], "B": [6.0, 5.0], "C": [8.0, 8.0]},
            [
                _resource("wind", "A", 0.0, 10.0, resource_type="vre", availability=(1.0, 0.3)),
                _resource("import", "B", 35.0, 8.0, resource_type="import"),
                _resource("thermal", "C", 70.0, 20.0),
            ],
            branches=[
                _line("AB", "A", "B", 12.0, 0.10),
                _line("BC", "B", "C", 12.0, 0.12),
                _line("AC", "A", "C", 12.0, 0.15),
            ],
        )
        _, result, output, oracle = self.assert_oracle(case)
        self.assertGreater(result.generation_mwh_by_asset["wind"], 0.0)
        self.assertGreater(result.generation_mwh_by_asset["import"], 0.0)
        self.assertLessEqual(oracle["maximum_equality_residual"], 1e-7)
        self.assertEqual(output.optimality_class, "GLOBAL_OPTIMUM_VALIDATED_LINEAR_PROGRAM")

    def test_islands_scarcity_battery_and_pumped_hydro(self):
        case = _case(
            {"A": [0.0, 4.0], "B": [3.0, 3.0]},
            [
                _resource("wind", "A", 0.0, 10.0, resource_type="vre", availability=(1.0, 0.0)),
                _resource("limited", "B", 40.0, 1.0),
            ],
            storage=[
                _store("battery", "A", "battery", power=5.0, energy=5.0, efficiency=0.8),
                _store("pumped", "B", "pumped_hydro", power=1.0, energy=3.0, efficiency=0.87),
            ],
            reference_buses={"A", "B"},
        )
        _, result, _, _ = self.assert_oracle(case)
        self.assertGreater(result.generation_mwh_by_asset["battery"], 0.0)
        self.assertGreater(result.total_blackout_mwh, 0.0)

    def test_24_and_168_hour_chronologies_and_random_convex_cases(self):
        for periods in (24, 168):
            availability = tuple(1.0 if period % 24 < 12 else 0.0 for period in range(periods))
            case = _case(
                {"A": [0.0] * periods, "B": [5.0] * periods},
                [
                    _resource("solar", "A", 0.0, 8.0, resource_type="vre", availability=availability),
                    _resource("thermal", "B", 70.0, 10.0),
                ],
                branches=[_line("AB", "A", "B", 8.0)],
                storage=[_store("pumped", "B", "pumped_hydro", power=2.0, energy=8.0, efficiency=0.87, initial=4.0)],
            )
            _, result, output, _ = self.assert_oracle(case, places=5)
            self.assertEqual(len(result.period_summaries), periods)
            self.assertEqual(len(output.periods), periods)
        for seed in range(6):
            rng = random.Random(seed)
            demand = [rng.uniform(2.0, 12.0) for _ in range(8)]
            case = _case(
                {"A": [0.0] * 8, "B": demand},
                [
                    _resource("cheap", "A", rng.uniform(1, 20), rng.uniform(4, 12)),
                    _resource("local", "B", rng.uniform(30, 90), rng.uniform(4, 12)),
                ],
                branches=[_line("AB", "A", "B", rng.uniform(2, 10), rng.uniform(0.08, 0.25))],
            )
            self.assert_oracle(case, places=5)

    def test_fail_closed_mutations_for_network_storage_and_mapping(self):
        case = _case(
            {"A": [0.0, 4.0], "B": [3.0, 5.0]},
            [
                _resource("wind", "A", 0.0, 8.0, resource_type="vre", availability=(1.0, 0.0)),
                _resource("thermal", "B", 60.0, 10.0),
            ],
            branches=[_line("AB", "A", "B", 5.0)],
            storage=[_store("battery", "A", "battery", power=4.0, energy=4.0, efficiency=0.8)],
        )
        network, _, output = _solve(case)
        period = output.periods[0]
        broken_injection = dict(period.nodal_injection_mwh)
        broken_injection["A"] += 1.0
        with self.assertRaisesRegex(ValueError, "nodal"):
            validate_dc_solution(network, replace(output, periods=(replace(period, nodal_injection_mwh=broken_injection), *output.periods[1:])))
        angles = dict(period.voltage_angle_radians)
        angles["B"] += 0.1
        with self.assertRaisesRegex(ValueError, "angle"):
            validate_dc_solution(network, replace(output, periods=(replace(period, voltage_angle_radians=angles), *output.periods[1:])))
        flows = dict(period.branch_flow_mw)
        flows["AB"] = 1_000.0
        with self.assertRaisesRegex(ValueError, "branch"):
            validate_dc_solution(network, replace(output, periods=(replace(period, branch_flow_mw=flows), *output.periods[1:])))
        refs = dict(period.voltage_angle_radians)
        refs["A"] = 0.01
        with self.assertRaisesRegex(ValueError, "reference"):
            validate_dc_solution(network, replace(output, periods=(replace(period, voltage_angle_radians=refs), *output.periods[1:])))
        storage = json.loads(json.dumps(output.extensions["storage"]))
        storage["battery"]["soc"][0] = 99.0
        with self.assertRaisesRegex(ValueError, "soc"):
            validate_dc_solution(network, replace(output, extensions={**output.extensions, "storage": storage}))
        incomplete = replace(
            network,
            topology=replace(network.topology, asset_mappings=network.topology.asset_mappings[:-1]),
        )
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            incomplete.validate()
        wrong_demand = replace(network, demand_mwh_by_bus={"A": (0.0, 0.0), "B": (3.0, 4.0)})
        with self.assertRaisesRegex(ValueError, "mismatch"):
            wrong_demand.validate()

    def test_actual_registry_selection_and_fast_audit_artifacts(self):
        registry = workspace_registry(ROOT / "missing-local-modules")
        with self.assertRaisesRegex(ValueError, "missing"):
            registry.resolve_selection(BASE_MODULES)
        graph = registry.resolve_selection(
            BASE_MODULES,
            selected_extensions=("value-network-contract-extension",),
            available_data_roles=NETWORK_ROLES,
        )
        self.assertIsInstance(graph.implementation("psm"), ReferenceDCNetworkPSM)
        case = _case(
            {"A": [0.0], "B": [5.0]},
            [_resource("thermal", "A", 40.0, 10.0)],
            branches=[_line("AB", "A", "B", 10.0)],
        )
        with tempfile.TemporaryDirectory(prefix="force-p68-") as temporary:
            root = Path(temporary)
            network, wrapped = _inputs(case, artifact_directory=root / "solver")
            result = graph.implementation("psm").run(wrapped)
            self.assertEqual(len(result.artifacts), 3)
            for artifact in result.artifacts:
                self.assertTrue((root / artifact.uri).is_file())
            jsonl = root / "solver" / "network" / "declared-network-inputs-2025.jsonl"
            rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(json.loads(rows[0]["payload_json"])["payload"]["period_id"], "p0")
            with closing(sqlite3.connect(root / "solver" / "network" / "dc-network-2025.sqlite")) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM period_bus").fetchone()[0], 2)
            validate_dc_solution(network, NetworkPSMOutput.from_dict(result.extensions["network"]))


if __name__ == "__main__":
    unittest.main()
