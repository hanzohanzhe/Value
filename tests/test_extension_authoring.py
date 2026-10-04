import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import backend.extension_authoring as authoring

from backend.extension_authoring import extension_proposal_template, validate_extension_proposal, build_extension_source_project
from gridform_core.v2.module_manifest import builtin_registry


class ExtensionAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.registry = builtin_registry()
        self.request = {"proposal": {"id": "author-audit-example", "name": "Audit example", "namespace": "community.audit-example", "version": "0.1.0",
            "question": "Can I inspect the recorded PSM input identity each year?", "validation_plan": "Verify the producer, year and input hash in a bounded check.",
            "migration_notes": "New namespace; existing state is not migrated."}}

    def test_reviewed_template_is_deterministic_and_rebuildable(self):
        report = validate_extension_proposal(self.request, self.registry)
        self.assertTrue(report["valid"], report["errors"])
        request = {**self.request, "expected_package_identity_sha256": report["package_identity_sha256"]}
        raw = extension_proposal_template(request, self.registry)
        self.assertEqual(raw, extension_proposal_template(request, self.registry))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), report["package_identity_sha256"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                manifest = json.loads(archive.read("force-extension.json"))
                self.assertEqual(manifest["maturity"], "experimental")
                self.assertEqual(manifest["data_roles"][0]["role"], "community.audit-example.audit-input")
                self.assertIn("does not calculate", archive.read("README.md").decode())
                source = archive.read(f"src/{report['source_package']}/hooks.py").decode()
                self.assertIn(repr(manifest["id"]), source)
                self.assertNotIn("bounded-test-input", source)
                archive.extractall(root / "project")
            result = build_extension_source_project(root / "project", root / "rebuilt.zip")
            self.assertEqual(result["bundle_sha256"], hashlib.sha256(raw).hexdigest())

    def test_changed_review_and_unsupported_scientific_claim_are_rejected(self):
        report = validate_extension_proposal(self.request, self.registry)
        changed = {"proposal": {**self.request["proposal"], "question": "Changed research question"}, "expected_package_identity_sha256": report["package_identity_sha256"]}
        with self.assertRaisesRegex(ValueError, "changed after review"):
            extension_proposal_template(changed, self.registry)
        for field, value in (("maturity", "ready"), ("hooks", []), ("composed_module_ids", ["uninstalled-module"])):
            with self.subTest(field=field):
                invalid = validate_extension_proposal({**self.request, "manifest": {**report["manifest"], field: value}}, self.registry)
                self.assertFalse(invalid["valid"])
                self.assertIsNone(invalid["package_identity_sha256"])
        manifest = json.loads(json.dumps(report["manifest"]))
        manifest["artifacts"][0]["summary_fields"] = ["system_cost"]
        self.assertFalse(validate_extension_proposal({**self.request, "manifest": manifest}, self.registry)["valid"])

    def test_namespace_paths_and_unknown_declarations_rejected(self):
        for key, value in (("id", "../escape"), ("namespace", "value.core.private"), ("version", "1")):
            report = validate_extension_proposal({"proposal": {**self.request["proposal"], key: value}}, self.registry)
            self.assertFalse(report["valid"])
        report = validate_extension_proposal(self.request, self.registry)
        manifest = report["manifest"]
        manifest["data_roles"][0]["typo"] = "do not silently ignore"
        self.assertFalse(validate_extension_proposal({**self.request, "manifest": manifest}, self.registry)["valid"])

    def test_unimplemented_capability_and_nonstring_identifiers_rejected(self):
        report = validate_extension_proposal(self.request, self.registry)
        invalid = {**report["manifest"], "provided_capabilities": ["domain.network.zonal_redispatch"]}
        self.assertFalse(validate_extension_proposal({**self.request, "manifest":invalid}, self.registry)["valid"])
        for target in ("state_schema_version", "artifact_type", "schema_version"):
            for value in (1, True, [], {}, "", " " , "x" * 201):
                with self.subTest(target=target,value=value):
                    manifest = json.loads(json.dumps(report["manifest"]))
                    if target == "state_schema_version":
                        manifest[target] = value
                    else:
                        manifest["artifacts"][0][target] = value
                    invalid = validate_extension_proposal({**self.request,"manifest":manifest},self.registry)
                    self.assertFalse(invalid["valid"])
                    self.assertIsNone(invalid["package_identity_sha256"])

    def test_final_download_bytes_must_match_reviewed_hash(self):
        report = validate_extension_proposal(self.request,self.registry)
        request = {**self.request,"expected_package_identity_sha256":report["package_identity_sha256"]}
        original_files = authoring._files
        calls = 0
        def changing_files(*args):
            nonlocal calls
            files = original_files(*args)
            calls += 1
            if calls == 2:
                files["LICENSE"] += b"\nchanged between review and download\n"
            return files
        with patch.object(authoring,"_files",changing_files), self.assertRaisesRegex(ValueError,"ZIP bytes changed"):
            extension_proposal_template(request,self.registry)


if __name__ == "__main__":
    unittest.main()
