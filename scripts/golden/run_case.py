"""Run one golden case in this process and print its digest as JSON.

Usage: python -B scripts/golden/run_case.py CASE_ID [--keep-output DIR]

The case is defined in tests/golden/cases.json and its input is the frozen
project tests/golden/projects/<case>.json.  run_project_application is
called directly (no preflight, so the host disk reserve R2-05 does not apply);
callers run each case in its own subprocess because the legacy kernel keeps an
unkeyed process-global weather cache (P7-02).  The run output is written to a
temporary directory and removed afterwards unless --keep-output is given.
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
import contextlib
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES = ROOT / "tests" / "golden" / "cases.json"
ZONES = ROOT / "tests" / "golden" / "zones.json"


def load_cases(path: Path = CASES) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["cases"]


def _merge(target: dict[str, Any], key: str, values: Mapping[str, Any] | None) -> None:
    if values:
        merged = dict(target.get(key) or {})
        merged.update(values)
        target[key] = merged


PROJECTS = ROOT / "tests" / "golden" / "projects"


def project_path(case: Mapping[str, Any]) -> Path:
    if case.get("project"):
        return ROOT / str(case["project"])
    return PROJECTS / f"{case['id']}.json"


def derived_maturity_acknowledgements(project: Mapping[str, Any], registry: Any = None) -> dict[str, str]:
    """Acknowledgements for the project's experimental modules/extensions at
    their *registered* versions.

    Frozen projects record keys such as
    ``module:value-zonal-redispatch-balancing@3.0.0``.  The user-consent
    meaning of an acknowledgement does not apply to golden fixtures, so the
    keys are re-derived from the registry at run time
    (``frontend_contract.maturity_acknowledgement_requirements``); a planned
    module version bump (VERSION_LEDGER) then cannot break a golden case
    whose snapshot is immutable.  Keys that are still current keep their
    frozen order and value; stale keys are dropped.
    """

    from gridform_core.frontend_contract import EXPERIMENTAL_ACK, maturity_acknowledgement_requirements

    if registry is None:
        from gridform_core.v2.module_manifest import builtin_registry

        registry = builtin_registry()
    required = [
        item["key"]
        for item in maturity_acknowledgement_requirements(
            registry, dict(project.get("modules") or {}), [str(item) for item in project.get("selected_extensions") or ()]
        )
    ]
    frozen = dict(project.get("maturity_acknowledgements") or {})
    derived = {key: value for key, value in frozen.items() if key in required and value == EXPERIMENTAL_ACK}
    for key in required:
        derived.setdefault(key, EXPERIMENTAL_ACK)
    return derived


def derived_solver_contract(project: Mapping[str, Any]) -> Any:
    """The current built-in solver contract for a frozen built-in default.

    Frozen projects record the solver contract of their time (C8:
    ``value.network-solver-contract/v3``).  Executing a historical contract
    is refused (P0-8 S4/S5, ``GF_SOLVER_CONTRACT_UPGRADE_REQUIRED``); a user
    upgrades a Study explicitly, a golden fixture has no user, so a frozen
    contract that was its generation's *built-in default* is replaced by the
    current built-in default at run time, exactly like the maturity keys
    above.  The golden revision that follows records the method change under
    its correction id.  A frozen non-default (custom) contract is never
    rewritten and fails as it would for a user.
    """

    from gridform_core.zonal_solver_contract import (
        DEFAULT_ZONAL_SOLVER_SETTINGS,
        solver_contract_generation,
    )

    contract = project.get("solver_contract")
    if not isinstance(contract, Mapping):
        return contract
    if solver_contract_generation(contract) in {"v4", "unknown"}:
        return contract
    if contract.get("is_builtin_default") is not True:
        return contract
    return DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()


def build_project(case: Mapping[str, Any], registry: Any = None) -> dict[str, Any]:
    """The frozen project of a golden case plus its overrides.

    The input is ``tests/golden/projects/<case>.json`` (the 35aadb3 course
    template with the case overrides already applied), never the live
    ``value_101_study()`` template, so later template edits cannot change the
    doctoral inputs.  ``modules``/``parameters``/``runtime_options`` from
    cases.json are merged on top (a no-op for the values already frozen); this
    is how X0 S8 pins ``methodology.profile`` for the D cases.  Maturity
    acknowledgements are re-derived for the registered module versions
    (:func:`derived_maturity_acknowledgements`).
    """

    path = project_path(case)
    if not path.is_file():
        raise SystemExit(f"golden case {case['id']}: frozen project {path.relative_to(ROOT)} is missing (capture.py freeze-projects)")
    project = json.loads(path.read_text(encoding="utf-8"))
    _merge(project, "modules", case.get("modules"))
    _merge(project, "parameters", case.get("parameters"))
    _merge(project, "runtime_options", case.get("runtime_options"))
    project["maturity_acknowledgements"] = derived_maturity_acknowledgements(project, registry)
    if "solver_contract" in project:
        project["solver_contract"] = derived_solver_contract(project)
    project["id"] = "golden-study"
    return project


def resolve_from_template(case: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve a *new* case from the live course template (freeze-projects only)."""

    from gridform_core.value_101 import value_101_study
    from gridform_core.value_101_lifecycle import build_value_101_network_pair

    project = value_101_study()
    variant = case.get("network_variant")
    if variant:
        pair, _ = build_value_101_network_pair(project, network_pack_id=str(case["network_pack_id"]))
        project = copy.deepcopy(pair[variant])
    _merge(project, "modules", case.get("modules"))
    _merge(project, "parameters", case.get("parameters"))
    _merge(project, "runtime_options", case.get("runtime_options"))
    # One fixed Study/Run id for every case so cross-case and cross-family
    # comparisons (delta reports) show only scientific differences.
    project["id"] = "golden-study"
    return project


def run_case(case_id: str, keep_output: Path | None = None) -> dict[str, Any]:
    from gridform_core.application import run_project_application
    from gridform_validation.golden import ZoneRules, digest_run

    cases = load_cases()
    if case_id not in cases:
        raise SystemExit(f"unknown golden case {case_id!r}")
    case = dict(cases[case_id], id=case_id)
    project = build_project(case)
    pack_root = (ROOT / case["pack"]).resolve()
    network_pack_root = (ROOT / case["network_pack"]).resolve() if case.get("network_pack") else None
    temporary = Path(tempfile.mkdtemp(prefix=f"value-golden-{case_id}-"))
    output = (keep_output or (temporary / "output")).resolve()
    log = temporary / "run.log"
    try:
        with log.open("w", encoding="utf-8") as handle, contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            run_project_application(
                project,
                run_id="golden-run",
                pack_root=pack_root,
                output_dir=output,
                mode=str(case["mode"]),
                network_pack_root=network_pack_root,
            )
        digest = digest_run(output, ZoneRules.load(ZONES))
        digest["case"] = case_id
        return digest
    except BaseException:
        sys.stderr.write(log.read_text(encoding="utf-8", errors="replace")[-6000:] if log.exists() else "")
        raise
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("case")
    parser.add_argument("--keep-output", type=Path)
    arguments = parser.parse_args()
    digest = run_case(arguments.case, arguments.keep_output)
    sys.stdout.write(json.dumps(digest, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
