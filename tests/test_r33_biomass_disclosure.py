"""R3-3 (DECISIONS A24-2): disclosure that biomass is rarely dispatched.

VALUE has no CfD/ROC support revenue for biomass (P4-07, next round), so
biomass offers at its full fuel and carbon cost and is rarely dispatched in
both profiles.  A24-2 asks for a disclosure only: every Run whose frozen fleet
has a biomass asset carries a generic read-time advisory, whatever its
methodology profile; nothing in the model changes.
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from gridform_core import result_advisories
from gridform_core.market_replay import canonical_technology
from gridform_core.methodology import MethodologyCatalogError, load_catalogue
from gridform_core.result_advisories import evaluate_advisories, load_generic_advisories_from

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "runs" / "pre-fix-dynamic-full"
ADVISORIES = ROOT / "gridform_core" / "data" / "methodology" / "advisories.json"
ADVISORY_ID = "VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED"


def _fleet(*generators: str) -> dict:
    return {
        "batteries": {"1c_battery": {"name": "1c_battery"}},
        "connections": {"Interconnect_France": {"name": "Interconnect_France"}},
        "electrolyzer": {},
        "generators": {name: {"name": name} for name in generators},
        "locations": {},
    }


class BiomassAdvisoryTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        self.run_root = Path(folder) / "run"
        shutil.copytree(FIXTURE, self.run_root)
        self.status = json.loads((self.run_root / "status.json").read_text(encoding="utf-8"))
        result_advisories._ASSET_CACHE.clear()
        self.addCleanup(result_advisories._ASSET_CACHE.clear)

    def _freeze_fleet(self, fleet: dict) -> None:
        pack = self.run_root / "input-snapshot" / "pack"
        (pack / "files" / "fleet__generators").mkdir(parents=True, exist_ok=True)
        (pack / "files" / "fleet__generators" / "fleet.json").write_text(json.dumps(fleet), encoding="utf-8")
        manifest = {"id": "value-uk-open-data-pack-public2",
                    "bindings": {"fleet.generators": {"uri": "files/fleet__generators/fleet.json"}}}
        (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        result_advisories._ASSET_CACHE.clear()

    def _advisory(self, status: dict | None = None) -> dict | None:
        rows = evaluate_advisories(self.status if status is None else status, self.run_root)
        return next((row for row in rows if row["id"] == ADVISORY_ID), None)

    def test_catalogue_entry(self) -> None:
        row = next(item for item in result_advisories.generic_advisories() if item["id"] == ADVISORY_ID)
        self.assertEqual(row["applies_to"], "fleet_assets")
        self.assertEqual(row["applies_when"], {"assets_any": ["biomass_and_waste"]})
        self.assertEqual(row["severity"], "medium")
        self.assertEqual(row["findings"], ["A24-2", "P4-07"])
        for phrase in ("CfD or ROC support revenue", "85 GBP/MWh", "rarely dispatched", "P4-07"):
            self.assertIn(phrase, row["summary"])
        # The asset key is the class the fleet evidence produces for the GB packs' row.
        self.assertEqual(canonical_technology("bio_and_waste"), "biomass_and_waste")
        # A disclosure, not a correction: the method identity does not see it.
        self.assertNotIn(ADVISORY_ID, load_catalogue().corrections)

    def test_run_with_biomass_carries_it_in_either_profile(self) -> None:
        self._freeze_fleet(_fleet("CCGT", "OCGT", "bio_and_waste", "Nuclear", "offshore1"))
        presented = self._advisory()
        self.assertIsNotNone(presented)
        self.assertEqual(presented["source"], "generic")
        self.assertIsNone(presented["correction_id"])
        self.assertEqual(presented["findings"], ["A24-2", "P4-07"])
        self.assertEqual(presented["title"], "Biomass without support revenue")
        every_correction = sorted(load_catalogue().corrections)
        for profile in ("value-corrected", "doctoral-lineage-0.6.0a2"):
            with self.subTest(profile=profile):
                status = copy.deepcopy(self.status)
                status["methodology"] = {"profile_id": profile, "applied_correction_ids": every_correction}
                rows = evaluate_advisories(status, self.run_root)
                # Every correction applied: no correction advisory is left, the disclosure stays.
                self.assertFalse([row for row in rows if row["source"] == "correction"])
                self.assertIn(ADVISORY_ID, {row["id"] for row in rows})

    def test_run_without_biomass_does_not(self) -> None:
        self._freeze_fleet(_fleet("CCGT", "offshore1", "onshore_London", "solar_London"))
        self.assertIsNone(self._advisory())

    def test_unreadable_fleet_keeps_it(self) -> None:
        self.assertIsNone(result_advisories.run_asset_classes(self.run_root))
        self.assertIsNotNone(self._advisory())

    def test_loader_rules_for_fleet_assets(self) -> None:
        payload = json.loads(ADVISORIES.read_text(encoding="utf-8"))
        broken_rows = []
        missing = copy.deepcopy(payload)
        del next(row for row in missing["advisories"] if row["id"] == ADVISORY_ID)["applies_when"]
        broken_rows.append(missing)
        unknown_key = copy.deepcopy(payload)
        next(row for row in unknown_key["advisories"] if row["id"] == ADVISORY_ID)["applies_when"] = {
            "modules_any": ["value-bid-at-cost-psm"]}
        broken_rows.append(unknown_key)
        empty = copy.deepcopy(payload)
        next(row for row in empty["advisories"] if row["id"] == ADVISORY_ID)["applies_when"] = {"assets_any": []}
        broken_rows.append(empty)
        stray = copy.deepcopy(payload)
        stray["advisories"][0]["applies_when"] = {"assets_any": ["nuclear"]}
        broken_rows.append(stray)
        bad_findings = copy.deepcopy(payload)
        next(row for row in bad_findings["advisories"] if row["id"] == ADVISORY_ID)["findings"] = "A24-2"
        broken_rows.append(bad_findings)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "advisories.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIn(ADVISORY_ID, {row["id"] for row in load_generic_advisories_from(path)})
            for index, broken in enumerate(broken_rows):
                with self.subTest(case=index):
                    path.write_text(json.dumps(broken), encoding="utf-8")
                    with self.assertRaises(MethodologyCatalogError):
                        load_generic_advisories_from(path)

    def test_documents_name_the_disclosure(self) -> None:
        card = (ROOT / "docs" / "SCHEME_C_MODEL_CARD.md").read_text(encoding="utf-8")
        draft = (ROOT / "docs" / "methodology" / "drafts" / "0.4" / "r33_biomass_support_disclosure.md").read_text(
            encoding="utf-8")
        for text in (card, draft):
            self.assertIn(ADVISORY_ID, text)
            self.assertIn("P4-07", text)


if __name__ == "__main__":
    unittest.main()
