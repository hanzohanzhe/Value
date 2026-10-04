from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

from gridform_core.application import run_project_application
from gridform_core.extension_framework import (
    ExtensionManifest,
    ExtensionRegistry,
    ExtensionRuntime,
    validate_extension_artifact,
    validate_extension_state,
)
from gridform_core.extension_bundle import (
    DESCRIPTOR,
    ExtensionBundleError,
    install_extension_bundle,
    validate_extension_bundle,
)
from gridform_core.project_revision import project_fingerprint
from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"
TOY_ID = "value-toy-audit-extension"
MODULES = {
    "psm": "value-perfect-foresight-lp",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "transition": "value-annual-state-transition",
}


class Prompt65ExtensionFrameworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = workspace_registry(ROOT / "missing-local-modules")
        self.toy = self.registry.extension_registry.manifest(TOY_ID)

    def _pack_manifest_with_toy_role(self) -> dict[str, object]:
        manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
        bindings = dict(manifest["bindings"])
        bindings["value.toy-audit.series"] = {
            **dict(bindings["planning.success_rates"]),
            "role": "value.toy-audit.series",
            "unit": "dimensionless",
        }
        manifest["bindings"] = bindings
        return manifest

    def _extension_zip(self, path: Path, *, extra: dict[str, bytes] | None = None) -> Path:
        manifest = self.toy.to_dict()
        manifest.update({
            "id": "vendor-audit-extension",
            "name": "Vendor audit extension",
            "namespace": "vendor.audit",
            "data_roles": [], "parameters": [], "artifacts": [], "hooks": [],
            "state_schema_version": None,
        })
        files = {
            "force-extension.json": (json.dumps(manifest, indent=2) + "\n").encode(),
            "LICENSE": b"Apache-2.0\n",
            "README.md": b"# bounded test extension\n",
            **(extra or {}),
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

    def test_unselected_extension_does_not_change_v2_resolution_identity(self):
        first = self.registry.resolve_selection(MODULES)
        second = self.registry.resolve_selection(MODULES, selected_extensions=())
        self.assertEqual(first.graph_sha256, second.graph_sha256)
        self.assertNotIn("extension_graph", first.to_dict())

    def test_capability_data_parameters_state_and_artifact_are_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "data roles are not ready"):
            self.registry.resolve_selection(MODULES, selected_extensions=(TOY_ID,))
        graph = self.registry.resolve_selection(
            MODULES,
            selected_extensions=(TOY_ID,),
            available_data_roles=("value.toy-audit.series",),
            extension_parameters={"value.toy-audit.multiplier": 2.5},
        )
        self.assertEqual(graph.extension_graph.parameters["value.toy-audit.multiplier"], 2.5)
        with self.assertRaisesRegex(ValueError, "above"):
            self.registry.resolve_selection(
                MODULES,
                selected_extensions=(TOY_ID,),
                available_data_roles=("value.toy-audit.series",),
                extension_parameters={"value.toy-audit.multiplier": 11},
            )
        state = {
            self.toy.namespace: {
                "owner": TOY_ID,
                "schema_version": self.toy.state_schema_version,
                "years_seen": [2025],
            }
        }
        self.assertEqual(validate_extension_state(state, graph.extension_graph), state)
        with self.assertRaisesRegex(ValueError, "Orphaned"):
            validate_extension_state({"foreign.namespace": {}}, graph.extension_graph)
        runtime = ExtensionRuntime(graph.extension_graph)
        artifact = runtime.invoke("after_psm", {"year": 2025, "input_sha256": "a" * 64})[0]
        self.assertEqual(validate_extension_artifact(artifact, self.toy), artifact)
        with self.assertRaisesRegex(ValueError, "Undeclared"):
            validate_extension_artifact({**artifact, "artifact_type": "foreign"}, self.toy)

    def test_namespace_schema_and_hook_cycles_are_rejected(self):
        other = replace(self.toy, id="other-extension", version="1.0.1")
        with self.assertRaisesRegex(ValueError, "namespace collision"):
            ExtensionRegistry((self.toy, other))
        unsafe = replace(
            self.toy,
            id="unsafe-extension",
            namespace="vendor.unsafe",
            parameters=(replace(self.toy.parameters[0], name="vendor.unsafe.payload", value_type="object"),),
        )
        with self.assertRaisesRegex(ValueError, "unsupported JSON type"):
            ExtensionRegistry((unsafe,))
        first = replace(
            self.toy,
            id="cycle-one",
            namespace="vendor.cycle-one",
            data_roles=(), parameters=(), artifacts=(),
            hooks=(replace(self.toy.hooks[0], after=("cycle-two",)),),
        )
        second = replace(
            self.toy,
            id="cycle-two",
            namespace="vendor.cycle-two",
            data_roles=(), parameters=(), artifacts=(),
            hooks=(replace(self.toy.hooks[0], after=("cycle-one",)),),
        )
        registry = ExtensionRegistry((first, second))
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            registry.resolve(("cycle-one", "cycle-two"))

    def test_extension_graph_changes_project_fingerprint_only_when_selected(self):
        manifest = self._pack_manifest_with_toy_role()
        base = {
            "id": "base", "data_pack_id": manifest["id"], "start_year": 2025,
            "end_year": 2026, "modules": MODULES, "parameters": {},
        }
        unchanged = project_fingerprint(base, self.registry, manifest)
        self.assertEqual(unchanged, project_fingerprint(dict(base), self.registry, manifest))
        extended = {
            **base,
            "selected_extensions": [TOY_ID],
            "extension_parameters": {"value.toy-audit.multiplier": 2.0},
        }
        self.assertNotEqual(unchanged, project_fingerprint(extended, self.registry, manifest))

    def test_toy_extension_runs_two_years_through_normal_application_path(self):
        with tempfile.TemporaryDirectory(prefix="force-p65-") as temporary:
            root = Path(temporary)
            pack = root / "pack"
            shutil.copytree(PACK, pack)
            (pack / "manifest.json").write_text(
                json.dumps(self._pack_manifest_with_toy_role(), indent=2), encoding="utf-8"
            )
            project = {
                "id": "p65-toy-two-year", "data_pack_id": pack.name,
                "start_year": 2025, "end_year": 2026, "modules": MODULES,
                "selected_extensions": [TOY_ID],
                "extension_parameters": {"value.toy-audit.multiplier": 2.0},
                "parameters": {}, "runtime_options": {},
            }
            result = run_project_application(
                project, run_id="p65-toy", pack_root=pack,
                output_dir=root / "output", mode="two_year_smoke", registry=self.registry,
            )
            years = result["orchestrator_results"]
            self.assertEqual([item["year"] for item in years], [2025, 2026])
            for item in years:
                artifacts = item["market"]["extensions"]["extension_artifacts"]
                self.assertEqual(artifacts[0]["artifact_type"], "toy.audit.year-summary")
                state = item["next_state"]["extensions"]["extension_state"]
                self.assertIn(self.toy.namespace, state)
            resolution = json.loads(
                (root / "output" / "module-resolution.json").read_text(encoding="utf-8")
            )
            from gridform_core.bundle_validator import validate_run_bundle
            bundle_validation = validate_run_bundle(root / "output")
            self.assertEqual(
                resolution["extension_graph"]["extensions"][0]["id"], TOY_ID
            )
            self.assertTrue(bundle_validation["valid"], bundle_validation["errors"])

    def test_extension_zip_reuses_bounded_inventory_and_installs_transactionally(self):
        with tempfile.TemporaryDirectory(prefix="force-p65-bundle-") as temporary:
            root = Path(temporary)
            bundle = self._extension_zip(root / "extension.zip")
            validated = validate_extension_bundle(bundle)
            self.assertEqual(validated.manifest.id, "vendor-audit-extension")
            record = install_extension_bundle(
                bundle, trust_acknowledged=True, modules_root=root / "modules"
            )
            self.assertEqual(record["extension_id"], "vendor-audit-extension")
            self.assertTrue(
                (root / "modules" / "extensions" / "vendor-audit-extension.json").is_file()
            )
            with self.assertRaisesRegex(ExtensionBundleError, "Confirm trust"):
                install_extension_bundle(
                    bundle, trust_acknowledged=False, modules_root=root / "other"
                )

    def test_extension_zip_rejects_unlisted_executable_and_traversal(self):
        with tempfile.TemporaryDirectory(prefix="force-p65-malicious-") as temporary:
            root = Path(temporary)
            executable = self._extension_zip(
                root / "executable.zip", extra={"examples/payload.py": b"print('no')\n"}
            )
            with self.assertRaisesRegex(ExtensionBundleError, "Executable code"):
                validate_extension_bundle(executable)
            traversal = root / "traversal.zip"
            with zipfile.ZipFile(traversal, "w") as archive:
                archive.writestr("../escape.json", "{}")
            with self.assertRaisesRegex(ExtensionBundleError, "Unsafe"):
                validate_extension_bundle(traversal)


if __name__ == "__main__":
    unittest.main()
