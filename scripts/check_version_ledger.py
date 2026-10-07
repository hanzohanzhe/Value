"""Check docs/release/VERSION_LEDGER.json against module manifests and classes.

* every built-in manifest has a ledger entry and vice versa;
* ledger current_version == manifest version == implementation class version;
* bumps form a chain from baseline_version to current_version, each strictly
  increasing, each naming package, correction ids, reason and opt-in flag;
* every correction id is registered (R4 M-低1): a correction of the
  methodology catalogue (gridform_core/data/methodology/corrections/) or a row
  of the "Correction ids" table of CHANGELOG.md, so a misspelt id never
  reaches the method-upgrade confirmation users read.
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
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LEDGER = ROOT / "docs" / "release" / "VERSION_LEDGER.json"
MANIFESTS = ROOT / "gridform_core" / "manifests"
CHANGELOG = ROOT / "CHANGELOG.md"
CORRECTION_ID = re.compile(r"^[a-z0-9]+(\.[a-z0-9-]+)+$")
_BACKTICKED = re.compile(r"`([^`]+)`")


def changelog_correction_ids(path: Path = CHANGELOG) -> set[str]:
    """Correction ids listed in the "Correction ids" sections of CHANGELOG.md."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    found: set[str] = set()
    inside = False
    for line in lines:
        if line.startswith("#"):
            inside = "correction ids" in line.lower()
            continue
        if inside:
            found.update(token for token in _BACKTICKED.findall(line) if CORRECTION_ID.fullmatch(token))
    return found


def registered_correction_ids(*, changelog: Path = CHANGELOG) -> set[str]:
    """Catalogue corrections plus the CHANGELOG "Correction ids" table."""

    from gridform_core.methodology import load_catalogue

    return set(load_catalogue().corrections) | changelog_correction_ids(changelog)


def parse_version(text: str) -> tuple[int, ...]:
    core = str(text).split("-", 1)[0].split("+", 1)[0]
    return tuple(int(part) for part in core.split("."))


def implementation_version(manifest: dict[str, Any]) -> str | None:
    target = str(manifest.get("implementation") or "")
    module_name, _, attribute = target.partition(":")
    if not module_name or not attribute:
        return None
    implementation = getattr(importlib.import_module(module_name), attribute)
    version = getattr(implementation, "version", None)
    return str(version) if version is not None else None


def check(ledger: dict[str, Any], manifests: dict[str, dict[str, Any]], *, import_classes: bool = True,
          registered: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    known = registered_correction_ids() if registered is None else set(registered)
    entries = ledger.get("modules") or {}
    for module_id in sorted(set(manifests) - set(entries)):
        errors.append(f"{module_id}: manifest has no VERSION_LEDGER entry")
    for module_id in sorted(set(entries) - set(manifests)):
        errors.append(f"{module_id}: ledger entry has no built-in manifest")
    for module_id in sorted(set(entries) & set(manifests)):
        entry = entries[module_id]
        manifest = manifests[module_id]
        if entry.get("current_version") != manifest.get("version"):
            errors.append(f"{module_id}: ledger current {entry.get('current_version')} != manifest {manifest.get('version')}")
        if import_classes:
            try:
                class_version = implementation_version(manifest)
            except Exception as exc:  # noqa: BLE001 - report, do not crash the gate
                errors.append(f"{module_id}: implementation import failed: {type(exc).__name__}: {exc}")
                class_version = None
            if class_version is not None and class_version != manifest.get("version"):
                errors.append(f"{module_id}: class version {class_version} != manifest {manifest.get('version')}")
        previous = entry.get("baseline_version")
        for index, bump in enumerate(entry.get("bumps") or []):
            label = f"{module_id} bump {index}"
            for field in ("from", "to", "package", "reason"):
                if not bump.get(field):
                    errors.append(f"{label}: missing {field}")
            if not isinstance(bump.get("correction_ids"), list) or not bump.get("correction_ids"):
                errors.append(f"{label}: needs correction_ids")
            else:
                for correction_id in bump["correction_ids"]:
                    if str(correction_id) not in known:
                        errors.append(
                            f"{label}: correction id {correction_id!r} is not registered (add it to "
                            "gridform_core/data/methodology/corrections/ or to the Correction ids table of CHANGELOG.md)"
                        )
            if not isinstance(bump.get("requires_user_opt_in"), bool):
                errors.append(f"{label}: requires_user_opt_in must be true or false")
            if bump.get("from") != previous:
                errors.append(f"{label}: from {bump.get('from')} does not continue {previous}")
            try:
                if parse_version(bump.get("to", "0")) <= parse_version(bump.get("from", "0")):
                    errors.append(f"{label}: version does not increase")
            except ValueError:
                errors.append(f"{label}: unparseable version")
            previous = bump.get("to")
        if previous != entry.get("current_version"):
            errors.append(f"{module_id}: bump chain ends at {previous}, current is {entry.get('current_version')}")
    return errors


def load_manifests(path: Path = MANIFESTS) -> dict[str, dict[str, Any]]:
    manifests = {}
    for manifest_path in sorted(path.glob("*.json")):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifests[str(payload["id"])] = payload
    return manifests


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-import", action="store_true", help="skip implementation class checks")
    arguments = parser.parse_args(argv)
    errors = check(json.loads(LEDGER.read_text(encoding="utf-8")), load_manifests(), import_classes=not arguments.no_import)
    print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
