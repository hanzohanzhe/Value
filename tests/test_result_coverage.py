"""P0-9 S5: one annual-coverage rule for every result view (F3-02, G1-10)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from tests.local_api_harness import start_local_api
from tests.test_prompt102_zonal_results_api import _write_fixture
from gridform_core.result_coverage import (
    ANNUAL_REASON_ALIASES, NON_ANNUAL_MODES, REASON_BOUNDARY, REASON_CANCELLED, REASON_COMPLETE,
    REASON_FAILED, REASON_IN_PROGRESS, REASON_NON_ANNUAL, REASON_YEAR_SET, legacy_reason, result_coverage,
    year_bounds_from_rows,
)

FULL = (0, 17519, 17520)


def status(state: str = "completed", mode: str = "two_year", start: int = 2025, end: int = 2026, periods: int = 17520) -> dict:
    return {"status": state, "mode": mode, "run_policy": {"start_year": start, "end_year": end, "periods_per_year": periods}}


class ResultCoverageTests(unittest.TestCase):
    def test_hand_computed_table(self) -> None:
        # (status, bounds, expected annual_status, reason, coverage percent)
        cases = (
            # 1 complete two-year run
            (status(), {2025: FULL, 2026: FULL}, "complete", REASON_COMPLETE, 100.0),
            # 2 two_year_smoke: 2 periods a year is never annual, whatever the bounds
            (status(mode="two_year_smoke", periods=2), {2025: (0, 1, 2), 2026: (0, 1, 2)}, "non_annual", REASON_NON_ANNUAL, 0.0),
            # 3 value_101_day (missing from one of the old copies, G1-10)
            (status(mode="value_101_day", end=2025, periods=48), {2025: (0, 47, 48)}, "non_annual", REASON_NON_ANNUAL, 0.3),
            # 4 still running: not yet a result
            (status("running"), {2025: FULL, 2026: (0, 99, 100)}, "in_progress", REASON_IN_PROGRESS, 50.3),
            # 5 cancelled full-year run at 16.6 % of one year (the review's example)
            (status("cancelled", end=2025), {2025: (0, 2907, 2908)}, "partial", REASON_CANCELLED, 16.6),
            # 6 failed in the second year
            (status("failed"), {2025: FULL, 2026: (0, 8759, 8760)}, "partial", REASON_FAILED, 75.0),
            # 7 completed but a declared year is missing from the ledger
            (status(), {2025: FULL}, "invalid", REASON_YEAR_SET, 50.0),
            # 8 completed, years match, one year has a gap in its periods
            (status(), {2025: FULL, 2026: (0, 17519, 17000)}, "partial", REASON_BOUNDARY, 98.5),
        )
        for index, (run, bounds, expected, reason, percent) in enumerate(cases, 1):
            with self.subTest(case=index):
                coverage = result_coverage(run, bounds)
                self.assertEqual(coverage["annual_status"], expected)
                self.assertEqual(coverage["reason_code"], reason)
                self.assertEqual(coverage["coverage_percent"], percent)
                self.assertEqual(coverage["schema_version"], "value.result-coverage/v1")

    def test_cancelled_reason_code_is_locked(self) -> None:
        coverage = result_coverage(status("cancelled", end=2025), {2025: FULL})
        self.assertEqual((coverage["annual_status"], coverage["reason_code"]), ("partial", "run_cancelled_before_full_coverage"))
        # an archived run is judged by the status it was archived from
        archived = dict(status("archived"), archived_from_status="cancelled")
        self.assertEqual(result_coverage(archived, {2025: FULL, 2026: FULL})["reason_code"], REASON_CANCELLED)
        self.assertEqual(result_coverage(dict(status("archived")), {2025: FULL, 2026: FULL})["annual_status"], "complete")

    def test_non_annual_modes_come_from_the_run_policies(self) -> None:
        self.assertEqual(NON_ANNUAL_MODES, frozenset({"smoke", "two_year_smoke", "validation_24h", "validation_168h", "value_101_day", "tutorial"}))
        # an unknown mode without a policy is not provably annual
        self.assertEqual(result_coverage({"status": "completed", "mode": "novel"}, {2025: FULL})["annual_status"], "non_annual")

    def test_per_year_rows_and_legacy_aliases(self) -> None:
        coverage = result_coverage(status("cancelled", end=2025), year_bounds_from_rows([(2025, 0, 2907, 2908)]))
        (row,) = coverage["years"]
        self.assertEqual((row["first_period"], row["last_period"], row["period_count"], row["complete"]), (0, 2907, 2908, False))
        self.assertAlmostEqual(row["coverage_fraction"], 2908 / 17520)
        self.assertEqual(legacy_reason(coverage), "annual_evidence_withheld_for_nonannual_run")
        self.assertEqual(ANNUAL_REASON_ALIASES[REASON_YEAR_SET], "vre_curtailment_annual_year_set_invalid")


class CoverageOverHttpTests(unittest.TestCase):
    def test_network_annual_brief_and_run_detail_carry_the_same_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary) / "runs"
            root = runs / "cancelled-run"
            root.mkdir(parents=True)
            (root / "status.json").write_text(json.dumps({
                "id": "cancelled-run", "status": "cancelled", "mode": "full",
                "run_policy": {"start_year": 2025, "end_year": 2025, "periods_per_year": 17520},
            }), encoding="utf-8")
            _write_fixture(root / "model-output" / "market" / "market.sqlite", "summary")
            with patch.object(server, "RUNS_ROOT", runs):
                api = start_local_api(data_home=Path(temporary), patch_state_roots=False)
                _httpd, origin, _session = api.start()
                try:
                    brief = json.loads(urllib.request.urlopen(origin + "/api/runs/cancelled-run/network-redispatch/annual", timeout=10).read())
                    detail = json.loads(urllib.request.urlopen(origin + "/api/runs/cancelled-run", timeout=10).read())
                finally:
                    api.stop()
        self.assertEqual(brief["coverage"]["annual_status"], "partial")
        self.assertEqual(brief["coverage"]["reason_code"], "run_cancelled_before_full_coverage")
        self.assertTrue(brief["years"], "the brief itself is still returned")
        self.assertEqual(detail["result_coverage"]["annual_status"], "partial")
        self.assertEqual(detail["result_coverage"]["coverage_source"], "market_ledger")



def _wal_ledger(database: Path, years: dict[int, int]) -> sqlite3.Connection:
    """A market ledger in WAL mode with a non-empty -wal file, as while a Run writes it."""

    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE period_summary (year INTEGER, period INTEGER)")
    for year, periods in years.items():
        connection.executemany("INSERT INTO period_summary VALUES (?, ?)", ((year, period) for period in range(periods)))
    connection.commit()
    return connection


class LedgerCopyTests(unittest.TestCase):
    """Review response: a Run-detail poll never copies a live WAL ledger."""

    def test_running_run_detail_does_not_copy_the_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "running-run"
            database = root / "model-output" / "market" / "market.sqlite"
            writer = _wal_ledger(database, {2025: 17520, 2026: 300})
            try:
                self.assertGreater(database.with_name("market.sqlite-wal").stat().st_size, 0)
                run = dict(status("running"), results=[{"year": 2025}])
                with patch("gridform_core.market_ledger.shutil.copyfile") as copyfile:
                    for _ in range(3):
                        coverage = server.run_result_coverage(root, run)
                self.assertEqual(copyfile.call_count, 0)
                self.assertEqual(coverage["annual_status"], "in_progress")
                self.assertEqual(coverage["coverage_source"], "status_results")
                # the finished year keeps its Complete year pill from status.json
                self.assertEqual([(row["year"], row["complete"]) for row in coverage["years"]], [(2025, True)])
                # a non-annual Run does not open its ledger either
                smoke = dict(status("completed", mode="two_year_smoke", periods=2), results=[{"year": 2025}])
                with patch("gridform_core.market_ledger.shutil.copyfile") as copyfile:
                    coverage = server.run_result_coverage(root, smoke)
                self.assertEqual(copyfile.call_count, 0)
                self.assertEqual(coverage["annual_status"], "non_annual")
                self.assertEqual(coverage["years"][0]["period_count"], 2)
            finally:
                writer.close()

    def test_terminal_ledger_bounds_are_cached_by_size_and_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "cancelled-run"
            database = root / "model-output" / "market" / "market.sqlite"
            writer = _wal_ledger(database, {2025: 2908})
            try:
                run = status("cancelled", end=2025)
                with patch("gridform_core.market_ledger.shutil.copyfile", wraps=shutil.copyfile) as copyfile:
                    first = server.run_result_coverage(root, run)
                    second = server.run_result_coverage(root, run)
                self.assertEqual(copyfile.call_count, 2, "one DB + WAL snapshot, then the cache")
                self.assertEqual(first, second)
                self.assertEqual(first["coverage_source"], "market_ledger")
                self.assertEqual(first["years"][0]["period_count"], 2908)
                writer.execute("INSERT INTO period_summary VALUES (2025, 2908)")
                writer.commit()
                third = server.run_result_coverage(root, run)
                self.assertEqual(third["years"][0]["period_count"], 2909, "a changed ledger is read again")
            finally:
                writer.close()


class RunningStageTests(unittest.TestCase):
    """Review response (P0-3 S8): the stage text never names a year after the end year."""

    def _present(self, completed: list[int]) -> str:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary)
            output = runs / "stage-run" / "model-output"
            output.mkdir(parents=True)
            (output / "module-events.jsonl").write_text("".join(
                json.dumps({"module_id": "value-annual-state-transition", "year": year, "action": "pipeline.complete_year"}) + "\n"
                for year in completed
            ), encoding="utf-8")
            with patch.object(server, "RUNS_ROOT", runs):
                return server.present_run(dict(status("running"), id="stage-run"))["current_stage"]

    def test_stage_names_the_next_declared_year_then_finishing(self) -> None:
        self.assertEqual(self._present([2025]), "Computing year 2026 (period-level progress not reported by this model)")
        self.assertEqual(self._present([2025, 2026]), "Finishing outputs after 2026")
        # without a declared policy the next year after the last finished one is named
        self.assertEqual(server.running_stage_text({"status": "running"}, {2030}), "Computing year 2031 (period-level progress not reported by this model)")

if __name__ == "__main__":
    unittest.main()
