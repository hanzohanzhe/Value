"""Cross-process ownership for one product market ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import InvariantError


MARKET_LEDGER_OWNERSHIP_SCHEMA_VERSION = "value.market-ledger-ownership/v1"


class MarketLedgerOwnershipLease:
    """Exclusive writer/recovery lease for one resolved ledger path."""

    def __init__(self, database: Path, role: str, handle, identity: tuple[int, int]):
        self._database = database
        self._role = role
        self._handle = handle
        self._identity = identity
        self._live = True

    @classmethod
    def acquire(cls, database: Path, *, role: str) -> "MarketLedgerOwnershipLease":
        if role not in {"writer", "recovery"}:
            raise ValueError("market ledger ownership role must be writer or recovery")
        database = Path(database).resolve()
        lock_path = database.with_name(f".{database.name}.ownership.lock")
        handle = lock_path.open("a+b", buffering=0)
        try:
            _lock(handle)
        except OSError as exc:
            handle.close()
            raise InvariantError(
                f"Market ledger ownership is already held for {database}"
            ) from exc
        try:
            identity = _file_identity(handle)
            handle.seek(0)
            handle.truncate()
            handle.write(_marker(database))
            handle.flush()
            os.fsync(handle.fileno())
            return cls(database, role, handle, identity)
        except Exception:
            _unlock(handle)
            handle.close()
            raise

    @property
    def is_live(self) -> bool:
        return self._live and not self._handle.closed

    def assert_recovery(self, database: Path) -> None:
        database = Path(database).resolve()
        if not self.is_live or self._role != "recovery" or self._database != database:
            raise InvariantError(
                "A live recovery ownership lease for this market ledger is required"
            )
        lock_path = database.with_name(f".{database.name}.ownership.lock")
        try:
            path_identity = _path_identity(lock_path)
        except OSError as exc:
            raise InvariantError("Market ledger ownership domain changed") from exc
        self._handle.seek(0)
        if (
            path_identity != self._identity
            or _file_identity(self._handle) != self._identity
            or self._handle.read() != _marker(database)
        ):
            raise InvariantError("Market ledger ownership domain changed")

    def close(self) -> None:
        if not self.is_live:
            return
        try:
            _unlock(self._handle)
        finally:
            self._live = False
            self._handle.close()

    def __enter__(self) -> "MarketLedgerOwnershipLease":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def _marker(database: Path) -> bytes:
    return json.dumps(
        {
            "schema_version": MARKET_LEDGER_OWNERSHIP_SCHEMA_VERSION,
            "database": str(database),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _file_identity(handle) -> tuple[int, int]:
    value = os.fstat(handle.fileno())
    return int(value.st_dev), int(value.st_ino)


def _path_identity(path: Path) -> tuple[int, int]:
    value = path.stat()
    return int(value.st_dev), int(value.st_ino)


def _lock(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
