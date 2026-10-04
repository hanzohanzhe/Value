import unittest

from gridform_validation.value_clearing_oracle import (
    audit_declared_solution,
    audit_declared_storage_limits,
    audit_storage_transition,
    solve_declared_supply,
)


def declared_case():
    return {
        "period_hours": 0.5,
        "target_power_mw": 90.0,
        "offers": [
            {"offer_id": "vre", "asset_id": "wind", "resource_kind": "vre", "side": "supply", "offer_price_gbp_per_mwh": 0.0, "minimum_power_mw": 0.0, "maximum_power_mw": 30.0},
            {"offer_id": "store", "asset_id": "battery", "resource_kind": "storage_discharge", "side": "supply", "offer_price_gbp_per_mwh": 20.0, "minimum_power_mw": 0.0, "maximum_power_mw": 10.0, "charge_period": -1},
            {"offer_id": "import", "asset_id": "france", "resource_kind": "import", "side": "supply", "offer_price_gbp_per_mwh": 40.0, "minimum_power_mw": 0.0, "maximum_power_mw": 25.0},
            {"offer_id": "thermal", "asset_id": "ccgt", "resource_kind": "thermal", "side": "supply", "offer_price_gbp_per_mwh": 60.0, "minimum_power_mw": 0.0, "maximum_power_mw": 50.0},
        ],
        "storage_pre_state": [{
            "asset_id": "battery", "state_of_charge_mwh": 10.0,
            "stored_tranches_mwh": [{"charge_period": -1, "stored_mwh": 10.0}],
            "charge_power_limit_mw": 10.0, "discharge_power_limit_mw": 10.0,
            "energy_capacity_mwh": 20.0, "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9, "period_hours": 0.5,
        }],
    }


class ForceDeclaredClearingOracleTests(unittest.TestCase):
    def test_thermal_vre_import_and_storage_compete_in_independent_lp(self):
        result = solve_declared_supply(declared_case())
        self.assertEqual(result.status, "optimal")
        self.assertAlmostEqual(result.dispatch_power_mw_by_offer["vre"], 30.0)
        self.assertAlmostEqual(result.dispatch_power_mw_by_offer["store"], 10.0)
        self.assertAlmostEqual(result.dispatch_power_mw_by_offer["import"], 25.0)
        self.assertAlmostEqual(result.dispatch_power_mw_by_offer["thermal"], 25.0)
        self.assertAlmostEqual(result.shortage_power_mw, 0.0)
        self.assertTrue(audit_declared_storage_limits(declared_case())["passed"])

    def test_damaged_power_balance_is_rejected(self):
        case = declared_case()
        result = solve_declared_supply(case)
        damaged = dict(result.dispatch_power_mw_by_offer)
        damaged["thermal"] -= 1.0
        audit = audit_declared_solution(
            case,
            dispatch_power_mw_by_offer=damaged,
            shortage_power_mw=result.shortage_power_mw,
        )
        self.assertFalse(audit["passed"])
        self.assertEqual(audit["violations"][0]["constraint"], "power_balance")

    def test_damaged_storage_energy_and_efficiency_are_rejected(self):
        case = declared_case()
        case["offers"][1]["maximum_power_mw"] = 25.0
        case["storage_pre_state"][0]["discharge_efficiency"] = 1.1
        audit = audit_declared_storage_limits(case)
        self.assertFalse(audit["passed"])
        constraints = {item["constraint"] for item in audit["violations"]}
        self.assertIn("storage_efficiency", constraints)
        self.assertIn("storage_tranche_energy", constraints)
        self.assertIn("shared_storage_power_and_energy", constraints)

    def test_damaged_offer_bound_is_rejected(self):
        case = declared_case()
        result = solve_declared_supply(case)
        damaged = dict(result.dispatch_power_mw_by_offer)
        damaged["vre"] = 31.0
        audit = audit_declared_solution(
            case,
            dispatch_power_mw_by_offer=damaged,
            shortage_power_mw=result.shortage_power_mw - 1.0,
        )
        self.assertFalse(audit["passed"])
        self.assertTrue(any(item["constraint"] == "offer_bound" for item in audit["violations"]))

    def test_damaged_soc_transition_is_rejected(self):
        case = declared_case()
        outcome = {
            "stage": "ahead",
            "accepted": [{"asset_id": "battery", "asset_type": "Battery", "accepted_power_mw": 10.0}],
            "storage_post_state": [{**case["storage_pre_state"][0], "state_of_charge_mwh": 10.0}],
        }
        audit = audit_storage_transition(case, outcome)
        self.assertFalse(audit["passed"])
        self.assertEqual(audit["violations"][0]["constraint"], "storage_discharge_soc")


if __name__ == "__main__":
    unittest.main()
