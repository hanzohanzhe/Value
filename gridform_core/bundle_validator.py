"""Validate a completed VALUE run bundle without rerunning the model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .provenance import PROVENANCE_SCHEMA, sha256_file
from .market_ledger import validate_market_ledger_file


def validate_run_bundle(bundle_root: Path) -> dict[str, object]:
    bundle_root = bundle_root.resolve()
    provenance_path = bundle_root / "provenance.json"
    errors: list[dict[str, str]] = []
    try:
        record = json.loads(provenance_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"valid": False, "errors": [{"code": "GF_BUNDLE_PROVENANCE_MISSING", "artifact_id": "provenance.json"}]}
    except json.JSONDecodeError:
        return {"valid": False, "errors": [{"code": "GF_BUNDLE_PROVENANCE_INVALID", "artifact_id": "provenance.json"}]}
    if record.get("schema_version") != PROVENANCE_SCHEMA:
        errors.append({"code": "GF_BUNDLE_SCHEMA_MISMATCH", "artifact_id": "provenance.json"})

    artifacts = {str(item["artifact_id"]): item for item in record.get("artifacts", [])}
    for artifact_id, expected in artifacts.items():
        path = (bundle_root / artifact_id).resolve()
        try:
            path.relative_to(bundle_root)
        except ValueError:
            errors.append({"code": "GF_BUNDLE_PATH_ESCAPE", "artifact_id": artifact_id})
            continue
        if not path.is_file():
            errors.append({"code": "GF_BUNDLE_ARTIFACT_MISSING", "artifact_id": artifact_id})
        elif sha256_file(path) != expected.get("sha256"):
            errors.append({"code": "GF_BUNDLE_HASH_MISMATCH", "artifact_id": artifact_id})

    referenced = [
        record.get("resolved_configuration", {}).get("artifact_id"),
        record.get("stage_events_artifact_id"),
        record.get("artifact_index_artifact_id"),
        (record.get("execution_source_identity") or {}).get("artifact_id"),
        *(
            module.get("manifest_artifact_id")
            for module in record.get("modules", {}).values()
        ),
    ]
    for artifact_id in filter(None, referenced):
        if artifact_id not in artifacts:
            errors.append({"code": "GF_BUNDLE_REFERENCE_UNINDEXED", "artifact_id": str(artifact_id)})

    required_suffixes = (
        "validation/scientific-validation.json",
        "planning/summary.json",
        "market/index.json",
        "performance.json",
        "artifact-index.json",
    )
    for suffix in required_suffixes:
        if not any(artifact_id.endswith(suffix) for artifact_id in artifacts):
            errors.append({"code": "GF_BUNDLE_REQUIRED_ARTIFACT_MISSING", "artifact_id": suffix})
    market_artifact_id = next(
        (artifact_id for artifact_id in artifacts if artifact_id.endswith("market/market.sqlite")),
        None,
    )
    if market_artifact_id:
        market_validation = validate_market_ledger_file(bundle_root / market_artifact_id)
        if not market_validation["valid"]:
            errors.append({
                "code": "GF_BUNDLE_MARKET_LEDGER_INVALID",
                "artifact_id": market_artifact_id,
            })
        elif market_validation.get("schema_version") == "value.market-ledger/v8":
            if not market_validation.get("science_root_by_year"):
                errors.append({
                    "code": "GF_BUNDLE_MARKET_SCIENCE_ROOT_MISSING",
                    "artifact_id": market_artifact_id,
                })
            if not market_validation.get("evidence_root_by_year"):
                errors.append({
                    "code": "GF_BUNDLE_MARKET_EVIDENCE_ROOT_MISSING",
                    "artifact_id": market_artifact_id,
                })
    # The source-bound resume contract was introduced without rewriting older,
    # immutable v2 bundles. Require its paired audit artifact only when the run
    # provenance declares the new execution identity capability.
    if record.get("execution_source_identity"):
        for suffix in ("execution-identity.json", "storage/cost-audit.json"):
            if not any(artifact_id.endswith(suffix) for artifact_id in artifacts):
                errors.append({"code": "GF_BUNDLE_REQUIRED_ARTIFACT_MISSING", "artifact_id": suffix})
    if (bundle_root / "preflight.json").is_file() and "preflight.json" not in artifacts:
        errors.append({"code": "GF_BUNDLE_REFERENCE_UNINDEXED", "artifact_id": "preflight.json"})
    checkpoint_ids = [artifact_id for artifact_id in artifacts if "/checkpoints-v2/state-" in f"/{artifact_id}"]
    if not checkpoint_ids:
        errors.append({"code": "GF_BUNDLE_REQUIRED_ARTIFACT_MISSING", "artifact_id": "checkpoints-v2/state-*.json"})

    chain = record.get("annual_state_chain") or []
    if not chain:
        errors.append({"code": "GF_BUNDLE_STATE_CHAIN_EMPTY", "artifact_id": "provenance.json"})
    else:
        if chain[0].get("input_state_sha256") != record.get("initial_state_sha256"):
            errors.append({"code": "GF_BUNDLE_INITIAL_STATE_MISMATCH", "artifact_id": "provenance.json"})
        for previous, current in zip(chain, chain[1:]):
            if previous.get("output_state_sha256") != current.get("input_state_sha256"):
                errors.append({"code": "GF_BUNDLE_STATE_CHAIN_BROKEN", "artifact_id": "provenance.json"})
            if previous.get("output_year") != current.get("input_year"):
                errors.append({"code": "GF_BUNDLE_STATE_YEAR_BROKEN", "artifact_id": "provenance.json"})

    events_id = record.get("stage_events_artifact_id")
    events_path = bundle_root / str(events_id) if events_id else None
    if events_path and events_path.is_file():
        try:
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except json.JSONDecodeError:
            errors.append({"code": "GF_BUNDLE_EVENTS_INVALID", "artifact_id": str(events_id)})
            events = []
        transitions = {int(item["year"]): item for item in events if item.get("stage") == "state_transition.apply"}
        advances = {int(item["year"]): item for item in events if item.get("stage") == "planning.advance_year"}
        for state in chain:
            year = int(state["year"])
            transition = transitions.get(year)
            advance = advances.get(year)
            if not transition or not advance:
                errors.append({"code": "GF_BUNDLE_STAGE_EVENT_MISSING", "artifact_id": str(events_id)})
                continue
            if advance.get("input_state_sha256") != state.get("input_state_sha256"):
                errors.append({"code": "GF_BUNDLE_ADVANCE_INPUT_MISMATCH", "artifact_id": str(events_id)})
            output_hash = transition.get("output_state_sha256") or transition.get("output_sha256")
            if output_hash != state.get("output_state_sha256"):
                errors.append({"code": "GF_BUNDLE_TRANSITION_OUTPUT_MISMATCH", "artifact_id": str(events_id)})

    return {
        "schema_version": "value.bundle-validation/v1",
        "valid": not errors,
        "run_id": record.get("identity", {}).get("run_id"),
        "artifacts_checked": len(artifacts),
        "state_transitions_checked": len(chain),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a VALUE run bundle")
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    report = validate_run_bundle(args.bundle)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
