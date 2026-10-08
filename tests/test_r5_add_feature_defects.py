"""R5-4 (DECISIONS A28): add-feature defects of the R4 final four-role report (build c204aac).

Each class names the defect ids it covers (F-中n / F-低n of add-feature.md).
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

from gridform_core.extension_bundle import (
    ExtensionBundleError,
    _namespace_collision_message,
    install_extension_bundle,
    installed_extension_source_changes,
    set_extension_enabled,
)
from gridform_core.extension_framework import ARTIFACT_RECORDING_HOOKS, ExtensionRuntime
from gridform_core.preflight import _replacement_advice
from gridform_core.v2.module_manifest import workspace_registry
from tests.test_r4_module_extension_defects import LifecycleApiCase

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ID = "r54-observer"
ARTIFACT = "r54.observer.year-summary"


class SourceBundleCase(unittest.TestCase):
    """An installed source extension with initialize, after_psm and after_cem hooks."""

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory(prefix="value-r54-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.modules = self.root / "modules"
        self.package = "value_r54_" + uuid.uuid4().hex[:12]
        original = list(sys.path)
        self.addCleanup(self._forget, original)

    def _forget(self, original: list[str]) -> None:
        sys.path[:] = original
        for name in list(sys.modules):
            if name.startswith(self.package):
                del sys.modules[name]

    def source(self) -> str:
        artifact = (
            "{'schema_version': 'r54.observer/v1', 'producer_extension': %r, "
            "'artifact_type': %r, 'source_inputs_sha256': 'a' * 64, 'year': payload['year']}"
        ) % (EXTENSION_ID, ARTIFACT)
        return (
            "class Hooks:\n"
            "    def initialize(self, payload):\n"
            f"        return {{'owner': {EXTENSION_ID!r}, 'schema_version': 'r54.observer.state/v1'}}\n"
            "    def after_psm(self, payload):\n"
            f"        return {artifact}\n"
            "    def after_cem(self, payload):\n"
            "        if payload.get('emit_artifact'):\n"
            f"            return {artifact}\n"
            "        return {'status': 'observed'}\n"
        )

    def install(self) -> Path:
        hooks = [{"hook": name, "implementation": f"{self.package}.hooks:Hooks"}
                 for name in ("initialize", "after_psm", "after_cem")]
        manifest = {
            "schema_version": "value.extension-bundle/v1", "id": EXTENSION_ID, "name": "R5-4 observer",
            "version": "0.1.0", "licence": "Apache-2.0", "namespace": "local.r54", "provided_capabilities": [],
            "hooks": hooks, "state_schema_version": "r54.observer.state/v1",
            "state_migrations": {"0.1.0": "declaration-only"},
            "artifacts": [{"artifact_type": ARTIFACT, "media_type": "application/json",
                           "schema_version": "r54.observer/v1", "summary_fields": ["year"]}],
        }
        files = {
            "force-extension.json": json.dumps(manifest).encode(), "LICENSE": b"Apache-2.0",
            f"src/{self.package}/__init__.py": b"", f"src/{self.package}/hooks.py": self.source().encode(),
        }
        descriptor = {"schema_version": "value.extension-bundle/v1", "files": [
            {"path": name, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for name, value in files.items()
        ]}
        path = self.root / f"{self.package}.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in files.items():
                archive.writestr(name, value)
            archive.writestr("force-extension-bundle.json", json.dumps(descriptor))
        install_extension_bundle(path, trust_acknowledged=True, modules_root=self.modules)
        return self.modules / "installed-extensions" / EXTENSION_ID / "0.1.0" / "src" / self.package / "hooks.py"

    def runtime(self) -> ExtensionRuntime:
        graph = workspace_registry(self.modules).extension_registry.resolve([EXTENSION_ID])
        return ExtensionRuntime(graph)


class HookOutputRecordingTests(SourceBundleCase):
    """F-中3: an artifact from a hook whose output is not recorded is refused, not dropped."""

    def test_only_after_psm_records_artifacts(self) -> None:
        self.assertEqual(ARTIFACT_RECORDING_HOOKS, ("after_psm",))
        self.install()
        runtime = self.runtime()
        artifacts = runtime.invoke("after_psm", {"year": 2025, "input_sha256": "b" * 64})
        self.assertEqual([item["artifact_type"] for item in artifacts], [ARTIFACT])
        # A plain status mapping from another hook stays accepted (it is not recorded).
        self.assertEqual(runtime.invoke("after_cem", {"year": 2025}), ({"status": "observed"},))
        with self.assertRaises(ValueError) as caught:
            runtime.invoke("after_cem", {"year": 2025, "emit_artifact": True})
        message = str(caught.exception)
        self.assertIn(f"{EXTENSION_ID}:after_cem", message)
        self.assertIn(ARTIFACT, message)
        self.assertIn("only from after_psm", message)

    def test_generated_readme_states_what_a_run_records(self) -> None:
        source = (ROOT / "backend" / "extension_authoring.py").read_text(encoding="utf-8")
        self.assertIn("## What a Run records", source)
        self.assertIn("their return values are not recorded", source)
        for document in ("MODULE_DEVELOPER_101.md", "MODULE_DEVELOPER_101_ZH.md"):
            text = (ROOT / "docs" / document).read_text(encoding="utf-8")
            self.assertIn("after_cem", text, document)


class EditedSourceEnableTests(SourceBundleCase):
    """F-中1 (partial): Enable still verifies the install identity, and now says how to recover."""

    def test_refusal_names_the_file_and_both_ways_out(self) -> None:
        hooks = self.install()
        original = hooks.read_bytes()
        hooks.write_bytes(original + b"# edited in place\n")
        self.assertEqual(len(installed_extension_source_changes(modules_root=self.modules)), 1)
        set_extension_enabled(EXTENSION_ID, False, modules_root=self.modules)
        with self.assertRaises(ExtensionBundleError) as caught:
            set_extension_enabled(EXTENSION_ID, True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_EXTENSION_SOURCE_CHANGED")
        message = str(caught.exception)
        self.assertIn(f"{self.package}.hooks", message)
        self.assertIn("restore the original files", message)
        self.assertIn("new version and Python package", message)
        hooks.write_bytes(original)
        set_extension_enabled(EXTENSION_ID, True, modules_root=self.modules)
        self.assertIn(EXTENSION_ID, workspace_registry(self.modules).extension_manifests())


class WordingTests(unittest.TestCase):
    """F-低1 (extension, not module) and F-低2 (the always-available way out first)."""

    def test_replacement_advice_by_kind(self) -> None:
        self.assertEqual(_replacement_advice([{"kind": "module"}]), "select another module in the Study")
        self.assertEqual(_replacement_advice([{"kind": "extension"}]),
                         "deselect the extension in the Study (saved as a new revision)")
        self.assertIn("or deselect the extension", _replacement_advice([{"kind": "module"}, {"kind": "extension"}]))

    def test_namespace_collision_offers_rebuild_first(self) -> None:
        message = _namespace_collision_message("local.fin-af", "fin-af-observer", "fin-af-copy", "installing")
        self.assertLess(message.index("its own namespace"), message.index("disable fin-af-observer"))
        self.assertIn("possible only while no saved Study or retained Run uses fin-af-observer", message)


class DuplicateStudyNameApiTests(LifecycleApiCase):
    """F-中2: a new Study whose name maps to an existing Study ID is refused as a name clash."""

    def setUp(self) -> None:
        import shutil

        super().setUp()
        shutil.copytree(ROOT / "data-packs" / "value-101-baseline-v1", self.home / "data-packs" / "value-101-baseline-v1")

    def study(self, **extra) -> dict:
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        project.pop("id", None)
        return {**project, "name": "VALUE 101 baseline · extension study", **extra}

    def test_second_new_study_with_the_same_name(self) -> None:
        status, first = self.request("POST", "/api/projects", self.study())
        self.assertEqual(status, 201, first)
        saved = first["project"]
        status, body = self.request("POST", "/api/projects", self.study(purpose="second draft"))
        self.assertEqual((status, body.get("error_code")), (409, "GF_STUDY_ID_EXISTS"), body)
        self.assertIn(saved["id"], body["error"])
        self.assertIn("another name", body["error"])
        self.assertNotIn("revision conflict", body["error"])
        # An edit of the saved Study (with its base revision) is unaffected.
        status, body = self.request("POST", "/api/projects", self.study(
            id=saved["id"], purpose="edited", base_revision_sha256=saved["revision_sha256"]))
        self.assertEqual(status, 201, body)
        # A stale base revision still reports the revision conflict.
        status, body = self.request("POST", "/api/projects", self.study(
            id=saved["id"], purpose="stale", base_revision_sha256="0" * 64))
        self.assertEqual(status, 409, body)
        self.assertIn("revision conflict", body["error"])


if __name__ == "__main__":
    unittest.main()
