"""P0-8b M6 review: the shared dec class order at an equal rounded price.

The storage dec price is capped at the period's lowest inc price.  VRE up bids
(GBP 0) exist whenever realised VRE exceeds its ahead schedule, so the cap is
usually GBP 0 and the battery tied with unsubsidised wind; the old
storage-after-generation tie rule then curtailed wind while the battery stayed
idle.  In the down direction storage charging now comes before run-of-river,
VRE and nuclear at an equal 0.01-rounded price, in copperplate and in the
zonal LP; in the up direction storage still comes after generation (Q8).
"""

from __future__ import annotations

import unittest

from gridform_core import network_method_rules
from gridform_core.builtin.scheme_c_1000twh.copperplate_balancing import _price_groups
from gridform_core.v2.contracts import StorageDispatchResource
from gridform_validation.zonal_case_generator import production_solution
from gridform_validation.zonal_oracle import compare_zonal_solutions, solve_zonal_oracle
from tests.network_toys import zonal_bid, zonal_declaration
from tests.test_network_dec_pricing import psm_input, run_staged, wind


def battery() -> StorageDispatchResource:
    return StorageDispatchResource("battery", "1c", 5.0, 5.0, 10.0, 0.9, 0.9, 5.0, 1.0)


def _bid(bid_id: str, direction: str, price: float, resource_class: str, technology: str = ""):
    bid = zonal_bid(bid_id, bid_id, "gb", direction, 1.0, price, resource_class=resource_class)
    if technology:
        from dataclasses import replace

        bid = replace(bid, technology=technology)
    return bid


class CopperplateDecClassOrderTests(unittest.TestCase):
    def test_battery_charges_before_wind_with_a_zero_priced_inc(self) -> None:
        # Wind 15 MW available, ahead schedule 10: a GBP 0 wind up bid of 5 MWh
        # caps the storage dec price at 0, the same as unsubsidised wind.
        for capacity in (10.0, 15.0):
            with self.subTest(wind_capacity=capacity):
                result = run_staged(psm_input(
                    (wind("wind", capacity),), forecast=10.0, actual=7.0, storage=(battery(),)
                ))
                dispatch = result.extensions["final_dispatch_mwh_by_physical_asset"]
                self.assertAlmostEqual(dispatch["wind"], 10.0)
                self.assertAlmostEqual(dispatch["battery"], -3.0)

    def test_down_groups_use_the_rounded_band_then_the_class_order(self) -> None:
        bids = [
            _bid("nuclear", "down", 0.0, "thermal", "Nuclear"),
            _bid("wind", "down", 0.004, "vre"),
            _bid("hydro", "down", 0.0, "hydro"),
            _bid("store", "down", 0.0, "storage"),
            _bid("gas", "down", 0.001, "thermal"),
            _bid("import", "down", 0.0, "import"),
            _bid("dear", "down", 5.0, "vre"),
        ]
        order = [
            [bid.bid_id for bid in group]
            for group in _price_groups(bids, descending=True, tie_rule="pro_rata_v1")
        ]
        self.assertEqual(
            order, [["dear"], ["gas"], ["import"], ["store"], ["hydro"], ["wind"], ["nuclear"]]
        )

    def test_up_groups_keep_storage_after_generation(self) -> None:
        bids = [
            _bid("store", "up", 10.0, "storage"),
            _bid("gas", "up", 10.0, "thermal"),
            _bid("wind", "up", 0.0, "vre"),
        ]
        order = [
            [bid.bid_id for bid in group]
            for group in _price_groups(bids, descending=False, tie_rule="pro_rata_v1")
        ]
        self.assertEqual(order, [["wind"], ["gas"], ["store"]])

    def test_rule_record_names_the_class_order(self) -> None:
        rules = network_method_rules.ECONOMIC.record()["rules"]
        self.assertEqual(rules["dec_class_order"], list(network_method_rules.DEC_CLASSES))
        self.assertEqual(
            network_method_rules.dec_rank(resource_class="export"),
            network_method_rules.DEC_CLASSES.index("import"),
        )


class ZonalDecClassOrderTests(unittest.TestCase):
    STORAGE = {
        "battery": {
            "charge_power_mw": 5.0,
            "discharge_power_mw": 5.0,
            "energy_capacity_mwh": 10.0,
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
            "bid_contract": "convex_net_power_v1",
        }
    }

    def declaration(self, extra_bids=(), extra_schedule=None, extra_classes=None, demand=7.0):
        bids = (
            zonal_bid("down-wind", "wind", "gb", "down", 10.0, 0.0, baseline_mwh=10.0,
                      resource_class="vre"),
            zonal_bid("up-wind", "wind", "gb", "up", 5.0, 0.0, baseline_mwh=10.0,
                      resource_class="vre"),
            zonal_bid("down-battery", "battery", "gb", "down", 5.0, 0.0, resource_class="storage"),
            *extra_bids,
        )
        schedule = {"wind": 10.0, "battery": 0.0, **(extra_schedule or {})}
        classes = {"wind": "vre", "battery": "storage", **(extra_classes or {})}
        return zonal_declaration(
            {"gb": demand}, schedule, {asset: "gb" for asset in schedule}, bids,
            availability_mwh={"wind": 15.0, "battery": 0.0,
                              **{asset: value for asset, value in (extra_schedule or {}).items()}},
            classes=classes, storage=self.STORAGE, opening_soc={"battery": 0.0},
        )

    def test_lp_charges_the_battery_before_curtailing_wind_and_matches_the_oracle(self) -> None:
        declaration = self.declaration()
        production = production_solution(declaration)
        self.assertAlmostEqual(production["final_dispatch_mwh_by_asset"]["wind"], 10.0, places=6)
        self.assertAlmostEqual(production["final_dispatch_mwh_by_asset"]["battery"], -3.0, places=6)
        oracle = solve_zonal_oracle(declaration)
        self.assertTrue(compare_zonal_solutions(declaration, production, oracle)["passed"])
        self.assertAlmostEqual(oracle["final_dispatch_mwh_by_asset"]["battery"], -3.0, places=6)

    def test_lp_reduces_run_of_river_before_wind_and_wind_before_nuclear(self) -> None:
        extra = (
            zonal_bid("down-hydro", "hydro", "gb", "down", 2.0, 0.0, baseline_mwh=2.0,
                      resource_class="hydro"),
            zonal_bid("down-nuclear", "nuclear", "gb", "down", 10.0, 0.0, baseline_mwh=10.0,
                      resource_class="thermal"),
        )
        from dataclasses import replace

        extra = (extra[0], replace(extra[1], technology="Nuclear"))
        # Schedule 22, demand 10: surplus 12 = battery 5, then hydro 2, then
        # wind 5; nuclear untouched.
        declaration = self.declaration(
            extra, {"hydro": 2.0, "nuclear": 10.0}, {"hydro": "hydro", "nuclear": "thermal"},
            demand=10.0,
        )
        production = production_solution(declaration)
        dispatch = production["final_dispatch_mwh_by_asset"]
        self.assertAlmostEqual(dispatch["battery"], -5.0, places=6)
        self.assertAlmostEqual(dispatch["hydro"], 0.0, places=6)
        self.assertAlmostEqual(dispatch["wind"], 5.0, places=6)
        self.assertAlmostEqual(dispatch["nuclear"], 10.0, places=6)
        oracle = solve_zonal_oracle(declaration)
        self.assertTrue(compare_zonal_solutions(declaration, production, oracle)["passed"])


if __name__ == "__main__":
    unittest.main()
