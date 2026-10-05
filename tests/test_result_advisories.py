"""Read-time scientific status presentation (X0 S10a)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.result_advisories import present_scientific_status


def _validation(**fields):
    return {
        "execution_status": "passed",
        "contract_validation_status": "passed",
        "analytical_mechanism_status": "passed",
        "retained_numerical_comparison_status": "failed",
        "scientific_validation_status": "failed",
        **fields,
    }


class PresentScientificStatusTests(unittest.TestCase):
    def _present(self, policy, *, mode="full", validation=None):
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder)
            path = run_root / "model-output" / "validation" / "scientific-validation.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(validation if validation is not None else _validation()), encoding="utf-8")
            run = {"id": "run", "mode": mode, "modules": {"storage_cost": policy}, "results": []}
            return present_scientific_status(run, run_root)

    def test_moved_rules_are_unchanged(self):
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

    def test_server_present_run_uses_the_shared_function(self):
        from unittest.mock import patch

        from backend import server

        with patch.object(server, "present_scientific_status", wraps=present_scientific_status) as spy, \
                tempfile.TemporaryDirectory() as folder, patch.object(server, "RUNS_ROOT", Path(folder)):
            (Path(folder) / "run").mkdir()
            server.present_run({"id": "run", "mode": "full", "modules": {}, "results": []})
        self.assertEqual(spy.call_count, 1)


if __name__ == "__main__":
    unittest.main()
