"""Locate the COIN-OR CBC executable used by the independent PuLP oracles.

Lookup order (first hit wins):

1. ``VALUE_CBC_PATH`` - an explicit executable path;
2. ``cbcbox.cbc_bin_path()`` - the CBC build shipped in the cbcbox wheel that
   is part of the locked VALUE environment;
3. ``cbc`` on ``PATH``.

The locator never writes to stdout/stderr.  :func:`cbc_identity` records the
variant and binary sha256 so oracle reports state which CBC produced them.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

import pulp

ENVIRONMENT_VARIABLE = "VALUE_CBC_PATH"


class CbcUnavailableError(RuntimeError):
    """No CBC executable was found."""


def _executable(path: str | os.PathLike[str] | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path)
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate.resolve()
    return None


def _cbcbox_path() -> Path | None:
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            import cbcbox  # type: ignore[import-not-found]

            return _executable(cbcbox.cbc_bin_path())
    except Exception:  # noqa: BLE001 - an unusable optional wheel means "not found"
        return None


def locate_cbc() -> tuple[str, Path] | None:
    """Return ``(variant, path)`` or ``None``; variant is env, cbcbox or path."""

    configured = os.environ.get(ENVIRONMENT_VARIABLE)
    if configured:
        found = _executable(configured)
        return ("env", found) if found else None
    found = _cbcbox_path()
    if found:
        return ("cbcbox", found)
    found = _executable(shutil.which("cbc"))
    if found:
        return ("path", found)
    return None


def cbc_path() -> str:
    """Executable path for ``pulp.COIN_CMD(path=...)``; raises when absent."""

    located = locate_cbc()
    if located is None:
        raise CbcUnavailableError(
            "Independent CBC executable is unavailable: set VALUE_CBC_PATH, install the locked "
            "cbcbox wheel, or put cbc on PATH"
        )
    return str(located[1])


def cbc_command(**options: Any) -> pulp.COIN_CMD:
    """A ``pulp.COIN_CMD`` bound to the located CBC executable."""

    return pulp.COIN_CMD(path=cbc_path(), **options)


@lru_cache(maxsize=8)
def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cbc_identity() -> dict[str, Any]:
    """Variant, path and binary hash of the CBC that oracles will use."""

    located = locate_cbc()
    if located is None:
        return {"available": False, "variant": None, "path": None, "binary_sha256": None}
    variant, path = located
    return {"available": True, "variant": variant, "path": str(path), "binary_sha256": _sha256(str(path))}
