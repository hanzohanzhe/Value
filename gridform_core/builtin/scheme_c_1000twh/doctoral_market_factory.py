"""Construct the static doctoral market from explicit typed/frozen inputs.

Source constructors: simulation_model.py:163-425; original construction loop:
run_investment_analysis_case3_decarbonization_breakdown_cm.py:1579-1596 and
run_investment_analysis.py:2683-2696; source parameters config.py:73-156,196-234.
No runtime disk, source import, environment, or weather-provider access occurs.

Typed OperatingState supplies current capacities (including nuclear policy).
Other constructor values are explicit frozen rows, never guessed from price or
technology averages. Source storage stock is MW-period quantity, so pool_limit
is typed MWh / 0.5; per_pool_limit is typed charging MW. This corrects the source
pumped-hydro table's reversed labels rather than copying those table values.
"""
from __future__ import annotations

import math
from typing import Mapping

from gridform_core.v2.contracts import PSMInput
from . import doctoral_market_kernel as k


FACTORY_SCHEMA = "value.doctoral-market-factory/v1"
COMMON_FIELDS = ("gen_cost", "curtail_cost", "carbon_emission", "capital_cost", "unit_time_cost")
GAS_FIELDS = COMMON_FIELDS + ("alter_limit", "startup_cost", "carbon_intensity", "carbon_price", "fuel_cost", "real_gen_energy")
BIO_FIELDS = GAS_FIELDS + ("energy_limit", "add_energy")
WATER_FIELDS = COMMON_FIELDS + ("alter_limit", "energy_limit", "add_energy", "real_gen_energy")
NUCLEAR_FIELDS = COMMON_FIELDS + ("alter_limit", "startup_cost")
VRE_FIELDS = COMMON_FIELDS + ("real_gen_energy",)
BATTERY_FIELDS = ("storage_fee", "per_storage_fee", "n_1", "n_2", "carbon_emission", "capital_cost")
CONNECTION_FIELDS = ("capital_cost", "carbon_emission", "carbon_intensity")
CONNECTION_SOURCE_KEYS = {
    "france": "Interconnect_France", "netherlands": "Interconnect_Netherland",
    "ireland": "Interconnect_Ireland", "norway": "Interconnect_Norway", "belgium": "Interconnect_Beligum",
}
DoctoralGenerator = k.GasGenerator | k.BiomassGenerator | k.WaterGenerator | k.NuclearGenerator | k.ExpensiverenewableGenerator


def _finite(value, field: str, *, nonnegative=False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid doctoral parameter {field}: expected finite number") from exc
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError(f"Invalid doctoral parameter {field}: expected finite {'nonnegative ' if nonnegative else ''}number")
    return result


def _source_row(rows: Mapping, asset_id: str, extensions: Mapping, group: str) -> tuple[str, Mapping]:
    key = str(extensions.get("doctoral_parameter_source_id", asset_id))
    row = rows.get(key)
    if not isinstance(row, Mapping):
        raise ValueError(f"Missing frozen doctoral {group} row for {asset_id}: {key}; supply an explicit doctoral_parameter_source_id")
    return key, row


def _parameter_extensions(asset, resource) -> Mapping:
    asset_source = asset.extensions.get("doctoral_parameter_source_id")
    resource_source = resource.extensions.get("doctoral_parameter_source_id")
    if asset_source is not None and resource_source is not None and str(asset_source) != str(resource_source):
        raise ValueError(f"Conflicting doctoral parameter source for {asset.asset_id}: {asset_source} / {resource_source}")
    return {**dict(resource.extensions), **dict(asset.extensions)}


def _values(row: Mapping, fields: tuple[str, ...], label: str) -> dict[str, float]:
    missing = [field for field in fields if field not in row or row[field] is None]
    if missing:
        raise ValueError(f"{label} missing constructor fields: {', '.join(missing)}")
    return {field: _finite(row[field], f"{label}.{field}") for field in fields}


def _profile(values, length: int, label: str, *, nonnegative=False, constant=False) -> tuple[float, ...]:
    if constant and len(values) == 1:
        return (_finite(values[0], label, nonnegative=nonnegative),) * length
    if len(values) != length:
        raise ValueError(f"{label} must cover every typed period ({length})")
    return tuple(_finite(value, label, nonnegative=nonnegative) for value in values)


def _connections(chronology, parameters: Mapping, periods: int) -> tuple[k.Connection, ...]:
    imports = {}
    for resource in chronology.resources:
        if resource.resource_type != "import":
            continue
        country = str(resource.extensions.get("country", resource.asset_id.removeprefix("import:")))
        if country in imports:
            raise ValueError(f"Duplicate typed interconnector import for {country}")
        imports[country] = resource
    exports = chronology.extensions.get("boundary_export_envelope_mwh_by_asset", {})
    export_prices = chronology.extensions.get("boundary_export_price_gbp_per_mwh_by_asset", {})
    countries = list(imports)
    for asset_id in exports:
        if not str(asset_id).startswith("export:"):
            raise ValueError(f"Explicit export identity required: {asset_id}")
        country = str(asset_id).removeprefix("export:")
        if country not in countries:
            countries.append(country)
    result = []
    for country in countries:
        resource = imports.get(country)
        export_id = f"export:{country}"
        asset_id = resource.asset_id if resource is not None else export_id
        explicit = resource.extensions.get("doctoral_parameter_source_id") if resource is not None else None
        key = explicit or (asset_id if asset_id in parameters else CONNECTION_SOURCE_KEYS.get(country))
        if key is None or not isinstance(parameters.get(key), Mapping):
            raise ValueError(f"Missing frozen doctoral connection row for {asset_id}: {key}")
        values = _values(parameters[key], CONNECTION_FIELDS, f"connections/{key}")
        connection = k.Connection(name=asset_id, **values)
        import_mw, import_prices = (0.0,) * periods, (0.0,) * periods
        if resource is not None:
            capacity = _finite(resource.capacity_mw, f"{asset_id}.capacity_mw", nonnegative=True)
            availability = _profile(resource.availability, periods, f"{asset_id}.availability", nonnegative=True, constant=True)
            import_mw = tuple(capacity * value for value in availability)
            import_prices = _profile(resource.marginal_cost_profile_gbp_per_mwh, periods, f"{asset_id}.price", constant=True) if resource.marginal_cost_profile_gbp_per_mwh else (_finite(resource.marginal_cost_gbp_per_mwh, f"{asset_id}.price"),) * periods
        export_mw, prices_out = (0.0,) * periods, (0.0,) * periods
        if export_id in exports:
            export_mw = tuple(value / 0.5 for value in _profile(exports[export_id], periods, f"{export_id}.envelope_mwh", nonnegative=True, constant=True))
            if export_id not in export_prices:
                raise ValueError(f"Missing explicit typed export prices: {export_id}")
            prices_out = _profile(export_prices[export_id], periods, f"{export_id}.price", constant=True)
        if any(inward > 0 and outward > 0 for inward, outward in zip(import_mw, export_mw)):
            raise ValueError(f"Doctoral signed connection cannot import and export simultaneously: {country}")
        signed = tuple(inward - outward for inward, outward in zip(import_mw, export_mw))
        prices = tuple(prices_out[index] if export_mw[index] > 0 else import_prices[index] for index in range(periods))
        connection.transfer_constraint, connection.external_price = signed[0], prices[0]
        connection.doctoral_transfer_constraint_mw_by_period = signed
        connection.doctoral_external_price_gbp_per_mwh_by_period = prices
        connection.doctoral_parameter_source_id = str(key)
        connection.doctoral_import_asset_id = resource.asset_id if resource is not None else None
        connection.doctoral_export_asset_id = export_id if export_id in exports else None
        result.append(connection)
    return tuple(result)


def from_doctoral_psm_input(model_input: PSMInput, fleet_parameters: Mapping, battery_parameters: Mapping) -> tuple[tuple[DoctoralGenerator, ...], tuple[k.Battery, ...], tuple[k.Connection, ...]]:
    """Build fresh source-class templates, ready for DoctoralPeriodEngine.

    fleet_parameters contains ``generators`` and ``connections`` mappings;
    battery_parameters is the frozen battery-row mapping. Rows are keyed by
    typed asset ID, or by an explicit asset extension
    ``doctoral_parameter_source_id``. Source ``name``/capacity table fields do
    not override typed IDs/current capacities. Cash/ramp/budget values are not
    automatically scaled when a caller reuses a template for another asset.

    Opening SOC must be zero: nonzero inventory requires a validated engine
    checkpoint carrying batch ages and costs. Each connection carries full
    typed period profiles; the period engine must select its current period.
    """
    if model_input.period_hours != 0.5:
        raise ValueError("Doctoral market factory requires period_hours=0.5")
    chronology = model_input.chronology
    if chronology is None or not chronology.period_ids:
        raise ValueError("Doctoral factory requires a nonempty typed chronology")
    if model_input.year != model_input.operating_state.year:
        raise ValueError("Doctoral PSM input and OperatingState year mismatch")
    from .doctoral_nuclear import validate_doctoral_nuclear_view
    validate_doctoral_nuclear_view(model_input.operating_state)
    periods = len(chronology.period_ids)
    _profile(chronology.demand_mwh, periods, "demand_mwh", nonnegative=True)
    generator_parameters = fleet_parameters.get("generators")
    if not isinstance(generator_parameters, Mapping):
        raise ValueError("Frozen fleet_parameters.generators mapping is required")
    assets = {asset.asset_id: asset for asset in model_input.operating_state.assets}
    if len(assets) != len(model_input.operating_state.assets):
        raise ValueError("Duplicate typed OperatingState asset IDs")
    resources = {resource.asset_id: resource for resource in chronology.resources if resource.resource_type != "import"}
    if len(resources) != sum(resource.resource_type != "import" for resource in chronology.resources):
        raise ValueError("Duplicate typed dispatch resource IDs")
    storage = {resource.asset_id: resource for resource in chronology.storage}
    if len(storage) != len(chronology.storage) or set(resources) & set(storage):
        raise ValueError("Duplicate generator/storage resource IDs")
    missing_assets = (set(resources) | set(storage)) - set(assets)
    if missing_assets:
        raise ValueError(f"Typed resources missing OperatingState assets: {sorted(missing_assets)}")
    generators, batteries = [], []
    for asset in model_input.operating_state.assets:
        capacity = _finite(asset.capacity_mw, f"{asset.asset_id}.capacity_mw", nonnegative=True)
        if asset.status == "retired" or capacity == 0:
            if asset.asset_id in resources or asset.asset_id in storage:
                raise ValueError(f"Inactive asset is offered by the typed chronology: {asset.asset_id}")
            continue
        if asset.asset_id in storage:
            resource = storage[asset.asset_id]
            key, row = _source_row(battery_parameters, asset.asset_id, _parameter_extensions(asset, resource), "batteries")
            values = _values(row, BATTERY_FIELDS, f"batteries/{key}")
            if not str(row.get("battery_type") or ""):
                raise ValueError(f"batteries/{key} missing constructor fields: battery_type")
            charge = _finite(resource.charge_power_mw, f"{asset.asset_id}.charge_power_mw", nonnegative=True)
            discharge = _finite(resource.discharge_power_mw, f"{asset.asset_id}.discharge_power_mw", nonnegative=True)
            energy = _finite(resource.energy_capacity_mwh, f"{asset.asset_id}.energy_capacity_mwh", nonnegative=True)
            if not math.isclose(charge, discharge, rel_tol=0, abs_tol=1e-10):
                raise ValueError(f"Doctoral battery requires equal charging/discharging power: {asset.asset_id}")
            if asset.energy_capacity_mwh is None or not math.isclose(energy, float(asset.energy_capacity_mwh), rel_tol=1e-10, abs_tol=1e-7) or not math.isclose(charge, capacity, rel_tol=1e-10, abs_tol=1e-7):
                raise ValueError(f"Storage limits disagree with OperatingState: {asset.asset_id}")
            if _finite(resource.initial_soc_mwh, f"{asset.asset_id}.initial_soc_mwh", nonnegative=True) != 0:
                raise ValueError(f"Nonzero opening SOC requires validated batch checkpoint: {asset.asset_id}")
            for source_key, typed_value in (("n_1", resource.charge_efficiency), ("n_2", resource.discharge_efficiency)):
                if not 0 < values[source_key] <= 1 or not math.isclose(values[source_key], _finite(typed_value, f"{asset.asset_id}.{source_key}"), rel_tol=0, abs_tol=1e-12):
                    raise ValueError(f"Source/typed storage efficiency mismatch: {asset.asset_id}.{source_key}")
            battery = k.Battery(name=asset.asset_id, pool_limit=energy / 0.5, per_pool_limit=charge, battery_type=str(row["battery_type"]), **values)
            battery.doctoral_parameter_source_id = key
            battery.doctoral_storage_units = "pool_limit=MWh/0.5; per_pool_limit=charging_MW"
            batteries.append(battery)
            continue
        resource = resources.get(asset.asset_id)
        if resource is None:
            raise ValueError(f"Active asset has no typed dispatch resource: {asset.asset_id}")
        if resource.technology != asset.technology or not math.isclose(_finite(resource.capacity_mw, f"{asset.asset_id}.resource_capacity"), capacity, rel_tol=1e-10, abs_tol=1e-7):
            raise ValueError(f"Typed resource disagrees with OperatingState: {asset.asset_id}")
        key, row = _source_row(generator_parameters, asset.asset_id, _parameter_extensions(asset, resource), "generators")
        technology = asset.technology
        if technology == "Nuclear" and key == "Nuclear" and asset.asset_id != "Nuclear":
            raise ValueError(f"Nuclear station-specific frozen ramp/startup/capital parameters required: {asset.asset_id}; national Nuclear row cannot be duplicated per station")
        constructors = {"CCGT": (k.GasGenerator, GAS_FIELDS), "OCGT": (k.GasGenerator, GAS_FIELDS), "gas": (k.GasGenerator, GAS_FIELDS), "bio_and_waste": (k.BiomassGenerator, BIO_FIELDS), "Hydro_natural_flow": (k.WaterGenerator, WATER_FIELDS), "Nuclear": (k.NuclearGenerator, NUCLEAR_FIELDS)}
        availability = _profile(resource.availability, periods, f"{asset.asset_id}.availability", nonnegative=True, constant=True)
        available_mw = tuple(capacity * value for value in availability)
        if technology in {"solar", "onshore", "offshore"}:
            values = _values(row, VRE_FIELDS, f"generators/{key}")
            generator = k.ExpensiverenewableGenerator(name=asset.asset_id, capacity_multiplier=capacity if technology == "solar" else capacity / 20.0,
                electrolyzer_cost=0.0, energy_efficiency=0.0, electrolyzer_limit=0.0, rampup_rate=0.0, **values)
            generator.capacity_limit = available_mw[0]
        elif technology in constructors:
            constructor, fields = constructors[technology]
            generator = constructor(name=asset.asset_id, capacity_limit=available_mw[0], **_values(row, fields, f"generators/{key}"))
        else:
            raise ValueError(f"Unsupported doctoral generator technology: {technology}")
        generator.doctoral_parameter_source_id = key
        generator.doctoral_capacity_mw_by_period = available_mw
        generator.doctoral_factory_schema = FACTORY_SCHEMA
        generators.append(generator)
    connections = _connections(chronology, fleet_parameters.get("connections", {}), periods)
    # Bind the complete market identity even when no nuclear station is active.
    nuclear_register_sha = model_input.operating_state.extensions.get("doctoral_nuclear_register_sha256")
    if nuclear_register_sha:
        for template in (*generators, *batteries, *connections):
            template.doctoral_nuclear_register_sha256 = nuclear_register_sha
    return tuple(generators), tuple(batteries), connections
