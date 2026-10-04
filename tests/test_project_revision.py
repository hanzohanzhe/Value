import tempfile
import unittest
from pathlib import Path

from gridform_core.project_revision import project_fingerprint, save_project_revision
from gridform_core.v2.module_manifest import workspace_registry


MODULES = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "storage_cost": "dynamic-annual-storage-cost",
}
PACK = {"schema_version": "value.data-pack/v1", "id": "pack", "bindings": {}}


class ProjectRevisionTests(unittest.TestCase):
    def setUp(self):
        self.registry = workspace_registry(Path("missing-modules-directory"))
        self.project = {
            "schema_version": "value.project/v1",
            "id": "p", "name": "Display name", "data_pack_id": "pack",
            "start_year": 2025, "end_year": 2034,
            "modules": MODULES,
            "parameters": {"planning.random_seed": 7},
            "runtime_options": {"runtime.market_trace_level": "summary"},
        }

    def test_fingerprint_is_canonical_and_ignores_display_name(self):
        reordered = {key: self.project[key] for key in reversed(list(self.project))}
        renamed = {**self.project, "name": "Another display name"}
        expected = project_fingerprint(self.project, self.registry, PACK)
        self.assertEqual(expected, project_fingerprint(reordered, self.registry, PACK))
        self.assertEqual(expected, project_fingerprint(renamed, self.registry, PACK))
        changed = {**self.project, "parameters": {"planning.random_seed": 8}}
        self.assertNotEqual(expected, project_fingerprint(changed, self.registry, PACK))

    def test_revisions_are_append_only_and_stale_edit_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "p"
            first = save_project_revision(root, self.project, self.registry, PACK)
            second_candidate = {**self.project, "parameters": {"planning.random_seed": 8}}
            second = save_project_revision(
                root, second_candidate, self.registry, PACK,
                expected_base_revision=str(first["revision_sha256"]),
            )
            self.assertEqual(second["parent_revision_sha256"], first["revision_sha256"])
            self.assertEqual(second["revision_number"], 2)
            self.assertEqual(len(list((root / "revisions").glob("*.json"))), 2)
            with self.assertRaisesRegex(ValueError, "revision conflict"):
                save_project_revision(
                    root, self.project, self.registry, PACK,
                    expected_base_revision=str(first["revision_sha256"]),
                )


if __name__ == "__main__":
    unittest.main()
