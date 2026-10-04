"""Atomic file replacement with unique temporary names (standard library only).

Every write goes to a fresh ``mkstemp`` file in the destination directory, is
flushed and fsync'd, and then moved over the destination with ``os.replace``.
Two concurrent writers therefore never share a temporary file (the
``status.json.tmp`` race of F5-03/P7-08).

The destination directory must already exist: these helpers never create it,
so a late write cannot recreate a run directory that has been moved to the
trash.  Callers that legitimately create new artifact folders create them
first.

On Windows ``os.replace`` fails while another process has the destination
open; terminal-state writes pass ``replace_retry_seconds`` (10 s) to retry.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


TERMINAL_REPLACE_RETRY_SECONDS = 10.0
_IS_WINDOWS = os.name == "nt"


def _fsync_directory(directory: Path) -> None:
    if _IS_WINDOWS:
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _replace(source: str, destination: Path, retry_seconds: float) -> None:
    deadline = time.monotonic() + max(0.0, retry_seconds)
    while True:
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if not _IS_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def atomic_write_bytes(
    path: os.PathLike[str] | str,
    data: bytes,
    *,
    replace_retry_seconds: float = 0.0,
    mode: int | None = None,
) -> Path:
    destination = Path(path)
    directory = destination.parent
    if not directory.is_dir():
        raise FileNotFoundError(f"Destination directory does not exist: {directory}")
    descriptor, temporary = tempfile.mkstemp(
        dir=directory, prefix=f".{destination.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        _replace(temporary, destination, replace_retry_seconds)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    _fsync_directory(directory)
    return destination


def atomic_write_text(
    path: os.PathLike[str] | str,
    text: str,
    *,
    encoding: str = "utf-8",
    replace_retry_seconds: float = 0.0,
) -> Path:
    return atomic_write_bytes(
        path, text.encode(encoding), replace_retry_seconds=replace_retry_seconds
    )


def atomic_write_json(
    path: os.PathLike[str] | str,
    payload: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    replace_retry_seconds: float = 0.0,
) -> Path:
    text = json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii, sort_keys=sort_keys)
    return atomic_write_text(path, text, replace_retry_seconds=replace_retry_seconds)


def write_new_json(path: os.PathLike[str] | str, payload: Any) -> Path:
    """Create ``path`` exclusively (``FileExistsError`` when it exists)."""

    destination = Path(path)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination
