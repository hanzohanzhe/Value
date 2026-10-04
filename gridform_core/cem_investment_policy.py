"""Versioned VALUE-CEM investment eligibility and site constraints."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping


POLICY_PATH = Path(__file__).resolve().parent / "data" / "cem" / "investment_eligibility.json"
POLICY_SCHEMA = "value.cem-investment-eligibility/v1"
VALID_MODES = {"headroom_required", "explicit_uncapped", "site_data_required", "denied"}


@lru_cache(maxsize=1)
def load_investment_eligibility() -> dict[str, object]:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != POLICY_SCHEMA:
        raise ValueError("Unsupported VALUE-CEM investment eligibility schema")
    default = str(payload.get("default_mode") or "")
    if default not in VALID_MODES:
        raise ValueError("Invalid default investment eligibility mode")
    modes = {str(key): str(value) for key, value in dict(payload.get("modes") or {}).items()}
    invalid = sorted({value for value in modes.values() if value not in VALID_MODES})
    if invalid:
        raise ValueError("Invalid investment eligibility modes: " + ", ".join(invalid))
    return payload


def investment_mode(technology: str) -> str:
    policy = load_investment_eligibility()
    return str(
        dict(policy.get("modes") or {}).get(
            technology, policy.get("default_mode", "denied")
        )
    )


def missing_site_evidence(technology: str, extensions: Mapping[str, object]) -> tuple[str, ...]:
    policy = load_investment_eligibility()
    required = tuple(
        str(item)
        for item in dict(policy.get("site_requirements") or {}).get(technology, ())
    )
    missing = []
    for key in required:
        value = extensions.get(key)
        if value is None or str(value).strip() == "":
            missing.append(key)
        elif key == "capital_cost_scope" and str(value) != "new_build":
            missing.append("capital_cost_scope=new_build")
    return tuple(missing)


def policy_summary() -> dict[str, object]:
    policy = load_investment_eligibility()
    return {
        "schema_version": policy["schema_version"],
        "policy_id": policy["policy_id"],
        "version": policy["version"],
        "default_mode": policy["default_mode"],
    }
