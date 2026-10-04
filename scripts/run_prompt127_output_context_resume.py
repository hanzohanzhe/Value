"""Resume the bounded Prompt 125 gates from fresh Prompt 127 evidence roots."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "publication" / "prompt127-output-context-test-report.json"
DEFAULT_MARKDOWN = ROOT / "publication" / "prompt127-output-context-test-report.md"
EVIDENCE_ROOT = ROOT / "publication" / "prompt127-output-context-evidence"
PROMPT125_RUNNER = ROOT / "scripts" / "run_prompt125_output_context_gate.py"
GATE_ORDER = (
    "zonal-48",
    "zonal-336",
    "two-year-coupling",
    "trace-equivalence",
    "failure-and-preflight",
)
GATE_EVIDENCE = {
    "zonal-48": ("contracts", "ledger_v8", "zonal_48_period"),
    "zonal-336": ("zonal_336_period",),
    "two-year-coupling": ("two_year_state_coupling",),
    "trace-equivalence": ("trace_science_equivalence",),
    "failure-and-preflight": (
        "failure_bundle",
        "preflight_estimate",
        "frontend_bounded_access",
    ),
}
ENERGY_BALANCE_TOLERANCE_MWH = 1e-5
LITERAL_48_EXPECTED = {
    "periods": 48,
    "demand_mwh": 48.0,
    "accepted_supply_mwh": 48.0,
    "physical_resource_cost_gbp": 480.0,
    "market_payment_gbp": 480.0,
    "blackout_mwh": 0.0,
    "curtailment_mwh": 0.0,
    "storage_charge_mwh": 0.0,
    "storage_discharge_mwh": 0.0,
    "maximum_absolute_energy_balance_residual_mwh": 0.0,
}

for _thread_variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_prompt125():
    spec = importlib.util.spec_from_file_location("prompt125_output_context_gate_for_prompt127", PROMPT125_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Prompt 125 gate runner: {PROMPT125_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROMPT125 = _load_prompt125()
PROMPT125_REQUIRED_GATES = tuple(PROMPT125.REQUIRED_GATES)
SCIENTIFIC_TRACE_TABLES = (
    "period_summary",
    "dispatch_summary",
    "storage_summary",
    "redispatch_summary",
    "zonal_period_accounting",
    "vre_curtailment_period",
    "zonal_demand_alignment",
    "zone_period_summary",
    "boundary_period_summary",
)
SOLVER_LINK_TABLE = "solver_declaration_link"
SOLVER_LINK_PROVENANCE_FIELD = "declared_input_sha256"


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _read_table_projection(database: Path, table: str) -> dict[str, Any]:
    with sqlite3.connect(database.resolve()) as connection:
        columns = connection.execute(
            f"PRAGMA table_info({_quoted_identifier(table)})"
        ).fetchall()
        if not columns:
            raise RuntimeError(f"Required trace table is missing: {table}")
        column_names = [str(row[1]) for row in columns]
        selected_columns = ", ".join(_quoted_identifier(name) for name in column_names)
        runtime_types = ", ".join(
            f"typeof({_quoted_identifier(name)})" for name in column_names
        )
        rows = connection.execute(
            f"SELECT {selected_columns} FROM {_quoted_identifier(table)} ORDER BY rowid"
        ).fetchall()
        types = connection.execute(
            f"SELECT {runtime_types} FROM {_quoted_identifier(table)} ORDER BY rowid"
        ).fetchall()
    return {
        "columns": [
            {
                "name": str(row[1]),
                "declared_type": str(row[2]),
                "not_null": bool(row[3]),
                "default": row[4],
                "primary_key_position": int(row[5]),
            }
            for row in columns
        ],
        "rows": [list(row) for row in rows],
        "runtime_types": [list(row) for row in types],
    }


def _maximum_numeric_difference(
    summary_rows: list[list[Any]], full_rows: list[list[Any]]
) -> float:
    maximum = 0.0
    for summary_row, full_row in zip(summary_rows, full_rows):
        for summary_value, full_value in zip(summary_row, full_row):
            if (
                isinstance(summary_value, (int, float))
                and not isinstance(summary_value, bool)
                and isinstance(full_value, (int, float))
                and not isinstance(full_value, bool)
            ):
                maximum = max(maximum, abs(float(summary_value) - float(full_value)))
    return maximum


def _compare_exact_table(
    summary_database: Path, full_database: Path, table: str
) -> tuple[dict[str, Any], float]:
    summary = _read_table_projection(summary_database, table)
    full = _read_table_projection(full_database, table)
    columns_equivalent = summary["columns"] == full["columns"]
    runtime_types_equivalent = summary["runtime_types"] == full["runtime_types"]
    rows_equivalent = summary["rows"] == full["rows"]
    comparison = {
        "equivalent": bool(
            columns_equivalent and runtime_types_equivalent and rows_equivalent
        ),
        "columns_equivalent": columns_equivalent,
        "runtime_types_equivalent": runtime_types_equivalent,
        "rows_equivalent": rows_equivalent,
        "summary_row_count": len(summary["rows"]),
        "full_row_count": len(full["rows"]),
        "summary_columns": summary["columns"],
        "full_columns": full["columns"],
    }
    return comparison, _maximum_numeric_difference(summary["rows"], full["rows"])


def _compare_solver_link(
    summary_database: Path, full_database: Path
) -> tuple[dict[str, Any], list[str], bool]:
    summary = _read_table_projection(summary_database, SOLVER_LINK_TABLE)
    full = _read_table_projection(full_database, SOLVER_LINK_TABLE)
    summary_names = [row["name"] for row in summary["columns"]]
    full_names = [row["name"] for row in full["columns"]]
    mismatched_fields: set[str] = set()
    declared_input_differs = False

    if summary["columns"] != full["columns"]:
        mismatched_fields.add("__schema__")
    if len(summary["rows"]) != len(full["rows"]):
        mismatched_fields.add("__row_count__")
    if summary_names != full_names or SOLVER_LINK_PROVENANCE_FIELD not in summary_names:
        mismatched_fields.add("__schema__")
    else:
        provenance_index = summary_names.index(SOLVER_LINK_PROVENANCE_FIELD)
        for row_index, (summary_row, full_row) in enumerate(
            zip(summary["rows"], full["rows"])
        ):
            summary_types = summary["runtime_types"][row_index]
            full_types = full["runtime_types"][row_index]
            for column_index, name in enumerate(summary_names):
                if summary_types[column_index] != full_types[column_index]:
                    mismatched_fields.add(name)
                if name == SOLVER_LINK_PROVENANCE_FIELD:
                    declared_input_differs = bool(
                        declared_input_differs
                        or summary_row[column_index] != full_row[column_index]
                    )
                elif summary_row[column_index] != full_row[column_index]:
                    mismatched_fields.add(name)
        if provenance_index >= len(summary_names):
            mismatched_fields.add("__schema__")

    comparison = {
        "equivalent_except_declared_input_sha256": not mismatched_fields,
        "declared_input_sha256_differs": declared_input_differs,
        "mismatched_fields": sorted(mismatched_fields),
        "summary_row_count": len(summary["rows"]),
        "full_row_count": len(full["rows"]),
        "summary_columns": summary["columns"],
        "full_columns": full["columns"],
    }
    return comparison, sorted(mismatched_fields), declared_input_differs


def _compare_trace_ledgers(
    summary_database: Path,
    full_database: Path,
    *,
    summary_validation: Mapping[str, Any],
    full_validation: Mapping[str, Any],
    summary_context: Mapping[str, Any],
    full_context: Mapping[str, Any],
    summary_science_root: str,
    full_science_root: str,
    summary_evidence_root: str,
    full_evidence_root: str,
) -> dict[str, Any]:
    issues: list[str] = []
    table_comparisons: dict[str, dict[str, Any]] = {}
    maximum_numeric_difference = 0.0
    for table in SCIENTIFIC_TRACE_TABLES:
        comparison, table_maximum = _compare_exact_table(
            summary_database, full_database, table
        )
        table_comparisons[table] = comparison
        maximum_numeric_difference = max(maximum_numeric_difference, table_maximum)
        if not comparison["equivalent"]:
            issues.append(f"scientific_table_mismatch:{table}")

    solver_link, solver_mismatches, declared_input_differs = _compare_solver_link(
        summary_database, full_database
    )
    issues.extend(
        f"solver_declaration_link_mismatch:{field}" for field in solver_mismatches
    )

    summary_validator_valid = summary_validation.get("valid") is True
    full_validator_valid = full_validation.get("valid") is True
    if not summary_validator_valid:
        issues.append("summary_ledger_validator_failed")
    if not full_validator_valid:
        issues.append("full_ledger_validator_failed")

    summary_run_id = summary_context.get("run_id")
    full_run_id = full_context.get("run_id")
    summary_trace_profile = summary_context.get("trace_profile")
    full_trace_profile = full_context.get("trace_profile")
    run_ids_distinct = bool(
        isinstance(summary_run_id, str)
        and summary_run_id
        and isinstance(full_run_id, str)
        and full_run_id
        and summary_run_id != full_run_id
    )
    trace_profiles_distinct = bool(
        summary_trace_profile == "summary" and full_trace_profile == "full"
    )
    summary_controls = summary_context.get("runtime_controls")
    full_controls = full_context.get("runtime_controls")
    runtime_controls_distinct = bool(
        isinstance(summary_controls, Mapping)
        and isinstance(full_controls, Mapping)
        and summary_controls != full_controls
        and summary_controls.get("runtime.market_trace_level") == "summary"
        and full_controls.get("runtime.market_trace_level") == "full"
    )
    if not run_ids_distinct:
        issues.append("summary_full_run_ids_not_distinct")
    if not trace_profiles_distinct:
        issues.append("summary_full_trace_profiles_not_summary_full")
    if not runtime_controls_distinct:
        issues.append("summary_full_runtime_controls_not_trace_specific")
    if declared_input_differs and not (
        run_ids_distinct and trace_profiles_distinct and runtime_controls_distinct
    ):
        issues.append("declared_input_difference_without_distinct_run_context")

    roots = {
        "summary_science_root": summary_science_root,
        "full_science_root": full_science_root,
        "summary_evidence_root": summary_evidence_root,
        "full_evidence_root": full_evidence_root,
    }
    for name, value in roots.items():
        if not PROMPT125._is_sha256(value):
            issues.append(f"missing_or_invalid_{name}")

    provenance_root_differences = []
    if summary_science_root != full_science_root:
        provenance_root_differences.append("science_root")
    if summary_evidence_root != full_evidence_root:
        provenance_root_differences.append("evidence_root")
    return {
        "passed": not issues,
        "issues": issues,
        "comparison_semantics": "exact_row_and_sqlite_type_equality",
        "maximum_absolute_numeric_difference": maximum_numeric_difference,
        "table_comparisons": table_comparisons,
        "scientific_tables_equivalent": all(
            row["equivalent"] for row in table_comparisons.values()
        ),
        "solver_declaration_link": solver_link,
        "solver_link_equivalent": not solver_mismatches,
        "summary_validator_valid": summary_validator_valid,
        "full_validator_valid": full_validator_valid,
        "summary_validator_errors": list(summary_validation.get("errors") or []),
        "full_validator_errors": list(full_validation.get("errors") or []),
        "summary_run_id": summary_run_id,
        "full_run_id": full_run_id,
        "summary_trace_profile": summary_trace_profile,
        "full_trace_profile": full_trace_profile,
        "summary_runtime_controls": copy.deepcopy(summary_controls),
        "full_runtime_controls": copy.deepcopy(full_controls),
        "run_ids_distinct": run_ids_distinct,
        "trace_profiles_distinct": trace_profiles_distinct,
        "runtime_controls_distinct": runtime_controls_distinct,
        "root_semantics": "context_bound",
        **roots,
        "provenance_only_differences": {
            "solver_declaration_link": (
                [SOLVER_LINK_PROVENANCE_FIELD] if declared_input_differs else []
            ),
            "context_bound_roots": provenance_root_differences,
        },
    }


def _prompt127_trace_gate_issues(evidence: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if evidence.get("passed") is not True:
        issues.append("gate_did_not_declare_passed")
    for issue in evidence.get("issues") or []:
        if str(issue) not in issues:
            issues.append(str(issue))
    if evidence.get("root_semantics") != "context_bound":
        issues.append("trace_roots_not_labelled_context_bound")
    if evidence.get("maximum_absolute_numeric_difference") != 0.0:
        issues.append("trace_numeric_difference_is_not_zero")
    if evidence.get("scientific_tables_equivalent") is not True:
        issues.append("trace_scientific_tables_not_equivalent")
    if evidence.get("solver_link_equivalent") is not True:
        issues.append("trace_solver_link_not_equivalent")
    if evidence.get("summary_validator_valid") is not True:
        issues.append("summary_ledger_validator_failed")
    if evidence.get("full_validator_valid") is not True:
        issues.append("full_ledger_validator_failed")
    if evidence.get("summary_run_passed") is not True:
        issues.append("summary_run_failed")
    if evidence.get("full_run_passed") is not True:
        issues.append("full_run_failed")
    if evidence.get("summary_results") != evidence.get("full_results"):
        issues.append("common_results_differ")
    for field in (
        "summary_science_root",
        "full_science_root",
        "summary_evidence_root",
        "full_evidence_root",
    ):
        if not PROMPT125._is_sha256(evidence.get(field)):
            issues.append(f"missing_or_invalid_{field}")
    return list(dict.fromkeys(issues))


def _audit_prompt127_evidence(
    evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    report = PROMPT125.audit_evidence(evidence)
    supplied = evidence.get("trace_science_equivalence", {})
    trace = copy.deepcopy(dict(supplied)) if isinstance(supplied, Mapping) else {}
    trace_issues = _prompt127_trace_gate_issues(trace)
    trace["passed"] = not trace_issues
    trace["issues"] = trace_issues
    report["gates"]["trace_science_equivalence"] = trace
    first_blocker = None
    for name in PROMPT125_REQUIRED_GATES:
        row = report["gates"][name]
        if row.get("issues"):
            first_blocker = {"gate": name, "issues": list(row["issues"])}
            if name == "ledger_v8":
                first_blocker["validator_errors_count"] = row.get(
                    "validator_errors_count"
                )
                first_blocker["validator_errors_by_kind"] = copy.deepcopy(
                    row.get("validator_errors_by_kind") or {}
                )
            break
    report["first_blocker"] = first_blocker
    report["ten_year_restart_authorised"] = first_blocker is None
    return report


def _gate_trace(_current: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    summary = PROMPT125._run_zonal(48, "summary", "trace-summary")
    full = PROMPT125._run_zonal(48, "full", "trace-full")
    summary_root = str((summary.get("science_root_by_year") or {}).get("2025") or "")
    full_root = str((full.get("science_root_by_year") or {}).get("2025") or "")
    summary_output_root = Path(str(summary["output_root"]))
    full_output_root = Path(str(full["output_root"]))
    summary_context = json.loads(
        (summary_output_root / "market" / "context" / "run-context.json").read_text(
            encoding="utf-8"
        )
    )
    full_context = json.loads(
        (full_output_root / "market" / "context" / "run-context.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = _compare_trace_ledgers(
        summary_output_root / "market" / "market.sqlite",
        full_output_root / "market" / "market.sqlite",
        summary_validation=dict(summary.get("ledger_validation") or {}),
        full_validation=dict(full.get("ledger_validation") or {}),
        summary_context=summary_context,
        full_context=full_context,
        summary_science_root=summary_root,
        full_science_root=full_root,
        summary_evidence_root=str(
            (summary.get("evidence_root_by_year") or {}).get("2025") or ""
        ),
        full_evidence_root=str(
            (full.get("evidence_root_by_year") or {}).get("2025") or ""
        ),
    )
    evidence.update({
        "summary_run_passed": summary.get("passed") is True,
        "full_run_passed": full.get("passed") is True,
        "summary_results": summary["science_results"],
        "full_results": full["science_results"],
        "summary_output_bytes": summary["actual_output_bytes"],
        "full_output_bytes": full["actual_output_bytes"],
        "summary_output_root": summary["output_root"],
        "full_output_root": full["output_root"],
        "elapsed_seconds": float(summary["elapsed_seconds"])
        + float(full["elapsed_seconds"]),
    })
    return {"trace_science_equivalence": evidence}


PROMPT127_GATE_RUNNERS = dict(PROMPT125.GATE_RUNNERS)
PROMPT127_GATE_RUNNERS["trace-equivalence"] = _gate_trace


def _read_literal_48_regression(database: Path) -> dict[str, Any]:
    resolved = database.resolve()
    with sqlite3.connect(resolved) as connection:
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(real_demand_mwh), 0), "
            "COALESCE(SUM(accepted_supply_mwh), 0), "
            "COALESCE(SUM(physical_resource_cost_gbp), 0), "
            "COALESCE(SUM(market_payment_gbp), 0), "
            "COALESCE(SUM(blackout_mwh), 0), COALESCE(SUM(curtailed_mwh), 0), "
            "COALESCE(SUM(storage_charge_mwh), 0), "
            "COALESCE(SUM(storage_discharge_mwh), 0), "
            "COALESCE(MAX(ABS(energy_balance_residual_mwh)), 0) "
            "FROM period_summary"
        ).fetchone()
    if row is None:
        raise RuntimeError(f"No literal regression row returned from {resolved}")
    observed = {
        "periods": int(row[0]),
        "demand_mwh": float(row[1]),
        "accepted_supply_mwh": float(row[2]),
        "physical_resource_cost_gbp": float(row[3]),
        "market_payment_gbp": float(row[4]),
        "blackout_mwh": float(row[5]),
        "curtailment_mwh": float(row[6]),
        "storage_charge_mwh": float(row[7]),
        "storage_discharge_mwh": float(row[8]),
        "maximum_absolute_energy_balance_residual_mwh": float(row[9]),
    }
    mismatches = [
        name
        for name, expected in LITERAL_48_EXPECTED.items()
        if name != "maximum_absolute_energy_balance_residual_mwh"
        and observed[name] != expected
    ]
    if observed["maximum_absolute_energy_balance_residual_mwh"] > ENERGY_BALANCE_TOLERANCE_MWH:
        mismatches.append("maximum_absolute_energy_balance_residual_mwh")
    return {
        "passed": not mismatches,
        "database_path": str(resolved),
        "expected": copy.deepcopy(LITERAL_48_EXPECTED),
        "observed": observed,
        "energy_balance_tolerance_mwh": ENERGY_BALANCE_TOLERANCE_MWH,
        "mismatches": mismatches,
    }


def _execute_ordered(
    gate_runners: Mapping[str, Callable[[Mapping[str, Any]], dict[str, dict[str, Any]]]],
    *,
    on_gate_complete: Callable[[str, dict[str, Any], dict[str, dict[str, Any]], float], bool],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    completed: list[str] = []
    execution_rows: list[dict[str, Any]] = []
    passed = True
    for index, name in enumerate(GATE_ORDER):
        started = time.perf_counter()
        error: str | None = None
        try:
            produced = gate_runners[name](evidence)
            evidence.update(produced)
        except Exception as exception:
            error = f"{type(exception).__module__}.{type(exception).__qualname__}: {exception}"
            produced = {"__execution_error__": {"passed": False, "execution_error": error}}
        elapsed = time.perf_counter() - started
        passed = bool(on_gate_complete(name, evidence, produced, elapsed)) and error is None
        completed.append(name)
        execution_rows.append({
            "gate": name,
            "command": f"scripts/run_prompt127_output_context_resume.py::{name}",
            "elapsed_seconds": elapsed,
            "passed": passed,
            "error": error,
        })
        if not passed:
            return {
                "passed": False,
                "evidence": evidence,
                "completed": completed,
                "not_run": list(GATE_ORDER[index + 1:]),
                "executions": execution_rows,
            }
    return {
        "passed": passed,
        "evidence": evidence,
        "completed": completed,
        "not_run": [],
        "executions": execution_rows,
    }


def _prompt127_decision(
    prompt125_report: Mapping[str, Any],
    literal_regression: Mapping[str, Any],
    evidence_path_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    gates = dict(prompt125_report.get("gates") or {})
    nine_passed = bool(
        set(gates) == set(PROMPT125_REQUIRED_GATES)
        and all(dict(gates.get(name) or {}).get("passed") is True for name in PROMPT125_REQUIRED_GATES)
    )
    paths_passed = evidence_path_audit is None or evidence_path_audit.get("passed") is True
    first_blocker = copy.deepcopy(prompt125_report.get("first_blocker"))
    if literal_regression.get("passed") is not True:
        first_blocker = {
            "gate": "zonal_48_literal_physical_regression",
            "issues": list(literal_regression.get("mismatches") or ["literal_regression_not_passed"]),
        }
    elif nine_passed and not paths_passed:
        first_blocker = {
            "gate": "prompt127_evidence_path_isolation",
            "issues": list((evidence_path_audit or {}).get("outside_root") or ["path_audit_not_passed"]),
        }
    authorised = bool(nine_passed and literal_regression.get("passed") is True and paths_passed)
    return {
        "ten_year_restart_authorised": authorised,
        "ten_year_restart_semantics": (
            "Authorises only a later fresh matched ten-year restart. Prompt 127 ran "
            "bounded fixtures only and did not start an annual or ten-year production study."
        ),
        "first_blocker": None if authorised else first_blocker,
        "bounded_scope": {
            "bounded_gate_only": True,
            "annual_run_started": False,
            "two_full_year_production_run_started": False,
            "ten_year_run_started": False,
            "note": (
                "The two-year state-coupling check is a bounded contract fixture, not "
                "a two-full-year production study."
            ),
        },
    }


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _evidence_path_audit(evidence: Mapping[str, Any], literal: Mapping[str, Any]) -> dict[str, Any]:
    paths: list[str] = []

    def visit(value: object, key: str = "") -> None:
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key))
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, key)
        elif isinstance(value, str) and key in {
            "output_root", "summary_output_root", "full_output_root", "path", "database_path"
        }:
            paths.append(str(Path(value).resolve()))

    visit(evidence)
    visit(literal)
    outside = [path for path in paths if not _path_is_within(Path(path), EVIDENCE_ROOT)]
    return {
        "passed": bool(paths) and not outside,
        "evidence_root": str(EVIDENCE_ROOT.resolve()),
        "paths": sorted(set(paths)),
        "outside_root": sorted(set(outside)),
    }


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Prompt 127 bounded output/context verification resume",
        "",
        f"Decision: **{'AUTHORISED FOR A LATER FRESH RESTART' if report.get('ten_year_restart_authorised') else 'NOT AUTHORISED'}**. "
        f"`ten_year_restart_authorised={str(bool(report.get('ten_year_restart_authorised'))).lower()}`.",
        "",
        "This was a bounded gate only. No annual, two-full-year production, or ten-year production study was run.",
        "The two-year state-coupling gate used a bounded contract fixture; it was not a two-full-year production study.",
        "",
        "| Gate | Result | Elapsed / key evidence |",
        "| --- | --- | --- |",
    ]
    not_run_evidence: set[str] = set()
    for runner_gate in report.get("not_run") or []:
        not_run_evidence.update(GATE_EVIDENCE.get(str(runner_gate), ()))
    for name in PROMPT125_REQUIRED_GATES:
        gate = dict((report.get("gates") or {}).get(name) or {})
        selected = {
            key: gate[key]
            for key in (
                "period_count", "actual_output_bytes", "accepted_estimate_bytes",
                "database_bytes", "database_sha256", "output_root", "elapsed_seconds",
                "output_bytes", "fixed_context_bytes", "incremental_output_bytes",
                "run_context_sha256", "year_context_sha256", "context_registry",
                "science_root_by_year", "evidence_root_by_year",
                "summary_science_root", "full_science_root",
                "summary_evidence_root", "full_evidence_root",
                "summary_output_root", "full_output_root",
                "summary_output_bytes", "full_output_bytes",
                "summary_results", "full_results", "profiles",
                "comparison_semantics", "maximum_absolute_numeric_difference",
                "scientific_tables_equivalent", "solver_link_equivalent",
                "summary_validator_valid", "full_validator_valid",
                "summary_run_passed", "full_run_passed",
                "summary_run_id", "full_run_id", "summary_trace_profile",
                "full_trace_profile", "summary_runtime_controls",
                "full_runtime_controls", "root_semantics",
                "provenance_only_differences",
                "validator_valid", "validator_errors_count", "issues",
            )
            if key in gate
        }
        result_label = (
            "NOT RUN" if name in not_run_evidence
            else ("PASS" if gate.get("passed") else "FAIL")
        )
        lines.append(
            f"| `{name}` | {result_label} | "
            f"`{json.dumps(selected, sort_keys=True)}` |"
        )
    literal = dict(report.get("literal_48_period_physical_regression") or {})
    lines.append(
        f"| `zonal_48_literal_physical_regression` | {'PASS' if literal.get('passed') else 'FAIL'} | "
        f"`{json.dumps(literal, sort_keys=True)}` |"
    )
    path_audit = dict(report.get("evidence_path_audit") or {})
    lines.append(
        f"| `prompt127_evidence_path_isolation` | {'PASS' if path_audit.get('passed') else 'FAIL'} | "
        f"`{json.dumps(path_audit, sort_keys=True)}` |"
    )
    lines.extend(["", "## First blocker", ""])
    lines.append(
        "None."
        if report.get("first_blocker") is None
        else f"`{json.dumps(report['first_blocker'], sort_keys=True)}`"
    )
    lines.extend(["", "## Ordered bounded executions", ""])
    for row in report.get("executions") or []:
        lines.append(
            f"- `{row.get('gate')}` — {float(row.get('elapsed_seconds') or 0):.3f}s — "
            f"{'PASS' if row.get('passed') else 'FAIL'}"
        )
    if report.get("not_run"):
        lines.extend(["", "## Not run after first blocker", ""])
        for name in report["not_run"]:
            lines.append(f"- `{name}`")
    return "\n".join(lines) + "\n"


def _persist_prompt127(
    evidence: Mapping[str, Mapping[str, Any]],
    literal: Mapping[str, Any],
    executions: list[dict[str, Any]],
    not_run: list[str],
    json_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    refreshed = PROMPT125._refresh_retained_zonal_48_evidence(evidence)
    report = _audit_prompt127_evidence(refreshed)
    path_audit = _evidence_path_audit(refreshed, literal)
    report.update(_prompt127_decision(report, literal, path_audit))
    report.update({
        "schema_version": "value.prompt127-output-context-report/v1",
        "prompt125_gate_schema_reused": True,
        "required_prompt125_gates": list(PROMPT125_REQUIRED_GATES),
        "raw_evidence": refreshed,
        "literal_48_period_physical_regression": copy.deepcopy(dict(literal)),
        "evidence_path_audit": path_audit,
        "executions": copy.deepcopy(executions),
        "not_run": list(not_run),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    PROMPT125._write_json(json_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return report


def run_bounded(json_path: Path, markdown_path: Path) -> tuple[int, dict[str, Any]]:
    PROMPT125.EVIDENCE_ROOT = EVIDENCE_ROOT
    executions: list[dict[str, Any]] = []
    literal: dict[str, Any] = {
        "passed": False,
        "expected": copy.deepcopy(LITERAL_48_EXPECTED),
        "mismatches": ["zonal_48_not_run"],
    }
    latest_report: dict[str, Any] = {}

    def checkpoint(
        name: str,
        evidence: dict[str, Any],
        produced: dict[str, dict[str, Any]],
        elapsed: float,
    ) -> bool:
        nonlocal literal, latest_report
        execution_error = dict(produced.get("__execution_error__") or {}).get("execution_error")
        if execution_error:
            for gate_name in GATE_EVIDENCE[name]:
                evidence.setdefault(gate_name, {"passed": False, "execution_error": execution_error})
        if name == "zonal-48" and not execution_error:
            output_root = Path(str(dict(evidence.get("zonal_48_period") or {})["output_root"]))
            database = output_root / "market" / "market.sqlite"
            try:
                literal = _read_literal_48_regression(database)
            except Exception as exception:
                literal = {
                    "passed": False,
                    "database_path": str(database.resolve()),
                    "expected": copy.deepcopy(LITERAL_48_EXPECTED),
                    "mismatches": ["literal_regression_query_failed"],
                    "execution_error": f"{type(exception).__module__}.{type(exception).__qualname__}: {exception}",
                }
        audited = _audit_prompt127_evidence(evidence)
        owned_passed = all(
            dict(audited["gates"].get(gate_name) or {}).get("passed") is True
            for gate_name in GATE_EVIDENCE[name]
        )
        passed = bool(
            not execution_error
            and owned_passed
            and (name != "zonal-48" or literal.get("passed") is True)
        )
        current_execution = {
            "gate": name,
            "command": f"scripts/run_prompt127_output_context_resume.py::{name}",
            "elapsed_seconds": elapsed,
            "passed": passed,
            "error": execution_error,
        }
        executions.append(current_execution)
        index = GATE_ORDER.index(name)
        latest_report = _persist_prompt127(
            evidence,
            literal,
            executions,
            [] if passed else list(GATE_ORDER[index + 1:]),
            json_path,
            markdown_path,
        )
        print(json.dumps({
            "gate": name,
            "passed": passed,
            "elapsed_seconds": elapsed,
            "first_blocker": latest_report.get("first_blocker"),
        }, sort_keys=True), flush=True)
        return passed

    outcome = _execute_ordered(PROMPT127_GATE_RUNNERS, on_gate_complete=checkpoint)
    if outcome["not_run"] != latest_report.get("not_run"):
        latest_report = _persist_prompt127(
            outcome["evidence"], literal, executions, outcome["not_run"],
            json_path, markdown_path,
        )
    return (0 if latest_report.get("ten_year_restart_authorised") is True else 1), latest_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args(argv)
    retained_paths = {PROMPT125.DEFAULT_JSON.resolve(), PROMPT125.DEFAULT_MARKDOWN.resolve()}
    if args.json.resolve() in retained_paths or args.markdown.resolve() in retained_paths:
        parser.error("Prompt 127 refuses to overwrite retained Prompt 125 reports")
    status, report = run_bounded(args.json, args.markdown)
    print(json.dumps({
        "ten_year_restart_authorised": report.get("ten_year_restart_authorised") is True,
        "first_blocker": report.get("first_blocker"),
        "json": str(args.json.resolve()),
        "markdown": str(args.markdown.resolve()),
    }, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
