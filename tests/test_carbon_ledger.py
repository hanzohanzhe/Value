import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gridform_core.carbon_ledger import (
    CURRENT_SCENARIO, LEGACY_SCENARIO, build_operational_carbon_ledger,
    write_carbon_ledgers,
)
from gridform_core.v2.contracts import AssetStateV2


class CarbonLedgerTests(unittest.TestCase):
    def test_authoritative_direct_and_import_mass(self):
        result = build_operational_carbon_ledger(
            year=2025, scenario_id=CURRENT_SCENARIO,
            generation_mwh_by_asset={"CCGT": 10, "solar_x": 10, "import:France": 10},
            technology_by_asset={"CCGT": "CCGT", "solar_x": "solar", "import:France": "import_electricity"},
            import_country_by_asset={"import:France": "France"}, delivered_demand_mwh=30,
        )
        self.assertEqual(result["status"], "reconciled")
        self.assertAlmostEqual(result["total_carbon_emissions_tco2e"], 4.47)
        self.assertAlmostEqual(result["intensities"]["delivered_demand_kgco2e_per_mwh"], 149.0)

    def test_norway_uses_pinned_nve_annual_fallback(self):
        result = build_operational_carbon_ledger(
            year=2025, scenario_id=CURRENT_SCENARIO,
            generation_mwh_by_asset={"import:Norway": 10},
            technology_by_asset={"import:Norway": "import_electricity"},
            import_country_by_asset={"import:Norway": "Norway"}, delivered_demand_mwh=10,
        )
        self.assertEqual(result["status"], "reconciled")
        self.assertAlmostEqual(result["total_carbon_emissions_tco2e"], 0.119)

    def test_retained_interconnector_ids_resolve_known_country_aliases(self):
        result = build_operational_carbon_ledger(
            year=2025,
            scenario_id=CURRENT_SCENARIO,
            generation_mwh_by_asset={
                "Interconnect_France": 1,
                "Interconnect_Netherland": 1,
                "Interconnect_Beligum": 1,
                "Interconnect_Ireland": 1,
            },
            technology_by_asset={},
            delivered_demand_mwh=4,
        )
        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(result["unresolved_activities"], [])
        self.assertAlmostEqual(result["total_carbon_emissions_tco2e"], 1.164)

    def test_retained_norway_id_resolves_to_same_pinned_fallback(self):
        result = build_operational_carbon_ledger(
            year=2025,
            scenario_id=CURRENT_SCENARIO,
            generation_mwh_by_asset={"Interconnect_Norway": 10},
            technology_by_asset={},
            delivered_demand_mwh=10,
        )
        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(result["unresolved_activities"], [])
        self.assertAlmostEqual(result["total_carbon_emissions_tco2e"], 0.119)

    def test_current_total_adds_asset_specific_embodied_without_double_count(self):
        result = build_operational_carbon_ledger(
            year=2025, scenario_id=CURRENT_SCENARIO,
            generation_mwh_by_asset={"CCGT": 10.0},
            technology_by_asset={"CCGT": "CCGT"}, delivered_demand_mwh=10.0,
            asset_states=(
                AssetStateV2(
                    "CCGT", "CCGT", 100.0,
                    extensions={"economic_lifetime_years": 25.0},
                ),
                AssetStateV2(
                    "commissioned:battery-1", "battery", 10.0,
                    energy_capacity_mwh=40.0, status="commissioned",
                    extensions={
                        "commissioning_year": 2025,
                        "economic_lifetime_years": 10.0,
                    },
                ),
            ),
        )
        # Direct CCGT: 3.94 t; annual CCGT equipment: 1,629.36 t;
        # battery manufacturing: 40 MWh * 89 t/MWh / 10 years = 356 t.
        self.assertAlmostEqual(result["operational_emissions_tco2e"], 3.94)
        self.assertAlmostEqual(result["embodied_lifecycle_emissions_tco2e"], 1985.36)
        self.assertAlmostEqual(result["total_carbon_emissions_tco2e"], 1989.30)
        self.assertAlmostEqual(
            sum(result["components_tco2e"].values()),
            result["total_carbon_emissions_tco2e"],
        )
        # F2-N4: component keys are sorted, independent of the hash seed.
        self.assertEqual(list(result["components_tco2e"]), sorted(result["components_tco2e"]))
        self.assertEqual(list(result["components_tco2e"]), ["asset_embodied", "direct_operational"])

    def test_embodied_missing_energy_capacity_fails_closed(self):
        result = build_operational_carbon_ledger(
            year=2025, scenario_id=CURRENT_SCENARIO,
            generation_mwh_by_asset={}, technology_by_asset={}, delivered_demand_mwh=0,
            asset_states=(AssetStateV2(
                "battery-missing-energy", "battery", 10.0,
                extensions={"economic_lifetime_years": 10.0},
            ),),
        )
        self.assertEqual(result["status"], "not_evaluated")
        self.assertIsNone(result["total_carbon_emissions_tco2e"])

    def test_storage_inventory_and_losses_close(self):
        result = build_operational_carbon_ledger(
            year=2025, scenario_id=CURRENT_SCENARIO,
            generation_mwh_by_asset={}, technology_by_asset={}, delivered_demand_mwh=10,
            storage_trace={
                "charge_mwh": [10.0, 0.0], "discharge_mwh": [0.0, 4.0],
                "charge_source_kgco2e_per_mwh": [400.0, 0.0],
                "charge_efficiency": [0.8], "discharge_efficiency": [0.8],
            },
        )
        self.assertEqual(result["storage_carried_carbon_status"], "reconciled_average_pool")
        self.assertAlmostEqual(result["ending_stored_carbon_inventory_tco2e"], 1.5)

    def test_legacy_storage_scalar_is_not_relabelled(self):
        result = build_operational_carbon_ledger(
            year=2025, scenario_id=LEGACY_SCENARIO,
            generation_mwh_by_asset={}, technology_by_asset={}, delivered_demand_mwh=0,
            legacy_metric=123.4,
        )
        self.assertEqual(result["scheme_c_legacy_carbon_metric"], 123.4)
        self.assertIsNone(result["total_carbon_emissions_tco2e"])

    def test_json_and_sqlite_store_the_same_annual_ledger(self):
        result = build_operational_carbon_ledger(
            year=2025, scenario_id=CURRENT_SCENARIO,
            generation_mwh_by_asset={"solar": 1.0},
            technology_by_asset={"solar": "solar"}, delivered_demand_mwh=1.0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = write_carbon_ledgers(Path(temporary) / "carbon.json", [result])
            exported = json.loads(path.read_text(encoding="utf-8"))["years"][0]
            connection = sqlite3.connect(path.with_suffix(".sqlite"))
            try:
                stored = json.loads(connection.execute(
                    "SELECT ledger_json FROM annual_carbon_ledger WHERE year = 2025"
                ).fetchone()[0])
            finally:
                connection.close()
        self.assertEqual(stored, exported)


if __name__ == "__main__":
    unittest.main()
