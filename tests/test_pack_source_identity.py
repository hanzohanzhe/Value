"""A frozen run-input pack keeps the identity its methodology pin names (Q3).

``run_snapshot._freeze_pack`` rewrites the bindings of the pack copy a Run
executes on; the whitelist identifies that copy by its recorded, verified
source manifest (``gridform_core.pack_source_identity``).
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from gridform_core import methodology, pack_source_identity
from gridform_core.methodology import REFERENCE_PROFILE_ID
from gridform_core.run_snapshot import create_run_input_snapshot
from gridform_core.v2.module_manifest import workspace_registry

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data-packs" / "value-101-baseline-v1"
VALUE_101_SHAS = {
    "8fe24b8a54251131d22a28b446deaf395f1148ee138d5d0333d14c88cdc2ac4c",  # manifest file bytes
    "76d51a937000cba6cd85991e170245a43f45e7688cfa2cdc84019c886127a3cc",  # canonical JSON
}


class FrozenPackIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        run = Path(cls.folder.name) / "runs" / "r"
        run.mkdir(parents=True)
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        project = methodology.with_profile(dict(project, id="d1"), REFERENCE_PROFILE_ID)
        create_run_input_snapshot(
            run_dir=run, project=project, pack_root=PACK_ROOT,
            registry=workspace_registry(Path("missing-modules-directory")),
            selected=project["modules"], object_root=Path(cls.folder.name) / "objects",
        )
        cls.frozen_bytes = (run / "input-snapshot" / "pack" / "manifest.json").read_bytes()
        cls.source = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def frozen(self):
        return json.loads(self.frozen_bytes.decode("utf-8"))

    def violations(self, manifest, raw=None):
        return methodology.combination_violations(REFERENCE_PROFILE_ID, data_packs=[(manifest, raw)])

    def test_the_frozen_copy_is_identified_by_its_source_manifest(self):
        frozen = self.frozen()
        self.assertTrue(frozen["snapshot_frozen"])
        # The freeze really rewrote the bindings: the frozen manifest is not the pinned one.
        self.assertNotIn(pack_source_identity.canonical_sha256(frozen), VALUE_101_SHAS)
        self.assertEqual(pack_source_identity.source_manifest(frozen), self.source)
        self.assertEqual(methodology.manifest_sha256_candidates(frozen, self.frozen_bytes) & VALUE_101_SHAS,
                         {"76d51a937000cba6cd85991e170245a43f45e7688cfa2cdc84019c886127a3cc"})
        self.assertEqual(self.violations(frozen, self.frozen_bytes), [])
        record = frozen[pack_source_identity.SOURCE_FIELD]
        self.assertEqual(record["file_sha256"], "8fe24b8a54251131d22a28b446deaf395f1148ee138d5d0333d14c88cdc2ac4c")

    def test_an_inconsistent_source_record_is_ignored(self):
        role = sorted(self.frozen()["bindings"])[0]
        tampered = []
        # The frozen data differs from the recorded source data.
        manifest = self.frozen()
        manifest["bindings"][role]["sha256"] = "0" * 64
        manifest["bindings"][role]["normalized_sha256"] = "0" * 64
        tampered.append(manifest)
        # The frozen binding claims a different source digest.
        manifest = self.frozen()
        manifest["bindings"][role]["source_sha256"] = "0" * 64
        tampered.append(manifest)
        # A field the freeze does not rewrite was edited after freezing.
        manifest = self.frozen()
        manifest["bindings"][role]["unit"] = "GWh"
        tampered.append(manifest)
        # A manifest-level field was edited after freezing.
        manifest = self.frozen()
        manifest["periods_per_year"] = 8760
        tampered.append(manifest)
        # A role was added or removed.
        manifest = self.frozen()
        manifest["bindings"].pop(role)
        tampered.append(manifest)
        # The record's own canonical sha does not describe its bindings.
        manifest = self.frozen()
        manifest[pack_source_identity.SOURCE_FIELD]["bindings"][role]["unit"] = "GWh"
        tampered.append(manifest)
        for index, manifest in enumerate(tampered):
            with self.subTest(case=index):
                self.assertIsNone(pack_source_identity.source_manifest(manifest))
                rows = self.violations(manifest)
                self.assertEqual([row["sub_reason"] for row in rows], ["data_pack"])
                self.assertIn("no verifiable source manifest identity", rows[0]["message"])

    def test_a_snapshot_without_a_source_record_is_refused(self):
        """Snapshots frozen before the record existed do not borrow the pin."""

        manifest = self.frozen()
        manifest.pop(pack_source_identity.SOURCE_FIELD)
        self.assertEqual([row["sub_reason"] for row in self.violations(manifest)], ["data_pack"])

    def test_a_source_record_on_an_unfrozen_pack_is_ignored(self):
        """A workspace pack cannot whitelist itself by copying a source record."""

        manifest = copy.deepcopy(self.source)
        manifest["bindings"][sorted(manifest["bindings"])[0]]["unit"] = "GWh"
        manifest[pack_source_identity.SOURCE_FIELD] = self.frozen()[pack_source_identity.SOURCE_FIELD]
        self.assertEqual([row["sub_reason"] for row in self.violations(manifest)], ["data_pack"])
        self.assertEqual(self.violations(self.source), [])


if __name__ == "__main__":
    unittest.main()
