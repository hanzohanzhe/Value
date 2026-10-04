"""Bind complete execution evidence to the frozen project and worker admission."""
from __future__ import annotations

import json
from pathlib import Path

from backend.frozen_run_recovery import json_hash, read_object, verify_recovered_configuration
from gridform_core.execution_archive import capture_execution_bundle, verify_execution_bundle


def current_execution(*, source_root: Path, data_home: Path, archive: bool = False) -> dict:
    return capture_execution_bundle(source_root=source_root, data_home=data_home,
                                    archive_root=data_home / "execution-archives", archive=archive)


def bind_run_execution(project: dict, run_root: Path, record: dict) -> dict:
    verify_recovered_configuration(project, execution_identity=record["identity_sha256"])
    value = json.loads(json.dumps(project))
    value.setdefault("extensions", {})["execution_bundle"] = {
        "schema_version": "value.execution-bundle-reference/v1",
        "identity_sha256": record["identity_sha256"], "source_sha256": record["source_sha256"],
        "environment_sha256": record["environment_sha256"], "record_sha256": json_hash(record),
    }
    path = run_root / "execution-bundle.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return value


def verify_run_execution(run_root: Path, project: dict, *, source_root: Path,
                         data_home: Path, require_record: bool = False) -> dict | None:
    reference = dict(project.get("extensions") or {}).get("execution_bundle")
    if reference is None:
        if require_record:
            raise ValueError("This historical Run lacks a complete source/environment identity. Review frozen-input migration to create a fresh Run.")
        return None
    if not isinstance(reference, dict):
        raise ValueError("Invalid execution archive reference")
    recorded = read_object(run_root / "execution-bundle.json")
    if (json_hash(recorded) != reference.get("record_sha256")
            or recorded.get("identity_sha256") != reference.get("identity_sha256")):
        raise ValueError("The execution archive record does not match the frozen project")
    verify_execution_bundle(recorded, archive_root=data_home / "execution-archives")
    current = current_execution(source_root=source_root, data_home=data_home)
    if current["identity_sha256"] != recorded["identity_sha256"]:
        raise ValueError("Execution source or runtime changed after enqueue; restore the recorded execution or review a new migration.")
    verify_recovered_configuration(project, execution_identity=current["identity_sha256"])
    return recorded
