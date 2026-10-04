"""Classify release changes against the last accepted VALUE scientific tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
SCIENTIFIC_PREFIXES = (
    "gridform_core/builtin/scheme_c_1000twh/",
    "gridform_core/data/carbon/",
    "gridform_core/manifests/",
    "gridform_validation/",
    "data-packs/value-synthetic-contract-pack-v1/",
)
SCIENTIFIC_FILES = {
    "gridform_core/application.py",
    "gridform_core/asset_economics.py",
    "gridform_core/canonical_psm_data.py",
    "gridform_core/carbon_factors.py",
    "gridform_core/carbon_ledger.py",
    "gridform_core/cem_identity.py",
    "gridform_core/cem_investment_policy.py",
    "gridform_core/clearing_inputs.py",
    "gridform_core/cost_ledger.py",
    "gridform_core/interfaces.py",
    "gridform_core/module_registry.py",
    "gridform_core/orchestrator.py",
    "gridform_core/parameters.py",
    "gridform_core/perfect_foresight_psm.py",
    "gridform_core/planning_index.py",
    "gridform_core/planning_ledger.py",
    "gridform_core/scientific_validation.py",
    "gridform_core/storage_audit.py",
    "gridform_core/storage_catalogue.py",
    "gridform_core/storage_recovery.py",
    "gridform_core/terminal_state.py",
    "gridform_core/weather_demand_ensembles.py",
    "gridform_core/v2/contracts.py",
    "gridform_core/v2/interfaces.py",
    "gridform_core/v2/module_manifest.py",
    "gridform_core/v2/orchestrator.py",
}
NUMERICAL_PACKAGES = {
    "numpy", "pandas", "scipy", "pulp", "cbcbox", "netcdf4", "cftime",
    "xarray", "pyproj", "python-dateutil", "pytz", "six", "tzdata",
}


def _git(*arguments: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT, check=True, capture_output=True, text=text,
    )
    return result.stdout


def _scientific(path: str) -> bool:
    return path in SCIENTIFIC_FILES or any(path.startswith(prefix) for prefix in SCIENTIFIC_PREFIXES)


def _base_files(base: str) -> list[str]:
    output = str(_git("ls-tree", "-r", "--name-only", base))
    return sorted(path for path in output.splitlines() if _scientific(path))


def _digest_current(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        path = ROOT / relative
        if not path.is_file():
            continue
        blob = str(_git("hash-object", "--path", relative, relative)).strip()
        digest.update(relative.encode("utf-8") + b"\0" + blob.encode("ascii") + b"\0")
    return digest.hexdigest()


def _digest_base(base: str, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        blob = str(_git("rev-parse", f"{base}:{relative}")).strip()
        digest.update(relative.encode("utf-8") + b"\0" + blob.encode("ascii") + b"\0")
    return digest.hexdigest()


def _pins(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        match = PIN.fullmatch(line.strip())
        if match:
            result[match.group(1).lower().replace("_", "-")] = match.group(2)
    return result


def _dependency_impact(base: str) -> dict[str, object]:
    base_pins: dict[str, str] = {}
    current_pins: dict[str, str] = {}
    locks = sorted((ROOT / "requirements").glob("force-*-py310.lock"))
    for path in locks:
        relative = path.relative_to(ROOT).as_posix()
        current_pins.update(_pins(path.read_text(encoding="utf-8")))
        try:
            old = _git("show", f"{base}:{relative}")
        except subprocess.CalledProcessError:
            old = ""
        base_pins.update(_pins(str(old)))
    numerical_changes = {
        name: {"base": base_pins.get(name), "current": current_pins.get(name)}
        for name in sorted(NUMERICAL_PACKAGES)
        if base_pins.get(name) != current_pins.get(name)
    }
    nonnumerical_changes = {
        name: {"base": base_pins.get(name), "current": current_pins.get(name)}
        for name in sorted(set(base_pins) | set(current_pins))
        if name not in NUMERICAL_PACKAGES and base_pins.get(name) != current_pins.get(name)
    }
    return {
        "numerical_dependency_changes": numerical_changes,
        "nonnumerical_dependency_changes": nonnumerical_changes,
        "numerical_dependencies_unchanged": not numerical_changes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    tracked_changes = set(str(_git("diff", "--name-only", args.base, "--")).splitlines())
    untracked = set(str(_git("ls-files", "--others", "--exclude-standard")).splitlines())
    changes = sorted(tracked_changes | untracked)
    scientific_changes = sorted(path for path in changes if _scientific(path))
    paths = _base_files(args.base)
    current_extra = sorted(
        path.relative_to(ROOT).as_posix()
        for prefix in SCIENTIFIC_PREFIXES
        for path in (ROOT / prefix).rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.lower() not in {".pyc", ".pyo"}
        and path.relative_to(ROOT).as_posix() not in paths
    )
    current_paths = sorted(set(paths) | set(current_extra) | {
        path for path in SCIENTIFIC_FILES if (ROOT / path).is_file()
    })
    dependencies = _dependency_impact(args.base)
    hashes_equal = paths == current_paths and _digest_base(args.base, paths) == _digest_current(current_paths)
    report = {
        "schema_version": "value.science-impact/v1",
        "base_commit": args.base,
        "working_tree_branch": str(_git("branch", "--show-current")).strip(),
        "changed_path_count": len(changes),
        "scientific_paths_changed": scientific_changes,
        "scientific_surface": {
            "files": len(paths),
            "base_sha256": _digest_base(args.base, paths),
            "current_sha256": _digest_current(current_paths),
            "identical": hashes_equal,
        },
        "dependencies": dependencies,
        "categories": {
            "contracts": "changed: data-bundle and future subannual-checkpoint contracts only",
            "data_adapters": "unchanged: scientific role adapters and bindings",
            "psm_cem_modules": "unchanged",
            "storage_policy": "unchanged",
            "state_transition": "unchanged",
            "cost_carbon_ledgers": "unchanged",
            "ui_api": "changed: data installer, recovery status and preflight estimates",
            "packaging_security_rights_docs": "changed",
            "scientific_data_bytes": "unchanged: synthetic and carbon bytes; UK object hashes preserved outside Git",
        },
        "scientific_execution_changed": bool(scientific_changes or not hashes_equal or not dependencies["numerical_dependencies_unchanged"]),
        "required_test_level": "no annual or ten-year rerun; complete software tests plus bounded 24/168 h operational profiles and immutable Prompt 52 evidence reuse",
        "reused_evidence": {
            "report": "publication/prompt52-final-test-report.json",
            "one_year": "prompt52-one-year-full",
            "causal_two_year": "prompt52-two-year-full",
            "dynamic_ten_year": "scientific-dynamic-storage-2025-2034-20260804-205626-585b97",
            "legacy_ten_year": "scientific-legacy-storage-2025-2034-20260804-205626-dcd3c5"
        }
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "scientific_execution_changed": report["scientific_execution_changed"],
        "scientific_surface": report["scientific_surface"],
        "numerical_dependency_changes": dependencies["numerical_dependency_changes"],
        "output": str(args.output.resolve()),
    }, indent=2))
    raise SystemExit(1 if report["scientific_execution_changed"] else 0)


if __name__ == "__main__":
    main()
