import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core.planning_index import materialize_planning_index
from gridform_core.v2.contracts import (
    ExpansionHeadroom, InvestmentDecision, MarketYearResult, OperatingState,
    PlanningAdmissionResult, PlanningAdvanceResult, PlanningProject, YearResult, YearState,
)


class PlanningIndexTests(unittest.TestCase):
    def test_expected_rows_reconcile_without_realised_failure_kpi(self):
        project = PlanningProject(
            "p", "P", "external", "solar", 25, 100, "Wales", "planning", "active",
            2025, 2027, "expected_capacity", 0.25,
        )
        operating = OperatingState(2025, (), (project,))
        advance = PlanningAdvanceResult(2025, operating, (project,), (), (), (), ())
        market = MarketYearResult("m", 2025, "p", "1", {}, {}, 0, 0, 0, 1, 0, 1, 0)
        investment = InvestmentDecision("i", 2025, "i", (), {})
        admission = PlanningAdmissionResult(2025, (), (), (project,), ())
        result = YearResult("r", 2025, advance, market, (), investment, admission, YearState(2026, (), (project,)))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.sqlite"
            summary = materialize_planning_index(path, (result,), run_id="run", project_revision="sha")
            self.assertEqual(summary["project_year_rows"], 1)
            self.assertEqual(summary["expected_capacity"][0]["declared_capacity_mw"], 100)
            self.assertEqual(summary["expected_capacity"][0]["probability_weighted_capacity_mw"], 25)
            self.assertEqual(summary["expected_capacity"][0]["realised_failure_count"], "not_applicable")
            self.assertEqual(summary["commissioning_diagnostics"][0]["commissioned_projects"], 0)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM project_year").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
