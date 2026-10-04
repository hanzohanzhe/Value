from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure-value-101.mjs"


class Value101TimingLedgerTests(unittest.TestCase):
    def test_live_stopwatch_uses_the_ordinary_learner_route(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for label in (
            "Learn: VALUE 101",
            "Create baseline Study",
            "Run baseline",
            "Preview change",
            "Create Study",
            "Compare three controlled Runs",
            "Export completion JSON",
        ):
            self.assertIn(label, source)
        self.assertIn("value.101-timing/v1", source)
        self.assertIn("started-at-ms", source)
        self.assertNotIn("annual cost delta", source.lower())


if __name__ == "__main__":
    unittest.main()
