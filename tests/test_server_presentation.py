import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import server


class RunPresentationTests(unittest.TestCase):
    def _present(self, policy: str):
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
            with patch.object(server, "RUNS_ROOT", root):
                return server.present_run(run)

    def test_dynamic_difference_is_an_informational_scenario_comparison(self):
        result = self._present("dynamic-annual-storage-cost")
        self.assertEqual(result["scientific_validation_status"], "failed")
        self.assertEqual(result["scientific_scenario_status"], "passed")
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
