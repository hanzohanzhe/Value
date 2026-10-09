"""Actual canonical-entry tests for the explicit national doctoral profile."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd

from gridform_core.canonical_psm_data import build_chronology, native_initial_state
from gridform_core.data_method import run_policy
from gridform_core.v2.contracts import AssetStateV2, OperatingState, PSMInput
from gridform_core.builtin.scheme_c_1000twh.doctoral_market_factory import from_doctoral_psm_input
from tests.test_doctoral_market_factory import gas_parameters, pumped_parameters
from tests.test_doctoral_planning_alignment import FIXTURE
from tests import test_doctoral_weather as weather_fixtures


ROOT = Path(__file__).resolve().parents[1]


class DoctoralCanonicalEntryTests(unittest.TestCase):
    def setUp(self):
        fixture = weather_fixtures.DoctoralWeatherTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.pack, self.manifest, self.fleet = fixture.pack, fixture.manifest, fixture.fleet
        self.fleet["generators"].update({"bio_and_waste": {"capacity_limit": 20.0}, "Nuclear": {"capacity_limit": 5958.0}})
        self.write_json("fleet.generators", self.fleet)
        costs = json.loads(self.path("costs.capital").read_text())
        # Supply a synthetic cost for the old adapter's raw-nuclear label too,
        # so RED exposes duplicate admission rather than stopping on economics.
        costs["capital_costs_per_mw"].update({"bio_and_waste": 1500000.0, "Nuclear": 3000000.0, "nuclear_nuclear": 3000000.0})
        self.write_json("costs.capital", costs)
        self.write_json("planning.timelines", {
            "development_stage_timelines": FIXTURE["context"]["development_stage_timelines"],
            "repd_status_to_timeline": FIXTURE["context"]["repd_status_to_timeline"],
            "development_timelines": {"solar": 27.8, "battery": 31.3},
        })
        config = json.loads(self.path("config.model_parameters").read_text())
        config["investment_parameters"]["target_payback_years"]["bio_and_waste"] = 20.0
        self.write_json("config.model_parameters", config)
        self.path("planning.success_rates").write_text("technology,region,success_rate\nsolar,London,0.6\nsolar,Scotland,0.4\nbattery,Wales,0.5\n", encoding="utf-8")
        self.rows = [
            {"project_id": "granted", "site_name": "Granted solar", "technology": "solar", "technology_source": "Solar Photovoltaics", "capacity_mw": 100, "development_status": "Planning Permission Granted", "region": "London", "operational": "01/01/2039"},
            {"project_id": "submitted", "site_name": "Submitted solar", "technology": "solar", "technology_source": "Solar Photovoltaics", "capacity_mw": 100, "development_status": "Application Submitted", "region": "Wales"},
            {"project_id": "zombie", "site_name": "Old solar", "technology": "solar", "technology_source": "Solar Photovoltaics", "capacity_mw": 100, "development_status": "Planning Permission Granted", "region": "London"},
            {"project_id": "canonical-only", "site_name": "User project", "technology": "solar", "capacity_mw": 20, "development_status": "Under Construction", "region": "London"},
            {"project_id": "battery", "site_name": "Battery site", "technology": "battery", "technology_source": "Battery", "capacity_mw": 100, "development_status": "Application Submitted", "region": "Wales"},
            {"project_id": "superseded", "site_name": "Earlier application", "technology": "solar", "technology_source": "Solar Photovoltaics", "capacity_mw": 40, "development_status": "Planning Permission Granted", "region": "London"},
            {"project_id": "replacement", "site_name": "Replacement application", "technology": "solar", "technology_source": "Solar Photovoltaics", "capacity_mw": 30, "development_status": "Planning Permission Granted", "region": "London"},
            {"project_id": "raw-nuclear", "site_name": "Raw nuclear entry", "technology": "Nuclear", "technology_source": "Nuclear", "capacity_mw": 3200, "development_status": "Planning Permission Granted", "region": "London"},
        ]
        pd.DataFrame(self.rows).to_csv(self.path("projects.repd"), index=False)
        raw = []
        for row in self.rows:
            if row["project_id"] == "canonical-only":
                continue
            raw.append({"Ref ID": row["project_id"], "Site Name": row["site_name"], "Technology Type": row["technology_source"], "Installed Capacity (MWelec)": row["capacity_mw"], "Development Status (short)": row["development_status"], "Region": row["region"],
                        "Planning Permission Granted": "01/01/2010" if row["project_id"] == "zombie" else "",
                        "Are they re-applying (New REPD Ref)": "replacement" if row["project_id"] == "superseded" else ""})
        pd.DataFrame(raw).to_csv(self.path("source.repd_raw"), index=False)
        (self.pack / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        self.parameters = {
            "planning.success_mode": "expected_capacity", "planning.include_uncertain_projects": True,
            "planning.zombie_filter_enabled": True, "planning.minimum_project_size_mw": 1.0,
            "planning.timeline_statistic": "median", "planning.defer_spread_years": 3,
            "planning.repd_battery_assignment": "all_1c",
        }

    def path(self, role):
        return self.pack / self.manifest["bindings"][role]["uri"]

    def write_json(self, role, value):
        self.path(role).write_text(json.dumps(value), encoding="utf-8")

    def state(self):
        return native_initial_state(self.pack, 2025, scientific_parameters=self.parameters, doctoral_alignment=True)

    def test_default_and_explicit_false_preserve_existing_profile(self):
        implicit = native_initial_state(self.pack, 2025, scientific_parameters=self.parameters)
        explicit = native_initial_state(self.pack, 2025, scientific_parameters=self.parameters, doctoral_alignment=False)
        self.assertEqual(implicit.to_dict(), explicit.to_dict())
        self.assertNotIn("doctoral_alignment_profile", implicit.extensions)
        self.assertEqual(next(p for p in implicit.planning_projects if p.project_id == "granted").capacity_mw, 60.0)

    def test_actual_entry_restores_probabilities_and_raw_milestone_filter(self):
        state = self.state()
        projects = {project.project_id: project for project in state.planning_projects}
        self.assertEqual(projects["granted"].capacity_mw, 100.0)
        self.assertEqual(projects["submitted"].capacity_mw, 50.0)
        self.assertNotIn("zombie", projects)
        self.assertLess(projects["granted"].expected_completion_year, 2039)

    def test_existing_ids_battery_economics_and_weather_survive_alignment(self):
        projects = {project.project_id: project for project in self.state().planning_projects}
        battery = projects["battery:1c_battery"]
        self.assertEqual((battery.original_capacity_mw, battery.capacity_mw), (100.0, 50.0))
        self.assertEqual(battery.extensions["energy_capacity_mwh"], 50.0)
        self.assertEqual(battery.extensions["expected_economics_capacity_mw"], 50.0)
        self.assertEqual(battery.extensions["source_record_id"], "battery")
        self.assertEqual(projects["granted"].extensions["weather_source_asset_id"], "solar_London")
        self.assertIsNone(projects["granted"].assigned_asset_id)

    def test_canonical_only_rows_are_kept_and_unsourced_reapplication_filter_is_absent(self):
        state = self.state()
        projects = {project.project_id: project for project in state.planning_projects}
        self.assertIn("superseded", projects)
        self.assertIn("canonical-only", projects)
        self.assertEqual(projects["canonical-only"].extensions["doctoral_row_provenance"], "canonical_only")
        self.assertEqual(state.extensions["doctoral_alignment_profile"], "value.doctoral-national/v1")
        diagnostics = {row["project_id"]: row for row in state.extensions["planning_preprocessing"]["doctoral_project_rows"]}
        self.assertEqual(diagnostics["zombie"]["reason"], "excluded_status_stagnant")
        self.assertEqual(diagnostics["granted"]["provenance"], "canonical_with_raw_milestones")

    def test_biomass_payback_is_twenty_but_economic_life_is_twenty_five(self):
        asset = next(asset for asset in self.state().assets if asset.asset_id == "bio_and_waste")
        self.assertEqual(asset.extensions["target_payback_years"], 20.0)
        self.assertEqual(asset.extensions["economic_lifetime_years"], 25.0)

    def test_nuclear_policy_and_weather_bytes_are_preserved(self):
        protected = [ROOT / "gridform_core/nuclear_policy.py", ROOT / "gridform_core/doctoral_weather.py", ROOT / "gridform_core/doctoral_weather_mapping.py", self.pack / "weather.wind.nc", self.pack / "weather.solar.nc"]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
        state = self.state()
        self.assertNotIn("raw-nuclear", {p.project_id for p in state.planning_projects})
        self.assertEqual(sum(asset.capacity_mw for asset in state.assets if asset.technology == "Nuclear"), 5958.0)
        self.assertTrue(any(p.technology == "Nuclear" and p.expected_completion_year == 2031 for p in state.planning_projects))
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected})

    def test_nuclear_parameter_provenance_is_explicit_without_changing_policy(self):
        state = self.state()
        for asset in state.assets:
            if asset.technology == "Nuclear":
                self.assertEqual(asset.extensions["doctoral_parameter_source_id"], "Nuclear")
                self.assertEqual(asset.extensions["doctoral_dispatch_asset_id"], "Nuclear")
        for project in state.planning_projects:
            if project.technology == "Nuclear":
                self.assertEqual(project.extensions["doctoral_parameter_source_id"], "Nuclear")
                self.assertEqual(project.extensions["doctoral_dispatch_asset_id"], "Nuclear")


class DoctoralChronologyEntryTests(unittest.TestCase):
    def setUp(self):
        fixture = weather_fixtures.DoctoralWeatherTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.pack, self.manifest, self.fleet = fixture.pack, fixture.manifest, fixture.fleet
        for name in self.fleet["generators"]:
            self.fleet["generators"][name].update({"gen_cost": .1, "unit_time_cost": 4.0,
                "curtail_cost": 2.0, "capital_cost": 10.0, "carbon_emission": 0.0, "real_gen_energy": 0.0})
        self.fleet["generators"]["solar_London"]["gen_cost"] = 90.0
        self.fleet["generators"]["CCGT"] = gas_parameters()
        self.fleet["batteries"]["pumpedhydro_battery"] = pumped_parameters()
        self.fleet["connections"]["Interconnect_France"] = {"capital_cost": 100.0, "carbon_emission": 0.0, "carbon_intensity": 53.0}
        self.path("fleet.generators").write_text(json.dumps(self.fleet), encoding="utf-8")
        for country in ("france", "belgium", "netherlands", "norway", "ireland"):
            flow = [10.0, -10.0] * 4 if country == "france" else [0.0] * 8
            self.path(f"market.{country}.profile").write_text("MW\n" + "\n".join(map(str, flow)), encoding="utf-8")
            self.path(f"market.{country}.price").write_text("\n".join(map(str, [-10.0, -20.0] * 4)), encoding="utf-8")
        self.assets = (
            AssetStateV2("solar_Nottingham", "solar", 20.0),
            AssetStateV2("CCGT", "CCGT", 100.0),
            AssetStateV2("pumpedhydro_battery", "pumped_hydro", 10.0, 50.0),
        )

    def path(self, role):
        return self.pack / self.manifest["bindings"][role]["uri"]

    def state(self, *, aligned=True, assets=None):
        return OperatingState(2025, self.assets if assets is None else assets, (),
            extensions={"doctoral_alignment_profile": "value.doctoral-national/v1"} if aligned else {})

    def chronology(self, *, aligned=True, assets=None):
        return build_chronology(self.pack, self.manifest, self.state(aligned=aligned, assets=assets), periods=8, period_hours=.5,
                                data_policy=run_policy(self.manifest))

    def test_default_path_retains_existing_cost_soc_and_price_semantics(self):
        chronology = self.chronology(aligned=False)
        rows = {row.asset_id: row for row in chronology.resources}
        self.assertEqual(rows["solar_Nottingham"].marginal_cost_gbp_per_mwh, 0.0)
        self.assertEqual(rows["CCGT"].marginal_cost_gbp_per_mwh, 14.0)
        self.assertEqual(chronology.storage[0].initial_soc_mwh, 25.0)
        self.assertEqual(rows["import:france"].marginal_cost_profile_gbp_per_mwh, (0.0,) * 8)
        self.assertEqual(chronology.extensions["boundary_export_price_gbp_per_mwh_by_asset"]["export:france"], (0.0,) * 8)
        self.assertNotIn("doctoral_parameter_source_id", rows["solar_Nottingham"].extensions)

    def test_doctoral_path_preserves_cost_components_empty_batches_and_signed_prices(self):
        chronology = self.chronology()
        rows = {row.asset_id: row for row in chronology.resources}
        self.assertEqual(rows["solar_Nottingham"].marginal_cost_gbp_per_mwh, 4.1)
        self.assertEqual(rows["CCGT"].marginal_cost_gbp_per_mwh, 22.0)
        self.assertEqual(chronology.storage[0].initial_soc_mwh, 0.0)
        self.assertEqual(chronology.extensions["doctoral_alignment_profile"], "value.doctoral-national/v1")
        self.assertEqual(rows["import:france"].marginal_cost_profile_gbp_per_mwh, (-10.0, -20.0) * 4)
        self.assertEqual(chronology.extensions["boundary_export_price_gbp_per_mwh_by_asset"]["export:france"], (-10.0, -20.0) * 4)
        model = PSMInput("small-real-adapter", 2025, "fixture", self.state(), .5, {}, chronology=chronology)
        generators, batteries, connections = from_doctoral_psm_input(model, self.fleet, self.fleet["batteries"])
        self.assertEqual([g.gen_cost for g in generators], [4.1, 22.0])
        self.assertEqual(batteries[0].stored_energy, {})
        self.assertEqual(connections[0].doctoral_transfer_constraint_mw_by_period, (10.0, -10.0) * 4)

    def test_source_agent_parameter_owner_and_weather_identity_are_independent(self):
        asset = AssetStateV2("commissioned:solar-1", "solar", 20.0, extensions={
            "source_agent_id": "solar_Nottingham", "weather_source_asset_id": "solar_London"})
        chronology = self.chronology(assets=(asset,))
        row = next(r for r in chronology.resources if r.asset_id == asset.asset_id)
        self.assertEqual(row.extensions["doctoral_parameter_source_id"], "solar_Nottingham")
        self.assertEqual(row.extensions["weather_profile"]["source_asset_id"], "solar_London")
        self.assertEqual(row.marginal_cost_gbp_per_mwh, 4.1)
        model = PSMInput("parameter-not-weather", 2025, "fixture", self.state(assets=(asset,)), .5, {}, chronology=chronology)
        self.assertEqual(from_doctoral_psm_input(model, self.fleet, {})[0][0].gen_cost, 4.1)

    def test_weather_mapping_alone_does_not_supply_parameter_owner(self):
        asset = AssetStateV2("commissioned:external-solar", "solar", 20.0,
            extensions={"weather_source_asset_id": "solar_London"})
        with self.assertRaisesRegex(ValueError, "doctoral.*parameter.*source"):
            self.chronology(assets=(asset,))

    def test_source_agent_wrong_technology_is_not_a_valid_parameter_binding(self):
        asset = AssetStateV2("commissioned:solar-1", "solar", 20.0, extensions={
            "source_agent_id": "onshore_Nottingham", "weather_source_asset_id": "solar_London"})
        with self.assertRaisesRegex(ValueError, "parameter.*technology"):
            self.chronology(assets=(asset,))

    def test_doctoral_profile_does_not_silently_use_old_csv_weather(self):
        self.manifest["id"] = "ordinary-pack"
        self.manifest["bindings"].pop("weather.wind")
        self.manifest["bindings"].pop("weather.solar")
        with self.assertRaisesRegex(ValueError, "doctoral.*weather|Doctoral.*weather"):
            self.chronology()


if __name__ == "__main__":
    unittest.main()
