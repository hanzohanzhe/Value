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
  CCGT/gas/biomass/OCGT (decided by technology, so gas with zero fuel and
  carbon cost still deducts), gross = profit for VRE and storage, and the
  decisions the HEAD rule yields on that net revenue (what P0-7 S4 must
  produce), including the scenarios whose decision must not move under A4;
* runs the S4 A4 path (``a4_net_revenue_for_decidable_groups``: investment-mode
  filter first) over a fleet with Nuclear, hydro and coal beside thermal.

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


def cost_rows(cashflow):
    """Fixture cashflow rows without their income fields: A4 takes income from the HEAD map (lead ruling)."""
    return {asset_id: {key: value for key, value in row.items() if key not in ia.A4_INCOME_FIELDS}
            for asset_id, row in cashflow.items()}


def with_agent_cashflow(market, entry):
    """The recorded market plus a ``value.agent-cashflow/v1`` extension built from the fixture cost rows."""
    from dataclasses import replace

    from gridform_core import agent_cashflow

    if not entry["cashflow_inputs"]:
        return market
    rows = {asset_id: agent_cashflow.cashflow_row(row["technology"], row["generated_mwh"], row,
                                                  cost_basis="p07-fixture")
            for asset_id, row in cost_rows(entry["cashflow_inputs"]).items()}
    return replace(market, extensions={
        **dict(market.extensions),
        agent_cashflow.EXTENSION_KEY: agent_cashflow.extension(rows, psm_module_id="p07-fixture",
                                                               cost_basis="p07-fixture")})


def _json_text(value) -> str:
    return json.dumps(value, sort_keys=True, allow_nan=False)


def assert_recomposition_matches_head(test, entry, income_by_agent):
    """The decomposed HEAD rule on ``income_by_agent`` reproduces the recorded HEAD decision."""
    inputs = REC.decanonical(entry["inputs"])
    head = REC.decanonical(entry["head_decision"])
    groups, ineligible_assets = ia.head_group_assets(inputs["assets"], income_by_agent)
    caps = ia.merge_headroom_caps(row["allowed_additions_mw"] for row in inputs["headroom"])
    result = ia.head_decide_accounts(groups, caps, investment_mode)
    extensions = head["extensions"]
    test.assertEqual(ineligible_assets, extensions["ineligible_assets"])
    test.assertEqual(len(groups), extensions["grouped_investment_owners"])
    test.assertEqual(
        [{"investment_owner_id": row["owner"], "technology": row["technology"], "reason": row["skipped"]}
         for row in result["outcomes"] if "skipped" in row],
        extensions["ineligible_groups"])
    test.assertEqual(_json_text(caps), _json_text(extensions["initial_headroom_mw_by_technology"]))
    test.assertEqual(_json_text(result["remaining_caps"]), _json_text(extensions["remaining_headroom_mw_by_technology"]))
    test.assertEqual(_json_text(result["retirements_mw"]), _json_text(head["retirements_mw"]))
    accepted = [row for row in result["outcomes"] if row["accepted_addition_mw"] > 0]
    test.assertEqual(len(accepted), len(head["proposals"]))
    run_id = inputs["run"]["run_id"]
    for outcome, proposal in zip(accepted, head["proposals"]):
        account = outcome["account"]
        test.assertEqual(proposal["proposal_id"],
                         f"{run_id}:{inputs['year']}:{outcome['owner']}:{outcome['index']}")
        test.assertEqual((proposal["agent_id"], proposal["technology"], proposal["region"]),
                         (outcome["owner"], outcome["technology"], outcome["region"]))
        test.assertEqual(proposal["capacity_mw"].hex(), outcome["accepted_addition_mw"].hex())
        test.assertEqual(proposal["extensions"]["investment_recommendation"], outcome["recommendation"])
        test.assertEqual(proposal["extensions"]["investment_eligibility_mode"], outcome["mode"])
        evidence = proposal["evidence"]
        test.assertEqual(evidence["roi"].hex(), account["roi"].hex())
        test.assertEqual(evidence["payback_years"].hex(), account["payback_years"].hex())
        test.assertEqual(evidence["preferred_rate"].hex(), account["preferred_rate"].hex())
        test.assertEqual(evidence["target_payback_years"].hex(), account["target_payback_years"].hex())
        test.assertEqual(evidence["recommendation_code"],
                         3.0 if outcome["recommendation"] == "Invest_High" else 2.0)
        test.assertEqual(proposal["extensions"]["capital_cost_per_mw"].hex(), account["cost_per_mw_gbp"].hex())


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
        self.assertGreaterEqual(len(ids), 10)

    def test_live_decide_reproduces_the_head_record(self):
        """P0-7 S4 (A4, correction p07.thermal-net-revenue, both profiles): declared deltas only.

        * ``unchanged_from_head`` (VRE/storage only): the live decide() equals the
          HEAD record bit for bit, apart from the added ``a4_net_revenue``
          audit record in the decision extensions;
        * thermal scenarios: the live decision equals ``a4_expected_decision``;
        * ``fails_closed``: the recorded operational cost beside A4 is refused;
        * a market without ``agent_cashflow`` and a decidable thermal group fails closed.
        """
        for entry in self.record["scenarios"]:
            expected = entry["a4_expected_decision"]
            with self.subTest(entry["id"]):
                run, state, market, headroom = REC.inputs_from_record(entry)
                market = with_agent_cashflow(market, entry)
                if expected == "not_applicable":
                    with self.assertRaisesRegex(ValueError, "agent_cashflow"):
                        SchemeCAgentInvestmentDefinition().decide(run, state, market, headroom)
                    continue
                if isinstance(expected, dict) and "fails_closed" in expected:
                    with self.assertRaisesRegex(ValueError, "annual_operational_cost_gbp"):
                        SchemeCAgentInvestmentDefinition().decide(run, state, market, headroom)
                    continue
                decision = SchemeCAgentInvestmentDefinition().decide(run, state, market, headroom)
                live = REC.decision_record(decision)
                audit = live["extensions"].pop("a4_net_revenue")
                self.assertEqual(audit["money_basis"], ia.MONEY_BASIS)
                if expected == "unchanged_from_head":
                    self.assertEqual(audit["thermal_operating_cost_gbp_by_group"], {})
                    self.assertEqual(_json_text(live), _json_text(entry["head_decision"]))
                    continue
                proposals = {f"{row['agent_id']}|{row['technology']}|{row['region']}": row
                             for row in live["proposals"]}
                for key, target in expected["groups"].items():
                    added = proposals[key]["capacity_mw"] if key in proposals else 0.0
                    self.assertTrue(math.isclose(added, target["accepted_addition_mw"], rel_tol=1e-12, abs_tol=1e-12))
                    if key in proposals:
                        self.assertEqual(proposals[key]["extensions"]["investment_recommendation"],
                                         target["recommendation"])
                    owner, technology, region = key.split("|")
                    members = [row["asset_id"] for row in REC.decanonical(entry["inputs"])["assets"]
                               if row["technology"] == technology and (row["region"] or "GB") == region]
                    retired = sum(live["retirements_mw"].get(asset_id, 0.0) for asset_id in members)
                    self.assertTrue(math.isclose(retired, target["retirement_mw"], rel_tol=1e-12, abs_tol=1e-12))
                for asset_id, value in expected.get("retirements_mw", {}).items():
                    self.assertTrue(math.isclose(live["retirements_mw"][asset_id], value, rel_tol=1e-12))

    def test_pure_recomposition_matches_the_head_record_bit_for_bit(self):
        for entry in self.record["scenarios"]:
            with self.subTest(entry["id"]):
                inputs = REC.decanonical(entry["inputs"])
                assert_recomposition_matches_head(self, entry, inputs["market"]["market_income_gbp_by_agent"])

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

    def _entry(self, scenario_id):
        return {entry["id"]: entry for entry in self.record["scenarios"]}[scenario_id]

    def test_multi_member_deplete_scenario_pins_sizing_and_split(self):
        """Review M0-P0-7-S1 round 3: a multi-member loss group with target payback != economic life."""
        entry = self._entry("deplete_multi_member_unequal")
        inputs = REC.decanonical(entry["inputs"])
        capacity = {row["asset_id"]: row["capacity_mw"] for row in inputs["assets"]}
        extensions = [row["extensions"] for row in inputs["assets"]]
        self.assertGreaterEqual(len(set(capacity.values())), 3)
        target = min(row["target_payback_years"] for row in extensions)
        life = min(row["economic_lifetime_years"] for row in extensions)
        self.assertNotEqual(target, life)
        head = entry["head_decision"]
        self.assertEqual(head["proposals"], [])
        retirements = head["retirements_mw"]
        self.assertEqual(set(retirements), set(capacity))
        loss = -sum(inputs["market"]["market_income_gbp_by_agent"].values())
        group = loss * target / 1e6  # unit cost 1e6 GBP/MW
        self.assertTrue(math.isclose(math.fsum(retirements.values()), group, rel_tol=1e-15))
        total = sum(capacity.values())
        for asset_id, value in retirements.items():
            with self.subTest(asset=asset_id):
                self.assertEqual(value, group * capacity[asset_id] / total)
        self.assertNotEqual(len(set(retirements.values())), 1)

    def test_tier_boundary_scenario_sits_exactly_on_both_boundaries(self):
        """ROI == preferred is not Invest_High (strict); payback == target is Invest_Profit (inclusive)."""
        head = self._entry("tier_boundaries_and_region_default")["head_decision"]
        by_owner = {row["agent_id"]: row for row in head["proposals"]}
        roi = by_owner["owner-roi"]["evidence"]
        self.assertEqual(roi["roi"].hex(), roi["preferred_rate"].hex())
        self.assertEqual(by_owner["owner-roi"]["extensions"]["investment_recommendation"], "Invest_Profit")
        payback = by_owner["owner-payback"]["evidence"]
        self.assertEqual(payback["payback_years"].hex(), payback["target_payback_years"].hex())
        self.assertLess(payback["roi"], payback["preferred_rate"])
        self.assertEqual(by_owner["owner-payback"]["extensions"]["investment_recommendation"], "Invest_Profit")
        self.assertNotIn("owner-even", by_owner)  # net exactly 0: Do_Nothing, not Deplete
        self.assertEqual(head["retirements_mw"], {})

    def test_region_none_defaults_to_gb(self):
        entry = self._entry("tier_boundaries_and_region_default")
        regions = {row["asset_id"]: row["region"] for row in entry["inputs"]["assets"]}
        self.assertIsNone(regions["solar-r-none"])
        self.assertIsNone(regions["solar-n-none"])
        self.assertEqual(regions["solar-r-gb"], "GB")
        head = entry["head_decision"]
        self.assertEqual(head["extensions"]["grouped_investment_owners"], 5)  # solar-r-none joins solar-r-gb
        self.assertEqual({row["agent_id"]: row["region"] for row in head["proposals"]
                          if row["agent_id"] in {"owner-r", "owner-n"}}, {"owner-r": "GB", "owner-n": "GB"})
        self.assertEqual([row["capacity_mw"] for row in head["proposals"] if row["agent_id"] == "owner-r"],
                         [(900_000.0 + 450_000.0) / 600_000.0])


class OwnershipAndFalsyDefaultsRecordTest(unittest.TestCase):
    """Lead ruling 2026-10-05 item 2: the scenario added to the HEAD record (sources still 35aadb3)."""

    def test_scenario_covers_ownership_headroom_and_falsy_defaults(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        entry = {row["id"]: row for row in record["scenarios"]}["ownership_and_falsy_defaults"]
        inputs = REC.decanonical(entry["inputs"])
        ext = {row["asset_id"]: row["extensions"] for row in inputs["assets"]}
        self.assertNotIn("investment_owner_id", ext["solar-src"])
        self.assertEqual(ext["solar-src"]["source_agent_id"], "agent-s")
        self.assertEqual((ext["solar-io"]["investment_owner_id"], ext["solar-io"]["source_agent_id"]),
                         ("owner-io", "agent-ignored"))
        self.assertEqual((ext["solar-io"]["preferred_rate"], ext["solar-io"]["target_payback_years"]), (0.0, 0.0))
        self.assertTrue(all("onshore" not in row["allowed_additions_mw"] for row in inputs["headroom"]))
        head = entry["head_decision"]
        by_owner = {row["agent_id"]: row for row in head["proposals"]}
        self.assertEqual(set(by_owner), {"agent-s", "owner-io"})
        self.assertEqual(by_owner["owner-io"]["evidence"]["preferred_rate"], 0.08)
        self.assertEqual(by_owner["owner-io"]["evidence"]["target_payback_years"], 25.0)
        self.assertEqual(by_owner["owner-io"]["extensions"]["investment_recommendation"], "Invest_Profit")
        self.assertEqual(by_owner["agent-s"]["extensions"]["investment_recommendation"], "Invest_High")
        self.assertNotIn("onshore", head["extensions"]["remaining_headroom_mw_by_technology"])
        self.assertEqual(head["retirements_mw"], {})


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
        self.assertEqual(bases[ia.NET_REVENUE_BASIS_THERMAL], set(ia.THERMAL_TECHNOLOGIES))
        self.assertTrue({"solar", "onshore", "1c_battery", "0.25c_battery"} <= bases[ia.NET_REVENUE_BASIS_GROSS])
        self.assertTrue(bases[ia.NET_REVENUE_BASIS_GROSS] <= ia.GROSS_PROFIT_TECHNOLOGIES)

    def test_a4_rule_text_names_the_technology_classes(self):
        rule = self.record["a4_rule"]
        self.assertIn("by technology", rule)
        for technology in sorted(ia.THERMAL_TECHNOLOGIES):
            self.assertIn(technology, rule)

    def test_zero_fuel_and_carbon_gas_still_deducts(self):
        entry = {row["id"]: row for row in self.record["scenarios"]}["gas_zero_fuel_and_carbon"]
        inputs = entry["cashflow_inputs"]["gas-z"]
        self.assertEqual((inputs["fuel_cost_gbp_per_mwh"], inputs["carbon_cost_gbp_per_mwh"]), (0.0, 0.0))
        self.assertEqual(entry["a4_expected"]["gas-z"]["basis"], ia.NET_REVENUE_BASIS_THERMAL)
        head = entry["head_decision"]["proposals"]
        self.assertEqual([(row["capacity_mw"], row["extensions"]["investment_recommendation"]) for row in head],
                         [(9.0, "Invest_High")])

    def test_net_revenue_matches_hand_computed_expectations(self):
        for entry in self.record["scenarios"]:
            income = entry["inputs"]["market"]["market_income_gbp_by_agent"]
            technology = {row["asset_id"]: row["technology"] for row in entry["inputs"]["assets"]}
            for asset_id, inputs in entry["cashflow_inputs"].items():
                with self.subTest(scenario=entry["id"], asset=asset_id):
                    self.assertEqual(inputs["electricity_income_gbp"], income[asset_id])
                    self.assertEqual(inputs["technology"], technology[asset_id])
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
            if not isinstance(expected, dict) or "groups" not in expected:
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
            for asset_id, value in expected.get("retirements_mw", {}).items():
                with self.subTest(scenario=entry["id"], retirement=asset_id):
                    actual = ia.head_decide_accounts(groups, caps, investment_mode)["retirements_mw"][asset_id]
                    self.assertTrue(math.isclose(actual, value, rel_tol=1e-12, abs_tol=1e-12))
                    checked += 1
        self.assertGreaterEqual(checked, 10)

    def _a4_net(self, entry):
        """A4 rows through the S4 path: mode filter first, then the A4 net revenue per member."""
        inputs = REC.decanonical(entry["inputs"])
        groups, _ = ia.head_group_assets(inputs["assets"], inputs["market"]["market_income_gbp_by_agent"])
        return ia.a4_net_revenue_for_decidable_groups(groups, investment_mode, cost_rows(entry["cashflow_inputs"]))

    def test_s4_path_reproduces_the_hand_computed_a4_rows(self):
        checked = 0
        for entry in self.record["scenarios"]:
            if not entry["cashflow_inputs"]:
                continue
            expected_decision = entry["a4_expected_decision"]
            if isinstance(expected_decision, dict) and "fails_closed" in expected_decision:
                continue  # test_recorded_operational_cost_beside_a4_fails_closed
            with self.subTest(entry["id"]):
                rows = self._a4_net(entry)
                self.assertEqual(set(rows), set(entry["a4_expected"]))
                for asset_id, expected in entry["a4_expected"].items():
                    for key, value in expected.items():
                        self.assertEqual(rows[asset_id][key], value)
                checked += 1
        self.assertGreaterEqual(checked, 7)

    def test_recorded_operational_cost_beside_a4_fails_closed(self):
        """Review M0-P0-7-S1 round 3: one operating-cost source under A4, never both (no double deduction)."""
        entry = {row["id"]: row for row in self.record["scenarios"]}["loss_profit_and_recorded_opex"]
        expected = entry["a4_expected_decision"]["fails_closed"]
        self.assertEqual(expected, {"error": "ValueError", "asset_ids": ["ccgt-opex"],
                                    "rule": "single_operating_cost_source"})
        inputs = REC.decanonical(entry["inputs"])
        opex = {row["asset_id"]: row["extensions"].get("annual_operational_cost_gbp")
                for row in inputs["assets"]}
        self.assertEqual(opex["ccgt-opex"], 10_950_000.0)
        with self.assertRaisesRegex(ValueError, "ccgt-opex .*annual_operational_cost_gbp"):
            self._a4_net(entry)
        # The hazard the rule closes: the A4 net (0) minus the recorded opex would be -10.95e6 and,
        # through the HEAD rule, retire the whole 100 MW CCGT; the HEAD record nets 0 and keeps it.
        a4 = entry["a4_expected"]["ccgt-opex"]
        self.assertEqual(a4["operating_cost_gbp"], opex["ccgt-opex"])
        self.assertEqual(a4["net_revenue_gbp"], 0.0)
        groups, _ = ia.head_group_assets(inputs["assets"], {"ccgt-opex": a4["net_revenue_gbp"]})
        double = {f"{row['owner']}|{row['technology']}": row
                  for row in ia.head_decide_accounts(groups, {}, investment_mode)["outcomes"]}
        self.assertEqual(double["owner-opex|CCGT"]["account"]["net_revenue_gbp"], -10_950_000.0)
        self.assertEqual(double["owner-opex|CCGT"]["retirement_mw"], 100.0)
        self.assertNotIn("ccgt-opex", entry["head_decision"]["retirements_mw"])
        # With the recorded opex removed (S4 keeps a single source) the A4 path computes every row.
        stripped = {**entry, "inputs": {**entry["inputs"], "assets": [
            {**row, "extensions": {key: value for key, value in row["extensions"].items()
                                   if key != "annual_operational_cost_gbp"}}
            for row in entry["inputs"]["assets"]]}}
        rows = self._a4_net(stripped)
        self.assertEqual({asset_id: row["net_revenue_gbp"] for asset_id, row in rows.items()},
                         {asset_id: row["net_revenue_gbp"] for asset_id, row in entry["a4_expected"].items()})

    def test_unchanged_from_head_scenarios_keep_the_head_decision_under_a4(self):
        """VRE and storage keep gross = profit, so the HEAD rule on the A4 net map repeats HEAD exactly."""
        checked = []
        for entry in self.record["scenarios"]:
            if entry["a4_expected_decision"] != "unchanged_from_head":
                continue
            with self.subTest(entry["id"]):
                rows = self._a4_net(entry)
                self.assertTrue(rows)
                self.assertEqual({row["basis"] for row in rows.values()}, {ia.NET_REVENUE_BASIS_GROSS})
                net = {asset_id: row["net_revenue_gbp"] for asset_id, row in rows.items()}
                assert_recomposition_matches_head(self, entry, net)
                checked.append(entry["id"])
        self.assertEqual(checked, ["vre_gross_shared_headroom", "storage_gross_headroom",
                                   "tier_boundaries_and_region_default", "ownership_and_falsy_defaults"])

    def test_vre_and_storage_net_is_the_head_income_bit_for_bit(self):
        """Lead ruling 2026-10-05: A4 changes only the operating-cost term; VRE/storage net == HEAD income."""
        checked = 0
        for entry in self.record["scenarios"]:
            expected = entry["a4_expected_decision"]
            if not entry["cashflow_inputs"] or (isinstance(expected, dict) and "fails_closed" in expected):
                continue
            inputs = REC.decanonical(entry["inputs"])
            income = inputs["market"]["market_income_gbp_by_agent"]
            groups, _ = ia.head_group_assets(inputs["assets"], income)
            # VRE and storage need no cost row at all: the result is the same.
            no_rows = {} if any(g["technology"] in ia.THERMAL_TECHNOLOGIES for g in groups) else \
                ia.a4_net_revenue_for_decidable_groups(groups, investment_mode, {})
            for rows in (self._a4_net(entry), no_rows):
                for asset_id, row in rows.items():
                    checked += 1
                    if row["basis"] != ia.NET_REVENUE_BASIS_GROSS:
                        continue
                    with self.subTest(scenario=entry["id"], asset=asset_id):
                        self.assertEqual(row["operating_cost_gbp"], 0.0)
                        self.assertEqual(row["net_revenue_gbp"].hex(),
                                         float(income.get(asset_id, 0.0) or 0.0).hex())
        self.assertGreater(checked, 20)

    def test_income_fields_in_a4_rows_are_refused(self):
        entry = {row["id"]: row for row in self.record["scenarios"]}["ccgt_price_equals_mc"]
        inputs = REC.decanonical(entry["inputs"])
        groups, _ = ia.head_group_assets(inputs["assets"], inputs["market"]["market_income_gbp_by_agent"])
        with self.assertRaisesRegex(ValueError, "income"):
            ia.a4_net_revenue_for_decidable_groups(groups, investment_mode, entry["cashflow_inputs"])

    def test_a4_path_skips_denied_and_site_data_groups_before_any_a4_call(self):
        """Review M0-P0-7-S1 round 2: Nuclear and hydro beside thermal must not reach deducts_energy_cost."""
        entry = {row["id"]: row for row in self.record["scenarios"]}["eligibility_and_grouping"]
        inputs = REC.decanonical(entry["inputs"])
        income = inputs["market"]["market_income_gbp_by_agent"]
        technology = {row["asset_id"]: row["technology"] for row in inputs["assets"]}
        zero = {"hydrogen_income_gbp": 0.0, "generation_cost_gbp_per_mwh": 0.0, "fuel_cost_gbp_per_mwh": 0.0,
                "carbon_cost_gbp_per_mwh": 0.0, "unit_time_cost_gbp_per_mwh": 0.0}
        costs = {"CCGT": {"fuel_cost_gbp_per_mwh": 35.0, "carbon_cost_gbp_per_mwh": 22.0,
                          "unit_time_cost_gbp_per_mwh": 3.0},
                 "bio_and_waste": {"fuel_cost_gbp_per_mwh": 30.0, "unit_time_cost_gbp_per_mwh": 5.0},
                 "solar": {"generation_cost_gbp_per_mwh": 0.0001}}
        # A row for every asset, including Nuclear, hydro and coal with zero fuel and carbon cost:
        # computed for those, A4 has no basis and raises.
        cashflow = {asset_id: {"technology": tech, "electricity_income_gbp": float(income.get(asset_id, 0.0)),
                               "generated_mwh": 1000.0, **zero, **costs.get(tech, {})}
                    for asset_id, tech in technology.items()}
        for asset_id in ("nuclear-1", "hydro-1", "coal-1"):
            row = dict(cashflow[asset_id])
            with self.subTest(direct=asset_id), self.assertRaises(ValueError):
                ia.scheme_c_investment_net_revenue(**row)
        groups, _ = ia.head_group_assets(inputs["assets"], income)
        self.assertTrue({"Nuclear", "Hydro_natural_flow", "coal"} <= {group["technology"] for group in groups})
        cashflow_costs = cost_rows(cashflow)
        rows = ia.a4_net_revenue_for_decidable_groups(groups, investment_mode, cashflow_costs)
        self.assertEqual(set(rows), {"ccgt-north", "ccgt-south", "solar-x1", "commissioned:model:solar-x2",
                                     "bio-silent"})
        self.assertEqual({asset_id: row["basis"] for asset_id, row in rows.items()},
                         {"ccgt-north": ia.NET_REVENUE_BASIS_THERMAL, "ccgt-south": ia.NET_REVENUE_BASIS_THERMAL,
                          "bio-silent": ia.NET_REVENUE_BASIS_THERMAL, "solar-x1": ia.NET_REVENUE_BASIS_GROSS,
                          "commissioned:model:solar-x2": ia.NET_REVENUE_BASIS_GROSS})
        net = {asset_id: row["net_revenue_gbp"] for asset_id, row in rows.items()}
        net_groups, ineligible_assets = ia.head_group_assets(inputs["assets"], net)
        caps = ia.merge_headroom_caps(row["allowed_additions_mw"] for row in inputs["headroom"])
        result = ia.head_decide_accounts(net_groups, caps, investment_mode)
        head = entry["head_decision"]["extensions"]
        self.assertEqual(ineligible_assets, head["ineligible_assets"])
        self.assertEqual(
            [{"investment_owner_id": row["owner"], "technology": row["technology"], "reason": row["skipped"]}
             for row in result["outcomes"] if "skipped" in row],
            head["ineligible_groups"])
        # Fail closed on the decidable side: a missing row or a row of another technology.
        for broken in ({k: v for k, v in cashflow_costs.items() if k != "bio-silent"},
                       {**cashflow_costs, "solar-x1": {**cashflow_costs["solar-x1"], "technology": "onshore"}},
                       {**cashflow_costs, "ccgt-south": {k: v for k, v in cashflow_costs["ccgt-south"].items()
                                                         if k != "unit_time_cost_gbp_per_mwh"}}):
            with self.subTest(broken=sorted(set(cashflow_costs) ^ set(broken)) or "row"), \
                    self.assertRaises((ValueError, TypeError)):
                ia.a4_net_revenue_for_decidable_groups(groups, investment_mode, broken)
        # Skipped groups need no row at all.
        decidable_only = {asset_id: cashflow_costs[asset_id] for asset_id in rows}
        self.assertEqual(ia.a4_net_revenue_for_decidable_groups(groups, investment_mode, decidable_only), rows)


class DecisionA7NoVreStorageFomInDecideTest(unittest.TestCase):
    """DECISIONS A7 (lead ruling item 3): no VRE or storage FOM term enters decide().

    The fixed OPEX of VRE and storage is folded into levelised CAPEX; a
    separate FOM on those assets must not move any recommendation, size or
    retirement. (The headline-cost half of the rule is tested with the cost
    ledger in tests/test_p07_cost_ledger_v2.py.)
    """

    def test_vre_and_storage_fom_does_not_move_the_decision(self):
        from dataclasses import replace

        record = json.loads(RECORD.read_text(encoding="utf-8"))
        checked = 0
        for entry in record["scenarios"]:
            run, state, market, headroom = REC.inputs_from_record(entry)
            technologies = {asset.technology for asset in state.assets if asset.capacity_mw > 0}
            if not technologies or not technologies <= ia.GROSS_PROFIT_TECHNOLOGIES:
                continue
            baseline = SchemeCAgentInvestmentDefinition().decide(run, state, market, headroom)
            heavy = replace(state, assets=tuple(
                replace(asset, extensions={**dict(asset.extensions), "annual_fixed_opex_gbp": 9.9e9,
                                           "fixed_om_basis": "test:A7"})
                for asset in state.assets))
            decision = SchemeCAgentInvestmentDefinition().decide(run, heavy, market, headroom)
            with self.subTest(entry["id"]):
                self.assertEqual(
                    [(p.agent_id, p.technology, p.capacity_mw.hex(), p.extensions["investment_recommendation"])
                     for p in decision.proposals],
                    [(p.agent_id, p.technology, p.capacity_mw.hex(), p.extensions["investment_recommendation"])
                     for p in baseline.proposals])
                self.assertEqual(_json_text(decision.retirements_mw), _json_text(baseline.retirements_mw))
                checked += 1
        self.assertGreaterEqual(checked, 4)


if __name__ == "__main__":
    unittest.main()
