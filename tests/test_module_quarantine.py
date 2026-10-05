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
from gridform_core.module_quarantine import (
    ExtensionHookImportError,
    ModuleQuarantinedError,
    clear_negative_caches,
    hook_quarantine_entries,
    selection_blockers,
)
from gridform_core.v2.module_manifest import ModuleManifest, ModuleRegistryV2, load_manifests, workspace_registry
from tests.module_lifecycle_fixtures import (
    EXAMPLE,
    IMPORT_FAILURES,
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
        clear_negative_caches()
        self.addCleanup(clear_negative_caches)


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

    def test_r2_g402_a_broken_external_module_does_not_break_the_registry(self) -> None:
        write_external_module(self.modules, "p02-broken", "p02_broken_plugin",
                              prefix="raise RuntimeError('simulated broken import')\n")
        registry = workspace_registry(self.modules)
        self.assertNotIn("p02-broken", registry.manifests())
        self.assertIn("value-bid-at-cost-psm", registry.manifests())
        self.assertEqual([item.entry_id for item in registry.quarantined], ["p02-broken"])

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

class RegistryQuarantineTests(_TemporaryModules):
    """P0-2 S3: two-pass isolation, coded hook failures, strict gates."""

    packages = ("p02_good_a", "p02_good_b", "p02_bad", "p02_dup_a", "p02_dup_b", "p02_counted",
                "p02_hook_bad", "p02_hook_good")

    def _builtin_manifests(self):
        return load_manifests(Path(__file__).resolve().parents[1] / "gridform_core" / "manifests")

    def test_every_kind_of_import_failure_is_quarantined_with_its_cause(self) -> None:
        for index, (name, prefix) in enumerate(sorted(IMPORT_FAILURES.items())):
            write_external_module(self.modules, f"p02-bad-{index}", f"p02_bad_{index}", prefix=prefix)
        registry = workspace_registry(self.modules)
        entries = {entry.entry_id: entry for entry in registry.quarantined}
        self.assertEqual(sorted(entries), [f"p02-bad-{index}" for index in range(len(IMPORT_FAILURES))])
        observed = {entry.error_type for entry in entries.values()}
        self.assertEqual(observed, {"RuntimeError", "SyntaxError", "SystemExit", "ModuleNotFoundError"})
        for entry in entries.values():
            self.assertEqual(entry.code, "GF_MODULE_IMPORT_FAILED")
            self.assertIn("failed to import", entry.message)
            self.assertNotIn(str(self.modules), entry.message)
            self.assertTrue(entry.blocking)
        self.assertEqual(
            list(registry.manifests()), [item.id for item in self._builtin_manifests()],
        )

    def test_independent_oracle_builtins_plus_healthy_externals_in_original_order(self) -> None:
        write_external_module(self.modules, "p02-good-b", "p02_good_b")
        write_external_module(self.modules, "p02-bad", "p02_bad", prefix="raise RuntimeError('no')\n")
        write_external_module(self.modules, "p02-good-a", "p02_good_a")
        write_external_extension(self.modules, "p02-ext-good", "local.p02-good")
        registry = workspace_registry(self.modules)
        healthy = [path for path in sorted(self.modules.glob("*.json")) if path.stem != "p02-bad"]
        oracle = ModuleRegistryV2(tuple(self._builtin_manifests()) + tuple(
            ModuleManifest.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in healthy
        ))
        self.assertEqual(list(registry.manifests()), list(oracle.manifests()))
        self.assertEqual(registry.catalog(), oracle.catalog())
        self.assertIn("p02-ext-good", registry.extension_manifests())

    def test_a_registry_that_builds_today_is_unchanged(self) -> None:
        from gridform_core.extension_framework import load_extension_manifests

        write_external_module(self.modules, "p02-good-a", "p02_good_a")
        write_external_extension(self.modules, "p02-ext-good", "local.p02-good")
        registry = workspace_registry(self.modules)
        builtin_root = Path(__file__).resolve().parents[1] / "gridform_core"
        legacy = ModuleRegistryV2(
            tuple(self._builtin_manifests()) + tuple(
                ModuleManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
                for path in sorted(self.modules.glob("*.json"))),
            tuple(load_extension_manifests(builtin_root / "extension_manifests"))
            + tuple(load_extension_manifests(self.modules / "extensions")),
        )
        self.assertEqual(registry.quarantined, ())
        self.assertEqual([item.to_dict() for item in registry.manifests().values()],
                         [item.to_dict() for item in legacy.manifests().values()])
        self.assertEqual([item.to_dict() for item in registry.extension_manifests().values()],
                         [item.to_dict() for item in legacy.extension_manifests().values()])

    def test_external_id_collisions_never_silently_replace(self) -> None:
        write_external_module(self.modules, "value-bid-at-cost-psm", "p02_good_a")
        write_external_module(self.modules, "p02-dup", "p02_dup_a")
        (self.modules / "p02-dup.json").rename(self.modules / "p02-dup-first.json")
        write_external_module(self.modules, "p02-dup", "p02_dup_b", version="2.0.0")
        registry = workspace_registry(self.modules)
        by_code = {}
        for entry in registry.quarantined:
            by_code.setdefault(entry.code, []).append(entry)
        shadow = by_code["GF_MODULE_SHADOWS_BUILTIN"][0]
        self.assertTrue(shadow.shadows_registered)
        self.assertEqual(registry.manifest("value-bid-at-cost-psm").implementation.split(".")[0], "gridform_core")
        self.assertEqual(len(by_code["GF_MODULE_ID_DUPLICATE"]), 2)
        self.assertNotIn("p02-dup", registry.manifests())
        self.assertEqual(selection_blockers(registry, ["value-bid-at-cost-psm"]), ())
        self.assertEqual({entry.entry_id for entry in selection_blockers(registry, ["p02-dup"])}, {"p02-dup"})

    def test_extension_namespace_and_id_collisions_quarantine_every_party(self) -> None:
        write_external_extension(self.modules, "p02-ns-a", "local.p02-shared")
        write_external_extension(self.modules, "p02-ns-b", "local.p02-shared")
        write_external_extension(self.modules, "p02-other", "local.p02-other")
        (self.modules / "extensions" / "p02-other.json").rename(self.modules / "extensions" / "zz-copy.json")
        write_external_extension(self.modules, "p02-other", "local.p02-other-2")
        registry = workspace_registry(self.modules)
        codes = sorted((entry.entry_id, entry.code) for entry in registry.quarantined)
        self.assertEqual(codes, [
            ("p02-ns-a", "GF_EXTENSION_NAMESPACE_COLLISION"),
            ("p02-ns-b", "GF_EXTENSION_NAMESPACE_COLLISION"),
            ("p02-other", "GF_EXTENSION_ID_DUPLICATE"),
            ("p02-other", "GF_EXTENSION_ID_DUPLICATE"),
        ])
        self.assertFalse({"p02-ns-a", "p02-ns-b", "p02-other"} & set(registry.extension_manifests()))

    def test_unreadable_and_drifted_manifests_are_quarantined_by_file(self) -> None:
        self.modules.mkdir(parents=True)
        (self.modules / "broken.json").write_text("{not json", encoding="utf-8")
        write_external_extension(self.modules, "p02-drift", "local.p02-drift",
                                 manifest_overrides={"required_force_version": ">=0.5.0"})
        registry = workspace_registry(self.modules)
        rows = sorted((entry.kind, entry.manifest_file, entry.entry_id, entry.code) for entry in registry.quarantined)
        self.assertEqual(rows, [
            ("extension", "extensions/p02-drift.json", "p02-drift", "GF_EXTENSION_MANIFEST_INVALID"),
            ("module", "broken.json", None, "GF_MODULE_MANIFEST_INVALID"),
        ])

    def test_builtins_stay_fail_closed(self) -> None:
        import gridform_core.v2.module_manifest as manifest_module

        real = manifest_module.load_manifests

        def with_broken_builtin(path):
            rows = real(path)
            if path.name == "manifests" and path.parent.name == "gridform_core":
                broken = manifest_module.ModuleManifest.from_dict(
                    {**rows[0].to_dict(), "id": "p02-broken-builtin", "implementation": "p02_absent_builtin:X"})
                return rows + (broken,)
            return rows

        with patch.object(manifest_module, "load_manifests", with_broken_builtin):
            with self.assertRaisesRegex(ValueError, "p02-broken-builtin"):
                workspace_registry(self.modules)

    def test_strict_mode_refuses_any_quarantine(self) -> None:
        write_external_module(self.modules, "p02-bad", "p02_bad", prefix="raise RuntimeError('no')\n")
        with self.assertRaises(ModuleQuarantinedError) as caught:
            workspace_registry(self.modules, strict=True)
        self.assertEqual(caught.exception.code, "GF_MODULE_QUARANTINED")
        self.assertIsInstance(caught.exception, ValueError)

    def test_failed_imports_run_once_until_a_rescan(self) -> None:
        counter = self.root / "imports.txt"
        write_external_module(self.modules, "p02-counted", "p02_counted",
                              prefix="raise RuntimeError('counted failure')\n", counter_file=counter)
        workspace_registry(self.modules)
        workspace_registry(self.modules)
        self.assertEqual(counter.read_text(), "x")
        clear_negative_caches()
        workspace_registry(self.modules)
        self.assertEqual(counter.read_text(), "xx")

    def test_hook_import_failure_is_coded_and_runtime_quarantined(self) -> None:
        write_external_extension(self.modules, "p02-hook-ext", "local.p02-hook", hook_package="p02_hook_bad",
                                 hook_prefix="raise SystemExit('hook exits')\n")
        registry = workspace_registry(self.modules)
        with self.assertRaises(ExtensionHookImportError) as caught:
            registry.extension_registry.resolve(("p02-hook-ext",))
        self.assertEqual(caught.exception.code, "GF_EXTENSION_HOOK_IMPORT")
        self.assertIsInstance(caught.exception, ValueError)
        [entry] = hook_quarantine_entries()
        self.assertEqual((entry.entry_id, entry.error_type), ("p02-hook-ext", "SystemExit"))
        self.assertEqual([item.code for item in selection_blockers(registry, (), ["p02-hook-ext"])],
                         ["GF_EXTENSION_HOOK_IMPORT"])
        with self.assertRaises(ExtensionHookImportError):
            registry.validate_selection(VALUE_101_MODULES, selected_extensions=("p02-hook-ext",))

    def test_quarantined_current_version_cannot_skip_the_migration_check(self) -> None:
        install_extension_bundle(
            build_extension_bundle(self.root / "v1.zip", "p02-state", "local.p02-state", version="1.0.0",
                                   manifest_overrides={"state_schema_version": "local.p02-state/v1"}),
            trust_acknowledged=True, modules_root=self.modules)
        active = self.modules / "extensions" / "p02-state.json"
        payload = json.loads(active.read_text(encoding="utf-8"))
        payload["required_force_version"] = ">=0.5.0"
        active.write_text(json.dumps(payload), encoding="utf-8")
        self.assertIn("p02-state", {entry.entry_id for entry in workspace_registry(self.modules).quarantined})
        with self.assertRaises(ExtensionBundleError) as caught:
            install_extension_bundle(
                build_extension_bundle(self.root / "v2.zip", "p02-state", "local.p02-state", version="2.0.0",
                                       manifest_overrides={"state_schema_version": "local.p02-state/v2"}),
                trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_EXTENSION_MIGRATION_REQUIRED")

class PostWriteVerificationTests(_TemporaryModules):
    """P0-2 S4: in-process check plus a worker-like out-of-process probe."""

    packages = ("value_example_flat_offer", "p02_c_broken")

    def _g401_state(self) -> str:
        install_extension_bundle(build_extension_bundle(self.root / "a.zip", "g4-ns-a", "local.g4-shared"),
                                 trust_acknowledged=True, modules_root=self.modules)
        set_extension_enabled("g4-ns-a", False, modules_root=self.modules)
        install_extension_bundle(build_extension_bundle(self.root / "b.zip", "g4-ns-b", "local.g4-shared"),
                                 trust_acknowledged=True, modules_root=self.modules)
        return tree_digest(self.modules)

    def _example_bundle(self) -> Path:
        bundle = self.root / "example.zip"
        build_module_bundle(manifest_path=EXAMPLE / "value-module.json", source_root=EXAMPLE / "src",
                            license_path=ROOT / "LICENSE", readme_path=EXAMPLE / "README.md", destination=bundle)
        return bundle

    def test_in_process_check_is_a_second_line_of_defence(self) -> None:
        import gridform_core.extension_bundle as bundle_module
        import gridform_core.module_quarantine as quarantine

        before = self._g401_state()
        with patch.object(bundle_module, "_namespace_owner", return_value=None), \
                patch.object(quarantine, "run_registry_probe", side_effect=AssertionError("probe not reached")):
            with self.assertRaises(ExtensionBundleError) as caught:
                set_extension_enabled("g4-ns-a", True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_EXTENSION_REGISTRY_CONFLICT")
        self.assertEqual(tree_digest(self.modules), before)

    def test_probe_alone_still_refuses_and_rolls_back(self) -> None:
        import gridform_core.extension_bundle as bundle_module
        import gridform_core.module_quarantine as quarantine

        before = self._g401_state()
        with patch.object(bundle_module, "_namespace_owner", return_value=None), \
                patch.object(quarantine, "verify_registry_in_process", return_value=None):
            with self.assertRaises(ExtensionBundleError) as caught:
                set_extension_enabled("g4-ns-a", True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_PROBE_FAILED")
        self.assertIn("out-of-process", str(caught.exception))
        self.assertIn("g4-ns-b", str(caught.exception))
        self.assertEqual(tree_digest(self.modules), before)

    def test_a_failing_probe_rolls_an_install_back(self) -> None:
        import gridform_core.module_quarantine as quarantine

        with patch.object(quarantine, "probe_argv",
                          lambda python, prefix, report, root: [sys.executable, "-B", "-c", "raise SystemExit(5)"]):
            with self.assertRaises(ValueError) as caught:
                install_module_bundle(self._example_bundle(), trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_PROBE_FAILED")
        self.assertIn("exit 5", str(caught.exception))
        self.assertFalse((self.modules / "example-flat-storage-offer.json").exists())
        self.assertFalse((self.modules / "installed" / "example-flat-storage-offer").exists())

    def test_probe_timeout_is_reported_and_the_probe_is_reaped(self) -> None:
        import os
        import time
        import gridform_core.module_quarantine as quarantine

        pid_file = self.root / "probe.pid"
        script = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
        started = time.monotonic()
        with patch.object(quarantine, "PROBE_TIMEOUT_SECONDS", 3.0), \
                patch.object(quarantine, "probe_argv", lambda *a: [sys.executable, "-B", "-c", script]):
            with self.assertRaises(ValueError) as caught:
                install_module_bundle(self._example_bundle(), trust_acknowledged=True, modules_root=self.modules)
        elapsed = time.monotonic() - started
        self.assertEqual(caught.exception.code, "GF_MODULE_PROBE_TIMEOUT")
        self.assertLess(elapsed, 8.0)
        pid = int(pid_file.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertFalse((self.modules / "example-flat-storage-offer.json").exists())

    def test_an_existing_broken_module_does_not_block_another_install(self) -> None:
        write_external_module(self.modules, "p02-c-broken", "p02_c_broken", prefix="raise RuntimeError('C')\n")
        record = install_module_bundle(self._example_bundle(), trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(record["module_id"], "example-flat-storage-offer")
        registry = workspace_registry(self.modules)
        self.assertIn("example-flat-storage-offer", registry.manifests())
        self.assertEqual([entry.entry_id for entry in registry.quarantined], ["p02-c-broken"])

    def test_disable_never_runs_a_post_write_check(self) -> None:
        import gridform_core.module_quarantine as quarantine

        install_module_bundle(self._example_bundle(), trust_acknowledged=True, modules_root=self.modules)
        with patch.object(quarantine, "verify_after_write", side_effect=AssertionError("no check on disable")):
            record = set_module_enabled("example-flat-storage-offer", False, modules_root=self.modules)
        self.assertFalse(record["enabled"])

    def test_a_refused_extension_install_leaves_no_folder_behind(self) -> None:
        import gridform_core.module_quarantine as quarantine

        self.modules.mkdir(parents=True)
        before = tree_digest(self.modules, files_only=True)
        with patch.object(quarantine, "probe_argv",
                          lambda python, prefix, report, root: [sys.executable, "-B", "-c", "raise SystemExit(4)"]):
            with self.assertRaises(ExtensionBundleError) as caught:
                install_extension_bundle(build_extension_bundle(self.root / "x.zip", "p02-x", "local.p02-x"),
                                         trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_PROBE_FAILED")
        self.assertEqual(tree_digest(self.modules, files_only=True), before)
        self.assertFalse((self.modules / "installed-extensions" / "p02-x").exists())

    def test_probe_starts_like_a_worker(self) -> None:
        from backend.lifecycle.python_argv import worker_python_argv
        from gridform_core.module_quarantine import probe_argv

        probe = probe_argv("python3", Path("/prefix"), Path("/r.json"), Path("/m"))
        worker = worker_python_argv("python3", Path("/prefix"), match_parent_user_site=True)
        self.assertEqual(probe[:len(worker) - 2], worker[:-2])
        self.assertEqual(probe[len(worker) - 2:len(worker)], ["-m", "gridform_core.module_recovery"])


class ExtensionRuntimeStateTests(_TemporaryModules):
    """Review response (M1-P0-2): extension lifecycle leaves no import state.

    sys.path is part of the execution identity (execution_archive import
    paths), so a stale source root would make every later run fail its
    worker identity check.
    """

    packages = ("p02_rev_hooked", "p02_rev_bad")

    def _modules_paths(self) -> list[str]:
        root_text = str(self.modules.resolve())
        return [item for item in sys.path if str(item).startswith(root_text)]

    def _loaded(self, package: str) -> list[str]:
        return [name for name in sys.modules if name.split(".", 1)[0] == package]

    def test_a_refused_hooked_extension_install_leaves_sys_path_and_identity_unchanged(self) -> None:
        import gridform_core.module_quarantine as quarantine
        from backend.run_execution import current_execution

        self.modules.mkdir(parents=True)
        before = current_execution(source_root=ROOT, data_home=self.root)["identity_sha256"]
        bundle = build_extension_bundle(self.root / "hooked.zip", "p02-rev-hooked", "local.p02-rev-hooked",
                                        hook_package="p02_rev_hooked")
        with patch.object(quarantine, "probe_argv",
                          lambda python, prefix, report, root: [sys.executable, "-B", "-c", "raise SystemExit(4)"]):
            with self.assertRaises(ExtensionBundleError) as caught:
                install_extension_bundle(bundle, trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_PROBE_FAILED")
        self.assertEqual(self._modules_paths(), [])
        self.assertEqual(self._loaded("p02_rev_hooked"), [])
        self.assertFalse((self.modules / "installed-extensions" / "p02-rev-hooked").exists())
        self.assertEqual(current_execution(source_root=ROOT, data_home=self.root)["identity_sha256"], before)

    def test_disabling_a_hooked_extension_forgets_its_code(self) -> None:
        install_extension_bundle(
            build_extension_bundle(self.root / "hooked.zip", "p02-rev-hooked", "local.p02-rev-hooked",
                                   hook_package="p02_rev_hooked"),
            trust_acknowledged=True, modules_root=self.modules)
        workspace_registry(self.modules).extension_registry.resolve(("p02-rev-hooked",))
        self.assertTrue(self._loaded("p02_rev_hooked"))
        self.assertTrue(self._modules_paths())
        set_extension_enabled("p02-rev-hooked", False, modules_root=self.modules)
        self.assertEqual(self._loaded("p02_rev_hooked"), [])
        self.assertEqual(self._modules_paths(), [])

    def _broken_hook_resolved(self) -> None:
        from gridform_core.module_quarantine import degraded_reasons

        write_external_extension(self.modules, "p02-rev-bad", "local.p02-rev-bad", hook_package="p02_rev_bad",
                                 hook_prefix="raise RuntimeError('hook breaks')\n")
        registry = workspace_registry(self.modules)
        with self.assertRaises(ExtensionHookImportError):
            registry.extension_registry.resolve(("p02-rev-bad",))
        self.assertEqual(degraded_reasons(registry), [{"code": "GF_EXTENSION_HOOK_IMPORT", "count": 1}])

    def test_disabling_an_extension_clears_its_runtime_hook_quarantine(self) -> None:
        from gridform_core.module_quarantine import degraded_reasons

        self._broken_hook_resolved()
        set_extension_enabled("p02-rev-bad", False, modules_root=self.modules)
        self.assertEqual(hook_quarantine_entries(), ())
        self.assertEqual(degraded_reasons(workspace_registry(self.modules)), [])

    def test_a_hook_entry_of_an_unregistered_extension_is_not_a_live_reason(self) -> None:
        from gridform_core.module_quarantine import degraded_reasons, quarantine_report
        from gridform_core.module_recovery import disable

        self._broken_hook_resolved()
        disable(self.modules.resolve(), "extension", "p02-rev-bad")  # offline: no process state touched
        self.assertEqual(len(hook_quarantine_entries()), 1)
        registry = workspace_registry(self.modules)
        self.assertEqual(degraded_reasons(registry), [])
        self.assertEqual(quarantine_report(registry)["status"], "ok")
        self.assertEqual(selection_blockers(registry, (), ["p02-rev-bad"]), ())


if __name__ == "__main__":
    unittest.main()
