from __future__ import annotations

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


ROOT = Path(__file__).resolve().parents[1]


class Value101ExperimentTests(unittest.TestCase):
    def test_clone_api_previews_exact_data_and_storage_changes_before_save(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-prompt113-") as temporary:
            root = Path(temporary)
            patches = (
                patch.object(server, "PACKS_ROOT", ROOT / "data-packs"),
                patch.object(server, "PROJECTS_ROOT", root / "projects"),
                patch.object(server, "RUNS_ROOT", root / "runs"),
                patch.object(server, "TRASH_ROOT", root / "trash"),
            )
            for item in patches:
                item.start()
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                status, created = self._request(
                    origin + "/api/tutorials/value-101/studies", {}
                )
                self.assertEqual(status, 201)
                self.assertFalse(created["run_started"])

                status, windy = self._request(
                    origin + "/api/tutorials/value-101/studies/value-101-baseline/clone-data",
                    {"target_pack_id": "value-101-windy-v1", "dry_run": True},
                )
                self.assertEqual(status, 200)
                self.assertEqual(windy["changed_dimensions"], ["data_pack_id"])
                self.assertEqual(
                    windy["changed_roles"],
                    ["profiles.vre_offshore", "profiles.vre_onshore", "weather.wind"],
                )
                self.assertIn("1.35", windy["transformation"])
                self.assertEqual(
                    windy["preserved_dimensions"],
                    ["years", "modules", "parameters", "runtime_controls"],
                )
                self.assertTrue(windy["can_save"])
                self.assertIsNone(windy["reason"])
                self.assertEqual(len(list((root / "projects").glob("*/project.json"))), 1)

                status, high_demand = self._request(
                    origin + "/api/tutorials/value-101/studies/value-101-baseline/clone-data",
                    {"target_pack_id": "value-101-high-demand-v1", "dry_run": True},
                )
                self.assertEqual(status, 200)
                self.assertEqual(high_demand["changed_roles"], ["demand.forecast", "demand.real"])
                self.assertIn("1.20", high_demand["transformation"])

                status, storage = self._request(
                    origin + "/api/tutorials/value-101/studies/value-101-baseline/clone-storage",
                    {
                        "storage_cost_module_id": "value-legacy-storage-tariff",
                        "dry_run": True,
                    },
                )
                self.assertEqual(status, 200)
                self.assertEqual(storage["changed_dimensions"], ["modules.storage_cost"])
                self.assertEqual(storage["changed_roles"], [])
                self.assertEqual(storage["from_value"], "dynamic-annual-storage-cost")
                self.assertEqual(storage["to_value"], "value-legacy-storage-tariff")
                self.assertTrue(storage["can_save"])
                self.assertEqual(len(list((root / "projects").glob("*/project.json"))), 1)

                status, refused = self._request(
                    origin + "/api/tutorials/value-101/studies/value-101-baseline/clone-storage",
                    {"storage_cost_module_id": "user-formula-storage-cost", "dry_run": True},
                )
                self.assertEqual(status, 400)
                self.assertEqual(refused["error_code"], "GF_VALUE_101_STORAGE_OPTION_NOT_GUIDED")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
                for item in reversed(patches):
                    item.stop()

    def test_frontend_requires_preview_then_explicit_study_and_run_actions(self) -> None:
        component_path = ROOT / "app" / "features" / "learn" / "Value101Experiment.tsx"
        self.assertTrue(component_path.is_file())
        component = component_path.read_text("utf-8")
        course = (ROOT / "app" / "features" / "learn" / "Value101Learn.tsx").read_text("utf-8")
        contract = (ROOT / "app" / "features" / "learn" / "value101.ts").read_text("utf-8")
        for label in (
            "Windy",
            "High demand",
            "Dynamic annual-average recovery",
            "Legacy fixed tariff",
            "Preview change",
            "Create Study",
            "Run Study",
        ):
            self.assertIn(label, component)
        self.assertIn("dry_run: true", component)
        self.assertIn("changed_roles", component)
        self.assertIn("preserved_dimensions", component)
        self.assertIn("Value101Experiment", course)
        self.assertIn("Value101ExperimentPreview", contract)
        self.assertNotIn("onChange={onRun", component)

    @staticmethod
    def _request(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, json.loads(body) if body else {}
        with response:
            return response.status, json.loads(response.read())


if __name__ == "__main__":
    unittest.main()
