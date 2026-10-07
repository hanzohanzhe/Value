"""R3-N6 / O-3 (four-role R1 retest, DECISIONS A23): the Run record names the
corrections in force, including the uncatalogued universal accounting
corrections such as the VoLL change ``fx5.voll-17000``, without changing the
method identity of saved Studies and Runs."""

from __future__ import annotations

import unittest

from gridform_core.methodology import (
    REFERENCE_PROFILE_ID,
    UNIVERSAL_ACCOUNTING_CORRECTIONS,
    load_catalogue,
    methodology_record,
    resolve_methodology,
)


class MethodologyRecordTests(unittest.TestCase):
    def test_doctoral_run_record_names_the_voll_correction(self) -> None:
        record = methodology_record({"parameters": {"methodology.profile": REFERENCE_PROFILE_ID}})
        self.assertNotIn("fx5.voll-17000", record["applied_correction_ids"])
        self.assertIn("fx5.voll-17000", record["universal_accounting_correction_ids"])
        self.assertIn("fx5.voll-17000", record["correction_ids_in_force"])
        self.assertTrue(set(record["applied_correction_ids"]) <= set(record["correction_ids_in_force"]))

    def test_both_profiles_list_the_same_universal_accounting_corrections(self) -> None:
        ids = [item[0] for item in UNIVERSAL_ACCOUNTING_CORRECTIONS]
        self.assertEqual(ids, sorted(set(ids)))
        for profile_id in load_catalogue().profiles:
            with self.subTest(profile=profile_id):
                self.assertEqual(resolve_methodology(profile_id).to_dict()["universal_accounting_correction_ids"], ids)

    def test_listed_ids_stay_out_of_the_catalogue_and_the_method_identity(self) -> None:
        catalogue = load_catalogue()
        ids = {item[0] for item in UNIVERSAL_ACCOUNTING_CORRECTIONS}
        self.assertFalse(ids & set(catalogue.corrections))
        for profile_id in catalogue.profiles:
            resolved = resolve_methodology(profile_id)
            identity = resolved.identity()
            self.assertEqual(set(identity), {"profile_id", "profile_version", "profile_definition_sha256", "applied_corrections_sha256"})
            self.assertFalse(ids & set(resolved.applied_correction_ids))


if __name__ == "__main__":
    unittest.main()
