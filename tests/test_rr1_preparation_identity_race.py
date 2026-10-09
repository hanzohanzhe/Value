"""RR-1 (5), EM-低3: a module change in the first seconds of a Run's preparation.

Disabling, removing or installing a module or extension while a Run records
its execution environment (or freezes its inputs) removed a manifest the
capture had already listed; the Run failed with the generic
GF_INPUT_SNAPSHOT_FAILED and a raw "[Errno 2] No such file ... modules/<id>.json"
and the Runs page offered no Resubmit.  Such a failure is now an execution
identity change (GF_RUN_EXECUTION_IDENTITY_CHANGED) when the lifecycle
generation changed since admission or the recorded source no longer matches;
every other snapshot failure keeps its code.  The race is injected: the
patched capture (or snapshot) bumps the generation as the lifecycle change
does and raises the FileNotFoundError the real scan raised.
"""

from __future__ import annotations

import errno
import json
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import server
from backend.lifecycle.run_status import create_status, read_status

CODE = "GF_RUN_EXECUTION_IDENTITY_CHANGED"


class PreparationRaceTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="value-rr1-race-")
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name) / "home"
        (self.home / "modules").mkdir(parents=True)
        self.run_dir = self.home / "runs" / "race-run"
        self.run_dir.mkdir(parents=True)
        create_status(self.run_dir, {
            "id": "race-run", "project_id": "p", "mode": "smoke", "status": "snapshotting",
            "execution_status": "queued", "execution_engine": "value-annual-orchestrator/v2",
            "current_stage": server.RUN_PREPARATION_STAGES[0][1],
            "preparation": server._preparation_record(time.time()),
        })
        for name, value in (("STATE_ROOT", self.home), ("RUNS_ROOT", self.home / "runs")):
            patcher = patch.object(server, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(server, "verify_recovered_inputs", lambda *a, **k: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def context(self, *, admission_generation: int | None) -> types.SimpleNamespace:
        manifest = types.SimpleNamespace(requires_capabilities=())
        registry = types.SimpleNamespace(manifest=lambda *a, **k: manifest)
        return types.SimpleNamespace(
            run_id="race-run", run_dir=self.run_dir, project={"name": "Race", "modules": {"psm": "psm-a"}},
            project_id="p", mode="smoke", policy=None, run_start=2025, run_end=2025, preflight={},
            pack_root=self.home / "pack", pack_selection=types.SimpleNamespace(network_pack_root=None),
            teaching_run_extensions={}, lineage=None, registry=registry,
            execution_source_sha256=None, execution_generation=None,
            admission_generation=admission_generation,
        )

    def missing(self, relative: str) -> FileNotFoundError:
        path = self.home / "modules" / relative
        return FileNotFoundError(errno.ENOENT, "No such file or directory", str(path))

    def status(self) -> dict:
        return read_status(self.run_dir)

    def test_module_disabled_during_capture_is_an_identity_change(self) -> None:
        context = self.context(admission_generation=server.execution_source_generation())

        def capture(**_kwargs):
            server._bump_execution_source_generation()  # the disable's catalogue refresh
            raise self.missing("hx-flat-offer-73.json")

        with patch.object(server, "current_execution", capture):
            server._prepare_run_stages(context)
        status = self.status()
        self.assertEqual((status["status"], status["error_code"]), ("failed", CODE))
        self.assertEqual(status["lifecycle_history"][-1]["reason_code"], CODE)
        self.assertIn("Resubmit", status["error"])
        self.assertTrue(status["error_detail"].startswith("Execution source changed while this Run was being prepared"))
        self.assertEqual(status["preparation"]["failed_stage"], "execution")
        diagnostic = json.loads((self.run_dir / "diagnostics" / "error.json").read_text("utf-8"))
        self.assertEqual(diagnostic["error_code"], CODE)
        self.assertIn("hx-flat-offer-73.json", diagnostic["exception_message"])

    def test_extension_removed_during_snapshot_with_changed_source(self) -> None:
        # No generation recorded (an older admission): the source hash decides.
        context = self.context(admission_generation=None)
        record = {"source_sha256": "a" * 64, "identity_sha256": "b" * 64}

        def snapshot(**_kwargs):
            try:
                raise self.missing("extensions/demo-extension.json")
            except FileNotFoundError as missing:
                raise ValueError("input snapshot could not read the extension manifest") from missing

        with patch.object(server, "current_execution", lambda **k: record), \
                patch.object(server, "bind_run_execution", lambda project, *a: project), \
                patch.object(server, "create_run_input_snapshot", snapshot), \
                patch.object(server, "source_identity_changed", lambda rec, **k: rec["source_sha256"] == "a" * 64):
            server._prepare_run_stages(context)
        status = self.status()
        self.assertEqual(status["error_code"], CODE)
        self.assertEqual(status["preparation"]["failed_stage"], "snapshot")

    def test_missing_module_file_without_a_lifecycle_change_keeps_its_code(self) -> None:
        context = self.context(admission_generation=server.execution_source_generation())

        def capture(**_kwargs):
            raise self.missing("hx-flat-offer-73.json")

        with patch.object(server, "current_execution", capture):
            server._prepare_run_stages(context)
        self.assertEqual(self.status()["error_code"], "GF_INPUT_SNAPSHOT_FAILED")

    def test_missing_file_outside_modules_keeps_its_code(self) -> None:
        context = self.context(admission_generation=server.execution_source_generation())

        def capture(**_kwargs):
            server._bump_execution_source_generation()
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(self.home / "packs" / "demand.csv"))

        with patch.object(server, "current_execution", capture):
            server._prepare_run_stages(context)
        status = self.status()
        self.assertEqual(status["error_code"], "GF_INPUT_SNAPSHOT_FAILED")
        self.assertIn("demand.csv", status["error"])

    def test_admission_records_the_generation_before_the_registry(self) -> None:
        source = Path(server.__file__).read_text("utf-8")
        admit = source[source.index("    def _admit_run("):source.index("    def _preflight_admitted_run(")]
        self.assertLess(admit.index("admission_generation = execution_source_generation()"),
                        admit.index("registry = MODULE_REGISTRY"))
        self.assertIn("admission_generation=admission_generation", admit)
        create = source[source.index("    def _create_preparing_run("):]
        self.assertIn('admission_generation=getattr(admission, "admission_generation", None)', create[:4000])


if __name__ == "__main__":
    unittest.main()
