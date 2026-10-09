"""Recoverable lifecycle operations for immutable VALUE Studies.

The service owns filesystem validation, audit records and rollback. HTTP and UI
layers decide how to present confirmation and dependency-readiness messages.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.lifecycle.states import ACTIVE_STATES as ACTIVE_RUN_STATUSES


SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class StudyLifecycleError(ValueError):
    """A recoverable Study lifecycle request violates the local state contract."""


def _read_json(path: Path, fallback: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # includes JSON and non-UTF-8 decoding (F5-05)
        return fallback


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _safe_child(root: Path, child_id: str, label: str) -> Path:
    if not SAFE_ID.fullmatch(child_id):
        raise StudyLifecycleError(f"Invalid {label} ID")
    candidate = root / child_id
    if candidate.resolve().parent != root.resolve():
        raise StudyLifecycleError(f"Refusing {label} path outside its state root")
    return candidate


def _path_in_trash(path: Path, trash_root: Path, label: str) -> Path:
    try:
        path.resolve().relative_to(trash_root.resolve())
    except (OSError, ValueError) as error:
        raise StudyLifecycleError(
            f"Refusing {label} path outside recoverable trash"
        ) from error
    return path


def _linked_runs(runs_root: Path, project_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for status_path in sorted(runs_root.glob("*/status.json")):
        status = _read_json(status_path, {})
        if isinstance(status, dict) and str(status.get("project_id") or "") == project_id:
            rows.append(status)
    return rows


def _batch_entries(trash_root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for record_path in sorted(
        trash_root.glob("value-101-reset/*/study-records/*.json")
    ):
        record = _read_json(record_path, {})
        if not isinstance(record, dict) or record.get("restored_at"):
            continue
        stored_path = Path(str(record.get("stored_path") or ""))
        if stored_path.is_dir():
            entries.append({**record, "legacy": False})
    return entries


def _legacy_entries(trash_root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for study_path in sorted(
        trash_root.glob("value-101-reset/*/studies/*/project.json")
    ):
        project = _read_json(study_path, {})
        if not isinstance(project, dict):
            continue
        study_id = str(project.get("id") or study_path.parent.name)
        reset_root = study_path.parents[2]
        if (reset_root / "study-records" / f"{study_id}.json").is_file():
            continue
        linked_ids: list[str] = []
        for status_path in sorted((reset_root / "runs").glob("*/status.json")):
            status = _read_json(status_path, {})
            if isinstance(status, dict) and str(status.get("project_id") or "") == study_id:
                linked_ids.append(str(status.get("id") or status_path.parent.name))
        timestamp = reset_root.name
        entries.append(
            {
                "schema_version": "value.study-trash/v1",
                "trash_id": f"legacy-value-101-reset--{timestamp}--{study_id}",
                "study_id": study_id,
                "study_name": str(project.get("name") or study_id),
                "deleted_at": timestamp,
                "reason_code": "value_101_reset",
                "reason": "VALUE 101 reset",
                "original_path": "",
                "stored_path": str(study_path.parent),
                "revision_sha256": str(project.get("revision_sha256") or ""),
                "revision_count": len(list((study_path.parent / "revisions").glob("*.json"))),
                "linked_run_ids": linked_ids,
                "linked_run_count": len(linked_ids),
                "recoverable": True,
                "legacy": True,
            }
        )
    return entries


def list_study_trash(
    projects_root: Path, runs_root: Path, trash_root: Path
) -> list[dict[str, object]]:
    """List recoverable Study entries, including the pre-v1 VALUE 101 layout."""

    del projects_root, runs_root  # identities are retained for a stable service API
    entries: list[dict[str, object]] = []
    for record_path in sorted(trash_root.glob("studies/*/trash-record.json")):
        record = _read_json(record_path, {})
        if not isinstance(record, dict):
            continue
        stored_path = Path(str(record.get("stored_path") or ""))
        if record.get("restored_at") or not stored_path.is_dir():
            continue
        entries.append({**record, "legacy": False})
    entries.extend(_batch_entries(trash_root))
    entries.extend(_legacy_entries(trash_root))
    return sorted(
        entries,
        key=lambda item: str(item.get("deleted_at") or ""),
        reverse=True,
    )


def study_id_is_reserved(
    project_id: str, *, projects_root: Path, trash_root: Path
) -> bool:
    """Return true while an ID is active or recoverable from trash."""

    active = _safe_child(projects_root, project_id, "Study")
    if active.is_dir():
        return True
    for record_path in trash_root.glob("studies/*/trash-record.json"):
        record = _read_json(record_path, {})
        if not isinstance(record, dict) or record.get("restored_at"):
            continue
        if str(record.get("study_id") or "") == project_id and Path(
            str(record.get("stored_path") or "")
        ).is_dir():
            return True
    return any(
        path.parent.name == project_id
        for path in trash_root.glob("value-101-reset/*/studies/*/project.json")
    )


def move_study_to_trash(
    project_id: str,
    *,
    projects_root: Path,
    runs_root: Path,
    trash_root: Path,
    confirmation_name: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Move a complete Study directory into recoverable local trash."""

    source = _safe_child(projects_root, project_id, "Study")
    project_path = source / "project.json"
    project = _read_json(project_path, {})
    if not source.is_dir() or not isinstance(project, dict) or not project:
        raise StudyLifecycleError(f"Study not found: {project_id}")
    study_name = str(project.get("name") or project_id)
    linked_runs = _linked_runs(runs_root, project_id)
    active = [
        str(row.get("id") or "unknown")
        for row in linked_runs
        if str(row.get("status") or "") in ACTIVE_RUN_STATUSES
    ]
    if active:
        raise StudyLifecycleError(
            "Cancel or finish the active Run before moving this Study to trash: "
            + ", ".join(active)
        )
    if linked_runs and confirmation_name != study_name:
        raise StudyLifecycleError(
            f'Type the exact Study name to confirm: "{study_name}"'
        )

    timestamp = datetime.now().astimezone()
    trash_id = f"study-{project_id}-{timestamp.strftime('%Y%m%d-%H%M%S-%f')}"
    entry_root = _safe_child(trash_root / "studies", trash_id, "trash")
    stored_path = entry_root / "study" / project_id
    record: dict[str, object] = {
        "schema_version": "value.study-trash/v1",
        "trash_id": trash_id,
        "study_id": project_id,
        "study_name": study_name,
        "deleted_at": timestamp.isoformat(timespec="seconds"),
        "reason_code": "user_requested",
        "reason": (reason or "").strip() or "user_requested",
        "original_path": str(source),
        "stored_path": str(stored_path),
        "revision_sha256": str(project.get("revision_sha256") or ""),
        "revision_count": len(list((source / "revisions").glob("*.json"))),
        "linked_run_ids": sorted(
            str(row.get("id") or "") for row in linked_runs if row.get("id")
        ),
        "linked_run_count": len(linked_runs),
        "recoverable": True,
    }
    moved = False
    try:
        stored_path.parent.mkdir(parents=True, exist_ok=False)
        shutil.move(str(source), str(stored_path))
        moved = True
        _atomic_json(entry_root / "trash-record.json", record)
    except Exception as error:
        if moved and stored_path.exists() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stored_path), str(source))
        shutil.rmtree(entry_root, ignore_errors=True)
        if isinstance(error, StudyLifecycleError):
            raise
        raise StudyLifecycleError(f"Unable to move Study to trash: {error}") from error
    return record


def move_value_101_records_to_trash(
    study_paths: list[Path],
    run_paths: list[Path],
    *,
    projects_root: Path,
    runs_root: Path,
    trash_root: Path,
) -> dict[str, object]:
    """Atomically move a VALUE 101 teaching cohort into audited trash."""

    studies: list[tuple[Path, dict[str, object]]] = []
    for source in study_paths:
        if source.resolve().parent != projects_root.resolve():
            raise StudyLifecycleError("Refusing a VALUE 101 Study outside its state root")
        project = _read_json(source / "project.json", {})
        if not isinstance(project, dict):
            raise StudyLifecycleError(f"VALUE 101 Study is unreadable: {source.name}")
        studies.append((source, project))
    run_statuses: list[tuple[Path, dict[str, object]]] = []
    for source in run_paths:
        if source.resolve().parent != runs_root.resolve():
            raise StudyLifecycleError("Refusing a VALUE 101 Run outside its state root")
        status = _read_json(source / "status.json", {})
        if not isinstance(status, dict):
            raise StudyLifecycleError(f"VALUE 101 Run is unreadable: {source.name}")
        if str(status.get("status") or "") in ACTIVE_RUN_STATUSES:
            raise StudyLifecycleError(
                "Cancel active VALUE 101 runs before reset: "
                + str(status.get("id") or source.name)
            )
        run_statuses.append((source, status))

    timestamp = datetime.now().astimezone()
    reset_id = timestamp.strftime("%Y%m%d-%H%M%S-%f")
    reset_root = trash_root / "value-101-reset" / reset_id
    moves: list[tuple[Path, Path]] = []
    records: list[dict[str, object]] = []
    for source, project in studies:
        study_id = str(project.get("id") or source.name)
        _safe_child(projects_root, study_id, "Study")
        if study_id != source.name:
            raise StudyLifecycleError(
                "VALUE 101 Study ID does not match its state directory"
            )
        linked = [
            (run_source, status)
            for run_source, status in run_statuses
            if str(status.get("project_id") or "") == study_id
        ]
        stored_path = reset_root / "studies" / study_id
        stored_runs = {
            str(status.get("id") or run_source.name): str(
                reset_root / "runs" / run_source.name
            )
            for run_source, status in linked
        }
        records.append(
            {
                "schema_version": "value.study-trash/v1",
                "trash_id": f"batch-value-101-reset--{reset_id}--{study_id}",
                "study_id": study_id,
                "study_name": str(project.get("name") or study_id),
                "deleted_at": timestamp.isoformat(timespec="seconds"),
                "reason_code": "value_101_reset",
                "reason": "VALUE 101 reset",
                "original_path": str(source),
                "stored_path": str(stored_path),
                "revision_sha256": str(project.get("revision_sha256") or ""),
                "revision_count": len(list((source / "revisions").glob("*.json"))),
                "linked_run_ids": sorted(stored_runs),
                "linked_run_count": len(stored_runs),
                "stored_run_paths": stored_runs,
                "recoverable": True,
            }
        )
        moves.append((source, stored_path))
    for source, _status in run_statuses:
        moves.append((source, reset_root / "runs" / source.name))

    completed: list[tuple[Path, Path]] = []
    try:
        for source, destination in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise StudyLifecycleError(f"Trash target already exists: {destination}")
            shutil.move(str(source), str(destination))
            completed.append((source, destination))
        for record in records:
            _atomic_json(
                reset_root / "study-records" / f"{record['study_id']}.json", record
            )
        _atomic_json(
            reset_root / "trash-record.json",
            {
                "schema_version": "value.study-trash-batch/v1",
                "trash_id": f"value-101-reset-{reset_id}",
                "deleted_at": timestamp.isoformat(timespec="seconds"),
                "reason_code": "value_101_reset",
                "study_ids": [str(record["study_id"]) for record in records],
                "run_ids": [
                    str(status.get("id") or source.name)
                    for source, status in run_statuses
                ],
                "recoverable": True,
            },
        )
    except Exception as error:
        rollback_errors: list[str] = []
        for source, destination in reversed(completed):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            except Exception as rollback_error:  # pragma: no cover - catastrophic I/O
                rollback_errors.append(f"{destination} -> {source}: {rollback_error}")
        if not rollback_errors:
            shutil.rmtree(reset_root, ignore_errors=True)
        if rollback_errors:
            raise RuntimeError(
                "VALUE 101 reset failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
                + f". Recoverable records remain under {reset_root}"
            ) from error
        raise

    return {
        "schema_version": "value.study-trash-batch/v1",
        "deleted_study_ids": [str(record["study_id"]) for record in records],
        "deleted_run_ids": [
            str(status.get("id") or source.name) for source, status in run_statuses
        ],
        "deleted_report_ids": [],
        "recoverable": True,
        "trash_location": str(reset_root) if moves else None,
        "trash_entries": records,
        "browser_progress_action": "delete value.101.progress.v1 in this browser",
    }


def _find_trash_entry(
    trash_id: str, trash_root: Path
) -> tuple[Path | None, dict[str, object]]:
    new_root = _safe_child(trash_root / "studies", trash_id, "trash")
    record = _read_json(new_root / "trash-record.json", {})
    if isinstance(record, dict) and record:
        return new_root / "trash-record.json", record
    batch_prefix = "batch-value-101-reset--"
    if trash_id.startswith(batch_prefix):
        remainder = trash_id[len(batch_prefix) :]
        timestamp, separator, project_id = remainder.partition("--")
        if separator and SAFE_ID.fullmatch(timestamp) and SAFE_ID.fullmatch(project_id):
            record_path = (
                trash_root / "value-101-reset" / timestamp / "study-records"
                / f"{project_id}.json"
            )
            record = _read_json(record_path, {})
            if isinstance(record, dict) and record:
                return record_path, record
    prefix = "legacy-value-101-reset--"
    if trash_id.startswith(prefix):
        remainder = trash_id[len(prefix) :]
        timestamp, separator, project_id = remainder.partition("--")
        if separator and SAFE_ID.fullmatch(timestamp) and SAFE_ID.fullmatch(project_id):
            stored = trash_root / "value-101-reset" / timestamp / "studies" / project_id
            project = _read_json(stored / "project.json", {})
            if isinstance(project, dict) and project:
                stored_runs = {}
                for status_path in sorted((stored.parents[1] / "runs").glob("*/status.json")):
                    status = _read_json(status_path, {})
                    if isinstance(status, dict) and str(status.get("project_id") or "") == project_id:
                        run_id = str(status.get("id") or status_path.parent.name)
                        stored_runs[run_id] = str(status_path.parent)
                return None, {
                    "schema_version": "value.study-trash/v1",
                    "trash_id": trash_id,
                    "study_id": project_id,
                    "study_name": str(project.get("name") or project_id),
                    "stored_path": str(stored),
                    "original_path": "",
                    "stored_run_paths": stored_runs,
                    "linked_run_ids": sorted(stored_runs),
                    "legacy": True,
                }
    raise StudyLifecycleError(f"Trash entry not found: {trash_id}")


def restore_study(
    trash_id: str, *, projects_root: Path, runs_root: Path, trash_root: Path
) -> dict[str, object]:
    """Restore a Study exactly as stored; dependency validation remains separate."""

    record_path, record = _find_trash_entry(trash_id, trash_root)
    project_id = str(record.get("study_id") or "")
    destination = _safe_child(projects_root, project_id, "Study")
    if destination.exists():
        raise StudyLifecycleError(
            f"Cannot restore {project_id}: an active Study already uses that ID"
        )
    raw_linked_run_ids = record.get("linked_run_ids") or []
    if not isinstance(raw_linked_run_ids, list):
        raise StudyLifecycleError("Stored Run inventory is malformed")
    linked_run_ids = [str(item) for item in raw_linked_run_ids]
    owned_reset_root: Path | None = None
    if trash_id.startswith("study-"):
        entry_root = _safe_child(trash_root / "studies", trash_id, "trash")
        stored_path = entry_root / "study" / project_id
        if record_path != entry_root / "trash-record.json":
            raise StudyLifecycleError("Study trash record is not owned by this entry")
        if record.get("stored_run_paths"):
            raise StudyLifecycleError("Ordinary Study trash cannot own Run directories")
        stored_run_paths: dict[str, Path] = {}
    elif trash_id.startswith("batch-value-101-reset--"):
        remainder = trash_id[len("batch-value-101-reset--") :]
        timestamp, separator, encoded_project_id = remainder.partition("--")
        if not separator or encoded_project_id != project_id:
            raise StudyLifecycleError("VALUE 101 trash identity is inconsistent")
        reset_root = _safe_child(
            trash_root / "value-101-reset", timestamp, "VALUE 101 reset"
        )
        owned_reset_root = reset_root
        expected_record = reset_root / "study-records" / f"{project_id}.json"
        if record_path != expected_record:
            raise StudyLifecycleError("VALUE 101 trash record is not owned by this entry")
        stored_path = reset_root / "studies" / project_id
        stored_run_paths = {
            run_id: _safe_child(reset_root / "runs", run_id, "Run")
            for run_id in linked_run_ids
        }
    elif trash_id.startswith("legacy-value-101-reset--"):
        remainder = trash_id[len("legacy-value-101-reset--") :]
        timestamp, separator, encoded_project_id = remainder.partition("--")
        if not separator or encoded_project_id != project_id:
            raise StudyLifecycleError("Legacy VALUE 101 trash identity is inconsistent")
        reset_root = _safe_child(
            trash_root / "value-101-reset", timestamp, "VALUE 101 reset"
        )
        owned_reset_root = reset_root
        stored_path = reset_root / "studies" / project_id
        stored_run_paths = {
            run_id: _safe_child(reset_root / "runs", run_id, "Run")
            for run_id in linked_run_ids
        }
    else:
        raise StudyLifecycleError("Unknown Study trash identity")
    _path_in_trash(stored_path, trash_root, "stored Study")
    declared_stored_path = _path_in_trash(
        Path(str(record.get("stored_path") or "")), trash_root, "stored Study"
    )
    if declared_stored_path.resolve() != stored_path.resolve():
        raise StudyLifecycleError("Stored Study path is not owned by this trash entry")
    if owned_reset_root is not None:
        raw_stored_run_paths = record.get("stored_run_paths") or {}
        if not isinstance(raw_stored_run_paths, dict):
            raise StudyLifecycleError("Stored Run inventory is malformed")
        declared_run_paths = {
            str(run_id): Path(str(path))
            for run_id, path in raw_stored_run_paths.items()
        }
        if set(declared_run_paths) != set(linked_run_ids):
            raise StudyLifecycleError("Stored Run inventory does not match linked Run IDs")
        for run_id, declared_path in declared_run_paths.items():
            _path_in_trash(declared_path, trash_root, "stored Run")
            if declared_path.resolve() != stored_run_paths[run_id].resolve():
                raise StudyLifecycleError(
                    f"Stored Run path is not owned by this trash entry: {run_id}"
                )
        owned_run_ids: set[str] = set()
        for status_path in (owned_reset_root / "runs").glob("*/status.json"):
            status = _read_json(status_path, {})
            if str((status or {}).get("project_id") or "") == project_id:
                owned_run_ids.add(str((status or {}).get("id") or status_path.parent.name))
        if owned_run_ids != set(linked_run_ids):
            raise StudyLifecycleError(
                "Stored Run inventory does not match the owned reset directory"
            )
    if not stored_path.is_dir():
        raise StudyLifecycleError(f"Stored Study is missing: {project_id}")
    for run_id, stored_run_path in stored_run_paths.items():
        _path_in_trash(stored_run_path, trash_root, "stored Run")
        if not stored_run_path.is_dir():
            raise StudyLifecycleError(
                f"Stored Run is missing; restore remains unchanged: {run_id}"
            )
        status = _read_json(stored_run_path / "status.json", {})
        if str((status or {}).get("project_id") or "") != project_id:
            raise StudyLifecycleError(
                f"Stored Run does not belong to Study {project_id}: {run_id}"
            )
        if _safe_child(runs_root, run_id, "Run").exists():
            raise StudyLifecycleError(
                f"Cannot restore {project_id}: Run {run_id} already exists"
            )
    moves = [(stored_path, destination)] + [
        (path, _safe_child(runs_root, run_id, "Run"))
        for run_id, path in stored_run_paths.items()
        if path.is_dir()
    ]
    completed: list[tuple[Path, Path]] = []
    try:
        for source, target in moves:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            completed.append((source, target))
        restored_at = datetime.now().astimezone().isoformat(timespec="seconds")
        updated = {
            **record,
            "restored_at": restored_at,
            "restored_path": str(destination),
            "restored_run_ids": sorted(stored_run_paths),
        }
        if record_path is not None:
            _atomic_json(record_path, updated)
        return updated
    except Exception as error:
        rollback_errors: list[str] = []
        for source, target in reversed(completed):
            try:
                if target.exists() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    target.rename(source)
            except Exception as rollback_error:  # pragma: no cover - catastrophic I/O
                rollback_errors.append(f"{target} -> {source}: {rollback_error}")
        if rollback_errors:
            raise RuntimeError(
                "Study restore failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from error
        if isinstance(error, StudyLifecycleError):
            raise
        raise StudyLifecycleError(f"Unable to restore Study: {error}") from error
