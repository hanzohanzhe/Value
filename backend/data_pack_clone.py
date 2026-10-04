"""Independent, identity-verified copies of local BASE data packs."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Mapping

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MIN_FREE_SPACE_BYTES = 64 * 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{64}$")


class DataPackCloneError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(message)


def manifest_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _regular(path: Path, root: Path) -> None:
    path.relative_to(root)
    current = path
    while current != root.parent:
        if current.is_symlink():
            raise ValueError("Source pack contains a symbolic link")
        current = current.parent
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Source pack files must be independent regular files")


def guard_clone_upload(manifest: Mapping[str, object], manifest_path: Path,
                       expected: str | None, projects_root: Path, trash_root: Path) -> None:
    """Caller holds the shared Study lifecycle lock."""
    if not isinstance(manifest, Mapping):
        raise DataPackCloneError("GF_DATA_PACK_UNKNOWN", "The target data pack is missing or invalid.", 404)
    if not manifest.get("copy_origin"):
        return
    if expected != manifest_sha256(manifest_path):
        raise DataPackCloneError("GF_DATA_PACK_STALE_REVISION", "The data pack changed; reload it before replacing a role.")
    for path in (list(projects_root.glob("*/project.json"))
                 + list(projects_root.glob("*/revisions/*.json"))
                 + list(trash_root.rglob("project.json"))
                 + list(trash_root.glob("**/revisions/*.json"))):
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(project, dict):
                raise ValueError("Study record must be an object")
        except (OSError, ValueError) as exc:
            raise DataPackCloneError("GF_DATA_PACK_REFERENCE_UNVERIFIABLE", "Cannot verify Study references; review the local Study records first.") from exc
        if project.get("data_pack_id") == manifest.get("id"):
            raise DataPackCloneError("GF_DATA_PACK_REFERENCED", "A saved or trashed Study uses this data pack. Copy it again before replacing a role.")


def clone_data_pack(source_id: str, request: Mapping[str, object], *, packs_root: Path,
                    minimum_free_space_bytes: int = MIN_FREE_SPACE_BYTES) -> dict[str, object]:
    """Caller holds the shared lifecycle lock through verification/publication."""
    name, expected = request.get("name"), request.get("source_manifest_sha256")
    if (set(request) != {"schema_version", "name", "source_manifest_sha256"}
            or request.get("schema_version") != "value.data-pack-clone-request/v1"
            or not SAFE_ID.fullmatch(source_id) or not isinstance(name, str) or not name.strip()
            or not isinstance(expected, str) or not SHA.fullmatch(expected)):
        raise DataPackCloneError("GF_DATA_PACK_CLONE_REQUEST_INVALID", "Provide a name and exact source manifest checksum.", 400)
    root = packs_root.absolute()
    source = root / source_id
    manifest_path = source / "manifest.json"
    if not manifest_path.exists():
        raise DataPackCloneError("GF_DATA_PACK_UNKNOWN", "The source BASE data pack is not installed.", 404)
    stage = None
    destination = None
    reserved = False
    try:
        _regular(manifest_path, source)
        raw = manifest_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise DataPackCloneError("GF_DATA_PACK_STALE_REVISION", "The source data pack changed; reload it before copying.")
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise ValueError("Source manifest must be an object")
        if manifest.get("id") != source_id or manifest.get("schema_version") != "value.data-pack/v1":
            raise ValueError("Source manifest identity is inconsistent")
        if manifest.get("data_pack_type") == "network_overlay" or manifest.get("network_overlay"):
            raise DataPackCloneError("GF_DATA_PACK_CLONE_BASE_ONLY", "Only local BASE data packs can be copied.", 400)
        files = {}
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ValueError("Source pack contains a symbolic link")
            if path.is_dir():
                continue
            _regular(path, source)
            files[path.relative_to(source).as_posix()] = manifest_sha256(path)
        for role, binding in manifest.get("bindings", {}).items():
            uri = binding.get("uri")
            if not isinstance(uri, str) or "\\" in uri:
                raise ValueError(f"Unsafe URI for {role}")
            if uri in {"manifest.json", "installation.json", "value-data-bundle.json"}:
                raise ValueError(f"Source role {role} points to reserved pack metadata")
            parts = PurePosixPath(uri)
            if parts.is_absolute() or any(part in {"..", "."} for part in parts.parts) or uri not in files:
                raise ValueError(f"Unsafe or missing file for {role}")
            if files[uri] != binding.get("sha256") or (source / uri).stat().st_size != binding.get("bytes"):
                raise ValueError(f"Source checksum or byte count mismatch for {role}")
        stem = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:100] or "data-pack"
        new_id = f"{stem}-{uuid.uuid4().hex[:12]}"
        destination = root / new_id
        required = sum((source / uri).stat().st_size for uri in files) + max(0, minimum_free_space_bytes)
        if shutil.disk_usage(root).free < required:
            raise DataPackCloneError("GF_DATA_PACK_DISK_HEADROOM", "Not enough disk headroom to copy the data pack.", 507)
        stage = Path(tempfile.mkdtemp(prefix=".data-pack-copy-", dir=root.parent))
        for uri in files:
            if uri in {"manifest.json", "installation.json", "value-data-bundle.json"}:
                continue
            target = stage / uri
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / uri, target)
            if manifest_sha256(target) != files[uri]:
                raise ValueError("Source files changed while copying")
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        clone = copy.deepcopy(manifest)
        for field in ("installation", "manifest_sha256", "pack_revision_sha256"):
            clone.pop(field, None)
        clone.update(id=new_id, name=name.strip(), created_at=timestamp, updated_at=timestamp,
                     copy_origin={"schema_version": "value.data-pack-copy/v1", "source_data_pack_id": source_id,
                                  "source_manifest_sha256": expected, "created_at": timestamp})
        (stage / "manifest.json").write_text(json.dumps(clone, indent=2, ensure_ascii=False), encoding="utf-8")
        if manifest_sha256(manifest_path) != expected or any(manifest_sha256(source / uri) != digest for uri, digest in files.items()):
            raise DataPackCloneError("GF_DATA_PACK_SOURCE_DRIFT", "Source files changed while copying; reload and retry.")
        destination.mkdir()
        reserved = True
        os.replace(stage, destination)
        stage = None
        clone["manifest_sha256"] = manifest_sha256(destination / "manifest.json")
        return {"ok": True, "data_pack": clone, "run_started": False}
    except DataPackCloneError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise DataPackCloneError("GF_DATA_PACK_CLONE_FAILED", f"The independent copy was not saved: {exc}") from exc
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
            if reserved and destination is not None:
                destination.rmdir()
