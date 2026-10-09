"""P0-4 S1 integration: derived fixtures, per-table HEAD golden, oracle verdicts.

Runs the seven ``tests/p04_variants.py`` fixtures (value_101_day, one process
each), then

* compares every table and column of each ``market.sqlite`` with
  ``tests/fixtures/p04_trajectory_golden.json`` (shared golden digest; exact
  on the reference platform, ``%.9g`` hashes elsewhere);
* runs the read-only oracle and checks the M0 gate verdicts: overshoot and
  nuclear_balancing ``failed``, baseline/export/nuclear_curtail (and the other
  fixtures) ``not_evaluated``, nothing ``passed``, ledger sha256 unchanged.

R4-1 (DECISIONS A26) corrected three thesis-kernel errors in both profiles:
the fixture was re-captured once (scripts/p04_capture_trajectory_golden.py),
nuclear_balancing no longer counts the must-run surplus twice (it passes),
and the overshoot day's hidden shortage fell from 810.546 to 772.012 MWh.
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

# Since P0-4 S6 the kernel declares default_psm_surplus_node_v1 (doctoral
# rule set) and records the surplus routing, so physically closing fixtures
# pass and the two defective ones fail on the declared boundary.
EXPECTED = {
    "baseline": oracle.PASSED,
    "overshoot": oracle.FAILED,
    "export": oracle.PASSED,
    "export_electrolyser": oracle.PASSED,
    "nuclear_curtail": oracle.PASSED,
    # R4-1 (A26, DEV-BAL-04 corrected): was FAILED (+3.000 MWh per period).
    "nuclear_balancing": oracle.PASSED,
    "multi_battery": oracle.PASSED,
}


# P0-4 S4-S6: tables that later steps add (accounting zone, never trajectory)
# and existing accounting columns they revise.
P04_ADDED_TABLES = {"storage_energy_audit", "storage_year_boundary", "surplus_routing"}
P04_ADDED_TABLES |= {"balance_boundary_period", "stress_event"}
# Four-role M-D1 (A16-1, Q12 accounting): the real storage offers.
P04_ADDED_TABLES |= {"storage_orders"}
P04_REVISED_COLUMNS: set[str] = {
    "period_summary.raw_energy_balance_residual_mwh",
    "period_summary.compatibility_adjustment_mwh",
    "period_summary.energy_balance_residual_mwh",
    "physical_dispatch.balance_component_mwh",
    "metadata.#rows", "metadata.key", "metadata.value",
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
        # Exact hashes on the reference platform, %.9g hashes elsewhere.  The
        # fixture is the M0 HEAD capture; P0-4 S4-S6 may only add or revise
        # accounting-zone columns of the tables they own (no trajectory change).
        fixture = json.loads(golden.FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema_version"], golden.SCHEMA_VERSION)
        self.assertEqual(set(fixture["variants"]), set(EXPECTED))
        for name, output in sorted(self.outputs.items()):
            with self.subTest(variant=name):
                expected = fixture["variants"][name]
                tables = {key.split("::", 1)[1].split(".", 1)[0] for key in expected["columns"]}
                self.assertIn("period_summary", tables)
                self.assertIn("storage_state", tables)
                differences = golden.compare(expected, golden.digest_output(output))
                self.assertEqual([item for item in differences if item["zone"] == "trajectory"], [])
                outside = [
                    item for item in differences
                    if item["key"].split("::", 1)[1] not in P04_REVISED_COLUMNS
                    and item["key"].split("::", 1)[1].split(".", 1)[0] not in P04_ADDED_TABLES
                ]
                self.assertEqual(outside, [])
                for item in differences:
                    if item["key"].split("::", 1)[1].split(".", 1)[0] in P04_ADDED_TABLES:
                        self.assertEqual(item["kind"], "added", item)
                        self.assertEqual(item["zone"], "accounting", item)

    def test_storage_energy_audit(self):
        # P0-4 S4 (P3-14, P5-11): the audited grid-side charge is the charge
        # the period summary records, per asset the SoC identity closes, and
        # the closing state the default PSM discards is booked per year.
        for name, path in sorted(self.ledgers.items()):
            uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
            with self.subTest(variant=name), closing(sqlite3.connect(uri, uri=True)) as connection:
                audited, residual, rows = connection.execute(
                    "SELECT SUM(charge_input_mwh), MAX(ABS(identity_residual_mwh)), COUNT(*) FROM storage_energy_audit"
                ).fetchone()
                summary_charge, periods = connection.execute(
                    "SELECT SUM(storage_charge_mwh), COUNT(*) FROM period_summary"
                ).fetchone()
                assets = connection.execute("SELECT COUNT(DISTINCT asset_id) FROM storage_state").fetchone()[0]
                self.assertEqual(rows, periods * assets)
                self.assertLessEqual(abs(audited - summary_charge), 1e-9)
                self.assertLessEqual(residual, 1e-12)
                discharge = connection.execute(
                    "SELECT ABS((SELECT SUM(discharge_output_mwh) FROM storage_energy_audit) - "
                    "(SELECT SUM(discharge_mwh) FROM storage_state))"
                ).fetchone()[0]
                self.assertLessEqual(discharge, 1e-9)
                closing_soc = dict(connection.execute(
                    "SELECT asset_id, soc_end_mwh FROM storage_energy_audit WHERE period=(SELECT MAX(period) FROM storage_energy_audit)"
                ).fetchall())
                boundary = {row[0]: row[1:] for row in connection.execute(
                    "SELECT asset_id, closing_soc_mwh, discarded_mwh, carry_policy FROM storage_year_boundary"
                )}
                self.assertEqual(set(boundary), set(closing_soc))
                for asset, (closing_value, discarded, policy) in boundary.items():
                    self.assertEqual(closing_value, closing_soc[asset])
                    self.assertEqual(discarded, closing_value)
                    self.assertEqual(policy, "new_battery_each_year")
        baseline = self.ledgers["baseline"].resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(baseline, uri=True)) as connection:
            charged = connection.execute("SELECT SUM(charge_input_mwh) FROM storage_energy_audit").fetchone()[0]
        self.assertAlmostEqual(charged, 11.113, places=3)
        multi = self.ledgers["multi_battery"].resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(multi, uri=True)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(DISTINCT asset_id) FROM storage_energy_audit").fetchone()[0], 2)

    def test_storage_orders_reconcile_with_the_bid_formula_and_dispatch(self):
        # Four-role M-D1: every storage tranche offer of both stages is booked
        # at its declared price, accepted or not.  A storage cost module author
        # can reconcile the doctoral linear bid (cycle wear + dwell x holding)
        # per asset and year, and the accepted energy with the dispatch.
        statuses: set[str] = set()
        for name, path in sorted(self.ledgers.items()):
            uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
            with self.subTest(variant=name), closing(sqlite3.connect(uri, uri=True)) as connection:
                rows = connection.execute(
                    "SELECT year, period, clearing_offer_id, asset_id, dwell_periods, bidding_factor, "
                    "offer_price_gbp_per_mwh, offered_mwh, accepted_mwh, status FROM storage_orders"
                ).fetchall()
                self.assertTrue(rows)
                statuses.update(row[9] for row in rows)
                declared = {}
                for year, period, stage, payload in connection.execute(
                    "SELECT year, period, stage, payload_json FROM clearing_inputs"
                ):
                    body = json.loads(payload)["payload"]
                    for offer in body.get("offers", []):
                        if offer.get("resource_kind") == "storage_discharge":
                            declared[(year, period, offer["offer_id"])] = (offer, body["period_hours"])
                self.assertEqual({(row[0], row[1], row[2]) for row in rows}, set(declared))
                lines: dict[tuple[int, str], list[tuple[int, float]]] = {}
                for year, period, offer_id, asset, dwell, factor, price, offered, accepted, _ in rows:
                    offer, hours = declared[(year, period, offer_id)]
                    self.assertEqual(price, offer["offer_price_gbp_per_mwh"])
                    self.assertAlmostEqual(offered, offer["maximum_power_mw"] * hours, places=12)
                    self.assertLessEqual(accepted, offered + 1e-9)
                    lines.setdefault((year, asset), []).append((dwell, price / factor))
                for key, points in lines.items():
                    dwells = sorted({dwell for dwell, _ in points})
                    if len(dwells) < 2:
                        continue
                    by_dwell = dict(points)
                    slope = (by_dwell[dwells[-1]] - by_dwell[dwells[0]]) / (dwells[-1] - dwells[0])
                    for dwell, bid in points:
                        self.assertAlmostEqual(bid, by_dwell[dwells[0]] + slope * (dwell - dwells[0]),
                                               places=9, msg=str(key))
                # Doctoral rule set: the audited discharge is the battery's
                # final_dispatch row in orders; both are net of a same-period
                # buy-back (R4-1, A26), so they never exceed the offers'
                # accepted energy.
                mismatches = connection.execute(
                    "SELECT COUNT(*) FROM (SELECT s.year, s.period, s.asset_id, SUM(s.accepted_mwh) AS offers, "
                    "(SELECT a.discharge_output_mwh FROM storage_energy_audit a WHERE a.year=s.year "
                    "AND a.period=s.period AND a.asset_id=s.asset_id) AS audited, "
                    "(SELECT COALESCE(SUM(o.accepted_mwh), 0) FROM orders o WHERE o.year=s.year "
                    "AND o.period=s.period AND o.asset_id=s.asset_id AND o.stage='final_dispatch') AS dispatched "
                    "FROM storage_orders s GROUP BY s.year, s.period, s.asset_id) "
                    "WHERE audited > offers + 1e-9 OR ABS(audited - dispatched) > 1e-9"
                ).fetchone()[0]
                self.assertEqual(mismatches, 0)
        # Offers that were not accepted are booked too (absent before M-D1).
        self.assertIn("rejected", statuses)

    def test_oracle_verdicts(self):
        statuses = {name: report["status"] for name, report in self.reports.items()}
        self.assertEqual(statuses, EXPECTED)
        for name, report in self.reports.items():
            with self.subTest(variant=name):
                self.assertEqual(report["boundary"]["source"], "metadata")
                self.assertEqual(report["boundary"]["boundary_id"], "default_psm_surplus_node_v1")
                self.assertEqual(report["boundary"]["rule_set"], "native-doctoral-thesis-v1")
                self.assertNotIn(oracle.R_LEGACY, report["reasons"])
                self.assertEqual(report["metrics"]["self_report"]["inconsistent_periods"], 0)
                self.assertEqual(report["metrics"]["self_report"]["raw_residual_basis"], "default_psm_surplus_node_v1")
                # S6: the compatibility adjustment absorbs numerical noise only.
                self.assertEqual(report["metrics"]["reported"]["adjusted_periods"], 0)
        self.assertIn(oracle.R_BOUNDARY_RESIDUAL, self.reports["overshoot"]["reasons"])
        self.assertNotIn(oracle.R_BOUNDARY_RESIDUAL, self.reports["nuclear_balancing"]["reasons"])

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
        # A2 shortfall for period 0: exact since P0-4 S5 records the surplus
        # routing (U_out = W_in = 0): D + C - S = 18.829 (HEAD bounds were
        # [13.829, 18.829]).
        self.assertEqual(report["stress"]["periods"][0]["period"], 0)
        self.assertAlmostEqual(report["stress"]["periods"][0]["shortfall_lower_mwh"], 18.829, places=3)
        self.assertAlmostEqual(report["stress"]["periods"][0]["shortfall_upper_mwh"], 18.829, places=3)
        reported = report["metrics"]["reported"]
        # HEAD closed every period with sum |adj| = 810.546 MWh (more than the
        # day's demand of 775.491 MWh); since S6 nothing is adjusted and the
        # raw residual is the declared boundary's.  R4-1 (A26): the
        # curtailment branch no longer takes down regulation twice and the
        # store nets instead of charging, so the day's shortage is 772.012.
        self.assertAlmostEqual(report["metrics"]["sum_demand_mwh"], 775.491, places=3)
        self.assertEqual(reported["adjusted_periods"], 0)
        self.assertAlmostEqual(reported["sum_abs_raw_residual_mwh"], 772.012, places=3)
        # A2: the ledger books the shortfall as unserved energy, so its
        # energy-balance account closes, and records one 48-period event.
        uri = self.ledgers["overshoot"].resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            shortfall, closing_max, flagged = connection.execute(
                "SELECT SUM(shortfall_mwh), MAX(ABS(closing_residual_mwh)), SUM(stress_flag) FROM balance_boundary_period"
            ).fetchone()
            events = connection.execute(
                "SELECT first_period, last_period, periods, shortfall_mwh, hidden_unserved_mwh FROM stress_event"
            ).fetchall()
        self.assertAlmostEqual(shortfall, 772.012, places=3)
        self.assertLessEqual(closing_max, 1e-9)
        self.assertEqual(flagged, 48)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][:3], (0, 47, 48))
        self.assertAlmostEqual(events[0][3], 772.012, places=3)
        self.assertAlmostEqual(events[0][4], 772.012, places=3)  # recorded blackout is 0
        summary = json.loads((self.outputs["overshoot"] / "market" / "metadata.json").read_text(encoding="utf-8"))
        year = summary["energy_balance"]["by_year"][0]
        self.assertEqual((year["stress_periods"], year["stress_event_count"]), (48, 1))
        self.assertAlmostEqual(year["shortfall_mwh"], 772.012, places=3)
        stress = report["stress"]
        self.assertEqual((stress["stress_periods"], stress["event_count"]), (48, 1))
        self.assertEqual(stress["events"][0]["first_period"], 0)
        self.assertEqual(stress["events"][0]["last_period"], 47)
        self.assertEqual(stress["recorded_unserved_mwh"], 0.0)
        # Exact (routing recorded): the whole hidden shortage of the day.
        self.assertEqual(stress["basis"], "exact")
        self.assertAlmostEqual(stress["shortfall_lower_mwh"], 772.012, places=3)
        self.assertAlmostEqual(stress["shortfall_upper_mwh"], stress["shortfall_lower_mwh"], places=9)

    def test_nuclear_balancing_counts_the_must_run_surplus_once(self):
        report = self.reports["nuclear_balancing"]
        envelope = report["metrics"]["envelope"]
        self.assertEqual(envelope["lower_violations"], 0)
        # Review pack_nucbal: 29 MW nuclear = 14.5 MWh, forecast 6 MW = 3.0 MWh below real
        # demand.  Before R4-1 the balancing branch added the 3.0 MWh balancing volume to the
        # in-dispatch nuclear output again (DEV-BAL-04): nuclear 17.5, full node +3.000 in 35
        # periods.  R4-1 (A26, r41.must-run-surplus-counted-once): the surplus already in S
        # serves the requirement once.  Period 0 by hand: S = 14.5, D = 13.829, C = 0.671
        # (the rest of the surplus charges the battery), XS = K = 0 -> full node = 0.
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
        self.assertAlmostEqual(nuclear, 14.5, places=9)
        self.assertAlmostEqual(row[1], 14.5, places=9)
        self.assertAlmostEqual(row[0] + row[2], 14.5, places=9)
        flows = contract.PeriodFlows(2025, 0, demand_mwh=row[0], supply_mwh=row[1], storage_charge_mwh=row[2],
                                     export_mwh=row[3], flexible_demand_mwh=row[4], blackout_mwh=row[5],
                                     excess_mwh=row[6], curtailed_mwh=row[7])
        result = contract.check_envelope(contract.UNKNOWN_BOUNDARY, flows, contract.EXACT_ARITHMETIC)
        self.assertAlmostEqual(result.full_node_residual_mwh, 0.0, places=9)
        self.assertEqual(result.upper_violation_mwh, 0.0)
        self.assertEqual(envelope["upper_violations"], 0)
        self.assertEqual(report["metrics"]["reported"]["adjusted_periods"], 0)
        self.assertEqual(report["stress"]["stress_periods"], 0)
        self.assertEqual(report["status"], oracle.PASSED)

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

    def _surplus_node(self, name):
        """Per-period default_psm_surplus_node_v1 residuals from the ledger rows."""

        uri = self.ledgers[name].resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            routing, missing = oracle.read_surplus_routing(connection)
            self.assertEqual(missing, [])
            self.assertIsNotNone(routing)
            residuals, gaps, shortfalls = [], [], []
            for row in connection.execute(
                "SELECT year, period, accepted_supply_mwh, blackout_mwh, real_demand_mwh, storage_charge_mwh, "
                "export_mwh, flexible_demand_mwh, excess_mwh, curtailed_mwh FROM period_summary ORDER BY period"
            ):
                rows = routing.get((row[0], row[1]), [])
                u_out, w_in = contract.surplus_terms(rows)
                flows = contract.PeriodFlows(*row, u_out_mwh=u_out, w_in_mwh=w_in)
                residuals.append(contract.surplus_node_residual(flows))
                gaps.extend(abs(item.conservation_gap_mwh()) for item in rows)
                shortfalls.append(contract.period_shortfall(flows))
        return residuals, gaps, shortfalls

    def test_surplus_node_boundary(self):
        # M3 gate (2): physically closing fixtures <= 1e-9, overshoot -18.829;
        # per-source surplus conservation <= 1e-9.  R4-1 (A26): nuclear_balancing
        # (+3.000 before, DEV-BAL-04) closes too.
        for name in ("baseline", "export", "export_electrolyser", "nuclear_curtail", "multi_battery",
                     "nuclear_balancing"):
            with self.subTest(variant=name):
                residuals, gaps, shortfalls = self._surplus_node(name)
                self.assertLessEqual(max(abs(value) for value in residuals), 1e-9)
                self.assertLessEqual(max(gaps, default=0.0), 1e-9)
                self.assertTrue(all(item.exact and item.lower_mwh <= 1e-9 for item in shortfalls))
        residuals, gaps, shortfalls = self._surplus_node("overshoot")
        self.assertAlmostEqual(residuals[0], -18.829, places=3)
        self.assertTrue(all(value < -1.0 for value in residuals))
        self.assertLessEqual(max(gaps), 1e-9)
        # A2 exact shortfall: the whole hidden shortage of the day (it equals
        # the compatibility adjustment HEAD used to hide it).
        self.assertAlmostEqual(sum(item.lower_mwh for item in shortfalls), 772.012, places=3)
        # The in-dispatch (nuclear) surplus re-dispatched in the balancing
        # branch is still routed to the requirement (3.0 MWh), but since
        # R4-1 it is not counted twice.
        uri = self.ledgers["nuclear_balancing"].resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            redispatched = connection.execute(
                "SELECT to_dispatch_mwh FROM surplus_routing WHERE period=0 AND source_class='in_dispatch'"
            ).fetchone()[0]
            double = connection.execute("SELECT MAX(non_vre_double_counted_mwh) FROM balance_boundary_period").fetchone()[0]
        self.assertAlmostEqual(redispatched, 3.0, places=9)
        self.assertEqual(double, 0.0)
        # nuclear_curtail: the booked down-regulation that nuclear could not
        # take out of S is the in-dispatch spill W_in (non_vre_spill).
        uri = self.ledgers["nuclear_curtail"].resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            spilled = connection.execute(
                "SELECT SUM(spilled_mwh) FROM surplus_routing WHERE source_class='in_dispatch'"
            ).fetchone()[0]
        self.assertGreater(spilled, 0.0)

    def test_physical_dispatch_components_follow_the_declared_boundary(self):
        # Sum of balance components minus demand = the declared raw residual.
        for name, path in sorted(self.ledgers.items()):
            uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
            with self.subTest(variant=name), closing(sqlite3.connect(uri, uri=True)) as connection:
                rows = connection.execute(
                    "SELECT p.period, p.raw_energy_balance_residual_mwh, p.real_demand_mwh, "
                    "(SELECT COALESCE(SUM(balance_component_mwh), 0) FROM physical_dispatch d "
                    " WHERE d.year=p.year AND d.period=p.period) FROM period_summary p"
                ).fetchall()
                self.assertEqual(len(rows), 48)
                for period, raw, demand, components in rows:
                    self.assertAlmostEqual(components - demand, raw, places=9, msg=period)

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
