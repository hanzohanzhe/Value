"""R4 (DECISIONS A27): the reproduce-role defects of the final four-role report.

Each test names the defect it covers (R-中n / R-低n / T-低n).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from gridform_core.planning_index import (
    SCHEMA_VERSION,
    materialize_planning_index,
    planning_summary_payload,
    query_index_projects,
    query_index_summary,
)
from gridform_core.v2.contracts import (
    InvestmentDecision, MarketYearResult, OperatingState, PlanningAdmissionResult,
    PlanningAdvanceResult, PlanningProject, YearResult, YearState,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "runs"


def _project(project_id: str, status: str, year: int, technology: str = "solar", region: str = "Wales") -> PlanningProject:
    return PlanningProject(
        project_id, project_id.upper(), "external", technology, 25, 100, region, "planning", status,
        year, year + 1, "expected_capacity", 0.25,
    )


def _year_result(year: int, active: tuple[PlanningProject, ...], commissioned: tuple[PlanningProject, ...]) -> YearResult:
    operating = OperatingState(year, (), active)
    advance = PlanningAdvanceResult(year, operating, active, commissioned, (), (), ())
    market = MarketYearResult("m", year, "p", "1", {}, {}, 0, 0, 0, 1, 0, 1, 0)
    investment = InvestmentDecision("i", year, "i", (), {})
    admission = PlanningAdmissionResult(year, (), (), active, ())
    return YearResult("r", year, advance, market, (), investment, admission, YearState(year + 1, (), active))


def _two_year_index(folder: Path) -> tuple[Path, dict[str, object]]:
    """Project p1 is active in 2025 and commissioned in 2026: two project-year rows."""

    path = folder / "project-index.sqlite"
    first = _year_result(2025, (_project("p1", "active", 2025), _project("p2", "active", 2025, "wind", "Scotland")), ())
    second = _year_result(2026, (_project("p2", "active", 2025, "wind", "Scotland"),), (_project("p1", "commissioned", 2025),))
    summary = materialize_planning_index(path, (first, second), run_id="run", project_revision="sha")
    return path, summary


class PlanningSummaryYearsTests(unittest.TestCase):
    """R-中1: the planning panel reads years[]; the v2 index summary.json has none."""

    def test_v2_index_summary_has_no_years_and_the_payload_adds_them(self):
        with tempfile.TemporaryDirectory() as folder:
            path, summary = _two_year_index(Path(folder))
            self.assertEqual(summary["schema_version"], SCHEMA_VERSION)
            self.assertNotIn("years", summary)
            payload = planning_summary_payload(json.loads(json.dumps(summary)), path)
            self.assertEqual([row["year"] for row in payload["years"]], [2025, 2026])
            # The index-level fields stay alongside the per-year rows.
            self.assertEqual(payload["project_year_rows"], 4)
            first = payload["years"][0]
            self.assertEqual(first["kpis"]["active"]["projects"], 2)
            self.assertEqual(set(first["breakdowns"]["technology"]), {"solar", "wind"})
            self.assertEqual(set(first["breakdowns"]["region"]), {"Wales", "Scotland"})
            self.assertEqual(first["breakdowns"]["expected_completion_year"]["2026"]["projects"], 2)
            second = payload["years"][1]
            self.assertEqual(second["kpis"]["commissioned"]["projects"], 1)
            self.assertIn("event_type", second["cause_breakdowns"])

    def test_payload_without_summary_file_or_index(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing.sqlite"
            self.assertEqual(planning_summary_payload(None, missing)["years"], [])
            self.assertEqual(planning_summary_payload({"schema_version": SCHEMA_VERSION}, missing)["years"], [])
            path, _summary = _two_year_index(Path(folder))
            self.assertEqual(planning_summary_payload(None, path), query_index_summary(path))
            legacy = {"schema_version": "value.planning-ledger/v1", "years": [{"year": 2030}]}
            self.assertIs(planning_summary_payload(legacy, path), legacy)

    def test_server_answers_planning_summary_with_years(self):
        from tests.local_api_harness import start_local_api

        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            run = home / "runs" / "pre-fix-dynamic-full"
            shutil.copytree(FIXTURES / "pre-fix-dynamic-full", run)
            planning = run / "model-output" / "planning"
            planning.mkdir(parents=True)
            path, summary = _two_year_index(planning)
            (planning / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            with start_local_api(data_home=home) as (_httpd, origin, _token):
                try:
                    with urllib.request.urlopen(origin + "/api/runs/pre-fix-dynamic-full/planning/summary", timeout=30) as response:
                        status, payload = response.status, json.loads(response.read())
                except urllib.error.HTTPError as error:
                    status, payload = error.code, json.loads(error.read())
        self.assertEqual(status, 200, payload)
        self.assertEqual([row["year"] for row in payload["years"]], [2025, 2026])


if __name__ == "__main__":
    unittest.main()
