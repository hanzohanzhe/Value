"""Nuclear and run-of-river hydro availability of the corrected profile (P0-5b S8).

Findings P5-09/P6-10 (natural-flow hydro dispatched at availability 1.0, about
17.5 TWh/a against 5-6 TWh actual) and P5-10 (no nuclear availability; a
station retires for a whole year).  Under ``p05.firm-availability``:

* a nuclear asset is derated by its station load factor (PRIS 2019-2024 mean,
  rescaled to the model's EDF capacity so the energy is preserved), falling
  back to the reactor-type value for a planned project and to the DESNZ fleet
  value for an undifferentiated ``Nuclear`` asset; in the year of a station's
  announced ``YYYY-MM`` generation end it is zero from the next month;
* natural-flow hydro is derated by an annual load factor times a monthly shape.

The reference values live in ``data/nuclear/value_uk_firm_availability_v1.json``
and are PENDING AUTHOR REVIEW (DECISIONS: acceptance deferred to the author).
The doctoral profile keeps the 35aadb3 constant availability.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import numpy as np

CORRECTION = "p05.firm-availability"
METHOD_ID = "value.firm-availability/v1"
TABLE_PATH = Path(__file__).resolve().parent / "data" / "nuclear" / "value_uk_firm_availability_v1.json"
NUCLEAR = "Nuclear"
HYDRO = "Hydro_natural_flow"
TECHNOLOGIES = (NUCLEAR, HYDRO)
PERIODS_PER_DAY = 48
DAYS_PER_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@lru_cache(maxsize=1)
def load_table() -> dict[str, Any]:
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    if table.get("schema_version") != "value.firm-availability/v1":
        raise ValueError("Unsupported firm availability table")
    shape = [float(value) for value in table["hydro_natural_flow"]["monthly_shape"]]
    if len(shape) != 12 or abs(sum(shape) / 12.0 - 1.0) > 1e-9 or min(shape) < 0:
        raise ValueError("Hydro monthly shape must have 12 non-negative values with mean 1")
    for station, row in table["nuclear"]["stations"].items():
        if not 0.0 < float(row["pris_load_factor"]) <= 1.0:
            raise ValueError(f"Nuclear load factor out of range: {station}")
    return table


def table_sha256() -> str:
    return hashlib.sha256(TABLE_PATH.read_bytes()).hexdigest()


def enabled(methodology: Any) -> bool:
    return bool(methodology.enabled("p05.firm-availability"))


def enabled_for_profile(profile_id: str | None) -> bool:
    from .methodology import resolve_methodology

    return enabled(resolve_methodology(profile_id))


def month_of_period(periods: int) -> np.ndarray:
    """Month index (0..11) of each period on the fixed 365-day calendar (wrapping)."""

    day_month = np.repeat(np.arange(12), DAYS_PER_MONTH)
    day = (np.arange(periods) // PERIODS_PER_DAY) % 365
    return day_month[day]


def first_period_of_month(month_number: int) -> int:
    """First period of calendar month ``month_number`` (1..12)."""

    return int(sum(DAYS_PER_MONTH[: month_number - 1]) * PERIODS_PER_DAY)


def _station_records() -> dict[str, Mapping[str, Any]]:
    from .nuclear_policy import load_value_uk_nuclear_policy

    return {str(row["station_id"]): row for row in load_value_uk_nuclear_policy()["existing_stations"]}


def _planned_project_ids() -> set[str]:
    from .nuclear_policy import load_value_uk_nuclear_policy

    return {str(row["project_id"]) for row in load_value_uk_nuclear_policy().get("planned_projects") or ()}


def nuclear_load_factor(asset_id: str, capacity_mw: float, extensions: Mapping[str, Any] | None = None
                        ) -> tuple[float, dict[str, Any]]:
    table = load_table()["nuclear"]
    extensions = dict(extensions or {})
    candidates = [asset_id, str(extensions.get("source_project_id") or ""), str(extensions.get("base_asset_id") or "")]
    for candidate in candidates:
        station_id = candidate.split(":", 1)[1] if candidate.startswith("nuclear:") else candidate
        row = table["stations"].get(station_id)
        if row is not None:
            model_mw = float(capacity_mw) if capacity_mw > 0 else float(row["pris_reference_mw"])
            factor = min(1.0, float(row["pris_load_factor"]) * float(row["pris_reference_mw"]) / model_mw)
            return factor, {"basis": "station", "station_id": station_id, "reactor_type": row["reactor_type"],
                            "pris_load_factor": float(row["pris_load_factor"]),
                            "pris_reference_mw": float(row["pris_reference_mw"]), "model_capacity_mw": model_mw}
    planned = _planned_project_ids()
    if any(candidate in planned for candidate in candidates if candidate):
        reactor = str(table["planned_project_reactor_type"])
        return float(table["reactor_type_defaults"][reactor]["load_factor"]), {
            "basis": "planned_project_reactor_type", "reactor_type": reactor}
    return float(table["national_aggregate"]["load_factor"]), {"basis": "national_aggregate"}


def generation_end_period(asset_id: str, year: int) -> int | None:
    """First zero period in ``year`` for a station whose announced end month falls in that year."""

    station_id = asset_id.split(":", 1)[1] if asset_id.startswith("nuclear:") else asset_id
    row = _station_records().get(station_id)
    if row is None:
        return None
    announced = str(row.get("announced_generation_end") or "")
    if len(announced) != 7 or announced[4] != "-":
        return None
    end_year, end_month = int(announced[:4]), int(announced[5:])
    if end_year != int(year):
        return None
    return first_period_of_month(end_month + 1) if end_month < 12 else 365 * PERIODS_PER_DAY


def asset_availability(*, asset_id: str, technology: str, capacity_mw: float, year: int, periods: int,
                       extensions: Mapping[str, Any] | None = None) -> tuple[np.ndarray, dict[str, Any]] | None:
    """Per-period availability (0..1) of a nuclear or natural-flow hydro asset, else None."""

    if technology == NUCLEAR:
        factor, evidence = nuclear_load_factor(asset_id, capacity_mw, extensions)
        values = np.full(periods, factor, dtype=float)
        end = generation_end_period(asset_id, year)
        if end is not None:
            values[np.arange(periods) % (365 * PERIODS_PER_DAY) >= end] = 0.0
            evidence = {**evidence, "generation_end_period": end}
    elif technology == HYDRO:
        hydro = load_table()["hydro_natural_flow"]
        shape = np.asarray(hydro["monthly_shape"], dtype=float)
        values = float(hydro["load_factor"]) * shape[month_of_period(periods)]
        evidence = {"basis": "annual_load_factor_x_monthly_shape", "load_factor": float(hydro["load_factor"])}
    else:
        return None
    values = np.clip(values, 0.0, 1.0)
    return values, {"method_id": METHOD_ID, "table_sha256": table_sha256(), "status": "PENDING AUTHOR REVIEW",
                    "annual_mean": float(np.mean(values)), **evidence}


def kernel_availability(assets: Any, *, year: int, periods: int) -> dict[str, np.ndarray]:
    """Capacity-weighted availability of the kernel's single Nuclear / Hydro_natural_flow agents."""

    weighted: dict[str, np.ndarray] = {}
    capacity: dict[str, float] = {}
    for asset in assets:
        if asset.technology not in TECHNOLOGIES or asset.capacity_mw <= 0:
            continue
        if getattr(asset, "status", "operating") not in {"operating", "commissioned"}:
            continue
        profile = asset_availability(asset_id=asset.asset_id, technology=asset.technology,
                                     capacity_mw=float(asset.capacity_mw), year=year, periods=periods,
                                     extensions=dict(getattr(asset, "extensions", {}) or {}))
        assert profile is not None
        weighted[asset.technology] = weighted.get(asset.technology, np.zeros(periods)) + profile[0] * asset.capacity_mw
        capacity[asset.technology] = capacity.get(asset.technology, 0.0) + float(asset.capacity_mw)
    return {technology: weighted[technology] / capacity[technology] for technology in weighted}
