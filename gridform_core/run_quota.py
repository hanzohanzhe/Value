"""Disk reservations and headroom checks for run snapshot/output creation."""

from __future__ import annotations

import json
import os
import shutil
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from backend.lifecycle.atomic_io import atomic_write_json
from backend.lifecycle.file_locks import hold_lock
from backend.lifecycle.states import ACTIVE_STATES, UNKNOWN, classify


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


RESERVATION_FILE = "reservation.json"
RESERVATION_LOCK = ".reservation.lock"
RESERVATION_LOCK_TIMEOUT_SECONDS = 5.0
RESERVATION_SCHEMA = "value.run-space-reservation/v2"
ACCOUNTING_BASIS = "physical-bytes-unique-inodes/v1"
# Every file on disk counts, reservation records included (they are bytes
# too); only the root lock file is bookkeeping.
_NOT_COUNTED = {RESERVATION_LOCK}


@dataclass(frozen=True)
class QuotaUsage:
    """Read-only quota picture of a runs root (F5-04, R1-03).

    ``existing_run_bytes`` counts every regular file under the runs root once
    per (st_dev, st_ino), so hard-linked copies are not double counted.
    ``outstanding_reserved_bytes`` counts, for active runs only (a missing or
    unreadable status counts as active: it may be a run being created), the part of the
    reservation not yet written: max(0, reserved - model-output bytes).
    Completed, failed, cancelled and archived runs hold no reservation.
    """

    existing_run_bytes: int
    outstanding_reserved_bytes: int
    active_runs: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "accounting_basis": ACCOUNTING_BASIS,
            "existing_run_bytes": self.existing_run_bytes,
            "outstanding_reserved_bytes": self.outstanding_reserved_bytes,
            "active_reservations": [dict(row) for row in self.active_runs],
        }


def _unique_bytes(root: Path, seen: set[tuple[int, int]]) -> int:
    total = 0
    if not root.is_dir():
        return 0
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in files:
            if name in _NOT_COUNTED:
                continue
            try:
                info = os.lstat(os.path.join(directory, name))
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            key = (info.st_dev, info.st_ino)
            if key in seen:
                continue
            seen.add(key)
            total += info.st_size
    return total


def _run_state(run_dir: Path) -> str | None:
    """The run's state, ``unknown`` when unreadable, ``None`` when missing."""

    try:
        value = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return UNKNOWN
    return classify(value)


def _reserved_bytes(run_dir: Path) -> int:
    try:
        value = json.loads((run_dir / RESERVATION_FILE).read_text(encoding="utf-8"))
        return max(0, int(value.get("reserved_bytes", 0)))
    except FileNotFoundError:
        return 0
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def run_outstanding_bytes(run_dir: Path) -> tuple[int, int, int]:
    """(reserved, written, outstanding) for one run's own reservation."""

    reserved = _reserved_bytes(run_dir)
    written = _unique_bytes(run_dir / "model-output", set())
    return reserved, written, max(0, reserved - written)


def quota_usage(runs_root: Path, *, exclude_run: str | None = None) -> QuotaUsage:
    """Read-only: never creates, locks or writes anything under ``runs_root``.

    ``exclude_run`` leaves that run's own reservation out of the outstanding
    total (a reservation or resume being decided for it); its bytes on disk
    still count as existing.
    """

    runs_root = Path(runs_root)
    seen: set[tuple[int, int]] = set()
    existing = 0
    outstanding = 0
    active: list[dict[str, object]] = []
    if runs_root.is_dir():
        for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir() and not path.is_symlink()):
            existing += _unique_bytes(run_dir, seen)
            if run_dir.name == exclude_run:
                continue
            state = _run_state(run_dir)
            # Missing (being created) and unreadable statuses keep their
            # reservation: the conservative reading of an unknown run.
            if state is not None and state != UNKNOWN and state not in ACTIVE_STATES:
                continue
            reserved, written, remaining = run_outstanding_bytes(run_dir)
            if reserved:
                outstanding += remaining
                active.append({"run_id": run_dir.name, "status": state or "missing",
                               "reserved_bytes": reserved, "written_bytes": written,
                               "outstanding_bytes": remaining})
    return QuotaUsage(existing, outstanding, tuple(active))


def global_quota_reasons(
    usage: QuotaUsage,
    required_bytes: int,
    policy: RunQuotaPolicy = RunQuotaPolicy(),
) -> list[str]:
    """The one quota rule shared by reservation, both preflight branches,
    snapshot readiness and resume (free-space criteria stay with each caller;
    unifying them is P1 R2-05)."""

    reasons: list[str] = []
    if int(required_bytes) > policy.per_run_quota_bytes:
        reasons.append("per_run_quota_exceeded")
    if usage.existing_run_bytes + usage.outstanding_reserved_bytes + int(required_bytes) > policy.global_quota_bytes:
        reasons.append("global_quota_exceeded")
    return reasons


QUOTA_CORRECTIVE_ACTIONS = (
    "Move older runs to the trash: completed runs keep their files and the trash frees their bytes; archiving does not.",
    "Free disk space or choose a smaller output (Summary trace).",
)


@contextmanager
def _reservation_lock(root: Path):
    """Advisory lock released by the OS if the holder dies (R1-13).

    A stale lock file never blocks: lock files are not unlinked by the
    holder.  ``LockTimeout`` (an OSError) after 5 s maps to HTTP 503.
    """

    root.mkdir(parents=True, exist_ok=True)
    with hold_lock(root / RESERVATION_LOCK, timeout=RESERVATION_LOCK_TIMEOUT_SECONDS):
        yield


def _existing_run_bytes(root: Path) -> int:
    return quota_usage(root).existing_run_bytes


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
        usage = quota_usage(runs_root, exclude_run=run_id)
        free = shutil.disk_usage(runs_root).free
        reasons = global_quota_reasons(usage, required, policy)
        if free - required < policy.minimum_free_bytes:
            reasons.append("minimum_free_space_floor")
        report = {
            "schema_version": RESERVATION_SCHEMA, "run_id": run_id,
            "accepted": not reasons, "required_bytes": required, "available_bytes": free,
            "already_reserved_bytes": usage.outstanding_reserved_bytes,
            "outstanding_reserved_bytes": usage.outstanding_reserved_bytes,
            "existing_run_bytes": usage.existing_run_bytes,
            "accounting_basis": ACCOUNTING_BASIS,
            "minimum_free_bytes": policy.minimum_free_bytes,
            "global_quota_bytes": policy.global_quota_bytes,
            "per_run_quota_bytes": policy.per_run_quota_bytes, "reason_codes": reasons,
        }
        if reasons:
            report["corrective_actions"] = list(QUOTA_CORRECTIVE_ACTIONS)
            return report
        directory = runs_root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(directory / RESERVATION_FILE, report | {"reserved_bytes": required})
        return report


def remove_legacy_reservation_lock(runs_root: Path) -> bool:
    """Start-up only (the backend singleton is held): drop a pre-P0-3 O_EXCL
    lock file, which may still contain a dead process id."""

    path = Path(runs_root) / RESERVATION_LOCK
    try:
        if path.is_file() and path.stat().st_size > 0:
            path.unlink()
            return True
    except OSError:
        return False
    return False


def quarantine_orphan_run_directories(runs_root: Path, trash_root: Path) -> list[str]:
    """Start-up only: run directories without status.json (left by a crashed
    pre-P0-3 start) move to ``trash/orphan-runs`` so that they are visible,
    recoverable and no longer silently counted."""

    moved: list[str] = []
    runs_root = Path(runs_root)
    if not runs_root.is_dir():
        return moved
    destination_root = Path(trash_root) / "orphan-runs"
    for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir() and not path.is_symlink()):
        if (run_dir / "status.json").exists():
            continue
        destination_root.mkdir(parents=True, exist_ok=True)
        target = destination_root / f"{run_dir.name}-{time.strftime('%Y%m%d-%H%M%S')}"
        suffix = 1
        while target.exists():
            suffix += 1
            target = destination_root / f"{run_dir.name}-{time.strftime('%Y%m%d-%H%M%S')}-{suffix}"
        try:
            os.rename(run_dir, target)
        except OSError:
            continue
        moved.append(run_dir.name)
    return moved


def verify_annual_headroom(run_root: Path, additional_bytes: int = 64 * 1024**2, *, policy: RunQuotaPolicy = RunQuotaPolicy()) -> dict[str, object]:
    free = shutil.disk_usage(run_root).free
    size = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file())
    accepted = size + additional_bytes <= policy.per_run_quota_bytes and free - additional_bytes >= policy.minimum_free_bytes
    return {
        "accepted": accepted, "current_run_bytes": size, "required_additional_bytes": additional_bytes,
        "available_bytes": free, "minimum_free_bytes": policy.minimum_free_bytes,
        "reason_code": None if accepted else "GF_RUN_ANNUAL_DISK_HEADROOM",
    }
