"""P0-8 S7: economic dec pricing and proportional ties (P2-05, P3-04).

Every staged balancing dec bid used to be GBP 0, so whether a fuel unit or a
wind farm was decremented depended on the asset id, and a decremented thermal
unit kept its ahead income without paying back the fuel it saved.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gridform_core import network_method_rules
from gridform_core.builtin.scheme_c_1000twh.copperplate_balancing import CopperplateBalancing
from gridform_core.builtin.scheme_c_1000twh.staged_psm import StagedBidAtCostPSM
from gridform_core.network_method_rules import (
    ECONOMIC,
    LEGACY,
    NetworkMethodRulesError,
    dec_pricing_inputs,
)
from gridform_core.staged_market_contracts import AheadMarketInput
from gridform_core.parameters import ParameterValidationError, resolve_scheme_c_parameters
from gridform_core.v2.contracts import (
    AssetStateV2,
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
    StorageDispatchResource,
)
from gridform_validation.zonal_case_generator import production_solution
from tests.network_toys import zonal_bid, zonal_declaration
from tests.test_prompt95_staged_copperplate import FlatStorageCostDefinition

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data-packs" / "value-101-baseline-v1"

ECONOMICS = {
    "capital_cost_per_mw": 0.0,
    "capital_cost_per_mwh": 0.0,
    "total_capex_gbp": 0.0,
    "annual_fixed_opex_gbp": 0.0,
    "economic_lifetime_years": 25.0,
    "capital_discount_rate": 0.0,
    "annualized_capital_cost_gbp": 0.0,
    "fixed_om_basis": "test_fixture",
    "asset_economics_schema_version": "value.asset-economics/v1",
}


def psm_input(
    resources: tuple[DispatchResource, ...],
    *,
    forecast: float,
    actual: float,
    storage: tuple[StorageDispatchResource, ...] = (),
    parameters: dict[str, object] | None = None,
) -> PSMInput:
    assets = tuple(
        AssetStateV2(row.asset_id, row.technology, row.capacity_mw, extensions=ECONOMICS)
        for row in resources
    ) + tuple(
        AssetStateV2(row.asset_id, "1c_battery", row.discharge_power_mw, row.energy_capacity_mwh,
                     extensions=ECONOMICS)
        for row in storage
    )
    data = ChronologicalPSMData(
        ("2025:0",), (actual,), resources, storage, 17_000.0,
        terminal_soc_rule="free", extensions={"forecast_demand_mwh": (forecast,)},
    )
    return PSMInput(
        "run-dec", 2025, "fixture-pack", OperatingState(2025, assets, ()), 1.0,
        {"market.bid_multiplier": 1.0, **(parameters or {})}, chronology=data,
    )


def run_staged(model_input: PSMInput, rules=ECONOMIC):
    tie_rule = "pro_rata_v1" if rules is ECONOMIC else "bid_id_v1"
    balancing = CopperplateBalancing(tie_rule=tie_rule)
    module = StagedBidAtCostPSM(network_rules=rules)
    with tempfile.TemporaryDirectory() as temporary:
        module.configure_run(
            output_dir=Path(temporary),
            storage_cost=FlatStorageCostDefinition(),
            balancing=balancing,
            expected_balancing_identity=(balancing.id, balancing.version),
            ledger_detail="summary",
        )
        return module.run(model_input)


def wind(name: str, capacity: float = 10.0) -> DispatchResource:
    return DispatchResource(name, "onshore", "vre", capacity, 0.0, (1.0,))


def gas(srmc: float = 80.0, capacity: float = 10.0) -> DispatchResource:
    return DispatchResource("gas", "CCGT", "thermal", capacity, srmc, (1.0,))


class EconomicDecPricingTests(unittest.TestCase):
    def test_curtailment_does_not_depend_on_the_asset_name(self) -> None:
        # Ahead: wind 10 at GBP 0 and gas 10 at GBP 80; realised demand is 3 lower.
        costs = {}
        for name in ("aa_wind", "zz_wind"):
            result = run_staged(psm_input((wind(name), gas()), forecast=20.0, actual=17.0))
            dispatch = result.extensions["final_dispatch_mwh_by_physical_asset"]
            self.assertAlmostEqual(dispatch["gas"], 7.0)
            self.assertAlmostEqual(dispatch[name], 10.0)
            costs[name] = result.total_operational_cost_gbp
        self.assertAlmostEqual(costs["aa_wind"], 560.0)
        self.assertAlmostEqual(costs["zz_wind"], 560.0)

    def test_legacy_rule_shows_the_asset_id_dependence(self) -> None:
        legacy = {
            name: run_staged(psm_input((wind(name), gas()), forecast=20.0, actual=17.0), LEGACY)
            for name in ("aa_wind", "zz_wind")
        }
        self.assertAlmostEqual(legacy["aa_wind"].total_operational_cost_gbp, 800.0)
        self.assertAlmostEqual(legacy["zz_wind"].total_operational_cost_gbp, 560.0)

    def test_decremented_thermal_unit_keeps_no_windfall(self) -> None:
        clearing = 80.0
        for rules, expected_profit in ((ECONOMIC, 0.0), (LEGACY, 3.0 * 80.0)):
            with self.subTest(rules=rules.rule_set_id):
                result = run_staged(
                    psm_input((wind("zz_wind"), gas()), forecast=20.0, actual=17.0), rules
                )
                income = result.market_income_gbp_by_agent["gas"]
                variable_cost = result.generation_mwh_by_asset["gas"] * 80.0
                undecremented_profit = 10.0 * clearing - 10.0 * 80.0
                self.assertAlmostEqual(income - variable_cost - undecremented_profit, expected_profit)

    def test_imports_are_decremented_before_cheaper_gas(self) -> None:
        imports = DispatchResource("import:fr", "interconnector_import", "import", 5.0, 90.0, (1.0,),
                                   extensions={"agent_id": "interconnector:fr"})
        result = run_staged(psm_input((wind("wind"), gas(), imports), forecast=25.0, actual=22.0))
        dispatch = result.extensions["final_dispatch_mwh_by_physical_asset"]
        self.assertAlmostEqual(dispatch["import:fr"], 2.0)
        self.assertAlmostEqual(dispatch["gas"], 10.0)
        self.assertAlmostEqual(dispatch["wind"], 10.0)

    def test_storage_charges_before_wind_is_curtailed(self) -> None:
        battery = StorageDispatchResource("battery", "1c", 5.0, 5.0, 10.0, 0.9, 0.9, 5.0, 1.0)
        result = run_staged(psm_input((wind("wind"), gas()), forecast=10.0, actual=7.0, storage=(battery,)))
        dispatch = result.extensions["final_dispatch_mwh_by_physical_asset"]
        self.assertAlmostEqual(dispatch["wind"], 10.0)
        self.assertAlmostEqual(dispatch["battery"], -3.0)

    def test_nuclear_is_decremented_last(self) -> None:
        nuclear = DispatchResource("nuclear", "Nuclear", "thermal", 10.0, 10.0, (1.0,))
        result = run_staged(psm_input((wind("wind"), nuclear, gas(capacity=2.0)), forecast=22.0, actual=15.0))
        dispatch = result.extensions["final_dispatch_mwh_by_physical_asset"]
        # Surplus 7: gas (GBP 80) first, then wind (GBP 0); nuclear (10-100) untouched.
        self.assertAlmostEqual(dispatch.get("gas", 0.0), 0.0)
        self.assertAlmostEqual(dispatch["wind"], 5.0)
        self.assertAlmostEqual(dispatch["nuclear"], 10.0)

    def test_equal_price_assets_share_pro_rata_under_any_names(self) -> None:
        for first, second in (("w_a", "w_b"), ("w_b", "w_a")):
            result = run_staged(
                psm_input((wind(first, 10.0), wind(second, 5.0)), forecast=15.0, actual=12.0)
            )
            dispatch = result.extensions["final_dispatch_mwh_by_physical_asset"]
            self.assertAlmostEqual(dispatch[first], 8.0)
            self.assertAlmostEqual(dispatch[second], 4.0)


class DecBidShapeTests(unittest.TestCase):
    def bids(self, rules=ECONOMIC, parameters=None):
        battery = StorageDispatchResource("battery", "1c", 5.0, 5.0, 10.0, 0.9, 0.9, 5.0, 1.0)
        nuclear = DispatchResource("nuclear", "Nuclear", "thermal", 10.0, 10.0, (1.0,))
        model_input = psm_input(
            (wind("wind"), gas(), nuclear), forecast=25.0, actual=25.0, storage=(battery,),
            parameters=parameters,
        )
        module = StagedBidAtCostPSM(network_rules=rules)
        module.configure_run(
            output_dir=None, storage_cost=FlatStorageCostDefinition(),
            balancing=CopperplateBalancing(),
            expected_balancing_identity=(CopperplateBalancing.id, CopperplateBalancing.version),
            ledger_detail="off",
        )
        storage_models, soc = module._storage_models(model_input)
        offers = module._ahead_offers(model_input, 0, soc, storage_models)
        ahead = module.clear_ahead(AheadMarketInput(
            "run-dec", 2025, 0, "2025:0", 1.0, "forecast_only", 25.0, offers, dict(soc),
        ))
        bids = module._flexibility_bids(model_input, 0, ahead, soc, storage_models)
        return {bid.bid_id.split(":", 3)[3]: bid for bid in bids}

    def test_prices_follow_the_shared_table(self) -> None:
        support = '{"onshore": 45.0}'
        bids = self.bids(parameters={"market.policy_support_gbp_per_mwh_by_technology": support})
        self.assertAlmostEqual(bids["down:gas"].price_gbp_per_mwh, 80.0)
        self.assertAlmostEqual(bids["down:wind"].price_gbp_per_mwh, -45.0)
        self.assertAlmostEqual(bids["down:nuclear"].price_gbp_per_mwh, 10.0 - 100.0)
        storage_down = bids["down-storage:battery"].price_gbp_per_mwh
        up_prices = [bid.price_gbp_per_mwh for bid in bids.values() if bid.direction == "up"]
        self.assertAlmostEqual(storage_down, 5.0 * 0.9 * 0.9)
        self.assertLessEqual(storage_down, min(up_prices))
        self.assertLessEqual(storage_down, 5.0)  # its own up price (flat storage cost 5)

    def test_legacy_dec_prices_are_zero(self) -> None:
        bids = self.bids(LEGACY)
        self.assertTrue(all(bid.price_gbp_per_mwh == 0.0 for bid in bids.values() if bid.direction == "down"))

    def test_dec_multiplier_cannot_exceed_bid_multiplier(self) -> None:
        with self.assertRaises(NetworkMethodRulesError):
            dec_pricing_inputs({"market.bid_multiplier": 1.0, "market.dec_multiplier": 1.2})
        with self.assertRaises(ParameterValidationError):
            resolve_scheme_c_parameters(BASELINE, {"market.dec_multiplier": 1.2})
        with self.assertRaises(ParameterValidationError):
            resolve_scheme_c_parameters(BASELINE, {"market.policy_support_gbp_per_mwh_by_technology": "[1, 2]"})
        inputs = dec_pricing_inputs({"market.bid_multiplier": 1.5, "market.dec_multiplier": 1.2})
        self.assertEqual(inputs.dec_multiplier, 1.2)
        self.assertEqual(inputs.inflexible_premium_gbp_per_mwh_by_technology, {"nuclear": 100.0})

    def test_rule_record_names_the_shared_table(self) -> None:
        record = ECONOMIC.record()
        self.assertEqual(record["rules"]["downward_table"]["nuclear_dec_premium_gbp_per_mwh"], 100.0)
        self.assertNotEqual(ECONOMIC.sha256, LEGACY.sha256)
        self.assertEqual(network_method_rules.dec_class("thermal", "Nuclear"), "nuclear")


class ZonalEqualPriceRenamingTests(unittest.TestCase):
    def test_equal_price_winds_keep_their_curtailment_when_renamed(self) -> None:
        results = []
        for first, second in (("wind-a", "wind-b"), ("wind-z", "wind-a")):
            bids = (
                zonal_bid(f"down-{first}", first, "gb", "down", 10.0, 0.0, baseline_mwh=10.0, resource_class="vre"),
                zonal_bid(f"down-{second}", second, "gb", "down", 5.0, 0.0, baseline_mwh=5.0, resource_class="vre"),
                zonal_bid("down-gas", "gas", "gb", "down", 5.0, 80.0, baseline_mwh=5.0),
            )
            declaration = zonal_declaration(
                {"gb": 14.0}, {first: 10.0, second: 5.0, "gas": 5.0},
                {first: "gb", second: "gb", "gas": "gb"}, bids,
                classes={first: "vre", second: "vre", "gas": "thermal"},
            )
            dispatch = production_solution(declaration)["final_dispatch_mwh_by_asset"]
            results.append((dispatch[first], dispatch[second], dispatch["gas"]))
        for first, second, gas_mwh in results:
            # Surplus 6: gas (GBP 80) first, then the 1 MWh left shared 10:5.
            self.assertAlmostEqual(gas_mwh, 0.0, places=6)
            self.assertAlmostEqual(first, 10.0 - 1.0 * 10.0 / 15.0, places=6)
            self.assertAlmostEqual(second, 5.0 - 1.0 * 5.0 / 15.0, places=6)


if __name__ == "__main__":
    unittest.main()
