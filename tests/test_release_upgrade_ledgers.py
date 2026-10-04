import math
import unittest

from gridform_core.cost_ledger import build_cem_cost_ledger
from gridform_core.storage_catalogue import compatibility_catalogue
from gridform_core.storage_recovery import recovery_adequacy, sensitivity_specifications
from gridform_core.v2.contracts import MarketYearResult


def market(**overrides):
    values = dict(
        result_id="test:2025",
        year=2025,
        module_id="test-psm",
        module_version="1.0.0",
        generation_mwh_by_asset={"thermal": 95.0},
        market_income_gbp_by_agent={},
        total_system_cost_gbp=999.0,
        total_operational_cost_gbp=40.0,
        total_levelized_capital_cost_gbp=60.0,
        total_demand_mwh=100.0,
        total_generation_mwh=95.0,
        total_blackout_mwh=5.0,
        total_excess_mwh=0.0,
    )
    values.update(overrides)
    return MarketYearResult(**values)


class CostLedgerTests(unittest.TestCase):
    def test_cem_headline_excludes_legacy_total_and_transfers(self):
        value = market(extensions={"market_settlement_gbp": 500.0, "policy_transfer_gbp": 20.0})
        ledger = build_cem_cost_ledger(value, legacy_system_cost_gbp=999.0)
        self.assertEqual(ledger.cem_system_cost_gbp, 100.0)
        self.assertEqual(ledger.cem_system_cost_gbp_per_mwh_served, 100.0 / 95.0)
        self.assertEqual(ledger.legacy_system_cost_gbp, 999.0)
        self.assertEqual(sum(line.included_in_cem_system_cost for line in ledger.lines), 2)

    def test_named_operating_breakdown_must_reconcile(self):
        value = market(extensions={"physical_operating_cost_components_gbp": {"fuel": 30.0, "vom": 10.0}})
        self.assertEqual(build_cem_cost_ledger(value).cem_system_cost_gbp, 100.0)
        with self.assertRaises(ValueError):
            build_cem_cost_ledger(market(extensions={"physical_operating_cost_components_gbp": {"fuel": 30.0}}))


class StorageCatalogueAndRecoveryTests(unittest.TestCase):
    def test_catalogue_preserves_duration_efficiency_and_battery_wear_boundary(self):
        catalogue = compatibility_catalogue()
        catalogue.validate_capacity("0.5c", power_capacity_mw=10.0, energy_capacity_mwh=20.0)
        with self.assertRaises(ValueError):
            catalogue.validate_capacity("0.5c", power_capacity_mw=10.0, energy_capacity_mwh=10.0)
        self.assertTrue(catalogue.get("0.5c").has_battery_cycle_depreciation)
        self.assertFalse(catalogue.get("pumped_hydro").has_battery_cycle_depreciation)
        self.assertAlmostEqual(catalogue.get("0.5c").input_output_energy_ratio, 0.98**2)

    def test_recovery_adequacy_and_variants_are_explicit(self):
        report = {
            "technology": "0.5c",
            "pricing_basis": "previous_year_sales",
            "current_year_sold_mwh": 100.0,
            "current_year_average_dwell_periods": 2.0,
            "cycle_depreciation_gbp_per_mwh": 1.0,
            "holding_recovery_gbp_per_mwh_period": 2.0,
            "annual_levelized_project_cost_gbp": 500.0,
        }
        adequacy = recovery_adequacy(report)
        self.assertEqual(adequacy["status"], "reconciled")
        variants = sensitivity_specifications()
        self.assertEqual([row["utilisation_floor_fraction"] for row in variants], [0.0, 0.01, 0.05, 0.10])
        self.assertEqual(variants[0]["classification"], "published_baseline")


if __name__ == "__main__":
    unittest.main()
