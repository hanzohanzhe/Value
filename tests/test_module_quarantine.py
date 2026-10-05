"""External module and extension fault isolation (P0-2, findings G4-01/G4-02).

R1-R6 reproduce the reviewed failures through the library entry points.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gridform_core.extension_bundle import (
    ExtensionBundleError,
    install_extension_bundle,
    set_extension_enabled,
)
from gridform_core.module_bundle import build_module_bundle
from gridform_core.module_installation import install_module_bundle, set_module_enabled
from gridform_core.v2.module_manifest import workspace_registry
from tests.module_lifecycle_fixtures import (
    EXAMPLE,
    ROOT,
    build_extension_bundle,
    forget_external_code,
    tree_digest,
    write_external_extension,
    write_external_module,
)

VALUE_101_MODULES = {
    "psm": "value-bid-at-cost-psm",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "investment": "agent-investment",
    "transition": "value-annual-state-transition",
}


class _TemporaryModules(unittest.TestCase):
    packages: tuple[str, ...] = ()

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory(prefix="value-p02-")
        self.root = Path(self.folder.name)
        self.modules = self.root / "modules"
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(forget_external_code, self.modules, self.packages)


class ReviewedFailureReproductions(_TemporaryModules):
    packages = ("value_example_flat_offer", "p02_broken_plugin", "p02_hook_broken")

    @unittest.expectedFailure  # reproduction; fixed by a later P0-2 step
    def test_r1_g401_enable_into_a_taken_namespace_is_refused_before_any_write(self) -> None:
        install_extension_bundle(build_extension_bundle(self.root / "a.zip", "g4-ns-a", "local.g4-shared"),
                                 trust_acknowledged=True, modules_root=self.modules)
        set_extension_enabled("g4-ns-a", False, modules_root=self.modules)
        install_extension_bundle(build_extension_bundle(self.root / "b.zip", "g4-ns-b", "local.g4-shared"),
                                 trust_acknowledged=True, modules_root=self.modules)
        before = tree_digest(self.modules)
        with self.assertRaises(ExtensionBundleError) as caught:
            set_extension_enabled("g4-ns-a", True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_EXTENSION_NAMESPACE_COLLISION")
        self.assertIn("g4-ns-b", str(caught.exception))
        self.assertEqual(tree_digest(self.modules), before)

    @unittest.expectedFailure  # reproduction; fixed by a later P0-2 step
    def test_r2_g402_a_broken_external_module_does_not_break_the_registry(self) -> None:
        write_external_module(self.modules, "p02-broken", "p02_broken_plugin",
                              prefix="raise RuntimeError('simulated broken import')\n")
        registry = workspace_registry(self.modules)
        self.assertNotIn("p02-broken", registry.manifests())
        self.assertIn("value-bid-at-cost-psm", registry.manifests())
        self.assertEqual([item.entry_id for item in registry.quarantined], ["p02-broken"])

    @unittest.expectedFailure  # reproduction; fixed by a later P0-2 step
    def test_r3_a_broken_hook_does_not_break_unrelated_draft_presets(self) -> None:
        from gridform_core.frontend_contract import system_domain_presets

        write_external_extension(self.modules, "p02-hook-ext", "local.p02-hook",
                                 hook_package="p02_hook_broken",
                                 hook_prefix="raise RuntimeError('broken hook import')\n")
        registry = workspace_registry(self.modules)
        presets = system_domain_presets(registry, VALUE_101_MODULES)
        self.assertTrue(presets)

    @unittest.expectedFailure  # reproduction; fixed by a later P0-2 step
    def test_r4_disable_leaves_no_module_of_the_package_loaded(self) -> None:
        bundle = self.root / "example.zip"
        build_module_bundle(manifest_path=EXAMPLE / "value-module.json", source_root=EXAMPLE / "src",
                            license_path=ROOT / "LICENSE", readme_path=EXAMPLE / "README.md", destination=bundle)
        install_module_bundle(bundle, trust_acknowledged=True, modules_root=self.modules)
        set_module_enabled("example-flat-storage-offer", False, modules_root=self.modules)
        root_text = str(self.modules.resolve())
        loaded = sorted(
            name for name, module in sys.modules.items()
            if str(getattr(module, "__file__", "") or "").startswith(root_text)
        )
        self.assertEqual(loaded, [])
        self.assertFalse([item for item in sys.path if str(item).startswith(root_text)])

    @unittest.expectedFailure  # reproduction; fixed by a later P0-2 step
    def test_r5_failed_install_leaves_no_source_root_on_sys_path(self) -> None:
        import gridform_core.module_installation as installation

        bundle = self.root / "example.zip"
        build_module_bundle(manifest_path=EXAMPLE / "value-module.json", source_root=EXAMPLE / "src",
                            license_path=ROOT / "LICENSE", readme_path=EXAMPLE / "README.md", destination=bundle)
        real = installation.activate_external_module_sources

        def activate_then_fail(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError("injected failure after promotion")

        with patch.object(installation, "activate_external_module_sources", activate_then_fail):
            with self.assertRaises(RuntimeError):
                install_module_bundle(bundle, trust_acknowledged=True, modules_root=self.modules)
        root_text = str(self.modules.resolve())
        self.assertFalse([item for item in sys.path if str(item).startswith(root_text)])
        self.assertFalse((self.modules / "example-flat-storage-offer.json").exists())

    @unittest.expectedFailure  # reproduction; fixed by a later P0-2 step
    def test_r6_a_schema_drifted_extension_can_still_be_disabled(self) -> None:
        install_extension_bundle(build_extension_bundle(self.root / "a.zip", "p02-drift", "local.p02-drift"),
                                 trust_acknowledged=True, modules_root=self.modules)
        for path in (self.modules / "extensions" / "p02-drift.json",
                     self.modules / "installed-extensions" / "p02-drift" / "0.1.0" / "force-extension.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["required_force_version"] = ">=0.5.0"
            path.write_text(json.dumps(payload), encoding="utf-8")
        record = set_extension_enabled("p02-drift", False, modules_root=self.modules)
        self.assertFalse(record["enabled"])
        self.assertFalse((self.modules / "extensions" / "p02-drift.json").exists())


if __name__ == "__main__":
    unittest.main()
