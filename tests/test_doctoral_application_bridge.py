"""Application routing and annual-boundary guards with controlled stubs."""
from dataclasses import replace
import unittest
from unittest.mock import patch, Mock

from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import (
    SchemeCPlanningPipelineDefinition, SchemeCStateTransitionDefinition)
from gridform_core.errors import ContractError
from gridform_core.v2.contracts import (
    InvestmentDecision, MarketYearResult, ModuleSelection, ResolvedRun, YearState)
from gridform_core.v2.orchestrator import AnnualModelOrchestratorV2


class UpdatedPlanning(SchemeCPlanningPipelineDefinition):
    def advance_year(self, run, state):
        result = super().advance_year(run, state)
        return replace(result, operating_state=replace(result.operating_state,
            extensions={**result.operating_state.extensions, "planning_marker": "updated"}))


class StubMarket:
    id, version = "fixture-market", "1.0.0"
    def run(self, model_input):
        return MarketYearResult("test", model_input.year, self.id, self.version,
            {}, {}, 0, 0, 0, 0, 0, 0, 0)


class StubInvestment:
    id, version = "fixture-investment", "1.0.0"
    calls = 0
    def decide(self, run, state, market, caps):
        self.calls += 1
        return InvestmentDecision("test", state.year, self.id, (), {})


class ApplicationBridgeTests(unittest.TestCase):
    def setup_runner(self, psm=None):
        pipeline, transition, investment = UpdatedPlanning(), SchemeCStateTransitionDefinition(), StubInvestment()
        psm = psm or StubMarket()
        choices = {"psm": psm, "pipeline": pipeline, "investment": investment, "transition": transition}
        run = ResolvedRun("test", "test", "basic", "fixture", 2025, 2025,
            {slot: ModuleSelection(slot, module.id, module.version, "fixture") for slot, module in choices.items()},
            {"clock.period_hours": 0.5}, {})
        return AnnualModelOrchestratorV2(psm, {}, investment, pipeline, transition), run, investment

    def test_operating_extensions_are_not_discarded_at_annual_transition(self):
        runner, run, _ = self.setup_runner()
        result = runner.run(run, YearState(2025, (), (), extensions={"planning_marker": "stale", "unrelated": 42}))[0]
        self.assertEqual(result.next_state.extensions["planning_marker"], "updated")
        self.assertEqual(result.next_state.extensions["unrelated"], 42)

    def test_diagnostic_doctoral_span_never_reaches_annual_investment(self):
        class Partial(StubMarket):
            def run(self, model_input):
                return replace(super().run(model_input), extensions={
                    "doctoral_alignment_profile": "value.doctoral-national/v1",
                    "doctoral_cashflow_inputs": {"period_coverage": {"annual_complete": False, "period_count": 2}}})
        runner, run, investment = self.setup_runner(Partial())
        with self.assertRaisesRegex(ContractError, "17520|annual"):
            runner.run(run, YearState(2025, (), ()))
        self.assertEqual(investment.calls, 0)

    def test_application_selects_doctoral_input_builder_only_for_explicit_module(self):
        from gridform_core import application
        self.assertTrue(callable(getattr(application, "_doctoral_native_input", None)),
                        "application has no doctoral native input bridge")
        model = Mock()
        run = Mock(run_id="run", scientific_parameters={"clock.period_hours": 0.5}, runtime_controls={})
        with patch.object(application, "build_doctoral_psm_input", return_value=model) as builder:
            result = application._doctoral_native_input(run, "pack", {"id": "pack"}, "state", 2)
        self.assertIs(result, model)
        self.assertEqual(builder.call_args.kwargs["periods"], 2)
        self.assertEqual(builder.call_args.kwargs["period_hours"], 0.5)

    def test_complete_physical_label_does_not_bypass_unresolved_annual_cem_contract(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import _hash
        class Unresolved(StubMarket):
            def run(self, model_input):
                # Deliberate contract stub: no scientific annual run is made.
                return replace(super().run(model_input), extensions={
                    "doctoral_alignment_profile": "value.doctoral-national/v1",
                    "doctoral_annual_cem_ready": False,
                    "doctoral_runtime": {}, "doctoral_runtime_sha256": _hash({}),
                    "doctoral_cashflow_inputs": {"period_coverage": {
                        "annual_complete": True, "period_count": 17520, "year": 2025,
                        "start_period_index": 0, "end_period_index_exclusive": 17520}}})
        runner, run, investment = self.setup_runner(Unresolved())
        with self.assertRaisesRegex(ContractError, "CEM"):
            runner.run(run, YearState(2025, (), ()))
        self.assertEqual(investment.calls, 0)


if __name__ == "__main__":
    unittest.main()
