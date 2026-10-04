import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gridform_core.runtime_paths import APPLICATION_VERSION, user_data_root
from gridform_core.state_migrations import ensure_state_layout


class RuntimePathAndUpgradeTests(unittest.TestCase):
    def test_explicit_unicode_state_root_is_independent_of_current_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            configured = Path(temporary) / "VALUE 研究 data"
            other_cwd = Path(temporary) / "unrelated working directory"
            other_cwd.mkdir()
            with patch.dict(os.environ, {"VALUE_DATA_HOME": str(configured)}, clear=False):
                previous = Path.cwd()
                try:
                    os.chdir(other_cwd)
                    self.assertEqual(user_data_root(), configured.resolve())
                finally:
                    os.chdir(previous)

    def test_additive_upgrade_does_not_rewrite_immutable_run_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "state"
            first = ensure_state_layout(root)
            immutable = root / "runs" / "historical-run" / "status.json"
            immutable.parent.mkdir(parents=True)
            immutable.write_bytes(b'{"status":"completed","evidence":1}\n')
            before = hashlib.sha256(immutable.read_bytes()).hexdigest()
            second = ensure_state_layout(root)
            after = hashlib.sha256(immutable.read_bytes()).hexdigest()

            self.assertEqual(first, second)
            self.assertEqual(before, after)
            self.assertEqual(second["created_by_version"], APPLICATION_VERSION)
            self.assertEqual(
                second["migration_policy"],
                "additive_only_immutable_runs_not_rewritten",
            )
            self.assertEqual(
                json.loads((root / "state-metadata.json").read_text(encoding="utf-8"))["schema_version"],
                "value.local-state/v1",
            )


if __name__ == "__main__":
    unittest.main()
