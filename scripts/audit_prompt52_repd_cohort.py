"""Audit a VALUE expected-capacity commissioning cohort against local REPD inputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]


def _year(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern).year
        except ValueError:
            pass
    match = re.search(r"(?:19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def _float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _rows(path: Path) -> tuple[list[dict[str, str]], str]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with path.open("r", encoding=encoding, newline="") as stream:
                return list(csv.DictReader(stream)), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", b"", 0, 1, f"Unsupported CSV encoding: {path}")


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _aggregate(rows: Iterable[dict[str, Any]], field: str) -> list[dict[str, object]]:
    values: dict[str, dict[str, float]] = defaultdict(lambda: {"rows": 0.0, "declared_mw": 0.0, "effective_mw": 0.0})
    for row in rows:
        label = str(row.get(field) or "missing")
        values[label]["rows"] += 1
        values[label]["declared_mw"] += _float(row.get("original_capacity_mw"))
        values[label]["effective_mw"] += _float(row.get("capacity_mw"))
    return [
        {
            field: label,
            "rows": int(value["rows"]),
            "declared_mw": value["declared_mw"],
            "effective_mw": value["effective_mw"],
        }
        for label, value in sorted(values.items())
    ]


def audit(
    checkpoint: Path,
    normalized_path: Path,
    raw_path: Path,
    planning_summary_path: Path,
    year: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    checkpoint_payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    projects = list(checkpoint_payload["state"]["planning_projects"])
    due = [
        dict(project)
        for project in projects
        if int(project.get("expected_completion_year", -1)) == year
        and str(project.get("status")) == "active"
        and str(project.get("outcome")) == "active"
    ]

    normalized, normalized_encoding = _rows(normalized_path)
    raw, raw_encoding = _rows(raw_path)
    normalized_id_counts = Counter(str(row.get("project_id") or "") for row in normalized)
    raw_id_counts = Counter(str(row.get("Ref ID") or "") for row in raw)
    normalized_by_id = {str(row.get("project_id") or ""): row for row in normalized}
    raw_by_id = {str(row.get("Ref ID") or ""): row for row in raw}

    detailed: list[dict[str, object]] = []
    maximum_probability_residual = 0.0
    maximum_duration_residual = 0.0
    maximum_capex_residual = 0.0
    for project in due:
        extensions = dict(project.get("extensions") or {})
        component_id = str(project["project_id"])
        project_id = str(extensions.get("physical_project_id") or component_id)
        normal = normalized_by_id.get(project_id, {})
        raw_row = raw_by_id.get(project_id, {})
        decision_year = int(project.get("decision_year", year - 1))
        operational_year = _year(normal.get("operational"))
        construction_year = _year(normal.get("under_construction"))
        if operational_year is not None and operational_year > decision_year:
            completion_basis = "source_future_operational_date"
        elif construction_year is not None and construction_year > decision_year:
            completion_basis = "source_future_under_construction_date"
        else:
            completion_basis = "model_timeline_plus_deterministic_spread"
        declared = _float(project.get("original_capacity_mw"))
        probability = _float(project.get("success_probability"))
        effective = _float(project.get("capacity_mw"))
        expected = declared * probability
        residual = effective - expected
        maximum_probability_residual = max(maximum_probability_residual, abs(residual))
        duration = extensions.get("declared_duration_hours")
        energy = extensions.get("energy_capacity_mwh")
        duration_residual = (
            _float(energy) - effective * _float(duration)
            if duration is not None and energy is not None else 0.0
        )
        expected_capex = (
            effective * _float(extensions.get("capital_cost_per_mw"))
            + _float(energy) * _float(extensions.get("capital_cost_per_mwh"))
        )
        capex_residual = _float(extensions.get("total_capex_gbp")) - expected_capex
        maximum_duration_residual = max(maximum_duration_residual, abs(duration_residual))
        maximum_capex_residual = max(maximum_capex_residual, abs(capex_residual))
        detailed.append({
            "component_id": component_id,
            "project_id": project_id,
            "site_name": project.get("name"),
            "model_technology": project.get("technology"),
            "normalized_technology": normal.get("technology"),
            "technology_source": normal.get("technology_source"),
            "raw_technology_type": raw_row.get("Technology Type"),
            "raw_storage_type": raw_row.get("Storage Type"),
            "region": project.get("region"),
            "development_status": normal.get("development_status"),
            "source_operational_year": operational_year,
            "source_under_construction_year": construction_year,
            "model_completion_year": year,
            "completion_basis": completion_basis,
            "success_mode": project.get("success_mode"),
            "success_probability": probability,
            "original_capacity_mw": declared,
            "capacity_mw": effective,
            "probability_identity_residual_mw": residual,
            "battery_assignment_method": extensions.get("repd_battery_assignment_method"),
            "declared_duration_hours": duration,
            "energy_capacity_mwh": energy,
            "duration_identity_residual_mwh": duration_residual,
            "expected_economics_capacity_mw": extensions.get("expected_economics_capacity_mw"),
            "total_capex_gbp": extensions.get("total_capex_gbp"),
            "capex_identity_residual_gbp": capex_residual,
            "reapplication_new_ref": raw_row.get("Are they re-applying (New REPD Ref)"),
            "reapplication_old_ref": raw_row.get("Are they re-applying (Old REPD Ref) "),
            "normalized_joined": bool(normal),
            "raw_joined": bool(raw_row),
        })

    physical_rows: dict[str, dict[str, object]] = {}
    for row in detailed:
        physical_id = str(row["project_id"])
        if physical_id not in physical_rows:
            physical_rows[physical_id] = {
                **dict(row),
                "original_capacity_mw": 0.0,
                "capacity_mw": 0.0,
            }
        physical = physical_rows[physical_id]
        physical["original_capacity_mw"] = _float(physical["original_capacity_mw"]) + _float(row["original_capacity_mw"])
        physical["capacity_mw"] = _float(physical["capacity_mw"]) + _float(row["capacity_mw"])
    duplicate_key_groups: dict[tuple[str, str, str, float], list[str]] = defaultdict(list)
    for row in physical_rows.values():
        duplicate_key = (
            _key(row["site_name"]),
            _key(row["technology_source"]),
            _key(row["region"]),
            round(_float(row["original_capacity_mw"]), 3),
        )
        duplicate_key_groups[duplicate_key].append(str(row["project_id"]))
    probable_duplicates = [
        {"key": list(key), "project_ids": ids}
        for key, ids in sorted(duplicate_key_groups.items())
        if key[0] and len(ids) > 1
    ]

    summary = json.loads(planning_summary_path.read_text(encoding="utf-8"))
    commissioning = next(
        row for row in summary["commissioning_diagnostics"] if int(row["year"]) == year
    )
    due_capacity = sum(_float(row["capacity_mw"]) for row in detailed)
    declared_capacity = sum(_float(row["original_capacity_mw"]) for row in detailed)
    missing_normalized = sum(not bool(row["normalized_joined"]) for row in detailed)
    missing_raw = sum(not bool(row["raw_joined"]) for row in detailed)
    duplicate_normalized_ids = sorted(
        project_id for project_id, count in normalized_id_counts.items() if project_id and count > 1
    )
    duplicate_raw_ids = sorted(
        project_id for project_id, count in raw_id_counts.items() if project_id and count > 1
    )
    reapplications = [
        row for row in physical_rows.values()
        if str(row["reapplication_new_ref"] or "").strip()
        or str(row["reapplication_old_ref"] or "").strip()
    ]
    battery = [
        row for row in detailed
        if row["model_technology"] in {
            "1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"
        }
        and row.get("normalized_technology") == "battery"
    ]
    physical_battery_rows = {
        str(row["project_id"]): row for row in battery
    }
    battery_storage_type_counts = Counter(
        str(row["raw_storage_type"] or "missing")
        for row in physical_battery_rows.values()
    )
    battery_assignment_counts = Counter(str(row["battery_assignment_method"] or "missing") for row in battery)
    modes = Counter(str(row["success_mode"]) for row in detailed)
    superseded_ids = {
        str(row.get("Ref ID") or "").strip()
        for row in raw
        if str(row.get("Are they re-applying (New REPD Ref)") or "").strip()
        and str(row.get("Are they re-applying (New REPD Ref)") or "").strip()
        != str(row.get("Ref ID") or "").strip()
        and str(row.get("Are they re-applying (New REPD Ref)") or "").strip() in raw_by_id
    }
    active_physical_ids = {
        str(dict(project.get("extensions") or {}).get("physical_project_id") or project["project_id"])
        for project in projects
        if str(project.get("status")) == "active"
        and str(project.get("outcome")) == "active"
    }
    active_superseded_ids = sorted(superseded_ids & active_physical_ids)
    structural_errors: list[str] = []
    if missing_normalized:
        structural_errors.append(f"{missing_normalized} cohort rows do not join to projects.repd")
    if missing_raw:
        structural_errors.append(f"{missing_raw} cohort rows do not join to source.repd_raw")
    if duplicate_normalized_ids:
        structural_errors.append("projects.repd contains duplicate project_id values")
    if maximum_probability_residual > 1e-8:
        structural_errors.append("effective capacity does not equal declared capacity times probability")
    if maximum_duration_residual > 1e-8:
        structural_errors.append("typed storage energy does not equal effective power times duration")
    if maximum_capex_residual > 1e-5:
        structural_errors.append("expected CAPEX does not reconcile to effective MW/MWh")
    if active_superseded_ids:
        structural_errors.append("superseded REPD applications remain in the active pipeline")
    if int(commissioning["commissioned_projects"]) != len(physical_rows):
        structural_errors.append("checkpoint cohort row count does not match commissioning diagnostics")
    if int(commissioning.get("commissioned_typed_components", len(detailed))) != len(detailed):
        structural_errors.append("checkpoint typed component count does not match commissioning diagnostics")
    if not math.isclose(
        _float(commissioning["commissioned_capacity_mw"]), due_capacity,
        rel_tol=0.0, abs_tol=1e-8,
    ):
        structural_errors.append("checkpoint cohort MW does not match commissioning diagnostics")

    scientific_flags: list[dict[str, object]] = []
    if battery:
        assignment_is_declared = set(battery_assignment_counts) == {
            "scheme_c_proportional_four_technology_split"
        }
        scientific_flags.append({
            "id": "battery_duration_mapping",
            "severity": "report_assumption" if assignment_is_declared else "block_ten_year_baseline",
            "finding": (
                "Generic REPD Battery rows have no project-level duration. They are represented "
                "by fixed-duration typed components using the declared retained VALUE "
                "proportional assignment. This is a model assumption, not source-observed duration."
            ),
            "physical_projects": len({str(row["project_id"]) for row in battery}),
            "typed_components": len(battery),
            "declared_mw": sum(_float(row["original_capacity_mw"]) for row in battery),
            "effective_mw": sum(_float(row["capacity_mw"]) for row in battery),
            "raw_storage_type_counts": dict(sorted(battery_storage_type_counts.items())),
            "assignment_method_counts": dict(sorted(battery_assignment_counts.items())),
        })
    if probable_duplicates:
        scientific_flags.append({
            "id": "probable_duplicate_projects",
            "severity": "review_before_ten_year",
            "groups": len(probable_duplicates),
            "finding": "Different Ref IDs share normalised site, technology, region and declared MW.",
        })
    if active_superseded_ids:
        scientific_flags.append({
            "id": "active_superseded_repd_applications",
            "severity": "block_ten_year_baseline",
            "rows": len(active_superseded_ids),
            "finding": "Older REPD applications with an extant replacement remain active.",
        })
    timeline_assigned = sum(
        row["completion_basis"] == "model_timeline_plus_deterministic_spread" for row in physical_rows.values()
    )
    if timeline_assigned:
        scientific_flags.append({
            "id": "model_assigned_completion_year",
            "severity": "report_assumption",
            "rows": timeline_assigned,
            "finding": "The 2026 completion year is model-derived for these rows, not a source completion date.",
        })

    report = {
        "schema_version": "value.prompt52-repd-cohort-audit/v1",
        "year": year,
        "inputs": {
            "checkpoint": str(checkpoint),
            "projects_repd": str(normalized_path),
            "source_repd_raw": str(raw_path),
            "planning_summary": str(planning_summary_path),
            "projects_repd_encoding": normalized_encoding,
            "source_repd_raw_encoding": raw_encoding,
        },
        "semantics": {
            "success_mode_counts": dict(sorted(modes.items())),
            "row_count_meaning": (
                "Expected-capacity project-equivalent rows, not realised successful-project counts"
                if set(modes) == {"expected_capacity"}
                else "Mixed or realised planning modes; inspect rows"
            ),
            "capacity_identity": "effective_capacity_mw = original_capacity_mw * success_probability",
        },
        "cohort": {
            "physical_projects": len(physical_rows),
            "typed_components": len(detailed),
            "declared_capacity_mw": declared_capacity,
            "effective_capacity_mw": due_capacity,
            "effective_to_declared_fraction": due_capacity / declared_capacity if declared_capacity else None,
            "maximum_probability_identity_residual_mw": maximum_probability_residual,
            "maximum_duration_identity_residual_mwh": maximum_duration_residual,
            "maximum_capex_identity_residual_gbp": maximum_capex_residual,
            "by_model_technology": _aggregate(detailed, "model_technology"),
            "by_development_status": _aggregate(detailed, "development_status"),
            "by_completion_basis": _aggregate(detailed, "completion_basis"),
            "by_region": _aggregate(detailed, "region"),
        },
        "lineage": {
            "missing_normalized_rows": missing_normalized,
            "missing_raw_rows": missing_raw,
            "duplicate_normalized_project_ids": duplicate_normalized_ids,
            "duplicate_raw_ref_ids": duplicate_raw_ids,
            "probable_duplicate_groups_in_cohort": probable_duplicates,
            "reapplication_rows_in_cohort": [row["project_id"] for row in reapplications],
            "active_superseded_repd_ids": active_superseded_ids,
        },
        "commissioning_diagnostic_reconciliation": {
            "reported_rows": int(commissioning["commissioned_projects"]),
            "reported_typed_components": int(commissioning.get("commissioned_typed_components", commissioning["commissioned_projects"])),
            "reported_effective_capacity_mw": _float(commissioning["commissioned_capacity_mw"]),
            "row_count_matches": int(commissioning["commissioned_projects"]) == len(physical_rows),
            "typed_component_count_matches": int(commissioning.get("commissioned_typed_components", len(detailed))) == len(detailed),
            "capacity_matches": math.isclose(
                _float(commissioning["commissioned_capacity_mw"]), due_capacity,
                rel_tol=0.0, abs_tol=1e-8,
            ),
        },
        "structural_gate": {
            "status": "passed" if not structural_errors else "failed",
            "errors": structural_errors,
        },
        "scientific_gate": {
            "status": "review_required" if scientific_flags else "passed",
            "flags": scientific_flags,
            "ten_year_baseline_allowed": not any(
                row["severity"] == "block_ten_year_baseline" for row in scientific_flags
            ),
        },
    }
    return report, detailed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--planning-summary", type=Path, required=True)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.pack / "manifest.json").read_text(encoding="utf-8"))
    bindings = manifest["bindings"]
    normalized = args.pack / bindings["projects.repd"]["uri"]
    raw = args.pack / bindings["source.repd_raw"]["uri"]
    report, detail = audit(
        args.checkpoint, normalized, raw, args.planning_summary, args.year
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(detail[0]) if detail else ["project_id"])
        writer.writeheader()
        writer.writerows(detail)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["structural_gate"]["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
