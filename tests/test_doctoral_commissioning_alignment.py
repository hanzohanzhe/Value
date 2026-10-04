"""Small source-backed commissioning tests; never import the annual main loop."""
from __future__ import annotations

import ast
from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from gridform_core.asset_economics import build_asset_economic_extensions, validate_asset_economics
from gridform_core.v2.contracts import AssetStateV2, OperatingState, YearState


MODULE = "gridform_core.builtin.scheme_c_1000twh.doctoral_commissioning"
SOURCE = "run_investment_analysis_case3_decarbonization_breakdown_cm.py"
FIXTURE = json.loads((Path(__file__).parent / "fixtures/doctoral_alignment/investment.json").read_text(encoding="utf-8"))


def original_tree():
    raw = (Path(FIXTURE["source_root"]) / SOURCE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE["source_hashes"][SOURCE]:
        raise ValueError("doctoral commissioning source identity changed")
    return ast.parse(raw.decode("utf-8-sig"))


def original_tables():
    main = next(node for node in original_tree().body if isinstance(node, ast.FunctionDef) and node.name == "main")
    names = {"pumped_hydro_expansion_plan", "pumped_hydro_energy_storage_plan", "pumped_hydro_capex_plan"}
    return {node.targets[0].id: ast.literal_eval(node.value) for node in main.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names}


def original_pumped_update(year):
    tree = original_tree()
    candidates = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and "current_year in pumped_hydro_expansion_plan" in ast.unparse(node.test)]
    if len(candidates) != 1:
        raise ValueError("source annual pumped block is not unique")
    battery = SimpleNamespace(pool_limit=2000, per_pool_limit=8000, capital_cost=720000000)
    namespace = {**original_tables(), "VALIDATION_MODE": False, "current_year": year,
                 "battery_objects": {"pumpedhydro_battery": battery}}
    with redirect_stdout(io.StringIO()):
        exec(compile(ast.Module(body=candidates, type_ignores=[]), "<original-pumped-year-block>", "exec"), namespace)
    return battery


def original_owner_additions(existing, projects, cost_per_mw):
    tree = original_tree()
    branches = [node for node in ast.walk(tree) if isinstance(node, ast.If) and node.lineno == 1873
                and ast.unparse(node.test) == "asset_type in ['solar', 'onshore', 'offshore']"]
    if len(branches) != 1:
        raise ValueError("source VRE commissioning branch is not unique")
    classify = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "get_asset_type")
    class SourceVRE:
        pass
    generators = {}
    for name, capacity in existing.items():
        asset = SourceVRE()
        asset.capacity_multiplier, asset.capital_cost = capacity, 0.0
        generators[name] = asset
    source_projects = [{"capacity": p["capacity_mw"], "assigned_generator": p.get("assigned_generator"), "source": p["project_id"]} for p in projects]
    namespace = {"asset_type": "solar", "projects": source_projects, "generator_objects": generators,
        "battery_objects": {}, "project_pipeline": list(source_projects), "current_year": 2026,
        "config": SimpleNamespace(capital_costs_per_mw={"solar": cost_per_mw}),
        "ExpensiverenewableGenerator": SourceVRE, "investment_summary": []}
    with redirect_stdout(io.StringIO()):
        exec(compile(ast.Module(body=[classify, *branches[0].body], type_ignores=[]), "<original-owner-commissioning>", "exec"), namespace)
    return {name: {"capacity_mw": value.capacity_multiplier - existing[name], "capital_gbp": value.capital_cost} for name, value in generators.items()}


def state_fixture(year=2025, operating=False):
    ext = build_asset_economic_extensions("pumped_hydro", 2828.0, energy_capacity_mwh=26700.0,
        capital_costs_per_mw={}, lifetimes={}, discount_rate=0.05, source_record_id="pumpedhydro_battery")
    ext["weather_source_weights"] = {"sentinel": 1.0}
    pumped = AssetStateV2("pumpedhydro_battery", "pumped_hydro", 2828.0, 26700.0, "Scotland", extensions=ext)
    nuclear = AssetStateV2("Nuclear", "Nuclear", 5958.0, region="GB", extensions={"investment_eligible": False})
    if operating:
        return OperatingState(year, (pumped, nuclear), (), extensions={"sentinel": "retained"})
    return YearState(year, (pumped, nuclear), (), cumulative_metrics={"test": 1}, extensions={"sentinel": "retained"})


class DoctoralCommissioningAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "doctoral commissioning policy is missing")
        self.policy = importlib.import_module(MODULE)

    def test_schedule_each_year_matches_original_literals_and_annual_assignments(self):
        tables = original_tables()
        schedule = self.policy.load_pumped_hydro_schedule()
        self.assertEqual(set(schedule), set(range(2025, 2036)))
        for year in range(2025, 2036):
            original = original_pumped_update(year)
            row = schedule[year]
            self.assertEqual(row["power_mw"], tables["pumped_hydro_expansion_plan"][year])
            self.assertEqual(row["energy_mwh"], tables["pumped_hydro_energy_storage_plan"][year])
            self.assertEqual(row["capital_cost_gbp"], tables["pumped_hydro_capex_plan"][year])
            self.assertEqual(row["source_pool_limit"], original.pool_limit)
            self.assertEqual(row["source_per_pool_limit"], original.per_pool_limit)

    def test_2034_updates_declared_capacity_energy_and_capital_together(self):
        state = state_fixture(2034)
        result = self.policy.apply_doctoral_pumped_schedule(state)
        pumped = result.assets[0]
        self.assertEqual((pumped.capacity_mw, pumped.energy_capacity_mwh), (5687.9, 70800.0))
        self.assertEqual(pumped.extensions["total_capex_gbp"], 596400000.0)
        self.assertAlmostEqual(pumped.extensions["capital_cost_per_mw"] * pumped.capacity_mw, 596400000.0)
        self.assertEqual(pumped.extensions["energy_capacity_mwh_basis"], 70800.0)
        validate_asset_economics(pumped)
        self.assertEqual(state.assets[0].capacity_mw, 2828.0)
        self.assertEqual(result.cumulative_metrics, state.cumulative_metrics)

    def test_updates_both_typed_state_forms_and_preserves_nuclear_and_weather(self):
        for operating in (False, True):
            with self.subTest(operating=operating):
                state = state_fixture(2031, operating)
                result = self.policy.apply_doctoral_pumped_schedule(state)
                self.assertIs(type(result), type(state))
                self.assertIs(result.assets[1], state.assets[1])
                self.assertEqual(result.assets[0].extensions["weather_source_weights"], state.assets[0].extensions["weather_source_weights"])
                self.assertEqual(result.extensions["sentinel"], "retained")

    def test_schedule_is_idempotent_and_does_not_invent_missing_assets(self):
        first = self.policy.apply_doctoral_pumped_schedule(state_fixture(2030))
        self.assertEqual(self.policy.apply_doctoral_pumped_schedule(first), first)
        empty = replace(first, assets=(first.assets[1],))
        self.assertIs(self.policy.apply_doctoral_pumped_schedule(empty), empty)

    def test_historical_validation_and_years_outside_table_are_unchanged(self):
        for year in (2024, 2036):
            state = state_fixture(year)
            self.assertIs(self.policy.apply_doctoral_pumped_schedule(state), state)
        state = state_fixture(2034)
        self.assertIs(self.policy.apply_doctoral_pumped_schedule(state, validation_mode=True), state)

    def test_scheduled_object_must_not_be_resolved_by_technology_name_alone(self):
        state = state_fixture(2034)
        other = replace(state.assets[0], asset_id="a-different-pumped-project")
        state = replace(state, assets=(other, state.assets[1]))
        self.assertIs(self.policy.apply_doctoral_pumped_schedule(state), state)

    def test_assigned_owner_is_applied_before_unassigned_proportional_additions(self):
        existing = {"solar_A": 100.0, "solar_B": 100.0}
        projects = [{"project_id": "unlocated", "capacity_mw": 80.0},
                    {"project_id": "located", "capacity_mw": 20.0, "assigned_generator": "solar_A"}]
        original = original_owner_additions(existing, projects, 1000)
        actual = self.policy.allocate_doctoral_vre_owners(existing, projects, capital_cost_per_mw=1000)
        for owner in existing:
            self.assertAlmostEqual(actual["agent_additions_mw"][owner], original[owner]["capacity_mw"])
            self.assertAlmostEqual(actual["agent_capital_additions_gbp"][owner], original[owner]["capital_gbp"])
        self.assertAlmostEqual(actual["agent_additions_mw"]["solar_A"], 20 + 80 * 120 / 220)
        self.assertEqual(actual["project_owner_allocations_mw"]["located"], {"solar_A": 20})
        self.assertEqual(existing, {"solar_A": 100.0, "solar_B": 100.0})
        self.assertEqual(projects[0], {"project_id": "unlocated", "capacity_mw": 80.0})

    def test_unresolvable_assigned_owner_is_not_replaced_by_a_weather_owner(self):
        result = self.policy.allocate_doctoral_vre_owners({"solar_A": 100}, [
            {"project_id": "p", "capacity_mw": 20, "assigned_generator": "missing",
             "weather_source_weights": {"solar_A": 1}}])
        self.assertEqual(result["agent_additions_mw"], {"solar_A": 0})
        self.assertEqual(result["unresolved_project_ids"], ["p"])

    def test_zero_existing_capacity_uses_original_first_generator_fallback(self):
        existing = {"solar_Z": 0, "solar_A": 0}
        projects = [{"project_id": "p", "capacity_mw": 20}]
        original = original_owner_additions(existing, projects, 100)
        actual = self.policy.allocate_doctoral_vre_owners(existing, projects, capital_cost_per_mw=100)
        self.assertEqual(actual["agent_additions_mw"], {"solar_Z": 20, "solar_A": 0})
        self.assertEqual(actual["agent_additions_mw"]["solar_Z"], original["solar_Z"]["capacity_mw"])

    def test_original_micro_capacity_skip_is_visible_and_not_renormalized(self):
        existing = {"solar_A": 100, "solar_B": 1e-10}
        projects = [{"project_id": "p", "capacity_mw": 1}]
        actual = self.policy.allocate_doctoral_vre_owners(existing, projects)
        original = original_owner_additions(existing, projects, 0)
        self.assertAlmostEqual(actual["agent_additions_mw"]["solar_A"], original["solar_A"]["capacity_mw"])
        self.assertEqual(actual["agent_additions_mw"]["solar_B"], 0)
        self.assertGreater(actual["unallocated_capacity_mw"], 0)


if __name__ == "__main__":
    unittest.main()
