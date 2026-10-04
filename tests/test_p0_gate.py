"""Tests for scripts/p0_gate.py (X0 S4)."""

from __future__ import annotations

import argparse
import importlib.util
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

        payload = json.loads(GATE.ESLINT_BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "value.eslint-ratchet/v1")
        for key, count in payload["counts"].items():
            self.assertEqual(len(json.loads(key)), 3)
            self.assertGreater(count, 0)

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


if __name__ == "__main__":
    unittest.main()
