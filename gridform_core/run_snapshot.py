"""Atomic, content-addressed input snapshots for queued model runs."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .v2.module_manifest import ModuleRegistryV2
from .frontend_contract import (
    ProjectSolverContractError,
    validate_maturity_acknowledgements,
    validate_project_solver_contract,
)
from .data_adapters import AdapterSpec, execute_adapter


SCHEMA_VERSION = "value.run-input-snapshot/v1"


class SnapshotError(RuntimeError):
    """Frozen-input verification failure; ``code`` is set when it is stable."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


METHOD_SUPERSEDED = "GF_RUN_METHOD_SUPERSEDED"
_SUPERSEDED_ACTION = (
    "The Run's results stay readable; to compute it again with the current "
    "method use frozen-run recovery in migration mode, which shows every "
    "changed setting before a new Study revision is saved."
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _safe_filename(value: str, fallback: str) -> str:
    name = Path(value).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name or fallback


def _readonly(path: Path) -> None:
    try:
        path.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        # Hash verification remains authoritative on filesystems without a
        # portable read-only bit.
        pass


def _source_path(entry_point: str) -> Path:
    module_name = entry_point.split(":", 1)[0]
    module = importlib.import_module(module_name)
    raw = getattr(module, "__file__", None)
    if not raw or not Path(raw).is_file():
        raise SnapshotError(f"Module source is not a hashable local file: {entry_point}")
    return Path(raw).resolve()


def _put_object(source: Path, expected_sha256: str, object_root: Path) -> Path:
    expected = expected_sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SnapshotError(f"Source has no valid SHA-256: {source.name}")
    if sha256_file(source) != expected:
        raise SnapshotError(f"Source changed before snapshot: {source.name}")
    destination = object_root / expected[:2] / expected
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        if sha256_file(destination) != expected:
            raise SnapshotError(f"Content-addressed object is corrupt: {expected}")
        return destination
    temporary = destination.with_name(f"{destination.name}.tmp-{uuid.uuid4().hex}")
    shutil.copyfile(source, temporary)
    if sha256_file(temporary) != expected:
        temporary.unlink(missing_ok=True)
        raise SnapshotError(f"Copied object failed SHA-256 verification: {source.name}")
    os.replace(temporary, destination)
    _readonly(destination)
    return destination


def _freeze_pack(
    *,
    pack_root: Path,
    pack_manifest: Mapping[str, object],
    staging: Path,
    destination_name: str,
    pack_kind: str,
    object_root: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Freeze one data product without merging its namespace or provenance."""

    frozen_manifest = dict(pack_manifest)
    frozen_bindings: dict[str, dict[str, object]] = {}
    objects: list[dict[str, object]] = []
    resolved_root = pack_root.resolve()
    destination_root = staging / destination_name
    for role, raw_binding in sorted(dict(pack_manifest.get("bindings") or {}).items()):
        binding = dict(raw_binding)
        source = (resolved_root / str(binding.get("uri") or "")).resolve()
        try:
            source.relative_to(resolved_root)
        except ValueError as exc:
            raise SnapshotError(f"Binding escapes the {pack_kind} data pack: {role}") from exc
        if not source.is_file():
            raise SnapshotError(f"Binding is missing: {role}")
        source_sha256 = str(binding.get("sha256") or "").lower()
        if sha256_file(source) != source_sha256:
            raise SnapshotError(f"Source changed before snapshot: {source.name}")
        expected = source_sha256
        normalized_source = source
        adapter_payload = binding.get("adapter")
        transformation_id = "identity/v1"
        if isinstance(adapter_payload, Mapping):
            specification = AdapterSpec.from_dict(adapter_payload)
            if specification.canonical_role != role:
                raise SnapshotError(
                    f"Adapter {specification.adapter_id} emits {specification.canonical_role}; expected {role}"
                )
            normalized_source = (
                staging / "normalized" / destination_name /
                str(role).replace(".", "__") / "data.csv"
            )
            result = execute_adapter(source, specification, normalized_source)
            expected = result.normalized_sha256
            transformation_id = result.transformation_id
            binding["format"] = specification.canonical_format
        object_path = _put_object(normalized_source, expected, object_root)
        filename = _safe_filename(str(binding.get("filename") or source.name), "data.bin")
        frozen_file = (
            destination_root / "files" / str(role).replace(".", "__") / filename
        )
        frozen_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(object_path, frozen_file)
            storage = "content_addressed_hardlink"
        except OSError:
            shutil.copyfile(object_path, frozen_file)
            storage = "verified_copy"
        _readonly(frozen_file)
        binding.update({
            "uri": frozen_file.relative_to(destination_root).as_posix(),
            "sha256": expected,
            "bytes": frozen_file.stat().st_size,
            "source_sha256": source_sha256,
            "normalized_sha256": expected,
            "snapshot_storage": storage,
            "transformation_id": transformation_id,
        })
        frozen_bindings[str(role)] = binding
        objects.append({
            "role": role,
            "pack_kind": pack_kind,
            "pack_directory": destination_name,
            "sha256": expected,
            "source_sha256": source_sha256,
            "bytes": frozen_file.stat().st_size,
            "snapshot_uri": binding["uri"],
        })
    frozen_manifest["bindings"] = frozen_bindings
    frozen_manifest["snapshot_frozen"] = True
    return frozen_manifest, objects


def create_run_input_snapshot(
    *,
    run_dir: Path,
    project: Mapping[str, object],
    pack_root: Path,
    registry: ModuleRegistryV2,
    selected: Mapping[str, str],
    object_root: Path,
    network_pack_root: Path | None = None,
) -> dict[str, object]:
    """Freeze project, data bytes and module identities before queue acceptance."""

    run_dir = run_dir.resolve()
    final = run_dir / "input-snapshot"
    if final.exists():
        raise SnapshotError("This run already has an input snapshot.")
    # Keep the staging component short: on Windows it sits below the run ID,
    # role directory and source filename, so a verbose marker can exhaust the
    # legacy 260-character path budget before an atomic snapshot is promoted.
    staging = run_dir / f".snapshot-{uuid.uuid4().hex[:12]}.tmp"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        pack_manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
        network_pack_manifest = None
        if network_pack_root is not None:
            network_pack_manifest = json.loads(
                (network_pack_root / "manifest.json").read_text(encoding="utf-8")
            )
            declared_network_id = str(
                dict(project.get("market_configuration") or {}).get("network_pack_id") or ""
            )
            actual_network_id = str(network_pack_manifest.get("id") or "")
            if declared_network_id != actual_network_id:
                raise SnapshotError(
                    "Project network_pack_id does not match the network overlay being frozen"
                )
            if network_pack_manifest.get("data_pack_type") != "network_overlay":
                raise SnapshotError("The separate network data product is not a network_overlay")
        selected_extensions = tuple(
            str(item) for item in project.get("selected_extensions", ())
        )
        validate_maturity_acknowledgements(
            registry,
            selected,
            selected_extensions,
            dict(project.get("maturity_acknowledgements") or {}),
        )
        try:
            canonical_solver_contract = validate_project_solver_contract(
                project,
                registry,
                modules=selected,
                require_acknowledgement=True,
            )
        except ProjectSolverContractError as exc:
            raise SnapshotError(f"{exc.code}: {exc}", exc.code) from exc
        if canonical_solver_contract is not None and canonical_solver_contract != project.get(
            "solver_contract"
        ):
            raise SnapshotError("Project solver contract is not canonical")
        available_data_roles = set(dict(pack_manifest.get("bindings") or {}))
        if network_pack_manifest is not None:
            available_data_roles.update(dict(network_pack_manifest.get("bindings") or {}))
        resolution_graph = registry.resolve_selection(
            selected,
            selected_extensions=selected_extensions,
            extension_parameters=dict(project.get("extension_parameters") or {}),
            available_data_roles=tuple(sorted(available_data_roles)),
        )
        frozen_manifest, objects = _freeze_pack(
            pack_root=pack_root,
            pack_manifest=pack_manifest,
            staging=staging,
            destination_name="pack",
            pack_kind="base",
            object_root=object_root,
        )
        frozen_network_manifest = None
        if network_pack_manifest is not None and network_pack_root is not None:
            frozen_network_manifest, network_objects = _freeze_pack(
                pack_root=network_pack_root,
                pack_manifest=network_pack_manifest,
                staging=staging,
                destination_name="network-pack",
                pack_kind="network_overlay",
                object_root=object_root,
            )
            objects.extend(network_objects)
        project_payload = dict(project)
        (staging / "project.json").write_text(
            json.dumps(project_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (staging / "pack" / "manifest.json").write_text(
            json.dumps(frozen_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if frozen_network_manifest is not None:
            (staging / "network-pack" / "manifest.json").write_text(
                json.dumps(frozen_network_manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        modules = []
        for slot, module_id in sorted(selected.items()):
            manifest = registry.manifest(module_id, expected_slot=slot)
            source = _source_path(manifest.implementation)
            modules.append({
                "slot": slot,
                "module_id": manifest.id,
                "module_version": manifest.version,
                "contract_version": manifest.contract_version,
                "entry_point": manifest.implementation,
                "source_sha256": sha256_file(source),
                "source_filename": source.name,
            })
        identity = {
            "project_sha256": _json_hash(project_payload),
            "pack_manifest_sha256": _json_hash(frozen_manifest),
            "objects": objects,
            "modules": modules,
        }
        if frozen_network_manifest is not None:
            identity.update({
                "network_pack_id": frozen_network_manifest.get("id"),
                "network_pack_manifest_sha256": _json_hash(frozen_network_manifest),
            })
        if resolution_graph.extension_graph is not None:
            identity["extension_graph"] = resolution_graph.extension_graph.to_dict()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": _json_hash(identity),
            "state": "ready",
            "input_tree_sha256": _json_hash(identity),
            **identity,
            "module_resolution_graph": resolution_graph.to_dict(),
        }
        (staging / "snapshot.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(staging, final)
        return manifest
    except Exception:
        # An incomplete directory is deliberately not promoted and is never a
        # runnable snapshot. It can be collected by an explicit retention job.
        raise


def verify_run_input_snapshot(
    snapshot_root: Path,
    registry: ModuleRegistryV2,
) -> dict[str, object]:
    manifest_path = snapshot_root / "snapshot.json"
    if not manifest_path.is_file():
        raise SnapshotError("Run input snapshot is incomplete.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("state") != "ready":
        raise SnapshotError("Run input snapshot is not runnable.")
    from .frozen_input_integrity import verify_frozen_input_integrity
    verify_frozen_input_integrity(snapshot_root)
    project = json.loads((snapshot_root / "project.json").read_text(encoding="utf-8"))
    pack = json.loads((snapshot_root / "pack" / "manifest.json").read_text(encoding="utf-8"))
    network_pack = None
    if _json_hash(project) != manifest.get("project_sha256"):
        raise SnapshotError("Frozen project bytes do not match the snapshot identity.")
    if _json_hash(pack) != manifest.get("pack_manifest_sha256"):
        raise SnapshotError("Frozen pack manifest does not match the snapshot identity.")
    if manifest.get("network_pack_manifest_sha256") is not None:
        network_manifest_path = snapshot_root / "network-pack" / "manifest.json"
        if not network_manifest_path.is_file():
            raise SnapshotError("Frozen network overlay is missing from the run snapshot.")
        network_pack = json.loads(network_manifest_path.read_text(encoding="utf-8"))
        if _json_hash(network_pack) != manifest.get("network_pack_manifest_sha256"):
            raise SnapshotError("Frozen network manifest does not match the snapshot identity.")
        if str(network_pack.get("id") or "") != str(manifest.get("network_pack_id") or ""):
            raise SnapshotError("Frozen network overlay identity changed after enqueue.")
    for row in manifest.get("objects", []):
        pack_directory = str(row.get("pack_directory") or "pack")
        frozen_root = (snapshot_root / pack_directory).resolve()
        path = (frozen_root / str(row["snapshot_uri"])).resolve()
        try:
            path.relative_to(frozen_root)
        except ValueError as exc:
            raise SnapshotError("Snapshot object path escapes its frozen data product.") from exc
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            raise SnapshotError(f"Frozen data object is missing or changed: {row['role']}")
    for row in manifest.get("modules", []):
        current = registry.manifest(str(row["module_id"]), expected_slot=str(row["slot"]))
        if current.version != row["module_version"] or current.contract_version != row["contract_version"]:
            raise SnapshotError(
                f"{METHOD_SUPERSEDED}: Module identity changed after enqueue: "
                f"{row['module_id']} {row['module_version']} -> {current.version}. "
                + _SUPERSEDED_ACTION,
                METHOD_SUPERSEDED,
            )
        if sha256_file(_source_path(current.implementation)) != row["source_sha256"]:
            raise SnapshotError(
                f"{METHOD_SUPERSEDED}: Module source changed after enqueue: "
                f"{row['module_id']}. " + _SUPERSEDED_ACTION,
                METHOD_SUPERSEDED,
            )
    selected = {
        str(row["slot"]): str(row["module_id"]) for row in manifest.get("modules", [])
    }
    selected_extensions = tuple(
        str(item) for item in project.get("selected_extensions", ())
    )
    validate_maturity_acknowledgements(
        registry,
        dict(project.get("modules") or {}),
        selected_extensions,
        dict(project.get("maturity_acknowledgements") or {}),
    )
    try:
        canonical_solver_contract = validate_project_solver_contract(
            project,
            registry,
            modules=selected,
            require_acknowledgement=True,
        )
    except ProjectSolverContractError as exc:
        if exc.code == "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED":
            raise SnapshotError(
                f"{METHOD_SUPERSEDED}: {exc}. " + _SUPERSEDED_ACTION,
                METHOD_SUPERSEDED,
            ) from exc
        raise SnapshotError(f"{exc.code}: {exc}", exc.code) from exc
    if canonical_solver_contract is not None and canonical_solver_contract != project.get(
        "solver_contract"
    ):
        raise SnapshotError("Frozen project solver contract is not canonical")
    available_data_roles = set(dict(pack.get("bindings") or {}))
    if network_pack is not None:
        available_data_roles.update(dict(network_pack.get("bindings") or {}))
    current_graph = registry.resolve_selection(
        selected,
        selected_extensions=selected_extensions,
        extension_parameters=dict(project.get("extension_parameters") or {}),
        available_data_roles=tuple(sorted(available_data_roles)),
    )
    frozen_graph = dict(manifest.get("module_resolution_graph") or {})
    if current_graph.graph_sha256 != frozen_graph.get("graph_sha256"):
        raise SnapshotError(
            f"{METHOD_SUPERSEDED}: Module resolution graph changed after enqueue. "
            + _SUPERSEDED_ACTION,
            METHOD_SUPERSEDED,
        )
    return manifest
