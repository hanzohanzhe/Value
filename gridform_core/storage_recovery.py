"""Adequacy and sensitivity evidence for the published storage-recovery rule."""

from __future__ import annotations

import math
from typing import Mapping


UTILISATION_VARIANTS = (
    {"id": "thesis_exact", "utilisation_floor_fraction": 0.0, "classification": "published_baseline"},
    {"id": "sensitivity_floor_01", "utilisation_floor_fraction": 0.01, "classification": "sensitivity"},
    {"id": "sensitivity_floor_05", "utilisation_floor_fraction": 0.05, "classification": "sensitivity"},
    {"id": "sensitivity_floor_10", "utilisation_floor_fraction": 0.10, "classification": "sensitivity"},
)


def _number(report: Mapping[str, object], key: str) -> float:
    value = float(report.get(key, 0.0) or 0.0)
    if not math.isfinite(value):
        raise ValueError(f"Storage recovery field {key} is not finite")
    return value


def recovery_adequacy(report: Mapping[str, object]) -> dict[str, object]:
    sold = _number(report, "current_year_sold_mwh")
    dwell = _number(report, "current_year_average_dwell_periods")
    cycle = _number(report, "cycle_depreciation_gbp_per_mwh")
    holding = _number(report, "holding_recovery_gbp_per_mwh_period")
    target = _number(report, "annual_levelized_project_cost_gbp")
    other_revenue = report.get("other_storage_revenue_gbp")
    other = float(other_revenue) if other_revenue is not None else 0.0
    # v2 (P0-6 S10, decision Q8): a cycle-only bid recovers the cycle wear
    # only; the holding term is investment adequacy, not dispatch revenue.
    bid_basis = str(report.get("bid_basis") or "thesis_dwell_linear")
    bid_recovered = sold * cycle + (0.0 if bid_basis == "cycle_only" else sold * dwell * holding)
    recovered = bid_recovered + other
    fallback = (
        "no_previous_year_sales_full_utilisation_design_case"
        if report.get("pricing_basis") == "full_utilisation_initialisation"
        else None
    )
    return {
        "schema_version": "value.storage-recovery-adequacy/v2",
        "technology": report.get("technology"),
        "bid_basis": bid_basis,
        "pricing_basis": report.get("pricing_basis"),
        "fallback_reason": fallback,
        "annual_levelized_project_cost_gbp": target,
        "sold_mwh": sold,
        "sales_weighted_dwell_periods": dwell,
        "bid_recovered_revenue_gbp": bid_recovered,
        "other_storage_revenue_gbp": (other if other_revenue is not None else None),
        "under_over_recovery_gbp": recovered - target,
        "effective_utilisation_denominator_mwh_periods": sold * dwell,
        "status": "reconciled" if math.isclose(recovered, target, rel_tol=1e-8, abs_tol=1e-6) else "observed_difference",
    }


def sensitivity_specifications() -> list[dict[str, object]]:
    return [dict(value) for value in UTILISATION_VARIANTS]
