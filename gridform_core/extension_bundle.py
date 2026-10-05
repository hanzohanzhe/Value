"""Bounded, inventory-checked installation for VALUE extension bundles."""

from __future__ import annotations

import hashlib
import json
import importlib
import importlib.util
import re
import sys
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Mapping

from .extension_framework import (
    EXTENSION_SCHEMA, ExtensionManifest, ExtensionRegistry, canonical_hash, hook_source_identity,
    load_extension_manifests,
)
from .module_bundle import MAX_BUNDLE_BYTES, MAX_MEMBERS, MAX_UNCOMPRESSED_BYTES, validate_module_bundle
from .module_quarantine import MODULE_LIFECYCLE_LOCK
from .v2.module_manifest import workspace_registry
from .runtime_paths import PACKAGE_ROOT, activate_external_module_sources


DESCRIPTOR = "force-extension-bundle.json"
MANIFEST = "force-extension.json"
ALLOWED_ROOT = {DESCRIPTOR, MANIFEST, "LICENSE", "README.md"}


def _semver_tuple(value: str) -> tuple[int, int, int]:
    core = value.split("-", 1)[0]
    try:
        major, minor, patch = core.split(".")
        return int(major), int(minor), int(patch)
    except (TypeError, ValueError) as exc:
        raise ExtensionBundleError("GF_EXTENSION_VERSION", f"Invalid semantic version: {value}") from exc


def list_extension_installations(modules_root: Path) -> list[dict[str, object]]:
    root = modules_root.resolve()
    rows: list[dict[str, object]] = []
    for path in sorted((root / "installed-extensions").glob("*/*/installation.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            manifest = json.loads((path.parent / MANIFEST).read_text(encoding="utf-8"))
            if not isinstance(record, dict) or not isinstance(manifest, Mapping):
                continue
            observed_manifest_hash = canonical_hash(ExtensionManifest.from_dict(manifest).to_dict())
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        record.update({
            "name": manifest.get("name"), "licence": manifest.get("licence"),
            "maturity": manifest.get("maturity"),
            "provided_capabilities": manifest.get("provided_capabilities", []),
            "required_capabilities": manifest.get("required_capabilities", []),
            "composed_module_ids": manifest.get("composed_module_ids", []),
            "current_manifest_sha256": observed_manifest_hash,
            "installation_boundary": "local_force_data_home/modules/installed-extensions",
            "installation_path": str(path.parent.relative_to(root).as_posix()),
            "conformance": dict(record.get("conformance") or {}) if record.get("manifest_sha256") == observed_manifest_hash and isinstance(record.get("conformance"), Mapping) else {"status": "not_run", "meaning": "No retained validation matches this manifest"},
        })
        rows.append(record)
    return sorted(rows, key=lambda item: (str(item.get("extension_id")), str(item.get("version"))))


def _read_json_object(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _raw_extension_records(modules_root: Path) -> list[dict[str, object]]:
    """Installer records read as raw JSON, without parsing any manifest.

    Lifecycle decisions (disable, current version, migration checks) must not
    depend on whether a manifest still parses under the current schema: a
    schema-drifted or quarantined extension must remain disableable and must
    not hide its state schema from an upgrade (P0-2 S2).
    """

    root = modules_root.resolve()
    rows: list[dict[str, object]] = []
    for path in sorted((root / "installed-extensions").glob("*/*/installation.json")):
        record = _read_json_object(path)
        if record is None or not record.get("extension_id"):
            continue
        rows.append({
            **record,
            "installation_path": str(path.parent.relative_to(root).as_posix()),
            "record_path": path,
            "raw_manifest": _read_json_object(path.parent / MANIFEST),
        })
    return rows


def _current_local_installation(modules_root: Path, extension_id: str) -> dict[str, object] | None:
    records = [
        item for item in _raw_extension_records(modules_root)
        if item.get("extension_id") == extension_id and item.get("enabled")
    ]
    return max(records, key=lambda item: _semver_tuple(str(item["version"]))) if records else None


def _builtin_extensions() -> tuple[ExtensionManifest, ...]:
    return load_extension_manifests(PACKAGE_ROOT / "extension_manifests")


def _namespace_owner(modules_root: Path, extension_id: str, namespace: str) -> str | None:
    """The extension that really holds ``namespace`` (built-in or enabled local).

    Read from raw active manifests so an enabled but quarantined owner is still
    found, and so the answer never depends on file-name order (G4-01).
    """

    for manifest in _builtin_extensions():
        if manifest.namespace == namespace and manifest.id != extension_id:
            return manifest.id
    owners = []
    for path in sorted((modules_root.resolve() / "extensions").glob("*.json")):
        payload = _read_json_object(path)
        if payload is None:
            continue
        owner = str(payload.get("id") or path.stem)
        if payload.get("namespace") == namespace and owner != extension_id:
            owners.append(owner)
    return ", ".join(sorted(owners)) or None


def _public_record(row: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in row.items() if key not in {"record_path", "raw_manifest"}}


class ExtensionBundleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedExtensionBundle:
    descriptor: Mapping[str, object]
    manifest: ExtensionManifest
    members: tuple[str, ...]
    bundle_sha256: str
    bundle_bytes: int
    uncompressed_bytes: int


def _safe_name(raw: str) -> str:
    if "\\" in raw:
        raise ExtensionBundleError("GF_EXTENSION_PATH", "Members must use portable '/' paths")
    value = PurePosixPath(raw)
    if value.is_absolute() or not value.parts or any(part in {"", ".", ".."} for part in value.parts):
        raise ExtensionBundleError("GF_EXTENSION_PATH", f"Unsafe extension member: {raw}")
    if ":" in value.parts[0]:
        raise ExtensionBundleError("GF_EXTENSION_PATH", f"Drive-qualified member: {raw}")
    return value.as_posix()


def validate_extension_bundle(path: Path) -> ValidatedExtensionBundle:
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise ExtensionBundleError("GF_EXTENSION_FORMAT", "Select an extension .zip bundle")
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ExtensionBundleError("GF_EXTENSION_SIZE", "Extension bundle exceeds 25 MiB")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ExtensionBundleError("GF_EXTENSION_FORMAT", "Unreadable extension ZIP") from exc
    with archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        if len(infos) > MAX_MEMBERS:
            raise ExtensionBundleError("GF_EXTENSION_MEMBERS", "Extension contains too many members")
        names = [_safe_name(item.filename) for item in infos]
        if len(names) != len(set(names)) or len(names) != len({item.casefold() for item in names}):
            raise ExtensionBundleError("GF_EXTENSION_DUPLICATE", "Duplicate extension members")
        total = sum(item.file_size for item in infos)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ExtensionBundleError("GF_EXTENSION_EXPANSION", "Extension expands above 100 MiB")
        for info, name in zip(infos, names):
            mode = info.external_attr >> 16
            if info.flag_bits & 0x1 or (mode and stat.S_ISLNK(mode)):
                raise ExtensionBundleError("GF_EXTENSION_LINK", f"Encrypted/link member forbidden: {name}")
            parts = PurePosixPath(name).parts
            if name not in ALLOWED_ROOT and parts[0] not in {"modules", "schemas", "examples", "src"}:
                raise ExtensionBundleError("GF_EXTENSION_LAYOUT", f"Unexpected extension member: {name}")
            if parts[0] == "src" and (len(parts) < 3 or not name.endswith(".py") or any(not part.isidentifier() for part in parts[1:-1])):
                raise ExtensionBundleError("GF_EXTENSION_SOURCE", "Source members must be Python files inside a package")
            if name.endswith((".pyc", ".pyo", ".pyd", ".dll", ".exe", ".so", ".dylib", ".a", ".o")) or (name.endswith(".py") and parts[0] != "src"):
                raise ExtensionBundleError(
                    "GF_EXTENSION_EXECUTABLE",
                    "Python hooks must be inside the declared src package; composed code requires an independently validated module ZIP, and native binaries are forbidden",
                )
        missing = sorted({DESCRIPTOR, MANIFEST, "LICENSE"}.difference(names))
        if missing:
            raise ExtensionBundleError("GF_EXTENSION_REQUIRED", "Missing: " + ", ".join(missing))
        try:
            descriptor = json.loads(archive.read(DESCRIPTOR).decode("utf-8"))
            raw_manifest = json.loads(archive.read(MANIFEST).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
            raise ExtensionBundleError("GF_EXTENSION_JSON", "Invalid extension descriptor/manifest") from exc
        if not isinstance(descriptor, Mapping) or not isinstance(raw_manifest, Mapping):
            raise ExtensionBundleError("GF_EXTENSION_JSON", "Extension descriptor and manifest must be JSON objects")
        if descriptor.get("schema_version") != EXTENSION_SCHEMA:
            raise ExtensionBundleError("GF_EXTENSION_SCHEMA", f"Expected {EXTENSION_SCHEMA}")
        inventory = descriptor.get("files")
        if not isinstance(inventory, list):
            raise ExtensionBundleError("GF_EXTENSION_INVENTORY", "Missing exact member inventory")
        declared = {str(item.get("path")): item for item in inventory if isinstance(item, Mapping)}
        actual = set(names).difference({DESCRIPTOR})
        if set(declared) != actual or len(declared) != len(inventory):
            raise ExtensionBundleError("GF_EXTENSION_INVENTORY", "Inventory does not match members")
        for name in actual:
            data = archive.read(name)
            if declared[name].get("bytes") != len(data) or declared[name].get("sha256") != hashlib.sha256(data).hexdigest():
                raise ExtensionBundleError("GF_EXTENSION_HASH", f"Inventory mismatch: {name}")
        try:
            manifest = ExtensionManifest.from_dict(raw_manifest)
            ExtensionRegistry((manifest,))
            if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", manifest.id):
                raise ValueError("Extension ID is unsafe")
            packages = {PurePosixPath(name).parts[1] for name in names if name.startswith("src/")}
            hook_packages = {hook.implementation.split(":", 1)[0].split(".", 1)[0] for hook in manifest.hooks}
            if packages and (len(packages) != 1 or packages != hook_packages):
                raise ValueError("All source must belong to the one package declared by hooks")
            if packages:
                package = next(iter(packages))
                if "src/" + package + "/__init__.py" not in names:
                    raise ValueError("Extension source package requires __init__.py")
                for hook in manifest.hooks:
                    module_name = hook.implementation.split(":", 1)[0]
                    relative = "src/" + module_name.replace(".", "/")
                    if relative + ".py" not in names and relative + "/__init__.py" not in names:
                        raise ValueError("Hook implementation source is missing")
        except (TypeError, ValueError) as exc:
            raise ExtensionBundleError("GF_EXTENSION_MANIFEST", str(exc)) from exc
        with tempfile.TemporaryDirectory(prefix="force-extension-modules-") as temporary:
            for name in sorted(item for item in names if item.startswith("modules/") and item.endswith(".zip")):
                module_path = Path(temporary) / PurePosixPath(name).name
                module_path.write_bytes(archive.read(name))
                validate_module_bundle(module_path)
    return ValidatedExtensionBundle(
        descriptor, manifest, tuple(sorted(names)), hashlib.sha256(path.read_bytes()).hexdigest(),
        path.stat().st_size, total,
    )


def _packages(manifest: ExtensionManifest) -> set[str]:
    return {hook.implementation.split(":", 1)[0].split(".", 1)[0] for hook in manifest.hooks}


def _check_source_collisions(packages: set[str], root: Path) -> None:
    for package in packages:
        if package in sys.stdlib_module_names or package in sys.modules or package == "gridform_core" or importlib.util.find_spec(package) is not None:
            raise ExtensionBundleError("GF_EXTENSION_SOURCE_COLLISION", "Extension package is reserved or already importable: " + package)
        for folder in ("installed", "installed-extensions"):
            if any((source / package).exists() or (source / (package + ".py")).exists() for source in (root / folder).glob("*/*/src")):
                raise ExtensionBundleError("GF_EXTENSION_SOURCE_COLLISION", "Every extension version needs an independent package: " + package)


def _check_hooks(manifest: ExtensionManifest, source: Path | None) -> list[dict[str, object]]:
    packages = _packages(manifest) if source is not None else set()
    original_path = list(sys.path)
    retained_modules = {name: module for name, module in sys.modules.items() if name.split(".", 1)[0] in packages}
    try:
        if source is not None:
            sys.path.insert(0, str(source))
        importlib.invalidate_caches()
        identities = []
        for hook in manifest.hooks:
            identity = hook_source_identity(hook)
            module_name, symbol_name = hook.implementation.split(":", 1)
            symbol = getattr(importlib.import_module(module_name), symbol_name)
            instance = symbol() if isinstance(symbol, type) else symbol
            if not callable(getattr(instance, hook.hook, None)):
                raise ValueError("Extension declared hook is not callable")
            identities.append(identity)
        return identities
    except Exception as exc:
        raise ExtensionBundleError("GF_EXTENSION_HOOK", "Extension hook validation failed: " + str(exc)) from exc
    finally:
        sys.path[:] = original_path
        for name in list(sys.modules):
            if name.split(".", 1)[0] in packages:
                del sys.modules[name]
        sys.modules.update(retained_modules)
        importlib.invalidate_caches()


def install_extension_bundle(
    path: Path, *, trust_acknowledged: bool, modules_root: Path
) -> dict[str, object]:
    with MODULE_LIFECYCLE_LOCK:
        return _install_extension_bundle(
            path, trust_acknowledged=trust_acknowledged, modules_root=modules_root
        )


def _install_extension_bundle(
    path: Path, *, trust_acknowledged: bool, modules_root: Path
) -> dict[str, object]:
    if not trust_acknowledged:
        raise ExtensionBundleError(
            "GF_EXTENSION_TRUST_REQUIRED",
            "Confirm trust because composed module bundles may contain executable Python",
        )
    validated = validate_extension_bundle(path)
    root = modules_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    current = workspace_registry(root)
    if any(item.id == validated.manifest.id for item in _builtin_extensions()):
        raise ExtensionBundleError(
            "GF_EXTENSION_BUILTIN_COLLISION",
            "A retained built-in extension cannot be overwritten",
        )
    existing_installation = _current_local_installation(root, validated.manifest.id)
    if existing_installation is not None:
        current_version = str(existing_installation["version"])
        if validated.manifest.version == current_version:
            if validated.bundle_sha256 == existing_installation.get("bundle_sha256"):
                listed = next((
                    row for row in list_extension_installations(root)
                    if row.get("extension_id") == validated.manifest.id and row.get("version") == current_version
                ), None)
                return {**(listed or _public_record(existing_installation)), "idempotent": True}
            raise ExtensionBundleError(
                "GF_EXTENSION_VERSION_COLLISION",
                "The same extension version already exists with different bytes",
            )
        if _semver_tuple(validated.manifest.version) < _semver_tuple(current_version):
            raise ExtensionBundleError(
                "GF_EXTENSION_DOWNGRADE",
                f"Refusing downgrade from {current_version} to {validated.manifest.version}",
            )
        migration = validated.manifest.state_migrations.get(current_version)
        # The retained manifest is read as raw JSON: a quarantined or
        # schema-drifted current version must not bypass this check.
        retained_manifest = existing_installation.get("raw_manifest")
        if not isinstance(retained_manifest, Mapping):
            raise ExtensionBundleError(
                "GF_EXTENSION_INSTALL_STATE",
                f"The installed {current_version} manifest is unreadable; disable that version before upgrading",
            )
        if retained_manifest.get("state_schema_version") and not migration:
            raise ExtensionBundleError(
                "GF_EXTENSION_MIGRATION_REQUIRED",
                f"Upgrade from {current_version} must declare a state migration",
            )
    owner = _namespace_owner(root, validated.manifest.id, validated.manifest.namespace)
    if owner:
        raise ExtensionBundleError(
            "GF_EXTENSION_NAMESPACE_COLLISION",
            f"Extension namespace {validated.manifest.namespace} is owned by enabled extension {owner}; "
            f"disable {owner} before installing {validated.manifest.id}",
        )
    combined = tuple(
        manifest for extension_id, manifest in current.extension_manifests().items()
        if extension_id != validated.manifest.id
    ) + (validated.manifest,)
    try:
        ExtensionRegistry(combined)
    except ValueError as exc:
        raise ExtensionBundleError("GF_EXTENSION_REGISTRY_CONFLICT", str(exc)) from exc
    available_modules = set(current.manifests())
    embedded = {
        str(item)
        for item in validated.manifest.composed_module_ids
        if str(item) in available_modules
    }
    missing = sorted(set(validated.manifest.composed_module_ids).difference(embedded))
    if missing:
        raise ExtensionBundleError(
            "GF_EXTENSION_COMPOSED_MODULE",
            "Install and validate composed module bundles first: " + ", ".join(missing),
        )
    target = root / "installed-extensions" / validated.manifest.id / validated.manifest.version
    if target.exists():
        raise ExtensionBundleError("GF_EXTENSION_VERSION_COLLISION", "Extension version already installed")
    source_members = [name for name in validated.members if name.startswith("src/")]
    if source_members:
        _check_source_collisions(_packages(validated.manifest), root)
    staging_parent = root / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="extension-", dir=staging_parent))
    active = root / "extensions" / f"{validated.manifest.id}.json"
    previous = Path(existing_installation["record_path"]) if existing_installation else None
    retained = {item: item.read_bytes() if item.exists() else None for item in (active, *((previous,) if previous else ()))}
    promoted = False
    try:
        with zipfile.ZipFile(path) as archive:
            for name in validated.members:
                destination = stage.joinpath(*PurePosixPath(name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))
        hook_identities = _check_hooks(validated.manifest, stage / "src" if source_members else None)
        record = {
            "schema_version": "value.extension-installation/v1", "extension_id": validated.manifest.id,
            "version": validated.manifest.version, "namespace": validated.manifest.namespace,
            "manifest_sha256": canonical_hash(validated.manifest.to_dict()),
            "conformance": {"status": "passed", "meaning": "structural extension contract and declared hook callable checks only"},
            "bundle_sha256": validated.bundle_sha256, "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "enabled": True, "source_root": "src" if source_members else None,
            "hook_source_identities": hook_identities,
            "upgraded_from": str(existing_installation["version"]) if existing_installation else None,
            "state_migration": validated.manifest.state_migrations.get(str(existing_installation["version"])) if existing_installation else None,
            "state_migration_executed": False,
        }
        (stage / "installation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        stage.replace(target)
        promoted = True
        active.parent.mkdir(parents=True, exist_ok=True)
        temporary = active.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(validated.manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
        temporary.replace(active)
        if previous:
            previous_record = json.loads(retained[previous])
            previous_record.update(enabled=False, superseded_by=validated.manifest.version)
            previous.write_text(json.dumps(previous_record, indent=2) + "\n", encoding="utf-8")
        activate_external_module_sources(root)
        return record
    except Exception:
        if promoted and target.exists():
            shutil.rmtree(target)
        if stage.exists():
            shutil.rmtree(stage)
        active.with_suffix(".json.tmp").unlink(missing_ok=True)
        for item, contents in retained.items():
            if contents is None:
                item.unlink(missing_ok=True)
            else:
                item.write_bytes(contents)
        activate_external_module_sources(root)
        raise


def set_extension_enabled(
    extension_id: str,
    enabled: bool,
    *,
    modules_root: Path,
) -> dict[str, object]:
    with MODULE_LIFECYCLE_LOCK:
        return _set_extension_enabled(extension_id, enabled, modules_root=modules_root)


def _set_extension_enabled(
    extension_id: str,
    enabled: bool,
    *,
    modules_root: Path,
) -> dict[str, object]:
    root = modules_root.resolve()
    # Raw installer records: a schema-drifted extension stays disableable (R6).
    records = [
        item for item in _raw_extension_records(root)
        if item.get("extension_id") == extension_id
    ]
    if not records:
        raise ExtensionBundleError(
            "GF_EXTENSION_BUILTIN_LIFECYCLE",
            "Built-in or unknown extensions cannot be disabled from the browser",
        )
    record = max(records, key=lambda item: _semver_tuple(str(item["version"])))
    record_path = Path(record["record_path"])
    listed = next((
        row for row in list_extension_installations(root)
        if row.get("extension_id") == extension_id and row.get("version") == record.get("version")
    ), None)
    record = listed or _public_record(record)
    stored = json.loads(record_path.read_text(encoding="utf-8"))
    active = root / "extensions" / f"{extension_id}.json"
    inactive = root / "disabled-extensions" / f"{extension_id}.json"
    source_manifest = record_path.parent / MANIFEST
    if enabled:
        try:
            manifest = ExtensionManifest.from_dict(json.loads(source_manifest.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError, AttributeError) as exc:
            raise ExtensionBundleError(
                "GF_EXTENSION_MANIFEST", f"The installed extension manifest is not valid: {exc}"
            ) from exc
        owner = _namespace_owner(root, extension_id, manifest.namespace)
        if owner:
            raise ExtensionBundleError(
                "GF_EXTENSION_NAMESPACE_COLLISION",
                f"Extension namespace {manifest.namespace} is owned by enabled extension {owner}; "
                f"disable {owner} before enabling {extension_id}",
            )
    if enabled and stored.get("source_root") == "src":
        observed = _check_hooks(manifest, record_path.parent / "src")
        if observed != stored.get("hook_source_identities"):
            raise ExtensionBundleError("GF_EXTENSION_SOURCE_CHANGED", "Installed hook source no longer matches its retained identity")
    retained = {item: item.read_bytes() if item.exists() else None for item in (record_path, active, inactive)}
    try:
        stored["enabled"] = bool(enabled)
        stored["state_changed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        temporary_record = record_path.with_suffix(".json.tmp")
        temporary_record.write_text(json.dumps(stored, indent=2) + "\n", encoding="utf-8")
        temporary_record.replace(record_path)
        destination = active if enabled else inactive
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_bytes(source_manifest.read_bytes())
        temporary.replace(destination)
        (inactive if enabled else active).unlink(missing_ok=True)
        activate_external_module_sources(root)
        return {**record, **stored}
    except Exception:
        for item, contents in retained.items():
            item.with_suffix(".json.tmp").unlink(missing_ok=True)
            if contents is None:
                item.unlink(missing_ok=True)
            else:
                item.write_bytes(contents)
        activate_external_module_sources(root)
        raise
