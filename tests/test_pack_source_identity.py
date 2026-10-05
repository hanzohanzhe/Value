"""A frozen run-input pack keeps the identity its methodology pin names (Q3).

``run_snapshot._freeze_pack`` rewrites the bindings of the pack copy a Run
executes on; the whitelist identifies that copy by its recorded, verified
source manifest (``gridform_core.pack_source_identity``).
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gridform_core import methodology, pack_source_identity
from gridform_core.methodology import REFERENCE_PROFILE_ID
from gridform_core.run_snapshot import create_run_input_snapshot
from gridform_core.v2.module_manifest import workspace_registry

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data-packs" / "value-101-baseline-v1"
VALUE_101_FILE_SHA = "8fe24b8a54251131d22a28b446deaf395f1148ee138d5d0333d14c88cdc2ac4c"
VALUE_101_CANONICAL_SHA = "76d51a937000cba6cd85991e170245a43f45e7688cfa2cdc84019c886127a3cc"
VALUE_101_SHAS = {VALUE_101_FILE_SHA, VALUE_101_CANONICAL_SHA}


def freeze(run_dir: Path, pack_root: Path, object_root: Path) -> bytes:
    """Freeze D1 (doctoral) on ``pack_root`` as ``run_snapshot`` does for a queued Run."""

    run_dir.mkdir(parents=True)
    project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
    project = methodology.with_profile(dict(project, id="d1"), REFERENCE_PROFILE_ID)
    create_run_input_snapshot(
        run_dir=run_dir, project=project, pack_root=pack_root,
        registry=workspace_registry(Path("missing-modules-directory")),
        selected=project["modules"], object_root=object_root,
    )
    return (run_dir / "input-snapshot" / "pack" / "manifest.json").read_bytes()


@contextlib.contextmanager
def value_101_pinned_by(shas):
    """The doctoral profile with the VALUE 101 entry pinned by ``shas`` only.

    Only the whitelist entries change (the profile record, and so the
    profile definition and every Study identity, stays the same).
    """

    catalogue = methodology.load_catalogue()
    profile = catalogue.profile(REFERENCE_PROFILE_ID)
    entries = tuple(
        dict(entry, manifest_sha256=list(shas)) if entry["id"] == "value-101-baseline-v1" else entry
        for entry in profile.supported_data_packs
    )
    pinned = dataclasses.replace(profile, supported_data_packs=entries)
    replaced = dataclasses.replace(catalogue, profiles={**catalogue.profiles, REFERENCE_PROFILE_ID: pinned})
    with patch.object(methodology, "load_catalogue", lambda: replaced):
        yield


class FrozenPackIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.run_dir = Path(cls.folder.name) / "runs" / "r"
        cls.frozen_bytes = freeze(cls.run_dir, PACK_ROOT, Path(cls.folder.name) / "objects")
        cls.source_bytes = (PACK_ROOT / "manifest.json").read_bytes()
        cls.source = json.loads(cls.source_bytes.decode("utf-8"))

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
        self.assertEqual(methodology.manifest_sha256_candidates(frozen, self.frozen_bytes), VALUE_101_SHAS)
        self.assertEqual(self.violations(frozen, self.frozen_bytes), [])
        record = frozen[pack_source_identity.SOURCE_FIELD]
        self.assertEqual(record["file_sha256"], VALUE_101_FILE_SHA)
        self.assertEqual(record["manifest_text"].encode("utf-8"), self.source_bytes)

    def test_preflight_and_the_worker_see_the_same_sha_candidates(self):
        """Preflight reads the source pack, the worker its frozen copy: one resolver, same candidates."""

        preflight = methodology.manifest_sha256_candidates(self.source, self.source_bytes)
        worker = methodology.manifest_sha256_candidates(self.frozen(), self.frozen_bytes)
        self.assertEqual(preflight, VALUE_101_SHAS)
        self.assertEqual(worker, preflight)
        # Without file bytes (a manifest from the API) the frozen copy still knows the source file sha.
        self.assertEqual(methodology.manifest_sha256_candidates(self.frozen()), VALUE_101_SHAS)

    def test_a_pin_by_either_sha_alone_admits_the_source_and_its_frozen_copy(self):
        for pin in (VALUE_101_FILE_SHA, VALUE_101_CANONICAL_SHA):
            with self.subTest(pin=pin[:8]), value_101_pinned_by([pin]):
                self.assertEqual(self.violations(self.source, self.source_bytes), [])
                self.assertEqual(self.violations(self.frozen(), self.frozen_bytes), [])
                self.assertEqual(self.violations(self.frozen()), [])
        with value_101_pinned_by(["0" * 64]):
            self.assertEqual([row["sub_reason"] for row in self.violations(self.frozen(), self.frozen_bytes)],
                             ["data_pack"])

    def test_a_frozen_copy_frozen_again_keeps_the_original_identity(self):
        """A run-input snapshot used as a pack root: preflight and the worker agree (review round 4)."""

        folder = Path(self.folder.name) / "refreeze"
        copy_root = folder / "data-packs" / "value-101-baseline-v1"
        shutil.copytree(self.run_dir / "input-snapshot" / "pack", copy_root)
        first = self.frozen()
        # Preflight on the hand-copied snapshot.
        self.assertEqual(self.violations(first, (copy_root / "manifest.json").read_bytes()), [])
        second_bytes = freeze(folder / "runs" / "r2", copy_root, folder / "objects")
        second = json.loads(second_bytes.decode("utf-8"))
        # The worker on the second snapshot.
        self.assertEqual(self.violations(second, second_bytes), [])
        self.assertEqual(second[pack_source_identity.SOURCE_FIELD], first[pack_source_identity.SOURCE_FIELD])
        self.assertEqual(pack_source_identity.source_manifest(second), self.source)
        for role, binding in second["bindings"].items():
            with self.subTest(role=role):
                self.assertEqual(binding["source_sha256"], self.source["bindings"][role]["sha256"])
                self.assertEqual(binding["transformation_id"], first["bindings"][role]["transformation_id"])
        self.assertEqual(methodology.manifest_sha256_candidates(second, second_bytes), VALUE_101_SHAS)

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
        # A self-consistent record of a different source manifest.
        manifest = self.frozen()
        other = copy.deepcopy(self.source)
        other["bindings"][role]["unit"] = "GWh"
        manifest[pack_source_identity.SOURCE_FIELD] = pack_source_identity.source_record(other)
        tampered.append(manifest)
        # The record text was edited; its shas were not.
        manifest = self.frozen()
        record = manifest[pack_source_identity.SOURCE_FIELD]
        record["manifest_text"] = record["manifest_text"].replace('"periods_per_year": 17520', '"periods_per_year": 8760')
        tampered.append(manifest)
        # The record text was edited and its file sha recomputed; the canonical sha was not.
        manifest = copy.deepcopy(manifest)
        record = manifest[pack_source_identity.SOURCE_FIELD]
        record["file_sha256"] = hashlib.sha256(record["manifest_text"].encode("utf-8")).hexdigest()
        tampered.append(manifest)
        # A record claiming the pinned file sha for other text.
        manifest = self.frozen()
        manifest[pack_source_identity.SOURCE_FIELD] = dict(pack_source_identity.source_record(other),
                                                           file_sha256=VALUE_101_FILE_SHA)
        tampered.append(manifest)
        # A first-format (v1) record: no source bytes, never verified.
        manifest = self.frozen()
        manifest[pack_source_identity.SOURCE_FIELD] = {
            "schema_version": "value.snapshot-source-manifest/v1",
            "canonical_sha256": VALUE_101_CANONICAL_SHA, "file_sha256": VALUE_101_FILE_SHA,
            "bindings": copy.deepcopy(self.source["bindings"]),
        }
        tampered.append(manifest)
        # A frozen value of a different JSON type that compares equal in Python (1 == True).
        manifest = self.frozen()
        manifest["annual_economics_eligible"] = 1
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


class RecoveredPackIdentityTests(unittest.TestCase):
    """A recovered base pack is identified by verified content identity with its source (Q3)."""

    @classmethod
    def setUpClass(cls):
        from backend.frozen_input_recovery import recovered_manifests
        from gridform_core.frozen_input_integrity import verify_frozen_input_integrity

        cls.folder = tempfile.TemporaryDirectory()
        run_dir = Path(cls.folder.name) / "runs" / "r"
        freeze(run_dir, PACK_ROOT, Path(cls.folder.name) / "objects")
        integrity = verify_frozen_input_integrity(run_dir / "input-snapshot")
        cls.recovered = recovered_manifests(
            integrity, source_run_id="r", base_pack_id="recovered-base-0123456789abcdef", network_pack_id=None,
            timestamp="2026-10-05T00:00:00+00:00", base_manifest_sha256="0" * 64,
            network_manifest_sha256=None)["base_manifest"]

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def manifest(self):
        return copy.deepcopy(self.recovered)

    def violations(self, manifest):
        return methodology.combination_violations(REFERENCE_PROFILE_ID, data_packs=[(manifest, None)])

    def test_the_recovered_pack_is_identified_as_its_source(self):
        manifest = self.manifest()
        self.assertEqual(manifest["id"], "recovered-base-0123456789abcdef")
        self.assertIs(manifest["scientific_baseline_eligible"], False)
        identity = pack_source_identity.resolve_pack_identity(manifest)
        self.assertEqual(identity.manifest, json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8")))
        self.assertEqual((identity.chain, identity.unverified), (("recovery",), None))
        self.assertEqual(set(identity.sha256_candidates), VALUE_101_SHAS)
        self.assertEqual(self.violations(manifest), [])
        # Names, timestamps, qualification and binding bookkeeping are not part of the identity.
        manifest.update(name="Renamed", updated_at="2027-01-01T00:00:00Z", scientific_validation_status="passed")
        role = sorted(manifest["bindings"])[0]
        manifest["bindings"][role]["imported_at"] = "2027-01-01T00:00:00Z"
        self.assertEqual(self.violations(manifest), [])

    def test_recovered_content_that_differs_from_the_source_is_not_identified(self):
        role = sorted(self.recovered["bindings"])[0]
        cases = {}
        manifest = self.manifest(); manifest["bindings"][role]["unit"] = "GWh"
        cases["binding metadata"] = manifest
        manifest = self.manifest(); manifest["bindings"][role]["sha256"] = "0" * 64
        cases["binding data"] = manifest
        manifest = self.manifest(); manifest["bindings"][role]["bytes"] += 1
        cases["binding size"] = manifest
        manifest = self.manifest(); manifest["bindings"].pop(role)
        cases["role coverage"] = manifest
        manifest = self.manifest(); manifest["periods_per_year"] = 8760
        cases["top-level field"] = manifest
        manifest = self.manifest(); manifest["description"] = "added"
        cases["added top-level field"] = manifest
        manifest = self.manifest(); manifest["data_pack_type"] = "network_overlay"
        cases["product type"] = manifest
        manifest = self.manifest(); manifest["frozen_recovery_origin"]["source_pack_id"] = "other-pack"
        cases["origin pack id"] = manifest
        manifest = self.manifest()
        record = manifest["frozen_recovery_origin"]["source_qualification"][pack_source_identity.SOURCE_FIELD]
        record["manifest_text"] = record["manifest_text"].replace('"periods_per_year": 17520', '"periods_per_year": 8760')
        cases["record text"] = manifest
        manifest = self.manifest()
        manifest["frozen_recovery_origin"]["source_qualification"].pop(pack_source_identity.SOURCE_FIELD)
        cases["no record"] = manifest
        for name, manifest in cases.items():
            with self.subTest(case=name):
                identity = pack_source_identity.resolve_pack_identity(manifest)
                self.assertEqual(identity.unverified, "recovery")
                rows = self.violations(manifest)
                self.assertEqual([row["sub_reason"] for row in rows], ["data_pack"])
                self.assertIn("recovered inputs carry no verifiable source manifest identity", rows[0]["message"])

    def test_the_frozen_copy_of_a_recovered_pack_is_identified_through_both_steps(self):
        folder = Path(self.folder.name) / "recovered-run"
        pack = folder / "data-packs" / self.recovered["id"]
        shutil.copytree(PACK_ROOT, pack, ignore=shutil.ignore_patterns("manifest.json"))
        (pack / "manifest.json").write_text(json.dumps(self.recovered, indent=2, sort_keys=True), encoding="utf-8")
        frozen_bytes = freeze(folder / "runs" / "r", pack, folder / "objects")
        frozen = json.loads(frozen_bytes.decode("utf-8"))
        identity = pack_source_identity.resolve_pack_identity(frozen, frozen_bytes)
        self.assertEqual(identity.chain, ("snapshot", "recovery"))
        self.assertEqual(set(identity.sha256_candidates), VALUE_101_SHAS)
        self.assertEqual(self.violations(frozen), [])


if __name__ == "__main__":
    unittest.main()
