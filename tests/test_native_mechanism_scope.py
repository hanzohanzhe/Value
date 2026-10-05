"""P0-9 S9 (F3-04): the native path does not model the capacity or the
decarbonisation mechanism, so it records them as null with a status instead
of a false 0.0, and never loads the legacy mechanism-cost loaders."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = r"""
import contextlib, io, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/scripts/golden")
import run_case
from gridform_core.application import run_project_application
from backend.model_runner import _frontend_results
case = dict(run_case.load_cases()["C2"], id="C2")
project = run_case.build_project(case)
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    exact = run_project_application(project, run_id="mechanism-scope", pack_root=(Path(sys.argv[1]) / case["pack"]).resolve(),
                                    output_dir=Path(sys.argv[2]), mode=str(case["mode"]))
# C2 is the native default chain in two_year_smoke; build the Runs-page rows from the native payload as model_runner does for an annual Run.
results = _frontend_results(exact, dict(project.get("modules") or {}), None, mode="two_year", periods_per_year=17520,
                            expected_years=tuple(int(row["Year"]) for row in exact["system_cost_history"]))
loaded = sorted(name for name in sys.modules if "mechanism_costs" in name or "decarbonization_cost_breakdown" in name)
print(json.dumps({"history": exact["system_cost_history"][0], "metrics": results[0]["metrics"], "loaded": loaded}))
"""


class NativeMechanismScopeTests(unittest.TestCase):
    def test_native_path_records_not_modelled_mechanisms_without_loading_them(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)}
            completed = subprocess.run(
                [sys.executable, "-B", "-c", PROBE, str(ROOT), str(Path(folder) / "output")],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=600,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
        report = json.loads(completed.stdout.strip().splitlines()[-1])
        history, metrics = report["history"], report["metrics"]
        self.assertIsNone(history["CM_Mechanism_Cost_Added_to_System_GBP"])
        self.assertEqual(history["CM_Mechanism_Cost_Status"], "not_modelled")
        self.assertIsNone(history["Decarbonization_Mechanism_Cost_Added_to_System_GBP"])
        self.assertEqual(history["Decarbonization_Mechanism_Cost_Status"], "not_modelled")
        self.assertIsNone(metrics["cm_mechanism_cost_gbp"])
        self.assertEqual(metrics["cm_mechanism_cost_status"], "not_modelled")
        self.assertEqual(metrics["decarbonization_mechanism_cost_status"], "not_modelled")
        self.assertIs(metrics["system_cost_includes_voll"], False)
        self.assertEqual(report["loaded"], [], "the native path must not import the legacy mechanism-cost loaders")

    def test_legacy_rows_keep_their_recorded_mechanisms_and_voll(self) -> None:
        from backend.model_runner import _frontend_results

        exact = {
            "capacity_history": [], "investment_decisions": [], "system_cost_history": [{
                "Year": 2025, "Total_System_Cost_GBP": 300.0, "Cost_per_MWh_GBP": 3.0, "Total_Energy_Generated_MWh": 100.0,
                "Total_Levelized_Capital_Cost_GBP": 100.0, "Total_Operational_Cost_GBP": 80.0,
                "Lost_Value_of_Electricity_GBP": 50.0, "CM_Mechanism_Cost_Added_to_System_GBP": 40.0,
                "Decarbonization_Mechanism_Cost_Added_to_System_GBP": 30.0, "Total_Energy_Deficit_MWh": 1.0,
            }],
        }
        metrics = _frontend_results(exact, {"investment": "agent-investment", "pipeline": "planning-pipeline", "vre_cap": "vre-expansion-cap", "storage_cap": "value-storage-expansion-policy", "transition": "value-annual-state-transition", "psm": "value-bid-at-cost-psm"}, None,
                                    mode="two_year", periods_per_year=17520, expected_years=(2025,))[0]["metrics"]
        self.assertEqual((metrics["cm_mechanism_cost_gbp"], metrics["cm_mechanism_cost_status"]), (40.0, "recorded"))
        self.assertEqual(metrics["lost_value_of_electricity_gbp"], 50.0)
        self.assertIs(metrics["system_cost_includes_voll"], True)


if __name__ == "__main__":
    unittest.main()
