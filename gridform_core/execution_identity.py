"""Deterministic source identity for resumable VALUE executions.

Checkpoint identity must include the code that creates and mutates the stored
scientific state.  Module IDs and versions alone are insufficient during local
development because a source edit can occur without a version bump.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


EXECUTION_IDENTITY_SCHEMA = "value.execution-source-identity/v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_identity(
    paths: Iterable[Path],
    *,
    root: Path,
    suffixes: frozenset[str] = frozenset({".py", ".json"}),
) -> dict[str, object]:
    """Hash a named source set without exposing host-specific absolute paths."""

    root = root.resolve()
    files: set[Path] = set()
    for raw in paths:
        path = raw.resolve()
        if path.is_dir():
            files.update(
                candidate.resolve()
                for candidate in path.rglob("*")
                if candidate.is_file()
                and candidate.suffix.lower() in suffixes
                and "__pycache__" not in candidate.parts
            )
        elif path.is_file() and path.suffix.lower() in suffixes:
            files.add(path)

    records: list[dict[str, object]] = []
    for path in sorted(files, key=lambda item: item.as_posix().casefold()):
        try:
            label = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"Execution source is outside the declared root: {path}") from exc
        records.append(
            {
                "path": label,
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    if not records:
        raise ValueError("Execution source identity cannot be empty")

    canonical = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "schema_version": EXECUTION_IDENTITY_SCHEMA,
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "files": records,
    }


def scheme_c_execution_identity() -> dict[str, object]:
    """Identity of the copied model path and its state-affecting core services."""

    core_root = Path(__file__).resolve().parent
    scheme_root = core_root / "builtin" / "scheme_c_1000twh"
    dependencies = (
        core_root / "data.py",
        core_root / "energy_balance_contract.py",
        core_root / "errors.py",
        core_root / "market_ledger.py",
        core_root / "module_registry.py",
        core_root / "parameters.py",
        core_root / "planning_ledger.py",
        core_root / "storage_audit.py",
        core_root / "v2" / "contracts.py",
    )
    return source_tree_identity((scheme_root, *dependencies), root=core_root.parent)
