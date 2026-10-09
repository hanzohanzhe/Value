"""Model wind/solar capacity factors next to DUKES load factors (decisions A9, A13; disclosure only).

The corrected profile's wind CF stays above the DESNZ DUKES load factors
after the literature losses; the author decided (A9) to keep it, without any
statistical calibration, and to disclose the comparison with its reasons in
the results and the methodology.  This module serves that disclosure:

* ``data/weather/value_uk_vre_cf_disclosure_v1.json`` holds the DUKES 2026
  table 6.3 load factors (read from the DESNZ xlsx in F1), the stated reasons,
  and the model's pre-curtailment CF of each known weather object for each
  dispatch weather method (``scripts/vre_cf_disclosure.py`` computes and
  checks these rows from the packs);
* ``run_disclosure`` picks the row of a Run from the sha256 of its frozen
  weather and fleet bindings and the weather method its recorded methodology
  implies (``site_weather.method_for_correction_ids``).

Nothing here changes a model result.  A Run on weather that is not in the
table gets ``status: not_tabulated`` and the DUKES column only.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "value.vre-cf-disclosure/v1"
TABLE_PATH = Path(__file__).resolve().parent / "data" / "weather" / "value_uk_vre_cf_disclosure_v1.json"
TECHNOLOGIES = ("onshore", "offshore", "solar")
ROLES = ("weather.solar", "weather.wind", "fleet.generators")


@lru_cache(maxsize=1)
def load_table() -> dict[str, Any]:
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    if table.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported VRE CF disclosure table")
    for technology in TECHNOLOGIES:
        row = table["dukes"]["technologies"][technology]
        years = {int(year): float(value) for year, value in row["by_year"].items()}
        for key, first in (("mean_2019_2024", 2019), ("mean_2020_2024", 2020)):
            values = [years[year] for year in range(first, 2025)]
            if abs(sum(values) / len(values) - float(row[key])) > 5e-5:
                raise ValueError(f"DUKES {technology} {key} is not the mean of its yearly values")
    for reference in table["model_reference"]:
        if set(reference["object_sha256"]) != set(ROLES):
            raise ValueError("A model reference row must name the weather and fleet sha256")
        for method_id, cf in reference["by_method"].items():
            if set(cf) != set(TECHNOLOGIES):
                raise ValueError(f"Model reference {reference['label']} / {method_id} lacks a technology")
    return table


def table_sha256() -> str:
    return hashlib.sha256(TABLE_PATH.read_bytes()).hexdigest()


def reference_for(object_sha256: Mapping[str, str]) -> Mapping[str, Any] | None:
    wanted = {role: str(object_sha256.get(role) or "").lower() for role in ROLES}
    for reference in load_table()["model_reference"]:
        if {role: str(value).lower() for role, value in reference["object_sha256"].items()} == wanted:
            return reference
    return None


def disclosure(object_sha256: Mapping[str, str] | None, weather_method_id: str | None) -> dict[str, Any]:
    """The disclosure block: model pre-curtailment CF (when tabulated), DUKES, ratios and reasons."""

    table = load_table()
    dukes = {technology: {key: row[key] for key in ("mean_2019_2024", "mean_2020_2024")}
             for technology, row in table["dukes"]["technologies"].items()}
    reference = reference_for(object_sha256 or {}) if object_sha256 else None
    model = None
    status, reason = "not_tabulated", None
    if not object_sha256:
        status, reason = "not_applicable", "the Run has no NetCDF site weather (dispatch uses declared CSV profiles)"
    elif reference is None:
        reason = "this weather/fleet is not in the disclosure table (scripts/vre_cf_disclosure.py --write)"
    elif weather_method_id not in reference["by_method"]:
        reason = f"weather method {weather_method_id!r} is not tabulated for this weather"
    else:
        status = "tabulated"
        model = dict(reference["by_method"][weather_method_id])
    comparison = None
    if model is not None:
        comparison = {technology: {
            "model_pre_curtailment_cf": model[technology],
            "dukes_load_factor_2020_2024": dukes[technology]["mean_2020_2024"],
            "dukes_load_factor_2019_2024": dukes[technology]["mean_2019_2024"],
            "ratio_to_dukes_2020_2024": round(model[technology] / dukes[technology]["mean_2020_2024"], 4),
        } for technology in TECHNOLOGIES}
    return {
        "schema_version": SCHEMA,
        "status": status,
        **({"reason": reason} if reason else {}),
        "disclosure_only": True,
        "decision_ids": list(table["decision_ids"]),
        "weather_method_id": weather_method_id,
        "reference_label": reference["label"] if reference is not None else None,
        "model_basis": table["model_basis"],
        "dukes_basis": table["dukes"]["basis"],
        "dukes_load_factor": dukes,
        "comparison": comparison,
        "reasons": [dict(item) for item in table["reasons"]],
        "table_sha256": table_sha256(),
    }


def _read(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def run_disclosure(run_root: Path, methodology: Mapping[str, Any] | None) -> dict[str, Any]:
    """Disclosure for a Run directory from its frozen pack manifest and recorded methodology."""

    from .site_weather import method_for_correction_ids

    manifest = _read(Path(run_root) / "input-snapshot" / "pack" / "manifest.json")
    bindings = dict(manifest.get("bindings") or {})
    netcdf = all(str(dict(bindings.get(role) or {}).get("uri", "")).lower().endswith(".nc")
                 for role in ("weather.solar", "weather.wind"))
    object_sha256 = ({role: str(dict(bindings.get(role) or {}).get("sha256") or "") for role in ROLES}
                     if netcdf else None)
    recorded = dict(methodology or {})
    if recorded.get("status") not in (None, "recorded") or not recorded.get("profile_id"):
        result = disclosure(object_sha256, None)
        result.update(status="methodology_not_recorded", comparison=None,
                      reason="the Run recorded no methodology, so its dispatch weather method is unknown")
        return result
    method = method_for_correction_ids(recorded.get("applied_correction_ids") or ())
    return disclosure(object_sha256, method.method_id)
