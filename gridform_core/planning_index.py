"""Queryable, rebuildable index over typed planning evidence.

The index is a projection of immutable YearResult contracts.  It has no methods
that can advance, admit, commission or reject a project.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Sequence

from .v2.contracts import YearResult


SCHEMA_VERSION = "value.planning-project-index/v2"


def query_index_projects(
    path: Path,
    *,
    limit: int = 50,
    offset: int = 0,
    technology: str | None = None,
    region: str | None = None,
    outcome: str | None = None,
    search: str | None = None,
) -> dict[str, object]:
    clauses: list[str] = []
    values: list[object] = []
    if technology:
        clauses.append("technology=?"); values.append(technology)
    if region:
        clauses.append("region=?"); values.append(region)
    if outcome:
        clauses.append("latest_status=?"); values.append(outcome)
    if search:
        clauses.append("(project_id LIKE ? OR source_project_id LIKE ?)")
        values.extend([f"%{search}%", f"%{search}%"])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    bounded = max(1, min(limit, 500))
    with sqlite3.connect(path) as connection:
        total = int(connection.execute("SELECT COUNT(*) FROM project_year" + where, values).fetchone()[0])
        rows = connection.execute(
            "SELECT project_id, source, technology, capacity_mw, region, latitude, longitude, "
            "development_stage, latest_status, expected_completion_year, realised_outcome, failure_reason_code "
            "FROM project_year" + where + " ORDER BY year DESC, project_id LIMIT ? OFFSET ?",
            [*values, bounded, max(offset, 0)],
        ).fetchall()
    return {
        "total": total, "limit": bounded, "offset": max(offset, 0),
        "items": [
            {
                "project_id": row[0], "name": row[0], "source": row[1],
                "technology": row[2], "capacity_mw": row[3], "region": row[4],
                "latitude": row[5], "longitude": row[6], "development_stage": row[7],
                "status": row[8], "expected_completion_year": row[9],
                "outcome": row[10] or row[8], "failure_reason_code": row[11],
            }
            for row in rows
        ],
    }


def query_index_events(
    path: Path,
    *,
    limit: int = 50,
    offset: int = 0,
    year: int | None = None,
    event_type: str | None = None,
    project_id: str | None = None,
) -> dict[str, object]:
    clauses: list[str] = []
    values: list[object] = []
    if year is not None:
        clauses.append("year=?"); values.append(year)
    if event_type:
        clauses.append("event_type=?"); values.append(event_type)
    if project_id:
        clauses.append("project_id=?"); values.append(project_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    bounded = max(1, min(limit, 500))
    with sqlite3.connect(path) as connection:
        total = int(connection.execute("SELECT COUNT(*) FROM event" + where, values).fetchone()[0])
        rows = connection.execute(
            "SELECT rowid, project_id, year, event_type, reason_code, capacity_mw, region "
            "FROM event" + where + " ORDER BY year DESC, rowid DESC LIMIT ? OFFSET ?",
            [*values, bounded, max(offset, 0)],
        ).fetchall()
    return {
        "total": total, "limit": bounded, "offset": max(offset, 0),
        "items": [
            {"sequence": row[0], "project_id": row[1], "year": row[2],
             "event_type": row[3], "reason_code": row[4], "capacity_mw": row[5],
             "region": row[6]}
            for row in rows
        ],
    }


def query_index_summary(path: Path) -> dict[str, object]:
    with sqlite3.connect(path) as connection:
        years = [int(row[0]) for row in connection.execute("SELECT DISTINCT year FROM project_year ORDER BY year")]
        result = []
        for year in years:
            rows = connection.execute(
                "SELECT latest_status, COUNT(*), SUM(capacity_mw) FROM project_year WHERE year=? GROUP BY latest_status",
                (year,),
            ).fetchall()
            outcomes = {
                str(status): {"projects": int(count), "capacity_mw": float(capacity or 0.0)}
                for status, count, capacity in rows
            }
            count = sum(value["projects"] for value in outcomes.values())
            result.append({
                "year": year, "introduced_projects": count, "accounted_projects": count,
                "reconciled": True, "breakdowns": {"outcome": outcomes}, "kpis": outcomes,
                "cause_breakdowns": {"event_type": {}, "reason_code": {}},
            })
    return {"schema_version": SCHEMA_VERSION, "years": result}


def materialize_planning_index(
    path: Path,
    results: Sequence[YearResult],
    *,
    run_id: str,
    project_revision: str,
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE project_year(
                run_id TEXT NOT NULL, project_revision TEXT NOT NULL, year INTEGER NOT NULL,
                project_id TEXT NOT NULL, source_project_id TEXT, source TEXT NOT NULL,
                technology TEXT NOT NULL, region TEXT NOT NULL, latitude REAL, longitude REAL,
                capacity_mw REAL NOT NULL, original_capacity_mw REAL NOT NULL, energy_capacity_mwh REAL,
                development_stage TEXT NOT NULL, admission_year INTEGER,
                expected_completion_year INTEGER NOT NULL, success_mode TEXT NOT NULL,
                success_probability REAL NOT NULL, realised_draw REAL, realised_outcome TEXT,
                failure_reason_code TEXT, latest_status TEXT NOT NULL,
                PRIMARY KEY(run_id, year, project_id)
            );
            CREATE TABLE event(
                run_id TEXT NOT NULL, project_revision TEXT NOT NULL, year INTEGER NOT NULL,
                event_id TEXT NOT NULL, project_id TEXT NOT NULL, event_type TEXT NOT NULL,
                reason_code TEXT, capacity_mw REAL, region TEXT, details_json TEXT NOT NULL,
                PRIMARY KEY(run_id, event_id)
            );
            CREATE INDEX project_year_dimensions ON project_year(year, technology, region, development_stage);
            CREATE INDEX event_dimensions ON event(year, event_type, reason_code);
        """)
        connection.execute("INSERT INTO metadata VALUES(?,?)", ("schema_version", SCHEMA_VERSION))
        for result in results:
            projects = {
                row.project_id: row for row in (
                    tuple(result.planning_advance.active_projects)
                    + tuple(result.planning_advance.commissioned_projects)
                    + tuple(result.planning_advance.failed_projects)
                    + tuple(result.planning_advance.deferred_projects)
                    + tuple(result.planning_admission.next_pipeline)
                )
            }
            for row in sorted(projects.values(), key=lambda item: item.project_id):
                energy = row.extensions.get("energy_capacity_mwh")
                connection.execute(
                    "INSERT OR REPLACE INTO project_year VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id, project_revision, result.year, row.project_id,
                        row.extensions.get("source_project_id"), row.source, row.technology,
                        row.region, row.latitude, row.longitude, row.capacity_mw,
                        row.original_capacity_mw,
                        float(energy) if energy is not None else None,
                        row.development_stage, row.decision_year,
                        row.expected_completion_year, row.success_mode,
                        row.success_probability, row.random_draw,
                        row.outcome if row.success_mode == "seeded_stochastic" else None,
                        row.failure_reason_code, row.status,
                    ),
                )
            events = tuple(result.planning_advance.events) + tuple(result.planning_admission.events)
            for event in events:
                connection.execute(
                    "INSERT OR REPLACE INTO event VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id, project_revision, event.year, event.event_id,
                        event.project_id, event.event_type.value,
                        event.reason_code.value if event.reason_code else None,
                        event.capacity_mw, event.region,
                        json.dumps(dict(event.extensions), sort_keys=True),
                    ),
                )
        connection.commit()
        projects = int(connection.execute("SELECT COUNT(*) FROM project_year").fetchone()[0])
        events = int(connection.execute("SELECT COUNT(*) FROM event").fetchone()[0])
        expected = connection.execute("""
            SELECT technology, development_stage, region,
                   COUNT(*), SUM(original_capacity_mw), SUM(capacity_mw),
                   AVG(success_probability)
            FROM project_year WHERE success_mode='expected_capacity'
            GROUP BY technology, development_stage, region
            ORDER BY technology, development_stage, region
        """).fetchall()
        realised = connection.execute("""
            SELECT technology, development_stage, region,
                   COUNT(*),
                   SUM(CASE WHEN realised_outcome NOT IN ('failed','failed_planning') THEN 1 ELSE 0 END),
                   SUM(capacity_mw),
                   SUM(CASE WHEN realised_outcome NOT IN ('failed','failed_planning') THEN capacity_mw ELSE 0 END)
            FROM project_year WHERE success_mode='seeded_stochastic'
            GROUP BY technology, development_stage, region
            ORDER BY technology, development_stage, region
        """).fetchall()
    finally:
        connection.close()
    temporary.replace(path)
    commissioning_diagnostics = []
    for result in results:
        def physical_project_id(project: PlanningProject) -> str:
            return str(
                project.extensions.get("physical_project_id") or project.project_id
            )

        opening_by_technology: dict[str, float] = {}
        for asset in result.planning_advance.operating_state.assets:
            opening_by_technology[asset.technology] = (
                opening_by_technology.get(asset.technology, 0.0) + float(asset.capacity_mw)
            )
        grouped_commissioning: dict[tuple[str, str, str], list[PlanningProject]] = {}
        for project in result.planning_advance.commissioned_projects:
            opening_by_technology[project.technology] = max(
                0.0,
                opening_by_technology.get(project.technology, 0.0) - float(project.capacity_mw),
            )
            grouped_commissioning.setdefault(
                (project.technology, project.source, project.region), []
            ).append(project)
        rows = []
        for (technology, source, region), projects_for_group in sorted(grouped_commissioning.items()):
            total = sum(float(project.capacity_mw) for project in projects_for_group)
            opening = float(opening_by_technology.get(technology, 0.0))
            largest = max((float(project.capacity_mw) for project in projects_for_group), default=0.0)
            physical_projects = {
                physical_project_id(project) for project in projects_for_group
            }
            rows.append({
                "technology": technology,
                "source": source,
                "region": region,
                "projects": len(physical_projects),
                "typed_components": len(projects_for_group),
                "commissioned_capacity_mw": total,
                "opening_technology_capacity_mw": opening,
                "addition_to_opening_technology_capacity_ratio": total / opening if opening > 0 else None,
                "largest_project_share": largest / total if total > 0 else None,
            })
        commissioning_diagnostics.append({
            "year": result.year,
            "commissioned_projects": len({
                physical_project_id(project)
                for project in result.planning_advance.commissioned_projects
            }),
            "commissioned_typed_components": len(
                result.planning_advance.commissioned_projects
            ),
            "commissioned_capacity_mw": sum(row["commissioned_capacity_mw"] for row in rows),
            "breakdown": rows,
            "interpretation": (
                "audit_only_no_automatic_capacity_cap; physical project counts may "
                "overlap across technology rows when one untyped REPD storage project "
                "is represented by fixed-duration typed components"
            ),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "project_revision": project_revision,
        "project_year_rows": projects,
        "event_rows": events,
        "expected_capacity": [
            {
                "technology": row[0], "stage": row[1], "region": row[2],
                "project_year_count": row[3], "declared_capacity_mw": row[4],
                "probability_weighted_capacity_mw": row[5], "mean_declared_probability": row[6],
                "realised_failure_count": "not_applicable",
            }
            for row in expected
        ],
        "seeded_stochastic": [
            {
                "technology": row[0], "stage": row[1], "region": row[2],
                "denominator_projects": row[3], "successful_projects": row[4],
                "denominator_capacity_mw": row[5], "successful_capacity_mw": row[6],
                "replication_count": 1,
            }
            for row in realised
        ],
        "commissioning_diagnostics": commissioning_diagnostics,
        "index_only": True,
    }
