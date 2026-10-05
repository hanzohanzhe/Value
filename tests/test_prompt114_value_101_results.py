from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import model_runner, server
from gridform_core.value_101 import value_101_study
from gridform_core.value_101_results import build_value_101_comparison
from tests.local_api_harness import start_local_api


ROOT = Path(__file__).resolve().parents[1]


def write_fixture(
    root: Path,
    *,
    run_id: str,
    kind: str,
    changed: list[str],
    scale: float,
    actual_overrides: dict[str, object] | None = None,
) -> Path:
    output = root / "model-output"
    (output / "ledgers").mkdir(parents=True)
    (output / "market").mkdir(parents=True)
    (output / "planning").mkdir(parents=True)
    modules = {
        "psm": "value-bid-at-cost-psm",
        "storage_cost": "value-legacy-storage-tariff" if kind == "storage" else "dynamic-annual-storage-cost",
        "investment": "agent-investment",
        "pipeline": "planning-pipeline",
        "vre_cap": "vre-expansion-cap",
        "storage_cap": "value-storage-expansion-policy",
        "transition": "value-annual-state-transition",
    }
    origin = {
        "origin": "guided-course",
        "course_revision": "value-101/v1",
        "variant_kind": kind,
        "parent_project_id": None if kind == "baseline" else "value-101-baseline",
        "changed_dimensions": changed,
    }
    (root / "status.json").write_text(json.dumps({
        "id": run_id,
        "project_id": f"{run_id}-study",
        "project_name": run_id,
        "mode": "tutorial",
        "status": "completed",
        "run_policy": {"start_year": 2025, "end_year": 2025, "periods_per_year": 2},
        "modules": modules,
        "extensions": {"value_101": origin},
    }), encoding="utf-8")
    resolved = {
        "data_pack_id": "value-101-windy-v1" if kind == "data" else "value-101-baseline-v1",
        "start_year": 2025,
        "end_year": 2026,
        "modules": modules,
        "scientific_parameters": {"carbon.factor_scenario": "fixture"},
        "runtime_controls": {"periods_per_year": 48},
        "extensions": {"project_revision_sha256": f"revision-{run_id}", "value_101": origin},
    }
    for key, value in (actual_overrides or {}).items():
        if key.startswith("modules."):
            resolved["modules"][key.split(".", 1)[1]] = value
        elif key.startswith("scientific_parameters."):
            resolved["scientific_parameters"][key.split(".", 1)[1]] = value
        else:
            resolved[key] = value
    (output / "resolved-run.json").write_text(json.dumps(resolved), encoding="utf-8")
    (output / "ledgers" / "annual-cost-ledger.json").write_text(json.dumps({
        "schema_version": "value.annual-cost-ledger/v1",
        "definition_id": "value.cem-system-resource-cost/v1",
        "years": [{
            "year": 2025,
            "status": "reconciled",
            "definition_id": "value.cem-system-resource-cost/v1",
            "cem_system_cost_gbp": 100.0 * scale,
            "cem_system_cost_gbp_per_mwh_served": 5.0,
            "demand_served_mwh": 20.0 * scale,
            "lines": [
                {"id": "commissioned_fleet.annualised_capital", "amount_gbp": 60.0 * scale},
                {"id": "operation.generation_import_and_reliability", "amount_gbp": 40.0 * scale},
            ],
        }],
    }), encoding="utf-8")
    (output / "ledgers" / "annual-carbon-ledger.json").write_text(json.dumps({
        "schema_version": "value.carbon-ledger-collection/v2",
        "years": [{
            "schema_version": "value.carbon-ledger/v2",
            "year": 2025,
            "status": "reconciled",
            "total_carbon_emissions_tco2e": 2.0 * scale,
            "operational_emissions_tco2e": 0.5 * scale,
            "embodied_lifecycle_emissions_tco2e": 1.5 * scale,
            "intensities": {
                "operational_kgco2e_per_mwh": 25.0,
                "overall_kgco2e_per_mwh": 100.0,
                "denominator_mwh": 20.0 * scale,
            },
        }],
    }), encoding="utf-8")
    market = output / "market" / "market.sqlite"
    with sqlite3.connect(market) as connection:
        connection.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE period_summary(
                year INTEGER, period INTEGER, forecast_demand_mwh REAL,
                real_demand_mwh REAL, accepted_supply_mwh REAL,
                storage_charge_mwh REAL, storage_discharge_mwh REAL,
                flexible_demand_mwh REAL, export_mwh REAL,
                vre_available_mwh REAL, vre_accepted_mwh REAL,
                curtailed_mwh REAL, import_mwh REAL,
                clearing_price_gbp_per_mwh REAL, blackout_mwh REAL,
                excess_mwh REAL, energy_balance_residual_mwh REAL,
                compatibility_adjustment_mwh REAL,
                raw_energy_balance_residual_mwh REAL
            );
            CREATE TABLE storage_state(
                year INTEGER, period INTEGER, asset_id TEXT,
                state_of_charge_mwh REAL, charge_mwh REAL, discharge_mwh REAL,
                power_capacity_mw REAL, energy_capacity_mwh REAL
            );
        """)
        connection.execute("INSERT INTO metadata VALUES(?,?)", ("semantic_metadata", json.dumps({"period_hours": 0.5, "excess_relationship": "separate_prebalancing", "excess_scope": "inflexible_mixed"})))
        for period in range(2):
            connection.execute("INSERT INTO period_summary VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                2025, period, 10.0 * scale, 10.0 * scale, 10.0 * scale,
                1.0 * scale, 0.5 * scale, 0.0, 0.0,
                10.0 * scale, 7.5 * scale, 1.0 * scale, 2.0 * scale,
                50.0, 0.0, 1.5 * scale, 0.0, 0.0, 0.0,
            ))
            connection.execute("INSERT INTO storage_state VALUES(?,?,?,?,?,?,?,?)", (
                2025, period, "battery", (2.0 + period) * scale,
                1.0 * scale, 0.5 * scale, 5.0, 10.0,
            ))
    planning = output / "planning" / "project-index.sqlite"
    with sqlite3.connect(planning) as connection:
        connection.executescript("""
            CREATE TABLE project_year(
                year INTEGER, project_id TEXT, source TEXT, technology TEXT,
                capacity_mw REAL, region TEXT, latitude REAL, longitude REAL,
                development_stage TEXT, latest_status TEXT,
                expected_completion_year INTEGER, realised_outcome TEXT,
                failure_reason_code TEXT
            );
            CREATE TABLE event(
                project_id TEXT, year INTEGER, event_type TEXT,
                reason_code TEXT, capacity_mw REAL, region TEXT
            );
        """)
        connection.execute("INSERT INTO project_year VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (2025, "project-1", "fixture", "solar", 15.0, "England", None, None, "planning", "commissioned", 2025, "commissioned", None))
        for event_type in ("admitted", "commissioned", "failed"):
            connection.execute("INSERT INTO event VALUES(?,?,?,?,?,?)", (f"{event_type}-project", 2025, event_type, None, 5.0, "England"))
    return root


class Value101ResultTests(unittest.TestCase):
    def test_worker_refuses_missing_or_corrupt_declared_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-missing-status-") as temporary:
            status_path = Path(temporary) / "status.json"
            with self.assertRaisesRegex(RuntimeError, "declared run status"):
                model_runner._load_declared_run_status(status_path, "run-1", "study-1")
            status_path.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "declared run status"):
                model_runner._load_declared_run_status(status_path, "run-1", "study-1")

    def test_background_worker_preserves_declared_run_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-worker-status-") as temporary:
            state = Path(temporary)
            run_id = "value-101-baseline-run"
            run_root = state / "runs" / run_id
            snapshot = run_root / "input-snapshot"
            (snapshot / "pack").mkdir(parents=True)
            project = value_101_study()
            project["revision_sha256"] = "fixture-revision"
            (snapshot / "project.json").write_text(json.dumps(project), encoding="utf-8")
            (snapshot / "pack" / "manifest.json").write_text(
                json.dumps({"id": "value-101-baseline-v1"}), encoding="utf-8"
            )
            (run_root / "preflight.json").write_text(
                json.dumps({"accepted": True, "warnings": []}), encoding="utf-8"
            )
            declared = {
                "id": run_id,
                "project_id": project["id"],
                "status": "queued",
                "created_at": "2026-08-24T12:00:00+01:00",
                "quota": {"reservation_bytes": 1024},
                "extensions": project["extensions"],
                "comparison_parent_run_id": "parent-run",
                "run_lineage_artifact": "run-lineage.json",
            }
            (run_root / "status.json").write_text(json.dumps(declared), encoding="utf-8")

            registry = SimpleNamespace(
                manifest=lambda *_args, **_kwargs: SimpleNamespace(requires_capabilities=())
            )

            def fake_application(*_args, output_dir: Path, **_kwargs):
                validation = output_dir / "validation" / "scientific-validation.json"
                validation.parent.mkdir(parents=True)
                validation.write_text(json.dumps({
                    "execution_status": "completed",
                    "contract_validation_status": "passed",
                    "scientific_validation_status": "not_evaluated",
                    "annual_economics_eligible": False,
                }), encoding="utf-8")
                return {
                    "scientific_validation_artifact": "validation/scientific-validation.json",
                    "provenance_artifact": "provenance.json",
                }

            with (
                patch.object(model_runner, "STATE_ROOT", state),
                patch.object(model_runner, "workspace_registry", return_value=registry),
                patch.object(model_runner, "verify_run_input_snapshot", return_value={
                    "snapshot_id": "snapshot-fixture",
                    "input_tree_sha256": "tree-fixture",
                }),
                patch.object(model_runner, "resolve_zonal_pack_selection", return_value=SimpleNamespace(
                    revision_manifest={}
                )),
                patch.object(model_runner, "run_project_application", side_effect=fake_application),
            ):
                model_runner.run(project["id"], run_id, "tutorial")

            completed = json.loads((run_root / "status.json").read_text(encoding="utf-8"))

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["extensions"], declared["extensions"])
        self.assertEqual(completed["created_at"], declared["created_at"])
        self.assertEqual(completed["quota"], declared["quota"])
        self.assertEqual(completed["comparison_parent_run_id"], "parent-run")
        self.assertEqual(completed["run_lineage_artifact"], "run-lineage.json")

    def test_builder_reads_artifacts_and_orders_exactly_three_controlled_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-results-") as temporary:
            root = Path(temporary)
            baseline = write_fixture(root / "baseline", run_id="baseline", kind="baseline", changed=[], scale=1.0)
            data = write_fixture(root / "data", run_id="data", kind="data", changed=["data_pack_id"], scale=1.2)
            storage = write_fixture(root / "storage", run_id="storage", kind="storage", changed=["modules.storage_cost"], scale=0.8)
            result = build_value_101_comparison(baseline, data, storage)

        self.assertEqual([row["variant_kind"] for row in result["rows"]], ["baseline", "data", "storage"])
        self.assertEqual(len(result["rows"]), 3)
        self.assertFalse(result["annual_economics_eligible"])
        self.assertEqual(result["comparison_gate"]["status"], "controlled")
        baseline_row = result["rows"][0]
        self.assertEqual(baseline_row["teaching_window_system_resource_cost_gbp"], 100.0)
        self.assertEqual(baseline_row["teaching_window_physical_operating_cost_gbp"], 40.0)
        self.assertEqual(baseline_row["teaching_window_cost_gbp_per_mwh_served"], 5.0)
        self.assertEqual(baseline_row["teaching_window_total_carbon_emissions_tco2e"], 2.0)
        self.assertEqual(baseline_row["teaching_window_operational_carbon_intensity_kgco2e_per_mwh"], 25.0)
        self.assertEqual(baseline_row["teaching_window_overall_carbon_intensity_kgco2e_per_mwh"], 100.0)
        self.assertEqual(baseline_row["teaching_window_vre_available_mwh"], 20.0)
        self.assertEqual(baseline_row["teaching_window_vre_accepted_mwh"], 15.0)
        self.assertEqual(baseline_row["teaching_window_vre_unused_mwh"], 5.0)
        self.assertEqual(baseline_row["teaching_window_storage_charge_mwh"], 2.0)
        self.assertEqual(baseline_row["teaching_window_storage_discharge_mwh"], 1.0)
        self.assertEqual(baseline_row["teaching_window_terminal_soc_mwh"], 3.0)
        self.assertEqual(baseline_row["teaching_window_load_shedding_mwh"], 0.0)
        self.assertEqual(baseline_row["planning_events"], {"admitted": 1, "failed": 1, "commissioned": 1})
        self.assertIn("market_replay", baseline_row["detail_routes"])
        self.assertIn("raw_json", baseline_row["detail_routes"])

    def test_declared_extra_dimension_refuses_controlled_interpretation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-results-bad-") as temporary:
            root = Path(temporary)
            baseline = write_fixture(root / "baseline", run_id="baseline", kind="baseline", changed=[], scale=1.0)
            data = write_fixture(root / "data", run_id="data", kind="data", changed=["data_pack_id", "parameters.foo"], scale=1.2)
            storage = write_fixture(root / "storage", run_id="storage", kind="storage", changed=["modules.storage_cost"], scale=0.8)
            result = build_value_101_comparison(baseline, data, storage)
        self.assertEqual(result["comparison_gate"]["status"], "refused")
        self.assertFalse(result["comparison_gate"]["controlled_interpretation_allowed"])

    def test_actual_extra_dimension_refuses_even_when_declaration_looks_controlled(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-results-hidden-change-") as temporary:
            root = Path(temporary)
            baseline = write_fixture(root / "baseline", run_id="baseline", kind="baseline", changed=[], scale=1.0)
            data = write_fixture(
                root / "data",
                run_id="data",
                kind="data",
                changed=["data_pack_id"],
                scale=1.2,
                actual_overrides={"modules.psm": "hidden-alternative-psm"},
            )
            storage = write_fixture(root / "storage", run_id="storage", kind="storage", changed=["modules.storage_cost"], scale=0.8)
            result = build_value_101_comparison(baseline, data, storage)
        self.assertEqual(result["comparison_gate"]["status"], "refused")
        self.assertIn("modules.psm", result["rows"][1]["actual_changed_dimensions"])
        self.assertTrue(any("actual" in value for value in result["comparison_gate"]["violations"]))

    def test_api_ignores_request_totals_and_reads_local_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-results-api-") as temporary:
            runs = Path(temporary)
            write_fixture(runs / "baseline", run_id="baseline", kind="baseline", changed=[], scale=1.0)
            write_fixture(runs / "data", run_id="data", kind="data", changed=["data_pack_id"], scale=1.2)
            write_fixture(runs / "storage", run_id="storage", kind="storage", changed=["modules.storage_cost"], scale=0.8)
            with patch.object(server, "RUNS_ROOT", runs):
                api = start_local_api(data_home=Path(temporary), patch_state_roots=False)
                httpd, _origin, _session = api.start()
                try:
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{httpd.server_address[1]}/api/tutorials/value-101/comparison",
                        method="POST",
                        data=json.dumps({
                            "baseline_run_id": "baseline",
                            "data_run_id": "data",
                            "storage_run_id": "storage",
                            "teaching_window_system_resource_cost_gbp": 999999999.0,
                        }).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=10) as response:
                        payload = json.loads(response.read())
                finally:
                    api.stop()
        self.assertEqual(payload["rows"][0]["teaching_window_system_resource_cost_gbp"], 100.0)

    def test_frontend_renders_server_rows_and_local_evidence_controls(self) -> None:
        component = (ROOT / "app" / "features" / "learn" / "Value101Comparison.tsx")
        self.assertTrue(component.is_file())
        source = component.read_text("utf-8")
        course = (ROOT / "app" / "features" / "learn" / "Value101Learn.tsx").read_text("utf-8")
        for token in (
            "comparison.rows",
            "annual_economics_eligible",
            "Market replay",
            "Storage SOC",
            "VRE & curtailment",
            "Cost and carbon",
            "Planning",
            "Provenance",
            "Raw JSON",
            "Export completion JSON",
            "Reset VALUE 101",
        ):
            self.assertIn(token, source)
        self.assertIn("Value101Comparison", course)
        self.assertNotIn("reduce(", source)


if __name__ == "__main__":
    unittest.main()
