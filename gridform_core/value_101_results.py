"""Artifact-backed comparison for the bounded VALUE 101 teaching window."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Mapping

from .market_replay import query_vre_curtailment_summary
from .planning_index import query_index_events
from .results_summary import build_run_summary
from .value_101_lifecycle import is_value_101_record


EXPECTED_DIMENSIONS = {
    "baseline": [],
    "data": ["data_pack_id"],
    "storage": ["modules.storage_cost"],
}


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Required VALUE 101 artifact is unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Required VALUE 101 artifact is not a JSON object: {path}")
    return value


def _finite(value: object, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"VALUE 101 artifact field is not numeric: {field}") from exc
    if not math.isfinite(number):
        raise ValueError(f"VALUE 101 artifact field is not finite: {field}")
    return number


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _origin(status: Mapping[str, object], resolved: Mapping[str, object]) -> dict[str, object]:
    for record in (status, resolved):
        extensions = record.get("extensions")
        if isinstance(extensions, Mapping):
            origin = extensions.get("value_101")
            if isinstance(origin, Mapping):
                return dict(origin)
    return {}


def _resolved_input_identity(resolved: Mapping[str, object]) -> dict[str, object]:
    raw_modules = resolved.get("modules")
    modules: dict[str, object] = {}
    if isinstance(raw_modules, Mapping):
        for slot, selection in sorted(raw_modules.items(), key=lambda item: str(item[0])):
            if isinstance(selection, Mapping):
                modules[str(slot)] = selection.get("module_id") or selection.get("id")
            else:
                modules[str(slot)] = selection
    scientific = resolved.get("scientific_parameters")
    runtime = resolved.get("runtime_controls")
    return {
        "data_pack_id": resolved.get("data_pack_id"),
        "start_year": resolved.get("start_year"),
        "end_year": resolved.get("end_year"),
        "modules": modules,
        "scientific_parameters": dict(scientific) if isinstance(scientific, Mapping) else {},
        "runtime_controls": dict(runtime) if isinstance(runtime, Mapping) else {},
    }


def _changed_dimensions(reference: object, candidate: object, prefix: str = "") -> list[str]:
    if isinstance(reference, Mapping) and isinstance(candidate, Mapping):
        changed: list[str] = []
        for key in sorted(set(reference) | set(candidate), key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            changed.extend(
                _changed_dimensions(reference.get(key), candidate.get(key), path)
            )
        return changed
    return [] if reference == candidate else [prefix]


def _identity_sha256(identity: Mapping[str, object]) -> str:
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _market_totals(database: Path) -> dict[str, float | int]:
    vre = query_vre_curtailment_summary(database)
    years = vre.get("years")
    if not isinstance(years, list) or not years:
        raise ValueError("VALUE 101 market ledger has no VRE summary rows")
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(real_demand_mwh),0), "
            "COALESCE(SUM(blackout_mwh),0), COALESCE(SUM(storage_charge_mwh),0), "
            "COALESCE(SUM(storage_discharge_mwh),0) FROM period_summary"
        ).fetchone()
        if row is None:
            raise ValueError("VALUE 101 market ledger has no period summary")
        terminal = connection.execute(
            "SELECT COALESCE(SUM(state_of_charge_mwh),0) FROM storage_state "
            "WHERE year=(SELECT year FROM storage_state ORDER BY year DESC, period DESC LIMIT 1) "
            "AND period=(SELECT period FROM storage_state ORDER BY year DESC, period DESC LIMIT 1)"
        ).fetchone()
    return {
        "period_count": int(row[0]),
        "demand_mwh": float(row[1]),
        "blackout_mwh": float(row[2]),
        "storage_charge_mwh": float(row[3]),
        "storage_discharge_mwh": float(row[4]),
        "terminal_soc_mwh": float((terminal or (0.0,))[0]),
        "vre_available_mwh": sum(_finite(item.get("available_vre_mwh"), field="available_vre_mwh") for item in years if isinstance(item, Mapping)),
        "vre_accepted_mwh": sum(_finite(item.get("accepted_vre_mwh"), field="accepted_vre_mwh") for item in years if isinstance(item, Mapping)),
        "vre_unused_mwh": sum(_finite(item.get("neutral_unused_vre_mwh"), field="neutral_unused_vre_mwh") for item in years if isinstance(item, Mapping)),
    }


def _planning_events(database: Path) -> dict[str, int]:
    events = query_index_events(database, limit=500)
    counts = {"admitted": 0, "failed": 0, "commissioned": 0}
    for row in events.get("items", []):
        event_type = str(row.get("event_type") or "").lower()
        if "admit" in event_type:
            counts["admitted"] += 1
        if "fail" in event_type or "reject" in event_type:
            counts["failed"] += 1
        if "commission" in event_type:
            counts["commissioned"] += 1
    return counts


def _row(
    run_root: Path, *, expected_kind: str
) -> tuple[dict[str, object], list[str], dict[str, object]]:
    status = _read(run_root / "status.json")
    if status.get("status") not in {"completed", "archived"}:
        raise ValueError(f"VALUE 101 Run is not complete: {run_root.name}")
    if status.get("mode") != "tutorial":
        raise ValueError(f"VALUE 101 comparison accepts tutorial Runs only: {run_root.name}")
    output = run_root / "model-output"
    resolved = _read(output / "resolved-run.json")
    origin = _origin(status, resolved)
    identity_record = {"extensions": {"value_101": origin}}
    if not is_value_101_record(identity_record):
        raise ValueError(f"VALUE 101 origin metadata is invalid: {run_root.name}")
    variant_kind = str(origin.get("variant_kind") or "")
    if variant_kind != expected_kind:
        raise ValueError(
            f"Expected {expected_kind} VALUE 101 Run, found {variant_kind or 'unknown'}"
        )
    changed = [str(value) for value in origin.get("changed_dimensions", [])]
    resolved_identity = _resolved_input_identity(resolved)
    summary = build_run_summary(run_root)
    cost = _read(output / "ledgers" / "annual-cost-ledger.json")
    carbon = _read(output / "ledgers" / "annual-carbon-ledger.json")
    cost_years = cost.get("years")
    carbon_years = carbon.get("years")
    if not isinstance(cost_years, list) or not isinstance(carbon_years, list):
        raise ValueError("VALUE 101 annual ledger collections are invalid")
    if any(row.get("status") != "reconciled" for row in cost_years if isinstance(row, Mapping)):
        raise ValueError("VALUE 101 cost ledger is not reconciled")
    if any(row.get("status") != "reconciled" for row in carbon_years if isinstance(row, Mapping)):
        raise ValueError("VALUE 101 carbon ledger is not reconciled")
    system_cost = sum(_finite(row.get("cem_system_cost_gbp"), field="cem_system_cost_gbp") for row in cost_years if isinstance(row, Mapping))
    demand_served = sum(_finite(row.get("demand_served_mwh"), field="demand_served_mwh") for row in cost_years if isinstance(row, Mapping))
    operating = sum(
        _finite(line.get("amount_gbp"), field="operation.amount_gbp")
        for row in cost_years if isinstance(row, Mapping)
        for line in row.get("lines", []) if isinstance(line, Mapping)
        if str(line.get("id") or "").startswith("operation.")
    )
    total_carbon = sum(_finite(row.get("total_carbon_emissions_tco2e"), field="total_carbon_emissions_tco2e") for row in carbon_years if isinstance(row, Mapping))
    operational_carbon = sum(_finite(row.get("operational_emissions_tco2e"), field="operational_emissions_tco2e") for row in carbon_years if isinstance(row, Mapping))
    embodied_carbon = sum(_finite(row.get("embodied_lifecycle_emissions_tco2e"), field="embodied_lifecycle_emissions_tco2e") for row in carbon_years if isinstance(row, Mapping))
    carbon_denominator = sum(
        _finite((row.get("intensities") or {}).get("denominator_mwh"), field="carbon.denominator_mwh")
        for row in carbon_years if isinstance(row, Mapping) and isinstance(row.get("intensities"), Mapping)
    )
    market_path = output / "market" / "market.sqlite"
    planning_path = output / "planning" / "project-index.sqlite"
    market = _market_totals(market_path)
    run_id = str(status.get("id") or run_root.name)
    return ({
        "run_id": run_id,
        "project_id": status.get("project_id"),
        "project_revision_sha256": summary.get("run", {}).get("project_revision"),
        "variant_kind": variant_kind,
        "changed_dimension": changed[0] if len(changed) == 1 else None,
        "declared_changed_dimensions": changed,
        "resolved_input_identity_sha256": _identity_sha256(resolved_identity),
        "data_pack_id": resolved.get("data_pack_id") or status.get("data_pack_id"),
        "storage_cost_module_id": dict(summary.get("modules") or {}).get("storage_cost"),
        "annual_economics_eligible": False,
        "teaching_window_period_count": market["period_count"],
        "teaching_window_system_resource_cost_gbp": system_cost,
        "teaching_window_physical_operating_cost_gbp": operating,
        "teaching_window_cost_gbp_per_mwh_served": system_cost / demand_served if demand_served else None,
        "teaching_window_demand_served_mwh": demand_served,
        "teaching_window_total_carbon_emissions_tco2e": total_carbon,
        "teaching_window_operational_emissions_tco2e": operational_carbon,
        "teaching_window_embodied_lifecycle_emissions_tco2e": embodied_carbon,
        "teaching_window_operational_carbon_intensity_kgco2e_per_mwh": operational_carbon * 1000.0 / carbon_denominator if carbon_denominator else None,
        "teaching_window_overall_carbon_intensity_kgco2e_per_mwh": total_carbon * 1000.0 / carbon_denominator if carbon_denominator else None,
        "teaching_window_vre_available_mwh": market["vre_available_mwh"],
        "teaching_window_vre_accepted_mwh": market["vre_accepted_mwh"],
        "teaching_window_vre_unused_mwh": market["vre_unused_mwh"],
        "teaching_window_storage_charge_mwh": market["storage_charge_mwh"],
        "teaching_window_storage_discharge_mwh": market["storage_discharge_mwh"],
        "teaching_window_terminal_soc_mwh": market["terminal_soc_mwh"],
        "teaching_window_load_shedding_mwh": market["blackout_mwh"],
        "planning_events": _planning_events(planning_path),
        "detail_routes": {
            "market_replay": f"/api/runs/{run_id}/market/periods",
            "dispatch": f"/api/runs/{run_id}/market/dispatch?year=2025&resolution=half_hour",
            "storage_soc": f"/api/runs/{run_id}/market/storage",
            "vre_curtailment": f"/api/runs/{run_id}/market/vre-summary",
            "cost": f"/api/runs/{run_id}/artifacts/ledgers/annual-cost-ledger.json",
            "carbon": f"/api/runs/{run_id}/artifacts/ledgers/annual-carbon-ledger.json",
            "planning": f"/api/runs/{run_id}/planning/projects",
            "provenance": f"/api/runs/{run_id}/provenance",
            "raw_json": f"/api/runs/{run_id}/artifacts/resolved-run.json",
        },
        "source_artifacts": {
            "market_sha256": _sha256(market_path),
            "cost_sha256": _sha256(output / "ledgers" / "annual-cost-ledger.json"),
            "carbon_sha256": _sha256(output / "ledgers" / "annual-carbon-ledger.json"),
            "planning_sha256": _sha256(planning_path),
        },
    }, changed, resolved_identity)


def build_value_101_comparison(
    baseline_run: Path, data_run: Path, storage_run: Path
) -> dict[str, object]:
    """Build exactly three server-owned evidence rows in the approved order."""

    rows: list[dict[str, object]] = []
    resolved_identities: list[dict[str, object]] = []
    declarations: list[list[str]] = []
    violations: list[str] = []
    for run_root, kind in (
        (baseline_run, "baseline"),
        (data_run, "data"),
        (storage_run, "storage"),
    ):
        row, changed, resolved_identity = _row(Path(run_root), expected_kind=kind)
        rows.append(row)
        declarations.append(changed)
        resolved_identities.append(resolved_identity)
        if changed != EXPECTED_DIMENSIONS[kind]:
            violations.append(
                f"{kind} declares {changed}; expected {EXPECTED_DIMENSIONS[kind]}"
            )
    baseline_identity = resolved_identities[0]
    for index, kind in enumerate(("baseline", "data", "storage")):
        actual = (
            []
            if kind == "baseline"
            else _changed_dimensions(baseline_identity, resolved_identities[index])
        )
        rows[index]["actual_changed_dimensions"] = actual
        if actual != EXPECTED_DIMENSIONS[kind]:
            violations.append(
                f"{kind} actual changes are {actual}; expected {EXPECTED_DIMENSIONS[kind]}"
            )
        if declarations[index] != actual:
            violations.append(
                f"{kind} declaration {declarations[index]} does not match actual {actual}"
            )
    controlled = not violations
    return {
        "schema_version": "value.101-comparison/v1",
        "scope": "teaching_window",
        "annual_economics_eligible": False,
        "rows": rows,
        "comparison_gate": {
            "status": "controlled" if controlled else "refused",
            "controlled_interpretation_allowed": controlled,
            "violations": violations,
            "expected_dimensions": EXPECTED_DIMENSIONS,
        },
        "warning": (
            "Short synthetic teaching-window totals; not annual British evidence."
        ),
    }
