"""Fault isolation for locally installed modules and extensions (P0-2).

Built-in manifests stay fail-closed: a broken built-in still stops the
process.  External (installer-owned) manifests are fail-isolated: a broken
external entry is quarantined in memory, never written into the scanned
``modules/`` tree, and no external entry silently wins a conflict.

One re-entrant ``MODULE_LIFECYCLE_LOCK`` serialises every install, enable,
disable and catalogue refresh in the process.  Global lock order
(P0_CONVENTIONS section 5): ``.backend.lock -> STUDY_LIFECYCLE_LOCK ->
RUN_ACTION_LOCKS[run] -> MODULE_LIFECYCLE_LOCK -> .reservation.lock ->
status.lock``; while it is held no STUDY_LIFECYCLE_LOCK may be requested.

At import time this module depends only on the standard library and
``errors`` so the registry, the extension framework and the worker can import
it cheaply; the registry and the probe helpers are imported lazily.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping

from .errors import ContractError

MODULE_LIFECYCLE_LOCK = threading.RLock()


class ModuleQuarantinedError(ContractError):
    """A coded module-lifecycle or quarantine failure.

    A ``ValueError`` (through ``ContractError``) so every existing handler
    still catches it; ``code`` is per instance and doubles as the public
    failure code a worker records.
    """

    category = "contract"

    def __init__(self, code: str, message: str, *, entries: tuple = ()) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.entries = tuple(entries)


class ExternalImportError(ValueError):
    """An implementation module raised while being imported (any exception)."""


class ExtensionHookImportError(ModuleQuarantinedError):
    """An extension hook module could not be imported; runtime-quarantined."""

    def __init__(
        self, message: str, *, extension_id: str | None = None, error_type: str = "ValueError",
        entries: tuple = (),
    ) -> None:
        super().__init__("GF_EXTENSION_HOOK_IMPORT", message, entries=entries)
        self.extension_id = extension_id
        self.error_type = error_type


# -- error codes -------------------------------------------------------------
# Quarantine reasons (one per entry) and lifecycle/HTTP codes.  The HTTP status
# of every coded lifecycle error is looked up in ERROR_CODE_STATUS (C1).
QUARANTINE_CODES = (
    "GF_MODULE_IMPORT_FAILED",
    "GF_MODULE_MANIFEST_INVALID",
    "GF_MODULE_ID_DUPLICATE",
    "GF_MODULE_SHADOWS_BUILTIN",
    "GF_EXTENSION_MANIFEST_INVALID",
    "GF_EXTENSION_ID_DUPLICATE",
    "GF_EXTENSION_NAMESPACE_COLLISION",
    "GF_EXTENSION_SHADOWS_BUILTIN",
    "GF_EXTENSION_HOOK_IMPORT",
    "GF_MODULE_INSTALL_RECORD_INVALID",
)

# An installer-owned folder whose record the execution archive cannot read:
# every run start is refused until it is repaired or parked.
INSTALL_RECORD_CODE = "GF_MODULE_INSTALL_RECORD_INVALID"

ERROR_CODE_STATUS: dict[str, int] = {
    # P0-8 S5: historical zonal solver contracts and superseded Run methods.
    "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED": 409,
    "GF_RUN_METHOD_SUPERSEDED": 409,
    "GF_MODULE_QUARANTINED": 409,
    "GF_STUDY_MODULE_QUARANTINED": 409,
    "GF_PREFLIGHT_MODULE_QUARANTINED": 409,
    "GF_EXTENSION_HOOK_IMPORT": 409,
    "GF_EXTENSION_NAMESPACE_COLLISION": 409,
    "GF_EXTENSION_REGISTRY_CONFLICT": 409,
    "GF_MODULE_REGISTRY_CONFLICT": 409,
    "GF_MODULE_PROBE_FAILED": 409,
    "GF_MODULE_PROBE_TIMEOUT": 504,
    "GF_MODULE_LIFECYCLE_RUNS_PENDING": 409,
    "GF_MODULE_CATALOG_STALE": 503,
    "GF_MODULE_CATALOG_REFRESH": 503,
    "GF_MODULE_ID_COLLISION": 409,
    "GF_MODULE_VERSION_COLLISION": 409,
    "GF_MODULE_PACKAGE_COLLISION": 409,
    "GF_MODULE_BUILTIN_COLLISION": 409,
    "GF_MODULE_IN_USE": 409,
    "GF_EXTENSION_IN_USE": 409,
    "GF_EXTENSION_VERSION_COLLISION": 409,
    "GF_EXTENSION_BUILTIN_COLLISION": 409,
    "GF_EXTENSION_SOURCE_COLLISION": 409,
    "GF_EXTENSION_MIGRATION_REQUIRED": 409,
    "GF_EXTENSION_DOWNGRADE": 409,
    "GF_EXTENSION_INSTALL_STATE": 409,
    "GF_MODULE_INSTALL_STATE": 409,
    "GF_EXECUTION_ARCHIVE_MODULE_RECORD": 409,
    "GF_MODULE_INSTALL_RECORD_INVALID": 409,
    "GF_MODULE_IMPORT_FAILED": 409,
    "GF_MODULE_NOT_INSTALLED": 404,
    "GF_MODULE_BUNDLE_SIZE": 413,
    "GF_EXTENSION_SIZE": 413,
}


def status_for_code(code: str) -> int:
    return ERROR_CODE_STATUS.get(code, 400)


# -- quarantine entries -------------------------------------------------------
@dataclass(frozen=True)
class QuarantinedEntry:
    """One external manifest the registry refused, with its reason.

    ``shadows_registered`` marks an external entry that collides with a
    built-in: the built-in stays registered, so a Study selecting that ID is
    not blocked.  ``manifest_file`` is relative to ``modules/`` (no absolute
    paths ever leave this object).  ``version`` is filled from the raw
    manifest or the installer folder when known (quarantine_report).
    """

    kind: str
    manifest_file: str
    entry_id: str | None
    code: str
    error_type: str
    message: str
    shadows_registered: bool = False
    version: str | None = None

    def key(self) -> tuple[str, str]:
        return (self.kind, self.entry_id or "file:" + self.manifest_file)

    @property
    def blocking(self) -> bool:
        return not self.shadows_registered

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind, "id": self.entry_id, "manifest_file": self.manifest_file,
            "version": self.version,
            "error_code": self.code, "error_type": self.error_type, "message": self.message,
            "shadows_registered": self.shadows_registered,
            "corrective_action": corrective_action(self),
        }


# The offline tool is named, never given as a bare "python -m" command: on an
# installed VALUE it needs the bundled interpreter, PYTHONPATH and the data
# directory, which the user guide spells out per platform.
OFFLINE_HELP = "stop VALUE first; the user guide section 'Offline module recovery' gives the exact command"


def corrective_action(entry: QuarantinedEntry) -> str:
    if entry.code == INSTALL_RECORD_CODE:
        target = " ".join(item for item in (entry.kind, entry.entry_id or "", entry.version or "") if item)
        return (f"Move the damaged installation aside offline: module_recovery park-installation {target} "
                f"({OFFLINE_HELP})")
    if entry.entry_id and entry.kind == "module":
        return (f"Disable module {entry.entry_id} in Modules, or offline: "
                f"module_recovery disable module {entry.entry_id} ({OFFLINE_HELP})")
    if entry.entry_id and entry.kind == "extension":
        return (f"Disable extension {entry.entry_id} in Modules, or offline: "
                f"module_recovery disable extension {entry.entry_id} ({OFFLINE_HELP})")
    return ("Move the unreadable manifest aside offline: module_recovery "
            f"park-manifest {entry.kind} {entry.manifest_file} ({OFFLINE_HELP})")


_HOME = str(Path.home())


def sanitize_message(text: str, *roots: Path) -> str:
    """Bounded message with local absolute paths replaced by stable labels."""

    value = str(text)
    for root, label in [(item, "<modules>") for item in roots] + [(Path(_HOME), "~")]:
        for spelling in {str(root), str(Path(root).resolve()) if Path(root).exists() else str(root)}:
            if spelling and spelling not in {"/", "."}:
                value = value.replace(spelling, label)
    return value[:2000]


def quarantine_entry(
    kind: str, manifest_file: str, entry_id: str | None, code: str, error: BaseException | str,
    *, roots: tuple[Path, ...] = (), shadows_registered: bool = False,
) -> QuarantinedEntry:
    if isinstance(error, BaseException):
        error_type, message = type(error).__name__, str(error)
    else:
        error_type, message = "ValueError", str(error)
    return QuarantinedEntry(kind, manifest_file, entry_id, code, error_type,
                            sanitize_message(message, *roots), shadows_registered)


# -- negative caches ------------------------------------------------------------
# An import that failed is not executed again in this process for the same
# (manifest path, manifest sha256, sys.path): import side effects run at most
# once.  POST /api/modules/rescan (clear_negative_caches) retries.
_CACHE_GUARD = threading.Lock()
_IMPORT_FAILURES: dict[tuple, tuple[str, str]] = {}
_HOOK_FAILURES: dict[tuple, tuple[str, str]] = {}
_HOOK_QUARANTINE: dict[str, QuarantinedEntry] = {}


def import_cache_key(manifest_path: Path, manifest_bytes: bytes) -> tuple:
    return (str(manifest_path), hashlib.sha256(manifest_bytes).hexdigest(), tuple(sys.path))


def cached_import_failure(key: tuple) -> tuple[str, str] | None:
    with _CACHE_GUARD:
        return _IMPORT_FAILURES.get(key)


def record_import_failure(key: tuple, error_type: str, message: str) -> None:
    with _CACHE_GUARD:
        _IMPORT_FAILURES[key] = (error_type, message)


def cached_hook_failure(key: tuple) -> tuple[str, str] | None:
    with _CACHE_GUARD:
        return _HOOK_FAILURES.get(key)


def record_hook_failure(key: tuple, error_type: str, message: str) -> None:
    with _CACHE_GUARD:
        _HOOK_FAILURES[key] = (error_type, message)


def record_hook_quarantine(extension_id: str, error: ExtensionHookImportError) -> None:
    entry = quarantine_entry(
        "extension", f"extensions/{extension_id}.json", extension_id, "GF_EXTENSION_HOOK_IMPORT",
        str(error), roots=(_modules_root_hint(),),
    )
    with _CACHE_GUARD:
        _HOOK_QUARANTINE[extension_id] = QuarantinedEntry(
            entry.kind, entry.manifest_file, entry.entry_id, entry.code, error.error_type, entry.message,
        )


def hook_quarantine_entries() -> tuple[QuarantinedEntry, ...]:
    with _CACHE_GUARD:
        return tuple(_HOOK_QUARANTINE[key] for key in sorted(_HOOK_QUARANTINE))


def clear_hook_quarantine(extension_id: str, packages: Iterable[str] = ()) -> int:
    """Forget one extension's runtime hook quarantine and failed hook imports.

    Called when that extension is disabled, enabled or installed: the entry
    described code that is no longer the extension's active state, and the
    corrective action it carried ("disable the extension") has been taken.
    ``packages`` are the extension's top-level hook packages.
    """

    names = {str(item) for item in packages}
    with _CACHE_GUARD:
        removed = 1 if _HOOK_QUARANTINE.pop(extension_id, None) is not None else 0
        for key in [key for key in _HOOK_FAILURES if str(key[0]).split(".", 1)[0] in names]:
            del _HOOK_FAILURES[key]
            removed += 1
    return removed


def clear_negative_caches() -> dict[str, int]:
    """Forget failed imports and runtime hook quarantine (rescan)."""

    with _CACHE_GUARD:
        counts = {"imports": len(_IMPORT_FAILURES), "hooks": len(_HOOK_FAILURES),
                  "hook_quarantine": len(_HOOK_QUARANTINE)}
        _IMPORT_FAILURES.clear()
        _HOOK_FAILURES.clear()
        _HOOK_QUARANTINE.clear()
    return counts


def _modules_root_hint() -> Path:
    from .runtime_paths import external_modules_root

    return external_modules_root()


# -- selection blockers -----------------------------------------------------------
def registry_quarantine(registry: object) -> tuple[QuarantinedEntry, ...]:
    return tuple(getattr(registry, "quarantined", ()) or ())


def live_hook_quarantine_entries(registry: object) -> tuple[QuarantinedEntry, ...]:
    """Runtime hook quarantine of extensions the registry still holds.

    An extension that is no longer registered (disabled offline, parked)
    cannot run its hooks, so its old hook failure is not a live reason.
    """

    entries = hook_quarantine_entries()
    extension_manifests = getattr(registry, "extension_manifests", None)
    if not callable(extension_manifests):
        return entries
    registered = extension_manifests()
    return tuple(entry for entry in entries if entry.entry_id in registered)


def all_quarantine_entries(registry: object) -> tuple[QuarantinedEntry, ...]:
    return registry_quarantine(registry) + live_hook_quarantine_entries(registry)


def selection_blockers(
    registry: object, module_ids: Iterable[object] = (), extension_ids: Iterable[object] = (),
) -> tuple[QuarantinedEntry, ...]:
    """Quarantine entries that make a selection unusable.

    A selected ID blocks when it is not registered and appears in a
    non-shadow quarantine entry, or (extensions) when its hooks are in the
    runtime hook quarantine.
    """

    entries = registry_quarantine(registry)
    modules = getattr(registry, "manifests", lambda: {})()
    extensions = getattr(registry, "extension_manifests", lambda: {})()
    hooks = {entry.entry_id: entry for entry in live_hook_quarantine_entries(registry)}
    found: list[QuarantinedEntry] = []
    for module_id in dict.fromkeys(str(item) for item in module_ids):
        if module_id not in modules:
            found.extend(entry for entry in entries
                         if entry.kind == "module" and entry.entry_id == module_id and entry.blocking)
    for extension_id in dict.fromkeys(str(item) for item in extension_ids):
        if extension_id not in extensions:
            found.extend(entry for entry in entries
                         if entry.kind == "extension" and entry.entry_id == extension_id and entry.blocking)
        if extension_id in hooks:
            found.append(hooks[extension_id])
    return tuple(found)


def blocker_error(code: str, blockers: Iterable[QuarantinedEntry]) -> ModuleQuarantinedError:
    entries = tuple(blockers)
    names = ", ".join(f"{entry.kind} {entry.entry_id} ({entry.code})" for entry in entries)
    return ModuleQuarantinedError(
        code,
        "The selection uses quarantined local code: " + names
        + ". Disable or repair it in Modules, then select a working module.",
        entries=entries,
    )


def degraded_reasons(
    registry: object, *, extra: Iterable[str] = (), entries: Iterable[QuarantinedEntry] = (),
) -> list[dict[str, object]]:
    """Grouped ``[{code, count}]`` for /api/health (no ids, no paths).

    ``entries`` are further entries not held by the registry (damaged
    installer records, installation_record_entries).
    """

    counts: dict[str, int] = {}
    for entry in all_quarantine_entries(registry) + tuple(entries):
        counts[entry.code] = counts.get(entry.code, 0) + 1
    for code in extra:
        counts[code] = counts.get(code, 0) + 1
    return [{"code": code, "count": counts[code]} for code in sorted(counts)]


def _with_version(entry: QuarantinedEntry, modules_root: Path | None) -> QuarantinedEntry:
    if entry.version is not None or modules_root is None:
        return entry
    try:
        payload = json.loads((Path(modules_root) / entry.manifest_file).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return entry
    version = payload.get("version") if isinstance(payload, dict) else None
    return replace(entry, version=str(version)) if isinstance(version, (str, int, float)) else entry


def quarantine_report(
    registry: object, *, extra_entries: Iterable[QuarantinedEntry] = (), modules_root: Path | None = None,
) -> dict[str, object]:
    """The quarantine panel's payload; ``modules_root`` lets each entry carry
    the version from its raw manifest (best effort)."""

    extra = tuple(extra_entries)
    entries = tuple(_with_version(entry, modules_root) for entry in all_quarantine_entries(registry) + extra)
    return {
        "schema_version": "value.module-quarantine/v1",
        "status": "degraded" if entries else "ok",
        "entries": [entry.to_dict() for entry in entries],
        "reasons": degraded_reasons(registry, entries=extra),
    }


# -- installer records (P0-2 review) ---------------------------------------------
# execution_archive._source_roots reads every record below installed/ and
# installed-extensions/ (enabled or not) at every run start, so one damaged
# record refuses every run.  The same conditions are reported here, so that
# /api/health turns degraded and the panel names the folder to park.
_INSTALLER_FOLDERS = (("module", "installed"), ("extension", "installed-extensions"))


def installation_record_problem(version_folder: Path, *, folder: str) -> str | None:
    """Why the execution archive would refuse this installer-owned version folder."""

    if version_folder.is_symlink() or not version_folder.is_dir():
        return "not a regular folder"
    record_path = version_folder / "installation.json"
    if record_path.is_symlink():
        return "installation record is a symbolic link"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "installation record is missing"
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return f"installation record is unreadable ({type(exc).__name__})"
    if not isinstance(record, dict):
        return "installation record is not a JSON object"
    if record.get("enabled"):
        source = record.get("source_root")
        if source not in (None, "src"):
            return "enabled installation declares an unsupported source root"
        if source is None and folder == "installed":
            return "enabled module has no installer-owned source"
    return None


def installation_record_entries(modules_root: Path) -> tuple[QuarantinedEntry, ...]:
    """Damaged installer folders as quarantine entries (code GF_MODULE_INSTALL_RECORD_INVALID)."""

    root = Path(modules_root)
    found: list[QuarantinedEntry] = []
    for kind, folder in _INSTALLER_FOLDERS:
        base = root / folder
        if not base.is_dir():
            continue
        try:
            identifiers = sorted(base.iterdir())
        except OSError:
            continue
        for identifier in identifiers:
            if identifier.is_symlink() or not identifier.is_dir():
                found.append(QuarantinedEntry(kind, f"{folder}/{identifier.name}", identifier.name,
                                              INSTALL_RECORD_CODE, "InstallationRecordError",
                                              "not a regular folder"))
                continue
            try:
                versions = sorted(identifier.iterdir())
            except OSError:
                continue
            for version in versions:
                problem = installation_record_problem(version, folder=folder)
                if problem is None:
                    continue
                label = f"{folder}/{identifier.name}/{version.name}"
                found.append(QuarantinedEntry(
                    kind, label if problem == "not a regular folder" else label + "/installation.json",
                    identifier.name, INSTALL_RECORD_CODE, "InstallationRecordError", problem,
                    version=version.name,
                ))
    return tuple(found)


# -- post-write verification (P0-2 S4) ---------------------------------------------
# After a lifecycle write the registry is rebuilt twice: in this process, and
# in a fresh interpreter started exactly like a worker (same isolated argv,
# cwd and inherited environment).  Either one refusing the change makes the
# caller roll the write back byte for byte.  Disabling never needs this.
PROBE_TIMEOUT_SECONDS = 120.0
PROBE_SCHEMA = "value.module-registry-probe/v1"


def quarantine_keys(registry: object) -> frozenset[tuple[str, str]]:
    return frozenset(entry.key() for entry in registry_quarantine(registry))


def _conflict_code(kind: str) -> str:
    return "GF_EXTENSION_REGISTRY_CONFLICT" if kind == "extension" else "GF_MODULE_REGISTRY_CONFLICT"


def _judge(
    *, kind: str, entry_id: str, registered: Iterable[str], quarantined: Iterable[Mapping[str, object]],
    before_keys: frozenset, code: str, layer: str,
) -> None:
    introduced = [row for row in quarantined
                  if (str(row.get("kind")), str(row.get("id") or "file:" + str(row.get("manifest_file"))))
                  not in before_keys]
    if introduced or entry_id not in set(registered):
        detail = "; ".join(
            f"{row.get('kind')} {row.get('id') or row.get('manifest_file')}: {row.get('error_code')} {row.get('message')}"
            for row in introduced
        ) or f"{kind} {entry_id} did not register"
        raise ModuleQuarantinedError(code, f"The {layer} registry check refused the change: {detail}")


def verify_registry_in_process(
    modules_root: Path, *, before_keys: frozenset, kind: str, entry_id: str,
) -> None:
    """First layer: rebuild the registry from disk in this process."""

    from .v2.module_manifest import workspace_registry

    try:
        registry = workspace_registry(modules_root)
    except (Exception, SystemExit) as exc:
        raise ModuleQuarantinedError(_conflict_code(kind), f"The registry could not be rebuilt: {exc}") from exc
    registered = registry.extension_manifests() if kind == "extension" else registry.manifests()
    _judge(kind=kind, entry_id=entry_id, registered=registered,
           quarantined=[entry.to_dict() for entry in registry.quarantined], before_keys=before_keys,
           code=_conflict_code(kind), layer="in-process")


def probe_argv(python: str, prefix: Path, report: Path, modules_root: Path) -> list[str]:
    """The probe starts like a worker (C4): same isolated interpreter flags."""

    from backend.lifecycle.python_argv import isolated_python_argv

    argv = isolated_python_argv(python, prefix)
    if not sys.flags.no_user_site:
        argv.remove("-s")
    return [*argv, "-m", "gridform_core.module_recovery", "verify",
            "--modules-root", str(modules_root), "--report", str(report)]


def _stop_probe(process: subprocess.Popen) -> None:
    """Stop the probe this function started (its own process group) and reap it."""

    try:
        if os.name == "nt":  # pragma: no cover - Windows only
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        process.kill()
        process.wait(timeout=5)


def run_registry_probe(modules_root: Path, *, timeout: float | None = None) -> dict[str, object]:
    """Build the registry in a fresh interpreter; return its report."""

    from backend.lifecycle.python_argv import isolated_environment, new_pycache_prefix
    from .runtime_paths import SOURCE_ROOT

    root = Path(modules_root).resolve()
    work = Path(tempfile.mkdtemp(prefix="value-module-probe-"))
    prefix = new_pycache_prefix(work)
    report = work / "report.json"
    environment = isolated_environment(dict(os.environ), prefix)
    environment["VALUE_DATA_HOME"] = str(root.parent)
    options: dict[str, object] = (
        {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if os.name == "nt"
        else {"start_new_session": True}
    )
    try:
        process = subprocess.Popen(
            probe_argv(sys.executable, prefix, report, root), cwd=SOURCE_ROOT, env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            close_fds=True, **options,
        )
        try:
            output, _ = process.communicate(timeout=PROBE_TIMEOUT_SECONDS if timeout is None else timeout)
        except subprocess.TimeoutExpired:
            _stop_probe(process)
            raise ModuleQuarantinedError(
                "GF_MODULE_PROBE_TIMEOUT",
                "The out-of-process registry check did not finish in time; the change was rolled back.",
            ) from None
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if process.returncode != 0 or not isinstance(payload, dict) or payload.get("schema_version") != PROBE_SCHEMA:
            tail = sanitize_message((output or b"").decode("utf-8", "replace")[-600:], root)
            raise ModuleQuarantinedError(
                "GF_MODULE_PROBE_FAILED",
                f"The out-of-process registry check failed (exit {process.returncode}): {tail}",
            )
        return payload
    finally:
        shutil.rmtree(work, ignore_errors=True)


def verify_registry_out_of_process(
    modules_root: Path, *, before_keys: frozenset, kind: str, entry_id: str, timeout: float | None = None,
) -> dict[str, object]:
    """Second layer: the registry as a newly started worker would build it."""

    payload = run_registry_probe(modules_root, timeout=timeout)
    registered = payload.get("extensions" if kind == "extension" else "modules") or ()
    _judge(kind=kind, entry_id=entry_id, registered=[str(item) for item in registered],  # type: ignore[union-attr]
           quarantined=[row for row in payload.get("quarantined") or () if isinstance(row, Mapping)],  # type: ignore[union-attr]
           before_keys=before_keys, code="GF_MODULE_PROBE_FAILED", layer="out-of-process")
    return payload


def verify_after_write(modules_root: Path, *, before_keys: frozenset, kind: str, entry_id: str) -> None:
    verify_registry_in_process(modules_root, before_keys=before_keys, kind=kind, entry_id=entry_id)
    verify_registry_out_of_process(modules_root, before_keys=before_keys, kind=kind, entry_id=entry_id)


# -- evidence for preflight/provenance (P0-2 S7, X0 external_code_policy) -----------
_BUILTIN_PACKAGES = ("gridform_core.", "gridform_validation.")


def _is_builtin_entry(entry_point: str) -> bool:
    return str(entry_point).startswith(_BUILTIN_PACKAGES)


def external_code_evidence(
    registry: object, module_ids: Iterable[object] = (), extension_ids: Iterable[object] = (),
) -> dict[str, object]:
    """Which local (non built-in) code the registry holds and the Study selects.

    The worker imports every enabled external implementation in process, so
    an external module can affect a run without being selected; X0's
    ``external_code_policy`` reads this record (checks.external_code).
    """

    modules = getattr(registry, "manifests", lambda: {})()
    extensions = getattr(registry, "extension_manifests", lambda: {})()
    external_modules = sorted(key for key, manifest in modules.items()
                              if not _is_builtin_entry(getattr(manifest, "implementation", "")))
    external_extensions = sorted(
        key for key, manifest in extensions.items()
        if any(not _is_builtin_entry(hook.implementation) for hook in getattr(manifest, "hooks", ()))
    )
    selected_modules = sorted({str(item) for item in module_ids} & set(external_modules))
    selected_extensions = sorted({str(item) for item in extension_ids} & set(external_extensions))
    return {
        "schema_version": "value.external-code/v1",
        "enabled_external_modules": external_modules,
        "enabled_external_extensions": external_extensions,
        "selected_external_modules": selected_modules,
        "selected_external_extensions": selected_extensions,
        "external_code_loaded": bool(external_modules or external_extensions),
        "execution_boundary": "in_process_trusted_python",
    }


def quarantine_check(
    registry: object, module_ids: Iterable[object] = (), extension_ids: Iterable[object] = (),
) -> dict[str, object]:
    blockers = selection_blockers(registry, module_ids, extension_ids)
    entries = all_quarantine_entries(registry)
    return {
        "passed": not blockers,
        "status": "degraded" if entries else "ok",
        "blockers": [entry.to_dict() for entry in blockers],
        "entries": [entry.to_dict() for entry in entries],
    }
