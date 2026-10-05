"""Check the methodology catalogue and scan the code against it (X0 S8).

``python -B scripts/check_methodology_catalog.py`` (p0_gate quick step
``methodology_catalog``) fails when:

* ``gridform_core/data/methodology`` does not parse (schema, unique default,
  gated corrections need a trigger_fixture, correction ids follow the pattern,
  each package edits only its own file);
* the ``methodology.profile`` parameter's default/allowed values differ from
  the catalogue (the catalogue is the single source);
* the reference profile constant is not a frozen profile of the catalogue;
* code asks ``.enabled(<id>)`` for an id the catalogue does not know, or a
  profile_gated correction is never consulted by any code (an unreachable
  switch) - the two-way code/catalogue check of plan X0 S8;
* a profile id literal appears in Python code outside the allow-list (C15: rule
  sets ask ``ResolvedMethodology.enabled``, they never compare profile ids).
"""

from __future__ import annotations

# P0 rule (P0_CONVENTIONS section 2): never write bytecode.
import os as _os
import sys as _sys

_sys.dont_write_bytecode = True
_os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCANNED_TREES = ("gridform_core", "backend", "worker", "scripts")
ENABLED_CALL = re.compile(r"""\.enabled\(\s*["']([^"']+)["']\s*\)""")
# Files that may spell a profile id, with the reason.
PROFILE_LITERAL_ALLOWLIST = {
    "gridform_core/methodology.py": "defines REFERENCE_PROFILE_ID, the one named profile",
    "gridform_core/energy_balance_contract.py": "P0-4 BOUNDARY_REGISTRY keys a rule set by its id; P0-4 S6 derives it from the methodology",
    "scripts/capture_p0_5_baseline.py": "M0 capture script records which profiles a finding is expected under",
    "scripts/check_methodology_catalog.py": "this scanner",
}


def _python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for tree in SCANNED_TREES:
        base = root / tree
        if base.is_dir():
            files.extend(path for path in sorted(base.rglob("*.py")) if "__pycache__" not in path.parts)
    return files


def check(root: Path = ROOT) -> list[str]:
    from gridform_core import methodology
    from gridform_core.parameters import REGISTRY

    errors: list[str] = []
    try:
        catalogue = methodology.load_catalogue_from(root / "gridform_core" / "data" / "methodology")
    except (methodology.MethodologyCatalogError, ValueError, OSError) as exc:
        return [f"catalogue: {exc}"]
    definition = REGISTRY.get(methodology.PROFILE_PARAMETER)
    if definition is None:
        errors.append(f"parameter {methodology.PROFILE_PARAMETER} is not registered")
    else:
        if definition.default != catalogue.default_profile_id:
            errors.append(f"parameter default {definition.default!r} != catalogue default {catalogue.default_profile_id!r}")
        if tuple(definition.allowed_values) != tuple(catalogue.profiles):
            errors.append(f"parameter allowed values {definition.allowed_values} != catalogue profiles {tuple(catalogue.profiles)}")
        if definition.category != "scientific":
            errors.append("methodology.profile must be a scientific parameter")
    reference = catalogue.profiles.get(methodology.REFERENCE_PROFILE_ID)
    if reference is None or not reference.frozen:
        errors.append(f"REFERENCE_PROFILE_ID {methodology.REFERENCE_PROFILE_ID} must be a frozen catalogue profile")

    profile_literal = re.compile(
        r"""["'](""" + "|".join(re.escape(item) for item in catalogue.profiles) + r""")["']"""
    )
    consulted: set[str] = set()
    for path in _python_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in ENABLED_CALL.finditer(text):
            correction_id = match.group(1)
            consulted.add(correction_id)
            if correction_id not in catalogue.corrections:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{relative}:{line}: enabled({correction_id!r}) names no catalogue correction")
        if relative not in PROFILE_LITERAL_ALLOWLIST:
            for match in profile_literal.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{relative}:{line}: profile id literal {match.group(1)!r}; ask ResolvedMethodology.enabled(<correction id>) "
                    "or use methodology.REFERENCE_PROFILE_ID (C15)"
                )
    for correction in catalogue.corrections.values():
        if correction.gated and correction.id not in consulted:
            errors.append(f"profile_gated correction {correction.id} is never consulted by code (.enabled({correction.id!r}))")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    errors = check(ROOT)
    if arguments.json:
        print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
    else:
        for line in errors:
            print(line)
        print("methodology catalogue: " + ("passed" if not errors else f"{len(errors)} error(s)"))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
