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
             patch("gridform_core.preflight.resolve_scheme_c_parameters", return_value=resolved or ResolvedFixture()):
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


if __name__ == "__main__":
    unittest.main()
