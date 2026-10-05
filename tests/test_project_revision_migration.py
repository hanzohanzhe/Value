"""Saved Study revision classification and migration (X0 S11, Q13)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gridform_core import methodology, revision_migration
from gridform_core.methodology import PROFILE_PARAMETER, default_profile_id
from gridform_core.preflight import run_preflight
from gridform_core.project_revision import _canonical_bytes, canonical_project_payload, save_project_revision
from gridform_core.revision_migration import (
    RevisionMigrationError,
    classify_revision_mismatch,
    migrate_project_revision,
)
from gridform_core.v2.module_manifest import workspace_registry

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data-packs" / "value-101-baseline-v1"
NETWORK_PACK_ROOT = ROOT / "data-packs" / "value-101-network-v1"
PSM = "value-bid-at-cost-psm"


class VersionedRegistry:
    """The built-in registry with some module versions moved (a simulated upgrade)."""

    def __init__(self, base, versions):
        self.base, self.versions = base, dict(versions)

    def manifest(self, module_id, expected_slot=None):
        manifest = self.base.manifest(module_id, expected_slot=expected_slot)
        if module_id in self.versions:
            return dataclasses.replace(manifest, version=self.versions[module_id])
        return manifest

    def __getattr__(self, name):
        return getattr(self.base, name)


def _ledger(opt_in: bool):
    return {PSM: {"baseline_version": "5.1.0", "current_version": "5.2.0", "bumps": [{
        "from": "5.1.0", "to": "5.2.0", "package": "P0-4", "correction_ids": ["p04.toy"],
        "reason": "test", "requires_user_opt_in": opt_in,
    }]}}


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.study = Path(self.folder.name) / "projects" / "study"
        self.registry = workspace_registry(Path("missing-modules-directory"))
        self.manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        project["id"] = "study"
        project["parameters"].pop(PROFILE_PARAMETER, None)
        self.saved = save_project_revision(self.study, project, self.registry, self.manifest)

    def project(self):
        return json.loads((self.study / "project.json").read_text(encoding="utf-8"))

    def revisions(self):
        return sorted(path.name for path in (self.study / "revisions").glob("*.json"))

    def classify(self, registry=None, manifest=None, project=None):
        return classify_revision_mismatch(project or self.project(), registry or self.registry, manifest or self.manifest)

    def test_every_saved_revision_records_its_basis_and_reason(self):
        basis = self.saved["fingerprint_basis"]
        self.assertEqual(basis["revision_sha256"], self.saved["revision_sha256"])
        self.assertEqual(hashlib.sha256(_canonical_bytes(basis["payload"])).hexdigest(), self.saved["revision_sha256"])
        self.assertEqual(basis["payload"]["methodology"]["profile_id"], default_profile_id())
        self.assertEqual(self.saved["revision_reason"], "user-save")
        self.assertEqual(self.classify()["classification"], "none")
        with self.assertRaises(ValueError):
            save_project_revision(self.study, self.saved, self.registry, self.manifest, revision_reason="because")

    def test_code_only_module_upgrade_is_appended_automatically(self):
        upgraded = VersionedRegistry(self.registry, {PSM: "5.2.0"})
        with patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=False)):
            result = self.classify(upgraded)
            self.assertEqual(result["classification"], "code_identity_upgrade")
            self.assertEqual(result["error_code"], "GF_PREFLIGHT_REVISION_REIDENTIFY")
            self.assertTrue(result["automatic"])
            self.assertEqual([row["key"] for row in result["differences"]], [f"psm:{PSM}"])
            report = self.preflight(upgraded)
            self.assertTrue(report["checks"]["project_revision"]["passed"])
            self.assertIn("GF_PREFLIGHT_REVISION_REIDENTIFY", {row["code"] for row in report["warnings"]})
            self.assertNotIn("GF_PREFLIGHT_PROJECT_REVISION", {row["code"] for row in report["errors"]})
            before = self.revisions()
            saved, _ = migrate_project_revision(self.study, upgraded, self.manifest)
        self.assertEqual(saved["revision_reason"], "code-identity-upgrade")
        self.assertEqual(saved["parent_revision_sha256"], self.saved["revision_sha256"])
        self.assertIn(f"{saved['revision_sha256']}.json", self.revisions())
        self.assertEqual(len(self.revisions()), len(before) + 1)
        self.assertNotIn(PROFILE_PARAMETER, saved["parameters"])

    def test_opt_in_module_upgrade_needs_the_confirmed_diff(self):
        upgraded = VersionedRegistry(self.registry, {PSM: "5.2.0"})
        with patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=True)):
            result = self.classify(upgraded)
            self.assertEqual(result["classification"], "method_upgrade_required")
            self.assertEqual(result["error_code"], "GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED")
            self.assertIn("p04.toy", result["differences"][0]["effect"])
            report = self.preflight(upgraded)
            self.assertFalse(report["accepted"])
            self.assertIn("GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED", {row["code"] for row in report["errors"]})
            before = (self.study / "project.json").read_bytes()
            for confirmation, code in ((None, "GF_REVISION_MIGRATION_CONFIRMATION_REQUIRED"),
                                       ("0" * 64, "GF_REVISION_MIGRATION_STALE")):
                with self.subTest(confirmation=confirmation), self.assertRaises(RevisionMigrationError) as caught:
                    migrate_project_revision(self.study, upgraded, self.manifest, confirm_diff_sha256=confirmation)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual((self.study / "project.json").read_bytes(), before)
            saved, _ = migrate_project_revision(self.study, upgraded, self.manifest, confirm_diff_sha256=result["diff_sha256"])
            self.assertEqual(saved["revision_reason"], "method-upgrade-confirmed")
            self.assertEqual(saved["parameters"][PROFILE_PARAMETER], default_profile_id())
            self.assertEqual(self.classify(upgraded)["classification"], "none")

    def catalogue_with(self, mutate):
        from tests.test_methodology_profiles import CatalogueCopy

        copy_ = CatalogueCopy()
        self.addCleanup(copy_.close)
        copy_.edit("corrections/x0.json", mutate)
        return copy_.load()

    def under(self, catalogue):
        stack = ExitStack()
        stack.enter_context(patch.object(methodology, "load_catalogue", return_value=catalogue))
        stack.enter_context(patch.object(revision_migration, "load_catalogue", return_value=catalogue))
        return stack

    def test_correction_wording_is_not_a_method_change(self):
        """Description, advisory text and applies_when are presentation, not method identity."""

        identity = methodology.resolve_methodology(None).identity()

        def reword(payload):
            row = payload["corrections"][0]
            row["description"] += " Reworded."
            row["applies_when"] = {"modes_any": ["full"]}
            row["advisory"] = {"severity": "info", "title": "t", "summary": "s", "affected_metrics": []}

        with self.under(self.catalogue_with(reword)):
            self.assertEqual(methodology.resolve_methodology(None).identity(), identity)
            result = self.classify()
        self.assertEqual(result["classification"], "none")

    def test_added_or_redefined_corrections_are_classified_by_their_numeric_effect(self):
        def correction(correction_id, affects):
            return {"id": correction_id, "package": "x0", "findings": [], "track": "universal", "scope": "test",
                    "affects": affects, "applies_when": {}, "advisory": None, "trigger_fixture": None,
                    "introduced_in": "test"}

        def redefine(payload):
            payload["corrections"][0]["affects"] = ["identity", "accounting"]

        cases = (
            ("identity correction added", lambda p: p["corrections"].append(correction("x0.toy-identity", ["identity"])),
             "code_identity_upgrade", ["x0.toy-identity"], []),
            ("numeric correction added", lambda p: p["corrections"].append(correction("x0.toy-numbers", ["trajectory"])),
             "method_upgrade_required", ["x0.toy-numbers"], ["x0.toy-numbers"]),
            ("correction redefined as numeric", redefine,
             "method_upgrade_required", [], ["x0.methodology-identity"]),
        )
        for label, mutate, expected, changed, numeric in cases:
            with self.subTest(label), self.under(self.catalogue_with(mutate)):
                result = self.classify()
                row = next(row for row in result["differences"] if row["key"] == "applied_corrections")
                self.assertEqual(result["classification"], expected)
                self.assertEqual(row["classification"], expected)
                self.assertEqual(row["changed_correction_ids"], changed)
                self.assertEqual(row["numeric_correction_ids"], numeric)

    def test_weather_identity_only_is_an_environment_reidentification(self):
        project = self.project()
        payload = dict(project["fingerprint_basis"]["payload"], dispatch_weather_identity={"adapter_sha256": "a" * 64})
        declared = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
        project["fingerprint_basis"] = dict(project["fingerprint_basis"], payload=payload, revision_sha256=declared)
        project["revision_sha256"] = declared
        result = self.classify(project=project)
        self.assertEqual(result["classification"], "environment_reidentify")
        self.assertTrue(result["automatic"])

    def test_unsaved_content_change_is_refused(self):
        project = self.project()
        project["parameters"]["planning.defer_spread_years"] = 2
        (self.study / "project.json").write_text(json.dumps(project), encoding="utf-8")
        result = self.classify()
        self.assertEqual(result["classification"], "content_changed")
        self.assertEqual(result["error_code"], "GF_PREFLIGHT_PROJECT_REVISION")
        self.assertFalse(result["confirmable"])
        report = self.preflight()
        self.assertIn("GF_PREFLIGHT_PROJECT_REVISION", {row["code"] for row in report["errors"]})
        with self.assertRaises(RevisionMigrationError) as caught:
            migrate_project_revision(self.study, self.registry, self.manifest, confirm_diff_sha256=result["diff_sha256"])
        self.assertEqual(caught.exception.code, "GF_PREFLIGHT_PROJECT_REVISION")

    def test_data_pack_content_change_needs_confirmation(self):
        changed = dict(self.manifest, updated_at="2099-01-01T00:00:00Z")
        result = self.classify(manifest=changed)
        self.assertEqual(result["classification"], "data_changed")
        self.assertEqual(result["error_code"], "GF_PREFLIGHT_DATA_CHANGED")
        self.assertTrue(result["confirmable"])

    def test_pre_profile_study_is_reconstructed_and_first_methodology_needs_confirmation(self):
        project = self.project()
        for key in ("fingerprint_basis", "revision_reason"):
            project.pop(key)
        legacy = canonical_project_payload(
            project, self.registry, self.manifest,
            module_version_overrides=revision_migration._baseline_overrides(self.registry, project["modules"]),
            include_methodology=False,
        )
        project["revision_sha256"] = hashlib.sha256(_canonical_bytes(legacy)).hexdigest()
        (self.study / "project.json").write_text(json.dumps(project), encoding="utf-8")
        result = self.classify()
        self.assertEqual(result["basis_source"], "reconstructed_35aadb3")
        self.assertEqual(result["classification"], "method_upgrade_required")
        self.assertEqual(result["differences"][-1]["dimension"], "methodology")
        self.assertIsNone(result["differences"][-1]["old"])
        saved, _ = migrate_project_revision(self.study, self.registry, self.manifest, confirm_diff_sha256=result["diff_sha256"])
        self.assertEqual(saved["parameters"][PROFILE_PARAMETER], default_profile_id())
        self.assertIn(f"{saved['revision_sha256']}.json", self.revisions())

    def test_unreconstructable_revision_is_unverifiable(self):
        project = self.project()
        project.pop("fingerprint_basis")
        project["revision_sha256"] = "0" * 64
        result = self.classify(project=project)
        self.assertEqual(result["classification"], "unverifiable")
        self.assertEqual(result["error_code"], "GF_PREFLIGHT_PROJECT_REVISION")
        self.assertTrue(result["confirmable"])
        # The confirmation dialog has the Study's current content to review.
        keys = {row["key"] for row in result["differences"]}
        self.assertTrue({"fingerprint_basis", "start_year", "end_year", "scientific_parameters",
                         "modules", "data_pack", "methodology"} <= keys, keys)
        start = next(row for row in result["differences"] if row["key"] == "start_year")
        self.assertEqual(start["new"], project["start_year"])

    def test_pre_profile_extension_study_is_reconstructed_from_its_stored_graph(self):
        """A 35aadb3-era Study with extensions hashed module source sha256s that any code change moves."""

        manifest = json.loads((NETWORK_PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "C8.json").read_text(encoding="utf-8"))
        self.assertIn("value-zonal-redispatch-extension", project["selected_extensions"])
        overrides = revision_migration._baseline_overrides(self.registry, project["modules"])
        legacy = canonical_project_payload(project, self.registry, manifest,
                                           module_version_overrides=overrides, include_methodology=False)
        graph = json.loads(json.dumps(legacy["module_resolution_graph"]))
        graph["modules"]["psm"]["source_sha256"] = "e" * 64  # the 35aadb3 source of the PSM entry point
        graph["graph_sha256"] = "f" * 64
        legacy["module_resolution_graph"] = graph
        project["module_resolution_graph"] = graph  # what project.json stored with the revision
        project["revision_sha256"] = hashlib.sha256(_canonical_bytes(legacy)).hexdigest()
        result = classify_revision_mismatch(project, self.registry, manifest)
        self.assertNotEqual(result["basis_source"], "none")
        self.assertEqual(result["basis_source"], "reconstructed_35aadb3_stored_graph")
        self.assertEqual(result["classification"], "method_upgrade_required")
        rows = {row["key"]: row for row in result["differences"]}
        self.assertEqual(rows["module_resolution_graph"]["classification"], "code_identity_upgrade")
        self.assertEqual(rows["profile_id"]["dimension"], "methodology")
        self.assertIsNone(rows["profile_id"]["old"])
        self.assertNotIn("unverifiable", {row["classification"] for row in result["differences"]})

    def zonal_study_with_superseded_contract(self):
        """A saved zonal Study whose revision (and basis) carry the superseded v2 solver contract."""

        manifest = json.loads((NETWORK_PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "C8.json").read_text(encoding="utf-8"))
        project["id"] = "zonal"
        folder = Path(self.folder.name) / "projects" / "zonal"
        saved = save_project_revision(folder, project, self.registry, manifest)
        old = "value.zonal-lexicographic-gbp1/v2"
        payload = json.loads(json.dumps(saved["fingerprint_basis"]["payload"]))
        payload["solver_contract"]["contract_version"] = old
        declared = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
        saved["solver_contract"]["contract_version"] = old
        saved["fingerprint_basis"] = dict(saved["fingerprint_basis"], payload=payload, revision_sha256=declared)
        saved["revision_sha256"] = declared
        (folder / "project.json").write_text(json.dumps(saved), encoding="utf-8")
        return folder, saved, manifest

    def test_superseded_solver_contract_requires_an_explicit_upgrade(self):
        from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS

        folder, project, manifest = self.zonal_study_with_superseded_contract()
        result = classify_revision_mismatch(project, self.registry, manifest)
        self.assertEqual(result["basis_source"], "recorded")
        self.assertEqual(result["classification"], "method_upgrade_required")
        self.assertEqual(result["error_code"], "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED")
        self.assertEqual([row["dimension"] for row in result["differences"]], ["solver_contract"])
        candidate = revision_migration.migration_candidate(project, self.registry)
        self.assertEqual(candidate["solver_contract"], DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        saved, _ = migrate_project_revision(folder, self.registry, manifest, confirm_diff_sha256=result["diff_sha256"])
        self.assertEqual(saved["solver_contract"], DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        self.assertEqual(classify_revision_mismatch(saved, self.registry, manifest)["classification"], "none")

    def test_superseded_solver_contract_does_not_hide_an_unsaved_content_edit(self):
        folder, project, manifest = self.zonal_study_with_superseded_contract()
        project["start_year"] = 2030  # edited on disk, never saved
        (folder / "project.json").write_text(json.dumps(project), encoding="utf-8")
        result = classify_revision_mismatch(project, self.registry, manifest)
        self.assertEqual(result["classification"], "content_changed")
        self.assertFalse(result["confirmable"])
        keys = {row["key"] for row in result["differences"]}
        self.assertTrue({"start_year", "contract_version"} <= keys, keys)
        before = (folder / "project.json").read_bytes()
        with self.assertRaises(RevisionMigrationError) as caught:
            migrate_project_revision(folder, self.registry, manifest, confirm_diff_sha256=result["diff_sha256"])
        self.assertEqual(caught.exception.code, "GF_PREFLIGHT_PROJECT_REVISION")
        self.assertEqual((folder / "project.json").read_bytes(), before)

    def test_missing_version_ledger_is_reported_not_silently_assumed(self):
        upgraded = VersionedRegistry(self.registry, {PSM: "5.2.0"})
        with patch.object(revision_migration, "_ledger", return_value=None):
            result = self.classify(upgraded)
            self.assertEqual(result["ledger_status"], "unavailable")
            self.assertEqual(result["classification"], "method_upgrade_required")
            self.assertIn("ledger_unavailable", result["differences"][0]["effect"])
            project = self.project()
            project.pop("fingerprint_basis")
            project["revision_sha256"] = "1" * 64
            unverifiable = self.classify(project=project)
            self.assertEqual(unverifiable["classification"], "unverifiable")
            self.assertIn("VERSION_LEDGER is unavailable", unverifiable["differences"][0]["effect"])
        self.assertEqual(self.classify()["ledger_status"], "available")

    def test_cli_preflight_accepts_a_code_only_change(self):
        """The CLI (application.main) runs the same preflight; a code-only change only warns."""

        upgraded = VersionedRegistry(self.registry, {PSM: "5.2.0"})
        with patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=False)):
            report = self.preflight(upgraded)
        self.assertNotIn("GF_PREFLIGHT_PROJECT_REVISION", {row["code"] for row in report["errors"]})
        classification = report["checks"]["project_revision"]["classification"]
        self.assertEqual(classification["classification"], "code_identity_upgrade")

    def preflight(self, registry=None):
        with tempfile.TemporaryDirectory() as folder, patch(
            "gridform_core.preflight.shutil.disk_usage",
            return_value=SimpleNamespace(total=4 * 1024**4, used=1024**4, free=3 * 1024**4),
        ):
            return run_preflight(
                self.project(), mode="smoke", pack_root=PACK_ROOT, pack_manifest=self.manifest,
                dataset_slots=[], registry=registry or self.registry, output_root=Path(folder),
            )


class MigrationApiTests(unittest.TestCase):
    """GET classifies without writing; POST migrates; a run start refuses an unconfirmed method change."""

    def test_http_migration_flow(self):
        from tests.local_api_harness import start_local_api

        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            pack = home / "data-packs" / "value-101-baseline-v1"
            shutil.copytree(PACK_ROOT, pack)
            registry = workspace_registry(Path("missing-modules-directory"))
            manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
            project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
            project["id"] = "legacy"
            project["parameters"].pop(PROFILE_PARAMETER, None)
            legacy = canonical_project_payload(
                project, registry, manifest,
                module_version_overrides=revision_migration._baseline_overrides(registry, project["modules"]),
                include_methodology=False,
            )
            project["revision_sha256"] = hashlib.sha256(_canonical_bytes(legacy)).hexdigest()
            study = home / "projects" / "legacy"
            study.mkdir(parents=True)
            (study / "project.json").write_text(json.dumps(project), encoding="utf-8")
            before = (study / "project.json").read_bytes()

            def call(method, path, body=None):
                request = urllib.request.Request(
                    origin + path, method=method,
                    data=None if body is None else json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(request, timeout=30) as response:
                        return response.status, json.loads(response.read())
                except urllib.error.HTTPError as error:
                    return error.code, json.loads(error.read())

            with start_local_api(data_home=home) as (_httpd, origin, _token):
                status, payload = call("GET", "/api/projects/legacy/revision-migration")
                self.assertEqual(status, 200)
                classification = payload["revision_migration"]
                self.assertEqual(classification["classification"], "method_upgrade_required")
                self.assertEqual((study / "project.json").read_bytes(), before)
                status, payload = call("POST", "/api/projects/legacy/runs", {"mode": "smoke"})
                self.assertEqual(status, 409, payload)
                self.assertEqual(payload["error_code"], "GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED")
                self.assertFalse((home / "runs").exists() and any((home / "runs").iterdir()))
                status, payload = call("POST", "/api/projects/legacy/revision-migration", {})
                self.assertEqual((status, payload["error_code"]), (409, "GF_REVISION_MIGRATION_CONFIRMATION_REQUIRED"))
                status, payload = call("POST", "/api/projects/legacy/revision-migration",
                                       {"diff_sha256": classification["diff_sha256"]})
                self.assertEqual(status, 200)
                self.assertEqual(payload["project"]["revision_reason"], "method-upgrade-confirmed")
                status, payload = call("GET", "/api/projects/legacy/revision-migration")
                self.assertEqual(payload["revision_migration"]["classification"], "none")


if __name__ == "__main__":
    unittest.main()
