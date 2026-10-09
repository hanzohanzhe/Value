"""Which hour of an hourly solar profile is extra?  Evidence against ERA5 ssrd (A24-1).

``python -B scripts/audit_hourly_solar_profile.py --profile sa.csv --era5 2022solar.nc
[--era5-span 2022-2023solar.nc] --year 2022 [--out evidence.json]``

The system-average solar profile ``sa.csv`` bound by R029 public1 and GBP1
public1 holds 8761 hourly values (one more than a year) and no timestamps.
This script compares it with the ERA5 surface solar radiation downwards
(``ssrd``, accumulated over the hour ending at the stamp) averaged over a GB
box, and reports:

* the Pearson correlation of profile row ``i + k`` with ERA5 stamp ``i`` for
  ``k`` in -2..2 over the whole year, per month and per week (the lag that
  fits best everywhere is the profile's alignment; a row inserted inside the
  year would move the best lag of every later week);
* "light in the dark": profile rows > 0 where the GB-mean ssrd is ~0 at the
  aligned stamp (zero at the right lag);
* with ``--era5-span`` (an ERA5 file running past the year end): the length of
  the inclusive slice ``year-01-01T00:00 .. (year+1)-01-01T00:00`` and the
  domain maximum of ssrd at the extra stamp.

It reads the files only; nothing is written except ``--out``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "value.hourly-solar-profile-audit/v1"
GB_BOX = {"latitude": (59.0, 50.0), "longitude": (-6.0, 2.0)}
LAGS = (-2, -1, 0, 1, 2)
DARK_J_PER_M2 = 0.5          # GB-mean hourly ssrd below this is night (ERA5 writes exact zeros)
LIGHT_PER_UNIT = 1e-6


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_profile(path: Path) -> tuple[np.ndarray, list[str]]:
    lines = path.read_bytes().decode("ascii").splitlines()
    return np.array([float(line) for line in lines]), lines


def _time_name(ds: Any) -> str:
    return next(name for name in ("valid_time", "time") if name in ds.coords)


def gb_mean_ssrd(path: Path, start: str, end: str) -> tuple[np.ndarray, list[str]]:
    import xarray as xr

    with xr.open_dataset(path) as ds:
        time = _time_name(ds)
        field = ds["ssrd"].sel({time: slice(start, end)})
        box = field.sel(latitude=slice(*GB_BOX["latitude"]), longitude=slice(*GB_BOX["longitude"]))
        values = box.mean(dim=("latitude", "longitude")).values.astype(float)
        stamps = [str(value)[:19] + "Z" for value in field[time].values]
    return values, stamps


def lag_statistics(profile: np.ndarray, era5: np.ndarray, lag: int, start: int = 0, end: int | None = None) -> dict[str, Any]:
    """Profile row ``i + lag`` against ERA5 stamp ``i`` for ``start <= i < end``."""

    end = len(era5) if end is None else end
    first, last = max(start, -lag), min(end, len(profile) - lag)
    if last - first < 2:
        return {"lag": lag, "n": 0}
    rows = profile[first + lag:last + lag]
    ref = era5[first:last]
    return {
        "lag": lag,
        "n": int(last - first),
        "correlation": round(float(np.corrcoef(rows, ref)[0, 1]), 5),
        "light_in_the_dark": int(((rows > LIGHT_PER_UNIT) & (ref < DARK_J_PER_M2)).sum()),
    }


def audit(profile_path: Path, era5_path: Path, year: int, span_path: Path | None = None) -> dict[str, Any]:
    profile, lines = read_profile(profile_path)
    era5, stamps = gb_mean_ssrd(era5_path, f"{year}-01-01T00:00", f"{year}-12-31T23:00")
    hours = len(era5)
    whole_year = [lag_statistics(profile, era5, lag) for lag in LAGS]
    best = max((row for row in whole_year if row["n"]), key=lambda row: row["correlation"])
    weekly = []
    for week in range(hours // 168):
        rows = [lag_statistics(profile, era5, lag, week * 168, (week + 1) * 168) for lag in (-1, 0, 1)]
        rows = [row for row in rows if row["n"]]
        weekly.append(max(rows, key=lambda row: row["correlation"])["lag"])
    month_starts = np.cumsum([0] + [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]) * 24
    monthly = {}
    for month in range(12):
        rows = [lag_statistics(profile, era5, lag, int(month_starts[month]), int(month_starts[month + 1]))
                for lag in (-1, 0, 1)]
        monthly[f"{month + 1:02d}"] = {str(row["lag"]): row.get("correlation") for row in rows}
    extra = len(profile) - hours
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "profile": {"name": profile_path.name, "sha256": sha256(profile_path), "rows": len(profile),
                    "first_rows": lines[:3], "last_rows": lines[-3:], "extra_rows": extra},
        "era5": {"name": era5_path.name, "sha256": sha256(era5_path), "variable": "ssrd",
                 "convention": "accumulated over the hour ending at the stamp (ERA5)",
                 "gb_box": GB_BOX, "hours": hours, "first_stamp": stamps[0], "last_stamp": stamps[-1]},
        "whole_year_by_lag": whole_year,
        "best_lag": best["lag"],
        "weekly_best_lags": sorted(set(weekly)),
        "weeks": len(weekly),
        "monthly_correlation_by_lag": monthly,
    }
    if span_path is not None:
        span, span_stamps = gb_mean_ssrd(span_path, f"{year}-01-01T00:00", f"{year + 1}-01-01T00:00")
        import xarray as xr

        with xr.open_dataset(span_path) as ds:
            time = _time_name(ds)
            at_end = float(ds["ssrd"].sel({time: f"{year + 1}-01-01T00:00"}).max())
        result["era5_span"] = {
            "name": span_path.name, "sha256": sha256(span_path),
            "inclusive_slice": f"{year}-01-01T00:00 .. {year + 1}-01-01T00:00",
            "inclusive_slice_hours": len(span), "last_stamp": span_stamps[-1],
            "domain_max_ssrd_at_last_stamp_j_per_m2": at_end,
            "whole_slice_lag0": lag_statistics(profile, span, 0),
        }
    if best["lag"] == 0 and result["weekly_best_lags"] == [0] and extra == 1:
        result["finding"] = {
            "extra_row_index": hours, "extra_row_line": hours + 1, "extra_row_value": lines[hours],
            "era5_stamp_of_extra_row": f"{year + 1}-01-01T00:00:00Z",
            "statement": (f"rows 0..{hours - 1} match ERA5 stamps {stamps[0]} .. {stamps[-1]} one to one; "
                          f"the last row is the stamp {year + 1}-01-01T00:00Z, outside the {year} stamps"),
            "first_row_value": lines[0],
            "interval_note": (
                f"ERA5 ssrd at a stamp is the hour ending at it, so by interval row 0 covers "
                f"{year - 1}-12-31T23:00-24:00Z and the last row {year}-12-31T23:00-24:00Z; both are night zeros. "
                "Dropping the out-of-year stamp keeps every existing reading of the first 8760 rows unchanged; "
                "re-labelling the profile to interval-start hours (one hour earlier, as finding P6-06 does for "
                "the NetCDF weather) would be a separate method change."),
        }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--era5", required=True, type=Path)
    parser.add_argument("--era5-span", type=Path)
    parser.add_argument("--year", type=int, default=2022)
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args(argv)
    result = audit(arguments.profile, arguments.era5, arguments.year, arguments.era5_span)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
