"""R6-1 (DECISIONS A29): queued Runs when modules or extensions change.

EM-中1: a lifecycle change while Runs are queued said they "would start with
the changed code"; they failed with the generic GF_CONTRACT_001.  Now the
confirmation says what happens, Runs whose recorded code changed are stopped
with GF_RUN_EXECUTION_IDENTITY_CHANGED (by the server, by the preparation
re-check, or by the worker's own verification), and the Runs page offers a
resubmission.

AF-低1: an extension hook output VALUE refuses fails the Run with
GF_EXTENSION_OUTPUT_REJECTED, and the first line of the diagnostic is shown
as ``error_detail``.
"""

from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import run_execution
from backend.frozen_run_recovery import json_hash
from backend.lifecycle.run_status import create_status, read_status
from gridform_core.errors import (
    ExecutionIdentityChangedError,
    ExtensionOutputError,
    failure_detail,
    public_failure,
)
from gridform_core.execution_archive import current_source_sha256
from tests.module_lifecycle_fixtures import write_external_module
from tests.test_r4_module_extension_defects import LifecycleApiCase
from tests.test_r5_add_feature_defects import ARTIFACT, EXTENSION_ID, SourceBundleCase

ROOT = Path(__file__).resolve().parents[1]
CODE = "GF_RUN_EXECUTION_IDENTITY_CHANGED"


class TaxonomyTests(unittest.TestCase):
    def test_execution_identity_change_has_its_own_code(self) -> None:
        failure = public_failure(ExecutionIdentityChangedError("changed"))
        self.assertEqual((failure.code, failure.category), (CODE, "execution_identity"))
        self.assertIn("Resubmit", failure.message)
        # Still a ValueError, so every existing handler (resume: 409
        # GF_EXECUTION_IDENTITY_CHANGED) keeps catching it.
        self.assertIsInstance(ExecutionIdentityChangedError("x"), ValueError)

    def test_extension_output_is_a_specific_contract_failure(self) -> None:
        failure = public_failure(ExtensionOutputError("Extension a:after_cem returned artifact"))
        self.assertEqual((failure.code, failure.category), ("GF_EXTENSION_OUTPUT_REJECTED", "contract"))
        self.assertNotEqual(failure.code, "GF_CONTRACT_001")

    def test_failure_detail_is_the_first_non_empty_line(self) -> None:
        self.assertEqual(failure_detail("\n  first line \nsecond"), "first line")
        self.assertIsNone(failure_detail(""))
        self.assertEqual(len(failure_detail("x" * 1000)), 400)


class WorkerVerificationTests(unittest.TestCase):
    """The worker's own check (backend/run_execution.py) raises the coded error."""

    def test_changed_identity_raises_the_coded_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-r61-") as folder:
            run_root = Path(folder)
            record = {"identity_sha256": "a" * 64, "source_sha256": "b" * 64}
            (run_root / "execution-bundle.json").write_text(json.dumps(record), "utf-8")
            project = {"extensions": {"execution_bundle": {
                "identity_sha256": "a" * 64, "record_sha256": json_hash(record)}}}
            with patch.object(run_execution, "verify_execution_bundle", lambda *a, **k: None), \
                    patch.object(run_execution, "current_execution", lambda **k: {"identity_sha256": "c" * 64}):
                with self.assertRaises(ExecutionIdentityChangedError) as caught:
                    run_execution.verify_run_execution(run_root, project, source_root=ROOT,
                                                       data_home=run_root, require_record=True)
        self.assertIn("Resubmit the Run", str(caught.exception))
        self.assertEqual(public_failure(caught.exception).code, CODE)


class FailureRecordTests(unittest.TestCase):
    """record_run_failure stores the diagnostic's first line for coded failures."""

    def record(self, error: BaseException) -> dict:
        from backend.model_runner import record_run_failure

        folder = tempfile.TemporaryDirectory(prefix="value-r61-fail-")
        self.addCleanup(folder.cleanup)
        run_dir = Path(folder.name) / "run-1"
        run_dir.mkdir()
        create_status(run_dir, {"id": "run-1", "status": "queued"})
        record_run_failure(run_dir / "status.json", run_id="run-1", project_id="p", mode="smoke", error=error)
        status = read_status(run_dir)
        diagnostic = json.loads((run_dir / "diagnostics" / "error.json").read_text("utf-8"))
        self.assertEqual(diagnostic["error_code"], status["error_code"])
        return status

    def test_identity_change(self) -> None:
        status = self.record(ExecutionIdentityChangedError("Execution source or runtime changed after enqueue\nmore"))
        self.assertEqual(status["error_code"], CODE)
        self.assertEqual(status["error_detail"], "Execution source or runtime changed after enqueue")

    def test_extension_output(self) -> None:
        status = self.record(ExtensionOutputError("Extension e:after_cem returned artifact 'x'"))
        self.assertEqual(status["error_code"], "GF_EXTENSION_OUTPUT_REJECTED")
        self.assertIn("e:after_cem", status["error_detail"])

    def test_runtime_failure_has_no_detail(self) -> None:
        status = self.record(RuntimeError("internal"))
        self.assertNotIn("error_detail", status)


class HookOutputTests(SourceBundleCase):
    """AF-低1: an artifact from an unrecorded hook raises the specific error."""

    def test_artifact_from_after_cem_is_a_coded_refusal(self) -> None:
        self.install()
        runtime = self.runtime()
        with self.assertRaises(ExtensionOutputError) as caught:
            runtime.invoke("after_cem", {"year": 2025, "emit_artifact": True})
        failure = public_failure(caught.exception)
        self.assertEqual(failure.code, "GF_EXTENSION_OUTPUT_REJECTED")
        detail = failure_detail(caught.exception)
        self.assertIn(f"{EXTENSION_ID}:after_cem", detail)
        self.assertIn(ARTIFACT, detail)


class PreparationRecheckTests(unittest.TestCase):
    """A Run being prepared re-checks its recorded source after a lifecycle change."""

    def test_recheck_only_after_a_lifecycle_change(self) -> None:
        from backend import server

        context = types.SimpleNamespace(execution_source_sha256="0" * 64,
                                        execution_generation=server.execution_source_generation())
        calls: list[dict] = []

        def changed(record, **_kwargs):
            calls.append(record)
            return True

        with patch.object(server, "source_identity_changed", changed):
            self.assertFalse(server._preparation_code_changed(context))
            self.assertEqual(calls, [])  # no lifecycle change: no hashing
            server._bump_execution_source_generation()
            self.assertTrue(server._preparation_code_changed(context))
        self.assertEqual(calls, [{"source_sha256": "0" * 64}])

    def test_unchanged_source_adopts_the_new_generation(self) -> None:
        from backend import server

        context = types.SimpleNamespace(execution_source_sha256="0" * 64, execution_generation=-1)
        with patch.object(server, "source_identity_changed", lambda record, **k: False):
            self.assertFalse(server._preparation_code_changed(context))
        self.assertEqual(context.execution_generation, server.execution_source_generation())


class QueuedRunsApiTests(LifecycleApiCase):
    PACKAGES = ("r61_api_ok",)

    def queued(self, run_id: str, source_sha256: str | None) -> Path:
        run = self.home / "runs" / run_id
        run.mkdir(parents=True)
        create_status(run, {"id": run_id, "project_id": "p", "mode": "smoke", "status": "queued",
                            "execution_engine": "value-annual-orchestrator/v2"})
        if source_sha256 is not None:
            (run / "execution-bundle.json").write_text(json.dumps({
                "identity_sha256": "1" * 64, "source_sha256": source_sha256}), "utf-8")
        return run

    def test_confirmation_says_what_happens_and_changed_runs_are_stopped(self) -> None:
        write_external_module(self.modules, "r61-api-ok", "r61_api_ok", enabled=False)
        before = current_source_sha256(source_root=ROOT, data_home=self.home)
        stale = self.queued("queued-stale", before)
        legacy = self.queued("queued-legacy", None)
        with patch("gridform_core.module_quarantine.verify_after_write", lambda *a, **k: None):
            status, body = self.request("POST", "/api/modules/r61-api-ok/enable", {})
            self.assertEqual(status, 409, body)
            self.assertEqual(body["error_code"], "GF_MODULE_LIFECYCLE_RUNS_PENDING")
            self.assertIn("will not start", body["error"])
            self.assertIn(CODE, body["error"])
            self.assertIn("Resubmit with current code", body["error"])
            self.assertNotIn("would start with the changed code", body["error"])
            status, body = self.request("POST", "/api/modules/r61-api-ok/enable", {"confirm_pending_runs": True})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["stopped_unstarted_runs"], ["queued-stale"])
        stopped = read_status(stale)
        self.assertEqual((stopped["status"], stopped["error_code"]), ("failed", CODE))
        self.assertEqual(stopped["lifecycle_history"][-1]["reason_code"], CODE)
        self.assertIn("Resubmit", stopped["error"])
        self.assertTrue(stopped["error_detail"].startswith("Execution source changed after enqueue"))
        diagnostic = json.loads((stale / "diagnostics" / "error.json").read_text("utf-8"))
        self.assertEqual(diagnostic["error_code"], CODE)
        # Without a recorded identity nothing is compared: the worker decides.
        self.assertEqual(read_status(legacy)["status"], "queued")
        status, runs = self.request("GET", "/api/runs")
        self.assertEqual(status, 200)
        listed = {run["id"]: run for run in (runs if isinstance(runs, list) else runs.get("runs", []))}
        self.assertEqual(listed["queued-stale"]["error_code"], CODE)
        self.assertTrue(listed["queued-stale"]["error_detail"])

    def test_unchanged_source_is_not_stopped(self) -> None:
        current = current_source_sha256(source_root=ROOT, data_home=self.home)
        run = self.queued("queued-current", current)
        self.assertEqual(self.server.stop_unstarted_runs_with_changed_code(), [])
        self.assertEqual(read_status(run)["status"], "queued")

    def test_old_contract_failure_shows_the_diagnostic_line(self) -> None:
        run = self.home / "runs" / "old-failed"
        run.mkdir(parents=True)
        create_status(run, {"id": "old-failed", "project_id": "p", "mode": "smoke", "status": "failed",
                            "execution_engine": "value-annual-orchestrator/v2",
                            "error_code": "GF_CONTRACT_001", "error_category": "contract",
                            "error": "A selected module did not satisfy its declared contract."})
        (run / "diagnostics").mkdir()
        (run / "diagnostics" / "error.json").write_text(json.dumps({
            "exception_message": "Extension x:after_cem returned artifact 'y'\nsecond line"}), "utf-8")
        status, runs = self.request("GET", "/api/runs")
        listed = {item["id"]: item for item in (runs if isinstance(runs, list) else runs.get("runs", []))}
        self.assertEqual(listed["old-failed"]["error_detail"], "Extension x:after_cem returned artifact 'y'")


if __name__ == "__main__":
    unittest.main()
