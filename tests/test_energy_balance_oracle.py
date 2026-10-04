"""Hand-computed cases T1-T6 for the P0-4 energy-balance oracle (plan 4.4 S1).

Every expected number below is worked out by hand in the comment next to it;
none is produced by the code under test.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gridform_core import energy_balance_contract as contract
from gridform_core import energy_balance_oracle as oracle

PERIOD_SUMMARY_SQL = """
CREATE TABLE period_summary(
    year INTEGER NOT NULL, period INTEGER NOT NULL, stage TEXT NOT NULL,
    forecast_demand_mwh REAL NOT NULL, real_demand_mwh REAL NOT NULL,
    accepted_supply_mwh REAL NOT NULL, storage_charge_mwh REAL NOT NULL,
    storage_discharge_mwh REAL NOT NULL, flexible_demand_mwh REAL NOT NULL,
    export_mwh REAL NOT NULL, vre_available_mwh REAL NOT NULL,
    vre_accepted_mwh REAL NOT NULL, curtailed_mwh REAL NOT NULL,
    import_mwh REAL NOT NULL, clearing_price_gbp_per_mwh REAL NOT NULL,
    physical_resource_cost_gbp REAL NOT NULL, market_payment_gbp REAL NOT NULL,
    policy_transfer_gbp REAL NOT NULL, blackout_mwh REAL NOT NULL,
    excess_mwh REAL NOT NULL, energy_balance_residual_mwh REAL NOT NULL,
    compatibility_adjustment_mwh REAL NOT NULL,
    raw_energy_balance_residual_mwh REAL NOT NULL,
    PRIMARY KEY(year, period, stage)
)
"""
ROUTING_SQL = """
CREATE TABLE surplus_routing(
    year INTEGER NOT NULL, period INTEGER NOT NULL, source_class TEXT NOT NULL,
    available_mwh REAL NOT NULL, to_storage_mwh REAL NOT NULL, to_export_mwh REAL NOT NULL,
    to_flexible_mwh REAL NOT NULL, spilled_mwh REAL NOT NULL,
    PRIMARY KEY(year, period, source_class)
)
"""
DEFAULT_PSM = {"psm_module_id": "value-bid-at-cost-psm", "psm_module_version": "5.1.0"}


def period(period_index, *, D, S, C=0.0, E=0.0, X=0.0, B=0.0, XS=0.0, F=None, raw=0.0, adj=0.0, residual=None, year=2025,
           stage="final_dispatch"):
    return {
        "year": year, "period": period_index, "stage": stage,
        "forecast_demand_mwh": D if F is None else F, "real_demand_mwh": D,
        "accepted_supply_mwh": S, "storage_charge_mwh": C, "storage_discharge_mwh": 0.0,
        "flexible_demand_mwh": X, "export_mwh": E, "vre_available_mwh": 0.0,
        "vre_accepted_mwh": 0.0, "curtailed_mwh": 0.0, "import_mwh": 0.0,
        "clearing_price_gbp_per_mwh": 0.0, "physical_resource_cost_gbp": 0.0,
        "market_payment_gbp": 0.0, "policy_transfer_gbp": 0.0, "blackout_mwh": B,
        "excess_mwh": XS,
        "energy_balance_residual_mwh": (raw + adj) if residual is None else residual,
        "compatibility_adjustment_mwh": adj, "raw_energy_balance_residual_mwh": raw,
    }


def write_ledger(path: Path, periods, *, metadata=None, routing=None, drop_column=None, wal=False):
    connection = sqlite3.connect(path)
    sql = PERIOD_SUMMARY_SQL
    if drop_column:
        sql = sql.replace(f"{drop_column} REAL NOT NULL, ", "")
        assert drop_column not in sql
    connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(sql)
    meta = {"schema_version": "value.market-ledger/v7", **(metadata or {})}
    connection.executemany(
        "INSERT INTO metadata VALUES(?,?)",
        [(key, value if key == "schema_version" else json.dumps(value)) for key, value in meta.items()],
    )
    columns = [row[1] for row in connection.execute("PRAGMA table_info(period_summary)")]
    for row in periods:
        connection.execute(
            f"INSERT INTO period_summary({', '.join(columns)}) VALUES({', '.join('?' for _ in columns)})",
            [row[name] for name in columns],
        )
    if routing is not None:
        connection.execute(ROUTING_SQL)
        connection.executemany("INSERT INTO surplus_routing VALUES(?,?,?,?,?,?,?,?)", routing)
    connection.commit()
    if wal:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO metadata VALUES('late','\"row\"')")
        connection.commit()
        return connection  # kept open: the WAL is not checkpointed
    connection.close()
    return None


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OracleCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="p04-oracle-")
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def evaluate(self, name, periods, **kwargs):
        path = self.root / name / "market" / "market.sqlite"
        path.parent.mkdir(parents=True)
        handle = write_ledger(path, periods, **kwargs)
        self.addCleanup(lambda: handle and handle.close())
        before = sha(path)
        mtime = path.stat().st_mtime_ns
        report = oracle.evaluate_ledger(path.parent.parent)
        self.assertEqual(report["ledger"]["sha256_before"], before)
        self.assertEqual(report["ledger"]["sha256_after"], before)
        self.assertTrue(report["ledger"]["unchanged"])
        self.assertEqual(sha(path), before)
        self.assertEqual(path.stat().st_mtime_ns, mtime)
        return report


class T1FullNode(OracleCase):
    FULL = {"energy_balance_boundary": "full_node_v1"}

    def test_closing_full_node_passes(self):
        # r = S + B - D - C - E - X = 10 + 0 - 7 - 2 - 0.5 - 0.5 = 0
        # r = 8 + 1.5 - 7 - 2 - 0.5 - 0 = 0 (1.5 MWh recorded blackout)
        report = self.evaluate("t1", [
            period(0, D=7.0, S=10.0, C=2.0, E=0.5, X=0.5),
            period(1, D=7.0, S=8.0, C=2.0, E=0.5, B=1.5),
        ], metadata=self.FULL)
        self.assertEqual(report["status"], oracle.PASSED, report["reasons"])
        self.assertEqual(report["boundary"]["source"], "metadata")
        self.assertEqual(report["metrics"]["boundary_residual"]["max_abs_mwh"], 0.0)
        # A2: full-node shortfall = max(0, D + C + E + X - S) = 7 + 2 + 0.5 - 8 = 1.5 in period 1,
        # entirely recorded as blackout.
        stress = report["stress"]
        self.assertEqual(stress["basis"], "exact")
        self.assertEqual(stress["stress_periods"], 1)
        self.assertEqual(stress["event_count"], 1)
        self.assertAlmostEqual(stress["shortfall_mwh"], 1.5, places=12)
        self.assertAlmostEqual(stress["recorded_unserved_mwh"], 1.5, places=12)
        self.assertAlmostEqual(stress["by_year"][0]["hidden_shortfall_lower_mwh"], 0.0, places=12)

    def test_imbalanced_full_node_fails(self):
        # r = 10 - 7 - 2 - 0.5 - 0 = +0.5, self-reported consistently as raw 0.5
        report = self.evaluate("t1b", [period(0, D=7.0, S=10.0, C=2.0, E=0.5, raw=0.5)], metadata=self.FULL)
        self.assertEqual(report["status"], oracle.FAILED)
        self.assertIn(oracle.R_BOUNDARY_RESIDUAL, report["reasons"])
        self.assertIn(oracle.R_ENVELOPE, report["reasons"])
        self.assertAlmostEqual(report["metrics"]["boundary_residual"]["max_mwh"], 0.5, places=12)


class T2SurplusNode(OracleCase):
    SURPLUS = {**DEFAULT_PSM, "energy_balance_boundary": "default_psm_surplus_node_v1"}

    def test_in_dispatch_spill_closes_with_w_in(self):
        # Period 0: must-run surplus inside S.  D = 13.829, S = 19.4815, so the
        # in-dispatch surplus is 5.6525: 5.0 charges storage, 0.6525 is spilled.
        #   full node  = 19.4815 - 13.829 - 5.0           = +0.6525  (= W_in)
        #   surplus    = 19.4815 + 0 - 0.6525 - 13.829 - 5.0 = 0
        # Period 1: out-of-dispatch VRE surplus 4.0 outside S: 3.0 charges, 1.0 spilled.
        #   full node  = 12.0 - 12.0 - 3.0 = -3.0  (inside [-(C+E+X), XS] = [-3, 1])
        #   surplus    = 12.0 + 3.0 - 0 - 12.0 - 3.0 = 0
        report = self.evaluate("t2", [
            period(0, D=13.829, S=19.4815, C=5.0, XS=0.6525),
            period(1, D=12.0, S=12.0, C=3.0, XS=1.0),
        ], metadata=self.SURPLUS, routing=[
            (2025, 0, "in_dispatch", 5.6525, 5.0, 0.0, 0.0, 0.6525),
            (2025, 1, "out_of_dispatch", 4.0, 3.0, 0.0, 0.0, 1.0),
        ])
        self.assertEqual(report["status"], oracle.PASSED, report["reasons"])
        self.assertAlmostEqual(report["metrics"]["full_node"]["max_mwh"], 0.6525, places=9)
        self.assertAlmostEqual(report["metrics"]["full_node"]["min_mwh"], -3.0, places=9)
        self.assertLessEqual(report["metrics"]["boundary_residual"]["max_abs_mwh"], 1e-9)
        self.assertEqual(report["stress"]["stress_periods"], 0)

    def test_unconserved_surplus_fails(self):
        # available 5.6525 but 5.0 + 0.5 routed/spilled: gap 0.1525
        report = self.evaluate("t2b", [period(0, D=13.829, S=19.3290, C=5.0, XS=0.5)],
                               metadata=self.SURPLUS,
                               routing=[(2025, 0, "in_dispatch", 5.6525, 5.0, 0.0, 0.0, 0.5)])
        self.assertEqual(report["status"], oracle.FAILED)
        self.assertIn(oracle.R_SURPLUS_CONSERVATION, report["reasons"])

    def test_declared_surplus_node_without_routing_is_not_evaluated(self):
        report = self.evaluate("t2c", [period(0, D=10.0, S=10.0)], metadata=self.SURPLUS)
        self.assertEqual(report["status"], oracle.NOT_EVALUATED)
        self.assertIn(oracle.R_ROUTING_MISSING, report["reasons"])

    def test_declared_raw_is_not_cross_checked_on_the_retained_boundary(self):
        # The kernel declares the surplus node, so its raw column (here 0, closing with
        # U_out = 2) is on that boundary.  Without routing it cannot be recomputed and
        # must not be compared with the retained recomputation (10 - 10 - min(2, 0) = 0
        # would agree by chance; F = 13 makes it -2).
        report = self.evaluate("t2d", [period(0, D=10.0, S=10.0, C=2.0, F=13.0)], metadata=self.SURPLUS)
        self.assertEqual(report["status"], oracle.NOT_EVALUATED)
        self.assertIsNone(report["metrics"]["self_report"]["raw_residual_basis"])
        self.assertNotIn(oracle.R_SELF_INCONSISTENT, report["reasons"])


class T3Envelope(OracleCase):
    def test_both_sides_violated_once(self):
        # Legacy ledger (no declared boundary, registry -> default PSM).
        # Period 0 (overshoot): D = 13.829, S = 0, C = 5, F = 60.
        #   full node = 0 - 13.829 - 5 = -18.829; lower bound -(C+E+X) = -5 -> violation 13.829
        #   retained raw = 0 - 13.829 - min(5, 60 - 13.829) = -18.829 (adjusted away)
        # Period 1 (nuclear balancing): D = 14.5, S = 17.5, XS = 0.
        #   full node = +3.0; upper bound XS = 0 -> violation 3.0
        report = self.evaluate("t3", [
            period(0, D=13.829, S=0.0, C=5.0, F=60.0, raw=-18.829, adj=18.829),
            period(1, D=14.5, S=17.5, raw=3.0, adj=-3.0),
        ], metadata=DEFAULT_PSM)
        self.assertEqual(report["status"], oracle.FAILED)
        self.assertIn(oracle.R_ENVELOPE, report["reasons"])
        self.assertIn(oracle.R_LEGACY, report["reasons"])
        envelope = report["metrics"]["envelope"]
        self.assertEqual((envelope["lower_violations"], envelope["upper_violations"]), (1, 1))
        self.assertAlmostEqual(envelope["max_lower_violation_mwh"], 13.829, places=9)
        self.assertAlmostEqual(envelope["max_upper_violation_mwh"], 3.0, places=9)
        self.assertEqual(report["metrics"]["self_report"]["inconsistent_periods"], 0)
        # A2 bounds: period 0 shortfall in [D - S, D + C - S] = [13.829, 18.829]
        stress = report["stress"]
        self.assertEqual(stress["basis"], "bounds")
        self.assertIsNone(stress["shortfall_mwh"])
        self.assertEqual(stress["periods"][0]["period"], 0)
        self.assertAlmostEqual(stress["periods"][0]["shortfall_lower_mwh"], 13.829, places=9)
        self.assertAlmostEqual(stress["periods"][0]["shortfall_upper_mwh"], 18.829, places=9)
        self.assertEqual(stress["stress_periods"], 1)

    def test_legacy_ledger_that_closes_is_never_passed(self):
        # Inside the envelope: full node -0.9 with C = 0.9 (VRE excess charging).
        report = self.evaluate("t3b", [period(0, D=15.0, S=15.0, C=0.9)], metadata=DEFAULT_PSM)
        self.assertEqual(report["status"], oracle.NOT_EVALUATED)
        self.assertEqual(report["reasons"], [oracle.R_LEGACY])

    def test_unknown_module_uses_widest_envelope(self):
        report = self.evaluate("t3c", [period(0, D=10.0, S=10.0, C=1.0)], metadata={"psm_module_id": "someone-elses-psm"})
        self.assertEqual(report["boundary"]["source"], "unknown")
        self.assertEqual(report["status"], oracle.NOT_EVALUATED)
        self.assertEqual(report["reasons"], [oracle.R_UNKNOWN_BOUNDARY])


class T4SelfReport(OracleCase):
    def test_residual_is_not_raw_plus_adjustment(self):
        # raw -2 + adj 0 = -2, but the ledger claims residual 0.
        report = self.evaluate("t4", [period(0, D=10.0, S=10.0, raw=-2.0, adj=0.0, residual=0.0)], metadata=DEFAULT_PSM)
        self.assertEqual(report["status"], oracle.FAILED)
        self.assertIn(oracle.R_SELF_INCONSISTENT, report["reasons"])

    def test_declared_raw_disagrees_with_recomputation(self):
        # Physically closing full node (10 - 7 - 3 = 0) but the ledger reports raw 0.25.
        report = self.evaluate("t4b", [period(0, D=7.0, S=10.0, C=3.0, raw=0.25, adj=-0.25)],
                               metadata={"energy_balance_boundary": "full_node_v1"})
        self.assertEqual(report["status"], oracle.FAILED)
        self.assertEqual(report["reasons"], [oracle.R_SELF_INCONSISTENT, oracle.R_ADJUSTMENT_CAP])

    def test_legacy_raw_is_cross_checked_on_the_retained_boundary(self):
        # Retained raw = S - D - min(C, max(F - D, 0)) = 10 - 10 - min(2, 0) = 0, ledger says -2.
        report = self.evaluate("t4c", [period(0, D=10.0, S=10.0, C=2.0, raw=-2.0, adj=2.0)], metadata=DEFAULT_PSM)
        self.assertEqual(report["status"], oracle.FAILED)
        self.assertIn(oracle.R_SELF_INCONSISTENT, report["reasons"])


class T5MissingInputs(OracleCase):
    def test_missing_column_is_not_evaluated(self):
        report = self.evaluate("t5", [period(0, D=10.0, S=10.0)], metadata=DEFAULT_PSM, drop_column="excess_mwh")
        self.assertEqual(report["status"], oracle.NOT_EVALUATED)
        self.assertEqual(report["reasons"], [oracle.R_MISSING_COLUMN])
        self.assertEqual(report["checks"][0]["missing_columns"], ["excess_mwh"])

    def test_no_period_summary_is_not_evaluated(self):
        path = self.root / "t5b.sqlite"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.commit()
        connection.close()
        report = oracle.evaluate_ledger(path)
        self.assertEqual(report["status"], oracle.NOT_EVALUATED)
        self.assertEqual(report["reasons"], [oracle.R_NO_TABLE])


class StageSelection(OracleCase):
    def test_final_dispatch_row_is_the_period_balance(self):
        # The ahead row is out of balance (S 0 vs D 10); only final_dispatch counts:
        # full node 10 - 10 = 0.
        report = self.evaluate("st", [
            period(0, D=10.0, S=0.0, stage="ahead"),
            period(0, D=10.0, S=10.0),
        ], metadata={"energy_balance_boundary": "full_node_v1"})
        self.assertEqual(report["status"], oracle.PASSED, report["reasons"])
        self.assertEqual(report["metrics"]["periods"], 1)

    def test_several_non_final_stages_are_ambiguous(self):
        report = self.evaluate("st2", [
            period(0, D=10.0, S=0.0, stage="ahead"),
            period(0, D=10.0, S=10.0, stage="balancing"),
        ], metadata={"energy_balance_boundary": "full_node_v1"})
        self.assertEqual(report["status"], oracle.NOT_EVALUATED)
        self.assertEqual(report["reasons"], [oracle.R_AMBIGUOUS_STAGE])


class T6Wal(OracleCase):
    def test_uncheckpointed_wal_is_not_evaluated(self):
        path = self.root / "t6" / "market.sqlite"
        path.parent.mkdir()
        handle = write_ledger(path, [period(0, D=13.829, S=0.0, C=5.0, F=60.0, raw=-18.829, adj=18.829)],
                              metadata=DEFAULT_PSM, wal=True)
        try:
            wal = path.with_name("market.sqlite-wal")
            self.assertGreater(wal.stat().st_size, 0)
            before = sha(path)
            report = oracle.evaluate_ledger(path)
            self.assertEqual(report["status"], oracle.NOT_EVALUATED)
            self.assertEqual(report["reasons"], [oracle.R_WAL])
            self.assertEqual(sha(path), before)
        finally:
            handle.close()


class ContractUnits(unittest.TestCase):
    def test_registry(self):
        entry = contract.registry_lookup("value-bid-at-cost-psm", "5.1.0", None)
        self.assertEqual(entry.boundary_id, contract.DEFAULT_PSM_SURPLUS_NODE_V1)
        self.assertEqual(contract.registry_lookup("value-bid-at-cost-psm", "5.2.0", "doctoral-lineage-0.6.0a2").boundary_id,
                         contract.DEFAULT_PSM_SURPLUS_NODE_V1)
        self.assertIsNone(contract.registry_lookup("value-bid-at-cost-psm", "6.0.0", None))
        self.assertIsNone(contract.registry_lookup("value-bid-at-cost-psm", "5.1.0", "value-corrected"))
        self.assertIsNone(contract.registry_lookup("value-doctoral-national-psm", "0.2.0", None))
        self.assertEqual(contract.registry_lookup("value-perfect-foresight-lp", "1.0.0", None).boundary_id, contract.FULL_NODE_V1)

    def test_tolerance_tiers(self):
        # max(abs 1e-6, rel 1e-9 * max(|m|, 1)): the relative term wins above 1000 MWh.
        self.assertEqual(contract.tolerance(contract.EXACT_ARITHMETIC, 10.0), 1e-6)
        self.assertEqual(contract.tolerance(contract.EXACT_ARITHMETIC, 500.0), 1e-6)
        self.assertAlmostEqual(contract.tolerance(contract.EXACT_ARITHMETIC, 1e4), 1e-5, places=18)
        self.assertAlmostEqual(contract.tolerance(contract.EXACT_ARITHMETIC, 1e7), 1e-2, places=15)
        self.assertEqual(contract.tolerance(contract.LP_SOLVER, 1.0), 1e-5)

    def test_stress_events_group_contiguous_periods_per_year(self):
        def estimate(year, index, value, blackout=0.0):
            return contract.ShortfallEstimate(year, index, value, value, blackout, True)

        summary = contract.stress_events([
            estimate(2025, 0, 1.0), estimate(2025, 1, 2.0, blackout=2.0), estimate(2025, 2, 0.0),
            estimate(2025, 3, 0.5), estimate(2025, 17519, 1.0), estimate(2026, 0, 1.0),
        ])
        self.assertEqual(summary.basis, "exact")
        self.assertEqual(summary.stress_periods, 5)
        # [0,1], [3], [17519] in 2025 and [0] in 2026: a new year starts a new event.
        self.assertEqual([(event.year, event.first_period, event.last_period, event.periods) for event in summary.events],
                         [(2025, 0, 1, 2), (2025, 3, 3, 1), (2025, 17519, 17519, 1), (2026, 0, 0, 1)])
        self.assertEqual(summary.by_year[2025]["event_count"], 3)
        self.assertAlmostEqual(summary.by_year[2025]["shortfall_lower_mwh"], 4.5)
        self.assertAlmostEqual(summary.by_year[2025]["hidden_shortfall_lower_mwh"], 2.5)
        self.assertAlmostEqual(summary.by_year[2025]["recorded_unserved_mwh"], 2.0)

    def test_contract_is_a_stdlib_leaf(self):
        import ast

        tree = ast.parse(Path(contract.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "the contract must not import project modules")
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "math", "dataclasses", "typing"})


class Cli(OracleCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = oracle.main(list(argv))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_exit_codes(self):
        cases = {
            "pass": ([period(0, D=7.0, S=10.0, C=3.0)], {"energy_balance_boundary": "full_node_v1"}, 0),
            "fail": ([period(0, D=13.829, S=0.0, C=5.0, F=60.0, raw=-18.829, adj=18.829)], DEFAULT_PSM, 1),
            "legacy": ([period(0, D=10.0, S=10.0)], DEFAULT_PSM, 2),
        }
        for name, (periods, metadata, expected) in cases.items():
            path = self.root / name / "market.sqlite"
            path.parent.mkdir()
            write_ledger(path, periods, metadata=metadata)
            output = self.root / f"{name}.json"
            code, stdout, _ = self.run_cli(str(path), "--quiet", "--output", str(output))
            self.assertEqual(code, expected, (name, stdout))
            self.assertEqual(json.loads(output.read_text())["status"], stdout.split()[0])
        code, _, err = self.run_cli(str(self.root / "missing.sqlite"))
        self.assertEqual(code, oracle.EXIT_USAGE)
        self.assertIn("does not exist", err)
        code, _, _ = self.run_cli("--no-such-flag")
        self.assertEqual(code, oracle.EXIT_USAGE)

    def test_module_entry_point(self):
        import subprocess
        import sys

        path = self.root / "m" / "market.sqlite"
        path.parent.mkdir()
        write_ledger(path, [period(0, D=10.0, S=10.0)], metadata=DEFAULT_PSM)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "gridform_core.energy_balance_oracle", str(path), "--quiet"],
            capture_output=True, text=True, env=environment, cwd=str(Path(__file__).resolve().parents[1]),
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertTrue(completed.stdout.startswith("not_evaluated"))


if __name__ == "__main__":
    unittest.main()
