"""The source identity of a Data Pack manifest that survives run-input freezing.

A queued Run executes on ``input-snapshot/pack``: ``run_snapshot._freeze_pack``
rewrites every binding of that copy (``uri``, ``sha256``, ``bytes``, plus the
snapshot fields) and marks the manifest ``snapshot_frozen``.  The frozen copy
therefore never has the manifest sha a methodology profile pins (decision Q3,
the doctoral data-pack whitelist).

At freeze time the snapshot records the source manifest's canonical sha and
its original bindings under :data:`SOURCE_FIELD`.  :func:`source_manifest`
rebuilds the source manifest from a frozen one and returns it only when the
rebuild is consistent with the frozen bindings:

* the role sets are equal;
* every frozen binding's ``source_sha256`` is the source binding's ``sha256``
  (``run_snapshot`` verified the source file against it before copying);
* an identity-transformed binding's frozen ``sha256`` is that same digest (the
  file verifiers - ``verify_run_input_snapshot`` and
  ``frozen_input_integrity`` - tie the frozen file bytes to it);
* every field the freeze does not rewrite is unchanged (adapter, unit, role,
  provenance text ...);
* the rebuilt manifest's canonical sha equals the recorded one.

A recorded source identity that is not consistent is ignored, so a forged or
damaged record never borrows a pinned identity.  No imports beyond the
standard library: ``gridform_core.methodology`` uses this module.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Mapping

SOURCE_FIELD = "snapshot_source_manifest"
SOURCE_SCHEMA = "value.snapshot-source-manifest/v1"
IDENTITY_TRANSFORMATION = "identity/v1"
# Binding fields run_snapshot._freeze_pack rewrites; ``format`` only for an
# adapter binding (the adapter emits the canonical format).
FREEZE_REWRITTEN_BINDING_FIELDS = frozenset({
    "uri", "sha256", "bytes", "source_sha256", "normalized_sha256",
    "snapshot_storage", "transformation_id",
})
_FROZEN_MANIFEST_FIELDS = frozenset({"snapshot_frozen", SOURCE_FIELD, "bindings"})


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def source_record(manifest: Mapping[str, object], manifest_bytes: bytes | None = None) -> dict[str, object]:
    """The record a frozen manifest carries about its source manifest."""

    record: dict[str, object] = {
        "schema_version": SOURCE_SCHEMA,
        "canonical_sha256": canonical_sha256(dict(manifest)),
        "bindings": copy.deepcopy(dict(manifest.get("bindings") or {})),  # type: ignore[arg-type]
    }
    if manifest_bytes is not None:
        record["file_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    return record


def _lower(value: object) -> str:
    return str(value or "").lower()


def _binding_consistent(frozen: object, source: object) -> bool:
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
    kept_frozen = {key: value for key, value in frozen.items() if key not in rewritten}
    kept_source = {key: value for key, value in source.items() if key not in rewritten}
    return kept_frozen == kept_source


def source_manifest(manifest: Mapping[str, object]) -> dict[str, object] | None:
    """The verified source manifest of a snapshot-frozen manifest, else ``None``."""

    if manifest.get("snapshot_frozen") is not True:
        return None
    record = manifest.get(SOURCE_FIELD)
    if not isinstance(record, Mapping) or record.get("schema_version") != SOURCE_SCHEMA:
        return None
    source_bindings = record.get("bindings")
    frozen_bindings = manifest.get("bindings")
    if not isinstance(source_bindings, Mapping) or not isinstance(frozen_bindings, Mapping):
        return None
    if set(source_bindings) != set(frozen_bindings):
        return None
    if not all(_binding_consistent(frozen_bindings[role], source_bindings[role]) for role in frozen_bindings):
        return None
    rebuilt = {key: copy.deepcopy(value) for key, value in manifest.items() if key not in _FROZEN_MANIFEST_FIELDS}
    rebuilt["bindings"] = copy.deepcopy(dict(source_bindings))
    if canonical_sha256(rebuilt) != record.get("canonical_sha256"):
        return None
    return rebuilt
