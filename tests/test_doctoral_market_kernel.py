"""Small-case source parity, not annual or physical-validity certification."""

from __future__ import annotations

import importlib
import importlib.util
import unittest
from unittest.mock import patch

from tests.doctoral_reference_harness import load_reference_symbols


def _observable(value):
    if isinstance(value, (list, tuple)):
        return [_observable(item) for item in value]
    if isinstance(value, dict):
        return {key: _observable(item) for key, item in value.items()}
    if hasattr(value, "name"):
        return value.name
    return value


def _gas(namespace, name="gas", price=50, startup=7):
    return namespace["GasGenerator"](name, price, 3, 0, 100, 100, startup, 0, 0, 0, 0, 0, 0)


def _electrolyzer_off(namespace):
    return namespace["Electrolyzer"]("off", 0, 0, 0.65, 0, 0, 0, 0)


def _ahead(namespace, generators, batteries, demand, period=0, accepted=None):
    return namespace["ahead_market_bidding"](
        generators, batteries, demand, period, accepted if accepted is not None else [],
        [0.0] * 4, [0.0] * 4, [0.0] * 4, [0.0] * 4, 1.0)


def _thermal_two_periods(namespace):
    generator = _gas(namespace)
    first = _ahead(namespace, [generator], [], 40)
    first_observed = _observable(first)
    balance = namespace["balancing_market_bidding"](
        [generator], 0, 55, 40, first[0], first[6],
        [0.0] * 4, [0.0] * 4, [0.0] * 4, first[10], [0.0] * 4,
        [], first[12], first[13], _electrolyzer_off(namespace), first[15], [], 1.0)
    balance_observed = _observable(balance)
    after_balance = dict(vars(generator))
    second = _ahead(namespace, [generator], [], 35, period=1, accepted=first[0])
    return {"first": first_observed, "balance": balance_observed,
            "after_balance": after_balance, "second": _observable(second),
            "final_state": dict(vars(generator))}


def _charge_before_export(namespace):
    expensive = namespace["Battery"]("expensive", 100, 8, 20, 1, 1, 1, 0)
    cheap = namespace["Battery"]("cheap", 100, 10, 0, 1, 1, 1, 0)
    connection = namespace["Connection"]("export", 0, 0, 0)
    connection.transfer_constraint, connection.external_price = -100, 80
    result = namespace["curtailment_market_bidding"](
        0, 0, 0, [], [], 30, [], [connection], _electrolyzer_off(namespace), [expensive, cheap])
    return {"result": _observable(result), "expensive": dict(expensive.stored_energy),
            "cheap": dict(cheap.stored_energy), "exported": connection.sold_energy}


def _storage_batch_ahead(namespace):
    battery = namespace["Battery"]("store", 100, 20, 0, 1, 1, 1, 0, battery_type="1c")
    battery.set_stored_energy_var(0, 30)
    generator = _gas(namespace)
    result = _ahead(namespace, [generator], [battery], 5, period=2)
    return {"result": _observable(result), "batch": dict(battery.stored_energy),
            "generator": dict(vars(generator))}


def _natural_energy_budget(namespace):
    water = namespace["WaterGenerator"]("water", 2, 0, 0, 50, 50, 10, 2, 0, 0, 0)
    gas = _gas(namespace)
    result = _ahead(namespace, [water, gas], [], 20)
    return {"result": _observable(result), "water": dict(vars(water)), "gas": dict(vars(gas))}


class DoctoralMarketKernelTests(unittest.TestCase):
    @staticmethod
    def kernel():
        name = "gridform_core.builtin.scheme_c_1000twh.doctoral_market_kernel"
        if importlib.util.find_spec(name) is None:
            raise AssertionError("static doctoral market kernel is not implemented")
        return importlib.import_module(name)

    def assert_reference_case(self, case):
        reference = load_reference_symbols()
        candidate = vars(self.kernel())
        self.assertIsNot(reference["Battery"], candidate["Battery"])
        actual, expected = case(candidate), case(reference)
        self.assertEqual(actual, expected)
        return actual

    def test_startup_price_balancing_and_previous_output_follow_source(self):
        observed = self.assert_reference_case(_thermal_two_periods)
        self.assertEqual(observed["first"][14], {"gas": 1140})
        self.assertEqual(observed["after_balance"]["real_gen_energy"], 55)
        self.assertEqual(observed["second"][14], {"gas": 875})

    def test_curtailment_orders_storage_before_positive_export(self):
        observed = self.assert_reference_case(_charge_before_export)
        self.assertEqual(observed["cheap"], {0: 10})
        self.assertEqual(observed["expensive"], {0: 8})
        self.assertEqual(observed["exported"], 12)

    def test_ahead_storage_uses_source_batch_decay_and_age_price(self):
        expected = _storage_batch_ahead(load_reference_symbols())
        observed = _storage_batch_ahead(vars(self.kernel()))
        # D1-income deliberately repairs the raw source's early return.
        self.assertEqual(expected["result"][14], {})
        self.assertEqual(observed["result"][14], {"store": 5})
        expected["result"][14] = {"store": 5}
        self.assertEqual(observed, expected)
        self.assertAlmostEqual(observed["batch"][0], 24.99937, places=8)

    def test_hydro_natural_energy_budget_limits_ahead_dispatch(self):
        observed = self.assert_reference_case(_natural_energy_budget)
        self.assertEqual(observed["water"]["have_gen_energy"], 12)
        self.assertEqual(observed["gas"]["real_gen_energy"], 8)

    def test_separate_prices_and_half_hour_are_explicit(self):
        kernel = self.kernel()
        reference = load_reference_symbols()
        with patch.dict("os.environ", {"PHYSICAL_PERIOD_HOURS": "1.0", "SIM_DEBUG_MARKET": "1"}):
            self.assertEqual(kernel.physical_period_hours(), 0.5)
            self.assertFalse(kernel.DEBUG_MARKET_STDOUT)
        for namespace in (vars(kernel), reference):
            gas = _gas(namespace)
            battery = namespace["Battery"]("store", 100, 20, 0, 0, 1, 1, 0)
            self.assertEqual(namespace["acm_income"]([[gas, 50, 10, 0]], [[battery, 4]], 70),
                             {"gas": 250, "store": 140})
            self.assertEqual(namespace["acm_income_balance"]([[gas, 2], [battery, 3]], 60, 80),
                             {"gas": 60, "store": 120})


if __name__ == "__main__":
    unittest.main()
