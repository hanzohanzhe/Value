from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import gridform_core
from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM
from gridform_core.errors import DeprecatedRouteError
from scripts.psm_entrypoint_scan import build_report


ROOT = Path(__file__).resolve().parents[1]


class PSMEntrypointIdentityTests(unittest.TestCase):
    def test_registry_sdk_and_builtin_export_same_live_class(self):
        graph = gridform_core.workspace_registry().resolve_selection({
            "psm": "value-bid-at-cost-psm",
            "investment": "agent-investment",
            "pipeline": "planning-pipeline",
            "vre_cap": "vre-expansion-cap",
            "storage_cap": "value-storage-expansion-policy",
            "transition": "value-annual-state-transition",
            "storage_cost": "dynamic-annual-storage-cost",
        })
        self.assertIs(type(graph.implementation("psm")), SchemeCNativePSM)
        self.assertIs(gridform_core.SchemeCNativePSM, SchemeCNativePSM)
        self.assertEqual(graph.identity("psm").execution_kind, "live_module")

    def test_old_direct_adapter_does_not_forward(self):
        from gridform_core.builtin.scheme_c_1000twh.psm import SchemeCPSM

        with self.assertRaisesRegex(DeprecatedRouteError, "run_project_application"):
            SchemeCPSM()

    def test_source_and_registry_inventory_is_unambiguous(self):
        report = build_report()
        self.assertTrue(report["passed"], report)

    def test_entrypoint_scanner_runs_as_documented_from_repository_root(self):
        completed = subprocess.run(
            [sys.executable, "scripts/psm_entrypoint_scan.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertTrue(report["passed"], report)


if __name__ == "__main__":
    unittest.main()
