"""P0-7 investment corrections through the production modules (plan 4.7 S4, S6-S8).

* ThermalNetRevenueTests - decision A4 in both profiles (p07.thermal-net-revenue):
  a CCGT paid exactly its marginal cost proposes nothing; paid 10 GBP/MWh
  below it, it retires per the HEAD rule (45.625 MW); VRE keeps gross = profit;
  a market without ``agent_cashflow`` fails closed for a thermal group.
"""
from __future__ import annotations

import importlib.util
import math
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core import agent_cashflow
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCAgentInvestmentDefinition
from gridform_core.methodology import PROFILE_PARAMETER, REFERENCE_PROFILE_ID, default_profile_id
from gridform_core.v2.contracts import MarketYearResult, OperatingState

ROOT = Path(__file__).resolve().parents[1]
YEAR = 2030


def _recorder():
    spec = importlib.util.spec_from_file_location("p07_record_head_decide", ROOT / "scripts" / "p07_record_head_decide.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REC = _recorder()
PROFILES = (REFERENCE_PROFILE_ID, default_profile_id())


def _run(profile_id: str, run_id: str = "p07-toy"):
    run = REC.build_run(run_id)
    return replace(run, scientific_parameters={**dict(run.scientific_parameters), PROFILE_PARAMETER: profile_id})


def _market(income: dict[str, float], rows: dict[str, dict[str, object]] | None) -> MarketYearResult:
    extensions = {} if rows is None else {
        agent_cashflow.EXTENSION_KEY: agent_cashflow.extension(rows, psm_module_id="toy", cost_basis="toy")}
    return MarketYearResult("toy-market", YEAR, "toy", "1", {}, income, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0,
                            extensions=extensions)


def _ccgt_row(mwh: float = 876_000.0) -> dict[str, object]:
    # gen_cost 60 GBP/MWh = generation 0.5 + fuel 40 + carbon 18 + unit time 1.5
    return agent_cashflow.cashflow_row("CCGT", mwh, {
        "generation_cost_gbp_per_mwh": 0.5, "fuel_cost_gbp_per_mwh": 40.0,
        "carbon_cost_gbp_per_mwh": 18.0, "unit_time_cost_gbp_per_mwh": 1.5}, cost_basis="toy")


class ThermalNetRevenueTests(unittest.TestCase):
    """Plan 6.7 P4-01 toys: 100 MW CCGT, 876,000 MWh, CAPEX 4.8e6 GBP/MW, life and target 25 years."""

    def _state(self):
        asset = REC._asset("ccgt-toy", "CCGT", 100.0, capex_per_mw=4_800_000.0, life=25.0, preferred_rate=0.08,
                           target_payback_years=25.0, investment_owner_id="owner-ccgt")
        return OperatingState(YEAR, (asset,), ())

    def _decide(self, profile_id, income, rows):
        return SchemeCAgentInvestmentDefinition().decide(_run(profile_id), self._state(), _market(income, rows), ())

    def test_price_equal_to_marginal_cost_proposes_nothing(self):
        income = {"ccgt-toy": 876_000.0 * 60.0}
        for profile_id in PROFILES:
            with self.subTest(profile=profile_id):
                decision = self._decide(profile_id, income, {"ccgt-toy": _ccgt_row()})
                self.assertEqual(decision.proposals, ())
                self.assertEqual(dict(decision.retirements_mw), {})
                self.assertEqual(decision.extensions["a4_net_revenue"]["thermal_operating_cost_gbp_by_group"],
                                 {"owner-ccgt|CCGT|GB": 876_000.0 * 60.0})

    def test_price_ten_below_marginal_cost_retires_per_rule(self):
        income = {"ccgt-toy": 876_000.0 * 50.0}
        for profile_id in PROFILES:
            with self.subTest(profile=profile_id):
                decision = self._decide(profile_id, income, {"ccgt-toy": _ccgt_row()})
                self.assertEqual(decision.proposals, ())
                # loss 8.76e6 x target 25 / 4.8e6 GBP/MW = 45.625 MW
                self.assertTrue(math.isclose(decision.retirements_mw["ccgt-toy"], 45.625, rel_tol=1e-12))

    def test_rounding_level_loss_is_not_a_retirement(self):
        """A bid-at-cost unit paid its cost up to rounding neither retires ~1e-12 MW nor invests."""
        cost = 876_000.0 * 60.0
        for income in (cost * (1 - 1e-12), cost * (1 + 1e-12)):
            with self.subTest(income=income):
                decision = self._decide(default_profile_id(), {"ccgt-toy": income}, {"ccgt-toy": _ccgt_row()})
                self.assertEqual((decision.proposals, dict(decision.retirements_mw)), ((), {}))
        decision = self._decide(default_profile_id(), {"ccgt-toy": cost * (1 - 1e-6)}, {"ccgt-toy": _ccgt_row()})
        self.assertGreater(decision.retirements_mw["ccgt-toy"], 0.0)

    def test_head_gross_rule_would_have_built_10_95_mw(self):
        """The HEAD (gross) outcome the correction removes, through the same rule with zero running cost."""
        income = {"ccgt-toy": 876_000.0 * 60.0}
        decision = self._decide(REFERENCE_PROFILE_ID, income, {"ccgt-toy": _ccgt_row(0.0)})
        self.assertEqual([(p.capacity_mw, p.extensions["investment_recommendation"]) for p in decision.proposals],
                         [(10.95, "Invest_High")])

    def test_missing_agent_cashflow_fails_closed_for_thermal(self):
        for profile_id in PROFILES:
            with self.subTest(profile=profile_id), self.assertRaisesRegex(ValueError, "agent_cashflow"):
                self._decide(profile_id, {"ccgt-toy": 1.0}, None)
            with self.subTest(profile=profile_id, row="missing"), self.assertRaisesRegex(ValueError, "ccgt-toy"):
                self._decide(profile_id, {"ccgt-toy": 1.0}, {})

    def test_vre_needs_no_cashflow_and_keeps_gross_revenue(self):
        solar = REC._asset("solar-toy", "solar", 10.0, capex_per_mw=600_000.0, investment_owner_id="owner-s")
        state = OperatingState(YEAR, (solar,), ())
        headroom = REC.build_inputs({"id": "toy", "assets": [solar], "income": {"solar-toy": 600_000.0},
                                     "headroom": [{"module_id": "vre-expansion-cap",
                                                   "allowed": {"solar": 100.0}}]})[3]
        for profile_id in PROFILES:
            with self.subTest(profile=profile_id):
                decision = SchemeCAgentInvestmentDefinition().decide(
                    _run(profile_id), state, _market({"solar-toy": 600_000.0}, None), headroom)
                self.assertEqual([(p.capacity_mw, p.extensions["investment_recommendation"])
                                  for p in decision.proposals], [(1.0, "Invest_High")])


if __name__ == "__main__":
    unittest.main()
