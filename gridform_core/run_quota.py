"""Disk reservations and headroom checks for run snapshot/output creation."""

from __future__ import annotations

import json
import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class RunQuotaPolicy:
    global_quota_bytes: int = 100 * 1024**3
    per_run_quota_bytes: int = 20 * 1024**3
    minimum_free_bytes: int = 2 * 1024**3
    schema_version: str = "value.run-quota-policy/v1"


# Retain the pre-Prompt122 import name for existing callers.
QuotaPolicy = RunQuotaPolicy


def output_reservation_bytes(
    estimates: Mapping[str, object],
    *,
    default_bytes: int = 512 * 1024**2,
) -> int:
    """Return the estimated run output that must be reserved.

    Snapshot resource estimates keep the volume safety reserve separate from
    the persisted and temporary output.  The safety reserve is checked by the
    resource gate and must not be counted as one run's output quota.
    """

    if "persisted_bytes" in estimates or "temporary_bytes" in estimates:
        persisted = int(estimates.get("persisted_bytes") or 0)
        temporary = int(estimates.get("temporary_bytes") or 0)
        required = persisted + temporary
    elif estimates.get("disk_bytes") is not None:
        required = int(estimates["disk_bytes"])
    elif estimates.get("required_bytes") is not None:
        required = int(estimates["required_bytes"])
    else:
        required = int(default_bytes)
    if required < 0:
        raise ValueError("estimated output bytes must be non-negative")
    return required


def _reservations(root: Path) -> int:
    total = 0
    for path in root.glob("*/reservation.json"):
        try:
            total += int(json.loads(path.read_text(encoding="utf-8")).get("reserved_bytes", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return total


@contextmanager
def _reservation_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".reservation.lock"
    deadline = time.monotonic() + 5.0
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(
                lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out acquiring the run reservation lock")
            time.sleep(0.01)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def _existing_run_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(
        path.stat().st_size
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"reservation.json", ".reservation.lock"}
    )


def reserve_run_space(
    runs_root: Path,
    run_id: str,
    required_bytes: int,
    *,
    policy: RunQuotaPolicy = RunQuotaPolicy(),
) -> dict[str, object]:
    required = int(required_bytes)
    if required < 0:
        raise ValueError("required_bytes must be non-negative")
    with _reservation_lock(runs_root):
        existing_size = _existing_run_bytes(runs_root)
        reserved = _reservations(runs_root)
        free = shutil.disk_usage(runs_root).free
        reasons = []
        if required > policy.per_run_quota_bytes:
            reasons.append("per_run_quota_exceeded")
        if existing_size + reserved + required > policy.global_quota_bytes:
            reasons.append("global_quota_exceeded")
        if free - required < policy.minimum_free_bytes:
            reasons.append("minimum_free_space_floor")
        report = {
            "schema_version": "value.run-space-reservation/v1", "run_id": run_id,
            "accepted": not reasons, "required_bytes": required, "available_bytes": free,
            "already_reserved_bytes": reserved, "existing_run_bytes": existing_size,
            "minimum_free_bytes": policy.minimum_free_bytes,
            "global_quota_bytes": policy.global_quota_bytes,
            "per_run_quota_bytes": policy.per_run_quota_bytes, "reason_codes": reasons,
        }
        if reasons:
            return report
        directory = runs_root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "reservation.json.tmp"
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(report | {"reserved_bytes": required}, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(directory / "reservation.json")
        return report


def verify_annual_headroom(run_root: Path, additional_bytes: int = 64 * 1024**2, *, policy: RunQuotaPolicy = RunQuotaPolicy()) -> dict[str, object]:
    free = shutil.disk_usage(run_root).free
    size = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file())
    accepted = size + additional_bytes <= policy.per_run_quota_bytes and free - additional_bytes >= policy.minimum_free_bytes
    return {
        "accepted": accepted, "current_run_bytes": size, "required_additional_bytes": additional_bytes,
        "available_bytes": free, "minimum_free_bytes": policy.minimum_free_bytes,
        "reason_code": None if accepted else "GF_RUN_ANNUAL_DISK_HEADROOM",
    }
