"""F-D2 (DECISIONS A16-3, design spec 11.5): the one-day lesson runs the
market step only, so preflight blocks it when the Study selects extensions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.catalog import DATASET_SLOTS
from gridform_core.preflight import run_preflight
from gridform_core.run_policy import (
    PSM_ONLY_RUN_MODES,
    RUN_POLICIES,
    scope_extension_block_message,
    scope_runs_extensions,
)
from gridform_core.value_101 import value_101_study


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data-packs" / "value-101-baseline-v1"
EXTENSION = "value-toy-audit-extension"
CODE = "GF_PREFLIGHT_SCOPE_SKIPS_EXTENSIONS"


class ScopeExtensionPolicyTests(unittest.TestCase):
    def test_only_the_one_day_lesson_skips_extension_hooks(self) -> None:
        self.assertEqual(PSM_ONLY_RUN_MODES, frozenset({"value_101_day"}))
        self.assertTrue(PSM_ONLY_RUN_MODES <= set(RUN_POLICIES))
        self.assertEqual(
            {mode for mode in RUN_POLICIES if not scope_runs_extensions(mode)},
            {"value_101_day"},
        )
        # An unrecorded mode is never treated as a scope that skips hooks.
        self.assertTrue(scope_runs_extensions(None))

    def test_message_is_the_design_spec_text(self) -> None:
        self.assertEqual(
            scope_extension_block_message(["a-ext", "b-ext"]),
            "The one-day lesson runs the market step only, so the selected extension(s) "
            "a-ext, b-ext would not execute. Choose two-period or a longer scope, "
            "or deselect the extension(s).",
        )


class ScopeExtensionPreflightTests(unittest.TestCase):
    def preflight(self, mode: str, extensions: list[str]) -> dict:
        study = value_101_study()
        study["selected_extensions"] = list(extensions)
        manifest = json.loads((BASELINE / "manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="value-fd2-preflight-") as temporary:
            return run_preflight(
                study,
                mode=mode,
                pack_root=BASELINE,
                pack_manifest=manifest,
                dataset_slots=DATASET_SLOTS,
                output_root=Path(temporary),
            )

    def test_one_day_with_selected_extension_is_blocked_with_spec_message(self) -> None:
        report = self.preflight("value_101_day", [EXTENSION])
        self.assertFalse(report["accepted"])
        rows = [row for row in report["errors"] if row["code"] == CODE]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "error")
        self.assertEqual(rows[0]["message"], scope_extension_block_message([EXTENSION]))
        self.assertIn("deselect the extension(s)", rows[0]["corrective_action"])
        self.assertFalse(report["checks"]["extension_readiness"]["executes_in_scope"])

    def test_one_day_without_extensions_and_longer_scopes_are_not_blocked_by_it(self) -> None:
        plain = self.preflight("value_101_day", [])
        self.assertNotIn(CODE, {row["code"] for row in plain["errors"] + plain["warnings"]})
        two_period = self.preflight("smoke", [EXTENSION])
        self.assertNotIn(CODE, {row["code"] for row in two_period["errors"] + two_period["warnings"]})
        self.assertTrue(two_period["checks"]["extension_readiness"]["executes_in_scope"])


if __name__ == "__main__":
    unittest.main()
