import unittest

from gridform_core.builtin.scheme_c_1000twh.legacy_result_adapter import (
    SchemeCLegacyResultAdapter,
    SchemeCResultCompatibilityError,
    _LEGACY_FIELD_ORDER,
)


class Asset:
    name = "solar_test"


def valid_tuple(periods=2):
    values = {name: [] for name in _LEGACY_FIELD_ORDER}
    values.update({
        "prices_gbp_per_mwh": [10.0, 20.0][:periods],
        "storage_charge_by_period": [0.0, 1.0][:periods],
        "generation_cost_gbp_by_period": [4.0, 6.0][:periods],
        "dispatch_by_period": [[(Asset(), 4.0)], [(Asset(), 6.0)]][:periods],
        "excess_electricity_mwh_by_period": [0.0, 1.0][:periods],
        "total_cost_gbp_by_period": [5.0, 7.0][:periods],
        "real_demand_mwh_by_period": [4.0, 5.0][:periods],
        "market_income_gbp_by_agent": {"solar_test": 11.0},
        "blackout_mwh_by_period": [0.0, 0.0][:periods],
    })
    return tuple(values[name] for name in _LEGACY_FIELD_ORDER)


class LegacyResultAdapterTests(unittest.TestCase):
    def convert(self, raw=None, **overrides):
        arguments = {"year": 2025, "periods": 2, "period_hours": 0.5}
        arguments.update(overrides)
        return SchemeCLegacyResultAdapter.validate_and_convert(
            valid_tuple() if raw is None else raw, **arguments
        )

    def test_named_conversion_and_existing_energy_conversion(self):
        result = self.convert()
        self.assertEqual(result.prices_gbp_per_mwh, [10.0, 20.0])
        self.assertEqual(result.generation_mwh_by_asset(), {"solar_test": 5.0})
        public = result.to_market_year_result(
            result_id="2025", module_id="value-bid-at-cost-psm", module_version="2.0.0"
        )
        self.assertEqual(public.total_system_cost_gbp, 12.0)
        self.assertEqual(public.total_blackout_mwh, 0.0)
        self.assertEqual(public.total_excess_mwh, 1.0)
        self.assertEqual(public.market_income_gbp_by_agent, {"solar_test": 11.0})

    def test_non_tuple_and_wrong_length_fail_loudly(self):
        with self.assertRaisesRegex(SchemeCResultCompatibilityError, "must be a tuple"):
            self.convert(list(valid_tuple()))
        with self.assertRaisesRegex(SchemeCResultCompatibilityError, "40 fields"):
            self.convert(valid_tuple()[:-1])

    def test_period_length_and_numeric_value_are_validated(self):
        values = dict(zip(_LEGACY_FIELD_ORDER, valid_tuple()))
        values["prices_gbp_per_mwh"] = [10.0]
        with self.assertRaisesRegex(SchemeCResultCompatibilityError, "prices.*1 periods"):
            self.convert(tuple(values[name] for name in _LEGACY_FIELD_ORDER))
        values = dict(zip(_LEGACY_FIELD_ORDER, valid_tuple()))
        values["blackout_mwh_by_period"] = [0.0, "bad"]
        with self.assertRaisesRegex(SchemeCResultCompatibilityError, "not numeric"):
            self.convert(tuple(values[name] for name in _LEGACY_FIELD_ORDER))

    def test_dispatch_shape_income_and_run_identity_are_validated(self):
        values = dict(zip(_LEGACY_FIELD_ORDER, valid_tuple()))
        values["dispatch_by_period"] = [[("not-a-pair",)], []]
        with self.assertRaisesRegex(SchemeCResultCompatibilityError, "not an \(asset, energy\) pair"):
            self.convert(tuple(values[name] for name in _LEGACY_FIELD_ORDER))
        values = dict(zip(_LEGACY_FIELD_ORDER, valid_tuple()))
        values["market_income_gbp_by_agent"] = []
        with self.assertRaisesRegex(SchemeCResultCompatibilityError, "not a mapping"):
            self.convert(tuple(values[name] for name in _LEGACY_FIELD_ORDER))
        with self.assertRaisesRegex(SchemeCResultCompatibilityError, "Invalid VALUE result year"):
            self.convert(year=25)
        with self.assertRaisesRegex(SchemeCResultCompatibilityError, "Invalid period duration"):
            self.convert(period_hours=0.0)


if __name__ == "__main__":
    unittest.main()
