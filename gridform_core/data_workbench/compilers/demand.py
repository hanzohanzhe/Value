"""Measured-energy regional demand weights with exact national reconciliation."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Mapping, Sequence

from shapely.geometry import Point, shape


_POSTCODE_PUNCTUATION = re.compile(r"[^A-Z0-9]")
_GB_COUNTRIES = {"england", "scotland", "wales"}


def normalize_postcode(value: object) -> str:
    return _POSTCODE_PUNCTUATION.sub("", str(value or "").strip().upper())


def _energy(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Postcode consumption is not numeric") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError("Postcode consumption cannot be negative or non-finite")
    return result


def compile_base_demand_weights(
    domestic_rows: Sequence[Mapping[str, object]],
    non_domestic_rows: Sequence[Mapping[str, object]],
    postcode_directory_rows: Sequence[Mapping[str, object]],
    zone_geojson: Mapping[str, object],
) -> dict[str, object]:
    if zone_geojson.get("type") != "FeatureCollection":
        raise ValueError("Demand zones must be a GeoJSON FeatureCollection")
    zones: list[tuple[str, object]] = []
    for raw in zone_geojson.get("features", []):  # type: ignore[assignment]
        if not isinstance(raw, Mapping) or not isinstance(raw.get("properties"), Mapping):
            raise ValueError("Demand zone feature is invalid")
        zone_id = str(raw["properties"].get("zone_id") or "")  # type: ignore[index]
        if not zone_id or any(existing == zone_id for existing, _ in zones):
            raise ValueError("Demand zone IDs must be unique and non-blank")
        zones.append((zone_id, shape(raw.get("geometry"))))
    zones.sort(key=lambda row: row[0])

    directory: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in postcode_directory_rows:
        key = normalize_postcode(row.get("postcode"))
        if key:
            directory[key].append(row)

    combined = [("domestic", row) for row in domestic_rows] + [
        ("non_domestic", row) for row in non_domestic_rows
    ]
    counts = Counter(normalize_postcode(row.get("postcode")) for _, row in combined)
    duplicate_postcodes = sorted(key for key, count in counts.items() if key and count > 1)
    energy_by_zone = {zone_id: 0.0 for zone_id, _ in zones}
    source_totals = {
        "domestic_mwh": sum(_energy(row.get("consumption_mwh")) for row in domestic_rows),
        "non_domestic_mwh": sum(_energy(row.get("consumption_mwh")) for row in non_domestic_rows),
    }
    unmatched: set[str] = set()
    terminated: set[str] = set()
    non_gb: set[str] = set()
    boundary_assignments: list[dict[str, object]] = []
    unmatched_mwh = 0.0
    excluded_mwh = 0.0
    included_mwh = 0.0
    for _, row in combined:
        key = normalize_postcode(row.get("postcode"))
        value = _energy(row.get("consumption_mwh"))
        candidates = directory.get(key, [])
        if not candidates:
            unmatched.add(key)
            unmatched_mwh += value
            continue
        directory_row = sorted(
            candidates,
            key=lambda item: (
                str(item.get("status") or ""),
                str(item.get("longitude") or ""),
                str(item.get("latitude") or ""),
            ),
        )[0]
        if str(directory_row.get("status") or "").strip().casefold() not in {
            "live",
            "active",
            "open",
        }:
            terminated.add(key)
            excluded_mwh += value
            continue
        if str(directory_row.get("country") or "").strip().casefold() not in _GB_COUNTRIES:
            non_gb.add(key)
            excluded_mwh += value
            continue
        try:
            point = Point(
                float(directory_row.get("longitude")),
                float(directory_row.get("latitude")),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Postcode {key} has invalid coordinates") from exc
        containing = sorted(zone_id for zone_id, polygon in zones if polygon.covers(point))
        if not containing:
            unmatched.add(key)
            unmatched_mwh += value
            continue
        selected = containing[0]
        if len(containing) > 1:
            boundary_assignments.append(
                {
                    "postcode": key,
                    "candidate_zone_ids": containing,
                    "selected_zone_id": selected,
                }
            )
        energy_by_zone[selected] += value
        included_mwh += value

    if included_mwh <= 0:
        raise ValueError("No measured GB postcode energy could be assigned to demand zones")
    weights = {zone_id: value / included_mwh for zone_id, value in energy_by_zone.items()}
    return {
        "schema_version": "value.measured-zone-demand-weights/v1",
        "energy_mwh_by_zone": dict(sorted(energy_by_zone.items())),
        "weights": dict(sorted(weights.items())),
        "method_by_zone": {
            zone_id: "measured" if value > 0 else "static_share_fallback"
            for zone_id, value in sorted(energy_by_zone.items())
        },
        "coverage": {
            "unmatched_postcodes": sorted(unmatched),
            "terminated_postcodes": sorted(terminated),
            "non_gb_postcodes": sorted(non_gb),
            "duplicate_postcodes": duplicate_postcodes,
            "boundary_assignments": sorted(boundary_assignments, key=lambda row: str(row["postcode"])),
            "directory_duplicate_postcodes": sorted(
                key for key, values in directory.items() if len(values) > 1
            ),
        },
        "reconciliation": {
            **source_totals,
            "source_total_mwh": source_totals["domestic_mwh"] + source_totals["non_domestic_mwh"],
            "included_mwh": included_mwh,
            "unmatched_mwh": unmatched_mwh,
            "excluded_mwh": excluded_mwh,
        },
    }


def evolve_demand_weights(
    base_weights: Mapping[str, float],
    fes_rows: Sequence[Mapping[str, object]],
    *,
    years: Sequence[int],
) -> dict[str, object]:
    if not years:
        raise ValueError("Demand evolution requires at least one year")
    zones = sorted(base_weights)
    if any(not math.isfinite(float(base_weights[zone])) or float(base_weights[zone]) < 0 for zone in zones):
        raise ValueError("Base demand weights must be finite and non-negative")
    factors: dict[tuple[int, str], float] = {}
    for row in fes_rows:
        key = (int(row.get("year") or 0), str(row.get("zone_id") or ""))
        factor = float(row.get("relative_factor"))
        if key in factors or key[1] not in base_weights or not math.isfinite(factor) or factor < 0:
            raise ValueError("FES demand evolution row is duplicate, unknown or invalid")
        factors[key] = factor

    base_year = min(int(year) for year in years)
    weights_by_year: dict[str, dict[str, float]] = {}
    methods: dict[str, dict[str, str]] = {}
    waivers: set[str] = set()
    for raw_year in sorted(set(int(year) for year in years)):
        values: dict[str, float] = {}
        year_methods: dict[str, str] = {}
        for zone in zones:
            if raw_year == base_year:
                values[zone] = float(base_weights[zone])
                year_methods[zone] = "measured" if values[zone] > 0 else "static_share_fallback"
            elif (raw_year, zone) in factors:
                values[zone] = float(base_weights[zone]) * factors[(raw_year, zone)]
                year_methods[zone] = "calibrated"
            else:
                values[zone] = float(base_weights[zone])
                year_methods[zone] = "static_share_fallback"
            if year_methods[zone] == "static_share_fallback":
                waivers.add(f"demand.{zone}.static_share_fallback")
        total = sum(values.values())
        if total <= 0:
            raise ValueError(f"Demand weights for {raw_year} have no positive total")
        weights_by_year[str(raw_year)] = {
            zone: values[zone] / total for zone in zones
        }
        methods[str(raw_year)] = year_methods
    return {
        "schema_version": "value.evolved-zone-demand-weights/v1",
        "weights_by_year": weights_by_year,
        "method_by_zone_year": methods,
        "requested_waivers": sorted(waivers),
    }


def spatialize_national_demand(
    national_rows: Sequence[Mapping[str, object]],
    weights: Mapping[str, float],
) -> dict[str, object]:
    zones = sorted(weights)
    total_weight = sum(float(weights[zone]) for zone in zones)
    if not zones or abs(total_weight - 1.0) > 1e-10 or any(float(weights[zone]) < 0 for zone in zones):
        raise ValueError("Regional demand weights must be non-negative and sum to one")
    period_ids: list[str] = []
    national_values: list[float] = []
    zonal = {zone: [] for zone in zones}
    residual_audit: list[dict[str, object]] = []
    largest_zone = min(
        (zone for zone in zones if float(weights[zone]) == max(float(item) for item in weights.values())),
        default=zones[0],
    )
    for row in national_rows:
        period_id = str(row.get("period_id") or "")
        national = float(row.get("national_demand_mwh"))
        if not period_id or period_id in period_ids or not math.isfinite(national) or national < 0:
            raise ValueError("National demand row has an invalid period or value")
        values = {zone: national * float(weights[zone]) for zone in zones}
        pre = national - sum(values.values())
        values[largest_zone] += pre
        post = national - sum(values.values())
        for zone in zones:
            zonal[zone].append(values[zone])
        period_ids.append(period_id)
        national_values.append(national)
        residual_audit.append(
            {
                "period_id": period_id,
                "adjusted_zone_id": largest_zone,
                "pre_residual_mwh": pre,
                "post_residual_mwh": post,
            }
        )
    return {
        "schema_version": "value.zonal-demand/v1",
        "period_ids": period_ids,
        "national_demand_mwh": national_values,
        "demand_mwh_by_zone": zonal,
        "residual_audit": residual_audit,
        "weight_method": "measured_base_with_optional_fes_relative_evolution",
    }
