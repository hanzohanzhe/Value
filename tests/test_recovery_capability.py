import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.recovery_capability import (
    SUBANNUAL_CHECKPOINT_SCHEMA,
    SUBANNUAL_REQUIRED_STATE,
    latest_safe_recovery_point,
    recovery_capability,
)


ROOT = Path(__file__).resolve().parents[1]


class RecoveryCapabilityTests(unittest.TestCase):
    def test_current_psm_is_truthfully_annual_only(self):
        report = recovery_capability(["value-bid-at-cost-psm", "agent-investment"])
        self.assertTrue(report["annual_resume_supported"])
        self.assertFalse(report["subannual_resume_supported"])
        self.assertEqual(report["optional_subannual_schema"], SUBANNUAL_CHECKPOINT_SCHEMA)
        self.assertEqual(tuple(report["required_subannual_state"]), SUBANNUAL_REQUIRED_STATE)
        self.assertGreaterEqual(len(report["state_gaps"]), 3)

    def test_maintained_zonal_chain_declares_monthly_resume_support(self):
        report = recovery_capability(
            ["value-staged-bid-at-cost-psm", "value-zonal-redispatch-balancing"]
        )
        self.assertTrue(report["subannual_resume_supported"])
        self.assertEqual(report["optional_subannual_schema"], SUBANNUAL_CHECKPOINT_SCHEMA)

    def test_future_schema_names_every_causal_state_group(self):
        schema = json.loads(
            (ROOT / "gridform_core" / "data" / "contracts" / "subannual-checkpoint-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], SUBANNUAL_CHECKPOINT_SCHEMA)
        self.assertTrue(set(SUBANNUAL_REQUIRED_STATE).issubset(schema["required"]))

    def test_latest_recovery_point_ignores_corrupt_or_unbound_files(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            checkpoints = output / "checkpoints-v2"
            checkpoints.mkdir()
            (checkpoints / "state-2026.json").write_text(json.dumps({
                "schema_version": "value.annual-checkpoint/v1",
                "identity": {"run_id": "r"}, "state_sha256": "a" * 64,
                "state": {"year": 2026},
            }), encoding="utf-8")
            (checkpoints / "state-2027.json").write_text("{broken", encoding="utf-8")
            self.assertEqual(latest_safe_recovery_point(output)["year"], 2026)


if __name__ == "__main__":
    unittest.main()
