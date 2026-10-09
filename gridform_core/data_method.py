"""Data-method policy and the one place that reads a pack's chronological roles (P0-5a S3/S4).

``DataMethodPolicy`` is derived from the run's methodology profile (only
through ``ResolvedMethodology.enabled``, C15) and the pack's ``pack_class``:

* the reading mode (``legacy-v1`` frozen; ``declared-v2`` when
  ``p05.declared-reader`` is in force),
* the clock (frozen; declared resolution when ``p05.series-clock`` is in force),
* the strictness (strict except for user workspaces, lenient in legacy mode),
* whether registry-identified data defects and chronology findings block a
  run (``p05.data-gate``).

The universal corrections (declared ``csv_column``, the registry repairs of
P6-02/P6-03/P6-04, the interconnector line identity) are applied in every
policy.  ``read_role`` and ``read_boundary`` are used by the canonical adapter,
the retained kernel's boundary injection and the validator alike.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import series_reader as sr
from .interconnector_identity import COUNTRIES, BoundaryIdentityError, resolve_profile_roles

SCHEMA_VERSION = "value.data-method/v1"
DECLARED_READER = "p05.declared-reader"
SERIES_CLOCK = "p05.series-clock"
DATA_GATE = "p05.data-gate"
UNIVERSAL_CORRECTIONS = (
    "p05.declared-column",
    "p05.belgium-price-currency",
    "p05.boundary-identity",
    "p05.demand-utc-clock",
    "p05.interconnector-clock",
)
DEMAND_ROLES = ("demand.real", "demand.forecast")
VRE_PROFILE_ROLES = ("profiles.vre_solar", "profiles.vre_onshore", "profiles.vre_offshore")
PROFILE_ROLE = "market.{}.profile"
PRICE_ROLE = "market.{}.price"
# 35aadb3 reader settings per role kind: (pandas header, hourly repeat, cyclic).
LEGACY_SETTINGS = {
    "demand": (0, False, False),
    "vre_profile": (None, True, False),
    "market_profile": (0, False, True),
    "market_price": (None, False, True),
}
PLAUSIBILITY_PATH = Path(__file__).resolve().parent / "data" / "validation" / "value_data_plausibility_v1.json"


def role_kind(role: str) -> str:
    if role in DEMAND_ROLES:
        return "demand"
    if role in VRE_PROFILE_ROLES:
        return "vre_profile"
    if role.startswith("market.") and role.endswith(".profile"):
        return "market_profile"
    if role.startswith("market.") and role.endswith(".price"):
        return "market_price"
    raise ValueError(f"{role} is not a chronological series role")


@dataclass(frozen=True)
class DataMethodPolicy:
    profile_id: str
    pack_class: str
    reader_mode: str
    clock_mode: str
    strictness: str
    fail_closed: bool
    universal_corrections: tuple[str, ...] = UNIVERSAL_CORRECTIONS

    @property
    def data_method_id(self) -> str:
        return f"value.data-method/{self.reader_mode}+{self.clock_mode}+{self.strictness}"

    def method_ids(self) -> dict[str, str]:
        return {
            "reader": sr.READER_METHOD_IDS[self.reader_mode],
            "clock": sr.CLOCK_METHOD_IDS[self.clock_mode],
            "data_method": self.data_method_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "profile_id": self.profile_id,
            "pack_class": self.pack_class,
            "reader_mode": self.reader_mode,
            "clock_mode": self.clock_mode,
            "strictness": self.strictness,
            "fail_closed": self.fail_closed,
            "universal_corrections": list(self.universal_corrections),
            "method_ids": self.method_ids(),
        }


def classify_pack(manifest: Mapping[str, object]) -> str:
    from .methodology import classify_data_pack

    return classify_data_pack(manifest)


def policy_for(methodology: Any, manifest: Mapping[str, object]) -> DataMethodPolicy:
    """The policy of ``methodology`` (a ResolvedMethodology) on this pack."""

    pack_class = classify_pack(manifest)
    declared = bool(methodology.enabled("p05.declared-reader"))
    clock = bool(methodology.enabled("p05.series-clock"))
    gate = bool(methodology.enabled("p05.data-gate"))
    reader_mode = sr.DECLARED if declared else sr.LEGACY
    strictness = sr.STRICT if declared and pack_class != "user_workspace" else sr.LENIENT
    return DataMethodPolicy(
        profile_id=str(methodology.profile_id), pack_class=pack_class, reader_mode=reader_mode,
        clock_mode=sr.DECLARED if clock else sr.LEGACY, strictness=strictness, fail_closed=gate,
    )


def policy_for_profile(profile_id: str | None, manifest: Mapping[str, object]) -> DataMethodPolicy:
    from .methodology import resolve_methodology

    return policy_for(resolve_methodology(profile_id), manifest)


def project_policy(project: Mapping[str, object], manifest: Mapping[str, object]) -> DataMethodPolicy:
    """The policy of a Study's selected profile (preflight, previews: no run is active)."""

    from .methodology import resolve_project_methodology

    return policy_for(resolve_project_methodology(project), manifest)


def current_policy(manifest: Mapping[str, object]) -> DataMethodPolicy:
    """The policy of the active methodology (inside a run or a profile scope)."""

    from .methodology import current_methodology

    return policy_for(current_methodology(), manifest)


def run_policy(manifest: Mapping[str, object]) -> DataMethodPolicy:
    """The active methodology's policy; outside any run, the frozen reference reading.

    Every Run activates its methodology (``run_project_application``), so the
    fallback only serves direct library calls (fixtures, scripts): they get
    the 35aadb3 reading plus the universal corrections, never a silently
    corrected one.
    """

    from .methodology import REFERENCE_PROFILE_ID, active_methodology, resolve_methodology

    return policy_for(active_methodology() or resolve_methodology(REFERENCE_PROFILE_ID), manifest)


def binding_path(pack_root: Path, manifest: Mapping[str, object], role: str) -> Path:
    binding = dict(manifest.get("bindings") or {}).get(role)  # type: ignore[arg-type]
    if not isinstance(binding, Mapping):
        raise ValueError(f"Canonical role is not bound: {role}")
    root = Path(pack_root).resolve()
    path = (root / str(binding.get("uri") or "")).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Canonical binding escapes the pack root: {role}") from exc
    if not path.is_file():
        raise ValueError(f"Canonical binding is missing: {role}")
    return path


@dataclass(frozen=True)
class RoleSeries:
    role: str
    path: Path
    spec: sr.SeriesSpec
    read: sr.SeriesRead
    values: np.ndarray            # on the run clock
    sha256: str                   # of the source file
    registry: Mapping[str, Any] | None = None

    def evidence(self) -> dict[str, object]:
        return {
            "file_sha256": self.sha256,
            "column": self.read.column,
            "transforms": list(self.read.transforms),
            "warnings": list(self.read.warnings),
            "correction_ids": list(self.read.correction_ids),
            **({"registry_object": self.spec.registry_object} if self.spec.registry_object else {}),
        }


def read_role(
    pack_root: Path, manifest: Mapping[str, object], role: str, policy: DataMethodPolicy, *,
    periods: int, path: Path | None = None, spec_role: str | None = None,
) -> RoleSeries:
    """Read one chronological role through the shared reader and put it on the run clock."""

    path = path or binding_path(pack_root, manifest, role)
    binding = dict(dict(manifest.get("bindings") or {}).get(spec_role or role) or {})  # type: ignore[arg-type]
    if path != binding_path(pack_root, manifest, spec_role or role):
        binding = {}
    registry = sr.registry_entry(path, binding or None)
    spec = sr.SeriesSpec.from_binding(spec_role or role, binding, registry=registry)
    header, hourly_repeat, cyclic = LEGACY_SETTINGS[role_kind(role)]
    read = sr.read_series(path, spec, mode=policy.reader_mode, strictness=policy.strictness, legacy_header=header)
    values = sr.align_clock(read.values, periods, spec, mode=policy.clock_mode, strictness=policy.strictness,
                            hourly_repeat=hourly_repeat, cyclic_default=cyclic)
    return RoleSeries(role, path, spec, read, values, sr.verified_sha256(path), registry)


@dataclass(frozen=True)
class BoundaryCountry:
    country: str
    flow: RoleSeries          # signed MW, positive = import to GB (source convention)
    price: RoleSeries         # GBP/MWh, unclipped

    @property
    def flow_mw(self) -> np.ndarray:
        return self.flow.values

    @property
    def price_gbp_per_mwh(self) -> np.ndarray:
        return self.price.values


@dataclass(frozen=True)
class Boundary:
    countries: Mapping[str, BoundaryCountry]
    identity: tuple[Mapping[str, object], ...] = field(default_factory=tuple)

    def series_sha256(self) -> str:
        digest = hashlib.sha256()
        for country in COUNTRIES:
            entry = self.countries[country]
            digest.update(country.encode("utf-8"))
            digest.update(np.asarray(entry.flow_mw, dtype="<f8").tobytes())
            digest.update(np.asarray(entry.price_gbp_per_mwh, dtype="<f8").tobytes())
        return digest.hexdigest()

    def evidence(self) -> dict[str, object]:
        return {
            "boundary_series_sha256": self.series_sha256(),
            "line_identity": [dict(item) for item in self.identity],
            "roles": {
                country: {"profile": entry.flow.evidence() | {"role": entry.flow.role},
                          "price": entry.price.evidence() | {"role": entry.price.role}}
                for country, entry in sorted(self.countries.items())
            },
        }


def read_boundary(pack_root: Path, manifest: Mapping[str, object], policy: DataMethodPolicy, *,
                  periods: int) -> Boundary:
    """Signed flows and raw prices of the five boundary countries on the run clock.

    The flow file of each country is found by line identity (P6-03), so a
    file bound under another country's role is used for its own line.
    """

    resolved, identity = resolve_profile_roles(
        pack_root, manifest, lambda role: binding_path(pack_root, manifest, role)
    )
    countries = {}
    for country in COUNTRIES:
        profile_role = resolved[country]
        flow = read_role(pack_root, manifest, PROFILE_ROLE.format(country), policy, periods=periods,
                         path=binding_path(pack_root, manifest, profile_role), spec_role=profile_role)
        price = read_role(pack_root, manifest, PRICE_ROLE.format(country), policy, periods=periods)
        countries[country] = BoundaryCountry(country, flow, price)
    return Boundary(countries, tuple(identity))


def chronology_extension(policy: DataMethodPolicy, series: Mapping[str, RoleSeries],
                         boundary: Boundary | None) -> dict[str, object]:
    """``chronology.extensions['data_method']``: profile, method ids and file sha of every read role."""

    corrections = sorted({item for entry in series.values() for item in entry.read.correction_ids}
                         | ({item for country in (boundary.countries.values() if boundary else ())
                             for item in (*country.flow.read.correction_ids, *country.price.read.correction_ids)}))
    if boundary is not None and any(item.get("rebound") for item in boundary.identity):
        corrections = sorted({*corrections, "p05.boundary-identity"})
    return {
        **policy.to_dict(),
        "files": {role: entry.sha256 for role, entry in sorted(series.items())},
        "applied_reading_corrections": corrections,
        "roles": {role: entry.evidence() for role, entry in sorted(series.items())},
    }


def load_plausibility() -> dict[str, Any]:
    payload = json.loads(PLAUSIBILITY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "value.data-plausibility/v1":
        raise ValueError("value_data_plausibility_v1.json has an unexpected schema_version")
    return payload


__all__ = [
    "BoundaryIdentityError", "Boundary", "BoundaryCountry", "DataMethodPolicy", "RoleSeries",
    "binding_path", "chronology_extension", "classify_pack", "current_policy", "load_plausibility",
    "policy_for", "policy_for_profile", "project_policy", "run_policy", "read_boundary", "read_role", "role_kind",
]
