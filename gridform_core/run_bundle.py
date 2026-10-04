"""Safe portable run-bundle export and validation.

Imported archives are treated strictly as data.  Executable files and legacy
pickle checkpoints are prohibited.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Sequence


PROFILES = {"compact_results", "complete_audit", "checkpoint_capable"}
PROHIBITED_SUFFIXES = {".py", ".pyc", ".pyo", ".pkl", ".pickle", ".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh", ".js", ".jar"}
MAX_FILES = 20_000
MAX_UNCOMPRESSED_BYTES = 20 * 1024**3
IMPORT_DIRECTORY_DIGEST_CHARS = 20
IMPORT_DIGEST_MARKER = ".force-import-sha256"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _included(relative: str, profile: str) -> bool:
    if relative in {"status.json", "provenance.json", "preflight.json"}:
        return True
    if not relative.startswith("model-output/"):
        return False
    if profile == "complete_audit":
        return True
    if profile == "checkpoint_capable":
        return True
    if relative in {
        "model-output/market/market.sqlite",
        "model-output/market/metadata.json",
        "model-output/market/index.json",
        "model-output/network/vre-curtailment-attribution.json",
    } or relative.startswith("model-output/market/context/"):
        return True
    return any(token in relative for token in (
        "modular-run.json", "resolved-run.json", "year-results-v2.json", "ledgers/",
        "planning/summary", "planning/typed-summary", "terminal/", "validation/",
    ))


def export_run_bundle(run_root: Path, destination: Path, *, profile: str) -> dict[str, object]:
    if profile not in PROFILES:
        raise ValueError("Unknown export profile")
    run_root = run_root.resolve()
    entries = []
    for path in sorted(run_root.rglob("*")):
        if not path.is_file() or path.name.endswith((".tmp", ".wal", ".shm")):
            continue
        relative = path.relative_to(run_root).as_posix()
        if not _included(relative, profile):
            continue
        if path.suffix.lower() in PROHIBITED_SUFFIXES:
            continue
        if profile == "compact_results" and "/checkpoints" in f"/{relative}":
            continue
        entries.append({"path": relative, "bytes": path.stat().st_size, "sha256": _sha(path)})
    included_paths = {str(row["path"]) for row in entries}
    market_ledgers: list[dict[str, object]] = []
    for row in entries:
        relative = PurePosixPath(str(row["path"]))
        if relative.name != "metadata.json":
            continue
        database_relative = (relative.parent / "market.sqlite").as_posix()
        if database_relative not in included_paths:
            continue
        try:
            metadata = json.loads(
                (run_root / relative).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
        if metadata.get("schema_version") != "value.market-ledger/v8":
            continue
        market_ledgers.append({
            "database_path": database_relative,
            "schema_version": metadata.get("schema_version"),
            "context_hashes": metadata.get("context_hashes"),
            "science_root_by_year": metadata.get("science_root_by_year"),
            "evidence_root_by_year": metadata.get("evidence_root_by_year"),
            "row_counts": metadata.get("rows"),
            "trace_coverage_by_year": metadata.get("trace_coverage_by_year"),
        })
    manifest = {
        "schema_version": "value.portable-run-bundle/v1", "profile": profile,
        "run_id": run_root.name, "resumable": profile == "checkpoint_capable",
        "source_data_included": False,
        "legacy_pickle_included": False,
        "files": entries,
        "market_ledgers": market_ledgers,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("bundle-manifest.json", json.dumps(manifest, indent=2))
        for entry in entries:
            archive.write(run_root / str(entry["path"]), str(entry["path"]))
    temporary.replace(destination)
    return manifest | {"archive_path": str(destination), "archive_bytes": destination.stat().st_size}


def validate_bundle_archive(archive_path: Path) -> dict[str, object]:
    errors: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES:
            errors.append("archive_file_count_limit")
        total = sum(item.file_size for item in infos)
        if total > MAX_UNCOMPRESSED_BYTES:
            errors.append("archive_uncompressed_size_limit")
        names = [item.filename for item in infos]
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or "\x00" in name:
                errors.append(f"unsafe_path:{name}")
            if path.suffix.lower() in PROHIBITED_SUFFIXES:
                errors.append(f"executable_payload:{name}")
        if "bundle-manifest.json" not in names:
            errors.append("manifest_missing")
            manifest = {}
        else:
            try:
                manifest = json.loads(archive.read("bundle-manifest.json"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                manifest = {}; errors.append("manifest_invalid")
        if manifest.get("schema_version") != "value.portable-run-bundle/v1":
            errors.append("manifest_schema_incompatible")
        declared = {str(row.get("path")): row for row in manifest.get("files", []) if isinstance(row, dict)}
        for name, row in declared.items():
            if name not in names:
                errors.append(f"declared_file_missing:{name}"); continue
            if hashlib.sha256(archive.read(name)).hexdigest() != row.get("sha256"):
                errors.append(f"hash_mismatch:{name}")
        undeclared = set(names).difference(declared).difference({"bundle-manifest.json"})
        if undeclared:
            errors.append("undeclared_payload:" + ",".join(sorted(undeclared)[:10]))
    return {
        "schema_version": "value.portable-run-bundle-validation/v1",
        "valid": not errors, "errors": errors, "profile": manifest.get("profile"),
        "resumable": bool(manifest.get("resumable")) and not errors,
        "uncompressed_bytes": total,
    }


def import_bundle_archive(archive_path: Path, staging_root: Path) -> Path:
    report = validate_bundle_archive(archive_path)
    if not report["valid"]:
        raise ValueError("Bundle rejected: " + "; ".join(report["errors"]))
    digest = _sha(archive_path)
    staging_root = staging_root.resolve()
    staging_root.mkdir(parents=True, exist_ok=True)
    directory_key = digest[:IMPORT_DIRECTORY_DIGEST_CHARS]
    destination = staging_root / directory_key
    if destination.exists():
        marker = destination / IMPORT_DIGEST_MARKER
        if marker.is_file() and marker.read_text(encoding="ascii").strip() == digest:
            return destination
        raise ValueError("Portable bundle import-key collision or incomplete destination")
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{directory_key}-", suffix=".staging", dir=staging_root)
    )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                target = (temporary / PurePosixPath(info.filename)).resolve()
                target.relative_to(temporary.resolve())
                target.parent.mkdir(parents=True, exist_ok=True)
                if not info.is_dir():
                    with archive.open(info) as source, target.open("wb") as output:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
        (temporary / IMPORT_DIGEST_MARKER).write_text(digest + "\n", encoding="ascii")
        temporary.replace(destination)
    except Exception:
        import shutil
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination
