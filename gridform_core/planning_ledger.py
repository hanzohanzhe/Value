"""SQLite planning lifecycle ledger shared by VALUE adapters and the API."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .v2.contracts import PlanningEventType, PlanningReasonCode


SCHEMA_VERSION = "value.planning-ledger/v1"
TERMINAL_EVENTS = {
    PlanningEventType.EXCLUDED_EXISTING_STOCK.value,
    PlanningEventType.FILTERED_STATUS_ZOMBIE.value,
    PlanningEventType.FILTERED_SCHEDULE_ZOMBIE.value,
    PlanningEventType.FILTERED_BELOW_MINIMUM_SIZE.value,
    PlanningEventType.FILTERED_OUTSIDE_HORIZON.value,
    PlanningEventType.FILTERED_ELIGIBILITY.value,
    PlanningEventType.FAILED_PLANNING.value,
    PlanningEventType.COMMISSIONED.value,
    PlanningEventType.DEPLETED_OR_RETIRED.value,
    PlanningEventType.OUTSIDE_SCOPE.value,
}
INTRODUCTION_EVENTS = {
    PlanningEventType.SOURCE_IMPORTED.value,
    PlanningEventType.ADMITTED_MODEL_INVESTMENT.value,
}


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower()).strip("-")


def normalize_stage(value: object) -> str:
    text = _slug(value).replace("-", "_")
    aliases = {
        "application_submitted": "application_submitted",
        "awaiting_construction": "pre_construction",
        "under_construction": "construction",
        "operational": "operational",
        "depletion": "retirement",
    }
    return aliases.get(text, text or "unknown")


def normalize_status(value: object) -> str:
    text = _slug(value).replace("-", "_")
    aliases = {
        "failed_due_to_success_rate": "failed_planning",
        "success_expected_capacity": "active_expected",
    }
    return aliases.get(text, text or "active")


def ensure_project_id(project: dict, *, scenario: str = "") -> str:
    existing = str(project.get("project_id") or "").strip()
    if existing:
        return existing
    source = str(project.get("source") or "external").lower()
    source_identifier = next(
        (
            project.get(key)
            for key in (
                "repd_id", "reference", "reference_id", "ref_id", "REPD ID",
                "site_reference", "project_reference",
            )
            if project.get(key)
        ),
        None,
    )
    if source == "external" and source_identifier:
        project_id = f"repd:{_slug(source_identifier)}"
    else:
        fingerprint = "|".join(
            str(item)
            for item in (
                source,
                scenario,
                project.get("decision_year", ""),
                project.get("target_asset_name", project.get("assigned_generator", "")),
                project.get("name", ""),
                project.get("technology_type", project.get("technology", "")),
                project.get("original_capacity", project.get("capacity", "")),
                project.get("region", ""),
                project.get("completion_year", ""),
                project.get("source_row_number", ""),
            )
        )
        prefix = "model" if source == "model" else "repd"
        project_id = f"{prefix}:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:24]}"
    project["project_id"] = project_id
    return project_id


def _capacity(project: Mapping[str, object]) -> float:
    return float(project.get("capacity_mw", project.get("capacity", 0.0)) or 0.0)


def _original_capacity(project: Mapping[str, object]) -> float:
    return float(project.get("original_capacity", _capacity(project)) or 0.0)


def _coordinates(project: Mapping[str, object]) -> tuple[float | None, float | None]:
    location = project.get("location") if isinstance(project.get("location"), Mapping) else {}
    latitude = project.get("latitude", location.get("lat"))  # type: ignore[union-attr]
    longitude = project.get("longitude", location.get("lon"))  # type: ignore[union-attr]
    return (
        float(latitude) if latitude not in (None, "") else None,
        float(longitude) if longitude not in (None, "") else None,
    )


class PlanningLedger:
    def __init__(self, planning_dir: Path, *, batch_size: int = 500) -> None:
        self.planning_dir = planning_dir
        self.planning_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.planning_dir / "pipeline.sqlite"
        self.summary_path = self.planning_dir / "summary.json"
        self.batch_size = max(1, int(batch_size))
        self._sequence = 0
        self._project_rows: list[tuple] = []
        self._event_rows: list[tuple] = []
        self._connection = sqlite3.connect(self.path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._create_schema()
        self._sequence = int(
            self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM events"
            ).fetchone()[0]
        )

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                technology TEXT NOT NULL,
                capacity_mw REAL NOT NULL,
                original_capacity_mw REAL NOT NULL,
                region TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                development_stage TEXT NOT NULL,
                status TEXT NOT NULL,
                decision_year INTEGER,
                expected_completion_year INTEGER,
                success_mode TEXT,
                success_probability REAL,
                random_draw REAL,
                outcome TEXT NOT NULL,
                failure_reason_code TEXT,
                assigned_asset_id TEXT,
                raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER NOT NULL,
                event_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                year INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                reason_code TEXT,
                from_stage TEXT,
                to_stage TEXT,
                capacity_mw REAL,
                region TEXT,
                details_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_year_type ON events(year, event_type);
            CREATE INDEX IF NOT EXISTS events_project ON events(project_id, sequence);
            CREATE TABLE IF NOT EXISTS annual_summary (
                year INTEGER NOT NULL,
                dimension TEXT NOT NULL,
                value TEXT NOT NULL,
                expected_completion_year INTEGER,
                project_count INTEGER NOT NULL,
                capacity_mw REAL NOT NULL,
                PRIMARY KEY(year, dimension, value, expected_completion_year)
            );
            """
        )
        self._connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self._connection.commit()

    def _project_row(
        self,
        project: dict,
        *,
        outcome: str | None = None,
        failure_reason: PlanningReasonCode | None = None,
        assigned_asset_id: str | None = None,
    ) -> tuple:
        scenario = os.getenv("DECARB_V2_SCENARIO", os.getenv("DECARB_SCENARIO", ""))
        project_id = ensure_project_id(project, scenario=scenario)
        latitude, longitude = _coordinates(project)
        source = "model_investment" if project.get("source") == "model" else "external_repd"
        technology = str(project.get("technology", project.get("technology_type", "unknown")))
        status = normalize_status(project.get("status", "active"))
        resolved_outcome = outcome or ("failed_planning" if status == "failed_planning" else "active")
        return (
            project_id,
            str(project.get("name") or project_id),
            source,
            technology,
            _capacity(project),
            _original_capacity(project),
            str(project.get("region") or "Unknown"),
            latitude,
            longitude,
            normalize_stage(project.get("development_stage", project.get("development_status"))),
            status,
            int(project["decision_year"]) if project.get("decision_year") is not None else None,
            int(project["completion_year"]) if project.get("completion_year") is not None else None,
            str(project.get("success_mode")) if project.get("success_mode") is not None else None,
            float(project["success_rate"]) if project.get("success_rate") is not None else None,
            float(project["random_draw"]) if project.get("random_draw") is not None else None,
            resolved_outcome,
            failure_reason.value if failure_reason else None,
            assigned_asset_id or project.get("assigned_generator") or project.get("target_asset_name"),
            json.dumps(project, sort_keys=True, ensure_ascii=False, default=str),
        )

    def upsert_project(
        self,
        project: dict,
        *,
        outcome: str | None = None,
        failure_reason: PlanningReasonCode | None = None,
        assigned_asset_id: str | None = None,
    ) -> str:
        row = self._project_row(
            project,
            outcome=outcome,
            failure_reason=failure_reason,
            assigned_asset_id=assigned_asset_id,
        )
        self._project_rows.append(row)
        if len(self._project_rows) >= self.batch_size:
            self.flush()
        return str(row[0])

    def record_event(
        self,
        project: dict,
        *,
        year: int,
        event_type: PlanningEventType,
        reason_code: PlanningReasonCode | None = None,
        from_stage: str | None = None,
        to_stage: str | None = None,
        details: Mapping[str, object] | None = None,
        outcome: str | None = None,
        assigned_asset_id: str | None = None,
    ) -> str:
        project_id = self.upsert_project(
            project,
            outcome=outcome,
            failure_reason=reason_code if outcome in {"failed_planning", "filtered", "outside_scope"} else None,
            assigned_asset_id=assigned_asset_id,
        )
        self._sequence += 1
        fingerprint = f"{project_id}|{year}|{event_type.value}|{reason_code}|{self._sequence}"
        event_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]
        self._event_rows.append((
            self._sequence,
            event_id,
            project_id,
            int(year),
            event_type.value,
            reason_code.value if reason_code else None,
            normalize_stage(from_stage) if from_stage else None,
            normalize_stage(to_stage) if to_stage else None,
            _capacity(project),
            str(project.get("region") or "Unknown"),
            json.dumps(dict(details or {}), sort_keys=True, ensure_ascii=False, default=str),
        ))
        if len(self._event_rows) >= self.batch_size:
            self.flush()
        return event_id

    def record_imports(self, projects: Sequence[dict], *, year: int) -> None:
        for project in projects:
            self.record_event(
                project, year=year, event_type=PlanningEventType.SOURCE_IMPORTED,
                reason_code=PlanningReasonCode.SOURCE_REPD,
            )
            self.record_event(
                project, year=year, event_type=PlanningEventType.ADMITTED_EXTERNAL,
                reason_code=PlanningReasonCode.SOURCE_REPD,
            )

    def record_source_import(self, project: dict, *, year: int) -> None:
        self.record_event(
            project,
            year=year,
            event_type=PlanningEventType.SOURCE_IMPORTED,
            reason_code=PlanningReasonCode.SOURCE_REPD,
        )

    def record_source_filter(
        self,
        project: dict,
        *,
        year: int,
        event_type: PlanningEventType,
        reason_code: PlanningReasonCode,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.record_event(
            project,
            year=year,
            event_type=event_type,
            reason_code=reason_code,
            details=details,
            outcome="filtered",
        )

    def record_external_admission(self, project: dict, *, year: int) -> None:
        self.record_event(
            project,
            year=year,
            event_type=PlanningEventType.ADMITTED_EXTERNAL,
            reason_code=PlanningReasonCode.SOURCE_REPD,
        )

    def record_removed(
        self,
        before: Sequence[dict],
        after: Sequence[dict],
        *,
        year: int,
        event_type: PlanningEventType,
        reason_code: PlanningReasonCode,
        outcome: str,
    ) -> None:
        after_ids = {ensure_project_id(project) for project in after}
        for project in before:
            if ensure_project_id(project) not in after_ids:
                self.record_event(
                    project, year=year, event_type=event_type,
                    reason_code=reason_code, outcome=outcome,
                )

    def record_deferred(self, before: Sequence[dict], after: Sequence[dict], *, year: int) -> None:
        before_year = {
            ensure_project_id(project): project.get("completion_year") for project in before
        }
        for project in after:
            project_id = ensure_project_id(project)
            old = before_year.get(project_id)
            new = project.get("completion_year")
            if old is not None and new != old:
                self.record_event(
                    project, year=year, event_type=PlanningEventType.DEFERRED,
                    reason_code=PlanningReasonCode.START_YEAR_STOCK_DEFERMENT,
                    details={"old_completion_year": old, "new_completion_year": new},
                )

    def record_success_evaluations(self, projects: Sequence[dict], *, year: int) -> None:
        for project in projects:
            if not project.get("success_rate_applied"):
                continue
            mode = str(project.get("success_mode") or "expected")
            reason = (
                PlanningReasonCode.SEEDED_STOCHASTIC
                if mode == "stochastic"
                else PlanningReasonCode.EXPECTED_CAPACITY
            )
            self.record_event(
                project, year=year, event_type=PlanningEventType.SUCCESS_EVALUATED,
                reason_code=reason,
                details={
                    "success_probability": project.get("success_rate"),
                    "random_draw": project.get("random_draw"),
                    "success_mode": mode,
                    "project_succeeds": project.get("project_succeeds"),
                },
            )
            if project.get("project_succeeds") is False:
                self.record_event(
                    project, year=year, event_type=PlanningEventType.FAILED_PLANNING,
                    reason_code=PlanningReasonCode.SUCCESS_PROBABILITY,
                    outcome="failed_planning",
                )

    def record_allocations(self, projects: Sequence[dict], *, year: int) -> None:
        for project in projects:
            assigned = project.get("assigned_generator") or project.get("target_asset_name")
            if assigned:
                self.record_event(
                    project, year=year, event_type=PlanningEventType.ALLOCATION_ASSIGNED,
                    reason_code=PlanningReasonCode.LOCATION_MATCH,
                    assigned_asset_id=str(assigned),
                )

    def record_model_admissions(self, projects: Sequence[dict], *, year: int) -> None:
        for project in projects:
            self.record_event(
                project, year=year, event_type=PlanningEventType.ADMITTED_MODEL_INVESTMENT,
                reason_code=PlanningReasonCode.SOURCE_MODEL_INVESTMENT,
            )
        self.record_success_evaluations(projects, year=year)

    def remove_project(
        self,
        pipeline: list,
        project: dict,
        *,
        year: int,
        event_type: PlanningEventType,
        reason_code: PlanningReasonCode,
        outcome: str,
        assigned_asset_id: str | None = None,
    ) -> None:
        self.record_event(
            project,
            year=year,
            event_type=event_type,
            reason_code=reason_code,
            outcome=outcome,
            assigned_asset_id=assigned_asset_id,
        )
        pipeline.remove(project)

    def flush(self) -> None:
        if self._project_rows:
            self._connection.executemany(
                """
                INSERT OR REPLACE INTO projects (
                    project_id, name, source, technology, capacity_mw,
                    original_capacity_mw, region, latitude, longitude,
                    development_stage, status, decision_year,
                    expected_completion_year, success_mode,
                    success_probability, random_draw, outcome,
                    failure_reason_code, assigned_asset_id, raw_json
                ) VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                self._project_rows,
            )
            self._project_rows.clear()
        if self._event_rows:
            self._connection.executemany(
                "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                self._event_rows,
            )
            self._event_rows.clear()
        self._connection.commit()

    def complete_year(self, year: int, active_pipeline: Sequence[dict]) -> dict[str, object]:
        active_ids = set()
        for project in active_pipeline:
            active_ids.add(self.upsert_project(project))
        self.flush()
        introduced = {
            row[0]
            for row in self._connection.execute(
                "SELECT DISTINCT project_id FROM events WHERE year <= ? AND event_type IN (?, ?)",
                (year, *sorted(INTRODUCTION_EVENTS)),
            )
        }
        last_terminal = {
            row[0]: row[1]
            for row in self._connection.execute(
                f"""
                SELECT e.project_id, e.event_type FROM events e
                JOIN (
                    SELECT project_id, MAX(sequence) AS sequence FROM events
                    WHERE year <= ? AND event_type IN ({','.join('?' for _ in TERMINAL_EVENTS)})
                    GROUP BY project_id
                ) last ON last.project_id=e.project_id AND last.sequence=e.sequence
                """,
                (year, *sorted(TERMINAL_EVENTS)),
            )
        }
        classified: dict[str, str] = {}
        for project_id in introduced:
            if project_id in last_terminal:
                classified[project_id] = last_terminal[project_id]
            elif project_id in active_ids:
                classified[project_id] = "active"
        missing = sorted(introduced.difference(classified))
        if missing:
            raise RuntimeError(
                "Planning reconciliation failed; unclassified project IDs: " + ", ".join(missing[:10])
            )

        rows = list(
            self._connection.execute(
                "SELECT project_id, technology, capacity_mw, region, development_stage, expected_completion_year FROM projects"
            )
        )
        project_by_id = {row[0]: row for row in rows}
        dimensions: dict[tuple[str, str, int | None], list[float]] = defaultdict(lambda: [0, 0.0])
        for project_id, outcome in classified.items():
            row = project_by_id[project_id]
            _, technology, capacity, region, stage, completion_year = row
            for dimension, value in (
                ("outcome", outcome), ("stage", stage),
                ("technology", technology), ("region", region),
            ):
                bucket = dimensions[(dimension, str(value), None)]
                bucket[0] += 1
                bucket[1] += float(capacity)
            if completion_year is not None and year + 1 <= int(completion_year) <= year + 3:
                bucket = dimensions[("expected_completion_year", str(completion_year), int(completion_year))]
                bucket[0] += 1
                bucket[1] += float(capacity)

        self._connection.execute("DELETE FROM annual_summary WHERE year=?", (year,))
        self._connection.executemany(
            "INSERT INTO annual_summary VALUES(?,?,?,?,?,?)",
            [
                (year, dimension, value, completion, int(values[0]), float(values[1]))
                for (dimension, value, completion), values in sorted(dimensions.items())
            ],
        )
        self._connection.commit()
        summary = {
            "year": year,
            "introduced_projects": len(introduced),
            "accounted_projects": len(classified),
            "reconciled": len(introduced) == len(classified),
            "breakdowns": defaultdict(dict),
        }
        display_labels: dict[tuple[str, str], str] = {}
        for (dimension, value, _completion), values in sorted(dimensions.items()):
            cleaned = str(value).strip() or "Unknown"
            display_key = (dimension, cleaned.casefold())
            label = display_labels.setdefault(display_key, cleaned)
            existing = summary["breakdowns"][dimension].setdefault(  # type: ignore[index]
                label, {"projects": 0, "capacity_mw": 0.0}
            )
            existing["projects"] += int(values[0])
            existing["capacity_mw"] += float(values[1])
        summary["breakdowns"] = dict(summary["breakdowns"])  # type: ignore[arg-type]
        event_groups = list(self._connection.execute(
            """
            SELECT e.event_type, COALESCE(e.reason_code, ''),
                   COALESCE(e.from_stage, ''), COALESCE(e.to_stage, ''),
                   COUNT(DISTINCT e.project_id),
                   SUM(COALESCE(e.capacity_mw, p.capacity_mw, 0.0))
            FROM events e LEFT JOIN projects p ON p.project_id=e.project_id
            WHERE e.year=?
            GROUP BY e.event_type, COALESCE(e.reason_code, ''),
                     COALESCE(e.from_stage, ''), COALESCE(e.to_stage, '')
            ORDER BY e.event_type, reason_code, from_stage, to_stage
            """,
            (year,),
        ))
        summary["causal_flows"] = [
            {
                "event_type": event_type,
                "reason_code": reason_code or None,
                "from_stage": from_stage or None,
                "to_stage": to_stage or None,
                "projects": int(project_count),
                "capacity_mw": float(capacity or 0.0),
            }
            for event_type, reason_code, from_stage, to_stage, project_count, capacity
            in event_groups
        ]
        by_event: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
        by_reason: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
        for event_type, reason_code, _from, _to, count, capacity in event_groups:
            by_event[str(event_type)][0] += int(count)
            by_event[str(event_type)][1] += float(capacity or 0.0)
            if reason_code:
                by_reason[str(reason_code)][0] += int(count)
                by_reason[str(reason_code)][1] += float(capacity or 0.0)
        summary["cause_breakdowns"] = {
            "event_type": {
                key: {"projects": int(value[0]), "capacity_mw": float(value[1])}
                for key, value in sorted(by_event.items())
            },
            "reason_code": {
                key: {"projects": int(value[0]), "capacity_mw": float(value[1])}
                for key, value in sorted(by_reason.items())
            },
        }
        outcomes = summary["breakdowns"].get("outcome", {})  # type: ignore[index]
        filtered_values = [
            value for key, value in outcomes.items()
            if str(key).startswith("filtered_") or str(key).startswith("excluded_")
        ]
        summary["kpis"] = {
            "active": outcomes.get("active", {"projects": 0, "capacity_mw": 0.0}),
            "commissioned": outcomes.get("commissioned", {"projects": 0, "capacity_mw": 0.0}),
            "failed": outcomes.get("failed_planning", {"projects": 0, "capacity_mw": 0.0}),
            "filtered": {
                "projects": sum(int(value["projects"]) for value in filtered_values),
                "capacity_mw": sum(float(value["capacity_mw"]) for value in filtered_values),
            },
            "deferred": {
                "projects": int(by_event.get(PlanningEventType.DEFERRED.value, [0, 0.0])[0]),
                "capacity_mw": float(by_event.get(PlanningEventType.DEFERRED.value, [0, 0.0])[1]),
            },
        }
        commissioning_rows = list(self._connection.execute(
            """
            SELECT p.assigned_asset_id, p.source, COUNT(DISTINCT e.project_id),
                   SUM(COALESCE(e.capacity_mw, p.capacity_mw, 0.0))
            FROM events e JOIN projects p ON p.project_id=e.project_id
            WHERE e.year=? AND e.event_type=?
            GROUP BY p.assigned_asset_id, p.source
            ORDER BY p.assigned_asset_id, p.source
            """,
            (year, PlanningEventType.COMMISSIONED.value),
        ))
        summary["commissioning_links"] = [
            {
                "asset_id": asset_id or "unassigned",
                "source": source or "unknown",
                "projects": int(count),
                "capacity_mw": float(capacity or 0.0),
            }
            for asset_id, source, count, capacity in commissioning_rows
        ]
        existing = {"schema_version": SCHEMA_VERSION, "years": []}
        if self.summary_path.exists():
            existing = json.loads(self.summary_path.read_text(encoding="utf-8"))
        years = [item for item in existing.get("years", []) if int(item["year"]) != year]
        years.append(summary)
        existing["years"] = sorted(years, key=lambda item: int(item["year"]))
        temporary = self.summary_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.summary_path)
        return summary

    def close(self) -> None:
        self.flush()
        self._connection.close()


def query_projects(
    database: Path,
    *,
    limit: int = 100,
    offset: int = 0,
    technology: str | None = None,
    region: str | None = None,
    outcome: str | None = None,
    search: str | None = None,
) -> dict[str, object]:
    limit = min(max(int(limit), 1), 500)
    offset = max(int(offset), 0)
    clauses, values = [], []
    for column, value in (("technology", technology), ("region", region), ("outcome", outcome)):
        if value:
            clauses.append(f"{column}=?")
            values.append(value)
    if search:
        clauses.append(
            "(project_id LIKE ? OR name LIKE ? OR technology LIKE ? "
            "OR region LIKE ? OR development_stage LIKE ? OR failure_reason_code LIKE ?)"
        )
        term = f"%{search.strip()}%"
        values.extend([term] * 6)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        total = connection.execute(f"SELECT COUNT(*) FROM projects{where}", values).fetchone()[0]
        rows = connection.execute(
            f"SELECT * FROM projects{where} ORDER BY project_id LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(row) for row in rows]}


def query_events(
    database: Path,
    *,
    limit: int = 100,
    offset: int = 0,
    year: int | None = None,
    event_type: str | None = None,
    project_id: str | None = None,
) -> dict[str, object]:
    limit = min(max(int(limit), 1), 500)
    offset = max(int(offset), 0)
    clauses, values = [], []
    for column, value in (("year", year), ("event_type", event_type), ("project_id", project_id)):
        if value is not None:
            clauses.append(f"{column}=?")
            values.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        total = connection.execute(f"SELECT COUNT(*) FROM events{where}", values).fetchone()[0]
        rows = connection.execute(
            f"SELECT * FROM events{where} ORDER BY sequence LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(row) for row in rows]}
