"""Interconnector landing and profile-allocation compiler."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from shapely.geometry import Point, shape


_ACTIVE = {"active", "commissioned", "operating", "operational"}


def _capacity(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Interconnector {label} is not numeric") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"Interconnector {label} is contradictory or negative")
    return result


def _haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, left)
    lon2, lat2 = map(math.radians, right)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def _zones(payload: Mapping[str, object]) -> list[tuple[str, str, object]]:
    if payload.get("type") != "FeatureCollection":
        raise ValueError("Interconnector zones must be a GeoJSON FeatureCollection")
    result: list[tuple[str, str, object]] = []
    for feature in payload.get("features", []):  # type: ignore[assignment]
        if not isinstance(feature, Mapping) or not isinstance(feature.get("properties"), Mapping):
            raise ValueError("Interconnector zone feature is invalid")
        props = feature["properties"]
        zone_id = str(props.get("zone_id") or "")
        nation = str(props.get("nation") or "")
        if nation.strip().casefold() in {"northern ireland", "northern_ireland", "ni"}:
            raise ValueError("Northern Ireland cannot be an internal GB network zone")
        result.append((zone_id, nation, shape(feature.get("geometry"))))
    if not result or len({row[0] for row in result}) != len(result):
        raise ValueError("Interconnector zones are empty or duplicated")
    return sorted(result, key=lambda row: row[0])


def _zone_for_point(point: Point, zones: Sequence[tuple[str, str, object]]) -> str:
    candidates = sorted(zone_id for zone_id, _, polygon in zones if polygon.covers(point))
    if not candidates:
        raise ValueError("Interconnector landing coordinate has an unknown landing zone")
    return candidates[0]


def compile_interconnector_landings(
    register_rows: Sequence[Mapping[str, object]],
    connection_evidence: Mapping[str, Mapping[str, object]],
    zone_geojson: Mapping[str, object],
    *,
    coast_candidates: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    zones = _zones(zone_geojson)
    identities = [str(row.get("interconnector_id") or "").strip() for row in register_rows]
    if any(not item for item in identities) or len(identities) != len(set(identities)):
        raise ValueError("Interconnector register contains a blank or duplicate asset identity")
    compiled: list[dict[str, object]] = []
    waivers: list[str] = []
    for row in register_rows:
        asset_id = str(row.get("interconnector_id") or "").strip()
        status = str(row.get("status") or "").strip().casefold()
        if status not in _ACTIVE:
            continue
        import_capacity = _capacity(row.get("import_capacity_mw"), "import capability")
        export_capacity = _capacity(row.get("export_capacity_mw"), "export capability")
        if import_capacity == 0 and export_capacity == 0:
            raise ValueError(f"Interconnector {asset_id} has contradictory zero capability evidence")
        site = str(row.get("connection_site") or "").strip()
        evidence = connection_evidence.get(site)
        if evidence:
            point = Point(float(evidence["longitude"]), float(evidence["latitude"]))
            zone_id = _zone_for_point(point, zones)
            method = str(evidence.get("evidence") or "official_connection_coordinate")
            distance_km = 0.0
            longitude, latitude = point.x, point.y
            evidence_level = "official_or_operator"
        else:
            try:
                reference = (float(row.get("fallback_longitude")), float(row.get("fallback_latitude")))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Interconnector {asset_id} lacks official landing coordinates and fallback reference"
                ) from exc
            eligible: list[tuple[float, str, str, float, float]] = []
            known_zone_ids = {zone_id for zone_id, _, _ in zones}
            for candidate in coast_candidates:
                zone_id = str(candidate.get("zone_id") or "")
                if zone_id not in known_zone_ids:
                    raise ValueError("Nearest-coast evidence names an unknown landing zone")
                longitude = float(candidate.get("longitude"))
                latitude = float(candidate.get("latitude"))
                eligible.append(
                    (
                        _haversine_km(reference, (longitude, latitude)),
                        str(candidate.get("coast_id") or ""),
                        zone_id,
                        longitude,
                        latitude,
                    )
                )
            if not eligible:
                raise ValueError(f"Interconnector {asset_id} has no deterministic coast candidate")
            distance_km, coast_id, zone_id, longitude, latitude = min(eligible)
            method = "nearest_coast_dso_inference"
            evidence_level = f"inferred_from:{coast_id}"
            waivers.append(f"interconnector.{asset_id}.nearest_coast_dso_inference")
        compiled.append(
            {
                "interconnector_id": asset_id,
                "asset_id": asset_id,
                "counterparty_country": str(row.get("counterparty_country") or ""),
                "connection_site": site,
                "zone_id": zone_id,
                "longitude": longitude,
                "latitude": latitude,
                "landing_method": method,
                "landing_evidence_level": evidence_level,
                "distance_km": distance_km,
                "import_capacity_mw": import_capacity,
                "export_capacity_mw": export_capacity,
                "status": status,
                "effective_date": str(row.get("effective_date") or ""),
                "host_transmission_owner": str(row.get("host_transmission_owner") or ""),
                "envelope_semantics": "signed_profile_envelope",
                "asset_scope": "external_to_gb_internal_fleet",
            }
        )
    return {
        "schema_version": "value.interconnector-landings-candidate/v1",
        "assets": sorted(compiled, key=lambda row: str(row["interconnector_id"])),
        "requested_waivers": sorted(waivers),
    }


def allocate_country_profile(
    profile_rows: Sequence[Mapping[str, object]],
    assets: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    allocations: list[dict[str, object]] = []
    seen_periods: set[tuple[str, str]] = set()
    for row in sorted(profile_rows, key=lambda item: (str(item.get("period_id")), str(item.get("country")))):
        period_id = str(row.get("period_id") or "")
        country = str(row.get("country") or "")
        key = (period_id, country)
        if not period_id or key in seen_periods:
            raise ValueError("Country profile contains a blank or double-counted period")
        seen_periods.add(key)
        timestamp = str(row.get("timestamp") or "")
        exchange = float(row.get("exchange_mw"))
        if not math.isfinite(exchange):
            raise ValueError("Country exchange is not finite")
        direction_field = "import_capacity_mw" if exchange >= 0 else "export_capacity_mw"
        active = [
            asset for asset in assets
            if str(asset.get("counterparty_country") or "") == country
            and str(asset.get("status") or "").casefold() in _ACTIVE
            and (not str(asset.get("effective_date") or "") or str(asset.get("effective_date")) <= timestamp[:10])
        ]
        if not active:
            raise ValueError(f"Country profile {country}/{period_id} has no effective assets")
        capacities = {
            str(asset.get("interconnector_id") or ""): _capacity(asset.get(direction_field), direction_field)
            for asset in active
        }
        total_capacity = sum(capacities.values())
        if abs(exchange) > total_capacity + 1e-9:
            raise ValueError(f"Country profile {country}/{period_id} exceeds the directional envelope")
        if total_capacity <= 0 and exchange != 0:
            raise ValueError(f"Country profile {country}/{period_id} has no directional envelope")
        values = {
            asset_id: (exchange * capacity / total_capacity if total_capacity else 0.0)
            for asset_id, capacity in capacities.items()
        }
        residual = exchange - sum(values.values())
        residual_asset = min(capacities, key=lambda item: (-capacities[item], item))
        values[residual_asset] += residual
        for asset_id in sorted(values):
            if abs(values[asset_id]) > capacities[asset_id] + 1e-9:
                raise ValueError(f"Allocated profile for {asset_id} exceeds its directional envelope")
            allocations.append(
                {
                    "period_id": period_id,
                    "timestamp": timestamp,
                    "country": country,
                    "interconnector_id": asset_id,
                    "exchange_mw": values[asset_id],
                    "directional_capacity_mw": capacities[asset_id],
                }
            )
    return {
        "schema_version": "value.interconnector-profile-allocation/v1",
        "allocation_method": "capacity_weighted_country_split",
        "allocations": allocations,
    }
