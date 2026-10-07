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


if __name__ == "__main__":
    unittest.main()
