"""Read-only original-source/weather comparison; never runs an annual model.

Writes only a new report file requested by --output. Original files, installed
data pack, checkpoints and previous run results are never modified.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gridform_core.canonical_psm_data import build_chronology
from gridform_core.data_method import run_policy
from gridform_core.v2.contracts import AssetStateV2, OperatingState


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite evidence: {args.output}")
    source = args.legacy_source / "simulation_model.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    names = {"IterLimit", "acm_energy", "acm_solar", "_wind_power_curve",
             "piecewise_limit", "piecewise_limit1", "piecewise_limit2",
             "piecewise_limit3", "piecewise_limit4", "piecewise_limit5"}
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    assert {n.name for n in nodes} == names
    original = {"np": np, "WIND_UNIT_MW": 20}
    # Execute only these explicitly enumerated pure definitions, not source
    # imports, config side effects, main(), or any checkpoint deserializer.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), original)
    config_tree = ast.parse((args.legacy_source / "config.py").read_text(encoding="utf-8-sig"))
    source_locations = next(ast.literal_eval(n.value) for n in config_tree.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "locations" for t in n.targets))
    manifest = json.loads((args.pack / "manifest.json").read_text(encoding="utf-8"))
    bindings = manifest["bindings"]
    fleet = json.loads((args.pack / bindings["fleet.generators"]["uri"]).read_text(encoding="utf-8"))
    assert source_locations == fleet["locations"], "Pack coordinates differ from original config"
    assets = []
    for name in fleet["generators"]:
        tech = next((t for t in ("solar", "onshore", "offshore") if name.startswith(t)), None)
        if tech:
            assets.append(AssetStateV2(name, tech, 1.0))
    chronology = build_chronology(args.pack, manifest, OperatingState(2025, assets, ()),
                                  periods=17520, period_hours=0.5, data_policy=run_policy(manifest))
    rows = {r.asset_id: r for r in chronology.resources}
    results = []
    with Dataset(str(args.pack / bindings["weather.wind"]["uri"])) as wind, \
         Dataset(str(args.pack / bindings["weather.solar"]["uri"])) as solar:
        for asset in assets:
            key = asset.asset_id if asset.technology == "offshore" else asset.asset_id.split("_", 1)[1]
            point = source_locations[key]
            if asset.technology == "solar":
                raw = original["acm_solar"](solar, point["lat"], point["lon"])
                iterator = original["IterLimit"](raw)
                expected = np.asarray([original["piecewise_limit"](next(iterator)) / 3600000 for _ in range(17520)])
            else:
                raw = original["acm_energy"](wind, point["lat"], point["lon"])
                iterator = original["IterLimit"](raw)
                curve = original["piecewise_limit5" if asset.technology == "onshore" else "piecewise_limit1"]
                expected = np.asarray([curve(next(iterator) ** 0.5) / 20 for _ in range(17520)])
            actual = np.asarray(rows[asset.asset_id].availability)
            error = float(np.max(np.abs(expected - actual)))
            old_csv_key = "profiles.vre_" + asset.technology
            # Fixed 1 MW availability comparison, not a rerun of system excess.
            import pandas as pd
            csv = pd.read_csv(args.pack / bindings[old_csv_key]["uri"], header=None).iloc[:, 0].to_numpy(dtype=float)
            old_csv = np.repeat(csv, 2)[:17520]
            results.append({"asset_id": asset.asset_id, "technology": asset.technology,
                "compared_half_hours": len(actual), "source_hour_count": len(raw),
                "max_absolute_per_unit_error": error, "passed": bool(error <= 1e-12),
                "original_mean_availability": float(np.mean(expected)),
                "corrected_mean_availability": float(np.mean(actual)),
                "previous_common_csv_mean": float(np.mean(old_csv)),
                "weather_evidence": dict(rows[asset.asset_id].extensions["weather_profile"])})
    report = {"created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "all original representative-point availability curves, not model dispatch or annual investment parity",
        "original_source": str(source.resolve()),
        "original_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "original_functions": {n.name: {"start": n.lineno, "end": n.end_lineno} for n in nodes},
        "pack": str(args.pack.resolve()), "coordinates_equal_original_config": True,
        "dispatch_weather_method": chronology.extensions["dispatch_weather_method"],
        "compared_assets": len(results), "compared_values": sum(r["compared_half_hours"] for r in results),
        "passed": bool(results and all(r["passed"] for r in results)), "assets": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"assets", "original_functions"}}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
