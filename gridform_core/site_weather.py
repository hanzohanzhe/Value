"""Per-site VRE availability from NetCDF weather, shared by the canonical adapter and the kernel (P0-5b).

One conversion serves both dispatch paths (plan 4.5 S5: ``site_cf_by_source``):

* the canonical adapter (``doctoral_weather.site_weather_profiles``) maps the
  per-source arrays onto assets;
* the retained kernel receives the same arrays through its module runtime
  (``kernel_injection``) under the corrected profile, instead of re-reading the
  files with its own ``IterLimit`` clock.

Two method switches, both profile-gated (C15: asked through
``ResolvedMethodology.enabled``):

* ``p05.weather-time-convention`` (P6-06, weather v2): ERA5 accumulations are
  stamped at the END of their hour, so the half-hour period ``t`` of the hour
  ``t // 2`` takes the value stamped ``t // 2 + 1``; instantaneous fields take
  the timestamp nearest to the period midpoint, ``(t + 1) // 2``.  The frozen
  v1 clock serves hour ``t // 2`` for both periods of the hour.
* ``p05.vre-loss-factors`` (P6-08, decisions Q15/A1): the free-stream single
  turbine power-curve CF is multiplied by literature wake, availability and
  electrical loss factors; solar GHI/1 kW m-2 by a performance ratio.  There is
  no calibration to statistical load factors; the factors and their sources
  are in ``data/weather/value_uk_vre_loss_factors_v1.json``.

The doctoral profile keeps v1 and no factors, bit-identical to 35aadb3.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

WEATHER_V1 = "value.doctoral-site-weather/v1"
WEATHER_V2 = "value.site-weather/v2"
TIME_CONVENTION_CORRECTION = "p05.weather-time-convention"
LOSS_FACTOR_CORRECTION = "p05.vre-loss-factors"
LOSS_FACTORS_PATH = Path(__file__).resolve().parent / "data" / "weather" / "value_uk_vre_loss_factors_v1.json"
VRE = ("solar", "onshore", "offshore")
WIND_UNIT_MW = 20.0
# Time conventions of an hourly source value.
ACCUMULATION_END = "accumulation_end_of_hour"   # ERA5 ssrd: the hour ENDING at the stamp
INSTANT = "instantaneous"                       # ERA5 u100/v100 analyses; synthetic samples
TIME_CONVENTIONS = (ACCUMULATION_END, INSTANT)


@lru_cache(maxsize=1)
def load_loss_factors() -> dict[str, Any]:
    table = json.loads(LOSS_FACTORS_PATH.read_text(encoding="utf-8"))
    if table.get("schema_version") != "value.vre-loss-factors/v1":
        raise ValueError("Unsupported VRE loss-factor table")
    for technology in VRE:
        entry = table["technologies"][technology]
        product = 1.0
        for component in entry["components"]:
            value = float(component["central"])
            if not 0.0 < value <= 1.0:
                raise ValueError(f"Loss factor out of range: {technology}.{component['id']}")
            product *= value
        if abs(product - float(entry["multiplier"])) > 1e-12:
            raise ValueError(f"Loss multiplier of {technology} is not the product of its components")
    return table


def loss_factor_table_sha256() -> str:
    return hashlib.sha256(LOSS_FACTORS_PATH.read_bytes()).hexdigest()


@dataclass(frozen=True)
class SiteWeatherMethod:
    """How NetCDF weather becomes per-period site capacity factors."""

    clock: str                      # "v1" (frozen IterLimit) or "v2" (ERA5 conventions)
    loss_factors: bool              # literature loss factors applied

    @property
    def frozen(self) -> bool:
        return self.clock == "v1" and not self.loss_factors

    @property
    def method_id(self) -> str:
        if self.frozen:
            return WEATHER_V1
        return f"{WEATHER_V2}+clock-{self.clock}+losses-{'v1' if self.loss_factors else 'none'}"

    def multiplier(self, technology: str) -> float:
        if not self.loss_factors:
            return 1.0
        return float(load_loss_factors()["technologies"][technology]["multiplier"])

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {"method_id": self.method_id, "clock": self.clock,
                                    "loss_factors": self.loss_factors}
        if self.loss_factors:
            value["loss_factor_table_sha256"] = loss_factor_table_sha256()
            value["multipliers"] = {technology: self.multiplier(technology) for technology in VRE}
        return value


FROZEN = SiteWeatherMethod(clock="v1", loss_factors=False)


def method_for(methodology: Any) -> SiteWeatherMethod:
    return SiteWeatherMethod(
        clock="v2" if methodology.enabled("p05.weather-time-convention") else "v1",
        loss_factors=bool(methodology.enabled("p05.vre-loss-factors")),
    )


def method_for_profile(profile_id: str | None) -> SiteWeatherMethod:
    from .methodology import resolve_methodology

    return method_for(resolve_methodology(profile_id))


def variable_time_convention(binding: Mapping[str, Any] | None, variable: Any) -> str:
    """Declared convention first (binding ``time_convention``), then the GRIB step type, else instantaneous."""

    declared = str(dict(binding or {}).get("time_convention") or "")
    if declared:
        if declared not in TIME_CONVENTIONS:
            raise ValueError(f"Unknown weather time_convention {declared!r}; expected one of {TIME_CONVENTIONS}")
        return declared
    step_type = str(getattr(variable, "GRIB_stepType", "") or "")
    return ACCUMULATION_END if step_type == "accum" else INSTANT


def hour_index(periods: int, hours: int, clock: str, convention: str) -> np.ndarray:
    """Source-hour index of each half-hour period (wrapping in source order)."""

    t = np.arange(periods)
    if clock == "v1":
        return (t // 2) % hours
    if convention == ACCUMULATION_END:
        return (t // 2 + 1) % hours
    return ((t + 1) // 2) % hours


def wind_unit_output(speed: float, *, onshore: bool) -> float:
    # Source: _wind_power_curve and piecewise_limit1..5 (cut-out itself included).
    rated, cut_out = (9.7, 25) if onshore else (10.5, 30)
    if speed < 3 or speed > cut_out:
        return 0
    if speed >= rated:
        return 20
    normalized = (speed**3 - 3**3) / (rated**3 - 3**3)
    return max(0, min(20, normalized * 20))


def point_series(ds: Any, variable: str, latitude: float, longitude: float):
    lats = np.asarray(ds.variables["latitude"][:])
    lons = np.asarray(ds.variables["longitude"][:])
    lat_index = int(np.abs(lats - latitude).argmin())
    lon_index = int(np.abs(lons - longitude).argmin())
    var = ds.variables[variable]
    if var.ndim == 4:
        raw = var[lat_index, lon_index, :, :]
    elif var.ndim == 3:
        raw = var[:, lat_index, lon_index]
    else:
        raise ValueError(f"Unsupported weather layout for {variable}: {var.dimensions}")
    if np.ma.is_masked(raw):
        raise ValueError(f"Missing weather values at {latitude}, {longitude}: {variable}")
    values = np.asarray(raw).flatten()
    if not values.size or not np.all(np.isfinite(values)):
        raise ValueError(f"Invalid weather values: {variable}")
    return values, (float(lats[lat_index]), float(lons[lon_index]))


def hourly_unit_cf(ds: Any, technology: str, latitude: float, longitude: float,
                   binding: Mapping[str, Any] | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """Hourly free-stream CF (0..1) at the nearest grid point, before any loss factor."""

    if technology == "solar":
        raw, grid = point_series(ds, "ssrd", latitude, longitude)
        hourly = np.asarray([v / 3600000 if 3600 < v <= 36000000 else 0 for v in raw])
        variable, curve = "ssrd", "piecewise_limit(ssrd)/3600000"
        convention = variable_time_convention(binding, ds.variables["ssrd"])
    else:
        if "wind_speed" in ds.variables:
            speed, grid = point_series(ds, "wind_speed", latitude, longitude)
            energy = speed**2
            variable, source = "wind_speed", ds.variables["wind_speed"]
        else:
            u, grid = point_series(ds, "u100", latitude, longitude)
            v, _ = point_series(ds, "v100", latitude, longitude)
            energy = u**2 + v**2
            variable, source = "u100,v100", ds.variables["u100"]
        hourly = np.asarray([wind_unit_output(e ** 0.5, onshore=technology == "onshore") / 20 for e in energy])
        curve = ("piecewise_limit5" if technology == "onshore" else "piecewise_limit1..4") + "/20"
        convention = variable_time_convention(binding, source)
    return hourly, {"grid_latitude": grid[0], "grid_longitude": grid[1], "source_variable": variable,
                    "curve": curve, "source_hour_count": len(hourly), "time_convention": convention}


def verified_sha256(path: Path, expected: str) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    observed = digest.hexdigest()
    if not expected or observed != expected:
        raise ValueError(f"Weather SHA256 mismatch: {path.name}; expected {expected}, observed {observed}")
    return observed


def site_cf_by_source(*, paths: Mapping[str, Path], hashes: Mapping[str, str],
                      bindings: Mapping[str, Mapping[str, Any]] | None,
                      sites: Mapping[str, Mapping[str, Any]], sources: Iterable[str],
                      periods: int, method: SiteWeatherMethod) -> dict[str, tuple[np.ndarray, dict[str, Any]]]:
    """Per-period CF of each representative source site (``doctoral_weather_mapping.representative_sites``).

    Sites sharing technology and location share one array.  The evidence names
    the method, clock, convention, multiplier and an array hash.
    """

    names = list(dict.fromkeys(sources))
    if not names:
        return {}
    roles = {"weather.solar" if sites[name]["technology"] == "solar" else "weather.wind" for name in names}
    verified = {role: verified_sha256(Path(paths[role]), str(hashes.get(role, ""))) for role in roles}
    from netCDF4 import Dataset

    result: dict[str, tuple[np.ndarray, dict[str, Any]]] = {}
    cache: dict[tuple, tuple[np.ndarray, dict[str, Any]]] = {}
    with ExitStack() as stack:
        datasets = {role: stack.enter_context(Dataset(str(paths[role]), "r")) for role in roles}
        for name in names:
            site = sites[name]
            technology = str(site["technology"])
            lat, lon = float(site["lat"]), float(site["lon"])
            key = (technology, lat, lon)
            if key not in cache:
                role = "weather.solar" if technology == "solar" else "weather.wind"
                hourly, evidence = hourly_unit_cf(datasets[role], technology, lat, lon, dict(bindings or {}).get(role))
                index = hour_index(periods, len(hourly), method.clock, evidence["time_convention"])
                values = hourly[index]
                multiplier = method.multiplier(technology)
                if multiplier != 1.0:
                    values = values * multiplier
                values = np.asarray(values, dtype=float)
                if not np.all(np.isfinite(values)):
                    raise ValueError(f"Non-finite converted weather: {name}")
                cache[key] = values, {
                    **evidence, "method_id": method.method_id, "source_role": role,
                    "source_sha256": verified[role], "requested_latitude": lat, "requested_longitude": lon,
                    "clock": ("IterLimit: repeat each hour twice; wrap in source order" if method.clock == "v1"
                              else f"v2 {evidence['time_convention']}: "
                              + ("hour t//2+1" if evidence["time_convention"] == ACCUMULATION_END else "hour (t+1)//2")),
                    "loss_multiplier": multiplier, "period_hours": 0.5, "period_count": periods,
                    "availability_sha256": hashlib.sha256(values.astype("<f8").tobytes()).hexdigest(),
                }
            values, evidence = cache[key]
            result[name] = values, {**evidence, "source_asset_id": name}
    return result


def annual_capacity_factors(profiles: Mapping[str, tuple[np.ndarray, Mapping[str, Any]]],
                            sites: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Unweighted mean CF over the representative sites of each technology (reporting only)."""

    by_technology: dict[str, list[float]] = {}
    for name, (values, _) in profiles.items():
        by_technology.setdefault(str(sites[name]["technology"]), []).append(float(np.mean(values)))
    return {technology: float(np.mean(values)) for technology, values in sorted(by_technology.items())}
