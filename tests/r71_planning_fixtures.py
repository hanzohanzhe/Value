"""Frozen planning tables for toy states (r71, DECISIONS A33).

Since R7-1 an endogenous proposal needs ``state.extensions['planning_parameters']``
(written by ``native_initial_state`` for real Runs).  Toy states built directly
in tests carry one of these tables.

``NEXT_YEAR_CERTAIN``: zero-month timelines and success rate 1 for every
label, so every proposal completes the year after its decision with
probability one - the pre-R7-1 behaviour that the investment-rule tests were
written against (it isolates the rule under test from planning timing).
"""
from __future__ import annotations

import copy
from dataclasses import replace

from gridform_core.builtin.scheme_c_1000twh.endogenous_planning import CORRECTION_ID, PARAMETERS_SCHEMA

LABELS = ("Solar Photovoltaics", "Wind Onshore", "Wind Offshore", "Battery")


def planning_parameters(months: float = 0.0, rate: float = 1.0, *, statistic: str = "median",
                        stage_timelines: dict | None = None, success_rates: dict | None = None) -> dict:
    tables = stage_timelines if stage_timelines is not None else {
        technology: {"total_median": float(months), "total_mean": float(months)}
        for technology in ("solar", "onshore", "offshore", "battery")
    }
    return {
        "schema_version": PARAMETERS_SCHEMA,
        "correction_id": CORRECTION_ID,
        "timeline_statistic": statistic,
        "development_stage_timelines": copy.deepcopy(tables),
        "repd_status_to_timeline": {"Application Submitted": {"timeline_type": "total_median"}},
        "success_rates": copy.deepcopy(success_rates) if success_rates is not None
        else {label: {"GB": float(rate)} for label in LABELS},
    }


NEXT_YEAR_CERTAIN = planning_parameters()


def with_planning(state, parameters: dict | None = None):
    """``state`` with frozen planning tables (default: next year, certain)."""
    return replace(state, extensions={
        **dict(state.extensions),
        "planning_parameters": copy.deepcopy(NEXT_YEAR_CERTAIN if parameters is None else parameters),
    })
