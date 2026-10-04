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
from .runtime_paths import activate_external_module_sources, external_modules_root
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
    source_root = source_root.resolve()
    for name, module in list(sys.modules.items()):
        raw = getattr(module, "__file__", None)
        if not raw:
            continue
        try:
            Path(raw).resolve().relative_to(source_root)
        except (OSError, ValueError):
            continue
        sys.modules.pop(name, None)
    text = str(source_root)
    while text in sys.path:
        sys.path.remove(text)
    importlib.invalidate_caches()


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
        target.parent.mkdir(parents=True, exist_ok=True)
        payload.replace(target)
        promoted = target
        active_manifest = root / f"{manifest.id}.json"
        _atomic_json(active_manifest, manifest.to_dict())
        activate_external_module_sources(root)
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
        if promoted is not None and promoted.exists():
            _inside(promoted, root / "installed")
            shutil.rmtree(promoted)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def set_module_enabled(
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
    original_record = dict(record)
    original_manifest = active_manifest.read_bytes() if active_manifest.is_file() else None
    source_text = str(source_root.resolve())
    try:
        if enabled:
            if active_manifest.exists():
                raise ModuleInstallationError("GF_MODULE_ID_COLLISION", "An active manifest already uses this module ID")
            activate_external_module_sources(root)
            if source_text not in sys.path:
                sys.path.insert(0, source_text)
            manifest = ModuleManifest.from_dict(
                json.loads((record_path.parent / str(record["manifest_path"])).read_text(encoding="utf-8"))
            )
            existing = workspace_registry(root)
            candidate = ModuleRegistryV2(tuple(existing.manifests().values()) + (manifest,))
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
            while source_text in sys.path:
                sys.path.remove(source_text)
            importlib.invalidate_caches()
        record["enabled"] = enabled
        record["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _atomic_json(record_path, record)
    except Exception:
        _atomic_json(record_path, original_record)
        if original_manifest is None:
            active_manifest.unlink(missing_ok=True)
            while source_text in sys.path:
                sys.path.remove(source_text)
        else:
            active_manifest.write_bytes(original_manifest)
            if source_text not in sys.path:
                sys.path.insert(0, source_text)
        importlib.invalidate_caches()
        raise
    result = dict(record)
    result["record_path"] = str(record_path.resolve())
    return result
