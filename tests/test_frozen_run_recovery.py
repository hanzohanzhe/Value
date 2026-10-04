"""Recovery service boundaries; real frozen bytes, no worker or environment archive."""
import copy
import json
import unittest
from unittest.mock import patch

from backend import frozen_run_recovery as service
from gridform_core.frozen_input_integrity import verify_frozen_input_integrity
from gridform_core.run_policy import resolve_run_policy
from tests import test_frozen_input_integrity as integrity_fixtures
from tests import test_frozen_input_recovery as recovery_fixtures


class FrozenRunRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = integrity_fixtures.FrozenInputIntegrityTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        source_fixture = recovery_fixtures.FrozenInputRecoveryTests()
        source_fixture.root = self.root
        self.run, _ = source_fixture.source(network=True)
        self.snapshot = self.run / "input-snapshot"
        self.run = self.snapshot.parent
        # Scope is genuinely frozen, not merely inserted into mutable status.
        self.fixture.mutate(self.snapshot, "project.json", lambda p: p.update(start_year=2025, end_year=2026))
        self.fixture.rehash(self.snapshot)
        self.integrity = verify_frozen_input_integrity(self.snapshot)
        self.status = {"id": self.run.name, "project_id": self.integrity["project"]["id"],
            "status": "failed", "mode": "two_year_smoke",
            "input_snapshot_id": self.integrity["snapshot_id"],
            "input_tree_sha256": self.integrity["input_tree_sha256"],
            "run_policy": resolve_run_policy("two_year_smoke").to_dict(self.integrity["project"])}
        self.write_status()
        self.current = {"identity_sha256": "a" * 64, "source_sha256": "b" * 64, "environment_sha256": "c" * 64, "identity_complete": True}
        self.draft_patch = patch.object(service, "resolve_study_draft", side_effect=self.draft)
        self.draft_patch.start(); self.addCleanup(self.draft_patch.stop)
        self.ack_patch = patch.object(service, "maturity_acknowledgement_requirements", return_value=[])
        self.ack_patch.start(); self.addCleanup(self.ack_patch.stop)

    def write_status(self):
        (self.run / "status.json").write_text(json.dumps(self.status))

    def draft(self, candidate, **kwargs):
        result = copy.deepcopy(candidate)
        result["module_resolution_graph"] = copy.deepcopy(self.integrity["snapshot"]["module_resolution_graph"])
        return {"normalised_project": result, "errors": []}

    def review(self, run=None, mode="migration"):
        return service.review_frozen_recovery(run or self.run, mode, registry=None,
            module_catalog=[], dataset_slots=[], current_execution=lambda: copy.deepcopy(self.current),
            verify_archive=lambda record: None)

    def archived_identity(self):
        record = {**self.current, "archive_complete": True}
        self.fixture.mutate(self.snapshot, "project.json", lambda p: p.setdefault("extensions", {}).update(
            execution_bundle={"record_sha256": service.json_hash(record), "identity_sha256": record["identity_sha256"]}))
        self.fixture.rehash(self.snapshot)
        self.integrity = verify_frozen_input_integrity(self.snapshot)
        self.status.update(input_snapshot_id=self.integrity["snapshot_id"], input_tree_sha256=self.integrity["input_tree_sha256"])
        self.write_status()
        (self.run / "execution-bundle.json").write_text(json.dumps(record))

    def publish(self, request=None, validate=None, save=None):
        report, _ = self.review()
        request = request or {"name": "Independent", "acknowledge": True,
            "recovery_mode": "migration", "review_sha256": report["review_sha256"]}
        def default_save(path, candidate, registry, manifest):
            path.mkdir(); (path / "project.json").write_text(json.dumps(candidate)); return candidate
        return service.publish_frozen_recovery(self.run, request, review=self.review,
            projects_root=self.root / "projects", packs_root=self.root / "packs",
            network_packs_root=self.root / "network-products", staging_root=self.root / "staging",
            registry=None, validate_project=validate or (lambda p: {"valid": True, "normalised_project": p}),
            revision_manifest=lambda p, m: {}, is_reserved=lambda p: False, save_revision=save or default_save)

    def assert_empty_outputs(self):
        for name in ("projects", "packs", "network-products", "staging"):
            root = self.root / name
            self.assertFalse(root.exists() and any(root.iterdir()), name)

    def test_missing_archive_strict_rejects_migration_reports_changed_method(self):
        strict, _ = self.review(mode="strict")
        self.assertFalse(strict["allowed"])
        self.assertTrue(strict["missing_evidence"])
        # Simulate an installed graph change without altering historical data.
        original = self.draft
        def changed(candidate, **kwargs):
            draft = original(candidate, **kwargs)
            draft["normalised_project"]["module_resolution_graph"]["graph_sha256"] = "d" * 64
            return draft
        with patch.object(service, "resolve_study_draft", side_effect=changed):
            migration, context = self.review()
        self.assertTrue(migration["allowed"])
        self.assertIsNotNone(context)
        self.assertIn("module_resolution_graph", [row["field"] for row in migration["changes"]])
        self.assertEqual(migration["scope"], {"mode": "two_year_smoke", "start_year": 2025, "end_year": 2026, "periods_per_year": 2})

    def test_strict_matching_archive_and_identity_scope_status_conflicts(self):
        self.archived_identity()
        self.assertTrue(self.review(mode="strict")[0]["allowed"])
        for key, value in (("id", "other-run"), ("project_id", "other-study"), ("status", "running"), ("input_snapshot_id", "0" * 64)):
            old = self.status[key]; self.status[key] = value; self.write_status()
            self.assertFalse(self.review()[0]["allowed"], key)
            self.status[key] = old
        self.status["run_policy"]["periods_per_year"] = 3; self.write_status()
        self.assertFalse(self.review()[0]["allowed"])

    def test_stale_review_rejected_before_any_product(self):
        self.current["identity_complete"] = False
        self.assertFalse(self.review()[0]["allowed"])
        self.current["identity_complete"] = True
        report, _ = self.review()
        self.current["source_sha256"] = "d" * 64
        self.current["identity_sha256"] = "e" * 64
        with self.assertRaises(service.FrozenRecoveryError) as caught:
            self.publish({"name": "Independent", "acknowledge": True, "recovery_mode": "migration", "review_sha256": report["review_sha256"]})
        self.assertEqual(caught.exception.code, "GF_FROZEN_RECOVERY_REVIEW_STALE")
        self.assert_empty_outputs()

    def test_publication_source_unchanged_no_run_and_guards_reject_drift(self):
        before = {str(p.relative_to(self.run)): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        result = self.publish()
        self.assertFalse(result["run_started"])
        self.assertEqual(result["mode"], "two_year_smoke")
        project = result["project"]
        base = self.root / "packs" / project["data_pack_id"]
        network = self.root / "network-products" / project["market_configuration"]["network_pack_id"]
        self.assertTrue(base.is_dir()); self.assertTrue(network.is_dir())
        self.assertTrue((self.root / "projects" / project["id"] / "project.json").is_file())
        service.verify_recovered_configuration(project, mode=result["mode"], execution_identity=self.current["identity_sha256"])
        service.verify_recovered_inputs(project, base, network)
        changed = copy.deepcopy(project); changed["modules"]["psm"] = "different-method"
        for kwargs in ({"mode": "full"}, {"execution_identity": "f" * 64}):
            with self.assertRaises(service.FrozenRecoveryError):
                service.verify_recovered_configuration(project, **kwargs)
        with self.assertRaises(service.FrozenRecoveryError):
            service.verify_recovered_configuration(changed)
        for field in ("parameter_overrides", "runtime_controls"):
            alias_changed = copy.deepcopy(project)
            alias_changed[field] = {"different": True}
            with self.assertRaises(service.FrozenRecoveryError):
                service.verify_recovered_configuration(alias_changed)
        manifest = json.loads((base / "manifest.json").read_bytes())
        binding = next(iter(manifest["bindings"].values()))
        (base / binding["uri"]).write_bytes(b"changed canonical bytes")
        with self.assertRaises(service.FrozenRecoveryError):
            service.verify_recovered_inputs(project, base, network, frozen=True)
        self.assertEqual(before, {str(p.relative_to(self.run)): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})

    def test_validation_and_partial_save_failure_roll_back_both_products(self):
        with self.assertRaisesRegex(service.FrozenRecoveryError, "rejected"):
            self.publish(validate=lambda p: {"valid": False, "errors": ["rejected"]})
        self.assert_empty_outputs()
        def changes_scope(project):
            changed = copy.deepcopy(project)
            changed["end_year"] += 1
            return {"valid": True, "normalised_project": changed}
        with self.assertRaisesRegex(service.FrozenRecoveryError, "changed the reviewed"):
            self.publish(validate=changes_scope)
        self.assert_empty_outputs()
        def fail_save(path, *args):
            path.mkdir(); (path / "partial.json").write_text("{}"); raise OSError("save interrupted")
        with self.assertRaisesRegex(OSError, "save interrupted"):
            self.publish(save=fail_save)
        self.assert_empty_outputs()


if __name__ == "__main__":
    unittest.main()
