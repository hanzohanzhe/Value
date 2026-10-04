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
anything unmatched is trajectory (the conservative default).  A column's zone
is pinned by the first revision that records it (``pinned_zones``): later
revisions may only make it stricter, and deltas are classified with the pinned
zone, so editing zones.json cannot unfreeze a doctoral trajectory column.

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
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

SCHEMA_VERSION = "value.golden-digest/v1"
JSON_COLUMN_DEPTH = 4
ROW_COUNT_SUFFIX = ".#rows"
ZONES = ("trajectory", "accounting", "identity")
# 128-bit prefixes of sha256 keep golden files small; collisions are not a
# realistic concern for regression detection.
HASH_CHARS = 32
GATED_ZONES = ("trajectory", "accounting")
# Strictness order.  A column's zone is pinned by the first revision that
# records it; a later revision may move it to a stricter zone but never to a
# weaker one, so editing zones.json cannot relabel a frozen trajectory column.
ZONE_STRENGTH = {"identity": 0, "accounting": 1, "trajectory": 2}

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


def compare_digests(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    mode: str = "exact",
    pinned: Mapping[str, str] | None = None,
) -> list[Difference]:
    """Per-column differences.  ``pinned`` (see :func:`pinned_zones`) overrides
    the zone recorded in either digest, so a delta is always classified with
    the zone a column had when it entered the golden file."""

    if mode not in {"exact", "tolerance"}:
        raise ValueError(f"unknown comparison mode {mode!r}")
    field = "sha256" if mode == "exact" else "sha256_9g"
    left = expected["columns"]
    right = actual["columns"]
    differences: list[Difference] = []
    pinned = pinned or {}

    def zone(key: str, recorded: str) -> str:
        return _stricter(pinned.get(key, recorded), recorded)

    for key in sorted(set(left) | set(right)):
        if key not in right:
            differences.append(Difference(key, "removed", zone(key, left[key]["zone"]), section_of(key)))
        elif key not in left:
            differences.append(Difference(key, "added", zone(key, right[key]["zone"]), section_of(key)))
        elif left[key][field] != right[key][field] or left[key]["count"] != right[key]["count"]:
            differences.append(
                Difference(key, "changed", _stricter(zone(key, left[key]["zone"]), right[key]["zone"]), section_of(key))
            )
    return differences


def _stricter(first: str, second: str) -> str:
    return first if ZONE_STRENGTH.get(first, 2) >= ZONE_STRENGTH.get(second, 2) else second


def pinned_zones(golden: Mapping[str, Any], upto: int | None = None) -> dict[str, str]:
    """Zone of every column as pinned by the revisions ``0..upto-1``.

    A column takes the zone of the first revision that records it; a later
    revision can only make it stricter.
    """

    pinned: dict[str, str] = {}
    revisions = golden.get("revisions") or []
    for revision in revisions[: len(revisions) if upto is None else upto]:
        for key, record in revision["digest"]["columns"].items():
            pinned[key] = _stricter(pinned[key], record["zone"]) if key in pinned else record["zone"]
    return pinned


def zone_weakenings(pinned: Mapping[str, str], digest: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """``(key, pinned zone, recorded zone)`` for columns recorded in a weaker zone."""

    rows = []
    for key, record in digest["columns"].items():
        if key in pinned and ZONE_STRENGTH.get(record["zone"], 2) < ZONE_STRENGTH.get(pinned[key], 2):
            rows.append((key, pinned[key], record["zone"]))
    return sorted(rows)


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


class _ReportPending:
    """Marker returned by a ``numeric_reports`` loader for the revision that
    ``capture.py revise`` is appending: its numeric report can only be built
    once the revision exists (``capture.py numeric-report``), so ``revise``
    does not check it; ``capture.py validate`` (gate ``golden_bookkeeping``)
    still refuses the commit until the report is in place."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "REPORT_PENDING"


REPORT_PENDING: Any = _ReportPending()


def validate_golden_file(
    golden: Mapping[str, Any],
    trajectory_allowlist: Mapping[str, Any],
    numeric_reports: Callable[[int], Mapping[str, Any] | None] | None = None,
) -> list[str]:
    """Return bookkeeping errors for one golden case file (no runs needed).

    ``numeric_reports(k)`` returns the committed numeric report of revision k,
    ``None`` when there is none, or :data:`REPORT_PENDING` for a revision
    whose report is still to be built.  A doctoral revision that changes
    trajectory columns needs one (:func:`validate_numeric_report`); any other
    revision must not have one (a report documents a doctoral trajectory
    re-baseline and nothing else).
    """

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
        pinned = pinned_zones(golden, index)
        weakened = zone_weakenings(pinned, revision["digest"])
        if weakened:
            sample = ", ".join(f"{key} {before}->{after}" for key, before, after in weakened[:5])
            errors.append(
                f"{name}: revision {index} moves {len(weakened)} column(s) to a weaker zone than revision "
                f"{_first_revision(golden, weakened[0][0])} recorded ({sample})"
            )
        delta = compare_digests(revisions[index - 1]["digest"], revision["digest"], "exact", pinned)
        if not delta:
            errors.append(f"{name}: revision {index} does not change the digest")
        recorded_rows = revision.get("delta", {}).get("differences", [])
        if sorted(row["key"] for row in recorded_rows) != sorted(row.key for row in delta):
            errors.append(f"{name}: revision {index} delta does not match its digests")
        elif sorted((row["key"], row["zone"]) for row in recorded_rows) != sorted((row.key, row.zone) for row in delta):
            errors.append(f"{name}: revision {index} delta records zones that differ from the pinned zones")
        trajectory = [row for row in delta if row.zone == "trajectory"] if golden.get("family") == "doctoral" else []
        report = numeric_reports(index) if numeric_reports is not None else None
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
            if report is not REPORT_PENDING:
                errors.extend(validate_numeric_report(report, golden, index, delta))
        elif report is not None and report is not REPORT_PENDING:
            errors.append(
                f"tests/golden/reports/{golden.get('case')}-r{index}.json: {name} revision {index} changes no doctoral "
                "trajectory column; numeric reports document doctoral trajectory re-baselines only"
            )
    return errors


def _first_revision(golden: Mapping[str, Any], key: str) -> int:
    for revision in golden.get("revisions") or []:
        if key in revision["digest"]["columns"]:
            return int(revision.get("revision", 0))
    return 0


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
    delta = compare_digests(latest_digest(golden), digest, "exact", pinned_zones(golden))
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


# --------------------------------------------------------------------------
# Numeric before/after reports for doctoral trajectory re-baselines
#
# Decisions Q9/A4/A5 require every doctoral trajectory re-baseline to come with
# a diff report.  Golden files keep hashes only, so the report is computed from
# two kept run outputs (parent commit and child) and committed next to the
# revision as tests/golden/reports/<case>-r<k>.json.  ``validate_golden_file``
# refuses a doctoral trajectory revision without a matching report.

NUMERIC_REPORT_SCHEMA = "value.golden-numeric-report/v1"
_YEAR_IN_PATH = re.compile(r"(?:^|[.\[])(\d{4})(?=$|[.:\]\[])")


def digest_fingerprint(digest: Mapping[str, Any]) -> str:
    """sha256 of a digest as stored in a golden revision (runtime fields dropped)."""

    stored = {key: value for key, value in digest.items() if key not in {"seconds", "case"}}
    return hashlib.sha256(json.dumps(stored, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def column_values(output_dir: Path) -> dict[str, list[tuple[str, Any, Any]]]:
    """The raw values behind every digest column: ``key -> [(label, value, year)]``.

    Keys, labels and volatile-key handling are those of :func:`digest_run`;
    ``year`` is the row's ``year`` column (SQLite) or a year found in the JSON
    path, else ``None``.
    """

    values: dict[str, list[tuple[str, Any, Any]]] = {}
    for artifact, path in iter_artifacts(output_dir):
        if path.suffix == ".sqlite":
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
                    except sqlite3.OperationalError:
                        cursor = connection.execute(f'SELECT {quoted} FROM "{table}" ORDER BY {quoted}')
                    year_index = columns.index("year") if "year" in columns else None
                    lists = [values.setdefault(f"{artifact}::{table}.{column}", []) for column in columns]
                    rows = 0
                    for row in cursor:
                        year = row[year_index] if year_index is not None else None
                        for index, value in enumerate(row):
                            lists[index].append((str(rows), "<volatile>" if columns[index] in VOLATILE_KEYS else value, year))
                        rows += 1
                    values[f"{artifact}::{table}{ROW_COUNT_SUFFIX}"] = [("rows", rows, None)]
            finally:
                connection.close()
            continue
        if path.suffix == ".jsonl":
            payload: Any = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
        for leaf_path, concrete, value in _json_leaves(payload):
            column = ".".join(leaf_path[:JSON_COLUMN_DEPTH]) or "$"
            match = _YEAR_IN_PATH.search(concrete)
            values.setdefault(f"{artifact}::{column}", []).append((concrete, value, match.group(1) if match else None))
    return values


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _column_change(before: Sequence[tuple[str, Any, Any]], after: Sequence[tuple[str, Any, Any]]) -> dict[str, Any]:
    left = {label: (value, year) for label, value, year in before}
    right = {label: (value, year) for label, value, year in after}
    changed = 0
    max_abs = 0.0
    max_rel: float | None = None
    zero_base_changes = 0
    samples: list[dict[str, Any]] = []
    for label in sorted(set(left) | set(right), key=lambda item: (len(item), item)):
        old = left.get(label, (None, None))[0]
        new = right.get(label, (None, None))[0]
        if label in left and label in right and _encode(old, False) == _encode(new, False):
            continue
        changed += 1
        old_number, new_number = _number(old), _number(new)
        if label in left and label in right and old_number is not None and new_number is not None:
            delta = abs(new_number - old_number)
            max_abs = max(max_abs, delta)
            if old_number != 0:
                relative = delta / abs(old_number)
                max_rel = relative if max_rel is None else max(max_rel, relative)
            elif delta:
                zero_base_changes += 1
        elif len(samples) < 3:
            samples.append({"label": label, "before": None if label not in left else str(old)[:120],
                            "after": None if label not in right else str(new)[:120]})

    def totals(rows: Sequence[tuple[str, Any, Any]]) -> tuple[float, dict[str, float]]:
        total = 0.0
        by_year: dict[str, float] = {}
        for _, value, year in rows:
            number = _number(value)
            if number is None:
                continue
            total += number
            if year is not None:
                by_year[str(year)] = by_year.get(str(year), 0.0) + number
        return total, by_year

    numeric = any(_number(value) is not None for _, value, _ in (*before, *after))
    record: dict[str, Any] = {
        "values_before": len(before),
        "values_after": len(after),
        "changed_values": changed,
        "numeric": numeric,
    }
    if numeric:
        sum_before, years_before = totals(before)
        sum_after, years_after = totals(after)
        record.update({
            "max_abs_delta": max_abs,
            "max_rel_delta": max_rel,
            "changes_from_zero": zero_base_changes,
            "sum_before": sum_before,
            "sum_after": sum_after,
            "annual_totals": {year: [years_before.get(year, 0.0), years_after.get(year, 0.0)]
                              for year in sorted(set(years_before) | set(years_after))},
        })
    if samples:
        record["non_numeric_samples"] = samples
    return record


def build_numeric_report(
    before_dir: Path,
    after_dir: Path,
    zones: ZoneRules,
    *,
    family: str,
    case: str,
    revision: int,
    parent_commit: str,
    child_commit: str,
    pinned: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Per-column magnitudes of every changed digest column between two run outputs."""

    before, after = column_values(before_dir), column_values(after_dir)
    after_digest = digest_run(after_dir, zones)
    pinned = pinned or {}
    columns: dict[str, Any] = {}
    by_zone: dict[str, int] = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old is not None and new is not None and [(label, _encode(value, False)) for label, value, _ in old] == [
            (label, _encode(value, False)) for label, value, _ in new
        ]:
            continue
        zone = _stricter(pinned.get(key, zones.zone(key)), zones.zone(key))
        kind = "added" if old is None else "removed" if new is None else "changed"
        columns[key] = {"zone": zone, "section": section_of(key), "kind": kind, **_column_change(old or [], new or [])}
        by_zone[zone] = by_zone.get(zone, 0) + 1
    return {
        "schema_version": NUMERIC_REPORT_SCHEMA,
        "family": family,
        "case": case,
        "revision": revision,
        "parent_commit": parent_commit,
        "child_commit": child_commit,
        "digest_sha256": digest_fingerprint(after_digest),
        "summary": {"changed_columns": len(columns), "by_zone": dict(sorted(by_zone.items()))},
        "columns": columns,
    }


def validate_numeric_report(report: Mapping[str, Any] | None, golden: Mapping[str, Any], index: int, delta: Sequence[Difference]) -> list[str]:
    name = f"{golden.get('family')}/{golden.get('case')}"
    where = f"tests/golden/reports/{golden.get('case')}-r{index}.json"
    if report is None:
        return [f"{name}: revision {index} changes doctoral trajectory without a numeric before/after report ({where}; capture.py numeric-report)"]
    errors = []
    expected = {"schema_version": NUMERIC_REPORT_SCHEMA, "family": golden.get("family"), "case": golden.get("case"), "revision": index}
    for field, value in expected.items():
        if report.get(field) != value:
            errors.append(f"{where}: {field} is {report.get(field)!r}, expected {value!r}")
    if report.get("digest_sha256") != digest_fingerprint(golden["revisions"][index]["digest"]):
        errors.append(f"{where}: digest_sha256 does not match revision {index}")
    reported = set((report.get("columns") or {}))
    changed = {row.key for row in delta}
    if reported != changed:
        errors.append(f"{where}: reports {len(reported)} column(s) but revision {index} changes {len(changed)}")
    return errors
