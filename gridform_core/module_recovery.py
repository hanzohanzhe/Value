"""Offline self-rescue and registry probe for local modules (P0-2).

    python -m gridform_core.module_recovery list [--json]
    python -m gridform_core.module_recovery disable module|extension <id> [--force]
    python -m gridform_core.module_recovery park-manifest module|extension <file-or-id> [--force]
    python -m gridform_core.module_recovery park-installation module|extension <id> [<version>] [--force]
    python -m gridform_core.module_recovery verify [--report FILE]

On an installed VALUE run it with the bundled interpreter, ``-B -s``,
``PYTHONPATH=<prefix>/app`` and ``--modules-root <prefix>/state/modules``
(USER_GUIDE, "Offline module recovery").

``list``, ``disable``, ``park-manifest`` and ``park-installation`` read and
write the installer's files only: they never import a module
implementation, an extension hook or the module catalogue, so they work
when the local code is what breaks VALUE.  ``disable`` does exactly what the
Modules page does (the current installation record says ``enabled: false``,
the active manifest leaves the scanned folder).  ``park-manifest`` moves an
active manifest that cannot be disabled normally (unreadable, no
installation record) to ``modules/disabled-manifests/{modules,extensions}/``.
``park-installation`` moves a whole installer folder
``installed[-extensions]/<id>/<version>/`` whose record is damaged (every
damaged version when no version is given) to
``modules/disabled-manifests/installed[-extensions]/<id>/``, together with
the active manifest when no enabled version is left.  VALUE never scans
``disabled-manifests/`` (registry, source activation, execution archive).
All of them refuse while a VALUE backend holds the data directory (use the
Modules page then) unless ``--force``.

``verify`` builds the workspace registry exactly as a newly started worker
would and writes a JSON report (registered IDs and quarantined entries).  It
is the out-of-process layer of the post-write check after every install or
enable; run by hand it imports the installed code in this process.

Exit codes: 0 success, 1 nothing to change or not found, 2 usage, 3 a
VALUE backend is running on this data directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .module_quarantine import PROBE_SCHEMA, installation_record_problem
from .runtime_paths import external_modules_root

MODULE_RECORD_SCHEMA = "value.module-installation/v1"
EXTENSION_MANIFEST = "force-extension.json"
PARKED = "disabled-manifests"
INSTALLER_FOLDER = {"module": "installed", "extension": "installed-extensions"}
EXIT_OK, EXIT_NOTHING, EXIT_USAGE, EXIT_RUNNING = 0, 1, 2, 3


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read(path: Path) -> tuple[object, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"unreadable ({type(exc).__name__})"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".recovery.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _backend_running(modules_root: Path) -> bool:
    from backend.lifecycle.file_locks import LOCK_HELD, probe_lock

    return probe_lock(modules_root.parent / ".backend.lock") == LOCK_HELD


# -- list ----------------------------------------------------------------------
def inventory(modules_root: Path) -> dict[str, object]:
    """Everything the installer owns, from raw JSON, with detectable problems.

    Import failures are not detectable without importing: ``verify`` does that.
    """

    root = modules_root
    rows: list[dict[str, object]] = []
    active_modules: dict[str, list[str]] = {}
    for path in sorted(root.glob("*.json")):
        payload, error = _read(path)
        entry_id = payload.get("id") if isinstance(payload, dict) else None
        if entry_id:
            active_modules.setdefault(str(entry_id), []).append(path.name)
        rows.append({"kind": "module", "source": "active_manifest", "file": _relative(path, root),
                     "id": entry_id, "problems": [f"manifest {error}"] if error else
                     ([] if isinstance(payload, dict) else ["manifest is not a JSON object"])})
    active_extensions: dict[str, list[str]] = {}
    namespaces: dict[str, list[str]] = {}
    for path in sorted((root / "extensions").glob("*.json")):
        payload, error = _read(path)
        entry_id = payload.get("id") if isinstance(payload, dict) else None
        if entry_id:
            active_extensions.setdefault(str(entry_id), []).append(path.name)
        if isinstance(payload, dict) and payload.get("namespace"):
            namespaces.setdefault(str(payload["namespace"]), []).append(str(entry_id or path.stem))
        rows.append({"kind": "extension", "source": "active_manifest", "file": _relative(path, root),
                     "id": entry_id, "namespace": payload.get("namespace") if isinstance(payload, dict) else None,
                     "problems": [f"manifest {error}"] if error else
                     ([] if isinstance(payload, dict) else ["manifest is not a JSON object"])})
    for kind, folder in (("module", "installed"), ("extension", "installed-extensions")):
        for path in sorted((root / folder).glob("*/*/installation.json")):
            record, error = _read(path)
            problems = [f"installation record {error}"] if error else []
            if not error and not isinstance(record, dict):
                problems.append("installation record is not a JSON object")
            record = record if isinstance(record, dict) else {}
            if record.get("source_root") == "src" and not (path.parent / "src").is_dir():
                problems.append("installer-owned source folder is missing")
            rows.append({
                "kind": kind, "source": "installation_record", "file": _relative(path, root),
                "id": record.get("module_id" if kind == "module" else "extension_id") or path.parent.parent.name,
                "version": record.get("module_version" if kind == "module" else "version") or path.parent.name,
                "enabled": record.get("enabled"), "problems": problems,
            })
        # Version folders without any record (or not folders at all) refuse
        # every run start as well (execution archive).
        for identifier in sorted((root / folder).glob("*")):
            versions = sorted(identifier.iterdir()) if identifier.is_dir() and not identifier.is_symlink() else [identifier]
            for version in versions:
                if (version / "installation.json").exists() and version.is_dir() and not version.is_symlink():
                    continue
                problem = installation_record_problem(version, folder=folder)
                if problem:
                    rows.append({"kind": kind, "source": "installation_record", "file": _relative(version, root),
                                 "id": identifier.name, "version": version.name if version != identifier else None,
                                 "enabled": None, "problems": [problem]})
    for row in rows:
        if row["source"] == "installation_record" and row["problems"]:
            row["fix"] = " ".join(str(item) for item in (
                "park-installation", row["kind"], row["id"], row.get("version") or "") if item)
    for row in rows:
        if row["source"] != "active_manifest" or not row.get("id"):
            continue
        same = (active_modules if row["kind"] == "module" else active_extensions).get(str(row["id"]), [])
        if len(same) > 1:
            row["problems"].append("ID declared by several active manifests: " + ", ".join(same))
        if row["kind"] == "extension" and row.get("namespace") and len(namespaces[str(row["namespace"])]) > 1:
            row["problems"].append("namespace shared with " + ", ".join(
                item for item in namespaces[str(row["namespace"])] if item != row["id"]))
    parked = sorted(_relative(path, root) for path in (root / PARKED).glob("*/*.json"))
    parked += sorted(_relative(path, root) for folder in INSTALLER_FOLDER.values()
                     for path in (root / PARKED / folder).glob("*/*"))
    return {
        "schema_version": "value.module-recovery-inventory/v1",
        "modules_root": str(root),
        "entries": rows,
        "parked_manifests": parked,
        "problems": sum(len(row["problems"]) for row in rows),
        "note": "Import failures are only visible to 'verify', which imports the installed code.",
    }


def command_list(root: Path, as_json: bool) -> int:
    report = inventory(root)
    if as_json:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return EXIT_OK
    print(f"Local modules in {root}")
    for row in report["entries"]:
        state = "" if row.get("enabled") is None else ("enabled " if row["enabled"] else "disabled ")
        version = f" {row['version']}" if row.get("version") else ""
        print(f"  {row['kind']:9} {state}{row.get('id') or '?'}{version}  [{row['file']}]")
        for problem in row["problems"]:
            print(f"      problem: {problem}")
        if row.get("fix"):
            print(f"      fix:     {row['fix']}")
    for name in report["parked_manifests"]:
        print(f"  parked    {name}")
    if not report["entries"]:
        print("  (none)")
    print(report["note"])
    return EXIT_OK


# -- disable -------------------------------------------------------------------
def _version_key(value: object) -> tuple[int, int, int]:
    """extension_bundle._semver_tuple without importing it (1.10.0 > 1.9.0);
    an unparsable version sorts first instead of raising."""

    core = str(value).split("-", 1)[0]
    try:
        major, minor, patch = core.split(".")
        return int(major), int(minor), int(patch)
    except (TypeError, ValueError):
        return (-1, -1, -1)


def disable(root: Path, kind: str, entry_id: str) -> dict[str, object]:
    """Disable like the Modules page, from raw JSON only; returns what changed.

    Extensions: as ``set_extension_enabled``, only the current record (the
    highest semantic version) is changed and its retained manifest is kept in
    ``disabled-extensions/``.  Modules have one record per ID (Q6).
    """

    changed: list[str] = []
    folder = "installed" if kind == "module" else "installed-extensions"
    key = "module_id" if kind == "module" else "extension_id"
    records = []
    for path in sorted((root / folder / entry_id).glob("*/installation.json")):
        record, error = _read(path)
        if error or not isinstance(record, dict):
            raise ValueError(
                f"{_relative(path, root)} is {error or 'not a JSON object'}; move the whole installation "
                f"aside with: park-installation {kind} {entry_id} {path.parent.name}"
            )
        if record.get(key, entry_id) != entry_id:
            continue
        records.append((path, record))
    active = root / f"{entry_id}.json" if kind == "module" else root / "extensions" / f"{entry_id}.json"
    if not records:
        raise LookupError(f"No installed {kind} {entry_id} under {root}")
    if kind == "extension":
        records = [max(records, key=lambda item: _version_key(item[1].get("version") or item[0].parent.name))]
    for path, record in records:
        if record.get("enabled"):
            record["enabled"] = False
            record["updated_at" if kind == "module" else "state_changed_at"] = _now()
            record["disabled_by"] = "module_recovery"
            _write_json(path, record)
            changed.append(_relative(path, root))
    if active.exists():
        if kind == "extension":
            # Same layout as the Modules page: the manifest is kept beside the
            # disabled-extensions list, never in the scanned folder.
            retained = records[0][0].parent / EXTENSION_MANIFEST
            source = retained if retained.is_file() else active
            target = root / "disabled-extensions" / f"{entry_id}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            changed.append(_relative(target, root))
        active.unlink()
        changed.append(_relative(active, root) + " (removed)")
    return {"kind": kind, "id": entry_id, "changed": changed}


def park_manifest(root: Path, kind: str, name: str) -> dict[str, object]:
    folder = root if kind == "module" else root / "extensions"
    candidate = Path(name).name
    if not candidate.endswith(".json"):
        candidate += ".json"
    source = folder / candidate
    if not source.is_file():
        raise LookupError(f"No active {kind} manifest {candidate} under {_relative(folder, root) or '.'}")
    target_folder = root / PARKED / ("modules" if kind == "module" else "extensions")
    target_folder.mkdir(parents=True, exist_ok=True)
    target = _free_target(target_folder, source.stem, ".json")
    source.replace(target)
    return {"kind": kind, "parked": _relative(target, root), "from": _relative(source, root)}


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _free_target(folder: Path, stem: str, suffix: str = "") -> Path:
    stamp = _stamp()
    target = folder / f"{stem}.{stamp}{suffix}"
    counter = 1
    while target.exists():
        counter += 1
        target = folder / f"{stem}.{stamp}-{counter}{suffix}"
    return target


def _enabled_readable_versions(folder: Path) -> list[str]:
    enabled = []
    for path in sorted(folder.glob("*/installation.json")):
        record, error = _read(path)
        if not error and isinstance(record, dict) and record.get("enabled"):
            enabled.append(path.parent.name)
    return enabled


def park_installation(root: Path, kind: str, entry_id: str, version: str | None = None) -> dict[str, object]:
    """Move damaged installer folders out of every scanned location.

    With ``version`` that folder is moved whatever its state; without it every
    version folder whose record the execution archive would refuse is moved.
    The active manifest follows when no enabled, readable version is left
    (otherwise the registry would quarantine a manifest without source).
    """

    folder_name = INSTALLER_FOLDER[kind]
    identifier = root / folder_name / Path(entry_id).name
    if not identifier.exists() and not identifier.is_symlink():
        raise LookupError(f"No installed {kind} {entry_id} under {folder_name}/")
    destination = root / PARKED / folder_name / Path(entry_id).name
    moved: list[str] = []
    if identifier.is_symlink() or not identifier.is_dir():
        candidates = [identifier]
        destination = root / PARKED / folder_name
    elif version is not None:
        candidate = identifier / Path(version).name
        if not candidate.exists() and not candidate.is_symlink():
            raise LookupError(f"No version {version} of {kind} {entry_id} under {folder_name}/{entry_id}/")
        candidates = [candidate]
    else:
        candidates = [item for item in sorted(identifier.iterdir())
                      if installation_record_problem(item, folder=folder_name)]
        if not candidates:
            raise ValueError(
                f"No damaged installation of {kind} {entry_id}; name the version to park a readable one, "
                f"or use: disable {kind} {entry_id}"
            )
    destination.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        target = _free_target(destination, candidate.name)
        candidate.replace(target)
        moved.append(f"{_relative(candidate, root)} -> {_relative(target, root)}")
    if identifier.is_dir() and not identifier.is_symlink() and not any(identifier.iterdir()):
        identifier.rmdir()
    result: dict[str, object] = {"kind": kind, "id": entry_id, "parked": moved}
    active = root / f"{entry_id}.json" if kind == "module" else root / "extensions" / f"{entry_id}.json"
    remaining = _enabled_readable_versions(identifier) if identifier.is_dir() else []
    if active.is_file() and not remaining:
        result["active_manifest"] = park_manifest(root, kind, active.name)["parked"]
    return result


def _guarded(root: Path, force: bool) -> int | None:
    if not force and _backend_running(root):
        print("VALUE is running on this data directory: use the Modules page, or stop VALUE first "
              "(--force overrides).", file=sys.stderr)
        return EXIT_RUNNING
    return None


def command_disable(root: Path, kind: str, entry_id: str, force: bool) -> int:
    refused = _guarded(root, force)
    if refused is not None:
        return refused
    try:
        result = disable(root, kind, entry_id)
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NOTHING
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NOTHING
    print(json.dumps(result, indent=2))
    return EXIT_OK if result["changed"] else EXIT_NOTHING


def command_park_installation(root: Path, kind: str, entry_id: str, version: str | None, force: bool) -> int:
    refused = _guarded(root, force)
    if refused is not None:
        return refused
    try:
        result = park_installation(root, kind, entry_id, version)
    except (LookupError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NOTHING
    print(json.dumps(result, indent=2))
    return EXIT_OK


def command_park(root: Path, kind: str, name: str, force: bool) -> int:
    refused = _guarded(root, force)
    if refused is not None:
        return refused
    try:
        result = park_manifest(root, kind, name)
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NOTHING
    print(json.dumps(result, indent=2))
    return EXIT_OK


# -- verify ----------------------------------------------------------------------
def _write_report(payload: dict[str, object], report: Path | None) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if report is None:
        sys.stdout.write(text)
        return
    temporary = report.with_name(report.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(report)


def command_verify(modules_root: Path, report: Path | None) -> int:
    from .v2.module_manifest import workspace_registry

    registry = workspace_registry(modules_root)
    _write_report({
        "schema_version": PROBE_SCHEMA,
        "modules_root": "<modules>",
        "modules": list(registry.manifests()),
        "extensions": list(registry.extension_manifests()),
        "quarantined": [entry.to_dict() for entry in registry.quarantined],
    }, report)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m gridform_core.module_recovery",
        description="Inspect and repair locally installed VALUE modules without starting VALUE.",
    )
    parser.add_argument("--modules-root", type=Path, default=None,
                        help="modules directory (default: $VALUE_DATA_HOME/modules)")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list installed modules/extensions and visible problems")
    listing.add_argument("--json", action="store_true")
    for name, help_text in (("disable", "disable an installed module or extension"),
                            ("park-manifest", "move an active manifest out of the scanned folder")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("kind", choices=("module", "extension"))
        command.add_argument("target", help="module/extension ID (park-manifest: manifest file name or ID)")
        command.add_argument("--force", action="store_true", help="act even while VALUE is running")
    parking = commands.add_parser(
        "park-installation", help="move a damaged installer folder out of every scanned location")
    parking.add_argument("kind", choices=("module", "extension"))
    parking.add_argument("target", help="module/extension ID")
    parking.add_argument("version", nargs="?", default=None,
                         help="version folder to park (default: every version whose record is damaged)")
    parking.add_argument("--force", action="store_true", help="act even while VALUE is running")
    verify = commands.add_parser("verify", help="build the registry as a new worker would and report it")
    verify.add_argument("--modules-root", type=Path, default=None, dest="sub_modules_root")
    verify.add_argument("--report", type=Path, default=None, help="write the JSON report to this file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    root = getattr(arguments, "sub_modules_root", None) or arguments.modules_root or external_modules_root()
    root = Path(root).expanduser().resolve()
    if arguments.command == "list":
        return command_list(root, arguments.json)
    if arguments.command == "disable":
        return command_disable(root, arguments.kind, arguments.target, arguments.force)
    if arguments.command == "park-manifest":
        return command_park(root, arguments.kind, arguments.target, arguments.force)
    if arguments.command == "park-installation":
        return command_park_installation(root, arguments.kind, arguments.target, arguments.version, arguments.force)
    if arguments.command == "verify":
        return command_verify(root, arguments.report)
    return EXIT_USAGE  # pragma: no cover - argparse rejects unknown commands


if __name__ == "__main__":
    raise SystemExit(main())
