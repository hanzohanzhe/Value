from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.hydrology import (
    CanonicalInflow,
    HydroAssetSiteMap,
    HydroSite,
    ReservoirParameters,
    adapt_hydrology_csv,
    reservoir_dispatch,
    run_of_river_dispatch,
    validate_site_mapping,
)
from gridform_validation.hydrology_oracle import solve_reservoir_oracle


ROOT = Path(__file__).resolve().parents[1]
HASH = "a" * 64


def inflow(values, *, site="reservoir", unit="water_unit/period", hours=1.0):
    return CanonicalInflow(
        site, tuple(f"2025-01-01T{index:02d}:00:00+00:00" for index in range(len(values))),
        tuple(values), unit, hours, "UTC", HASH, "fixture/v1",
    )


def reservoir_parameters(**changes):
    values = {
        "site_id": "reservoir", "min_volume": 0.0, "max_volume": 20.0,
        "initial_volume": 5.0, "terminal_volume": 5.0,
        "max_turbine_release_per_period": 3.0,
        "max_total_release_per_period": 5.0,
        "minimum_environmental_release_per_period": 0.25,
        "conversion_mwh_per_water_unit": 1.0, "turbine_efficiency": 0.9,
        "turbine_capacity_mw": 3.0, "information_structure": "perfect_foresight",
    }
    values.update(changes)
    return ReservoirParameters(**values)


class Prompt66HydrologyTests(unittest.TestCase):
    def test_run_of_river_is_period_local_and_curtailment_is_explicit(self):
        site = HydroSite(
            "ror", "run_of_river", "bus-a", 10.0, 0.9,
            {"source": "synthetic fixture", "licence": "CC0-1.0"},
        )
        series = inflow([0.0, 0.5, 1.0], site="ror", unit="p.u.", hours=0.5)
        result = run_of_river_dispatch(site, series, accepted_mwh=(0.0, 1.0, 4.0))
        self.assertEqual(tuple(result.available_energy_mwh), (0.0, 2.5, 5.0))
        self.assertEqual(tuple(result.curtailed_energy_mwh), (0.0, 1.5, 1.0))
        self.assertEqual(result.information_structure, "period_local_no_storage")
        with self.assertRaisesRegex(ValueError, "exceeds"):
            run_of_river_dispatch(site, series, accepted_mwh=(0.0, 3.0, 4.0))
        with self.assertRaisesRegex(ValueError, "missing or reordered"):
            series.validate(expected_period_ids=(*series.period_ids, "missing"))

    def test_mapping_rejects_dangling_double_map_and_pumped_hydro_substitution(self):
        site = HydroSite(
            "ror", "run_of_river", "bus-a", 1.0, 1.0,
            {"source": "fixture", "licence": "CC0-1.0"},
        )
        with self.assertRaisesRegex(ValueError, "dangling"):
            validate_site_mapping((site,), (HydroAssetSiteMap("asset", "missing"),))
        with self.assertRaisesRegex(ValueError, "double-mapped"):
            validate_site_mapping(
                (site,),
                (HydroAssetSiteMap("asset", "ror", 0.6), HydroAssetSiteMap("asset", "ror", 0.6)),
            )
        pumped = HydroSite(
            "pump", "pumped_hydro", "bus-a", 1.0, 0.8,
            {"source": "fixture", "licence": "CC0-1.0"},
        )
        with self.assertRaisesRegex(ValueError, "Unknown hydrology technology"):
            validate_site_mapping((pumped,), ())

    def test_reservoir_water_energy_bounds_drought_flood_and_terminal_target(self):
        parameters = reservoir_parameters()
        drought = reservoir_dispatch(parameters, inflow([0.25] * 4), energy_value_gbp_per_mwh=[1, 2, 3, 4])
        self.assertLess(max(abs(value) for value in drought.water_balance_residual), 1e-9)
        self.assertAlmostEqual(drought.end_volume[-1], 5.0)
        self.assertTrue(all(value >= -1e-10 for value in drought.environmental_bypass))
        flood_parameters = reservoir_parameters(
            initial_volume=20.0, terminal_volume=20.0,
            max_turbine_release_per_period=1.0, max_total_release_per_period=1.0,
            turbine_capacity_mw=1.0,
        )
        flood = reservoir_dispatch(
            flood_parameters, inflow([10.0, 10.0]), energy_value_gbp_per_mwh=[1, 1]
        )
        self.assertGreater(sum(flood.spill), 0)
        self.assertLess(max(abs(value) for value in flood.water_balance_residual), 1e-9)
        with self.assertRaisesRegex(ValueError, "infeasible"):
            reservoir_dispatch(
                reservoir_parameters(initial_volume=0.0, terminal_volume=0.0,
                                     minimum_environmental_release_per_period=2.0),
                inflow([0.0]), energy_value_gbp_per_mwh=[1],
            )

    def test_24_and_168_hour_production_lp_match_independent_oracle(self):
        for periods in (24, 168):
            values = [1.0 + (index % 7) * 0.1 for index in range(periods)]
            prices = [20.0 + (index % 24) * 2.0 for index in range(periods)]
            parameters = reservoir_parameters(max_volume=80.0, initial_volume=20.0, terminal_volume=20.0)
            production = reservoir_dispatch(
                parameters, inflow(values), energy_value_gbp_per_mwh=prices
            )
            oracle = solve_reservoir_oracle(
                {
                    "minimum": parameters.min_volume, "maximum": parameters.max_volume,
                    "initial": parameters.initial_volume, "terminal": parameters.terminal_volume,
                    "max_turbine_release": parameters.max_turbine_release_per_period,
                    "max_total_release": parameters.max_total_release_per_period,
                    "minimum_environmental_release": parameters.minimum_environmental_release_per_period,
                    "conversion": parameters.conversion_mwh_per_water_unit,
                    "efficiency": parameters.turbine_efficiency,
                }, values, prices,
            )
            production_value = sum(
                generation * price for generation, price in zip(production.generation_mwh, prices)
            )
            self.assertTrue(oracle["success"])
            self.assertAlmostEqual(production_value, oracle["objective_gbp"], places=6)
            self.assertLess(max(abs(value) for value in production.water_balance_residual), 1e-8)
            self.assertLess(oracle["max_equality_residual"], 1e-8)

    def test_csv_adapter_records_hash_timezone_units_and_duplicate_failure(self):
        with tempfile.TemporaryDirectory(prefix="force-hydro-csv-") as temporary:
            path = Path(temporary) / "inflow.csv"
            path.write_text(
                "timestamp,site_id,value,unit\n"
                "2025-01-01T00:00:00+00:00,ror,0.4,p.u.\n"
                "2025-01-01T01:00:00+00:00,ror,0.5,p.u.\n",
                encoding="utf-8",
            )
            adapted = adapt_hydrology_csv(
                path, site_id="ror", unit="p.u.", interval_hours=1.0, timezone="UTC"
            )
            self.assertEqual(len(adapted.source_sha256), 64)
            path.write_text(
                "timestamp,site_id,value,unit\n"
                "2025-01-01T00:00:00+00:00,ror,0.4,p.u.\n"
                "2025-01-01T00:00:00+00:00,ror,0.5,p.u.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate"):
                adapt_hydrology_csv(
                    path, site_id="ror", unit="p.u.", interval_hours=1.0, timezone="UTC"
                )

    def test_extension_contract_keeps_real_uk_path_not_evaluated(self):
        payload = json.loads(
            (ROOT / "gridform_core" / "extension_manifests" / "value-hydrology-extension.json").read_text(
                encoding="utf-8"
            )
        )
        text = json.dumps(payload).lower()
        self.assertNotIn("pumped_hydro", text)
        self.assertEqual(payload["maturity"], "experimental")


if __name__ == "__main__":
    unittest.main()
