import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gridform_core.preflight import run_preflight
from gridform_core.preflight import resource_gate_report
from gridform_core.preflight_resources import ResourceEstimate
from gridform_core.project_revision import project_fingerprint
from gridform_core.run_quota import RunQuotaPolicy
from gridform_core.v2.module_manifest import workspace_registry


MODULES = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "storage_cost": "dynamic-annual-storage-cost",
}


# These tests exercise revision and resource warnings, not the host volume.
# Pin the disk probe so the outcome does not depend on the free space of the
# machine running the suite (X0 S1; preflight requires free >= 2x estimate).
PINNED_DISK_USAGE = SimpleNamespace(total=4 * 1024**4, used=1024**4, free=3 * 1024**4)


class ResolvedFixture:
    warnings = ()

    def __init__(self, runtime=None):
        self.runtime = SimpleNamespace(values={
            "runtime.market_trace_level": "summary",
            "runtime.market_export_format": "sqlite",
            "runtime.checkpoint_enabled": True,
            **(runtime or {}),
        })

    def to_dict(self):
        return {
            "scientific_parameters": {},
            "runtime_options": dict(self.runtime.values),
            "sources": {},
            "warnings": [],
        }


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.registry = workspace_registry(Path("missing-modules-directory"))
        self.pack = {"schema_version": "value.data-pack/v1", "id": "pack", "bindings": {}}
        self.project = {
            "schema_version": "value.project/v1",
            "id": "project", "name": "Project", "data_pack_id": "pack",
            "start_year": 2025, "end_year": 2034,
            "modules": MODULES, "parameters": {}, "runtime_options": {},
        }

    def _run(self, project=None, resolved=None):
        with tempfile.TemporaryDirectory() as folder, \
             patch("gridform_core.preflight.validate_data_pack", return_value={
                 "schema_version": "value.data-pack-validation/v1", "valid": True,
                 "errors": [], "warnings": [], "bindings": [],
                 "summary": {"passed": 0, "failed": 0, "total": 0},
             }), \
             patch("gridform_core.preflight.resolve_scheme_c_parameters", return_value=resolved or ResolvedFixture()), \
             patch("gridform_core.preflight.shutil.disk_usage", return_value=PINNED_DISK_USAGE):
            return run_preflight(
                project or self.project,
                mode="full",
                pack_root=Path(folder),
                pack_manifest=self.pack,
                dataset_slots=[],
                registry=self.registry,
                output_root=Path(folder),
            )

    def test_warning_only_legacy_revision_is_accepted(self):
        report = self._run()
        self.assertTrue(report["accepted"])
        self.assertEqual(report["errors"], [])
        self.assertIn("GF_PREFLIGHT_UNSAVED_REVISION", {row["code"] for row in report["warnings"]})
        self.assertEqual(report["estimates"]["periods"], 175_200)
        self.assertGreater(report["estimates"]["peak_memory_bytes"], 0)
        self.assertEqual(report["estimates"]["data_scale"]["operating_assets"], 0)

    def test_staged_psm_with_a_dwell_cost_module_warns(self):
        # P0-6 S10 (P5-15): the staged PSM bids storage with d = 0.
        default = self._run()
        self.assertNotIn("GF_STAGED_DWELL_NOT_TRACKED", {row["code"] for row in default["warnings"]})
        staged = {**self.project, "modules": {**MODULES, "psm": "value-staged-bid-at-cost-psm"}}
        report = self._run(staged)
        self.assertIn("GF_STAGED_DWELL_NOT_TRACKED", {row["code"] for row in report["warnings"]})
        legacy = {**self.project, "modules": {**MODULES, "psm": "value-staged-bid-at-cost-psm",
                                               "storage_cost": "value-legacy-storage-tariff"}}
        self.assertNotIn("GF_STAGED_DWELL_NOT_TRACKED", {row["code"] for row in self._run(legacy)["warnings"]})

    def test_stale_project_revision_is_blocking(self):
        project = {**self.project, "revision_sha256": "0" * 64}
        report = self._run(project)
        self.assertFalse(report["accepted"])
        self.assertIn("GF_PREFLIGHT_PROJECT_REVISION", {row["code"] for row in report["errors"]})

    def test_matching_revision_and_checkpoint_warning(self):
        project = dict(self.project)
        project["revision_sha256"] = project_fingerprint(project, self.registry, self.pack)
        report = self._run(project, ResolvedFixture({"runtime.checkpoint_enabled": False}))
        self.assertTrue(report["accepted"])
        self.assertIn("GF_PREFLIGHT_CHECKPOINT_DISABLED", {row["code"] for row in report["warnings"]})

    def test_selected_parquet_without_optional_engine_is_blocking(self):
        real_find = __import__("importlib").util.find_spec

        def find_spec(name):
            return None if name == "pyarrow" else real_find(name)

        with patch("gridform_core.preflight.importlib.util.find_spec", side_effect=find_spec):
            report = self._run(resolved=ResolvedFixture({"runtime.market_export_format": "parquet"}))
        self.assertFalse(report["accepted"])
        self.assertIn("GF_PREFLIGHT_OPTIONAL_PARQUET", {row["code"] for row in report["errors"]})

    def test_zonal_preflight_refuses_a_missing_explicit_demand_mode(self):
        project = {
            **self.project,
            "modules": {
                **MODULES,
                "psm": "value-staged-bid-at-cost-psm",
                "balancing": "value-zonal-redispatch-balancing",
                "weather_spatializer": "value-representative-point-weather",
            },
            "market_configuration": {"network_pack_id": "missing-network"},
        }

        report = self._run(project)

        self.assertFalse(report["accepted"])
        self.assertIn(
            "GF_PREFLIGHT_ZONAL_DEMAND_MODE",
            {row["code"] for row in report["errors"]},
        )

    def test_prompt122_hard_refusal_preserves_requested_full_trace(self):
        project = {
            **self.project,
            "runtime_options": {"runtime.market_trace_level": "full"},
        }
        estimate = ResourceEstimate(
            persisted_bytes=20,
            temporary_bytes=5,
            reserve_bytes=10,
            runtime_seconds=1.0,
            trace_profile="full",
            calibration_basis={"persisted_safety_multiplier": 1.5},
            row_cardinality={"zones": 3},
        )

        report = resource_gate_report(
            project=project,
            estimate=estimate,
            free_bytes=34,
            quota_policy=RunQuotaPolicy(
                global_quota_bytes=100,
                per_run_quota_bytes=100,
                minimum_free_bytes=0,
            ),
        )

        self.assertFalse(report["accepted"])
        self.assertEqual(report["errors"][0]["code"], "VALUE_PREFLIGHT_DISK_SPACE")
        self.assertEqual(
            report["errors"][0]["corrective_actions"],
            ["Choose Summary", "Move output root", "Free space"],
        )
        self.assertEqual(
            project["runtime_options"]["runtime.market_trace_level"], "full"
        )

    def test_application_cli_passes_explicit_network_pack_to_preflight(self):
        from gridform_core.application import main

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project_path = root / "project.json"
            pack_root = root / "pack"
            network_root = root / "network"
            output_root = root / "output"
            pack_root.mkdir()
            network_root.mkdir()
            project_path.write_text("{}", encoding="utf-8")
            (pack_root / "manifest.json").write_text(
                json.dumps({"id": "pack", "bindings": {}}), encoding="utf-8"
            )
            arguments = [
                "value-run",
                "--project", str(project_path),
                "--pack", str(pack_root),
                "--network-pack", str(network_root),
                "--output", str(output_root),
                "--mode", "full",
            ]
            with patch.object(sys, "argv", arguments), patch(
                "gridform_core.preflight.run_preflight",
                return_value={"accepted": True},
            ) as preflight, patch(
                "gridform_core.application.run_project_application",
                return_value={"engine": "value-native", "system_cost_history": []},
            ):
                main()

        self.assertEqual(
            preflight.call_args.kwargs.get("network_pack_root"),
            network_root.resolve(),
        )


class R14PreflightTests(unittest.TestCase):
    """R1-4: disabled modules (M2-N2), the runtime-kernel seal (M-D6), runtime estimate (F2-N2)."""

    setUp = PreflightTests.setUp
    _run = PreflightTests._run

    def test_selected_disabled_module_is_named_with_its_own_code(self):
        project = {**self.project, "modules": {**MODULES, "storage_cost": "uat-disabled-offer"}}
        disabled = [{"module_id": "uat-disabled-offer", "module_version": "0.1.0", "enabled": False}]
        with patch("gridform_core.module_installation.list_module_installations", return_value=disabled):
            report = self._run(project)
        self.assertFalse(report["accepted"])
        codes = [row["code"] for row in report["errors"]]
        self.assertIn("GF_PREFLIGHT_MODULE_DISABLED", codes)
        # R4 M-低3: the selection and revision errors caused only by the
        # disabled module are not repeated with misleading advice.
        self.assertNotIn("GF_PREFLIGHT_MODULE_SELECTION", codes)
        self.assertNotIn("GF_PREFLIGHT_PROJECT_REVISION", codes)
        issue = next(row for row in report["errors"] if row["code"] == "GF_PREFLIGHT_MODULE_DISABLED")
        self.assertIn("module uat-disabled-offer 0.1.0", issue["message"])
        self.assertIn("Enable", issue["corrective_action"])
        self.assertEqual(report["checks"]["module_disabled"], [{"kind": "module", "id": "uat-disabled-offer", "versions": ["0.1.0"]}])
        with patch("gridform_core.module_installation.list_module_installations",
                   return_value=[{**disabled[0], "enabled": True}]):
            report = self._run(project)
        self.assertNotIn("GF_PREFLIGHT_MODULE_DISABLED", {row["code"] for row in report["errors"]})
        self.assertIn("GF_PREFLIGHT_MODULE_SELECTION", {row["code"] for row in report["errors"]})

    def test_unsealed_runtime_kernel_blocks_readiness(self):
        report = self._run()
        self.assertEqual(report["checks"]["runtime_overlay"], {"passed": True, "errors": []})
        changed = {"errors": ["modular_simulation_model.py: registered runtime file changed (value_instrumentation); reseal with --correction <id>"],
                   "warnings": []}
        with patch("gridform_core.builtin.scheme_c_1000twh.runtime_overlay.inspect_runtime_overlay", return_value=changed):
            report = self._run()
        self.assertFalse(report["accepted"])
        issue = next(row for row in report["errors"] if row["code"] == "GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED")
        self.assertIn("modular_simulation_model.py", issue["message"])
        self.assertIn("seal_runtime_overlay.py --correction", issue["corrective_action"])
        self.assertFalse(report["checks"]["runtime_overlay"]["passed"])

    def test_runtime_estimate_uses_a_realistic_default_and_annual_runs(self):
        from gridform_core.preflight import DEFAULT_SECONDS_PER_PERIOD, _estimates
        policy = {"total_periods": 35_040, "years": 2, "mode": "two_year", "periods_per_year": 17_520}
        with tempfile.TemporaryDirectory() as folder:
            runs = Path(folder)
            estimate = _estimates(self.project, policy, {}, runs, {})
            self.assertEqual(DEFAULT_SECONDS_PER_PERIOD, 0.03)
            self.assertAlmostEqual(estimate["runtime_seconds"], 35_040 * 0.03)
            self.assertLess(estimate["runtime_seconds"] / 3600, 0.5)  # was 3.4 hours
            for name, mode, periods, seconds in (("smoke", "smoke", 2, 5), ("full", "full", 17_520, 175)):
                (runs / name).mkdir()
                (runs / name / "status.json").write_text(json.dumps({
                    "status": "completed", "mode": mode, "run_policy": {"total_periods": periods},
                    "started_at": "2026-10-06T10:00:00", "finished_at": f"2026-10-06T10:{seconds // 60:02d}:{seconds % 60:02d}"}))
            estimate = _estimates(self.project, policy, {}, runs, {})
            self.assertAlmostEqual(estimate["runtime_seconds"], 35_040 * 175 / 17_520)
            self.assertIn("comparable completed local run", estimate["runtime_basis"])
            short = _estimates(self.project, {**policy, "total_periods": 2, "years": 1, "mode": "smoke"}, {}, runs, {})
            self.assertEqual(short["runtime_seconds"], 60.0)


if __name__ == "__main__":
    unittest.main()
