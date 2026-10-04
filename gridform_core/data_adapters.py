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


def _convert(value: str, rule: ColumnRule, interval_minutes: int | None = None) -> object:
    if not value.strip():
        return None
    if rule.source_unit is None or rule.target_unit is None or rule.source_unit == rule.target_unit:
        return value
    factor = UNIT_FACTORS.get((rule.source_unit, rule.target_unit))
    if rule.source_unit == "MWh/period" and rule.target_unit == "MW":
        if isinstance(interval_minutes, bool) or not isinstance(interval_minutes, (int, float)) or not math.isfinite(interval_minutes) or interval_minutes <= 0:
            raise ValueError("MWh/period to MW requires an explicit positive interval_minutes")
        factor = 60.0 / interval_minutes
    if factor is None:
        raise ValueError(
            f"Ambiguous unit conversion for {rule.target}: {rule.source_unit} to {rule.target_unit}"
        )
    number = float(value)
    converted = number * factor
    if not math.isfinite(converted):
        raise ValueError(f"Non-finite value in {rule.source}")
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
            normalized = {rule.target: _convert(str(raw.get(rule.source, "")), rule, spec.interval_minutes) for rule in spec.columns}
            if spec.technology_column and spec.technology_column in normalized:
                raw_technology = str(normalized[spec.technology_column])
                normalized[spec.technology_column] = spec.technology_mapping.get(
                    raw_technology, raw_technology
                )
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


def execute_adapter(source: Path, spec: AdapterSpec, output: Path) -> AdapterResult:
    if spec.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported adapter schema: {spec.schema_version}")
    if spec.source_format != "csv" or spec.canonical_format != "csv":
        raise ValueError("This release implements explicit CSV-to-CSV normalization only")
    preview_csv(source, spec, limit=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    rows = 0
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
            normalized = {rule.target: _convert(str(raw.get(rule.source, "")), rule, spec.interval_minutes) for rule in spec.columns}
            if spec.technology_column and spec.technology_column in normalized:
                technology = str(normalized[spec.technology_column])
                normalized[spec.technology_column] = spec.technology_mapping.get(technology, technology)
            writer.writerow(normalized)
            rows += 1
    temporary.replace(output)
    return AdapterResult(
        sha256_file(source),
        sha256_file(output),
        output,
        rows,
        targets,
        f"{spec.adapter_id}@{spec.version}",
    )

