from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.catalog import DATASET_SLOTS
from gridform_core.data_pack_validation import validate_data_pack
from gridform_core.domain_readiness import summarise_zonal_network_pack
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.zonal_contracts import (
    BoundaryRatingProfile,
    CutsetMember,
    ETYSBoundary,
    InterconnectorLanding,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZonalAssetMapping,
    ZonalDemand,
    ZonalNetworkPack,
    load_zonal_network_pack,
)


ROOT = Path(__file__).resolve().parents[1]


def signed(pack: ZonalNetworkPack) -> ZonalNetworkPack:
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


def valid_pack(*, three_zones: bool = False) -> ZonalNetworkPack:
    zones = [
        NetworkZone("north", "North", "Northern Powergrid", "England"),
        NetworkZone("south", "South", "UK Power Networks", "England"),
    ]
    corridors = [
        TransportCorridor("north-south", "north", "south", "from_to_positive")
    ]
    cutsets = [
        ETYSBoundary(
            "B6",
            "North to south boundary",
            (CutsetMember("north-south", 1),),
            8.0,
            6.0,
            rating_profile_id="winter-maintenance",
            reverse_limit_method="independent_source",
        )
    ]
    mappings = [
        ZonalAssetMapping("thermal", "north", "generator", "CCGT", 1.0, "source_coordinate"),
        ZonalAssetMapping("wind", "north", "generator", "onshore", 2.0 / 3.0, "regional_share"),
        ZonalAssetMapping("wind", "south", "generator", "onshore", 1.0 / 3.0, "regional_share"),
        ZonalAssetMapping("import:france", "south", "boundary_interconnector", "interconnector", 1.0, "landing_zone"),
    ]
    demand = {"north": (3.0, 4.0), "south": (7.0, 8.0)}
    if three_zones:
        zones.append(NetworkZone("west", "West", "National Grid Electricity Distribution", "Wales"))
        corridors.append(
            TransportCorridor("west-south", "west", "south", "from_to_positive")
        )
        cutsets.append(
            ETYSBoundary(
                "B-west",
                "West overlap",
                (
                    CutsetMember("north-south", -1),
                    CutsetMember("west-south", 1),
                ),
                5.0,
                4.0,
                reverse_limit_method="assumed_symmetric_from_forward",
            )
        )
        mappings.append(
            ZonalAssetMapping("hydro", "west", "generator", "hydro", 1.0, "source_coordinate")
        )
        demand["west"] = (1.0, 1.0)
    national = tuple(sum(values[p] for values in demand.values()) for p in range(2))
    active = ["thermal", "wind", "import:france"] + (["hydro"] if three_zones else [])
    capacities = {"CCGT": 10.0, "onshore": 6.0, "interconnector": 4.0}
    if three_zones:
        capacities["hydro"] = 2.0
    return signed(ZonalNetworkPack(
        network_pack_id="fixture-zonal-v1",
        scientific_sha256="",
        zones=tuple(zones),
        corridors=tuple(corridors),
        cutsets=tuple(cutsets),
        asset_mappings=tuple(mappings),
        zonal_demand=ZonalDemand(("p0", "p1"), demand, national),
        rating_profiles=(
            BoundaryRatingProfile("winter-maintenance", ("p0", "p1"), (1.0, 0.5)),
        ),
        interconnector_landings=(
            InterconnectorLanding("france", "import:france", "south", "signed_profile_envelope"),
        ),
        spatial_audit=SpatialAudit(
            tuple(active),
            capacities,
            capacities,
            1e-8,
            fallback_asset_ids=(),
            excluded_northern_ireland_asset_ids=("ni-generator",),
        ),
        loss_capability_absent_reason="lossless_v1",
    ))


class ZonalContractValidationTests(unittest.TestCase):
    def test_one_zone_and_two_zone_asymmetric_boundary_are_valid(self):
        one = signed(ZonalNetworkPack(
            "one-zone",
            "",
            (NetworkZone("gb", "GB", "aggregate", "England"),),
            (),
            (),
            (ZonalAssetMapping("g", "gb", "generator", "CCGT", 1.0, "aggregate"),),
            ZonalDemand(("p0",), {"gb": (5.0,)}, (5.0,)),
            (),
            (),
            SpatialAudit(("g",), {"CCGT": 10.0}, {"CCGT": 10.0}, 1e-8),
            "lossless_v1",
        ))
        one.validate()
        two = valid_pack()
        two.validate()
        self.assertEqual(two.cutsets[0].forward_limit_mw, 8.0)
        self.assertEqual(two.cutsets[0].reverse_limit_mw, 6.0)
        self.assertEqual(two.rating_profiles[0].multipliers, (1.0, 0.5))

    def test_overlapping_cutsets_and_unconstrained_england_fallback_are_valid(self):
        three = valid_pack(three_zones=True)
        three.validate()
        self.assertEqual(len(three.cutsets), 2)
        fallback = NetworkZone(
            "england-fallback",
            "England fallback",
            "aggregate",
            "England",
            is_unconstrained_fallback=True,
        )
        pack = replace(
            three,
            zones=(*three.zones, fallback),
            corridors=(*three.corridors, TransportCorridor(
                "fallback-south", "england-fallback", "south", "from_to_positive"
            )),
            asset_mappings=(*three.asset_mappings, ZonalAssetMapping(
                "unlocated", "england-fallback", "generator", "solar", 1.0,
                "england_fallback",
            )),
            zonal_demand=replace(
                three.zonal_demand,
                demand_mwh_by_zone={
                    **three.zonal_demand.demand_mwh_by_zone,
                    "england-fallback": (0.0, 0.0),
                },
            ),
            spatial_audit=replace(
                three.spatial_audit,
                active_asset_ids=(*three.spatial_audit.active_asset_ids, "unlocated"),
                capacity_mw_by_technology={
                    **three.spatial_audit.capacity_mw_by_technology,
                    "solar": 1.0,
                },
                mapped_capacity_mw_by_technology={
                    **three.spatial_audit.mapped_capacity_mw_by_technology,
                    "solar": 1.0,
                },
                fallback_asset_ids=("unlocated",),
            ),
            scientific_sha256="",
        )
        pack = signed(pack)
        pack.validate()
        constrained_corridors = {
            member.corridor_id for boundary in pack.cutsets for member in boundary.members
        }
        self.assertNotIn("fallback-south", constrained_corridors)

    def test_corridor_contract_rejects_dc_or_physical_line_fields(self):
        with self.assertRaisesRegex(ValueError, "DC/AC field"):
            TransportCorridor.from_dict({
                "corridor_id": "ab",
                "from_zone_id": "a",
                "to_zone_id": "b",
                "positive_direction": "from_to_positive",
                "reactance_pu": 0.1,
            })
        with self.assertRaisesRegex(ValueError, "routing purpose"):
            replace(
                valid_pack().corridors[0], purpose="physical_line"
            ).validate()

    def test_unknown_duplicate_dangling_disconnected_and_northern_ireland_fail(self):
        base = valid_pack()
        with self.assertRaisesRegex(ValueError, "duplicate zone"):
            replace(base, zones=(base.zones[0], base.zones[0])).validate()
        with self.assertRaisesRegex(ValueError, "dangling"):
            replace(
                base,
                corridors=(replace(base.corridors[0], to_zone_id="missing"),),
            ).validate()
        island = NetworkZone("island", "Island", "DSO", "Scotland")
        with self.assertRaisesRegex(ValueError, "disconnected unexplained"):
            replace(base, zones=(*base.zones, island)).validate()
        with self.assertRaisesRegex(ValueError, "Northern Ireland"):
            replace(
                base,
                zones=(replace(base.zones[0], nation="Northern Ireland"), *base.zones[1:]),
            ).validate()

    def test_cutset_members_limits_profiles_and_directions_fail_closed(self):
        base = valid_pack()
        boundary = base.cutsets[0]
        with self.assertRaisesRegex(ValueError, "empty"):
            replace(base, cutsets=(replace(boundary, members=()),)).validate()
        with self.assertRaisesRegex(ValueError, "duplicate signed member"):
            replace(
                base,
                cutsets=(replace(boundary, members=(boundary.members[0], boundary.members[0])),),
            ).validate()
        with self.assertRaisesRegex(ValueError, "coefficient"):
            replace(
                base,
                cutsets=(replace(boundary, members=(CutsetMember("north-south", 0),)),),
            ).validate()
        with self.assertRaisesRegex(ValueError, "negative"):
            replace(base, cutsets=(replace(boundary, reverse_limit_mw=-1.0),)).validate()
        with self.assertRaisesRegex(ValueError, "multiplier"):
            replace(
                base,
                rating_profiles=(replace(base.rating_profiles[0], multipliers=(1.0, 1.1)),),
            ).validate()
        with self.assertRaisesRegex(ValueError, "positive direction"):
            replace(
                base,
                corridors=(replace(base.corridors[0], positive_direction="both"),),
            ).validate()

    def test_mapping_demand_capacity_interconnector_and_identity_fail_closed(self):
        base = valid_pack()
        with self.assertRaisesRegex(ValueError, "active assets"):
            replace(
                base,
                asset_mappings=tuple(
                    row for row in base.asset_mappings if row.asset_id != "thermal"
                ),
            ).validate()
        with self.assertRaisesRegex(ValueError, "share"):
            replace(
                base,
                asset_mappings=(*base.asset_mappings, replace(base.asset_mappings[0], zone_id="south")),
            ).validate()
        with self.assertRaisesRegex(ValueError, "demand residual"):
            replace(
                base,
                zonal_demand=replace(base.zonal_demand, national_demand_mwh=(9.0, 12.0)),
            ).validate()
        with self.assertRaisesRegex(ValueError, "capacity reconciliation"):
            replace(
                base,
                spatial_audit=replace(
                    base.spatial_audit,
                    mapped_capacity_mw_by_technology={"CCGT": 9.0, "onshore": 6.0, "interconnector": 4.0},
                ),
            ).validate()
        with self.assertRaisesRegex(ValueError, "double counted"):
            replace(
                base,
                corridors=(TransportCorridor(
                    "import:france", "north", "south", "from_to_positive"
                ),),
                cutsets=(),
            ).validate()
        with self.assertRaisesRegex(ValueError, "scientific SHA-256"):
            replace(base, scientific_sha256="0" * 64).validate()

    def test_nested_inputs_are_frozen_and_round_trip(self):
        source = {"north": [3.0, 4.0], "south": [7.0, 8.0]}
        demand = ZonalDemand(("p0", "p1"), source, (10.0, 12.0))
        source["north"][0] = 999.0
        self.assertEqual(demand.demand_mwh_by_zone["north"][0], 3.0)
        base = valid_pack(three_zones=True)
        restored = ZonalNetworkPack.from_dict(base.to_dict())
        restored.validate()
        self.assertEqual(restored.to_dict(), base.to_dict())


class ZonalPackLoaderAndRegistryTests(unittest.TestCase):
    def test_example_pack_loads_and_hashes_every_required_binding(self):
        pack_root = ROOT / "examples" / "zonal-network-pack"
        loaded = load_zonal_network_pack(pack_root, topology_policy="enforce")
        loaded.validate()
        self.assertEqual(loaded.network_pack_id, "force-zonal-template-v1")
        self.assertEqual(len(loaded.zones), 3)
        self.assertTrue(loaded.spatial_audit.source_sha256_by_role)
        summary = summarise_zonal_network_pack(loaded)
        self.assertEqual(summary["status"], "data_ready")
        self.assertEqual(summary["metrics"]["zones"]["value"], 3)
        self.assertEqual(summary["loss_capability"], {
            "status": "absent", "reason": "lossless_v1",
        })

    def test_zonal_roles_are_conditional_and_do_not_change_base_25(self):
        registry = workspace_registry(ROOT / "missing-local-modules")
        self.assertEqual(len(DATASET_SLOTS), 25)
        self.assertEqual(
            registry.extension_registry.conditional_dataset_slots(()), ()
        )
        roles = registry.extension_registry.conditional_dataset_slots(
            ("value-zonal-redispatch-extension",)
        )
        required = {row["role"] for row in roles if row["required"]}
        self.assertEqual(required, {
            "value.zonal.zones",
            "value.zonal.corridors",
            "value.zonal.cutsets",
            "value.zonal.asset-map",
            "value.zonal.demand",
            "value.zonal.ratings",
            "value.zonal.interconnector-landings",
            "value.zonal.spatial-audit",
        })
        self.assertIn("value.zonal.geometry", {row["role"] for row in roles})

    def test_data_pack_validator_checks_the_conditional_zonal_roles(self):
        pack_root = ROOT / "examples" / "zonal-network-pack"
        manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
        registry = workspace_registry(ROOT / "missing-local-modules")
        slots = registry.extension_registry.conditional_dataset_slots(
            ("value-zonal-redispatch-extension",)
        )
        report = validate_data_pack(pack_root, manifest, slots, full_year_periods=2)
        self.assertEqual(report["valid_required_count"], 8)
        self.assertEqual(report["required_count"], 8)
        self.assertFalse(report["errors"], report["errors"])

    def test_loader_rejects_changed_member_even_if_binding_hash_is_rewritten(self):
        source = ROOT / "examples" / "zonal-network-pack"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "pack"
            import shutil
            shutil.copytree(source, destination)
            target = destination / "files" / "zones.json"
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["zones"][0]["display_name"] = "Changed"
            target.write_text(json.dumps(payload), encoding="utf-8")
            manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
            manifest["bindings"]["value.zonal.zones"]["sha256"] = hashlib.sha256(
                target.read_bytes()
            ).hexdigest()
            (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "scientific SHA-256"):
                load_zonal_network_pack(destination, topology_policy="enforce")


if __name__ == "__main__":
    unittest.main()
