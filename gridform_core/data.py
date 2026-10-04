"""Load VALUE data-pack manifests with resolved, immutable bindings."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import DataPack, DatasetBinding
from .errors import DataError


def load_data_pack(pack_root: str | Path) -> DataPack:
    root = Path(pack_root).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    bindings = {}
    for role, raw in manifest.get("bindings", {}).items():
        uri = Path(raw["uri"])
        if not uri.is_absolute():
            uri = root / uri
        bindings[role] = DatasetBinding(
            role=role,
            uri=str(uri.resolve()),
            format=str(raw.get("format", uri.suffix.lstrip("."))),
            unit=raw.get("unit"),
            checksum=raw.get("sha256"),
            mapping=raw.get("mapping", {}),
        )
    return DataPack(
        id=manifest["id"],
        name=manifest["name"],
        country=manifest.get("country", ""),
        timezone=manifest.get("timezone", "UTC"),
        datasets=bindings,
    )


def required_uri(pack: DataPack, role: str) -> str:
    try:
        return pack.datasets[role].uri
    except KeyError as exc:
        raise DataError(f"Data pack {pack.id} does not bind required role {role}") from exc
