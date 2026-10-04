"""Seal or verify the Scheme C runtime overlay (RUNTIME_OVERLAY.json v2).

Usage::

    seal_runtime_overlay.py --verify
    seal_runtime_overlay.py --correction <id> [--note TEXT]   # register kernel edits
    seal_runtime_overlay.py --migrate-v1                      # one-off v1 -> v2

``--correction`` re-registers every changed registered file as
``declared_runtime_edit`` carrying the correction id (appended to its list),
registers new ``.py`` files as ``value_added_module`` and new data files as
``data``, and refuses removals unless ``--allow-remove`` is given.  It never
touches the retained ``compat/`` tree.
"""

from __future__ import annotations

# P0 rule (P0_CONVENTIONS section 2): never write bytecode, even when started
# without -B; the managed install's runtime is read-only and must stay
# byte-identical.  Inherited by every subprocess through the environment.
import os as _os
import sys as _sys

_sys.dont_write_bytecode = True
_os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.builtin.scheme_c_1000twh import runtime_overlay as overlay  # noqa: E402

CORRECTION_ID = re.compile(r"^[a-z0-9]+(\.[a-z0-9-]+)+$")
# VALUE edits present in runtime_compat before P0 (the pre-P0 kernel baseline).
VALUE_INSTRUMENTATION = {
    "modular_simulation_model.py": "VALUE market-ledger, trace and storage-cost instrumentation present at 35aadb3",
    "storage_cost.py": "VALUE storage-cost function boundary present at 35aadb3",
}


def _write(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def migrate_v1(root: Path) -> dict[str, Any]:
    manifest_path = root / "RUNTIME_OVERLAY.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") == overlay.SCHEMA_V2:
        raise SystemExit("RUNTIME_OVERLAY.json is already v2")
    runtime_root = root / "runtime_compat"
    source_root = root / "compat"
    excluded = tuple(manifest.get("excluded_generated_paths") or ())
    substitutions = {str(row["path"]) for row in manifest.get("mechanical_substitutions") or []}
    support = {str(path).removeprefix("runtime_compat/") for path in manifest.get("packaged_support_files") or []}
    rows = []
    for path in sorted(runtime_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(runtime_root).as_posix()
        if overlay._generated(relative, excluded):
            continue
        sha = overlay._file_sha256(path)
        reference = source_root / relative
        if relative in substitutions:
            kind, note = "mechanical_substitution", "declared mechanical substitution"
        elif relative in VALUE_INSTRUMENTATION:
            kind, note = "value_instrumentation", VALUE_INSTRUMENTATION[relative]
        elif relative in support or not relative.endswith(".py"):
            kind, note = "data", "packaged runtime data"
        elif reference.is_file() and overlay._file_sha256(reference) == sha:
            kind, note = "source_identical", None
        elif reference.is_file():
            raise SystemExit(f"{relative}: differs from compat/ but is not a declared substitution or instrumentation")
        else:
            kind, note = "value_added_module", "VALUE module inside the runtime package"
        row: dict[str, Any] = {"path": relative, "sha256": sha, "kind": kind, "correction_ids": []}
        if note:
            row["note"] = note
        rows.append(row)
    v2 = {
        "schema_version": overlay.SCHEMA_V2,
        "previous_schema_version": manifest.get("schema_version"),
        "generator_version": "x0-s5-runtime-overlay-v2",
        "source_package": manifest["source_package"],
        "runtime_package": manifest["runtime_package"],
        "source_tree_sha256": manifest["source_tree_sha256"],
        "runtime_tree_sha256": overlay.registered_tree_sha256(rows),
        "v1_runtime_tree_sha256": manifest.get("runtime_tree_sha256"),
        "v1_note": (
            "The v1 runtime_tree_sha256 predates VALUE instrumentation edits to "
            "modular_simulation_model.py and storage_cost.py and was never checked "
            "on the production path; v2 registers every runtime file instead."
        ),
        "excluded_generated_paths": list(excluded),
        "mechanical_substitutions": manifest.get("mechanical_substitutions") or [],
        "required_bindings": manifest.get("required_bindings") or [],
        "packaged_support_files": manifest.get("packaged_support_files") or [],
        "preservation_rule": manifest.get("preservation_rule"),
        "runtime_files": rows,
    }
    _write(manifest_path, v2)
    return {"migrated": True, "files": len(rows), "kinds": sorted({row["kind"] for row in rows})}


def seal(root: Path, correction_id: str, note: str | None, allow_remove: bool) -> dict[str, Any]:
    if not CORRECTION_ID.match(correction_id):
        raise SystemExit(f"correction id {correction_id!r} does not match {CORRECTION_ID.pattern}")
    manifest_path = root / "RUNTIME_OVERLAY.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != overlay.SCHEMA_V2:
        raise SystemExit("migrate to v2 first (--migrate-v1)")
    runtime_root = root / "runtime_compat"
    excluded = tuple(manifest.get("excluded_generated_paths") or ())
    rows = {str(row["path"]): dict(row) for row in manifest["runtime_files"]}
    changed, added, removed = [], [], []
    for relative, row in list(rows.items()):
        target = runtime_root / relative
        if not target.is_file():
            if not allow_remove:
                raise SystemExit(f"{relative}: registered file is missing (use --allow-remove)")
            removed.append(relative)
            del rows[relative]
            continue
        sha = overlay._file_sha256(target)
        if sha != row["sha256"]:
            row["sha256"] = sha
            if row["kind"] in {"source_identical", "mechanical_substitution", "value_instrumentation"}:
                row["previous_kind"] = row["kind"]
                row["kind"] = "declared_runtime_edit"
            row["correction_ids"] = sorted(set(row.get("correction_ids") or []) | {correction_id})
            if note:
                row["note"] = note
            changed.append(relative)
    for path in sorted(runtime_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(runtime_root).as_posix()
        if relative in rows or overlay._generated(relative, excluded):
            continue
        rows[relative] = {
            "path": relative,
            "sha256": overlay._file_sha256(path),
            "kind": "value_added_module" if relative.endswith(".py") else "data",
            "correction_ids": [correction_id],
            **({"note": note} if note else {}),
        }
        added.append(relative)
    manifest["runtime_files"] = [rows[key] for key in sorted(rows)]
    manifest["runtime_tree_sha256"] = overlay.registered_tree_sha256(manifest["runtime_files"])
    _write(manifest_path, manifest)
    overlay.clear_runtime_overlay_cache()
    return {"correction_id": correction_id, "changed": changed, "added": added, "removed": removed}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=overlay.ROOT, help=argparse.SUPPRESS)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify", action="store_true")
    group.add_argument("--correction")
    group.add_argument("--migrate-v1", action="store_true")
    parser.add_argument("--note")
    parser.add_argument("--allow-remove", action="store_true")
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    if arguments.verify:
        report = overlay.inspect_runtime_overlay(root)
        summary = {
            "verified": not report["errors"],
            "errors": report["errors"],
            "warnings": report["warnings"],
            "source_reference_present": report.get("source_reference_present"),
        }
        print(json.dumps(summary, indent=2))
        return 0 if not report["errors"] else 1
    if arguments.migrate_v1:
        print(json.dumps(migrate_v1(root), indent=2))
        return 0
    print(json.dumps(seal(root, arguments.correction, arguments.note, arguments.allow_remove), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
