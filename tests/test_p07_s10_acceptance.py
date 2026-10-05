"""P0-7 S10: integration acceptance after P0-5b + P0-7 (no model runs).

* the acceptance checks of ``scripts/p07_s10_acceptance.py`` catch the three
  S10 failure modes on synthetic year results (High at S~0, a power-battery
  pool overflow, an unreconciled cost ledger);
* the committed VALUE-101 acceptance record (two_year and two_year_smoke in
  both profiles) passed, reproduced its golden revisions exactly, and is
  consistent with the golden history;
* every golden revision of both families that changes a gated column names a
  correction id; doctoral trajectory changes only for allow-listed universal
  findings, each with its numeric report.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "p07" / "s10_acceptance.json"


def _module():
    spec = importlib.util.spec_from_file_location("p07_s10_acceptance", ROOT / "scripts" / "p07_s10_acceptance.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


acceptance = _module()


def _year(proposals=(), a4=None, income=None, pools=None, caps=None):
    assets = [
        {"asset_id": "CCGT", "technology": "CCGT", "capacity_mw": 50.0, "region": "GB",
         "extensions": {"investment_owner_id": "CCGT"}},
        {"asset_id": "1c_battery", "technology": "1c_battery", "capacity_mw": 10.0, "region": "GB",
         "extensions": {"investment_owner_id": "1c_battery", "total_capex_gbp": 3.3e6}},
    ]
    return {
        "year": 2026,
        "planning_advance": {"operating_state": {"assets": assets}},
        "market": {"market_income_gbp_by_agent": income or {"CCGT": 1000.0, "1c_battery": 138025.0}},
        "expansion_headroom": [{"module_id": "value-storage-expansion-policy", "allowed_additions_mw": caps or {},
                                "extensions": {"headroom_semantics": "corrected_leftover_power_pool_v1",
                                               "pools": pools or {}}}],
        "investment": {
            "proposals": list(proposals),
            "retirements_mw": {},
            "extensions": {
                "initial_headroom_mw_by_technology": caps or {},
                "a4_net_revenue": {"thermal_operating_cost_gbp_by_group": a4 or {"CCGT|CCGT|GB": 1000.0}},
            },
        },
    }


def _proposal(technology, mw, recommendation, roi, preferred=0.08, payback=None, owner=None):
    return {"technology": technology, "capacity_mw": mw, "agent_id": owner or technology,
            "evidence": {"roi": roi, "preferred_rate": preferred,
                         "payback_years": payback if payback is not None else (1.0 / roi if roi > 0 else float("inf")),
                         "target_payback_years": 25.0},
            "extensions": {"investment_recommendation": recommendation, "investment_owner_id": owner or technology}}


class InvestmentCheckTests(unittest.TestCase):
    def test_accepts_profit_battery_within_the_pool(self):
        pools = {"power_battery_pool": {"cap_mw": 4.0, "technologies": ["0.25c_battery", "0.5c_battery", "1c_battery"]}}
        caps = {"0.25c_battery": 4.0, "0.5c_battery": 4.0, "1c_battery": 4.0}
        row = acceptance.check_investment_year(
            _year([_proposal("1c_battery", 0.418, "Invest_Profit", 0.0418)], pools=pools, caps=caps))
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["storage_headroom"]["pools"]["power_battery_pool"]["added_mw"], 0.418)
        self.assertTrue(row["thermal_groups"][0]["near_zero"])

    def test_high_at_zero_surplus_is_reported(self):
        # A thermal group whose income equals its running cost (S~0) proposing High.
        row = acceptance.check_investment_year(_year([_proposal("CCGT", 10.95, "Invest_High", 0.0, payback=float("inf"))]))
        joined = " ".join(row["errors"])
        self.assertIn("S<=0", joined)
        self.assertIn("Invest_High", joined)
        self.assertIn("S~0", joined)

    def test_high_below_the_preferred_rate_is_reported(self):
        row = acceptance.check_investment_year(_year([_proposal("onshore", 2.0, "Invest_High", 0.05)]))
        self.assertTrue(any("Invest_High with roi" in e for e in row["errors"]))

    def test_pool_overflow_is_reported(self):
        pools = {"power_battery_pool": {"cap_mw": 4.0, "technologies": ["0.25c_battery", "0.5c_battery", "1c_battery"]}}
        caps = {"0.25c_battery": 4.0, "0.5c_battery": 4.0, "1c_battery": 4.0}
        proposals = [_proposal(t, 3.0, "Invest_Profit", 0.05, owner=t) for t in ("0.25c_battery", "1c_battery")]
        row = acceptance.check_investment_year(_year(proposals, pools=pools, caps=caps))
        self.assertTrue(any("above the pool cap" in e for e in row["errors"]))


class CostLedgerCheckTests(unittest.TestCase):
    def _ledger(self, headline=125.0 - 40.0 + 10.0):
        return {"years": [{
            "year": 2026, "cem_system_cost_gbp": headline, "status": "reconciled",
            "headline_capital_gbp": 85.0, "vre_storage_fixed_opex_excluded_gbp": 0.0,
            "compatibility_capital_gbp": 40.0, "compatibility_capital_in_headline": False,
            "lines": [
                {"id": "commissioned_fleet.annualised_capital", "amount_gbp": 85.0, "included_in_cem_system_cost": True},
                {"id": "operation.generation_import_and_reliability", "amount_gbp": 10.0, "included_in_cem_system_cost": True},
                {"id": "existing_stock_compatibility.annualised_capital", "amount_gbp": 40.0, "included_in_cem_system_cost": False},
            ]}]}

    def test_reconciled_ledger_passes(self):
        rows = acceptance.check_cost_ledger(self._ledger(), [{"year": 2026, "market": {"total_levelized_capital_cost_gbp": 125.0}}])
        self.assertEqual(rows[0]["errors"], [])

    def test_headline_mismatch_and_counted_memo_are_reported(self):
        ledger = self._ledger(headline=135.0)
        ledger["years"][0]["lines"][2]["included_in_cem_system_cost"] = True
        rows = acceptance.check_cost_ledger(ledger, [{"year": 2026, "market": {"total_levelized_capital_cost_gbp": 125.0}}])
        joined = " ".join(rows[0]["errors"])
        self.assertIn("memo row existing_stock_compatibility.annualised_capital is counted", joined)

    def test_capital_line_must_match_the_market(self):
        rows = acceptance.check_cost_ledger(self._ledger(), [{"year": 2026, "market": {"total_levelized_capital_cost_gbp": 130.0}}])
        self.assertTrue(any("capital line" in e for e in rows[0]["errors"]))


class AcceptanceRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_record_covers_both_profiles_and_both_modes(self):
        self.assertEqual(self.record["schema_version"], acceptance.SCHEMA)
        runs = self.record["runs"]
        self.assertEqual(sorted(runs), ["C2", "C5", "C6", "D2", "D4"])
        self.assertEqual({runs[c]["profile"] for c in ("D2", "D4")}, {"doctoral-lineage-0.6.0a2"})
        self.assertEqual({runs[c]["profile"] for c in ("C2", "C5", "C6")}, {"value-corrected"})
        for case in ("C5", "C6", "D4"):
            self.assertEqual(runs[case]["periods_per_year"], [17520, 17520])

    def test_record_passed_and_reproduced_its_golden_revision(self):
        self.assertTrue(self.record["passed"])
        cases = json.loads((ROOT / "tests" / "golden" / "cases.json").read_text(encoding="utf-8"))["cases"]
        for case_id, run in self.record["runs"].items():
            self.assertEqual(run["errors"], [], case_id)
            self.assertEqual(run["golden_check"]["gated_differences"], 0, case_id)
            golden = json.loads((ROOT / "tests" / "golden" / cases[case_id]["family"] / f"{case_id}.json").read_text(encoding="utf-8"))
            # Later milestones may append revisions; the record must point at an existing one.
            self.assertLess(run["golden_check"]["revision"], len(golden["revisions"]), case_id)

    def test_corrected_two_year_keeps_the_pool_and_no_zero_surplus_build(self):
        for case_id in ("C5", "C6"):
            for year in self.record["runs"][case_id]["investment"]:
                pool = year["storage_headroom"]["pools"]["power_battery_pool"]
                self.assertLessEqual(pool["added_mw"], pool["cap_mw"] + 1e-9)
                for group in year["thermal_groups"]:
                    if group["near_zero"]:
                        self.assertEqual(group["proposed_mw"], 0.0)
                self.assertTrue(all(p["roi"] > 0 for p in year["proposals"]))

    def test_doctoral_has_no_pool(self):
        for case_id in ("D2", "D4"):
            for year in self.record["runs"][case_id]["investment"]:
                self.assertEqual(year["storage_headroom"]["pools"], {})


class GoldenAttributionTests(unittest.TestCase):
    def test_every_gated_revision_is_attributed(self):
        report = acceptance.attribute_goldens()
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["passed"])

    def test_m5_doctoral_trajectory_changes_only_for_a4(self):
        report = acceptance.attribute_goldens()
        for case_id, case in report["cases"].items():
            if case["family"] != "doctoral":
                continue
            for row in case["revisions"]:
                if row["m5"] and row["trajectory_columns"]:
                    self.assertEqual(row["findings"], ["P4-01-thermal"], f"{case_id} r{row['revision']}")
                    self.assertEqual(case_id, "D4")

    def test_missing_correction_id_is_reported(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "golden"
            (target / "corrected").mkdir(parents=True)
            source = ROOT / "tests" / "golden"
            shutil.copy(source / "doctoral_trajectory_rebaselines.json", target)
            cases = json.loads((source / "cases.json").read_text(encoding="utf-8"))
            cases["cases"] = {"C2": cases["cases"]["C2"]}
            (target / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
            golden = copy.deepcopy(json.loads((source / "corrected" / "C2.json").read_text(encoding="utf-8")))
            golden["revisions"][-1]["correction_ids"] = []
            (target / "corrected" / "C2.json").write_text(json.dumps(golden), encoding="utf-8")
            report = acceptance.attribute_goldens(target)
        self.assertFalse(report["passed"])
        self.assertTrue(any("corrected/C2" in e for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
