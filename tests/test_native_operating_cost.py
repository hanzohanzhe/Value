"""P0-6 S4 (P5-06): physical operating cost and settlement accounts of the default PSM."""

from __future__ import annotations

import unittest

import numpy as np

from gridform_core.builtin.scheme_c_1000twh import native_corrected as corrected
from gridform_core.builtin.scheme_c_1000twh.native_market_rules import (
    CORRECTED,
    DOCTORAL,
    column_semantics,
    voll_gbp_per_mwh,
)
from gridform_core.builtin.scheme_c_1000twh.native_realisation import COST_COLUMNS, RealisationLog
from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM

from tests import native_reproduction_harness as harness


def _asset(kind: str, name: str, **attributes):
    cls = type(kind, (), {})
    asset = cls()
    asset.name = name
    for key, value in attributes.items():
        setattr(asset, key, value)
    return asset


class PhysicalCostTermsTests(unittest.TestCase):
    def test_hand_calculated_period(self):
        # Half-hour period.  CCGT 20 MW at 50 GBP/MWh that was not running
        # (start-up adder 10 GBP/MWh), wind 30 MW at 0.0001, import 5 MW at
        # 80 GBP/MWh, battery discharge 10 MW (wear is booked on the battery).
        ccgt = _asset("GasGenerator", "CCGT", gen_cost=50.0, startup_cost=10.0)
        wind = _asset("ExpensiverenewableGenerator", "onshore", gen_cost=0.0001)
        link = _asset("Connection", "Interconnect_France", external_price=80.0)
        battery = _asset("Battery", "battery")
        terms = corrected.physical_cost_terms(
            {ccgt: 20.0, wind: 30.0, link: 5.0, battery: 10.0}, [], 0.5,
            storage_fee_this_period=12.0, retained_cost_gbp=900.0, generation_offer_gbp=600.0,
            storage_fee_retained_gbp=6.0, curtailment_fee_gbp=0.0, balancing_fee_gbp=294.0,
            export_revenue_gbp=0.0, import_payment_gbp=200.0,
        )
        self.assertAlmostEqual(terms["generation_variable_gbp"], 0.5 * (20 * 50.0 + 30 * 0.0001), places=12)
        self.assertAlmostEqual(terms["import_variable_gbp"], 200.0)
        self.assertAlmostEqual(terms["startup_adder_gbp"], 100.0)
        self.assertAlmostEqual(terms["storage_offer_payment_gbp"], 6.0)
        # A unit that was already running carries no start-up adder.
        running = corrected.physical_cost_terms(
            {ccgt: 20.0}, [ccgt], 0.5, storage_fee_this_period=0.0, retained_cost_gbp=0.0,
            generation_offer_gbp=0.0, storage_fee_retained_gbp=0.0, curtailment_fee_gbp=0.0,
            balancing_fee_gbp=0.0, export_revenue_gbp=0.0, import_payment_gbp=0.0,
        )
        self.assertEqual(running["startup_adder_gbp"], 0.0)

    def test_physical_cost_ignores_the_bid_multiplier(self):
        # gen_cost is the running cost; the multiplier only scales offers, so
        # the same dispatch has the same physical cost (plan S4 test).
        ccgt = _asset("GasGenerator", "CCGT", gen_cost=50.0, startup_cost=0.0)
        one = corrected.physical_cost_terms(
            {ccgt: 40.0}, [ccgt], 0.5, storage_fee_this_period=0.0, retained_cost_gbp=1000.0,
            generation_offer_gbp=1000.0, storage_fee_retained_gbp=0.0, curtailment_fee_gbp=0.0,
            balancing_fee_gbp=0.0, export_revenue_gbp=0.0, import_payment_gbp=0.0,
        )
        two = corrected.physical_cost_terms(
            {ccgt: 40.0}, [ccgt], 0.5, storage_fee_this_period=0.0, retained_cost_gbp=2000.0,
            generation_offer_gbp=2000.0, storage_fee_retained_gbp=0.0, curtailment_fee_gbp=0.0,
            balancing_fee_gbp=0.0, export_revenue_gbp=0.0, import_payment_gbp=0.0,
        )
        self.assertEqual(one["generation_variable_gbp"], two["generation_variable_gbp"])
        self.assertEqual(one["generation_variable_gbp"], 1000.0)


class VollTests(unittest.TestCase):
    def test_doctoral_uses_the_author_constant(self):
        # A16-5 (fx5.voll-17000): the thesis constant 8000 is replaced by 17000;
        # the doctoral rule set ignores the parameter.
        self.assertEqual(voll_gbp_per_mwh(DOCTORAL, {"market.voll_gbp_per_mwh": 12345.0}), 17000.0)
        self.assertEqual(voll_gbp_per_mwh(DOCTORAL, {}), 17000.0)

    def test_corrected_reads_the_parameter(self):
        self.assertEqual(voll_gbp_per_mwh(CORRECTED, {}), 17000.0)
        self.assertEqual(voll_gbp_per_mwh(CORRECTED, {"market.voll_gbp_per_mwh": None}), 17000.0)
        self.assertEqual(voll_gbp_per_mwh(CORRECTED, {"market.voll_gbp_per_mwh": 12345.0}), 12345.0)


class OperatingAccountTests(unittest.TestCase):
    def _log(self, **columns) -> RealisationLog:
        log = RealisationLog(2)
        for column in COST_COLUMNS:
            getattr(log, column)[:] = np.asarray(columns.get(column, (0.0, 0.0)), dtype=float)
        return log

    def test_operating_is_physical_and_wear_is_counted_once(self):
        log = self._log(
            generation_variable_gbp=(500.0, 469.35), import_variable_gbp=(0.0, 0.0),
            startup_adder_gbp=(0.0, 0.0), storage_offer_payment_gbp=(30.0, 0.0),
            retained_period_cost_gbp=(800.0, 530.0), generation_offer_payment_gbp=(770.0, 500.0),
            storage_fee_retained_gbp=(30.0, 30.0), balancing_payment_gbp=(0.0, 0.0),
        )

        class _Summary:
            def __init__(self, blackout):
                self.blackout_mwh = blackout

        detail, settlement = SchemeCNativePSM._operating_cost_accounts(
            log, (_Summary(0.0), _Summary(5.0)), DOCTORAL, {}, 7.5,
        )
        # 969.35 generation + 5 MWh x 17000 + 7.5 wear (A16-5: the thesis
        # constant was 8000); the storage offer payment (which already
        # contains the wear) is a transfer.
        self.assertAlmostEqual(detail["total_gbp"], 969.35 + 85000.0 + 7.5)
        self.assertEqual(detail["blackout_reliability"], 85000.0)
        self.assertEqual(detail["voll_basis"], "constant_17000")
        detail_corrected, _ = SchemeCNativePSM._operating_cost_accounts(
            log, (_Summary(0.0), _Summary(5.0)), CORRECTED, {}, 7.5,
        )
        self.assertEqual(detail_corrected["blackout_reliability"], 85000.0)
        detail_override, _ = SchemeCNativePSM._operating_cost_accounts(
            log, (_Summary(0.0), _Summary(5.0)), CORRECTED, {"market.voll_gbp_per_mwh": 10000.0}, 7.5,
        )
        self.assertEqual(detail_override["blackout_reliability"], 50000.0)
        # The thesis cost column carried 30 GBP of storage fee into period 1.
        self.assertAlmostEqual(settlement["storage_fee_carry_residual"], 30.0)
        self.assertEqual(settlement["reconciliation"], "reconciled")


class SyntheticAccountTests(unittest.TestCase):
    """The 96-period synthetic scenario through the live loop (both rule sets)."""

    def _run(self, rules, variant="dynamic"):
        log = RealisationLog()
        harness.run_case(variant, loop="live", runtime_attributes={"market_rules": rules, "realisation_log": log})
        return log

    def test_storage_fee_carry_is_diagnosed_and_settled_per_period(self):
        # R4-1 (A26, DEV-STO-01): with one storage position per period the
        # dynamic variant no longer discharges a store in the balancing stage
        # after the ahead stage, so the thesis carry is shown on the legacy
        # tariff variant (the doctoral reference configuration, Q3).
        self.assertEqual(float(np.sum(self._run(DOCTORAL).storage_fee_carry_gbp_per_h)), 0.0)
        log = self._run(DOCTORAL, "legacy_tariff")
        carry = float(np.sum(log.storage_fee_carry_gbp_per_h)) * 0.5
        residual = float(np.sum(log.storage_fee_retained_gbp - log.storage_offer_payment_gbp))
        self.assertGreater(carry, 0.0)
        self.assertAlmostEqual(residual, carry, places=6)
        corrected_log = self._run(CORRECTED)
        self.assertEqual(float(np.sum(corrected_log.storage_fee_carry_gbp_per_h)), 0.0)
        self.assertAlmostEqual(
            float(np.sum(corrected_log.storage_fee_retained_gbp - corrected_log.storage_offer_payment_gbp)),
            0.0, places=9,
        )

    def test_retained_cost_reconciles_to_its_settlement_parts(self):
        log = self._run(DOCTORAL)
        parts = (log.generation_offer_payment_gbp + log.storage_fee_retained_gbp
                 + log.curtailment_payment_gbp + log.balancing_payment_gbp)
        np.testing.assert_allclose(log.retained_period_cost_gbp, parts, rtol=1e-9, atol=1e-9)


class ColumnSemanticsTests(unittest.TestCase):
    def test_doctoral_declarations_are_the_retained_ones(self):
        self.assertEqual(column_semantics(DOCTORAL), {
            "excess_scope": "inflexible_mixed",
            "excess_relationship": "separate_prebalancing",
            "curtailment_semantics": "balancing_stage_down_regulation_after_storage_export_and_flexible_demand",
        })

    def test_corrected_declares_vre_curtailment_and_non_vre_spill(self):
        semantics = column_semantics(CORRECTED)
        self.assertEqual(semantics["excess_scope"], "non_vre_spill")
        self.assertEqual(semantics["curtailment_semantics"], "vre_available_minus_gross_output")


if __name__ == "__main__":
    unittest.main()
