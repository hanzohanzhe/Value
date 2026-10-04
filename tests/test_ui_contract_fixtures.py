"""UI contract fixtures (P0-9 S2): regeneration, budgets and invariants."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import ui_contract_fixtures as fixtures  # noqa: E402


def _committed() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(fixtures.FIXTURE_DIR.glob("*.json"))
        if path.name != fixtures.INDEX_NAME
    }


class CommittedFixtureTests(unittest.TestCase):
    def test_index_lists_exactly_the_committed_fixtures(self) -> None:
        index = json.loads((fixtures.FIXTURE_DIR / fixtures.INDEX_NAME).read_text(encoding="utf-8"))
        committed = _committed()
        self.assertEqual(index["schema_version"], fixtures.INDEX_SCHEMA_VERSION)
        self.assertEqual([row["file"] for row in index["fixtures"]], sorted(committed))
        for row in index["fixtures"]:
            document = committed[row["file"]]
            self.assertEqual(document["schema_version"], fixtures.SCHEMA_VERSION)
            self.assertEqual((row["source"], row["path"], row["query"]),
                             (document["source"], document["request"]["path"], document["request"]["query"]))

    def test_every_source_answers_every_ui_market_request(self) -> None:
        committed = _committed()
        for source in fixtures.SOURCES:
            names = {name.split(".")[1] for name in committed if name.startswith(f"{source}.")}
            self.assertTrue({"capabilities", "dispatch-daily", "dispatch-half-hour", "vre-summary",
                             "vre-timeline-daily", "periods", "storage"} <= names, source)
        self.assertIn("toy-v7.auction-ahead.json", committed)
        self.assertIn("value-101-day.auction-ahead.json", committed)

    def test_sources_are_the_ledgers_they_claim(self) -> None:
        committed = _committed()
        self.assertEqual(committed["toy-v7.capabilities.json"]["payload"]["ledger_schema_version"], "value.market-ledger/v7")
        self.assertEqual(committed["toy-v8.capabilities.json"]["payload"]["ledger_schema_version"], "value.market-ledger/v8")
        self.assertEqual(committed["toy-v8.capabilities.json"]["payload"]["trace_level"], "summary")
        self.assertEqual(committed["value-101-day.capabilities.json"]["payload"]["semantic_metadata"]["psm_module_id"], "value-bid-at-cost-psm")
        self.assertEqual(committed["toy-v8.dispatch-half-hour.json"]["payload"]["dispatch_source"], "dispatch_summary")
        self.assertEqual(committed["value-101-day.dispatch-half-hour.json"]["payload"]["total"], 48)

    def test_committed_fixtures_hold_both_invariants_and_fit_the_budget(self) -> None:
        report = fixtures.invariant_report(_committed())
        self.assertTrue(report["passed"], report)
        self.assertIn("v8_period_conservation:toy-v8.dispatch-half-hour.json", report["checks"])
        self.assertLessEqual(fixtures.total_bytes(), fixtures.SIZE_BUDGET_BYTES)

    def test_only_the_sqlite_file_hash_is_masked(self) -> None:
        text = "".join(path.read_text(encoding="utf-8") for path in fixtures.FIXTURE_DIR.glob("*.json"))
        self.assertIn(fixtures.VOLATILE_PLACEHOLDER, text)
        self.assertEqual(fixtures.VOLATILE_KEYS, frozenset({"source_artifact_sha256"}))
        auction = _committed()["value-101-day.auction-ahead.json"]["payload"]
        self.assertRegex(auction["input_sha256"], r"^[0-9a-f]{64}$", "content hashes stay real")


class GeneratorHelperTests(unittest.TestCase):
    def test_differences_uses_the_relative_tolerance_and_reports_structure(self) -> None:
        self.assertEqual(fixtures.differences({"a": 1.0}, {"a": 1.0 + 1e-12}), [])
        self.assertEqual(len(fixtures.differences({"a": 1.0}, {"a": 1.0 + 1e-6})), 1)
        self.assertIn("keys differ", fixtures.differences({"a": 1, "b": 2}, {"a": 1, "c": 2})[0])
        self.assertIn("length", fixtures.differences([1, 2], [1])[0])
        self.assertIn("type", fixtures.differences({"a": 1}, {"a": 1.5})[0])
        self.assertEqual(fixtures.differences({"a": 0}, {"a": 0.0}), [])
        self.assertEqual(len(fixtures.differences({"a": True}, {"a": 1})), 1)
        self.assertEqual(len(fixtures.differences({"a": None}, {"a": 0.0})), 1, "missing never equals zero")

    def test_normalise_masks_only_the_file_hash_and_rejects_non_finite_numbers(self) -> None:
        payload = {"source_artifact_sha256": "f" * 64, "input_sha256": "e" * 64, "nested": [{"source_artifact_sha256": None}]}
        normalised = fixtures.normalise(payload)
        self.assertEqual(normalised["source_artifact_sha256"], fixtures.VOLATILE_PLACEHOLDER)
        self.assertEqual(normalised["input_sha256"], "e" * 64)
        self.assertIsNone(normalised["nested"][0]["source_artifact_sha256"], "a missing hash stays missing")
        with self.assertRaises(ValueError):
            fixtures.normalise({"x": float("nan")})

    def test_supply_invariant_classifies_v7_flow_types_and_v8_final_rows(self) -> None:
        v7 = {"dispatch_source": "physical_dispatch", "items": [{"period_start": 0, "period_end": 0, "accepted_supply_mwh": 10.0, "flows": [
            {"flow_type": "generation", "energy_mwh": 6.0}, {"flow_type": "storage_discharge", "energy_mwh": 1.0},
            {"flow_type": "import", "energy_mwh": 3.0}, {"flow_type": "storage_charge", "energy_mwh": 2.0},
            {"flow_type": "excess_generation", "energy_mwh": 5.0},
        ]}]}
        self.assertEqual(fixtures.supply_flow_violations(v7), [])
        v7["items"][0]["flows"].pop(0)
        self.assertEqual(len(fixtures.supply_flow_violations(v7)), 1)
        v8 = {"dispatch_source": "dispatch_summary", "items": [{"period_start": 0, "period_end": 0, "accepted_supply_mwh": 4.0, "energy_balance_residual_mwh": 0.0, "flows": [
            {"flow_type": "accepted_dispatch", "evidence_scope": "zone:north;stage:final_dispatch", "energy_mwh": 4.0},
            {"flow_type": "accepted_dispatch", "evidence_scope": "zone:north;stage:ahead", "energy_mwh": 4.0},
        ]}]}
        self.assertEqual(fixtures.v8_period_conservation_violations(v8), [])
        v8["items"][0]["energy_balance_residual_mwh"] = 0.1
        self.assertEqual(len(fixtures.v8_period_conservation_violations(v8)), 1)

    def test_render_is_line_oriented_json(self) -> None:
        document = {"payload": {"items": [{"a": 1, "b": [1, 2]}, {"a": 2, "b": []}], "empty": [], "scalar": 0.5}}
        text = fixtures.render(document)
        self.assertEqual(json.loads(text), document)
        self.assertIn('\n   {"a":1,"b":[1,2]},\n', text)
        self.assertTrue(text.endswith("\n"))


class RegenerationTests(unittest.TestCase):
    def test_regeneration_matches_the_committed_fixtures_within_budgets(self) -> None:
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        with tempfile.TemporaryDirectory() as scratch:
            completed = subprocess.run(
                [sys.executable, "-B", str(ROOT / "tests" / "ui_contract_fixtures.py"), "--check", "--scratch", scratch],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=300,
            )
            leftovers = list(Path(scratch).iterdir())
        self.assertEqual(completed.returncode, 0, completed.stdout[-4000:] + completed.stderr[-4000:])
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["differences"], [])
        self.assertEqual(summary["budget_violations"], [])
        self.assertLessEqual(summary["seconds"], fixtures.TIME_BUDGET_SECONDS)
        self.assertLessEqual(summary["bytes"], fixtures.SIZE_BUDGET_BYTES)
        self.assertTrue(summary["invariants"]["passed"], summary["invariants"])
        self.assertEqual(leftovers, [], "the generator removes its ledgers and Run")


if __name__ == "__main__":
    unittest.main()
