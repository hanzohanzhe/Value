"""Audit the sign of a pack's interconnector flows against an annual reference (P0-5b S11).

``python -B scripts/audit_boundary_flow_sign.py --pack DIR --reference REF.json [--output EVIDENCE.json]``

The reference (``boundary_flow_reference_2022.json``) is supplied by the
author (plan 2.3: external reference statistics are not downloaded).  It
gives, per country, the annual NET IMPORT to GB in TWh (positive = import):

    {"schema_version": "value.boundary-flow-reference/v1", "year": 2022,
     "sign_convention": "positive = import to GB",
     "source": "...", "net_import_twh": {"france": -9.9, ...}}

For each country the pack's net flow (sum of flow_mw x period hours, read
with the pack's declared column) is compared with the reference: the signs
must agree and the magnitude must be within ``--relative-tolerance`` of the
reference (or ``--absolute-tolerance-twh``, whichever is larger).  The
evidence is ``verified`` only when every country with a reference agrees.
It binds the sha256 of the reference and of every audited flow file, so
the pack builder can only mark ``flow_sign`` verified for exactly these bytes.
Nothing is uploaded; the script only reads local files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

SCHEMA = "value.boundary-flow-sign-audit/v1"
REFERENCE_SCHEMA = "value.boundary-flow-reference/v1"
COUNTRIES = ("france", "belgium", "netherlands", "norway", "ireland")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_flow_mw(pack: Path, binding: Mapping[str, Any]) -> np.ndarray:
    """Declared column when the binding names one, else the single numeric column."""

    path = pack / str(binding["uri"])
    header = 0 if binding.get("csv_header", True) else None
    frame = pd.read_csv(path, header=header)
    column = binding.get("csv_column")
    if column is not None:
        series = frame[column]
    else:
        numeric = [name for name in frame.columns if pd.api.types.is_numeric_dtype(frame[name])]
        if len(numeric) != 1:
            raise ValueError(f"{path.name}: declare csv_column (numeric columns: {numeric})")
        series = frame[numeric[0]]
    return pd.to_numeric(series, errors="raise").to_numpy(dtype=float)


def audit(pack: Path, reference: Path, *, relative_tolerance: float = 0.25,
          absolute_tolerance_twh: float = 0.5) -> dict[str, Any]:
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    ref = json.loads(reference.read_text(encoding="utf-8"))
    if ref.get("schema_version") != REFERENCE_SCHEMA:
        raise ValueError(f"reference schema must be {REFERENCE_SCHEMA}")
    period_hours = float(manifest.get("period_hours") or 0.5)
    countries: dict[str, Any] = {}
    for country in COUNTRIES:
        binding = dict(manifest["bindings"].get(f"market.{country}.profile") or {})
        if not binding or country not in ref["net_import_twh"]:
            continue
        flow = read_flow_mw(pack, binding)
        model = float(flow.sum() * period_hours / 1e6)
        expected = float(ref["net_import_twh"][country])
        tolerance = max(relative_tolerance * abs(expected), absolute_tolerance_twh)
        same_sign = (model > 0) == (expected > 0) or abs(expected) <= absolute_tolerance_twh
        consistent = bool(same_sign and abs(model - expected) <= tolerance)
        countries[country] = {
            "flow_sha256": _sha256(pack / str(binding["uri"])), "csv_column": binding.get("csv_column"),
            "model_net_import_twh": round(model, 6), "reference_net_import_twh": expected,
            "tolerance_twh": tolerance, "same_sign": bool(same_sign), "consistent": consistent,
        }
    verified = bool(countries) and all(row["consistent"] for row in countries.values())
    return {
        "schema_version": SCHEMA, "pack_id": manifest.get("id"),
        "reference_sha256": _sha256(reference), "reference_source": ref.get("source"),
        "reference_year": ref.get("year"), "sign_convention": "positive = import to GB",
        "relative_tolerance": relative_tolerance, "absolute_tolerance_twh": absolute_tolerance_twh,
        "countries": countries, "verified": verified,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--relative-tolerance", type=float, default=0.25)
    parser.add_argument("--absolute-tolerance-twh", type=float, default=0.5)
    arguments = parser.parse_args(argv)
    evidence = audit(arguments.pack, arguments.reference, relative_tolerance=arguments.relative_tolerance,
                     absolute_tolerance_twh=arguments.absolute_tolerance_twh)
    text = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if evidence["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
