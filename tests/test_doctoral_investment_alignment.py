"""Bounded investment comparisons against isolated, hash-checked original ASTs."""
from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Mapping
import unittest

import numpy as np
import pandas as pd


FIXTURE = json.loads((Path(__file__).parent / "fixtures/doctoral_alignment/investment.json").read_text(encoding="utf-8"))
POLICY_MODULE = "gridform_core.builtin.scheme_c_1000twh.doctoral_policy"
STORAGE = ("1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery")


def source_tree(relative_path):
    path = Path(FIXTURE["source_root"]) / relative_path
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE["source_hashes"][relative_path]:
        raise ValueError(f"doctoral source identity changed: {relative_path}")
    return ast.parse(raw.decode("utf-8-sig"), filename=str(path))


def account(name, tech="solar", capacity=100.0, net=80.0, capex=1.0, preferred=0.08, target=25.0):
    return dict(account_id=name, technology=tech, current_capacity_mw=capacity,
                net_revenue_gbp=net, capital_cost_per_mw_gbp=capex,
                replacement_capital_gbp=capacity * capex, preferred_rate=preferred,
                target_payback_years=target)


def source_decisions(accounts, caps):
    """Execute only original nested policy functions and the direct scaling loop.

    The original annual entry point, I/O, dispatch and main loop never execute.
    Configuration is fixture input, and no candidate function enters this oracle.
    """
    tree = source_tree("run_investment_analysis_case3_decarbonization_breakdown_cm.py")
    annual = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "analyze_investment_case3")
    names = {"assign_recommendation", "_profit_based_addition_mw", "calculate_new_capacity"}
    functions = [node for node in annual.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in functions} != names:
        raise ValueError("original investment dependency closure incomplete")
    loops = [node for node in annual.body if isinstance(node, ast.For)
             and isinstance(node.target, ast.Name) and node.target.id == "tech_type"
             and isinstance(node.iter, ast.Name) and node.iter.id == "vre_battery_techs"]
    if len(loops) != 1:
        raise ValueError("original investment scaling loop is not unique")
    frame = pd.DataFrame({row["account_id"]: dict(
        asset_type=row["technology"], current_capacity=row["current_capacity_mw"],
        net_revenue=row["net_revenue_gbp"], capital_cost=row["replacement_capital_gbp"],
        ROI=row["net_revenue_gbp"] / row["replacement_capital_gbp"] if row["replacement_capital_gbp"] else np.nan,
        payback_years=row["replacement_capital_gbp"] / row["net_revenue_gbp"] if row["net_revenue_gbp"] > 0 else math.inf,
        preferred_rate=row["preferred_rate"], target_payback=row["target_payback_years"],
    ) for row in accounts}).T
    namespace = {"pd": pd, "np": np,
        "config": SimpleNamespace(capital_costs_per_mw={row["technology"]: row["capital_cost_per_mw_gbp"] for row in accounts}),
        "regulated_targets": {"CCGT": 1.01, "OCGT": 1.01, "bio_and_waste": 1.01, **caps},
        "_sec": SimpleNamespace(EXPANDABLE_STORAGE_KEYS=STORAGE),
        "df_analysis": frame, "vre_battery_techs": ("solar", "onshore", "offshore", *STORAGE),
        "battery_techs": set(STORAGE)}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<original-investment-functions>", "exec"), namespace)
    frame["recommendation"] = frame.apply(namespace["assign_recommendation"], axis=1)
    frame["suggested_new_capacity"] = frame.apply(namespace["calculate_new_capacity"], axis=1)
    exec(compile(ast.Module(body=loops, type_ignores=[]), "<original-investment-scaling>", "exec"), namespace)
    return {str(key): {"recommendation": row["recommendation"], "delta_mw": float(row["suggested_new_capacity"] - row["current_capacity"])} for key, row in frame.iterrows()}


def source_storage():
    """Isolate the original storage definitions and constants; omit imports/I/O."""
    raw = Path(FIXTURE["storage_source_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE["storage_source_sha256"]:
        raise ValueError("doctoral storage source identity changed")
    tree = ast.parse(raw.decode("utf-8-sig"))
    definitions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.Assign, ast.AnnAssign))]
    namespace = {"np": np, "os": os, "Path": Path, "Mapping": Mapping,
                 "config": SimpleNamespace(batteries={key: {} for key in STORAGE})}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "<original-storage-definitions>", "exec"), namespace)
    return namespace


def typed_inputs():
    from gridform_core.asset_economics import build_asset_economic_extensions
    from gridform_core.v2.contracts import AssetStateV2, ExpansionHeadroom, MarketYearResult, OperatingState, ResolvedRun
    assets = []
    for asset_id, owner, capacity, region in (("z1", "Z", 50, "Scotland"), ("z2", "Z", 50, "North West"), ("a", "A", 100, "England")):
        ext = build_asset_economic_extensions("solar", capacity, energy_capacity_mwh=None, capital_costs_per_mw={"solar": 1}, lifetimes={"solar": 25}, discount_rate=0.05, source_record_id=asset_id)
        ext.update(investment_owner_id=owner, investment_eligible=True, preferred_rate=0.08, target_payback_years=25)
        assets.append(AssetStateV2(asset_id, "solar", capacity, region=region, extensions=ext))
    run = ResolvedRun("test", "p", "basic", "fixture", 2025, 2025, {}, {}, {})
    state = OperatingState(2025, tuple(assets), ())
    market = MarketYearResult("market", 2025, "fixture", "1", {}, {}, 0, 0, 0, 0, 0, 0, 0)
    headroom = (ExpansionHeadroom("cap", 2025, "vre-expansion-cap", {"solar": 100}),)
    accounts = {"z1": {"net_revenue_gbp": 40}, "z2": {"net_revenue_gbp": 40}, "a": {"net_revenue_gbp": 80}}
    return run, state, market, headroom, accounts


class DoctoralInvestmentAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(POLICY_MODULE), "source-backed doctoral investment policy is missing")
        self.policy = importlib.import_module(POLICY_MODULE)

    def test_vre_threshold_matches_original_bisection_not_peak_headroom(self):
        fixture = FIXTURE["cases"]["vre_cap_200"]
        demand = [demand for count, demand, profile in fixture["blocks"] for _ in range(count)]
        profile = [profile for count, demand, profile in fixture["blocks"] for _ in range(count)]
        tree = source_tree("run_investment_analysis.py")
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "critical_capacity_for_threshold")
        namespace = {"pd": pd, "np": np}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<original-vre-cap>", "exec"), namespace)
        with tempfile.TemporaryDirectory(prefix="doctoral-investment-") as temp:
            demand_path, profile_path = Path(temp) / "demand.csv", Path(temp) / "profile.csv"
            pd.DataFrame({"demand": demand}).to_csv(demand_path, index=False)
            pd.DataFrame(profile).to_csv(profile_path, index=False, header=False)
            expected = namespace["critical_capacity_for_threshold"](demand_path, profile_path)
        actual = self.policy.critical_capacity_for_threshold(demand, profile)
        self.assertEqual(actual, expected)
        self.assertAlmostEqual(self.policy.vre_annual_expansion_cap(demand, profile), fixture["cap_mw"], places=5)

    def test_vre_unreachable_threshold_keeps_source_zero(self):
        self.assertEqual(self.policy.critical_capacity_for_threshold([50] * 199, [1] * 199), 0.0)
        self.assertEqual(self.policy.critical_capacity_for_threshold([50] * 300, [0] * 300), 0.0)

    def test_vre_rejects_misaligned_nonfinite_or_negative_profiles(self):
        for demand, profile in [([1, 2], [1]), ([1], [math.nan]), ([1], [-1]), ([], [])]:
            with self.subTest(demand=demand, profile=profile), self.assertRaises(ValueError):
                self.policy.critical_capacity_for_threshold(demand, profile)

    def test_four_recommendations_preserve_strict_high_and_inclusive_payback(self):
        classify = self.policy.classify_investment
        self.assertEqual(classify(10, 100, 0.09, 5), "Invest_High")
        self.assertEqual(classify(10, 100, 0.10, 10), "Invest_Profit")
        self.assertEqual(classify(10, 100, 0.10, 9), "Do_Nothing")
        self.assertEqual(classify(-10, 100, 0.10, 10), "Deplete")

    def test_biomass_twenty_year_target_is_independent_of_economic_life(self):
        target = self.policy.target_payback_years("bio_and_waste")
        self.assertEqual(target, 20)
        self.assertEqual(self.policy.classify_investment(100 / 22, 100, 0.089, target), "Do_Nothing")

    def test_target_mapping_matches_original_config_including_gas_alias(self):
        tree = source_tree("config.py")
        node = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "investment_parameters" for t in node.targets))
        original = ast.literal_eval(node.value)["target_payback_years"]
        for tech in ("solar", "onshore", "offshore", "bio_and_waste", "gas", "CCGT", "OCGT", *STORAGE):
            self.assertEqual(self.policy.target_payback_years(tech), original.get(tech, original["default"]))

    def test_same_technology_owners_receive_proportional_allocation(self):
        rows = [account("Z"), account("A")]
        actual = self.policy.evaluate_investment_accounts(rows, {"solar": 100})
        self.assertEqual([row["account_id"] for row in actual], ["Z", "A"])
        self.assertEqual([row["accepted_addition_mw"] for row in actual], [50, 50])
        reference = source_decisions(rows, {"solar": 100})
        self.assertEqual([row["accepted_addition_mw"] for row in actual], [reference[row["account_id"]]["delta_mw"] for row in actual])

    def test_renaming_or_reordering_owners_cannot_change_their_allocation(self):
        rows = [account("Z", net=80), account("A", net=40)]
        actual = self.policy.evaluate_investment_accounts(rows, {"solar": 60})
        renamed = self.policy.evaluate_investment_accounts([{**rows[1], "account_id": "Z"}, {**rows[0], "account_id": "A"}], {"solar": 60})
        self.assertEqual([row["accepted_addition_mw"] for row in actual], [40, 20])
        self.assertEqual([row["accepted_addition_mw"] for row in renamed], [20, 40])

    def test_thermal_high_uses_one_percent_not_profit_capacity(self):
        rows = [account(tech, tech=tech, net=10) for tech in ("CCGT", "OCGT", "bio_and_waste")]
        actual = self.policy.evaluate_investment_accounts(rows, {})
        reference = source_decisions(rows, {})
        for row in actual:
            self.assertEqual(row["accepted_addition_mw"], 1)
            self.assertEqual(row["accepted_addition_mw"], reference[row["account_id"]]["delta_mw"])

    def test_storage_high_uses_cap_and_preserves_profit_floor(self):
        for cap, expected in ((20, 20), (5, 10), (0, 10)):
            rows = [account("store", tech="1c_battery", net=10)]
            actual = self.policy.evaluate_investment_accounts(rows, {"1c_battery": cap})[0]
            self.assertEqual(actual["accepted_addition_mw"], expected)
            self.assertEqual(actual["accepted_addition_mw"], source_decisions(rows, {"1c_battery": cap})["store"]["delta_mw"])

    def test_storage_profit_is_excluded_from_high_cap_scaling(self):
        rows = [account("high", tech="1c_battery", net=20), account("profit", tech="1c_battery", net=10, preferred=0.2)]
        actual = self.policy.evaluate_investment_accounts(rows, {"1c_battery": 5})
        self.assertEqual([row["accepted_addition_mw"] for row in actual], [20, 10])
        self.assertEqual(actual[1]["recommendation"], "Invest_Profit")

    def test_storage_multiple_high_agents_keep_original_individual_profit_floors(self):
        rows = [account("large", tech="1c_battery", net=90), account("small", tech="1c_battery", net=10)]
        actual = self.policy.evaluate_investment_accounts(rows, {"1c_battery": 100})
        self.assertEqual([row["accepted_addition_mw"] for row in actual], [90, 50])
        reference = source_decisions(rows, {"1c_battery": 100})
        self.assertEqual([row["accepted_addition_mw"] for row in actual], [reference[row["account_id"]]["delta_mw"] for row in actual])

    def test_depletion_is_preserved_when_positive_vre_proposals_are_scaled(self):
        rows = [account("loss", net=-2, target=20), account("build", net=80)]
        reference = source_decisions(rows, {"solar": 40})
        self.assertEqual(reference["loss"]["delta_mw"], 0, "source defect characterization")
        actual = self.policy.evaluate_investment_accounts(rows, {"solar": 40})
        self.assertEqual(actual[0]["retirement_mw"], 40)
        self.assertEqual(actual[0]["accepted_addition_mw"], 0)
        self.assertEqual(actual[1]["accepted_addition_mw"], 40)

    def test_depletion_never_exceeds_current_capacity(self):
        row = self.policy.evaluate_investment_accounts([account("loss", net=-20)], {})[0]
        self.assertEqual(row["retirement_mw"], 100)

    def test_nuclear_and_electrolyser_cannot_propose_or_economically_retire(self):
        rows = [account(tech, tech=tech, net=net) for tech, net in (("Nuclear", 1000), ("nuclear", -1000), ("electrolyzer", 1000))]
        for row in self.policy.evaluate_investment_accounts(rows, {}):
            self.assertEqual(row["accepted_addition_mw"], 0)
            self.assertEqual(row["retirement_mw"], 0)

    def test_storage_cap_uses_observed_leftover_charge_and_discharge(self):
        case = FIXTURE["cases"]["storage_credit"]
        result = self.policy.storage_expansion_from_traces(
            case["accepted_vre_mwh"], case["demand_mwh"],
            storage_charge_mwh=case["charge_mwh"], leftover_excess_mwh=case["leftover_excess_mwh"],
            storage_discharge_mwh=case["discharge_mwh"])
        self.assertEqual(result["excess_mwh"], case["excess_mwh"])
        self.assertEqual(result["deficit_mwh"], case["deficit_mwh"])

    def test_storage_virtual_pool_spectrum_matches_original_source_kernel(self):
        original = source_storage()
        # 800 charged/discharged hours span both the 730h and 365h bands.
        excess = np.tile([10.0, 0.0, 4.0, 0.0], 800)
        deficit = np.tile([0.0, 7.0, 0.0, 3.0], 800)
        zero = np.zeros(len(excess))
        actual = self.policy.storage_expansion_from_traces(
            zero, deficit, storage_charge_mwh=zero,
            leftover_excess_mwh=excess, storage_discharge_mwh=zero)
        self.assertEqual(actual["spectrum"], original["aligned_utilisation_spectrum"](excess, deficit))
        self.assertGreater(actual["spectrum"]["daily_loop"], 0)
        self.assertGreater(actual["spectrum"]["intraday"], 0)
        self.assertGreater(actual["limits_mw"]["1c_battery"], 0)
        self.assertEqual(actual["limits_mw"], original["calculate_storage_expansion_limits_from_profiles"](
            zero, deficit, store_charge=zero, excess_generation=excess,
            storage_discharge=zero, credit_mode="scheme_c"))

    def test_storage_missing_or_misaligned_trace_does_not_invent_a_fallback(self):
        with self.assertRaises(ValueError):
            self.policy.storage_expansion_from_traces([90], [60], storage_charge_mwh=[30],
                leftover_excess_mwh=None, storage_discharge_mwh=[0])
        with self.assertRaises(ValueError):
            self.policy.storage_expansion_from_traces([90], [60], storage_charge_mwh=[30, 0],
                leftover_excess_mwh=[10], storage_discharge_mwh=[0])

    def test_typed_decision_aggregates_owner_once_before_region_distribution(self):
        self.assertTrue(hasattr(self.policy, "decide_doctoral_investment"), "typed doctoral investment integration is missing")
        result = self.policy.decide_doctoral_investment(*typed_inputs())
        by_owner = {}
        for proposal in result.proposals:
            by_owner[proposal.agent_id] = by_owner.get(proposal.agent_id, 0) + proposal.capacity_mw
        self.assertEqual(by_owner, {"Z": 50, "A": 50})
        self.assertEqual([(proposal.region, proposal.capacity_mw) for proposal in result.proposals if proposal.agent_id == "Z"], [("Scotland", 25), ("North West", 25)])
        self.assertEqual(len(result.extensions["doctoral_investment_accounts"]), 2)
        self.assertEqual([row["net_revenue_gbp"] for row in result.extensions["doctoral_investment_accounts"]], [80, 80])

    def test_typed_decision_requires_complete_per_asset_cashflow(self):
        self.assertTrue(hasattr(self.policy, "decide_doctoral_investment"), "typed doctoral investment integration is missing")
        run, state, market, headroom, accounts = typed_inputs()
        with self.assertRaisesRegex(ValueError, "cashflow"):
            self.policy.decide_doctoral_investment(run, state, market, headroom)
        del accounts["z2"]
        with self.assertRaisesRegex(ValueError, "z2"):
            self.policy.decide_doctoral_investment(run, state, market, headroom, accounts)

    def test_typed_decision_uses_actual_account_cost_before_classification(self):
        self.assertTrue(hasattr(self.policy, "decide_doctoral_investment"), "typed doctoral investment integration is missing")
        run, state, market, headroom, accounts = typed_inputs()
        accounts["z1"] = {"market_income_gbp": 40, "operational_cost_gbp": 41}
        accounts["z2"] = {"market_income_gbp": 40, "operational_cost_gbp": 41}
        result = self.policy.decide_doctoral_investment(run, state, market, headroom, accounts)
        self.assertEqual(result.retirements_mw, {"z1": 25, "z2": 25})
        self.assertEqual([(proposal.agent_id, proposal.capacity_mw) for proposal in result.proposals], [("A", 80)])


if __name__ == "__main__":
    unittest.main()
