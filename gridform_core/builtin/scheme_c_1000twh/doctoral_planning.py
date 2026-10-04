"""Doctoral REPD preprocessing, independent of weather and annual investment.

Source: run_investment_analysis.py (SHA256 81446a975e51983aef6806a64ca1e5e7
bbd70efc97903d8a08b6c9691697e528), config.py (587ad317e89305fb60342ed06cd309
ee79a00df3e3bcc7dbc2f235fe63478de5).  The original files are never imported.

The caller supplies frozen status/timeline tables and an explicit uncertainty
choice. Physical REPD batteries remain untyped here; the existing storage
allocation and all weather/owner mapping belong to downstream consumers.
"""
from __future__ import annotations

import hashlib
import math
from typing import Mapping, Sequence

import pandas as pd

from gridform_core.v2.contracts import PlanningProject


PREPROCESSING_SCHEMA = "value.doctoral-planning-preprocessing/v1"
HIGH_CONFIDENCE = frozenset({"Under Construction", "Awaiting Construction", "Planning Permission Granted"})
UNCERTAIN = frozenset({"Application Submitted", "Appeal Lodged", "Revised"})
TERMINAL = frozenset({
    "Application Refused", "Application Withdrawn", "Abandoned", "Appeal Refused",
    "Appeal Withdrawn", "Decommissioned", "Application Expired", "Finished",
})
PROGRESS_COLUMNS = (
    "Planning Application Submitted", "Appeal Lodged", "Appeal Granted",
    "Planning Permission Granted", "Planning Permission  Granted",
    "Secretary of State - Granted", "Under Construction", "Operational",
)
ROW_ALIASES = {
    "Ref ID": "project_id", "Site Name": "site_name", "Technology Type": "technology_source",
    "Development Status (short)": "development_status", "Installed Capacity (MWelec)": "capacity_mw",
    "Region": "region", "Planning Application Submitted": "planning_application_submitted",
    "Planning Permission Granted": "planning_permission_granted", "Appeal Lodged": "appeal_lodged",
    "Appeal Granted": "appeal_granted", "Secretary of State - Granted": "secretary_of_state_granted",
    "Under Construction": "under_construction", "Operational": "operational",
}
SUCCESS_LABELS = {
    "solar": "Solar Photovoltaics", "onshore": "Wind Onshore", "offshore": "Wind Offshore",
    "battery": "Battery", "1c_battery": "Battery", "0.5c_battery": "Battery", "0.25c_battery": "Battery",
    "gas": "Wind Onshore", "CCGT": "Wind Onshore", "OCGT": "Wind Onshore", "bio_and_waste": "Wind Onshore",
}


def _missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "nan", "nat"}) or bool(pd.isna(value))


def _row_value(row: Mapping[str, object], column: str, default: object = None) -> object:
    value = row.get(column, row.get(ROW_ALIASES.get(column, ""), default))
    return default if _missing(value) else value


def stable_int_hash(text: str) -> int:
    """Source lines 17-20: first 64 bits of the MD5 digest, not Python hash."""
    return int(hashlib.md5(str(text).encode("utf-8")).hexdigest()[:16], 16)


def parse_repd_year(value: object) -> int | None:
    """Source lines 1303-1309: day-first dates, invalid/missing dates -> None."""
    if _missing(value):
        return None
    date = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(date) else int(date.year)


def _timeline_technology(technology: str) -> str:
    # Source _map_repd_tech_type, lines 482-494 (including solar fallback).
    if technology in {"solar", "onshore", "offshore", "battery"}:
        return technology
    return {"Solar Photovoltaics": "solar", "Wind Onshore": "onshore", "Wind Offshore": "offshore", "Battery": "battery"}.get(technology, "solar")


def _asset_technology(value: object) -> str | None:
    # Source get_asset_type_from_repd, lines 41-51. Nuclear and pumped hydro
    # are deliberately not admitted to this general REPD pipeline.
    text = str(value)
    if text in {"solar", "onshore", "offshore", "battery", "gas"}:
        return text
    for label, technology in (("Onshore", "onshore"), ("Offshore", "offshore"), ("Solar", "solar"), ("Battery", "battery")):
        if label in text:
            return technology
    if "Pumped Storage" in text:
        return None
    return "gas" if "Gas" in text else None


def timeline_months(technology: str, status: str, context: Mapping[str, object]) -> float:
    """Source lines 497-518, 608-625; granted includes construction time."""
    statistic = str(context.get("timeline_statistic", "median"))
    if statistic not in {"median", "mean"}:
        raise ValueError("timeline_statistic must be median or mean")
    tables = context["development_stage_timelines"]
    stages = tables.get(_timeline_technology(technology), tables["solar"])
    status_config = context["repd_status_to_timeline"].get(status, {})
    kind = str(status_config.get("timeline_type", "total_median"))
    if kind.endswith(("_median", "_mean")):
        kind = kind.rsplit("_", 1)[0]
    if kind == "pre_construction":
        months = float(stages[f"pre_construction_{statistic}"]) + float(stages[f"construction_{statistic}"])
    elif kind in {"construction", "planning_consenting"}:
        months = float(stages[f"{kind}_{statistic}"])
    else:
        months = float(stages[f"total_{statistic}"])
    if not math.isfinite(months) or months < 0:
        raise ValueError("Invalid development timeline months")
    return months


def completion_year_from_months(base_year: int, months: float, project_key: str = "") -> int:
    """Source lines 521-527: calendar year after rounded months and MD5 jitter."""
    jitter = (stable_int_hash(project_key) % 13) - 6 if project_key else 0
    rounded_months = int(round(max(1.0, float(months) + jitter)))
    return int(base_year) + rounded_months // 12


def _milestones(row: Mapping[str, object]) -> dict[str, int | None]:
    return {column: parse_repd_year(_row_value(row, column)) for column in PROGRESS_COLUMNS}


def _permission_year(years: Mapping[str, int | None]) -> int | None:
    return years.get("Planning Permission  Granted") or years.get("Planning Permission Granted")


def estimate_repd_completion_year(row: Mapping[str, object], status: str, context: Mapping[str, object], *, historical: bool = False) -> int:
    """Source lines 637-699: historical screening or forward milestone schedule.

    Operational/Under Construction forecast dates do not schedule commissioning.
    Historical screening does not apply the forward start-year floor.
    """
    start = int(context["start_year"])
    years = _milestones(row)
    permission, application = _permission_year(years), years["Planning Application Submitted"]
    technology = str(_row_value(row, "Technology Type", row.get("technology", "")))
    key = str(_row_value(row, "Site Name", _row_value(row, "Ref ID", "unknown")))
    if status in HIGH_CONFIDENCE and permission:
        base = permission
    else:
        base = application if application and application >= 2000 else start
    if not historical:
        base = max(base, start)
    completion = completion_year_from_months(base, timeline_months(technology, status, context), key)
    if not historical and application and application >= 2000:
        full = completion_year_from_months(max(application, start), timeline_months(technology, "Application Submitted", context), key)
        completion = max(completion, full)
    if not historical and context.get("apply_repd_initial_snapshot", True):
        completion = max(completion, start + 1)
    return completion


def repd_zombie_flags(row: Mapping[str, object], context: Mapping[str, object]) -> tuple[bool, bool]:
    """Return (status_stagnant, schedule_overdue), source lines 702-828."""
    if not context.get("zombie_filter_enabled", True):
        return False, False
    status = _row_value(row, "Development Status (short)", "")
    snapshot = int(context.get("zombie_snapshot_year", context["start_year"]))
    years = _milestones(row)
    if status == "Operational" or (years["Operational"] is not None and years["Operational"] <= snapshot):
        return False, False
    if not status or status in TERMINAL:
        return False, False
    known = [year for year in years.values() if year is not None]
    stagnant = bool(known and max(known) <= int(context.get("zombie_status_stale_year", 2015)))
    historical_context = dict(context, start_year=snapshot)
    historical = estimate_repd_completion_year(row, str(status), historical_context, historical=True)
    deadline = snapshot - int(context.get("construction_grace_years", 2))
    return stagnant, historical <= deadline


def lookup_regional_success_rate(success_rates: Mapping, technology: str, region: str) -> float:
    """Source lines 546-552: region, then technology mean, then 0.75.

    Accept the original nested labels or canonical (technology, region) keys.
    Tuple-key tables have already normalized labels; their GB row participates
    in the technology mean, and is not an override for a missing region.
    """
    label = SUCCESS_LABELS.get(technology, technology)
    if any(isinstance(key, tuple) for key in success_rates):
        rates = {str(key[1]).lower(): value for key, value in success_rates.items() if isinstance(key, tuple) and SUCCESS_LABELS.get(key[0], key[0]) == label}
        lookup = region.lower()
    else:
        rates = success_rates.get(label, {})
        lookup = region
    values = [float(value) for value in rates.values()]
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
        raise ValueError("Invalid REPD success rate; expected finite probability in [0,1]")
    return float(rates[lookup]) if lookup in rates else (sum(values) / len(values) if values else 0.75)


def resolve_repd_success(capacity_mw: float, technology: str, region: str, status: str, project_name: str, context: Mapping[str, object]) -> dict[str, object]:
    """Source lines 530-595,1124-1186; do not advance a process-global RNG."""
    mode = str(context.get("success_mode", "expected_capacity"))
    modes = {"expected": "expected_capacity", "expectation": "expected_capacity", "mean": "expected_capacity", "lottery": "seeded_stochastic", "draw": "seeded_stochastic", "binary": "seeded_stochastic"}
    mode = modes.get(mode, mode)
    if mode not in {"expected_capacity", "seeded_stochastic"}:
        raise ValueError(f"Unsupported REPD success_mode: {mode}")
    applied = bool(context["repd_status_to_timeline"].get(status, {}).get("apply_success_rate", False))
    label = SUCCESS_LABELS.get(technology, "Solar Photovoltaics")
    rate = lookup_regional_success_rate(context["success_rates"], label, region) if applied else 1.0
    draw = None
    if applied and mode == "seeded_stochastic":
        draw = (stable_int_hash(f"{project_name}|{region}|{label}") % 1_000_000) / 1_000_000.0
        succeeds = draw <= rate
        effective = float(capacity_mw) if succeeds else 0.0
    else:
        effective = float(capacity_mw) * rate
        succeeds = effective > 1e-6
    return {"capacity_mw": effective, "success_probability": rate, "success_rate_applied": applied,
            "random_draw": draw, "project_succeeds": succeeds, "success_mode": mode,
            "success_technology": label, "success_region": region}


def defer_start_year_external_pipeline_completions(projects: Sequence[Mapping[str, object]], context: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """Source lines 310-345: defer only external projects completing START_YEAR."""
    start = int(context["start_year"])
    spread = max(1, int(context.get("defer_spread_years", 3)))
    result = []
    for project in projects:
        updated = dict(project)
        completion = project.get("completion_year")
        if context.get("apply_repd_initial_snapshot", True) and project.get("source") == "external" and completion is not None and int(completion) == start:
            updated["completion_year"] = start + 1 + stable_int_hash(str(project.get("name", ""))) % spread
            updated["deferred_from_start_year"] = True
        result.append(updated)
    return tuple(result)


def preprocess_doctoral_project_records(rows: Sequence[Mapping[str, object]], context: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """Return one explicit retained/excluded decision per input row (F18-F20).

    Required context: start_year, include_uncertain_projects,
    development_stage_timelines, repd_status_to_timeline, success_rates. Other
    switches default to the source's documented configuration. The random seed
    is recorded but does not change the original hash-derived draw.
    """
    for key in ("start_year", "include_uncertain_projects", "development_stage_timelines", "repd_status_to_timeline", "success_rates"):
        if key not in context:
            raise ValueError(f"Missing frozen REPD context: {key}")
    if not isinstance(context["include_uncertain_projects"], bool):
        raise ValueError("include_uncertain_projects must be an explicit boolean")
    result = []
    start = int(context["start_year"])
    for index, row in enumerate(rows):
        project_id = str(_row_value(row, "Ref ID", f"repd:{index}"))
        name = str(_row_value(row, "Site Name", project_id))
        source_tech = str(_row_value(row, "Technology Type", row.get("technology", "")))
        technology = _asset_technology(source_tech)
        status = str(_row_value(row, "Development Status (short)", ""))
        record = {"row_index": index, "project_id": project_id, "name": name,
                  "source_technology": source_tech, "technology": technology,
                  "development_status": status, "region": str(_row_value(row, "Region", "England")),
                  "retained": False, "reason": None, "original_capacity_mw": None,
                  "completion_year": None, "historical_completion_year": None,
                  "last_status_progress_year": None, "source_row": dict(row),
                  "schema_version": PREPROCESSING_SCHEMA}
        result.append(record)
        if "nuclear" in source_tech.lower():
            record["reason"] = "excluded_nuclear_policy_managed"
            continue
        if technology is None:
            record["reason"] = "excluded_unsupported_technology"
            continue
        years = _milestones(row)
        record["milestone_years"] = years
        known = [value for value in years.values() if value is not None]
        record["last_status_progress_year"] = max(known) if known else None
        raw_capacity = _row_value(row, "Installed Capacity (MWelec)")
        try:
            capacity = float(raw_capacity)
        except (ValueError, TypeError):
            capacity = float("nan")
        record["original_capacity_mw"] = capacity if math.isfinite(capacity) else None
        if context.get("zombie_filter_enabled", True) and status in TERMINAL:
            record["reason"] = "excluded_terminal_status"
            continue
        stagnant, overdue = repd_zombie_flags(row, context)
        if stagnant or overdue:
            record["reason"] = "excluded_status_stagnant" if stagnant else "excluded_schedule_overdue"
            record["historical_completion_year"] = estimate_repd_completion_year(row, status, context, historical=True)
            continue
        if not context["include_uncertain_projects"] and status in UNCERTAIN:
            record["reason"] = "excluded_uncertain_status"
            continue
        if not context["include_uncertain_projects"] and status not in HIGH_CONFIDENCE:
            record["reason"] = "excluded_unknown_status"
            continue
        if not math.isfinite(capacity):
            record["reason"] = "excluded_invalid_capacity"
            continue
        if capacity < float(context.get("minimum_project_size_mw", 1.0)):
            record["reason"] = "excluded_below_minimum_size"
            continue
        if status == "Operational" or (years["Operational"] is not None and years["Operational"] <= start):
            record["reason"] = "excluded_already_operational"
            continue
        historical = estimate_repd_completion_year(row, status, context, historical=True)
        record["historical_completion_year"] = historical
        if historical < start:
            record["reason"] = "excluded_past_completion"
            continue
        completion = estimate_repd_completion_year(row, status, context)
        record["completion_year"] = completion
        if completion > int(context.get("max_completion_year", 2040)):
            record["reason"] = "excluded_after_max_completion_year"
            continue
        record.update(resolve_repd_success(capacity, technology, record["region"], status, name, context))
        record.update({"retained": True, "reason": "included", "success_draw_method": "doctoral_md5_name_region_technology/v1", "configured_seed": context.get("random_seed")})
    return tuple(result)


def preprocess_doctoral_projects(rows: list[dict[str, object]], context: dict[str, object]) -> tuple[PlanningProject, ...]:
    """Adapt retained physical rows to PlanningProject; no weather or owner mutation.

    For a ledger covering exclusions, call preprocess_doctoral_project_records.
    Do not reapply success probability when splitting batteries or admitting
    these projects in the annual planner: capacities already contain the draw.
    """
    projects = []
    for record in preprocess_doctoral_project_records(rows, context):
        if not record["retained"]:
            continue
        succeeds = bool(record["project_succeeds"])
        extensions = {key: value for key, value in record.items() if key != "source_row"}
        extensions.update({"planning_preprocessing_contract": PREPROCESSING_SCHEMA,
                           "physical_project_id": record["project_id"], "success_evaluated": True,
                           "source_role": "source.repd_raw", "source_declared_capacity_mw": record["original_capacity_mw"]})
        projects.append(PlanningProject(
            project_id=record["project_id"], name=record["name"], source="repd", technology=record["technology"],
            capacity_mw=record["capacity_mw"], original_capacity_mw=record["original_capacity_mw"],
            region=record["region"], development_stage=record["development_status"],
            status="active" if succeeds else "failed", decision_year=int(context["start_year"]),
            expected_completion_year=record["completion_year"], success_mode=record["success_mode"],
            success_probability=record["success_probability"], random_draw=record["random_draw"],
            outcome="active" if succeeds else "failed_planning",
            failure_reason_code=None if succeeds else "failed_due_to_success_rate", extensions=extensions,
        ))
    return tuple(projects)
