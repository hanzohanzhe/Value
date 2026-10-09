"""Decision A18: corrected-profile nuclear starts in service; start-up cost only after a period off.

The thesis kernel (doctoral rule set) starts every model year with an empty
``accepted_bids``: every gas, biomass and nuclear unit adds its
``startup_cost`` to its day-ahead offer until it is first accepted.  Nuclear
(start-up 500 GBP/MWh on GBP1) therefore sits at the end of the merit order
until the first scarcity period of the year (FX7: 12 December on GBP1 2025)
and then stays on (A15 path dependency).  The corrected rule set
(``fx8.nuclear-in-service-at-start``) counts nuclear units as running before
the first period, so they run as baseload at their availability from period
0; a unit that was not accepted in a period pays the start-up cost once, in
the period it restarts.  Each toy is checked under both rule sets.
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
from gridform_core.builtin.scheme_c_1000twh.native_market_rules import (
    CORRECTED,
    DOCTORAL,
    FIELD_CORRECTIONS,
)
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel

from tests import native_reproduction_harness as harness

CORRECTION_ID = "fx8.nuclear-in-service-at-start"
ROOT = Path(__file__).resolve().parents[1]
STARTUP = 500.0


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


def nuclear(capacity=40.0):
    # NuclearGenerator(name, gen_cost, curtail_cost, carbon_emission, capacity_limit,
    #                  alter_limit, startup_cost, capital_cost, unit_time_cost)
    return kernel.NuclearGenerator("Nuclear", 0.0, 91430, 0, capacity, 100.0, STARTUP, 0, 0)


def gas(capacity=60.0):
    return kernel.GasGenerator("CCGT", 0.1, 48.04, 0, capacity, capacity, 50.0, 0, 0, 0, 55.0, 0.0, 0)


RECORDED: list = []


def _record(stage, period, information_scope, payload):
    RECORDED.append({"stage": stage, "period": int(period), **dict(payload)})
    return None


def nuclear_offer(period):
    rows = [row for row in RECORDED if row["stage"] == "ahead" and row["period"] == period]
    offers = [offer for offer in rows[-1]["offers"] if offer["asset_type"] == "NuclearGenerator"]
    return offers[0]


def clear(generators, accepted_bids, forecast, period):
    zeros = [np.zeros(period + 1, dtype=np.float32) for _ in range(4)]
    result = kernel.ahead_market_bidding(
        list(generators), [], forecast, period, accepted_bids, zeros[0], zeros[1], zeros[2], zeros[3], 1.0,
        retain_storage_tranche_history=False, connections=[],
    )
    return result[0], result[10]


def output(gen_list, asset):
    return sum(float(row[1]) for row in gen_list if row[0] is asset)


def nuclear_startup_gbp(dispatch, previous):
    """The physical start-up term of the nuclear unit alone (GBP, one period)."""

    terms = corrected.physical_cost_terms(
        dispatch, previous, 0.5, storage_fee_this_period=0.0, retained_cost_gbp=0.0,
        generation_offer_gbp=0.0, storage_fee_retained_gbp=0.0, curtailment_fee_gbp=0.0,
        balancing_fee_gbp=0.0, export_revenue_gbp=0.0, import_payment_gbp=0.0,
    )
    return terms["startup_adder_gbp"]


class NuclearInServiceTests(unittest.TestCase):
    """Trigger fixture of fx8.nuclear-in-service-at-start (direct clearing calls)."""

    def setUp(self):
        RECORDED.clear()
        patcher = unittest.mock.patch.object(kernel, "_record_declared_input", _record)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _initial(self, rules, generators):
        # What run_simulation does before its first period (A18 rows or the thesis []).
        if rules.nuclear_initial_state == "in_service_at_start":
            return corrected.initial_running_rows(generators)
        return []

    def test_rule_fields_and_initial_rows(self):
        self.assertEqual(DOCTORAL.nuclear_initial_state, "off_until_accepted")
        self.assertEqual(CORRECTED.nuclear_initial_state, "in_service_at_start")
        unit, ccgt = nuclear(), gas()
        rows = corrected.initial_running_rows([ccgt, unit])
        # Only nuclear is in service; gas and biomass keep the thesis rule.
        self.assertEqual(rows, [[unit, 0.0, 0.0, 0.0]])

    def test_nuclear_with_startup_cost_runs_from_period_zero(self):
        for rules, expected_price, expected_output in ((DOCTORAL, STARTUP, 0.0), (CORRECTED, 0.0, 40.0)):
            with self.subTest(rules=rules.rule_set_id), rules_scope(rules):
                RECORDED.clear()
                unit, ccgt = nuclear(), gas()
                accepted, gen_list = clear([unit, ccgt], self._initial(rules, [unit, ccgt]), 60.0, 0)
                offer = nuclear_offer(0)
                self.assertEqual(offer["offer_price_gbp_per_mwh"], expected_price)
                self.assertEqual(offer["startup_component_applied"], rules is DOCTORAL)
                # Thesis: the 500 GBP/MWh nuclear offer clears after the 60 MW
                # CCGT (55.1 + start-up 50) only for the residual 0 MW, so the
                # CCGT serves the whole forecast; the nuclear unit ramps from
                # its constructor state only when accepted.  Corrected: the
                # nuclear unit clears first at its availability.
                self.assertEqual(output(gen_list, unit), expected_output)
                self.assertEqual(output(gen_list, ccgt), 60.0 - output(gen_list, unit))
                # The start-up term of the physical operating cost follows the offer.
                previous = [row[0] for row in self._initial(rules, [unit, ccgt])]
                booked = nuclear_startup_gbp({unit: output(gen_list, unit)}, previous)
                self.assertEqual(booked, 0.0)

    def test_restart_after_a_forced_off_period_pays_startup_once(self):
        with rules_scope(CORRECTED):
            unit, ccgt = nuclear(), gas()
            generators = [unit, ccgt]
            accepted = corrected.initial_running_rows(generators)
            startup_paid = []
            prices = []
            outputs = []
            for period, available in enumerate((40.0, 40.0, 0.0, 40.0, 40.0, 40.0)):
                unit.capacity_limit = available
                previous = [row[0] for row in accepted]
                # Forecast above the CCGT capacity: the restarting unit clears
                # even at its start-up offer.
                accepted, gen_list = clear(generators, accepted, 90.0, period)
                prices.append(nuclear_offer(period)["offer_price_gbp_per_mwh"])
                outputs.append(output(gen_list, unit))
                startup_paid.append(nuclear_startup_gbp({unit: outputs[-1]}, previous))
        # Period 2: refuelling/outage (zero availability), not accepted.
        self.assertEqual(outputs[2], 0.0)
        self.assertTrue(all(value > 0.0 for index, value in enumerate(outputs) if index != 2), outputs)
        # The start-up adder is in the offer only in the restart period 3 ...
        self.assertEqual([price > 0.0 for price in prices], [False, False, False, True, False, False])
        self.assertEqual(prices[3], STARTUP)
        # ... and the physical start-up term is booked once, for the restart energy.
        self.assertEqual([value > 0.0 for value in startup_paid], [False, False, False, True, False, False])
        self.assertAlmostEqual(startup_paid[3], outputs[3] * 0.5 * STARTUP)

    def test_switch_is_registered_for_the_corrected_profile_only(self):
        from gridform_core import methodology

        self.assertEqual(FIELD_CORRECTIONS["nuclear_initial_state"], CORRECTION_ID)
        self.assertTrue(methodology.resolve_methodology(None).enabled(CORRECTION_ID))
        self.assertFalse(methodology.resolve_methodology(methodology.REFERENCE_PROFILE_ID).enabled(CORRECTION_ID))
        entry = methodology.load_catalogue().corrections[CORRECTION_ID]
        self.assertTrue(entry.gated)
        self.assertIn("trajectory", entry.affects)


# The synthetic scenario's period with forecast demand 0: nothing is accepted.
ZERO_FORECAST = 81


class ForcedOutageDriver(harness.SyntheticDriver):
    """The synthetic driver with the nuclear unit unavailable in OUTAGE periods."""

    OUTAGE = (40, 41)

    def begin_period(self, period, generators, batterys, connections, electrolyzer) -> None:
        super().begin_period(period, generators, batterys, connections, electrolyzer)
        for asset in generators:
            if type(asset).__name__ == "NuclearGenerator":
                asset.capacity_limit = 0.0 if int(period) in self.OUTAGE else 40.0


class SyntheticLoopTests(unittest.TestCase):
    """The 96-period synthetic scenario, live loop (run_simulation), both rule sets."""

    @staticmethod
    def _run(rules, *, outage=False):
        terms: list = []
        original = corrected.physical_cost_terms

        def capture(dispatch, previous, *args, **kwargs):
            result = original(dispatch, previous, *args, **kwargs)
            terms.append({
                "previous_nuclear": any(type(asset).__name__ == "NuclearGenerator" for asset in previous),
                "nuclear_startup_gbp": sum(
                    float(power) * 0.5 * float(asset.startup_cost) for asset, power in dispatch.items()
                    if type(asset).__name__ == "NuclearGenerator" and asset not in previous and float(power) > 0.0
                ),
            })
            return result

        scenario = harness.build_scenario()
        if outage:
            # Scarcity on the restart period, so the start-up offer clears there.
            for key in ("forecast_mw", "real_mw"):
                scenario[key][ForcedOutageDriver.OUTAGE[-1] + 1] = 200.0
        patches = [unittest.mock.patch.object(corrected, "physical_cost_terms", capture)]
        if outage:
            patches.append(unittest.mock.patch.object(harness, "SyntheticDriver", ForcedOutageDriver))
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            run = harness.run_case("dynamic", scenario, loop="live", runtime_attributes={"market_rules": rules})
        nuclear_mwh = [sum(row["accepted_mwh"] for row in rows if row["asset_type"] == "NuclearGenerator")
                       for rows in run["ledger"].orders]
        return run, terms, nuclear_mwh

    def test_corrected_nuclear_is_baseload_from_period_zero(self):
        self.assertEqual(harness.build_scenario()["forecast_mw"][ZERO_FORECAST], 0.0)
        _, terms, nuclear_mwh = self._run(CORRECTED)
        self.assertEqual(nuclear_mwh[0], 20.0)  # 40 MW x 0.5 h in the first period
        self.assertTrue(terms[0]["previous_nuclear"])
        # Baseload until the synthetic zero-forecast period 81 (nothing clears
        # there, so the unit is off and its later restart pays start-up).
        self.assertTrue(all(value > 0.0 for value in nuclear_mwh[:ZERO_FORECAST]), "never off before")
        self.assertEqual(nuclear_mwh[ZERO_FORECAST], 0.0)
        self.assertEqual(sum(row["nuclear_startup_gbp"] for row in terms[:ZERO_FORECAST + 1]), 0.0)
        paid = [period for period, row in enumerate(terms) if row["nuclear_startup_gbp"] > 0.0]
        self.assertEqual(len(paid), 1)
        self.assertGreater(paid[0], ZERO_FORECAST)
        self.assertTrue(all(not row["previous_nuclear"] for row in terms[ZERO_FORECAST + 1:paid[0] + 1]))
        _, terms, thesis_mwh = self._run(DOCTORAL)
        # Thesis: off until the first scarcity (period 8 of the synthetic scenario).
        self.assertEqual(thesis_mwh[:8], [0.0] * 8)
        self.assertFalse(terms[0]["previous_nuclear"])
        self.assertGreater(sum(nuclear_mwh), sum(thesis_mwh))

    def test_corrected_restart_after_an_outage_pays_startup_once(self):
        run, terms, nuclear_mwh = self._run(CORRECTED, outage=True)
        first, last = ForcedOutageDriver.OUTAGE
        self.assertEqual(nuclear_mwh[first:last + 1], [0.0, 0.0])
        restart = last + 1
        self.assertGreater(nuclear_mwh[restart], 0.0)
        paid = [period for period, row in enumerate(terms[:ZERO_FORECAST]) if row["nuclear_startup_gbp"] > 0.0]
        self.assertEqual(paid, [restart])
        self.assertAlmostEqual(terms[restart]["nuclear_startup_gbp"], nuclear_mwh[restart] * STARTUP)
        # The energy balance still closes outside the A2 forecast-rule periods.
        for row in run["ledger"].periods:
            self.assertEqual(row["compatibility_adjustment_mwh"], 0.0, row["period"])


class MethodChangeTests(unittest.TestCase):
    """Q13: a method change of the corrected profile that saved Studies must confirm."""

    def test_version_ledger_bump_requires_opt_in(self):
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        bumps = [bump for bump in ledger["modules"]["value-bid-at-cost-psm"]["bumps"]
                 if CORRECTION_ID in bump["correction_ids"]]
        self.assertEqual(len(bumps), 1)
        self.assertTrue(bumps[0]["requires_user_opt_in"])
        self.assertEqual(bumps[0]["package"], "FX8")

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
