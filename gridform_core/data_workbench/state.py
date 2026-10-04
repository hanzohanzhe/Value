"""Mutable Data Workbench paths derived from the application state root."""

from __future__ import annotations

from pathlib import Path

from gridform_core.runtime_paths import user_data_root


def resolve_data_workbench_root(application_state_root: Path | None = None) -> Path:
    root = (application_state_root or user_data_root()).expanduser().resolve()
    return root / "data-workbench"

