"""Public protocols for executable VALUE v2 modules."""

from __future__ import annotations

from typing import Protocol, Sequence

from ..balancing import BalancingModule
from ..subannual_checkpoint import PSMSubannualCheckpointEngine

from .contracts import (
    ExpansionHeadroom,
    InvestmentDecision,
    InvestmentProposal,
    MarketYearResult,
    OperatingState,
    PlanningAdmissionResult,
    PlanningAdvanceResult,
    PSMInput,
    ResolvedRun,
    YearState,
)


class PSMEngine(Protocol):
    id: str
    version: str

    def run(self, model_input: PSMInput) -> MarketYearResult: ...


class ExpansionPolicy(Protocol):
    id: str
    version: str

    def evaluate(
        self,
        run: ResolvedRun,
        state: OperatingState,
        market: MarketYearResult,
    ) -> ExpansionHeadroom: ...


class InvestmentModule(Protocol):
    id: str
    version: str

    def decide(
        self,
        run: ResolvedRun,
        state: OperatingState,
        market: MarketYearResult,
        headroom: Sequence[ExpansionHeadroom],
    ) -> InvestmentDecision: ...


class PlanningPipeline(Protocol):
    id: str
    version: str

    def advance_year(self, run: ResolvedRun, state: YearState) -> PlanningAdvanceResult: ...

    def admit_projects(
        self,
        run: ResolvedRun,
        state: OperatingState,
        proposals: Sequence[InvestmentProposal],
    ) -> PlanningAdmissionResult: ...


class StateTransition(Protocol):
    id: str
    version: str

    def apply(
        self,
        run: ResolvedRun,
        current_state: YearState,
        planning: PlanningAdmissionResult,
        investment: InvestmentDecision,
    ) -> YearState: ...


__all__ = [
    "BalancingModule",
    "ExpansionPolicy",
    "InvestmentModule",
    "PlanningPipeline",
    "PSMEngine",
    "PSMSubannualCheckpointEngine",
    "StateTransition",
]
