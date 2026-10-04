"""Deterministic, bounded VALUE external-module bundles."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


BUNDLE_SCHEMA = "value.module-bundle/v1"
BUNDLE_DESCRIPTOR = "force-bundle.json"
MODULE_MANIFEST = "value-module.json"
SOURCE_ROOT = "src"
MAX_BUNDLE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_MEMBERS = 1_000
ALLOWED_SOURCE_SUFFIXES = {
    ".py", ".pyi", ".json", ".csv", ".txt", ".md", ".toml", ".yaml", ".yml",
}
FORBIDDEN_SUFFIXES = {
    ".bat", ".cmd", ".com", ".dll", ".dylib", ".exe", ".msi", ".pyd", ".so",
}


class ModuleBundleError(ValueError):
    """A stable, user-actionable module bundle validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedModuleBundle:
    descriptor: Mapping[str, object]
    manifest: Mapping[str, object]
    members: tuple[str, ...]
    bundle_sha256: str
    bundle_bytes: int
    uncompressed_bytes: int


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _member_name(raw: str) -> str:
    if "\\" in raw:
        raise ModuleBundleError("GF_MODULE_BUNDLE_PATH", "Bundle members must use portable '/' paths")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ModuleBundleError("GF_MODULE_BUNDLE_PATH", f"Unsafe bundle member path: {raw}")
    if ":" in path.parts[0]:
        raise ModuleBundleError("GF_MODULE_BUNDLE_PATH", f"Drive-qualified bundle path is forbidden: {raw}")
    return path.as_posix()


def _validate_source_name(name: str) -> None:
    path = PurePosixPath(name)
    if not path.parts or path.parts[0] != SOURCE_ROOT:
        return
    suffix = path.suffix.lower()
    if suffix in FORBIDDEN_SUFFIXES:
        raise ModuleBundleError(
            "GF_MODULE_BUNDLE_EXECUTABLE",
            f"Native or executable bundle member is forbidden: {name}",
        )
    if suffix and suffix not in ALLOWED_SOURCE_SUFFIXES:
        raise ModuleBundleError(
            "GF_MODULE_BUNDLE_FILE_TYPE",
            f"Unsupported self-contained source member: {name}",
        )


def _inventory_row(name: str, data: bytes) -> dict[str, object]:
    return {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def validate_module_bundle(path: Path) -> ValidatedModuleBundle:
    path = path.resolve()
    if not path.is_file():
        raise ModuleBundleError("GF_MODULE_BUNDLE_MISSING", "Select an existing module ZIP")
    if path.suffix.lower() != ".zip":
        raise ModuleBundleError("GF_MODULE_BUNDLE_FORMAT", "VALUE modules must be supplied as a .zip bundle")
    size = path.stat().st_size
    if size > MAX_BUNDLE_BYTES:
        raise ModuleBundleError("GF_MODULE_BUNDLE_SIZE", "Module bundle exceeds the 25 MiB upload limit")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ModuleBundleError("GF_MODULE_BUNDLE_FORMAT", "The selected file is not a readable ZIP") from exc
    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_MEMBERS:
            raise ModuleBundleError("GF_MODULE_BUNDLE_MEMBERS", "Module bundle contains too many files")
        names = [_member_name(info.filename) for info in infos]
        if len(names) != len(set(names)) or len(names) != len({name.casefold() for name in names}):
            raise ModuleBundleError("GF_MODULE_BUNDLE_DUPLICATE", "Module bundle contains duplicate file names")
        total = sum(info.file_size for info in infos)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ModuleBundleError("GF_MODULE_BUNDLE_EXPANSION", "Expanded module bundle exceeds 100 MiB")
        for info, name in zip(infos, names):
            if info.flag_bits & 0x1:
                raise ModuleBundleError("GF_MODULE_BUNDLE_ENCRYPTED", f"Encrypted member is forbidden: {name}")
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise ModuleBundleError("GF_MODULE_BUNDLE_LINK", f"Links are forbidden in module bundles: {name}")
            _validate_source_name(name)
        required = {BUNDLE_DESCRIPTOR, MODULE_MANIFEST, "LICENSE"}
        missing = sorted(required.difference(names))
        if missing:
            raise ModuleBundleError(
                "GF_MODULE_BUNDLE_REQUIRED",
                "Module bundle is missing: " + ", ".join(missing),
            )
        exact_root_files = {BUNDLE_DESCRIPTOR, MODULE_MANIFEST, "LICENSE", "README.md"}
        extras = sorted(
            name for name in names
            if name not in exact_root_files and PurePosixPath(name).parts[0] != SOURCE_ROOT
        )
        if extras:
            raise ModuleBundleError(
                "GF_MODULE_BUNDLE_LAYOUT",
                "Unexpected bundle members: " + ", ".join(extras[:5]),
            )
        if not any(name.startswith(SOURCE_ROOT + "/") and name.endswith(".py") for name in names):
            raise ModuleBundleError("GF_MODULE_BUNDLE_SOURCE", "Bundle src/ contains no Python implementation")
        try:
            descriptor = json.loads(archive.read(BUNDLE_DESCRIPTOR).decode("utf-8"))
            manifest = json.loads(archive.read(MODULE_MANIFEST).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
            raise ModuleBundleError("GF_MODULE_BUNDLE_JSON", "Bundle descriptor or module manifest is invalid JSON") from exc
        if not isinstance(descriptor, dict) or descriptor.get("schema_version") != BUNDLE_SCHEMA:
            raise ModuleBundleError("GF_MODULE_BUNDLE_SCHEMA", f"Expected {BUNDLE_SCHEMA}")
        if descriptor.get("manifest") != MODULE_MANIFEST or descriptor.get("source_root") != SOURCE_ROOT:
            raise ModuleBundleError("GF_MODULE_BUNDLE_LAYOUT", "Bundle descriptor must use value-module.json and src/")
        inventory = descriptor.get("files")
        if not isinstance(inventory, list) or not all(isinstance(row, dict) for row in inventory):
            raise ModuleBundleError("GF_MODULE_BUNDLE_INVENTORY", "Bundle descriptor has no valid file inventory")
        declared = {str(row.get("path")): row for row in inventory}
        actual_names = set(names).difference({BUNDLE_DESCRIPTOR})
        if set(declared) != actual_names or len(declared) != len(inventory):
            raise ModuleBundleError("GF_MODULE_BUNDLE_INVENTORY", "Bundle inventory does not match its files")
        for name in sorted(actual_names):
            data = archive.read(name)
            row = declared[name]
            if row.get("bytes") != len(data) or row.get("sha256") != hashlib.sha256(data).hexdigest():
                raise ModuleBundleError("GF_MODULE_BUNDLE_HASH", f"Bundle inventory mismatch for {name}")
        if not isinstance(manifest, dict):
            raise ModuleBundleError("GF_MODULE_MANIFEST", "value-module.json must contain an object")
    return ValidatedModuleBundle(
        descriptor=descriptor,
        manifest=manifest,
        members=tuple(sorted(names)),
        bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        bundle_bytes=size,
        uncompressed_bytes=total,
    )


def extract_validated_bundle(bundle: Path, destination: Path, validated: ValidatedModuleBundle) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(bundle) as archive:
        for name in validated.members:
            target = destination.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))


def build_module_bundle(
    *,
    manifest_path: Path,
    source_root: Path,
    license_path: Path,
    destination: Path,
    readme_path: Path | None = None,
) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ModuleBundleError("GF_MODULE_MANIFEST", "Module manifest must be a JSON object")
    files: dict[str, bytes] = {
        MODULE_MANIFEST: _json_bytes(manifest),
        "LICENSE": license_path.read_bytes(),
    }
    if readme_path is not None:
        files["README.md"] = readme_path.read_bytes()
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        if "__pycache__" in source.parts or source.suffix.lower() in {".pyc", ".pyo"}:
            continue
        name = PurePosixPath(SOURCE_ROOT, source.relative_to(source_root).as_posix()).as_posix()
        _member_name(name)
        _validate_source_name(name)
        files[name] = source.read_bytes()
    if not any(name.endswith(".py") for name in files if name.startswith(SOURCE_ROOT + "/")):
        raise ModuleBundleError("GF_MODULE_BUNDLE_SOURCE", "Source root contains no Python files")
    descriptor: dict[str, object] = {
        "schema_version": BUNDLE_SCHEMA,
        "manifest": MODULE_MANIFEST,
        "source_root": SOURCE_ROOT,
        "files": [_inventory_row(name, files[name]) for name in sorted(files)],
    }
    members = {BUNDLE_DESCRIPTOR: _json_bytes(descriptor), **files}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, members[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temporary.replace(destination)
    validated = validate_module_bundle(destination)
    return {
        "schema_version": BUNDLE_SCHEMA,
        "archive": str(destination.resolve()),
        "module_id": manifest.get("id"),
        "module_version": manifest.get("version"),
        "member_count": len(validated.members),
        "bytes": validated.bundle_bytes,
        "sha256": validated.bundle_sha256,
    }
