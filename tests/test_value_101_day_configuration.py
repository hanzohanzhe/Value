"""One-day orchestration artifact regression without executing a model."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gridform_core import application


class OneDayConfigurationTests(unittest.TestCase):
    def test_success_publishes_executed_configuration_and_keeps_short_run_gates(self):
        payload = {
            "run_id": "new-one-day-run", "project_id": "frozen-study",
            "data_pack_id": "frozen-pack", "start_year": 2025, "end_year": 2025,
            "scientific_parameters": {"clock.period_hours": 0.5, "example.cost": 73.0},
            "runtime_controls": {"periods_per_year": 48},
            "modules": {}, "extensions": {},
        }
        resolved = SimpleNamespace(**payload, to_dict=lambda: payload)
        psm = SimpleNamespace(id="fixture-psm", run=Mock(return_value=SimpleNamespace(
            year=2025, module_id="fixture-psm", to_dict=lambda: {"period_summaries": []},
        )))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "pack"
            pack.mkdir()
            (pack / "manifest.json").write_text("{}")
            output = root / "model-output"
            output.mkdir()
            with patch.object(application, "validate_pack_run_mode"), \
                 patch.object(application, "native_initial_state", return_value=SimpleNamespace(
                     year=2025, assets=(), planning_projects=(),
                 )), \
                 patch.object(application, "checkpoint_identity", return_value={}), \
                 patch.object(application, "_parent_annual_checkpoint_identity", return_value={}), \
                 patch.object(application, "build_chronology", return_value=()), \
                 patch.object(application, "PSMInput", return_value={}), \
                 patch.object(application, "AnnualModelOrchestratorV2") as annual:
                result = application._run_native_project(
                    project={}, resolved=resolved, registry=None,
                    resolution_graph=SimpleNamespace(implementations_by_slot={"psm": psm}),
                    selected={"psm": "fixture-psm"}, pack_root=pack,
                    network_pack_root=None, output_dir=output, periods=48,
                    mode="value_101_day", manifest_snapshots={}, preparation_seconds=0,
                )
            self.assertEqual(json.loads((output / "resolved-run.json").read_text()), payload)
            self.assertFalse((output / "resolved-run.json.tmp").exists())
            self.assertEqual(result["execution_engine"], "value-psm-only/v1")
            validation = json.loads((output / result["scientific_validation_artifact"]).read_text())
            self.assertFalse(validation["annual_economics_eligible"])
            self.assertEqual(validation["scientific_validation_status"], "not_evaluated")
            self.assertFalse(validation["cem_stages_executed"])
            annual.assert_not_called()
            psm.run.assert_called_once()
