"""Plugin interfaces. Researchers implement these, not the annual loop."""

from __future__ import annotations

from typing import Protocol, Sequence

from .contracts import CapacityDecision, ModelState, PSMInput, PSMResult, YearContext


class PSMEngine(Protocol):
    id: str
    version: str

    def run(self, model_input: PSMInput) -> PSMResult: ...


class CEMModule(Protocol):
    id: str
    version: str
    order: int

    def decide(
        self,
        context: YearContext,
        state: ModelState,
        psm_result: PSMResult,
        previous_decisions: Sequence[CapacityDecision],
    ) -> CapacityDecision: ...


class StateTransition(Protocol):
    id: str

    def apply(
        self,
        context: YearContext,
        state: ModelState,
        decisions: Sequence[CapacityDecision],
    ) -> ModelState: ...

