"""Versioned, read-only final VRE attribution queries; no model execution."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Mapping

from gridform_core.market_ledger import _read_only_connection, market_ledger_capabilities, ATTRIBUTION_SCHEMA_VERSIONS
from gridform_core.result_advisories import withheld_annual_result
from gridform_core.result_coverage import REASON_CANCELLED, REASON_NON_ANNUAL, is_non_annual, legacy_reason, result_coverage, stopped_reason, year_bounds_from_rows
from gridform_core.results_summary import validate_vre_curtailment_attribution
from gridform_core.zonal_results import query_zonal_annual_brief, query_zonal_results
from gridform_core.vre_curtailment_attribution import ATTRIBUTION_METHOD_ID

CONTRACT = "value.vre-curtailment-attribution/v2"
FIELDS = ("available_mwh", "economic_mwh", "forecast_added_mwh", "forecast_avoided_mwh", "redispatch_added_mwh", "redispatch_avoided_mwh", "redispatch_net_mwh", "total_mwh", "rate", "identity_residual_mwh", "aggregate_tolerance_mwh")
PERIOD_FIELDS = dict(zip(FIELDS, ("realised_available_vre_mwh", "economic_curtailment_mwh", "forecast_added_curtailment_mwh", "forecast_avoided_curtailment_mwh", "redispatch_added_curtailment_mwh", "redispatch_avoided_curtailment_mwh", "redispatch_net_impact_mwh", "total_curtailment_mwh", "curtailment_rate", "identity_residual_mwh", "validation_tolerance_mwh")))


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GF_RESULT_INVALID: artifact must be an object")
    return payload


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integer(query: Mapping, key: str, default=None):
    value = query.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{key} must be an integer")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _validated(row: Mapping) -> dict:
    result = dict(row)
    for field in FIELDS:
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("GF_RESULT_INVALID: nonfinite or missing " + field)
    if any(row[field] < 0 for field in ("economic_mwh", "forecast_added_mwh", "forecast_avoided_mwh", "redispatch_added_mwh", "redispatch_avoided_mwh")):
        raise ValueError("GF_RESULT_INVALID: gross curtailment components cannot be negative")
    tolerance = row["aggregate_tolerance_mwh"]
    available, total = row["available_mwh"], row["total_mwh"]
    residual = row["economic_mwh"] + row["forecast_added_mwh"] - row["forecast_avoided_mwh"] + row["redispatch_added_mwh"] - row["redispatch_avoided_mwh"] - total
    rate = total / available if available else 0.0
    if tolerance < 0 or available < 0 or total < 0 or total > available + tolerance or not 0 <= row["rate"] <= 1 or not math.isclose(row["rate"], rate, rel_tol=1e-9, abs_tol=1e-12) or abs(residual) > tolerance or not math.isclose(row["identity_residual_mwh"], residual, rel_tol=1e-9, abs_tol=1e-12) or abs(row["redispatch_net_mwh"] - row["redispatch_added_mwh"] + row["redispatch_avoided_mwh"]) > tolerance:
        raise ValueError("GF_RESULT_INVALID: attribution identity does not reconcile")
    return result


def query_vre_curtailment_results(run_root: Path, query: Mapping[str, object]) -> dict:
    allowed = {"source", "resolution", "year", "period_from", "period_to", "limit", "offset"}
    if set(query) - allowed:
        raise ValueError("Unsupported result query field: " + ", ".join(sorted(set(query) - allowed)))
    requested_source = str(query.get("source", "auto"))
    resolution = str(query.get("resolution", "annual"))
    if requested_source not in {"auto", "sqlite", "compact"} or resolution not in {"annual", "half_hour"}:
        raise ValueError("Unsupported source or resolution")
    year = _integer(query, "year")
    start, end = _integer(query, "period_from"), _integer(query, "period_to")
    limit, offset = _integer(query, "limit", 48), _integer(query, "offset", 0)
    if limit is None or offset is None or (year is not None and year < 1) or not 1 <= limit <= 500 or offset < 0 or (start is not None and start < 0) or (end is not None and end < 0) or (start is not None and end is not None and end < start):
        raise ValueError("Invalid result pagination or period window")
    if resolution == "annual" and (start is not None or end is not None):
        raise ValueError("GF_RESULT_DIMENSION_UNAVAILABLE: annual rows cannot be filtered by period")
    if resolution == "half_hour" and year is None:
        raise ValueError("year is required for half_hour queries")
    output = run_root / "model-output"
    database = output / "market" / "market.sqlite"
    compact = output / "network" / "vre-curtailment-attribution.json"
    kind = requested_source if requested_source != "auto" else ("sqlite" if database.is_file() else "compact")
    path = database if kind == "sqlite" else compact
    status = _read(run_root / "status.json")
    resolved = _read(output / "resolved-run.json")
    evidence_bytes = compact.read_bytes() if kind == "compact" and compact.is_file() else None
    evidence = json.loads(evidence_bytes) if evidence_bytes is not None else {}
    if not isinstance(evidence, Mapping):
        raise ValueError("GF_RESULT_INVALID: compact artifact must be an object")
    for document, key in ((status, "run_policy"), (resolved, "extensions")):
        if document.get(key) is not None and not isinstance(document[key], Mapping):
            raise ValueError("GF_RESULT_INVALID: " + key + " must be an object")
    policy = status.get("run_policy") or {}
    expected_years = tuple(range(policy["start_year"], policy["end_year"] + 1)) if all(isinstance(policy.get(k), int) and not isinstance(policy.get(k), bool) for k in ("start_year", "end_year")) and policy["start_year"] > 0 and 0 <= policy["end_year"] - policy["start_year"] < 200 else ()
    graph = _read(output / "module-resolution.json")
    identity = {"run_id": run_root.name, "requested_run_id": run_root.name, "container_run_id": status.get("id"), "recorded_run_id": evidence.get("run_id"), "study_id": status.get("project_id"), "study_revision": (resolved.get("extensions") or {}).get("project_revision_sha256"), "input_snapshot_id": status.get("input_snapshot_id")}
    for key in ("data_pack_id", "network_pack_id", "initial_state_sha256", "module_resolution_graph_sha256", "module_identities"):
        identity[key] = evidence.get(key)
    result = {"schema_version": "value.result-query/v1", "family": "vre-curtailment", "contract_version": CONTRACT, "identity": identity, "source": {"kind": kind, "requested": requested_source, "artifact_path": path.relative_to(run_root).as_posix(), "artifact_sha256": hashlib.sha256(evidence_bytes).hexdigest() if evidence_bytes is not None else _sha(path) if path.is_file() else None, "original_schema_version": None, "trace_level": None}, "scope": {"resolution": resolution, "year": year, "period_from": start, "period_to": end}, "identity_binding": {"container": "status.json", "source": "artifact_metadata", "source_run_id_recorded": bool(evidence.get("run_id"))}, "capabilities": {"available_resolutions": ["annual", "half_hour"] if kind == "sqlite" and path.is_file() else ["annual"] if path.is_file() else [], "available_dimensions": ["year", "period_window"] if kind == "sqlite" and path.is_file() else ["year"] if path.is_file() else [], "unavailable_dimensions": ["zone", "technology"] + (["period_window"] if kind == "compact" else [])}, "status": "unavailable", "reason_code": "result_artifact_missing", "total": 0, "limit": limit, "offset": offset, "count": 0, "has_more": False, "items": []}
    if kind == "compact" and resolution != "annual":
        raise ValueError("GF_RESULT_DIMENSION_UNAVAILABLE: compact evidence only records annual totals")
    if resolution == "annual":
        # Q14: a run whose profile publishes annual results only after its raw
        # invariants pass serves no annual rows until they do.
        withheld = withheld_annual_result(run_root, "results/vre-curtailment?resolution=annual", status)
        if withheld is not None:
            result.update(status="withheld", reason_code=withheld["reason_code"],
                          result_publication=withheld["result_publication"], available_in=withheld["available_in"])
            return result
    if not path.is_file():
        return result
    observed_stat = (path.stat().st_size, path.stat().st_mtime_ns)
    if kind == "sqlite" and (Path(str(path) + "-wal").exists() or Path(str(path) + "-journal").exists()):
        result.update(status="withheld", reason_code="source_has_active_transaction_files")
        return result
    if status.get("status") not in {"completed", "archived"}:
        result.update(status="withheld", reason_code="immutable_completed_run_required")
        return result
    if kind == "compact":
        result["source"]["original_schema_version"] = evidence.get("schema_version")
        result["source"]["trace_level"] = evidence.get("ledger_trace_level")
        policy = status.get("run_policy") or {}
        expected = expected_years
        validation = validate_vre_curtailment_attribution(evidence, mode=status.get("mode"), periods_per_year=policy.get("periods_per_year"), expected_years=tuple(expected), run_status=status)
        if validation["status"] != "reconciled":
            missing_reasons = {"vre_curtailment_attribution_artifact_missing", "vre_curtailment_annual_evidence_missing", "vre_curtailment_attribution_not_reconciled", "module_does_not_provide_counterfactual_snapshot"}
            normalized_status = "withheld" if validation["status"] == "withheld" else "unavailable" if validation["reason_code"] in missing_reasons or evidence.get("capability_status") == "unavailable" else "invalid"
            result.update(status=normalized_status, reason_code=validation["reason_code"])
            return result
        proof = evidence.get("matched_counterfactual_proof") or {}
        hashes = [proof.get("period_identity_set_sha256"), evidence.get("counterfactual_realised_input_set_sha256")]
        if evidence.get("attribution_method_id") != ATTRIBUTION_METHOD_ID or any(not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in hashes):
            result.update(status="invalid", reason_code="attribution_method_or_proof_invalid")
            return result
        if evidence.get("run_id") is not None and evidence["run_id"] != status.get("id"):
            result.update(status="invalid", reason_code="attribution_run_identity_mismatch")
            return result
        identity["attribution_method_id"] = evidence["attribution_method_id"]
        identity["counterfactual_realised_input_set_sha256"] = hashes[1]
        rows = [_validated({key: row.get(key) for key in ("year", "period_count", *FIELDS)}) for row in evidence["annual_totals"] if year is None or row["year"] == year]
        total = len(rows)
        rows = rows[offset:offset + limit]
    else:
        capabilities = market_ledger_capabilities(database)
        result["source"]["original_schema_version"] = capabilities.get("ledger_schema_version")
        if capabilities.get("ledger_schema_version") not in ATTRIBUTION_SCHEMA_VERSIONS:
            result.update(reason_code="legacy_contract_did_not_measure_avoided_curtailment")
            result["capabilities"]["available_resolutions"] = []
            return result
        with _read_only_connection(database) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"vre_curtailment_period", "zonal_period_accounting"} <= tables:
                result.update(reason_code="attribution_evidence_not_recorded")
                return result
            # G1-07 (P0-9 S7): both tables present but empty (a copperplate or
            # pre-attribution Run) means no evidence was recorded: unavailable,
            # not invalid.  One empty and one filled table still fails below.
            recorded_any = any(
                connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                for table in ("vre_curtailment_period", "zonal_period_accounting")
            )
            if not recorded_any:
                result.update(status="unavailable", reason_code="attribution_evidence_not_recorded")
                return result
            mismatch = connection.execute("SELECT 1 FROM vre_curtailment_period v LEFT JOIN zonal_period_accounting a ON v.year=a.year AND v.period=a.period AND v.period_id=a.period_id WHERE a.period_id IS NULL OR v.counterfactual_realised_input_sha256 IS NULL OR a.counterfactual_realised_input_sha256 IS NULL OR length(v.counterfactual_realised_input_sha256)<>64 OR v.counterfactual_realised_input_sha256 GLOB '*[^0-9a-f]*' OR v.counterfactual_realised_input_sha256<>a.counterfactual_realised_input_sha256 OR a.accounting_status IS NULL OR v.accounting_status IS NULL OR v.attribution_method_id IS NULL OR a.accounting_status<>'reconciled' OR v.accounting_status<>'reconciled' OR v.attribution_method_id<>? LIMIT 1", (ATTRIBUTION_METHOD_ID,)).fetchone()
            missing = connection.execute("SELECT 1 FROM zonal_period_accounting a LEFT JOIN vre_curtailment_period v ON v.year=a.year AND v.period=a.period AND v.period_id=a.period_id WHERE v.period_id IS NULL LIMIT 1").fetchone()
            if mismatch or missing:
                result.update(status="invalid", reason_code="attribution_counterfactual_identity_mismatch")
                return result
            metadata = dict(connection.execute("SELECT key,value FROM metadata")) if "metadata" in tables else {}
            recorded_id = metadata.get("run_id")
            if recorded_id is not None:
                try:
                    recorded_id = json.loads(recorded_id)
                except (ValueError, TypeError):
                    pass
            if recorded_id and status.get("id") and recorded_id != status["id"]:
                result.update(status="invalid", reason_code="attribution_run_identity_mismatch")
                return result
            identity["recorded_run_id"] = recorded_id
            result["identity_binding"]["source_run_id_recorded"] = bool(recorded_id)
            if not recorded_id:
                result.update(status="invalid", reason_code="attribution_source_run_identity_unknown")
                return result
            for table in ("vre_curtailment_period", "zonal_period_accounting"):
                columns = {entry[1] for entry in connection.execute("PRAGMA table_info(" + table + ")")}
                if "run_id" in columns and connection.execute("SELECT 1 FROM " + table + " WHERE run_id IS NULL OR run_id<>? LIMIT 1", (recorded_id,)).fetchone():
                    result.update(status="invalid", reason_code="attribution_run_identity_mismatch")
                    return result
            connection.row_factory = sqlite3.Row
            for stored in connection.execute("SELECT * FROM vre_curtailment_period ORDER BY year, period"):
                try:
                    _validated({key: stored[column] for key, column in PERIOD_FIELDS.items()})
                except ValueError:
                    result.update(status="invalid", reason_code="attribution_period_value_invalid")
                    return result
            result["source"]["trace_level"] = metadata.get("trace_level")
            for key in ("data_pack_id", "network_pack_id", "initial_state_sha256", "module_resolution_graph_sha256", "module_identities"):
                value = metadata.get(key)
                if value is not None:
                    try:
                        value = json.loads(value)
                    except (ValueError, TypeError):
                        pass
                    if identity[key] is not None and identity[key] != value:
                        result.update(status="invalid", reason_code="attribution_source_identity_mismatch")
                        return result
                    identity[key] = value
        identity["attribution_method_id"] = ATTRIBUTION_METHOD_ID
        if resolution == "annual":
            # P0-9 S5: the shared annual-coverage rule (gridform_core.result_coverage).
            if is_non_annual(status):
                result.update(status="withheld", reason_code=REASON_NON_ANNUAL)
                return result
            brief_years = query_zonal_annual_brief(database)["years"]
            if not expected_years or {item["year"] for item in brief_years} != set(expected_years):
                # Designer ruling 3 (M2 UI review): a Run that was cancelled (or
                # failed) before a declared year completed is not self-contradictory;
                # a missing year is then unavailable, never a red "invalid".
                stopped = stopped_reason(status)
                if stopped is not None and expected_years and {item["year"] for item in brief_years} <= set(expected_years):
                    result.update(status="unavailable", reason_code="cancelled_before_year_complete" if stopped == REASON_CANCELLED else "failed_before_year_complete")
                    return result
                result.update(status="invalid", reason_code="vre_curtailment_annual_year_set_invalid")
                return result
            with _read_only_connection(database) as connection:
                bounds = connection.execute("SELECT year,MIN(period),MAX(period),COUNT(DISTINCT period) FROM vre_curtailment_period GROUP BY year").fetchall()
            coverage = result_coverage(status, year_bounds_from_rows(bounds))
            result["coverage"] = coverage
            if coverage["annual_status"] != "complete":
                # Review response: the precise coverage code, with the older wording kept beside it.
                result.update(status="invalid" if coverage["annual_status"] == "invalid" else "withheld", reason_code=coverage["reason_code"], legacy_reason_code=legacy_reason(coverage))
                return result
            rows = []
            for item in brief_years:
                row = item["vre_curtailment"]
                if row.get("attribution_status") != "reconciled":
                    result.update(status="invalid", reason_code=row.get("reason_code"))
                    return result
                if row.get("period_count") != 17520:
                    result.update(status="withheld", reason_code="annual_evidence_withheld_for_nonannual_run")
                    return result
                if year is not None and item["year"] != year:
                    continue
                normalized = {key: row.get(key) for key in ("period_count", *FIELDS)}
                normalized["year"] = item["year"]
                normalized["identity_residual_mwh"] = row["economic_mwh"] + row["forecast_added_mwh"] - row["forecast_avoided_mwh"] + row["redispatch_added_mwh"] - row["redispatch_avoided_mwh"] - row["total_mwh"]
                rows.append(_validated(normalized))
            total = len(rows)
            rows = rows[offset:offset + limit]
        else:
            filters = {"view": "curtailment", "year": year, "limit": limit, "offset": offset}
            if start is not None:
                filters["period_from"] = start
            if end is not None:
                filters["period_to"] = end
            page = query_zonal_results(database, filters)
            total = page["total"]
            rows = [_validated({"year": row["year"], "period": row["period"], "period_id": row["period_id"], "period_count": 1, "realised_input_sha256": row["counterfactual_realised_input_sha256"], **{key: row.get(column) for key, column in PERIOD_FIELDS.items()}}) for row in page["items"]]
    if observed_stat != (path.stat().st_size, path.stat().st_mtime_ns) or result["source"]["artifact_sha256"] != _sha(path):
        result.update(status="invalid", reason_code="source_changed_during_query")
        return result
    for key, recorded in (("data_pack_id", resolved.get("data_pack_id")), ("module_resolution_graph_sha256", graph.get("graph_sha256"))):
        if identity.get(key) is not None and recorded is not None and identity[key] != recorded:
            result.update(status="invalid", reason_code="attribution_frozen_input_identity_mismatch")
            return result
    identity["missing_fields"] = [key for key in ("recorded_run_id", "study_id", "study_revision", "input_snapshot_id", "data_pack_id", "network_pack_id", "initial_state_sha256", "module_resolution_graph_sha256", "module_identities") if identity.get(key) is None]
    result.update(status="reconciled" if total else "unavailable", reason_code=None if total else "scope_not_recorded", total=total, count=len(rows), items=rows, has_more=offset + len(rows) < total)
    return result
