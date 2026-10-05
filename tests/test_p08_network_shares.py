"""P0-8 S2/S3: asset-to-bus share mappings are solved or rejected (P1-01)."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.network_contracts import (
    AssetBusMapping,
    MultiBusMappingError,
)
from gridform_core.network_contracts import NetworkPSMOutput, network_clearing_input_row
from gridform_core.network_dc import ReferenceDCNetworkPSM, validate_dc_solution

from tests.network_toys import dc_case, three_bus_dc_case


ROOT = Path(__file__).resolve().parents[1]


class ShareContractTests(unittest.TestCase):
    def test_a_single_partial_share_is_rejected(self) -> None:
        network, _ = dc_case(
            {"A": [1.0]},
            [{"asset_id": "gas", "capacity_mw": 5.0, "cost": 10.0, "buses": [("A", 0.3)]}],
        )
        with self.assertRaisesRegex(ValueError, "shares sum to 0.3"):
            network.validate()

    def test_shares_must_sum_to_one_and_not_repeat_a_bus(self) -> None:
        network, _ = three_bus_dc_case(split=True)
        network.validate()
        topology = network.topology
        over = replace(topology, asset_mappings=tuple(topology.asset_mappings) + (
            AssetBusMapping("wind", "C", "generator", 0.1),
        ))
        with self.assertRaisesRegex(ValueError, "shares sum to"):
            over.validate(capability="domain.network.dc")
        repeated = replace(topology, asset_mappings=tuple(
            replace(row, bus_id="A") if row.asset_id == "wind" else row
            for row in topology.asset_mappings
        ))
        with self.assertRaisesRegex(ValueError, "same bus twice"):
            repeated.validate(capability="domain.network.dc")
        mixed = replace(topology, asset_mappings=tuple(
            replace(row, asset_class="storage")
            if row.asset_id == "wind" and row.bus_id == "B" else row
            for row in topology.asset_mappings
        ))
        with self.assertRaisesRegex(ValueError, "conflicting classes"):
            mixed.validate(capability="domain.network.dc")

    def test_single_bus_lookup_refuses_a_split_asset(self) -> None:
        network, _ = three_bus_dc_case(split=True)
        self.assertEqual(
            [(row.bus_id, row.share) for row in network.topology.mappings_by_asset()["wind"]],
            [("A", 0.5), ("B", 0.5)],
        )
        with self.assertRaisesRegex(MultiBusMappingError, "wind"):
            network.topology.mapping_by_asset()

    def test_extension_declares_the_sum_to_one_rule(self) -> None:
        manifest = json.loads(
            (ROOT / "gridform_core" / "extension_manifests" / "value-network-contract-extension.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], "1.1.0")
        role = next(
            row for row in manifest["data_roles"] if row["role"] == "value.network.asset-map"
        )
        self.assertEqual(role["validation_rules"], {"shares_sum_to_one": True})


class ShareStopGapTests(unittest.TestCase):
    def test_ac_requires_exactly_one_bus_per_asset(self) -> None:
        from gridform_core.network_ac import ACNetworkInputError, ReferenceACFeasibilityPSM
        from tests.test_prompt69_ac_feasibility import _two_bus

        network, wrapped = _two_bus()
        rows = []
        for row in network.topology.asset_mappings:
            if row.asset_id == "slack":
                rows.append(replace(row, share=0.5))
                rows.append(replace(row, bus_id="B", share=0.5))
            else:
                rows.append(row)
        split = replace(network, topology=replace(network.topology, asset_mappings=tuple(rows)))
        split.validate()
        wrapped = replace(
            wrapped, extensions={**dict(wrapped.extensions), "network_input": split.to_dict()}
        )
        with self.assertRaisesRegex(ACNetworkInputError, "exactly one bus mapping"):
            ReferenceACFeasibilityPSM().run(wrapped)



V100_SINGLE_BUS_FIXTURE = ROOT / "tests" / "fixtures" / "network_toys" / "dc-1.0.0-single-bus.json"


def single_bus_storage_case():
    """Two buses, AB rated 5 MW, one single-bus battery at each bus."""

    demand = {"A": [0.0, 40.0], "B": [0.0, 40.0]}
    resources = [{"asset_id": "gas", "capacity_mw": 200.0, "cost": 10.0, "buses": [("A", 1.0)]},
                 {"asset_id": "peaker", "capacity_mw": 200.0, "cost": 500.0, "buses": [("B", 1.0)]}]
    branches = [{"branch_id": "AB", "from_bus": "A", "to_bus": "B", "rating_mw": 5.0}]
    return dc_case(demand, resources, branches=branches, terminal_soc_rule="free", storage=[
        {"asset_id": "battery-a", "power_mw": 10.0, "energy_mwh": 20.0, "efficiency": 1.0, "buses": [("A", 1.0)]},
        {"asset_id": "battery-b", "power_mw": 30.0, "energy_mwh": 60.0, "efficiency": 1.0, "buses": [("B", 1.0)]},
    ])


class DCShareExpansionTests(unittest.TestCase):
    """S3: expand-solve-aggregate; HEAD put all 200 MW at the last row's bus."""

    def solve(self, network, wrapped):
        result = ReferenceDCNetworkPSM().run(wrapped)
        output = NetworkPSMOutput.from_dict(result.extensions["network"])
        validate_dc_solution(network, output)
        return result, output

    def test_split_wind_needs_no_flow_and_no_gas(self) -> None:
        network, wrapped = three_bus_dc_case(split=True)
        result, output = self.solve(network, wrapped)
        period = output.periods[0]
        self.assertAlmostEqual(period.branch_flow_mw["AB"], 0.0, places=7)
        self.assertAlmostEqual(result.generation_mwh_by_asset["gas"], 0.0, places=7)
        self.assertAlmostEqual(result.total_operational_cost_gbp, 0.0, places=6)
        self.assertAlmostEqual(period.nodal_injection_mwh["A"], 100.0, places=7)
        self.assertAlmostEqual(period.nodal_injection_mwh["B"], 100.0, places=7)

    def test_split_equals_two_explicit_units_and_row_order_is_irrelevant(self) -> None:
        split = self.solve(*three_bus_dc_case(split=True))
        swapped = self.solve(*three_bus_dc_case(split=True, swap_rows=True))
        explicit = self.solve(*three_bus_dc_case(split=False))
        for other in (swapped, explicit):
            self.assertAlmostEqual(split[0].total_operational_cost_gbp, other[0].total_operational_cost_gbp, places=9)
            self.assertEqual(split[1].periods[0].branch_flow_mw, other[1].periods[0].branch_flow_mw)
            self.assertEqual(split[1].periods[0].nodal_price_gbp_per_mwh, other[1].periods[0].nodal_price_gbp_per_mwh)
        self.assertEqual(split[0].total_operational_cost_gbp, swapped[0].total_operational_cost_gbp)
        self.assertAlmostEqual(
            split[0].generation_mwh_by_asset["wind"],
            explicit[0].generation_mwh_by_asset["wind-a"] + explicit[0].generation_mwh_by_asset["wind-b"],
            places=9,
        )
        row = network_clearing_input_row(three_bus_dc_case(split=True)[0], period=0)
        payload = json.loads(row.payload_json)["payload"]
        self.assertEqual(payload["asset_bus_shares"]["wind"], [["A", 0.5], ["B", 0.5]])
        self.assertNotIn("wind", payload["asset_to_bus"])
        self.assertEqual(payload["asset_to_bus"]["gas"], "C")

    def test_split_storage_keeps_one_soc_curve_per_bus(self) -> None:
        demand = {"A": [0.0, 40.0], "B": [0.0, 40.0]}
        resources = [{"asset_id": "gas", "capacity_mw": 200.0, "cost": 10.0, "buses": [("A", 1.0)]},
                     {"asset_id": "peaker", "capacity_mw": 200.0, "cost": 500.0, "buses": [("B", 1.0)]}]
        branches = [{"branch_id": "AB", "from_bus": "A", "to_bus": "B", "rating_mw": 5.0}]
        split = dc_case(demand, resources, branches=branches, terminal_soc_rule="free", storage=[{
            "asset_id": "battery", "power_mw": 40.0, "energy_mwh": 80.0, "efficiency": 1.0,
            "buses": [("A", 0.25), ("B", 0.75)],
        }])
        explicit = single_bus_storage_case()
        split_result, split_output = self.solve(*split)
        explicit_result, _ = self.solve(*explicit)
        self.assertAlmostEqual(
            split_result.total_operational_cost_gbp, explicit_result.total_operational_cost_gbp, places=6
        )
        curves = split_output.extensions["storage_sub_resources"]
        self.assertEqual(set(curves), {"battery::bus::A", "battery::bus::B"})
        self.assertEqual(curves["battery::bus::A"]["share"], 0.25)
        for sub in curves.values():
            self.assertLessEqual(max(sub["soc"]), 80.0 * sub["share"] + 1e-9)
        aggregate = split_output.extensions["storage"]["battery"]["soc"]
        for period, value in enumerate(aggregate):
            self.assertAlmostEqual(
                value, sum(sub["soc"][period] for sub in curves.values()), places=9
            )

    def test_single_bus_input_is_tagged_and_has_no_sub_resources(self) -> None:
        network, wrapped = three_bus_dc_case(split=False)
        result, output = self.solve(network, wrapped)
        self.assertNotIn("storage_sub_resources", output.extensions)
        self.assertEqual(output.extensions["share_mapping_rule"], "expand_solve_aggregate/v1")
        self.assertEqual(ReferenceDCNetworkPSM.version, "1.1.0")

    def test_single_bus_inputs_reproduce_the_1_0_0_numbers(self) -> None:
        """Numerically equal to value-reference-dc-network 1.0.0 (only +/-0 differ).

        The expected values were produced by the 1.0.0 module (network_dc.py
        at c664330^).  Python ``==`` treats -0.0, 0.0 and 0 as equal; 1.0.0
        emitted -0.0 in some flow/price/storage entries and an integer 0 for
        curtailment, so the serialized bytes are not identical.
        """

        expected = json.loads(V100_SINGLE_BUS_FIXTURE.read_text(encoding="utf-8"))["cases"]
        cases = {
            "three_bus_explicit": three_bus_dc_case(split=False),
            "storage_explicit": single_bus_storage_case(),
        }
        self.assertEqual(set(expected), set(cases))
        for name, (network, wrapped) in cases.items():
            with self.subTest(case=name):
                result, _output = self.solve(network, wrapped)
                payload = result.extensions["network"]
                want = expected[name]
                self.assertEqual(result.total_operational_cost_gbp, want["total_operational_cost_gbp"])
                self.assertEqual(dict(result.generation_mwh_by_asset), want["generation_mwh_by_asset"])
                self.assertEqual(payload["objective_gbp"], want["objective_gbp"])
                self.assertEqual(payload["periods"], want["periods"])
                self.assertEqual(payload["extensions"]["storage"], want["storage"])

if __name__ == "__main__":
    unittest.main()
