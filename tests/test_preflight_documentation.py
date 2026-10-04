from __future__ import annotations

import unittest
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "docs" / "tutorial"


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


class PreflightDocumentationTests(unittest.TestCase):
    def test_maintained_guides_explain_single_node_and_zonal_resolution(self) -> None:
        """Catches a guide that leaves 'resolved during preflight' undefined."""

        english = (TUTORIAL / "VALUE_101.md").read_text(encoding="utf-8")
        chinese = (TUTORIAL / "VALUE_101_ZH.md").read_text(encoding="utf-8")
        supplement = (TUTORIAL / "VALUE_101_TO_VALUE_UK.md").read_text(
            encoding="utf-8"
        )
        for source in (english, supplement):
            for phrase in (
                "What Check readiness resolves",
                "resolved during preflight",
                "input snapshot",
                "Saved Study → declared Data Pack → validate and freeze",
                "resolve compatible Network Pack",
                "must not silently",
            ):
                self.assertIn(phrase, source)
        for phrase in (
            "Check readiness 会解析什么",
            "resolved during preflight",
            "input snapshot",
            "Saved Study → declared Data Pack → validate and freeze",
            "resolve compatible Network Pack",
            "不得静默",
        ):
            self.assertIn(phrase, chinese)

    def test_generated_pdfs_contain_the_preflight_contract(self) -> None:
        """Catches regenerated PDFs that omit the maintained preflight section."""

        for filename in (
            "VALUE_101_guide.pdf",
            "VALUE_101_TO_VALUE_UK_guide.pdf",
        ):
            text = pdf_text(ROOT / "output" / "pdf" / filename).lower()
            for phrase in (
                "resolved during preflight",
                "single node",
                "network pack",
                "input snapshot",
            ):
                self.assertIn(phrase, text, filename)

    def test_generated_pdfs_render_preflight_markup_instead_of_leaking_markdown(self) -> None:
        """Catches raw fences, emphasis markers and missing-glyph boxes in the PDFs."""

        for filename in (
            "VALUE_101_guide.pdf",
            "VALUE_101_TO_VALUE_UK_guide.pdf",
        ):
            text = pdf_text(ROOT / "output" / "pdf" / filename)
            self.assertNotIn("```", text, filename)
            self.assertNotIn("**resolved during preflight**", text, filename)
            self.assertNotIn("\x00", text, filename)
            self.assertNotIn("\ufffd", text, filename)
            self.assertIn(
                "Saved Study -> declared Data Pack -> validate and freeze",
                " ".join(text.split()),
                filename,
            )


if __name__ == "__main__":
    unittest.main()
