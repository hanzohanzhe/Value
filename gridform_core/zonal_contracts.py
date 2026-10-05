"""Immutable, solver-neutral contracts for VALUE zonal redispatch data.

The corridors in this contract are computational routing edges.  They are not
transmission-line records and deliberately carry no impedance or voltage data.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from .v2.contracts import JsonContract


ZONAL_PACK_SCHEMA = "value.zonal-network-pack/v1"
ZONAL_ROLES = (
    "value.zonal.zones",
    "value.zonal.corridors",
    "value.zonal.cutsets",
    "value.zonal.asset-map",
    "value.zonal.demand",
    "value.zonal.ratings",
    "value.zonal.interconnector-landings",
    "value.zonal.spatial-audit",
)


def _tuple(value: Sequence[object]) -> tuple[object, ...]:
    return tuple(value)


def _float_tuple(value: Sequence[float]) -> tuple[float, ...]:
    return tuple(float(item) for item in value)


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            result[str(key)] = _frozen_mapping(item)
        elif isinstance(item, (list, tuple)):
            result[str(key)] = tuple(item)
        else:
            result[str(key)] = item
    return MappingProxyType(result)


def _require_id(value: str, label: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{label} requires a stable non-blank ID")


def _finite_nonnegative(value: float, label: str) -> None:
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{label} cannot be negative or non-finite")


@dataclass(frozen=True)
class NetworkZone(JsonContract):
    zone_id: str
    display_name: str
    dso_owner: str
    nation: str
    is_unconstrained_fallback: bool = False
    geometry_feature_id: str | None = None
    island_reason: str | None = None
    schema_version: str = "value.network-zone/v1"

    def validate(self) -> None:
        _require_id(self.zone_id, "Network zone")
        if not self.display_name or not self.dso_owner:
            raise ValueError(f"Network zone {self.zone_id} lacks display name or DSO owner")
        if self.nation.strip().lower() in {"northern ireland", "northern_ireland", "ni"}:
            raise ValueError("Northern Ireland internal zones are outside the GB contract")


@dataclass(frozen=True)
class TransportCorridor(JsonContract):
    corridor_id: str
    from_zone_id: str
    to_zone_id: str
    positive_direction: str
    purpose: str = "computational_routing"
    schema_version: str = "value.transport-corridor/v1"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "TransportCorridor":
        forbidden_tokens = (
            "reactance", "resistance", "impedance", "voltage", "susceptance",
            "tap_ratio", "phase_shift", "physical_line", "thermal_rating",
        )
        forbidden = sorted(
            str(key) for key in payload
            if any(token in str(key).lower() for token in forbidden_tokens)
        )
        if forbidden:
            raise ValueError("Transport corridor rejects DC/AC field(s): " + ", ".join(forbidden))
        allowed = {
            "corridor_id", "from_zone_id", "to_zone_id", "positive_direction",
            "purpose", "schema_version",
        }
        unknown = sorted(set(payload).difference(allowed))
        if unknown:
            raise ValueError("Unknown transport-corridor fields: " + ", ".join(unknown))
        return super().from_dict(payload)

    def validate(self) -> None:
        _require_id(self.corridor_id, "Transport corridor")
        if self.from_zone_id == self.to_zone_id:
            raise ValueError(f"Transport corridor {self.corridor_id} is a self-loop")
        if self.positive_direction != "from_to_positive":
            raise ValueError(f"Transport corridor {self.corridor_id} has invalid positive direction")
        if self.purpose != "computational_routing":
            raise ValueError("Transport corridors must declare the computational routing purpose")


@dataclass(frozen=True)
class CutsetMember(JsonContract):
    corridor_id: str
    coefficient: int
    schema_version: str = "value.etys-cutset-member/v1"

    def validate(self) -> None:
        _require_id(self.corridor_id, "Cut-set member")
        if self.coefficient not in {-1, 1}:
            raise ValueError("Cut-set member coefficient must be +1 or -1")


@dataclass(frozen=True)
class ETYSBoundary(JsonContract):
    boundary_id: str
    display_name: str
    members: Sequence[CutsetMember]
    forward_limit_mw: float
    reverse_limit_mw: float
    rating_profile_id: str | None = None
    reverse_limit_method: str = "independent_source"
    schema_version: str = "value.etys-cutset/v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "members", tuple(self.members))

    def validate(self) -> None:
        _require_id(self.boundary_id, "ETYS boundary")
        if not self.members:
            raise ValueError(f"ETYS boundary {self.boundary_id} has an empty cut set")
        for member in self.members:
            member.validate()
        member_ids = [member.corridor_id for member in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError(f"ETYS boundary {self.boundary_id} has a duplicate signed member")
        _finite_nonnegative(self.forward_limit_mw, "Forward boundary rating")
        _finite_nonnegative(self.reverse_limit_mw, "Reverse boundary rating")
        if self.reverse_limit_method not in {
            "independent_source", "assumed_symmetric_from_forward", "source_declared_symmetric"
        }:
            raise ValueError(f"ETYS boundary {self.boundary_id} has an invalid reverse-limit method")


@dataclass(frozen=True)
class ZonalAssetMapping(JsonContract):
    asset_id: str
    zone_id: str
    asset_class: str
    technology: str
    share: float
    mapping_method: str
    fixed_after_assignment: bool = True
    schema_version: str = "value.zonal-asset-map/v1"

    def validate(self) -> None:
        _require_id(self.asset_id, "Zonal asset mapping")
        if self.asset_class not in {
            "generator", "storage", "boundary_interconnector", "demand", "flexibility"
        }:
            raise ValueError(f"Asset {self.asset_id} has an invalid class")
        if not math.isfinite(float(self.share)) or not 0 < float(self.share) <= 1:
            raise ValueError(f"Asset {self.asset_id} has an invalid zone share")
        if not self.fixed_after_assignment:
            raise ValueError(f"Asset {self.asset_id} zone assignment must remain fixed")


@dataclass(frozen=True)
class ZonalDemand(JsonContract):
    period_ids: Sequence[str]
    demand_mwh_by_zone: Mapping[str, Sequence[float]]
    national_demand_mwh: Sequence[float]
    reconciliation_tolerance_mwh: float = 1e-8
    schema_version: str = "value.zonal-demand/v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "period_ids", tuple(str(item) for item in self.period_ids))
        object.__setattr__(self, "demand_mwh_by_zone", MappingProxyType({
            str(key): _float_tuple(values) for key, values in self.demand_mwh_by_zone.items()
        }))
        object.__setattr__(self, "national_demand_mwh", _float_tuple(self.national_demand_mwh))

    def validate(self, zone_ids: set[str]) -> None:
        periods = len(self.period_ids)
        if not periods or len(set(self.period_ids)) != periods:
            raise ValueError("Zonal demand requires unique periods")
        if set(self.demand_mwh_by_zone) != zone_ids:
            raise ValueError("Zonal demand must name every and only declared zone")
        if len(self.national_demand_mwh) != periods:
            raise ValueError("National demand chronology length does not match period IDs")
        for zone, values in self.demand_mwh_by_zone.items():
            if len(values) != periods or any(not math.isfinite(value) or value < 0 for value in values):
                raise ValueError(f"Zonal demand for {zone} is invalid")
        for index, national in enumerate(self.national_demand_mwh):
            zonal = sum(values[index] for values in self.demand_mwh_by_zone.values())
            if abs(zonal - national) > self.reconciliation_tolerance_mwh:
                raise ValueError(
                    f"Zonal demand residual exceeds 1e-8 MWh at {self.period_ids[index]}: "
                    f"{zonal - national}"
                )


@dataclass(frozen=True)
class BoundaryRatingProfile(JsonContract):
    profile_id: str
    period_ids: Sequence[str]
    multipliers: Sequence[float]
    fixed_across_model_years: bool = True
    schema_version: str = "value.boundary-rating-profile/v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "period_ids", tuple(str(item) for item in self.period_ids))
        object.__setattr__(self, "multipliers", _float_tuple(self.multipliers))

    def validate(self, expected_periods: Sequence[str]) -> None:
        _require_id(self.profile_id, "Boundary rating profile")
        if tuple(self.period_ids) != tuple(expected_periods):
            raise ValueError(f"Rating profile {self.profile_id} uses a different clock")
        if len(self.multipliers) != len(self.period_ids):
            raise ValueError(f"Rating profile {self.profile_id} length is invalid")
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in self.multipliers):
            raise ValueError(f"Rating profile {self.profile_id} multiplier must be within 0..1")
        if not self.fixed_across_model_years:
            raise ValueError("Boundary rating profiles must be fixed across model years in v1")


@dataclass(frozen=True)
class InterconnectorLanding(JsonContract):
    interconnector_id: str
    asset_id: str
    zone_id: str
    envelope_semantics: str
    schema_version: str = "value.interconnector-landing/v1"

    def validate(self) -> None:
        _require_id(self.interconnector_id, "Interconnector landing")
        if self.envelope_semantics != "signed_profile_envelope":
            raise ValueError("Interconnector landing must preserve its signed profile envelope")


@dataclass(frozen=True)
class SpatialAudit(JsonContract):
    active_asset_ids: Sequence[str]
    capacity_mw_by_technology: Mapping[str, float]
    mapped_capacity_mw_by_technology: Mapping[str, float]
    tolerance_mw: float
    fallback_asset_ids: Sequence[str] = field(default_factory=tuple)
    excluded_northern_ireland_asset_ids: Sequence[str] = field(default_factory=tuple)
    source_sha256_by_role: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = "value.spatial-audit/v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_asset_ids", tuple(str(item) for item in self.active_asset_ids))
        object.__setattr__(self, "capacity_mw_by_technology", MappingProxyType({
            str(key): float(value) for key, value in self.capacity_mw_by_technology.items()
        }))
        object.__setattr__(self, "mapped_capacity_mw_by_technology", MappingProxyType({
            str(key): float(value) for key, value in self.mapped_capacity_mw_by_technology.items()
        }))
        object.__setattr__(self, "fallback_asset_ids", tuple(str(item) for item in self.fallback_asset_ids))
        object.__setattr__(self, "excluded_northern_ireland_asset_ids", tuple(
            str(item) for item in self.excluded_northern_ireland_asset_ids
        ))
        object.__setattr__(self, "source_sha256_by_role", MappingProxyType({
            str(key): str(value) for key, value in self.source_sha256_by_role.items()
        }))

    def validate(self) -> None:
        if self.tolerance_mw < 0 or not math.isfinite(self.tolerance_mw):
            raise ValueError("Spatial-audit tolerance is invalid")
        if len(self.active_asset_ids) != len(set(self.active_asset_ids)):
            raise ValueError("Spatial audit contains duplicate active assets")
        technologies = set(self.capacity_mw_by_technology) | set(self.mapped_capacity_mw_by_technology)
        for technology in technologies:
            source = self.capacity_mw_by_technology.get(technology, 0.0)
            mapped = self.mapped_capacity_mw_by_technology.get(technology, 0.0)
            _finite_nonnegative(source, f"{technology} source capacity")
            _finite_nonnegative(mapped, f"{technology} mapped capacity")
            if abs(source - mapped) > self.tolerance_mw:
                raise ValueError(
                    f"Spatial capacity reconciliation failed for {technology}: {source} versus {mapped}"
                )


@dataclass(frozen=True)
class ZonalNetworkPack(JsonContract):
    network_pack_id: str
    scientific_sha256: str
    zones: Sequence[NetworkZone]
    corridors: Sequence[TransportCorridor]
    cutsets: Sequence[ETYSBoundary]
    asset_mappings: Sequence[ZonalAssetMapping]
    zonal_demand: ZonalDemand
    rating_profiles: Sequence[BoundaryRatingProfile]
    interconnector_landings: Sequence[InterconnectorLanding]
    spatial_audit: SpatialAudit
    loss_capability_absent_reason: str
    geometry_artifact: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = ZONAL_PACK_SCHEMA

    def __post_init__(self) -> None:
        for name in ("zones", "corridors", "cutsets", "asset_mappings", "rating_profiles", "interconnector_landings"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "provenance", _frozen_mapping(self.provenance))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ZonalNetworkPack":
        return cls(
            network_pack_id=str(payload.get("network_pack_id") or ""),
            scientific_sha256=str(payload.get("scientific_sha256") or ""),
            zones=tuple(NetworkZone.from_dict(item) for item in payload.get("zones", ())),  # type: ignore[arg-type]
            corridors=tuple(TransportCorridor.from_dict(item) for item in payload.get("corridors", ())),  # type: ignore[arg-type]
            cutsets=tuple(ETYSBoundary.from_dict(item) for item in payload.get("cutsets", ())),  # type: ignore[arg-type]
            asset_mappings=tuple(ZonalAssetMapping.from_dict(item) for item in payload.get("asset_mappings", ())),  # type: ignore[arg-type]
            zonal_demand=ZonalDemand.from_dict(payload.get("zonal_demand", {})),  # type: ignore[arg-type]
            rating_profiles=tuple(BoundaryRatingProfile.from_dict(item) for item in payload.get("rating_profiles", ())),  # type: ignore[arg-type]
            interconnector_landings=tuple(InterconnectorLanding.from_dict(item) for item in payload.get("interconnector_landings", ())),  # type: ignore[arg-type]
            spatial_audit=SpatialAudit.from_dict(payload.get("spatial_audit", {})),  # type: ignore[arg-type]
            loss_capability_absent_reason=str(payload.get("loss_capability_absent_reason") or ""),
            geometry_artifact=(str(payload["geometry_artifact"]) if payload.get("geometry_artifact") else None),
            provenance=payload.get("provenance", {}),  # type: ignore[arg-type]
            schema_version=str(payload.get("schema_version") or ZONAL_PACK_SCHEMA),
        )

    def compute_scientific_sha256(self) -> str:
        payload = self.to_dict()
        payload["scientific_sha256"] = ""
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def validate(self) -> None:
        _require_id(self.network_pack_id, "Zonal network pack")
        if self.schema_version != ZONAL_PACK_SCHEMA:
            raise ValueError("Zonal network pack uses an incompatible schema")
        if self.loss_capability_absent_reason != "lossless_v1":
            raise ValueError("Zonal v1 must declare loss capability absent as lossless_v1")
        if not self.zones:
            raise ValueError("Zonal network pack has no zones")
        for zone in self.zones:
            zone.validate()
        zone_ids = [zone.zone_id for zone in self.zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("Zonal network pack contains a duplicate zone")
        known_zones = set(zone_ids)
        corridor_ids: list[str] = []
        adjacency = {zone_id: set() for zone_id in zone_ids}
        for corridor in self.corridors:
            corridor.validate()
            corridor_ids.append(corridor.corridor_id)
            if corridor.from_zone_id not in known_zones or corridor.to_zone_id not in known_zones:
                raise ValueError(f"Transport corridor {corridor.corridor_id} has a dangling endpoint")
            adjacency[corridor.from_zone_id].add(corridor.to_zone_id)
            adjacency[corridor.to_zone_id].add(corridor.from_zone_id)
        if len(corridor_ids) != len(set(corridor_ids)):
            raise ValueError("Zonal network pack contains a duplicate corridor")
        if len(zone_ids) > 1:
            visited: set[str] = set()
            stack = [zone_ids[0]]
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                stack.extend(adjacency[current].difference(visited))
            unexplained = [
                zone for zone in self.zones
                if zone.zone_id not in visited and not zone.is_unconstrained_fallback and not zone.island_reason
            ]
            if unexplained:
                raise ValueError("Zonal network pack has a disconnected unexplained zone")
        known_corridors = set(corridor_ids)
        boundary_ids: list[str] = []
        for boundary in self.cutsets:
            boundary.validate()
            boundary_ids.append(boundary.boundary_id)
            unknown = {member.corridor_id for member in boundary.members}.difference(known_corridors)
            if unknown:
                raise ValueError(f"ETYS boundary {boundary.boundary_id} has unknown corridors: {sorted(unknown)}")
        if len(boundary_ids) != len(set(boundary_ids)):
            raise ValueError("Zonal network pack contains a duplicate ETYS boundary")
        profile_ids = [profile.profile_id for profile in self.rating_profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("Zonal network pack contains a duplicate rating profile")
        for profile in self.rating_profiles:
            profile.validate(self.zonal_demand.period_ids)
        known_profiles = set(profile_ids)
        for boundary in self.cutsets:
            if boundary.rating_profile_id and boundary.rating_profile_id not in known_profiles:
                raise ValueError(f"ETYS boundary {boundary.boundary_id} has an unknown rating profile")
        self.zonal_demand.validate(known_zones)
        share_by_asset: dict[str, float] = {}
        for mapping in self.asset_mappings:
            mapping.validate()
            if mapping.zone_id not in known_zones:
                raise ValueError(f"Asset {mapping.asset_id} maps to an unknown zone")
            share_by_asset[mapping.asset_id] = share_by_asset.get(mapping.asset_id, 0.0) + mapping.share
        missing = sorted(set(self.spatial_audit.active_asset_ids).difference(share_by_asset))
        if missing:
            raise ValueError("Zonal mapping is missing active assets: " + ", ".join(missing))
        invalid_shares = {asset: value for asset, value in share_by_asset.items() if abs(value - 1.0) > 1e-9}
        if invalid_shares:
            raise ValueError(f"Zonal asset share reconciliation failed: {invalid_shares}")
        landing_ids: list[str] = []
        landing_assets: list[str] = []
        for landing in self.interconnector_landings:
            landing.validate()
            landing_ids.append(landing.interconnector_id)
            landing_assets.append(landing.asset_id)
            if landing.zone_id not in known_zones:
                raise ValueError(f"Interconnector {landing.interconnector_id} has an unknown landing zone")
            matching = [item for item in self.asset_mappings if item.asset_id == landing.asset_id]
            if len(matching) != 1 or matching[0].asset_class != "boundary_interconnector":
                raise ValueError(f"Interconnector {landing.interconnector_id} lacks one boundary mapping")
        if len(landing_ids) != len(set(landing_ids)) or len(landing_assets) != len(set(landing_assets)):
            raise ValueError("Interconnector landing is double counted")
        if set(landing_assets).intersection(known_corridors):
            raise ValueError("Interconnector is double counted as an internal corridor")
        self.spatial_audit.validate()
        if self.scientific_sha256 != self.compute_scientific_sha256():
            raise ValueError("Zonal network pack scientific SHA-256 identity does not match")


def _binding_path(pack_root: Path, binding: Mapping[str, object]) -> Path:
    path = (pack_root / str(binding.get("uri") or "")).resolve()
    try:
        path.relative_to(pack_root.resolve())
    except ValueError as exc:
        raise ValueError("Zonal binding path escapes the pack root") from exc
    if not path.is_file():
        raise ValueError(f"Zonal binding is missing: {path}")
    expected = str(binding.get("sha256") or "").lower()
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected != actual:
        raise ValueError(f"Zonal binding SHA-256 mismatch: {path.name}")
    return path


def load_zonal_network_pack(
    pack_root: Path,
    manifest: Mapping[str, object] | None = None,
    *,
    topology_policy: str,
) -> ZonalNetworkPack:
    """Load and validate the eight required zonal roles without runtime downloads.

    ``topology_policy`` is required (P0-8 S11): ``"enforce"`` rejects a pack
    whose boundaries are not the cuts they claim to be
    (:func:`classify_cutsets`); ``"audit"`` only reads (historical Runs,
    recovery and import review), and callers obtain the classification from
    :func:`audit_zonal_network_topology`.
    """

    pack, _report = _load_zonal_network_pack(pack_root, manifest, topology_policy=topology_policy)
    return pack


def audit_zonal_network_topology(
    pack_root: Path, manifest: Mapping[str, object] | None = None
) -> tuple[ZonalNetworkPack, dict[str, object]]:
    """Load a pack read-only and return its derived cut-set classification."""

    return _load_zonal_network_pack(pack_root, manifest, topology_policy="audit")


def _load_zonal_network_pack(
    pack_root: Path,
    manifest: Mapping[str, object] | None,
    *,
    topology_policy: str,
) -> tuple[ZonalNetworkPack, dict[str, object]]:
    if topology_policy not in TOPOLOGY_POLICIES:
        raise ValueError(f"topology_policy must be one of {TOPOLOGY_POLICIES}")
    pack_root = Path(pack_root).resolve()
    if manifest is None:
        manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    bindings = manifest.get("bindings")
    if not isinstance(bindings, Mapping):
        raise ValueError("Zonal data pack has no bindings")
    payloads: dict[str, Mapping[str, object]] = {}
    hashes: dict[str, str] = {}
    for role in ZONAL_ROLES:
        binding = bindings.get(role)
        if not isinstance(binding, Mapping):
            raise ValueError(f"Required zonal role is not bound: {role}")
        path = _binding_path(pack_root, binding)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, Mapping):
            raise ValueError(f"Zonal role {role} must contain a JSON object")
        payloads[role] = loaded
        hashes[role] = str(binding["sha256"])
    identity = manifest.get("zonal_network_pack")
    if not isinstance(identity, Mapping):
        raise ValueError("Manifest lacks zonal_network_pack immutable identity")
    audit_payload = dict(payloads["value.zonal.spatial-audit"])
    audit_payload["source_sha256_by_role"] = hashes
    pack = ZonalNetworkPack(
        network_pack_id=str(identity.get("network_pack_id") or ""),
        scientific_sha256=str(identity.get("scientific_sha256") or ""),
        zones=tuple(NetworkZone.from_dict(item) for item in payloads["value.zonal.zones"].get("zones", ())),  # type: ignore[arg-type]
        corridors=tuple(TransportCorridor.from_dict(item) for item in payloads["value.zonal.corridors"].get("corridors", ())),  # type: ignore[arg-type]
        cutsets=tuple(ETYSBoundary.from_dict(item) for item in payloads["value.zonal.cutsets"].get("cutsets", ())),  # type: ignore[arg-type]
        asset_mappings=tuple(ZonalAssetMapping.from_dict(item) for item in payloads["value.zonal.asset-map"].get("asset_mappings", ())),  # type: ignore[arg-type]
        zonal_demand=ZonalDemand.from_dict(payloads["value.zonal.demand"].get("zonal_demand", {})),  # type: ignore[arg-type]
        rating_profiles=tuple(BoundaryRatingProfile.from_dict(item) for item in payloads["value.zonal.ratings"].get("rating_profiles", ())),  # type: ignore[arg-type]
        interconnector_landings=tuple(InterconnectorLanding.from_dict(item) for item in payloads["value.zonal.interconnector-landings"].get("interconnector_landings", ())),  # type: ignore[arg-type]
        spatial_audit=SpatialAudit.from_dict(audit_payload),
        loss_capability_absent_reason=str(identity.get("loss_capability_absent_reason") or ""),
        geometry_artifact=(str(identity["geometry_artifact"]) if identity.get("geometry_artifact") else None),
        provenance=identity.get("provenance", {}),  # type: ignore[arg-type]
    )
    pack.validate()
    report = classify_cutsets(
        pack, tuple(payloads["value.zonal.cutsets"].get("cutsets", ()))  # type: ignore[arg-type]
    )
    report["topology_policy"] = topology_policy
    if topology_policy == "enforce" and report["error_count"]:
        raise ZonalTopologyError(report)
    return pack, report


def pack_fallback_assets(pack: ZonalNetworkPack) -> dict[str, object]:
    """Assets the pack itself places in an unconstrained fallback zone (P2-13).

    Read-only preflight evidence; the run-time audit
    (``staged_psm.runtime_fallback_audit``) must report the same assets with
    allocation source ``pack_mapping``.
    """

    fallback = sorted(zone.zone_id for zone in pack.zones if zone.is_unconstrained_fallback)
    rows = sorted(
        (
            {
                "asset_id": mapping.asset_id,
                "technology": mapping.technology,
                "zone_id": mapping.zone_id,
                "share": float(mapping.share),
                "mapping_method": mapping.mapping_method,
            }
            for mapping in pack.asset_mappings
            if mapping.zone_id in fallback and mapping.asset_class != "demand"
        ),
        key=lambda row: (str(row["technology"]), str(row["asset_id"])),
    )
    return {"fallback_zone_ids": fallback, "assets": rows}


# --------------------------------------------------------------------------
# Cut-set classification (P0-8 S11, findings P1-05 / P2-15)
# --------------------------------------------------------------------------

TOPOLOGY_POLICIES = ("enforce", "audit")
CUTSET_CLASSIFICATION_SCHEMA = "value.zonal-cutset-classification/v1"


class ZonalTopologyError(ValueError):
    """A declared boundary is not the graph cut it claims to be."""

    def __init__(self, report: Mapping[str, object]) -> None:
        self.report = dict(report)
        errors = [
            f"{row['boundary_id']}: {', '.join(row['errors'])}"
            for row in report.get("boundaries", ())  # type: ignore[union-attr]
            if row.get("errors")
        ]
        super().__init__("Zonal cut sets are invalid: " + "; ".join(errors))


def _components(zone_ids: Sequence[str], edges: Sequence[tuple[str, str]]) -> dict[str, int]:
    adjacency: dict[str, set[str]] = {zone: set() for zone in zone_ids}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    label: dict[str, int] = {}
    for start in zone_ids:
        if start in label:
            continue
        index = len(set(label.values()))
        stack = [start]
        while stack:
            zone = stack.pop()
            if zone in label:
                continue
            label[zone] = index
            stack.extend(adjacency[zone].difference(label))
    return label


def classify_cutsets(
    pack: ZonalNetworkPack,
    raw_cutsets: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Classify every boundary as a declared-partition cut, a cut or a corridor limit.

    * A boundary that declares ``positive_side_zone_ids`` /
      ``negative_side_zone_ids`` (raw cut-set rows; the contract does not
      carry them, so the pack hash is unchanged) must be exactly the set of
      corridors crossing that partition, every member oriented from the
      positive to the negative side: otherwise ``partition_mismatch``,
      ``bypass`` (a non-member corridor crosses, including through an
      unconstrained fallback zone) or ``orientation_conflict``.
    * An undeclared multi-member boundary must be a graph cut: removing its
      members separates the positive side S (from-zone of a +1 member, or
      to-zone of a -1 member) from every member's other end, with consistent
      signs; otherwise ``not_a_cut`` / ``orientation_conflict``.
    * An undeclared single-member boundary that is not a cut is a
      ``corridor_limit`` (a rating on one corridor, e.g. Western Link or a
      thermal AC limit): accepted and labelled, never treated as an ETYS
      boundary.

    The result is derived data; it never changes the pack or its hash.
    """

    zone_ids = [zone.zone_id for zone in pack.zones]
    corridors = {corridor.corridor_id: corridor for corridor in pack.corridors}
    raw_by_id = {
        str(row.get("boundary_id")): row for row in (raw_cutsets or ()) if isinstance(row, Mapping)
    }
    rows: list[dict[str, object]] = []
    for boundary in pack.cutsets:
        members = {member.corridor_id: int(member.coefficient) for member in boundary.members}
        raw = raw_by_id.get(boundary.boundary_id, {})
        positive = raw.get("positive_side_zone_ids")
        negative = raw.get("negative_side_zone_ids")
        errors: list[str] = []
        declared = isinstance(positive, (list, tuple)) and isinstance(negative, (list, tuple))
        side: set[str]
        if declared:
            side = {str(zone) for zone in positive}  # type: ignore[union-attr]
            other = {str(zone) for zone in negative}  # type: ignore[union-attr]
            if side & other or (side | other) != set(zone_ids):
                errors.append("partition_mismatch")
        else:
            # Remove the members; each remaining component must lie wholly on
            # one side.  A +1 member runs from the positive side S to the
            # other side, a -1 member the reverse; the sides of the touched
            # components follow from the members (a component may be a single
            # zone that only the members connected).
            remaining = [
                (corridor.from_zone_id, corridor.to_zone_id)
                for corridor_id, corridor in corridors.items()
                if corridor_id not in members
            ]
            label = _components(zone_ids, remaining)
            component_side: dict[int, bool] = {}
            separable = True
            for corridor_id, coefficient in members.items():
                corridor = corridors[corridor_id]
                origin, target = label[corridor.from_zone_id], label[corridor.to_zone_id]
                if origin == target:
                    separable = False
                    continue
                for component, value in ((origin, coefficient > 0), (target, coefficient < 0)):
                    if component_side.setdefault(component, value) != value:
                        errors.append("orientation_conflict")
            side = {zone for zone in zone_ids if component_side.get(label[zone]) is True}
            if not separable:
                errors.append("not_a_cut")
        crossing = {
            corridor_id
            for corridor_id, corridor in corridors.items()
            if (corridor.from_zone_id in side) != (corridor.to_zone_id in side)
        }
        member_ids = set(members)
        oriented = all(
            (corridors[corridor_id].from_zone_id in side) == (coefficient > 0)
            for corridor_id, coefficient in members.items()
            if corridor_id in crossing
        )
        if declared:
            if member_ids - crossing:
                errors.append("partition_mismatch")
            if crossing - member_ids:
                errors.append("bypass")
            if not oriented:
                errors.append("orientation_conflict")
            kind = "declared_partition_cut"
        else:
            if "not_a_cut" not in errors and (member_ids - crossing or crossing - member_ids):
                errors.append("not_a_cut")
            if not errors:
                kind = "cut"
            elif len(members) == 1 and errors == ["not_a_cut"]:
                kind = "corridor_limit"
                errors = []
            elif "not_a_cut" in errors:
                kind = "not_a_cut"
            else:
                kind = "cut"
        rows.append({
            "boundary_id": boundary.boundary_id,
            "classification": kind,
            "member_count": len(members),
            "partition_declared": declared,
            "positive_side_zone_ids": sorted(side) if kind != "corridor_limit" else [],
            "bypass_corridor_ids": sorted(crossing - member_ids) if kind != "corridor_limit" else [],
            "errors": sorted(set(errors)),
        })
    return {
        "schema_version": CUTSET_CLASSIFICATION_SCHEMA,
        "network_pack_id": pack.network_pack_id,
        "scientific_sha256": pack.scientific_sha256,
        "boundaries": rows,
        "error_count": sum(len(row["errors"]) for row in rows),  # type: ignore[arg-type]
        "counts": {
            kind: sum(1 for row in rows if row["classification"] == kind)
            for kind in ("declared_partition_cut", "cut", "corridor_limit", "not_a_cut")
        },
    }
