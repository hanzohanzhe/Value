"""Canonical data-pack adapter for native single-node PSM modules.

The adapter is the only place in the native path that knows the installed
VALUE-derived file layout.  PSM implementations receive typed arrays only.
"""

from __future__ import annotations

import json
import hashlib
import math
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .asset_economics import build_asset_economic_extensions
from .doctoral_weather import METHOD_ID as DOCTORAL_WEATHER_METHOD, site_weather_profiles, uses_doctoral_weather
from .nuclear_policy import (
    applies_to_data_pack,
    build_value_uk_nuclear_projects,
    existing_nuclear_asset_specs,
    load_value_uk_nuclear_policy,
)
from .storage_catalogue import compatibility_catalogue
from .v2.contracts import (
    AssetStateV2,
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PlanningProject,
    PSMInput,
    StorageDispatchResource,
    YearState,
)


SCHEMA_VERSION = "value.canonical-psm-adapter/v1"
# P0-5a: the chronology adapter reads through data_method (declared reader,
# data policy).  The operating-state adapter is unchanged and keeps v1 (its
# schema id is a column of the frozen doctoral trajectory).
CHRONOLOGY_SCHEMA_VERSION = "value.canonical-psm-adapter/v2"
DOCTORAL_ALIGNMENT_PROFILE = "value.doctoral-national/v1"
INTERCONNECTORS = {
    "france": ("market.france.profile", "market.france.price"),
    "belgium": ("market.belgium.profile", "market.belgium.price"),
    "netherlands": ("market.netherlands.profile", "market.netherlands.price"),
    "norway": ("market.norway.profile", "market.norway.price"),
    "ireland": ("market.ireland.profile", "market.ireland.price"),
}


def _binding_path(pack_root: Path, manifest: Mapping[str, object], role: str) -> Path:
    binding = dict(manifest.get("bindings") or {}).get(role)
    if not isinstance(binding, Mapping):
        raise ValueError(f"Canonical role is not bound: {role}")
    path = (pack_root / str(binding.get("uri") or "")).resolve()
    try:
        path.relative_to(pack_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Canonical binding escapes the pack root: {role}") from exc
    if not path.is_file():
        raise ValueError(f"Canonical binding is missing: {role}")
    return path


def _series(path: Path, *, header: int | None = 0) -> np.ndarray:
    """35aadb3 reader, kept for the frozen reader inventory: no declaration, legacy-v1.

    Production reads go through ``data_method.read_role`` (P0-5a S1).
    """

    from .series_reader import LEGACY, SeriesSpec, read_series

    return read_series(path, SeriesSpec(), mode=LEGACY, legacy_header=header).values


def _clock(values: np.ndarray, periods: int, *, hourly_repeat: bool = False) -> np.ndarray:
    from .series_reader import legacy_clock

    return legacy_clock(values, periods, hourly_repeat=hourly_repeat)


def _technology(value: object) -> str:
    raw = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    if "pumped" in raw and ("hydro" in raw or "storage" in raw):
        return "pumped_hydro"
    if "hydro" in raw:
        return "Hydro_natural_flow"
    if "hydrogen" in raw and ("battery" in raw or "storage" in raw):
        return "hydrogen_battery"
    if re.search(r"(?:^|\s)0?\.25\s*c(?:\s|$)", raw):
        return "0.25c_battery"
    if re.search(r"(?:^|\s)0?\.5\s*c(?:\s|$)", raw):
        return "0.5c_battery"
    if re.search(r"(?:^|\s)1(?:\.0)?\s*c(?:\s|$)", raw):
        return "1c_battery"
    if "solar" in raw:
        return "solar"
    if "offshore" in raw:
        return "offshore"
    if "onshore" in raw or "wind" in raw:
        return "onshore"
    if "battery" in raw or "storage" in raw:
        return "battery"
    if "gas" in raw:
        return "gas"
    return re.sub(r"\s+", "_", raw) or "unknown"


def _date_year(value: object) -> int | None:
    raw = str(value or "").strip()
    if not raw or raw.lower() == "nan":
        return None
    match = re.search(r"(?:19|20)\d{2}", raw)
    return int(match.group(0)) if match else None


def _planning_probability(path: Path) -> dict[tuple[str, str], float]:
    frame = pd.read_csv(path)
    columns = {str(column).strip().lower(): column for column in frame.columns}
    tech_column = columns.get("technology")
    region_column = columns.get("region")
    rate_column = columns.get("success_rate")
    if tech_column is None or region_column is None or rate_column is None:
        return {}
    values: dict[tuple[str, str], float] = {}
    for _, row in frame.iterrows():
        try:
            rate = float(row[rate_column])
        except (TypeError, ValueError):
            continue
        values[(_technology(row[tech_column]), str(row[region_column]).strip().lower())] = min(
            max(rate, 0.0), 1.0
        )
    return values


def _doctoral_parameter_row(asset: AssetStateV2, fleet: Mapping, group: str) -> tuple[dict, dict]:
    """Bind frozen parameters by explicit source identity, never weather identity."""
    rows = dict(fleet.get(group) or {})
    extensions = dict(asset.extensions)
    if extensions.get("doctoral_parameter_source_id"):
        key, basis = str(extensions["doctoral_parameter_source_id"]), "explicit_parameter_source_id"
    elif asset.asset_id in rows:
        key, basis = asset.asset_id, "canonical_asset_id"
    elif extensions.get("source_agent_id"):
        key, basis = str(extensions["source_agent_id"]), "validated_source_agent_id"
    else:
        raise ValueError(f"Missing doctoral parameter source for {asset.asset_id}; weather identity is not a parameter owner")
    if not isinstance(rows.get(key), Mapping) or not rows[key]:
        raise ValueError(f"Missing doctoral parameter source row {group}/{key} for {asset.asset_id}")
    source_technology, asset_technology = _technology(key), _technology(asset.technology)
    if source_technology != asset_technology and not (
        asset_technology == "gas" and source_technology in {"ccgt", "ocgt"}
    ):
        raise ValueError(f"Doctoral parameter source technology mismatch for {asset.asset_id}: {key} / {asset.technology}")
    raw = dict(rows[key])
    return raw, {
        "doctoral_parameter_source_id": key,
        "doctoral_parameter_binding_basis": basis,
        "doctoral_parameter_source_group": group,
        "doctoral_parameter_row_sha256": hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest(),
    }


def _doctoral_marginal_cost(raw: Mapping, technology: str, source_id: str) -> float:
    fields = ("gen_cost", "unit_time_cost")
    if technology in {"CCGT", "OCGT", "gas", "bio_and_waste"}:
        fields += ("fuel_cost", "carbon_price")
    missing = [key for key in fields if key not in raw or raw[key] is None]
    if missing:
        raise ValueError(f"Doctoral parameter source {source_id} missing cost fields: {', '.join(missing)}")
    values = [float(raw[key]) for key in fields]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Non-finite doctoral parameter cost in {source_id}")
    return sum(values)


def native_initial_state(
    pack_root: Path,
    year: int,
    *,
    capital_discount_rate: float = 0.05,
    scientific_parameters: Mapping[str, object] | None = None,
    doctoral_alignment: bool = False,
) -> YearState:
    """Build a typed state from canonical bindings, without a legacy factory call."""

    pack_root = pack_root.resolve()
    manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    model_parameters = json.loads(
        _binding_path(pack_root, manifest, "config.model_parameters").read_text(encoding="utf-8")
    )
    fleet = json.loads(
        _binding_path(pack_root, manifest, "fleet.generators").read_text(encoding="utf-8")
    )
    costs = json.loads(
        _binding_path(pack_root, manifest, "costs.capital").read_text(encoding="utf-8")
    ).get("capital_costs_per_mw", {})
    timelines_payload = json.loads(
        _binding_path(pack_root, manifest, "planning.timelines").read_text(encoding="utf-8")
    )
    timelines = dict(timelines_payload.get("development_timelines") or {})
    compatibility_unparameterized = scientific_parameters is None and not doctoral_alignment
    parameters = dict(scientific_parameters or {})
    success_mode = str(parameters.get("planning.success_mode", "expected_capacity"))
    success_mode = {
        "expected": "expected_capacity",
        "stochastic": "seeded_stochastic",
    }.get(success_mode, success_mode)
    random_seed = int(parameters.get("planning.random_seed", 0) or 0)
    include_uncertain = bool(parameters.get("planning.include_uncertain_projects", True))
    zombie_filter = bool(parameters.get("planning.zombie_filter_enabled", not compatibility_unparameterized))
    zombie_stale_year = int(parameters.get("planning.zombie_status_stale_year", 2015) or 2015)
    construction_grace = int(parameters.get("planning.construction_grace_years", 2) or 0)
    minimum_size = float(parameters.get("planning.minimum_project_size_mw", 0.0 if compatibility_unparameterized else 1.0) or 0.0)
    maximum_completion = int(parameters.get("planning.max_completion_year", 9999 if compatibility_unparameterized else 2040) or 2040)
    timeline_statistic = str(parameters.get("planning.timeline_statistic", "median"))
    defer_spread_years = int(parameters.get("planning.defer_spread_years", 0 if compatibility_unparameterized else 3) or 0)
    repd_battery_assignment = str(
        parameters.get(
            "planning.repd_battery_assignment",
            "legacy_all_0.25c" if compatibility_unparameterized else "value_proportional_split",
        )
    )
    preprocessing_counts: Counter[str] = Counter()
    success_rates = _planning_probability(
        _binding_path(pack_root, manifest, "planning.success_rates")
    )
    repd = pd.read_csv(_binding_path(pack_root, manifest, "projects.repd"))
    repd.columns = [str(column).strip() for column in repd.columns]
    superseded_repd_ids: set[str] = set()
    if not compatibility_unparameterized:
        raw_repd_path = _binding_path(pack_root, manifest, "source.repd_raw")
        try:
            raw_repd = pd.read_csv(raw_repd_path, encoding="utf-8", dtype=str, low_memory=False)
        except UnicodeDecodeError:
            raw_repd = pd.read_csv(raw_repd_path, encoding="latin1", dtype=str, low_memory=False)
        raw_ids = {
            str(value).strip()
            for value in raw_repd.get("Ref ID", pd.Series(dtype=str)).fillna("")
            if str(value).strip()
        }
        for _, raw_row in raw_repd.iterrows():
            project_id = str(raw_row.get("Ref ID") or "").strip()
            replacement_id = str(
                raw_row.get("Are they re-applying (New REPD Ref)") or ""
            ).strip()
            if (
                project_id
                and replacement_id
                and replacement_id.lower() != "nan"
                and replacement_id != project_id
                and replacement_id in raw_ids
            ):
                superseded_repd_ids.add(project_id)
    lives = dict(model_parameters["investment_parameters"].get("target_payback_years") or {})
    lives.update({
        "CCGT": 25.0,
        "OCGT": 25.0,
        "bio_and_waste": 25.0,
        "Nuclear": 40.0,
        "Hydro_natural_flow": 50.0,
    })
    target_paybacks = dict(lives)
    if doctoral_alignment:
        # Source config.py:60 uses 20 years in the investment decision; the
        # independent asset-economics lifetime remains 25 years.
        target_paybacks["bio_and_waste"] = 20.0
    preferred_rates = dict(
        model_parameters.get("investment_methodology_external", {}).get("preferred_rates") or {}
    )
    assets: list[AssetStateV2] = []
    # A compact public/synthetic pack may intentionally contain no VRE or
    # storage assets.  In that case the REPD operational-stock mapper has no
    # work to do, so do not import its optional geospatial/weather stack.
    # Full UK packs still take the preserved VALUE-derived mapping path.
    fleet_generators = dict(fleet.get("generators") or {})
    requires_repd_snapshot = bool(fleet.get("batteries")) or any(
        _technology(name) in {"solar", "onshore", "offshore"}
        for name in fleet_generators
    )
    if requires_repd_snapshot:
        from .builtin.scheme_c_1000twh.runtime_compat.modular_investment_support import (
            build_repd_operational_snapshot,
        )

        scheme_c_vre_snapshot, scheme_c_battery_mw = build_repd_operational_snapshot(
            year,
            str(_binding_path(pack_root, manifest, "source.repd_raw")),
        )
    else:
        scheme_c_vre_snapshot, scheme_c_battery_mw = {}, 0.0

    def add_asset(
        asset_id: str,
        technology: str,
        capacity_mw: float,
        *,
        region: str = "GB",
        energy_capacity_mwh: float | None = None,
        source: str,
        extra: Mapping[str, object] | None = None,
        capital_cost_per_mw_override: float | None = None,
        investment_owner_id: str | None = None,
        investment_eligible: bool = True,
    ) -> None:
        if capacity_mw <= 0:
            return
        extensions = dict(extra or {})
        if doctoral_alignment and (asset_id in fleet_generators or asset_id in dict(fleet.get("batteries") or {})):
            extensions["doctoral_parameter_source_id"] = asset_id
        extensions.update(build_asset_economic_extensions(
            technology,
            float(capacity_mw),
            energy_capacity_mwh=energy_capacity_mwh,
            capital_costs_per_mw=costs,
            lifetimes=lives,
            discount_rate=float(capital_discount_rate),
            source_record_id=asset_id,
            capital_cost_per_mw_override=capital_cost_per_mw_override,
        ))
        extensions.update({
            "source": source,
            "investment_owner_id": investment_owner_id or asset_id,
            "investment_eligible": bool(investment_eligible),
            "preferred_rate": float(preferred_rates.get(technology, 0.08) or 0.08),
            "target_payback_years": float(
                target_paybacks.get(technology, target_paybacks.get("default", 25.0)) or 25.0
            ),
            "annualized_capital_basis": "audited_asset_economics",
        })
        assets.append(AssetStateV2(
            asset_id,
            technology,
            float(capacity_mw),
            float(energy_capacity_mwh) if energy_capacity_mwh is not None else None,
            region,
            extensions=extensions,
        ))

    # The fleet binding is the authoritative operating-fleet input. VRE entries
    # use the explicit capacity multiplier carried by the copied data snapshot.
    vre_capacity_present = {"solar": 0.0, "onshore": 0.0, "offshore": 0.0}
    nuclear_policy_enabled = False
    nuclear_policy_summary: dict[str, object] | None = None
    for asset_id, raw_value in dict(fleet.get("generators") or {}).items():
        raw = dict(raw_value or {})
        technology = _technology(asset_id)
        if technology not in vre_capacity_present:
            technology = str(asset_id)
        capacity = float(
            scheme_c_vre_snapshot.get(asset_id, 0.0)
            if technology in vre_capacity_present
            else raw.get("capacity_limit", 0.0)
            or 0.0
        )
        if technology in vre_capacity_present:
            vre_capacity_present[technology] += capacity
        region = str(asset_id).split("_", 1)[1] if "_" in str(asset_id) and technology in {"solar", "onshore"} else "GB"
        if technology == "Nuclear" and applies_to_data_pack(manifest):
            nuclear_policy = load_value_uk_nuclear_policy()
            nuclear_policy_enabled = True
            nuclear_policy_summary = {
                "schema_version": nuclear_policy["schema_version"],
                "policy_id": nuclear_policy["policy_id"],
                "version": nuclear_policy["version"],
                "declared_existing_capacity_mw": nuclear_policy[
                    "declared_existing_capacity_mw"
                ],
                "endogenous_investment_allowed": nuclear_policy[
                    "endogenous_investment_allowed"
                ],
            }
            declared_capacity = float(nuclear_policy["declared_existing_capacity_mw"])
            aggregate_capital_cost = float(raw.get("capital_cost", 0.0) or 0.0)
            capital_cost_per_mw = (
                aggregate_capital_cost / declared_capacity
                if aggregate_capital_cost > 0 and declared_capacity > 0
                else None
            )
            for station in existing_nuclear_asset_specs(year):
                add_asset(
                    str(station["asset_id"]),
                    "Nuclear",
                    float(station["capacity_mw"]),
                    source="EDF station fleet under declared VALUE-UK nuclear policy",
                    capital_cost_per_mw_override=capital_cost_per_mw,
                    investment_eligible=False,
                    extra={
                        **({"doctoral_parameter_source_id": "Nuclear", "doctoral_dispatch_asset_id": "Nuclear"}
                           if doctoral_alignment else {}),
                        "station_id": station["station_id"],
                        "station_name": station["name"],
                        "model_unavailable_from_year": int(
                            station["model_unavailable_from_year"]
                        ),
                        "announced_generation_end": station["announced_generation_end"],
                        "source_title": station["source_title"],
                        "source_url": station["source_url"],
                        "nuclear_policy_id": nuclear_policy["policy_id"],
                        "nuclear_policy_version": nuclear_policy["version"],
                        "spatial_mapping_asset_id": "Nuclear",
                        "marginal_cost_components": {
                            "fuel_cost": float(raw.get("fuel_cost", 0.0) or 0.0),
                            "carbon_price": float(raw.get("carbon_price", 0.0) or 0.0),
                            "generation_cost": float(raw.get("gen_cost", 0.0) or 0.0),
                        },
                    },
                )
            continue
        add_asset(
            str(asset_id), technology, capacity, region=region,
            source="fleet.generators canonical binding",
            capital_cost_per_mw_override=(
                None
                if costs.get(technology) is not None
                else (
                    float(raw.get("capital_cost", 0.0) or 0.0) / capacity
                    if capacity > 0 and float(raw.get("capital_cost", 0.0) or 0.0) > 0
                    else None
                )
            ),
            extra={
                "marginal_cost_components": {
                    "fuel_cost": float(raw.get("fuel_cost", 0.0) or 0.0),
                    "carbon_price": float(raw.get("carbon_price", 0.0) or 0.0),
                    "generation_cost": float(raw.get("gen_cost", 0.0) or 0.0),
                },
                **({
                    "capital_cost_scope": "existing_stock_compatibility",
                    "new_build_cost_inheritable": False,
                    "capital_cost_scope_note": (
                        "Preserved VALUE existing-stock accounting basis; "
                        "not a sourced new-build hydro CAPEX."
                    ),
                } if technology == "Hydro_natural_flow" else {}),
            },
        )

    status_column = "development_status"
    capacity_column = "capacity_mw"
    technology_column = "technology"
    operational_rows: list[tuple[int, object]] = []
    for index, row in repd.iterrows():
        status = str(row.get(status_column, "")).strip().lower()
        operational_year = _date_year(row.get("operational"))
        if status == "operational" or (operational_year is not None and operational_year <= year):
            operational_rows.append((index, row))

    # Generic packs need not pre-aggregate VRE in fleet.generators. In that
    # case, canonical operational REPD rows become explicit site assets.
    for index, row in operational_rows:
        technology = _technology(
            f"{row.get(technology_column, '')} {row.get('technology_source', '')}"
        )
        if technology not in vre_capacity_present or vre_capacity_present[technology] > 0:
            continue
        try:
            capacity = float(row.get(capacity_column, 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        add_asset(
            f"repd-operating:{row.get('project_id', index)}",
            technology,
            capacity,
            region=str(row.get("region") or "GB"),
            source="projects.repd operational record",
            investment_owner_id=f"force-owner:{technology}:{str(row.get('region') or 'GB')}",
        )

    operational_storage_mw = float(scheme_c_battery_mw)
    storage_catalogue = compatibility_catalogue().technologies
    battery_rows = dict(fleet.get("batteries") or {})
    weighted = {
        asset_id: max(float(dict(raw or {}).get("pool_limit", 0.0) or 0.0), 1.0)
        for asset_id, raw in battery_rows.items()
        if asset_id != "pumpedhydro_battery"
    }
    weight_total = sum(weighted.values())
    storage_technology = {
        "pumpedhydro_battery": "pumped_hydro",
        "1c_battery": "1c_battery",
        "0.5c_battery": "0.5c_battery",
        "0.25c_battery": "0.25c_battery",
        "hydrogen_battery": "hydrogen_battery",
    }
    catalogue_key = {
        "pumped_hydro": "pumped_hydro", "1c_battery": "1c",
        "0.5c_battery": "0.5c", "0.25c_battery": "0.25c",
        "hydrogen_battery": "hydrogen",
    }
    for asset_id, raw_value in battery_rows.items():
        raw = dict(raw_value or {})
        technology = storage_technology.get(str(asset_id), str(asset_id))
        if asset_id == "pumpedhydro_battery":
            capacity = 2828.0 if year == 2025 else float(
                raw.get("initial_power_capacity_mw", raw.get("per_pool_limit", 0.0)) or 0.0
            )
        elif weight_total > 0:
            capacity = operational_storage_mw * weighted.get(asset_id, 0.0) / weight_total
        else:
            capacity = float(raw.get("initial_power_capacity_mw", 0.0) or 0.0)
        specification = storage_catalogue.get(catalogue_key.get(technology, ""))
        duration = specification.duration_hours if specification is not None else 1.0
        add_asset(
            str(asset_id), technology, capacity,
            energy_capacity_mwh=(26700.0 if asset_id == "pumpedhydro_battery" and year == 2025 else capacity * duration),
            source="fleet.generators storage binding plus operational projects.repd allocation",
            extra={"storage_catalogue_id": compatibility_catalogue().catalogue_id},
        )

    projects: list[PlanningProject] = []
    terminal_statuses = {"operational", "abandoned", "planning permission refused", "application withdrawn"}
    uncertain_statuses = {"application submitted", "appeal lodged", "revised"}
    high_confidence_statuses = {
        "under construction", "awaiting construction", "planning permission granted"
    }
    negative_statuses = {
        "application refused", "application withdrawn", "abandoned", "appeal refused",
        "appeal withdrawn", "decommissioned", "application expired", "finished",
        "planning permission refused",
    }

    def timeline_months(technology: str, status: str) -> float:
        base = "battery" if technology in {
            "pumped_hydro", "1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"
        } else technology
        status_row = dict(
            dict(timelines_payload.get("repd_status_to_timeline") or {}).get(status, {}) or {}
        )
        timeline_type = str(status_row.get("timeline_type") or f"total_{timeline_statistic}")
        timeline_type = re.sub(r"_(?:mean|median)$", f"_{timeline_statistic}", timeline_type)
        stage_values = dict(
            dict(timelines_payload.get("development_stage_timelines") or {}).get(base, {}) or {}
        )
        if timeline_type in stage_values:
            return float(stage_values[timeline_type])
        fallback = timelines.get(base, timelines.get(technology, 12.0))
        return float(fallback or 12.0)

    def latest_progress_year(row: object) -> int | None:
        years = [
            _date_year(row.get(column))
            for column in (
                "planning_application_submitted", "planning_permission_granted",
                "under_construction", "operational",
            )
        ]
        known = [value for value in years if value is not None]
        return max(known) if known else None

    storage_catalogue_key = {
        "pumped_hydro": "pumped_hydro",
        "1c_battery": "1c",
        "0.5c_battery": "0.5c",
        "0.25c_battery": "0.25c",
        "hydrogen_battery": "hydrogen",
    }
    scheme_c_storage_weights: dict[str, float] = {}
    for asset_id, value in weighted.items():
        typed = storage_technology.get(str(asset_id), str(asset_id))
        if typed in storage_catalogue_key and typed != "pumped_hydro":
            scheme_c_storage_weights[typed] = (
                scheme_c_storage_weights.get(typed, 0.0) + float(value)
            )

    def typed_project_components(
        physical_project_id: str,
        source_technology: str,
        declared_capacity_mw: float,
    ) -> tuple[tuple[str, str, float, str], ...]:
        if source_technology != "battery":
            return ((physical_project_id, source_technology, declared_capacity_mw, "source_typed"),)
        if compatibility_unparameterized or repd_battery_assignment == "legacy_all_0.25c":
            return ((physical_project_id, "0.25c_battery", declared_capacity_mw, "legacy_all_0.25c"),)
        fixed = {
            "all_1c": "1c_battery",
            "all_0.5c": "0.5c_battery",
            "all_0.25c": "0.25c_battery",
        }.get(repd_battery_assignment)
        if fixed is not None:
            return ((f"{physical_project_id}:{fixed}", fixed, declared_capacity_mw, repd_battery_assignment),)
        if repd_battery_assignment == "exclude_untyped":
            return ()
        if repd_battery_assignment != "value_proportional_split":
            raise ValueError(
                "Unsupported planning.repd_battery_assignment: "
                f"{repd_battery_assignment}"
            )
        total_weight = sum(scheme_c_storage_weights.values())
        if total_weight <= 0:
            raise ValueError("VALUE battery assignment has no positive template weights")
        return tuple(
            (
                f"{physical_project_id}:{technology}",
                technology,
                declared_capacity_mw * weight / total_weight,
                "value_proportional_four_technology_split",
            )
            for technology, weight in sorted(scheme_c_storage_weights.items())
        )

    for index, row in (() if doctoral_alignment else repd.iterrows()):
        project_id = str(row.get("project_id") or f"repd:{index}")
        if project_id in superseded_repd_ids:
            preprocessing_counts["excluded_superseded_reapplication"] += 1
            continue
        status = str(row.get(status_column, "")).strip()
        status_key = status.lower()
        if status_key in terminal_statuses or (zombie_filter and status_key in negative_statuses):
            preprocessing_counts["excluded_terminal_or_status_zombie"] += 1
            continue
        try:
            capacity = float(row.get(capacity_column, 0.0) or 0.0)
        except (TypeError, ValueError):
            preprocessing_counts["excluded_invalid_capacity"] += 1
            continue
        if capacity <= 0 or capacity < minimum_size:
            preprocessing_counts["excluded_below_minimum_size"] += 1
            continue
        source_technology = _technology(
            f"{row.get(technology_column, '')} {row.get('technology_source', '')}"
        )
        if not include_uncertain and status_key in uncertain_statuses:
            preprocessing_counts["excluded_uncertain_status"] += 1
            continue
        if not include_uncertain and status_key not in high_confidence_statuses:
            preprocessing_counts["excluded_unknown_status"] += 1
            continue
        progress_year = latest_progress_year(row)
        if (
            zombie_filter
            and status_key in uncertain_statuses
            and progress_year is not None
            and progress_year <= zombie_stale_year
        ):
            preprocessing_counts["excluded_status_stagnant"] += 1
            continue
        region = str(row.get("region") or "GB")
        completion = next((candidate for candidate in (
            _date_year(row.get("operational")),
            _date_year(row.get("under_construction")),
        ) if candidate is not None and candidate > year), None)
        if completion is None:
            months = timeline_months(source_technology, status)
            completion = year + max(1, int(math.ceil(months / 12.0)))
            if defer_spread_years > 0:
                completion += int(
                    hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:8], 16
                ) % (defer_spread_years + 1)
        if (
            zombie_filter
            and status_key == "under construction"
            and _date_year(row.get("under_construction")) is not None
        ):
            construction_year = int(_date_year(row.get("under_construction")) or year)
            construction_end = construction_year + max(
                1, int(math.ceil(timeline_months(source_technology, status) / 12.0))
            ) + construction_grace
            if construction_end < year:
                preprocessing_counts["excluded_schedule_overdue"] += 1
                continue
        if completion > maximum_completion:
            preprocessing_counts["excluded_after_max_completion_year"] += 1
            continue
        probability_key = "battery" if source_technology == "battery" else _technology(source_technology)
        probability = success_rates.get(
            (probability_key, region.strip().lower()),
            success_rates.get((probability_key, "gb"), 1.0),
        )
        draw = int(
            hashlib.sha256(f"{random_seed}:{project_id}".encode("utf-8")).hexdigest()[:13], 16
        ) / float(16 ** 13 - 1)
        realised_failure = success_mode == "seeded_stochastic" and draw > probability
        components = typed_project_components(project_id, source_technology, capacity)
        if not components:
            preprocessing_counts["excluded_untyped_battery"] += 1
            continue
        if source_technology == "battery":
            preprocessing_counts["included_battery_physical_projects"] += 1
            preprocessing_counts["included_battery_typed_components"] += len(components)
        for component_id, technology, declared_component_capacity, assignment_method in components:
            effective_capacity = (
                declared_component_capacity
                if compatibility_unparameterized
                else (
                    declared_component_capacity * probability
                    if success_mode == "expected_capacity"
                    else declared_component_capacity
                )
            )
            energy_capacity_mwh = None
            duration_hours = None
            if technology in storage_catalogue_key:
                duration_hours = compatibility_catalogue().get(
                    storage_catalogue_key[technology]
                ).duration_hours
                energy_capacity_mwh = effective_capacity * duration_hours
            economics_capacity = (
                declared_component_capacity
                if compatibility_unparameterized
                else effective_capacity
            )
            project_extensions = build_asset_economic_extensions(
                technology,
                economics_capacity,
                energy_capacity_mwh=energy_capacity_mwh,
                capital_costs_per_mw=costs,
                lifetimes=lives,
                discount_rate=float(capital_discount_rate),
                source_record_id=project_id,
            )
            project_extensions.update({
                "source_role": "projects.repd",
                "physical_project_id": project_id,
                "typed_component_id": component_id,
                "repd_source_technology": source_technology,
                "repd_battery_assignment_method": assignment_method,
                "source_declared_capacity_mw": capacity,
                "component_declared_capacity_mw": declared_component_capacity,
                "energy_capacity_mwh": energy_capacity_mwh,
                "declared_duration_hours": duration_hours,
                "expected_economics_capacity_mw": economics_capacity,
                "preferred_rate": float(preferred_rates.get(technology, 0.08) or 0.08),
                "target_payback_years": float(
                    lives.get(technology, lives.get("default", 25.0)) or 25.0
                ),
                "development_years": max(1, completion - year),
                "planning_preprocessing_contract": "value.planning-preprocessing-contract/v1",
                "planning_timeline_statistic": timeline_statistic,
            })
            projects.append(PlanningProject(
                component_id,
                str(row.get("site_name") or project_id),
                "repd",
                technology,
                effective_capacity,
                declared_component_capacity,
                region,
                status or "external_pipeline",
                "failed" if realised_failure else "active",
                year,
                completion,
                success_mode,
                min(max(probability, 0.0), 1.0),
                random_draw=draw if success_mode == "seeded_stochastic" else None,
                outcome="failed_planning" if realised_failure else "active",
                extensions=project_extensions,
            ))
            preprocessing_counts[
                "included_seeded_failure" if realised_failure else "included_active"
            ] += 1
    doctoral_project_rows: list[dict[str, object]] = []
    if doctoral_alignment:
        from .builtin.scheme_c_1000twh.doctoral_planning import (
            PREPROCESSING_SCHEMA, PROGRESS_COLUMNS, ROW_ALIASES,
            preprocess_doctoral_project_records,
        )

        # The canonical table remains authoritative for project identity and
        # user-editable facts. The original milestones supply the full source
        # history, including appeals and Secretary of State decisions omitted
        # by the normalized table. Canonical-only projects remain explicit.
        raw_by_id = {
            str(raw.get("Ref ID") or "").strip(): raw
            for raw in raw_repd.where(pd.notna(raw_repd), None).to_dict(orient="records")
        }
        prepared_rows: list[dict[str, object]] = []
        provenances: list[str] = []
        for index, row in repd.iterrows():
            normal = {str(key): None if pd.isna(value) else value for key, value in row.items()}
            physical_id = str(normal.get("project_id") or f"repd:{index}")
            prepared = {
                column: normal.get(alias)
                for column, alias in ROW_ALIASES.items()
                if alias in normal
            }
            prepared["Ref ID"] = physical_id
            prepared["Site Name"] = normal.get("site_name") or physical_id
            prepared["Technology Type"] = normal.get("technology_source") or normal.get("technology") or ""
            original = raw_by_id.get(physical_id)
            provenance = "canonical_only" if original is None else "canonical_with_raw_milestones"
            if original is not None:
                for column in PROGRESS_COLUMNS:
                    if column in original:
                        prepared[column] = original[column]
            prepared_rows.append(prepared)
            provenances.append(provenance)
        context = {
            "start_year": year, "include_uncertain_projects": include_uncertain,
            "development_stage_timelines": dict(timelines_payload.get("development_stage_timelines") or {}),
            "repd_status_to_timeline": dict(timelines_payload.get("repd_status_to_timeline") or {}),
            "success_rates": success_rates, "success_mode": success_mode,
            "zombie_filter_enabled": zombie_filter, "zombie_status_stale_year": zombie_stale_year,
            "zombie_snapshot_year": year, "construction_grace_years": construction_grace,
            "minimum_project_size_mw": minimum_size, "max_completion_year": maximum_completion,
            "timeline_statistic": timeline_statistic, "defer_spread_years": defer_spread_years,
            "apply_repd_initial_snapshot": bool(parameters.get("fleet.repd_initial_snapshot", True)),
            "random_seed": random_seed,
        }
        if not context["development_stage_timelines"].get("solar"):
            raise ValueError("Doctoral planning requires frozen development_stage_timelines including solar")
        for record in preprocess_doctoral_project_records(prepared_rows, context):
            provenance = provenances[int(record["row_index"])]
            diagnostic = {key: value for key, value in record.items() if key != "source_row"}
            diagnostic["provenance"] = provenance
            doctoral_project_rows.append(diagnostic)
            if not record["retained"]:
                preprocessing_counts[str(record["reason"])] += 1
                continue
            project_id = str(record["project_id"])
            technology_source = str(record["technology"])
            declared_capacity = float(record["original_capacity_mw"])
            components = typed_project_components(project_id, technology_source, declared_capacity)
            if not components:
                diagnostic.update(retained=False, reason="excluded_untyped_battery")
                preprocessing_counts["excluded_untyped_battery"] += 1
                continue
            if technology_source == "battery":
                preprocessing_counts["included_battery_physical_projects"] += 1
                preprocessing_counts["included_battery_typed_components"] += len(components)
            effective_ratio = float(record["capacity_mw"]) / declared_capacity if declared_capacity else 0.0
            failed = not bool(record["project_succeeds"])
            completion = int(record["completion_year"])
            for component_id, technology, component_capacity, assignment in components:
                effective_capacity = component_capacity * effective_ratio
                duration = compatibility_catalogue().get(storage_catalogue_key[technology]).duration_hours if technology in storage_catalogue_key else None
                energy = effective_capacity * duration if duration is not None else None
                extensions = build_asset_economic_extensions(
                    technology, effective_capacity, energy_capacity_mwh=energy,
                    capital_costs_per_mw=costs, lifetimes=lives,
                    discount_rate=float(capital_discount_rate), source_record_id=project_id,
                )
                extensions.update({
                    "source_role": "projects.repd", "physical_project_id": project_id,
                    "typed_component_id": component_id, "repd_source_technology": technology_source,
                    "repd_battery_assignment_method": assignment,
                    "source_declared_capacity_mw": declared_capacity,
                    "component_declared_capacity_mw": component_capacity,
                    "energy_capacity_mwh": energy, "declared_duration_hours": duration,
                    "expected_economics_capacity_mw": effective_capacity,
                    "preferred_rate": float(preferred_rates.get(technology, 0.08) or 0.08),
                    "target_payback_years": float(target_paybacks.get(technology, target_paybacks.get("default", 25.0)) or 25.0),
                    "development_years": max(1, completion - year),
                    "planning_preprocessing_contract": PREPROCESSING_SCHEMA,
                    "planning_timeline_statistic": timeline_statistic,
                    "doctoral_row_provenance": provenance,
                    "doctoral_preprocessing": diagnostic,
                    "success_rate_applied": record["success_rate_applied"],
                    "success_evaluated": True,
                    "success_draw_method": record["success_draw_method"],
                })
                projects.append(PlanningProject(
                    component_id, str(record["name"]), "repd", technology,
                    effective_capacity, component_capacity, str(record["region"]),
                    str(record["development_status"]), "failed" if failed else "active",
                    year, completion, str(record["success_mode"]), float(record["success_probability"]),
                    random_draw=record["random_draw"], outcome="failed_planning" if failed else "active",
                    failure_reason_code="failed_due_to_success_rate" if failed else None,
                    extensions=extensions,
                ))
                preprocessing_counts["included_seeded_failure" if failed else "included_active"] += 1
    if nuclear_policy_enabled:
        projects.extend(
            build_value_uk_nuclear_projects(
                start_year=year,
                end_year=2034,
                capital_discount_rate=float(capital_discount_rate),
            )
        )
        if doctoral_alignment:
            projects = [replace(project, extensions={
                **dict(project.extensions),
                "doctoral_parameter_source_id": "Nuclear",
                "doctoral_dispatch_asset_id": "Nuclear",
            }) if project.technology == "Nuclear" else project for project in projects]
    state = YearState(
        year,
        tuple(assets),
        tuple(projects),
        extensions={
            "source": "copied VALUE initial-state adapter",
            "adapter_schema": SCHEMA_VERSION,
            "legacy_factory_called": False,
            "canonical_pipeline_count": len(projects),
            **({"doctoral_alignment_profile": "value.doctoral-national/v1"} if doctoral_alignment else {}),
            **({"nuclear_policy": nuclear_policy_summary} if nuclear_policy_summary else {}),
            "planning_preprocessing": {
                "schema_version": "value.planning-preprocessing-evidence/v1",
                "contract_id": "value-canonical-planning-input-v1",
                "parameters": {
                    "planning.include_uncertain_projects": include_uncertain,
                    "planning.zombie_filter_enabled": zombie_filter,
                    "planning.zombie_status_stale_year": zombie_stale_year,
                    "planning.construction_grace_years": construction_grace,
                    "planning.minimum_project_size_mw": minimum_size,
                    "planning.max_completion_year": maximum_completion,
                    "planning.timeline_statistic": timeline_statistic,
                    "planning.defer_spread_years": defer_spread_years,
                    "planning.repd_battery_assignment": repd_battery_assignment,
                    "planning.success_mode": success_mode,
                    "planning.random_seed": random_seed,
                },
                "counts": dict(sorted(preprocessing_counts.items())),
                **({"doctoral_project_rows": doctoral_project_rows} if doctoral_alignment else {}),
            },
        },
    )
    if uses_doctoral_weather(manifest):
        from .doctoral_weather_mapping import attach_project_weather
        raw_path = _binding_path(pack_root, manifest, "source.repd_raw")
        try:
            weather_repd = pd.read_csv(raw_path, encoding="utf-8", dtype=str, low_memory=False)
        except UnicodeDecodeError:
            weather_repd = pd.read_csv(raw_path, encoding="latin1", dtype=str, low_memory=False)
        state = attach_project_weather(state, fleet, weather_repd)
    if "value.zonal.asset-map" in dict(manifest.get("bindings") or {}):
        from .spatialization import attach_spatial_metadata_from_pack

        state = attach_spatial_metadata_from_pack(state, pack_root, manifest)
    return state


def build_doctoral_psm_input(
    pack_root: Path, manifest: Mapping[str, object], state: OperatingState, *,
    run_id: str, periods: int, period_hours: float = 0.5,
    parameters: Mapping[str, object] | None = None,
    terminal_soc_rule: str = "free", voll_gbp_per_mwh: float = 10_000.0,
    data_policy: "DataMethodPolicy | None" = None,
) -> PSMInput:
    """Build one explicitly selected national input from the station register.

    The returned OperatingState is a dispatch/cashflow view, NOT a replacement
    for the authoritative station state used by annual planning/retirement.
    Existing staged and zonal paths do not select this entry point.
    """
    from .builtin.scheme_c_1000twh.doctoral_nuclear import aggregate_doctoral_nuclear_state

    if period_hours != 0.5:
        raise ValueError("Doctoral national input requires half-hour periods")
    evidence = None
    if applies_to_data_pack(manifest) and state.extensions.get("nuclear_policy"):
        policy = load_value_uk_nuclear_policy()
        declared = state.extensions["nuclear_policy"]
        if any(declared.get(key) != policy[key] for key in ("policy_id", "version")):
            raise ValueError("Nuclear policy identity differs from station state")
        evidence = policy  # Full cost evidence, including Sizewell B life extension; provenance only.
    national = aggregate_doctoral_nuclear_state(state, policy_evidence=evidence)
    if data_policy is None:
        from .data_method import run_policy

        data_policy = run_policy(manifest)
    chronology = build_chronology(pack_root, manifest, national, periods=periods,
        period_hours=period_hours, data_policy=data_policy, terminal_soc_rule=terminal_soc_rule,
        voll_gbp_per_mwh=voll_gbp_per_mwh)
    return PSMInput(run_id, state.year, str(manifest.get("id") or ""), national,
        period_hours, dict(parameters or {}), chronology=chronology,
        extensions={"doctoral_alignment_profile": DOCTORAL_ALIGNMENT_PROFILE,
                    "state_scope": "national_dispatch_view_not_annual_station_register"})


def build_chronology(
    pack_root: Path,
    manifest: Mapping[str, object],
    state: OperatingState,
    *,
    periods: int,
    period_hours: float,
    data_policy: "DataMethodPolicy",
    terminal_soc_rule: str = "cyclic",
    voll_gbp_per_mwh: float = 10_000.0,
) -> ChronologicalPSMData:
    """Normalize one immutable pack/state revision to chronological contracts.

    ``data_policy`` (required, P0-5a S3) selects the reading method; every
    chronological role is read through ``data_method.read_role``.
    """

    from .data_method import DataMethodPolicy, chronology_extension, read_boundary, read_role

    if not isinstance(data_policy, DataMethodPolicy):
        raise TypeError("build_chronology requires a DataMethodPolicy (data_method.policy_for)")
    pack_root = pack_root.resolve()
    series = {
        role: read_role(pack_root, manifest, role, data_policy, periods=periods)
        for role in ("demand.real", "demand.forecast", "profiles.vre_solar", "profiles.vre_onshore",
                     "profiles.vre_offshore")
    }
    boundary = read_boundary(pack_root, manifest, data_policy, periods=periods)
    # VALUE-derived source rows are instantaneous MW even though the old
    # import manifests labelled them MWh/period.  The typed PSM boundary is
    # strictly MWh/period, so conversion belongs here, once, and is declared in
    # the chronology evidence.  The retained kernel continues to read its
    # unchanged source files and performs the same multiplication internally.
    demand = series["demand.real"].values * period_hours
    forecast_demand = series["demand.forecast"].values * period_hours
    fleet = json.loads(
        _binding_path(pack_root, manifest, "fleet.generators").read_text(encoding="utf-8")
    )
    doctoral_alignment = state.extensions.get("doctoral_alignment_profile") == DOCTORAL_ALIGNMENT_PROFILE
    doctoral_weather = uses_doctoral_weather(manifest)
    if doctoral_alignment and not doctoral_weather:
        raise ValueError("Doctoral national profile requires bound doctoral site weather; CSV dispatch fallback is not permitted")
    profiles = {
        "solar": series["profiles.vre_solar"].values,
        "onshore": series["profiles.vre_onshore"].values,
        "offshore": series["profiles.vre_offshore"].values,
    }
    profiles = {key: np.clip(value, 0.0, 1.0) for key, value in profiles.items()}
    # The CSVs remain investment-cap inputs. The doctoral UK weather bindings
    # must generate dispatch bounds by representative site, not by technology.
    site_profiles = {}
    if doctoral_weather and any(a.technology in profiles and a.capacity_mw > 0 for a in state.assets):
        roles = {"weather.solar" if a.technology == "solar" else "weather.wind"
                 for a in state.assets if a.technology in profiles and a.capacity_mw > 0}
        site_profiles = site_weather_profiles(
            paths={role: _binding_path(pack_root, manifest, role) for role in roles},
            hashes={role: str(manifest["bindings"][role].get("sha256") or "") for role in roles},
            fleet=fleet, assets=state.assets, periods=periods, period_hours=period_hours,
        )
    state_by_id = {asset.asset_id: asset for asset in state.assets}
    resources: list[DispatchResource] = []
    storage_assets: list[StorageDispatchResource] = []
    boundary_export_envelopes: dict[str, tuple[float, ...]] = {}
    boundary_export_prices: dict[str, tuple[float, ...]] = {}

    for asset in state.assets:
        if asset.capacity_mw <= 0:
            continue
        technology = asset.technology
        if technology in {"solar", "onshore", "offshore"}:
            asset_extensions = dict(asset.extensions)
            marginal = 0.0
            if doctoral_alignment:
                raw, binding = _doctoral_parameter_row(asset, fleet, "generators")
                asset_extensions.update(binding)
                marginal = _doctoral_marginal_cost(raw, technology, binding["doctoral_parameter_source_id"])
            availability, weather_evidence = (
                site_profiles[asset.asset_id] if doctoral_weather else (
                    tuple(float(value) for value in profiles[technology]),
                    {"method_id": "value.declared-technology-csv/v1"},
                )
            )
            resources.append(DispatchResource(
                asset.asset_id,
                technology,
                "vre",
                asset.capacity_mw,
                marginal,
                availability,
                region=asset.region,
                extensions={
                    **asset_extensions,
                    "weather_profile": weather_evidence,
                    "base_asset_id": asset.asset_id,
                    "agent_id": str(
                        asset_extensions.get("investment_owner_id")
                        or asset_extensions.get("source_agent_id")
                        or asset.asset_id
                    ),
                },
            ))
            continue
        storage_key = {
            "pumped_hydro": "pumped_hydro",
            "1c_battery": "1c",
            "0.5c_battery": "0.5c",
            "0.25c_battery": "0.25c",
            "hydrogen_battery": "hydrogen",
        }.get(technology)
        if storage_key:
            continue
        parameter_binding = {}
        if doctoral_alignment:
            raw, parameter_binding = _doctoral_parameter_row(asset, fleet, "generators")
            template_id = parameter_binding["doctoral_parameter_source_id"]
        else:
            raw = dict(fleet.get("generators", {}).get(asset.asset_id) or {})
            template_id = asset.asset_id
        if not raw and not doctoral_alignment:
            template_id = {
                "gas": "CCGT",
                "CCGT": "CCGT",
                "OCGT": "OCGT",
                "bio_and_waste": "bio_and_waste",
                "Hydro_natural_flow": "Hydro_natural_flow",
                "Nuclear": "Nuclear",
            }.get(technology, "")
            raw = dict(fleet.get("generators", {}).get(template_id) or {})
        if not raw:
            raise ValueError(
                f"Active non-storage asset {asset.asset_id} ({technology}) has no dispatch template"
            )
        marginal = float(raw.get("fuel_cost", 0.0) or 0.0) + float(
            raw.get("carbon_price", 0.0) or 0.0
        ) + float(raw.get("gen_cost", 0.0) or 0.0)
        if doctoral_alignment:
            marginal = _doctoral_marginal_cost(raw, technology, template_id)
        resource_type = "hydro" if technology == "Hydro_natural_flow" else "thermal"
        resources.append(DispatchResource(
            asset.asset_id,
            technology,
            resource_type,
            asset.capacity_mw,
            marginal,
            (1.0,),
            region=asset.region,
            extensions={
                **dict(asset.extensions),
                **parameter_binding,
                "base_asset_id": asset.asset_id,
                "agent_id": str(
                    asset.extensions.get("investment_owner_id")
                    or asset.extensions.get("source_agent_id")
                    or asset.asset_id
                ),
                "cost_source": ("frozen doctoral constructor components including unit_time_cost"
                                if doctoral_alignment else "fleet.generators fuel_cost + carbon_price + gen_cost"),
                "dispatch_template_asset_id": template_id,
                "source_project_id": asset.extensions.get("source_project_id"),
                "hydrology": "constant availability compatibility assumption" if resource_type == "hydro" else None,
            },
        ))

    storage_catalogue = compatibility_catalogue()
    catalogue = dict(storage_catalogue.technologies)
    for asset in state.assets:
        storage_key = {
            "pumped_hydro": "pumped_hydro",
            "1c_battery": "1c",
            "0.5c_battery": "0.5c",
            "0.25c_battery": "0.25c",
            "hydrogen_battery": "hydrogen",
        }.get(asset.technology)
        if storage_key is None or asset.capacity_mw <= 0:
            continue
        specification = catalogue[storage_key]
        parameter_binding = {}
        if doctoral_alignment:
            _, parameter_binding = _doctoral_parameter_row(asset, fleet, "batteries")
        energy = (
            float(asset.energy_capacity_mwh)
            if asset.energy_capacity_mwh is not None
            else asset.capacity_mw * specification.duration_hours
        )
        variable_degradation = 0.0
        if specification.has_battery_cycle_depreciation and specification.maximum_cycles > 0:
            project_capex = specification.capex_value * asset.capacity_mw
            variable_degradation = project_capex / (
                specification.maximum_cycles * max(energy, 1e-12)
            )
        storage_assets.append(StorageDispatchResource(
            asset.asset_id,
            storage_key,
            asset.capacity_mw,
            asset.capacity_mw,
            energy,
            specification.charge_efficiency,
            specification.discharge_efficiency,
            0.0 if doctoral_alignment else energy * 0.5,
            variable_degradation,
            extensions={
                **dict(asset.extensions),
                **parameter_binding,
                "base_asset_id": asset.asset_id,
                "agent_id": str(
                    asset.extensions.get("investment_owner_id")
                    or asset.extensions.get("source_agent_id")
                    or asset.asset_id
                ),
                "catalogue_id": storage_catalogue.catalogue_id,
                "battery_cycle_depreciation": specification.has_battery_cycle_depreciation,
            },
        ))

    for country in INTERCONNECTORS:
        # Line identity (P6-03), declared column (P6-01), EUR->GBP (P6-02):
        # data_method.read_boundary; the flow stays signed, the price raw.
        raw_availability = boundary.countries[country].flow_mw * period_hours
        prices = boundary.countries[country].price_gbp_per_mwh
        export_energy = np.maximum(-raw_availability, 0.0)
        if float(np.max(export_energy, initial=0.0)) > 0:
            export_asset_id = f"export:{country}"
            boundary_export_envelopes[export_asset_id] = tuple(
                float(value) for value in export_energy
            )
            boundary_export_prices[export_asset_id] = tuple(
                float(value if doctoral_alignment else max(value, 0.0)) for value in prices
            )
        import_energy = np.maximum(raw_availability, 0.0)
        maximum = float(np.max(import_energy, initial=0.0))
        if maximum <= 0:
            continue
        resources.append(DispatchResource(
            f"import:{country}",
            "interconnector_import",
            "import",
            maximum / period_hours,
            float(np.mean(prices)),
            tuple(float(value / maximum) for value in import_energy),
            tuple(float(value if doctoral_alignment else max(value, 0.0)) for value in prices),
            extensions={
                "system_boundary": "signed_external_offer_envelope",
                "country": country,
                "agent_id": f"interconnector:{country}",
            },
        ))

    capacity_by_technology: dict[str, float] = {key: 0.0 for key in profiles}
    for asset in state.assets:
        if asset.technology in capacity_by_technology:
            capacity_by_technology[asset.technology] += asset.capacity_mw
    headroom = {}
    for technology, availability in profiles.items():
        peak = float(np.max(availability, initial=0.0))
        headroom[technology] = max(
            0.0,
            (
                float(np.max(demand, initial=0.0))
                / period_hours
                / max(peak, 1e-12)
            )
            - capacity_by_technology[technology],
        )
    return ChronologicalPSMData(
        tuple(f"{state.year}:{index}" for index in range(periods)),
        tuple(float(value) for value in demand),
        tuple(resources),
        tuple(storage_assets),
        float(voll_gbp_per_mwh),
        terminal_soc_rule=terminal_soc_rule,
        terminal_soc_mwh_by_asset={
            storage.asset_id: storage.initial_soc_mwh for storage in storage_assets
        },
        extensions={
            "adapter_schema": CHRONOLOGY_SCHEMA_VERSION,
            **({"doctoral_alignment_profile": DOCTORAL_ALIGNMENT_PROFILE,
                "doctoral_opening_inventory": "empty_batches_or_explicit_engine_checkpoint"} if doctoral_alignment else {}),
            "dispatch_weather_method": (DOCTORAL_WEATHER_METHOD if doctoral_weather
                                        else "value.declared-technology-csv/v1"),
            "vre_expansion_headroom_mw_by_technology": headroom,
            "source_pack_id": manifest.get("id"),
            "data_method": {
                **chronology_extension(data_policy, series, boundary),
                "boundary": boundary.evidence(),
            },
            "boundary_raw_series": {
                "flow_mw_by_country": {
                    country: tuple(float(value) for value in entry.flow_mw)
                    for country, entry in sorted(boundary.countries.items())
                },
                "price_gbp_per_mwh_by_country": {
                    country: tuple(float(value) for value in entry.price_gbp_per_mwh)
                    for country, entry in sorted(boundary.countries.items())
                },
                "flow_sign": "source convention (positive = import to GB unless the binding declares flow_sign)",
                "boundary_series_sha256": boundary.series_sha256(),
            },
            "forecast_demand_mwh": tuple(float(value) for value in forecast_demand),
            "boundary_export_envelope_mwh_by_asset": boundary_export_envelopes,
            "boundary_export_price_gbp_per_mwh_by_asset": boundary_export_prices,
            "source_profile_compatibility_adjustment": {
                "definition_id": "value.source-power-to-energy/v1",
                "source_row_unit": "MW",
                "contract_unit": "MWh/period",
                "multiplier": period_hours,
                "roles": [
                    "demand.forecast",
                    "demand.real",
                    *[
                        availability_role
                        for availability_role, _price_role in INTERCONNECTORS.values()
                    ],
                ],
            },
        },
    )
