"""Verification for the source-preserving Scheme C runtime copy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ...errors import CompatibilityError


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "RUNTIME_OVERLAY.json"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() not in {".pyc", ".pyo"}
    )
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(f"{relative}\0{_file_sha256(path)}\n".encode("utf-8"))
    return digest.hexdigest()


def verify_runtime_overlay() -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source_root = ROOT / "compat"
    runtime_root = ROOT / "runtime_compat"
    observed = {"runtime_tree_sha256": _tree_sha256(runtime_root)}
    if source_root.is_dir():
        observed["source_tree_sha256"] = _tree_sha256(source_root)
    for field, value in observed.items():
        if value != manifest[field]:
            raise CompatibilityError(
                f"Scheme C runtime overlay {field} differs from its manifest: "
                f"expected {manifest[field]}, observed {value}"
            )
    return {
        **manifest,
        "verified": True,
        "source_reference_present": source_root.is_dir(),
        "observed": observed,
    }
