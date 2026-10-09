"""Verification for the source-preserving Scheme C runtime copy.

RUNTIME_OVERLAY.json v2 registers every file of ``runtime_compat/`` with its
sha256 and a kind:

* ``source_identical``        byte copy of the retained ``compat/`` file;
* ``mechanical_substitution`` declared path/weather substitutions (see
  ``mechanical_substitutions``);
* ``value_instrumentation``   VALUE ledger/trace edits present before P0
  (the pre-P0 baseline of the kernel);
* ``declared_runtime_edit``   a later kernel edit; must name correction ids;
* ``value_added_module``      a new VALUE module inside the runtime package;
* ``data``                    packaged data such as ``scenarios_v2/*.csv``.

Rules: a registered file that is missing or changed is an error (data files
included); an unregistered ``.py`` or data file is an error; ``__pycache__``,
``*.pyc`` and files under ``excluded_generated_paths`` only warn.  The
retained ``compat/`` tree, when present, must match ``source_tree_sha256``.

Production runs call :func:`ensure_runtime_overlay_sealed` at entry; its
result is cached for the life of the process.  Kernel edits are registered
with ``scripts/seal_runtime_overlay.py --correction <id>``.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Mapping

from ...errors import CompatibilityError


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "RUNTIME_OVERLAY.json"
SCHEMA_V2 = "value.scheme-c-runtime-overlay/v2"
FILE_KINDS = (
    "source_identical",
    "mechanical_substitution",
    "value_instrumentation",
    "declared_runtime_edit",
    "value_added_module",
    "data",
)
_CACHE: dict[str, Any] = {}
_LOCK = threading.Lock()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generated(relative: str, excluded: tuple[str, ...]) -> bool:
    parts = relative.split("/")
    return (
        "__pycache__" in parts
        or relative.endswith((".pyc", ".pyo"))
        or any(relative.startswith(prefix) for prefix in excluded)
    )


def _tree_sha256(root: Path, excluded: tuple[str, ...] = ()) -> str:
    """Hash a tree, skipping bytecode and ``excluded`` path prefixes."""

    digest = hashlib.sha256()
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() not in {".pyc", ".pyo"}
    )
    for path in files:
        relative = path.relative_to(root).as_posix()
        if "__pycache__" in relative.split("/") or any(relative.startswith(prefix) for prefix in excluded):
            continue
        digest.update(f"{relative}\0{_file_sha256(path)}\n".encode("utf-8"))
    return digest.hexdigest()


def registered_tree_sha256(runtime_files: list[Mapping[str, Any]]) -> str:
    """Deterministic hash of the registered (path, sha256) set."""

    digest = hashlib.sha256()
    for row in sorted(runtime_files, key=lambda item: str(item["path"])):
        digest.update(f"{row['path']}\0{row['sha256']}\n".encode("utf-8"))
    return digest.hexdigest()


def inspect_runtime_overlay(root: Path = ROOT) -> dict[str, Any]:
    """Return ``{errors, warnings, ...}`` without raising."""

    manifest = json.loads((root / "RUNTIME_OVERLAY.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    if manifest.get("schema_version") != SCHEMA_V2:
        return {"manifest": manifest, "errors": [f"unsupported overlay schema {manifest.get('schema_version')!r}; reseal with scripts/seal_runtime_overlay.py"], "warnings": []}
    excluded = tuple(str(item) for item in manifest.get("excluded_generated_paths") or ())
    runtime_root = root / "runtime_compat"
    source_root = root / "compat"
    registered: dict[str, Mapping[str, Any]] = {}
    for row in manifest.get("runtime_files") or []:
        path = str(row["path"])
        if path in registered:
            errors.append(f"{path}: registered twice")
        registered[path] = row
        kind = row.get("kind")
        if kind not in FILE_KINDS:
            errors.append(f"{path}: unknown kind {kind!r}")
        if kind == "declared_runtime_edit" and not row.get("correction_ids"):
            errors.append(f"{path}: declared_runtime_edit without correction ids")
        target = runtime_root / path
        if not target.is_file():
            errors.append(f"{path}: registered runtime file is missing")
            continue
        actual = _file_sha256(target)
        if actual != row.get("sha256"):
            errors.append(f"{path}: registered runtime file changed ({kind}); reseal with --correction <id>")
        if kind == "source_identical" and source_root.is_dir():
            reference = source_root / path
            if not reference.is_file() or _file_sha256(reference) != actual:
                errors.append(f"{path}: declared source_identical but differs from compat/{path}")
    for path in sorted(runtime_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(runtime_root).as_posix()
        if relative in registered:
            continue
        if _generated(relative, excluded):
            warnings.append(f"{relative}: unregistered generated file ignored")
        else:
            errors.append(f"{relative}: unregistered runtime file")
    substitutions = manifest.get("mechanical_substitutions") or []
    for row in substitutions:
        registered_row = registered.get(str(row["path"]))
        if registered_row is None or registered_row.get("kind") != "mechanical_substitution":
            errors.append(f"{row['path']}: mechanical substitution is not registered as such")
        elif registered_row.get("sha256") != row.get("runtime_sha256"):
            errors.append(f"{row['path']}: mechanical substitution runtime hash disagrees with runtime_files")
        if source_root.is_dir():
            reference = source_root / str(row["path"])
            if not reference.is_file() or _file_sha256(reference) != row.get("source_sha256"):
                errors.append(f"{row['path']}: retained source differs from the substitution record")
    observed: dict[str, str] = {
        "runtime_tree_sha256": registered_tree_sha256([{"path": path, "sha256": _file_sha256(runtime_root / path)} for path in registered if (runtime_root / path).is_file()]),
    }
    if registered_tree_sha256(list(registered.values())) != manifest.get("runtime_tree_sha256"):
        errors.append("runtime_tree_sha256 does not match the registered file set")
    if source_root.is_dir():
        observed["source_tree_sha256"] = _tree_sha256(source_root)
        if observed["source_tree_sha256"] != manifest.get("source_tree_sha256"):
            errors.append("retained compat/ tree differs from source_tree_sha256 (it must stay byte-identical)")
    return {
        "manifest": manifest,
        "errors": errors,
        "warnings": warnings,
        "observed": observed,
        "source_reference_present": source_root.is_dir(),
    }


def verify_runtime_overlay(root: Path = ROOT) -> dict[str, object]:
    """Verify the overlay; raise CompatibilityError on any error."""

    report = inspect_runtime_overlay(root)
    if report["errors"]:
        raise CompatibilityError(
            "Scheme C runtime overlay verification failed: " + "; ".join(report["errors"][:10])
        )
    manifest = report["manifest"]
    return {
        **{key: value for key, value in manifest.items() if key != "runtime_files"},
        "runtime_file_count": len(manifest.get("runtime_files") or []),
        "verified": True,
        "warnings": report["warnings"],
        "source_reference_present": report["source_reference_present"],
        "observed": report["observed"],
    }


def ensure_runtime_overlay_sealed(root: Path = ROOT) -> dict[str, object]:
    """Process-cached verification used at every run entry.

    Returns a compact summary for provenance; raises CompatibilityError when
    the runtime kernel differs from its sealed manifest.
    """

    key = str(root)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            report = verify_runtime_overlay(root)
            cached = {
                "schema_version": report["schema_version"],
                "verified": True,
                "runtime_tree_sha256": report["runtime_tree_sha256"],
                "manifest_sha256": _file_sha256(root / "RUNTIME_OVERLAY.json"),
                "runtime_file_count": report["runtime_file_count"],
                "source_reference_present": report["source_reference_present"],
                "warnings": list(report["warnings"]),
            }
            _CACHE[key] = cached
        return dict(cached, warnings=list(cached["warnings"]))


def clear_runtime_overlay_cache() -> None:
    """Forget cached verification (tests and the seal script)."""

    with _LOCK:
        _CACHE.clear()
