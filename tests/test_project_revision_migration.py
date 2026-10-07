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


def _shipped_and_upgraded() -> tuple[str, str]:
    from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM

    major, minor, _patch = (int(part) for part in SchemeCNativePSM.version.split("."))
    return SchemeCNativePSM.version, f"{major}.{minor + 1}.0"


# A hypothetical upgrade one minor version beyond the shipped PSM, derived from
# the shipped version (which the P0 packages bump).
SHIPPED, UPGRADED = _shipped_and_upgraded()


def _ledger(opt_in: bool):
    return {PSM: {"baseline_version": SHIPPED, "current_version": UPGRADED, "bumps": [{
        "from": SHIPPED, "to": UPGRADED, "package": "P0-x", "correction_ids": ["p0x.toy"],
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
        upgraded = VersionedRegistry(self.registry, {PSM: UPGRADED})
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
        upgraded = VersionedRegistry(self.registry, {PSM: UPGRADED})
        with patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=True)):
            result = self.classify(upgraded)
            self.assertEqual(result["classification"], "method_upgrade_required")
            self.assertEqual(result["error_code"], "GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED")
            self.assertIn("p0x.toy", result["differences"][0]["effect"])
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
        """A 35aadb3-era Study with extensions hashed module source sha256s that any code change moves.

        It also hashed the v3 zonal solver contract of its time, which the
        installed code refuses to canonicalise since P0-8 (v4): the basis is
        still rebuilt, and the contract upgrade is its own row.
        """

        from gridform_core.zonal_solver_contract import SOLVER_CONTRACT_VERSION, V3_SOLVER_CONTRACT_VERSION

        manifest = json.loads((NETWORK_PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "C8.json").read_text(encoding="utf-8"))
        self.assertIn("value-zonal-redispatch-extension", project["selected_extensions"])
        self.assertEqual(project["solver_contract"]["contract_version"], V3_SOLVER_CONTRACT_VERSION)
        overrides = revision_migration._baseline_overrides(self.registry, project["modules"])
        legacy = canonical_project_payload(project, self.registry, manifest,
                                           module_version_overrides=overrides, include_methodology=False,
                                           recorded_solver_contract=True)
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
        self.assertEqual(rows["contract_version"]["dimension"], "solver_contract")
        self.assertEqual((rows["contract_version"]["old"], rows["contract_version"]["new"]),
                         (V3_SOLVER_CONTRACT_VERSION, SOLVER_CONTRACT_VERSION))
        self.assertEqual(rows["contract_version"]["classification"], "method_upgrade_required")
        self.assertNotIn("unverifiable", {row["classification"] for row in result["differences"]})

    def zonal_study_with_superseded_contract(self):
        """A saved zonal Study whose revision (and basis) carry the superseded v3 solver contract.

        The installed code only saves the current (v4) contract, so the Study
        is saved with it and its record is then rewritten to the v3 identity
        it would carry from before P0-8.
        """

        from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS, V3_SOLVER_CONTRACT_VERSION

        manifest = json.loads((NETWORK_PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "C8.json").read_text(encoding="utf-8"))
        project["id"] = "zonal"
        project["solver_contract"] = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
        folder = Path(self.folder.name) / "projects" / "zonal"
        saved = save_project_revision(folder, project, self.registry, manifest)
        old = V3_SOLVER_CONTRACT_VERSION
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
        upgraded = VersionedRegistry(self.registry, {PSM: UPGRADED})
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

        upgraded = VersionedRegistry(self.registry, {PSM: UPGRADED})
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


# project.json files written by save_project_revision of the 35aadb3 code
# (git archive 35aadb3, tests/golden/projects/<case>.json, the registry of
# workspace_registry(Path("missing-modules-directory")) and the case's pack
# manifest), frozen byte for byte.  The revision sha256 are the 35aadb3 values,
# confirmed independently by the X0 S8-S11 review; they are not produced by
# this branch's code, so a change that breaks the reconstruction of real
# pre-S11 Studies fails here.
STUDIES_35AADB3 = ROOT / "tests" / "fixtures" / "studies-35aadb3"
REVISIONS_35AADB3 = {
    "D1": ("value-101-baseline-v1", "8a45ed0fe336b53db5b285b5996dbb5e1ab61e5cd0dc9a98654ca0d327b84c95"),
    "C1": ("value-101-baseline-v1", "32e3551c1767020493e60ff8668508cb4b1afc3a6ac38417842b62769dbb9cd9"),
    "C7": ("value-101-network-v1", "2ec91a476a5fa236177c7246b1b8714a1cd0a3f0d61117fc3c92765d976e6724"),
}


class Studies35aadb3Tests(unittest.TestCase):
    """Real 35aadb3-saved Studies are reconstructed, never unverifiable (S11 against an external oracle)."""

    def test_35aadb3_studies_are_reconstructed_with_only_the_first_methodology_write(self):
        registry = workspace_registry(Path("missing-modules-directory"))
        for case, (pack_id, revision) in REVISIONS_35AADB3.items():
            with self.subTest(case):
                project = json.loads((STUDIES_35AADB3 / f"{case}.project.json").read_text(encoding="utf-8"))
                self.assertEqual(project["revision_sha256"], revision)
                self.assertNotIn("fingerprint_basis", project)
                manifest = json.loads((ROOT / "data-packs" / pack_id / "manifest.json").read_text(encoding="utf-8"))
                result = classify_revision_mismatch(project, registry, manifest)
                # Assert the reconstruction, not the exact classification: a later
                # data-pack or opt-in module change may add rows (data_changed,
                # method_upgrade_required) without making the Study unverifiable.
                self.assertNotEqual(result["basis_source"], "none", result)
                self.assertTrue(str(result["basis_source"]).startswith("reconstructed_35aadb3"), result["basis_source"])
                self.assertNotIn(result["classification"], {"unverifiable", "content_changed", "none"})
                self.assertNotIn("unverifiable", {row.get("classification") for row in result["differences"]})
                first_write = [row for row in result["differences"] if row.get("dimension") == "methodology"]
                self.assertTrue(first_write, result["differences"])
                self.assertTrue(all(row["old"] is None for row in first_write), first_write)
                self.assertTrue(result["confirmable"])

    def test_confirmed_migration_of_a_35aadb3_study_settles_it(self):
        registry = workspace_registry(Path("missing-modules-directory"))
        manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            study = Path(folder) / "projects" / "golden-study"
            study.mkdir(parents=True)
            shutil.copyfile(STUDIES_35AADB3 / "D1.project.json", study / "project.json")
            project = json.loads((study / "project.json").read_text(encoding="utf-8"))
            result = classify_revision_mismatch(project, registry, manifest)
            saved, _ = migrate_project_revision(study, registry, manifest, confirm_diff_sha256=result["diff_sha256"])
            self.assertEqual(saved["parent_revision_sha256"], REVISIONS_35AADB3["D1"][1])
            self.assertEqual(classify_revision_mismatch(saved, registry, manifest)["classification"], "none")


class ProfileChoiceTests(unittest.TestCase):
    """A pre-profile Study chooses the methodology it is migrated to (review of X0 S11)."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.registry = workspace_registry(Path("missing-modules-directory"))
        self.manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))

    def study(self, case):
        study = Path(self.folder.name) / "projects" / case
        study.mkdir(parents=True)
        shutil.copyfile(STUDIES_35AADB3 / f"{case}.project.json", study / "project.json")
        return study, json.loads((study / "project.json").read_text(encoding="utf-8"))

    def test_doctoral_preset_study_is_offered_the_frozen_profile(self):
        study, project = self.study("D1")
        result = classify_revision_mismatch(project, self.registry, self.manifest)
        choices = {row["profile_id"]: row for row in result["profile_choices"]}
        self.assertEqual(set(choices), set(methodology.profile_ids()))
        doctoral = choices[methodology.REFERENCE_PROFILE_ID]
        self.assertTrue(doctoral["supported"])
        self.assertTrue(doctoral["matches_reference_preset"])
        self.assertTrue(choices[default_profile_id()]["default"])
        self.assertFalse(choices[default_profile_id()]["matches_reference_preset"])
        first_write = next(row for row in result["differences"] if row["dimension"] == "methodology")
        self.assertEqual(first_write["hint"], "matches_reference_preset")
        self.assertEqual(first_write["matches_reference_preset"], [methodology.REFERENCE_PROFILE_ID])
        self.assertEqual(first_write["new"], default_profile_id())
        chosen = classify_revision_mismatch(project, self.registry, self.manifest,
                                            profile_id=methodology.REFERENCE_PROFILE_ID)
        self.assertEqual(chosen["selected_profile_id"], methodology.REFERENCE_PROFILE_ID)
        self.assertNotEqual(chosen["diff_sha256"], result["diff_sha256"])
        with self.assertRaises(RevisionMigrationError) as caught:
            migrate_project_revision(study, self.registry, self.manifest, confirm_diff_sha256=result["diff_sha256"],
                                     profile_id=methodology.REFERENCE_PROFILE_ID)
        self.assertEqual(caught.exception.code, "GF_REVISION_MIGRATION_STALE")
        saved, _ = migrate_project_revision(study, self.registry, self.manifest, confirm_diff_sha256=chosen["diff_sha256"],
                                            profile_id=methodology.REFERENCE_PROFILE_ID)
        self.assertEqual(saved["parameters"][PROFILE_PARAMETER], methodology.REFERENCE_PROFILE_ID)
        self.assertEqual(classify_revision_mismatch(saved, self.registry, self.manifest)["classification"], "none")
        with self.assertRaises(RevisionMigrationError) as caught:
            classify_revision_mismatch(saved, self.registry, self.manifest, profile_id=default_profile_id())
        self.assertEqual(caught.exception.code, "GF_REVISION_MIGRATION_PROFILE_NOT_APPLICABLE")

    def test_a_pin_by_the_manifest_file_sha_alone_is_honoured_by_the_profile_choice(self):
        """Review round 5 (minor): the profile choice uses the same whitelist input as preflight and the worker."""

        from tests.test_pack_source_identity import VALUE_101_FILE_SHA, value_101_pinned_by

        study, project = self.study("D1")
        packs = [methodology.pack_entry(PACK_ROOT)]
        with value_101_pinned_by([VALUE_101_FILE_SHA]):
            self.assertEqual(methodology.combination_violations(methodology.REFERENCE_PROFILE_ID, data_packs=packs), [])
            # Without the file bytes only the canonical sha is known (the fallback the callers no longer use).
            fallback = classify_revision_mismatch(project, self.registry, self.manifest)
            row = next(row for row in fallback["profile_choices"] if row["profile_id"] == methodology.REFERENCE_PROFILE_ID)
            self.assertEqual((row["supported"], row["unsupported_reasons"]), (False, ["data_pack"]))
            result = classify_revision_mismatch(project, self.registry, self.manifest, whitelist_packs=packs)
            row = next(row for row in result["profile_choices"] if row["profile_id"] == methodology.REFERENCE_PROFILE_ID)
            self.assertEqual((row["supported"], row["matches_reference_preset"]), (True, True))
            chosen = classify_revision_mismatch(project, self.registry, self.manifest, whitelist_packs=packs,
                                                profile_id=methodology.REFERENCE_PROFILE_ID)
            saved, _ = migrate_project_revision(study, self.registry, self.manifest, whitelist_packs=packs,
                                                confirm_diff_sha256=chosen["diff_sha256"],
                                                profile_id=methodology.REFERENCE_PROFILE_ID)
        self.assertEqual(saved["parameters"][PROFILE_PARAMETER], methodology.REFERENCE_PROFILE_ID)

    def test_default_confirmation_still_writes_the_default_profile(self):
        study, project = self.study("D1")
        result = classify_revision_mismatch(project, self.registry, self.manifest)
        saved, _ = migrate_project_revision(study, self.registry, self.manifest, confirm_diff_sha256=result["diff_sha256"])
        self.assertEqual(saved["parameters"][PROFILE_PARAMETER], default_profile_id())

    def test_unsupported_or_unknown_choice_is_refused(self):
        _, project = self.study("C1")
        result = classify_revision_mismatch(project, self.registry, self.manifest)
        doctoral = next(row for row in result["profile_choices"] if row["profile_id"] == methodology.REFERENCE_PROFILE_ID)
        if doctoral["supported"]:
            self.skipTest("C1 is admissible under the frozen profile")
        self.assertFalse(doctoral["matches_reference_preset"])
        self.assertNotIn("hint", next(row for row in result["differences"] if row["dimension"] == "methodology"))
        for profile_id, code in ((methodology.REFERENCE_PROFILE_ID, "VALUE_PROFILE_COMBINATION_UNSUPPORTED"),
                                 ("no-such-profile", "VALUE_PROFILE_UNKNOWN")):
            with self.subTest(profile_id), self.assertRaises(RevisionMigrationError) as caught:
                classify_revision_mismatch(project, self.registry, self.manifest, profile_id=profile_id)
            self.assertEqual(caught.exception.code, code)

    def test_unverifiable_pre_profile_study_can_choose_too(self):
        _, project = self.study("D1")
        project["revision_sha256"] = "0" * 64
        result = classify_revision_mismatch(project, self.registry, self.manifest,
                                            profile_id=methodology.REFERENCE_PROFILE_ID)
        self.assertEqual(result["classification"], "unverifiable")
        row = next(row for row in result["differences"] if row["key"] == "methodology")
        self.assertEqual(row["new"]["profile_id"], methodology.REFERENCE_PROFILE_ID)


class MigrationApiTests(unittest.TestCase):
    """GET classifies without writing; POST migrates; a run start refuses an unconfirmed method change."""

    def test_http_migration_flow(self):
        from tests.local_api_harness import start_local_api

        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            pack = home / "data-packs" / "value-101-baseline-v1"
            shutil.copytree(PACK_ROOT, pack)
            # The Study as 35aadb3 saved it (not rebuilt with this branch's code).
            study = home / "projects" / "golden-study"
            study.mkdir(parents=True)
            shutil.copyfile(STUDIES_35AADB3 / "D1.project.json", study / "project.json")
            before = (study / "project.json").read_bytes()
            route = "/api/projects/golden-study/"

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
                status, payload = call("GET", route + "revision-migration")
                self.assertEqual(status, 200)
                classification = payload["revision_migration"]
                self.assertEqual(classification["classification"], "method_upgrade_required")
                self.assertEqual(classification["selected_profile_id"], default_profile_id())
                self.assertEqual((study / "project.json").read_bytes(), before)
                status, payload = call("GET", route + f"revision-migration?profile_id={methodology.REFERENCE_PROFILE_ID}")
                self.assertEqual(status, 200)
                doctoral = payload["revision_migration"]
                self.assertEqual(doctoral["selected_profile_id"], methodology.REFERENCE_PROFILE_ID)
                self.assertNotEqual(doctoral["diff_sha256"], classification["diff_sha256"])
                status, payload = call("GET", route + "revision-migration?profile_id=no-such-profile")
                self.assertEqual((status, payload["error_code"]), (409, "VALUE_PROFILE_UNKNOWN"))
                self.assertEqual((study / "project.json").read_bytes(), before)
                status, payload = call("POST", route + "runs", {"mode": "smoke"})
                self.assertEqual(status, 409, payload)
                self.assertEqual(payload["error_code"], "GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED")
                self.assertFalse((home / "runs").exists() and any((home / "runs").iterdir()))
                status, payload = call("POST", route + "revision-migration", {})
                self.assertEqual((status, payload["error_code"]), (409, "GF_REVISION_MIGRATION_CONFIRMATION_REQUIRED"))
                # The default-profile confirmation does not confirm the doctoral choice.
                status, payload = call("POST", route + "revision-migration",
                                       {"diff_sha256": classification["diff_sha256"],
                                        "profile_id": methodology.REFERENCE_PROFILE_ID})
                self.assertEqual((status, payload["error_code"]), (409, "GF_REVISION_MIGRATION_STALE"))
                self.assertEqual((study / "project.json").read_bytes(), before)
                status, payload = call("POST", route + "revision-migration",
                                       {"diff_sha256": doctoral["diff_sha256"],
                                        "profile_id": methodology.REFERENCE_PROFILE_ID})
                self.assertEqual(status, 200)
                self.assertEqual(payload["project"]["revision_reason"], "method-upgrade-confirmed")
                self.assertEqual(payload["project"]["parameters"][PROFILE_PARAMETER], methodology.REFERENCE_PROFILE_ID)
                status, payload = call("GET", route + "revision-migration")
                self.assertEqual(payload["revision_migration"]["classification"], "none")
                status, payload = call("POST", route + "revision-migration",
                                       {"profile_id": methodology.REFERENCE_PROFILE_ID})
                self.assertEqual((status, payload["error_code"]), (409, "GF_REVISION_MIGRATION_PROFILE_NOT_APPLICABLE"))

    def test_a_file_sha_pin_is_honoured_by_the_migration_api(self):
        """Review round 5 (minor): GET and POST revision-migration pass the pack file bytes to the whitelist."""

        from tests.local_api_harness import start_local_api
        from tests.test_pack_source_identity import VALUE_101_FILE_SHA, value_101_pinned_by

        with tempfile.TemporaryDirectory() as folder, value_101_pinned_by([VALUE_101_FILE_SHA]):
            home = Path(folder)
            shutil.copytree(PACK_ROOT, home / "data-packs" / "value-101-baseline-v1")
            study = home / "projects" / "golden-study"
            study.mkdir(parents=True)
            shutil.copyfile(STUDIES_35AADB3 / "D1.project.json", study / "project.json")
            route = "/api/projects/golden-study/revision-migration"

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
                status, payload = call("GET", route + f"?profile_id={methodology.REFERENCE_PROFILE_ID}")
                self.assertEqual(status, 200, payload)
                doctoral = payload["revision_migration"]
                row = next(row for row in doctoral["profile_choices"]
                           if row["profile_id"] == methodology.REFERENCE_PROFILE_ID)
                self.assertTrue(row["supported"], row)
                status, payload = call("POST", route, {"diff_sha256": doctoral["diff_sha256"],
                                                       "profile_id": methodology.REFERENCE_PROFILE_ID})
                self.assertEqual(status, 200, payload)
                self.assertEqual(payload["project"]["parameters"][PROFILE_PARAMETER], methodology.REFERENCE_PROFILE_ID)

    def test_run_start_appends_a_code_only_revision_and_is_accepted(self):
        """POST /runs on a Study whose module moved by a code-only bump: revision appended, run admitted."""

        from backend import server
        from tests.local_api_harness import start_local_api

        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            shutil.copytree(PACK_ROOT, home / "data-packs" / "value-101-baseline-v1")
            registry = workspace_registry(Path("missing-modules-directory"))
            manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
            project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
            project["id"] = "coded"
            project["parameters"].pop(PROFILE_PARAMETER, None)
            study = home / "projects" / "coded"
            saved = save_project_revision(study, project, registry, manifest)
            upgraded = VersionedRegistry(server.MODULE_REGISTRY, {PSM: UPGRADED})
            spawned, preflighted = [], []
            # The classification and migration are real; the collaborators after
            # admission (preflight, source archive, input snapshot, worker) are stubbed.
            stubs = ExitStack()
            for name, value in {
                "run_preflight": lambda project, **k: preflighted.append(project) or {
                    "accepted": True, "estimates": {"disk_bytes": 100}, "warnings": []},
                "current_execution": lambda **k: {"identity_sha256": "e" * 64},
                "bind_run_execution": lambda project, run_dir, record: project,
                "create_run_input_snapshot": lambda **k: {"snapshot_id": "s", "input_tree_sha256": "t"},
            }.items():
                stubs.enter_context(patch.object(server, name, value))
            with start_local_api(data_home=home) as (_httpd, origin, _token), stubs, \
                    patch.object(server, "MODULE_REGISTRY", upgraded), \
                    patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=False)), \
                    patch.object(server.RunSupervisor, "spawn_worker",
                                 side_effect=lambda **kwargs: spawned.append(kwargs)):
                request = urllib.request.Request(
                    origin + "/api/projects/coded/runs", method="POST",
                    data=json.dumps({"mode": "smoke"}).encode("utf-8"), headers={"Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(request, timeout=120) as response:
                        status, payload = response.status, json.loads(response.read())
                except urllib.error.HTTPError as error:
                    status, payload = error.code, json.loads(error.read())
                # A24-5: the worker is spawned by the background preparation.
                self.assertTrue(server.wait_for_run_preparation(timeout=120))
            self.assertIn(status, {200, 201, 202}, payload)
            self.assertEqual(len(spawned), 1)
            current = json.loads((study / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(preflighted[0]["revision_sha256"], current["revision_sha256"])
            self.assertEqual(current["revision_reason"], "code-identity-upgrade")
            self.assertEqual(current["parent_revision_sha256"], saved["revision_sha256"])
            reasons = {
                json.loads(path.read_text(encoding="utf-8")).get("revision_reason")
                for path in (study / "revisions").glob("*.json")
            }
            self.assertEqual(reasons, {"user-save", "code-identity-upgrade"})
            self.assertTrue((study / "revisions" / f"{current['revision_sha256']}.json").is_file())


if __name__ == "__main__":
    unittest.main()
