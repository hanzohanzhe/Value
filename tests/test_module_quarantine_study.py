"""Quarantine at the four Study stages: draft, preflight, worker, derivation (P0-2 S7)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core import catalog
from gridform_core.module_quarantine import (
    ExtensionHookImportError,
    clear_negative_caches,
    hook_quarantine_entries,
)
from gridform_core.preflight import run_preflight
from gridform_core.v2.module_manifest import workspace_registry
from tests.local_api_harness import start_local_api
from tests.module_lifecycle_fixtures import forget_external_code, write_external_extension, write_external_module
from tests.test_preflight import MODULES, PINNED_DISK_USAGE, ResolvedFixture

PACKAGES = ("p02_study_broken", "p02_study_hook")


class _QuarantineHome(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory(prefix="value-p02-study-")
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        self.modules = self.home / "modules"
        clear_negative_caches()
        self.addCleanup(clear_negative_caches)
        self.addCleanup(forget_external_code, self.modules, PACKAGES)

    def broken_module(self) -> None:
        write_external_module(self.modules, "p02-study-broken", "p02_study_broken",
                              prefix="raise RuntimeError('broken for the Study tests')\n")

    def broken_hook(self) -> None:
        write_external_extension(self.modules, "p02-study-hook", "local.p02-study-hook",
                                 hook_package="p02_study_hook", hook_prefix="raise ImportError('hook gone')\n")


class PreflightQuarantineTests(_QuarantineHome):
    project = {
        "schema_version": "value.project/v1", "id": "project", "name": "Project", "data_pack_id": "pack",
        "start_year": 2025, "end_year": 2034, "modules": MODULES, "parameters": {}, "runtime_options": {},
    }

    def _run(self, registry, project=None) -> dict:
        with tempfile.TemporaryDirectory() as folder, \
                patch("gridform_core.preflight.validate_data_pack", return_value={
                    "schema_version": "value.data-pack-validation/v1", "valid": True, "errors": [],
                    "warnings": [], "bindings": [], "summary": {"passed": 0, "failed": 0, "total": 0},
                }), \
                patch("gridform_core.preflight.resolve_scheme_c_parameters", return_value=ResolvedFixture()), \
                patch("gridform_core.preflight.shutil.disk_usage", return_value=PINNED_DISK_USAGE):
            return run_preflight(
                project or self.project, mode="full", pack_root=Path(folder),
                pack_manifest={"schema_version": "value.data-pack/v1", "id": "pack", "bindings": {}},
                dataset_slots=[], registry=registry, output_root=Path(folder),
            )

    @staticmethod
    def _codes(report: dict) -> list[tuple[str, str]]:
        return sorted((row["severity"], row["code"]) for row in report["errors"] + report["warnings"])

    def test_shadow_oracle_unrelated_quarantine_adds_exactly_one_warning(self) -> None:
        baseline = self._run(workspace_registry(self.home / "no-modules"))
        self.broken_module()
        self.broken_hook()
        registry = workspace_registry(self.modules)
        with self.assertRaises(ExtensionHookImportError):
            registry.extension_registry.resolve(("p02-study-hook",))
        quarantined = self._run(registry)
        self.assertTrue(baseline["accepted"])
        self.assertTrue(quarantined["accepted"])
        added = list(self._codes(quarantined))
        for row in self._codes(baseline):
            added.remove(row)
        self.assertEqual(added, [("warning", "GF_PREFLIGHT_MODULE_QUARANTINE_PRESENT")])
        check = quarantined["checks"]["module_quarantine"]
        self.assertEqual((check["passed"], check["status"], len(check["entries"])), (True, "degraded", 2))
        self.assertEqual(baseline["checks"]["module_quarantine"]["status"], "ok")
        evidence = quarantined["checks"]["external_code"]
        self.assertEqual(evidence["enabled_external_extensions"], ["p02-study-hook"])
        self.assertEqual(evidence["selected_external_modules"], [])
        self.assertTrue(evidence["external_code_loaded"])
        self.assertFalse(baseline["checks"]["external_code"]["external_code_loaded"])

    def test_a_selected_quarantined_module_blocks_with_its_code(self) -> None:
        self.broken_module()
        project = {**self.project, "modules": {**MODULES, "storage_cost": "p02-study-broken"}}
        report = self._run(workspace_registry(self.modules), project)
        self.assertFalse(report["accepted"])
        self.assertIn("GF_PREFLIGHT_MODULE_QUARANTINED", {row["code"] for row in report["errors"]})
        self.assertEqual(report["checks"]["module_quarantine"]["blockers"][0]["id"], "p02-study-broken")

    def test_a_selected_quarantined_extension_blocks_without_crashing(self) -> None:
        write_external_extension(self.modules, "p02-ns-1", "local.p02-collide")
        write_external_extension(self.modules, "p02-ns-2", "local.p02-collide")
        project = {**self.project, "selected_extensions": ["p02-ns-1"]}
        report = self._run(workspace_registry(self.modules), project)
        self.assertFalse(report["accepted"])
        codes = {row["code"] for row in report["errors"]}
        self.assertIn("GF_PREFLIGHT_MODULE_QUARANTINED", codes)
        self.assertEqual(report["checks"]["module_quarantine"]["blockers"][0]["error_code"],
                         "GF_EXTENSION_NAMESPACE_COLLISION")


    def test_a_broken_hook_selected_on_the_first_preflight_has_the_quarantine_code(self) -> None:
        self.broken_hook()
        self.assertEqual(hook_quarantine_entries(), ())  # no earlier resolution in this process
        project = {**self.project, "selected_extensions": ["p02-study-hook"]}
        first = self._run(workspace_registry(self.modules), project)
        second = self._run(workspace_registry(self.modules), project)
        for report in (first, second):
            self.assertFalse(report["accepted"])
            codes = {row["code"] for row in report["errors"]}
            self.assertIn("GF_PREFLIGHT_MODULE_QUARANTINED", codes)
            self.assertNotIn("GF_PREFLIGHT_MODULE_SELECTION", codes)
            self.assertEqual([row["id"] for row in report["checks"]["module_quarantine"]["blockers"]],
                             ["p02-study-hook"])
        self.assertEqual(first["errors"][0]["code"], second["errors"][0]["code"])

class DraftQuarantineTests(_QuarantineHome):
    def setUp(self) -> None:
        super().setUp()
        patches = [patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}),
                   patch.object(catalog, "_SNAPSHOT", None)]
        patches += [patch.object(server, name, getattr(server, name))
                    for name in ("MODULE_REGISTRY", "MODULES", "MODULE_SLOT_BY_ID", "REQUIRED_MODULE_SLOTS",
                                 "CATALOG_STALE")]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, _ = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def _draft(self, study: dict) -> tuple[int, dict]:
        request = urllib.request.Request(self.origin + "/api/projects/resolve-draft", method="POST",
                                         data=json.dumps(study).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def _study(self, **changes) -> dict:
        return {"id": "draft", "name": "Draft", "data_pack_id": "none", "start_year": 2025, "end_year": 2025,
                "modules": dict(MODULES), **changes}

    def test_unrelated_draft_resolves_with_one_extra_warning(self) -> None:
        server.refresh_module_catalog()
        status, baseline = self._draft(self._study())
        self.assertEqual(status, 200)
        self.broken_module()
        self.broken_hook()
        server.refresh_module_catalog()
        status, draft = self._draft(self._study())
        self.assertEqual(status, 200)
        self.assertEqual(draft["errors"], baseline["errors"])
        self.assertEqual(draft["valid"], baseline["valid"])
        self.assertEqual([row["code"] for row in draft["warnings"]],
                         [row["code"] for row in baseline["warnings"]] + ["GF_MODULE_QUARANTINE_PRESENT"])
        self.assertEqual(draft["graph_sha256"], baseline["graph_sha256"])

    def test_selecting_quarantined_code_names_it(self) -> None:
        self.broken_module()
        self.broken_hook()
        server.refresh_module_catalog()
        status, module_draft = self._draft(self._study(modules={**MODULES, "storage_cost": "p02-study-broken"}))
        self.assertEqual(status, 200)
        self.assertFalse(module_draft["valid"])
        self.assertIn("GF_STUDY_MODULE_QUARANTINED", [row["code"] for row in module_draft["errors"]])
        status, hook_draft = self._draft(self._study(selected_extensions=["p02-study-hook"]))
        self.assertEqual(status, 200)
        self.assertIn("GF_STUDY_MODULE_QUARANTINED", [row["code"] for row in hook_draft["errors"]])
        self.assertEqual([entry.entry_id for entry in hook_quarantine_entries()], ["p02-study-hook"])


class WorkerQuarantineTests(_QuarantineHome):
    def _queued_run(self, project: dict) -> Path:
        from backend.lifecycle.run_status import create_status

        run_dir = self.home / "runs" / "run-1"
        (run_dir / "input-snapshot").mkdir(parents=True)
        (run_dir / "input-snapshot" / "project.json").write_text(json.dumps(project), encoding="utf-8")
        create_status(run_dir, {"id": "run-1", "project_id": "study", "mode": "smoke", "status": "queued"})
        return run_dir

    def _execute(self, run_dir: Path) -> int:
        from backend import model_runner

        with patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}), \
                patch.object(model_runner, "STATE_ROOT", self.home), \
                patch("gridform_core.provenance.write_failed_run_provenance", side_effect=RuntimeError("skip")):
            return model_runner.execute("study", "run-1", "smoke", status_path=run_dir / "status.json")

    def test_worker_fails_with_the_quarantine_code_instead_of_staying_queued(self) -> None:
        from backend.lifecycle.run_status import read_status

        self.broken_module()
        run_dir = self._queued_run({"modules": {**MODULES, "storage_cost": "p02-study-broken"}})
        self.assertEqual(self._execute(run_dir), 1)
        status = read_status(run_dir)
        self.assertEqual((status["status"], status["error_code"]), ("failed", "GF_MODULE_QUARANTINED"))
        diagnostic = json.loads((run_dir / "diagnostics" / "error.json").read_text(encoding="utf-8"))
        self.assertIn("p02-study-broken", diagnostic["exception_message"])

    def test_a_hook_import_failure_in_the_worker_keeps_its_code(self) -> None:
        from backend import model_runner
        from backend.lifecycle.run_status import read_status

        run_dir = self._queued_run({"modules": dict(MODULES)})
        error = ExtensionHookImportError("Extension hook x.hooks:Hook failed to import: ImportError: gone")
        with patch.object(model_runner, "run", side_effect=error):
            self.assertEqual(self._execute(run_dir), 1)
        status = read_status(run_dir)
        self.assertEqual((status["status"], status["error_code"]), ("failed", "GF_EXTENSION_HOOK_IMPORT"))


class DerivationQuarantineTests(_QuarantineHome):
    def test_a_quarantined_replacement_module_is_refused_with_its_code(self) -> None:
        from backend.study_derivation import StudyDerivationError, _method_candidate

        self.broken_module()
        registry = workspace_registry(self.modules)
        with self.assertRaises(StudyDerivationError) as caught:
            _method_candidate({"modules": dict(MODULES)}, {
                "slot": "storage_cost", "module_id": "p02-study-broken",
                "candidate_identity_sha256": "0" * 64,
            }, registry)
        self.assertEqual((caught.exception.code, caught.exception.status), ("GF_STUDY_MODULE_QUARANTINED", 409))


if __name__ == "__main__":
    unittest.main()
