"""FX7 (decisions A16-6, A16-7): solar model approval status; GBP1 public2 local registration.

A16-6: the author approved the A13 plane-of-array model choices directly; the
parameter table and the reference statistics say so, with the values unchanged.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOSS_TABLE = ROOT / "gridform_core" / "data" / "weather" / "value_uk_vre_loss_factors_v1.json"
REFERENCE_STATISTICS = ROOT / "docs" / "dev" / "REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md"


class SolarModelApprovalTests(unittest.TestCase):
    def test_parameter_table_marks_the_a13_model_choices_approved(self):
        table = json.loads(LOSS_TABLE.read_text(encoding="utf-8"))
        solar = table["solar_plane_of_array"]
        self.assertTrue(solar["status"].startswith("AUTHOR APPROVED (DECISIONS A16-6"))
        self.assertNotIn("PENDING", solar["status"])
        self.assertIn("A16-6", table["status"])
        self.assertNotIn("PENDING", table["status"])
        # The approval changes no value (A16-6: "作者直接认可").
        self.assertEqual((solar["tilt_rule"], solar["decomposition"], solar["transposition"]),
                         ("jacobson-jadhav-2018", "erbs-1982", "hay-davies-1980"))
        self.assertEqual((solar["albedo"], solar["solar_constant_w_m2"], solar["max_zenith_deg"]), (0.2, 1361.0, 87.0))

    def test_reference_statistics_section_3_5_is_approved(self):
        text = REFERENCE_STATISTICS.read_text(encoding="utf-8")
        heading = next(line for line in text.splitlines() if line.startswith("### 3.5 "))
        self.assertIn("作者已认可，A16-6", heading)
        self.assertIn("已由作者直接认可（DECISIONS A16-6", text.splitlines()[2])

    def test_catalogue_descriptions_match_the_code(self):
        from gridform_core.methodology import load_catalogue

        catalogue = load_catalogue()
        solar = catalogue.corrections["p05.solar-plane-of-array"].description
        self.assertIn("Jacobson & Jadhav (2018) optimal tilt", solar)
        self.assertNotIn("tilted at the site latitude", solar)
        self.assertNotIn("PENDING", catalogue.corrections["p05.vre-loss-factors"].description)


if __name__ == "__main__":
    unittest.main()
