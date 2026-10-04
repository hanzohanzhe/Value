"""Prove that disabling the retained generation trace preserves public results."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


VOLATILE_KEYS = {
    "result_id",
    "run_id",
    "created_at",
    "updated_at",
    "started_at",
    "finished_at",
    "writer_seconds",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scrub(value: Any, run_label: str) -> Any:
    if isinstance(value, dict):
        return {
            key: scrub(item, run_label)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [scrub(item, run_label) for item in value]
    if isinstance(value, str):
        return value.replace(run_label, "<run-id>")
    return value


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def first_differences(left: Any, right: Any, path: str = "$", limit: int = 30) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []

    def visit(first: Any, second: Any, current: str) -> None:
        if len(differences) >= limit:
            return
        if type(first) is not type(second):
            differences.append({"path": current, "trace_on": repr(first)[:240], "trace_off": repr(second)[:240]})
            return
        if isinstance(first, dict):
            for key in sorted(set(first) | set(second)):
                if key not in first or key not in second:
                    differences.append({"path": f"{current}.{key}", "trace_on": repr(first.get(key))[:240], "trace_off": repr(second.get(key))[:240]})
                else:
                    visit(first[key], second[key], f"{current}.{key}")
                if len(differences) >= limit:
                    return
            return
        if isinstance(first, list):
            if len(first) != len(second):
                differences.append({"path": current + ".length", "trace_on": len(first), "trace_off": len(second)})
                return
            for index, (first_item, second_item) in enumerate(zip(first, second)):
                visit(first_item, second_item, f"{current}[{index}]")
                if len(differences) >= limit:
                    return
            return
        if first != second:
            differences.append({"path": current, "trace_on": repr(first)[:240], "trace_off": repr(second)[:240]})

    visit(left, right, path)
    return differences


def sqlite_table_digest(path: Path, table: str) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        hasher = hashlib.sha256()
        count = 0
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid"):
            hasher.update(
                json.dumps(row, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
            )
            hasher.update(b"\n")
            count += 1
        return {"columns": columns, "rows": count, "sha256": hasher.hexdigest()}
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-on", type=Path, required=True)
    parser.add_argument("--trace-off", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    left = args.trace_on.resolve()
    right = args.trace_off.resolve()

    json_artifacts = [
        "year-results-v2.json",
        "ledgers/annual-cost-ledger.json",
        "ledgers/annual-carbon-ledger.json",
        "planning/summary.json",
        "terminal/fleet-vintage.json",
        "terminal/terminal-state.json",
    ]
    json_checks: dict[str, Any] = {}
    for relative in json_artifacts:
        left_value = scrub(load_json(left / relative), left.name)
        right_value = scrub(load_json(right / relative), right.name)
        left_hash = digest(left_value)
        right_hash = digest(right_value)
        json_checks[relative] = {
            "equal_after_run_identity_normalisation": left_hash == right_hash,
            "trace_on_sha256": left_hash,
            "trace_off_sha256": right_hash,
            "first_differences": first_differences(left_value, right_value) if left_hash != right_hash else [],
        }

    sqlite_checks: dict[str, Any] = {}
    for table in ("period_summary", "storage_state"):
        left_signature = sqlite_table_digest(left / "market" / "market.sqlite", table)
        right_signature = sqlite_table_digest(right / "market" / "market.sqlite", table)
        sqlite_checks[table] = {
            "equal": left_signature == right_signature,
            "trace_on": left_signature,
            "trace_off": right_signature,
        }

    left_performance = load_json(left / "performance.json")
    right_performance = load_json(right / "performance.json")
    left_seconds = float(left_performance["phases_seconds"]["public_contract_materialisation"])
    right_seconds = float(right_performance["phases_seconds"]["public_contract_materialisation"])
    improvement = (left_seconds - right_seconds) / left_seconds * 100.0

    checks = [
        *(row["equal_after_run_identity_normalisation"] for row in json_checks.values()),
        *(row["equal"] for row in sqlite_checks.values()),
    ]
    passed = all(checks)
    report = {
        "schema_version": "value.prompt52-trace-equivalence/v1",
        "passed": passed,
        "decision": "PASS" if passed else "FAIL",
        "scope": (
            "A/B full 2025 run. SAVE_GENERATION_TRACE changes only the retained "
            "in-memory compatibility trace; public model and audit artifacts must remain identical."
        ),
        "trace_on_run": str(left),
        "trace_off_run": str(right),
        "json_artifacts": json_checks,
        "sqlite_tables": sqlite_checks,
        "performance": {
            "trace_on_public_contract_materialisation_seconds": left_seconds,
            "trace_off_public_contract_materialisation_seconds": right_seconds,
            "observed_improvement_percent": improvement,
            "interpretation": "measurement_only_not_a_scientific_result",
        },
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"decision": report["decision"], "output": str(output)}, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
