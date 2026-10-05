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
        self.assertEqual(
            (dynamic["scientific_scenario_status"], dynamic["retained_numerical_comparison_status"], dynamic["retained_comparison_role"]),
            ("passed", "expected_difference", "informational_scenario_difference"),
        )
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
        self.assertEqual(ids, ["VALUE-ADV-2026-10-04-REVIEW", "GF_VALIDATION_LEGACY_REPORT"])
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
        self.assertEqual(run["scientific_scenario_status"], "passed")
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


class PublicationTests(unittest.TestCase):
    def test_raw_invariant_evidence_decides_doctoral_publication(self):
        doctoral = resolve_methodology(REFERENCE_PROFILE_ID).to_dict()
        corrected = resolve_methodology().to_dict()
        root = Path("/nonexistent-run")
        self.assertEqual(result_publication({"methodology": corrected}, root)["status"], "published")
        self.assertEqual(result_publication({}, root)["status"], "published")
        cases = [
            ({}, "withheld", "not_evaluated"),
            ({"raw_invariants": {"status": "passed"}}, "published", "passed"),
            ({"raw_invariants": {"status": "failed"}}, "withheld", "failed"),
            ({"run_invariant_status": "passed", "energy_balance_status": "reproduction_conformant"}, "published", "passed"),
            ({"run_invariant_status": "passed", "energy_balance_status": "reproduction_with_declared_deviations"}, "withheld", "failed"),
            ({"run_invariant_status": "passed"}, "withheld", "not_evaluated"),
        ]
        for evidence, status, verdict in cases:
            with self.subTest(evidence=evidence):
                publication = result_publication({"methodology": doctoral, **evidence}, root)
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
