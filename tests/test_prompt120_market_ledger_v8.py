from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from gridform_core import market_ledger as market_ledger_module
from gridform_core.builtin.scheme_c_1000twh import staged_psm as staged_psm_module
from gridform_core.clearing_inputs import ClearingInputRow, ClearingOutcomeRow
from gridform_core.errors import InvariantError
from gridform_core.perfect_foresight_psm import PerfectForesightPSM
from gridform_core.market_ledger import (
    DispatchSummaryRow,
    BoundaryPeriodLedgerRow,
    MarketPeriodBatch,
    NetworkSolverDiagnosticRow,
    OrderLedgerRow,
    PeriodLedgerRow,
    PERIOD_INDEXED_V8_TABLES,
    PhysicalDispatchRow,
    RedispatchSettlementRow,
    RedispatchSummaryRow,
    ReliabilityEventRow,
    SQLiteMarketLedger,
    SolverDeclarationLinkRow,
    StorageStateRow,
    StorageSummaryRow,
    VRECurtailmentDetailRow,
    VRECurtailmentPeriodRow,
    ZonalAccountingLedgerRow,
    ZonalDemandAlignmentLedgerRow,
    ZonalResourceDispatchRow,
    ZonePeriodLedgerRow,
    build_market_period_batch,
    market_ledger_boundary,
    query_market_table,
    validate_market_ledger_file,
    verify_v8_market_prefix,
)
from gridform_core.run_bundle import export_run_bundle
from gridform_core.staged_market_contracts import AcceptedAdjustment, FlexibilityBid
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_CONTEXT_SHA256 = "a" * 64
YEAR_CONTEXT_SHA256 = "b" * 64


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _period(index: int) -> PeriodLedgerRow:
    return PeriodLedgerRow(
        year=2025,
        period=index,
        stage="final_dispatch",
        forecast_demand_mwh=10.0,
        real_demand_mwh=10.0,
        accepted_supply_mwh=10.0,
        storage_charge_mwh=1.0,
        storage_discharge_mwh=1.0,
        flexible_demand_mwh=0.0,
        export_mwh=0.0,
        vre_available_mwh=6.0,
        vre_accepted_mwh=5.0,
        curtailed_mwh=1.0,
        import_mwh=0.0,
        clearing_price_gbp_per_mwh=50.0,
        physical_resource_cost_gbp=200.0,
        market_payment_gbp=500.0,
        policy_transfer_gbp=0.0,
        blackout_mwh=0.0,
        excess_mwh=1.0,
        energy_balance_residual_mwh=0.0,
    )


def _batch(index: int, *, include_order: bool) -> MarketPeriodBatch:
    period = _period(index)
    dispatch = (
        DispatchSummaryRow(
            2025, index, "final_dispatch", "GB", "solar", 5.0
        ),
        DispatchSummaryRow(
            2025, index, "final_dispatch", "GB", "ccgt", 5.0
        ),
    )
    storage = (
        StorageSummaryRow(2025, index, "GB", "battery", 1.0, 1.0, 4.0),
    )
    redispatch = (
        RedispatchSummaryRow(2025, index, "GB", "ccgt", "up", 1.0, 20.0),
    )
    orders = (
        OrderLedgerRow(
            f"order-{index}", 2025, index, "ahead", "solar", "vre",
            "supply", 0.0, 5.0, 5.0, "accepted", "cleared", 0.0, 0.0,
        ),
    ) if include_order else ()
    return build_market_period_batch(
        period=period,
        dispatch_summary=dispatch,
        storage_summary=storage,
        redispatch_summary=redispatch,
        common_rows={},
        full_rows={"orders": orders},
        run_context_sha256=RUN_CONTEXT_SHA256,
        year_context_sha256=YEAR_CONTEXT_SHA256,
    )


def _solver_diagnostics(index: int) -> tuple[NetworkSolverDiagnosticRow, ...]:
    common = {
        "run_id": "run-zonal",
        "year": 2025,
        "period": index,
        "period_id": f"2025:{index}",
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


def _zonal_accounting(index: int) -> ZonalAccountingLedgerRow:
    return ZonalAccountingLedgerRow(
        year=2025,
        period=index,
        period_id=f"2025:{index}",
        system_resource_cost_gbp=0.0,
        network_constraint_cost_gbp=0.0,
        national_settlement_gbp=0.0,
        redispatch_settlement_gbp=0.0,
        policy_transfer_gbp=0.0,
        perfect_forecast_resource_cost_gbp=0.0,
        realised_copperplate_resource_cost_gbp=0.0,
        zonal_resource_cost_gbp=0.0,
        forecast_error_cost_gbp=0.0,
        total_deviation_cost_gbp=0.0,
        blackout_mwh=0.0,
        counterfactual_realised_input_sha256="c" * 64,
        accounting_status="reconciled",
    )


def _full_trace_batch(index: int) -> MarketPeriodBatch:
    clearing_input = ClearingInputRow.create(
        year=2025,
        period=index,
        stage="ahead",
        information_scope="fixture",
        payload={"period": index},
    )
    clearing_outcome = ClearingOutcomeRow.create(
        clearing_input.input_sha256,
        {"status": "cleared", "period": index},
    )
    return build_market_period_batch(
        period=_period(index),
        dispatch_summary=(
            DispatchSummaryRow(2025, index, "final_dispatch", "GB", "solar", 10.0),
        ),
        storage_summary=(
            StorageSummaryRow(2025, index, "GB", "battery", 1.0, 1.0, 4.0),
        ),
        redispatch_summary=(
            RedispatchSummaryRow(2025, index, "GB", "ccgt", "up", 1.0, 20.0),
        ),
        common_rows={
            "zonal_period_accounting": (_zonal_accounting(index),),
            "vre_curtailment_period": (
                VRECurtailmentPeriodRow(
                    2025, index, f"2025:{index}", 6.0, 5.0, 5.0, 5.0,
                    1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0 / 6.0,
                    0.0, 1e-9, "reconciled", "c" * 64, "fixture-v1",
                ),
            ),
            "zonal_demand_alignment": (
                ZonalDemandAlignmentLedgerRow(
                    2025, index, f"2025:{index}",
                    "network_pack_absolute_demand", 10.0, 10.0, 10.0,
                    1.0, 10.0, 0.0,
                ),
            ),
            "zone_period_summary": (
                ZonePeriodLedgerRow(
                    2025, index, "GB", 10.0, 10.0, 10.0, 0.0, 0.0, 0.0,
                ),
            ),
            "boundary_period_summary": (
                BoundaryPeriodLedgerRow(
                    2025, index, "B1", 0.0, 10.0, 10.0, 0.0, 0.0,
                    "diagnostic_not_zonal_price_or_cash_cost",
                ),
            ),
            "solver_declaration_link": (
                SolverDeclarationLinkRow(
                    2025, index, clearing_input.input_sha256,
                    f"declaration-{index}", f"solver-{index}", None, "optimal",
                ),
            ),
        },
        full_rows={
            "orders": (
                OrderLedgerRow(
                    f"order-{index}", 2025, index, "ahead", "solar", "vre",
                    "supply", 0.0, 5.0, 5.0, "accepted", "cleared", 0.0, 0.0,
                ),
            ),
            "storage_state": (
                StorageStateRow(2025, index, "battery", 4.0, 1.0, 1.0, 2.0, 8.0),
            ),
            "physical_dispatch": (
                PhysicalDispatchRow(
                    2025, index, "solar", "solar", "generation", 10.0, 10.0,
                    "physical_asset", "final_dispatch",
                ),
            ),
            "clearing_inputs": (clearing_input,),
            "clearing_outcomes": (clearing_outcome,),
            "vre_curtailment_detail": (
                VRECurtailmentDetailRow(
                    2025, index, f"2025:{index}", "solar", "agent", "GB",
                    "solar", f"tranche-{index}", 6.0, 5.0, 5.0, 5.0,
                    1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0,
                    "deterministic_reference_allocation",
                ),
            ),
            "zonal_resource_dispatch": (
                ZonalResourceDispatchRow(
                    2025, index, "solar", "agent", "GB", "solar",
                    10.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                ),
            ),
            "redispatch_settlement": (
                RedispatchSettlementRow(
                    f"bid-{index}", 2025, index, "agent", "solar", "GB",
                    "solar", "up", 1.0, 1.0, 20.0, 20.0,
                    "accepted", "cleared",
                ),
            ),
            "network_solver_diagnostics": _solver_diagnostics(index),
        },
        run_context_sha256=RUN_CONTEXT_SHA256,
        year_context_sha256=YEAR_CONTEXT_SHA256,
    )


def _write_legacy_fixture(database: Path, version: str) -> None:
    contracts = ROOT / "gridform_core" / "data" / "contracts"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE period_summary(
                year INTEGER NOT NULL, period INTEGER NOT NULL, stage TEXT NOT NULL,
                forecast_demand_mwh REAL NOT NULL, real_demand_mwh REAL NOT NULL,
                accepted_supply_mwh REAL NOT NULL, storage_charge_mwh REAL NOT NULL,
                storage_discharge_mwh REAL NOT NULL, flexible_demand_mwh REAL NOT NULL,
                export_mwh REAL NOT NULL, vre_available_mwh REAL NOT NULL,
                vre_accepted_mwh REAL NOT NULL, curtailed_mwh REAL NOT NULL,
                import_mwh REAL NOT NULL, clearing_price_gbp_per_mwh REAL NOT NULL,
                physical_resource_cost_gbp REAL NOT NULL, market_payment_gbp REAL NOT NULL,
                policy_transfer_gbp REAL NOT NULL, blackout_mwh REAL NOT NULL,
                excess_mwh REAL NOT NULL, energy_balance_residual_mwh REAL NOT NULL,
                compatibility_adjustment_mwh REAL NOT NULL,
                raw_energy_balance_residual_mwh REAL NOT NULL,
                PRIMARY KEY(year, period, stage)
            );
            """
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
            (f"value.market-ledger/{version}",),
        )
        connection.execute(
            "INSERT INTO period_summary VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(_period(0).__dict__.values()),
        )
        if version in {"v5", "v6", "v7"}:
            connection.executescript(
                (contracts / "market-ledger-v5.schema.sql").read_text("utf-8")
            )
        if version in {"v6", "v7"}:
            connection.executescript(
                (contracts / "market-ledger-v6.schema.sql").read_text("utf-8")
            )
        if version == "v7":
            connection.executescript(
                (contracts / "market-ledger-v7.schema.sql").read_text("utf-8")
            )


class Prompt120MarketLedgerV8Tests(unittest.TestCase):
    def test_period_index_registry_exactly_covers_the_v8_schema(self):
        expected = (
            "period_summary", "orders", "storage_state", "physical_dispatch",
            "clearing_inputs", "zonal_period_summary", "zonal_period_accounting",
            "vre_curtailment_period", "vre_curtailment_detail",
            "zonal_demand_alignment", "zone_period_summary",
            "boundary_period_summary", "zonal_resource_dispatch",
            "redispatch_settlement", "solver_declaration_link",
            "network_solver_diagnostics", "dispatch_summary", "storage_summary",
            "redispatch_summary", "period_integrity",
        )
        self.assertEqual(PERIOD_INDEXED_V8_TABLES, expected)
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(_full_trace_batch(0))
            ledger.close_unsealed()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE future_period_rows("
                    "year INTEGER NOT NULL, period INTEGER NOT NULL)"
                )
                connection.commit()
            with self.assertRaisesRegex(InvariantError, "period-indexed.*registry"):
                market_ledger_boundary(database, year=2025, committed_period=0)

    def test_prefix_verifier_replays_every_period_through_the_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            for period in range(3):
                ledger.record_period_batch(_full_trace_batch(period))
            ledger.close_unsealed()

            boundary = market_ledger_boundary(
                database, year=2025, committed_period=2
            )
            verification = verify_v8_market_prefix(database, boundary=boundary)

            self.assertTrue(verification["valid"], verification)
            self.assertEqual(boundary.period_count, 3)
            self.assertEqual(boundary.last_committed_period, 2)
            self.assertEqual(
                boundary.common_projection_sha256,
                verification["common_projection_sha256"],
            )
            self.assertEqual(
                boundary.stored_rows_sha256,
                verification["stored_rows_sha256"],
            )

    def test_prefix_verifier_rejects_a_missing_middle_period(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            for period in range(3):
                ledger.record_period_batch(_full_trace_batch(period))
            ledger.close_unsealed()
            boundary = market_ledger_boundary(
                database, year=2025, committed_period=2
            )
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "DELETE FROM period_integrity WHERE year=2025 AND period=1"
                )
                connection.commit()

            with self.assertRaisesRegex(InvariantError, "continuous.*0..2"):
                verify_v8_market_prefix(database, boundary=boundary)

    def test_prefix_verifier_rejects_a_tampered_boundary_root(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            for period in range(3):
                ledger.record_period_batch(_full_trace_batch(period))
            ledger.close_unsealed()
            boundary = market_ledger_boundary(
                database, year=2025, committed_period=2
            )
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE period_integrity SET science_hash=? "
                    "WHERE year=2025 AND period=2",
                    ("f" * 64,),
                )
                connection.commit()

            with self.assertRaisesRegex(InvariantError, "science root"):
                verify_v8_market_prefix(database, boundary=boundary)

    @unittest.skipUnless(
        importlib.util.find_spec("scipy") is not None,
        "real perfect-foresight regression requires the approved SciPy extra",
    )
    def test_shared_factory_preserves_real_perfect_foresight_v7_contract(self):
        staged_factory = getattr(
            market_ledger_module, "create_staged_market_ledger_v8", None
        )
        self.assertIsNotNone(staged_factory)
        self.assertIs(
            getattr(staged_psm_module, "create_staged_market_ledger_v8", None),
            staged_factory,
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for trace_level in ("summary", "full"):
                with self.subTest(trace_level=trace_level):
                    artifact_directory = root / trace_level / "solver"
                    artifact_directory.mkdir(parents=True)
                    model_input = PSMInput(
                        "pf-run",
                        2025,
                        "synthetic",
                        OperatingState(2025, (), ()),
                        1.0,
                        {"runtime.market_trace_level": trace_level},
                        chronology=ChronologicalPSMData(
                            ("p0",),
                            (1.0,),
                            (
                                DispatchResource(
                                    "thermal", "ccgt", "thermal", 1.0, 10.0, (1.0,)
                                ),
                            ),
                            (),
                            10_000.0,
                        ),
                        extensions={"artifact_directory": str(artifact_directory)},
                    )
                    result = PerfectForesightPSM().run(model_input)
                    metadata = result.extensions["market_ledger"]
                    database = artifact_directory.parent / "market" / "market.sqlite"
                    validation = validate_market_ledger_file(database)
                    self.assertEqual(metadata["schema_version"], "value.market-ledger/v7")
                    self.assertNotIn("context_hashes", metadata)
                    self.assertNotIn("science_root_by_year", metadata)
                    self.assertNotIn("evidence_root_by_year", metadata)
                    self.assertGreater(metadata["rows"]["physical_dispatch"], 0)
                    self.assertTrue(validation["valid"], validation)
                    index = json.loads(
                        (database.parent / "index.json").read_text("utf-8")
                    )
                    field_dictionary = json.loads(
                        (database.parent / "field-dictionary.json").read_text("utf-8")
                    )
                    self.assertEqual(
                        index["ledger_schema_version"], "value.market-ledger/v7"
                    )
                    self.assertNotIn("context_hashes", index)
                    self.assertEqual(
                        field_dictionary["ledger_schema_version"],
                        "value.market-ledger/v7",
                    )
                    with closing(sqlite3.connect(database)) as connection:
                        tables = {
                            str(row[0])
                            for row in connection.execute(
                                "SELECT name FROM sqlite_master WHERE type='table'"
                            )
                        }
                    self.assertTrue(
                        {"context_registry", "period_integrity", "year_integrity"}.isdisjoint(
                            tables
                        )
                    )

            staged = staged_factory(
                root / "staged" / "market.sqlite", trace_level="summary"
            )
            staged.record_period_batch(_batch(0, include_order=False))
            staged_metadata = staged.close()
            self.assertEqual(
                staged_metadata["schema_version"], "value.market-ledger/v8"
            )

    def test_year_chain_requires_contiguous_append_and_rejects_sealed_year(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            try:
                ledger.record_period_batch(_batch(0, include_order=False))
                with self.assertRaisesRegex(InvariantError, "expected period 1"):
                    ledger.record_period_batch(_batch(2, include_order=False))
                ledger.record_period_batch(_batch(1, include_order=False))
                ledger.close()
            finally:
                if not ledger._closed:
                    ledger.connection.close()

            reopened = SQLiteMarketLedger(database, trace_level="summary")
            with self.assertRaisesRegex(InvariantError, "sealed"):
                reopened.record_period_batch(_batch(2, include_order=False))
            reopened.close()

    def test_reopen_rejects_trace_or_immutable_metadata_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(
                database,
                trace_level="summary",
                semantic_metadata={"run_id": "run-a", "period_hours": 0.5},
            )
            ledger.record_period_batch(_batch(0, include_order=False))
            ledger.close()
            with self.assertRaisesRegex(InvariantError, "trace_level"):
                SQLiteMarketLedger(
                    database,
                    trace_level="full",
                    semantic_metadata={"run_id": "run-a", "period_hours": 0.5},
                )
            with self.assertRaisesRegex(InvariantError, "semantic metadata"):
                SQLiteMarketLedger(
                    database,
                    trace_level="summary",
                    semantic_metadata={"run_id": "run-b", "period_hours": 0.5},
                )

    def test_integer_zero_float_fields_round_trip_through_v8_integrity(self):
        period = replace(
            _period(0),
            flexible_demand_mwh=0,
            export_mwh=0,
            import_mwh=0,
            policy_transfer_gbp=0,
            blackout_mwh=0,
            energy_balance_residual_mwh=0,
            compatibility_adjustment_mwh=0,
            raw_energy_balance_residual_mwh=0,
        )
        batch = build_market_period_batch(
            period=period,
            run_context_sha256=RUN_CONTEXT_SHA256,
            year_context_sha256=YEAR_CONTEXT_SHA256,
        )
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(batch)
            ledger.close()

            validation = validate_market_ledger_file(database)
            self.assertTrue(validation["valid"], validation)
            with closing(sqlite3.connect(database)) as connection:
                stored_projection_sha256 = connection.execute(
                    "SELECT common_projection_sha256 FROM period_integrity "
                    "WHERE year=2025 AND period=0"
                ).fetchone()[0]
                reconstructed_projection, _ = (
                    market_ledger_module._database_period_projections(
                        connection,
                        year=2025,
                        period=0,
                        trace_level="summary",
                    )
                )
            self.assertEqual(
                stored_projection_sha256,
                market_ledger_module.projection_sha256(
                    reconstructed_projection,
                    schema_version=market_ledger_module.SCIENCE_PROJECTION_SCHEMA,
                ),
            )
            projection_json = json.loads(json.dumps(reconstructed_projection))
            self.assertIsInstance(projection_json["period"]["year"], int)
            self.assertIsInstance(projection_json["period"]["period"], int)

    def test_full_trace_solver_diagnostics_round_trip_boolean_contract(self):
        batch = build_market_period_batch(
            period=_period(0),
            common_rows={"zonal_period_accounting": (_zonal_accounting(0),)},
            full_rows={"network_solver_diagnostics": _solver_diagnostics(0)},
            run_context_sha256=RUN_CONTEXT_SHA256,
            year_context_sha256=YEAR_CONTEXT_SHA256,
        )
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(batch)
            ledger.close()

            validation = validate_market_ledger_file(database)
            self.assertTrue(validation["valid"], validation)
            with closing(sqlite3.connect(database)) as connection:
                _, evidence = market_ledger_module._database_period_projections(
                    connection,
                    year=2025,
                    period=0,
                    trace_level="full",
                )
            diagnostics = evidence["full_rows"]["network_solver_diagnostics"]
            self.assertEqual([row["presolve"] for row in diagnostics], [True] * 3)
            self.assertTrue(
                all(type(row["presolve"]) is bool for row in diagnostics)
            )

    def test_full_trace_signed_zero_bid_prices_round_trip_through_v8_integrity(self):
        batch = build_market_period_batch(
            period=_period(0),
            full_rows={
                "orders": (
                    OrderLedgerRow(
                        "order-0", 2025, 0, "ahead", "solar", "vre",
                        "supply", -0.0, 5.0, 5.0, "accepted", "cleared",
                        0.0, 0.0,
                    ),
                ),
                "redispatch_settlement": (
                    RedispatchSettlementRow(
                        "bid-0", 2025, 0, "agent-0", "solar", "GB",
                        "vre", "down", 1.0, 0.0, -0.0, 0.0,
                        "accepted", "cleared",
                    ),
                ),
            },
            run_context_sha256=RUN_CONTEXT_SHA256,
            year_context_sha256=YEAR_CONTEXT_SHA256,
        )
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(batch)
            ledger.close()

            validation = validate_market_ledger_file(database)
            self.assertTrue(validation["valid"], validation)

    def test_float_canonicalisation_preserves_nonzero_negative_bid_price(self):
        canonical = market_ledger_module._canonical_row_mapping(
            RedispatchSettlementRow,
            {"bid_price_gbp_per_mwh": -0.000001},
        )
        self.assertEqual(canonical["bid_price_gbp_per_mwh"], -0.000001)
        self.assertLess(canonical["bid_price_gbp_per_mwh"], 0.0)

    def test_integer_contract_rejects_lossy_coercions(self):
        canonical = market_ledger_module._canonical_row_mapping(
            NetworkSolverDiagnosticRow, {"nonzero_term_count": 2}
        )
        self.assertEqual(canonical["nonzero_term_count"], 2)
        self.assertIs(type(canonical["nonzero_term_count"]), int)
        for invalid in (True, 2.5, "2", float("nan"), float("inf"), -float("inf")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                market_ledger_module._canonical_row_mapping(
                    NetworkSolverDiagnosticRow,
                    {"nonzero_term_count": invalid},
                )

    def test_boolean_contract_rejects_noncanonical_source_values(self):
        for value in (True, False):
            with self.subTest(writer=value):
                canonical = market_ledger_module._canonical_row_mapping(
                    NetworkSolverDiagnosticRow, {"presolve": value}
                )
                self.assertIs(canonical["presolve"], value)
        for invalid in (0, 1, "true", None):
            with self.subTest(writer_invalid=invalid), self.assertRaises(ValueError):
                market_ledger_module._canonical_row_mapping(
                    NetworkSolverDiagnosticRow, {"presolve": invalid}
                )
        for value, expected in ((0, False), (1, True)):
            with self.subTest(sqlite=value):
                canonical = market_ledger_module._canonical_database_row_mapping(
                    NetworkSolverDiagnosticRow, {"presolve": value}
                )
                self.assertIs(canonical["presolve"], expected)
        for invalid in (True, False, -1, 2, 0.0, 1.0, "1", None):
            with self.subTest(sqlite_invalid=invalid), self.assertRaises(ValueError):
                market_ledger_module._canonical_database_row_mapping(
                    NetworkSolverDiagnosticRow, {"presolve": invalid}
                )

    def test_required_float_contract_rejects_boolean_and_nonfinite_values(self):
        canonical = market_ledger_module._canonical_row_mapping(
            PeriodLedgerRow, {"export_mwh": 0}
        )
        self.assertEqual(canonical["export_mwh"], 0.0)
        self.assertIs(type(canonical["export_mwh"]), float)
        for invalid in (True, float("nan"), float("inf"), -float("inf")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                market_ledger_module._canonical_row_mapping(
                    PeriodLedgerRow, {"export_mwh": invalid}
                )

    def test_nullable_float_contract_preserves_none_and_canonicalises_numbers(self):
        absent = market_ledger_module._canonical_row_mapping(
            NetworkSolverDiagnosticRow, {"ipm_optimality_tolerance": None}
        )
        self.assertIsNone(absent["ipm_optimality_tolerance"])
        for value, expected in ((0, 0.0), (1, 1.0), (1e-9, 1e-9)):
            with self.subTest(value=value):
                canonical = market_ledger_module._canonical_row_mapping(
                    NetworkSolverDiagnosticRow,
                    {"ipm_optimality_tolerance": value},
                )
                self.assertEqual(canonical["ipm_optimality_tolerance"], expected)
                self.assertIs(
                    type(canonical["ipm_optimality_tolerance"]), float
                )

    def test_nullable_float_contract_rejects_boolean_and_nonfinite_values(self):
        for invalid in (True, float("nan"), float("inf"), -float("inf")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                market_ledger_module._canonical_row_mapping(
                    NetworkSolverDiagnosticRow,
                    {"ipm_optimality_tolerance": invalid},
                )

    def test_fractional_integer_tamper_fails_full_trace_integrity(self):
        batch = build_market_period_batch(
            period=_period(0),
            common_rows={"zonal_period_accounting": (_zonal_accounting(0),)},
            full_rows={"network_solver_diagnostics": _solver_diagnostics(0)},
            run_context_sha256=RUN_CONTEXT_SHA256,
            year_context_sha256=YEAR_CONTEXT_SHA256,
        )
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(batch)
            ledger.close()
            self.assertTrue(validate_market_ledger_file(database)["valid"])

            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE network_solver_diagnostics "
                    "SET nonzero_term_count=2.5 "
                    "WHERE year=2025 AND period=0 "
                    "AND phase_id='primary_bid_cost'"
                )
                raw = connection.execute(
                    "SELECT nonzero_term_count, typeof(nonzero_term_count) "
                    "FROM network_solver_diagnostics "
                    "WHERE year=2025 AND period=0 "
                    "AND phase_id='primary_bid_cost'"
                ).fetchone()
                connection.commit()
            self.assertEqual(raw, (2.5, "real"))

            validation = validate_market_ledger_file(database)
            self.assertFalse(validation["valid"], validation)
            self.assertTrue(
                any(
                    "projection" in error or "validation_failed" in error
                    for error in validation["errors"]
                ),
                validation,
            )

    def test_real_field_tamper_at_one_millionth_still_fails_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(0, include_order=False))
            ledger.close()
            self.assertTrue(validate_market_ledger_file(database)["valid"])

            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE period_summary SET export_mwh=0.000001 "
                    "WHERE year=2025 AND period=0"
                )
                connection.commit()

            validation = validate_market_ledger_file(database)
            self.assertFalse(validation["valid"], validation)
            self.assertTrue(
                any(
                    error.startswith(
                        "period_integrity_science_projection_mismatch:2025:0"
                    )
                    for error in validation["errors"]
                ),
                validation,
            )

    def test_validator_recomputes_every_period_chain_and_stored_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(0, include_order=False))
            ledger.record_period_batch(_batch(1, include_order=False))
            ledger.close()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE period_integrity SET previous_science_hash=? "
                    "WHERE year=2025 AND period=1",
                    ("c" * 64,),
                )
                connection.execute(
                    "UPDATE dispatch_summary SET accepted_dispatch_mwh=4.5 "
                    "WHERE year=2025 AND period=0 AND technology='solar'"
                )
                connection.commit()
            validation = validate_market_ledger_file(database)
            self.assertFalse(validation["valid"], validation)
            self.assertTrue(
                any(
                    error.startswith("period_integrity_previous_science_mismatch")
                    for error in validation["errors"]
                ),
                validation,
            )
            self.assertTrue(
                any(
                    error.startswith("period_integrity_science_projection_mismatch")
                    for error in validation["errors"]
                ),
                validation,
            )

    def test_validator_rejects_full_only_rows_and_false_annual_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(0, include_order=False))
            ledger.close()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    tuple(asdict(_batch(0, include_order=True).full_rows["orders"][0]).values()),
                )
                connection.execute(
                    "INSERT INTO physical_dispatch VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        2025, 0, "thermal", "ccgt", "generation", 10.0, 10.0,
                        "tampered_after_seal", "final_dispatch",
                    ),
                )
                connection.execute(
                    "UPDATE year_integrity SET row_counts_json=?, trace_coverage_json=? "
                    "WHERE year=2025",
                    (
                        json.dumps({"orders": 0, "physical_dispatch": 0}),
                        json.dumps(
                            {
                                "schema_version": "value.market-trace-coverage/v1",
                                "trace_level": "full",
                                "common_summary": True,
                                "full_detail": True,
                            }
                        ),
                    ),
                )
                connection.commit()
            validation = validate_market_ledger_file(database)
            self.assertFalse(validation["valid"], validation)
            self.assertTrue(
                any(error.startswith("summary_contains_full_only_rows:2025:0:orders") for error in validation["errors"]),
                validation,
            )
            self.assertTrue(
                any(error.startswith("summary_contains_full_only_rows:2025:0:physical_dispatch") for error in validation["errors"]),
                validation,
            )
            self.assertIn("year_integrity_row_counts_mismatch:2025", validation["errors"])
            self.assertIn("year_integrity_trace_coverage_mismatch:2025", validation["errors"])

    def test_validator_rejects_off_v8_with_full_only_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(0, include_order=False))
            ledger.close()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE metadata SET value='off' WHERE key='trace_level'"
                )
                connection.execute(
                    "INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    tuple(asdict(_batch(0, include_order=True).full_rows["orders"][0]).values()),
                )
                connection.commit()
            validation = validate_market_ledger_file(database)
            self.assertFalse(validation["valid"], validation)
            self.assertIn("v8_trace_level_unsupported:off", validation["errors"])
            self.assertTrue(
                any(error.startswith("off_contains_full_only_rows:2025:0:orders") for error in validation["errors"]),
                validation,
            )

    def test_reliability_rows_are_sealed_into_annual_evidence_identity(self):
        event_a = ReliabilityEventRow(
            "observed-2025-0-0", 2025, 0, 0, 1, 0.5, 1.0,
            '["Z1"]', 1.0,
            "observed_loss_of_load_chronology_not_statistical_lole",
        )
        event_b = replace(event_a, unserved_mwh=2.0, maximum_deficit_mwh=2.0)
        with tempfile.TemporaryDirectory() as folder:
            roots = []
            for name, event in (("a", event_a), ("b", event_b)):
                ledger = SQLiteMarketLedger(
                    Path(folder) / name / "market.sqlite", trace_level="summary"
                )
                ledger.record_period_batch(_batch(0, include_order=False))
                ledger.record_reliability_events((event,))
                metadata = ledger.close()
                roots.append(metadata["evidence_root_by_year"]["2025"])
                self.assertEqual(metadata["rows"]["reliability_event"], 1)
            self.assertNotEqual(roots[0], roots[1])

    def test_reliability_rows_roll_back_when_annual_seal_fails(self):
        event = ReliabilityEventRow(
            "observed-2025-0-0", 2025, 0, 0, 1, 0.5, 1.0,
            '["Z1"]', 1.0,
            "observed_loss_of_load_chronology_not_statistical_lole",
        )
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(
                Path(folder) / "market.sqlite", trace_level="summary"
            )
            ledger.record_period_batch(_batch(0, include_order=False))
            with patch(
                "gridform_core.market_ledger.seal_year",
                side_effect=RuntimeError("injected annual seal failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "annual seal failure"):
                    ledger.record_reliability_events((event,))
            count = ledger.connection.execute(
                "SELECT COUNT(*) FROM reliability_event WHERE year=2025"
            ).fetchone()[0]
            complete = ledger.connection.execute(
                "SELECT complete FROM year_integrity WHERE year=2025"
            ).fetchone()[0]
            self.assertEqual(count, 0)
            self.assertEqual(complete, 0)
            ledger.close()

    def test_table_roles_are_versioned_disjoint_and_fail_closed_twice(self):
        role_version = getattr(market_ledger_module, "TABLE_ROLE_SCHEMA_VERSION", None)
        common_tables = getattr(market_ledger_module, "COMMON_TABLES", None)
        full_tables = getattr(market_ledger_module, "FULL_ONLY_TABLES", None)
        self.assertEqual(role_version, "value.market-table-roles/v1")
        self.assertIsInstance(common_tables, frozenset)
        self.assertIsInstance(full_tables, frozenset)
        self.assertTrue(common_tables.isdisjoint(full_tables))
        base = _batch(0, include_order=True)
        overlapping = full_tables | {next(iter(common_tables))}
        with patch.object(
            market_ledger_module, "FULL_ONLY_TABLES", overlapping
        ):
            with self.assertRaisesRegex(ValueError, "overlaps"):
                replace(base)
        for table in sorted(full_tables):
            with self.subTest(table=table, role="common"):
                with self.assertRaisesRegex(ValueError, "full-only"):
                    replace(base, common_rows={table: ()})
        for table in sorted(common_tables):
            with self.subTest(table=table, role="full"):
                with self.assertRaisesRegex(ValueError, "common table"):
                    replace(base, full_rows={table: ()})

        corrupted = _batch(0, include_order=True)
        object.__setattr__(
            corrupted, "common_rows", MappingProxyType({"orders": ()})
        )
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(
                Path(folder) / "market.sqlite", trace_level="summary"
            )
            with self.assertRaisesRegex(ValueError, "full-only"):
                ledger.record_period_batch(corrupted)
            ledger.close()

    def test_caller_cannot_inject_trace_detail_into_science_projection(self):
        base = _batch(0, include_order=True)
        injected = dict(base.science_payload)
        injected["orders"] = [{"order_id": "trace-dependent"}]
        with self.assertRaisesRegex(ValueError, "science_payload"):
            replace(base, science_payload=injected)

    def test_all_bundle_profiles_include_authoritative_v8_and_contexts(self):
        required = {
            "model-output/market/market.sqlite",
            "model-output/market/metadata.json",
            "model-output/market/index.json",
            "model-output/market/context/run-context.json",
            "model-output/market/context/year-2025.json",
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "run-a"
            market = root / "model-output" / "market"
            context = market / "context"
            context.mkdir(parents=True)
            (context / "run-context.json").write_text(
                json.dumps({"sha256": RUN_CONTEXT_SHA256}), encoding="utf-8"
            )
            (context / "year-2025.json").write_text(
                json.dumps({"sha256": YEAR_CONTEXT_SHA256}), encoding="utf-8"
            )
            ledger = SQLiteMarketLedger(market / "market.sqlite", trace_level="summary")
            ledger.record_period_batch(_batch(0, include_order=False))
            ledger.close()
            for profile in (
                "compact_results", "complete_audit", "checkpoint_capable"
            ):
                archive = Path(folder) / f"{profile}.zip"
                manifest = export_run_bundle(root, archive, profile=profile)
                included = {str(row["path"]) for row in manifest["files"]}
                self.assertTrue(required.issubset(included), (profile, included))
                self.assertEqual(len(manifest["market_ledgers"]), 1)
                with zipfile.ZipFile(archive) as bundle:
                    self.assertTrue(required.issubset(bundle.namelist()))

    def test_redispatch_summary_uses_physical_cost_and_reconciles_zonal_total(self):
        builder = getattr(staged_psm_module, "_build_redispatch_summary_rows", None)
        self.assertIsNotNone(builder)
        if builder is None:
            return
        bids = (
            FlexibilityBid(
                "up", "agent-up", "asset-up", "ccgt", "Z1", "p0", "up",
                2.0, 100.0, 0.0, 30.0, "n", {},
                extensions={"available_mwh": 2.0},
            ),
            FlexibilityBid(
                "down", "agent-down", "asset-down", "wind", "Z2", "p0", "down",
                1.0, 80.0, 1.0, 20.0, "n", {},
                extensions={"available_mwh": 1.0},
            ),
        )
        accepted = (
            AcceptedAdjustment(
                "up", "agent-up", "asset-up", "Z1", 2.0, 100.0, 200.0,
                "accepted",
            ),
            AcceptedAdjustment(
                "down", "agent-down", "asset-down", "Z2", -1.0, 80.0, -80.0,
                "accepted",
            ),
        )
        rows = builder(
            year=2025,
            period=0,
            bids=bids,
            accepted_adjustments=accepted,
            ahead_resource_cost_gbp=100.0,
            blackout_resource_cost_gbp=0.0,
            zonal_resource_cost_gbp=140.0,
        )
        by_direction = {row.direction: row for row in rows}
        self.assertEqual(by_direction["up"].accepted_delta_mwh, 2.0)
        self.assertEqual(by_direction["up"].resource_cost_gbp, 60.0)
        self.assertEqual(by_direction["down"].accepted_delta_mwh, 1.0)
        self.assertEqual(by_direction["down"].resource_cost_gbp, -20.0)
        self.assertEqual(sum(row.resource_cost_gbp for row in rows), 40.0)

    def test_summary_and_full_share_science_root_but_not_evidence_root(self):
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder)
            metadata = {}
            counts = {}
            for trace_level in ("summary", "full"):
                market_root = run_root / trace_level / "market"
                ledger = SQLiteMarketLedger(
                    market_root / "market.sqlite", trace_level=trace_level
                )
                for period in range(2):
                    ledger.record_period_batch(
                        _batch(period, include_order=True)
                    )
                metadata[trace_level] = ledger.close()
                counts[trace_level] = metadata[trace_level]["rows"]
                validation = validate_market_ledger_file(
                    market_root / "market.sqlite"
                )
                self.assertTrue(validation["valid"], validation)

            summary_meta = metadata["summary"]
            full_meta = metadata["full"]
            summary_counts = counts["summary"]
            full_counts = counts["full"]
            self.assertEqual(
                summary_meta["schema_version"], "value.market-ledger/v8"
            )
            self.assertEqual(
                summary_meta["science_root_by_year"],
                full_meta["science_root_by_year"],
            )
            self.assertNotEqual(
                summary_meta["evidence_root_by_year"],
                full_meta["evidence_root_by_year"],
            )
            self.assertEqual(summary_counts["orders"], 0)
            self.assertGreater(full_counts["orders"], 0)
            self.assertEqual(summary_counts["dispatch_summary"], 4)
            self.assertEqual(full_counts["dispatch_summary"], 4)
            self.assertFalse(
                (run_root / "summary" / "market" / "staged-market.jsonl").exists()
            )
            self.assertFalse(
                (run_root / "full" / "market" / "staged-market.jsonl").exists()
            )

    def test_period_batch_failure_rolls_back_rows_and_hash_state(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(_batch(0, include_order=True))
            before = ledger.connection.execute(
                "SELECT science_root, evidence_root, period_count "
                "FROM year_integrity WHERE year=2025"
            ).fetchone()

            def fail_after_first_common_table(table: str) -> None:
                if table == "dispatch_summary":
                    raise RuntimeError("injected period failure")

            with patch.object(
                ledger,
                "_after_period_batch_table_insert",
                side_effect=fail_after_first_common_table,
            ):
                with self.assertRaisesRegex(RuntimeError, "injected period failure"):
                    ledger.record_period_batch(_batch(1, include_order=True))

            after = ledger.connection.execute(
                "SELECT science_root, evidence_root, period_count "
                "FROM year_integrity WHERE year=2025"
            ).fetchone()
            self.assertEqual(after, before)
            for table in (
                "period_summary", "dispatch_summary", "storage_summary",
                "redispatch_summary", "orders", "period_integrity",
            ):
                count = ledger.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE year=2025 AND period=1"
                ).fetchone()[0]
                self.assertEqual(count, 0, table)
            ledger.close()

    def test_v4_through_v7_are_queryable_and_remain_byte_identical(self):
        for version in ("v4", "v5", "v6", "v7"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as folder:
                database = Path(folder) / "market.sqlite"
                _write_legacy_fixture(database, version)
                before = _sha256_file(database)
                validation = validate_market_ledger_file(database)
                page = query_market_table(
                    database, "period_summary", year=2025, limit=1
                )
                with self.assertRaisesRegex(InvariantError, "read-only"):
                    SQLiteMarketLedger(database, trace_level="summary")
                self.assertTrue(validation["valid"], validation)
                self.assertEqual(
                    validation["schema_version"], f"value.market-ledger/{version}"
                )
                self.assertEqual(page["total"], 1)
                self.assertEqual(page["items"][0]["period"], 0)
                self.assertEqual(_sha256_file(database), before)


if __name__ == "__main__":
    unittest.main()
