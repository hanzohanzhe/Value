import json
import unittest
from pathlib import Path
from unittest import mock

from scripts.verify_public_uk_pack import verify


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-uk-open-data-pack-v1"


class PublicUkSourceBoundaryTests(unittest.TestCase):
    def test_source_only_release_scan_records_uninstalled_separate_asset(self):
        import scripts.release_scan as release_scan

        with mock.patch.object(
            release_scan,
            "SEPARATE_RELEASE_ASSET_ROOTS",
            {("data-packs", "deliberately-not-installed-uk-pack")},
        ):
            report = release_scan.scan()
        self.assertTrue(report["go"], report["issues"])
        self.assertEqual(len(report["separate_release_assets"]), 1)
        row = report["separate_release_assets"][0]
        self.assertFalse(row["installed"])
        self.assertEqual(row["status"], "NOT_INSTALLED_SEPARATE_ASSET")
        self.assertIsNone(row["verification"])


@unittest.skipUnless((PACK / "manifest.json").is_file(), "local UK public pack not assembled")
class PublicUkDistributionTests(unittest.TestCase):
    def test_large_public_pack_is_a_verified_separate_release_asset(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/data-packs/value-uk-open-data-pack-v1/", gitignore)

        from scripts.release_scan import scan

        report = scan()
        rows = report["separate_release_assets"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["repository_treatment"],
            "gitignored_separate_release_asset",
        )
        self.assertEqual(rows[0]["verification"]["decision"], "GO")

    def test_every_role_has_an_explicit_go_and_attribution(self):
        manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["bindings"]), 25)
        for role, binding in manifest["bindings"].items():
            with self.subTest(role=role):
                self.assertTrue(binding["licence"])
                self.assertTrue(binding["attribution"])
                self.assertTrue(str(binding["redistribution_class"]).startswith(
                    ("redistributable_", "owner_licensed_")
                ))

    def test_public_artifact_scan_has_no_forbidden_or_corrupt_objects(self):
        result = verify(PACK)
        self.assertEqual(result["decision"], "GO")
        self.assertEqual(result["forbidden_or_corrupt_objects"], 0)

    def test_policy_workbook_keeps_scientific_caveat(self):
        provenance = json.loads((
            ROOT / "publication" / "value-uk-open-data-pack" / "policy-provenance.json"
        ).read_text(encoding="utf-8"))
        self.assertIn("approximate", provenance["scientific_status"])
        self.assertIn("must not relabel", provenance["release_rule"])


if __name__ == "__main__":
    unittest.main()
