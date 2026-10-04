import json
import math
import unittest

from gridform_core.builtin.scheme_c_1000twh.compat.modular_simulation_model import (
    Battery,
    ahead_market_bidding,
    np,
)
from gridform_core.builtin.scheme_c_1000twh.compat import modular_storage_expansion_cap
from gridform_core.builtin.scheme_c_1000twh.compat.storage_cost import (
    DynamicAnnualStorageCost,
    SchemeCLegacyTariffStorageCost,
    UserFormulaAnnualStorageCost,
    compile_storage_formula,
)
from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import (
    restore_storage_cost_runtime,
    snapshot_storage_cost_runtime,
)


class DynamicStorageCostTests(unittest.TestCase):
    def test_runtime_snapshot_restores_observations_and_pricing_coefficients(self):
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import (
            UserFormulaAnnualStorageCost as RuntimeUserFormulaAnnualStorageCost,
        )

        original = RuntimeUserFormulaAnnualStorageCost(
            formula="cycle_depreciation_gbp_per_mwh + dwell_periods * holding_recovery_gbp_per_mwh_period",
            battery_type="1c",
            utilisation_floor=0.1,
        )
        kwargs = dict(
            capital_cost_gbp=1_000_000.0,
            power_capacity_mw=1.0,
            energy_capacity_mwh=1.0,
            discharge_efficiency=0.9,
        )
        original.prepare_year(2025, **kwargs)
        original.record_sale(10.0, 2.0)
        original.prepare_year(2026, **kwargs)
        original.record_sale(4.0, 3.0)
        payload = json.loads(json.dumps(snapshot_storage_cost_runtime(original)))

        rebuilt = RuntimeUserFormulaAnnualStorageCost(
            formula=original.formula,
            battery_type="1c",
            utilisation_floor=0.1,
        )
        restore_storage_cost_runtime(rebuilt, payload)

        self.assertEqual(snapshot_storage_cost_runtime(rebuilt), payload)
        self.assertEqual(rebuilt.report(), original.report())
        self.assertAlmostEqual(rebuilt.bid_price_gbp_per_mwh(7), original.bid_price_gbp_per_mwh(7))
        self.assertNotIn("formula", payload)
        self.assertNotIn("_compiled_formula", payload)

    def test_runtime_restore_rejects_impossible_years_and_negative_cost_state(self):
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import (
            DynamicAnnualStorageCost as RuntimeDynamicAnnualStorageCost,
        )

        source = RuntimeDynamicAnnualStorageCost(battery_type="1c")
        kwargs = dict(
            capital_cost_gbp=1_000_000.0,
            power_capacity_mw=1.0,
            energy_capacity_mwh=1.0,
            discharge_efficiency=0.9,
        )
        source.prepare_year(2025, **kwargs)
        source.record_sale(2.0, 3.0)
        source.prepare_year(2026, **kwargs)
        payload = snapshot_storage_cost_runtime(source)

        mutations = (
            ("current.year", lambda item: item["current"].update(year=2025)),
            ("previous.year", lambda item: item["previous"].update(year=2027)),
            (
                "negative sold energy",
                lambda item: item["current"].update(sold_energy_mwh=-1.0),
            ),
            (
                "negative dwell total",
                lambda item: item["previous"].update(
                    dwell_weighted_sold_mwh_periods=-1.0
                ),
            ),
            (
                "negative pricing coefficient",
                lambda item: item.update(cycle_depreciation_gbp_per_mwh=-1.0),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                invalid = json.loads(json.dumps(payload))
                mutate(invalid)
                rebuilt = RuntimeDynamicAnnualStorageCost(battery_type="1c")
                with self.assertRaises(ValueError):
                    restore_storage_cost_runtime(rebuilt, invalid)

    def test_full_utilisation_initialisation_recovers_annual_levelized_cost(self):
        model = DynamicAnnualStorageCost(battery_type="0.5c")
        model.prepare_year(
            2025,
            capital_cost_gbp=1_000_000.0,
            power_capacity_mw=1.0,
            energy_capacity_mwh=2.0,
            discharge_efficiency=1.0,
        )
        recovered = (
            model.cycle_depreciation_gbp_per_mwh * model.pricing_basis_sold_mwh
            + model.holding_recovery_gbp_per_mwh_period
            * model.pricing_basis_sold_mwh
            * model.pricing_basis_average_dwell_periods
        )
        self.assertEqual(model.pricing_basis, "full_utilisation_initialisation")
        self.assertTrue(
            math.isclose(recovered, model.annual_levelized_project_cost_gbp, rel_tol=1e-12)
        )

    def test_next_year_uses_previous_year_sold_energy_and_dwell(self):
        model = DynamicAnnualStorageCost(battery_type="1c", utilisation_floor=0.0)
        kwargs = dict(
            capital_cost_gbp=1_000_000.0,
            power_capacity_mw=1.0,
            energy_capacity_mwh=1.0,
            discharge_efficiency=0.9,
        )
        model.prepare_year(2025, **kwargs)
        model.record_sale(80.0, 2.0)
        model.record_sale(20.0, 6.0)
        model.prepare_year(2026, **kwargs)

        self.assertEqual(model.pricing_basis, "previous_year_sales")
        self.assertAlmostEqual(model.pricing_basis_sold_mwh, 100.0)
        self.assertAlmostEqual(model.pricing_basis_average_dwell_periods, 2.8)
        recovered = (
            model.cycle_depreciation_gbp_per_mwh * 100.0
            + model.holding_recovery_gbp_per_mwh_period * 100.0 * 2.8
        )
        self.assertAlmostEqual(recovered, model.annual_levelized_project_cost_gbp)

    def test_pumped_hydro_has_no_cycle_depreciation(self):
        model = DynamicAnnualStorageCost(battery_type="pumped_hydro")
        model.prepare_year(
            2025,
            capital_cost_gbp=500_000_000.0,
            power_capacity_mw=2_000.0,
            energy_capacity_mwh=8_000.0,
            discharge_efficiency=0.87,
        )
        self.assertEqual(model.cycle_depreciation_gbp_per_mwh, 0.0)
        recovered = (
            model.holding_recovery_gbp_per_mwh_period
            * model.pricing_basis_sold_mwh
            * model.pricing_basis_average_dwell_periods
        )
        self.assertAlmostEqual(recovered, model.annual_levelized_project_cost_gbp)

    def test_hydrogen_storage_has_no_battery_cycle_depreciation(self):
        model = DynamicAnnualStorageCost(battery_type="hydrogen")
        model.prepare_year(
            2025,
            capital_cost_gbp=1_000_000.0,
            power_capacity_mw=1.0,
            energy_capacity_mwh=250.0,
            discharge_efficiency=0.57,
        )
        self.assertEqual(model.cycle_depreciation_gbp_per_mwh, 0.0)

    def test_battery_uses_explicit_power_energy_ratio_and_records_delivered_mwh(self):
        battery = Battery(
            name="air_battery",
            pool_limit=400.0,
            per_pool_limit=200.0,
            storage_fee=999.0,
            per_storage_fee=999.0,
            n_1=0.8,
            n_2=0.8,
            carbon_emission=0.0,
            capital_cost=45_000_000.0,
            battery_type="0.25c",
        )
        self.assertAlmostEqual(battery.energy_capacity_mwh, 400.0)
        self.assertAlmostEqual(battery.power_capacity_mw, 100.0)
        battery.prepare_operating_year(2025)
        self.assertNotEqual(battery.storage_fee, 999.0)

        self.assertAlmostEqual(battery.charge(0, 100.0), 100.0)
        self.assertAlmostEqual(battery.stored_energy[0], 40.0)
        self.assertAlmostEqual(battery.available_discharge_power(0), 64.0)
        self.assertAlmostEqual(battery.discharge(0, 64.0, 2), 64.0)
        self.assertAlmostEqual(battery.cost_recovery.current.sold_energy_mwh, 32.0)
        self.assertAlmostEqual(sum(battery.stored_energy.values()), 0.0)
        report = battery.storage_cost_report()
        self.assertGreater(report["annual_fixed_opex_gbp"], 0.0)
        self.assertGreater(report["current_cycle_depreciation_gbp"], 0.0)

    def test_cem_power_resize_preserves_fixed_technology_duration(self):
        battery = Battery(
            "thermal_battery", 100.0, 50.0, 0.0, 1.0, 0.9, 0.9, 0.0,
            capital_cost=1.0,
            battery_type="1c",
        )
        battery.pool_limit = 125.0
        self.assertAlmostEqual(battery.power_capacity_mw, 125.0)
        self.assertAlmostEqual(battery.energy_capacity_mwh, 125.0)

    def test_disabling_plot_only_tranche_history_is_dispatch_equivalent(self):
        def execute(retain_history):
            battery = Battery(
                "li_battery", 20.0, 10.0, 0.0, 0.0, 0.9, 0.9, 0.0,
                capital_cost=1_000_000.0,
                battery_type="0.5c",
            )
            battery.prepare_operating_year(2025)
            battery.stored_energy = {0: 4.0, 1: 3.0}
            traces = [np.zeros(4, dtype=np.float32) for _ in range(4)]
            result = ahead_market_bidding(
                [], [battery], 5.0, 3, [],
                traces[0], traces[1], traces[2], traces[3], 1.0,
                retain_storage_tranche_history=retain_history,
            )
            return battery, result

        traced_battery, traced = execute(True)
        compact_battery, compact = execute(False)

        self.assertTrue(traced[2])
        self.assertTrue(traced[3])
        self.assertEqual(compact[2], {})
        self.assertEqual(compact[3], {})
        self.assertAlmostEqual(traced[1], compact[1])
        self.assertAlmostEqual(traced[10][0][1], compact[10][0][1])
        self.assertAlmostEqual(
            traced_battery.cost_recovery.current.sold_energy_mwh,
            compact_battery.cost_recovery.current.sold_energy_mwh,
        )
        self.assertEqual(traced_battery.stored_energy.keys(), compact_battery.stored_energy.keys())
        for period in traced_battery.stored_energy:
            self.assertAlmostEqual(
                traced_battery.stored_energy[period],
                compact_battery.stored_energy[period],
            )

    def test_modular_storage_cap_ignores_legacy_hard_coded_tariffs(self):
        sec = modular_storage_expansion_cap
        original_capex = sec.config.capital_costs_per_mw["1c_battery"]
        original_storage_fee = sec.config.batteries["1c_battery"]["storage_fee"]
        original_holding_fee = sec.config.batteries["1c_battery"]["per_storage_fee"]
        try:
            sec.config.capital_costs_per_mw["1c_battery"] = 1.0
            signal = [0.0, 0.0, 1.0, 1.0]
            excess = [1.0, 1.0, 0.0, 0.0]
            prices = [0.0, 0.0, 100.0, 100.0]
            baseline = sec.simulate_tier_arbitrage_profit(
                signal, excess, prices, "1c_battery", 1.0
            )
            sec.config.batteries["1c_battery"]["storage_fee"] = 1e9
            sec.config.batteries["1c_battery"]["per_storage_fee"] = 1e9
            changed_legacy_values = sec.simulate_tier_arbitrage_profit(
                signal, excess, prices, "1c_battery", 1.0
            )
            self.assertGreater(baseline, 0.0)
            self.assertAlmostEqual(baseline, changed_legacy_values)
        finally:
            sec.config.capital_costs_per_mw["1c_battery"] = original_capex
            sec.config.batteries["1c_battery"]["storage_fee"] = original_storage_fee
            sec.config.batteries["1c_battery"]["per_storage_fee"] = original_holding_fee

    def test_legacy_tariff_matches_scheme_c_equation_exactly(self):
        model = SchemeCLegacyTariffStorageCost(
            battery_type="0.5c",
            storage_fee_gbp_per_mwh=135.26,
            holding_fee_gbp_per_mwh_period=0.1736,
        )
        self.assertAlmostEqual(
            model.bid_price_gbp_per_mwh(7),
            135.26 + 7 * 0.1736,
        )
        stored = {0: 1.0, 2: 1.0, 5: 1.0}
        expected = sorted(
            stored,
            key=lambda charge_period: model.bid_price_gbp_per_mwh(6 - charge_period),
        )
        self.assertEqual(list(model.ordered_charge_periods(stored, 6)), expected)

    def test_builtin_linear_dwell_order_avoids_materialising_a_sorted_key_list(self):
        model = DynamicAnnualStorageCost(battery_type="0.5c")
        model.prepare_year(
            2025,
            capital_cost_gbp=1_000_000.0,
            power_capacity_mw=1.0,
            energy_capacity_mwh=2.0,
            discharge_efficiency=0.9,
        )
        stored = dict.fromkeys(range(100_000), 1.0)
        order = model.ordered_charge_periods(stored, 100_000)
        self.assertNotIsInstance(order, list)
        self.assertEqual(next(order), 99_999)

    def test_battery_preserves_chronological_key_order_for_linear_merit_iteration(self):
        battery = Battery(
            "li_battery", 20.0, 10.0, 0.0, 0.0, 0.9, 0.9, 0.0,
            capital_cost=1_000_000.0,
            battery_type="0.5c",
        )
        for period in (5, 1, 3):
            battery.set_stored_energy_var(period, 1.0)
        self.assertEqual(list(battery.stored_energy), [1, 3, 5])
        battery.prepare_operating_year(2025)
        expected = sorted(
            battery.stored_energy,
            key=lambda charge_period: battery.storage_bid_price(6, charge_period),
        )
        self.assertEqual(list(battery.ordered_charge_periods(6)), expected)

    def test_user_formula_is_arithmetic_only(self):
        model = UserFormulaAnnualStorageCost(
            formula="cycle_depreciation_gbp_per_mwh + 2 * dwell_periods * holding_recovery_gbp_per_mwh_period",
            battery_type="1c",
        )
        model.prepare_year(
            2025,
            capital_cost_gbp=1_000_000.0,
            power_capacity_mw=1.0,
            energy_capacity_mwh=1.0,
            discharge_efficiency=0.9,
        )
        expected = model.cycle_depreciation_gbp_per_mwh + 6 * model.holding_recovery_gbp_per_mwh_period
        self.assertAlmostEqual(model.bid_price_gbp_per_mwh(3), expected)
        non_monotonic = UserFormulaAnnualStorageCost(
            formula="100 - dwell_periods",
            battery_type="1c",
        )
        non_monotonic.prepare_year(
            2025,
            capital_cost_gbp=1_000_000.0,
            power_capacity_mw=1.0,
            energy_capacity_mwh=1.0,
            discharge_efficiency=0.9,
        )
        stored = {0: 1.0, 1: 1.0, 2: 1.0}
        self.assertEqual(
            list(non_monotonic.ordered_charge_periods(stored, 3)),
            [0, 1, 2],
        )
        for invalid in (
            "__import__('os').system('echo unsafe')",
            "dwell_periods.__class__",
            "unknown_name + 1",
            "dwell_periods[0]",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    compile_storage_formula(invalid)


if __name__ == "__main__":
    unittest.main()
