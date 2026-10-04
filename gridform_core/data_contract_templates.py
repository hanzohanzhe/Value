"""Small, non-scientific templates and bounded previews for declared data roles."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Mapping, Sequence


CSV_TEMPLATES: dict[str, tuple[tuple[str, ...], tuple[object, ...]]] = {
    "value.network.nodal-demand": (("period_id", "bus_id", "demand_mwh"), ("2025:0", "bus-1", 100.0)),
    "value.network.ac.reactive-demand": (("period_id", "bus_id", "reactive_demand_mvar"), ("2025:0", "bus-1", 20.0)),
    "value.network.ac.active-schedule": (("period_id", "asset_id", "active_schedule_mwh"), ("2025:0", "generator-1", 50.0)),
    "value.hydrology.site-catalogue": (("site_id", "technology_class", "bus_id", "capacity_mw", "turbine_efficiency", "conversion_mwh_per_water_unit", "source", "licence"), ("ror-1", "run_of_river", "bus-1", 10.0, 0.9, "", "source citation", "licence")),
    "value.hydrology.asset-site-map": (("asset_id", "site_id", "share"), ("hydro-asset-1", "ror-1", 1.0)),
    # The canonical hydrology adapter reads ``timestamp``.  Interval and
    # timezone are binding metadata supplied by the caller, not row fields.
    "value.hydrology.run-of-river-inflow": (("timestamp", "site_id", "value", "unit", "interval_hours", "timezone"), ("2025-01-01T00:00:00+00:00", "ror-1", 0.7, "p.u.", 0.5, "Europe/London")),
    "value.hydrology.reservoir-inflow": (("timestamp", "site_id", "value", "unit", "interval_hours", "timezone"), ("2025-01-01T00:00:00+00:00", "reservoir-1", 12.0, "water_unit/period", 0.5, "Europe/London")),
}

JSON_TEMPLATES: dict[str, object] = {
    "value.network.buses": {"buses": [{"bus_id": "bus-1", "voltage_kv": 400.0, "region": "GB", "reference_eligible": True, "is_reference": True, "base_mva": 100.0, "voltage_min_pu": 0.95, "voltage_max_pu": 1.05, "bus_type": "slack"}]},
    "value.network.branches": {"branches": [{"branch_id": "line-1", "from_bus": "bus-1", "to_bus": "bus-2", "branch_type": "ac_line", "in_service": True, "thermal_rating_mw": 1000.0, "reactance_pu": 0.1, "resistance_pu": 0.01, "charging_susceptance_pu": 0.0, "apparent_power_rating_mva": 1000.0, "circuits": 1}]},
    "value.network.asset-map": {"asset_mappings": [{"asset_id": "generator-1", "bus_id": "bus-1", "asset_class": "generator", "share": 1.0}]},
    "value.network.ac.generators": {"generator_specs": [{"asset_id": "generator-1", "active_min_mw": 0.0, "active_max_mw": 100.0, "reactive_min_mvar": -50.0, "reactive_max_mvar": 50.0, "voltage_setpoint_pu": 1.0, "slack_balancer": True}]},
    "value.network.ac.initial-voltage": {"initial_voltage": {"bus-1": {"magnitude_pu": 1.0, "angle_degrees": 0.0}}},
    "value.hydrology.reservoir-parameters": {"reservoirs": [{"site_id": "reservoir-1", "min_volume": 0.0, "max_volume": 1000.0, "initial_volume": 500.0, "terminal_volume": 500.0, "max_turbine_release_per_period": 10.0, "max_total_release_per_period": 12.0, "minimum_environmental_release_per_period": 1.0, "conversion_mwh_per_water_unit": 1.0, "turbine_efficiency": 0.9, "turbine_capacity_mw": 18.0, "information_structure": "perfect_foresight"}]},
    "value.network.expansion.candidates": {"candidates": [{"candidate_id": "corridor-1-build", "corridor_id": "corridor-1", "from_bus": "bus-1", "to_bus": "bus-2", "technology": "ac_line", "circuits_per_build": 1, "max_build_circuits": 2, "thermal_rating_mw_per_circuit": 1000.0, "apparent_power_rating_mva_per_circuit": 1000.0, "resistance_pu": 0.01, "reactance_pu": 0.1, "charging_susceptance_pu": 0.0, "tap_ratio": None, "phase_shift_degrees": 0.0, "owner_id": "regulated-owner", "planner_id": "system-planner", "total_capex_gbp_per_build": 500000000.0, "annual_fixed_opex_gbp_per_build": 5000000.0, "construction_life_years": 5.0, "economic_life_years": 40.0, "discount_rate": 0.05, "lead_time_years": 5, "success_probability": 0.8, "budget_group": "national-network", "trigger_branch_ids": ["line-1"], "trigger_branch_rating_mw": 1000.0, "minimum_trigger_utilisation": 0.9, "declared_annual_benefit_gbp": 75000000.0, "minimum_benefit_cost_ratio": 1.0, "earliest_decision_year": 2025, "embodied_carbon_factor_tco2e_per_mw": None, "embodied_carbon_source": {}, "provenance": {"source": "replace with cited candidate evidence"}}]},
}


# Accepted formats belong to manifests.  This map records what the shipped
# canonical runtime adapters can actually consume today; the UI exposes both.
RUNTIME_SUPPORTED_FORMATS: dict[str, tuple[str, ...]] = {
    "value.network.buses": ("json",),
    "value.network.branches": ("json",),
    "value.network.asset-map": ("json",),
    "value.network.nodal-demand": ("csv",),
    "value.network.ac.generators": ("json",),
    "value.network.ac.reactive-demand": ("csv",),
    "value.network.ac.active-schedule": ("csv",),
    "value.network.ac.initial-voltage": ("json",),
    "value.hydrology.site-catalogue": ("csv",),
    "value.hydrology.asset-site-map": ("csv",),
    "value.hydrology.run-of-river-inflow": ("csv",),
    "value.hydrology.reservoir-inflow": ("csv",),
    "value.hydrology.reservoir-parameters": ("json",),
    "value.network.expansion.candidates": ("json",),
}


def runtime_supported_formats(role: str, accepted_formats: Sequence[str]) -> tuple[str, ...]:
    """Return formats with a shipped parser, never a guessed browser mapping."""

    declared = RUNTIME_SUPPORTED_FORMATS.get(role)
    if declared is None:
        return tuple(str(item) for item in accepted_formats)
    return tuple(item for item in declared if item in accepted_formats)


def template_available(role: str) -> bool:
    return role in CSV_TEMPLATES or role in JSON_TEMPLATES


def template_for_role(role: str, formats: Sequence[str]) -> tuple[bytes, str, str]:
    if role in CSV_TEMPLATES and "csv" in formats:
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        header, example = CSV_TEMPLATES[role]
        writer.writerow(header)
        writer.writerow(example)
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", f"{role.replace('.', '-')}-template.csv"
    if role in JSON_TEMPLATES and "json" in formats:
        return (
            (json.dumps(JSON_TEMPLATES[role], indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
            "application/json; charset=utf-8",
            f"{role.replace('.', '-')}-template.json",
        )
    raise ValueError(f"No generated template is declared for {role}")


def _safe_binding_path(pack_root: Path, binding: Mapping[str, object]) -> Path:
    path = (pack_root / str(binding.get("uri") or "")).resolve()
    path.relative_to(pack_root.resolve())
    if not path.is_file():
        raise ValueError("The bound file is missing")
    return path


def preview_binding(
    pack_root: Path,
    manifest: Mapping[str, object],
    slot: Mapping[str, object],
    *,
    sample_rows: int = 200,
    maximum_json_bytes: int = 10 * 1024 * 1024,
) -> dict[str, object]:
    role = str(slot["role"])
    binding = dict(manifest.get("bindings") or {}).get(role)
    if not isinstance(binding, Mapping):
        return {"schema_version": "value.data-preview/v1", "role": role, "status": "not_bound"}
    path = _safe_binding_path(pack_root, binding)
    file_format = str(binding.get("format") or path.suffix.lstrip(".")).lower()
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest() if path.stat().st_size <= maximum_json_bytes else str(binding.get("sha256") or "")
    result: dict[str, object] = {
        "schema_version": "value.data-preview/v1", "role": role,
        "status": "bounded_preview", "format": file_format,
        "bytes": path.stat().st_size, "source_sha256": source_sha,
        "declared_sha256": binding.get("sha256"), "filename": binding.get("filename"),
        "unit": binding.get("unit") or slot.get("unit"),
        "definition": slot.get("label"), "capability": slot.get("capability"),
        "time_semantics": slot.get("time_semantics"),
        "sample_limit": sample_rows,
    }
    if file_format == "csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or ())
            rows = []
            identities: set[tuple[str, ...]] = set()
            duplicates = 0
            timestamp_first = None
            timestamp_last = None
            numeric: dict[str, list[float]] = {}
            for index, row in enumerate(reader):
                if index >= sample_rows:
                    break
                rows.append({key: row.get(key) for key in columns[:12]})
                timestamp = row.get("period_id") or row.get("timestamp")
                if timestamp:
                    timestamp_first = timestamp_first or timestamp
                    timestamp_last = timestamp
                identity = tuple(str(row.get(key) or "") for key in ("period_id", "bus_id", "site_id", "asset_id") if key in row)
                if identity:
                    duplicates += int(identity in identities)
                    identities.add(identity)
                for key, raw in row.items():
                    try:
                        value = float(raw or "")
                    except ValueError:
                        continue
                    if math.isfinite(value):
                        numeric.setdefault(str(key), []).append(value)
        result.update({
            "columns": columns, "sampled_rows": len(rows), "sample": rows[:5],
            "duplicate_sample_identities": duplicates,
            "timestamp_sample": {"first": timestamp_first, "last": timestamp_last},
            "numeric_ranges": {key: {"minimum": min(values), "maximum": max(values)} for key, values in numeric.items() if values},
        })
    elif file_format == "json":
        if path.stat().st_size > maximum_json_bytes:
            result.update({"status": "metadata_only", "reason": "JSON exceeds bounded preview limit"})
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                result["top_level_keys"] = sorted(str(key) for key in payload)
                arrays = {str(key): len(value) for key, value in payload.items() if isinstance(value, list)}
                result["array_counts"] = arrays
                result["sample"] = {
                    str(key): value[:3] for key, value in payload.items() if isinstance(value, list)
                }
            elif isinstance(payload, list):
                result.update({"array_counts": {"root": len(payload)}, "sample": payload[:3]})
            else:
                result["status"] = "invalid_root"
    else:
        result.update({"status": "metadata_only", "reason": "Use the canonical adapter during preflight for this format"})
    return result


def missing_input_checklist(
    slots: Sequence[Mapping[str, object]], manifest: Mapping[str, object]
) -> dict[str, object]:
    bindings = dict(manifest.get("bindings") or {})
    rows = [{
        "role": slot["role"], "label": slot["label"],
        "group": slot.get("group"), "source": slot.get("source", "base"),
        "capability": slot.get("capability"), "required": bool(slot.get("required")),
        "formats": list(slot.get("formats") or ()), "unit": slot.get("unit"),
        "status": "bound" if slot["role"] in bindings else "missing" if slot.get("required") else "optional_not_bound",
    } for slot in slots]
    return {
        "schema_version": "value.missing-input-checklist/v1",
        "data_pack_id": manifest.get("id"), "rows": rows,
        "missing_required": [row["role"] for row in rows if row["status"] == "missing"],
        "contains_private_data": False,
    }
