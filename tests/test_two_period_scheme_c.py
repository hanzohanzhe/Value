import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction"
HAS_RUNTIME_DEPS = all(
    importlib.util.find_spec(name) is not None
    for name in ("numpy", "pandas", "xarray", "netCDF4")
)
MODULES = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
}


@unittest.skipUnless(sys.version_info[:2] == (3, 10), "VALUE parity requires Python 3.10")
@unittest.skipUnless((PACK / "manifest.json").is_file(), "local verified data pack not installed")
@unittest.skipUnless(HAS_RUNTIME_DEPS, "VALUE scientific dependencies are not installed")
class TwoPeriodSchemeCExecutionTests(unittest.TestCase):
    def test_two_period_run_executes_every_selected_stage(self):
        from gridform_core.builtin.scheme_c_1000twh.modular_run import (
            ModularRunRequest,
            run_modular_scheme_c,
        )

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            console = io.StringIO()
            with redirect_stdout(console), redirect_stderr(console):
                result = run_modular_scheme_c(
                    ModularRunRequest(
                        pack_root=PACK,
                        output_dir=output,
                        module_ids=MODULES,
                        start_year=2025,
                        end_year=2025,
                        periods=2,
                        scenario="existing_decarb_base",
                        explicit_reference_comparison=True,
                    )
                )
            events = [
                json.loads(line)
                for line in (output / "module-events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            planning_database = output / "planning" / "pipeline.sqlite"
            planning_summary = json.loads(
                (output / "planning" / "summary.json").read_text(encoding="utf-8")
            )
            with closing(sqlite3.connect(planning_database)) as connection:
                planning_projects = connection.execute(
                    "SELECT COUNT(*) FROM projects"
                ).fetchone()[0]
                planning_events = connection.execute(
                    "SELECT COUNT(*) FROM events"
                ).fetchone()[0]
                planning_event_types = {
                    row[0]
                    for row in connection.execute("SELECT DISTINCT event_type FROM events")
                }
            planning_database_bytes = planning_database.stat().st_size
            run_context = json.loads(
                (output / "scheme-c-run-context.json").read_text(encoding="utf-8")
            )
            legacy_session = json.loads(
                (output / "legacy-config-session.json").read_text(encoding="utf-8")
            )
            execution_identity = json.loads(
                (output / "execution-identity.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["runtime"]["periods_per_year"], 2)
        self.assertEqual(len(result["system_cost_history"]), 1)
        completed = {(row["module_id"], row["action"]) for row in events}
        self.assertIn(("doctoral-reproduction-kernel-bridge", "psm.complete"), completed)
        self.assertIn((MODULES["investment"], "investment.complete"), completed)
        self.assertIn((MODULES["pipeline"], "pipeline.complete_year"), completed)
        self.assertIn((MODULES["vre_cap"], "vre_cap.complete"), completed)
        self.assertIn((MODULES["storage_cap"], "storage_cap.complete"), completed)
        self.assertGreater(planning_projects, 0)
        self.assertGreater(planning_events, planning_projects)
        self.assertIn("source_imported", planning_event_types)
        self.assertTrue(planning_summary["years"][0]["reconciled"])
        self.assertLess(planning_database_bytes, 32 * 1024 * 1024)
        self.assertTrue(legacy_session["restored"])
        self.assertEqual(
            run_context["context_sha256"],
            execution_identity["scheme_c_run_context_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
