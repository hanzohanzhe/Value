"""Capture, check and revise the two golden families.

Commands::

    capture.py check    [--tier fast|full|nightly] [--cases D1 C1 ...] [--mode exact|tolerance]
    capture.py init     --cases ...                      # write revision 0 (refuses to overwrite)
    capture.py revise   --cases ... --reason TEXT [--correction-id ID ...] [--finding ID ...]
    capture.py validate                                  # bookkeeping only, no model runs
    capture.py dump     --cases ... --out-dir DIR        # raw digests for inspection

Each case runs in its own hermetic subprocess (scripts/golden/run_case.py).
``check`` exits 1 when any case differs from its latest revision in a
trajectory or accounting column; identity-zone differences (code and module
identity hashes, versions) are reported only.  ``revise`` appends a revision
carrying the delta; for the doctoral family a trajectory change is accepted
only for a finding listed in tests/golden/doctoral_trajectory_rebaselines.json
and only once per finding and case.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_validation import golden as golden_lib  # noqa: E402

GOLDEN_DIR = ROOT / "tests" / "golden"
CASES = GOLDEN_DIR / "cases.json"
TRAJECTORY_ALLOWLIST = GOLDEN_DIR / "doctoral_trajectory_rebaselines.json"
TIER_ORDER = {"fast": 0, "full": 1, "nightly": 2}
GATED_ZONES = ("trajectory", "accounting")


def _runner_module():
    spec = importlib.util.spec_from_file_location("run_backend_tests", ROOT / "scripts" / "run_backend_tests.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_cases() -> dict[str, dict[str, Any]]:
    return json.loads(CASES.read_text(encoding="utf-8"))["cases"]


def golden_path(family: str, case_id: str) -> Path:
    return GOLDEN_DIR / family / f"{case_id}.json"


def select_cases(cases: dict[str, dict[str, Any]], tier: str | None, names: Sequence[str] | None) -> list[str]:
    if names:
        unknown = sorted(set(names) - set(cases))
        if unknown:
            raise SystemExit(f"unknown golden case(s): {', '.join(unknown)}")
        return list(names)
    limit = TIER_ORDER[tier or "fast"]
    return sorted(name for name, case in cases.items() if TIER_ORDER[case["tier"]] <= limit)


def run_case_subprocess(case_id: str, python: str = sys.executable, timeout: float = 3600) -> dict[str, Any]:
    runner = _runner_module()
    scratch = Path(tempfile.mkdtemp(prefix=f"value-golden-{case_id}-"))
    started = time.monotonic()
    try:
        environment = runner.hermetic_environment(scratch)
        completed = subprocess.run(
            [python, "-B", str(ROOT / "scripts" / "golden" / "run_case.py"), case_id],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"golden case {case_id} failed (exit {completed.returncode}):\n{completed.stderr[-4000:]}")
        digest = json.loads(completed.stdout.strip().splitlines()[-1])
        digest["seconds"] = round(time.monotonic() - started, 2)
        return digest
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def run_cases(case_ids: Sequence[str], jobs: int | None = None, python: str = sys.executable) -> dict[str, dict[str, Any]]:
    jobs = jobs or min(8, max(1, os.cpu_count() or 1))
    results: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run_case_subprocess, case_id, python): case_id for case_id in case_ids}
        for future in concurrent.futures.as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _strip_runtime(digest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in digest.items() if key not in {"seconds", "case"}}


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def command_check(arguments: argparse.Namespace) -> int:
    cases = load_cases()
    selected = select_cases(cases, arguments.tier, arguments.cases)
    mode = arguments.mode or golden_lib.default_mode()
    digests = run_cases(selected, arguments.jobs)
    report: dict[str, Any] = {"schema_version": "value.golden-check/v1", "mode": mode, "cases": {}, "errors": []}
    for case_id in selected:
        family = cases[case_id]["family"]
        path = golden_path(family, case_id)
        if not path.is_file():
            report["errors"].append(f"{family}/{case_id}: no golden file (run capture.py init)")
            continue
        golden = json.loads(path.read_text(encoding="utf-8"))
        differences = golden_lib.compare_digests(golden_lib.latest_digest(golden), digests[case_id], mode)
        gated = [row for row in differences if row.zone in GATED_ZONES]
        report["cases"][case_id] = {
            "family": family,
            "seconds": digests[case_id].get("seconds"),
            "revision": golden["revisions"][-1]["revision"],
            "gated_differences": [row.to_dict() for row in gated],
            "identity_differences": len(differences) - len(gated),
        }
        if gated:
            report["errors"].append(
                f"{family}/{case_id}: {len(gated)} trajectory/accounting column(s) differ from revision "
                f"{golden['revisions'][-1]['revision']} (append a revision with capture.py revise)"
            )
    report["passed"] = not report["errors"]
    _emit(report, arguments.json_output)
    return 0 if report["passed"] else 1


def command_init(arguments: argparse.Namespace) -> int:
    cases = load_cases()
    selected = select_cases(cases, arguments.tier, arguments.cases)
    existing = [case_id for case_id in selected if golden_path(cases[case_id]["family"], case_id).exists()]
    if existing and not arguments.force_reinit:
        raise SystemExit(f"golden file(s) already exist: {', '.join(existing)}")
    first = run_cases(selected, arguments.jobs)
    second = run_cases(selected, arguments.jobs) if arguments.twice else first
    head = _git_head()
    for case_id in selected:
        differences = golden_lib.compare_digests(first[case_id], second[case_id], "exact")
        if differences:
            raise SystemExit(f"{case_id}: two captures differ: {[row.key for row in differences][:10]}")
        family = cases[case_id]["family"]
        golden = golden_lib.new_golden(family, case_id, _strip_runtime(first[case_id]), head, arguments.reason)
        golden_lib.write_golden(golden_path(family, case_id), golden)
    print(json.dumps({case_id: first[case_id].get("seconds") for case_id in selected}, indent=2))
    return 0


def command_revise(arguments: argparse.Namespace) -> int:
    cases = load_cases()
    selected = select_cases(cases, arguments.tier, arguments.cases)
    digests = run_cases(selected, arguments.jobs)
    allowlist = json.loads(TRAJECTORY_ALLOWLIST.read_text(encoding="utf-8"))
    head = _git_head()
    summary = {}
    for case_id in selected:
        family = cases[case_id]["family"]
        path = golden_path(family, case_id)
        golden = json.loads(path.read_text(encoding="utf-8"))
        try:
            revision = golden_lib.append_revision(
                golden,
                _strip_runtime(digests[case_id]),
                base_commit=head,
                reason=arguments.reason,
                correction_ids=arguments.correction_id or [],
                findings=arguments.finding or [],
            )
        except ValueError as exc:
            summary[case_id] = str(exc)
            continue
        errors = golden_lib.validate_golden_file(golden, allowlist)
        if errors:
            raise SystemExit("refusing revision:\n" + "\n".join(errors))
        golden_lib.write_golden(path, golden)
        summary[case_id] = revision["delta"]["by_zone"]
    print(json.dumps(summary, indent=2))
    return 0


def validate_all() -> list[str]:
    allowlist = json.loads(TRAJECTORY_ALLOWLIST.read_text(encoding="utf-8"))
    cases = load_cases()
    errors: list[str] = []
    for case_id, case in cases.items():
        path = golden_path(case["family"], case_id)
        if not path.is_file():
            errors.append(f"{case['family']}/{case_id}: golden file missing")
            continue
        golden = json.loads(path.read_text(encoding="utf-8"))
        if golden.get("case") != case_id or golden.get("family") != case["family"]:
            errors.append(f"{path.relative_to(ROOT)}: case/family header mismatch")
        errors.extend(golden_lib.validate_golden_file(golden, allowlist))
    for family in ("doctoral", "corrected"):
        for path in sorted((GOLDEN_DIR / family).glob("*.json")):
            if path.stem not in cases:
                errors.append(f"{path.relative_to(ROOT)}: no case definition")
    return errors


def command_validate(arguments: argparse.Namespace) -> int:
    errors = validate_all()
    _emit({"schema_version": "value.golden-validate/v1", "errors": errors, "passed": not errors}, arguments.json_output)
    return 0 if not errors else 1


def command_dump(arguments: argparse.Namespace) -> int:
    cases = load_cases()
    selected = select_cases(cases, arguments.tier, arguments.cases)
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    for case_id, digest in run_cases(selected, arguments.jobs).items():
        (arguments.out_dir / f"{case_id}.json").write_text(json.dumps(digest, indent=1, sort_keys=True), encoding="utf-8")
    return 0


def _emit(report: dict[str, Any], destination: Path | None) -> None:
    text = json.dumps(report, indent=2)
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text + "\n", encoding="utf-8")
    print(text)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "init", "revise", "validate", "dump"):
        command = sub.add_parser(name)
        command.add_argument("--json-output", type=Path)
        if name == "validate":
            continue
        command.add_argument("--cases", nargs="*")
        command.add_argument("--tier", choices=sorted(TIER_ORDER), default=None)
        command.add_argument("--jobs", type=int, default=None)
        if name == "check":
            command.add_argument("--mode", choices=("exact", "tolerance"))
        if name == "init":
            command.add_argument("--reason", default="revision 0: behaviour of the model code at 35aadb3")
            command.add_argument("--twice", action="store_true", help="capture twice and require identical digests")
            command.add_argument("--force-reinit", action="store_true", help=argparse.SUPPRESS)
        if name == "revise":
            command.add_argument("--reason", required=True)
            command.add_argument("--correction-id", action="append")
            command.add_argument("--finding", action="append")
        if name == "dump":
            command.add_argument("--out-dir", type=Path, required=True)
    arguments = parser.parse_args(argv)
    handler = {
        "check": command_check,
        "init": command_init,
        "revise": command_revise,
        "validate": command_validate,
        "dump": command_dump,
    }[arguments.command]
    return handler(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
