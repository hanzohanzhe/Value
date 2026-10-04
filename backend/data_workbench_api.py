"""Focused HTTP-contract adapter for the local Data Workbench service."""

from __future__ import annotations

import re
import threading
from typing import Mapping

from gridform_core.data_workbench.jobs import SQLiteJobStore, WorkbenchJobRunner


BASE = "/api/data-workbench/v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,159}$")


class DataWorkbenchApi:
    def __init__(self, service: object, jobs: SQLiteJobStore) -> None:
        self.service = service
        self.jobs = jobs
        self.runner = WorkbenchJobRunner(jobs)

    def _run_job(self, job_id: str) -> None:
        job = self.jobs.read(job_id)
        if job is None:
            return
        operation = str(job["operation"])
        declared = dict(job["declared_input"])  # type: ignore[arg-type]

        def handler(cancelled: object) -> Mapping[str, object]:
            run_operation = getattr(self.service, "run_operation", None)
            if callable(run_operation):
                return run_operation(operation, declared, cancelled)
            method = getattr(self.service, operation)
            if operation == "validate":
                return method(str(declared.get("candidate_id") or ""))
            return method(declared)

        self.runner.run(job_id, handler)  # type: ignore[arg-type]

    @staticmethod
    def _error(code: str, message: str, status: int = 400) -> tuple[int, dict[str, object]]:
        return status, {"schema_version": "value.data-api-error/v1", "error_code": code, "error": message}

    def handle(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None,
    ) -> tuple[int, dict[str, object]]:
        if not path.startswith(BASE) or ".." in path or "\\" in path:
            return self._error("DW_API_PATH", "Unsafe or unknown Data Workbench API path")
        relative = path[len(BASE) :].strip("/")
        parts = relative.split("/") if relative else []
        payload = dict(body or {})
        try:
            if method == "GET" and parts == ["overlays"]:
                return 200, self.service.overlay_editor.overlays()
            if method == "POST" and len(parts) == 3 and parts[0] == "overlays" and parts[2] == "candidates":
                return 201, self.service.overlay_editor.clone(parts[1], payload)
            if len(parts) >= 2 and parts[0] == "overlay-candidates":
                if not SAFE_ID.fullmatch(parts[1]):
                    return self._error("DW_API_PATH", "Invalid overlay candidate directory")
                if method == "GET" and len(parts) == 2:
                    return 200, self.service.overlay_editor.detail(parts[1])
                if method == "POST" and len(parts) == 3 and parts[2] == "validate":
                    if set(payload) != {"schema_version", "candidate_id"} or payload.get("schema_version") != "value.network-overlay-validation-request/v1":
                        return self._error("DW_API_INPUT", "Validation requires exact candidate identity; no client validator overrides")
                    return 200, self.service.overlay_editor.validate(parts[1], str(payload["candidate_id"]))
                if method == "POST" and len(parts) == 3 and parts[2] == "promote":
                    fields = {"schema_version", "candidate_id", "version", "reviewer", "accepted_waivers"}
                    if set(payload) != fields or payload.get("schema_version") != "value.data-promotion-request/v1" or not isinstance(payload.get("accepted_waivers"), list):
                        return self._error("DW_API_PROMOTION_FIELDS", "Promotion requires exact candidate identity, version, reviewer and waivers")
                    return 200, self.service.overlay_editor.promote(parts[1], payload)
            if method == "GET" and parts == ["sources"]:
                return 200, self.service.sources()
            if method == "GET" and parts == ["candidates"]:
                return 200, self.service.candidates()
            if method == "GET" and parts == ["revisions"]:
                return 200, self.service.revisions()
            if method == "GET" and parts == ["bundles"]:
                return 200, self.service.bundles()
            if method == "GET" and len(parts) == 2 and parts[0] == "reports":
                if not SAFE_ID.fullmatch(parts[1]):
                    return self._error("DW_API_PATH", "Invalid candidate ID")
                return 200, self.service.report(parts[1])
            if method == "GET" and len(parts) == 2 and parts[0] == "jobs":
                job = self.jobs.read(parts[1])
                return (200, {"job": job}) if job else self._error("DW_API_JOB_UNKNOWN", "Job not found", 404)
            if method == "POST" and parts == ["jobs"]:
                if payload.get("schema_version") != "value.data-job-request/v1":
                    return self._error("DW_API_SCHEMA", "Expected value.data-job-request/v1")
                operation = str(payload.get("operation") or "")
                if operation not in {"discover", "fetch", "compile", "validate"}:
                    return self._error("DW_API_OPERATION", "Unsupported cancellable operation")
                declared = payload.get("declared_input")
                if not isinstance(declared, Mapping):
                    return self._error("DW_API_INPUT", "declared_input must be an object")
                job = self.jobs.create(operation, declared)
                if payload.get("start") is True:
                    threading.Thread(
                        target=self._run_job,
                        args=(str(job["job_id"]),),
                        daemon=True,
                        name=f"value-data-{job['job_id']}",
                    ).start()
                return 202, {"job": job}
            if method == "POST" and len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel":
                if not SAFE_ID.fullmatch(parts[1]):
                    return self._error("DW_API_PATH", "Invalid job ID")
                return 200, {"job": self.jobs.request_cancel(parts[1])}
            if len(parts) == 3 and parts[0] == "candidates" and method == "POST":
                candidate_id, action = parts[1], parts[2]
                if not SAFE_ID.fullmatch(candidate_id):
                    return self._error("DW_API_PATH", "Invalid candidate ID")
                if action == "validate":
                    forbidden = set(payload).difference({"schema_version"})
                    if forbidden:
                        return self._error("DW_API_VALIDATOR_OVERRIDE", "Client cannot override validator output")
                    if payload.get("schema_version") != "value.data-validation-request/v1":
                        return self._error("DW_API_SCHEMA", "Expected value.data-validation-request/v1")
                    return 200, self.service.validate(candidate_id)
                if action == "promote":
                    allowed = {"schema_version", "candidate_id", "version", "reviewer", "accepted_waivers"}
                    forbidden = set(payload).difference(allowed)
                    if forbidden:
                        return self._error("DW_API_VALIDATOR_OVERRIDE", "Client cannot override validator output")
                    required = allowed
                    if set(payload) != required or payload.get("schema_version") != "value.data-promotion-request/v1":
                        return self._error("DW_API_PROMOTION_FIELDS", "Promotion requires exact candidate hash, version, reviewer and accepted waivers")
                    if payload.get("candidate_id") != candidate_id or not str(payload.get("reviewer") or "").strip():
                        return self._error("DW_API_PROMOTION_FIELDS", "Promotion path, hash and reviewer must agree")
                    if not isinstance(payload.get("accepted_waivers"), list):
                        return self._error("DW_API_PROMOTION_FIELDS", "accepted_waivers must be an exact list")
                    return 200, self.service.promote(candidate_id, payload)
            return self._error("DW_API_NOT_FOUND", "Data Workbench endpoint not found", 404)
        except (KeyError, ValueError, OSError) as exc:
            return self._error("DW_API_INVALID", str(exc))

    def handle_upload(self, method: str, path: str, raw: bytes, filename: str, expected_candidate_id: str) -> tuple[int, dict[str, object]]:
        if not path.startswith(BASE + "/") or ".." in path or "\\" in path:
            return self._error("DW_API_PATH", "Unsafe upload path")
        parts = path[len(BASE):].strip("/").split("/")
        if method != "POST" or len(parts) != 5 or parts[0] != "overlay-candidates" or parts[2] != "roles" or parts[4] != "file":
            return self._error("DW_API_PATH", "Unknown overlay upload endpoint", 404)
        if len(raw) > 32 * 1024 * 1024:
            return self._error("DW_API_UPLOAD_LIMIT", "Overlay files are limited to 32 MiB", 413)
        try:
            return 200, self.service.overlay_editor.upload(parts[1], parts[3], raw, filename, expected_candidate_id)
        except (KeyError, ValueError, OSError, UnicodeError) as exc:
            return self._error("DW_API_INVALID", str(exc))
