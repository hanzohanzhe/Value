"""Public protocol for replaceable current-period balancing modules."""

from __future__ import annotations

from typing import Protocol

from .staged_market_contracts import BalancingInput, BalancingResult


class BalancingModule(Protocol):
    id: str
    version: str

    def clear(self, model_input: BalancingInput) -> BalancingResult: ...
