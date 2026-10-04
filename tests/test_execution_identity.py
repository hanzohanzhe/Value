import tempfile
import unittest
from pathlib import Path

from gridform_core.execution_identity import (
    EXECUTION_IDENTITY_SCHEMA,
    scheme_c_execution_identity,
    source_tree_identity,
)


class ExecutionIdentityTests(unittest.TestCase):
    def test_source_identity_is_stable_and_changes_with_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "model.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            first = source_tree_identity((root,), root=root)
            second = source_tree_identity((root,), root=root)
            source.write_text("VALUE = 2\n", encoding="utf-8")
            changed = source_tree_identity((root,), root=root)

        self.assertEqual(first, second)
        self.assertNotEqual(first["sha256"], changed["sha256"])
        self.assertEqual(first["files"][0]["path"], "model.py")

    def test_scheme_c_identity_covers_public_execution_sources(self):
        identity = scheme_c_execution_identity()
        paths = {row["path"] for row in identity["files"]}
        self.assertEqual(identity["schema_version"], EXECUTION_IDENTITY_SCHEMA)
        self.assertEqual(len(identity["sha256"]), 64)
        self.assertIn(
            "gridform_core/builtin/scheme_c_1000twh/compat/modular_case3.py", paths
        )
        self.assertIn(
            "gridform_core/builtin/scheme_c_1000twh/compat/storage_cost.py", paths
        )
        self.assertIn("gridform_core/market_ledger.py", paths)


if __name__ == "__main__":
    unittest.main()
