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
from gridform_core.module_bundle import build_module_bundle
from tests.local_api_harness import start_local_api


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "external_module_bundle"


class ModuleInstallationApiTests(unittest.TestCase):
    def test_loopback_upload_refresh_and_disable_guard(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            bundle = state / "example.zip"
            build_module_bundle(
                manifest_path=EXAMPLE / "value-module.json",
                source_root=EXAMPLE / "src",
                license_path=ROOT / "LICENSE",
                readme_path=EXAMPLE / "README.md",
                destination=bundle,
            )
            projects, runs = state / "projects", state / "runs"
            patches = (
                patch.dict(os.environ, {"VALUE_DATA_HOME": str(state)}),
                patch.object(server, "STATE_ROOT", state),
                patch.object(server, "IMPORT_STAGING_ROOT", state / "import-staging"),
                patch.object(server, "PACKS_ROOT", state / "data-packs"),
                patch.object(server, "PROJECTS_ROOT", projects),
                patch.object(server, "RUNS_ROOT", runs),
                patch.object(server, "ARCHIVES_ROOT", state / "archives"),
                patch.object(server, "TRASH_ROOT", state / "trash"),
            )
            for item in patches:
                item.start()
            api = start_local_api(data_home=Path(folder), patch_state_roots=False)
            httpd, origin, _session = api.start()
            try:
                untrusted = urllib.request.Request(
                    origin + "/api/modules/install",
                    data=bundle.read_bytes(),
                    method="POST",
                    headers={"Content-Type": "application/zip", "X-Filename": "example.zip"},
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(untrusted, timeout=10)
                self.assertEqual(rejected.exception.code, 400)

                trusted = urllib.request.Request(
                    origin + "/api/modules/install",
                    data=bundle.read_bytes(),
                    method="POST",
                    headers={
                        "Content-Type": "application/zip",
                        "X-Filename": "example.zip",
                        "X-Force-Executable-Trust": "acknowledged",
                    },
                )
                payload = json.loads(urllib.request.urlopen(trusted, timeout=10).read())
                self.assertTrue(payload["ok"])
                workspace = json.loads(
                    urllib.request.urlopen(origin + "/api/workspace", timeout=10).read()
                )
                installed = next(
                    row for row in workspace["modules"]
                    if row["id"] == "example-flat-storage-offer"
                )
                self.assertEqual(installed["origin"], "local_bundle")

                project_path = projects / "uses-external" / "project.json"
                project_path.parent.mkdir(parents=True)
                project_path.write_text(json.dumps({
                    "id": "uses-external",
                    "modules": {"storage_cost": "example-flat-storage-offer"},
                }), encoding="utf-8")
                disable = urllib.request.Request(
                    origin + "/api/modules/example-flat-storage-offer/disable",
                    data=b"{}", method="POST", headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as blocked:
                    urllib.request.urlopen(disable, timeout=10)
                self.assertEqual(blocked.exception.code, 409)
                body = json.loads(blocked.exception.read())
                self.assertEqual(body["error_code"], "GF_MODULE_IN_USE")
            finally:
                api.stop()
                for item in reversed(patches):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
