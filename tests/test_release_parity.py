import json
import unittest
from pathlib import Path

from gridform_core.dispatch_benchmark import solve_fixture


ROOT = Path(__file__).resolve().parents[1]


class ReleaseParityTests(unittest.TestCase):
    def test_convex_bid_at_cost_fixture(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "convex_bid_at_cost_dispatch.json").read_text("utf-8")
        )
        self.assertEqual(solve_fixture(fixture), fixture["expected"])

    def test_normal_runtime_has_no_reference_entry_point(self):
        server = (ROOT / "backend" / "server.py").read_text("utf-8")
        runner = (ROOT / "backend" / "model_runner.py").read_text("utf-8")
        self.assertNotIn("run_exact_scheme_c", server + runner)
        self.assertNotIn("modular_case3", server + runner)
        self.assertIn("run_project_application", runner)

    def test_packaged_storage_modules_do_not_import_excluded_compat_tree(self):
        storage_root = (
            ROOT
            / "gridform_core"
            / "builtin"
            / "scheme_c_1000twh"
            / "storage"
        )
        for path in storage_root.glob("*.py"):
            with self.subTest(path=path.name):
                source = path.read_text("utf-8")
                self.assertNotIn("from ..compat", source)
                self.assertNotIn("import ..compat", source)

    def test_replay_contract_requires_agent_economics_evidence(self):
        from gridform_core.builtin.scheme_c_1000twh.reference import SchemeCReplayData

        self.assertIn("agent_economics_by_year", SchemeCReplayData.__dataclass_fields__)

    def test_market_loop_has_no_per_period_full_garbage_collection(self):
        source = (
            ROOT
            / "gridform_core"
            / "builtin"
            / "scheme_c_1000twh"
            / "compat"
            / "modular_simulation_model.py"
        ).read_text("utf-8")
        section = source[source.index("def ahead_market_bidding"):source.index("def balancing_market_bidding")]
        self.assertNotIn("gc.collect()", section)

    def test_storage_cost_policy_has_truthful_scientific_version(self):
        from gridform_core.catalog import MODULE_REGISTRY

        manifest = MODULE_REGISTRY.manifest("dynamic-annual-storage-cost")
        self.assertEqual(manifest.version, "1.0.0")
        self.assertEqual(manifest.scientific_version, "dynamic-storage-recovery-2026.08.04")
        psm = MODULE_REGISTRY.manifest("value-bid-at-cost-psm")
        self.assertEqual(psm.version, "5.2.0")
        self.assertEqual(psm.execution_kind, "live_module")
        self.assertTrue(psm.implementation.endswith(":SchemeCNativePSM"))
        self.assertIn("storage.bid-cost-function", psm.requires_capabilities)

        storage_cap = MODULE_REGISTRY.manifest("value-storage-expansion-policy")
        self.assertEqual(storage_cap.version, "4.0.0")
        self.assertIn("market.year-result", storage_cap.requires_capabilities)
        self.assertNotIn("storage.bid-cost-function", storage_cap.requires_capabilities)

    def test_verbose_balance_diagnostic_is_explicitly_opt_in(self):
        from gridform_core.parameters import REGISTRY

        definition = REGISTRY["runtime.market_balance_diagnostic"]
        self.assertFalse(definition.default)
        self.assertEqual(definition.category, "runtime")


if __name__ == "__main__":
    unittest.main()
