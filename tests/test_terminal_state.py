import unittest

from gridform_core.terminal_state import build_fleet_vintage_ledger, build_terminal_state_report
from gridform_core.v2.contracts import AssetStateV2, PlanningProject, YearState


class TerminalStateTests(unittest.TestCase):
    def test_vintage_and_remaining_value_are_declared_or_unknown(self):
        assets = (
            AssetStateV2("new", "solar", 100, extensions={
                "commissioning_year": 2034, "vintage_source": "project ledger",
                "economic_lifetime_years": 20, "lifetime_source": "cost table",
                "annualized_capital_cost_gbp": 1_000_000,
            }),
            AssetStateV2("unknown", "ccgt", 50),
        )
        result = build_fleet_vintage_ledger(assets, valuation_year=2034, discount_rate=0.05)
        new, unknown = result["rows"]
        expected = 1_000_000 * (1 - 1.05 ** -20) / 0.05
        self.assertAlmostEqual(new["model_remaining_capital_value_gbp"], expected)
        self.assertIsNone(unknown["remaining_life_years"])
        self.assertEqual(unknown["quality"], "not_evaluated")

    def test_pipeline_tail_has_no_fabricated_economics(self):
        project = PlanningProject(
            "p", "Project", "model", "solar", 20, 20, "GB", "planning", "active",
            2033, 2036, "expected_capacity", 0.5,
        )
        state = YearState(2035, (), (project,))
        report = build_terminal_state_report(state, horizon_year=2034, policy="pipeline_tail")
        self.assertEqual(report["post_horizon_capacity_mw"], 20)
        self.assertEqual(report["pipeline_tail"][-1]["system_cost_gbp"], "not_applicable")
        self.assertTrue(report["terminal_state_reconciled"])


if __name__ == "__main__":
    unittest.main()
