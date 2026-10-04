"""Tests for scripts/p0_gate.py (X0 S4)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p0_gate", ROOT / "scripts" / "p0_gate.py")
GATE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GATE)


def _gate(tier: str = "quick", **overrides) -> "GATE.Gate":
    arguments = argparse.Namespace(
        changed_since=None, base="35aadb3", report=str(Path(tempfile.gettempdir()) / "p0-gate-test.json"),
        python="python3", jobs=None, skip=None, only=None, update_eslint_baseline=False, quiet=True,
        append_base=GATE.APPEND_ONLY_BASE,
    )
    for key, value in overrides.items():
        setattr(arguments, key, value)
    with mock.patch.object(GATE, "changed_files", return_value=None):
        return GATE.Gate(tier, arguments)


class P0GateTests(unittest.TestCase):
    def test_guard_refuses_state_inside_the_managed_install(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            installed = Path(folder) / "installed"
            (installed / "state").mkdir(parents=True)
            with mock.patch.object(GATE.RATCHET, "installed_root", return_value=installed), \
                    mock.patch.dict(os.environ, {"VALUE_DATA_HOME": str(installed / "state")}):
                with self.assertRaises(SystemExit):
                    GATE.step_guard(_gate())

    def test_guard_enforces_tier_disk_minimum(self) -> None:
        with mock.patch.object(GATE.RATCHET, "installed_root", return_value=None), \
                mock.patch.dict(os.environ, {"VALUE_DATA_HOME": tempfile.gettempdir()}):
            with mock.patch.object(GATE.shutil, "disk_usage", return_value=SimpleNamespace(free=int(1.2 * 1024**3))):
                self.assertEqual(GATE.step_guard(_gate("quick"))["status"], "passed")
                self.assertEqual(GATE.step_guard(_gate("full"))["status"], "failed")
                self.assertEqual(GATE.step_guard(_gate("nightly"))["status"], "failed")

    def test_eslint_ratchet_catches_fix_one_add_one(self) -> None:
        baseline = GATE.eslint_counts([
            {"file": "app/a.tsx", "ruleId": "r1", "message": "m"},
            {"file": "app/b.tsx", "ruleId": "r2", "message": "n"},
        ])
        current = GATE.eslint_counts([
            {"file": "app/a.tsx", "ruleId": "r1", "message": "m"},
            {"file": "app/c.tsx", "ruleId": "r2", "message": "n"},
        ])
        difference = GATE.compare_eslint(baseline, current)
        self.assertEqual([row["key"] for row in difference["increased"]], [["app/c.tsx", "r2", "n"]])
        self.assertEqual([row["key"] for row in difference["decreased"]], [["app/b.tsx", "r2", "n"]])
        same = GATE.compare_eslint(baseline, baseline)
        self.assertEqual(same, {"increased": [], "decreased": []})
        more = GATE.eslint_counts([{"file": "app/a.tsx", "ruleId": "r1", "message": "m"}] * 2)
        self.assertEqual(GATE.compare_eslint(baseline, more)["increased"][0]["current"], 2)

    def test_committed_eslint_baseline_is_well_formed(self) -> None:
        import json

        text = GATE.ESLINT_BASELINE.read_text(encoding="utf-8")
        payload = json.loads(text)
        self.assertEqual(payload["schema_version"], GATE.ESLINT_SCHEMA)
        for key, count in payload["counts"].items():
            file_name, _rule, message = json.loads(key)
            self.assertEqual(message, GATE.eslint_message_key(message), "baseline keys are stored normalised")
            self.assertFalse(Path(file_name).is_absolute())
            self.assertGreater(count, 0)
        self.assertNotIn(str(ROOT), text)
        self.assertNotIn("/home/", text)

    def test_eslint_key_is_independent_of_checkout_location_and_line(self) -> None:
        def message(root: str, line: int) -> str:
            return (
                "Error: Calling setState synchronously within an effect can trigger cascading renders\n\n"
                "Effects are intended to synchronize state.\n\n"
                f"{root}/app/page.tsx:{line}:5\n  {line - 1} |   useEffect(() => {{\n> {line} |     setValue(1);\n"
            )

        first_root = "/home/someone/work/value-fix-review-2026-10-04"
        second_root = "/tmp/lane-p0-9/checkout"
        first = GATE.eslint_counts(
            [{"file": "app/page.tsx", "ruleId": "react-hooks/set-state-in-effect", "message": message(first_root, 606)}],
            first_root,
        )
        second = GATE.eslint_counts(
            [{"file": "app/page.tsx", "ruleId": "react-hooks/set-state-in-effect", "message": message(second_root, 731)}],
            second_root,
        )
        self.assertEqual(first, second)
        self.assertEqual(GATE.compare_eslint(first, second), {"increased": [], "decreased": []})
        (key,) = first
        self.assertNotIn("/", json.loads(key)[2])
        # absolute paths inside a single-line message are reduced to the file name;
        # URLs are left alone
        self.assertEqual(
            GATE.eslint_message_key("Cannot resolve '/opt/x/app/lib.ts:3:9' here", "/elsewhere"),
            "Cannot resolve 'lib.ts' here",
        )
        url = "Do not assign to `module`. See: https://nextjs.org/docs/messages/no-assign-module-variable"
        self.assertEqual(GATE.eslint_message_key(url), url)

    def test_v1_baseline_keys_are_rekeyed_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "eslint-baseline.json"
            raw = json.dumps(["app/page.tsx", "r", f"Error: x\n\n{folder}/app/page.tsx:606:5"])
            path.write_text(json.dumps({"schema_version": "value.eslint-ratchet/v1", "counts": {raw: 2}}), encoding="utf-8")
            loaded = GATE.load_eslint_baseline(path, folder)
        self.assertEqual(loaded, {json.dumps(["app/page.tsx", "r", "Error: x"]): 2})

    def test_no_release_file_carries_a_local_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.json").write_text(json.dumps({"p": f"{root}/x"}), encoding="utf-8")
            (root / "b.txt").write_text("https://www.arcgis.com/home/item.html\n", encoding="utf-8")
            (root / "c.txt").write_text(f"{Path.home()}/secret\n", encoding="utf-8")
            leaks = GATE.local_path_leaks(["a.json", "b.txt", "c.txt", "missing.txt"], root)
        self.assertEqual(sorted(leaks), ["a.json", "c.txt"])

    def test_new_http_tests_must_use_the_local_api_harness(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "tests").mkdir()
            (root / "tests" / "test_bad.py").write_text(
                'httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)\n', encoding="utf-8"
            )
            (root / "tests" / "test_good.py").write_text(
                "from tests.local_api_harness import start_local_api\n"
                'httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)\n',
                encoding="utf-8",
            )
            (root / "tests" / "test_plain.py").write_text("x = 1\n", encoding="utf-8")
            violations = GATE.http_harness_violations(
                ["tests/test_bad.py", "tests/test_good.py", "tests/test_plain.py", "app/x.ts"], root
            )
        self.assertEqual(violations, ["tests/test_bad.py"])

    def test_commands_naming_live_ports_are_refused(self) -> None:
        for command in (["python", "-m", "backend.server", "--port", "8766"], ["curl", "http://127.0.0.1:8800/"]):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    GATE.run(command)

    def test_every_tier_extends_the_previous_one(self) -> None:
        quick = [step.name for step in GATE.QUICK_STEPS]
        full = [step.name for step in GATE.FULL_STEPS]
        nightly = [step.name for step in GATE.NIGHTLY_STEPS]
        self.assertEqual(full[: len(quick)], quick)
        self.assertEqual(nightly[: len(full)], full)
        self.assertIn("backend_ratchet", quick)
        self.assertIn("golden_bookkeeping", quick)
        self.assertIn("golden_full", full)
        self.assertIn("golden_nightly", nightly)

    def test_skip_is_recorded(self) -> None:
        gate = _gate(skip=["release_manifest"])
        gate.execute([GATE.Step("release_manifest", lambda _: {"status": "passed"})])
        self.assertEqual(gate.results[0]["status"], "skipped")

    def test_quick_tier_enforces_append_only(self) -> None:
        self.assertIn("append_only", [step.name for step in GATE.QUICK_STEPS])

    def test_append_only_step_passes_on_this_checkout(self) -> None:
        if GATE.run(["git", "rev-parse", "--git-dir"]).returncode != 0:
            self.skipTest("not a git checkout")
        outcome = GATE.step_append_only(_gate())
        self.assertEqual(outcome["status"], "passed", outcome)
        self.assertGreater(outcome["detail"]["golden_files"], 0)
        self.assertEqual(GATE.step_append_only(_gate(append_base="0" * 40))["status"], "failed")


def _golden_text(*revisions: dict) -> str:
    return json.dumps({"schema_version": "value.golden-case/v1", "family": "doctoral", "case": "D1",
                       "revisions": list(revisions)}, indent=1, sort_keys=True) + "\n"


def _revision(index: int, price_hash: str) -> dict:
    return {"revision": index, "reason": "r", "correction_ids": [] if index == 0 else ["p05.x"], "findings": [],
            "digest": {"columns": {"m::price": {"zone": "trajectory", "count": 2, "sha256": price_hash, "sha256_9g": price_hash}}}}


class AppendOnlyTests(unittest.TestCase):
    GOLDEN = "tests/golden/doctoral/D1.json"
    BASELINE = "tests/baselines/known-failures-linux-py310.txt"
    QUARANTINE = "tests/baselines/quarantine.txt"
    ESLINT = "tests/baselines/eslint-baseline.json"

    def setUp(self) -> None:
        self.base = {
            self.GOLDEN: _golden_text(_revision(0, "aa")),
            self.BASELINE: "# fingerprint: {}\ntest_a.A.test_one  # old\ntest_b.B.test_two\n",
            self.QUARANTINE: "# header\ntest_c.C.test_host | reason=r | owner=P1-1 | expires=host\n"
                             "IMPORT:test_d | reason=r | owner=X0-gate-venv | expires=M7\n",
            self.ESLINT: json.dumps({"schema_version": GATE.ESLINT_SCHEMA, "counts": {json.dumps(["app/a.tsx", "r", "m"]): 2}}),
        }
        self.head = dict(self.base)

    def _violations(self) -> list[str]:
        return GATE.append_only_violations(self.base.get, self.head.get, [self.GOLDEN])

    def test_unchanged_appended_and_shrunk_state_passes(self) -> None:
        self.assertEqual(self._violations(), [])
        self.head[self.GOLDEN] = _golden_text(_revision(0, "aa"), _revision(1, "bb"))
        self.head[self.BASELINE] = "# fingerprint: {}\ntest_b.B.test_two\n"
        self.head[self.QUARANTINE] = "test_c.C.test_host | reason=r | owner=P1-1 | expires=host\n" \
                                     "IMPORT:test_d | reason=r | owner=X0-gate-venv | expires=M5\n"
        self.head[self.ESLINT] = json.dumps({"schema_version": GATE.ESLINT_SCHEMA, "counts": {json.dumps(["app/a.tsx", "r", "m"]): 1}})
        self.assertEqual(self._violations(), [])

    def test_revision_zero_rewrite_is_refused(self) -> None:
        self.head[self.GOLDEN] = _golden_text(_revision(0, "cc"))
        self.assertTrue(any("revision 0 was rewritten" in row for row in self._violations()))
        self.head[self.GOLDEN] = _golden_text(_revision(0, "cc"), _revision(1, "aa"))
        self.assertTrue(any("revision 0 was rewritten" in row for row in self._violations()))

    def test_golden_deletion_and_truncation_are_refused(self) -> None:
        self.base[self.GOLDEN] = _golden_text(_revision(0, "aa"), _revision(1, "bb"))
        self.head[self.GOLDEN] = _golden_text(_revision(0, "aa"))
        self.assertTrue(any("revisions removed" in row for row in self._violations()))
        del self.head[self.GOLDEN]
        self.assertTrue(any("deleted" in row for row in self._violations()))

    def test_baseline_growth_and_golden_ids_are_refused(self) -> None:
        self.head[self.BASELINE] = self.base[self.BASELINE] + "test_golden_doctoral.GoldenDoctoralFamilyTests.test_fast_cases_match_latest_revision  # 2026-10-05: silenced\n"
        violations = self._violations()
        self.assertTrue(any("added (the baseline only shrinks)" in row for row in violations), violations)
        self.assertTrue(any("golden tests may never be baselined" in row for row in violations), violations)

    def test_quarantine_growth_extension_and_golden_ids_are_refused(self) -> None:
        self.head[self.QUARANTINE] = self.base[self.QUARANTINE].replace("expires=M7", "expires=host") + \
            "IMPORT:test_golden_corrected | reason=r | owner=x | expires=M1\n"
        violations = self._violations()
        self.assertTrue(any("quarantine only shrinks" in row for row in violations), violations)
        self.assertTrue(any("expiry moved later" in row for row in violations), violations)
        self.assertTrue(any("never be quarantined" in row for row in violations), violations)

    def test_eslint_baseline_growth_is_refused(self) -> None:
        self.head[self.ESLINT] = json.dumps({"schema_version": GATE.ESLINT_SCHEMA, "counts": {
            json.dumps(["app/a.tsx", "r", "m"]): 2, json.dumps(["app/b.tsx", "r", "m"]): 1}})
        self.assertTrue(any("ESLint baseline only shrinks" in row for row in self._violations()))



if __name__ == "__main__":
    unittest.main()
