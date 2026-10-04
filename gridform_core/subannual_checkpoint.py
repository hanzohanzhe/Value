"""Versioned VALUE runtime checkpoints at verified calendar-month boundaries."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Mapping, Protocol, Sequence, runtime_checkable

from .staged_market_contracts import contract_sha256
from .v2.contracts import JsonContract

if TYPE_CHECKING:
    from .market_ledger import MarketLedgerBoundary


SUBANNUAL_CHECKPOINT_SCHEMA = "value.subannual-checkpoint/v1"
SUBANNUAL_RECOVERY_AUTHORIZATION_SCHEMA = (
    "value.subannual-recovery-authorization/v1"
)
SUBANNUAL_AUTH_FIELDS = (
    "schema_version",
    "run_id",
    "checkpoint_id",
    "checkpoint_content_sha256",
    "model_year",
    "last_committed_period",
    "next_period",
    "run_context_sha256",
    "year_context_sha256",
    "source",
    "nonce",
)


@runtime_checkable
class PSMSubannualCheckpointEngine(Protocol):
    """Optional hooks implemented by PSMs with intra-year recovery support."""

    def configure_subannual_checkpoint_sink(
        self,
        sink: Callable[
            [RuntimeCheckpointBoundary, Mapping[str, object], "MarketLedgerBoundary"],
            None,
        ]
        | None,
    ) -> None: ...

    def export_runtime_checkpoint(
        self, boundary: RuntimeCheckpointBoundary
    ) -> Mapping[str, object]: ...

    def restore_runtime_checkpoint(
        self, checkpoint: Mapping[str, object]
    ) -> None: ...
REQUIRED_INPUT_IDENTITIES = frozenset({
    "study_revision_sha256",
    "resolved_run_sha256",
    "run_context_sha256",
    "year_context_sha256",
    "data_pack_id",
    "data_pack_manifest_sha256",
    "network_pack_id",
    "network_pack_manifest_sha256",
    "scientific_parameters_sha256",
    "runtime_controls_sha256",
})
REQUIRED_MODULE_IDENTITIES = frozenset({
    "module_graph_sha256",
    "psm_module_id",
    "psm_module_version",
    "balancing_module_id",
    "balancing_module_version",
    "solver_contract_id",
    "solver_contract_version",
})

_PERIOD_ID = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2}):(?P<settlement>\d{2})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _freeze_json(value: object) -> object:
    if isinstance(value, MappingABC):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _freeze_fields(instance: object, *names: str) -> None:
    for name in names:
        object.__setattr__(instance, name, _freeze_json(getattr(instance, name)))


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _require_model_year(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1900 <= value <= 3000:
        raise ValueError("model_year must be a valid model year")


def _require_period_hours(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("period_hours must be finite and greater than zero")
    period_hours = float(value)
    if not math.isfinite(period_hours) or period_hours <= 0:
        raise ValueError("period_hours must be finite and greater than zero")
    return period_hours


def _require_identity_keys(name: str, values: Mapping[str, object], required: frozenset[str]) -> None:
    missing = required.difference(values)
    if missing:
        raise ValueError(f"{name} is missing required identities: {', '.join(sorted(missing))}")
    for key in required:
        _require_text(f"{name}.{key}", values[key])


def _checkpoint_id(run_id: str, model_year: int, calendar_month: int, last_period_index: int) -> str:
    return f"{run_id}:{model_year}:month-{calendar_month:02d}:period-{last_period_index}"


@dataclass(frozen=True)
class RuntimeCheckpointBoundary(JsonContract):
    checkpoint_id: str
    run_id: str
    model_year: int
    calendar_month: int
    boundary_timestamp: str
    last_period_index: int
    last_period_id: str
    next_period_index: int
    next_period_id: str
    period_hours: float
    chronology_sha256: str

    def __post_init__(self) -> None:
        _require_text("checkpoint_id", self.checkpoint_id)
        _require_text("run_id", self.run_id)
        _require_model_year(self.model_year)
        if not 1 <= self.calendar_month <= 12:
            raise ValueError("calendar_month must be between 1 and 12")
        _require_text("boundary_timestamp", self.boundary_timestamp)
        if self.last_period_index < 0 or self.next_period_index != self.last_period_index + 1:
            raise ValueError("checkpoint boundary period indexes must be consecutive")
        _require_text("last_period_id", self.last_period_id)
        _require_text("next_period_id", self.next_period_id)
        _require_period_hours(self.period_hours)
        _require_sha256("chronology_sha256", self.chronology_sha256)
        expected_id = _checkpoint_id(
            self.run_id, self.model_year, self.calendar_month, self.last_period_index
        )
        if self.checkpoint_id != expected_id:
            raise ValueError("checkpoint_id does not match the checkpoint boundary")


@dataclass(frozen=True)
class SubannualCheckpointIdentity(JsonContract):
    run_id: str
    model_year: int
    period_hours: float
    chronology_sha256: str
    frozen_input_hashes: Mapping[str, object]
    frozen_module_hashes: Mapping[str, object]

    def __post_init__(self) -> None:
        _freeze_fields(self, "frozen_input_hashes", "frozen_module_hashes")
        _require_text("run_id", self.run_id)
        _require_model_year(self.model_year)
        _require_period_hours(self.period_hours)
        _require_sha256("chronology_sha256", self.chronology_sha256)
        _require_identity_keys(
            "frozen_input_hashes", self.frozen_input_hashes, REQUIRED_INPUT_IDENTITIES
        )
        _require_identity_keys(
            "frozen_module_hashes", self.frozen_module_hashes, REQUIRED_MODULE_IDENTITIES
        )


@dataclass(frozen=True)
class LedgerPrefixIdentity(JsonContract):
    database_sha256: str
    committed_period_count: int
    maximum_committed_period: int
    committed_prefix_sha256: str

    def __post_init__(self) -> None:
        _require_sha256("database_sha256", self.database_sha256)
        _require_sha256("committed_prefix_sha256", self.committed_prefix_sha256)
        if self.committed_period_count < 1 or self.maximum_committed_period < 0:
            raise ValueError("ledger prefix must contain committed periods")


@dataclass(frozen=True)
class SubannualCheckpoint(JsonContract):
    checkpoint_id: str
    run_id: str
    model_year: int
    calendar_month: int
    boundary_timestamp: str
    last_committed_period: int
    last_committed_period_id: str
    next_period: int
    next_period_id: str
    period_hours: float
    chronology_sha256: str
    chronological_storage_state: Sequence[object]
    agent_observations: Mapping[str, object]
    writer_offsets: Mapping[str, object]
    random_generator_states: Mapping[str, object]
    year_to_date: Mapping[str, object]
    frozen_input_hashes: Mapping[str, object]
    frozen_module_hashes: Mapping[str, object]
    parent_annual_checkpoint_identity: Mapping[str, object]
    ledger_boundary: LedgerPrefixIdentity | Mapping[str, object]
    publication_state: str
    content_sha256: str
    schema_version: str = SUBANNUAL_CHECKPOINT_SCHEMA

    def __post_init__(self) -> None:
        _freeze_fields(
            self,
            "chronological_storage_state",
            "agent_observations",
            "writer_offsets",
            "random_generator_states",
            "year_to_date",
            "frozen_input_hashes",
            "frozen_module_hashes",
            "parent_annual_checkpoint_identity",
            "ledger_boundary",
        )
        if self.schema_version != SUBANNUAL_CHECKPOINT_SCHEMA:
            raise ValueError("SubannualCheckpoint schema_version is unsupported")
        _require_text("checkpoint_id", self.checkpoint_id)
        _require_text("run_id", self.run_id)
        _require_model_year(self.model_year)
        if not 1 <= self.calendar_month <= 12:
            raise ValueError("calendar_month must be between 1 and 12")
        _require_text("boundary_timestamp", self.boundary_timestamp)
        if self.last_committed_period < 0 or self.next_period != self.last_committed_period + 1:
            raise ValueError("checkpoint periods must be consecutive")
        _require_text("last_committed_period_id", self.last_committed_period_id)
        _require_text("next_period_id", self.next_period_id)
        _require_period_hours(self.period_hours)
        _require_sha256("chronology_sha256", self.chronology_sha256)
        _require_identity_keys(
            "frozen_input_hashes", self.frozen_input_hashes, REQUIRED_INPUT_IDENTITIES
        )
        _require_identity_keys(
            "frozen_module_hashes", self.frozen_module_hashes, REQUIRED_MODULE_IDENTITIES
        )
        _require_sha256("content_sha256", self.content_sha256)
        if self.publication_state != "verified":
            raise ValueError("publication_state must be verified")
        expected_id = _checkpoint_id(
            self.run_id, self.model_year, self.calendar_month, self.last_committed_period
        )
        if self.checkpoint_id != expected_id:
            raise ValueError("checkpoint_id does not match the checkpoint boundary")


@dataclass(frozen=True)
class RecoveryMismatch(JsonContract):
    code: str
    message: str
    corrective_action: str

    def __post_init__(self) -> None:
        _require_text("code", self.code)
        _require_text("message", self.message)
        _require_text("corrective_action", self.corrective_action)


@dataclass(frozen=True)
class RecoveryCandidate(JsonContract):
    checkpoint_id: str
    compatible: bool
    selectable: bool
    boundary_label: str
    next_period_label: str
    mismatch: RecoveryMismatch | None = None

    def __post_init__(self) -> None:
        _require_text("checkpoint_id", self.checkpoint_id)
        _require_text("boundary_label", self.boundary_label)
        _require_text("next_period_label", self.next_period_label)
        if self.selectable and not self.compatible:
            raise ValueError("an incompatible recovery candidate cannot be selectable")
        if self.compatible and self.mismatch is not None:
            raise ValueError("a compatible recovery candidate cannot have a mismatch")


def _parse_period_id(
    period_id: str, *, period_hours: float
) -> tuple[datetime, int]:
    match = _PERIOD_ID.fullmatch(period_id)
    if match is None:
        indexed = re.fullmatch(r"(?P<year>[0-9]{4}):(?P<index>[0-9]+)", period_id)
        if indexed is None:
            raise ValueError("frozen chronology contains an unparseable period id")
        periods_per_day = round(24 / period_hours)
        index = int(indexed.group("index"))
        day_offset, zero_based_settlement = divmod(index, periods_per_day)
        year = int(indexed.group("year"))
        day = datetime(year, 1, 1) + timedelta(days=day_offset)
        if day.year != year:
            raise ValueError("frozen chronology contains an invalid indexed period")
        return day, zero_based_settlement + 1
    try:
        day = datetime.strptime(match.group("date"), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("frozen chronology contains an unparseable period id") from exc
    settlement = int(match.group("settlement"))
    settlements_per_day = round(24 / period_hours)
    daylight_saving_extension = round(1 / period_hours)
    if not 1 <= settlement <= settlements_per_day + daylight_saving_extension:
        raise ValueError("frozen chronology contains an invalid settlement period")
    return day, settlement


def calendar_month_boundaries(
    period_ids: Sequence[str],
    *,
    model_year: int,
    period_hours: float,
    run_id: str,
) -> tuple[RuntimeCheckpointBoundary, ...]:
    """Return real calendar-month boundaries from the immutable source chronology."""

    _require_model_year(model_year)
    _require_text("run_id", run_id)
    normalized_hours = _require_period_hours(period_hours)
    raw_period_ids = tuple(period_ids)
    parsed = tuple(
        _parse_period_id(period_id, period_hours=normalized_hours)
        for period_id in raw_period_ids
    )
    if any(right <= left for left, right in zip(parsed, parsed[1:])):
        raise ValueError("frozen chronology must be strictly monotonic")
    chronology_sha256 = contract_sha256({
        "period_ids": raw_period_ids,
        "period_hours": normalized_hours,
        "model_year": model_year,
    })
    boundaries: list[RuntimeCheckpointBoundary] = []
    for last_index, (last_period, next_period) in enumerate(zip(parsed, parsed[1:])):
        last_day, _last_settlement = last_period
        next_day, _next_settlement = next_period
        if (last_day.year, last_day.month) == (
            next_day.year,
            next_day.month,
        ):
            continue
        boundary_timestamp = datetime(model_year, next_day.month, 1).isoformat(
            timespec="seconds"
        )
        boundaries.append(RuntimeCheckpointBoundary(
            checkpoint_id=_checkpoint_id(run_id, model_year, last_day.month, last_index),
            run_id=run_id,
            model_year=model_year,
            calendar_month=last_day.month,
            boundary_timestamp=boundary_timestamp,
            last_period_index=last_index,
            last_period_id=raw_period_ids[last_index],
            next_period_index=last_index + 1,
            next_period_id=raw_period_ids[last_index + 1],
            period_hours=normalized_hours,
            chronology_sha256=chronology_sha256,
        ))
    return tuple(boundaries)


def checkpoint_content_sha256(checkpoint: SubannualCheckpoint | Mapping[str, object]) -> str:
    """Hash the canonical checkpoint JSON without its self-referential digest."""

    payload = checkpoint.to_dict() if isinstance(checkpoint, JsonContract) else dict(checkpoint)
    payload.pop("content_sha256", None)
    return contract_sha256(payload)


def subannual_recovery_authorization_id(value: Mapping[str, object]) -> str:
    """Return the canonical identity of one explicit monthly recovery grant."""

    if not isinstance(value, MappingABC):
        raise TypeError("subannual recovery authorization must be a mapping")
    payload = {name: value.get(name) for name in SUBANNUAL_AUTH_FIELDS}
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def issue_subannual_recovery_authorization(
    *,
    run_id: str,
    checkpoint_id: str,
    checkpoint_content_sha256: str,
    model_year: int,
    last_committed_period: int,
    next_period: int,
    run_context_sha256: str,
    year_context_sha256: str,
    source: str,
    nonce: str | None = None,
) -> Mapping[str, object]:
    """Issue an immutable, one-use grant for one already-validated checkpoint."""

    _require_text("run_id", run_id)
    _require_text("checkpoint_id", checkpoint_id)
    _require_sha256("checkpoint_content_sha256", checkpoint_content_sha256)
    _require_model_year(model_year)
    if (
        isinstance(last_committed_period, bool)
        or not isinstance(last_committed_period, int)
        or last_committed_period < 0
        or next_period != last_committed_period + 1
    ):
        raise ValueError("subannual authorization periods must be consecutive")
    _require_sha256("run_context_sha256", run_context_sha256)
    _require_sha256("year_context_sha256", year_context_sha256)
    _require_text("source", source)
    issuance_nonce = secrets.token_hex(16) if nonce is None else nonce
    if (
        not isinstance(issuance_nonce, str)
        or len(issuance_nonce) != 32
        or any(character not in "0123456789abcdef" for character in issuance_nonce)
    ):
        raise ValueError("nonce must contain 32 lowercase hexadecimal characters")
    authorization: dict[str, object] = {
        "schema_version": SUBANNUAL_RECOVERY_AUTHORIZATION_SCHEMA,
        "run_id": run_id,
        "checkpoint_id": checkpoint_id,
        "checkpoint_content_sha256": checkpoint_content_sha256,
        "model_year": model_year,
        "last_committed_period": last_committed_period,
        "next_period": next_period,
        "run_context_sha256": run_context_sha256,
        "year_context_sha256": year_context_sha256,
        "source": source,
        "nonce": issuance_nonce,
        "state": "issued",
    }
    authorization["authorization_id"] = subannual_recovery_authorization_id(
        authorization
    )
    return MappingProxyType(authorization)


def claim_subannual_recovery_authorization(
    *,
    store: "SubannualCheckpointStore",
    authorization: Mapping[str, object],
) -> Mapping[str, object]:
    """Atomically consume one explicitly presented monthly recovery grant."""

    if not isinstance(store, SubannualCheckpointStore):
        raise TypeError("store must be a SubannualCheckpointStore")
    if not isinstance(authorization, MappingABC):
        raise TypeError("authorization must be a mapping")
    if authorization.get("state") != "presented":
        raise ValueError("Subannual recovery authorization must be presented")
    if authorization.get("schema_version") != SUBANNUAL_RECOVERY_AUTHORIZATION_SCHEMA:
        raise ValueError("Subannual recovery authorization schema is unsupported")
    if authorization.get("authorization_id") != subannual_recovery_authorization_id(
        authorization
    ):
        raise ValueError("Subannual recovery authorization identity does not match")
    store.claim(authorization)
    return MappingProxyType({**dict(authorization), "state": "consumed"})


def validate_subannual_checkpoint(
    checkpoint: SubannualCheckpoint,
    expected: SubannualCheckpointIdentity,
) -> None:
    """Fail closed unless a verified checkpoint matches the exact frozen identity."""

    if not isinstance(checkpoint, SubannualCheckpoint):
        raise TypeError("checkpoint must be a SubannualCheckpoint")
    if not isinstance(expected, SubannualCheckpointIdentity):
        raise TypeError("expected must be a SubannualCheckpointIdentity")
    _require_identity_keys(
        "frozen_input_hashes", checkpoint.frozen_input_hashes, REQUIRED_INPUT_IDENTITIES
    )
    _require_identity_keys(
        "frozen_module_hashes", checkpoint.frozen_module_hashes, REQUIRED_MODULE_IDENTITIES
    )
    for name in ("run_id", "model_year", "period_hours", "chronology_sha256"):
        if getattr(checkpoint, name) != getattr(expected, name):
            raise ValueError(f"checkpoint {name} does not match the expected frozen identity")
    for name in ("frozen_input_hashes", "frozen_module_hashes"):
        if dict(getattr(checkpoint, name)) != dict(getattr(expected, name)):
            raise ValueError(f"checkpoint {name} does not match the expected frozen identity")
    if checkpoint.content_sha256 != checkpoint_content_sha256(checkpoint):
        raise ValueError("checkpoint content_sha256 does not match the canonical payload")


_CHECKPOINT_STORE_SCHEMA = "value.subannual-checkpoint-store/v1"
_CLAIM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) + "\n").encode("utf-8")


def _checkpoint_identity(checkpoint: SubannualCheckpoint) -> SubannualCheckpointIdentity:
    return SubannualCheckpointIdentity(
        run_id=checkpoint.run_id, model_year=checkpoint.model_year,
        period_hours=checkpoint.period_hours, chronology_sha256=checkpoint.chronology_sha256,
        frozen_input_hashes=checkpoint.frozen_input_hashes,
        frozen_module_hashes=checkpoint.frozen_module_hashes,
    )


class SubannualCheckpointStore:
    """Durable, fail-closed publication and recovery index for monthly checkpoints."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.directory = self.root / "model-output" / "checkpoints-subannual-v1"
        self.manifest_path = self.directory / "manifest.json"

    def publish(self, checkpoint: SubannualCheckpoint) -> RecoveryCandidate:
        if not isinstance(checkpoint, SubannualCheckpoint):
            raise TypeError("checkpoint must be a SubannualCheckpoint")
        validate_subannual_checkpoint(checkpoint, _checkpoint_identity(checkpoint))
        relative_path = self._relative_path(checkpoint)
        serialized = _canonical_json_bytes(checkpoint.to_dict())
        manifest = self._read_manifest()
        existing = next(
            (entry for entry in manifest["entries"] if entry["checkpoint_id"] == checkpoint.checkpoint_id),
            None,
        )
        collisions = [
            entry for entry in manifest["entries"]
            if entry["relative_path"] == relative_path.as_posix()
            and entry["checkpoint_id"] != checkpoint.checkpoint_id
        ]
        if collisions:
            raise ValueError("checkpoint artifact path collides with a different checkpoint id")
        destination = self.directory / relative_path
        if destination.exists():
            if destination.read_bytes() != serialized:
                raise FileExistsError("checkpoint artifact path already contains conflicting bytes")
        else:
            self._atomic_write(destination, serialized)
        entry = self._entry_from_file(
            relative_path, checkpoint.checkpoint_id,
            expected_file_sha256=hashlib.sha256(serialized).hexdigest(),
        )
        entries = [entry for entry in manifest["entries"] if entry["checkpoint_id"] != checkpoint.checkpoint_id]
        entries.append(entry)
        manifest["entries"] = entries
        self._publish_manifest(manifest)
        if existing is not None and existing["relative_path"] != entry["relative_path"]:
            self._cleanup_entries((existing,))
        return self._candidate_from_entry(entry, _checkpoint_identity(checkpoint))

    def discover(self, expected: SubannualCheckpointIdentity) -> tuple[RecoveryCandidate, ...]:
        if not isinstance(expected, SubannualCheckpointIdentity):
            raise TypeError("expected must be a SubannualCheckpointIdentity")
        entries = sorted(
            self._read_manifest()["entries"],
            key=lambda entry: (entry["model_year"], entry["calendar_month"], entry["last_period"]),
            reverse=True,
        )
        return tuple(self._candidate_from_entry(entry, expected) for entry in entries)

    def load(self, checkpoint_id: str, expected: SubannualCheckpointIdentity) -> SubannualCheckpoint:
        if not isinstance(expected, SubannualCheckpointIdentity):
            raise TypeError("expected must be a SubannualCheckpointIdentity")
        for entry in self._read_manifest()["entries"]:
            if entry["checkpoint_id"] == checkpoint_id:
                checkpoint = self._load_entry(entry)
                validate_subannual_checkpoint(checkpoint, expected)
                return checkpoint
        raise FileNotFoundError(f"checkpoint is not in the published manifest: {checkpoint_id}")

    def prune_verified(self, *, year: int, keep: int = 2) -> None:
        _require_model_year(year)
        if isinstance(keep, bool) or not isinstance(keep, int) or keep < 0:
            raise ValueError("keep must be a non-negative integer")
        manifest = self._read_manifest()
        in_year = [entry for entry in manifest["entries"] if entry["model_year"] == year]
        for entry in in_year:
            self._load_entry(entry)
        ordered = sorted(
            in_year, key=lambda entry: (entry["calendar_month"], entry["last_period"]), reverse=True
        )
        discarded = ordered[keep:]
        discarded_ids = {entry["checkpoint_id"] for entry in discarded}
        manifest["entries"] = [
            entry for entry in manifest["entries"] if entry["checkpoint_id"] not in discarded_ids
        ]
        self._publish_manifest(manifest)
        self._cleanup_entries(discarded)

    def supersede_with_annual(self, *, year: int, annual_checkpoint_sha256: str) -> None:
        _require_model_year(year)
        _require_sha256("annual_checkpoint_sha256", annual_checkpoint_sha256)
        manifest = self._read_manifest()
        superseded = [entry for entry in manifest["entries"] if entry["model_year"] == year]
        for entry in superseded:
            self._load_entry(entry)
        superseded_ids = {entry["checkpoint_id"] for entry in superseded}
        manifest["entries"] = [
            entry for entry in manifest["entries"] if entry["checkpoint_id"] not in superseded_ids
        ]
        manifest["annual_supersessions"][str(year)] = annual_checkpoint_sha256
        self._publish_manifest(manifest)
        self._cleanup_entries(superseded)

    def claim(self, authorization: Mapping[str, object]) -> Path:
        if not isinstance(authorization, MappingABC):
            raise TypeError("authorization must be a mapping")
        authorization_id = authorization.get("authorization_id")
        if not isinstance(authorization_id, str) or not _CLAIM_ID.fullmatch(authorization_id):
            raise ValueError("authorization.authorization_id must be a safe non-empty identifier")
        claims = self.directory / "claims"
        claims.mkdir(parents=True, exist_ok=True)
        path = claims / f"{authorization_id}.claim"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_canonical_json_bytes(dict(authorization)))
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise
        return path

    def _read_manifest(self) -> dict[str, object]:
        if not self.manifest_path.exists():
            return {"schema_version": _CHECKPOINT_STORE_SCHEMA, "entries": [], "annual_supersessions": {}}
        payload, raw = self._read_json_file(self.manifest_path)
        if raw != _canonical_json_bytes(payload):
            raise ValueError("checkpoint manifest is not canonical JSON")
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "entries", "annual_supersessions"
        }:
            raise ValueError("checkpoint manifest has an invalid envelope")
        if payload["schema_version"] != _CHECKPOINT_STORE_SCHEMA:
            raise ValueError("checkpoint manifest schema_version is unsupported")
        if not isinstance(payload["entries"], list) or not isinstance(payload["annual_supersessions"], dict):
            raise ValueError("checkpoint manifest has invalid collections")
        entries = [self._validate_entry(entry) for entry in payload["entries"]]
        annual = payload["annual_supersessions"]
        for model_year, digest in annual.items():
            try:
                _require_model_year(int(model_year))
            except (TypeError, ValueError) as exc:
                raise ValueError("checkpoint manifest has an invalid annual supersession year") from exc
            _require_sha256("annual supersession hash", digest)
        return {"schema_version": _CHECKPOINT_STORE_SCHEMA, "entries": entries, "annual_supersessions": dict(annual)}

    def _publish_manifest(self, manifest: Mapping[str, object]) -> None:
        self._atomic_write(self.manifest_path, _canonical_json_bytes(manifest))
        self._read_manifest()

    def _atomic_write(self, destination: Path, data: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _read_json_file(path: Path) -> tuple[object, bytes]:
        try:
            raw = path.read_bytes()
            return json.loads(raw.decode("utf-8")), raw
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"checkpoint file cannot be read: {path}") from exc

    def _entry_from_file(
        self, relative_path: Path, checkpoint_id: str, *, expected_file_sha256: str
    ) -> dict[str, object]:
        payload, raw = self._read_json_file(self.directory / relative_path)
        if hashlib.sha256(raw).hexdigest() != expected_file_sha256:
            raise ValueError("checkpoint complete-file SHA-256 does not match post-rename bytes")
        if not isinstance(payload, MappingABC):
            raise ValueError("checkpoint file must contain an object")
        if raw != _canonical_json_bytes(payload):
            raise ValueError("checkpoint file is not canonical JSON")
        checkpoint = self._checkpoint_from_payload(payload)
        if checkpoint.checkpoint_id != checkpoint_id:
            raise ValueError("checkpoint file id does not match its publication request")
        validate_subannual_checkpoint(checkpoint, _checkpoint_identity(checkpoint))
        return {
            "checkpoint_id": checkpoint.checkpoint_id,
            "relative_path": relative_path.as_posix(),
            "model_year": checkpoint.model_year,
            "calendar_month": checkpoint.calendar_month,
            "last_period": checkpoint.last_committed_period,
            "next_period": checkpoint.next_period,
            "boundary_label": checkpoint.boundary_timestamp,
            "next_period_label": checkpoint.next_period_id,
            "content_sha256": checkpoint.content_sha256,
            "complete_file_sha256": hashlib.sha256(raw).hexdigest(),
        }

    def _validate_entry(self, entry: object) -> dict[str, object]:
        required = {
            "checkpoint_id", "relative_path", "model_year", "calendar_month", "last_period",
            "next_period", "boundary_label", "next_period_label", "content_sha256",
            "complete_file_sha256",
        }
        if not isinstance(entry, MappingABC) or set(entry) != required:
            raise ValueError("checkpoint manifest entry has an invalid envelope")
        normalized = dict(entry)
        _require_text("checkpoint manifest checkpoint_id", normalized["checkpoint_id"])
        relative = Path(normalized["relative_path"])
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".json":
            raise ValueError("checkpoint manifest entry has an unsafe relative path")
        _require_model_year(normalized["model_year"])
        if not isinstance(normalized["calendar_month"], int) or not 1 <= normalized["calendar_month"] <= 12:
            raise ValueError("checkpoint manifest entry has an invalid calendar month")
        if not isinstance(normalized["last_period"], int) or normalized["last_period"] < 0:
            raise ValueError("checkpoint manifest entry has an invalid last period")
        if normalized["next_period"] != normalized["last_period"] + 1:
            raise ValueError("checkpoint manifest entry has non-consecutive periods")
        _require_text("checkpoint manifest boundary_label", normalized["boundary_label"])
        _require_text("checkpoint manifest next_period_label", normalized["next_period_label"])
        _require_sha256("checkpoint manifest content_sha256", normalized["content_sha256"])
        _require_sha256("checkpoint manifest complete_file_sha256", normalized["complete_file_sha256"])
        return normalized

    def _entry_path(self, entry: Mapping[str, object]) -> Path:
        path = self.directory / str(entry["relative_path"])
        try:
            path.resolve().relative_to(self.directory.resolve())
        except ValueError as exc:
            raise ValueError("checkpoint manifest path escapes the checkpoint directory") from exc
        return path

    @staticmethod
    def _relative_path(checkpoint: SubannualCheckpoint) -> Path:
        return Path(str(checkpoint.model_year)) / (
            f"month-{checkpoint.calendar_month:02d}-period-{checkpoint.last_committed_period}"
            f"-{checkpoint.content_sha256}.json"
        )

    def _cleanup_entries(self, entries: Sequence[Mapping[str, object]]) -> None:
        """Remove artifacts no longer referenced by the already-published manifest."""

        for entry in entries:
            try:
                self._entry_path(entry).unlink()
            except OSError:
                continue

    def _load_entry(self, entry: Mapping[str, object]) -> SubannualCheckpoint:
        payload, raw = self._read_json_file(self._entry_path(entry))
        if hashlib.sha256(raw).hexdigest() != entry["complete_file_sha256"]:
            raise ValueError("checkpoint complete-file SHA-256 does not match manifest")
        if not isinstance(payload, MappingABC):
            raise ValueError("checkpoint file must contain an object")
        if raw != _canonical_json_bytes(payload):
            raise ValueError("checkpoint file is not canonical JSON")
        checkpoint = self._checkpoint_from_payload(payload)
        if checkpoint.checkpoint_id != entry["checkpoint_id"]:
            raise ValueError("checkpoint id does not match manifest")
        if checkpoint.content_sha256 != entry["content_sha256"]:
            raise ValueError("checkpoint canonical-content SHA-256 does not match manifest")
        expected_fields = {
            "relative_path": self._relative_path(checkpoint).as_posix(),
            "model_year": checkpoint.model_year,
            "calendar_month": checkpoint.calendar_month,
            "last_period": checkpoint.last_committed_period,
            "next_period": checkpoint.next_period,
            "boundary_label": checkpoint.boundary_timestamp,
            "next_period_label": checkpoint.next_period_id,
        }
        for field_name, expected_value in expected_fields.items():
            if entry[field_name] != expected_value:
                raise ValueError(f"checkpoint manifest {field_name} does not match checkpoint payload")
        validate_subannual_checkpoint(checkpoint, _checkpoint_identity(checkpoint))
        return checkpoint

    @staticmethod
    def _checkpoint_from_payload(payload: Mapping[str, object]) -> SubannualCheckpoint:
        if set(payload) != {item.name for item in fields(SubannualCheckpoint)}:
            raise ValueError("checkpoint file has an invalid envelope")
        try:
            decoded = dict(payload)
            ledger_boundary = decoded["ledger_boundary"]
            if isinstance(ledger_boundary, MappingABC):
                decoded["ledger_boundary"] = LedgerPrefixIdentity.from_dict(ledger_boundary)
            return SubannualCheckpoint(**decoded)
        except (TypeError, ValueError) as exc:
            raise ValueError("checkpoint file has an invalid payload") from exc

    def _candidate_from_entry(
        self, entry: Mapping[str, object], expected: SubannualCheckpointIdentity
    ) -> RecoveryCandidate:
        try:
            checkpoint = self._load_entry(entry)
            validate_subannual_checkpoint(checkpoint, expected)
        except (OSError, TypeError, ValueError) as exc:
            message = str(exc)
            if "complete-file SHA-256" in message:
                code = "complete_file_sha256_mismatch"
            elif "canonical-content SHA-256" in message or "content_sha256" in message:
                code = "canonical_content_sha256_mismatch"
            elif "expected frozen identity" in message:
                code = "identity_mismatch"
            else:
                code = "checkpoint_invalid"
            return RecoveryCandidate(
                checkpoint_id=str(entry["checkpoint_id"]), compatible=False, selectable=False,
                boundary_label=str(entry["boundary_label"]),
                next_period_label=str(entry["next_period_label"]),
                mismatch=RecoveryMismatch(
                    code=code, message=message,
                    corrective_action="Select an explicitly verified checkpoint or republish this boundary.",
                ),
            )
        return RecoveryCandidate(
            checkpoint_id=checkpoint.checkpoint_id, compatible=True, selectable=True,
            boundary_label=checkpoint.boundary_timestamp, next_period_label=checkpoint.next_period_id,
        )
