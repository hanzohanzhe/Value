import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core.methodology import resolve_methodology


class RunPresentationTests(unittest.TestCase):
    def _present(self, policy: str, methodology=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_root = root / "run"
            validation_path = run_root / "model-output" / "validation" / "scientific-validation.json"
            validation_path.parent.mkdir(parents=True)
            validation_path.write_text(json.dumps({
                "execution_status": "passed",
                "contract_validation_status": "passed",
                "analytical_mechanism_status": "passed",
                "retained_numerical_comparison_status": "failed",
                "scientific_validation_status": "failed",
            }), encoding="utf-8")
            run = {
                "id": "run",
                "mode": "full",
                "modules": {"storage_cost": policy},
                "scientific_validation_artifact": "validation/scientific-validation.json",
                "scientific_validation_status": "failed",
                "results": [],
            }
            if methodology is not None:
                run["methodology"] = methodology
            with patch.object(server, "RUNS_ROOT", root):
                return server.present_run(run)

    def test_dynamic_difference_is_an_informational_scenario_comparison(self):
        result = self._present("dynamic-annual-storage-cost")
        self.assertEqual(result["scientific_validation_status"], "failed")
        # A run without a methodology record predates the 2026-10 fixes: its
        # positive scenario claim is superseded, the recorded value is kept
        # (X0 S10b).  The server no longer forces "passed" (P0-4 S3, P7-01):
        # a run that records its methodology but only a v1 report (whose
        # contract "passed" was a literal) is superseded as well.
        self.assertEqual(result["scientific_scenario_status"], "superseded_pre_fix")
        self.assertEqual(result["recorded_validation_statuses"]["scientific_scenario_status"], "passed")
        recorded = self._present("dynamic-annual-storage-cost", methodology=resolve_methodology().to_dict())
        self.assertEqual(recorded["scientific_scenario_status"], "superseded_pre_fix")
        self.assertEqual(recorded["recorded_validation_statuses"]["scientific_scenario_status"], "passed")
        self.assertEqual(
            result["retained_numerical_comparison_status"], "expected_difference"
        )
        self.assertEqual(
            result["retained_comparison_role"], "informational_scenario_difference"
        )

    def test_legacy_difference_remains_a_failed_reproduction_gate(self):
        result = self._present("value-legacy-storage-tariff")
        self.assertEqual(result["scientific_scenario_status"], "failed")
        self.assertEqual(result["retained_numerical_comparison_status"], "failed")
        self.assertEqual(result["retained_comparison_role"], "required_reproduction_gate")


if __name__ == "__main__":
    unittest.main()
