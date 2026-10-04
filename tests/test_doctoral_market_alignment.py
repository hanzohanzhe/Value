"""Named source defect regressions, distinct from unchanged-source parity."""

import unittest
from collections import defaultdict

from gridform_core.builtin.scheme_c_1000twh import doctoral_market_kernel as kernel
from tests.doctoral_reference_harness import load_reference_symbols


def vre(name, capacity):
    generator = kernel.ExpensiverenewableGenerator(name, 2, 3, 0, 0, 0, 0, 0, 0.6, 0, 0)
    generator.capacity_limit = capacity
    return generator


def gas(capacity=100):
    return kernel.GasGenerator("gas", 50, 3, 0, capacity, capacity, 0, 0, 0, 0, 0, 0, 0)


def ahead(generators, batteries, demand, period=0):
    return kernel.ahead_market_bidding(generators, batteries, demand, period, [],
                                      defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float), 1)


def balance(generators, batteries, planned, actual, forecast, connections=(), period=0):
    return kernel.balancing_market_bidding(generators, period, actual, forecast, planned[0], planned[6],
        defaultdict(float), defaultdict(float), defaultdict(float), planned[10], defaultdict(float),
        list(connections), planned[12], planned[13], kernel.Electrolyzer("off", 0, 0, .6, 0, 0, 0, 0),
        planned[15], batteries, 1)


def thermal_asset(namespace, kind, name, *, previous=20, current=20, ramp=10, curtail_cost=2):
    params = dict(name=name, gen_cost=1, curtail_cost=curtail_cost, carbon_emission=0,
                  capacity_limit=100, alter_limit=ramp, capital_cost=0,
                  real_gen_energy=current, unit_time_cost=0)
    if kind in {"WaterGenerator", "BiomassGenerator"}:
        params.update(energy_limit=1000, add_energy=0)
    if kind in {"GasGenerator", "BiomassGenerator"}:
        params.update(startup_cost=0, carbon_intensity=0, carbon_price=0, fuel_cost=0)
    asset = namespace[kind](**params)
    if hasattr(asset, "have_gen_energy"):
        asset.have_gen_energy = 100  # 80 prior quantity + 20 this period.
    return asset, [asset, asset.gen_cost, current, curtail_cost], (asset, curtail_cost, previous)


def thermal_curtail(namespace, specs, need, *, export_capacity=0, extra_previous=()):
    prepared = [thermal_asset(namespace, **spec) for spec in specs]
    assets = [row[0] for row in prepared]
    accepted = [row[1] for row in prepared]
    previous = list(extra_previous) + [row[2] for row in prepared]
    generation = [[asset, asset.real_gen_energy] for asset in assets]
    connections = []
    if export_capacity:
        connection = namespace["Connection"]("export", 0, 0, 0)
        connection.transfer_constraint = -export_capacity
        connection.external_price = 80
        connections.append(connection)
    outcome = namespace["curtailment_market_bidding"](
        0, 40 - need, 40, accepted, previous, 0, generation, connections,
        namespace["Electrolyzer"]("off", 0, 0, .6, 0, 0, 0, 0), [])
    return {"generation": {asset.name: amount for asset, amount in outcome[4]},
            "memory": {asset.name: dict(vars(asset)) for asset in assets},
            "fees": outcome[0], "exported": sum(c.sold_energy for c in connections),
            "accepted": {row[0].name: row[2] for row in accepted}}


class SourceDefectRegressionTests(unittest.TestCase):
    def test_biomass_curtailment_releases_only_current_natural_energy_budget(self):
        spec = [dict(kind="BiomassGenerator", name="bio")]
        for exported in (0, 2):
            with self.subTest(exported=exported):
                raw = thermal_curtail(load_reference_symbols(), spec, 5 + exported, export_capacity=exported)
                actual = thermal_curtail(vars(kernel), spec, 5 + exported, export_capacity=exported)
                self.assertEqual(raw["generation"]["bio"], 15)
                self.assertEqual(raw["memory"]["bio"]["have_gen_energy"], 100,
                                 "R0 executes (WaterGenerator or BiomassGenerator) as Water only")
                self.assertEqual(actual["generation"]["bio"], 15)
                self.assertEqual(actual["memory"]["bio"]["have_gen_energy"], 95)
                self.assertEqual(actual["memory"]["bio"]["energy_limit"], 1000)

    def test_water_budget_retains_prior_period_generation(self):
        spec = [dict(kind="WaterGenerator", name="water")]
        for exported in (0, 2):
            with self.subTest(exported=exported):
                raw = thermal_curtail(load_reference_symbols(), spec, 5 + exported, export_capacity=exported)
                actual = thermal_curtail(vars(kernel), spec, 5 + exported, export_capacity=exported)
                self.assertEqual(actual, raw)
                self.assertEqual(actual["memory"]["water"]["have_gen_energy"], 95)

    def test_curtailment_uses_previous_output_of_the_same_object(self):
        spec = [dict(kind="GasGenerator", name="selected", curtail_cost=2)]
        for exported in (0, 2):
            with self.subTest(exported=exported):
                observations = []
                for namespace in (load_reference_symbols(), vars(kernel)):
                    unused, _, old = thermal_asset(namespace, "GasGenerator", "unused", previous=100,
                                                   current=0, ramp=10, curtail_cost=1)
                    observations.append(thermal_curtail(namespace, spec, 5 + exported,
                                        export_capacity=exported, extra_previous=(old,)))
                self.assertEqual(observations[0]["generation"]["selected"], 90,
                                 "R0 wrong positional history produces negative curtailment")
                self.assertEqual(observations[1]["generation"]["selected"], 15)
                self.assertEqual(sum(observations[1]["fees"]), 10)

    def test_satisfied_thermal_curtailment_is_not_repeated_for_later_assets(self):
        specs = [dict(kind="GasGenerator", name="first"), dict(kind="GasGenerator", name="second")]
        for exported in (0, 2):
            with self.subTest(exported=exported):
                raw = thermal_curtail(load_reference_symbols(), specs, 5 + exported, export_capacity=exported)
                actual = thermal_curtail(vars(kernel), specs, 5 + exported, export_capacity=exported)
                self.assertEqual(raw["generation"], {"first": 10, "second": 20},
                                 "R0 never clears the satisfied request before the outer loop continues")
                self.assertEqual(actual["generation"], {"first": 15, "second": 20})
                self.assertEqual(actual["accepted"], actual["generation"])
                self.assertEqual(sum(actual["fees"]), 10)
                self.assertEqual(actual["exported"], exported)

    def test_partial_thermal_curtailment_updates_both_natural_budgets_once(self):
        specs = [dict(kind="BiomassGenerator", name="bio", ramp=2, curtail_cost=1),
                 dict(kind="WaterGenerator", name="water", ramp=10, curtail_cost=2)]
        for exported in (0, 2):
            with self.subTest(exported=exported):
                raw = thermal_curtail(load_reference_symbols(), specs, 6 + exported, export_capacity=exported)
                actual = thermal_curtail(vars(kernel), specs, 6 + exported, export_capacity=exported)
                self.assertEqual(raw["generation"], {"bio": 18, "water": 12})
                self.assertEqual(actual["generation"], {"bio": 18, "water": 16})
                self.assertEqual(actual["memory"]["bio"]["have_gen_energy"], 98)
                self.assertEqual(actual["memory"]["water"]["have_gen_energy"], 96)
                self.assertEqual(sum(actual["fees"]), 10)

    def test_missing_thermal_previous_state_is_rejected_before_mutation(self):
        generator, bid, _ = thermal_asset(vars(kernel), "GasGenerator", "gas")
        generation = [[generator, 20]]
        with self.assertRaisesRegex(ValueError, "previous.*gas"):
            kernel.store_service_three([bid], [], 0, 5, [], 0, generation, [],
                kernel.Electrolyzer("off", 0, 0, .6, 0, 0, 0, 0))
        self.assertEqual(generator.real_gen_energy, 20)
        self.assertEqual(bid[2], 20)
        self.assertEqual(generation[0][1], 20)

    def test_thermal_scan_keeps_source_order_when_vre_cost_is_interleaved(self):
        def run(namespace):
            first, first_bid, first_old = thermal_asset(namespace, "GasGenerator", "first", curtail_cost=1)
            second, second_bid, second_old = thermal_asset(namespace, "GasGenerator", "second", curtail_cost=3)
            wind = namespace["ExpensiverenewableGenerator"]("wind", 1, 2, 0, 0, 0, 0, 0, .6, 0, 0)
            wind.real_gen_energy = wind.capacity_limit = 20
            accepted = [first_bid, [wind, 1, 20, 2], second_bid]
            generation = [[first, 20], [wind, 20], [second, 20]]
            result = namespace["store_service_three"](accepted, [], 0, 15,
                [first_old, (wind, 2, 20), second_old], 0, generation, [],
                namespace["Electrolyzer"]("off", 0, 0, .6, 0, 0, 0, 0))
            return {obj.name: amount for obj, amount in result[2]}, result[0]

        raw_generation, raw_fees = run(load_reference_symbols())
        actual_generation, actual_fees = run(vars(kernel))
        self.assertEqual(raw_generation, {"first": 10, "wind": 15, "second": 15},
                         "R0 thermal scan order is preserved, but its satisfied request curtails wind again")
        self.assertEqual(actual_generation, {"first": 10, "wind": 20, "second": 15})
        self.assertEqual(actual_fees[:2], raw_fees[:2])
        self.assertEqual(sum(actual_fees), 25)

    def test_nuclear_ramp_surplus_is_retained_without_double_generation(self):
        nuclear = kernel.NuclearGenerator("nuclear", 5, 1, 0, 100, 10, 0, 0, 0)
        planned = ahead([nuclear], [], 20)
        self.assertEqual(planned[6], 70)
        self.assertEqual([(g.name, q) for g, q in planned[15]], [("nuclear", 70)])
        result = balance([nuclear], [], planned, 30, 20)
        self.assertEqual(sum(q for g, q in result[8] if g is nuclear), 90)

    def test_storage_discharge_cannot_exceed_period_power_limit(self):
        store = kernel.Battery("store", 200, 10, 1, 0, 1, 1, 0)
        store.stored_energy = {0: 100}
        planned = ahead([gas()], [store], 50, period=2)
        self.assertEqual(sum(q for g, q in planned[10] if g is store), 10)
        self.assertEqual(sum(q for g, q in planned[10] if g.name == "gas"), 40)

    def test_storage_charge_limit_uses_input_not_efficiency_reduced_stock(self):
        wind = vre("wind", 100)
        store = kernel.Battery("store", 200, 10, 1, 0, .8, 1, 0)
        planned = ahead([wind], [store], 50)
        result = kernel.curtailment_market_bidding(0, 45, 50, planned[0], planned[5],
            planned[6], planned[10], [], kernel.Electrolyzer("off", 0, 0, .6, 0, 0, 0, 0), [store])
        self.assertEqual(result[1], 10)
        self.assertEqual(store.stored_energy[0], 8)

    def test_exact_forecast_acceptance_does_not_erase_later_available_vre(self):
        first, second = vre("first", 100), vre("second", 80)
        result = ahead([first, second], [], 100)
        self.assertEqual(result[6], 80)
        self.assertEqual([(g.name, q) for g, q in result[15]], [("second", 80)])

    def test_unaccepted_vre_retains_its_own_identity(self):
        first, second = vre("first", 100), vre("second", 80)
        result = ahead([first, second], [], 50)
        self.assertEqual([(g.name, q) for g, q in result[15]], [("first", 50), ("second", 80)])

    def test_zero_forecast_vre_can_charge_before_export(self):
        wind = vre("wind", 50)
        store = kernel.Battery("store", 200, 30, 1, 0, 1, 1, 0)
        exporter = kernel.Connection("export", 0, 0, 0)
        exporter.transfer_constraint, exporter.external_price = -100, 80
        planned = ahead([wind], [store], 0)
        result = balance([wind], [store], planned, 0, 0, [exporter])
        self.assertEqual(result[3] * .5, 15)
        self.assertEqual(exporter.sold_energy * .5, 10)
        self.assertEqual(result[10], 0)

    def test_partial_storage_discharge_reports_delivered_not_withdrawn_power(self):
        store = kernel.Battery("store", 200, 30, 5, 0, 1, .8, 0)
        store.stored_energy = {0: 100}
        result = ahead([gas()], [store], 10, period=2)
        self.assertEqual(sum(q for obj, q in result[10] if obj is store), 10)
        self.assertEqual(result[14]["store"], 25)

    def test_multiple_storage_batches_are_paid_once_at_separate_storage_price(self):
        store = kernel.Battery("store", 200, 30, 5, 1, 1, 1, 0)
        store.stored_energy = {0: 3, 1: 4}
        result = ahead([gas()], [store], 6, period=3)
        self.assertAlmostEqual(result[14]["store"], 6 * .5 * 8)

    def test_balancing_new_vre_enters_physical_gen_list(self):
        first, second = vre("first", 100), vre("second", 80)
        planned = ahead([first, second], [], 50)
        result = balance([first, second], [], planned, 120, 50)
        output = {obj.name: value for obj, value in result[8]}
        self.assertIn("second", output)
        self.assertAlmostEqual(sum(output.values()), 120)
        self.assertAlmostEqual(output["second"], 70 * 80 / 130)

    def test_source_import_branch_is_reachable_with_capacity_and_price_not_swapped(self):
        domestic = gas(0)
        importer = kernel.Connection("import", 0, 0, 0)
        importer.transfer_constraint, importer.external_price = 10, 20
        planned = ahead([domestic], [], 0)
        result = balance([domestic], [], planned, 5, 0, [importer])
        self.assertEqual(result[16], 0)
        self.assertEqual(sum(result[12]), 100)  # source MW-period * GBP/MWh; x.5 at boundary
        self.assertEqual([(g.name, q) for g, q in result[8] if isinstance(g, kernel.Connection)], [("import", 5)])

    def test_import_capacity_exhaustion_reduces_residual(self):
        domestic = gas(0)
        importer = kernel.Connection("import", 0, 0, 0)
        importer.transfer_constraint, importer.external_price = 3, 20
        result = balance([domestic], [], ahead([domestic], [], 0), 5, 0, [importer])
        self.assertEqual(result[16], 2)
        self.assertEqual(sum(result[12]), 60)


if __name__ == "__main__":
    unittest.main()
