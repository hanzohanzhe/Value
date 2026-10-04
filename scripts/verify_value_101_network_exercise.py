"""Verify a completed VALUE 101 copperplate/network teaching pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path, PurePosixPath


EXPECTED_PERIODS = 96
_AHEAD_FIELDS = (
    "year",
    "period",
    "period_id",
    "accepted_volume_mwh",
    "clearing_price_gbp_per_mwh",
    "schedule_mwh_by_asset",
    "storage_scheduled_action_mwh_by_asset",
    "extensions",
)


def _ahead_results(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("contract_type") != "AheadMarketResult":
            continue
        payload = dict(row["payload"])
        rows.append({field: payload[field] for field in _AHEAD_FIELDS})
    return rows


def _model_output_root(path: Path) -> Path:
    """Accept either a model-output directory or an ordinary saved Run root."""

    root = Path(path).resolve()
    nested = root / "model-output"
    return nested if (nested / "market").is_dir() else root


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_identity(run_root: Path, *, expected_role: str) -> dict[str, object]:
    root = Path(run_root).resolve()
    status_path = root / "status.json"
    project_path = root / "project-snapshot.json"
    artifact_index_path = root / "artifact-index.json"
    provenance_path = root / "provenance.json"
    for path in (status_path, project_path, artifact_index_path, provenance_path):
        if not path.is_file():
            raise ValueError(f"Saved Run evidence is missing: {path}")
    status = json.loads(status_path.read_text("utf-8"))
    project = json.loads(project_path.read_text("utf-8"))
    provenance = json.loads(provenance_path.read_text("utf-8"))
    status_role = dict(dict(status.get("extensions") or {}).get("value_101") or {}).get(
        "network_role"
    )
    project_role = dict(dict(project.get("extensions") or {}).get("value_101") or {}).get(
        "network_role"
    )
    run_id = str(status.get("id") or "")
    project_id = str(status.get("project_id") or "")
    artifact_index = json.loads(artifact_index_path.read_text("utf-8"))
    artifact_errors: list[str] = []
    artifact_ids: set[str] = set()
    records = artifact_index.get("artifacts")
    if artifact_index.get("schema_version") != "value.artifact-index/v1":
        artifact_errors.append("artifact-index schema is not value.artifact-index/v1")
    if not isinstance(records, list) or not records:
        artifact_errors.append("artifact-index has no artifact records")
        records = []
    for record in records:
        if not isinstance(record, dict):
            artifact_errors.append("artifact-index contains a non-object record")
            continue
        artifact_id = str(record.get("artifact_id") or "")
        pure = PurePosixPath(artifact_id)
        if (
            not artifact_id
            or pure.is_absolute()
            or ".." in pure.parts
            or "\\" in artifact_id
            or pure.as_posix() != artifact_id
        ):
            artifact_errors.append(f"unsafe artifact path: {artifact_id}")
            continue
        if artifact_id in artifact_ids:
            artifact_errors.append(f"duplicate artifact path: {artifact_id}")
            continue
        artifact_ids.add(artifact_id)
        artifact_path = root / Path(*pure.parts)
        if not artifact_path.is_file():
            artifact_errors.append(f"indexed artifact is missing: {artifact_id}")
            continue
        declared_bytes = record.get("bytes")
        if not isinstance(declared_bytes, int) or declared_bytes != artifact_path.stat().st_size:
            artifact_errors.append(f"indexed artifact byte count differs: {artifact_id}")
        if str(record.get("sha256") or "").lower() != _sha256(artifact_path):
            artifact_errors.append(f"indexed artifact SHA-256 differs: {artifact_id}")
    required_artifacts = {
        "data-pack-snapshot.json",
        "preflight.json",
        "project-snapshot.json",
        "model-output/resolved-run.json",
        "model-output/market/staged-market.jsonl",
        "model-output/market/market.sqlite",
    }
    for missing in sorted(required_artifacts - artifact_ids):
        artifact_errors.append(f"required artifact is not indexed: {missing}")

    output = _model_output_root(root)
    ahead_path = output / "market" / "staged-market.jsonl"
    sqlite_path = output / "market" / "market.sqlite"
    resolved_path = output / "resolved-run.json"
    for path in (ahead_path, sqlite_path, resolved_path):
        if not path.is_file():
            raise ValueError(f"Saved Run evidence is missing: {path}")
    for suffix in ("-wal", "-shm"):
        sidecar = sqlite_path.with_name(sqlite_path.name + suffix)
        if sidecar.exists():
            artifact_errors.append(
                "unsealed SQLite sidecar: "
                + sidecar.relative_to(root).as_posix()
            )
    resolved_run = json.loads(resolved_path.read_text("utf-8"))
    provenance_identity = dict(provenance.get("identity") or {})
    verified = all((
        run_id,
        project_id,
        run_id == root.name,
        status.get("status") == "completed",
        status.get("execution_status") == "passed",
        project.get("id") == project_id,
        status_role == expected_role,
        project_role == expected_role,
        status.get("input_tree_sha256"),
        project.get("revision_sha256"),
        not artifact_errors,
        provenance.get("completion", {}).get("status") == "completed",
        provenance_identity.get("run_id") == run_id,
        provenance_identity.get("project_id") == project_id,
        provenance_identity.get("resolved_run_schema") == "value.resolved-run/v2",
        provenance_identity.get("execution_kind") == "live_module",
        resolved_run.get("schema_version") == "value.resolved-run/v2",
        resolved_run.get("run_id") == run_id,
        resolved_run.get("project_id") == project_id,
    ))
    return {
        "run_root_name": root.name,
        "run_id": run_id,
        "project_id": project_id,
        "status": status.get("status"),
        "execution_status": status.get("execution_status"),
        "network_role": status_role,
        "input_tree_sha256": status.get("input_tree_sha256"),
        "project_revision_sha256": project.get("revision_sha256"),
        "status_sha256": _sha256(status_path),
        "project_snapshot_sha256": _sha256(project_path),
        "artifact_index_sha256": _sha256(artifact_index_path),
        "provenance_sha256": _sha256(provenance_path),
        "ahead_market_sha256": _sha256(ahead_path),
        "market_sqlite_sha256": _sha256(sqlite_path) if sqlite_path.is_file() else None,
        "artifact_index_verified": not artifact_errors,
        "artifact_index_errors": artifact_errors,
        "indexed_artifact_count": len(artifact_ids),
        "verified": bool(verified),
    }


def verify_network_pair(
    copperplate_run_root: Path,
    constrained_run_root: Path | None = None,
) -> dict[str, object]:
    if constrained_run_root is None:
        pair_root = Path(copperplate_run_root).resolve()
        copperplate_saved_root = pair_root / "copperplate"
        constrained_saved_root = pair_root / "constrained"
    else:
        pair_root = None
        copperplate_saved_root = Path(copperplate_run_root).resolve()
        constrained_saved_root = Path(constrained_run_root).resolve()
    identities = {
        "copperplate": _run_identity(
            copperplate_saved_root, expected_role="copperplate_control"
        ),
        "constrained": _run_identity(
            constrained_saved_root, expected_role="fixed_three_zone_constrained"
        ),
    }
    copperplate_root = _model_output_root(copperplate_saved_root)
    constrained_root = _model_output_root(constrained_saved_root)
    copperplate = _ahead_results(
        copperplate_root / "market" / "staged-market.jsonl"
    )
    constrained = _ahead_results(
        constrained_root / "market" / "staged-market.jsonl"
    )
    database = constrained_root / "market" / "market.sqlite"
    diagnostics = []
    for path in sorted((constrained_root / "market" / "zonal-redispatch").glob("*-diagnostics.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value.get("validation"), dict):
            diagnostics.append(value["validation"])
    immutable_uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(immutable_uri, uri=True)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise ValueError("Saved market.sqlite failed SQLite integrity_check")
        solver_rows, period_ids = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT period_id) "
            "FROM network_solver_diagnostics"
        ).fetchone()
        solver_classes = [
            str(row[0]) for row in connection.execute(
                "SELECT DISTINCT validation_class "
                "FROM network_solver_diagnostics ORDER BY validation_class"
            )
        ]
        congested_boundaries = int(connection.execute(
            "SELECT COUNT(*) FROM boundary_period_summary "
            "WHERE ABS(utilisation_fraction) >= 0.999999"
        ).fetchone()[0])
        redispatch_rows, redispatch_mwh, settlement_gbp = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(ABS(accepted_delta_mwh)), 0), "
            "COALESCE(SUM(cashflow_to_agent_gbp), 0) "
            "FROM redispatch_settlement"
        ).fetchone()
        network_cost_gbp, blackout_mwh = connection.execute(
            "SELECT COALESCE(SUM(network_constraint_cost_gbp), 0), "
            "COALESCE(SUM(blackout_mwh), 0) FROM zonal_period_accounting"
        ).fetchone()
        added, avoided, net, total = connection.execute(
            "SELECT COALESCE(SUM(redispatch_added_curtailment_mwh), 0), "
            "COALESCE(SUM(redispatch_avoided_curtailment_mwh), 0), "
            "COALESCE(SUM(redispatch_net_impact_mwh), 0), "
            "COALESCE(SUM(total_curtailment_mwh), 0) "
            "FROM vre_curtailment_period"
        ).fetchone()
        energy_residual = float(connection.execute(
            "SELECT COALESCE(MAX(ABS(energy_balance_residual_mwh)), 0) FROM period_summary"
        ).fetchone()[0])
        curtailment_residual = float(connection.execute(
            "SELECT COALESCE(MAX(ABS(identity_residual_mwh)), 0) FROM vre_curtailment_period"
        ).fetchone()[0])
        cost_residual = float(connection.execute(
            "SELECT COALESCE(MAX(ABS(network_constraint_cost_gbp - "
            "(zonal_resource_cost_gbp - realised_copperplate_resource_cost_gbp))), 0) "
            "FROM zonal_period_accounting"
        ).fetchone()[0])
        corridor_residual = float(connection.execute(
            "SELECT COALESCE(MAX(CASE WHEN transfer_mwh >= 0 THEN "
            "MAX(transfer_mwh - forward_capacity_mwh, 0) ELSE "
            "MAX(-transfer_mwh - reverse_capacity_mwh, 0) END), 0) "
            "FROM boundary_period_summary"
        ).fetchone()[0])

    solver_equality_residual = max(
        (abs(float(row.get("maximum_equality_residual", 0.0))) for row in diagnostics),
        default=float("inf"),
    )
    solver_inequality_residual = max(
        (abs(float(row.get("maximum_inequality_violation", 0.0))) for row in diagnostics),
        default=float("inf"),
    )
    network_accounting = {
        "status": "reconciled" if diagnostics and all(
            value <= limit for value, limit in (
                (energy_residual, 1e-6),
                (solver_equality_residual, 1e-6),
                (max(corridor_residual, solver_inequality_residual), 1e-6),
                (curtailment_residual, 1e-6),
                (cost_residual, 1e-3),
            )
        ) else "failed",
        "energy_balance_residual_mwh": energy_residual,
        "soc_residual_mwh": solver_equality_residual,
        "corridor_capacity_violation_mwh": max(
            corridor_residual, solver_inequality_residual
        ),
        "curtailment_identity_residual_mwh": curtailment_residual,
        "cost_residual_gbp": cost_residual,
        "soc_residual_semantics": (
            "Conservative maximum equality residual across the solved zonal problem; "
            "this includes storage state equations and nodal balance equations."
        ),
        "corridor_residual_semantics": (
            "Maximum of the independently reconstructed signed corridor-capacity "
            "violation and the solver validation inequality violation."
        ),
    }

    checks = {
        "actual_saved_runs_verified": (
            identities["copperplate"]["verified"] is True
            and identities["constrained"]["verified"] is True
            and copperplate_saved_root != constrained_saved_root
            and identities["copperplate"]["run_id"]
            != identities["constrained"]["run_id"]
        ),
        "both_runs_have_96_ahead_results": (
            len(copperplate) == len(constrained) == EXPECTED_PERIODS
        ),
        "ahead_schedules_are_identical": copperplate == constrained,
        "network_period_ids_are_unique_across_years": (
            int(period_ids) == EXPECTED_PERIODS
        ),
        "three_solver_phases_per_period": (
            int(solver_rows) == EXPECTED_PERIODS * 3
        ),
        "all_solver_locks_are_go": solver_classes == ["GO"],
        "congestion_is_observed": congested_boundaries > 0,
        "redispatch_is_observed": int(redispatch_rows) > 0 and float(redispatch_mwh) > 0,
        "network_constraint_cost_is_observed": float(network_cost_gbp) > 0,
        "no_material_load_shedding": abs(float(blackout_mwh)) <= 1e-8,
        "network_accounting_reconciles": network_accounting["status"] == "reconciled",
    }
    return {
        "schema_version": "value.101-network-live-verification/v2",
        "decision": "PASS" if all(checks.values()) else "FAIL",
        "scope": (
            "two matched 48-period years; teaching diagnostic, not annual economics"
        ),
        "run_root_name": pair_root.name if pair_root is not None else None,
        "local_run_root_bundled": False,
        "run_identity": identities,
        "checks": checks,
        "metrics": {
            "periods": EXPECTED_PERIODS,
            "solver_rows": int(solver_rows),
            "congested_boundary_periods": congested_boundaries,
            "redispatch_settlement_rows": int(redispatch_rows),
            "absolute_redispatch_mwh": float(redispatch_mwh),
            "redispatch_settlement_gbp": float(settlement_gbp),
            "network_constraint_cost_gbp": float(network_cost_gbp),
            "blackout_mwh": float(blackout_mwh),
            "redispatch_added_curtailment_mwh": float(added),
            "redispatch_avoided_curtailment_mwh": float(avoided),
            "redispatch_net_curtailment_impact_mwh": float(net),
            "total_curtailment_mwh": float(total),
        },
        "network_accounting": network_accounting,
        "method_boundary": (
            "fixed lossless zonal transport and pay-as-bid redispatch; "
            "not DC load flow, AC power flow, N-1 security or transmission expansion"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    pair = parser.add_mutually_exclusive_group(required=True)
    pair.add_argument("--run-root", type=Path)
    pair.add_argument("--copperplate-run-root", type=Path)
    parser.add_argument("--constrained-run-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.run_root is not None:
        if args.constrained_run_root is not None:
            parser.error("--constrained-run-root cannot be combined with --run-root")
        report = verify_network_pair(args.run_root)
    else:
        if args.constrained_run_root is None:
            parser.error("--constrained-run-root is required with --copperplate-run-root")
        report = verify_network_pair(
            args.copperplate_run_root,
            args.constrained_run_root,
        )
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="")
    print(encoded, end="")
    if report["decision"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
