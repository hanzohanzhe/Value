"""Four-role finding M-D1: real storage offers in the market ledger (A16-1, Q12).

The default PSM booked a battery that discharged as one ``orders`` row with
offer price 0.0 (``accepted_non_generator_offer``) and did not book storage
offers that were not accepted.  The kernel now books every storage tranche
offer of the ahead and balancing stages in the accounting table
``storage_orders`` at its real price.  These tests take the view of a storage
cost module author: with their own bid formula plugged into the kernel, every
row of the table, accepted or not, must reconcile with the formula, with the
clearing declaration (``clearing_inputs``) and with the discharged energy.
Dispatch is unchanged (golden check: no trajectory column moves).
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh import native_storage_orders as storage_orders
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel
from gridform_core.market_ledger import (
    StorageOrderLedgerRow,
    create_market_ledger,
    set_active_market_ledger,
)

PERIOD_HOURS = 0.5
YEAR = 2025


class AuthorFormula:
    """A storage cost module author's bid: 12 GBP/MWh plus 3 GBP/MWh per dwell period."""

    prepared_year = None
    cycle_depreciation_gbp_per_mwh = 12.0
    holding_recovery_gbp_per_mwh_period = 3.0

    def __init__(self):
        self.sales = []

    def bid_price_gbp_per_mwh(self, dwell_periods):
        return 12.0 + 3.0 * max(float(dwell_periods), 0.0)

    def record_sale(self, delivered_mwh, dwell_periods):
        self.sales.append((delivered_mwh, dwell_periods))


def _battery():
    # pumped hydro: long duration, so the rated power never binds here; the
    # tiny self-discharge only trims the offered power.
    battery = kernel.Battery("store", 400, 0, 0, 0, 1.0, 1.0, 0, battery_type="pumped_hydro")
    battery.cost_recovery = AuthorFormula()
    battery.stored_energy = {2: 10.0, 3: 10.0, 4: 10.0}
    return battery


def _gas():
    return kernel.GasGenerator("gas", 50, 3, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0)


def _electrolyser():
    return kernel.Electrolyzer("off", 0, 0, .6, 0, 0, 0, 0)


def _clear_period(period=7, forecast=30.0, real=45.0, bidding_factor=1.0):
    """One ahead clearing and one balancing clearing of the retained kernel."""

    battery, gas = _battery(), _gas()
    planned = kernel.ahead_market_bidding(
        [gas], [battery], forecast, period, [], defaultdict(float), defaultdict(float),
        defaultdict(float), defaultdict(float), bidding_factor)
    ahead_offers = list(kernel._STORAGE_OFFERS.offers)
    kernel.balancing_market_bidding(
        [gas], period, real, forecast, planned[0], planned[6], defaultdict(float),
        defaultdict(float), defaultdict(float), planned[10], defaultdict(float), [],
        planned[12], planned[13], _electrolyser(), planned[15], [battery], bidding_factor)
    return battery, ahead_offers


class _Environment(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in ("PHYSICAL_PERIOD_HOURS", "SIMULATION_YEAR")}
        os.environ["PHYSICAL_PERIOD_HOURS"] = str(PERIOD_HOURS)
        os.environ["SIMULATION_YEAR"] = str(YEAR)
        kernel._P06_STATE.reset()

    def tearDown(self):
        set_active_market_ledger(None)
        kernel._P06_STATE.reset()
        kernel._STORAGE_OFFERS.reset()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class StorageOfferTraceTests(_Environment):
    def test_every_offer_is_booked_at_the_module_formula(self):
        period, bidding_factor = 7, 1.25
        battery, ahead_offers = _clear_period(period=period, bidding_factor=bidding_factor)
        rows = kernel._STORAGE_OFFERS.rows(YEAR, period, PERIOD_HOURS, StorageOrderLedgerRow)
        self.assertEqual([offer.stage for offer in ahead_offers], ["ahead"] * 3)
        self.assertEqual({row.stage for row in rows}, {"ahead_offer", "balancing_offer"})
        for row in rows:
            with self.subTest(order=row.order_id):
                self.assertEqual(row.dwell_periods, period - row.charge_period)
                self.assertEqual(
                    row.offer_price_gbp_per_mwh,
                    (12.0 + 3.0 * row.dwell_periods) * bidding_factor,
                )
                self.assertEqual(row.bidding_factor, bidding_factor)
                self.assertAlmostEqual(row.accepted_offer_value_gbp,
                                       row.offer_price_gbp_per_mwh * row.accepted_mwh, places=12)
                self.assertLessEqual(row.accepted_mwh, row.offered_mwh + 1e-12)

        ahead = {row.charge_period: row for row in rows if row.stage == "ahead_offer"}
        # Merit order: the newest tranche is the cheapest.  Demand 30 MW: the
        # cp=4 tranche (~20 MW) clears, cp=3 fills the rest, cp=2 is not reached.
        self.assertEqual((ahead[4].status, ahead[4].reason_code), ("accepted", "cleared"))
        self.assertEqual((ahead[3].status, ahead[3].reason_code), ("partially_accepted", "demand_filled"))
        self.assertEqual((ahead[2].status, ahead[2].reason_code), ("rejected", "merit_order_not_reached"))
        self.assertEqual(ahead[2].accepted_mwh, 0.0)
        self.assertAlmostEqual(ahead[4].accepted_mwh + ahead[3].accepted_mwh, 30.0 * PERIOD_HOURS, places=9)

        balancing = [row for row in rows if row.stage == "balancing_offer"]
        self.assertTrue(balancing)
        self.assertTrue(all(row.dwell_periods >= 2 for row in balancing))
        self.assertAlmostEqual(sum(row.accepted_mwh for row in balancing), 15.0 * PERIOD_HOURS, places=9)

        # The battery's own sales book is what the offers delivered.  Since
        # R4-1 (A26) both rule sets record a period's sales when the loop
        # closes the store's net position.
        battery.close_period(period)
        delivered = sum(mwh for mwh, _ in battery.cost_recovery.sales)
        self.assertAlmostEqual(delivered, sum(row.accepted_mwh for row in rows), places=12)

    def test_trace_is_read_only(self):
        # Same clearing with the trace hooks switched off: identical outcome.
        traced, _ = _clear_period()
        trace = kernel._STORAGE_OFFERS
        trace.reset()
        trace.declare = lambda *args, **kwargs: None
        trace.deliver = lambda *args, **kwargs: None
        try:
            untraced, _ = _clear_period()
        finally:
            del trace.declare, trace.deliver
        self.assertEqual(trace.offers, [])
        self.assertEqual(traced.stored_energy, untraced.stored_energy)
        self.assertEqual(traced.cost_recovery.sales, untraced.cost_recovery.sales)

    def test_rows_of_another_period_are_empty(self):
        _clear_period(period=7)
        self.assertEqual(kernel._STORAGE_OFFERS.rows(YEAR, 8, PERIOD_HOURS, StorageOrderLedgerRow), [])

    def test_unrecognised_item_is_ignored(self):
        trace = storage_orders.StorageOfferTrace()
        trace.declare("ahead", 1, [], bidding_factor=1.0, asset_name=str)
        trace.deliver(["not", "an", "offer", 1], 5.0)
        self.assertEqual(trace.rows(YEAR, 1, PERIOD_HOURS, StorageOrderLedgerRow), [])


class StorageOrdersLedgerTests(_Environment):
    def test_orders_table_reconciles_with_the_clearing_declaration(self):
        period = 7
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market" / "market.sqlite"
            ledger = create_market_ledger(path, "full", semantic_metadata={"period_hours": PERIOD_HOURS})
            set_active_market_ledger(ledger)
            _clear_period(period=period)
            ledger.record_storage_orders(
                kernel._STORAGE_OFFERS.rows(YEAR, period, PERIOD_HOURS, StorageOrderLedgerRow))
            set_active_market_ledger(None)
            metadata = ledger.close()
            with closing(sqlite3.connect(path)) as connection:
                rows = connection.execute(
                    "SELECT clearing_offer_id, stage, offer_price_gbp_per_mwh, offered_mwh, charge_period, "
                    "status FROM storage_orders ORDER BY order_id"
                ).fetchall()
                declared = {}
                for (payload,) in connection.execute("SELECT payload_json FROM clearing_inputs"):
                    for offer in json.loads(payload)["payload"].get("offers", []):
                        declared[offer["offer_id"]] = offer
        self.assertEqual(metadata["rows"]["storage_orders"], len(rows))
        self.assertIn("rejected", {row[5] for row in rows})
        storage_declared = {key for key, offer in declared.items()
                            if offer["resource_kind"] == "storage_discharge"}
        self.assertEqual({row[0] for row in rows}, storage_declared)
        for offer_id, stage, price, offered_mwh, charge_period, _status in rows:
            offer = declared[offer_id]
            self.assertEqual(stage, f"{offer_id.split(':', 1)[0]}_offer")
            self.assertEqual(price, offer["offer_price_gbp_per_mwh"])
            self.assertAlmostEqual(offered_mwh, offer["maximum_power_mw"] * PERIOD_HOURS, places=12)
            self.assertEqual(charge_period, offer["charge_period"])
            self.assertNotEqual(price, 0.0)

    def test_ledgers_without_storage_offers_keep_their_table_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market.sqlite"
            ledger = create_market_ledger(path, "full")
            ledger.record_storage_orders([])
            metadata = ledger.close()
            with closing(sqlite3.connect(path)) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("storage_orders", tables)
        self.assertNotIn("storage_orders", metadata["rows"])


class LiveKernelLoopTests(_Environment):
    """The live default-PSM loop on the 96-period synthetic scenario (doctoral rules)."""

    def test_live_loop_books_storage_orders_that_reconcile_with_dispatch(self):
        from tests import native_reproduction_harness as harness

        for variant in ("dynamic", "legacy_tariff"):
            with self.subTest(variant=variant):
                ledger = harness.run_case(variant, loop="live")["ledger"]
                rows = ledger.storage_orders
                self.assertTrue(rows)
                self.assertTrue({"accepted", "rejected"} <= {row["status"] for row in rows})
                offers: dict[tuple[int, str], float] = defaultdict(float)
                for row in rows:
                    self.assertGreaterEqual(row["dwell_periods"], 0)
                    self.assertAlmostEqual(row["accepted_offer_value_gbp"],
                                           row["offer_price_gbp_per_mwh"] * row["accepted_mwh"], places=9)
                    offers[(row["period"], row["asset_id"])] += row["accepted_mwh"]
                dispatched: dict[tuple[int, str], float] = defaultdict(float)
                for period_rows in ledger.orders:
                    for order in period_rows:
                        if order["stage"] == "final_dispatch" and order["asset_type"] == "Battery":
                            # The frozen battery row: price 0.0, not an offer.
                            self.assertEqual(order["offer_price_gbp_per_mwh"], 0.0)
                            dispatched[(order["period"], order["asset_id"])] += order["accepted_mwh"]
                # R4-1 (A26): the doctoral rule set nets a same-period
                # buy-back too, so the battery row (net) never exceeds the
                # offers' delivered energy (gross); without a buy-back they
                # are equal.
                bought = 0
                for key in set(offers) | set(dispatched):
                    self.assertLessEqual(dispatched.get(key, 0.0), offers.get(key, 0.0) + 1e-9, msg=str(key))
                    bought += dispatched.get(key, 0.0) < offers.get(key, 0.0) - 1e-9
                self.assertGreater(bought, 0)
                self.assertLess(bought, len(offers))


    def test_corrected_rules_book_offers_gross_of_the_buy_back(self):
        # Corrected rule set (one net position per period): a same-period
        # buy-back lowers the battery's net row, never the booked offers.
        from gridform_core.builtin.scheme_c_1000twh.native_market_rules import CORRECTED
        from tests import native_reproduction_harness as harness

        ledger = harness.run_case("dynamic", loop="live", runtime_attributes={"market_rules": CORRECTED})["ledger"]
        self.assertTrue(ledger.storage_orders)
        offers: dict[tuple[int, str], float] = defaultdict(float)
        for row in ledger.storage_orders:
            self.assertEqual(row["offer_price_gbp_per_mwh"] * row["accepted_mwh"], row["accepted_offer_value_gbp"])
            offers[(row["period"], row["asset_id"])] += row["accepted_mwh"]
        for period_rows in ledger.orders:
            for order in period_rows:
                if order["stage"] == "final_dispatch" and order["asset_type"] == "Battery":
                    key = (order["period"], order["asset_id"])
                    self.assertLessEqual(order["accepted_mwh"], offers.get(key, 0.0) + 1e-9, msg=str(key))


if __name__ == "__main__":
    unittest.main()
