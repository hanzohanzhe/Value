from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.application import run_project_application
from gridform_core.builtin.scheme_c_1000twh.scheme_c_modules import build_scheme_c_runtime
from gridform_core.errors import ContractError
from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"
MANIFESTS = ROOT / "examples" / "external_modules" / "manifests"


class ModuleResolutionGraphTests(unittest.TestCase):
    def _project(self) -> dict[str, object]:
        project = json.loads((ROOT / "tests" / "fixtures" / "prompt08_audit_project.json").read_text(encoding="utf-8"))
        project.update({"id": "all-slot-external-proof", "data_pack_id": PACK.name})
        project["modules"] = {
            "psm": "example-marked-perfect-foresight-psm",
            "investment": "example-agent-investment",
            "pipeline": "example-planning-pipeline",
            "vre_cap": "example-vre-cap",
            "storage_cap": "example-storage-cap",
            "transition": "example-state-transition",
        }
        return project

    def test_one_frozen_graph_drives_every_native_stage(self):
        registry = workspace_registry(MANIFESTS)
        with tempfile.TemporaryDirectory(prefix="force-all-slots-") as temporary:
            output = Path(temporary)
            result = run_project_application(
                self._project(), run_id="all-slot-proof", pack_root=PACK,
                output_dir=output, mode="smoke", registry=registry,
            )
            graph = json.loads((output / "module-resolution.json").read_text(encoding="utf-8"))
            self.assertEqual(set(graph["modules"]), set(self._project()["modules"]))
            self.assertTrue(all(len(row["source_sha256"]) == 64 for row in graph["modules"].values()))
            year = result["orchestrator_results"][0]
            self.assertTrue(year["market"]["extensions"]["external_fixture_executed"])
            self.assertTrue(year["planning_advance"]["operating_state"]["extensions"]["example_pipeline_advance_executed"])
            self.assertTrue(year["investment"]["extensions"]["example_investment_executed"])
            self.assertTrue(all(row["module_id"].startswith("example-") for row in year["expansion_headroom"]))
            self.assertTrue(year["next_state"]["extensions"]["example_transition_executed"])
            events = [json.loads(line) for line in (output / "orchestrator-events.jsonl").read_text(encoding="utf-8").splitlines()]
            observed = {row["module_slot"] for row in events}
            self.assertEqual(observed, {"pipeline", "psm", "vre_cap", "storage_cap", "investment", "transition"})

    def test_external_storage_cost_is_resolved_by_same_graph(self):
        registry = workspace_registry(MANIFESTS)
        selected = {
            "psm": "value-bid-at-cost-psm", "investment": "agent-investment",
            "pipeline": "planning-pipeline", "vre_cap": "vre-expansion-cap",
            "storage_cap": "value-storage-expansion-policy",
            "storage_cost": "example-storage-cost", "transition": "value-annual-state-transition",
        }
        graph = registry.resolve_selection(selected)
        with tempfile.TemporaryDirectory(prefix="force-cost-graph-") as temporary:
            with self.assertRaisesRegex(ContractError, "native orchestrator"):
                build_scheme_c_runtime(
                    selected, Path(temporary) / "events.jsonl", resolution_graph=graph
                )

    def test_external_v2_psm_cannot_be_silently_used_as_reference_bridge(self):
        registry = workspace_registry(MANIFESTS)
        selected = {
            "psm": "value-bid-at-cost-psm", "investment": "agent-investment",
            "pipeline": "planning-pipeline", "vre_cap": "vre-expansion-cap",
            "storage_cap": "value-storage-expansion-policy", "storage_cost": "dynamic-annual-storage-cost",
            "transition": "value-annual-state-transition",
        }
        graph = registry.resolve_selection(selected)
        with tempfile.TemporaryDirectory(prefix="force-no-fallback-") as temporary:
            with self.assertRaisesRegex(ContractError, "native orchestrator"):
                build_scheme_c_runtime(selected, Path(temporary) / "events.jsonl", resolution_graph=graph)


if __name__ == "__main__":
    unittest.main()
