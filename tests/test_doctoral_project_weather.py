"""Project commissioning must retain source-derived weather, not a CSV fallback."""
import json
import unittest
from dataclasses import replace
import pandas as pd

from gridform_core.asset_economics import build_asset_economic_extensions
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCPlanningPipelineDefinition
from gridform_core.canonical_psm_data import native_initial_state
from gridform_core.doctoral_weather_mapping import attach_project_weather, nearest_site, source_weights
from gridform_core.v2.contracts import PlanningProject, ResolvedRun, YearState
from tests import test_doctoral_weather as weather_fixtures


class DoctoralProjectWeatherTests(unittest.TestCase):
    def setUp(self):
        self.fx = weather_fixtures.DoctoralWeatherTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.sites = {
            "solar_Nottingham": {"technology": "solar", "lat": 53., "lon": -1.},
            "solar_London": {"technology": "solar", "lat": 51., "lon": -1.},
            "onshore_Nottingham": {"technology": "onshore", "lat": 53., "lon": -1.},
            "offshore1": {"technology": "offshore", "lat": 53., "lon": 1.},
        }
        self.run = ResolvedRun("weather", "study", "scenario", "pack", 2025, 2034, {}, {}, {})

    def project(self, name, capacity, **extensions):
        economy = build_asset_economic_extensions("solar", capacity,
            energy_capacity_mwh=None,
            capital_costs_per_mw={"solar": 1000.}, lifetimes={"solar": 25.},
            discount_rate=.05, source_record_id=name)
        return PlanningProject(name, name, "repd", "solar", capacity, capacity,
            "London", "construction", "active", 2025, 2026, "expected_capacity", 1.,
            extensions={**economy, **extensions})

    def state(self, projects):
        return YearState(2026, self.fx.assets, tuple(projects), extensions={
            "doctoral_weather_reference_sites": self.sites})

    def advance(self, state):
        return SchemeCPlanningPipelineDefinition().advance_year(self.run, state).operating_state

    def test_unlocated_batch_uses_stock_after_same_year_assigned_projects(self):
        unknown = self.project("unlocated", 80., weather_assignment_rule="doctoral_proportional_at_commissioning")
        assigned = self.project("located", 20., weather_source_asset_id="solar_London")
        state = self.advance(self.state([unknown, assigned]))
        row = next(a for a in state.assets if a.asset_id == "commissioned:unlocated")
        self.assertEqual(row.extensions.get("weather_source_weights"), {
            "solar_London": 120 / 220,
            # Source gives the last sorted generator the floating remainder.
            "solar_Nottingham": (80. - 80. * (120. / 220.)) / 80.})
        self.assertEqual(row.capacity_mw, 80.)
        self.assertIsNone(row.extensions["investment_owner_id"])

    def test_frozen_weights_survive_json_and_later_stock_changes(self):
        p = self.project("unlocated", 80., weather_assignment_rule="doctoral_proportional_at_commissioning")
        operating = self.advance(self.state([p]))
        saved = YearState(2027, operating.assets, (), extensions=operating.extensions)
        restored = YearState.from_dict(json.loads(json.dumps(saved.to_dict())))
        self.assertIn("weather_source_weights", restored.assets[-1].extensions)
        altered = tuple(replace(a, capacity_mw=900.) if a.asset_id == "solar_London" else a for a in restored.assets)
        rows = {r.asset_id: r for r in self.fx.chronology(assets=altered).resources}
        self.assertAlmostEqual(rows["commissioned:unlocated"].availability[4], .375)

    def test_proportional_cohort_is_not_sensitive_to_project_order(self):
        one = self.project("one", 80., weather_assignment_rule="doctoral_proportional_at_commissioning")
        two = self.project("two", 20., weather_assignment_rule="doctoral_proportional_at_commissioning")
        output = self.advance(self.state([one, two]))
        weighted = [a for a in output.assets if a.asset_id.startswith("commissioned:")]
        self.assertEqual([a.extensions.get("weather_source_weights") for a in weighted],
                         [{"solar_London": .5, "solar_Nottingham": .5}] * 2)

    def test_failed_and_future_projects_do_not_change_allocation(self):
        p = self.project("unlocated", 80., weather_assignment_rule="doctoral_proportional_at_commissioning")
        failed = replace(self.project("failed", 500., weather_source_asset_id="solar_London"), outcome="failed_planning")
        future = replace(self.project("future", 500., weather_source_asset_id="solar_London"), expected_completion_year=2027)
        output = self.advance(self.state([p, failed, future]))
        row = next(a for a in output.assets if a.asset_id == "commissioned:unlocated")
        self.assertEqual(row.extensions.get("weather_source_weights"), {"solar_London": .5, "solar_Nottingham": .5})

    def test_empty_stock_uses_original_first_matching_representative(self):
        p = self.project("unlocated", 80., weather_assignment_rule="doctoral_proportional_at_commissioning")
        state = self.state([p])
        state = replace(state, assets=tuple(replace(a, capacity_mw=0.) for a in state.assets))
        output = self.advance(state)
        row = next(a for a in output.assets if a.asset_id == "commissioned:unlocated")
        self.assertEqual(row.extensions.get("weather_source_weights"), {"solar_Nottingham": 1.})

    def test_missing_unproven_mapping_still_fails_before_commissioning(self):
        with self.assertRaisesRegex(ValueError, "weather.*mapping|weather.*identity"):
            self.advance(self.state([self.project("unknown", 10.)]))

    def test_initial_native_state_attaches_region_mapping_to_new_solar_project(self):
        manifest = self.fx.manifest
        pack = self.fx.pack
        (pack / "manifest.json").write_text(json.dumps(manifest))
        repd = pack / manifest["bindings"]["projects.repd"]["uri"]
        repd.write_text("project_id,site_name,technology,capacity_mw,development_status,region\nnew,new,solar,20,Under Construction,London\n")
        state = native_initial_state(pack, 2025)
        p = next(p for p in state.planning_projects if p.project_id == "new")
        self.assertEqual(p.extensions.get("weather_source_asset_id"), "solar_London")
        self.assertIsNone(p.assigned_asset_id)  # Do not change financial ownership.

    def map_projects(self, projects, rows=()):
        fleet = {"generators": dict.fromkeys(self.sites), "locations": {
            (n if s["technology"] == "offshore" else n.split("_", 1)[1]):
                {"lat": s["lat"], "lon": s["lon"]} for n, s in self.sites.items()}}
        return attach_project_weather(self.state(projects), fleet, pd.DataFrame(rows)).planning_projects

    def test_coordinates_override_region_and_preserve_nearest_tie_order(self):
        p = replace(self.project("located", 10.), latitude=53., longitude=-1.)
        mapped = self.map_projects([p])[0]
        self.assertEqual(mapped.extensions["weather_source_asset_id"], "solar_Nottingham")
        self.assertEqual(nearest_site(52., -1., "solar", self.sites), "solar_Nottingham")

    def test_raw_project_coordinates_then_last_valid_site_name_fallback(self):
        p = self.project("id", 10.)
        rows = [{"Ref ID": "id", "Site Name": "id", "Latitude": 53., "Longitude": -1.},
                {"Ref ID": "other", "Site Name": "id", "Latitude": 51., "Longitude": -1.}]
        self.assertEqual(self.map_projects([p], rows)[0].extensions["weather_source_asset_id"], "solar_Nottingham")
        p = replace(p, project_id="missing")
        self.assertEqual(self.map_projects([p], rows)[0].extensions["weather_source_asset_id"], "solar_London")

    def test_planning_osgb_is_not_silently_converted_and_unknown_uses_declared_rule(self):
        p = replace(self.project("id", 10.), region="unrecognised")
        mapped = self.map_projects([p], [{"Ref ID": "id", "X-coordinate": 530000, "Y-coordinate": 180000}])[0]
        self.assertNotIn("weather_source_asset_id", mapped.extensions)
        self.assertEqual(mapped.extensions["weather_assignment_rule"], "doctoral_proportional_at_commissioning")
        self.assertEqual(mapped.extensions["weather_project_location"], {"lat": None, "lon": None})

    def test_corrupted_explicit_identity_and_invalid_weights_fail_closed(self):
        original = self.fx.assets[0]
        for bad in ({"weather_source_asset_id": "missing"},
                    {"weather_source_asset_id": "offshore1"},
                    {"weather_source_weights": {"solar_London": -1.}},
                    {"weather_source_weights": {"solar_London": float("nan")}},
                    {"weather_source_weights": {"solar_London": 1.1}},
                    {"weather_source_weights": {"solar_London": .2}},
                    {"weather_source_weights": {"solar_London": 0.}},
                    {"weather_source_weights": {"solar_London": .2}, "weather_allocation_cohort_mw": 80.},
                    {"weather_source_weights": {"offshore1": 1.}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                source_weights(replace(original, technology="solar", extensions=bad), self.sites)

    def test_original_fraction_before_multiplication_order_and_tiny_skip(self):
        p = self.project("small", 1e-6, weather_assignment_rule="doctoral_proportional_at_commissioning")
        row = self.advance(self.state([p])).assets[-1]
        self.assertEqual(row.extensions["weather_source_weights"], {"solar_London": 0., "solar_Nottingham": 0.})
        self.assertEqual(set(self.fx.chronology(assets=(row,)).resources[0].availability), {0.})

    def test_endogenous_owner_is_retained_as_weather_lineage(self):
        p = self.project("endogenous", 10., investment_owner_id="solar_London")
        row = self.advance(self.state([p])).assets[-1]
        self.assertEqual(row.extensions["weather_source_weights"], {"solar_London": 1.})
        self.assertEqual(row.extensions["investment_owner_id"], "solar_London")

    def test_later_cohort_uses_prior_frozen_lineage_and_reduced_current_capacity(self):
        first = self.project("first", 100., weather_assignment_rule="doctoral_proportional_at_commissioning")
        operating = self.advance(self.state([first]))
        assets = tuple(replace(a, capacity_mw=0.) if a.asset_id == "solar_London" else a
                       for a in operating.assets)
        second = replace(self.project("second", 80., weather_assignment_rule="doctoral_proportional_at_commissioning"),
                         expected_completion_year=2027)
        state = YearState(2027, assets, (second,), extensions=operating.extensions)
        output = self.advance(state)
        self.assertEqual(output.assets[-1].extensions["weather_source_weights"],
                         {"solar_London": .25, "solar_Nottingham": .75})
        old = next(a for a in output.assets if a.asset_id == "commissioned:first")
        self.assertEqual(old.extensions["weather_source_weights"], {"solar_London": .5, "solar_Nottingham": .5})


if __name__ == "__main__":
    unittest.main()
