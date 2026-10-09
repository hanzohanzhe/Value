"""Source-grounded small cashflow and dual-view ledger regressions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

from tests.doctoral_reference_harness import load_reference_symbols, validate_source_manifest


ANNUAL_SOURCE = "run_investment_analysis_case3_decarbonization_breakdown_cm.py"


def _original_statements(relative_path, first_line, last_line, inputs):
    """Compile only exact, hash-verified statement ranges; never import a main."""
    manifest = validate_source_manifest()
    path = Path(manifest["source_root"]) / relative_path
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["sources"][relative_path]["sha256"]:
        raise ValueError("source identity changed before statement extraction")
    tree = ast.parse(raw.decode("utf-8-sig"))
    candidates = sorted(
        [node for node in ast.walk(tree) if isinstance(node, ast.stmt)
         and node.lineno >= first_line and node.end_lineno <= last_line],
        key=lambda node: (node.lineno, -node.end_lineno))
    selected = []
    for node in candidates:
        if not any(parent.lineno <= node.lineno and parent.end_lineno >= node.end_lineno
                   for parent in selected):
            selected.append(node)
    if not selected:
        raise AssertionError("source oracle range matched no statements")
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) for parent in selected for node in ast.walk(parent)):
        raise AssertionError("source oracle range must not import modules")
    namespace = dict(inputs)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec", dont_inherit=True),
         namespace, namespace)
    return namespace


def _state(*ids):
    return {"assets": [{"asset_id": asset_id, "extensions": {"investment_owner_id": "owner"}}
                       for asset_id in ids]}


def _market():
    return {
        "ahead_income_gbp_by_asset": {"a": 8_000_000, "b": 1_000_000},
        "balancing_income_gbp_by_asset": {"a": 1_000_000, "b": 0},
        "operating_cost_gbp_by_asset": {"a": 10_000_000, "b": 2_000_000},
        "total_market_income_gbp_by_asset": {"a": 9_000_000, "b": 1_000_000},
    }


class DoctoralLedgerTests(unittest.TestCase):
    @staticmethod
    def ledger():
        name = "gridform_core.doctoral_ledgers"
        if importlib.util.find_spec(name) is None:
            raise AssertionError("explicit doctoral ledgers are not implemented")
        return importlib.import_module(name)

    def test_generator_operating_cost_matches_exact_annual_statement(self):
        ledger = self.ledger()
        reference = load_reference_symbols(["Battery"])
        gas = SimpleNamespace(name="gas", gen_cost=60)
        idle = SimpleNamespace(name="idle", gen_cost=80)
        battery = reference["Battery"]("store", 100, 20, 0, 0, 1, 1, 0)
        source = _original_statements(ANNUAL_SOURCE, 425, 435, {
            "Battery": reference["Battery"], "PHYSICAL_PERIOD_HOURS": 0.5,
            "generators_list": [gas, idle],
            "gen_list_composition": [[[gas, 10], [battery, 4]], [[gas, 30]]],
        })
        actual = ledger.operating_costs_from_generation(
            {"gas": 40, "idle": 0}, {"gas": 60, "idle": 80}, generation_unit="mw_period_sum")
        self.assertEqual(actual["operating_cost_gbp_by_asset"], source["total_operational_costs"])
        self.assertEqual(actual["raw_generation_fee_by_asset"], {"gas": 2400, "idle": 0})
        self.assertEqual(actual["generation_mwh_by_asset"], {"gas": 20, "idle": 0})

    def test_mwh_input_is_not_multiplied_by_half_hour_again(self):
        actual = self.ledger().operating_costs_from_generation(
            {"gas": 20}, {"gas": 60}, generation_unit="mwh")
        self.assertEqual(actual["operating_cost_gbp_by_asset"], {"gas": 1200})
        with self.assertRaisesRegex(ValueError, "generation_unit"):
            self.ledger().operating_costs_from_generation({"gas": 20}, {"gas": 60}, generation_unit="unknown")

    def test_actual_cost_reaches_owner_loss_without_readding_total_income(self):
        ledger = self.ledger()
        accounts = ledger.build_agent_accounts(_market(), _state("a", "b"), {"scenario": "basic"})
        owner = accounts["owner"]
        self.assertEqual(owner["market_income_gbp"], 9_000_000)
        self.assertEqual(owner["balancing_income_gbp"], 1_000_000)
        self.assertEqual(owner["operating_cost_gbp"], 12_000_000)
        self.assertEqual(owner["net_profit_gbp"], -2_000_000)
        self.assertEqual(owner["net_revenue_gbp"], -2_000_000)
        self.assertEqual(owner["cm_income_gbp"], 0)
        self.assertEqual(owner["decarb_income_gbp"], 0)

    def test_missing_actual_cost_or_owner_is_not_silently_zero(self):
        ledger = self.ledger()
        market = _market()
        del market["operating_cost_gbp_by_asset"]["a"]
        with self.assertRaisesRegex(ValueError, "operating_cost.*coverage"):
            ledger.build_agent_accounts(market, _state("a", "b"), {"scenario": "basic"})
        with self.assertRaisesRegex(ValueError, "owner"):
            ledger.build_agent_accounts(_market(), {"assets": [{"asset_id": "a"}, {"asset_id": "b"}]},
                                        {"scenario": "basic"})

    def test_market_total_mismatch_and_unknown_asset_are_rejected(self):
        ledger = self.ledger()
        market = _market()
        market["total_market_income_gbp_by_asset"]["a"] += 1
        with self.assertRaisesRegex(ValueError, "income reconciliation"):
            ledger.build_asset_accounts(market, _state("a", "b"), {"scenario": "basic"})
        market = _market()
        market["ahead_income_gbp_by_asset"]["unknown"] = 1
        with self.assertRaisesRegex(ValueError, "coverage"):
            ledger.build_asset_accounts(market, _state("a", "b"), {"scenario": "basic"})

    def test_net_revenue_matches_source_and_policy_transfers_are_not_capex(self):
        import pandas as pd
        ledger = self.ledger()
        policy = {"scenario": "decarb", "cm_income_gbp_by_asset": {"a": 400},
                  "decarb_income_gbp_by_asset": {"b": 600}}
        actual = ledger.build_asset_accounts(_market(), _state("a", "b"), policy)
        frame = pd.DataFrame({"electricity_income": [9_000_000, 1_000_000], "hydrogen_income": [0, 0],
                              "agent_decarbonization_income": [0, 600], "cm_income": [400, 0],
                              "operational_cost": [10_000_000, 2_000_000]}, index=["a", "b"])
        source = _original_statements(ANNUAL_SOURCE, 867, 874, {"df_analysis": frame})
        self.assertEqual({asset: row["net_revenue_gbp"] for asset, row in actual.items()},
                         source["df_analysis"]["net_revenue"].to_dict())
        with self.assertRaisesRegex(ValueError, "basic"):
            ledger.build_agent_accounts(_market(), _state("a", "b"), {**policy, "scenario": "basic"})

    def test_policy_weights_allocate_the_pot_once_and_basic_disables_both(self):
        import pandas as pd
        ledger = self.ledger()
        amounts = dict(cm_pot_gbp=100, decarb_pot_gbp=40,
                       cm_capacity_weights_mw={"a": 30, "b": 10},
                       eligible_decarb_capacity_mw={"a": 1, "b": 3})
        actual = ledger.allocate_policy_transfers(scenario="decarb", **amounts)
        self.assertEqual(actual["cm_income_gbp_by_asset"], {"a": 75, "b": 25})
        self.assertEqual(actual["decarb_income_gbp_by_asset"], {"a": 10, "b": 30})
        source = _original_statements(ANNUAL_SOURCE, 792, 802, {
            "eligible_vre_capacity": 4, "agent_investable_decarb": 40,
            "subsidy_eligible_vre_capacities": {"a": 1, "b": 3},
            "df_analysis": pd.DataFrame(index=["a", "b"]),
        })
        self.assertEqual(actual["decarb_income_gbp_by_asset"],
                         source["df_analysis"]["agent_decarbonization_income"].to_dict())
        basic = ledger.allocate_policy_transfers(scenario="basic", **amounts)
        self.assertEqual(basic["cm_income_gbp_by_asset"], {})
        self.assertEqual(basic["decarb_income_gbp_by_asset"], {})
        cm = ledger.allocate_policy_transfers(scenario="with_cm", **amounts)
        self.assertEqual(cm["cm_income_gbp_by_asset"], {"a": 75, "b": 25})
        self.assertEqual(cm["decarb_income_gbp_by_asset"], {})

    def test_unallocated_policy_pot_remains_visible(self):
        actual = self.ledger().allocate_policy_transfers(
            scenario="decarb", cm_pot_gbp=100, decarb_pot_gbp=40,
            cm_capacity_weights_mw={}, eligible_decarb_capacity_mw={})
        self.assertEqual(actual["unallocated_cm_gbp"], 100)
        self.assertEqual(actual["unallocated_decarb_gbp"], 40)
        self.assertEqual(actual["eligibility_status"], "caller_supplied_not_independently_evaluated")

    def test_typed_market_costs_flow_through_ledger_into_actual_investment(self):
        from dataclasses import replace
        from gridform_core.builtin.scheme_c_1000twh.doctoral_policy import decide_doctoral_investment
        from tests.test_doctoral_investment_alignment import typed_inputs
        run, state, market, headroom, _ = typed_inputs()
        inputs = {
            "ahead_income_gbp_by_asset": {"z1": 40, "z2": 40, "a": 80},
            "balancing_income_gbp_by_asset": {"z1": 0, "z2": 0, "a": 0},
            "operating_cost_gbp_by_asset": {"z1": 41, "z2": 41, "a": 0},
        }
        market = replace(market, extensions={"doctoral_cashflow_inputs": inputs})
        accounts = self.ledger().build_asset_accounts(market, state, {"scenario": "basic"})
        decision = decide_doctoral_investment(run, state, market, headroom, accounts)
        self.assertEqual(decision.retirements_mw, {"z1": 25, "z2": 25})
        self.assertEqual([(p.agent_id, p.capacity_mw) for p in decision.proposals], [("A", 80)])

    def test_raw_cost_and_resource_cost_have_distinct_denominators(self):
        ledger = self.ledger()
        actual = ledger.build_system_cost_views(
            legacy_capital_cost_gbp=100, legacy_operating_cost_gbp=200,
            deficit_mwh=1, existing_decarb_levy_gbp=20, additional_decarb_levy_gbp=30,
            cm_levy_gbp=40, generated_mwh=100,
            resource_capital_cost_gbp=100, resource_operating_cost_gbp=180,
            resource_reliability_cost_gbp=17000, served_mwh=80)
        # A16-5 (fx5.voll-17000): 1 MWh of deficit at 17000 GBP/MWh (thesis code: 8000).
        self.assertEqual(actual["legacy_deficit_cost_gbp"], 17000)
        self.assertEqual(actual["legacy_system_cost_gbp"], 17390)
        self.assertAlmostEqual(actual["legacy_cost_per_mwh_generated"], 173.9)
        self.assertEqual(actual["resource_system_cost_gbp"], 17280)
        self.assertEqual(actual["resource_cost_per_mwh_served"], 216)

    def test_legacy_carbon_is_source_scalar_not_a_physical_tonne_claim(self):
        ledger = self.ledger()
        gas = SimpleNamespace(carbon_emission=3, carbon_intensity=394)
        storage = SimpleNamespace(carbon_emission=50)
        source = _original_statements("simulation_model.py", 2348, 2356, {
            "gen_list": [[gas, 10], [storage, 2]],
            "electrolyzer": SimpleNamespace(body_emission=0), "carbon_emission": [],
        })
        actual = ledger.legacy_carbon_metric([
            {"generation_source_quantity": 10, "carbon_emission": 3, "carbon_intensity": 394},
            {"generation_source_quantity": 2, "carbon_emission": 50},
        ], electrolyzer_body_emission=0)
        self.assertEqual(actual["legacy_carbon_metric"], source["carbon_emission"][0])
        self.assertEqual(actual["unit_status"], "unknown_source_scalar")
        physical = ledger.physical_carbon_view({"gas": 5}, {"gas": 394})
        self.assertEqual(physical["operational_tco2e"], 1.97)
        self.assertEqual(physical["storage_carbon_status"], "not_evaluated")
        self.assertIsNone(physical["closing_storage_carbon_tco2e"])


if __name__ == "__main__":
    unittest.main()
