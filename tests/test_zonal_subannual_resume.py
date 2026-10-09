from __future__ import annotations

import copy
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from gridform_core.application import (
    _advance_subannual_parent_after_annual_checkpoint,
    _configure_subannual_checkpoint_sink,
    _recover_explicit_subannual_checkpoint,
)
from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import (
    DynamicStorageCostDefinition,
)
from gridform_core.builtin.scheme_c_1000twh.staged_psm import StagedBidAtCostPSM
from gridform_core.market_ledger import MarketLedgerBoundary
from gridform_core.module_context import ImmutableContextResolver, RunStaticContext
from gridform_core.subannual_checkpoint import (
    REQUIRED_INPUT_IDENTITIES,
    REQUIRED_MODULE_IDENTITIES,
    RuntimeCheckpointBoundary,
    SubannualCheckpointIdentity,
    SubannualCheckpointStore,
)
from gridform_core.v2.contracts import (
    AssetStateV2,
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
    ResolvedRun,
    StorageDispatchResource,
    YearState,
)
from gridform_core.v2.orchestrator import (
    CancellationRequested,
    build_year_context,
    checkpoint_identity,
    json_checkpoint_writer,
)
from gridform_core.zonal_contracts import ZonalDemand
from gridform_core.zonal_redispatch import ZonalRedispatchBalancing
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS

from tests.test_prompt101_staged_cem_integration import _economics, _network_pack


PERIOD_IDS = (
    "2022-01-31:23",
    "2022-01-31:24",
    "2022-02-28:23",
    "2022-02-28:24",
    "2022-03-01:01",
    "2022-03-01:02",
)

SCIENCE_TABLES = (
    "period_summary",
    "dispatch_summary",
    "storage_summary",
    "redispatch_summary",
    "zonal_period_accounting",
    "vre_curtailment_period",
    "zone_period_summary",
    "boundary_period_summary",
    "zonal_resource_dispatch",
    "redispatch_settlement",
    "period_integrity",
    "year_integrity",
)


class _CountingZonalRedispatch(ZonalRedispatchBalancing):
    def __init__(self) -> None:
        super().__init__()
        self.clear_calls = 0

    def clear(self, model_input):
        self.clear_calls += 1
        return super().clear(model_input)


class _CheckpointProtocolDouble:
    def __init__(self) -> None:
        self.sink = None
        self.restored: list[dict[str, object]] = []

    def configure_subannual_checkpoint_sink(self, sink) -> None:
        self.sink = sink

    def export_runtime_checkpoint(self, boundary):
        raise AssertionError("the application sink receives the exported checkpoint")

    def restore_runtime_checkpoint(self, checkpoint) -> None:
        self.restored.append(dict(checkpoint))


def _checkpoint_contract_fixture(root: Path, *, year: int = 2025):
    psm = _CheckpointProtocolDouble()
    store = SubannualCheckpointStore(root)
    input_hashes = {key: "a" * 64 for key in REQUIRED_INPUT_IDENTITIES}
    input_hashes.update({
        "data_pack_id": "fixture-pack",
        "network_pack_id": "fixture-network",
    })
    module_hashes = {key: "b" * 64 for key in REQUIRED_MODULE_IDENTITIES}
    module_hashes.update({
        "psm_module_id": "force-staged-bid-at-cost-psm",
        "psm_module_version": "1.1.0",
        "balancing_module_id": "value-zonal-redispatch-balancing",
        "balancing_module_version": "2.0.0",
        "solver_contract_id": "value.network-solver-contract/v2",
        "solver_contract_version": "value.zonal-lexicographic/v2",
    })
    parent_annual_identity = {
        "schema_version": "value.parent-annual-checkpoint-identity/v1",
        "identity": {"run_id": "monthly-run"},
        "state_year": year,
        "state_sha256": "c" * 64,
        "annual_checkpoint_sha256": "7" * 64,
    }
    configured = _configure_subannual_checkpoint_sink(
        psm=psm,
        store=store,
        frozen_input_hashes=input_hashes,
        frozen_module_hashes=module_hashes,
        parent_annual_checkpoint_identity=parent_annual_identity,
    )
    if not configured or psm.sink is None:
        raise AssertionError("checkpoint protocol double was not configured")
    boundary = RuntimeCheckpointBoundary(
        checkpoint_id=f"monthly-run:{year}:month-01:period-1",
        run_id="monthly-run",
        model_year=year,
        calendar_month=1,
        boundary_timestamp=f"{year}-02-01T00:00:00",
        last_period_index=1,
        last_period_id="2022-01-31:24",
        next_period_index=2,
        next_period_id="2022-02-01:01",
        period_hours=1.0,
        chronology_sha256="d" * 64,
    )
    ledger = MarketLedgerBoundary(
        year=year,
        last_committed_period=1,
        period_count=2,
        run_context_sha256="e" * 64,
        year_context_sha256="f" * 64,
        science_root="1" * 64,
        evidence_root="2" * 64,
        common_projection_sha256="3" * 64,
        stored_rows_sha256="4" * 64,
        trace_level="full",
        row_counts_json="{}",
        trace_coverage_json="{}",
        database_sha256="5" * 64,
        committed_prefix_sha256="6" * 64,
    )
    runtime_checkpoint = {
        "schema_version": "value.staged-psm-runtime-checkpoint/v1",
        "run_id": boundary.run_id,
        "year": boundary.model_year,
        "chronology_sha256": boundary.chronology_sha256,
        "run_context_sha256": ledger.run_context_sha256,
        "year_context_sha256": ledger.year_context_sha256,
        "runtime_state": {
            "next_period_index": boundary.next_period_index,
            "soc_mwh_by_asset": {"battery": 1.0},
            "income_gbp_by_owner": {"owner": 2.0},
        },
    }
    psm.sink(boundary, runtime_checkpoint, ledger)
    input_hashes.update({
        "run_context_sha256": ledger.run_context_sha256,
        "year_context_sha256": ledger.year_context_sha256,
    })
    expected = SubannualCheckpointIdentity(
        run_id=boundary.run_id,
        model_year=boundary.model_year,
        period_hours=boundary.period_hours,
        chronology_sha256=boundary.chronology_sha256,
        frozen_input_hashes=input_hashes,
        frozen_module_hashes=module_hashes,
    )
    checkpoint = store.load(boundary.checkpoint_id, expected)
    return (
        psm,
        store,
        checkpoint,
        expected,
        runtime_checkpoint,
        parent_annual_identity,
    )


def _dated_fixture() -> tuple[PSMInput, object]:
    profile = (1.0, 0.3, 0.8, 0.2, 0.7, 0.4)
    demand = (10.0, 9.0, 11.0, 8.0, 10.0, 9.0)
    assets = (
        AssetStateV2(
            "wind", "onshore", 10.0, region="north",
            extensions=_economics("wind-owner"),
        ),
        AssetStateV2(
            "battery", "1c_battery", 2.0, 2.0, "south",
            extensions=_economics("storage-owner"),
        ),
        AssetStateV2(
            "ccgt", "CCGT", 10.0, region="south",
            extensions=_economics("thermal-owner"),
        ),
    )
    chronology = ChronologicalPSMData(
        PERIOD_IDS,
        demand,
        (
            DispatchResource(
                "wind", "onshore", "vre", 10.0, 0.0, profile,
                extensions={"agent_id": "wind-owner"},
            ),
            DispatchResource(
                "ccgt", "CCGT", "thermal", 10.0, 100.0, (1.0,) * 6,
                extensions={"agent_id": "thermal-owner"},
            ),
        ),
        (
            StorageDispatchResource(
                "battery", "1c", 2.0, 2.0, 2.0, 1.0, 1.0, 2.0, 1.0,
                extensions={
                    "agent_id": "storage-owner",
                    "base_asset_id": "battery",
                },
            ),
        ),
        17_000.0,
        terminal_soc_rule="free",
        extensions={"forecast_demand_mwh": demand},
    )
    model_input = PSMInput(
        "zonal-monthly-parity",
        2025,
        "fixture-pack",
        OperatingState(2025, assets, ()),
        1.0,
        {"market.bid_multiplier": 1.0},
        chronology=chronology,
    )
    pack = replace(
        _network_pack(),
        zonal_demand=ZonalDemand(
            PERIOD_IDS,
            {
                "north": tuple(value * 0.4 for value in demand),
                "south": tuple(value * 0.6 for value in demand),
            },
            demand,
        ),
        scientific_sha256="",
    )
    return model_input, replace(
        pack, scientific_sha256=pack.compute_scientific_sha256()
    )


def _configured_psm(
    output_dir: Path,
    *,
    solver_contract: dict[str, object] | None = None,
) -> tuple[StagedBidAtCostPSM, _CountingZonalRedispatch, PSMInput]:
    model_input, pack = _dated_fixture()
    psm = StagedBidAtCostPSM()
    balancing = _CountingZonalRedispatch()
    psm.configure_run(
        output_dir=output_dir,
        storage_cost=DynamicStorageCostDefinition(),
        balancing=balancing,
        expected_balancing_identity=(balancing.id, balancing.version),
        network_pack=pack,
        zonal_demand_mode="network_pack_absolute_demand",
        ledger_detail="full",
    )
    run_context = RunStaticContext(
        run_id=model_input.run_id,
        study_revision_sha256="a" * 64,
        start_year=model_input.year,
        end_year=model_input.year,
        period_hours=model_input.period_hours,
        data_pack={
            "data_pack_id": model_input.data_pack_id,
            "manifest_sha256": "b" * 64,
        },
        module_graph={"graph_sha256": "c" * 64},
        scientific_parameters={"clock.period_hours": model_input.period_hours},
        runtime_controls={},
        trace_profile="full",
        solver_contract=(
            solver_contract
            if solver_contract is not None
            else DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
        ),
        market_configuration={
            "zonal_demand_mode": "network_pack_absolute_demand"
        },
        network_pack=pack.to_dict(),
    )
    prepared, metadata = psm.prepare_year_context(model_input)
    year_context = build_year_context(
        run_context=run_context,
        model_input=prepared,
        transition_lineage={"fixture": True},
        annual_metadata=metadata,
    )
    resolver = ImmutableContextResolver(
        run_contexts=(run_context,),
        year_contexts=(year_context,),
        modules_by_slot={"psm": psm, "balancing": balancing},
    )
    psm.configure(run_context, resolver)
    psm.start_year(year_context)
    return psm, balancing, prepared


def _logical_ledger(path: Path) -> dict[str, list[tuple[object, ...]]]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: list(connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
            for table in SCIENCE_TABLES
        }


def _ledger_roots(path: Path) -> tuple[str, str]:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT science_root, evidence_root FROM year_integrity WHERE year=2025"
        ).fetchone()
    if row is None:
        raise AssertionError("fixture ledger has no year-integrity row")
    return str(row[0]), str(row[1])


def _without_operational_transport_metadata(
    payload: dict[str, object]
) -> dict[str, object]:
    normalized = copy.deepcopy(payload)
    extensions = normalized["extensions"]
    ledger = extensions["market_ledger"]
    ledger.pop("writer_seconds", None)
    ledger.pop("source_artifact_sha256", None)
    for artifact in normalized["artifacts"]:
        if artifact["kind"] == "authoritative-market-ledger":
            artifact.pop("checksum_sha256", None)
    return normalized


class ZonalSubannualResumeTests(unittest.TestCase):
    def test_two_year_full_trace_preserves_unique_order_ids_and_references(self) -> None:
        original, pack = _dated_fixture()
        inputs = []
        for year in (2025, 2026):
            chronology = replace(original.chronology, period_ids=tuple(
                period_id.replace("2022", str(year)) for period_id in PERIOD_IDS
            ))
            inputs.append(replace(original, year=year,
                operating_state=replace(original.operating_state, year=year),
                chronology=chronology))
        pack = replace(pack, zonal_demand=ZonalDemand(
            tuple(period_id for item in inputs for period_id in item.chronology.period_ids),
            {zone: values * 2 for zone, values in pack.zonal_demand.demand_mwh_by_zone.items()},
            pack.zonal_demand.national_demand_mwh * 2,
        ), scientific_sha256="")
        pack = replace(pack, scientific_sha256=pack.compute_scientific_sha256())
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            psm = StagedBidAtCostPSM()
            balancing = _CountingZonalRedispatch()
            psm.configure_run(output_dir=output_dir,
                storage_cost=DynamicStorageCostDefinition(), balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=pack, zonal_demand_mode="network_pack_absolute_demand",
                ledger_detail="full")
            run_context = RunStaticContext(
                run_id=original.run_id, study_revision_sha256="a" * 64,
                start_year=2025, end_year=2026, period_hours=original.period_hours,
                data_pack={"data_pack_id": original.data_pack_id, "manifest_sha256": "b" * 64},
                module_graph={"graph_sha256": "c" * 64},
                scientific_parameters={"clock.period_hours": original.period_hours},
                runtime_controls={}, trace_profile="full",
                solver_contract=DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
                market_configuration={"zonal_demand_mode": "network_pack_absolute_demand"},
                network_pack=pack.to_dict())
            prepared_years = []
            contexts = []
            for model_input in inputs:
                prepared, metadata = psm.prepare_year_context(model_input)
                prepared_years.append(prepared)
                contexts.append(build_year_context(run_context=run_context,
                    model_input=prepared, transition_lineage={"fixture": True},
                    annual_metadata=metadata))
            resolver = ImmutableContextResolver(run_contexts=(run_context,),
                year_contexts=tuple(contexts), modules_by_slot={"psm": psm, "balancing": balancing})
            psm.configure(run_context, resolver)
            declared_balancing = []
            clear = balancing.clear
            def capture_clear(model_input):
                result = clear(model_input)
                declared_balancing.append((model_input, result))
                return result
            with patch.object(balancing, "clear", side_effect=capture_clear):
                for prepared, context in zip(prepared_years, contexts):
                    psm.start_year(context)
                    psm.run(prepared)
            with closing(sqlite3.connect(output_dir / "market" / "market.sqlite")) as connection:
                orders = connection.execute("SELECT order_id,year,period,stage FROM orders").fetchall()
                self.assertEqual({row[1] for row in orders}, {2025, 2026})
                self.assertEqual(len(orders), len({row[0] for row in orders}))
                for order_id, year, period, stage in orders:
                    self.assertTrue(order_id.startswith(f"{'ahead' if stage == 'ahead' else 'balance'}:{year}:{period}:"))
                missing = connection.execute("SELECT COUNT(*) FROM redispatch_settlement r LEFT JOIN orders o "
                    "ON r.bid_id=o.order_id AND r.year=o.year AND r.period=o.period "
                    "WHERE o.order_id IS NULL").fetchone()[0]
                self.assertEqual(missing, 0)
                scoped_orders = {}
                for order_id, year, period, stage in orders:
                    scoped_orders.setdefault((year, period, stage), set()).add(order_id)
                self.assertEqual(len(declared_balancing), 12)
                for model_input, result in declared_balancing:
                    ids = {bid.bid_id for bid in model_input.bids}
                    self.assertTrue({row.bid_id for row in result.accepted_adjustments}.issubset(ids))
                    self.assertEqual(ids, scoped_orders[(model_input.year, model_input.period, "balancing")])
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM period_integrity").fetchone()[0], 12)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM year_integrity").fetchone()[0], 2)

    maxDiff = None

    def test_verified_2028_annual_checkpoint_advances_2029_monthly_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            psm, store, _checkpoint, expected, _runtime, parent = (
                _checkpoint_contract_fixture(root, year=2028)
            )
            run = ResolvedRun(
                "monthly-run",
                "project",
                "scenario",
                "fixture-pack",
                2028,
                2029,
                {},
                {"clock.period_hours": 1.0},
                {},
            )
            annual_writer = json_checkpoint_writer(
                root / "model-output" / "checkpoints-v2",
                run,
                on_verified=lambda state, digest: (
                    _advance_subannual_parent_after_annual_checkpoint(
                        store=store,
                        parent_annual_checkpoint_identity=parent,
                        resolved_identity=checkpoint_identity(run),
                        state=state,
                        annual_checkpoint_sha256=digest,
                    )
                ),
            )
            annual_writer(YearState(2029, (), ()))
            self.assertEqual(parent["state_year"], 2029)
            self.assertEqual(parent["identity"], checkpoint_identity(run))
            self.assertEqual(store.discover(expected), ())

            boundary = RuntimeCheckpointBoundary(
                checkpoint_id="monthly-run:2029:month-01:period-1",
                run_id="monthly-run",
                model_year=2029,
                calendar_month=1,
                boundary_timestamp="2029-02-01T00:00:00",
                last_period_index=1,
                last_period_id="2022-01-31:24",
                next_period_index=2,
                next_period_id="2022-02-01:01",
                period_hours=1.0,
                chronology_sha256="8" * 64,
            )
            ledger = MarketLedgerBoundary(
                year=2029,
                last_committed_period=1,
                period_count=2,
                run_context_sha256="e" * 64,
                year_context_sha256="9" * 64,
                science_root="1" * 64,
                evidence_root="2" * 64,
                common_projection_sha256="3" * 64,
                stored_rows_sha256="4" * 64,
                trace_level="full",
                row_counts_json="{}",
                trace_coverage_json="{}",
                database_sha256="5" * 64,
                committed_prefix_sha256="6" * 64,
            )
            runtime = {
                "schema_version": "value.staged-psm-runtime-checkpoint/v1",
                "run_id": boundary.run_id,
                "year": boundary.model_year,
                "chronology_sha256": boundary.chronology_sha256,
                "run_context_sha256": ledger.run_context_sha256,
                "year_context_sha256": ledger.year_context_sha256,
                "runtime_state": {
                    "next_period_index": 2,
                    "soc_mwh_by_asset": {"battery": 1.0},
                },
            }
            psm.sink(boundary, runtime, ledger)
            next_inputs = {
                **dict(expected.frozen_input_hashes),
                "run_context_sha256": ledger.run_context_sha256,
                "year_context_sha256": ledger.year_context_sha256,
            }
            next_checkpoint = store.load(
                boundary.checkpoint_id,
                SubannualCheckpointIdentity(
                    run_id=boundary.run_id,
                    model_year=boundary.model_year,
                    period_hours=boundary.period_hours,
                    chronology_sha256=boundary.chronology_sha256,
                    frozen_input_hashes=next_inputs,
                    frozen_module_hashes=expected.frozen_module_hashes,
                ),
            )
            self.assertEqual(
                next_checkpoint.to_dict()["parent_annual_checkpoint_identity"],
                parent,
            )
            self.assertEqual(
                next_checkpoint.parent_annual_checkpoint_identity["state_year"],
                2029,
            )

    def test_explicit_recovery_claims_before_cleanup_and_restores_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            psm, store, checkpoint, expected, runtime_checkpoint, parent = (
                _checkpoint_contract_fixture(root)
            )
            database = root / "model-output" / "market" / "market.sqlite"
            database.parent.mkdir(parents=True, exist_ok=True)
            database.write_bytes(b"live-ledger")
            status = root / "status.json"
            status.write_text(json.dumps({"id": checkpoint.run_id}), encoding="utf-8")
            order: list[str] = []

            def recover(_database, *, boundary, diagnostic_directory, lease):
                claims = list((store.directory / "claims").glob("*.claim"))
                self.assertEqual(len(claims), 1)
                order.append("cleanup")
                return {
                    "diagnostic_database": (diagnostic_directory / "snapshot" / "market.sqlite").as_posix(),
                    "diagnostic_sha256": "7" * 64,
                    "cleaned_database_sha256": "8" * 64,
                    "committed_prefix_sha256": boundary.committed_prefix_sha256,
                    "committed_period": boundary.last_committed_period,
                    "period_count": boundary.period_count,
                }

            real_restore = psm.restore_runtime_checkpoint

            def restore(payload):
                order.append("restore")
                real_restore(payload)

            psm.restore_runtime_checkpoint = restore
            with patch(
                "gridform_core.application.recover_v8_market_prefix",
                side_effect=recover,
            ):
                evidence = _recover_explicit_subannual_checkpoint(
                    output_dir=root / "model-output",
                    resume_checkpoint_id=checkpoint.checkpoint_id,
                    expected=expected,
                    expected_parent_annual_checkpoint_identity=parent,
                    psm=psm,
                )

            self.assertEqual(order, ["cleanup", "restore"])
            self.assertEqual(psm.restored, [runtime_checkpoint])
            self.assertEqual(
                evidence["resumed_from_checkpoint_id"], checkpoint.checkpoint_id
            )
            persisted = json.loads(status.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted["subannual_recovery_authorization"]["state"],
                "consumed",
            )
            self.assertEqual(
                persisted["subannual_recovery"]["diagnostic_sha256"], "7" * 64
            )
            with patch(
                "gridform_core.application.recover_v8_market_prefix"
            ) as second_cleanup:
                with self.assertRaises(FileExistsError):
                    _recover_explicit_subannual_checkpoint(
                        output_dir=root / "model-output",
                        resume_checkpoint_id=checkpoint.checkpoint_id,
                        expected=expected,
                        expected_parent_annual_checkpoint_identity=parent,
                        psm=psm,
                    )
                second_cleanup.assert_not_called()

    def test_cleanup_failure_keeps_claim_checkpoint_and_live_database_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            psm, store, checkpoint, expected, _runtime, parent = (
                _checkpoint_contract_fixture(root)
            )
            checkpoint_path = next(
                (store.directory / str(checkpoint.model_year)).glob("*.json")
            )
            checkpoint_bytes = checkpoint_path.read_bytes()
            database = root / "model-output" / "market" / "market.sqlite"
            database.parent.mkdir(parents=True, exist_ok=True)
            database.write_bytes(b"live-ledger")

            with patch(
                "gridform_core.application.recover_v8_market_prefix",
                side_effect=RuntimeError("cleanup failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                    _recover_explicit_subannual_checkpoint(
                        output_dir=root / "model-output",
                        resume_checkpoint_id=checkpoint.checkpoint_id,
                        expected=expected,
                        expected_parent_annual_checkpoint_identity=parent,
                        psm=psm,
                    )

            self.assertEqual(len(list((store.directory / "claims").glob("*.claim"))), 1)
            self.assertEqual(checkpoint_path.read_bytes(), checkpoint_bytes)
            self.assertEqual(database.read_bytes(), b"live-ledger")
            self.assertEqual(psm.restored, [])

    def test_absent_or_mismatched_explicit_id_has_no_monthly_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            psm, store, checkpoint, expected, _runtime, parent = (
                _checkpoint_contract_fixture(root)
            )
            database = root / "model-output" / "market" / "market.sqlite"
            database.parent.mkdir(parents=True, exist_ok=True)
            database.write_bytes(b"live-ledger")

            with patch("gridform_core.application.SubannualCheckpointStore") as store_type:
                self.assertIsNone(_recover_explicit_subannual_checkpoint(
                    output_dir=root / "model-output",
                    resume_checkpoint_id=None,
                    expected=None,
                    expected_parent_annual_checkpoint_identity=None,
                    psm=psm,
                ))
                store_type.assert_not_called()

            with patch("gridform_core.application.recover_v8_market_prefix") as recover:
                with self.assertRaises(FileNotFoundError):
                    _recover_explicit_subannual_checkpoint(
                        output_dir=root / "model-output",
                        resume_checkpoint_id=checkpoint.checkpoint_id + "-mismatch",
                        expected=expected,
                        expected_parent_annual_checkpoint_identity=parent,
                        psm=psm,
                    )
                recover.assert_not_called()
            with patch("gridform_core.application.recover_v8_market_prefix") as recover:
                with self.assertRaisesRegex(ValueError, "parent annual"):
                    _recover_explicit_subannual_checkpoint(
                        output_dir=root / "model-output",
                        resume_checkpoint_id=checkpoint.checkpoint_id,
                        expected=expected,
                        expected_parent_annual_checkpoint_identity={
                            **parent,
                            "state_sha256": "9" * 64,
                        },
                        psm=psm,
                    )
                recover.assert_not_called()
            self.assertEqual(database.read_bytes(), b"live-ledger")
            self.assertFalse((store.directory / "claims").exists())

    def _capture_january_checkpoint(
        self,
        output_dir: Path,
        *,
        solver_contract: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], tuple[object, ...]]:
        psm, _balancing, model_input = _configured_psm(
            output_dir,
            solver_contract=solver_contract,
        )
        captured: list[tuple[object, ...]] = []
        psm.configure_subannual_checkpoint_sink(
            lambda boundary, checkpoint, ledger_boundary: captured.append(
                (boundary, checkpoint, ledger_boundary)
            )
        )

        def stop_after_january(year: int, period: int) -> None:
            if (year, period) == (2025, 1):
                raise CancellationRequested("stop after January")

        psm.configure_period_boundary_cancellation(stop_after_january)
        with self.assertRaisesRegex(CancellationRequested, "January"):
            psm.run(model_input)
        self.assertEqual(len(captured), 1)
        boundary, checkpoint, ledger_boundary = captured[0]
        self.assertIsInstance(boundary, RuntimeCheckpointBoundary)
        self.assertEqual(boundary.calendar_month, 1)
        self.assertEqual(boundary.last_period_index, 1)
        self.assertEqual(ledger_boundary.last_committed_period, 1)
        self.assertEqual(checkpoint["runtime_state"]["next_period_index"], 2)
        return copy.deepcopy(checkpoint), captured[0]

    def test_manifest_shaped_solver_contract_enables_monthly_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint, captured = self._capture_january_checkpoint(
                Path(temporary),
                solver_contract={
                    "schema_path": "gridform_core/data/contracts/network-solver-contract-v2.schema.json",
                    "defaults": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
                },
            )

        self.assertEqual(captured[0].calendar_month, 1)
        self.assertEqual(checkpoint["runtime_state"]["next_period_index"], 2)

    def test_january_restore_matches_uninterrupted_january_to_march_result_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "same-run"
            continuous, _balancing, continuous_input = _configured_psm(output_dir)
            continuous_result = continuous.run(continuous_input).to_dict()
            continuous_ledger = _logical_ledger(output_dir / "market" / "market.sqlite")
            continuous_roots = _ledger_roots(output_dir / "market" / "market.sqlite")

            shutil.rmtree(output_dir)
            checkpoint, captured = self._capture_january_checkpoint(output_dir)
            january_boundary = captured[0]
            january_ledger = captured[2]
            with closing(
                sqlite3.connect(output_dir / "market" / "market.sqlite")
            ) as connection:
                january_period_roots = connection.execute(
                    "SELECT science_hash, evidence_hash FROM period_integrity "
                    "WHERE year=2025 AND period=1"
                ).fetchone()
            self.assertEqual(
                checkpoint["runtime_state"]["next_period_index"],
                january_boundary.next_period_index,
            )
            self.assertEqual(
                checkpoint["runtime_state"]["solver_diagnostic_rows"][-1]["period"],
                january_ledger.last_committed_period,
            )
            self.assertEqual(
                january_period_roots,
                (january_ledger.science_root, january_ledger.evidence_root),
            )

            resumed, balancing, resumed_input = _configured_psm(output_dir)
            emitted_months: list[int] = []
            resumed.configure_subannual_checkpoint_sink(
                lambda boundary, _checkpoint, _ledger: emitted_months.append(
                    boundary.calendar_month
                )
            )
            resumed.restore_runtime_checkpoint(checkpoint)
            resumed_result = resumed.run(resumed_input).to_dict()
            resumed_ledger = _logical_ledger(output_dir / "market" / "market.sqlite")
            resumed_roots = _ledger_roots(output_dir / "market" / "market.sqlite")

        self.assertEqual(balancing.clear_calls, 4)
        self.assertEqual(emitted_months, [2])
        self.assertEqual(
            _without_operational_transport_metadata(resumed_result),
            _without_operational_transport_metadata(continuous_result),
        )
        self.assertEqual(resumed_ledger, continuous_ledger)
        self.assertEqual(resumed_roots, continuous_roots)

    def test_maintained_balancing_identity_follows_the_module_class(self) -> None:
        # C22 (M2-P0-8a review): staged_psm compared against a hard-coded
        # ("value-zonal-redispatch-balancing", "4.0.0"); a version bump would
        # have silently refused every subannual restore.
        with patch.object(ZonalRedispatchBalancing, "version", "4.0.1"):
            with tempfile.TemporaryDirectory() as temporary:
                output_dir = Path(temporary) / "same-run"
                checkpoint, _captured = self._capture_january_checkpoint(output_dir)
                resumed, balancing, resumed_input = _configured_psm(output_dir)
                self.assertEqual(balancing.version, "4.0.1")
                resumed.restore_runtime_checkpoint(checkpoint)
                resumed.run(resumed_input)
        self.assertGreater(balancing.clear_calls, 0)

    def test_restore_rejects_foreign_identity_before_any_solver_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "same-run"
            checkpoint, _captured = self._capture_january_checkpoint(output_dir)
            cases = {
                "run": ("run_id", "foreign-run", "run"),
                "year": ("year", 2026, "year"),
                "chronology": ("chronology_sha256", "f" * 64, "chronology"),
                "run context": ("run_context_sha256", "e" * 64, "run context"),
                "year context": ("year_context_sha256", "d" * 64, "year context"),
            }
            for label, (field, value, message) in cases.items():
                with self.subTest(label=label):
                    altered = copy.deepcopy(checkpoint)
                    altered[field] = value
                    psm, balancing, model_input = _configured_psm(output_dir)
                    with self.assertRaisesRegex(ValueError, message):
                        psm.restore_runtime_checkpoint(altered)
                        psm.run(model_input)
                    self.assertEqual(balancing.clear_calls, 0)


if __name__ == "__main__":
    unittest.main()
