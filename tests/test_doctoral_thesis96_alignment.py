"""Independent numerical examples from final9.6, Chapter 4, not source parity.

These tests deliberately distinguish the thesis's profit/annual-capital rule
from the frozen old program's operating-surplus/total-capital rule.
"""
from dataclasses import replace
import math
import unittest

from gridform_core.builtin.scheme_c_1000twh import doctoral_policy as policy


def account(name="A", *, capacity=100.0, surplus=108.0, annual_capital=100.0,
            capex=10.0, preferred=0.076, technology="solar"):
    return {"account_id": name, "technology": technology,
            "current_capacity_mw": capacity, "operating_surplus_gbp": surplus,
            "annualized_capital_cost_gbp": annual_capital,
            "capital_cost_per_mw_gbp": capex, "replacement_capital_gbp": capacity * capex,
            "preferred_rate": preferred, "target_payback_years": 25.0}


class Thesis96InvestmentTests(unittest.TestCase):
    def evaluate(self, rows, caps):
        self.assertTrue(callable(getattr(policy, "evaluate_thesis96_investment_accounts", None)),
                        "final9.6 annual-profit investment rule is missing")
        return policy.evaluate_thesis96_investment_accounts(rows, caps)

    def test_profit_is_after_annual_capital_and_high_raises_funding_to_cap(self):
        row = self.evaluate([account()], {"solar": 20})[0]
        self.assertEqual(row["annual_profit_gbp"], 8)
        self.assertEqual(row["payback_rate"], 0.08)
        self.assertEqual(row["recommendation"], "Invest_High")
        self.assertEqual(row["accepted_addition_mw"], 20)
        self.assertEqual(row["profit_funded_addition_mw"], 0.8)
        self.assertEqual(row["externally_funded_capital_gbp"], 192)

    def test_high_vre_cap_shares_follow_capacity_not_profit(self):
        rows = [account("small", capacity=25, surplus=40, annual_capital=25),
                account("large", capacity=75, surplus=81, annual_capital=75)]
        result = self.evaluate(rows, {"solar": 20})
        self.assertEqual([r["accepted_addition_mw"] for r in result], [5, 15])
        reverse = self.evaluate(list(reversed(rows)), {"solar": 20})
        self.assertEqual([r["accepted_addition_mw"] for r in reverse], [15, 5])

    def test_four_bands_and_equality_do_not_spend_depreciation(self):
        cases = [(108, "Invest_High", 20, 0), (107.6, "Invest_Profit", 0.76, 0),
                 (105, "Invest_Profit", 0.5, 0), (100, "Do_Nothing", 0, 0),
                 (90, "Do_Nothing", 0, 0), (0, "Do_Nothing", 0, 0),
                 (-2, "Deplete", 0, 5)]
        for surplus, band, addition, retirement in cases:
            with self.subTest(surplus=surplus):
                row = self.evaluate([account(surplus=surplus)], {"solar": 20})[0]
                self.assertEqual(row["recommendation"], band)
                self.assertAlmostEqual(row["accepted_addition_mw"], addition)
                self.assertEqual(row["retirement_mw"], retirement)

    def test_missing_annual_capital_and_nonfinite_cashflow_are_not_defaults(self):
        row = account()
        del row["annualized_capital_cost_gbp"]
        for bad in (row, account(annual_capital=0), account(surplus=math.nan)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.evaluate([bad], {"solar": 20})

    def test_nuclear_and_direct_electrolysis_remain_excluded(self):
        for technology in ("Nuclear", "electrolyzer"):
            row = self.evaluate([account(technology=technology, surplus=1000)], {technology: 100})[0]
            self.assertEqual(row["accepted_addition_mw"], 0)
            self.assertEqual(row["retirement_mw"], 0)

    def test_storage_profit_floor_does_not_accidentally_overspend_shared_cap(self):
        rows = [account("rich", surplus=1100, technology="1c_battery", preferred=.12),
                account("small", surplus=120, technology="1c_battery", preferred=.12)]
        result = self.evaluate(rows, {"1c_battery": 150})
        self.assertEqual([r["accepted_addition_mw"] for r in result], [100, 50])
        self.assertEqual(sum(r["accepted_addition_mw"] for r in result), 150)
        reversed_result = self.evaluate(list(reversed(rows)), {"1c_battery": 150})
        self.assertEqual([r["accepted_addition_mw"] for r in reversed_result], [50, 100])

    def test_proposal_preserves_regional_profit_and_external_funding_lineage(self):
        from test_doctoral_investment_alignment import typed_inputs
        run, state, market, caps, _ = typed_inputs()
        run = replace(run, scientific_parameters={"doctoral.investment_basis": "thesis_final9.6"})
        state = replace(state, assets=tuple(replace(a, extensions={**a.extensions,
            "annualized_capital_cost_gbp": a.capacity_mw, "preferred_rate": .076}) for a in state.assets))
        accounts = {a.asset_id: {"operating_surplus_gbp": a.capacity_mw * 1.08} for a in state.assets}
        decision = policy.decide_doctoral_investment(run, state, market, caps, accounts)
        self.assertEqual(sum(p.extensions.get("profit_funded_capital_gbp", 0) for p in decision.proposals), 16)
        self.assertEqual(sum(p.extensions.get("externally_funded_capital_gbp", 0) for p in decision.proposals), 84)
        for proposal in decision.proposals:
            self.assertAlmostEqual(proposal.extensions["profit_funded_capital_gbp"]
                + proposal.extensions["externally_funded_capital_gbp"], proposal.extensions["total_capex_gbp"])
            self.assertEqual(proposal.extensions["funding_status"], "planned_not_drawn")

    def test_vre_cap_subtracts_all_operational_available_generation(self):
        self.assertTrue(callable(getattr(policy, "thesis96_vre_annual_expansion_cap", None)),
                        "final9.6 net-demand VRE cap is missing")
        cap = policy.thesis96_vre_annual_expansion_cap(
            [100.0] * 300, [75.0] * 300, [0.5] * 300)
        self.assertAlmostEqual(cap, 10.0, places=5)
        self.assertEqual(policy.thesis96_vre_annual_expansion_cap(
            [100.0] * 300, [110.0] * 300, [0.5] * 300), 0.0)

    def test_typed_adapter_selects_explicit_thesis_basis(self):
        from test_doctoral_investment_alignment import typed_inputs
        run, state, market, caps, old_accounts = typed_inputs()
        run = replace(run, scientific_parameters={
            **dict(run.scientific_parameters), "doctoral.investment_basis": "thesis_final9.6"})
        # Hand-set complete annual economics, independent of the cost builder.
        assets = tuple(replace(a, extensions={**dict(a.extensions),
                    "annualized_capital_cost_gbp": a.capacity_mw,
                    "preferred_rate": 0.076}) for a in state.assets)
        state = replace(state, assets=assets)
        accounts = {a.asset_id: {"operating_surplus_gbp": a.capacity_mw * 1.08,
                                "net_revenue_gbp": a.capacity_mw * 1.08} for a in assets}
        result = policy.decide_doctoral_investment(run, state, market, caps, accounts)
        outcomes = result.extensions["doctoral_investment_accounts"]
        self.assertEqual([r["recommendation"] for r in outcomes], ["Invest_High", "Invest_High"])
        self.assertTrue(all("annual_profit_gbp" in r for r in outcomes),
                        "typed adapter ignored the final9.6 investment basis")
        self.assertEqual([r["annual_profit_gbp"] for r in outcomes], [8, 8])
        self.assertEqual(result.extensions["investment_basis"], "thesis_final9.6")


class Thesis96AnnualCashTests(unittest.TestCase):
    def fixture(self):
        # Constructed annual totals test accounting only, not annual dispatch.
        state = {"year": 2025, "assets": [{"asset_id": "solar", "extensions": {
            "investment_owner_id": "A", "annual_fixed_opex_gbp": 10.0,
            "annualized_capital_cost_gbp": 100.0}}]}
        market = {"ahead_income_gbp_by_asset": {"solar": 120.0},
                  "balancing_income_gbp_by_asset": {"solar": 8.0},
                  "operating_cost_gbp_by_asset": {"solar": 20.0},
                  "period_hours": 0.5, "period_coverage": {"year": 2025,
                    "start_period_index": 0, "end_period_index_exclusive": 17520,
                    "period_count": 17520, "annual_complete": True}}
        return market, state

    def test_fixed_opex_capital_and_policy_enter_profit_once(self):
        from gridform_core import doctoral_ledgers
        self.assertTrue(callable(getattr(doctoral_ledgers, "build_thesis96_asset_accounts", None)),
                        "annual thesis9.6 cashflow bridge is missing")
        market, state = self.fixture()
        result = doctoral_ledgers.build_thesis96_asset_accounts(market, state,
            {"scenario": "decarb", "cm_income_gbp_by_asset": {"solar": 5.0},
             "decarb_income_gbp_by_asset": {"solar": 10.0},
             "ancillary_income_gbp_by_asset": {"solar": 2.0}})["solar"]
        self.assertEqual(result["operating_cost_gbp"], 30)
        self.assertEqual(result["operating_surplus_gbp"], 115)
        self.assertEqual(result["annual_profit_gbp"], 15)
        self.assertEqual(result["net_profit_gbp"], 15)
        self.assertEqual(result["payback_rate"], 0.15)

    def test_partial_year_cannot_be_turned_into_annual_investment_cash(self):
        from gridform_core import doctoral_ledgers
        self.assertTrue(callable(getattr(doctoral_ledgers, "build_thesis96_asset_accounts", None)))
        market, state = self.fixture()
        market["period_coverage"]["period_count"] = 1488
        with self.assertRaisesRegex(ValueError, "annual"):
            doctoral_ledgers.build_thesis96_asset_accounts(market, state, {"scenario": "basic"})

    def test_missing_fixed_opex_is_not_silently_zero(self):
        from gridform_core import doctoral_ledgers
        self.assertTrue(callable(getattr(doctoral_ledgers, "build_thesis96_asset_accounts", None)))
        market, state = self.fixture()
        del state["assets"][0]["extensions"]["annual_fixed_opex_gbp"]
        with self.assertRaisesRegex(ValueError, "annual_fixed_opex"):
            doctoral_ledgers.build_thesis96_asset_accounts(market, state, {"scenario": "basic"})

    def test_pumped_table_annual_cost_is_not_annuitized_twice(self):
        from gridform_core.builtin.scheme_c_1000twh import doctoral_commissioning
        from test_doctoral_commissioning_alignment import state_fixture
        from gridform_core.asset_economics import validate_asset_economics
        self.assertTrue(callable(getattr(doctoral_commissioning, "apply_thesis96_pumped_schedule", None)),
                        "final9.6 Table 10 annual-cost schedule is missing")
        original = state_fixture(2034)
        result = doctoral_commissioning.apply_thesis96_pumped_schedule(original)
        pumped = result.assets[0]
        self.assertEqual(pumped.extensions["annualized_capital_cost_gbp"], 596_400_000)
        self.assertEqual(pumped.extensions["annual_fixed_opex_gbp"], 134_900_000)
        self.assertEqual((pumped.capacity_mw, pumped.energy_capacity_mwh), (5687.9, 70800))
        self.assertEqual(doctoral_commissioning.apply_thesis96_pumped_schedule(result), result)
        self.assertIs(result.assets[1], original.assets[1])
        self.assertEqual(pumped.extensions["weather_source_weights"], {"sentinel": 1.0})
        validate_asset_economics(pumped)


if __name__ == "__main__":
    unittest.main()
