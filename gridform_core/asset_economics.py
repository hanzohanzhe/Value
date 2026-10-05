"""Single audited economic specification for operating and commissioned assets."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Mapping

from .storage_catalogue import compatibility_catalogue
from .v2.contracts import AssetStateV2, CommissionedAssetRecord, PlanningProject


ECONOMICS_SCHEMA = "value.asset-economics/v1"
STORAGE_CATALOGUE_KEYS = {
    "pumped_hydro": "pumped_hydro",
    "1c_battery": "1c",
    "0.5c_battery": "0.5c",
    "0.25c_battery": "0.25c",
    "hydrogen_battery": "hydrogen",
    "battery": "0.25c",
}
REQUIRED_ECONOMIC_FIELDS = (
    "capital_cost_per_mw",
    "capital_cost_per_mwh",
    "total_capex_gbp",
    "annual_fixed_opex_gbp",
    "economic_lifetime_years",
    "capital_discount_rate",
    "annualized_capital_cost_gbp",
    "fixed_om_basis",
    "asset_economics_schema_version",
)


def capital_recovery_factor(rate: float, years: float) -> float:
    if years <= 0:
        raise ValueError("Economic lifetime must be positive")
    if rate < 0:
        raise ValueError("Capital discount rate cannot be negative")
    if rate == 0:
        return 1.0 / years
    return rate * (1.0 + rate) ** years / ((1.0 + rate) ** years - 1.0)


def _storage_values(technology: str, capacity_mw: float) -> dict[str, object] | None:
    key = STORAGE_CATALOGUE_KEYS.get(technology)
    if key is None:
        return None
    catalogue = compatibility_catalogue()
    specification = catalogue.get(key)
    if specification.capex_unit == "GBP/MW":
        capital_per_mw = specification.capex_value
        capital_per_mwh = 0.0
        total_capex = capital_per_mw * capacity_mw
    elif specification.capex_unit == "GBP/MWh":
        capital_per_mw = 0.0
        capital_per_mwh = specification.capex_value
        total_capex = capital_per_mwh * specification.energy_capacity_mwh(capacity_mw)
    elif specification.capex_unit == "GBP/project":
        capital_per_mw = 0.0
        capital_per_mwh = 0.0
        total_capex = specification.capex_value
    else:  # guarded by the catalogue validator; retained as a fail-closed boundary
        raise ValueError(f"Unsupported storage CAPEX unit {specification.capex_unit}")
    if specification.fixed_opex_unit == "GBP/kW/year":
        fixed_om = specification.fixed_opex_value * capacity_mw * 1000.0
    elif specification.fixed_opex_unit == "GBP/MW/year":
        fixed_om = specification.fixed_opex_value * capacity_mw
    elif specification.fixed_opex_unit == "GBP/year":
        fixed_om = specification.fixed_opex_value
    else:
        raise ValueError(f"Unsupported storage FOM unit {specification.fixed_opex_unit}")
    return {
        "capital_cost_per_mw": float(capital_per_mw),
        "capital_cost_per_mwh": float(capital_per_mwh),
        "total_capex_gbp": float(total_capex),
        "annual_fixed_opex_gbp": float(fixed_om),
        "fixed_om_basis": f"{catalogue.catalogue_id}:{specification.fixed_opex_unit}",
        "economic_lifetime_years": float(specification.economic_lifetime_years),
        "source_catalogue_id": catalogue.catalogue_id,
        "charge_efficiency": float(specification.charge_efficiency),
        "discharge_efficiency": float(specification.discharge_efficiency),
        "duration_hours": float(specification.duration_hours),
    }


def build_asset_economic_extensions(
    technology: str,
    capacity_mw: float,
    *,
    energy_capacity_mwh: float | None,
    capital_costs_per_mw: Mapping[str, object],
    lifetimes: Mapping[str, object],
    discount_rate: float,
    source_record_id: str,
    capital_cost_per_mw_override: float | None = None,
    annual_fixed_opex_gbp_override: float | None = None,
) -> dict[str, object]:
    """Return complete, explicit economics; zero FOM is allowed only with a basis."""

    capacity = float(capacity_mw)
    if capacity <= 0:
        raise ValueError("Asset economics require positive MW capacity")
    storage = _storage_values(technology, capacity)
    if storage is not None:
        values = dict(storage)
    else:
        raw_capital = (
            capital_cost_per_mw_override
            if capital_cost_per_mw_override is not None
            else capital_costs_per_mw.get(technology)
        )
        if raw_capital is None and technology == "gas":
            raw_capital = capital_costs_per_mw.get("CCGT")
        if raw_capital is None:
            raise ValueError(f"No CAPEX basis is available for technology {technology!r}")
        capital_per_mw = float(raw_capital)
        if capital_per_mw <= 0:
            raise ValueError(f"CAPEX must be positive for technology {technology!r}")
        life_key = technology if technology in lifetimes else "default"
        life = float(lifetimes.get(life_key, 25.0) or 25.0)
        fixed_om = float(annual_fixed_opex_gbp_override or 0.0)
        values = {
            "capital_cost_per_mw": capital_per_mw,
            "capital_cost_per_mwh": 0.0,
            "total_capex_gbp": capital_per_mw * capacity,
            "annual_fixed_opex_gbp": fixed_om,
            "fixed_om_basis": (
                "explicit_override"
                if annual_fixed_opex_gbp_override is not None
                else "no_separate_non_storage_fom_term"
            ),
            "economic_lifetime_years": life,
            "source_catalogue_id": "value-uk-1000twh-reproduction:costs.capital",
        }
    life = float(values["economic_lifetime_years"])
    total_capex = float(values["total_capex_gbp"])
    crf = capital_recovery_factor(float(discount_rate), life)
    values.update({
        "capital_discount_rate": float(discount_rate),
        "capital_recovery_factor": crf,
        "annualized_capital_cost_gbp": total_capex * crf,
        "asset_economics_schema_version": ECONOMICS_SCHEMA,
        "source_record_id": source_record_id,
        "energy_capacity_mwh_basis": (
            float(energy_capacity_mwh) if energy_capacity_mwh is not None else None
        ),
    })
    return values


def validate_asset_economics(asset: AssetStateV2) -> None:
    if asset.capacity_mw <= 0 or asset.status not in {"operating", "commissioned"}:
        return
    extensions = dict(asset.extensions)
    missing = [key for key in REQUIRED_ECONOMIC_FIELDS if key not in extensions]
    if missing:
        raise ValueError(
            f"Active asset {asset.asset_id} is missing economic fields: {', '.join(missing)}"
        )
    numeric_keys = REQUIRED_ECONOMIC_FIELDS[:7]
    for key in numeric_keys:
        value = float(extensions[key])
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Active asset {asset.asset_id} has invalid {key}: {value}")
    life = float(extensions["economic_lifetime_years"])
    if life <= 0:
        raise ValueError(f"Active asset {asset.asset_id} has non-positive economic lifetime")
    expected = float(extensions["total_capex_gbp"]) * capital_recovery_factor(
        float(extensions["capital_discount_rate"]), life
    )
    actual = float(extensions["annualized_capital_cost_gbp"])
    if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=0.01):
        raise ValueError(
            f"Active asset {asset.asset_id} annualized CAPEX {actual} does not reconcile to {expected}"
        )
    if float(extensions["annual_fixed_opex_gbp"]) == 0 and not str(
        extensions.get("fixed_om_basis") or ""
    ):
        raise ValueError(f"Active asset {asset.asset_id} has silent zero fixed O&M")


def primary_annual_asset_costs(asset: AssetStateV2) -> tuple[float, float]:
    """Return annual capital/FOM included in the primary model cost ledger."""

    if asset.extensions.get("primary_cost_ledger_included") is False:
        return 0.0, 0.0
    return (
        float(asset.extensions.get("annualized_capital_cost_gbp", 0.0) or 0.0),
        float(asset.extensions.get("annual_fixed_opex_gbp", 0.0) or 0.0),
    )


CAPITAL_COST_COMPONENTS_KEY = "capital_cost_components_gbp"
CAPITAL_COST_COMPONENTS_SCHEMA = "value.capital-cost-components/v1"
EXISTING_STOCK_COMPATIBILITY_SCOPE = "existing_stock_compatibility"
# DECISIONS A7: VRE and storage have no separate fixed OPEX in the headline;
# it is treated as folded into their levelised (annualised) CAPEX.
FOM_IN_LEVELISED_CAPEX_TECHNOLOGIES = frozenset({
    "solar", "onshore", "offshore",
    "1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery", "pumped_hydro", "battery",
})


def capital_cost_components(assets, *, included_fixed_opex_gbp: float | None = None) -> dict[str, object]:
    """What a PSM's ``total_levelized_capital_cost_gbp`` contains (cost ledger v2, P0-7 S8).

    ``included_annualised_capital_gbp`` and ``included_fixed_opex_gbp`` are the
    ``primary_annual_asset_costs`` sums the PSM booked; the two named parts are
    subsets of them: the annualised capital of assets whose
    ``capital_cost_scope`` is ``existing_stock_compatibility`` (run-of-river
    hydro, P4-03) and the fixed OPEX of VRE and storage (decision A7). A PSM
    that books a different FOM passes its ``included_fixed_opex_gbp``.
    """
    capital = fixed = compatibility = vre_storage_fom = 0.0
    for asset in assets:
        asset_capital, asset_fixed = primary_annual_asset_costs(asset)
        capital += asset_capital
        fixed += asset_fixed
        if asset.extensions.get("capital_cost_scope") == EXISTING_STOCK_COMPATIBILITY_SCOPE:
            compatibility += asset_capital
        if asset.technology in FOM_IN_LEVELISED_CAPEX_TECHNOLOGIES:
            vre_storage_fom += asset_fixed
    if included_fixed_opex_gbp is not None:
        fixed = float(included_fixed_opex_gbp)
        vre_storage_fom = 0.0
    return {
        "schema_version": CAPITAL_COST_COMPONENTS_SCHEMA,
        "included_annualised_capital_gbp": capital,
        "included_fixed_opex_gbp": fixed,
        "existing_stock_compatibility_capital_gbp": compatibility,
        "vre_storage_fixed_opex_gbp": vre_storage_fom,
    }


def resize_asset_economics(asset: AssetStateV2, capacity_mw: float) -> AssetStateV2:
    """Apply a retirement without leaving stale annualized costs on the asset."""

    old_capacity = float(asset.capacity_mw)
    new_capacity = max(float(capacity_mw), 0.0)
    if old_capacity <= 0:
        return replace(asset, capacity_mw=new_capacity)
    ratio = new_capacity / old_capacity
    old_energy = float(asset.energy_capacity_mwh or 0.0)
    new_energy = old_energy * ratio if asset.energy_capacity_mwh is not None else None
    extensions = dict(asset.extensions)
    if all(key in extensions for key in REQUIRED_ECONOMIC_FIELDS):
        total_capex = (
            float(extensions["capital_cost_per_mw"]) * new_capacity
            + float(extensions["capital_cost_per_mwh"]) * float(new_energy or 0.0)
        )
        if (
            float(extensions["capital_cost_per_mw"]) == 0
            and float(extensions["capital_cost_per_mwh"]) == 0
        ):
            total_capex = float(extensions["total_capex_gbp"]) * ratio
        extensions["total_capex_gbp"] = total_capex
        extensions["annual_fixed_opex_gbp"] = (
            float(extensions["annual_fixed_opex_gbp"]) * ratio
        )
        extensions["annualized_capital_cost_gbp"] = total_capex * capital_recovery_factor(
            float(extensions["capital_discount_rate"]),
            float(extensions["economic_lifetime_years"]),
        )
        extensions["retirement_capacity_fraction_remaining"] = ratio
        if new_capacity == 0:
            extensions["retired_from_active_cost_ledger"] = True
    return replace(
        asset,
        capacity_mw=new_capacity,
        energy_capacity_mwh=new_energy,
        status="retired" if new_capacity == 0 else asset.status,
        extensions=extensions,
    )


def commissioned_asset_record(
    project: PlanningProject,
    *,
    asset_id: str,
    commissioning_year: int,
) -> CommissionedAssetRecord:
    extensions = dict(project.extensions)
    missing = [key for key in REQUIRED_ECONOMIC_FIELDS if key not in extensions]
    if missing:
        raise ValueError(
            f"Project {project.project_id} cannot commission without economics: {', '.join(missing)}"
        )
    energy = extensions.get("energy_capacity_mwh")
    return CommissionedAssetRecord(
        asset_id=asset_id,
        source_project_id=project.project_id,
        technology=project.technology,
        region=project.region,
        commissioning_year=int(commissioning_year),
        capacity_mw=float(project.capacity_mw),
        energy_capacity_mwh=float(energy) if energy is not None else None,
        capital_cost_per_mw_gbp=float(extensions["capital_cost_per_mw"]),
        capital_cost_per_mwh_gbp=float(extensions["capital_cost_per_mwh"]),
        total_capex_gbp=float(extensions["total_capex_gbp"]),
        annual_fixed_opex_gbp=float(extensions["annual_fixed_opex_gbp"]),
        economic_lifetime_years=float(extensions["economic_lifetime_years"]),
        discount_rate=float(extensions["capital_discount_rate"]),
        annualized_capital_cost_gbp=float(extensions["annualized_capital_cost_gbp"]),
        charge_efficiency=(
            float(extensions["charge_efficiency"])
            if extensions.get("charge_efficiency") is not None else None
        ),
        discharge_efficiency=(
            float(extensions["discharge_efficiency"])
            if extensions.get("discharge_efficiency") is not None else None
        ),
        source_catalogue_id=str(extensions.get("source_catalogue_id") or "") or None,
        source_record_id=str(extensions.get("source_record_id") or "") or None,
        investment_owner_id=(
            str(
                extensions.get("investment_owner_id")
                or extensions.get("source_agent_id")
                or ""
            )
            or None
        ),
        extensions={
            "fixed_om_basis": extensions["fixed_om_basis"],
            "asset_economics_schema_version": extensions["asset_economics_schema_version"],
        },
    )
