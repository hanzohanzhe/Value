"""Immutable, content-addressed contexts delivered to VALUE market modules."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from threading import RLock
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence

from .v2.contracts import JsonContract


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TRACE_PROFILES = {"off", "summary", "full"}


def _freeze_json(value: object) -> object:
    if isinstance(value, MappingABC):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Context JSON object keys must be strings")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Context JSON values must be finite")
        return value
    raise ValueError("Context values must be JSON scalars, mappings or sequences")


def _freeze_fields(instance: object, *names: str) -> None:
    for name in names:
        object.__setattr__(instance, name, _freeze_json(getattr(instance, name)))


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _require_year(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1900 <= value <= 3000:
        raise ValueError(f"{name} must be a valid model year")


def _require_finite(name: str, value: object, *, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _require_mapping(name: str, value: object) -> None:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{name} must be a mapping")


def _require_numeric_mapping(name: str, value: Mapping[str, object], *, minimum: float | None = None) -> None:
    for key, item in value.items():
        _require_text(f"{name} key", key)
        _require_finite(f"{name}.{key}", item, minimum=minimum)


def canonical_context_sha256(value: JsonContract | Mapping[str, object]) -> str:
    """Hash canonical context JSON without accepting non-finite values."""

    payload = value.to_dict() if isinstance(value, JsonContract) else dict(value)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class RunContextRef(JsonContract):
    sha256: str
    schema_version: str = "value.run-static-context/v1"

    def __post_init__(self) -> None:
        _require_sha256("sha256", self.sha256)
        if self.schema_version != "value.run-static-context/v1":
            raise ValueError("RunContextRef schema_version is unsupported")


@dataclass(frozen=True)
class YearContextRef(JsonContract):
    year: int
    sha256: str
    schema_version: str = "value.year-context/v1"

    def __post_init__(self) -> None:
        _require_year("year", self.year)
        _require_sha256("sha256", self.sha256)
        if self.schema_version != "value.year-context/v1":
            raise ValueError("YearContextRef schema_version is unsupported")


@dataclass(frozen=True)
class RunStaticContext(JsonContract):
    run_id: str
    study_revision_sha256: str
    start_year: int
    end_year: int
    period_hours: float
    data_pack: Mapping[str, object]
    module_graph: Mapping[str, object]
    scientific_parameters: Mapping[str, object]
    runtime_controls: Mapping[str, object]
    trace_profile: str
    solver_contract: Mapping[str, object]
    market_configuration: Mapping[str, object]
    network_pack: Mapping[str, object] | None = None
    schema_version: str = "value.run-static-context/v1"

    def __post_init__(self) -> None:
        _freeze_fields(
            self,
            "data_pack",
            "module_graph",
            "scientific_parameters",
            "runtime_controls",
            "solver_contract",
            "market_configuration",
            "network_pack",
        )
        _require_text("run_id", self.run_id)
        _require_sha256("study_revision_sha256", self.study_revision_sha256)
        _require_year("start_year", self.start_year)
        _require_year("end_year", self.end_year)
        if self.end_year < self.start_year:
            raise ValueError("end_year must not precede start_year")
        _require_finite("period_hours", self.period_hours, minimum=0.0)
        if self.period_hours <= 0:
            raise ValueError("period_hours must be greater than zero")
        for name in (
            "data_pack",
            "module_graph",
            "scientific_parameters",
            "runtime_controls",
            "solver_contract",
            "market_configuration",
        ):
            _require_mapping(name, getattr(self, name))
        if self.network_pack is not None:
            _require_mapping("network_pack", self.network_pack)
        if self.trace_profile not in _TRACE_PROFILES:
            raise ValueError("trace_profile must be off, summary or full")
        if self.schema_version != "value.run-static-context/v1":
            raise ValueError("RunStaticContext schema_version is unsupported")


@dataclass(frozen=True)
class YearContext(JsonContract):
    run_id: str
    year: int
    run_context_sha256: str
    operating_state: Mapping[str, object]
    frozen_zone_shares: Mapping[str, Mapping[str, float]]
    opening_soc_mwh_by_asset: Mapping[str, float]
    transition_lineage: Mapping[str, object]
    schema_version: str = "value.year-context/v1"

    def __post_init__(self) -> None:
        _freeze_fields(
            self,
            "operating_state",
            "frozen_zone_shares",
            "opening_soc_mwh_by_asset",
            "transition_lineage",
        )
        _require_text("run_id", self.run_id)
        _require_year("year", self.year)
        _require_sha256("run_context_sha256", self.run_context_sha256)
        for name in (
            "operating_state",
            "frozen_zone_shares",
            "opening_soc_mwh_by_asset",
            "transition_lineage",
        ):
            _require_mapping(name, getattr(self, name))
        for asset_id, zone_shares in self.frozen_zone_shares.items():
            _require_text("frozen_zone_shares key", asset_id)
            _require_mapping(f"frozen_zone_shares.{asset_id}", zone_shares)
            _require_numeric_mapping(
                f"frozen_zone_shares.{asset_id}", zone_shares, minimum=0.0
            )
        _require_numeric_mapping(
            "opening_soc_mwh_by_asset", self.opening_soc_mwh_by_asset, minimum=0.0
        )
        if self.schema_version != "value.year-context/v1":
            raise ValueError("YearContext schema_version is unsupported")


class ImmutableContextResolver:
    """Resolve only explicitly bound, content-addressed contexts and modules."""

    def __init__(
        self,
        *,
        run_contexts: Sequence[RunStaticContext],
        year_contexts: Sequence[YearContext],
        modules_by_slot: Mapping[str, object] | Sequence[tuple[str, object]],
        authorized_year_run_context_sha256: Sequence[str] = (),
    ) -> None:
        self._runs_by_sha256: dict[str, RunStaticContext] = {}
        for context in run_contexts:
            digest = canonical_context_sha256(context)
            if digest in self._runs_by_sha256:
                raise ValueError("Duplicate run context hash")
            self._runs_by_sha256[digest] = context
        authorized_lineage: set[str] = set()
        for digest in authorized_year_run_context_sha256:
            _require_sha256("authorized year run context SHA-256", digest)
            authorized_lineage.add(digest)
        self._authorized_year_run_context_sha256 = frozenset(authorized_lineage)

        self._year_bind_lock = RLock()
        years_by_reference: dict[tuple[int, str], YearContext] = {}
        year_digest_by_identity: dict[tuple[str, int], str] = {}
        for context in year_contexts:
            digest = canonical_context_sha256(context)
            key = (context.year, digest)
            if key in years_by_reference:
                raise ValueError("Duplicate year context hash")
            self._validate_year_context(context)
            identity = (context.run_id, context.year)
            if identity in year_digest_by_identity:
                raise ValueError(
                    "Year context identity is already bound to different content"
                )
            years_by_reference[key] = context
            year_digest_by_identity[identity] = digest
        self._years_by_reference: Mapping[tuple[int, str], YearContext] = (
            MappingProxyType(years_by_reference)
        )
        self._year_digest_by_identity: Mapping[tuple[str, int], str] = (
            MappingProxyType(year_digest_by_identity)
        )

        module_items = (
            modules_by_slot.items()
            if isinstance(modules_by_slot, MappingABC)
            else modules_by_slot
        )
        self._modules_by_slot: dict[str, object] = {}
        for slot, module in module_items:
            _require_text("module slot", slot)
            if slot in self._modules_by_slot:
                raise ValueError("Duplicate module slot")
            self._modules_by_slot[slot] = module
        self._modules_by_slot = MappingProxyType(self._modules_by_slot)  # type: ignore[assignment]

    def _validate_year_context(self, context: YearContext) -> None:
        if not isinstance(context, YearContext):
            raise TypeError("bind_year requires a YearContext")
        try:
            run_context = self._runs_by_sha256[context.run_context_sha256]
        except KeyError as exc:
            if (
                context.run_context_sha256
                not in self._authorized_year_run_context_sha256
            ):
                raise ValueError(
                    "Year context references an unbound run context"
                ) from exc
            matching = tuple(
                candidate
                for candidate in self._runs_by_sha256.values()
                if candidate.run_id == context.run_id
            )
            if len(matching) != 1:
                raise ValueError(
                    "Authorized historical run lineage has no unique runtime context"
                ) from exc
            run_context = matching[0]
        if context.run_id != run_context.run_id:
            raise ValueError("Year context run does not match its bound run context")

    def bind_year(self, context: YearContext) -> YearContextRef:
        """Bind one immutable annual context, idempotently, for a run and year."""

        return self._bind_year(context, publisher=None)

    def bind_year_transaction(
        self,
        context: YearContext,
        publisher: Callable[[], None],
    ) -> YearContextRef:
        """Publish side effects under the annual lock, then commit the binding."""

        if not callable(publisher):
            raise TypeError("bind_year_transaction requires a publisher callback")
        return self._bind_year(context, publisher=publisher)

    def _bind_year(
        self,
        context: YearContext,
        *,
        publisher: Callable[[], None] | None,
    ) -> YearContextRef:
        """Validate, optionally publish, and copy-on-write the annual binding."""

        self._validate_year_context(context)
        digest = canonical_context_sha256(context)
        reference = YearContextRef(context.year, digest)
        identity = (context.run_id, context.year)
        with self._year_bind_lock:
            existing_digest = self._year_digest_by_identity.get(identity)
            if existing_digest is not None:
                if existing_digest != digest:
                    raise ValueError(
                        "Year context identity is already bound to different content"
                    )
                existing = self._years_by_reference[(context.year, digest)]
                if existing != context:
                    raise ValueError("Year context hash is bound to different content")
            if publisher is not None:
                publisher()
            if existing_digest is not None:
                return reference

            years_by_reference = dict(self._years_by_reference)
            years_by_reference[(context.year, digest)] = context
            year_digest_by_identity = dict(self._year_digest_by_identity)
            year_digest_by_identity[identity] = digest
            self._years_by_reference = MappingProxyType(years_by_reference)
            self._year_digest_by_identity = MappingProxyType(year_digest_by_identity)
        return reference

    def resolve_run(self, reference: RunContextRef) -> RunStaticContext:
        try:
            return self._runs_by_sha256[reference.sha256]
        except KeyError as exc:
            raise ValueError("Run context reference is not bound") from exc

    def resolve_year(self, reference: YearContextRef) -> YearContext:
        try:
            return self._years_by_reference[(reference.year, reference.sha256)]
        except KeyError as exc:
            raise ValueError("Year context reference is not bound") from exc

    def resolve_module(self, slot: str) -> object:
        try:
            return self._modules_by_slot[slot]
        except KeyError as exc:
            raise ValueError(f"Module slot is not bound: {slot}") from exc


class ModuleContextLifecycle(Protocol):
    def configure(self, run_context: RunStaticContext, resolver: ImmutableContextResolver) -> None:
        ...

    def start_year(self, year_context: YearContext) -> None:
        ...
