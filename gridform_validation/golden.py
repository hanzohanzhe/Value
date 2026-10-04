"""Golden digests of VALUE run outputs, hashed per table x column.

A digest maps ``"<artifact>::<column>"`` keys to a record::

    {"zone": "trajectory|accounting|identity",
     "count": <values hashed>,
     "sha256": <exact hash, floats as repr; 128-bit prefix>,
     "sha256_9g": <hash with floats formatted as %.9g; 128-bit prefix>}

The section (dispatch, economics, reporting) is derived from the artifact
name (``section_of``).

* SQLite artifacts: every table, one key per column (values ordered by
  rowid) plus ``<table>.#rows``.
* JSON artifacts: leaves are flattened; list indices are dropped from the
  column key and the key is truncated to ``JSON_COLUMN_DEPTH`` dict keys.
  Volatile keys (``uri``, ``*_seconds``, ``created_at``, ``output_dir``,
  ``origin``, ``psm_input_sha256`` ...) are removed recursively.

Zones follow decision Q12: the trajectory zone (dispatch, flows, prices, SoC,
capacity, investment proposals) of the doctoral family is frozen; the
accounting zone (residuals, adjustments, audit tables, cost ledgers,
validation reports) may be revised under a universal correction id.  Zone
rules live in ``tests/golden/zones.json``; the first matching pattern wins and
anything unmatched is trajectory (the conservative default).

Exact comparison is meant for the reference platform (linux-x86_64,
CPython 3.10, numpy 1.24.4); elsewhere ``tolerance`` mode compares the
``%.9g`` hashes.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import platform
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Sequence

SCHEMA_VERSION = "value.golden-digest/v1"
JSON_COLUMN_DEPTH = 4
ROW_COUNT_SUFFIX = ".#rows"
ZONES = ("trajectory", "accounting", "identity")
# 128-bit prefixes of sha256 keep golden files small; collisions are not a
# realistic concern for regression detection.
HASH_CHARS = 32
GATED_ZONES = ("trajectory", "accounting")

VOLATILE_KEYS = frozenset(
    {
        "uri",
        "writer_seconds",
        "created_at",
        "output_dir",
        "origin",
        "psm_input_sha256",
        "generated_at",
        "started_at",
        "finished_at",
        "completed_at",
        "updated_at",
        "timestamp",
        "run_dir",
        "output_root",
        "path",
        "absolute_path",
    }
)
VOLATILE_SUFFIXES = ("_seconds", "_at_utc", "_timestamp")
# Dict keys that are data (years, period ids such as "2025:17") rather than
# field names are folded into one "{}" column so columns stay table-like.
_DATA_KEY = re.compile(r"^\d{4}(:\d+)?$")

# Run artifacts that are configuration, identity, timing or duplicates of
# digested results.  They are never part of a golden digest.
EXCLUDED_ARTIFACTS = (
    "artifact-index.json",
    "cem-model-identity.json",
    "legacy-config-session.json",
    "module-resolution.json",
    "performance.json",
    "preflight.json",
    "provenance.json",
    "resolved-run.json",
    "value-run-context.json",
    "comparison-eligibility.json",
    "execution-bundle.json",
    "status.json",
    "orchestrator-events.jsonl",
    "module-manifests/*",
    "checkpoints-v2/*",
    "checkpoints/*",
    "partial-year-results/*",
    "value-kernel-session/*",
    "market/field-dictionary.json",
    "market/index.json",
    "market/.*",
    "*/.*",
    "subannual-checkpoints/*",
    "frozen-inputs/*",
    "input-snapshot/*",
)

SECTION_RULES = (
    ("market/*.sqlite", "dispatch"),
    ("planning/*.sqlite", "dispatch"),
    ("validation/*", "reporting"),
    ("parity/*", "reporting"),
    ("network/*", "reporting"),
    ("market/metadata.json", "reporting"),
    ("teaching/*", "reporting"),
    ("*", "economics"),
)


@dataclass(frozen=True)
class ZoneRules:
    """Ordered (pattern, zone) rules matched against ``artifact::column``."""

    rules: tuple[tuple[str, str], ...]
    default: str = "trajectory"

    @classmethod
    def load(cls, path: Path) -> "ZoneRules":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rules = tuple((str(row["pattern"]), str(row["zone"])) for row in payload["rules"])
        for _, zone in rules:
            if zone not in ZONES:
                raise ValueError(f"unknown golden zone {zone!r}")
        return cls(rules, str(payload.get("default", "trajectory")))

    def zone(self, key: str) -> str:
        for pattern, zone in self.rules:
            if fnmatch.fnmatchcase(key, pattern):
                return zone
        return self.default


def _section(artifact: str) -> str:
    for pattern, section in SECTION_RULES:
        if fnmatch.fnmatchcase(artifact, pattern):
            return section
    return "economics"


def section_of(key: str) -> str:
    """Section (dispatch, economics, reporting) of an ``artifact::column`` key."""

    return _section(key.split("::", 1)[0])


def _excluded(artifact: str) -> bool:
    name = PurePosixPath(artifact).name
    if name.startswith("."):
        return True
    return any(fnmatch.fnmatchcase(artifact, pattern) for pattern in EXCLUDED_ARTIFACTS)


def _volatile(key: str) -> bool:
    return key in VOLATILE_KEYS or key.endswith(VOLATILE_SUFFIXES)


def _encode(value: Any, rounded: bool) -> str:
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return repr(value)
        return format(value, ".9g") if rounded else repr(value)
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "b:" + bytes(value).hex()
    return "s:" + str(value)


class _ColumnHasher:
    __slots__ = ("exact", "rounded", "count")

    def __init__(self) -> None:
        self.exact = hashlib.sha256()
        self.rounded = hashlib.sha256()
        self.count = 0

    def add(self, label: str, value: Any) -> None:
        self.exact.update(f"{label}\x1f{_encode(value, False)}\x1e".encode("utf-8", "surrogatepass"))
        self.rounded.update(f"{label}\x1f{_encode(value, True)}\x1e".encode("utf-8", "surrogatepass"))
        self.count += 1


def _json_leaves(value: Any, path: tuple[str, ...] = (), concrete: str = "") -> Iterator[tuple[tuple[str, ...], str, Any]]:
    """Yield (column path without list indices, concrete path, leaf value)."""

    if isinstance(value, Mapping):
        if not value:
            yield path, concrete, "{}"
        for key in value:
            text = str(key)
            if _volatile(text):
                continue
            column = "{}" if _DATA_KEY.match(text) else text
            yield from _json_leaves(value[key], path + (column,), f"{concrete}.{text}")
    elif isinstance(value, list):
        if not value:
            yield path, concrete, "[]"
        for index, item in enumerate(value):
            yield from _json_leaves(item, path, f"{concrete}[{index}]")
    else:
        yield path, concrete, value


def _digest_json(artifact: str, payload: Any, hashers: dict[str, _ColumnHasher]) -> None:
    for path, concrete, value in _json_leaves(payload):
        column = ".".join(path[:JSON_COLUMN_DEPTH]) or "$"
        hashers.setdefault(f"{artifact}::{column}", _ColumnHasher()).add(concrete, value)


def _digest_jsonl(artifact: str, text: str, hashers: dict[str, _ColumnHasher]) -> None:
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    _digest_json(artifact, rows, hashers)


def _digest_sqlite(artifact: str, path: Path, hashers: dict[str, _ColumnHasher]) -> None:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            quoted = ", ".join(f'"{column}"' for column in columns)
            try:
                cursor = connection.execute(f'SELECT {quoted} FROM "{table}" ORDER BY rowid')
            except sqlite3.OperationalError:  # WITHOUT ROWID tables
                cursor = connection.execute(f'SELECT {quoted} FROM "{table}" ORDER BY {quoted}')
            column_hashers = [hashers.setdefault(f"{artifact}::{table}.{column}", _ColumnHasher()) for column in columns]
            rows = 0
            for row in cursor:
                for index, value in enumerate(row):
                    if columns[index] in VOLATILE_KEYS:
                        value = "<volatile>"
                    column_hashers[index].add(str(rows), value)
                rows += 1
            counter = hashers.setdefault(f"{artifact}::{table}{ROW_COUNT_SUFFIX}", _ColumnHasher())
            counter.add("rows", rows)
    finally:
        connection.close()


def iter_artifacts(output_dir: Path) -> Iterator[tuple[str, Path]]:
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        artifact = path.relative_to(output_dir).as_posix()
        if _excluded(artifact):
            continue
        if path.suffix in {".json", ".jsonl", ".sqlite"}:
            yield artifact, path


def digest_run(output_dir: Path, zones: ZoneRules) -> dict[str, Any]:
    """Return the golden digest of one run output directory."""

    hashers: dict[str, _ColumnHasher] = {}
    for artifact, path in iter_artifacts(output_dir):
        if path.suffix == ".sqlite":
            _digest_sqlite(artifact, path, hashers)
        elif path.suffix == ".jsonl":
            _digest_jsonl(artifact, path.read_text(encoding="utf-8"), hashers)
        else:
            _digest_json(artifact, json.loads(path.read_text(encoding="utf-8")), hashers)
    columns = {}
    for key in sorted(hashers):
        hasher = hashers[key]
        columns[key] = {
            "zone": zones.zone(key),
            "count": hasher.count,
            "sha256": hasher.exact.hexdigest()[:HASH_CHARS],
            "sha256_9g": hasher.rounded.hexdigest()[:HASH_CHARS],
        }
    return {"schema_version": SCHEMA_VERSION, "platform": reference_platform(), "columns": columns}


def reference_platform() -> dict[str, str]:
    try:
        import numpy

        numpy_version = numpy.__version__
    except Exception:  # pragma: no cover - numpy is a hard dependency
        numpy_version = "unavailable"
    return {
        "platform": f"{sys.platform}-{platform.machine()}",
        "python": ".".join(platform.python_version_tuple()[:2]),
        "implementation": platform.python_implementation(),
        "numpy": numpy_version,
    }


REFERENCE_PLATFORM = {"platform": "linux-x86_64", "python": "3.10", "implementation": "CPython", "numpy": "1.24.4"}


def default_mode() -> str:
    return "exact" if reference_platform() == REFERENCE_PLATFORM else "tolerance"


@dataclass(frozen=True)
class Difference:
    key: str
    kind: str  # changed | added | removed
    zone: str
    section: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "kind": self.kind, "zone": self.zone, "section": self.section}


def compare_digests(expected: Mapping[str, Any], actual: Mapping[str, Any], mode: str = "exact") -> list[Difference]:
    if mode not in {"exact", "tolerance"}:
        raise ValueError(f"unknown comparison mode {mode!r}")
    field = "sha256" if mode == "exact" else "sha256_9g"
    left = expected["columns"]
    right = actual["columns"]
    differences: list[Difference] = []
    for key in sorted(set(left) | set(right)):
        if key not in right:
            differences.append(Difference(key, "removed", left[key]["zone"], section_of(key)))
        elif key not in left:
            differences.append(Difference(key, "added", right[key]["zone"], section_of(key)))
        elif left[key][field] != right[key][field] or left[key]["count"] != right[key]["count"]:
            differences.append(Difference(key, "changed", left[key]["zone"], section_of(key)))
    return differences


def summarise(differences: Iterable[Difference]) -> dict[str, Any]:
    rows = list(differences)
    zones: dict[str, int] = {}
    for row in rows:
        zones[row.zone] = zones.get(row.zone, 0) + 1
    return {"count": len(rows), "by_zone": dict(sorted(zones.items())), "differences": [row.to_dict() for row in rows]}


# --------------------------------------------------------------------------
# Golden files and revision bookkeeping

GOLDEN_FILE_SCHEMA = "value.golden-case/v1"


def latest_digest(golden: Mapping[str, Any]) -> Mapping[str, Any]:
    return golden["revisions"][-1]["digest"]


def validate_golden_file(golden: Mapping[str, Any], trajectory_allowlist: Mapping[str, Any]) -> list[str]:
    """Return bookkeeping errors for one golden case file (no runs needed)."""

    errors: list[str] = []
    name = f"{golden.get('family')}/{golden.get('case')}"
    if golden.get("schema_version") != GOLDEN_FILE_SCHEMA:
        errors.append(f"{name}: unsupported schema {golden.get('schema_version')!r}")
        return errors
    if golden.get("family") not in {"doctoral", "corrected"}:
        errors.append(f"{name}: unknown family {golden.get('family')!r}")
    revisions = golden.get("revisions") or []
    if not revisions:
        errors.append(f"{name}: no revisions")
        return errors
    allowed_findings = set(trajectory_allowlist.get("findings", {}))
    used: set[str] = set()
    for index, revision in enumerate(revisions):
        if revision.get("revision") != index:
            errors.append(f"{name}: revision {index} is numbered {revision.get('revision')!r}")
        if index == 0:
            continue
        if not revision.get("reason"):
            errors.append(f"{name}: revision {index} has no reason")
        if not revision.get("correction_ids") and not revision.get("findings"):
            errors.append(f"{name}: revision {index} names no correction id or finding")
        delta = compare_digests(revisions[index - 1]["digest"], revision["digest"], "exact")
        if not delta:
            errors.append(f"{name}: revision {index} does not change the digest")
        recorded = sorted(row["key"] for row in revision.get("delta", {}).get("differences", []))
        if recorded != sorted(row.key for row in delta):
            errors.append(f"{name}: revision {index} delta does not match its digests")
        if golden.get("family") == "doctoral":
            trajectory = [row for row in delta if row.zone == "trajectory"]
            if trajectory:
                findings = set(revision.get("findings") or [])
                approved = findings & allowed_findings
                if not approved:
                    errors.append(
                        f"{name}: revision {index} changes {len(trajectory)} trajectory column(s) without an approved universal finding"
                    )
                reused = approved & used
                if reused:
                    errors.append(f"{name}: revision {index} re-baselines trajectory again for {sorted(reused)}")
                used |= approved
    return errors


def new_golden(family: str, case: str, digest: Mapping[str, Any], base_commit: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": GOLDEN_FILE_SCHEMA,
        "family": family,
        "case": case,
        "revisions": [
            {
                "revision": 0,
                "base_commit": base_commit,
                "reason": reason,
                "correction_ids": [],
                "findings": [],
                "digest": dict(digest),
            }
        ],
    }


def append_revision(
    golden: dict[str, Any],
    digest: Mapping[str, Any],
    *,
    base_commit: str,
    reason: str,
    correction_ids: Sequence[str],
    findings: Sequence[str] = (),
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("a golden revision needs a reason")
    if not correction_ids and not findings:
        raise ValueError("a golden revision needs at least one correction id or finding")
    delta = compare_digests(latest_digest(golden), digest, "exact")
    if not delta:
        raise ValueError("digest is unchanged; no revision needed")
    revision = {
        "revision": len(golden["revisions"]),
        "base_commit": base_commit,
        "reason": reason,
        "correction_ids": list(correction_ids),
        "findings": list(findings),
        "delta": summarise(delta),
        "digest": dict(digest),
    }
    golden["revisions"].append(revision)
    return revision


def write_golden(path: Path, golden: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
