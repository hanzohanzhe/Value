"""R4-4 (DECISIONS A27): edit-module and add-feature defects of the final four-role report.

Each class names the defect ids it covers (M-* edit a module, F-* add a feature).
"""

from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gridform_core import revision_migration
from gridform_core.methodology import PROFILE_PARAMETER
from gridform_core.preflight import run_preflight
from gridform_core.project_revision import save_project_revision
from gridform_core.v2.module_manifest import workspace_registry

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data-packs" / "value-101-baseline-v1"
PSM = "value-bid-at-cost-psm"
PINNED_DISK = SimpleNamespace(total=4 * 1024**4, used=1024**4, free=3 * 1024**4)


class VersionedRegistry:
    """The built-in registry with some module versions moved (a simulated upgrade)."""

    def __init__(self, base, versions):
        self.base, self.versions = base, dict(versions)

    def manifest(self, module_id, expected_slot=None):
        manifest = self.base.manifest(module_id, expected_slot=expected_slot)
        if module_id in self.versions:
            return dataclasses.replace(manifest, version=self.versions[module_id])
        return manifest

    def __getattr__(self, name):
        return getattr(self.base, name)


def _versions() -> tuple[str, str]:
    from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM

    major, minor, _patch = (int(part) for part in SchemeCNativePSM.version.split("."))
    return SchemeCNativePSM.version, f"{major}.{minor + 1}.0"


SHIPPED, UPGRADED = _versions()


def _ledger(opt_in: bool) -> dict:
    return {PSM: {"baseline_version": SHIPPED, "current_version": UPGRADED, "bumps": [{
        "from": SHIPPED, "to": UPGRADED, "package": "P0-x", "correction_ids": ["p06.storage-net-per-period"],
        "reason": "test", "requires_user_opt_in": opt_in,
    }]}}


class SavedStudyCase(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.study = Path(self.folder.name) / "projects" / "study"
        self.registry = workspace_registry(Path("missing-modules-directory"))
        self.manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        project["id"] = "study"
        self.saved = save_project_revision(self.study, project, self.registry, self.manifest)

    def project(self) -> dict:
        return json.loads((self.study / "project.json").read_text(encoding="utf-8"))

    def preflight(self, registry=None, project=None) -> dict:
        with tempfile.TemporaryDirectory() as folder, patch(
            "gridform_core.preflight.shutil.disk_usage", return_value=PINNED_DISK,
        ):
            return run_preflight(
                project or self.project(), mode="smoke", pack_root=PACK_ROOT, pack_manifest=self.manifest,
                dataset_slots=[], registry=registry or self.registry, output_root=Path(folder),
            )


class PreflightIdentityTests(SavedStudyCase):
    """M-中2 / F-中1: a code-only re-identification still yields a readiness report."""

    def test_report_names_the_saved_revision_it_evaluated(self) -> None:
        upgraded = VersionedRegistry(self.registry, {PSM: UPGRADED})
        with patch.object(revision_migration, "_ledger", return_value=_ledger(opt_in=False)):
            report = self.preflight(upgraded)
        check = report["checks"]["project_revision"]
        self.assertTrue(check["classification"]["automatic"])
        self.assertNotEqual(check["calculated_sha256"], self.saved["revision_sha256"])
        # The report is evidence for the saved revision the UI holds ...
        self.assertEqual(report["project_revision_sha256"], self.saved["revision_sha256"])
        # ... and still says which hash the run will append.
        self.assertEqual(report["calculated_project_revision_sha256"], check["calculated_sha256"])
        self.assertIn("GF_PREFLIGHT_REVISION_REIDENTIFY", {row["code"] for row in report["warnings"]})

    def test_unchanged_and_unsaved_reports_keep_their_identity(self) -> None:
        report = self.preflight()
        self.assertEqual(report["project_revision_sha256"], self.saved["revision_sha256"])
        self.assertEqual(report["calculated_project_revision_sha256"], self.saved["revision_sha256"])
        unsaved = {key: value for key, value in self.project().items() if key != "revision_sha256"}
        report = self.preflight(project=unsaved)
        self.assertEqual(report["project_revision_sha256"], report["calculated_project_revision_sha256"])
        self.assertTrue(report["project_revision_sha256"])


if __name__ == "__main__":
    unittest.main()
