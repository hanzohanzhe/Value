import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from backend import server


MODULES = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
}


class ProjectValidationTests(unittest.TestCase):
    def test_run_ids_are_bounded_for_windows_snapshot_paths(self):
        run_id = server.bounded_run_id(
            "castle-101-baseline-value-legacy-storage-tariff-with-a-very-long-study-name",
            timestamp="20260820-123456",
            nonce="abcdef12",
        )
        self.assertLessEqual(len(run_id), 40)
        self.assertEqual(run_id, "castle-101-base-20260820-123456-abcdef12")

    def test_bounded_run_ids_keep_the_unique_suffix(self):
        first = server.bounded_run_id(
            "a" * 100, timestamp="20260820-123456", nonce="00000001"
        )
        second = server.bounded_run_id(
            "a" * 100, timestamp="20260820-123456", nonce="00000002"
        )
        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith("-00000001"))

    def _complete_manifest(self, packs: Path) -> Path:
        root = packs / "complete"
        bindings = {}
        for index, slot in enumerate(server.DATASET_SLOTS):
            if not slot.get("required"):
                continue
            file_format = slot["formats"][0]
            path = root / "files" / f"{index}.{file_format}"
            path.parent.mkdir(parents=True, exist_ok=True)
            if slot["role"] == "config.model_parameters":
                path.write_text(json.dumps({
                    "simulation_parameters": {"bidding_factor": 1.0},
                    "repd_filtering": {
                        "apply_zombie_filter": True,
                        "zombie_status_stale_year": 2015,
                        "minimum_project_size_mw": 1.0,
                        "max_completion_year": 2040,
                    },
                    "storage_cap_fraction": 0.2,
                }), encoding="utf-8")
            else:
                path.write_bytes(b"test")
            bindings[slot["role"]] = {
                "uri": str(path.relative_to(root)).replace("\\", "/"),
                "format": file_format,
                "sha256": "0" * 64,
            }
        manifest = root / "manifest.json"
        server.atomic_json(
            manifest, {"id": "complete", "name": "Complete", "bindings": bindings}
        )
        return manifest

    def test_missing_required_bindings_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            packs = Path(folder)
            manifest = packs / "empty" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            server.atomic_json(manifest, {"id": "empty", "bindings": {}})
            with patch.object(server, "PACKS_ROOT", packs):
                report = server.validate_project({
                    "data_pack_id": "empty", "start_year": 2025,
                    "end_year": 2030, "modules": MODULES,
                })
        self.assertFalse(report["valid"])
        self.assertTrue(any("Forecast demand" in error for error in report["errors"]))

    def test_complete_pack_passes_data_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            packs = Path(folder)
            self._complete_manifest(packs)
            with patch.object(server, "PACKS_ROOT", packs):
                report = server.validate_project({
                    "data_pack_id": "complete", "start_year": 2025,
                    "end_year": 2030, "modules": MODULES,
                })
        self.assertTrue(report["valid"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])

    def test_run_history_only_exposes_v2_application_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            runs = Path(folder)
            legacy = runs / "legacy" / "status.json"
            exact = runs / "exact" / "status.json"
            legacy.parent.mkdir(parents=True)
            exact.parent.mkdir(parents=True)
            legacy.write_text(json.dumps({
                "id": "legacy", "project_id": "p", "status": "completed",
                "updated_at": "2026-07-22T00:00:00+01:00",
            }), encoding="utf-8")
            exact.write_text(json.dumps({
                "id": "exact", "project_id": "p", "status": "completed",
                "execution_engine": "scheme-c-authoritative-exact/v1",
                "updated_at": "2026-07-23T00:00:00+01:00",
            }), encoding="utf-8")
            production = runs / "production" / "status.json"
            production.parent.mkdir(parents=True)
            production.write_text(json.dumps({
                "id": "production", "project_id": "p", "status": "completed",
                "execution_engine": "gridform-annual-orchestrator/v2",
                "updated_at": "2026-07-24T00:00:00+01:00",
            }), encoding="utf-8")
            with patch.object(server, "RUNS_ROOT", runs):
                visible = server.list_runs()
        self.assertEqual([run["id"] for run in visible], ["production"])

    def test_project_rejects_a_module_in_the_wrong_slot(self):
        with tempfile.TemporaryDirectory() as folder:
            packs = Path(folder)
            self._complete_manifest(packs)
            invalid = dict(MODULES)
            invalid["psm"] = "agent-investment"
            with patch.object(server, "PACKS_ROOT", packs):
                report = server.validate_project({
                    "data_pack_id": "complete",
                    "start_year": 2025,
                    "end_year": 2026,
                    "modules": invalid,
                })
        self.assertFalse(report["valid"])
        self.assertTrue(any("cannot fill psm" in error for error in report["errors"]))

    def test_run_relative_artifacts_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            runs = Path(folder) / "runs"
            run_root = runs / "safe-run"
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(
                json.dumps({"id": "safe-run", "status": "completed"}), encoding="utf-8"
            )
            artifact = run_root / "model-output" / "result.json"
            artifact.parent.mkdir()
            artifact.write_text("{}", encoding="utf-8")
            outside = Path(folder) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            with patch.object(server, "RUNS_ROOT", runs):
                self.assertEqual(
                    server.safe_run_artifact("safe-run", "model-output/result.json"),
                    artifact.resolve(),
                )
                self.assertIsNone(server.safe_run_artifact("safe-run", "../secret.txt"))
                self.assertIsNone(
                    server.safe_run_artifact("safe-run", "%2e%2e/secret.txt")
                )
                self.assertIsNone(server.safe_run_artifact("../safe-run", "status.json"))
                listed = server.list_run_artifacts("safe-run")
            self.assertEqual({row["id"] for row in listed}, {
                "model-output/result.json", "status.json"
            })

    def test_large_ledgers_do_not_enter_run_status_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            runs = Path(folder)
            run_root = runs / "bounded"
            market = run_root / "model-output" / "market" / "market.sqlite"
            market.parent.mkdir(parents=True)
            market.write_bytes(b"x" * 2_000_000)
            (run_root / "status.json").write_text(json.dumps({
                "id": "bounded", "project_id": "p", "project_name": "P",
                "status": "completed", "execution_engine": "gridform-annual-orchestrator/v2",
                "updated_at": "2026-08-04T00:00:00+01:00", "results": [],
            }), encoding="utf-8")
            with patch.object(server, "RUNS_ROOT", runs):
                payload = json.dumps(server.list_runs()).encode("utf-8")
            self.assertLess(len(payload), 2_000)

    def test_external_module_disable_dependency_scan_is_bounded_to_saved_studies_and_active_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            projects, runs = root / "projects", root / "runs"
            project = projects / "uses-module" / "project.json"
            project.parent.mkdir(parents=True)
            project.write_text(json.dumps({
                "id": "uses-module",
                "modules": {"storage_cost": "my-storage-module"},
            }), encoding="utf-8")
            active = runs / "active" / "status.json"
            complete = runs / "complete" / "status.json"
            active.parent.mkdir(parents=True)
            complete.parent.mkdir(parents=True)
            active.write_text(json.dumps({
                "id": "active", "status": "running",
                "modules": {"storage_cost": "my-storage-module"},
            }), encoding="utf-8")
            complete.write_text(json.dumps({
                "id": "complete", "status": "completed",
                "modules": {"storage_cost": "my-storage-module"},
            }), encoding="utf-8")
            handler = object.__new__(server.Handler)
            with patch.object(server, "PROJECTS_ROOT", projects), patch.object(server, "RUNS_ROOT", runs):
                dependents = handler._module_dependents("my-storage-module")
        self.assertEqual(dependents["projects"], ["uses-module"])
        self.assertEqual(dependents["active_runs"], ["active"])


if __name__ == "__main__":
    unittest.main()
