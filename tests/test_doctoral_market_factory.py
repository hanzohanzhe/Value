"""Typed input conversion at the static doctoral constructor boundary."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest

from gridform_core.builtin.scheme_c_1000twh import doctoral_market_kernel as k
from gridform_core.builtin.scheme_c_1000twh.doctoral_market_factory import from_doctoral_psm_input
from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
from gridform_core.v2.contracts import AssetStateV2, ChronologicalPSMData, DispatchResource, OperatingState, PSMInput, StorageDispatchResource


def gas_parameters():
    return {"name": "CCGT", "gen_cost": 1.0, "curtail_cost": 2.0, "carbon_emission": 3.0,
            "capacity_limit": 200.0, "alter_limit": 100.0, "startup_cost": 4.0,
            "carbon_intensity": 5.0, "capital_cost": 6000.0, "carbon_price": 6.0,
            "fuel_cost": 7.0, "real_gen_energy": 0.0, "unit_time_cost": 8.0}


def pumped_parameters():
    return {"name": "pumpedhydro_battery", "pool_limit": 8000.0, "per_pool_limit": 2000.0,
            "storage_fee": 0.0, "per_storage_fee": 1.1008, "n_1": 0.87, "n_2": 0.87,
            "carbon_emission": 40.0, "capital_cost": 720000000.0, "battery_type": "pumped_hydro"}


def model_input():
    assets = (AssetStateV2("CCGT", "CCGT", 100.0), AssetStateV2("pumpedhydro_battery", "pumped_hydro", 10.0, 50.0))
    chronology = ChronologicalPSMData(("2025:0", "2025:1"), (10.0, 12.0),
        (DispatchResource("CCGT", "CCGT", "thermal", 100.0, 22.0, (1.0, 1.0)),),
        (StorageDispatchResource("pumpedhydro_battery", "pumped_hydro", 10.0, 10.0, 50.0, .87, .87, 0.0),), 8000.0)
    return PSMInput("factory-test", 2025, "fixture", OperatingState(2025, assets, ()), .5, {}, chronology=chronology)


class DoctoralFactoryTests(unittest.TestCase):
    def objects(self, model=None, fleet=None, batteries=None):
        return from_doctoral_psm_input(model or model_input(), fleet or {"generators": {"CCGT": gas_parameters()}, "connections": {}}, batteries or {"pumpedhydro_battery": pumped_parameters()})

    def test_typed_energy_converts_to_source_half_hour_stock(self):
        battery = self.objects()[1][0]
        self.assertEqual(battery.pool_limit, 100.0)

    def test_typed_charging_power_overrides_raw_table_limit(self):
        battery = self.objects()[1][0]
        self.assertEqual(battery.per_pool_limit, 10.0)

    def test_typed_current_fleet_capacity_overrides_initial_source_snapshot(self):
        generator = self.objects()[0][0]
        self.assertEqual(generator.capacity_limit, 100.0)

    def test_native_constant_availability_is_expanded_without_inventing_values(self):
        original = model_input()
        resource = replace(original.chronology.resources[0], availability=(.75,))
        modified = replace(original, chronology=replace(original.chronology, resources=(resource,)))
        generator = self.objects(modified)[0][0]
        self.assertEqual(generator.doctoral_capacity_mw_by_period, (75.0, 75.0))
        self.assertEqual(generator.capacity_limit, 75.0)

    def test_incomplete_nonconstant_profiles_are_rejected(self):
        original = model_input()
        resource = replace(original.chronology.resources[0], availability=(1.0, .5, .25))
        modified = replace(original, chronology=replace(original.chronology, resources=(resource,)))
        with self.assertRaisesRegex(ValueError, "CCGT.availability"):
            self.objects(modified)

    def test_startup_curtail_unit_time_and_carbon_fields_are_not_lost(self):
        generator = self.objects()[0][0]
        self.assertIs(type(generator), k.GasGenerator)
        self.assertEqual(generator.gen_cost, 22.0)
        self.assertEqual((generator.curtail_cost, generator.startup_cost, generator.alter_limit), (2.0, 4.0, 100.0))
        self.assertEqual((generator.carbon_intensity, generator.capital_cost, generator.carbon_emission), (5.0, 6000.0, 3.0))

    def test_nonzero_soc_or_mismatched_efficiency_is_not_silently_discarded(self):
        original = model_input()
        for overrides, message in (({"initial_soc_mwh": 10.0}, "opening SOC"), ({"charge_efficiency": .8}, "efficiency mismatch"), ({"discharge_power_mw": 20.0}, "equal charging/discharging")):
            with self.subTest(overrides=overrides):
                modified = replace(original, chronology=replace(original.chronology, storage=(replace(original.chronology.storage[0], **overrides),)))
                with self.assertRaisesRegex(ValueError, message):
                    self.objects(modified)

    def test_missing_critical_constructor_field_names_the_asset_and_field(self):
        row = gas_parameters()
        del row["unit_time_cost"]
        with self.assertRaisesRegex(ValueError, "generators/CCGT missing constructor fields: unit_time_cost"):
            self.objects(fleet={"generators": {"CCGT": row}})

    def test_existing_synthetic_pack_gaps_fail_closed(self):
        root = Path(__file__).resolve().parents[1]
        fleet = json.loads((root / "data-packs/value-synthetic-contract-pack-v1/files/fleet__generators/fleet.json").read_text())
        with self.assertRaisesRegex(ValueError, "generators/CCGT missing constructor fields:.*curtail_cost.*unit_time_cost"):
            self.objects(fleet=fleet)

    def test_actual_value101_full_source_rows_construct_without_zero_defaults(self):
        root = Path(__file__).resolve().parents[1]
        fleet = json.loads((root / "data-packs/value-101-baseline-v1/files/fleet__generators/fleet.json").read_text())
        original = model_input()
        asset = AssetStateV2("1c_battery", "1c_battery", 10.0, 10.0)
        battery = StorageDispatchResource("1c_battery", "1c_battery", 10.0, 10.0, 10.0, .9, .9, 0.0)
        modified = replace(original, operating_state=replace(original.operating_state, assets=(original.operating_state.assets[0], asset)), chronology=replace(original.chronology, storage=(battery,)))
        generators, batteries, _ = from_doctoral_psm_input(modified, fleet, fleet["batteries"])
        self.assertEqual(generators[0].gen_cost, 66.5)
        self.assertEqual(generators[0].alter_limit, 50.0)
        self.assertEqual((batteries[0].pool_limit, batteries[0].per_pool_limit), (20.0, 10.0))

    def test_nuclear_template_cannot_restore_superseded_source_capacity(self):
        original = model_input()
        asset = AssetStateV2("Nuclear", "Nuclear", 50.0)
        resource = DispatchResource(asset.asset_id, asset.technology, "thermal", 50.0, 0.0, (1.0, 1.0))
        modified = replace(original, operating_state=replace(original.operating_state, assets=(asset,)), chronology=replace(original.chronology, resources=(resource,), storage=()))
        row = {"name": "Nuclear", "gen_cost": 0.0, "curtail_cost": 91430.0, "carbon_emission": 0.0, "capacity_limit": 5883.0, "alter_limit": 500.0, "startup_cost": 500.0, "capital_cost": 470640000.0, "unit_time_cost": 0.0}
        generator = self.objects(modified, fleet={"generators": {"Nuclear": row}})[0][0]
        self.assertEqual((generator.name, generator.capacity_limit, generator.real_gen_energy), ("Nuclear", 50.0, 50.0))
        self.assertEqual(generator.startup_cost, 500.0)

    def test_nuclear_station_rejects_unallocated_national_ramp_and_capital(self):
        original = model_input()
        asset = AssetStateV2("policy-station", "Nuclear", 50.0, extensions={"doctoral_parameter_source_id": "Nuclear"})
        resource = DispatchResource(asset.asset_id, asset.technology, "thermal", 50.0, 0.0, (1.0,))
        modified = replace(original, operating_state=replace(original.operating_state, assets=(asset,)), chronology=replace(original.chronology, resources=(resource,), storage=()))
        row = {"gen_cost": 0.0, "curtail_cost": 91430.0, "carbon_emission": 0.0, "capacity_limit": 5883.0, "alter_limit": 500.0, "startup_cost": 500.0, "capital_cost": 470640000.0, "unit_time_cost": 0.0}
        with self.assertRaisesRegex(ValueError, "station-specific.*ramp.*capital"):
            self.objects(modified, fleet={"generators": {"Nuclear": row}})

    def test_validated_resource_parameter_binding_is_used_but_conflicts_fail(self):
        original = model_input()
        asset = replace(original.operating_state.assets[0], asset_id="commissioned:gas-1")
        resource = replace(original.chronology.resources[0], asset_id=asset.asset_id, extensions={"doctoral_parameter_source_id": "CCGT"})
        modified = replace(original, operating_state=replace(original.operating_state, assets=(asset,)), chronology=replace(original.chronology, resources=(resource,), storage=()))
        self.assertEqual(self.objects(modified)[0][0].doctoral_parameter_source_id, "CCGT")
        conflicting = replace(asset, extensions={"doctoral_parameter_source_id": "OCGT"})
        modified = replace(modified, operating_state=replace(modified.operating_state, assets=(conflicting,)))
        with self.assertRaisesRegex(ValueError, "Conflicting doctoral parameter source"):
            self.objects(modified)

    def test_vre_load_controls_are_disabled_and_profiles_come_from_typed_input(self):
        original = model_input()
        asset = AssetStateV2("wind-project", "onshore", 40.0, extensions={"doctoral_parameter_source_id": "onshore_Nottingham"})
        resource = DispatchResource(asset.asset_id, asset.technology, "vre", 40.0, 0.1, (.5, .25))
        modified = replace(original, operating_state=replace(original.operating_state, assets=(asset,)), chronology=replace(original.chronology, resources=(resource,), storage=()))
        row = {"gen_cost": .1, "curtail_cost": 2.0, "carbon_emission": 3.0, "capital_cost": 10.0, "real_gen_energy": 0.0, "unit_time_cost": 4.0, "electrolyzer_cost": 15000.0, "energy_efficiency": .65, "electrolyzer_limit": 5.0, "rampup_rate": .125}
        generator = self.objects(modified, fleet={"generators": {"onshore_Nottingham": row}})[0][0]
        self.assertEqual(generator.doctoral_capacity_mw_by_period, (20.0, 10.0))
        self.assertEqual(generator.capacity_multiplier, 2.0)
        self.assertEqual((generator.electrolyzer_cost, generator.energy_efficiency, generator.electrolyzer_limit, generator.rampup_rate, generator.real_energy), (0.0, 0.0, 0.0, 0.0, 0))
        self.assertEqual(generator.gen_cost, 4.1)

    def test_hydro_and_biomass_budget_and_replenishment_survive_construction(self):
        original = model_input()
        bio = dict(gas_parameters(), name="bio_and_waste", energy_limit=16000000.0, add_energy=913.0)
        water = {"gen_cost": 0.0, "curtail_cost": 0.0, "carbon_emission": 0.0, "capital_cost": 200000000000.0, "unit_time_cost": 0.0, "alter_limit": 2000.0, "energy_limit": 2000.0, "add_energy": 2000.0, "real_gen_energy": 1.0}
        assets = (AssetStateV2("bio_and_waste", "bio_and_waste", 30.0), AssetStateV2("Hydro_natural_flow", "Hydro_natural_flow", 20.0))
        resources = tuple(DispatchResource(a.asset_id, a.technology, "thermal", a.capacity_mw, 0.0, (1.0, 1.0)) for a in assets)
        modified = replace(original, operating_state=replace(original.operating_state, assets=assets), chronology=replace(original.chronology, resources=resources, storage=()))
        generators = self.objects(modified, fleet={"generators": {"bio_and_waste": bio, "Hydro_natural_flow": water}})[0]
        self.assertEqual([(type(g).__name__, g.energy_limit, g.add_energy, g.have_gen_energy) for g in generators], [("BiomassGenerator", 16000000.0, 913.0, 0.0), ("WaterGenerator", 2000.0, 2000.0, 1.0)])

    def test_signed_connection_profiles_preserve_power_and_price_per_period(self):
        original = model_input()
        resource = DispatchResource("import:france", "interconnector_import", "import", 10.0, 20.0, (.5, 0.0), (20.0, 25.0), extensions={"country": "france"})
        modified = replace(original, chronology=replace(original.chronology, resources=original.chronology.resources + (resource,), extensions={"boundary_export_envelope_mwh_by_asset": {"export:france": (0.0, 3.0)}, "boundary_export_price_gbp_per_mwh_by_asset": {"export:france": (70.0, 80.0)}}))
        fleet = {"generators": {"CCGT": gas_parameters()}, "connections": {"Interconnect_France": {"capital_cost": 100.0, "carbon_emission": 0.0, "carbon_intensity": 53.0}}}
        connection = self.objects(modified, fleet=fleet)[2][0]
        self.assertEqual(connection.doctoral_transfer_constraint_mw_by_period, (5.0, -6.0))
        self.assertEqual(connection.doctoral_external_price_gbp_per_mwh_by_period, (20.0, 80.0))
        self.assertEqual((connection.transfer_constraint, connection.external_price), (5.0, 20.0))

    def test_two_real_engine_periods_accept_factory_objects_without_input_mutation(self):
        original = model_input()
        fleet = {"generators": {"CCGT": gas_parameters()}, "connections": {}}
        batteries = {"pumpedhydro_battery": pumped_parameters()}
        frozen = copy.deepcopy((original.to_dict(), fleet, batteries))
        generators, storage, connections = self.objects(original, fleet, batteries)
        engine = DoctoralPeriodEngine(generators, storage, year=2025, connections=connections)
        for demand in (20.0, 24.0):
            plan = engine.plan_period(demand)
            outcome = engine.realise_period(plan, demand)
            self.assertAlmostEqual(sum(outcome.generation_mwh_by_asset.values()), demand * .5)
            self.assertAlmostEqual(outcome.energy_balance_residual_mwh, 0.0)
            engine.commit(outcome)
        self.assertEqual(engine.state.next_absolute_period, 2)
        self.assertEqual((original.to_dict(), fleet, batteries), frozen)


if __name__ == "__main__":
    unittest.main()
