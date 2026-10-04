from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gridform_core.application import run_project_application
from gridform_core.catalog import DATASET_SLOTS
from gridform_core.data_pack_validation import validate_data_pack


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"


class SyntheticPublicPackTests(unittest.TestCase):
    def _project(self) -> dict[str, object]:
        project = json.loads(
            (ROOT / "tests" / "fixtures" / "prompt08_audit_project.json")
            .read_text(encoding="utf-8")
        )
        project.update({
            "id": "synthetic-public-contract-test",
            "name": "Synthetic public contract test",
            "data_pack_id": "value-synthetic-contract-pack-v1",
        })
        project["modules"] = dict(project["modules"])
        project["modules"]["psm"] = "value-perfect-foresight-lp"
        project["modules"]["transition"] = "value-annual-state-transition"
        project["modules"].pop("storage_cost", None)
        return project

    def test_pack_validates_and_runs_real_two_year_native_chain(self):
        manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["licence"], "CC0-1.0")
        self.assertEqual(manifest["publication_status"], "redistributable")
        self.assertTrue((PACK / "LICENSE").is_file())
        self.assertTrue(all(
            binding["licence"] == "CC0-1.0"
            and binding["redistribution_class"] == "redistributable_cc0"
            for binding in manifest["bindings"].values()
        ))
        validation = validate_data_pack(PACK, manifest, DATASET_SLOTS)
        self.assertTrue(validation["valid"], validation["errors"])

        with tempfile.TemporaryDirectory(prefix="force-synthetic-") as temporary:
            output = Path(temporary) / "model-output"
            captured = io.StringIO()
            with redirect_stdout(captured), redirect_stderr(captured):
                result = run_project_application(
                    self._project(),
                    run_id="synthetic-public-two-year",
                    pack_root=PACK,
                    output_dir=output,
                    mode="two_year_smoke",
                )
            self.assertEqual(result["execution_path"], "native_public_contracts")
            self.assertEqual(
                [row["year"] for row in result["orchestrator_results"]],
                [2025, 2026],
            )
            self.assertTrue((output / "ledgers" / "annual-cost-ledger.json").is_file())
            self.assertTrue((output / "ledgers" / "annual-carbon-ledger.json").is_file())
            self.assertTrue((output / "planning" / "project-index.sqlite").is_file())


if __name__ == "__main__":
    unittest.main()
