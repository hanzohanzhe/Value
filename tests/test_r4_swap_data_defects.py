"""R4 (DECISIONS A27): the swap-data-role defects of the final four-role report.

Each test names the defect it covers (S-中n / S-低n, and the clock and
coverage notes of section 7.3).
"""

from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core.market_ledger import create_market_ledger
from gridform_core.market_replay import query_dispatch_timeline, query_stress_events
from gridform_core.model_clock import (
    LEGACY_LEDGER_CLOCK,
    MODEL_CALENDAR,
    ledger_clock,
    period_start_iso,
)

from tests.test_market_replay import _period

ROOT = Path(__file__).resolve().parents[1]


def _ledger(folder: Path, semantic: dict | None = None) -> Path:
    database = folder / "market" / "market.sqlite"
    ledger = create_market_ledger(
        database,
        "full",
        semantic_metadata=semantic if semantic is not None else {
            "period_hours": 0.5,
            # What the PSMs wrote before S-中1: the ledger replaces it.
            "timezone": "Europe/London",
            "calendar": "fixed_365_day_local_periods",
        },
    )
    for period in range(4):
        ledger.record_period(_period(period))
    ledger.close()
    return database


def _stored_metadata(database: Path) -> dict[str, object]:
    with closing(sqlite3.connect(database)) as connection:
        return {key: json.loads(value) for key, value in connection.execute(
            "SELECT key, value FROM metadata WHERE key NOT IN ('schema_version', 'trace_level')")}


def _relabel_as_legacy(database: Path) -> None:
    """Make a ledger look like one written before S-中1 (label Europe/London)."""

    with closing(sqlite3.connect(database)) as connection:
        for key, value in LEGACY_LEDGER_CLOCK.items():
            connection.execute("UPDATE metadata SET value=? WHERE key=?", (json.dumps(value), key))
        connection.commit()
    metadata_path = database.parent / "metadata.json"
    if metadata_path.is_file():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        payload["semantic_metadata"].update(LEGACY_LEDGER_CLOCK)
        metadata_path.write_text(json.dumps(payload), encoding="utf-8")


class ModelClockTests(unittest.TestCase):
    """S-中1: one clock rule (UTC, fixed 365-day year) for ledger, read models and exports."""

    def test_period_start_is_utc_on_a_365_day_year(self) -> None:
        self.assertEqual(period_start_iso(2025, 0), "2025-01-01T00:00:00Z")
        # The swap-data case: 1 July, period 8,720 is 16:00 UTC (17:00 in London).
        self.assertEqual(period_start_iso(2025, 8720), "2025-07-01T16:00:00Z")
        self.assertEqual(period_start_iso(2025, 17_520), "2026-01-01T00:00:00Z")
        # A leap model year has no 29 February: day 59 is 1 March, and the
        # year still ends at 1 January of the next year.
        self.assertEqual(period_start_iso(2028, 58 * 48 + 47), "2028-02-28T23:30:00Z")
        self.assertEqual(period_start_iso(2028, 59 * 48), "2028-03-01T00:00:00Z")
        self.assertEqual(period_start_iso(2028, 17_519), "2028-12-31T23:30:00Z")
        self.assertEqual(period_start_iso(2028, 17_520), "2029-01-01T00:00:00Z")
        self.assertEqual(period_start_iso(2025, 25, 1.0), "2025-01-02T01:00:00Z")

    def test_legacy_label_is_reported_on_the_utc_clock(self) -> None:
        legacy = ledger_clock(dict(LEGACY_LEDGER_CLOCK))
        self.assertEqual(legacy["timezone"], "UTC")
        self.assertEqual(legacy["calendar"], MODEL_CALENDAR)
        self.assertTrue(legacy["clock_label_corrected"])
        self.assertIn("Europe/London", legacy["clock_note"])
        current = ledger_clock({"timezone": "UTC", "calendar": MODEL_CALENDAR})
        self.assertFalse(current["clock_label_corrected"])
        self.assertNotIn("clock_note", current)
        self.assertFalse(ledger_clock({})["clock_label_corrected"])

    def test_ledger_records_the_utc_clock_whatever_the_psm_supplies(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = _ledger(Path(folder))
            stored = _stored_metadata(database)
            timeline = query_dispatch_timeline(database, year=2025, resolution="half_hour", limit=4)
            stress = query_stress_events(database, year=2025)
        self.assertEqual(stored["timezone"], "UTC")
        self.assertEqual(stored["calendar"], MODEL_CALENDAR)
        self.assertEqual(timeline["timezone"], "UTC")
        self.assertFalse(timeline["clock_label_corrected"])
        self.assertEqual(timeline["items"][1]["timestamp_start"], "2025-01-01T00:30:00Z")
        self.assertEqual(timeline["items"][1]["timestamp_end"], "2025-01-01T01:00:00Z")
        self.assertEqual(stress["timezone"], "UTC")

    def test_a_ledger_written_before_the_fix_reads_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = _ledger(Path(folder))
            _relabel_as_legacy(database)
            timeline = query_dispatch_timeline(database, year=2025, resolution="half_hour", limit=4)
            # Resuming keeps the ledger's immutable label instead of refusing it.
            ledger = create_market_ledger(
                database, "full", semantic_metadata={"period_hours": 0.5},
            )
            ledger.close()
            stored = _stored_metadata(database)
        self.assertEqual(timeline["timezone"], "UTC")
        self.assertTrue(timeline["clock_label_corrected"])
        self.assertIn("Europe/London", timeline["clock_note"])
        self.assertEqual(timeline["items"][0]["timestamp_start"], "2025-01-01T00:00:00Z")
        self.assertEqual(stored["timezone"], "Europe/London")

    def test_flat_replay_export_carries_the_utc_period_start(self) -> None:
        from gridform_core.replay_export import _model_clock, _write_flat

        with tempfile.TemporaryDirectory() as folder:
            database = _ledger(Path(folder))
            target = Path(folder) / "export.csv"
            rows = _write_flat(database, target, "csv", " WHERE year=?", (2025,))
            with target.open(encoding="utf-8", newline="") as handle:
                exported = list(csv.DictReader(handle))
            with closing(sqlite3.connect(database)) as connection:
                clock = _model_clock({key: json.loads(value) for key, value in connection.execute(
                    "SELECT key, value FROM metadata WHERE key IN ('timezone', 'calendar', 'period_hours')")})
        self.assertEqual(rows, 4)
        self.assertEqual(list(exported[0])[-1], "period_start_utc")
        self.assertEqual([row["period_start_utc"] for row in exported][:2],
                         ["2025-01-01T00:00:00Z", "2025-01-01T00:30:00Z"])
        self.assertEqual(clock["timezone"], "UTC")
        self.assertEqual(clock["period_start_column"], "period_start_utc")

    def test_psms_no_longer_label_the_clock_europe_london(self) -> None:
        for relative in ("gridform_core/builtin/scheme_c_1000twh/scheme_c_native_psm.py",
                         "gridform_core/perfect_foresight_psm.py", "gridform_core/market_replay.py"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn('"Europe/London"', text, relative)
            self.assertNotIn("fixed_365_day_local_periods", text, relative)


class _MappingFixture:
    """An independent copy of an empty BASE pack and a mapping service (as tests.test_data_mapping)."""

    def setUp(self) -> None:  # noqa: D401 - unittest hook
        import threading

        from backend.data_mapping import DataMappingService
        from backend.data_pack_clone import clone_data_pack, manifest_sha256
        from gridform_core.catalog import DATASET_SLOTS

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)  # type: ignore[attr-defined]
        self.root = Path(self.temp.name)
        packs = self.root / "packs"
        source = packs / "base"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text(json.dumps({
            "schema_version": "value.data-pack/v1", "id": "base", "name": "base", "bindings": {}}))
        copied = clone_data_pack("base", {"schema_version": "value.data-pack-clone-request/v1",
            "name": "independent", "source_manifest_sha256": manifest_sha256(source / "manifest.json")},
            packs_root=packs, minimum_free_space_bytes=0)["data_pack"]
        self.pack_id = copied["id"]
        self.pack = packs / self.pack_id
        self.manifest_sha256 = manifest_sha256
        self.service = DataMappingService(packs_root=packs, staging_root=self.root / "staging",
            projects_root=self.root / "projects", trash_root=self.root / "trash",
            dataset_slots=DATASET_SLOTS, lifecycle_lock=threading.RLock())

    def stage(self, raw: bytes, role: str = "market.france.price") -> dict:
        return self.service.stage(self.pack_id, role, raw, "mine.csv", self.manifest_sha256(self.pack / "manifest.json"))

    def preview(self, stage: dict, *, source_unit: str = "GBP/MWh", target_unit: str = "GBP/MWh", **extra) -> dict:
        return self.service.preview(stage["stage_id"], {
            "schema_version": "value.data-mapping-preview-request/v1",
            "source_sha256": stage["source_sha256"], "target_manifest_sha256": stage["target_manifest_sha256"],
            "columns": [{"source": "price", "target": "value", "source_unit": source_unit, "target_unit": target_unit}],
            **extra})

    def commit(self, review: dict, **extra) -> dict:
        return self.service.commit(review["review_id"], {
            "schema_version": "value.data-mapping-commit-request/v1",
            **{key: review[key] for key in ("source_sha256", "spec_sha256", "normalized_sha256", "target_manifest_sha256")},
            **extra})


def _stamps(count: int, *, start: str = "2025-01-01 00:00", step_minutes: int = 30, fmt: str = "%Y-%m-%d %H:%M") -> list[str]:
    import datetime as dt

    first = dt.datetime.fromisoformat(start)
    return [(first + dt.timedelta(minutes=step_minutes * index)).strftime(fmt) for index in range(count)]


def _timed_csv(stamps: list[str], value: str = "70") -> bytes:
    return ("time,price\n" + "".join(f"{stamp},{value}\n" for stamp in stamps)).encode()


class ClockNoteTests(_MappingFixture, unittest.TestCase):
    """S-中2: the review and the pack validation say what the reader does with the length."""

    def test_plan_matches_align_clock_on_the_lengths_users_bring(self) -> None:
        import numpy as np

        from gridform_core.series_reader import DECLARED, STRICT, SeriesSpec, align_clock, clock_alignment

        cases = [
            ("market.france.price", {}, 8760, True),
            ("market.france.price", {}, 17_568, True),
            ("market.france.price", {}, 8784, True),
            ("market.france.price", {}, 17_000, True),
            ("market.france.price", {}, 20_000, True),
            ("market.france.profile", {"interval_minutes": 30}, 8760, True),
            ("demand.real", {"interval_minutes": 30}, 17_568, False),
        ]
        for role, binding, rows, cyclic in cases:
            with self.subTest(role=role, rows=rows):
                spec = SeriesSpec.from_binding(role, binding)
                plan = clock_alignment(rows, 17_520, spec, cyclic_default=cyclic)
                aligned = align_clock(np.arange(float(rows)), 17_520, spec, mode=DECLARED, cyclic_default=cyclic)
                self.assertEqual(len(aligned), 17_520)
                if plan.hourly_doubled:
                    self.assertEqual(aligned[1], 0.0)
                    self.assertEqual(aligned[2], 1.0)
                if plan.leap_day_removed and not plan.energy_rescaled:
                    first = 2832 if plan.hourly_doubled else 2832
                    self.assertEqual(aligned[first], 1440.0 if plan.hourly_doubled else 2880.0)
                if plan.wrapped_periods:
                    self.assertEqual(aligned[17_520 - plan.wrapped_periods], 0.0)
                    self.assertEqual(aligned[-1], float(plan.wrapped_periods - 1))
                if plan.ignored_periods:
                    self.assertEqual(aligned[-1], 17_519.0)
        self.assertIsNone(clock_alignment(17_520, 17_520, SeriesSpec.from_binding("market.france.price", {})).describe())
        refused = clock_alignment(17_000, 17_520, SeriesSpec.from_binding("profiles.vre_solar", {"interval_minutes": 30}),
                                  strictness=STRICT, cyclic_default=False)
        self.assertIn("GF_DATA_SHORT_SERIES", refused.describe())

    def test_hourly_and_leap_year_prices_are_described_as_read(self) -> None:
        hourly = self.preview(self.stage(_timed_csv(_stamps(8760, step_minutes=60))),
                              timestamp={"column": "time", "time_zone": "UTC"})
        self.assertTrue(hourly["valid"], hourly["errors"])
        text = " ".join(hourly["warnings"])
        self.assertIn("each hour is used for two half-hour periods", text)
        self.assertNotIn("cyclically", text)
        self.assertTrue(hourly["clock"]["hourly_doubled"])
        self.assertEqual(hourly["acknowledgements_required"], [])
        leap = self.preview(self.stage(_timed_csv(_stamps(17_568, start="2024-01-01 00:00"))),
                            timestamp={"column": "time", "time_zone": "UTC"})
        self.assertIn("29 February is removed", " ".join(leap["warnings"]))
        self.assertTrue(leap["clock"]["leap_day_removed"])
        longer = self.preview(self.stage(_timed_csv(_stamps(20_000))))
        self.assertIn("the last 2,480 are ignored", " ".join(longer["warnings"]))

    def test_pack_validation_uses_the_same_note(self) -> None:
        from gridform_core.catalog import DATASET_SLOTS
        from gridform_core.data_pack_validation import validate_data_pack

        folder = self.root / "pack"
        folder.mkdir()
        (folder / "price.csv").write_text("value\n" + "70\n" * 8760)
        import hashlib

        digest = hashlib.sha256((folder / "price.csv").read_bytes()).hexdigest()
        manifest = {"bindings": {"market.france.price": {"uri": "price.csv", "format": "csv", "sha256": digest,
                                                          "csv_header": True, "csv_column": "value"}}}
        slots = [slot for slot in DATASET_SLOTS if slot["role"] == "market.france.price"]
        report = validate_data_pack(folder, manifest, slots, layers=False)
        warnings = report["bindings"][0]["warnings"]
        self.assertTrue(any("each hour is used for two half-hour periods" in item for item in warnings), warnings)
        self.assertFalse(any("cyclically" in item for item in warnings))
        self.assertTrue(report["bindings"][0]["details"]["clock_alignment"]["hourly_doubled"])


class DateOrderTests(_MappingFixture, unittest.TestCase):
    """S-中3: day/month dates (02/01/2025) are read in the right order, or the report says why not."""

    def test_uk_day_month_dates_are_detected_and_kept(self) -> None:
        stamps = _stamps(17_520, fmt="%d/%m/%Y %H:%M")
        review = self.preview(self.stage(_timed_csv(stamps)), timestamp={"column": "time", "time_zone": "UTC"})
        self.assertTrue(review["valid"], review["errors"])
        self.assertEqual(review["timestamp"]["problem_count"], 0)
        self.assertEqual(review["timestamp"]["date_order"], "day_first")
        self.assertIn("first field above 12", review["timestamp"]["date_order_basis"])
        binding = self.commit(review)["binding"]
        self.assertEqual(binding["timestamp_date_order"], "day_first")
        from gridform_core.data_validation_layers import evaluate_layers

        manifest = json.loads((self.pack / "manifest.json").read_text())
        codes = [row["code"] for row in evaluate_layers(self.pack, manifest)["chronology"]["findings"]]
        self.assertNotIn("GF_DATA_TIMESTAMPS", codes)

    def test_month_day_dates_and_a_wrong_declared_order(self) -> None:
        us = self.preview(self.stage(_timed_csv(_stamps(17_520, fmt="%m/%d/%Y %H:%M"))),
                          timestamp={"column": "time", "time_zone": "UTC"})
        self.assertEqual((us["timestamp"]["problem_count"], us["timestamp"]["date_order"]), (0, "month_first"))
        wrong = self.preview(self.stage(_timed_csv(_stamps(17_520, fmt="%d/%m/%Y %H:%M"))),
                             timestamp={"column": "time", "time_zone": "UTC", "date_order": "month_first"})
        self.assertFalse(wrong["valid"])
        self.assertEqual(wrong["timestamp"]["date_order_basis"], "declared")
        self.assertTrue(any("DD/MM/YYYY order" in hint for hint in wrong["timestamp"]["hints"]))
        self.assertTrue(any("not a valid date in MM/DD/YYYY order" in row["problem"]
                            for row in wrong["timestamp"]["problems"]) or wrong["timestamp"]["problem_count"] > 100)

    def test_unknown_date_order_is_refused(self) -> None:
        from backend.data_mapping import DataMappingError

        with self.assertRaises(DataMappingError) as refused:
            self.preview(self.stage(_timed_csv(_stamps(48))),
                         timestamp={"column": "time", "time_zone": "UTC", "date_order": "year_last"})
        self.assertEqual(refused.exception.code, "GF_MAPPING_TIMESTAMP")


class CsvDelimiterTests(_MappingFixture, unittest.TestCase):
    """S-低1: a semicolon or tab export gets a plain explanation, not a width error."""

    def test_semicolon_and_tab_files_are_named(self) -> None:
        from backend.data_mapping import DataMappingError

        for raw, name in ((b"time;price\n2025-01-01 00:00;70,5\n", "semicolon"),
                          (b"time;price\n2025-01-01 00:00;70.5\n", "semicolon"),
                          (b"time\tprice\n2025-01-01 00:00\t70.5\n", "tab")):
            with self.subTest(raw=raw), self.assertRaises(DataMappingError) as refused:
                self.stage(raw)
            self.assertEqual(refused.exception.code, "GF_MAPPING_CSV")
            self.assertIn(f"looks {name}-separated", str(refused.exception))
            self.assertIn("comma-separated", str(refused.exception))
        # A comma CSV whose header merely contains a semicolon is read as before.
        self.assertEqual(self.stage(b"time,price;eur\n2025-01-01 00:00,70\n")["source_columns"], ["time", "price;eur"])


class CoverageTests(_MappingFixture, unittest.TestCase):
    """S-低2 and report section 7.3: coverage short of a year and the data year are reported and confirmed."""

    def test_short_series_needs_an_explicit_acknowledgement(self) -> None:
        from backend.data_mapping import SHORT_SERIES_ACKNOWLEDGEMENT, DataMappingError

        stage = self.stage(_timed_csv(_stamps(17_000, start="2023-01-01 00:00")))
        review = self.preview(stage, timestamp={"column": "time", "time_zone": "UTC"}, model_start_year=2025)
        self.assertTrue(review["valid"], review["errors"])
        warnings = " ".join(review["warnings"])
        self.assertIn("GF_DATA_TIMESTAMP_COVERAGE", warnings)
        self.assertIn("the last 520 periods (10.8 days) are filled by repeating the series from its start", warnings)
        self.assertIn("GF_DATA_TIMESTAMP_YEAR: the timestamps are in 2023; the Study's first model year is 2025", warnings)
        self.assertEqual(review["timestamp"]["coverage"]["data_years"], [2023])
        self.assertFalse(review["timestamp"]["coverage"]["full_year"])
        self.assertEqual([item["code"] for item in review["acknowledgements_required"]], [SHORT_SERIES_ACKNOWLEDGEMENT])
        with self.assertRaises(DataMappingError) as refused:
            self.commit(review)
        self.assertEqual(refused.exception.code, "GF_MAPPING_ACKNOWLEDGEMENT")
        binding = self.commit(review, acknowledged=[SHORT_SERIES_ACKNOWLEDGEMENT])["binding"]
        self.assertEqual(binding["timestamp_column"], "time")

    def test_short_series_without_timestamps_is_acknowledged_too(self) -> None:
        review = self.preview(self.stage(b"price\n" + b"70\n" * 17_000))
        self.assertTrue(any("filled by repeating the series" in item for item in review["warnings"]))
        self.assertEqual(len(review["acknowledgements_required"]), 1)

    def test_full_year_in_the_model_year_has_no_year_note(self) -> None:
        review = self.preview(self.stage(_timed_csv(_stamps(17_520))), timestamp={"column": "time", "time_zone": "UTC"},
                              model_start_year=2025)
        self.assertFalse([item for item in review["warnings"] if item.startswith("GF_DATA_TIMESTAMP_")])
        self.assertEqual(review["timestamp"]["coverage"]["span_days"], 365.0)
        self.assertEqual(review["acknowledgements_required"], [])


class RowNumberAndReportTests(_MappingFixture, unittest.TestCase):
    """S-低3 (one row numbering) and S-低4 (the whole-file report includes the timestamp check)."""

    def test_timestamp_rows_name_data_row_and_csv_line(self) -> None:
        stamps = _stamps(17_520)
        stamps[3] = stamps[2]
        review = self.preview(self.stage(_timed_csv(stamps)), timestamp={"column": "time", "time_zone": "UTC"})
        problem = review["timestamp"]["problems"][0]
        self.assertEqual((problem["data_row"], problem["csv_line"], problem["row"]), (4, 5, 5))
        self.assertEqual(problem["problem"], "duplicate of data row 3 (CSV line 4)")
        self.assertIn("data_row", review["timestamp"]["row_numbering"])
        # S-低4: the whole-file report says failed beside the failed timestamp check.
        self.assertEqual(review["validation"]["status"], "failed")
        self.assertEqual(review["validation"]["timestamp_check"]["status"], "failed")
        self.assertTrue(any("GF_DATA_TIMESTAMPS" in item for item in review["validation"]["errors"]))

    def test_cell_errors_use_the_same_pair(self) -> None:
        review = self.preview(self.stage(b"price\n" + b"70\n" * 49 + b"x\n" + b"70\n" * 17_470))
        self.assertTrue(any(item.startswith("Row 50 (CSV line 51)") for item in review["errors"]), review["errors"])

    def test_passed_timestamp_check_is_in_the_report(self) -> None:
        review = self.preview(self.stage(_timed_csv(_stamps(17_520))), timestamp={"column": "time", "time_zone": "UTC"})
        self.assertEqual(review["validation"]["timestamp_check"]["status"], "passed")
        self.assertNotEqual(review["validation"]["status"], "failed")


class FxDeclarationTests(_MappingFixture, unittest.TestCase):
    """S-低6: fx_basis is one of the editor's three values; a price year other than the model's base is noted."""

    def eur(self, fx: dict) -> dict:
        stage = self.stage(b"price\n" + b"70\n" * 17_520)
        return self.preview(stage, source_unit="EUR/MWh", fx=fx)

    def test_fx_basis_is_an_enumeration(self) -> None:
        from backend.data_mapping import FX_BASES, DataMappingError

        self.assertEqual(FX_BASES, ("annual average", "monthly average", "fixed rate"))
        frontend = (ROOT / "app/features/data/csvMappingFx.ts").read_text(encoding="utf-8")
        self.assertIn('FX_BASES = ["annual average", "monthly average", "fixed rate"]', frontend)
        with self.assertRaises(DataMappingError) as refused:
            self.eur({"eur_per_gbp": 1.17, "fx_basis": "my bank's rate", "price_year": 2025})
        self.assertEqual(refused.exception.code, "GF_MAPPING_FX")

    def test_price_year_other_than_the_base_is_noted(self) -> None:
        from backend.data_mapping import MODEL_PRICE_BASE_YEAR

        restart = json.loads((ROOT / "gridform_core/data/thermal/value_thermal_restart_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(MODEL_PRICE_BASE_YEAR, restart["price_base"]["to_year"])
        old = self.eur({"eur_per_gbp": 1.17, "fx_basis": "annual average", "price_year": 2015})
        self.assertTrue(old["valid"], old["errors"])
        self.assertTrue(any(item.startswith("GF_MAPPING_PRICE_YEAR: the prices are declared in 2015 money")
                            for item in old["warnings"]), old["warnings"])
        same = self.eur({"eur_per_gbp": 1.17, "fx_basis": "annual average", "price_year": 2025})
        self.assertFalse(any("GF_MAPPING_PRICE_YEAR" in item for item in same["warnings"]))


if __name__ == "__main__":
    unittest.main()
