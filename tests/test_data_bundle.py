import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gridform_core.catalog import DATASET_SLOTS
from gridform_core.data_bundle import (
    BUNDLE_DESCRIPTOR,
    DataBundleError,
    build_data_bundle,
    install_data_bundle,
    validate_data_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"


class DataBundleTests(unittest.TestCase):
    def test_active_bundle_descriptor_uses_only_the_value_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "pack.zip"
            build_data_bundle(pack_root=SYNTHETIC, destination=bundle)
            with zipfile.ZipFile(bundle) as archive:
                self.assertIn("value-data-bundle.json", archive.namelist())
                self.assertNotIn("force-data-bundle.json", archive.namelist())
            self.assertEqual(BUNDLE_DESCRIPTOR, "value-data-bundle.json")

    def test_deterministic_synthetic_bundle_installs_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.zip"
            second = root / "second.zip"
            report_a = build_data_bundle(pack_root=SYNTHETIC, destination=first)
            report_b = build_data_bundle(pack_root=SYNTHETIC, destination=second)
            self.assertEqual(report_a["sha256"], report_b["sha256"])
            packs = root / "packs"
            installed = install_data_bundle(
                first,
                packs_root=packs,
                dataset_slots=DATASET_SLOTS,
                rights_acknowledged=True,
                minimum_free_space_bytes=0,
            )
            self.assertEqual(installed["validation"], {"passed": 25, "failed": 0, "total": 25})
            repeated = install_data_bundle(
                first,
                packs_root=packs,
                dataset_slots=DATASET_SLOTS,
                rights_acknowledged=True,
                minimum_free_space_bytes=0,
            )
            self.assertTrue(repeated["idempotent"])

    def test_rights_acknowledgement_is_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "pack.zip"
            build_data_bundle(pack_root=SYNTHETIC, destination=bundle)
            with self.assertRaisesRegex(DataBundleError, "Acknowledge"):
                install_data_bundle(
                    bundle,
                    packs_root=root / "packs",
                    dataset_slots=DATASET_SLOTS,
                    rights_acknowledged=False,
                    minimum_free_space_bytes=0,
                )

    def test_traversal_duplicate_and_executable_members_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for filename, members, code in (
                ("traversal.zip", [("../escape", b"x")], "GF_DATA_BUNDLE_PATH"),
                ("executable.zip", [("files/run.py", b"x")], "GF_DATA_BUNDLE_EXECUTABLE"),
                ("duplicate.zip", [("manifest.json", b"{}"), ("manifest.json", b"{}")], "GF_DATA_BUNDLE_DUPLICATE"),
            ):
                path = root / filename
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(BUNDLE_DESCRIPTOR, json.dumps({"schema_version": "value.data-bundle/v1"}))
                    for name, content in members:
                        archive.writestr(name, content)
                with self.assertRaises(DataBundleError) as captured:
                    validate_data_bundle(path)
                self.assertEqual(captured.exception.code, code)

    def test_inventory_hash_mutation_fails_during_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = root / "valid.zip"
            changed = root / "changed.zip"
            build_data_bundle(pack_root=SYNTHETIC, destination=valid)
            with zipfile.ZipFile(valid) as source, zipfile.ZipFile(changed, "w") as target:
                for info in source.infolist():
                    data = source.read(info.filename)
                    if info.filename.endswith("forecast.csv"):
                        # Preserve the declared byte count so extraction reaches
                        # the per-object digest check rather than failing the
                        # earlier inventory-size gate.
                        data = bytes([data[0] ^ 1]) + data[1:]
                    target.writestr(info, data)
            with self.assertRaises(DataBundleError) as captured:
                install_data_bundle(
                    changed,
                    packs_root=root / "packs",
                    dataset_slots=DATASET_SLOTS,
                    rights_acknowledged=True,
                    minimum_free_space_bytes=0,
                )
            self.assertEqual(captured.exception.code, "GF_DATA_BUNDLE_HASH")
            self.assertFalse((root / "packs" / "value-synthetic-contract-pack-v1").exists())

    def test_disk_headroom_failure_is_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "pack.zip"
            build_data_bundle(pack_root=SYNTHETIC, destination=bundle)
            with patch(
                "gridform_core.data_bundle.shutil.disk_usage",
                return_value=SimpleNamespace(free=0),
            ):
                with self.assertRaises(DataBundleError) as captured:
                    install_data_bundle(
                        bundle,
                        packs_root=root / "packs",
                        dataset_slots=DATASET_SLOTS,
                        rights_acknowledged=True,
                        minimum_free_space_bytes=1,
                    )
            self.assertEqual(captured.exception.code, "GF_DATA_BUNDLE_DISK_HEADROOM")
            self.assertFalse((root / "packs" / "value-synthetic-contract-pack-v1").exists())

    def test_manifest_revision_mismatch_fails_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = root / "valid.zip"
            changed = root / "changed.zip"
            build_data_bundle(pack_root=SYNTHETIC, destination=valid)
            with zipfile.ZipFile(valid) as source, zipfile.ZipFile(changed, "w") as target:
                for info in source.infolist():
                    data = source.read(info.filename)
                    if info.filename == BUNDLE_DESCRIPTOR:
                        descriptor = json.loads(data)
                        descriptor["pack_revision_sha256"] = "0" * 64
                        data = (json.dumps(descriptor, indent=2, sort_keys=True) + "\n").encode()
                    target.writestr(info, data)
            with self.assertRaises(DataBundleError) as captured:
                validate_data_bundle(changed)
            self.assertEqual(captured.exception.code, "GF_DATA_BUNDLE_REVISION")

    def test_different_bytes_cannot_replace_an_installed_pack_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            modified_pack = root / "modified-pack"
            shutil.copytree(SYNTHETIC, modified_pack)
            licence = modified_pack / "LICENSE"
            licence.write_text(licence.read_text(encoding="utf-8") + "\nChanged fixture.\n", encoding="utf-8")
            first = root / "first.zip"
            second = root / "second.zip"
            build_data_bundle(pack_root=SYNTHETIC, destination=first)
            build_data_bundle(pack_root=modified_pack, destination=second)
            packs = root / "packs"
            install_data_bundle(
                first,
                packs_root=packs,
                dataset_slots=DATASET_SLOTS,
                rights_acknowledged=True,
                minimum_free_space_bytes=0,
            )
            sentinel = (packs / "value-synthetic-contract-pack-v1" / "installation.json").read_bytes()
            with self.assertRaises(DataBundleError) as captured:
                install_data_bundle(
                    second,
                    packs_root=packs,
                    dataset_slots=DATASET_SLOTS,
                    rights_acknowledged=True,
                    minimum_free_space_bytes=0,
                )
            self.assertEqual(captured.exception.code, "GF_DATA_BUNDLE_COLLISION")
            self.assertEqual(
                sentinel,
                (packs / "value-synthetic-contract-pack-v1" / "installation.json").read_bytes(),
            )

    def test_link_archive_bomb_and_expansion_limit_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            link_bundle = root / "link.zip"
            with zipfile.ZipFile(link_bundle, "w") as archive:
                link = zipfile.ZipInfo("files/link")
                link.create_system = 3
                link.external_attr = 0o120777 << 16
                archive.writestr(link, b"target")
            with self.assertRaises(DataBundleError) as captured:
                validate_data_bundle(link_bundle)
            self.assertEqual(captured.exception.code, "GF_DATA_BUNDLE_LINK")

            bomb = root / "bomb.zip"
            with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("files/zeros.csv", b"0" * (2 * 1024 * 1024))
            with self.assertRaises(DataBundleError) as captured:
                validate_data_bundle(bomb)
            self.assertEqual(captured.exception.code, "GF_DATA_BUNDLE_RATIO")

            small = root / "small.zip"
            with zipfile.ZipFile(small, "w") as archive:
                archive.writestr("manifest.json", b"{}")
            with patch("gridform_core.data_bundle.MAX_UNCOMPRESSED_BYTES", 1):
                with self.assertRaises(DataBundleError) as captured:
                    validate_data_bundle(small)
            self.assertEqual(captured.exception.code, "GF_DATA_BUNDLE_EXPANSION")


if __name__ == "__main__":
    unittest.main()
