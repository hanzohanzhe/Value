"""Reproducible, non-invasive performance analysis for completed VALUE runs.

The profiler reads existing evidence only.  It deliberately distinguishes an
inclusive legacy timing span (``investment.complete``) from additive stage
timings so that the PSM is never counted twice.
"""

from __future__ import annotations

import json
import platform
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from .recovery_capability import latest_safe_recovery_point, recovery_capability


SCHEMA_VERSION = "value.performance-profile/v1"


def _model_output(path: Path) -> tuple[Path, Path | None]:
    path = path.resolve()
    if (path / "performance.json").is_file():
        return path, path.parent if (path.parent / "status.json").is_file() else None
    if (path / "model-output" / "performance.json").is_file():
        return path / "model-output", path
    raise ValueError(f"No completed VALUE performance evidence found under {path}")


def _json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _files(root: Path) -> list[dict[str, object]]:
    rows = [
        {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size}
        for path in root.rglob("*")
        if path.is_file()
    ]
    return sorted(rows, key=lambda row: (-int(row["bytes"]), str(row["path"])))


def _market_rows(database: Path) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    total: dict[str, int] = {}
    annual: dict[str, dict[str, int]] = defaultdict(dict)
    if not database.is_file():
        return total, dict(annual)
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for table in ("period_summary", "orders", "storage_state"):
            if table not in tables:
                continue
            total[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for year, count in connection.execute(
                f"SELECT year, COUNT(*) FROM {table} GROUP BY year ORDER BY year"
            ):
                annual[str(int(year))][table] = int(count)
    finally:
        connection.close()
    return total, dict(sorted(annual.items()))


def _duration(status: Mapping[str, object]) -> float | None:
    try:
        started = datetime.fromisoformat(str(status["started_at"]))
        finished = datetime.fromisoformat(str(status.get("finished_at") or status["updated_at"]))
        return max(0.0, (finished - started).total_seconds())
    except (KeyError, TypeError, ValueError):
        return None


def _module_years(events: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    years: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "stage_seconds": {},
            "operating_assets_visible_to_investment": None,
            "planning_projects_at_year_open": None,
        }
    )
    for event in events:
        if "year" not in event:
            continue
        year = str(int(event["year"]))
        action = str(event.get("action") or "")
        if action == "pipeline.begin_year":
            years[year]["planning_projects_at_year_open"] = event.get("projects")
        if action == "investment.complete":
            years[year]["operating_assets_visible_to_investment"] = event.get("assets")
        if "duration_seconds" in event:
            stages = years[year]["stage_seconds"]
            assert isinstance(stages, dict)
            stages[action] = float(stages.get(action, 0.0)) + float(event["duration_seconds"])
    for row in years.values():
        stage = row["stage_seconds"]
        assert isinstance(stage, dict)
        if "investment.complete" in stage:
            row["investment_envelope_seconds"] = stage["investment.complete"]
            row["investment_timing_semantics"] = (
                "inclusive parent span: contains PSM and cap calls; never add to child stages"
            )
    return dict(sorted(years.items()))


def _contract_years(events: Iterable[Mapping[str, object]]) -> dict[str, dict[str, float]]:
    years: dict[str, dict[str, float]] = defaultdict(dict)
    for event in events:
        if "year" not in event:
            continue
        year = str(int(event["year"]))
        stage = str(event.get("stage") or "unknown")
        years[year][stage] = years[year].get(stage, 0.0) + float(event.get("duration_seconds") or 0.0)
    return dict(sorted(years.items()))


def _checkpoint_bytes(output: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for path in sorted((output / "checkpoints-v2").glob("state-*.json")):
        try:
            opening_year = int(path.stem.split("-")[-1])
        except ValueError:
            continue
        result[str(opening_year - 1)] = path.stat().st_size
    return result


def _causal_analysis(annual: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    psm = []
    assets = []
    projects = []
    for year, row in annual.items():
        stages = row.get("stage_seconds") or {}
        if isinstance(stages, Mapping) and "psm.complete" in stages:
            psm.append({"year": int(year), "seconds": float(stages["psm.complete"])})
        if row.get("operating_assets_visible_to_investment") is not None:
            assets.append(int(row["operating_assets_visible_to_investment"]))
        if row.get("planning_projects_at_year_open") is not None:
            projects.append(int(row["planning_projects_at_year_open"]))
    facts = []
    if psm:
        slowest = max(psm, key=lambda row: row["seconds"])
        fastest = min(psm, key=lambda row: row["seconds"])
        facts.append(
            f"Observed PSM time ranges from {fastest['seconds']:.3f}s ({fastest['year']}) "
            f"to {slowest['seconds']:.3f}s ({slowest['year']})."
        )
    if assets and len(set(assets)) == 1:
        facts.append(f"The exposed investment event reports {assets[0]} assets in every observed year.")
    if len(projects) > 1 and projects[-1] < projects[0]:
        facts.append(f"Visible planning projects fall from {projects[0]} to {projects[-1]}.")
    return {
        "classification": "UNKNOWN",
        "facts": facts,
        "reason": (
            "The available event contract does not expose the compatibility-kernel object counts, "
            "allocation profile or peak memory needed to distinguish repeated adapter work, Python "
            "object growth and PSM algorithmic complexity. Elapsed time alone is not causal evidence."
        ),
        "optimization_decision": "No scientific execution path was changed without an isolated measured hot path.",
    }


def build_performance_profile(run_path: Path) -> dict[str, object]:
    output, run_root = _model_output(run_path)
    performance = _json(output / "performance.json", {})
    if not isinstance(performance, Mapping):
        performance = {}
    status = _json(run_root / "status.json", {}) if run_root else {}
    if not isinstance(status, Mapping):
        status = {}
    process = _json(output / "process-metrics.json", {})
    if not isinstance(process, Mapping):
        process = {}
    module_events = _jsonl(output / "module-events.jsonl")
    contract_events = _jsonl(output / "orchestrator-events.jsonl")
    annual = _module_years(module_events)
    contract = _contract_years(contract_events)
    total_rows, annual_rows = _market_rows(output / "market" / "market.sqlite")
    checkpoints = _checkpoint_bytes(output)
    for year in sorted(set(annual) | set(contract) | set(annual_rows) | set(checkpoints)):
        row = annual.setdefault(year, {"stage_seconds": {}})
        row["public_contract_stage_seconds"] = contract.get(year, {})
        row["market_record_counts"] = annual_rows.get(year, {})
        row["annual_checkpoint_bytes"] = checkpoints.get(year, 0)
    files = _files(output)
    wall = process.get("wall_seconds") or _duration(status)
    phases = performance.get("phases_seconds") if isinstance(performance.get("phases_seconds"), Mapping) else {}
    if wall is None and isinstance(phases, Mapping):
        wall = sum(
            float(phases.get(key) or 0.0)
            for key in (
                "data_and_configuration_preparation",
                "copied_project_composed_kernel",
                "public_contract_materialisation",
                "result_serialization_and_validation",
            )
        )
    peak = process.get("peak_resident_memory_bytes")
    cpu = process.get("cpu_seconds")
    max_psm = max(
        (
            float(row.get("stage_seconds", {}).get("psm.complete", 0.0))
            for row in annual.values()
            if isinstance(row.get("stage_seconds"), Mapping)
        ),
        default=0.0,
    )
    total_bytes = sum(int(row["bytes"]) for row in files)
    selected_modules = []
    resolved = _json(output / "resolved-run.json", {})
    if isinstance(resolved, Mapping):
        modules = resolved.get("modules") or resolved.get("selected_modules") or {}
        if isinstance(modules, Mapping):
            selected_modules = [str(value) for value in modules.values()]
    return {
        "schema_version": SCHEMA_VERSION,
        "interpretation": "measured operational evidence; not a scientific result or universal hardware promise",
        "run": {
            "path": str(output),
            "run_id": status.get("id") or process.get("run_id"),
            "mode": status.get("mode") or process.get("mode"),
            "status": status.get("status") or ("completed" if performance else "unknown"),
        },
        "reference_machine": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "logical_processors": __import__("os").cpu_count(),
        },
        "measurements": {
            "wall_seconds": wall,
            "cpu_seconds": cpu if cpu is not None else None,
            "cpu_status": "measured" if cpu is not None else "UNKNOWN: historical run has no process counter artifact",
            "peak_resident_memory_bytes": peak if peak is not None else None,
            "peak_memory_status": "measured" if peak is not None else "UNKNOWN: historical run has no process counter artifact",
            "artifact_bytes": total_bytes,
            "artifact_file_count": len(files),
            "market_record_counts": total_rows,
            "phases_seconds": dict(phases) if isinstance(phases, Mapping) else {},
        },
        "annual": dict(sorted(annual.items())),
        "largest_artifacts": files[:20],
        "causal_analysis": _causal_analysis(annual),
        "local_warning_thresholds": {
            "annual_psm_seconds": max_psm * 1.25 if max_psm else None,
            "artifact_bytes": int(total_bytes * 1.25),
            "peak_resident_memory_bytes": int(float(peak) * 1.25) if peak is not None else None,
            "basis": "125% of this measured local baseline; warning threshold, not a support guarantee",
        },
        "recovery": {
            **recovery_capability(selected_modules),
            "latest_safe_point": latest_safe_recovery_point(output),
        },
        "change_impact": {
            "production_scientific_execution_changed": False,
            "optimizations_accepted": [],
            "required_test_level": "bounded 24-hour and 168-hour operational profiles; immutable annual/ten-year evidence reused",
        },
    }


def write_performance_profile(run_path: Path, report_path: Path) -> dict[str, object]:
    report = build_performance_profile(run_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
