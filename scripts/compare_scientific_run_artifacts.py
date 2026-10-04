"""Compare two VALUE runs after normalising only run-scoped identity fields."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


VOLATILE_KEYS = {"run_id", "result_id", "created_at", "updated_at", "writer_seconds"}
JSON_ARTIFACTS = (
    "year-results-v2.json",
    "ledgers/annual-cost-ledger.json",
    "ledgers/annual-carbon-ledger.json",
    "planning/summary.json",
    "terminal/fleet-vintage.json",
    "terminal/terminal-state.json",
)


def _scrub(value: Any, identities: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {key: _scrub(item, identities) for key, item in value.items() if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_scrub(item, identities) for item in value]
    if isinstance(value, str):
        for identity in sorted(identities, key=len, reverse=True):
            value = value.replace(identity, "<run-id>")
    return value


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sqlite_digest(path: Path, table: str) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        hasher = hashlib.sha256()
        count = 0
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid"):
            hasher.update(json.dumps(row, separators=(",", ":"), default=str).encode("utf-8"))
            hasher.update(b"\n")
            count += 1
        return {"rows": count, "sha256": hasher.hexdigest()}
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    left, right = args.left.resolve(), args.right.resolve()
    identities = (left.name, right.name)
    checks: dict[str, object] = {}
    passed = True
    for relative in JSON_ARTIFACTS:
        first_path, second_path = left / relative, right / relative
        if not first_path.is_file() and not second_path.is_file():
            continue
        if not first_path.is_file() or not second_path.is_file():
            checks[relative] = {"equal": False, "reason": "artifact missing from one run"}
            passed = False
            continue
        first = _digest(_scrub(json.loads(first_path.read_text(encoding="utf-8")), identities))
        second = _digest(_scrub(json.loads(second_path.read_text(encoding="utf-8")), identities))
        checks[relative] = {"equal": first == second, "left_sha256": first, "right_sha256": second}
        passed = passed and first == second
    for table in ("period_summary", "orders", "storage_state"):
        first = _sqlite_digest(left / "market" / "market.sqlite", table)
        second = _sqlite_digest(right / "market" / "market.sqlite", table)
        checks[f"market.sqlite::{table}"] = {"equal": first == second, "left": first, "right": second}
        passed = passed and first == second
    report = {
        "schema_version": "value.scientific-artifact-equivalence/v1",
        "passed": passed,
        "normalisation": "run/result identity and creation/update timestamps only",
        "left": str(left),
        "right": str(right),
        "checks": checks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"passed": passed, "report": str(args.report.resolve())}, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
