import unittest
from dataclasses import replace

from gridform_core.catalog import MODULES, MODULE_REGISTRY
from gridform_core.v2.module_manifest import ModuleRegistryV2


SELECTION = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "storage_cost": "dynamic-annual-storage-cost",
}


class ModuleManifestV2Tests(unittest.TestCase):
    def test_builtin_selection_resolves_and_catalog_uses_same_objects(self):
        resolved = MODULE_REGISTRY.validate_selection(SELECTION)
        self.assertEqual(len(resolved), 6)
        self.assertEqual(
            {row["id"] for row in MODULES}, set(MODULE_REGISTRY.manifests())
        )
        instance = MODULE_REGISTRY.resolve("value-bid-at-cost-psm", expected_slot="psm")
        self.assertEqual(instance.id, "value-bid-at-cost-psm")

    def test_duplicate_id_is_rejected(self):
        manifest = MODULE_REGISTRY.manifest("value-bid-at-cost-psm")
        with self.assertRaisesRegex(ValueError, "Duplicate module ID"):
            ModuleRegistryV2((manifest, manifest))

    def test_missing_module_and_wrong_slot_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "not registered"):
            MODULE_REGISTRY.resolve("missing", expected_slot="psm")
        with self.assertRaisesRegex(ValueError, "cannot fill pipeline"):
            MODULE_REGISTRY.resolve("value-bid-at-cost-psm", expected_slot="pipeline")

    def test_unsupported_contract_and_missing_entry_point_are_rejected(self):
        manifest = MODULE_REGISTRY.manifest("value-bid-at-cost-psm")
        with self.assertRaisesRegex(ValueError, "expected value.psm/v2"):
            ModuleRegistryV2((replace(manifest, contract_version="value.psm/v99"),))
        with self.assertRaisesRegex(ValueError, "symbol is missing"):
            ModuleRegistryV2((replace(manifest, id="missing-symbol", implementation=manifest.implementation + "Missing"),))

    def test_missing_slot_and_capability_are_rejected(self):
        incomplete = {key: value for key, value in SELECTION.items() if key != "storage_cap"}
        with self.assertRaisesRegex(ValueError, "Missing required module slots"):
            MODULE_REGISTRY.validate_selection(incomplete)
        psm = replace(
            MODULE_REGISTRY.manifest("value-bid-at-cost-psm"),
            id="requires-impossible",
            selection_required=False,
            requires_capabilities=("impossible.capability",),
        )
        registry = ModuleRegistryV2((psm,))
        with self.assertRaisesRegex(ValueError, "incompatible capabilities"):
            registry.validate_selection({"psm": "requires-impossible"})


if __name__ == "__main__":
    unittest.main()
