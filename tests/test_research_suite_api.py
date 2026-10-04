from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core.data_bundle import build_data_bundle
from gridform_core.research_suite import build_research_suite
from gridform_core.value_uk import value_uk_study_templates


ROOT = Path(__file__).resolve().parents[1]


class ResearchSuiteApiTests(unittest.TestCase):
    def test_upload_installs_two_packs_and_creates_two_unrun_value_uk_studies(self) -> None:
        """Catches the HTTP route installing data without creating runnable Study revisions."""

        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            base_root = state / "base-source"
            network_root = state / "network-source"
            shutil.copytree(ROOT / "data-packs" / "value-101-baseline-v1", base_root)
            shutil.copytree(ROOT / "data-packs" / "value-101-network-v1", network_root)
            (base_root / "derivation.json").unlink(missing_ok=True)
            (network_root / "derivation.json").unlink(missing_ok=True)
            network_manifest_path = network_root / "manifest.json"
            network_manifest = json.loads(network_manifest_path.read_text(encoding="utf-8"))
            network_bindings = dict(network_manifest["bindings"])
            retained_bindings = {
                role: binding
                for role, binding in network_bindings.items()
                if role.startswith("value.zonal.")
            }
            retained_paths = {str(binding["uri"]) for binding in retained_bindings.values()}
            for binding in network_bindings.values():
                relative = str(binding["uri"])
                if relative not in retained_paths:
                    (network_root / relative).unlink(missing_ok=True)
            network_manifest["bindings"] = retained_bindings
            network_manifest_path.write_text(
                json.dumps(network_manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            base_bundle = state / "base.zip"
            network_bundle = state / "network.zip"
            build_data_bundle(pack_root=base_root, destination=base_bundle)
            build_data_bundle(pack_root=network_root, destination=network_bundle)
            templates = state / "study-templates.json"
            templates.write_text(
                json.dumps(
                    {
                        "schema_version": "value.study-templates/v1",
                        "studies": list(
                            value_uk_study_templates(
                                "value-101-baseline-v1", "value-101-network-v1"
                            )
                        ),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            rights = state / "RIGHTS.json"
            rights.write_text(
                json.dumps({"schema_version": "value.data-rights/v1", "redistribution": "test"}),
                encoding="utf-8",
            )
            attribution = state / "ATTRIBUTION.md"
            attribution.write_text("# Attribution\n\nSynthetic API fixture.\n", encoding="utf-8")
            suite = state / "value-uk-suite.zip"
            build_research_suite(
                base_bundle=base_bundle,
                network_bundle=network_bundle,
                studies_path=templates,
                rights_paths=(rights, attribution),
                destination=suite,
            )
            body = suite.read_bytes()
            patches = (
                patch.dict(os.environ, {"VALUE_DATA_HOME": str(state)}),
                patch.object(server, "STATE_ROOT", state),
                patch.object(server, "IMPORT_STAGING_ROOT", state / "import-staging"),
                patch.object(server, "PACKS_ROOT", state / "data-packs"),
                patch.object(server, "PROJECTS_ROOT", state / "projects"),
                patch.object(server, "RUNS_ROOT", state / "runs"),
                patch.object(server, "ARCHIVES_ROOT", state / "archives"),
                patch.object(server, "TRASH_ROOT", state / "trash"),
                patch.object(server, "MIN_FREE_SPACE_BYTES", 0),
            )
            for item in patches:
                item.start()
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                request = urllib.request.Request(
                    origin + "/api/research-suites/install",
                    data=body,
                    method="POST",
                    headers={
                        "Content-Type": "application/zip",
                        "X-Filename": "VALUE-UK-Research-Suite.bundle.zip",
                        "X-VALUE-Data-Rights": "acknowledged",
                    },
                )
                try:
                    response = json.loads(urllib.request.urlopen(request, timeout=30).read())
                except urllib.error.HTTPError as exc:
                    self.fail(exc.read().decode("utf-8", errors="replace"))

                self.assertTrue(response["ok"])
                self.assertEqual(
                    response["installation"]["component_pack_ids"],
                    ["value-101-baseline-v1", "value-101-network-v1"],
                )
                self.assertEqual(
                    response["installation"]["study_ids"],
                    ["value-uk-copperplate-2025-2034", "value-uk-zonal-2025-2034"],
                )
                projects = {
                    path.parent.name: json.loads(path.read_text(encoding="utf-8"))
                    for path in (state / "projects").glob("*/project.json")
                }
                self.assertEqual(set(projects), set(response["installation"]["study_ids"]))
                self.assertEqual(projects["value-uk-copperplate-2025-2034"]["end_year"], 2034)
                self.assertEqual(
                    projects["value-uk-zonal-2025-2034"]["market_configuration"]["network_pack_id"],
                    "value-101-network-v1",
                )
                self.assertEqual(
                    projects["value-uk-zonal-2025-2034"]["modules"]["weather_spatializer"],
                    "value-representative-point-weather",
                )
                self.assertEqual(
                    projects["value-uk-zonal-2025-2034"]["market_configuration"][
                        "weather_spatialisation_module_id"
                    ],
                    "value-representative-point-weather",
                )
                self.assertFalse((state / "runs").exists())
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
                for item in reversed(patches):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
