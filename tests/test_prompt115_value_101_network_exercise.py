from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from tests.local_api_harness import start_local_api
from gridform_core.application import _network_period_ids_for_year
from gridform_core.value_101 import value_101_study
from gridform_core.value_101_lifecycle import build_value_101_network_pair
from gridform_core.frontend_contract import resolve_study_draft
from gridform_core.catalog import DATASET_SLOTS
from gridform_core.run_policy import validate_pack_run_mode
from gridform_core.v2.module_manifest import builtin_registry
from gridform_core.zonal_contracts import ZONAL_ROLES, load_zonal_network_pack
from scripts.build_value_101_network_pack import (
    NETWORK_PACK_ID,
    _read_demand_mwh,
    build_network_pack,
)
from scripts.install_synthetic_pack import (
    UPGRADABLE_BUILTIN_TREES,
    _replace_known_builtin,
    _tree_sha256,
    install_builtin_packs,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data-packs" / "value-101-baseline-v1"
NETWORK = ROOT / "data-packs" / NETWORK_PACK_ID


def payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def series(path: Path) -> list[float]:
    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
    values = []
    for row in rows:
        try:
            values.append(float(row[0]))
        except ValueError:
            continue
    return values


class Value101NetworkPackTests(unittest.TestCase):
    def test_short_smoke_selects_from_a_single_full_year_reference_clock(self) -> None:
        period_ids = tuple(f"2022-{period:05d}" for period in range(17_520))
        self.assertEqual(
            _network_period_ids_for_year(period_ids, year=2025, periods=2),
            period_ids[:2],
        )

    def test_multi_year_network_clock_selects_the_requested_year(self) -> None:
        period_ids = tuple(
            f"{year}:{period}" for year in (2025, 2026) for period in range(17_520)
        )
        self.assertEqual(
            _network_period_ids_for_year(period_ids, year=2025, periods=17_520),
            period_ids[:17_520],
        )
        self.assertEqual(
            _network_period_ids_for_year(period_ids, year=2026, periods=17_520),
            period_ids[17_520:],
        )
        with self.assertRaisesRegex(ValueError, "has no 2027 clock"):
            _network_period_ids_for_year(period_ids, year=2027, periods=17_520)

    def test_builder_is_deterministic_and_adds_only_network_roles(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            left = Path(first) / NETWORK_PACK_ID
            right = Path(second) / NETWORK_PACK_ID
            first_report = build_network_pack(BASELINE, left)
            second_report = build_network_pack(BASELINE, right)
            self.assertEqual(first_report["tree_sha256"], second_report["tree_sha256"])
            left_manifest = payload(left / "manifest.json")
            right_manifest = payload(right / "manifest.json")
            baseline_manifest = payload(BASELINE / "manifest.json")
            self.assertEqual(left_manifest, right_manifest)
            self.assertEqual(
                set(left_manifest["bindings"]),
                set(baseline_manifest["bindings"]) | set(ZONAL_ROLES),
            )
            self.assertEqual(left_manifest["periods_per_year"], 17_520)
            self.assertTrue(left_manifest["annual_economics_eligible"])
            self.assertIn("two_year", left_manifest["allowed_run_modes"])
            validate_pack_run_mode(left_manifest, "two_year")
            for role, binding in baseline_manifest["bindings"].items():
                self.assertEqual(
                    left_manifest["bindings"][role]["sha256"], binding["sha256"]
                )

    def test_checked_in_pack_is_complete_three_zone_and_asymmetric(self) -> None:
        model = load_zonal_network_pack(NETWORK, topology_policy="enforce")
        self.assertEqual([zone.zone_id for zone in model.zones], ["north", "central", "south"])
        self.assertEqual(
            [(row.corridor_id, row.from_zone_id, row.to_zone_id) for row in model.corridors],
            [
                ("north-central", "north", "central"),
                ("central-south", "central", "south"),
            ],
        )
        self.assertTrue(any(row.forward_limit_mw != row.reverse_limit_mw for row in model.cutsets))
        self.assertEqual(len(model.zonal_demand.period_ids), 35_040)
        self.assertEqual(model.zonal_demand.period_ids[0], "2025:0")
        self.assertEqual(model.zonal_demand.period_ids[-1], "2026:17519")
        planning_mapping = next(
            row for row in model.asset_mappings
            if row.asset_id == "value101-solar-planning"
        )
        self.assertEqual(planning_mapping.zone_id, "south")
        self.assertEqual(planning_mapping.mapping_method, "synthetic_project_location")
        self.assertNotIn(
            "value101-solar-planning", model.spatial_audit.active_asset_ids
        )
        derivation = payload(NETWORK / "derivation.json")
        event = derivation["known_congestion_fixture"]
        self.assertEqual(event["period_id"], "2025:31")
        self.assertGreater(event["unconstrained_north_export_mwh"], event["north_central_limit_mwh"])
        self.assertFalse(event["all_periods_have_north_export_congestion"])
        self.assertLess(
            event["minimum_onshore_only_north_export_mwh"],
            event["normal_north_central_limit_mwh"],
        )
        self.assertEqual(derivation["excluded_methods"], [
            "DC load flow", "AC power flow", "N-1 security", "transmission expansion",
        ])

    def test_network_demand_repeats_the_baseline_national_clock(self) -> None:
        manifest = payload(BASELINE / "manifest.json")
        demand_path = BASELINE / manifest["bindings"]["demand.real"]["uri"]
        baseline_mwh = [value * 0.5 for value in series(demand_path)]
        model = load_zonal_network_pack(NETWORK, topology_policy="enforce")
        self.assertEqual(list(model.zonal_demand.national_demand_mwh[:17_520]), baseline_mwh)
        self.assertEqual(list(model.zonal_demand.national_demand_mwh[17_520:]), baseline_mwh)

    def test_installer_places_the_same_pack_in_base_and_overlay_stores(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            reports = install_builtin_packs(state)
            self.assertIn(NETWORK_PACK_ID, {row["pack_id"] for row in reports})
            base = state / "data-packs" / NETWORK_PACK_ID
            overlay = state / "data-workbench" / "installed-packs" / NETWORK_PACK_ID
            self.assertTrue(base.is_dir())
            self.assertTrue(overlay.is_dir())
            self.assertEqual(
                hashlib.sha256((base / "manifest.json").read_bytes()).hexdigest(),
                hashlib.sha256((overlay / "manifest.json").read_bytes()).hexdigest(),
            )

    def test_installer_upgrades_only_a_known_builtin_network_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            install_builtin_packs(state)
            base = state / "data-packs" / NETWORK_PACK_ID
            overlay = state / "data-workbench" / "installed-packs" / NETWORK_PACK_ID
            for root in (base, overlay):
                marker = root / "known-old-revision.txt"
                marker.write_text("known bundled revision\n", encoding="utf-8")
            old_tree = _tree_sha256(base)
            self.assertEqual(old_tree, _tree_sha256(overlay))
            with patch.dict(
                UPGRADABLE_BUILTIN_TREES,
                {NETWORK_PACK_ID: frozenset({old_tree})},
                clear=False,
            ):
                report = {
                    row["pack_id"]: row for row in install_builtin_packs(state)
                }[NETWORK_PACK_ID]
            self.assertEqual(report["status"], "upgraded_builtin")
            self.assertEqual(report["network_overlay_status"], "upgraded_builtin")
            self.assertTrue(Path(report["previous_revision_backup"]).is_dir())
            self.assertTrue(Path(report["previous_overlay_backup"]).is_dir())
            self.assertEqual(_tree_sha256(base), _tree_sha256(NETWORK))
            self.assertEqual(_tree_sha256(overlay), _tree_sha256(NETWORK))
            user_marker = base / "user-owned-change.txt"
            user_marker.write_text("do not replace\n", encoding="utf-8")
            conflict = {
                row["pack_id"]: row for row in install_builtin_packs(state)
            }[NETWORK_PACK_ID]
            self.assertEqual(conflict["status"], "conflict_preserved")
            self.assertTrue(user_marker.is_file())

    def test_builtin_upgrade_does_not_touch_an_occupied_legacy_staging_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            install_builtin_packs(state)
            base = state / "data-packs" / NETWORK_PACK_ID
            (base / "known-old-revision.txt").write_text("old\n", encoding="utf-8")
            old_tree = _tree_sha256(base)
            staging = base.with_name(NETWORK_PACK_ID + ".installing")
            staging.mkdir()
            marker = staging / "user-file.txt"
            marker.write_text("preserve\n", encoding="utf-8")
            with patch.dict(
                UPGRADABLE_BUILTIN_TREES,
                {NETWORK_PACK_ID: frozenset({old_tree})},
                clear=False,
            ):
                report = {
                    row["pack_id"]: row for row in install_builtin_packs(state)
                }[NETWORK_PACK_ID]
            self.assertEqual(report["status"], "upgraded_builtin")
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve\n")

    def test_builtin_upgrade_rolls_back_a_concurrent_destination_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            install_builtin_packs(state)
            base = state / "data-packs" / NETWORK_PACK_ID
            (base / "known-old-revision.txt").write_text("old\n", encoding="utf-8")
            old_tree = _tree_sha256(base)
            real_tree_sha256 = _tree_sha256

            def hash_after_change(root: Path):
                if (
                    root.name.startswith(NETWORK_PACK_ID + "-")
                ):
                    (root / "concurrent-user-change.txt").write_text(
                        "preserve\n", encoding="utf-8"
                    )
                return real_tree_sha256(root)

            with patch(
                "scripts.install_synthetic_pack._tree_sha256",
                side_effect=hash_after_change,
            ):
                with self.assertRaisesRegex(ValueError, "changed during staging"):
                    _replace_known_builtin(
                        NETWORK,
                        base,
                        NETWORK_PACK_ID,
                        old_tree,
                        state / "builtin-pack-backups" / "test",
                    )
            self.assertEqual(
                (base / "concurrent-user-change.txt").read_text(encoding="utf-8"),
                "preserve\n",
            )
            self.assertFalse(base.with_name(NETWORK_PACK_ID + ".previous").exists())
            self.assertFalse(any(base.parent.glob(f".{NETWORK_PACK_ID}.installing-*")))

    def test_builtin_upgrade_preserves_changes_after_the_commit_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            install_builtin_packs(state)
            base = state / "data-packs" / NETWORK_PACK_ID
            (base / "known-old-revision.txt").write_text("old\n", encoding="utf-8")
            old_tree = _tree_sha256(base)
            real_tree_sha256 = _tree_sha256

            def hash_then_change(root: Path):
                actual = real_tree_sha256(root)
                if (
                    root.name.startswith(NETWORK_PACK_ID + "-")
                ):
                    (root / "post-hash-user-change.txt").write_text(
                        "preserve\n", encoding="utf-8"
                    )
                return actual

            with patch(
                "scripts.install_synthetic_pack._tree_sha256",
                side_effect=hash_then_change,
            ):
                backup = _replace_known_builtin(
                    NETWORK,
                    base,
                    NETWORK_PACK_ID,
                    old_tree,
                    state / "builtin-pack-backups" / "test",
                )
            self.assertEqual(
                (backup / "post-hash-user-change.txt").read_text(encoding="utf-8"),
                "preserve\n",
            )
            self.assertEqual(_tree_sha256(base), _tree_sha256(NETWORK))

    def test_matched_pair_changes_only_the_declared_network_selection(self) -> None:
        pair, identity = build_value_101_network_pair(
            value_101_study(), network_pack_id=NETWORK_PACK_ID
        )
        copperplate = pair["copperplate"]
        constrained = pair["constrained"]
        self.assertEqual(copperplate["data_pack_id"], NETWORK_PACK_ID)
        self.assertEqual(constrained["data_pack_id"], NETWORK_PACK_ID)
        self.assertEqual(copperplate["modules"]["psm"], "value-staged-bid-at-cost-psm")
        self.assertEqual(constrained["modules"]["psm"], "value-staged-bid-at-cost-psm")
        self.assertEqual(
            copperplate["modules"]["weather_spatializer"],
            "value-representative-point-weather",
        )
        self.assertEqual(
            constrained["modules"]["weather_spatializer"],
            "value-representative-point-weather",
        )
        self.assertEqual(
            copperplate["maturity_acknowledgements"],
            {
                "module:value-representative-point-weather@1.0.0":
                    "value.experimental-ack/v1"
            },
        )
        self.assertEqual(copperplate["modules"]["balancing"], "value-copperplate-balancing")
        self.assertEqual(constrained["modules"]["balancing"], "value-zonal-redispatch-balancing")
        self.assertEqual(constrained["solver_contract"]["method"], "highs-ds")
        self.assertTrue(constrained["solver_contract"]["is_builtin_default"])
        self.assertNotIn(
            "solver-contract:value-zonal-redispatch-balancing@2.0.0",
            constrained["maturity_acknowledgements"],
        )
        self.assertTrue(identity["ahead_inputs_identical"])
        self.assertTrue(identity["only_network_delivery_changed"])
        self.assertEqual(identity["controlled_dimensions"], [
            "modules.balancing",
            "selected_extensions",
            "market_configuration",
            "solver_contract",
            "maturity_acknowledgements",
        ])

    def test_network_lesson_rejects_a_seed_outside_2025_to_2026(self) -> None:
        seed = value_101_study()
        seed["start_year"] = 2030
        seed["end_year"] = 2031
        with self.assertRaisesRegex(ValueError, "2025 to 2026"):
            build_value_101_network_pair(seed, network_pack_id=NETWORK_PACK_ID)

    def test_network_builder_does_not_skip_a_corrupt_data_period(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "demand.csv"
            path.write_text(
                "value\n1\ncorrupt\n" + "\n".join("1" for _ in range(17_519)) + "\n",
                encoding="utf-8",
            )
            manifest = {"bindings": {"demand.real": {"uri": "demand.csv"}}}
            with self.assertRaisesRegex(ValueError, "row 3"):
                _read_demand_mwh(root, manifest)

    def test_both_matched_studies_resolve_through_the_ordinary_registry(self) -> None:
        pair, _ = build_value_101_network_pair(
            value_101_study(), network_pack_id=NETWORK_PACK_ID
        )
        registry = builtin_registry()
        manifest = payload(NETWORK / "manifest.json")
        catalog = [row.to_dict() for row in registry.manifests().values()]
        for role, project in pair.items():
            with self.subTest(role=role):
                result = resolve_study_draft(
                    project,
                    registry=registry,
                    module_catalog=catalog,
                    base_dataset_slots=DATASET_SLOTS,
                    available_data_roles=tuple(manifest["bindings"]),
                )
                self.assertTrue(result["valid"], result["errors"])

    def test_loopback_api_previews_then_creates_two_studies_without_running(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-network-api-") as temporary:
            state = Path(temporary)
            install_builtin_packs(state)
            (state / "runs").mkdir()
            patches = (
                patch.object(server, "STATE_ROOT", state),
                patch.object(server, "PACKS_ROOT", state / "data-packs"),
                patch.object(server, "PROJECTS_ROOT", state / "projects"),
                patch.object(server, "RUNS_ROOT", state / "runs"),
                patch.object(server, "TRASH_ROOT", state / "trash"),
                patch.dict(os.environ, {"VALUE_DATA_HOME": str(state)}),
            )
            for item in patches:
                item.start()
            api = start_local_api(data_home=Path(temporary), patch_state_roots=False)
            httpd, origin, _session = api.start()
            try:
                status, baseline = self._request(
                    origin + "/api/tutorials/value-101/studies", {}
                )
                self.assertEqual(status, 201, baseline)
                route = origin + "/api/tutorials/value-101/studies/value-101-baseline/network-pair"
                status, preview = self._request(route, {"dry_run": True})
                self.assertEqual(status, 200, preview)
                self.assertTrue(preview["identity"]["only_network_delivery_changed"])
                self.assertFalse(preview["run_started"])
                self.assertEqual(len(list((state / "projects").glob("*/project.json"))), 1)
                status, created = self._request(route, {})
                self.assertEqual(status, 201, created)
                self.assertFalse(created["run_started"])
                self.assertEqual(set(created["studies"]), {"copperplate", "constrained"})
                self.assertEqual(len(list((state / "projects").glob("*/project.json"))), 3)
                self.assertEqual(list((state / "runs").iterdir()), [])
                for project_id in (
                    "value-101-network-copperplate",
                    "value-101-network-constrained",
                ):
                    with self.subTest(project_id=project_id):
                        status, preflight = self._request(
                            origin + f"/api/projects/{project_id}/preflight",
                            {"mode": "two_year"},
                        )
                        self.assertEqual(status, 200, preflight)
                        self.assertTrue(preflight["accepted"], preflight["errors"])
                        self.assertEqual(preflight["estimates"]["periods"], 35_040)
                        self.assertTrue(
                            preflight["checks"]["project_revision"]["passed"],
                            preflight["checks"]["project_revision"],
                        )
            finally:
                api.stop()
                for item in reversed(patches):
                    item.stop()

    def test_frontend_teaches_scope_and_uses_existing_results_page(self) -> None:
        page = (ROOT / "app" / "page.tsx").read_text(encoding="utf-8")
        source = (ROOT / "app" / "features" / "learn" / "Value101NetworkExercise.tsx").read_text(encoding="utf-8")
        for label in (
            "Network constraints & redispatch",
            "Preview matched pair",
            "Create matched Studies",
            "Run copperplate",
            "Run constrained",
            "not DC load flow, AC power flow or N-1 security",
            "Open network results",
        ):
            self.assertIn(label, source)
        self.assertNotIn("transmission expansion module", source.lower())
        self.assertIn('onRunNetworkStudy={(study) => void startRun("two_year", study as Project)}', page)
        self.assertIn("const projectRuns = useMemo(", page)
        self.assertIn("workspace.runs.filter", page)
        self.assertIn("{projectRuns.map((run)", page)
        self.assertIn('canRunMode("two_year")', page)
        self.assertIn("selectRunProject(run.project_id)", page)
        self.assertIn("defaultRunModeForPack(nextPack)", page)
        self.assertIn("selectRunProject(value101Project.id)", page)
        self.assertIn("const effectivePreflightMode =", page)
        self.assertIn("checkPreflight(mode = effectivePreflightMode)", page)

    @staticmethod
    def _request(url: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=15)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())
        with response:
            return response.status, json.loads(response.read())


if __name__ == "__main__":
    unittest.main()
