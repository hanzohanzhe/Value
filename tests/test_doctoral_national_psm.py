"""Bounded tests of the registered national PSM, not annual CEM evidence."""
from dataclasses import replace
import importlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gridform_core.builtin.scheme_c_1000twh.doctoral_market import _hash
from test_doctoral_market_factory import model_input, gas_parameters, pumped_parameters

MODULE = "gridform_core.builtin.scheme_c_1000twh.doctoral_national_psm"


class DoctoralNationalPSMTests(unittest.TestCase):
    def psm(self, directory):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "registered doctoral national PSM is missing")
        instance = importlib.import_module(MODULE).DoctoralNationalPSM()
        instance.configure_run(output_dir=Path(directory),
            fleet_parameters={"generators": {"CCGT": gas_parameters()}, "connections": {}},
            battery_parameters={"pumpedhydro_battery": pumped_parameters()},
            frozen_data_identity={"data_pack_sha256": "a" * 64, "weather_sha256": "b" * 64,
                                  "nuclear_policy_sha256": "c" * 64})
        return instance

    def inputs(self):
        model = model_input()
        chronology = replace(model.chronology, extensions={
            **model.chronology.extensions, "forecast_demand_mwh": (10.0, 12.0)})
        return replace(model, chronology=chronology, extensions={
            "doctoral_alignment_profile": "value.doctoral-national/v1"})

    def test_actual_periods_reach_cashflow_and_result_without_pretending_annual_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            instance = self.psm(directory)
            result = instance.run(self.inputs())
            self.assertEqual(result.module_id, "value-doctoral-national-psm")
            self.assertEqual(result.total_demand_mwh, 22.0)
            self.assertEqual(result.generation_mwh_by_asset["CCGT"], 22.0)
            self.assertEqual(result.total_blackout_mwh, 0)
            self.assertEqual(len(result.period_summaries), 2)
            cash = result.extensions["doctoral_cashflow_inputs"]
            self.assertEqual(cash["operating_cost_gbp_by_asset"]["CCGT"], 22 * 22)
            self.assertFalse(cash["period_coverage"]["annual_complete"])
            self.assertFalse(result.extensions["scientific_release_eligible"])
            self.assertEqual(result.extensions["doctoral_runtime"]["engine"]["state"]["next_period_index"], 2)

    def test_checkpoint_resume_restores_cumulative_result_not_just_latest_segment(self):
        with tempfile.TemporaryDirectory() as directory:
            instance = self.psm(directory)
            model = self.inputs()
            first = instance.run(model, stop_after_period=1)
            self.assertEqual(first.total_demand_mwh, 10.0)
            instance = self.psm(directory)
            resumed = instance.run(model)
            with tempfile.TemporaryDirectory() as clean:
                uninterrupted = self.psm(clean).run(model)
            self.assertEqual(resumed.to_dict(), uninterrupted.to_dict())

    def test_checkpoint_requires_its_bound_settlement_detail_file(self):
        with tempfile.TemporaryDirectory() as directory:
            model = self.inputs()
            self.psm(directory).run(model, stop_after_period=1)
            detail = Path(directory)/'doctoral-settlement-details'/str(model.year)/'00000.json'
            self.assertTrue(detail.is_file())
            detail.write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Settlement detail missing or hash mismatch'):
                self.psm(directory).run(model)

    def test_uncalibrated_cost_profile_fails_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            model = self.inputs()
            model = replace(model,extensions={**model.extensions,'doctoral_cost_profile':'thermal_extra_costs'})
            with self.assertRaisesRegex(ValueError,'uncalibrated'):
                self.psm(directory).run(model)
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_forecast_and_profile_are_explicit_and_context_drift_cannot_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            instance = self.psm(directory)
            model = self.inputs()
            bad = replace(model, chronology=replace(model.chronology, extensions={}))
            with self.assertRaisesRegex(ValueError, "forecast"):
                instance.run(bad)
            with self.assertRaisesRegex(ValueError, "profile"):
                instance.run(replace(model, extensions={}))
            instance.run(model, stop_after_period=1)
            changed = replace(model, parameters={"market.bid_multiplier": 1.01})
            with self.assertRaisesRegex(ValueError, "identity"):
                self.psm(directory).run(changed)

    def test_manifest_resolves_to_this_live_engine(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE))
        from gridform_core.v2.module_manifest import workspace_registry
        registry = workspace_registry()
        manifest = registry.manifest("value-doctoral-national-psm", expected_slot="psm")
        self.assertEqual(manifest.implementation, MODULE + ":DoctoralNationalPSM")
        self.assertEqual(manifest.status, "experimental")

    def test_complete_year_costs_are_validated_before_dispatch_or_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            instance = self.psm(directory)
            model = self.inputs()
            chronology = replace(model.chronology,
                period_ids=tuple(f"2025:{i}" for i in range(17520)),
                demand_mwh=(10.0,) * 17520,
                extensions={"forecast_demand_mwh": (10.0,) * 17520})
            with patch(MODULE + ".from_doctoral_psm_input") as factory:
                with self.assertRaisesRegex(ValueError, "annual_fixed_opex_gbp"):
                    instance.run(replace(model, chronology=chronology))
                factory.assert_not_called()
            self.assertFalse((Path(directory) / "doctoral-checkpoints").exists())

    def test_negative_or_boolean_annual_cost_is_rejected(self):
        module = importlib.import_module(MODULE)
        self.assertTrue(hasattr(module, "_annual_costs"), "annual cost validation is missing")
        model = self.inputs()
        for value in (-1, True):
            state = replace(model.operating_state, assets=(replace(model.operating_state.assets[0],
                extensions={"annual_fixed_opex_gbp": value, "annualized_capital_cost_gbp": 1}),))
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "annual_fixed_opex_gbp"):
                module._annual_costs(state)

    def test_resume_summary_must_match_cash_and_physical_accumulator(self):
        module = importlib.import_module(MODULE)
        self.assertTrue(hasattr(module, "_validate_summaries"), "summary reconciliation is missing")
        with tempfile.TemporaryDirectory() as directory:
            result = self.psm(directory).run(self.inputs())
            summaries = list(result.period_summaries)
            summaries[0] = replace(summaries[0], market_payment_gbp=summaries[0].market_payment_gbp + 1)
            with self.assertRaisesRegex(ValueError, "market_payment_gbp"):
                module._validate_summaries(summaries, self.inputs(), result.extensions["physical_totals"])
            summaries = list(result.period_summaries)
            summaries[0] = replace(summaries[0], period=1)
            with self.assertRaisesRegex(ValueError, "period identity"):
                module._validate_summaries(summaries, self.inputs(), result.extensions["physical_totals"])

    def test_runtime_adapter_drift_cannot_reuse_an_unchanged_physical_engine_checkpoint(self):
        module = importlib.import_module(MODULE)
        self.assertTrue(hasattr(module, "_runtime_identity"), "PSM/ledger/factory identity is missing")
        with tempfile.TemporaryDirectory() as directory:
            model = self.inputs()
            first = self.psm(directory)
            result = first.run(model, stop_after_period=1)
            identity = result.extensions["doctoral_runtime"]["identity"]
            self.assertIn("runtime_implementation_sha256", identity)
            changed = {**module._runtime_identity(), "deliberate_adapter_change": "fixture"}
            with patch.object(module, "_runtime_identity", return_value=changed):
                with self.assertRaisesRegex(ValueError, "identity"):
                    self.psm(directory).run(model)


if __name__ == "__main__":
    unittest.main()
