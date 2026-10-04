"""Truthful annual/subannual recovery capability for the selected VALUE chain."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


SUBANNUAL_CHECKPOINT_SCHEMA = "value.subannual-checkpoint/v1"
ANNUAL_CHECKPOINT_SCHEMA = "value.annual-checkpoint/v1"
SUBANNUAL_REQUIRED_STATE = (
    "last_committed_period",
    "chronological_storage_state",
    "agent_observations",
    "writer_offsets",
    "random_generator_states",
    "year_to_date",
    "frozen_input_hashes",
    "frozen_module_hashes",
    "parent_annual_checkpoint_identity",
    "ledger_boundary",
)


def recovery_capability(selected_module_ids: Iterable[str] = ()) -> dict[str, object]:
    modules = sorted(set(str(value) for value in selected_module_ids))
    supports_monthly = {
        "value-staged-bid-at-cost-psm",
        "value-zonal-redispatch-balancing",
    }.issubset(set(modules))
    gaps = [
        "The selected PSM contract exposes one whole-year run call and no deterministic per-period step/export/import boundary.",
        "Mid-year generator, storage SOC, bid/revenue observations and compatibility-session object state are not all returned by the public PSM result.",
        "The market ledger has no transactionally coupled checkpoint offset with the hidden PSM state, so a suffix cannot yet be replaced without duplicate-period risk.",
    ]
    report = {
        "schema_version": "value.recovery-capability/v1",
        "selected_module_ids": modules,
        "annual_resume_supported": True,
        "annual_checkpoint_schema": ANNUAL_CHECKPOINT_SCHEMA,
        "annual_safe_boundary": "after a complete year and durable result/checkpoint commit",
        "subannual_resume_supported": supports_monthly,
        "optional_subannual_schema": SUBANNUAL_CHECKPOINT_SCHEMA,
        "required_subannual_state": list(SUBANNUAL_REQUIRED_STATE),
        "state_gaps": [] if supports_monthly else gaps,
        "user_message": (
            "Recovery can resume the maintained zonal chain from a verified calendar-month checkpoint."
            if supports_monthly
            else "Recovery is currently annual. An interrupted model year is recomputed from its verified opening checkpoint."
        ),
    }
    return report


def latest_safe_recovery_point(model_output: Path) -> dict[str, object]:
    checkpoint_root = model_output / "checkpoints-v2"
    accepted: list[tuple[int, Path]] = []
    for path in checkpoint_root.glob("state-*.json") if checkpoint_root.is_dir() else ():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != ANNUAL_CHECKPOINT_SCHEMA:
                continue
            year = int(payload["state"]["year"])
            if payload.get("identity") and payload.get("state_sha256"):
                accepted.append((year, path))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    if not accepted:
        return {"available": False, "year": None, "artifact": None}
    year, path = max(accepted, key=lambda item: item[0])
    return {
        "available": True,
        "year": year,
        "artifact": path.relative_to(model_output).as_posix(),
        "meaning": f"opening state for model year {year}",
    }
