from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gridform_core.builtin.scheme_c_1000twh.runtime_compat.modular_simulation_model import (
    Battery,
    ExpensiverenewableGenerator,
    GasGenerator,
    ahead_market_bidding,
)
from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM
from gridform_core.market_ledger import SQLiteMarketLedger, set_active_market_ledger
from gridform_core.market_replay import query_auction_view


class Connection:
    def __init__(self, name: str): self.name = name


class NamedBattery:
    def __init__(self, name: str): self.name = name


NamedBattery.__name__ = "Battery"


class SolarGenerator:
    def __init__(self, name: str): self.name = name


class ForceMarketReplayRuntimeTests(unittest.TestCase):
    def test_actual_force_ahead_declaration_replays_in_executed_price_order(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SIMULATION_YEAR": "2025", "PHYSICAL_PERIOD_HOURS": "0.5"},
        ):
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            set_active_market_ledger(ledger)
            try:
                wind = ExpensiverenewableGenerator(
                    "offshore_wind", 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 1.0, 0.0, 0.0,
                )
                wind.capacity_limit = 8.0
                gas = GasGenerator(
                    "ccgt", 50.0, 0.0, 0.0, 12.0, 12.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                )
                battery = Battery(
                    "battery", 8.0, 4.0, 0.0, 0.0, 0.95, 0.9, 0.0,
                    capital_cost=100_000.0, battery_type="0.5c",
                )
                battery.prepare_operating_year(2025)
                battery.set_stored_energy_var(-1, 4.0)
                arrays = [defaultdict(float) for _ in range(4)]
                ahead_market_bidding(
                    [wind, gas], [battery], 10.0, 0, [],
                    arrays[0], arrays[1], arrays[2], arrays[3], 1.0,
                    retain_storage_tranche_history=False,
                )
            finally:
                ledger.close()
                set_active_market_ledger(None)
            replay = query_auction_view(database, year=2025, period=0, stage="ahead")
        prices = [float(row["offer_price_gbp_per_mwh"]) for row in replay["offers"]]
        self.assertEqual(prices, sorted(prices))
        self.assertTrue(replay["declared_before_clearing"])
        self.assertGreater(len(replay["offers"]), 1)
        self.assertEqual(replay["requirement_mwh"], 5.0)

    def test_native_result_bridge_writes_one_final_physical_layer(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            solar = SolarGenerator("solar")
            battery = NamedBattery("battery")
            connection = Connection("interconnector")
            named = SimpleNamespace(
                dispatch_by_period=[[(solar, 4.0), (battery, 2.0), (connection, 1.0)]],
                storage_charge_by_period=[3.0],
                flexible_demand_mwh_by_period=[1.0],
                interconnector_exports_mwh_by_period=[.5],
                curtailed_electricity_mwh_by_period=[2.0],
                excess_electricity_mwh_by_period=[1.5],
                blackout_mwh_by_period=[.25],
            )
            SchemeCNativePSM._record_physical_dispatch(
                ledger, named, year=2025, period_hours=.5,
                forecast=[12.0], real=[10.0],
            )
            ledger.close()
            with closing(sqlite3.connect(database)) as connection_db:
                rows = connection_db.execute(
                    "SELECT asset_id, flow_type, energy_mwh FROM physical_dispatch ORDER BY asset_id"
                ).fetchall()
        keyed = {(asset, flow): energy for asset, flow, energy in rows}
        self.assertEqual(keyed[("solar", "generation")], 2.0)
        self.assertEqual(keyed[("battery", "storage_discharge")], 1.0)
        self.assertEqual(keyed[("interconnector", "import")], .5)
        self.assertEqual(keyed[("__storage_charge_unallocated__", "storage_charge")], 1.5)
        self.assertEqual(keyed[("__prebalancing_excess__", "excess_generation")], .75)
        self.assertNotIn(("__compatibility_adjustment__", "generation"), keyed)


if __name__ == "__main__":
    unittest.main()
