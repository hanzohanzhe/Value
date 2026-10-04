from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path

import pandas as pd

from gridform_core.catalog import DATASET_SLOTS
from gridform_core.application import run_project_application
from gridform_core.data_pack_validation import validate_data_pack
from scripts.build_value_101_packs import (
    BASELINE_PACK_ID,
    build_value_101_pack_family,
)


ROOT = Path(__file__).resolve().parents[1]
CHECKED_IN_PACK = ROOT / "data-packs" / BASELINE_PACK_ID


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class Value101PackTests(unittest.TestCase):
    def test_builder_emits_deterministic_cc0_base_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-") as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            report = build_value_101_pack_family(first)
            build_value_101_pack_family(second)

            first_pack = first / BASELINE_PACK_ID
            manifest = json.loads((first_pack / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn(BASELINE_PACK_ID, report["pack_ids"])
            self.assertEqual(manifest["id"], BASELINE_PACK_ID)
            self.assertEqual(manifest["licence"], "CC0-1.0")
            self.assertEqual(manifest["country"], "SYNTHETIC")
            self.assertEqual(manifest["periods_per_year"], 48)
            self.assertFalse(manifest["annual_economics_eligible"])
            self.assertEqual(len(manifest["bindings"]), len(DATASET_SLOTS))
            self.assertEqual(tree_hash(first), tree_hash(second))

            validation = validate_data_pack(first_pack, manifest, DATASET_SLOTS)
            self.assertTrue(validation["valid"], validation["errors"])
            for role, binding in manifest["bindings"].items():
                self.assertFalse(role.startswith("value.network."), role)
                self.assertEqual(binding["licence"], "CC0-1.0")
                self.assertEqual(binding["redistribution_class"], "redistributable_cc0")
                self.assertTrue(binding["source_url"].startswith("generated://value-101/"))
                self.assertFalse(Path(binding["uri"]).is_absolute())
                self.assertNotIn("..", Path(binding["uri"]).parts)

            demand_path = first_pack / manifest["bindings"]["demand.real"]["uri"]
            self.assertEqual(len(pd.read_csv(demand_path)), 48)
            for role in ("profiles.vre_solar", "profiles.vre_onshore", "profiles.vre_offshore"):
                profile_path = first_pack / manifest["bindings"][role]["uri"]
                self.assertEqual(len(pd.read_csv(profile_path, header=None)), 48)

            fleet_path = first_pack / manifest["bindings"]["fleet.generators"]["uri"]
            fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
            self.assertIn("CCGT", fleet["generators"])
            self.assertEqual(set(fleet["batteries"]), {"1c_battery"})
            self.assertIn("solar_Nottingham", fleet["generators"])
            self.assertIn("onshore_Nottingham", fleet["generators"])
            self.assertIn("offshore21", fleet["generators"])
            self.assertEqual(fleet["batteries"]["1c_battery"]["pool_limit"], 10.0)

    def test_checked_in_pack_is_the_deterministic_builder_output(self) -> None:
        self.assertTrue(CHECKED_IN_PACK.is_dir())
        with tempfile.TemporaryDirectory(prefix="value-101-release-") as temporary:
            rebuilt = Path(temporary)
            build_value_101_pack_family(rebuilt)
            self.assertEqual(
                tree_hash(CHECKED_IN_PACK),
                tree_hash(rebuilt / BASELINE_PACK_ID),
            )

    def test_checked_in_pack_runs_the_real_force_psm_and_cem_chain(self) -> None:
        project = {
            "schema_version": "value.project/v1",
            "id": "value-101-contract-run",
            "name": "VALUE 101 contract run",
            "data_pack_id": BASELINE_PACK_ID,
            "start_year": 2025,
            "end_year": 2026,
            "modules": {
                "psm": "value-bid-at-cost-psm",
                "storage_cost": "dynamic-annual-storage-cost",
                "investment": "agent-investment",
                "pipeline": "planning-pipeline",
                "vre_cap": "vre-expansion-cap",
                "storage_cap": "value-storage-expansion-policy",
                "transition": "value-annual-state-transition",
            },
            "parameters": {},
            "runtime_options": {"runtime.market_trace_level": "full"},
        }
        with tempfile.TemporaryDirectory(prefix="value-101-run-") as temporary:
            output = Path(temporary) / "model-output"
            captured = io.StringIO()
            with redirect_stdout(captured), redirect_stderr(captured):
                result = run_project_application(
                    project,
                    run_id="value-101-contract-run",
                    pack_root=CHECKED_IN_PACK,
                    output_dir=output,
                    mode="tutorial",
                )
            year_result = result["orchestrator_results"][0]
            market = year_result["market"]
            with closing(sqlite3.connect(output / "planning" / "project-index.sqlite")) as connection:
                planning_rows = connection.execute(
                    "SELECT COUNT(*) FROM project_year"
                ).fetchone()[0]
                value101_planning_rows = connection.execute(
                    "SELECT COUNT(*) FROM project_year WHERE project_id LIKE 'value101-solar-planning%'"
                ).fetchone()[0]
            with closing(sqlite3.connect(output / "market" / "market.sqlite")) as connection:
                storage_charge, storage_discharge = connection.execute(
                    "SELECT COALESCE(SUM(storage_charge_mwh),0), "
                    "COALESCE(SUM(storage_discharge_mwh),0) FROM period_summary"
                ).fetchone()
                (
                    minimum_soc, maximum_soc_over_capacity,
                    maximum_power_capacity, maximum_energy_capacity,
                ) = (
                    connection.execute(
                        "SELECT COALESCE(MIN(state_of_charge_mwh),0), "
                        "COALESCE(MAX(state_of_charge_mwh-energy_capacity_mwh),0), "
                        "COALESCE(MAX(power_capacity_mw),0), "
                        "COALESCE(MAX(energy_capacity_mwh),0) "
                        "FROM storage_state"
                    ).fetchone()
                )
            cost_ledger_exists = (output / "ledgers" / "annual-cost-ledger.json").is_file()
            carbon_ledger_exists = (output / "ledgers" / "annual-carbon-ledger.json").is_file()
            cost_ledger = json.loads(
                (output / "ledgers" / "annual-cost-ledger.json").read_text("utf-8")
            )
            carbon_ledger = json.loads(
                (output / "ledgers" / "annual-carbon-ledger.json").read_text("utf-8")
            )
            metadata = json.loads((output / "market" / "metadata.json").read_text("utf-8"))

        self.assertEqual(result["execution_path"], "native_public_contracts")
        self.assertEqual(year_result["year"], 2025)
        self.assertEqual(len(market["period_summaries"]), 48)
        self.assertGreater(market["total_demand_mwh"], 0.0)
        self.assertGreater(market["total_system_cost_gbp"], 0.0)
        self.assertGreater(sum(market["generation_mwh_by_asset"].values()), 0.0)
        self.assertGreater(sum(row["vre_available_mwh"] for row in market["period_summaries"]), 0.0)
        unused_vre = sum(
            row["curtailed_mwh"] for row in market["period_summaries"]
        ) + market["total_excess_mwh"]
        self.assertGreater(unused_vre, 0.0)
        self.assertGreater(
            storage_charge,
            0.0,
            (maximum_power_capacity, maximum_energy_capacity, market["total_excess_mwh"]),
        )
        self.assertGreater(storage_discharge, 0.0)
        self.assertGreaterEqual(minimum_soc, -1e-8)
        self.assertLessEqual(maximum_soc_over_capacity, 1e-8)
        self.assertGreater(planning_rows, 0)
        self.assertGreater(value101_planning_rows, 0)
        self.assertTrue(cost_ledger_exists)
        self.assertTrue(carbon_ledger_exists)
        self.assertEqual(cost_ledger["years"][0]["status"], "reconciled")
        self.assertEqual(carbon_ledger["years"][0]["status"], "reconciled")
        self.assertLess(metadata["maximum_absolute_energy_balance_residual_mwh"], 1e-7)


if __name__ == "__main__":
    unittest.main()
