from __future__ import annotations

import importlib.util
import json
import copy
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_prompt127_output_context_resume.py"
SCIENTIFIC_TABLES = (
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


def load_runner():
    if not RUNNER.is_file():
        raise AssertionError("Prompt 127 output/context resume runner has not been implemented")
    spec = importlib.util.spec_from_file_location("prompt127_output_context_resume", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_trace_fixture(
    root: Path,
    *,
    run_id: str,
    trace_profile: str,
    declared_input_sha256: str,
    scientific_value: float = 1.0,
    solver_status: str = "optimal",
    declaration_artifact_id: str = "market/market.sqlite#declared-input",
) -> tuple[Path, dict[str, object]]:
    market = root / "market"
    context = market / "context"
    context.mkdir(parents=True)
    database = market / "market.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        for table in SCIENTIFIC_TABLES:
            connection.execute(
                f"CREATE TABLE {table}("
                "year INTEGER, period INTEGER, value REAL, status TEXT)"
            )
            connection.execute(
                f"INSERT INTO {table} VALUES(?,?,?,?)",
                (
                    2025,
                    0,
                    scientific_value if table == "period_summary" else 1.0,
                    "reconciled",
                ),
            )
        connection.execute(
            "CREATE TABLE solver_declaration_link("
            "year INTEGER, period INTEGER, declared_input_sha256 TEXT, "
            "declaration_artifact_id TEXT, solver_artifact_id TEXT, "
            "failure_artifact_id TEXT, solver_status TEXT)"
        )
        connection.execute(
            "INSERT INTO solver_declaration_link VALUES(?,?,?,?,?,?,?)",
            (
                2025,
                0,
                declared_input_sha256,
                declaration_artifact_id,
                None,
                None,
                solver_status,
            ),
        )
        connection.commit()
    run_context: dict[str, object] = {
        "schema_version": "value.run-static-context/v1",
        "run_id": run_id,
        "trace_profile": trace_profile,
        "runtime_controls": {"runtime.market_trace_level": trace_profile},
        "scientific_parameters": {"clock.period_hours": 1.0},
    }
    (context / "run-context.json").write_text(
        json.dumps(run_context, sort_keys=True), encoding="utf-8"
    )
    return database, run_context


def _compare_fixture_pair(
    runner,
    root: Path,
    *,
    full_scientific_value: float = 1.0,
    full_solver_status: str = "optimal",
    full_declaration_artifact_id: str = "market/market.sqlite#declared-input",
    full_validator_valid: bool = True,
    summary_run_passed: bool = True,
    full_run_passed: bool = True,
    full_results: dict[str, str] | None = None,
):
    summary_database, summary_context = _write_trace_fixture(
        root / "summary",
        run_id="summary-run",
        trace_profile="summary",
        declared_input_sha256="a" * 64,
    )
    full_database, full_context = _write_trace_fixture(
        root / "full",
        run_id="full-run",
        trace_profile="full",
        declared_input_sha256="b" * 64,
        scientific_value=full_scientific_value,
        solver_status=full_solver_status,
        declaration_artifact_id=full_declaration_artifact_id,
    )
    result = runner._compare_trace_ledgers(
        summary_database,
        full_database,
        summary_validation={"valid": True, "errors": []},
        full_validation={"valid": full_validator_valid, "errors": []},
        summary_context=summary_context,
        full_context=full_context,
        summary_science_root="1" * 64,
        full_science_root="2" * 64,
        summary_evidence_root="3" * 64,
        full_evidence_root="4" * 64,
    )
    result.update({
        "summary_run_passed": summary_run_passed,
        "full_run_passed": full_run_passed,
        "summary_results": {"dispatch_sha256": "5" * 64},
        "full_results": full_results or {"dispatch_sha256": "5" * 64},
    })
    return result


class Prompt127OutputContextResumeTests(unittest.TestCase):
    def test_exact_science_passes_with_only_context_bound_provenance_differences(self) -> None:
        runner = load_runner()
        self.assertTrue(
            hasattr(runner, "_compare_trace_ledgers"),
            "Prompt 127 needs a context-aware exact trace-ledger comparison",
        )
        with tempfile.TemporaryDirectory() as folder:
            result = _compare_fixture_pair(runner, Path(folder))

        self.assertTrue(result["passed"], result)
        self.assertEqual(result["maximum_absolute_numeric_difference"], 0.0)
        self.assertEqual(set(result["table_comparisons"]), set(SCIENTIFIC_TABLES))
        self.assertTrue(all(
            row["equivalent"] for row in result["table_comparisons"].values()
        ))
        self.assertEqual(result["root_semantics"], "context_bound")
        self.assertEqual(result["summary_science_root"], "1" * 64)
        self.assertEqual(result["full_science_root"], "2" * 64)
        self.assertEqual(result["summary_evidence_root"], "3" * 64)
        self.assertEqual(result["full_evidence_root"], "4" * 64)
        self.assertEqual(
            result["provenance_only_differences"]["solver_declaration_link"],
            ["declared_input_sha256"],
        )
        self.assertEqual(result["summary_run_id"], "summary-run")
        self.assertEqual(result["full_run_id"], "full-run")
        self.assertEqual(result["summary_trace_profile"], "summary")
        self.assertEqual(result["full_trace_profile"], "full")

    def test_one_micro_unit_physical_change_fails_exact_trace_equivalence(self) -> None:
        runner = load_runner()
        self.assertTrue(hasattr(runner, "_compare_trace_ledgers"))
        with tempfile.TemporaryDirectory() as folder:
            result = _compare_fixture_pair(
                runner, Path(folder), full_scientific_value=1.000001
            )

        self.assertFalse(result["passed"], result)
        self.assertIn("scientific_table_mismatch:period_summary", result["issues"])
        self.assertGreater(result["maximum_absolute_numeric_difference"], 0.0)
        self.assertAlmostEqual(
            result["maximum_absolute_numeric_difference"], 0.000001, places=12
        )

    def test_unexpected_solver_link_field_changes_fail(self) -> None:
        runner = load_runner()
        self.assertTrue(hasattr(runner, "_compare_trace_ledgers"))
        mutations = (
            {"full_solver_status": "fallback", "field": "solver_status"},
            {
                "full_declaration_artifact_id": "unexpected#declared-input",
                "field": "declaration_artifact_id",
            },
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(field=mutation["field"]), tempfile.TemporaryDirectory() as folder:
                arguments = {key: value for key, value in mutation.items() if key != "field"}
                result = _compare_fixture_pair(
                    runner, Path(folder) / str(index), **arguments
                )

            self.assertFalse(result["passed"], result)
            self.assertIn(
                f"solver_declaration_link_mismatch:{mutation['field']}",
                result["issues"],
            )

    def test_both_ledgers_must_validate_independently(self) -> None:
        runner = load_runner()
        self.assertTrue(hasattr(runner, "_compare_trace_ledgers"))
        with tempfile.TemporaryDirectory() as folder:
            result = _compare_fixture_pair(
                runner, Path(folder), full_validator_valid=False
            )

        self.assertFalse(result["passed"], result)
        self.assertTrue(result["summary_validator_valid"])
        self.assertFalse(result["full_validator_valid"])
        self.assertIn("full_ledger_validator_failed", result["issues"])

    def test_prompt127_audit_overrides_only_prompt125_trace_root_equality(self) -> None:
        runner = load_runner()
        self.assertTrue(hasattr(runner, "_compare_trace_ledgers"))
        self.assertTrue(hasattr(runner, "_audit_prompt127_evidence"))
        with tempfile.TemporaryDirectory() as folder:
            trace = _compare_fixture_pair(runner, Path(folder))
        evidence = {"trace_science_equivalence": trace}

        original = runner.PROMPT125.audit_evidence(evidence)
        local = runner._audit_prompt127_evidence(evidence)

        self.assertIn(
            "trace_science_root_mismatch",
            original["gates"]["trace_science_equivalence"]["issues"],
        )
        self.assertTrue(local["gates"]["trace_science_equivalence"]["passed"])
        self.assertEqual(local["gates"]["trace_science_equivalence"]["issues"], [])
        for name in runner.PROMPT125_REQUIRED_GATES:
            if name != "trace_science_equivalence":
                with self.subTest(gate=name):
                    self.assertEqual(local["gates"][name], original["gates"][name])

    def test_trace_audit_retains_run_success_and_common_result_guards(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as folder:
            passing = _compare_fixture_pair(runner, Path(folder))
        mutations = (
            ("summary_run_failed", {"summary_run_passed": False}),
            ("full_run_failed", {"full_run_passed": False}),
            (
                "common_results_differ",
                {"full_results": {"dispatch_sha256": "6" * 64}},
            ),
        )
        for expected, updates in mutations:
            with self.subTest(expected=expected):
                trace = copy.deepcopy(passing)
                trace.update(updates)
                report = runner._audit_prompt127_evidence(
                    {"trace_science_equivalence": trace}
                )
                self.assertIn(
                    expected,
                    report["gates"]["trace_science_equivalence"]["issues"],
                )

    def test_markdown_labels_unexecuted_downstream_evidence_not_run(self) -> None:
        runner = load_runner()
        markdown = runner._markdown({
            "gates": {
                "failure_bundle": {"passed": False},
                "preflight_estimate": {"passed": False},
                "frontend_bounded_access": {"passed": False},
            },
            "literal_48_period_physical_regression": {"passed": True},
            "evidence_path_audit": {"passed": True},
            "executions": [],
            "not_run": ["failure-and-preflight"],
        })

        for name in (
            "failure_bundle",
            "preflight_estimate",
            "frontend_bounded_access",
        ):
            self.assertIn(f"| `{name}` | NOT RUN |", markdown)

    def test_prompt127_paths_are_isolated_from_retained_prompt125_artifacts(self) -> None:
        runner = load_runner()

        self.assertEqual(
            runner.DEFAULT_JSON,
            ROOT / "publication" / "prompt127-output-context-test-report.json",
        )
        self.assertEqual(
            runner.DEFAULT_MARKDOWN,
            ROOT / "publication" / "prompt127-output-context-test-report.md",
        )
        self.assertEqual(
            runner.EVIDENCE_ROOT,
            ROOT / "publication" / "prompt127-output-context-evidence",
        )
        self.assertNotIn("prompt125", str(runner.DEFAULT_JSON))
        self.assertNotIn("prompt125", str(runner.DEFAULT_MARKDOWN))
        self.assertNotIn("prompt125", str(runner.EVIDENCE_ROOT))

    def test_ordered_execution_stops_immediately_after_first_failed_gate(self) -> None:
        runner = load_runner()
        calls: list[str] = []

        def gate(name: str, passed: bool):
            def execute(_evidence):
                calls.append(name)
                return {name: {"passed": passed}}

            return execute

        gate_runners = {
            name: gate(name, name != "two-year-coupling")
            for name in runner.GATE_ORDER
        }

        outcome = runner._execute_ordered(
            gate_runners,
            on_gate_complete=lambda name, _evidence, produced, _elapsed: bool(
                next(iter(produced.values()))["passed"]
            ),
        )

        self.assertEqual(
            calls,
            ["zonal-48", "zonal-336", "two-year-coupling"],
        )
        self.assertEqual(outcome["completed"], calls)
        self.assertEqual(
            outcome["not_run"],
            ["trace-equivalence", "failure-and-preflight"],
        )
        self.assertFalse(outcome["passed"])

    def test_literal_48_period_regression_is_read_from_sqlite(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE period_summary("
                    "real_demand_mwh REAL, accepted_supply_mwh REAL, "
                    "physical_resource_cost_gbp REAL, market_payment_gbp REAL, "
                    "blackout_mwh REAL, curtailed_mwh REAL, "
                    "storage_charge_mwh REAL, storage_discharge_mwh REAL, "
                    "energy_balance_residual_mwh REAL)"
                )
                connection.executemany(
                    "INSERT INTO period_summary VALUES(?,?,?,?,?,?,?,?,?)",
                    [(1.0, 1.0, 10.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0)] * 48,
                )
                connection.commit()

            result = runner._read_literal_48_regression(database)

        self.assertTrue(result["passed"], result)
        self.assertEqual(
            result["expected"],
            {
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
            },
        )
        self.assertEqual(result["observed"], result["expected"])
        self.assertEqual(result["database_path"], str(database.resolve()))

    def test_restart_requires_nine_prompt125_gates_and_literal_regression(self) -> None:
        runner = load_runner()
        nine_passed = {
            name: {"passed": True, "issues": []}
            for name in runner.PROMPT125_REQUIRED_GATES
        }

        authorised = runner._prompt127_decision(
            {"gates": nine_passed, "first_blocker": None},
            {"passed": True},
        )
        refused = runner._prompt127_decision(
            {"gates": nine_passed, "first_blocker": None},
            {"passed": False, "mismatches": ["market_payment_gbp"]},
        )

        self.assertTrue(authorised["ten_year_restart_authorised"])
        self.assertFalse(refused["ten_year_restart_authorised"])
        self.assertEqual(
            refused["first_blocker"],
            {
                "gate": "zonal_48_literal_physical_regression",
                "issues": ["market_payment_gbp"],
            },
        )
        self.assertFalse(authorised["bounded_scope"]["annual_run_started"])
        self.assertFalse(authorised["bounded_scope"]["ten_year_run_started"])

    def test_markdown_retains_trace_paths_hashes_bytes_and_elapsed_time(self) -> None:
        runner = load_runner()
        report = {
            "gates": {
                "trace_science_equivalence": {
                    "passed": False,
                    "summary_science_root": "a" * 64,
                    "full_science_root": "b" * 64,
                    "summary_evidence_root": "c" * 64,
                    "full_evidence_root": "d" * 64,
                    "summary_output_root": "C:/prompt127/trace-summary",
                    "full_output_root": "C:/prompt127/trace-full",
                    "summary_output_bytes": 123,
                    "full_output_bytes": 456,
                    "elapsed_seconds": 7.5,
                    "comparison_semantics": "exact_row_and_sqlite_type_equality",
                    "maximum_absolute_numeric_difference": 0.0,
                    "scientific_tables_equivalent": True,
                    "solver_link_equivalent": True,
                    "summary_validator_valid": True,
                    "full_validator_valid": False,
                    "root_semantics": "context_bound",
                    "provenance_only_differences": {
                        "solver_declaration_link": ["declared_input_sha256"],
                    },
                    "issues": ["trace_science_root_mismatch"],
                },
            },
            "literal_48_period_physical_regression": {"passed": True},
            "evidence_path_audit": {"passed": True},
            "executions": [],
        }

        markdown = runner._markdown(report)

        for expected in (
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            "C:/prompt127/trace-summary",
            "C:/prompt127/trace-full",
            '"summary_output_bytes": 123',
            '"full_output_bytes": 456',
            '"elapsed_seconds": 7.5',
            '"comparison_semantics": "exact_row_and_sqlite_type_equality"',
            '"maximum_absolute_numeric_difference": 0.0',
            '"scientific_tables_equivalent": true',
            '"solver_link_equivalent": true',
            '"summary_validator_valid": true',
            '"full_validator_valid": false',
            '"root_semantics": "context_bound"',
            '"solver_declaration_link": ["declared_input_sha256"]',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, markdown)


if __name__ == "__main__":
    unittest.main()
