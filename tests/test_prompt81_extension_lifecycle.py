from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from gridform_core.extension_bundle import (
    DESCRIPTOR,
    ExtensionBundleError,
    install_extension_bundle,
    list_extension_installations,
    set_extension_enabled,
)


def extension_bundle(
    path: Path,
    *,
    version: str,
    readme: str = "fixture",
    migration: bool = False,
    extension_id: str = "vendor-lifecycle-extension",
) -> Path:
    manifest = {
        "schema_version": "value.extension-bundle/v1",
        "id": extension_id,
        "name": "Vendor lifecycle fixture",
        "version": version,
        "licence": "Apache-2.0",
        "namespace": "vendor.lifecycle",
        "provided_capabilities": ["vendor.lifecycle.audit/v1"],
        "required_capabilities": [],
        "composed_module_ids": [],
        "data_roles": [],
        "parameters": [],
        "artifacts": [],
        "hooks": [],
        "state_schema_version": f"vendor.lifecycle-state/v{version.split('.')[0]}",
        "state_migrations": {"1.0.0": "vendor.lifecycle-state/v2"} if migration else {},
        "required_force_version": ">=0.5.0",
        "required_contract_versions": {},
        "member_inventory": [],
        "maturity": "experimental",
    }
    files = {
        "force-extension.json": (json.dumps(manifest, indent=2) + "\n").encode(),
        "LICENSE": b"Apache-2.0\n",
        "README.md": (readme + "\n").encode(),
    }
    descriptor = {
        "schema_version": "value.extension-bundle/v1",
        "manifest": "force-extension.json",
        "files": [
            {"path": name, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for name, value in sorted(files.items())
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(DESCRIPTOR, json.dumps(descriptor))
        for name, value in files.items():
            archive.writestr(name, value)
    return path


class Prompt81ExtensionLifecycleTests(unittest.TestCase):
    def test_idempotence_same_version_collision_upgrade_downgrade_and_toggle(self):
        with tempfile.TemporaryDirectory(prefix="value-p81-") as temporary:
            root = Path(temporary)
            modules = root / "modules"
            v1 = extension_bundle(root / "v1.zip", version="1.0.0")
            first = install_extension_bundle(v1, trust_acknowledged=True, modules_root=modules)
            self.assertEqual(first["version"], "1.0.0")
            second = install_extension_bundle(v1, trust_acknowledged=True, modules_root=modules)
            self.assertTrue(second["idempotent"])

            changed = extension_bundle(root / "v1-changed.zip", version="1.0.0", readme="different bytes")
            with self.assertRaisesRegex(ExtensionBundleError, "same extension version") as collision:
                install_extension_bundle(changed, trust_acknowledged=True, modules_root=modules)
            self.assertEqual(collision.exception.code, "GF_EXTENSION_VERSION_COLLISION")

            missing_migration = extension_bundle(root / "v2-bad.zip", version="2.0.0")
            with self.assertRaisesRegex(ExtensionBundleError, "state migration") as migration_error:
                install_extension_bundle(missing_migration, trust_acknowledged=True, modules_root=modules)
            self.assertEqual(migration_error.exception.code, "GF_EXTENSION_MIGRATION_REQUIRED")

            v2 = extension_bundle(root / "v2.zip", version="2.0.0", migration=True)
            upgraded = install_extension_bundle(v2, trust_acknowledged=True, modules_root=modules)
            self.assertEqual(upgraded["upgraded_from"], "1.0.0")
            records = list_extension_installations(modules)
            self.assertEqual(sum(bool(item["enabled"]) for item in records), 1)
            self.assertEqual(next(item for item in records if item["enabled"])["version"], "2.0.0")

            with self.assertRaisesRegex(ExtensionBundleError, "downgrade") as downgrade:
                install_extension_bundle(v1, trust_acknowledged=True, modules_root=modules)
            self.assertEqual(downgrade.exception.code, "GF_EXTENSION_DOWNGRADE")

            disabled = set_extension_enabled(
                "vendor-lifecycle-extension", False, modules_root=modules
            )
            self.assertFalse(disabled["enabled"])
            self.assertFalse((modules / "extensions" / "vendor-lifecycle-extension.json").exists())
            enabled = set_extension_enabled(
                "vendor-lifecycle-extension", True, modules_root=modules
            )
            self.assertTrue(enabled["enabled"])
            self.assertTrue((modules / "extensions" / "vendor-lifecycle-extension.json").is_file())

    def test_built_in_lifecycle_is_not_available(self):
        with tempfile.TemporaryDirectory(prefix="value-p81-built-in-") as temporary:
            with self.assertRaisesRegex(ExtensionBundleError, "Built-in") as error:
                set_extension_enabled(
                    "value-network-contract-extension", False,
                    modules_root=Path(temporary),
                )
            self.assertEqual(error.exception.code, "GF_EXTENSION_BUILTIN_LIFECYCLE")


if __name__ == "__main__":
    unittest.main()
