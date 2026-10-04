"""Versioned, transport-neutral contracts for the VALUE Data Workbench."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import ClassVar, Mapping, Sequence

from gridform_core.v2.contracts import JsonContract


DATA_WORKBENCH_API_SCHEMA = "value.data-workbench-api/v1"
_NON_SCIENTIFIC_KEYS = {
    "approved_at",
    "discovered_at",
    "observed_at",
    "retrieved_at",
}
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


def _without_observation_metadata(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _without_observation_metadata(item)
            for key, item in value.items()
            if str(key) not in _NON_SCIENTIFIC_KEYS
        }
    if isinstance(value, (tuple, list)):
        return [_without_observation_metadata(item) for item in value]
    return value


def _reject_absolute_paths(value: object, *, field_name: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_absolute_paths(item, field_name=str(key))
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _reject_absolute_paths(item, field_name=field_name)
        return
    if not isinstance(value, str) or "://" in value:
        return
    if _WINDOWS_ABSOLUTE.match(value) or value.startswith("/"):
        raise ValueError(f"Public contract field {field_name} contains an absolute path")


class WorkbenchContract(JsonContract):
    SCHEMA_VERSION: ClassVar[str]

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]):  # type: ignore[override]
        if payload.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError(
                f"{cls.__name__} schema_version must be {cls.SCHEMA_VERSION}"
            )
        _reject_absolute_paths(payload)
        return super().from_dict(payload)


@dataclass(frozen=True)
class SourceDefinition(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-source-definition/v1"

    source_id: str
    authority: str
    semantic_role: str
    landing_page: str
    discovery_adapter: str
    allowed_domains: Sequence[str]
    licence_expected: str
    candidate_uses: Sequence[str]
    schema_version: str = SCHEMA_VERSION
    expected_media_types: Sequence[str] = field(default_factory=tuple)
    redistribution_policy: str = "verify_each_revision"
    discovery_config: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceRevision(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-source-revision/v1"

    source_id: str
    revision_id: str
    publication_date: str
    landing_page: str
    download_url: str
    media_type: str
    reported_licence: str
    discovered_at: str
    status: str
    schema_version: str = SCHEMA_VERSION
    catalogue_metadata: Mapping[str, object] = field(default_factory=dict)
    object_key: str | None = None
    redistribution_decision: str | None = None


@dataclass(frozen=True)
class StoredObject(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-stored-object/v1"

    object_key: str
    sha256: str
    byte_size: int
    media_type: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class RawObjectReceipt(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-raw-object-receipt/v1"

    source_id: str
    revision_id: str
    sha256: str
    byte_size: int
    media_type: str
    retrieved_at: str
    final_resolved_url: str
    licence_snapshot: str
    object_key: str
    schema_version: str = SCHEMA_VERSION
    http_metadata: Mapping[str, str] = field(default_factory=dict)
    redistribution_decision: str = "needs_rights_review"


@dataclass(frozen=True)
class BuildManifest(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-build-manifest/v1"

    build_id: str
    target_contract: str
    source_object_hashes: Mapping[str, str]
    compiler_versions: Mapping[str, str]
    parameters: Mapping[str, object]
    assumptions: Sequence[str]
    manual_overrides: Mapping[str, str]
    schema_version: str = SCHEMA_VERSION
    created_at: str = ""
    parent_candidate_id: str | None = None


@dataclass(frozen=True)
class CandidateInventoryItem(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-candidate-inventory-item/v1"

    item_id: str
    status: str
    usable_for: Sequence[str]
    not_usable_for: Sequence[str]
    blocking_reasons: Sequence[str]
    required_actions: Sequence[str]
    schema_version: str = SCHEMA_VERSION
    affected_artifacts: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class CandidatePack(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-candidate-pack/v1"

    build_manifest_hash: str
    artifact_hashes: Mapping[str, str]
    source_revisions: Sequence[SourceRevision]
    validation_status: str
    candidate_inventory: Sequence[CandidateInventoryItem]
    requested_waivers: Sequence[str]
    report_refs: Mapping[str, str]
    observed_at: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ValidationIssue(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-validation-issue/v1"

    code: str
    severity: str
    artifact_role: str
    message: str
    evidence: Mapping[str, object]
    repair: str
    waivable: bool
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ValidationReport(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-validation-report/v1"

    candidate_id: str
    status: str
    issues: Sequence[ValidationIssue]
    schema_version: str = SCHEMA_VERSION
    gate_results: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PromotionRequest(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-promotion-request/v1"

    candidate_id: str
    version: str
    reviewer: str
    accepted_waivers: Sequence[str]
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SignedBundleReceipt(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-signed-bundle-receipt/v1"

    network_pack_id: str
    candidate_id: str
    bundle_sha256: str
    manifest_sha256: str
    approved_by: str
    approved_at: str
    accepted_waivers: Sequence[str]
    schema_version: str = SCHEMA_VERSION
    signature_type: str = "local_approval_attestation"


@dataclass(frozen=True)
class DiscoveryRequest(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-discovery-request/v1"

    registry_id: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class DiscoveryReport(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-discovery-report/v1"

    revisions: Sequence[SourceRevision]
    observed_at: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class BuildRequest(WorkbenchContract):
    SCHEMA_VERSION: ClassVar[str] = "value.data-build-request/v1"

    recipe_id: str
    source_receipts: Sequence[RawObjectReceipt]
    parameters: Mapping[str, object]
    schema_version: str = SCHEMA_VERSION


def canonical_payload(value: object, *, scientific: bool = False) -> str:
    if isinstance(value, JsonContract):
        value = value.to_dict()
    _reject_absolute_paths(value)
    if scientific:
        value = _without_observation_metadata(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scientific_hash(value: object) -> str:
    return hashlib.sha256(canonical_payload(value, scientific=True).encode("utf-8")).hexdigest()


def candidate_id(candidate: CandidatePack) -> str:
    return "candidate-" + scientific_hash(candidate)[:20]
