from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from gridform_core.module_bundle import (
    ModuleBundleError,
    build_module_bundle,
    validate_module_bundle,
)
from gridform_core.module_installation import (
    ModuleInstallationError,
    install_module_bundle,
    list_module_installations,
    set_module_enabled,
)
from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "external_module_bundle"
EXTERNAL_PSM_EXAMPLE = ROOT / "examples" / "external_psm_bundle"


class ModuleInstallationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.modules = self.root / "modules"
        self.bundle = self.root / "example.zip"

    def tearDown(self) -> None:
        for name in list(sys.modules):
            if name == "value_example_flat_offer" or name.startswith("value_example_flat_offer."):
                sys.modules.pop(name, None)
        root_text = str(self.modules)
        sys.path[:] = [item for item in sys.path if not str(item).startswith(root_text)]
        self.temporary.cleanup()

    def build(self, destination: Path | None = None) -> Path:
        target = destination or self.bundle
        build_module_bundle(
            manifest_path=EXAMPLE / "value-module.json",
            source_root=EXAMPLE / "src",
            license_path=ROOT / "LICENSE",
            readme_path=EXAMPLE / "README.md",
            destination=target,
        )
        return target

    def test_deterministic_builder_and_transactional_install(self) -> None:
        first = self.build()
        second = self.build(self.root / "second.zip")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        installation = install_module_bundle(
            first, trust_acknowledged=True, modules_root=self.modules
        )
        self.assertEqual(installation["module_id"], "example-flat-storage-offer")
        self.assertEqual(installation["conformance"]["status"], "passed")
        manifest_payload = json.loads((self.modules / "example-flat-storage-offer.json").read_text())
        self.assertEqual(installation["manifest_sha256"], hashlib.sha256(
            json.dumps(manifest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest())
        self.assertTrue((self.modules / "example-flat-storage-offer.json").is_file())
        self.assertEqual(len(list_module_installations(self.modules)), 1)
        registry = workspace_registry(self.modules)
        definition = registry.resolve("example-flat-storage-offer", expected_slot="storage_cost")
        offer = definition.create()
        offer.prepare_year(2025, capital_cost_gbp=1_000_000)
        self.assertEqual(offer.bid_price_gbp_per_mwh(12), 42.0)
        graph = registry.resolve_selection({
            "psm": "value-bid-at-cost-psm",
            "storage_cost": "example-flat-storage-offer",
            "pipeline": "planning-pipeline",
            "vre_cap": "vre-expansion-cap",
            "storage_cap": "value-storage-expansion-policy",
            "investment": "agent-investment",
            "transition": "value-annual-state-transition",
        })
        self.assertEqual(graph.identity("storage_cost").module_version, "1.0.0")
        self.assertEqual(graph.identity("storage_cost").source_sha256, installation["source_sha256"])

    def test_experimental_install_keeps_explicit_study_acknowledgement(self) -> None:
        from gridform_core.frontend_contract import validate_maturity_acknowledgements, EXPERIMENTAL_ACK
        manifest = json.loads((EXAMPLE / "value-module.json").read_text())
        manifest["status"] = "experimental"
        path = self.root / "experimental.json"
        path.write_text(json.dumps(manifest))
        build_module_bundle(manifest_path=path, source_root=EXAMPLE / "src", license_path=ROOT / "LICENSE", destination=self.bundle)
        installed = install_module_bundle(self.bundle, trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(installed["conformance"]["status"], "passed")
        self.assertEqual(installed["scientific_validation_status"], "not_evaluated")
        registry = workspace_registry(self.modules)
        self.assertEqual(registry.manifest(manifest["id"]).status, "experimental")
        with self.assertRaisesRegex(ValueError, "Experimental acknowledgement required"):
            validate_maturity_acknowledgements(registry, {"storage_cost": manifest["id"]}, (), {})
        validate_maturity_acknowledgements(registry, {"storage_cost": manifest["id"]}, (), {
            f"module:{manifest['id']}@{manifest['version']}": EXPERIMENTAL_ACK,
        })

    def test_trust_is_required_and_failed_install_leaves_no_registry_entry(self) -> None:
        bundle = self.build()
        with self.assertRaisesRegex(ModuleInstallationError, "executable Python") as caught:
            install_module_bundle(bundle, trust_acknowledged=False, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_TRUST_REQUIRED")
        self.assertFalse(self.modules.exists())

    def test_disable_and_enable_reuses_retained_installation(self) -> None:
        install_module_bundle(self.build(), trust_acknowledged=True, modules_root=self.modules)
        disabled = set_module_enabled(
            "example-flat-storage-offer", False, modules_root=self.modules
        )
        self.assertFalse(disabled["enabled"])
        self.assertFalse((self.modules / "example-flat-storage-offer.json").exists())
        with self.assertRaisesRegex(ValueError, "not registered"):
            workspace_registry(self.modules).manifest("example-flat-storage-offer")
        enabled = set_module_enabled(
            "example-flat-storage-offer", True, modules_root=self.modules
        )
        self.assertTrue(enabled["enabled"])
        self.assertIsNotNone(
            workspace_registry(self.modules).resolve(
                "example-flat-storage-offer", expected_slot="storage_cost"
            )
        )

    def test_builtin_id_cannot_be_shadowed(self) -> None:
        manifest = json.loads((EXAMPLE / "value-module.json").read_text(encoding="utf-8"))
        manifest["id"] = "value-bid-at-cost-psm"
        changed = self.root / "manifest.json"
        changed.write_text(json.dumps(manifest), encoding="utf-8")
        bundle = self.root / "shadow.zip"
        build_module_bundle(
            manifest_path=changed,
            source_root=EXAMPLE / "src",
            license_path=ROOT / "LICENSE",
            destination=bundle,
        )
        with self.assertRaises(ModuleInstallationError) as caught:
            install_module_bundle(bundle, trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_BUILTIN_COLLISION")
        self.assertFalse((self.modules / "value-bid-at-cost-psm.json").exists())

    def test_hash_mutation_is_rejected(self) -> None:
        original = self.build()
        mutated = self.root / "mutated.zip"
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(mutated, "w") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename.endswith("plugin.py"):
                    data += b"\n# changed after inventory\n"
                target.writestr(info, data)
        with self.assertRaises(ModuleBundleError) as caught:
            validate_module_bundle(mutated)
        self.assertEqual(caught.exception.code, "GF_MODULE_BUNDLE_HASH")

    def test_path_traversal_is_rejected(self) -> None:
        malicious = self.root / "traversal.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("../outside.py", "raise RuntimeError('must not execute')")
            archive.writestr("force-bundle.json", "{}")
            archive.writestr("value-module.json", "{}")
            archive.writestr("LICENSE", "test")
        with self.assertRaises(ModuleBundleError) as caught:
            validate_module_bundle(malicious)
        self.assertEqual(caught.exception.code, "GF_MODULE_BUNDLE_PATH")

    def test_duplicate_and_native_members_are_rejected(self) -> None:
        duplicate = self.root / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.writestr("force-bundle.json", "{}")
                archive.writestr("force-bundle.json", "{}")
                archive.writestr("value-module.json", "{}")
                archive.writestr("LICENSE", "test")
        with self.assertRaises(ModuleBundleError) as caught:
            validate_module_bundle(duplicate)
        self.assertEqual(caught.exception.code, "GF_MODULE_BUNDLE_DUPLICATE")

        native = self.root / "native.zip"
        with zipfile.ZipFile(native, "w") as archive:
            archive.writestr("force-bundle.json", "{}")
            archive.writestr("value-module.json", "{}")
            archive.writestr("LICENSE", "test")
            archive.writestr("src/plugin.py", "class Plugin: pass")
            archive.writestr("src/native.dll", b"MZ")
        with self.assertRaises(ModuleBundleError) as caught:
            validate_module_bundle(native)
        self.assertEqual(caught.exception.code, "GF_MODULE_BUNDLE_EXECUTABLE")

    def test_missing_callable_fails_before_promotion(self) -> None:
        broken_source = self.root / "broken-src" / "force_broken_offer"
        broken_source.mkdir(parents=True)
        (broken_source / "__init__.py").write_text("class Broken: pass\n", encoding="utf-8")
        manifest = json.loads((EXAMPLE / "value-module.json").read_text(encoding="utf-8"))
        manifest.update({
            "id": "broken-storage-offer",
            "implementation": "force_broken_offer:Broken",
        })
        manifest_path = self.root / "broken-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        broken_bundle = self.root / "broken.zip"
        build_module_bundle(
            manifest_path=manifest_path,
            source_root=broken_source.parent,
            license_path=ROOT / "LICENSE",
            destination=broken_bundle,
        )
        with self.assertRaises(ModuleInstallationError) as caught:
            install_module_bundle(
                broken_bundle, trust_acknowledged=True, modules_root=self.modules
            )
        self.assertEqual(caught.exception.code, "GF_MODULE_CONFORMANCE")
        self.assertFalse((self.modules / "broken-storage-offer.json").exists())
        self.assertFalse((self.modules / "installed" / "broken-storage-offer").exists())

    def test_external_psm_without_snapshot_capability_installs_normally(self) -> None:
        """Attribution support is optional rather than an installation barrier."""

        bundle = self.root / "external-psm.zip"
        build_module_bundle(
            manifest_path=EXTERNAL_PSM_EXAMPLE / "value-module.json",
            source_root=EXTERNAL_PSM_EXAMPLE / "src",
            license_path=ROOT / "LICENSE",
            readme_path=EXTERNAL_PSM_EXAMPLE / "README.md",
            destination=bundle,
        )
        installation = install_module_bundle(
            bundle, trust_acknowledged=True, modules_root=self.modules
        )

        self.assertEqual(installation["conformance"]["status"], "passed")
        manifest = workspace_registry(self.modules).manifest(
            "example-thermal-quantity-offer-psm", expected_slot="psm"
        )
        self.assertNotIn(
            "evidence.vre-counterfactual-snapshot/v1",
            manifest.provides_capabilities,
        )


if __name__ == "__main__":
    unittest.main()
