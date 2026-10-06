"""A16-4 (M-D2, spec 11.7): an in-place source edit of an installed module is accepted and recorded.

Preflight gives an amber warning naming the old and new source hashes; it
never blocks the run (the run records the new hash and Compare shows the
module method as changed).
"""

from __future__ import annotations

import hashlib
import json
import os
from unittest.mock import patch

from gridform_core.module_installation import installed_source_changes
from gridform_core.v2.module_manifest import workspace_registry
from tests.module_lifecycle_fixtures import write_external_module
from tests.test_module_quarantine_study import MODULES, PreflightQuarantineTests, _QuarantineHome

MODULE_ID, PACKAGE = "p02-source-edit", "p02_source_edit"


class InstalledSourceChangeTests(_QuarantineHome):
    project = PreflightQuarantineTests.project
    _run = PreflightQuarantineTests._run

    def setUp(self) -> None:
        super().setUp()
        record_path = write_external_module(self.modules, MODULE_ID, PACKAGE) / "installation.json"
        self.plugin = record_path.parent / "src" / PACKAGE / "plugin.py"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.installed = hashlib.sha256(self.plugin.read_bytes()).hexdigest()
        record["source_sha256"] = self.installed
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        self.project_with_module = {**self.project, "modules": {**MODULES, "storage_cost": MODULE_ID}}

    def _edit(self) -> str:
        self.plugin.write_text(self.plugin.read_text(encoding="utf-8") + "\n# edited in place\n", encoding="utf-8")
        return hashlib.sha256(self.plugin.read_bytes()).hexdigest()

    def test_unchanged_source_reports_nothing(self) -> None:
        self.assertEqual(installed_source_changes([MODULE_ID], modules_root=self.modules), [])

    def test_edited_source_reports_both_hashes(self) -> None:
        current = self._edit()
        self.assertEqual(installed_source_changes([MODULE_ID, "value-bid-at-cost-psm"], modules_root=self.modules), [
            {"module_id": MODULE_ID, "installed_sha256": self.installed, "current_sha256": current},
        ])
        # Only selected modules are checked.
        self.assertEqual(installed_source_changes(["value-bid-at-cost-psm"], modules_root=self.modules), [])

    def test_preflight_warns_amber_and_still_accepts(self) -> None:
        current = self._edit()
        with patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}):
            report = self._run(workspace_registry(self.modules), self.project_with_module)
        rows = [row for row in report["warnings"] if row["code"] == "GF_PREFLIGHT_MODULE_SOURCE_CHANGED"]
        self.assertEqual(len(rows), 1, report["warnings"])
        self.assertEqual(rows[0]["severity"], "warning")
        self.assertEqual(
            rows[0]["message"],
            f"Module {MODULE_ID} source changed since install ({self.installed[:8]}… → {current[:8]}…). "
            "Results will record the new source hash.",
        )
        self.assertNotIn("GF_PREFLIGHT_MODULE_SOURCE_CHANGED", {row["code"] for row in report["errors"]})
        self.assertEqual(report["checks"]["module_source_changes"][0]["current_sha256"], current)

    def test_preflight_without_an_edit_has_no_source_warning(self) -> None:
        with patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}):
            report = self._run(workspace_registry(self.modules), self.project_with_module)
        self.assertNotIn("GF_PREFLIGHT_MODULE_SOURCE_CHANGED", {row["code"] for row in report["warnings"]})
        self.assertEqual(report["checks"]["module_source_changes"], [])

