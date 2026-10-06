from __future__ import annotations

import importlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gridform_core.catalog import MODULE_REGISTRY
from gridform_core.dispatch_benchmark import solve_fixture
from gridform_core.staged_market_contracts import (
    AheadMarketInput,
    AheadMarketResult,
    BalancingInput,
    FlexibilityBid,
    contract_sha256,
)
from gridform_core.v2.contracts import (
    AssetStateV2,
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
    StorageDispatchResource,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data-packs" / "value-101-baseline-v1"


class FlatStorageCost:
    def __init__(self, price: float = 5.0) -> None:
        self.price = price
        self.current_sold_mwh = 0.0

    def prepare_year(self, year: int, **kwargs) -> None:
        self.year = year
        self.prepared = dict(kwargs)

    def bid_price_gbp_per_mwh(self, dwell_periods: float) -> float:
        return self.price + 0.1 * max(float(dwell_periods), 0.0)

    def record_sale(self, delivered_mwh: float, dwell_periods: float) -> None:
        self.current_sold_mwh += float(delivered_mwh)

    def report(self):
        return {
            "method": "fixture-flat",
            "current_year_sold_mwh": self.current_sold_mwh,
        }


class FlatStorageCostDefinition:
    id = "fixture-storage-cost"
    version = "1.0.0"

    def __init__(self, price: float = 5.0) -> None:
        self.price = price

    def create(self, **kwargs):
        return FlatStorageCost(self.price)


def chronology(
    *,
    forecast: tuple[float, ...],
    actual: tuple[float, ...],
    vre: tuple[float, ...] | None = None,
    thermal_capacity_mw: float = 20.0,
    storage: bool = False,
) -> PSMInput:
    economics = {
        "capital_cost_per_mw": 0.0,
        "capital_cost_per_mwh": 0.0,
        "total_capex_gbp": 0.0,
        "annual_fixed_opex_gbp": 0.0,
        "economic_lifetime_years": 25.0,
        "capital_discount_rate": 0.0,
        "annualized_capital_cost_gbp": 0.0,
        "fixed_om_basis": "test_fixture",
        "asset_economics_schema_version": "value.asset-economics/v1",
    }
    periods = len(actual)
    vre_profile = vre or tuple(0.0 for _ in actual)
    resources = (
        DispatchResource("wind", "onshore", "vre", 10.0, 0.0, vre_profile),
        DispatchResource(
            "ccgt", "CCGT", "thermal", thermal_capacity_mw, 50.0, (1.0,)
        ),
    )
    storage_rows = (
        StorageDispatchResource(
            "battery", "1c", 5.0, 5.0, 10.0, 0.9, 0.9, 5.0, 1.0
        ),
    ) if storage else ()
    assets = (
        AssetStateV2("wind", "onshore", 10.0, extensions=economics),
        AssetStateV2(
            "ccgt", "CCGT", thermal_capacity_mw, extensions=economics
        ),
        *(
            (
                AssetStateV2(
                    "battery",
                    "1c_battery",
                    5.0,
                    10.0,
                    extensions=economics,
                ),
            )
            if storage
            else ()
        ),
    )
    data = ChronologicalPSMData(
        tuple(f"2025:{period}" for period in range(periods)),
        actual,
        resources,
        storage_rows,
        17_000.0,
        terminal_soc_rule="free",
        extensions={"forecast_demand_mwh": forecast},
    )
    return PSMInput(
        "run-1",
        2025,
        "fixture-pack",
        OperatingState(2025, assets, ()),
        1.0,
        {"market.bid_multiplier": 1.0},
        chronology=data,
    )


def boundary_chronology(*, export: bool) -> PSMInput:
    model_input = chronology(
        forecast=(10.0 if export else 5.0,),
        actual=(5.0,),
        vre=(1.0 if export else 0.0,),
    )
    assert model_input.chronology is not None
    resources = list(model_input.chronology.resources)
    extensions = dict(model_input.chronology.extensions)
    if export:
        extensions.update({
            "boundary_export_envelope_mwh_by_asset": {"export:france": (5.0,)},
            "boundary_export_price_gbp_per_mwh_by_asset": {"export:france": (80.0,)},
        })
    else:
        resources.append(DispatchResource(
            "import:france",
            "interconnector_import",
            "import",
            10.0,
            20.0,
            (1.0,),
            extensions={"agent_id": "interconnector:france"},
        ))
    return PSMInput(
        model_input.run_id,
        model_input.year,
        model_input.data_pack_id,
        model_input.operating_state,
        model_input.period_hours,
        model_input.parameters,
        chronology=ChronologicalPSMData(
            model_input.chronology.period_ids,
            model_input.chronology.demand_mwh,
            tuple(resources),
            model_input.chronology.storage,
            model_input.chronology.voll_gbp_per_mwh,
            terminal_soc_rule="free",
            extensions=extensions,
        ),
    )


class Prompt95PublicModuleTests(unittest.TestCase):
    def test_staged_modules_exist(self):
        self.assertIsNotNone(
            importlib.util.find_spec(
                "gridform_core.builtin.scheme_c_1000twh.staged_psm"
            )
        )
        self.assertIsNotNone(
            importlib.util.find_spec(
                "gridform_core.builtin.scheme_c_1000twh.copperplate_balancing"
            )
        )

    def test_frozen_module_identities_are_registered(self):
        staged = MODULE_REGISTRY.manifest(
            "value-staged-bid-at-cost-psm", expected_slot="psm"
        )
        balancing = MODULE_REGISTRY.manifest(
            "value-copperplate-balancing", expected_slot="balancing"
        )
        self.assertEqual(staged.version, "1.4.0")  # P0-8 S7 (economic dec pricing) 1.3.0; FX5 (VoLL 17000) 1.4.0
        self.assertEqual(balancing.version, "1.1.0")  # P0-8 S7 (pro-rata ties)
        self.assertIn("market.ahead-schedule/v1", staged.provides_capabilities)
        self.assertIn("market.balancing/v1", balancing.provides_capabilities)
        self.assertIn("domain.single_node", balancing.provides_capabilities)

    def test_frontend_preset_composes_the_staged_psm_with_balancing(self):
        from gridform_core.catalog import MODULES
        from gridform_core.frontend_contract import system_domain_presets

        presets = system_domain_presets(
            MODULE_REGISTRY,
            {
                "psm": "value-bid-at-cost-psm",
                "storage_cost": "dynamic-annual-storage-cost",
                "investment": "agent-investment",
                "pipeline": "planning-pipeline",
                "vre_cap": "vre-expansion-cap",
                "storage_cap": "value-storage-expansion-policy",
                "transition": "value-annual-state-transition",
            },
        )
        staged = next(
            row for row in presets
            if row["psm_module_id"] == "value-staged-bid-at-cost-psm"
        )
        self.assertTrue(staged["available"], staged["unavailable_reason"])
        self.assertEqual(
            staged["recommended_modules"]["balancing"],
            "value-copperplate-balancing",
        )


class CopperplateBalancingTests(unittest.TestCase):
    @staticmethod
    def ahead_result() -> AheadMarketResult:
        source = AheadMarketInput(
            "run-1",
            2025,
            0,
            "2025:0",
            1.0,
            "forecast_only",
            10.0,
            (),
            {},
        )
        return AheadMarketResult(
            "run-1",
            2025,
            0,
            "2025:0",
            "forecast_only",
            {"ccgt": 10.0},
            50.0,
            10.0,
            {"ccgt": 10.0},
            {},
            contract_sha256(source),
        )

    @classmethod
    def balancing_input(cls, *, ahead_hash: str | None = None) -> BalancingInput:
        ahead = cls.ahead_result()
        bid = FlexibilityBid(
            "up-ccgt",
            "ccgt",
            "ccgt",
            "CCGT",
            "GB",
            "2025:0",
            "up",
            10.0,
            50.0,
            10.0,
            50.0,
            "GB:injection",
            {"resource_class": "thermal"},
        )
        return BalancingInput(
            "run-1",
            2025,
            0,
            "2025:0",
            ahead_hash or contract_sha256(ahead),
            12.0,
            {"ccgt": 20.0},
            {},
            (bid,),
            1.0,
            17_000.0,
            domain_payload={
                "schema_version": "value.copperplate-balancing-domain/v1",
                "ahead_result": ahead.to_dict(),
                "resource_cost_gbp_per_mwh_by_asset": {"ccgt": 50.0},
                "resource_class_by_asset": {"ccgt": "thermal"},
                "storage": {},
            },
        )

    def test_balancing_consumes_frozen_ahead_result_once(self):
        module = importlib.import_module(
            "gridform_core.builtin.scheme_c_1000twh.copperplate_balancing"
        ).CopperplateBalancing()
        value = self.balancing_input()
        result = module.clear(value)
        self.assertEqual(result.final_dispatch_mwh_by_asset["ccgt"], 12.0)
        self.assertEqual(result.blackout_mwh, 0.0)
        self.assertAlmostEqual(result.energy_balance_residual_mwh, 0.0)
        self.assertEqual(result.source_input_sha256, contract_sha256(value))
        with self.assertRaisesRegex(ValueError, "already been balanced"):
            module.clear(value)

    def test_mutated_ahead_hash_fails_closed(self):
        module = importlib.import_module(
            "gridform_core.builtin.scheme_c_1000twh.copperplate_balancing"
        ).CopperplateBalancing()
        with self.assertRaisesRegex(ValueError, "ahead result hash"):
            module.clear(self.balancing_input(ahead_hash="f" * 64))


class StagedBidAtCostPSMTests(unittest.TestCase):
    def test_profiled_resource_offer_uses_period_cost_for_physical_accounting(self):
        model_input = chronology(forecast=(5.0,), actual=(5.0,))
        assert model_input.chronology is not None
        profiled = DispatchResource(
            "profiled-import",
            "interconnector_import",
            "import",
            10.0,
            100.0,
            (1.0,),
            marginal_cost_profile_gbp_per_mwh=(40.0,),
        )
        model_input = PSMInput(
            model_input.run_id,
            model_input.year,
            model_input.data_pack_id,
            model_input.operating_state,
            model_input.period_hours,
            {"market.bid_multiplier": 2.0},
            chronology=ChronologicalPSMData(
                model_input.chronology.period_ids,
                model_input.chronology.demand_mwh,
                (profiled,),
                (),
                model_input.chronology.voll_gbp_per_mwh,
                terminal_soc_rule="free",
                extensions=model_input.chronology.extensions,
            ),
        )

        [offer] = importlib.import_module(
            "gridform_core.builtin.scheme_c_1000twh.staged_psm"
        ).StagedBidAtCostPSM._ahead_offers(model_input, 0, {}, {})

        self.assertEqual(offer["price_gbp_per_mwh"], 80.0)
        self.assertEqual(offer["physical_cost_gbp_per_mwh"], 40.0)

    def test_value_copperplate_summary_ledger_does_not_require_zonal_accounting(self):
        from gridform_core.builtin.value_modules import (
            ValueCopperplateBalancing,
            ValueStagedBidAtCostPSM,
        )

        with tempfile.TemporaryDirectory() as temporary:
            module = ValueStagedBidAtCostPSM()
            balancing = ValueCopperplateBalancing()
            module.configure_run(
                output_dir=Path(temporary),
                storage_cost=FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                ledger_detail="summary",
            )

            result = module.run(
                chronology(forecast=(10.0,), actual=(12.0,), vre=(0.5,))
            )

        self.assertAlmostEqual(result.total_operational_cost_gbp, 350.0)

    @staticmethod
    def modules(output_dir: Path):
        staged_module = importlib.import_module(
            "gridform_core.builtin.scheme_c_1000twh.staged_psm"
        ).StagedBidAtCostPSM()
        balancing_module = importlib.import_module(
            "gridform_core.builtin.scheme_c_1000twh.copperplate_balancing"
        ).CopperplateBalancing()
        staged_module.configure_run(
            output_dir=output_dir,
            storage_cost=FlatStorageCostDefinition(),
            balancing=balancing_module,
            expected_balancing_identity=("value-copperplate-balancing", "1.0.0"),
        )
        return staged_module, balancing_module

    def test_one_period_declares_ahead_before_realised_balancing(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _balancing = self.modules(Path(temporary))
            result = module.run(
                chronology(forecast=(10.0,), actual=(12.0,), vre=(0.5,))
            )
            self.assertAlmostEqual(result.generation_mwh_by_asset["wind"], 5.0)
            self.assertAlmostEqual(result.generation_mwh_by_asset["ccgt"], 7.0)
            self.assertAlmostEqual(result.total_operational_cost_gbp, 350.0)
            self.assertAlmostEqual(result.total_blackout_mwh, 0.0)
            self.assertAlmostEqual(
                result.period_summaries[0].energy_balance_residual_mwh, 0.0
            )
            self.assertEqual(
                result.extensions["balancing_module"],
                {"module_id": "value-copperplate-balancing", "module_version": "1.0.0"},
            )

            records = [
                json.loads(line)
                for line in (
                    Path(temporary) / "market" / "staged-market.jsonl"
                ).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [row["contract_type"] for row in records],
                [
                    "AheadMarketInput",
                    "AheadMarketResult",
                    "BalancingInput",
                    "BalancingResult",
                ],
            )
            for row in records[:2]:
                text = json.dumps(row["payload"], sort_keys=True)
                self.assertNotIn("real_demand_mwh", text)
                self.assertNotIn("realised_availability", text)

    def test_stale_balancing_identity_is_rejected_before_run(self):
        module = importlib.import_module(
            "gridform_core.builtin.scheme_c_1000twh.staged_psm"
        ).StagedBidAtCostPSM()
        balancing = importlib.import_module(
            "gridform_core.builtin.scheme_c_1000twh.copperplate_balancing"
        ).CopperplateBalancing()
        with self.assertRaisesRegex(ValueError, "balancing identity"):
            module.configure_run(
                output_dir=None,
                storage_cost=FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=("other-module", "1.0.0"),
            )

    def test_storage_soc_uses_final_charge_idle_and_discharge_not_ahead_schedule(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _balancing = self.modules(Path(temporary))
            result = module.run(
                chronology(
                    forecast=(10.0, 0.0, 10.0),
                    actual=(5.0, 0.0, 10.0),
                    vre=(1.0, 0.0, 0.0),
                    storage=True,
                )
            )
            records = [
                json.loads(line)
                for line in (
                    Path(temporary) / "market" / "staged-market.jsonl"
                ).read_text(encoding="utf-8").splitlines()
            ]
            balanced = [
                row["payload"]
                for row in records
                if row["contract_type"] == "BalancingResult"
            ]
            self.assertAlmostEqual(
                balanced[0]["final_soc_mwh_by_asset"]["battery"], 9.5
            )
            self.assertAlmostEqual(
                balanced[1]["final_soc_mwh_by_asset"]["battery"], 9.5
            )
            self.assertAlmostEqual(
                balanced[2]["final_soc_mwh_by_asset"]["battery"],
                9.5 - 5.0 / 0.9,
            )
            self.assertAlmostEqual(
                result.extensions["storage_cost_observations"]["battery"][
                    "current_year_sold_mwh"
                ],
                5.0,
            )

    def test_24_hour_equal_forecast_fixture_matches_transparent_copperplate_reference(self):
        forecast = tuple(6.0 + float(period % 7) for period in range(48))
        vre = tuple(0.2 + 0.05 * float(period % 5) for period in range(48))
        with tempfile.TemporaryDirectory() as temporary:
            module, _balancing = self.modules(Path(temporary))
            result = module.run(
                chronology(forecast=forecast, actual=forecast, vre=vre)
            )

        for period, summary in enumerate(result.period_summaries):
            wind = 10.0 * vre[period]
            reference = solve_fixture({
                "demand_mwh": forecast[period],
                "offers": [
                    {
                        "asset_id": "wind",
                        "capacity_mwh": wind,
                        "marginal_cost_gbp_per_mwh": 0.0,
                    },
                    {
                        "asset_id": "ccgt",
                        "capacity_mwh": 20.0,
                        "marginal_cost_gbp_per_mwh": 50.0,
                    },
                ],
            })
            self.assertAlmostEqual(
                summary.accepted_supply_mwh,
                reference["accepted_supply_mwh"],
                delta=1e-8,
            )
            self.assertAlmostEqual(
                summary.physical_resource_cost_gbp,
                reference["physical_resource_cost_gbp"],
                delta=1e-8,
            )
            self.assertAlmostEqual(summary.blackout_mwh, reference["blackout_mwh"])

    def test_signed_interconnector_import_and_export_envelopes_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            import_module, _ = self.modules(Path(temporary) / "import")
            import_result = import_module.run(boundary_chronology(export=False))
            export_module, _ = self.modules(Path(temporary) / "export")
            export_result = export_module.run(boundary_chronology(export=True))
            records = [
                json.loads(line)
                for line in (
                    Path(temporary) / "export" / "market" / "staged-market.jsonl"
                ).read_text(encoding="utf-8").splitlines()
            ]

        self.assertAlmostEqual(
            import_result.generation_mwh_by_asset["import:france"], 5.0
        )
        self.assertAlmostEqual(import_result.period_summaries[0].import_mwh, 5.0)
        balancing = next(
            row["payload"] for row in records
            if row["contract_type"] == "BalancingResult"
        )
        self.assertAlmostEqual(
            balancing["final_dispatch_mwh_by_asset"]["export:france"], -5.0
        )
        self.assertAlmostEqual(
            balancing["settlement_cashflow_gbp_by_agent"]["interconnector:france"],
            -400.0,
        )
        self.assertAlmostEqual(export_result.total_excess_mwh, 0.0)

    def test_live_application_invokes_both_selected_staged_modules(self):
        from gridform_core.application import run_project_application
        from gridform_core.value_101 import value_101_study

        study = value_101_study()
        study["modules"]["psm"] = "value-staged-bid-at-cost-psm"
        study["modules"]["balancing"] = "value-copperplate-balancing"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            console = io.StringIO()
            with redirect_stdout(console), redirect_stderr(console):
                result = run_project_application(
                    study,
                    run_id="prompt95-live-staged-value-101",
                    pack_root=BASELINE,
                    output_dir=output,
                    mode="tutorial",
                )
            typed = json.loads(
                (output / "year-results-v2.json").read_text(encoding="utf-8")
            )
            resolved = json.loads(
                (output / "resolved-run.json").read_text(encoding="utf-8")
            )
            eligibility = json.loads(
                (output / "comparison-eligibility.json").read_text(encoding="utf-8")
            )

        self.assertEqual(
            result["orchestrator_results"][0]["market"]["module_id"],
            "value-staged-bid-at-cost-psm",
        )
        self.assertTrue(
            typed[0]["market"]["extensions"]["live_staged_clearing_invocation"]
        )
        self.assertEqual(
            typed[0]["market"]["extensions"]["balancing_module"]["module_id"],
            "value-copperplate-balancing",
        )
        self.assertEqual(
            resolved["modules"]["balancing"]["module_id"],
            "value-copperplate-balancing",
        )
        self.assertEqual(
            eligibility["demand_authority_mode"],
            "copperplate_scenario_demand",
        )
        self.assertEqual(len(eligibility["annual_input_evidence"]), len(typed))
        self.assertTrue(eligibility["network_cost_attribution_candidate"])

    def test_same_pack_two_period_thermal_case_matches_live_monolithic_dispatch(self):
        from gridform_core.builtin.scheme_c_1000twh.scheme_c_context import (
            build_scheme_c_run_context,
        )
        from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import (
            SchemeCNativePSM,
        )
        from gridform_core.canonical_psm_data import build_chronology, native_initial_state
        from gridform_core.data_method import run_policy

        manifest = json.loads((BASELINE / "manifest.json").read_text(encoding="utf-8"))
        source_state = native_initial_state(
            BASELINE, 2025, scientific_parameters={}
        )
        ccgt = next(asset for asset in source_state.assets if asset.asset_id == "CCGT")
        operating = OperatingState(2025, (ccgt,), ())
        chronology_data = build_chronology(
            BASELINE,
            manifest,
            operating,
            periods=2,
            period_hours=0.5,
            data_policy=run_policy(manifest),
            terminal_soc_rule="free",
        )
        model_input = PSMInput(
            "prompt95-same-pack",
            2025,
            "value-101-baseline-v1",
            operating,
            0.5,
            {"market.bid_multiplier": 1.0},
            chronology=chronology_data,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            monolithic_output = root / "monolithic"
            monolithic_output.mkdir(parents=True)
            (monolithic_output / "session").mkdir()
            context = build_scheme_c_run_context(
                run_id="prompt95-monolithic",
                project_id="prompt95-parity",
                start_year=2025,
                end_year=2025,
                periods=2,
                scenario_id="existing_decarb_base",
                pack_root=BASELINE,
                output_dir=monolithic_output,
                reference_work_dir=monolithic_output / "session",
                module_ids={"psm": "value-bid-at-cost-psm"},
                scientific_parameters={"clock.period_hours": 0.5},
                runtime_options={"runtime.market_trace_level": "full"},
                environment={},
            )
            monolithic = SchemeCNativePSM()
            monolithic.configure_run(
                context,
                MODULE_REGISTRY.resolve(
                    "dynamic-annual-storage-cost", expected_slot="storage_cost"
                ),
            )
            console = io.StringIO()
            with redirect_stdout(console), redirect_stderr(console):
                old_result = monolithic.run(model_input)
            staged, _ = self.modules(root / "staged")
            new_result = staged.run(model_input)

        self.assertAlmostEqual(
            new_result.generation_mwh_by_asset["CCGT"],
            old_result.generation_mwh_by_asset["CCGT"],
            delta=1e-8,
        )
        self.assertAlmostEqual(
            new_result.total_operational_cost_gbp,
            old_result.total_operational_cost_gbp,
            delta=1e-8,
        )
        self.assertAlmostEqual(new_result.total_blackout_mwh, 0.0, delta=1e-8)


if __name__ == "__main__":
    unittest.main()
