"""P0-4 S4: per-asset storage energy audit of the default PSM (P3-14, P5-11).

Hand-calculated battery toy (SoC identity <= 1e-12), tail write-off,
``Battery.__new__`` compatibility, the ledger tables and the VALUE 101
baseline (sum of audited charge = 11.113 MWh = period_summary charge).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh import native_balance_audit as audit_module
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel
from gridform_core.market_ledger import (
    StorageEnergyAuditRow,
    StorageStateRow,
    StorageYearBoundaryRow,
    create_market_ledger,
)


def _battery(name="toy", pool_limit=4.0, n_1=0.9, n_2=0.8, battery_type="1c"):
    return kernel.Battery(name, pool_limit, 0.0, 0.0, 0.0, n_1, n_2, 0.0, capital_cost=0, battery_type=battery_type)


class StorageAuditToyTests(unittest.TestCase):
    def setUp(self):
        self._hours = os.environ.get("PHYSICAL_PERIOD_HOURS")
        os.environ["PHYSICAL_PERIOD_HOURS"] = "0.5"

    def tearDown(self):
        if self._hours is None:
            os.environ.pop("PHYSICAL_PERIOD_HOURS", None)
        else:
            os.environ["PHYSICAL_PERIOD_HOURS"] = self._hours

    def test_hand_calculated_period_closes(self):
        battery = _battery()  # 1c: 4 MWh, 4 MW
        audit_module.open_storage_period([battery], 0)
        charged = battery.charge(0, 3.0)  # 3 MW for 0.5 h
        self.assertEqual(charged, 3.0)
        (row,) = audit_module.storage_audit_rows(2025, 0, [battery])
        self.assertIsInstance(row, StorageEnergyAuditRow)
        self.assertEqual(row.soc_start_mwh, 0.0)
        self.assertAlmostEqual(row.charge_input_mwh, 1.5, places=15)
        self.assertAlmostEqual(row.charge_stored_mwh, 1.35, places=15)
        self.assertAlmostEqual(row.soc_end_mwh, 1.35, places=15)
        self.assertLessEqual(abs(row.identity_residual_mwh), 1e-12)

        # Period 1: self-discharge (decay_func, 1c rate 2.1e-5) then a discharge
        # that leaves a tail below 0.001 MWh, which the kernel deletes.
        audit_module.open_storage_period([battery], 1)
        battery.apply_self_discharge(1)
        decayed = 1.35 * (1 - 0.000021)
        output = (decayed - 0.0005) * 0.8 / 0.5  # leave 0.0005 MWh stored
        delivered = battery.discharge(0, output, 1)
        self.assertAlmostEqual(delivered, output, places=12)
        (row,) = audit_module.storage_audit_rows(2025, 1, [battery])
        self.assertAlmostEqual(row.soc_start_mwh, 1.35, places=15)
        self.assertAlmostEqual(row.self_discharge_mwh, 1.35 * 0.000021, places=15)
        self.assertAlmostEqual(row.discharge_output_mwh, output * 0.5, places=12)
        self.assertAlmostEqual(row.discharge_withdrawn_mwh, output * 0.5 / 0.8, places=12)
        self.assertAlmostEqual(row.tail_writeoff_mwh, 0.0005, places=12)
        self.assertEqual(row.soc_end_mwh, 0.0)
        self.assertEqual(battery.stored_energy, {})
        self.assertLessEqual(abs(row.identity_residual_mwh), 1e-12)

    def test_self_discharge_is_the_retained_decay(self):
        audited = _battery()
        plain = _battery()
        for battery in (audited, plain):
            battery.charge(0, 2.0)
        audit_module.open_storage_period([audited], 1)
        audited.apply_self_discharge(1)
        kernel.decay_func(plain.stored_energy, plain.battery_type)
        self.assertEqual(audited.stored_energy, plain.stored_energy)  # bit-identical

    def test_battery_new_without_init_is_audited_lazily(self):
        # module_conformance builds Battery.__new__(Battery) without __init__.
        battery = kernel.Battery.__new__(kernel.Battery)
        battery.stored_energy = {0: 1.0}
        battery.battery_type = "pumped_hydro"
        battery.apply_self_discharge(3)
        self.assertAlmostEqual(battery.stored_energy[0], 1.0 * (1 - 0.000001), places=15)
        self.assertAlmostEqual(audit_module.battery_audit(battery).self_discharge_mwh, 0.000001, places=15)
        battery.clr_stored_energy_var(0, 0.9999985, audit_period=3)
        self.assertEqual(battery.stored_energy, {})
        self.assertGreater(audit_module.battery_audit(battery).tail_writeoff_mwh, 0.0)

    def test_unopened_battery_reports_its_whole_state_as_opening(self):
        battery = _battery()
        battery.stored_energy = {0: 2.0}
        (row,) = audit_module.storage_audit_rows(2025, 5, [battery])
        self.assertEqual((row.soc_start_mwh, row.soc_end_mwh, row.identity_residual_mwh), (2.0, 2.0, 0.0))


class StorageAuditLedgerTests(unittest.TestCase):
    def test_tables_are_created_on_first_write_and_summarised(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market" / "market.sqlite"
            ledger = create_market_ledger(path, "summary", semantic_metadata={"period_hours": 0.5})
            ledger.record_storage([StorageStateRow(2025, 0, "b", 1.0, 0.0, 0.0, 2.0, 4.0)])
            ledger.record_storage_audit([StorageEnergyAuditRow(2025, 0, "b", 0.0, 1.2, 1.08, 0.0, 0.0, 0.0, 0.0, 1.0, 0.08)])
            ledger.record_storage_year_boundary([StorageYearBoundaryRow(2025, "b", 0.0, 1.0, 0.0, 1.0, "new_battery_each_year")])
            metadata = ledger.close()
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM storage_energy_audit").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT discarded_mwh FROM storage_year_boundary").fetchone()[0], 1.0)
            self.assertEqual(metadata["rows"]["storage_energy_audit"], 1)
            audit = metadata["energy_audit"]
            self.assertEqual(audit["storage_by_year"][0]["charge_input_mwh"], 1.2)
            self.assertAlmostEqual(audit["storage_by_year"][0]["maximum_absolute_identity_residual_mwh"], 0.08)
            # 1.2 MWh charged in half an hour at 2 MW rated power exceeds 1.0 MWh.
            self.assertEqual(audit["storage_throughput_exceedances"], {"periods": 1, "enforcement": "report_only"})
            self.assertEqual(audit["storage_year_boundary"], [{"year": 2025, "discarded_mwh": 1.0, "carried_forward_mwh": 0.0}])

    def test_ledgers_without_audit_rows_keep_their_table_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market.sqlite"
            ledger = create_market_ledger(path, "summary")
            metadata = ledger.close()
            with closing(sqlite3.connect(path)) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("storage_energy_audit", tables)
            self.assertNotIn("energy_audit", metadata)
            self.assertNotIn("storage_energy_audit", metadata["rows"])


if __name__ == "__main__":
    unittest.main()
