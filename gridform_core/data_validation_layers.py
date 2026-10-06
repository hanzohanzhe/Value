"""Chronology and plausibility layers of data-pack validation (P0-5a S4/S9; P6-11).

``data_pack_validation.validate_data_pack`` keeps deciding ``valid`` from the
structural layer only, so a pack with a known defect (GBP1 public1) can still
be installed and used by the profile that accepts it.  This module adds

* ``chronology``: line identity of interconnector flows, price currency,
  untimestamped local-time demand, registry-identified row-order defects,
  forecast/real alignment, index columns, declared timestamps;
* ``plausibility``: magnitudes against the versioned ranges in
  ``data/validation/value_data_plausibility_v1.json``;
* ``profile_eligibility``: per methodology profile, which findings block it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from . import series_reader as sr
from .interconnector_identity import COUNTRIES, BoundaryIdentityError, header_line_country

SCHEMA_VERSION = "value.data-validation-layers/v1"
DEMAND_ROLES = ("demand.real", "demand.forecast")


def _finding(code: str, layer: str, message: str, *, role: str | None = None, **detail: Any) -> dict[str, Any]:
    return {"code": code, "layer": layer, "role": role, "message": message, **detail}


def _path(pack_root: Path, manifest: Mapping[str, Any], role: str) -> Path | None:
    from .data_method import binding_path

    try:
        return binding_path(pack_root, manifest, role)
    except ValueError:
        return None


def _bound(manifest: Mapping[str, Any], role: str) -> dict[str, Any]:
    return dict(dict(manifest.get("bindings") or {}).get(role) or {})


def _forecast_lag(real: np.ndarray, forecast: np.ndarray, window: int) -> int:
    """Lag (periods) maximising the correlation of first differences; 0 = aligned."""

    size = min(len(real), len(forecast))
    a = np.diff(np.asarray(real[:size], dtype=float))
    b = np.diff(np.asarray(forecast[:size], dtype=float))
    best, best_lag = -np.inf, 0
    for lag in range(-window, window + 1):
        if lag >= 0:
            x, y = a[lag:], b[: len(b) - lag]
        else:
            x, y = a[:lag], b[-lag:]
        if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
            continue
        value = float(np.corrcoef(x, y)[0, 1])
        if value > best + 1e-12:
            best, best_lag = value, lag
    return best_lag


def _read(pack_root: Path, manifest: Mapping[str, Any], role: str, policy: Any, periods: int):
    from .data_method import read_role

    return read_role(pack_root, manifest, role, policy, periods=periods)


def evaluate_layers(pack_root: Path, manifest: Mapping[str, Any], *, periods: int = 17_520) -> dict[str, Any]:
    """The chronology and plausibility findings of a pack (never raises on data)."""

    from .data_method import load_plausibility, policy_for_profile, read_boundary

    pack_root = Path(pack_root).resolve()
    bindings = dict(manifest.get("bindings") or {})
    chronology: list[dict[str, Any]] = []
    plausibility: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}
    ranges = load_plausibility()

    # Registry-identified defects of verified objects.
    for role in sorted(bindings):
        path = _path(pack_root, manifest, role)
        if path is None or path.suffix.lower() != ".csv":
            continue
        entry = sr.registry_entry(path, bindings[role])
        if entry:
            for defect in entry.get("defects") or ():
                chronology.append(_finding(
                    defect["code"], "chronology", defect["message"], role=role, registry=True,
                    finding=defect.get("finding"), registry_object=entry.get("object"),
                ))

    # Interconnector line identity (P6-03).
    profile_paths = {country: _path(pack_root, manifest, f"market.{country}.profile") for country in COUNTRIES}
    if all(profile_paths.values()):
        for country, path in profile_paths.items():
            column, line = header_line_country(path)  # type: ignore[arg-type]
            if line is not None and line != country:
                chronology.append(_finding(
                    "GF_DATA_BOUNDARY_IDENTITY", "chronology",
                    f"market.{country}.profile carries {column}, the GB-{line} line", role=f"market.{country}.profile",
                    finding="P6-03",
                ))

    # Price currency (P6-02).
    for country in COUNTRIES:
        role = f"market.{country}.price"
        path = _path(pack_root, manifest, role)
        if path is None:
            continue
        try:
            first = path.open("r", encoding="utf-8-sig").readline()
        except (OSError, UnicodeDecodeError):
            continue
        declared = str(_bound(manifest, role).get("currency") or "").upper()
        if "EUR" in first.upper() and declared != "EUR":
            chronology.append(_finding(
                "GF_DATA_PRICE_CURRENCY", "chronology",
                f"{path.name} has a EUR column but the binding declares no EUR currency and conversion", role=role,
                finding="P6-02",
            ))

    # Untimestamped local-time demand (P6-04).
    timezone = str(manifest.get("timezone") or "UTC")
    for role in DEMAND_ROLES:
        path = _path(pack_root, manifest, role)
        if path is None:
            continue
        binding = _bound(manifest, role)
        try:
            rows = sum(1 for _ in path.open("rb"))
        except OSError:
            continue
        if timezone.upper() != "UTC" and not binding.get("timestamp_column") and rows > periods + 1:
            chronology.append(_finding(
                "GF_DATA_LOCAL_TIME_WITHOUT_TIMESTAMPS", "chronology",
                f"{rows} untimestamped rows in local time {timezone}; declare timestamps or a UTC mapping", role=role,
                finding="P6-04",
            ))

    # Declared timestamps (a binding's own timestamp_column).  A mapped
    # binding (spec 11.6, S-D4) keeps its timestamps in the retained source
    # (timestamp_uri) because the canonical file holds the value column only.
    for role in sorted(bindings):
        binding = _bound(manifest, role)
        if not binding.get("timestamp_column"):
            continue
        path = _path(pack_root, manifest, role)
        if binding.get("timestamp_uri"):
            path = _timestamp_source(pack_root, str(binding["timestamp_uri"]))
            if path is None:
                # A frozen snapshot copies the canonical file only; the check
                # passed when the mapping was committed.
                if dict(binding.get("timestamp_check") or {}).get("status") != "passed":
                    chronology.append(_finding(
                        "GF_DATA_TIMESTAMPS", "chronology",
                        "the declared timestamp source is unavailable and no passed check is recorded", role=role,
                    ))
                continue
        if path is not None:
            interval = binding.get("interval_minutes") or dict(binding.get("timestamp_check") or {}).get("interval_minutes") or 30
            chronology.extend(timestamp_findings(
                path, str(binding["timestamp_column"]), int(interval), role,
                time_zone=str(binding.get("timestamp_time_zone") or "UTC"),
            ))

    # Reading-dependent checks: index columns, forecast lag, magnitudes.
    readings: dict[str, Any] = {}
    from .methodology import profile_ids

    for profile_id in profile_ids():
        try:
            policy = policy_for_profile(profile_id, manifest)
        except Exception:  # noqa: BLE001 - unknown profile catalogue in a stripped install
            continue
        if policy.reader_mode in readings:
            continue
        lenient = replace(policy, strictness=sr.LENIENT)
        readings[policy.reader_mode] = lenient
    lags: dict[str, int] = {}
    demand: dict[str, np.ndarray] = {}
    for mode, policy in readings.items():
        try:
            real = _read(pack_root, manifest, "demand.real", policy, periods).values
            forecast = _read(pack_root, manifest, "demand.forecast", policy, periods).values
        except sr.SeriesReadError as exc:
            chronology.append(_finding(exc.code, "chronology", str(exc), role=exc.role, reader_modes=[mode]))
            continue
        except (ValueError, OSError):
            continue
        lags[mode] = _forecast_lag(real, forecast, int(ranges["forecast_lag_window_periods"]))
        demand.setdefault("real", real)
        demand.setdefault("forecast", forecast)
    if lags:
        evidence["forecast_lag_periods_by_reader"] = lags
        lagged = sorted(mode for mode, lag in lags.items() if lag != 0)
        if lagged:
            chronology.append(_finding(
                "GF_DATA_FORECAST_LAG", "chronology",
                "forecast and real demand are offset by " + ", ".join(f"{lags[m]} period(s) under {m}" for m in lagged),
                role="demand.forecast", reader_modes=lagged, finding="P6-05",
            ))

    boundary = None
    policy = next(iter(readings.values()), None)
    if policy is not None:
        try:
            boundary = read_boundary(pack_root, manifest, policy, periods=periods)
        except BoundaryIdentityError as exc:
            chronology.append(_finding("GF_DATA_BOUNDARY_IDENTITY", "chronology", str(exc), finding="P6-03"))
        except sr.SeriesReadError as exc:
            chronology.append(_finding(exc.code, "chronology", str(exc), role=exc.role))
        except (ValueError, OSError, KeyError):
            boundary = None

    # Plausibility (P6-11).
    scientific_gb = str(manifest.get("country") or "").upper() == "GB"
    peak_demand_mw = float(np.max(demand["real"])) if "real" in demand else None
    if "real" in demand:
        real = demand["real"]
        annual_twh = float(np.sum(real)) * 0.5 / 1e6
        evidence["demand_peak_mw"] = round(peak_demand_mw or 0.0, 3)
        evidence["demand_annual_twh"] = round(annual_twh, 3)
        if scientific_gb:
            limits = ranges["gb_demand_mw"]
            if not limits["peak_min"] <= peak_demand_mw <= limits["peak_max"]:
                plausibility.append(_finding("GF_DATA_PLAUSIBILITY_DEMAND", "plausibility",
                                             f"GB peak demand {peak_demand_mw:.0f} MW outside "
                                             f"[{limits['peak_min']:.0f}, {limits['peak_max']:.0f}]", role="demand.real"))
            if not limits["annual_twh_min"] <= annual_twh <= limits["annual_twh_max"]:
                plausibility.append(_finding("GF_DATA_PLAUSIBILITY_DEMAND", "plausibility",
                                             f"GB annual demand {annual_twh:.1f} TWh outside "
                                             f"[{limits['annual_twh_min']:.0f}, {limits['annual_twh_max']:.0f}]",
                                             role="demand.real"))
        else:
            capacity = _fleet_capacity_mw(pack_root, manifest)
            if capacity:
                ratio = peak_demand_mw / capacity
                evidence["demand_to_fleet_capacity"] = round(ratio, 6)
                limits = ranges["teaching_demand_to_fleet_capacity"]
                if not limits["min"] <= ratio <= limits["max"]:
                    plausibility.append(_finding("GF_DATA_PLAUSIBILITY_DEMAND", "plausibility",
                                                 f"peak demand is {ratio:.3g} x the installed fleet capacity",
                                                 role="demand.real"))
        if "forecast" in demand:
            forecast = demand["forecast"]
            mask = np.abs(real) > 1e-9
            mape = float(np.mean(np.abs(forecast[mask] - real[mask]) / np.abs(real[mask]))) if mask.any() else 0.0
            evidence["forecast_mape"] = round(mape, 6)
            if mape > float(ranges["forecast_mape_max"]):
                plausibility.append(_finding("GF_DATA_PLAUSIBILITY_FORECAST", "plausibility",
                                             f"forecast MAPE {mape:.1%} exceeds {ranges['forecast_mape_max']:.0%}",
                                             role="demand.forecast"))
    if boundary is not None:
        low, high = ranges["price_gbp_per_mwh"]["min"], ranges["price_gbp_per_mwh"]["max"]
        margin = float(ranges["flow_capacity_margin"])
        for country, entry in boundary.countries.items():
            prices = entry.price_gbp_per_mwh
            if float(np.min(prices)) < low or float(np.max(prices)) > high:
                plausibility.append(_finding("GF_DATA_PLAUSIBILITY_PRICE", "plausibility",
                                             f"{country} price range [{np.min(prices):.4g}, {np.max(prices):.4g}] "
                                             f"outside [{low:g}, {high:g}] GBP/MWh", role=f"market.{country}.price"))
            flow = float(np.max(np.abs(entry.flow_mw)))
            if scientific_gb:
                limit = margin * float(ranges["interconnector_nominal_capacity_mw"][country])
            elif peak_demand_mw is not None:
                limit = float(ranges["teaching_flow_to_peak_demand_max"]) * peak_demand_mw
            else:
                continue
            if flow > limit + 1e-9:
                plausibility.append(_finding("GF_DATA_PLAUSIBILITY_FLOW", "plausibility",
                                             f"{country} |flow| {flow:.4g} MW exceeds {limit:.4g} MW",
                                             role=f"market.{country}.profile"))
        evidence["boundary_series_sha256"] = boundary.series_sha256()
    return {
        "schema_version": SCHEMA_VERSION,
        "chronology": _layer(chronology),
        "plausibility": _layer(plausibility),
        "evidence": evidence,
    }


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, result = set(), []
    for row in rows:
        key = (row["code"], row.get("role"))
        if key in seen:
            if row.get("registry"):
                for item in result:
                    if (item["code"], item.get("role")) == key:
                        item.update(registry=True, registry_object=row.get("registry_object"))
            continue
        seen.add(key)
        result.append(row)
    return result


def _layer(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _dedupe(rows)
    return {"status": "passed" if not rows else "findings", "findings": rows,
            "codes": sorted({row["code"] for row in rows})}


def _fleet_capacity_mw(pack_root: Path, manifest: Mapping[str, Any]) -> float | None:
    import json

    path = _path(pack_root, manifest, "fleet.generators")
    if path is None:
        return None
    try:
        fleet = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    total = 0.0
    for group in ("generators", "batteries"):
        for raw in dict(fleet.get(group) or {}).values():
            for key in ("capacity_limit", "capacity_multiplier", "pool_limit", "capacity_mw"):
                value = dict(raw or {}).get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    total += float(value)
                    break
    return total or None


def finding_severity(policy: Any, finding: Mapping[str, Any]) -> str:
    """``error`` or ``warning`` of one finding under a data-method policy."""

    modes = finding.get("reader_modes")
    if modes is not None and policy.reader_mode not in modes:
        return "not_applicable"
    if not policy.fail_closed:
        return "warning"
    if finding["layer"] == "chronology":
        if finding.get("registry") or policy.pack_class != "user_workspace":
            return "error"
        return "warning"
    return "error" if policy.pack_class == "scientific_reference" else "warning"


def profile_eligibility(manifest: Mapping[str, Any], layers: Mapping[str, Any], *, structural_valid: bool) -> dict[str, Any]:
    from .data_method import policy_for_profile
    from .methodology import profile_ids

    result = {}
    findings = [*layers["chronology"]["findings"], *layers["plausibility"]["findings"]]
    for profile_id in profile_ids():
        policy = policy_for_profile(profile_id, manifest)
        errors = [row for row in findings if finding_severity(policy, row) == "error"]
        warnings = [row for row in findings if finding_severity(policy, row) == "warning"]
        result[profile_id] = {
            "eligible": bool(structural_valid) and not errors,
            "pack_class": policy.pack_class,
            "data_method_id": policy.data_method_id,
            "blocking_codes": sorted({row["code"] for row in errors}),
            "warning_codes": sorted({row["code"] for row in warnings}),
        }
    return result


TIMESTAMP_TIME_ZONES = ("UTC", "Europe/London")
TIMESTAMP_ROW_LIMIT = 50


def _timestamp_source(pack_root: Path, uri: str) -> Path | None:
    """The retained mapping source named by ``timestamp_uri`` (inside the pack), if present."""

    root = Path(pack_root).resolve()
    try:
        path = (root / uri).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


try:  # pandas raises pytz's errors, which are not ValueError subclasses (N-2).
    from pytz.exceptions import InvalidTimeError as _PytzInvalidTime
except ImportError:  # pragma: no cover - pytz ships with pandas here
    _PytzInvalidTime = ValueError

AMBIGUOUS_LOCAL_TIME = (
    "ambiguous local time (a repeated autumn hour that the row order cannot place; "
    "give this row an explicit UTC offset)")
NONEXISTENT_LOCAL_TIME = "non-existent local time (skipped by the spring clock change)"


def _parse_declared(path: Path, column: str, time_zone: str) -> tuple[pd.Series, pd.Series]:
    """UTC instants and, per row, why a readable local stamp could not be placed (else None)."""

    if time_zone not in TIMESTAMP_TIME_ZONES:
        raise ValueError(f"time zone must be one of {', '.join(TIMESTAMP_TIME_ZONES)}")
    raw = pd.read_csv(path, usecols=[column], encoding="utf-8-sig", dtype=str, keep_default_na=False)[column].str.strip()
    reasons = pd.Series([None] * len(raw), index=raw.index, dtype=object)
    with_offset = raw.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)
    if time_zone == "UTC" or bool(with_offset.all()):
        return pd.to_datetime(raw, errors="coerce", utc=True, format="mixed"), reasons
    naive = pd.to_datetime(raw.where(~with_offset), errors="coerce", format="mixed")
    try:
        local = naive.dt.tz_localize(time_zone, ambiguous="infer", nonexistent="NaT")
    except (ValueError, TypeError, _PytzInvalidTime):
        # N-2: an autumn hour that cannot be inferred by order (for example the
        # repeated hour appears only once) becomes NaT and is reported per row.
        local = naive.dt.tz_localize(time_zone, ambiguous="NaT", nonexistent="NaT")
    unplaced = naive.notna() & local.isna()
    if bool(unplaced.any()):
        as_dst = naive.dt.tz_localize(time_zone, ambiguous=True, nonexistent="NaT")
        as_std = naive.dt.tz_localize(time_zone, ambiguous=False, nonexistent="NaT")
        ambiguous = unplaced & as_dst.notna() & as_std.notna() & (as_dst != as_std)
        reasons[ambiguous] = AMBIGUOUS_LOCAL_TIME
        reasons[unplaced & ~ambiguous & as_dst.isna()] = NONEXISTENT_LOCAL_TIME
    stamps = local.dt.tz_convert("UTC")
    if bool(with_offset.any()):
        stamps = stamps.where(~with_offset, pd.to_datetime(raw.where(with_offset), errors="coerce", utc=True, format="mixed"))
    return stamps, reasons


def parse_declared_timestamps(path: Path, column: str, time_zone: str = "UTC") -> pd.Series:
    """Declared timestamps as UTC instants; an unreadable cell is NaT.

    ``UTC``: naive stamps are UTC.  ``Europe/London``: naive stamps are local
    wall-clock time (the repeated autumn hour is resolved by order; where the
    order cannot resolve it, or for a non-existent spring hour, the row is
    NaT); stamps carrying an offset keep it.
    """

    return _parse_declared(path, column, time_zone)[0]


def timestamp_row_problems(
    path: Path, column: str, interval_minutes: int | None, *, time_zone: str = "UTC", limit: int = TIMESTAMP_ROW_LIMIT,
) -> dict[str, Any]:
    """Row-by-row problems of a declared timestamp column (spec 11.6, S-D4).

    Rows are numbered as in the file (the header is row 1).  Each problem
    row says what is wrong: unreadable, a duplicate of an earlier row, earlier
    than the previous row, a gap, or an irregular step.  ``interval_minutes``
    None infers a 30- or 60-minute step from the most common one.
    """

    stamps, reasons = _parse_declared(path, column, time_zone)
    minutes = (stamps.diff().dt.total_seconds() / 60.0)
    if interval_minutes is None:
        positive = minutes[(minutes > 0)].round()
        common = positive.mode()
        interval_minutes = int(common.iloc[0]) if len(common) and int(common.iloc[0]) in (30, 60) else 30
    seen: dict[Any, int] = {}
    problems: list[dict[str, Any]] = []
    for index, (stamp, step, reason) in enumerate(zip(stamps, minutes, reasons)):
        row = index + 2
        text = None
        if pd.isna(stamp):
            text = reason or "unreadable timestamp"
        elif stamp in seen:
            text = f"duplicate of row {seen[stamp]}"
        elif index and not pd.isna(step):
            if step < 0:
                text = "earlier than the previous row"
            elif step > interval_minutes:
                text = f"gap of {step:g} minutes after the previous row (expected {interval_minutes})"
            elif step != interval_minutes:
                text = f"irregular step of {step:g} minutes (expected {interval_minutes})"
        if not pd.isna(stamp):
            seen.setdefault(stamp, row)
        if text:
            problems.append({"row": row, "timestamp": None if pd.isna(stamp) else stamp.isoformat(), "problem": text})
    return {
        "column": column, "time_zone": time_zone, "interval_minutes": interval_minutes,
        "rows_checked": int(len(stamps)), "problem_count": len(problems), "problems": problems[:limit],
        "first_utc": None if not len(stamps) or pd.isna(stamps.iloc[0]) else stamps.iloc[0].isoformat(),
    }


def timestamp_findings(path: Path, column: str, interval_minutes: int, role: str, *, time_zone: str = "UTC") -> list[dict[str, Any]]:
    """Monotonic, unique, gap-free declared timestamps (chronology layer)."""

    try:
        stamps, reasons = _parse_declared(path, column, time_zone)
    except (ValueError, KeyError, OSError, _PytzInvalidTime) as exc:
        return [_finding("GF_DATA_TIMESTAMPS", "chronology", f"{path.name}: unreadable timestamps ({exc})", role=role)]
    if stamps.isna().any():
        ambiguous = int((reasons == AMBIGUOUS_LOCAL_TIME).sum())
        detail = f"{int(stamps.isna().sum())} unreadable timestamp(s)"
        if ambiguous:
            detail += f", of which {ambiguous} ambiguous local time(s) in the repeated autumn hour"
        return [_finding("GF_DATA_TIMESTAMPS", "chronology", f"{path.name}:{column} {detail}", role=role)]
    step = stamps.diff().dropna()
    expected = pd.Timedelta(minutes=interval_minutes)
    problems = []
    if (step <= pd.Timedelta(0)).any():
        problems.append("not strictly increasing")
    if (step > expected).any():
        problems.append(f"{int((step > expected).sum())} gap(s)")
    if stamps.duplicated().any():
        problems.append("duplicates")
    if problems:
        return [_finding("GF_DATA_TIMESTAMPS", "chronology", f"{path.name}:{column} " + ", ".join(problems), role=role)]
    return []
