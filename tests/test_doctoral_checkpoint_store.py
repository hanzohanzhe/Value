"""Disk-failure and restart tests use bounded synthetic periods only."""
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine, _hash
from gridform_core.builtin.scheme_c_1000twh.doctoral_period_ledger import DoctoralPeriodLedger
from test_doctoral_period_engine import assets

MODULE = "gridform_core.doctoral_checkpoint"


class DoctoralCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "doctoral disk checkpoint publisher is missing")
        self.module = importlib.import_module(MODULE)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "national-checkpoints"
        gen, bat = assets()
        self.engine = DoctoralPeriodEngine(gen, bat, year=2025)
        self.frozen = {"run_id": "checkpoint-fixture", "year": 2025,
            "engine_input_sha256": self.engine.input_sha256,
            "source_rule_sha256": _hash(self.engine.rule_identity), "weather_sha256": "a" * 64,
            "data_pack_sha256": "b" * 64, "parameters_sha256": "c" * 64,
            "thesis_contract_sha256": "d" * 64, "planning_state_sha256": _hash({"year": 2025}),
            "nuclear_policy_sha256": "e" * 64}
        self.ledger = DoctoralPeriodLedger(run_id=self.frozen["run_id"],
            input_sha256=self.engine.input_sha256,
            source_rule_sha256=self.frozen["source_rule_sha256"], weather_sha256=self.frozen["weather_sha256"],
            initial_state=self.engine.state, asset_ids=("wind", "gas", "store"))
        self.store = self.module.DoctoralCheckpointStore(self.directory, frozen_identity=self.frozen)

    def step(self, engine=None, ledger=None):
        engine, ledger = engine or self.engine, ledger or self.ledger
        result = engine.realise_period(engine.plan_period(50), 50)
        ledger.append(result)
        engine.commit(result)

    def publish(self):
        return self.store.publish(self.engine, self.ledger,
            annual_state={"year": 2025}, boundary="diagnostic")

    def test_disk_roundtrip_resumes_same_next_period_and_account_prefix(self):
        self.step()
        record = self.publish()
        payload = self.store.load_latest()
        self.assertEqual(payload["ledger"]["prefix_sha256"], record["ledger_prefix_sha256"])
        gen, bat = assets()
        engine = DoctoralPeriodEngine(gen, bat, year=2025, checkpoint=payload["engine"])
        ledger = DoctoralPeriodLedger.from_snapshot(payload["ledger"],
            expected_input_sha256=self.engine.input_sha256,
            expected_source_rule_sha256=self.frozen["source_rule_sha256"],
            expected_weather_sha256=self.frozen["weather_sha256"],
            expected_prefix_sha256=record["ledger_prefix_sha256"])
        self.step()
        self.step(engine, ledger)
        self.assertEqual(engine.export_state(), self.engine.export_state())
        self.assertEqual(ledger.snapshot(), self.ledger.snapshot())

    def test_crash_before_anchor_publish_leaves_previous_checkpoint_authoritative(self):
        self.step()
        first = self.publish()
        self.step()
        with patch.object(self.store, "_publish_index", side_effect=OSError("injected disk failure")):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(self.store.latest_record(), first)
        self.assertEqual(self.store.load_latest()["ledger"]["period_count"], 1)
        second = self.publish()
        self.assertEqual(self.store.latest_record(), second)
        self.assertEqual(len(list(self.directory.glob("checkpoint-*.json"))), 2)

    def test_month_is_calendar_boundary_and_partial_year_cannot_publish_as_annual(self):
        self.assertEqual(self.module.month_end_periods(), (1488, 2832, 4320, 5760, 7248,
            8688, 10176, 11664, 13104, 14592, 16032, 17520))
        self.step()
        for boundary in ("monthly", "annual"):
            with self.subTest(boundary=boundary), self.assertRaisesRegex(ValueError, "boundary|annual"):
                self.store.publish(self.engine, self.ledger, annual_state={"year": 2025}, boundary=boundary)
        self.assertFalse((self.directory / "index.json").exists())

    def test_input_state_drift_and_tampered_bundle_are_rejected(self):
        self.step()
        record = self.publish()
        altered = {**self.frozen, "weather_sha256": "f" * 64}
        with self.assertRaisesRegex(ValueError, "identity"):
            self.module.DoctoralCheckpointStore(self.directory, frozen_identity=altered).load_latest()
        with self.assertRaisesRegex(ValueError, "planning"):
            self.store.publish(self.engine, self.ledger, annual_state={"year": 2026}, boundary="diagnostic")
        path = self.directory / record["filename"]
        payload = json.loads(path.read_text())
        payload["ledger"]["cumulative"]["actual_demand_mwh"] = 999
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.store.load_latest()

    def test_ledger_and_engine_must_commit_the_same_outcome_before_publication(self):
        outcome = self.engine.realise_period(self.engine.plan_period(50), 50)
        self.ledger.append(outcome)
        with self.assertRaisesRegex(ValueError, "state"):
            self.publish()
        self.engine.commit(outcome)
        self.assertEqual(self.publish()["next_period_index"], 1)


if __name__ == "__main__":
    unittest.main()
