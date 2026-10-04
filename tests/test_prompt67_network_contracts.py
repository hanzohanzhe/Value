from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.network_contracts import (
    AssetBusMapping,
    NetworkBranch,
    NetworkBus,
    NetworkPSMInput,
    NetworkPeriodResult,
    NetworkTopology,
    network_clearing_input_row,
)
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    StorageDispatchResource,
)
from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]


def resource(asset_id: str, kind: str = "thermal") -> DispatchResource:
    return DispatchResource(asset_id, kind, kind, 10.0, 20.0, (1.0, 1.0))


def storage() -> StorageDispatchResource:
    return StorageDispatchResource("battery", "battery", 2, 2, 4, 0.9, 0.9, 2)


def chronology(resources=None, stores=None, demand=(5.0, 6.0)) -> ChronologicalPSMData:
    return ChronologicalPSMData(
        ("p0", "p1"), demand, tuple(resources or (resource("thermal"),)),
        tuple(stores or ()), 10_000.0,
    )


class Prompt67NetworkContractTests(unittest.TestCase):
    def test_one_bus_roundtrip_reconciles_base_contract(self):
        topology = NetworkTopology(
            (NetworkBus("gb", 400, "GB", True, True),), (),
            (AssetBusMapping("thermal", "gb", "generator"),), 100.0,
        )
        value = NetworkPSMInput(
            "run", 2025, 0.5, chronology(), topology,
            {"gb": (5.0, 6.0)}, "domain.network.dc", "chronological_perfect_foresight",
        )
        value.validate()
        restored = NetworkPSMInput.from_dict(value.to_dict())
        self.assertEqual(restored.to_dict(), value.to_dict())
        declared = network_clearing_input_row(value, period=0)
        self.assertEqual(declared.payload()["reference_buses"], ["gb"])
        self.assertNotIn("accepted_mwh", declared.payload_json)

    def test_two_bus_congested_and_three_bus_mesh_are_structurally_valid(self):
        buses = (
            NetworkBus("a", 400, "A", True, True),
            NetworkBus("b", 400, "B"),
            NetworkBus("c", 275, "C"),
        )
        branches = (
            NetworkBranch("ab", "a", "b", "ac_line", True, 5, reactance_pu=0.1),
            NetworkBranch("bc", "b", "c", "transformer", True, 4, reactance_pu=0.2, tap_ratio=1.05),
            NetworkBranch("ca", "c", "a", "ac_line", True, 3, reactance_pu=0.15),
        )
        mappings = (
            AssetBusMapping("thermal", "a", "generator"),
            AssetBusMapping("solar", "b", "generator"),
            AssetBusMapping("import:france", "c", "boundary_import"),
            AssetBusMapping("battery", "b", "storage"),
        )
        data = chronology(
            (resource("thermal"), resource("solar", "vre"), resource("import:france", "import")),
            (storage(),), demand=(9, 9),
        )
        model = NetworkPSMInput(
            "run", 2025, 1.0, data, NetworkTopology(buses, branches, mappings, 100),
            {"a": (1, 1), "b": (4, 4), "c": (4, 4)},
            "domain.network.dc", "chronological_perfect_foresight",
        )
        model.validate()
        self.assertEqual(model.topology.islands(), (("a", "b", "c"),))

    def test_islands_slacks_topology_units_mapping_and_demand_fail_closed(self):
        buses = (
            NetworkBus("a", 400, "A", True, True),
            NetworkBus("b", 400, "B"),
        )
        base = NetworkTopology(
            buses,
            (NetworkBranch("ab", "a", "b", "ac_line", True, 5, reactance_pu=0.1),),
            (AssetBusMapping("thermal", "a", "generator"),), 100,
        )
        with self.assertRaisesRegex(ValueError, "dangling endpoint"):
            replace(base, branches=(replace(base.branches[0], to_bus="missing"),)).validate(
                capability="domain.network.dc"
            )
        with self.assertRaisesRegex(ValueError, "invalid DC reactance"):
            replace(base, branches=(replace(base.branches[0], reactance_pu=0.0),)).validate(
                capability="domain.network.dc"
            )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            replace(base, branches=(replace(base.branches[0], in_service=False),)).validate(
                capability="domain.network.dc"
            )
        with self.assertRaisesRegex(ValueError, "Nodal demand mismatch"):
            NetworkPSMInput(
                "run", 2025, 1, chronology(), base, {"a": (1, 1), "b": (1, 1)},
                "domain.network.dc", "period_local",
            ).validate()
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            replace(base, asset_mappings=()).validate(capability="domain.network.dc")
            # Topology alone is valid; mapping completeness belongs to PSM input.
            NetworkPSMInput(
                "run", 2025, 1, chronology(), replace(base, asset_mappings=()),
                {"a": (5, 6), "b": (0, 0)}, "domain.network.dc", "period_local",
            ).validate()

    def test_boundary_import_is_external_supply_not_internal_branch(self):
        data = chronology((resource("import:france", "import"),))
        topology = NetworkTopology(
            (NetworkBus("gb", 400, "GB", True, True),), (),
            (AssetBusMapping("import:france", "gb", "generator"),), 100,
        )
        with self.assertRaisesRegex(ValueError, "boundary_import"):
            NetworkPSMInput(
                "run", 2025, 1, data, topology, {"gb": (5, 6)},
                "domain.network.dc", "period_local",
            ).validate()

    def test_unsupported_ac_and_loss_outputs_are_absent_not_zero(self):
        result = NetworkPeriodResult(
            "p0", {"a": 1}, {"b": 1}, {"ab": 1}, {"a": 0, "b": 0},
            {"a": 0, "b": 0}, voltage_angle_radians={"a": 0, "b": -0.1},
            unsupported={
                "network_losses_mwh": "DC approximation is lossless",
                "voltage_magnitude_pu": "DC approximation does not model voltage magnitude",
                "reactive_injection_mvarh": "DC approximation does not model reactive power",
            },
        ).to_dict()
        self.assertNotIn("network_losses_mwh", result)
        self.assertNotIn("voltage_magnitude_pu", result)
        self.assertNotIn("reactive_injection_mvarh", result)
        self.assertIn("network_losses_mwh", result["unsupported"])

    def test_network_roles_are_conditional_and_single_node_psm_is_incompatible(self):
        registry = workspace_registry(ROOT / "missing-local-modules")
        roles = registry.extension_registry.conditional_dataset_slots(
            ("value-network-contract-extension",)
        )
        self.assertEqual(sum(bool(item["required"]) for item in roles), 4)
        selected = {
            "psm": "value-perfect-foresight-lp", "investment": "agent-investment",
            "pipeline": "planning-pipeline", "vre_cap": "vre-expansion-cap",
            "storage_cap": "value-storage-expansion-policy", "transition": "value-annual-state-transition",
        }
        with self.assertRaisesRegex(ValueError, "domain.network.solver"):
            registry.resolve_selection(
                selected,
                selected_extensions=("value-network-contract-extension",),
                available_data_roles=tuple(item["role"] for item in roles if item["required"]),
            )
        # The same base selection remains valid and activates no network files.
        registry.resolve_selection(selected)


if __name__ == "__main__":
    unittest.main()
