"""Additive local-state migrations; immutable run directories are never rewritten."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .runtime_paths import APPLICATION_VERSION


STATE_SCHEMA = "value.local-state/v1"


def ensure_state_layout(root: Path) -> dict[str, object]:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in (
        "data-packs", "projects", "runs", "objects", "import-staging",
        "archives", "trash", "modules",
    ):
        (root / name).mkdir(exist_ok=True)
    path = root / "state-metadata.json"
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != STATE_SCHEMA:
            raise RuntimeError(
                "Unsupported VALUE local-state schema. Keep the directory unchanged "
                "and use the matching application version."
            )
        return payload
    payload = {
        "schema_version": STATE_SCHEMA,
        "created_by_version": APPLICATION_VERSION,
        "last_opened_by_version": APPLICATION_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "migration_policy": "additive_only_immutable_runs_not_rewritten",
        "migrations": ["0.5.0b1-create-explicit-state-layout"],
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)
    return payload
