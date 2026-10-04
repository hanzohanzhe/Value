"""Canonical rolling integrity chains for VALUE market-ledger v8."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Mapping


SCIENCE_PROJECTION_SCHEMA = "value.market-common-projection/v1"
EVIDENCE_PROJECTION_SCHEMA = "value.market-stored-evidence/v1"
_ZERO_SHA256 = "0" * 64


def _require_sha256(value: str, name: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return text


def canonical_json_bytes(
    payload: Mapping[str, object], *, schema_version: str
) -> bytes:
    if not isinstance(payload, Mapping):
        raise ValueError("integrity projection must be a mapping")
    if payload.get("schema_version") != schema_version:
        raise ValueError(
            f"integrity projection must use schema_version {schema_version}"
        )
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def projection_sha256(
    payload: Mapping[str, object], *, schema_version: str
) -> str:
    return hashlib.sha256(
        canonical_json_bytes(payload, schema_version=schema_version)
    ).hexdigest()


def _next_hash(
    previous: str,
    payload: Mapping[str, object],
    *,
    schema_version: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(_require_sha256(previous, "previous").encode("ascii"))
    digest.update(canonical_json_bytes(payload, schema_version=schema_version))
    return digest.hexdigest()


def next_science_hash(
    previous: str, common_projection: Mapping[str, object]
) -> str:
    return _next_hash(
        previous,
        common_projection,
        schema_version=SCIENCE_PROJECTION_SCHEMA,
    )


def next_evidence_hash(
    previous: str, stored_rows: Mapping[str, object]
) -> str:
    return _next_hash(
        previous,
        stored_rows,
        schema_version=EVIDENCE_PROJECTION_SCHEMA,
    )


def _metadata_value(connection: sqlite3.Connection, key: str, default: str) -> str:
    row = connection.execute(
        "SELECT value FROM metadata WHERE key=?", (key,)
    ).fetchone()
    return str(row[0]) if row else default


def _year_row_counts(
    connection: sqlite3.Connection, year: int
) -> dict[str, int]:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    counts: dict[str, int] = {}
    for table in sorted(tables):
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if "year" in columns:
            counts[table] = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE year=?", (year,)
                ).fetchone()[0]
            )
    return counts


def annual_evidence_payload(
    connection: sqlite3.Connection, year: int
) -> dict[str, object]:
    """Build the fixed annual evidence projection from authoritative rows."""

    columns = [
        str(row[1])
        for row in connection.execute("PRAGMA table_info(reliability_event)")
    ]
    rows = [
        dict(zip(columns, row))
        for row in connection.execute(
            "SELECT * FROM reliability_event WHERE year=? "
            "ORDER BY start_period, end_period, event_id",
            (int(year),),
        )
    ]
    return {
        "schema_version": EVIDENCE_PROJECTION_SCHEMA,
        "period": {"year": int(year), "period": "annual_seal"},
        "annual_rows": {"reliability_event": rows},
        "annual_row_counts": {"reliability_event": len(rows)},
    }


def seal_year(
    connection: sqlite3.Connection, year: int
) -> Mapping[str, object]:
    """Seal one already-committed year without reading the SQLite file."""

    latest = connection.execute(
        "SELECT science_hash, evidence_hash FROM period_integrity "
        "WHERE year=? ORDER BY period DESC LIMIT 1",
        (int(year),),
    ).fetchone()
    if latest is None:
        raise ValueError(f"cannot seal year {year}: no committed periods")
    contexts = connection.execute(
        "SELECT run_context_sha256, year_context_sha256, period_count, "
        "science_root, evidence_root, row_counts_json, trace_coverage_json, complete "
        "FROM year_integrity WHERE year=?",
        (int(year),),
    ).fetchone()
    if contexts is None:
        raise ValueError(f"cannot seal year {year}: integrity state is missing")
    if int(contexts[7]) == 1:
        return {
            "year": int(year),
            "run_context_sha256": str(contexts[0]),
            "year_context_sha256": str(contexts[1]),
            "science_root": str(contexts[3]),
            "evidence_root": str(contexts[4]),
            "period_count": int(contexts[2]),
            "row_counts": json.loads(str(contexts[5])),
            "trace_coverage": json.loads(str(contexts[6])),
            "complete": True,
        }
    periods = [
        int(row[0])
        for row in connection.execute(
            "SELECT period FROM period_integrity WHERE year=? ORDER BY period",
            (int(year),),
        )
    ]
    if periods != list(range(len(periods))) or len(periods) != int(contexts[2]):
        raise ValueError(
            f"cannot seal year {year}: period chain is not contiguous and complete"
        )
    annual_payload = annual_evidence_payload(connection, int(year))
    annual_evidence_root = next_evidence_hash(str(latest[1]), annual_payload)
    row_counts = _year_row_counts(connection, int(year))
    trace_level = _metadata_value(connection, "trace_level", "unknown")
    trace_coverage = {
        "schema_version": "value.market-trace-coverage/v1",
        "trace_level": trace_level,
        "common_summary": trace_level in {"summary", "full"},
        "full_detail": trace_level == "full",
    }
    connection.execute(
        "UPDATE year_integrity SET science_root=?, evidence_root=?, "
        "row_counts_json=?, trace_coverage_json=?, complete=1 WHERE year=?",
        (
            str(latest[0]),
            annual_evidence_root,
            json.dumps(row_counts, sort_keys=True, separators=(",", ":")),
            json.dumps(trace_coverage, sort_keys=True, separators=(",", ":")),
            int(year),
        ),
    )
    return {
        "year": int(year),
        "run_context_sha256": str(contexts[0]),
        "year_context_sha256": str(contexts[1]),
        "science_root": str(latest[0]),
        "evidence_root": annual_evidence_root,
        "period_count": int(contexts[2]),
        "row_counts": row_counts,
        "trace_coverage": trace_coverage,
        "complete": True,
    }


def initial_science_hash(run_context_sha256: str, year_context_sha256: str) -> str:
    digest = hashlib.sha256()
    digest.update(_require_sha256(run_context_sha256, "run_context_sha256").encode("ascii"))
    digest.update(_require_sha256(year_context_sha256, "year_context_sha256").encode("ascii"))
    return digest.hexdigest()


def initial_evidence_hash(science_seed: str, trace_level: str) -> str:
    digest = hashlib.sha256()
    digest.update(_require_sha256(science_seed, "science_seed").encode("ascii"))
    digest.update(str(trace_level).encode("utf-8"))
    return digest.hexdigest()


ZERO_SHA256 = _ZERO_SHA256
