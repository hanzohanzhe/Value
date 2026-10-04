"""Pinned scientific identity for the public VALUE CEM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


IDENTITY_PATH = Path(__file__).resolve().parent / "data" / "cem" / "cem_identity.json"


def load_cem_identity() -> dict[str, object]:
    payload = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "value.cem-model-identity/v1":
        raise ValueError("Unsupported VALUE CEM identity schema")
    if payload.get("numerical_reproduction_claim") is not False:
        raise ValueError("VALUE CEM identity must not silently claim retained numerical parity")
    return payload


def cem_identity_summary() -> Mapping[str, object]:
    payload = load_cem_identity()
    return {
        "schema_version": payload["schema_version"],
        "model_id": payload["model_id"],
        "version": payload["version"],
        "relationship_to_doctoral_reproduction": payload["relationship_to_doctoral_reproduction"],
        "numerical_reproduction_claim": payload["numerical_reproduction_claim"],
    }
