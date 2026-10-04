"""Build the audited VALUE carbon-factor SQLite database from text seeds."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPOSITORY_ROOT / "gridform_core" / "data" / "carbon"
DEFAULT_OUTPUT = DATA_DIRECTORY / "value_carbon_factors.sqlite"


def _read_csv(name: str) -> list[dict[str, str]]:
    path = DATA_DIRECTORY / name
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _optional_float(value: str) -> float | None:
    return None if value == "" else float(value)


def _optional_int(value: str) -> int | None:
    return None if value == "" else int(value)


def _insert_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: Iterable[str],
    rows: Iterable[dict[str, Any]],
) -> None:
    column_list = list(columns)
    placeholders = ", ".join("?" for _ in column_list)
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(column_list)}) VALUES ({placeholders})",
        ([row[column] for column in column_list] for row in rows),
    )


def build_database(output: Path = DEFAULT_OUTPUT) -> Path:
    """Build *output* atomically and return its resolved path."""

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    datasets = _read_csv("datasets.csv")
    sources = _read_csv("sources.csv")
    factors = _read_csv("factor_catalog.csv")
    rules = _read_csv("methodology_rules.csv")

    for row in sources:
        row["publication_year"] = int(row["publication_year"])
        row["doi"] = row["doi"] or None

    for row in factors:
        row["value"] = float(row["value"])
        row["commissioning_year"] = _optional_int(row["commissioning_year"])
        row["load_factor"] = _optional_float(row["load_factor"])
        row["lifetime_years"] = _optional_float(row["lifetime_years"])
        row["duration_hours"] = _optional_float(row["duration_hours"])
        row["used_by_snapshot"] = int(row["used_by_snapshot"])
        row["derivation"] = row["derivation"] or None

    manifest = json.loads((DATA_DIRECTORY / "snapshot_manifest.json").read_text(encoding="utf-8"))
    artifacts = []
    for item in manifest["source_artifacts"]:
        artifacts.append(
            {
                "artifact_id": item["artifact_id"],
                "portable_name": item["portable_name"],
                "sha256": item["sha256"],
                "size_bytes": int(item["size_bytes"]),
                "modified_at": item["modified_at"],
                "copied_into_repository": int(item["copied_into_repository"]),
                "repository_copy": item.get("repository_copy"),
                "note": item.get("copy_note") or item.get("reason_not_copied") or "",
            }
        )

    temporary_handle, temporary_name = tempfile.mkstemp(
        prefix="carbon-factors-", suffix=".sqlite.tmp", dir=output.parent
    )
    os.close(temporary_handle)
    temporary_path = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            connection.executescript((DATA_DIRECTORY / "schema.sql").read_text(encoding="utf-8"))
            with connection:
                _insert_rows(connection, "datasets", datasets[0].keys(), datasets)
                _insert_rows(connection, "sources", sources[0].keys(), sources)
                _insert_rows(connection, "factors", factors[0].keys(), factors)
                _insert_rows(connection, "methodology_rules", rules[0].keys(), rules)
                _insert_rows(connection, "snapshot_artifacts", artifacts[0].keys(), artifacts)

            foreign_key_failures = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_failures:
                raise RuntimeError(f"Foreign-key validation failed: {foreign_key_failures}")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"SQLite integrity check failed: {integrity}")
            connection.execute("VACUUM")
        finally:
            connection.close()
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output


def _counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        return {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("datasets", "sources", "factors", "methodology_rules", "snapshot_artifacts")
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    result = build_database(arguments.output)
    print(json.dumps({"database": str(result), "counts": _counts(result)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
