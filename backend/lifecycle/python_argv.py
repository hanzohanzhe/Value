"""Interpreter arguments that never read bytecode from the source/runtime tree.

``-B`` stops writing bytecode but CPython still *reads* matching ``.pyc``
files from ``__pycache__`` directories next to the sources, including the
standard library inside a bundled runtime.  An unverified ``.pyc`` there
would then execute instead of the verified source (R1-07).  Pointing
``pycache_prefix`` at a fresh empty directory makes the interpreter look for
bytecode only there, so every module is compiled from its source.

``-s`` drops the user site directory.  ``-I`` is not used: the linux-local
layout relies on ``PYTHONPATH`` (P0_CONVENTIONS section 8).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

WORKER_MODULE = "backend.worker_entry"
PYCACHE_PREFIX_PREFIX = "value-pycache-"


def new_pycache_prefix(parent: os.PathLike[str] | str | None = None) -> Path:
    """Create a fresh, empty, private directory for ``pycache_prefix``."""

    return Path(tempfile.mkdtemp(prefix=PYCACHE_PREFIX_PREFIX, dir=parent))


def isolated_python_argv(python: os.PathLike[str] | str, prefix: os.PathLike[str] | str) -> list[str]:
    return [os.fspath(python), "-B", "-s", "-X", f"pycache_prefix={os.fspath(prefix)}"]


def worker_python_argv(python: os.PathLike[str] | str, prefix: os.PathLike[str] | str) -> list[str]:
    return [*isolated_python_argv(python, prefix), "-m", WORKER_MODULE]


def isolated_environment(environment: dict[str, str], prefix: os.PathLike[str] | str) -> dict[str, str]:
    """Return a copy that also carries the prefix for grandchild interpreters."""

    updated = dict(environment)
    updated["PYTHONPYCACHEPREFIX"] = os.fspath(prefix)
    updated["PYTHONDONTWRITEBYTECODE"] = "1"
    return updated


def remove_empty_prefix(prefix: os.PathLike[str] | str) -> bool:
    """Remove a prefix directory that is still empty; never deletes content."""

    try:
        Path(prefix).rmdir()
    except OSError:
        return False
    return True
