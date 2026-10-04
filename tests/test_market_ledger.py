import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from contextlib import closing
from pathlib import Path

from gridform_core.market_ledger import (
    NetworkSolverDiagnosticRow,
    OrderLedgerRow,
    PeriodLedgerRow,
    PhysicalDispatchRow,
    SCHEMA_VERSION,
    SQLiteMarketLedger,
    StorageStateRow,
    create_market_ledger,
    export_market_table,
    query_market_table,
    validate_market_ledger_file,
)
from gridform_core.clearing_inputs import ClearingInputRow, ClearingOutcomeRow
from gridform_core.errors import InvariantError


ROOT = Path(__file__).resolve().parents[1]


def _three_phase_diagnostic_rows():
    common = {
        "run_id": "run-zonal",
        "year": 2025,
        "period": 4,
        "period_id": "2025:4",
        "module_id": "value-zonal-redispatch-balancing",
        "module_version": "2.0.0",
        "solver_contract_version": "value.zonal-lexicographic/v2",
        "scipy_version": "1.8.1",
        "highs_identity": "scipy-embedded-highs:" + "a" * 64,
        "highs_binary_sha256": "a" * 64,
        "method": "highs-ds",
        "presolve": True,
        "primal_feasibility_tolerance": 1e-9,
        "dual_feasibility_tolerance": 1e-9,
        "ipm_optimality_tolerance": None,
        "validation_class": "GO",
        "error_code": None,
        "declared_input_sha256": "b" * 64,
    }
    return tuple(
        NetworkSolverDiagnosticRow(
            **common,
            phase_id=phase_id,
            objective_unit=unit,
            optimum=optimum,
            achieved_final_value=optimum,
            degradation=0.0,
            computed_tolerance=tolerance,
            warning_ceiling=validated_ceiling * 0.1,
            validated_ceiling=validated_ceiling,
            absolute_ceiling=absolute_ceiling,
            nonzero_term_count=term_count,
            absolute_term_scale=scale,
        )
        for phase_id, unit, optimum, tolerance, validated_ceiling,
        absolute_ceiling, term_count, scale in (
            ("primary_bid_cost", "GBP", 600.0, 6e-7, 0.01, 0.10, 2, 600.0),
            (
                "secondary_schedule_deviation", "MWh", 12.0, 1.2e-8,
                0.001, 0.01, 4, 12.0,
            ),
            ("physical_throughput", "MWh", 4.0, 4e-9, 0.001, 0.01, 2, 4.0),
        )
    )


def _create_legacy_ledger(database: Path, version: str) -> None:
    contracts = ROOT / "gridform_core" / "data" / "contracts"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
            (f"value.market-ledger/{version}",),
        )
        connection.executescript(
            (contracts / "market-ledger-v5.schema.sql").read_text(encoding="utf-8")
        )
        if version in {"v6", "v7"}:
            connection.executescript(
                (contracts / "market-ledger-v6.schema.sql").read_text(
                    encoding="utf-8"
                )
            )
        if version == "v7":
            connection.executescript(
                (contracts / "market-ledger-v7.schema.sql").read_text(
                    encoding="utf-8"
                )
            )
        connection.commit()


def period(index=0, residual=0.0):
    return PeriodLedgerRow(
        2025, index, "final_dispatch", 50.0, 49.0, 50.0,
        1.0, 2.0, 0.0, 0.0, 20.0, 19.0, 1.0, 2.0,
        80.0, 1000.0, 4000.0, 0.0, 0.0, 0.0, residual,
    )


class MarketLedgerTests(unittest.TestCase):
    def test_close_hashes_the_database_without_reading_it_into_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(
                Path(folder) / "market.sqlite", trace_level="summary"
            )
            ledger.record_period(period())
            declared = ClearingInputRow.create(
                year=2025,
                period=0,
                stage="ahead",
                information_scope="forecast only",
                payload={"target_power_mw": 10.0, "offers": []},
            )
            ledger.record_clearing_input(declared)
            ledger.record_clearing_outcome(ClearingOutcomeRow.create(
                declared.input_sha256,
                {"accepted_power_mw": 0.0},
            ))
            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("database must be hashed as a stream"),
            ):
                metadata = ledger.close()
        self.assertEqual(len(metadata["source_artifact_sha256"]), 64)
        self.assertEqual(metadata["rows"]["clearing_inputs"], 0)
        self.assertEqual(metadata["rows"]["clearing_outcomes"], 0)

    def test_schema_round_trip_pagination_filter_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full", batch_size=2)
            ledger.record_period(period(0))
            ledger.record_period(period(1))
            ledger.record_orders((
                OrderLedgerRow("o1", 2025, 0, "ahead_offer", "solar", "vre", "supply", 0.0, 10.0, 10.0, "accepted", "cleared", 0.0, 500.0),
                OrderLedgerRow("o2", 2025, 0, "ahead_offer", "gas", "thermal", "supply", 50.0, 10.0, 0.0, "rejected", "not_selected", 0.0, 0.0),
            ))
            ledger.record_storage((StorageStateRow(2025, 0, "battery", 5.0, 1.0, 0.0, 2.0, 8.0),))
            ledger.record_physical_dispatch((
                PhysicalDispatchRow(2025, 0, "solar", "solar", "generation", 10.0, 10.0, "physical_asset", "final_dispatch"),
            ))
            declared = ClearingInputRow.create(
                year=2025,
                period=0,
                stage="ahead",
                information_scope="forecast only",
                payload={"target_power_mw": 10.0, "offers": []},
            )
            ledger.record_clearing_input(declared)
            ledger.record_clearing_outcome(ClearingOutcomeRow.create(
                declared.input_sha256,
                {"accepted_power_mw": 0.0},
            ))
            metadata = ledger.close()
            page = query_market_table(database, "orders", limit=1, period=0)
            physical = query_market_table(
                database, "physical_dispatch", technology="solar", flow_type="generation"
            )
            export = export_market_table(database, "period_summary", root / "periods.jsonl")
            with closing(sqlite3.connect(database)) as connection:
                version = connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertEqual(page["total"], 2)
            self.assertEqual(len(page["items"]), 1)
            self.assertEqual(physical["total"], 1)
            self.assertEqual(export["rows"], 2)
            self.assertEqual(metadata["rows"]["orders"], 2)
            self.assertEqual(metadata["rows"]["clearing_inputs"], 1)
            self.assertEqual(metadata["rows"]["clearing_outcomes"], 1)
            self.assertEqual(metadata["rows"]["physical_dispatch"], 1)
            self.assertEqual(len(metadata["source_artifact_sha256"]), 64)
            self.assertEqual(metadata["compatibility_adjustment_periods"], 0)
            self.assertGreater(metadata["bytes"], 0)
            self.assertTrue((root / "metadata.json").is_file())
            index = json.loads((root / "index.json").read_text("utf-8"))
            self.assertEqual(index["storage_cost_module_id"], "unknown")
            self.assertEqual(index["rows"]["period_summary"], 2)
            self.assertEqual(index["units"]["energy"], "MWh/period")

    def test_declared_input_is_stable_and_rejects_outcome_leakage(self):
        first = ClearingInputRow.create(
            year=2025,
            period=7,
            stage="ahead",
            information_scope="forecast only",
            payload={"offers": [{"price": 2.0, "asset": "a"}], "target": 1.0},
        )
        second = ClearingInputRow.create(
            year=2025,
            period=7,
            stage="ahead",
            information_scope="forecast only",
            payload={"target": 1.0, "offers": [{"asset": "a", "price": 2.0}]},
        )
        self.assertEqual(first.input_sha256, second.input_sha256)
        self.assertEqual(first.payload(), second.payload())
        with self.assertRaisesRegex(ValueError, "outcome"):
            ClearingInputRow.create(
                year=2025,
                period=7,
                stage="ahead",
                information_scope="forecast only",
                payload={"accepted_mwh": 1.0},
            )

    def test_compatibility_adjustment_is_explicit_and_balanced(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(Path(folder) / "market.sqlite", trace_level="summary")
            row = period()
            ledger.record_period(PeriodLedgerRow(
                **{
                    **row.__dict__,
                    "energy_balance_residual_mwh": 0.0,
                    "compatibility_adjustment_mwh": 2.0,
                    "raw_energy_balance_residual_mwh": -2.0,
                }
            ))
            metadata = ledger.close()
            self.assertEqual(metadata["compatibility_adjustment_periods"], 1)
            self.assertEqual(metadata["maximum_absolute_raw_energy_balance_residual_mwh"], 2.0)

    def test_energy_balance_is_asserted_before_insert(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(Path(folder) / "market.sqlite", trace_level="summary")
            ledger.record_period(period(residual=1e-7))
            with self.assertRaisesRegex(ValueError, "energy balance"):
                ledger.record_period(period(1, residual=0.1))
            metadata = ledger.close()
            self.assertEqual(metadata["rows"]["period_summary"], 1)

    def test_off_is_null_and_full_only_controls_orders(self):
        off = create_market_ledger(Path("unused.sqlite"), "off")
        off.record_period(period())
        self.assertEqual(off.close()["rows"], 0)
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(Path(folder) / "market.sqlite", trace_level="summary")
            ledger.record_orders((OrderLedgerRow("ignored", 2025, 0, "ahead", "a", "x", "supply", 0, 1, 0, "rejected", "x", 0, 0),))
            metadata = ledger.close()
            self.assertEqual(metadata["rows"]["orders"], 0)

    def test_close_is_idempotent_and_commits_partial_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(Path(folder) / "market.sqlite", trace_level="summary", batch_size=100)
            ledger.record_period(period())
            first = ledger.close()
            second = ledger.close()
            self.assertEqual(first["rows"], second["rows"])

    def test_optional_parquet_absence_does_not_break_default_sqlite(self):
        with tempfile.TemporaryDirectory() as folder:
            default = SQLiteMarketLedger(Path(folder) / "default.sqlite", trace_level="summary")
            default.record_period(period())
            self.assertEqual(default.close()["requested_export_format"], "sqlite")
            selected = SQLiteMarketLedger(
                Path(folder) / "selected.sqlite",
                trace_level="summary",
                export_format="parquet",
            )
            selected.record_period(period())
            with patch("gridform_core.market_ledger.parquet_available", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "requires pyarrow"):
                    selected.close()


class MarketLedgerV7Tests(unittest.TestCase):
    def test_diagnostic_degradation_must_match_final_minus_optimum(self):
        payload = vars(_three_phase_diagnostic_rows()[0]) | {
            "achieved_final_value": 600.00001,
            "degradation": 0.0,
        }

        with self.assertRaisesRegex(
            ValueError, "degradation.*achieved_final_value.*optimum"
        ):
            NetworkSolverDiagnosticRow(**payload)

    def test_v7_sql_rejects_contradictory_degradation_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.close()
            values = vars(_three_phase_diagnostic_rows()[0]) | {
                "achieved_final_value": 600.00001,
                "degradation": 0.0,
            }

            with closing(sqlite3.connect(database)) as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO network_solver_diagnostics VALUES("
                        + ",".join("?" for _ in range(29))
                        + ")",
                        tuple(values.values()),
                    )

    def test_v7_sql_rejects_forged_lock_classes_and_degradation_above_tau(self):
        mutations = (
            {
                "optimum": -5.0,
                "achieved_final_value": -4.998,
                "degradation": 0.002,
                "computed_tolerance": 0.001,
                "validation_class": "GO",
            },
            {"validation_class": "GO_WITH_NUMERICAL_WARNING"},
            {"validation_class": "COMPLETED_WITH_NUMERICAL_WARNING"},
            {
                "computed_tolerance": 0.02,
                "validation_class": "GO_WITH_NUMERICAL_WARNING",
            },
            {"validation_class": "UNKNOWN"},
        )
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.close()
            base = vars(_three_phase_diagnostic_rows()[0])
            with closing(sqlite3.connect(database)) as connection:
                for mutation in mutations:
                    with self.subTest(mutation=mutation):
                        values = base | mutation
                        with self.assertRaises(sqlite3.IntegrityError):
                            connection.execute(
                                "INSERT INTO network_solver_diagnostics VALUES("
                                + ",".join("?" for _ in range(29))
                                + ")",
                                tuple(values.values()),
                            )

    def test_solver_identity_text_must_match_recorded_binary_sha(self):
        payload = vars(_three_phase_diagnostic_rows()[0]) | {
            "highs_identity": "scipy-embedded-highs:" + "c" * 64,
        }

        with self.assertRaisesRegex(ValueError, "highs_identity.*binary SHA"):
            NetworkSolverDiagnosticRow(**payload)

    def test_active_ipm_method_requires_positive_ipm_tolerance(self):
        payload = vars(_three_phase_diagnostic_rows()[0]) | {
            "method": "highs-ipm",
            "ipm_optimality_tolerance": None,
        }

        with self.assertRaisesRegex(
            ValueError, "ipm_optimality_tolerance must be positive"
        ):
            NetworkSolverDiagnosticRow(**payload)

    def test_v7_sql_rejects_null_or_nonfinite_active_ipm_tolerance(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.close()
            with closing(sqlite3.connect(database)) as connection:
                for index, tolerance in enumerate((None, float("inf"))):
                    values = vars(_three_phase_diagnostic_rows()[0]) | {
                        "run_id": f"ipm-run-{index}",
                        "method": "highs-ipm",
                        "ipm_optimality_tolerance": tolerance,
                    }
                    with self.subTest(tolerance=tolerance), self.assertRaises(
                        sqlite3.IntegrityError
                    ):
                        connection.execute(
                            "INSERT INTO network_solver_diagnostics VALUES("
                            + ",".join("?" for _ in range(29))
                            + ")",
                            tuple(values.values()),
                        )

    def test_diagnostic_class_must_match_declared_numerical_evidence(self):
        payload = vars(_three_phase_diagnostic_rows()[1]) | {
            "computed_tolerance": 0.002,
            "validation_class": "GO",
        }
        with self.assertRaisesRegex(ValueError, "validation_class does not match"):
            NetworkSolverDiagnosticRow(**payload)

    def test_v8_round_trips_one_row_per_locked_phase(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_network_solver_diagnostics(
                _three_phase_diagnostic_rows()
            )
            metadata = ledger.close()
            with closing(sqlite3.connect(database)) as connection:
                phases = [
                    row[0]
                    for row in connection.execute(
                        "SELECT phase_id FROM network_solver_diagnostics "
                        "ORDER BY rowid"
                    )
                ]
                integrity = connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
        self.assertEqual(phases, [
            "primary_bid_cost",
            "secondary_schedule_deviation",
            "physical_throughput",
        ])
        self.assertEqual(integrity, "ok")
        self.assertEqual(metadata["schema_version"], "value.market-ledger/v8")
        self.assertEqual(metadata["rows"]["network_solver_diagnostics"], 3)

    def test_v8_round_trips_unvalidated_tolerance_above_reference_threshold(self):
        rows = list(_three_phase_diagnostic_rows())
        rows[0] = NetworkSolverDiagnosticRow(**(
            vars(rows[0]) | {
                "achieved_final_value": 600.11,
                "degradation": 0.11,
                "computed_tolerance": 0.12,
                "validation_class": "COMPLETED_WITH_NUMERICAL_WARNING",
            }
        ))
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_network_solver_diagnostics(rows)
            ledger.close()
            with closing(sqlite3.connect(database)) as connection:
                stored = connection.execute(
                    "SELECT computed_tolerance, validation_class "
                    "FROM network_solver_diagnostics "
                    "WHERE phase_id = 'primary_bid_cost'"
                ).fetchone()

        self.assertEqual(stored, (0.12, "COMPLETED_WITH_NUMERICAL_WARNING"))

    def test_diagnostic_period_requires_all_three_locked_phases(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(
                Path(folder) / "market.sqlite", trace_level="summary"
            )
            try:
                with self.assertRaisesRegex(InvariantError, "three locked phases"):
                    ledger.record_network_solver_diagnostics(
                        _three_phase_diagnostic_rows()[:2]
                    )
            finally:
                ledger.close()

    def test_v5_through_v7_are_read_only_but_queryable(self):
        for version in ("v5", "v6", "v7"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as folder:
                database = Path(folder) / "market.sqlite"
                _create_legacy_ledger(database, version)
                before = database.read_bytes()
                report = validate_market_ledger_file(database)
                page = query_market_table(
                    database, "zone_period_summary", limit=10
                )
                self.assertIs(report["valid"], True)
                self.assertEqual(
                    report["schema_version"], f"value.market-ledger/{version}"
                )
                self.assertEqual(page["total"], 0)
                with self.assertRaisesRegex(InvariantError, "read-only"):
                    SQLiteMarketLedger(database, trace_level="full")
                self.assertEqual(database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
