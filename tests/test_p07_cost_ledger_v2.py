"""P0-7 S8: cost ledger v2 (P4-03 and decision A7).

* corrected (p07.compatibility-capital-out-of-headline): run-of-river hydro
  existing-stock compatibility capital leaves the headline as a memo line;
  the doctoral headline keeps it (memo marked as included);
* both profiles (A7): VRE and storage fixed OPEX is folded into levelised
  CAPEX, so it is a memo and never part of the headline;
* capital + operating = headline in the ledger and in system_cost_history.
"""
from __future__ import annotations

import unittest

from gridform_core.asset_economics import capital_cost_components
from gridform_core.cost_ledger import (
    COMPATIBILITY_CAPITAL_LINE,
    VRE_STORAGE_FOM_LINE,
    build_cem_cost_ledger,
)
from gridform_core.methodology import REFERENCE_PROFILE_ID, default_profile_id, resolve_methodology
from gridform_core.v2.contracts import AssetStateV2, MarketYearResult


def _market(capital: float, operating: float, components: dict | None) -> MarketYearResult:
    extensions = {"physical_operating_cost_components_gbp": {"generation": operating}}
    if components is not None:
        extensions["capital_cost_components_gbp"] = components
    return MarketYearResult("m", 2030, "toy", "1", {}, {}, capital + operating, operating, capital,
                            1000.0, 1000.0, 0.0, 0.0, extensions=extensions)


TOY = {"schema_version": "value.capital-cost-components/v1", "included_annualised_capital_gbp": 125.0,
       "included_fixed_opex_gbp": 0.0, "existing_stock_compatibility_capital_gbp": 40.0,
       "vre_storage_fixed_opex_gbp": 0.0}


class CostLedgerV2Tests(unittest.TestCase):
    def _lines(self, ledger):
        return {line.id: line for line in ledger.lines}

    def test_plan_toy_v1_125_v2_85_memo_40(self):
        corrected = build_cem_cost_ledger(_market(125.0, 50.0, TOY), exclude_compatibility_capital=True)
        self.assertEqual(corrected.headline_capital_gbp, 85.0)
        self.assertEqual(corrected.cem_system_cost_gbp, 135.0)
        self.assertEqual(corrected.status, "reconciled")
        memo = self._lines(corrected)[COMPATIBILITY_CAPITAL_LINE]
        self.assertEqual((memo.amount_gbp, memo.included_in_cem_system_cost, memo.classification),
                         (40.0, False, "memo_excluded_from_headline"))
        self.assertIs(corrected.compatibility_capital_in_headline, False)
        doctoral = build_cem_cost_ledger(_market(125.0, 50.0, TOY), exclude_compatibility_capital=False)
        self.assertEqual(doctoral.headline_capital_gbp, 125.0)
        self.assertEqual(doctoral.cem_system_cost_gbp, 175.0)
        self.assertEqual(self._lines(doctoral)[COMPATIBILITY_CAPITAL_LINE].classification,
                         "memo_included_in_commissioned_fleet_capital")
        for ledger in (corrected, doctoral):
            included = sum(line.amount_gbp for line in ledger.lines if line.included_in_cem_system_cost)
            self.assertEqual(included, ledger.cem_system_cost_gbp)
            self.assertEqual(ledger.headline_capital_gbp + 50.0, ledger.cem_system_cost_gbp)

    def test_a7_vre_and_storage_fom_never_enters_the_headline(self):
        components = dict(TOY, included_fixed_opex_gbp=10.0, vre_storage_fixed_opex_gbp=7.0)
        for exclude in (True, False):
            with self.subTest(corrected=exclude):
                ledger = build_cem_cost_ledger(_market(135.0, 50.0, components), exclude_compatibility_capital=exclude)
                self.assertEqual(ledger.headline_capital_gbp, 135.0 - 7.0 - (40.0 if exclude else 0.0))
                fom = self._lines(ledger)[VRE_STORAGE_FOM_LINE]
                self.assertEqual((fom.amount_gbp, fom.included_in_cem_system_cost), (7.0, False))

    def test_components_from_assets(self):
        hydro = AssetStateV2("hydro", "Hydro_natural_flow", 100.0, extensions={
            "annualized_capital_cost_gbp": 40.0, "annual_fixed_opex_gbp": 0.0,
            "capital_cost_scope": "existing_stock_compatibility"})
        battery = AssetStateV2("bat", "1c_battery", 10.0, 10.0, extensions={
            "annualized_capital_cost_gbp": 20.0, "annual_fixed_opex_gbp": 7.0})
        ccgt = AssetStateV2("ccgt", "CCGT", 100.0, extensions={
            "annualized_capital_cost_gbp": 65.0, "annual_fixed_opex_gbp": 3.0})
        components = capital_cost_components((hydro, battery, ccgt))
        self.assertEqual(components["included_annualised_capital_gbp"], 125.0)
        self.assertEqual(components["included_fixed_opex_gbp"], 10.0)
        self.assertEqual(components["existing_stock_compatibility_capital_gbp"], 40.0)
        self.assertEqual(components["vre_storage_fixed_opex_gbp"], 7.0)

    def test_a_psm_without_components_keeps_the_v1_headline(self):
        ledger = build_cem_cost_ledger(_market(125.0, 50.0, None), exclude_compatibility_capital=True)
        self.assertEqual(ledger.cem_system_cost_gbp, 175.0)
        self.assertIsNone(ledger.compatibility_capital_gbp)

    def test_the_switch_is_profile_gated(self):
        self.assertTrue(resolve_methodology(default_profile_id()).enabled("p07.compatibility-capital-out-of-headline"))
        self.assertFalse(resolve_methodology(REFERENCE_PROFILE_ID).enabled("p07.compatibility-capital-out-of-headline"))


if __name__ == "__main__":
    unittest.main()
