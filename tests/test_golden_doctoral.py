"""The doctoral golden family: fast-tier cases reproduce their latest revision.

Each case runs in its own hermetic subprocess (scripts/golden/run_case.py) and
is compared per table x column with tests/golden/doctoral/<case>.json.  Identity
zone differences (code/module hashes, versions) are ignored here.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from gridform_validation import golden

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("golden_capture", ROOT / "scripts" / "golden" / "capture.py")
CAPTURE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CAPTURE)
FAMILY = "doctoral"


class GoldenDoctoralFamilyTests(unittest.TestCase):
    def test_fast_cases_match_latest_revision(self) -> None:
        cases = CAPTURE.load_cases()
        selected = [name for name in CAPTURE.select_cases(cases, "fast", None) if cases[name]["family"] == FAMILY]
        self.assertTrue(selected)
        digests = CAPTURE.run_cases(selected)
        mode = golden.default_mode()
        for case_id in selected:
            with self.subTest(case=case_id):
                record = json.loads(CAPTURE.golden_path(FAMILY, case_id).read_text(encoding="utf-8"))
                differences = [
                    row.to_dict()
                    for row in golden.compare_digests(
                        golden.latest_digest(record), digests[case_id], mode, golden.pinned_zones(record)
                    )
                    if row.zone in golden.GATED_ZONES
                ]
                self.assertEqual(differences, [], f"{FAMILY}/{case_id} differs from revision {record['revisions'][-1]['revision']}")

    def test_family_bookkeeping_is_valid(self) -> None:
        # Errors are attributed by case id, so numeric-report errors
        # ("tests/golden/reports/<case>-r<k>.json: ...") are enforced here too,
        # not only by the gate's golden_bookkeeping step.
        family_cases = {name for name, case in CAPTURE.load_cases().items() if case["family"] == FAMILY}

        def concerns_family(error: str) -> bool:
            return (
                error.startswith(f"{FAMILY}/")
                or f"/{FAMILY}/" in error
                or any(f"reports/{case_id}-r" in error for case_id in family_cases)
            )

        errors = [error for error in CAPTURE.validate_all() if concerns_family(error)]
        missing_long = [error for error in errors if "golden file missing" in error]
        self.assertEqual([error for error in errors if error not in missing_long], [])
        self.assertEqual(missing_long, [], "every case in tests/golden/cases.json needs revision 0")


if __name__ == "__main__":
    unittest.main()
