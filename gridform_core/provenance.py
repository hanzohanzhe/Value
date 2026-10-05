"""Create a self-identifying, path-safe scientific run provenance record."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from backend.lifecycle.atomic_io import atomic_write_json

from .v2.contracts import ResolvedRun, YearResult, YearState
from .v2.module_manifest import ModuleRegistryV2, ResolvedModuleGraph
from .v2.orchestrator import contract_hash
from .runtime_capabilities import VALUE_NATIVE, capability_status


PROVENANCE_SCHEMA = "value.run-provenance/v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def snapshot_module_manifests(
    output_dir: Path,
    registry: ModuleRegistryV2,
    selected: Mapping[str, str],
    resolution_graph: ResolvedModuleGraph | None = None,
) -> dict[str, Path]:
    directory = output_dir / "module-manifests"
    directory.mkdir(parents=True, exist_ok=True)
    snapshots: dict[str, Path] = {}
    for slot, module_id in sorted(selected.items()):
        manifest = (
            resolution_graph.manifest(slot)
            if resolution_graph is not None
            else registry.manifest(module_id, expected_slot=slot)
        )
        if manifest.id != module_id:
            raise ValueError(f"Resolved module graph differs from selected {slot}: {module_id}")
        path = directory / f"{slot}--{module_id}.json"
        path.write_text(
            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        snapshots[slot] = path
    return snapshots


def _git_identity(project_root: Path) -> dict[str, object]:
    def command(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(project_root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )

    try:
        commit = command("rev-parse", "HEAD")
        if commit.returncode != 0:
            return {"available": False, "reason_code": "git_metadata_unavailable"}
        dirty = command("status", "--porcelain", "--untracked-files=normal")
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "reason_code": "git_command_unavailable"}
    return {
        "available": True,
        "commit": commit.stdout.strip(),
        "dirty": dirty.returncode != 0 or bool(dirty.stdout.strip()),
    }


def _dependencies(names: Sequence[str]) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for name in names:
        try:
            values[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            values[name] = None
    return values


def _module_source(module_entry_point: str) -> tuple[str, str | None]:
    module_name = module_entry_point.split(":", 1)[0]
    module = importlib.import_module(module_name)
    source = getattr(module, "__file__", None)
    if not source or not Path(source).is_file():
        return module_name, None
    return module_name, sha256_file(Path(source))


def _json_schema(path: Path) -> str | None:
    if path.suffix.lower() != ".json" or path.stat().st_size > 10_000_000:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return str(payload.get("schema_version")) if isinstance(payload, dict) and payload.get("schema_version") else None


def _is_external_launcher_log(path: Path) -> bool:
    """Return True for process-supervisor logs outside the scientific bundle."""

    name = path.name.lower()
    return path.suffix.lower() == ".log" and name.startswith(
        ("background-", "background_", "launcher-", "launcher_")
    )


def _artifact_index(bundle_root: Path, output_dir: Path) -> list[dict[str, object]]:
    sqlite_sidecars = [
        path
        for path in bundle_root.rglob("*")
        if path.is_file() and path.name.endswith(("-wal", "-shm"))
    ]
    if sqlite_sidecars:
        members = ", ".join(
            path.relative_to(bundle_root).as_posix()
            for path in sorted(sqlite_sidecars)
        )
        raise RuntimeError(
            "Scientific artifacts cannot be sealed with live SQLite sidecars: "
            + members
        )
    candidates = list(output_dir.rglob("*"))
    diagnostics = bundle_root / "diagnostics"
    if diagnostics.is_dir():
        candidates.extend(diagnostics.rglob("*"))
    for name in (
        "project-snapshot.json", "data-pack-snapshot.json", "preflight.json",
        "artifact-index.json",
    ):
        candidate = bundle_root / name
        if candidate.is_file():
            candidates.append(candidate)
    rows = []
    for path in sorted(set(candidates)):
        if (
            not path.is_file()
            or path.name in {"provenance.json", "status.json", "model.log"}
            or _is_external_launcher_log(path)
            or path.suffix in {".tmp", ".wal", ".shm"}
        ):
            continue
        rows.append({
            "artifact_id": path.relative_to(bundle_root).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "schema_version": _json_schema(path),
        })
    return rows


def _write_artifact_index(bundle_root: Path, output_dir: Path) -> Path:
    path = bundle_root / "artifact-index.json"
    payload = {
        "schema_version": "value.artifact-index/v1",
        "artifacts": _artifact_index(bundle_root, output_dir),
    }
    atomic_write_json(path, payload, indent=2, ensure_ascii=True)
    return path


def _failed_run_methodology(resolved_path: Path, project: Mapping[str, object]) -> object:
    """The methodology a failed run executed (or would have executed) under (X0 S9)."""

    try:
        resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
        recorded = dict(resolved.get("extensions") or {}).get("methodology")
        if isinstance(recorded, Mapping):
            return dict(recorded)
    except (OSError, ValueError, AttributeError):
        pass
    if not project:
        return None
    try:
        from .methodology import resolve_project_methodology

        return {**resolve_project_methodology(project).to_dict(), "source": "project_snapshot"}
    except ValueError as exc:
        return {"status": "unresolved", "error": str(exc)}


def write_failed_run_provenance(
    bundle_root: Path,
    *,
    run_id: str,
    project_id: str,
    error_code: str,
) -> Path:
    """Write an explicitly incomplete identity record for a newly failed run.

    The run directory must exist: a run moved to the trash is never recreated
    (``FileNotFoundError``).
    """

    bundle_root = bundle_root.resolve()
    if not bundle_root.is_dir():
        raise FileNotFoundError(f"Run directory does not exist: {bundle_root}")
    output_dir = bundle_root / "model-output"
    output_dir.mkdir(exist_ok=True)
    project = {}
    pack = {}
    for path, target in (
        (bundle_root / "project-snapshot.json", project),
        (bundle_root / "data-pack-snapshot.json", pack),
    ):
        try:
            target.update(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError:
            continue
    modules: dict[str, dict[str, object]] = {}
    selected = dict(project.get("modules") or {})
    selected.setdefault("transition", "value-annual-state-transition")
    for slot, module_id in sorted(selected.items()):
        snapshot = output_dir / "module-manifests" / f"{slot}--{module_id}.json"
        row: dict[str, object] = {"module_id": module_id}
        if snapshot.is_file():
            try:
                manifest = json.loads(snapshot.read_text(encoding="utf-8"))
                row.update({
                    "module_version": manifest.get("version"),
                    "scientific_version": manifest.get("scientific_version"),
                    "contract_version": manifest.get("contract_version"),
                    "entry_point": manifest.get("implementation"),
                    "execution_kind": manifest.get("execution_kind", "live_module"),
                    "manifest_artifact_id": snapshot.relative_to(bundle_root).as_posix(),
                    "manifest_sha256": sha256_file(snapshot),
                })
            except json.JSONDecodeError:
                row["manifest_warning_code"] = "GF_MANIFEST_SNAPSHOT_INVALID"
        modules[slot] = row
    bindings = {
        role: {
            "sha256": binding.get("sha256"),
            "bytes": binding.get("bytes"),
            "format": binding.get("format"),
        }
        for role, binding in sorted(dict(pack.get("bindings") or {}).items())
    }
    resolved_path = output_dir / "resolved-run.json"
    resolved_reference = None
    if resolved_path.is_file():
        resolved_reference = {
            "artifact_id": resolved_path.relative_to(bundle_root).as_posix(),
            "sha256": sha256_file(resolved_path),
        }
    record = {
        "schema_version": PROVENANCE_SCHEMA,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "completion": {
            "status": "failed",
            "error_code": error_code,
            "incomplete_fields": ["initial_state_sha256", "annual_state_chain"],
        },
        "identity": {
            "run_id": run_id,
            "project_id": project.get("id") or project_id,
            "data_pack_id": project.get("data_pack_id") or pack.get("id"),
            "project_schema": project.get("schema_version"),
            "data_pack_schema": pack.get("schema_version"),
            "execution_kind": "live_module",
            "runtime_capability": VALUE_NATIVE,
        },
        "modules": modules,
        "source_control": {"available": False, "reason_code": "run_failed_before_final_provenance"},
        "environment": {
            "python_executable": Path(sys.executable).name,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.system(),
            "dependencies": _dependencies(("numpy", "pandas", "xarray", "netCDF4")),
            "runtime_capability": capability_status(
                VALUE_NATIVE,
                selected_module_ids=selected.values(),
            ),
        },
        "data_bindings": bindings,
        "resolved_configuration": resolved_reference,
        "methodology": _failed_run_methodology(resolved_path, project),
        "randomness": {
            "planning_seed": (project.get("parameters") or {}).get("planning.random_seed", 0),
            "planning_draw_algorithm": "md5-prefix-mod-1000000/v1",
        },
        "initial_state_sha256": None,
        "annual_state_chain": [],
        "artifacts": _artifact_index(bundle_root, output_dir),
    }
    path = bundle_root / "provenance.json"
    atomic_write_json(path, record, indent=2, ensure_ascii=False)
    return path


def write_run_provenance(
    *,
    project_root: Path,
    pack_root: Path,
    output_dir: Path,
    resolved_run: ResolvedRun,
    registry: ModuleRegistryV2,
    selected: Mapping[str, str],
    project_schema: str | None,
    manifest_snapshots: Mapping[str, Path],
    initial_state: YearState,
    year_results: Sequence[YearResult],
    runtime_overlay: Mapping[str, object] | None = None,
) -> Path:
    """Write provenance only after immutable model artifacts have closed."""

    bundle_root = (
        output_dir.parent
        if (output_dir.parent / "project-snapshot.json").is_file()
        else output_dir
    )
    pack_manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    modules: dict[str, dict[str, object]] = {}
    for slot, module_id in sorted(selected.items()):
        manifest = registry.manifest(module_id, expected_slot=slot)
        module_name, source_hash = _module_source(manifest.implementation)
        snapshot = manifest_snapshots[slot]
        modules[slot] = {
            "module_id": manifest.id,
            "module_version": manifest.version,
            "scientific_version": manifest.scientific_version,
            "contract_version": manifest.contract_version,
            "entry_point": manifest.implementation,
            "source_module": module_name,
            "source_sha256": source_hash,
            "execution_kind": manifest.execution_kind,
            "manifest_artifact_id": snapshot.relative_to(bundle_root).as_posix(),
            "manifest_sha256": sha256_file(snapshot),
        }
    binding_hashes = {
        role: {
            "sha256": binding.get("sha256"),
            "bytes": binding.get("bytes"),
            "format": binding.get("format"),
        }
        for role, binding in sorted(dict(pack_manifest.get("bindings") or {}).items())
    }
    resolved_path = output_dir / "resolved-run.json"
    state_chain = []
    current = initial_state
    for result in year_results:
        declared_input_hash = result.extensions.get("annual_input_state_sha256")
        input_state_sha256 = (
            str(declared_input_hash)
            if declared_input_hash
            else contract_hash(current)
        )
        state_chain.append({
            "year": result.year,
            "input_year": current.year,
            "input_state_sha256": input_state_sha256,
            "output_year": result.next_state.year,
            "output_state_sha256": contract_hash(result.next_state),
        })
        current = result.next_state
    source_initial_state_sha256 = contract_hash(initial_state)
    effective_initial_state_sha256 = (
        str(state_chain[0]["input_state_sha256"])
        if state_chain else source_initial_state_sha256
    )
    artifact_index_path = _write_artifact_index(bundle_root, output_dir)
    execution_identity_path = output_dir / "execution-identity.json"
    execution_identity = (
        json.loads(execution_identity_path.read_text(encoding="utf-8"))
        if execution_identity_path.is_file()
        else None
    )
    record = {
        "schema_version": PROVENANCE_SCHEMA,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "completion": {"status": "completed"},
        "identity": {
            "run_id": resolved_run.run_id,
            "project_id": resolved_run.project_id,
            "data_pack_id": resolved_run.data_pack_id,
            "resolved_run_schema": resolved_run.schema_version,
            "project_schema": project_schema,
            "data_pack_schema": pack_manifest.get("schema_version"),
            "execution_kind": "live_module",
            "runtime_capability": resolved_run.extensions.get(
                "runtime_capability", "value-native"
            ),
        },
        "modules": modules,
        "source_control": _git_identity(project_root),
        "environment": {
            "python_executable": Path(sys.executable).name,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.system(),
            "dependencies": _dependencies(("numpy", "pandas", "xarray", "netCDF4")),
            "runtime_capability": resolved_run.extensions.get(
                "runtime_capability_status"
            ),
        },
        "data_bindings": binding_hashes,
        "resolved_configuration": {
            "artifact_id": resolved_path.relative_to(bundle_root).as_posix(),
            "sha256": sha256_file(resolved_path),
            "scientific_parameters_sha256": sha256_json(resolved_run.scientific_parameters),
            "runtime_options_sha256": sha256_json(resolved_run.runtime_controls),
            "scientific_parameters": dict(resolved_run.scientific_parameters),
            "runtime_options": dict(resolved_run.runtime_controls),
        },
        "execution_source_identity": (
            {
                "artifact_id": execution_identity_path.relative_to(bundle_root).as_posix(),
                "sha256": execution_identity.get("sha256"),
                "resume_identity_sha256": execution_identity.get("resume_identity_sha256"),
                "files": len(execution_identity.get("files") or []),
            }
            if execution_identity is not None
            else None
        ),
        "randomness": {
            "planning_success_mode": resolved_run.scientific_parameters.get("planning.success_mode"),
            "planning_seed": resolved_run.scientific_parameters.get("planning.random_seed"),
            "planning_draw_algorithm": "md5-prefix-mod-1000000/v1",
            "python_hash_seed": 0,
        },
        "source_initial_state_sha256": source_initial_state_sha256,
        "initial_state_sha256": effective_initial_state_sha256,
        "initialization": {
            "source_initial_state_sha256": source_initial_state_sha256,
            "effective_initial_state_sha256": effective_initial_state_sha256,
            "extension_initialization_applied": (
                source_initial_state_sha256 != effective_initial_state_sha256
            ),
        },
        "annual_state_chain": state_chain,
        "stage_events_artifact_id": (output_dir / "orchestrator-events.jsonl").relative_to(bundle_root).as_posix(),
        "artifact_index_artifact_id": artifact_index_path.relative_to(bundle_root).as_posix(),
        "artifacts": _artifact_index(bundle_root, output_dir),
    }
    if runtime_overlay is not None:
        record["runtime_overlay"] = dict(runtime_overlay)
    record["methodology"] = resolved_run.extensions.get("methodology")
    path = bundle_root / "provenance.json"
    atomic_write_json(path, record, indent=2, ensure_ascii=False)
    return path
