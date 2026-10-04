import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh.scheme_c_modules import (
    build_scheme_c_runtime,
    build_retained_reference_runtime,
)
from gridform_core.errors import ContractError


MODULES = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "storage_cost": "dynamic-annual-storage-cost",
}


class SchemeCModuleRuntimeTests(unittest.TestCase):
    def test_project_ids_resolve_to_executable_stages_and_emit_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "module-events.jsonl"
            runtime = build_retained_reference_runtime(MODULES, evidence)
            self.assertEqual(runtime.psm.id, "doctoral-reproduction-kernel-bridge")
            self.assertEqual(runtime.psm.project_module_id, MODULES["psm"])
            self.assertEqual(runtime.psm.run(lambda value: value + 1, 2), 3)
            self.assertEqual(runtime.storage_cost.id, "dynamic-annual-storage-cost")
            runtime.pipeline.begin_year(4)
            runtime.pipeline.complete_year(5)
            rows = [
                json.loads(line)
                for line in evidence.read_text(encoding="utf-8").splitlines()
            ]
            runtime.close()
        psm_start = next(row for row in rows if row["action"] == "psm.start")
        self.assertEqual(psm_start["module_id"], "doctoral-reproduction-kernel-bridge")
        self.assertEqual(
            psm_start["storage_cost_module_id"], "dynamic-annual-storage-cost"
        )
        self.assertEqual(rows[-1]["module_id"], "planning-pipeline")

    def test_missing_selection_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "storage_cap"):
                build_scheme_c_runtime(
                    {key: value for key, value in MODULES.items() if key != "storage_cap"},
                    Path(folder) / "events.jsonl",
                )

    def test_live_psm_is_not_relabelled_as_retained_reference_bridge(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ContractError, "native orchestrator"):
                build_scheme_c_runtime(MODULES, Path(folder) / "events.jsonl")

    def test_legacy_cost_selection_is_shared_by_psm_and_storage_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "events.jsonl"
            modules = {**MODULES, "storage_cost": "value-legacy-storage-tariff"}
            runtime = build_retained_reference_runtime(modules, evidence)
            runtime.psm.run(lambda: None)
            runtime.storage_cap.calculate(lambda: {})
            runtime.close()
            rows = [json.loads(line) for line in evidence.read_text("utf-8").splitlines()]
        relevant = [row for row in rows if row["action"] in {"psm.start", "storage_cap.complete"}]
        self.assertEqual(
            {row["storage_cost_module_id"] for row in relevant},
            {"value-legacy-storage-tariff"},
        )


if __name__ == "__main__":
    unittest.main()
