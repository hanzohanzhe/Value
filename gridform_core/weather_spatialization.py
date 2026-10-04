"""Offline weather preprocessing for zonal VALUE resource tranches."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Mapping, Sequence

from .spatialization import AgentZoneAllocation
from .v2.contracts import JsonContract


PROFILE_SCHEMA = "value.zonal-availability-profile/v1"


def _hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


def _profile(values: Sequence[float], periods: int, label: str) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != periods:
        raise ValueError(f"Weather profile {label} uses a different clock")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in result):
        raise ValueError(f"Weather profile {label} must be within 0..1")
    return result


@dataclass(frozen=True)
class ZonalAvailabilityProfile(JsonContract):
    profile_id: str
    economic_owner_id: str
    technology: str
    zone_id: str
    period_ids: Sequence[str]
    availability: Sequence[float]
    aggregated_capacity_mw: float
    source_ids: Sequence[str]
    aggregation_method: str
    source_sha256: str
    schema_version: str = PROFILE_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "period_ids", tuple(str(item) for item in self.period_ids))
        object.__setattr__(self, "availability", tuple(float(item) for item in self.availability))
        object.__setattr__(self, "source_ids", tuple(str(item) for item in self.source_ids))

    def validate(self) -> None:
        if not all((self.profile_id, self.economic_owner_id, self.technology, self.zone_id)):
            raise ValueError("Zonal availability profile has a blank identity")
        _profile(self.availability, len(self.period_ids), self.profile_id)
        if not math.isfinite(self.aggregated_capacity_mw) or self.aggregated_capacity_mw <= 0:
            raise ValueError(f"Zonal availability profile {self.profile_id} has invalid MW")
        if not self.source_sha256:
            raise ValueError(f"Zonal availability profile {self.profile_id} has no source identity")


@dataclass(frozen=True)
class ZonalAvailabilityBundle(JsonContract):
    mode: str
    period_ids: Sequence[str]
    profiles: Sequence[ZonalAvailabilityProfile]
    source_sha256: str
    runtime_opens_repd_or_era5: bool = False
    scientific_sha256: str = ""
    schema_version: str = "value.zonal-availability-bundle/v1"
    provenance: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "period_ids", tuple(str(item) for item in self.period_ids))
        object.__setattr__(self, "profiles", tuple(self.profiles))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    def compute_scientific_sha256(self) -> str:
        payload = self.to_dict()
        payload["scientific_sha256"] = ""
        return _hash(payload)

    def validate(self) -> None:
        if self.mode not in {"representative_point", "repd_era5_mw_aggregated"}:
            raise ValueError("Unknown zonal weather preprocessing mode")
        if self.runtime_opens_repd_or_era5:
            raise ValueError("Runtime must not open raw REPD or ERA5 data per bidder")
        keys = []
        for row in self.profiles:
            row.validate()
            if tuple(row.period_ids) != tuple(self.period_ids):
                raise ValueError("Aggregated weather profiles use inconsistent clocks")
            keys.append((row.economic_owner_id, row.technology, row.zone_id))
        if len(keys) != len(set(keys)):
            raise ValueError("Weather bundle contains duplicate agent-technology-zone profiles")
        if self.scientific_sha256 != self.compute_scientific_sha256():
            raise ValueError("Zonal availability scientific identity does not match")


def _groups(
    allocations: Sequence[AgentZoneAllocation],
) -> dict[tuple[str, str, str], list[AgentZoneAllocation]]:
    result: dict[tuple[str, str, str], list[AgentZoneAllocation]] = {}
    for row in allocations:
        row.validate()
        result.setdefault(
            (row.economic_owner_id, row.technology, row.zone_id), []
        ).append(row)
    return result


def _finish(
    mode: str,
    period_ids: Sequence[str],
    profiles: Sequence[ZonalAvailabilityProfile],
    source_sha256: str,
    provenance: Mapping[str, object],
) -> ZonalAvailabilityBundle:
    bundle = ZonalAvailabilityBundle(
        mode, tuple(period_ids), tuple(profiles), source_sha256,
        runtime_opens_repd_or_era5=False, provenance=provenance,
    )
    bundle = replace(bundle, scientific_sha256=bundle.compute_scientific_sha256())
    bundle.validate()
    return bundle


class RepresentativePointWeather:
    """Copy one declared VALUE representative trace to each physical tranche."""

    id = "value-representative-point-weather"

    @staticmethod
    def build(
        allocations: Sequence[AgentZoneAllocation],
        *,
        period_ids: Sequence[str],
        profiles_by_agent_technology: Mapping[str, Sequence[float]],
        source_sha256: str,
    ) -> ZonalAvailabilityBundle:
        periods = tuple(str(item) for item in period_ids)
        profiles: list[ZonalAvailabilityProfile] = []
        for (owner, technology, zone), rows in sorted(_groups(allocations).items()):
            key = f"{owner}|{technology}"
            if key not in profiles_by_agent_technology:
                raise ValueError(f"Representative weather is missing {key}")
            values = _profile(profiles_by_agent_technology[key], len(periods), key)
            profiles.append(ZonalAvailabilityProfile(
                f"representative:{owner}:{technology}:{zone}", owner, technology, zone,
                periods, values, sum(row.capacity_mw for row in rows),
                tuple(sorted({row.source_id for row in rows})),
                "copied_representative_agent_trace", source_sha256,
            ))
        return _finish(
            "representative_point", periods, profiles, source_sha256,
            {"location_indexing": "not_used", "runtime_inputs": "aggregated_profiles_only"},
        )


class REPDERA5AggregatedWeather:
    """MW-weight REPD-location profiles offline by agent, technology and zone."""

    id = "value-repd-era5-aggregated-weather"

    @staticmethod
    def build(
        allocations: Sequence[AgentZoneAllocation],
        *,
        period_ids: Sequence[str],
        profiles_by_source: Mapping[str, Sequence[float]],
        source_sha256: str,
    ) -> ZonalAvailabilityBundle:
        periods = tuple(str(item) for item in period_ids)
        profiles: list[ZonalAvailabilityProfile] = []
        for (owner, technology, zone), rows in sorted(_groups(allocations).items()):
            total = sum(row.capacity_mw for row in rows)
            if total <= 0:
                raise ValueError(f"ERA5 aggregation group {owner}/{technology}/{zone} has no MW")
            weighted = [0.0] * len(periods)
            for row in rows:
                if row.source_id not in profiles_by_source:
                    raise ValueError(f"ERA5 profile is missing source {row.source_id}")
                values = _profile(profiles_by_source[row.source_id], len(periods), row.source_id)
                for index, value in enumerate(values):
                    weighted[index] += value * row.capacity_mw / total
            profiles.append(ZonalAvailabilityProfile(
                f"repd-era5:{owner}:{technology}:{zone}", owner, technology, zone,
                periods, tuple(weighted), total,
                tuple(sorted({row.source_id for row in rows})),
                "offline_repd_location_era5_mw_weighted", source_sha256,
            ))
        return _finish(
            "repd_era5_mw_aggregated", periods, profiles, source_sha256,
            {
                "location_indexing": "offline_repd_coordinates",
                "aggregation": "MW_weighted_agent_technology_zone",
                "runtime_inputs": "aggregated_profiles_only",
            },
        )
