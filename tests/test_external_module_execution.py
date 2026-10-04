from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gridform_core.application import run_project_application
from gridform_core.module_conformance import conformance_report
from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"
MANIFESTS = ROOT / "examples" / "external_modules" / "manifests"


class ExternalModuleExecutionTests(unittest.TestCase):
    def _project(self, psm: str) -> dict[str, object]:
        payload = json.loads(
            (ROOT / "tests" / "fixtures" / "prompt08_audit_project.json")
            .read_text(encoding="utf-8")
        )
        payload.update({"id": "external-proof", "data_pack_id": PACK.name})
        payload["modules"] = dict(payload["modules"])
        payload["modules"]["psm"] = psm
        payload["modules"]["transition"] = "value-annual-state-transition"
        payload["modules"].pop("storage_cost", None)
        return payload

    def test_all_external_fixture_manifests_conform(self):
        report = conformance_report(workspace_registry(MANIFESTS))
        external = [row for row in report["modules"] if str(row["module_id"]).startswith("example-")]
        self.assertEqual(len(external), 7)
        self.assertTrue(all(row["status"] == "passed" for row in external), external)

    def test_selected_external_psm_runs_and_changes_result_by_exact_marker(self):
        registry = workspace_registry(MANIFESTS)
        with tempfile.TemporaryDirectory(prefix="force-external-") as temporary:
            root = Path(temporary)
            captured = io.StringIO()
            with redirect_stdout(captured), redirect_stderr(captured):
                baseline = run_project_application(
                    self._project("value-perfect-foresight-lp"),
                    run_id="external-proof-baseline", pack_root=PACK,
                    output_dir=root / "baseline", mode="smoke", registry=registry,
                )
                marked = run_project_application(
                    self._project("example-marked-perfect-foresight-psm"),
                    run_id="external-proof-marked", pack_root=PACK,
                    output_dir=root / "marked", mode="smoke", registry=registry,
                )
            base_market = baseline["orchestrator_results"][0]["market"]
            marked_market = marked["orchestrator_results"][0]["market"]
            self.assertAlmostEqual(
                marked_market["total_operational_cost_gbp"]
                - base_market["total_operational_cost_gbp"],
                123.45,
                places=6,
            )
            self.assertTrue(marked_market["extensions"]["external_fixture_executed"])
            events = [
                json.loads(line)
                for line in (root / "marked" / "orchestrator-events.jsonl")
                .read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn(
                "example-marked-perfect-foresight-psm",
                [row["module_id"] for row in events if row["stage"] == "psm.run"],
            )


if __name__ == "__main__":
    unittest.main()
