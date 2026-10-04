"""P0-7 S1: pure investment-decision arithmetic (gridform_core.investment_accounts)."""
from __future__ import annotations

import ast
import json
import math
import random
import unittest
from pathlib import Path

import numpy as np

from gridform_core import investment_accounts as ia
from gridform_core.builtin.scheme_c_1000twh import doctoral_policy

ROOT = Path(__file__).resolve().parents[1]


class FiniteNumberTest(unittest.TestCase):
    def test_rejects_non_numbers_and_non_finite_values(self):
        for value in (True, False, None, "1.0", [1.0], math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ia.finite_number(value, "x")
        self.assertEqual(ia.finite_number(3, "x"), 3.0)
        self.assertEqual(ia.finite_number(-2.5, "x"), -2.5)
        with self.assertRaises(ValueError):
            ia.finite_number(-1e-300, "x", nonnegative=True)
        self.assertEqual(ia.finite_number(0.0, "x", nonnegative=True), 0.0)

    def test_numpy_scalars_are_numbers_but_numpy_bools_are_not(self):
        """pandas / sqlite aggregates arrive as numpy scalars (S2-S4 cashflow)."""
        for value, expected in ((np.int64(3), 3.0), (np.int32(-2), -2.0), (np.float32(1.5), 1.5),
                                (np.float64(2.25), 2.25), (np.uint8(7), 7.0)):
            with self.subTest(type=type(value).__name__):
                result = ia.finite_number(value, "x")
                self.assertIs(type(result), float)
                self.assertEqual(result, expected)
        for value in (np.bool_(True), np.bool_(False), np.float32("nan"), np.float64("inf")):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                ia.finite_number(value, "x")
        with self.assertRaises(ValueError):
            ia.finite_number(np.int64(-1), "x", nonnegative=True)
        parsed = ia.require_agent_cashflow(
            {"a": {"market_income_gbp": np.int64(5), "operating_cost_gbp": np.float32(0.5)}}, ["a"])
        self.assertEqual(parsed, {"a": {"market_income_gbp": 5.0, "operating_cost_gbp": 0.5}})


class RequireAgentCashflowTest(unittest.TestCase):
    ROWS = {
        "a": {"market_income_gbp": -5.0, "operating_cost_gbp": 0.0},
        "b": {"market_income_gbp": 10.0, "operating_cost_gbp": 2.0},
        "unused": {"market_income_gbp": 1.0, "operating_cost_gbp": 1.0},
    }

    def test_valid_rows_parse_and_negative_income_is_allowed(self):
        parsed = ia.require_agent_cashflow(self.ROWS, ["a", "b"])
        self.assertEqual(parsed, {"a": {"market_income_gbp": -5.0, "operating_cost_gbp": 0.0},
                                  "b": {"market_income_gbp": 10.0, "operating_cost_gbp": 2.0}})

    def test_every_failure_mode_raises_instead_of_defaulting_to_zero(self):
        cases = {
            "container_not_mapping": ([("a", {})], ["a"]),
            "asset_missing": (self.ROWS, ["a", "absent"]),
            "row_not_mapping": ({"a": 5.0}, ["a"]),
            "field_missing": ({"a": {"market_income_gbp": 1.0}}, ["a"]),
            "nan": ({"a": {"market_income_gbp": math.nan, "operating_cost_gbp": 0.0}}, ["a"]),
            "infinite": ({"a": {"market_income_gbp": 1.0, "operating_cost_gbp": math.inf}}, ["a"]),
            "negative_cost": ({"a": {"market_income_gbp": 1.0, "operating_cost_gbp": -0.01}}, ["a"]),
            "boolean": ({"a": {"market_income_gbp": True, "operating_cost_gbp": 0.0}}, ["a"]),
            "string": ({"a": {"market_income_gbp": "1", "operating_cost_gbp": 0.0}}, ["a"]),
            "none": ({"a": {"market_income_gbp": None, "operating_cost_gbp": 0.0}}, ["a"]),
        }
        for name, (rows, ids) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                ia.require_agent_cashflow(rows, ids)

    def test_nonnegative_fields_must_be_required_fields(self):
        with self.assertRaises(ValueError):
            ia.require_agent_cashflow(self.ROWS, ["a"], fields=("market_income_gbp",))


class SchemeCNetRevenueTest(unittest.TestCase):
    """Decision A4: thermal nets energy x gen_cost; VRE and storage keep gross."""

    CCGT = dict(technology="CCGT", generated_mwh=182_500.0, fuel_cost_gbp_per_mwh=35.0,
                carbon_cost_gbp_per_mwh=22.0, unit_time_cost_gbp_per_mwh=3.0)

    def test_ccgt_at_price_equal_to_gen_cost_has_zero_net(self):
        row = ia.scheme_c_investment_net_revenue(electricity_income_gbp=10_950_000.0, **self.CCGT)
        self.assertEqual(row["gen_cost_gbp_per_mwh"], 60.0)
        self.assertEqual(row["operating_cost_gbp"], 10_950_000.0)
        self.assertEqual(row["net_revenue_gbp"], 0.0)
        self.assertEqual(row["basis"], ia.NET_REVENUE_BASIS_THERMAL)

    def test_ccgt_below_gen_cost_loses_money(self):
        row = ia.scheme_c_investment_net_revenue(electricity_income_gbp=9_125_000.0, **self.CCGT)
        self.assertEqual(row["net_revenue_gbp"], -1_825_000.0)

    def test_fuel_only_and_carbon_only_assets_deduct(self):
        biomass = ia.scheme_c_investment_net_revenue(
            technology="bio_and_waste", electricity_income_gbp=24e6, generated_mwh=3e5, fuel_cost_gbp_per_mwh=30.0,
            unit_time_cost_gbp_per_mwh=5.0)
        self.assertEqual((biomass["operating_cost_gbp"], biomass["net_revenue_gbp"]), (10.5e6, 13.5e6))
        carbon_only = ia.scheme_c_investment_net_revenue(
            technology="OCGT", electricity_income_gbp=1.6e6, generated_mwh=1e4, generation_cost_gbp_per_mwh=1.0,
            carbon_cost_gbp_per_mwh=90.0, unit_time_cost_gbp_per_mwh=9.0)
        self.assertEqual(carbon_only["gen_cost_gbp_per_mwh"], 100.0)
        self.assertEqual(carbon_only["net_revenue_gbp"], 6e5)

    def test_vre_and_storage_gross_is_profit(self):
        vre = ia.scheme_c_investment_net_revenue(
            technology="solar", electricity_income_gbp=6e6, generated_mwh=1e5,
            generation_cost_gbp_per_mwh=0.0001, unit_time_cost_gbp_per_mwh=0.0)
        storage = ia.scheme_c_investment_net_revenue(
            technology="1c_battery", electricity_income_gbp=-3.0, generated_mwh=4e4)
        offshore = ia.scheme_c_investment_net_revenue(
            technology="offshore", electricity_income_gbp=5.0, generated_mwh=1.0,
            generation_cost_gbp_per_mwh=7.0, unit_time_cost_gbp_per_mwh=2.0)
        for row, gross in ((vre, 6e6), (storage, -3.0), (offshore, 5.0)):
            self.assertEqual(row["basis"], ia.NET_REVENUE_BASIS_GROSS)
            self.assertIsNone(row["gen_cost_gbp_per_mwh"])
            self.assertEqual(row["operating_cost_gbp"], 0.0)
            self.assertEqual(row["net_revenue_gbp"], gross)

    def test_hydrogen_income_joins_total_income(self):
        row = ia.scheme_c_investment_net_revenue(
            technology="gas", electricity_income_gbp=100.0, hydrogen_income_gbp=50.0, generated_mwh=1.0,
            fuel_cost_gbp_per_mwh=10.0)
        self.assertEqual((row["total_income_gbp"], row["net_revenue_gbp"]), (150.0, 140.0))

    def test_invalid_inputs_fail_closed(self):
        for kwargs in ({"generated_mwh": -1.0}, {"fuel_cost_gbp_per_mwh": math.nan},
                       {"carbon_cost_gbp_per_mwh": -1.0}, {"electricity_income_gbp": math.inf}):
            payload = {"technology": "CCGT", "electricity_income_gbp": 1.0, "generated_mwh": 1.0, **kwargs}
            with self.subTest(kwargs), self.assertRaises(ValueError):
                ia.scheme_c_investment_net_revenue(**payload)


    def test_thermal_is_decided_by_technology_not_by_cost(self):
        """Review M0-P0-7-S1 #1: zero fuel and carbon cost does not make gas gross."""
        for technology in sorted(ia.THERMAL_TECHNOLOGIES):
            with self.subTest(technology):
                row = ia.scheme_c_investment_net_revenue(
                    technology=technology, electricity_income_gbp=1e6, generated_mwh=1e4,
                    generation_cost_gbp_per_mwh=5.0, unit_time_cost_gbp_per_mwh=3.0)
                self.assertEqual(row["basis"], ia.NET_REVENUE_BASIS_THERMAL)
                self.assertEqual(row["gen_cost_gbp_per_mwh"], 8.0)
                self.assertEqual(row["operating_cost_gbp"], 8e4)
                self.assertEqual(row["net_revenue_gbp"], 9.2e5)
                self.assertEqual(row["technology"], technology)

    def test_vre_or_storage_with_fuel_or_carbon_cost_is_an_error(self):
        for technology in sorted(ia.GROSS_PROFIT_TECHNOLOGIES):
            for cost in ({"carbon_cost_gbp_per_mwh": 1.0}, {"fuel_cost_gbp_per_mwh": 0.5}):
                with self.subTest(technology=technology, cost=cost), self.assertRaises(ValueError):
                    ia.scheme_c_investment_net_revenue(
                        technology=technology, electricity_income_gbp=1.0, generated_mwh=1.0, **cost)

    def test_other_technologies_deduct_only_with_a_fuel_or_carbon_cost(self):
        coal = ia.scheme_c_investment_net_revenue(
            technology="coal", electricity_income_gbp=100.0, generated_mwh=2.0, fuel_cost_gbp_per_mwh=10.0)
        self.assertEqual((coal["basis"], coal["net_revenue_gbp"]), (ia.NET_REVENUE_BASIS_THERMAL, 80.0))
        for technology in ("Nuclear", "Hydro_natural_flow", "pumped_hydro", "unknown"):
            with self.subTest(technology), self.assertRaises(ValueError):
                ia.scheme_c_investment_net_revenue(
                    technology=technology, electricity_income_gbp=1.0, generated_mwh=1.0)
        for technology in ("", None, 5):
            with self.subTest(technology=technology), self.assertRaises(ValueError):
                ia.scheme_c_investment_net_revenue(
                    technology=technology, electricity_income_gbp=1.0, generated_mwh=1.0,
                    fuel_cost_gbp_per_mwh=1.0)
        with self.assertRaises(TypeError):
            ia.scheme_c_investment_net_revenue(electricity_income_gbp=1.0, generated_mwh=1.0)  # type: ignore[call-arg]


class TechnologyClassTest(unittest.TestCase):
    """One thermal / VRE / storage classification for the repository."""

    def test_classes_are_disjoint(self):
        self.assertFalse(ia.THERMAL_TECHNOLOGIES & ia.GROSS_PROFIT_TECHNOLOGIES)
        self.assertEqual(ia.GROSS_PROFIT_TECHNOLOGIES, ia.VRE_TECHNOLOGIES | ia.STORAGE_TECHNOLOGIES)

    def test_classes_match_the_investment_eligibility_policy(self):
        policy = json.loads((ROOT / "gridform_core/data/cem/investment_eligibility.json").read_text(encoding="utf-8"))
        modes = policy["modes"]
        self.assertEqual({tech for tech, mode in modes.items() if mode == "explicit_uncapped"},
                         set(ia.THERMAL_TECHNOLOGIES))
        self.assertEqual({tech for tech, mode in modes.items() if mode == "headroom_required"},
                         set(ia.GROSS_PROFIT_TECHNOLOGIES))

    def test_classes_match_the_doctoral_policy(self):
        self.assertEqual(set(doctoral_policy.VRE_TECHNOLOGIES), set(ia.VRE_TECHNOLOGIES))
        self.assertEqual(set(doctoral_policy.STORAGE_TECHNOLOGIES), set(ia.STORAGE_TECHNOLOGIES))
        self.assertTrue(set(doctoral_policy.THERMAL_HIGH_TECHNOLOGIES) <= ia.THERMAL_TECHNOLOGIES)

    def test_doctoral_marginal_cost_uses_the_shared_thermal_set(self):
        from gridform_core import canonical_psm_data

        self.assertIs(canonical_psm_data.THERMAL_TECHNOLOGIES, ia.THERMAL_TECHNOLOGIES)
        source = (ROOT / "gridform_core/canonical_psm_data.py").read_text(encoding="utf-8")
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == "_doctoral_marginal_cost")
        tests = [ast.unparse(node.test) for node in ast.walk(function) if isinstance(node, ast.If)]
        self.assertIn("technology in THERMAL_TECHNOLOGIES", tests)
        raw = {"gen_cost": 1.0, "unit_time_cost": 2.0}
        for technology in sorted(ia.THERMAL_TECHNOLOGIES):
            with self.subTest(technology), self.assertRaises(ValueError):
                canonical_psm_data._doctoral_marginal_cost(raw, technology, "fixture")
            self.assertEqual(canonical_psm_data._doctoral_marginal_cost(
                {**raw, "fuel_cost": 3.0, "carbon_price": 4.0}, technology, "fixture"), 10.0)
        self.assertEqual(canonical_psm_data._doctoral_marginal_cost(raw, "solar", "fixture"), 3.0)


class HeadRuleTest(unittest.TestCase):
    """The decomposed 35aadb3 v2 decide() rule; tiers are undiscounted (A6)."""

    def test_roi_tier_is_strict_at_relative_epsilon(self):
        capital, preferred, target = 1e8, 0.08, 25.0
        at = 8e6
        for factor, expected in ((1 + 1e-12, "Invest_High"), (1.0, "Invest_Profit"), (1 - 1e-12, "Invest_Profit")):
            net = at * factor
            with self.subTest(factor=factor):
                self.assertEqual(ia.head_tier(net / capital, preferred, capital / net, target), expected)

    def test_payback_tier_is_inclusive_at_relative_epsilon(self):
        roi, preferred, payback = 0.05, 0.08, 12.5
        self.assertEqual(ia.head_tier(roi, preferred, payback, 12.5), "Invest_Profit")
        self.assertEqual(ia.head_tier(roi, preferred, payback, 12.5 * (1 + 1e-12)), "Invest_Profit")
        self.assertEqual(ia.head_tier(roi, preferred, payback, 12.5 * (1 - 1e-12)), "Do_Nothing")
        self.assertEqual(ia.head_tier(roi, preferred, math.inf, 1e300), "Do_Nothing")

    def test_deplete_needs_a_loss_and_a_positive_unit_cost(self):
        self.assertTrue(ia.head_is_deplete(-1.0, 1.0))
        self.assertFalse(ia.head_is_deplete(-1.0, 0.0))
        self.assertFalse(ia.head_is_deplete(0.0, 1.0))
        account = ia.head_group_account([{"capacity_mw": 10.0, "income_gbp": -5.0, "extensions": {}}])
        self.assertEqual(account["replacement_capital_gbp"], 0.0)
        self.assertEqual(ia.head_recommendation(account), "Do_Nothing")

    def test_group_account_defaults_and_pooling(self):
        members = [
            {"capacity_mw": 10.0, "income_gbp": 6e6,
             "extensions": {"total_capex_gbp": 6e6, "economic_lifetime_years": 25.0}},
            {"capacity_mw": 5.0, "income_gbp": 3e6,
             "extensions": {"total_capex_gbp": 3e6, "economic_lifetime_years": 20.0,
                            "preferred_rate": 0.1, "annual_operational_cost_gbp": 1e6}},
        ]
        account = ia.head_group_account(members)
        self.assertEqual(account["capacity_mw"], 15.0)
        self.assertEqual(account["net_revenue_gbp"], 8e6)
        self.assertEqual(account["cost_per_mw_gbp"], 6e5)
        self.assertEqual(account["preferred_rate"], 0.1)
        self.assertEqual(account["economic_lifetime_years"], 20.0)
        self.assertEqual(account["target_payback_years"], 20.0)  # min over members, each defaulting to life
        self.assertEqual(account["payback_years"], 9e6 / 8e6)

    def test_retirement_is_capped_at_capacity(self):
        self.assertEqual(ia.head_retirement_mw(-1_825_000.0, 100.0, 25.0, 1e6), 45.625)
        self.assertEqual(ia.head_retirement_mw(-1e9, 100.0, 25.0, 1e6), 100.0)

    def test_requested_addition_is_net_over_unit_cost(self):
        self.assertEqual(ia.head_requested_addition_mw(10_950_000.0, 1e6), 10.95)

    def test_headroom_rows_merge_to_clamped_minimum(self):
        caps = ia.merge_headroom_caps([{"solar": 12.0, "onshore": 50.0}, {"onshore": 4.0, "offshore": -3.0}])
        self.assertEqual(caps, {"solar": 12.0, "onshore": 4.0, "offshore": 0.0})

    def test_greedy_allocation_spends_one_shared_budget_in_order(self):
        remaining = {"solar": 12.0}
        first = ia.head_greedy_allocation(10.0, "solar", "headroom_required", remaining)
        second = ia.head_greedy_allocation(10.0, "solar", "headroom_required", remaining)
        self.assertEqual((first, second, remaining["solar"]), (10.0, 2.0, 0.0))
        self.assertEqual(ia.head_greedy_allocation(5.0, "1c_battery", "headroom_required", remaining), 0.0)
        self.assertEqual(ia.head_greedy_allocation(7.0, "CCGT", "explicit_uncapped", remaining), 7.0)
        self.assertNotIn("CCGT", remaining)

    def test_owner_key(self):
        self.assertEqual(ia.head_investment_owner("a", {"investment_owner_id": "o"}), "o")
        self.assertEqual(ia.head_investment_owner("a", {"source_agent_id": "s"}), "s")
        self.assertEqual(ia.head_investment_owner("a", {}), "a")
        self.assertEqual(ia.head_investment_owner("commissioned:x", {}), "")

    def test_missing_income_is_zero_only_on_the_head_path(self):
        self.assertEqual(ia.head_income_lookup({"a": None}, "a"), 0.0)
        self.assertEqual(ia.head_income_lookup({}, "a"), 0.0)
        with self.assertRaises(ValueError):
            ia.require_agent_cashflow({}, ["a"])


class AllocateCappedRequestsTest(unittest.TestCase):
    def test_power_pool_scales_proportionally(self):
        result = ia.allocate_capped_requests(
            [{"request_id": "1c", "technology": "1c_battery", "requested_mw": 300.0},
             {"request_id": "05c", "technology": "0.5c_battery", "requested_mw": 200.0},
             {"request_id": "025c", "technology": "0.25c_battery", "requested_mw": 100.0}],
            pools={"power_battery_pool": {"cap_mw": 400.0,
                                          "technologies": ["1c_battery", "0.5c_battery", "0.25c_battery"]}})
        accepted = result["accepted_mw"]
        # 200 + 400/3 + 200/3 rounds to 400 + 1 ulp; the clamp takes that ulp from the largest share.
        self.assertAlmostEqual(accepted["1c"], 200.0, places=12)
        self.assertAlmostEqual(accepted["05c"], 400.0 / 3.0, places=12)
        self.assertAlmostEqual(accepted["025c"], 200.0 / 3.0, places=12)
        self.assertLessEqual(sum(accepted.values()), 400.0)
        self.assertAlmostEqual(result["pool_scale"]["power_battery_pool"], 2.0 / 3.0, places=15)

    def test_shared_technology_cap_splits_equal_requests_equally(self):
        result = ia.allocate_capped_requests(
            [{"request_id": "a", "technology": "solar", "requested_mw": 10.0},
             {"request_id": "b", "technology": "solar", "requested_mw": 10.0}],
            technology_caps={"solar": 12.0})
        self.assertEqual(result["accepted_mw"], {"a": 6.0, "b": 6.0})

    def test_technology_cap_applies_before_pool_cap(self):
        result = ia.allocate_capped_requests(
            [{"request_id": "1c", "technology": "1c_battery", "requested_mw": 300.0},
             {"request_id": "05c", "technology": "0.5c_battery", "requested_mw": 200.0},
             {"request_id": "025c", "technology": "0.25c_battery", "requested_mw": 100.0},
             {"request_id": "h2", "technology": "hydrogen_battery", "requested_mw": 900.0}],
            technology_caps={"1c_battery": 150.0},
            pools={"pool": {"cap_mw": 400.0, "technologies": ["1c_battery", "0.5c_battery", "0.25c_battery"]}})
        accepted = result["accepted_mw"]
        self.assertAlmostEqual(accepted["1c"], 150.0 * 400.0 / 450.0, places=12)
        self.assertAlmostEqual(accepted["05c"], 200.0 * 400.0 / 450.0, places=12)
        self.assertAlmostEqual(accepted["025c"], 100.0 * 400.0 / 450.0, places=12)
        self.assertEqual(accepted["h2"], 900.0)  # neither capped nor pooled
        self.assertEqual(result["technology_scale"], {"1c_battery": 0.5})

    def test_under_cap_requests_are_unchanged(self):
        result = ia.allocate_capped_requests(
            [{"request_id": "a", "technology": "solar", "requested_mw": 3.0}],
            technology_caps={"solar": 12.0}, pools={"p": {"cap_mw": 0.0, "technologies": []}})
        self.assertEqual(result["accepted_mw"], {"a": 3.0})
        self.assertEqual((result["technology_scale"], result["pool_scale"]), ({"solar": 1.0}, {"p": 1.0}))

    def test_zero_cap_and_invalid_requests(self):
        result = ia.allocate_capped_requests(
            [{"request_id": "a", "technology": "solar", "requested_mw": 3.0}], technology_caps={"solar": 0.0})
        self.assertEqual(result["accepted_mw"], {"a": 0.0})
        invalid = {
            "duplicate": dict(requests=[{"request_id": "a", "technology": "s", "requested_mw": 1.0}] * 2),
            "negative": dict(requests=[{"request_id": "a", "technology": "s", "requested_mw": -1.0}]),
            "nan": dict(requests=[{"request_id": "a", "technology": "s", "requested_mw": math.nan}]),
            "no_technology": dict(requests=[{"request_id": "a", "requested_mw": 1.0}]),
            "negative_cap": dict(requests=[], technology_caps={"s": -1.0}),
            "two_pools": dict(requests=[], pools={"p": {"cap_mw": 1.0, "technologies": ["s"]},
                                                  "q": {"cap_mw": 1.0, "technologies": ["s"]}}),
        }
        for name, kwargs in invalid.items():
            with self.subTest(name), self.assertRaises(ValueError):
                ia.allocate_capped_requests(**kwargs)


    def test_scaled_sums_never_exceed_the_cap(self):
        """Review M0-P0-7-S1 #5: strict sum <= cap (S7 acceptance), proportional to a few ulp."""
        rng = random.Random(20261005)
        technologies = ["1c_battery", "0.5c_battery", "0.25c_battery"]
        clamped = 0
        for case in range(3000):
            requests = [{"request_id": f"r{i}", "technology": rng.choice(technologies),
                         "requested_mw": rng.choice([rng.uniform(0, 1e4), rng.uniform(0, 1), float(rng.randint(0, 900))])}
                        for i in range(rng.randint(1, 9))]
            cap = rng.choice([rng.uniform(0, 5e3), float(rng.randint(0, 3000)), rng.uniform(0, 1e-3)])
            tech_caps = {tech: rng.uniform(0, 4e3) for tech in technologies if rng.random() < 0.3}
            result = ia.allocate_capped_requests(
                requests, technology_caps=tech_caps,
                pools={"pool": {"cap_mw": cap, "technologies": technologies}})
            accepted = result["accepted_mw"]
            values = [accepted[row["request_id"]] for row in requests]
            with self.subTest(case=case):
                self.assertLessEqual(sum(values), cap)
                self.assertLessEqual(math.fsum(values), cap)
                for row in requests:
                    value = accepted[row["request_id"]]
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, row["requested_mw"])
                    tech = row["technology"]
                    if tech in tech_caps:
                        members = [r["request_id"] for r in requests if r["technology"] == tech]
                        self.assertLessEqual(sum(accepted[key] for key in members), tech_caps[tech])
                total = sum(row["requested_mw"] for row in requests)
                if total > 0:
                    # Proportionality survives the clamp to within a few ulp of the cap.
                    scale_bound = 8 * math.ulp(max(cap, total))
                    tech_factor = {tech: result["technology_scale"].get(tech, 1.0) for tech in technologies}
                    for row in requests:
                        ideal = row["requested_mw"] * tech_factor[row["technology"]] * result["pool_scale"]["pool"]
                        self.assertLessEqual(abs(accepted[row["request_id"]] - ideal), scale_bound + 1e-9 * ideal)
                if math.fsum(values) != sum(values) or sum(values) == cap:
                    clamped += 1
        self.assertGreater(clamped, 0)


class ScopeTest(unittest.TestCase):
    def test_no_discounting_rule_is_introduced(self):
        """A6: P4-02 is out of scope; decisions stay undiscounted in base-year money."""
        self.assertEqual(ia.MONEY_BASIS, "constant_base_year_gbp_undiscounted")
        for name in ("npv_flat_annuity", "irr_flat_annuity", "classify_npv_annuity", "effective_hurdle_rate",
                     "effective_storage_life"):
            self.assertFalse(hasattr(ia, name), name)


if __name__ == "__main__":
    unittest.main()
