"""Typed run-of-river and conventional-reservoir hydrology contracts.

Pumped hydro is intentionally absent.  It remains an electrical storage
technology with charging and round-trip losses in the VALUE storage catalogue.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import linprog


@dataclass(frozen=True)
class HydroSite:
    site_id: str
    technology_class: str
    bus_id: str
    capacity_mw: float
    turbine_efficiency: float
    provenance: Mapping[str, object]
    conversion_mwh_per_water_unit: float | None = None
    schema_version: str = "value.hydrology-site/v1"

    def validate(self) -> None:
        if self.technology_class not in {"run_of_river", "reservoir"}:
            raise ValueError(f"Unknown hydrology technology at {self.site_id}")
        if self.capacity_mw <= 0 or not math.isfinite(self.capacity_mw):
            raise ValueError(f"Hydrology site {self.site_id} has invalid capacity")
        if not 0 < self.turbine_efficiency <= 1:
            raise ValueError(f"Hydrology site {self.site_id} has invalid turbine efficiency")
        if not self.provenance.get("source") or not self.provenance.get("licence"):
            raise ValueError(f"Hydrology site {self.site_id} lacks provenance/licence")


@dataclass(frozen=True)
class HydroAssetSiteMap:
    asset_id: str
    site_id: str
    share: float = 1.0
    schema_version: str = "value.hydrology-asset-site-map/v1"

    def validate(self) -> None:
        if not self.asset_id or not self.site_id or not 0 < self.share <= 1:
            raise ValueError("Hydrology asset/site mapping is invalid")


@dataclass(frozen=True)
class CanonicalInflow:
    site_id: str
    period_ids: Sequence[str]
    values: Sequence[float]
    unit: str
    interval_hours: float
    timezone: str
    source_sha256: str
    adapter_version: str
    imputation: str = "none"
    schema_version: str = "value.hydrology-inflow/v1"

    def validate(self, expected_period_ids: Sequence[str] | None = None) -> None:
        if len(self.period_ids) != len(self.values) or not self.period_ids:
            raise ValueError(f"Inflow {self.site_id} has insufficient chronology")
        if len(set(self.period_ids)) != len(self.period_ids):
            raise ValueError(f"Inflow {self.site_id} contains duplicate timestamps")
        if expected_period_ids is not None and tuple(self.period_ids) != tuple(expected_period_ids):
            raise ValueError(f"Inflow {self.site_id} has a missing or reordered period")
        if self.interval_hours <= 0 or not self.timezone:
            raise ValueError(f"Inflow {self.site_id} has invalid calendar semantics")
        if self.unit not in {"p.u.", "water_unit/period"}:
            raise ValueError(f"Inflow {self.site_id} uses impossible/unsupported unit {self.unit}")
        if any(not math.isfinite(value) or value < 0 for value in self.values):
            raise ValueError(f"Inflow {self.site_id} contains negative/non-finite values")
        if len(self.source_sha256) != 64:
            raise ValueError(f"Inflow {self.site_id} has no raw object hash")


@dataclass(frozen=True)
class ReservoirParameters:
    site_id: str
    min_volume: float
    max_volume: float
    initial_volume: float
    terminal_volume: float | None
    max_turbine_release_per_period: float
    max_total_release_per_period: float
    minimum_environmental_release_per_period: float
    conversion_mwh_per_water_unit: float
    turbine_efficiency: float
    turbine_capacity_mw: float
    information_structure: str = "perfect_foresight"
    water_unit: str = "water_unit"
    schema_version: str = "value.reservoir-parameters/v1"

    def validate(self, period_hours: float) -> None:
        numeric = (
            self.min_volume, self.max_volume, self.initial_volume,
            self.max_turbine_release_per_period, self.max_total_release_per_period,
            self.minimum_environmental_release_per_period,
            self.conversion_mwh_per_water_unit, self.turbine_capacity_mw,
        )
        if any(not math.isfinite(value) or value < 0 for value in numeric):
            raise ValueError(f"Reservoir {self.site_id} contains a negative/non-finite parameter")
        if not self.min_volume <= self.initial_volume <= self.max_volume:
            raise ValueError(f"Reservoir {self.site_id} initial volume is outside bounds")
        if self.terminal_volume is not None and not self.min_volume <= self.terminal_volume <= self.max_volume:
            raise ValueError(f"Reservoir {self.site_id} terminal volume is outside bounds")
        if self.max_total_release_per_period < self.max_turbine_release_per_period:
            raise ValueError(f"Reservoir {self.site_id} total release is below turbine release")
        if not 0 < self.turbine_efficiency <= 1 or period_hours <= 0:
            raise ValueError(f"Reservoir {self.site_id} has invalid conversion/clock")
        energy_from_max_release = (
            self.max_turbine_release_per_period
            * self.conversion_mwh_per_water_unit
            * self.turbine_efficiency
        )
        if energy_from_max_release > self.turbine_capacity_mw * period_hours + 1e-9:
            raise ValueError(f"Reservoir {self.site_id} release exceeds turbine power capacity")
        if self.information_structure not in {"myopic", "rolling_horizon", "perfect_foresight"}:
            raise ValueError(f"Reservoir {self.site_id} has unknown information structure")


@dataclass(frozen=True)
class RunOfRiverResult:
    site_id: str
    available_energy_mwh: Sequence[float]
    accepted_generation_mwh: Sequence[float]
    curtailed_energy_mwh: Sequence[float]
    information_structure: str = "period_local_no_storage"
    schema_version: str = "value.run-of-river-result/v1"


@dataclass(frozen=True)
class ReservoirDispatchResult:
    site_id: str
    turbine_release: Sequence[float]
    environmental_bypass: Sequence[float]
    spill: Sequence[float]
    end_volume: Sequence[float]
    generation_mwh: Sequence[float]
    water_balance_residual: Sequence[float]
    objective_gbp: float
    solver_status: str
    information_structure: str
    schema_version: str = "value.reservoir-dispatch/v1"


@dataclass(frozen=True)
class HydrologyInputBundle:
    """Canonical, validated hydrology inputs shared by preview and execution wiring."""

    sites: Sequence[HydroSite]
    asset_site_mappings: Sequence[HydroAssetSiteMap]
    run_of_river_inflows: Mapping[str, CanonicalInflow]
    reservoir_inflows: Mapping[str, CanonicalInflow]
    reservoir_parameters: Mapping[str, ReservoirParameters]
    source_sha256: Mapping[str, str]
    schema_version: str = "value.hydrology-input-bundle/v1"


def validate_site_mapping(
    sites: Sequence[HydroSite], mappings: Sequence[HydroAssetSiteMap]
) -> dict[str, HydroSite]:
    by_site: dict[str, HydroSite] = {}
    for site in sites:
        site.validate()
        if site.site_id in by_site:
            raise ValueError(f"Duplicate hydrological site ID: {site.site_id}")
        by_site[site.site_id] = site
    by_asset: dict[str, float] = {}
    result: dict[str, HydroSite] = {}
    for mapping in mappings:
        mapping.validate()
        if mapping.site_id not in by_site:
            raise ValueError(f"Hydrology mapping has dangling site {mapping.site_id}")
        by_asset[mapping.asset_id] = by_asset.get(mapping.asset_id, 0.0) + mapping.share
        if by_asset[mapping.asset_id] > 1 + 1e-12:
            raise ValueError(f"Hydrology asset {mapping.asset_id} is double-mapped")
        result[mapping.asset_id] = by_site[mapping.site_id]
    return result


def run_of_river_dispatch(
    site: HydroSite,
    inflow: CanonicalInflow,
    *,
    accepted_mwh: Sequence[float] | None = None,
) -> RunOfRiverResult:
    site.validate()
    inflow.validate()
    if site.technology_class != "run_of_river" or site.site_id != inflow.site_id:
        raise ValueError("Run-of-river site/inflow mapping is incompatible")
    maximum = site.capacity_mw * inflow.interval_hours
    if inflow.unit == "p.u.":
        if any(value > 1 for value in inflow.values):
            raise ValueError("Normalized run-of-river availability exceeds 1 p.u.")
        available = [maximum * value for value in inflow.values]
    else:
        if site.conversion_mwh_per_water_unit is None:
            raise ValueError("Water-volume inflow requires a declared MWh conversion")
        available = [
            min(maximum, value * site.conversion_mwh_per_water_unit * site.turbine_efficiency)
            for value in inflow.values
        ]
    accepted = list(available if accepted_mwh is None else accepted_mwh)
    if len(accepted) != len(available):
        raise ValueError("Run-of-river accepted generation has the wrong chronology")
    if any(value < -1e-12 or value > limit + 1e-9 for value, limit in zip(accepted, available)):
        raise ValueError("Run-of-river dispatch exceeds period-local available energy")
    curtailed = [max(0.0, limit - value) for limit, value in zip(available, accepted)]
    return RunOfRiverResult(site.site_id, tuple(available), tuple(accepted), tuple(curtailed))


def reservoir_dispatch(
    parameters: ReservoirParameters,
    inflow: CanonicalInflow,
    *,
    energy_value_gbp_per_mwh: Sequence[float],
) -> ReservoirDispatchResult:
    inflow.validate()
    parameters.validate(inflow.interval_hours)
    if parameters.site_id != inflow.site_id or inflow.unit != "water_unit/period":
        raise ValueError("Reservoir inflow/site/unit is incompatible")
    periods = len(inflow.values)
    if len(energy_value_gbp_per_mwh) != periods:
        raise ValueError("Reservoir value chronology is incomplete")
    # q turbine release, e environmental bypass, w spill, s end volume.
    q0, e0, w0, s0 = 0, periods, 2 * periods, 3 * periods
    variables = 4 * periods
    conversion = parameters.conversion_mwh_per_water_unit * parameters.turbine_efficiency
    objective = np.zeros(variables)
    objective[q0:q0 + periods] = -np.asarray(energy_value_gbp_per_mwh) * conversion
    objective[w0:w0 + periods] = 1e-9  # deterministic preference against needless spill
    equalities = np.zeros((periods, variables))
    rhs = np.asarray(inflow.values, dtype=float)
    for period in range(periods):
        equalities[period, q0 + period] = 1
        equalities[period, e0 + period] = 1
        equalities[period, w0 + period] = 1
        equalities[period, s0 + period] = 1
        if period == 0:
            rhs[period] += parameters.initial_volume
        else:
            equalities[period, s0 + period - 1] = -1
    inequalities = np.zeros((2 * periods, variables))
    upper = np.zeros(2 * periods)
    for period in range(periods):
        inequalities[period, q0 + period] = -1
        inequalities[period, e0 + period] = -1
        upper[period] = -parameters.minimum_environmental_release_per_period
        inequalities[periods + period, q0 + period] = 1
        inequalities[periods + period, e0 + period] = 1
        upper[periods + period] = parameters.max_total_release_per_period
    storage_bounds = [(parameters.min_volume, parameters.max_volume)] * periods
    if parameters.terminal_volume is not None:
        storage_bounds[-1] = (parameters.terminal_volume, parameters.terminal_volume)
    bounds = (
        [(0, parameters.max_turbine_release_per_period)] * periods
        + [(0, parameters.max_total_release_per_period)] * periods
        + [(0, None)] * periods
        + storage_bounds
    )
    solved = linprog(
        objective, A_ub=inequalities, b_ub=upper, A_eq=equalities,
        b_eq=rhs, bounds=bounds, method="highs",
    )
    if not solved.success:
        raise ValueError(f"Reservoir dispatch infeasible: {solved.message}")
    values = solved.x
    q = values[q0:q0 + periods]
    bypass = values[e0:e0 + periods]
    spill = values[w0:w0 + periods]
    storage = values[s0:s0 + periods]
    residuals = []
    previous = parameters.initial_volume
    for period in range(periods):
        residuals.append(
            previous + inflow.values[period] - q[period] - bypass[period] - spill[period] - storage[period]
        )
        previous = storage[period]
    generation = q * conversion
    return ReservoirDispatchResult(
        parameters.site_id, tuple(q), tuple(bypass), tuple(spill), tuple(storage),
        tuple(generation), tuple(residuals), float(-solved.fun), "optimal",
        parameters.information_structure,
    )


def adapt_hydrology_csv(
    path: Path,
    *,
    site_id: str,
    unit: str,
    interval_hours: float,
    timezone: str,
    adapter_version: str = "value.hydrology-csv/v1",
) -> CanonicalInflow:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    periods: list[str] = []
    values: list[float] = []
    for row in rows:
        if str(row.get("site_id") or "") != site_id:
            continue
        timestamp = str(row.get("timestamp") or "")
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Hydrology timestamp is invalid: {timestamp}") from exc
        if parsed.tzinfo is None:
            raise ValueError("Hydrology timestamps must carry a timezone")
        if str(row.get("unit") or unit) != unit:
            raise ValueError("Hydrology CSV mixes incompatible units")
        periods.append(timestamp)
        values.append(float(row["value"]))
    result = CanonicalInflow(
        site_id, tuple(periods), tuple(values), unit, interval_hours, timezone,
        digest, adapter_version,
    )
    result.validate()
    return result


def load_hydrology_inputs_from_pack(
    pack_root: Path,
    manifest: Mapping[str, object],
    *,
    expected_period_ids: Sequence[str] | None = None,
) -> HydrologyInputBundle:
    """Load the five declared hydrology roles through one canonical adapter.

    This function does not dispatch water or electricity.  It is intentionally
    reusable by run preparation and by the bounded readiness preview so the UI
    cannot invent a second column mapping.
    """

    root = pack_root.resolve()
    bindings = dict(manifest.get("bindings") or {})

    def bound(role: str) -> tuple[Path, Mapping[str, object]]:
        binding = bindings.get(role)
        if not isinstance(binding, Mapping):
            raise ValueError(f"Hydrology data role is not bound: {role}")
        path = (root / str(binding.get("uri") or "")).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Hydrology binding escapes pack root: {role}") from exc
        if not path.is_file():
            raise ValueError(f"Hydrology binding is missing: {role}")
        return path, binding

    def rows(role: str, json_key: str) -> tuple[list[Mapping[str, object]], Path]:
        path, _binding = bound(role)
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload = payload.get(json_key) if isinstance(payload, Mapping) else payload
            if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
                raise ValueError(f"Hydrology role {role} must contain a {json_key} array")
            return list(payload), path
        if path.suffix.lower() != ".csv":
            raise ValueError(f"Hydrology role {role} has no shipped parser for {path.suffix}")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle)), path

    site_rows, site_path = rows("value.hydrology.site-catalogue", "sites")
    sites = tuple(HydroSite(
        site_id=str(item.get("site_id") or ""),
        technology_class=str(item.get("technology_class") or ""),
        bus_id=str(item.get("bus_id") or ""),
        capacity_mw=float(item.get("capacity_mw") or 0.0),
        turbine_efficiency=float(item.get("turbine_efficiency") or 0.0),
        provenance=(
            dict(item.get("provenance") or {})
            if isinstance(item.get("provenance"), Mapping)
            else {"source": item.get("source"), "licence": item.get("licence")}
        ),
        conversion_mwh_per_water_unit=(
            float(item["conversion_mwh_per_water_unit"])
            if item.get("conversion_mwh_per_water_unit") not in {None, ""} else None
        ),
    ) for item in site_rows)

    mapping_rows, mapping_path = rows("value.hydrology.asset-site-map", "asset_site_mappings")
    mappings = tuple(HydroAssetSiteMap(
        str(item.get("asset_id") or ""),
        str(item.get("site_id") or ""),
        float(item.get("share") or 1.0),
    ) for item in mapping_rows)
    validate_site_mapping(sites, mappings)

    parameter_rows, parameter_path = rows(
        "value.hydrology.reservoir-parameters", "reservoirs"
    )
    parameters = {
        str(item.get("site_id") or ""): ReservoirParameters(
            site_id=str(item.get("site_id") or ""),
            min_volume=float(item.get("min_volume") or 0.0),
            max_volume=float(item.get("max_volume") or 0.0),
            initial_volume=float(item.get("initial_volume") or 0.0),
            terminal_volume=(
                float(item["terminal_volume"])
                if item.get("terminal_volume") not in {None, ""} else None
            ),
            max_turbine_release_per_period=float(item.get("max_turbine_release_per_period") or 0.0),
            max_total_release_per_period=float(item.get("max_total_release_per_period") or 0.0),
            minimum_environmental_release_per_period=float(item.get("minimum_environmental_release_per_period") or 0.0),
            conversion_mwh_per_water_unit=float(item.get("conversion_mwh_per_water_unit") or 0.0),
            turbine_efficiency=float(item.get("turbine_efficiency") or 0.0),
            turbine_capacity_mw=float(item.get("turbine_capacity_mw") or 0.0),
            information_structure=str(item.get("information_structure") or "perfect_foresight"),
            water_unit=str(item.get("water_unit") or "water_unit"),
        )
        for item in parameter_rows
    }

    def inflows(role: str, expected_technology: str, default_unit: str) -> tuple[dict[str, CanonicalInflow], Path]:
        path, binding = bound(role)
        if path.suffix.lower() != ".csv":
            raise ValueError(f"Hydrology role {role} has no shipped parser for {path.suffix}")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            raw_rows = list(csv.DictReader(handle))
        result: dict[str, CanonicalInflow] = {}
        for site in sites:
            if site.technology_class != expected_technology:
                continue
            site_rows = [item for item in raw_rows if str(item.get("site_id") or "") == site.site_id]
            if not site_rows:
                raise ValueError(f"Hydrology inflow is missing for site {site.site_id}")
            units = {str(item.get("unit") or binding.get("unit") or default_unit) for item in site_rows}
            intervals = {float(item.get("interval_hours") or binding.get("interval_hours") or 0.0) for item in site_rows}
            timezones = {str(item.get("timezone") or binding.get("timezone") or manifest.get("timezone") or "") for item in site_rows}
            if len(units) != 1 or len(intervals) != 1 or len(timezones) != 1:
                raise ValueError(f"Hydrology inflow metadata is inconsistent for site {site.site_id}")
            series = adapt_hydrology_csv(
                path,
                site_id=site.site_id,
                unit=next(iter(units)),
                interval_hours=next(iter(intervals)),
                timezone=next(iter(timezones)),
            )
            series.validate(expected_period_ids=expected_period_ids)
            result[site.site_id] = series
        return result, path

    ror, ror_path = inflows(
        "value.hydrology.run-of-river-inflow", "run_of_river", "p.u."
    )
    reservoir, reservoir_path = inflows(
        "value.hydrology.reservoir-inflow", "reservoir", "water_unit/period"
    )
    reservoir_site_ids = {item.site_id for item in sites if item.technology_class == "reservoir"}
    if set(parameters) != reservoir_site_ids:
        missing = sorted(reservoir_site_ids.difference(parameters))
        extra = sorted(set(parameters).difference(reservoir_site_ids))
        raise ValueError(f"Reservoir parameter/site mismatch; missing={missing}, extra={extra}")
    for site_id, item in parameters.items():
        item.validate(reservoir[site_id].interval_hours)

    source_paths = {
        "value.hydrology.site-catalogue": site_path,
        "value.hydrology.asset-site-map": mapping_path,
        "value.hydrology.run-of-river-inflow": ror_path,
        "value.hydrology.reservoir-inflow": reservoir_path,
        "value.hydrology.reservoir-parameters": parameter_path,
    }
    return HydrologyInputBundle(
        sites, mappings, ror, reservoir, parameters,
        {role: hashlib.sha256(path.read_bytes()).hexdigest() for role, path in source_paths.items()},
    )
