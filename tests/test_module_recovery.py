"""Offline self-rescue CLI: python -m gridform_core.module_recovery (P0-2 S8)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gridform_core import module_recovery
from gridform_core.v2.module_manifest import workspace_registry
from tests.module_lifecycle_fixtures import forget_external_code, write_external_extension, write_external_module

ROOT = Path(__file__).resolve().parents[1]


class ModuleRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory(prefix="value-p02-recovery-")
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        self.modules = self.home / "modules"
        self.addCleanup(forget_external_code, self.modules, ("p02_rescue_plugin", "p02_rescue_ok"))

    def _main(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module_recovery.main(["--modules-root", str(self.modules), *arguments])
        return code, out.getvalue(), err.getvalue()

    def test_disable_never_imports_the_catalogue_or_the_broken_code(self) -> None:
        counter = Path(self.folder.name) / "imports.txt"
        write_external_module(self.modules, "p02-rescue", "p02_rescue_plugin",
                              prefix="raise SystemExit(13)\n", counter_file=counter)
        environment = dict(os.environ)
        environment.update(VALUE_DATA_HOME=str(self.home), PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        code = (
            "import sys\n"
            "from gridform_core import module_recovery\n"
            "status = module_recovery.main(['disable', 'module', 'p02-rescue'])\n"
            "loaded = sorted(n for n in sys.modules if n == 'gridform_core.catalog' or n.startswith('p02_'))\n"
            "print('RESULT', status, loaded)\n"
        )
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=environment,
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("RESULT 0 []", result.stdout)
        self.assertFalse(counter.exists(), "the broken plugin was executed")
        record = json.loads((self.modules / "installed" / "p02-rescue" / "1.0.0" / "installation.json").read_text())
        self.assertFalse(record["enabled"])
        self.assertFalse((self.modules / "p02-rescue.json").exists())
        self.assertEqual(workspace_registry(self.modules).quarantined, ())

    def test_a_schema_drifted_extension_can_be_disabled_offline(self) -> None:
        write_external_extension(self.modules, "p02-rescue-drift", "local.p02-rescue",
                                 manifest_overrides={"required_force_version": ">=0.5.0"})
        self.assertEqual(len(workspace_registry(self.modules).quarantined), 1)
        code, out, _ = self._main("disable", "extension", "p02-rescue-drift")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.modules / "extensions" / "p02-rescue-drift.json").exists())
        self.assertTrue((self.modules / "disabled-extensions" / "p02-rescue-drift.json").is_file())
        self.assertEqual(workspace_registry(self.modules).quarantined, ())

    def test_list_reports_damaged_records_collisions_and_parked_files(self) -> None:
        target = write_external_module(self.modules, "p02-rescue", "p02_rescue_plugin")
        (target / "installation.json").write_text("{damaged", encoding="utf-8")
        write_external_extension(self.modules, "p02-ns-a", "local.p02-same")
        write_external_extension(self.modules, "p02-ns-b", "local.p02-same")
        (self.modules / "broken.json").write_text("{", encoding="utf-8")
        self.assertEqual(self._main("park-manifest", "module", "broken")[0], 0)
        code, out, _ = self._main("list", "--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        problems = {(row["file"], problem) for row in report["entries"] for problem in row["problems"]}
        self.assertIn(("installed/p02-rescue/1.0.0/installation.json", "installation record unreadable (JSONDecodeError)"),
                      problems)
        self.assertIn("park-installation module p02-rescue 1.0.0",
                      [row.get("fix") for row in report["entries"]])
        self.assertIn(("extensions/p02-ns-a.json", "namespace shared with p02-ns-b"), problems)
        self.assertEqual(len(report["parked_manifests"]), 1)
        self.assertTrue(report["parked_manifests"][0].startswith("disabled-manifests/modules/broken."))
        code, text, _ = self._main("list")
        self.assertIn("problem: installation record unreadable", text)
        self.assertIn("fix:     park-installation module p02-rescue 1.0.0", text)

    def test_a_damaged_record_is_degraded_and_one_command_rescues_it(self) -> None:
        from gridform_core.execution_archive import ExecutionArchiveError, _source_roots
        from gridform_core.module_quarantine import degraded_reasons, installation_record_entries

        target = write_external_module(self.modules, "p02-rescue", "p02_rescue_plugin")
        (target / "installation.json").write_text("{damaged", encoding="utf-8")
        with self.assertRaises(ExecutionArchiveError) as caught:
            _source_roots(ROOT, self.home)
        self.assertIn("park-installation module p02-rescue 1.0.0", str(caught.exception))
        [entry] = installation_record_entries(self.modules)
        self.assertEqual((entry.kind, entry.entry_id, entry.version, entry.code),
                         ("module", "p02-rescue", "1.0.0", "GF_MODULE_INSTALL_RECORD_INVALID"))
        self.assertIn("park-installation module p02-rescue 1.0.0", entry.to_dict()["corrective_action"])
        # Its source root is no longer activated, so the active manifest also
        # fails to import; the damaged record is reported in its own right.
        registry = workspace_registry(self.modules)
        self.assertIn({"code": "GF_MODULE_INSTALL_RECORD_INVALID", "count": 1},
                      degraded_reasons(registry, entries=installation_record_entries(self.modules)))
        code, _, err = self._main("disable", "module", "p02-rescue")
        self.assertEqual(code, 1)
        self.assertIn("park-installation module p02-rescue 1.0.0", err)
        code, out, _ = self._main("park-installation", "module", "p02-rescue")
        self.assertEqual(code, 0, out)
        result = json.loads(out)
        self.assertTrue(result["parked"][0].startswith("installed/p02-rescue/1.0.0 -> disabled-manifests/installed/p02-rescue/1.0.0."))
        self.assertTrue(result["active_manifest"].startswith("disabled-manifests/modules/p02-rescue."))
        self.assertFalse((self.modules / "installed" / "p02-rescue").exists())
        self.assertFalse((self.modules / "p02-rescue.json").exists())
        _source_roots(ROOT, self.home)  # every run start works again
        self.assertEqual(installation_record_entries(self.modules), ())
        self.assertEqual(degraded_reasons(workspace_registry(self.modules)), [])
        self.assertNotIn("p02-rescue", workspace_registry(self.modules).manifests())
        report = json.loads(self._main("list", "--json")[1])
        self.assertTrue(any(name.startswith("disabled-manifests/installed/p02-rescue/1.0.0.")
                            for name in report["parked_manifests"]))

    def test_park_installation_keeps_a_readable_current_version(self) -> None:
        old = write_external_extension(self.modules, "p02-rescue-ext", "local.p02-rescue", version="1.0.0",
                                       enabled=False)
        write_external_extension(self.modules, "p02-rescue-ext", "local.p02-rescue", version="2.0.0")
        (old / "installation.json").unlink()
        code, out, err = self._main("list", "--json")
        rows = [row for row in json.loads(out)["entries"] if row["problems"]]
        self.assertEqual([(row["file"], row["problems"], row["fix"]) for row in rows], [(
            "installed-extensions/p02-rescue-ext/1.0.0", ["installation record is missing"],
            "park-installation extension p02-rescue-ext 1.0.0")])
        code, out, _ = self._main("park-installation", "extension", "p02-rescue-ext")
        self.assertEqual(code, 0, out)
        self.assertNotIn("active_manifest", json.loads(out))
        self.assertTrue((self.modules / "extensions" / "p02-rescue-ext.json").is_file())
        self.assertTrue((self.modules / "installed-extensions" / "p02-rescue-ext" / "2.0.0").is_dir())
        self.assertIn("p02-rescue-ext", workspace_registry(self.modules).extension_manifests())
        code, _, err = self._main("park-installation", "extension", "p02-rescue-ext")
        self.assertEqual(code, 1)
        self.assertIn("No damaged installation", err)
        self.assertEqual(self._main("park-installation", "extension", "p02-absent")[0], 1)

    def test_a_parked_module_id_stays_taken(self) -> None:
        from gridform_core.module_bundle import build_module_bundle
        from gridform_core.module_installation import ModuleInstallationError, install_module_bundle
        from tests.module_lifecycle_fixtures import EXAMPLE

        target = write_external_module(self.modules, "example-flat-storage-offer", "p02_rescue_plugin")
        (target / "installation.json").write_text("[]", encoding="utf-8")
        self.assertEqual(self._main("park-installation", "module", "example-flat-storage-offer")[0], 0)
        bundle = Path(self.folder.name) / "example.zip"
        build_module_bundle(manifest_path=EXAMPLE / "value-module.json", source_root=EXAMPLE / "src",
                            license_path=ROOT / "LICENSE", readme_path=EXAMPLE / "README.md", destination=bundle)
        with self.assertRaises(ModuleInstallationError) as caught:
            install_module_bundle(bundle, trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_ID_COLLISION")
        self.assertIn("parked", str(caught.exception))

    def test_refuses_while_a_backend_holds_the_data_directory(self) -> None:
        from backend.lifecycle.file_locks import FileLock

        write_external_module(self.modules, "p02-rescue-ok", "p02_rescue_ok")
        lock = FileLock(self.home / ".backend.lock").acquire(timeout=0)
        try:
            # Probe from another process: this thread's own lock would read as held anyway.
            environment = dict(os.environ)
            environment.update(PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(
                [sys.executable, "-B", "-m", "gridform_core.module_recovery", "--modules-root", str(self.modules),
                 "disable", "module", "p02-rescue-ok"],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=180,
            )
            self.assertEqual(result.returncode, 3, result.stderr[-2000:])
            self.assertIn("use the Modules page", result.stderr)
            self.assertTrue((self.modules / "p02-rescue-ok.json").exists())
            code, _, _ = self._main("disable", "module", "p02-rescue-ok", "--force")
            self.assertEqual(code, 0)
        finally:
            lock.release()

    def test_unknown_ids_are_reported(self) -> None:
        self.modules.mkdir(parents=True)
        self.assertEqual(self._main("disable", "module", "p02-absent")[0], 1)
        self.assertEqual(self._main("park-manifest", "extension", "p02-absent")[0], 1)

    def test_verify_reports_the_registry(self) -> None:
        write_external_module(self.modules, "p02-rescue", "p02_rescue_plugin", prefix="raise RuntimeError('x')\n")
        report = Path(self.folder.name) / "report.json"
        self.assertEqual(self._main("verify", "--report", str(report))[0], 0)
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "value.module-registry-probe/v1")
        self.assertIn("value-bid-at-cost-psm", payload["modules"])
        self.assertEqual([row["id"] for row in payload["quarantined"]], ["p02-rescue"])


if __name__ == "__main__":
    unittest.main()
