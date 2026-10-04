"""Transactional data-binding promotion."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Mapping, Sequence

from .data_pack_validation import validate_data_pack


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def promote_binding_revision(
    *,
    pack_root: Path,
    manifest: Mapping[str, object],
    role: str,
    staged_file: Path,
    filename: str,
    file_format: str,
    dataset_slots: Sequence[Mapping[str, object]],
    imported_at: str,
    metadata: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Validate a candidate and atomically promote only the manifest pointer."""

    digest = sha256_file(staged_file)
    safe_name = Path(filename).name
    destination = (
        pack_root / "files" / role.replace(".", "__") / f"{digest[:12]}--{safe_name}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = not destination.exists()
    if destination.exists():
        if sha256_file(destination) != digest:
            raise ValueError("Existing binding revision has a conflicting digest")
        staged_file.unlink(missing_ok=True)
    else:
        os.replace(staged_file, destination)
    binding = {
        "role": role,
        "uri": destination.relative_to(pack_root).as_posix(),
        "filename": safe_name,
        "format": file_format,
        "bytes": destination.stat().st_size,
        "sha256": digest,
        "imported_at": imported_at,
        "binding_revision": digest,
        **dict(metadata or {}),
    }
    provisional = dict(manifest)
    bindings = {key: dict(value) for key, value in dict(manifest.get("bindings") or {}).items()}
    bindings[role] = binding
    provisional["bindings"] = bindings
    report = validate_data_pack(pack_root, provisional, dataset_slots)
    role_report = next(row for row in report["bindings"] if row["role"] == role)
    if role_report["status"] == "failed":
        # A content-addressed candidate is unreferenced and safe to remove. The
        # previous binding and manifest remain byte-for-byte untouched.
        if created:
            destination.unlink(missing_ok=True)
        raise ValueError("; ".join(role_report["errors"]))
    binding["validation"] = {
        "status": role_report["status"],
        "warnings": list(role_report["warnings"]),
        "details": dict(role_report.get("details") or {}),
    }
    bindings[role] = binding
    provisional["bindings"] = bindings
    provisional["updated_at"] = imported_at
    manifest_path = pack_root / "manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(provisional, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, manifest_path)
    return binding, role_report
