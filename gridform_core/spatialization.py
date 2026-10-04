"""Offline economic-agent to physical-zone preprocessing for VALUE.

This module never creates runtime bidders.  It freezes spatial shares at a data
pack revision and produces physical tranches that can be aggregated before the
market is executed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from pyproj import Transformer

from .v2.contracts import AssetStateV2, JsonContract, PlanningProject, YearState
from .zonal_contracts import ZonalAssetMapping


SPATIAL_FLEET_SCHEMA = "value.spatial-fleet/v1"
ALLOCATION_SCHEMA = "value.agent-zone-allocation/v1"


def _freeze_float_map(values: Mapping[str, float]) -> Mapping[str, float]:
    return MappingProxyType({str(key): float(value) for key, value in values.items()})


def _canonical_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalise(values: Mapping[str, float]) -> dict[str, float]:
    positive = {
        str(key): float(value) for key, value in values.items()
        if math.isfinite(float(value)) and float(value) > 0
    }
    total = sum(positive.values())
    if total <= 0:
        return {}
    ordered = sorted(positive)
    result = {key: positive[key] / total for key in ordered}
    # Close binary floating residue deterministically on the final zone.
    result[ordered[-1]] += 1.0 - sum(result.values())
    return result


@dataclass(frozen=True)
class SpatialSourceRecord(JsonContract):
    source_id: str
    source_kind: str
    economic_owner_id: str
    technology: str
    capacity_value: float
    capacity_unit: str
    country: str = "GB"
    zone_id: str | None = None
    location_method: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw_easting: float | None = None
    raw_northing: float | None = None
    frozen_zone_shares: Mapping[str, float] = field(default_factory=dict)
    provenance: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.spatial-source-record/v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "frozen_zone_shares", _freeze_float_map(self.frozen_zone_shares))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    @property
    def capacity_mw(self) -> float:
        if self.capacity_unit == "MW":
            factor = 1.0
        elif self.capacity_unit == "scheme_c_20mw_multiplier":
            if self.technology not in {"onshore", "offshore", "wind"}:
                raise ValueError("The VALUE 20 MW multiplier is valid only for wind")
            factor = 20.0
        else:
            raise ValueError(f"Unsupported spatial capacity unit: {self.capacity_unit}")
        value = float(self.capacity_value) * factor
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Spatial source {self.source_id} has invalid capacity")
        return value

    @property
    def capacity_conversion(self) -> str:
        return (
            f"{float(self.capacity_value)} × 20 MW"
            if self.capacity_unit == "scheme_c_20mw_multiplier"
            else "direct MW"
        )


@dataclass(frozen=True)
class AgentZoneAllocation(JsonContract):
    allocation_id: str
    economic_owner_id: str
    technology: str
    source_id: str
    source_kind: str
    zone_id: str
    capacity_mw: float
    zone_share: float
    location_method: str
    pack_revision: str
    source_capacity_unit: str
    capacity_unit_conversion: str
    provenance: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = ALLOCATION_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    def validate(self) -> None:
        if not all((self.allocation_id, self.economic_owner_id, self.technology, self.source_id, self.zone_id, self.pack_revision)):
            raise ValueError("Agent-zone allocation has a blank identity field")
        if not math.isfinite(self.capacity_mw) or self.capacity_mw < 0:
            raise ValueError(f"Allocation {self.allocation_id} has invalid MW")
        if not math.isfinite(self.zone_share) or not 0 < self.zone_share <= 1:
            raise ValueError(f"Allocation {self.allocation_id} has invalid share")


@dataclass(frozen=True)
class SpatialFleet(JsonContract):
    pack_revision: str
    allocations: Sequence[AgentZoneAllocation]
    source_capacity_mw_by_technology: Mapping[str, float]
    mapped_capacity_mw_by_technology: Mapping[str, float]
    fallback_asset_ids: Sequence[str]
    excluded_northern_ireland_asset_ids: Sequence[str]
    material_spatial_fallback_by_technology: Mapping[str, bool]
    scientific_sha256: str = ""
    schema_version: str = SPATIAL_FLEET_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "allocations", tuple(self.allocations))
        object.__setattr__(self, "source_capacity_mw_by_technology", _freeze_float_map(self.source_capacity_mw_by_technology))
        object.__setattr__(self, "mapped_capacity_mw_by_technology", _freeze_float_map(self.mapped_capacity_mw_by_technology))
        object.__setattr__(self, "fallback_asset_ids", tuple(self.fallback_asset_ids))
        object.__setattr__(self, "excluded_northern_ireland_asset_ids", tuple(self.excluded_northern_ireland_asset_ids))
        object.__setattr__(self, "material_spatial_fallback_by_technology", MappingProxyType({
            str(key): bool(value) for key, value in self.material_spatial_fallback_by_technology.items()
        }))

    def compute_scientific_sha256(self) -> str:
        payload = self.to_dict()
        payload["scientific_sha256"] = ""
        return _canonical_hash(payload)

    def validate(self) -> None:
        if self.schema_version != SPATIAL_FLEET_SCHEMA or not self.pack_revision:
            raise ValueError("Spatial fleet identity is invalid")
        for row in self.allocations:
            row.validate()
            if row.pack_revision != self.pack_revision:
                raise ValueError("Allocation pack revision is mutable or inconsistent")
        technologies = set(self.source_capacity_mw_by_technology) | set(self.mapped_capacity_mw_by_technology)
        for technology in technologies:
            source = self.source_capacity_mw_by_technology.get(technology, 0.0)
            mapped = self.mapped_capacity_mw_by_technology.get(technology, 0.0)
            if abs(source - mapped) > 1e-8:
                raise ValueError(f"Spatial capacity drift for {technology}: {source} versus {mapped}")
        if self.scientific_sha256 != self.compute_scientific_sha256():
            raise ValueError("Spatial fleet scientific identity does not match")


@dataclass(frozen=True)
class ConvertedCoordinate(JsonContract):
    raw_easting: float
    raw_northing: float
    latitude: float
    longitude: float
    source_crs: str
    target_crs: str
    transformation_pipeline: str
    schema_version: str = "value.coordinate-conversion/v1"


@dataclass(frozen=True)
class OffshoreLanding(JsonContract):
    project_id: str
    zone_id: str
    method: str
    actual_connection: bool
    distance_km: float | None = None
    source: str | None = None
    schema_version: str = "value.offshore-landing/v1"


def convert_bng_to_wgs84(easting: float, northing: float) -> ConvertedCoordinate:
    """Convert OSGB36 / British National Grid while retaining raw provenance."""

    if not all(math.isfinite(float(value)) for value in (easting, northing)):
        raise ValueError("BNG coordinates must be finite")
    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    longitude, latitude = transformer.transform(float(easting), float(northing))
    return ConvertedCoordinate(
        float(easting), float(northing), float(latitude), float(longitude),
        "EPSG:27700", "EPSG:4326", transformer.description or "EPSG:27700 to EPSG:4326",
    )


def _distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius = 6371.0088
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lon = math.radians(lon_b - lon_a)
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def resolve_offshore_landing(
    project_id: str,
    latitude: float | None,
    longitude: float | None,
    *,
    landing_overrides: Mapping[str, Mapping[str, object]],
    coast_points: Sequence[Mapping[str, object]],
    fallback_zone_id: str = "ENGLAND_FALLBACK",
) -> OffshoreLanding:
    override = landing_overrides.get(project_id)
    if override:
        zone = str(override.get("zone_id") or "")
        if not zone:
            raise ValueError(f"Offshore override for {project_id} has no zone")
        return OffshoreLanding(
            project_id, zone, "actual_landfall_override", True,
            source=str(override.get("source") or "declared_override"),
        )
    if latitude is None or longitude is None or not coast_points:
        return OffshoreLanding(project_id, fallback_zone_id, "unlocated_england_fallback", False)
    candidates: list[tuple[float, str]] = []
    for row in coast_points:
        zone = str(row.get("zone_id") or "")
        try:
            distance = _distance_km(
                float(latitude), float(longitude),
                float(row["latitude"]), float(row["longitude"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if zone:
            candidates.append((distance, zone))
    if not candidates:
        return OffshoreLanding(project_id, fallback_zone_id, "unlocated_england_fallback", False)
    distance, zone = min(candidates, key=lambda item: (item[0], item[1]))
    return OffshoreLanding(
        project_id, zone, "inferred_nearest_coast_dso", False,
        distance_km=distance, source="deterministic_nearest_coast_reference_point",
    )


def _record_weights(
    record: SpatialSourceRecord,
    *,
    operational: Mapping[str, Mapping[str, float]],
    pipeline: Mapping[str, Mapping[str, float]],
    user: Mapping[str, Mapping[str, float]],
    fallback: str,
) -> tuple[dict[str, float], str]:
    if record.zone_id:
        return {record.zone_id: 1.0}, record.location_method or "source_coordinate"
    frozen = _normalise(record.frozen_zone_shares)
    if frozen:
        return frozen, "frozen_pack_share"
    for source, label in (
        (operational, "operational_mw_weight"),
        (pipeline, "active_pipeline_mw_weight"),
        (user, "explicit_user_weight"),
    ):
        weights = _normalise(source.get(record.technology, {}))
        if weights:
            return weights, label
    return {fallback: 1.0}, "unlocated_england_fallback"


def build_agent_zone_allocations(
    records: Sequence[SpatialSourceRecord],
    *,
    operational_mw_by_technology_zone: Mapping[str, Mapping[str, float]] | None = None,
    pipeline_mw_by_technology_zone: Mapping[str, Mapping[str, float]] | None = None,
    user_weights_by_technology_zone: Mapping[str, Mapping[str, float]] | None = None,
    pack_revision: str,
    england_fallback_zone_id: str = "ENGLAND_FALLBACK",
) -> tuple[AgentZoneAllocation, ...]:
    if not pack_revision:
        raise ValueError("Spatial allocations require an immutable pack revision")
    allocations: list[AgentZoneAllocation] = []
    for record in records:
        if record.country.strip().lower() in {"northern ireland", "northern_ireland", "ni"}:
            continue
        weights, method = _record_weights(
            record,
            operational=operational_mw_by_technology_zone or {},
            pipeline=pipeline_mw_by_technology_zone or {},
            user=user_weights_by_technology_zone or {},
            fallback=england_fallback_zone_id,
        )
        for zone, share in sorted(weights.items()):
            allocation_id = "allocation:" + _canonical_hash({
                "revision": pack_revision, "source_id": record.source_id, "zone_id": zone,
                "technology": record.technology, "owner": record.economic_owner_id,
            })[:20]
            row = AgentZoneAllocation(
                allocation_id, record.economic_owner_id, record.technology,
                record.source_id, record.source_kind, zone,
                record.capacity_mw * share, share, method, pack_revision,
                record.capacity_unit, record.capacity_conversion,
                provenance={
                    **dict(record.provenance),
                    "source_latitude": record.latitude,
                    "source_longitude": record.longitude,
                    "raw_bng_easting": record.raw_easting,
                    "raw_bng_northing": record.raw_northing,
                },
            )
            row.validate()
            allocations.append(row)
    return tuple(sorted(allocations, key=lambda item: (item.source_id, item.zone_id)))


def rescale_to_national_totals(
    allocations: Sequence[AgentZoneAllocation],
    national_capacity_mw_by_technology: Mapping[str, float],
) -> tuple[AgentZoneAllocation, ...]:
    result = list(allocations)
    for technology, target_value in sorted(national_capacity_mw_by_technology.items()):
        target = float(target_value)
        if not math.isfinite(target) or target < 0:
            raise ValueError(f"National target for {technology} is invalid")
        indices = [index for index, row in enumerate(result) if row.technology == technology]
        current = sum(result[index].capacity_mw for index in indices)
        if target > 0 and current <= 0:
            raise ValueError(f"Cannot rescale {technology}: no mapped source capacity")
        if not indices:
            continue
        scale = target / current if current > 0 else 0.0
        running = 0.0
        for position, index in enumerate(indices):
            value = (
                target - running
                if position == len(indices) - 1
                else result[index].capacity_mw * scale
            )
            running += value
            result[index] = replace(
                result[index], capacity_mw=value,
                provenance={**dict(result[index].provenance), "national_rescale_factor": scale},
            )
    return tuple(result)


def build_spatial_fleet(
    records: Sequence[SpatialSourceRecord],
    *,
    operational_mw_by_technology_zone: Mapping[str, Mapping[str, float]],
    pipeline_mw_by_technology_zone: Mapping[str, Mapping[str, float]] | None = None,
    user_weights_by_technology_zone: Mapping[str, Mapping[str, float]] | None = None,
    pack_revision: str,
    england_fallback_zone_id: str = "ENGLAND_FALLBACK",
    accepted_national_capacity_mw_by_technology: Mapping[str, float] | None = None,
    material_fallback_threshold: float = 0.01,
) -> SpatialFleet:
    internal = tuple(
        record for record in records
        if record.country.strip().lower() not in {"northern ireland", "northern_ireland", "ni"}
    )
    excluded = tuple(sorted(
        record.source_id for record in records if record not in internal
    ))
    allocations = build_agent_zone_allocations(
        internal,
        operational_mw_by_technology_zone=operational_mw_by_technology_zone,
        pipeline_mw_by_technology_zone=pipeline_mw_by_technology_zone or {},
        user_weights_by_technology_zone=user_weights_by_technology_zone or {},
        pack_revision=pack_revision,
        england_fallback_zone_id=england_fallback_zone_id,
    )
    source_totals: dict[str, float] = {}
    for record in internal:
        source_totals[record.technology] = source_totals.get(record.technology, 0.0) + record.capacity_mw
    if accepted_national_capacity_mw_by_technology is not None:
        allocations = rescale_to_national_totals(
            allocations, accepted_national_capacity_mw_by_technology
        )
        source_totals.update({
            str(key): float(value) for key, value in accepted_national_capacity_mw_by_technology.items()
        })
    mapped: dict[str, float] = {}
    fallback_mw: dict[str, float] = {}
    fallback_ids: set[str] = set()
    for row in allocations:
        mapped[row.technology] = mapped.get(row.technology, 0.0) + row.capacity_mw
        if row.zone_id == england_fallback_zone_id:
            fallback_ids.add(row.source_id)
            fallback_mw[row.technology] = fallback_mw.get(row.technology, 0.0) + row.capacity_mw
    material = {
        technology: (
            fallback_mw.get(technology, 0.0) / total > material_fallback_threshold
            if total > 0 else False
        )
        for technology, total in source_totals.items()
    }
    fleet = SpatialFleet(
        pack_revision, allocations, source_totals, mapped,
        tuple(sorted(fallback_ids)), excluded, material,
    )
    fleet = replace(fleet, scientific_sha256=fleet.compute_scientific_sha256())
    fleet.validate()
    return fleet


def attach_spatial_metadata(
    state: YearState,
    allocations: Sequence[AgentZoneAllocation],
) -> YearState:
    """Attach frozen shares/located projects without splitting economic agents."""

    grouped: dict[str, list[AgentZoneAllocation]] = {}
    for row in allocations:
        row.validate()
        grouped.setdefault(row.source_id, []).append(row)

    def metadata(source_id: str, *, project: bool) -> dict[str, object]:
        rows = grouped.get(source_id, [])
        if not rows:
            return {}
        revisions = {row.pack_revision for row in rows}
        if len(revisions) != 1:
            raise ValueError(f"Spatial mappings for {source_id} mix pack revisions")
        shares = {row.zone_id: row.zone_share for row in sorted(rows, key=lambda item: item.zone_id)}
        payload: dict[str, object] = {
            "spatial_pack_revision": next(iter(revisions)),
            "zonal_allocation_contract": ALLOCATION_SCHEMA,
            "frozen_zone_shares": shares,
            "zonal_allocations": [row.to_dict() for row in rows],
        }
        if project:
            if len(rows) != 1 or abs(rows[0].zone_share - 1.0) > 1e-9:
                raise ValueError(f"Located REPD project {source_id} must retain one exact zone")
            payload["zone_id"] = rows[0].zone_id
            payload["location_method"] = rows[0].location_method
        return payload

    assets = tuple(
        replace(asset, extensions={**dict(asset.extensions), **metadata(asset.asset_id, project=False)})
        for asset in state.assets
    )
    projects = tuple(
        replace(project, extensions={
            **dict(project.extensions),
            **metadata(project.project_id, project=project.source == "repd"),
        })
        for project in state.planning_projects
    )
    revisions = sorted({row.pack_revision for row in allocations})
    return replace(
        state,
        assets=assets,
        planning_projects=projects,
        extensions={
            **dict(state.extensions),
            "spatial_fleet_contract": SPATIAL_FLEET_SCHEMA,
            "spatial_pack_revisions": revisions,
            "runtime_asset_level_bidders_created": False,
        },
    )


def allocations_for_state(
    state: YearState,
    mappings: Sequence[ZonalAssetMapping],
    *,
    pack_revision: str,
) -> tuple[AgentZoneAllocation, ...]:
    """Translate a validated zonal asset map into state-sized frozen tranches."""

    by_source: dict[str, list[ZonalAssetMapping]] = {}
    for mapping in mappings:
        mapping.validate()
        by_source.setdefault(mapping.asset_id, []).append(mapping)
    for source_id, rows in by_source.items():
        if abs(sum(row.share for row in rows) - 1.0) > 1e-9:
            raise ValueError(f"Zonal mappings for {source_id} do not sum to one")
    allocations: list[AgentZoneAllocation] = []
    sources: list[tuple[str, str, str, float, str, str, str]] = []
    for asset in state.assets:
        spatial_mapping_id = str(
            asset.extensions.get("spatial_mapping_asset_id") or ""
        )
        owner = str(
            asset.extensions.get("investment_owner_id")
            or asset.extensions.get("source_agent_id")
            or asset.asset_id
        )
        sources.append((
            asset.asset_id, "economic_asset", owner, asset.capacity_mw,
            asset.technology, "state_asset_capacity_mw",
            spatial_mapping_id
            or (asset.asset_id if asset.asset_id in by_source else owner),
        ))
    for project in state.planning_projects:
        spatial_mapping_id = str(
            project.extensions.get("spatial_mapping_asset_id") or ""
        )
        owner = str(
            project.extensions.get("investment_owner_id")
            or project.extensions.get("source_agent_id")
            or project.assigned_asset_id
            or f"force-owner:{project.technology}:{project.region}"
        )
        sources.append((
            project.project_id, "repd_project" if project.source == "repd" else "model_project",
            owner, project.capacity_mw, project.technology, "planning_project_capacity_mw",
            spatial_mapping_id
            or (project.project_id if project.project_id in by_source else owner),
        ))
    for source_id, kind, owner, capacity, technology, capacity_source, mapping_key in sources:
        rows = by_source.get(mapping_key, [])
        for mapping in sorted(rows, key=lambda item: item.zone_id):
            allocation_id = "allocation:" + _canonical_hash({
                "revision": pack_revision, "source_id": source_id,
                "zone_id": mapping.zone_id, "technology": technology, "owner": owner,
            })[:20]
            allocations.append(AgentZoneAllocation(
                allocation_id, owner, technology, source_id, kind, mapping.zone_id,
                float(capacity) * mapping.share, mapping.share,
                mapping.mapping_method, pack_revision, "MW", "direct MW",
                provenance={
                    "source": capacity_source,
                    "mapping_identity": mapping_key,
                    "zonal_asset_map_schema": mapping.schema_version,
                    "fixed_after_assignment": mapping.fixed_after_assignment,
                },
            ))
    return tuple(allocations)


def attach_spatial_metadata_from_pack(
    state: YearState,
    pack_root: Path,
    manifest: Mapping[str, object],
) -> YearState:
    """Attach a prebuilt map; never perform GIS or coordinate work at runtime."""

    bindings = manifest.get("bindings")
    if not isinstance(bindings, Mapping):
        return state
    binding = bindings.get("value.zonal.asset-map")
    if not isinstance(binding, Mapping):
        return state
    path = (Path(pack_root).resolve() / str(binding.get("uri") or "")).resolve()
    try:
        path.relative_to(Path(pack_root).resolve())
    except ValueError as exc:
        raise ValueError("Zonal asset-map binding escapes the data-pack root") from exc
    if not path.is_file():
        raise ValueError("Zonal asset-map binding is missing")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if str(binding.get("sha256") or "").lower() != actual:
        raise ValueError("Zonal asset-map SHA-256 does not match")
    payload = json.loads(path.read_text(encoding="utf-8"))
    mappings = tuple(
        ZonalAssetMapping.from_dict(item) for item in payload.get("asset_mappings", ())
    )
    identity = manifest.get("zonal_network_pack")
    revision = (
        str(identity.get("scientific_sha256") or identity.get("network_pack_id") or "")
        if isinstance(identity, Mapping) else str(manifest.get("revision") or manifest.get("id") or "")
    )
    if not revision:
        raise ValueError("Zonal asset map has no immutable pack revision")
    return attach_spatial_metadata(
        state, allocations_for_state(state, mappings, pack_revision=revision)
    )
