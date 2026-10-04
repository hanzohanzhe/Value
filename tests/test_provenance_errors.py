import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import server
from backend.model_runner import record_run_failure
from gridform_core.parameters import ParameterValidationError
from gridform_core.provenance import _git_identity


class ProvenanceErrorTests(unittest.TestCase):
    def test_run_failure_status_survives_unsealed_sqlite_sidecars(self):
        with tempfile.TemporaryDirectory() as folder:
            status_path = Path(folder) / "run" / "status.json"
            sidecar = status_path.parent / "model-output" / "market" / "market.sqlite-wal"
            sidecar.parent.mkdir(parents=True)
            sidecar.write_bytes(b"live")

            status = record_run_failure(
                status_path,
                run_id="failed-run",
                project_id="project",
                mode="two_year_smoke",
                error=RuntimeError("model failed"),
            )

            persisted = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "failed")
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(persisted["execution_status"], "failed")
            self.assertNotIn("provenance_artifact", persisted)
            self.assertIn(
                "GF_FAILED_PROVENANCE_WARNING",
                {row["code"] for row in persisted["warnings"]},
            )

    def test_run_failure_status_survives_any_provenance_error(self):
        with tempfile.TemporaryDirectory() as folder:
            status_path = Path(folder) / "run" / "status.json"
            status_path.parent.mkdir()
            with patch(
                "backend.model_runner.write_failed_run_provenance",
                side_effect=TypeError("malformed optional provenance input"),
            ):
                status = record_run_failure(
                    status_path,
                    run_id="failed-run",
                    project_id="project",
                    mode="two_year_smoke",
                    error=RuntimeError("model failed"),
                )
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["execution_status"], "failed")

    def test_run_failure_replaces_structurally_invalid_status(self):
        with tempfile.TemporaryDirectory() as folder:
            status_path = Path(folder) / "run" / "status.json"
            status_path.parent.mkdir()
            status_path.write_text('["not", "an", "object"]', encoding="utf-8")
            status = record_run_failure(
                status_path,
                run_id="failed-run",
                project_id="project",
                mode="two_year_smoke",
                error=RuntimeError("model failed"),
            )
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["execution_status"], "failed")

    def test_git_unavailable_is_structured_without_a_path(self):
        with tempfile.TemporaryDirectory() as folder:
            identity = _git_identity(Path(folder))
        self.assertFalse(identity["available"])
        self.assertIn(identity["reason_code"], {
            "git_metadata_unavailable", "git_command_unavailable"
        })
        self.assertNotIn("path", identity)

    def test_public_failure_code_and_local_diagnostic_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            status_path = Path(folder) / "run" / "status.json"
            status_path.parent.mkdir()
            try:
                raise ParameterValidationError("private scientific detail")
            except ParameterValidationError as error:
                status = record_run_failure(
                    status_path,
                    run_id="failed-run",
                    project_id="project",
                    mode="smoke",
                    error=error,
                )
            diagnostic = json.loads(
                (status_path.parent / "diagnostics" / "error.json").read_text("utf-8")
            )
            provenance_text = (status_path.parent / "provenance.json").read_text("utf-8")
            with patch.object(server, "RUNS_ROOT", status_path.parent.parent):
                response = server.run_provenance("run")
            root_text = folder
        self.assertEqual(status["error_code"], "GF_PARAMETER_001")
        self.assertEqual(status["error_category"], "parameter")
        self.assertNotIn("private scientific detail", json.dumps(status))
        self.assertNotIn("traceback", status)
        self.assertEqual(diagnostic["exception_message"], "private scientific detail")
        self.assertIn("traceback", diagnostic)
        self.assertNotIn(root_text, provenance_text)
        self.assertNotIn(root_text, json.dumps(response))

    def test_declared_core_files_have_no_silent_broad_exception(self):
        root = Path(__file__).resolve().parents[1]
        declared = [
            "gridform_core/application.py",
            "gridform_core/planning_ledger.py",
            "gridform_core/market_ledger.py",
            "gridform_core/v2/orchestrator.py",
            "gridform_core/provenance.py",
            "gridform_core/bundle_validator.py",
            "backend/model_runner.py",
            "backend/server.py",
        ]
        for relative in declared:
            with self.subTest(file=relative):
                self.assertIsNone(re.search(
                    r"except\s+Exception(?:\s+as\s+\w+)?\s*:\s*pass\b",
                    (root / relative).read_text("utf-8"),
                ))


if __name__ == "__main__":
    unittest.main()
