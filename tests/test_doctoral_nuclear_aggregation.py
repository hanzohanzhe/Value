"""Registered policy stations feed ONE national dispatch and cashflow object."""
from dataclasses import replace
import json
import unittest

from gridform_core import canonical_psm_data as canonical
from gridform_core.asset_economics import build_asset_economic_extensions, primary_annual_asset_costs, validate_asset_economics
from gridform_core.builtin.scheme_c_1000twh.doctoral_market_factory import from_doctoral_psm_input
from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
from gridform_core.builtin.scheme_c_1000twh.doctoral_period_ledger import DoctoralPeriodLedger
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCPlanningPipelineDefinition, SchemeCStateTransitionDefinition
from gridform_core.nuclear_policy import build_value_uk_nuclear_projects, existing_nuclear_asset_specs
from gridform_core.nuclear_policy import load_value_uk_nuclear_policy
from gridform_core.v2.contracts import AssetStateV2, OperatingState, YearState, InvestmentDecision, PlanningAdmissionResult, ResolvedRun
from tests import test_doctoral_weather as weather_fixtures


PROFILE = {"doctoral_alignment_profile": "value.doctoral-national/v1"}
NUCLEAR = {"name": "Nuclear", "capacity_limit": 5883.0, "alter_limit": 500.0,
           "startup_cost": 500.0, "capital_cost": 470640000.0,
           "gen_cost": 0.0, "unit_time_cost": 0.0, "curtail_cost": 91430.0, "carbon_emission": 0.0}


def station(asset_id, capacity, *, included=True, unavailable=2056, price=80000.0):
    economics = build_asset_economic_extensions("Nuclear", capacity, energy_capacity_mwh=None,
        capital_costs_per_mw={"Nuclear": price}, lifetimes={"Nuclear": 40},
        discount_rate=.05, source_record_id=asset_id)
    return AssetStateV2(asset_id, "Nuclear", capacity, region="station-region", extensions={
        **economics, "investment_owner_id": asset_id, "investment_eligible": False,
        "primary_cost_ledger_included": included, "doctoral_parameter_source_id": "Nuclear",
        "station_name": asset_id, "model_unavailable_from_year": unavailable})


class DoctoralNuclearAggregationTests(unittest.TestCase):
    def setUp(self):
        fixture = weather_fixtures.DoctoralWeatherTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.pack, self.manifest, self.fleet = fixture.pack, fixture.manifest, fixture.fleet
        self.fleet["generators"]["Nuclear"] = dict(NUCLEAR)
        self.fleet["generators"]["CCGT"] = {
            "gen_cost": 30, "curtail_cost": 30, "carbon_emission": 0,
            "capital_cost": 100, "unit_time_cost": 0, "alter_limit": 100,
            "startup_cost": 0, "carbon_intensity": 0, "carbon_price": 0,
            "fuel_cost": 30, "real_gen_energy": 0}
        self.fleet["connections"] = {key: {"capital_cost": 100.0, "carbon_emission": 0.0, "carbon_intensity": 53.0}
            for key in ("Interconnect_France", "Interconnect_Netherland", "Interconnect_Ireland", "Interconnect_Norway", "Interconnect_Beligum")}
        path = self.pack / self.manifest["bindings"]["fleet.generators"]["uri"]
        path.write_text(json.dumps(self.fleet), encoding="utf-8")

    def prepared(self, state, periods=2):
        return canonical.build_doctoral_psm_input(self.pack, self.manifest, state,
            run_id="bounded-nuclear", periods=periods, period_hours=.5)

    def registered(self, assets=None, year=2025):
        return OperatingState(year, assets or (station("station:a", 1000), station("station:b", 2000)), (), extensions=PROFILE)

    def test_registered_capacity_is_dispatched_once_with_one_national_ramp(self):
        original = self.registered()
        frozen = original.to_dict()
        model = self.prepared(original)
        self.assertEqual([(a.asset_id, a.capacity_mw) for a in model.operating_state.assets], [("Nuclear", 3000)])
        resources = [r for r in model.chronology.resources if r.technology == "Nuclear"]
        self.assertEqual([(r.asset_id, r.capacity_mw) for r in resources], [("Nuclear", 3000)])
        generators, batteries, _ = from_doctoral_psm_input(model, self.fleet, {})
        self.assertEqual(len(generators), 1)
        generator = generators[0]
        self.assertEqual((generator.name, generator.capacity_limit, generator.capital_cost), ("Nuclear", 3000, 470640000))
        engine = DoctoralPeriodEngine(generators, batteries, year=2025)
        outcome = engine.realise_period(engine.plan_period(3000), 0)
        # Original single aggregate can ramp down only 500 MW, not 500 per station.
        self.assertEqual(outcome.generation_mwh_by_asset, {"Nuclear": 1250.0})
        self.assertEqual(outcome.non_vre_spill_mwh, 1250.0)
        self.assertEqual(original.to_dict(), frozen)

    def test_primary_cost_excludes_externally_financed_station_and_keeps_register(self):
        assets = (station("station:a", 1000), station("station:hpc", 1630, included=False, price=17500000000/1630))
        model = self.prepared(self.registered(assets))
        national = model.operating_state.assets[0]
        validate_asset_economics(national)
        self.assertEqual(national.extensions["total_capex_gbp"], 80000000)
        self.assertAlmostEqual(primary_annual_asset_costs(national)[0], primary_annual_asset_costs(assets[0])[0])
        register = model.operating_state.extensions["doctoral_nuclear_register"]
        self.assertEqual(register["station_assets"], [a.to_dict() for a in assets])
        self.assertFalse(register["station_assets"][1]["extensions"]["primary_cost_ledger_included"])
        self.assertEqual(register["station_assets"][1]["extensions"]["total_capex_gbp"], 17500000000)
        self.assertEqual(national.extensions["investment_owner_id"], "Nuclear")
        self.assertFalse(national.extensions["investment_eligible"])

    def test_lifecycle_station_ledger_controls_2031_and_2032_without_adding_sizewell_c(self):
        assets = tuple(station(row["asset_id"], row["capacity_mw"], unavailable=row["model_unavailable_from_year"])
                       for row in existing_nuclear_asset_specs(2025))
        projects = tuple(replace(p, extensions={**dict(p.extensions), "doctoral_parameter_source_id": "Nuclear"})
            for p in build_value_uk_nuclear_projects(start_year=2025, end_year=2034, capital_discount_rate=.05))
        state = YearState(2025, assets, projects, extensions=PROFILE)
        run = ResolvedRun("run", "project", "scenario", "pack", 2025, 2034, {}, {}, {})
        capacities = []
        for year in range(2025, 2035):
            advance = SchemeCPlanningPipelineDefinition().advance_year(run, state)
            operating = advance.operating_state
            model = self.prepared(operating, periods=1)
            capacities.append(model.operating_state.assets[0].capacity_mw)
            self.assertIn("sizewell-c", [p.project_id for p in model.operating_state.active_planning_projects])
            self.assertEqual(len(from_doctoral_psm_input(model, self.fleet, {})[0]), 1)
            state = SchemeCStateTransitionDefinition().apply(run,
                YearState(year, operating.assets, operating.active_planning_projects, extensions=PROFILE),
                PlanningAdmissionResult(year, (), (), operating.active_planning_projects, ()),
                InvestmentDecision("none", year, "fixture-no-investment", (), {}))
        self.assertEqual(capacities, [5958, 5958, 5958, 5958, 5958, 5958, 2828, 4458, 4458, 4458])

    def test_malformed_or_mixed_registrations_are_not_silently_merged(self):
        a, b = self.registered().assets
        for assets, pattern in (
            ((a, a), "Duplicate"),
            ((a, replace(b, asset_id="Nuclear")), "mixed|Mixed"),
            ((a, replace(b, capacity_mw=-1)), "capacity"),
            ((a, replace(b, extensions={**dict(b.extensions), "doctoral_parameter_source_id": "Other"})), "parameter"),
            ((a, replace(b, extensions={**dict(b.extensions), "model_unavailable_from_year": 2025})), "retirement"),
            ((a, replace(b, extensions={**dict(b.extensions), "model_first_full_operating_year": 2031})), "commission"),
        ):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                self.prepared(self.registered(assets))

    def test_unselected_profile_is_not_silently_changed(self):
        with self.assertRaisesRegex(ValueError, "profile"):
            self.prepared(replace(self.registered(), extensions={}))

    def test_retired_only_register_has_no_phantom_dispatch_object(self):
        asset = station("retired", 1000)
        model = self.prepared(self.registered((replace(asset, status="retired", capacity_mw=0),)))
        self.assertEqual(model.operating_state.assets, ())
        self.assertFalse(any(r.technology == "Nuclear" for r in model.chronology.resources))
        self.assertEqual(len(model.operating_state.extensions["doctoral_nuclear_register"]["station_assets"]), 1)

    def test_policy_cost_evidence_is_preserved_without_becoming_primary_capex(self):
        policy = load_value_uk_nuclear_policy()
        state = replace(self.registered(), extensions={**PROFILE, "nuclear_policy": {
            "policy_id": policy["policy_id"], "version": policy["version"]}})
        model = self.prepared(state)
        evidence = model.operating_state.extensions["doctoral_nuclear_register"]["policy_evidence"]
        self.assertEqual(evidence["cost_evidence"], policy["cost_evidence"])
        self.assertEqual(model.operating_state.assets[0].extensions["total_capex_gbp"], 240000000)

    def test_incompatible_primary_financial_bases_are_not_averaged(self):
        a, b = self.registered().assets
        other_economics = build_asset_economic_extensions("Nuclear", 2000, energy_capacity_mwh=None,
            capital_costs_per_mw={"Nuclear": 80000}, lifetimes={"Nuclear": 20},
            discount_rate=.05, source_record_id=b.asset_id)
        b = replace(b, extensions={**dict(b.extensions), **other_economics})
        with self.assertRaisesRegex(ValueError, "Incompatible.*economics"):
            self.prepared(self.registered((a, b)))

    def test_other_assets_and_planning_records_are_unchanged_in_national_view(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_nuclear import aggregate_doctoral_nuclear_state
        a, b = self.registered().assets
        solar = AssetStateV2("solar:x", "solar", 50, region="kept-region", extensions={"weather_source_asset_id": "solar_London"})
        projects = build_value_uk_nuclear_projects(start_year=2025, end_year=2034, capital_discount_rate=.05)
        state = replace(self.registered((solar, a, b)), active_planning_projects=projects)
        result = aggregate_doctoral_nuclear_state(state)
        self.assertEqual(result.assets[0].to_dict(), solar.to_dict())
        self.assertEqual(result.active_planning_projects, projects)
        self.assertEqual(result.assets[1].region, "GB")

    def test_already_aggregated_state_is_rejected_and_register_is_independent(self):
        original = self.registered()
        model = self.prepared(original)
        with self.assertRaisesRegex(ValueError, "already aggregated"):
            self.prepared(model.operating_state)
        original.assets[0].extensions["station_name"] = "changed externally"
        self.assertEqual(model.operating_state.extensions["doctoral_nuclear_register"]["station_assets"][0]["extensions"]["station_name"], "station:a")

    def test_mutated_register_or_aggregate_cost_is_rejected_at_factory(self):
        model = self.prepared(self.registered())
        model.operating_state.extensions["doctoral_nuclear_register"]["station_assets"][0]["extensions"]["station_name"] = "tampered"
        with self.assertRaisesRegex(ValueError, "identity"):
            from_doctoral_psm_input(model, self.fleet, {})
        model = self.prepared(self.registered())
        model.operating_state.assets[0].extensions["total_capex_gbp"] *= 2
        with self.assertRaisesRegex(ValueError, "economics|CAPEX"):
            from_doctoral_psm_input(model, self.fleet, {})

    def test_same_capacity_different_register_cannot_reuse_engine_checkpoint(self):
        first = self.prepared(self.registered())
        second = self.prepared(self.registered((station("station:c", 1000), station("station:b", 2000))))
        one = from_doctoral_psm_input(first, self.fleet, {})[0]
        two = from_doctoral_psm_input(second, self.fleet, {})[0]
        before = DoctoralPeriodEngine(one, (), year=2025)
        with self.assertRaisesRegex(ValueError, "identity|input"):
            DoctoralPeriodEngine(two, (), year=2025, checkpoint=before.export_state())

    def test_missing_register_with_aggregation_markers_is_rejected(self):
        model = self.prepared(self.registered())
        del model.operating_state.extensions["doctoral_nuclear_register"]
        model.operating_state.assets[0].extensions["total_capex_gbp"] *= 2
        with self.assertRaisesRegex(ValueError, "register.*missing|Missing.*register"):
            from_doctoral_psm_input(model, self.fleet, {})

    def test_deleted_register_cannot_be_reaggregated_as_a_station(self):
        model = self.prepared(self.registered())
        del model.operating_state.extensions["doctoral_nuclear_register"]
        with self.assertRaisesRegex(ValueError, "aggregated|register"):
            self.prepared(model.operating_state)

    def test_all_retired_register_still_binds_engine_checkpoint_identity(self):
        gas = AssetStateV2("CCGT", "CCGT", 100)
        engines = []
        for name in ("retired:a", "retired:b"):
            retired = replace(station(name, 1000), status="retired", capacity_mw=0)
            model = self.prepared(self.registered((retired, gas)))
            objects = from_doctoral_psm_input(model, self.fleet, {})
            engines.append(DoctoralPeriodEngine(objects[0], objects[1], year=2025))
        with self.assertRaisesRegex(ValueError, "identity|input"):
            DoctoralPeriodEngine(objects[0], objects[1], year=2025,
                                 checkpoint=engines[0].export_state())

    def test_empty_station_register_cannot_hide_due_commissioning(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_nuclear import aggregate_doctoral_nuclear_state
        projects = build_value_uk_nuclear_projects(start_year=2025, end_year=2034, capital_discount_rate=.05)
        state = OperatingState(2031, (), projects, extensions=PROFILE)
        with self.assertRaisesRegex(ValueError, "commission"):
            aggregate_doctoral_nuclear_state(state)

    def test_future_pipeline_is_preserved_even_without_station_assets(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_nuclear import aggregate_doctoral_nuclear_state, validate_doctoral_nuclear_view
        projects = build_value_uk_nuclear_projects(start_year=2025, end_year=2034, capital_discount_rate=.05)
        state = OperatingState(2025, (), projects, extensions=PROFILE)
        projected = aggregate_doctoral_nuclear_state(state)
        self.assertEqual(projected.extensions.get("doctoral_nuclear_register", {}).get("pipeline_projects"),
                         [p.to_dict() for p in projects])
        validate_doctoral_nuclear_view(projected)

    def test_national_cashflow_and_json_resume_have_one_nuclear_owner(self):
        model = self.prepared(self.registered())
        generators = from_doctoral_psm_input(model, self.fleet, {})[0]
        engine = DoctoralPeriodEngine(generators, (), year=2025)
        initial = engine.state
        outcome = engine.realise_period(engine.plan_period(3000), 3000)
        ledger = DoctoralPeriodLedger(run_id="nuclear", input_sha256=engine.input_sha256,
            source_rule_sha256="a"*64, weather_sha256="b"*64, initial_state=initial, asset_ids=("Nuclear",))
        ledger.append(outcome)
        engine.commit(outcome)
        self.assertEqual(set(ledger.build_asset_accounts(model.operating_state, {"scenario": "basic"})), {"Nuclear"})
        resumed = DoctoralPeriodEngine(generators, (), year=2025, checkpoint=json.loads(json.dumps(engine.export_state())))
        continuous = engine.realise_period(engine.plan_period(2800), 2800)
        restarted = resumed.realise_period(resumed.plan_period(2800), 2800)
        self.assertEqual(continuous.to_dict(), restarted.to_dict())


if __name__ == "__main__":
    unittest.main()
