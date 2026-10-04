"""Versioned, solver-neutral declarations captured before VALUE clearing.

The declaration deliberately contains no accepted quantities, clearing prices or
other outcomes.  It is canonicalised and hashed so an independent validator can
prove that it solved the same information set that the production market saw.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping


CLEARING_INPUT_SCHEMA_VERSION = "value.clearing-input/v1"
CLEARING_OUTCOME_SCHEMA_VERSION = "value.clearing-outcome/v1"
_FORBIDDEN_INPUT_KEYS = {
    "accepted_mwh",
    "accepted_power_mw",
    "clearing_price_gbp_per_mwh",
    "dispatch_mwh",
    "dispatch_power_mw",
    "market_payment_gbp",
    "outcome",
    "result",
}


def _assert_finite(value: Any, path: str = "payload", *, forbid_outcomes: bool = False) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if forbid_outcomes and str(key) in _FORBIDDEN_INPUT_KEYS:
                raise ValueError(f"{path}.{key} is an outcome and cannot be declared before clearing")
            _assert_finite(item, f"{path}.{key}", forbid_outcomes=forbid_outcomes)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_finite(item, f"{path}[{index}]", forbid_outcomes=forbid_outcomes)
        return
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}")


def canonical_json(payload: Mapping[str, Any], *, forbid_outcomes: bool = False) -> str:
    _assert_finite(payload, forbid_outcomes=forbid_outcomes)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True)
class ClearingInputRow:
    input_sha256: str
    year: int
    period: int
    stage: str
    schema_version: str
    information_scope: str
    declared_before_clearing: int
    payload_json: str

    @classmethod
    def create(
        cls,
        *,
        year: int,
        period: int,
        stage: str,
        information_scope: str,
        payload: Mapping[str, Any],
    ) -> "ClearingInputRow":
        if not stage.strip():
            raise ValueError("Clearing stage is required")
        if not information_scope.strip():
            raise ValueError("Clearing information scope is required")
        envelope = {
            "schema_version": CLEARING_INPUT_SCHEMA_VERSION,
            "year": int(year),
            "period": int(period),
            "stage": stage,
            "information_scope": information_scope,
            "payload": dict(payload),
        }
        encoded = canonical_json(envelope, forbid_outcomes=True)
        return cls(
            hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            int(year),
            int(period),
            stage,
            CLEARING_INPUT_SCHEMA_VERSION,
            information_scope,
            1,
            encoded,
        )

    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)["payload"]


@dataclass(frozen=True)
class ClearingOutcomeRow:
    input_sha256: str
    schema_version: str
    outcome_json: str

    @classmethod
    def create(cls, input_sha256: str, outcome: Mapping[str, Any]) -> "ClearingOutcomeRow":
        if len(input_sha256) != 64:
            raise ValueError("Clearing outcome requires a SHA-256 input link")
        return cls(
            input_sha256,
            CLEARING_OUTCOME_SCHEMA_VERSION,
            canonical_json(dict(outcome)),
        )

    def outcome(self) -> dict[str, Any]:
        return json.loads(self.outcome_json)
