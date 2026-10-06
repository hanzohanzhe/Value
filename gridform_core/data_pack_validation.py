"""Bounded semantic validation for imported power-system data packs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import math
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = "value.data-pack-validation/v2"
# P0-5a S9: required NetCDF data variables and their canonical units per role.
NETCDF_VARIABLES = {
    "weather.solar": ({"ssrd"},),
    "weather.wind": ({"wind_speed"}, {"u100", "v100"}),
}
NETCDF_UNITS = {"ssrd": "J m-2", "wind_speed": "m s-1", "u100": "m s-1", "v100": "m s-1"}
TIME_LENGTHS = {8760, 8784}
CLOCK_ROLES = {
    "demand.forecast", "demand.real",
    "market.france.profile", "market.france.price",
    "market.belgium.profile", "market.belgium.price",
    "market.netherlands.profile", "market.netherlands.price",
    "market.norway.profile", "market.norway.price",
    "market.ireland.profile", "market.ireland.price",
    "profiles.vre_solar", "profiles.vre_onshore", "profiles.vre_offshore",
}
DEMAND_ROLES = {"demand.forecast", "demand.real"}
# Audited published raw-MW bytes whose v1 manifests incorrectly said MWh/period.
# Compatibility is content-bound, never inferred from a missing metadata field.
LEGACY_DEMAND_MW_SHA256 = {
    "demand.forecast": {"62b59aa0e32a62636b6fdecc8fab6499ea6e9a5c728ff1905acbf271f8824fe0", "fcdb98f9a0d3bd7d8d75db9aea05153164b2ad88128ea7085dd9897162c626a3"},
    "demand.real": {"75b5f11d2c5603802cf49f07af48547da9cb3f4fca4539f7f90db24c3870e77b", "fcdb98f9a0d3bd7d8d75db9aea05153164b2ad88128ea7085dd9897162c626a3"},
}
VRE_PROFILE_ROLES = {"profiles.vre_solar", "profiles.vre_onshore", "profiles.vre_offshore"}
CYCLIC_MARKET_ROLES = CLOCK_ROLES.difference(DEMAND_ROLES | VRE_PROFILE_ROLES)
REQUIRED_JSON_KEYS = {
    "fleet.generators": {"generators", "batteries", "connections"},
    "costs.capital": {"capital_costs_per_mw"},
    "planning.timelines": {"development_stage_timelines"},
    "config.model_parameters": {"simulation_parameters", "investment_parameters"},
    "value.network.buses": {"buses"},
    "value.network.branches": {"branches"},
    "value.network.asset-map": {"asset_mappings"},
    "value.network.ac.generators": {"generator_specs"},
    "value.hydrology.reservoir-parameters": {"reservoirs"},
    "value.network.expansion.candidates": {"candidates"},
    "value.zonal.zones": {"zones"},
    "value.zonal.corridors": {"corridors"},
    "value.zonal.cutsets": {"cutsets"},
    "value.zonal.asset-map": {"asset_mappings"},
    "value.zonal.demand": {"zonal_demand"},
    "value.zonal.ratings": {"rating_profiles"},
    "value.zonal.interconnector-landings": {"interconnector_landings"},
    "value.zonal.spatial-audit": {
        "active_asset_ids", "capacity_mw_by_technology",
        "mapped_capacity_mw_by_technology", "tolerance_mw",
    },
}
REQUIRED_CSV_COLUMNS = {
    "projects.repd": {"project_id", "technology", "capacity_mw", "development_status", "region"},
    "source.repd_raw": {"Ref ID", "Site Name", "Technology Type", "Installed Capacity (MWelec)", "Development Status"},
    "planning.success_rates": {"Technology", "Region", "Success_Rate"},
    "value.network.nodal-demand": {"period_id", "bus_id", "demand_mwh"},
    "value.network.ac.reactive-demand": {"period_id", "bus_id", "reactive_demand_mvar"},
    "value.network.ac.active-schedule": {"period_id", "asset_id", "active_schedule_mwh"},
    "value.hydrology.site-catalogue": {"site_id", "technology_class", "bus_id", "capacity_mw", "turbine_efficiency", "source", "licence"},
    "value.hydrology.asset-site-map": {"asset_id", "site_id", "share"},
    "value.hydrology.run-of-river-inflow": {"timestamp", "site_id", "value", "unit", "interval_hours", "timezone"},
    "value.hydrology.reservoir-inflow": {"timestamp", "site_id", "value", "unit", "interval_hours", "timezone"},
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(pack_root: Path, uri: str) -> Path:
    path = (pack_root / uri).resolve()
    try:
        path.relative_to(pack_root.resolve())
    except ValueError as exc:
        raise ValueError("binding path escapes the data-pack root") from exc
    return path


def _csv_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        return raw.decode("cp1252"), "cp1252"


def _csv_shape(path: Path) -> tuple[int, list[str], str]:
    text, encoding = _csv_text(path)
    rows = list(csv.reader(io.StringIO(text)))
    return len(rows), (rows[0] if rows else []), encoding


def normalize_unit(value: object) -> str:
    """UDUNITS-style spelling: 'm s**-1', 'm s-1', 'm/s' and 'm.s-1' are the same unit."""

    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text.replace("**", "").replace("^", "").replace(".", " ")
    match = re.fullmatch(r"([A-Za-z]+)\s*/\s*([A-Za-z]+)(\d*)", text)
    if match:
        text = f"{match.group(1)} {match.group(2)}-{match.group(3) or '1'}"
    return re.sub(r"\s+", " ", text)


def _registry_unit(path: Path, binding: Mapping[str, object]) -> object:
    from .series_reader import registry_entry

    entry = registry_entry(path, binding)
    field = dict(dict(entry or {}).get("fields") or {}).get("unit") or {}
    return field.get("value") if field.get("status") == "registry_asserted" else None


def _series_cells(path: Path, binding: Mapping[str, object]) -> tuple[list[float], int]:
    """The values of a single-series CSV role: the declared csv_column, else the legacy rule (P6-01)."""

    column = binding.get("csv_column")
    if not column:
        return _first_numeric_column(path)
    text, _encoding = _csv_text(path)
    reader = csv.DictReader(io.StringIO(text))
    if column not in (reader.fieldnames or []):
        return [], 1
    values: list[float] = []
    invalid = 0
    for row in reader:
        try:
            values.append(float(str(row.get(column) or "").strip()))
        except ValueError:
            invalid += 1
    return values, invalid


def _netcdf_structure(dataset: object, role: str, np: object) -> tuple[list[str], list[str], dict[str, object]]:
    """Structural NetCDF checks: data variables only (ndim >= 2, not coordinates), units, time axis, finiteness."""

    errors: list[str] = []
    warnings: list[str] = []
    dimensions = set(dataset.dimensions)  # type: ignore[attr-defined]
    data_variables = {
        name: variable for name, variable in dataset.variables.items()  # type: ignore[attr-defined]
        if name not in dimensions and getattr(variable, "ndim", 0) >= 2
        and getattr(variable.dtype, "kind", "") in {"i", "u", "f"}
    }
    details: dict[str, object] = {"data_variables": sorted(data_variables)}
    if not data_variables:
        errors.append("NetCDF has no numeric data variable")
        return errors, warnings, details
    options = NETCDF_VARIABLES.get(role)
    required: set[str] = set()
    if options:
        present = next((option for option in options if option <= set(data_variables)), None)
        if present is None:
            errors.append("NetCDF lacks the required variable " + " or ".join("+".join(sorted(o)) for o in options))
        else:
            required = set(present)
    for name in sorted(required):
        units = getattr(data_variables[name], "units", None)
        if units is None:
            warnings.append(f"NetCDF variable {name} declares no units; {NETCDF_UNITS[name]} is assumed")
        elif normalize_unit(units) != NETCDF_UNITS[name]:
            errors.append(f"NetCDF variable {name} has units {units!r}; expected {NETCDF_UNITS[name]}")
    lengths = {name: len(value) for name, value in dataset.dimensions.items()}  # type: ignore[attr-defined]
    if "time" in lengths:
        time_ok = lengths["time"] in TIME_LENGTHS
    elif "dayofyear" in lengths and "hour" in lengths:
        time_ok = lengths["dayofyear"] in (365, 366) and lengths["hour"] == 24
    else:
        time_ok = False
    details["time_axis"] = {key: lengths[key] for key in ("time", "dayofyear", "hour") if key in lengths}
    if options and not time_ok:
        errors.append("NetCDF time axis must be 8760/8784 hours or 365/366 days x 24 hours")
    sampled = bad = 0
    for name in sorted(required or set(list(data_variables)[:1])):
        variable = data_variables[name]
        index = tuple(
            slice(None, None, max(1, len(dataset.dimensions[dim]) // 10))  # type: ignore[attr-defined]
            if dim in ("latitude", "longitude", "lat", "lon") else slice(None)
            for dim in variable.dimensions
        )
        flat = np.ma.asarray(variable[index]).filled(np.nan).reshape(-1)  # type: ignore[attr-defined]
        sampled += int(flat.size)
        bad += int(np.count_nonzero(~np.isfinite(flat)))  # type: ignore[attr-defined]
    details.update({"validation_level": "data_variables_full_time_strided_space",
                    "sampled_numeric_values": sampled, "sampled_non_finite_values": bad})
    if bad:
        errors.append("NetCDF data variable contains missing or non-finite values")
    return errors, warnings, details


def _first_numeric_column(path: Path) -> tuple[list[float], int]:
    text, _encoding = _csv_text(path)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], 0
    width = max(len(row) for row in rows)
    candidates: list[tuple[list[float], int]] = []
    for column in range(width):
        values: list[float] = []
        invalid = 0
        for row_number, row in enumerate(rows):
            raw = row[column].strip() if column < len(row) else ""
            if not raw:
                if row_number == 0:
                    continue
                invalid += 1
                continue
            try:
                value = float(raw)
            except ValueError:
                if row_number == 0:
                    # Only the first physical row may be an optional header.
                    continue
                invalid += 1
                continue
            values.append(value)
        candidates.append((values, invalid))
    return max(candidates, key=lambda item: len(item[0]))


def _own_manifest_bytes(pack_root: Path, manifest: Mapping[str, object]) -> bytes | None:
    """The pack's manifest file bytes when ``manifest`` is that file's content (whitelist pins, N-1)."""

    try:
        raw = (Path(pack_root) / "manifest.json").read_bytes()
        return raw if json.loads(raw.decode("utf-8")) == dict(manifest) else None
    except (OSError, ValueError):
        return None


def validate_data_pack(
    pack_root: Path,
    manifest: Mapping[str, object],
    dataset_slots: Sequence[Mapping[str, object]],
    *,
    full_year_periods: int = 17_520,
    verify_hashes_below_bytes: int = 32 * 1024 * 1024,
    layers: bool = True,
) -> dict[str, object]:
    """Validate a pack.  ``valid`` is the structural layer only (P0-5a S9).

    With ``layers`` the report also carries the chronology and plausibility
    layers and ``profile_eligibility`` (which findings block which
    methodology profile); preflight reads the eligibility of the run's profile.
    """
    pack_root = pack_root.resolve()
    if bool(manifest.get("teaching_only")):
        declared_periods = manifest.get("periods_per_year")
        if (
            isinstance(declared_periods, int)
            and not isinstance(declared_periods, bool)
            and 1 <= declared_periods <= 17_520
            and manifest.get("annual_economics_eligible") is False
            and manifest.get("scientific_baseline_eligible") is False
        ):
            full_year_periods = declared_periods
    bindings = dict(manifest.get("bindings") or {})  # type: ignore[arg-type]
    reports: list[dict[str, object]] = []
    errors: list[str] = []
    warnings: list[str] = []
    slot_by_role = {str(slot["role"]): slot for slot in dataset_slots}

    for role, slot in slot_by_role.items():
        binding = bindings.get(role)
        row_errors: list[str] = []
        row_warnings: list[str] = []
        details: dict[str, object] = {}
        if not isinstance(binding, Mapping):
            if slot.get("required"):
                row_errors.append("required semantic role is not bound")
            reports.append({"role": role, "status": "failed" if row_errors else "not_bound", "errors": row_errors, "warnings": row_warnings})
            errors.extend(f"{role}: {item}" for item in row_errors)
            continue
        try:
            path = _resolve(pack_root, str(binding.get("uri") or ""))
        except ValueError as exc:
            row_errors.append(str(exc))
            path = pack_root / "missing"
        file_format = str(binding.get("format") or path.suffix.lstrip(".")).lower()
        if file_format not in tuple(slot.get("formats") or ()):
            row_errors.append(f"format {file_format or 'unknown'} is not accepted")
        if not path.is_file():
            row_errors.append("bound file is missing")
        else:
            size = path.stat().st_size
            details["bytes"] = size
            declared = str(binding.get("sha256") or "")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", declared):
                row_errors.append("valid SHA-256 provenance is missing")
            elif size <= verify_hashes_below_bytes:
                details["checksum_verified"] = _sha256(path).lower() == declared.lower()
                if not details["checksum_verified"]:
                    row_errors.append("SHA-256 checksum does not match the imported file")
            else:
                details["checksum_verified"] = False
                row_warnings.append("large-file checksum deferred to immutable run provenance")

            if file_format == "csv":
                count, first_row, encoding = _csv_shape(path)
                details.update({"csv_rows_including_optional_header": count, "first_row_columns": len(first_row), "encoding": encoding})
                if role in DEMAND_ROLES:
                    details["clock_adapter"] = "take_first_required_periods"
                    values, invalid = _series_cells(path, binding)
                    details["numeric_values"] = len(values)
                    details["csv_data_rows"] = len(values)
                    details["non_numeric_or_missing_cells"] = invalid
                    if invalid:
                        row_errors.append(
                            f"demand contains {invalid} non-numeric or missing data cells "
                            "after the optional header"
                        )
                    if len(values) < full_year_periods:
                        row_errors.append(
                            f"demand contains {len(values)} numeric periods; "
                            f"at least {full_year_periods} are required"
                        )
                    elif len(values) != full_year_periods:
                        row_warnings.append(
                            f"source contains {len(values)} numeric periods plus any header; "
                            f"the VALUE adapter selects the first {full_year_periods} periods"
                        )
                    if any(not math.isfinite(value) or value < 0 for value in values):
                        row_errors.append("demand contains a negative or non-finite value")
                elif role in CYCLIC_MARKET_ROLES:
                    details["clock_adapter"] = "cyclic_repeat"
                    values, invalid = _series_cells(path, binding)
                    details["numeric_values"] = len(values)
                    details["csv_data_rows"] = len(values)
                    details["non_numeric_or_missing_cells"] = invalid
                    if invalid:
                        row_errors.append(
                            f"cyclic market series contains {invalid} non-numeric or missing "
                            "data cells after the optional header"
                        )
                    if len(values) < 1:
                        row_errors.append("cyclic market series is empty")
                    elif len(values) != full_year_periods:
                        row_warnings.append(
                            f"source contains {len(values)} numeric periods plus any header; "
                            "the VALUE interconnector adapter repeats it cyclically"
                        )
                elif role in VRE_PROFILE_ROLES:
                    details["clock_adapter"] = "hourly_or_half_hour_profile"
                    minimum = max(full_year_periods // 2, 1)
                    values, invalid = _series_cells(path, binding)
                    details["numeric_values"] = len(values)
                    details["csv_data_rows"] = len(values)
                    details["non_numeric_or_missing_cells"] = invalid
                    if len(values) < minimum:
                        row_errors.append(
                            f"VRE profile contains {len(values)} numeric periods; at least "
                            f"{minimum} hourly-equivalent periods are required"
                        )
                    if invalid:
                        row_errors.append(
                            f"VRE profile contains {invalid} non-numeric or missing data cells "
                            "after the optional header"
                        )
                    if any(not math.isfinite(value) or value < 0 or value > 1 for value in values):
                        row_errors.append("VRE profile must contain finite per-unit values between 0 and 1")
                required_columns = REQUIRED_CSV_COLUMNS.get(role)
                if required_columns:
                    missing = sorted(required_columns.difference(first_row))
                    if missing:
                        row_errors.append("missing columns: " + ", ".join(missing))
                    elif role == "projects.repd":
                        text, _encoding = _csv_text(path)
                        ids = [
                            str(row.get("project_id") or "").strip()
                            for row in csv.DictReader(io.StringIO(text))
                        ]
                        duplicates = len(ids) - len(set(ids))
                        details["duplicate_project_ids"] = duplicates
                        if duplicates:
                            row_errors.append(f"contains {duplicates} duplicate project IDs")
                        reader = list(csv.DictReader(io.StringIO(text)))
                        bad_capacity = 0
                        broken_technology = 0
                        for record in reader:
                            try:
                                value = float(record.get("capacity_mw") or "nan")
                                bad_capacity += int(not math.isfinite(value) or value < 0)
                            except ValueError:
                                bad_capacity += 1
                            broken_technology += int(not str(record.get("technology") or "").strip())
                        if bad_capacity:
                            row_errors.append(f"contains {bad_capacity} invalid capacity_mw values")
                        if broken_technology:
                            row_errors.append(f"contains {broken_technology} missing technology labels")
            elif file_format == "json":
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    row_errors.append(f"invalid JSON: {exc}")
                else:
                    required_keys = REQUIRED_JSON_KEYS.get(role, set())
                    if not isinstance(payload, Mapping):
                        row_errors.append("JSON root must be an object")
                    else:
                        missing = sorted(required_keys.difference(payload))
                        if missing:
                            row_errors.append("missing JSON keys: " + ", ".join(missing))
            elif file_format == "nc":
                try:
                    import netCDF4
                    import numpy as np
                except ImportError:
                    row_warnings.append(
                        "NetCDF scientific validation was not evaluated because netCDF4 is unavailable"
                    )
                    details["validation_level"] = "container_only"
                else:
                    try:
                        with netCDF4.Dataset(path, mode="r") as dataset:
                            details["dimensions"] = {
                                name: len(value) for name, value in dataset.dimensions.items()
                            }
                            nc_errors, nc_warnings, nc_details = _netcdf_structure(dataset, role, np)
                            row_errors.extend(nc_errors)
                            row_warnings.extend(nc_warnings)
                            details.update(nc_details)
                    except (OSError, RuntimeError, IndexError) as exc:
                        row_errors.append(f"invalid NetCDF structure: {exc}")
            elif file_format == "zarr":
                details["validation_level"] = "container_only"
                row_warnings.append("Zarr deep chunk validation requires the optional zarr capability")

            expected_unit = slot.get("unit")
            declared_unit = binding.get("unit")
            if role in DEMAND_ROLES and expected_unit == "MW":
                if binding.get("input_unit_contract") not in (None, "value.demand-mw-half-hour/v1"):
                    row_errors.append("Unknown demand input_unit_contract; use explicit CSV mapping")
                if ("interval_minutes" in binding and (isinstance(binding["interval_minutes"], bool)
                        or binding["interval_minutes"] != 30)):
                    row_errors.append("Demand interval_minutes must be 30; resampling is not supported")
                if binding.get("input_unit_contract") and binding.get("interval_minutes") != 30:
                    row_errors.append("The explicit demand contract requires interval_minutes=30")
            if expected_unit and not declared_unit:
                row_warnings.append(f"unit is not declared; canonical role expects {expected_unit}")
            elif (role in DEMAND_ROLES and expected_unit == "MW" and declared_unit == "MWh/period"
                  and not binding.get("input_unit_contract")
                  and details.get("checksum_verified") is True
                  and binding.get("sha256") in LEGACY_DEMAND_MW_SHA256[role]):
                # Preserve historical bytes and their actual raw-MW interpretation.
                # New mapped uploads always carry the explicit MW contract.
                details["legacy_unit_interpretation"] = {"declared_unit": declared_unit, "runtime_unit": "MW",
                    "interval_minutes": 30, "definition_id": "value.legacy-demand-label/v1"}
                row_warnings.append("Legacy demand label MWh/period is interpreted as raw MW, as in historical VALUE runs. "
                                    "Use CSV mapping with an explicit source unit for new data; old bytes are unchanged.")
            elif (expected_unit and declared_unit != expected_unit and details.get("checksum_verified") is True
                  and _registry_unit(path, binding) == expected_unit):
                # A verified registry object whose label is known to be wrong
                # (GBP1 public1 interconnector flows: MWh/period on MW values, P6-12).
                details["registry_unit_interpretation"] = {"declared_unit": declared_unit, "runtime_unit": expected_unit}
                row_warnings.append(f"unit label {declared_unit} is a known mislabel of this object; "
                                    f"the values are {expected_unit} (truth registry)")
            elif expected_unit and declared_unit != expected_unit:
                row_errors.append(f"unit {declared_unit} does not match canonical {expected_unit}")

        status = "passed" if not row_errors else "failed"
        reports.append({"role": role, "status": status, "errors": row_errors, "warnings": row_warnings, "details": details})
        errors.extend(f"{role}: {item}" for item in row_errors)
        warnings.extend(f"{role}: {item}" for item in row_warnings)

    layer_report = None
    eligibility = None
    if layers:
        from .data_validation_layers import evaluate_layers, profile_eligibility

        try:
            layer_report = evaluate_layers(pack_root, manifest, periods=full_year_periods)
            eligibility = profile_eligibility(manifest, layer_report, structural_valid=not errors,
                                              manifest_bytes=_own_manifest_bytes(pack_root, manifest))
        except Exception as exc:  # noqa: BLE001 - the layers never decide validity
            layer_report = {"status": "not_evaluated", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "schema_version": SCHEMA_VERSION,
        "data_pack_id": manifest.get("id"),
        "valid": not errors,
        "layers": {
            "structural": {"status": "passed" if not errors else "failed", "decides_valid": True},
            **({"chronology": layer_report["chronology"], "plausibility": layer_report["plausibility"],
                "evidence": layer_report["evidence"]} if layer_report and "chronology" in layer_report
               else ({"not_evaluated": layer_report} if layer_report else {})),
        },
        "profile_eligibility": eligibility,
        "required_count": sum(bool(slot.get("required")) for slot in slot_by_role.values()),
        "valid_required_count": sum(
            bool(slot_by_role[row["role"]].get("required")) and row["status"] == "passed"
            for row in reports
        ),
        "errors": errors,
        "warnings": warnings,
        "bindings": reports,
        "summary": {
            "passed": sum(row["status"] == "passed" for row in reports),
            "failed": sum(row["status"] == "failed" for row in reports),
            "total": len(reports),
        },
    }
