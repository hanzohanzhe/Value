"""Freeze and verify Prompt122 readiness evidence beside a run snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Mapping

from .module_context import RunStaticContext, YearContext, canonical_context_sha256


RESOURCE_READINESS_SCHEMA_VERSION = "value.resource-readiness-snapshot/v1"
RESOURCE_READINESS_FILENAME = "resource-readiness.json"


class ResourceSnapshotMismatch(RuntimeError):
    pass


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_evidence(evidence: Mapping[str, object]) -> dict[str, object]:
    required = {
        "trace_profile", "run_context_sha256", "year_context_sha256",
        "calibration_key", "calibration_basis", "free_space_observation",
        "quota_decision", "selected_output_root",
    }
    missing = sorted(required - set(evidence))
    if missing:
        raise ResourceSnapshotMismatch(
            "Resource readiness evidence is incomplete: " + ", ".join(missing)
        )
    payload = dict(evidence)
    payload["schema_version"] = RESOURCE_READINESS_SCHEMA_VERSION
    if payload["trace_profile"] not in {"off", "summary", "full"}:
        raise ResourceSnapshotMismatch("Frozen resource trace profile is invalid")
    for field in ("run_context_sha256", "year_context_sha256"):
        value = str(payload[field])
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ResourceSnapshotMismatch(f"Frozen {field} is not a lowercase SHA-256")
    return payload


def freeze_resource_readiness(
    snapshot_root: Path, evidence: Mapping[str, object]
) -> dict[str, object]:
    """Add immutable readiness evidence before a worker is allowed to start."""

    snapshot_root = Path(snapshot_root)
    manifest_path = snapshot_root / "snapshot.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceSnapshotMismatch("Base run input snapshot is missing or corrupt") from exc
    if not isinstance(manifest, dict):
        raise ResourceSnapshotMismatch("Base run input snapshot manifest is not an object")
    payload = _validate_evidence(evidence)
    payload_sha256 = _hash(payload)
    destination = snapshot_root / RESOURCE_READINESS_FILENAME
    if destination.exists():
        raise ResourceSnapshotMismatch("Resource readiness is already frozen")
    _atomic_json(destination, payload)
    updated = dict(manifest)
    updated["resource_readiness_sha256"] = payload_sha256
    updated["resource_readiness_path"] = RESOURCE_READINESS_FILENAME
    identity = {
        "base_input_tree_sha256": manifest.get("input_tree_sha256"),
        "resource_readiness_sha256": payload_sha256,
    }
    updated["input_tree_sha256"] = _hash(identity)
    updated["snapshot_id"] = _hash({
        "base_snapshot_id": manifest.get("snapshot_id"),
        **identity,
    })
    _atomic_json(manifest_path, updated)
    return payload


def verify_frozen_resource_readiness(
    snapshot_root: Path,
    *,
    project: Mapping[str, object],
    selected_output_root: Path,
    actual_run_context: RunStaticContext,
    actual_year_context: YearContext,
    actual_calibration_key: Mapping[str, object],
) -> dict[str, object]:
    snapshot_root = Path(snapshot_root)
    try:
        manifest = json.loads((snapshot_root / "snapshot.json").read_text(encoding="utf-8"))
        payload = json.loads(
            (snapshot_root / RESOURCE_READINESS_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceSnapshotMismatch("Frozen resource readiness is missing or corrupt") from exc
    if not isinstance(manifest, Mapping) or not isinstance(payload, Mapping):
        raise ResourceSnapshotMismatch("Frozen resource readiness is not a JSON object")
    verified = _validate_evidence(payload)
    if _hash(verified) != manifest.get("resource_readiness_sha256"):
        raise ResourceSnapshotMismatch("Frozen resource readiness hash changed after enqueue")
    runtime = dict(project.get("runtime_options") or project.get("runtime_controls") or {})
    trace = str(runtime.get("runtime.market_trace_level") or "summary")
    if trace != verified["trace_profile"]:
        raise ResourceSnapshotMismatch("Frozen trace profile changed after readiness")
    if Path(str(verified["selected_output_root"])).resolve() != Path(selected_output_root).resolve():
        raise ResourceSnapshotMismatch("Selected output root changed after readiness")
    if canonical_context_sha256(actual_run_context) != verified["run_context_sha256"]:
        raise ResourceSnapshotMismatch("Run context identity changed after readiness")
    if canonical_context_sha256(actual_year_context) != verified["year_context_sha256"]:
        raise ResourceSnapshotMismatch("Year context identity changed after readiness")
    if dict(actual_calibration_key) != dict(verified["calibration_key"]):
        raise ResourceSnapshotMismatch("Resource calibration key changed after readiness")
    if not bool(dict(verified["quota_decision"]).get("accepted")):
        raise ResourceSnapshotMismatch("Frozen resource quota decision was not accepted")
    return verified
