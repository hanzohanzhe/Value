"""One-time importer for the verified 18/19 July 2026 VALUE 1000 TWh data.

The source research tree is read only. Every input is copied into a VALUE
data pack and recorded with SHA-256 provenance. Generated JSON files extract
configuration data from Python so the runtime no longer reads config.py.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from gridform_core.runtime_paths import user_data_root


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("source-not-configured")
WEATHER = Path("weather-not-configured")
TARGET = user_data_root() / "data-packs" / "value-uk-1000twh-reproduction"
FILES = TARGET / "files"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_binding(role: str, source: Path, unit: str | None = None) -> dict:
    if not source.is_file():
        raise FileNotFoundError(f"Missing VALUE dataset for {role}: {source}")
    destination_dir = FILES / role.replace(".", "__")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if not destination.exists() or destination.stat().st_size != source.stat().st_size:
        shutil.copy2(source, destination)
    binding = {
        "role": role,
        "uri": destination.relative_to(TARGET).as_posix(),
        "filename": destination.name,
        "format": destination.suffix.lower().lstrip("."),
        "bytes": destination.stat().st_size,
        "sha256": sha256(destination),
        "imported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_release": "scheme-c-1000twh-2026-07-18_19",
    }
    if unit:
        binding["unit"] = unit
    return binding


def write_generated(role: str, filename: str, payload: dict, unit: str | None = None) -> dict:
    directory = FILES / role.replace(".", "__")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    binding = {
        "role": role,
        "uri": path.relative_to(TARGET).as_posix(),
        "filename": path.name,
        "format": "json",
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "imported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_release": "scheme-c-1000twh-2026-07-18_19",
        "transform": "extracted from verified VALUE config.py",
    }
    if unit:
        binding["unit"] = unit
    return binding


def load_config():
    os.environ["CAPITAL_COST_PROFILE"] = "arup_medium"
    spec = importlib.util.spec_from_file_location("scheme_c_source_config", SOURCE / "config.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load VALUE config")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_repd(source: Path) -> dict:
    frame = pd.read_csv(source, encoding="latin1", low_memory=False)

    def technology(value):
        text = str(value)
        if "Onshore" in text:
            return "onshore"
        if "Offshore" in text:
            return "offshore"
        if "Solar" in text:
            return "solar"
        if "Battery" in text and "Pumped Storage" not in text:
            return "battery"
        if "Gas" in text:
            return "gas"
        return None

    normalized = pd.DataFrame({
        "project_id": frame["Ref ID"].astype(str),
        "site_name": frame["Site Name"],
        "technology": frame["Technology Type"].map(technology),
        "technology_source": frame["Technology Type"],
        "capacity_mw": pd.to_numeric(frame["Installed Capacity (MWelec)"], errors="coerce"),
        "development_status": frame["Development Status (short)"],
        "region": frame["Region"],
        "country": frame["Country"],
        "planning_application_submitted": frame["Planning Application Submitted"],
        "planning_permission_granted": frame["Planning Permission Granted"],
        "under_construction": frame["Under Construction"],
        "operational": frame["Operational"],
        "x_coordinate": pd.to_numeric(frame["X-coordinate"], errors="coerce"),
        "y_coordinate": pd.to_numeric(frame["Y-coordinate"], errors="coerce"),
    })
    normalized = normalized[normalized["technology"].notna() & normalized["capacity_mw"].gt(0)].copy()
    directory = FILES / "projects__repd"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "repd_projects_normalized.csv"
    normalized.to_csv(destination, index=False, encoding="utf-8")
    return {
        "role": "projects.repd",
        "uri": destination.relative_to(TARGET).as_posix(),
        "filename": destination.name,
        "format": "csv",
        "bytes": destination.stat().st_size,
        "sha256": sha256(destination),
        "imported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_release": "REPD Q2 July 2025",
        "unit": "MW",
        "mapping": {
            "Installed Capacity (MWelec)": "capacity_mw",
            "Development Status (short)": "development_status",
            "Technology Type": "technology",
            "Region": "region",
        },
        "rows": int(len(normalized)),
    }


def main() -> None:
    global SOURCE, WEATHER, TARGET, FILES
    parser = argparse.ArgumentParser(description="Import an owner-supplied VALUE data snapshot")
    parser.add_argument("--source", required=True, type=Path, help="Read-only VALUE research-data directory")
    parser.add_argument("--weather", required=True, type=Path, help="Read-only weather-data directory")
    parser.add_argument("--target", type=Path, default=TARGET, help="Destination data-pack directory")
    args = parser.parse_args()
    SOURCE = args.source.expanduser().resolve()
    WEATHER = args.weather.expanduser().resolve()
    TARGET = args.target.expanduser().resolve()
    FILES = TARGET / "files"
    if not SOURCE.is_dir() or not WEATHER.is_dir():
        raise SystemExit("Both --source and --weather must name existing read-only input directories.")
    TARGET.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    bindings = {
        "demand.forecast": copy_binding("demand.forecast", SOURCE / "2022fd.csv", "MW"),
        "demand.real": copy_binding("demand.real", SOURCE / "2022reald.csv", "MW"),
        "weather.wind": copy_binding("weather.wind", WEATHER / "average_annual_wind_profile.nc"),
        "weather.solar": copy_binding("weather.solar", WEATHER / "average_annual_solar_profile.nc"),
        "market.france.profile": copy_binding("market.france.profile", SOURCE / "France_profile.csv", "MWh/period"),
        "market.france.price": copy_binding("market.france.price", SOURCE / "France.csv", "GBP/MWh"),
        "market.belgium.profile": copy_binding("market.belgium.profile", SOURCE / "belgium_profile.csv", "MWh/period"),
        "market.belgium.price": copy_binding("market.belgium.price", SOURCE / "Belgium_price.csv", "GBP/MWh"),
        "market.netherlands.profile": copy_binding("market.netherlands.profile", SOURCE / "nehtheralnd_profile.csv", "MWh/period"),
        "market.netherlands.price": copy_binding("market.netherlands.price", SOURCE / "Netherlands.csv", "GBP/MWh"),
        "market.norway.profile": copy_binding("market.norway.profile", SOURCE / "Norway_profile.csv", "MWh/period"),
        "market.norway.price": copy_binding("market.norway.price", SOURCE / "Norway.csv", "GBP/MWh"),
        "market.ireland.profile": copy_binding("market.ireland.profile", SOURCE / "Ireland_profile.csv", "MWh/period"),
        "market.ireland.price": copy_binding("market.ireland.price", SOURCE / "Ireland.csv", "GBP/MWh"),
        "profiles.vre_solar": copy_binding("profiles.vre_solar", SOURCE / "sa.csv", "p.u."),
        "profiles.vre_onshore": copy_binding("profiles.vre_onshore", SOURCE / "wa.csv", "p.u."),
        "profiles.vre_offshore": copy_binding("profiles.vre_offshore", SOURCE / "we.csv", "p.u."),
        "source.repd_raw": copy_binding("source.repd_raw", SOURCE / "repd-q2-jul-2025.csv", "MW"),
        "policy.support": copy_binding("policy.support", SOURCE / "mechansim cost.xlsx", "GBP"),
        "planning.success_rates": copy_binding("planning.success_rates", SOURCE / "regional_technology_success_rates.csv"),
    }
    bindings["projects.repd"] = normalize_repd(SOURCE / "repd-q2-jul-2025.csv")
    bindings["fleet.generators"] = write_generated("fleet.generators", "fleet.json", {
        "generators": cfg.generators,
        "batteries": cfg.batteries,
        "connections": cfg.connections,
        "electrolyzer": cfg.electrolyzer,
        "locations": cfg.locations,
    })
    bindings["costs.capital"] = write_generated("costs.capital", "capital_costs.json", {
        "active_profile": cfg.ACTIVE_CAPITAL_COST_PROFILE,
        "capital_costs_per_mw": cfg.capital_costs_per_mw,
        "arup_medium_total_capex_per_mw": cfg.ARUP_MEDIUM_TOTAL_CAPEX_PER_MW,
    }, "GBP/MW")
    bindings["planning.timelines"] = write_generated("planning.timelines", "planning_timelines.json", {
        "development_stage_timelines": cfg.development_stage_timelines,
        "repd_status_to_timeline": cfg.repd_status_to_timeline,
        "development_timelines": cfg.development_timelines,
        "construction_timelines": cfg.construction_timelines,
    }, "months")
    bindings["config.model_parameters"] = write_generated("config.model_parameters", "model_parameters.json", {
        "simulation_parameters": cfg.simulation_parameters,
        "investment_parameters": cfg.investment_parameters,
        "investment_methodology_external": cfg.investment_methodology_external,
        "repd_filtering": cfg.repd_filtering,
        "storage_cap_fraction": 0.20,
        "storage_credit_mode": "scheme_c",
        "storage_virtual_pool_energy_mwh": 1_000_000_000.0,
        "physical_period_hours": 0.5,
        "verified_run_ids": [
            "20260718_decarb_virtual_pool_1000twh_scheme_c",
            "20260719_base_cm_aligned_repd_virtual_pool_1000twh_scheme_c",
        ],
    })
    manifest = {
        "schema_version": "value.data-pack/v1",
        "id": "value-uk-1000twh-reproduction",
        "name": "UK VALUE — 1000 TWh verified data",
        "country": "GB",
        "timezone": "Europe/London",
        "period_hours": 0.5,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "bindings": bindings,
    }
    (TARGET / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Imported {len(bindings)} bindings into {TARGET}")


if __name__ == "__main__":
    main()
