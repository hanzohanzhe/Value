from __future__ import annotations

import copy
import unittest

from scripts.audit_prompt46_release import carbon_gate, commissioned_lineage


def result_fixture() -> dict:
    return {
        "planning_advance": {
            "commissioned_projects": [
                {
                    "project_id": "current-project",
                    "capacity_mw": 20.0,
                    "extensions": {
                        "total_capex_gbp": 200.0,
                        "annual_fixed_opex_gbp": 2.0,
                        "economic_lifetime_years": 20.0,
                        "annualized_capital_cost_gbp": 10.0,
                    },
                }
            ],
            "operating_state": {
                "assets": [
                    {"asset_id": "initial-asset"},
                    {"asset_id": "commissioned:prior-project"},
                    {"asset_id": "commissioned:current-project"},
                ]
            },
        },
        "market": {
            "extensions": {
                "state_coupling": {
                    "generator_objects": {
                        "solar": {
                            "source_asset_capacity_mw": {
                                "initial-asset": 5.0,
                                "commissioned:prior-project": 10.0,
                                "commissioned:current-project": 20.0,
                            }
                        }
                    },
                    "storage_objects": {},
                    "active_asset_count": 3,
                    "mapped_asset_count": 3,
                    "unmapped_asset_ids": [],
                }
            }
        },
    }


class Prompt46ReleaseAuditTests(unittest.TestCase):
    def test_prior_year_commissioned_assets_are_expected_live_lineage(self) -> None:
        lineage = commissioned_lineage(result_fixture())
        self.assertEqual(lineage["live_lineage_matches"], 1)
        self.assertEqual(lineage["cumulative_live_lineage_matches"], 2)
        self.assertEqual(lineage["cumulative_commissioned_project_ids"], 2)
        self.assertEqual(lineage["missing_live_project_ids"], [])
        self.assertEqual(lineage["unexpected_live_project_ids"], [])

    def test_live_project_absent_from_operating_state_fails_closed(self) -> None:
        result = copy.deepcopy(result_fixture())
        sources = result["market"]["extensions"]["state_coupling"]["generator_objects"]["solar"]["source_asset_capacity_mw"]
        sources["commissioned:spurious-project"] = 1.0
        lineage = commissioned_lineage(result)
        self.assertEqual(lineage["unexpected_live_project_ids"], ["spurious-project"])

    def test_carbon_gate_accepts_reconciled_physical_total(self) -> None:
        result = carbon_gate({
            "status": "reconciled",
            "scenario": {"scenario_id": "value_current_authoritative_v1"},
            "total_carbon_emissions_tco2e": 123.0,
            "unresolved_activities": [],
        })
        self.assertTrue(result["passed"])
        self.assertEqual(result["interpretation"], "physical_total_reconciled")

    def test_carbon_gate_accepts_only_declared_legacy_nonphysical_boundary(self) -> None:
        row = {
            "status": "not_physically_interpretable",
            "scenario": {"scenario_id": "scheme_c_reproduction_2026_07_18"},
            "total_carbon_emissions_tco2e": None,
            "reason_code": "legacy_storage_scalars_have_no_declared_physical_unit",
            "unresolved_activities": [],
        }
        self.assertTrue(carbon_gate(row)["passed"])
        row["scenario"] = {"scenario_id": "value_current_authoritative_v1"}
        self.assertFalse(carbon_gate(row)["passed"])

    def test_carbon_gate_rejects_generic_not_evaluated(self) -> None:
        self.assertFalse(carbon_gate({
            "status": "not_evaluated",
            "scenario": {"scenario_id": "value_current_authoritative_v1"},
            "total_carbon_emissions_tco2e": None,
            "unresolved_activities": ["imports"],
        })["passed"])


if __name__ == "__main__":
    unittest.main()
