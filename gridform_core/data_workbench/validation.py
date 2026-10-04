"""Independent, non-mutating validation gates for Data Workbench candidates."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

from .contracts import ValidationIssue, ValidationReport


CANDIDATE_SCHEMA = "value.data-workbench-candidate/v1"
WAIVER_SUFFIXES = (
    ".symmetric_forward_fallback",
    ".capacity_weighted_country_split",
    ".nearest_coast_dso_inference",
    ".static_share_fallback",
)


def registered_waiver(waiver_id: str) -> bool:
    return any(waiver_id.endswith(suffix) for suffix in WAIVER_SUFFIXES)


def candidate_identity(payload: Mapping[str, object]) -> str:
    canonical = dict(payload)
    canonical.pop("candidate_id", None)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "candidate-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def _issue(
    code: str,
    gate: str,
    message: str,
    repair: str,
    *,
    evidence: Mapping[str, object] | None = None,
    waivable: bool = False,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity="waiver_required" if waivable else "blocking",
        artifact_role=gate,
        message=message,
        evidence=evidence or {},
        repair=repair,
        waivable=waivable,
    )


def _rights_gate(payload: Mapping[str, object], _: Path, __: str | None) -> list[ValidationIssue]:
    accepted = {"redistributable", "pointer_only", "local_use_only"}
    rows = payload.get("source_rights")
    if not isinstance(rows, list) or not rows:
        return [_issue("DW-RIGHTS-001", "source_rights", "Candidate has no source-rights records", "Add reviewed rights decisions for every source")]
    invalid = [
        str(row.get("source_id") or "unknown")
        for row in rows if not isinstance(row, Mapping)
        or str(row.get("redistribution_decision") or "") not in accepted
    ]
    return [] if not invalid else [
        _issue(
            "DW-RIGHTS-001",
            "source_rights",
            "One or more source rights decisions remain unresolved",
            "Complete rights review; rights failures cannot be waived",
            evidence={"source_ids": sorted(invalid)},
        )
    ]


def _safe_artifact(root: Path, relative: str) -> Path | None:
    key = PurePosixPath(relative)
    if key.is_absolute() or not key.parts or any(part in {"", ".", ".."} for part in key.parts):
        return None
    target = (root / Path(*key.parts)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def _schema_hash_gate(payload: Mapping[str, object], root: Path, _: str | None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if payload.get("schema_version") != CANDIDATE_SCHEMA:
        issues.append(_issue("DW-SCHEMA-001", "schema_hash", f"Expected {CANDIDATE_SCHEMA}", "Rebuild the candidate with a compatible compiler"))
    artifact_hashes = payload.get("artifact_hashes")
    if not isinstance(artifact_hashes, Mapping):
        return issues + [_issue("DW-HASH-001", "schema_hash", "Candidate has no artifact hash inventory", "Rebuild and pin every candidate artifact")]
    pack_root = root / "pack"
    if not artifact_hashes or not (pack_root / "manifest.json").is_file():
        issues.append(
            _issue(
                "DW-PACK-001",
                "schema_hash",
                "Candidate is a scientific review artifact, not a promotable VALUE data pack",
                "Assemble and validate pack/manifest.json plus its complete artifact hash inventory",
            )
        )
    actual = {
        path.relative_to(root).as_posix()
        for path in pack_root.rglob("*")
        if path.is_file()
    } if pack_root.is_dir() else set()
    declared = {str(key) for key in artifact_hashes}
    failed: list[str] = sorted(actual ^ declared)
    for relative, expected in artifact_hashes.items():
        path = _safe_artifact(root, str(relative))
        if (
            path is None
            or not path.is_file()
            or not re.fullmatch(r"[0-9a-f]{64}", str(expected))
            or hashlib.sha256(path.read_bytes()).hexdigest() != str(expected)
        ):
            failed.append(str(relative))
    if failed:
        issues.append(
            _issue(
                "DW-HASH-001",
                "schema_hash",
                "Candidate artifact inventory or SHA-256 identity failed",
                "Restore pinned bytes or rebuild a new candidate",
                evidence={"artifacts": sorted(set(failed))},
            )
        )
    return issues


def _topology_gate(payload: Mapping[str, object], _: Path, __: str | None) -> list[ValidationIssue]:
    topology = payload.get("spatial_topology")
    if not isinstance(topology, Mapping):
        return [_issue("DW-TOPOLOGY-001", "spatial_topology", "Candidate lacks spatial/topology evidence", "Run spatial and topology validation")]
    dangling = list(topology.get("dangling_references") or [])
    failed = dangling or topology.get("connected") is not True or topology.get("map_ids_reconcile") is not True
    return [] if not failed else [
        _issue(
            "DW-TOPOLOGY-001",
            "spatial_topology",
            "Spatial references, connectivity or audit-map IDs do not reconcile",
            "Repair topology and rebuild; reference failures cannot be waived",
            evidence={"dangling_references": dangling},
        )
    ]


def _scientific_gate(payload: Mapping[str, object], _: Path, __: str | None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    reconciliation = payload.get("scientific_reconciliation")
    if not isinstance(reconciliation, Mapping):
        issues.append(_issue("DW-CONSERVATION-001", "scientific_reconciliation", "Candidate lacks reconciliation evidence", "Run demand and profile conservation checks"))
    else:
        residuals = {
            str(key): float(value)
            for key, value in reconciliation.items()
            if str(key).endswith(("residual_mwh", "residual_mw"))
        }
        bad = {key: value for key, value in residuals.items() if not math.isfinite(value) or abs(value) > 1e-8}
        if bad:
            issues.append(
                _issue(
                    "DW-CONSERVATION-001",
                    "scientific_reconciliation",
                    "Demand or exchange conservation exceeds tolerance",
                    "Repair the compiler; conservation failures cannot be waived",
                    evidence=bad,
                )
            )
    requested = [str(item) for item in payload.get("requested_waivers", [])]  # type: ignore[arg-type]
    for waiver_id in sorted(set(requested)):
        if not registered_waiver(waiver_id):
            issues.append(
                _issue(
                    "DW-WAIVER-UNKNOWN",
                    "scientific_reconciliation",
                    f"Unknown scientific waiver {waiver_id}",
                    "Register an allowed scientific approximation or remove it",
                    evidence={"waiver_id": waiver_id},
                )
            )
        else:
            issues.append(
                _issue(
                    "DW-SCI-WAIVER-001",
                    "scientific_reconciliation",
                    f"Scientific approximation requires explicit acceptance: {waiver_id}",
                    "Review the assumption and accept this exact waiver during promotion",
                    evidence={"waiver_id": waiver_id},
                    waivable=True,
                )
            )
    return issues


def _determinism_gate(payload: Mapping[str, object], _: Path, __: str | None) -> list[ValidationIssue]:
    expected = candidate_identity(payload)
    actual = str(payload.get("candidate_id") or "")
    return [] if actual == expected else [
        _issue(
            "DW-DETERMINISM-001",
            "determinism_regression",
            "Candidate ID does not match its canonical scientific metadata",
            "Rebuild the candidate; never edit a candidate in place",
            evidence={"declared": actual, "computed": expected},
        )
    ]


def _owner_gate(payload: Mapping[str, object], _: Path, reviewer: str | None) -> list[ValidationIssue]:
    if reviewer and reviewer.strip():
        return []
    return [
        _issue(
            "DW-OWNER-001",
            "owner_review",
            "Candidate has not received a named local owner approval",
            "Submit a PromotionRequest with the responsible reviewer's name",
        )
    ]


_VALIDATORS: tuple[tuple[str, Callable[[Mapping[str, object], Path, str | None], list[ValidationIssue]]], ...] = (
    ("source_rights", _rights_gate),
    ("schema_hash", _schema_hash_gate),
    ("spatial_topology", _topology_gate),
    ("scientific_reconciliation", _scientific_gate),
    ("determinism_regression", _determinism_gate),
    ("owner_review", _owner_gate),
)


def validate_candidate_directory(
    candidate_root: Path, *, reviewer: str | None = None
) -> ValidationReport:
    root = Path(candidate_root).resolve()
    manifest_path = root / "workbench-candidate.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Candidate manifest is missing or unreadable") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("Candidate manifest must be a JSON object")
    issues: list[ValidationIssue] = []
    gate_results: dict[str, str] = {}
    for name, validator in _VALIDATORS:
        observed = validator(payload, root, reviewer)
        issues.extend(observed)
        if not observed:
            gate_results[name] = "passed"
        elif all(issue.waivable for issue in observed):
            gate_results[name] = "waiver_required"
        elif name == "owner_review" and reviewer is None:
            gate_results[name] = "pending"
        else:
            gate_results[name] = "blocked"
    return ValidationReport(
        candidate_id=str(payload.get("candidate_id") or ""),
        status="passed" if not issues else "blocked",
        issues=tuple(issues),
        gate_results=gate_results,
    )
