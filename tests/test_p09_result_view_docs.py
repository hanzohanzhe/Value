"""P0-9 S12: the result-view documentation names fields the read models really send."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELD_MAP = ROOT / "docs" / "frontend" / "EXPANDED_FRONTEND_FIELD_MAP.md"
FIXTURES = ROOT / "tests" / "fixtures" / "ui-contract"
SOURCES = (
    "backend/model_runner.py", "backend/server.py", "backend/data_mapping.py", "backend/result_queries.py",
    "gridform_core/market_replay.py", "gridform_core/scientific_validation.py", "gridform_core/result_advisories.py",
    "gridform_core/zonal_results.py", "gridform_core/result_coverage.py",
)


class ResultViewDocsTests(unittest.TestCase):
    def section(self) -> str:
        text = FIELD_MAP.read_text(encoding="utf-8")
        start = text.index("## Result views: displayed value -> API field")
        return text[start:]

    def test_every_documented_field_is_sent_by_a_read_model(self) -> None:
        section = self.section()
        fields = set()
        for row in section.splitlines():
            cells = row.split("|")
            if len(cells) > 4 and not row.startswith("| ---") and not row.startswith("| View"):
                fields.update(re.findall(r"`([a-z][a-z0-9_]+)`", cells[3]))
        self.assertGreater(len(fields), 30)
        corpus = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in SOURCES)
        corpus += "\n".join(path.read_text(encoding="utf-8") for path in FIXTURES.glob("*.json"))
        missing = sorted(field for field in fields if f'"{field}"' not in corpus and f"'{field}'" not in corpus)
        self.assertEqual(missing, [], "documented result-view fields that no read model sends")

    def test_fixtures_carry_the_corrected_vre_basis_the_docs_describe(self) -> None:
        summary = json.loads((FIXTURES / "value-101-day.vre-summary.json").read_text(encoding="utf-8"))["payload"]
        self.assertEqual(summary["curtailment_semantics"], "vre_available_minus_gross_output")
        self.assertEqual(summary["years"][0]["event_basis"], "corrected_unused_vre")
        self.assertIn("corrected_unused_vre", self.section())
        guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
        guide_zh = (ROOT / "docs" / "USER_GUIDE_ZH.md").read_text(encoding="utf-8")
        for text in (guide, guide_zh):
            for phrase in ("corrected_unused_vre", "stress (supply < demand)", "Annual results not published", "Stopped · n%"):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
