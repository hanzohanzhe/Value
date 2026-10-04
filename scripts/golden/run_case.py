"""Run one golden case in this process and print its digest as JSON.

Usage: python -B scripts/golden/run_case.py CASE_ID [--keep-output DIR]

The case is defined in tests/golden/cases.json.  run_project_application is
called directly (no preflight, so the host disk reserve R2-05 does not apply);
callers run each case in its own subprocess because the legacy kernel keeps an
unkeyed process-global weather cache (P7-02).  The run output is written to a
temporary directory and removed afterwards unless --keep-output is given.
"""

from __future__ import annotations

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


def build_project(case: Mapping[str, Any]) -> dict[str, Any]:
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
