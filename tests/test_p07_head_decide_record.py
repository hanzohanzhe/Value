"""P0-7 S1: the HEAD (35aadb3) decide() record and its pure recomposition.

``tests/fixtures/p07/head_decide_record.json`` was written once by
``scripts/p07_record_head_decide.py`` with the decide() sources byte-identical
to 35aadb3 (and re-checked on a ``git archive 35aadb3`` copy). This test

* rebuilds every scenario from the stored inputs alone and requires the live
  ``SchemeCAgentInvestmentDefinition.decide()`` to reproduce the stored output
  exactly (identity-zone ``cem_model_identity`` excluded);
* requires ``investment_accounts.head_decide_accounts`` (the decomposed HEAD
  rule) to reproduce the same proposals, retirements and headroom bit for bit;
* checks the decision-A4 fixtures: restored Scheme C thermal net revenue for
  gas/biomass/OCGT, gross = profit for VRE and storage, and the decisions the
  HEAD rule yields on that net revenue (what P0-7 S4 must produce).

P0-7 S4 changes decide() under correction p07 thermal net revenue (A4, both
profiles); it must then update the first assertion with the declared deltas.
"""
from __future__ import annotations

import importlib.util
import json
import math
import unittest
from pathlib import Path

from gridform_core import investment_accounts as ia
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCAgentInvestmentDefinition
from gridform_core.cem_investment_policy import investment_mode

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "tests" / "fixtures" / "p07" / "head_decide_record.json"


def _recorder():
    spec = importlib.util.spec_from_file_location("p07_record_head_decide", ROOT / "scripts" / "p07_record_head_decide.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REC = _recorder()


def _json_text(value) -> str:
    return json.dumps(value, sort_keys=True, allow_nan=False)


class HeadDecideRecordTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_record_identity(self):
        self.assertEqual(self.record["schema_version"], "value.p07-head-decide-record/v1")
        self.assertEqual(self.record["freeze_commit"], "35aadb3")
        self.assertEqual(self.record["identity_extension_keys_excluded"], ["cem_model_identity"])
        ids = [entry["id"] for entry in self.record["scenarios"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 7)

    def test_live_decide_reproduces_the_head_record(self):
        for entry in self.record["scenarios"]:
            with self.subTest(entry["id"]):
                run, state, market, headroom = REC.inputs_from_record(entry)
                decision = SchemeCAgentInvestmentDefinition().decide(run, state, market, headroom)
                self.assertEqual(_json_text(REC.decision_record(decision)), _json_text(entry["head_decision"]))

    def test_pure_recomposition_matches_the_head_record_bit_for_bit(self):
        for entry in self.record["scenarios"]:
            with self.subTest(entry["id"]):
                self._check_recomposition(entry)

    def _check_recomposition(self, entry):
        inputs = REC.decanonical(entry["inputs"])
        head = REC.decanonical(entry["head_decision"])
        groups, ineligible_assets = ia.head_group_assets(
            inputs["assets"], inputs["market"]["market_income_gbp_by_agent"])
        caps = ia.merge_headroom_caps(row["allowed_additions_mw"] for row in inputs["headroom"])
        result = ia.head_decide_accounts(groups, caps, investment_mode)
        extensions = head["extensions"]
        self.assertEqual(ineligible_assets, extensions["ineligible_assets"])
        self.assertEqual(len(groups), extensions["grouped_investment_owners"])
        self.assertEqual(
            [{"investment_owner_id": row["owner"], "technology": row["technology"], "reason": row["skipped"]}
             for row in result["outcomes"] if "skipped" in row],
            extensions["ineligible_groups"])
        self.assertEqual(_json_text(caps), _json_text(extensions["initial_headroom_mw_by_technology"]))
        self.assertEqual(_json_text(result["remaining_caps"]), _json_text(extensions["remaining_headroom_mw_by_technology"]))
        self.assertEqual(_json_text(result["retirements_mw"]), _json_text(head["retirements_mw"]))
        accepted = [row for row in result["outcomes"] if row["accepted_addition_mw"] > 0]
        self.assertEqual(len(accepted), len(head["proposals"]))
        run_id = inputs["run"]["run_id"]
        for outcome, proposal in zip(accepted, head["proposals"]):
            account = outcome["account"]
            self.assertEqual(proposal["proposal_id"],
                             f"{run_id}:{inputs['year']}:{outcome['owner']}:{outcome['index']}")
            self.assertEqual((proposal["agent_id"], proposal["technology"], proposal["region"]),
                             (outcome["owner"], outcome["technology"], outcome["region"]))
            self.assertEqual(proposal["capacity_mw"].hex(), outcome["accepted_addition_mw"].hex())
            self.assertEqual(proposal["extensions"]["investment_recommendation"], outcome["recommendation"])
            self.assertEqual(proposal["extensions"]["investment_eligibility_mode"], outcome["mode"])
            evidence = proposal["evidence"]
            self.assertEqual(evidence["roi"].hex(), account["roi"].hex())
            self.assertEqual(evidence["payback_years"].hex(), account["payback_years"].hex())
            self.assertEqual(evidence["preferred_rate"].hex(), account["preferred_rate"].hex())
            self.assertEqual(evidence["target_payback_years"].hex(), account["target_payback_years"].hex())
            self.assertEqual(evidence["recommendation_code"],
                             3.0 if outcome["recommendation"] == "Invest_High" else 2.0)
            self.assertEqual(proposal["extensions"]["capital_cost_per_mw"].hex(), account["cost_per_mw_gbp"].hex())

    def test_head_toy_values_named_in_the_plan(self):
        by_id = {entry["id"]: entry["head_decision"] for entry in self.record["scenarios"]}
        mc = by_id["ccgt_price_equals_mc"]["proposals"]
        self.assertEqual([(row["technology"], row["capacity_mw"], row["extensions"]["investment_recommendation"])
                          for row in mc], [("CCGT", 10.95, "Invest_High")])
        self.assertEqual(by_id["ccgt_price_50"]["proposals"][0]["capacity_mw"], 9.125)
        storage = by_id["storage_gross_headroom"]
        self.assertEqual([(row["technology"], row["capacity_mw"]) for row in storage["proposals"]],
                         [("0.25c_battery", 3.0)])
        solar = [row["capacity_mw"] for row in by_id["vre_gross_shared_headroom"]["proposals"]
                 if row["technology"] == "solar"]
        self.assertEqual(solar, [10.0, 2.0])


class DecisionA4FixtureTest(unittest.TestCase):
    """Thermal net revenue restored in both profiles; VRE and storage gross = profit."""

    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_fixture_covers_thermal_with_fuel_and_carbon_and_gross_vre_storage(self):
        bases = {}
        technologies = {}
        for entry in self.record["scenarios"]:
            assets = {row["asset_id"]: row["technology"] for row in entry["inputs"]["assets"]}
            for asset_id, expected in entry["a4_expected"].items():
                bases.setdefault(expected["basis"], set()).add(assets[asset_id])
                technologies[asset_id] = assets[asset_id]
        self.assertTrue({"CCGT", "gas", "bio_and_waste", "OCGT"} <= bases[ia.NET_REVENUE_BASIS_THERMAL])
        self.assertTrue({"solar", "onshore", "1c_battery", "0.25c_battery"} <= bases[ia.NET_REVENUE_BASIS_GROSS])

    def test_net_revenue_matches_hand_computed_expectations(self):
        for entry in self.record["scenarios"]:
            income = entry["inputs"]["market"]["market_income_gbp_by_agent"]
            for asset_id, inputs in entry["cashflow_inputs"].items():
                with self.subTest(scenario=entry["id"], asset=asset_id):
                    self.assertEqual(inputs["electricity_income_gbp"], income[asset_id])
                    row = ia.scheme_c_investment_net_revenue(**inputs)
                    expected = entry["a4_expected"][asset_id]
                    self.assertEqual(row["basis"], expected["basis"])
                    self.assertEqual(row["gen_cost_gbp_per_mwh"], expected["gen_cost_gbp_per_mwh"])
                    self.assertEqual(row["operating_cost_gbp"], expected["operating_cost_gbp"])
                    self.assertEqual(row["net_revenue_gbp"], expected["net_revenue_gbp"])

    def test_head_rule_on_restored_net_gives_the_expected_s4_decisions(self):
        checked = 0
        for entry in self.record["scenarios"]:
            expected = entry["a4_expected_decision"]
            if not isinstance(expected, dict):
                continue
            net = {asset_id: row["net_revenue_gbp"] for asset_id, row in entry["a4_expected"].items()}
            inputs = REC.decanonical(entry["inputs"])
            groups, _ = ia.head_group_assets(inputs["assets"], net)
            caps = ia.merge_headroom_caps(row["allowed_additions_mw"] for row in inputs["headroom"])
            outcomes = {f"{row['owner']}|{row['technology']}|{row['region']}": row
                        for row in ia.head_decide_accounts(groups, caps, investment_mode)["outcomes"]}
            for key, target in expected["groups"].items():
                with self.subTest(scenario=entry["id"], group=key):
                    row = outcomes[key]
                    self.assertEqual(row["recommendation"], target["recommendation"])
                    self.assertTrue(math.isclose(row["accepted_addition_mw"], target["accepted_addition_mw"],
                                                 rel_tol=1e-12, abs_tol=1e-12))
                    self.assertTrue(math.isclose(row["retirement_mw"], target["retirement_mw"],
                                                 rel_tol=1e-12, abs_tol=1e-12))
                    checked += 1
        self.assertGreaterEqual(checked, 5)


if __name__ == "__main__":
    unittest.main()
