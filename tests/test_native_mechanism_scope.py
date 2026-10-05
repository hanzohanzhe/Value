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



def _ledger(components: dict[str, float] | None, *, zonal: bool = False) -> dict:
    """A CEM cost ledger built by the real ledger builder from one PSM's operating components."""

    from gridform_core.cost_ledger import build_cem_cost_ledger
    from gridform_core.v2.contracts import MarketYearResult

    operating = sum((components or {"_": 30.0}).values())
    extensions: dict[str, object] = {"physical_operating_cost_components_gbp": components} if components else {}
    if zonal:
        extensions["zonal_accounting_gbp"] = {
            "system_resource_cost_gbp": 100.0 + operating, "transmission_constraint_resource_cost_gbp": 3.0,
            "national_settlement_gbp": 50.0, "redispatch_settlement_gbp": 4.0, "policy_transfer_gbp": 0.0,
        }
    market = MarketYearResult(
        result_id="voll-basis", year=2025, module_id="fixture-psm", module_version="1",
        generation_mwh_by_asset={}, market_income_gbp_by_agent={},
        total_system_cost_gbp=100.0 + operating, total_operational_cost_gbp=operating,
        total_levelized_capital_cost_gbp=100.0, total_demand_mwh=10.0, total_generation_mwh=9.0,
        total_blackout_mwh=1.0, total_excess_mwh=0.0,
        extensions=extensions,
    )
    return build_cem_cost_ledger(market).to_dict()


class VollBasisTests(unittest.TestCase):
    """Review response: the VoLL flag comes from the declared headline components, not from name fragments."""

    def test_perfect_foresight_headline_includes_voll(self) -> None:
        from backend.model_runner import _system_cost_includes_voll

        # perfect_foresight_psm: blackout x VoLL is the operating line blackout_prevention_failure
        ledger = _ledger({"generation_and_import_variable": 20.0, "storage_variable_degradation": 2.0, "blackout_prevention_failure": 8.0})
        self.assertIn("operation.blackout_prevention_failure", [line["id"] for line in ledger["lines"] if line["included_in_cem_system_cost"]])
        self.assertIs(_system_cost_includes_voll(ledger), True)

    def test_native_and_unknown_components(self) -> None:
        from backend.model_runner import _system_cost_includes_voll

        native = _ledger({"generation_import_and_reliability": 25.0, "storage_cycle_depreciation": 5.0})
        self.assertIs(_system_cost_includes_voll(native), False)
        # zonal redispatch adds load_shedding x VoLL to the same class total (staged_psm reconciles it)
        zonal = _ledger({"generation_import_and_reliability": 25.0, "storage_cycle_depreciation": 5.0}, zonal=True)
        self.assertTrue(any(line["id"].startswith("zonal.") for line in zonal["lines"]))
        self.assertIs(_system_cost_includes_voll(zonal), True)
        # an opaque operating total or an unreviewed component: the basis is not recorded
        self.assertIsNone(_system_cost_includes_voll(_ledger(None)))
        self.assertIsNone(_system_cost_includes_voll(_ledger({"generation_import_and_reliability": 25.0, "lost_load_guess": 5.0})))
        # the doctoral (legacy) total has no CEM ledger and adds Lost_Value_of_Electricity
        self.assertIs(_system_cost_includes_voll(None), True)

    def test_every_psm_operating_component_is_reviewed(self) -> None:
        import re

        from backend.model_runner import VOLL_BASIS_BY_LEDGER_LINE

        for relative in ("gridform_core/perfect_foresight_psm.py", "gridform_core/builtin/scheme_c_1000twh/scheme_c_native_psm.py",
                         "gridform_core/builtin/scheme_c_1000twh/staged_psm.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            block = source[source.index('"physical_operating_cost_components_gbp": {'):]
            block = block[:block.index("},")]
            keys = re.findall(r'"([a-z_]+)":', block.split("{", 1)[1])
            self.assertTrue(keys, relative)
            for key in keys:
                with self.subTest(psm=relative, component=key):
                    self.assertIn(f"operation.{key}", VOLL_BASIS_BY_LEDGER_LINE)

if __name__ == "__main__":
    unittest.main()
