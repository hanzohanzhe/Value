"""Declared deviations of the methodology profiles (P0-4 S7).

The catalogue ``data/methodology/declared_deviations.json`` lists, per
profile, the model behaviour a profile keeps on purpose together with a
falsifiable signature.  :func:`for_profile` returns the deviations a profile
declares; :func:`gate_policy` names how a run's validation gates are read:

* ``production`` - any failed gate check fails the run (scientific
  validation ``failed``, annual economics not eligible);
* ``declared_deviations`` - a frozen reproduction profile: a gate failure is
  ``reproduction_with_declared_deviations`` when every failing period or row
  carries a declared signature, ``failed`` otherwise; a passed gate is
  ``reproduction_conformant``.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

CATALOGUE_PATH = Path(__file__).resolve().parent / "data" / "methodology" / "declared_deviations.json"
SCHEMA_VERSION = "value.methodology-declared-deviations/v1"
GATE_EFFECTS = ("explains_gate_failure", "none")
MATCHERS = (
    "in_dispatch_double_count", "stage_power_reset",
    "forecast_above_supply_shortfall", "new_battery_each_year",
)
PRODUCTION = "production"
DECLARED_DEVIATIONS = "declared_deviations"


class DeclaredDeviationCatalogError(ValueError):
    pass


def load_from(path: Path) -> tuple[dict[str, Any], ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION:
        raise DeclaredDeviationCatalogError(f"declared_deviations.json: schema_version must be {SCHEMA_VERSION}")
    rows = payload.get("deviations")
    if not isinstance(rows, list):
        raise DeclaredDeviationCatalogError("declared_deviations.json: deviations must be a list")
    seen: set[str] = set()
    result = []
    for index, row in enumerate(rows):
        where = f"declared_deviations.json[{index}]"
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str) or not row["id"]:
            raise DeclaredDeviationCatalogError(f"{where}: id is required")
        if row["id"] in seen:
            raise DeclaredDeviationCatalogError(f"{where}: duplicate id {row['id']}")
        seen.add(row["id"])
        profiles = row.get("profiles")
        if not isinstance(profiles, list) or not profiles or not all(isinstance(item, str) and item for item in profiles):
            raise DeclaredDeviationCatalogError(f"{where}: profiles must be a non-empty list of profile ids")
        if row.get("gate_effect") not in GATE_EFFECTS:
            raise DeclaredDeviationCatalogError(f"{where}: gate_effect must be one of {GATE_EFFECTS}")
        signature = row.get("signature")
        if signature is not None:
            if not isinstance(signature, Mapping) or signature.get("matcher") not in MATCHERS:
                raise DeclaredDeviationCatalogError(f"{where}: signature.matcher must be one of {MATCHERS}")
            checks = signature.get("checks")
            if not isinstance(checks, list) or not all(isinstance(item, str) for item in checks):
                raise DeclaredDeviationCatalogError(f"{where}: signature.checks must be a list of check ids")
            if not isinstance(signature.get("relation"), str) or not signature["relation"]:
                raise DeclaredDeviationCatalogError(f"{where}: signature.relation is required")
        if row["gate_effect"] == "explains_gate_failure" and not (signature and signature.get("checks")):
            raise DeclaredDeviationCatalogError(f"{where}: a deviation that explains gate failures names its checks")
        if row["gate_effect"] == "none" and signature and signature.get("checks"):
            raise DeclaredDeviationCatalogError(f"{where}: a report-only deviation explains no gate check")
        result.append(copy.deepcopy(dict(row)))
    return tuple(result)


@lru_cache(maxsize=1)
def catalogue() -> tuple[dict[str, Any], ...]:
    return load_from(CATALOGUE_PATH)


def for_profile(profile_id: str | None) -> list[dict[str, Any]]:
    """The deviations a profile declares (every gate effect), catalogue order."""

    if not profile_id:
        return []
    return [copy.deepcopy(row) for row in catalogue() if profile_id in row["profiles"]]


def gating(declared: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The subset of ``declared`` whose signature may explain a gate failure."""

    return [dict(row) for row in declared if row.get("gate_effect") == "explains_gate_failure"]


def gate_policy(methodology: Mapping[str, Any] | None) -> str:
    """``declared_deviations`` for a frozen reproduction profile, else ``production``."""

    if isinstance(methodology, Mapping) and methodology.get("frozen") is True and methodology.get("profile_id"):
        return DECLARED_DEVIATIONS
    return PRODUCTION
