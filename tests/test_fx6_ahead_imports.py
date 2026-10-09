"""Decision A16-2 (four-role S-D3): day-ahead interconnector imports, corrected profile only.

The thesis kernel (doctoral rule set) offers an interconnector import only in
the balancing stage, for the upward requirement left after the day-ahead
schedule; ``ahead_market_bidding`` never sees a connection.  The corrected
rule set (``fx6.day-ahead-interconnector-imports``) also offers every
connection with a positive transfer constraint to the day-ahead clearing at
the period's counterparty price, and the balancing stage then offers only the
capacity the day-ahead schedule left.  Each toy is checked under both rule
sets: the doctoral value is the thesis behaviour, the corrected value the new
one.
"""

from __future__ import annotations

import contextlib
import json
import os
import unittest
import unittest.mock
from collections import defaultdict

import numpy as np

from gridform_core.builtin.scheme_c_1000twh import native_corrected as corrected
from gridform_core.builtin.scheme_c_1000twh.native_market_rules import (
    CORRECTED,
    DOCTORAL,
    FIELD_CORRECTIONS,
)
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel

from tests import native_reproduction_harness as harness

CORRECTION_ID = "fx6.day-ahead-interconnector-imports"
PERIOD = 10


@contextlib.contextmanager
def rules_scope(rules):
    saved = {key: os.environ.get(key) for key in ("PHYSICAL_PERIOD_HOURS", "SIMULATION_YEAR")}
    os.environ["PHYSICAL_PERIOD_HOURS"] = "0.5"
    os.environ["SIMULATION_YEAR"] = "2030"
    kernel._P06_STATE.reset(rules)
    try:
        yield
    finally:
        kernel._P06_STATE.reset()
        kernel._STORAGE_OFFERS.reset()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def gas(name="CCGT", fuel=55.0, capacity=100.0, alter=100.0, previous=0.0, curtail_cost=10.0):
    return kernel.GasGenerator(name, 0.0, curtail_cost, 0, capacity, alter, 0, 0, 0, 0, fuel, previous, 0)


def wind(available):
    asset = kernel.ExpensiverenewableGenerator(
        "wind", 0.0001, 0, 0, 0, 0, 0, electrolyzer_cost=0, energy_efficiency=0.65,
        electrolyzer_limit=0, rampup_rate=0, capacity_multiplier=1,
    )
    asset.capacity_limit = available
    return asset


def connection(name="Interconnect_France", transfer=40.0, price=30.0):
    link = kernel.Connection(name, 0, 0, 0)
    link.transfer_constraint = transfer
    link.external_price = price
    return link


def electrolyzer():
    return kernel.Electrolyzer("electrolyzer", 0, 0, 0.65, 1000, 0, 0, 0)


def ahead(generators, connections, forecast, batteries=()):
    zeros = [np.zeros(PERIOD + 1, dtype=np.float32) for _ in range(4)]
    result = kernel.ahead_market_bidding(
        list(generators), list(batteries), forecast, PERIOD, [], zeros[0], zeros[1], zeros[2], zeros[3], 1.0,
        retain_storage_tranche_history=False, connections=list(connections),
    )
    return {
        "accepted_bids": result[0], "last_gen_energy": result[5], "excess": result[6], "gen_list": result[10],
        "gen_list_name": result[12], "bids": result[13], "income": result[14], "excess_list": result[15],
    }


def balancing(generators, connections, state, forecast, real, batteries=()):
    result = kernel.balancing_market_bidding(
        list(generators), PERIOD, real, forecast, state["accepted_bids"], state["excess"], defaultdict(float),
        defaultdict(float), defaultdict(float), state["gen_list"], defaultdict(float), list(connections),
        state["gen_list_name"], state["bids"], electrolyzer(), state["excess_list"], list(batteries), 1.0,
    )
    return {"gen_list": result[8], "bought_fee": result[12], "unserved": result[16]}


def output(gen_list, asset):
    return sum(float(row[1]) for row in gen_list if row[0] is asset)


def declared_offers(stage):
    """Offers of the last clearing declaration of ``stage`` (kernel recorder)."""

    rows = [row for row in RECORDED if row["stage"] == stage]
    return rows[-1]["offers"] if rows else []


RECORDED: list = []


def _record(stage, period, information_scope, payload):
    RECORDED.append({"stage": stage, **dict(payload)})
    return None


class AheadImportOfferTests(unittest.TestCase):
    """Trigger fixture of fx6.day-ahead-interconnector-imports."""

    def setUp(self):
        RECORDED.clear()
        patcher = unittest.mock.patch.object(kernel, "_record_declared_input", _record)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _clear(self, rules, *, price, forecast, transfer=40.0):
        with rules_scope(rules):
            ccgt, link = gas(), connection(transfer=transfer, price=price)
            state = ahead([ccgt], [link], forecast)
            return state, ccgt, link

    def test_a_cheaper_import_displaces_ccgt(self):
        thesis, ccgt, link = self._clear(DOCTORAL, price=30.0, forecast=100.0)
        # Thesis: the day-ahead clearing receives no connection.
        self.assertEqual(output(thesis["gen_list"], link), 0.0)
        self.assertEqual(output(thesis["gen_list"], ccgt), 100.0)
        self.assertEqual([offer["resource_kind"] for offer in declared_offers("ahead")], ["thermal"])
        RECORDED.clear()
        fixed, ccgt, link = self._clear(CORRECTED, price=30.0, forecast=100.0)
        # Corrected: the 30 GBP/MWh import clears its 40 MW before the 55 GBP/MWh CCGT.
        self.assertEqual(output(fixed["gen_list"], link), 40.0)
        self.assertEqual(output(fixed["gen_list"], ccgt), 60.0)
        self.assertIn([link, 30.0, 40.0, 0.0], fixed["accepted_bids"])
        offers = {offer["resource_kind"]: offer for offer in declared_offers("ahead")}
        self.assertEqual(offers["import"]["offer_price_gbp_per_mwh"], 30.0)
        self.assertEqual(offers["import"]["maximum_power_mw"], 40.0)
        self.assertTrue(offers["import"]["offer_id"].startswith("ahead:i:"))
        self.assertEqual(kernel._P06_STATE.imports.scheduled_mw, {}, "state is reset after the scope")
        # Uniform settlement: the CCGT is marginal, the import is paid 55.
        self.assertAlmostEqual(fixed["income"][link.name], 40.0 * 0.5 * 55.0)

    def test_an_expensive_import_is_not_accepted(self):
        for rules in (DOCTORAL, CORRECTED):
            with self.subTest(rules=rules.rule_set_id):
                state, ccgt, link = self._clear(rules, price=90.0, forecast=100.0)
                self.assertEqual(output(state["gen_list"], link), 0.0)
                self.assertEqual(output(state["gen_list"], ccgt), 100.0)
        # Scarcity: the dear import fills what domestic capacity cannot.
        state, ccgt, link = self._clear(CORRECTED, price=90.0, forecast=120.0)
        self.assertEqual(output(state["gen_list"], ccgt), 100.0)
        self.assertEqual(output(state["gen_list"], link), 20.0)
        self.assertAlmostEqual(state["income"][link.name], 20.0 * 0.5 * 90.0)

    def test_exports_and_zero_capacity_offer_nothing_ahead(self):
        for transfer in (-40.0, 0.0):
            with self.subTest(transfer=transfer):
                state, ccgt, link = self._clear(CORRECTED, price=1.0, forecast=100.0, transfer=transfer)
                self.assertEqual(output(state["gen_list"], link), 0.0)
                self.assertEqual(corrected.import_offers([link], 1.0), [])

    def test_equal_band_order_generation_then_import_then_storage(self):
        ccgt, link = gas(), connection(price=55.0)
        storage = [kernel.Battery("store", 400, 0, 0, 0, 1.0, 1.0, 0, battery_type="pumped_hydro"), 55.0, 0, 10.0]
        generator = [ccgt, 55.0, 100.0, 10.0, 0]
        offers = [generator, storage] + corrected.import_offers([link], 1.0)
        ordered = sorted(offers, key=corrected.merit_key)
        self.assertIs(ordered[0], generator)
        self.assertTrue(corrected.is_import_offer(ordered[1]))
        self.assertIs(ordered[2], storage)

    def test_switch_is_registered_for_the_corrected_profile_only(self):
        from gridform_core import methodology

        self.assertEqual(FIELD_CORRECTIONS["interconnector_import_stage"], CORRECTION_ID)
        self.assertTrue(methodology.resolve_methodology(None).enabled(CORRECTION_ID))
        self.assertFalse(methodology.resolve_methodology(methodology.REFERENCE_PROFILE_ID).enabled(CORRECTION_ID))
        entry = methodology.load_catalogue().corrections[CORRECTION_ID]
        self.assertTrue(entry.gated)
        self.assertIn("trajectory", entry.affects)


class BalancingResidualTests(unittest.TestCase):
    """No double counting: balancing offers only the capacity the day-ahead schedule left."""

    def _run(self, rules, forecast, real):
        with rules_scope(rules):
            ccgt, link = gas(previous=100.0), connection(transfer=80.0, price=30.0)
            state = ahead([ccgt], [link], forecast)
            ahead_import = output(state["gen_list"], link)
            result = balancing([ccgt], [link], state, forecast, real)
            return ahead_import, result, ccgt, link

    def test_import_capacity_is_shared_between_the_stages(self):
        # Thesis: ahead CCGT 50; balancing requirement 50 is met by the import.
        ahead_import, result, ccgt, link = self._run(DOCTORAL, 50.0, 100.0)
        self.assertEqual(ahead_import, 0.0)
        self.assertEqual(output(result["gen_list"], link), 50.0)
        self.assertEqual(output(result["gen_list"], ccgt), 50.0)
        # Corrected: the import clears 50 ahead; balancing offers the other
        # 30 MW, so the CCGT supplies the last 20 (total import = capacity).
        ahead_import, result, ccgt, link = self._run(CORRECTED, 50.0, 100.0)
        self.assertEqual(ahead_import, 50.0)
        self.assertEqual(output(result["gen_list"], link), 80.0)
        self.assertEqual(output(result["gen_list"], ccgt), 20.0)
        self.assertAlmostEqual(sum(result["bought_fee"]), 30.0 * 30.0)
        self.assertEqual(result["unserved"], 0)

    def test_balancing_import_never_exceeds_the_remaining_capacity(self):
        for real in (60.0, 80.0, 140.0, 200.0):
            with self.subTest(real=real):
                _, result, ccgt, link = self._run(CORRECTED, 50.0, real)
                self.assertLessEqual(output(result["gen_list"], link), 80.0 + 1e-9)
                served = output(result["gen_list"], link) + output(result["gen_list"], ccgt)
                self.assertAlmostEqual(served + result["unserved"], real)


class CurtailmentTests(unittest.TestCase):
    """An accepted day-ahead import is reduced at its avoided import price."""

    def test_the_dearer_import_is_reduced_before_ccgt(self):
        with rules_scope(CORRECTED):
            ccgt, link = gas(capacity=60.0, alter=60.0, previous=60.0), connection(transfer=40.0, price=70.0)
            state = ahead([ccgt], [link], 100.0)
            self.assertEqual(output(state["gen_list"], link), 40.0)
            result = kernel.curtailment_market_bidding(
                PERIOD, 80.0, 100.0, state["accepted_bids"], state["last_gen_energy"], state["excess"],
                state["gen_list"], [link], electrolyzer(), [],
            )
            fees, gen_list = result[0], result[4]
            accepted = {id(row[0]): row for row in state["accepted_bids"]}
        self.assertEqual(output(gen_list, link), 20.0)
        self.assertEqual(output(gen_list, ccgt), 60.0)
        self.assertEqual(accepted[id(link)][2], 20.0)  # the paid import follows the reduction
        self.assertEqual(sum(fees), 0.0)  # no curtailment payment to the counterparty

    def test_downward_key_of_an_import(self):
        link = connection(price=55.0)
        ccgt = gas(fuel=55.0)
        hydro_like = kernel.BiomassGenerator("bio", 0.0, 3, 0, 20, 20, 0, 1000, 0, 0, 0, 0, 55.0, 0, 0)
        order = sorted([hydro_like, link, ccgt], key=corrected.downward_key)
        self.assertEqual([asset.name for asset in order], ["CCGT", "Interconnect_France", "bio"])
        self.assertEqual(corrected.avoided_cost(link), 55.0)
        self.assertEqual(corrected.ramp_floor_mw(link, 40.0), 0.0)


class SyntheticLoopTests(unittest.TestCase):
    """The 96-period synthetic scenario, live loop, both rule sets."""

    @classmethod
    def setUpClass(cls):
        cls.runs = {
            rules.rule_set_id: harness.run_case("dynamic", loop="live", runtime_attributes={"market_rules": rules})
            for rules in (DOCTORAL, CORRECTED)
        }

    def _imports(self, rules):
        return sum(row["import_mwh"] for row in self.runs[rules.rule_set_id]["ledger"].periods)

    def test_energy_balance_closes_with_day_ahead_imports(self):
        ledger = self.runs[CORRECTED.rule_set_id]["ledger"]
        self.assertGreater(self._imports(CORRECTED), 0.0)
        for row in ledger.periods:
            raw = row["raw_energy_balance_residual_mwh"]
            # A2 forecast-rule shortfalls stay (never a surplus); every other
            # period closes exactly, imports included in the supply.
            self.assertLessEqual(raw, 1e-9, row["period"])
            if not 8 <= row["period"] <= 12:
                self.assertAlmostEqual(raw, 0.0, places=9, msg=row["period"])
            self.assertEqual(row["compatibility_adjustment_mwh"], 0.0)

    def test_day_ahead_imports_are_declared_and_booked_as_offers(self):
        ledger = self.runs[CORRECTED.rule_set_id]["ledger"]
        import_rows = [order for period_rows in ledger.orders for order in period_rows
                       if order["asset_type"] == "Connection"]
        self.assertTrue(import_rows)
        self.assertEqual({row["stage"] for row in import_rows}, {"ahead_offer"})
        by_period = defaultdict(float)
        for row in import_rows:
            self.assertLessEqual(row["accepted_mwh"], row["offered_mwh"] + 1e-9)
            by_period[row["period"]] += row["accepted_mwh"]
        for row in ledger.periods:
            self.assertAlmostEqual(by_period.get(row["period"], 0.0), row["import_mwh"], places=9)

    def test_doctoral_keeps_imports_out_of_the_day_ahead_clearing(self):
        ledger = self.runs[DOCTORAL.rule_set_id]["ledger"]
        self.assertGreater(self._imports(DOCTORAL), 0.0)
        for period_rows in ledger.orders:
            for order in period_rows:
                if order["asset_type"] == "Connection":
                    # The frozen thesis row: a balancing import booked as final dispatch.
                    self.assertEqual(order["stage"], "final_dispatch")


class MethodChangeTests(unittest.TestCase):
    """Q13: a method change of the corrected profile that saved Studies must confirm."""

    def test_version_ledger_bump_requires_opt_in(self):
        from pathlib import Path

        ledger = json.loads((Path(__file__).resolve().parents[1] / "docs" / "release" / "VERSION_LEDGER.json")
                            .read_text(encoding="utf-8"))
        bumps = [bump for bump in ledger["modules"]["value-bid-at-cost-psm"]["bumps"]
                 if CORRECTION_ID in bump["correction_ids"]]
        self.assertEqual(len(bumps), 1)
        self.assertTrue(bumps[0]["requires_user_opt_in"])
        self.assertEqual(bumps[0]["package"], "FX6")

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
