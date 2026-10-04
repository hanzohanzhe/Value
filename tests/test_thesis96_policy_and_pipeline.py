"""Final9.6 policy allocations and public planning regression examples."""
from dataclasses import replace
import math
import unittest

from gridform_core import doctoral_ledgers
from gridform_core.asset_economics import build_asset_economic_extensions, validate_asset_economics
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCPlanningPipelineDefinition
from gridform_core.v2.contracts import AssetStateV2, InvestmentProposal, OperatingState, ResolvedRun, YearState


def fleet():
    # Equal MW, deliberately very different energy capacities: CM uses MW.
    return OperatingState(2025, tuple(AssetStateV2(name, tech, power, energy,
        extensions={"investment_owner_id": name}) for name, tech, power, energy in (
            ("gas", "CCGT", 100, None), ("nuc", "Nuclear", 100, None),
            ("b1", "1c_battery", 100, 100), ("b4", "0.25c_battery", 100, 400),
            ("pump", "pumped_hydro", 100, 1000),
            ("pv", "solar", 100, None), ("wind", "onshore", 300, None))), ())


class Thesis96PolicyTests(unittest.TestCase):
    def allocate(self, scenario="subsidy_as_usual", state=None, **overrides):
        fn = getattr(doctoral_ledgers, "allocate_thesis96_policy", None)
        self.assertTrue(callable(fn), "final9.6 policy eligibility is not implemented")
        args = dict(scenario=scenario, ancillary_budget_gbp=800,
            existing_decarb_budget_gbp=9000, additional_decarb_budget_gbp=400,
            target_capacity_mw_by_technology={"solar": 100, "onshore": 400})
        args.update(overrides)
        return fn(state or fleet(), **args)

    def test_cm_uses_544bn_and_typed_discharge_power_derating(self):
        result = self.allocate()
        self.assertEqual(result["cm_capacity_weights_mw"],
                         {"gas": 95, "nuc": 85, "b1": 5, "b4": 60, "pump": 95})
        self.assertAlmostEqual(sum(result["cm_income_gbp_by_asset"].values()), 5_440_000_000)
        self.assertAlmostEqual(result["cm_income_gbp_by_asset"]["b4"], 960_000_000)
        self.assertEqual(result["ancillary_income_gbp_by_asset"],
                         {"gas": 160, "nuc": 160, "b1": 160, "b4": 160, "pump": 160})

    def test_existing_support_is_system_cost_not_investable_income(self):
        base = self.allocate("decarbonisation_base")
        usual = self.allocate()
        self.assertEqual(base["decarb_income_gbp_by_asset"], {})
        self.assertEqual(usual["decarb_income_gbp_by_asset"], {"pv": 100, "wind": 300})
        self.assertEqual(base["system_policy_costs_gbp"]["existing_decarb"], 9000)
        self.assertEqual(base["system_policy_costs_gbp"]["additional_decarb"], 0)

    def test_target_equality_stops_technology_and_reallocates_to_eligible(self):
        result = self.allocate("governmental_target")
        self.assertEqual(result["decarb_income_gbp_by_asset"], {"wind": 400})
        result = self.allocate("governmental_target", target_capacity_mw_by_technology={"solar": 50, "onshore": 200})
        self.assertEqual(result["decarb_income_gbp_by_asset"], {})
        self.assertEqual(result["unallocated_decarb_gbp"], 400)

    def test_disabled_policy_is_not_paid_and_unknown_storage_is_not_assumed(self):
        result = self.allocate("basic")
        for field in ("cm_income_gbp_by_asset", "decarb_income_gbp_by_asset", "ancillary_income_gbp_by_asset"):
            self.assertEqual(result[field], {})
        hydrogen = replace(fleet(), assets=fleet().assets + (AssetStateV2("h2", "hydrogen_battery", 10, 100),))
        with self.assertRaisesRegex(ValueError, "derating"):
            self.allocate(state=hydrogen)
        result = self.allocate(state=hydrogen, cm_derating_overrides={"hydrogen_battery": 0.0})
        self.assertNotIn("h2", result["cm_income_gbp_by_asset"])

    def test_missing_target_and_nonfinite_budget_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "target"):
            self.allocate("governmental_target", target_capacity_mw_by_technology={"solar": 100})
        with self.assertRaises(ValueError):
            self.allocate(ancillary_budget_gbp=math.nan)


class PlanningProbabilityRegressionTests(unittest.TestCase):
    def test_public_investment_does_not_replace_zero_planning_probability(self):
        from test_doctoral_investment_alignment import typed_inputs
        from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCAgentInvestmentDefinition
        run, state, market, caps, _ = typed_inputs()
        state = replace(state, assets=tuple(replace(a, extensions={**a.extensions,
            "success_probability": 0.0}) for a in state.assets))
        market = replace(market, market_income_gbp_by_agent={"z1": 40, "z2": 40, "a": 80})
        decision = SchemeCAgentInvestmentDefinition().decide(run, state, market, caps)
        self.assertTrue(decision.proposals)
        self.assertEqual({p.extensions["success_probability"] for p in decision.proposals}, {0.0})
        admitted = SchemeCPlanningPipelineDefinition().admit_projects(run, state, decision.proposals)
        self.assertEqual(admitted.admitted_projects, ())

    def fixture(self, probability=0.5, mode="expected_capacity"):
        run = ResolvedRun("regression", "p", "basic", "fixture", 2025, 2030, {},
            {"planning.success_mode": mode}, {})
        economics = build_asset_economic_extensions("0.25c_battery", 100,
            energy_capacity_mwh=400, capital_costs_per_mw={"0.25c_battery": 1000},
            lifetimes={"0.25c_battery": 20}, discount_rate=0.05,
            source_record_id="proposal", annual_fixed_opex_gbp_override=100)
        proposal = InvestmentProposal("proposal", 2025, "owner", "0.25c_battery", 100,
            "GB", 2027, extensions={**economics, "energy_capacity_mwh": 400,
                "success_probability": probability, "investment_owner_id": "owner"})
        return run, OperatingState(2025, (), ()), proposal

    def test_zero_probability_never_becomes_full_success(self):
        for mode in ("expected_capacity", "seeded_stochastic"):
            with self.subTest(mode=mode):
                run, state, proposal = self.fixture(0.0, mode)
                result = SchemeCPlanningPipelineDefinition().admit_projects(run, state, (proposal,))
                self.assertEqual(sum(p.capacity_mw for p in result.admitted_projects), 0)

    def test_expected_energy_and_economics_scale_once_through_commissioning(self):
        run, state, proposal = self.fixture()
        pipeline = SchemeCPlanningPipelineDefinition()
        result = pipeline.admit_projects(run, state, (proposal,))
        project = result.admitted_projects[0]
        self.assertEqual((project.capacity_mw, project.extensions["energy_capacity_mwh"]), (50, 200))
        for field in ("total_capex_gbp", "annual_fixed_opex_gbp", "annualized_capital_cost_gbp"):
            self.assertAlmostEqual(project.extensions[field], proposal.extensions[field] * 0.5)
        advanced = pipeline.advance_year(run, YearState(2027, (), result.next_pipeline))
        asset = advanced.operating_state.assets[0]
        self.assertEqual((asset.capacity_mw, asset.energy_capacity_mwh), (50, 200))
        self.assertEqual(asset.extensions["investment_owner_id"], "owner")
        validate_asset_economics(asset)
        self.assertEqual(proposal.extensions["energy_capacity_mwh"], 400)

    def test_invalid_probability_or_mode_is_not_silently_normalized(self):
        for probability, mode in ((math.nan, "expected_capacity"), (-0.1, "expected_capacity"),
                                  (1.1, "expected_capacity"), (0.5, "misspelled")):
            run, state, proposal = self.fixture(probability, mode)
            with self.subTest(probability=probability, mode=mode), self.assertRaises(ValueError):
                SchemeCPlanningPipelineDefinition().admit_projects(run, state, (proposal,))


if __name__ == "__main__":
    unittest.main()
