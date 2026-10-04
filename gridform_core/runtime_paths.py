"""Application/resource paths that do not depend on the current directory."""

from __future__ import annotations

import os
import json
import sys
from pathlib import Path


APPLICATION_VERSION = "0.6.0-alpha.2"
PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_ROOT.parent


def user_data_root() -> Path:
    """Return the explicit mutable state root.

    ``VALUE_DATA_HOME`` is the portable/managed-install contract. A clean
    Windows install defaults to LocalAppData; other systems use the customary
    per-user data directory. Launchers set the variable explicitly, including
    when preserving a pre-0.5 source checkout's existing ``.gridform`` state.
    """

    configured = os.environ.get("VALUE_DATA_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return (Path(local) / "VALUE").resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return (Path(xdg) / "value").expanduser().resolve()
    return (Path.home() / ".local" / "share" / "value").resolve()


def external_modules_root() -> Path:
    return user_data_root() / "modules"


def activate_external_module_sources(modules_root: Path | None = None) -> tuple[Path, ...]:
    """Add only enabled, installer-owned source roots to module resolution.

    External code is separated by module/version on disk, but it deliberately
    executes in the VALUE Python process.  Installation records are the sole
    authority; an arbitrary directory below the data root is never added.
    """

    root = (modules_root or external_modules_root()).resolve()
    active: list[Path] = []
    record_paths = sorted((root / "installed").glob("*/*/installation.json")) + sorted((root / "installed-extensions").glob("*/*/installation.json"))
    for record_path in record_paths:
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("source_root") != "src":
                continue
            expected = record_path.parent / "src"
            source = expected.resolve()
            if source != expected.absolute() or record_path.is_symlink() or record_path.parent.is_symlink():
                continue
            source.relative_to(root)
            text = str(source)
            if not record.get("enabled"):
                while text in sys.path:
                    sys.path.remove(text)
                continue
            if not source.is_dir():
                continue
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        active.append(source)
    # Match a clean activation's precedence regardless of prior conformance
    # imports, duplicates, or the server's installation history. Preserve every
    # other path so execution identity still detects unmanaged import roots.
    controlled = set(active)
    remaining = [raw for raw in sys.path
                 if Path(raw or os.getcwd()).resolve() not in controlled]
    sys.path[:] = [str(source) for source in reversed(active)] + remaining
    return tuple(active)
