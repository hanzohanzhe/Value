import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gridform_core.performance_profile import build_performance_profile


class PerformanceProfileTests(unittest.TestCase):
    def test_profiles_existing_evidence_without_double_counting_investment(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "model-output"
            (output / "market").mkdir(parents=True)
            (output / "checkpoints-v2").mkdir()
            (root / "status.json").write_text(json.dumps({
                "id": "run", "mode": "validation_24h", "status": "completed",
                "started_at": "2026-01-01T00:00:00+00:00", "finished_at": "2026-01-01T00:00:10+00:00",
            }), encoding="utf-8")
            (output / "performance.json").write_text(json.dumps({
                "phases_seconds": {"copied_project_composed_kernel": 9.0}
            }), encoding="utf-8")
            events = [
                {"year": 2025, "action": "pipeline.begin_year", "projects": 20},
                {"year": 2025, "action": "psm.complete", "duration_seconds": 7.0},
                {"year": 2025, "action": "investment.complete", "duration_seconds": 8.0, "assets": 5},
            ]
            (output / "module-events.jsonl").write_text(
                "\n".join(json.dumps(row) for row in events), encoding="utf-8"
            )
            (output / "orchestrator-events.jsonl").write_text(
                json.dumps({"year": 2025, "stage": "state_transition.apply", "duration_seconds": 0.1}),
                encoding="utf-8",
            )
            database = sqlite3.connect(output / "market" / "market.sqlite")
            database.execute("CREATE TABLE period_summary (year INTEGER, period INTEGER)")
            database.executemany("INSERT INTO period_summary VALUES (2025, ?)", [(1,), (2,)])
            database.commit()
            database.close()
            (output / "checkpoints-v2" / "state-2026.json").write_text("{}", encoding="utf-8")

            report = build_performance_profile(root)

            self.assertEqual(report["schema_version"], "value.performance-profile/v1")
            year = report["annual"]["2025"]
            self.assertEqual(year["stage_seconds"]["psm.complete"], 7.0)
            self.assertIn("inclusive parent span", year["investment_timing_semantics"])
            self.assertEqual(year["market_record_counts"]["period_summary"], 2)
            self.assertEqual(report["measurements"]["peak_memory_status"].split(":")[0], "UNKNOWN")
            self.assertFalse(report["change_impact"]["production_scientific_execution_changed"])


if __name__ == "__main__":
    unittest.main()
