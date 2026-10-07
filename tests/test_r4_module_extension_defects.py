"""R4-4 (DECISIONS A27): edit-module and add-feature defects of the final four-role report.

Each class names the defect ids it covers (M-* edit a module, F-* add a feature).
"""

from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gridform_core import revision_migration
from gridform_core.methodology import PROFILE_PARAMETER
from gridform_core.preflight import run_preflight
from gridform_core.project_revision import save_project_revision
from gridform_core.v2.module_manifest import workspace_registry

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data-packs" / "value-101-baseline-v1"
PSM = "value-bid-at-cost-psm"
PINNED_DISK = SimpleNamespace(total=4 * 1024**4, used=1024**4, free=3 * 1024**4)


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


def _versions() -> tuple[str, str]:
    from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM

    major, minor, _patch = (int(part) for part in SchemeCNativePSM.version.split("."))
    return SchemeCNativePSM.version, f"{major}.{minor + 1}.0"


SHIPPED, UPGRADED = _versions()


def _ledger(opt_in: bool) -> dict:
    return {PSM: {"baseline_version": SHIPPED, "current_version": UPGRADED, "bumps": [{
        "from": SHIPPED, "to": UPGRADED, "package": "P0-x", "correction_ids": ["p06.storage-net-per-period"],
        "reason": "test", "requires_user_opt_in": opt_in,
    }]}}


class SavedStudyCase(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.study = Path(self.folder.name) / "projects" / "study"
        self.registry = workspace_registry(Path("missing-modules-directory"))
        self.manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        project["id"] = "study"
        self.saved = save_project_revision(self.study, project, self.registry, self.manifest)

    def project(self) -> dict:
        return json.loads((self.study / "project.json").read_text(encoding="utf-8"))

    def preflight(self, registry=None, project=None) -> dict:
        with tempfile.TemporaryDirectory() as folder, patch(
            "gridform_core.preflight.shutil.disk_usage", return_value=PINNED_DISK,
        ):
            return run_preflight(
                project or self.project(), mode="smoke", pack_root=PACK_ROOT, pack_manifest=self.manifest,
                dataset_slots=[], registry=registry or self.registry, output_root=Path(folder),
            )


class PreflightIdentityTests(SavedStudyCase):
    """M-中2 / F-中1: a code-only re-identification still yields a readiness report."""

    def test_report_names_the_saved_revision_it_evaluated(self) -> None:
        upgraded = VersionedRegistry(self.registry, {PSM: UPGRADED})
        with patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=False)):
            report = self.preflight(upgraded)
        check = report["checks"]["project_revision"]
        self.assertTrue(check["classification"]["automatic"])
        self.assertNotEqual(check["calculated_sha256"], self.saved["revision_sha256"])
        # The report is evidence for the saved revision the UI holds ...
        self.assertEqual(report["project_revision_sha256"], self.saved["revision_sha256"])
        # ... and still says which hash the run will append.
        self.assertEqual(report["calculated_project_revision_sha256"], check["calculated_sha256"])
        self.assertIn("GF_PREFLIGHT_REVISION_REIDENTIFY", {row["code"] for row in report["warnings"]})

    def test_unchanged_and_unsaved_reports_keep_their_identity(self) -> None:
        report = self.preflight()
        self.assertEqual(report["project_revision_sha256"], self.saved["revision_sha256"])
        self.assertEqual(report["calculated_project_revision_sha256"], self.saved["revision_sha256"])
        unsaved = {key: value for key, value in self.project().items() if key != "revision_sha256"}
        report = self.preflight(project=unsaved)
        self.assertEqual(report["project_revision_sha256"], report["calculated_project_revision_sha256"])
        self.assertTrue(report["project_revision_sha256"])


def _graph(module_sha: str, hook_sha: str) -> dict:
    return {
        "schema_version": "value.module-resolution/v1", "graph_sha256": module_sha[:8] + hook_sha[:8],
        "modules": {
            "psm": {"module_id": PSM, "source_sha256": "a" * 64, "distribution": "workspace-source"},
            "storage_cost": {"module_id": "hx-flat", "source_sha256": module_sha, "distribution": "installed-source"},
        },
        "extension_graph": {"extensions": [{"id": "obs", "version": "0.1.0"}], "hook_source_identities": {
            "obs": [{"hook": "after_psm", "implementation": "pkg.hooks:Hook", "source_sha256": hook_sha,
                     "distribution": "installed-source"}],
        }},
    }


class ExtensionSourceChangeTests(unittest.TestCase):
    """F-中2: an extension edited in place is detected and never called "no change expected"."""

    def test_installed_extension_source_change_is_detected_without_import(self) -> None:
        from gridform_core.extension_bundle import installed_extension_source_changes

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            version = root / "installed-extensions" / "obs" / "0.1.0"
            (version / "src" / "pkg").mkdir(parents=True)
            hooks = version / "src" / "pkg" / "hooks.py"
            hooks.write_text("raise SystemExit('never imported')\n", encoding="utf-8")
            import hashlib

            installed = hashlib.sha256(hooks.read_bytes()).hexdigest()
            record = {"schema_version": "value.extension-installation/v1", "extension_id": "obs", "version": "0.1.0",
                      "enabled": True, "source_root": "src", "hook_source_identities": [
                          {"hook": "after_psm", "implementation": "pkg.hooks:Hook", "source_sha256": installed}]}
            (version / "installation.json").write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(installed_extension_source_changes(modules_root=root), [])
            hooks.write_text("raise SystemExit('edited, still never imported')\n", encoding="utf-8")
            changes = installed_extension_source_changes(modules_root=root)
            self.assertEqual([(row["extension_id"], row["implementation"], row["installed_sha256"]) for row in changes],
                             [("obs", "pkg.hooks", installed)])
            self.assertEqual(installed_extension_source_changes(["other"], modules_root=root), [])
            record["enabled"] = False
            (version / "installation.json").write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(installed_extension_source_changes(modules_root=root), [])

    def test_graph_rows_name_installed_code_edited_in_place(self) -> None:
        old, new = _graph("b" * 64, "c" * 64), _graph("b" * 64, "d" * 64)
        rows = revision_migration.installed_source_changes(old, new)
        self.assertEqual([(row["kind"], row["id"]) for row in rows], [("extension", "obs")])
        both = revision_migration.installed_source_changes(old, _graph("e" * 64, "d" * 64))
        self.assertEqual([(row["kind"], row["id"]) for row in both], [("module", "hx-flat"), ("extension", "obs")])
        # A built-in (workspace-source) source change ships with a release: not listed.
        builtin = _graph("b" * 64, "c" * 64)
        builtin["modules"]["psm"]["source_sha256"] = "f" * 64
        self.assertEqual(revision_migration.installed_source_changes(old, builtin), [])
        methodology = {"profile_id": "value-corrected"}
        basis = {"payload": {"module_resolution_graph": old, "methodology": methodology}}
        current = {"module_resolution_graph": new, "methodology": methodology}
        differences = revision_migration._differences(basis, current, {})
        graph_row = next(row for row in differences if row["key"] == "module_resolution_graph")
        self.assertEqual(graph_row["classification"], "code_identity_upgrade")
        self.assertIn("results may change", graph_row["effect"])
        record = revision_migration._finish({"classification": "code_identity_upgrade", "differences": differences})
        self.assertTrue(record["automatic"])
        self.assertEqual(record["revision_reason"], "source-reidentify")
        plain = revision_migration._finish({"classification": "code_identity_upgrade", "differences": []})
        self.assertEqual(plain["revision_reason"], "code-identity-upgrade")

    def test_source_reidentify_is_a_known_revision_reason(self) -> None:
        from gridform_core.project_revision import REVISION_REASONS

        self.assertIn("source-reidentify", REVISION_REASONS)


class SourceReidentifyPreflightTests(SavedStudyCase):
    def test_readiness_wording_says_results_may_change(self) -> None:
        old, new = _graph("b" * 64, "c" * 64), _graph("b" * 64, "d" * 64)
        methodology = {"profile_id": "value-corrected"}
        differences = revision_migration._differences(
            {"payload": {"module_resolution_graph": old, "methodology": methodology}},
            {"module_resolution_graph": new, "methodology": methodology}, {})
        classification = revision_migration._finish({
            "classification": "code_identity_upgrade", "declared_sha256": self.saved["revision_sha256"],
            "calculated_sha256": "9" * 64, "differences": differences,
        })
        with patch("gridform_core.preflight.classify_revision_mismatch", return_value=classification):
            report = self.preflight()
        warning = next(row for row in report["warnings"] if row["code"] == "GF_PREFLIGHT_REVISION_REIDENTIFY")
        self.assertIn("extension obs", warning["message"])
        self.assertIn("results may change", warning["message"])
        self.assertNotIn("no change to methods or results expected", warning["message"])
        self.assertTrue(report["accepted"])
        self.assertEqual(report["project_revision_sha256"], self.saved["revision_sha256"])


class LifecycleApiCase(unittest.TestCase):
    """A local API on a scratch data home (the quarantine API test harness)."""

    PACKAGES: tuple[str, ...] = ()

    def setUp(self) -> None:
        import os
        import urllib.error
        import urllib.request

        from backend import server
        from gridform_core import catalog
        from gridform_core.module_quarantine import clear_negative_caches
        from tests.local_api_harness import start_local_api
        from tests.module_lifecycle_fixtures import forget_external_code

        self.server, self.urllib_request, self.urllib_error = server, urllib.request, urllib.error
        self.folder = tempfile.TemporaryDirectory(prefix="value-r44-api-")
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        self.modules = self.home / "modules"
        names = ("MODULE_REGISTRY", "MODULES", "MODULE_SLOT_BY_ID", "REQUIRED_MODULE_SLOTS", "CATALOG_STALE")
        patches = [patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}), patch.object(catalog, "_SNAPSHOT", None)]
        patches += [patch.object(server, name, getattr(server, name)) for name in names]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        clear_negative_caches()
        self.addCleanup(clear_negative_caches)
        self.addCleanup(forget_external_code, self.modules, self.PACKAGES)
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, self.token = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def request(self, method: str, route: str, body: object = None, headers: dict | None = None):
        data, merged = None, dict(headers or {})
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            merged.setdefault("Content-Type", "application/json")
        request = self.urllib_request.Request(self.origin + route, data=data, method=method, headers=merged)
        try:
            with self.urllib_request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read() or b"null")
        except self.urllib_error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    def install_extension(self, extension_id: str, namespace: str, **options) -> tuple[int, dict]:
        from tests.module_lifecycle_fixtures import build_extension_bundle

        bundle = build_extension_bundle(Path(self.folder.name) / f"{extension_id}.zip", extension_id, namespace, **options)
        return self.request("POST", "/api/extensions/install", bundle.read_bytes(), {
            "Content-Type": "application/zip", "X-Filename": bundle.name, "X-VALUE-Executable-Trust": "acknowledged",
        })


class ExtensionRescanApiTests(LifecycleApiCase):
    """F-中3 (Rescan re-imports extension hooks) and F-中2 over HTTP."""

    PACKAGES = ("r44_hook",)

    def test_rescan_quarantines_a_broken_hook_and_restores_a_repaired_one(self) -> None:
        status, body = self.install_extension("r44-observer", "local.r44-observer", hook_package="r44_hook")
        self.assertEqual(status, 201, body)
        hooks = self.modules / "installed-extensions" / "r44-observer" / "0.1.0" / "src" / "r44_hook" / "hooks.py"
        working = hooks.read_text(encoding="utf-8")
        status, body = self.request("POST", "/api/modules/rescan", {})
        self.assertEqual((status, body["status"], body["quarantined_extensions"]), (200, "ok", []), body)
        self.assertGreaterEqual(body["reloaded_extensions"], 1)
        self.assertEqual(self.request("GET", "/api/workspace")[1]["extension_source_changes"], [])
        # A behaviour edit in place is reported (F-中2) ...
        hooks.write_text(working.replace("return {}", "return {'edited': 10}"), encoding="utf-8")
        changes = self.request("GET", "/api/workspace")[1]["extension_source_changes"]
        self.assertEqual([(row["extension_id"], row["implementation"]) for row in changes], [("r44-observer", "r44_hook.hooks")])
        # ... and a hook that no longer imports is quarantined by Rescan (F-中3).
        hooks.write_text(working + "raise RuntimeError('broken after load')\n", encoding="utf-8")
        status, body = self.request("POST", "/api/modules/rescan", {})
        self.assertEqual((status, body["status"], body["quarantined_extensions"]), (200, "degraded", ["r44-observer"]), body)
        entry = next(row for row in body["module_quarantine"]["entries"] if row["id"] == "r44-observer")
        self.assertEqual((entry["kind"], entry["error_code"]), ("extension", "GF_EXTENSION_HOOK_IMPORT"))
        self.assertEqual(self.request("GET", "/api/health")[1]["status"], "degraded")
        hooks.write_text(working, encoding="utf-8")
        status, body = self.request("POST", "/api/modules/rescan", {})
        self.assertEqual((status, body["status"], body["quarantined_extensions"]), (200, "ok", []), body)
        self.assertEqual(self.request("GET", "/api/health")[1]["status"], "ok")


class DerivedReadinessErrorTests(unittest.TestCase):
    """M-低3 / F-低3: quarantined, disabled or stale local code is reported once, with the right action."""

    PACKAGES = ("r44_broken_offer", "r44_bad_hook", "r44_edit_hook")

    def setUp(self) -> None:
        from gridform_core.module_quarantine import clear_negative_caches
        from tests.module_lifecycle_fixtures import forget_external_code

        self.folder = tempfile.TemporaryDirectory(prefix="value-r44-ready-")
        self.addCleanup(self.folder.cleanup)
        self.modules = Path(self.folder.name) / "modules"
        clear_negative_caches()
        self.addCleanup(clear_negative_caches)
        self.addCleanup(forget_external_code, self.modules, self.PACKAGES)
        self.project = {
            "schema_version": "value.project/v1", "id": "project", "name": "Project", "data_pack_id": "pack",
            "start_year": 2025, "end_year": 2034, "parameters": {}, "runtime_options": {},
            "modules": {"psm": PSM, "investment": "agent-investment", "pipeline": "planning-pipeline",
                        "vre_cap": "vre-expansion-cap", "storage_cap": "value-storage-expansion-policy",
                        "storage_cost": "dynamic-annual-storage-cost"},
            "revision_sha256": "0" * 64,
        }

    def run_preflight(self, project: dict) -> dict:
        from tests.test_preflight import PINNED_DISK_USAGE, ResolvedFixture

        with tempfile.TemporaryDirectory() as folder, \
                patch("gridform_core.preflight.validate_data_pack", return_value={
                    "schema_version": "value.data-pack-validation/v1", "valid": True, "errors": [],
                    "warnings": [], "bindings": [], "summary": {"passed": 0, "failed": 0, "total": 0},
                }), \
                patch("gridform_core.preflight.resolve_scheme_c_parameters", return_value=ResolvedFixture()), \
                patch("gridform_core.preflight.shutil.disk_usage", return_value=PINNED_DISK_USAGE):
            return run_preflight(
                project, mode="full", pack_root=Path(folder),
                pack_manifest={"schema_version": "value.data-pack/v1", "id": "pack", "bindings": {}},
                dataset_slots=[], registry=workspace_registry(self.modules), output_root=Path(folder),
            )

    def test_quarantined_module_gives_one_error(self) -> None:
        from tests.module_lifecycle_fixtures import write_external_module

        write_external_module(self.modules, "r44-broken-offer", "r44_broken_offer",
                              prefix="raise RuntimeError('broken offer')\n")
        project = {**self.project, "modules": {**self.project["modules"], "storage_cost": "r44-broken-offer"}}
        report = self.run_preflight(project)
        self.assertFalse(report["accepted"])
        codes = [row["code"] for row in report["errors"]]
        self.assertEqual(codes.count("GF_PREFLIGHT_MODULE_QUARANTINED"), 1, codes)
        self.assertNotIn("GF_PREFLIGHT_MODULE_SELECTION", codes)
        self.assertNotIn("GF_PREFLIGHT_PROJECT_REVISION", codes)
        self.assertEqual(report["checks"]["project_revision"].get("blocked_by"), "local_code")
        issue = next(row for row in report["errors"] if row["code"] == "GF_PREFLIGHT_MODULE_QUARANTINED")
        self.assertIn("Rescan", issue["corrective_action"])

    def test_quarantined_extension_hook_is_reported_once(self) -> None:
        from tests.module_lifecycle_fixtures import write_external_extension

        write_external_extension(self.modules, "r44-bad-hook", "local.r44-bad-hook",
                                 hook_package="r44_bad_hook", hook_prefix="raise ImportError('hook gone')\n")
        project = {**self.project, "selected_extensions": ["r44-bad-hook"]}
        for attempt in ("first", "second"):  # first: found during resolution; second: already quarantined
            with self.subTest(attempt=attempt):
                report = self.run_preflight(project)
                codes = [row["code"] for row in report["errors"]]
                self.assertEqual(codes.count("GF_PREFLIGHT_MODULE_QUARANTINED"), 1, codes)
                self.assertNotIn("GF_PREFLIGHT_MODULE_SELECTION", codes)
                self.assertNotIn("GF_PREFLIGHT_PROJECT_REVISION", codes)

    def test_hook_edited_after_load_asks_for_rescan(self) -> None:
        from gridform_core.extension_framework import ExtensionSourceReloadRequired
        from tests.module_lifecycle_fixtures import write_external_extension

        target = write_external_extension(self.modules, "r44-edit-hook", "local.r44-edit-hook", hook_package="r44_edit_hook")
        project = {**self.project, "selected_extensions": ["r44-edit-hook"]}
        registry = workspace_registry(self.modules)
        registry.extension_registry.resolve(("r44-edit-hook",))  # the hook is now loaded
        hooks = target / "src" / "r44_edit_hook" / "hooks.py"
        hooks.write_text(hooks.read_text(encoding="utf-8") + "# edited after load\n", encoding="utf-8")
        with self.assertRaises(ExtensionSourceReloadRequired):
            registry.extension_registry.resolve(("r44-edit-hook",))
        report = self.run_preflight(project)
        codes = [row["code"] for row in report["errors"]]
        self.assertIn("GF_PREFLIGHT_EXTENSION_SOURCE_RELOAD", codes)
        self.assertNotIn("GF_PREFLIGHT_MODULE_SELECTION", codes)
        self.assertNotIn("GF_PREFLIGHT_PROJECT_REVISION", codes)
        issue = next(row for row in report["errors"] if row["code"] == "GF_PREFLIGHT_EXTENSION_SOURCE_RELOAD")
        self.assertIn("Rescan modules", issue["corrective_action"])


class GraphShiftRegistry(VersionedRegistry):
    """A simulated code-only upgrade: the PSM version and its resolved graph move together."""

    def resolve_selection(self, modules, **kwargs):
        graph = self.base.resolve_selection(modules, **kwargs).to_dict()
        for row in graph["modules"].values():
            if row.get("module_id") in self.versions:
                row["module_version"] = self.versions[row["module_id"]]
        graph["graph_sha256"] = "1" * 64
        return SimpleNamespace(to_dict=lambda: json.loads(json.dumps(graph)))


class MigrationGraphTests(SavedStudyCase):
    """M-中3 (a): a migration revision records the current module graph."""

    def setUp(self) -> None:
        super().setUp()
        import shutil

        project = {key: value for key, value in self.project().items()
                   if key not in {"revision_sha256", "revision_number", "parent_revision_sha256", "fingerprint_basis",
                                  "revision_reason", "change_summary"}}
        project["module_resolution_graph"] = revision_migration.current_module_graph(project, self.registry, self.manifest)
        shutil.rmtree(self.study)  # saved as validation normalises it: with its module graph
        self.saved = save_project_revision(self.study, project, self.registry, self.manifest)

    def test_code_only_migration_refreshes_the_stored_graph(self) -> None:
        stored = self.project()["module_resolution_graph"]
        self.assertEqual(stored["modules"]["psm"]["module_version"], SHIPPED)
        upgraded = GraphShiftRegistry(self.registry, {PSM: UPGRADED})
        with patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=False)):
            saved, classification = revision_migration.migrate_project_revision(self.study, upgraded, self.manifest)
        self.assertEqual(classification["classification"], "code_identity_upgrade")
        self.assertEqual(saved["revision_number"], self.saved["revision_number"] + 1)
        self.assertEqual(saved["module_resolution_graph"]["modules"]["psm"]["module_version"], UPGRADED)
        record = json.loads((self.study / "revisions" / f"{saved['revision_sha256']}.json").read_text(encoding="utf-8"))
        self.assertEqual(record["module_resolution_graph"], saved["module_resolution_graph"])
        self.assertIn("module_resolution_graph", saved["change_summary"])


class DerivationGraphDriftTests(unittest.TestCase):
    """M-中3 (b): a source whose stored graph is stale (code-level only) can be derived from."""

    def setUp(self) -> None:
        from tests.test_study_derivation import StudyDerivationTests

        self.case = StudyDerivationTests("test_reproduction_preserves_configuration_and_source")
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        case = self.case
        # A Study without extensions: the module graph is evidence, not part of the revision hash.
        source = json.loads((case.projects / "baseline" / "project.json").read_text())
        for key in ("revision_sha256", "revision_number", "parent_revision_sha256", "fingerprint_basis",
                    "revision_reason", "change_summary"):
            source.pop(key, None)
        source["selected_extensions"], source["extension_parameters"] = [], {}
        source["module_resolution_graph"] = case.graph(source)
        import shutil

        shutil.rmtree(case.projects / "baseline")
        case.source = save_project_revision(case.projects / "baseline", source, case.registry, case.pack("baseline-pack"))
        case.before = (case.projects / "baseline" / "project.json").read_bytes()

    def test_code_level_drift_is_recorded_not_refused(self) -> None:
        case = self.case
        recorded = case.source["module_resolution_graph"]["graph_sha256"]
        case.registry.source_sha = "b" * 64  # a module source edited in place (A16-4)
        response = case.derive()
        derivation = response["project"]["derivation"]
        drift = derivation["source_module_graph_drift"]
        self.assertEqual(drift["recorded_graph_sha256"], recorded)
        self.assertEqual(drift["current_graph_sha256"], derivation["source_module_graph_sha256"])
        self.assertNotEqual(drift["current_graph_sha256"], recorded)
        self.assertIn(("psm", "source_sha256"), {(row["slot"], row["field"]) for row in drift["differences"]})
        self.assertEqual(response["source_graph_drift"], drift)
        self.assertEqual((case.projects / "baseline" / "project.json").read_bytes(), case.before)

    def test_method_variant_derives_from_the_current_graph(self) -> None:
        case = self.case
        case.registry.source_sha = "b" * 64
        with patch("backend.study_derivation.module_candidate_identity", return_value="c" * 64):
            response = case.derive("edit_module", request=case.method_request())
        self.assertEqual(response["project"]["modules"]["psm"], "candidate-psm")
        self.assertIn("source_module_graph_drift", response["project"]["derivation"])

    def test_unchanged_source_records_no_drift(self) -> None:
        response = self.case.derive()
        self.assertNotIn("source_module_graph_drift", response["project"]["derivation"])
        self.assertNotIn("source_graph_drift", response)


class DeriveSourceMigrationTests(SavedStudyCase):
    """M-中3 (c): the derive API appends a code-only revision of the source first (Q13)."""

    def test_automatic_change_is_appended_and_the_request_follows_it(self) -> None:
        from backend import server

        projects = self.study.parent
        packs = Path(self.folder.name) / "data-packs"
        packs.mkdir()
        import shutil

        shutil.copytree(PACK_ROOT, packs / self.manifest["id"])
        upgraded = GraphShiftRegistry(self.registry, {PSM: UPGRADED})
        body = {"intent": "reproduce", "name": "Copy", "data_pack_id": self.manifest["id"],
                "source_revision_sha256": self.saved["revision_sha256"]}
        with patch.object(server, "PROJECTS_ROOT", projects), patch.object(server, "PACKS_ROOT", packs), \
                patch.object(server, "MODULE_REGISTRY", upgraded), \
                patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=False)):
            stale = server.Handler._migrate_derivation_source(None, "study", {**body, "source_revision_sha256": "0" * 64})
            self.assertEqual(stale, ({**body, "source_revision_sha256": "0" * 64}, None))
            request, migration = server.Handler._migrate_derivation_source(None, "study", body)
        current = self.project()
        self.assertEqual(migration["from_revision_sha256"], self.saved["revision_sha256"])
        self.assertEqual(migration["to_revision_sha256"], current["revision_sha256"])
        self.assertEqual(migration["revision_reason"], "code-identity-upgrade")
        self.assertEqual(request["source_revision_sha256"], current["revision_sha256"])
        # A method change is never appended here: it needs the user's confirmation.
        with patch.object(server, "PROJECTS_ROOT", projects), patch.object(server, "PACKS_ROOT", packs), \
                patch.object(server, "MODULE_REGISTRY", GraphShiftRegistry(self.registry, {PSM: "99.0.0"})), \
                patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=True)):
            body = {**body, "source_revision_sha256": current["revision_sha256"]}
            self.assertEqual(server.Handler._migrate_derivation_source(None, "study", body), (body, None))
        self.assertEqual(self.project()["revision_sha256"], current["revision_sha256"])


class StorageCostEvidenceTests(unittest.TestCase):
    """M-中1: the storage-cost slot shows the market-ledger evidence of the PSM's internal calls."""

    def run_with_ledger(self, ledger_module: str | None) -> dict:
        from backend import server

        with tempfile.TemporaryDirectory() as folder:
            runs = Path(folder)
            output = runs / "r1" / "model-output"
            (output / "market").mkdir(parents=True)
            (output / "orchestrator-events.jsonl").write_text(json.dumps({
                "sequence": 1, "run_id": "r1", "year": 2025, "stage": "psm.run", "module_slot": "psm",
                "module_id": PSM, "module_version": SHIPPED,
            }) + "\n", encoding="utf-8")
            if ledger_module is not None:
                (output / "market" / "index.json").write_text(json.dumps({
                    "years": [2025], "storage_cost_module_id": ledger_module,
                    "rows": {"storage_state": 48, "orders": 2115},
                }), encoding="utf-8")
            run = {"id": "r1", "project_id": "p", "mode": "value_101_day", "status": "completed",
                   "modules": {"psm": PSM, "storage_cost": "hx-flat-storage-offer-73"}, "results": []}
            with patch.object(server, "RUNS_ROOT", runs):
                return server.present_run(run)

    def test_ledger_names_the_storage_cost_module(self) -> None:
        run = self.run_with_ledger("hx-flat-storage-offer-73")
        evidence = run["module_evidence"]["hx-flat-storage-offer-73"]
        self.assertEqual((evidence["source"], evidence["storage_asset_periods"], evidence["years"]),
                         ("market_ledger", 48, [2025]))
        self.assertEqual(run["module_evidence"][PSM]["actions"], 1)

    def test_no_evidence_is_invented(self) -> None:
        self.assertNotIn("hx-flat-storage-offer-73", self.run_with_ledger("dynamic-annual-storage-cost")["module_evidence"])
        self.assertNotIn("hx-flat-storage-offer-73", self.run_with_ledger(None)["module_evidence"])


class CorrectionIdRegistryTests(unittest.TestCase):
    """M-低1: an unregistered correction id fails the ledger check and the overlay seal."""

    @staticmethod
    def _script(name: str):
        import importlib.util

        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_committed_ledger_ids_are_registered_and_a_typo_is_not(self) -> None:
        check = self._script("check_version_ledger")
        ledger = json.loads(check.LEDGER.read_text(encoding="utf-8"))
        manifests = check.load_manifests()
        self.assertEqual(check.check(ledger, manifests, import_classes=False), [])
        registered = check.registered_correction_ids()
        self.assertIn("p08.pro-rata-ties", registered)  # CHANGELOG Correction ids table only
        self.assertIn("r41.down-regulation-taken-once", registered)  # methodology catalogue
        entry = ledger["modules"][PSM]
        current = entry["current_version"]
        major, minor, _patch = (int(part) for part in current.split("."))
        bumped = f"{major}.{minor + 1}.0"
        entry["bumps"].append({"from": current, "to": bumped, "package": "UAT", "reason": "test",
                               "correction_ids": ["x0.uat-edit-module-optin"], "requires_user_opt_in": True})
        entry["current_version"] = bumped
        manifests[PSM]["version"] = bumped
        errors = check.check(ledger, manifests, import_classes=False)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("'x0.uat-edit-module-optin' is not registered", errors[0])

    def test_changelog_table_is_parsed_from_its_section_only(self) -> None:
        check = self._script("check_version_ledger")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "CHANGELOG.md"
            path.write_text("# Changelog\n\n### Notes\n`a1.outside`\n\n### Correction ids\n\n"
                            "| P | `b2.inside-one`, `b2.inside-two` | `market.voll_gbp_per_mwh` |\n\n## Next\n`c3.after`\n",
                            encoding="utf-8")
            self.assertEqual(check.changelog_correction_ids(path), {"b2.inside-one", "b2.inside-two"})

    def test_seal_refuses_an_unregistered_id(self) -> None:
        import contextlib
        import io
        import shutil

        from gridform_core.builtin.scheme_c_1000twh import runtime_overlay as overlay

        seal = self._script("seal_runtime_overlay")
        self.assertIn("p08.pro-rata-ties", seal.known_correction_ids())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "scheme_c"
            root.mkdir()
            for name in ("compat", "runtime_compat"):
                shutil.copytree(overlay.ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(overlay.ROOT / "RUNTIME_OVERLAY.json", root / "RUNTIME_OVERLAY.json")
            before = (root / "RUNTIME_OVERLAY.json").read_bytes()
            kernel = root / "runtime_compat" / "storage_cost.py"
            kernel.write_bytes(kernel.read_bytes() + b"\n# uat edit\n")
            with self.assertRaises(SystemExit) as refused, contextlib.redirect_stdout(io.StringIO()):
                seal.main(["--root", str(root), "--correction", "x0.uat-edit-module-optin"])
            self.assertIn("not registered", str(refused.exception))
            self.assertEqual((root / "RUNTIME_OVERLAY.json").read_bytes(), before)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(seal.main(["--root", str(root), "--correction", "p06.storage-net-per-period"]), 0)
        overlay.clear_runtime_overlay_cache()


if __name__ == "__main__":
    unittest.main()
