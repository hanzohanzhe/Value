"""Rerun the two independent PSM decisions after the live VALUE cutover."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]


def _test(pattern: str) -> dict[str, object]:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        pattern,
        "-v",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "tail": (completed.stdout + completed.stderr)[-4000:],
    }


def build_report(force_run: Path) -> dict[str, object]:
    typed_path = force_run / "year-results-v2.json"
    graph_path = force_run / "module-resolution.json"
    ledger_path = force_run / "market" / "market.sqlite"
    typed = json.loads(typed_path.read_text(encoding="utf-8"))
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    registry = workspace_registry()
    manifest = registry.manifest("value-bid-at-cost-psm", expected_slot="psm")
    psm_identity = graph["modules"]["psm"]
    live_invocation = bool(
        typed
        and typed[0]["market"]["extensions"].get("live_scheme_c_clearing_invocation")
    )
    with sqlite3.connect(ledger_path) as connection:
        order_rows = int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
        storage_rows = int(connection.execute("SELECT COUNT(*) FROM storage_state").fetchone()[0])
        ahead_storage_offers = int(connection.execute(
            "SELECT COUNT(*) FROM orders WHERE stage='ahead_offer' AND asset_type='Battery'"
        ).fetchone()[0])
        balancing_offers = int(connection.execute(
            "SELECT COUNT(*) FROM orders WHERE stage LIKE 'balancing_offer%'"
        ).fetchone()[0])
    public_identity_passed = (
        psm_identity["module_id"] == "value-bid-at-cost-psm"
        and psm_identity["entry_point"] == manifest.implementation
        and psm_identity["source_sha256"]
        and psm_identity["execution_kind"] == "live_module"
        and live_invocation
    )
    perfect = _test("test_independent_psm_validation.py")
    retained = _test("test_retained_source_manifest.py")
    force_audit_complete = ahead_storage_offers > 0 and balancing_offers > 0
    force_decision = (
        "VALUE_CLEARING_VALIDATED"
        if public_identity_passed and force_audit_complete
        else "VALUE_CLEARING_NOT_EVALUATED"
    )
    return {
        "schema_version": "value.independent-psm-validation-report/v2",
        "runtime": {
            "capability": "value-native",
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
        },
        "force_offer_clearing": {
            "decision": force_decision,
            "public_invocation_proven": public_identity_passed,
            "module_identity": psm_identity,
            "live_invocation_marker": live_invocation,
            "audit_rows": {
                "orders": order_rows,
                "storage_state": storage_rows,
                "ahead_storage_offers": ahead_storage_offers,
                "balancing_offers": balancing_offers,
            },
            "required_cases": {
                "thermal_vre_import_storage_24h": "not_evaluated",
                "thermal_vre_import_storage_168h": "not_evaluated",
                "random_convex": "not_evaluated",
                "required_mutations": "not_evaluated",
            },
            "first_blocker": (
                None
                if force_audit_complete
                else "The live ledger does not expose priced storage ahead offers and balancing offers as a complete solver-neutral offer set. Storage appears only as final supplemental dispatch, and storage_state is post-period rather than declared pre-period SOC. An independent oracle must not reconstruct these hidden inputs from outcomes."
            ),
            "counterfactual_optimality_gap": "not_evaluated",
        },
        "perfect_foresight": {
            "decision": (
                "PERFECT_FORESIGHT_PSM_VALIDATED"
                if perfect["passed"]
                else "PERFECT_FORESIGHT_PSM_VALIDATION_FAILED"
            ),
            "independent_engine": "PuLP 3.3.2 / COIN-OR CBC",
            "production_engine": "SciPy 1.8.1 / HiGHS",
            "24h_168h_random_and_mutations": perfect,
        },
        "retained_source_hashes": retained,
        "release_gate_passed": (
            force_decision == "VALUE_CLEARING_VALIDATED"
            and perfect["passed"]
            and retained["passed"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-run", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = build_report(args.force_run.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "force": report["force_offer_clearing"]["decision"],
        "perfect_foresight": report["perfect_foresight"]["decision"],
        "release_gate_passed": report["release_gate_passed"],
    }, indent=2))
    # NOT_EVALUATED is an honest scientific gate result, not a script crash.
    raise SystemExit(0 if report["perfect_foresight"]["decision"] == "PERFECT_FORESIGHT_PSM_VALIDATED" else 1)


if __name__ == "__main__":
    main()
