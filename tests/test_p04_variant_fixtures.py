"""P0-4 S1 integration: derived fixtures, per-table HEAD golden, oracle verdicts.

Runs the seven ``tests/p04_variants.py`` fixtures (value_101_day, one process
each), then

* compares every table and column of each ``market.sqlite`` with
  ``tests/fixtures/p04_trajectory_golden.json`` (shared golden digest; exact
  on the reference platform, ``%.9g`` hashes elsewhere);
* runs the read-only oracle and checks the M0 gate verdicts: overshoot and
  nuclear_balancing ``failed``, baseline/export/nuclear_curtail (and the other
  fixtures) ``not_evaluated``, nothing ``passed``, ledger sha256 unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core import energy_balance_contract as contract
from gridform_core import energy_balance_oracle as oracle
from scripts import p04_capture_trajectory_golden as golden
from tests import p04_variants

EXPECTED = {
    "baseline": oracle.NOT_EVALUATED,
    "overshoot": oracle.FAILED,
    "export": oracle.NOT_EVALUATED,
    "export_electrolyser": oracle.NOT_EVALUATED,
    "nuclear_curtail": oracle.NOT_EVALUATED,
    "nuclear_balancing": oracle.FAILED,
    "multi_battery": oracle.NOT_EVALUATED,
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class P04VariantFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="value-p04-variants-")
        cls.outputs = golden.run_variants(sorted(p04_variants.VARIANTS), Path(cls._tmp.name), workers=4)
        cls.ledgers = {name: output / "market" / "market.sqlite" for name, output in cls.outputs.items()}
        cls.sha_before = {name: _sha(path) for name, path in cls.ledgers.items()}
        cls.reports = {name: oracle.evaluate_ledger(path) for name, path in cls.ledgers.items()}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_variant_set_matches_plan(self):
        self.assertEqual(set(p04_variants.VARIANTS), set(EXPECTED))

    def test_per_table_golden_at_head(self):
        # Exact hashes on the reference platform, %.9g hashes elsewhere.
        fixture = json.loads(golden.FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema_version"], golden.SCHEMA_VERSION)
        self.assertEqual(set(fixture["variants"]), set(EXPECTED))
        for name, output in sorted(self.outputs.items()):
            with self.subTest(variant=name):
                expected = fixture["variants"][name]
                tables = {key.split("::", 1)[1].split(".", 1)[0] for key in expected["columns"]}
                self.assertIn("period_summary", tables)
                self.assertIn("storage_state", tables)
                self.assertEqual(golden.compare(expected, golden.digest_output(output)), [])

    def test_oracle_verdicts(self):
        statuses = {name: report["status"] for name, report in self.reports.items()}
        self.assertEqual(statuses, EXPECTED)
        self.assertNotIn(oracle.PASSED, statuses.values())
        for name, report in self.reports.items():
            with self.subTest(variant=name):
                self.assertEqual(report["boundary"]["source"], "registry")
                self.assertEqual(report["boundary"]["boundary_id"], "default_psm_surplus_node_v1")
                self.assertIn(oracle.R_LEGACY, report["reasons"])
                self.assertEqual(report["metrics"]["self_report"]["inconsistent_periods"], 0)

    def test_ledgers_are_never_modified(self):
        for name, path in self.ledgers.items():
            with self.subTest(variant=name):
                report = self.reports[name]
                self.assertEqual(report["ledger"]["sha256_before"], self.sha_before[name])
                self.assertEqual(report["ledger"]["sha256_after"], self.sha_before[name])
                self.assertEqual(_sha(path), self.sha_before[name])
                self.assertEqual(report["ledger"]["side_files"], {})

    def test_overshoot_is_the_release_r2_imbalance(self):
        report = self.reports["overshoot"]
        envelope = report["metrics"]["envelope"]
        self.assertEqual(envelope["lower_violations"], 48)
        self.assertEqual(envelope["upper_violations"], 0)
        # Period 0 by hand: D = 27.658155 MW * 0.5 h = 13.829, S = 0, C = 10 MW * 0.5 h = 5
        # -> full node -18.829, envelope lower bound -5, violation 13.829.
        uri = self.ledgers["overshoot"].resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            row = connection.execute(
                "SELECT real_demand_mwh, accepted_supply_mwh, storage_charge_mwh, export_mwh, "
                "flexible_demand_mwh, blackout_mwh, excess_mwh FROM period_summary WHERE period=0"
            ).fetchone()
        flows = contract.PeriodFlows(2025, 0, demand_mwh=row[0], supply_mwh=row[1], storage_charge_mwh=row[2],
                                     export_mwh=row[3], flexible_demand_mwh=row[4], blackout_mwh=row[5],
                                     excess_mwh=row[6])
        result = contract.check_envelope(contract.UNKNOWN_BOUNDARY, flows, contract.EXACT_ARITHMETIC)
        self.assertAlmostEqual(result.full_node_residual_mwh, -18.829, places=3)
        self.assertAlmostEqual(result.lower_violation_mwh, 13.829, places=3)
        self.assertEqual(result.upper_violation_mwh, 0.0)
        # A2 shortfall bounds for period 0: [D - S, D + C + min(XS + K, S) - S] = [13.829, 18.829]
        self.assertEqual(report["stress"]["periods"][0]["period"], 0)
        self.assertAlmostEqual(report["stress"]["periods"][0]["shortfall_lower_mwh"], 13.829, places=3)
        self.assertAlmostEqual(report["stress"]["periods"][0]["shortfall_upper_mwh"], 18.829, places=3)
        reported = report["metrics"]["reported"]
        self.assertEqual(reported["adjusted_periods"], 48)
        # Sum |adj| = 810.546 MWh exceeds the day's demand of 775.491 MWh.
        self.assertAlmostEqual(report["metrics"]["sum_demand_mwh"], 775.491, places=3)
        self.assertAlmostEqual(reported["sum_abs_adjustment_mwh"], 810.546, places=3)
        self.assertGreater(reported["sum_abs_adjustment_mwh"], report["metrics"]["sum_demand_mwh"])
        stress = report["stress"]
        self.assertEqual((stress["stress_periods"], stress["event_count"]), (48, 1))
        self.assertEqual(stress["events"][0]["first_period"], 0)
        self.assertEqual(stress["events"][0]["last_period"], 47)
        self.assertEqual(stress["recorded_unserved_mwh"], 0.0)
        # Lower bound: sum(D - S) = 775.491 - 204.945.  Upper bound: S <= K in every period,
        # so D + C + min(K, S) - S = D + C and the day sums to sum(D) + sum(C).
        self.assertAlmostEqual(stress["shortfall_lower_mwh"], 570.546, places=3)
        self.assertAlmostEqual(
            stress["shortfall_upper_mwh"],
            report["metrics"]["sum_demand_mwh"] + report["metrics"]["sum_storage_charge_mwh"], places=6,
        )

    def test_nuclear_balancing_double_count_breaks_the_upper_envelope(self):
        report = self.reports["nuclear_balancing"]
        envelope = report["metrics"]["envelope"]
        self.assertEqual(envelope["lower_violations"], 0)
        # DEV-BAL-04 (review pack_nucbal): 29 MW nuclear = 14.5 MWh, forecast 6 MW = 3.0 MWh
        # below real demand.  The balancing branch adds the 3.0 MWh balancing volume to the
        # in-dispatch nuclear output again, so nuclear is recorded as 17.5 instead of 14.5.
        # Period 0 by hand: S = 17.5, D = 13.829, C = 0.671 (the real surplus 14.5 - 13.829
        # charges the battery), XS = K = 0 -> full node = 17.5 - 13.829 - 0.671 = +3.000 with
        # an upper envelope bound of 0.
        uri = self.ledgers["nuclear_balancing"].resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            row = connection.execute(
                "SELECT real_demand_mwh, accepted_supply_mwh, storage_charge_mwh, export_mwh, "
                "flexible_demand_mwh, blackout_mwh, excess_mwh, curtailed_mwh FROM period_summary WHERE period=0"
            ).fetchone()
            nuclear = connection.execute(
                "SELECT SUM(energy_mwh) FROM physical_dispatch WHERE period=0 AND technology='nuclear' "
                "AND flow_type='generation'"
            ).fetchone()[0]
        self.assertAlmostEqual(nuclear, 17.5, places=9)
        self.assertAlmostEqual(row[0] + row[2], 14.5, places=9)
        flows = contract.PeriodFlows(2025, 0, demand_mwh=row[0], supply_mwh=row[1], storage_charge_mwh=row[2],
                                     export_mwh=row[3], flexible_demand_mwh=row[4], blackout_mwh=row[5],
                                     excess_mwh=row[6], curtailed_mwh=row[7])
        result = contract.check_envelope(contract.UNKNOWN_BOUNDARY, flows, contract.EXACT_ARITHMETIC)
        self.assertAlmostEqual(result.full_node_residual_mwh, 3.0, places=9)
        self.assertAlmostEqual(result.upper_violation_mwh, 3.0, places=9)
        # Wherever the nuclear surplus covers the balancing volume the violation is exactly 3.0.
        self.assertEqual(envelope["upper_violations"], 35)
        self.assertAlmostEqual(envelope["max_upper_violation_mwh"], 3.0, places=9)
        self.assertEqual(report["metrics"]["reported"]["adjusted_periods"], 35)
        # A double count is an excess, not a shortfall: no certain stress period.
        self.assertEqual(report["stress"]["stress_periods"], 0)

    def test_closing_fixtures_exercise_their_flows(self):
        metrics = {name: report["metrics"] for name, report in self.reports.items()}
        self.assertAlmostEqual(metrics["baseline"]["sum_storage_charge_mwh"], 11.113, places=3)
        self.assertGreater(metrics["export"]["sum_export_mwh"], 0.0)
        self.assertGreater(metrics["export_electrolyser"]["sum_export_mwh"], 0.0)
        self.assertGreater(metrics["export_electrolyser"]["sum_flexible_demand_mwh"], 0.0)
        self.assertGreater(metrics["nuclear_curtail"]["sum_excess_mwh"], 0.0)
        for name in ("baseline", "export", "export_electrolyser", "nuclear_curtail", "multi_battery"):
            with self.subTest(variant=name):
                self.assertEqual(metrics[name]["envelope"]["lower_violations"], 0)
                self.assertEqual(metrics[name]["envelope"]["upper_violations"], 0)
                self.assertEqual(self.reports[name]["stress"]["stress_periods"], 0)

    def test_cli_exit_code_on_a_real_ledger(self):
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "gridform_core.energy_balance_oracle",
             str(self.outputs["overshoot"]), "--quiet"],
            cwd=str(golden.ROOT), capture_output=True, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertTrue(completed.stdout.startswith("failed GF_ENERGY_BALANCE_ENVELOPE_VIOLATED"))


if __name__ == "__main__":
    unittest.main()
