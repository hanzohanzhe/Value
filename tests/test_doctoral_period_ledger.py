"""Bounded period accumulation, authenticated continuation and cashflow tests."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
import unittest

from gridform_core.builtin.scheme_c_1000twh.doctoral_state import DoctoralRuntimeState, StorageBatch
from gridform_core.asset_economics import build_asset_economic_extensions
from gridform_core.v2.contracts import AssetStateV2, ExpansionHeadroom, MarketYearResult, OperatingState, ResolvedRun


MODULE = "gridform_core.builtin.scheme_c_1000twh.doctoral_period_ledger"
INPUT_HASH, RULE_HASH = "a" * 64, "b" * 64
WEATHER_HASH = "c" * 64


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def initial_state(local=0, absolute=0):
    return DoctoralRuntimeState(2025, local, absolute, {}, {}, {
        "solar": {"kind": "ExpensiverenewableGenerator", "real_gen_energy": 0.0,
                  "run_time": 0.0, "if_curtail": False}}, ())


def outcome(before):
    memory = {name: dict(row) for name, row in before.generator_memory.items()}
    memory["solar"]["real_gen_energy"] = 20.0
    after = before.commit_period(storage_batches=before.storage_batches,
        generator_memory=memory, accepted_generator_ids=("solar",))
    return {
        "state_sha256": digest(before.to_dict()), "input_sha256": INPUT_HASH,
        "ahead_sha256": digest({"before": before.to_dict(), "forecast_mw": 20}),
        "next_state": after.to_dict(), "forecast_demand_mwh": 10.0, "actual_demand_mwh": 10.0,
        "generation_mwh_by_asset": {"solar": 10.0},
        "ahead_income_gbp_by_asset": {"solar": 40.0},
        "balancing_income_gbp_by_asset": {"solar": 5.0},
        "operating_cost_gbp_by_asset": {"solar": 5.0},
        "ahead_scheduled_mwh_by_asset": {"solar": 10.0},
        "upward_accepted_mwh_by_asset": {"solar": 0.0},
        "downward_accepted_mwh_by_asset": {"solar": 0.0},
        "upward_income_gbp_by_asset": {"solar": 5.0},
        "downward_cash_gbp_by_asset": {"solar": 0.0},
        "legacy_downward_fee_gbp_by_asset": {"solar": 0.0},
        "fuel_cost_gbp_by_asset": {"solar": 0.0},
        "carbon_cost_gbp_by_asset": {"solar": 0.0},
        "other_operating_cost_gbp_by_asset": {"solar": 5.0},
        "export_mwh_by_asset": {"solar": 0.0},
        "export_receipt_gbp_by_asset": {"solar": 0.0},
        "storage_charge_mwh": 0.0, "storage_discharge_mwh": 0.0,
        "export_mwh": 0.0, "import_mwh": 0.0, "vre_available_mwh": 10.0,
        "vre_curtailed_mwh": 0.0, "blackout_mwh": 0.0, "non_vre_spill_mwh": 0.0,
        "storage_decay_loss_mwh": 0.0, "storage_conversion_loss_mwh": 0.0,
        "storage_numerical_discard_mwh": 0.0,
        "energy_balance_residual_mwh": 0.0,
        "raw_source_cost_components": {
            "ahead_generator_price_times_source_quantity": 80.0,
            "ahead_storage": 0.0, "balancing": 10.0, "balancing_storage": 0.0,
            "curtailment": 0.0, "imports_included_in_balancing": 0.0},
    }


def economic_state():
    ext = build_asset_economic_extensions("solar", 100, energy_capacity_mwh=None,
        capital_costs_per_mw={"solar": 1}, lifetimes={"solar": 25}, discount_rate=.05,
        source_record_id="solar")
    ext.update(investment_owner_id="owner", investment_eligible=True, preferred_rate=.08,
               target_payback_years=25)
    return OperatingState(2025, (AssetStateV2("solar", "solar", 100, region="GB", extensions=ext),), ())


class DoctoralPeriodLedgerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "bounded doctoral period ledger is missing")
        self.module = importlib.import_module(MODULE)

    def ledger(self, state=None, asset_ids=("solar",)):
        return self.module.DoctoralPeriodLedger(run_id="bounded-test", input_sha256=INPUT_HASH,
            source_rule_sha256=RULE_HASH, weather_sha256=WEATHER_HASH,
            initial_state=state or initial_state(), asset_ids=asset_ids)

    def restore(self, snapshot, anchor):
        return self.module.DoctoralPeriodLedger.from_snapshot(snapshot,
            expected_input_sha256=INPUT_HASH, expected_source_rule_sha256=RULE_HASH,
            expected_weather_sha256=WEATHER_HASH, expected_prefix_sha256=anchor)

    def test_two_periods_accumulate_cash_and_energy_without_double_half_hour(self):
        ledger = self.ledger()
        first = outcome(ledger.current_state)
        ledger.append(first)
        ledger.append(outcome(ledger.current_state))
        totals = ledger.totals
        self.assertEqual(ledger.period_count, 2)
        self.assertEqual(totals["generation_mwh_by_asset"], {"solar": 20})
        self.assertEqual(totals["actual_demand_mwh"], 20)
        self.assertEqual(totals["operating_cost_gbp_by_asset"], {"solar": 10})
        self.assertEqual(totals["raw_source_cost_components"]["ahead_generator_price_times_source_quantity"], 160)
        self.assertEqual(totals["source_cost_components_gbp"]["ahead_generator_price_times_source_quantity"], 80)
        self.assertEqual(totals["source_cost_components_gbp"]["balancing"], 10)
        self.assertNotIn("total_source_cost_gbp", totals, "overlapping source fee components are not additive")
        first["ahead_income_gbp_by_asset"]["solar"] = 999
        self.assertEqual(ledger.doctoral_cashflow_inputs()["ahead_income_gbp_by_asset"], {"solar": 80})

    def test_json_interrupt_resume_has_identical_final_prefix_state_and_totals(self):
        uninterrupted = self.ledger()
        uninterrupted.append(outcome(uninterrupted.current_state))
        snapshot = json.loads(json.dumps(uninterrupted.snapshot(), allow_nan=False))
        resumed = self.restore(snapshot, uninterrupted.prefix_sha256)
        second = outcome(uninterrupted.current_state)
        uninterrupted.append(second)
        resumed.append(second)
        self.assertEqual(resumed.snapshot(), uninterrupted.snapshot())

    def test_nonzero_explicit_start_clock_is_retained_without_inventing_a_prefix(self):
        ledger = self.ledger(initial_state(local=7, absolute=17527))
        ledger.append(outcome(ledger.current_state))
        self.assertEqual(ledger.current_state.next_period_index, 8)
        self.assertEqual(ledger.current_state.next_absolute_period, 17528)
        self.assertEqual(ledger.period_count, 1)
        self.assertEqual(ledger.snapshot()["header"]["initial_state"]["next_period_index"], 7)

    def test_empty_ledger_can_roundtrip_with_its_trusted_initial_anchor(self):
        ledger = self.ledger()
        self.assertEqual(self.restore(ledger.snapshot(), ledger.prefix_sha256).snapshot(), ledger.snapshot())

    def test_duplicate_skipped_and_different_identity_outcomes_are_rejected_atomically(self):
        ledger = self.ledger()
        first = outcome(ledger.current_state)
        ledger.append(first)
        good = outcome(ledger.current_state)
        mutations = [first, {**good, "input_sha256": "c" * 64},
            {**good, "state_sha256": "d" * 64}]
        for field, value in (("year", 2026), ("next_period_index", 4), ("next_absolute_period", 4)):
            bad = deepcopy(good)
            bad["next_state"][field] = value
            mutations.append(bad)
        before = ledger.snapshot()
        for bad in mutations:
            with self.subTest(bad=bad["next_state"]), self.assertRaises(ValueError):
                ledger.append(bad)
            self.assertEqual(ledger.snapshot(), before)

    def test_missing_unknown_or_nonfinite_asset_money_never_becomes_zero(self):
        for field in self.module.ASSET_MAP_FIELDS:
            for bad_map in ({}, {"solar": 1, "ghost": 0}, {"solar": float("nan")}, {"solar": True}):
                ledger = self.ledger()
                bad = outcome(ledger.current_state)
                bad[field] = bad_map
                with self.subTest(field=field, bad_map=bad_map), self.assertRaises(ValueError):
                    ledger.append(bad)
                self.assertEqual(ledger.period_count, 0)

    def test_missing_losses_raw_component_or_nonfinite_scalar_are_rejected(self):
        for field in ("storage_conversion_loss_mwh", "storage_decay_loss_mwh", "storage_numerical_discard_mwh", "non_vre_spill_mwh"):
            ledger = self.ledger()
            bad = outcome(ledger.current_state)
            del bad[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                ledger.append(bad)
        ledger = self.ledger()
        bad = outcome(ledger.current_state)
        del bad["raw_source_cost_components"]["imports_included_in_balancing"]
        with self.assertRaises(ValueError):
            ledger.append(bad)
        bad = outcome(ledger.current_state)
        bad["actual_demand_mwh"] = float("inf")
        with self.assertRaises(ValueError):
            ledger.append(bad)

    def test_reported_balance_cannot_hide_non_vre_spill_or_fake_soc(self):
        ledger = self.ledger()
        bad = outcome(ledger.current_state)
        bad["non_vre_spill_mwh"] = 2
        with self.assertRaisesRegex(ValueError, "balance"):
            ledger.append(bad)
        bad = outcome(ledger.current_state)
        bad["storage_conversion_loss_mwh"] = 1
        with self.assertRaisesRegex(ValueError, "storage"):
            ledger.append(bad)

    def test_storage_stock_change_is_reconciled_with_separate_losses(self):
        before = initial_state(local=1, absolute=1)
        before = replace(before, storage_capacities_mwh={"store": 10},
                         storage_batches={"store": (StorageBatch(0, 5),)})
        ledger = self.ledger(before, ("solar", "store"))
        item = outcome(before)
        for field in self.module.ASSET_MAP_FIELDS:
            item[field]["store"] = 0.0
        item["storage_charge_mwh"] = 2
        item["actual_demand_mwh"] = 8
        item["storage_decay_loss_mwh"] = .1
        item["storage_conversion_loss_mwh"] = .4
        item["next_state"]["storage_batches"]["store"] = [
            {"charged_absolute_period": 0, "stored_energy_mwh": 4.9},
            {"charged_absolute_period": 1, "stored_energy_mwh": 1.6}]
        ledger.append(item)
        self.assertAlmostEqual(ledger.current_state.storage_energy_mwh("store"), 6.5)
        self.assertEqual(ledger.totals["storage_decay_loss_mwh"], .1)
        self.assertEqual(ledger.totals["storage_conversion_loss_mwh"], .4)

    def test_scalar_actor_totals_must_match_the_identified_generation(self):
        for field in ("storage_discharge_mwh", "import_mwh", "vre_available_mwh", "vre_curtailed_mwh"):
            ledger = self.ledger()
            bad = outcome(ledger.current_state)
            bad[field] += 1
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    ledger.append(bad)
                self.assertEqual(ledger.period_count, 0)

    def test_aggregate_storage_overflow_is_rejected_even_when_each_asset_is_finite(self):
        before = initial_state(local=1, absolute=1)
        before = replace(before, storage_capacities_mwh={"one": 1e308, "two": 1e308},
            storage_batches={"one": (StorageBatch(0, 1e308),), "two": (StorageBatch(0, 1e308),)})
        ledger = self.ledger(before, ("solar", "one", "two"))
        item = outcome(before)
        for field in self.module.ASSET_MAP_FIELDS:
            item[field].update(one=0, two=0)
        with self.assertRaisesRegex(ValueError, "finite"):
            ledger.append(item)
        self.assertEqual(ledger.period_count, 0)

    def test_real_engine_two_period_storage_cashflow_and_json_resume(self):
        from gridform_core.builtin.scheme_c_1000twh import doctoral_market_kernel as k
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine

        def engine(checkpoint=None):
            wind = k.ExpensiverenewableGenerator("wind", 2, 3, 0, 0, 0, 0, 0, .6, 0, 0)
            wind.capacity_limit = 100
            gas = k.GasGenerator("gas", 50, 3, 0, 100, 100, 7, 0, 0, 0, 0, 0, 0)
            store = k.Battery("store", 200, 50, 10, 1, 1, .8, 0, battery_type="1c")
            return DoctoralPeriodEngine([wind, gas], [store], year=2025, checkpoint=checkpoint)

        original = engine()
        ledger = self.module.DoctoralPeriodLedger(run_id="typed-two-periods", input_sha256=original.input_sha256,
            source_rule_sha256=digest(original.rule_identity), weather_sha256=WEATHER_HASH,
            initial_state=original.state, asset_ids=("wind", "gas", "store"))
        first = original.realise_period(original.plan_period(50), 50)
        ledger.append(first)
        original.commit(first)
        replay_engine = engine(json.loads(json.dumps(original.export_state())))
        replay_ledger = self.module.DoctoralPeriodLedger.from_snapshot(json.loads(json.dumps(ledger.snapshot())),
            expected_input_sha256=original.input_sha256, expected_source_rule_sha256=digest(original.rule_identity),
            expected_weather_sha256=WEATHER_HASH, expected_prefix_sha256=ledger.prefix_sha256)
        for active_engine, active_ledger in ((original, ledger), (replay_engine, replay_ledger)):
            second = active_engine.realise_period(active_engine.plan_period(20, available_mw_by_vre={"wind": 0}), 20)
            active_ledger.append(second)
            active_engine.commit(second)
        self.assertEqual(replay_ledger.snapshot(), ledger.snapshot())
        self.assertEqual(replay_engine.export_state(), original.export_state())
        self.assertEqual(ledger.current_state.to_dict(), original.state.to_dict())
        self.assertEqual(ledger.totals["generation_mwh_by_asset"], {"wind": 50, "gas": 0, "store": 10})
        self.assertEqual(ledger.totals["storage_charge_mwh"], 25)
        self.assertEqual(ledger.totals["storage_discharge_mwh"], 10)
        self.assertAlmostEqual(ledger.totals["storage_decay_loss_mwh"], 25 * .000021)
        self.assertAlmostEqual(ledger.totals["storage_conversion_loss_mwh"], 10 * (1 / .8 - 1))
        self.assertFalse(ledger.coverage["annual_complete"])

    def test_real_negative_import_price_is_signed_cost_and_survives_json(self):
        from gridform_core.builtin.scheme_c_1000twh import doctoral_market_kernel as k
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
        solar = k.ExpensiverenewableGenerator("solar", 2, 3, 0, 0, 0, 0, 0, .6, 0, 0)
        solar.capacity_limit = 0
        connection = k.Connection("import", 0, 0, 0)
        connection.doctoral_transfer_constraint_mw_by_period = (10, 30)
        connection.doctoral_external_price_gbp_per_mwh_by_period = (-5, -7)
        engine = DoctoralPeriodEngine([solar], [], connections=[connection], year=2025)
        ledger = self.module.DoctoralPeriodLedger(run_id="negative-import", input_sha256=engine.input_sha256,
            source_rule_sha256=digest(engine.rule_identity), weather_sha256=WEATHER_HASH,
            initial_state=engine.state, asset_ids=("solar", "import"))
        for energy, cost in ((5, -25), (15, -105)):
            item = engine.realise_period(engine.plan_period(0), 100)
            self.assertEqual(item.import_mwh, energy)
            self.assertEqual(item.operating_cost_gbp_by_asset["import"], cost)
            ledger.append(item)
            engine.commit(item)
        self.assertEqual(ledger.totals["operating_cost_gbp_by_asset"]["import"], -130)
        self.assertEqual(ledger.build_asset_accounts(economic_state(), {"scenario": "basic"})["solar"]["net_revenue_gbp"], 0)
        resumed = self.module.DoctoralPeriodLedger.from_snapshot(json.loads(json.dumps(ledger.snapshot())),
            expected_input_sha256=engine.input_sha256, expected_source_rule_sha256=digest(engine.rule_identity),
            expected_weather_sha256=WEATHER_HASH, expected_prefix_sha256=ledger.prefix_sha256)
        self.assertEqual(resumed.snapshot(), ledger.snapshot())

    def test_negative_domestic_operating_cost_still_fails_closed(self):
        ledger = self.ledger()
        bad = outcome(ledger.current_state)
        bad["operating_cost_gbp_by_asset"]["solar"] = -1
        with self.assertRaises(ValueError):
            ledger.append(bad)

    def test_recomputed_content_hash_does_not_authenticate_changed_cumulative_money(self):
        ledger = self.ledger()
        ledger.append(outcome(ledger.current_state))
        forged = ledger.snapshot()
        forged["cumulative"]["ahead_income_gbp_by_asset"]["solar"] += 100
        forged["content_sha256"] = digest({key: value for key, value in forged.items() if key != "content_sha256"})
        with self.assertRaisesRegex(ValueError, "accumulator|prefix"):
            self.restore(forged, ledger.prefix_sha256)

    def test_untrusted_self_consistent_prefix_is_rejected_against_callers_anchor(self):
        ledger = self.ledger()
        ledger.append(outcome(ledger.current_state))
        forged = ledger.snapshot()
        forged["prefix_sha256"] = "f" * 64
        forged["content_sha256"] = digest({key: value for key, value in forged.items() if key != "content_sha256"})
        with self.assertRaisesRegex(ValueError, "prefix"):
            self.restore(forged, ledger.prefix_sha256)

    def test_snapshot_requires_content_identity_and_complete_chain(self):
        ledger = self.ledger()
        ledger.append(outcome(ledger.current_state))
        ledger.append(outcome(ledger.current_state))
        for field in ("content_sha256", "entries", "current_state"):
            bad = ledger.snapshot()
            if field == "content_sha256":
                bad[field] = "f" * 64
            elif field == "entries":
                bad[field].pop(0)
                bad["content_sha256"] = digest({key: value for key, value in bad.items() if key != "content_sha256"})
            else:
                bad[field]["generator_memory"]["solar"]["real_gen_energy"] += 1
                bad["content_sha256"] = digest({key: value for key, value in bad.items() if key != "content_sha256"})
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.restore(bad, ledger.prefix_sha256)

    def test_real_cashflow_builder_reaches_investment_once_and_policy_stays_explicit(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_policy import decide_doctoral_investment
        ledger = self.ledger()
        ledger.append(outcome(ledger.current_state))
        ledger.append(outcome(ledger.current_state))
        state = economic_state()
        accounts = ledger.build_asset_accounts(state, {"scenario": "basic"})
        self.assertEqual(accounts["solar"]["net_revenue_gbp"], 80)
        run = ResolvedRun("ledger", "p", "basic", "fixture", 2025, 2025, {}, {}, {})
        market = MarketYearResult("m", 2025, "fixture", "1", {}, {}, 0, 0, 0, 0, 0, 0, 0)
        caps = (ExpansionHeadroom("h", 2025, "vre-expansion-cap", {"solar": 100}),)
        decision = decide_doctoral_investment(run, state, market, caps, accounts)
        self.assertEqual([(p.agent_id, p.capacity_mw) for p in decision.proposals], [("owner", 80)])
        with self.assertRaises(ValueError):
            ledger.build_asset_accounts(state, {"scenario": "with_cm"})
        with self.assertRaises(ValueError):
            ledger.build_asset_accounts(state, {"scenario": "decarb", "cm_income_gbp_by_asset": {}})
        supported = ledger.build_asset_accounts(state, {"scenario": "decarb",
            "cm_income_gbp_by_asset": {"solar": 10}, "decarb_income_gbp_by_asset": {"solar": 20}})
        self.assertEqual(supported["solar"]["net_revenue_gbp"], 110)

    def test_external_connection_cash_is_retained_but_asset_view_is_explicit(self):
        ledger = self.ledger(asset_ids=("solar", "import"))
        item = outcome(ledger.current_state)
        for field in self.module.ASSET_MAP_FIELDS:
            item[field]["import"] = 0
        item["operating_cost_gbp_by_asset"]["import"] = 7
        item["other_operating_cost_gbp_by_asset"]["import"] = 7
        ledger.append(item)
        self.assertEqual(ledger.doctoral_cashflow_inputs()["operating_cost_gbp_by_asset"]["import"], 7)
        self.assertEqual(ledger.build_asset_accounts(economic_state(), {"scenario": "basic"})["solar"]["net_revenue_gbp"], 40)
        with self.assertRaises(ValueError):
            ledger.doctoral_cashflow_inputs(asset_ids=("ghost",))


if __name__ == "__main__":
    unittest.main()
