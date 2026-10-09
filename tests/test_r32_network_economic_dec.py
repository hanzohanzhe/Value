"""R3-2 (DECISIONS A19, A22, A22a, A24-3): economic dec order of the network models.

The staged / zonal balancing used to reduce a gas or biomass unit in one block
before VRE (fuel at its avoided cost c > 0, VRE at GBP 0).  The maintained rule
set network-economic-v2 splits that dec at minimum stable generation: the
running range keeps c and so is reduced before VRE; the shutdown segment is
priced at the net saving a(H) = c - S(H)/(m H) and competes with VRE on price,
after VRE at an equal band; below the minimum down time it is a last resort.
The toys mirror the default PSM's R1-2 toys (tests/test_r12_economic_downward_order.py)
in the staged copperplate path, in a two-zone LP checked against the
independent PuLP/CBC oracle, and in a live staged zonal Run.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core import network_method_rules
from gridform_core.builtin.scheme_c_1000twh import native_corrected
from gridform_core.builtin.scheme_c_1000twh.copperplate_balancing import (
    CopperplateBalancing,
    _price_groups,
)
from gridform_core.builtin.scheme_c_1000twh.staged_psm import StagedBidAtCostPSM
from gridform_core.network_method_rules import (
    ECONOMIC,
    ECONOMIC_P08,
    dec_pricing_inputs,
    thermal_dec_segments,
)
from gridform_core.staged_market_contracts import AheadMarketInput
from gridform_core.v2.contracts import (
    AssetStateV2,
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
)
from gridform_core.zonal_contracts import (
    CutsetMember,
    ETYSBoundary,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZonalAssetMapping,
    ZonalDemand,
    ZonalNetworkPack,
)
from gridform_core.zonal_redispatch import ZonalRedispatchBalancing
from gridform_validation.zonal_case_generator import production_solution
from gridform_validation.zonal_oracle import compare_zonal_solutions, solve_zonal_oracle
from tests.network_toys import zonal_bid, zonal_declaration, zonal_pack
from tests.test_network_dec_pricing import ECONOMICS
from tests.test_prompt95_staged_copperplate import FlatStorageCostDefinition

ROOT = Path(__file__).resolve().parents[1]

CORRECTION_ID = "r32.network-economic-downward-order"


def ocgt(capacity: float = 20.0, cost: float = 75.0) -> DispatchResource:
    return DispatchResource("ocgt", "OCGT", "thermal", capacity, cost, (1.0,))


def ccgt(capacity: float = 20.0, cost: float = 55.0) -> DispatchResource:
    return DispatchResource("ccgt", "CCGT", "thermal", capacity, cost, (1.0,))


def wind(capacity: float = 30.0) -> DispatchResource:
    return DispatchResource("wind", "onshore", "vre", capacity, 0.0, (1.0,))


def chronological_input(
    resources: tuple[DispatchResource, ...],
    forecast: tuple[float, ...],
    actual: tuple[float, ...],
    *,
    period_hours: float = 1.0,
) -> PSMInput:
    assets = tuple(
        AssetStateV2(row.asset_id, row.technology, row.capacity_mw, extensions=ECONOMICS)
        for row in resources
    )
    data = ChronologicalPSMData(
        tuple(f"2025:{index}" for index in range(len(actual))), actual, resources, (), 17_000.0,
        terminal_soc_rule="free", extensions={"forecast_demand_mwh": forecast},
    )
    return PSMInput(
        "run-r32", 2025, "fixture-pack", OperatingState(2025, assets, ()), period_hours,
        {"market.bid_multiplier": 1.0}, chronology=data,
    )


def surplus_then(surplus_periods: int, deficit_periods: int, *, first=(50.0, 25.0)):
    """Period 0 is balanced down (forecast 50, realised 25); then
    ``surplus_periods`` forecasts that wind covers (10) and ``deficit_periods``
    that need thermal output (50)."""

    forecast = (first[0],) + (10.0,) * surplus_periods + (50.0,) * deficit_periods
    actual = (first[1],) + (10.0,) * surplus_periods + (50.0,) * deficit_periods
    return forecast, actual


def run_staged(model_input: PSMInput, rules=ECONOMIC):
    balancing = CopperplateBalancing(tie_rule="pro_rata_v1")
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


def dispatch(result) -> dict[str, float]:
    return dict(result.extensions["final_dispatch_mwh_by_physical_asset"])


class SegmentRuleTests(unittest.TestCase):
    def segments(self, technology, horizon, cost, scheduled=20.0, rules=ECONOMIC, asset_id="unit"):
        return thermal_dec_segments(
            rules, resource_class="thermal", technology=technology, asset_id=asset_id,
            scheduled_mwh=scheduled, dec_price_gbp_per_mwh=cost, expected_downtime_h=horizon,
        )

    def test_net_saving_equals_the_default_psm_formula(self) -> None:
        table = native_corrected.restart_parameters()
        for technology, name, cost, horizons in (
            ("CCGT", "CCGT", 55.07, (3.0, 6.0, 12.0, 49.0)),
            ("OCGT", "OCGT", 75.0, (0.5, 2.0, 3.0, 5.0)),
            ("bio_and_waste", "biomass", 40.0, (6.0, 10.0)),
        ):
            for horizon in horizons:
                with self.subTest(technology=technology, horizon=horizon):
                    segments = self.segments(technology, horizon, cost)
                    params = table[name]
                    self.assertEqual(segments.technology, name)
                    self.assertAlmostEqual(
                        segments.net_saving_gbp_per_mwh, params.net_saving(cost, horizon)
                    )
                    self.assertAlmostEqual(
                        segments.net_saving_gbp_per_mwh,
                        cost - params.restart_cost(horizon) / (params.min_stable_fraction * horizon),
                    )
                    self.assertAlmostEqual(segments.shutdown_mwh, params.min_stable_fraction * 20.0)
                    self.assertAlmostEqual(segments.running_mwh + segments.shutdown_mwh, 20.0)
        # Worked numbers of the R1-2 toys: OCGT 75 at H = 5 h / 3 h, with the
        # 2025 GBP restart cost 175.7 GBP/MW (A24-4; 170 in 2024 GBP).
        self.assertAlmostEqual(self.segments("OCGT", 5.0, 75.0).net_saving_gbp_per_mwh, 75.0 - 175.7 / 2.5)
        self.assertAlmostEqual(self.segments("OCGT", 5.0, 75.0).net_saving_gbp_per_mwh, 4.72)
        self.assertAlmostEqual(self.segments("OCGT", 3.0, 75.0).net_saving_gbp_per_mwh, 75.0 - 351.4 / 3.0)

    def test_classes_and_labels(self) -> None:
        cases = (
            ("OCGT", 5.0, "fuel_shutdown", "thermal_shutdown_net_saving"),
            ("OCGT", 3.0, "fuel_shutdown", "thermal_shutdown_after_vre"),
            ("OCGT", 4.0, "fuel_shutdown", "thermal_shutdown_after_vre"),  # a = 75 - 87.85 < 0
            ("CCGT", 5.5, "fuel_shutdown_last_resort", "thermal_shutdown_below_min_down_time"),
            ("CCGT", 6.0, "fuel_shutdown", "thermal_shutdown_net_saving"),
        )
        for technology, horizon, dec_class, label in cases:
            with self.subTest(technology=technology, horizon=horizon):
                segments = self.segments(technology, horizon, 75.0)
                self.assertEqual(segments.shutdown_class, dec_class)
                self.assertEqual(segments.shutdown_segment, label)

    def test_only_gas_and_biomass_fuel_units_are_split(self) -> None:
        self.assertIsNone(self.segments("Nuclear", 6.0, 10.0))
        self.assertIsNone(self.segments("Hydro_natural_flow", 6.0, 10.0))
        self.assertIsNone(self.segments("dsr", 6.0, 10.0))
        self.assertIsNone(self.segments("OCGT", 6.0, 75.0, rules=ECONOMIC_P08))
        self.assertIsNone(self.segments("OCGT", 6.0, 75.0, rules=network_method_rules.LEGACY))
        # Technology names of the canonical chronology (canonical_psm_data).
        self.assertEqual(network_method_rules.restart_technology("gas"), "CCGT")
        self.assertEqual(network_method_rules.restart_technology("gas", "OCGT_peaker"), "OCGT")
        self.assertEqual(network_method_rules.restart_technology("CCGT"), "CCGT")
        self.assertEqual(network_method_rules.restart_technology("OCGT"), "OCGT")
        self.assertEqual(network_method_rules.restart_technology("bio_and_waste"), "biomass")
        self.assertIsNone(network_method_rules.restart_technology("onshore"))

    def test_last_resort_price_is_one_band_below_every_other_dec(self) -> None:
        self.assertEqual(network_method_rules.last_resort_price(-385.0, [0.0, 55.0]), -385.0)
        self.assertEqual(network_method_rules.last_resort_price(18.4, [0.0, 55.0]), -0.01)
        self.assertEqual(network_method_rules.last_resort_price(18.4, [-89.996, 55.0]), -90.01)
        self.assertEqual(network_method_rules.last_resort_price(18.4, []), 18.4)

    def test_horizon_counts_the_current_and_following_forecast_surplus_periods(self) -> None:
        horizon = network_method_rules.shutdown_horizon_hours(
            (50.0, 10.0, 10.0, 50.0, 10.0), (30.0,) * 5, 0.5
        )
        self.assertEqual(horizon, (1.5, 1.0, 0.5, 1.0, 0.5))

    def test_rule_identity(self) -> None:
        record = ECONOMIC.record()
        self.assertEqual(record["rule_set_id"], "network-economic-v2")
        rules = record["rules"]
        self.assertEqual(rules["thermal_shutdown"], "restart_cost_vs_avoided_cost_v1")
        self.assertEqual(rules["dec_class_order"], list(network_method_rules.DEC_CLASSES))
        self.assertEqual(rules["restart_table"]["sha256"], native_corrected.restart_table_sha256())
        # The P0-8b rule set is kept byte for byte (sha recorded in C7/C8 before R3-2).
        self.assertEqual(
            ECONOMIC_P08.sha256,
            "3f858ac96dea3d17ecc019b14635fdf06dd17efc1818f42b25206e8d5c7e922f",
        )
        self.assertEqual(ECONOMIC_P08.record()["rules"]["dec_class_order"], list(network_method_rules.DEC_CLASSES_P08))
        self.assertNotIn("thermal_shutdown", ECONOMIC_P08.record()["rules"])
        self.assertIs(StagedBidAtCostPSM()._network_rules, ECONOMIC)

    def test_copperplate_groups_put_a_shutdown_after_vre_at_an_equal_band(self) -> None:
        def bid(bid_id, price, resource_class, dec_class=None):
            row = zonal_bid(bid_id, bid_id, "gb", "down", 1.0, price, resource_class=resource_class)
            if dec_class:
                row = replace(row, provenance={**row.provenance, "dec_class": dec_class})
            return row

        bids = [
            bid("last", -0.01, "thermal", "fuel_shutdown_last_resort"),
            bid("nuclear", 0.0, "thermal", "nuclear"),
            bid("tie", 0.004, "thermal", "fuel_shutdown"),
            bid("wind", 0.0, "vre"),
            bid("saving", 7.0, "thermal", "fuel_shutdown"),
            bid("running", 75.0, "thermal", "fuel"),
        ]
        order = [
            [row.bid_id for row in group]
            for group in _price_groups(bids, descending=True, tie_rule="pro_rata_v1")
        ]
        self.assertEqual(order, [["running"], ["saving"], ["wind"], ["tie"], ["nuclear"], ["last"]])


class StagedCopperplateToyTests(unittest.TestCase):
    """The R1-2 toys: OCGT 20 MW and wind 30 MW, 25 MWh to reduce."""

    def test_a_shutdown_before_wind_when_the_saving_exceeds_the_restart_cost(self) -> None:
        # H = 5 h: a = 75 - 170 / (0.5 x 5) = 7 > 0 (restart GBP 1,700 < saving GBP 3,750).
        forecast, actual = surplus_then(4, 0)
        result = run_staged(chronological_input((ocgt(), wind()), forecast, actual))
        flows = dispatch(result)
        self.assertAlmostEqual(flows["ocgt"], 0.0)
        self.assertAlmostEqual(flows["wind"], 25.0 + 4 * 10.0)
        summary = result.extensions["downward_restart_economics"]
        self.assertEqual(summary["schema_version"], "value.network-downward-restart-economics/v1")
        self.assertEqual(summary["down_regulation_periods"], 1)
        self.assertAlmostEqual(summary["mean_horizon_hours"], 5.0)
        reduced = summary["reduced_mwh_by_segment"]
        self.assertAlmostEqual(reduced["thermal_running_range"], 10.0)
        self.assertAlmostEqual(reduced["thermal_shutdown_net_saving"], 10.0)
        self.assertAlmostEqual(reduced["vre"], 5.0)

    def test_b_wind_before_a_shutdown_when_the_restart_cost_is_larger(self) -> None:
        # H = 3 h: a = 75 - 170 / 1.5 = -38.3 (restart GBP 3,400 > saving GBP 2,250).
        forecast, actual = surplus_then(2, 2)
        result = run_staged(chronological_input((ocgt(), wind()), forecast, actual))
        flows = dispatch(result)
        self.assertAlmostEqual(flows["ocgt"], 10.0 + 2 * 20.0)
        self.assertAlmostEqual(flows["wind"], 15.0 + 2 * 10.0 + 2 * 30.0)
        summary = result.extensions["downward_restart_economics"]
        self.assertAlmostEqual(summary["mean_horizon_hours"], 3.0)
        self.assertAlmostEqual(summary["reduced_mwh_by_segment"]["thermal_running_range"], 10.0)
        self.assertAlmostEqual(summary["reduced_mwh_by_segment"]["vre"], 15.0)
        self.assertAlmostEqual(summary["reduced_mwh_by_segment"]["thermal_shutdown_after_vre"], 0.0)

    def test_p08_rules_reduced_the_whole_unit_before_wind(self) -> None:
        forecast, actual = surplus_then(2, 2)
        result = run_staged(chronological_input((ocgt(), wind()), forecast, actual), ECONOMIC_P08)
        self.assertAlmostEqual(dispatch(result)["ocgt"], 0.0 + 2 * 20.0)
        self.assertNotIn("downward_restart_economics", result.extensions)

    def test_c_reduction_inside_the_running_range_comes_before_wind(self) -> None:
        resources = (ccgt(70.0), wind())
        result = run_staged(chronological_input(resources, (100.0,), (80.0,)))
        flows = dispatch(result)
        self.assertAlmostEqual(flows["ccgt"], 50.0)
        self.assertAlmostEqual(flows["wind"], 30.0)

    def test_below_the_minimum_down_time_a_shutdown_is_the_last_resort(self) -> None:
        # CCGT c = 55 at H = 3 h < 6 h: running 10, then all wind, then 3 of the shutdown.
        resources = (ccgt(20.0), wind(5.0))
        forecast, actual = (25.0, 1.0, 1.0, 25.0), (7.0, 1.0, 1.0, 25.0)
        result = run_staged(chronological_input(resources, forecast, actual))
        flows = dispatch(result)
        self.assertAlmostEqual(flows["ccgt"], 7.0 + 20.0)
        self.assertAlmostEqual(flows["wind"], 0.0 + 1.0 + 1.0 + 5.0)
        reduced = result.extensions["downward_restart_economics"]["reduced_mwh_by_segment"]
        self.assertAlmostEqual(reduced["thermal_shutdown_below_min_down_time"], 3.0)

    def test_bids_carry_the_segment_evidence(self) -> None:
        model_input = chronological_input((ocgt(), wind()), (50.0,), (25.0,))
        module = StagedBidAtCostPSM()
        offers = module._ahead_offers(model_input, 0, {}, {})
        ahead = module.clear_ahead(AheadMarketInput(
            "run-r32", 2025, 0, "2025:0", 1.0, "forecast_only", 50.0, offers, {},
        ))
        bids = {
            bid.bid_id: bid
            for bid in module._flexibility_bids(model_input, 0, ahead, {}, {}, 0.5)
            if bid.direction == "down"
        }
        running = bids["balance:2025:0:down:ocgt"]
        shutdown = bids["balance:2025:0:down-shutdown:ocgt"]
        self.assertAlmostEqual(running.price_gbp_per_mwh, 75.0)
        self.assertAlmostEqual(running.extensions["available_mwh"], 10.0)
        self.assertEqual(running.provenance["dec_segment"], "thermal_running_range")
        self.assertAlmostEqual(shutdown.extensions["available_mwh"], 10.0)
        self.assertAlmostEqual(shutdown.provenance["net_saving_gbp_per_mwh"], 75.0 - 175.7 / 0.25)
        self.assertEqual(shutdown.provenance["dec_class"], "fuel_shutdown")
        self.assertEqual(shutdown.provenance["start_class"], "hot")
        self.assertAlmostEqual(shutdown.baseline_mw, 20.0)
        # Without a horizon the current period alone is the expected downtime.
        default = {
            bid.bid_id: bid
            for bid in module._flexibility_bids(model_input, 0, ahead, {}, {})
        }
        self.assertAlmostEqual(
            default["balance:2025:0:down-shutdown:ocgt"].provenance["expected_downtime_h"], 1.0
        )


def two_zone_case(horizon_h: float, rules=ECONOMIC) -> dict[str, object]:
    """North: OCGT 20 (c 75) and wind 30 scheduled ahead; south: 35 MWh of
    demand and a GBP 90 CCGT with 30 MWh of headroom; north demand 10.  The
    north-south boundary (15 MWh) forces the north down by 25 MWh although
    the national surplus is only 5."""

    pricing = dec_pricing_inputs({})
    bids = [
        zonal_bid("wind-down", "wind", "north", "down", 30.0, 0.0, baseline_mwh=30.0,
                  resource_class="vre"),
        zonal_bid("ccgt-up", "ccgt", "south", "up", 30.0, 90.0),
    ]
    dec_price = network_method_rules.resource_dec_price(
        rules, resource_class="thermal", technology="OCGT", marginal_cost_gbp_per_mwh=75.0,
        inputs=pricing,
    )
    segments = thermal_dec_segments(
        rules, resource_class="thermal", technology="OCGT", asset_id="ocgt",
        scheduled_mwh=20.0, dec_price_gbp_per_mwh=dec_price, expected_downtime_h=horizon_h,
    )
    if segments is None:
        bids.append(replace(
            zonal_bid("ocgt-down", "ocgt", "north", "down", 20.0, dec_price, baseline_mwh=20.0),
            technology="OCGT",
        ))
    else:
        bids.append(replace(
            zonal_bid("ocgt-down", "ocgt", "north", "down", segments.running_mwh, dec_price,
                      baseline_mwh=20.0),
            technology="OCGT",
            provenance={"resource_class": "thermal", "dec_class": "fuel"},
        ))
        bids.append(replace(
            zonal_bid("ocgt-down-shutdown", "ocgt", "north", "down", segments.shutdown_mwh,
                      segments.net_saving_gbp_per_mwh, baseline_mwh=20.0),
            technology="OCGT",
            provenance={"resource_class": "thermal", "dec_class": segments.shutdown_class},
        ))
    demand = {"north": 10.0, "south": 35.0}
    corridor = TransportCorridor("north-south", "north", "south", "from_to_positive")
    boundary = ETYSBoundary(
        "B_TEST", "Fixture boundary", (CutsetMember("north-south", 1),), 15.0, 15.0,
        reverse_limit_method="assumed_symmetric_from_forward",
    )
    return zonal_declaration(
        demand,
        {"wind": 30.0, "ocgt": 20.0, "ccgt": 0.0},
        {"wind": "north", "ocgt": "north", "ccgt": "south"},
        tuple(bids),
        pack=zonal_pack(demand, corridors=(corridor,), cutsets=(boundary,)),
        availability_mwh={"wind": 30.0, "ocgt": 20.0, "ccgt": 30.0},
        classes={"wind": "vre", "ocgt": "thermal", "ccgt": "thermal"},
        costs={"wind": 0.0, "ocgt": 75.0, "ccgt": 90.0},
    )


class TwoZoneLPTests(unittest.TestCase):
    def solve(self, declaration, *, exact_tie=False):
        production = production_solution(declaration)
        oracle = solve_zonal_oracle(declaration)
        comparison = compare_zonal_solutions(declaration, production, oracle)
        if exact_tie:
            # At an exact primary tie the production lock allowances (about
            # 1e-6 MWh here) may be spent by the stable phase; the comparison
            # classifies that as a tie-break difference, both audits pass.
            self.assertTrue(comparison["production_audit"]["passed"], comparison)
            self.assertTrue(comparison["oracle_audit"]["passed"], comparison)
            self.assertLess(comparison["maximum_mapping_gaps"]["final_dispatch_mwh_by_asset"], 1e-5)
        else:
            self.assertTrue(comparison["passed"], comparison)
        for asset, value in production["final_dispatch_mwh_by_asset"].items():
            self.assertAlmostEqual(oracle["final_dispatch_mwh_by_asset"][asset], value, places=5)
        return production["final_dispatch_mwh_by_asset"]

    def test_a_ocgt_shuts_before_wind_is_curtailed_behind_the_boundary(self) -> None:
        flows = self.solve(two_zone_case(5.0))
        self.assertAlmostEqual(flows["ocgt"], 0.0, places=6)
        self.assertAlmostEqual(flows["wind"], 25.0, places=6)
        self.assertAlmostEqual(flows["ccgt"], 20.0, places=6)

    def test_b_wind_is_curtailed_before_the_ocgt_shuts(self) -> None:
        flows = self.solve(two_zone_case(3.0))
        self.assertAlmostEqual(flows["ocgt"], 10.0, places=6)
        self.assertAlmostEqual(flows["wind"], 15.0, places=6)
        self.assertAlmostEqual(flows["ccgt"], 20.0, places=6)

    def test_equal_price_shutdown_waits_for_wind(self) -> None:
        # A shutdown whose net saving equals the wind dec price (GBP 0) is a
        # tie of the primary objective; the physical tie phase takes wind
        # (weight 3) before the shutdown (3.5), as A22's strict "a > 0".
        declaration = two_zone_case(4.0)
        for bid in declaration["bids"]:
            if bid["bid_id"] == "ocgt-down-shutdown":
                bid["price_gbp_per_mwh"] = 0.0
        flows = self.solve(declaration, exact_tie=True)
        self.assertAlmostEqual(flows["ocgt"], 10.0, places=5)
        self.assertAlmostEqual(flows["wind"], 15.0, places=5)

    def test_p08_rules_shut_the_whole_unit_first(self) -> None:
        flows = self.solve(two_zone_case(3.0, ECONOMIC_P08))
        self.assertAlmostEqual(flows["ocgt"], 0.0, places=6)
        self.assertAlmostEqual(flows["wind"], 25.0, places=6)


def _live_pack(north_demand, south_demand, limit) -> ZonalNetworkPack:
    periods = tuple(f"2025:{index}" for index in range(len(north_demand)))
    pack = ZonalNetworkPack(
        "r32-fixture-network",
        "",
        (
            NetworkZone("north", "North", "Fixture DSO", "England"),
            NetworkZone("south", "South", "Fixture DSO", "England"),
        ),
        (TransportCorridor("north-south", "north", "south", "from_to_positive"),),
        (
            ETYSBoundary(
                "B_TEST", "Fixture boundary", (CutsetMember("north-south", 1),), limit, limit,
                reverse_limit_method="source_declared_symmetric",
            ),
        ),
        (
            ZonalAssetMapping("wind", "north", "generator", "onshore", 1.0, "fixture"),
            ZonalAssetMapping("ocgt", "north", "generator", "OCGT", 1.0, "fixture"),
            ZonalAssetMapping("ccgt", "south", "generator", "CCGT", 1.0, "fixture"),
        ),
        ZonalDemand(
            periods,
            {"north": tuple(north_demand), "south": tuple(south_demand)},
            tuple(a + b for a, b in zip(north_demand, south_demand)),
        ),
        (),
        (),
        SpatialAudit((), {}, {}, 1e-9),
        "lossless_v1",
    )
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


class LiveZonalRunTests(unittest.TestCase):
    """The two-zone case through the staged PSM and the zonal LP module, with H
    computed by the PSM from the forecast and the declared wind availability."""

    def run_live(self, surplus_periods: int, deficit_periods: int):
        from tests.test_prompt101_staged_cem_integration import _run_contextual

        north = (10.0,) + (0.0,) * surplus_periods + (40.0,) * deficit_periods
        south = (35.0,) + (10.0,) * surplus_periods + (10.0,) * deficit_periods
        actual = tuple(a + b for a, b in zip(north, south))
        forecast = (50.0,) + actual[1:]
        resources = (
            DispatchResource("wind", "onshore", "vre", 30.0, 0.0, (1.0,),
                             extensions={"agent_id": "wind"}),
            DispatchResource("ocgt", "OCGT", "thermal", 20.0, 75.0, (1.0,),
                             extensions={"agent_id": "ocgt"}),
            # South CCGT at 100 GBP/MWh (90 before R3-3): only its role as the
            # dearer southern supply matters here.  With 90 and the 2025 GBP
            # OCGT restart cost (175.7), HiGHS dual simplex stops in the
            # physical_throughput phase with "optimal for the scaled model,
            # NOTSET in the unscaled model" (GF_ZONAL_SOLVER_FAILURE); the same
            # happens with S = 173-178 at 90, or with c = 80 and 95.  That is a
            # numerical fragility of the zonal LP, not of the dec rule; it is
            # recorded as an open issue in docs/dev/p0-reports/R3-3-*.md.
            DispatchResource("ccgt", "CCGT", "thermal", 30.0, 100.0, (1.0,),
                             extensions={"agent_id": "ccgt"}),
        )
        model_input = chronological_input(resources, forecast, actual)
        with tempfile.TemporaryDirectory() as temporary:
            psm = StagedBidAtCostPSM()
            balancing = ZonalRedispatchBalancing()
            psm.configure_run(
                output_dir=Path(temporary),
                storage_cost=FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=_live_pack(north, south, 15.0),
                zonal_demand_mode="network_pack_absolute_demand",
                ledger_detail="summary",
            )
            return _run_contextual(psm, balancing, model_input)

    def test_live_zonal_run_follows_the_restart_economics(self) -> None:
        for surplus, deficit, ocgt_period0, horizon in ((4, 0, 0.0, 5.0), (2, 2, 10.0, 3.0)):
            with self.subTest(horizon=horizon):
                result = self.run_live(surplus, deficit)
                flows = dispatch(result)
                self.assertAlmostEqual(flows["ocgt"], ocgt_period0 + deficit * 20.0, places=6)
                summary = result.extensions["downward_restart_economics"]
                self.assertEqual(summary["down_regulation_periods"], 1)
                self.assertAlmostEqual(summary["mean_horizon_hours"], horizon)
                self.assertEqual(
                    result.extensions["network_method_rules"]["rule_set_id"], "network-economic-v2"
                )


class MethodChangeTests(unittest.TestCase):
    """Q13: a method change of the corrected profile's network models."""

    def test_version_ledger_bump_requires_opt_in(self) -> None:
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        entry = ledger["modules"]["value-staged-bid-at-cost-psm"]
        bump = next(item for item in entry["bumps"] if item["package"] == "R3-2")
        self.assertEqual((bump["from"], bump["to"]), ("1.4.0", "1.5.0"))
        self.assertEqual(bump["correction_ids"], [CORRECTION_ID])
        self.assertTrue(bump["requires_user_opt_in"])
        self.assertEqual(entry["current_version"], StagedBidAtCostPSM.version)
        manifest = json.loads(
            (ROOT / "gridform_core" / "manifests" / "value-staged-bid-at-cost-psm.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], StagedBidAtCostPSM.version)

    def test_saved_study_with_the_previous_version_needs_confirmation(self) -> None:
        from gridform_core import revision_migration

        kind, reason = revision_migration._module_change_kind(
            "value-staged-bid-at-cost-psm", "1.4.0", "1.5.0"
        )
        self.assertEqual(kind, "method_upgrade_required")
        self.assertIn(CORRECTION_ID, reason)


if __name__ == "__main__":
    unittest.main()
