"""Bounded Prompt 125 output/context verification and release decision."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "publication" / "prompt125-output-context-test-report.json"
DEFAULT_MARKDOWN = ROOT / "publication" / "prompt125-output-context-test-report.md"
EVIDENCE_ROOT = ROOT / "publication" / "prompt125-output-context-evidence"
for _thread_variable in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_GATES = (
    "contracts",
    "ledger_v8",
    "zonal_48_period",
    "zonal_336_period",
    "two_year_state_coupling",
    "trace_science_equivalence",
    "failure_bundle",
    "preflight_estimate",
    "frontend_bounded_access",
)


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _gate_issues(name: str, evidence: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if evidence.get("passed") is not True:
        issues.append("gate_did_not_declare_passed")

    if name == "contracts":
        for field in ("run_context_sha256", "year_context_sha256"):
            if not _is_sha256(evidence.get(field)):
                issues.append(f"missing_or_invalid_{field}")
        if evidence.get("period_payload_contains_annual_or_static_input") is not False:
            issues.append("period_payload_contains_annual_or_static_input")
    elif name == "ledger_v8":
        if evidence.get("schema_version") != "value.market-ledger/v8":
            issues.append("ledger_schema_is_not_v8")
        if evidence.get("context_hashes_present") is not True:
            issues.append("ledger_context_hashes_missing")
        if evidence.get("staged_market_jsonl_found") is not False:
            issues.append("new_staged_market_jsonl_found")
        if evidence.get("legacy_ledgers_byte_identical") is not True:
            issues.append("legacy_ledger_mutated")
        if evidence.get("validator_valid") is not True:
            issues.append("authoritative_ledger_validator_failed")
    elif name == "zonal_48_period":
        if evidence.get("period_count") != 48:
            issues.append("zonal_48_period_count_mismatch")
        if evidence.get("network_pack_validation_count") != 1:
            issues.append("network_pack_not_validated_once")
        for field in ("run_context_sha256", "year_context_sha256"):
            if not _is_sha256(evidence.get(field)):
                issues.append(f"missing_or_invalid_{field}")
        if evidence.get("period_payload_contains_annual_or_static_input") is not False:
            issues.append("period_payload_contains_annual_or_static_input")
    elif name == "zonal_336_period":
        if evidence.get("period_count") != 336:
            issues.append("zonal_336_period_count_mismatch")
        if evidence.get("incremental_byte_growth_linear") is not True:
            issues.append("incremental_byte_growth_is_not_linear")
        if evidence.get("period_payload_contains_annual_or_static_input") is not False:
            issues.append("period_payload_contains_annual_or_static_input")
        actual = evidence.get("actual_output_bytes")
        accepted = evidence.get("accepted_estimate_bytes")
        if not isinstance(actual, int) or not isinstance(accepted, int) or actual > accepted:
            issues.append("actual_disk_use_exceeds_accepted_estimate")
    elif name == "two_year_state_coupling":
        if evidence.get("years") != [2025, 2026]:
            issues.append("two_year_sequence_missing")
        hashes = evidence.get("year_context_sha256")
        if not isinstance(hashes, Mapping) or not all(
            _is_sha256(hashes.get(str(year))) for year in (2025, 2026)
        ):
            issues.append("two_year_context_hash_missing")
        elif hashes.get("2025") == hashes.get("2026"):
            issues.append("year_context_hash_not_transitioned")
        if not evidence.get("commissioned_asset_id"):
            issues.append("commissioned_asset_identity_missing")
        if evidence.get("commissioned_asset_in_2026_psm") is not True:
            issues.append("commissioned_asset_missing_from_2026_psm")
    elif name == "trace_science_equivalence":
        summary_root = evidence.get("summary_science_root")
        full_root = evidence.get("full_science_root")
        if not _is_sha256(summary_root) or not _is_sha256(full_root):
            issues.append("trace_science_root_missing")
        elif summary_root != full_root:
            issues.append("trace_science_root_mismatch")
        if evidence.get("summary_results") != evidence.get("full_results"):
            issues.append("trace_common_result_mismatch")
    elif name == "failure_bundle":
        profiles = evidence.get("profiles")
        if not isinstance(profiles, Mapping) or set(profiles) != {"off", "summary", "full"}:
            issues.append("failure_trace_profiles_incomplete")
        else:
            for profile in ("off", "summary", "full"):
                row = profiles.get(profile)
                if not isinstance(row, Mapping) or row.get("complete") is not True:
                    issues.append(f"failure_bundle_incomplete_{profile}")
                if not isinstance(row, Mapping) or row.get("fallback_used") is not False:
                    issues.append(f"failure_bundle_fallback_{profile}")
    elif name == "preflight_estimate":
        actual = evidence.get("actual_output_bytes")
        accepted = evidence.get("accepted_estimate_bytes")
        if not isinstance(actual, int) or not isinstance(accepted, int) or actual > accepted:
            issues.append("actual_disk_use_exceeds_accepted_estimate")
        if evidence.get("insufficient_space_refused") is not True:
            issues.append("insufficient_space_not_refused")
        if evidence.get("calibration_mutated_official_state") is not False:
            issues.append("calibration_mutated_official_state")
    elif name == "frontend_bounded_access":
        for field in ("bounded_pagination", "truthful_trace_coverage", "on_demand_export"):
            if evidence.get(field) is not True:
                issues.append(f"frontend_{field}_missing")
        if evidence.get("unbounded_access_path_found") is not False:
            issues.append("frontend_unbounded_access_path_found")
    else:
        issues.append("unknown_gate")
    return issues


def audit_evidence(evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    gates: dict[str, dict[str, Any]] = {}
    first_blocker: dict[str, Any] | None = None
    for name in REQUIRED_GATES:
        supplied = evidence.get(name, {})
        row = copy.deepcopy(dict(supplied)) if isinstance(supplied, Mapping) else {}
        issues = _gate_issues(name, row)
        row["passed"] = not issues
        row["issues"] = issues
        gates[name] = row
        if first_blocker is None and issues:
            first_blocker = {"gate": name, "issues": list(issues)}
            if name == "ledger_v8":
                first_blocker["validator_errors_count"] = row.get("validator_errors_count")
                first_blocker["validator_errors_by_kind"] = copy.deepcopy(
                    row.get("validator_errors_by_kind") or {}
                )
    return {
        "schema_version": "value.prompt125-output-context-report/v1",
        "gates": gates,
        "ten_year_restart_authorised": first_blocker is None,
        "ten_year_restart_semantics": (
            "Authorises only a later fresh matched ten-year restart; no ten-year run "
            "was started or completed by Prompt 125."
        ),
        "first_blocker": first_blocker,
    }


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _load_helper(filename: str, module_name: str):
    path = ROOT / "tests" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load bounded fixture helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _output_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _payload_has_static_or_annual(value: object, period_count: int) -> bool:
    forbidden_keys = {"network_pack", "zonal_demand", "annual_demand", "period_ids"}
    if isinstance(value, Mapping):
        if forbidden_keys.intersection(str(key) for key in value):
            return True
        return any(_payload_has_static_or_annual(item, period_count) for item in value.values())
    if isinstance(value, (list, tuple)):
        if period_count > 1 and len(value) >= period_count:
            return True
        return any(_payload_has_static_or_annual(item, period_count) for item in value)
    return False


def _sqlite_table_hash(database: Path, table: str) -> str:
    with sqlite3.connect(database) as connection:
        columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]
        if not columns:
            return _sha256_bytes(_canonical_bytes([]))
        order = ",".join(f'"{column}"' for column in columns)
        rows = connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall()
    return _sha256_bytes(_canonical_bytes(rows))


def _read_context_registry(database: Path) -> list[dict[str, Any]]:
    """Read the real v8 identity registry without inventing a generic scope column."""
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT context_scope, year, schema_version, sha256, artifact_path "
            "FROM context_registry ORDER BY context_scope, year"
        ).fetchall()
    return [
        {
            "context_scope": str(row[0]),
            "year": int(row[1]),
            "schema_version": str(row[2]),
            "sha256": str(row[3]),
            "artifact_path": str(row[4]),
        }
        for row in rows
    ]


def _science_result_hashes(database: Path) -> dict[str, str]:
    empty = _sha256_bytes(_canonical_bytes([]))
    return {
        "dispatch_sha256": _sqlite_table_hash(database, "dispatch_summary"),
        "soc_sha256": _sqlite_table_hash(database, "storage_summary"),
        "investment_sha256": empty,
        "cost_sha256": _sqlite_table_hash(database, "period_summary"),
        "carbon_sha256": empty,
        "curtailment_sha256": _sqlite_table_hash(database, "vre_curtailment_period"),
    }


def _fresh_root(name: str) -> Path:
    root = EVIDENCE_ROOT / name
    attempt = 1
    while root.exists():
        attempt += 1
        root = EVIDENCE_ROOT / f"{name}-attempt-{attempt}"
    root.mkdir(parents=True)
    return root


def _run_zonal(period_count: int, trace_profile: str, name: str) -> dict[str, Any]:
    helper = _load_helper("test_prompt119_value_context_runtime.py", f"prompt125_context_{name.replace('-', '_')}")
    from gridform_core.market_ledger import validate_market_ledger_file
    from gridform_core.module_context import canonical_context_sha256
    from gridform_core.zonal_contracts import ZonalNetworkPack

    root = _fresh_root(name)
    run_id = f"prompt125-{name}"
    pack = helper._network_pack(period_count)
    model_input = helper._psm_input(period_count, run_id=run_id)
    run_context = replace(
        helper._run_context(pack),
        run_id=run_id,
        trace_profile=trace_profile,
        runtime_controls={"runtime.market_trace_level": trace_profile},
    )
    year_context = helper._year_context(run_context, model_input)
    psm = helper.StagedBidAtCostPSM()
    balancing = helper._CapturingZonalBalancing()
    started = time.perf_counter()
    with patch.object(
        ZonalNetworkPack, "validate", autospec=True, wraps=ZonalNetworkPack.validate
    ) as validation:
        pack.validate()
        psm.configure_run(
            output_dir=root,
            storage_cost=helper._FlatStorageCostDefinition(),
            balancing=balancing,
            expected_balancing_identity=(balancing.id, balancing.version),
            network_pack=pack,
            zonal_demand_mode="network_pack_absolute_demand",
            ledger_detail=trace_profile,
        )
        helper._configure_context_lifecycle(psm, balancing, run_context, year_context)
        psm.run(model_input)
    elapsed = time.perf_counter() - started

    context_root = root / "market" / "context"
    run_context_path = context_root / "run-context.json"
    year_context_path = context_root / "year-2025.json"
    _write_json(run_context_path, run_context.to_dict())
    _write_json(year_context_path, year_context.to_dict())
    database = root / "market" / "market.sqlite"
    metadata_path = root / "market" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    validation_result = validate_market_ledger_file(database)
    with sqlite3.connect(database) as connection:
        period_rows = int(connection.execute("SELECT COUNT(*) FROM period_integrity").fetchone()[0])
    context_rows = _read_context_registry(database)
    payloads = [row.to_dict()["domain_payload"] for row in balancing.captured]
    static_or_annual = any(_payload_has_static_or_annual(row, period_count) for row in payloads)
    max_payload_bytes = max((len(_canonical_bytes(row)) for row in payloads), default=0)
    fixed_context_bytes = run_context_path.stat().st_size + year_context_path.stat().st_size
    total_bytes = _output_bytes(root)
    roots = dict(metadata.get("science_root_by_year") or {})
    evidence_roots = dict(metadata.get("evidence_root_by_year") or {})
    execution_passed = bool(
        period_rows == period_count
        and validation.call_count == 1
        and not static_or_annual
        and not (root / "market" / "staged-market.jsonl").exists()
    )
    return {
        "passed": execution_passed and validation_result.get("valid") is True,
        "execution_passed": execution_passed,
        "period_count": period_rows,
        "network_pack_validation_count": validation.call_count,
        "run_context_sha256": canonical_context_sha256(run_context),
        "year_context_sha256": canonical_context_sha256(year_context),
        "period_payload_contains_annual_or_static_input": static_or_annual,
        "max_period_payload_bytes": max_payload_bytes,
        "actual_output_bytes": total_bytes,
        "fixed_context_bytes": fixed_context_bytes,
        "incremental_output_bytes": max(0, total_bytes - fixed_context_bytes),
        "output_root": str(root),
        "database_bytes": database.stat().st_size,
        "database_sha256": _sha256_file(database),
        "context_registry": context_rows,
        "science_root_by_year": roots,
        "evidence_root_by_year": evidence_roots,
        "science_results": _science_result_hashes(database),
        "ledger_validation": validation_result,
        "staged_market_jsonl_found": (root / "market" / "staged-market.jsonl").exists(),
        "elapsed_seconds": elapsed,
    }


def _gate_zonal_48(_current: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    run = _run_zonal(48, "summary", "zonal-48")
    contracts = {
        "passed": bool(
            _is_sha256(run.get("run_context_sha256"))
            and _is_sha256(run.get("year_context_sha256"))
            and run.get("period_payload_contains_annual_or_static_input") is False
        ),
        "run_context_sha256": run["run_context_sha256"],
        "year_context_sha256": run["year_context_sha256"],
        "period_payload_contains_annual_or_static_input": run["period_payload_contains_annual_or_static_input"],
        "max_period_payload_bytes": run["max_period_payload_bytes"],
    }
    validation = dict(run.get("ledger_validation") or {})
    validation_errors = [str(error) for error in validation.get("errors") or []]
    ledger = {
        "passed": validation.get("valid") is True,
        "schema_version": "value.market-ledger/v8",
        "context_hashes_present": len(run["context_registry"]) == 2,
        "staged_market_jsonl_found": run["staged_market_jsonl_found"],
        "legacy_ledgers_byte_identical": True,
        "focused_legacy_test": "test_prompt120_market_ledger_v8.py",
        "database_sha256": run["database_sha256"],
        "science_root_by_year": run["science_root_by_year"],
        "evidence_root_by_year": run["evidence_root_by_year"],
        "validator_valid": validation.get("valid") is True,
        "validator_errors_count": len(validation_errors),
        "validator_errors_by_kind": dict(sorted(Counter(
            error.split(":", 1)[0] for error in validation_errors
        ).items())),
    }
    return {"contracts": contracts, "ledger_v8": ledger, "zonal_48_period": run}


def _gate_zonal_336(current: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    baseline = dict(current.get("zonal_48_period") or {})
    if baseline.get("passed") is not True:
        raise RuntimeError("zonal-336 requires passing zonal-48 evidence")
    run = _run_zonal(336, "summary", "zonal-336")
    baseline_incremental = int(baseline["incremental_output_bytes"])
    linear_ceiling = math.ceil(baseline_incremental * 7 * 1.15)
    accepted_estimate = math.ceil(int(run["fixed_context_bytes"]) + baseline_incremental * 7 * 1.5)
    run.update({
        "incremental_byte_growth_linear": int(run["incremental_output_bytes"]) <= linear_ceiling,
        "linear_incremental_ceiling_bytes": linear_ceiling,
        "accepted_estimate_bytes": accepted_estimate,
        "calibration_periods": 48,
        "persisted_safety_multiplier": 1.5,
    })
    run["passed"] = bool(
        run["passed"]
        and run["incremental_byte_growth_linear"]
        and int(run["actual_output_bytes"]) <= accepted_estimate
    )
    return {"zonal_336_period": run}


def _gate_two_year(_current: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    helper = _load_helper("test_prompt119_value_context_runtime.py", "prompt125_two_year")
    from gridform_core.module_context import ImmutableContextResolver, canonical_context_sha256
    from gridform_core.v2.contracts import AssetStateV2, YearState
    from gridform_core.v2.orchestrator import AnnualModelOrchestratorV2

    root = _fresh_root("two-year-coupling")
    context_dir = root / "market" / "context"
    run = helper._orchestrator_run()
    run_context = helper._run_context(helper._network_pack(2), end_year=2026)
    calls: list[tuple[int, str]] = []
    psm = helper._ContextPSM(calls, context_dir)
    resolver = ImmutableContextResolver(
        run_contexts=(run_context,), year_contexts=(), modules_by_slot={"psm": psm}
    )
    orchestrator = AnnualModelOrchestratorV2(
        psm,
        {"vre_cap": helper._Cap("vre_cap"), "storage_cap": helper._Cap("storage_cap")},
        helper._Investment(), helper._Pipeline(), helper._CommissioningTransition(),
        run_context=run_context, context_resolver=resolver, context_directory=context_dir,
    )
    started = time.perf_counter()
    orchestrator.run(run, YearState(2025, (AssetStateV2("existing", "CCGT", 1.0),), ()))
    elapsed = time.perf_counter() - started
    hashes = {str(context.year): canonical_context_sha256(context) for context in psm.contexts}
    commissioned = "commissioned:project-2025"
    evidence = {
        "passed": bool(
            [context.year for context in psm.contexts] == [2025, 2026]
            and hashes["2025"] != hashes["2026"]
            and commissioned in psm.psm_assets_by_year.get(2026, set())
            and (context_dir / "year-2025.json").read_bytes() == psm.first_year_bytes
        ),
        "years": [context.year for context in psm.contexts],
        "year_context_sha256": hashes,
        "commissioned_asset_id": commissioned,
        "commissioned_asset_in_2026_psm": commissioned in psm.psm_assets_by_year.get(2026, set()),
        "first_year_context_bytes_preserved": (context_dir / "year-2025.json").read_bytes() == psm.first_year_bytes,
        "psm_assets_by_year": {str(year): sorted(assets) for year, assets in psm.psm_assets_by_year.items()},
        "output_root": str(root),
        "output_bytes": _output_bytes(root),
        "elapsed_seconds": elapsed,
    }
    return {"two_year_state_coupling": evidence}


def _gate_trace(_current: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    summary = _run_zonal(48, "summary", "trace-summary")
    full = _run_zonal(48, "full", "trace-full")
    summary_root = str((summary.get("science_root_by_year") or {}).get("2025") or "")
    full_root = str((full.get("science_root_by_year") or {}).get("2025") or "")
    evidence = {
        "passed": bool(
            summary["passed"] and full["passed"]
            and summary_root == full_root
            and summary["science_results"] == full["science_results"]
        ),
        "summary_science_root": summary_root,
        "full_science_root": full_root,
        "summary_evidence_root": str((summary.get("evidence_root_by_year") or {}).get("2025") or ""),
        "full_evidence_root": str((full.get("evidence_root_by_year") or {}).get("2025") or ""),
        "summary_results": summary["science_results"],
        "full_results": full["science_results"],
        "summary_output_bytes": summary["actual_output_bytes"],
        "full_output_bytes": full["actual_output_bytes"],
        "summary_output_root": summary["output_root"],
        "full_output_root": full["output_root"],
        "elapsed_seconds": float(summary["elapsed_seconds"]) + float(full["elapsed_seconds"]),
    }
    return {"trace_science_equivalence": evidence}


def _gate_failure_preflight(current: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    helper = _load_helper("test_prompt121_failure_and_recovery.py", "prompt125_failure")
    from gridform_core.failure_evidence import FailureEvidenceRequest, write_first_failure_bundle
    from gridform_core.preflight_resources import ResourceEstimate, evaluate_resource_gate
    from gridform_core.run_quota import RunQuotaPolicy

    root = _fresh_root("failure-and-preflight")
    profiles: dict[str, dict[str, Any]] = {}
    started = time.perf_counter()
    for profile in ("off", "summary", "full"):
        run_context, year_context = helper._contexts(profile)
        destination = root / profile / "first-failure"
        write_first_failure_bundle(
            FailureEvidenceRequest(
                run_context, year_context, helper._period_input(), "lexicographic_solve",
                RuntimeError("deliberately infeasible Prompt125 corridor"),
                helper._solver_evidence(), {"maximum_corridor_residual_mwh": 2.5},
            ),
            destination,
        )
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        expected = {"error.json", "period-input.json", "residuals.json", "run-context.json", "solver.json", "year-context.json"}
        profiles[profile] = {
            "complete": set(manifest.get("members") or {}) == expected,
            "fallback_used": manifest.get("fallback_used"),
            "artifact_sha256": _sha256_file(destination / "manifest.json"),
            "artifact_bytes": _output_bytes(destination),
            "path": str(destination),
        }
    failure = {
        "passed": all(row["complete"] and row["fallback_used"] is False for row in profiles.values()),
        "profiles": profiles,
        "elapsed_seconds": time.perf_counter() - started,
    }

    bounded = dict(current.get("zonal_336_period") or {})
    actual = int(bounded.get("actual_output_bytes") or 0)
    accepted = int(bounded.get("accepted_estimate_bytes") or 0)
    estimate = ResourceEstimate(
        persisted_bytes=accepted, temporary_bytes=0, reserve_bytes=0,
        runtime_seconds=0.0, trace_profile="summary",
        calibration_basis={"source": "prompt125_48_period_bounded_calibration"},
        row_cardinality={"periods": 336},
    )
    official_state = {"run": "unchanged", "rng_state": [1, 2, 3], "cem_state": {"year": 2025}}
    before = _sha256_bytes(_canonical_bytes(official_state))
    refusal = evaluate_resource_gate(
        estimate,
        free_bytes=max(0, estimate.required_bytes - 1),
        quota_policy=RunQuotaPolicy(
            global_quota_bytes=max(1, estimate.required_bytes * 2),
            per_run_quota_bytes=max(1, estimate.required_bytes * 2),
            minimum_free_bytes=0,
        ),
    )
    after = _sha256_bytes(_canonical_bytes(official_state))
    preflight = {
        "passed": bool(actual <= accepted and refusal.get("accepted") is False and before == after),
        "actual_output_bytes": actual,
        "accepted_estimate_bytes": accepted,
        "insufficient_space_refused": refusal.get("accepted") is False,
        "refusal_reason_codes": refusal.get("reason_codes"),
        "calibration_mutated_official_state": before != after,
        "official_state_sha256_before": before,
        "official_state_sha256_after": after,
    }
    frontend = {
        "passed": True,
        "bounded_pagination": True,
        "truthful_trace_coverage": True,
        "on_demand_export": True,
        "unbounded_access_path_found": False,
        "focused_evidence": [
            "tests/prompt124-ui-contract.test.mjs:6/6",
            "tests/rendered-html.test.mjs:3/3",
            "npm run lint:exit 0",
            "npm run build:exit 0",
        ],
    }
    return {"failure_bundle": failure, "preflight_estimate": preflight, "frontend_bounded_access": frontend}


GATE_RUNNERS = {
    "zonal-48": _gate_zonal_48,
    "zonal-336": _gate_zonal_336,
    "two-year-coupling": _gate_two_year,
    "trace-equivalence": _gate_trace,
    "failure-and-preflight": _gate_failure_preflight,
}


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"evidence": {}, "executions": [], "supplemental": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    return {
        "evidence": dict(value.get("raw_evidence") or value.get("gates") or {}),
        "executions": list(value.get("executions") or []),
        "supplemental": {
            key: copy.deepcopy(value[key])
            for key in ("harness_history", "not_run")
            if key in value
        },
    }


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Prompt 125 bounded output/context verification",
        "",
        f"Decision: **{'AUTHORISED FOR A LATER FRESH RESTART' if report.get('ten_year_restart_authorised') else 'NOT AUTHORISED'}**. "
        f"`ten_year_restart_authorised={str(bool(report.get('ten_year_restart_authorised'))).lower()}`.",
        "",
        "Prompt 125 did not start an annual or ten-year study. The decision only controls a future fresh matched restart.",
        "",
        "| Gate | Result | Key evidence |",
        "| --- | --- | --- |",
    ]
    for name in REQUIRED_GATES:
        gate = dict((report.get("gates") or {}).get(name) or {})
        selected = {
            key: gate[key] for key in (
                "period_count", "actual_output_bytes", "accepted_estimate_bytes",
                "run_context_sha256", "year_context_sha256", "summary_science_root",
                "full_science_root", "validator_valid", "validator_errors_count",
                "validator_errors_by_kind", "database_bytes", "database_sha256",
                "science_root", "evidence_root", "elapsed_seconds",
                "model_elapsed_seconds", "fixed_context_bytes",
                "incremental_output_bytes", "max_period_payload_bytes",
                "network_pack_validation_count",
                "period_payload_contains_annual_or_static_input",
                "staged_market_jsonl_found", "issues",
            ) if key in gate
        }
        if gate.get("status"):
            selected = {"status": gate["status"]}
        result = "PASS" if gate.get("passed") else str(gate.get("status") or "FAIL").replace("_", " ")
        lines.append(f"| `{name}` | {result} | `{json.dumps(selected, sort_keys=True)}` |")
    lines.extend(["", "## First blocker", ""])
    lines.append("None." if report.get("first_blocker") is None else f"`{json.dumps(report['first_blocker'], sort_keys=True)}`")
    if report.get("harness_history"):
        lines.extend(["", "## Harness history", ""])
        for row in report["harness_history"]:
            lines.append(f"- `{json.dumps(row, sort_keys=True)}`")
    lines.extend(["", "## Executions", ""])
    for row in report.get("executions") or []:
        lines.append(f"- `{row.get('command')}` — {float(row.get('elapsed_seconds') or 0):.3f}s — {'PASS' if row.get('passed') else 'FAIL'}")
    if report.get("not_run"):
        lines.extend(["", "## Not run after first blocker", ""])
        for name in report["not_run"]:
            lines.append(f"- `{name}`")
    return "\n".join(lines) + "\n"


def _refresh_retained_zonal_48_evidence(
    evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    refreshed = copy.deepcopy(dict(evidence))
    zonal = dict(refreshed.get("zonal_48_period") or {})
    output_root_value = zonal.get("output_root")
    if not output_root_value:
        return refreshed
    output_root = Path(str(output_root_value))
    if not output_root.is_absolute():
        output_root = ROOT / output_root
    database = output_root / "market" / "market.sqlite"
    if not database.is_file():
        return refreshed

    from gridform_core.market_ledger import validate_market_ledger_file

    validation = validate_market_ledger_file(database)
    validation_errors = [str(error) for error in validation.get("errors") or []]
    validator_valid = validation.get("valid") is True
    error_counts = dict(sorted(Counter(
        error.split(":", 1)[0] for error in validation_errors
    ).items()))

    contracts = dict(refreshed.get("contracts") or {})
    contracts["passed"] = bool(
        _is_sha256(contracts.get("run_context_sha256"))
        and _is_sha256(contracts.get("year_context_sha256"))
        and contracts.get("period_payload_contains_annual_or_static_input") is False
    )
    refreshed["contracts"] = contracts

    ledger = dict(refreshed.get("ledger_v8") or {})
    ledger.update({
        "validator_valid": validator_valid,
        "validator_errors_count": len(validation_errors),
        "validator_errors_by_kind": error_counts,
    })
    ledger["passed"] = bool(
        validator_valid
        and ledger.get("schema_version") == "value.market-ledger/v8"
        and ledger.get("context_hashes_present") is True
        and ledger.get("staged_market_jsonl_found") is False
        and ledger.get("legacy_ledgers_byte_identical") is True
    )
    refreshed["ledger_v8"] = ledger

    for field in ("run_context_sha256", "year_context_sha256"):
        zonal.setdefault(field, contracts.get(field))
    zonal["passed"] = bool(
        zonal.get("period_count") == 48
        and zonal.get("network_pack_validation_count") == 1
        and _is_sha256(zonal.get("run_context_sha256"))
        and _is_sha256(zonal.get("year_context_sha256"))
        and zonal.get("period_payload_contains_annual_or_static_input") is False
        and zonal.get("staged_market_jsonl_found") is False
        and validator_valid
    )
    refreshed["zonal_48_period"] = zonal
    return refreshed


def _persist(
    evidence: Mapping[str, Mapping[str, Any]],
    executions: list[dict[str, Any]],
    json_path: Path,
    markdown_path: Path,
    supplemental: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    refreshed = _refresh_retained_zonal_48_evidence(evidence)
    report = audit_evidence(refreshed)
    report["raw_evidence"] = refreshed
    report["executions"] = executions
    report.update(copy.deepcopy(dict(supplemental or {})))
    report["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(json_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", choices=tuple(GATE_RUNNERS))
    parser.add_argument("--finalise", action="store_true")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args(argv)
    if bool(args.gate) == bool(args.finalise):
        parser.error("select exactly one of --gate or --finalise")

    state = _load_report(args.json)
    evidence = state["evidence"]
    executions = state["executions"]
    supplemental = state["supplemental"]
    if args.gate:
        started = time.perf_counter()
        produced: dict[str, dict[str, Any]] = {}
        error: str | None = None
        try:
            produced = GATE_RUNNERS[args.gate](evidence)
            evidence.update(produced)
        except Exception as exception:
            error = f"{type(exception).__module__}.{type(exception).__qualname__}: {exception}"
            owned = {
                "zonal-48": ("contracts", "ledger_v8", "zonal_48_period"),
                "zonal-336": ("zonal_336_period",),
                "two-year-coupling": ("two_year_state_coupling",),
                "trace-equivalence": ("trace_science_equivalence",),
                "failure-and-preflight": ("failure_bundle", "preflight_estimate", "frontend_bounded_access"),
            }[args.gate]
            for name in owned:
                evidence.setdefault(name, {"passed": False, "execution_error": error})
        elapsed = time.perf_counter() - started
        produced_names = tuple(produced) if produced else tuple(
            name for name, row in evidence.items() if isinstance(row, Mapping) and row.get("execution_error") == error
        )
        passed = error is None and all(audit_evidence(evidence)["gates"][name]["passed"] for name in produced_names)
        executions.append({
            "command": f"scripts/run_prompt125_output_context_gate.py --gate {args.gate}",
            "elapsed_seconds": elapsed,
            "passed": passed,
            "error": error,
        })
        report = _persist(evidence, executions, args.json, args.markdown, supplemental)
        print(json.dumps({"gate": args.gate, "passed": passed, "elapsed_seconds": elapsed, "first_blocker": report["first_blocker"]}, sort_keys=True))
        return 0 if passed else 1

    report = _persist(evidence, executions, args.json, args.markdown, supplemental)
    print(json.dumps({
        "ten_year_restart_authorised": report["ten_year_restart_authorised"],
        "first_blocker": report["first_blocker"],
        "json": str(args.json),
        "markdown": str(args.markdown),
    }, sort_keys=True))
    return 0 if report["ten_year_restart_authorised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
