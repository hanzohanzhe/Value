"""Atomic first-failure evidence and annual-only v8 recovery plumbing."""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import shutil
import sqlite3
import stat
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import InvariantError
from .module_context import (
    RunStaticContext,
    YearContext,
    canonical_context_sha256,
)
from .market_ledger import (
    MarketLedgerBoundary,
    PERIOD_INDEXED_V8_TABLES,
    _verify_v8_market_prefix_connection,
)
from .market_ownership import MarketLedgerOwnershipLease
from .staged_market_contracts import BalancingInput, contract_sha256
from .v2.contracts import ArtifactReference


FAILURE_BUNDLE_SCHEMA_VERSION = "value.failure-bundle/v1"
FAILURE_BUNDLE_MEMBERS = frozenset({
    "run-context.json", "year-context.json", "period-input.json",
    "solver.json", "residuals.json", "error.json",
})
RECOVERY_AUTHORIZATION_SCHEMA_VERSION = "value.annual-recovery-authorization/v1"
MARKET_RECOVERY_DIAGNOSTIC_SCHEMA_VERSION = (
    "value.market-recovery-diagnostic/v1"
)
RECOVERY_AUTHORIZATION_FIELDS = (
    "schema_version", "run_id", "incomplete_year", "committed_period",
    "checkpoint_state_sha256", "run_context_sha256", "year_context_sha256",
    "source", "issuance_nonce",
)


def recovery_authorization_id(value: Mapping[str, object]) -> str:
    """Return the immutable identity of a scoped one-use recovery grant."""
    payload = {name: value.get(name) for name in RECOVERY_AUTHORIZATION_FIELDS}
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


class FailureBundlePublicationError(RuntimeError):
    """A complete temporary bundle could not be atomically published."""

    def __init__(self, message: str, diagnostics: Mapping[str, object]) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


@dataclass(frozen=True)
class FailureEvidenceRequest:
    run_context: RunStaticContext
    year_context: YearContext
    period_input: BalancingInput
    stage: str
    error: Exception
    solver: Mapping[str, object]
    residuals: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.run_context, RunStaticContext):
            raise TypeError("run_context must be a RunStaticContext")
        if not isinstance(self.year_context, YearContext):
            raise TypeError("year_context must be a YearContext")
        if not isinstance(self.period_input, BalancingInput):
            raise TypeError("period_input must be a BalancingInput")
        if not isinstance(self.error, Exception):
            raise TypeError("error must be an Exception")
        if not isinstance(self.stage, str) or not self.stage.strip():
            raise ValueError("stage is required")
        if self.year_context.run_id != self.run_context.run_id:
            raise ValueError("Failure year context run does not match run context")
        if self.period_input.run_id != self.run_context.run_id:
            raise ValueError("Failure period input run does not match run context")
        if self.period_input.year != self.year_context.year:
            raise ValueError("Failure period input year does not match year context")
        if self.year_context.run_context_sha256 != canonical_context_sha256(
            self.run_context
        ):
            raise ValueError("Failure year context does not bind the run context")
        for name, value in self.residuals.items():
            if not isinstance(name, str) or not name:
                raise ValueError("Residual names must be non-empty strings")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"Residual {name} must be finite")


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    return repr(value)


def _encoded_json(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            _jsonable(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_synced(path: Path, payload: Mapping[str, object]) -> tuple[str, int]:
    encoded = _encoded_json(payload)
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_from_published(destination: Path) -> ArtifactReference:
    manifest_path = destination / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != FAILURE_BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported manifest schema")
        members = manifest.get("members")
        if not isinstance(members, Mapping) or set(members) != FAILURE_BUNDLE_MEMBERS:
            raise ValueError("failure bundle does not declare the mandatory members")
        entries = list(destination.iterdir())
        actual = {path.name for path in entries}
        if actual != FAILURE_BUNDLE_MEMBERS | {"manifest.json"}:
            raise ValueError("failure bundle file set does not match its manifest")
        if any(
            path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode)
            for path in entries
        ):
            raise ValueError("failure bundle entries must be ordinary files")
        for name, raw_member in members.items():
            if not isinstance(name, str) or Path(name).name != name:
                raise ValueError("failure bundle member path is invalid")
            if not isinstance(raw_member, Mapping):
                raise ValueError("failure bundle member record is invalid")
            member_path = destination / name
            if not member_path.is_file():
                raise ValueError(f"failure bundle member is missing: {name}")
            if _sha256_file(member_path) != raw_member.get("sha256"):
                raise ValueError(f"failure bundle member hash mismatch: {name}")
            if member_path.stat().st_size != raw_member.get("size_bytes"):
                raise ValueError(f"failure bundle member size mismatch: {name}")
        run_context = RunStaticContext.from_dict(json.loads(
            (destination / "run-context.json").read_text(encoding="utf-8")
        ))
        year_context = YearContext.from_dict(json.loads(
            (destination / "year-context.json").read_text(encoding="utf-8")
        ))
        period_input = BalancingInput.from_dict(json.loads(
            (destination / "period-input.json").read_text(encoding="utf-8")
        ))
        context_hashes = manifest["context_hashes"]
        if not isinstance(context_hashes, Mapping):
            raise ValueError("failure bundle context hashes are invalid")
        identities = (
            manifest["artifact_id"] == f"{run_context.run_id}:first-failure",
            manifest["run_id"] == run_context.run_id == year_context.run_id == period_input.run_id,
            manifest["year"] == year_context.year == period_input.year,
            manifest["period"] == period_input.period,
            manifest["period_id"] == period_input.period_id,
            manifest["trace_profile"] == run_context.trace_profile,
            manifest["fallback_used"] is False,
            context_hashes.get("run_context_sha256") == canonical_context_sha256(run_context),
            context_hashes.get("year_context_sha256") == canonical_context_sha256(year_context),
            manifest["period_input_sha256"] == contract_sha256(period_input),
        )
        if not all(identities):
            raise ValueError("failure bundle manifest identities do not match its members")
        solver_payload = json.loads((destination / "solver.json").read_text(encoding="utf-8"))
        if not isinstance(solver_payload, Mapping):
            raise ValueError("failure bundle solver evidence is not an object")
        if not isinstance(solver_payload.get("solver_contract"), Mapping) or not solver_payload["solver_contract"]:
            raise ValueError("failure bundle solver contract is missing")
        if not isinstance(solver_payload.get("solver_stack"), Mapping) or not solver_payload["solver_stack"]:
            raise ValueError("failure bundle solver identity is missing")
        if not isinstance(solver_payload.get("method"), str) or not solver_payload["method"]:
            raise ValueError("failure bundle solver settings are missing")
        if not isinstance(solver_payload.get("environment"), Mapping) or not solver_payload["environment"]:
            raise ValueError("failure bundle solver environment is missing")
        if not isinstance(solver_payload.get("diagnostics"), Mapping):
            raise ValueError("failure bundle solver diagnostics are invalid")
        solver_phases = solver_payload.get("completed_phases")
        if not isinstance(solver_phases, list) or not all(isinstance(item, Mapping) for item in solver_phases):
            raise ValueError("failure bundle completed solver phases are invalid")
        residuals_payload = json.loads((destination / "residuals.json").read_text(encoding="utf-8"))
        if not isinstance(residuals_payload, Mapping) or not all(
            isinstance(name, str)
            and bool(name)
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for name, value in residuals_payload.items()
        ):
            raise ValueError("failure bundle residual evidence is invalid")
        error_payload = json.loads((destination / "error.json").read_text(encoding="utf-8"))
        if not isinstance(error_payload, Mapping):
            raise ValueError("failure bundle error evidence is not an object")
        error_phases = error_payload.get("completed_phases")
        exception_identity = (
            error_payload.get("exception_module"), error_payload.get("exception_type"),
            error_payload.get("exception_qualname"),
        )
        if (
            error_payload.get("stage") != manifest["stage"]
            or not isinstance(error_payload.get("stage"), str)
            or error_payload.get("fallback_used") is not False
            or not all(isinstance(value, str) and bool(value) for value in exception_identity)
            or not isinstance(error_payload.get("exception_message"), str)
            or not isinstance(error_payload.get("diagnostics"), Mapping)
            or not isinstance(error_phases, list)
            or not all(isinstance(item, Mapping) for item in error_phases)
            or error_phases != solver_phases
        ):
            raise ValueError("failure bundle error identity does not match its manifest")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise FailureBundlePublicationError(
            "The canonical first-failure bundle is incomplete or invalid",
            {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "destination": str(destination),
            },
        ) from exc
    return ArtifactReference(
        artifact_id=str(manifest["artifact_id"]),
        kind="failure_evidence",
        uri=destination.as_posix(),
        media_type="application/vnd.value.failure-bundle+directory",
        checksum_sha256=_sha256_file(manifest_path),
        size_bytes=sum(path.stat().st_size for path in entries),
        extensions={
            "schema_version": FAILURE_BUNDLE_SCHEMA_VERSION,
            "fallback_used": False,
            "stage": manifest["stage"],
        },
    )


def write_first_failure_bundle(
    request: FailureEvidenceRequest,
    destination: Path,
) -> ArtifactReference:
    """Publish one complete bundle without overwriting the first failure."""

    if not isinstance(request, FailureEvidenceRequest):
        raise TypeError("request must be a FailureEvidenceRequest")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return _artifact_from_published(destination)

    diagnostics = dict(getattr(request.error, "diagnostics", {}) or {})
    completed_phases = request.solver.get(
        "completed_phases",
        diagnostics.get("completed_phase_optima", []),
    )
    members_payload = {
        "run-context.json": request.run_context.to_dict(),
        "year-context.json": request.year_context.to_dict(),
        "period-input.json": request.period_input.to_dict(),
        "solver.json": {
            **dict(request.solver),
            "completed_phases": completed_phases,
        },
        "residuals.json": {
            str(name): float(value) for name, value in sorted(request.residuals.items())
        },
        "error.json": {
            "stage": request.stage,
            "exception_module": type(request.error).__module__,
            "exception_type": type(request.error).__name__,
            "exception_qualname": type(request.error).__qualname__,
            "exception_message": str(request.error),
            "exception_args": [repr(value) for value in request.error.args],
            "diagnostics": diagnostics,
            "completed_phases": completed_phases,
            "fallback_used": False,
        },
    }
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    owns_destination = False
    try:
        members: dict[str, dict[str, object]] = {}
        for name, payload in members_payload.items():
            digest, size = _write_synced(temporary / name, payload)
            members[name] = {"sha256": digest, "size_bytes": size}
        manifest = {
            "schema_version": FAILURE_BUNDLE_SCHEMA_VERSION,
            "artifact_id": f"{request.run_context.run_id}:first-failure",
            "run_id": request.run_context.run_id,
            "year": request.year_context.year,
            "period": request.period_input.period,
            "period_id": request.period_input.period_id,
            "stage": request.stage,
            "trace_profile": request.run_context.trace_profile,
            "fallback_used": False,
            "context_hashes": {
                "run_context_sha256": canonical_context_sha256(request.run_context),
                "year_context_sha256": canonical_context_sha256(request.year_context),
            },
            "period_input_sha256": contract_sha256(request.period_input),
            "members": members,
        }
        _write_synced(temporary / "manifest.json", manifest)
        _artifact_from_published(temporary)
        try:
            os.rename(temporary, destination)
            owns_destination = True
        except OSError as exc:
            if destination.exists() and exc.errno in {
                None,
                errno.EEXIST,
                errno.ENOTEMPTY,
                errno.EACCES,
            }:
                shutil.rmtree(temporary, ignore_errors=True)
                return _artifact_from_published(destination)
            raise
        return _artifact_from_published(destination)
    except FailureBundlePublicationError:
        shutil.rmtree(temporary, ignore_errors=True)
        if owns_destination:
            shutil.rmtree(destination, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        if owns_destination:
            shutil.rmtree(destination, ignore_errors=True)
        raise FailureBundlePublicationError(
            "The first-failure bundle could not be atomically published",
            {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "destination": str(destination),
                "stage": request.stage,
                "original_exception_type": type(request.error).__name__,
                "original_exception_message": str(request.error),
            },
        ) from exc


_YEAR_TABLES = (
    *PERIOD_INDEXED_V8_TABLES,
    "reliability_event",
    "context_registry",
    "year_integrity",
)


def _validate_market_recovery_diagnostic(
    destination: Path,
    *,
    expected_manifest: Mapping[str, object],
) -> None:
    entries = {path.name: path for path in destination.iterdir()}
    expected_members = dict(expected_manifest["members"])
    if set(entries) != {*expected_members, "manifest.json"}:
        raise ValueError("Recovery diagnostic file set is not immutable")
    for path in entries.values():
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("Recovery diagnostic contains a non-regular member")
    manifest_path = entries["manifest.json"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != dict(expected_manifest):
        raise ValueError("Recovery diagnostic manifest identity mismatch")
    for name, expected in expected_members.items():
        path = entries[name]
        if (
            path.stat().st_size != int(expected["size_bytes"])
            or _sha256_file(path) != str(expected["sha256"])
        ):
            raise ValueError(f"Recovery diagnostic member identity mismatch: {name}")


def _market_recovery_member(path: Path) -> Mapping[str, object]:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"Recovery diagnostic source is not regular: {path.name}")
    return {"sha256": _sha256_file(path), "size_bytes": path.stat().st_size}


def _publish_market_recovery_diagnostic(
    snapshot: Path,
    *,
    live_database: Path,
    diagnostic_directory: Path,
    boundary: MarketLedgerBoundary,
) -> tuple[Path, str]:
    diagnostic_directory.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(
        prefix=".market-recovery-", dir=diagnostic_directory
    ))
    try:
        retained_snapshot = temporary / "market.sqlite"
        os.replace(snapshot, retained_snapshot)
        with retained_snapshot.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        digest = _sha256_file(retained_snapshot)
        members: dict[str, Mapping[str, object]] = {
            "market.sqlite": _market_recovery_member(retained_snapshot)
        }
        for suffix in ("-wal", "-shm"):
            live_sidecar = live_database.with_name(live_database.name + suffix)
            if live_sidecar.exists():
                retained_sidecar = temporary / ("market.sqlite" + suffix)
                if not stat.S_ISREG(live_sidecar.lstat().st_mode):
                    raise ValueError("Live market ledger sidecar is not regular")
                shutil.copyfile(live_sidecar, retained_sidecar)
                with retained_sidecar.open("r+b") as handle:
                    handle.flush()
                    os.fsync(handle.fileno())
                members[retained_sidecar.name] = _market_recovery_member(
                    retained_sidecar
                )
        manifest = {
            "schema_version": MARKET_RECOVERY_DIAGNOSTIC_SCHEMA_VERSION,
            "market_sqlite_sha256": digest,
            "market_sqlite_size_bytes": retained_snapshot.stat().st_size,
            "year": boundary.year,
            "last_committed_period": boundary.last_committed_period,
            "committed_prefix_sha256": boundary.committed_prefix_sha256,
            "selected_boundary": boundary.to_dict(),
            "members": members,
        }
        _write_synced(temporary / "manifest.json", manifest)
        destination = diagnostic_directory / digest
        if destination.exists():
            _validate_market_recovery_diagnostic(
                destination,
                expected_manifest=manifest,
            )
            shutil.rmtree(temporary)
            return destination / "market.sqlite", digest
        try:
            os.rename(temporary, destination)
        except OSError as exc:
            if destination.exists() and exc.errno in {
                None, errno.EEXIST, errno.ENOTEMPTY, errno.EACCES,
            }:
                shutil.rmtree(temporary, ignore_errors=True)
                _validate_market_recovery_diagnostic(
                    destination,
                    expected_manifest=manifest,
                )
                return destination / "market.sqlite", digest
            raise
        _validate_market_recovery_diagnostic(
            destination,
            expected_manifest=manifest,
        )
        _sync_directory_best_effort(diagnostic_directory)
        return destination / "market.sqlite", digest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise


def _delete_v8_market_table_tail(
    connection: sqlite3.Connection,
    table: str,
    boundary: MarketLedgerBoundary,
) -> int:
    before = connection.total_changes
    connection.execute(
        f"DELETE FROM {table} WHERE year=? AND period>?",
        (boundary.year, boundary.last_committed_period),
    )
    return connection.total_changes - before


def _delete_v8_market_tail(
    connection: sqlite3.Connection, boundary: MarketLedgerBoundary
) -> Mapping[str, int]:
    deleted: dict[str, int] = {}
    before = connection.total_changes
    connection.execute(
        "DELETE FROM clearing_outcomes WHERE input_sha256 IN "
        "(SELECT input_sha256 FROM clearing_inputs WHERE year=? AND period>?)",
        (boundary.year, boundary.last_committed_period),
    )
    deleted["clearing_outcomes"] = connection.total_changes - before
    for table in PERIOD_INDEXED_V8_TABLES:
        deleted[table] = _delete_v8_market_table_tail(
            connection, table, boundary
        )
    changed = connection.execute(
        "UPDATE year_integrity SET run_context_sha256=?, "
        "year_context_sha256=?, science_root=?, evidence_root=?, "
        "period_count=?, row_counts_json=?, trace_coverage_json=?, complete=0 "
        "WHERE year=?",
        (
            boundary.run_context_sha256,
            boundary.year_context_sha256,
            boundary.science_root,
            boundary.evidence_root,
            boundary.period_count,
            boundary.row_counts_json,
            boundary.trace_coverage_json,
            boundary.year,
        ),
    )
    if changed.rowcount != 1:
        raise InvariantError("Recovery could not rewrite year_integrity")
    orphaned = int(connection.execute(
        "SELECT COUNT(*) FROM clearing_outcomes AS o "
        "LEFT JOIN clearing_inputs AS i ON i.input_sha256=o.input_sha256 "
        "WHERE i.input_sha256 IS NULL"
    ).fetchone()[0])
    if orphaned:
        raise InvariantError("Recovery would leave orphaned clearing outcomes")
    return deleted


def _sqlite_live_identity(database: Path) -> Mapping[str, object]:
    identity: dict[str, object] = {}
    for suffix in ("", "-wal", "-shm"):
        path = database.with_name(database.name + suffix)
        if path.exists():
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError(f"Live market ledger member is not regular: {path.name}")
            identity[suffix] = {
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        else:
            identity[suffix] = None
    return identity


def _sync_directory_best_effort(directory: Path) -> None:
    """Sync a directory where Python exposes enforceable directory fsync."""

    if os.name == "nt":
        return
    descriptor = os.open(
        directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_owned_market_snapshot(database: Path, destination: Path) -> Path:
    before = _sqlite_live_identity(database)
    snapshot = destination / database.name
    for suffix in ("", "-wal", "-shm"):
        source = database.with_name(database.name + suffix)
        if source.exists():
            shutil.copyfile(source, destination / (database.name + suffix))
    if _sqlite_live_identity(database) != dict(before):
        raise InvariantError("Live market ledger changed while capturing snapshot")
    return snapshot


def _market_recovery_temp(database: Path, *, purpose: str) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{database.name}-{purpose}-recovery-",
        suffix=".tmp",
        dir=database.parent,
    )
    path = Path(name)
    try:
        os.close(descriptor)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return path


def recover_v8_market_prefix(
    database: Path,
    *,
    boundary: MarketLedgerBoundary,
    diagnostic_directory: Path,
    lease: MarketLedgerOwnershipLease,
) -> Mapping[str, object]:
    """Publish a verified prefix while holding the run's recovery ownership.

    The caller must prove its worker has exited by acquiring the recovery role
    in the same ownership domain that product writers are required to use.
    """

    if not isinstance(boundary, MarketLedgerBoundary):
        raise TypeError("boundary must be a MarketLedgerBoundary")
    database = Path(database).resolve()
    diagnostic_directory = Path(diagnostic_directory).resolve()
    if not isinstance(lease, MarketLedgerOwnershipLease):
        raise InvariantError(
            "A live recovery ownership lease for this market ledger is required"
        )
    lease.assert_recovery(database)
    working: Path | None = None
    diagnostic_snapshot: Path | None = None
    try:
        working = _market_recovery_temp(database, purpose="prefix")
        diagnostic_snapshot = _market_recovery_temp(
            database, purpose="diagnostic"
        )
        live_identity = _sqlite_live_identity(database)
        with tempfile.TemporaryDirectory(
            prefix="gridform-owned-sqlite-snapshot-"
        ) as snapshot_folder:
            snapshot = _copy_owned_market_snapshot(
                database, Path(snapshot_folder)
            )
            source = sqlite3.connect(snapshot)
            try:
                source.execute("PRAGMA query_only=ON")
                source.execute("BEGIN")
                verification = _verify_v8_market_prefix_connection(
                    source, boundary=boundary
                )
                live_period_count = int(source.execute(
                    "SELECT period_count FROM year_integrity WHERE year=?",
                    (boundary.year,),
                ).fetchone()[0])
                with closing(sqlite3.connect(working)) as recovered:
                    source.backup(recovered)
                with closing(sqlite3.connect(diagnostic_snapshot)) as retained:
                    source.backup(retained)
            finally:
                source.close()
        if _sqlite_live_identity(database) != dict(live_identity):
            raise InvariantError("Live market ledger changed while recovery held ownership")
        diagnostic, diagnostic_sha256 = _publish_market_recovery_diagnostic(
            diagnostic_snapshot,
            live_database=database,
            diagnostic_directory=diagnostic_directory,
            boundary=boundary,
        )
        diagnostic_snapshot = None

        recovered = sqlite3.connect(working)
        try:
            recovered.execute("BEGIN IMMEDIATE")
            deleted = dict(_delete_v8_market_tail(recovered, boundary))
            cleaned_verification = _verify_v8_market_prefix_connection(
                recovered, boundary=boundary, require_exact=True
            )
            recovered.commit()
            integrity = str(
                recovered.execute("PRAGMA integrity_check").fetchone()[0]
            )
            if integrity != "ok":
                raise InvariantError(
                    f"Recovered market ledger failed SQLite integrity: {integrity}"
                )
            journal_mode = str(
                recovered.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower()
            if journal_mode == "wal":
                checkpoint = recovered.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)"
                ).fetchone()
                if checkpoint is None or int(checkpoint[0]) != 0:
                    raise RuntimeError("Recovered market ledger WAL checkpoint failed")
                recovered.execute("PRAGMA journal_mode=DELETE")
        except Exception:
            recovered.rollback()
            raise
        finally:
            recovered.close()
        with working.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        cleaned_sha256 = _sha256_file(working)
        working.unlink()
        working = None

        lease.assert_recovery(database)
        if _sqlite_live_identity(database) != dict(live_identity):
            raise InvariantError("Live market ledger changed while recovery held ownership")
        live = sqlite3.connect(database)
        committed = False
        try:
            live.execute("PRAGMA synchronous=FULL")
            live.execute("BEGIN IMMEDIATE")
            live_deleted = dict(_delete_v8_market_tail(live, boundary))
            live_verification = _verify_v8_market_prefix_connection(
                live, boundary=boundary, require_exact=True
            )
            if live_deleted != deleted or dict(live_verification) != dict(
                cleaned_verification
            ):
                raise InvariantError(
                    "Live market ledger recovery diverged from verified working copy"
                )
            result = {
                "schema_version": "value.market-prefix-recovery/v1",
                "year": boundary.year,
                "committed_period": boundary.last_committed_period,
                "period_count": boundary.period_count,
                "deleted_periods": live_period_count - boundary.period_count,
                "deleted_rows": live_deleted,
                "diagnostic_database": diagnostic.as_posix(),
                "diagnostic_sha256": diagnostic_sha256,
                "cleaned_database_sha256": cleaned_sha256,
                "committed_prefix_sha256": boundary.committed_prefix_sha256,
                "verification": dict(verification),
                "cleaned_verification": dict(cleaned_verification),
                "publication": "sqlite_transaction",
            }
            lease.assert_recovery(database)
            live.commit()
            committed = True
            return result
        except Exception:
            if live.in_transaction:
                live.rollback()
            raise
        finally:
            try:
                live.close()
            except Exception:
                if not committed:
                    raise
    except Exception:
        if working is not None:
            try:
                working.unlink(missing_ok=True)
            except OSError:
                pass
        if diagnostic_snapshot is not None:
            try:
                diagnostic_snapshot.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def cleanup_incomplete_v8_year(
    database: Path,
    *,
    year: int,
    expected_committed_period: int,
    expected_run_context_sha256: str,
    expected_year_context_sha256: str,
) -> Mapping[str, object]:
    """Delete only one verified incomplete year in one immediate transaction."""

    database = Path(database)
    connection = sqlite3.connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        schema = connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        if schema is None or str(schema[0]) != "value.market-ledger/v8":
            raise ValueError("Annual recovery requires value.market-ledger/v8")
        row = connection.execute(
            "SELECT run_context_sha256, year_context_sha256, period_count, complete "
            "FROM year_integrity WHERE year=?",
            (year,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No incomplete market year exists for {year}")
        if str(row[0]) != expected_run_context_sha256:
            raise ValueError("Frozen RunContext SHA-256 does not match")
        if str(row[1]) != expected_year_context_sha256:
            raise ValueError("Frozen opening YearContext SHA-256 does not match")
        if int(row[3]) != 0:
            raise ValueError(f"Market year {year} is complete and cannot be cleaned")
        run_registry = connection.execute(
            "SELECT sha256 FROM context_registry "
            "WHERE context_scope='run' AND year=-1"
        ).fetchone()
        if run_registry is None or str(run_registry[0]) != expected_run_context_sha256:
            raise ValueError("Frozen RunContext registry does not match")
        period_rows = connection.execute(
            "SELECT period FROM period_integrity WHERE year=? ORDER BY period",
            (year,),
        ).fetchall()
        committed_periods = [int(item[0]) for item in period_rows]
        if (
            committed_periods != list(range(expected_committed_period + 1))
            or int(row[2]) != len(committed_periods)
        ):
            raise ValueError("Interrupted ledger does not match the committed-period authorization")
        registry = connection.execute(
            "SELECT sha256 FROM context_registry "
            "WHERE context_scope='year' AND year=?",
            (year,),
        ).fetchone()
        if registry is None or str(registry[0]) != expected_year_context_sha256:
            raise ValueError("Frozen opening YearContext registry does not match")
        tables = {
            str(item[0])
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "clearing_outcomes" in tables and "clearing_inputs" in tables:
            connection.execute(
                "DELETE FROM clearing_outcomes WHERE input_sha256 IN "
                "(SELECT input_sha256 FROM clearing_inputs WHERE year=?)",
                (year,),
            )
        for table in _YEAR_TABLES:
            if table in tables:
                connection.execute(f"DELETE FROM {table} WHERE year=?", (year,))
        connection.commit()
        return {
            "schema_version": "value.annual-recovery/v1",
            "year": year,
            "deleted_periods": int(row[2]),
            "committed_period": expected_committed_period,
            "run_context_sha256": expected_run_context_sha256,
            "year_context_sha256": expected_year_context_sha256,
            "resume_boundary": "prior_annual_checkpoint",
            "resume_mode": "recompute_full_incomplete_year",
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def recover_incomplete_v8_year(
    database: Path,
    *,
    year: int,
    expected_committed_period: int,
    expected_run_context_sha256: str,
    expected_year_context_sha256: str,
    diagnostic_directory: Path,
) -> Mapping[str, object]:
    """Atomically publish a cleaned copy and retain the interrupted ledger."""

    database = Path(database).resolve()
    diagnostic_directory = Path(diagnostic_directory).resolve()
    diagnostic_directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{database.name}-recovery-",
        suffix=".tmp",
        dir=database.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    snapshot_temp: Path | None = None
    try:
        with closing(sqlite3.connect(database)) as source:
            descriptor, snapshot_name = tempfile.mkstemp(
                prefix=f".incomplete-year-{year}-", suffix=".sqlite.tmp",
                dir=diagnostic_directory,
            )
            os.close(descriptor)
            snapshot_temp = Path(snapshot_name)
            snapshot_temp.unlink()
            with closing(sqlite3.connect(snapshot_temp)) as retained:
                source.backup(retained)
            retained_hash = _sha256_file(snapshot_temp)
            diagnostic = diagnostic_directory / f"incomplete-year-{year}-{retained_hash}.sqlite"
            if diagnostic.exists():
                if _sha256_file(diagnostic) != retained_hash:
                    raise ValueError("Existing interrupted-ledger snapshot hash mismatch")
                snapshot_temp.unlink()
            else:
                os.rename(snapshot_temp, diagnostic)
            with closing(sqlite3.connect(temporary)) as recovered:
                source.backup(recovered)
        cleanup = cleanup_incomplete_v8_year(
            temporary,
            year=year,
            expected_committed_period=expected_committed_period,
            expected_run_context_sha256=expected_run_context_sha256,
            expected_year_context_sha256=expected_year_context_sha256,
        )
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, database)
        for suffix in ("-wal", "-shm"):
            database.with_name(database.name + suffix).unlink(missing_ok=True)
        return {
            **dict(cleanup),
            "diagnostic_database": diagnostic.as_posix(),
            "diagnostic_sha256": retained_hash,
            "publication": "atomic_database_replace",
        }
    except Exception:
        temporary.unlink(missing_ok=True)
        if snapshot_temp is not None:
            snapshot_temp.unlink(missing_ok=True)
        raise
