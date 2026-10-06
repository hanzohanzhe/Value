"""Reconciled physical and legacy carbon accounting for VALUE results."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .carbon_factors import CarbonFactorDatabase, DEFAULT_DATABASE
from .v2.contracts import AssetStateV2


CURRENT_SCENARIO = "value_current_authoritative_v1"
LEGACY_SCENARIO = "doctoral_reproduction_2026_07_18"

_IMPORT_COUNTRY_ALIASES = {
    "france": "France",
    "netherland": "Netherlands",
    "netherlands": "Netherlands",
    "beligum": "Belgium",  # Historical VALUE asset spelling.
    "belgium": "Belgium",
    "ireland": "Ireland",
    "norway": "Norway",
}


@dataclass(frozen=True)
class CarbonLine:
    line_id: str
    component: str
    emissions_tco2e: float | None
    activity_mwh: float | None
    factor_record_id: str | None
    factor_value: float | None
    factor_unit: str | None
    treatment: str
    reason: str | None = None
    factor_provenance: Mapping[str, object] | None = None
    asset_capacity_mw: float | None = None
    asset_energy_capacity_mwh: float | None = None
    asset_commissioning_year: int | None = None


def database_sha256(path: Path = DEFAULT_DATABASE) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def factor_scenario_manifest(scenario_id: str) -> dict[str, object]:
    if scenario_id == CURRENT_SCENARIO:
        records = {
            "ccgt": "auth_ccgt_op", "ocgt": "auth_ocgt_op", "biomass": "auth_biomass_op",
            "hydro": "auth_hydro_op", "nuclear": "auth_nuclear_op", "solar": "auth_solar_op",
            "onshore_wind": "auth_wind_op", "offshore_wind": "auth_wind_op",
            "pumped_hydro": "auth_phs_op",
            "import:France": "auth_import_fr", "import:Netherlands": "auth_import_nl",
            "import:Belgium": "auth_import_be", "import:Ireland": "auth_import_ie",
            "import:Norway": "auth_import_no_nve_2024",
        }
        embodied_records = {
            "ccgt": "pp_ccgt_annual", "ocgt": "pp_ocgt_annual",
            "biomass": "pp_biomass_annual", "hydro": "pp_hydro_annual",
            "nuclear": "pp_nuclear_annual", "solar": "pp_solar_annual",
            "onshore_wind": "pp_onshore_annual",
            "offshore_wind": "pp_offshore_annual",
            "pumped_hydro": "pp_phs_annual",
            "battery": "auth_bess_mid",
            "hydrogen_storage:power": "pp_electrolyser_annual",
            "hydrogen_storage:energy": "ch4_h2_store_lifetime",
        }
        return {
            "schema_version": "value.carbon-factor-scenario/v1", "scenario_id": scenario_id,
            "dataset_id": "uk_authority_reference_2026_08_06", "database_sha256": database_sha256(),
            "record_ids_by_activity": records,
            "record_ids_by_embodied_asset": embodied_records,
            "physical_boundary": "direct operational generation and exogenous imports, plus separately annualised asset-construction and equipment lifecycle emissions",
            "storage_carbon_rule": "single_node_average_pool_charging_inventory",
            "excluded_with_reason": {
                "battery_direct_operation": "no direct combustion; carried charge carbon is inventoried separately",
                "storage_charge_in_total": "generation-side emissions already include charging supply; adding them again would double count",
                "battery_power_balance_of_plant": "no separately compatible factor selected; the energy-capacity manufacturing record is the complete selected battery equipment proxy",
            },
            "embodied_method": "active-capacity annual allocation; paper snapshot factors preserve the published Chapter 4 calculation, while battery manufacturing is divided by each asset economic life",
        }
    if scenario_id == LEGACY_SCENARIO:
        return {
            "schema_version": "value.carbon-factor-scenario/v1", "scenario_id": scenario_id,
            "dataset_id": "doctoral_reproduction_2026_07_18", "database_sha256": database_sha256(),
            "record_ids_by_activity": "all_literal_doctoral_reproduction_snapshot_records",
            "physical_boundary": "legacy reproduction only",
            "legacy_storage_unit_status": "not_physically_interpretable",
        }
    raise ValueError(f"Unknown carbon factor scenario {scenario_id}")


def _factor_by_record(database: CarbonFactorDatabase, record_id: str):
    rows = [row for row in database.query() if row.record_id == record_id]
    if len(rows) != 1:
        raise LookupError(f"Carbon factor record {record_id} is missing or ambiguous")
    return rows[0]


def _kg_per_mwh(value: float, unit: str) -> float:
    if unit in {"kgCO2_per_MWh", "kgCO2e_per_MWh", "gCO2e_per_kWh"}:
        return value  # 1 g/kWh == 1 kg/MWh
    raise ValueError(f"Factor unit {unit} cannot be converted to kgCO2e/MWh")


def _factor_provenance(factor: object) -> dict[str, object]:
    return {
        "record_id": factor.record_id,
        "dataset_id": factor.dataset_id,
        "factor_kind": factor.factor_kind,
        "boundary": factor.lifecycle_scope,
        "basis": factor.basis,
        "geography": factor.geography,
        "scenario": factor.scenario,
        "source_id": factor.source_id,
        "source_title": factor.source_title,
        "source_url": factor.source_url,
        "review_status": factor.status,
        "quality_note": factor.quality_note,
    }


def _normalise_technology(technology: str) -> str:
    return {
        "CCGT": "ccgt", "OCGT": "ocgt", "gas": "ccgt",
        "bio_and_waste": "biomass", "Hydro_natural_flow": "hydro",
        "Nuclear": "nuclear", "onshore": "onshore_wind",
        "offshore": "offshore_wind", "interconnector_import": "import_electricity",
        "1c_battery": "battery", "0.5c_battery": "battery",
        "0.25c_battery": "battery", "battery_1c": "battery",
        "battery_0_5c": "battery", "battery_0_25c": "battery",
        "hydrogen_battery": "hydrogen_storage",
    }.get(technology, technology)


def _asset_embodied_lines(
    *,
    year: int,
    assets: Sequence[AssetStateV2],
    mapping: Mapping[str, str],
    database: CarbonFactorDatabase,
) -> tuple[list[CarbonLine], list[str]]:
    """Annualise the selected equipment boundary without charging-energy duplication."""

    lines: list[CarbonLine] = []
    unresolved: list[str] = []
    for asset in assets:
        capacity_mw = float(asset.capacity_mw)
        if capacity_mw <= 0 or asset.status not in {"operating", "commissioned", "active"}:
            continue
        technology = _normalise_technology(str(asset.technology))
        commissioning_year_raw = asset.extensions.get("commissioning_year")
        commissioning_year = (
            int(commissioning_year_raw) if commissioning_year_raw is not None else None
        )
        if commissioning_year is not None and commissioning_year > year:
            unresolved.append(f"{asset.asset_id}:commissioning_after_ledger_year")
            continue
        economic_life = float(asset.extensions.get("economic_lifetime_years", 0.0) or 0.0)
        selections: list[tuple[str, str]] = []
        if technology == "hydrogen_storage":
            selections = [
                ("storage_power_equipment", mapping.get("hydrogen_storage:power", "")),
                ("storage_energy_equipment", mapping.get("hydrogen_storage:energy", "")),
            ]
        else:
            selections = [("asset_embodied", mapping.get(technology, ""))]
        for component, record_id in selections:
            if not record_id:
                unresolved.append(f"{asset.asset_id}:{technology}:embodied_factor")
                lines.append(CarbonLine(
                    f"embodied:{asset.asset_id}:{component}", component, None, None,
                    None, None, None, "not_evaluated", "no pinned compatible factor",
                    asset_capacity_mw=capacity_mw,
                    asset_energy_capacity_mwh=asset.energy_capacity_mwh,
                    asset_commissioning_year=commissioning_year,
                ))
                continue
            factor = _factor_by_record(database, record_id)
            if factor.unit == "tCO2e_per_MW_year":
                emissions = capacity_mw * factor.value
                treatment = "active_power_capacity_times_annualised_factor"
            elif factor.unit == "kgCO2e_per_kWh_capacity":
                if asset.energy_capacity_mwh is None or economic_life <= 0:
                    unresolved.append(f"{asset.asset_id}:{technology}:energy_capacity_or_life")
                    emissions = None
                    treatment = "not_evaluated"
                else:
                    # kg/kWh is numerically t/MWh. Divide lifetime construction
                    # emissions across the asset's declared economic life.
                    emissions = float(asset.energy_capacity_mwh) * factor.value / economic_life
                    treatment = "energy_capacity_manufacturing_emissions_divided_by_asset_life"
            elif factor.unit == "tCO2e_per_MWh_capacity":
                lifetime = economic_life
                if asset.energy_capacity_mwh is None or lifetime <= 0:
                    unresolved.append(f"{asset.asset_id}:{technology}:energy_capacity_or_life")
                    emissions = None
                    treatment = "not_evaluated"
                else:
                    emissions = float(asset.energy_capacity_mwh) * factor.value / lifetime
                    treatment = "energy_capacity_lifecycle_emissions_divided_by_asset_life"
            else:
                raise ValueError(
                    f"Embodied factor {record_id} uses unsupported unit {factor.unit}"
                )
            lines.append(CarbonLine(
                f"embodied:{asset.asset_id}:{component}", component, emissions, None,
                factor.record_id, factor.value, factor.unit, treatment,
                None if emissions is not None else "missing energy capacity or economic life",
                _factor_provenance(factor), capacity_mw, asset.energy_capacity_mwh,
                commissioning_year,
            ))
    return lines, unresolved


def _import_country(asset_id: str, declared: str | None) -> str | None:
    """Resolve both public IDs and retained VALUE interconnector spellings."""

    candidate = str(declared or "").strip()
    if not candidate and asset_id.startswith("import:"):
        candidate = asset_id.split(":", 1)[1]
    if not candidate and asset_id.casefold().startswith("interconnect_"):
        candidate = asset_id.split("_", 1)[1]
    return _IMPORT_COUNTRY_ALIASES.get(candidate.casefold())


def build_operational_carbon_ledger(
    *,
    year: int,
    scenario_id: str,
    generation_mwh_by_asset: Mapping[str, float],
    technology_by_asset: Mapping[str, str],
    delivered_demand_mwh: float,
    import_country_by_asset: Mapping[str, str] | None = None,
    legacy_metric: float | None = None,
    storage_trace: Mapping[str, Sequence[float]] | None = None,
    asset_states: Sequence[AssetStateV2] | None = None,
) -> dict[str, object]:
    manifest = factor_scenario_manifest(scenario_id)
    if scenario_id == LEGACY_SCENARIO:
        return {
            "schema_version": "value.carbon-ledger/v2", "year": year, "scenario": manifest,
            "status": "not_physically_interpretable",
            "total_carbon_emissions_tco2e": None,
            "doctoral_reproduction_carbon_metric": legacy_metric,
            "reason_code": "legacy_storage_scalars_have_no_declared_physical_unit",
            "intensities": {}, "lines": [],
        }
    database = CarbonFactorDatabase()
    mapping = manifest["record_ids_by_activity"]
    lines: list[CarbonLine] = []
    unresolved: list[str] = []
    import_country_by_asset = dict(import_country_by_asset or {})
    for asset_id, activity in generation_mwh_by_asset.items():
        activity = float(activity)
        technology = str(technology_by_asset.get(asset_id, "unknown"))
        import_country = _import_country(asset_id, import_country_by_asset.get(asset_id))
        if import_country is not None:
            technology = "import_electricity"
        technology = _normalise_technology(technology)
        if technology in {"battery", "1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"}:
            # Discharge moves carbon previously admitted to inventory; it does not create it.
            lines.append(CarbonLine(asset_id, "storage_carried_transfer", 0.0, activity, None, None, None, "inventory_transfer_not_new_emission"))
            continue
        key = f"import:{import_country or ''}" if technology in {"import", "import_electricity"} else technology
        record_id = mapping.get(key) if isinstance(mapping, Mapping) else None
        if not record_id:
            unresolved.append(f"{asset_id}:{key}")
            lines.append(CarbonLine(asset_id, "unresolved", None, activity, None, None, None, "not_evaluated", "no pinned compatible factor"))
            continue
        factor = _factor_by_record(database, str(record_id))
        kg = _kg_per_mwh(factor.value, factor.unit)
        component = "imported_electricity" if technology in {"import", "import_electricity"} else "direct_operational"
        lines.append(CarbonLine(
            asset_id, component, activity * kg / 1000.0, activity,
            factor.record_id, factor.value, factor.unit,
            "activity_times_pinned_factor", factor_provenance=_factor_provenance(factor),
        ))
    # Chronological storage accounting needs source-specific or average-pool charging intensity.
    storage_status = "not_evaluated"
    ending_inventory = None
    if storage_trace:
        required = {"charge_mwh", "discharge_mwh", "charge_source_kgco2e_per_mwh", "charge_efficiency", "discharge_efficiency"}
        if required.issubset(storage_trace):
            inventory_energy = 0.0
            inventory_kg = 0.0
            for charge, discharge, intensity in zip(storage_trace["charge_mwh"], storage_trace["discharge_mwh"], storage_trace["charge_source_kgco2e_per_mwh"]):
                admitted = float(charge) * float(storage_trace["charge_efficiency"][0])
                inventory_energy += admitted
                inventory_kg += float(charge) * float(intensity)
                withdrawn = float(discharge) / float(storage_trace["discharge_efficiency"][0])
                if withdrawn > inventory_energy + 1e-7:
                    raise ValueError("Storage carbon inventory cannot discharge more energy than held")
                share = withdrawn / inventory_energy if inventory_energy > 0 else 0.0
                inventory_kg *= 1.0 - share
                inventory_energy -= withdrawn
            ending_inventory = inventory_kg / 1000.0
            storage_status = "reconciled_average_pool"
    operational_lines = list(lines)
    operational = sum(
        float(line.emissions_tco2e or 0.0) for line in operational_lines
    ) if not unresolved else None
    embodied_lines, embodied_unresolved = _asset_embodied_lines(
        year=year,
        assets=tuple(asset_states or ()),
        mapping=manifest["record_ids_by_embodied_asset"],
        database=database,
    )
    lines.extend(embodied_lines)
    unresolved.extend(embodied_unresolved)
    embodied = sum(
        float(line.emissions_tco2e or 0.0) for line in embodied_lines
    ) if not embodied_unresolved else None
    total = (
        operational + embodied
        if operational is not None and embodied is not None and not unresolved
        else None
    )
    operational_intensity = (
        operational * 1000.0 / delivered_demand_mwh
        if operational is not None and delivered_demand_mwh > 0 else None
    )
    overall_intensity = (
        total * 1000.0 / delivered_demand_mwh
        if total is not None and delivered_demand_mwh > 0 else None
    )
    return {
        "schema_version": "value.carbon-ledger/v2", "year": year, "scenario": manifest,
        "status": "reconciled" if total is not None else "not_evaluated",
        "total_carbon_emissions_tco2e": total,
        "components_tco2e": {
            name: sum(float(row.emissions_tco2e or 0.0) for row in lines if row.component == name)
            # F2-N4: sorted, so the key order does not follow the string hash
            # seed of the process and identical runs write identical bytes.
            for name in sorted({row.component for row in lines})
        },
        "storage_carried_carbon_status": storage_status,
        "ending_stored_carbon_inventory_tco2e": ending_inventory,
        "operational_emissions_tco2e": operational,
        "embodied_lifecycle_emissions_tco2e": embodied,
        "embodied_status": "reconciled" if embodied is not None else "not_evaluated",
        "intensities": {
            "operational_kgco2e_per_mwh": operational_intensity,
            "overall_kgco2e_per_mwh": overall_intensity,
            "delivered_demand_kgco2e_per_mwh": overall_intensity,
            "numerator": "total_carbon_emissions_tco2e",
            "denominator_mwh": delivered_demand_mwh,
        },
        "unresolved_activities": unresolved,
        "lines": [asdict(row) for row in lines],
        "mass_reconciliation_residual_tco2e": 0.0 if total is not None else None,
    }


def write_carbon_ledgers(path: Path, ledgers: Sequence[Mapping[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    collection = {
        "schema_version": "value.carbon-ledger-collection/v2",
        "years": list(ledgers),
    }
    temporary.write_text(
        json.dumps(collection, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)
    sqlite_path = path.with_suffix(".sqlite")
    handle, temporary_name = tempfile.mkstemp(
        prefix="annual-carbon-ledger-", suffix=".sqlite.tmp", dir=path.parent
    )
    os.close(handle)
    temporary_sqlite = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary_sqlite)
        try:
            connection.executescript(
                """
                PRAGMA journal_mode=OFF;
                PRAGMA synchronous=OFF;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE annual_carbon_ledger (
                    year INTEGER PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    operational_emissions_tco2e REAL,
                    embodied_emissions_tco2e REAL,
                    total_emissions_tco2e REAL,
                    operational_intensity_kgco2e_per_mwh REAL,
                    overall_intensity_kgco2e_per_mwh REAL,
                    ledger_sha256 TEXT NOT NULL,
                    ledger_json TEXT NOT NULL
                );
                CREATE TABLE carbon_lines (
                    year INTEGER NOT NULL,
                    line_id TEXT NOT NULL,
                    component TEXT NOT NULL,
                    emissions_tco2e REAL,
                    factor_record_id TEXT,
                    line_json TEXT NOT NULL,
                    PRIMARY KEY (year, line_id)
                );
                """
            )
            connection.execute(
                "INSERT INTO metadata VALUES (?, ?)",
                ("schema_version", "value.carbon-ledger-sqlite/v1"),
            )
            for ledger in ledgers:
                canonical = json.dumps(
                    ledger, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
                intensities = dict(ledger.get("intensities") or {})
                scenario = dict(ledger.get("scenario") or {})
                connection.execute(
                    "INSERT INTO annual_carbon_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(ledger["year"]), str(scenario.get("scenario_id", "unknown")),
                        str(ledger.get("status", "unknown")),
                        ledger.get("operational_emissions_tco2e"),
                        ledger.get("embodied_lifecycle_emissions_tco2e"),
                        ledger.get("total_carbon_emissions_tco2e"),
                        intensities.get("operational_kgco2e_per_mwh"),
                        intensities.get("overall_kgco2e_per_mwh"),
                        hashlib.sha256(canonical.encode("utf-8")).hexdigest(), canonical,
                    ),
                )
                for line in ledger.get("lines", []):
                    line_payload = dict(line)
                    connection.execute(
                        "INSERT INTO carbon_lines VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            int(ledger["year"]), str(line_payload["line_id"]),
                            str(line_payload["component"]),
                            line_payload.get("emissions_tco2e"),
                            line_payload.get("factor_record_id"),
                            json.dumps(
                                line_payload, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False,
                            ),
                        ),
                    )
            connection.commit()
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Carbon ledger SQLite integrity check failed")
        finally:
            connection.close()
        os.replace(temporary_sqlite, sqlite_path)
    finally:
        temporary_sqlite.unlink(missing_ok=True)
    return path
