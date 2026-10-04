"""Build the deterministic CC0 VALUE 101 teaching data-pack family."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

from netCDF4 import Dataset


BASELINE_PACK_ID = "value-101-baseline-v1"
PACK_IDS = (BASELINE_PACK_ID,)
PERIODS_PER_YEAR = 17_520
HOURS_PER_YEAR = 8_760
BUILDER_VERSION = "scripts/build_value_101_packs.py@v2"
CREATED_AT = "2026-08-20T00:00:00Z"
ATTRIBUTION = (
    "VALUE 101 synthetic teaching data by Hanzhe Xing. "
    "Attribution is requested for scientific traceability but is not a CC0 condition."
)

SOLAR_LOCATIONS = (
    "Nottingham", "Ipswich", "London", "Newcastle", "Manchester", "Edinburgh",
    "Portsmouth", "Bournemouth", "Cardiff", "Birmingham", "Sheffield",
)
ONSHORE_LOCATIONS = SOLAR_LOCATIONS
OFFSHORE_LOCATIONS = tuple(f"offshore{index}" for index in range(1, 22))


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="")


def _write_csv(path: Path, rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def _write_weather(path: Path, *, variable: str, values: list[float]) -> None:
    """Write a small, deterministic netCDF3 field understood by the live PSM."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(path, "w", format="NETCDF3_CLASSIC") as dataset:
        dataset.createDimension("time", len(values))
        dataset.createDimension("latitude", 1)
        dataset.createDimension("longitude", 1)
        dataset.createVariable("time", "i4", ("time",))[:] = list(range(len(values)))
        dataset.createVariable("latitude", "f8", ("latitude",))[:] = [52.0]
        dataset.createVariable("longitude", "f8", ("longitude",))[:] = [0.0]
        field = dataset.createVariable(variable, "f8", ("time", "latitude", "longitude"))
        field[:, 0, 0] = values


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(pack_root: Path) -> dict[str, object]:
    return json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))


def _scientific_payload_sha256(manifest: dict[str, object]) -> str:
    digest = hashlib.sha256()
    bindings = dict(manifest.get("bindings") or {})
    for role, binding in sorted(bindings.items()):
        digest.update(str(role).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(binding["sha256"]).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _write_derivation(
    pack_root: Path,
    *,
    parent_pack_id: str | None,
    parent_payload_sha256: str | None,
    transform: str,
    affected_roles: list[str],
    unchanged_role_hashes_match: bool,
) -> None:
    _write_text(
        pack_root / "derivation.json",
        _json({
            "schema_version": "value.data-pack-derivation/v1",
            "parent_pack_id": parent_pack_id,
            "parent_scientific_payload_sha256": parent_payload_sha256,
            "transform": transform,
            "affected_roles": affected_roles,
            "unchanged_role_hashes_match": unchanged_role_hashes_match,
            "builder_version": BUILDER_VERSION,
            "licence": "CC0-1.0",
            "cc0_statement": (
                "This deterministic synthetic teaching data pack is dedicated "
                "to the public domain under CC0-1.0."
            ),
        }),
    )


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _solar_profile(period: int) -> float:
    day = period // 48
    hour = (period % 48) / 2.0
    if hour < 6.0 or hour > 18.0:
        return 0.0
    daylight = math.sin((hour - 6.0) * math.pi / 12.0)
    season = 0.58 + 0.42 * math.sin((day - 80) * 2 * math.pi / 365.0) ** 2
    return round(max(0.0, min(daylight * season, 1.0)), 6)


def _wind_profile(period: int) -> float:
    day = period // 48
    within_day = period % 48
    value = (
        0.42
        + 0.13 * math.sin((within_day + 5) * 2 * math.pi / 48)
        + 0.12 * math.sin((day + 17) * 2 * math.pi / 29)
        + 0.08 * math.cos((day + 31) * 2 * math.pi / 365)
    )
    return round(max(0.08, min(value, 0.92)), 6)


def _demand(period: int) -> float:
    day = period // 48
    hour = (period % 48) / 2.0
    morning = 9.0 * math.exp(-((hour - 8.0) / 2.2) ** 2)
    evening = 19.0 * math.exp(-((hour - 19.0) / 2.5) ** 2)
    overnight = 2.0 * math.exp(-((hour - 1.0) / 3.5) ** 2)
    winter = 1.0 + 0.16 * math.cos(day * 2 * math.pi / 365.0)
    weekday = 1.0 if day % 7 < 5 else 0.92
    teaching_peak = 30.0 if period % 48 == 31 and day in {0, 182} else 0.0
    return round((22.0 + morning + evening + overnight) * winter * weekday + teaching_peak, 6)


def _forecast_demand(period: int) -> float:
    """Introduce a visible midday balancing event without using random noise."""

    balancing_margin = 12.0 if period % 48 == 30 and period // 48 in {0, 182} else 0.0
    return round(_demand(period) + balancing_margin, 6)


def _build_baseline_pack(destination: Path) -> dict[str, object]:
    """Create the deterministic VALUE 101 baseline pack."""

    destination = destination.resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    files: dict[str, tuple[str, str, str | None]] = {}

    def register(role: str, filename: str, file_format: str, unit: str | None = None) -> Path:
        path = destination / "files" / role.replace(".", "__") / filename
        files[role] = (path.relative_to(destination).as_posix(), file_format, unit)
        return path

    real_demand_rows = [["mwh"], *[[_demand(period)] for period in range(PERIODS_PER_YEAR)]]
    forecast_demand_rows = [["mwh"], *[[_forecast_demand(period)] for period in range(PERIODS_PER_YEAR)]]
    _write_csv(register("demand.real", "real.csv", "csv", "MW"), real_demand_rows)
    _write_csv(
        register("demand.forecast", "forecast.csv", "csv", "MW"),
        forecast_demand_rows,
    )

    profiles = {
        "profiles.vre_solar": [_solar_profile(period) for period in range(PERIODS_PER_YEAR)],
        "profiles.vre_onshore": [_wind_profile(period) for period in range(PERIODS_PER_YEAR)],
        "profiles.vre_offshore": [
            round(min(_wind_profile(period) * 1.08, 1.0), 6)
            for period in range(PERIODS_PER_YEAR)
        ],
    }
    for role, values in profiles.items():
        _write_csv(
            register(role, f"{role.rsplit('.', 1)[-1]}.csv", "csv"),
            [[value] for value in values],
        )

    hourly_solar = [_solar_profile(hour * 2) * 3_600_000.0 for hour in range(HOURS_PER_YEAR)]
    hourly_wind = [
        7.0 + 2.0 * math.sin((hour + 3) * 2 * math.pi / 24)
        + 1.2 * math.sin((hour // 24 + 17) * 2 * math.pi / 29)
        for hour in range(HOURS_PER_YEAR)
    ]
    _write_weather(
        register("weather.wind", "wind.nc", "nc"),
        variable="wind_speed",
        values=hourly_wind,
    )
    _write_weather(
        register("weather.solar", "solar.nc", "nc"),
        variable="ssrd",
        values=hourly_solar,
    )

    for country in ("france", "belgium", "netherlands", "norway", "ireland"):
        available = 12.0 if country == "france" else 0.0
        price = 82.0 if country == "france" else 200.0
        _write_csv(
            register(f"market.{country}.profile", f"{country}-profile.csv", "csv"),
            [["mwh"], *[[available] for _ in range(PERIODS_PER_YEAR)]],
        )
        _write_csv(
            register(f"market.{country}.price", f"{country}-price.csv", "csv"),
            [[price] for _ in range(PERIODS_PER_YEAR)],
        )

    renewable_template = {
        "gen_cost": 0.0001,
        "curtail_cost": 0.0,
        "carbon_emission": 0.0,
        "capital_cost": 0.0,
        "real_gen_energy": 0.0,
        "unit_time_cost": 0.0,
        "electrolyzer_cost": 15_000.0,
        "energy_efficiency": 0.65,
        "electrolyzer_limit": 1.0,
        "rampup_rate": 0.125,
    }
    generators: dict[str, dict[str, object]] = {
        "CCGT": {
            "name": "CCGT",
            "gen_cost": 0.5,
            "curtail_cost": 66.5,
            "carbon_emission": 0.0,
            "capacity_limit": 50.0,
            "alter_limit": 50.0,
            "startup_cost": 0.0,
            "carbon_intensity": 394.0,
            "capital_cost": 50_000_000.0,
            "carbon_price": 8.0,
            "fuel_cost": 58.0,
            "real_gen_energy": 0.0,
            "unit_time_cost": 0.0,
        }
    }
    for prefix, names in (
        ("solar", SOLAR_LOCATIONS),
        ("onshore", ONSHORE_LOCATIONS),
    ):
        for location in names:
            name = f"{prefix}_{location}"
            generators[name] = {
                "name": name,
                **renewable_template,
                "capacity_multiplier": 1.0 if location == "Nottingham" else 0.0,
            }
    for location in OFFSHORE_LOCATIONS:
        generators[location] = {
            "name": location,
            **renewable_template,
            "capacity_multiplier": 0.0,
        }

    connections = {
        "Interconnect_France": {
            "name": "Interconnect_France", "capital_cost": 0.0,
            "carbon_emission": 0.0, "carbon_intensity": 53.0,
        },
        "Interconnect_Beligum": {
            "name": "Interconnect_Beligum", "capital_cost": 0.0,
            "carbon_emission": 0.0, "carbon_intensity": 179.0,
        },
        "Interconnect_Netherland": {
            "name": "Interconnect_Netherland", "capital_cost": 0.0,
            "carbon_emission": 0.0, "carbon_intensity": 474.0,
        },
        "Interconnect_Norway": {
            "name": "Interconnect_Norway", "capital_cost": 0.0,
            "carbon_emission": 0.0, "carbon_intensity": 100.0,
        },
        "Interconnect_Ireland": {
            "name": "Interconnect_Ireland", "capital_cost": 0.0,
            "carbon_emission": 0.0, "carbon_intensity": 458.0,
        },
    }
    fleet = {
        "generators": generators,
        "batteries": {
            "1c_battery": {
                "name": "1c_battery",
                "pool_limit": 10.0,
                "per_pool_limit": 10.0,
                "storage_fee": 0.0,
                "per_storage_fee": 0.0,
                "n_1": 0.9,
                "n_2": 0.9,
                "carbon_emission": 50.0,
                "capital_cost": 500_000.0,
                "battery_type": "1c",
            }
        },
        "connections": connections,
        "electrolyzer": {
            "name": "electrolyzer",
            "capital_cost": 0.0,
            "operational_cost": 0.0,
            "energy_efficiency": 0.65,
            "cycle_life": 50_000,
            "capacity_limit": 0.0,
            "rampup_rate": 0.125,
            "body_emission": 0.0,
        },
        "locations": {
            name: {"lat": 52.0, "lon": 0.0}
            for name in (*SOLAR_LOCATIONS, *OFFSHORE_LOCATIONS)
        },
    }
    _write_text(register("fleet.generators", "fleet.json", "json"), _json(fleet))

    costs = {
        "capital_costs_per_mw": {
            "CCGT": 1_000_000.0,
            "solar": 650_000.0,
            "onshore": 1_350_000.0,
            "offshore": 2_700_000.0,
            "battery": 50_000.0,
        }
    }
    _write_text(register("costs.capital", "costs.json", "json", "GBP/MW"), _json(costs))

    project_columns = [
        "project_id", "technology", "capacity_mw", "development_status", "region",
        "planning_application_submitted", "planning_permission_granted",
        "under_construction", "operational",
    ]
    project_rows = [
        project_columns,
        ["value101-solar-operating", "solar", 35.0, "Operational", "GB", "", "", "", "01/01/2024"],
        ["value101-wind-operating", "onshore", 20.0, "Operational", "GB", "", "", "", "01/01/2024"],
        ["value101-battery-operating", "battery", 10.0, "Operational", "GB", "", "", "", "01/01/2024"],
        ["value101-solar-planning", "solar", 15.0, "Application Submitted", "GB", "01/01/2025", "", "", ""],
    ]
    _write_csv(register("projects.repd", "projects.csv", "csv"), project_rows)

    raw_columns = [
        "Ref ID", "Site Name", "Technology Type", "Installed Capacity (MWelec)",
        "Development Status", "Development Status (short)", "Country", "Region",
        "Planning Application Submitted", "Planning Permission Granted",
        "Under Construction", "Operational",
    ]
    raw_rows = [
        raw_columns,
        ["value101-solar-operating", "VALUE 101 Solar", "Solar Photovoltaics", 35.0, "Operational", "Operational", "Synthetic", "South East", "", "", "", "01/01/2024"],
        ["value101-wind-operating", "VALUE 101 Wind", "Wind Onshore", 20.0, "Operational", "Operational", "Synthetic", "South East", "", "", "", "01/01/2024"],
        ["value101-battery-operating", "VALUE 101 Battery", "Battery", 10.0, "Operational", "Operational", "Synthetic", "South East", "", "", "", "01/01/2024"],
        ["value101-solar-planning", "VALUE 101 Solar Extension", "Solar Photovoltaics", 15.0, "Application Submitted", "Application Submitted", "Synthetic", "South East", "01/01/2025", "", "", ""],
    ]
    _write_csv(register("source.repd_raw", "repd.csv", "csv"), raw_rows)

    _write_text(
        register("policy.support", "policy.json", "json"),
        _json({"synthetic": True, "mechanisms": []}),
    )
    timelines = {
        "development_stage_timelines": {
            "solar": {"total_median": 12.0, "total_mean": 12.0},
            "onshore": {"total_median": 18.0, "total_mean": 18.0},
            "offshore": {"total_median": 30.0, "total_mean": 30.0},
            "battery": {"total_median": 12.0, "total_mean": 12.0},
        },
        "development_timelines": {"solar": 12.0, "onshore": 18.0, "offshore": 30.0, "battery": 12.0},
        "repd_status_to_timeline": {
            "Application Submitted": {"timeline_type": "total_median"}
        },
    }
    _write_text(register("planning.timelines", "timelines.json", "json"), _json(timelines))
    _write_csv(
        register("planning.success_rates", "success.csv", "csv"),
        [
            ["Technology", "Region", "Success_Rate"],
            ["solar", "GB", 1.0],
            ["onshore", "GB", 1.0],
            ["offshore", "GB", 1.0],
            ["battery", "GB", 1.0],
        ],
    )
    config = {
        "simulation_parameters": {"periods": PERIODS_PER_YEAR, "bidding_factor": 1.0},
        "investment_parameters": {"target_payback_years": {"default": 25.0}},
        "investment_methodology_external": {"preferred_rates": {}},
        "repd_filtering": {
            "apply_zombie_filter": False,
            "zombie_status_stale_year": 2015,
            "minimum_project_size_mw": 0.1,
            "max_completion_year": 2035,
        },
        "storage_cap_fraction": 0.2,
        "physical_period_hours": 0.5,
        "teaching_scope": {
            "periods_per_year": PERIODS_PER_YEAR,
            "annual_economics_eligible": True,
            "scientific_baseline_eligible": False,
        },
    }
    _write_text(register("config.model_parameters", "parameters.json", "json"), _json(config))

    bindings: dict[str, dict[str, object]] = {}
    for role, (uri, file_format, unit) in sorted(files.items()):
        path = destination / uri
        bindings[role] = {
            "role": role,
            "uri": uri,
            "filename": path.name,
            "format": file_format,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "unit": unit,
            "source_url": f"generated://value-101/{BASELINE_PACK_ID}/{role}",
            "source_version": "value-101-generator-v1",
            "access_date": "2026-08-20",
            "licence": "CC0-1.0",
            "attribution": ATTRIBUTION,
            "redistribution_class": "redistributable_cc0",
            "transformation_version": BUILDER_VERSION,
        }

    manifest = {
        "schema_version": "value.data-pack/v1",
        "id": BASELINE_PACK_ID,
        "name": "VALUE 101 baseline teaching data",
        "country": "SYNTHETIC",
        "timezone": "UTC",
        "period_hours": 0.5,
        "periods_per_year": PERIODS_PER_YEAR,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
        "publication_status": "redistributable",
        "licence": "CC0-1.0",
        "copyright_affirmer": "Hanzhe Xing",
        "teaching_only": True,
        "annual_economics_eligible": True,
        "scientific_baseline_eligible": False,
        "allowed_run_modes": ["smoke", "two_year_smoke", "value_101_day", "two_year"],
        "bindings": bindings,
    }
    _write_text(destination / "manifest.json", _json(manifest))
    _write_text(
        destination / "LICENSE",
        "CC0 1.0 Universal\n\n"
        "Hanzhe Xing has dedicated the VALUE 101 synthetic teaching data to the public domain.\n"
        "You may copy, modify, distribute and use these synthetic data without permission.\n"
        "https://creativecommons.org/publicdomain/zero/1.0/\n",
    )
    _write_derivation(
        destination,
        parent_pack_id=None,
        parent_payload_sha256=None,
        transform="deterministic VALUE 101 baseline generator",
        affected_roles=sorted(bindings),
        unchanged_role_hashes_match=True,
    )
    return {
        "pack_id": BASELINE_PACK_ID,
        "bindings": len(bindings),
        "destination": str(destination),
    }


def build_value_101_pack_family(output_root: Path) -> dict[str, object]:
    """Build the one complete annual VALUE 101 baseline pack."""

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    baseline = output_root / BASELINE_PACK_ID
    reports = [_build_baseline_pack(baseline)]
    return {
        "schema_version": "value.101-pack-family-build/v1",
        "pack_ids": list(PACK_IDS),
        "packs": reports,
    }


def _check_checked_in_family(root: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="value-101-pack-check-") as temporary:
        rebuilt_root = Path(temporary)
        build_value_101_pack_family(rebuilt_root)
        checks = {
            pack_id: (
                (root / pack_id).is_dir()
                and _tree_hash(root / pack_id) == _tree_hash(rebuilt_root / pack_id)
            )
            for pack_id in PACK_IDS
        }
    if not all(checks.values()):
        failed = ", ".join(pack_id for pack_id, passed in checks.items() if not passed)
        raise SystemExit(f"Checked-in VALUE 101 packs are stale or missing: {failed}")
    return {"schema_version": "value.101-pack-check/v1", "passed": True, "packs": checks}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data-packs",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        report = _check_checked_in_family(args.output_root)
    else:
        report = build_value_101_pack_family(args.output_root)
    print(_json(report), end="")


if __name__ == "__main__":
    main()
