import unittest
from dataclasses import replace

from gridform_core import AnnualModelOrchestrator
from gridform_core.contracts import CapacityDecision, DataPack, ModelState, PSMResult


class FakePSM:
    id = "test-psm"
    version = "1"

    def __init__(self):
        self.years = []

    def run(self, model_input):
        self.years.append(model_input.context.year)
        return PSMResult(
            year=model_input.context.year,
            market_income_gbp={}, generation_mwh={}, prices_gbp_per_mwh=(),
            demand_mwh=(), vre_generation_mwh=(), storage_discharge_mwh=(),
        )


class FakeCEM:
    version = "1"

    def __init__(self, module_id, order, calls):
        self.id, self.order, self.calls = module_id, order, calls

    def decide(self, context, state, psm_result, previous_decisions):
        self.calls.append((context.year, self.id, len(previous_decisions)))
        return CapacityDecision(module_id=self.id)


class Transition:
    id = "test-transition"

    def apply(self, context, state, decisions):
        return replace(state, year=context.year + 1)


class OrchestratorTests(unittest.TestCase):
    def test_psm_then_ordered_cem_then_next_year(self):
        calls = []
        psm = FakePSM()
        orchestrator = AnnualModelOrchestrator(
            psm,
            [FakeCEM("storage", 40, calls), FakeCEM("agents", 10, calls)],
            Transition(),
        )
        pack = DataPack("uk", "UK", "GB", "Europe/London", {})
        result = orchestrator.run(
            project_id="p", scenario_id="s", data_pack=pack,
            initial_state=ModelState(year=2025, assets=()),
            years=range(2025, 2027), parameters={},
        )
        self.assertEqual(psm.years, [2025, 2026])
        self.assertEqual(calls, [(2025, "agents", 0), (2025, "storage", 1), (2026, "agents", 0), (2026, "storage", 1)])
        self.assertEqual(result[-1].next_state.year, 2027)


if __name__ == "__main__":
    unittest.main()
