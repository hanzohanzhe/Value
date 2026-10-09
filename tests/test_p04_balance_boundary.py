"""P0-4 S6: declared energy-balance boundary, capped adjustment, A2 stress (P7-10, P3-02)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core import energy_balance_contract as contract
from gridform_core.errors import InvariantError
from gridform_core.market_ledger import (
    BalanceTermsRow,
    PeriodLedgerRow,
    create_market_ledger,
    validate_market_ledger_file,
)

SURPLUS = contract.DEFAULT_PSM_SURPLUS_NODE_V1


def _row(year, period, *, supply, demand, charge=0.0, blackout=0.0, raw=None, adjustment=0.0, residual=None):
    raw = supply + blackout - demand - charge if raw is None else raw
    residual = raw + adjustment if residual is None else residual
    return PeriodLedgerRow(
        year, period, "final_dispatch", demand, demand, supply, charge, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 0.0, blackout, 0.0, residual, adjustment, raw,
    )


class DeclaredBoundaryLedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "market" / "market.sqlite"

    def tearDown(self):
        self._tmp.cleanup()

    def _ledger(self, **declare):
        ledger = create_market_ledger(self.path, "summary", semantic_metadata={"period_hours": 0.5})
        ledger.declare_balance_boundary(SURPLUS, rule_set=contract.NATIVE_DOCTORAL_RULE_SET, **declare)
        return ledger

    def test_physical_imbalance_is_recorded_not_raised(self):
        ledger = self._ledger()
        # Period 0 closes through U_out (VRE surplus charged the store).
        ledger.record_balance_terms(BalanceTermsRow(2025, 0, 2.0, 0.0))
        ledger.record_period(_row(2025, 0, supply=10.0, demand=10.0, charge=2.0, raw=0.0))
        # Periods 1-2: hidden shortfall of 3 MWh (overshoot-like), period 4: 1 MWh.
        for period in (1, 2, 4):
            ledger.record_balance_terms(BalanceTermsRow(2025, period, 0.0, 0.0))
            short = 1.0 if period == 4 else 3.0
            ledger.record_period(_row(2025, period, supply=10.0 - short, demand=10.0))
        ledger.record_balance_terms(BalanceTermsRow(2025, 3, 0.0, 0.0))
        ledger.record_period(_row(2025, 3, supply=10.0, demand=10.0))
        metadata = ledger.close()
        self.assertEqual(ledger.physical_imbalance_periods, 3)
        with closing(sqlite3.connect(self.path)) as connection:
            stored = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
            booked = connection.execute(
                "SELECT period, raw_residual_mwh, shortfall_mwh, closing_residual_mwh, stress_flag "
                "FROM balance_boundary_period ORDER BY period"
            ).fetchall()
            events = connection.execute(
                "SELECT event_index, first_period, last_period, periods, shortfall_mwh FROM stress_event ORDER BY event_index"
            ).fetchall()
        self.assertEqual(json.loads(stored["energy_balance_boundary"]), SURPLUS)
        self.assertEqual(json.loads(stored["energy_balance_rule_set"]), "native-doctoral-thesis-v1")
        self.assertEqual([row[4] for row in booked], [0, 1, 1, 0, 1])
        self.assertEqual([row[3] for row in booked], [0.0] * 5)  # A2: unserved closes the account
        self.assertEqual(events, [(0, 1, 2, 2, 6.0), (1, 4, 4, 1, 1.0)])
        year = metadata["energy_balance"]["by_year"][0]
        self.assertEqual((year["stress_periods"], year["stress_event_count"], year["shortfall_mwh"]), (3, 2, 7.0))
        self.assertEqual(metadata["rows"]["stress_event"], 2)
        validation = validate_market_ledger_file(self.path)
        self.assertIs(validation["physically_consistent"], False)
        self.assertEqual(validation["physically_inconsistent_periods"], 3)

    def test_self_report_inconsistent_with_the_boundary_raises(self):
        ledger = self._ledger()
        ledger.record_balance_terms(BalanceTermsRow(2025, 0, 2.0, 0.0))
        with self.assertRaisesRegex(InvariantError, "GF_LEDGER_RESIDUAL_SELF_INCONSISTENT"):
            # Retained-boundary raw (0 - 2 = -2 is what surplus node gives 0 for).
            ledger.record_period(_row(2025, 0, supply=10.0, demand=10.0, charge=2.0))
        ledger.close_unsealed()

    def test_adjustment_above_the_noise_cap_raises(self):
        ledger = self._ledger()
        ledger.record_balance_terms(BalanceTermsRow(2025, 0, 0.0, 0.0))
        with self.assertRaisesRegex(InvariantError, "GF_COMPAT_ADJUSTMENT_ABOVE_CAP"):
            ledger.record_period(_row(2025, 0, supply=7.0, demand=10.0, adjustment=3.0))
        ledger.close_unsealed()

    def test_strict_mode_raises_on_a_physical_imbalance(self):
        ledger = self._ledger(strict=True)
        ledger.record_balance_terms(BalanceTermsRow(2025, 0, 0.0, 0.0))
        with self.assertRaisesRegex(InvariantError, "GF_ENERGY_BALANCE_STRICT"):
            ledger.record_period(_row(2025, 0, supply=7.0, demand=10.0))
        ledger.close_unsealed()

    def test_missing_terms_and_changed_boundary_fail_closed(self):
        ledger = self._ledger()
        with self.assertRaisesRegex(InvariantError, "GF_LEDGER_BALANCE_TERMS_MISSING"):
            ledger.record_period(_row(2025, 0, supply=10.0, demand=10.0))
        with self.assertRaisesRegex(InvariantError, "GF_LEDGER_BOUNDARY_CHANGED"):
            ledger.declare_balance_boundary(contract.FULL_NODE_V1)
        with self.assertRaisesRegex(ValueError, "GF_LEDGER_BOUNDARY_UNKNOWN"):
            ledger.declare_balance_boundary(contract.RETAINED_DEMAND_SERVING_V1)
        ledger.close_unsealed()

    def test_yearly_instances_on_one_file_summarise_every_year(self):
        # The default PSM opens a new ledger instance on the same file each year.
        for year, short in ((2025, 2.0), (2026, 0.0)):
            ledger = self._ledger()
            ledger.record_balance_terms(BalanceTermsRow(year, 0, 0.0, 0.0))
            ledger.record_period(_row(year, 0, supply=10.0 - short, demand=10.0))
            metadata = ledger.close()
        years = {row["year"]: row for row in metadata["energy_balance"]["by_year"]}
        self.assertEqual(set(years), {2025, 2026})
        self.assertEqual((years[2025]["stress_event_count"], years[2026]["stress_event_count"]), (1, 0))
        with self.assertRaisesRegex(InvariantError, "GF_LEDGER_BOUNDARY_CHANGED"):
            other = create_market_ledger(self.path, "summary")
            try:
                other.declare_balance_boundary(contract.FULL_NODE_V1)
            finally:
                other.close_unsealed()

    def test_undeclared_ledgers_keep_the_legacy_closure_rule(self):
        ledger = create_market_ledger(self.path, "summary")
        with self.assertRaisesRegex(InvariantError, "Market energy balance failed"):
            ledger.record_period(_row(2025, 0, supply=7.0, demand=10.0))
        ledger.close_unsealed()
        other = Path(self._tmp.name) / "other.sqlite"
        ledger = create_market_ledger(other, "summary")
        ledger.record_period(_row(2025, 0, supply=7.0, demand=10.0, adjustment=3.0))
        metadata = ledger.close()
        self.assertNotIn("energy_balance", metadata)
        self.assertIsNone(validate_market_ledger_file(other)["physically_consistent"])


class ContractBookingTests(unittest.TestCase):
    def test_capped_adjustment_absorbs_noise_only(self):
        self.assertEqual(contract.capped_adjustment(5e-7, contract.EXACT_ARITHMETIC, 10.0), -5e-7)
        self.assertEqual(contract.capped_adjustment(1e-10, contract.EXACT_ARITHMETIC, 10.0), 0.0)
        self.assertEqual(contract.capped_adjustment(-18.829, contract.EXACT_ARITHMETIC, 13.8), 0.0)

    def test_rule_sets_declare_their_boundary(self):
        from gridform_core.builtin.scheme_c_1000twh import native_market_rules as rules

        self.assertEqual(rules.DOCTORAL.rule_set_id, contract.NATIVE_DOCTORAL_RULE_SET)
        self.assertEqual(contract.boundary_for_rule_set(rules.DOCTORAL.rule_set_id), SURPLUS)
        self.assertEqual(contract.boundary_for_rule_set(rules.CORRECTED.rule_set_id), contract.NATIVE_CORRECTED_FULL_NODE_V1)
        self.assertIsNone(contract.boundary_for_rule_set("native-partial-0123456789ab"))
        self.assertIsNone(contract.boundary_for_rule_set(None))
        entry = contract.registry_lookup("value-bid-at-cost-psm", "5.2.0", contract.NATIVE_DOCTORAL_RULE_SET)
        self.assertEqual(entry.boundary_id, SURPLUS)

    def test_booking_closes_a_shortfall_and_keeps_a_double_count(self):
        # Overshoot period 0: D 13.829, S 0, C 5 -> shortfall 18.829 booked as unserved.
        short = contract.PeriodFlows(2025, 0, 0.0, 0.0, 13.829, 5.0, 0.0, 0.0, u_out_mwh=0.0, w_in_mwh=0.0)
        booking = contract.balance_booking(SURPLUS, short)
        self.assertAlmostEqual(booking.raw_residual_mwh, -18.829)
        self.assertAlmostEqual(booking.unserved_mwh, 18.829)
        self.assertAlmostEqual(booking.hidden_unserved_mwh, 18.829)
        self.assertAlmostEqual(booking.closing_residual_mwh, 0.0)
        self.assertTrue(booking.stress)
        # nuclear_balancing period 0: +3.000 double count stays in the account.
        double = contract.PeriodFlows(2025, 0, 17.5, 0.0, 13.829, 0.671, 0.0, 0.0, u_out_mwh=0.0, w_in_mwh=0.0)
        booking = contract.balance_booking(SURPLUS, double)
        self.assertAlmostEqual(booking.closing_residual_mwh, 3.0)
        self.assertFalse(booking.stress)
        # Recorded blackout is part of the shortfall, not on top of it.
        blackout = contract.PeriodFlows(2025, 0, 8.0, 2.0, 10.0, 0.0, 0.0, 0.0, u_out_mwh=0.0, w_in_mwh=0.0)
        booking = contract.balance_booking(SURPLUS, blackout)
        self.assertEqual((booking.raw_residual_mwh, booking.unserved_mwh, booking.hidden_unserved_mwh), (0.0, 2.0, 0.0))
        self.assertEqual(booking.closing_residual_mwh, 0.0)


if __name__ == "__main__":
    unittest.main()
