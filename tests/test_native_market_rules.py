"""P0-6 S2: NativeMarketRules skeleton (no behaviour change)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gridform_core import methodology
from gridform_core.builtin.scheme_c_1000twh import native_market_rules as rules_module
from gridform_core.builtin.scheme_c_1000twh.native_market_rules import (
    CORRECTED,
    DOCTORAL,
    FIELD_CORRECTIONS,
    PENDING_CORRECTION_IDS,
    NativeMarketRules,
    active_rules,
    market_rule_set_record,
    rules_for_methodology,
    storage_bid_basis_source,
)


def _catalogue_with(correction_ids):
    """A temporary catalogue copy that registers ``correction_ids`` as profile-gated."""

    temporary = Path(tempfile.mkdtemp(prefix="p06-rules-"))
    root = temporary / "methodology"
    shutil.copytree(methodology.CATALOGUE_ROOT, root)
    # One file per package (p06 and FX6, decision A16-2): each switch package's
    # file is replaced by exactly the requested ids of that package.
    packages = sorted({correction_id.split(".", 1)[0] for correction_id in FIELD_CORRECTIONS.values()})
    for package in packages:
        payload = {
            "schema_version": methodology.CORRECTIONS_SCHEMA,
            "package": package,
            "notes": ["test copy"],
            "corrections": [
                {
                    "id": correction_id, "package": package, "findings": [], "track": "profile_gated",
                    "scope": "market", "affects": ["trajectory"], "applies_when": {}, "advisory": None,
                    "trigger_fixture": {"test": "tests/test_native_market_rules.py"},
                    "introduced_in": "test", "deviation_signature": None, "description": "test",
                }
                for correction_id in correction_ids if correction_id.split(".", 1)[0] == package
            ],
        }
        (root / "corrections" / f"{package}.json").write_text(json.dumps(payload), encoding="utf-8")
    return temporary, methodology.load_catalogue_from(root)


class RuleSetDefinitionTests(unittest.TestCase):
    def test_the_two_rule_sets_have_distinct_identities(self):
        self.assertNotEqual(DOCTORAL.sha256, CORRECTED.sha256)
        self.assertNotEqual(DOCTORAL.rule_set_id, CORRECTED.rule_set_id)
        self.assertEqual(len(DOCTORAL.sha256), 64)
        # The sha covers every field: one changed value changes it.
        from dataclasses import replace

        self.assertNotEqual(replace(DOCTORAL, reliability_voll="x").sha256, DOCTORAL.sha256)

    def test_plan_table_values(self):
        self.assertEqual(DOCTORAL.switches(), {
            "surplus_accounting": "thesis_marginal_vre_only",
            "ahead_merit_key": "thesis_stable_price",
            "downward_order": "curtail_cost_thesis",
            "storage_position": "per_stage_thesis",
            "storage_fee_carry": "thesis_carry_last_balancing",
            "vre_direct_electrolysis": "thesis_pre_clearing_skim",
            "storage_bid_basis": "thesis_dwell_linear",
            "storage_settlement_basis": "thesis_max_bat_price",
            "reliability_voll": "constant_17000",
            "interconnector_import_stage": "balancing_residual_only",
            "nuclear_initial_state": "off_until_accepted",
            "downward_restart_economics": "not_modelled",
        })
        self.assertEqual(CORRECTED.switches(), {
            "surplus_accounting": "rebuilt_available_minus_accepted",
            "ahead_merit_key": "rounded_price_generation_before_storage",
            "downward_order": "avoided_cost",
            "storage_position": "net_per_period",
            "storage_fee_carry": "per_period",
            "vre_direct_electrolysis": "disabled",
            "storage_bid_basis": "cycle_only",
            "storage_settlement_basis": "uniform_clearing_price",
            "reliability_voll": "chronology_parameter",
            "interconnector_import_stage": "day_ahead_offer_then_balancing_residual",
            "nuclear_initial_state": "in_service_at_start",
            "downward_restart_economics": "restart_cost_vs_avoided_cost_v1",
        })
        # A2: P3-01 dispatch is unchanged in both profiles; P5-06 is universal.
        self.assertEqual(DOCTORAL.realisation_basis, "forecast_thesis")
        self.assertEqual(CORRECTED.realisation_basis, "forecast_thesis")
        self.assertEqual(DOCTORAL.operating_cost_basis, CORRECTED.operating_cost_basis)
        # Every field that differs has a switch.
        differing = {
            name for name, value in DOCTORAL.definition().items()
            if name != "rule_set_id" and CORRECTED.definition()[name] != value
        }
        self.assertEqual(differing, set(FIELD_CORRECTIONS))

    def test_switch_ids_follow_the_catalogue_pattern_and_pending_ids_are_unregistered(self):
        for correction_id in FIELD_CORRECTIONS.values():
            self.assertRegex(correction_id, methodology.CORRECTION_ID_PATTERN)
            # P0-6 switches, plus the FX6 (A16-2), FX8 (A18) and R1-2 (A19/A22)
            # method changes.
            self.assertTrue(correction_id.startswith(("p06.", "fx6.", "fx8.", "r12.")), correction_id)
        self.assertEqual(len(set(FIELD_CORRECTIONS.values())), len(FIELD_CORRECTIONS))
        self.assertLessEqual(PENDING_CORRECTION_IDS, set(FIELD_CORRECTIONS.values()))
        registered = set(methodology.load_catalogue().corrections)
        # The step that implements a switch registers it and removes it from
        # PENDING_CORRECTION_IDS in the same commit.
        self.assertFalse(PENDING_CORRECTION_IDS & registered)


class ResolutionTests(unittest.TestCase):
    def test_profiles_resolve_to_their_complete_rule_sets(self):
        # P0-6 S5-S10 registered every switch in corrections/p06.json: the
        # corrected profile (gated "*") resolves to CORRECTED, the frozen
        # doctoral profile (gated []) to DOCTORAL; nothing is pending.
        self.assertEqual(PENDING_CORRECTION_IDS, frozenset())
        for profile_id in methodology.profile_ids():
            resolved = methodology.resolve_methodology(profile_id)
            rules = rules_for_methodology(resolved)
            expected = DOCTORAL if profile_id == methodology.REFERENCE_PROFILE_ID else CORRECTED
            self.assertIs(rules, expected, profile_id)
            self.assertEqual(rules_module.pending_switches(rules), [])
        catalogue = methodology.load_catalogue()
        for correction_id in FIELD_CORRECTIONS.values():
            self.assertTrue(catalogue.corrections[correction_id].gated, correction_id)

    def test_registered_switches_select_the_corrected_rules_only_where_enabled(self):
        temporary, catalogue = _catalogue_with(FIELD_CORRECTIONS.values())
        self.addCleanup(shutil.rmtree, temporary, True)
        with mock.patch.object(rules_module, "PENDING_CORRECTION_IDS", frozenset()):
            corrected = rules_for_methodology(methodology.resolve_methodology(None, catalogue=catalogue))
            doctoral = rules_for_methodology(
                methodology.resolve_methodology(methodology.REFERENCE_PROFILE_ID, catalogue=catalogue)
            )
        self.assertIs(corrected, CORRECTED)
        self.assertIs(doctoral, DOCTORAL)

    def test_a_partly_registered_catalogue_gives_a_named_partial_rule_set(self):
        temporary, catalogue = _catalogue_with(["p06.storage-bid-cycle-only"])
        self.addCleanup(shutil.rmtree, temporary, True)
        pending = frozenset(FIELD_CORRECTIONS.values()) - {"p06.storage-bid-cycle-only"}
        with mock.patch.object(rules_module, "PENDING_CORRECTION_IDS", pending):
            rules = rules_for_methodology(methodology.resolve_methodology(None, catalogue=catalogue))
            pending_in_record = rules_module.pending_switches(rules)
        self.assertEqual(rules.storage_bid_basis, "cycle_only")
        self.assertEqual(rules.downward_order, DOCTORAL.downward_order)
        self.assertTrue(rules.rule_set_id.startswith(rules_module.PARTIAL_RULE_SET_PREFIX))
        self.assertNotIn("p06.storage-bid-cycle-only", pending_in_record)

    def test_an_unknown_switch_that_is_not_pending_fails_closed(self):
        resolved = methodology.resolve_methodology(None)
        typo = dict(FIELD_CORRECTIONS, storage_bid_basis="p06.storage-bid-cycle-onyl")
        with mock.patch.object(rules_module, "FIELD_CORRECTIONS", typo):
            with self.assertRaises(methodology.UnknownCorrectionError):
                rules_for_methodology(resolved)


class ActiveRulesTests(unittest.TestCase):
    def test_explicit_argument_wins(self):
        runtime = SimpleNamespace(storage_cost=None, market_rules=DOCTORAL)
        self.assertIs(active_rules(CORRECTED, runtime), CORRECTED)
        with self.assertRaises(TypeError):
            active_rules("native-corrected-v1", None)  # type: ignore[arg-type]

    def test_runtime_rules_are_used(self):
        self.assertIs(active_rules(None, SimpleNamespace(market_rules=CORRECTED)), CORRECTED)
        with self.assertRaises(TypeError):
            active_rules(None, SimpleNamespace(market_rules=object()))

    def test_reference_runtime_and_no_runtime_are_doctoral(self):
        from gridform_core.builtin.scheme_c_1000twh.scheme_c_modules import SchemeCModuleRuntime

        reference = SchemeCModuleRuntime(*(SimpleNamespace() for _ in range(6)))
        self.assertIs(active_rules(None, reference), DOCTORAL)
        self.assertIs(active_rules(None, None), DOCTORAL)

    def test_other_configured_runtime_without_rules_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "without market_rules"):
            active_rules(None, SimpleNamespace(storage_cost=object()))

    def test_kernel_reads_the_module_runtime(self):
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat import module_context
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel

        saved = module_context._runtime
        try:
            module_context._runtime = None
            self.assertIs(kernel._active_rules(), DOCTORAL)
            module_context._runtime = SimpleNamespace(storage_cost=object(), market_rules=CORRECTED)
            self.assertIs(kernel._active_rules(), CORRECTED)
            self.assertIs(kernel._active_rules(DOCTORAL), DOCTORAL)
            module_context._runtime = SimpleNamespace(storage_cost=object())
            with self.assertRaises(RuntimeError):
                kernel.run_simulation(1, [], [], [0.0], [0.0], [], None)
        finally:
            module_context._runtime = saved


class StorageRuntimeTests(unittest.TestCase):
    def _sources(self, definition):
        from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import _StorageRuntime

        runtime = _StorageRuntime(definition, {}, DOCTORAL)
        for battery_type in ("1c", "pumped_hydro", "hydrogen"):
            runtime.create(battery_type=battery_type, period_hours=0.5,
                           legacy_storage_fee=1.0, legacy_holding_fee=0.1)
        self.assertIs(runtime.market_rules, DOCTORAL)
        return set(runtime.bid_basis_sources.values()), runtime

    def test_four_storage_module_kinds(self):
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import (
            DynamicStorageCostDefinition,
            SchemeCLegacyStorageCostDefinition,
            UserFormulaStorageCostDefinition,
        )
        from gridform_core.builtin.value_modules import ValueLegacyStorageCost

        class ExternalStorageCost:
            id = "external-storage-cost"

            def create(self, **_kwargs):
                return SimpleNamespace(bid_price=lambda dwell: 0.0)

        self.assertEqual(self._sources(DynamicStorageCostDefinition())[0], {"rule_set"})
        self.assertEqual(self._sources(SchemeCLegacyStorageCostDefinition())[0], {"module_defined"})
        self.assertEqual(self._sources(ValueLegacyStorageCost())[0], {"module_defined"})
        # A subclass of DynamicAnnualStorageCost defines its own bid.
        self.assertEqual(self._sources(UserFormulaStorageCostDefinition())[0], {"module_defined"})
        sources, runtime = self._sources(ExternalStorageCost())
        self.assertEqual(sources, {"module_defined"})
        self.assertEqual(runtime.id, "external-storage-cost")

    def test_storage_bid_basis_source_is_exact_type(self):
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import DynamicAnnualStorageCost

        self.assertEqual(
            storage_bid_basis_source(DynamicAnnualStorageCost(battery_type="1c", period_hours=0.5)),
            "rule_set",
        )
        self.assertEqual(storage_bid_basis_source(object()), "module_defined")


class RecordTests(unittest.TestCase):
    def test_market_rule_set_record(self):
        record = market_rule_set_record(
            DOCTORAL, storage_cost_module_id="dynamic-annual-storage-cost",
            storage_bid_basis_sources={"lithium_battery": "rule_set"},
            runtime_kernel_tree_sha256="a" * 64, voll_gbp_per_mwh=17000.0,
        )
        self.assertEqual(record["rule_set_id"], DOCTORAL.rule_set_id)
        self.assertEqual(record["rule_set_sha256"], DOCTORAL.sha256)
        self.assertEqual(record["rules"], DOCTORAL.definition())
        self.assertEqual(record["pending_switches"], sorted(PENDING_CORRECTION_IDS))
        self.assertEqual(record["voll_gbp_per_mwh"], 17000.0)
        json.dumps(record)  # serialisable
        self.assertEqual(market_rule_set_record(CORRECTED)["pending_switches"], [])
        self.assertIsInstance(DOCTORAL, NativeMarketRules)


if __name__ == "__main__":
    unittest.main()
