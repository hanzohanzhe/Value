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
from .v2.module_manifest import SUPPORTED_CONTRACTS, ModuleManifest, ModuleRegistryV2, builtin_registry, workspace_registry


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


def _implementation_source(record: Mapping[str, object]) -> Path | None:
    record_path = Path(str(record.get("record_path") or ""))
    module_name = str(record.get("implementation") or "").split(":", 1)[0]
    if not module_name or not record_path.name:
        return None
    base = record_path.parent / str(record.get("source_root") or "src") / Path(*module_name.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def installed_source_changes(
    module_ids: object, *, modules_root: Path | None = None,
) -> list[dict[str, object]]:
    """Enabled installed modules whose source changed since install (A16-4, M-D2).

    An in-place source edit of an installed module is accepted and recorded:
    the run records the new source hash and the comparison shows a method
    change; this read-only check lets preflight say so.  Reads bytes only and
    never imports installed code.
    """

    wanted = {str(item) for item in (module_ids or ()) if item}
    changes: list[dict[str, object]] = []
    for record in list_module_installations(modules_root):
        module_id = str(record.get("module_id") or "")
        installed = str(record.get("source_sha256") or "").lower()
        if module_id not in wanted or not record.get("enabled") or not re.fullmatch(r"[0-9a-f]{64}", installed):
            continue
        source = _implementation_source(record)
        if source is None:
            continue
        current = hashlib.sha256(source.read_bytes()).hexdigest()
        if current != installed:
            changes.append({"module_id": module_id, "installed_sha256": installed, "current_sha256": current})
    return sorted(changes, key=lambda row: str(row["module_id"]))


def disabled_selections(
    registry: object, module_ids: object = (), extension_ids: object = (), *, modules_root: Path | None = None,
) -> list[dict[str, object]]:
    """Selected local modules/extensions that are installed but disabled (M2-N2).

    A disabled entry is not registered, so the selection check alone says
    "Module is not registered"; this names the cause.  Reads installation
    records only; never imports installed code.
    """

    from .extension_bundle import list_extension_installations

    root = (modules_root or external_modules_root()).resolve()
    registered_modules = set(getattr(registry, "manifests", lambda: {})())
    registered_extensions = set(getattr(registry, "extension_manifests", lambda: {})())
    found: list[dict[str, object]] = []
    for kind, wanted, registered, records, key in (
        ("module", module_ids, registered_modules, list_module_installations(root), "module_id"),
        ("extension", extension_ids, registered_extensions, list_extension_installations(root), "extension_id"),
    ):
        for entry_id in dict.fromkeys(str(item) for item in (wanted or ()) if item):
            if entry_id in registered:
                continue
            rows = [row for row in records if str(row.get(key) or "") == entry_id]
            if rows and not any(row.get("enabled") for row in rows):
                versions = sorted({str(row.get("module_version" if kind == "module" else "version") or "") for row in rows})
                found.append({"kind": kind, "id": entry_id, "versions": [item for item in versions if item]})
    return found


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


def check_slot_contract(manifest: ModuleManifest) -> None:
    """The slot and contract a module declares, checked before any code is loaded (R4 M-低5)."""

    expected = SUPPORTED_CONTRACTS.get(manifest.slot)
    if expected is None:
        raise ModuleInstallationError(
            "GF_MODULE_SLOT_UNSUPPORTED",
            f"Slot {manifest.slot!r} is not a replaceable VALUE module slot; use one of "
            + ", ".join(sorted(SUPPORTED_CONTRACTS)) + ".",
        )
    if manifest.contract_version != expected:
        retired = (" Contract IDs beginning with 'gridform.' are the retired names; VALUE uses 'value.*' contracts."
                   if str(manifest.contract_version).startswith("gridform.") else "")
        raise ModuleInstallationError(
            "GF_MODULE_CONTRACT_MISMATCH",
            f"Module {manifest.id} in slot {manifest.slot} uses {manifest.contract_version}; expected {expected}. "
            f"Set contract_version to {expected} in the manifest and rebuild the bundle." + retired,
        )


def _validate_manifest_for_install(
    payload: Mapping[str, object], source_root: Path | None, modules_root: Path
) -> tuple[ModuleManifest, dict[str, object]]:
    """``source_root`` None: only the checks that need no extracted or imported code (precheck)."""
    try:
        manifest = ModuleManifest.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise ModuleInstallationError("GF_MODULE_MANIFEST", f"Module manifest fields are invalid: {exc}") from exc
    check_slot_contract(manifest)
    if not MODULE_ID.fullmatch(manifest.id):
        raise ModuleInstallationError(
            "GF_MODULE_ID", "Module ID must use 3-64 lowercase letters, numbers or hyphens"
        )
    if manifest.status not in {"ready", "experimental", "not_evaluated"}:
        raise ModuleInstallationError("GF_MODULE_STATUS", "Installable modules must declare ready, experimental or not_evaluated maturity; unfinished placeholders are not installable")
    if source_root is not None and not _entry_source_exists(source_root, manifest.implementation):
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
    if source_root is None:
        return manifest, {}
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


def precheck_module_bundle(bundle_path: Path, *, modules_root: Path | None = None) -> None:
    """The install refusals that need no extraction or import; writes nothing (R4 F-低5).

    Run before a pending-runs confirmation is asked, so a bundle that would be
    refused anyway is refused first.
    """

    try:
        validated = validate_module_bundle(bundle_path)
    except ModuleBundleError as exc:
        raise ModuleInstallationError(exc.code, str(exc)) from exc
    _validate_manifest_for_install(validated.manifest, None, (modules_root or external_modules_root()).resolve())


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
    from .module_recovery import active_manifests_declaring, park_other_manifests

    parked: list[dict[str, object]] = []
    try:
        if enabled:
            if active_manifest.exists():
                raise ModuleInstallationError("GF_MODULE_ID_COLLISION", "An active manifest already uses this module ID")
            others = [path.name for path in active_manifests_declaring(root, "module", module_id)]
            if others:
                # R5-3 中2: a copied manifest with this ID is still in the
                # scanned folder; enabling would only quarantine both.
                raise ModuleInstallationError(
                    "GF_MODULE_ID_COLLISION",
                    "Another active manifest declares this module ID (modules/" + ", modules/".join(others)
                    + "); press Disable on its row in the quarantine panel, then Enable again",
                )
            activate_external_module_sources(root)
            manifest = ModuleManifest.from_dict(
                json.loads((record_path.parent / str(record["manifest_path"])).read_text(encoding="utf-8"))
            )
            check_slot_contract(manifest)
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
            # R5-3 中2: a second manifest with this ID (for example a copy of
            # <id>.json) is parked too, so a disabled ID leaves the scanned
            # folder completely and the quarantine it caused clears.
            parked = park_other_manifests(root, "module", module_id)
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
        for item in parked:
            # Parked copies go back where they were (byte-exact rollback).
            moved, original = root / str(item["parked"]), root / str(item["from"])
            if moved.is_file() and not original.exists():
                moved.replace(original)
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
    if parked:
        result["parked_manifests"] = [str(item["parked"]) for item in parked]
    return result
