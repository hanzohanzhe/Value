"""Execution admission binds recorded evidence; no runtime capture or worker."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import run_execution as admission
from backend.frozen_run_recovery import json_hash
from gridform_core.v2.contracts import ResolvedRun
from gridform_core.v2.orchestrator import checkpoint_identity


class RunExecutionAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.record = {"identity_sha256": "a" * 64, "source_sha256": "b" * 64,
            "environment_sha256": "c" * 64, "archive_complete": True, "identity_complete": True}
        self.original = {"id": "study", "extensions": {"existing": {"preserved": True}}}
        self.project = admission.bind_run_execution(self.original, self.root, self.record)

    def verify(self, project=None):
        return admission.verify_run_execution(self.root, project or self.project,
            source_root=self.root / "source", data_home=self.root / "state", require_record=True)

    def test_bound_reference_matches_record_and_same_current_identity_passes(self):
        reference = self.project["extensions"]["execution_bundle"]
        self.assertEqual(reference["record_sha256"], json_hash(self.record))
        self.assertNotIn("execution_bundle", self.original["extensions"])
        self.assertEqual(self.project["extensions"]["existing"], self.original["extensions"]["existing"])
        self.assertEqual(json.loads((self.root / "execution-bundle.json").read_text()), self.record)
        with patch.object(admission, "verify_execution_bundle") as archive, patch.object(
                admission, "current_execution", return_value=copy.deepcopy(self.record)):
            self.assertEqual(self.verify(), self.record)
            archive.assert_called_once_with(self.record, archive_root=self.root / "state/execution-archives")

    def test_record_tamper_rejected_before_archive_or_current_capture(self):
        changed = {**self.record, "source_sha256": "d" * 64}
        (self.root / "execution-bundle.json").write_text(json.dumps(changed))
        with patch.object(admission, "verify_execution_bundle") as archive, patch.object(admission, "current_execution") as capture:
            with self.assertRaisesRegex(ValueError, "does not match"):
                self.verify()
            archive.assert_not_called(); capture.assert_not_called()

    def test_current_source_or_environment_identity_change_rejected(self):
        for field in ("source_sha256", "environment_sha256"):
            changed = {**self.record, field: "d" * 64, "identity_sha256": "e" * 64}
            with self.subTest(field=field), patch.object(admission, "verify_execution_bundle"), patch.object(
                    admission, "current_execution", return_value=changed):
                with self.assertRaisesRegex(ValueError, "changed after enqueue"):
                    self.verify()

    def test_required_legacy_reference_and_missing_record_rejected(self):
        with self.assertRaisesRegex(ValueError, "historical Run lacks"):
            self.verify(project=self.original)
        self.assertIsNone(admission.verify_run_execution(self.root, self.original,
            source_root=self.root, data_home=self.root, require_record=False))
        (self.root / "execution-bundle.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.verify()

    def test_checkpoint_identity_changes_with_execution_bundle(self):
        run = ResolvedRun("run", "study", "scenario", "pack", 2025, 2026, {},
            {"clock.period_hours": .5}, {}, extensions={"execution_bundle": self.project["extensions"]["execution_bundle"]})
        before = checkpoint_identity(run)
        changed = replace(run, extensions={"execution_bundle": {**run.extensions["execution_bundle"], "identity_sha256": "f" * 64}})
        self.assertNotEqual(before, checkpoint_identity(changed))
        self.assertEqual(before["execution_bundle"], self.project["extensions"]["execution_bundle"])


if __name__ == "__main__":
    unittest.main()
