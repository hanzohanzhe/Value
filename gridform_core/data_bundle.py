"""Deterministic, non-executable VALUE data bundles and atomic installation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from .data_pack_validation import validate_data_pack


BUNDLE_SCHEMA = "value.data-bundle/v1"
BUNDLE_DESCRIPTOR = "value-data-bundle.json"
PACK_MANIFEST = "manifest.json"
INSTALLATION_SCHEMA = "value.data-bundle-installation/v1"
MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 3 * 1024 * 1024 * 1024
MAX_MEMBERS = 5_000
MAX_DESCRIPTOR_BYTES = 8 * 1024 * 1024
MIN_FREE_SPACE_BYTES = 1024 * 1024 * 1024
PACK_ID = re.compile(r"^[a-z][a-z0-9-]{2,127}$")
FORBIDDEN_SUFFIXES = {
    ".7z", ".bat", ".cmd", ".com", ".dll", ".dylib", ".exe", ".jar",
    ".msi", ".pickle", ".pkl", ".ps1", ".py", ".pyc", ".pyd", ".pyo",
    ".sh", ".so", ".tar", ".tgz", ".zip",
}
ALLOWED_ROOT_FILES = {
    PACK_MANIFEST,
    "RIGHTS.json",
    "LICENSE",
    "ATTRIBUTION.md",
    "README.md",
    "semantic-preflight.json",
}


class DataBundleError(ValueError):
    """Stable, user-facing data-bundle failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedDataBundle:
    descriptor: Mapping[str, object]
    members: tuple[str, ...]
    bundle_sha256: str
    bundle_bytes: int
    uncompressed_bytes: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _member_name(raw: str) -> str:
    if "\\" in raw or "\x00" in raw:
        raise DataBundleError("GF_DATA_BUNDLE_PATH", "Bundle paths must use portable '/' names")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise DataBundleError("GF_DATA_BUNDLE_PATH", f"Unsafe data-bundle path: {raw}")
    if ":" in path.parts[0]:
        raise DataBundleError("GF_DATA_BUNDLE_PATH", f"Drive-qualified path is forbidden: {raw}")
    return path.as_posix()


def _validate_layout(name: str) -> None:
    path = PurePosixPath(name)
    if name == BUNDLE_DESCRIPTOR:
        return
    if len(path.parts) == 1 and name not in ALLOWED_ROOT_FILES:
        raise DataBundleError("GF_DATA_BUNDLE_LAYOUT", f"Unexpected root member: {name}")
    if len(path.parts) > 1 and path.parts[0] != "files":
        raise DataBundleError("GF_DATA_BUNDLE_LAYOUT", f"Data objects must be under files/: {name}")
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise DataBundleError("GF_DATA_BUNDLE_EXECUTABLE", f"Executable or nested archive is forbidden: {name}")


def _archive_metadata(path: Path) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo], list[str], int]:
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise DataBundleError("GF_DATA_BUNDLE_FORMAT", "Select a VALUE .zip data bundle")
    size = path.stat().st_size
    if size > MAX_BUNDLE_BYTES:
        raise DataBundleError("GF_DATA_BUNDLE_SIZE", "Data bundle exceeds the 2 GiB limit")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise DataBundleError("GF_DATA_BUNDLE_FORMAT", "The selected data bundle is not a readable ZIP") from exc
    infos = [info for info in archive.infolist() if not info.is_dir()]
    if len(infos) > MAX_MEMBERS:
        archive.close()
        raise DataBundleError("GF_DATA_BUNDLE_MEMBERS", "Data bundle contains too many objects")
    names = [_member_name(info.filename) for info in infos]
    if len(names) != len(set(names)) or len(names) != len({name.casefold() for name in names}):
        archive.close()
        raise DataBundleError("GF_DATA_BUNDLE_DUPLICATE", "Data bundle contains duplicate paths")
    total = sum(info.file_size for info in infos)
    if total > MAX_UNCOMPRESSED_BYTES:
        archive.close()
        raise DataBundleError("GF_DATA_BUNDLE_EXPANSION", "Expanded data bundle exceeds 3 GiB")
    for info, name in zip(infos, names):
        if info.flag_bits & 0x1:
            archive.close()
            raise DataBundleError("GF_DATA_BUNDLE_ENCRYPTED", f"Encrypted member is forbidden: {name}")
        mode = info.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            archive.close()
            raise DataBundleError("GF_DATA_BUNDLE_LINK", f"Links are forbidden: {name}")
        if info.file_size > 1024 * 1024 and info.compress_size > 0 and info.file_size / info.compress_size > 1000:
            archive.close()
            raise DataBundleError("GF_DATA_BUNDLE_RATIO", f"Suspicious compression ratio: {name}")
        _validate_layout(name)
    return archive, infos, names, total


def validate_data_bundle(path: Path) -> ValidatedDataBundle:
    path = path.resolve()
    archive, infos, names, total = _archive_metadata(path)
    with archive:
        required = {BUNDLE_DESCRIPTOR, PACK_MANIFEST}
        missing = sorted(required.difference(names))
        if missing:
            raise DataBundleError("GF_DATA_BUNDLE_REQUIRED", "Data bundle is missing: " + ", ".join(missing))
        descriptor_info = archive.getinfo(BUNDLE_DESCRIPTOR)
        if descriptor_info.file_size > MAX_DESCRIPTOR_BYTES:
            raise DataBundleError("GF_DATA_BUNDLE_DESCRIPTOR", "Data-bundle descriptor is too large")
        try:
            descriptor = json.loads(archive.read(BUNDLE_DESCRIPTOR).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
            raise DataBundleError("GF_DATA_BUNDLE_DESCRIPTOR", "Invalid data-bundle descriptor") from exc
        if not isinstance(descriptor, dict) or descriptor.get("schema_version") != BUNDLE_SCHEMA:
            raise DataBundleError("GF_DATA_BUNDLE_SCHEMA", f"Expected {BUNDLE_SCHEMA}")
        if descriptor.get("manifest") != PACK_MANIFEST:
            raise DataBundleError("GF_DATA_BUNDLE_LAYOUT", "Descriptor must identify manifest.json")
        rights_files = descriptor.get("rights_files")
        if not isinstance(rights_files, list) or not rights_files:
            raise DataBundleError("GF_DATA_BUNDLE_RIGHTS", "Data bundle has no rights/licence record")
        if any(str(name) not in names for name in rights_files):
            raise DataBundleError("GF_DATA_BUNDLE_RIGHTS", "Declared rights/licence record is missing")
        inventory = descriptor.get("files")
        if not isinstance(inventory, list) or not all(isinstance(row, dict) for row in inventory):
            raise DataBundleError("GF_DATA_BUNDLE_INVENTORY", "Descriptor has no valid file inventory")
        declared = {str(row.get("path")): row for row in inventory}
        actual = set(names).difference({BUNDLE_DESCRIPTOR})
        if set(declared) != actual or len(declared) != len(inventory):
            raise DataBundleError("GF_DATA_BUNDLE_INVENTORY", "Descriptor inventory does not match archive members")
        for name, row in declared.items():
            if row.get("bytes") != archive.getinfo(name).file_size:
                raise DataBundleError("GF_DATA_BUNDLE_INVENTORY", f"Byte count mismatch: {name}")
            if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256") or "")):
                raise DataBundleError("GF_DATA_BUNDLE_INVENTORY", f"Invalid SHA-256: {name}")
        try:
            manifest = json.loads(archive.read(PACK_MANIFEST).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DataBundleError("GF_DATA_BUNDLE_MANIFEST", "manifest.json is invalid") from exc
        if not isinstance(manifest, dict) or manifest.get("schema_version") != "value.data-pack/v1":
            raise DataBundleError("GF_DATA_BUNDLE_MANIFEST", "Expected value.data-pack/v1")
        pack_id = str(manifest.get("id") or "")
        if not PACK_ID.fullmatch(pack_id) or descriptor.get("pack_id") != pack_id:
            raise DataBundleError("GF_DATA_BUNDLE_PACK_ID", "Manifest and descriptor pack IDs must match")
        manifest_hash = hashlib.sha256(archive.read(PACK_MANIFEST)).hexdigest()
        if descriptor.get("pack_revision_sha256") != manifest_hash:
            raise DataBundleError("GF_DATA_BUNDLE_REVISION", "Pack revision does not match manifest.json")
    return ValidatedDataBundle(
        descriptor=descriptor,
        members=tuple(sorted(names)),
        bundle_sha256=_sha256_file(path),
        bundle_bytes=path.stat().st_size,
        uncompressed_bytes=total,
    )


def build_data_bundle(*, pack_root: Path, destination: Path) -> dict[str, object]:
    pack_root = pack_root.resolve()
    manifest_path = pack_root / PACK_MANIFEST
    if not manifest_path.is_file():
        raise DataBundleError("GF_DATA_BUNDLE_MANIFEST", "Data-pack root has no manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pack_id = str(manifest.get("id") or "") if isinstance(manifest, dict) else ""
    if not PACK_ID.fullmatch(pack_id):
        raise DataBundleError("GF_DATA_BUNDLE_PACK_ID", "Data-pack manifest has an invalid ID")
    sources = sorted(
        path for path in pack_root.rglob("*")
        if path.is_file() and not any(part in {"__pycache__", ".pytest_cache"} for part in path.parts)
    )
    names: dict[str, Path] = {}
    for source in sources:
        name = _member_name(source.relative_to(pack_root).as_posix())
        _validate_layout(name)
        names[name] = source
    rights_files = [name for name in ("RIGHTS.json", "LICENSE", "ATTRIBUTION.md") if name in names]
    if not rights_files:
        raise DataBundleError("GF_DATA_BUNDLE_RIGHTS", "Data-pack root needs RIGHTS.json, LICENSE or ATTRIBUTION.md")
    inventory = [
        {"path": name, "bytes": path.stat().st_size, "sha256": _sha256_file(path)}
        for name, path in sorted(names.items())
    ]
    descriptor: dict[str, object] = {
        "schema_version": BUNDLE_SCHEMA,
        "pack_id": pack_id,
        "pack_revision_sha256": _sha256_file(manifest_path),
        "manifest": PACK_MANIFEST,
        "rights_files": rights_files,
        "files": inventory,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        descriptor_info = zipfile.ZipInfo(BUNDLE_DESCRIPTOR, date_time=(1980, 1, 1, 0, 0, 0))
        descriptor_info.compress_type = zipfile.ZIP_DEFLATED
        descriptor_info.external_attr = 0o100644 << 16
        archive.writestr(descriptor_info, _json_bytes(descriptor), compresslevel=9)
        for name, source in sorted(names.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
    os.replace(temporary, destination)
    validated = validate_data_bundle(destination)
    return {
        "schema_version": BUNDLE_SCHEMA,
        "pack_id": pack_id,
        "pack_revision_sha256": descriptor["pack_revision_sha256"],
        "archive": str(destination.resolve()),
        "members": len(validated.members),
        "bytes": validated.bundle_bytes,
        "uncompressed_bytes": validated.uncompressed_bytes,
        "sha256": validated.bundle_sha256,
    }


def _safe_target(root: Path, pack_id: str) -> Path:
    target = (root / pack_id).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise DataBundleError("GF_DATA_BUNDLE_PATH", "Installation target escaped the data root") from exc
    return target


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def install_data_bundle(
    bundle_path: Path,
    *,
    packs_root: Path,
    dataset_slots: Sequence[Mapping[str, object]],
    rights_acknowledged: bool,
    minimum_free_space_bytes: int = MIN_FREE_SPACE_BYTES,
) -> dict[str, object]:
    if not rights_acknowledged:
        raise DataBundleError("GF_DATA_BUNDLE_RIGHTS_ACK", "Acknowledge the data licence and attribution before installation")
    validated = validate_data_bundle(bundle_path)
    root = packs_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    required_space = validated.uncompressed_bytes + max(0, minimum_free_space_bytes)
    available = shutil.disk_usage(root).free
    if available < required_space:
        raise DataBundleError(
            "GF_DATA_BUNDLE_DISK_HEADROOM",
            f"Installation needs {required_space} free bytes; {available} are available",
        )
    staging_root = root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="data-bundle-", dir=staging_root)).resolve()
    payload = stage / "pack"
    payload.mkdir()
    promoted = False
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            inventory = {
                str(row["path"]): row
                for row in validated.descriptor.get("files", [])
                if isinstance(row, dict)
            }
            for name in sorted(inventory):
                target = payload.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with archive.open(name) as source, target.open("wb") as destination:
                    while chunk := source.read(1024 * 1024):
                        destination.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                row = inventory[name]
                if size != row["bytes"] or digest.hexdigest() != row["sha256"]:
                    raise DataBundleError("GF_DATA_BUNDLE_HASH", f"Data object failed verification: {name}")
            (payload / BUNDLE_DESCRIPTOR).write_bytes(archive.read(BUNDLE_DESCRIPTOR))
        manifest = json.loads((payload / PACK_MANIFEST).read_text(encoding="utf-8"))
        pack_id = str(manifest.get("id") or "")
        target = _safe_target(root, pack_id)
        if target.exists():
            existing = target / "installation.json"
            if existing.is_file():
                record = json.loads(existing.read_text(encoding="utf-8"))
                if record.get("bundle_sha256") == validated.bundle_sha256:
                    result = dict(record)
                    result["idempotent"] = True
                    return result
            raise DataBundleError(
                "GF_DATA_BUNDLE_COLLISION",
                "That data-pack ID already exists with different bytes; publish a new versioned pack ID",
            )
        report = validate_data_pack(payload, manifest, dataset_slots)
        if not report.get("valid"):
            raise DataBundleError(
                "GF_DATA_BUNDLE_SEMANTIC",
                "; ".join(str(error) for error in report.get("errors", [])[:10]),
            )
        record: dict[str, object] = {
            "schema_version": INSTALLATION_SCHEMA,
            "pack_id": pack_id,
            "name": manifest.get("name") or pack_id,
            "pack_revision_sha256": validated.descriptor["pack_revision_sha256"],
            "bundle_sha256": validated.bundle_sha256,
            "bundle_bytes": validated.bundle_bytes,
            "uncompressed_bytes": validated.uncompressed_bytes,
            "original_bundle_name": bundle_path.name,
            "original_bundle_retained": False,
            "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "rights_files": list(validated.descriptor.get("rights_files", [])),
            "validation": report["summary"],
            "installation_boundary": "local_data_only_no_executable_content",
        }
        _atomic_json(payload / "installation.json", record)
        os.replace(payload, target)
        promoted = True
        return record
    finally:
        if not promoted and payload.exists():
            shutil.rmtree(payload, ignore_errors=True)
        shutil.rmtree(stage, ignore_errors=True)
