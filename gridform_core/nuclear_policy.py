"""Audited exogenous nuclear fleet policy for VALUE-UK studies."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from .asset_economics import build_asset_economic_extensions
from .v2.contracts import PlanningProject


POLICY_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "nuclear"
    / "value_uk_nuclear_policy_v1.json"
)
POLICY_SCHEMA = "value.uk-nuclear-policy/v1"
VALUE_UK_OPEN_DATA_PACK_ID = "value-uk-open-data-pack-v1"


def applies_to_data_pack(manifest: Mapping[str, object]) -> bool:
    """Keep the VALUE-UK policy out of the retained doctoral reproduction."""

    return str(manifest.get("id") or "") == VALUE_UK_OPEN_DATA_PACK_ID


@lru_cache(maxsize=1)
def load_value_uk_nuclear_policy() -> dict[str, object]:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != POLICY_SCHEMA:
        raise ValueError("Unsupported VALUE-UK nuclear policy schema")
    stations = tuple(dict(row) for row in payload.get("existing_stations") or ())
    station_ids = [str(row.get("station_id") or "") for row in stations]
    if not station_ids or any(not value for value in station_ids):
        raise ValueError("VALUE-UK nuclear policy requires named existing stations")
    if len(station_ids) != len(set(station_ids)):
        raise ValueError("VALUE-UK nuclear station IDs must be unique")
    total = sum(float(row.get("capacity_mw", 0.0) or 0.0) for row in stations)
    declared = float(payload.get("declared_existing_capacity_mw", 0.0) or 0.0)
    if total != declared:
        raise ValueError(
            f"VALUE-UK nuclear station capacity {total} MW does not reconcile to {declared} MW"
        )
    if payload.get("endogenous_investment_allowed") is not False:
        raise ValueError("VALUE-UK nuclear policy must deny endogenous investment")
    unavailable_years = [int(row.get("model_unavailable_from_year", 0) or 0) for row in stations]
    if any(year <= 2025 for year in unavailable_years):
        raise ValueError("VALUE-UK existing nuclear stations must operate in the 2025 initial state")
    planned = tuple(dict(row) for row in payload.get("planned_projects") or ())
    project_ids = [str(row.get("project_id") or "") for row in planned]
    if len(project_ids) != len(set(project_ids)) or any(not value for value in project_ids):
        raise ValueError("VALUE-UK planned nuclear project IDs must be unique and non-empty")
    for row in planned:
        if float(row.get("capacity_mw", 0.0) or 0.0) <= 0:
            raise ValueError("VALUE-UK planned nuclear projects require positive capacity")
        first_generation = row.get("expected_first_generation_year")
        if first_generation is not None and int(
            row.get("model_first_full_operating_year", 0) or 0
        ) <= int(first_generation):
            raise ValueError("VALUE-UK full-year commissioning must follow first generation")
    return payload


def existing_nuclear_asset_specs(model_year: int) -> tuple[dict[str, object], ...]:
    """Return declared station records that are available in ``model_year``."""

    policy = load_value_uk_nuclear_policy()
    return tuple(
        {
            **dict(row),
            "asset_id": f"nuclear:{row['station_id']}",
            "technology": "Nuclear",
        }
        for row in policy["existing_stations"]
        if int(row["model_unavailable_from_year"]) > int(model_year)
    )


def build_value_uk_nuclear_projects(
    *,
    start_year: int,
    end_year: int,
    capital_discount_rate: float,
) -> tuple[PlanningProject, ...]:
    """Build only the declared projects that have a full operating year in-range."""

    policy = load_value_uk_nuclear_policy()
    planned = tuple(dict(row) for row in policy["planned_projects"])
    cost_rows = tuple(dict(row) for row in policy.get("cost_evidence") or ())
    projects: list[PlanningProject] = []
    for row in planned:
        completion = int(row["model_first_full_operating_year"])
        retain_beyond_horizon = (
            str(row.get("model_treatment") or "")
            == "retain_in_pipeline_beyond_model_horizon"
        )
        if completion < int(start_year) or (
            completion > int(end_year) and not retain_beyond_horizon
        ):
            continue
        project_id = str(row["project_id"])
        cost_row = next(
            (
                candidate
                for candidate in cost_rows
                if project_id in tuple(candidate.get("applies_to_project_ids") or ())
            ),
            None,
        )
        if cost_row is None:
            raise ValueError(f"No nuclear cost evidence is declared for {project_id}")
        covered_ids = tuple(str(value) for value in cost_row["applies_to_project_ids"])
        covered_capacity = sum(
            float(candidate["capacity_mw"])
            for candidate in planned
            if str(candidate["project_id"]) in covered_ids
        )
        capacity = float(row["capacity_mw"])
        total_capex = float(cost_row["total_cost_gbp"]) * capacity / covered_capacity
        economics = build_asset_economic_extensions(
            "Nuclear",
            capacity,
            energy_capacity_mwh=None,
            capital_costs_per_mw={"Nuclear": total_capex / capacity},
            lifetimes={"Nuclear": 40.0, "default": 40.0},
            discount_rate=float(capital_discount_rate),
            source_record_id=project_id,
        )
        economics.update(
            {
                "investment_eligible": False,
                "spatial_mapping_asset_id": "Nuclear",
                "primary_cost_ledger_included": False,
                "cost_evidence_id": cost_row["evidence_id"],
                "cost_price_year": cost_row["price_year"],
                "cost_ledger_treatment": cost_row["primary_ledger_treatment"],
                "model_first_full_operating_year": completion,
                "development_years": max(1, completion - int(start_year)),
                "source_title": row["source_title"],
                "source_url": row["source_url"],
                **(
                    {"expected_first_generation_year": int(first_generation)}
                    if (first_generation := row.get("expected_first_generation_year"))
                    is not None
                    else {}
                ),
                **(
                    {"model_treatment": row["model_treatment"]}
                    if row.get("model_treatment") is not None
                    else {}
                ),
                **(
                    {"completion_year_basis": row["completion_year_basis"]}
                    if row.get("completion_year_basis") is not None
                    else {}
                ),
                **(
                    {
                        "final_investment_decision_date": row[
                            "final_investment_decision_date"
                        ]
                    }
                    if row.get("final_investment_decision_date") is not None
                    else {}
                ),
                **(
                    {"financial_close_date": row["financial_close_date"]}
                    if row.get("financial_close_date") is not None
                    else {}
                ),
            }
        )
        projects.append(
            PlanningProject(
                project_id,
                str(row["name"]),
                "declared_external_nuclear_plan",
                "Nuclear",
                capacity,
                capacity,
                "GB",
                "under_construction",
                "active",
                int(start_year),
                completion,
                "expected_capacity",
                1.0,
                extensions=economics,
            )
        )
    return tuple(projects)


def nuclear_capacity_trajectory(
    start_year: int,
    end_year: int,
) -> tuple[dict[str, float | int], ...]:
    """Return an annual capacity ledger derived from the declared policy."""

    if int(end_year) < int(start_year):
        raise ValueError("Nuclear capacity trajectory end year precedes start year")
    policy = load_value_uk_nuclear_policy()
    planned = tuple(dict(row) for row in policy["planned_projects"])
    initial_existing = sum(
        float(row["capacity_mw"])
        for row in existing_nuclear_asset_specs(int(start_year))
    )
    initial_planned = sum(
        float(row["capacity_mw"])
        for row in planned
        if int(row["model_first_full_operating_year"]) <= int(start_year)
    )
    baseline_total = initial_existing + initial_planned
    previous_existing = initial_existing
    previous_planned = initial_planned
    cumulative_commissioning = 0.0
    cumulative_retirements = 0.0
    rows: list[dict[str, float | int]] = []
    for model_year in range(int(start_year), int(end_year) + 1):
        existing = sum(
            float(row["capacity_mw"])
            for row in existing_nuclear_asset_specs(model_year)
        )
        operating_planned = sum(
            float(row["capacity_mw"])
            for row in planned
            if int(row["model_first_full_operating_year"]) <= model_year
        )
        annual_retirements = max(previous_existing - existing, 0.0)
        annual_commissioning = max(operating_planned - previous_planned, 0.0)
        cumulative_retirements += annual_retirements
        cumulative_commissioning += annual_commissioning
        total = existing + operating_planned
        rows.append(
            {
                "model_year": model_year,
                "operating_existing_mw": existing,
                "operating_planned_additions_mw": operating_planned,
                "annual_commissioning_mw": annual_commissioning,
                "annual_retirements_mw": annual_retirements,
                "cumulative_commissioning_mw": cumulative_commissioning,
                "cumulative_retirements_mw": cumulative_retirements,
                "total_nuclear_capacity_mw": total,
                "net_change_from_2025_mw": total - baseline_total,
            }
        )
        previous_existing = existing
        previous_planned = operating_planned
    return tuple(rows)
