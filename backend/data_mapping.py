"""Reviewed CSV normalization into independent BASE packs; no model execution."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import time
from itertools import islice
from typing import Callable, Mapping, Sequence
import uuid
from datetime import datetime, timezone

from backend.data_pack_clone import SAFE_ID, guard_clone_upload
from gridform_core.data_adapters import (
    AdapterSpec, AdapterValueError, ColumnRule, FX_CONVERSIONS, MAX_LISTED_CELL_PROBLEMS, UNIT_FACTORS,
    execute_adapter, fx_factor,
)
from gridform_core.data_contract_templates import CSV_TEMPLATES, runtime_supported_formats
from gridform_core.data_import import promote_binding_revision
from gridform_core.data_pack_validation import (
    CYCLIC_MARKET_ROLES, DEMAND_ROLES, VRE_PROFILE_ROLES, REQUIRED_CSV_COLUMNS,
    demand_annual_energy_mwh, demand_scale_warning, legacy_demand_unit, validate_data_pack,
)
from gridform_core.data_validation_layers import (
    TIMESTAMP_DATE_ORDERS, TIMESTAMP_TIME_ZONES, timestamp_row_problems,
)
from gridform_core.series_reader import LENIENT, SeriesReadError, SeriesSpec, clock_alignment, period_span_text

MAX_UPLOAD_BYTES = 32 * 1024 * 1024
TOKEN = re.compile(r"^[0-9a-f]{32}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
FIELD_UNITS = {
    "projects.repd": {"capacity_mw": "MW"},
    "source.repd_raw": {"Installed Capacity (MWelec)": "MW"},
    "value.network.nodal-demand": {"demand_mwh": "MWh"},
    "value.network.ac.active-schedule": {"active_schedule_mwh": "MWh"},
    "value.network.ac.reactive-demand": {"reactive_demand_mvar": "MVAr"},
    "value.hydrology.site-catalogue": {"capacity_mw": "MW"},
}


MARKET_PROFILE_ROLES = {role for role in CYCLIC_MARKET_ROLES if role.endswith(".profile")}
MARKET_PRICE_ROLES = {role for role in CYCLIC_MARKET_ROLES if role.endswith(".price")}
# Roles whose MWh/period source converts to MW with the declared 30-minute interval.
PER_PERIOD_ENERGY_ROLES = DEMAND_ROLES | MARKET_PROFILE_ROLES
# Single-value time series that may declare a timestamp column (spec 11.6, S-D4).
TIME_SERIES_ROLES = DEMAND_ROLES | CYCLIC_MARKET_ROLES | VRE_PROFILE_ROLES


# The price-year range of the mapping editor (app/features/data/csvMappingFx.ts).
PRICE_YEAR_RANGE = (1990, 2100)
# S-低6: the FX bases the mapping editor offers (csvMappingFx.ts FX_BASES); the
# API accepts the same three and nothing else.
FX_BASES = ("annual average", "monthly average", "fixed rate")
# S-低6: the price base of the model's cost parameters (constant 2025 GBP,
# decisions A6 and A24-4; the restart table's price_base.to_year and the
# storage catalogue's currency_base_year).  A mapped price is converted in
# currency only, never re-indexed to another year.
MODEL_PRICE_BASE_YEAR = 2025
# The model year a mapped series fills (half-hour periods of the 365-day UTC clock).
MODEL_YEAR_PERIODS = 17_520
# S-低2: a series shorter than a model year is repeated from its start; the
# commit needs this acknowledgement.
SHORT_SERIES_ACKNOWLEDGEMENT = "GF_DATA_SHORT_SERIES_REPEAT"
# S-F-中3 (R5): row counts of an hourly year without timestamps (the same rule
# the series reader applies to an undeclared interval).
HOURLY_YEAR_ROWS = (8760, 8784)


def _fx(value: object) -> dict[str, object] | None:
    """The explicit EUR->GBP rate of a mapping request (P0-5a S10); None when absent."""

    if value is None:
        return None
    if not isinstance(value, dict) or not {"eur_per_gbp", "fx_basis"} <= set(value) <= {"eur_per_gbp", "fx_basis", "price_year"}:
        raise DataMappingError("GF_MAPPING_FX", "fx must be {eur_per_gbp, fx_basis[, price_year]}.")
    try:
        fx_factor(value)
    except ValueError as exc:
        raise DataMappingError("GF_MAPPING_FX", str(exc)) from exc
    if str(value["fx_basis"]).strip() not in FX_BASES:
        raise DataMappingError("GF_MAPPING_FX", f"fx_basis must be one of: {', '.join(FX_BASES)}.")
    year = value.get("price_year")
    if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
        raise DataMappingError("GF_MAPPING_FX", "price_year must be an integer year.")
    # L-5 (four-role R1 retest): the same range the mapping editor enforces.
    if year is not None and not PRICE_YEAR_RANGE[0] <= year <= PRICE_YEAR_RANGE[1]:
        raise DataMappingError(
            "GF_MAPPING_FX", f"price_year must be between {PRICE_YEAR_RANGE[0]} and {PRICE_YEAR_RANGE[1]}."
        )
    return {"eur_per_gbp": float(value["eur_per_gbp"]), "fx_basis": str(value["fx_basis"]).strip(),
            **({"price_year": year} if year is not None else {})}


def _timestamp(value: object, source_columns: Sequence[str], mapped: Sequence[str], role: str) -> dict[str, str] | None:
    """The declared timestamp column of a mapping request (spec 11.6, S-D4); None when absent.

    ``date_order`` (S-中3) is optional: auto, day_first or month_first.
    """

    if value is None:
        return None
    if role not in TIME_SERIES_ROLES:
        raise DataMappingError("GF_MAPPING_TIMESTAMP", "Only half-hourly or hourly series roles take a timestamp column.")
    if not isinstance(value, dict) or not {"column", "time_zone"} <= set(value) <= {"column", "time_zone", "date_order"}:
        raise DataMappingError("GF_MAPPING_TIMESTAMP", "timestamp must be {column, time_zone[, date_order]}.")
    column, zone = value["column"], value["time_zone"]
    if not isinstance(column, str) or column not in source_columns:
        raise DataMappingError("GF_MAPPING_TIMESTAMP", "Choose a timestamp column from the uploaded file.")
    if column in mapped:
        raise DataMappingError("GF_MAPPING_TIMESTAMP", "The timestamp column cannot also be a mapped value column.")
    if zone not in TIMESTAMP_TIME_ZONES:
        raise DataMappingError("GF_MAPPING_TIMESTAMP", f"time_zone must be one of {', '.join(TIMESTAMP_TIME_ZONES)}.")
    order = value.get("date_order", "auto")
    if order not in TIMESTAMP_DATE_ORDERS:
        raise DataMappingError("GF_MAPPING_TIMESTAMP", f"date_order must be one of {', '.join(TIMESTAMP_DATE_ORDERS)}.")
    return {"column": column, "time_zone": zone, "date_order": order}


def _demand_source_interval(role: str, source: Path, rows: int, timestamp: Mapping[str, str] | None) -> int:
    """30 or 60: the period of a demand source (S-F-中3); other roles are never expanded.

    With a declared timestamp column the most common step decides (the same
    inference as the timestamp check); without one an hourly year is 8,760
    or 8,784 rows.
    """

    if role not in DEMAND_ROLES:
        return 30
    if timestamp is not None:
        try:
            report = timestamp_row_problems(source, timestamp["column"], None, time_zone=timestamp["time_zone"],
                                            date_order=timestamp["date_order"], limit=1)
        except (ValueError, OSError, KeyError):
            return 30
        return 60 if report.get("interval_minutes") == 60 else 30
    return 60 if rows in HOURLY_YEAR_ROWS else 30


def _replaced_demand_warning(target_root: Path, manifest: Mapping[str, object], role: str,
                             normalized: Path, binding: Mapping[str, object]) -> list[str]:
    """GF_DATA_DEMAND_SCALE of a mapped demand series against the target pack's current file (S-F-高1)."""

    current = (manifest.get("bindings") or {}).get(role) if isinstance(manifest.get("bindings"), Mapping) else None
    if not isinstance(current, Mapping) or not current.get("uri"):
        return []
    path = (target_root / str(current["uri"])).resolve()
    try:
        path.relative_to(target_root.resolve())
    except ValueError:
        return []
    relabel = legacy_demand_unit(role, current)
    reference = "the file it replaces in this pack" + (
        ", which is read as MW although its header says mwh and its label MWh/period" if relabel else "")
    warning = demand_scale_warning(role, demand_annual_energy_mwh(normalized, binding),
                                   demand_annual_energy_mwh(path, current), reference)
    return [warning] if warning else []


def _model_start_year(value: object) -> int | None:
    """The first model year of the Study the mapping is for (optional, S-低2)."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not PRICE_YEAR_RANGE[0] <= value <= PRICE_YEAR_RANGE[1]:
        raise DataMappingError("GF_MAPPING_REQUEST", "model_start_year must be a year.")
    return value


def _clock_plan(role: str, binding: Mapping[str, object], rows: int):
    """What the corrected reader's clock does with this many rows (S-中2, S-低2); None for non-series roles."""

    if role not in TIME_SERIES_ROLES:
        return None
    try:
        spec = SeriesSpec.from_binding(role, dict(binding))
    except SeriesReadError:
        return None
    return clock_alignment(rows, MODEL_YEAR_PERIODS, spec, strictness=LENIENT,
                           cyclic_default=role in CYCLIC_MARKET_ROLES)


class DataMappingError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(message)


# S-D6: converted values are rounded to this many significant digits, so a
# factor such as 1/1.15 does not write binary noise (90.00000000000001) into
# the canonical file.  The preview and the commit's rebuild use the same
# setting; the run snapshot never re-converts a mapped file.
MAPPED_VALUE_SIGNIFICANT_DIGITS = 15


def _cell_problems(normalized: bytes, column: str, source_column: str, *,
                   negative_invalid: bool = False, repeat_rows: int = 1) -> tuple[list[str], int]:
    """S-D7: rows of a single-value series whose cell is missing or not a finite number.

    With ``negative_invalid`` (demand roles, L-3) negative values are listed too.
    """

    listed: list[str] = []
    count = 0
    reader = csv.DictReader(io.StringIO(normalized.decode("utf-8")))
    for index, row in enumerate(reader):
        if index % repeat_rows:
            continue  # S-F-中3: a repeated (hourly -> half-hour) copy of the row above
        row_number = index // repeat_rows + 1
        value = str(row.get(column) or "")
        try:
            number = float(value)
            problem = (
                "not a finite number" if not math.isfinite(number)
                else "negative" if negative_invalid and number < 0
                else None
            )
        except ValueError:
            problem = "missing" if not value.strip() else "not a number"
        if problem is None:
            continue
        count += 1
        if len(listed) < MAX_LISTED_CELL_PROBLEMS:
            listed.append(f"Row {row_number} (CSV line {row_number + 1}), column {source_column}: {value!r} is {problem}")
    if count > len(listed):
        listed.append(f"{count} cell(s) are missing or not numbers"
                      + (" or negative" if negative_invalid else "")
                      + f"; the first {len(listed)} are listed.")
    return listed, count


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _write(path: Path, payload: object) -> None:
    path.write_bytes(_canonical(payload))


def _bytes(path: Path, root: Path) -> bytes:
    current = path
    path.absolute().relative_to(root.absolute())
    while current != root.parent:
        if current.is_symlink():
            raise DataMappingError("GF_MAPPING_UNSAFE_FILE", "Mapping files must not contain symbolic links.")
        current = current.parent
    if not path.is_file() or path.stat().st_nlink != 1:
        raise DataMappingError("GF_MAPPING_UNSAFE_FILE", "Mapping files must be independent regular files.")
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise DataMappingError("GF_MAPPING_SIZE", "CSV or mapping metadata exceeds 32 MiB.", 413)
    return path.read_bytes()


def _shape(raw: bytes) -> tuple[list[str], int]:
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise DataMappingError("GF_MAPPING_SIZE", "Provide a nonempty CSV no larger than 32 MiB.", 413)
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("NUL characters are not allowed")
        first_line = text.split("\n", 1)[0]
        for delimiter, name in ((";", "semicolon"), ("\t", "tab")):
            if delimiter in first_line and "," not in first_line:
                # S-低1: a semicolon export (often with decimal commas) or a
                # TSV is not read as one wide column or a width error.
                raise DataMappingError(
                    "GF_MAPPING_CSV",
                    f"This file looks {name}-separated: its header has {name}s and no commas. VALUE reads "
                    "comma-separated CSV with a decimal point (1234.5). Save the file as comma-separated "
                    "CSV (UTF-8) with decimal points and upload it again.")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if not header or any(not value.strip() for value in header) or len(set(header)) != len(header):
            raise ValueError("CSV requires a nonempty, unique header")
        rows = 0
        for row in reader:
            if len(row) != len(header):
                raise ValueError(f"CSV row {reader.line_num} does not match the header width")
            rows += 1
        if not rows:
            raise ValueError("CSV must contain data rows")
        return header, rows
    except DataMappingError:
        raise
    except (UnicodeError, csv.Error, ValueError, StopIteration) as exc:
        raise DataMappingError("GF_MAPPING_CSV", f"Invalid UTF-8 CSV: {exc}") from exc


def _reading_metadata(role: str) -> dict[str, object]:
    """How a mapped canonical file is read: the declarations the commit writes into the binding."""

    single = role in DEMAND_ROLES | CYCLIC_MARKET_ROLES | VRE_PROFILE_ROLES
    return {
        **({"input_unit_contract": "value.demand-mw-half-hour/v1", "interval_minutes": 30}
           if role in DEMAND_ROLES else {}),
        **({"csv_header": True, "csv_column": "value"} if single else {}),
        **({"interval_minutes": 30} if role in MARKET_PROFILE_ROLES else {}),
    }


def _coverage_warnings(report: Mapping[str, object], clock: Mapping[str, object] | None,
                       model_start_year: int | None) -> list[str]:
    """Coverage and data-year notes of a declared timestamp column (S-低2, report section 7.3)."""

    warnings: list[str] = []
    coverage = report.get("coverage")
    if not isinstance(coverage, Mapping):
        return warnings
    if clock and int(clock.get("wrapped_periods") or 0) > 0:
        warnings.append(
            f"GF_DATA_TIMESTAMP_COVERAGE: the timestamps run from {report.get('first_utc')} to "
            f"{report.get('last_utc')} ({coverage['span_days']} days), less than a model year. "
            f"{clock.get('note') or ''} Confirm this below before committing.".strip())
    years = [int(year) for year in coverage.get("data_years") or []]
    if model_start_year is not None and years and model_start_year not in years:
        warnings.append(
            f"GF_DATA_TIMESTAMP_YEAR: the timestamps are in {', '.join(str(year) for year in years)}; the Study's "
            f"first model year is {model_start_year}. VALUE reads the series in row order as the model year "
            "(1 January 00:00 UTC onwards) and reuses it for each model year; it does not move dates, weekdays "
            "or holidays between years.")
    return warnings


class DataMappingService:
    def __init__(self, *, packs_root: Path, staging_root: Path, projects_root: Path,
                 trash_root: Path, dataset_slots: Sequence[Mapping[str, object]],
                 lifecycle_lock: object, ttl_seconds: int = 1800,
                 busy_packs: Callable[[], frozenset[str]] | None = None):
        self.packs_root, self.staging_root = Path(packs_root).absolute(), Path(staging_root).absolute()
        # A24-5: packs whose files a Run preparation is copying right now; a
        # commit to one of them is refused instead of racing the snapshot.
        self.busy_packs = busy_packs or (lambda: frozenset())
        self.projects_root, self.trash_root = Path(projects_root), Path(trash_root)
        self.slots = {str(slot["role"]): dict(slot) for slot in dataset_slots}
        self.lock, self.ttl_seconds = lifecycle_lock, ttl_seconds

    def _target(self, pack_id: str, expected: str | None = None):
        if not isinstance(pack_id, str) or not SAFE_ID.fullmatch(pack_id):
            raise DataMappingError("GF_MAPPING_PACK", "Invalid data-pack identity.")
        root = self.packs_root / pack_id
        path = root / "manifest.json"
        raw = _bytes(path, self.packs_root)
        manifest = json.loads(raw)
        if (not isinstance(manifest, dict) or manifest.get("id") != pack_id
                or manifest.get("schema_version") != "value.data-pack/v1"
                or not isinstance(manifest.get("copy_origin"), dict)
                or manifest["copy_origin"].get("schema_version") != "value.data-pack-copy/v1"
                or manifest.get("data_pack_type") == "network_overlay" or manifest.get("network_overlay")):
            raise DataMappingError("GF_MAPPING_BASE_COPY_ONLY", "Copy a BASE pack before mapping; network overlays are not supported.", 409)
        digest = _hash(raw)
        if expected is not None and digest != expected:
            raise DataMappingError("GF_MAPPING_STALE_TARGET", "The target pack changed; stage and review again.", 409)
        guard_clone_upload(manifest, path, digest, self.projects_root, self.trash_root)
        return root, manifest, digest

    def _role(self, role: str) -> dict[str, object]:
        slot = self.slots.get(role)
        if not slot or "csv" not in runtime_supported_formats(role, tuple(slot.get("formats") or ())):
            raise DataMappingError("GF_MAPPING_ROLE", "Select a declared role with a shipped CSV parser.")
        single = role in DEMAND_ROLES | CYCLIC_MARKET_ROLES | VRE_PROFILE_ROLES
        if single:
            columns = [{"target": "value", "target_unit": slot.get("unit")}]
        elif role in CSV_TEMPLATES or role in REQUIRED_CSV_COLUMNS:
            header = CSV_TEMPLATES[role][0] if role in CSV_TEMPLATES else sorted(REQUIRED_CSV_COLUMNS[role])
            columns = [{"target": column, "target_unit": FIELD_UNITS.get(role, {}).get(column)} for column in header]
        else:
            raise DataMappingError("GF_MAPPING_ROLE", "This CSV role has no explicit canonical column contract.")
        demand = role in DEMAND_ROLES
        per_period = role in PER_PERIOD_ENERGY_ROLES
        price = role in MARKET_PRICE_ROLES
        return {"role": role, "columns": columns, "single_value": single,
                **({"interval_minutes": 30, "unit_contract": "value.demand-mw-half-hour/v1"} if demand else {}),
                **({"interval_minutes": 30} if role in MARKET_PROFILE_ROLES else {}),
                **({"fx_required_for": ["EUR/MWh"]} if price else {}),
                **({"timestamp_supported": True, "time_zones": list(TIMESTAMP_TIME_ZONES)} if role in TIME_SERIES_ROLES else {}),
                "conversion_pairs": [{"source_unit": source, "target_unit": target,
                                      **({"requires_fx": True} if (source, target) in FX_CONVERSIONS else {})}
                    for source, target in sorted(set(UNIT_FACTORS) | ({("MWh/period", "MW")} if per_period else set())
                                                 | (set(FX_CONVERSIONS) if price else set()) | {
                        (column["target_unit"], column["target_unit"]) for column in columns if column["target_unit"] is not None
                    }) if target in {column["target_unit"] for column in columns}]}

    def catalog(self, pack_id: str) -> dict[str, object]:
        with self.lock:
            _, _, digest = self._target(pack_id)
            roles = []
            for role in self.slots:
                try:
                    roles.append(self._role(role))
                except DataMappingError:
                    continue
            return {"schema_version": "value.data-mapping-catalog/v1", "pack_id": pack_id,
                    "target_manifest_sha256": digest, "roles": roles, "max_upload_bytes": MAX_UPLOAD_BYTES}

    def _new(self, kind: str) -> tuple[str, Path]:
        token = uuid.uuid4().hex
        root = self.staging_root / kind
        root.mkdir(parents=True, exist_ok=True)
        directory = root / token
        directory.mkdir()
        return token, directory

    def _load(self, kind: str, token: str):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise DataMappingError("GF_MAPPING_TOKEN", "Invalid mapping token.", 404)
        directory = self.staging_root / kind / token
        try:
            metadata = json.loads(_bytes(directory / "metadata.json", self.staging_root))
        except FileNotFoundError as exc:
            raise DataMappingError("GF_MAPPING_TOKEN", "Mapping review is unavailable; upload again.", 404) from exc
        if not isinstance(metadata, dict) or metadata.get("token") != token:
            raise DataMappingError("GF_MAPPING_IDENTITY", "Mapping metadata identity is inconsistent.", 409)
        expires = metadata.get("expires_epoch")
        if isinstance(expires, bool) or not isinstance(expires, (float, int)) or not math.isfinite(expires) or time.time() >= expires:
            raise DataMappingError("GF_MAPPING_EXPIRED", "Mapping review expired; upload and review again.", 409)
        return directory, metadata

    def stage(self, pack_id: str, role: str, raw: bytes, filename: str,
              expected_manifest_sha256: str) -> dict[str, object]:
        if not isinstance(expected_manifest_sha256, str) or not SHA.fullmatch(expected_manifest_sha256):
            raise DataMappingError("GF_MAPPING_IDENTITY", "Provide the exact target manifest checksum.")
        columns, rows = _shape(raw)
        if not isinstance(filename, str) or not filename.lower().endswith(".csv"):
            raise DataMappingError("GF_MAPPING_CSV", "Upload a .csv file.")
        with self.lock:
            self._role(role)
            _, _, digest = self._target(pack_id, expected_manifest_sha256)
            token, directory = self._new("stages")
            expires = time.time() + self.ttl_seconds
            report = {"schema_version": "value.data-mapping-stage/v1", "stage_id": token,
                      "pack_id": pack_id, "role": role, "source_sha256": _hash(raw), "source_bytes": len(raw),
                      "source_columns": columns, "rows": rows, "target_manifest_sha256": digest, "expires_at": _iso(expires)}
            try:
                (directory / "source.csv").write_bytes(raw)
                _write(directory / "metadata.json", {**report, "token": token, "expires_epoch": expires})
            except Exception:
                shutil.rmtree(directory)
                raise
            return report

    def _spec(self, role: str, columns: object, source_columns: list[str],
              fx: Mapping[str, object] | None = None, source_interval_minutes: int = 30) -> AdapterSpec:
        if source_interval_minutes not in (30, 60) or (source_interval_minutes == 60 and role not in DEMAND_ROLES):
            raise DataMappingError("GF_MAPPING_INTERVAL", "Only demand series are expanded from hourly to half-hourly rows.")
        contract = self._role(role)
        targets = {column["target"]: column["target_unit"] for column in contract["columns"]}
        if not isinstance(columns, list) or len(columns) != len(targets):
            raise DataMappingError("GF_MAPPING_COLUMNS", "Map every canonical column exactly once.")
        rules = {}
        for item in columns:
            if not isinstance(item, dict) or set(item) != {"source", "target", "source_unit", "target_unit"}:
                raise DataMappingError("GF_MAPPING_COLUMNS", "Use explicit column and unit mappings only.")
            source, target = item["source"], item["target"]
            if not isinstance(source, str) or source not in source_columns or not isinstance(target, str) or target not in targets or target in rules:
                raise DataMappingError("GF_MAPPING_COLUMNS", "Unknown source/target column or repeated target.")
            source_unit, target_unit = item["source_unit"], item["target_unit"]
            if target_unit != targets[target] or (source_unit is not None and not isinstance(source_unit, str)):
                raise DataMappingError("GF_MAPPING_UNITS", "Target units must match the canonical field contract.")
            if target_unit is None:
                if source_unit is not None:
                    raise DataMappingError("GF_MAPPING_UNITS", "This field has no declared unit conversion.")
            elif (source_unit, target_unit) in FX_CONVERSIONS and role in MARKET_PRICE_ROLES:
                if fx is None:
                    raise DataMappingError("GF_MAPPING_FX", "EUR prices need an explicit eur_per_gbp and fx_basis.")
            elif source_unit is None or (source_unit != target_unit and (source_unit, target_unit) not in UNIT_FACTORS
                    and not (role in PER_PERIOD_ENERGY_ROLES and source_unit == "MWh/period" and target_unit == "MW")):
                raise DataMappingError("GF_MAPPING_UNITS", "Select an explicit supported source unit.")
            rules[target] = ColumnRule(source, target, source_unit, target_unit)
        uses_fx = any((rule.source_unit, rule.target_unit) in FX_CONVERSIONS for rule in rules.values())
        if fx is not None and not uses_fx:
            raise DataMappingError("GF_MAPPING_FX", "fx is only accepted for an EUR/MWh price column.")
        # S-F-中3 (R5): an hourly demand series converts MWh/period with the
        # 60-minute source period and is written as two half-hour rows per
        # hour (the same MW), so the canonical file is half-hourly.
        hourly = source_interval_minutes == 60
        return AdapterSpec("value.explicit-column-mapping", "2" if role in DEMAND_ROLES else "1", "csv", role, "csv",
                           tuple(rules[column["target"]] for column in contract["columns"]),
                           interval_minutes=(60 if hourly else 30) if role in PER_PERIOD_ENERGY_ROLES else None,
                           source=dict(fx or {}), repeat_rows=2 if hourly else 1)

    def preview(self, stage_id: str, request: Mapping[str, object]) -> dict[str, object]:
        base_fields = {"schema_version", "source_sha256", "target_manifest_sha256", "columns"}
        if not (base_fields <= set(request) <= base_fields | {"fx", "timestamp", "model_start_year"}) or request.get("schema_version") != "value.data-mapping-preview-request/v1":
            raise DataMappingError("GF_MAPPING_REQUEST", "Invalid mapping preview request.")
        fx = _fx(request.get("fx"))
        model_start_year = _model_start_year(request.get("model_start_year"))
        stage_dir, stage = self._load("stages", stage_id)
        raw = _bytes(stage_dir / "source.csv", self.staging_root)
        columns, rows = _shape(raw)
        if _hash(raw) != stage["source_sha256"] or request["source_sha256"] != stage["source_sha256"] or request["target_manifest_sha256"] != stage["target_manifest_sha256"]:
            raise DataMappingError("GF_MAPPING_IDENTITY", "Source or target identity changed; upload again.", 409)
        spec = self._spec(stage["role"], request["columns"], columns, fx)
        timestamp = _timestamp(request.get("timestamp"), columns, [rule.source for rule in spec.columns], stage["role"])
        if _demand_source_interval(stage["role"], stage_dir / "source.csv", rows, timestamp) == 60:
            spec = self._spec(stage["role"], request["columns"], columns, fx, source_interval_minutes=60)
        with self.lock:
            target_root, manifest, _ = self._target(stage["pack_id"], stage["target_manifest_sha256"])
            token, directory = self._new("reviews")
            _write(directory / "spec.json", spec.to_dict())
            errors = []
            validation = None
            sample = []
            source_sample: list[dict[str, object]] = []
            timestamp_report: dict[str, object] | None = None
            timestamp_warnings: list[str] = []
            acknowledgements: list[dict[str, str]] = []
            clock: dict[str, object] | None = None
            digest = None
            size = 0
            try:
                result = execute_adapter(stage_dir / "source.csv", spec, directory / "normalized.csv",
                                         significant_digits=MAPPED_VALUE_SIGNIFICANT_DIGITS)
                normalized = _bytes(directory / "normalized.csv", self.staging_root)
                _shape(normalized)
                digest, size = _hash(normalized), len(normalized)
                candidate = copy.deepcopy(manifest)
                # S-中2: validate the binding the commit will write (its declared
                # interval and column), so the clock note matches the run.
                candidate_binding = {"uri": "normalized.csv", "format": "csv", "sha256": digest,
                                     "unit": self.slots[stage["role"]].get("unit"),
                                     **_reading_metadata(stage["role"])}
                candidate["bindings"] = {stage["role"]: candidate_binding}
                report = validate_data_pack(directory, candidate, [self.slots[stage["role"]]])
                validation = report["bindings"][0]
                plan = _clock_plan(stage["role"], candidate_binding, rows * spec.repeat_rows)
                if spec.repeat_rows == 2:
                    timestamp_warnings.append(
                        f"GF_MAPPING_HOURLY_DEMAND: the file has hourly rows ({rows:,} hours). Each hour's demand is "
                        f"used for two half-hour periods at the same MW, giving {rows * 2:,} half-hour periods"
                        + ("; MWh/period values are per hour and are converted to MW with a 60-minute period"
                           if any(rule.source_unit == "MWh/period" for rule in spec.columns) else "")
                        + ". The original hourly file is kept with the mapping.")
                if plan is not None:
                    clock = {"source_rows": plan.source_rows, "periods": plan.periods,
                             "hourly_doubled": plan.hourly_doubled, "leap_day_removed": plan.leap_day_removed,
                             "ignored_periods": plan.ignored_periods, "wrapped_periods": plan.wrapped_periods,
                             "note": plan.describe()}
                    if plan.short_of_a_year:
                        acknowledgements.append({
                            "code": SHORT_SERIES_ACKNOWLEDGEMENT,
                            "text": (f"The series covers {plan.used_periods:,} of the {plan.periods:,} half-hour "
                                     f"periods of a model year; the last "
                                     f"{period_span_text(plan.wrapped_periods, plan.period_hours)} will repeat "
                                     "the series from its start."),
                        })
                errors = list(validation["errors"])
                if not errors and stage["role"] in DEMAND_ROLES:
                    # S-F-高1 (R5): compare the annual energy with the file it replaces.
                    timestamp_warnings.extend(_replaced_demand_warning(
                        target_root, manifest, stage["role"], directory / "normalized.csv", candidate_binding))
                if errors and [rule.target for rule in spec.columns] == ["value"]:
                    # S-D7: the whole-file check counts bad cells; name the rows.
                    errors.extend(_cell_problems(normalized, "value", spec.columns[0].source,
                                                 negative_invalid=stage["role"] in DEMAND_ROLES,
                                                 repeat_rows=spec.repeat_rows)[0])
                sample = list(islice(csv.DictReader(io.StringIO(normalized.decode("utf-8"))), 20))
                # F-P05A-1: the raw values of the mapped source columns for the same
                # rows, so the UI shows the original EUR price beside the converted one.
                mapped = [rule.source for rule in spec.columns]
                source_sample = [
                    {name: row.get(name) for name in mapped}
                    for row in islice(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))), 20)
                ]
                if result.source_sha256 != stage["source_sha256"]:
                    raise DataMappingError("GF_MAPPING_IDENTITY", "Source changed during normalization.", 409)
                if timestamp is not None:
                    # Spec 11.6 (S-D4): the chronology layer checks the declared
                    # timestamps row by row; any problem blocks the commit.
                    timestamp_report = {**timestamp_row_problems(
                        stage_dir / "source.csv", timestamp["column"], spec.interval_minutes,
                        time_zone=timestamp["time_zone"], date_order=timestamp["date_order"]),
                        "source_sha256": stage["source_sha256"]}
                    if timestamp_report["problem_count"]:
                        errors.append(
                            f"GF_DATA_TIMESTAMPS: {timestamp_report['problem_count']} timestamp problem(s) in column "
                            f"{timestamp['column']} ({timestamp['time_zone']}); the rows are listed below.")
                    # N-3: the model reads row 1 as 1 January 00:00; a shifted series
                    # passes the row checks, so say so (a warning: the spec's checks
                    # are monotonicity, gaps and duplicates).
                    offset = timestamp_report.get("origin_offset_minutes")
                    if offset:
                        timestamp_warnings.append(
                            f"GF_DATA_TIMESTAMP_ORIGIN: the first timestamp {timestamp_report['first_utc']} is "
                            f"{abs(offset)} minutes {'after' if offset > 0 else 'before'} 1 January 00:00; the model "
                            "reads row 1 as the first period of the year, so the series would be shifted.")
                    timestamp_warnings.extend(_coverage_warnings(timestamp_report, clock, model_start_year))
            except AdapterValueError as exc:
                # S-D7: every unconvertible cell by row and column, not the
                # first Python exception.
                errors = exc.messages()
            except (ValueError, OSError) as exc:
                errors = [str(exc)]
            if fx and fx.get("price_year") is not None and fx["price_year"] != MODEL_PRICE_BASE_YEAR:
                timestamp_warnings.append(
                    f"GF_MAPPING_PRICE_YEAR: the prices are declared in {fx['price_year']} money. VALUE converts the "
                    "currency only; it does not re-index prices to another year. The model's other costs are in "
                    f"constant {MODEL_PRICE_BASE_YEAR} GBP, so these prices enter the model as {fx['price_year']} "
                    "prices.")
            if validation is not None and timestamp_report is not None:
                # S-低4: the whole-file report includes the timestamp check, so it
                # never says "passed" beside a failed timestamp check.
                problems = int(timestamp_report["problem_count"])
                validation = {**validation, "timestamp_check": {
                    "status": "failed" if problems else "passed", "problem_count": problems,
                    "column": timestamp_report["column"], "time_zone": timestamp_report["time_zone"]}}
                if problems:
                    validation["status"] = "failed"
                    validation["errors"] = [*list(validation.get("errors") or []),
                                            f"GF_DATA_TIMESTAMPS: {problems} timestamp problem(s); see the timestamp table"]
            expires = stage["expires_epoch"]
            review = {"schema_version": "value.data-mapping-review/v1", "review_id": token, "stage_id": stage_id,
                      "pack_id": stage["pack_id"], "role": stage["role"], "valid": not errors and validation is not None,
                      "errors": errors, "warnings": (list(validation["warnings"]) if validation else []) + timestamp_warnings,
                      "source_sha256": stage["source_sha256"], "spec_sha256": _hash(_canonical(spec.to_dict())),
                      "normalized_sha256": digest, "target_manifest_sha256": stage["target_manifest_sha256"],
                      "source_bytes": len(raw), "normalized_bytes": size, "rows": rows,
                      "columns": spec.to_dict()["columns"], "sample_rows": sample, "validation": validation,
                      "source_sample_rows": source_sample, "fx": dict(fx) if fx else None,
                      "interval_minutes": spec.interval_minutes,
                      "source_interval_minutes": 60 if spec.repeat_rows == 2 else None,
                      "timestamp": timestamp_report,
                      "clock": clock,
                      "acknowledgements_required": acknowledgements,
                      "expires_at": _iso(expires)}
            _write(directory / "metadata.json", {**review, "token": token, "expires_epoch": expires})
            return review

    def commit(self, review_id: str, request: Mapping[str, object]) -> dict[str, object]:
        expected_fields = {"schema_version", "source_sha256", "spec_sha256", "normalized_sha256", "target_manifest_sha256"}
        if not expected_fields <= set(request) <= expected_fields | {"acknowledged"} or request.get("schema_version") != "value.data-mapping-commit-request/v1":
            raise DataMappingError("GF_MAPPING_REQUEST", "Invalid mapping commit request.")
        acknowledged = request.get("acknowledged", [])
        if not isinstance(acknowledged, list) or not all(isinstance(item, str) for item in acknowledged):
            raise DataMappingError("GF_MAPPING_REQUEST", "acknowledged must be a list of codes.")
        with self.lock:
            directory, review = self._load("reviews", review_id)
            if review.get("valid") is not True or review.get("errors"):
                raise DataMappingError("GF_MAPPING_NOT_VALIDATED", "Review and validate this mapping before committing.", 409)
            for field in expected_fields - {"schema_version"}:
                if request[field] != review.get(field):
                    raise DataMappingError("GF_MAPPING_IDENTITY", "Reviewed mapping identity changed; review again.", 409)
            missing = [item["code"] for item in review.get("acknowledgements_required") or []
                       if item.get("code") not in acknowledged]
            if missing:
                # S-低2: a series shorter than a model year is committed only
                # when the user has confirmed that it will be repeated.
                raise DataMappingError(
                    "GF_MAPPING_ACKNOWLEDGEMENT",
                    "Confirm the coverage note of the review before committing: " + ", ".join(missing) + ".", 409)
            if review.get("pack_id") in self.busy_packs():
                raise DataMappingError("GF_DATA_PACK_FREEZING", "A Run is freezing this data pack's files right now; commit the mapping after the Run is queued.", 409)
            root, manifest, _ = self._target(review["pack_id"], review["target_manifest_sha256"])
            stage_dir, stage = self._load("stages", review["stage_id"])
            source = _bytes(stage_dir / "source.csv", self.staging_root)
            headers, _ = _shape(source)
            spec_payload = json.loads(_bytes(directory / "spec.json", self.staging_root))
            if not isinstance(spec_payload, dict):
                raise DataMappingError("GF_MAPPING_IDENTITY", "Mapping specification is corrupt; review again.", 409)
            spec = self._spec(review["role"], spec_payload.get("columns"), headers,
                              _fx(spec_payload.get("source") or None),
                              source_interval_minutes=60 if spec_payload.get("repeat_rows") == 2 else 30)
            if _canonical(spec_payload) != _canonical(spec.to_dict()) or _hash(_canonical(spec_payload)) != review["spec_sha256"] or _hash(source) != review["source_sha256"]:
                raise DataMappingError("GF_MAPPING_IDENTITY", "Source or mapping specification changed; review again.", 409)
            normalized = _bytes(directory / "normalized.csv", self.staging_root)
            if _hash(normalized) != review["normalized_sha256"] or stage["pack_id"] != review["pack_id"] or stage["role"] != review["role"]:
                raise DataMappingError("GF_MAPPING_IDENTITY", "Normalized bytes or target identity changed; review again.", 409)
            # Recompute to prove the reviewed bytes still derive from this exact source/spec.
            rebuilt = directory / "rechecked.csv"
            result = execute_adapter(stage_dir / "source.csv", spec, rebuilt,
                                     significant_digits=MAPPED_VALUE_SIGNIFICANT_DIGITS)
            if result.normalized_sha256 != review["normalized_sha256"] or result.source_sha256 != review["source_sha256"]:
                rebuilt.unlink(missing_ok=True)
                raise DataMappingError("GF_MAPPING_IDENTITY", "Normalization no longer matches the reviewed bytes.", 409)
            self._target(review["pack_id"], review["target_manifest_sha256"])
            provenance_root = root / "mapping-provenance"
            if provenance_root.is_symlink():
                rebuilt.unlink(missing_ok=True)
                raise DataMappingError("GF_MAPPING_UNSAFE_FILE", "Mapping provenance must remain inside the pack.")
            provenance = provenance_root / review_id
            if provenance.exists():
                rebuilt.unlink(missing_ok=True)
                raise DataMappingError("GF_MAPPING_ALREADY_COMMITTED", "This review has already been committed.", 409)
            provenance.mkdir(parents=True)
            try:
                (provenance / "source.csv").write_bytes(source)
                _write(provenance / "spec.json", spec_payload)
                _write(provenance / "review.json", review)
                timestamp = review.get("timestamp")
                timestamp_metadata = {
                    "timestamp_column": timestamp["column"],
                    "timestamp_time_zone": timestamp["time_zone"],
                    # S-中3: the day/month order the check used (omitted for ISO dates).
                    **({"timestamp_date_order": timestamp["date_order"]}
                       if timestamp.get("date_order") in ("day_first", "month_first") else {}),
                    "timestamp_uri": (provenance / "source.csv").relative_to(root).as_posix(),
                    # The interval the check used; the binding's own interval_minutes is unchanged.
                    "timestamp_check": {"status": "passed", "rows_checked": timestamp["rows_checked"],
                                        "interval_minutes": timestamp["interval_minutes"],
                                        "source_sha256": review["source_sha256"]},
                } if isinstance(timestamp, dict) else {}
                metadata = {"unit": self.slots[review["role"]].get("unit"),
                            # P0-5a S10: the normalized file declares how it is read
                            # (the preview validated the same declarations, S-中2).
                            **_reading_metadata(review["role"]),
                            **({"currency": "GBP"} if review["role"] in MARKET_PRICE_ROLES else {}),
                            **({"source_currency": "EUR", **dict(spec.source)} if spec.source else {}),
                            # S-F-中3: the retained source is hourly; the canonical file is half-hourly.
                            **({"source_interval_minutes": 60, "source_expansion": "each hour used for two half-hour periods"}
                               if spec.repeat_rows == 2 else {}),
                            # Spec 11.6 (S-D4): the declared timestamps stay in the retained
                            # source; the chronology layer re-checks them from there.
                            **timestamp_metadata,
                            "redistribution_class": "not_declared",
                            "owner_extension": self.slots[review["role"]].get("owner_extension"),
                            "capability": self.slots[review["role"]].get("capability"),
                            "mapping_provenance": {"schema_version": "value.data-mapping-provenance/v1",
                                "source_uri": (provenance / "source.csv").relative_to(root).as_posix(),
                                "spec_uri": (provenance / "spec.json").relative_to(root).as_posix(),
                                "review_uri": (provenance / "review.json").relative_to(root).as_posix(),
                                "source_sha256": review["source_sha256"], "spec_sha256": review["spec_sha256"],
                                "normalized_sha256": review["normalized_sha256"],
                                "converted_value_significant_digits": MAPPED_VALUE_SIGNIFICANT_DIGITS}}
                binding, validation = promote_binding_revision(pack_root=root, manifest=manifest,
                    role=review["role"], staged_file=rebuilt, filename="mapped.csv", file_format="csv",
                    dataset_slots=[self.slots[review["role"]]], imported_at=_iso(time.time()), metadata=metadata)
            except Exception:
                shutil.rmtree(provenance)
                rebuilt.unlink(missing_ok=True)
                raise
            return {"schema_version": "value.data-mapping-commit/v1", "ok": True,
                    "pack_id": review["pack_id"], "role": review["role"], "binding": binding,
                    "validation": validation, "manifest_sha256": _hash((root / "manifest.json").read_bytes()),
                    "run_started": False}
