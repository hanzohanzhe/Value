import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.run_bundle import export_run_bundle, import_bundle_archive, validate_bundle_archive
from gridform_core.run_lifecycle import LifecycleError, atomic_status_transition
from gridform_core.run_quota import (
    QuotaPolicy,
    output_reservation_bytes,
    reserve_run_space,
)


class RunLifecycleTests(unittest.TestCase):
    def test_snapshot_volume_reserve_is_not_counted_as_run_output(self):
        gib = 1024**3
        estimate = {
            "persisted_bytes": 2 * gib,
            "temporary_bytes": 1 * gib,
            "reserve_bytes": 80 * gib,
            "required_bytes": 83 * gib,
            "disk_bytes": 2 * gib,
        }
        self.assertEqual(output_reservation_bytes(estimate), 3 * gib)

    def test_legacy_estimates_use_disk_bytes_then_required_bytes(self):
        self.assertEqual(output_reservation_bytes({"disk_bytes": 123}), 123)
        self.assertEqual(output_reservation_bytes({"required_bytes": 456}), 456)

    def test_state_machine_is_atomic_and_rejects_invalid_transition(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            path.write_text(json.dumps({"status": "running"}), encoding="utf-8")
            value = atomic_status_transition(path, "cancel_requested", reason_code="TEST_CANCEL")
            self.assertEqual(value["status"], "cancel_requested")
            self.assertEqual(value["lifecycle_history"][0]["reason_code"], "TEST_CANCEL")
            with self.assertRaises(LifecycleError):
                atomic_status_transition(path, "archived", reason_code="BAD")

    def test_quota_refuses_before_writing_reservation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = reserve_run_space(root, "r", 101, policy=QuotaPolicy(100, 100, 0))
            self.assertFalse(result["accepted"])
            self.assertFalse((root / "r" / "reservation.json").exists())

    def test_portable_bundle_roundtrip_excludes_pickle_and_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "run"
            (root / "model-output" / "checkpoints-v2").mkdir(parents=True)
            (root / "status.json").write_text('{"status":"completed"}', encoding="utf-8")
            (root / "model-output" / "resolved-run.json").write_text("{}", encoding="utf-8")
            (root / "model-output" / "checkpoints-v2" / "state-2026.json").write_text("{}", encoding="utf-8")
            (root / "model-output" / "legacy.pkl").write_bytes(b"not executable during import")
            archive = Path(folder) / "bundle.zip"
            manifest = export_run_bundle(root, archive, profile="checkpoint_capable")
            self.assertTrue(manifest["resumable"])
            self.assertFalse(any(row["path"].endswith(".pkl") for row in manifest["files"]))
            self.assertTrue(validate_bundle_archive(archive)["valid"])
            imported = import_bundle_archive(archive, Path(folder) / "staging")
            self.assertTrue((imported / "model-output" / "checkpoints-v2" / "state-2026.json").is_file())
            self.assertEqual(len(imported.name), 20)
            self.assertEqual(import_bundle_archive(archive, Path(folder) / "staging"), imported)
            self.assertEqual(len((imported / ".force-import-sha256").read_text().strip()), 64)


if __name__ == "__main__":
    unittest.main()
