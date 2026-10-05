from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.gb_zonal_pack_builder import (
    REQUIRED_SOURCE_ROLES,
    _repd_comparison,
    build_candidate,
    sign_and_install_candidate,
    validate_source_inventory,
)
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.zonal_contracts import load_zonal_network_pack
from scripts.validate_gb_zonal_pack import validate as validate_candidate


def _json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="",
    )


def _csv(path: Path, rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_inventory(root: Path) -> Path:
    periods = ["p0", "p1"]
    _json(root / "dso.geojson", {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "north",
                "properties": {
                    "zone_id": "north", "display_name": "North", "dso_owner": "DSO N",
                    "nation": "Scotland", "geometry_feature_id": "north",
                },
                "geometry": {"type": "Polygon", "coordinates": [[[-4, 54], [-1, 54], [-1, 58], [-4, 58], [-4, 54]]]},
            },
            {
                "type": "Feature",
                "id": "south",
                "properties": {
                    "zone_id": "south", "display_name": "South", "dso_owner": "DSO S",
                    "nation": "England", "geometry_feature_id": "south",
                },
                "geometry": {"type": "Polygon", "coordinates": [[[-4, 50], [2, 50], [2, 54], [-4, 54], [-4, 50]]]},
            },
            {
                "type": "Feature",
                "id": "ENGLAND_FALLBACK",
                "properties": {
                    "zone_id": "ENGLAND_FALLBACK", "display_name": "Unlocated England",
                    "dso_owner": "VALUE fallback", "nation": "England",
                    "is_unconstrained_fallback": True,
                },
                "geometry": None,
            },
            {
                "type": "Feature",
                "id": "north-sliver",
                "properties": {
                    "zone_id": "north-sliver", "display_name": "North sliver",
                    "dso_owner": "DSO N", "nation": "Scotland", "merge_into": "north",
                },
                "geometry": {"type": "Polygon", "coordinates": [[[-1, 54], [-0.8, 54], [-0.8, 54.2], [-1, 54.2], [-1, 54]]]},
            },
        ],
    })
    _json(root / "etys.json", {
        "corridors": [
            {
                "corridor_id": "north-south", "from_zone_id": "north", "to_zone_id": "south",
                "positive_direction": "from_to_positive",
            },
            {
                "corridor_id": "fallback-south", "from_zone_id": "ENGLAND_FALLBACK",
                "to_zone_id": "south", "positive_direction": "from_to_positive",
            },
        ],
        "boundaries": [
            {
                "boundary_id": "B_NS", "display_name": "North to South",
                "source_partition_zone_ids": ["north"], "sink_partition_zone_ids": ["south"],
                "forward_limit_mw": 100.0, "source_direction": "north_to_south",
                "expected_corridor_ids": ["north-south"],
            }
        ],
        "rating_profiles": [],
        "unconstrained_zone_ids": ["ENGLAND_FALLBACK"],
    })
    _csv(root / "demand.csv", [
        ["period_id", "national_demand_mwh"], ["p0", 100.0], ["p1", 120.0],
    ])
    _csv(root / "regional.csv", [
        ["period_id", "zone_id", "weight", "method"],
        ["*", "north", 0.4, "calibrated"], ["*", "south", 0.6, "calibrated"],
        ["*", "ENGLAND_FALLBACK", 0.0, "static_share_fallback"],
    ])
    _csv(root / "fleet.csv", [
        ["asset_id", "technology", "capacity_mw", "status", "asset_class", "zone_id", "share", "mapping_method"],
        ["wind-n", "onshore", 20.0, "operating", "generator", "north", 1.0, "source_coordinate"],
        ["gas-s", "ccgt", 30.0, "operating", "generator", "south", 1.0, "source_coordinate"],
        ["battery-u", "battery", 5.0, "operating", "storage", "", 1.0, "unlocated_england_fallback"],
    ])
    _csv(root / "repd.csv", [
        ["asset_id", "technology", "capacity_mw", "status"],
        ["wind-n", "onshore", 20.0, "Operational"],
    ])
    _csv(root / "landings.csv", [
        ["interconnector_id", "asset_id", "zone_id", "envelope_semantics", "technology", "capacity_mw"],
        ["ifa", "import-ifa", "south", "signed_profile_envelope", "interconnector", 10.0],
    ])
    profile = {
        "profile_id": "wind-north",
        "economic_owner_id": "wind-agent",
        "technology": "onshore",
        "zone_id": "north",
        "period_ids": periods,
        "availability": [0.4, 0.6],
        "aggregated_capacity_mw": 20.0,
        "source_ids": ["wind-n"],
        "aggregation_method": "fixture",
        "source_sha256": "c" * 64,
        "schema_version": "value.zonal-availability-profile/v1",
    }
    representative = {
        "schema_version": "value.zonal-availability-bundle/v1", "mode": "representative_point",
        "period_ids": periods, "profiles": [profile], "source_sha256": "a" * 64,
        "runtime_opens_repd_or_era5": False, "scientific_sha256": "", "provenance": {},
    }
    aggregated = {
        "schema_version": "value.zonal-availability-bundle/v1", "mode": "repd_era5_mw_aggregated",
        "period_ids": periods,
        "profiles": [{**profile, "profile_id": "wind-north-aggregated", "aggregation_method": "fixture_mw_weighted"}],
        "source_sha256": "b" * 64,
        "runtime_opens_repd_or_era5": False, "scientific_sha256": "", "provenance": {},
    }
    # Empty profile bundles are sufficient for the pack-builder fixture. Prompt 97 separately
    # verifies profile-level aggregation; Prompt 98 verifies clocks, mode and immutability.
    for name, payload in (("weather-representative.json", representative), ("weather-aggregated.json", aggregated)):
        canonical = dict(payload)
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        canonical["scientific_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        _json(root / name, canonical)

    names = {
        "dso_areas": "dso.geojson",
        "etys_boundaries": "etys.json",
        "neso_national_demand": "demand.csv",
        "regional_demand_evidence": "regional.csv",
        "model_fleet": "fleet.csv",
        "repd": "repd.csv",
        "interconnector_landings": "landings.csv",
        "era5_representative_profiles": "weather-representative.json",
        "era5_aggregated_profiles": "weather-aggregated.json",
    }
    objects = []
    for role in REQUIRED_SOURCE_ROLES:
        path = root / names[role]
        objects.append({
            "role": role,
            "required": True,
            "authoritative_url": f"https://example.invalid/{role}",
            "publisher": "Prompt 98 deterministic fixture",
            "title": role,
            "publication_date": "2026-01-01",
            "source_version": "fixture-v1",
            "licence": "CC0-1.0",
            "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "redistribution_decision": "redistributable",
            "local_path": names[role],
            "sha256": _sha(path),
            "access_result": "present",
            "transformation_step": "prompt98 fixture transform",
            "coordinate_reference_system": "EPSG:4326" if role == "dso_areas" else None,
        })
    inventory = root / "inventory.json"
    _json(inventory, {
        "schema_version": "value.gb-zonal-source-inventory/v1",
        "inventory_id": "prompt98-test-fixture",
        "objects": objects,
    })
    return inventory


class Prompt98GbZonalPackBuilderTests(unittest.TestCase):
    def test_owner_approval_signs_and_atomically_installs_the_exact_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = make_inventory(root)
            candidate = root / "candidate"
            built = build_candidate(inventory, candidate)
            before = {
                path.relative_to(candidate).as_posix(): _sha(path)
                for path in candidate.rglob("*") if path.is_file()
            }
            slots = workspace_registry(root / "missing-modules").extension_registry.conditional_dataset_slots(
                ("value-zonal-redispatch-extension",)
            )

            receipt = sign_and_install_candidate(
                candidate,
                state_root=root / "state",
                dataset_slots=slots,
                approved_by="Hanzhe Xing",
                approved_at="2026-08-21T12:00:00+00:00",
                expected_candidate_scientific_sha256=str(built["candidate_scientific_sha256"]),
            )

            expected_id = "force-gb-zonal-network-v1-" + str(
                built["candidate_scientific_sha256"]
            )[:12]
            self.assertEqual(receipt["network_pack_id"], expected_id)
            self.assertEqual(
                receipt["approved_candidate_scientific_sha256"],
                built["candidate_scientific_sha256"],
            )
            self.assertEqual(receipt["signature_type"], "local_approval_attestation")
            self.assertEqual(receipt["approved_by"], "Hanzhe Xing")
            self.assertEqual(receipt["validation"], {"passed": 8, "failed": 0, "total": 9})
            installed = root / "state" / "installed-packs" / expected_id
            loaded = load_zonal_network_pack(installed, topology_policy="enforce")
            self.assertEqual(loaded.network_pack_id, expected_id)
            self.assertEqual(loaded.scientific_sha256, receipt["installed_scientific_sha256"])
            self.assertNotEqual(
                receipt["installed_scientific_sha256"],
                receipt["approved_candidate_scientific_sha256"],
            )
            rights = json.loads((installed / "RIGHTS.json").read_text(encoding="utf-8"))
            self.assertEqual(rights["complete_bundle_redistribution"], "local_rights_governed")
            self.assertTrue((root / "state" / "approvals" / f"{expected_id}.json").is_file())
            after = {
                path.relative_to(candidate).as_posix(): _sha(path)
                for path in candidate.rglob("*") if path.is_file()
            }
            self.assertEqual(after, before, "Signing must not mutate the approved candidate")

    def test_owner_approval_rejects_a_different_hash_before_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = make_inventory(root)
            candidate = root / "candidate"
            build_candidate(inventory, candidate)
            slots = workspace_registry(root / "missing-modules").extension_registry.conditional_dataset_slots(
                ("value-zonal-redispatch-extension",)
            )

            with self.assertRaisesRegex(ValueError, "approved candidate hash"):
                sign_and_install_candidate(
                    candidate,
                    state_root=root / "state",
                    dataset_slots=slots,
                    approved_by="Hanzhe Xing",
                    approved_at="2026-08-21T12:00:00+00:00",
                    expected_candidate_scientific_sha256="0" * 64,
                )

            self.assertFalse((root / "state" / "installed-packs").exists())

    def test_repd_review_compares_battery_power_against_all_non_pumped_battery_types(self) -> None:
        rows = [
            {"technology": "battery", "capacity_mw": "2000", "status": "Operational"},
            {"technology": "pumped_hydro", "capacity_mw": "500", "status": "Operational"},
        ]
        result = _repd_comparison(
            rows,
            {"1c": 50.0, "0.5c": 100.0, "0.25c": 200.0, "pumped_hydro": 500.0},
        )

        by_technology = {row["technology"]: row for row in result}
        self.assertEqual(by_technology["battery"]["model_active_capacity_mw"], 350.0)
        self.assertEqual(by_technology["pumped_hydro"]["difference_mw"], 0.0)

    def test_complete_inventory_builds_deterministically_without_installing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = make_inventory(root)
            first = build_candidate(inventory, root / "candidate-a")
            second = build_candidate(inventory, root / "candidate-b")
            self.assertEqual(first["status"], "awaiting_owner_signoff")
            self.assertEqual(first["candidate_scientific_sha256"], second["candidate_scientific_sha256"])
            self.assertEqual(first["scientific_file_sha256"], second["scientific_file_sha256"])
            self.assertEqual(first["maximum_demand_residual_mwh"], 0.0)
            self.assertEqual(first["assumed_symmetric_boundaries"], ["B_NS"])
            self.assertEqual(first["merged_dso_features"], {"north-sliver": "north"})
            self.assertFalse((root / "candidate-a" / "manifest.json").exists())
            self.assertTrue((root / "candidate-a" / "candidate-manifest.json").exists())
            validation = validate_candidate(root / "candidate-a")
            self.assertEqual(validation["status"], "passed_unsigned_candidate_validation")
            self.assertEqual(validation["owner_signoff"], "pending")
            serialized = (root / "candidate-a" / "candidate-manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("C:\\\\", serialized)
            review = json.loads(
                (root / "candidate-a" / "review" / "reconciliation-and-rights.json").read_text(encoding="utf-8")
            )
            self.assertEqual(review["source_direction_by_boundary"], {"B_NS": "north_to_south"})
            self.assertTrue(review["region_to_zone_weights"])
            map_svg = (root / "candidate-a" / "review" / "zone-map.svg").read_text(encoding="utf-8")
            self.assertIn('data-kind="corridor"', map_svg)
            self.assertIn('data-kind="power-asset"', map_svg)
            self.assertIn('data-kind="interconnector"', map_svg)
            self.assertIn('data-kind="zone-index"', map_svg)
            self.assertIn('data-kind="zone-legend"', map_svg)
            self.assertIn('data-kind="symbol-legend"', map_svg)
            self.assertIn('viewBox="0 0 1320 800"', map_svg)
            manifest_path = root / "candidate-a" / "candidate-manifest.json"
            tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
            tampered["bindings"]["value.zonal.zones"]["sha256"] = "f" * 64
            _json(manifest_path, tampered)
            with self.assertRaisesRegex(ValueError, "binding identity"):
                validate_candidate(root / "candidate-a")

    def test_missing_rights_hash_mismatch_and_invalid_cut_stop_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_path = make_inventory(root)
            payload = json.loads(inventory_path.read_text(encoding="utf-8"))
            payload["objects"][0]["redistribution_decision"] = "unclear"
            _json(inventory_path, payload)
            with self.assertRaisesRegex(ValueError, "rights"):
                validate_source_inventory(inventory_path)

            inventory_path = make_inventory(root)
            payload = json.loads(inventory_path.read_text(encoding="utf-8"))
            payload["objects"][1]["sha256"] = "0" * 64
            _json(inventory_path, payload)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                build_candidate(inventory_path, root / "bad-hash")

            inventory_path = make_inventory(root)
            etys = json.loads((root / "etys.json").read_text(encoding="utf-8"))
            etys["boundaries"][0]["expected_corridor_ids"] = ["fallback-south"]
            _json(root / "etys.json", etys)
            payload = json.loads(inventory_path.read_text(encoding="utf-8"))
            row = next(item for item in payload["objects"] if item["role"] == "etys_boundaries")
            row["sha256"] = _sha(root / "etys.json")
            _json(inventory_path, payload)
            with self.assertRaisesRegex(ValueError, "cut-set"):
                build_candidate(inventory_path, root / "bad-cut")

    def test_weather_bundle_must_cover_each_active_vre_technology_zone(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_path = make_inventory(root)
            weather_path = root / "weather-representative.json"
            weather = json.loads(weather_path.read_text(encoding="utf-8"))
            weather["profiles"] = []
            weather["scientific_sha256"] = ""
            encoded = json.dumps(weather, sort_keys=True, separators=(",", ":"))
            weather["scientific_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            _json(weather_path, weather)
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            row = next(
                item for item in inventory["objects"]
                if item["role"] == "era5_representative_profiles"
            )
            row["sha256"] = _sha(weather_path)
            _json(inventory_path, inventory)
            with self.assertRaisesRegex(ValueError, "active VRE"):
                build_candidate(inventory_path, root / "missing-weather-coverage")


if __name__ == "__main__":
    unittest.main()
