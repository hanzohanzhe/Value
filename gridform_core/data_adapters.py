"""Versioned foreign-schema adapters for canonical PSM/CEM data roles."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = "value.data-adapter/v1"
UNIT_FACTORS = {
    ("kW", "MW"): 0.001,
    ("GW", "MW"): 1000.0,
    ("kWh", "MWh"): 0.001,
    ("GWh", "MWh"): 1000.0,
    ("TWh", "MWh"): 1_000_000.0,
    ("GBP/kWh", "GBP/MWh"): 1000.0,
}
# Conversions that need an explicit, documented rate (P0-5a S10, review P6-12):
# EUR/MWh -> GBP/MWh divides by spec.source["eur_per_gbp"] and records
# spec.source["fx_basis"]; there is no default rate.
FX_CONVERSIONS = {("EUR/MWh", "GBP/MWh")}
# S-D7: cell problems are reported with their row and column, not as the
# first Python exception; at most this many are listed in full.
MAX_LISTED_CELL_PROBLEMS = 20


class CellConversionError(ValueError):
    """One source cell cannot be converted (not a spec-level error)."""


class AdapterValueError(ValueError):
    """Source cells that could not be converted, by row and column.

    ``problems`` lists at most :data:`MAX_LISTED_CELL_PROBLEMS` rows of
    ``{"row", "line", "column", "value", "problem"}``: ``row`` is the 1-based
    data row (the header is not counted) and ``line`` the CSV line number.
    ``problem_count`` is the total.  ``messages()`` gives one sentence per
    listed cell plus a closing count when more were found.
    """

    def __init__(self, problems: Sequence[Mapping[str, object]], problem_count: int) -> None:
        self.problems = [dict(row) for row in problems]
        self.problem_count = int(problem_count)
        super().__init__("; ".join(self.messages()))

    def messages(self) -> list[str]:
        lines = [
            f"Row {row['row']} (CSV line {row['line']}), column {row['column']}: "
            f"{row['value']!r} is {row['problem']}"
            for row in self.problems
        ]
        if self.problem_count > len(self.problems):
            lines.append(
                f"{self.problem_count} cell(s) could not be converted; the first {len(self.problems)} are listed."
            )
        return lines


@dataclass(frozen=True)
class ColumnRule:
    source: str
    target: str
    source_unit: str | None = None
    target_unit: str | None = None


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    version: str
    source_format: str
    canonical_role: str
    canonical_format: str
    columns: Sequence[ColumnRule] = field(default_factory=tuple)
    technology_mapping: Mapping[str, str] = field(default_factory=dict)
    technology_column: str | None = None
    timestamp_column: str | None = None
    source_timezone: str | None = None
    target_timezone: str | None = None
    interval_minutes: int | None = None
    source: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "AdapterSpec":
        columns = tuple(ColumnRule(**dict(item)) for item in value.get("columns", []))
        payload = dict(value)
        payload["columns"] = columns
        return cls(**payload)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterResult:
    source_sha256: str
    normalized_sha256: str
    normalized_path: Path
    rows: int
    columns: Sequence[str]
    transformation_id: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fx_factor(source: Mapping[str, object] | None) -> float:
    """1 / eur_per_gbp of a mapping that converts EUR to GBP; refuses a missing or invalid rate."""

    rate = dict(source or {}).get("eur_per_gbp")
    basis = dict(source or {}).get("fx_basis")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        raise ValueError("EUR/MWh to GBP/MWh requires an explicit positive eur_per_gbp")
    if not isinstance(basis, str) or not basis.strip():
        raise ValueError("EUR/MWh to GBP/MWh requires an fx_basis naming the rate's source")
    return 1.0 / float(rate)


def _convert(value: str, rule: ColumnRule, interval_minutes: int | None = None,
             source: Mapping[str, object] | None = None,
             significant_digits: int | None = None) -> object:
    if not value.strip():
        return None
    if rule.source_unit is None or rule.target_unit is None or rule.source_unit == rule.target_unit:
        return value
    factor = UNIT_FACTORS.get((rule.source_unit, rule.target_unit))
    if (rule.source_unit, rule.target_unit) in FX_CONVERSIONS:
        factor = fx_factor(source)
    if rule.source_unit == "MWh/period" and rule.target_unit == "MW":
        if isinstance(interval_minutes, bool) or not isinstance(interval_minutes, (int, float)) or not math.isfinite(interval_minutes) or interval_minutes <= 0:
            raise ValueError("MWh/period to MW requires an explicit positive interval_minutes")
        factor = 60.0 / interval_minutes
    if factor is None:
        raise ValueError(
            f"Ambiguous unit conversion for {rule.target}: {rule.source_unit} to {rule.target_unit}"
        )
    try:
        number = float(value)
    except ValueError:
        raise CellConversionError("not a number") from None
    converted = number * factor
    if not math.isfinite(converted):
        raise CellConversionError("not finite after conversion")
    if significant_digits is not None:
        # S-D6: a conversion factor such as 1/1.15 leaves binary noise
        # (103.5 EUR -> 90.00000000000001 GBP); round it away at the
        # requested precision (15 significant digits changes a value by at
        # most one part in 10^15).
        converted = float(f"{converted:.{significant_digits}g}")
    return converted


def preview_csv(
    source: Path,
    spec: AdapterSpec,
    *,
    limit: int = 20,
) -> dict[str, object]:
    if limit < 1 or limit > 100:
        raise ValueError("Preview limit must be between 1 and 100 rows")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        source_columns = tuple(reader.fieldnames or ())
        missing = sorted({rule.source for rule in spec.columns}.difference(source_columns))
        if missing:
            raise ValueError("Missing mapped columns: " + ", ".join(missing))
        rows = []
        for raw in reader:
            problems: list[dict[str, object]] = []
            normalized = _convert_row(raw, spec, len(rows) + 1, reader.line_num, problems)
            if problems:
                raise AdapterValueError(problems, len(problems))
            rows.append(normalized)
            if len(rows) >= limit:
                break
    return {
        "schema_version": "value.data-adapter-preview/v1",
        "adapter_id": spec.adapter_id,
        "canonical_role": spec.canonical_role,
        "source_columns": source_columns,
        "canonical_columns": [rule.target for rule in spec.columns],
        "sample": rows,
        "sample_truncated": True,
    }


def _converts(rule: ColumnRule) -> bool:
    return rule.source_unit is not None and rule.target_unit is not None and rule.source_unit != rule.target_unit


def _convert_row(raw: Mapping[str, object], spec: AdapterSpec, row_number: int, line: int,
                 problems: list[dict[str, object]], significant_digits: int | None = None,
                 blanks: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Convert one source row; a cell problem is appended to ``problems`` (S-D7).

    An empty cell of a converted column passes through as empty (the whole-file
    validation reports it); with ``blanks`` it is also noted there, so a file
    rejected for other cells lists it in the same report (L-1).
    """

    normalized: dict[str, object] = {}
    for rule in spec.columns:
        value = str(raw.get(rule.source, ""))
        if blanks is not None and not value.strip() and _converts(rule):
            blanks.append({"row": row_number, "line": line, "column": rule.source, "value": value,
                           "problem": "missing"})
        try:
            normalized[rule.target] = _convert(value, rule, spec.interval_minutes, spec.source, significant_digits)
        except CellConversionError as exc:
            problems.append({"row": row_number, "line": line, "column": rule.source, "value": value,
                             "problem": str(exc)})
            normalized[rule.target] = None
    if spec.technology_column and spec.technology_column in normalized:
        technology = str(normalized[spec.technology_column])
        normalized[spec.technology_column] = spec.technology_mapping.get(technology, technology)
    return normalized


def execute_adapter(source: Path, spec: AdapterSpec, output: Path, *,
                    significant_digits: int | None = None) -> AdapterResult:
    """Normalize ``source`` into ``output``.

    Spec-level problems (unknown conversion, missing rate or interval) raise
    at once.  Cell-level problems are collected over the whole file and
    raised together as :class:`AdapterValueError`, by row and column, and no
    output is written (S-D7).  ``significant_digits`` rounds converted values
    (the mapping editor passes 15, S-D6); the run snapshot does not round.
    """

    if spec.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported adapter schema: {spec.schema_version}")
    if spec.source_format != "csv" or spec.canonical_format != "csv":
        raise ValueError("This release implements explicit CSV-to-CSV normalization only")
    if significant_digits is not None and (isinstance(significant_digits, bool) or not isinstance(significant_digits, int)
                                           or not 1 <= significant_digits <= 17):
        raise ValueError("significant_digits must be an integer between 1 and 17")
    try:
        preview_csv(source, spec, limit=1)
    except AdapterValueError:
        pass  # reported with every other cell problem below
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    rows = 0
    problems: list[dict[str, object]] = []
    problem_count = 0
    # L-1 (four-role R1 retest): empty cells of converted columns, listed with
    # the other cell problems when the file is rejected for those.
    blanks: list[dict[str, object]] = []
    blank_count = 0
    targets = [rule.target for rule in spec.columns]
    if len(set(targets)) != len(targets):
        raise ValueError("Canonical adapter target columns must be unique")
    with source.open("r", encoding="utf-8-sig", newline="") as source_handle, temporary.open(
        "w", encoding="utf-8", newline=""
    ) as output_handle:
        reader = csv.DictReader(source_handle)
        writer = csv.DictWriter(output_handle, fieldnames=targets, lineterminator="\n")
        writer.writeheader()
        for raw in reader:
            found: list[dict[str, object]] = []
            empty: list[dict[str, object]] = []
            normalized = _convert_row(raw, spec, rows + 1, reader.line_num, found, significant_digits, empty)
            problem_count += len(found)
            blank_count += len(empty)
            problems.extend(found[:max(0, MAX_LISTED_CELL_PROBLEMS - len(problems))])
            blanks.extend(empty[:max(0, MAX_LISTED_CELL_PROBLEMS - len(blanks))])
            writer.writerow(normalized)
            rows += 1
    if problem_count:
        temporary.unlink(missing_ok=True)
        listed = sorted(problems + blanks, key=lambda item: (int(item["row"]), str(item["column"])))
        raise AdapterValueError(listed[:MAX_LISTED_CELL_PROBLEMS], problem_count + blank_count)
    temporary.replace(output)
    return AdapterResult(
        sha256_file(source),
        sha256_file(output),
        output,
        rows,
        targets,
        f"{spec.adapter_id}@{spec.version}",
    )

