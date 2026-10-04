import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compare_release_roots", ROOT / "scripts" / "compare_release_roots.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CompareReleaseRootsTests(unittest.TestCase):
    def test_classifies_identical_changed_and_missing_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            primary = parent / "primary"
            candidate = parent / "candidate"
            for root in (primary, candidate):
                (root / "docs").mkdir(parents=True)
                (root / "source-release-manifest.json").write_text(
                    json.dumps(
                        {
                            "schema_version": "value.source-release-manifest/v1",
                            "include": ["docs", "source-release-manifest.json"],
                            "exclude_names": [],
                            "exclude_suffixes": [],
                        }
                    ),
                    encoding="utf-8",
                )
            (primary / "docs" / "same.md").write_text("same", encoding="utf-8")
            (candidate / "docs" / "same.md").write_text("same", encoding="utf-8")
            (primary / "docs" / "changed.md").write_text("new", encoding="utf-8")
            (candidate / "docs" / "changed.md").write_text("old", encoding="utf-8")
            (primary / "docs" / "primary.md").write_text("p", encoding="utf-8")
            (candidate / "docs" / "candidate.md").write_text("c", encoding="utf-8")

            report = MODULE.compare(primary, [("candidate", candidate)])
            comparison = report["comparisons"][0]
            self.assertEqual(comparison["different"], ["docs/changed.md"])
            self.assertEqual(comparison["primary_only"], ["docs/primary.md"])
            self.assertEqual(comparison["candidate_only"], ["docs/candidate.md"])
            self.assertGreaterEqual(comparison["identical_count"], 1)


if __name__ == "__main__":
    unittest.main()
