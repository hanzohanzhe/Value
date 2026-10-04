"""Advisory inter-process file locks using only the standard library.

POSIX uses ``fcntl.flock`` on a dedicated lock file; Windows uses
``msvcrt.locking`` on its first byte.  Both are released by the operating
system when the holder exits for any reason (including SIGKILL), so a lock
file left on disk never blocks anyone: lock files are created once and never
unlinked (unlinking would let two holders lock different inodes).

``flock`` excludes every other open file description, including another
``open()`` of the same path in the same process, so these locks also serialise
threads.  A thread that asks for a lock it already holds would deadlock on
itself; that is detected per thread and raised immediately as
:class:`LockReentryError`.

Descriptors are opened non-inheritable (PEP 446) and ``subprocess`` closes
other descriptors by default, so a child process never inherits a lock.

:class:`LockTimeout` subclasses :class:`TimeoutError` and therefore
:class:`OSError`.  HTTP callers must map it to 503 *before* any generic
``except OSError`` clause.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import IO, Iterator
from contextlib import contextmanager

if os.name == "nt":  # pragma: no cover - exercised through a mocked msvcrt
    import msvcrt as _msvcrt
    _fcntl = None
else:
    import fcntl as _fcntl
    _msvcrt = None


DEFAULT_POLL_SECONDS = 0.01


class LockTimeout(TimeoutError):
    """The lock was not acquired before the deadline (HTTP 503)."""

    def __init__(self, path: os.PathLike[str] | str, timeout: float) -> None:
        self.path = str(path)
        self.timeout = float(timeout)
        super().__init__(f"Timed out after {timeout:g} s acquiring lock {Path(path).name}")


class LockReentryError(RuntimeError):
    """The calling thread already holds this lock (it would deadlock)."""


_THREAD_STATE = threading.local()


def _held_by_thread() -> set[str]:
    held = getattr(_THREAD_STATE, "held", None)
    if held is None:
        held = set()
        _THREAD_STATE.held = held
    return held


def lock_key(path: os.PathLike[str] | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def held_by_current_thread(path: os.PathLike[str] | str) -> bool:
    return lock_key(path) in _held_by_thread()


def _windows_prepare(stream: IO[bytes]) -> None:
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)


def _try_lock(stream: IO[bytes]) -> bool:
    """Try once, without blocking.  False only when another holder owns it."""

    if _msvcrt is not None:
        _windows_prepare(stream)
        try:
            _msvcrt.locking(stream.fileno(), _msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    assert _fcntl is not None
    try:
        _fcntl.flock(stream.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _lock_blocking(stream: IO[bytes], poll: float) -> None:
    if _msvcrt is not None:
        while not _try_lock(stream):
            time.sleep(poll)
        return
    assert _fcntl is not None
    _fcntl.flock(stream.fileno(), _fcntl.LOCK_EX)


def _unlock(stream: IO[bytes]) -> None:
    if _msvcrt is not None:
        stream.seek(0)
        _msvcrt.locking(stream.fileno(), _msvcrt.LK_UNLCK, 1)
        return
    assert _fcntl is not None
    _fcntl.flock(stream.fileno(), _fcntl.LOCK_UN)


class FileLock:
    """One exclusive lock on ``path``; usable as a context manager.

    The lock file's parent directory must already exist; it is never created
    here (a late writer must not resurrect a run directory that was moved).
    """

    def __init__(self, path: os.PathLike[str] | str) -> None:
        self.path = Path(path)
        self._key = lock_key(path)
        self._stream: IO[bytes] | None = None

    @property
    def held(self) -> bool:
        return self._stream is not None

    def acquire(self, timeout: float | None = None, *, poll: float = DEFAULT_POLL_SECONDS) -> "FileLock":
        held = _held_by_thread()
        if self._key in held:
            raise LockReentryError(f"This thread already holds lock {self.path.name}")
        stream = open(self.path, "a+b")  # noqa: SIM115 - kept open while held
        try:
            if timeout is None:
                _lock_blocking(stream, poll)
            else:
                deadline = time.monotonic() + max(0.0, float(timeout))
                while not _try_lock(stream):
                    if time.monotonic() >= deadline:
                        raise LockTimeout(self.path, float(timeout))
                    time.sleep(poll)
        except BaseException:
            stream.close()
            raise
        self._stream = stream
        held.add(self._key)
        return self

    def release(self) -> None:
        stream, self._stream = self._stream, None
        _held_by_thread().discard(self._key)
        if stream is None:
            return
        try:
            _unlock(stream)
        finally:
            stream.close()

    def __enter__(self) -> "FileLock":
        if self._stream is None:
            self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


@contextmanager
def hold_lock(
    path: os.PathLike[str] | str,
    *,
    timeout: float | None = None,
    poll: float = DEFAULT_POLL_SECONDS,
) -> Iterator[FileLock]:
    """Hold an exclusive lock for the ``with`` block (``timeout=None`` waits)."""

    lock = FileLock(path).acquire(timeout, poll=poll)
    try:
        yield lock
    finally:
        lock.release()


def try_acquire(path: os.PathLike[str] | str) -> FileLock | None:
    """Acquire without waiting; ``None`` when another holder owns the lock."""

    try:
        return FileLock(path).acquire(0.0)
    except LockTimeout:
        return None


LOCK_HELD = "held"
LOCK_FREE = "free"
LOCK_ABSENT = "absent"


def probe_lock(path: os.PathLike[str] | str) -> str:
    """Return ``held``, ``free`` or ``absent`` without creating the lock file.

    A lock this thread holds reports ``held``.  ``free`` means the lock could be
    taken at the moment of the probe (it is released again immediately).
    """

    location = Path(path)
    if held_by_current_thread(location):
        return LOCK_HELD
    if not location.is_file():
        return LOCK_ABSENT
    try:
        stream = open(location, "r+b")  # noqa: SIM115
    except FileNotFoundError:
        return LOCK_ABSENT
    try:
        if not _try_lock(stream):
            return LOCK_HELD
        _unlock(stream)
        return LOCK_FREE
    finally:
        stream.close()
