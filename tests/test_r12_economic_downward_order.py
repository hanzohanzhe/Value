"""Decisions A19/A22: the corrected down-regulation order weighs restart cost against avoided cost.

P0-6 S7 read P3-03 as "always reduce thermal before VRE"; A19 withdrew that.
In the corrected rule set (``r12.economic-downward-order``) a gas or biomass
unit is split at minimum stable generation (``m x`` its accepted output):

* running range (above ``m x P``): no restart, saves ``c`` (fuel + carbon +
  VOM) per MWh, so it is reduced before VRE (cost 0);
* shutdown segment (below ``m x P``, down to the ramp floor): net saving
  ``a(H) = c - S(H)/(m H)`` with restart cost ``S`` per MW of capacity and
  expected downtime ``H`` (removing 1 MW of output from units at minimum
  stable generation shuts ``1/m`` MW of capacity; A22a); reduced before VRE
  only when ``a > 0``, after VRE otherwise, and only as a last resort when
  ``H`` is below the minimum down time.

The thesis (doctoral) rule set keeps its ascending curtail-cost order.
"""

from __future__ import annotations

import contextlib
import json
import os
import unittest
import unittest.mock
from pathlib import Path

import numpy as np

from gridform_core.builtin.scheme_c_1000twh import native_corrected as corrected
from gridform_core.builtin.scheme_c_1000twh.kernel_injection import _Bound
from gridform_core.builtin.scheme_c_1000twh.native_market_rules import (
    CORRECTED,
    DOCTORAL,
    FIELD_CORRECTIONS,
)
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel

CORRECTION_ID = "r12.economic-downward-order"
ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def rules_scope(rules, outlook=None):
    saved = os.environ.get("PHYSICAL_PERIOD_HOURS")
    os.environ["PHYSICAL_PERIOD_HOURS"] = "0.5"
    kernel._P06_STATE.reset(rules)
    kernel._P06_STATE.outlook = outlook
    try:
        yield
    finally:
        kernel._P06_STATE.reset()
        if saved is None:
            os.environ.pop("PHYSICAL_PERIOD_HOURS", None)
        else:
            os.environ["PHYSICAL_PERIOD_HOURS"] = saved


def wind(available, name="wind"):
    asset = kernel.ExpensiverenewableGenerator(
        name, 0.0001, 0, 0, 0, 0, 0, electrolyzer_cost=0, energy_efficiency=0.65,
        electrolyzer_limit=0, rampup_rate=0, capacity_multiplier=1,
    )
    asset.capacity_limit = available
    asset.curtail_cost = 0
    return asset


def gas(name, fuel, capacity, alter, previous):
    # GasGenerator(name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit,
    #              startup_cost, carbon_intensity, capital_cost, carbon_price, fuel_cost,
    #              real_gen_energy, unit_time_cost): gen_cost = fuel here.
    return kernel.GasGenerator(name, 0.0, 10.0, 0, capacity, alter, 0, 0, 0, 0, fuel, previous, 0)


def biomass(capacity, alter, previous, fuel=85.0):
    return kernel.BiomassGenerator(
        "bio_and_waste", 0.0, 3, 0, capacity, alter, 0, 1000, 0, 0, 0, 0, fuel, previous, 0,
    )


def electrolyzer():
    return kernel.Electrolyzer("electrolyzer", 0, 0, 0.65, 1000, 0, 0, 0)


def stack(units, schedule, need, horizon_h, tally=None):
    accepted = [[unit, unit.gen_cost, power, unit.curtail_cost] for unit, power in schedule]
    last = [(unit, unit.curtail_cost, unit.real_gen_energy) for unit, _ in schedule]
    gen_list = [[unit, power] for unit, power in schedule]
    remaining, fees, reductions = corrected.economic_downward_stack(
        accepted, last, need, gen_list, horizon_h=horizon_h, tally=tally)
    return remaining, reductions, gen_list


def output(gen_list, asset):
    return sum(float(row[1]) for row in gen_list if row[0] is asset)


class EconomicDownwardOrderTests(unittest.TestCase):
    """Trigger fixture of r12.economic-downward-order: the three toys of the task."""

    def test_a_fuel_saving_above_restart_cost_reduces_thermal_first(self):
        # OCGT c = 75, S = 175.7 (2025 GBP, A24-4), m = 0.5, minimum down time
        # 0.5 h; H = 5 h (10 surplus periods): removing the last 10 MW of
        # output shuts 20 MW of capacity, restart 175.7 x 20 = 3,514 < saving
        # 75 x 10 x 5 = 3,750; a = 75 - 175.7/(0.5 x 5) = 4.72 > 0, so the
        # shutdown precedes wind.
        ocgt, vre = gas("OCGT", 75.0, 50.0, 50.0, 20.0), wind(30.0)
        tally = corrected.DownwardTally()
        remaining, reductions, gen_list = stack([ocgt, vre], [(ocgt, 20.0), (vre, 30.0)], 25.0, 5.0, tally)
        self.assertEqual(remaining, 0.0)
        self.assertEqual(reductions, [[ocgt, 20.0], [vre, 5.0]])
        self.assertEqual(output(gen_list, ocgt), 0.0)
        self.assertEqual(output(gen_list, vre), 25.0)
        self.assertEqual(tally.power_mw[corrected.SEGMENT_THERMAL_RUNNING], 10.0)
        self.assertEqual(tally.power_mw[corrected.SEGMENT_THERMAL_SHUTDOWN_SAVING], 10.0)
        self.assertEqual(tally.power_mw[corrected.SEGMENT_VRE], 5.0)
        # CCGT: c = 55, S(6 h) = 113.7 (hot), m = 0.5, H = 6 h >= minimum down
        # time 6 h: a = 55 - 113.7/3 = 17.1 > 0.
        ccgt, vre = gas("CCGT", 55.0, 100.0, 100.0, 40.0), wind(30.0)
        remaining, reductions, _ = stack([ccgt, vre], [(ccgt, 40.0), (vre, 30.0)], 45.0, 6.0)
        self.assertEqual(reductions, [[ccgt, 40.0], [vre, 5.0]])

    def test_b_restart_cost_above_saving_curtails_wind_first(self):
        # Same OCGT, H = 0.5 h: a = 75 - 175.7/0.25 = -627.8 <= 0; the running range
        # (20 -> 10 MW) still goes first, then wind, the shutdown last.
        ocgt, vre = gas("OCGT", 75.0, 50.0, 50.0, 20.0), wind(30.0)
        tally = corrected.DownwardTally()
        remaining, reductions, gen_list = stack([ocgt, vre], [(ocgt, 20.0), (vre, 30.0)], 25.0, 0.5, tally)
        self.assertEqual(remaining, 0.0)
        self.assertEqual(reductions, [[ocgt, 10.0], [vre, 15.0]])
        self.assertEqual(output(gen_list, ocgt), 10.0)
        self.assertEqual(tally.power_mw[corrected.SEGMENT_THERMAL_SHUTDOWN_SAVING], 0.0)
        # H = 3 h (the review's case): restart 175.7 x 20 = 3,514 > saving
        # 75 x 10 x 3 = 2,250, a = 75 - 175.7/1.5 = -42.1 <= 0: wind first,
        # although c x H = 225 > S = 175.7 per MW (the A22 form c - S/H would
        # have shut the OCGT first).
        ocgt, vre = gas("OCGT", 75.0, 50.0, 50.0, 20.0), wind(30.0)
        tally = corrected.DownwardTally()
        remaining, reductions, _ = stack([ocgt, vre], [(ocgt, 20.0), (vre, 30.0)], 25.0, 3.0, tally)
        self.assertEqual(remaining, 0.0)
        self.assertEqual(reductions, [[ocgt, 10.0], [vre, 15.0]])
        self.assertEqual(tally.power_mw[corrected.SEGMENT_THERMAL_SHUTDOWN_SAVING], 0.0)
        # H = 2 h: a = 75 - 175.7 = -100.7, still wind first; once wind is gone the
        # shutdown follows (after VRE, not refused).
        ocgt, vre = gas("OCGT", 75.0, 50.0, 50.0, 20.0), wind(30.0)
        tally = corrected.DownwardTally()
        remaining, reductions, _ = stack([ocgt, vre], [(ocgt, 20.0), (vre, 30.0)], 45.0, 2.0, tally)
        self.assertEqual(remaining, 0.0)
        self.assertEqual(reductions, [[ocgt, 15.0], [vre, 30.0]])
        self.assertEqual(tally.power_mw[corrected.SEGMENT_THERMAL_SHUTDOWN_AFTER_VRE], 5.0)
        # CCGT with H = 3 h < minimum down time 6 h (a = 55 - 113.7/1.5 = -20.8
        # anyway): it may not shut down while other down regulation is left
        # (last resort after wind).
        ccgt, vre = gas("CCGT", 55.0, 100.0, 100.0, 40.0), wind(30.0)
        tally = corrected.DownwardTally()
        remaining, reductions, _ = stack([ccgt, vre], [(ccgt, 40.0), (vre, 30.0)], 60.0, 3.0, tally)
        self.assertEqual(remaining, 0.0)
        self.assertEqual(reductions, [[ccgt, 30.0], [vre, 30.0]])
        self.assertEqual(tally.power_mw[corrected.SEGMENT_THERMAL_SHUTDOWN_LAST_RESORT], 10.0)

    def test_c_reduction_within_the_running_range_is_thermal_first(self):
        # CCGT at 70 MW (minimum stable 35 MW), wind 30 MW, 20 MW to remove,
        # one-period outlook: no unit has to stop, so CCGT saves 55/MWh first.
        ccgt, vre = gas("CCGT", 55.0, 100.0, 60.0, 70.0), wind(30.0)
        remaining, reductions, gen_list = stack([ccgt, vre], [(ccgt, 70.0), (vre, 30.0)], 20.0, 0.5)
        self.assertEqual(remaining, 0.0)
        self.assertEqual(reductions, [[ccgt, 20.0]])
        self.assertEqual(output(gen_list, vre), 30.0)

    def test_doctoral_rule_set_keeps_the_thesis_order(self):
        def run(rules):
            ccgt, vre = gas("CCGT", 55.0, 100.0, 60.0, 70.0), wind(30.0)
            ccgt.curtail_cost = 48.04
            with rules_scope(rules), unittest.mock.patch.object(
                    corrected, "economic_downward_stack", wraps=corrected.economic_downward_stack) as spy:
                accepted = [[vre, vre.gen_cost, 30.0, 0], [ccgt, 55.0, 70.0, 48.04]]
                last = [(vre, 0, 0.0), (ccgt, 48.04, 70.0)]
                gen_list = [[vre, 30.0], [ccgt, 70.0]]
                result = kernel.curtailment_market_bidding(
                    3, 80.0, 100.0, accepted, last, 0.0, gen_list, [], electrolyzer(), [])
            return result[4], vre, ccgt, spy.call_count

        thesis, vre, ccgt, calls = run(DOCTORAL)
        self.assertEqual(calls, 0)
        self.assertEqual(output(thesis, vre), 10.0)  # thesis: wind (curtail cost 0) first
        self.assertEqual(output(thesis, ccgt), 70.0)
        fixed, vre, ccgt, calls = run(CORRECTED)
        self.assertEqual(calls, 1)
        self.assertEqual(output(fixed, vre), 30.0)  # running range: CCGT first
        self.assertEqual(output(fixed, ccgt), 50.0)


class SegmentRuleTests(unittest.TestCase):
    def test_restart_table_holds_the_a22_values(self):
        # A22 values (2024 GBP) restated in 2025 GBP (A24-4, factor 138.4 / 133.9).
        parameters = corrected.restart_parameters()
        self.assertEqual(set(parameters), {"CCGT", "OCGT", "biomass"})
        ccgt, ocgt, bio = parameters["CCGT"], parameters["OCGT"], parameters["biomass"]
        self.assertEqual([ccgt.restart_cost(h) for h in (0.5, 11.5, 12.0, 48.0, 48.5)],
                         [113.7, 113.7, 134.4, 134.4, 155.0])
        self.assertEqual([ocgt.restart_cost(h) for h in (0.5, 60.0)], [175.7, 175.7])
        self.assertEqual([bio.restart_cost(h) for h in (0.5, 60.0)], [129.2, 129.2])
        a22 = {name: row["restart_cost_gbp2024_per_mw"]
               for name, row in corrected.restart_table()["technologies"].items()}
        self.assertEqual(a22, {"CCGT": {"hot": 110.0, "warm": 130.0, "cold": 150.0},
                               "OCGT": {"hot": 170.0, "warm": 170.0, "cold": 170.0},
                               "biomass": {"hot": 125.0, "warm": 125.0, "cold": 125.0}})
        self.assertEqual((ccgt.min_stable_fraction, ocgt.min_stable_fraction, bio.min_stable_fraction),
                         (0.5, 0.5, 0.35))
        self.assertEqual((ccgt.min_down_time_h, ocgt.min_down_time_h, bio.min_down_time_h), (6.0, 0.5, 6.0))
        table = corrected.restart_table()
        self.assertIn("A22", table["status"])
        self.assertEqual(len(corrected.restart_table_sha256()), 64)

    def test_net_saving_charges_restart_per_mw_of_capacity(self):
        # A22a: a(H) = c - S(H)/(m H); S per MW of capacity, 1 MW of output at
        # minimum stable generation is 1/m MW of capacity.
        parameters = corrected.restart_parameters()
        ccgt, ocgt, bio = parameters["CCGT"], parameters["OCGT"], parameters["biomass"]
        self.assertAlmostEqual(ccgt.net_saving(55.07, 6.0), 55.07 - 113.7 / 3.0)
        self.assertAlmostEqual(ccgt.net_saving(55.07, 14.0), 55.07 - 134.4 / 7.0)
        self.assertAlmostEqual(ocgt.net_saving(75.0, 3.0), 75.0 - 351.4 / 3.0)
        self.assertAlmostEqual(ocgt.net_saving(75.0, 5.0), 4.72)
        self.assertAlmostEqual(bio.net_saving(85.0, 6.0), 85.0 - 129.2 / (0.35 * 6.0))
        # Break-even downtimes of reference statistics 4.6 (GBP1 costs, 2025 GBP).
        self.assertAlmostEqual(ccgt.break_even_hours(55.07), 4.13, places=2)
        self.assertAlmostEqual(ocgt.break_even_hours(74.92), 4.69, places=2)
        self.assertAlmostEqual(bio.break_even_hours(85.0), 4.34, places=2)
        self.assertEqual(ocgt.break_even_hours(0.0), float("inf"))
        # Restart cost of the output actually removed equals S x capacity shut.
        removed_mw, horizon = 10.0, 3.0
        capacity_shut = removed_mw / ocgt.min_stable_fraction
        self.assertAlmostEqual(ocgt.net_saving(75.0, horizon) * removed_mw * horizon,
                               75.0 * removed_mw * horizon - 175.7 * capacity_shut)
        zero = corrected.RestartParameters("x", {"hot": 1.0, "warm": 1.0, "cold": 1.0}, 0.0, 1.0, 12.0, 48.0)
        with self.assertRaises(ValueError):
            zero.net_saving(50.0, 6.0)

    def test_technology_mapping(self):
        self.assertEqual(corrected.restart_technology(gas("CCGT", 55.0, 1, 1, 0)), "CCGT")
        self.assertEqual(corrected.restart_technology(gas("OCGT", 75.0, 1, 1, 0)), "OCGT")
        self.assertEqual(corrected.restart_technology(biomass(10.0, 10.0, 0.0)), "biomass")
        self.assertIsNone(corrected.restart_technology(wind(1.0)))
        self.assertIsNone(corrected.restart_technology(kernel.NuclearGenerator("Nuclear", 0, 0, 0, 1, 1, 0, 0, 0)))

    def test_zero_net_saving_ties_go_to_vre(self):
        # OCGT c = 87.85, H = 4 h: a = 87.85 - 175.7/(0.5 x 4) = 0 -> not > 0, wind first.
        ocgt, vre = gas("OCGT", 87.85, 50.0, 50.0, 20.0), wind(30.0)
        self.assertEqual(corrected.restart_parameters()["OCGT"].net_saving(87.85, 4.0), 0.0)
        _, reductions, _ = stack([ocgt, vre], [(ocgt, 20.0), (vre, 30.0)], 25.0, 4.0)
        self.assertEqual(reductions, [[ocgt, 10.0], [vre, 15.0]])

    def test_ramp_floor_bounds_both_segments_and_biomass_gets_budget_back(self):
        # CCGT 40 MW, previous 40, alter 10: floor 30 > minimum stable 20, so
        # only 10 MW (running range) can go; biomass m = 0.35.
        ccgt = gas("CCGT", 55.0, 100.0, 10.0, 40.0)
        unit = biomass(20.0, 20.0, 20.0)
        unit.have_gen_energy = 30.0
        vre = wind(5.0)
        tally = corrected.DownwardTally()
        remaining, reductions, _ = stack([ccgt, unit, vre], [(ccgt, 40.0), (unit, 20.0), (vre, 5.0)], 40.0, 6.0,
                                         tally)
        # Biomass running 13 (c = 85), CCGT running 10 (c = 55), biomass
        # shutdown 7 (a = 85 - 129.2/(0.35 x 6) = 23.5), then wind 5; 5 MW are
        # left (spill).
        self.assertEqual(reductions, [[unit, 20.0], [ccgt, 10.0], [vre, 5.0]])
        self.assertAlmostEqual(remaining, 5.0)
        self.assertAlmostEqual(unit.have_gen_energy, 10.0)
        self.assertAlmostEqual(tally.power_mw[corrected.SEGMENT_THERMAL_SHUTDOWN_SAVING], 7.0)
        # 25 MW to remove: the CCGT running range (55) now ranks above the
        # biomass shutdown (23.5), so the biomass stops only 2 MW (with the
        # A22 form 85 - 129.2/6 = 63.5 it would have stopped all 7 MW first).
        ccgt = gas("CCGT", 55.0, 100.0, 10.0, 40.0)
        unit = biomass(20.0, 20.0, 20.0)
        unit.have_gen_energy = 30.0
        vre = wind(5.0)
        tally = corrected.DownwardTally()
        remaining, reductions, _ = stack([ccgt, unit, vre], [(ccgt, 40.0), (unit, 20.0), (vre, 5.0)], 25.0, 6.0,
                                         tally)
        self.assertEqual(remaining, 0.0)
        self.assertAlmostEqual(reductions[0][1], 15.0)
        self.assertIs(reductions[0][0], unit)
        self.assertEqual(reductions[1], [ccgt, 10.0])
        self.assertAlmostEqual(tally.power_mw[corrected.SEGMENT_THERMAL_SHUTDOWN_SAVING], 2.0)

    def test_other_rows_are_tallied_by_class(self):
        hydro = kernel.WaterGenerator("Hydro_natural_flow", 0, 0, 0, 100.0, 100.0, 1000, 0, 0, 10.0, 0)
        hydro.have_gen_energy = 50.0
        nuclear = kernel.NuclearGenerator("Nuclear", 0, 0, 0, 40.0, 40.0, 0, 0, 0)
        vre = wind(10.0)
        tally = corrected.DownwardTally()
        remaining, reductions, _ = stack([hydro, nuclear, vre], [(hydro, 10.0), (nuclear, 40.0), (vre, 10.0)],
                                         25.0, 0.5, tally)
        # Hydro (avoided cost 0, rank 1) before VRE (0.0001 -> 0.00, rank 2),
        # nuclear (0 - 100 premium) last.
        self.assertEqual(remaining, 0.0)
        self.assertEqual([row[1] for row in reductions], [10.0, 10.0, 5.0])
        self.assertEqual((tally.power_mw[corrected.SEGMENT_HYDRO], tally.power_mw[corrected.SEGMENT_VRE],
                          tally.power_mw[corrected.SEGMENT_NUCLEAR]), (10.0, 10.0, 5.0))

    def test_order_is_deterministic(self):
        def run():
            a, b = gas("OCGT", 75.0, 50.0, 50.0, 20.0), gas("OCGT", 75.0, 50.0, 50.0, 20.0)
            vre = wind(30.0)
            _, reductions, _ = stack([a, b, vre], [(a, 20.0), (b, 20.0), (vre, 30.0)], 25.0, 0.5)
            return [(id(row[0]) == id(a), row[1]) for row in reductions]

        self.assertEqual(run(), run())
        self.assertEqual(run(), [(True, 10.0), (False, 10.0), (False, 5.0)])


class OutlookTests(unittest.TestCase):
    def test_run_after(self):
        self.assertEqual(corrected.surplus_run_after([True, False, True, True, False, True]).tolist(),
                         [0, 2, 1, 0, 1, 0])

    def test_outlook_from_forecast_vre_and_nuclear(self):
        vre = wind(0.0, name="onshore_Nottingham")
        vre.capacity_multiplier = 2.0
        nuclear = kernel.NuclearGenerator("Nuclear", 0, 0, 0, 40.0, 5, 0, 0, 0)
        hydro = kernel.WaterGenerator("Hydro_natural_flow", 0, 0, 0, 100.0, 10, 10, 6, 0, 0, 0)
        cf = np.array([0.5, 1.0, 1.0, 0.2, 1.0, 1.0])
        bound = _Bound([(vre, 20.0, cf)], [(nuclear, 40.0, np.full(6, 0.5)), (hydro, 100.0, np.ones(6))])
        # Must-take = 40 x cf + 20 (hydro excluded): 40, 60, 60, 28, 60, 60.
        forecast = np.array([70.0, 60.0, 55.0, 50.0, 60.0, 61.0])
        outlook = corrected.build_surplus_outlook(forecast, bound, [vre, nuclear, hydro], 0.5, 6)
        self.assertEqual(outlook.basis, corrected.OUTLOOK_FORECAST)
        self.assertEqual((outlook.vre_covered, outlook.vre_total), (1, 1))
        # Surplus flags: F, T, T, F, T, F -> H = (1 + run after) x 0.5 h.
        self.assertEqual([outlook.horizon_hours(t) for t in range(6)], [1.5, 1.0, 0.5, 1.0, 0.5, 0.5])
        fallback = corrected.build_surplus_outlook(forecast, None, [vre], 0.5, 6)
        self.assertEqual(fallback.basis, corrected.OUTLOOK_CURRENT_ONLY)
        self.assertEqual(fallback.horizon_hours(0), 0.5)

    def test_kernel_reads_the_outlook_of_the_period(self):
        # Period 3 with 11 more surplus periods: H = 6 h, so the CCGT shutdown
        # (a = 55 - 110/3 > 0) goes before wind inside the kernel branch.
        outlook = corrected.SurplusOutlook(0.5, np.array([0, 0, 0, 11, 0]), corrected.OUTLOOK_FORECAST)
        ccgt, vre = gas("CCGT", 55.0, 100.0, 100.0, 40.0), wind(30.0)
        with rules_scope(CORRECTED, outlook):
            kernel._P06_STATE.downward_tally = corrected.DownwardTally()
            accepted = [[vre, vre.gen_cost, 30.0, 0], [ccgt, 55.0, 40.0, 10.0]]
            last = [(vre, 0, 0.0), (ccgt, 10.0, 40.0)]
            gen_list = [[vre, 30.0], [ccgt, 40.0]]
            result = kernel.curtailment_market_bidding(3, 25.0, 70.0, accepted, last, 0.0, gen_list, [],
                                                       electrolyzer(), [])
            tally = kernel._P06_STATE.downward_tally
        self.assertEqual(output(result[4], ccgt), 0.0)
        self.assertEqual(output(result[4], vre), 25.0)
        self.assertEqual(tally.down_periods, 1)
        self.assertEqual(tally.horizon_hours_sum, 6.0)
        summary = tally.summary(0.5)
        self.assertEqual(summary["reduced_mwh_by_segment"][corrected.SEGMENT_THERMAL_SHUTDOWN_SAVING], 10.0)
        # One period earlier the outlook is the current period only: wind first.
        ccgt, vre = gas("CCGT", 55.0, 100.0, 100.0, 40.0), wind(30.0)
        with rules_scope(CORRECTED, outlook):
            accepted = [[vre, vre.gen_cost, 30.0, 0], [ccgt, 55.0, 40.0, 10.0]]
            last = [(vre, 0, 0.0), (ccgt, 10.0, 40.0)]
            result = kernel.curtailment_market_bidding(2, 25.0, 70.0, accepted, last, 0.0,
                                                       [[vre, 30.0], [ccgt, 40.0]], [], electrolyzer(), [])
        self.assertEqual(output(result[4], ccgt), 20.0)
        self.assertEqual(output(result[4], vre), 5.0)


class MethodChangeTests(unittest.TestCase):
    """Q13: a method change of the corrected profile that saved Studies must confirm."""

    def test_switch_is_gated_to_the_corrected_profile(self):
        from gridform_core import methodology

        self.assertEqual(FIELD_CORRECTIONS["downward_restart_economics"], CORRECTION_ID)
        self.assertEqual(DOCTORAL.downward_restart_economics, "not_modelled")
        self.assertEqual(CORRECTED.downward_restart_economics, "restart_cost_vs_avoided_cost_v1")
        catalogue = methodology.load_catalogue()
        self.assertTrue(catalogue.corrections[CORRECTION_ID].gated)
        self.assertTrue(methodology.resolve_methodology("value-corrected").enabled(CORRECTION_ID))
        self.assertFalse(methodology.resolve_methodology(methodology.REFERENCE_PROFILE_ID).enabled(CORRECTION_ID))

    def test_version_ledger_bump_requires_opt_in(self):
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        bumps = [bump for bump in ledger["modules"]["value-bid-at-cost-psm"]["bumps"]
                 if CORRECTION_ID in bump["correction_ids"]]
        self.assertEqual(len(bumps), 1)
        self.assertTrue(bumps[0]["requires_user_opt_in"])
        self.assertEqual(bumps[0]["package"], "R1-2")

    def test_saved_corrected_study_needs_confirmation(self):
        from gridform_core import revision_migration
        from gridform_core.methodology import PROFILE_PARAMETER, resolve_project_methodology

        project = {"modules": {"psm": "value-bid-at-cost-psm"}, "parameters": {PROFILE_PARAMETER: "value-corrected"}}
        resolved = resolve_project_methodology(project)
        self.assertIn(CORRECTION_ID, resolved.applied_correction_ids)
        before = [item for item in resolved.applied_correction_ids if item != CORRECTION_ID]
        records = [item for item in resolved.applied_correction_records() if item["id"] != CORRECTION_ID]
        row = revision_migration._applied_corrections_row(
            {"applied_correction_ids": before, "applied_corrections": records}, project)
        self.assertEqual(row["classification"], "method_upgrade_required")
        self.assertIn(CORRECTION_ID, row["changed_correction_ids"])
        doctoral = resolve_project_methodology(
            {"modules": {}, "parameters": {PROFILE_PARAMETER: "doctoral-lineage-0.6.0a2"}})
        self.assertNotIn(CORRECTION_ID, doctoral.applied_correction_ids)


if __name__ == "__main__":
    unittest.main()
