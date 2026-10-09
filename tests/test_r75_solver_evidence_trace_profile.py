"""R7-5: solver evidence of a summary-trace staged/zonal Run is not "invalid".

The authoritative v8 ledger keeps ``network_solver_diagnostics`` only under the
full trace profile, so a summary-trace Run has no per-period solver rows by
design. Before R7-5 the Network & redispatch read model still demanded a row
for every reconciled period and reported ``solver_diagnostics_missing_completed_period``
("Solver evidence invalid"). The read model now reports
``not_recorded_under_trace_profile``; a full-trace Run whose rows are missing
is still invalid. Read model only: no dispatch number changes.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core.market_ledger import SQLiteMarketLedger, validate_market_ledger_file
from gridform_core.zonal_results import (
    SOLVER_EVIDENCE_NOT_RECORDED_UNDER_TRACE_PROFILE,
    query_solver_validation_summary,
    query_zonal_annual_brief,
    zonal_workspace_capabilities,
)
from tests.test_prompt120_market_ledger_v8 import _full_trace_batch


def _write_v8(path: Path, trace_level: str, periods: int = 2) -> Path:
    ledger = SQLiteMarketLedger(path, trace_level=trace_level)
    for period in range(periods):
        ledger.record_period_batch(_full_trace_batch(period))
    ledger.close()
    return path


class SolverEvidenceTraceProfileTests(unittest.TestCase):
    def test_summary_trace_reports_not_recorded_under_trace_profile(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = _write_v8(Path(folder) / "market.sqlite", "summary")
            with closing(sqlite3.connect(database)) as connection:
                stored = connection.execute(
                    "SELECT COUNT(*) FROM network_solver_diagnostics"
                ).fetchone()[0]
                reconciled = connection.execute(
                    "SELECT COUNT(*) FROM zonal_period_accounting "
                    "WHERE accounting_status='reconciled'"
                ).fetchone()[0]
            validation = validate_market_ledger_file(database)
            summary = query_solver_validation_summary(database)
            year_summary = query_solver_validation_summary(database, year=2025)
            capabilities = zonal_workspace_capabilities(database)
            brief = query_zonal_annual_brief(database)

        self.assertEqual(stored, 0, "summary trace keeps no solver rows")
        self.assertEqual(reconciled, 2)
        self.assertTrue(validation["valid"], validation["errors"])
        for item in (
            summary,
            year_summary,
            capabilities["solver_validation_summary"],
            brief["solver_validation_summary"],
            brief["years"][0]["solver_validation_summary"],
        ):
            self.assertIsNotNone(item)
            self.assertEqual(
                item["evidence_status"],
                SOLVER_EVIDENCE_NOT_RECORDED_UNDER_TRACE_PROFILE,
            )
            self.assertEqual(item["evidence_errors"], [])
            self.assertEqual(item["study_status"], "NOT_RECORDED")
            self.assertEqual(item["annual_status"], "NOT_RECORDED")
            self.assertEqual(item["trace_level"], "summary")
            self.assertEqual(
                item["evidence_reason"],
                "per_period_solver_diagnostics_recorded_only_with_full_trace",
            )
            self.assertFalse(item["solver_validated"])
            self.assertEqual(item["row_count"], 0)

    def test_full_trace_with_complete_rows_stays_valid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = _write_v8(Path(folder) / "market.sqlite", "full")
            summary = query_solver_validation_summary(database)
        self.assertEqual(summary["evidence_status"], "valid")
        self.assertEqual(summary["evidence_errors"], [])
        self.assertEqual(summary["row_count"], 6)

    def test_full_trace_missing_rows_is_still_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = _write_v8(Path(folder) / "market.sqlite", "full")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "DELETE FROM network_solver_diagnostics WHERE period=1"
                )
                connection.commit()
            summary = query_solver_validation_summary(database)
            validation = validate_market_ledger_file(database)

        self.assertEqual(summary["evidence_status"], "invalid")
        self.assertEqual(summary["study_status"], "solver_evidence_invalid")
        self.assertTrue(any(
            error.startswith("solver_diagnostics_missing_completed_period:")
            for error in summary["evidence_errors"]
        ), summary["evidence_errors"])
        self.assertFalse(validation["valid"])

    def test_full_trace_with_no_rows_at_all_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = _write_v8(Path(folder) / "market.sqlite", "full")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("DELETE FROM network_solver_diagnostics")
                connection.commit()
            summary = query_solver_validation_summary(database)

        self.assertEqual(summary["evidence_status"], "invalid")
        self.assertIn(
            "solver_diagnostics_missing_completed_period:2025:0:2025:0",
            summary["evidence_errors"],
        )

    def test_summary_trace_with_full_only_rows_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            full = _write_v8(Path(folder) / "full.sqlite", "full")
            database = _write_v8(Path(folder) / "summary.sqlite", "summary")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("ATTACH DATABASE ? AS full_ledger", (str(full),))
                connection.execute(
                    "INSERT INTO network_solver_diagnostics "
                    "SELECT * FROM full_ledger.network_solver_diagnostics"
                )
                connection.commit()
            summary = query_solver_validation_summary(database)

        self.assertEqual(summary["evidence_status"], "invalid")
        self.assertIn(
            "summary_contains_full_only_rows:network_solver_diagnostics:6",
            summary["evidence_errors"],
        )


if __name__ == "__main__":
    unittest.main()
