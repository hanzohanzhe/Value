import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.module_conformance import check_manifest, check_storage_lifecycle, conformance_report
from gridform_core.v2.module_manifest import ModuleRegistryV2, workspace_registry


class ModuleConformanceTests(unittest.TestCase):
    def test_fixed_73_template_uses_real_battery_lifecycle(self):
        source = Path("examples/external_module_bundle/src/value_example_flat_offer/plugin.py").read_text()
        namespace = {}
        exec(compile(source.replace("42.0", "73.0"), "fixed73.py", "exec"), namespace)
        offer = namespace["FlatStorageCostDefinition"]().create(battery_type="1c", period_hours=0.5)
        check_storage_lifecycle(offer)
        self.assertEqual(offer.bid_price_gbp_per_mwh(999), 73.0)
        self.assertEqual(offer.report()["fixed_offer_gbp_per_mwh"], 73.0)
        self.assertEqual(offer.report()["method"], "experimental_fixed_offer")
        self.assertGreater(offer.report()["previous_year_sold_mwh"], 0)

    def test_lifecycle_rejects_original_incomplete_template_and_missing_sales(self):
        class OriginalOffer:
            def prepare_year(self, year, **project):
                self.year = year
            def bid_price_gbp_per_mwh(self, dwell):
                return 42.0
        with self.assertRaises(AttributeError):
            check_storage_lifecycle(OriginalOffer())
        source = Path("examples/external_module_bundle/src/value_example_flat_offer/plugin.py").read_text()
        namespace = {}
        exec(compile(source, "fixed.py", "exec"), namespace)
        offer = namespace["FlatStorageOffer"]()
        offer.record_sale = lambda *args: None
        with self.assertRaisesRegex(ValueError, "non-zero Battery discharge"):
            check_storage_lifecycle(offer)
        offer = namespace["FlatStorageOffer"]()
        offer.bid_price_gbp_per_mwh = lambda dwell: float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            check_storage_lifecycle(offer)

    def test_builtin_modules_pass_callable_shape_conformance(self):
        report = conformance_report(workspace_registry(Path("missing-modules-directory")))
        self.assertTrue(report["passed"])
        self.assertTrue(all(row["status"] == "passed" for row in report["modules"]))

    def test_workspace_manifest_reaches_production_registry_resolution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            payload = {
                "schema_version": "value.module/v2",
                "id": "external-dynamic-storage-cost-fixture",
                "name": "External fixture",
                "version": "1.0.0",
                "slot": "storage_cost",
                "implementation": "gridform_core.builtin.scheme_c_1000twh.compat.storage_cost:DynamicStorageCostDefinition",
                "contract_version": "value.storage-cost/v1",
                "inputs": ["storage.asset"],
                "outputs": ["storage.bid-cost-function"],
                "parameters": [],
                "state_reads": [],
                "state_writes": [],
                "determinism": "deterministic",
                "artifacts": [],
                "description": "test fixture",
                "selection_required": False,
                "provides_capabilities": ["storage.bid-cost-function"],
                "requires_capabilities": [],
                "units": {"storage.asset": "MW/MWh"}
            }
            (root / "external.json").write_text(json.dumps(payload), encoding="utf-8")
            registry = workspace_registry(root)
            instance = registry.resolve(payload["id"], expected_slot="storage_cost")
            self.assertEqual(instance.id, "dynamic-annual-storage-cost")
            report = check_manifest(registry, registry.manifest(payload["id"]))
            self.assertEqual(report["status"], "passed")

    def test_unknown_units_and_parameters_are_rejected(self):
        base = workspace_registry(Path("missing-modules-directory")).manifest(
            "dynamic-annual-storage-cost"
        )
        with self.assertRaisesRegex(ValueError, "units for unknown"):
            ModuleRegistryV2((replace(base, id="bad-unit", units={"missing": "MW"}),))
        bad_parameter = replace(
            base, id="bad-parameter", selection_required=False,
            parameters=("not.registered",),
        )
        registry = ModuleRegistryV2((bad_parameter,))
        report = check_manifest(registry, bad_parameter)
        self.assertEqual(report["status"], "failed")
        self.assertIn("undeclared parameter", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
