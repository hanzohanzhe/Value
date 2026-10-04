"""End-of-horizon fleet and planning-pipeline reporting.

Terminal values produced here are informational and never feed dispatch, CEM
investment or the canonical system-cost ledger.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .v2.contracts import AssetStateV2, PlanningProject, YearState


TERMINAL_SCHEMA = "value.terminal-state-report/v1"
FLEET_SCHEMA = "value.fleet-vintage-ledger/v1"


@dataclass(frozen=True)
class FleetVintageRow:
    asset_id: str
    technology: str
    region: str | None
    capacity_mw: float
    energy_capacity_mwh: float | None
    vintage_year: int | None
    vintage_source: str
    declared_life_years: float | None
    life_source: str
    expected_retirement_year: int | None
    age_years: float | None
    remaining_life_years: float | None
    annualised_capital_charge_gbp: float | None
    model_remaining_capital_value_gbp: float | None
    historical_book_value_gbp: float | None
    market_salvage_value_gbp: float | None
    quality: str


def _present_value_annuity(annual_charge: float, years: float, discount_rate: float) -> float:
    if annual_charge < 0 or years < 0 or discount_rate < 0:
        raise ValueError("Annuity inputs must be non-negative")
    if years == 0:
        return 0.0
    return annual_charge * years if discount_rate == 0 else annual_charge * (1 - (1 + discount_rate) ** -years) / discount_rate


def build_fleet_vintage_ledger(
    assets: Sequence[AssetStateV2],
    *,
    valuation_year: int,
    discount_rate: float,
) -> dict[str, object]:
    rows: list[FleetVintageRow] = []
    for asset in assets:
        ext = asset.extensions
        vintage_raw = ext.get("commissioning_year", ext.get("vintage_year"))
        life_raw = ext.get("economic_lifetime_years", ext.get("technical_lifetime_years"))
        vintage = int(vintage_raw) if vintage_raw not in {None, ""} else None
        life = float(life_raw) if life_raw not in {None, ""} else None
        age = max(float(valuation_year - vintage), 0.0) if vintage is not None else None
        remaining = max(life - age, 0.0) if life is not None and age is not None else None
        retirement = int(vintage + life) if vintage is not None and life is not None else None
        annual_raw = ext.get("annualized_capital_cost_gbp")
        annual = float(annual_raw) if annual_raw not in {None, ""} else None
        remaining_value = (
            _present_value_annuity(annual, remaining, discount_rate)
            if annual is not None and remaining is not None else None
        )
        book = ext.get("historical_book_value_gbp")
        rows.append(FleetVintageRow(
            asset.asset_id, asset.technology, asset.region, float(asset.capacity_mw),
            float(asset.energy_capacity_mwh) if asset.energy_capacity_mwh is not None else None,
            vintage, str(ext.get("vintage_source") or "not_evaluated"), life,
            str(ext.get("lifetime_source") or "not_evaluated"), retirement, age, remaining,
            annual, remaining_value,
            float(book) if book not in {None, ""} else None,
            None,
            "declared" if vintage is not None and life is not None else "not_evaluated",
        ))
    aggregates: dict[str, dict[str, float | int | None]] = {}
    for technology in sorted({row.technology for row in rows}):
        selected = [row for row in rows if row.technology == technology]
        known = [row for row in selected if row.remaining_life_years is not None]
        capacity = sum(row.capacity_mw for row in selected)
        aggregates[technology] = {
            "assets": len(selected),
            "capacity_mw": capacity,
            "capacity_weighted_remaining_life_years": (
                sum(row.capacity_mw * float(row.remaining_life_years) for row in known)
                / sum(row.capacity_mw for row in known)
                if known and sum(row.capacity_mw for row in known) > 0 else None
            ),
            "model_remaining_capital_value_gbp": sum(
                float(row.model_remaining_capital_value_gbp or 0.0) for row in selected
            ),
            "retiring_within_1y_mw": sum(row.capacity_mw for row in known if float(row.remaining_life_years) <= 1),
            "retiring_within_5y_mw": sum(row.capacity_mw for row in known if float(row.remaining_life_years) <= 5),
            "retiring_within_10y_mw": sum(row.capacity_mw for row in known if float(row.remaining_life_years) <= 10),
            "unknown_vintage_or_life_assets": len(selected) - len(known),
        }
    return {
        "schema_version": FLEET_SCHEMA,
        "valuation_year": valuation_year,
        "gbp_base_year": "as_declared_by_each_asset_cost_source",
        "discount_rate": discount_rate,
        "model_remaining_capital_value_formula": "A * (1 - (1+r)^(-remaining_years)) / r",
        "historical_book_value_policy": "asset_specific_only",
        "market_salvage_value_policy": "not_evaluated",
        "rows": [asdict(row) for row in rows],
        "aggregates_by_technology": aggregates,
    }


def build_terminal_state_report(
    final_state: YearState,
    *,
    horizon_year: int,
    policy: str = "report_only",
) -> dict[str, object]:
    if policy not in {"report_only", "pipeline_tail", "full_extension"}:
        raise ValueError("Unknown terminal policy")
    projects = list(final_state.planning_projects)
    active = [row for row in projects if row.outcome not in {"commissioned", "failed_planning", "filtered"}]
    after = [row for row in active if row.expected_completion_year > horizon_year]
    terminal_year = max([horizon_year, *[row.expected_completion_year for row in after]])
    rows = [row.to_dict() for row in projects]
    # pipeline_tail is a planning-only view. It deliberately creates no PSM/CEM results.
    tail = []
    if policy == "pipeline_tail":
        tail = [
            {
                "year": year,
                "dispatch": "not_run",
                "generation_mwh": "not_applicable",
                "system_cost_gbp": "not_applicable",
                "emissions_tco2e": "not_applicable",
                "projects_due": sum(1 for row in after if row.expected_completion_year == year),
                "capacity_due_mw": sum(row.capacity_mw for row in after if row.expected_completion_year == year),
            }
            for year in range(horizon_year + 1, terminal_year + 1)
        ]
    by_status: dict[str, dict[str, float | int]] = {}
    for project in projects:
        bucket = by_status.setdefault(project.outcome, {"project_count": 0, "capacity_mw": 0.0})
        bucket["project_count"] = int(bucket["project_count"]) + 1
        bucket["capacity_mw"] = float(bucket["capacity_mw"]) + float(project.capacity_mw)
    return {
        "schema_version": TERMINAL_SCHEMA,
        "horizon_year": horizon_year,
        "terminal_policy": policy,
        "terminal_state_reconciled": len(rows) == sum(int(x["project_count"]) for x in by_status.values()),
        "outstanding_project_count": len(active),
        "outstanding_capacity_mw": sum(row.capacity_mw for row in active),
        "post_horizon_project_count": len(after),
        "post_horizon_capacity_mw": sum(row.capacity_mw for row in after),
        "by_outcome": by_status,
        "projects": rows,
        "pipeline_tail": tail,
        "warning": (
            "Outstanding planning exposure remains at the model horizon."
            if active else None
        ),
    }


def write_terminal_artifacts(directory: Path, final_state: YearState, *, horizon_year: int, discount_rate: float, policy: str) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    terminal = build_terminal_state_report(final_state, horizon_year=horizon_year, policy=policy)
    fleet = build_fleet_vintage_ledger(final_state.assets, valuation_year=horizon_year, discount_rate=discount_rate)
    paths = directory / "terminal-state.json", directory / "fleet-vintage.json"
    for path, payload in zip(paths, (terminal, fleet)):
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    return paths
