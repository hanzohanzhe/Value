"""Offline weather-lineage audit against selected original source statements.

Does not run dispatch, investment decisions, a model process, or a monitor.
Only creates the explicitly requested new report; never modifies source inputs,
installed packs, previous results or real checkpoints.
"""
import argparse
import ast
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gridform_core.canonical_psm_data import native_initial_state, build_chronology
from gridform_core.data_method import run_policy
from gridform_core.doctoral_weather import weather_execution_identity
from gridform_core.doctoral_weather_mapping import source_weights
from gridform_core.parameters import resolve_scheme_c_parameters
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCPlanningPipelineDefinition
from gridform_core.v2.contracts import AssetStateV2, OperatingState, ResolvedRun, YearState


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OriginalImportAdapter(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        # These two helpers are explicitly injected below; never import the old
        # model entrypoint (its imports/config can have simulation side effects).
        return None if node.module == "run_investment_analysis" else node


def original_mapping(source, fleet):
    path = source / "map_projects_to_generators_by_location.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names = {"haversine_distance", "find_nearest_generator", "extract_location_from_repd",
             "load_repd_with_locations", "map_projects_to_generators"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == names
    investment_path = source / "run_investment_analysis.py"
    investment = ast.parse(investment_path.read_text(encoding="utf-8-sig"))
    region = next(n for n in investment.body if isinstance(n, ast.FunctionDef) and n.name == "region_to_generator_name")
    env = {"pd": pd, "config": SimpleNamespace(locations=fleet["locations"]),
           "get_asset_type": lambda name: next((t for t in ("solar", "onshore", "offshore") if name.startswith(t)), None),
           "print": lambda *a, **k: None,
           **{n: getattr(math, n) for n in ("radians", "cos", "sin", "asin", "sqrt")}}
    module = OriginalImportAdapter().visit(ast.Module(body=[region, *nodes], type_ignores=[]))
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), env)
    return env


def original_commissioning(source):
    path = source / "run_investment_analysis_case3_decarbonization_breakdown_cm.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    branches = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                and ast.unparse(n.test) == "asset_type in ['solar', 'onshore', 'offshore']"
                and any(isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "projects_with_assignment"
                        for t in s.targets) for s in n.body)]
    assert len(branches) == 1, "Original VRE commissioning branch changed or ambiguous"
    branch = branches[0]
    return compile(ast.Module(body=branch.body, type_ignores=[]), str(path), "exec"), {
        "path": str(path), "sha256": digest(path), "start": branch.lineno,
        "end": branch.body[-1].end_lineno}


class OriginalRepresentative:
    def __init__(self, capacity, unit):
        self.capacity_multiplier = capacity / unit
        self.capital_cost = 0.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite evidence: {args.output}")
    manifest = json.loads((args.pack / "manifest.json").read_text(encoding="utf-8"))
    paths = {role: args.pack / binding["uri"] for role, binding in manifest["bindings"].items()}
    fleet = json.loads(paths["fleet.generators"].read_text(encoding="utf-8"))
    parameters = resolve_scheme_c_parameters(args.pack).scientific.values
    state = native_initial_state(args.pack, 2025, scientific_parameters=parameters)
    sites = state.extensions["doctoral_weather_reference_sites"]
    old = original_mapping(args.legacy_source, fleet)
    old_code, commissioning_evidence = original_commissioning(args.legacy_source)
    try:
        raw = pd.read_csv(paths["source.repd_raw"], encoding="utf-8", dtype=str, low_memory=False)
    except UnicodeDecodeError:
        raw = pd.read_csv(paths["source.repd_raw"], encoding="latin1", dtype=str, low_memory=False)
    raw_ids = {str(row.get("Ref ID", "")).strip(): row for _, row in raw.iterrows()}
    original_projects = []
    initial = [p for p in state.planning_projects if p.technology in {"solar", "onshore", "offshore"}]
    for p in initial:
        lat, lon = p.latitude, p.longitude
        # Old load_external_projects sets these from the physical REPD row.
        if lat is None or lon is None:
            row = raw_ids.get(str(p.extensions.get("physical_project_id", p.project_id)))
            if row is not None:
                lat, lon = old["extract_location_from_repd"](row)
        original_projects.append({"id": p.project_id, "name": p.name,
            "technology_type": p.technology, "region": p.region,
            "latitude": lat, "longitude": lon, "capacity": p.capacity_mw})
    mapped, _ = old["map_projects_to_generators"](original_projects, dict.fromkeys(sites), str(paths["source.repd_raw"]))
    mapped = {p["id"]: p for p in mapped}
    mapping_checks = [{"project_id": p.project_id, "technology": p.technology,
        "expected_completion_year": p.expected_completion_year, "capacity_mw": p.capacity_mw,
        "source_assigned_generator": mapped[p.project_id].get("assigned_generator"),
        "native_weather_source": p.extensions.get("weather_source_asset_id"),
        "assignment_rule": p.extensions["weather_assignment_rule"],
        "passed": mapped[p.project_id].get("assigned_generator") == p.extensions.get("weather_source_asset_id")}
        for p in initial]
    unit = lambda n: 1. if sites[n]["technology"] == "solar" else 20.
    stock = dict.fromkeys(sites, 0.)
    for a in state.assets:
        if a.technology in {"solar", "onshore", "offshore"} and a.capacity_mw > 0:
            for n, w in source_weights(a, sites).items():
                stock[n] += a.capacity_mw * w
    original_generators = {n: OriginalRepresentative(cap, unit(n)) for n, cap in stock.items()}
    reference = build_chronology(args.pack, manifest, OperatingState(2025,
        tuple(AssetStateV2(n, s["technology"], 1.) for n, s in sites.items()), ()), periods=96, period_hours=.5, data_policy=run_policy(manifest))
    curves = {r.asset_id: np.asarray(r.availability) for r in reference.resources}
    run = ResolvedRun("offline-weather-audit", "audit", "audit", manifest["id"], 2025, 2034, parameters, {}, {})
    pipeline = SchemeCPlanningPipelineDefinition()
    years = []
    for year in range(2025, 2035):
        assert state.year == year
        due = [p for p in state.planning_projects if p.technology in {"solar", "onshore", "offshore"}
               and p.expected_completion_year <= year and p.outcome not in {"failed", "failed_planning"}]
        for tech in ("solar", "onshore", "offshore"):
            projects = [dict(mapped[p.project_id]) for p in due if p.technology == tech]
            env = {**old, "asset_type": tech, "projects": projects,
                "project_pipeline": list(projects), "generator_objects": original_generators,
                "battery_objects": {}, "current_year": year, "investment_summary": [],
                "ExpensiverenewableGenerator": OriginalRepresentative,
                "config": SimpleNamespace(capital_costs_per_mw={})}
            exec(old_code, env)
        result = pipeline.advance_year(run, state)
        operating = result.operating_state
        vre = tuple(a for a in operating.assets if a.technology in {"solar", "onshore", "offshore"} and a.capacity_mw > 0)
        actual_stock = dict.fromkeys(sites, 0.)
        for a in vre:
            for n, w in source_weights(a, sites).items():
                actual_stock[n] += a.capacity_mw * w
        old_stock = {n: a.capacity_multiplier * unit(n) for n, a in original_generators.items()}
        stock_error = max(abs(actual_stock[n] - old_stock[n]) for n in sites)
        chronology = build_chronology(args.pack, manifest, OperatingState(year, vre, (), extensions=operating.extensions),
                                     periods=96, period_hours=.5, data_policy=run_policy(manifest))
        sizes = {a.asset_id: a.capacity_mw for a in vre}
        # Native chronology also materializes pack interconnectors; this audit
        # concerns VRE potential only, not imported power or dispatch decisions.
        actual_power = sum(np.asarray(r.availability) * sizes[r.asset_id]
                           for r in chronology.resources if r.asset_id in sizes)
        expected_power = sum(curves[n] * old_stock[n] for n in sites)
        power_error = float(np.max(np.abs(actual_power - expected_power)))
        before = {p.project_id: p.capacity_mw for p in due}
        after = {p.project_id: p.capacity_mw for p in result.commissioned_projects if p.project_id in before}
        next_state = YearState(year + 1, operating.assets, operating.active_planning_projects, extensions=operating.extensions)
        restored = YearState.from_dict(json.loads(json.dumps(next_state.to_dict())))
        frozen = all(dict(a.extensions) == dict(b.extensions) for a, b in zip(next_state.assets, restored.assets))
        years.append({"year": year, "due_vre_projects": len(due), "active_vre_assets": len(vre),
            "new_vre_mw": sum(before.values()), "unchanged_project_capacity": before == after,
            "original_representative_capacity_max_error_mw": stock_error,
            "aggregate_availability_max_error_mw_96_periods": power_error,
            "json_roundtrip_retains_extensions": frozen,
            "passed": before == after and frozen and stock_error < 1e-7 and power_error < 1e-7})
        state = restored
    report = {"created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Current native initial REPD projects: source mapping and commissioning-only 2025-2034 replay, 96-period availability comparison each year. Not a dispatch/investment run or whole-model parity claim.",
        "pack": str(args.pack), "legacy_source": str(args.legacy_source),
        "native_parameters": dict(parameters), "weather_execution_identity": weather_execution_identity(),
        "commissioning_source": commissioning_evidence,
        "source_mapping_sha256": digest(args.legacy_source / "map_projects_to_generators_by_location.py"),
        "source_analysis_sha256": digest(args.legacy_source / "run_investment_analysis.py"),
        "audit_script_sha256": digest(Path(__file__)),
        "input_sha256": {r: digest(paths[r]) for r in ("source.repd_raw", "projects.repd", "fleet.generators", "weather.wind", "weather.solar")},
        "initial_vre_projects": len(initial),
        "mapping_rule_counts": dict(Counter(r["assignment_rule"] for r in mapping_checks)),
        "unmapped_or_different_from_source": sum(not r["passed"] for r in mapping_checks),
        "commissioned_vre_projects_2025_2034": sum(y["due_vre_projects"] for y in years),
        "passed": all(r["passed"] for r in mapping_checks) and all(y["passed"] for y in years),
        "years": years, "projects": mapping_checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("passed", "initial_vre_projects", "mapping_rule_counts",
                      "unmapped_or_different_from_source", "commissioned_vre_projects_2025_2034", "years")}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
