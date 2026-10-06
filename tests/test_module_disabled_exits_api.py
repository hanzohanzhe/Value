"""Spec 11.4 (M-D4, F-D3): ways back from a disabled or quarantined local module or extension.

* Enable reports the result of a fresh scan, never a remembered failed import.
* Remove moves the entry's files out of the scanned folders (never deletes)
  and refuses an enabled working entry or one that saved Studies use.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core import catalog
from gridform_core.module_quarantine import clear_negative_caches
from tests.local_api_harness import start_local_api
from tests.module_lifecycle_fixtures import example_plugin_source, forget_external_code, write_external_extension, write_external_module

MODULE_ID, PACKAGE = "p02-exit-module", "p02_exit_module"
OTHER_ID, OTHER_PACKAGE = "p02-exit-working", "p02_exit_working"
EXTENSION_ID = "p02-exit-extension"


class DisabledExitTests(unittest.TestCase):
    def setUp(self) -> None:
        # The same harness as tests.test_module_quarantine_study.DraftQuarantineTests.
        folder = tempfile.mkdtemp(prefix="value-fx3-exits-")
        self.addCleanup(shutil.rmtree, folder, True)
        self.home = Path(folder) / "state"
        self.modules = self.home / "modules"
        clear_negative_caches()
        self.addCleanup(clear_negative_caches)
        self.addCleanup(forget_external_code, self.modules, (PACKAGE, OTHER_PACKAGE))
        patches = [patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}), patch.object(catalog, "_SNAPSHOT", None)]
        patches += [patch.object(server, name, getattr(server, name))
                    for name in ("MODULE_REGISTRY", "MODULES", "MODULE_SLOT_BY_ID", "REQUIRED_MODULE_SLOTS", "CATALOG_STALE")]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, _ = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def _post(self, path: str) -> tuple[int, dict]:
        request = urllib.request.Request(self.origin + path, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def _plugin(self, module_id: str, package: str):
        return self.modules / "installed" / module_id / "1.0.0" / "src" / package / "plugin.py"

    def test_enable_after_a_fix_uses_a_fresh_scan(self) -> None:
        write_external_module(self.modules, MODULE_ID, PACKAGE, prefix="raise RuntimeError('first failure')\n")
        server.refresh_module_catalog()
        self.assertIn(MODULE_ID, server._quarantined_ids("module"))
        status, payload = self._post(f"/api/modules/{MODULE_ID}/disable")
        self.assertEqual(status, 200, payload)
        # Still broken, but differently: the error is the new one, not the remembered one.
        self._plugin(MODULE_ID, PACKAGE).write_text("raise RuntimeError('second failure')\n" + example_plugin_source(), encoding="utf-8")
        status, payload = self._post(f"/api/modules/{MODULE_ID}/enable")
        self.assertGreaterEqual(status, 400, payload)
        self.assertIn("second failure", json.dumps(payload))
        self.assertNotIn("first failure", json.dumps(payload))
        # Fixed: Enable succeeds without a separate Rescan, and it forgot every
        # remembered failed import first (the stale-error path of M-D4).
        self._plugin(MODULE_ID, PACKAGE).write_text(example_plugin_source(), encoding="utf-8")
        with patch.object(server, "clear_negative_caches", wraps=server.clear_negative_caches) as cleared:
            status, payload = self._post(f"/api/modules/{MODULE_ID}/enable")
        cleared.assert_called()
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["installation"]["enabled"])

    def test_remove_parks_a_disabled_module_and_keeps_its_files(self) -> None:
        write_external_module(self.modules, MODULE_ID, PACKAGE, enabled=False)
        server.refresh_module_catalog()
        status, payload = self._post(f"/api/modules/{MODULE_ID}/remove")
        self.assertEqual(status, 200, payload)
        self.assertFalse((self.modules / "installed" / MODULE_ID).exists())
        destination = self.modules / payload["removed"]["destination"]
        self.assertTrue(destination.is_relative_to(self.modules / "disabled-manifests" / "removed" / "modules" / MODULE_ID))
        self.assertTrue((destination / MODULE_ID / "1.0.0" / "installation.json").is_file())
        self.assertNotIn(MODULE_ID, [row["module_id"] for row in server.list_module_installations()])

    def test_remove_of_a_quarantined_module_parks_its_manifest_too(self) -> None:
        write_external_module(self.modules, MODULE_ID, PACKAGE, prefix="raise RuntimeError('broken')\n")
        server.refresh_module_catalog()
        status, payload = self._post(f"/api/modules/{MODULE_ID}/remove")
        self.assertEqual(status, 200, payload)
        self.assertFalse((self.modules / f"{MODULE_ID}.json").exists())
        self.assertNotIn(MODULE_ID, server._quarantined_ids("module"))
        self.assertEqual(payload["module_quarantine"]["status"], "ok")

    def test_remove_refuses_an_enabled_working_module(self) -> None:
        write_external_module(self.modules, OTHER_ID, OTHER_PACKAGE)
        server.refresh_module_catalog()
        status, payload = self._post(f"/api/modules/{OTHER_ID}/remove")
        self.assertEqual((status, payload["error_code"]), (409, "GF_MODULE_REMOVE_ENABLED"))
        self.assertTrue((self.modules / "installed" / OTHER_ID).is_dir())

    def test_remove_refuses_a_module_saved_studies_use(self) -> None:
        write_external_module(self.modules, MODULE_ID, PACKAGE, enabled=False)
        project = self.home / "projects" / "uses-it" / "project.json"
        project.parent.mkdir(parents=True, exist_ok=True)
        project.write_text(json.dumps({"id": "uses-it", "modules": {"storage_cost": MODULE_ID}}), encoding="utf-8")
        status, payload = self._post(f"/api/modules/{MODULE_ID}/remove")
        self.assertEqual((status, payload["error_code"]), (409, "GF_MODULE_IN_USE"))
        self.assertEqual(payload["dependents"]["projects"], ["uses-it"])
        self.assertTrue((self.modules / "installed" / MODULE_ID).is_dir())

    def test_extension_enable_also_starts_from_a_fresh_scan(self) -> None:
        write_external_extension(self.modules, EXTENSION_ID, "local.p02-exit-extension", enabled=False)
        with patch.object(server, "clear_negative_caches", wraps=server.clear_negative_caches) as cleared:
            status, payload = self._post(f"/api/extensions/{EXTENSION_ID}/enable")
        self.assertEqual(status, 200, payload)
        cleared.assert_called()

    def test_remove_parks_a_disabled_extension(self) -> None:
        write_external_extension(self.modules, EXTENSION_ID, "local.p02-exit-extension", enabled=False)
        status, payload = self._post(f"/api/extensions/{EXTENSION_ID}/remove")
        self.assertEqual(status, 200, payload)
        self.assertFalse((self.modules / "installed-extensions" / EXTENSION_ID).exists())
        self.assertEqual(payload["removed"]["kind"], "extension")

    def test_remove_of_an_unknown_entry_is_404(self) -> None:
        status, payload = self._post("/api/modules/not-installed-anywhere/remove")
        self.assertEqual((status, payload["error_code"]), (404, "GF_MODULE_NOT_INSTALLED"))
