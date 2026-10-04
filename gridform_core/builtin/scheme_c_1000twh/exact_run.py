"""Exact Scheme C annual-run boundary.

This module runs the packaged copy of the verified Scheme C research kernel.
It never imports or executes the desktop research tree.  Data files are bound
through a GridForm data pack, while the annual PSM -> investment -> pipeline ->
state-update order remains the order implemented by the authoritative kernel.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ...data import load_data_pack, required_uri


@dataclass(frozen=True)
class ExactRunRequest:
    pack_root: Path
    output_dir: Path
    start_year: int = 2025
    end_year: int = 2026
    periods: int = 17_520
    scenario: str = "existing_decarb_base"


ROLE_TO_CONFIG_KEY = {
    "demand.forecast": "forecast_demand",
    "demand.real": "real_demand",
    "market.france.profile": "france_profile",
    "market.france.price": "france_price",
    "market.belgium.profile": "belgium_profile",
    "market.belgium.price": "belgium_price",
    "market.netherlands.profile": "netherlands_profile",
    "market.netherlands.price": "netherlands_price",
    "market.norway.profile": "norway_profile",
    "market.norway.price": "norway_price",
    "market.ireland.profile": "ireland_profile",
    "market.ireland.price": "ireland_price",
    "profiles.vre_solar": "vre_solar_profile",
    "profiles.vre_onshore": "vre_onshore_profile",
    "profiles.vre_offshore": "vre_offshore_profile",
    "weather.solar": "solar_weather",
    "weather.wind": "wind_weather",
}


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


@contextmanager
def _environment(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _prepare_legacy_named_inputs(request: ExactRunRequest) -> Path:
    """Provide legacy filenames at the data-adapter boundary.

    The kernel still expects three historical filenames for REPD, policy costs,
    and planning success rates.  Copies live inside the run directory; the
    original data pack and the authoritative desktop model remain untouched.
    """

    pack = load_data_pack(request.pack_root)
    work = request.output_dir / "bound-inputs"
    work.mkdir(parents=True, exist_ok=True)
    for role, filename in {
        "source.repd_raw": "repd-q2-jul-2025.csv",
        "policy.support": "mechansim cost.xlsx",
        "planning.success_rates": "regional_technology_success_rates.csv",
    }.items():
        shutil.copy2(required_uri(pack, role), work / filename)
    return work


def _bind_pack(request: ExactRunRequest) -> None:
    pack = load_data_pack(request.pack_root)
    from .compat import config

    fleet = json.loads(Path(required_uri(pack, "fleet.generators")).read_text(encoding="utf-8"))
    model = json.loads(Path(required_uri(pack, "config.model_parameters")).read_text(encoding="utf-8"))
    costs = json.loads(Path(required_uri(pack, "costs.capital")).read_text(encoding="utf-8"))
    config.generators = fleet["generators"]
    config.batteries = fleet["batteries"]
    config.connections = fleet["connections"]
    config.electrolyzer = fleet["electrolyzer"]
    config.locations = fleet["locations"]
    config.investment_parameters = model["investment_parameters"]
    config.investment_methodology_external = model["investment_methodology_external"]
    config.capital_costs_per_mw = costs["capital_costs_per_mw"]
    config.simulation_parameters.update(model["simulation_parameters"])
    for role, key in ROLE_TO_CONFIG_KEY.items():
        config.file_paths[key] = required_uri(pack, role)
    config.simulation_parameters["periods"] = int(request.periods)
    config.simulation_parameters["solar_data"] = required_uri(pack, "weather.solar")
    config.simulation_parameters["wind_data"] = required_uri(pack, "weather.wind")


def run_exact_scheme_c(request: ExactRunRequest) -> dict:
    """Run the exact packaged Scheme C yearly chain and return parsed results."""

    if sys.version_info[:2] != (3, 10):
        raise RuntimeError(
            "Authoritative Scheme C runs require Python 3.10, matching the "
            "2026-07-18 retained-output environment. Refusing an unverified "
            f"Python {sys.version_info.major}.{sys.version_info.minor} run."
        )
    if request.end_year < request.start_year:
        raise ValueError("end_year must be greater than or equal to start_year")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    work = _prepare_legacy_named_inputs(request)
    env = {
        "PYTHONHASHSEED": "0",
        "START_YEAR": str(request.start_year),
        "END_YEAR": str(request.end_year),
        "OUTPUT_DIR": str(request.output_dir.resolve()),
        "ENABLE_CHECKPOINT": "1",
        "PLANNING_USE_MEDIAN": "1",
        "PIPELINE_DEFER_SPREAD_YEARS": "3",
        "CAPITAL_COST_PROFILE": "arup_medium",
        "PHYSICAL_PERIOD_HOURS": "0.5",
        "FAST_ANALYSIS_OUTPUT": "1",
        "TRACE_FORMAT": "sqlite",
        "SAVE_GENERATION_TRACE": "0",
        "SAVE_MARKET_TRACE": "0",
        "PYTHONIOENCODING": "utf-8",
        "VALIDATION_MODE": "0",
        "VALIDATION_DISABLE_EXTERNAL_PROJECTS": "0",
        "VALIDATION_HISTORICAL_DECARB": "0",
        "VALIDATION_INITIAL_CAPACITY_YEAR": "",
        "VALIDATION_REPD_FILE": "",
        "REPD_ZOMBIE_STATUS_STALE_YEAR": "2015",
        "REPD_ZOMBIE_SNAPSHOT_YEAR": str(request.start_year),
        "APPLY_REPD_INITIAL_SNAPSHOT": "1",
        "REPD_INCLUDE_UNCERTAIN_PROJECTS": "1",
        "REPD_UNCERTAIN_AS_MODEL_DECISION": "0",
        "STORAGE_EXPANSION_CAP_FRACTION": "0.20",
        "STORAGE_CAP_CREDIT_MODE": "scheme_c",
        "STORAGE_CAP_METHOD": "scheme_c_sim_trace",
        "STORAGE_VIRTUAL_POOL_ENERGY_MWH": "1000000000",
        "STORAGE_VIRTUAL_POOL_POWER_MW": "1e9",
        "MODEL_SUCCESS_MODE": "expected",
        "RUN_SUITE": "",
        "SCENARIO_V2": "1",
        "DECARB_V2_SCENARIO": request.scenario,
        "DECARB_SCENARIO": f"{request.scenario}_2025_2035",
    }
    with _environment(env), _working_directory(work):
        _bind_pack(request)
        # Import only after environment and data bindings are established.  The
        # authoritative module resolves scenario constants at import time.
        from .compat import case3

        case3.main()
    result = load_exact_results(request.output_dir, request.scenario)
    result["runtime"] = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "periods_per_year": int(request.periods),
        "start_year": int(request.start_year),
        "end_year": int(request.end_year),
        "data_pack": str(request.pack_root.resolve()),
    }
    (request.output_dir / "exact-run.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _numbers(row: dict) -> dict:
    converted = {}
    for key, value in row.items():
        try:
            converted[key] = float(value)
        except (TypeError, ValueError):
            converted[key] = value
    return converted


def load_exact_results(output_dir: Path, scenario: str) -> dict:
    suffix = f"case3_v2_{scenario}"
    costs = [_numbers(row) for row in _read_csv(output_dir / f"system_cost_history_{suffix}.csv")]
    capacities = [_numbers(row) for row in _read_csv(output_dir / f"capacity_history_{suffix}.csv")]
    investment_path = output_dir / "investment_analysis_trace.sqlite"
    investments: list[dict] = []
    if investment_path.exists():
        with sqlite3.connect(investment_path) as connection:
            query = """
                SELECT year, asset_type,
                       SUM(current_capacity),
                       SUM(suggested_new_capacity),
                       SUM(suggested_new_capacity - current_capacity)
                FROM investment_analysis
                GROUP BY year, asset_type
                ORDER BY year, asset_type
            """
            for year, technology, current, suggested, addition in connection.execute(query):
                investments.append({
                    "year": int(year),
                    "technology": technology,
                    "current_capacity_mw": float(current or 0),
                    "suggested_capacity_mw": float(suggested or 0),
                    "suggested_addition_mw": float(addition or 0),
                })
    return {
        "engine": "scheme-c-authoritative-packaged-kernel",
        "scenario": scenario,
        "system_cost_history": costs,
        "capacity_history": capacities,
        "investment_decisions": investments,
    }
