from __future__ import annotations

import json
import io
import tempfile
import unittest
import urllib.request
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from backend import server
from gridform_core.application import run_project_application
from gridform_core.catalog import DATASET_SLOTS
from gridform_core.preflight import run_preflight
from gridform_core.run_policy import resolve_run_policy
from gridform_core.scientific_validation import build_scientific_validation_report
from gridform_core.value_101 import value_101_descriptor, value_101_study
from scripts.install_synthetic_pack import install_builtin_packs
from tests.local_api_harness import start_local_api


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data-packs" / "value-101-baseline-v1"


class TutorialRuntimeTests(unittest.TestCase):
    def test_tutorial_policy_requires_exactly_two_48_period_years(self) -> None:
        policy = resolve_run_policy("tutorial")
        project = {"start_year": 2025, "end_year": 2026}
        self.assertEqual(policy.years(project), (2025, 2026))
        self.assertEqual(policy.to_dict(project)["total_periods"], 96)
        self.assertFalse(policy.annual_economics_candidate)
        self.assertFalse(policy.scientific_baseline_candidate)
        with self.assertRaisesRegex(ValueError, "exactly two"):
            policy.years({"start_year": 2025, "end_year": 2025})
        with self.assertRaisesRegex(ValueError, "exactly two"):
            policy.years({"start_year": 2025, "end_year": 2027})

    def test_canonical_study_uses_the_ordinary_bid_at_cost_chain(self) -> None:
        study = value_101_study()
        self.assertEqual(study["data_pack_id"], "value-101-baseline-v1")
        self.assertEqual((study["start_year"], study["end_year"]), (2025, 2026))
        self.assertEqual(study["modules"], {
            "psm": "value-bid-at-cost-psm",
            "storage_cost": "dynamic-annual-storage-cost",
            "investment": "agent-investment",
            "pipeline": "planning-pipeline",
            "vre_cap": "vre-expansion-cap",
            "storage_cap": "value-storage-expansion-policy",
            "transition": "value-annual-state-transition",
        })
        self.assertEqual(study["selected_extensions"], [])
        self.assertEqual(study["parameters"], {"planning.defer_spread_years": 0})
        self.assertEqual(study["runtime_options"]["runtime.market_trace_level"], "full")
        study["modules"]["psm"] = "changed"
        self.assertEqual(value_101_study()["modules"]["psm"], "value-bid-at-cost-psm")

    def test_short_tutorial_cannot_be_presented_as_annual_science(self) -> None:
        report = build_scientific_validation_report(
            mode="tutorial",
            periods_per_year=48,
            parity_report={"contract_parity_passed": True},
            mechanism_checks=[],
            retained_comparison_role="informational_scenario_difference",
        )
        self.assertFalse(report["annual_economics_eligible"])
        self.assertTrue(report["short_run_diagnostics_only"])
        self.assertEqual(report["scientific_validation_status"], "not_evaluated")

    def test_value_101_pack_refuses_annual_run_modes_and_bad_studies(self) -> None:
        study = value_101_study()
        manifest = json.loads((BASELINE / "manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="value-101-preflight-") as temporary:
            report = run_preflight(
                study,
                mode="full",
                pack_root=BASELINE,
                pack_manifest=manifest,
                dataset_slots=DATASET_SLOTS,
                output_root=Path(temporary),
            )
            self.assertFalse(report["accepted"])
            self.assertIn(
                "GF_PREFLIGHT_TEACHING_RUN_MODE",
                {row["code"] for row in report["errors"]},
            )
            with self.assertRaisesRegex(ValueError, "does not allow run mode"):
                run_project_application(
                    study,
                    run_id="value-101-forbidden-full",
                    pack_root=BASELINE,
                    output_dir=Path(temporary) / "forbidden",
                    mode="full",
                )

        with tempfile.TemporaryDirectory(prefix="value-101-study-validation-") as temporary:
            packs = Path(temporary) / "packs"
            with patch.object(server, "PACKS_ROOT", packs):
                missing = server.validate_project(study)
            self.assertFalse(missing["valid"])
            self.assertIn("GF_DATA_PACK_UNKNOWN", {row["code"] for row in missing["error_events"]})

            installed = packs / "value-101-baseline-v1"
            installed.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copytree(BASELINE, installed)
            incompatible = value_101_study()
            incompatible["modules"]["psm"] = "agent-investment"
            with patch.object(server, "PACKS_ROOT", packs):
                invalid = server.validate_project(incompatible)
            self.assertFalse(invalid["valid"])

    def test_tutorial_mode_runs_two_real_years_and_commissions_the_value_101_project(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-tutorial-run-") as temporary:
            output = Path(temporary) / "model-output"
            console = io.StringIO()
            with redirect_stdout(console), redirect_stderr(console):
                result = run_project_application(
                    value_101_study(),
                    run_id="value-101-tutorial-real-run",
                    pack_root=BASELINE,
                    output_dir=output,
                    mode="tutorial",
                )
            years = result["orchestrator_results"]
            validation = json.loads(
                (output / "validation" / "scientific-validation.json").read_text("utf-8")
            )
        self.assertEqual([row["year"] for row in years], [2025, 2026])
        self.assertTrue(all(len(row["market"]["period_summaries"]) == 48 for row in years))
        planning = years[1]["planning_advance"]
        planning_summary = {
            key: [
                {
                    "project_id": project.get("project_id"),
                    "status": project.get("status"),
                    "expected_completion_year": project.get("expected_completion_year"),
                }
                for project in planning.get(key, [])
            ]
            for key in ("active_projects", "commissioned_projects", "failed_projects")
        }
        self.assertTrue(any(
            project["project_id"].startswith("value101-solar-planning")
            for project in planning["commissioned_projects"]
        ), planning_summary)
        self.assertFalse(validation["annual_economics_eligible"])
        self.assertEqual(validation["scientific_validation_status"], "not_evaluated")

    def test_builtin_installer_is_idempotent_and_refuses_replacement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-installer-") as temporary:
            state = Path(temporary)
            first = install_builtin_packs(state)
            second = install_builtin_packs(state)
            self.assertEqual({row["pack_id"] for row in first}, {
                "value-synthetic-contract-pack-v1",
                "value-101-baseline-v1",
                "value-101-windy-v1",
                "value-101-high-demand-v1",
                "value-101-network-v1",
            })
            self.assertTrue(all(row["status"] == "installed" for row in first))
            self.assertTrue(all(row["status"] == "already_installed" for row in second))
            manifest = state / "data-packs" / "value-101-baseline-v1" / "manifest.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["name"] = "different"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            conflict = install_builtin_packs(state)
            baseline = next(row for row in conflict if row["pack_id"] == "value-101-baseline-v1")
            self.assertEqual(baseline["status"], "conflict_preserved")

    def test_read_only_api_descriptor_reports_pack_availability(self) -> None:
        descriptor = value_101_descriptor(
            installed_pack_ids={"value-101-baseline-v1"}
        )
        baseline = next(
            row for row in descriptor["availability"]["packs"]
            if row["pack_id"] == "value-101-baseline-v1"
        )
        self.assertTrue(baseline["installed"])
        with tempfile.TemporaryDirectory(prefix="value-101-api-") as temporary:
            packs = Path(temporary) / "data-packs"
            patches = (
                patch.object(server, "PACKS_ROOT", packs),
                patch.object(server, "PROJECTS_ROOT", Path(temporary) / "projects"),
                patch.object(server, "RUNS_ROOT", Path(temporary) / "runs"),
            )
            for item in patches:
                item.start()
            api = start_local_api(data_home=Path(temporary), patch_state_roots=False)
            httpd, origin, _session = api.start()
            try:
                payload = json.loads(
                    urllib.request.urlopen(origin + "/api/tutorials/value-101", timeout=10).read()
                )
                self.assertEqual(payload["id"], "value-101")
                self.assertFalse(payload["availability"]["all_packs_installed"])
                self.assertEqual(payload["study"]["data_pack_id"], "value-101-baseline-v1")
            finally:
                api.stop()
                for item in reversed(patches):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
