from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core.value_101 import value_101_study
from gridform_core.value_101_lifecycle import (
    clone_value_101_data_variant,
    clone_value_101_storage_variant,
    is_value_101_record,
    value_101_completion_report,
    value_101_origin,
)
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.v2.projects import parse_project
from tests.local_api_harness import start_local_api


ROOT = Path(__file__).resolve().parents[1]


def teaching_study() -> dict[str, object]:
    study = value_101_study()
    study["extensions"] = {
        "value_101": value_101_origin(
            variant_kind="baseline",
            parent_project_id=None,
            changed_dimensions=(),
        )
    }
    return study


class Value101LifecycleTests(unittest.TestCase):
    def test_v1_parser_preserves_explicit_teaching_origin(self) -> None:
        study = teaching_study()
        parsed = parse_project(study, workspace_registry()).to_dict()
        self.assertEqual(
            parsed["extensions"]["value_101"]["origin"],
            "guided-course",
        )
        self.assertTrue(is_value_101_record(parsed))

    def test_controlled_clones_change_exactly_one_scientific_dimension(self) -> None:
        base = teaching_study()
        data_clone, data_audit = clone_value_101_data_variant(
            base,
            target_pack_id="value-101-windy-v1",
            new_id="value-101-windy-study",
            new_name="VALUE 101 windy Study",
        )
        self.assertEqual(data_clone["data_pack_id"], "value-101-windy-v1")
        self.assertEqual(data_clone["modules"], base["modules"])
        self.assertEqual(data_audit["changed_scientific_paths"], ["data_pack_id"])
        self.assertTrue(data_audit["only_intended_dimension_changed"])
        self.assertEqual(
            data_clone["extensions"]["value_101"]["changed_dimensions"],
            ["data_pack_id"],
        )

        storage_clone, storage_audit = clone_value_101_storage_variant(
            base,
            storage_module_id="value-legacy-storage-tariff",
            new_id="value-101-legacy-study",
            new_name="VALUE 101 legacy storage Study",
        )
        self.assertEqual(
            storage_clone["modules"]["storage_cost"],
            "value-legacy-storage-tariff",
        )
        self.assertEqual(storage_clone["data_pack_id"], base["data_pack_id"])
        self.assertEqual(
            storage_audit["changed_scientific_paths"],
            ["modules.storage_cost"],
        )
        self.assertTrue(storage_audit["only_intended_dimension_changed"])

    def test_completion_uses_origin_metadata_not_a_name_substring(self) -> None:
        teaching = teaching_study()
        ordinary = {
            **teaching,
            "id": "ordinary-research",
            "name": "ordinary value-101 sensitivity research",
            "extensions": {},
        }
        runs = [
            {
                "id": "teaching-run",
                "project_id": teaching["id"],
                "status": "completed",
                "extensions": teaching["extensions"],
            },
            {
                "id": "ordinary-run",
                "project_id": ordinary["id"],
                "status": "completed",
                "extensions": {},
            },
        ]
        report = value_101_completion_report([teaching, ordinary], runs)
        self.assertEqual([row["id"] for row in report["studies"]], [teaching["id"]])
        self.assertEqual([row["id"] for row in report["runs"]], ["teaching-run"])
        self.assertFalse(is_value_101_record(ordinary))

    def test_scoped_http_lifecycle_creates_clones_reports_and_resets_only_teaching(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-lifecycle-") as temporary:
            root = Path(temporary)
            projects = root / "projects"
            runs = root / "runs"
            trash = root / "trash"
            ordinary_dir = projects / "ordinary-value-101-research"
            ordinary_dir.mkdir(parents=True)
            ordinary = {
                **teaching_study(),
                "id": ordinary_dir.name,
                "name": "value-101 ordinary research",
                "extensions": {},
            }
            (ordinary_dir / "project.json").write_text(
                json.dumps(ordinary), encoding="utf-8"
            )
            patches = (
                patch.object(server, "PACKS_ROOT", ROOT / "data-packs"),
                patch.object(server, "PROJECTS_ROOT", projects),
                patch.object(server, "RUNS_ROOT", runs),
                patch.object(server, "TRASH_ROOT", trash),
            )
            for item in patches:
                item.start()
            api = start_local_api(data_home=Path(temporary), patch_state_roots=False)
            httpd, origin, _session = api.start()
            try:
                status, created = self._request_json(
                    origin + "/api/tutorials/value-101/studies", "POST", {}
                )
                self.assertEqual(status, 201)
                self.assertEqual(created["project"]["id"], "value-101-baseline")
                self.assertEqual(list(runs.glob("*/status.json")), [])

                status, data_clone = self._request_json(
                    origin + "/api/tutorials/value-101/studies/value-101-baseline/clone-data",
                    "POST",
                    {
                        "id": "value-101-windy-study",
                        "name": "VALUE 101 windy Study",
                        "target_pack_id": "value-101-windy-v1",
                    },
                )
                self.assertEqual(status, 201)
                self.assertTrue(data_clone["identity_diff"]["only_intended_dimension_changed"])

                status, storage_clone = self._request_json(
                    origin + "/api/tutorials/value-101/studies/value-101-baseline/clone-storage",
                    "POST",
                    {
                        "id": "value-101-legacy-study",
                        "name": "VALUE 101 legacy storage Study",
                        "storage_cost_module_id": "value-legacy-storage-tariff",
                    },
                )
                self.assertEqual(status, 201)
                self.assertTrue(storage_clone["identity_diff"]["only_intended_dimension_changed"])

                status, report = self._request_json(
                    origin + "/api/tutorials/value-101/completion-report", "GET"
                )
                self.assertEqual(status, 200)
                self.assertEqual(len(report["studies"]), 3)
                self.assertNotIn(ordinary["id"], {row["id"] for row in report["studies"]})

                status, refused = self._request_json(
                    origin + "/api/tutorials/value-101/reset", "POST", {"confirm": False}
                )
                self.assertEqual(status, 400)
                self.assertEqual(refused["error_code"], "GF_VALUE_101_RESET_CONFIRMATION_REQUIRED")

                status, reset = self._request_json(
                    origin + "/api/tutorials/value-101/reset", "POST", {"confirm": True}
                )
                self.assertEqual(status, 200)
                self.assertEqual(len(reset["deleted_study_ids"]), 3)
                self.assertTrue((ordinary_dir / "project.json").is_file())
                self.assertTrue((ROOT / "data-packs" / "value-101-baseline-v1").is_dir())
            finally:
                api.stop()
                for item in reversed(patches):
                    item.stop()

    @staticmethod
    def _request_json(
        url: str,
        method: str,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            method=method,
            data=data,
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
