"""Immutable experiment specifications and bounded uncertainty summaries.

This module deliberately contains no model-global RNG.  Every child receives a
seed derived from immutable experiment identity and must run with its own input
snapshot and output directory.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping, Sequence


ENSEMBLE_SCHEMA = "value.ensemble-specification/v1"
SUMMARY_SCHEMA = "value.ensemble-summary/v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def derive_child_seed(master_seed: int, ensemble_id: str, replication: int) -> int:
    """Derive a stable unsigned 64-bit seed without depending on Python hashing."""

    if replication < 0:
        raise ValueError("replication must be non-negative")
    digest = hashlib.sha256(
        f"force-child-seed/v1|{int(master_seed)}|{ensemble_id}|{replication}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


@dataclass(frozen=True)
class EnsembleSpecification:
    ensemble_id: str
    base_project_revision: str
    mode: str
    master_seed: int
    replications: int
    selected_outputs: tuple[str, ...]
    maximum_parallel_children: int = 1
    schema_version: str = ENSEMBLE_SCHEMA
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in {"expected_capacity", "seeded_stochastic"}:
            raise ValueError("Planning ensemble mode must be expected_capacity or seeded_stochastic")
        if self.replications < 1:
            raise ValueError("An ensemble requires at least one replication")
        if not 1 <= self.maximum_parallel_children <= min(self.replications, 16):
            raise ValueError("maximum_parallel_children must be within 1..min(replications, 16)")
        if self.mode == "expected_capacity" and self.replications != 1:
            raise ValueError("expected_capacity is a deterministic expectation, not repeated realised trials")

    @property
    def revision(self) -> str:
        return hashlib.sha256(_canonical(asdict(self))).hexdigest()

    def children(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "child_run_id": f"{self.ensemble_id}-r{index:05d}",
                "replication": index,
                "child_seed": derive_child_seed(self.master_seed, self.ensemble_id, index),
                "base_project_revision": self.base_project_revision,
                "ensemble_revision": self.revision,
            }
            for index in range(self.replications)
        )


def expected_capacity_summary(projects: Sequence[Mapping[str, object]]) -> dict[str, object]:
    declared_mw = sum(float(row.get("capacity_mw", 0.0) or 0.0) for row in projects)
    expected_mw = sum(
        float(row.get("capacity_mw", 0.0) or 0.0)
        * float(row.get("success_probability", 0.0) or 0.0)
        for row in projects
    )
    probability = (
        sum(float(row.get("success_probability", 0.0) or 0.0) for row in projects) / len(projects)
        if projects else None
    )
    return {
        "mode": "expected_capacity",
        "declared_capacity_mw": declared_mw,
        "probability_weighted_capacity_mw": expected_mw,
        "mean_declared_probability": probability,
        "realised_successful_projects": "not_applicable",
        "realised_failed_projects": "not_applicable",
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(item) for item in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def aggregate_children(
    spec: EnsembleSpecification,
    children: Sequence[Mapping[str, object]],
    *,
    metric_names: Sequence[str],
) -> dict[str, object]:
    """Aggregate only completed children; missing/failed children remain explicit."""

    by_id = {str(row.get("child_run_id")): row for row in children}
    expected_ids = [str(row["child_run_id"]) for row in spec.children()]
    completed = [by_id[item] for item in expected_ids if by_id.get(item, {}).get("status") == "completed"]
    failed = [item for item in expected_ids if by_id.get(item, {}).get("status") == "failed"]
    missing = [item for item in expected_ids if item not in by_id]
    interrupted = [item for item in expected_ids if by_id.get(item, {}).get("status") == "interrupted"]
    metrics: dict[str, object] = {}
    for name in metric_names:
        values = [float(row["metrics"][name]) for row in completed if name in row.get("metrics", {})]  # type: ignore[index]
        metrics[name] = {
            "sample_count": len(values),
            "mean": statistics.fmean(values) if values else None,
            "q05": _quantile(values, 0.05) if values else None,
            "q50": _quantile(values, 0.50) if values else None,
            "q95": _quantile(values, 0.95) if values else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "interval_interpretation": (
                "empirical_quantiles_not_probability_confidence_interval"
                if values else "not_evaluated"
            ),
        }
    return {
        "schema_version": SUMMARY_SCHEMA,
        "ensemble_id": spec.ensemble_id,
        "ensemble_revision": spec.revision,
        "aggregation_rule": "completed_children_only_with_all_exclusions_reported",
        "requested_children": spec.replications,
        "completed_children": len(completed),
        "failed_child_run_ids": failed,
        "interrupted_child_run_ids": interrupted,
        "missing_child_run_ids": missing,
        "scientific_status": "exploratory" if len(completed) < 30 and spec.mode == "seeded_stochastic" else "empirical_ensemble",
        "metrics": metrics,
    }


def write_ensemble_specification(path: Path, spec: EnsembleSpecification) -> Path:
    payload = asdict(spec) | {"revision": spec.revision, "children": list(spec.children())}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path
