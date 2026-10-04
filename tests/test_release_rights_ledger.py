import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_release_rights", ROOT / "scripts" / "build_release_rights.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReleaseRightsLedgerTests(unittest.TestCase):
    @unittest.skipUnless(
        MODULE.UK_RIGHTS.is_file(),
        "separate UK benchmark asset not installed",
    )
    def test_generated_authority_matches_every_shipped_object(self):
        stored = json.loads(
            (ROOT / "publication" / "release-rights-ledger.json").read_text(
                encoding="utf-8"
            )
        )
        generated = MODULE.build_ledger()
        self.assertEqual(stored, generated)
        self.assertEqual(MODULE.validate_ledger(stored), [])

    def test_checked_in_authority_is_valid_without_separate_uk_payload(self):
        stored = json.loads(
            (ROOT / "publication" / "release-rights-ledger.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            MODULE.validate_ledger(stored, require_uk_payload=False), []
        )

    def test_all_projected_rights_files_name_the_authority(self):
        inventory = json.loads(
            (ROOT / "publication" / "rights-inventory.json").read_text(encoding="utf-8")
        )
        source_plan = json.loads(
            (ROOT / "publication" / "uk-source-plan.json").read_text(encoding="utf-8")
        )
        bill = json.loads(
            (ROOT / "publication" / "value-uk-open-data-pack" / "bill-of-data.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(inventory["authority"], MODULE.AUTHORITY)
        self.assertEqual(source_plan["authority"], MODULE.AUTHORITY)
        self.assertEqual(bill["authority"], MODULE.AUTHORITY)
        self.assertTrue(all(row["included_in_public_archive"] for row in bill["objects"]))

    @unittest.skipUnless(
        MODULE.UK_RIGHTS.is_file(),
        "separate UK benchmark asset not installed",
    )
    def test_missing_rights_decision_fails_generation(self):
        original = MODULE._read_json

        def changed(path: Path):
            payload = original(path)
            if path == MODULE.UK_RIGHTS:
                payload["objects"][0]["decision"] = "UNKNOWN"
            return payload

        with mock.patch.object(MODULE, "_read_json", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "not cleared"):
                MODULE.build_ledger()


if __name__ == "__main__":
    unittest.main()
