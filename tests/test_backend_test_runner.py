"""Tests for the fingerprinted unittest ratchet (scripts/run_backend_tests.py)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_backend_tests", ROOT / "scripts" / "run_backend_tests.py")
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)

TOY_MODULES = {
    "test_toy_pass": """
        import unittest
        class Passing(unittest.TestCase):
            def test_ok(self):
                self.assertTrue(True)
            @unittest.skip("not here")
            def test_skipped(self):
                pass
    """,
    "test_toy_fail": """
        import unittest
        class Failing(unittest.TestCase):
            def test_bad(self):
                self.assertEqual(1, 2)
            def test_good(self):
                pass
    """,
    "test_toy_error": """
        import unittest
        class Erroring(unittest.TestCase):
            def test_raises(self):
                raise KeyError("boom")
    """,
    "test_toy_import": """
        import module_that_does_not_exist_anywhere
    """,
    "test_toy_subtests": """
        import unittest
        class Sub(unittest.TestCase):
            def test_many(self):
                for index in range(3):
                    with self.subTest(index=index):
                        self.assertLess(index, 1)
            def test_all_pass(self):
                for index in range(3):
                    with self.subTest(index=index):
                        self.assertGreaterEqual(index, 0)
    """,
    "test_toy_setup_class": """
        import unittest
        class Broken(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise RuntimeError("fixture unavailable")
            def test_never_runs(self):
                pass
    """,
}

EXPECTED_FAILING = {
    "test_toy_fail.Failing.test_bad",
    "test_toy_error.Erroring.test_raises",
    "IMPORT:test_toy_import",
    "test_toy_subtests.Sub.test_many",
    "test_toy_setup_class.Broken.setUpClass",
}


class BackendTestRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.tests_dir = self.root / "toy_tests"
        self.tests_dir.mkdir()
        for name, body in TOY_MODULES.items():
            (self.tests_dir / f"{name}.py").write_text(textwrap.dedent(body), encoding="utf-8")
        self.baseline = self.root / "baseline.txt"
        self.quarantine = self.root / "quarantine.txt"
        self.report = self.root / "report.json"
        self.addCleanup(self._temporary.cleanup)

    def _main(self, *extra: str, milestone: str = "M0") -> tuple[int, dict]:
        arguments = [
            "--tests-dir", str(self.tests_dir),
            "--baseline", str(self.baseline),
            "--quarantine", str(self.quarantine),
            "--json-output", str(self.report),
            "--jobs", "4",
            *extra,
        ]
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"VALUE_P0_MILESTONE": milestone}), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = RUNNER.main(arguments)
        report = json.loads(self.report.read_text(encoding="utf-8")) if self.report.is_file() and "--update-baseline" not in extra else {}
        return code, report

    def _write_baseline(self, ids, fingerprint=None) -> None:
        RUNNER.write_baseline(self.baseline, fingerprint or RUNNER.environment_fingerprint(), {identifier: "" for identifier in ids})

    def test_ids_are_method_level_and_subtests_and_fixtures_are_merged(self) -> None:
        run = RUNNER.run_modules(sorted(TOY_MODULES), jobs=4, tests_dir=self.tests_dir)
        outcomes = run["outcomes"]
        self.assertEqual(RUNNER.failing_ids(outcomes), EXPECTED_FAILING)
        self.assertEqual(outcomes["test_toy_pass.Passing.test_ok"], "pass")
        self.assertEqual(outcomes["test_toy_pass.Passing.test_skipped"], "skip")
        self.assertEqual(outcomes["test_toy_fail.Failing.test_good"], "pass")
        self.assertEqual(outcomes["test_toy_subtests.Sub.test_all_pass"], "pass")
        # Two failing subTests collapse into one method id, no subTest suffix.
        self.assertEqual([key for key in outcomes if key.startswith("test_toy_subtests.Sub.test_many")], ["test_toy_subtests.Sub.test_many"])
        self.assertIn("ModuleNotFoundError", run["details"]["IMPORT:test_toy_import"])

    def test_matching_baseline_passes_and_a_new_failure_exits_one(self) -> None:
        self._write_baseline(EXPECTED_FAILING)
        code, report = self._main()
        self.assertEqual(code, 0, report)
        self.assertEqual(report["new_failures"], [])
        self.assertEqual(report["fixed_but_listed"], [])

        self._write_baseline(EXPECTED_FAILING - {"test_toy_fail.Failing.test_bad"})
        code, report = self._main()
        self.assertEqual(code, 1)
        self.assertEqual(report["new_failures"], ["test_toy_fail.Failing.test_bad"])

    def test_fixed_but_listed_exits_one_and_update_only_deletes(self) -> None:
        stale = "test_toy_pass.Passing.test_ok"
        self._write_baseline(EXPECTED_FAILING | {stale})
        code, report = self._main()
        self.assertEqual(code, 1)
        self.assertEqual(report["fixed_but_listed"], [stale])

        code, _ = self._main("--update-baseline")
        self.assertEqual(code, 0)
        self.assertEqual(RUNNER.read_baseline(self.baseline).ids, EXPECTED_FAILING)

    def test_update_refuses_to_add_without_allow_add_and_reason(self) -> None:
        self._write_baseline(EXPECTED_FAILING - {"IMPORT:test_toy_import"})
        code, _ = self._main("--update-baseline")
        self.assertEqual(code, 1)
        self.assertNotIn("IMPORT:test_toy_import", RUNNER.read_baseline(self.baseline).ids)
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                self._main("--update-baseline", "--allow-add")
        code, _ = self._main("--update-baseline", "--allow-add", "--reason", "toy import failure")
        self.assertEqual(code, 0)
        baseline = RUNNER.read_baseline(self.baseline)
        self.assertIn("IMPORT:test_toy_import", baseline.ids)
        self.assertIn("toy import failure", baseline.entries["IMPORT:test_toy_import"])

    def test_fingerprint_mismatch_reports_and_fails_only_in_strict_mode(self) -> None:
        fingerprint = dict(RUNNER.environment_fingerprint(), numpy="0.0.0-other")
        self._write_baseline(EXPECTED_FAILING, fingerprint)
        code, report = self._main()
        self.assertEqual(code, 0)
        self.assertIn("numpy", report["fingerprint_differences"])
        code, report = self._main("--strict")
        self.assertEqual(code, 1)
        self.assertTrue(any("fingerprint" in error for error in report["errors"]))

    def test_quarantine_is_excluded_from_ratchet_until_it_expires(self) -> None:
        self._write_baseline(EXPECTED_FAILING - {"test_toy_error.Erroring.test_raises"})
        self.quarantine.write_text(
            "test_toy_error.Erroring.test_raises | reason=toy host dependency | owner=X0 | expires=M2\n",
            encoding="utf-8",
        )
        code, report = self._main(milestone="M1")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["quarantined_failing"], ["test_toy_error.Erroring.test_raises"])
        code, report = self._main(milestone="M3")
        self.assertEqual(code, 1)
        self.assertEqual(report["expired_quarantine"], ["test_toy_error.Erroring.test_raises"])

    def test_quarantine_entries_require_reason_owner_and_known_milestone(self) -> None:
        self.quarantine.write_text("a.B.c | reason=x | expires=M1\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            RUNNER.read_quarantine(self.quarantine)
        self.quarantine.write_text("a.B.c | reason=x | owner=y | expires=M99\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            RUNNER.read_quarantine(self.quarantine)

    def test_expiry_is_valid_through_and_host_entries_never_expire(self) -> None:
        entries = {
            "a.B.through_m2": {"reason": "r", "owner": "o", "expires": "M2"},
            "a.B.host": {"reason": "r", "owner": "o", "expires": RUNNER.HOST_EXPIRY},
        }
        self.assertEqual(RUNNER.expired_quarantine(entries, "M2"), [])
        self.assertEqual(RUNNER.expired_quarantine(entries, "M3"), ["a.B.through_m2"])
        self.assertEqual(RUNNER.expired_quarantine(entries, "M8"), ["a.B.through_m2"])
        self.quarantine.write_text("a.B.c | reason=x | owner=y | expires=host\n", encoding="utf-8")
        self.assertEqual(RUNNER.read_quarantine(self.quarantine)["a.B.c"]["expires"], "host")

    def test_golden_family_tests_are_never_baselined_or_quarantined(self) -> None:
        for identifier in (
            "test_golden_doctoral.GoldenDoctoralFamilyTests.test_fast_cases_match_latest_revision",
            "IMPORT:test_golden_corrected",
        ):
            self.assertTrue(RUNNER._never_baselined(identifier))
        self.assertFalse(RUNNER._never_baselined("test_gold_prices.A.test_b"))
        self.quarantine.write_text("test_golden_doctoral.G.test_x | reason=x | owner=y | expires=M1\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            RUNNER.read_quarantine(self.quarantine)

    def test_committed_quarantine_can_expire(self) -> None:
        """Every milestone-bound entry fails the run at M8; only host entries are permanent."""

        quarantine = RUNNER.read_quarantine(RUNNER.DEFAULT_QUARANTINE)
        bounded = sorted(identifier for identifier, fields in quarantine.items() if fields["expires"] != RUNNER.HOST_EXPIRY)
        self.assertTrue(bounded)
        self.assertEqual(RUNNER.expired_quarantine(quarantine, "M8"), bounded)
        self.assertEqual(RUNNER.expired_quarantine(quarantine, RUNNER.current_milestone()), [])
        for identifier, fields in quarantine.items():
            with self.subTest(identifier=identifier):
                if fields["owner"] == "X0-gate-venv":
                    self.assertNotEqual(fields["expires"], RUNNER.HOST_EXPIRY)

    def test_module_filter_limits_fixed_but_listed_to_selected_modules(self) -> None:
        self._write_baseline(EXPECTED_FAILING)
        code, report = self._main("--modules", "test_toy_fail", "test_toy_pass")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["fixed_but_listed"], [])

    def test_hermetic_environment_redirects_state_and_refuses_the_managed_install(self) -> None:
        environment = RUNNER.hermetic_environment(self.root / "scratch", base={"PATH": "/usr/bin"})
        for name in ("HOME", "TMPDIR", "VALUE_DATA_HOME", "PYTHONPYCACHEPREFIX"):
            self.assertTrue(environment[name].startswith(str(self.root)), name)
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        with self.assertRaises(SystemExit):
            RUNNER.refuse_installed_paths([self.root / "inside" / "state"], installed=self.root)
        RUNNER.refuse_installed_paths([self.root / "elsewhere"], installed=self.root / "inside")

    def test_static_pytest_ids_cover_known_pytest_style_modules(self) -> None:
        identifiers = RUNNER.static_pytest_ids(ROOT)
        self.assertTrue(any(identifier.startswith("tests/test_market_ledger_v6.py::") for identifier in identifiers))
        self.assertTrue(any(identifier.startswith("tests/data_workbench/") for identifier in identifiers))

    def test_committed_baseline_has_fingerprint_and_no_quarantined_ids(self) -> None:
        baseline = RUNNER.read_baseline(RUNNER.DEFAULT_BASELINE)
        self.assertIsNotNone(baseline.fingerprint)
        for key in ("python", "numpy", "scipy", "pandas", "pulp", "cbcbox", "pytest", "pypdf"):
            self.assertIn(key, baseline.fingerprint)
        quarantine = RUNNER.read_quarantine(RUNNER.DEFAULT_QUARANTINE)
        self.assertFalse(baseline.ids & set(quarantine))


if __name__ == "__main__":
    unittest.main()
