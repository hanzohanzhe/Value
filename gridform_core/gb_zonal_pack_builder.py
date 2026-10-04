"""Deterministic, offline construction of an unsigned VALUE GB zonal pack.

The builder consumes only source objects pinned by a local inventory.  It does
not download data, assign a final network-pack identity, or install a pack.
Those three boundaries are deliberate: Prompt 98 requires the scientific owner
to review the candidate before it can become an immutable benchmark.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .data_bundle import build_data_bundle, install_data_bundle
from .weather_spatialization import ZonalAvailabilityBundle
from .zonal_contracts import (
    BoundaryRatingProfile,
    CutsetMember,
    ETYSBoundary,
    InterconnectorLanding,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZONAL_ROLES,
    ZonalAssetMapping,
    ZonalDemand,
    ZonalNetworkPack,
)


INVENTORY_SCHEMA = "value.gb-zonal-source-inventory/v1"
CANDIDATE_SCHEMA = "value.gb-zonal-network-candidate/v1"
BUILDER_VERSION = "prompt98-builder/1.0.0"
COMPATIBILITY_FACADE_TARGET = (
    "gridform_core.data_workbench.compilers.network_candidate.build_prompt98_candidate"
)
REQUIRED_SOURCE_ROLES = (
    "dso_areas",
    "etys_boundaries",
    "neso_national_demand",
    "regional_demand_evidence",
    "model_fleet",
    "repd",
    "interconnector_landings",
    "era5_representative_profiles",
    "era5_aggregated_profiles",
)
ACCEPTED_RIGHTS = {"redistributable", "local_use_only", "pointer_only"}
ACTIVE_STATUSES = {"active", "operating", "operational", "commissioned"}
FALLBACK_ZONE = "ENGLAND_FALLBACK"


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_source_path(inventory_path: Path, relative: str) -> Path:
    candidate = (inventory_path.parent / relative).resolve()
    try:
        candidate.relative_to(inventory_path.parent.resolve())
    except ValueError as exc:
        raise ValueError(f"Inventory local_path escapes its pinned source root: {relative}") from exc
    return candidate


def _load_inventory(inventory_path: Path) -> dict[str, object]:
    payload = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GB zonal source inventory must be a JSON object")
    return payload


def validate_source_inventory(inventory_path: Path) -> dict[str, Path]:
    """Validate source identity, access and rights and return pinned paths by role."""

    inventory_path = Path(inventory_path).resolve()
    payload = _load_inventory(inventory_path)
    if payload.get("schema_version") != INVENTORY_SCHEMA:
        raise ValueError("GB zonal source inventory uses an incompatible schema")
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise ValueError("GB zonal source inventory has no object list")
    by_role: dict[str, Mapping[str, object]] = {}
    for raw in objects:
        if not isinstance(raw, Mapping):
            raise ValueError("GB zonal source inventory contains a non-object row")
        role = str(raw.get("role") or "")
        if role in by_role:
            raise ValueError(f"GB zonal source inventory repeats role {role}")
        by_role[role] = raw
    missing = sorted(set(REQUIRED_SOURCE_ROLES).difference(by_role))
    if missing:
        raise ValueError("GB zonal source inventory is missing required role(s): " + ", ".join(missing))

    resolved: dict[str, Path] = {}
    for role in REQUIRED_SOURCE_ROLES:
        row = by_role[role]
        required_metadata = (
            "authoritative_url", "publisher", "title", "publication_date",
            "source_version", "licence", "licence_url", "transformation_step",
        )
        absent = [key for key in required_metadata if not str(row.get(key) or "").strip()]
        if absent:
            raise ValueError(f"Source {role} lacks provenance field(s): {', '.join(absent)}")
        decision = str(row.get("redistribution_decision") or "")
        if decision not in ACCEPTED_RIGHTS:
            raise ValueError(f"Source {role} has unclear rights or redistribution decision")
        if row.get("access_result") != "present":
            raise ValueError(f"Source {role} is not locally present")
        local_path = str(row.get("local_path") or "")
        if not local_path or Path(local_path).is_absolute():
            raise ValueError(f"Source {role} must use an inventory-relative local_path")
        path = _safe_source_path(inventory_path, local_path)
        if not path.is_file():
            raise ValueError(f"Source {role} pinned object is missing: {local_path}")
        expected = str(row.get("sha256") or "").lower()
        if len(expected) != 64 or sha256_file(path) != expected:
            raise ValueError(f"Source {role} SHA-256 identity does not match")
        resolved[role] = path
    return resolved


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _float(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload), encoding="utf-8", newline="")


def _source_metadata(inventory_path: Path) -> list[dict[str, object]]:
    payload = _load_inventory(inventory_path)
    result: list[dict[str, object]] = []
    for raw in sorted(payload["objects"], key=lambda item: item["role"]):  # type: ignore[index]
        row = dict(raw)
        row.pop("local_path", None)
        row["pinned_object"] = f"source-object://{row['role']}/{row.get('sha256')}"
        result.append(row)
    return result


def _polygon_parts(geometry: object) -> list[object]:
    if not isinstance(geometry, Mapping):
        return []
    if geometry.get("type") == "Polygon":
        coordinates = geometry.get("coordinates")
        return [coordinates] if isinstance(coordinates, list) else []
    if geometry.get("type") == "MultiPolygon":
        coordinates = geometry.get("coordinates")
        return list(coordinates) if isinstance(coordinates, list) else []
    return []


def _zones(
    geojson: Mapping[str, object],
) -> tuple[list[NetworkZone], dict[str, object], dict[str, str]]:
    if geojson.get("type") != "FeatureCollection" or not isinstance(geojson.get("features"), list):
        raise ValueError("DSO areas source must be a GeoJSON FeatureCollection")
    features: dict[str, dict[str, object]] = {}
    aliases: dict[str, str] = {}
    for feature in geojson["features"]:  # type: ignore[index]
        if not isinstance(feature, Mapping) or not isinstance(feature.get("properties"), Mapping):
            raise ValueError("DSO areas contain an invalid feature")
        props = feature["properties"]
        zone_id = str(props.get("zone_id") or "")
        if not zone_id or zone_id in features:
            raise ValueError("DSO areas contain a blank or duplicate zone_id")
        features[zone_id] = dict(feature)
        if props.get("merge_into"):
            aliases[zone_id] = str(props["merge_into"])
    for source, target in aliases.items():
        if source == target or target not in features or target in aliases:
            raise ValueError(f"DSO sliver {source} has an invalid merge target {target}")
        target_feature = features[target]
        merged_parts = _polygon_parts(target_feature.get("geometry"))
        merged_parts.extend(_polygon_parts(features[source].get("geometry")))
        if merged_parts:
            target_feature["geometry"] = {
                "type": "MultiPolygon",
                "coordinates": merged_parts,
            }

    zones: list[NetworkZone] = []
    retained_features: list[dict[str, object]] = []
    for zone_id, feature in features.items():
        props = feature["properties"]  # type: ignore[assignment]
        if zone_id in aliases:
            continue
        zone = NetworkZone(
            zone_id=zone_id,
            display_name=str(props.get("display_name") or ""),
            dso_owner=str(props.get("dso_owner") or ""),
            nation=str(props.get("nation") or ""),
            is_unconstrained_fallback=bool(props.get("is_unconstrained_fallback", False)),
            geometry_feature_id=(str(props["geometry_feature_id"]) if props.get("geometry_feature_id") else None),
            island_reason=(str(props["island_reason"]) if props.get("island_reason") else None),
        )
        zone.validate()
        zones.append(zone)
        retained_features.append(feature)
    if not any(zone.zone_id == FALLBACK_ZONE and zone.is_unconstrained_fallback for zone in zones):
        raise ValueError("DSO area layer must declare the unconstrained ENGLAND_FALLBACK zone")
    return sorted(zones, key=lambda item: item.zone_id), {
        "type": "FeatureCollection", "features": retained_features,
    }, dict(sorted(aliases.items()))


def _network(
    payload: Mapping[str, object], zones: Sequence[NetworkZone], period_ids: Sequence[str],
    zone_aliases: Mapping[str, str],
) -> tuple[
    list[TransportCorridor], list[ETYSBoundary], list[BoundaryRatingProfile],
    list[str], dict[str, str],
]:
    zone_ids = {zone.zone_id for zone in zones}
    corridors: list[TransportCorridor] = []
    for raw_corridor in payload.get("corridors", []):  # type: ignore[assignment]
        row = dict(raw_corridor)
        row["from_zone_id"] = zone_aliases.get(str(row.get("from_zone_id")), str(row.get("from_zone_id")))
        row["to_zone_id"] = zone_aliases.get(str(row.get("to_zone_id")), str(row.get("to_zone_id")))
        if row["from_zone_id"] == row["to_zone_id"]:
            continue
        corridors.append(TransportCorridor.from_dict(row))
    for corridor in corridors:
        corridor.validate()
        if corridor.from_zone_id not in zone_ids or corridor.to_zone_id not in zone_ids:
            raise ValueError(f"Corridor {corridor.corridor_id} has an unknown zone")
    unconstrained = {
        zone_aliases.get(str(item), str(item))
        for item in payload.get("unconstrained_zone_ids", [])  # type: ignore[arg-type]
    }
    constrained_zones = zone_ids.difference(unconstrained)
    boundaries: list[ETYSBoundary] = []
    assumed: list[str] = []
    source_directions: dict[str, str] = {}
    for raw in payload.get("boundaries", []):  # type: ignore[assignment]
        if not isinstance(raw, Mapping):
            raise ValueError("ETYS boundary row must be an object")
        source = {zone_aliases.get(str(item), str(item)) for item in raw.get("source_partition_zone_ids", [])}  # type: ignore[arg-type]
        sink = {zone_aliases.get(str(item), str(item)) for item in raw.get("sink_partition_zone_ids", [])}  # type: ignore[arg-type]
        if source & sink or source | sink != constrained_zones:
            raise ValueError(f"Boundary {raw.get('boundary_id')} does not define a valid zone partition")
        members: list[CutsetMember] = []
        for corridor in corridors:
            if corridor.from_zone_id in unconstrained or corridor.to_zone_id in unconstrained:
                continue
            if corridor.from_zone_id in source and corridor.to_zone_id in sink:
                members.append(CutsetMember(corridor.corridor_id, 1))
            elif corridor.from_zone_id in sink and corridor.to_zone_id in source:
                members.append(CutsetMember(corridor.corridor_id, -1))
        actual = {member.corridor_id for member in members}
        expected = {str(item) for item in raw.get("expected_corridor_ids", actual)}  # type: ignore[arg-type]
        if actual != expected or not actual:
            raise ValueError(
                f"Boundary {raw.get('boundary_id')} cut-set does not match its declared zone separation"
            )
        forward = _float(raw.get("forward_limit_mw"), "forward boundary limit")
        reverse_raw = raw.get("reverse_limit_mw")
        if reverse_raw in (None, ""):
            reverse = forward
            reverse_method = "assumed_symmetric_from_forward"
            assumed.append(str(raw.get("boundary_id")))
        else:
            reverse = _float(reverse_raw, "reverse boundary limit")
            reverse_method = str(raw.get("reverse_limit_method") or "independent_source")
        boundary = ETYSBoundary(
            boundary_id=str(raw.get("boundary_id") or ""),
            display_name=str(raw.get("display_name") or ""),
            members=tuple(members),
            forward_limit_mw=forward,
            reverse_limit_mw=reverse,
            rating_profile_id=(str(raw["rating_profile_id"]) if raw.get("rating_profile_id") else None),
            reverse_limit_method=reverse_method,
        )
        boundary.validate()
        boundaries.append(boundary)
        source_direction = str(raw.get("source_direction") or "")
        if not source_direction:
            raise ValueError(f"Boundary {boundary.boundary_id} lacks its sourced direction label")
        source_directions[boundary.boundary_id] = source_direction
    profiles = [BoundaryRatingProfile.from_dict(row) for row in payload.get("rating_profiles", [])]  # type: ignore[arg-type]
    for profile in profiles:
        profile.validate(period_ids)
    return corridors, boundaries, profiles, sorted(assumed), dict(sorted(source_directions.items()))


def _demand(
    national_rows: Sequence[Mapping[str, str]], regional_rows: Sequence[Mapping[str, str]],
    zones: Sequence[NetworkZone], zone_aliases: Mapping[str, str],
) -> tuple[ZonalDemand, dict[str, str], float]:
    period_ids = [str(row.get("period_id") or "") for row in national_rows]
    if not period_ids or any(not item for item in period_ids) or len(period_ids) != len(set(period_ids)):
        raise ValueError("NESO demand source has missing or duplicate period IDs")
    national = [_float(row.get("national_demand_mwh"), "national demand") for row in national_rows]
    zone_ids = [zone.zone_id for zone in zones]
    by_period: dict[str, dict[str, tuple[float, str]]] = defaultdict(dict)
    static: dict[str, tuple[float, str]] = {}
    for row in regional_rows:
        period = str(row.get("period_id") or "")
        raw_zone = str(row.get("zone_id") or "")
        zone = zone_aliases.get(raw_zone, raw_zone)
        if zone not in zone_ids:
            raise ValueError(f"Regional demand evidence names unknown zone {zone}")
        item = (_float(row.get("weight"), "regional demand weight"), str(row.get("method") or ""))
        target = static if period == "*" else by_period[period]
        if zone in target:
            previous_weight, previous_method = target[zone]
            target[zone] = (
                previous_weight + item[0],
                previous_method if previous_method == item[1] else "merged_dso_evidence",
            )
        else:
            target[zone] = item
    demand_by_zone = {zone: [] for zone in zone_ids}
    method_by_zone: dict[str, str] = {}
    max_residual = 0.0
    for index, period in enumerate(period_ids):
        evidence = by_period.get(period) or static
        if set(evidence) != set(zone_ids):
            raise ValueError(f"Regional demand evidence does not cover every zone for {period}")
        weights = {zone: evidence[zone][0] for zone in zone_ids}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            raise ValueError(f"Regional demand weights sum to zero for {period}")
        allocated = 0.0
        for zone in zone_ids[:-1]:
            value = national[index] * weights[zone] / total_weight
            demand_by_zone[zone].append(value)
            allocated += value
        demand_by_zone[zone_ids[-1]].append(national[index] - allocated)
        for zone in zone_ids:
            method_by_zone.setdefault(zone, evidence[zone][1])
        residual = sum(demand_by_zone[zone][index] for zone in zone_ids) - national[index]
        max_residual = max(max_residual, abs(residual))
    result = ZonalDemand(tuple(period_ids), demand_by_zone, tuple(national), 1e-8)
    result.validate(set(zone_ids))
    return result, method_by_zone, max_residual


def _fleet(
    rows: Sequence[Mapping[str, str]], landing_rows: Sequence[Mapping[str, str]],
    zones: Sequence[NetworkZone], zone_aliases: Mapping[str, str],
) -> tuple[list[ZonalAssetMapping], SpatialAudit, list[InterconnectorLanding], dict[str, object]]:
    zone_ids = {zone.zone_id for zone in zones}
    mappings: list[ZonalAssetMapping] = []
    source_capacity: dict[str, float] = defaultdict(float)
    mapped_capacity: dict[str, float] = defaultdict(float)
    active_ids: list[str] = []
    fallback_ids: list[str] = []
    excluded_ni: list[str] = []
    seen_asset_capacity: dict[str, float] = {}
    status_source_seen: set[tuple[str, str, str]] = set()
    mapping_audit: list[dict[str, object]] = []
    capacity_by_status: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"source_mw": 0.0, "mapped_mw": 0.0, "fallback_mw": 0.0}
    )
    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        technology = str(row.get("technology") or "")
        capacity = _float(row.get("capacity_mw"), f"capacity for {row.get('asset_id')}")
        source_key = (str(row.get("asset_id") or ""), technology, status)
        if source_key not in status_source_seen:
            capacity_by_status[(technology, status)]["source_mw"] += capacity
            status_source_seen.add(source_key)
        if status not in ACTIVE_STATUSES:
            continue
        asset_id = str(row.get("asset_id") or "")
        if str(row.get("nation") or "").strip().lower() in {"northern ireland", "ni"}:
            excluded_ni.append(asset_id)
            continue
        share = _float(row.get("share") or 1.0, f"zone share for {asset_id}")
        raw_zone_id = str(row.get("zone_id") or FALLBACK_ZONE)
        zone_id = zone_aliases.get(raw_zone_id, raw_zone_id)
        method = str(row.get("mapping_method") or "unlocated_england_fallback")
        if zone_id not in zone_ids:
            zone_id, method = FALLBACK_ZONE, "unlocated_england_fallback"
        if asset_id not in seen_asset_capacity:
            seen_asset_capacity[asset_id] = capacity
            source_capacity[technology] += capacity
            active_ids.append(asset_id)
        elif abs(seen_asset_capacity[asset_id] - capacity) > 1e-9:
            raise ValueError(f"Asset {asset_id} repeats with inconsistent capacity")
        mapping = ZonalAssetMapping(
            asset_id, zone_id, str(row.get("asset_class") or "generator"), technology,
            share, method,
        )
        mapping.validate()
        mappings.append(mapping)
        mapped_capacity[technology] += capacity * share
        capacity_by_status[(technology, status)]["mapped_mw"] += capacity * share
        if zone_id == FALLBACK_ZONE:
            fallback_ids.append(asset_id)
            capacity_by_status[(technology, status)]["fallback_mw"] += capacity * share
        mapping_audit.append({
            "asset_id": asset_id, "technology": technology, "capacity_mw": capacity,
            "status": status, "region": str(row.get("region") or "not_declared"),
            "zone_id": zone_id, "share": share, "mapping_method": method,
            "latitude": (_float(row.get("latitude"), f"latitude for {asset_id}") if row.get("latitude") not in (None, "") else None),
            "longitude": (_float(row.get("longitude"), f"longitude for {asset_id}") if row.get("longitude") not in (None, "") else None),
        })

    landings: list[InterconnectorLanding] = []
    for row in landing_rows:
        asset_id = str(row.get("asset_id") or "")
        raw_zone_id = str(row.get("zone_id") or "")
        zone_id = zone_aliases.get(raw_zone_id, raw_zone_id)
        if zone_id not in zone_ids:
            raise ValueError(f"Interconnector {asset_id} has no declared GB landing zone")
        capacity = _float(row.get("capacity_mw"), f"capacity for {asset_id}")
        technology = str(row.get("technology") or "interconnector")
        if asset_id not in seen_asset_capacity:
            capacity_by_status[(technology, "operating")]["source_mw"] += capacity
            active_ids.append(asset_id)
            seen_asset_capacity[asset_id] = capacity
            source_capacity[technology] += capacity
            mapped_capacity[technology] += capacity
            mappings.append(ZonalAssetMapping(
                asset_id, zone_id, "boundary_interconnector", technology, 1.0,
                "declared_interconnector_landing",
            ))
            capacity_by_status[(technology, "operating")]["mapped_mw"] += capacity
        landing = InterconnectorLanding(
            str(row.get("interconnector_id") or ""), asset_id, zone_id,
            str(row.get("envelope_semantics") or ""),
        )
        landing.validate()
        landings.append(landing)
    for zone in zones:
        mappings.append(ZonalAssetMapping(
            f"demand:{zone.zone_id}", zone.zone_id, "demand", "demand", 1.0,
            "zonal_demand_contract",
        ))
    audit = SpatialAudit(
        tuple(sorted(active_ids)), dict(sorted(source_capacity.items())),
        dict(sorted(mapped_capacity.items())), 1e-8,
        tuple(sorted(set(fallback_ids))), tuple(sorted(set(excluded_ni))), {},
    )
    audit.validate()
    return mappings, audit, landings, {
        "asset_mappings": mapping_audit,
        "capacity_mw_by_technology_and_status": [
            {"technology": technology, "status": status, **values}
            for (technology, status), values in sorted(capacity_by_status.items())
        ],
        "fallback_asset_count": len(set(fallback_ids)),
        "excluded_northern_ireland_asset_count": len(set(excluded_ni)),
    }


def _repd_comparison(
    repd_rows: Sequence[Mapping[str, str]], source_capacity: Mapping[str, float]
) -> list[dict[str, object]]:
    def comparison_technology(technology: str) -> str:
        # VALUE separates batteries by discharge duration/rate. REPD reports
        # those same non-pumped assets under one Battery category, so the
        # review ledger must compare like with like without changing the
        # scientific fleet representation used by the model.
        return "battery" if technology in {"1c", "0.5c", "0.25c"} else technology

    repd: dict[str, float] = defaultdict(float)
    for row in repd_rows:
        if str(row.get("status") or "").strip().lower() != "operational":
            continue
        technology = comparison_technology(str(row.get("technology") or ""))
        repd[technology] += _float(row.get("capacity_mw"), "REPD capacity")
    model_capacity: dict[str, float] = defaultdict(float)
    for technology, capacity in source_capacity.items():
        model_capacity[comparison_technology(str(technology))] += float(capacity)
    result: list[dict[str, object]] = []
    for technology in sorted(set(repd) | set(model_capacity)):
        model = float(model_capacity.get(technology, 0.0))
        source = float(repd.get(technology, 0.0))
        difference = model - source
        result.append({
            "technology": technology,
            "model_active_capacity_mw": model,
            "repd_operational_capacity_mw": source,
            "difference_mw": difference,
            "interpretation": (
                "matched" if abs(difference) <= 1e-8 else
                "outside_repd_scope" if technology not in repd else
                "requires_owner_review"
            ),
        })
    return result


def _region_to_zone_weights(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    capacity: dict[tuple[str, str, str], float] = defaultdict(float)
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        region = str(row.get("region") or "not_declared")
        technology = str(row.get("technology") or "")
        zone = str(row.get("zone_id") or "")
        mapped = float(row.get("capacity_mw") or 0.0) * float(row.get("share") or 0.0)
        capacity[(region, technology, zone)] += mapped
        totals[(region, technology)] += mapped
    return [
        {
            "region": region,
            "technology": technology,
            "zone_id": zone,
            "mapped_capacity_mw": mapped,
            "weight": mapped / totals[(region, technology)] if totals[(region, technology)] else 0.0,
        }
        for (region, technology, zone), mapped in sorted(capacity.items())
    ]


def _svg_map(
    geometry: Mapping[str, object], zones: Sequence[NetworkZone],
    corridors: Sequence[TransportCorridor], asset_rows: Sequence[Mapping[str, object]],
    landings: Sequence[InterconnectorLanding],
) -> str:
    colours = ["#4f6bed", "#25a18e", "#f4a261", "#8d6cab", "#e76f51"]
    ordered_zones = [zone for zone in zones if not zone.is_unconstrained_fallback]
    ordered_zones.extend(zone for zone in zones if zone.is_unconstrained_fallback)
    zone_number = {zone.zone_id: index + 1 for index, zone in enumerate(ordered_zones)}
    zone_colour = {
        zone.zone_id: colours[index % len(colours)]
        for index, zone in enumerate(ordered_zones)
    }
    features = {str(feature.get("properties", {}).get("zone_id")): feature for feature in geometry.get("features", [])}  # type: ignore[union-attr]
    polygons: list[tuple[str, list[tuple[float, float]]]] = []
    for zone in zones:
        feature = features.get(zone.zone_id)
        shape = feature.get("geometry") if isinstance(feature, Mapping) else None
        for polygon in _polygon_parts(shape):
            if not isinstance(polygon, list) or not polygon:
                continue
            points = [(float(point[0]), float(point[1])) for point in polygon[0]]
            polygons.append((zone.zone_id, points))
    if not polygons:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1320 800"></svg>\n'
    xs = [x for _, points in polygons for x, _ in points]
    ys = [y for _, points in polygons for _, y in points]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    width, height, map_width, pad = 1320.0, 800.0, 900.0, 40.0
    sx = (map_width - 2 * pad) / max(xmax - xmin, 1e-9)
    sy = (height - 2 * pad) / max(ymax - ymin, 1e-9)
    scale = min(sx, sy)
    rendered_width = (xmax - xmin) * scale
    rendered_height = (ymax - ymin) * scale
    x_offset = pad + (map_width - 2 * pad - rendered_width) / 2
    y_offset = pad + (height - 2 * pad - rendered_height) / 2
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}">',
        '<rect width="1320" height="800" fill="#f8fafc"/>',
    ]
    centres_raw: dict[str, tuple[float, float]] = {}
    by_zone: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for zone_id, points in polygons:
        by_zone[zone_id].extend(points)
    for zone_id, points in by_zone.items():
        centres_raw[zone_id] = (
            sum(x for x, _ in points) / len(points),
            sum(y for _, y in points) / len(points),
        )

    def xy(longitude: float, latitude: float) -> tuple[float, float]:
        return (
            x_offset + (longitude - xmin) * scale,
            height - y_offset - (latitude - ymin) * scale,
        )

    for zone_id, points in polygons:
        rendered = " ".join(
            f"{xy(x, y)[0]:.2f},{xy(x, y)[1]:.2f}" for x, y in points
        )
        lines.append(
            f'<polygon data-kind="zone" data-id="{html.escape(zone_id)}" '
            f'points="{rendered}" fill="{zone_colour.get(zone_id, "#cbd5e1")}" '
            f'stroke="#334155" stroke-width="1.5" opacity="0.78"/>'
        )
    for corridor in corridors:
        if corridor.from_zone_id not in centres_raw or corridor.to_zone_id not in centres_raw:
            continue
        x1, y1 = xy(*centres_raw[corridor.from_zone_id])
        x2, y2 = xy(*centres_raw[corridor.to_zone_id])
        lines.append(
            f'<line data-kind="corridor" data-id="{html.escape(corridor.corridor_id)}" '
            f'x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="#111827" stroke-width="4" stroke-dasharray="10 6"/>'
        )
    for zone_id, (longitude, latitude) in centres_raw.items():
        x, y = xy(longitude, latitude)
        lines.append(
            f'<circle data-kind="zone-index" data-id="{html.escape(zone_id)}" '
            f'cx="{x:.2f}" cy="{y:.2f}" r="11" fill="#ffffff" '
            f'stroke="#0f172a" stroke-width="1.5"/>'
        )
        lines.append(
            f'<text data-kind="zone-index-label" x="{x:.2f}" y="{y + 4.5:.2f}" '
            f'text-anchor="middle" font-family="Arial, sans-serif" font-size="12" '
            f'font-weight="700" fill="#0f172a">{zone_number[zone_id]}</text>'
        )
    offsets: dict[str, int] = defaultdict(int)
    for row in asset_rows:
        zone_id = str(row.get("zone_id") or "")
        if zone_id not in centres_raw:
            continue
        longitude = row.get("longitude")
        latitude = row.get("latitude")
        if longitude is None or latitude is None:
            base_x, base_y = xy(*centres_raw[zone_id])
            offset = offsets[zone_id]
            offsets[zone_id] += 1
            x = base_x + 12.0 * ((offset % 5) - 2)
            y = base_y + 18.0 + 12.0 * (offset // 5)
        else:
            x, y = xy(float(longitude), float(latitude))
        lines.append(
            f'<circle data-kind="power-asset" data-id="{html.escape(str(row.get("asset_id") or ""))}" '
            f'cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#7f1d1d" stroke="#ffffff" stroke-width="1"/>'
        )
    landing_offsets: dict[str, int] = defaultdict(int)
    for landing in landings:
        if landing.zone_id not in centres_raw:
            continue
        base_x, base_y = xy(*centres_raw[landing.zone_id])
        offset = landing_offsets[landing.zone_id]
        landing_offsets[landing.zone_id] += 1
        x = base_x + 16.0 + 15.0 * (offset % 3)
        y = base_y - 16.0 + 15.0 * (offset // 3)
        lines.append(
            f'<rect data-kind="interconnector" data-id="{html.escape(landing.interconnector_id)}" '
            f'x="{x:.2f}" y="{y:.2f}" width="12" height="12" '
            f'fill="#f8fafc" stroke="#be123c" stroke-width="3"/>'
        )

    legend_x = 925.0
    lines.append(
        f'<line x1="{legend_x - 20:g}" y1="30" x2="{legend_x - 20:g}" y2="770" '
        'stroke="#cbd5e1" stroke-width="1"/>'
    )
    for index, zone in enumerate(ordered_zones):
        y = 42.0 + index * 25.0
        lines.append(
            f'<circle data-kind="zone-legend" data-id="{html.escape(zone.zone_id)}" '
            f'cx="{legend_x:.2f}" cy="{y:.2f}" r="9" '
            f'fill="{zone_colour[zone.zone_id]}" stroke="#334155" stroke-width="1"/>'
        )
        lines.append(
            f'<text x="{legend_x:.2f}" y="{y + 4:.2f}" text-anchor="middle" '
            f'font-family="Arial, sans-serif" font-size="10" font-weight="700" '
            f'fill="#0f172a">{index + 1}</text>'
        )
        display_name = zone.display_name
        if zone.is_unconstrained_fallback:
            display_name += " (unconstrained fallback)"
        lines.append(
            f'<text x="{legend_x + 17:.2f}" y="{y + 5:.2f}" '
            f'font-family="Arial, sans-serif" font-size="13" fill="#0f172a">'
            f'{html.escape(display_name)}</text>'
        )

    symbol_y = 650.0
    lines.append(
        f'<g data-kind="symbol-legend" font-family="Arial, sans-serif" '
        f'font-size="13" fill="#0f172a">'
        f'<line x1="{legend_x - 8:.2f}" y1="{symbol_y:.2f}" '
        f'x2="{legend_x + 22:.2f}" y2="{symbol_y:.2f}" stroke="#111827" '
        f'stroke-width="4" stroke-dasharray="10 6"/>'
        f'<text x="{legend_x + 32:.2f}" y="{symbol_y + 5:.2f}">Computational corridor</text>'
        f'<circle cx="{legend_x + 7:.2f}" cy="{symbol_y + 28:.2f}" r="5" '
        f'fill="#7f1d1d" stroke="#ffffff" stroke-width="1"/>'
        f'<text x="{legend_x + 32:.2f}" y="{symbol_y + 33:.2f}">Power asset</text>'
        f'<rect x="{legend_x + 1:.2f}" y="{symbol_y + 47:.2f}" width="12" height="12" '
        f'fill="#f8fafc" stroke="#be123c" stroke-width="3"/>'
        f'<text x="{legend_x + 32:.2f}" y="{symbol_y + 59:.2f}">Interconnector landing</text>'
        '</g>'
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _copy_weather(
    path: Path, expected_mode: str, period_ids: Sequence[str],
    required_capacity_mw_by_technology_zone: Mapping[tuple[str, str], float],
) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    bundle = ZonalAvailabilityBundle.from_dict(payload)
    bundle.validate()
    if bundle.mode != expected_mode:
        raise ValueError(f"Weather bundle {path.name} has mode {bundle.mode}, expected {expected_mode}")
    if tuple(bundle.period_ids) != tuple(period_ids):
        raise ValueError(f"Weather bundle {path.name} uses a different accepted demand clock")
    covered: dict[tuple[str, str], float] = defaultdict(float)
    for profile in bundle.profiles:
        covered[(profile.technology.lower(), profile.zone_id)] += profile.aggregated_capacity_mw
    missing = sorted(set(required_capacity_mw_by_technology_zone).difference(covered))
    if missing:
        raise ValueError(f"Weather bundle {path.name} lacks active VRE technology-zone profiles: {missing}")
    mismatched = {
        key: {"mapped_mw": required, "profile_mw": covered.get(key, 0.0)}
        for key, required in required_capacity_mw_by_technology_zone.items()
        if abs(required - covered.get(key, 0.0)) > 1e-8
    }
    if mismatched:
        raise ValueError(f"Weather bundle {path.name} changes mapped VRE capacity totals: {mismatched}")
    return bundle.to_dict()


def _role_payloads(
    zones: Sequence[NetworkZone], corridors: Sequence[TransportCorridor],
    boundaries: Sequence[ETYSBoundary], mappings: Sequence[ZonalAssetMapping],
    demand: ZonalDemand, demand_methods: Mapping[str, str],
    ratings: Sequence[BoundaryRatingProfile], landings: Sequence[InterconnectorLanding],
    audit: SpatialAudit, geometry: Mapping[str, object],
    source_directions: Mapping[str, str], merged_zone_aliases: Mapping[str, str],
) -> dict[str, dict[str, object]]:
    return {
        "value.zonal.zones": {"schema_version": "value.network-zones/v1", "zones": [item.to_dict() for item in zones], "geometry": geometry, "merged_zone_aliases": dict(merged_zone_aliases)},
        "value.zonal.corridors": {"schema_version": "value.transport-corridors/v1", "corridors": [item.to_dict() for item in corridors]},
        "value.zonal.cutsets": {"schema_version": "value.etys-cutsets/v1", "cutsets": [item.to_dict() for item in boundaries], "source_direction_by_boundary": dict(source_directions)},
        "value.zonal.asset-map": {"schema_version": "value.zonal-asset-mappings/v1", "asset_mappings": [item.to_dict() for item in mappings]},
        "value.zonal.demand": {"schema_version": "value.zonal-demand-dataset/v1", "zonal_demand": demand.to_dict(), "method_by_zone": dict(demand_methods)},
        "value.zonal.ratings": {"schema_version": "value.boundary-rating-profiles/v1", "rating_profiles": [item.to_dict() for item in ratings]},
        "value.zonal.interconnector-landings": {"schema_version": "value.interconnector-landings/v1", "interconnector_landings": [item.to_dict() for item in landings]},
        "value.zonal.spatial-audit": {
            "schema_version": audit.schema_version,
            "active_asset_ids": list(audit.active_asset_ids),
            "capacity_mw_by_technology": dict(audit.capacity_mw_by_technology),
            "mapped_capacity_mw_by_technology": dict(audit.mapped_capacity_mw_by_technology),
            "tolerance_mw": audit.tolerance_mw,
            "fallback_asset_ids": list(audit.fallback_asset_ids),
            "excluded_northern_ireland_asset_ids": list(audit.excluded_northern_ireland_asset_ids),
        },
    }


def _build_candidate_compatibility_impl(source_inventory: Path, output_root: Path) -> dict[str, object]:
    """Build, validate and audit an unsigned candidate without installing it."""

    source_inventory = Path(source_inventory).resolve()
    paths = validate_source_inventory(source_inventory)
    output_root = Path(output_root).resolve()
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    dso_payload = json.loads(paths["dso_areas"].read_text(encoding="utf-8"))
    zones, retained_geometry, merged_zone_aliases = _zones(dso_payload)
    national_rows = _read_csv(paths["neso_national_demand"])
    demand, demand_methods, max_residual = _demand(
        national_rows, _read_csv(paths["regional_demand_evidence"]), zones,
        merged_zone_aliases,
    )
    etys_payload = json.loads(paths["etys_boundaries"].read_text(encoding="utf-8"))
    corridors, boundaries, ratings, assumed, source_directions = _network(
        etys_payload, zones, demand.period_ids, merged_zone_aliases,
    )
    mappings, audit, landings, mapping_audit = _fleet(
        _read_csv(paths["model_fleet"]), _read_csv(paths["interconnector_landings"]),
        zones, merged_zone_aliases,
    )
    repd_comparison = _repd_comparison(
        _read_csv(paths["repd"]), audit.capacity_mw_by_technology,
    )
    required_vre: dict[tuple[str, str], float] = defaultdict(float)
    for mapping in mappings:
        if (
            mapping.asset_class == "generator"
            and (
                "wind" in mapping.technology.lower()
                or "solar" in mapping.technology.lower()
                or mapping.technology.lower() in {"onshore", "offshore"}
            )
        ):
            capacity = float(next(
                row["capacity_mw"] for row in mapping_audit["asset_mappings"]  # type: ignore[index]
                if row["asset_id"] == mapping.asset_id and row["zone_id"] == mapping.zone_id
            ))
            required_vre[(mapping.technology.lower(), mapping.zone_id)] += capacity * mapping.share
    weather = {
        "representative-point.json": _copy_weather(
            paths["era5_representative_profiles"], "representative_point",
            demand.period_ids, required_vre,
        ),
        "repd-era5-aggregated.json": _copy_weather(
            paths["era5_aggregated_profiles"], "repd_era5_mw_aggregated",
            demand.period_ids, required_vre,
        ),
    }

    role_payloads = _role_payloads(
        zones, corridors, boundaries, mappings, demand, demand_methods, ratings,
        landings, audit, retained_geometry, source_directions, merged_zone_aliases,
    )
    bindings: dict[str, dict[str, object]] = {}
    scientific_files: dict[str, str] = {}
    for role in ZONAL_ROLES:
        relative = f"scientific/{role}.json"
        path = output_root / relative
        _write_json(path, role_payloads[role])
        digest = sha256_file(path)
        bindings[role] = {"role": role, "uri": relative, "format": "json", "sha256": digest, "bytes": path.stat().st_size}
        scientific_files[relative] = digest
    for filename, payload in weather.items():
        relative = f"scientific/weather/{filename}"
        path = output_root / relative
        _write_json(path, payload)
        scientific_files[relative] = sha256_file(path)

    source_hashes = {role: str(binding["sha256"]) for role, binding in bindings.items()}
    pack_audit = replace(audit, source_sha256_by_role=source_hashes)
    pack = ZonalNetworkPack(
        network_pack_id="candidate-unassigned",
        scientific_sha256="",
        zones=tuple(zones), corridors=tuple(corridors), cutsets=tuple(boundaries),
        asset_mappings=tuple(mappings), zonal_demand=demand,
        rating_profiles=tuple(ratings), interconnector_landings=tuple(landings),
        spatial_audit=pack_audit, loss_capability_absent_reason="lossless_v1",
        geometry_artifact="review/zone-map.svg",
        provenance={
            "builder_version": BUILDER_VERSION,
            "source_inventory_id": _load_inventory(source_inventory).get("inventory_id"),
            "source_objects": _source_metadata(source_inventory),
            "candidate_only": True,
        },
    )
    pack = replace(pack, scientific_sha256=pack.compute_scientific_sha256())
    pack.validate()

    map_path = output_root / "review" / "zone-map.svg"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(
        _svg_map(
            retained_geometry, zones, corridors,
            mapping_audit["asset_mappings"], landings,  # type: ignore[arg-type]
        ),
        encoding="utf-8", newline="",
    )
    offshore = [row for row in mapping_audit["asset_mappings"] if "offshore" in str(row["technology"]).lower()]  # type: ignore[index]
    review = {
        "schema_version": "value.gb-zonal-candidate-review/v1",
        "candidate_scientific_sha256": pack.scientific_sha256,
        "zone_count": len(zones),
        "constrained_zone_count": sum(not zone.is_unconstrained_fallback for zone in zones),
        "target_zone_count_review": "approximately_18_to_24_not_schema_enforced",
        "corridor_count": len(corridors),
        "boundary_count": len(boundaries),
        "merged_dso_features": merged_zone_aliases,
        "maximum_zonal_demand_reconciliation_residual_mwh": max_residual,
        "capacity_reconciliation": {
            "source_mw_by_technology": dict(audit.capacity_mw_by_technology),
            "mapped_mw_by_technology": dict(audit.mapped_capacity_mw_by_technology),
        },
        "model_vs_repd_operational_capacity": repd_comparison,
        "capacity_mw_by_technology_and_status": mapping_audit["capacity_mw_by_technology_and_status"],
        "region_to_zone_weights": _region_to_zone_weights(mapping_audit["asset_mappings"]),  # type: ignore[arg-type]
        "fallback_asset_ids": list(audit.fallback_asset_ids),
        "excluded_northern_ireland_asset_ids": list(audit.excluded_northern_ireland_asset_ids),
        "offshore_connection_audit": {
            "records": offshore,
            "actual_count": sum(row["mapping_method"] in {"actual_landfall_override", "source_coordinate"} for row in offshore),
            "inferred_count": sum(row["mapping_method"] == "inferred_nearest_coast_dso" for row in offshore),
            "fallback_count": sum(row["zone_id"] == FALLBACK_ZONE for row in offshore),
            "actual_mw": sum(float(row["capacity_mw"]) * float(row["share"]) for row in offshore if row["mapping_method"] in {"actual_landfall_override", "source_coordinate"}),
            "inferred_mw": sum(float(row["capacity_mw"]) * float(row["share"]) for row in offshore if row["mapping_method"] == "inferred_nearest_coast_dso"),
            "fallback_mw": sum(float(row["capacity_mw"]) * float(row["share"]) for row in offshore if row["zone_id"] == FALLBACK_ZONE),
        },
        "assumed_symmetric_boundaries": assumed,
        "source_direction_by_boundary": source_directions,
        "derating_profiles": [profile.to_dict() for profile in ratings],
        "unmapped_or_excluded": [
            {"asset_id": item, "reason": "northern_ireland_outside_gb_scope"}
            for item in audit.excluded_northern_ireland_asset_ids
        ],
        "source_rights": _source_metadata(source_inventory),
        "owner_signoff": {"status": "pending", "signed_by": None, "signed_at": None},
    }
    _write_json(output_root / "review" / "reconciliation-and-rights.json", review)
    candidate_manifest = {
        "schema_version": CANDIDATE_SCHEMA,
        "status": "awaiting_owner_signoff",
        "candidate_id": "prompt98-unsigned-gb-zonal-candidate",
        "candidate_scientific_sha256": pack.scientific_sha256,
        "builder_version": BUILDER_VERSION,
        "final_network_pack_id": None,
        "installed": False,
        "owner_signoff": review["owner_signoff"],
        "zonal_network_pack": pack.to_dict(),
        "bindings": bindings,
        "weather_artifacts": sorted(f"scientific/weather/{name}" for name in weather),
        "review_artifacts": ["review/zone-map.svg", "review/reconciliation-and-rights.json"],
        "scientific_file_sha256": dict(sorted(scientific_files.items())),
    }
    _write_json(output_root / "candidate-manifest.json", candidate_manifest)
    return {
        "schema_version": "value.gb-zonal-candidate-build-result/v1",
        "status": "awaiting_owner_signoff",
        "candidate_scientific_sha256": pack.scientific_sha256,
        "scientific_file_sha256": dict(sorted(scientific_files.items())),
        "maximum_demand_residual_mwh": max_residual,
        "assumed_symmetric_boundaries": assumed,
        "merged_dso_features": merged_zone_aliases,
        "zone_count": len(zones),
        "active_assets": len(audit.active_asset_ids),
        "fallback_assets": len(audit.fallback_asset_ids),
        "output": output_root.name,
    }


def build_candidate(source_inventory: Path, output_root: Path) -> dict[str, object]:
    """Compatibility facade over the Data Workbench candidate compiler."""

    from .data_workbench.compilers.network_candidate import build_prompt98_candidate

    return build_prompt98_candidate(
        source_inventory,
        output_root,
        implementation=_build_candidate_compatibility_impl,
    )


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(payload), encoding="utf-8", newline="")
    os.replace(temporary, path)


def _checked_candidate(candidate_root: Path, expected_sha256: str) -> tuple[dict[str, object], ZonalNetworkPack]:
    """Revalidate a Prompt 98 candidate immediately before owner promotion."""

    root = Path(candidate_root).resolve()
    manifest_path = root / "candidate-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CANDIDATE_SCHEMA:
        raise ValueError("Prompt 98 candidate uses an incompatible schema")
    if payload.get("status") != "awaiting_owner_signoff":
        raise ValueError("Prompt 98 candidate is not awaiting owner signoff")
    if payload.get("final_network_pack_id") is not None or payload.get("installed") is not False:
        raise ValueError("Prompt 98 candidate was already assigned or installed")
    signoff = payload.get("owner_signoff")
    if not isinstance(signoff, Mapping) or signoff.get("status") != "pending":
        raise ValueError("Prompt 98 candidate does not have a pending owner signoff")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("Expected approved candidate hash must be a SHA-256 value")
    pack = ZonalNetworkPack.from_dict(payload.get("zonal_network_pack", {}))  # type: ignore[arg-type]
    pack.validate()
    declared = str(payload.get("candidate_scientific_sha256") or "")
    if declared != expected_sha256 or pack.scientific_sha256 != expected_sha256:
        raise ValueError("The approved candidate hash does not match the candidate on disk")

    scientific_hashes = payload.get("scientific_file_sha256")
    if not isinstance(scientific_hashes, Mapping) or not scientific_hashes:
        raise ValueError("Prompt 98 candidate has no scientific artifact inventory")
    for raw_relative, raw_expected in scientific_hashes.items():
        relative = str(raw_relative)
        artifact = (root / relative).resolve()
        try:
            artifact.relative_to(root)
        except ValueError as exc:
            raise ValueError("Prompt 98 scientific artifact escapes the candidate root") from exc
        if not artifact.is_file() or sha256_file(artifact) != str(raw_expected):
            raise ValueError(f"Prompt 98 scientific artifact changed after review: {relative}")

    bindings = payload.get("bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != set(ZONAL_ROLES):
        raise ValueError("Prompt 98 candidate does not bind the eight zonal roles")
    for role, raw_binding in bindings.items():
        if not isinstance(raw_binding, Mapping):
            raise ValueError(f"Prompt 98 candidate binding is invalid: {role}")
        artifact = (root / str(raw_binding.get("uri") or "")).resolve()
        try:
            artifact.relative_to(root)
        except ValueError as exc:
            raise ValueError("Prompt 98 binding escapes the candidate root") from exc
        expected = str(raw_binding.get("sha256") or "")
        if not artifact.is_file() or sha256_file(artifact) != expected:
            raise ValueError(f"Prompt 98 binding changed after review: {role}")
        if pack.spatial_audit.source_sha256_by_role.get(str(role)) != expected:
            raise ValueError(f"Prompt 98 binding identity changed after review: {role}")

    for raw_relative in payload.get("weather_artifacts", []):  # type: ignore[assignment]
        relative = str(raw_relative)
        artifact = (root / relative).resolve()
        try:
            artifact.relative_to(root)
        except ValueError as exc:
            raise ValueError("Prompt 98 weather artifact escapes the candidate root") from exc
        weather = ZonalAvailabilityBundle.from_dict(
            json.loads(artifact.read_text(encoding="utf-8"))
        )
        weather.validate()
    for required in ("review/zone-map.svg", "review/reconciliation-and-rights.json"):
        if not (root / required).is_file():
            raise ValueError(f"Prompt 98 candidate is missing review evidence: {required}")
    return payload, pack


def _final_network_pack_id(candidate_scientific_sha256: str) -> str:
    return f"force-gb-zonal-network-v1-{candidate_scientific_sha256[:12]}"


def sign_and_install_candidate(
    candidate_root: Path,
    *,
    state_root: Path,
    dataset_slots: Sequence[Mapping[str, object]],
    approved_by: str,
    approved_at: str,
    expected_candidate_scientific_sha256: str,
) -> dict[str, object]:
    """Create a local approval attestation and install an immutable network pack.

    The reviewed candidate directory is never modified.  The candidate hash is
    the object approved by the owner; the installed scientific hash additionally
    covers the final immutable ID and installed artifact paths.  The receipt
    records both identities so the promotion is auditable without pretending the
    unsigned candidate already had a final ID.
    """

    if not str(approved_by).strip() or not str(approved_at).strip():
        raise ValueError("Owner approval requires the approver and approval time")
    root = Path(candidate_root).resolve()
    state = Path(state_root).resolve()
    candidate, candidate_pack = _checked_candidate(
        root, expected_candidate_scientific_sha256
    )
    pack_id = _final_network_pack_id(expected_candidate_scientific_sha256)
    final_provenance = dict(candidate_pack.provenance)
    final_provenance.update({
        "candidate_only": False,
        "approved_candidate_scientific_sha256": expected_candidate_scientific_sha256,
        "runtime_downloads": False,
    })
    installed_identity = replace(
        candidate_pack,
        network_pack_id=pack_id,
        scientific_sha256="",
        geometry_artifact="files/review/zone-map.svg",
        provenance=final_provenance,
    )
    installed_identity = replace(
        installed_identity,
        scientific_sha256=installed_identity.compute_scientific_sha256(),
    )
    installed_identity.validate()

    with tempfile.TemporaryDirectory(prefix="force-prompt98-sign-") as temporary:
        pack_root = Path(temporary) / "pack"
        files_root = pack_root / "files"
        files_root.mkdir(parents=True)
        installed_bindings: dict[str, dict[str, object]] = {}
        bindings = candidate["bindings"]
        assert isinstance(bindings, Mapping)
        for role in ZONAL_ROLES:
            source_binding = bindings[role]
            assert isinstance(source_binding, Mapping)
            source = root / str(source_binding["uri"])
            relative = f"files/zonal/{source.name}"
            target = pack_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            installed_bindings[role] = {
                **dict(source_binding),
                "role": role,
                "uri": relative,
                "sha256": sha256_file(target),
            }

        weather_paths: list[str] = []
        for raw_relative in candidate.get("weather_artifacts", []):  # type: ignore[assignment]
            source = root / str(raw_relative)
            relative = f"files/weather/{source.name}"
            target = pack_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            weather_paths.append(relative)
        for raw_relative in candidate.get("review_artifacts", []):  # type: ignore[assignment]
            source = root / str(raw_relative)
            relative = f"files/review/{source.name}"
            target = pack_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.copy2(root / "candidate-manifest.json", files_root / "approved-candidate-manifest.json")

        review = json.loads(
            (root / "review" / "reconciliation-and-rights.json").read_text(encoding="utf-8")
        )
        accepted_assumptions = {
            "assumed_symmetric_boundaries": list(review.get("assumed_symmetric_boundaries") or []),
            "loss_model": "lossless_v1",
            "fallback_zone": FALLBACK_ZONE,
        }
        approval = {
            "schema_version": "value.local-approval-attestation/v1",
            "signature_type": "local_approval_attestation",
            "approved_by": str(approved_by).strip(),
            "approved_at": str(approved_at).strip(),
            "approved_candidate_scientific_sha256": expected_candidate_scientific_sha256,
            "network_pack_id": pack_id,
            "installed_scientific_sha256": installed_identity.scientific_sha256,
            "accepted_assumptions": accepted_assumptions,
        }
        _atomic_json(files_root / "approval-attestation.json", approval)
        _atomic_json(pack_root / "RIGHTS.json", {
            "schema_version": "value.data-rights/v1",
            "network_pack_id": pack_id,
            "complete_bundle_redistribution": "local_rights_governed",
            "public_source_release_includes_complete_bundle": False,
            "reason": "The aggregate contains local-use and pointer-only UK research inputs; redistribute source records only under their individual terms.",
            "source_rights": list(review.get("source_rights") or []),
        })
        (pack_root / "ATTRIBUTION.md").write_text(
            "# Attribution\n\n"
            "Compiled by Hanzhe Xing for VALUE from the source records listed in "
            "`RIGHTS.json`. Each upstream source retains its own licence and attribution.\n",
            encoding="utf-8",
            newline="",
        )
        manifest = {
            "schema_version": "value.data-pack/v1",
            "id": pack_id,
            "name": "VALUE GB zonal network benchmark — ETYS 2025 B6/B7a",
            "licence": "mixed-source-local-rights-governed",
            "data_pack_type": "network_overlay",
            "annual_economics_eligible": True,
            "scientific_baseline_eligible": False,
            "scientific_baseline_status": "owner_approved_network_input_pending_solver_validation",
            "owner_approval": approval,
            "zonal_network_pack": {
                "network_pack_id": installed_identity.network_pack_id,
                "scientific_sha256": installed_identity.scientific_sha256,
                "loss_capability_absent_reason": installed_identity.loss_capability_absent_reason,
                "geometry_artifact": installed_identity.geometry_artifact,
                "provenance": dict(installed_identity.provenance),
            },
            "bindings": installed_bindings,
            "weather_artifacts": sorted(weather_paths),
        }
        _atomic_json(pack_root / "manifest.json", manifest)

        archive = state / "signed-bundles" / f"{pack_id}.zip"
        bundle = build_data_bundle(pack_root=pack_root, destination=archive)
        installation = install_data_bundle(
            archive,
            packs_root=state / "installed-packs",
            dataset_slots=dataset_slots,
            rights_acknowledged=True,
            minimum_free_space_bytes=0,
        )

    receipt: dict[str, object] = {
        **approval,
        "bundle_sha256": bundle["sha256"],
        "pack_revision_sha256": bundle["pack_revision_sha256"],
        "validation": installation["validation"],
        "installed_location": f"<VALUE_DATA_HOME>/data-workbench/installed-packs/{pack_id}",
    }
    _atomic_json(state / "approvals" / f"{pack_id}.json", receipt)
    return receipt
