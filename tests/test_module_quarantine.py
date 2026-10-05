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

class LifecycleHygieneTests(_TemporaryModules):
    """P0-2 S2: coded conflicts, raw-record lifecycle, byte rollback, one lock."""

    packages = ("p02_hygiene_plugin",)

    def test_install_into_a_taken_namespace_names_the_real_owner(self) -> None:
        install_extension_bundle(build_extension_bundle(self.root / "a.zip", "p02-owner", "local.p02-shared"),
                                 trust_acknowledged=True, modules_root=self.modules)
        before = tree_digest(self.modules)
        with self.assertRaises(ExtensionBundleError) as caught:
            install_extension_bundle(build_extension_bundle(self.root / "b.zip", "p02-late", "local.p02-shared"),
                                     trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_EXTENSION_NAMESPACE_COLLISION")
        self.assertIn("owned by enabled extension p02-owner", str(caught.exception))
        self.assertEqual(tree_digest(self.modules), before)

    def test_builtin_namespace_is_reported_with_its_owner(self) -> None:
        from gridform_core.extension_bundle import _builtin_extensions

        builtin = _builtin_extensions()[0]
        with self.assertRaises(ExtensionBundleError) as caught:
            install_extension_bundle(build_extension_bundle(self.root / "c.zip", "p02-shadow", builtin.namespace),
                                     trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_EXTENSION_NAMESPACE_COLLISION")
        self.assertIn(builtin.id, str(caught.exception))

    def test_failed_module_enable_restores_every_byte(self) -> None:
        import gridform_core.module_installation as installation

        write_external_module(self.modules, "p02-hygiene", "p02_hygiene_plugin", enabled=False)
        before = tree_digest(self.modules)
        failed = {"module_id": "p02-hygiene", "status": "failed", "errors": ["injected"], "warnings": []}
        with patch.object(installation, "check_manifest", return_value=failed):
            with self.assertRaises(ValueError) as caught:
                set_module_enabled("p02-hygiene", True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_CONFORMANCE")
        self.assertEqual(tree_digest(self.modules), before)
        root_text = str(self.modules.resolve())
        self.assertFalse([name for name, module in sys.modules.items()
                          if str(getattr(module, "__file__", "") or "").startswith(root_text)])

    def test_failed_extension_enable_restores_every_byte(self) -> None:
        install_extension_bundle(build_extension_bundle(self.root / "a.zip", "p02-toggle", "local.p02-toggle"),
                                 trust_acknowledged=True, modules_root=self.modules)
        set_extension_enabled("p02-toggle", False, modules_root=self.modules)
        before = tree_digest(self.modules)
        import gridform_core.extension_bundle as bundle_module

        real = bundle_module.activate_external_module_sources
        calls = []

        def fail_once(*args, **kwargs):
            calls.append(1)
            real(*args, **kwargs)
            if len(calls) == 1:
                raise RuntimeError("injected failure after the write")

        with patch.object(bundle_module, "activate_external_module_sources", fail_once):
            with self.assertRaises(RuntimeError):
                set_extension_enabled("p02-toggle", True, modules_root=self.modules)
        self.assertEqual(tree_digest(self.modules), before)

    def test_lifecycle_entry_points_hold_the_module_lifecycle_lock(self) -> None:
        import gridform_core.module_installation as installation
        from gridform_core.module_quarantine import MODULE_LIFECYCLE_LOCK

        write_external_module(self.modules, "p02-hygiene", "p02_hygiene_plugin")
        owned = []
        real = installation.purge_source_root

        def record(*args, **kwargs):
            owned.append(MODULE_LIFECYCLE_LOCK._is_owned())
            return real(*args, **kwargs)

        with patch.object(installation, "purge_source_root", record):
            set_module_enabled("p02-hygiene", False, modules_root=self.modules)
        self.assertEqual(owned, [True])
        self.assertFalse(MODULE_LIFECYCLE_LOCK._is_owned())


if __name__ == "__main__":
    unittest.main()
