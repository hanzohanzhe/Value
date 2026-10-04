"""Short synthetic settlement checks, not thesis-result reproduction."""
import unittest
import tempfile
import random
from dataclasses import replace
from pathlib import Path
from gridform_core.builtin.scheme_c_1000twh import doctoral_market_kernel as k
from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine


class SettlementDetailsTests(unittest.TestCase):
    def gas(self, price):
        return k.GasGenerator('gas', 10, price, 0, 100, 100, 7, 0, 0, 2, 30, 0, 3)

    def test_signed_downward_cash_and_half_hour_exactly_once(self):
        for price in (-20, 20, 0):
            engine = DoctoralPeriodEngine([self.gas(price)], [], year=2025)
            plan = engine.plan_period(80)
            result = engine.realise_period(plan, 60)
            self.assertEqual(result.ahead_scheduled_mwh_by_asset['gas'], 40)
            self.assertEqual(result.downward_accepted_mwh_by_asset['gas'], 10)
            self.assertEqual(result.downward_cash_gbp_by_asset['gas'], 10*price)
            self.assertEqual(result.balancing_income_gbp_by_asset['gas'], 10*price)
            self.assertEqual(result.generation_mwh_by_asset['gas'], 30)
            self.assertEqual(result.ahead_income_gbp_by_asset['gas'], 40*(45+7))
            self.assertEqual(result.fuel_cost_gbp_by_asset['gas'], 30*30)
            self.assertEqual(result.carbon_cost_gbp_by_asset['gas'], 30*2)
            self.assertEqual(result.other_operating_cost_gbp_by_asset['gas'], 30*13)

    def test_vre_zero_downward_payment_even_if_legacy_offer_nonzero(self):
        wind = k.ExpensiverenewableGenerator('wind', 2, 3, 0, 0, 0, 0, 0, .6, 0, 0)
        wind.capacity_limit = 100
        engine = DoctoralPeriodEngine([wind], [], year=2025)
        result = engine.realise_period(engine.plan_period(80), 60)
        self.assertEqual(result.downward_accepted_mwh_by_asset['wind'], 10)
        self.assertEqual(result.downward_cash_gbp_by_asset['wind'], 0)
        self.assertEqual(result.balancing_income_gbp_by_asset['wind'], 0)

    def test_nuclear_legacy_fee_not_new_income(self):
        gen = k.NuclearGenerator('nuclear', 10, 91430, 0, 100, 100, 500, 0, 0)
        engine = DoctoralPeriodEngine([gen], [], year=2025)
        result = engine.realise_period(engine.plan_period(100), 90)
        self.assertEqual(result.downward_cash_gbp_by_asset['nuclear'], 0)
        self.assertEqual(result.legacy_downward_fee_gbp_by_asset['nuclear'], 5*91430)
        self.assertEqual(result.raw_source_cost_components['curtailment'], 10*91430)

    def test_upward_split_and_double_entry_reconcile(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_settlement import settlement_report
        engine = DoctoralPeriodEngine([self.gas(-20)], [], year=2025)
        result = engine.realise_period(engine.plan_period(60), 80)
        self.assertEqual(result.upward_accepted_mwh_by_asset['gas'], 10)
        self.assertEqual(result.upward_income_gbp_by_asset['gas'], result.balancing_income_gbp_by_asset['gas'])
        report = settlement_report(result)
        self.assertEqual(report['cash_balance_residual_gbp'], 0)
        self.assertEqual(report['agent_income_residual_gbp'], 0)
        self.assertTrue(report['legacy_downward_closed'])

    def test_uncalibrated_profile_rejected(self):
        with self.assertRaisesRegex(ValueError, 'uncalibrated'):
            DoctoralPeriodEngine([self.gas(1)], [], year=2025, cost_profile='thermal_extra_costs')

    def test_legacy_nuclear_report_is_explicitly_not_closed(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_settlement import settlement_report
        gen = k.NuclearGenerator('nuclear', 10, 91430, 0, 100, 100, 500, 0, 0)
        engine = DoctoralPeriodEngine([gen], [], year=2025)
        report = settlement_report(engine.realise_period(engine.plan_period(100), 90))
        self.assertFalse(report['legacy_downward_closed'])
        self.assertEqual(report['raw_downward_attribution_residual_gbp'], 0)

    def test_large_nuclear_roundoff_is_not_a_false_failure_but_real_error_is(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_settlement import settlement_report
        rng = random.Random(2)
        gens = [k.NuclearGenerator(str(i),10,91430,0,1000+rng.random(),2000,500,0,0) for i in range(20)]
        engine = DoctoralPeriodEngine(gens,[],year=2025)
        result = engine.realise_period(engine.plan_period(sum(g.capacity_limit for g in gens)),rng.random()*1000)
        report = settlement_report(result)
        self.assertLess(abs(report['raw_downward_attribution_residual_gbp']),1e-5)
        source = dict(result.raw_source_cost_components)
        source['curtailment'] += 2 # a real extra pound after the half-hour conversion
        with self.assertRaisesRegex(ValueError,'does not reconcile'):
            settlement_report(replace(result,raw_source_cost_components=source))

    def test_negative_import_price_has_one_procurement_credit(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_settlement import settlement_report
        gas = self.gas(1)
        gas.capacity_limit = 0
        connection = k.Connection('link', 0, 0, 0)
        connection.transfer_constraint, connection.external_price = 30, -5
        engine = DoctoralPeriodEngine([gas], [], connections=[connection], year=2025)
        result = engine.realise_period(engine.plan_period(0), 20)
        report = settlement_report(result)
        rows = [r for r in report['transactions'] if r['stage']=='external_import_procurement']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['amount_gbp'], 50)
        self.assertEqual(rows[0]['payee'], 'asset:link')
        self.assertEqual(rows[0]['payer'], 'external:link')
        self.assertEqual(report['agent_income_residual_gbp'], 0)

    def test_export_is_external_receipt_not_another_generation_sale(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_settlement import settlement_report
        wind = k.ExpensiverenewableGenerator('wind', 2, 0, 0, 0, 0, 0, 0, .6, 0, 0)
        wind.capacity_limit = 100
        connection = k.Connection('link', 0, 0, 0)
        connection.transfer_constraint, connection.external_price = -30, 5
        engine = DoctoralPeriodEngine([wind], [], connections=[connection], year=2025)
        result = engine.realise_period(engine.plan_period(80), 60)
        self.assertEqual(result.export_mwh_by_asset['link'], 15)
        self.assertEqual(result.export_receipt_gbp_by_asset['link'], 75)
        report = settlement_report(result)
        self.assertEqual(sum(r['amount_gbp'] for r in report['transactions'] if r['stage']=='external_export'),75)

    def test_detail_publish_replay_and_corruption_guard(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_settlement import publish_settlement_report, verify_settlement_files
        engine = DoctoralPeriodEngine([self.gas(-20)], [], year=2025)
        outcome = engine.realise_period(engine.plan_period(80), 60)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record = publish_settlement_report(root, outcome)
            self.assertEqual(record, publish_settlement_report(root, outcome))
            verify_settlement_files(root, [record], 1)
            (root/record['file']).write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                verify_settlement_files(root, [record], 1)
            with self.assertRaisesRegex(ValueError, 'differs from replay'):
                publish_settlement_report(root, outcome)

    def test_storage_downward_cash_zero_and_inventory_reconciles(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_settlement import settlement_report
        wind = k.ExpensiverenewableGenerator('wind', 2, 0, 0, 0, 0, 0, 0, .6, 0, 0)
        wind.capacity_limit = 100
        store = k.Battery('store', 200, 50, 10, 1, .9, .8, 0, battery_type='1c')
        engine = DoctoralPeriodEngine([wind,self.gas(-20)], [store], year=2025)
        first = engine.realise_period(engine.plan_period(50),50)
        engine.commit(first)
        second = engine.realise_period(engine.plan_period(20,available_mw_by_vre={'wind':0}),10)
        self.assertEqual(second.downward_cash_gbp_by_asset['store'],0)
        # Source absorbs surplus through charging; it does not offer storage
        # discharge into its generator curtailment auction. Preserve that rule.
        expected = (engine.state.storage_energy_mwh('store') + second.storage_charge_mwh
            - second.storage_discharge_mwh - second.storage_decay_loss_mwh
            - second.storage_conversion_loss_mwh - second.storage_numerical_discard_mwh)
        self.assertAlmostEqual(expected,second.next_state.storage_energy_mwh('store'))
        self.assertEqual(settlement_report(second)['cash_balance_residual_gbp'],0)


if __name__ == '__main__':
    unittest.main()
