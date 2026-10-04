from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "docs" / "tutorial"


class Value101TutorialDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = {
            "english": TUTORIAL / "VALUE_101.md",
            "chinese": TUTORIAL / "VALUE_101_ZH.md",
            "quick": TUTORIAL / "VALUE_101_QUICK_CARD.md",
            "demo": TUTORIAL / "JOHN_PILOT_RUNBOOK.md",
        }

    def test_required_sources_exist_and_use_the_release_local_url(self) -> None:
        for label, path in self.paths.items():
            with self.subTest(document=label):
                self.assertTrue(path.is_file(), path)
                text = path.read_text("utf-8")
                self.assertIn("http://127.0.0.1:8800", text)
                self.assertNotIn("127.0.0.1:3000", text)
                self.assertNotIn("localhost:3000", text)

    def test_manuals_match_the_real_value_101_contract_and_labels(self) -> None:
        required = {
            "value-bid-at-cost-psm",
            "dynamic-annual-storage-cost",
            "agent-investment",
            "planning-pipeline",
            "vre-expansion-cap",
            "value-storage-expansion-policy",
            "value-annual-state-transition",
            "value-101-baseline-v1",
            "value-101-windy-v1",
            "value-101-high-demand-v1",
            "Create baseline Study",
            "Run baseline",
            "Build from VALUE 101",
            "Network constraints & redispatch",
        }
        for path in (self.paths["english"], self.paths["chinese"]):
            text = path.read_text("utf-8")
            for value in required:
                self.assertIn(value, text, f"{value!r} missing from {path.name}")
            self.assertRegex(text, r"48[^\n]{0,80}half-hour|48[^\n]{0,80}半小时")
            self.assertIn("2025", text)
            self.assertIn("2026", text)
            self.assertRegex(text.lower(), r"not annual|不能.*年度|不是.*年度")

    def test_core_concepts_precede_extension_work(self) -> None:
        english = self.paths["english"].read_text("utf-8")
        positions = [english.index(term) for term in ("Data", "Study", "Modules", "Run", "Results")]
        extension = english.index("Build from VALUE 101")
        self.assertLess(max(positions), extension)

    def test_quick_card_is_short_and_demo_runbook_has_recovery(self) -> None:
        quick = self.paths["quick"].read_text("utf-8")
        demo = self.paths["demo"].read_text("utf-8")
        self.assertLess(len(re.findall(r"\b[\w'-]+\b", quick)), 700)
        self.assertIn("VALUE 101", quick)
        self.assertIn("Stop VALUE 101", demo)
        self.assertIn("offline", demo.lower())
        self.assertIn("missing pack", demo.lower())
        self.assertIn("occupied port", demo.lower())

    def test_humanized_final_sources_avoid_common_ai_tells(self) -> None:
        forbidden = (
            "As an AI",
            "delve into",
            "seamlessly",
            "In conclusion",
            "It is important to note",
            "—",
            "–",
        )
        for label, path in self.paths.items():
            text = path.read_text("utf-8")
            for phrase in forbidden:
                self.assertNotIn(phrase, text, f"{phrase!r} found in {label}")


if __name__ == "__main__":
    unittest.main()
