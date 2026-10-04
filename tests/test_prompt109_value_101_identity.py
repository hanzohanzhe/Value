from __future__ import annotations

import importlib
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core.v2.module_manifest import workspace_registry


class Value101IdentityTests(unittest.TestCase):
    def test_value_101_descriptor_declares_the_teaching_identity_and_pack_family(self) -> None:
        self.assertIsNotNone(
            importlib.util.find_spec("gridform_core.value_101"),
            "VALUE 101 must have a canonical teaching-contract module",
        )
        value_101 = importlib.import_module("gridform_core.value_101")

        descriptor = value_101.value_101_descriptor(
            installed_pack_ids={"value-101-baseline-v1"}
        )

        self.assertEqual(descriptor["id"], "value-101")
        self.assertEqual(descriptor["study"]["id"], "value-101-baseline")
        self.assertEqual(
            descriptor["study"]["data_pack_id"], "value-101-baseline-v1"
        )
        self.assertEqual(descriptor["scientific_boundary"]["country"], "SYNTHETIC")
        self.assertEqual(descriptor["scientific_boundary"]["timezone"], "UTC")
        self.assertEqual(descriptor["scientific_boundary"]["periods_per_year"], 48)
        self.assertFalse(
            descriptor["scientific_boundary"]["annual_economics_eligible"]
        )
        availability = {
            row["pack_id"]: row["installed"]
            for row in descriptor["availability"]["packs"]
        }
        self.assertEqual(
            availability,
            {
                "value-101-baseline-v1": True,
                "value-101-windy-v1": False,
                "value-101-high-demand-v1": False,
            },
        )

    def test_public_registry_hides_ac_while_internal_registry_retains_it(self) -> None:
        try:
            public = workspace_registry(include_internal_experimental=False)
            internal = workspace_registry(include_internal_experimental=True)
        except TypeError as exc:
            self.fail(f"workspace registry lacks the explicit internal boundary: {exc}")

        self.assertNotIn("value-reference-ac-feasibility", public.manifests())
        self.assertNotIn("value-ac-data-extension", public.extension_manifests())
        self.assertIn("value-reference-ac-feasibility", internal.manifests())
        self.assertIn("value-ac-data-extension", internal.extension_manifests())

    def test_loopback_api_serves_only_the_value_101_tutorial_route(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-api-") as temporary:
            root = Path(temporary)
            patches = (
                patch.object(server, "PACKS_ROOT", root / "data-packs"),
                patch.object(server, "PROJECTS_ROOT", root / "projects"),
                patch.object(server, "RUNS_ROOT", root / "runs"),
            )
            for item in patches:
                item.start()
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                status, payload = self._get_json(origin + "/api/tutorials/value-101")
                self.assertEqual(status, 200)
                self.assertEqual(payload["id"], "value-101")

                old_status, _ = self._get_json(origin + "/api/tutorials/castle-101")
                self.assertEqual(old_status, 404)

                workspace_status, workspace = self._get_json(origin + "/api/workspace")
                self.assertEqual(workspace_status, 200)
                visible = json.dumps(workspace, sort_keys=True)
                self.assertNotIn("value-reference-ac-feasibility", visible)
                self.assertNotIn("value-ac-data-extension", visible)
                self.assertNotIn("domain.network.ac", visible)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
                for item in reversed(patches):
                    item.stop()

    @staticmethod
    def _get_json(url: str) -> tuple[int, dict[str, object]]:
        try:
            response = urllib.request.urlopen(url, timeout=10)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, json.loads(body) if body else {}
        with response:
            return response.status, json.loads(response.read())


if __name__ == "__main__":
    unittest.main()
