"""PSM -> CEM -> next-year state orchestration.

The orchestrator owns time. Individual models only own one well-defined step.
That prevents a demand provider, a storage-cap method or an investment strategy
from silently changing the outer annual loop.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence

from .contracts import DataPack, ModelState, PSMInput, YearContext, YearResult
from .interfaces import CEMModule, PSMEngine, StateTransition


class AnnualModelOrchestrator:
    def __init__(
        self,
        psm: PSMEngine,
        cem_modules: Sequence[CEMModule],
        transition: StateTransition,
    ) -> None:
        self.psm = psm
        self.cem_modules = tuple(sorted(cem_modules, key=lambda module: module.order))
        self.transition = transition

    def run(
        self,
        *,
        project_id: str,
        scenario_id: str,
        data_pack: DataPack,
        initial_state: ModelState,
        years: Iterable[int],
        parameters: dict,
    ) -> list[YearResult]:
        state = initial_state
        results: list[YearResult] = []
        for year in years:
            if state.year != year:
                state = replace(state, year=year)
            context = YearContext(
                project_id=project_id,
                scenario_id=scenario_id,
                year=year,
                data_pack=data_pack,
                parameters=parameters,
            )
            psm_result = self.psm.run(PSMInput(context=context, state=state))
            if psm_result.year != year:
                raise ValueError(f"PSM returned year {psm_result.year}; expected {year}")

            decisions = []
            for module in self.cem_modules:
                decision = module.decide(context, state, psm_result, tuple(decisions))
                if decision.module_id != module.id:
                    raise ValueError(
                        f"CEM module {module.id} returned decision for {decision.module_id}"
                    )
                decisions.append(decision)

            next_state = self.transition.apply(context, state, tuple(decisions))
            if next_state.year != year + 1:
                raise ValueError("State transition must advance exactly one year")
            results.append(
                YearResult(
                    year=year,
                    psm=psm_result,
                    decisions=tuple(decisions),
                    next_state=next_state,
                )
            )
            state = next_state
        return results

