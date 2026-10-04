"""Compact, non-invasive performance evidence for scientific runs."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Mapping


def _jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_performance_report(
    output_dir: Path,
    *,
    preparation_seconds: float,
    copied_kernel_seconds: float,
    contract_materialisation_seconds: float,
    serialization_and_validation_seconds: float,
) -> Path:
    module_events = _jsonl(output_dir / "module-events.jsonl")
    contract_events = _jsonl(output_dir / "orchestrator-events.jsonl")
    annual: dict[int, dict[str, float]] = defaultdict(dict)
    hot_paths: list[dict[str, object]] = []
    for row in module_events:
        if "duration_seconds" not in row:
            continue
        seconds = float(row["duration_seconds"])
        year, action = int(row["year"]), str(row["action"])
        annual[year][action] = annual[year].get(action, 0.0) + seconds
        hot_paths.append({"source": "copied_modular_kernel", "year": year, "stage": action, "duration_seconds": seconds})
    for row in contract_events:
        seconds = float(row.get("duration_seconds") or 0.0)
        hot_paths.append({"source": "public_contract_materialisation", "year": int(row["year"]), "stage": str(row["stage"]), "duration_seconds": seconds})
    market_path = output_dir / "market" / "metadata.json"
    market: Mapping[str, object] = {}
    if market_path.is_file():
        market = json.loads(market_path.read_text(encoding="utf-8"))
    report = {
        "schema_version": "value.performance/v1",
        "interpretation": "measurement_not_scientific_output",
        "phases_seconds": {
            "data_and_configuration_preparation": max(0.0, preparation_seconds),
            "copied_project_composed_kernel": max(0.0, copied_kernel_seconds),
            "public_contract_materialisation": max(0.0, contract_materialisation_seconds),
            "result_serialization_and_validation": max(0.0, serialization_and_validation_seconds),
            "market_ledger_writer": float(market.get("writer_seconds") or 0.0),
        },
        "annual_copied_kernel_stages_seconds": {
            str(year): dict(sorted(stages.items())) for year, stages in sorted(annual.items())
        },
        "observed_hot_paths": sorted(hot_paths, key=lambda row: float(row["duration_seconds"]), reverse=True)[:50],
        "market_ledger": {
            "rows": market.get("rows", 0),
            "bytes": market.get("bytes", 0),
            "trace_level": market.get("trace_level", "off"),
        },
        "note": "Hot paths are reported only; this release does not silently change model equations or numerical order.",
    }
    path = output_dir / "performance.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
