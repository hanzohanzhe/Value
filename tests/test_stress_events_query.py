"""P0-9 M7 (spec 4.4, decision A2): the full-year stress-event read model."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from gridform_core.market_replay import STRESS_EVENT_PAGE_LIMIT, query_stress_events


def _ledger(root: Path, *, with_table: bool = True) -> Path:
    database = root / "market.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE period_summary(year INTEGER, period INTEGER)")
        if with_table:
            schema = (Path(__file__).resolve().parents[1] / "gridform_core" / "data" / "contracts"
                      / "market-ledger-energy-balance-v1.schema.sql").read_text(encoding="utf-8")
            start = schema.index("CREATE TABLE IF NOT EXISTS stress_event")
            connection.executescript(schema[start:schema.index(";", start) + 1])
            # Inserted out of order: event_index order differs from start-period order,
            # and start periods 2, 10, 100 must sort numerically.
            rows = [
                (2025, 0, 100, 101, 2, 30.0, 0.0, 30.0, "native_corrected_full_node_v1"),
                (2025, 1, 2, 2, 1, 1.5, 1.5, 0.0, "native_corrected_full_node_v1"),
                (2025, 2, 10, 13, 4, 12.25, 2.0, 10.25, "native_corrected_full_node_v1"),
                (2026, 0, 5, 5, 1, 7.0, 0.0, 7.0, "native_corrected_full_node_v1"),
            ]
            connection.executemany("INSERT INTO stress_event VALUES(?,?,?,?,?,?,?,?,?)", rows)
    return database


class StressEventsQueryTests(unittest.TestCase):
    def test_full_year_events_are_paged_by_numeric_start_period(self):
        with tempfile.TemporaryDirectory() as directory:
            database = _ledger(Path(directory))
            page = query_stress_events(database, year=2025, limit=2, offset=0)
            self.assertEqual(page["status"], "recorded")
            self.assertEqual((page["total"], page["has_more"]), (3, True))
            self.assertEqual([item["start_period"] for item in page["items"]], [2, 10])
            self.assertEqual(page["stress_periods"], 7)
            self.assertAlmostEqual(page["shortfall_mwh"], 43.75)
            first = page["items"][0]
            self.assertEqual(first["start_timestamp"], "2025-01-01T01:00:00")
            self.assertEqual((first["periods"], first["event_type"]), (1, "stress"))
            second = query_stress_events(database, year=2025, limit=2, offset=2)
            self.assertEqual([item["start_period"] for item in second["items"]], [100])
            self.assertFalse(second["has_more"])
            self.assertEqual(query_stress_events(database, year=2026)["total"], 1)
            self.assertEqual(query_stress_events(database)["total"], 4)
            self.assertEqual(query_stress_events(database, limit=10_000)["limit"], STRESS_EVENT_PAGE_LIMIT)

    def test_a_ledger_without_the_table_is_not_recorded_not_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            page = query_stress_events(_ledger(Path(directory), with_table=False), year=2025)
            self.assertEqual((page["status"], page["total"], page["items"]), ("not_recorded", 0, []))
            self.assertNotIn("stress_periods", page)

    def test_an_empty_table_is_recorded_with_no_events(self):
        with tempfile.TemporaryDirectory() as directory:
            database = _ledger(Path(directory))
            page = query_stress_events(database, year=2030)
            self.assertEqual((page["status"], page["total"], page["stress_periods"]), ("recorded", 0, 0))


if __name__ == "__main__":
    unittest.main()
