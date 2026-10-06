"""Run-level invariants, stage parity v3 and scientific validation v2 (P0-4 S2).

Hand-built toys pin each check (state chain with and without network
expansion, the input tally, the generation cross path); the integration cases
run the derived VALUE 101 fixtures (tests/p04_variants.py) through the real
application path and check what the run directory then records.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from gridform_core.bundle_validator import validate_run_bundle
from gridform_core.market_ledger import PeriodLedgerRow, PhysicalDispatchRow, create_market_ledger
from gridform_core.parity import build_native_parity_report, recompute_check
from gridform_core.run_invariants import (
    FAILED,
    NOT_APPLICABLE,
    NOT_EVALUATED,
    PASSED,
    evaluate_run_invariants,
    input_tally,
    record_input_tally,
    summarise,
)
from gridform_core.scientific_validation import build_scientific_validation_report
from gridform_core.v2.orchestrator import contract_hash
from tests import p04_variants


def _state(year: int, label: str) -> dict:
    return {"year": year, "assets": [{"asset_id": label}], "planning_projects": [], "schema_version": "value.year-state/v2"}


def _chain(years=(2025, 2026), *, network=False):
    """Typed results whose state hand-over is consistent, plus matching events."""

    initial = _state(years[0], "initial")
    previous = initial
    results, events = [], []
    for year in years:
        extensions = {}
        if network:
            advanced = _state(year, f"network-{year}")
            extensions["network_expansion"] = {"advance": {"state": advanced}}
            events.append({"year": year, "stage": "network_expansion.advance_year",
                           "input_state_sha256": contract_hash(previous)})
            annual_input = contract_hash(advanced)
        else:
            annual_input = contract_hash(previous)
        extensions["annual_input_state_sha256"] = annual_input
        next_state = _state(year + 1, f"after-{year}")
        events.append({"year": year, "stage": "planning.advance_year", "input_state_sha256": annual_input})
        events.append({"year": year, "stage": "state_transition.apply",
                       "output_state_sha256": contract_hash(next_state)})
        results.append({"year": year, "extensions": extensions, "next_state": next_state,
                        "market": {}})
        previous = next_state
    return contract_hash(initial), results, events


def _period(year: int, period: int, demand: float, forecast: float, supply: float | None = None) -> PeriodLedgerRow:
    supply = demand if supply is None else supply
    return PeriodLedgerRow(
        year=year, period=period, stage="final_dispatch",
        forecast_demand_mwh=forecast, real_demand_mwh=demand, accepted_supply_mwh=supply,
        storage_charge_mwh=0.0, storage_discharge_mwh=0.0, flexible_demand_mwh=0.0,
        export_mwh=0.0, vre_available_mwh=0.0, vre_accepted_mwh=0.0, curtailed_mwh=0.0,
        import_mwh=0.0, clearing_price_gbp_per_mwh=50.0, physical_resource_cost_gbp=0.0,
        market_payment_gbp=0.0, policy_transfer_gbp=0.0, blackout_mwh=0.0, excess_mwh=0.0,
        energy_balance_residual_mwh=0.0,
    )


def _ledger_run(root: Path, *, demand=(10.0, 12.0), forecast=(11.0, 12.5), gas=(6.0, 7.0)) -> Path:
    output = root / "model-output"
    (output / "market").mkdir(parents=True)
    ledger = create_market_ledger(output / "market" / "market.sqlite", "full")
    for period, value in enumerate(demand):
        ledger.record_period(_period(2025, period, value, forecast[period]))
        ledger.record_physical_dispatch((
            PhysicalDispatchRow(2025, period, "gas-a", "ccgt", "generation", gas[period], gas[period],
                                "physical_asset", "final_dispatch"),
            PhysicalDispatchRow(2025, period, "wind-a", "onshore_wind", "generation", value - gas[period],
                                value - gas[period], "physical_asset", "final_dispatch"),
            PhysicalDispatchRow(2025, period, "battery-a", "battery", "storage_discharge", 1.0, 1.0,
                                "final_storage_output", "final_dispatch"),
        ))
    ledger.close()
    return output


def _typed(demand=(10.0, 12.0), gas=(6.0, 7.0)) -> dict:
    by_asset = {"gas-a": sum(gas), "wind-a": sum(demand) - sum(gas)}
    return {"year": 2025, "market": {
        "total_demand_mwh": sum(demand), "generation_mwh_by_asset": by_asset,
        "total_generation_mwh": sum(by_asset.values()), "period_summaries": [{}, {}],
    }}


def _check(report: dict, check_id: str) -> dict:
    return next(row for row in report["checks"] if row["id"] == check_id)


class StateChainToyTests(unittest.TestCase):
    def _evaluate(self, results, events, initial, *, network):
        with tempfile.TemporaryDirectory() as folder:
            return evaluate_run_invariants(
                Path(folder), year_results=results, expected_years=[2025, 2026], periods_per_year=2,
                initial_state_sha256=initial, network_expansion=network, events=events,
            )

    def test_consistent_chain_without_network_expansion_passes(self):
        initial, results, events = _chain()
        report = self._evaluate(results, events, initial, network=False)
        chain = _check(report, "run.state_chain")
        self.assertEqual(chain["status"], PASSED)
        self.assertEqual(chain["links_checked"], 8)

    def test_a_broken_hand_over_fails_without_network_expansion(self):
        initial, results, events = _chain()
        results[1]["extensions"]["annual_input_state_sha256"] = "0" * 64
        chain = _check(self._evaluate(results, events, initial, network=False), "run.state_chain")
        self.assertEqual(chain["status"], FAILED)
        self.assertIn("previous_state_is_annual_input", {row["link"] for row in chain["failed_links"]})

    def test_network_expansion_advance_sits_between_the_years(self):
        initial, results, events = _chain(network=True)
        chain = _check(self._evaluate(results, events, initial, network=True), "run.state_chain")
        self.assertEqual(chain["status"], PASSED)
        # The hand-over without the network advance is not the annual input.
        self.assertEqual(_check(self._evaluate(results, events, initial, network=False), "run.state_chain")["status"],
                         FAILED)
        broken = json.loads(json.dumps(events))
        next(row for row in broken if row["stage"] == "network_expansion.advance_year" and row["year"] == 2026)[
            "input_state_sha256"] = "f" * 64
        chain = _check(self._evaluate(results, broken, initial, network=True), "run.state_chain")
        self.assertEqual(chain["status"], FAILED)
        self.assertEqual([row["link"] for row in chain["failed_links"]], ["previous_state_is_network_advance_input"])

    def test_a_transition_event_must_record_the_next_state(self):
        initial, results, events = _chain()
        results[0]["next_state"]["assets"] = [{"asset_id": "edited"}]
        chain = _check(self._evaluate(results, events, initial, network=False), "run.state_chain")
        self.assertEqual(chain["status"], FAILED)


def _extension_chain(years=(2025, 2026), *, network=False, initialize_year=None):
    """F-D1: a typed chain whose first executed year starts from the state the
    extension initialize hook produced (source state + ``extension_state``)."""

    source = _state(years[0], "initial")
    initialize_year = years[0] if initialize_year is None else initialize_year
    previous = source
    results, events = [], []
    for year in years:
        extensions = {}
        if year == initialize_year:
            initialized = {**previous, "extensions": {"extension_state": {"value.toy-audit": {"years_seen": []}}}}
            extensions["extension_initialize"] = {
                "schema_version": "value.extension-initialize-link/v1", "year": year,
                "input_state_sha256": contract_hash(previous),
                "output_state_sha256": contract_hash(initialized),
            }
            previous = initialized
        if network:
            advanced = _state(year, f"network-{year}")
            extensions["network_expansion"] = {"advance": {"state": advanced}}
            events.append({"year": year, "stage": "network_expansion.advance_year",
                           "input_state_sha256": contract_hash(previous)})
            annual_input = contract_hash(advanced)
        else:
            annual_input = contract_hash(previous)
        extensions["annual_input_state_sha256"] = annual_input
        next_state = _state(year + 1, f"after-{year}")
        events.append({"year": year, "stage": "planning.advance_year", "input_state_sha256": annual_input})
        events.append({"year": year, "stage": "state_transition.apply",
                       "output_state_sha256": contract_hash(next_state)})
        results.append({"year": year, "extensions": extensions, "next_state": next_state, "market": {}})
        previous = next_state
    return contract_hash(source), results, events


class ExtensionInitializeChainTests(unittest.TestCase):
    """F-D1: the state chain origin of a run with selected extensions."""

    def _evaluate(self, results, events, initial, *, network=False, years=(2025, 2026), periods=2):
        with tempfile.TemporaryDirectory() as folder:
            return evaluate_run_invariants(
                Path(folder), year_results=results, expected_years=list(years), periods_per_year=periods,
                initial_state_sha256=initial, network_expansion=network, events=events,
            )

    def test_source_initialize_annual_input_chain_passes(self):
        initial, results, events = _extension_chain()
        chain = _check(self._evaluate(results, events, initial), "run.state_chain")
        self.assertEqual(chain["status"], PASSED, chain["failed_links"])
        self.assertEqual(chain["links_checked"], 9)

    def test_without_the_initialize_link_the_pre_fix_mismatch_is_reported(self):
        initial, results, events = _extension_chain()
        del results[0]["extensions"]["extension_initialize"]
        chain = _check(self._evaluate(results, events, initial), "run.state_chain")
        self.assertEqual(chain["status"], FAILED)
        self.assertEqual([(row["link"], row["year"]) for row in chain["failed_links"]],
                         [("previous_state_is_annual_input", 2025)])

    def test_tampered_initialize_input_or_output_fails(self):
        initial, results, events = _extension_chain()
        tampered = json.loads(json.dumps(results))
        tampered[0]["extensions"]["extension_initialize"]["input_state_sha256"] = "a" * 64
        chain = _check(self._evaluate(tampered, events, initial), "run.state_chain")
        self.assertEqual([row["link"] for row in chain["failed_links"]],
                         ["previous_state_is_extension_initialize_input"])
        tampered = json.loads(json.dumps(results))
        tampered[0]["extensions"]["extension_initialize"]["output_state_sha256"] = "b" * 64
        chain = _check(self._evaluate(tampered, events, initial), "run.state_chain")
        self.assertEqual([row["link"] for row in chain["failed_links"]], ["previous_state_is_annual_input"])
        tampered = json.loads(json.dumps(results))
        del tampered[0]["extensions"]["extension_initialize"]["output_state_sha256"]
        chain = _check(self._evaluate(tampered, events, initial), "run.state_chain")
        self.assertEqual(chain["status"], FAILED)

    def test_initialize_then_network_expansion_advance(self):
        initial, results, events = _extension_chain(network=True)
        chain = _check(self._evaluate(results, events, initial, network=True), "run.state_chain")
        self.assertEqual(chain["status"], PASSED, chain["failed_links"])

    def test_resumed_run_re_records_initialize_on_the_resumed_year(self):
        initial, results, events = _extension_chain(years=(2025, 2026, 2027))
        # The resumed part re-runs initialize on the 2026 checkpoint; a
        # deterministic initialize leaves the namespace unchanged.
        checkpoint = contract_hash(results[0]["next_state"])
        results[1]["extensions"]["extension_initialize"] = {
            "input_state_sha256": checkpoint, "output_state_sha256": checkpoint,
        }
        chain = _check(self._evaluate(results, events, initial, years=(2025, 2026, 2027)), "run.state_chain")
        self.assertEqual(chain["status"], PASSED, chain["failed_links"])

    def test_full_year_annual_path_over_the_whole_horizon(self):
        # The annual (17520-period) execution path for 2025-2050 without a
        # ledger: every other check is not evaluated, the state chain must
        # pass, and the summary must not be failed.
        years = tuple(range(2025, 2051))
        initial, results, events = _extension_chain(years=years)
        report = self._evaluate(results, events, initial, years=years, periods=17520)
        self.assertEqual(report["execution_scope"], "annual")
        self.assertEqual(report["periods_per_year"], 17520)
        chain = _check(report, "run.state_chain")
        self.assertEqual(chain["status"], PASSED, chain["failed_links"])
        self.assertEqual(chain["links_checked"], 4 * len(years) + 1)
        self.assertNotIn("run.state_chain", report["failed_checks"])
        self.assertNotEqual(report["status"], FAILED)
        # Pre-fix origin (application passing the source hash with no link):
        del results[0]["extensions"]["extension_initialize"]
        report = self._evaluate(results, events, initial, years=years, periods=17520)
        self.assertIn("run.state_chain", report["failed_checks"])


class LedgerCrossPathTests(unittest.TestCase):
    def _evaluate(self, output: Path, typed: dict) -> dict:
        return evaluate_run_invariants(output, year_results=[typed], expected_years=[2025], periods_per_year=2,
                                       execution_scope="psm_only")

    def _tally(self, output: Path, *, demand_delta=0.0, forecast=(11.0, 12.5), authority="chronology"):
        record_input_tally(output, input_tally(year=2025, demand_mwh=(10.0, 12.0 + demand_delta),
                                               forecast_demand_mwh=forecast, source="toy",
                                               demand_authority=authority))

    def test_input_tally_reconciles_with_ledger_and_typed_result(self):
        with tempfile.TemporaryDirectory() as folder:
            output = _ledger_run(Path(folder))
            self._tally(output)
            report = self._evaluate(output, _typed())
        demand = _check(report, "run.demand_input_reconciliation")
        self.assertEqual(demand["status"], PASSED)
        self.assertEqual({row["path"] for row in demand["comparisons"]},
                         {"ledger.period_summary", "typed.market.total_demand_mwh"})
        self.assertEqual(_check(report, "run.period_coverage")["status"], PASSED)
        self.assertEqual(_check(report, "run.state_chain")["status"], NOT_APPLICABLE)
        self.assertEqual(report["status"], PASSED)
        self.assertEqual((report["checks_passed"], report["checks_total"]), (2, 2))

    def test_an_input_tally_deviation_of_one_thousandth_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            output = _ledger_run(Path(folder))
            self._tally(output, demand_delta=1e-3)
            report = self._evaluate(output, _typed())
        demand = _check(report, "run.demand_input_reconciliation")
        self.assertEqual(demand["status"], FAILED)
        failing = [row for row in demand["comparisons"] if row["status"] == FAILED]
        self.assertEqual({row["path"] for row in failing}, {"ledger.period_summary", "typed.market.total_demand_mwh"})
        self.assertAlmostEqual(failing[0]["difference"], -1e-3)
        self.assertEqual(report["status"], FAILED)
        self.assertEqual(report["failed_checks"], ["run.demand_input_reconciliation"])

    def test_a_forecast_deviation_fails_and_missing_tally_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as folder:
            output = _ledger_run(Path(folder))
            self._tally(output, forecast=(11.0, 12.6))
            self.assertEqual(_check(self._evaluate(output, _typed()), "run.demand_input_reconciliation")["status"],
                             FAILED)
        with tempfile.TemporaryDirectory() as folder:
            output = _ledger_run(Path(folder))
            report = self._evaluate(output, _typed())
        self.assertEqual(_check(report, "run.demand_input_reconciliation")["reason_code"],
                         "GF_INVARIANT_INPUT_TALLY_MISSING")
        self.assertEqual(report["status"], NOT_EVALUATED)

    def test_zonal_demand_authority_is_not_reconciled_with_the_chronology(self):
        with tempfile.TemporaryDirectory() as folder:
            output = _ledger_run(Path(folder))
            self._tally(output, demand_delta=5.0, authority="network_pack:scenario_scaled_zonal_shares")
            demand = _check(self._evaluate(output, _typed()), "run.demand_input_reconciliation")
        self.assertEqual((demand["status"], demand["reason_code"]),
                         (NOT_EVALUATED, "GF_INVARIANT_DEMAND_AUTHORITY_NOT_CHRONOLOGY"))

    def test_generation_cross_path_compares_assets_and_ignores_storage_outside_the_typed_map(self):
        with tempfile.TemporaryDirectory() as folder:
            output = _ledger_run(Path(folder))
            good = _check(self._evaluate(output, _typed()), "run.generation_cross_path")
            typed = _typed()
            typed["market"]["generation_mwh_by_asset"]["gas-a"] += 0.01
            typed["market"]["total_generation_mwh"] += 0.01
            bad = _check(self._evaluate(output, typed), "run.generation_cross_path")
            missing = _typed()
            del missing["market"]["generation_mwh_by_asset"]["wind-a"]
            missing["market"]["total_generation_mwh"] = 13.0
            absent = _check(self._evaluate(output, missing), "run.generation_cross_path")
            with_storage = _typed()
            with_storage["market"]["generation_mwh_by_asset"]["battery-a"] = 2.0
            with_storage["market"]["total_generation_mwh"] += 2.0
            storage = _check(self._evaluate(output, with_storage), "run.generation_cross_path")
        self.assertEqual((good["status"], good["assets_compared"]), (PASSED, 2))
        self.assertEqual(bad["status"], FAILED)
        self.assertEqual(bad["mismatches"][0]["asset_id"], "gas-a")
        self.assertEqual(absent["status"], FAILED)  # ledger generation the typed result does not carry
        self.assertEqual(storage["status"], PASSED)  # a typed storage asset is compared with its discharge rows

    def test_an_uncheckpointed_ledger_is_not_read(self):
        with tempfile.TemporaryDirectory() as folder:
            output = _ledger_run(Path(folder))
            self._tally(output)
            (output / "market" / "market.sqlite-wal").write_bytes(b"pending frames")
            report = self._evaluate(output, _typed())
        self.assertEqual(_check(report, "run.generation_cross_path")["reason_code"],
                         "GF_INVARIANT_LEDGER_UNCHECKPOINTED_WAL")
        self.assertEqual(_check(report, "run.period_coverage")["typed_periods"], 2)

    def test_without_a_ledger_nothing_is_claimed(self):
        with tempfile.TemporaryDirectory() as folder:
            report = self._evaluate(Path(folder), {"year": 2025, "market": {}})
        self.assertEqual(report["status"], NOT_EVALUATED)
        self.assertEqual(report["checks_passed"], 0)

    def test_summary_semantics(self):
        self.assertEqual(summarise([])["status"], NOT_EVALUATED)
        self.assertEqual(summarise([{"id": "a", "class": "integrity", "status": PASSED}])["status"], NOT_EVALUATED)
        self.assertEqual(summarise([{"id": "a", "class": "cross_path", "status": PASSED},
                                    {"id": "b", "class": "integrity", "status": NOT_APPLICABLE}])["status"], PASSED)
        self.assertEqual(summarise([{"id": "a", "class": "cross_path", "status": PASSED},
                                    {"id": "b", "class": "integrity", "status": NOT_EVALUATED}])["status"], NOT_EVALUATED)


class ParityV3Tests(unittest.TestCase):
    def test_recompute_check(self):
        self.assertTrue(recompute_check({"actual": 1.0, "expected": 1.0 + 1e-9, "absolute_tolerance": 1e-6}))
        self.assertFalse(recompute_check({"actual": 1.0, "expected": 1.001, "absolute_tolerance": 1e-6}))
        self.assertFalse(recompute_check({"actual": float("nan"), "expected": 1.0, "absolute_tolerance": 1.0}))
        self.assertTrue(recompute_check({"actual": ["a"], "expected": ["a"]}))
        self.assertIsNone(recompute_check({"metric": "x"}))

    def test_native_parity_records_executed_checks_only(self):
        with tempfile.TemporaryDirectory() as folder:
            output = _ledger_run(Path(folder))
            (output / "market" / "metadata.json").write_text(json.dumps({"rows": {"period_summary": 2}}), "utf-8")
            (output / "orchestrator-events.jsonl").write_text(json.dumps({"year": 2025, "stage": "psm.run"}) + "\n", "utf-8")
            report = build_native_parity_report(
                output, year_results=[_typed()], expected_years=[2025], periods_per_year=2,
                selected_psm="toy", execution_scope="psm_only",
            )
            (output / "market" / "metadata.json").write_text(json.dumps({"rows": {"period_summary": 3}}), "utf-8")
            wrong = build_native_parity_report(
                output, year_results=[_typed()], expected_years=[2025], periods_per_year=2,
                selected_psm="toy", execution_scope="psm_only",
            )
        self.assertEqual(report["schema_version"], "value.stage-parity-report/v3")
        self.assertTrue(report["contract_parity_passed"])
        self.assertEqual(report["checks_total"], 3)
        self.assertTrue(all(row["class"] == "contract" for row in report["checks"]))
        self.assertEqual(report["market_evidence"]["energy_balance"]["status"], "not_evaluated")
        self.assertFalse(wrong["contract_parity_passed"])
        self.assertEqual(wrong["first_divergence"]["metric"], "period_row_count")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ApplicationValidationIntegrationTests(unittest.TestCase):
    """The real application path on the derived VALUE 101 fixtures (one subprocess each)."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix="p04-s2-")
        cls.runs = {}
        for name, mode in (("baseline", "two_year_smoke"), ("overshoot", "two_year_smoke"),
                           ("overshoot", "value_101_day")):
            cls.runs[(name, mode)] = p04_variants.run_variant(name, Path(cls.folder) / f"{name}-{mode}", mode=mode)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def test_two_year_smoke_v3_contract_gate_passes_with_executed_checks(self):
        output = self.runs[("baseline", "two_year_smoke")]
        parity = _read(output / "parity" / "stage-parity.json")
        validation = _read(output / "validation" / "scientific-validation.json")
        invariants = _read(output / "validation" / "run-invariants.json")
        self.assertEqual(parity["schema_version"], "value.stage-parity-report/v3")
        self.assertTrue(parity["contract_parity_passed"])
        self.assertGreaterEqual(parity["checks_total"], 6)
        self.assertEqual({row["metric"] for row in parity["checks"]},
                         {"typed_result_years", "core_stage_order", "period_row_count", "years",
                          "included_lines_equal_cem_system_cost"})
        self.assertEqual(validation["schema_version"], "value.scientific-validation/v2")
        self.assertEqual(validation["contract_validation_status"], "passed")
        self.assertEqual(validation["contract_validation"]["checks_total"], parity["checks_total"])
        self.assertEqual(invariants["status"], "passed")
        self.assertEqual({row["id"] for row in invariants["checks"]},
                         {"run.period_coverage", "run.demand_input_reconciliation",
                          "run.generation_cross_path", "run.state_chain"})
        self.assertTrue(all(row["status"] == "passed" for row in invariants["checks"]))
        tallies = sorted(path.name for path in (output / "validation" / "input-tally").glob("*.json"))
        self.assertEqual(tallies, ["year-2025.json", "year-2026.json"])
        # No surplus routing yet (S5): the legacy envelope can never pass.
        self.assertEqual(validation["energy_balance_status"], "not_evaluated")
        self.assertEqual(validation["raw_invariants"]["status"], "not_evaluated")
        self.assertEqual(validation["scientific_validation_status"], "not_evaluated")  # 2 periods per year
        self.assertEqual(validate_run_bundle(output)["errors"], [])

    def test_overshoot_two_year_smoke_reports_four_stress_periods(self):
        output = self.runs[("overshoot", "two_year_smoke")]
        validation = _read(output / "validation" / "scientific-validation.json")
        balance = validation["energy_balance"]
        # P0-4 S6: the adjustment absorbs numerical noise only (HEAD: 4 periods).
        self.assertEqual(balance["compatibility_adjustment_periods"], 0)
        # P0-4 S7, decision A2: the shortfall is booked as unserved energy, so
        # the gated account closes; the raw boundary verdict stays as evidence.
        self.assertEqual(validation["energy_balance_status"], "passed")
        self.assertEqual(balance["raw_boundary_status"], "failed")
        self.assertEqual(balance["gate_basis"], "a2_balance_account")
        self.assertEqual(balance["balance_account"]["open_periods"], 0)
        self.assertEqual(balance["severity"], "gate")
        self.assertEqual(validation["stress"]["stress_periods"], 4)
        self.assertEqual(validation["stress"]["forecast_above_supply_stress_periods"], 4)  # DEV-BAL-02 shape
        self.assertIn("GF_STRESS_EVENTS_RECORDED", {row["code"] for row in validation["validation_warnings"]})
        self.assertNotIn("GF_ENERGY_BALANCE_FAILED", {row["code"] for row in validation["validation_warnings"]})
        # The fixture runs the doctoral market rule set under the corrected
        # (production) profile: its storage throughput fails the gate.
        self.assertEqual(validation["validation_gate"]["policy"], "production")
        gates = validation["validation_gate"]["gates"]
        self.assertEqual(validation["raw_invariants"]["status"], "failed" if "failed" in gates.values() else "passed")
        parity = _read(output / "parity" / "stage-parity.json")
        self.assertTrue(parity["contract_parity_passed"])  # the contract itself; gates live in the v2 report
        self.assertEqual(parity["market_evidence"]["energy_balance"]["compatibility_adjustment_periods"], 0)
        oracle = _read(output / "validation" / "energy-balance-oracle.json")
        self.assertEqual(oracle["ledger"]["artifact"], "market/market.sqlite")
        self.assertNotIn(str(output), json.dumps(oracle))
        digest = hashlib.sha256((output / "market" / "market.sqlite").read_bytes()).hexdigest()
        self.assertEqual(oracle["ledger"]["source_artifact_sha256"], digest)

    def test_value_101_day_contract_is_recomputed(self):
        output = self.runs[("overshoot", "value_101_day")]
        validation = _read(output / "validation" / "scientific-validation.json")
        self.assertEqual(validation["execution_scope"], "psm_only")
        self.assertEqual(validation["contract_validation_status"], "passed")
        self.assertEqual(validation["analytical_mechanism_status"], "not_evaluated")
        # P0-4 S7 (production policy): the doctoral kernel charges and
        # discharges a store in one period (P5-03), which fails the storage
        # gate and with it the run; the energy balance closes (A2).
        self.assertEqual(validation["energy_balance_status"], "passed")
        self.assertEqual(validation["storage_invariant_status"], "failed")
        self.assertIn("storage.single_direction", validation["storage_invariants"]["failed_checks"])
        self.assertEqual(validation["validation_gate"]["status"], "failed")
        self.assertEqual(validation["scientific_validation_status"], "failed")
        self.assertFalse(validation["annual_economics_eligible"])
        self.assertIn("GF_VALIDATION_GATE_FAILED", {row["code"] for row in validation["validation_warnings"]})
        self.assertFalse(validation["cem_stages_executed"])
        self.assertEqual(validation["stress"]["stress_periods"], 48)
        self.assertAlmostEqual(validation["stress"]["shortfall_mwh"], 810.546171074, places=6)
        self.assertEqual(validation["energy_balance"]["compatibility_adjustment_periods"], 0)  # P0-4 S6
        invariants = _read(output / "validation" / "run-invariants.json")
        self.assertEqual(invariants["status"], "passed")
        self.assertEqual(_check(invariants, "run.state_chain")["status"], "not_applicable")

    def test_bundle_validator_recomputes_the_stored_statuses(self):
        source = self.runs[("baseline", "two_year_smoke")]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "bundle"
            shutil.copytree(source, output)
            path = output / "validation" / "scientific-validation.json"
            report = _read(path)
            report["energy_balance_status"] = "passed"
            path.write_text(json.dumps(report), encoding="utf-8")
            errors = validate_run_bundle(output)["errors"]
        codes = {(row["code"], row.get("field")) for row in errors}
        self.assertIn(("GF_BUNDLE_VALIDATION_STATUS_MISMATCH", "energy_balance_status"), codes)

    def test_scientific_report_is_rebuilt_identically_from_the_bundle(self):
        output = self.runs[("overshoot", "two_year_smoke")]
        stored = _read(output / "validation" / "scientific-validation.json")
        rebuilt = build_scientific_validation_report(
            mode=stored["mode"], periods_per_year=stored["periods_per_year"],
            parity_report=_read(output / "parity" / "stage-parity.json"),
            retained_comparison_role=stored["retained_numerical_comparison_role"],
            run_invariants=_read(output / "validation" / "run-invariants.json"),
            energy_balance=_read(output / "validation" / "energy-balance-oracle.json"),
        )
        for field in ("contract_validation_status", "run_invariant_status", "energy_balance_status",
                      "raw_invariants", "stress", "validation_warnings", "scientific_validation_status"):
            self.assertEqual(rebuilt[field], stored[field], field)


if __name__ == "__main__":
    unittest.main()
