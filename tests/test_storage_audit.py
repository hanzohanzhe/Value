import json
import pickle
import tempfile
import unittest
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh.compat.modular_simulation_model import Battery
from gridform_core.storage_audit import (
    STORAGE_AUDIT_SCHEMA,
    build_storage_cost_audit,
    build_storage_cost_audit_from_year_results,
    export_storage_cost_audit,
)


class StorageAuditTests(unittest.TestCase):
    def _checkpoint(self, root: Path, year: int, battery: Battery) -> None:
        path = root / f"case_checkpoint_{year}.pkl"
        with path.open("wb") as handle:
            pickle.dump(
                {"completed_year": year, "battery_objects": {"battery": battery}},
                handle,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    def test_export_is_plain_json_and_keeps_detailed_cost_basis(self):
        battery = Battery(
            "battery", 2.0, 1.0, 0.0, 0.0, 0.9, 0.8, 0.0,
            capital_cost=1_000_000.0, battery_type="0.5c",
        )
        battery.prepare_operating_year(2025)
        battery.cost_recovery.record_sale(4.0, 3.0)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._checkpoint(root, 2025, battery)
            output = root / "audit.json"
            export_storage_cost_audit(
                root, output, trust_local_checkpoints=True, run_id="audit-test"
            )
            payload = build_storage_cost_audit(
                root, trust_local_checkpoints=True, run_id="audit-test"
            )
            self.assertTrue(output.is_file())

        asset = payload["years"][0]["assets"][0]
        self.assertEqual(payload["schema_version"], STORAGE_AUDIT_SCHEMA)
        self.assertEqual(payload["summary"]["years"], 1)
        self.assertEqual(asset["pricing_basis"], "full_utilisation_initialisation")
        self.assertEqual(asset["current_year_sold_mwh"], 4.0)
        self.assertEqual(asset["power_capacity_mw"], 1.0)
        self.assertEqual(asset["energy_capacity_mwh"], 2.0)
        self.assertEqual(asset["charge_efficiency"], 0.9)
        self.assertEqual(asset["discharge_efficiency"], 0.8)

    def test_pickle_import_requires_explicit_local_trust(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "local-trust"):
                build_storage_cost_audit(
                    Path(folder), trust_local_checkpoints=False
                )

    def test_safe_v2_year_results_do_not_require_pickle_trust(self):
        observation = {
            "method": "dynamic_annual_average_depreciation_recovery",
            "pricing_basis": "observed_previous_year_sales",
            "previous_year_sold_mwh": 10.0,
            "current_year_sold_mwh": 0.0,
            "holding_recovery_gbp_per_mwh_period": 20_000.0,
            "power_capacity_mw": 1.0,
            "energy_capacity_mwh": 2.0,
            "annual_levelized_project_cost_gbp": 100.0,
            "current_cycle_depreciation_gbp": 2.0,
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "year-results-v2.json"
            path.write_text(
                json.dumps(
                    [{
                        "result_id": "year-2026",
                        "year": 2026,
                        "market": {"extensions": {"storage_cost_observations": {"battery": observation}}},
                    }]
                ),
                encoding="utf-8",
            )
            payload = build_storage_cost_audit_from_year_results(path, run_id="v2")
        codes = {row["code"] for row in payload["years"][0]["diagnostics"]}
        self.assertEqual(payload["source"], "safe_public_year_results_v2")
        self.assertIn("GF_STORAGE_ZERO_SALES_AFTER_OBSERVED_BASIS", codes)
        self.assertIn("GF_STORAGE_HIGH_HOLDING_RECOVERY", codes)


if __name__ == "__main__":
    unittest.main()
