import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend.frozen_input_recovery import stage_recovered_inputs, FrozenInputRecoveryError
from gridform_core.run_snapshot import create_run_input_snapshot, _freeze_pack
from gridform_core.frozen_input_integrity import verify_frozen_input_integrity
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.zonal_contracts import ZONAL_ROLES, load_zonal_network_pack
from gridform_core.frontend_contract import builtin_maturity_acknowledgement_key
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS
from tests.test_run_input_snapshot import SELECTION


ROOT = Path(__file__).resolve().parents[1]


class FrozenInputRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.staging = self.root / "staging"

    def source(self, network=False):
        source_pack = self.root / "source-pack"
        selected = dict(SELECTION)
        project = {"id": "source-study", "modules": selected, "data_pack_id": "source-base"}
        if network:
            shutil.copytree(ROOT / "data-packs/value-101-network-v1", source_pack)
            original = json.loads((source_pack / "manifest.json").read_bytes())
            selected.update(psm="value-staged-bid-at-cost-psm", balancing="value-zonal-redispatch-balancing",
                            weather_spatializer="value-representative-point-weather", storage_cost="dynamic-annual-storage-cost")
            project.update(data_pack_id=original["id"], market_configuration={"network_pack_id": original["id"]},
                selected_extensions=["value-zonal-redispatch-extension"],
                maturity_acknowledgements={
                    builtin_maturity_acknowledgement_key("module", "value-zonal-redispatch-balancing"): "value.experimental-ack/v1",
                    "module:value-representative-point-weather@1.0.0": "value.experimental-ack/v1",
                    "extension:value-zonal-redispatch-extension@1.0.0": "value.experimental-ack/v1"},
                solver_contract=DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        else:
            source_pack.mkdir()
            raw = b"power\n1000\n2000\n"
            (source_pack / "raw.csv").write_bytes(raw)
            adapter = {"adapter_id": "capacity-map", "version": "1", "source_format": "csv",
                "canonical_role": "demand.real", "canonical_format": "csv",
                "columns": [{"source": "power", "target": "value", "source_unit": "kW", "target_unit": "MW"}]}
            manifest = {"schema_version": "value.data-pack/v1", "id": "source-base", "name": "Source",
                "scientific_baseline_eligible": True, "scientific_validation_status": "passed",
                "owner_approval": "source-owner",
                "bindings": {"demand.real": {"uri": "raw.csv", "filename": "raw.csv", "format": "csv",
                    "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "adapter": adapter,
                    "mapping_provenance": {"source_uri": "not-in-snapshot/raw.csv"}}}}
            (source_pack / "manifest.json").write_text(json.dumps(manifest))
        run = self.root / "source-run"; run.mkdir()
        snapshot = create_run_input_snapshot(run_dir=run, project=project, pack_root=source_pack,
            network_pack_root=source_pack if network else None, registry=workspace_registry(self.root / "no-local"),
            selected=selected, object_root=self.root / "objects")
        return run, snapshot["snapshot_id"]

    def recover(self, run, snapshot_id, network=False):
        return stage_recovered_inputs(run, self.staging, base_pack_id="recovered-base-v1",
            network_pack_id="recovered-network-v1" if network else None, source_snapshot_id=snapshot_id)

    def test_adapter_is_historical_only_independent_copy_and_source_unchanged(self):
        run, snapshot_id = self.source()
        before = {str(path.relative_to(run)): path.read_bytes() for path in run.rglob("*") if path.is_file()}
        result = self.recover(run, snapshot_id)
        binding = result["base_manifest"]["bindings"]["demand.real"]
        self.assertNotIn("adapter", binding)
        self.assertNotIn("mapping_provenance", binding)
        provenance = binding["frozen_recovery_provenance"]
        self.assertIn("adapter", provenance["historical_metadata"])
        self.assertEqual(provenance["historical_metadata"]["mapping_provenance"]["source_uri"], "not-in-snapshot/raw.csv")
        self.assertFalse(provenance["historical_uri_files_restored"])
        path = result["base_root"] / binding["uri"]
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertEqual(path.read_bytes(), b"value\n1.0\n2.0\n")
        with patch("gridform_core.run_snapshot.execute_adapter", side_effect=AssertionError("no double normalization")):
            stage = self.root / "new-snapshot"; stage.mkdir()
            frozen, _ = _freeze_pack(pack_root=result["base_root"], pack_manifest=result["base_manifest"],
                staging=stage, destination_name="pack", pack_kind="base", object_root=self.root / "new-objects")
        self.assertEqual((stage / "pack" / frozen["bindings"]["demand.real"]["uri"]).read_bytes(), path.read_bytes())
        self.assertFalse(result["base_manifest"]["scientific_baseline_eligible"])
        self.assertNotIn("owner_approval", result["base_manifest"])
        after = {str(path.relative_to(run)): path.read_bytes() for path in run.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(result["study_saved"])
        self.assertFalse(result["run_started"])

    def test_real_value101_network_same_source_separates_and_rehashes_mechanical_identity(self):
        run, snapshot_id = self.source(network=True)
        before = verify_frozen_input_integrity(run / "input-snapshot")
        result = self.recover(run, snapshot_id, network=True)
        self.assertEqual(result["base_manifest"]["data_pack_type"], "base")
        self.assertEqual(result["network_manifest"]["data_pack_type"], "network_overlay")
        self.assertNotIn("zonal_network_pack", result["base_manifest"])
        self.assertTrue(set(ZONAL_ROLES).isdisjoint(result["base_manifest"]["bindings"]))
        self.assertEqual(set(result["network_manifest"]["bindings"]), set(ZONAL_ROLES))
        self.assertIn("demand.real", result["base_manifest"]["bindings"])
        network = load_zonal_network_pack(result["network_root"], result["network_manifest"])
        self.assertEqual(network.network_pack_id, "recovered-network-v1")
        self.assertNotEqual(network.scientific_sha256, before["network_manifest"]["zonal_network_pack"]["scientific_sha256"])
        self.assertFalse(result["network_manifest"]["scientific_baseline_eligible"])
        self.assertEqual(result["base_manifest"]["frozen_recovery_origin"]["source_data_pack_type"], "network_overlay")
        self.assertEqual(verify_frozen_input_integrity(run / "input-snapshot"), before)

    def test_bad_ids_stale_snapshot_and_tampered_source_are_rejected(self):
        run, snapshot_id = self.source()
        for base_id, expected in (("../escape", snapshot_id), ("source-base", snapshot_id), ("new-base", "d" * 64)):
            with self.subTest(base_id=base_id), self.assertRaises(FrozenInputRecoveryError):
                stage_recovered_inputs(run, self.staging, base_pack_id=base_id, network_pack_id=None, source_snapshot_id=expected)
        result = verify_frozen_input_integrity(run / "input-snapshot")
        path = run / "input-snapshot/pack" / result["canonical_roles"][0]["uri"]
        path.unlink(); path.write_bytes(b"tampered\n")
        with self.assertRaises(FrozenInputRecoveryError):
            self.recover(run, snapshot_id)
        self.assertFalse(self.staging.exists())

    def test_copy_failure_and_source_drift_remove_entire_stage(self):
        run, snapshot_id = self.source()
        with patch("backend.frozen_input_recovery.shutil.copyfile", side_effect=OSError("disk full")):
            with self.assertRaises(FrozenInputRecoveryError):
                self.recover(run, snapshot_id)
        self.assertEqual(list(self.staging.iterdir()), [])
        real_verify = verify_frozen_input_integrity
        count = 0
        def drift(root):
            nonlocal count
            result = real_verify(root); count += 1
            if count == 2:
                result["snapshot_id"] = "d" * 64
            return result
        with patch("backend.frozen_input_recovery.verify_frozen_input_integrity", side_effect=drift):
            with self.assertRaisesRegex(FrozenInputRecoveryError, "changed while staging"):
                self.recover(run, snapshot_id)
        self.assertEqual(list(self.staging.iterdir()), [])
