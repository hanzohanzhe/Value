from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import time

import pytest

from backend.data_workbench_api import DataWorkbenchApi
from gridform_core.data_workbench.cli import command_names, execute_command
from gridform_core.data_workbench.jobs import SQLiteJobStore


class FakeService:
    def sources(self) -> dict[str, object]:
        return {"schema_version": "value.data-sources/v1", "sources": [{"source_id": "neso.fixture"}]}

    def candidates(self) -> dict[str, object]:
        return {"schema_version": "value.data-candidates/v1", "candidates": []}

    def discover(self, request: dict[str, object]) -> dict[str, object]:
        return {"schema_version": "value.data-discovery-report/v1", "revisions": [], "request": request}

    def validate(self, candidate_id: str) -> dict[str, object]:
        return {"schema_version": "value.data-validation-report/v1", "candidate_id": candidate_id, "status": "passed", "issues": [], "gate_results": {}}

    def promote(self, candidate_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"schema_version": "value.data-signed-bundle-receipt/v1", "candidate_id": candidate_id}


def test_cli_and_api_return_equivalent_source_dto(tmp_path: Path) -> None:
    service = FakeService()
    cli = execute_command(service, ["sources"])
    api = DataWorkbenchApi(service, SQLiteJobStore(tmp_path / "jobs.sqlite"))
    status, payload = api.handle("GET", "/api/data-workbench/v1/sources", None)

    assert status == 200
    assert payload == cli


def test_cli_exposes_all_versioned_subcommands() -> None:
    assert set(command_names()) == {
        "discover", "fetch", "compile", "validate", "candidates", "promote",
        "sources", "diff", "report", "export", "freshness",
    }


def test_api_rejects_path_traversal_missing_review_and_validator_override(tmp_path: Path) -> None:
    api = DataWorkbenchApi(FakeService(), SQLiteJobStore(tmp_path / "jobs.sqlite"))
    status, _ = api.handle("POST", "/api/data-workbench/v1/candidates/../../evil/validate", {})
    assert status == 400

    status, payload = api.handle(
        "POST", "/api/data-workbench/v1/candidates/candidate-123/promote", {"schema_version": "value.data-promotion-request/v1"}
    )
    assert status == 400
    assert payload["error_code"] == "DW_API_PROMOTION_FIELDS"

    status, payload = api.handle(
        "POST",
        "/api/data-workbench/v1/candidates/candidate-123/promote",
        {
            "schema_version": "value.data-promotion-request/v1",
            "candidate_id": "candidate-123",
            "version": "v1",
            "reviewer": "owner",
            "accepted_waivers": [],
            "validation_status": "passed",
        },
    )
    assert status == 400
    assert payload["error_code"] == "DW_API_VALIDATOR_OVERRIDE"

    status, payload = api.handle(
        "POST",
        "/api/data-workbench/v1/candidates/candidate-123/validate",
        {"schema_version": "wrong"},
    )
    assert status == 400
    assert payload["error_code"] == "DW_API_SCHEMA"


def test_api_job_contract_rejects_unknown_schema_and_supports_cancel(tmp_path: Path) -> None:
    api = DataWorkbenchApi(FakeService(), SQLiteJobStore(tmp_path / "jobs.sqlite"))
    status, payload = api.handle(
        "POST",
        "/api/data-workbench/v1/jobs",
        {"schema_version": "wrong", "operation": "discover", "declared_input": {}},
    )
    assert status == 400
    assert payload["error_code"] == "DW_API_SCHEMA"

    status, created = api.handle(
        "POST",
        "/api/data-workbench/v1/jobs",
        {
            "schema_version": "value.data-job-request/v1",
            "operation": "discover",
            "declared_input": {"registry_id": "uk-network"},
        },
    )
    assert status == 202
    job_id = created["job"]["job_id"]
    status, cancelled = api.handle(
        "POST", f"/api/data-workbench/v1/jobs/{job_id}/cancel", {}
    )
    assert status == 200
    assert cancelled["job"]["status"] == "cancel_requested"


def test_api_can_execute_job_in_background_through_same_service(tmp_path: Path) -> None:
    api = DataWorkbenchApi(FakeService(), SQLiteJobStore(tmp_path / "jobs.sqlite"))
    status, created = api.handle(
        "POST",
        "/api/data-workbench/v1/jobs",
        {
            "schema_version": "value.data-job-request/v1",
            "operation": "discover",
            "declared_input": {"source_ids": ["neso.fixture"]},
            "start": True,
        },
    )
    assert status == 202
    job_id = created["job"]["job_id"]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status, response = api.handle("GET", f"/api/data-workbench/v1/jobs/{job_id}", None)
        if response["job"]["status"] == "completed":
            break
        time.sleep(0.01)
    assert status == 200
    assert response["job"]["status"] == "completed"
    assert response["job"]["result"]["schema_version"] == "value.data-discovery-report/v1"


def test_force_data_script_runs_directly_from_checkout() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "force_data.py"), "sources"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["schema_version"] == "value.data-sources/v1"
