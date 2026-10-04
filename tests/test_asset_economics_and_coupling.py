import math
import unittest

from gridform_core.asset_economics import (
    build_asset_economic_extensions,
    resize_asset_economics,
    validate_asset_economics,
)
from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import (
    SchemeCAgentInvestmentDefinition,
    SchemeCPlanningPipelineDefinition,
)
from gridform_core.v2.contracts import (
    AssetStateV2,
    ExpansionHeadroom,
    MarketYearResult,
    ModuleSelection,
    OperatingState,
    PSMInput,
    PlanningProject,
    ResolvedRun,
    YearState,
)


def run_contract():
    modules = {
        slot: ModuleSelection(slot, module, "test", f"value.{slot}/v2")
        for slot, module in {
            "psm": "value-bid-at-cost-psm",
            "pipeline": "planning-pipeline",
            "investment": "agent-investment",
        }.items()
    }
    return ResolvedRun(
        "run", "project", "scenario", "pack", 2025, 2026,
        modules, {"clock.period_hours": 0.5}, {},
    )


def solar_economics(capacity):
    return build_asset_economic_extensions(
        "solar", capacity, energy_capacity_mwh=None,
        capital_costs_per_mw={"solar": 600_000},
        lifetimes={"solar": 25, "default": 25},
        discount_rate=0.05,
        source_record_id="fixture",
    )


class ExpensiverenewableGenerator:
    def __init__(self, name, capacity):
        self.name = name
        self.capacity_multiplier = capacity


class GasGenerator:
    def __init__(self, name, capacity):
        self.name = name
        self.capacity_limit = capacity


class Battery:
    def __init__(self, name):
        self.name = name
        self.power = None
        self.energy = None

    def resize_power_capacity(self, power, energy):
        self.power = float(power)
        self.energy = float(energy)


class CommissionedAssetEconomicsTests(unittest.TestCase):
    def test_commissioning_fails_closed_when_economics_are_missing(self):
        project = PlanningProject(
            "missing", "Missing", "repd", "solar", 10, 10, "GB",
            "planning", "active", 2024, 2025, "expected_capacity", 1.0,
        )
        with self.assertRaisesRegex(ValueError, "cannot commission without economics"):
            SchemeCPlanningPipelineDefinition().advance_year(
                run_contract(), YearState(2025, (), (project,))
            )

    def test_commissioned_asset_has_versioned_record_and_reconciled_cost(self):
        extensions = solar_economics(10)
        project = PlanningProject(
            "repd:1", "Solar", "repd", "solar", 10, 10, "Scotland",
            "planning", "active", 2024, 2025, "expected_capacity", 1.0,
            extensions=extensions,
        )
        result = SchemeCPlanningPipelineDefinition().advance_year(
            run_contract(), YearState(2025, (), (project,))
        )
        asset = result.operating_state.assets[0]
        validate_asset_economics(asset)
        record = asset.extensions["commissioned_asset_record"]
        self.assertEqual(record["schema_version"], "value.commissioned-asset/v1")
        self.assertEqual(record["source_project_id"], "repd:1")
        self.assertGreater(record["annualized_capital_cost_gbp"], 0)

    def test_model_commissioned_asset_inherits_investment_owner(self):
        extensions = solar_economics(10)
        extensions.update({"investment_owner_id": "owner:solar", "source_agent_id": "owner:solar"})
        project = PlanningProject(
            "model:1", "Solar", "model_investment", "solar", 10, 10, "GB",
            "planning", "active", 2024, 2025, "expected_capacity", 1.0,
            extensions=extensions,
        )
        result = SchemeCPlanningPipelineDefinition().advance_year(
            run_contract(), YearState(2025, (), (project,))
        )
        asset = result.operating_state.assets[0]
        self.assertEqual(asset.extensions["investment_owner_id"], "owner:solar")
        self.assertTrue(asset.extensions["investment_eligible"])
        self.assertEqual(
            asset.extensions["commissioned_asset_record"]["investment_owner_id"],
            "owner:solar",
        )

    def test_external_commissioned_asset_does_not_create_an_investor(self):
        project = PlanningProject(
            "repd:external", "Solar", "repd", "solar", 10, 10, "GB",
            "planning", "active", 2024, 2025, "expected_capacity", 1.0,
            extensions=solar_economics(10),
        )
        advance = SchemeCPlanningPipelineDefinition().advance_year(
            run_contract(), YearState(2025, (), (project,))
        )
        asset = advance.operating_state.assets[0]
        self.assertIsNone(asset.extensions["investment_owner_id"])
        self.assertFalse(asset.extensions["investment_eligible"])
        market = MarketYearResult(
            "m", 2025, "psm", "1", {}, {asset.asset_id: 100_000_000},
            1, 1, 1, 1, 1, 0, 0,
        )
        decision = SchemeCAgentInvestmentDefinition().decide(
            run_contract(), advance.operating_state, market,
            (ExpansionHeadroom("h", 2025, "vre-expansion-cap", {"solar": 100}),),
        )
        self.assertEqual(decision.proposals, ())

    def test_pumped_hydro_project_without_site_data_is_deferred(self):
        extensions = build_asset_economic_extensions(
            "pumped_hydro", 10, energy_capacity_mwh=40,
            capital_costs_per_mw={}, lifetimes={}, discount_rate=0.05,
            source_record_id="pumped",
        )
        extensions["energy_capacity_mwh"] = 40.0
        project = PlanningProject(
            "pumped:1", "Pumped", "repd", "pumped_hydro", 10, 10, "Scotland",
            "planning", "active", 2024, 2025, "expected_capacity", 1.0,
            extensions=extensions,
        )
        result = SchemeCPlanningPipelineDefinition().advance_year(
            run_contract(), YearState(2025, (), (project,))
        )
        self.assertEqual(result.commissioned_projects, ())
        self.assertEqual(len(result.deferred_projects), 1)
        self.assertEqual(len(result.operating_state.active_planning_projects), 1)
        self.assertEqual(
            result.events[0].reason_code.value,
            "missing_site_or_hydrology_data",
        )

    def test_site_data_without_new_build_cost_scope_still_cannot_commission_hydro(self):
        extensions = build_asset_economic_extensions(
            "Hydro_natural_flow", 10, energy_capacity_mwh=None,
            capital_costs_per_mw={"Hydro_natural_flow": 100_000_000},
            lifetimes={"Hydro_natural_flow": 50}, discount_rate=0.05,
            source_record_id="existing-stock-proxy",
        )
        extensions.update({
            "hydrology_profile_id": "hydrology:site-a",
            "capital_cost_scope": "existing_stock_compatibility",
            "new_build_cost_source_id": "not-valid-for-new-build",
        })
        project = PlanningProject(
            "hydro:1", "Hydro", "external", "Hydro_natural_flow", 10, 10, "Wales",
            "planning", "active", 2024, 2025, "expected_capacity", 1.0,
            extensions=extensions,
        )
        result = SchemeCPlanningPipelineDefinition().advance_year(
            run_contract(), YearState(2025, (), (project,))
        )
        self.assertEqual(result.commissioned_projects, ())
        self.assertIn(
            "capital_cost_scope=new_build",
            result.events[0].extensions["missing_fields"],
        )

    def test_retirement_scales_capacity_energy_capex_and_fom_together(self):
        extensions = build_asset_economic_extensions(
            "0.25c_battery", 10, energy_capacity_mwh=40,
            capital_costs_per_mw={}, lifetimes={}, discount_rate=0.05,
            source_record_id="storage",
        )
        asset = AssetStateV2(
            "storage", "0.25c_battery", 10, 40, extensions=extensions
        )
        resized = resize_asset_economics(asset, 4)
        self.assertEqual(resized.capacity_mw, 4)
        self.assertEqual(resized.energy_capacity_mwh, 16)
        self.assertAlmostEqual(
            resized.extensions["total_capex_gbp"],
            asset.extensions["total_capex_gbp"] * 0.4,
        )
        self.assertAlmostEqual(
            resized.extensions["annual_fixed_opex_gbp"],
            asset.extensions["annual_fixed_opex_gbp"] * 0.4,
        )
        validate_asset_economics(resized)

    def test_new_asset_changes_next_year_live_force_capacity(self):
        initial = AssetStateV2(
            "solar_A", "solar", 100, region="A", extensions=solar_economics(100)
        )
        addition = AssetStateV2(
            "commissioned:repd:1", "solar", 25, region="A",
            status="commissioned", extensions=solar_economics(25),
        )
        generators = {
            "solar_A": ExpensiverenewableGenerator("solar_A", 100),
            "CCGT": GasGenerator("CCGT", 100),
        }
        batteries = {"0.25c_battery": Battery("air_battery")}
        first = PSMInput(
            "run", 2025, "pack", OperatingState(2025, (initial,), ()), 0.5, {}
        )
        audit_2025 = SchemeCNativePSM._apply_state(generators, batteries, first)
        self.assertEqual(generators["solar_A"].capacity_multiplier, 100)
        second = PSMInput(
            "run", 2026, "pack", OperatingState(2026, (initial, addition), ()), 0.5, {}
        )
        audit_2026 = SchemeCNativePSM._apply_state(generators, batteries, second)
        self.assertEqual(generators["solar_A"].capacity_multiplier, 125)
        self.assertEqual(audit_2025["mapped_asset_count"], 1)
        self.assertEqual(audit_2026["mapped_asset_count"], 2)
        lineage = audit_2026["generator_objects"]["solar_A"]["source_asset_capacity_mw"]
        self.assertEqual(lineage["commissioned:repd:1"], 25)

    def test_invest_profit_branch_is_executable(self):
        extensions = solar_economics(10)
        extensions.update({"preferred_rate": 0.20, "target_payback_years": 10})
        asset = AssetStateV2("solar", "solar", 10, extensions=extensions)
        replacement = 10 * extensions["capital_cost_per_mw"]
        income = replacement / 8
        market = MarketYearResult(
            "m", 2025, "psm", "1", {}, {"solar": income},
            1, 1, 1, 1, 1, 0, 0,
        )
        decision = SchemeCAgentInvestmentDefinition().decide(
            run_contract(), OperatingState(2025, (asset,), ()), market,
            (ExpansionHeadroom("h", 2025, "vre-expansion-cap", {"solar": 100}),),
        )
        self.assertEqual(len(decision.proposals), 1)
        proposal = decision.proposals[0]
        self.assertEqual(proposal.extensions["investment_recommendation"], "Invest_Profit")
        self.assertTrue(math.isclose(proposal.evidence["payback_years"], 8.0))

    def test_one_owner_with_multiple_physical_assets_makes_one_decision(self):
        first = solar_economics(10)
        second = solar_economics(5)
        first.update({"investment_owner_id": "solar-owner"})
        second.update({"investment_owner_id": "solar-owner"})
        assets = (
            AssetStateV2("solar-original", "solar", 10, region="GB", extensions=first),
            AssetStateV2("commissioned:model:1", "solar", 5, region="GB", extensions=second),
        )
        market = MarketYearResult(
            "m", 2025, "psm", "1", {},
            {"solar-original": 6_000_000, "commissioned:model:1": 3_000_000},
            1, 1, 1, 1, 1, 0, 0,
        )
        decision = SchemeCAgentInvestmentDefinition().decide(
            run_contract(), OperatingState(2025, assets, ()), market,
            (ExpansionHeadroom("h", 2025, "vre-expansion-cap", {"solar": 100}),),
        )
        self.assertEqual(len(decision.proposals), 1)
        self.assertEqual(decision.proposals[0].agent_id, "solar-owner")
        self.assertEqual(decision.extensions["grouped_investment_owners"], 1)

    def test_headroom_is_one_shared_technology_year_budget(self):
        assets = []
        income = {}
        for owner in ("owner-a", "owner-b"):
            extensions = solar_economics(10)
            extensions.update({"investment_owner_id": owner})
            asset_id = owner + ":asset"
            assets.append(AssetStateV2(asset_id, "solar", 10, region="GB", extensions=extensions))
            income[asset_id] = 6_000_000
        market = MarketYearResult("m", 2025, "psm", "1", {}, income, 1, 1, 1, 1, 1, 0, 0)
        decision = SchemeCAgentInvestmentDefinition().decide(
            run_contract(), OperatingState(2025, tuple(assets), ()), market,
            (ExpansionHeadroom("h", 2025, "vre-expansion-cap", {"solar": 12}),),
        )
        self.assertAlmostEqual(sum(row.capacity_mw for row in decision.proposals), 12.0)
        self.assertEqual(decision.extensions["remaining_headroom_mw_by_technology"]["solar"], 0.0)

    def test_site_constrained_hydro_cannot_invest_without_site_module(self):
        hydro_extensions = build_asset_economic_extensions(
            "Hydro_natural_flow", 10, energy_capacity_mwh=None,
            capital_costs_per_mw={"Hydro_natural_flow": 1_000_000},
            lifetimes={"Hydro_natural_flow": 50}, discount_rate=0.05,
            source_record_id="hydro",
        )
        hydro_extensions.update({"investment_owner_id": "hydro-owner"})
        asset = AssetStateV2("hydro", "Hydro_natural_flow", 10, extensions=hydro_extensions)
        market = MarketYearResult(
            "m", 2025, "psm", "1", {}, {"hydro": 100_000_000},
            1, 1, 1, 1, 1, 0, 0,
        )
        decision = SchemeCAgentInvestmentDefinition().decide(
            run_contract(), OperatingState(2025, (asset,), ()), market, (),
        )
        self.assertEqual(decision.proposals, ())
        self.assertEqual(decision.extensions["ineligible_groups"][0]["reason"], "site_data_required")


if __name__ == "__main__":
    unittest.main()
