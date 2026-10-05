from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import server
from tests.local_api_harness import start_local_api
import gridform_core.zonal_results as zonal_results_module

from gridform_core.market_ledger import (
    BoundaryPeriodLedgerRow,
    NetworkSolverDiagnosticRow,
    RedispatchSettlementRow,
    ReliabilityEventRow,
    SQLiteMarketLedger,
    SolverDeclarationLinkRow,
    VRECurtailmentDetailRow,
    VRECurtailmentPeriodRow,
    ZonalAccountingLedgerRow,
    ZonalDemandAlignmentLedgerRow,
    ZonePeriodLedgerRow,
    ZonalResourceDispatchRow,
    create_market_ledger,
    validate_market_ledger_file,
)
from gridform_core.zonal_results import (
    build_solver_validation_summary,
    export_zonal_results,
    query_zonal_annual_brief,
    query_zonal_results,
    zonal_workspace_capabilities,
)
from gridform_core.zonal_solver_contract import (
    SolverStackIdentity,
    solver_stack_identity,
)


ROOT = Path(__file__).resolve().parents[1]


def _solver_rows(period: int) -> tuple[NetworkSolverDiagnosticRow, ...]:
    rows = []
    for phase_id, unit, validated, absolute in (
        ("primary_bid_cost", "GBP", 0.01, 0.10),
        ("secondary_schedule_deviation", "MWh", 0.001, 0.01),
        ("physical_throughput", "MWh", 0.001, 0.01),
    ):
        is_causal = period == 1 and phase_id == "secondary_schedule_deviation"
        tolerance = 0.002 if is_causal else validated * 0.01
        rows.append(NetworkSolverDiagnosticRow(
            run_id="zonal-run",
            year=2025,
            period=period,
            period_id=f"2025:{period}",
            phase_id=phase_id,
            module_id="value-zonal-redispatch-balancing",
            module_version="1.2.0",
            solver_contract_version="value.zonal-lexicographic/v2",
            scipy_version="1.8.1",
            highs_identity="scipy-embedded-highs:" + "e" * 64,
            highs_binary_sha256="e" * 64,
            method="highs-ds",
            presolve=True,
            primal_feasibility_tolerance=1e-9,
            dual_feasibility_tolerance=1e-9,
            ipm_optimality_tolerance=None,
            objective_unit=unit,
            optimum=10.0,
            achieved_final_value=10.0,
            degradation=0.0,
            computed_tolerance=tolerance,
            warning_ceiling=validated * 0.1,
            validated_ceiling=validated,
            absolute_ceiling=absolute,
            nonzero_term_count=2,
            absolute_term_scale=10.0,
            validation_class=(
                "COMPLETED_WITH_NUMERICAL_WARNING" if is_causal else "GO"
            ),
            error_code=None,
            declared_input_sha256=("c" if period == 0 else "d") * 64,
        ))
    return tuple(rows)


def _accounting(period: int) -> SimpleNamespace:
    return SimpleNamespace(
        year=2025,
        period=period,
        period_id=f"2025:{period}",
        system_resource_cost_gbp=120.0,
        transmission_constraint_resource_cost_gbp=20.0,
        national_settlement_gbp=500.0,
        redispatch_settlement_gbp=20.0,
        policy_transfer_gbp=3.0,
        perfect_forecast_resource_cost_gbp=90.0,
        realised_copperplate_resource_cost_gbp=100.0,
        zonal_resource_cost_gbp=120.0,
        forecast_error_cost_gbp=10.0,
        total_deviation_cost_gbp=30.0,
        blackout_mwh=1.0 if period == 1 else 0.0,
        counterfactual_realised_input_sha256=("a" if period == 0 else "b") * 64,
        accounting_status="reconciled",
    )


def _curtailment_period(period: int) -> VRECurtailmentPeriodRow:
    if period == 0:
        # 10 available - 6 final = 2 economic + 2 redispatch-added = 4.
        values = (8.0, 8.0, 6.0, 2.0, 2.0, 0.0, 4.0)
    else:
        # 10 available - 10 final = 3 economic - 3 redispatch-avoided = 0.
        values = (7.0, 7.0, 10.0, 3.0, 0.0, 3.0, 0.0)
    perfect, copperplate, zonal, economic, added, avoided, total = values
    return VRECurtailmentPeriodRow(
        2025,
        period,
        f"2025:{period}",
        10.0,
        perfect,
        copperplate,
        zonal,
        economic,
        0.0,
        0.0,
        added,
        avoided,
        added - avoided,
        total,
        total / 10.0,
        0.0,
        1e-7,
        "reconciled",
        ("a" if period == 0 else "b") * 64,
        "value.pro-rata-technology-bid-tranche/v1",
    )


def _curtailment_detail(period: int) -> VRECurtailmentDetailRow:
    row = _curtailment_period(period)
    return VRECurtailmentDetailRow(
        row.year,
        row.period,
        row.period_id,
        f"vre-{period}",
        f"owner-{period}",
        "north" if period == 0 else "south",
        "Onshore wind" if period == 0 else "Solar",
        f"tranche-{period}",
        row.realised_available_vre_mwh,
        row.perfect_reference_dispatch_mwh,
        row.copperplate_reference_dispatch_mwh,
        row.zonal_final_dispatch_mwh,
        row.economic_curtailment_mwh,
        row.forecast_added_curtailment_mwh,
        row.forecast_avoided_curtailment_mwh,
        row.redispatch_added_curtailment_mwh,
        row.redispatch_avoided_curtailment_mwh,
        row.redispatch_net_impact_mwh,
        row.total_curtailment_mwh,
        "deterministic_reference_allocation",
    )


def _write_fixture(path: Path, trace_level: str) -> None:
    ledger = create_market_ledger(
        path,
        trace_level,
        semantic_metadata={
            "run_id": "zonal-run",
            "run_parent_id": "",
            "data_pack_id": "gb-data",
            "network_pack_id": "gb-zones-v1",
            "zonal_demand_mode": "scenario_scaled_zonal_shares",
            "module_ids": [
                "value-staged-bid-at-cost-psm",
                "value-zonal-redispatch-balancing",
            ],
            "period_hours": 0.5,
            "network_semantics": "lossless_computational_transport_with_etys_cutsets",
        },
    )
    for period, utilisation in ((0, 1.0), (1, 0.5)):
        ledger.record_zonal_accounting(
            (ZonalAccountingLedgerRow.from_accounting(_accounting(period)),)
        )
        ledger.record_vre_curtailment_periods((_curtailment_period(period),))
        ledger.record_vre_curtailment_details((_curtailment_detail(period),))
        ledger.record_zones((
            ZonePeriodLedgerRow(2025, period, "north", 5.0, 7.0, 6.0, -1.0, 0.0, 1.0),
            ZonePeriodLedgerRow(
                2025, period, "south", 5.0, 3.0, 3.0, 0.0,
                1.0 if period == 1 else 0.0, -1.0,
            ),
        ))
        ledger.record_boundaries((BoundaryPeriodLedgerRow(
            2025, period, "B1", 2.0 if period == 0 else 1.0,
            2.0, 3.0, utilisation, 0.0,
            "diagnostic_marginal_value_in_accepted_bid_objective_not_zonal_price_or_cash_cost",
        ),))
        ledger.record_zonal_resources((ZonalResourceDispatchRow(
            2025, period, "gas", "gas-owner", "south", "CCGT",
            2.0, 3.0, 1.0, 0.0, 0.0, 0.0, 120.0,
        ),))
        ledger.record_redispatch_settlements((RedispatchSettlementRow(
            f"bid-{period}", 2025, period, "gas-owner", "gas", "south",
            "CCGT", "up", 1.0, 1.0, 25.0, 25.0, "accepted",
            "zonal_redispatch_up",
        ),))
        ledger.record_solver_links((SolverDeclarationLinkRow(
            2025, period, ("c" if period == 0 else "d") * 64,
            "market/staged-market.jsonl",
            f"market/zonal-redispatch/{period}-diagnostics.json",
            None, "optimal",
        ),))
        ledger.record_network_solver_diagnostics(_solver_rows(period))
    ledger.record_reliability_events((ReliabilityEventRow(
        "observed-2025-1-1", 2025, 1, 1, 1, 0.5, 1.0,
        json.dumps(["south"]), 1.0,
        "observed_loss_of_load_chronology_not_statistical_lole",
    ),))
    ledger.record_zonal_demand_alignment((
        ZonalDemandAlignmentLedgerRow(
            2025, 0, "2025:0", "scenario_scaled_zonal_shares",
            10.0, 11.0, 8.0, 1.25, 10.0, 0.0,
        ),
        ZonalDemandAlignmentLedgerRow(
            2025, 1, "2025:1", "scenario_scaled_zonal_shares",
            12.0, 13.0, 12.0, 1.0, 12.0, 0.0,
        ),
    ))
    ledger.close()


def _directory_snapshot(path: Path) -> dict[str, tuple[int, int, str]]:
    return {
        item.name: (
            item.stat().st_size,
            item.stat().st_mtime_ns,
            hashlib.sha256(item.read_bytes()).hexdigest(),
        )
        for item in sorted(path.iterdir())
        if item.is_file()
    }


def _write_v5_fixture(path: Path) -> Path:
    schema = ROOT / "gridform_core" / "data" / "contracts" / "market-ledger-v5.schema.sql"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
            ("value.market-ledger/v5",),
        )
        connection.executescript(schema.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO zonal_period_summary VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                2025, 0, "2025:0", 120.0, 20.0, 500.0, 20.0, 3.0,
                90.0, 100.0, 120.0, 10.0, 30.0, 2.0, 0.0, 2.0, 4.0,
                0.0, 0.0, "a" * 64, "reconciled",
            ),
        )
        connection.commit()
    return path


def _write_v6_fixture(path: Path) -> Path:
    contracts = ROOT / "gridform_core" / "data" / "contracts"
    row = ZonalAccountingLedgerRow.from_accounting(_accounting(0))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
            ("value.market-ledger/v6",),
        )
        for name in (
            "market-ledger-v5.schema.sql",
            "market-ledger-v6.schema.sql",
        ):
            connection.executescript(
                (contracts / name).read_text(encoding="utf-8")
            )
        connection.execute(
            "INSERT INTO zonal_period_accounting VALUES("
            + ",".join("?" for _ in range(16))
            + ")",
            tuple(vars(row).values()),
        )
        connection.commit()
    return path


class Prompt102ZonalResultsApiTests(unittest.TestCase):
    def test_public_validation_and_solver_query_are_immutable_on_wal_database(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "market.sqlite"
            _write_fixture(database, "summary")
            self.assertFalse(database.with_name("market.sqlite-wal").exists())
            self.assertFalse(database.with_name("market.sqlite-shm").exists())
            before = _directory_snapshot(root)

            validation = validate_market_ledger_file(database)
            summary = zonal_results_module.query_solver_validation_summary(database)

            after = _directory_snapshot(root)

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual(summary["row_count"], 6)
        self.assertEqual(after, before)
        self.assertNotIn("market.sqlite-wal", after)
        self.assertNotIn("market.sqlite-shm", after)

    def test_public_readers_snapshot_committed_nonzero_wal_without_touching_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "market.sqlite"
            _write_fixture(database, "summary")
            writer = sqlite3.connect(database)
            try:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute(
                    "UPDATE network_solver_diagnostics "
                    "SET computed_tolerance=0.0002 "
                    "WHERE phase_id='primary_bid_cost'"
                )
                writer.commit()
                wal = database.with_name("market.sqlite-wal")
                self.assertTrue(wal.is_file())
                self.assertGreater(wal.stat().st_size, 0)
                before = _directory_snapshot(root)

                validation = validate_market_ledger_file(database)
                summary = zonal_results_module.query_solver_validation_summary(
                    database
                )

                after = _directory_snapshot(root)
            finally:
                writer.close()

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual(
            summary["phases"]["primary_bid_cost"]["max_tolerance"],
            0.0002,
        )
        self.assertEqual(after, before)

    def test_candidate_runtime_identity_is_not_builtin_validated(self) -> None:
        candidate = solver_stack_identity()
        candidate_rows = tuple(
            replace(
                row,
                scipy_version=candidate.scipy_version,
                highs_identity=candidate.highs_identity,
                highs_binary_sha256=candidate.highs_binary_sha256,
            )
            for row in _solver_rows(0)
        )
        unknown_sha = "0" * 64
        if unknown_sha == candidate.highs_binary_sha256:
            unknown_sha = "1" * 64
        unknown_rows = tuple(
            replace(
                row,
                highs_identity=f"scipy-embedded-highs:{unknown_sha}",
                highs_binary_sha256=unknown_sha,
            )
            for row in candidate_rows
        )

        candidate_summary = build_solver_validation_summary(candidate_rows)
        unknown_summary = build_solver_validation_summary(unknown_rows)

        self.assertIs(candidate_summary["solver_validated"], False)
        self.assertEqual(
            candidate_summary["solver_stack_validation_status"],
            "solver_stack_not_yet_validated",
        )
        self.assertIs(unknown_summary["solver_validated"], False)
        self.assertEqual(
            unknown_summary["solver_stack_validation_status"],
            "solver_stack_not_yet_validated",
        )

    def test_runtime_binary_replacement_cannot_self_approve(self) -> None:
        replacement_sha = "f" * 64
        replacement = SolverStackIdentity(
            scipy_version="1.8.1",
            highs_extension_path="replacement-highs.pyd",
            highs_binary_sha256=replacement_sha,
            highs_identity=f"scipy-embedded-highs:{replacement_sha}",
        )
        replacement_rows = tuple(
            replace(
                row,
                scipy_version=replacement.scipy_version,
                highs_identity=replacement.highs_identity,
                highs_binary_sha256=replacement.highs_binary_sha256,
            )
            for row in _solver_rows(0)
        )

        with patch.object(
            zonal_results_module,
            "solver_stack_identity",
            return_value=replacement,
        ):
            summary = build_solver_validation_summary(replacement_rows)

        self.assertIs(summary["solver_validated"], False)
        self.assertEqual(
            summary["solver_stack_validation_status"],
            "solver_stack_not_yet_validated",
        )

    def test_validated_original_registry_entry_does_not_approve_replacement(
        self,
    ) -> None:
        candidate = zonal_results_module.load_solver_validation_registry()[0]
        self.assertEqual(candidate.status, "candidate")
        validated_original = replace(candidate, status="validated")
        replacement_sha = "f" * 64
        self.assertNotEqual(replacement_sha, candidate.highs_binary_sha256)
        replacement = SolverStackIdentity(
            scipy_version=candidate.scipy_version,
            highs_extension_path="replacement-highs.pyd",
            highs_binary_sha256=replacement_sha,
            highs_identity=f"scipy-embedded-highs:{replacement_sha}",
        )
        replacement_rows = tuple(
            replace(
                row,
                module_id=candidate.module_id,
                module_version=candidate.module_version,
                solver_contract_version=candidate.solver_contract_version,
                scipy_version=replacement.scipy_version,
                highs_identity=replacement.highs_identity,
                highs_binary_sha256=replacement.highs_binary_sha256,
            )
            for row in _solver_rows(0)
        )

        with patch.object(
            zonal_results_module,
            "load_solver_validation_registry",
            return_value=(validated_original,),
        ), patch.object(
            zonal_results_module,
            "solver_stack_identity",
            return_value=replacement,
        ):
            summary = build_solver_validation_summary(replacement_rows)

        self.assertIs(summary["solver_validated"], False)
        self.assertEqual(
            summary["solver_stack_validation_status"],
            "solver_stack_not_yet_validated",
        )

    def test_builtin_baseline_requires_explicit_validated_registry_status(
        self,
    ) -> None:
        loader = getattr(
            zonal_results_module,
            "load_solver_validation_registry",
            None,
        )
        self.assertTrue(callable(loader))
        candidate = loader()[0]
        runtime = SolverStackIdentity(
            scipy_version=candidate.scipy_version,
            highs_extension_path="registry-candidate-highs.pyd",
            highs_binary_sha256=candidate.highs_binary_sha256,
            highs_identity=candidate.highs_identity,
        )
        rows = tuple(
            replace(
                row,
                module_id=candidate.module_id,
                module_version=candidate.module_version,
                solver_contract_version=candidate.solver_contract_version,
                scipy_version=candidate.scipy_version,
                highs_identity=candidate.highs_identity,
                highs_binary_sha256=candidate.highs_binary_sha256,
            )
            for row in _solver_rows(0)
        )

        with patch.object(
            zonal_results_module,
            "solver_stack_identity",
            return_value=runtime,
        ):
            with patch.object(
                zonal_results_module,
                "load_solver_validation_registry",
                return_value=(candidate,),
            ):
                candidate_summary = build_solver_validation_summary(rows)
            with patch.object(
                zonal_results_module,
                "load_solver_validation_registry",
                return_value=(replace(candidate, status="validated"),),
            ):
                validated_summary = build_solver_validation_summary(rows)

        self.assertIs(candidate_summary["solver_validated"], False)
        self.assertEqual(
            candidate_summary["solver_stack_validation_status"],
            "solver_stack_not_yet_validated",
        )
        self.assertIs(validated_summary["solver_validated"], True)
        self.assertEqual(
            validated_summary["solver_stack_validation_status"],
            "builtin_validated_baseline",
        )

    def test_historical_validated_stack_is_checked_from_stored_identity_not_current_runtime(self) -> None:
        candidate = zonal_results_module.load_solver_validation_registry()[0]
        rows = tuple(
            replace(
                row,
                module_id=candidate.module_id,
                module_version=candidate.module_version,
                solver_contract_version=candidate.solver_contract_version,
                scipy_version=candidate.scipy_version,
                highs_identity=candidate.highs_identity,
                highs_binary_sha256=candidate.highs_binary_sha256,
            )
            for row in _solver_rows(0)
        )
        current_sha = "f" * 64
        current_runtime = SolverStackIdentity(
            scipy_version="9.9.9",
            highs_extension_path="current-runtime-highs.pyd",
            highs_binary_sha256=current_sha,
            highs_identity=f"scipy-embedded-highs:{current_sha}",
        )

        with patch.object(
            zonal_results_module,
            "load_solver_validation_registry",
            return_value=(replace(candidate, status="validated"),),
        ), patch.object(
            zonal_results_module,
            "solver_stack_identity",
            return_value=current_runtime,
        ):
            summary = build_solver_validation_summary(rows)

        self.assertIs(summary["solver_validated"], True)
        self.assertEqual(
            summary["solver_stack_validation_status"],
            "builtin_validated_baseline",
        )

    def test_read_side_rejects_incomplete_inconsistent_and_orphan_solver_groups(
        self,
    ) -> None:
        mutations = {
            "incomplete_phase_group": (
                "DELETE FROM network_solver_diagnostics "
                "WHERE period=0 AND phase_id='physical_throughput'",
                "solver_diagnostics_incomplete_phase_group",
            ),
            "inconsistent_period_identity": (
                "UPDATE network_solver_diagnostics SET period_id='wrong' "
                "WHERE period=0 AND phase_id='physical_throughput'",
                "solver_diagnostics_inconsistent_period_identity",
            ),
            "inconsistent_stack_identity": (
                "UPDATE network_solver_diagnostics SET module_version='9.9.9' "
                "WHERE period=0 AND phase_id='physical_throughput'",
                "solver_diagnostics_inconsistent_stack_identity",
            ),
            "inconsistent_input_identity": (
                "UPDATE network_solver_diagnostics "
                "SET declared_input_sha256='ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff' "
                "WHERE period=0 AND phase_id='physical_throughput'",
                "solver_diagnostics_inconsistent_input_identity",
            ),
            "missing_completed_period": (
                "DELETE FROM network_solver_diagnostics WHERE period=1",
                "solver_diagnostics_missing_completed_period",
            ),
            "orphan_period": (
                "DELETE FROM zonal_period_accounting WHERE period=1",
                "solver_diagnostics_orphan_period",
            ),
        }
        for name, (statement, expected_error) in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                database = Path(temporary) / "market.sqlite"
                _write_fixture(database, "summary")
                with closing(sqlite3.connect(database)) as connection:
                    connection.execute(statement)
                    connection.commit()

                validation = validate_market_ledger_file(database)
                summary = zonal_workspace_capabilities(database)[
                    "solver_validation_summary"
                ]

                self.assertIs(validation["valid"], False)
                self.assertTrue(
                    any(
                        str(error).startswith(expected_error)
                        for error in validation["errors"]
                    ),
                    validation["errors"],
                )
                self.assertIs(summary["solver_validated"], False)
                self.assertEqual(summary["evidence_status"], "invalid")
                self.assertTrue(
                    any(
                        str(error).startswith(expected_error)
                        for error in summary["evidence_errors"]
                    ),
                    summary["evidence_errors"],
                )

    def test_read_side_recomputes_degradation_identity_from_unitful_values(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "market.sqlite"
            _write_fixture(database, "summary")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("PRAGMA ignore_check_constraints=ON")
                connection.execute(
                    "UPDATE network_solver_diagnostics "
                    "SET achieved_final_value=optimum + computed_tolerance * 2, "
                    "degradation=0.0 "
                    "WHERE period=0 AND phase_id='primary_bid_cost'"
                )
                connection.commit()

            validation = validate_market_ledger_file(database)
            summary = zonal_workspace_capabilities(database)[
                "solver_validation_summary"
            ]

        expected = "solver_diagnostics_degradation_identity_mismatch"
        self.assertIs(validation["valid"], False)
        self.assertTrue(
            any(str(error).startswith(expected) for error in validation["errors"]),
            validation["errors"],
        )
        self.assertEqual(summary["evidence_status"], "invalid")
        self.assertTrue(
            any(
                str(error).startswith(expected)
                for error in summary["evidence_errors"]
            ),
            summary["evidence_errors"],
        )

    def test_read_side_rejects_forged_lock_classes_and_degradation_above_tau(
        self,
    ) -> None:
        mutations = (
            (
                "optimum=-5.0, achieved_final_value=-4.998, "
                "degradation=0.002, computed_tolerance=0.001, "
                "validation_class='GO'",
                "solver_diagnostics_degradation_exceeds_computed_tolerance",
            ),
            (
                "validation_class='GO_WITH_NUMERICAL_WARNING'",
                "solver_diagnostics_validation_class_mismatch",
            ),
            (
                "validation_class='COMPLETED_WITH_NUMERICAL_WARNING'",
                "solver_diagnostics_validation_class_mismatch",
            ),
            (
                "computed_tolerance=0.02, "
                "validation_class='GO_WITH_NUMERICAL_WARNING'",
                "solver_diagnostics_validation_class_mismatch",
            ),
            (
                "validation_class='UNKNOWN'",
                "solver_diagnostics_validation_class_unsupported",
            ),
        )
        for assignment, expected in mutations:
            with self.subTest(assignment=assignment):
                with tempfile.TemporaryDirectory() as temporary:
                    database = Path(temporary) / "market.sqlite"
                    _write_fixture(database, "summary")
                    with closing(sqlite3.connect(database)) as connection:
                        connection.execute("PRAGMA ignore_check_constraints=ON")
                        connection.execute(
                            "UPDATE network_solver_diagnostics SET "
                            + assignment
                            + " WHERE period=0 "
                            "AND phase_id='primary_bid_cost'"
                        )
                        connection.commit()

                    validation = validate_market_ledger_file(database)
                    summary = zonal_workspace_capabilities(database)[
                        "solver_validation_summary"
                    ]

                self.assertIs(validation["valid"], False)
                self.assertTrue(
                    any(
                        str(error).startswith(expected)
                        for error in validation["errors"]
                    ),
                    validation["errors"],
                )
                self.assertEqual(summary["evidence_status"], "invalid")
                self.assertNotEqual(summary["annual_status"], "GO")
                self.assertTrue(
                    any(
                        str(error).startswith(expected)
                        for error in summary["evidence_errors"]
                    ),
                    summary["evidence_errors"],
                )

    def test_first_causal_phase_uses_solver_execution_order(self) -> None:
        rows = tuple(
            replace(
                row,
                computed_tolerance=row.validated_ceiling * 2.0,
                validation_class="COMPLETED_WITH_NUMERICAL_WARNING",
            )
            if row.phase_id in {"primary_bid_cost", "physical_throughput"}
            else row
            for row in _solver_rows(0)
        )

        summary = build_solver_validation_summary(reversed(rows))

        self.assertEqual(
            summary["first_causal_period"]["phase_id"], "primary_bid_cost"
        )

    def test_annual_phase_summary_uses_stored_custom_warning_ceiling(self) -> None:
        rows = tuple(
            replace(
                row,
                computed_tolerance=0.0005,
                warning_ceiling=0.0001,
                validation_class="GO_WITH_NUMERICAL_WARNING",
            )
            if row.phase_id == "primary_bid_cost"
            else row
            for row in _solver_rows(0)
        )

        summary = build_solver_validation_summary(rows)

        self.assertEqual(
            summary["phases"]["primary_bid_cost"]
            ["periods_above_warning_fraction"],
            1,
        )

    def test_summary_streams_rows_into_the_task1_aggregator(self) -> None:
        state = {"aggregator_started": False, "eager_consumption": False}

        def guarded_rows():
            for index, row in enumerate(_solver_rows(0)):
                if index and not state["aggregator_started"]:
                    state["eager_consumption"] = True
                yield row

        real_aggregator = zonal_results_module.summarise_solver_diagnostics

        def observing_aggregator(rows):
            state["aggregator_started"] = True
            return real_aggregator(rows)

        with patch.object(
            zonal_results_module,
            "summarise_solver_diagnostics",
            observing_aggregator,
        ):
            build_solver_validation_summary(guarded_rows())

        self.assertIs(state["eager_consumption"], False)

    def test_nonbaseline_solver_stack_is_unvalidated_even_when_physical_rows_are_go(self) -> None:
        rows = []
        for row in _solver_rows(0):
            rows.append(NetworkSolverDiagnosticRow(**{
                **vars(row),
                "method": "highs-ipm",
                "ipm_optimality_tolerance": 1e-9,
            }))

        summary = build_solver_validation_summary(rows)

        self.assertIs(summary["solver_validated"], False)
        self.assertEqual(
            summary["solver_stack_validation_status"],
            "solver_stack_not_yet_validated",
        )
        self.assertEqual(summary["study_status"], "solver_stack_not_yet_validated")

    def test_annual_sql_summary_inherits_first_unvalidated_year_causally(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "market.sqlite"
            _write_fixture(database, "summary")
            rows = tuple(
                NetworkSolverDiagnosticRow(**{
                    **vars(row),
                    "year": 2026,
                    "period_id": "2026:0",
                    "declared_input_sha256": "f" * 64,
                })
                for row in _solver_rows(0)
            )
            with closing(sqlite3.connect(database)) as connection:
                connection.executemany(
                    "INSERT INTO network_solver_diagnostics VALUES("
                    + ",".join("?" for _ in range(29))
                    + ")",
                    [tuple(vars(row).values()) for row in rows],
                )
                connection.execute("""
                    INSERT INTO zonal_period_accounting
                    SELECT 2026, period, '2026:0',
                        system_resource_cost_gbp, network_constraint_cost_gbp,
                        national_settlement_gbp, redispatch_settlement_gbp,
                        policy_transfer_gbp, perfect_forecast_resource_cost_gbp,
                        realised_copperplate_resource_cost_gbp,
                        zonal_resource_cost_gbp, forecast_error_cost_gbp,
                        total_deviation_cost_gbp, blackout_mwh,
                        counterfactual_realised_input_sha256, accounting_status
                    FROM zonal_period_accounting
                    WHERE year=2025 AND period=0
                """)
                connection.commit()
            brief = query_zonal_annual_brief(database)

        first = next(row for row in brief["years"] if row["year"] == 2025)
        second = next(row for row in brief["years"] if row["year"] == 2026)
        self.assertIs(
            first["solver_validation_summary"]["solver_validated"], False
        )
        self.assertIs(
            second["solver_validation_summary"]["solver_validated"], False
        )
        self.assertIs(
            second["solver_validation_summary"]["inherited_unvalidated"], True
        )
        self.assertEqual(
            second["solver_validation_summary"]["first_causal_period"],
            first["solver_validation_summary"]["first_causal_period"],
        )

    def test_v7_annual_brief_uses_gross_sums_and_energy_weighted_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "market.sqlite"
            _write_fixture(database, "full")
            capabilities = zonal_workspace_capabilities(database)
            brief = query_zonal_annual_brief(database)

        self.assertEqual(brief["schema_version"], "value.zonal-annual-brief/v2")
        self.assertEqual(capabilities["network_pack_id"], "gb-zones-v1")
        self.assertEqual(capabilities["attribution_status"], "reconciled")
        self.assertIn("curtailment", capabilities["available_views"])
        self.assertIn("curtailment-detail", capabilities["available_views"])
        annual = brief["years"][0]
        curtailment = annual["vre_curtailment"]
        self.assertEqual(curtailment["redispatch_added_mwh"], 2.0)
        self.assertEqual(curtailment["redispatch_avoided_mwh"], 3.0)
        self.assertEqual(curtailment["redispatch_net_mwh"], -1.0)

        self.assertEqual(curtailment["total_mwh"], 4.0)
        self.assertEqual(curtailment["rate"], 4.0 / 20.0)
        self.assertEqual(
            curtailment["by_zone_technology"],
            [
                {
                    "year": 2025,
                    "zone_id": "north",
                    "technology": "Onshore wind",
                    "available_mwh": 10.0,
                    "economic_mwh": 2.0,
                    "forecast_added_mwh": 0.0,
                    "forecast_avoided_mwh": 0.0,
                    "redispatch_added_mwh": 2.0,
                    "redispatch_avoided_mwh": 0.0,
                    "redispatch_net_mwh": 2.0,
                    "total_mwh": 4.0,
                },
                {
                    "year": 2025,
                    "zone_id": "south",
                    "technology": "Solar",
                    "available_mwh": 10.0,
                    "economic_mwh": 3.0,
                    "forecast_added_mwh": 0.0,
                    "forecast_avoided_mwh": 0.0,
                    "redispatch_added_mwh": 0.0,
                    "redispatch_avoided_mwh": 3.0,
                    "redispatch_net_mwh": -3.0,
                    "total_mwh": 0.0,
                },
            ],
        )
        self.assertEqual(
            curtailment["by_technology"],
            [
                {
                    "year": 2025,
                    "technology": "Onshore wind",
                    "available_mwh": 10.0,
                    "economic_mwh": 2.0,
                    "forecast_added_mwh": 0.0,
                    "forecast_avoided_mwh": 0.0,
                    "redispatch_added_mwh": 2.0,
                    "redispatch_avoided_mwh": 0.0,
                    "redispatch_net_mwh": 2.0,
                    "total_mwh": 4.0,
                },
                {
                    "year": 2025,
                    "technology": "Solar",
                    "available_mwh": 10.0,
                    "economic_mwh": 3.0,
                    "forecast_added_mwh": 0.0,
                    "forecast_avoided_mwh": 0.0,
                    "redispatch_added_mwh": 0.0,
                    "redispatch_avoided_mwh": 3.0,
                    "redispatch_net_mwh": -3.0,
                    "total_mwh": 0.0,
                },
            ],
        )
        self.assertEqual(annual["congested_boundary_periods"], 1)
        self.assertEqual(annual["observed_loss_of_load_hours"], 0.5)
        self.assertEqual(annual["unserved_energy_mwh"], 1.0)

    def test_solver_diagnostics_are_bounded_filtered_and_reconciled_with_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "market.sqlite"
            _write_fixture(database, "full")
            capabilities = zonal_workspace_capabilities(database)
            page = query_zonal_results(database, {
                "view": "solver-diagnostics",
                "run": "zonal-run",
                "year": 2025,
                "period_from": 0,
                "period_to": 1,
                "limit": 1,
            })
            exported = export_zonal_results(
                database,
                {
                    "view": "solver-diagnostics",
                    "run": "zonal-run",
                    "year": 2025,
                    "period_from": 0,
                    "period_to": 1,
                    "limit": 1,
                },
                root / "solver.jsonl",
            )
            sql_row = dict(page["items"][0])
            json_row = json.loads(
                (root / "solver.jsonl").read_text(encoding="utf-8").strip()
            )

        self.assertIn("solver-diagnostics", capabilities["available_views"])
        self.assertEqual(page["total"], 6)
        self.assertEqual(page["items"][0]["period"], 0)
        self.assertEqual(exported["rows"], 1)
        self.assertEqual(json_row, sql_row)
        self.assertEqual(
            capabilities["solver_validation_summary"]["first_causal_period"],
            {
                "year": 2025,
                "period": 1,
                "period_id": "2025:1",
                "phase_id": "secondary_schedule_deviation",
                "validation_class": "COMPLETED_WITH_NUMERICAL_WARNING",
            },
        )
        self.assertIs(
            capabilities["solver_validation_summary"]["solver_validated"], False
        )

        for bad_query in (
            {"view": "solver-diagnostics", "limit": 1001},
            {"view": "solver-diagnostics", "sql": "DROP TABLE metadata"},
            {"view": "solver-diagnostics", "asset_id": "gas"},
            {"view": "solver-diagnostics", "status": "GO"},
        ):
            with self.subTest(query=bad_query), self.assertRaises(ValueError):
                query_zonal_results(database, bad_query)

    def test_reliability_period_window_returns_overlapping_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "market.sqlite"
            _write_fixture(database, "full")
            included = query_zonal_results(database, {
                "view": "reliability", "year": 2025,
                "period_from": 0, "period_to": 1, "limit": 250,
            })
            excluded = query_zonal_results(database, {
                "view": "reliability", "year": 2025,
                "period_from": 2, "period_to": 3, "limit": 250,
            })

        self.assertEqual(included["total"], 1)
        self.assertEqual(included["items"][0]["event_id"], "observed-2025-1-1")
        self.assertEqual(excluded["total"], 0)

    def test_v5_reads_are_byte_preserving_and_avoided_values_remain_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = _write_v5_fixture(root / "market.sqlite")

            def byte_preserving(call):
                before = hashlib.sha256(database.read_bytes()).hexdigest()
                result = call()
                self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)
                return result

            capabilities = byte_preserving(lambda: zonal_workspace_capabilities(database))
            validation = byte_preserving(lambda: validate_market_ledger_file(database))
            brief = byte_preserving(lambda: query_zonal_annual_brief(database))
            page = byte_preserving(
                lambda: query_zonal_results(database, {"view": "period", "limit": 10})
            )
            exported = byte_preserving(
                lambda: export_zonal_results(
                    database, {"view": "period", "limit": 10},
                    root / "legacy.csv", output_format="csv",
                )
            )

        self.assertTrue(validation["valid"])
        self.assertEqual(capabilities["attribution_status"], "legacy_partial")
        legacy = brief["years"][0]["vre_curtailment"]
        self.assertEqual(legacy["attribution_status"], "legacy_partial")
        self.assertIsNone(legacy["forecast_avoided_mwh"])
        self.assertIsNone(legacy["redispatch_avoided_mwh"])
        self.assertIsNone(legacy["redispatch_net_mwh"])
        self.assertEqual(
            legacy["reason_code"],
            "legacy_contract_did_not_measure_avoided_curtailment",
        )
        self.assertEqual(page["total"], 1)
        self.assertEqual(exported["rows"], 1)

    def test_v6_period_reader_is_byte_preserving_and_uses_accounting_table(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = _write_v6_fixture(Path(temporary) / "market.sqlite")
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            capabilities = zonal_workspace_capabilities(database)
            page = query_zonal_results(
                database, {"view": "period", "year": 2025, "limit": 10}
            )
            after = hashlib.sha256(database.read_bytes()).hexdigest()

        self.assertEqual(before, after)
        self.assertEqual(
            capabilities["ledger_schema_version"], "value.market-ledger/v6"
        )
        self.assertEqual(capabilities["years"], [2025])
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["period_id"], "2025:0")

    def test_period_and_detail_views_are_filtered_bounded_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "market.sqlite"
            _write_fixture(database, "summary")
            periods = query_zonal_results(
                database, {"view": "curtailment", "year": 2025, "limit": 1}
            )
            details = query_zonal_results(
                database,
                {
                    "view": "curtailment-detail", "year": 2025,
                    "zone": "north", "technology": "Onshore wind",
                    "asset": "vre-0", "bid_tranche": "tranche-0", "limit": 10,
                },
            )
            exported = export_zonal_results(
                database,
                {"view": "curtailment-detail", "year": 2025, "limit": 1},
                root / "detail.csv", output_format="csv",
            )

            self.assertEqual(periods["total"], 2)
            self.assertEqual(periods["count"], 1)
            self.assertEqual(periods["items"][0]["period"], 0)
            self.assertEqual(details["total"], 1)
            self.assertEqual(details["count"], 1)
            self.assertEqual(details["items"][0]["asset_id"], "vre-0")
            self.assertEqual(exported["rows"], 1)
            self.assertEqual(
                len((root / "detail.csv").read_text(encoding="utf-8").splitlines()),
                2,
            )

            for query in (
                {"view": "curtailment", "limit": 1001},
                {"view": "curtailment", "offset": -1},
                {"view": "curtailment", "sql": "DROP TABLE metadata"},
                {"view": "curtailment", "zone": "north"},
                {"view": "curtailment-detail", "zone_id": "north"},
            ):
                with self.subTest(query=query), self.assertRaises(ValueError):
                    query_zonal_results(database, query)
            with self.assertRaises(ValueError):
                export_zonal_results(
                    database, {"view": "curtailment"}, root / "bad.parquet",
                    output_format="parquet",
                )

    def test_annual_v6_marks_a_missing_attribution_period_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "market.sqlite"
            _write_fixture(database, "summary")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "DELETE FROM vre_curtailment_detail WHERE period=1"
                )
                connection.execute(
                    "DELETE FROM vre_curtailment_period WHERE period=1"
                )
                connection.commit()
            attribution = query_zonal_annual_brief(database)["years"][0][
                "vre_curtailment"
            ]

        self.assertEqual(attribution["attribution_status"], "incomplete")
        self.assertEqual(
            attribution["reason_code"], "attribution_period_set_incomplete"
        )

    def test_annual_v6_matches_period_id_as_part_of_the_exact_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "market.sqlite"
            _write_fixture(database, "summary")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE vre_curtailment_period "
                    "SET period_id='attribution-orphan' WHERE period=1"
                )
                connection.commit()
            annual = query_zonal_annual_brief(database)["years"][0][
                "vre_curtailment"
            ]

        self.assertEqual(annual["attribution_status"], "incomplete")
        self.assertEqual(
            annual["reason_code"], "attribution_period_set_incomplete"
        )

    def test_annual_v6_surfaces_attribution_only_orphan_year(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "market.sqlite"
            _write_fixture(database, "summary")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("""
                    INSERT INTO vre_curtailment_period
                    SELECT 2026, 0, '2026:0',
                        realised_available_vre_mwh,
                        perfect_reference_dispatch_mwh,
                        copperplate_reference_dispatch_mwh,
                        zonal_final_dispatch_mwh,
                        economic_curtailment_mwh,
                        forecast_added_curtailment_mwh,
                        forecast_avoided_curtailment_mwh,
                        redispatch_added_curtailment_mwh,
                        redispatch_avoided_curtailment_mwh,
                        redispatch_net_impact_mwh,
                        total_curtailment_mwh,
                        curtailment_rate,
                        identity_residual_mwh,
                        validation_tolerance_mwh,
                        accounting_status,
                        counterfactual_realised_input_sha256,
                        attribution_method_id
                    FROM vre_curtailment_period
                    WHERE year=2025 AND period=0
                """)
                connection.commit()
            years = query_zonal_annual_brief(database)["years"]

        self.assertEqual([row["year"] for row in years], [2025, 2026])
        self.assertEqual(
            [row["vre_curtailment"]["attribution_status"] for row in years],
            ["incomplete", "incomplete"],
        )
        self.assertIsNone(years[1]["system_resource_cost_gbp"])

    def test_summary_and_full_ledgers_return_identical_annual_scientific_totals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary, full = root / "summary.sqlite", root / "full.sqlite"
            _write_fixture(summary, "summary")
            _write_fixture(full, "full")
            summary_brief = query_zonal_annual_brief(summary)
            full_brief = query_zonal_annual_brief(full)
            summary_caps = zonal_workspace_capabilities(summary)
            full_caps = zonal_workspace_capabilities(full)
        self.assertEqual(summary_brief["years"], full_brief["years"])
        self.assertFalse(summary_caps["bid_replay_available"])
        self.assertTrue(full_caps["bid_replay_available"])

    def test_loopback_api_exposes_bounded_curtailment_routes_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary) / "runs"
            root = runs / "api-run"
            root.mkdir(parents=True)
            (root / "status.json").write_text(
                json.dumps({"id": "api-run", "status": "completed"}),
                encoding="utf-8",
            )
            _write_fixture(
                root / "model-output" / "market" / "market.sqlite", "summary"
            )
            with patch.object(server, "RUNS_ROOT", runs):
                api = start_local_api(data_home=Path(temporary), patch_state_roots=False)
                httpd, origin, _session = api.start()
                try:
                    period = json.loads(urllib.request.urlopen(
                        origin
                        + "/api/runs/api-run/network-redispatch/curtailment"
                        + "?year=2025&limit=1",
                        timeout=10,
                    ).read())
                    detail = json.loads(urllib.request.urlopen(
                        origin
                        + "/api/runs/api-run/network-redispatch/curtailment-detail"
                        + "?year=2025&zone=north&asset=vre-0&bid_tranche=tranche-0",
                        timeout=10,
                    ).read())
                    csv_bytes = urllib.request.urlopen(
                        origin
                        + "/api/runs/api-run/network-redispatch/export"
                        + "?view=curtailment-detail&format=csv&limit=1",
                        timeout=10,
                    ).read()
                    with self.assertRaises(urllib.error.HTTPError) as rejected:
                        urllib.request.urlopen(
                            origin
                            + "/api/runs/api-run/network-redispatch/curtailment"
                            + "?limit=1001",
                            timeout=10,
                        )
                    with self.assertRaises(urllib.error.HTTPError) as raw_sql:
                        urllib.request.urlopen(
                            origin
                            + "/api/runs/api-run/network-redispatch/curtailment"
                            + "?sql=SELECT%201",
                            timeout=10,
                        )
                finally:
                    api.stop()

        self.assertEqual(period["view"], "curtailment")
        self.assertEqual(period["count"], 1)
        self.assertEqual(detail["view"], "curtailment-detail")
        self.assertEqual(detail["items"][0]["asset_id"], "vre-0")
        self.assertEqual(len(csv_bytes.decode("utf-8").splitlines()), 2)
        self.assertEqual(rejected.exception.code, 400)
        self.assertEqual(raw_sql.exception.code, 400)

    def test_loopback_api_exposes_solver_diagnostics_with_exact_allowlist(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary) / "runs"
            root = runs / "api-run"
            root.mkdir(parents=True)
            (root / "status.json").write_text(
                json.dumps({"id": "api-run", "status": "completed"}),
                encoding="utf-8",
            )
            _write_fixture(
                root / "model-output" / "market" / "market.sqlite", "summary"
            )
            with patch.object(server, "RUNS_ROOT", runs):
                api = start_local_api(data_home=Path(temporary), patch_state_roots=False)
                httpd, origin, _session = api.start()

                def request(path: str) -> tuple[int, bytes]:
                    try:
                        response = urllib.request.urlopen(origin + path, timeout=10)
                        return response.status, response.read()
                    except urllib.error.HTTPError as exc:
                        return exc.code, exc.read()

                try:
                    status, direct_bytes = request(
                        "/api/runs/api-run/network-redispatch/solver-diagnostics"
                        "?run=zonal-run&year=2025&period=1"
                        "&phase=secondary_schedule_deviation&limit=1"
                    )
                    export_status, export_bytes = request(
                        "/api/runs/api-run/network-redispatch/export"
                        "?view=solver-diagnostics&format=jsonl&run=zonal-run"
                        "&year=2025&period=1"
                        "&phase=secondary_schedule_deviation&limit=1"
                    )
                    rejected = [
                        request(
                            "/api/runs/api-run/network-redispatch/solver-diagnostics?"
                            + query
                        )[0]
                        for query in (
                            "limit=1001",
                            "sql=SELECT%201",
                            "status=GO",
                            "asset_id=gas",
                            "zone=north",
                        )
                    ]
                finally:
                    api.stop()

        self.assertEqual(status, 200)
        direct = json.loads(direct_bytes)
        self.assertEqual(direct["view"], "solver-diagnostics")
        self.assertEqual(direct["count"], 1)
        self.assertEqual(
            direct["items"][0]["phase_id"], "secondary_schedule_deviation"
        )
        self.assertEqual(export_status, 200)
        self.assertEqual(json.loads(export_bytes), direct["items"][0])
        self.assertEqual(rejected, [400, 400, 400, 400, 400])


if __name__ == "__main__":
    unittest.main()
