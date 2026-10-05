"""The content identity of a Data Pack manifest across freezing and recovery.

A methodology profile pins a Data Pack by id, class and manifest sha (decision
Q3, the doctoral data-pack whitelist).  Two product flows rewrite a manifest
while keeping its scientific content:

* A queued Run executes on ``input-snapshot/pack``: ``run_snapshot._freeze_pack``
  rewrites every binding of that copy (``uri``, ``sha256``, ``bytes``, plus the
  snapshot fields) and marks the manifest ``snapshot_frozen``.
* Frozen-input recovery (``backend/frozen_input_recovery.py``) publishes a
  Run's frozen inputs as a new pack ``recovered-base-<suffix>``: new id, name
  and timestamps, qualification fields moved into ``frozen_recovery_origin``,
  binding locators and history moved into ``frozen_recovery_provenance``.

:func:`resolve_pack_identity` is the one resolver every whitelist check uses
(Study resolution, preflight, the run entry in the worker, the recovery
review).  It walks back from such a copy to the manifest it was made from and
returns that manifest with its sha candidates, so preflight on a source pack
and the worker on its frozen copy compare the same values against a pin.

**The source record.**  At freeze time the snapshot stores the exact bytes of
the source manifest file (as UTF-8 text) under :data:`SOURCE_FIELD`, with
their file sha and canonical-JSON sha.  A record is verified by content only:
the text hashes to the recorded file sha and parses to a manifest whose
canonical sha is the recorded canonical sha.  Both sha candidates of the
identified manifest therefore come from verified content, never from a
self-declared value.

**Frozen copy -> source** (:func:`frozen_source`): the record verifies; the role
sets are equal; every frozen binding's ``source_sha256`` is the source
binding's ``sha256`` (``run_snapshot`` verified the source file against it
before copying); an identity-transformed binding's frozen ``sha256`` is that
same digest (the file verifiers - ``verify_run_input_snapshot`` and
``frozen_input_integrity`` - tie the frozen file bytes to it); every binding
field the freeze does not rewrite is unchanged; every top-level field except
the freeze fields is unchanged.

**Recovered pack -> source** (:func:`recovered_source`), verified content
identity: the record carried in ``frozen_recovery_origin.source_qualification``
verifies; the recovered pack is a base pack; every binding is
identity-transformed in the source and has the same data sha (and byte count)
in the recovered pack; every binding field other than locators, recovery
bookkeeping and history is unchanged; every top-level field other than the
recovery-rewritten ones (:data:`RECOVERY_REWRITTEN_FIELDS`,
:data:`RECOVERY_QUALIFICATION_FIELDS`) is unchanged.  The recovered pack then
holds exactly the source pack's data and semantic metadata, so it is
identified as the source pack.  Adapter-transformed bindings, network
overlays and a base pack whose network roles were projected out are not
identified (their content differs from the source).

A record or origin that is not consistent is ignored, so a forged or damaged
record never borrows a pinned identity.  Comparisons use canonical JSON (so
``1``, ``1.0`` and ``true`` differ).  No imports beyond the standard library:
``gridform_core.methodology`` uses this module.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

SOURCE_FIELD = "snapshot_source_manifest"
# v2 stores the source manifest bytes; a v1 record (canonical sha and source
# bindings only, written on the development branch between 21865c1 and the
# round-4 response, never released) is not verifiable and is ignored.
SOURCE_SCHEMA = "value.snapshot-source-manifest/v2"
IDENTITY_TRANSFORMATION = "identity/v1"
# Binding fields run_snapshot._freeze_pack rewrites; ``format`` only for an
# adapter binding (the adapter emits the canonical format).
FREEZE_REWRITTEN_BINDING_FIELDS = frozenset({
    "uri", "sha256", "bytes", "source_sha256", "normalized_sha256",
    "snapshot_storage", "transformation_id",
})
FREEZE_MANIFEST_FIELDS = frozenset({"snapshot_frozen", SOURCE_FIELD})

# Frozen-input recovery (backend/frozen_input_recovery.py uses these sets, so
# the publisher and the resolver cannot drift apart).
RECOVERY_ORIGIN_FIELD = "frozen_recovery_origin"
RECOVERY_ORIGIN_SCHEMA = "value.frozen-input-recovery-origin/v1"
RECOVERY_BINDING_PROVENANCE_FIELD = "frozen_recovery_provenance"
RECOVERY_QUALIFICATION_FIELDS = frozenset({
    "installation", "validation", "validation_status", "contract_validation_status",
    "scientific_validation_status", "scientific_baseline_eligible", "scientific_baseline_status",
    "owner_approval", "pack_revision_sha256", "manifest_sha256", "snapshot_frozen", SOURCE_FIELD,
    "copy_origin", "overlay_editor_provenance", RECOVERY_ORIGIN_FIELD,
})
# Top-level fields recovery sets on the new pack (besides the qualification
# fields above); ``data_pack_type`` is compared separately (always "base").
RECOVERY_REWRITTEN_FIELDS = frozenset({"id", "name", "data_pack_type", "created_at", "updated_at"})
RECOVERY_BINDING_HISTORY_FIELDS = frozenset({
    "adapter", "mapping_provenance", RECOVERY_BINDING_PROVENANCE_FIELD, "source_uri", "snapshot_uri",
    "source_sha256", "normalized_sha256", "transformation_id", "snapshot_storage", "validation",
})
# Binding fields recovery sets on every recovered binding.
RECOVERY_BINDING_SET_FIELDS = frozenset({"role", "uri", "sha256", "bytes", "binding_revision", "imported_at"})
MAX_IDENTITY_DEPTH = 8


def recovery_history_binding_field(name: str) -> bool:
    """Is a binding field moved into the recovery provenance (not active metadata)?"""

    return (name in RECOVERY_BINDING_HISTORY_FIELDS or name.endswith("_uri") or name.endswith("_path")
            or "provenance" in name)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def source_record(manifest: Mapping[str, object], manifest_bytes: bytes | None = None) -> dict[str, object]:
    """The record a frozen manifest carries about its source manifest.

    ``manifest_bytes`` are the source manifest file bytes and must parse to
    ``manifest``; without them the canonical JSON text stands in (its file sha
    is then the canonical sha).
    """

    if manifest_bytes is None:
        text = _canonical(dict(manifest))
    else:
        text = manifest_bytes.decode("utf-8")
        if _canonical(json.loads(text)) != _canonical(dict(manifest)):
            raise ValueError("The source manifest bytes do not describe the manifest being frozen")
    return {
        "schema_version": SOURCE_SCHEMA,
        "canonical_sha256": canonical_sha256(dict(manifest)),
        "file_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "manifest_text": text,
    }


def verified_record(record: object) -> tuple[dict[str, object], bytes] | None:
    """(source manifest, its file bytes) of a self-consistent source record, else ``None``."""

    if not isinstance(record, Mapping) or record.get("schema_version") != SOURCE_SCHEMA:
        return None
    text = record.get("manifest_text")
    if not isinstance(text, str):
        return None
    try:
        raw = text.encode("utf-8")
        parsed = json.loads(text)
    except (UnicodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    if hashlib.sha256(raw).hexdigest() != record.get("file_sha256"):
        return None
    if canonical_sha256(parsed) != record.get("canonical_sha256"):
        return None
    return parsed, raw


def _lower(value: object) -> str:
    return str(value or "").lower()


def _without(mapping: Mapping[str, object], drop) -> str:
    return _canonical({key: value for key, value in mapping.items() if not drop(key)})


def _frozen_binding_consistent(frozen: object, source: object) -> bool:
    if not isinstance(frozen, Mapping) or not isinstance(source, Mapping):
        return False
    source_sha = _lower(source.get("sha256"))
    if len(source_sha) != 64 or _lower(frozen.get("source_sha256")) != source_sha:
        return False
    rewritten = set(FREEZE_REWRITTEN_BINDING_FIELDS)
    if isinstance(source.get("adapter"), Mapping):
        rewritten.add("format")
    elif (frozen.get("transformation_id") != IDENTITY_TRANSFORMATION
          or _lower(frozen.get("sha256")) != source_sha):
        return False
    return _without(frozen, rewritten.__contains__) == _without(source, rewritten.__contains__)


def _same_roles(left: object, right: object) -> bool:
    return isinstance(left, Mapping) and isinstance(right, Mapping) and set(left) == set(right)


def frozen_source(manifest: Mapping[str, object]) -> tuple[dict[str, object], bytes] | None:
    """(source manifest, source file bytes) of a snapshot-frozen manifest, else ``None``."""

    if manifest.get("snapshot_frozen") is not True:
        return None
    verified = verified_record(manifest.get(SOURCE_FIELD))
    if verified is None:
        return None
    source, raw = verified
    frozen_bindings, source_bindings = manifest.get("bindings"), source.get("bindings")
    if not _same_roles(frozen_bindings, source_bindings):
        return None
    if not all(_frozen_binding_consistent(frozen_bindings[role], source_bindings[role])  # type: ignore[index]
               for role in frozen_bindings):  # type: ignore[union-attr]
        return None
    fixed = FREEZE_MANIFEST_FIELDS | {"bindings"}
    if _without(manifest, fixed.__contains__) != _without(source, fixed.__contains__):
        return None
    return copy.deepcopy(source), raw


def _recovered_binding_consistent(role: str, recovered: object, source: object) -> bool:
    if not isinstance(recovered, Mapping) or not isinstance(source, Mapping):
        return False
    source_sha = _lower(source.get("sha256"))
    if len(source_sha) != 64 or "adapter" in source or _lower(recovered.get("sha256")) != source_sha:
        return False
    if recovered.get("role") != role or source.get("role", role) != role:
        return False
    if "bytes" in source and _canonical(recovered.get("bytes")) != _canonical(source.get("bytes")):
        return False

    def drop(name: str) -> bool:
        return name in RECOVERY_BINDING_SET_FIELDS or recovery_history_binding_field(name)

    return _without(recovered, drop) == _without(source, drop)


def recovered_source(manifest: Mapping[str, object]) -> tuple[dict[str, object], bytes] | None:
    """(source manifest, source file bytes) of a recovered base pack with the source's content, else ``None``."""

    if manifest.get("snapshot_frozen") is True:
        return None
    origin = manifest.get(RECOVERY_ORIGIN_FIELD)
    if not isinstance(origin, Mapping) or origin.get("schema_version") != RECOVERY_ORIGIN_SCHEMA:
        return None
    qualification = origin.get("source_qualification")
    if not isinstance(qualification, Mapping) or qualification.get("snapshot_frozen") is not True:
        return None
    verified = verified_record(qualification.get(SOURCE_FIELD))
    if verified is None:
        return None
    source, raw = verified
    if origin.get("source_pack_id") != source.get("id"):
        return None
    if manifest.get("data_pack_type") != "base" or source.get("data_pack_type", "base") != "base":
        return None
    recovered_bindings, source_bindings = manifest.get("bindings"), source.get("bindings")
    if not _same_roles(recovered_bindings, source_bindings):
        return None
    if not all(_recovered_binding_consistent(str(role), recovered_bindings[role], source_bindings[role])  # type: ignore[index]
               for role in recovered_bindings):  # type: ignore[union-attr]
        return None
    rewritten = RECOVERY_QUALIFICATION_FIELDS | RECOVERY_REWRITTEN_FIELDS | {"bindings"}
    if _without(manifest, rewritten.__contains__) != _without(source, rewritten.__contains__):
        return None
    return copy.deepcopy(source), raw


def source_manifest(manifest: Mapping[str, object]) -> dict[str, object] | None:
    """The verified source manifest of a snapshot-frozen manifest, else ``None``."""

    found = frozen_source(manifest)
    return found[0] if found is not None else None


@dataclass(frozen=True)
class PackIdentity:
    """The manifest a whitelist compares, and the sha candidates of its content.

    ``chain`` lists the verified steps taken (``"snapshot"``, ``"recovery"``);
    ``unverified`` names the copy kind whose identity could not be verified
    (``"snapshot"`` or ``"recovery"``), else ``None``.
    """

    manifest: Mapping[str, object]
    sha256_candidates: frozenset[str]
    chain: tuple[str, ...]
    unverified: str | None


def resolve_pack_identity(manifest: Mapping[str, object], manifest_bytes: bytes | None = None) -> PackIdentity:
    """The one identity resolver for whitelist checks (preflight and worker alike).

    Follows verified frozen-copy and recovered-pack steps back to the original
    manifest.  Its sha candidates are its canonical-JSON sha and, when the file
    bytes are known (given for the input manifest, verified record text for a
    resolved one), the file sha.
    """

    current: Mapping[str, object] = manifest
    raw = manifest_bytes
    chain: list[str] = []
    for _ in range(MAX_IDENTITY_DEPTH):
        step = frozen_source(current)
        kind = "snapshot"
        if step is None:
            step = recovered_source(current)
            kind = "recovery"
        if step is None:
            break
        current, raw = step
        chain.append(kind)
    shas = {canonical_sha256(dict(current))}
    if raw is not None:
        shas.add(hashlib.sha256(raw).hexdigest())
    unverified = None
    if current.get("snapshot_frozen") is True:
        unverified = "snapshot"
    elif current.get(RECOVERY_ORIGIN_FIELD) is not None:
        unverified = "recovery"
    return PackIdentity(current, frozenset(shas), tuple(chain), unverified)
