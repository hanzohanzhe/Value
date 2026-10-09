"""Public validation fields and their read-time presentation (P0-4 S3).

* a v2 report's run-invariant, energy-balance and A2 stress fields reach the
  run status, run summaries and comparisons;
* an r2-type historical run (v1 report with literal "passed", a ledger whose
  energy balance violates the envelope) is flagged wherever it is shown,
  while its bundle stays byte-identical;
* market replay sums residuals and adjustments as absolute values and carries
  per-window stress events.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.model_runner import VALIDATION_STATUS_FIELDS
from gridform_core import result_advisories
from gridform_core.market_ledger import PeriodLedgerRow, create_market_ledger
from gridform_core.market_replay import query_dispatch_timeline
from gridform_core.result_advisories import present_scientific_status
from gridform_core.results_summary import build_run_summary, compare_run_summaries
from gridform_core.scientific_validation import MechanismCheck, build_scientific_validation_report
from tests import p04_variants

V1_REPORT = {
    # What VALUE 0.6.0-alpha.2 wrote on the PSM-only path (P7-01: literal).
    "schema_version": "value.scientific-validation/v1",
    "mode": "value_101_day",
    "periods_per_year": 48,
    "execution_status": "passed",
    "contract_validation_status": "passed",
    "scientific_validation_status": "not_evaluated",
    "annual_economics_eligible": False,
    "short_run_diagnostics_only": True,
    "execution_scope": "psm_only",
    "cem_stages_executed": False,
}


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    return {
        path.relative_to(root).as_posix(): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _legacy_run(runs: Path, run_id: str, output: Path) -> Path:
    """A pre-P0-4 run directory: the ledger of ``output`` and a v1 report."""

    run = runs / run_id
    shutil.copytree(output, run / "model-output")
    # The ledger as a pre-P0-4 S4 run wrote it (no audit/routing tables, no
    # declared boundary, HEAD compatibility adjustments).
    p04_variants.downgrade_to_pre_p04_ledger(run / "model-output" / "market" / "market.sqlite")
    for name in ("validation", "parity"):
        shutil.rmtree(run / "model-output" / name, ignore_errors=True)
    report = run / "model-output" / "validation" / "scientific-validation.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps(V1_REPORT), encoding="utf-8")
    (run / "status.json").write_text(json.dumps({
        "id": run_id, "status": "completed", "mode": "value_101_day", "project_id": "release",
        "execution_engine": "value-annual-orchestrator/v2",
        "project_name": run_id, "modules": {"psm": "value-bid-at-cost-psm", "storage_cost": "dynamic-annual-storage-cost"},
        "execution_status": "passed", "contract_validation_status": "passed",
        "scientific_validation_status": "not_evaluated", "results": [],
        "scientific_validation_artifact": "validation/scientific-validation.json",
    }), encoding="utf-8")
    return run


class LegacyRunPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix="p04-s3-"))
        cls.outputs = {
            name: p04_variants.run_variant(name, cls.folder / "outputs" / name, mode="value_101_day")
            for name in ("overshoot", "baseline")
        }
        cls.runs = cls.folder / "runs"
        cls.r2 = _legacy_run(cls.runs, "release-r2-like", cls.outputs["overshoot"])
        cls.baseline = _legacy_run(cls.runs, "value-101-baseline-like", cls.outputs["baseline"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def setUp(self):
        result_advisories._ORACLE_CACHE.clear()
        self.before = _snapshot(self.runs)

    def tearDown(self):
        self.assertEqual(_snapshot(self.runs), self.before, "a read-time presentation wrote to a run directory")
        for side in self.runs.rglob("*-wal"):
            self.fail(f"read-time check left {side}")

    def _present(self, run_root: Path, **overrides) -> dict:
        from backend import server

        status = json.loads((run_root / "status.json").read_text(encoding="utf-8"))
        status.update(overrides)
        with patch.object(server, "RUNS_ROOT", self.runs):
            return server.present_run(status)

    def test_r2_type_run_is_flagged_in_run_details(self):
        run = self._present(self.r2)
        self.assertEqual(run["contract_validation_status"], "superseded_pre_fix")
        self.assertEqual(run["recorded_validation_statuses"]["contract_validation_status"], "passed")
        self.assertEqual(run["energy_balance_status"], "failed")
        self.assertEqual(run["energy_balance"]["source"], "read_time_oracle")
        self.assertEqual(run["energy_balance"]["compatibility_adjustment_periods"], 48)
        self.assertEqual(run["stress"]["stress_periods"], 48)
        # Lower bound max(D - S, 0) of the downgraded ledger (no routing).  R4-1
        # (A26): the doctoral store nets the absorbed need against its own
        # discharge instead of charging, so S is lower and the bound higher
        # (570.546171074 before R4-1); the exact shortfall stays 810.546.
        self.assertAlmostEqual(run["stress"]["shortfall_mwh"], 760.890307058, places=6)
        self.assertEqual(run["stress"]["shortfall_basis"], "lower_bound")
        self.assertEqual(run["run_invariant_status"], "not_evaluated")
        codes = {row["code"] for row in run["validation_warnings"]}
        self.assertEqual(codes, {"GF_VALIDATION_LEGACY_REPORT", "GF_ENERGY_BALANCE_FAILED", "GF_STRESS_EVENTS_RECORDED"})
        self.assertIn("GF_VALIDATION_LEGACY_REPORT", {row["id"] for row in run["advisories"]})
        self.assertEqual(run["raw_invariants"]["status"], "failed")

    def test_r2_type_run_is_flagged_in_listing_summary_and_comparison(self):
        from backend import server

        with patch.object(server, "RUNS_ROOT", self.runs):
            listed = {row["id"]: row for row in server.list_runs()}
        self.assertEqual(listed["release-r2-like"]["energy_balance_status"], "failed")
        self.assertEqual(listed["value-101-baseline-like"]["energy_balance_status"], "not_evaluated")
        r2 = build_run_summary(self.r2)
        baseline = build_run_summary(self.baseline)
        self.assertEqual(r2["run"]["energy_balance_status"], "failed")
        self.assertEqual(r2["run"]["stress"]["stress_periods"], 48)
        self.assertEqual(baseline["run"]["stress"]["stress_periods"], 0)
        comparison = compare_run_summaries([baseline, r2])
        self.assertEqual(comparison["attribution_status"], "needs_review")
        self.assertIn({"run_id": "release-r2-like", "reason": "energy_balance_failed"},
                      comparison["attribution_review_reasons"])
        self.assertEqual(comparison["changed_dimensions"]["run.energy_balance_status"], ["not_evaluated", "failed"])
        self.assertFalse(comparison["causal_claim_allowed"])

    def test_a_running_run_is_not_checked_at_read_time(self):
        with patch.object(result_advisories, "read_time_energy_balance") as oracle:
            run = self._present(self.r2, status="running")
        oracle.assert_not_called()
        self.assertEqual(run["energy_balance_status"], "not_evaluated")
        self.assertEqual(run["validation_evidence"], {"source": "not_yet_available"})

    def test_read_time_check_is_cached_and_size_capped(self):
        with patch("gridform_core.energy_balance_oracle.evaluate_run_ledger",
                   wraps=__import__("gridform_core.energy_balance_oracle", fromlist=["x"]).evaluate_run_ledger) as spy:
            first = result_advisories.read_time_energy_balance(self.r2)
            second = result_advisories.read_time_energy_balance(self.r2)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(first, second)
        with patch.object(result_advisories, "READ_TIME_ORACLE_MAX_BYTES", 10):
            skipped = result_advisories.read_time_energy_balance(self.baseline)
        self.assertEqual(skipped["reasons"], [result_advisories.R_READ_TIME_SKIPPED])
        self.assertEqual(skipped["status"], "not_evaluated")


class V2EvidencePresentationTests(unittest.TestCase):
    def test_model_runner_copies_every_v2_evidence_field(self):
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520, parity_report={"contract_parity_passed": True},
            mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")])
        self.assertTrue(set(VALIDATION_STATUS_FIELDS) - {"stress"} <= set(report))
        self.assertTrue(set(result_advisories.VALIDATION_EVIDENCE_FIELDS) <= set(VALIDATION_STATUS_FIELDS))

    def test_v2_report_is_authoritative_over_status_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "model-output" / "validation" / "scientific-validation.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "schema_version": "value.scientific-validation/v2", "scientific_validation_status": "passed",
                "contract_validation_status": "passed", "run_invariant_status": "passed",
                "energy_balance_status": "failed", "raw_invariants": {"status": "failed"},
                "stress": {"stress_periods": 3, "shortfall_mwh": 1.5}, "validation_warnings": [],
            }), encoding="utf-8")
            run = present_scientific_status({
                "id": "run", "mode": "full", "status": "completed", "modules": {},
                "energy_balance_status": "passed", "contract_validation_status": "passed",
            }, root)
        self.assertEqual(run["energy_balance_status"], "failed")
        self.assertEqual(run["stress"]["stress_periods"], 3)
        self.assertEqual(run["validation_evidence"]["source"], "scientific_validation_v2")
        # Pre-profile run: its positive claims are still superseded.
        self.assertEqual(run["contract_validation_status"], "superseded_pre_fix")


def _row(period: int, *, demand: float, supply: float, adjustment: float = 0.0) -> PeriodLedgerRow:
    return PeriodLedgerRow(
        year=2025, period=period, stage="final_dispatch", forecast_demand_mwh=demand,
        real_demand_mwh=demand, accepted_supply_mwh=supply, storage_charge_mwh=0.0,
        storage_discharge_mwh=0.0, flexible_demand_mwh=0.0, export_mwh=0.0,
        vre_available_mwh=0.0, vre_accepted_mwh=0.0, curtailed_mwh=0.0, import_mwh=0.0,
        clearing_price_gbp_per_mwh=40.0, physical_resource_cost_gbp=0.0, market_payment_gbp=0.0,
        policy_transfer_gbp=0.0, blackout_mwh=0.0, excess_mwh=0.0,
        energy_balance_residual_mwh=0.0, compatibility_adjustment_mwh=adjustment,
        raw_energy_balance_residual_mwh=-adjustment,
    )


class MarketReplayAggregationTests(unittest.TestCase):
    def _timeline(self, rows, **query):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = create_market_ledger(database, "summary")
            for row in rows:
                ledger.record_period(row)
            ledger.close()
            return query_dispatch_timeline(database, year=2025, **query)

    def test_opposite_adjustments_in_one_window_do_not_cancel(self):
        timeline = self._timeline([
            _row(0, demand=10.0, supply=10.0, adjustment=2.0),
            _row(1, demand=10.0, supply=10.0, adjustment=-2.0),
        ], resolution="daily")
        bucket = timeline["items"][0]
        self.assertEqual(bucket["compatibility_adjustment_mwh"], 4.0)
        self.assertEqual(bucket["raw_energy_balance_residual_mwh"], 4.0)
        self.assertEqual(timeline["residual_aggregation"], "sum_of_absolute_period_values")

    def test_windows_carry_stress_periods_and_the_certain_shortfall(self):
        timeline = self._timeline([
            _row(0, demand=10.0, supply=10.0),
            _row(1, demand=10.0, supply=7.5),
            _row(2, demand=10.0, supply=9.0),
            _row(3, demand=10.0, supply=10.0),
        ], resolution="half_hour", limit=10)
        self.assertTrue(timeline["stress_recorded"])
        stress = [(item["stress_periods"], item["shortfall_mwh"]) for item in timeline["items"]]
        self.assertEqual(stress, [(0, 0.0), (1, 2.5), (1, 1.0), (0, 0.0)])
        self.assertEqual({item["shortfall_basis"] for item in timeline["items"]}, {"lower_bound"})
        daily = self._timeline([
            _row(0, demand=10.0, supply=10.0),
            _row(1, demand=10.0, supply=7.5),
            _row(2, demand=10.0, supply=9.0),
        ], resolution="daily")["items"][0]
        self.assertEqual((daily["stress_periods"], daily["shortfall_mwh"]), (2, 3.5))


if __name__ == "__main__":
    unittest.main()
