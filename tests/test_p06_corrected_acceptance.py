"""P0-6 acceptance on the real application path (M4 gate 2, corrected profile).

The P0-4 VALUE 101 variants (``tests/p04_variants.py``) are run with the
Study's own methodology profile, i.e. the corrected market rule set, one
subprocess each.  Expected: every physically closing variant passes the
energy-balance oracle on ``native_corrected_full_node_v1`` with no
compatibility adjustment and raw residuals <= 1e-6, the DEV-BAL-04 double
count of ``nuclear_balancing`` is gone, the storage invariants hold, and the
``overshoot`` forecast (decision A2: realisation rule unchanged) still fails
with an exact shortfall booked as stress.
"""

from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core import energy_balance_contract as contract
from gridform_core import energy_balance_oracle as oracle
from tests import p04_variants

RUNS = (
    ("baseline", "value_101_day"),
    ("baseline", "two_year_smoke"),
    ("export", "value_101_day"),
    ("export_electrolyser", "value_101_day"),
    ("nuclear_curtail", "value_101_day"),
    ("nuclear_balancing", "value_101_day"),
    ("multi_battery", "value_101_day"),
    ("overshoot", "value_101_day"),
)
CLOSING = {run for run in RUNS if run[0] != "overshoot"}


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)


class CorrectedAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="value-p06-acceptance-")

        def one(run):
            name, mode = run
            output = Path(cls._tmp.name) / f"{name}-{mode}"
            p04_variants.run_variant(name, output, mode=mode, rule_set="profile")
            return run, output

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            cls.outputs = dict(pool.map(one, RUNS))
        cls.ledgers = {run: output / "market" / "market.sqlite" for run, output in cls.outputs.items()}
        cls.reports = {run: oracle.evaluate_ledger(path) for run, path in cls.ledgers.items()}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_corrected_boundary_is_declared(self):
        for run, report in self.reports.items():
            with self.subTest(run=run):
                self.assertEqual(report["boundary"]["source"], "metadata")
                self.assertEqual(report["boundary"]["boundary_id"], contract.NATIVE_CORRECTED_FULL_NODE_V1)
                self.assertEqual(report["boundary"]["rule_set"], contract.NATIVE_CORRECTED_RULE_SET)
                self.assertEqual(report["metrics"]["reported"]["adjusted_periods"], 0)
                self.assertEqual(report["metrics"]["self_report"]["inconsistent_periods"], 0)

    def test_closing_variants_pass_the_oracle(self):
        for run in sorted(CLOSING):
            with self.subTest(run=run), closing(_ro(self.ledgers[run])) as connection:
                self.assertEqual(self.reports[run]["status"], "passed", self.reports[run]["reasons"])
                worst = connection.execute(
                    "SELECT MAX(ABS(raw_energy_balance_residual_mwh)), SUM(compatibility_adjustment_mwh != 0) "
                    "FROM period_summary"
                ).fetchone()
                self.assertLessEqual(worst[0], 1e-6)
                self.assertEqual(worst[1], 0)

    def test_nuclear_balancing_double_count_is_gone(self):
        report = self.reports[("nuclear_balancing", "value_101_day")]
        self.assertEqual(report["status"], "passed")
        self.assertNotIn(oracle.R_BOUNDARY_RESIDUAL, report["reasons"])

    def test_overshoot_keeps_its_a2_shortfall(self):
        run = ("overshoot", "value_101_day")
        self.assertEqual(self.reports[run]["status"], "failed")
        with closing(_ro(self.ledgers[run])) as connection:
            shortfall, stress, closing_residual = connection.execute(
                "SELECT SUM(shortfall_mwh), SUM(stress_flag), MAX(ABS(closing_residual_mwh)) "
                "FROM balance_boundary_period"
            ).fetchone()
            raw = connection.execute("SELECT MAX(raw_energy_balance_residual_mwh) FROM period_summary").fetchone()[0]
        self.assertGreater(shortfall, 0.0)
        self.assertGreater(stress, 0)
        self.assertLessEqual(closing_residual, 1e-9)  # unserved closes the account
        self.assertLessEqual(raw, 1e-9)  # a shortfall, never a surplus

    def test_storage_invariants(self):
        for run in RUNS:
            with self.subTest(run=run), closing(_ro(self.ledgers[run])) as connection:
                hours = 0.5
                over_power = connection.execute(
                    "SELECT COUNT(*) FROM storage_state WHERE discharge_mwh > power_capacity_mw * ? + 1e-6",
                    (hours,),
                ).fetchone()[0]
                both = connection.execute(
                    "SELECT COUNT(*) FROM storage_energy_audit WHERE charge_input_mwh > 1e-6 AND discharge_output_mwh > 1e-6"
                ).fetchone()[0]
                soc = connection.execute(
                    "SELECT COUNT(*) FROM storage_state WHERE state_of_charge_mwh < -1e-6 "
                    "OR state_of_charge_mwh > energy_capacity_mwh + 1e-6"
                ).fetchone()[0]
                identity = connection.execute(
                    "SELECT MAX(ABS(identity_residual_mwh)) FROM storage_energy_audit"
                ).fetchone()[0]
                self.assertEqual((over_power, both, soc), (0, 0, 0))
                self.assertLessEqual(identity, 1e-9)

    def test_vre_columns_follow_the_corrected_semantics(self):
        for run in RUNS:
            with self.subTest(run=run), closing(_ro(self.ledgers[run])) as connection:
                gap = connection.execute(
                    "SELECT MAX(ABS(vre_available_mwh - vre_accepted_mwh - curtailed_mwh)), MIN(curtailed_mwh) "
                    "FROM period_summary"
                ).fetchone()
                self.assertLessEqual(gap[0], 1e-9)
                self.assertGreaterEqual(gap[1], -1e-9)
                semantics = json.loads(connection.execute(
                    "SELECT value FROM metadata WHERE key='curtailment_semantics'"
                ).fetchone()[0])
                self.assertEqual(semantics, "vre_available_minus_gross_output")

    def test_two_year_smoke_validation_reports_a_closed_balance(self):
        output = self.outputs[("baseline", "two_year_smoke")]
        validation = json.loads((output / "validation" / "scientific-validation.json").read_text(encoding="utf-8"))
        self.assertEqual(validation["energy_balance_status"], "passed")
        self.assertEqual(validation["energy_balance"]["compatibility_adjustment_periods"], 0)


if __name__ == "__main__":
    unittest.main()
