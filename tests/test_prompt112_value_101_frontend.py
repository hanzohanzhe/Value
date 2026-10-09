from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

# P1 W3 (spec 5.1): app/page.tsx became the workbench state, the shell and one
# route per page; "the page" is now their union (the assertions are unchanged).
WORKBENCH_FILES = (
    "page.tsx", "HomeView.tsx", "features/shell/useWorkbenchState.ts", "features/shell/Workbench.tsx",
    "learn/LearnView.tsx", "studies/StudiesView.tsx", "data/DataView.tsx", "modules/ModulesView.tsx",
    "extensions/ExtensionsView.tsx", "runs/RunsView.tsx", "runs/[runId]/RunResultsView.tsx", "runs/[runId]/replay/ReplayView.tsx",
    "runs/[runId]/vre/VreView.tsx", "runs/[runId]/network/NetworkView.tsx", "runs/[runId]/systems/SystemsView.tsx",
    "inspect/InspectView.tsx", "compare/CompareView.tsx",
)


def workbench_source(app: Path) -> str:
    return "\n".join((app / name).read_text(encoding="utf-8") for name in WORKBENCH_FILES)


class Value101FrontendContractTests(unittest.TestCase):
    def test_active_frontend_uses_only_the_value_101_identity(self) -> None:
        page = workbench_source(APP)
        value_component = APP / "features" / "learn" / "Value101Learn.tsx"
        value_contract = APP / "features" / "learn" / "value101.ts"
        self.assertTrue(value_component.is_file())
        self.assertTrue(value_contract.is_file())
        self.assertFalse((APP / "features" / "learn" / "Castle101Learn.tsx").exists())
        self.assertFalse((APP / "features" / "learn" / "castle101.ts").exists())
        active = page + value_component.read_text(encoding="utf-8") + value_contract.read_text(encoding="utf-8")
        self.assertNotRegex(active, re.compile(r"castle", re.IGNORECASE))
        self.assertNotIn("/tutorials/castle-101", active)
        self.assertIn("/tutorials/value-101", page)
        self.assertIn('"value.101.progress.v1"', active)

    def test_home_exposes_four_distinct_first_use_actions(self) -> None:
        page = workbench_source(APP)
        for label in (
            "Start VALUE 101",
            "Build a Study",
            "Open a saved Study",
            "Add data or modules",
        ):
            self.assertIn(label, page)
        self.assertNotIn("Experimental AC feasibility", page)
        self.assertNotIn("value-reference-ac-feasibility", page)

    def test_course_opens_the_lesson_and_declares_all_recommended_steps(self) -> None:
        component = (APP / "features" / "learn" / "Value101Learn.tsx").read_text(encoding="utf-8")
        contract = (APP / "features" / "learn" / "value101.ts").read_text(encoding="utf-8")
        for step in (
            "building-blocks",
            "baseline",
            "data-variant",
            "module-variant",
            "compare",
            "build-from",
            "network",
        ):
            self.assertIn(f'"{step}"', contract)
        self.assertIn("setLessonOpen(true)", component)
        self.assertIn("How the five building blocks fit together", component)
        self.assertNotIn("disabled={completed", component)

    def test_module_chain_discloses_live_registry_identity_and_contract(self) -> None:
        card = (APP / "features" / "learn" / "ModuleChainCard.tsx").read_text(encoding="utf-8")
        component = (APP / "features" / "learn" / "Value101Learn.tsx").read_text(encoding="utf-8")
        for token in (
            "module.id",
            "module.version",
            "module.contract_version",
            "module.inputs",
            "module.outputs",
            "module.implementation",
        ):
            self.assertIn(token, card)
        self.assertIn("<details", card)
        self.assertIn("ModuleChainCard", component)
        self.assertIn("baselineModules", component)
        self.assertIn("length === 7", component)

    def test_study_creation_and_run_are_separate_and_build_from_is_unsaved(self) -> None:
        page = workbench_source(APP)
        component = (APP / "features" / "learn" / "Value101Learn.tsx").read_text(encoding="utf-8")
        self.assertIn("createValue101BaselineStudy", page)
        self.assertIn("run_started", page)
        self.assertIn("Create baseline Study", component)
        self.assertIn("Run baseline", component)
        self.assertIn("Build from VALUE 101", component)
        self.assertIn("loadValue101AsOrdinaryDraft", page)
        self.assertIn("unsaved", page)

    def test_incompatible_module_options_remain_visible_with_backend_reason(self) -> None:
        page = workbench_source(APP)
        self.assertIn("option.reason", page)
        self.assertIn("corrective", page.lower())
        self.assertIn("disabled={!option.compatible}", page)


if __name__ == "__main__":
    unittest.main()
