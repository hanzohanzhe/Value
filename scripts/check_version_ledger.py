"""Check docs/release/VERSION_LEDGER.json against module manifests and classes.

* every built-in manifest has a ledger entry and vice versa;
* ledger current_version == manifest version == implementation class version;
* bumps form a chain from baseline_version to current_version, each strictly
  increasing, each naming package, correction ids, reason and opt-in flag.
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
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LEDGER = ROOT / "docs" / "release" / "VERSION_LEDGER.json"
MANIFESTS = ROOT / "gridform_core" / "manifests"


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


def check(ledger: dict[str, Any], manifests: dict[str, dict[str, Any]], *, import_classes: bool = True) -> list[str]:
    errors: list[str] = []
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
