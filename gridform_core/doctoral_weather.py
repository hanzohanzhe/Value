"""Site weather adapter matching the doctoral simulation_model.py calculations.

Only paths, resource identity and array packaging are adapted. No smoothing,
annual-energy calibration, hub-height correction or technology-average fallback
is performed. The preserved research source is not imported or modified.
"""
from __future__ import annotations

import hashlib
from contextlib import ExitStack
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .v2.contracts import AssetStateV2
from .doctoral_weather_mapping import representative_sites, source_weights


METHOD_ID = "value.doctoral-site-weather/v1"
VRE = {"solar", "onshore", "offshore"}


def weather_execution_identity() -> dict[str, object]:
    """Bind checkpoints to the actual adapter and its chronology integration.

    Module manifests alone identify a wrapper, not these implementation files.
    Keep this separate from user scientific parameters and saved project JSON.
    """
    root = Path(__file__).resolve().parent
    return {"method_id": METHOD_ID, "source_sha256": {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("doctoral_weather.py", "canonical_psm_data.py", "doctoral_weather_mapping.py",
                     "builtin/scheme_c_1000twh/v2_module_definitions.py",
                     "builtin/scheme_c_1000twh/runtime_compat/map_projects_to_generators_by_location.py",
                     # P0-5b: corrected-profile weather v2, loss factors, firm availability.
                     "site_weather.py", "firm_availability.py",
                     # F2 (A13): corrected-profile solar plane-of-array irradiance.
                     "solar_irradiance.py",
                     "data/weather/value_uk_vre_loss_factors_v1.json",
                     "data/nuclear/value_uk_firm_availability_v1.json")
    }}


def uses_doctoral_weather(manifest: Mapping[str, object]) -> bool:
    if manifest.get("id") in {"value-uk-open-data-pack-v1", "value-uk-1000twh-reproduction"}:
        return True
    bindings = dict(manifest.get("bindings") or {})
    return any(str(dict(bindings.get(role) or {}).get("uri", "")).lower().endswith(".nc")
               for role in ("weather.wind", "weather.solar"))


def _verified_hash(path: Path, expected: str) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    observed = digest.hexdigest()
    if not expected or observed != expected:
        raise ValueError(f"Doctoral weather SHA256 mismatch: {path.name}; expected {expected}, observed {observed}")
    return observed


def _point_series(ds, variable: str, latitude: float, longitude: float):
    lats = np.asarray(ds.variables["latitude"][:])
    lons = np.asarray(ds.variables["longitude"][:])
    lat_index = int(np.abs(lats - latitude).argmin())
    lon_index = int(np.abs(lons - longitude).argmin())
    var = ds.variables[variable]
    # These are the two layouts supported by the original acm_* routines.
    if var.ndim == 4:
        raw = var[lat_index, lon_index, :, :]
    elif var.ndim == 3:
        raw = var[:, lat_index, lon_index]
    else:
        raise ValueError(f"Unsupported doctoral weather layout for {variable}: {var.dimensions}")
    if np.ma.is_masked(raw):
        raise ValueError(f"Missing doctoral weather values at {latitude}, {longitude}: {variable}")
    values = np.asarray(raw).flatten()
    if not values.size or not np.all(np.isfinite(values)):
        raise ValueError(f"Invalid doctoral weather values: {variable}")
    return values, (float(lats[lat_index]), float(lons[lon_index]))


def _wind_unit_output(speed, *, onshore: bool):
    # Source: _wind_power_curve and piecewise_limit1..5. Keep endpoint rules
    # and scalar evaluation order (in particular, cut-out itself is included).
    rated, cut_out = (9.7, 25) if onshore else (10.5, 30)
    if speed < 3 or speed > cut_out:
        return 0
    if speed >= rated:
        return 20
    normalized = (speed**3 - 3**3) / (rated**3 - 3**3)
    return max(0, min(20, normalized * 20))


def _source_identity(asset: AssetStateV2, fleet: Mapping[str, object]) -> tuple[str, str]:
    locations = dict(fleet.get("locations") or {})
    generators = dict(fleet.get("generators") or {})
    extensions = dict(asset.extensions)
    candidates = [extensions.get("weather_source_asset_id"), asset.asset_id,
                  extensions.get("assigned_generator"), extensions.get("investment_owner_id"),
                  extensions.get("source_agent_id"), extensions.get("base_asset_id")]
    for candidate in candidates:
        name = str(candidate or "")
        matches_tech = (name.startswith("offshore") if asset.technology == "offshore"
                        else name.startswith(asset.technology + "_"))
        if name not in generators or not matches_tech:
            continue
        key = name if asset.technology == "offshore" else name.split("_", 1)[1]
        if key in locations:
            return name, key
    # A project with no documented representative-point assignment must not
    # silently receive the country's common CSV or an invented nearest site.
    raise ValueError(f"Missing doctoral weather identity mapping for asset {asset.asset_id} ({asset.technology})")


def site_weather_profiles(*, paths: Mapping[str, Path], hashes: Mapping[str, str],
                          fleet: Mapping[str, object], assets: Sequence[AssetStateV2],
                          periods: int, period_hours: float, method=None,
                          bindings: Mapping[str, Mapping] | None = None) -> dict[str, tuple[tuple[float, ...], dict]]:
    """Per-asset dispatch availability from the representative sites.

    ``method`` (``site_weather.SiteWeatherMethod``) is None or frozen for the
    doctoral profile (this function's 35aadb3 code path); the corrected profile
    passes weather v2 / loss factors, computed by ``site_weather.site_cf_by_source``
    (the same arrays the retained kernel receives, plan 4.5 S5).
    """
    if period_hours != 0.5:
        raise ValueError("Doctoral weather requires the original 0.5-hour (half-hour) clock")
    if periods <= 0:
        raise ValueError("Doctoral weather needs a positive period count")
    selected = [asset for asset in assets if asset.technology in VRE and asset.capacity_mw > 0]
    if not selected:
        return {}
    sites = representative_sites(fleet)
    lineages = {a.asset_id: source_weights(a, sites) for a in selected}
    source_names = dict.fromkeys(name for weights in lineages.values() for name in weights)
    source_assets = [AssetStateV2(name, sites[name]["technology"], 1.) for name in source_names]
    identities = {a.asset_id: _source_identity(a, fleet) for a in source_assets}
    roles = {"weather.solar" if a.technology == "solar" else "weather.wind" for a in selected}
    if method is not None and not method.frozen:
        from .site_weather import site_cf_by_source

        corrected = site_cf_by_source(paths=paths, hashes=hashes, bindings=bindings, sites=sites,
                                      sources=[identities[a.asset_id][0] for a in source_assets],
                                      periods=periods, method=method)
        result = {a.asset_id: (tuple(float(v) for v in corrected[identities[a.asset_id][0]][0]),
                               {**corrected[identities[a.asset_id][0]][1],
                                "source_location_key": identities[a.asset_id][1]})
                  for a in source_assets}
        verified = {role: next(e["source_sha256"] for _, e in result.values() if e["source_role"] == role)
                    for role in roles}
        return _map_lineages(selected, lineages, result, verified, periods, method.method_id)
    verified = {role: _verified_hash(paths[role], hashes.get(role, "")) for role in roles}
    from netCDF4 import Dataset

    result = {}
    cache = {}
    with ExitStack() as stack:
        datasets = {role: stack.enter_context(Dataset(str(paths[role]), "r")) for role in roles}
        for asset in source_assets:
            source_id, key = identities[asset.asset_id]
            cache_key = (asset.technology, key)
            if cache_key not in cache:
                point = fleet["locations"][key]
                lat, lon = float(point["lat"]), float(point["lon"])
                role = "weather.solar" if asset.technology == "solar" else "weather.wind"
                ds = datasets[role]
                if asset.technology == "solar":
                    raw, grid_point = _point_series(ds, "ssrd", lat, lon)
                    # Original piecewise_limit(ssrd) / 3600000, without clipping.
                    hourly = np.asarray([v / 3600000 if 3600 < v <= 36000000 else 0 for v in raw])
                    curve = "piecewise_limit(ssrd)/3600000"
                else:
                    if "wind_speed" in ds.variables:
                        speed, grid_point = _point_series(ds, "wind_speed", lat, lon)
                        energy = speed**2
                        variable = "wind_speed"
                    else:
                        u, grid_point = _point_series(ds, "u100", lat, lon)
                        v, _ = _point_series(ds, "v100", lat, lon)
                        energy = u**2 + v**2
                        variable = "u100,v100"
                    # Original run_simulation uses raw_energy ** 0.5, not a
                    # power curve on annual mean u/v or on a mean CF.
                    hourly = np.asarray([_wind_unit_output(v ** 0.5, onshore=asset.technology == "onshore") / 20
                                         for v in energy])
                    curve = ("piecewise_limit5" if asset.technology == "onshore" else "piecewise_limit1..4") + "/20"
                # IterLimit repeats every source hour twice, then wraps. A
                # 17520-period year consumes the first 8760 of 8784 input hours.
                values = tuple(float(v) for v in hourly[(np.arange(periods) // 2) % len(hourly)])
                if not all(np.isfinite(values)):
                    raise ValueError(f"Non-finite converted doctoral weather: {source_id}")
                evidence = {"method_id": METHOD_ID, "source_role": role,
                            "source_sha256": verified[role], "source_location_key": key,
                            "requested_latitude": lat, "requested_longitude": lon,
                            "grid_latitude": grid_point[0], "grid_longitude": grid_point[1],
                            "source_variable": "ssrd" if asset.technology == "solar" else variable,
                            "source_hour_count": len(hourly), "curve": curve,
                            "clock": "IterLimit: repeat each hour twice; wrap in source order",
                            "period_hours": 0.5, "period_count": periods,
                            "availability_sha256": hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()}
                cache[cache_key] = values, evidence
            values, evidence = cache[cache_key]
            result[asset.asset_id] = values, {**evidence, "source_asset_id": source_id}
    return _map_lineages(selected, lineages, result, verified, periods, METHOD_ID)


def _map_lineages(selected, lineages, result, verified, periods, method_id):
    mapped, mixtures = {}, {}
    for asset in selected:
        weights = lineages[asset.asset_id]
        if len(weights) == 1 and next(iter(weights.values())) == 1.:
            mapped[asset.asset_id] = result[next(iter(weights))]
            continue
        key = tuple(sorted(weights.items()))
        if key not in mixtures:
            combined = np.zeros(periods)
            components = []
            for name, weight in key:
                values, evidence = result[name]
                combined += np.asarray(values) * weight
                components.append({"source_asset_id": name, "weight": weight,
                                   "availability_sha256": evidence["availability_sha256"]})
            mixtures[key] = (tuple(float(v) for v in combined), {
                "method_id": method_id, "source_asset_id": None,
                "assignment": "frozen doctoral representative-capacity allocation",
                "source_weights": dict(key), "source_components": components,
                "source_role": "weather.solar" if asset.technology == "solar" else "weather.wind",
                "source_sha256": verified["weather.solar" if asset.technology == "solar" else "weather.wind"],
                "period_hours": .5, "period_count": periods,
                "availability_sha256": hashlib.sha256(combined.astype("<f8").tobytes()).hexdigest(),
            })
        mapped[asset.asset_id] = mixtures[key]
    return mapped
