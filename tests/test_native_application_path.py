from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.application import run_project_application


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"


class NativeApplicationPathTests(unittest.TestCase):
    def test_perfect_foresight_runs_two_year_chain_without_storage_offer_rule(self):
        project = json.loads(
            (ROOT / "tests" / "fixtures" / "prompt08_audit_project.json")
            .read_text(encoding="utf-8")
        )
        project["id"] = "native-perfect-foresight-fixture"
        project["data_pack_id"] = PACK.name
        project["modules"] = dict(project["modules"])
        project["modules"]["psm"] = "value-perfect-foresight-lp"
        project["modules"]["transition"] = "value-annual-state-transition"
        project["modules"].pop("storage_cost", None)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "model-output"
            result = run_project_application(
                project,
                run_id="native-perfect-test",
                pack_root=PACK,
                output_dir=output,
                mode="two_year_smoke",
            )
            self.assertEqual(result["execution_path"], "native_public_contracts")
            self.assertIsNone(result["compatibility_boundary"])
            self.assertEqual(len(result["orchestrator_results"]), 2)
            self.assertEqual(
                [row["year"] for row in result["orchestrator_results"]],
                [2025, 2026],
            )
            self.assertEqual(
                result["orchestrator_results"][0]["market"]["extensions"]["storage_offer_rule"],
                "not_applicable",
            )
            events = [
                json.loads(line)
                for line in (output / "orchestrator-events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                [row["module_id"] for row in events if row["stage"] == "psm.run"],
                ["value-perfect-foresight-lp", "value-perfect-foresight-lp"],
            )
            self.assertTrue((output / "ledgers" / "annual-cost-ledger.json").is_file())


if __name__ == "__main__":
    unittest.main()
