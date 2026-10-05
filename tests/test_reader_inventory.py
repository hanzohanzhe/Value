"""P0-5a S1: every implicit column-guessing reader site is inventoried (frozen_reader_inventory_v1.json)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "gridform_core" / "data" / "validation" / "frozen_reader_inventory_v1.json"
SCANNED = ("gridform_core", "backend", "scripts")


def _sites(patterns: list[str]) -> set[str]:
    found = set()
    for top in SCANNED:
        for path in (ROOT / top).rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if "/compat/" in relative or "__pycache__" in relative:
                continue  # compat/ is the byte-preserved Scheme C source
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern in text for pattern in patterns):
                found.add(relative)
    return found


class ReaderInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

    def test_every_guessing_site_is_listed_and_no_entry_is_stale(self) -> None:
        listed = {row["path"] for row in self.inventory["sites"]}
        found = _sites(self.inventory["patterns"])
        self.assertEqual(sorted(found - listed), [], "unlisted implicit column readers")
        self.assertEqual(sorted(listed - found), [], "stale inventory entries")
        self.assertTrue(all(row["reason"] for row in self.inventory["sites"]))

    def test_production_readers_go_through_the_shared_reader(self) -> None:
        canonical = (ROOT / "gridform_core" / "canonical_psm_data.py").read_text(encoding="utf-8")
        self.assertIn("read_role", canonical)
        self.assertIn("read_boundary", canonical)
        kernel = (ROOT / "gridform_core/builtin/scheme_c_1000twh/runtime_compat/modular_simulation_model.py").read_text(
            encoding="utf-8")
        self.assertNotIn("IterLimit_new(transfer_constraint", kernel)
        self.assertIn("active_boundary", kernel)

    def test_dead_vre_expansion_module_is_removed(self) -> None:
        self.assertFalse((ROOT / "gridform_core/builtin/scheme_c_1000twh/vre_expansion.py").exists())


if __name__ == "__main__":
    unittest.main()
