from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from tests.local_api_harness import start_local_api


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class StudyLifecycleApiTests(unittest.TestCase):
    def request(
        self, origin: str, route: str, method: str = "GET", payload: dict[str, object] | None = None
    ) -> tuple[int, dict[str, object]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            origin + route,
            method=method,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")
        with response:
            return response.status, json.loads(response.read())

    def test_http_trash_requires_confirmation_and_restore_returns_exact_study(self) -> None:
        """Catches routes that bypass confirmation or fail to expose recovery."""

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            projects, runs, trash = state / "projects", state / "runs", state / "trash"
            write_json(
                projects / "study-a" / "project.json",
                {"id": "study-a", "name": "Study A", "revision_sha256": "a" * 64},
            )
            write_json(
                runs / "run-a" / "status.json",
                {
                    "id": "run-a",
                    "project_id": "study-a",
                    "project_name": "Study A",
                    "status": "completed",
                    "execution_engine": "value-annual-orchestrator/v2",
                    "updated_at": "2026-08-25T10:00:00+01:00",
                },
            )
            patches = (
                patch.object(server, "PROJECTS_ROOT", projects),
                patch.object(server, "RUNS_ROOT", runs),
                patch.object(server, "TRASH_ROOT", trash),
            )
            for item in patches:
                item.start()
            api = start_local_api(data_home=Path(temporary), patch_state_roots=False)
            httpd, origin, _session = api.start()
            try:
                status, projects_listing = self.request(origin, "/api/projects")
                self.assertEqual(status, 200)
                self.assertEqual(projects_listing["projects"][0]["linked_run_count"], 1)

                status, blocked = self.request(
                    origin,
                    "/api/projects/study-a/trash",
                    "POST",
                    {"confirm": True, "confirm_name": "study a"},
                )
                self.assertEqual(status, 409)
                self.assertEqual(blocked["error_code"], "GF_STUDY_TRASH_CONFIRMATION_REQUIRED")

                status, moved = self.request(
                    origin,
                    "/api/projects/study-a/trash",
                    "POST",
                    {"confirm": True, "confirm_name": "Study A", "reason": "superseded"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(moved["trash_entry"]["linked_run_count"], 1)

                status, listing = self.request(origin, "/api/study-trash")
                self.assertEqual(status, 200)
                self.assertEqual(listing["studies"][0]["study_id"], "study-a")
                status, run_listing = self.request(origin, "/api/runs")
                self.assertEqual(status, 200)
                self.assertEqual(run_listing["runs"][0]["source_study_status"], "trash")
                status, run_detail = self.request(origin, "/api/runs/run-a")
                self.assertEqual(status, 200)
                self.assertEqual(run_detail["source_study_status"], "trash")
                status, read_only = self.request(
                    origin, "/api/runs/run-a/resume", "POST", {}
                )
                self.assertEqual(status, 409)
                self.assertEqual(
                    read_only["error_code"], "GF_RUN_SOURCE_STUDY_IN_TRASH"
                )

                trash_id = str(moved["trash_entry"]["trash_id"])
                status, restored = self.request(
                    origin, f"/api/study-trash/{trash_id}/restore", "POST", {}
                )
                self.assertEqual(status, 200)
                self.assertEqual(restored["study"]["id"], "study-a")
                self.assertTrue((projects / "study-a" / "project.json").is_file())
            finally:
                api.stop()
                for item in reversed(patches):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
