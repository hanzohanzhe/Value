"""Read-time scientific status, advisories and result publication (X0 S10a/S10b)."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gridform_core import methodology
from gridform_core import result_advisories
from gridform_core.methodology import REFERENCE_PROFILE_ID, resolve_methodology
from gridform_core.result_advisories import (
    evaluate_advisories,
    present_scientific_status,
    result_publication,
    withhold_annual_results,
)
from gridform_core.results_summary import build_run_summary, compare_run_summaries

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "runs"


def _validation(**fields):
    return {
        "schema_version": "value.scientific-validation/v1",
        "execution_status": "passed",
        "contract_validation_status": "passed",
        "analytical_mechanism_status": "passed",
        "retained_numerical_comparison_status": "failed",
        "scientific_validation_status": "failed",
        **fields,
    }


def _v2_validation(**fields):
    """A recomputed (P0-4 S2) report; its evidence fields are authoritative."""

    return {
        "schema_version": "value.scientific-validation/v2",
        "execution_status": "passed",
        "contract_validation_status": "passed",
        "analytical_mechanism_status": "passed",
        "retained_numerical_comparison_role": "informational_scenario_difference",
        "retained_numerical_comparison_status": "expected_difference",
        "scientific_validation_status": "passed",
        "run_invariant_status": "not_evaluated",
        "energy_balance_status": "not_evaluated",
        **fields,
    }


def _run_with_report(folder: Path, report: dict) -> Path:
    path = folder / "model-output" / "validation" / "scientific-validation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return folder


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    """sha256 and mtime_ns of every file under ``root``."""

    return {
        path.relative_to(root).as_posix(): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


class PresentScientificStatusTests(unittest.TestCase):
    def _present(self, policy, *, mode="full", validation=None, recorded=True):
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder)
            path = run_root / "model-output" / "validation" / "scientific-validation.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(validation if validation is not None else _validation()), encoding="utf-8")
            run = {"id": "run", "mode": mode, "modules": {"storage_cost": policy}, "results": []}
            if recorded:
                run["methodology"] = resolve_methodology().to_dict()
            return present_scientific_status(run, run_root)

    def test_moved_rules_are_unchanged_for_a_recorded_run(self):
        dynamic = self._present("dynamic-annual-storage-cost")
        # P0-4 S3: the scenario reading of a v1 report is computed as before,
        # but a passed claim resting on it is superseded even when the run
        # recorded its methodology (P7-01: v1 contract "passed" was a literal).
        self.assertEqual(
            (dynamic["scientific_scenario_status"], dynamic["retained_numerical_comparison_status"], dynamic["retained_comparison_role"]),
            ("superseded_pre_fix", "expected_difference", "informational_scenario_difference"),
        )
        self.assertEqual(dynamic["recorded_validation_statuses"], {"scientific_scenario_status": "passed"})
        legacy = self._present("value-legacy-storage-tariff")
        self.assertEqual(
            (legacy["scientific_scenario_status"], legacy["retained_numerical_comparison_status"], legacy["retained_comparison_role"]),
            ("failed", "failed", "required_reproduction_gate"),
        )
        short = self._present("dynamic-annual-storage-cost", mode="smoke")
        self.assertEqual(short["scientific_scenario_status"], "failed")
        missing = self._present("dynamic-annual-storage-cost", validation=[])
        self.assertEqual(missing["scientific_scenario_status"], "not_evaluated")
        self.assertEqual(missing["retained_numerical_comparison_status"], "not_evaluated")

    def test_v2_report_is_presented_as_recomputed_without_a_forced_pass(self):
        # A v2 report decides the scenario status itself; the alternative
        # storage policy no longer turns it into "passed" (P0-4 S3).
        not_evaluated = self._present("dynamic-annual-storage-cost", validation=_v2_validation(
            scientific_validation_status="not_evaluated"))
        self.assertEqual(not_evaluated["scientific_scenario_status"], "not_evaluated")
        self.assertNotIn("recorded_validation_statuses", not_evaluated)
        passed = self._present("dynamic-annual-storage-cost", validation=_v2_validation(
            run_invariant_status="passed", energy_balance_status="failed",
            stress={"stress_periods": 4, "shortfall_mwh": 47.35, "shortfall_basis": "lower_bound"},
            validation_warnings=[{"code": "GF_ENERGY_BALANCE_FAILED"}]))
        self.assertEqual(passed["scientific_scenario_status"], "passed")
        self.assertEqual((passed["run_invariant_status"], passed["energy_balance_status"]), ("passed", "failed"))
        self.assertEqual(passed["stress"]["stress_periods"], 4)
        self.assertEqual(passed["validation_evidence"]["source"], "scientific_validation_v2")
        self.assertNotIn("GF_VALIDATION_LEGACY_REPORT", {row["id"] for row in passed["advisories"]})

    def test_copied_status_evidence_without_a_v2_report_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as folder:
            run_root = _run_with_report(Path(folder), _validation())
            run = {"id": "run", "mode": "full", "status": "completed", "modules": {}, "results": [],
                   "methodology": resolve_methodology(REFERENCE_PROFILE_ID).to_dict(),
                   "raw_invariants": {"status": "passed"}, "energy_balance_status": "passed",
                   "run_invariant_status": "passed"}
            presented = present_scientific_status(run, run_root)
        self.assertEqual(presented["energy_balance_status"], "not_evaluated")
        self.assertEqual(presented["run_invariant_status"], "not_evaluated")
        self.assertEqual(presented["raw_invariants"]["status"], "not_evaluated")
        self.assertEqual(presented["result_publication"]["status"], "withheld")
        self.assertIn("GF_VALIDATION_LEGACY_REPORT", {row["code"] for row in presented["validation_warnings"]})

    def test_pre_profile_positive_claims_are_superseded_and_kept(self):
        run = self._present("dynamic-annual-storage-cost", recorded=False)
        self.assertEqual(run["scientific_scenario_status"], "superseded_pre_fix")
        self.assertEqual(run["recorded_validation_statuses"], {"scientific_scenario_status": "passed"})
        self.assertEqual(run["methodology"], {"status": "not_recorded", "profile_id": None})
        self.assertIn("VALUE-ADV-2026-10-04-REVIEW", {row["id"] for row in run["advisories"]})
        self.assertTrue(run["advisory_summary"]["needs_review"])
        legacy = self._present("value-legacy-storage-tariff", recorded=False)
        self.assertEqual(legacy["scientific_scenario_status"], "failed")
        self.assertNotIn("recorded_validation_statuses", legacy)

    def test_unresolved_methodology_is_not_treated_as_a_pre_fix_run(self):
        with tempfile.TemporaryDirectory() as folder:
            run = {"id": "run", "mode": "full", "modules": {}, "results": [],
                   "scientific_validation_status": "passed",
                   "methodology": {"schema_version": "value.methodology/v1", "status": "unresolved",
                                   "error": "Unknown methodology profile 'typo'"}}
            presented = present_scientific_status(run, Path(folder))
        self.assertEqual(presented["methodology"]["status"], "unresolved")
        self.assertIn("typo", presented["methodology"]["error"])
        self.assertEqual(presented["scientific_validation_status"], "passed")
        self.assertNotIn("recorded_validation_statuses", presented)
        self.assertNotIn("VALUE-ADV-2026-10-04-REVIEW", {row["id"] for row in presented["advisories"]})

    def test_server_present_run_uses_the_shared_function(self):
        from backend import server

        with patch.object(server, "present_scientific_status", wraps=present_scientific_status) as spy, \
                tempfile.TemporaryDirectory() as folder, patch.object(server, "RUNS_ROOT", Path(folder)):
            (Path(folder) / "run").mkdir()
            server.present_run({"id": "run", "mode": "full", "modules": {}, "results": []})
        self.assertEqual(spy.call_count, 1)


class FixtureRunTests(unittest.TestCase):
    """The committed fixture runs are read through every presentation path; nothing on disk changes."""

    def setUp(self):
        self.before = _snapshot(FIXTURES)

    def tearDown(self):
        self.assertEqual(_snapshot(FIXTURES), self.before, "a read-time presentation wrote to a run directory")

    def _present_run(self, run_id):
        from backend import server

        status = json.loads((FIXTURES / run_id / "status.json").read_text(encoding="utf-8"))
        with patch.object(server, "RUNS_ROOT", FIXTURES):
            return server.present_run(status)

    def test_pre_fix_passed_run_is_superseded_with_advisories(self):
        run = self._present_run("pre-fix-dynamic-full")
        self.assertEqual(run["scientific_scenario_status"], "superseded_pre_fix")
        self.assertEqual(run["recorded_validation_statuses"]["scientific_scenario_status"], "passed")
        self.assertEqual(run["contract_validation_status"], "superseded_pre_fix")
        self.assertEqual(run["recorded_validation_statuses"]["contract_validation_status"], "passed")
        self.assertEqual(run["scientific_validation_status"], "failed")
        ids = [row["id"] for row in run["advisories"]]
        # P0-5a: a pre-fix run of the retained kernel PSM also gets the P6-24
        # interconnector-clock advisory of p05.interconnector-clock.
        # P0-6: a pre-fix default-PSM Run also did not apply the corrected
        # market rules; each one with an advisory is listed (severity order).
        self.assertEqual(ids, [
            "p05.interconnector-clock", "VALUE-ADV-2026-10-04-REVIEW",
            "p06.avoided-cost-downward-order", "p06.d1-surplus-accounting",
            "p06.storage-bid-cycle-only", "p06.storage-net-per-period",
            "GF_VALIDATION_LEGACY_REPORT",
            "p06.no-vre-pre-clearing-skim", "p06.storage-uniform-price-settlement",
        ])
        self.assertEqual(run["result_publication"]["status"], "published")
        self.assertEqual(len(run["results"]), 1)

    def test_pre_fix_failed_run_stays_failed(self):
        run = self._present_run("pre-fix-legacy-failed")
        self.assertEqual(run["scientific_scenario_status"], "failed")
        self.assertEqual(run["scientific_validation_status"], "failed")
        self.assertEqual(run["recorded_validation_statuses"], {"contract_validation_status": "passed"})
        self.assertIn("VALUE-ADV-2026-10-04-REVIEW", {row["id"] for row in run["advisories"]})

    def test_doctoral_run_without_raw_invariants_is_withheld(self):
        run = self._present_run("doctoral-no-invariants")
        self.assertEqual(run["methodology"]["profile_id"], REFERENCE_PROFILE_ID)
        # Its passed claim rests on a v1 report: superseded (P0-4 S3).
        self.assertEqual(run["scientific_scenario_status"], "superseded_pre_fix")
        self.assertEqual(run["recorded_validation_statuses"]["scientific_scenario_status"], "passed")
        self.assertNotIn("VALUE-ADV-2026-10-04-REVIEW", {row["id"] for row in run["advisories"]})
        publication = run["result_publication"]
        self.assertEqual(publication["status"], "withheld")
        self.assertEqual(publication["reason_code"], "GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED")
        self.assertEqual(publication["available_in"], ["inspect", "export"])
        self.assertEqual(run["results"], [])
        self.assertEqual(run["withheld_result_year_count"], 1)
        summary = build_run_summary(FIXTURES / "doctoral-no-invariants")
        self.assertEqual(summary["result_publication"]["status"], "withheld")

    def test_compact_listing_is_bounded_but_keeps_the_badges(self):
        from backend import server

        with patch.object(server, "RUNS_ROOT", FIXTURES):
            rows = {row["id"]: row for row in server.list_runs()}
        doctoral = rows["doctoral-no-invariants"]
        self.assertNotIn("advisories", doctoral)
        self.assertEqual(doctoral["methodology"]["profile_id"], REFERENCE_PROFILE_ID)
        self.assertEqual(set(doctoral["methodology"]), {"status", "profile_id", "profile_version", "label"})
        self.assertEqual(doctoral["result_publication"]["status"], "withheld")
        old = rows["pre-fix-dynamic-full"]
        self.assertEqual(old["scientific_scenario_status"], "superseded_pre_fix")
        self.assertTrue(old["advisory_summary"]["needs_review"])

    def test_summaries_and_comparisons_use_the_same_presentation(self):
        old = build_run_summary(FIXTURES / "pre-fix-dynamic-full")
        self.assertEqual(old["run"]["scientific_status"], "superseded_pre_fix")
        self.assertEqual(old["run"]["recorded_scientific_status"], "failed")
        self.assertEqual(old["methodology"]["status"], "not_recorded")
        failed = build_run_summary(FIXTURES / "pre-fix-legacy-failed")
        comparison = compare_run_summaries([old, failed])
        self.assertEqual(comparison["attribution_status"], "needs_review")
        reasons = {row["reason"] for row in comparison["attribution_review_reasons"]}
        self.assertEqual(reasons, {"advisory", "validation_failed"})
        self.assertFalse(comparison["causal_claim_allowed"])
        doctoral = build_run_summary(FIXTURES / "doctoral-no-invariants")
        mixed = compare_run_summaries([old, doctoral])
        reasons = {row["reason"] for row in mixed["attribution_review_reasons"]}
        self.assertIn("methodology_differs", reasons)
        self.assertIn("annual_results_withheld", reasons)
        self.assertTrue(mixed["annual_metrics_withheld"])

    def test_same_profile_id_with_another_identity_is_a_methodology_difference(self):
        first = build_run_summary(FIXTURES / "doctoral-no-invariants")
        second = json.loads(json.dumps(first))
        second["run"]["run_id"] = "other"
        self.assertNotIn("methodology_differs",
                         {row["reason"] for row in compare_run_summaries([first, second])["attribution_review_reasons"]})
        second["methodology"]["applied_corrections_sha256"] = "0" * 64
        reasons = compare_run_summaries([first, second])["attribution_review_reasons"]
        row = next(row for row in reasons if row["reason"] == "methodology_differs")
        self.assertEqual(row["differing_fields"], ["applied_corrections_sha256"])
        self.assertEqual(len(set(row["profile_ids"])), 1)


class WithheldAnnualResourceTests(unittest.TestCase):
    """Q14 is enforced by the server for every annual-result resource, not only by the run card."""

    def test_annual_resources_of_a_withheld_run_are_refused_and_half_hour_stays(self):
        import urllib.error
        import urllib.request

        from tests.local_api_harness import start_local_api

        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            run = home / "runs" / "doctoral-no-invariants"
            shutil.copytree(FIXTURES / "doctoral-no-invariants", run)
            (run / "model-output" / "market").mkdir()
            (run / "model-output" / "market" / "market.sqlite").write_bytes(b"")
            (run / "model-output" / "planning").mkdir()

            def call(path):
                try:
                    with urllib.request.urlopen(origin + path, timeout=30) as response:
                        return response.status, json.loads(response.read())
                except urllib.error.HTTPError as error:
                    return error.code, json.loads(error.read())

            with start_local_api(data_home=home) as (_httpd, origin, _token):
                base = "/api/runs/doctoral-no-invariants/"
                for resource in ("market/vre-summary", "planning/summary", "domains/network/summary?year=2025",
                                 "domains/expansion/summary", "network-redispatch/annual"):
                    with self.subTest(resource):
                        status, payload = call(base + resource)
                        self.assertEqual(status, 409, payload)
                        self.assertEqual(payload["status"], "withheld")
                        self.assertEqual(payload["reason_code"], result_advisories.WITHHELD_NOT_EVALUATED)
                        self.assertEqual(payload["available_in"], ["inspect", "export"])
                status, payload = call(base + "results/vre-curtailment?resolution=annual")
                self.assertEqual(status, 200, payload)
                self.assertEqual((payload["status"], payload["reason_code"]),
                                 ("withheld", result_advisories.WITHHELD_NOT_EVALUATED))
                self.assertEqual(payload["items"], [])
                _status, payload = call(base + "results/vre-curtailment?resolution=half_hour&year=2025")
                self.assertNotEqual(payload.get("reason_code"), result_advisories.WITHHELD_NOT_EVALUATED)
                status, payload = call(base.rstrip("/"))
                self.assertEqual(status, 200)
                self.assertEqual(payload["result_publication"]["status"], "withheld")

    def test_summary_of_a_withheld_run_carries_no_annual_result_artifact(self):
        planning = {"schema_version": "value.planning-ledger/v1", "years": [{"year": 2025, "commissioned_mw": 1200.0}]}
        attribution = {"schema_version": "value.vre-curtailment-attribution/v2", "annual": [{"year": 2025, "total_mwh": 5.0}]}
        terminal = {"terminal_policy": "x", "outstanding_project_count": 3, "outstanding_capacity_mw": 900.0}
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder) / "doctoral-no-invariants"
            shutil.copytree(FIXTURES / "doctoral-no-invariants", run)
            output = run / "model-output"
            for relative, payload in (("planning/summary.json", planning),
                                      ("network/vre-curtailment-attribution.json", attribution),
                                      ("terminal/terminal-state.json", terminal)):
                (output / relative).parent.mkdir(parents=True, exist_ok=True)
                (output / relative).write_text(json.dumps(payload), encoding="utf-8")
            withheld = build_run_summary(run)
            # Passing raw invariants come from a recomputed (v2) report.
            _run_with_report(run, _v2_validation(raw_invariants={"status": "passed"}))
            published = build_run_summary(run)
        self.assertEqual(withheld["result_publication"]["status"], "withheld")
        self.assertEqual(withheld["result_publication"]["withheld_fields"],
                         ["annual", "planning", "vre_curtailment_attribution", "terminal"])
        for field in ("planning", "vre_curtailment_attribution", "terminal"):
            with self.subTest(field):
                self.assertIsNone(withheld[field])
        self.assertEqual(withheld["annual"], [])
        self.assertNotIn("1200.0", json.dumps(withheld))
        self.assertNotIn("900.0", json.dumps(withheld))
        self.assertIn("comparison_identity", withheld)
        self.assertIn("comparison_eligibility", withheld)
        # The same run with passing raw invariants serves all three.
        self.assertEqual(published["result_publication"]["status"], "published")
        self.assertEqual(published["result_publication"]["withheld_fields"], [])
        self.assertEqual(published["planning"], planning)
        self.assertEqual(published["vre_curtailment_attribution"], attribution)
        self.assertEqual(published["terminal"]["outstanding_capacity_mw"], 900.0)

    def test_published_runs_are_not_gated(self):
        status = json.loads((FIXTURES / "doctoral-no-invariants" / "status.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder) / "doctoral-no-invariants"
            shutil.copytree(FIXTURES / "doctoral-no-invariants", run)
            _run_with_report(run, _v2_validation(raw_invariants={"status": "passed"}))
            self.assertIsNone(result_advisories.withheld_annual_result(run, "x", status))
        # A copied status claim alone does not publish (P0-4 S3).
        claimed = dict(status, raw_invariants={"status": "passed"})
        self.assertIsNotNone(result_advisories.withheld_annual_result(FIXTURES / "doctoral-no-invariants", "x", claimed))
        self.assertIsNone(result_advisories.withheld_annual_result(FIXTURES / "pre-fix-dynamic-full", "x"))
        self.assertIsNotNone(result_advisories.withheld_annual_result(FIXTURES / "doctoral-no-invariants", "x"))

    def test_value_101_rows_have_no_totals_for_a_withheld_run(self):
        from gridform_core.value_101_results import _row
        from tests.test_prompt114_value_101_results import write_fixture

        doctoral = json.loads((FIXTURES / "doctoral-no-invariants" / "status.json").read_text(encoding="utf-8"))["methodology"]
        with tempfile.TemporaryDirectory() as folder:
            published = write_fixture(Path(folder) / "published", run_id="published", kind="baseline", changed=[], scale=1.0)
            withheld = write_fixture(Path(folder) / "withheld", run_id="withheld", kind="baseline", changed=[], scale=1.0)
            status_path = Path(withheld) / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["methodology"] = doctoral
            status_path.write_text(json.dumps(status), encoding="utf-8")
            open_row, _, _ = _row(Path(published), expected_kind="baseline")
            row, _, _ = _row(Path(withheld), expected_kind="baseline")
        self.assertEqual(open_row["teaching_window_system_resource_cost_gbp"], 100.0)
        self.assertTrue(row["totals_withheld"])
        self.assertEqual(row["result_publication"]["reason_code"], result_advisories.WITHHELD_NOT_EVALUATED)
        self.assertFalse([key for key in row if key.startswith("teaching_window_")])


class PublicationTests(unittest.TestCase):
    def test_raw_invariant_evidence_decides_doctoral_publication(self):
        doctoral = resolve_methodology(REFERENCE_PROFILE_ID).to_dict()
        corrected = resolve_methodology().to_dict()
        root = Path("/nonexistent-run")
        self.assertEqual(result_publication({"methodology": corrected}, root)["status"], "published")
        self.assertEqual(result_publication({}, root)["status"], "published")
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        cases = [
            ({}, "withheld", "not_evaluated"),
            ({"raw_invariants": {"status": "passed"}}, "published", "passed"),
            ({"raw_invariants": {"status": "failed"}}, "withheld", "failed"),
            ({"run_invariant_status": "passed", "energy_balance_status": "reproduction_conformant"}, "published", "passed"),
            ({"run_invariant_status": "passed", "energy_balance_status": "reproduction_with_declared_deviations"}, "withheld", "failed"),
            ({"run_invariant_status": "passed"}, "withheld", "not_evaluated"),
        ]
        for index, (evidence, status, verdict) in enumerate(cases):
            with self.subTest(evidence=evidence):
                # The evidence is the run's v2 report (P0-4 S2), not status.json.
                run_root = _run_with_report(Path(folder) / f"run-{index}", _v2_validation(**evidence))
                if "energy_balance_status" not in evidence:
                    report = json.loads((run_root / "model-output" / "validation" / "scientific-validation.json").read_text())
                    report.pop("energy_balance_status")
                    report.pop("run_invariant_status", None) if "run_invariant_status" not in evidence else None
                    _run_with_report(run_root, report)
                publication = result_publication({"methodology": doctoral, "status": "completed"}, run_root)
                self.assertEqual((publication["status"], publication["raw_invariants_status"]), (status, verdict))
        withheld = withhold_annual_results({"result_publication": {"status": "withheld"}, "results": [{"year": 2025}]})
        self.assertEqual((withheld["results"], withheld["withheld_result_year_count"]), ([], 1))


class CorrectionAdvisoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        root = Path(folder) / "methodology"
        shutil.copytree(methodology.CATALOGUE_ROOT, root)
        path = root / "corrections" / "x0.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["corrections"].append({
            "id": "x0.toy-storage-cap", "package": "x0", "findings": ["P0-TEST"], "track": "universal",
            "scope": "kernel", "affects": ["accounting"],
            "applies_when": {"modules_any": ["value-storage-expansion-policy"], "modes_any": ["full", "two_year"]},
            "advisory": {"severity": "medium", "title": "Toy", "summary": "Toy advisory.", "affected_metrics": ["storage"]},
            "trigger_fixture": None, "introduced_in": "test",
        })
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.catalogue = methodology.load_catalogue_from(root)

    def test_unapplied_matching_corrections_become_advisories_after_id_normalisation(self):
        status = json.loads((FIXTURES / "pre-fix-dynamic-full" / "status.json").read_text(encoding="utf-8"))
        with patch.object(result_advisories, "load_catalogue", return_value=self.catalogue):
            rows = evaluate_advisories(status, FIXTURES / "pre-fix-dynamic-full")
            self.assertIn("x0.toy-storage-cap", [row["id"] for row in rows])
            toy = next(row for row in rows if row["id"] == "x0.toy-storage-cap")
            self.assertEqual((toy["source"], toy["findings"], toy["severity"]), ("correction", ["P0-TEST"], "medium"))
            applied = dict(status, methodology={
                **resolve_methodology(catalogue=self.catalogue).to_dict(),
            })
            self.assertNotIn("x0.toy-storage-cap", [row["id"] for row in evaluate_advisories(applied, FIXTURES / "pre-fix-dynamic-full")])
            other_mode = dict(status, mode="smoke")
            self.assertNotIn("x0.toy-storage-cap", [row["id"] for row in evaluate_advisories(other_mode, FIXTURES / "pre-fix-dynamic-full")])

    def test_generic_advisory_catalogue_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "advisories.json"
            payload = json.loads((methodology.CATALOGUE_ROOT / "advisories.json").read_text(encoding="utf-8"))
            payload["advisories"][0]["applies_to"] = "every_run"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(methodology.MethodologyCatalogError):
                result_advisories.load_generic_advisories_from(path)


if __name__ == "__main__":
    unittest.main()
