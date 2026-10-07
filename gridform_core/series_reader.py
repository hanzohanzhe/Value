"""Declarative chronological series reader (P0-5a S1/S2).

One reader for the canonical adapter, the data-pack validator and the
retained kernel's boundary input.  A series is read from what the binding
declares (``csv_column``, ``csv_header``, ``unit``, ``currency``,
``eur_per_gbp``, ``interval_minutes`` ...), never by guessing "the column
with the most numbers" when a declaration exists.

Two reading modes, independent of the strictness:

* ``legacy-v1`` reproduces the 35aadb3 reader (``_series``/``_clock`` of
  ``canonical_psm_data``) bit for bit, except for the universal corrections:
  a declared ``csv_column`` is read (P6-01) and the semantics the truth
  registry asserts for a verified object are applied (P6-02, P6-03, P6-04;
  decision A5).
* ``declared-v2`` reads the declaration first: an undeclared header is
  inferred the way the validator always did (only a wholly non-numeric first
  row is a header, P6-05), several numeric columns without a declaration are
  ambiguous (``strict`` raises ``GF_DATA_AMBIGUOUS_COLUMN``; ``lenient`` keeps
  the legacy choice with a warning), and the clock honours the declared
  resolution (P6-07).

Both modes share one guard: an implicitly selected column that is an integer
sequence with step 1 is an index, not data (``GF_DATA_INDEX_COLUMN``).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


LEGACY = "legacy-v1"
DECLARED = "declared-v2"
MODES = (LEGACY, DECLARED)
STRICT = "strict"
LENIENT = "lenient"
READER_METHOD_IDS = {LEGACY: "value.series-reader.legacy/v1", DECLARED: "value.series-reader.declared/v2"}
CLOCK_METHOD_IDS = {LEGACY: "value.series-clock.legacy/v1", DECLARED: "value.series-clock.declared/v2"}

REGISTRY_PATH = Path(__file__).resolve().parent / "data" / "validation" / "known_data_objects_v1.json"
REGISTRY_SCHEMA = "value.known-data-objects/v1"
# Binding fields a registry entry may assert for a verified object.
SPEC_FIELDS = (
    "csv_header", "csv_column", "unit", "currency", "eur_per_gbp", "fx_basis", "interval_minutes",
    "source_periods", "source_start_utc", "cyclic", "leap_policy", "chronology_contract",
    "time_convention", "flow_sign", "timestamp_column",
)
FIELD_STATUSES = ("declared", "registry_asserted", "declared_unverified")
DEMAND_ROLES = frozenset({"demand.forecast", "demand.real"})


class SeriesReadError(ValueError):
    """A series cannot be read as declared; ``code`` is the public GF_DATA_* code."""

    def __init__(self, code: str, message: str, *, role: str | None = None) -> None:
        self.code = code
        self.role = role
        super().__init__(f"{code}: {message}" if not role else f"{code} [{role}]: {message}")


# --------------------------------------------------------------- registry

@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != REGISTRY_SCHEMA:
        raise ValueError(f"{REGISTRY_PATH.name}: schema_version must be {REGISTRY_SCHEMA}")
    objects = payload.get("objects")
    if not isinstance(objects, dict):
        raise ValueError(f"{REGISTRY_PATH.name}: objects must be a mapping by sha256")
    for sha, entry in objects.items():
        if len(sha) != 64 or not isinstance(entry, dict):
            raise ValueError(f"{REGISTRY_PATH.name}: malformed entry {sha!r}")
        for name, item in dict(entry.get("fields") or {}).items():
            if name not in SPEC_FIELDS or not isinstance(item, dict) or item.get("status") not in FIELD_STATUSES:
                raise ValueError(f"{REGISTRY_PATH.name}: {sha[:12]} field {name!r} is malformed")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


_VERIFIED: dict[tuple[str, int, int], str] = {}


def verified_sha256(path: Path) -> str:
    """The file's sha256 (memoised by realpath, size and mtime)."""

    path = Path(path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _VERIFIED:
        _VERIFIED[key] = file_sha256(path)
    return _VERIFIED[key]


def registry_entry(path: Path, binding: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """The truth-registry entry of a bound file, only after its hash is verified.

    A registry entry is keyed by the object's sha256; the semantics it asserts
    are used only when the bytes on disk hash to that key (and, when the
    binding records a sha256, to the binding's too).  Unregistered or
    unverifiable objects get ``None``.
    """

    objects = load_registry()["objects"]
    declared = str(dict(binding or {}).get("sha256") or "").lower()
    if declared and declared not in objects:
        return None
    try:
        actual = verified_sha256(path)
    except OSError:
        return None
    if declared and actual != declared:
        return None
    entry = objects.get(actual)
    return dict(entry, sha256=actual) if entry else None


# -------------------------------------------------------------------- spec

@dataclass(frozen=True)
class SeriesSpec:
    role: str = ""
    csv_header: bool | None = None
    csv_column: str | None = None
    unit: str | None = None
    currency: str | None = None
    eur_per_gbp: float | None = None
    fx_basis: str | None = None
    interval_minutes: int | None = None
    source_periods: int | None = None
    source_start_utc: str | None = None
    cyclic: bool | None = None
    leap_policy: str | None = None
    chronology_contract: str | None = None
    time_convention: str | None = None
    flow_sign: str | None = None
    timestamp_column: str | None = None
    field_status: Mapping[str, str] = field(default_factory=dict)
    repairs: Mapping[str, Any] = field(default_factory=dict)
    registry_object: str | None = None
    correction_ids: tuple[str, ...] = ()

    @classmethod
    def from_binding(
        cls, role: str, binding: Mapping[str, Any] | None, *, registry: Mapping[str, Any] | None = None,
    ) -> "SeriesSpec":
        """Declarations of a binding, overlaid by a verified registry entry's assertions."""

        binding = dict(binding or {})
        values: dict[str, Any] = {}
        status: dict[str, str] = {}
        for name in SPEC_FIELDS:
            if name in binding and binding[name] is not None:
                values[name] = binding[name]
                status[name] = "declared"
        repairs: dict[str, Any] = {}
        corrections: tuple[str, ...] = ()
        object_name = None
        if registry:
            for name, item in dict(registry.get("fields") or {}).items():
                if item["status"] == "registry_asserted":
                    values[name] = item.get("value")
                    status[name] = "registry_asserted"
                elif name in values and item["status"] == "declared_unverified":
                    status[name] = "declared_unverified"
            repairs = dict(registry.get("repairs") or {})
            corrections = tuple(registry.get("correction_ids") or ())
            object_name = str(registry.get("object") or "") or None
        if "csv_header" in values and not isinstance(values["csv_header"], bool):
            raise SeriesReadError("GF_DATA_DECLARATION", "csv_header must be true or false", role=role)
        for name in ("interval_minutes", "source_periods"):
            if name in values and (isinstance(values[name], bool) or not isinstance(values[name], int) or values[name] <= 0):
                raise SeriesReadError("GF_DATA_DECLARATION", f"{name} must be a positive integer", role=role)
        if "eur_per_gbp" in values:
            rate = values["eur_per_gbp"]
            if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
                raise SeriesReadError("GF_DATA_PRICE_CURRENCY", "eur_per_gbp must be a positive number", role=role)
            values["eur_per_gbp"] = float(rate)
        return cls(role=role, field_status=status, repairs=repairs, registry_object=object_name,
                   correction_ids=corrections, **values)

    def declaration(self) -> dict[str, Any]:
        """The effective declarations (evidence)."""

        return {name: getattr(self, name) for name in SPEC_FIELDS if getattr(self, name) is not None}


@dataclass(frozen=True)
class SeriesRead:
    values: np.ndarray
    column: str | int | None
    header: bool
    mode: str
    warnings: tuple[str, ...] = ()
    transforms: tuple[str, ...] = ()
    correction_ids: tuple[str, ...] = ()


# ------------------------------------------------------------------- read

def _index_like(values: np.ndarray) -> bool:
    if values.size < 3 or not np.all(np.isfinite(values)):
        return False
    if not np.all(values == np.round(values)):
        return False
    return bool(np.all(np.diff(values) == 1.0))


def _guard_index(values: np.ndarray, role: str, path: Path) -> None:
    if _index_like(values):
        raise SeriesReadError(
            "GF_DATA_INDEX_COLUMN",
            f"{path.name}: the implicitly selected column is an integer index (step 1); declare csv_column",
            role=role,
        )


def _legacy_values(path: Path, header: int | None) -> tuple[np.ndarray, int]:
    """35aadb3 ``canonical_psm_data._series``: the column with the most numbers, NaN dropped."""

    frame = pd.read_csv(path, header=header)
    candidates = [pd.to_numeric(frame.iloc[:, index], errors="coerce") for index in range(frame.shape[1])]
    numeric = max(candidates, key=lambda value: int(value.notna().sum()))
    selected = next(index for index, value in enumerate(candidates) if value is numeric)
    return numeric.dropna().to_numpy(dtype=float), selected


def _first_row_is_header(path: Path) -> bool:
    first = pd.read_csv(path, header=None, nrows=1, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    cells = [str(value).strip() for value in first.iloc[0].tolist()] if len(first) else []
    if not cells:
        return False
    return all(pd.to_numeric(pd.Series([cell]), errors="coerce").isna().iloc[0] for cell in cells if cell != "") and any(cells)


def _declared_column(path: Path, spec: SeriesSpec) -> tuple[np.ndarray, str]:
    if spec.csv_header is False:
        raise SeriesReadError("GF_DATA_DECLARATION", "csv_column requires csv_header true", role=spec.role)
    frame = pd.read_csv(path, header=0, encoding="utf-8-sig")
    column = str(spec.csv_column)
    if column not in frame.columns:
        raise SeriesReadError("GF_DATA_COLUMN_MISSING", f"{path.name} has no column {column!r}", role=spec.role)
    numeric = pd.to_numeric(frame[column], errors="coerce")
    if int(numeric.isna().sum()):
        raise SeriesReadError(
            "GF_DATA_NON_NUMERIC", f"{path.name}:{column} has {int(numeric.isna().sum())} non-numeric cells",
            role=spec.role,
        )
    return numeric.to_numpy(dtype=float), column


def _declared_values(path: Path, spec: SeriesSpec, strictness: str) -> tuple[np.ndarray, int | str, bool, list[str]]:
    warnings: list[str] = []
    header = spec.csv_header if spec.csv_header is not None else _first_row_is_header(path)
    frame = pd.read_csv(path, header=0 if header else None, encoding="utf-8-sig")
    columns = []
    for index in range(frame.shape[1]):
        numeric = pd.to_numeric(frame.iloc[:, index], errors="coerce")
        if int(numeric.notna().sum()) and int(numeric.isna().sum()) == 0:
            columns.append((index, numeric.to_numpy(dtype=float)))
    if not columns:
        raise SeriesReadError("GF_DATA_NON_NUMERIC", f"{path.name} has no wholly numeric column", role=spec.role)
    if len(columns) > 1:
        names = [str(frame.columns[index]) if header else str(index) for index, _ in columns]
        if strictness == STRICT:
            raise SeriesReadError(
                "GF_DATA_AMBIGUOUS_COLUMN", f"{path.name} has numeric columns {names}; declare csv_column",
                role=spec.role,
            )
        warnings.append(f"GF_DATA_AMBIGUOUS_COLUMN: {path.name} has numeric columns {names}; the first was read")
    index, values = columns[0]
    _guard_index(values, spec.role, path)
    return values, (str(frame.columns[index]) if header else index), bool(header), warnings


def _physical_rows(path: Path, spec: SeriesSpec) -> np.ndarray:
    """All data rows of a single-value file under the declared header (repairs index these)."""

    if spec.csv_column:
        return _declared_column(path, spec)[0]
    frame = pd.read_csv(path, header=0 if spec.csv_header else None, encoding="utf-8-sig")
    if frame.shape[1] != 1:
        raise SeriesReadError("GF_DATA_DECLARATION", f"{path.name}: row repairs need one column or csv_column",
                              role=spec.role)
    values = pd.to_numeric(frame.iloc[:, 0], errors="coerce")
    if int(values.isna().sum()):
        raise SeriesReadError("GF_DATA_NON_NUMERIC", f"{path.name} has non-numeric data rows", role=spec.role)
    return values.to_numpy(dtype=float)


def apply_row_repairs(values: np.ndarray, repairs: Mapping[str, Any]) -> tuple[np.ndarray, list[str]]:
    """Registry-asserted row repairs: drop duplicated source rows, interpolate named gaps (P6-04)."""

    notes: list[str] = []
    drop = sorted(int(index) for index in repairs.get("drop_source_rows", ()))
    if drop:
        values = np.delete(values, drop)
        notes.append(f"dropped duplicated source rows {drop}")
    for gap in repairs.get("interpolate_gaps", ()):
        position, count = int(gap["at"]), int(gap["count"])
        before, after = float(values[position - 1]), float(values[position])
        filled = np.interp(np.arange(1, count + 1), [0, count + 1], [before, after])
        values = np.insert(values, position, filled)
        notes.append(f"interpolated {count} missing periods at {position}")
    return values, notes


def read_series(
    path: Path,
    spec: SeriesSpec,
    *,
    mode: str = LEGACY,
    strictness: str = LENIENT,
    legacy_header: int | None = 0,
) -> SeriesRead:
    """Read one numeric series as declared (see the module docstring)."""

    if mode not in MODES:
        raise ValueError(f"Unknown series reading mode {mode!r}")
    path = Path(path)
    warnings: list[str] = []
    transforms: list[str] = []
    corrections: list[str] = []
    if spec.repairs:
        values = _physical_rows(path, spec)
        values, notes = apply_row_repairs(values, spec.repairs)
        transforms.extend(notes)
        corrections.extend(spec.correction_ids)
        column: str | int | None = spec.csv_column or 0
        header = bool(spec.csv_header)
        if mode == LEGACY and legacy_header == 0 and spec.csv_header is False:
            # Frozen 35aadb3 behaviour (P6-05 is corrected only): the first
            # data row of a headerless file was consumed as a header.
            values = values[1:]
            transforms.append("legacy: first data row consumed as header (P6-05 frozen)")
    elif spec.csv_column:
        values, column = _declared_column(path, spec)
        header = True
        if spec.field_status.get("csv_column") == "registry_asserted":
            corrections.extend(spec.correction_ids)
    elif mode == LEGACY:
        values, column = _legacy_values(path, legacy_header)
        header = legacy_header is not None
        if pd.read_csv(path, header=legacy_header, nrows=0 if legacy_header is not None else 1).shape[1] > 1:
            _guard_index(values, spec.role, path)
    else:
        values, column, header, extra = _declared_values(path, spec, strictness)
        warnings.extend(extra)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError(f"Numeric series contains no usable finite values: {path.name}")
    if spec.currency is not None and str(spec.currency).upper() != "GBP":
        if str(spec.currency).upper() != "EUR" or spec.eur_per_gbp is None:
            raise SeriesReadError(
                "GF_DATA_PRICE_CURRENCY",
                f"{path.name} is priced in {spec.currency}; a GBP conversion needs eur_per_gbp and fx_basis",
                role=spec.role,
            )
        values = values / float(spec.eur_per_gbp)
        transforms.append(f"EUR/MWh / {spec.eur_per_gbp:g} EUR per GBP ({spec.fx_basis or 'fx basis not recorded'})")
        if spec.field_status.get("currency") == "registry_asserted":
            corrections.extend(spec.correction_ids)
    if spec.field_status.get("interval_minutes") == "registry_asserted" and spec.interval_minutes == 60:
        # A registry-asserted hourly object is expanded once, in both modes (A5).
        values = np.repeat(values, 2)
        transforms.append("hourly -> half-hourly (each hour twice)")
    return SeriesRead(values, column, header, mode, tuple(warnings), tuple(transforms),
                      tuple(dict.fromkeys(corrections)))


# ------------------------------------------------------------------- clock

def legacy_clock(values: np.ndarray, periods: int, *, hourly_repeat: bool = False) -> np.ndarray:
    """35aadb3 ``canonical_psm_data._clock`` (frozen; P6-07 is corrected only)."""

    if len(values) == periods:
        return values.copy()
    if hourly_repeat and len(values) * 2 >= periods:
        return np.repeat(values, 2)[:periods]
    if len(values) == 0:
        raise ValueError("A chronological source is empty.")
    if len(values) < periods:
        return np.resize(values, periods)
    return values[:periods]


def _drop_leap_day(values: np.ndarray, *, conserve_energy: bool) -> np.ndarray:
    if conserve_energy:
        from .weather_demand_ensembles import normalize_half_hour_year

        return np.asarray(normalize_half_hour_year(values, source_periods=17_568), dtype=float)
    start = (31 + 28) * 48
    return np.concatenate([values[:start], values[start + 48:]])


def align_clock(
    values: np.ndarray,
    periods: int,
    spec: SeriesSpec,
    *,
    mode: str = LEGACY,
    strictness: str = LENIENT,
    hourly_repeat: bool = False,
    cyclic_default: bool = False,
) -> np.ndarray:
    """Put a read series on the run clock.

    ``legacy-v1`` is the frozen clock.  ``declared-v2`` takes the resolution
    from ``interval_minutes`` (or an hourly length 8760/8784) before it
    truncates, so a short window never stretches a half-hour series (P6-07);
    a leap year is reduced by 29 February; a shorter series wraps only when it
    is declared (or by role convention) cyclic, and strict reading refuses it
    otherwise.
    """

    values = np.asarray(values, dtype=float)
    if mode == LEGACY:
        already_expanded = spec.field_status.get("interval_minutes") == "registry_asserted"
        return legacy_clock(values, periods, hourly_repeat=hourly_repeat and not already_expanded)
    if len(values) == 0:
        raise ValueError("A chronological source is empty.")
    expanded = spec.field_status.get("interval_minutes") == "registry_asserted" and spec.interval_minutes == 60
    if not expanded and (spec.interval_minutes == 60 or (spec.interval_minutes is None and len(values) in (8760, 8784))):
        values = np.repeat(values, 2)
    elif spec.interval_minutes not in (None, 30, 60):
        raise SeriesReadError("GF_DATA_RESOLUTION", f"interval_minutes={spec.interval_minutes} is not supported",
                              role=spec.role)
    if len(values) == 17_568 and spec.leap_policy != "keep":
        values = _drop_leap_day(values, conserve_energy=spec.role in DEMAND_ROLES)
    if len(values) >= periods:
        return values[:periods].copy()
    cyclic = spec.cyclic if spec.cyclic is not None else cyclic_default
    if not cyclic and strictness == STRICT:
        raise SeriesReadError(
            "GF_DATA_SHORT_SERIES", f"{len(values)} periods cannot cover a {periods}-period run (not declared cyclic)",
            role=spec.role,
        )
    return np.resize(values, periods)


@dataclass(frozen=True)
class ClockAlignment:
    """What the declared clock (``align_clock`` in ``declared-v2``) does to ``source_rows`` values.

    Four-role test S-中2: the review report and the pack validation describe
    the branch the reader actually takes, from this one place, instead of
    saying "repeats it cyclically" for every length.
    """

    source_rows: int
    periods: int
    period_hours: float = 0.5
    hourly_doubled: bool = False
    leap_day_removed: bool = False
    energy_rescaled: bool = False
    used_periods: int = 0
    ignored_periods: int = 0
    wrapped_periods: int = 0
    refused: str | None = None

    @property
    def changes_series(self) -> bool:
        return bool(self.hourly_doubled or self.leap_day_removed or self.ignored_periods
                    or self.wrapped_periods or self.refused)

    @property
    def short_of_a_year(self) -> bool:
        """The reader fills part of the model year by repeating the series (S-低2)."""

        return self.wrapped_periods > 0 and self.refused is None

    def describe(self) -> str | None:
        """One sentence for the user, or None when the series is used as it is."""

        if self.refused:
            return self.refused
        parts: list[str] = []
        if self.hourly_doubled:
            parts.append(f"{self.source_rows:,} rows are read as hourly values: each hour is used for two "
                         "half-hour periods")
        if self.leap_day_removed:
            parts.append("the series has 17,568 half-hour periods (a leap year): 29 February is removed"
                         + (" and the other periods are rescaled to keep the annual energy"
                            if self.energy_rescaled else ""))
        if self.ignored_periods:
            parts.append(f"only the first {self.periods:,} half-hour periods are used; the last "
                         f"{self.ignored_periods:,} are ignored")
        if self.wrapped_periods:
            days = self.wrapped_periods * self.period_hours / 24.0
            parts.append(f"the series covers {self.used_periods:,} of the {self.periods:,} half-hour periods "
                         f"of a model year: the last {self.wrapped_periods:,} periods ({days:.1f} days) are "
                         "filled by repeating the series from its start")
        if not parts:
            return None
        text = "; ".join(parts)
        return text[0].upper() + text[1:] + "."


def clock_alignment(
    source_rows: int,
    periods: int,
    spec: SeriesSpec,
    *,
    strictness: str = LENIENT,
    cyclic_default: bool = False,
    period_hours: float = 0.5,
) -> ClockAlignment:
    """The plan of ``align_clock(..., mode=DECLARED)`` for a series of ``source_rows`` values.

    It follows the declared branch step by step (the hourly expansion of a
    registry-asserted object in ``read_series`` included); the unit tests
    check it against ``align_clock`` on the lengths users bring.
    """

    rows = int(source_rows)
    if rows <= 0:
        return ClockAlignment(rows, periods, period_hours, refused="The series is empty.")
    if spec.interval_minutes not in (None, 30, 60):
        return ClockAlignment(rows, periods, period_hours,
                              refused=f"interval_minutes={spec.interval_minutes} is not supported.")
    length = rows
    doubled = spec.interval_minutes == 60 or (spec.interval_minutes is None and rows in (8760, 8784))
    if doubled:
        length *= 2
    leap = length == 17_568 and spec.leap_policy != "keep"
    if leap:
        length = 17_520
    if length >= periods:
        return ClockAlignment(rows, periods, period_hours, doubled, leap, leap and spec.role in DEMAND_ROLES,
                              used_periods=periods, ignored_periods=length - periods)
    cyclic = spec.cyclic if spec.cyclic is not None else cyclic_default
    if not cyclic and strictness == STRICT:
        return ClockAlignment(
            rows, periods, period_hours, doubled, leap, leap and spec.role in DEMAND_ROLES, used_periods=length,
            refused=(f"The series covers {length:,} of the {periods:,} half-hour periods of a model year and is "
                     "not declared cyclic: the strict reader refuses it (GF_DATA_SHORT_SERIES)."),
        )
    return ClockAlignment(rows, periods, period_hours, doubled, leap, leap and spec.role in DEMAND_ROLES,
                          used_periods=length, wrapped_periods=periods - length)


def series_sha256(values: Sequence[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()
