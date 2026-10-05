"""Transactional installation lifecycle for local executable VALUE modules."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .module_bundle import (
    MODULE_MANIFEST,
    ModuleBundleError,
    extract_validated_bundle,
    validate_module_bundle,
)
from .module_conformance import check_manifest
from . import module_quarantine
from .module_quarantine import MODULE_LIFECYCLE_LOCK, ExternalImportError, ModuleQuarantinedError, quarantine_keys
from .runtime_paths import activate_external_module_sources, external_modules_root, purge_source_root
from .v2.module_manifest import ModuleManifest, ModuleRegistryV2, builtin_registry, workspace_registry


INSTALLATION_SCHEMA = "value.module-installation/v1"
MODULE_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
RESERVED_PACKAGES = {"backend", "examples", "gridform_core", "gridform_validation", "scripts", "tests"}


class ModuleInstallationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _inside(path: Path, root: Path) -> Path:
    resolved, parent = path.resolve(), root.resolve()
    try:
        resolved.relative_to(parent)
    except ValueError as exc:
        raise ModuleInstallationError("GF_MODULE_INSTALL_PATH", "Module installation escaped its managed root") from exc
    return resolved


def _records(modules_root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted((modules_root / "installed").glob("*/*/installation.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("schema_version") == INSTALLATION_SCHEMA:
            value["record_path"] = str(path.resolve())
            records.append(value)
    return records


def list_module_installations(modules_root: Path | None = None) -> list[dict[str, object]]:
    root = (modules_root or external_modules_root()).resolve()
    return _records(root)


def _entry_source_exists(source_root: Path, implementation: str) -> bool:
    module_name = implementation.split(":", 1)[0]
    relative = Path(*module_name.split("."))
    return (source_root / relative).with_suffix(".py").is_file() or (source_root / relative / "__init__.py").is_file()


def _remove_staged_modules(source_root: Path) -> None:
    purge_source_root(source_root)


def _active_package_names(root: Path) -> set[str]:
    return {
        str(record.get("implementation_package"))
        for record in _records(root)
        if record.get("implementation_package")
    }


def _validate_manifest_for_install(
    payload: Mapping[str, object], source_root: Path, modules_root: Path
) -> tuple[ModuleManifest, dict[str, object]]:
    try:
        manifest = ModuleManifest.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise ModuleInstallationError("GF_MODULE_MANIFEST", f"Module manifest fields are invalid: {exc}") from exc
    if not MODULE_ID.fullmatch(manifest.id):
        raise ModuleInstallationError(
            "GF_MODULE_ID", "Module ID must use 3-64 lowercase letters, numbers or hyphens"
        )
    if manifest.status not in {"ready", "experimental", "not_evaluated"}:
        raise ModuleInstallationError("GF_MODULE_STATUS", "Installable modules must declare ready, experimental or not_evaluated maturity; unfinished placeholders are not installable")
    if not _entry_source_exists(source_root, manifest.implementation):
        raise ModuleInstallationError(
            "GF_MODULE_ENTRY_POINT",
            "The declared implementation is not provided by this bundle's src/ package",
        )
    top_level = manifest.implementation.split(":", 1)[0].split(".", 1)[0]
    if top_level in RESERVED_PACKAGES:
        raise ModuleInstallationError(
            "GF_MODULE_PACKAGE_COLLISION", f"External package name is reserved by VALUE: {top_level}"
        )
    builtins = builtin_registry().manifests()
    if manifest.id in builtins:
        raise ModuleInstallationError("GF_MODULE_BUILTIN_COLLISION", "A bundle cannot replace a built-in VALUE module")
    installed_ids = {str(record.get("module_id")) for record in _records(modules_root)}
    if manifest.id in installed_ids:
        raise ModuleInstallationError(
            "GF_MODULE_ID_COLLISION",
            "That module ID is already installed; publish a new ID for a new scientific implementation",
        )
    if (modules_root / "disabled-manifests" / "installed" / manifest.id).exists():
        # A parked (damaged) installation keeps its ID taken, like a disabled one.
        raise ModuleInstallationError(
            "GF_MODULE_ID_COLLISION",
            "That module ID belongs to a parked installation; publish a new ID for a new scientific implementation",
        )
    if top_level in _active_package_names(modules_root):
        raise ModuleInstallationError(
            "GF_MODULE_PACKAGE_COLLISION", "The bundle's top-level Python package is already installed"
        )
    source_text = str(source_root.resolve())
    sys.path.insert(0, source_text)
    importlib.invalidate_caches()
    try:
        existing = workspace_registry(modules_root)
        registry = ModuleRegistryV2(tuple(existing.manifests().values()) + (manifest,))
        conformance = check_manifest(registry, manifest)
    except (ImportError, ModuleNotFoundError, ValueError) as exc:
        raise ModuleInstallationError("GF_MODULE_RESOLUTION", f"Module implementation could not be loaded: {exc}") from exc
    finally:
        _remove_staged_modules(source_root)
    if conformance["status"] != "passed":
        raise ModuleInstallationError(
            "GF_MODULE_CONFORMANCE",
            "; ".join(str(item) for item in conformance.get("errors") or ["Module conformance failed"]),
        )
    return manifest, conformance


def install_module_bundle(
    bundle_path: Path,
    *,
    trust_acknowledged: bool,
    modules_root: Path | None = None,
) -> dict[str, object]:
    with MODULE_LIFECYCLE_LOCK:
        return _install_module_bundle(
            bundle_path, trust_acknowledged=trust_acknowledged, modules_root=modules_root
        )


def _install_module_bundle(
    bundle_path: Path,
    *,
    trust_acknowledged: bool,
    modules_root: Path | None = None,
) -> dict[str, object]:
    if not trust_acknowledged:
        raise ModuleInstallationError(
            "GF_MODULE_TRUST_REQUIRED",
            "Confirm that this bundle contains executable Python from a source you trust",
        )
    root = (modules_root or external_modules_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    staging_parent = root / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    try:
        validated = validate_module_bundle(bundle_path)
    except ModuleBundleError as exc:
        raise ModuleInstallationError(exc.code, str(exc)) from exc
    stage = Path(tempfile.mkdtemp(prefix="module-", dir=staging_parent)).resolve()
    payload = stage / "package"
    promoted: Path | None = None
    active_manifest: Path | None = None
    created_parent = False
    try:
        extract_validated_bundle(bundle_path, payload, validated)
        source_root = payload / "src"
        manifest, conformance = _validate_manifest_for_install(validated.manifest, source_root, root)
        target = _inside(root / "installed" / manifest.id / manifest.version, root / "installed")
        if target.exists():
            raise ModuleInstallationError("GF_MODULE_VERSION_COLLISION", "This module version is already installed")
        record: dict[str, object] = {
            "schema_version": INSTALLATION_SCHEMA,
            "module_id": manifest.id,
            "name": manifest.name,
            "module_version": manifest.version,
            "scientific_version": manifest.scientific_version,
            "slot": manifest.slot,
            "contract_version": manifest.contract_version,
            "implementation": manifest.implementation,
            "implementation_package": manifest.implementation.split(":", 1)[0].split(".", 1)[0],
            "source_root": "src",
            "manifest_path": MODULE_MANIFEST,
            "bundle_path": "original-bundle.zip",
            "bundle_sha256": validated.bundle_sha256,
            "bundle_bytes": validated.bundle_bytes,
            "uncompressed_bytes": validated.uncompressed_bytes,
            "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "enabled": True,
            "origin": "local_bundle",
            "execution_boundary": "in_process_trusted_python",
            "scientific_validation_status": "not_evaluated",
            "conformance": conformance,
            "manifest_sha256": hashlib.sha256(
                json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        }
        shutil.copy2(bundle_path, payload / "original-bundle.zip")
        _atomic_json(payload / "installation.json", record)
        before_keys = quarantine_keys(workspace_registry(root))
        created_parent = not target.parent.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload.replace(target)
        promoted = target
        active_manifest = root / f"{manifest.id}.json"
        _atomic_json(active_manifest, manifest.to_dict())
        activate_external_module_sources(root)
        _verify_written(root, before_keys, manifest.id)
        registry = workspace_registry(root)
        registry.resolve(manifest.id, expected_slot=manifest.slot)
        record["source_sha256"] = hashlib.sha256(
            Path(importlib.import_module(manifest.implementation.split(":", 1)[0]).__file__).read_bytes()
        ).hexdigest()
        _atomic_json(target / "installation.json", record)
        result = dict(record)
        result["record_path"] = str((target / "installation.json").resolve())
        return result
    except Exception:
        if active_manifest is not None and active_manifest.exists():
            active_manifest.unlink()
        if promoted is not None:
            # The promoted source root was activated on sys.path and may have
            # been imported; leave no import state behind (P0-2 R5).
            purge_source_root(promoted / "src")
        if promoted is not None and promoted.exists():
            _inside(promoted, root / "installed")
            shutil.rmtree(promoted)
        if promoted is not None and created_parent:
            try:
                promoted.parent.rmdir()  # only the empty <id>/ folder this install created
            except OSError:
                pass
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _verify_written(root: Path, before_keys: frozenset, module_id: str) -> None:
    """Post-write check in this process and in a fresh worker-like process (P0-2 S4)."""

    try:
        module_quarantine.verify_after_write(root, before_keys=before_keys, kind="module", entry_id=module_id)
    except ModuleQuarantinedError as exc:
        raise ModuleInstallationError(exc.code, str(exc)) from exc


def set_module_enabled(
    module_id: str,
    enabled: bool,
    *,
    modules_root: Path | None = None,
) -> dict[str, object]:
    with MODULE_LIFECYCLE_LOCK:
        return _set_module_enabled(module_id, enabled, modules_root=modules_root)


def _set_module_enabled(
    module_id: str,
    enabled: bool,
    *,
    modules_root: Path | None = None,
) -> dict[str, object]:
    root = (modules_root or external_modules_root()).resolve()
    matches = [record for record in _records(root) if record.get("module_id") == module_id]
    if not matches:
        raise ModuleInstallationError("GF_MODULE_NOT_INSTALLED", "Only installed external modules can be changed")
    if len(matches) != 1:
        raise ModuleInstallationError("GF_MODULE_INSTALL_STATE", "Module installation identity is ambiguous")
    record = matches[0]
    record_path = Path(str(record.pop("record_path")))
    active_manifest = root / f"{module_id}.json"
    source_root = record_path.parent / str(record["source_root"])
    # Byte-exact rollback: the record and the active manifest are restored to
    # the bytes they had, never re-serialised (P0-2 S2).
    original_record = record_path.read_bytes()
    original_manifest = active_manifest.read_bytes() if active_manifest.is_file() else None
    source_text = str(source_root.resolve())
    try:
        if enabled:
            if active_manifest.exists():
                raise ModuleInstallationError("GF_MODULE_ID_COLLISION", "An active manifest already uses this module ID")
            activate_external_module_sources(root)
            manifest = ModuleManifest.from_dict(
                json.loads((record_path.parent / str(record["manifest_path"])).read_text(encoding="utf-8"))
            )
            existing = workspace_registry(root)
            before_keys = quarantine_keys(existing)
            # workspace_registry re-activates only enabled sources; the source
            # being enabled goes on sys.path after it, for the candidate check.
            if source_text not in sys.path:
                sys.path.insert(0, source_text)
            importlib.invalidate_caches()
            try:
                candidate = ModuleRegistryV2(tuple(existing.manifests().values()) + (manifest,))
            except ExternalImportError as exc:
                raise ModuleInstallationError("GF_MODULE_IMPORT_FAILED", str(exc)) from exc
            except ValueError as exc:
                if getattr(exc, "code", None):
                    raise
                if "Duplicate module ID" in str(exc):
                    raise ModuleInstallationError("GF_MODULE_ID_COLLISION", str(exc)) from exc
                raise ModuleInstallationError(
                    "GF_MODULE_RESOLUTION", f"Module implementation could not be loaded: {exc}"
                ) from exc
            conformance = check_manifest(candidate, manifest)
            if conformance["status"] != "passed":
                raise ModuleInstallationError("GF_MODULE_CONFORMANCE", "Module no longer passes conformance")
            _atomic_json(active_manifest, manifest.to_dict())
            record["conformance"] = conformance
            record["manifest_sha256"] = hashlib.sha256(
                json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest()
        else:
            active_manifest.unlink(missing_ok=True)
            # Disabled code must not stay importable from sys.modules (P0-2 R4).
            purge_source_root(source_root)
        record["enabled"] = enabled
        record["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _atomic_json(record_path, record)
        if enabled:
            _verify_written(root, before_keys, module_id)
    except Exception:
        for temporary in (record_path, active_manifest):
            temporary.with_suffix(temporary.suffix + ".tmp").unlink(missing_ok=True)
        record_path.write_bytes(original_record)
        if original_manifest is None:
            active_manifest.unlink(missing_ok=True)
            purge_source_root(source_root)
        else:
            active_manifest.write_bytes(original_manifest)
            if source_text not in sys.path:
                sys.path.insert(0, source_text)
        importlib.invalidate_caches()
        raise
    result = dict(record)
    result["record_path"] = str(record_path.resolve())
    return result
