import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.extension_results import query_extension_artifacts
from gridform_core.extension_framework import ExtensionManifest, HookDeclaration, ArtifactDeclaration, canonical_hash


class ExtensionResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "recorded-run"
        (self.root / "model-output").mkdir(parents=True)
        self.status = {"id": "container-run", "status": "completed"}
        self.manifest = ExtensionManifest(id="old-audit", name="Historical audit", version="1.0.0", licence="Apache-2.0",
            namespace="old.audit", provided_capabilities=("audit/v1",),
            artifacts=(ArtifactDeclaration("audit.summary", "application/json", "audit.result/v1", ("year", "value", "nested")),),
            hooks=(HookDeclaration("after_psm", "package_removed_since_run:OldHook"),))
        self.graph = {"schema_version": "value.resolved-extension-graph/v1",
            "extensions": [{"id": self.manifest.id, "version": self.manifest.version, "namespace": self.manifest.namespace,
                "manifest_sha256": canonical_hash(self.manifest.to_dict())}],
            "manifests": {self.manifest.id: self.manifest.to_dict()},
            "hook_source_identities": {self.manifest.id: [{"hook": "after_psm", "implementation": "package_removed_since_run:OldHook",
                "source_sha256": "a" * 64, "distribution": "installed-source"}]},
            "parameters": {}, "parameter_schema_hashes": {}, "hook_order": {"after_psm": [self.manifest.id]}}
        self.years = [{"schema_version": "value.year-result/v2", "year": year, "market": {"extensions": {"extension_artifacts": [{
            "producer_extension": self.manifest.id, "artifact_type": "audit.summary", "schema_version": "audit.result/v1",
            "source_inputs_sha256": "b" * 64, "year": year, "value": year - 2000, "nested": {"ignored": list(range(100))},
            "private_undeclared": "must not reach browser"}]}}} for year in (2025, 2026, 2027)]
        self.write()

    def write(self, recalculate_graph=True):
        if recalculate_graph:
            self.graph["graph_sha256"] = canonical_hash({"extensions": [self.graph["manifests"][item["id"]] for item in self.graph["extensions"]],
                **{key: self.graph[key] for key in ("hook_source_identities", "parameters", "parameter_schema_hashes", "hook_order")}})
        (self.root / "status.json").write_text(json.dumps(self.status))
        (self.root / "model-output/module-resolution.json").write_text(json.dumps({"graph_sha256": "c" * 64, "extension_graph": self.graph}))
        (self.root / "model-output/year-results-v2.json").write_text(json.dumps(self.years))

    def test_frozen_declarations_survive_uninstalled_code_and_paginate(self):
        with patch("gridform_core.extension_framework.ExtensionRegistry.manifest", side_effect=AssertionError("No current registry allowed")):
            first = query_extension_artifacts(self.root, {"limit": "1"})
            second = query_extension_artifacts(self.root, {"limit": 1, "offset": 1})
            scoped = query_extension_artifacts(self.root, {"extension_id": "old-audit", "year": "2027"})
        self.assertEqual(first["status"], "available")
        self.assertEqual(first["run_id"], "recorded-run")
        self.assertEqual(first["total"], 3)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["items"][0]["year"], 2025)
        self.assertEqual(second["items"][0]["year"], 2026)
        self.assertEqual(scoped["total"], 1)
        self.assertEqual(scoped["items"][0]["summary"], {"year": 2027, "value": 27, "nested": None})
        self.assertEqual(scoped["items"][0]["unavailable_summary_fields"], ["nested"])
        self.assertNotIn("private_undeclared", json.dumps(first))
        self.assertEqual(len(first["source"]["year_results"]["sha256"]), 64)

    def test_one_day_lesson_names_the_scope_instead_of_missing_year_results(self):
        # F-D2 (DECISIONS A16-3): the one-day lesson records the extension graph
        # but never runs its hooks and writes no year results.
        self.status["mode"] = "value_101_day"
        self.write()
        (self.root / "model-output/year-results-v2.json").unlink()
        result = query_extension_artifacts(self.root, {})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason_code"], "extensions_not_executed_in_scope")
        self.assertIn("runs the market step only", result["message"])
        self.assertIn("old-audit", result["message"])
        self.assertEqual([row["id"] for row in result["capabilities"]["extensions"]], ["old-audit"])
        self.assertNotEqual(result["reason_code"], "year_results_missing")
        # A scope that runs hooks still reports the missing evidence itself.
        self.status["mode"] = "smoke"
        (self.root / "status.json").write_text(json.dumps(self.status))
        self.assertEqual(query_extension_artifacts(self.root, {})["reason_code"], "year_results_missing")

    def test_old_declaration_and_hook_source_missing_are_unavailable(self):
        del self.graph["manifests"]
        self.write(False)
        self.assertEqual(query_extension_artifacts(self.root, {})["reason_code"], "frozen_extension_declarations_missing")
        self.graph["manifests"] = {self.manifest.id: self.manifest.to_dict()}
        self.graph["hook_source_identities"][self.manifest.id][0]["source_sha256"] = None
        self.write()
        result = query_extension_artifacts(self.root, {})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason_code"], "frozen_hook_source_identity_missing")
        self.assertEqual(result["items"], [])

    def test_owner_schema_and_input_source_fail_closed(self):
        artifact = self.years[0]["market"]["extensions"]["extension_artifacts"][0]
        for field, value, expected in (("producer_extension", "other", "artifact_owner_invalid"),
                                      ("schema_version", "audit.result/v2", "artifact_contract_invalid"),
                                      ("source_inputs_sha256", None, "artifact_contract_invalid"),
                                      ("source_inputs_sha256", "not-a-hash", "artifact_input_identity_invalid")):
            with self.subTest(field=field, value=value):
                original = artifact[field]; artifact[field] = value; self.write()
                result = query_extension_artifacts(self.root, {})
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["reason_code"], expected)
                self.assertEqual(result["items"], [])
                artifact[field] = original

    def test_frozen_hash_mismatch_is_invalid(self):
        self.graph["manifests"][self.manifest.id]["version"] = "2.0.0"
        self.write()
        self.assertEqual(query_extension_artifacts(self.root, {})["reason_code"], "extension_manifest_identity_mismatch")
        self.graph["manifests"][self.manifest.id] = self.manifest.to_dict()
        self.write()
        self.graph["graph_sha256"] = "d" * 64; self.write(False)
        self.assertEqual(query_extension_artifacts(self.root, {})["reason_code"], "frozen_extension_graph_hash_mismatch")

    def test_query_bounds_incomplete_run_and_file_limit(self):
        for query in ({"period": 1}, {"year": True}, {"limit": 0}, {"limit": None}, {"offset": -1}, {"extension_id": []}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                query_extension_artifacts(self.root, query)
        for run_status in ("running", "failed", "cancelled", "unknown"):
            with self.subTest(run_status=run_status):
                self.status["status"] = run_status; self.write()
                self.assertEqual(query_extension_artifacts(self.root, {})["status"], "withheld")
        self.status["status"] = "archived"
        for archived_from in (None, "failed", "cancelled", "unknown"):
            with self.subTest(archived_from=archived_from):
                self.status.pop("archived_from_status", None)
                if archived_from is not None:
                    self.status["archived_from_status"] = archived_from
                self.write()
                result = query_extension_artifacts(self.root, {})
                self.assertEqual(result["status"], "withheld")
                self.assertEqual(result["reason_code"], "run_not_completed")
                self.assertEqual(result["items"], [])
        self.status["archived_from_status"] = "completed"; self.write()
        self.assertEqual(query_extension_artifacts(self.root, {})["status"], "available")
        with patch("backend.extension_results.LIMITS", {"status": 65536, "module_resolution": 2 * 1024 * 1024, "year_results": 1}):
            result = query_extension_artifacts(self.root, {})
        self.assertEqual(result["reason_code"], "year_results_size_limit")
        self.assertEqual(result["status"], "unavailable")

    def test_changed_evidence_and_nonfinite_json_fail_closed(self):
        original_loads = json.loads
        graph_path = self.root / "model-output/module-resolution.json"
        def change_after_parsing(*args, **kwargs):
            value = original_loads(*args, **kwargs)
            if isinstance(value, dict) and "extension_graph" in value:
                graph_path.write_text(graph_path.read_text() + "\n")
            return value
        with patch("backend.extension_results.json.loads", side_effect=change_after_parsing):
            result = query_extension_artifacts(self.root, {})
        self.assertEqual(result["reason_code"], "source_changed_during_query")
        self.assertEqual(result["items"], [])
        self.write()
        path = self.root / "model-output/year-results-v2.json"
        path.write_text(path.read_text().replace('"value": 25', '"value": 1e999'))
        self.assertEqual(query_extension_artifacts(self.root, {})["reason_code"], "year_results_invalid_json")


if __name__ == "__main__":
    unittest.main()
