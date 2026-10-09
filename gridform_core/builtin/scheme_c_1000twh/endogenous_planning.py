"""Planning terms of endogenous (model) investments: r71 (DECISIONS A33, finding P4-05).

The original Scheme C entered every model investment into the planning
pipeline with the pack's development timeline and regional success rate
(``runtime_compat/modular_investment_support.py``:
``append_model_investment_to_pipeline`` with ``calculate_development_timeline``,
``completion_year_from_months``, ``_lookup_regional_success_rate``,
``_tech_label_for_success_rate``, ``_repd_model_status_for_asset`` and
``get_asset_region``).  The v2 port derived the development time and success
probability from member-asset extensions that are never set, so every
endogenous proposal completed the next year with probability one.  This module
restores the original rule for both methodology profiles (universal
correction ``r71.endogenous-planning-timelines``):

* the planning tables are frozen into the initial state
  (``state.extensions['planning_parameters']``, written by
  ``canonical_psm_data.native_initial_state``) so a Run never re-reads the pack;
* technology label: solar -> Solar Photovoltaics, onshore -> Wind Onshore,
  offshore -> Wind Offshore, every battery type and electrolyser -> Battery,
  gas/CCGT/OCGT/bio_and_waste -> Wind Onshore, anything else -> Solar
  Photovoltaics (the original mapping, unknown types included);
* development status of a model decision: ``Application Submitted`` (median
  stage-1 timeline, normally ``total_median``), timeline technology from the
  label, a technology without a stage-timeline entry uses the ``solar`` entry;
* completion year: months after 1 January of the decision year, with the
  original deterministic per-project dispersion of -6..+6 months
  (MD5 of ``"Model Decision: <owner>"``), at least one month, rounded;
* success region from the owner (asset) name as in ``get_asset_region``;
  success rate: the (label, region) entry, else the mean over the label's
  regions, else 0.75 (the original's constant);
* explicit choice where the original has no working rule: the original
  commissioned a project only in the year equal to its completion year, so a
  model investment whose computed completion fell in its own decision year
  was silently never built.  Here the completion year is at least the year
  after the decision (the earliest year the annual loop can commission it,
  the same floor as the REPD start-year rule) and the record says so
  (``completion_floor_applied``).

Retirements (negative capacity) are not proposals: they take effect the next
year, as the original's ``depletion`` entries with ``completion_year =
decision_year + 1`` did, and no success rate applies to them.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Mapping

CORRECTION_ID = "r71.endogenous-planning-timelines"
PARAMETERS_SCHEMA = "value.planning-parameters/v1"
TERMS_SCHEMA = "value.endogenous-planning-terms/v1"
MODEL_DEVELOPMENT_STATUS = "Application Submitted"
SOURCE_DEFAULT_SUCCESS_RATE = 0.75
JITTER_MONTHS = 6

# Original _tech_label_for_success_rate (default "Solar Photovoltaics").
SUCCESS_LABELS = {
    "solar": "Solar Photovoltaics",
    "onshore": "Wind Onshore",
    "offshore": "Wind Offshore",
    "battery": "Battery",
    "1c_battery": "Battery",
    "0.5c_battery": "Battery",
    "0.25c_battery": "Battery",
    "electrolyzer": "Battery",
    "electrolyzer_attached": "Battery",
    "gas": "Wind Onshore",
    "CCGT": "Wind Onshore",
    "OCGT": "Wind Onshore",
    "bio_and_waste": "Wind Onshore",
}
DEFAULT_SUCCESS_LABEL = "Solar Photovoltaics"
# Original _map_repd_tech_type applied to the label (default "solar").
TIMELINE_TECHNOLOGY = {
    "Solar Photovoltaics": "solar",
    "Wind Onshore": "onshore",
    "Wind Offshore": "offshore",
    "Battery": "battery",
}
# Original get_asset_region: name table, then "offshore" in the name ->
# All Offshore, everything else (batteries included) -> England.
_CITY_REGIONS = {
    "Nottingham": "East Midlands",
    "Ipswich": "Eastern",
    "London": "London",
    "Newcastle": "North East",
    "Manchester": "North West",
    "Edinburgh": "Scotland",
    "Portsmouth": "South East",
    "Bournemouth": "South West",
    "Cardiff": "Wales",
    "Birmingham": "West Midlands",
    "Sheffield": "Yorkshire and Humber",
}
SOURCE_ASSET_REGIONS = {
    **{f"{kind}_{city}": region for kind in ("solar", "onshore") for city, region in _CITY_REGIONS.items()},
    "CCGT": "England",
    "OCGT": "England",
    "bio_and_waste": "England",
    "Nuclear": "England",
    "electrolyzer": "England",
}
# Pack success-table technology (after canonical normalisation) -> label.
_ROW_LABELS = {
    "solar": "Solar Photovoltaics",
    "onshore": "Wind Onshore",
    "offshore": "Wind Offshore",
    "battery": "Battery",
    "1c_battery": "Battery",
    "0.5c_battery": "Battery",
    "0.25c_battery": "Battery",
}


def stable_int_hash(text: str) -> int:
    """Original ``_stable_int_hash``: first 64 bits of the MD5 digest."""
    return int(hashlib.md5(str(text).encode("utf-8")).hexdigest()[:16], 16)


def success_label(technology: str) -> str:
    return SUCCESS_LABELS.get(str(technology), DEFAULT_SUCCESS_LABEL)


def source_success_region(asset_name: str) -> str:
    """Original ``get_asset_region`` on the investing asset (owner) name."""
    name = str(asset_name)
    if name in SOURCE_ASSET_REGIONS:
        return SOURCE_ASSET_REGIONS[name]
    if "offshore" in name.lower():
        return "All Offshore"
    return "England"


def model_project_key(owner: str) -> str:
    """Original project name of a model decision (``"Model Decision: <asset>"``)."""
    return f"Model Decision: {owner}"


def freeze_planning_parameters(
    timelines_payload: Mapping[str, object],
    success_rates_path: Path,
    *,
    timeline_statistic: str,
) -> dict[str, object]:
    """JSON-ready copy of the pack tables the endogenous rule reads.

    Success rows are grouped by the original labels (``Solar Photovoltaics``,
    ``Wind Onshore``, ``Wind Offshore``, ``Battery``; compact packs that write
    ``solar``/``onshore``/... are normalised to the same labels), with the
    region stripped as the original loader did.  A row whose rate is not a
    finite number in [0, 1] is rejected here rather than clamped later.
    """
    import pandas as pd

    from ...canonical_psm_data import _technology

    statistic = str(timeline_statistic)
    if statistic not in {"median", "mean"}:
        raise ValueError("planning.timeline_statistic must be median or mean")
    frame = pd.read_csv(success_rates_path)
    columns = {str(column).strip().lower(): column for column in frame.columns}
    rates: dict[str, dict[str, float]] = {}
    if all(key in columns for key in ("technology", "region", "success_rate")):
        for index, row in frame.iterrows():
            label = _ROW_LABELS.get(_technology(row[columns["technology"]]))
            if label is None:
                continue
            region = str(row[columns["region"]]).strip()
            try:
                rate = float(row[columns["success_rate"]])
            except (TypeError, ValueError):
                raise ValueError(
                    f"planning.success_rates row {index}: success rate is not a number"
                ) from None
            if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
                raise ValueError(
                    f"planning.success_rates row {index}: success rate {rate} is not a probability"
                )
            rates.setdefault(label, {})[region] = rate
    return {
        "schema_version": PARAMETERS_SCHEMA,
        "correction_id": CORRECTION_ID,
        "timeline_statistic": statistic,
        "development_stage_timelines": {
            str(tech): {str(key): float(value) for key, value in dict(stages or {}).items()}
            for tech, stages in dict(timelines_payload.get("development_stage_timelines") or {}).items()
        },
        "repd_status_to_timeline": {
            str(status): dict(config or {})
            for status, config in dict(timelines_payload.get("repd_status_to_timeline") or {}).items()
        },
        # Row order is kept: the original averaged the regions in file order.
        "success_rates": {label: dict(by_region) for label, by_region in rates.items()},
    }


def _timeline_months(stage_tables: Mapping[str, Mapping[str, float]], timeline_technology: str,
                     timeline_type: str, statistic: str) -> tuple[float, str]:
    """Original ``_timeline_months_for_type`` (``solar`` entry as the fallback)."""
    if timeline_technology in stage_tables:
        used = timeline_technology
    elif "solar" in stage_tables:
        used = "solar"
    else:
        raise ValueError(
            f"{CORRECTION_ID}: the pack's development_stage_timelines has no '{timeline_technology}' "
            "entry and no 'solar' entry (the original rule's fallback)"
        )
    stages = stage_tables[used]
    suffix = statistic

    def stage(key: str) -> float:
        if key not in stages:
            raise ValueError(f"{CORRECTION_ID}: development_stage_timelines['{used}'] has no '{key}'")
        return float(stages[key])

    if timeline_type in {f"total_{suffix}", "total_mean", "total_median"}:
        key = f"total_{suffix}"
        months = float(stages[key]) if key in stages else stage("total_median")
    elif timeline_type in {f"pre_construction_{suffix}", "pre_construction_mean", "pre_construction_median"}:
        months = stage(f"pre_construction_{suffix}") + stage(f"construction_{suffix}")
    elif timeline_type in {f"construction_{suffix}", "construction_mean", "construction_median"}:
        months = stage(f"construction_{suffix}")
    elif timeline_type in {f"planning_consenting_{suffix}", "planning_consenting_mean", "planning_consenting_median"}:
        months = stage(f"planning_consenting_{suffix}")
    else:
        months = stage(f"total_{suffix}")
    if not math.isfinite(months) or months < 0:
        raise ValueError(f"{CORRECTION_ID}: invalid development timeline {months} months")
    return months, used


def _success_rate(rates: Mapping[str, Mapping[str, float]], label: str, region: str) -> tuple[float, str]:
    """Original ``_lookup_regional_success_rate`` with the source of the value."""
    by_region = rates.get(label)
    if by_region is not None and region in by_region:
        return float(by_region[region]), "pack_region"
    if by_region is not None:
        values = [float(value) for value in by_region.values()]
        if values:
            return sum(values) / len(values), "pack_technology_mean"
    return SOURCE_DEFAULT_SUCCESS_RATE, "source_default_0.75"


def endogenous_planning_terms(
    parameters: Mapping[str, object] | None,
    *,
    technology: str,
    owner: str,
    decision_year: int,
) -> dict[str, object]:
    """Completion year and success rate of one endogenous proposal (r71)."""
    if not isinstance(parameters, Mapping) or parameters.get("schema_version") != PARAMETERS_SCHEMA:
        raise ValueError(
            f"{CORRECTION_ID}: the run's initial state carries no frozen planning parameters "
            "(state.extensions['planning_parameters']); an endogenous proposal needs the pack's "
            "development timelines and success rates"
        )
    statistic = str(parameters.get("timeline_statistic", "median"))
    if statistic not in {"median", "mean"}:
        raise ValueError(f"{CORRECTION_ID}: unsupported timeline statistic {statistic!r}")
    label = success_label(technology)
    timeline_technology = TIMELINE_TECHNOLOGY.get(label, "solar")
    statuses = dict(parameters.get("repd_status_to_timeline") or {})
    status_config = dict(statuses.get(MODEL_DEVELOPMENT_STATUS) or {"timeline_type": f"total_{statistic}"})
    timeline_type = str(status_config.get("timeline_type", "total_median"))
    if statistic == "mean" and timeline_type.endswith("_median"):
        timeline_type = timeline_type[: -len("_median")] + "_mean"
    elif statistic == "median" and timeline_type.endswith("_mean"):
        timeline_type = timeline_type[: -len("_mean")] + "_median"
    months, used_technology = _timeline_months(
        dict(parameters.get("development_stage_timelines") or {}), timeline_technology, timeline_type, statistic,
    )
    key = model_project_key(owner)
    jitter = (stable_int_hash(key) % (2 * JITTER_MONTHS + 1)) - JITTER_MONTHS
    rounded_months = int(round(max(1.0, months + jitter)))
    year = int(decision_year)
    source_completion = year + rounded_months // 12
    completion = max(source_completion, year + 1)
    region = source_success_region(owner)
    rate, rate_source = _success_rate(dict(parameters.get("success_rates") or {}), label, region)
    if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
        raise ValueError(f"{CORRECTION_ID}: success rate {rate} is not a probability")
    return {
        "schema_version": TERMS_SCHEMA,
        "correction_id": CORRECTION_ID,
        "development_status": MODEL_DEVELOPMENT_STATUS,
        "project_key": key,
        "timeline_statistic": statistic,
        "timeline_type": timeline_type,
        "timeline_technology": used_technology,
        "timeline_months": months,
        "timeline_jitter_months": jitter,
        "timeline_months_applied": rounded_months,
        "source_completion_year": source_completion,
        "completion_year": completion,
        "completion_floor_applied": completion != source_completion,
        "success_technology": label,
        "success_region": region,
        "success_rate": rate,
        "success_rate_source": rate_source,
    }
