"""P0-8 S11: boundaries must be the graph cuts they claim to be (P1-05, P2-15)."""

from __future__ import annotations

import copy
import csv
import inspect
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.gb_zonal_pack_builder import build_candidate
from gridform_core.zonal_contracts import (
    ETYSBoundary,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZonalDemand,
    ZonalNetworkPack,
    classify_cutsets,
    load_zonal_network_pack,
)

from tests.network_toys import eleven_zone_topology


def pack_from_topology(topology: dict[str, object]) -> ZonalNetworkPack:
    zones = tuple(NetworkZone.from_dict(row) for row in topology["zones"])  # type: ignore[union-attr]
    pack = ZonalNetworkPack(
        "eleven-zone-copy", "", zones,
        tuple(TransportCorridor.from_dict(row) for row in topology["corridors"]),  # type: ignore[union-attr]
        tuple(ETYSBoundary.from_dict(row) for row in topology["cutsets"]),  # type: ignore[union-attr]
        (),
        ZonalDemand(("p0",), {zone.zone_id: (1.0,) for zone in zones}, (float(len(zones)),)),
        (), (), SpatialAudit((), {}, {}, 1e-9), "lossless_v1",
    )
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


def classify(topology: dict[str, object]) -> dict[str, dict[str, object]]:
    report = classify_cutsets(pack_from_topology(topology), topology["cutsets"])  # type: ignore[arg-type]
    return {row["boundary_id"]: row for row in report["boundaries"]}  # type: ignore[index]


class ElevenZoneCopyTests(unittest.TestCase):
    def test_eleven_zone_copy_has_no_errors(self) -> None:
        topology = eleven_zone_topology()
        before = copy.deepcopy(topology)
        rows = classify(topology)
        self.assertEqual(topology, before)
        self.assertEqual(sum(len(row["errors"]) for row in rows.values()), 0)
        declared = [key for key, row in rows.items() if row["classification"] == "declared_partition_cut"]
        self.assertEqual(sorted(declared), sorted(["B4", "B6", "B7a", "B8", "B9", "EC5", "LE1", "B13"]))
        limits = sorted(key for key, row in rows.items() if row["classification"] == "corridor_limit")
        self.assertEqual(len(limits), 9)
        self.assertIn("Western_Link", limits)
        self.assertTrue(all(key == "Western_Link" or key.startswith("THERMAL_AC:") for key in limits))

    def test_classification_does_not_change_the_pack_hash(self) -> None:
        pack = pack_from_topology(eleven_zone_topology())
        digest = pack.compute_scientific_sha256()
        classify_cutsets(pack, eleven_zone_topology()["cutsets"])  # type: ignore[arg-type]
        self.assertEqual(pack.compute_scientific_sha256(), digest)


class BrokenCutTests(unittest.TestCase):
    def boundary(self, topology: dict[str, object], boundary_id: str) -> dict[str, object]:
        return next(row for row in topology["cutsets"] if row["boundary_id"] == boundary_id)  # type: ignore[union-attr]

    def test_partition_mismatch(self) -> None:
        topology = eleven_zone_topology()
        b6 = self.boundary(topology, "B6")
        b6["positive_side_zone_ids"] = ["T1"]
        b6["negative_side_zone_ids"] = [f"T{index}" for index in range(2, 12)]
        self.assertIn("partition_mismatch", classify(topology)["B6"]["errors"])

    def test_bypass_when_a_crossing_corridor_is_left_out(self) -> None:
        topology = eleven_zone_topology()
        b6 = self.boundary(topology, "B6")
        b6["members"] = [row for row in b6["members"] if row["corridor_id"] != "HVDC:Western_Link"]
        row = classify(topology)["B6"]
        self.assertIn("bypass", row["errors"])
        self.assertEqual(row["bypass_corridor_ids"], ["HVDC:Western_Link"])

    def test_bypass_through_an_unconstrained_fallback_zone(self) -> None:
        topology = eleven_zone_topology()
        topology["zones"].append({  # type: ignore[union-attr]
            "zone_id": "FALLBACK", "display_name": "Fallback", "dso_owner": "none",
            "nation": "England", "is_unconstrained_fallback": True,
        })
        topology["corridors"].extend([  # type: ignore[union-attr]
            {"corridor_id": "T1-F", "from_zone_id": "T1", "to_zone_id": "FALLBACK",
             "positive_direction": "from_to_positive", "purpose": "computational_routing"},
            {"corridor_id": "F-T11", "from_zone_id": "FALLBACK", "to_zone_id": "T11",
             "positive_direction": "from_to_positive", "purpose": "computational_routing"},
        ])
        b4 = self.boundary(topology, "B4")
        b4["negative_side_zone_ids"] = list(b4["negative_side_zone_ids"]) + ["FALLBACK"]
        self.assertIn("bypass", classify(topology)["B4"]["errors"])

    def test_orientation_conflict(self) -> None:
        topology = eleven_zone_topology()
        b13 = self.boundary(topology, "B13")
        b13["members"] = [dict(row, coefficient=1) for row in b13["members"]]
        self.assertIn("orientation_conflict", classify(topology)["B13"]["errors"])

    def test_undeclared_multi_member_non_cut_is_an_error_single_member_is_a_limit(self) -> None:
        topology = eleven_zone_topology()
        for row in topology["cutsets"]:  # type: ignore[union-attr]
            row.pop("positive_side_zone_ids", None)
            row.pop("negative_side_zone_ids", None)
        b6 = self.boundary(topology, "B6")
        b6["members"] = [{"corridor_id": "AC:T2--T3", "coefficient": 1},
                         {"corridor_id": "AC:T8--T9", "coefficient": 1}]
        rows = classify(topology)
        self.assertEqual(rows["B6"]["classification"], "not_a_cut")
        self.assertEqual(rows["Western_Link"]["classification"], "corridor_limit")
        self.assertEqual(rows["B4"]["classification"], "cut")
        self.assertEqual(rows["B9"]["classification"], "cut")


class LoaderPolicyTests(unittest.TestCase):
    def test_topology_policy_is_required(self) -> None:
        signature = inspect.signature(load_zonal_network_pack)
        self.assertIs(signature.parameters["topology_policy"].default, inspect.Parameter.empty)
        with self.assertRaises(TypeError):
            load_zonal_network_pack(Path("unused"))  # type: ignore[call-arg]
        with self.assertRaisesRegex(ValueError, "topology_policy"):
            load_zonal_network_pack(Path("unused"), topology_policy="lenient")

    def test_value_101_network_pack_loads_under_enforce(self) -> None:
        root = Path(__file__).resolve().parents[1] / "data-packs" / "value-101-network-v1"
        load_zonal_network_pack(root, topology_policy="enforce")


class BuilderUnknownZoneTests(unittest.TestCase):
    def test_misspelt_zone_id_stops_the_build_unless_explicitly_allowed(self) -> None:
        import json

        from tests.test_prompt98_gb_zonal_pack_builder import _json, _sha, make_inventory

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sources").mkdir()
            inventory = make_inventory(root / "sources")
            fleet = inventory.parent / "fleet.csv"
            with fleet.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            rows.append(["gas-x", "ccgt", "10.0", "operating", "generator", "SCOTLND", "1.0", "source_coordinate"])
            with fleet.open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle).writerows(rows)
            payload = json.loads(inventory.read_text(encoding="utf-8"))
            row = next(item for item in payload["objects"] if item["role"] == "model_fleet")
            row["sha256"] = _sha(fleet)
            _json(inventory, payload)
            with self.assertRaisesRegex(ValueError, "gas-x=SCOTLND"):
                build_candidate(inventory, root / "candidate")
            built = build_candidate(
                inventory, root / "candidate-allowed", allow_unknown_zone_fallback=True
            )
            self.assertTrue(built)


if __name__ == "__main__":
    unittest.main()
