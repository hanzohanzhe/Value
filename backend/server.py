"""Loopback-only API for VALUE projects, data packs and model runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import traceback
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from backend.data_mapping import DataMappingService, DataMappingError, MAX_UPLOAD_BYTES as MAX_MAPPING_UPLOAD_BYTES
from backend.data_pack_clone import DataPackCloneError, clone_data_pack, guard_clone_upload, manifest_sha256
from backend.data_workbench_api import BASE as DATA_WORKBENCH_API_BASE, DataWorkbenchApi
from backend.study_derivation import StudyDerivationError, derive_study
from backend.module_authoring import module_authoring_detail, module_authoring_template
from backend.extension_authoring import validate_extension_proposal, extension_proposal_template
from backend.extension_results import query_extension_artifacts
from backend.result_queries import query_vre_curtailment_results
from backend.run_reproduction import assess_run_reproduction
from backend.frozen_run_recovery import (
    FrozenRecoveryError, review_frozen_recovery, publish_frozen_recovery,
    verify_recovered_configuration, verify_recovered_inputs,
)
from backend.run_execution import current_execution, bind_run_execution, verify_run_execution
from gridform_core.execution_archive import verify_execution_bundle
from gridform_core.legacy_module_ids import ORCHESTRATOR_ENGINES as LEGACY_ORCHESTRATOR_ENGINES

from gridform_core.catalog import get_catalog_snapshot
from gridform_core.dataset_slots import DATASET_SLOTS
from gridform_core.errors import ContractError
from gridform_core.execution_archive import ExecutionArchiveError
from gridform_core.module_quarantine import (
    MODULE_LIFECYCLE_LOCK,
    ModuleQuarantinedError,
    all_quarantine_entries,
    clear_negative_caches,
    degraded_reasons,
    installation_record_entries,
    quarantine_report,
    status_for_code,
)
from gridform_core.module_bundle import MAX_BUNDLE_BYTES
from gridform_core.extension_bundle import (
    ExtensionBundleError,
    install_extension_bundle,
    list_extension_installations,
    set_extension_enabled,
)
from gridform_core.data_bundle import (
    MAX_BUNDLE_BYTES as MAX_DATA_BUNDLE_BYTES,
    DataBundleError,
    install_data_bundle,
)
from gridform_core.research_suite import ResearchSuiteError, install_research_suite
from gridform_core.module_installation import (
    ModuleInstallationError,
    install_module_bundle,
    list_module_installations,
    set_module_enabled,
)
from gridform_core.frontend_contract import (
    FRONTEND_CONTRACT_VERSION,
    extension_catalogue,
    module_slot_catalog,
    resolve_study_draft,
)
from gridform_core.parameters import (
    ParameterValidationError,
    parameter_schema,
    resolve_scheme_c_parameters,
)
from gridform_core.market_ledger import query_market_table
from gridform_core.market_replay import (
    legacy_staged_market_available,
    market_replay_capabilities,
    query_auction_view,
    query_dispatch_timeline,
    query_legacy_staged_market_jsonl,
    query_vre_curtailment_summary,
    query_vre_curtailment_timeline,
)
from gridform_core.zonal_results import (
    export_zonal_results,
    query_zonal_annual_brief,
    query_zonal_results,
    zonal_workspace_capabilities,
)
from gridform_core.planning_ledger import query_events, query_projects
from gridform_core.planning_index import (
    query_index_events,
    query_index_projects,
    query_index_summary,
)
from gridform_core.errors import public_failure
from gridform_core.run_policy import resolve_run_policy
from gridform_core.value_101 import (
    VALUE_101_NETWORK_PACK_ID,
    VALUE_101_PACK_IDS,
    value_101_descriptor,
    value_101_study,
)
from gridform_core.replay_export import (
    ReplayExportRequest,
    create_replay_export,
)
from gridform_core.value_101_lifecycle import (
    build_value_101_network_pair,
    is_value_101_record,
    value_101_origin,
)
from gridform_core.project_revision import attach_revision_identity, save_project_revision
from gridform_core.study_lifecycle import (
    StudyLifecycleError,
    list_study_trash,
    move_study_to_trash,
    move_value_101_records_to_trash,
    restore_study,
    study_id_is_reserved,
)
from gridform_core.data_pack_validation import validate_data_pack
from gridform_core.preflight import run_preflight
from gridform_core.preflight_resources import (
    resource_readiness_from_snapshot,
    selected_staged_zonal_calibration_runner,
)
from gridform_core.run_snapshot import (
    SnapshotError,
    create_run_input_snapshot,
    verify_run_input_snapshot,
)
from gridform_core.run_input_snapshot import (
    ResourceSnapshotMismatch,
    freeze_resource_readiness,
)
from gridform_core.data_import import promote_binding_revision
from gridform_core.data_workbench.jobs import SQLiteJobStore
from gridform_core.data_workbench.local_service import LocalDataWorkbenchService
from gridform_core.data_workbench.state import resolve_data_workbench_root
from gridform_core.data_contract_templates import (
    missing_input_checklist,
    preview_binding,
    runtime_supported_formats,
    template_for_role,
    template_available,
)
from gridform_core.domain_readiness import build_domain_readiness
from gridform_core.domain_results import (
    DomainResultError,
    domain_result_capabilities,
    query_ac_results,
    query_expansion_events,
    query_expansion_summary,
    query_network_branches,
    query_network_periods,
    query_network_summary,
)
from gridform_core.run_lifecycle import LifecycleError
from backend.lifecycle.atomic_io import atomic_write_json
from backend.lifecycle.file_locks import LOCK_HELD, FileLock, LockTimeout, hold_lock
from backend.lifecycle.run_status import (
    STATUS_LOCK,
    STATUS_LOCK_TIMEOUT_SECONDS,
    WRITER_SERVER,
    LeaseHeldError,
    create_status,
    is_lifecycle_root_file,
    read_status,
    update_status,
)
from backend.lifecycle.states import ACTIVE_STATES, DELETABLE_STATES, classify
from backend.lifecycle.worker_lease import lease_state
from backend.run_supervisor import SHUTDOWN_SEAL_SECONDS, RunSupervisor, WorkerSpawnError, worker_liveness
from backend.api_session import new_token, publish_session, withdraw_session
from backend.api_security import (
    SECURITY_RESPONSE_HEADERS,
    UnsupportedMediaType,
    drainable_length,
    evaluate as evaluate_request,
)
from gridform_core.run_lineage import copperplate_rerun_project
from gridform_core.run_quota import (
    QUOTA_CORRECTIVE_ACTIONS,
    RunQuotaPolicy,
    global_quota_reasons,
    output_reservation_bytes,
    quarantine_orphan_run_directories,
    quota_usage,
    remove_legacy_reservation_lock,
    reserve_run_space,
    run_outstanding_bytes,
)
from gridform_core.run_bundle import export_run_bundle, validate_bundle_archive
from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection
from gridform_core.results_summary import build_run_summary, compare_run_summaries, comparison_csv
from gridform_core.runtime_paths import (
    APPLICATION_VERSION,
    SOURCE_ROOT,
    external_modules_root,
    user_data_root,
)
from gridform_core.runtime_capabilities import VALUE_NATIVE, capability_matrix
from gridform_core.recovery_capability import latest_safe_recovery_point, recovery_capability
from gridform_core.state_migrations import ensure_state_layout


PROJECT_ROOT = SOURCE_ROOT
STATE_ROOT = user_data_root()
PACKS_ROOT = STATE_ROOT / "data-packs"
PROJECTS_ROOT = STATE_ROOT / "projects"
RUNS_ROOT = STATE_ROOT / "runs"
OBJECTS_ROOT = STATE_ROOT / "objects" / "sha256"
IMPORT_STAGING_ROOT = STATE_ROOT / "import-staging"
ARCHIVES_ROOT = STATE_ROOT / "archives"
TRASH_ROOT = STATE_ROOT / "trash"
STUDY_LIFECYCLE_LOCK = threading.RLock()
# Runs written before the gridform -> value rename keep their stored engine
# label; both labels denote the v2 annual application service (R2-08).
ORCHESTRATOR_ENGINES = LEGACY_ORCHESTRATOR_ENGINES
REPLAY_EXPORT_JOBS_LOCK = threading.RLock()
# Global lock order (P0_CONVENTIONS section 5): .backend.lock ->
# STUDY_LIFECYCLE_LOCK -> RUN_ACTION_LOCKS[run_id] -> MODULE_LIFECYCLE_LOCK ->
# <runs>/.reservation.lock -> <run>/status.lock.  Every server-side status
# change of one run is serialised under its RUN_ACTION_LOCKS entry.
RUN_ACTION_LOCKS: dict[str, threading.RLock] = {}
_RUN_ACTION_LOCKS_GUARD = threading.Lock()


def run_action_lock(run_id: str) -> threading.RLock:
    with _RUN_ACTION_LOCKS_GUARD:
        lock = RUN_ACTION_LOCKS.get(run_id)
        if lock is None:
            lock = RUN_ACTION_LOCKS[run_id] = threading.RLock()
        return lock


BACKEND_LOCK_NAME = ".backend.lock"
EXIT_BACKEND_ALREADY_RUNNING = 3
SUPERVISOR: RunSupervisor | None = None
_SUPERVISOR_GUARD = threading.Lock()


def _seal_still_wanted(run_dir: Path, queued: Mapping[str, Any]) -> bool:
    """Is the run still exactly the failed run that was queued for sealing?

    A delete may have moved it to the trash, or a resume may have queued it
    again, between ``settle`` and the sealer (review M1-P0-3 #2).
    """

    if not run_dir.is_dir() or (run_dir / "provenance.json").exists():
        return False
    current = read_status(run_dir)
    if not current or classify(current) != "failed":
        return False
    history = current.get("lifecycle_history")
    queued_history = queued.get("lifecycle_history")
    if not isinstance(history, list) or not isinstance(queued_history, list):
        return False
    return len(history) == len(queued_history) and current.get("worker_outcome") == queued.get("worker_outcome")


def _seal_failed_run(run_dir: Path, status: Mapping[str, Any]) -> None:
    """Background sealer: failed provenance for a run settled by the server.

    Runs under the run's action lock, like every server-side change of a run,
    and seals only a run that is still the failed run it was queued for.
    """

    from gridform_core.provenance import write_failed_run_provenance

    with run_action_lock(run_dir.name):
        if not _seal_still_wanted(run_dir, status):
            return
        try:
            path = write_failed_run_provenance(
                run_dir, run_id=str(status.get("id") or run_dir.name),
                project_id=str(status.get("project_id") or ""),
                error_code=str(status.get("error_code") or "GF_WORKER_LOST"),
            )
        except (RuntimeError, OSError, ValueError) as exc:
            if run_dir.is_dir():
                update_status(run_dir, writer=WRITER_SERVER, mutate=lambda current: current.update({
                    "warnings": [*(current.get("warnings") if isinstance(current.get("warnings"), list) else []), {
                        "schema_version": "value.warning/v1", "code": "GF_FAILED_PROVENANCE_WARNING",
                        "category": "artifact", "severity": "warning",
                        "message": f"The stopped run could not be sealed: {exc}",
                    }],
                }))
            return
        update_status(run_dir, writer=WRITER_SERVER,
                      mutate=lambda current: current.__setitem__("provenance_artifact", path.name))


def run_supervisor() -> RunSupervisor:
    """The process's supervisor (created lazily for embedded/test servers)."""

    global SUPERVISOR
    with _SUPERVISOR_GUARD:
        if SUPERVISOR is None or SUPERVISOR.runs_root != RUNS_ROOT:
            SUPERVISOR = RunSupervisor(RUNS_ROOT, run_lock=run_action_lock, sealer=_seal_failed_run)
        return SUPERVISOR


MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MIN_FREE_SPACE_BYTES = 1024 * 1024 * 1024
# No CORS: browsers reach the API only through the same-origin UI gateway
# (P0-1); every request passes backend.api_security.evaluate first.
ROLE_INDEX = {slot["role"]: slot for slot in DATASET_SLOTS}


# Set when a catalogue refresh failed after a lifecycle change: the previous
# catalogue stays in use, new runs are refused (503) until a rescan succeeds.
CATALOG_STALE: dict[str, str] | None = None


def refresh_module_catalog(*, refresh: bool = True) -> None:
    """Refresh the single registry after a reviewed local lifecycle change.

    External faults never raise here (they are quarantined); anything that
    still fails marks the catalogue stale and raises a coded error.
    """

    global MODULE_REGISTRY, MODULES, MODULE_SLOT_BY_ID, REQUIRED_MODULE_SLOTS, CATALOG_STALE
    with MODULE_LIFECYCLE_LOCK:
        try:
            snapshot = get_catalog_snapshot(refresh=refresh)
        except (Exception, SystemExit) as exc:
            CATALOG_STALE = {"code": "GF_MODULE_CATALOG_STALE", "error_type": type(exc).__name__}
            raise ModuleQuarantinedError(
                "GF_MODULE_CATALOG_REFRESH",
                "The module catalogue could not be refreshed; the previous catalogue stays in use "
                "and new runs are paused. Fix or disable the change, then rescan modules.",
            ) from exc
        MODULE_REGISTRY = snapshot["registry"]
        MODULES = snapshot["modules"]
        MODULE_SLOT_BY_ID = snapshot["slot_by_id"]
        REQUIRED_MODULE_SLOTS = snapshot["required_slots"]
        CATALOG_STALE = None


# Built once at import (fault-isolated: a broken external entry is
# quarantined, never fatal); main() re-reads the same cached snapshot.
refresh_module_catalog(refresh=False)


def module_record_entries() -> tuple[Any, ...]:
    """Damaged installer records: each refuses every run start, so they are
    reported with the quarantine (GF_MODULE_INSTALL_RECORD_INVALID)."""

    return installation_record_entries(external_modules_root())


def module_quarantine_payload() -> dict[str, Any]:
    report = quarantine_report(
        MODULE_REGISTRY, extra_entries=module_record_entries(), modules_root=external_modules_root()
    )
    if CATALOG_STALE:
        report = {**report, "status": "degraded", "catalog_stale": True}
    return report


def pending_run_statuses() -> dict[str, str]:
    """Runs whose worker has not finished, with their status: a lifecycle
    change alters their execution identity, so it needs explicit
    confirmation (P0-2 Q9)."""

    found: dict[str, str] = {}
    for path in sorted(RUNS_ROOT.glob("*/status.json")):
        status = read_object(path)
        state = str(status.get("status") or "")
        if state in ACTIVE_STATES:
            found[str(status.get("id") or path.parent.name)] = state
    return found


def pending_runs() -> list[str]:
    return list(pending_run_statuses())


def require_no_pending_runs(confirmed: bool) -> None:
    statuses = pending_run_statuses()
    if not statuses or confirmed:
        return
    # Queued/snapshotting runs import the installed code when their worker
    # starts; running ones keep theirs but their resume checks the identity.
    waiting = [run for run, state in statuses.items() if state in {"queued", "snapshotting"}]
    started = [run for run in statuses if run not in waiting]
    parts = []
    if waiting:
        parts.append(f"{len(waiting)} run(s) not started yet (" + ", ".join(waiting[:10])
                     + ") would start with the changed code")
    if started:
        parts.append(f"{len(started)} run(s) already running (" + ", ".join(started[:10])
                     + ") keep their code but could not be resumed after the change")
    raise ModuleQuarantinedError(
        "GF_MODULE_LIFECYCLE_RUNS_PENDING",
        "Runs have not finished: " + "; ".join(parts) + ". Confirm to change installed modules anyway.",
    )


def _quarantined_ids(kind: str) -> set[str]:
    return {str(entry.entry_id) for entry in all_quarantine_entries(MODULE_REGISTRY)
            if entry.kind == kind and entry.entry_id}


def extension_installation_records() -> dict[str, dict[str, Any]]:
    """Read installer-owned extension records; built-ins have no record."""

    records: dict[str, dict[str, Any]] = {}
    root = external_modules_root() / "installed-extensions"
    if not root.is_dir():
        return records
    for path in sorted(root.glob("*/*/installation.json")):
        record = read_json(path)
        if not isinstance(record, dict) or not record.get("extension_id"):
            continue
        current = records.get(str(record["extension_id"]))
        if current is None or str(record.get("installed_at", "")) > str(current.get("installed_at", "")):
            records[str(record["extension_id"])] = record
    return records


def extension_dependents(extension_id: str) -> dict[str, list[str]]:
    projects = [
        str(project["id"])
        for project in list_projects()
        if extension_id in tuple(project.get("selected_extensions") or ())
    ]
    runs: list[str] = []
    for status_path in RUNS_ROOT.glob("*/status.json"):
        project = read_object(status_path.parent / "input-snapshot" / "project.json")
        if extension_id in tuple(project.get("selected_extensions") or ()):
            runs.append(status_path.parent.name)
    return {
        "projects": sorted(projects),
        "runs_and_retained_history": sorted(runs),
    }


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slug(value: str, fallback: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return safe[:64] or fallback


RUN_ID_MAX_CHARS = 40


def bounded_run_id(project_id: str, *, timestamp: str, nonce: str) -> str:
    """Build a readable run ID without exhausting the Windows path budget."""

    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}", timestamp):
        raise ValueError("Run timestamp must use YYYYMMDD-HHMMSS.")
    safe_nonce = re.sub(r"[^a-fA-F0-9]", "", nonce).lower()[:8]
    if len(safe_nonce) != 8:
        raise ValueError("Run nonce must contain eight hexadecimal characters.")
    suffix = f"-{timestamp}-{safe_nonce}"
    prefix_budget = RUN_ID_MAX_CHARS - len(suffix)
    project_prefix = slug(project_id, "run")[:prefix_budget]
    return f"{project_prefix}{suffix}"


def atomic_json(path: Path, payload: Any) -> None:
    """Write a server-owned artifact (never a run's status.json; see run_status)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload)


def _record_start_failure(run_dir: Path, fields: Mapping[str, Any], reason_code: str) -> dict[str, Any]:
    """Move a run that never reached its worker from snapshotting to failed."""

    return update_status(
        run_dir,
        mutate=lambda status: status.update({**fields, "execution_status": "failed"}),
        transition="failed",
        reason_code=reason_code,
        writer=WRITER_SERVER,
    )


def _mark_unfinished_start_failed(run_dir: Path) -> None:
    """After an unexpected error, never leave a start in snapshotting/queued."""

    try:
        status = read_json(run_dir / "status.json", {})
        if isinstance(status, Mapping) and status.get("status") in {"snapshotting", "queued"}:
            _record_start_failure(run_dir, {
                "current_stage": "Run start failed",
                "error_code": "GF_RUN_START_FAILED",
            }, "GF_RUN_START_FAILED")
    except (LifecycleError, OSError) as exc:  # the original error is re-raised
        print(f"VALUE: could not record the failed start of {run_dir.name}: {exc}", file=sys.stderr)


def read_json(path: Path, fallback: Any = None) -> Any:
    """Read one JSON record; a missing, unreadable or non-UTF-8 file is the
    fallback (F5-05: one bad record never breaks a listing)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"VALUE: unreadable record {path.name} in {path.parent.name}: {type(exc).__name__}", file=sys.stderr)
        return fallback


def read_object(path: Path) -> dict[str, Any]:
    """Read a JSON object record; anything else (list, scalar, unreadable) is {}."""
    value = read_json(path, {})
    return value if isinstance(value, dict) else {}


class QueryParameterError(ValueError):
    """An invalid query parameter (HTTP 400, GF_QUERY_INVALID)."""


def _record_warning(code: str, message: str) -> dict[str, str]:
    return {
        "schema_version": "value.warning/v1", "code": code, "category": "artifact",
        "severity": "warning", "message": message,
    }


def _replay_export_job_path(run_root: Path, job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("Replay export job ID is invalid")
    run_root = run_root.resolve()
    path = (
        run_root / "model-output" / "exports" / "jobs" / f"{job_id}.json"
    ).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise ValueError("Replay export job path escapes the run") from exc
    return path


def read_replay_export_job(run_root: Path, job_id: str) -> dict[str, object]:
    payload = read_json(_replay_export_job_path(run_root, job_id))
    if not isinstance(payload, dict):
        raise LookupError("Replay export job was not found")
    return dict(payload)


def create_replay_export_job(
    run_root: Path,
    request: ReplayExportRequest,
) -> dict[str, object]:
    """Queue one export in a daemon thread, independently of the model worker."""

    run_root = run_root.resolve()
    database = (run_root / "model-output" / "market" / "market.sqlite").resolve()
    try:
        database.relative_to(run_root)
    except ValueError as exc:
        raise ValueError("Market ledger path escapes the run") from exc
    if not database.is_file():
        raise FileNotFoundError("market ledger is not available")
    job_id = uuid.uuid4().hex
    suffix = {"zip": "zip", "jsonl": "jsonl", "csv": "csv"}[request.output_format]
    destination = (
        run_root / "model-output" / "exports" / f"replay-{job_id}.{suffix}"
    ).resolve()
    job_path = _replay_export_job_path(run_root, job_id)
    record: dict[str, object] = {
        "schema_version": "value.replay-export-job/v1",
        "job_id": job_id,
        "status": "queued",
        "created_at": now(),
        "request": {
            "range_kind": request.range_kind,
            "year": request.year,
            "period_from": request.period_from,
            "period_to": request.period_to,
            "output_format": request.output_format,
        },
        "artifact_path": str(destination),
    }
    with REPLAY_EXPORT_JOBS_LOCK:
        atomic_json(job_path, record)

    def run_export() -> None:
        current = {**record, "status": "running", "started_at": now()}
        with REPLAY_EXPORT_JOBS_LOCK:
            atomic_json(job_path, current)
        try:
            result = dict(create_replay_export(database, request, destination))
            current.update({
                "status": "completed",
                "completed_at": now(),
                "result": result,
            })
        except Exception as exc:  # fail-closed record for local background work
            current.update({
                "status": "failed",
                "completed_at": now(),
                "error": str(exc),
            })
            code = getattr(exc, "code", None)
            if isinstance(code, str) and code:
                current["error_code"] = code
        with REPLAY_EXPORT_JOBS_LOCK:
            atomic_json(job_path, current)

    threading.Thread(
        target=run_export,
        name=f"value-replay-export-{job_id[:8]}",
        daemon=True,
    ).start()
    return dict(record)


def _integer_query(values: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(values.get(key, [str(default)])[0])
    except (TypeError, ValueError) as exc:
        raise QueryParameterError(f"{key} must be an integer") from exc


def _optional_integer_query(values: dict[str, list[str]], key: str) -> int | None:
    raw = values.get(key, [""])[0]
    if raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise QueryParameterError(f"{key} must be an integer") from exc


def _run_root(run_id: str) -> Path | None:
    safe_id = slug(run_id, "run")
    if safe_id != run_id:
        return None
    root = (RUNS_ROOT / safe_id).resolve()
    try:
        root.relative_to(RUNS_ROOT.resolve())
    except ValueError:
        return None
    return root if (root / "status.json").is_file() else None


def _downloadable_artifact(relative: str) -> bool:
    """Lock files and root lifecycle records are never listed or served."""
    name = relative.rsplit("/", 1)[-1]
    if name.endswith(".lock"):
        return False
    return "/" in relative or not is_lifecycle_root_file(name)


def safe_run_artifact(run_id: str, relative_path: str) -> Path | None:
    """Resolve a downloadable artifact without permitting traversal."""

    root = _run_root(run_id)
    if root is None or not relative_path or "\x00" in relative_path:
        return None
    decoded = unquote(relative_path).replace("\\", "/")
    if decoded.startswith("/") or any(part in {"", ".", ".."} for part in decoded.split("/")):
        return None
    candidate = (root / Path(decoded)).resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError:
        return None
    if not _downloadable_artifact(relative):
        return None
    return candidate if candidate.is_file() else None


def list_run_artifacts(run_id: str) -> list[dict[str, object]]:
    root = _run_root(run_id)
    if root is None:
        return []
    provenance = read_json(root / "provenance.json", {})
    checksums = {
        str(item.get("artifact_id")): item.get("sha256")
        for item in provenance.get("artifacts", [])
    }
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix in {".tmp", ".wal", ".shm"}:
            continue
        relative = path.relative_to(root).as_posix()
        if not _downloadable_artifact(relative):
            continue
        rows.append({
            "id": relative,
            "name": path.name,
            "bytes": path.stat().st_size,
            "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "sha256": checksums.get(relative),
            "download_url": f"/api/runs/{run_id}/artifacts/{relative}",
        })
    return rows


def run_provenance(run_id: str) -> dict[str, object] | None:
    root = _run_root(run_id)
    if root is None:
        return None
    provenance = read_json(root / "provenance.json")
    if provenance:
        return {
            "schema_version": provenance.get("schema_version"),
            "created_at": provenance.get("created_at"),
            "identity": provenance.get("identity"),
            "modules": provenance.get("modules"),
            "source_control": provenance.get("source_control"),
            "environment": provenance.get("environment"),
            "data_bindings": provenance.get("data_bindings"),
            "resolved_configuration": provenance.get("resolved_configuration"),
            "randomness": provenance.get("randomness"),
            "initial_state_sha256": provenance.get("initial_state_sha256"),
            "annual_state_chain": provenance.get("annual_state_chain"),
            "artifact_count": len(provenance.get("artifacts", [])),
        }
    status = read_json(root / "status.json", {})
    project = read_json(root / "project-snapshot.json", {})
    pack = read_json(root / "data-pack-snapshot.json", {})
    resolved = read_json(root / "model-output" / "resolved-run.json", {})
    bindings = {
        role: {
            "filename": binding.get("filename") or Path(str(binding.get("uri", ""))).name,
            "format": binding.get("format"),
            "bytes": binding.get("bytes"),
            "sha256": binding.get("sha256"),
        }
        for role, binding in dict(pack.get("bindings") or {}).items()
    }
    return {
        "schema_version": "value.run-provenance/v1",
        "run_id": run_id,
        "execution_engine": status.get("execution_engine"),
        "python": status.get("python"),
        "started_at": status.get("started_at"),
        "finished_at": status.get("finished_at"),
        "project": {
            "id": project.get("id"), "name": project.get("name"),
            "start_year": project.get("start_year"), "end_year": project.get("end_year"),
        },
        "data_pack": {"id": pack.get("id"), "name": pack.get("name"), "bindings": bindings},
        "modules": resolved.get("modules") or project.get("modules") or {},
        "scientific_parameters": resolved.get("scientific_parameters") or {},
        "runtime_options": resolved.get("runtime_options") or {},
        "parameter_sources": (resolved.get("extensions") or {}).get("parameter_sources")
            or resolved.get("sources") or {},
    }


def ensure_default_pack() -> None:
    if any(path.is_file() for path in PACKS_ROOT.glob("*/manifest.json")):
        return
    manifest = PACKS_ROOT / "value-uk-research-data" / "manifest.json"
    atomic_json(manifest, {
        "schema_version": "value.data-pack/v1", "id": "value-uk-research-data",
        "name": "UK VALUE research data", "country": "GB",
        "timezone": "Europe/London", "created_at": now(), "updated_at": now(),
        "bindings": {},
    })


def binding_issue(
    pack_id: str,
    role: str,
    binding: dict[str, Any],
    slot: dict[str, Any] | None = None,
) -> str | None:
    slot = slot or ROLE_INDEX.get(role)
    if slot is None:
        return "uses an undeclared semantic role"
    declared_format = str(binding.get("format") or "").lower().lstrip(".")
    uri = str(binding.get("uri") or "")
    if not uri:
        return "has no file URI"
    supported_formats = tuple(slot.get("supported_formats") or slot["formats"])
    if declared_format not in supported_formats:
        return (
            f"declares format {declared_format or 'unknown'}; expected "
            f"a shipped runtime parser for {', '.join(supported_formats)}"
        )
    pack_root = (PACKS_ROOT / pack_id).resolve()
    path = Path(uri)
    path = path.resolve() if path.is_absolute() else (pack_root / path).resolve()
    try:
        path.relative_to(pack_root)
    except ValueError:
        return "points outside the data pack"
    if not path.is_file():
        return "points to a missing file"
    checksum = str(binding.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
        return "has no valid SHA-256 provenance"
    return None


def _decorate_dataset_slot(item: dict[str, Any], *, source: str, owner_extension: str | None = None) -> dict[str, Any]:
    role = str(item["role"])
    return {
        **item,
        "source": source,
        "owner_extension": owner_extension,
        "template_available": template_available(role),
        "supported_formats": list(runtime_supported_formats(role, item.get("formats", ()))),
    }


def active_project_dataset_slots(project: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [_decorate_dataset_slot(dict(item), source="base") for item in DATASET_SLOTS]
    try:
        for extension_id in tuple(str(item) for item in project.get("selected_extensions", ())):
            extension = MODULE_REGISTRY.extension_registry.manifest(extension_id)
            rows.extend(
                _decorate_dataset_slot(role.to_dataset_slot(), source="extension", owner_extension=extension_id)
                for role in extension.data_roles
            )
    except (TypeError, ValueError):
        # The draft resolver emits the stable unknown-extension error.
        pass
    return rows


def all_registered_dataset_slots() -> list[dict[str, Any]]:
    rows = [_decorate_dataset_slot(dict(item), source="base") for item in DATASET_SLOTS]
    seen = {str(item["role"]) for item in rows}
    for extension in MODULE_REGISTRY.extension_manifests().values():
        for role in extension.data_roles:
            if role.role in seen:
                continue
            rows.append(_decorate_dataset_slot(role.to_dataset_slot(), source="extension", owner_extension=extension.id))
            seen.add(role.role)
    return rows


def dataset_slot(role: str) -> dict[str, Any] | None:
    return next(
        (item for item in all_registered_dataset_slots() if item["role"] == role),
        None,
    )


def valid_available_roles(
    project: dict[str, Any], pack_id: str, pack: dict[str, Any] | None
) -> tuple[str, ...]:
    if not pack:
        return ()
    slot_by_role = {
        str(slot["role"]): slot for slot in active_project_dataset_slots(project)
    }
    bindings = dict(pack.get("bindings") or {})
    return tuple(sorted(
        role for role, binding in bindings.items()
        if role in slot_by_role
        and isinstance(binding, dict)
        and dict(binding.get("validation") or {}).get("status") != "failed"
        and binding_issue(pack_id, role, binding, slot_by_role[role]) is None
    ))


def resolve_project_draft(project: dict[str, Any]) -> dict[str, Any]:
    pack_id = str(project.get("data_pack_id") or "")
    pack = read_json(PACKS_ROOT / pack_id / "manifest.json") if pack_id else None
    available_roles = set(valid_available_roles(project, pack_id, pack))
    if pack:
        try:
            selection = resolve_zonal_pack_selection(
                project,
                base_pack_root=PACKS_ROOT / pack_id,
                base_manifest=pack,
                data_home=STATE_ROOT,
            )
            if selection.network_manifest is not None:
                available_roles.update(
                    str(role)
                    for role in dict(selection.network_manifest.get("bindings") or {})
                )
        except ValueError:
            # Draft resolution keeps the stable missing-role diagnostics. The
            # readiness endpoint reports the exact missing Network Pack.
            pass
    return resolve_study_draft(
        project,
        registry=MODULE_REGISTRY,
        module_catalog=MODULES,
        base_dataset_slots=DATASET_SLOTS,
        available_data_roles=tuple(sorted(available_roles)),
    )


def list_packs() -> list[dict[str, Any]]:
    ensure_default_pack()
    packs = []
    for manifest_path in PACKS_ROOT.glob("*/manifest.json"):
        try:
            manifest_bytes = manifest_path.read_bytes()
            pack = json.loads(manifest_bytes)
        except (OSError, ValueError):
            continue
        if not isinstance(pack, dict) or not pack:
            continue
        required = [slot["role"] for slot in DATASET_SLOTS if slot.get("required")]
        bindings = pack.get("bindings", {})
        pack["required_count"] = len(required)
        pack["bound_required_count"] = sum(role in bindings for role in required)
        issues = {
            role: issue
            for role in required
            if role in bindings
            if (issue := binding_issue(pack["id"], role, bindings[role]))
        }
        pack["binding_issues"] = issues
        pack["valid_required_count"] = sum(
            role in bindings and role not in issues for role in required
        )
        pack["complete"] = all(role in bindings and role not in issues for role in required)
        installation = read_json(manifest_path.parent / "installation.json")
        if installation:
            pack["installation"] = installation
        pack["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        packs.append(pack)
    return sorted(packs, key=lambda item: item.get("name", ""))


def _list_json(root: Path, filename: str) -> list[dict[str, Any]]:
    rows = [read_json(path) for path in root.glob(f"*/{filename}")]
    return sorted(
        (row for row in rows if isinstance(row, dict) and row),
        key=lambda item: str(item.get("updated_at") or ""), reverse=True,
    )


def list_projects() -> list[dict[str, Any]]:
    rows = _list_json(PROJECTS_ROOT, "project.json")
    result = []
    for project in rows:
        if project.get("revision_sha256"):
            result.append(project)
            continue
        pack = read_object(PACKS_ROOT / str(project.get("data_pack_id")) / "manifest.json")
        try:
            result.append(attach_revision_identity(
                project, MODULE_REGISTRY, _revision_manifest(project, pack)
            ))
        except (ValueError, KeyError):
            result.append(project)
        except Exception as exc:  # noqa: BLE001 - isolate one bad Study (F5-05)
            result.append({**project, "warnings": [_record_warning(
                "GF_STUDY_PRESENTATION_FAILED", f"This Study could not be fully presented ({type(exc).__name__}).",
            )]})
    linked_run_counts: dict[str, int] = {}
    for status_path in RUNS_ROOT.glob("*/status.json"):
        status = read_object(status_path)
        project_id = str(status.get("project_id") or "")
        if project_id:
            linked_run_counts[project_id] = linked_run_counts.get(project_id, 0) + 1
    return [
        {
            **project,
            "linked_run_count": linked_run_counts.get(str(project.get("id") or ""), 0),
        }
        for project in result
    ]


def _revision_manifest(
    project: dict[str, object],
    pack_manifest: dict[str, object],
) -> dict[str, object]:
    """Use the same base-plus-overlay identity at save and preflight time."""

    modules = dict(project.get("modules") or {})
    selected_extensions = {
        str(item) for item in project.get("selected_extensions", ())
    }
    if (
        str(modules.get("balancing") or "")
        != "value-zonal-redispatch-balancing"
        or "value-zonal-redispatch-extension" not in selected_extensions
    ):
        return dict(pack_manifest)
    pack_id = str(project.get("data_pack_id") or "")
    selection = resolve_zonal_pack_selection(
        project,
        base_pack_root=PACKS_ROOT / pack_id,
        base_manifest=pack_manifest,
        data_home=STATE_ROOT,
    )
    return selection.revision_manifest


def _value_101_origin_extensions(record: dict[str, Any]) -> dict[str, object]:
    if not is_value_101_record(record):
        return {}
    return {
        "value_101": dict(
            dict(record.get("extensions") or {}).get("value_101") or {}
        )
    }


def _save_value_101_project(
    candidate: dict[str, object],
) -> tuple[dict[str, object], dict[str, Any]]:
    with STUDY_LIFECYCLE_LOCK:
        return _save_value_101_project_locked(candidate)


def _save_value_101_project_locked(
    candidate: dict[str, object],
) -> tuple[dict[str, object], dict[str, Any]]:
    if not is_value_101_record(candidate):
        raise ValueError("VALUE 101 Study origin metadata is missing or invalid")
    validation = validate_project(dict(candidate))
    if not validation["valid"]:
        raise ValueError(str(validation["errors"][0]))
    normalised = dict(validation["normalised_project"])
    project_id = slug(str(normalised.get("id") or "value-101-study"), "project")
    normalised["id"] = project_id
    pack_id = str(normalised.get("data_pack_id") or "")
    pack_manifest = read_json(PACKS_ROOT / pack_id / "manifest.json", {})
    if not pack_manifest:
        raise ValueError(f"VALUE 101 data pack is not installed: {pack_id}")
    project_path = PROJECTS_ROOT / project_id / "project.json"
    if project_path.exists():
        raise ValueError(f"VALUE 101 Study already exists: {project_id}")
    if study_id_is_reserved(
        project_id, projects_root=PROJECTS_ROOT, trash_root=TRASH_ROOT
    ):
        raise ValueError(
            f"Restore the trashed VALUE 101 Study before reusing its ID: {project_id}"
        )
    saved = save_project_revision(
        PROJECTS_ROOT / project_id,
        normalised,
        MODULE_REGISTRY,
        _revision_manifest(normalised, pack_manifest),
    )
    return saved, validation


def _value_101_reset_records() -> tuple[list[Path], list[Path]]:
    study_paths = [
        path.parent
        for path in sorted(PROJECTS_ROOT.glob("*/project.json"))
        if is_value_101_record(read_json(path, {}))
    ]
    run_paths = [
        path.parent
        for path in sorted(RUNS_ROOT.glob("*/status.json"))
        if is_value_101_record(read_json(path, {}))
    ]
    return study_paths, run_paths


def _move_value_101_reset_records(
    study_paths: list[Path],
    run_paths: list[Path],
) -> dict[str, object]:
    report = move_value_101_records_to_trash(
        study_paths,
        run_paths,
        projects_root=PROJECTS_ROOT,
        runs_root=RUNS_ROOT,
        trash_root=TRASH_ROOT,
    )
    return {
        **report,
        "schema_version": "value.101-reset/v1",
        "trash_schema_version": report["schema_version"],
    }


def present_run(run: dict[str, Any]) -> dict[str, Any]:
    """Add UI-compatible aliases without rewriting persisted research results."""
    if run.get("id"):
        run_root = RUNS_ROOT / str(run["id"])
        evidence_path = run_root / "model-output" / "module-events.jsonl"
        if not evidence_path.is_file():
            evidence_path = run_root / "model-output" / "orchestrator-events.jsonl"
        if evidence_path.exists():
            completed_years: set[int] = set()
            evidence: dict[str, dict[str, Any]] = {}
            try:
                for line in evidence_path.read_text(encoding="utf-8").splitlines():
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        continue
                    year = event.get("year")
                    year = year if isinstance(year, int) and not isinstance(year, bool) else None
                    module_id = str(event.get("module_id") or "")
                    if module_id:
                        row = evidence.setdefault(module_id, {
                            "version": event.get("module_version"),
                            "actions": 0,
                            "years": set(),
                        })
                        row["actions"] += 1
                        if year is not None:
                            row["years"].add(year)
                    if year is not None and (
                        event.get("action") == "pipeline.complete_year"
                        or event.get("stage") == "state_transition.apply"
                    ):
                        completed_years.add(year)
                run["module_evidence"] = {
                    module_id: {
                        "version": row["version"],
                        "actions": row["actions"],
                        "years": sorted(row["years"]),
                    }
                    for module_id, row in evidence.items()
                }
                if completed_years and run.get("status") == "running":
                    run["completed_years"] = len(completed_years)
                    run["current_stage"] = (
                        f"Completed {max(completed_years)}; preparing the next annual state"
                    )
            except (OSError, ValueError, json.JSONDecodeError):
                run.setdefault("warnings", []).append({
                    "schema_version": "value.warning/v1",
                    "code": "GF_MODULE_EVIDENCE_READ_WARNING",
                    "category": "artifact",
                    "severity": "warning",
                    "message": "Module progress evidence is incomplete or unreadable.",
                })
        # Historical completed bundles are immutable.  Some dynamic-policy runs
        # were packaged before retained comparison was correctly classified as
        # informational.  Present the scenario gate separately from the raw
        # embedded report, based only on its preserved execution, contract and
        # analytical evidence; never rewrite that report on disk.
        validation_path = run_root / "model-output" / str(
            run.get("scientific_validation_artifact")
            or "validation/scientific-validation.json"
        )
        validation = read_object(validation_path)
        storage_policy = str((run.get("modules") or {}).get("storage_cost") or "")
        alternative_policy = storage_policy in {
            "dynamic-annual-storage-cost", "user-formula-storage-cost"
        }
        role = validation.get("retained_numerical_comparison_role")
        if not role:
            role = (
                "informational_scenario_difference"
                if alternative_policy
                else "required_reproduction_gate"
            )
        retained_status = validation.get("retained_numerical_comparison_status")
        if alternative_policy and retained_status == "failed":
            retained_status = "expected_difference"
        evidence_passed = all(
            validation.get(field) == "passed"
            for field in (
                "execution_status",
                "contract_validation_status",
                "analytical_mechanism_status",
            )
        )
        scenario_status = validation.get("scientific_validation_status")
        if alternative_policy and evidence_passed and run.get("mode") in {"full", "two_year"}:
            scenario_status = "passed"
        run["scientific_scenario_status"] = scenario_status or "not_evaluated"
        run["retained_comparison_role"] = role
        run["retained_numerical_comparison_status"] = retained_status or "not_evaluated"
    for result in run.get("results", []):
        if "initial_pipeline" not in result and "pipeline_next_year" in result:
            result["initial_pipeline"] = result["pipeline_next_year"]
    run_root = RUNS_ROOT / str(run.get("id") or "")
    cancel_request = read_json(run_root / "cancel-request.json") if run.get("id") else None
    if isinstance(cancel_request, Mapping) and cancel_request.get("schema_version") == "value.cancel-request/v1":
        run["cancel_requested_at"] = cancel_request.get("requested_at")
        if run.get("status") in {"queued", "snapshotting", "running"}:
            # Cancellation is a request file read by the worker (P0-3 S2);
            # the persisted status stays with the worker until it stops.
            run["persisted_status"] = run.get("status")
            run["status"] = "cancel_requested"
    if run.get("id") and run_root.is_dir():
        liveness, worker = worker_liveness(run_root, run)
        run["worker_liveness"] = liveness
        if worker:
            run["worker"] = worker
    selected_modules = (run.get("modules") or {}).values()
    run["recovery"] = {
        **recovery_capability(selected_modules),
        "latest_safe_point": latest_safe_recovery_point(run_root / "model-output"),
    }
    project_id = str(run.get("project_id") or "")
    frozen_project = read_json(run_root / "input-snapshot" / "project.json", {})
    run["recorded_project_revision_sha256"] = (
        frozen_project.get("revision_sha256")
        if isinstance(frozen_project, Mapping) and frozen_project.get("id") == project_id
        else None
    )
    run["source_study_status"] = source_study_status(project_id)
    return run


def source_study_status(project_id: str) -> str:
    if (PROJECTS_ROOT / project_id / "project.json").is_file():
        return "active"
    trashed = {
        str(entry.get("study_id") or "")
        for entry in list_study_trash(PROJECTS_ROOT, RUNS_ROOT, TRASH_ROOT)
    }
    return "trash" if project_id in trashed else "missing"


def _safe_present(row: dict[str, Any]) -> dict[str, Any]:
    """present_run for one listed record; a failure keeps the raw record (F5-05)."""
    try:
        return present_run(dict(row))
    except Exception as exc:  # noqa: BLE001 - isolate one bad run from the listing
        print(f"VALUE: run {row.get('id')!r} could not be presented: {type(exc).__name__}: {exc}", file=sys.stderr)
        warnings = row.get("warnings") if isinstance(row.get("warnings"), list) else []
        return {**row, "warnings": [*warnings, _record_warning(
            "GF_RUN_PRESENTATION_FAILED", "This run's evidence could not be read; its stored status is shown.",
        )]}


def list_runs(*, compact: bool = True) -> list[dict[str, Any]]:
    # Historical/reference files remain immutable on disk.  The normal website
    # lists only runs launched through the v2 application service; reference
    # comparison is an explicit CLI workflow, never a selectable production path.
    rows = [
        _safe_present(row)
        for row in _list_json(RUNS_ROOT, "status.json")
        if row.get("project_id")
        and row.get("status")
        and row.get("execution_engine") in ORCHESTRATOR_ENGINES
    ]
    if not compact:
        return rows
    for row in rows:
        results = list(row.get("results") or [])
        row["result_year_count"] = len(results)
        row["results"] = []
    return rows


def _review_frozen_recovery(root: Path, mode: str):
    return review_frozen_recovery(
        root, mode, registry=MODULE_REGISTRY, module_catalog=MODULES, dataset_slots=DATASET_SLOTS,
        current_execution=lambda: current_execution(source_root=PROJECT_ROOT, data_home=STATE_ROOT),
        verify_archive=lambda record: verify_execution_bundle(record, archive_root=STATE_ROOT / "execution-archives"),
    )


def validate_project(project: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    error_events: list[dict[str, Any]] = []
    warnings: list[str] = []
    warning_events: list[dict[str, str]] = []
    pack_id = str(project.get("data_pack_id", ""))
    pack = read_json(PACKS_ROOT / pack_id / "manifest.json") if pack_id else None
    if not pack:
        errors.append("Select an existing data pack")
        error_events.append({
            "code": "GF_DATA_PACK_UNKNOWN", "scope": "data",
            "message": "Select an existing data pack",
        })
    start_year, end_year = project.get("start_year", 2025), project.get("end_year", 2034)
    if not isinstance(start_year, int) or not isinstance(end_year, int):
        errors.append("Start and end years must be integers")
    elif end_year < start_year:
        errors.append("The end year cannot be earlier than the start year")
    draft = resolve_project_draft(project)
    error_events.extend(dict(item) for item in draft["errors"])
    errors.extend(str(item["message"]) for item in draft["errors"])
    selected_modules = dict(draft["normalised_project"].get("modules") or {})
    selected_ids = set(selected_modules.values())
    if any(
        module.get("id") in selected_ids and module.get("status") != "ready"
        for module in MODULES
    ):
        warnings.append("One or more selected modules are not ready to run")
        warning_events.append({
            "schema_version": "value.warning/v1",
            "code": "GF_MODULE_NOT_READY",
            "category": "contract",
            "severity": "warning",
            "message": "One or more selected modules are not ready to run.",
        })
    resolved_parameters = None
    if pack and not errors:
        try:
            resolved = resolve_scheme_c_parameters(
                PACKS_ROOT / pack_id,
                project.get("parameters") or {},
                project.get("runtime_options") or {},
            )
            resolved_parameters = resolved.to_dict()
            warnings.extend(resolved.warnings)
            warning_events.extend(dict(item) for item in resolved.warning_events)
        except ParameterValidationError as exc:
            errors.append(str(exc))
    return {
        "valid": not errors,
        "errors": errors,
        "error_events": error_events,
        "warnings": warnings,
        "warning_events": warning_events,
        "resolved_parameters": resolved_parameters,
        "draft_resolution": draft,
        "normalised_project": draft["normalised_project"],
    }


def _error_body(message: str, code: str, **extra: Any) -> dict[str, Any]:
    return {"error": message, "error_code": code, **extra}


def map_request_exception(exc: BaseException) -> tuple[int, dict[str, Any], dict[str, str]]:
    """The C1 exception table (ordered); P0-1/P0-2 add their entries here.

    QueryParameterError 400 | UnsupportedMediaType 415 |
    DataMappingError/DataPackCloneError own status |
    LockTimeout 503 + Retry-After | UnicodeError 500 (corrupt stored record) |
    ValueError 400 | anything else 500 through public_failure (never an
    internal path or traceback in the body).
    """

    if isinstance(exc, QueryParameterError):
        return 400, _error_body(str(exc), "GF_QUERY_INVALID"), {}
    if isinstance(exc, UnsupportedMediaType):
        return 415, _error_body(str(exc), UnsupportedMediaType.code), {}
    if isinstance(exc, (DataMappingError, DataPackCloneError)):
        return int(exc.status), _error_body(str(exc), str(exc.code)), {}
    code = getattr(exc, "code", None)
    if isinstance(exc, (ModuleQuarantinedError, ContractError, ExtensionBundleError,
                        ModuleInstallationError, ExecutionArchiveError)) and isinstance(code, str) and code:
        # P0-2 error-code table (gridform_core.module_quarantine.ERROR_CODE_STATUS).
        extra: dict[str, Any] = {}
        entries = getattr(exc, "entries", ())
        if entries:
            extra["quarantine"] = [entry.to_dict() for entry in entries]
        return status_for_code(code), _error_body(str(exc), code, **extra), {}
    if isinstance(exc, LockTimeout):
        return 503, _error_body(
            "VALUE is busy with another change to the same records; retry shortly.",
            "GF_LOCK_TIMEOUT",
        ), {"Retry-After": "5"}
    if isinstance(exc, UnicodeError):
        failure = public_failure(exc)
        return 500, _error_body(failure.message, failure.code, error_category=failure.category), {}
    if isinstance(exc, ValueError):
        return 400, _error_body(str(exc), "GF_REQUEST_INVALID"), {}
    failure = public_failure(exc)
    return 500, _error_body(failure.message, failure.code, error_category=failure.category), {}


def health_degradation() -> tuple[str, list[dict[str, Any]]]:
    """Backend status and grouped degraded reasons: quarantined local module
    entries and a stale catalogue (codes and counts only; no IDs or paths)."""

    reasons = degraded_reasons(
        MODULE_REGISTRY, extra=[CATALOG_STALE["code"]] if CATALOG_STALE else [],
        entries=module_record_entries(),
    )
    return ("degraded" if reasons else "ok"), reasons


def health_payload(*, full: bool) -> dict[str, Any]:
    """/api/health: the reduced payload without a session (C3), all of it with one."""

    runtime = capability_matrix(selected_module_ids=("value-bid-at-cost-psm",))
    status, degraded = health_degradation()
    reduced = {
        "ok": True,
        "service": "value-modular-local",
        "version": APPLICATION_VERSION,
        "python": sys.version.split()[0],
        "authoritative_runtime_compatible": runtime["capabilities"][VALUE_NATIVE]["available"],
        "session_required": True,
        "status": status,
        "degraded_reasons": [{"code": str(item.get("code")), "count": int(item.get("count", 1))} for item in degraded],
    }
    if not full:
        return reduced
    return {
        **reduced,
        "time": now(),
        "python_executable": sys.executable,
        "runtime_capability": VALUE_NATIVE,
        "runtime_capabilities": runtime,
        "degraded_details": degraded,
        "module_quarantine": [
            {key: row[key] for key in ("kind", "id", "manifest_file", "error_code", "error_type")}
            for row in module_quarantine_payload()["entries"]
        ],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "VALUELocal/0.5"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    session_authenticated = False

    def end_headers(self) -> None:
        # Every response, including http.server's own send_error pages.
        for name, value in SECURITY_RESPONSE_HEADERS:
            self.send_header(name, value)
        super().end_headers()

    def _headers(self, status: int = 200, *, error_code: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if error_code:
            self.send_header("X-VALUE-Error-Code", error_code)
        self.end_headers()

    def _json(self, payload: Any, status: int = 200) -> None:
        code = payload.get("error_code") if isinstance(payload, dict) and int(status) >= 400 else None
        self._headers(status, error_code=str(code) if code else None)
        try:
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        except ConnectionError:
            # Browsers may cancel an obsolete polling request during reload or
            # reconnect.  That is a client disconnect, not a model failure.
            return

    def _artifact(self, path: Path) -> None:
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self.wfile.write(chunk)

    def _bytes(self, data: bytes, media_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise ValueError("JSON request body too large")
        value = json.loads(self.rfile.read(length).decode("utf-8") if length else "{}")
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _mapping_service(self) -> DataMappingService:
        # A fresh catalogue includes modules/extensions installed since startup;
        # stage/review identity and the shared lifecycle lock live outside it.
        return DataMappingService(
            packs_root=PACKS_ROOT, staging_root=IMPORT_STAGING_ROOT / "csv-mapping",
            projects_root=PROJECTS_ROOT, trash_root=TRASH_ROOT,
            dataset_slots=all_registered_dataset_slots(), lifecycle_lock=STUDY_LIFECYCLE_LOCK,
        )

    def _small_upload_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_MAPPING_UPLOAD_BYTES:
            raise DataMappingError("GF_UPLOAD_SIZE", "Provide a nonempty file no larger than 32 MiB.", 413)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise DataMappingError("GF_UPLOAD_INCOMPLETE", "Upload body is incomplete.")
        return raw

    # -- request entry (P0_CONVENTIONS section 4, C1) -------------------------
    response_started = False

    def send_response(self, code: int, message: str | None = None) -> None:
        self.response_started = True
        super().send_response(code, message)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch(self._route_get)

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch(self._route_post)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._dispatch(self._route_options)

    def _guard(self) -> bool:
        """P0-1 request guard (backend.api_security.evaluate); answers 4xx itself.

        Returns True when the request may be routed.  A rejected request's
        body (up to 2 MiB) is read first so the client sees the answer
        instead of a connection reset; a larger or unreadable body closes the
        connection after the answer.
        """

        self.session_authenticated = False
        decision = evaluate_request(
            self.command, urlparse(self.path).path, self.headers,
            bound_port=int(self.server.server_address[1]),
            token=getattr(self.server, "session_token", None),
        )
        if decision.allowed:
            self.session_authenticated = decision.authenticated
            return True
        drain = drainable_length(self.headers)
        if drain:
            try:
                self.rfile.read(drain)
            except OSError:
                drain = None
        if drain is None:
            self.close_connection = True
        payload = json.dumps(_error_body(decision.message, decision.code), ensure_ascii=False).encode("utf-8")
        self.send_response(int(decision.status or 403))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-VALUE-Error-Code", decision.code)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except ConnectionError:
            self.close_connection = True
        return False

    def _dispatch(self, route: Any) -> None:
        self.response_started = False  # reset for every request on the connection
        try:
            if self._guard():
                route()
        except Exception as exc:  # the single exception exit of every request
            self._send_mapped_error(exc)

    def _send_mapped_error(self, exc: BaseException) -> None:
        if isinstance(exc, ConnectionError):
            self.close_connection = True
            return
        if self.response_started:
            # Headers (and maybe part of a body) are out: a second response
            # would corrupt the stream, so only close the connection.
            traceback.print_exc()
            self.close_connection = True
            return
        status, payload, headers = map_request_exception(exc)
        if status >= 500 and status != 503:
            traceback.print_exc()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if payload.get("error_code"):
            self.send_header("X-VALUE-Error-Code", str(payload["error_code"]))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        except ConnectionError:
            self.close_connection = True

    def _route_options(self) -> None:
        self._headers(HTTPStatus.NO_CONTENT)

    def _route_get(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        overlay_file = re.fullmatch(re.escape(DATA_WORKBENCH_API_BASE) + r"/overlay-candidates/([^/]+)/roles/([^/]+)/file", route)
        if overlay_file:
            try:
                raw, filename, media_type = self.server.data_workbench_api.service.overlay_editor.download_role(  # type: ignore[attr-defined]
                    overlay_file[1], unquote(overlay_file[2]), str(query.get("candidate_id", [""])[0]),
                )
                self._bytes(raw, media_type, filename)
            except (OSError, ValueError, KeyError) as exc:
                self._json({"error": str(exc), "error_code": "DW_API_INVALID"}, 409)
            return
        mapping_catalog = re.fullmatch(r"/api/data-packs/([^/]+)/csv-mapping/catalog", route)
        if mapping_catalog:
            try:
                self._json(self._mapping_service().catalog(unquote(mapping_catalog[1])))
            except (DataMappingError, DataPackCloneError) as exc:
                self._json({"error": str(exc), "error_code": exc.code}, exc.status)
            except (OSError, ValueError) as exc:
                self._json({"error": str(exc)}, 400)
            return
        if route.startswith(DATA_WORKBENCH_API_BASE):
            status, payload = self.server.data_workbench_api.handle("GET", route, None)  # type: ignore[attr-defined]
            self._json(payload, status)
            return
        if route == "/api/health":
            self._json(health_payload(full=self.session_authenticated))
        elif route == "/api/workspace":
            runtime_matrix = capability_matrix(selected_module_ids=("value-bid-at-cost-psm",))
            self._json({"modules": MODULES, "dataset_slots": DATASET_SLOTS,
                        "frontend_contract_version": FRONTEND_CONTRACT_VERSION,
                        "module_slots": module_slot_catalog(MODULE_REGISTRY, MODULES),
                        "extensions": extension_catalogue(
                            MODULE_REGISTRY,
                            installation_records=extension_installation_records(),
                        ),
                        "extension_installations": list_extension_installations(external_modules_root()),
                        "module_installations": list_module_installations(),
                        "module_quarantine": module_quarantine_payload(),
                        "data_packs": list_packs(), "projects": list_projects(),
                        "study_trash": list_study_trash(PROJECTS_ROOT, RUNS_ROOT, TRASH_ROOT),
                        "runs": list_runs(), "architecture_version": "value.contracts/v2",
                        "runtime": {
                            "python": sys.version.split()[0],
                            "compatible": runtime_matrix["capabilities"][VALUE_NATIVE]["available"],
                            "selected_capability": VALUE_NATIVE,
                            "capabilities": runtime_matrix["capabilities"],
                            "recovery": recovery_capability(("value-bid-at-cost-psm",)),
                        }})
        elif route == "/api/data-packs":
            self._json({"data_packs": list_packs()})
        elif route == "/api/tutorials/value-101":
            self._json(value_101_descriptor(
                installed_pack_ids={
                    pack_id
                    for pack_id in (*VALUE_101_PACK_IDS, VALUE_101_NETWORK_PACK_ID)
                    if (PACKS_ROOT / pack_id / "manifest.json").is_file()
                }
            ))
        elif route.startswith("/api/data-contracts/") and route.endswith("/template"):
            role = unquote(route.strip("/").split("/")[2])
            slot = dataset_slot(role)
            if slot is None:
                self._json({"error": "unknown data role", "error_code": "GF_DATA_ROLE_UNKNOWN"}, 404); return
            try:
                data, media_type, filename = template_for_role(role, slot["formats"])
            except ValueError as exc:
                self._json({"error": str(exc), "error_code": "GF_DATA_TEMPLATE_NOT_AVAILABLE"}, 404); return
            self._bytes(data, media_type, filename); return
        elif route.startswith("/api/data-packs/") and route.endswith("/validation"):
            pack_id = slug(route.strip("/").split("/")[2], "pack")
            pack_root = PACKS_ROOT / pack_id
            manifest = read_json(pack_root / "manifest.json")
            if not manifest:
                self._json({"error": "data pack not found"}, 404); return
            selected_extensions = tuple(
                item for item in query.get("extensions", [""])[0].split(",") if item
            )
            slots = [dict(item, source="base") for item in DATASET_SLOTS]
            try:
                slots.extend(
                    dict(item, source="extension")
                    for item in MODULE_REGISTRY.extension_registry.conditional_dataset_slots(selected_extensions)
                )
            except ValueError as exc:
                self._json({"error": str(exc), "error_code": "GF_EXTENSION_UNKNOWN"}, 400); return
            self._json(validate_data_pack(pack_root, manifest, slots))
        elif route.startswith("/api/data-packs/") and route.endswith("/preview"):
            pack_id = slug(route.strip("/").split("/")[2], "pack")
            role = query.get("role", [""])[0]
            slot = dataset_slot(role)
            manifest = read_json(PACKS_ROOT / pack_id / "manifest.json")
            if not manifest or slot is None:
                self._json({"error": "data pack or role not found"}, 404); return
            try:
                self._json(preview_binding(PACKS_ROOT / pack_id, manifest, slot))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc), "error_code": "GF_DATA_PREVIEW_INVALID"}, 400)
        elif route.startswith("/api/data-packs/") and route.endswith("/missing-checklist"):
            pack_id = slug(route.strip("/").split("/")[2], "pack")
            manifest = read_json(PACKS_ROOT / pack_id / "manifest.json")
            if not manifest:
                self._json({"error": "data pack not found"}, 404); return
            selected_extensions = tuple(
                item for item in query.get("extensions", [""])[0].split(",") if item
            )
            try:
                slots = active_project_dataset_slots({"selected_extensions": selected_extensions})
            except ValueError as exc:
                self._json({"error": str(exc)}, 400); return
            checklist = missing_input_checklist(slots, manifest)
            if query.get("format", ["json"])[0] == "json":
                data = (json.dumps(checklist, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
                self._bytes(data, "application/json; charset=utf-8", f"{pack_id}-missing-input-checklist.json"); return
            self._json(checklist)
        elif route == "/api/projects":
            self._json({"projects": list_projects()})
        elif route == "/api/study-trash":
            self._json({
                "schema_version": "value.study-trash-list/v1",
                "studies": list_study_trash(PROJECTS_ROOT, RUNS_ROOT, TRASH_ROOT),
            })
        elif route == "/api/runs":
            self._json({"runs": list_runs()})
        elif route == "/api/comparisons":
            run_ids = [item for item in query.get("runs", [""])[0].split(",") if item]
            roots = [_run_root(item) for item in run_ids]
            if any(root is None for root in roots):
                self._json({"error": "one or more comparison runs were not found"}, 404); return
            comparison = compare_run_summaries([build_run_summary(root) for root in roots if root])
            if query.get("format", ["json"])[0] == "csv":
                data = comparison_csv(comparison).encode("utf-8-sig")
                self._bytes(data, "text/csv; charset=utf-8", "value-run-comparison.csv"); return
            self._json(comparison)
        elif route == "/api/retention":
            def directory_bytes(root: Path) -> int:
                return sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.exists() else 0
            self._json({
                "schema_version": "value.retention-dashboard/v1",
                "active_run_bytes": directory_bytes(RUNS_ROOT),
                "archive_bytes": directory_bytes(ARCHIVES_ROOT),
                "trash_bytes": directory_bytes(TRASH_ROOT),
                "trash_policy": "recoverable local trash; no automatic permanent deletion in public beta",
                "archives": [path.name for path in sorted(ARCHIVES_ROOT.glob("*.zip"))],
                "trash_items": [path.name for path in sorted(TRASH_ROOT.glob("*")) if path.is_dir()],
            })
        elif route == "/api/modules":
            self._json({
                "schema_version": "value.module-catalog/v2",
                "modules": MODULES,
                "required_slots": list(REQUIRED_MODULE_SLOTS),
                "module_quarantine": module_quarantine_payload(),
            })
        elif route.startswith("/api/modules/") and route.endswith(("/authoring", "/template")):
            parts = route.strip("/").split("/")
            module_id = unquote(parts[2]) if len(parts) == 4 else ""
            if module_id not in MODULE_REGISTRY.manifests():
                self._json({"error": "Module not found in the active registry", "error_code": "GF_MODULE_UNKNOWN"}, 404); return
            try:
                if parts[3] == "authoring":
                    self._json(module_authoring_detail(
                        MODULE_REGISTRY, module_id,
                        installation_records=list_module_installations(),
                    ))
                else:
                    template_id = query.get("module_id", [None])[0]
                    version = query.get("version", ["0.1.0"])[0]
                    content = module_authoring_template(
                        MODULE_REGISTRY, module_id, template_id=template_id, version=version,
                    )
                    self._bytes(content, "application/zip", "value-module-source-template.zip")
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self._json({"error": str(exc), "error_code": "GF_MODULE_AUTHORING_UNAVAILABLE"}, 400)
        elif route == "/api/module-installations":
            self._json({
                "schema_version": "value.module-installation-list/v1",
                "installations": list_module_installations(),
                "execution_boundary": "in_process_trusted_python",
            })
        elif route == "/api/extensions":
            self._json({
                "schema_version": "value.extension-installation-list/v1",
                "extensions": extension_catalogue(
                    MODULE_REGISTRY,
                    installation_records=extension_installation_records(),
                ),
                "installations": list_extension_installations(external_modules_root()),
                "module_quarantine": module_quarantine_payload(),
            })
        elif route == "/api/parameters":
            self._json(parameter_schema())
        elif route.startswith("/api/runs/") and route.endswith("/extensions/artifacts"):
            parts = route.strip("/").split("/")
            root = _run_root(unquote(parts[2])) if len(parts) == 5 else None
            if root is None:
                self._json({"error": "Run not found", "error_code": "GF_RUN_NOT_FOUND"}, 404); return
            try:
                self._json(query_extension_artifacts(root, {key: values[0] for key, values in query.items()}))
            except (ValueError, TypeError, KeyError) as exc:
                self._json({"error": str(exc), "error_code": "GF_EXTENSION_QUERY_INVALID"}, 400)
        elif route.startswith("/api/runs/"):
            parts = route.strip("/").split("/")
            if len(parts) < 3:
                self._json({"error": "run not found"}, 404); return
            run_id = parts[2]
            root = _run_root(run_id)
            if root is None:
                self._json({"error": "run not found"}, 404); return
            if len(parts) == 3:
                self._json(present_run(read_json(root / "status.json", {}))); return
            resource = parts[3]
            if resource == "results" and len(parts) == 5 and parts[4] == "vre-curtailment":
                try:
                    if any(len(values) != 1 for values in query.values()):
                        raise ValueError("Repeated result query fields are not allowed")
                    self._json(query_vre_curtailment_results(root, {key: values[0] for key, values in query.items()}))
                except (ValueError, OSError, sqlite3.DatabaseError) as exc:
                    code = "GF_RESULT_DIMENSION_UNAVAILABLE" if "GF_RESULT_DIMENSION_UNAVAILABLE" in str(exc) else "GF_RESULT_QUERY_INVALID"
                    self._json({"error": str(exc), "error_code": code}, 400)
                return
            if resource == "reproduction-capability" and len(parts) == 4:
                self._json(assess_run_reproduction(root, MODULE_REGISTRY)); return
            if resource == "summary" and len(parts) == 4:
                self._json(build_run_summary(root)); return
            if resource == "replay-exports" and len(parts) == 5:
                try:
                    job = read_replay_export_job(root, parts[4])
                except (LookupError, ValueError) as exc:
                    self._json({"error": str(exc)}, 404); return
                if job.get("status") == "completed":
                    artifact = Path(str(job.get("artifact_path") or ""))
                    job["download_url"] = (
                        f"/api/runs/{run_id}/artifacts/"
                        + artifact.relative_to(root).as_posix()
                    )
                self._json(job); return
            if resource == "domains":
                try:
                    if len(parts) == 5 and parts[4] == "capabilities":
                        self._json(domain_result_capabilities(root)); return
                    if len(parts) != 6:
                        self._json({"error": "unknown optional-domain result resource"}, 404); return
                    domain, query_name = parts[4], parts[5]
                    year = _optional_integer_query(query, "year")
                    if domain in {"network", "ac"} and year is None:
                        self._json({"error": "year is required"}, 400); return
                    if domain == "network" and query_name == "summary":
                        self._json(query_network_summary(root, year=year)); return
                    if domain == "network" and query_name == "periods":
                        self._json(query_network_periods(
                            root, year=year,
                            limit=_integer_query(query, "limit", 48),
                            offset=_integer_query(query, "offset", 0),
                        )); return
                    if domain == "network" and query_name == "branches":
                        self._json(query_network_branches(
                            root, year=year,
                            period_id=query.get("period_id", [None])[0],
                            branch_id=query.get("branch_id", [None])[0],
                            limit=_integer_query(query, "limit", 100),
                            offset=_integer_query(query, "offset", 0),
                        )); return
                    if domain == "ac" and query_name == "results":
                        self._json(query_ac_results(
                            root, year=year,
                            limit=_integer_query(query, "limit", 48),
                            offset=_integer_query(query, "offset", 0),
                        )); return
                    if domain == "hydrology" and query_name == "summary":
                        capabilities = domain_result_capabilities(root)
                        self._json({
                            "schema_version": "value.hydrology-result-query/v1",
                            "identity": capabilities["identity"],
                            **capabilities["capabilities"]["hydrology"],
                            "values": None,
                        }); return
                    if domain == "expansion" and query_name == "summary":
                        self._json(query_expansion_summary(root)); return
                    if domain == "expansion" and query_name == "events":
                        self._json(query_expansion_events(
                            root,
                            year=year,
                            event_type=query.get("event_type", [None])[0],
                            limit=_integer_query(query, "limit", 100),
                            offset=_integer_query(query, "offset", 0),
                        )); return
                    self._json({"error": "unknown optional-domain result resource"}, 404); return
                except DomainResultError as exc:
                    self._json({"error": str(exc), "error_code": "GF_DOMAIN_RESULT_UNAVAILABLE"}, 409); return
                except (OSError, ValueError, KeyError, sqlite3.DatabaseError, json.JSONDecodeError) as exc:
                    self._json({"error": str(exc), "error_code": "GF_DOMAIN_RESULT_INVALID"}, 400); return
            if resource == "planning" and len(parts) == 5:
                planning_dir = root / "model-output" / "planning"
                native_database = planning_dir / "project-index.sqlite"
                if parts[4] == "summary":
                    summary = read_json(planning_dir / "summary.json")
                    if not summary and native_database.is_file():
                        summary = query_index_summary(native_database)
                    self._json(summary if summary else {
                        "schema_version": "value.planning-ledger/v1", "years": []
                    }); return
                database = planning_dir / "pipeline.sqlite"
                if not database.is_file() and not native_database.is_file():
                    self._json({"error": "planning ledger is not available"}, 404); return
                if parts[4] == "projects":
                    query_function = query_projects if database.is_file() else query_index_projects
                    self._json(query_function(
                        database if database.is_file() else native_database,
                        limit=_integer_query(query, "limit", 50),
                        offset=_integer_query(query, "offset", 0),
                        technology=query.get("technology", [None])[0],
                        region=query.get("region", [None])[0],
                        outcome=query.get("outcome", [None])[0],
                        search=query.get("search", [None])[0],
                    )); return
                if parts[4] == "events":
                    query_function = query_events if database.is_file() else query_index_events
                    self._json(query_function(
                        database if database.is_file() else native_database,
                        limit=_integer_query(query, "limit", 50),
                        offset=_integer_query(query, "offset", 0),
                        year=_optional_integer_query(query, "year"),
                        event_type=query.get("event_type", [None])[0],
                        project_id=query.get("project_id", [None])[0],
                    )); return
            if resource == "market" and len(parts) == 5:
                database = root / "model-output" / "market" / "market.sqlite"
                market_resource = parts[4]
                legacy_jsonl = legacy_staged_market_available(root)
                if not database.is_file() and not legacy_jsonl:
                    self._json({"error": "market ledger is not available"}, 404); return
                try:
                    if market_resource == "capabilities":
                        if database.is_file():
                            capabilities = market_replay_capabilities(database)
                            capabilities["legacy_staged_market_jsonl"] = legacy_jsonl
                            capabilities["legacy_jsonl_resource"] = (
                                "legacy-periods" if legacy_jsonl else None
                            )
                            self._json(capabilities); return
                        self._json({
                            "schema_version": "value.market-replay-capabilities/v1",
                            "ledger_schema_version": "legacy.staged-market-jsonl",
                            "legacy_staged_market_jsonl": True,
                            "legacy_jsonl_resource": "legacy-periods",
                            "period_summary": True,
                            "bid_replay_available": False,
                            "missing_reason": None,
                        }); return
                    if legacy_jsonl and (
                        market_resource == "legacy-periods"
                        or (market_resource == "periods" and not database.is_file())
                    ):
                        year = _optional_integer_query(query, "year")
                        period_from = _optional_integer_query(query, "period_from")
                        period_to = _optional_integer_query(query, "period_to")
                        if year is None or period_from is None or period_to is None:
                            self._json({
                                "error": "legacy market replay requires year, period_from and period_to"
                            }, 400); return
                        self._json(query_legacy_staged_market_jsonl(
                            root,
                            year=year,
                            period_from=period_from,
                            period_to=period_to,
                            limit=_integer_query(query, "limit", 50),
                            offset=_integer_query(query, "offset", 0),
                        )); return
                    if not database.is_file():
                        self._json({
                            "error": "this legacy run exposes only bounded period records"
                        }, 409); return
                    if market_resource == "dispatch":
                        year = _optional_integer_query(query, "year")
                        if year is None:
                            self._json({"error": "year is required"}, 400); return
                        self._json(query_dispatch_timeline(
                            database,
                            year=year,
                            resolution=query.get("resolution", ["daily"])[0],
                            start_period=_optional_integer_query(query, "start_period"),
                            end_period=_optional_integer_query(query, "end_period"),
                            period_from=_optional_integer_query(query, "period_from"),
                            period_to=_optional_integer_query(query, "period_to"),
                            limit=_integer_query(query, "limit", 500),
                            offset=_integer_query(query, "offset", 0),
                        )); return
                    if market_resource == "auction":
                        year = _optional_integer_query(query, "year")
                        period = _optional_integer_query(query, "period")
                        stage = query.get("stage", [""])[0]
                        if year is None or period is None or not stage:
                            self._json({"error": "year, period and stage are required"}, 400); return
                        self._json(query_auction_view(
                            database, year=year, period=period, stage=stage,
                        )); return
                    if market_resource == "vre-summary":
                        self._json(query_vre_curtailment_summary(database)); return
                    if market_resource == "vre-timeline":
                        year = _optional_integer_query(query, "year")
                        if year is None:
                            self._json({"error": "year is required"}, 400); return
                        self._json(query_vre_curtailment_timeline(
                            database,
                            year=year,
                            resolution=query.get("resolution", ["daily"])[0],
                            start_period=_optional_integer_query(query, "start_period"),
                            end_period=_optional_integer_query(query, "end_period"),
                            period_from=_optional_integer_query(query, "period_from"),
                            period_to=_optional_integer_query(query, "period_to"),
                            limit=_integer_query(query, "limit", 500),
                            offset=_integer_query(query, "offset", 0),
                        )); return
                except LookupError as exc:
                    self._json({"error": str(exc)}, 404); return
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400); return
                table = {
                    "periods": "period_summary", "orders": "orders",
                    "storage": "storage_state", "physical": "physical_dispatch",
                }.get(market_resource)
                if not table:
                    self._json({"error": "unknown market resource"}, 404); return
                metadata = read_json(database.parent / "metadata.json", {})
                page = query_market_table(
                    database, table,
                    limit=_integer_query(query, "limit", 50),
                    offset=_integer_query(query, "offset", 0),
                    year=_optional_integer_query(query, "year"),
                    period=_optional_integer_query(query, "period"),
                    period_from=_optional_integer_query(query, "period_from"),
                    period_to=_optional_integer_query(query, "period_to"),
                    stage=query.get("stage", [None])[0],
                    asset_id=query.get("asset_id", [None])[0],
                    technology=query.get("technology", [None])[0],
                    flow_type=query.get("flow_type", [None])[0],
                    status=query.get("status", [None])[0],
                    side=query.get("side", [None])[0],
                )
                page["trace_level"] = metadata.get("trace_level", "off")
                self._json(page); return
            if resource == "network-redispatch":
                database = root / "model-output" / "market" / "market.sqlite"
                if not database.is_file():
                    self._json({
                        "error": "network redispatch ledger is not available",
                        "error_code": "GF_ZONAL_RESULTS_UNAVAILABLE",
                    }, 404); return
                zonal_resource = parts[4] if len(parts) >= 5 else "capabilities"
                try:
                    capabilities = zonal_workspace_capabilities(database)
                    if not capabilities["available_views"]:
                        self._json({
                            "error": "this run has no zonal redispatch results",
                            "error_code": "GF_ZONAL_RESULTS_UNAVAILABLE",
                            "capabilities": capabilities,
                        }, 409); return
                    if zonal_resource == "capabilities":
                        if query:
                            raise ValueError(
                                "Unsupported network redispatch query field: "
                                + ", ".join(sorted(query))
                            )
                        self._json(capabilities); return
                    if zonal_resource == "annual":
                        if query:
                            raise ValueError(
                                "Unsupported network redispatch query field: "
                                + ", ".join(sorted(query))
                            )
                        self._json(query_zonal_annual_brief(database)); return
                    view_aliases = {
                        "periods": "period",
                        "curtailment": "curtailment",
                        "curtailment-detail": "curtailment-detail",
                        "zones": "zone",
                        "boundaries": "boundary",
                        "resources": "resource",
                        "settlements": "agent",
                        "reliability": "reliability",
                        "solver": "solver",
                        "solver-diagnostics": "solver-diagnostics",
                    }
                    view = view_aliases.get(zonal_resource)
                    if zonal_resource == "export":
                        view = str(query.get("view", ["period"])[0])
                        if view == "solver-diagnostics":
                            allowed_query_fields = {
                                "view", "format", "limit", "offset", "run",
                                "year", "period", "period_from", "period_to", "phase",
                            }
                            text_fields = ("run", "phase")
                        else:
                            allowed_query_fields = {
                                "view", "format", "limit", "offset", "year",
                                "period", "period_from", "period_to", "zone_id", "boundary_id", "agent_id",
                                "asset_id", "technology", "status", "event_id",
                                "zone", "asset", "bid_tranche",
                            }
                            text_fields = (
                                "zone_id", "boundary_id", "agent_id", "asset_id",
                                "technology", "status", "event_id", "zone", "asset",
                                "bid_tranche",
                            )
                        unsupported = sorted(
                            set(query).difference(allowed_query_fields)
                        )
                        if unsupported:
                            raise ValueError(
                                "Unsupported network redispatch query field: "
                                + ", ".join(unsupported)
                            )
                        output_format = str(query.get("format", ["jsonl"])[0]).lower()
                        export_query: dict[str, object] = {
                            "view": view,
                            "limit": _integer_query(query, "limit", 1000),
                            "offset": _integer_query(query, "offset", 0),
                            **{
                                name: query[name][0]
                                for name in text_fields
                                if query.get(name)
                            },
                        }
                        for name in ("year", "period", "period_from", "period_to"):
                            value = _optional_integer_query(query, name)
                            if value is not None:
                                export_query[name] = value
                        suffix = "csv" if output_format == "csv" else "jsonl"
                        destination = (
                            root / "model-output" / "exports"
                            / f"network-redispatch-{slug(view, 'view')}.{suffix}"
                        )
                        export_zonal_results(
                            database,
                            export_query,
                            destination,
                            output_format=output_format,
                        )
                        self._artifact(destination); return
                    if view is None:
                        self._json({"error": "unknown network redispatch resource"}, 404); return
                    if view == "solver-diagnostics":
                        allowed_query_fields = {
                            "limit", "offset", "run", "year", "period", "period_from", "period_to", "phase",
                        }
                        text_fields = ("run", "phase")
                    else:
                        allowed_query_fields = {
                            "limit", "offset", "year", "period", "period_from", "period_to", "zone_id",
                            "boundary_id", "agent_id", "asset_id", "technology",
                            "status", "event_id", "zone", "asset", "bid_tranche",
                        }
                        text_fields = (
                            "zone_id", "boundary_id", "agent_id", "asset_id",
                            "technology", "status", "event_id", "zone", "asset",
                            "bid_tranche",
                        )
                    unsupported = sorted(
                        set(query).difference(allowed_query_fields)
                    )
                    if unsupported:
                        raise ValueError(
                            "Unsupported network redispatch query field: "
                            + ", ".join(unsupported)
                        )
                    result_query: dict[str, object] = {
                        "view": view,
                        "limit": _integer_query(query, "limit", 100),
                        "offset": _integer_query(query, "offset", 0),
                    }
                    for name in ("year", "period", "period_from", "period_to"):
                        value = _optional_integer_query(query, name)
                        if value is not None:
                            result_query[name] = value
                    for name in text_fields:
                        if query.get(name):
                            result_query[name] = query[name][0]
                    self._json(query_zonal_results(database, result_query)); return
                except (OSError, ValueError, sqlite3.DatabaseError) as exc:
                    self._json({
                        "error": str(exc),
                        "error_code": "GF_ZONAL_RESULTS_INVALID",
                    }, 400); return
            if resource == "artifacts":
                if len(parts) == 4:
                    self._json({"run_id": run_id, "items": list_run_artifacts(run_id)}); return
                artifact = safe_run_artifact(run_id, "/".join(parts[4:]))
                if artifact is None:
                    self._json({"error": "artifact not found"}, 404); return
                self._artifact(artifact); return
            if resource == "provenance" and len(parts) == 4:
                self._json(run_provenance(run_id)); return
            self._json({"error": "run resource not found"}, 404)
        else:
            self._json({"error": "not found"}, 404)

    def _upload_dataset(self, route: str) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 5:
            self._json({"error": "invalid upload route"}, 404)
            return
        pack_id, role = slug(parts[2], "pack"), unquote(parts[4])
        slot = dataset_slot(role)
        if slot is None:
            self._json({"error": f"unknown dataset role: {role}", "error_code": "GF_DATA_ROLE_UNKNOWN"}, 400)
            return
        manifest_path = PACKS_ROOT / pack_id / "manifest.json"
        manifest = read_json(manifest_path)
        if not manifest:
            self._json({"error": "data pack not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._json({"error": "empty file"}, 400)
            return
        if length > MAX_UPLOAD_BYTES:
            self._json({"error": "file exceeds the 2 GiB local import limit"}, 413)
            return
        free = shutil.disk_usage(STATE_ROOT).free
        if free < length + MIN_FREE_SPACE_BYTES:
            self._json({
                "error": "not enough disk headroom to stage and validate this file",
                "required_bytes": length + MIN_FREE_SPACE_BYTES,
                "available_bytes": free,
            }, 507)
            return
        filename = Path(unquote(self.headers.get("X-Filename", "dataset.bin"))).name
        file_format = Path(filename).suffix.lower().lstrip(".")
        supported_formats = tuple(slot.get("supported_formats") or slot["formats"])
        if file_format not in supported_formats:
            self._json({
                "error": (
                    f"{slot['label']} has a shipped runtime parser for "
                    f"{', '.join(supported_formats)}; received "
                    f"{file_format or 'a file without an extension'}"
                ),
                "error_code": "GF_DATA_PARSER_UNAVAILABLE",
            }, 400)
            return
        IMPORT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        destination = IMPORT_STAGING_ROOT / f"{uuid.uuid4().hex}.upload"
        digest, remaining = hashlib.sha256(), length
        with destination.open("wb") as handle:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("upload ended before Content-Length")
                handle.write(chunk); digest.update(chunk); remaining -= len(chunk)
        try:
            with STUDY_LIFECYCLE_LOCK:
                manifest = read_json(manifest_path)
                guard_clone_upload(manifest, manifest_path, self.headers.get("X-Expected-Pack-Revision"), PROJECTS_ROOT, TRASH_ROOT)
                binding, validation = promote_binding_revision(
                    pack_root=PACKS_ROOT / pack_id,
                    manifest=manifest,
                    role=role,
                    staged_file=destination,
                    filename=filename,
                    file_format=file_format,
                    dataset_slots=[slot],
                    imported_at=now(),
                    metadata={
                        "redistribution_class": "not_declared",
                        "owner_extension": slot.get("owner_extension"),
                        "capability": slot.get("capability"),
                        "unit": slot.get("unit"),
                    },
                )
                current_hash = manifest_sha256(manifest_path)
        except DataPackCloneError as exc:
            destination.unlink(missing_ok=True)
            self._json({"error": str(exc), "error_code": exc.code}, exc.status)
            return
        except (OSError, ValueError) as exc:
            destination.unlink(missing_ok=True)
            self._json({
                "error": f"The new file was not imported: {exc}",
                "rollback": "The previous valid binding is unchanged.",
            }, 400)
            return
        self._json({"ok": True, "binding": binding, "validation": validation, "manifest_sha256": current_hash}, 201)

    def _upload_data_bundle(self) -> None:
        if self.headers.get("X-VALUE-Data-Rights", "").lower() != "acknowledged":
            self._json({
                "error": "Acknowledge the data licence and attribution before installation",
                "error_code": "GF_DATA_BUNDLE_RIGHTS_ACK",
            }, 400)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._json({
                "error": "Select a non-empty VALUE data bundle",
                "error_code": "GF_DATA_BUNDLE_FORMAT",
            }, 400)
            return
        if length > MAX_DATA_BUNDLE_BYTES:
            self._json({
                "error": "Data bundle exceeds the 2 GiB limit",
                "error_code": "GF_DATA_BUNDLE_SIZE",
            }, 413)
            return
        filename = Path(unquote(self.headers.get("X-Filename", "data-pack.zip"))).name
        if Path(filename).suffix.lower() != ".zip":
            self._json({
                "error": "VALUE data bundles must use .zip",
                "error_code": "GF_DATA_BUNDLE_FORMAT",
            }, 400)
            return
        free = shutil.disk_usage(STATE_ROOT).free
        if free < length + MIN_FREE_SPACE_BYTES:
            self._json({
                "error": "Not enough disk headroom to stage the data bundle",
                "error_code": "GF_DATA_BUNDLE_DISK_HEADROOM",
                "required_bytes": length + MIN_FREE_SPACE_BYTES,
                "available_bytes": free,
            }, 507)
            return
        IMPORT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        staged = IMPORT_STAGING_ROOT / f"{uuid.uuid4().hex}.data-bundle.zip"
        try:
            remaining = length
            with staged.open("wb") as handle:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise DataBundleError(
                            "GF_DATA_BUNDLE_UPLOAD",
                            "Upload ended before Content-Length; no data pack was installed",
                        )
                    handle.write(chunk)
                    remaining -= len(chunk)
            installation = install_data_bundle(
                staged,
                packs_root=PACKS_ROOT,
                dataset_slots=DATASET_SLOTS,
                rights_acknowledged=True,
                minimum_free_space_bytes=MIN_FREE_SPACE_BYTES,
            )
        except (DataBundleError, OSError, ValueError) as exc:
            self._json({
                "error": str(exc),
                "error_code": getattr(exc, "code", "GF_DATA_BUNDLE_INSTALL"),
                "rollback": "No existing data pack was changed.",
            }, 400)
            return
        finally:
            staged.unlink(missing_ok=True)
        self._json({"ok": True, "installation": installation}, 201)

    def _upload_research_suite(self) -> None:
        if self.headers.get("X-VALUE-Data-Rights", "").lower() != "acknowledged":
            self._json({
                "error": "Acknowledge the research-suite rights and attribution before installation",
                "error_code": "VALUE_RESEARCH_SUITE_RIGHTS_ACK",
            }, 400)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._json({
                "error": "Select a non-empty VALUE research suite",
                "error_code": "VALUE_RESEARCH_SUITE_MISSING",
            }, 400)
            return
        if length > MAX_UPLOAD_BYTES:
            self._json({
                "error": "VALUE research suite exceeds the 2 GiB upload limit",
                "error_code": "VALUE_RESEARCH_SUITE_SIZE",
            }, 413)
            return
        filename = Path(unquote(self.headers.get("X-Filename", "research-suite.zip"))).name
        if Path(filename).suffix.lower() != ".zip":
            self._json({
                "error": "VALUE research suites must use .zip",
                "error_code": "VALUE_RESEARCH_SUITE_FORMAT",
            }, 400)
            return
        free = shutil.disk_usage(STATE_ROOT).free
        if free < length + MIN_FREE_SPACE_BYTES:
            self._json({
                "error": "Not enough disk headroom to stage the VALUE research suite",
                "error_code": "VALUE_RESEARCH_SUITE_DISK_HEADROOM",
                "required_bytes": length + MIN_FREE_SPACE_BYTES,
                "available_bytes": free,
            }, 507)
            return
        IMPORT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        staged = IMPORT_STAGING_ROOT / f"{uuid.uuid4().hex}.research-suite.zip"
        try:
            remaining = length
            with staged.open("wb") as handle:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ResearchSuiteError(
                            "VALUE_RESEARCH_SUITE_UPLOAD",
                            "Upload ended before Content-Length; nothing was installed",
                        )
                    handle.write(chunk)
                    remaining -= len(chunk)
            installation = install_research_suite(
                staged,
                packs_root=PACKS_ROOT,
                network_packs_root=STATE_ROOT / "data-workbench" / "installed-packs",
                projects_root=PROJECTS_ROOT,
                base_dataset_slots=DATASET_SLOTS,
                network_dataset_slots=MODULE_REGISTRY.extension_registry.conditional_dataset_slots(
                    ["value-zonal-redispatch-extension"]
                ),
                registry=MODULE_REGISTRY,
                validate_project=validate_project,
                revision_manifest=_revision_manifest,
                rights_acknowledged=True,
                minimum_free_space_bytes=MIN_FREE_SPACE_BYTES,
            )
        except (ResearchSuiteError, OSError, ValueError) as exc:
            self._json({
                "error": str(exc),
                "error_code": getattr(exc, "code", "VALUE_RESEARCH_SUITE_INSTALL"),
                "rollback": "No existing data pack or Study was changed.",
            }, 400)
            return
        finally:
            staged.unlink(missing_ok=True)
        self._json({"ok": True, "installation": installation}, 201)

    def _upload_module_bundle(self) -> None:
        if self.headers.get("X-VALUE-Executable-Trust", "").lower() != "acknowledged":
            self._json({
                "error": "Confirm that the bundle contains executable Python from a source you trust",
                "error_code": "GF_MODULE_TRUST_REQUIRED",
            }, 400)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._json({"error": "Select a non-empty module ZIP", "error_code": "GF_MODULE_BUNDLE_MISSING"}, 400)
            return
        if length > MAX_BUNDLE_BYTES:
            self._json({"error": "Module bundle exceeds the 25 MiB limit", "error_code": "GF_MODULE_BUNDLE_SIZE"}, 413)
            return
        filename = Path(unquote(self.headers.get("X-Filename", "module.zip"))).name
        if Path(filename).suffix.lower() != ".zip":
            self._json({"error": "VALUE modules must be supplied as a .zip bundle", "error_code": "GF_MODULE_BUNDLE_FORMAT"}, 400)
            return
        free = shutil.disk_usage(STATE_ROOT).free
        if free < length * 5 + MIN_FREE_SPACE_BYTES:
            self._json({
                "error": "Not enough disk headroom to stage and validate the module",
                "error_code": "GF_MODULE_DISK_HEADROOM",
            }, 507)
            return
        IMPORT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        staged = IMPORT_STAGING_ROOT / f"{uuid.uuid4().hex}.module.zip"
        remaining = length
        with staged.open("wb") as handle:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    staged.unlink(missing_ok=True)
                    raise ValueError("upload ended before Content-Length")
                handle.write(chunk)
                remaining -= len(chunk)
        try:
            require_no_pending_runs(self._pending_runs_confirmed())
            with MODULE_LIFECYCLE_LOCK:
                installation = install_module_bundle(staged, trust_acknowledged=True)
                stale = self._refresh_after_lifecycle_change()
        except (ModuleInstallationError, ModuleQuarantinedError) as exc:
            self._json({
                "error": str(exc),
                "error_code": exc.code,
                "rollback": "No built-in or previously enabled module was changed.",
            }, status_for_code(exc.code))
            return
        finally:
            staged.unlink(missing_ok=True)
        self._json({
            "ok": True,
            "installation": installation,
            "message": "The module passed structural conformance and is ready for a wiring test.",
            **stale,
        }, 201)

    def _upload_extension_bundle(self) -> None:
        if self.headers.get("X-VALUE-Executable-Trust", "").lower() != "acknowledged":
            self._json({
                "error": "Acknowledge the local executable-code boundary before installing an extension",
                "error_code": "GF_EXTENSION_TRUST_REQUIRED",
            }, 400)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._json({"error": "Select a non-empty extension bundle", "error_code": "GF_EXTENSION_FORMAT"}, 400)
            return
        if length > MAX_BUNDLE_BYTES:
            self._json({"error": "Extension bundle exceeds 25 MiB", "error_code": "GF_EXTENSION_SIZE"}, 413)
            return
        filename = Path(unquote(self.headers.get("X-Filename", "extension.zip"))).name
        if Path(filename).suffix.lower() != ".zip":
            self._json({"error": "Extensions must use .zip", "error_code": "GF_EXTENSION_FORMAT"}, 400)
            return
        if shutil.disk_usage(STATE_ROOT).free < length * 5 + MIN_FREE_SPACE_BYTES:
            self._json({"error": "Not enough disk headroom to stage this extension", "error_code": "GF_EXTENSION_DISK"}, 507)
            return
        IMPORT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        staged = IMPORT_STAGING_ROOT / f"{uuid.uuid4().hex}.extension.zip"
        remaining = length
        with staged.open("wb") as handle:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    staged.unlink(missing_ok=True)
                    raise ValueError("extension upload ended before Content-Length")
                handle.write(chunk)
                remaining -= len(chunk)
        try:
            require_no_pending_runs(self._pending_runs_confirmed())
            with MODULE_LIFECYCLE_LOCK:
                installation = install_extension_bundle(
                    staged,
                    trust_acknowledged=True,
                    modules_root=external_modules_root(),
                )
                stale = self._refresh_after_lifecycle_change()
        except (ExtensionBundleError, ModuleQuarantinedError) as exc:
            self._json({
                "error": str(exc), "error_code": exc.code,
                "rollback": "No built-in or previously enabled extension was changed.",
            }, status_for_code(exc.code))
            return
        finally:
            staged.unlink(missing_ok=True)
        self._json({
            "ok": True,
            "installation": installation,
            "message": "The extension passed structural contract validation; scientific maturity is unchanged.",
            **stale,
        }, 201)

    def _pending_runs_confirmed(self, body: Mapping[str, Any] | None = None) -> bool:
        """Explicit confirmation to change modules while runs are pending:
        ``{"confirm_pending_runs": true}`` in a JSON body, or the header
        ``X-VALUE-Confirm-Pending-Runs: acknowledged`` for ZIP uploads."""

        if body is not None and body.get("confirm_pending_runs") is True:
            return True
        return self.headers.get("X-VALUE-Confirm-Pending-Runs", "").lower() == "acknowledged"

    def _refresh_after_lifecycle_change(self) -> dict[str, Any]:
        """The change on disk is already verified; a failed catalogue refresh
        is reported (catalogue stale, runs paused) instead of undoing it."""

        try:
            refresh_module_catalog()
        except ModuleQuarantinedError as exc:
            return {"catalog_stale": True, "warning": {"error_code": exc.code, "message": str(exc)}}
        return {}

    def _module_dependents(self, module_id: str) -> dict[str, list[str]]:
        projects = []
        for path in sorted(PROJECTS_ROOT.glob("*/project.json")):
            project = read_json(path, {})
            if module_id in set((project.get("modules") or {}).values()):
                projects.append(str(project.get("id") or path.parent.name))
        runs = []
        for path in sorted(RUNS_ROOT.glob("*/status.json")):
            run = read_json(path, {})
            if run.get("status") in {"queued", "snapshotting", "running", "cancel_requested"} and module_id in set((run.get("modules") or {}).values()):
                runs.append(str(run.get("id") or path.parent.name))
        return {"projects": projects, "active_runs": runs}

    def _start_run(
        self,
        project_id: str,
        body: dict[str, Any],
        *,
        project_override: dict[str, object] | None = None,
        lineage: dict[str, object] | None = None,
    ) -> None:
        with STUDY_LIFECYCLE_LOCK:
            self._start_run_locked(
                project_id,
                body,
                project_override=project_override,
                lineage=lineage,
            )

    def _start_run_locked(
        self,
        project_id: str,
        body: dict[str, Any],
        *,
        project_override: dict[str, object] | None = None,
        lineage: dict[str, object] | None = None,
    ) -> None:
        # One registry for the whole admission: a module lifecycle change that
        # finishes meanwhile must not swap it halfway (C6; P0-2 review).
        registry = MODULE_REGISTRY
        project = (
            json.loads(json.dumps(project_override))
            if project_override is not None
            else read_json(PROJECTS_ROOT / project_id / "project.json")
        )
        if not project:
            self._json({"error": "project not found"}, 404); return
        if CATALOG_STALE:
            raise ModuleQuarantinedError(
                "GF_MODULE_CATALOG_STALE",
                "The module catalogue is stale after a failed refresh; rescan modules before starting runs.",
            )
        teaching_run_extensions = _value_101_origin_extensions(project)
        validation = validate_project(project)
        if not validation["valid"]:
            upgrade_event = next((
                row for row in validation.get("error_events", ())
                if row.get("code") == "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED"
            ), None)
            if upgrade_event is not None:
                self._json({
                    "error": upgrade_event.get("message", validation["errors"][0]),
                    "error_code": "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED",
                    "validation": validation,
                }, status_for_code("GF_SOLVER_CONTRACT_UPGRADE_REQUIRED")); return
            self._json({"error": validation["errors"][0], "validation": validation}, 400); return
        mode = str(body.get("mode", "smoke"))
        try:
            verify_recovered_configuration(project, mode=mode)
            policy = resolve_run_policy(mode)
            run_start, run_end = policy.years(project)
        except ValueError as exc:
            self._json({"error": str(exc), "error_code": getattr(exc, "code", None) or "GF_RUN_REQUEST_INVALID"}, 400); return
        pack_root = PACKS_ROOT / str(project["data_pack_id"])
        pack_manifest = read_json(pack_root / "manifest.json", {})
        try:
            pack_selection = resolve_zonal_pack_selection(
                project, base_pack_root=pack_root, data_home=STATE_ROOT
            )
        except ValueError as exc:
            self._json({"error": str(exc), "error_code": getattr(exc, "code", None) or "GF_ZONAL_PACK_SELECTION"}, 400); return
        run_id = bounded_run_id(
            project_id,
            timestamp=datetime.now().strftime("%Y%m%d-%H%M%S"),
            nonce=uuid.uuid4().hex[:8],
        )
        try:
            project = attach_revision_identity(
                project, registry, pack_selection.revision_manifest
            )
        except ValueError as exc:
            self._json({"error": str(exc), "error_code": getattr(exc, "code", None) or "GF_PROJECT_REVISION"}, 409); return
        preflight = run_preflight(
            project,
            mode=mode,
            pack_root=pack_root,
            pack_manifest=pack_manifest,
            dataset_slots=DATASET_SLOTS,
            registry=registry,
            output_root=RUNS_ROOT,
            runs_root=RUNS_ROOT,
            network_pack_root=pack_selection.network_pack_root,
            resource_calibration_root=STATE_ROOT / "resource-calibration",
            preflight_run_id=run_id,
            resource_calibration_runner=(
                selected_staged_zonal_calibration_runner(
                    project=project,
                    pack_root=pack_root,
                    network_pack_root=pack_selection.network_pack_root,
                    registry=registry,
                )
                if pack_selection.network_pack_root is not None
                and dict(project.get("modules") or {}).get("psm")
                == "value-staged-bid-at-cost-psm"
                and dict(project.get("modules") or {}).get("balancing")
                == "value-zonal-redispatch-balancing"
                else None
            ),
        )
        if not preflight["accepted"]:
            first = preflight["errors"][0]
            self._json({"error": first["message"], "error_code": first.get("code") or "GF_PREFLIGHT_REFUSED", "preflight": preflight}, 400); return
        run_dir = RUNS_ROOT / run_id
        # Every server-side status change of the run happens under its action
        # lock from the first write on, so a supervisor tick never judges a run
        # that is still being created (review M1-P0-3 #3).
        with run_action_lock(run_id):
            run_dir.mkdir(parents=True, exist_ok=False)
            # The run is visible from the moment its directory exists (R1-13): a
            # start that fails later leaves a failed status, never an orphan.
            create_status(run_dir, {
                "id": run_id, "project_id": project_id,
                "project_name": project.get("name"), "mode": mode,
                "status": "snapshotting", "execution_status": "queued",
                "execution_engine": "value-annual-orchestrator/v2",
                "current_stage": "Freezing immutable run inputs",
                "created_at": now(), "results": [],
                "extensions": teaching_run_extensions,
            })
            try:
                queued = self._freeze_and_queue_run(
                    run_id=run_id, run_dir=run_dir, project=project, project_id=project_id,
                    mode=mode, policy=policy, run_start=run_start, run_end=run_end,
                    preflight=preflight, pack_root=pack_root, pack_selection=pack_selection,
                    teaching_run_extensions=teaching_run_extensions, lineage=lineage,
                    registry=registry,
                )
            except BaseException:
                _mark_unfinished_start_failed(run_dir)
                raise
        if queued is not None:
            # Outside the start's failure boundary: the worker has been
            # spawned, and a client that disconnects while this answer is sent
            # must not fail its run (review M1-P0-3 #4).
            self._json({"ok": True, "run": queued}, 202)

    def _freeze_and_queue_run(
        self,
        *,
        run_id: str,
        run_dir: Path,
        project: dict[str, Any],
        project_id: str,
        mode: str,
        policy: Any,
        run_start: int,
        run_end: int,
        preflight: dict[str, Any],
        pack_root: Path,
        pack_selection: Any,
        teaching_run_extensions: dict[str, object],
        lineage: dict[str, object] | None,
        registry: Any,
    ) -> dict[str, Any] | None:
        """Freeze inputs, queue the run and spawn its worker.

        Returns the queued status once the worker is spawned; ``None`` after an
        error that has already been answered.  The caller sends the 202.
        """

        selected = dict(project.get("modules") or {})
        selected.setdefault("transition", "value-annual-state-transition")
        psm_manifest = registry.manifest(str(selected["psm"]), expected_slot="psm")
        if "storage.bid-cost-function" in psm_manifest.requires_capabilities:
            selected.setdefault("storage_cost", "dynamic-annual-storage-cost")
        try:
            verify_recovered_inputs(project, pack_root, pack_selection.network_pack_root)
            execution_record = current_execution(source_root=PROJECT_ROOT, data_home=STATE_ROOT, archive=True)
            project = bind_run_execution(project, run_dir, execution_record)
            snapshot = create_run_input_snapshot(
                run_dir=run_dir,
                project=project,
                pack_root=pack_root,
                registry=registry,
                selected=selected,
                object_root=OBJECTS_ROOT,
                network_pack_root=pack_selection.network_pack_root,
            )
            readiness = preflight.get("resource_readiness")
            if isinstance(readiness, Mapping):
                snapshot_root = run_dir / "input-snapshot"
                volume = shutil.disk_usage(RUNS_ROOT)
                quota_policy = RunQuotaPolicy()
                snapshot_estimate, snapshot_decision, readiness = (
                    resource_readiness_from_snapshot(
                        project=project,
                        policy=policy.to_dict(project),
                        run_id=run_id,
                        snapshot_root=snapshot_root,
                        registry=registry,
                        calibration_root=STATE_ROOT / "resource-calibration",
                        selected_output_root=RUNS_ROOT,
                        free_bytes=volume.free,
                        target_volume_bytes=volume.total,
                        quota_policy=quota_policy,
                        calibration_runner=selected_staged_zonal_calibration_runner(
                            project=project,
                            pack_root=snapshot_root / "pack",
                            network_pack_root=snapshot_root / "network-pack",
                            registry=registry,
                        ),
                        usage=quota_usage(RUNS_ROOT, exclude_run=run_id),
                    )
                )
                preflight = {
                    **dict(preflight),
                    "checks": {
                        **dict(preflight.get("checks") or {}),
                        "disk": {
                            "passed": bool(snapshot_decision["accepted"]),
                            **snapshot_decision,
                            "estimated_persisted_bytes": (
                                snapshot_estimate.persisted_bytes
                            ),
                            "estimated_temporary_bytes": (
                                snapshot_estimate.temporary_bytes
                            ),
                            "reserve_bytes": snapshot_estimate.reserve_bytes,
                            "identity_source": "immutable_input_snapshot",
                        },
                    },
                    "estimates": {
                        "label": "estimate_not_guarantee",
                        **snapshot_estimate.to_dict(),
                        "periods": snapshot_estimate.row_cardinality["periods"],
                        "ledger_rows": dict(snapshot_estimate.row_cardinality),
                        "disk_bytes": snapshot_estimate.persisted_bytes,
                        "context_copies": snapshot_estimate.calibration_basis[
                            "context_copies"
                        ],
                        "persisted_safety_multiplier": (
                            snapshot_estimate.calibration_basis[
                                "persisted_safety_multiplier"
                            ]
                        ),
                    },
                    "resource_readiness": readiness,
                }
                if not snapshot_decision["accepted"]:
                    atomic_json(run_dir / "preflight.json", preflight)
                    failed = _record_start_failure(run_dir, {
                        "current_stage": "Snapshot resource gate refused",
                        "error_code": "VALUE_PREFLIGHT_DISK_SPACE",
                        "quota": snapshot_decision,
                    }, "VALUE_PREFLIGHT_DISK_SPACE")
                    self._json({
                        "error": "Snapshot-normalized output does not fit quota",
                        "run": failed,
                    }, 507)
                    return
            estimate = output_reservation_bytes(
                preflight.get("estimates") or {}
            )
            reservation = reserve_run_space(RUNS_ROOT, run_id, estimate)
            if not reservation["accepted"]:
                failed = _record_start_failure(run_dir, {
                    "current_stage": "Disk reservation refused",
                    "error_code": "VALUE_PREFLIGHT_DISK_SPACE",
                    "quota": reservation,
                }, "VALUE_PREFLIGHT_DISK_SPACE")
                self._json({
                    "error": "Run disk quota or free-space floor was not satisfied",
                    "run": failed,
                }, 507)
                return
            atomic_json(run_dir / "preflight.json", preflight)
            update_status(
                run_dir,
                mutate=lambda status: status.update({"quota": reservation}),
                writer=WRITER_SERVER,
            )
            if isinstance(readiness, Mapping):
                frozen_readiness = {
                    **dict(readiness),
                    "quota_decision": reservation,
                }
                freeze_resource_readiness(
                    run_dir / "input-snapshot", frozen_readiness
                )
                snapshot = read_json(
                    run_dir / "input-snapshot" / "snapshot.json", {}
                )
        except LockTimeout:
            _record_start_failure(run_dir, {
                "current_stage": "Disk reservation lock busy",
                "error_code": "GF_RUN_RESERVATION_LOCK_TIMEOUT",
            }, "GF_RUN_RESERVATION_LOCK_TIMEOUT")
            raise
        except (OSError, ValueError, SnapshotError, ResourceSnapshotMismatch) as exc:
            code = (
                getattr(exc, "code", None)
                if isinstance(exc, (ExecutionArchiveError, SnapshotError)) else None
            )
            failed = _record_start_failure(run_dir, {
                "current_stage": "Input snapshot failed",
                "error_code": code or "GF_INPUT_SNAPSHOT_FAILED",
                "error": str(exc),
            }, code or "GF_INPUT_SNAPSHOT_FAILED")
            self._json({"error": str(exc), "error_code": code or "GF_INPUT_SNAPSHOT_FAILED", "run": failed}, 409)
            return
        initial = {"id": run_id, "project_id": project_id, "project_name": project["name"],
                   "mode": mode, "current_stage": "Waiting for the model process to start",
                   "execution_engine": "value-annual-orchestrator/v2",
                   "completed_years": 0,
                   "total_years": run_end - run_start + 1,
                   "run_policy": policy.to_dict(project),
                   "execution_status": "queued",
                   "contract_validation_status": "not_evaluated",
                   "scientific_validation_status": "not_evaluated",
                   "input_snapshot_id": snapshot["snapshot_id"],
                   "input_tree_sha256": snapshot["input_tree_sha256"],
                   "extensions": teaching_run_extensions,
                   "results": []}
        recovery = dict(project.get("extensions") or {}).get("frozen_recovery")
        if recovery:
            initial["frozen_recovery"] = recovery
            atomic_json(run_dir / "frozen-recovery-lineage.json", recovery)
        initial["execution_identity_sha256"] = execution_record["identity_sha256"]
        if lineage is not None:
            initial["comparison_parent_run_id"] = lineage["comparison_parent_run_id"]
            initial["run_lineage_artifact"] = "run-lineage.json"
            atomic_json(run_dir / "run-lineage.json", lineage)
        initial = update_status(
            run_dir,
            mutate=lambda status: status.update(initial),
            transition="queued",
            reason_code="GF_RUN_QUEUED",
            writer=WRITER_SERVER,
        )
        if not self._spawn_or_fail(run_dir, run_id=run_id, project_id=project_id, mode=mode, log_mode="w"):
            return None
        return initial

    def _spawn_or_fail(self, run_dir: Path, *, run_id: str, project_id: str, mode: str,
                       log_mode: str, extra: Mapping[str, Any] | None = None) -> bool:
        """Spawn the run's worker; on failure record it and answer 500 JSON."""

        try:
            run_supervisor().spawn_worker(
                run_dir=run_dir, run_id=run_id, project_id=project_id, mode=mode,
                python=sys.executable, cwd=PROJECT_ROOT, log_mode=log_mode, extra=extra,
            )
        except WorkerSpawnError as exc:
            failed = _record_start_failure(run_dir, {
                "current_stage": "Model worker could not start",
                "error_code": "GF_WORKER_SPAWN_FAILED",
                "error": str(exc),
            }, "GF_WORKER_SPAWN_FAILED")
            self._json({"error": str(exc), "error_code": "GF_WORKER_SPAWN_FAILED", "run": failed}, 500)
            return False
        return True

    def _rerun_as_copperplate(self, run_id: str) -> None:
        with STUDY_LIFECYCLE_LOCK:
            self._rerun_as_copperplate_locked(run_id)

    def _rerun_as_copperplate_locked(self, run_id: str) -> None:
        root = _run_root(run_id)
        if root is None:
            self._json({"error": "run not found"}, 404); return
        status = read_json(root / "status.json", {})
        source_status = source_study_status(str(status.get("project_id") or ""))
        if source_status != "active":
            self._json({
                "error": "Restore the source Study before creating another Run",
                "error_code": (
                    "GF_RUN_SOURCE_STUDY_IN_TRASH"
                    if source_status == "trash" else "GF_RUN_SOURCE_STUDY_MISSING"
                ),
                "source_study_status": source_status,
            }, 409); return
        if status.get("status") != "failed":
            self._json({"error": "Only a failed zonal run can be rerun as copperplate"}, 409); return
        snapshot_root = root / "input-snapshot"
        try:
            verify_run_input_snapshot(snapshot_root, MODULE_REGISTRY)
            source = read_json(snapshot_root / "project.json", {})
            project, lineage = copperplate_rerun_project(source, parent_run_id=run_id)
        except (OSError, ValueError, SnapshotError) as exc:
            body = {"error": f"Cannot create copperplate rerun: {exc}"}
            if isinstance(exc, SnapshotError) and exc.code:
                body["error_code"] = exc.code
            self._json(body, 409); return
        self._start_run(
            str(status.get("project_id") or project.get("id") or "project"),
            {"mode": str(status.get("mode") or "smoke")},
            project_override=project,
            lineage=lineage,
        )

    def _resume_run(self, run_id: str) -> None:
        with STUDY_LIFECYCLE_LOCK, run_action_lock(run_id):
            self._resume_run_locked(run_id)

    def _resume_run_locked(self, run_id: str) -> None:
        registry = MODULE_REGISTRY  # one registry for the whole resume (C6)
        root = _run_root(run_id)
        if root is None:
            self._json({"error": "run not found"}, 404); return
        status = read_json(root / "status.json", {})
        source_status = source_study_status(str(status.get("project_id") or ""))
        if source_status != "active":
            self._json({
                "error": "Restore the source Study before resuming this Run",
                "error_code": (
                    "GF_RUN_SOURCE_STUDY_IN_TRASH"
                    if source_status == "trash" else "GF_RUN_SOURCE_STUDY_MISSING"
                ),
                "source_study_status": source_status,
            }, 409); return
        if status.get("status") not in {"failed", "cancelled"}:
            self._json({"error": "Only a failed or cancelled run can be resumed safely"}, 409); return
        if lease_state(root) == LOCK_HELD:
            self._json({"error": "A model worker of this run is still alive", "error_code": "GF_WORKER_ALIVE"}, 409); return
        legacy_checkpoints = list((root / "model-output" / "checkpoints").glob("*_checkpoint.pkl"))
        safe_checkpoints = list((root / "model-output" / "checkpoints-v2").glob("state-*.json"))
        if not safe_checkpoints and (
            not legacy_checkpoints
            or not all(path.with_suffix(".metadata.json").is_file() for path in legacy_checkpoints)
        ):
            self._json({"error": "No identity-verified annual VALUE checkpoint is available"}, 409); return
        snapshot_root = root / "input-snapshot"
        try:
            snapshot = verify_run_input_snapshot(snapshot_root, registry)
        except (OSError, ValueError, SnapshotError) as exc:
            body = {"error": f"Input snapshot verification failed: {exc}"}
            if isinstance(exc, SnapshotError) and exc.code:
                body["error_code"] = exc.code
            self._json(body, 409); return
        project = read_json(snapshot_root / "project.json", {})
        try:
            verify_run_execution(root, project, source_root=PROJECT_ROOT, data_home=STATE_ROOT, require_record=True)
            verify_recovered_configuration(project, mode=str(status.get("mode") or ""))
        except (ValueError, OSError) as exc:
            self._json({"error": str(exc), "error_code": "GF_EXECUTION_IDENTITY_CHANGED"}, 409); return
        manifest = read_json(snapshot_root / "pack" / "manifest.json", {})
        if not project or not manifest:
            self._json({"error": "The immutable run snapshots required for resume are missing"}, 409); return
        mode = str(status.get("mode") or "full")
        pack_root = snapshot_root / "pack"
        network_pack_root = (
            snapshot_root / "network-pack"
            if (snapshot_root / "network-pack" / "manifest.json").is_file()
            else None
        )
        preflight = run_preflight(
            project, mode=mode, pack_root=pack_root, pack_manifest=manifest,
            dataset_slots=DATASET_SLOTS, registry=registry,
            output_root=RUNS_ROOT, runs_root=RUNS_ROOT,
            network_pack_root=network_pack_root,
            resource_calibration_root=STATE_ROOT / "resource-calibration",
            preflight_run_id=run_id,
            resource_calibration_runner=(
                selected_staged_zonal_calibration_runner(
                    project=project,
                    pack_root=pack_root,
                    network_pack_root=network_pack_root,
                    registry=registry,
                )
                if network_pack_root is not None
                and dict(project.get("modules") or {}).get("psm")
                == "value-staged-bid-at-cost-psm"
                and dict(project.get("modules") or {}).get("balancing")
                == "value-zonal-redispatch-balancing"
                else None
            ),
        )
        if not preflight["accepted"]:
            first = preflight["errors"][0]
            self._json({"error": first["message"], "error_code": first.get("code") or "GF_PREFLIGHT_REFUSED", "preflight": preflight}, 400); return
        # Resume needs only this run's own unwritten reservation (F5-04).
        reserved, written, own_outstanding = run_outstanding_bytes(root)
        usage = quota_usage(RUNS_ROOT, exclude_run=run_id)
        policy_quota = RunQuotaPolicy()
        quota_reasons = global_quota_reasons(usage, own_outstanding, policy_quota)
        if shutil.disk_usage(RUNS_ROOT).free - own_outstanding < policy_quota.minimum_free_bytes:
            quota_reasons.append("minimum_free_space_floor")
        if quota_reasons:
            self._json({
                "error": "Run disk quota or free-space floor was not satisfied",
                "error_code": "VALUE_PREFLIGHT_DISK_SPACE",
                "quota": {
                    "reason_codes": quota_reasons, "required_bytes": own_outstanding,
                    "reserved_bytes": reserved, "written_bytes": written, **usage.to_dict(),
                    "corrective_actions": list(QUOTA_CORRECTIVE_ACTIONS),
                },
            }, 507); return
        atomic_json(root / "preflight.json", preflight)
        cancel_request = root / "cancel-request.json"
        if cancel_request.is_file():
            history = root / "cancellation-history"
            history.mkdir(exist_ok=True)
            destination = history / f"cancel-request-resume-{int(status.get('resume_attempt') or 0) + 1}.json"
            shutil.move(str(cancel_request), str(destination))
        resumed_fields = {
            "execution_status": "queued",
            "current_stage": "Waiting to resume from the last verified annual checkpoint",
            "resume_attempt": int(status.get("resume_attempt") or 0) + 1,
            "input_snapshot_id": snapshot.get("snapshot_id"),
            "resumed_from_status": status.get("status"),
            "parent_run_id": run_id,
        }
        status = update_status(
            root,
            mutate=lambda current: current.update(resumed_fields),
            transition="queued",
            reason_code="GF_RUN_RESUME_QUEUED",
            writer=WRITER_SERVER,
        )
        if not self._spawn_or_fail(
            root, run_id=run_id, project_id=str(project["id"]), mode=mode, log_mode="a",
            extra={"resume_attempt": status["resume_attempt"]},
        ):
            return
        self._json({"ok": True, "run": status}, 202)

    def _run_lifecycle_action(self, run_id: str, action: str, body: dict[str, Any]) -> None:
        with run_action_lock(run_id):
            self._run_lifecycle_action_locked(run_id, action, body)

    def _delete_run(self, run_id: str, root: Path) -> None:
        """Move a terminal run to the trash first; record ``deleting`` only there.

        A failed move leaves the run exactly as it was (F5-12): no state is
        written before the directory has moved.  The check happens under the
        run's status lock, which is released before the rename (Windows cannot
        rename a directory holding an open lock file).
        """

        with hold_lock(root / STATUS_LOCK, timeout=STATUS_LOCK_TIMEOUT_SECONDS):
            state = classify(read_json(root / "status.json"))
            alive = lease_state(root) == LOCK_HELD
        if state not in DELETABLE_STATES:
            self._json({"error": "Active runs must be cancelled first", "error_code": "GF_RUN_NOT_TERMINAL",
                        "status": state}, 409); return
        if alive:
            self._json({"error": "A model worker of this run is still alive", "error_code": "GF_WORKER_ALIVE"}, 409); return
        TRASH_ROOT.mkdir(parents=True, exist_ok=True)
        stem = f"{run_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        target = TRASH_ROOT / stem
        suffix = 1
        while target.exists():
            suffix += 1
            target = TRASH_ROOT / f"{stem}-{suffix}"
        size = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
        try:
            os.rename(root, target)
        except OSError as exc:
            self._json({"error": f"The run could not be moved to the trash; nothing changed: {exc}",
                        "error_code": "GF_RUN_TRASH_MOVE_FAILED"}, 409); return
        warnings = []
        try:
            update_status(
                target, transition="deleting", reason_code="GF_RUN_MOVING_TO_TRASH",
                details={"trash_name": target.name}, writer=WRITER_SERVER,
            )
        except (LifecycleError, OSError) as exc:
            warnings.append(f"The trash copy's status could not record the deletion: {exc}")
        self._json({"ok": True, "run_id": run_id, "moved_to": str(target), "bytes": size,
                    "recoverable": True, "warnings": warnings})

    def _run_lifecycle_action_locked(self, run_id: str, action: str, body: dict[str, Any]) -> None:
        root = _run_root(run_id)
        if root is None:
            self._json({"error": "run not found"}, 404); return
        status_path = root / "status.json"
        status = read_json(status_path, {})
        try:
            if action == "cancel":
                if status.get("status") not in ACTIVE_STATES:
                    self._json({"error": "Only queued or running runs can be cancelled"}, 409); return
                request = root / "cancel-request.json"
                # The worker owns status.json while it runs: cancellation is
                # only this request file, written once (a repeated cancel
                # leaves it byte-identical and answers 202 again).
                if not request.is_file():
                    atomic_json(request, {
                        "schema_version": "value.cancel-request/v1", "run_id": run_id,
                        "requested_at": now(),
                        "guaranteed_boundary": "native: after annual checkpoint; VALUE compatibility: after copied-kernel return",
                    })
                self._json({"ok": True, "run": present_run(read_json(status_path, {}))}, 202); return
            if action == "mark-lost":
                code, payload = run_supervisor().mark_lost(
                    root, confirm_run_id=str(body.get("confirm_run_id") or ""),
                )
                if code == 200:
                    payload["run"] = present_run(dict(payload["run"]))
                self._json(payload, code); return
            if action == "export":
                profile = str(body.get("profile") or "compact_results")
                destination = root / "exports" / f"{run_id}-{profile}.zip"
                manifest = export_run_bundle(root, destination, profile=profile)
                validation = validate_bundle_archive(destination)
                self._json({
                    "ok": True, "manifest": manifest, "validation": validation,
                    "download_url": f"/api/runs/{run_id}/artifacts/exports/{destination.name}",
                }, 201); return
            if action == "archive":
                if status.get("status") not in {"completed", "failed", "cancelled"}:
                    self._json({"error": "Only terminal runs can be archived"}, 409); return
                if lease_state(root) == LOCK_HELD:
                    self._json({"error": "A model worker of this run is still alive", "error_code": "GF_WORKER_ALIVE"}, 409); return
                ARCHIVES_ROOT.mkdir(parents=True, exist_ok=True)
                destination = ARCHIVES_ROOT / f"{run_id}.zip"
                manifest = export_run_bundle(root, destination, profile="complete_audit")
                if not validate_bundle_archive(destination)["valid"]:
                    self._json({"error": "Archive verification failed"}, 500); return
                original = str(status["status"])
                updated = update_status(
                    root,
                    mutate=lambda current: current.__setitem__("archived_from_status", original),
                    transition="archived", reason_code="GF_RUN_ARCHIVED",
                    details={"archive": destination.name}, writer=WRITER_SERVER,
                )
                self._json({"ok": True, "run": updated, "archive": manifest}); return
            if action == "restore":
                if status.get("status") != "archived":
                    self._json({"error": "Run is not archived"}, 409); return
                archive = ARCHIVES_ROOT / f"{run_id}.zip"
                validation = validate_bundle_archive(archive) if archive.is_file() else {"valid": False}
                if not validation["valid"]:
                    self._json({"error": "Archive is missing or invalid"}, 409); return
                target = str(status.get("archived_from_status") or "completed")
                updated = update_status(
                    root, transition=target, reason_code="GF_RUN_ARCHIVE_RESTORED",
                    writer=WRITER_SERVER,
                )
                self._json({"ok": True, "run": updated}); return
            if action == "delete":
                if str(body.get("confirm_run_id") or "") != run_id:
                    self._json({"error": "Exact run ID confirmation is required", "run_id": run_id, "path": str(root)}, 409); return
                self._delete_run(run_id, root); return
            self._json({"error": "unknown lifecycle action"}, 404)
        except LockTimeout:
            raise
        except (LifecycleError, OSError, ValueError) as exc:
            self._json({"error": str(exc)}, 409)

    def _route_post(self) -> None:
        route = urlparse(self.path).path
        mapping_stage = re.fullmatch(r"/api/data-packs/([^/]+)/csv-mapping/stages", route)
        mapping_preview = re.fullmatch(r"/api/data-mapping/stages/([0-9a-f]{32})/preview", route)
        mapping_commit = re.fullmatch(r"/api/data-mapping/reviews/([0-9a-f]{32})/commit", route)
        if mapping_stage:
            query = parse_qs(urlparse(self.path).query)
            result = self._mapping_service().stage(
                unquote(mapping_stage[1]), str(query.get("role", [""])[0]), self._small_upload_body(),
                unquote(self.headers.get("X-Filename", "data.csv")),
                self.headers.get("X-Expected-Pack-Revision", ""),
            )
            self._json(result, 201); return
        if mapping_preview:
            self._json(self._mapping_service().preview(mapping_preview[1], self._json_body())); return
        if mapping_commit:
            self._json(self._mapping_service().commit(mapping_commit[1], self._json_body())); return
        if re.fullmatch(re.escape(DATA_WORKBENCH_API_BASE) + r"/overlay-candidates/[^/]+/roles/[^/]+/file", route):
            status, payload = self.server.data_workbench_api.handle_upload(  # type: ignore[attr-defined]
                "POST", route, self._small_upload_body(),
                unquote(self.headers.get("X-Filename", "")), self.headers.get("X-Expected-Candidate-Id", ""),
            )
            self._json(payload, status); return
        if route.startswith(DATA_WORKBENCH_API_BASE):
            body = self._json_body()
            status, payload = self.server.data_workbench_api.handle("POST", route, body)  # type: ignore[attr-defined]
            self._json(payload, status)
            return
        if route == "/api/data-packs/install":
            self._upload_data_bundle(); return
        if route == "/api/research-suites/install":
            self._upload_research_suite(); return
        if route.startswith("/api/data-packs/") and "/files/" in route:
            self._upload_dataset(route); return
        if route == "/api/modules/install":
            self._upload_module_bundle(); return
        if route == "/api/extensions/install":
            self._upload_extension_bundle(); return
        body = self._json_body()
        recovery_route = re.fullmatch(r"/api/runs/([^/]+)/frozen-recovery(/review)?", route)
        if recovery_route:
            root = _run_root(unquote(recovery_route[1]))
            if root is None:
                self._json({"error": "Run not found"}, 404); return
            try:
                with STUDY_LIFECYCLE_LOCK:
                    if recovery_route[2]:
                        result, _ = _review_frozen_recovery(root, str(body.get("recovery_mode") or ""))
                        status = 200
                    else:
                        result = publish_frozen_recovery(
                            root, body, review=_review_frozen_recovery, projects_root=PROJECTS_ROOT,
                            packs_root=PACKS_ROOT, network_packs_root=STATE_ROOT / "data-workbench" / "installed-packs",
                            staging_root=STATE_ROOT / "frozen-recovery-staging", registry=MODULE_REGISTRY,
                            validate_project=validate_project, revision_manifest=_revision_manifest,
                            is_reserved=lambda sid: study_id_is_reserved(sid, projects_root=PROJECTS_ROOT, trash_root=TRASH_ROOT),
                        )
                        status = 201
            except FrozenRecoveryError as exc:
                self._json({"error": str(exc), "error_code": exc.code}, exc.status); return
            self._json(result, status); return
        if route == "/api/extensions/authoring/validate":
            self._json(validate_extension_proposal(body, MODULE_REGISTRY))
        elif route == "/api/extensions/authoring/template":
            try:
                data = extension_proposal_template(body, MODULE_REGISTRY)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                self._json({"error": str(exc), "error_code": "GF_EXTENSION_AUTHORING_INVALID"}, 400); return
            self._bytes(data, "application/zip", "value-extension-source-project.zip")
        elif route == "/api/tutorials/value-101/studies":
            try:
                saved, validation = _save_value_101_project(value_101_study())
            except ValueError as exc:
                self._json({
                    "error": str(exc),
                    "error_code": "GF_VALUE_101_STUDY_CREATE_FAILED",
                }, 409)
                return
            self._json({
                "ok": True,
                "project": saved,
                "validation": validation,
                "run_started": False,
            }, 201)
        elif route.startswith("/api/tutorials/value-101/studies/") and route.endswith("/network-pair"):
            parts = route.strip("/").split("/")
            if len(parts) != 6:
                self._json({"error": "invalid VALUE 101 network-pair route"}, 404); return
            base_id = slug(parts[4], "project")
            base = read_json(PROJECTS_ROOT / base_id / "project.json")
            if not base or not is_value_101_record(base):
                self._json({"error": "VALUE 101 base Study not found"}, 404); return
            base_pack = PACKS_ROOT / VALUE_101_NETWORK_PACK_ID / "manifest.json"
            overlay_pack = (
                STATE_ROOT / "data-workbench" / "installed-packs"
                / VALUE_101_NETWORK_PACK_ID / "manifest.json"
            )
            if not base_pack.is_file() or not overlay_pack.is_file():
                self._json({
                    "error": "The bundled VALUE 101 network teaching pack is not installed",
                    "error_code": "GF_VALUE_101_NETWORK_PACK_NOT_INSTALLED",
                }, 409); return
            try:
                pair, identity = build_value_101_network_pair(
                    base, network_pack_id=VALUE_101_NETWORK_PACK_ID
                )
                validations = {
                    role: validate_project(dict(project))
                    for role, project in pair.items()
                }
                invalid = [
                    role for role, validation in validations.items()
                    if not validation["valid"]
                ]
                if invalid:
                    first = invalid[0]
                    raise ValueError(str(validations[first]["errors"][0]))
                if body.get("dry_run") is True:
                    self._json({
                        "ok": True,
                        "schema_version": "value.101-network-pair-preview/v1",
                        "identity": identity,
                        "studies": pair,
                        "run_started": False,
                    }); return
                with STUDY_LIFECYCLE_LOCK:
                    live_base = read_json(PROJECTS_ROOT / base_id / "project.json")
                    if not live_base or not is_value_101_record(live_base):
                        raise ValueError(
                            "Restore the VALUE 101 base Study before creating the network pair"
                        )
                    pair, identity = build_value_101_network_pair(
                        live_base, network_pack_id=VALUE_101_NETWORK_PACK_ID
                    )
                    existing = [
                        str(project["id"])
                        for project in pair.values()
                        if study_id_is_reserved(
                            str(project["id"]),
                            projects_root=PROJECTS_ROOT,
                            trash_root=TRASH_ROOT,
                        )
                    ]
                    if existing:
                        raise ValueError(
                            "Restore or reset the existing VALUE 101 network Studies before recreating: "
                            + ", ".join(existing)
                        )
                    saved_pair = {
                        role: _save_value_101_project(dict(project))[0]
                        for role, project in pair.items()
                    }
            except ValueError as exc:
                self._json({
                    "error": str(exc),
                    "error_code": "GF_VALUE_101_NETWORK_PAIR_FAILED",
                }, 409); return
            self._json({
                "ok": True,
                "schema_version": "value.101-network-pair/v1",
                "identity": identity,
                "studies": saved_pair,
                "run_started": False,
            }, 201)
        elif route == "/api/tutorials/value-101/reset":
            if body.get("confirm") is not True:
                self._json({
                    "error": "Explicit confirmation is required to reset VALUE 101",
                    "error_code": "GF_VALUE_101_RESET_CONFIRMATION_REQUIRED",
                }, 400); return
            try:
                with STUDY_LIFECYCLE_LOCK:
                    studies, runs = _value_101_reset_records()
                    reset = _move_value_101_reset_records(studies, runs)
            except ValueError as exc:
                self._json({
                    "error": str(exc),
                    "error_code": "GF_VALUE_101_RESET_BLOCKED",
                }, 409); return
            self._json({"ok": True, **reset})
        elif route.startswith("/api/data-packs/") and route.endswith("/clone"):
            parts = route.strip("/").split("/")
            if len(parts) != 4:
                self._json({"error": "invalid data pack clone route"}, 404); return
            try:
                with STUDY_LIFECYCLE_LOCK:
                    result = clone_data_pack(unquote(parts[2]), body, packs_root=PACKS_ROOT)
            except DataPackCloneError as exc:
                self._json({"error": str(exc), "error_code": exc.code}, exc.status); return
            self._json(result, 201)
        elif route == "/api/data-packs":
            pack_id = slug(str(body.get("id") or body.get("name") or "data-pack"), "data-pack")
            path = PACKS_ROOT / pack_id / "manifest.json"
            if path.exists(): self._json({"error": "data pack already exists"}, 409); return
            manifest = {"schema_version": "value.data-pack/v1", "id": pack_id,
                        "name": str(body.get("name") or pack_id), "country": str(body.get("country") or ""),
                        "timezone": str(body.get("timezone") or "UTC"), "created_at": now(),
                        "updated_at": now(), "bindings": {}}
            atomic_json(path, manifest); self._json({"ok": True, "data_pack": manifest}, 201)
        elif route.startswith("/api/projects/") and route.endswith("/derive"):
            parts = route.strip("/").split("/")
            if len(parts) != 4:
                self._json({"error": "invalid Study derivation route"}, 404); return
            try:
                with STUDY_LIFECYCLE_LOCK:
                    result = derive_study(
                        unquote(parts[2]), body,
                        projects_root=PROJECTS_ROOT,
                        packs_root=PACKS_ROOT,
                        registry=MODULE_REGISTRY,
                        validate_project=validate_project,
                        revision_manifest=_revision_manifest,
                        is_reserved=lambda study_id: study_id_is_reserved(
                            study_id, projects_root=PROJECTS_ROOT,
                            trash_root=TRASH_ROOT,
                        ),
                    )
            except StudyDerivationError as exc:
                payload = {"error": str(exc), "error_code": exc.code}
                if exc.validation is not None:
                    payload["validation"] = exc.validation
                self._json(payload, exc.status); return
            self._json(result, 201)
        elif route == "/api/projects":
            project_id = slug(str(body.get("id") or body.get("name") or "project"), "project")
            project = {"schema_version": "value.project/v1", "id": project_id,
                       "name": str(body.get("name") or project_id),
                       "data_pack_id": str(body.get("data_pack_id") or "value-uk-1000twh-reproduction"),
                       "start_year": int(body.get("start_year", 2025)), "end_year": int(body.get("end_year", 2034)),
                       "modules": body.get("modules") or {"psm": "value-bid-at-cost-psm", "investment": "agent-investment",
                           "pipeline": "planning-pipeline", "vre_cap": "vre-expansion-cap",
                           "storage_cap": "value-storage-expansion-policy",
                           "storage_cost": "dynamic-annual-storage-cost"},
                       "purpose": str(body.get("purpose") or ""),
                       "selected_extensions": body.get("selected_extensions") or [],
                       "extension_parameters": body.get("extension_parameters") or {},
                       "maturity_acknowledgements": body.get("maturity_acknowledgements") or {},
                       "market_configuration": body.get("market_configuration") or {},
                       "parameters": body.get("parameters") or {},
                       "runtime_options": body.get("runtime_options") or {},
                       "updated_at": now()}
            if "solver_contract" in body:
                project["solver_contract"] = body.get("solver_contract")
            validation = validate_project(project)
            if not validation["valid"]:
                solver_ack_event = next((
                    row for row in validation["error_events"]
                    if row.get("code") == "GF_SOLVER_CONTRACT_ACK_REQUIRED"
                ), None)
                # A historical (v2/v3) solver contract is a method change the
                # user must confirm explicitly: 409 with the coded event (P0-8 S5).
                upgrade_event = next((
                    row for row in validation["error_events"]
                    if row.get("code") == "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED"
                ), None)
                first = solver_ack_event or upgrade_event or (
                    validation["error_events"][0]
                    if validation["error_events"] else {}
                )
                if solver_ack_event is not None:
                    status = 422
                elif upgrade_event is not None:
                    status = status_for_code("GF_SOLVER_CONTRACT_UPGRADE_REQUIRED")
                else:
                    status = 400
                self._json({
                    "error": first.get("message", validation["errors"][0]),
                    "error_code": first.get("code", "GF_STUDY_INVALID"),
                    "validation": validation,
                }, status); return
            project = dict(validation["normalised_project"])
            project.update({
                "schema_version": "value.project/v1",
                "id": project_id,
                "name": str(body.get("name") or project_id),
                "data_pack_id": str(body.get("data_pack_id") or "value-uk-1000twh-reproduction"),
                "start_year": int(body.get("start_year", 2025)),
                "end_year": int(body.get("end_year", 2034)),
                "updated_at": now(),
            })
            pack_manifest = read_json(PACKS_ROOT / project["data_pack_id"] / "manifest.json", {})
            try:
                with STUDY_LIFECYCLE_LOCK:
                    project_path = PROJECTS_ROOT / project_id / "project.json"
                    if not project_path.is_file() and study_id_is_reserved(
                        project_id, projects_root=PROJECTS_ROOT, trash_root=TRASH_ROOT
                    ):
                        self._json({
                            "error": "Restore the trashed Study before reusing this ID",
                            "error_code": "GF_STUDY_ID_RESERVED_IN_TRASH",
                            "study_id": project_id,
                        }, 409); return
                    existing_project = read_json(project_path, {})
                    for metadata_key in ("derivation", "extensions"):
                        if metadata_key in existing_project:
                            project[metadata_key] = json.loads(json.dumps(existing_project[metadata_key]))
                    verify_recovered_configuration(project)
                    project = save_project_revision(
                        PROJECTS_ROOT / project_id, project, MODULE_REGISTRY,
                        _revision_manifest(project, pack_manifest),
                        expected_base_revision=(str(body["base_revision_sha256"]) if body.get("base_revision_sha256") else None),
                    )
            except ValueError as exc:
                self._json({"error": str(exc)}, 409); return
            self._json({"ok": True, "project": project, "validation": validation}, 201)
        elif route == "/api/projects/validate":
            self._json(validate_project(body))
        elif route == "/api/projects/resolve-draft":
            self._json(resolve_project_draft(body))
        elif route == "/api/projects/resolve-readiness":
            pack_id = slug(str(body.get("data_pack_id") or ""), "pack")
            pack_root = PACKS_ROOT / pack_id
            manifest = read_json(pack_root / "manifest.json")
            if not manifest:
                self._json({"error": "data pack not found", "error_code": "GF_DATA_PACK_UNKNOWN"}, 404); return
            try:
                policy = resolve_run_policy(str(body.get("mode") or "smoke"))
                self._json(build_domain_readiness(
                    body,
                    pack_root=pack_root,
                    pack_manifest=manifest,
                    registry=MODULE_REGISTRY,
                    requested_periods=policy.periods_per_year,
                ))
            except (ValueError, KeyError, TypeError) as exc:
                self._json({"error": str(exc), "error_code": "GF_DOMAIN_READINESS_INVALID"}, 400)
        elif route.startswith("/api/projects/") and route.endswith("/trash"):
            parts = route.strip("/").split("/")
            if len(parts) != 4:
                self._json({"error": "invalid Study trash route"}, 404); return
            project_id = slug(parts[2], "project")
            if body.get("confirm") is not True:
                self._json({
                    "error": "Confirm before moving this Study to recoverable trash",
                    "error_code": "GF_STUDY_TRASH_CONFIRMATION_REQUIRED",
                }, 400); return
            try:
                with STUDY_LIFECYCLE_LOCK:
                    entry = move_study_to_trash(
                        project_id,
                        projects_root=PROJECTS_ROOT,
                        runs_root=RUNS_ROOT,
                        trash_root=TRASH_ROOT,
                        confirmation_name=(
                            str(body.get("confirm_name"))
                            if body.get("confirm_name") is not None else None
                        ),
                        reason=(str(body.get("reason")) if body.get("reason") else None),
                    )
            except StudyLifecycleError as exc:
                code = (
                    "GF_STUDY_TRASH_CONFIRMATION_REQUIRED"
                    if "exact Study name" in str(exc)
                    else "GF_STUDY_TRASH_BLOCKED"
                )
                self._json({"error": str(exc), "error_code": code}, 409); return
            self._json({"ok": True, "trash_entry": entry})
        elif route.startswith("/api/study-trash/") and route.endswith("/restore"):
            parts = route.strip("/").split("/")
            if len(parts) != 4:
                self._json({"error": "invalid Study restore route"}, 404); return
            trash_id = parts[2]
            try:
                with STUDY_LIFECYCLE_LOCK:
                    restored = restore_study(
                        trash_id,
                        projects_root=PROJECTS_ROOT,
                        runs_root=RUNS_ROOT,
                        trash_root=TRASH_ROOT,
                    )
            except StudyLifecycleError as exc:
                self._json({
                    "error": str(exc),
                    "error_code": "GF_STUDY_RESTORE_BLOCKED",
                }, 409); return
            project = read_json(
                PROJECTS_ROOT / str(restored["study_id"]) / "project.json", {}
            )
            validation = validate_project(project) if project else {
                "valid": False, "errors": ["Restored Study is unreadable"]
            }
            self._json({
                "ok": True,
                "study": project,
                "trash_entry": restored,
                "validation": validation,
                "needs_attention": not validation["valid"],
            })
        elif route.startswith("/api/modules/") and route.endswith(("/enable", "/disable")):
            parts = route.strip("/").split("/")
            if len(parts) != 4:
                self._json({"error": "invalid module lifecycle route"}, 404); return
            module_id = slug(parts[2], "module")
            enabling = parts[3] == "enable"
            dependents = self._module_dependents(module_id)
            # A quarantined module may be disabled even when saved Studies
            # still name it; only runs that are still active block it (Q3).
            quarantined = module_id in _quarantined_ids("module")
            if not enabling and (dependents["active_runs"] or (dependents["projects"] and not quarantined)):
                self._json({
                    "error": "This module is referenced by saved Studies or active runs and cannot be disabled",
                    "error_code": "GF_MODULE_IN_USE",
                    "dependents": dependents,
                }, 409)
                return
            require_no_pending_runs(self._pending_runs_confirmed(body))
            with MODULE_LIFECYCLE_LOCK:
                installation = set_module_enabled(module_id, enabling)
                stale = self._refresh_after_lifecycle_change()
            self._json({"ok": True, "installation": installation, "dependents": dependents, **stale})
        elif route.startswith("/api/extensions/") and route.endswith(("/enable", "/disable")):
            parts = route.strip("/").split("/")
            if len(parts) != 4:
                self._json({"error": "invalid extension lifecycle route"}, 404); return
            extension_id = slug(parts[2], "extension")
            enabling = parts[3] == "enable"
            dependents = extension_dependents(extension_id)
            blocking = any(dependents.values())
            if extension_id in _quarantined_ids("extension"):
                # Quarantined: only runs that are still active block a disable (Q3).
                blocking = any(
                    str(read_object(RUNS_ROOT / run / "status.json").get("status") or "") in ACTIVE_STATES
                    for run in dependents["runs_and_retained_history"]
                )
            if not enabling and blocking:
                self._json({
                    "error": "This extension is referenced by saved Studies, snapshots or retained run history",
                    "error_code": "GF_EXTENSION_IN_USE",
                    "dependents": dependents,
                }, 409); return
            require_no_pending_runs(self._pending_runs_confirmed(body))
            with MODULE_LIFECYCLE_LOCK:
                installation = set_extension_enabled(
                    extension_id, enabling, modules_root=external_modules_root()
                )
                stale = self._refresh_after_lifecycle_change()
            self._json({"ok": True, "installation": installation, "dependents": dependents, **stale})
        elif route == "/api/modules/rescan":
            # Retry everything the negative caches remember and rebuild the
            # catalogue; clears a stale catalogue when it succeeds.
            with MODULE_LIFECYCLE_LOCK:
                cleared = clear_negative_caches()
                refresh_module_catalog()
            report = module_quarantine_payload()
            self._json({"ok": True, "cleared": cleared, "status": report["status"], "module_quarantine": report})
        elif route.startswith("/api/projects/") and route.endswith("/clone-storage-policy"):
            base_id = slug(route.strip("/").split("/")[2], "project")
            with STUDY_LIFECYCLE_LOCK:
                base = read_json(PROJECTS_ROOT / base_id / "project.json")
                if not base:
                    self._json({"error": "base project not found"}, 404); return
                storage_module = str(body.get("storage_cost_module_id") or "")
                try:
                    MODULE_REGISTRY.manifest(storage_module, expected_slot="storage_cost")
                except (ValueError, KeyError) as exc:
                    self._json({"error": str(exc)}, 400); return
                clone = json.loads(json.dumps(base))
                clone_id = slug(str(body.get("id") or f"{base_id}-{storage_module}"), "project")
                clone["id"] = clone_id
                clone["name"] = str(body.get("name") or f"{base.get('name')} · {storage_module}")
                clone["modules"] = dict(clone.get("modules") or {}) | {"storage_cost": storage_module}
                clone["parent_revision_sha256"] = base.get("revision_sha256")
                clone.pop("revision_sha256", None); clone.pop("revision_number", None)
                clone["updated_at"] = now()
                pack_manifest = read_json(PACKS_ROOT / str(clone["data_pack_id"]) / "manifest.json", {})
                if study_id_is_reserved(
                    clone_id, projects_root=PROJECTS_ROOT, trash_root=TRASH_ROOT
                ):
                    self._json({
                        "error": "Restore or rename the existing Study before creating this clone",
                        "error_code": "GF_STUDY_ID_RESERVED_IN_TRASH",
                        "study_id": clone_id,
                    }, 409); return
                saved = save_project_revision(
                    PROJECTS_ROOT / clone_id,
                    clone,
                    MODULE_REGISTRY,
                    _revision_manifest(clone, pack_manifest),
                )
            controlled = {
                key: base.get(key) == saved.get(key) for key in ("data_pack_id", "start_year", "end_year", "parameters", "runtime_options")
            }
            self._json({"ok": True, "project": saved, "controlled_dimensions": controlled, "only_intended_module_changed": all(controlled.values())}, 201)
        elif route == "/api/parameters/preview":
            pack_id = slug(str(body.get("data_pack_id") or ""), "pack")
            pack_root = PACKS_ROOT / pack_id
            if not (pack_root / "manifest.json").is_file():
                self._json({"error": "data pack not found"}, 404); return
            resolved = resolve_scheme_c_parameters(
                pack_root,
                body.get("parameters") or {},
                body.get("runtime_options") or {},
                periods_per_year=int(body.get("periods_per_year", 17_520)),
            )
            self._json(resolved.to_dict())
        elif route.startswith("/api/projects/") and route.endswith("/runs"):
            self._start_run(slug(route.strip("/").split("/")[2], "project"), body)
        elif route.startswith("/api/projects/") and route.endswith("/preflight"):
            project_id = slug(route.strip("/").split("/")[2], "project")
            project = read_json(PROJECTS_ROOT / project_id / "project.json")
            if not project:
                self._json({"error": "project not found"}, 404); return
            pack_root = PACKS_ROOT / str(project["data_pack_id"])
            manifest = read_json(pack_root / "manifest.json", {})
            try:
                verify_recovered_configuration(project, mode=str(body.get("mode", "smoke")))
                if dict(project.get("extensions") or {}).get("frozen_recovery"):
                    selection = resolve_zonal_pack_selection(project, base_pack_root=pack_root, data_home=STATE_ROOT)
                    verify_recovered_inputs(project, pack_root, selection.network_pack_root)
                    execution = current_execution(source_root=PROJECT_ROOT, data_home=STATE_ROOT)
                    verify_recovered_configuration(project, execution_identity=execution["identity_sha256"])
            except (ValueError, OSError) as exc:
                self._json({"error": str(exc), "error_code": "GF_FROZEN_RECOVERY_BLOCKED"}, 409); return
            self._json(run_preflight(
                project,
                mode=str(body.get("mode", "smoke")),
                pack_root=pack_root,
                pack_manifest=manifest,
                dataset_slots=DATASET_SLOTS,
                registry=MODULE_REGISTRY,
                output_root=RUNS_ROOT,
                runs_root=RUNS_ROOT,
            ))
        elif route.startswith("/api/runs/") and route.endswith("/resume"):
            self._resume_run(slug(route.strip("/").split("/")[2], "run"))
        elif route.startswith("/api/runs/") and route.endswith("/rerun-copperplate"):
            self._rerun_as_copperplate(slug(route.strip("/").split("/")[2], "run"))
        elif route.startswith("/api/runs/") and route.endswith("/replay-exports"):
            parts = route.strip("/").split("/")
            run_id = slug(parts[2], "run")
            root = _run_root(run_id)
            if root is None:
                self._json({"error": "run not found"}, 404); return
            try:
                request = ReplayExportRequest(
                    range_kind=str(body.get("range_kind") or ""),
                    year=(int(body["year"]) if body.get("year") is not None else None),
                    period_from=(
                        int(body["period_from"])
                        if body.get("period_from") is not None else None
                    ),
                    period_to=(
                        int(body["period_to"])
                        if body.get("period_to") is not None else None
                    ),
                    output_format=str(body.get("output_format") or ""),
                )
                job = create_replay_export_job(root, request)
            except (FileNotFoundError, TypeError, ValueError) as exc:
                self._json({"error": str(exc)}, 400); return
            self._json({
                **job,
                "status_url": f"/api/runs/{run_id}/replay-exports/{job['job_id']}",
            }, 202)
        elif route.startswith("/api/runs/"):
            parts = route.strip("/").split("/")
            if len(parts) == 4 and parts[3] in {"cancel", "archive", "restore", "delete", "export", "mark-lost"}:
                self._run_lifecycle_action(slug(parts[2], "run"), parts[3], body)
            else:
                self._json({"error": "not found"}, 404)
        else:
            self._json({"error": "not found"}, 404)


def acquire_backend_singleton(state_root: Path) -> FileLock | None:
    """Hold ``<state>/.backend.lock`` for the life of this backend (C2).

    ``None`` when another backend already serves this data directory.  The
    lock descriptor is not inheritable, so workers never keep it alive.
    """

    try:
        return FileLock(Path(state_root) / BACKEND_LOCK_NAME).acquire(timeout=0)
    except LockTimeout:
        return None


def _startup_quota_repairs(report: Any) -> None:
    """Start-up (singleton held): legacy reservation lock and orphan run dirs."""

    if supervisor_observe_only():
        return
    if remove_legacy_reservation_lock(RUNS_ROOT):
        report.extra["removed_legacy_reservation_lock"] = True
    moved = quarantine_orphan_run_directories(RUNS_ROOT, TRASH_ROOT)
    if moved:
        report.extra["orphan_run_directories_moved_to_trash"] = moved


def supervisor_observe_only() -> bool:
    return run_supervisor().observe_only


def _raise_keyboard_interrupt(signum: int, _frame: object) -> None:
    raise KeyboardInterrupt(f"signal {signum}")


def _ignore_stop_signals() -> None:
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is not None:
            try:
                signal.signal(number, signal.SIG_IGN)
            except (OSError, ValueError):
                pass


LOOPBACK_BIND_HOSTS = frozenset({"127.0.0.1", "localhost"})


def make_api_server(
    host: str,
    port: int,
    *,
    session_token: str | None,
    data_workbench_api: DataWorkbenchApi | None = None,
) -> ThreadingHTTPServer:
    """Bind the local API (loopback only) without touching any state root.

    ``session_token`` is this process's API session (P0-1); the request guard
    compares ``X-VALUE-Session`` against it.  ``data_workbench_api`` is
    mounted only when given, so tests and embedded servers decide whether the
    data workbench routes exist.
    """

    if host not in LOOPBACK_BIND_HOSTS:
        raise ValueError("VALUE local API only permits loopback binding")
    server = ThreadingHTTPServer((host, int(port)), Handler)
    server.session_token = session_token  # type: ignore[attr-defined]
    if data_workbench_api is not None:
        server.data_workbench_api = data_workbench_api  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="VALUE modular local API")
    parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", default=8766, type=int)
    args = parser.parse_args()
    if args.host not in LOOPBACK_BIND_HOSTS:
        raise SystemExit("VALUE local API only permits loopback binding")
    # Start-up order (P0 C2): state layout -> .backend.lock -> default pack ->
    # reconcile_all -> workbench -> bind -> publish session -> supervisor
    # threads -> serve -> (finally) withdraw session.
    ensure_state_layout(STATE_ROOT)
    singleton = acquire_backend_singleton(STATE_ROOT)
    if singleton is None:
        print(
            f"VALUE: another VALUE backend already uses the data directory {STATE_ROOT}; "
            "this one stops without changing anything.",
            file=sys.stderr, flush=True,
        )
        raise SystemExit(EXIT_BACKEND_ALREADY_RUNNING)
    supervisor = run_supervisor()
    try:
        ensure_default_pack()
        # C2: the catalogue (built once at import, fault-isolated) is in place
        # before reconciliation; quarantined local entries are announced
        # here by code only, never with a path.
        refresh_module_catalog(refresh=False)
        status, reasons = health_degradation()
        if reasons:
            print("VALUE started degraded: " + ", ".join(
                f"{item['code']} x{item['count']}" for item in reasons
            ) + " (see Modules, or the offline module_recovery tool: user guide 'Offline module recovery')",
                  flush=True)
        report = supervisor.reconcile_all(extra_steps=[_startup_quota_repairs])
        if report.settled or report.repaired or report.unverifiable:
            print("VALUE run reconciliation: " + json.dumps(report.to_dict(), ensure_ascii=False), flush=True)
        workbench_root = resolve_data_workbench_root(STATE_ROOT)
        workbench = DataWorkbenchApi(
            LocalDataWorkbenchService(workbench_root),
            SQLiteJobStore(workbench_root / "jobs.sqlite"),
        )
        session_token = new_token()
        server = make_api_server(args.host, args.port, session_token=session_token, data_workbench_api=workbench)
        bound_port = int(server.server_address[1])
        # The token goes only to the 0600 session file (never to stdout, the
        # command line or a worker environment); the UI gateway reads it there.
        session_file = publish_session(STATE_ROOT, bound_port, session_token)
        try:
            supervisor.start()
            for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
                number = getattr(signal, name, None)
                if number is not None:
                    signal.signal(number, _raise_keyboard_interrupt)
            print(f"VALUE modular API: http://{args.host}:{bound_port} (session file {session_file})", flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            # A stop signal may arrive at any point once the handlers are in
            # place (also between the ready line and serve_forever).
            pass
        finally:
            # Launchers and process groups often deliver a second SIGTERM;
            # it must not interrupt the shutdown (stale session file, traceback).
            _ignore_stop_signals()
            withdraw_session(STATE_ROOT, bound_port, session_token)
            server.server_close()
    finally:
        # Queued failed-provenance seals get a bounded time; whatever is left
        # is re-queued by the next start's reconciliation.
        supervisor.stop(seal_timeout=SHUTDOWN_SEAL_SECONDS)
        background = supervisor.background_runs()
        if background:
            print(
                f"VALUE: {len(background)} run(s) continue in the background and will be "
                "supervised again when VALUE next starts: " + ", ".join(background),
                flush=True,
            )
        singleton.release()


if __name__ == "__main__":
    main()
