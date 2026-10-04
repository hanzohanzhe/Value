from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "docs" / "tutorial"
PDF = ROOT / "output" / "pdf" / "VALUE_101_guide.pdf"


class Value101PilotPublicationTests(unittest.TestCase):
    def test_value_application_and_value_101_tutorial_are_distinct(self) -> None:
        sources = (
            ROOT / "README.md",
            TUTORIAL / "VALUE_101.md",
            TUTORIAL / "VALUE_101_ZH.md",
            TUTORIAL / "VALUE_101_QUICK_CARD.md",
            TUTORIAL / "VALUE_101_TO_VALUE_UK.md",
            TUTORIAL / "JOHN_PILOT_RUNBOOK.md",
        )
        for path in sources:
            text = path.read_text("utf-8")
            self.assertIn("VALUE-Setup.exe", text)
            self.assertNotIn("VALUE-101-Setup.exe", text)
            self.assertNotIn("Stop VALUE 101", text)
            self.assertNotIn("Uninstall VALUE 101", text)
        english = (TUTORIAL / "VALUE_101.md").read_text("utf-8")
        self.assertIn("VALUE 101", english)
        self.assertIn("%LOCALAPPDATA%\\VALUE\\state", english)

    def test_public_documents_cover_the_complete_john_route(self) -> None:
        english = (TUTORIAL / "VALUE_101.md").read_text("utf-8")
        chinese = (TUTORIAL / "VALUE_101_ZH.md").read_text("utf-8")
        for term in (
            "Data Pack",
            "Study",
            "Modules",
            "Run",
            "Results",
            "25",
            "value-101-baseline-v1",
            "value-101-network-v1",
            "dynamic-annual-storage-cost",
            "Network & redispatch",
            "does not calculate voltage",
        ):
            self.assertIn(term, english)
        for term in (
            "Data Pack",
            "Study",
            "Modules",
            "Run",
            "Results",
            "25",
            "value-101-baseline-v1",
            "value-101-network-v1",
            "dynamic-annual-storage-cost",
            "Build from VALUE 101",
            "Network constraints & redispatch",
            "不是 DC 潮流",
        ):
            self.assertIn(term, chinese)

    def test_old_teaching_brand_and_public_ac_module_are_absent(self) -> None:
        roots = (
            ROOT / "README.md",
            ROOT / "app",
            ROOT / "backend" / "model_runner.py",
            ROOT / "packaging",
            ROOT / "scripts" / "start-local.ps1",
            ROOT / "docs" / "tutorial",
        )
        files: list[Path] = []
        for root in roots:
            if root.is_file():
                files.append(root)
            else:
                files.extend(path for path in root.rglob("*") if path.is_file())
        forbidden = (
            "Castle",
            "force-castle-101-v1",
            "VALUE-Castle-101",
            "value-reference-ac-feasibility",
            "domain.network.ac",
            "ac_feasibility",
            "domains/ac",
        )
        for path in files:
            if path.suffix.lower() not in {".md", ".json", ".py", ".ps1", ".cmd", ".cs", ".ts", ".tsx"}:
                continue
            text = path.read_text("utf-8", errors="ignore")
            for value in forbidden:
                self.assertNotIn(value, text, f"{value!r} remains in {path.relative_to(ROOT)}")

    def test_installer_declares_only_the_two_synthetic_teaching_packs(self) -> None:
        product = json.loads((ROOT / "packaging" / "windows-pilot" / "product.json").read_text("utf-8"))
        self.assertEqual(
            product["data_packs"],
            [
                "value-101-baseline-v1",
                "value-101-network-v1",
            ],
        )
        self.assertEqual(product["data_licence"], "CC0-1.0")
        self.assertNotIn("value-uk-1000twh-reproduction", json.dumps(product).lower())

    def test_pack_catalogue_does_not_add_the_legacy_placeholder_when_teaching_packs_exist(self) -> None:
        from backend import server

        with tempfile.TemporaryDirectory(prefix="value-101-pack-catalogue-") as temporary:
            packs_root = Path(temporary) / "data-packs"
            teaching_root = packs_root / "value-101-baseline-v1"
            teaching_root.mkdir(parents=True)
            (teaching_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "value.data-pack/v1",
                        "id": "value-101-baseline-v1",
                        "name": "VALUE 101 baseline",
                        "bindings": {},
                    }
                ),
                "utf-8",
            )

            with patch.object(server, "PACKS_ROOT", packs_root):
                packs = server.list_packs()

            self.assertEqual(
                [pack["id"] for pack in packs],
                ["value-101-baseline-v1"],
            )
            self.assertFalse((packs_root / "uk-scheme-c").exists())

    def test_pdf_has_embedded_fonts_headings_pages_and_links(self) -> None:
        self.assertTrue(PDF.is_file(), PDF)
        pdf_bytes = PDF.read_bytes()
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreaterEqual(len(re.findall(rb"/Type\s*/Page\b", pdf_bytes)), 4)
        self.assertIn(b"/FontFile2", pdf_bytes)
        self.assertIn(b"http://127.0.0.1:8800", pdf_bytes)
        english = (TUTORIAL / "VALUE_101.md").read_text("utf-8")
        for heading in (
            "VALUE 101",
            "The five objects",
            "What Check readiness resolves",
            "Optional network lesson",
        ):
            self.assertIn(heading, english)


if __name__ == "__main__":
    unittest.main()
