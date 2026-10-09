"""DECISIONS A26 (R4-1): three true errors of the doctoral kernel, fixed as universal corrections.

The retained Scheme C kernel (``runtime_compat/modular_simulation_model.py``)
runs the thesis clearing in the doctoral reproduction profile.  The website
methodology describes the published VALUE model, so the author ruled (A26)
that three implementation errors are corrected in both profiles:

* ``r41.down-regulation-taken-once`` (A15): in the curtailment branch a
  non-VRE unit that met the remaining down-regulation requirement left the
  requirement unchanged, so the outer loop took the same amount again from
  later bids (usually wind).
* ``r41.storage-period-power-budget`` (DEV-STO-01, P5-03): every clearing
  stage reset a store's power limit, so a store could discharge up to twice
  its rating in one period and charge and discharge in the same period.
* ``r41.must-run-surplus-counted-once`` (DEV-BAL-04, P5-04): the balancing
  stage added the must-run nuclear surplus that served the balancing
  requirement to nuclear output already in the accepted supply, and paid it
  a second time.

Each toy below has a hand-computable oracle.
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import unittest
from pathlib import Path

import numpy as np

from gridform_core.builtin.scheme_c_1000twh import native_corrected as corrected
from gridform_core.builtin.scheme_c_1000twh.native_market_rules import CORRECTED, DOCTORAL, FIELD_CORRECTIONS
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel

from tests.test_native_corrected_rules import ahead, battery

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = ROOT / "tests" / "fixtures" / "runs"
DOCTORAL_PROFILE = "doctoral-lineage-0.6.0a2"
CORRECTED_PROFILE = "value-corrected"
R41_IDS = (
    "r41.down-regulation-taken-once",
    "r41.must-run-surplus-counted-once",
)
# DEV-STO-01 reuses the corrected rule's id, now universal (A26).
STORAGE_ID = "p06.storage-net-per-period"
UNIVERSAL_IDS = R41_IDS + (STORAGE_ID,)


@contextlib.contextmanager
def rules_scope(rules):
    saved = os.environ.get("PHYSICAL_PERIOD_HOURS")
    os.environ["PHYSICAL_PERIOD_HOURS"] = "0.5"
    kernel._P06_STATE.reset(rules)
    kernel._SURPLUS_TRACE.begin(0, 0.0, None)
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


def hydro(capacity, previous, alter=100.0):
    # WaterGenerator(name, gen_cost, curtail_cost, carbon_emission, capacity_limit,
    #                alter_limit, energy_limit, add_energy, capital_cost, real_gen_energy, unit_time_cost)
    return kernel.WaterGenerator("Hydro_natural_flow", 0.0, 0, 0, capacity, alter, 1.0e6, 0, 0, previous, 0)


def gas(name, fuel, capacity, alter, previous, curtail_cost=10.0):
    return kernel.GasGenerator(name, 0.0, curtail_cost, 0, capacity, alter, 0, 0, 0, 0, fuel, previous, 0)


def electrolyzer():
    # capacity 0: no flexible demand in these toys.
    return kernel.Electrolyzer("electrolyzer", 0, 0, 0.65, 1000, 0, 0, 0)


def output(gen_list, asset):
    return sum(float(row[1]) for row in gen_list if row[0] is asset)


class DownRegulationTakenOnceTests(unittest.TestCase):
    """Trigger fixture of r41.down-regulation-taken-once (A15, option C)."""

    def _curtail(self, connections):
        # Forecast 100 MW, realised 85 MW: 15 MW must be taken out of the
        # day-ahead schedule.  Hydro (curtail cost 0) sorts before wind (0,
        # input order) and can give 20 MW (previous output 20 < ramp 100), so
        # it meets the whole 15 MW.  Oracle: hydro 20 -> 5, wind stays 30,
        # CCGT stays 50; S = 85 = realised demand.
        river, vre, ccgt = hydro(100.0, 20.0), wind(30.0), gas("CCGT", 55.0, 100.0, 100.0, 50.0)
        accepted = [[river, 0.0, 20.0, 0], [vre, vre.gen_cost, 30.0, 0], [ccgt, 55.0, 50.0, 10.0]]
        last = [(river, 0, 20.0), (vre, 0, 0.0), (ccgt, 10.0, 50.0)]
        gen_list = [[river, 20.0], [vre, 30.0], [ccgt, 50.0]]
        with rules_scope(DOCTORAL):
            result = kernel.curtailment_market_bidding(
                3, 85.0, 100.0, accepted, last, 0.0, gen_list, connections, electrolyzer(), [])
            routing = {key: dict(value) for key, value in kernel._SURPLUS_TRACE.routing.items()}
        gen_list, curtailed = result[4], result[5]
        return river, vre, ccgt, gen_list, curtailed, routing

    def _assert_taken_once(self, connections):
        river, vre, ccgt, gen_list, curtailed, routing = self._curtail(connections)
        self.assertEqual(output(gen_list, river), 5.0)
        self.assertEqual(output(gen_list, vre), 30.0)  # before R4-1: 15.0 (taken twice)
        self.assertEqual(output(gen_list, ccgt), 50.0)
        self.assertEqual(sum(float(row[1]) for row in gen_list), 85.0)
        self.assertEqual(curtailed, 15.0)
        # Surplus routing of the period: everything booked was taken out of S.
        in_dispatch = routing[kernel._IN_DISPATCH]
        self.assertEqual(in_dispatch["available"], 15.0)
        self.assertEqual(in_dispatch["curtailed"], 15.0)
        self.assertEqual(in_dispatch["claimed_spill"], 0.0)  # before R4-1: -15.0

    def test_branch_without_export_lines(self):
        self._assert_taken_once([])

    def test_branch_with_export_lines(self):
        # An export line at a zero price sells nothing, so the second
        # sub-branch (soldable lines exist) reaches the same down regulation.
        line = kernel.Connection("france", 0, 0, 0)
        line.transfer_constraint = -40.0
        line.external_price = 0.0
        self._assert_taken_once([line])

    def test_partial_non_vre_then_ccgt_meets_the_rest_once(self):
        # Period-301 shape: hydro gives all 20 MW (else branch), CCGT meets the
        # remaining 10 MW (>= branch).  Oracle: hydro 0, CCGT 40, wind 30.
        river, vre = hydro(100.0, 20.0), wind(30.0)
        ccgt = gas("CCGT", 55.0, 100.0, 100.0, 50.0, curtail_cost=10.0)
        accepted = [[river, 0.0, 20.0, 0], [vre, vre.gen_cost, 30.0, 0], [ccgt, 55.0, 50.0, 10.0]]
        last = [(river, 0, 20.0), (vre, 0, 0.0), (ccgt, 10.0, 50.0)]
        gen_list = [[river, 20.0], [vre, 30.0], [ccgt, 50.0]]
        with rules_scope(DOCTORAL):
            result = kernel.curtailment_market_bidding(
                3, 70.0, 100.0, accepted, last, 0.0, gen_list, [], electrolyzer(), [])
        self.assertEqual(output(result[4], river), 0.0)
        self.assertEqual(output(result[4], ccgt), 40.0)
        self.assertEqual(output(result[4], vre), 30.0)  # before R4-1: 20.0
        self.assertEqual(sum(float(row[1]) for row in result[4]), 70.0)

    def test_vre_branch_was_already_taken_once(self):
        # Wind first (input order before hydro): the VRE branch always zeroed
        # the requirement; unchanged.  Oracle: wind 30 -> 15.
        river, vre = hydro(100.0, 20.0), wind(30.0)
        accepted = [[vre, vre.gen_cost, 30.0, 0], [river, 0.0, 20.0, 0]]
        last = [(vre, 0, 0.0), (river, 0, 20.0)]
        gen_list = [[vre, 30.0], [river, 20.0]]
        with rules_scope(DOCTORAL):
            result = kernel.curtailment_market_bidding(
                3, 35.0, 50.0, accepted, last, 0.0, gen_list, [], electrolyzer(), [])
        self.assertEqual(output(result[4], vre), 15.0)
        self.assertEqual(output(result[4], river), 20.0)


def nuclear(capacity, previous, price=10.0):
    unit = kernel.NuclearGenerator("Nuclear", price, 50.0, 0, capacity, 1.0, 0, 0, 0)
    unit.real_gen_energy = previous
    return unit


def balancing(generators, real, forecast, accepted, excess, gen_list, bids, excess_list, batteries=()):
    accounts = [collections.defaultdict(float) for _ in range(4)]
    result = kernel.balancing_market_bidding(
        generators, 5, real, forecast, accepted, excess, accounts[0], accounts[1], accounts[2], gen_list,
        accounts[3], [], [], bids, electrolyzer(), excess_list, list(batteries), 1.0)
    return {
        "fee": sum(result[0]), "gen_list": result[8], "excess": result[10], "income": result[15],
        "unserved": result[16], "balance_renewables": sum(accounts[0].values()),
    }


class MustRunSurplusCountedOnceTests(unittest.TestCase):
    """Trigger fixture of r41.must-run-surplus-counted-once (DEV-BAL-04)."""

    def test_nuclear_surplus_serving_the_balancing_requirement_is_not_generated_again(self):
        # Must-run nuclear produced 14 MW ahead against a 10 MW forecast:
        # 4 MW surplus inside S.  Realised demand 13 MW: the 3 MW balancing
        # requirement is met by that surplus.  Oracle: nuclear stays 14 MW
        # (before R4-1: 17), no balancing fee or income for it (before: fee
        # 3 MW x 10 GBP/MWh = 30, income 3 x 0.5 h x 10 = 15 GBP), 1 MW left.
        unit = nuclear(30.0, 14.0)
        with rules_scope(DOCTORAL):
            kernel._SURPLUS_TRACE.begin(5, 4.0, kernel._IN_DISPATCH)
            result = balancing([unit], 13.0, 10.0, [[unit, 10.0, 14.0, 50.0]], 4.0, [[unit, 14.0]],
                               [[unit, 10.0, 30.0, 50.0, 0]], [[unit, 4.0]])
            routing = kernel._SURPLUS_TRACE.routing[kernel._IN_DISPATCH]
        self.assertEqual(output(result["gen_list"], unit), 14.0)
        self.assertEqual(sum(float(row[1]) for row in result["gen_list"]), 14.0)  # = 13 demand + 1 surplus
        self.assertEqual(result["fee"], 0.0)
        self.assertEqual(result["balance_renewables"], 0.0)
        self.assertEqual(result["income"].get("Nuclear", 0.0), 0.0)
        self.assertEqual(result["excess"], 1.0)
        self.assertEqual(result["unserved"], 0)
        # The routing still shows the 3 MW the surplus served (to_dispatch).
        self.assertEqual(routing["to_dispatch"], 3.0)
        self.assertEqual(routing["claimed_spill"], 1.0)

    def test_requirement_above_the_nuclear_surplus(self):
        # Requirement 6 MW > surplus 4 MW: the whole surplus serves it (no
        # second generation); of the remaining 2 MW nuclear (the marginal
        # ahead unit) ramps up by its 1 MW ramp limit and CCGT gives 1 MW.
        # Oracle: nuclear 15 (before R4-1: 19 = 14 + 4 again + 1), CCGT 1,
        # total 16 = realised demand (before: 20).
        unit = nuclear(30.0, 14.0)
        ccgt = gas("CCGT", 50.0, 100.0, 100.0, 0.0)
        with rules_scope(DOCTORAL):
            kernel._SURPLUS_TRACE.begin(5, 4.0, kernel._IN_DISPATCH)
            result = balancing([unit, ccgt], 16.0, 10.0, [[unit, 10.0, 14.0, 50.0]], 4.0, [[unit, 14.0]],
                               [[unit, 10.0, 30.0, 50.0, 0], [ccgt, 50.0, 100.0, 10.0, 0]], [[unit, 4.0]])
        self.assertEqual(output(result["gen_list"], unit), 15.0)
        self.assertEqual(output(result["gen_list"], ccgt), 1.0)
        self.assertEqual(sum(float(row[1]) for row in result["gen_list"]), 16.0)
        self.assertEqual(result["unserved"], 0)

    def test_vre_surplus_is_still_dispatched_and_paid(self):
        # A VRE surplus row is outside S: serving the requirement adds VRE
        # output and pays it, as before.  Wind accepted 10 of 14 MW.
        vre = wind(14.0)
        with rules_scope(DOCTORAL):
            kernel._SURPLUS_TRACE.begin(5, 4.0, "out_of_dispatch")
            result = balancing([vre], 13.0, 10.0, [[vre, vre.gen_cost, 10.0, 0]], 4.0, [[vre, 10.0]],
                               [[vre, vre.gen_cost, 14.0, 0, 0]], [[vre, 4.0]])
        self.assertEqual(output(result["gen_list"], vre), 13.0)
        self.assertAlmostEqual(result["fee"], 3.0 * vre.gen_cost, places=12)
        self.assertEqual(result["excess"], 1.0)


class StoragePeriodPowerBudgetTests(unittest.TestCase):
    """Trigger fixture of p06.storage-net-per-period as a universal correction (DEV-STO-01)."""

    def test_rule_sets_share_the_storage_position(self):
        self.assertEqual(DOCTORAL.storage_position, "net_per_period")
        self.assertEqual(CORRECTED.storage_position, "net_per_period")
        self.assertNotIn("storage_position", FIELD_CORRECTIONS)

    def test_balancing_stage_shares_the_rated_power(self):
        # 200 MW store (0.5c, 800 MWh) with 600 MWh stored; forecast 250 MW,
        # realised 350 MW.  Ahead: the store (bid below the OCGT's 200) gives
        # its rated 200 MW, OCGT 50.  Balancing (+100 MW): the store has no
        # power left in this period, so the OCGT gives the 100 MW.
        # Oracle: store 200 (before R4-1: 300), OCGT 150 (before: 50).
        from tests.test_native_corrected_rules import gas as corrected_gas

        with rules_scope(DOCTORAL):
            unit = battery(energy=800.0, tranches={0: 300.0, 1: 300.0})
            unit.resize_power_capacity(200.0, 800.0)
            peaker = corrected_gas("OCGT", 200.0, 500.0, 500.0, 0.0)
            state = ahead([peaker], [unit], 250.0)
            kernel.balancing_market_bidding(
                [peaker], 10, 350.0, 250.0, state["accepted_bids"], state["excess"],
                np.zeros(11), np.zeros(11), np.zeros(11), state["gen_list"], np.zeros(11), [], [],
                state["bids"], electrolyzer(), state["excess_list"], [unit], 1.0,
            )
            closed = unit.close_period(10)
        self.assertEqual(output(state["gen_list"], unit), 200.0)
        self.assertEqual(output(state["gen_list"], peaker), 150.0)
        self.assertEqual(closed["discharged_mw"], 200.0)

    def test_curtailment_branch_nets_instead_of_charging(self):
        # 200 MW store with a 200 MWh tranche; forecast 100 MW met by the
        # store ahead; realised 60 MW, so 40 MW must be absorbed.  The store
        # reduces its own discharge by 40 MW instead of charging 40 MW while
        # discharging 100 MW.  Oracle: delivered 60, charged 0, state of
        # charge = 200 x (1 - 0.000021) - 60 x 0.5 (n1 = n2 = 1).
        with rules_scope(DOCTORAL):
            unit = battery(energy=800.0, tranches={0: 200.0})
            unit.resize_power_capacity(200.0, 800.0)
            before = sum(unit.stored_energy.values())
            state = ahead([], [unit], 100.0)
            kernel._SURPLUS_TRACE.begin(10, 0.0, None)
            result = kernel.curtailment_market_bidding(
                10, 60.0, 100.0, state["accepted_bids"], state["last_gen_energy"], state["excess"],
                state["gen_list"], [], electrolyzer(), [unit],
            )
            routing = kernel._SURPLUS_TRACE.routing[kernel._IN_DISPATCH]
            closed = unit.close_period(10)
        self.assertEqual(result[1], 0.0)  # storage charge; before R4-1: 40 MW
        self.assertAlmostEqual(output(result[4], unit), 60.0, places=9)
        self.assertAlmostEqual(sum(unit.stored_energy.values()), before * (1 - 0.000021) - 60.0 * 0.5, places=9)
        self.assertEqual(closed["charged_mw"], 0.0)
        self.assertAlmostEqual(closed["bought_back_mw"], 40.0, places=9)
        # The 40 MW leave S as a lower store output: routing books them as
        # taken out of S (curtailed), not as a storage charge.
        self.assertAlmostEqual(routing["curtailed"], 40.0, places=9)
        self.assertEqual(routing["to_storage"], 0.0)
        self.assertEqual(routing["claimed_spill"], 0.0)

    def test_balancing_surplus_nets_against_the_discharge(self):
        # 0.5c store, 10 MWh stored (0.000021 decay): it can give
        # 2 x 9.99979 = 19.99958 MW, bid 25.8 GBP/MWh below nuclear at 60.
        # Forecast 50: store 19.99958, nuclear at its ramp floor 35 (40 - 5),
        # must-run surplus 4.99958.  Realised 52: the 2 MW requirement is
        # served by the surplus (r41.must-run-surplus-counted-once), the
        # remaining 2.99958 MW are netted against the store's discharge.
        # Oracle: store delivers exactly 17 MW, charges 0, nuclear 35,
        # supply 52 = realised demand.  Before R4-1: store 19.99958 MW out and
        # 2.99958 MW in, nuclear 37, supply 56.99958.
        with rules_scope(DOCTORAL):
            unit = battery(energy=400.0, tranches={0: 10.0})
            unit_nuclear = kernel.NuclearGenerator("Nuclear", 60.0, 91430, 0, 40.0, 5.0, 0, 0, 0)
            state = ahead([unit_nuclear], [unit], 50.0)
            kernel._SURPLUS_TRACE.begin(10, state["excess"], kernel._IN_DISPATCH)
            result = kernel.balancing_market_bidding(
                [unit_nuclear], 10, 52.0, 50.0, state["accepted_bids"], state["excess"],
                np.zeros(11), np.zeros(11), np.zeros(11), state["gen_list"], np.zeros(11), [], [],
                state["bids"], electrolyzer(), state["excess_list"], [unit], 1.0,
            )
            routing = kernel._SURPLUS_TRACE.routing[kernel._IN_DISPATCH]
            closed = unit.close_period(10)
        self.assertAlmostEqual(state["excess"], 4.99958, places=9)
        self.assertEqual(result[3], 0.0)  # storage charge
        self.assertAlmostEqual(output(result[8], unit), 17.0, places=9)
        self.assertEqual(output(result[8], unit_nuclear), 35.0)
        self.assertAlmostEqual(sum(float(row[1]) for row in result[8]), 52.0, places=9)
        self.assertEqual(closed["charged_mw"], 0.0)
        self.assertAlmostEqual(closed["discharged_mw"], 17.0, places=9)
        # The whole must-run surplus serves demand (2 MW requirement, 2.99958
        # MW in place of the store's discharge); nothing is charged.
        self.assertAlmostEqual(routing["to_dispatch"], 4.99958, places=9)
        self.assertEqual(routing["to_storage"], 0.0)

    def test_vre_surplus_netted_against_a_discharge_enters_the_supply(self):
        # The store discharged 19.99958 MW ahead; wind delivered 4 MW and has
        # 6 MW of surplus outside S (its excess row).  Netting the surplus
        # against the discharge: the store delivers 13.99958, wind's 6 MW
        # enter S as wind output, nothing is charged, total supply unchanged
        # (before R4-1 the store discharged 19.99958 and charged 6).
        with rules_scope(DOCTORAL):
            unit = battery(energy=400.0, tranches={0: 10.0})
            unit.discharge(0, 19.99958, 10)
            vre = wind(10.0)
            gen_list = [[unit, 19.99958], [vre, 4.0]]
            rows = [[vre, 6.0]]
            bought, charged = kernel._thesis_absorb_excess(unit, 10, 6.0, gen_list, "out_of_dispatch", rows)
            closed = unit.close_period(10)
        self.assertAlmostEqual(bought, 6.0, places=12)
        self.assertEqual(charged, 0.0)
        self.assertAlmostEqual(output(gen_list, unit), 13.99958, places=9)
        self.assertAlmostEqual(output(gen_list, vre), 10.0, places=12)
        self.assertAlmostEqual(sum(float(row[1]) for row in gen_list), 23.99958, places=9)
        self.assertEqual(rows[0][1], 0.0)
        self.assertEqual(closed["charged_mw"], 0.0)

    def test_unclassified_surplus_is_not_netted_and_a_discharging_store_does_not_charge(self):
        with rules_scope(DOCTORAL):
            unit = battery(energy=400.0, tranches={0: 10.0})
            unit.discharge(0, 10.0, 10)
            gen_list = [[unit, 10.0]]
            self.assertEqual(kernel._thesis_absorb_excess(unit, 10, 3.0, gen_list, None, []), (0.0, 0.0))
            self.assertEqual(output(gen_list, unit), 10.0)

    def test_close_period_rejects_a_store_that_charged_and_discharged(self):
        with rules_scope(DOCTORAL):
            unit = battery(energy=100.0)
            book = corrected.period_book(unit, 4)
            book.draws.append([1, 5.0])
            book.charged_mw = 3.0
            with self.assertRaises(corrected.StorageNettingError):
                unit.close_period(4)


class CatalogueAndIdentityTests(unittest.TestCase):
    """A26: universal corrections in both profiles; Q13 opt-in; doctoral-only advisories."""

    def test_universal_in_both_profiles(self):
        from gridform_core import methodology

        catalogue = methodology.load_catalogue()
        for correction_id in UNIVERSAL_IDS:
            correction = catalogue.corrections[correction_id]
            self.assertEqual(correction.track, "universal", correction_id)
            if correction_id in R41_IDS:
                self.assertEqual(correction.applies_when["profiles_any"], (DOCTORAL_PROFILE,))
            for profile in (DOCTORAL_PROFILE, CORRECTED_PROFILE):
                resolved = methodology.resolve_methodology(profile)
                self.assertTrue(resolved.enabled(correction_id), (profile, correction_id))
                self.assertIn(correction_id, resolved.to_dict()["applied_correction_ids"])

    def test_old_studies_are_a_method_change(self):
        from gridform_core import methodology

        # Before R4-1 the doctoral profile applied none of the three and the
        # corrected profile applied p06.storage-net-per-period as a
        # profile-gated correction.
        for profile in (DOCTORAL_PROFILE, CORRECTED_PROFILE):
            current = methodology.resolve_methodology(profile)
            before = []
            for item in current.applied_correction_records():
                if item["id"] in R41_IDS or (item["id"] == STORAGE_ID and profile == DOCTORAL_PROFILE):
                    continue
                before.append(dict(item, track="profile_gated") if item["id"] == STORAGE_ID else item)
            self.assertNotEqual(methodology._sha256_json(before), current.applied_corrections_sha256, profile)
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        bump = next(item for item in ledger["modules"]["value-bid-at-cost-psm"]["bumps"] if item["package"] == "R4-1")
        self.assertEqual((bump["from"], bump["to"]), ("6.6.0", "6.7.0"))
        self.assertTrue(bump["requires_user_opt_in"])
        self.assertEqual(set(bump["correction_ids"]), set(UNIVERSAL_IDS))

    def test_advisory_only_for_doctoral_and_pre_profile_runs(self):
        from gridform_core import methodology
        from gridform_core.result_advisories import evaluate_advisories

        run_root = FIXTURE_RUNS / "pre-fix-dynamic-full"
        status = json.loads((run_root / "status.json").read_text(encoding="utf-8"))

        def ids(methodology_record):
            run = dict(status)
            if methodology_record is None:
                run.pop("methodology", None)
            else:
                run["methodology"] = methodology_record
            return {row["id"] for row in evaluate_advisories(run, run_root)}

        def before_r41(profile):
            record = methodology.resolve_methodology(profile).to_dict()
            record["applied_correction_ids"] = [
                item for item in record["applied_correction_ids"] if item not in R41_IDS]
            return record

        with_advisory = [item for item in R41_IDS
                         if methodology.load_catalogue().corrections[item].advisory is not None]
        self.assertTrue(with_advisory)
        self.assertTrue(set(with_advisory) <= ids(None))  # pre-profile Run: thesis kernel
        self.assertTrue(set(with_advisory) <= ids(before_r41(DOCTORAL_PROFILE)))
        self.assertFalse(set(R41_IDS) & ids(before_r41(CORRECTED_PROFILE)))
        self.assertFalse(set(R41_IDS) & ids(methodology.resolve_methodology(DOCTORAL_PROFILE).to_dict()))


if __name__ == "__main__":
    unittest.main()
