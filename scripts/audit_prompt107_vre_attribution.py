"""Run the fixed Prompt 107 short and independent verification gate."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "value.prompt107-vre-attribution-report/v1"
SHORT_COMMAND_IDS = (
    "focused_scientific_verification",
    "sqlite_fixture_checks",
    "retained_scheme_c_hashes",
    "python_full_suite",
    "frontend_lint",
    "frontend_build",
    "frontend_e2e",
)
_MAXIMUM_RESIDUAL = re.compile(
    r"PROMPT107_MAX_IDENTITY_RESIDUAL_MWH=([-+0-9.eE]+)"
)
_ALLOWED_OPTIONAL_SKIP_MARKERS = (
    "netCDF4 is optional",
    "verified local pack is required",
    "local verified data pack not installed",
    "local verified data pack is required",
    "local UK public pack not assembled",
    "separate UK benchmark asset not installed",
    "runtime guard only applies outside the reference interpreter",
    "VALUE requires Python 3.10",
    "VALUE parity requires Python 3.10",
    "VALUE scientific dependencies are required",
    "VALUE scientific dependencies are not installed",
    "optional VALUE scientific runtime is not installed",
    "Port 8800 is already occupied",
)


@dataclass(frozen=True)
class CommandSpec:
    command_id: str
    argv: tuple[str, ...]
    count_style: str = "none"
    timeout_seconds: int = 1_800


def build_short_command_registry() -> dict[str, CommandSpec]:
    """Return the complete, ordered short-gate command registry."""

    python = sys.executable
    npm = shutil.which("npm") or "npm"
    return {
        "focused_scientific_verification": CommandSpec(
            "focused_scientific_verification",
            (
                python,
                "-m",
                "pytest",
                "tests/test_vre_curtailment_attribution.py",
                "tests/test_prompt99_zonal_redispatch.py",
                "tests/test_prompt103_zonal_validation.py",
                "tests/test_force_actual_random_clearing.py",
                "-q",
                "-s",
                "-rs",
            ),
            "pytest",
        ),
        "sqlite_fixture_checks": CommandSpec(
            "sqlite_fixture_checks",
            (
                python,
                "-m",
                "pytest",
                "tests/test_market_ledger_v6.py",
                "tests/test_prompt102_zonal_results_api.py",
                "-q",
                "-rs",
            ),
            "pytest",
            600,
        ),
        "retained_scheme_c_hashes": CommandSpec(
            "retained_scheme_c_hashes",
            (
                python,
                "-m",
                "pytest",
                "tests/test_retained_source_manifest.py",
                "-q",
                "-rs",
            ),
            "pytest",
            300,
        ),
        "python_full_suite": CommandSpec(
            "python_full_suite",
            (
                python,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
                "-v",
            ),
            "unittest",
            2_400,
        ),
        "frontend_lint": CommandSpec(
            "frontend_lint", (npm, "run", "lint"), timeout_seconds=600
        ),
        "frontend_build": CommandSpec(
            "frontend_build", (npm, "run", "build"), timeout_seconds=900
        ),
        "frontend_e2e": CommandSpec(
            "frontend_e2e",
            (npm, "run", "test:e2e"),
            "playwright",
            1_800,
        ),
    }


def parse_test_counts(output: str, style: str) -> dict[str, int]:
    """Parse only runner summaries; never infer a count from progress glyphs."""

    if style == "pytest":
        counts: dict[str, int] = {}
        for name in ("passed", "failed", "skipped", "xfailed", "xpassed", "errors"):
            pattern = "errors?" if name == "errors" else name
            matches = re.findall(rf"(\d+)\s+{pattern}\b", output)
            if matches:
                counts[name] = int(matches[-1])
        return counts
    if style == "unittest":
        ran = re.findall(r"Ran\s+(\d+)\s+tests?\s+in", output)
        if not ran:
            return {}
        counts = {"run": int(ran[-1])}
        for name in ("failures", "errors", "skipped", "expected failures"):
            matches = re.findall(rf"{re.escape(name)}=(\d+)", output)
            if matches:
                counts[name.replace(" ", "_")] = int(matches[-1])
        counts["passed"] = max(
            counts["run"]
            - counts.get("failures", 0)
            - counts.get("errors", 0)
            - counts.get("skipped", 0)
            - counts.get("expected_failures", 0),
            0,
        )
        return counts
    if style == "playwright":
        counts = {}
        for name in ("passed", "failed", "skipped"):
            matches = re.findall(rf"(\d+)\s+{name}\b", output)
            if matches:
                counts[name] = int(matches[-1])
        return counts
    return {}


def _skip_reasons(output: str) -> list[str]:
    reasons: list[str] = []
    for line in output.splitlines():
        unittest_match = re.search(r"skipped\s+['\"](.+?)['\"]\s*$", line)
        pytest_match = re.search(r"SKIPPED\s+\[[^]]+\]\s+.*?:\s*(.+)$", line)
        match = unittest_match or pytest_match
        if match:
            reasons.append(match.group(1).strip())
    return reasons


def _maximum_identity_residual(output: str) -> float | None:
    values = [float(value) for value in _MAXIMUM_RESIDUAL.findall(output)]
    return max(values) if values else None


def run_registered_command(spec: CommandSpec) -> dict[str, object]:
    """Execute one declared command with no shell and bounded evidence."""

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            list(spec.argv),
            cwd=ROOT,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=spec.timeout_seconds,
        )
        exit_code: int | None = int(completed.returncode)
        output = completed.stdout + completed.stderr
        execution_error = None
    except (OSError, subprocess.TimeoutExpired) as exc:
        exit_code = None
        stdout = getattr(exc, "stdout", "") or ""
        stderr = getattr(exc, "stderr", "") or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output = f"{stdout}{stderr}"
        execution_error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    reasons = _skip_reasons(output)
    unexpected = [
        reason for reason in reasons
        if not any(marker in reason for marker in _ALLOWED_OPTIONAL_SKIP_MARKERS)
    ]
    record: dict[str, object] = {
        "command_id": spec.command_id,
        "argv": list(spec.argv),
        "shell": False,
        "capture_output": True,
        "exit_code": exit_code,
        "elapsed_seconds": round(elapsed, 6),
        "timeout_seconds": spec.timeout_seconds,
        "final_output_lines": output.splitlines()[-40:],
        "parsed_counts": parse_test_counts(output, spec.count_style),
        "optional_skip_reasons": reasons,
        "unexpected_skip_reasons": unexpected,
        "execution_error": execution_error,
    }
    residual = _maximum_identity_residual(output)
    if residual is not None:
        record["maximum_identity_residual_mwh"] = residual
    return record


def build_short_report(
    records: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Build a fail-closed short report from executed command records."""

    registry = build_short_command_registry()
    missing = [command_id for command_id in SHORT_COMMAND_IDS if command_id not in records]
    nonzero = []
    invalid_records: dict[str, list[str]] = {}
    unexpected_skips: dict[str, list[str]] = {}

    def invalidate(command_id: str, reason: str) -> None:
        invalid_records.setdefault(command_id, []).append(reason)

    for command_id in SHORT_COMMAND_IDS:
        if command_id not in records:
            continue
        record = records[command_id]
        spec = registry[command_id]
        if record.get("command_id") != command_id:
            invalidate(command_id, "command_id_mismatch")
        if tuple(record.get("argv", ())) != spec.argv:
            invalidate(command_id, "argv_mismatch")
        if record.get("shell") is not False:
            invalidate(command_id, "shell_must_be_false")
        if record.get("capture_output") is not True:
            invalidate(command_id, "capture_output_must_be_true")
        if record.get("timeout_seconds") != spec.timeout_seconds:
            invalidate(command_id, "timeout_mismatch")
        if record.get("execution_error") is not None:
            invalidate(command_id, "execution_error")
        if record.get("exit_code") != 0:
            nonzero.append(command_id)
        raw_skip_reasons = record.get("optional_skip_reasons", ())
        if not isinstance(raw_skip_reasons, Sequence) or isinstance(raw_skip_reasons, str):
            invalidate(command_id, "skip_reasons_missing")
            raw_skip_reasons = ()
        recomputed_unexpected = [
            str(reason)
            for reason in raw_skip_reasons
            if not any(marker in str(reason) for marker in _ALLOWED_OPTIONAL_SKIP_MARKERS)
        ]
        declared_unexpected = record.get("unexpected_skip_reasons", ())
        if not isinstance(declared_unexpected, Sequence) or isinstance(declared_unexpected, str):
            invalidate(command_id, "unexpected_skip_reasons_malformed")
            declared_unexpected = ()
        combined_unexpected = sorted(
            {str(reason) for reason in (*recomputed_unexpected, *declared_unexpected)}
        )
        if combined_unexpected:
            unexpected_skips[command_id] = combined_unexpected
            invalidate(command_id, "unexpected_skip_reason")
        counts = record.get("parsed_counts")
        if not isinstance(counts, Mapping):
            invalidate(command_id, "parsed_counts_missing")
            counts = {}
        if int(counts.get("failed", 0) or 0) != 0:
            invalidate(command_id, "failed_tests_recorded")
        if int(counts.get("errors", 0) or 0) != 0:
            invalidate(command_id, "test_errors_recorded")

        minimum_passed = {
            "focused_scientific_verification": 47,
            "sqlite_fixture_checks": 17,
            "retained_scheme_c_hashes": 1,
            "frontend_e2e": 25,
        }.get(command_id)
        if minimum_passed is not None and int(counts.get("passed", 0) or 0) < minimum_passed:
            invalidate(command_id, f"passed_below_{minimum_passed}")
        if command_id == "python_full_suite":
            run = int(counts.get("run", 0) or 0)
            passed = int(counts.get("passed", 0) or 0)
            skipped = int(counts.get("skipped", 0) or 0)
            if run < 552:
                invalidate(command_id, "run_below_552")
            if passed <= 0:
                invalidate(command_id, "no_passing_tests")
            if passed + skipped != run:
                invalidate(command_id, "unittest_count_mismatch")
            if len(raw_skip_reasons) != skipped:
                invalidate(command_id, "skip_reason_count_mismatch")
        if command_id == "frontend_build" and not any(
            "Build complete" in str(line)
            for line in record.get("final_output_lines", ())
        ):
            invalidate(command_id, "build_success_marker_missing")
        if command_id == "frontend_e2e" and int(counts.get("skipped", 0) or 0) != 0:
            invalidate(command_id, "playwright_skips_not_allowed")
    focused = records.get("focused_scientific_verification", {})
    residual = focused.get("maximum_identity_residual_mwh")
    residual_valid = (
        isinstance(residual, (int, float))
        and math.isfinite(float(residual))
        and float(residual) >= 0.0
    )
    registry_complete = tuple(records) == SHORT_COMMAND_IDS
    gate_passed = (
        registry_complete
        and not missing
        and not nonzero
        and not invalid_records
        and not unexpected_skips
        and residual_valid
    )
    command_records = [dict(records[command_id]) for command_id in SHORT_COMMAND_IDS if command_id in records]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "short_and_independent_verification",
        "decision": "GO" if gate_passed else "NO-GO",
        "short_gate": {
            "status": "passed" if gate_passed else "failed",
            "required_command_ids": list(SHORT_COMMAND_IDS),
            "registry_complete_and_ordered": registry_complete,
            "missing_command_ids": missing,
            "nonzero_or_unexecuted_command_ids": nonzero,
            "invalid_command_records": invalid_records,
            "unexpected_skip_reasons": unexpected_skips,
        },
        "commands": command_records,
        "parsed_test_counts": {
            record["command_id"]: record.get("parsed_counts", {})
            for record in command_records
        },
        "maximum_identity_residual_mwh": (
            float(residual) if residual_valid else None
        ),
        "retained_scheme_c_hashes_unchanged": (
            records.get("retained_scheme_c_hashes", {}).get("exit_code") == 0
            and "retained_scheme_c_hashes" not in invalid_records
        ),
        "optional_environment_skips": {
            record["command_id"]: record.get("optional_skip_reasons", [])
            for record in command_records
            if record.get("optional_skip_reasons")
        },
        "annual_gate": "not_run_in_short_gate",
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("short",), default="short")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("publication/prompt107-vre-curtailment-attribution-report.json"),
    )
    args = parser.parse_args(argv)
    registry = build_short_command_registry()
    records = {
        command_id: run_registered_command(spec)
        for command_id, spec in registry.items()
    }
    report = build_short_report(records)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    _write_json(output, report)
    print(json.dumps({
        "decision": report["decision"],
        "short_gate": report["short_gate"],
        "maximum_identity_residual_mwh": report["maximum_identity_residual_mwh"],
        "annual_gate": report["annual_gate"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0 if report["decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
