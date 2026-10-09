from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from gridform_core.catalog import DATASET_SLOTS, MODULE_REGISTRY
from gridform_core.data_bundle import build_data_bundle
from gridform_core.research_suite import (
    ResearchSuiteError,
    build_research_suite,
    install_research_suite,
    validate_research_suite,
)
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS


ROOT = Path(__file__).resolve().parents[1]
BASE_PACK = ROOT / "data-packs" / "value-101-baseline-v1"
NETWORK_PACK = ROOT / "data-packs" / "value-101-network-v1"


def _network_slots() -> list[dict[str, object]]:
    rows = [dict(item) for item in DATASET_SLOTS]
    seen = {str(item["role"]) for item in rows}
    for extension in MODULE_REGISTRY.extension_manifests().values():
        if extension.id != "value-zonal-redispatch-extension":
            continue
        for role in extension.data_roles:
            if role.role not in seen:
                rows.append(role.to_dataset_slot())
                seen.add(role.role)
    return rows


def _templates(base_id: str, network_id: str) -> dict[str, object]:
    modules = {
        "psm": "value-staged-bid-at-cost-psm",
        "storage_cost": "dynamic-annual-storage-cost",
        "investment": "agent-investment",
        "pipeline": "planning-pipeline",
        "vre_cap": "vre-expansion-cap",
        "storage_cap": "value-storage-expansion-policy",
        "transition": "value-annual-state-transition",
    }
    common = {
        "schema_version": "value.project/v1",
        "data_pack_id": base_id,
        "start_year": 2025,
        "end_year": 2034,
        "parameters": {},
        "runtime_options": {"runtime.market_trace_level": "summary"},
        "extension_parameters": {},
    }
    return {
        "schema_version": "value.study-templates/v1",
        "studies": [
            {
                **common,
                "id": "value-uk-copperplate-2025-2034",
                "name": "VALUE-UK copperplate 2025-2034",
                "modules": {**modules, "balancing": "value-copperplate-balancing"},
                "selected_extensions": [],
                "market_configuration": {},
                "maturity_acknowledgements": {},
            },
            {
                **common,
                "id": "value-uk-zonal-2025-2034",
                "name": "VALUE-UK fixed-zonal network 2025-2034",
                "modules": {**modules, "balancing": "value-zonal-redispatch-balancing"},
                "selected_extensions": ["value-zonal-redispatch-extension"],
                "market_configuration": {
                    "network_pack_id": network_id,
                    "zonal_demand_mode": "scenario_scaled_zonal_shares",
                },
                "solver_contract": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
                "maturity_acknowledgements": {
                    "module:value-zonal-redispatch-balancing@2.0.0": "value.experimental-ack/v1",
                    "extension:value-zonal-redispatch-extension@1.0.0": "value.experimental-ack/v1",
                },
            },
        ],
    }


class ResearchSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.base_pack_root = self.root / "base-pack"
        self.network_pack_root = self.root / "network-pack"
        shutil.copytree(BASE_PACK, self.base_pack_root)
        shutil.copytree(NETWORK_PACK, self.network_pack_root)
        (self.base_pack_root / "derivation.json").unlink(missing_ok=True)
        (self.network_pack_root / "derivation.json").unlink(missing_ok=True)
        self.base_bundle = self.root / "base.zip"
        self.network_bundle = self.root / "network.zip"
        build_data_bundle(pack_root=self.base_pack_root, destination=self.base_bundle)
        build_data_bundle(pack_root=self.network_pack_root, destination=self.network_bundle)
        self.templates = self.root / "study-templates.json"
        self.templates.write_text(
            json.dumps(_templates("value-101-baseline-v1", "value-101-network-v1"), indent=2),
            encoding="utf-8",
        )
        self.rights = self.root / "RIGHTS.json"
        self.rights.write_text(
            json.dumps({"schema_version": "value.data-rights/v1", "redistribution": "test"}),
            encoding="utf-8",
        )
        self.attribution = self.root / "ATTRIBUTION.md"
        self.attribution.write_text("# Attribution\n\nSynthetic test fixtures.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _build(self, destination: Path, *, network_bundle: Path | None = None) -> Path:
        build_research_suite(
            base_bundle=self.base_bundle,
            network_bundle=network_bundle or self.network_bundle,
            studies_path=self.templates,
            rights_paths=(self.rights, self.attribution),
            destination=destination,
        )
        return destination

    def _install(self, suite: Path, state: Path) -> dict[str, object]:
        network_root = state / "data-workbench" / "installed-packs"

        def validate_project(project: dict[str, object]) -> dict[str, object]:
            return {"valid": True, "normalised_project": project, "errors": []}

        def revision_manifest(
            project: dict[str, object], base_manifest: dict[str, object]
        ) -> dict[str, object]:
            if "value-zonal-redispatch-extension" not in project.get("selected_extensions", []):
                return dict(base_manifest)
            network_id = str(dict(project["market_configuration"])["network_pack_id"])
            network_manifest = json.loads(
                (network_root / network_id / "manifest.json").read_text(encoding="utf-8")
            )
            merged = dict(base_manifest)
            merged["bindings"] = {
                **dict(base_manifest.get("bindings") or {}),
                **dict(network_manifest.get("bindings") or {}),
            }
            merged["network_overlay"] = {
                "id": network_id,
                "zonal_network_pack": network_manifest.get("zonal_network_pack"),
            }
            return merged

        return install_research_suite(
            suite,
            packs_root=state / "data-packs",
            network_packs_root=network_root,
            projects_root=state / "projects",
            base_dataset_slots=DATASET_SLOTS,
            network_dataset_slots=_network_slots(),
            registry=MODULE_REGISTRY,
            validate_project=validate_project,
            revision_manifest=revision_manifest,
            rights_acknowledged=True,
            minimum_free_space_bytes=0,
        )

    def test_one_suite_installs_two_packs_and_two_unrun_studies_idempotently(self) -> None:
        """Catches a convenience suite merging identities or launching a hidden Run."""

        suite = self._build(self.root / "suite.zip")
        state = self.root / "state"
        first = self._install(suite, state)
        second = self._install(suite, state)

        self.assertEqual(
            first["component_pack_ids"],
            ["value-101-baseline-v1", "value-101-network-v1"],
        )
        self.assertEqual(
            first["study_ids"],
            ["value-uk-copperplate-2025-2034", "value-uk-zonal-2025-2034"],
        )
        self.assertTrue(second["idempotent"])
        self.assertTrue((state / "data-packs" / "value-101-baseline-v1").is_dir())
        self.assertTrue(
            (state / "data-workbench" / "installed-packs" / "value-101-network-v1").is_dir()
        )
        self.assertFalse((state / "runs").exists())

    def test_reinstall_over_an_earlier_version_study_points_to_revision_migration(self) -> None:
        """A suite Study saved before X0 S11 differs only in identity: migrate, do not call it a collision."""

        import hashlib

        from gridform_core import revision_migration
        from gridform_core.project_revision import _canonical_bytes, canonical_project_payload, save_project_revision

        suite = self._build(self.root / "suite.zip")
        state = self.root / "state"
        self._install(suite, state)
        shutil.rmtree(state / "research-suites")
        study_dir = state / "projects" / "value-uk-copperplate-2025-2034"
        manifest = json.loads((state / "data-packs" / "value-101-baseline-v1" / "manifest.json").read_text(encoding="utf-8"))
        project = json.loads((study_dir / "project.json").read_text(encoding="utf-8"))
        for key in ("fingerprint_basis", "revision_reason"):
            project.pop(key)
        legacy = canonical_project_payload(
            project, MODULE_REGISTRY, manifest, include_methodology=False,
            module_version_overrides=revision_migration._baseline_overrides(MODULE_REGISTRY, project["modules"]),
        )
        project["revision_sha256"] = hashlib.sha256(_canonical_bytes(legacy)).hexdigest()
        (study_dir / "project.json").write_text(json.dumps(project), encoding="utf-8")

        with self.assertRaises(ResearchSuiteError) as caught:
            self._install(suite, state)
        self.assertEqual(caught.exception.code, "VALUE_RESEARCH_SUITE_STUDY_MIGRATION_REQUIRED")
        self.assertIn("revision-migration", str(caught.exception))
        classification = caught.exception.revision_migration
        self.assertEqual(classification["classification"], "method_upgrade_required")

        revision_migration.migrate_project_revision(
            study_dir, MODULE_REGISTRY, manifest, confirm_diff_sha256=classification["diff_sha256"],
        )
        shutil.rmtree(state / "research-suites", ignore_errors=True)
        self.assertFalse(self._install(suite, state)["idempotent"])  # the migrated Study is the suite's Study

        shutil.rmtree(state / "research-suites")
        edited = json.loads((study_dir / "project.json").read_text(encoding="utf-8"))
        save_project_revision(study_dir, dict(edited, start_year=2026), MODULE_REGISTRY, manifest,
                              expected_base_revision=edited["revision_sha256"])
        with self.assertRaises(ResearchSuiteError) as caught:
            self._install(suite, state)
        self.assertEqual(caught.exception.code, "VALUE_RESEARCH_SUITE_STUDY_COLLISION")

    def test_suite_rejects_undeclared_executable_content(self) -> None:
        """Catches the data-only trust boundary accepting executable payloads."""

        suite = self._build(self.root / "unsafe.zip")
        with zipfile.ZipFile(suite, "a") as archive:
            archive.writestr("bin/tool.exe", b"not executable, but forbidden")

        with self.assertRaisesRegex(ResearchSuiteError, "undeclared|executable"):
            validate_research_suite(suite)

    def test_network_semantic_failure_rolls_back_new_base_pack_and_studies(self) -> None:
        """Catches half-installed research suites after the second component fails."""

        broken_root = self.root / "broken-network"
        shutil.copytree(self.network_pack_root, broken_root)
        manifest_path = broken_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        first_role = next(iter(manifest["bindings"]))
        manifest["bindings"][first_role]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        broken_bundle = self.root / "broken-network.zip"
        build_data_bundle(pack_root=broken_root, destination=broken_bundle)
        suite = self._build(self.root / "broken-suite.zip", network_bundle=broken_bundle)
        state = self.root / "rollback-state"

        with self.assertRaises(ResearchSuiteError):
            self._install(suite, state)

        self.assertFalse((state / "data-packs" / "value-101-baseline-v1").exists())
        self.assertFalse(
            (state / "data-workbench" / "installed-packs" / "value-101-network-v1").exists()
        )
        self.assertFalse((state / "projects").exists())


if __name__ == "__main__":
    unittest.main()
