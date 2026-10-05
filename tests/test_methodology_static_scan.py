"""Two-way code/catalogue scan of the methodology profiles (X0 S8)."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_methodology_catalog", ROOT / "scripts" / "check_methodology_catalog.py")
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)  # type: ignore[union-attr]


class StaticScanTests(unittest.TestCase):
    def test_repository_passes(self):
        self.assertEqual(scanner.check(ROOT), [])

    def _tree(self) -> Path:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        shutil.copytree(ROOT / "gridform_core" / "data" / "methodology", folder / "gridform_core" / "data" / "methodology")
        (folder / "gridform_core" / "rules.py").write_text("", encoding="utf-8")
        return folder

    def test_unknown_correction_id_in_code_is_reported(self):
        tree = self._tree()
        (tree / "gridform_core" / "rules.py").write_text(
            "def rule(m):\n    return m.enabled('p06.does-not-exist')\n", encoding="utf-8")
        errors = scanner.check(tree)
        self.assertTrue(any("p06.does-not-exist" in line and "rules.py:2" in line for line in errors), errors)

    def test_profile_id_comparison_is_reported(self):
        tree = self._tree()
        (tree / "backend").mkdir()
        (tree / "backend" / "view.py").write_text(
            "def label(run):\n    return run['profile'] == \"doctoral-lineage-0.6.0a2\"\n", encoding="utf-8")
        errors = scanner.check(tree)
        self.assertTrue(any(line.startswith("backend/view.py:2: profile id literal") for line in errors), errors)

    def test_unconsulted_gated_correction_is_reported(self):
        tree = self._tree()
        path = tree / "gridform_core" / "data" / "methodology" / "corrections" / "x0.json"
        text = path.read_text(encoding="utf-8")
        gated = ('{"id": "x0.toy-gate", "package": "x0", "findings": [], "track": "profile_gated", "scope": "kernel", '
                 '"affects": ["trajectory"], "applies_when": {}, "advisory": null, '
                 '"trigger_fixture": {"test": "tests/x.py::T.t"}, "introduced_in": "test"},')
        path.write_text(text.replace('"corrections": [', '"corrections": [' + gated, 1), encoding="utf-8")
        errors = scanner.check(tree)
        self.assertTrue(any("x0.toy-gate is never consulted" in line for line in errors), errors)
        (tree / "gridform_core" / "rules.py").write_text("def r(m):\n    return m.enabled('x0.toy-gate')\n", encoding="utf-8")
        self.assertEqual(scanner.check(tree), [])


if __name__ == "__main__":
    unittest.main()
