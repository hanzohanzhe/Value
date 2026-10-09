"""P0-7 investment corrections through the production modules (plan 4.7 S4, S6-S8).

* ThermalNetRevenueTests - decision A4 in both profiles (p07.thermal-net-revenue):
  a CCGT paid exactly its marginal cost proposes nothing; paid 10 GBP/MWh
  below it, it retires per the HEAD rule (45.625 MW); VRE keeps gross = profit;
  a market without ``agent_cashflow`` fails closed for a thermal group.
* StorageHeadroomTests - P5-01 (p07.storage-leftover-headroom, corrected only):
  a 17520-period square wave gives a 400 MW cap for each power battery type
  (per-type since A20; HEAD/doctoral: 0); a 96-period chronology gives zero
  with reason partial_year_chronology; no kernel global is rebound.
* PowerBatteryPoolTests - P5-02 (p07.power-battery-pool), withdrawn by A20
  (r13.per-type-battery-caps, see tests/test_r13_per_type_battery_caps.py):
  under a pre-A20 corrected methodology (pool in force) pool 400 with
  requests 300/200/100 accepts 200/133.33/66.67; doctoral keeps
  per-technology caps (600 in total) and refuses a pooled row.
"""
from __future__ import annotations

import importlib.util
import math
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from gridform_core import agent_cashflow
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCAgentInvestmentDefinition
from gridform_core.methodology import PROFILE_PARAMETER, REFERENCE_PROFILE_ID, default_profile_id
from gridform_core.builtin.scheme_c_1000twh import storage_headroom as sh
from gridform_core.builtin.scheme_c_1000twh.storage import storage_expansion_cap as kernel
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCStorageExpansionPolicyDefinition
from gridform_core.v2.contracts import ExpansionHeadroom, MarketYearResult, OperatingState, PeriodSummary
from tests.r71_planning_fixtures import with_planning

ROOT = Path(__file__).resolve().parents[1]
YEAR = 2030


def _recorder():
    spec = importlib.util.spec_from_file_location("p07_record_head_decide", ROOT / "scripts" / "p07_record_head_decide.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REC = _recorder()
PROFILES = (REFERENCE_PROFILE_ID, default_profile_id())
PER_TYPE_CAPS = "r13.per-type-battery-caps"


@contextmanager
def pre_a20_corrected():
    """The corrected methodology as it was between P0-7 and R1-3 (shared power-battery pool)."""
    from gridform_core.methodology import activate, resolve_methodology

    current = resolve_methodology(default_profile_id())
    assert PER_TYPE_CAPS in current.applied_correction_ids
    pooled = replace(current, applied_correction_ids=tuple(
        item for item in current.applied_correction_ids if item != PER_TYPE_CAPS))
    with activate(pooled):
        yield pooled


def _run(profile_id: str, run_id: str = "p07-toy"):
    run = REC.build_run(run_id)
    return replace(run, scientific_parameters={**dict(run.scientific_parameters), PROFILE_PARAMETER: profile_id})


def _market(income: dict[str, float], rows: dict[str, dict[str, object]] | None) -> MarketYearResult:
    extensions = {} if rows is None else {
        agent_cashflow.EXTENSION_KEY: agent_cashflow.extension(rows, psm_module_id="toy", cost_basis="toy")}
    return MarketYearResult("toy-market", YEAR, "toy", "1", {}, income, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0,
                            extensions=extensions)


def _ccgt_row(mwh: float = 876_000.0) -> dict[str, object]:
    # gen_cost 60 GBP/MWh = generation 0.5 + fuel 40 + carbon 18 + unit time 1.5
    return agent_cashflow.cashflow_row("CCGT", mwh, {
        "generation_cost_gbp_per_mwh": 0.5, "fuel_cost_gbp_per_mwh": 40.0,
        "carbon_cost_gbp_per_mwh": 18.0, "unit_time_cost_gbp_per_mwh": 1.5}, cost_basis="toy")


class ThermalNetRevenueTests(unittest.TestCase):
    """Plan 6.7 P4-01 toys: 100 MW CCGT, 876,000 MWh, CAPEX 4.8e6 GBP/MW, life and target 25 years."""

    def _state(self):
        asset = REC._asset("ccgt-toy", "CCGT", 100.0, capex_per_mw=4_800_000.0, life=25.0, preferred_rate=0.08,
                           target_payback_years=25.0, investment_owner_id="owner-ccgt")
        return with_planning(OperatingState(YEAR, (asset,), ()))

    def _decide(self, profile_id, income, rows):
        return SchemeCAgentInvestmentDefinition().decide(_run(profile_id), self._state(), _market(income, rows), ())

    def test_price_equal_to_marginal_cost_proposes_nothing(self):
        income = {"ccgt-toy": 876_000.0 * 60.0}
        for profile_id in PROFILES:
            with self.subTest(profile=profile_id):
                decision = self._decide(profile_id, income, {"ccgt-toy": _ccgt_row()})
                self.assertEqual(decision.proposals, ())
                self.assertEqual(dict(decision.retirements_mw), {})
                self.assertEqual(decision.extensions["a4_net_revenue"]["thermal_operating_cost_gbp_by_group"],
                                 {"owner-ccgt|CCGT|GB": 876_000.0 * 60.0})

    def test_price_ten_below_marginal_cost_retires_per_rule(self):
        income = {"ccgt-toy": 876_000.0 * 50.0}
        for profile_id in PROFILES:
            with self.subTest(profile=profile_id):
                decision = self._decide(profile_id, income, {"ccgt-toy": _ccgt_row()})
                self.assertEqual(decision.proposals, ())
                # loss 8.76e6 x target 25 / 4.8e6 GBP/MW = 45.625 MW
                self.assertTrue(math.isclose(decision.retirements_mw["ccgt-toy"], 45.625, rel_tol=1e-12))

    def test_rounding_level_loss_is_not_a_retirement(self):
        """A bid-at-cost unit paid its cost up to rounding neither retires ~1e-12 MW nor invests."""
        cost = 876_000.0 * 60.0
        for income in (cost * (1 - 1e-12), cost * (1 + 1e-12)):
            with self.subTest(income=income):
                decision = self._decide(default_profile_id(), {"ccgt-toy": income}, {"ccgt-toy": _ccgt_row()})
                self.assertEqual((decision.proposals, dict(decision.retirements_mw)), ((), {}))
        decision = self._decide(default_profile_id(), {"ccgt-toy": cost * (1 - 1e-6)}, {"ccgt-toy": _ccgt_row()})
        self.assertGreater(decision.retirements_mw["ccgt-toy"], 0.0)

    def test_head_gross_rule_would_have_built_10_95_mw(self):
        """The HEAD (gross) outcome the correction removes, through the same rule with zero running cost."""
        income = {"ccgt-toy": 876_000.0 * 60.0}
        decision = self._decide(REFERENCE_PROFILE_ID, income, {"ccgt-toy": _ccgt_row(0.0)})
        self.assertEqual([(p.capacity_mw, p.extensions["investment_recommendation"]) for p in decision.proposals],
                         [(10.95, "Invest_High")])

    def test_missing_agent_cashflow_fails_closed_for_thermal(self):
        for profile_id in PROFILES:
            with self.subTest(profile=profile_id), self.assertRaisesRegex(ValueError, "agent_cashflow"):
                self._decide(profile_id, {"ccgt-toy": 1.0}, None)
            with self.subTest(profile=profile_id, row="missing"), self.assertRaisesRegex(ValueError, "ccgt-toy"):
                self._decide(profile_id, {"ccgt-toy": 1.0}, {})

    def test_vre_needs_no_cashflow_and_keeps_gross_revenue(self):
        solar = REC._asset("solar-toy", "solar", 10.0, capex_per_mw=600_000.0, investment_owner_id="owner-s")
        state = with_planning(OperatingState(YEAR, (solar,), ()))
        headroom = REC.build_inputs({"id": "toy", "assets": [solar], "income": {"solar-toy": 600_000.0},
                                     "headroom": [{"module_id": "vre-expansion-cap",
                                                   "allowed": {"solar": 100.0}}]})[3]
        for profile_id in PROFILES:
            with self.subTest(profile=profile_id):
                decision = SchemeCAgentInvestmentDefinition().decide(
                    _run(profile_id), state, _market({"solar-toy": 600_000.0}, None), headroom)
                self.assertEqual([(p.capacity_mw, p.extensions["investment_recommendation"])
                                  for p in decision.proposals], [(1.0, "Invest_High")])


def _square_wave(periods: int) -> tuple[tuple[PeriodSummary, ...], list[float]]:
    """Half a day of 1000 MWh/period surplus (curtailed after the fleet charged), half a day of 1000 MWh gap."""
    rows, leftover = [], []
    for period in range(periods):
        surplus = (period % 48) < 24
        rows.append(PeriodSummary(f"p{period}", YEAR, period, "final_dispatch", 1000.0, 1000.0,
                                  1000.0 if surplus else 0.0, 0.0, 0.0, 2000.0 if surplus else 0.0,
                                  1000.0 if surplus else 0.0, 1000.0 if surplus else 0.0, 0.0, 50.0,
                                  0.0, 0.0, 0.0, 0.0))
        leftover.append(1000.0 if surplus else 0.0)
    return tuple(rows), leftover


def _storage_market(periods: int, *, with_trace: bool = True) -> MarketYearResult:
    rows, leftover = _square_wave(periods)
    extensions = {sh.HEADROOM_INPUTS_KEY: sh.headroom_inputs(leftover, basis="excess_plus_curtailed_disjoint",
                                                             psm_module_id="toy")} if with_trace else {}
    return MarketYearResult("toy", YEAR, "toy", "1", {}, {}, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0,
                            period_summaries=rows, extensions=extensions)


class _Policy(SchemeCStorageExpansionPolicyDefinition):
    id = "value-storage-expansion-policy"


class StorageHeadroomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_year = _storage_market(17520)

    def _evaluate(self, profile_id, market, fraction=None):
        run = _run(profile_id)
        if fraction is not None:
            run = replace(run, scientific_parameters={**dict(run.scientific_parameters),
                                                      "expansion.storage_cap_fraction": fraction})
        return _Policy().evaluate(run, OperatingState(YEAR, (), ()), market)

    def test_square_wave_gives_a_400_mw_cap_per_power_battery_in_the_corrected_profile(self):
        before = kernel.CAP_FRACTION
        row = self._evaluate(default_profile_id(), self.full_year)
        self.assertEqual(kernel.CAP_FRACTION, before)
        self.assertIsNone(row.extensions["reason"])
        for tech in sh.POWER_BATTERIES:
            self.assertAlmostEqual(row.allowed_additions_mw[tech], 400.0, delta=1e-6)
        # A20: per-type caps, no shared pool.
        self.assertNotIn("pools", row.extensions)
        self.assertFalse(row.extensions["pooled_power_batteries"])
        self.assertAlmostEqual(row.evidence["power_cap_mw_per_technology"], 400.0, delta=1e-6)
        self.assertAlmostEqual(row.evidence["power_room_mw"], 2000.0, delta=1e-6)
        self.assertAlmostEqual(row.allowed_additions_mw[sh.HYDROGEN_BATTERY], 0.0, delta=1e-6)
        self.assertEqual(row.extensions["headroom_semantics"], sh.HEADROOM_SEMANTICS_PER_TYPE)

    def test_doctoral_profile_keeps_the_head_zero_headroom(self):
        row = self._evaluate(REFERENCE_PROFILE_ID, self.full_year)
        self.assertTrue(all(value == 0.0 for value in row.allowed_additions_mw.values()))
        self.assertNotIn("pools", row.extensions)

    def test_cap_fraction_scales_without_rebinding_the_kernel_global(self):
        before = kernel.CAP_FRACTION
        row = self._evaluate(default_profile_id(), self.full_year, fraction=0.3)
        self.assertEqual(kernel.CAP_FRACTION, before)
        self.assertAlmostEqual(row.allowed_additions_mw["1c_battery"], 600.0, delta=1e-6)

    def test_partial_year_gives_zero_with_a_reason(self):
        row = self._evaluate(default_profile_id(), _storage_market(96))
        self.assertEqual(row.extensions["reason"], "partial_year_chronology")
        self.assertEqual(set(row.allowed_additions_mw.values()), {0.0})
        self.assertNotIn("pools", row.extensions)
        with pre_a20_corrected():
            row = self._evaluate(default_profile_id(), _storage_market(96))
        self.assertEqual(row.extensions["pools"][sh.POWER_BATTERY_POOL]["cap_mw"], 0.0)

    def test_missing_trace_gives_zero_with_a_reason(self):
        row = self._evaluate(default_profile_id(), _storage_market(17520, with_trace=False))
        self.assertEqual(row.extensions["reason"], "leftover_trace_unavailable")
        self.assertEqual(set(row.allowed_additions_mw.values()), {0.0})

    def test_trace_of_the_wrong_length_or_sign_is_refused(self):
        rows, leftover = _square_wave(17520)
        for bad in (leftover[:-1], [-1.0] + leftover[1:]):
            market = MarketYearResult("toy", YEAR, "toy", "1", {}, {}, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0,
                                      period_summaries=rows, extensions={sh.HEADROOM_INPUTS_KEY: sh.headroom_inputs(
                                          bad, basis="x", psm_module_id="toy")})
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                self._evaluate(default_profile_id(), market)


class PowerBatteryPoolTests(unittest.TestCase):
    REQUESTS = {"1c_battery": 300.0, "0.5c_battery": 200.0, "0.25c_battery": 100.0}

    def _fleet(self):
        assets, income = [], {}
        for tech, requested in self.REQUESTS.items():
            asset = REC._asset(f"{tech}-a", tech, 10.0, energy=10.0, investment_owner_id=f"owner-{tech}")
            per_mw = float(asset.extensions["total_capex_gbp"]) / 10.0
            assets.append(asset)
            income[asset.asset_id] = requested * per_mw
        return with_planning(OperatingState(YEAR, tuple(assets), ())), income

    def _row(self, *, pooled: bool):
        extensions = {"headroom_semantics": sh.HEADROOM_SEMANTICS}
        if pooled:
            extensions["pools"] = {sh.POWER_BATTERY_POOL: {"cap_mw": 400.0, "technologies": list(sh.POWER_BATTERIES)}}
        return ExpansionHeadroom("h", YEAR, "value-storage-expansion-policy",
                                 {tech: 400.0 for tech in sh.POWER_BATTERIES}, extensions=extensions)

    def test_pre_a20_corrected_pool_scales_requests_proportionally(self):
        state, income = self._fleet()
        with pre_a20_corrected():
            decision = SchemeCAgentInvestmentDefinition().decide(
                _run(default_profile_id()), state, _market(income, {}), (self._row(pooled=True),))
        accepted = {p.technology: p.capacity_mw for p in decision.proposals}
        self.assertAlmostEqual(accepted["1c_battery"], 200.0, delta=1e-9)
        self.assertAlmostEqual(accepted["0.5c_battery"], 400.0 / 3.0, delta=1e-9)
        self.assertAlmostEqual(accepted["0.25c_battery"], 200.0 / 3.0, delta=1e-9)
        self.assertLessEqual(math.fsum(accepted.values()), 400.0)
        record = decision.extensions["power_battery_pool"]
        self.assertAlmostEqual(record["pool_scale"][sh.POWER_BATTERY_POOL], 400.0 / 600.0)
        self.assertEqual([p.proposal_id for p in decision.proposals],
                         sorted((p.proposal_id for p in decision.proposals),
                                key=lambda item: int(item.rsplit(":", 1)[1])))

    def test_doctoral_keeps_per_technology_copies(self):
        state, income = self._fleet()
        decision = SchemeCAgentInvestmentDefinition().decide(
            _run(REFERENCE_PROFILE_ID), state, _market(income, {}), (self._row(pooled=False),))
        self.assertAlmostEqual(math.fsum(p.capacity_mw for p in decision.proposals), 600.0, delta=1e-9)
        self.assertNotIn("power_battery_pool", decision.extensions)

    def test_doctoral_refuses_a_pooled_row(self):
        state, income = self._fleet()
        with self.assertRaisesRegex(ValueError, "shared pools"):
            SchemeCAgentInvestmentDefinition().decide(
                _run(REFERENCE_PROFILE_ID), state, _market(income, {}), (self._row(pooled=True),))


if __name__ == "__main__":
    unittest.main()
