import importlib.util
import importlib
import hashlib
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from gridform_core.catalog import DATASET_SLOTS, MODULE_REGISTRY, MODULES
from gridform_core.frontend_contract import EXPERIMENTAL_ACK, resolve_study_draft
from gridform_core.module_conformance import check_manifest
from gridform_core.project_revision import project_fingerprint
from gridform_core.run_snapshot import create_run_input_snapshot, verify_run_input_snapshot
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS

from gridform_core.staged_market_contracts import (
    AcceptedAdjustment,
    AheadMarketInput,
    AheadMarketResult,
    BalancingInput,
    BalancingResult,
    FlexibilityBid,
    StagedMarketYearResult,
    contract_sha256,
)
from gridform_core.v2.module_manifest import ModuleRegistryV2
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.v2.contracts import ModuleSelection, ResolvedRun
from gridform_core.v2.orchestrator import checkpoint_identity
from gridform_core.v2.projects import migrate_project_v1


class FixtureBalancingModule:
    id = "fixture-balancing"
    version = "1.0.0"

    def clear(self, model_input):
        return model_input


class StagedMarketContractTests(unittest.TestCase):
    def test_public_staged_contract_module_exists(self):
        """Removing the staged contract module must break the public boundary."""

        self.assertIsNotNone(
            importlib.util.find_spec("gridform_core.staged_market_contracts")
        )

    def test_public_contract_symbols_are_stable(self):
        """Deleting or renaming one public contract must break module authors."""

        module = importlib.import_module("gridform_core.staged_market_contracts")
        for name in (
            "AheadMarketInput",
            "AheadMarketResult",
            "FlexibilityBid",
            "BalancingInput",
            "AcceptedAdjustment",
            "BalancingResult",
            "StagedMarketYearResult",
            "contract_sha256",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(module, name), name)

    def test_contracts_round_trip_with_canonical_hash_links(self):
        """Changing field decoding or canonical order must break replay links."""

        ahead_input = AheadMarketInput(
            run_id="run-1",
            year=2025,
            period=0,
            period_id="2025:0",
            period_hours=0.5,
            information_scope="forecast_only",
            forecast_demand_mwh=50.0,
            offers=(
                {
                    "offer_id": "offer-1",
                    "asset_id": "ccgt-1",
                    "available_mw": 100.0,
                    "price_gbp_per_mwh": 75.0,
                },
            ),
            storage_state_mwh={"battery-1": 4.0},
        )
        ahead_input_hash = contract_sha256(ahead_input)
        ahead_result = AheadMarketResult(
            run_id="run-1",
            year=2025,
            period=0,
            period_id="2025:0",
            information_scope="forecast_only",
            schedule_mwh_by_asset={"ccgt-1": 50.0},
            clearing_price_gbp_per_mwh=75.0,
            accepted_volume_mwh=50.0,
            settlement_mwh_by_asset={"ccgt-1": 50.0},
            storage_scheduled_action_mwh_by_asset={"battery-1": 0.0},
            source_input_sha256=ahead_input_hash,
        )
        bid = FlexibilityBid(
            bid_id="bid-1",
            agent_id="agent-1",
            asset_id="ccgt-1",
            technology="ccgt",
            zone_id="GB",
            period_id="2025:0",
            direction="up",
            available_mw=10.0,
            price_gbp_per_mwh=-5.0,
            baseline_mw=100.0,
            physical_cost_gbp_per_mwh=70.0,
            network_effect_id="GB:injection",
            provenance={"method": "fixture"},
        )
        balancing_input = BalancingInput(
            run_id="run-1",
            year=2025,
            period=0,
            period_id="2025:0",
            ahead_result_sha256=contract_sha256(ahead_result),
            real_demand_mwh=52.0,
            realised_availability_mw_by_asset={"ccgt-1": 100.0},
            initial_soc_mwh_by_asset={"battery-1": 4.0},
            bids=(bid,),
            period_hours=0.5,
            voll_gbp_per_mwh=17000.0,
            domain_payload={"schema_version": "fixture.domain/v1"},
        )
        adjustment = AcceptedAdjustment(
            bid_id="bid-1",
            agent_id="agent-1",
            asset_id="ccgt-1",
            zone_id="GB",
            accepted_delta_mwh=2.0,
            bid_price_gbp_per_mwh=-5.0,
            cashflow_to_agent_gbp=-10.0,
            reason_code="accepted",
        )
        self.assertNotIn("schema_version", adjustment.to_dict())
        balancing_result = BalancingResult(
            run_id="run-1",
            year=2025,
            period=0,
            period_id="2025:0",
            ahead_result_sha256=balancing_input.ahead_result_sha256,
            source_input_sha256=contract_sha256(balancing_input),
            accepted_adjustments=(adjustment,),
            final_dispatch_mwh_by_asset={"ccgt-1": 52.0},
            final_soc_mwh_by_asset={"battery-1": 4.0},
            curtailment_mwh_by_class={"network_added": 0.0},
            blackout_mwh=0.0,
            settlement_cashflow_gbp_by_agent={"agent-1": -10.0},
            resource_cost_gbp_by_class={"thermal": 140.0},
            energy_balance_residual_mwh=0.0,
        )
        self.assertEqual(
            balancing_result.to_dict()["source_input_sha256"],
            contract_sha256(balancing_input),
        )
        year_result = StagedMarketYearResult(
            result_id="staged-2025",
            run_id="run-1",
            year=2025,
            psm_module_id="value-staged-bid-at-cost-psm",
            psm_module_version="1.0.0",
            balancing_module_id="value-copperplate-balancing",
            balancing_module_version="1.0.0",
            ahead_result_sha256_by_period={"2025:0": contract_sha256(ahead_result)},
            balancing_result_sha256_by_period={
                "2025:0": contract_sha256(balancing_result)
            },
        )

        for value in (
            ahead_input,
            ahead_result,
            bid,
            balancing_input,
            adjustment,
            balancing_result,
            year_result,
        ):
            with self.subTest(contract=type(value).__name__):
                payload = json.loads(json.dumps(value.to_dict()))
                restored = type(value).from_dict(payload)
                self.assertEqual(restored, value)
                self.assertEqual(contract_sha256(restored), contract_sha256(value))

    def test_flexibility_bid_rejects_unavailable_invalid_or_nonfinite_values(self):
        """Relaxing bid validation must not admit an unusable market block."""

        valid = {
            "bid_id": "bid-1",
            "agent_id": "agent-1",
            "asset_id": "asset-1",
            "technology": "battery",
            "zone_id": "GB",
            "period_id": "2025:0",
            "direction": "down",
            "available_mw": 1.0,
            "price_gbp_per_mwh": -10.0,
            "baseline_mw": 0.0,
            "physical_cost_gbp_per_mwh": 2.0,
            "network_effect_id": "GB:withdrawal",
            "provenance": {"module_id": "fixture"},
        }
        with self.assertRaisesRegex(ValueError, "direction"):
            FlexibilityBid(**{**valid, "direction": "sideways"})
        with self.assertRaisesRegex(ValueError, "available_mw"):
            FlexibilityBid(**{**valid, "available_mw": 0.0})
        with self.assertRaisesRegex(ValueError, "finite"):
            FlexibilityBid(**{**valid, "price_gbp_per_mwh": float("nan")})

    def test_contracts_freeze_nested_payloads_at_construction(self):
        """Caller mutation must not change a declared market input or its hash."""

        offer = {"asset_id": "asset-1", "metadata": {"source": "declared"}}
        offers = [offer]
        extensions = {"forecast": {"method": "fixture"}}
        value = AheadMarketInput(
            "run-1", 2025, 0, "2025:0", 0.5, "forecast_only", 1.0,
            offers, {}, extensions=extensions,
        )
        digest = contract_sha256(value)
        offer["metadata"]["source"] = "mutated"
        offers.append({"asset_id": "asset-2"})
        extensions["forecast"]["method"] = "mutated"
        self.assertEqual(value.offers[0]["metadata"]["source"], "declared")
        self.assertEqual(len(value.offers), 1)
        self.assertEqual(value.extensions["forecast"]["method"], "fixture")
        self.assertEqual(contract_sha256(value), digest)
        with self.assertRaises(FrozenInstanceError):
            value.period = 2

    def test_balancing_input_rejects_duplicate_or_wrong_period_bids(self):
        """Dropping identity checks must not double-submit or time-shift a bid."""

        bid = FlexibilityBid(
            "bid-1", "agent-1", "asset-1", "ccgt", "GB", "2025:0",
            "up", 1.0, 50.0, 0.0, 45.0, "GB:injection", {"source": "fixture"},
        )
        values = {
            "run_id": "run-1",
            "year": 2025,
            "period": 0,
            "period_id": "2025:0",
            "ahead_result_sha256": "a" * 64,
            "real_demand_mwh": 1.0,
            "realised_availability_mw_by_asset": {"asset-1": 2.0},
            "initial_soc_mwh_by_asset": {},
            "period_hours": 0.5,
            "voll_gbp_per_mwh": 17000.0,
        }
        with self.assertRaisesRegex(ValueError, "Duplicate bid_id"):
            BalancingInput(**values, bids=(bid, bid))
        wrong_period = FlexibilityBid.from_dict(
            {**bid.to_dict(), "bid_id": "bid-2", "period_id": "2025:1"}
        )
        with self.assertRaisesRegex(ValueError, "period_id"):
            BalancingInput(**values, bids=(wrong_period,))

    def test_ahead_contract_rejects_realised_information_and_bad_hash_links(self):
        """Ahead clearing must fail if current realised information leaks in."""

        with self.assertRaisesRegex(ValueError, "realised information"):
            AheadMarketInput(
                "run-1", 2025, 0, "2025:0", 0.5, "forecast_only", 1.0,
                (), {}, extensions={"real_demand_mwh": 1.0},
            )
        with self.assertRaisesRegex(ValueError, "forecast_only"):
            AheadMarketInput(
                "run-1", 2025, 0, "2025:0", 0.5, "perfect_foresight", 1.0,
                (), {},
            )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            AheadMarketResult(
                "run-1", 2025, 0, "2025:0", "forecast_only", {}, 0.0,
                0.0, {}, {}, "not-a-hash",
            )

    def test_adjustment_cashflow_and_year_period_hashes_reconcile(self):
        """Changing settlement signs or dropping one period link must fail closed."""

        with self.assertRaisesRegex(ValueError, "cashflow"):
            AcceptedAdjustment(
                "bid-1", "agent-1", "asset-1", "GB", -2.0, 10.0,
                20.0, "accepted",
            )
        with self.assertRaisesRegex(ValueError, "same periods"):
            StagedMarketYearResult(
                "result-1", "run-1", 2025, "psm", "1.0.0", "balancing",
                "1.0.0", {"2025:0": "a" * 64}, {},
            )
        adjustment = AcceptedAdjustment(
            "bid-1", "agent-1", "asset-1", "GB", 2.0, 10.0,
            20.0, "accepted",
        )
        with self.assertRaisesRegex(ValueError, "settlement_cashflow"):
            BalancingResult(
                run_id="run-1",
                year=2025,
                period=0,
                period_id="2025:0",
                ahead_result_sha256="a" * 64,
                source_input_sha256="b" * 64,
                accepted_adjustments=(adjustment,),
                final_dispatch_mwh_by_asset={"asset-1": 2.0},
                final_soc_mwh_by_asset={},
                curtailment_mwh_by_class={},
                blackout_mwh=0.0,
                settlement_cashflow_gbp_by_agent={"agent-1": 0.0},
                resource_cost_gbp_by_class={},
                energy_balance_residual_mwh=0.0,
            )


class StagedMarketRegistryTests(unittest.TestCase):
    @staticmethod
    def registry() -> ModuleRegistryV2:
        base = MODULE_REGISTRY.manifest("value-bid-at-cost-psm")
        monolithic = replace(
            base,
            id="fixture-monolithic",
            selection_required=True,
            provides_capabilities=("market.year-result",),
            requires_capabilities=(),
        )
        staged = replace(
            base,
            id="fixture-staged",
            selection_required=False,
            provides_capabilities=("market.ahead-schedule/v1",),
            requires_capabilities=("market.balancing/v1",),
        )
        balancing = replace(
            base,
            id="fixture-balancing",
            slot="balancing",
            contract_version="value.balancing-module/v1",
            selection_required=False,
            provides_capabilities=("market.balancing/v1",),
            requires_capabilities=(),
        )
        return ModuleRegistryV2((monolithic, staged, balancing))

    def test_registry_accepts_the_versioned_balancing_slot(self):
        """Removing slot support must prevent every external balancing module."""

        base = MODULE_REGISTRY.manifest("value-bid-at-cost-psm")
        manifest = replace(
            base,
            id="fixture-balancing",
            slot="balancing",
            contract_version="value.balancing-module/v1",
            selection_required=False,
            provides_capabilities=("market.balancing/v1",),
            requires_capabilities=(),
        )
        try:
            registry = ModuleRegistryV2((manifest,))
        except ValueError as exc:
            self.fail(f"balancing slot was rejected: {exc}")
        self.assertEqual(
            registry.manifest("fixture-balancing", expected_slot="balancing"),
            manifest,
        )

    def test_staged_psm_requires_exactly_one_balancing_provider(self):
        """Weakening conditional selection must not launch a half-wired market."""

        registry = self.registry()
        with self.assertRaisesRegex(ValueError, "requires a balancing module"):
            registry.validate_selection({"psm": "fixture-staged"})
        resolved = registry.validate_selection(
            {"psm": "fixture-staged", "balancing": "fixture-balancing"}
        )
        self.assertEqual({row.slot for row in resolved}, {"psm", "balancing"})
        with self.assertRaisesRegex(ValueError, "more than one balancing"):
            registry.validate_selection(
                {
                    "psm": "fixture-staged",
                    "balancing": "fixture-balancing",
                    "balancing_secondary": "fixture-balancing",
                }
            )

    def test_builtin_staged_zonal_composition_declares_attribution_contract(self):
        """A built-in attribution claim must name both sides of the live path."""

        registry = workspace_registry(Path("missing-prompt105-local-modules"))
        staged = registry.manifest(
            "value-staged-bid-at-cost-psm", expected_slot="psm"
        )
        zonal = registry.manifest(
            "value-zonal-redispatch-balancing", expected_slot="balancing"
        )

        self.assertIn("value.vre-counterfactual-snapshot/v1", staged.outputs)
        self.assertIn(
            "evidence.vre-counterfactual-snapshot/v1",
            staged.provides_capabilities,
        )
        self.assertIn("network.zonal-redispatch-result/v1", staged.inputs)
        self.assertIn("network.zonal-redispatch-result/v1", zonal.outputs)

    def test_external_staged_module_without_snapshot_remains_valid_but_unavailable(self):
        """The platform must not infer attribution from an otherwise valid module."""

        registry = self.registry()
        external = replace(
            registry.manifest("fixture-staged"),
            id="fixture-external-staged-without-snapshot",
        )
        registry = ModuleRegistryV2((*registry.manifests().values(), external))
        resolution = resolve_study_draft(
            {
                "schema_version": "value.study-draft/v1",
                "name": "External staged fixture",
                "data_pack_id": "fixture-pack",
                "start_year": 2025,
                "end_year": 2025,
                "modules": {
                    "psm": external.id,
                    "balancing": "fixture-balancing",
                },
            },
            registry=registry,
            module_catalog=(),
            base_dataset_slots=(),
        )

        self.assertTrue(resolution["valid"], resolution["errors"])
        self.assertEqual(resolution["curtailment_attribution"]["status"], "unavailable")
        self.assertEqual(
            resolution["curtailment_attribution"]["reason_code"],
            "module_does_not_provide_counterfactual_snapshot",
        )

        declaring = replace(
            external,
            id="fixture-staged-with-snapshot",
            provides_capabilities=(
                "market.ahead-schedule/v1",
                "evidence.vre-counterfactual-snapshot/v1",
            ),
        )
        zonal = replace(
            registry.manifest("fixture-balancing"),
            id="fixture-zonal-balancing",
            outputs=("network.zonal-redispatch-result/v1",),
        )
        registry = ModuleRegistryV2((*registry.manifests().values(), declaring, zonal))
        base_project = {
            "schema_version": "value.study-draft/v1",
            "name": "Declared snapshot fixture",
            "data_pack_id": "fixture-pack",
            "start_year": 2025,
            "end_year": 2025,
        }
        copperplate = resolve_study_draft(
            {
                **base_project,
                "modules": {
                    "psm": declaring.id,
                    "balancing": "fixture-balancing",
                },
            },
            registry=registry,
            module_catalog=(),
            base_dataset_slots=(),
        )
        self.assertEqual(copperplate["curtailment_attribution"]["status"], "unavailable")
        self.assertEqual(
            copperplate["curtailment_attribution"]["reason_code"],
            "selected_balancing_does_not_provide_final_zonal_dispatch",
        )
        self.assertTrue(
            copperplate["curtailment_attribution"]["selected_psm_declares_snapshot"]
        )
        self.assertFalse(
            copperplate["curtailment_attribution"]
            ["selected_balancing_produces_final_zonal_dispatch"]
        )

        zonal_resolution = resolve_study_draft(
            {
                **base_project,
                "modules": {
                    "psm": declaring.id,
                    "balancing": zonal.id,
                },
            },
            registry=registry,
            module_catalog=(),
            base_dataset_slots=(),
        )
        self.assertTrue(zonal_resolution["valid"], zonal_resolution["errors"])
        self.assertEqual(zonal_resolution["curtailment_attribution"], {
            "capability": "results.vre-curtailment-attribution/v2",
            "status": "available",
            "reason_code": None,
            "selected_psm_declares_snapshot": True,
            "selected_balancing_produces_final_zonal_dispatch": True,
        })

    def test_builtin_staged_drafts_distinguish_zonal_and_copperplate_attribution(self):
        """Only the selected built-in zonal composition enables attribution."""

        registry = workspace_registry(Path("missing-prompt105-local-modules"))
        pack = json.loads(
            (Path("data-packs") / "value-synthetic-contract-pack-v1" / "manifest.json")
            .read_text(encoding="utf-8")
        )
        project = {
            "schema_version": "value.study-draft/v1",
            "name": "Built-in staged attribution fixture",
            "data_pack_id": pack["id"],
            "start_year": 2025,
            "end_year": 2025,
            "modules": {
                "psm": "value-staged-bid-at-cost-psm",
                "balancing": "value-zonal-redispatch-balancing",
                "storage_cost": "dynamic-annual-storage-cost",
                "investment": "agent-investment",
                "pipeline": "planning-pipeline",
                "vre_cap": "vre-expansion-cap",
                "storage_cap": "value-storage-expansion-policy",
                "transition": "value-annual-state-transition",
            },
            "maturity_acknowledgements": {
                "module:value-zonal-redispatch-balancing@"
                + registry.manifest(
                    "value-zonal-redispatch-balancing", expected_slot="balancing"
                ).version: EXPERIMENTAL_ACK,
            },
        }
        zonal = resolve_study_draft(
            {
                **project,
                "market_configuration": {
                    "zonal_demand_mode": "scenario_scaled_zonal_shares",
                },
                "solver_contract": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
            },
            registry=registry,
            module_catalog=MODULES,
            base_dataset_slots=DATASET_SLOTS,
            available_data_roles=tuple(pack["bindings"]),
        )
        copperplate_with_zonal_contract = resolve_study_draft(
            {
                **project,
                "modules": {
                    **project["modules"],
                    "balancing": "value-copperplate-balancing",
                },
                "solver_contract": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
            },
            registry=registry,
            module_catalog=MODULES,
            base_dataset_slots=DATASET_SLOTS,
            available_data_roles=tuple(pack["bindings"]),
        )
        copperplate = resolve_study_draft(
            {
                **project,
                "modules": {
                    **project["modules"],
                    "balancing": "value-copperplate-balancing",
                },
            },
            registry=registry,
            module_catalog=MODULES,
            base_dataset_slots=DATASET_SLOTS,
            available_data_roles=tuple(pack["bindings"]),
        )

        self.assertTrue(zonal["valid"], zonal["errors"])
        self.assertEqual(zonal["curtailment_attribution"]["status"], "available")
        self.assertIsNone(zonal["curtailment_attribution"]["reason_code"])
        self.assertTrue(copperplate["valid"], copperplate["errors"])
        self.assertEqual(copperplate["curtailment_attribution"]["status"], "unavailable")
        self.assertEqual(
            copperplate["curtailment_attribution"]["reason_code"],
            "selected_balancing_does_not_provide_final_zonal_dispatch",
        )
        self.assertFalse(copperplate_with_zonal_contract["valid"])
        self.assertEqual(
            [issue["code"] for issue in copperplate_with_zonal_contract["errors"]],
            ["GF_SOLVER_CONTRACT_MODULE_MISMATCH"],
        )

    def test_monolithic_psm_neither_requires_nor_accepts_balancing(self):
        """Adding a conditional slot must not reinterpret an old Study."""

        registry = self.registry()
        resolved = registry.validate_selection({"psm": "fixture-monolithic"})
        self.assertEqual(tuple(row.slot for row in resolved), ("psm",))
        with self.assertRaisesRegex(ValueError, "only valid with a staged PSM"):
            registry.validate_selection(
                {"psm": "fixture-monolithic", "balancing": "fixture-balancing"}
            )

    def test_wrong_balancing_capability_is_rejected(self):
        """A same-slot module without the balancing capability must not compose."""

        registry = self.registry()
        wrong = replace(
            registry.manifest("fixture-balancing"),
            id="fixture-wrong-balancing",
            provides_capabilities=("market.not-balancing/v1",),
        )
        broken_registry = ModuleRegistryV2(
            (*registry.manifests().values(), wrong)
        )
        with self.assertRaisesRegex(ValueError, "market.balancing/v1"):
            broken_registry.validate_selection(
                {"psm": "fixture-staged", "balancing": "fixture-wrong-balancing"}
            )

    def test_balancing_module_conformance_checks_the_public_clear_method(self):
        """External balancing bundles must be installable through the shared checker."""

        registry = self.registry()
        manifest = replace(
            registry.manifest("fixture-balancing"),
            implementation=f"{__name__}:FixtureBalancingModule",
        )
        conforming_registry = ModuleRegistryV2(
            (
                registry.manifest("fixture-monolithic"),
                registry.manifest("fixture-staged"),
                manifest,
            )
        )
        self.assertEqual(
            check_manifest(conforming_registry, manifest)["status"],
            "passed",
        )

    def test_checkpoint_identity_includes_balancing_only_for_staged_runs(self):
        """A resumed staged run must not silently switch balancing implementation."""

        def resolved_run(modules):
            return ResolvedRun(
                run_id="run-1",
                project_id="project-1",
                scenario_id="scenario-1",
                data_pack_id="pack-1",
                start_year=2025,
                end_year=2026,
                modules=modules,
                scientific_parameters={},
                runtime_controls={},
            )

        psm = ModuleSelection(
            slot="psm",
            module_id="fixture-staged",
            module_version="1.0.0",
            contract_version="value.psm/v2",
        )
        balancing = ModuleSelection(
            slot="balancing",
            module_id="fixture-balancing",
            module_version="1.0.0",
            contract_version="value.balancing-module/v1",
        )
        staged = checkpoint_identity(
            resolved_run({"psm": psm, "balancing": balancing})
        )
        monolithic = checkpoint_identity(resolved_run({"psm": psm}))
        self.assertEqual(staged["modules"]["balancing"]["module_id"], "fixture-balancing")
        self.assertNotIn("balancing", monolithic["modules"])

    def test_existing_project_and_graph_identities_do_not_change(self):
        """Conditional contracts must not alter a saved monolithic identity."""

        selection = {
            "psm": "value-bid-at-cost-psm",
            "investment": "agent-investment",
            "pipeline": "planning-pipeline",
            "vre_cap": "vre-expansion-cap",
            "storage_cap": "value-storage-expansion-policy",
            "storage_cost": "dynamic-annual-storage-cost",
        }
        self.assertEqual(
            MODULE_REGISTRY.resolve_selection(selection).graph_sha256,
            "01a4ff7e0f5d4ff45730960c12655ac9fc08f4e2fa6fd2c711bcd95c399e60ae",
        )
        project = {
            "schema_version": "value.project/v1",
            "id": "p",
            "name": "Display name",
            "data_pack_id": "pack",
            "start_year": 2025,
            "end_year": 2034,
            "modules": selection,
            "parameters": {"planning.random_seed": 7},
            "runtime_options": {"runtime.market_trace_level": "summary"},
        }
        pack = {"schema_version": "value.data-pack/v1", "id": "pack", "bindings": {}}
        self.assertEqual(
            project_fingerprint(project, MODULE_REGISTRY, pack),
            "921bd01e4ce9ca3f23d5dfa0f1df5b580e70b26ad58e967425769cf087fe2a41",
        )
        migrated = migrate_project_v1(project)
        self.assertNotIn("balancing", migrated["modules"])

    def test_workspace_graph_identity_is_independent_of_editable_install_metadata(self):
        """An editable install must not rename unchanged workspace source."""

        selection = {
            "psm": "value-bid-at-cost-psm",
            "investment": "agent-investment",
            "pipeline": "planning-pipeline",
            "vre_cap": "vre-expansion-cap",
            "storage_cap": "value-storage-expansion-policy",
            "storage_cost": "dynamic-annual-storage-cost",
        }
        with patch(
            "gridform_core.v2.module_manifest.importlib.metadata.packages_distributions",
            return_value={},
        ):
            source_graph = MODULE_REGISTRY.resolve_selection(selection)
        with patch(
            "gridform_core.v2.module_manifest.importlib.metadata.packages_distributions",
            return_value={"gridform_core": ["gridform-local"]},
        ):
            editable_graph = MODULE_REGISTRY.resolve_selection(selection)

        self.assertEqual(editable_graph.graph_sha256, source_graph.graph_sha256)
        self.assertEqual(
            editable_graph.identity("psm").distribution,
            "workspace-source",
        )

    def test_staged_snapshot_includes_balancing_but_monolithic_snapshot_does_not(self):
        """Dropping the conditional identity must make replay scientifically ambiguous."""

        registry = self.registry()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pack_root = root / "pack"
            data = pack_root / "files" / "demand.csv"
            data.parent.mkdir(parents=True)
            data.write_bytes(b"1\n")
            digest = hashlib.sha256(b"1\n").hexdigest()
            (pack_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "value.data-pack/v1",
                        "id": "fixture",
                        "bindings": {
                            "demand.real": {
                                "uri": "files/demand.csv",
                                "filename": "demand.csv",
                                "format": "csv",
                                "bytes": 2,
                                "sha256": digest,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            cases = (
                (
                    "staged",
                    {"psm": "fixture-staged", "balancing": "fixture-balancing"},
                    {"psm", "balancing"},
                ),
                ("monolithic", {"psm": "fixture-monolithic"}, {"psm"}),
            )
            for run_id, selected, expected_slots in cases:
                with self.subTest(run_id=run_id):
                    run_dir = root / run_id
                    run_dir.mkdir()
                    snapshot = create_run_input_snapshot(
                        run_dir=run_dir,
                        project={"id": run_id, "modules": selected},
                        pack_root=pack_root,
                        registry=registry,
                        selected=selected,
                        object_root=root / "objects",
                    )
                    self.assertEqual(
                        {row["slot"] for row in snapshot["modules"]}, expected_slots
                    )
                    self.assertEqual(
                        verify_run_input_snapshot(run_dir / "input-snapshot", registry)[
                            "snapshot_id"
                        ],
                        snapshot["snapshot_id"],
                    )

    def test_protocol_schema_and_v2_exports_are_public(self):
        """Omitting public packaging must fail external module development."""

        self.assertIsNotNone(importlib.util.find_spec("gridform_core.balancing"))
        schema_path = (
            Path("gridform_core") / "data" / "contracts" / "staged-market-v1.schema.json"
        )
        self.assertTrue(schema_path.is_file())
        if schema_path.is_file():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$id"], "value.staged-market-contracts/v1")
            self.assertTrue(
                {
                    "AheadMarketInput",
                    "AheadMarketResult",
                    "FlexibilityBid",
                    "BalancingInput",
                    "AcceptedAdjustment",
                    "BalancingResult",
                    "StagedMarketYearResult",
                }.issubset(schema["$defs"]),
            )
        public_v2 = importlib.import_module("gridform_core.v2")
        self.assertTrue(hasattr(public_v2, "BalancingModule"))
        self.assertTrue(hasattr(public_v2, "BalancingInput"))


if __name__ == "__main__":
    unittest.main()
