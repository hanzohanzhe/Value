"""P0-6 S5-S10: the corrected market rule set of the default PSM, toy by toy.

Every class is the trigger fixture of one profile-gated correction in
``gridform_core/data/methodology/corrections/p06.json``: the same hand-checkable
toy gives the thesis value under the doctoral rule set and the corrected value
under the corrected one.  Decision A2 keeps the realisation branch (and every
hidden shortfall) unchanged in both.
"""

from __future__ import annotations

import contextlib
import os
import unittest

import numpy as np

from gridform_core import energy_balance_contract as contract
from gridform_core.builtin.scheme_c_1000twh import native_corrected as corrected
from gridform_core.builtin.scheme_c_1000twh.native_market_rules import CORRECTED, DOCTORAL
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel
from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import DynamicAnnualStorageCost

from tests import native_reproduction_harness as harness


@contextlib.contextmanager
def rules_scope(rules):
    saved = os.environ.get("PHYSICAL_PERIOD_HOURS")
    os.environ["PHYSICAL_PERIOD_HOURS"] = "0.5"
    kernel._P06_STATE.reset(rules)
    try:
        yield
    finally:
        kernel._P06_STATE.reset()
        if saved is None:
            os.environ.pop("PHYSICAL_PERIOD_HOURS", None)
        else:
            os.environ["PHYSICAL_PERIOD_HOURS"] = saved


def wind(name="wind", available=0.0, electrolyzer_limit=0.0, rampup=0.0):
    asset = kernel.ExpensiverenewableGenerator(
        name, 0.0001, 0, 0, 0, 0, 0, electrolyzer_cost=0, energy_efficiency=0.65,
        electrolyzer_limit=electrolyzer_limit, rampup_rate=rampup, capacity_multiplier=1,
    )
    asset.capacity_limit = available
    return asset


def gas(name, fuel, capacity, alter, previous, curtail_cost=10.0):
    return kernel.GasGenerator(
        name, 0.0, curtail_cost, 0, capacity, alter, 0, 0, 0, 0, fuel, previous, 0,
    )


def nuclear(capacity, alter):
    return kernel.NuclearGenerator("Nuclear", 0, 91430, 0, capacity, alter, 0, 0, 0)


def biomass(capacity, alter, previous, fuel=60.0):
    return kernel.BiomassGenerator(
        "bio_and_waste", 0.0, 3, 0, capacity, alter, 0, 1000, 0, 0, 0, 0, fuel, previous, 0,
    )


def battery(name="battery", energy=400.0, battery_type="0.5c", tranches=None, bid_basis=None):
    unit = kernel.Battery(name, energy, 0, 0, 0, 1.0, 1.0, 0, capital_cost=1_000_000, battery_type=battery_type)
    unit.prepare_operating_year(2030)
    if bid_basis is not None:
        unit.cost_recovery.bid_basis = bid_basis
    for period, stored in (tranches or {}).items():
        unit.set_stored_energy_var(period, stored)
    return unit


def electrolyzer(capacity=0.0):
    return kernel.Electrolyzer("electrolyzer", 0, 0, 0.65, 1000, capacity, capacity, 0)


def ahead(generators, batteries, forecast, period=10, accepted=None):
    accepted_bids = list(accepted or [])
    zeros = [np.zeros(period + 1, dtype=np.float32) for _ in range(4)]
    result = kernel.ahead_market_bidding(
        generators, batteries, forecast, period, accepted_bids, zeros[0], zeros[1], zeros[2], zeros[3], 1.0,
        retain_storage_tranche_history=False,
    )
    return {
        "accepted_bids": result[0], "last_gen_energy": result[5], "excess": result[6], "gen_list": result[10],
        "bids": result[13], "income": result[14], "excess_list": result[15],
    }


def output(gen_list, asset):
    return sum(float(row[1]) for row in gen_list if row[0] is asset)


class MeritKeyAndSurplusTests(unittest.TestCase):
    """p06.storage-after-generation-merit-key and p06.d1-surplus-accounting."""

    def _zero_bid_storage(self, rules):
        with rules_scope(rules):
            unit = battery("pumpedhydro_battery", battery_type="pumped_hydro", tranches={0: 100.0},
                           bid_basis="cycle_only")
            vre = wind(available=50.0)
            return ahead([vre], [unit], 50.0), vre, unit

    def test_zero_bid_pumped_hydro_does_not_crowd_out_wind(self):
        thesis, vre, unit = self._zero_bid_storage(DOCTORAL)
        # Thesis key: the zero storage bid sorts below 0.0001 and fills F; the
        # wind is neither accepted nor recorded as surplus (it vanishes).
        self.assertEqual(output(thesis["gen_list"], vre), 0.0)
        self.assertEqual(output(thesis["gen_list"], unit), 50.0)
        self.assertEqual(thesis["excess"], 0)
        fixed, vre, unit = self._zero_bid_storage(CORRECTED)
        # Same 0.01 band: generation first, storage after; wind serves 50.
        self.assertEqual(output(fixed["gen_list"], vre), 50.0)
        self.assertEqual(output(fixed["gen_list"], unit), 0.0)

    def test_nuclear_blocking_surplus_is_rebuilt(self):
        def run(rules):
            with rules_scope(rules):
                unit, vre = nuclear(40.0, 5.0), wind(available=30.0)
                return ahead([unit, vre], [], 20.0), unit, vre

        thesis, unit, vre = run(DOCTORAL)
        # Nuclear ramp floor 35 > F 20: 15 MW must-run surplus; the wind is
        # not accepted and HEAD records only the nuclear row.
        self.assertEqual(thesis["excess"], 15.0)
        self.assertEqual([row[0] for row in thesis["excess_list"]], [unit])
        fixed, unit, vre = run(CORRECTED)
        self.assertEqual(fixed["excess"], 45.0)
        self.assertEqual([(row[0], row[1]) for row in fixed["excess_list"]], [(unit, 15.0), (vre, 30.0)])

    def test_merit_key(self):
        generator = [wind(), 0.0001, 10.0, 0, 0]
        storage = [battery(), 0.0, 0, 10.0]
        offers = sorted([storage, generator], key=corrected.merit_key)
        self.assertIs(offers[0], generator)
        dearer = [battery(), 0.02, 0, 10.0]
        self.assertIs(sorted([dearer, [wind(), 0.015, 1.0, 0, 0]], key=corrected.merit_key)[1], dearer)


class DownwardOrderTests(unittest.TestCase):
    """p06.avoided-cost-downward-order (P3-03)."""

    def _curtail(self, rules, units, schedule, forecast, real):
        with rules_scope(rules):
            accepted = [[unit, unit.gen_cost, power, unit.curtail_cost] for unit, power in schedule]
            last = [(unit, unit.curtail_cost, unit.real_gen_energy) for unit in units]
            gen_list = [[unit, power] for unit, power in schedule]
            result = kernel.curtailment_market_bidding(
                3, real, forecast, accepted, last, 0.0, gen_list, [], electrolyzer(), [],
            )
            return result[4]

    def test_ccgt_is_reduced_before_wind(self):
        def run(rules):
            vre, ccgt = wind(available=30.0), gas("CCGT", 55.0, 100.0, 60.0, 70.0, curtail_cost=48.04)
            vre.curtail_cost = 0
            return self._curtail(rules, [vre, ccgt], [(vre, 30.0), (ccgt, 70.0)], 100.0, 80.0), vre, ccgt

        thesis, vre, ccgt = run(DOCTORAL)
        self.assertEqual(output(thesis, vre), 10.0)  # thesis: cheapest curtail_cost (wind) first
        self.assertEqual(output(thesis, ccgt), 70.0)
        fixed, vre, ccgt = run(CORRECTED)
        self.assertEqual(output(fixed, vre), 30.0)
        self.assertEqual(output(fixed, ccgt), 50.0)

    def test_ocgt_before_ccgt_and_ramp_floor_spills(self):
        with rules_scope(CORRECTED):
            ccgt = gas("CCGT", 55.0, 100.0, 10.0, 40.0)
            ocgt = gas("OCGT", 75.0, 50.0, 50.0, 20.0)
            accepted = [[ccgt, 55.0, 40.0, 10.0], [ocgt, 75.0, 20.0, 10.0]]
            last = [(ccgt, 10.0, 40.0), (ocgt, 10.0, 20.0)]
            gen_list = [[ccgt, 40.0], [ocgt, 20.0]]
            remaining, fees, reductions = corrected.downward_stack(accepted, last, 45.0, gen_list)
        self.assertEqual(reductions, [[ocgt, 20.0], [ccgt, 10.0]])  # CCGT floor 40 - 10 = 30
        self.assertEqual(remaining, 15.0)  # left for the in-dispatch spill
        self.assertEqual(output(gen_list, ccgt), 30.0)

    def test_biomass_gets_its_budget_back(self):
        with rules_scope(CORRECTED):
            unit = biomass(20.0, 20.0, 10.0)
            unit.have_gen_energy = 15.0
            accepted = [[unit, unit.gen_cost, 10.0, 3]]
            remaining, _, _ = corrected.downward_stack(accepted, [(unit, 3, 10.0)], 4.0, [[unit, 10.0]])
        self.assertEqual(remaining, 0.0)
        self.assertEqual(unit.have_gen_energy, 11.0)


class NettingTests(unittest.TestCase):
    """p06.storage-net-per-period (P5-03)."""

    def _balancing_discharge(self, rules):
        with rules_scope(rules):
            unit = battery(energy=800.0, tranches={0: 300.0, 1: 300.0})
            unit.resize_power_capacity(200.0, 800.0)
            peaker = gas("OCGT", 200.0, 500.0, 500.0, 0.0)
            # Ahead: storage 200 (rated) + OCGT 50 for F = 250; realised 350.
            state = ahead([peaker], [unit], 250.0)
            kernel.balancing_market_bidding(
                [peaker], 10, 350.0, 250.0, state["accepted_bids"], state["excess"],
                np.zeros(11, dtype=np.float32), np.zeros(11, dtype=np.float32), np.zeros(11, dtype=np.float32),
                state["gen_list"], np.zeros(11, dtype=np.float32), [], [], state["bids"], electrolyzer(),
                state["excess_list"], [unit], 1.0,
            )
            return output(state["gen_list"], unit), output(state["gen_list"], peaker)

    def test_stages_share_the_rated_power(self):
        thesis_storage, thesis_peaker = self._balancing_discharge(DOCTORAL)
        self.assertEqual(thesis_storage, 300.0)  # 200 ahead + 100 again in balancing
        self.assertEqual(thesis_peaker, 50.0)
        fixed_storage, fixed_peaker = self._balancing_discharge(CORRECTED)
        self.assertEqual(fixed_storage, 200.0)
        self.assertEqual(fixed_peaker, 150.0)

    def _curtailment_after_discharge(self, rules):
        with rules_scope(rules):
            unit = battery(energy=800.0, tranches={0: 200.0})
            unit.resize_power_capacity(200.0, 800.0)
            before = sum(unit.stored_energy.values())
            state = ahead([], [unit], 100.0)
            result = kernel.curtailment_market_bidding(
                10, 60.0, 100.0, state["accepted_bids"], state["last_gen_energy"], state["excess"],
                state["gen_list"], [], electrolyzer(), [unit],
            )
            if rules is CORRECTED:
                unit.close_period(10)
            return before, sum(unit.stored_energy.values()), result[1], output(result[4], unit)

    def test_curtailment_buys_back_instead_of_charging(self):
        before, after, charged, delivered = self._curtailment_after_discharge(DOCTORAL)
        self.assertGreater(charged, 0.0)  # discharged 100 then charged 40 in one period
        before, after, charged, delivered = self._curtailment_after_discharge(CORRECTED)
        self.assertEqual(charged, 0.0)
        self.assertAlmostEqual(delivered, 60.0)
        decay = 0.000021
        self.assertAlmostEqual(after, before * (1 - decay) - 60.0 * 0.5, places=9)

    def test_close_period_rejects_charge_and_discharge(self):
        with rules_scope(CORRECTED):
            unit = battery(energy=100.0)
            book = corrected.period_book(unit, 4)
            book.draws.append([1, 5.0])
            book.charged_mw = 3.0
            with self.assertRaises(corrected.StorageNettingError):
                corrected.close_battery_period(unit, 4)


class SkimTests(unittest.TestCase):
    """p06.no-vre-pre-clearing-skim (P3-08)."""

    def test_small_availability_is_not_lost(self):
        for rules, expected in ((DOCTORAL, 0.0), (CORRECTED, 0.05)):
            with rules_scope(rules):
                vre = wind(available=0.05, electrolyzer_limit=1.0, rampup=0.125)
                ahead([vre], [], 10.0)
                self.assertEqual(vre.capacity_limit, expected)
                if rules is DOCTORAL:
                    self.assertAlmostEqual(kernel._P06_STATE.diagnostics["vre_skim_leak_mw"], 0.05)


class BidBasisTests(unittest.TestCase):
    """p06.storage-bid-cycle-only (P5-04, Q8)."""

    def _cost(self, battery_type, basis):
        cost = DynamicAnnualStorageCost(battery_type=battery_type)
        cost.prepare_year(2030, capital_cost_gbp=1e6, power_capacity_mw=10.0,
                          energy_capacity_mwh=20.0, discharge_efficiency=0.9)
        cost.bid_basis = basis
        return cost

    def test_cycle_only_ignores_dwell(self):
        thesis = self._cost("0.5c", "thesis_dwell_linear")
        fixed = self._cost("0.5c", "cycle_only")
        self.assertGreater(thesis.bid_price_gbp_per_mwh(48), thesis.bid_price_gbp_per_mwh(2))
        self.assertEqual(fixed.bid_price_gbp_per_mwh(48), fixed.bid_price_gbp_per_mwh(2))
        self.assertEqual(fixed.bid_price_gbp_per_mwh(48), fixed.cycle_depreciation_gbp_per_mwh)
        self.assertEqual(self._cost("pumped_hydro", "cycle_only").bid_price_gbp_per_mwh(500), 0.0)
        self.assertEqual(list(fixed.ordered_charge_periods({1: 1.0, 5: 1.0}, 9)), [1, 5])

    def test_reports_and_recovery_adequacy_follow_the_basis(self):
        from gridform_core.storage_recovery import recovery_adequacy

        thesis = self._cost("0.5c", "thesis_dwell_linear")
        self.assertNotIn("bid_basis", thesis.report())  # thesis reports stay byte-identical
        fixed = self._cost("0.5c", "cycle_only")
        for cost in (thesis, fixed):
            cost.record_sale(10.0, 4)
        fixed_report = fixed.report()
        self.assertEqual(fixed_report["bid_basis"], "cycle_only")
        adequacy = recovery_adequacy(fixed_report)
        self.assertEqual(adequacy["schema_version"], "value.storage-recovery-adequacy/v2")
        self.assertAlmostEqual(adequacy["bid_recovered_revenue_gbp"], 10.0 * fixed.cycle_depreciation_gbp_per_mwh)
        thesis_adequacy = recovery_adequacy(thesis.report())
        self.assertAlmostEqual(
            thesis_adequacy["bid_recovered_revenue_gbp"],
            10.0 * thesis.cycle_depreciation_gbp_per_mwh + 10.0 * 4 * thesis.holding_recovery_gbp_per_mwh_period,
        )


class UniformSettlementTests(unittest.TestCase):
    """p06.storage-uniform-price-settlement (A8, P5-05)."""

    def test_storage_is_paid_the_marginal_price(self):
        def run(rules):
            with rules_scope(rules):
                unit = battery(energy=40.0, tranches={0: 20.0}, bid_basis="cycle_only")
                ccgt = gas("CCGT", 55.0, 100.0, 100.0, 50.0)
                state = ahead([ccgt], [unit], 60.0)
                return state["income"], unit

        income, unit = run(DOCTORAL)
        bid = unit.storage_bid_price(10, 0)
        self.assertAlmostEqual(income[unit.name], 20.0 * 0.5 * bid)
        income, unit = run(CORRECTED)
        self.assertAlmostEqual(income[unit.name], 20.0 * 0.5 * 55.0)
        self.assertAlmostEqual(income["CCGT"], 40.0 * 0.5 * 55.0)


class CorrectedSyntheticRunTests(unittest.TestCase):
    """The 96-period synthetic scenario under the corrected rule set (live loop)."""

    @classmethod
    def setUpClass(cls):
        cls.runs = {
            variant: harness.run_case(variant, loop="live", runtime_attributes={"market_rules": CORRECTED})
            for variant in harness.VARIANTS
        }

    def test_declares_the_corrected_boundary(self):
        for run in self.runs.values():
            self.assertEqual(run["ledger"].balance_declarations[0]["boundary_id"],
                             contract.NATIVE_CORRECTED_FULL_NODE_V1)

    def test_node_closes_except_decision_a2_shortfalls(self):
        for variant, run in self.runs.items():
            for row in run["ledger"].periods:
                raw = row["raw_energy_balance_residual_mwh"]
                # A2: the forecast realisation rule is unchanged, so a period
                # whose ahead stage could not meet the forecast keeps its
                # shortfall (never a surplus).
                self.assertLessEqual(raw, 1e-9, (variant, row["period"]))
                if not 8 <= row["period"] <= 12:
                    self.assertAlmostEqual(raw, 0.0, places=9, msg=(variant, row["period"]))
                self.assertAlmostEqual(row["vre_available_mwh"], row["vre_accepted_mwh"] + row["curtailed_mwh"])
                self.assertEqual(row["compatibility_adjustment_mwh"], 0.0)

    def test_storage_never_exceeds_rated_power(self):
        for run in self.runs.values():
            for row in run["ledger"].storage:
                self.assertLessEqual(row["discharge_mwh"], row["power_capacity_mw"] * 0.5 + 1e-6)


if __name__ == "__main__":
    unittest.main()
