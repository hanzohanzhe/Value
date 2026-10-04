"""Bounded read-only queries over completed optional-domain run artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Mapping


SCHEMA_VERSION = "value.domain-results/v1"
MAX_PAGE = 500
MAX_AC_QUERY_PERIODS = 336


class DomainResultError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _completed(run_root: Path) -> Mapping[str, object]:
    status_path = run_root / "status.json"
    if not status_path.is_file():
        raise DomainResultError("Run status is missing")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("status") not in {"completed", "archived"}:
        raise DomainResultError("Optional-domain results are available only for immutable completed runs")
    return status


def _identity(run_root: Path) -> dict[str, object]:
    graph_path = run_root / "model-output" / "module-resolution.json"
    if not graph_path.is_file():
        graph_path = run_root / "input-snapshot" / "module-resolution.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8")) if graph_path.is_file() else {}
    project = {}
    for candidate in (
        run_root / "input-snapshot" / "project.json",
        run_root / "project-snapshot.json",
    ):
        if candidate.is_file():
            project = json.loads(candidate.read_text(encoding="utf-8"))
            break
    return {
        "run_id": run_root.name,
        "project_id": project.get("id"),
        "project_revision_sha256": project.get("revision_sha256"),
        "graph_sha256": graph.get("graph_sha256"),
        "modules": graph.get("modules") or project.get("modules") or {},
        "extensions": (graph.get("extension_graph") or {}).get("extensions") or project.get("selected_extensions") or [],
    }


def _years(root: Path, prefix: str, suffix: str) -> list[int]:
    result = []
    for path in root.glob(f"{prefix}*{suffix}"):
        raw = path.name[len(prefix): -len(suffix)] if suffix else path.name[len(prefix):]
        try:
            result.append(int(raw))
        except ValueError:
            continue
    return sorted(set(result))


def domain_result_capabilities(run_root: Path) -> dict[str, object]:
    _completed(run_root)
    network_root = run_root / "model-output" / "solver" / "network"
    ac_root = run_root / "model-output" / "solver" / "ac"
    expansion_root = run_root / "model-output" / "network"
    if not expansion_root.is_dir():
        expansion_root = run_root / "model-output" / "network-expansion"
    dc_years = _years(network_root, "dc-network-", ".sqlite")
    ac_years = _years(ac_root, "ac-feasibility-", ".json")
    expansion = next(iter((run_root / "model-output").rglob("network-expansion.sqlite")), None)
    hydrology = list((run_root / "model-output").rglob("*hydrolog*.sqlite")) + list((run_root / "model-output").rglob("*hydrolog*.json"))
    identity = _identity(run_root)
    return {
        "schema_version": "value.domain-result-capabilities/v1",
        "identity": identity,
        "capabilities": {
            "network_dc": {
                "status": "supported" if dc_years else "unsupported",
                "years": dc_years,
                "reason": None if dc_years else "No DC network artifact is indexed for this run.",
            },
            "ac_feasibility": {
                "status": "experimental" if ac_years else "unsupported",
                "years": ac_years,
                "claim": "Local feasibility of a declared schedule; not AC OPF.",
                "reason": None if ac_years else "No AC feasibility artifact is indexed for this run.",
            },
            "hydrology": {
                "status": "experimental" if hydrology else "not_evaluated",
                "reason": None if hydrology else "The ordinary annual application emitted no natural-flow hydrology result artifact; no water quantity is reconstructed.",
            },
            "network_expansion": {
                "status": "experimental" if expansion else "unsupported",
                "reason": None if expansion else "No network-expansion history artifact is indexed for this run.",
            },
        },
    }


def _dc_paths(run_root: Path, year: int) -> tuple[Path, Path, Path]:
    root = run_root / "model-output" / "solver" / "network"
    paths = (
        root / f"dc-network-{year}.sqlite",
        root / f"dc-network-{year}.json",
        root / f"declared-network-inputs-{year}.jsonl",
    )
    if not all(path.is_file() for path in paths):
        raise DomainResultError(f"DC network artifacts are incomplete for {year}")
    return paths


def _declared_topology(path: Path) -> dict[str, object]:
    first = next((line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()), "")
    if not first:
        raise DomainResultError("Declared network input artifact is empty")
    row = json.loads(first)
    envelope = json.loads(row["payload_json"])
    payload = envelope["payload"]
    branches = {
        str(item["branch_id"]): {
            **item,
            "rating_mw": float(item.get("thermal_rating_mw") or 0.0) * int(item.get("circuits") or 1),
        }
        for item in payload.get("branches", ())
    }
    return {
        "buses": list(payload.get("buses", ())),
        "branches": branches,
        "asset_to_bus": dict(payload.get("asset_to_bus") or {}),
        "reference_buses": list(payload.get("reference_buses", ())),
        "period_hours": float(payload.get("period_hours") or 0.0),
        "source_artifact_sha256": _sha256(path),
    }


def _validate_dc_database(connection: sqlite3.Connection, topology: Mapping[str, object]) -> dict[str, float]:
    """Fail closed when the indexed values no longer satisfy their declared topology."""

    branches = dict(topology["branches"])
    period_hours = float(topology.get("period_hours") or 0.0)
    if period_hours <= 0:
        raise DomainResultError("Declared network period length is invalid")
    connection.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _branch_contract(branch_id TEXT PRIMARY KEY, from_bus TEXT, to_bus TEXT, rating_mw REAL)"
    )
    connection.execute("DELETE FROM _branch_contract")
    connection.executemany(
        "INSERT INTO _branch_contract VALUES (?,?,?,?)",
        [
            (branch_id, item.get("from_bus"), item.get("to_bus"), item.get("rating_mw"))
            for branch_id, item in branches.items()
        ],
    )
    unknown = int(connection.execute(
        "SELECT COUNT(*) FROM period_branch p LEFT JOIN _branch_contract b USING(branch_id) WHERE b.branch_id IS NULL"
    ).fetchone()[0])
    if unknown:
        raise DomainResultError("The DC result index contains an undeclared branch")
    maximum_branch_violation = float(connection.execute(
        "SELECT COALESCE(MAX(MAX(ABS(p.flow_mw)-b.rating_mw,0)),0) "
        "FROM period_branch p JOIN _branch_contract b USING(branch_id)"
    ).fetchone()[0])
    if maximum_branch_violation > 1e-6:
        raise DomainResultError(
            f"The DC result index violates a declared branch rating by {maximum_branch_violation} MW"
        )
    connection.executescript(
        "DROP TABLE IF EXISTS _net_export;"
        "CREATE TEMP TABLE _net_export AS "
        "SELECT period_id,bus_id,SUM(value) net_export_mwh FROM ("
        f"SELECT p.period_id,b.from_bus bus_id,p.flow_mw*{period_hours:.17g} value FROM period_branch p JOIN _branch_contract b USING(branch_id) "
        "UNION ALL "
        f"SELECT p.period_id,b.to_bus bus_id,-p.flow_mw*{period_hours:.17g} value FROM period_branch p JOIN _branch_contract b USING(branch_id)"
        ") GROUP BY period_id,bus_id;"
        "CREATE INDEX _net_export_identity ON _net_export(period_id,bus_id);"
    )
    maximum_balance_residual = float(connection.execute(
        "SELECT COALESCE(MAX(ABS(p.injection_mwh-p.withdrawal_mwh-COALESCE(n.net_export_mwh,0))),0) "
        "FROM period_bus p LEFT JOIN _net_export n USING(period_id,bus_id)"
    ).fetchone()[0])
    if maximum_balance_residual > 1e-6:
        raise DomainResultError(
            f"The DC result index violates nodal balance by {maximum_balance_residual} MWh"
        )
    missing_prices = int(connection.execute(
        "SELECT COUNT(*) FROM period_bus WHERE price_gbp_per_mwh IS NULL"
    ).fetchone()[0])
    if missing_prices:
        raise DomainResultError("The DC result index has missing nodal LP duals")
    return {
        "maximum_branch_violation_mw": maximum_branch_violation,
        "maximum_nodal_balance_residual_mwh": maximum_balance_residual,
    }


def query_network_summary(run_root: Path, *, year: int) -> dict[str, object]:
    _completed(run_root)
    database, output_path, declared_path = _dc_paths(run_root, year)
    topology = _declared_topology(declared_path)
    branches = topology["branches"]
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        integrity = _validate_dc_database(connection, topology)
        bus = connection.execute(
            "SELECT COUNT(DISTINCT period_id) periods, COUNT(DISTINCT bus_id) buses, "
            "SUM(blackout_mwh) blackout_mwh, MIN(price_gbp_per_mwh) minimum_price, "
            "MAX(price_gbp_per_mwh) maximum_price FROM period_bus"
        ).fetchone()
        rows = connection.execute(
            "SELECT branch_id, MAX(ABS(flow_mw)) maximum_absolute_flow_mw, "
            "AVG(ABS(flow_mw)) mean_absolute_flow_mw FROM period_branch GROUP BY branch_id ORDER BY branch_id"
        ).fetchall()
    branch_rows = []
    congestion_periods = 0
    with closing(sqlite3.connect(database)) as connection:
        for row in rows:
            branch = dict(branches.get(str(row["branch_id"])) or {})
            rating = float(branch.get("rating_mw") or 0.0)
            if rating > 0:
                congestion_periods += int(connection.execute(
                    "SELECT COUNT(*) FROM period_branch WHERE branch_id=? AND ABS(flow_mw)>=?-1e-7",
                    (row["branch_id"], rating),
                ).fetchone()[0])
            branch_rows.append({
                "branch_id": row["branch_id"],
                "from_bus": branch.get("from_bus"), "to_bus": branch.get("to_bus"),
                "rating_mw": rating if rating > 0 else None,
                "maximum_absolute_flow_mw": row["maximum_absolute_flow_mw"],
                "maximum_utilisation_fraction": (
                    float(row["maximum_absolute_flow_mw"]) / rating if rating > 0 else None
                ),
                "mean_absolute_flow_mw": row["mean_absolute_flow_mw"],
            })
    output = json.loads(output_path.read_text(encoding="utf-8"))
    artifact_sha = _sha256(database)
    return {
        "schema_version": SCHEMA_VERSION,
        "identity": _identity(run_root),
        "domain": "network_dc", "year": year,
        "source_artifacts": {
            "period_index_sha256": artifact_sha,
            "typed_result_sha256": _sha256(output_path),
            "declared_input_sha256": topology["source_artifact_sha256"],
        },
        "metrics": {
            "periods": {"value": int(bus["periods"] or 0), "unit": "periods", "definition_id": "value.network.period-count/v1", "source_artifact_sha256": artifact_sha},
            "blackout_mwh": {"value": float(bus["blackout_mwh"] or 0.0), "unit": "MWh", "definition_id": "value.network.nodal-blackout-sum/v1", "source_artifact_sha256": artifact_sha},
            "minimum_nodal_price": {"value": bus["minimum_price"], "unit": "GBP/MWh", "definition_id": "value.network.minimum-nodal-lp-dual/v1", "source_artifact_sha256": artifact_sha},
            "maximum_nodal_price": {"value": bus["maximum_price"], "unit": "GBP/MWh", "definition_id": "value.network.maximum-nodal-lp-dual/v1", "source_artifact_sha256": artifact_sha},
            "congestion_branch_periods": {"value": congestion_periods, "unit": "branch-periods", "definition_id": "value.network.rating-binding-count/v1", "source_artifact_sha256": artifact_sha},
            "maximum_nodal_residual": {"value": output.get("maximum_residual"), "unit": "MWh", "definition_id": "value.network.maximum-model-residual/v1", "source_artifact_sha256": _sha256(output_path)},
            "indexed_nodal_balance_residual": {"value": integrity["maximum_nodal_balance_residual_mwh"], "unit": "MWh", "definition_id": "value.network.indexed-nodal-balance-audit/v1", "source_artifact_sha256": artifact_sha},
        },
        "topology": {
            "buses": topology["buses"],
            "branches": list(branches.values()),
            "reference_buses": topology["reference_buses"],
            "placement": "schematic_not_geographic",
        },
        "branch_summary": branch_rows,
        "storage_soc": {
            "status": "linked",
            "endpoint": f"/api/runs/{run_root.name}/market/storage?year={year}",
            "reason": "Storage SOC remains in the authoritative market ledger and is not duplicated here.",
        },
    }


def query_network_periods(
    run_root: Path,
    *,
    year: int,
    limit: int = 48,
    offset: int = 0,
) -> dict[str, object]:
    _completed(run_root)
    database, _output, declared = _dc_paths(run_root, year)
    topology = _declared_topology(declared)
    limit = max(1, min(int(limit), MAX_PAGE))
    offset = max(0, int(offset))
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        _validate_dc_database(connection, topology)
        total = int(connection.execute("SELECT COUNT(DISTINCT period_id) FROM period_bus").fetchone()[0])
        periods = [row[0] for row in connection.execute(
            "SELECT period_id FROM period_bus GROUP BY period_id ORDER BY MIN(rowid) LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()]
        items = []
        for period_id in periods:
            row = connection.execute(
                "SELECT SUM(injection_mwh) injection_mwh, SUM(withdrawal_mwh) withdrawal_mwh, "
                "SUM(blackout_mwh) blackout_mwh, AVG(price_gbp_per_mwh) mean_nodal_price "
                "FROM period_bus WHERE period_id=?", (period_id,),
            ).fetchone()
            buses = [dict(item) for item in connection.execute(
                "SELECT bus_id,injection_mwh,withdrawal_mwh,blackout_mwh,angle_rad,price_gbp_per_mwh "
                "FROM period_bus WHERE period_id=? ORDER BY bus_id", (period_id,),
            ).fetchall()]
            items.append({"period_id": period_id, **dict(row), "buses": buses})
    return {
        "schema_version": "value.network-period-query/v1", "identity": _identity(run_root),
        "year": year, "total": total, "limit": limit, "offset": offset,
        "source_artifact_sha256": _sha256(database),
        "definitions": {
            "injection_mwh": "sum of canonical nodal injections", "withdrawal_mwh": "sum of canonical nodal withdrawals",
            "blackout_mwh": "sum of bus load shed", "mean_nodal_price": "unweighted mean of nodal LP balance duals; not a settlement price",
            "angle_rad": "DC voltage angle relative to the declared island reference bus",
            "price_gbp_per_mwh": "nodal LP balance dual; not a settlement price",
        },
        "units": {"injection_mwh": "MWh", "withdrawal_mwh": "MWh", "blackout_mwh": "MWh", "mean_nodal_price": "GBP/MWh", "angle_rad": "radians", "price_gbp_per_mwh": "GBP/MWh"},
        "items": items,
        "topology_source_sha256": topology["source_artifact_sha256"],
    }


def query_network_branches(
    run_root: Path,
    *,
    year: int,
    period_id: str | None = None,
    branch_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, object]:
    _completed(run_root)
    database, _output, declared = _dc_paths(run_root, year)
    topology = _declared_topology(declared)
    branches = topology["branches"]
    clauses, values = [], []
    if period_id:
        clauses.append("period_id=?"); values.append(period_id)
    if branch_id:
        clauses.append("branch_id=?"); values.append(branch_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    limit, offset = max(1, min(int(limit), MAX_PAGE)), max(0, int(offset))
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        _validate_dc_database(connection, topology)
        total = int(connection.execute("SELECT COUNT(*) FROM period_branch" + where, values).fetchone()[0])
        rows = connection.execute(
            "SELECT period_id, branch_id, flow_mw FROM period_branch" + where + " ORDER BY rowid LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
    items = []
    for row in rows:
        branch = dict(branches.get(str(row["branch_id"])) or {})
        rating = float(branch.get("rating_mw") or 0.0)
        flow = float(row["flow_mw"])
        items.append({
            **dict(row), "from_bus": branch.get("from_bus"), "to_bus": branch.get("to_bus"),
            "rating_mw": rating if rating > 0 else None,
            "utilisation_fraction": abs(flow) / rating if rating > 0 else None,
            "utilisation_status": "available" if rating > 0 else "not_evaluated",
        })
    return {
        "schema_version": "value.network-branch-query/v1", "identity": _identity(run_root),
        "year": year, "total": total, "limit": limit, "offset": offset,
        "source_artifact_sha256": _sha256(database),
        "definition_id": "value.network.branch-flow-and-rating/v1",
        "units": {"flow_mw": "MW", "rating_mw": "MW", "utilisation_fraction": "fraction"},
        "items": items,
    }


def _ac_path(run_root: Path, year: int) -> Path:
    path = run_root / "model-output" / "solver" / "ac" / f"ac-feasibility-{year}.json"
    if not path.is_file():
        raise DomainResultError(f"AC feasibility artifact is missing for {year}")
    return path


def query_ac_results(
    run_root: Path,
    *,
    year: int,
    limit: int = 48,
    offset: int = 0,
) -> dict[str, object]:
    _completed(run_root)
    path = _ac_path(run_root, year)
    payload = json.loads(path.read_text(encoding="utf-8"))
    periods = list(payload.get("periods") or [])
    if len(periods) > MAX_AC_QUERY_PERIODS:
        raise DomainResultError(
            "Annual AC JSON is not an indexed query artifact; bounded browser inspection is limited to 336 periods"
        )
    limit, offset = max(1, min(int(limit), MAX_PAGE)), max(0, int(offset))
    items = []
    for period in periods[offset: offset + limit]:
        required = {
            "voltage_magnitude_pu", "voltage_angle_radians",
            "reactive_generation_mvar_by_bus", "branch_from_active_mw",
            "branch_from_reactive_mvar", "active_loss_mw_by_branch",
            "residuals", "violations",
        }
        missing = sorted(required.difference(period))
        if missing:
            raise DomainResultError(
                "AC feasibility evidence is incomplete; missing " + ", ".join(missing)
            )
        voltage = [float(value) for value in dict(period.get("voltage_magnitude_pu") or {}).values()]
        losses = dict(period.get("active_loss_mw_by_branch") or {})
        branch_p = dict(period.get("branch_from_active_mw") or {})
        branch_q = dict(period.get("branch_from_reactive_mvar") or {})
        items.append({
            "period_id": period.get("period_id"), "status": period.get("status"),
            "minimum_voltage_pu": min(voltage) if voltage else None,
            "maximum_voltage_pu": max(voltage) if voltage else None,
            "active_loss_mw": sum(float(value) for value in losses.values()) if losses else None,
            "branch_mva": {
                branch: math.hypot(float(active), float(branch_q.get(branch, 0.0)))
                for branch, active in branch_p.items()
            },
            "reactive_generation_mvar_by_bus": period.get("reactive_generation_mvar_by_bus"),
            "residuals": period.get("residuals"), "violations": period.get("violations"),
        })
    artifact_sha = _sha256(path)
    return {
        "schema_version": "value.ac-result-query/v1", "identity": _identity(run_root),
        "domain": "ac_feasibility", "claim": "Local feasibility of a declared active schedule; not AC OPF.",
        "year": year, "total": len(periods), "limit": limit, "offset": offset,
        "source_artifact_sha256": artifact_sha,
        "summary": {
            "solver_status": payload.get("solver_status"),
            "convergence_class": payload.get("convergence_class"),
            "maximum_active_residual_mw": payload.get("maximum_active_residual_mw"),
            "maximum_reactive_residual_mvar": payload.get("maximum_reactive_residual_mvar"),
            "maximum_equipment_violation": payload.get("maximum_equipment_violation"),
            "unsupported": payload.get("unsupported"),
            "branch_rating_utilisation": {"status": "not_evaluated", "reason": "The immutable AC result artifact does not carry branch ratings; no utilisation is reconstructed."},
        },
        "units": {"voltage": "p.u.", "angle": "radians", "reactive": "Mvar", "loss": "MW", "branch_mva": "MVA"},
        "items": items,
    }


def _expansion_path(run_root: Path) -> Path:
    candidates = list((run_root / "model-output").rglob("network-expansion.sqlite"))
    if len(candidates) != 1:
        raise DomainResultError("A unique network-expansion index is unavailable")
    return candidates[0]


def query_expansion_summary(run_root: Path) -> dict[str, object]:
    _completed(run_root)
    path = _expansion_path(run_root)
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        years = [dict(row) for row in connection.execute("SELECT * FROM annual_summary ORDER BY year")]
    return {
        "schema_version": "value.network-expansion-summary-query/v1",
        "identity": _identity(run_root), "status": "experimental",
        "source_artifact_sha256": _sha256(path), "years": years,
        "lineage": "candidate → proposal → planning → commissioned / failed / retired",
        "counterfactual_claim": "not_claimed_without_a_controlled_comparison_study",
        "ledger_links": {
            "cost_and_carbon_artifact_index": f"/api/runs/{run_root.name}/artifacts",
        },
    }


def query_expansion_events(
    run_root: Path,
    *,
    year: int | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, object]:
    _completed(run_root)
    path = _expansion_path(run_root)
    clauses, values = [], []
    if year is not None:
        clauses.append("year=?"); values.append(int(year))
    if event_type:
        clauses.append("event_type=?"); values.append(event_type)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    limit, offset = max(1, min(int(limit), MAX_PAGE)), max(0, int(offset))
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        total = int(connection.execute("SELECT COUNT(*) FROM events" + where, values).fetchone()[0])
        rows = connection.execute(
            "SELECT year,event_id,event_type,candidate_id,project_id,asset_id,corridor_id,from_bus,to_bus,circuits,rating_mw,reason_code "
            "FROM events" + where + " ORDER BY year,event_id LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
    return {
        "schema_version": "value.network-expansion-event-query/v1",
        "identity": _identity(run_root), "total": total, "limit": limit, "offset": offset,
        "source_artifact_sha256": _sha256(path), "items": [dict(row) for row in rows],
        "units": {"rating_mw": "MW", "circuits": "circuits"},
    }
