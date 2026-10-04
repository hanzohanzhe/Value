import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.v2.contracts import (
    AssetStateV2,
    ExpansionHeadroom,
    InvestmentDecision,
    InvestmentProposal,
    MarketYearResult,
    ModuleSelection,
    OperatingState,
    PlanningAdmissionResult,
    PlanningAdvanceResult,
    ResolvedRun,
    YearState,
)
from gridform_core.v2.orchestrator import AnnualModelOrchestratorV2, json_checkpoint_writer, load_json_checkpoint


VERSIONS = {
    "pipeline": ("spy-pipeline", "1.0"),
    "psm": ("spy-psm", "1.0"),
    "storage_cap": ("spy-storage", "1.0"),
    "vre_cap": ("spy-vre", "1.0"),
    "investment": ("spy-investment", "1.0"),
    "transition": ("spy-transition", "1.0"),
}


def resolved_run(end_year=2026):
    return ResolvedRun(
        "run", "project", "scenario", "pack", 2025, end_year,
        {
            slot: ModuleSelection(slot, module_id, version, f"value.{slot}/v2")
            for slot, (module_id, version) in VERSIONS.items()
        },
        {"clock.period_hours": 0.5},
        {},
    )


class PipelineSpy:
    id, version = VERSIONS["pipeline"]

    def __init__(self, calls): self.calls = calls

    def advance_year(self, run, state):
        self.calls.append((state.year, "planning.advance"))
        operating = OperatingState(state.year, state.assets, state.planning_projects)
        return PlanningAdvanceResult(state.year, operating, state.planning_projects, (), (), (), ())

    def admit_projects(self, run, state, proposals):
        self.calls.append((state.year, "planning.admit", len(proposals)))
        return PlanningAdmissionResult(state.year, (), (), (), ())


class PSMSpy:
    id, version = VERSIONS["psm"]

    def __init__(self, calls): self.calls = calls

    def run(self, model_input):
        self.calls.append((model_input.year, "psm", len(model_input.operating_state.assets)))
        return MarketYearResult(
            f"market:{model_input.year}", model_input.year, self.id, self.version,
            {"solar": 1.0}, {}, 10.0, 4.0, 6.0, 1.0, 1.0, 0.0, 0.0,
        )


class CapSpy:
    version = "1.0"

    def __init__(self, slot, calls):
        self.slot, self.id, self.calls = slot, VERSIONS[slot][0], calls

    def evaluate(self, run, state, market):
        self.calls.append((market.year, self.slot))
        return ExpansionHeadroom(f"{self.id}:{market.year}", market.year, self.id, {self.slot: 5.0})


class InvestmentSpy:
    id, version = VERSIONS["investment"]

    def __init__(self, calls): self.calls = calls

    def decide(self, run, state, market, headroom):
        self.calls.append((market.year, "investment", tuple(item.module_id for item in headroom)))
        proposal = InvestmentProposal(
            f"proposal:{market.year}", market.year, "agent", "solar", 1.0,
            "Scotland", market.year + 2,
        )
        return InvestmentDecision(f"decision:{market.year}", market.year, self.id, (proposal,), {})


class TransitionSpy:
    id, version = VERSIONS["transition"]

    def __init__(self, calls): self.calls = calls

    def apply(self, run, current_state, planning, investment):
        self.calls.append((current_state.year, "transition", len(investment.proposals)))
        return YearState(current_state.year + 1, current_state.assets, planning.next_pipeline)


class OrchestratorV2Tests(unittest.TestCase):
    def build(self, calls, events):
        return AnnualModelOrchestratorV2(
            PSMSpy(calls),
            {"vre_cap": CapSpy("vre_cap", calls), "storage_cap": CapSpy("storage_cap", calls)},
            InvestmentSpy(calls), PipelineSpy(calls), TransitionSpy(calls),
            event_sink=events.append,
        )

    def test_selected_modules_receive_data_in_two_phase_order(self):
        calls, events = [], []
        initial = YearState(2025, (AssetStateV2("solar", "solar", 10.0),), ())
        results = self.build(calls, events).run(resolved_run(), initial)
        self.assertEqual([result.year for result in results], [2025, 2026])
        per_year = [item[1] for item in calls if item[0] == 2025]
        self.assertEqual(per_year, [
            "planning.advance", "psm", "storage_cap", "vre_cap",
            "investment", "planning.admit", "transition",
        ])
        investment_call = next(item for item in calls if item[1] == "investment")
        self.assertEqual(investment_call[2], ("spy-storage", "spy-vre"))
        self.assertEqual(results[-1].next_state.year, 2027)
        self.assertEqual(len(events), 14)
        self.assertTrue(all(len(event.input_state_sha256) == 64 for event in events))
        self.assertTrue(all(len(event.output_state_sha256) == 64 for event in events))
        self.assertTrue(all(event.contract_version.endswith("/v2") for event in events))
        self.assertTrue(all(event.duration_seconds >= 0 for event in events))
        self.assertTrue(all(event.module_id.startswith("spy-") for event in events))

    def test_unvalidated_solver_status_is_inherited_while_later_cem_executes(self):
        calls, observed_states = [], {}
        cause = {
            "schema_version": "value.solver-validation-summary/v1",
            "annual_status": "COMPLETED_WITH_NUMERICAL_WARNING",
            "study_status": "COMPLETED_WITH_NUMERICAL_WARNING",
            "solver_validated": False,
            "inherited_unvalidated": False,
            "first_causal_period": {
                "year": 2025,
                "period": 7,
                "period_id": "2025:7",
                "phase_id": "primary_bid_cost",
                "validation_class": "COMPLETED_WITH_NUMERICAL_WARNING",
            },
        }

        class StatusPSM(PSMSpy):
            def run(self, model_input):
                observed_states[model_input.year] = dict(
                    model_input.operating_state.extensions
                )
                market = super().run(model_input)
                summary = (
                    cause
                    if model_input.year == 2025
                    else model_input.operating_state.extensions[
                        "solver_validation_state"
                    ]
                )
                return replace(
                    market,
                    extensions={"solver_validation_summary": dict(summary)},
                )

        class PreservingPipeline(PipelineSpy):
            def advance_year(self, run, state):
                result = super().advance_year(run, state)
                return replace(
                    result,
                    operating_state=replace(
                        result.operating_state,
                        extensions=dict(state.extensions),
                    ),
                )

        class PreservingTransition(TransitionSpy):
            def apply(self, run, current_state, planning, investment):
                state = super().apply(
                    run, current_state, planning, investment
                )
                return replace(state, extensions=dict(current_state.extensions))

        orchestrator = AnnualModelOrchestratorV2(
            StatusPSM(calls),
            {
                "vre_cap": CapSpy("vre_cap", calls),
                "storage_cap": CapSpy("storage_cap", calls),
            },
            InvestmentSpy(calls),
            PreservingPipeline(calls),
            PreservingTransition(calls),
        )
        results = orchestrator.run(
            resolved_run(), YearState(2025, (), ())
        )

        self.assertEqual([result.year for result in results], [2025, 2026])
        self.assertEqual(
            observed_states[2026]["solver_validation_state"], cause
        )
        self.assertEqual(
            [call[0] for call in calls if call[1] == "investment"],
            [2025, 2026],
        )

    def test_wrong_selected_implementation_fails_before_any_stage(self):
        calls, events = [], []
        orchestrator = self.build(calls, events)
        orchestrator.psm.id = "not-selected"
        with self.assertRaisesRegex(ValueError, "Selected psm"):
            orchestrator.run(resolved_run(2025), YearState(2025, (), ()))
        self.assertEqual(calls, [])
        self.assertEqual(events, [])

    def test_state_year_and_nonnegative_capacity_invariants(self):
        calls, events = [], []
        orchestrator = self.build(calls, events)
        with self.assertRaisesRegex(ValueError, "Initial state year"):
            orchestrator.run(resolved_run(2025), YearState(2024, (), ()))

        class BadTransition(TransitionSpy):
            def apply(self, run, current_state, planning, investment):
                return YearState(
                    current_state.year + 1,
                    (AssetStateV2("bad", "solar", -1.0),), (),
                )

        orchestrator.transition = BadTransition(calls)
        with self.assertRaisesRegex(ValueError, "negative"):
            orchestrator.run(resolved_run(2025), YearState(2025, (), ()))

    def test_atomic_checkpoint_resumes_deterministically_into_year_two(self):
        run = resolved_run()
        initial = YearState(2025, (AssetStateV2("solar", "solar", 10.0),), ())
        uninterrupted = self.build([], []).run(run, initial)
        with tempfile.TemporaryDirectory() as folder:
            writer = json_checkpoint_writer(Path(folder), run)
            writer(uninterrupted[0].next_state)
            checkpoint = Path(folder) / "state-2026.json"
            payload = json.loads(checkpoint.read_text("utf-8"))
            self.assertEqual(payload["contains"]["planning_projects"], 0)
            resumed_state = load_json_checkpoint(checkpoint, run)
            calls, events = [], []
            resumed = self.build(calls, events).run(run, resumed_state)
        self.assertEqual([item.year for item in resumed], [2026])
        self.assertEqual(resumed[-1].next_state, uninterrupted[-1].next_state)
        self.assertTrue(all(call[0] == 2026 for call in calls))

    def test_checkpoint_refuses_different_research_identity(self):
        run = resolved_run()
        state = YearState(2026, (), ())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state-2026.json"
            json_checkpoint_writer(Path(folder), run)(state)
            changed = replace(run, project_id="other-project")
            with self.assertRaisesRegex(ValueError, "identity does not match"):
                load_json_checkpoint(path, changed)


if __name__ == "__main__":
    unittest.main()
