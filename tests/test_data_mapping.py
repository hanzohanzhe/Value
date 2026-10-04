import csv
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.data_mapping import DataMappingService, DataMappingError
from backend.data_pack_clone import clone_data_pack, DataPackCloneError, manifest_sha256
from gridform_core.catalog import DATASET_SLOTS
from gridform_core.run_snapshot import _freeze_pack


class DataMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        packs = self.root / "packs"
        source = packs / "base"; source.mkdir(parents=True)
        (source / "manifest.json").write_text(json.dumps({
            "schema_version": "value.data-pack/v1", "id": "base", "name": "base", "bindings": {},
        }))
        copied = clone_data_pack("base", {"schema_version": "value.data-pack-clone-request/v1",
            "name": "independent", "source_manifest_sha256": manifest_sha256(source / "manifest.json")},
            packs_root=packs, minimum_free_space_bytes=0)["data_pack"]
        self.pack_id = copied["id"]
        self.pack = packs / self.pack_id
        self.service = DataMappingService(packs_root=packs, staging_root=self.root / "staging",
            projects_root=self.root / "projects", trash_root=self.root / "trash",
            dataset_slots=DATASET_SLOTS, lifecycle_lock=threading.RLock())

    def stage(self, raw, role="projects.repd"):
        return self.service.stage(self.pack_id, role, raw, "foreign.csv", manifest_sha256(self.pack / "manifest.json"))

    def review(self, stage, columns):
        return self.service.preview(stage["stage_id"], {"schema_version": "value.data-mapping-preview-request/v1",
            "source_sha256": stage["source_sha256"], "target_manifest_sha256": stage["target_manifest_sha256"],
            "columns": columns})

    def commit(self, review):
        return self.service.commit(review["review_id"], {"schema_version": "value.data-mapping-commit-request/v1",
            **{key: review[key] for key in ("source_sha256", "spec_sha256", "normalized_sha256", "target_manifest_sha256")}})

    def project_review(self):
        stage = self.stage(b"id,kind,power,status,area\np1,CCGT,1000,Operational,GB\n")
        columns = [{"source": source, "target": target, "source_unit": unit, "target_unit": target_unit}
            for source, target, unit, target_unit in (
                ("id", "project_id", None, None), ("kind", "technology", None, None),
                ("power", "capacity_mw", "kW", "MW"),
                ("status", "development_status", None, None), ("area", "region", None, None))]
        return stage, self.review(stage, columns)

    def test_runtime_catalog_and_two_roles_validate_and_normalize_once(self):
        roles = {row["role"]: row for row in self.service.catalog(self.pack_id)["roles"]}
        self.assertEqual(roles["demand.forecast"]["columns"], [{"target": "value", "target_unit": "MW"}])
        self.assertEqual({row["target"]: row["target_unit"] for row in roles["projects.repd"]["columns"]}["capacity_mw"], "MW")
        stage = self.stage(b"ignored,load\n" + b"x,60\n" * 17520, "demand.forecast")
        review = self.review(stage, [{"source": "load", "target": "value", "source_unit": "MWh/period", "target_unit": "MW"}])
        self.assertTrue(review["valid"], review["errors"])
        self.assertFalse(any("unit is not declared" in warning for warning in review["warnings"]))
        self.assertEqual(review["rows"], 17520)
        self.assertEqual(len(review["sample_rows"]), 20)
        self.assertEqual(float(review["sample_rows"][0]["value"]), 120.0)
        self.assertEqual(review["interval_minutes"], 30)
        demand = self.commit(review)["binding"]
        self.assertEqual(demand["unit"], "MW")
        self.assertEqual(demand["input_unit_contract"], "value.demand-mw-half-hour/v1")
        self.assertEqual(demand["interval_minutes"], 30)
        stage, review = self.project_review()
        self.assertTrue(review["valid"], review["errors"])
        result = self.commit(review)
        self.assertFalse(result["run_started"])
        binding = result["binding"]
        self.assertNotIn("adapter", binding)
        normalized = (self.pack / binding["uri"]).read_bytes()
        row = list(csv.DictReader(io.StringIO(normalized.decode())))[0]
        self.assertEqual(float(row["capacity_mw"]), 1.0)
        provenance = binding["mapping_provenance"]
        self.assertIn(b"1000", (self.pack / provenance["source_uri"]).read_bytes())
        self.assertTrue((self.pack / provenance["spec_uri"]).is_file())
        manifest = json.loads((self.pack / "manifest.json").read_bytes())
        snapshot_dir = self.root / "snapshot"; snapshot_dir.mkdir()
        with patch("gridform_core.run_snapshot.execute_adapter", side_effect=AssertionError("must not convert twice")):
            frozen, objects = _freeze_pack(pack_root=self.pack, pack_manifest=manifest,
                staging=snapshot_dir, destination_name="pack", pack_kind="base", object_root=self.root / "objects")
        self.assertEqual((snapshot_dir / "pack" / frozen["bindings"]["projects.repd"]["uri"]).read_bytes(), normalized)
        frozen_demand = snapshot_dir / "pack" / frozen["bindings"]["demand.forecast"]["uri"]
        self.assertEqual(float(next(csv.DictReader(io.StringIO(frozen_demand.read_text())))["value"]), 120.0)
        self.assertEqual(objects[-1]["sha256"], binding["sha256"])

    def test_csv_whole_file_shape_utf8_and_last_row_validation(self):
        before = (self.pack / "manifest.json").read_bytes()
        with self.assertRaises(DataMappingError):
            self.service.stage(self.pack_id, "projects.repd", b"a\n1\n", "foreign.csv", None)
        for raw in (b"a,a\n1,2\n", b"a,b\n1,2\n3\n", b"a\n\xff\n", b"a\n", b"a\n\x00\n"):
            with self.subTest(raw=raw), self.assertRaises(DataMappingError):
                self.stage(raw)
        stage = self.stage(b"load\n" + b"2\n" * 17520 + b"not-a-number\n", "demand.forecast")
        review = self.review(stage, [{"source": "load", "target": "value", "source_unit": "MWh/period", "target_unit": "MW"}])
        self.assertFalse(review["valid"])
        with self.assertRaises(DataMappingError):
            self.commit(review)
        self.assertEqual((self.pack / "manifest.json").read_bytes(), before)

    def test_changed_source_spec_normalized_target_and_expiry_reject_without_manifest_write(self):
        for changed in ("source", "spec", "normalized", "target", "expiry"):
            with self.subTest(changed=changed):
                stage, review = self.project_review()
                stage_dir = self.root / "staging/stages" / stage["stage_id"]
                review_dir = self.root / "staging/reviews" / review["review_id"]
                if changed == "source":
                    (stage_dir / "source.csv").write_bytes(b"changed\n1\n")
                elif changed == "spec":
                    payload = json.loads((review_dir / "spec.json").read_bytes())
                    payload["columns"][0]["source"] = "id"
                    (review_dir / "spec.json").write_text(json.dumps(payload))
                elif changed == "normalized":
                    (review_dir / "normalized.csv").write_bytes(b"changed\n1\n")
                elif changed == "target":
                    payload = json.loads((self.pack / "manifest.json").read_bytes()); payload["name"] = "new"
                    (self.pack / "manifest.json").write_text(json.dumps(payload))
                else:
                    payload = json.loads((review_dir / "metadata.json").read_bytes()); payload["expires_epoch"] = 0
                    (review_dir / "metadata.json").write_text(json.dumps(payload))
                before = (self.pack / "manifest.json").read_bytes()
                with self.assertRaises((DataMappingError, DataPackCloneError)):
                    self.commit(review)
                self.assertEqual((self.pack / "manifest.json").read_bytes(), before)

    def test_saved_historical_and_trashed_study_references_block_commit(self):
        for relative in ("projects/study/project.json", "projects/study/revisions/old.json", "trash/item/study/project.json", "trash/item/study/revisions/old.json"):
            with self.subTest(relative=relative):
                _, review = self.project_review()
                path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"data_pack_id": self.pack_id}))
                before = (self.pack / "manifest.json").read_bytes()
                with self.assertRaisesRegex(DataPackCloneError, "uses this data pack"):
                    self.commit(review)
                self.assertEqual((self.pack / "manifest.json").read_bytes(), before)
                path.unlink()

    def test_unsupported_units_duplicate_target_and_failure_keep_manifest(self):
        stage, review = self.project_review()
        before = (self.pack / "manifest.json").read_bytes()
        columns = review["columns"]
        for variant in ("unit", "duplicate"):
            bad = [dict(row) for row in columns]
            if variant == "unit":
                next(row for row in bad if row["target"] == "capacity_mw")["source_unit"] = "ambiguous"
            else:
                bad[1]["target"] = bad[0]["target"]
            with self.assertRaises(DataMappingError):
                self.review(stage, bad)
        with patch("backend.data_mapping.promote_binding_revision", side_effect=ValueError("role validation failed")):
            with self.assertRaisesRegex(ValueError, "role validation failed"):
                self.commit(review)
        self.assertEqual((self.pack / "manifest.json").read_bytes(), before)
        self.assertFalse((self.pack / "mapping-provenance" / review["review_id"]).exists())
