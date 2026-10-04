from __future__ import annotations

import unittest
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "methodology" / "VALUE_METHODOLOGY.md"
PDF = ROOT / "output" / "pdf" / "VALUE_Methodology.pdf"


class ValueMethodologyTests(unittest.TestCase):
    def test_source_and_pdf_describe_the_executable_value_method(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertTrue(PDF.is_file())
        source = SOURCE.read_text(encoding="utf-8")
        pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(PDF)).pages)
        required = (
            "bid at cost",
            "dynamic annual-average",
            "planning pipeline",
            "fixed zonal",
            "redispatch",
            "£17,000/MWh",
            "scenario_scaled_zonal_shares",
            "post-thesis",
            "not a security analysis",
            "state reads",
            "state writes",
            "Known limitations",
        )
        for phrase in required:
            self.assertIn(phrase.casefold(), source.casefold(), phrase)
            self.assertIn(phrase.casefold(), pdf_text.casefold(), phrase)
        self.assertNotIn("force", source.casefold())
        self.assertNotIn("force", pdf_text.casefold())


if __name__ == "__main__":
    unittest.main()
