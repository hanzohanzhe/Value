"""Durable local job state and cooperative Data Workbench execution."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .contracts import canonical_payload


class JobCancelled(RuntimeError):
    pass


_TRANSITIONS = {
    "queued": {"running", "cancel_requested", "failed"},
    "running": {"completed", "failed", "cancel_requested"},
    "cancel_requested": {"cancelled", "failed", "completed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


class SQLiteJobStore:
    def __init__(self, path: Path, *, clock: Callable[[], str] | None = None) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS data_workbench_jobs (
                    job_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    declared_input_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL,
                    result_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, object] | None:
        if row is None:
            return None
        return {
            "schema_version": "value.data-job/v1",
            "job_id": row["job_id"],
            "operation": row["operation"],
            "declared_input": json.loads(row["declared_input_json"]),
            "status": row["status"],
            "progress": row["progress"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create(
        self,
        operation: str,
        declared_input: Mapping[str, object],
        *,
        job_id: str | None = None,
    ) -> dict[str, object]:
        if not operation.strip():
            raise ValueError("Job operation is required")
        encoded = canonical_payload(dict(declared_input))
        identity = job_id or f"data-job-{uuid.uuid4().hex}"
        timestamp = self.clock()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO data_workbench_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identity, operation, encoded, "queued", 0.0, None, None, None, timestamp, timestamp),
            )
        value = self.read(identity)
        assert value is not None
        return value

    def read(self, job_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM data_workbench_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._row(row)

    def transition(
        self,
        job_id: str,
        target: str,
        *,
        progress: float | None = None,
        result: Mapping[str, object] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, object]:
        current = self.read(job_id)
        if current is None:
            raise KeyError(f"Unknown Data Workbench job {job_id}")
        if target not in _TRANSITIONS.get(str(current["status"]), set()):
            raise ValueError(f"Invalid job transition {current['status']} -> {target}")
        if result is not None:
            result_json = canonical_payload(dict(result))
        else:
            result_json = None
        resolved_progress = (
            float(progress)
            if progress is not None
            else (1.0 if target == "completed" else float(current["progress"]))
        )
        if not 0 <= resolved_progress <= 1:
            raise ValueError("Job progress must be between zero and one")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE data_workbench_jobs
                SET status = ?, progress = ?, result_json = ?, error_code = ?,
                    error_message = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    target,
                    resolved_progress,
                    result_json,
                    error_code,
                    error_message,
                    self.clock(),
                    job_id,
                ),
            )
        value = self.read(job_id)
        assert value is not None
        return value

    def request_cancel(self, job_id: str) -> dict[str, object]:
        current = self.read(job_id)
        if current is None:
            raise KeyError(f"Unknown Data Workbench job {job_id}")
        if current["status"] == "cancel_requested":
            return current
        return self.transition(job_id, "cancel_requested")

    def cancellation_requested(self, job_id: str) -> bool:
        value = self.read(job_id)
        return value is not None and value["status"] == "cancel_requested"

    def recover_incomplete(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_id, status FROM data_workbench_jobs WHERE status IN ('running', 'cancel_requested') ORDER BY job_id"
            ).fetchall()
        recovered: list[str] = []
        for row in rows:
            job_id = str(row["job_id"])
            if row["status"] == "cancel_requested":
                self.transition(job_id, "cancelled", error_code="DW_JOB_CANCELLED_ON_RESTART")
            else:
                self.transition(
                    job_id,
                    "failed",
                    error_code="DW_JOB_RESTART_RECOVERY_REQUIRED",
                    error_message="Interrupted local job retained no usable partial result",
                )
            recovered.append(job_id)
        return recovered


class WorkbenchJobRunner:
    def __init__(self, store: SQLiteJobStore) -> None:
        self.store = store

    def run(
        self,
        job_id: str,
        handler: Callable[[Callable[[], bool]], Mapping[str, object]],
    ) -> dict[str, object]:
        current = self.store.read(job_id)
        if current is None:
            raise KeyError(f"Unknown Data Workbench job {job_id}")
        if current["status"] == "cancel_requested":
            return self.store.transition(job_id, "cancelled", error_code="DW_JOB_CANCELLED")
        self.store.transition(job_id, "running", progress=0.01)
        try:
            result = handler(lambda: self.store.cancellation_requested(job_id))
            if self.store.cancellation_requested(job_id):
                return self.store.transition(job_id, "cancelled", error_code="DW_JOB_CANCELLED")
            return self.store.transition(job_id, "completed", result=result)
        except JobCancelled:
            current = self.store.read(job_id)
            if current and current["status"] == "running":
                self.store.transition(job_id, "cancel_requested")
            return self.store.transition(job_id, "cancelled", error_code="DW_JOB_CANCELLED")
        except Exception as exc:
            code = f"DW_JOB_{type(exc).__name__.upper()}"
            return self.store.transition(
                job_id,
                "failed",
                error_code=code,
                error_message=str(exc),
            )
