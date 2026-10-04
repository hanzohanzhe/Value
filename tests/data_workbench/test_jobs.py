from __future__ import annotations

from pathlib import Path

import pytest

from gridform_core.data_workbench.jobs import JobCancelled, SQLiteJobStore, WorkbenchJobRunner


def test_durable_job_transitions_and_restart_recovery(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite", clock=lambda: "2026-08-21T10:00:00Z")
    queued = store.create("discover", {"registry_id": "uk-network"}, job_id="job-1")
    assert queued["status"] == "queued"
    store.transition("job-1", "running", progress=0.25)
    store.request_cancel("job-1")
    assert store.read("job-1")["status"] == "cancel_requested"

    restarted = SQLiteJobStore(tmp_path / "jobs.sqlite", clock=lambda: "2026-08-21T10:05:00Z")
    recovered = restarted.recover_incomplete()
    assert recovered == ["job-1"]
    assert restarted.read("job-1")["status"] == "cancelled"
    assert restarted.read("job-1")["result"] is None


def test_runner_covers_completed_failed_and_cooperative_cancelled(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    runner = WorkbenchJobRunner(store)

    store.create("validate", {}, job_id="complete")
    assert runner.run("complete", lambda cancelled: {"ok": not cancelled()})["status"] == "completed"

    store.create("validate", {}, job_id="failed")
    failed = runner.run("failed", lambda cancelled: (_ for _ in ()).throw(ValueError("bad candidate")))
    assert failed["status"] == "failed"
    assert failed["error_code"] == "DW_JOB_VALUEERROR"

    store.create("fetch", {}, job_id="cancelled")
    store.request_cancel("cancelled")
    cancelled = runner.run(
        "cancelled",
        lambda is_cancelled: (_ for _ in ()).throw(JobCancelled()) if is_cancelled() else {"receipt": "bad"},
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["result"] is None


def test_job_input_rejects_absolute_paths_and_unknown_transition(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    with pytest.raises(ValueError, match="absolute path"):
        store.create("compile", {"input": "C:/private/source.csv"})
    store.create("compile", {}, job_id="job")
    with pytest.raises(ValueError, match="transition"):
        store.transition("job", "completed")
