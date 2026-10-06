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


class EurPriceMappingTests(DataMappingTests):
    """P0-5a S10 (P6-12): EUR prices need an explicit rate; mapped series declare how they are read."""

    def preview_with(self, stage, columns, fx=None):
        request = {"schema_version": "value.data-mapping-preview-request/v1",
                   "source_sha256": stage["source_sha256"], "target_manifest_sha256": stage["target_manifest_sha256"],
                   "columns": columns}
        if fx is not None:
            request["fx"] = fx
        return self.service.preview(stage["stage_id"], request)

    def test_eur_price_converts_with_an_explicit_rate(self):
        roles = {row["role"]: row for row in self.service.catalog(self.pack_id)["roles"]}
        price = roles["market.belgium.price"]
        self.assertEqual(price["columns"], [{"target": "value", "target_unit": "GBP/MWh"}])
        self.assertIn({"source_unit": "EUR/MWh", "target_unit": "GBP/MWh", "requires_fx": True}, price["conversion_pairs"])
        stage = self.stage(b"hour,eur\n" + b"x,110\n" * 17520, "market.belgium.price")
        columns = [{"source": "eur", "target": "value", "source_unit": "EUR/MWh", "target_unit": "GBP/MWh"}]
        with self.assertRaises(DataMappingError) as missing:
            self.preview_with(stage, columns)
        self.assertEqual(missing.exception.code, "GF_MAPPING_FX")
        with self.assertRaises(DataMappingError):
            self.preview_with(stage, columns, {"eur_per_gbp": 1.1})
        review = self.preview_with(stage, columns, {"eur_per_gbp": 1.1, "fx_basis": "toy fixed rate", "price_year": 2022})
        self.assertTrue(review["valid"], review["errors"])
        self.assertAlmostEqual(float(review["sample_rows"][0]["value"]), 100.0, places=9)
        # F-P05A-1: the original EUR value is reported beside the converted one, with the rate used.
        self.assertEqual(review["source_sample_rows"][0], {"eur": "110"})
        self.assertEqual(review["fx"], {"eur_per_gbp": 1.1, "fx_basis": "toy fixed rate", "price_year": 2022})
        binding = self.commit(review)["binding"]
        self.assertEqual((binding["unit"], binding["currency"], binding["source_currency"]), ("GBP/MWh", "GBP", "EUR"))
        self.assertEqual((binding["eur_per_gbp"], binding["fx_basis"]), (1.1, "toy fixed rate"))
        self.assertEqual((binding["csv_column"], binding["csv_header"]), ("value", True))

    def test_market_profile_in_mwh_per_period_converts_to_mw(self):
        stage = self.stage(b"t,flow\n" + b"x,6\n" * 17520, "market.france.profile")
        review = self.preview_with(stage, [{"source": "flow", "target": "value", "source_unit": "MWh/period", "target_unit": "MW"}])
        self.assertTrue(review["valid"], review["errors"])
        self.assertEqual(float(review["sample_rows"][0]["value"]), 12.0)
        binding = self.commit(review)["binding"]
        self.assertEqual((binding["unit"], binding["interval_minutes"]), ("MW", 30))

    # Spec 11.6 (S-D4): a declared timestamp column is checked row by row by the chronology layer.
    def _timed(self, rows):
        return b"time,flow\n" + "".join(f"{stamp},6\n" for stamp in rows).encode()

    def _half_hours(self, count, start="2025-01-01T00:00:00"):
        import datetime as dt
        first = dt.datetime.fromisoformat(start)
        return [(first + dt.timedelta(minutes=30 * index)).strftime("%Y-%m-%d %H:%M") for index in range(count)]

    def test_timestamp_column_is_declared_checked_and_kept(self):
        roles = {row["role"]: row for row in self.service.catalog(self.pack_id)["roles"]}
        self.assertTrue(roles["market.france.profile"]["timestamp_supported"])
        self.assertEqual(roles["market.france.profile"]["time_zones"], ["UTC", "Europe/London"])
        self.assertNotIn("timestamp_supported", roles["projects.repd"])
        stage = self.stage(self._timed(self._half_hours(17520)), "market.france.profile")
        columns = [{"source": "flow", "target": "value", "source_unit": "MWh/period", "target_unit": "MW"}]
        review = self.service.preview(stage["stage_id"], {"schema_version": "value.data-mapping-preview-request/v1",
            "source_sha256": stage["source_sha256"], "target_manifest_sha256": stage["target_manifest_sha256"],
            "columns": columns, "timestamp": {"column": "time", "time_zone": "UTC"}})
        self.assertTrue(review["valid"], review["errors"])
        self.assertEqual((review["timestamp"]["problem_count"], review["timestamp"]["rows_checked"]), (0, 17520))
        binding = self.commit(review)["binding"]
        self.assertEqual((binding["timestamp_column"], binding["timestamp_time_zone"], binding["interval_minutes"]), ("time", "UTC", 30))
        self.assertTrue((self.pack / binding["timestamp_uri"]).is_file())
        self.assertEqual(binding["timestamp_check"]["status"], "passed")
        # The pack's chronology layer re-checks the declared timestamps from the retained source.
        from gridform_core.data_validation_layers import evaluate_layers
        manifest = json.loads((self.pack / "manifest.json").read_text())
        self.assertNotIn("GF_DATA_TIMESTAMPS", [row["code"] for row in evaluate_layers(self.pack, manifest)["chronology"]["findings"]])

    def test_shifted_or_repeated_timestamps_are_listed_by_row_and_block_the_commit(self):
        stamps = self._half_hours(17520)
        stamps[3] = stamps[2]           # a repeated stamp (row 5 in the file)
        stamps[10:] = self._half_hours(17510, start="2025-01-01T06:00:00")  # 04:30 -> 06:00 at row 12
        stage = self.stage(self._timed(stamps), "market.france.profile")
        columns = [{"source": "flow", "target": "value", "source_unit": "MWh/period", "target_unit": "MW"}]
        review = self.service.preview(stage["stage_id"], {"schema_version": "value.data-mapping-preview-request/v1",
            "source_sha256": stage["source_sha256"], "target_manifest_sha256": stage["target_manifest_sha256"],
            "columns": columns, "timestamp": {"column": "time", "time_zone": "UTC"}})
        self.assertFalse(review["valid"])
        self.assertTrue(any(error.startswith("GF_DATA_TIMESTAMPS: ") for error in review["errors"]), review["errors"])
        rows = {row["row"]: row["problem"] for row in review["timestamp"]["problems"]}
        self.assertEqual(rows[5], "duplicate of row 4")
        self.assertEqual(rows[12], "gap of 90 minutes after the previous row (expected 30)")
        with self.assertRaises(DataMappingError) as refused:
            self.commit(review)
        self.assertEqual(refused.exception.code, "GF_MAPPING_NOT_VALIDATED")

    def test_london_autumn_hour_seen_once_is_a_row_finding_not_a_runtime_error(self):
        # N-2: naive London wall-clock stamps written as a continuous 30-minute
        # sequence show the repeated autumn hour once; pytz's AmbiguousTimeError
        # used to escape the fallback and the preview failed with HTTP 500.
        from gridform_core.data_validation_layers import (
            AMBIGUOUS_LOCAL_TIME, NONEXISTENT_LOCAL_TIME, timestamp_findings, timestamp_row_problems)
        stage = self.stage(self._timed(self._half_hours(17520)), "market.france.profile")
        columns = [{"source": "flow", "target": "value", "source_unit": "MWh/period", "target_unit": "MW"}]
        review = self.service.preview(stage["stage_id"], {"schema_version": "value.data-mapping-preview-request/v1",
            "source_sha256": stage["source_sha256"], "target_manifest_sha256": stage["target_manifest_sha256"],
            "columns": columns, "timestamp": {"column": "time", "time_zone": "Europe/London"}})
        self.assertFalse(review["valid"])
        self.assertTrue(any(error.startswith("GF_DATA_TIMESTAMPS: ") for error in review["errors"]), review["errors"])
        rows = {row["row"]: row["problem"] for row in review["timestamp"]["problems"]}
        # 2025-10-26 01:00 and 01:30 are file rows 14308 and 14309 (header is row 1).
        self.assertEqual(rows[14308], AMBIGUOUS_LOCAL_TIME)
        self.assertEqual(rows[14309], AMBIGUOUS_LOCAL_TIME)
        # 2025-03-30 01:00 and 01:30 do not exist in London (file rows 4228 and 4229).
        self.assertEqual(rows[4228], NONEXISTENT_LOCAL_TIME)
        self.assertEqual(rows[4229], NONEXISTENT_LOCAL_TIME)
        self.assertEqual(review["timestamp"]["problem_count"], 4)
        with self.assertRaises(DataMappingError):
            self.commit(review)
        # The same file through the chronology layer: a finding, not an exception.
        path = self.root / "london-once.csv"
        path.write_bytes(self._timed(self._half_hours(17520)))
        findings = timestamp_findings(path, "time", 30, "market.france.profile", time_zone="Europe/London")
        self.assertEqual([row["code"] for row in findings], ["GF_DATA_TIMESTAMPS"])
        self.assertIn("2 ambiguous local time(s)", findings[0]["message"])
        # Autumn stamps carrying their offsets are placed exactly.
        offsets = self.root / "london-offsets.csv"
        offsets.write_text("time,v\n2025-10-26 01:00+01:00,1\n2025-10-26 01:30+01:00,1\n"
                           "2025-10-26 01:00+00:00,1\n2025-10-26 01:30+00:00,1\n")
        self.assertEqual(timestamp_row_problems(offsets, "time", 30, time_zone="Europe/London")["problem_count"], 0)

    def test_series_shifted_against_the_model_clock_is_warned_not_blocked(self):
        # N-3: a whole-series shift passes the row checks; the review says so.
        columns = [{"source": "flow", "target": "value", "source_unit": "MWh/period", "target_unit": "MW"}]
        def review_of(stamps):
            stage = self.stage(self._timed(stamps), "market.france.profile")
            return self.service.preview(stage["stage_id"], {"schema_version": "value.data-mapping-preview-request/v1",
                "source_sha256": stage["source_sha256"], "target_manifest_sha256": stage["target_manifest_sha256"],
                "columns": columns, "timestamp": {"column": "time", "time_zone": "UTC"}})
        aligned = review_of(self._half_hours(17520))
        self.assertEqual(aligned["timestamp"]["origin_offset_minutes"], 0)
        self.assertEqual((aligned["timestamp"]["first_utc"], aligned["timestamp"]["last_utc"]),
                         ("2025-01-01T00:00:00+00:00", "2025-12-31T23:30:00+00:00"))
        self.assertFalse([w for w in aligned["warnings"] if w.startswith("GF_DATA_TIMESTAMP_ORIGIN")])
        for start, offset, word in (("2025-01-01T00:30:00", 30, "after"), ("2024-12-31T23:30:00", -30, "before")):
            with self.subTest(start=start):
                shifted = review_of(self._half_hours(17520, start=start))
                self.assertTrue(shifted["valid"], shifted["errors"])
                self.assertEqual(shifted["timestamp"]["origin_offset_minutes"], offset)
                origin = [w for w in shifted["warnings"] if w.startswith("GF_DATA_TIMESTAMP_ORIGIN")]
                self.assertEqual(len(origin), 1, shifted["warnings"])
                self.assertIn(f"30 minutes {word} 1 January 00:00", origin[0])
        # Another reference year is not a shift: the year is shown, not judged.
        other_year = review_of(self._half_hours(17520, start="2023-01-01T00:00:00"))
        self.assertEqual((other_year["timestamp"]["origin_offset_minutes"], other_year["timestamp"]["first_utc"]),
                         (0, "2023-01-01T00:00:00+00:00"))

    def test_timestamp_declaration_is_validated(self):
        stage = self.stage(self._timed(self._half_hours(4)), "market.france.profile")
        columns = [{"source": "flow", "target": "value", "source_unit": "MWh/period", "target_unit": "MW"}]
        base = {"schema_version": "value.data-mapping-preview-request/v1", "source_sha256": stage["source_sha256"],
                "target_manifest_sha256": stage["target_manifest_sha256"], "columns": columns}
        for timestamp in ({"column": "missing", "time_zone": "UTC"}, {"column": "flow", "time_zone": "UTC"},
                          {"column": "time", "time_zone": "Europe/Paris"}, {"column": "time"}):
            with self.subTest(timestamp=timestamp), self.assertRaises(DataMappingError) as refused:
                self.service.preview(stage["stage_id"], {**base, "timestamp": timestamp})
            self.assertEqual(refused.exception.code, "GF_MAPPING_TIMESTAMP")
        project_stage, _ = self.project_review()
        with self.assertRaises(DataMappingError) as refused:
            self.service.preview(project_stage["stage_id"], {"schema_version": "value.data-mapping-preview-request/v1",
                "source_sha256": project_stage["source_sha256"], "target_manifest_sha256": project_stage["target_manifest_sha256"],
                "columns": [{"source": "id", "target": "project_id", "source_unit": None, "target_unit": None}],
                "timestamp": {"column": "status", "time_zone": "UTC"}})
        self.assertIn(refused.exception.code, {"GF_MAPPING_TIMESTAMP", "GF_MAPPING_COLUMNS"})

    def test_london_wall_clock_across_the_autumn_change_is_regular(self):
        from gridform_core.data_validation_layers import timestamp_row_problems
        path = self.root / "london.csv"
        path.write_text("time,v\n2025-10-26 00:30,1\n2025-10-26 01:00,1\n2025-10-26 01:30,1\n2025-10-26 01:00,1\n2025-10-26 01:30,1\n2025-10-26 02:00,1\n")
        self.assertEqual(timestamp_row_problems(path, "time", 30, time_zone="Europe/London")["problem_count"], 0)
        utc = timestamp_row_problems(path, "time", 30, time_zone="UTC")
        self.assertEqual([row["problem"] for row in utc["problems"]], ["duplicate of row 3", "duplicate of row 4"])
