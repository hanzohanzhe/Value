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
from gridform_core.network_dc import DCNetworkInputError, ReferenceDCNetworkPSM

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

    def test_reference_dc_refuses_a_split_mapping_instead_of_guessing(self) -> None:
        _network, wrapped = three_bus_dc_case(split=True)
        with self.assertRaisesRegex(DCNetworkInputError, "multi-bus share"):
            ReferenceDCNetworkPSM().run(wrapped)


if __name__ == "__main__":
    unittest.main()
