"""Transactional national period adapter, including JSON continuation."""

import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from gridform_core.builtin.scheme_c_1000twh import doctoral_market_kernel as k


def assets():
    wind = k.ExpensiverenewableGenerator("wind", 2, 3, 0, 0, 0, 0, 0, .6, 0, 0)
    wind.capacity_limit = 100
    gas = k.GasGenerator("gas", 50, 3, 0, 100, 100, 7, 0, 0, 0, 0, 0, 0)
    store = k.Battery("store", 200, 50, 10, 1, 1, .8, 0, battery_type="1c")
    return [wind, gas], [store]


class DoctoralPeriodEngineTests(unittest.TestCase):
    def engine(self, checkpoint=None):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        generators, batteries = assets()
        return DoctoralPeriodEngine(generators, batteries, year=2025, checkpoint=checkpoint)

    def test_plan_does_not_read_actual_or_modify_state_and_cannot_be_mutated(self):
        engine = self.engine()
        before = engine.export_state()
        plan = engine.plan_period(50)
        first = engine.realise_period(plan, 40)
        second = engine.realise_period(plan, 60)
        self.assertEqual(first.ahead_sha256, second.ahead_sha256)
        self.assertEqual(engine.export_state(), before)
        self.assertNotEqual(first.actual_demand_mwh, second.actual_demand_mwh)

    def test_available_vre_enters_physical_generation_for_charge(self):
        engine = self.engine()
        outcome = engine.realise_period(engine.plan_period(50), 50)
        self.assertEqual(outcome.storage_charge_mwh, 25)
        self.assertEqual(outcome.generation_mwh_by_asset["wind"], 50)
        self.assertEqual(outcome.blackout_mwh, 0)
        self.assertAlmostEqual(outcome.energy_balance_residual_mwh, 0)
        self.assertEqual(outcome.next_state.storage_energy_mwh("store"), 25)
        self.assertEqual(engine.state.storage_energy_mwh("store"), 0)
        engine.commit(outcome)
        self.assertEqual(engine.state.storage_energy_mwh("store"), 25)
        with self.assertRaisesRegex(ValueError, "already|stale"):
            engine.commit(outcome)

    def test_interruption_roundtrip_matches_uninterrupted_next_period(self):
        engine = self.engine()
        first = engine.realise_period(engine.plan_period(50), 50)
        engine.commit(first)
        restored = self.engine(json.loads(json.dumps(engine.export_state())))
        second = engine.realise_period(engine.plan_period(80, available_mw_by_vre={"wind": 0}), 85)
        replay = restored.realise_period(restored.plan_period(80, available_mw_by_vre={"wind": 0}), 85)
        self.assertEqual(second.to_dict(), replay.to_dict())
        engine.commit(second)
        restored.commit(replay)
        self.assertEqual(engine.export_state(), restored.export_state())

    def test_wrong_identity_and_tampered_state_are_rejected(self):
        engine = self.engine()
        snapshot = engine.export_state()
        snapshot["input_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "identity"):
            self.engine(snapshot)
        snapshot = engine.export_state()
        snapshot["state"]["next_absolute_period"] = 100
        with self.assertRaisesRegex(ValueError, "hash"):
            self.engine(snapshot)

    def test_actual_thermal_dispatch_does_not_sum_duplicated_legacy_real_list(self):
        engine = self.engine()
        result = engine.realise_period(engine.plan_period(40, available_mw_by_vre={"wind": 0}), 55)
        self.assertEqual(result.generation_mwh_by_asset["gas"], 27.5)
        self.assertEqual(result.blackout_mwh, 0)
        self.assertAlmostEqual(result.energy_balance_residual_mwh, 0)

    def test_non_half_hour_and_enabled_direct_electrolysis_rejected(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        generators, batteries = assets()
        with self.assertRaisesRegex(ValueError, "0.5"):
            DoctoralPeriodEngine(generators, batteries, year=2025, period_hours=1)
        generators[0].electrolyzer_limit = 10
        with self.assertRaisesRegex(ValueError, "electroly"):
            DoctoralPeriodEngine(generators, batteries, year=2025)

    def test_outcome_is_immutable_and_commit_binds_all_fields(self):
        engine = self.engine()
        outcome = engine.realise_period(engine.plan_period(50), 50)
        with self.assertRaises(TypeError):
            outcome.generation_mwh_by_asset["wind"] = 9999
        for forged in (
            replace(outcome, next_state=replace(outcome.next_state, year=2030)),
            replace(outcome, next_state=replace(outcome.next_state, next_period_index=0)),
            replace(outcome, actual_demand_mwh=9999),
        ):
            with self.assertRaisesRegex(ValueError, "issued|advance|year|period"):
                engine.commit(forged)
        engine.commit(outcome)

    def test_rule_implementation_change_rejects_old_snapshot(self):
        snapshot = self.engine().export_state()
        previous = k.acm_income
        def doubled(*args, **kwargs):
            return {key: value * 2 for key, value in previous(*args, **kwargs).items()}
        with patch.object(k, "acm_income", doubled):
            with self.assertRaisesRegex(ValueError, "rule|identity"):
                self.engine(snapshot)

    def test_nuclear_surplus_is_not_generated_twice_and_spill_is_explicit(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        nuclear = k.NuclearGenerator("nuclear", 10, 100, 0, 100, 10, 0, 0, 0)
        store = k.Battery("store", 200, 50, 100, 0, 1, 1, 0, battery_type="1c")
        for actual, spill in ((20, 10), (30, 5)):
            engine = DoctoralPeriodEngine([nuclear], [store], year=2025)
            outcome = engine.realise_period(engine.plan_period(20), actual)
            self.assertEqual(outcome.generation_mwh_by_asset["nuclear"], 45)
            self.assertEqual(outcome.storage_charge_mwh, 25)
            self.assertEqual(outcome.non_vre_spill_mwh, spill)
            self.assertAlmostEqual(outcome.energy_balance_residual_mwh, 0)

    def test_actual_downward_ramp_floor_is_explicit_spill_after_sinks(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        # A 3000 MW unit can reduce only 500 MW in this half-hour. Charging
        # and export absorb the downward demand difference before curtailment.
        for charge_mw, export_mw, generation_mwh, spill_mwh in (
            (0, 0, 1250, 1250), (400, 0, 1250, 1050), (0, 600, 1250, 950),
            (400, 600, 1250, 750), (1200, 1400, 1300, 0), (1400, 1600, 1500, 0),
        ):
            with self.subTest(charge_mw=charge_mw, export_mw=export_mw):
                nuclear = k.NuclearGenerator("nuclear", 10, 100, 0, 3000, 500, 0, 0, 0)
                store = k.Battery("store", 10000, charge_mw, 100, 0, 1, 1, 0, battery_type="1c")
                link = k.Connection("export", 0, 0, 0)
                link.transfer_constraint, link.external_price = -export_mw, 10
                engine = DoctoralPeriodEngine([nuclear], [store], connections=[link], year=2025)
                before = engine.export_state()
                outcome = engine.realise_period(engine.plan_period(3000), 0)
                self.assertEqual(outcome.generation_mwh_by_asset["nuclear"], generation_mwh)
                self.assertEqual(outcome.storage_charge_mwh, charge_mw * .5)
                self.assertEqual(outcome.export_mwh, export_mw * .5)
                self.assertEqual(outcome.non_vre_spill_mwh, spill_mwh)
                self.assertEqual(outcome.vre_curtailed_mwh, 0)
                self.assertEqual(outcome.blackout_mwh, 0)
                self.assertAlmostEqual(outcome.energy_balance_residual_mwh, 0)
                self.assertEqual(engine.export_state(), before)

    def test_downward_curtailment_reconciles_mixed_vre_and_nuclear_surplus(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        # Nuclear offers first: 90 MW physical output for a 20 MW schedule,
        # plus 100 MW unaccepted wind. Store takes the 10 MW demand drop
        # first, then 10 MW of the existing 170 MW surplus; export takes
        # another 75 MW of that pool. Half of each source pool is consumed.
        nuclear = k.NuclearGenerator("nuclear", 1, 100, 0, 100, 10, 0, 0, 0)
        wind = assets()[0][0]
        store = k.Battery("store", 200, 20, 100, 0, 1, 1, 0, battery_type="1c")
        link = k.Connection("export", 0, 0, 0)
        link.transfer_constraint, link.external_price = -75, 10
        engine = DoctoralPeriodEngine([nuclear, wind], [store], connections=[link], year=2025)
        result = engine.realise_period(engine.plan_period(20), 10)
        self.assertEqual(result.generation_mwh_by_asset["nuclear"], 45)
        self.assertEqual(result.generation_mwh_by_asset["wind"], 25)
        self.assertEqual(result.storage_charge_mwh, 10)
        self.assertEqual(result.export_mwh, 37.5)
        self.assertEqual(result.non_vre_spill_mwh, 17.5)
        self.assertEqual(result.vre_curtailed_mwh, 25)
        self.assertEqual(result.blackout_mwh, 0)
        self.assertAlmostEqual(result.energy_balance_residual_mwh, 0)

    def test_downward_curtailment_does_not_count_curtailed_vre_as_spill(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        # Wind supplies 100 MW and nuclear supplies 90 MW for a 150 MW
        # schedule. On a drop to zero, all wind can stop; nuclear is already
        # at its ramp floor. Its 40 MW old surplus and 50 MW unmet downward
        # request are one 90 MW physical spill, without wind generation.
        nuclear = k.NuclearGenerator("nuclear", 10, 100, 0, 100, 10, 0, 0, 0)
        wind = assets()[0][0]
        engine = DoctoralPeriodEngine([wind, nuclear], [], year=2025)
        result = engine.realise_period(engine.plan_period(150), 0)
        self.assertEqual(result.generation_mwh_by_asset, {"wind": 0, "nuclear": 45})
        self.assertEqual(result.vre_curtailed_mwh, 50)
        self.assertEqual(result.non_vre_spill_mwh, 45)
        self.assertEqual(result.blackout_mwh, 0)
        self.assertAlmostEqual(result.energy_balance_residual_mwh, 0)

    def test_connection_capacity_and_price_advance_with_local_period(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        gas = k.GasGenerator("gas", 1000, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        link = k.Connection("import", 0, 0, 0)
        link.doctoral_transfer_constraint_mw_by_period = (10, 30)
        link.doctoral_external_price_gbp_per_mwh_by_period = (5, 7)
        engine = DoctoralPeriodEngine([gas], [], connections=[link], year=2025)
        for imported, cost in ((5, 25), (15, 105)):
            result = engine.realise_period(engine.plan_period(0), 100)
            self.assertEqual(result.import_mwh, imported)
            self.assertEqual(result.operating_cost_gbp_by_asset["import"], cost)
            engine.commit(result)
        with self.assertRaisesRegex(ValueError, "connection|profile"):
            engine.plan_period(0)

    def test_storage_losses_are_explicit_and_soc_balances(self):
        engine = self.engine()
        first = engine.realise_period(engine.plan_period(50), 50)
        engine.commit(first)
        second = engine.realise_period(engine.plan_period(20, available_mw_by_vre={"wind": 0}), 20)
        self.assertAlmostEqual(second.storage_decay_loss_mwh, 25 * .000021)
        self.assertAlmostEqual(second.storage_conversion_loss_mwh, 10 * (1 / .8 - 1))
        self.assertEqual(second.storage_numerical_discard_mwh, 0)
        self.assertAlmostEqual(second.next_state.storage_energy_mwh("store"),
            25 + second.storage_charge_mwh - second.storage_discharge_mwh
            - second.storage_decay_loss_mwh - second.storage_conversion_loss_mwh)

    def test_typed_capacity_profile_is_used_every_period(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        gas = assets()[0][1]
        gas.doctoral_capacity_mw_by_period = (50, 10)
        engine = DoctoralPeriodEngine([gas], [], year=2025)
        for generation in (25, 5):
            result = engine.realise_period(engine.plan_period(100), 100)
            self.assertEqual(result.generation_mwh_by_asset["gas"], generation)
            engine.commit(result)

    def test_forecast_shortfall_does_not_trigger_spurious_actual_curtailment(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        gas = assets()[0][1]
        gas.capacity_limit = 50
        engine = DoctoralPeriodEngine([gas], [], year=2025)
        result = engine.realise_period(engine.plan_period(100), 60)
        self.assertEqual(result.generation_mwh_by_asset["gas"], 25)
        self.assertEqual(result.blackout_mwh, 5)


if __name__ == "__main__":
    unittest.main()
