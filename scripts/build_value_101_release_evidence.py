"""Build Prompt 117 evidence from live Runs, APIs and independent audit inputs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.audit_value_101_release import (
    ROOT,
    _audit_retained_sources,
    _audit_source_control,
    _probe_api,
    _recompute_comparison,
    load_json,
)
from scripts.verify_value_101_network_exercise import verify_network_pair
from scripts.verify_value_101_reset_scope import verify_reset_scope


def _section(path: Path, key: str) -> dict[str, Any]:
    payload = load_json(path)
    value = payload.get(key, payload)
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} does not contain a {key} object")
    return dict(value)


def build_evidence(
    *,
    root: Path,
    baseline_run_root: Path,
    data_run_root: Path,
    storage_run_root: Path,
    network_copperplate_run_root: Path,
    network_constrained_run_root: Path,
    network_report: Path,
    journey_report: Path,
    reset_report: Path | None,
    test_report: Path,
    api_origin: str,
    api_state_root: Path | None = None,
) -> dict[str, Any]:
    run_roots = {
        "baseline": str(baseline_run_root.resolve()),
        "data": str(data_run_root.resolve()),
        "storage": str(storage_run_root.resolve()),
    }
    comparison_seed: dict[str, Any] = {"comparison_run_roots": run_roots}
    comparison = _recompute_comparison(comparison_seed)
    api = _probe_api(api_origin, api_state_root)
    network_verification = verify_network_pair(
        network_copperplate_run_root,
        network_constrained_run_root,
    )
    declared_network = load_json(network_report)
    if declared_network != network_verification:
        raise ValueError(
            "The network report does not match the two declared saved Run roots"
        )
    reset = verify_reset_scope()
    if reset_report is not None and _section(reset_report, "reset_scope") != reset:
        raise ValueError("The reset report does not match a fresh loopback API verification")
    return {
        "schema_version": "value.101-release-evidence/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_control": _audit_source_control(root.resolve()),
        "public_module_ids": list(api.get("public_module_ids") or []),
        "api_routes": dict(api.get("routes") or {}),
        "scientific_boundary": {
            "label": "Teaching diagnostic: not annual economics",
            "annual_economics_eligible": False,
            "periods_per_year": 48,
            "years": 2,
        },
        "comparison_run_roots": run_roots,
        "comparison": comparison,
        "network_accounting_source": str(network_report.resolve()),
        "network_run_roots": {
            "copperplate": str(network_copperplate_run_root.resolve()),
            "constrained": str(network_constrained_run_root.resolve()),
        },
        "network_verification": network_verification,
        "network_accounting": dict(network_verification["network_accounting"]),
        "reset_scope": reset,
        "scheme_c_hashes": _audit_retained_sources(root.resolve()),
        "test_evidence": _section(test_report, "test_evidence"),
        "clean_user_journey": _section(journey_report, "clean_user_journey"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline-run-root", type=Path, required=True)
    parser.add_argument("--data-run-root", type=Path, required=True)
    parser.add_argument("--storage-run-root", type=Path, required=True)
    parser.add_argument("--network-copperplate-run-root", type=Path, required=True)
    parser.add_argument("--network-constrained-run-root", type=Path, required=True)
    parser.add_argument("--network-report", type=Path, required=True)
    parser.add_argument("--journey-report", type=Path, required=True)
    parser.add_argument("--reset-report", type=Path)
    parser.add_argument("--test-report", type=Path, required=True)
    parser.add_argument("--api-origin", default="http://127.0.0.1:8766")
    parser.add_argument("--api-data-home", type=Path, default=None,
                        help="VALUE_DATA_HOME of the probed API (its session file); default: this process's")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "publication" / "prompt117-value-101-evidence.json",
    )
    args = parser.parse_args()
    evidence = build_evidence(
        root=args.root,
        baseline_run_root=args.baseline_run_root,
        data_run_root=args.data_run_root,
        storage_run_root=args.storage_run_root,
        network_copperplate_run_root=args.network_copperplate_run_root,
        network_constrained_run_root=args.network_constrained_run_root,
        network_report=args.network_report,
        journey_report=args.journey_report,
        reset_report=args.reset_report,
        test_report=args.test_report,
        api_origin=args.api_origin,
        api_state_root=args.api_data_home,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
