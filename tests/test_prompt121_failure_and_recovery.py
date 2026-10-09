from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Barrier, BrokenBarrierError, Lock
from unittest.mock import patch

from backend.model_runner import (
    _present_recovery_authorization,
    record_run_cancelled,
    record_run_failure,
)
from gridform_core import failure_evidence as failure_evidence_module
from gridform_core.application import _load_authorized_incomplete_year_context
from gridform_core.builtin.scheme_c_1000twh.staged_psm import (
    _record_period_batch_at_boundary,
)
from gridform_core.failure_evidence import (
    FailureBundlePublicationError,
    FailureEvidenceRequest,
    MarketLedgerOwnershipLease,
    RECOVERY_AUTHORIZATION_SCHEMA_VERSION,
    cleanup_incomplete_v8_year,
    recover_incomplete_v8_year,
    recover_v8_market_prefix,
    recovery_authorization_id,
    write_first_failure_bundle,
)
from gridform_core.errors import InvariantError
from gridform_core.market_ledger import (
    DispatchSummaryRow,
    MarketLedgerBoundary,
    PERIOD_INDEXED_V8_TABLES,
    PeriodLedgerRow,
    RedispatchSummaryRow,
    SQLiteMarketLedger,
    StorageSummaryRow,
    build_market_period_batch,
    market_ledger_boundary,
)
from gridform_core.module_context import (
    RunStaticContext,
    YearContext,
    canonical_context_sha256,
)
from gridform_core.staged_market_contracts import BalancingInput, FlexibilityBid
from gridform_core.subannual_checkpoint import (
    SUBANNUAL_RECOVERY_AUTHORIZATION_SCHEMA,
    SubannualCheckpointStore,
    claim_subannual_recovery_authorization,
    issue_subannual_recovery_authorization,
    subannual_recovery_authorization_id,
)
from gridform_core.v2.orchestrator import (
    CancellationRequested,
    request_period_boundary_cancel,
)
from gridform_core.zonal_redispatch import (
    ZonalRedispatchBalancing,
    ZonalRedispatchSolveError,
)
from test_prompt120_market_ledger_v8 import _full_trace_batch


ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_bytes(database: Path) -> dict[str, bytes | None]:
    return {
        suffix: (
            database.with_name(database.name + suffix).read_bytes()
            if database.with_name(database.name + suffix).exists()
            else None
        )
        for suffix in ("", "-wal", "-shm")
    }


def _contexts(trace_profile: str = "summary") -> tuple[RunStaticContext, YearContext]:
    run_context = RunStaticContext(
        run_id="prompt121-run",
        study_revision_sha256=SHA_A,
        start_year=2025,
        end_year=2026,
        period_hours=0.5,
        data_pack={"id": "fixture", "manifest_sha256": SHA_B},
        module_graph={"balancing": "value-zonal-redispatch-balancing"},
        scientific_parameters={"clock.period_hours": 0.5},
        runtime_controls={"runtime.market_trace_level": trace_profile},
        trace_profile=trace_profile,
        solver_contract={"method": "highs-ds", "presolve": True},
        market_configuration={"zonal_demand_mode": "network_pack_absolute_demand"},
        network_pack={"network_pack_id": "broken-corridor-fixture"},
    )
    year_context = YearContext(
        run_id=run_context.run_id,
        year=2025,
        run_context_sha256=canonical_context_sha256(run_context),
        operating_state={"assets": [], "corridor": "B_TEST"},
        frozen_zone_shares={},
        opening_soc_mwh_by_asset={"battery": 2.0},
        transition_lineage={"annual_input_state_sha256": SHA_B},
    )
    return run_context, year_context


def _period_input() -> BalancingInput:
    bid = FlexibilityBid(
        "bid-1",
        "agent-1",
        "asset-1",
        "thermal",
        "north",
        "p1",
        "up",
        3.0,
        51.0,
        0.0,
        25.0,
        "north:injection",
        {"resource_class": "thermal"},
        extensions={"available_mwh": 1.5},
    )
    return BalancingInput(
        "prompt121-run",
        2025,
        1,
        "p1",
        SHA_A,
        1.5,
        {"asset-1": 3.0},
        {"battery": 2.0},
        (bid,),
        0.5,
        17_000.0,
        domain_payload={
            "schema_version": "value.zonal-redispatch-domain/v2",
            "period_slice": {
                "period_id": "p1",
                "forward_boundary_capacity_mwh": {"B_TEST": -1.0},
            },
        },
    )


def _solver_evidence() -> dict[str, object]:
    return {
        "solver_contract": {"method": "highs-ds", "presolve": True},
        "solver_stack": {"engine": "scipy.optimize.milp", "version": "fixture"},
        "method": "highs-ds",
        "completed_phases": [],
        "diagnostics": {},
        "environment": {"python": "fixture", "platform": "test"},
    }


def _batch(year: int, period: int, year_context_sha256: str):
    row = PeriodLedgerRow(
        year=year,
        period=period,
        stage="final_dispatch",
        forecast_demand_mwh=10.0,
        real_demand_mwh=10.0,
        accepted_supply_mwh=10.0,
        storage_charge_mwh=0.0,
        storage_discharge_mwh=0.0,
        flexible_demand_mwh=0.0,
        export_mwh=0.0,
        vre_available_mwh=5.0,
        vre_accepted_mwh=5.0,
        curtailed_mwh=0.0,
        import_mwh=0.0,
        clearing_price_gbp_per_mwh=50.0,
        physical_resource_cost_gbp=200.0,
        market_payment_gbp=500.0,
        policy_transfer_gbp=0.0,
        blackout_mwh=0.0,
        excess_mwh=0.0,
        energy_balance_residual_mwh=0.0,
    )
    return build_market_period_batch(
        period=row,
        dispatch_summary=(
            DispatchSummaryRow(year, period, "final_dispatch", "GB", "thermal", 10.0),
        ),
        storage_summary=(
            StorageSummaryRow(year, period, "GB", "battery", 0.0, 0.0, 2.0),
        ),
        redispatch_summary=(
            RedispatchSummaryRow(year, period, "GB", "thermal", "up", 0.0, 0.0),
        ),
        common_rows={},
        full_rows={},
        run_context_sha256=SHA_A,
        year_context_sha256=year_context_sha256,
    )


def _insert_obsolete_zonal_period(
    connection: sqlite3.Connection, period: int
) -> None:
    connection.execute(
        "INSERT INTO zonal_period_summary VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            2025, period, f"2025:{period}", 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0,
            0.0, "c" * 64, "reconciled",
        ),
    )
    connection.commit()


class Prompt121FailureAndRecoveryTests(unittest.TestCase):
    def test_subannual_authorization_binds_every_recovery_identity_and_is_one_use(self) -> None:
        issued = issue_subannual_recovery_authorization(
            run_id="monthly-run",
            checkpoint_id="monthly-run:2025:month-01:period-1",
            checkpoint_content_sha256="1" * 64,
            model_year=2025,
            last_committed_period=1,
            next_period=2,
            run_context_sha256="2" * 64,
            year_context_sha256="3" * 64,
            source="explicit_resume_checkpoint_id",
            nonce="4" * 32,
        )
        self.assertEqual(
            issued["schema_version"], SUBANNUAL_RECOVERY_AUTHORIZATION_SCHEMA
        )
        self.assertEqual(issued["state"], "issued")
        self.assertEqual(
            issued["authorization_id"],
            subannual_recovery_authorization_id(issued),
        )
        bound_fields = {
            "run_id": "another-run",
            "checkpoint_id": "monthly-run:2025:month-02:period-3",
            "checkpoint_content_sha256": "5" * 64,
            "model_year": 2026,
            "last_committed_period": 3,
            "next_period": 4,
            "run_context_sha256": "6" * 64,
            "year_context_sha256": "7" * 64,
            "source": "another-explicit-source",
            "nonce": "8" * 32,
        }
        for field_name, changed_value in bound_fields.items():
            with self.subTest(field_name=field_name):
                self.assertNotEqual(
                    subannual_recovery_authorization_id(
                        {**issued, field_name: changed_value}
                    ),
                    issued["authorization_id"],
                )

        with tempfile.TemporaryDirectory() as folder:
            store = SubannualCheckpointStore(Path(folder))
            presented = {**issued, "state": "presented"}
            consumed = claim_subannual_recovery_authorization(
                store=store, authorization=presented
            )
            self.assertEqual(consumed["state"], "consumed")
            with self.assertRaises(FileExistsError):
                claim_subannual_recovery_authorization(
                    store=store, authorization=presented
                )

    def test_subannual_claim_rejects_unpresented_or_tampered_authorization(self) -> None:
        issued = issue_subannual_recovery_authorization(
            run_id="monthly-run",
            checkpoint_id="monthly-run:2025:month-01:period-1",
            checkpoint_content_sha256="1" * 64,
            model_year=2025,
            last_committed_period=1,
            next_period=2,
            run_context_sha256="2" * 64,
            year_context_sha256="3" * 64,
            source="explicit_resume_checkpoint_id",
            nonce="4" * 32,
        )
        with tempfile.TemporaryDirectory() as folder:
            store = SubannualCheckpointStore(Path(folder))
            with self.assertRaisesRegex(ValueError, "presented"):
                claim_subannual_recovery_authorization(
                    store=store, authorization=issued
                )
            with self.assertRaisesRegex(ValueError, "identity"):
                claim_subannual_recovery_authorization(
                    store=store,
                    authorization={
                        **issued,
                        "state": "presented",
                        "checkpoint_content_sha256": "9" * 64,
                    },
                )

    def test_market_ledger_ownership_excludes_writer_and_recovery_processes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            ready = root / "writer-ready"
            release = root / "writer-release"
            script = f"""
import sys
import time
from pathlib import Path
from gridform_core.market_ledger import SQLiteMarketLedger
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_prompt120_market_ledger_v8 import _full_trace_batch
database = Path({json.dumps(str(database))})
ready = Path({json.dumps(str(ready))})
release = Path({json.dumps(str(release))})
ledger = SQLiteMarketLedger(database, trace_level='full')
ledger.connection.execute('PRAGMA wal_autocheckpoint=0')
ledger.record_period_batch(_full_trace_batch(0))
ledger.record_period_batch(_full_trace_batch(1))
ready.write_text('ready', encoding='utf-8')
while not release.exists():
    time.sleep(0.01)
ledger.close_unsealed()
"""
            writer = subprocess.Popen(
                [sys.executable, "-c", script], cwd=ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                for _ in range(500):
                    if ready.exists() or writer.poll() is not None:
                        break
                    __import__("time").sleep(0.01)
                self.assertTrue(ready.exists(), writer.stderr.read() if writer.poll() else "")
                self.assertTrue(database.with_name(database.name + "-wal").is_file())
                with self.assertRaisesRegex(InvariantError, "ownership"):
                    MarketLedgerOwnershipLease.acquire(database, role="recovery")
                self.assertFalse((root / "recovery-diagnostics").exists())
            finally:
                release.write_text("release", encoding="utf-8")
                stdout, stderr = writer.communicate(timeout=10)
                self.assertEqual(writer.returncode, 0, stdout + stderr)

            with MarketLedgerOwnershipLease.acquire(database, role="recovery"):
                blocked = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "from gridform_core.failure_evidence import "
                            "MarketLedgerOwnershipLease; "
                            f"MarketLedgerOwnershipLease.acquire(Path({str(database)!r}), "
                            "role='writer')"
                        ),
                    ],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn("ownership", blocked.stderr)

            with self.assertRaises(TypeError):
                recover_v8_market_prefix(
                    database,
                    boundary=object(),
                    diagnostic_directory=root / "recovery-diagnostics",
                )

    def test_prefix_recovery_captures_wal_and_removes_every_table_tail(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            boundary_path = root / "boundary.json"
            script = f"""
import json
import os
import sys
from pathlib import Path
from gridform_core.market_ledger import SQLiteMarketLedger, market_ledger_boundary
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_prompt120_market_ledger_v8 import _full_trace_batch
from test_prompt121_failure_and_recovery import _insert_obsolete_zonal_period
database = Path({json.dumps(str(database))})
ledger = SQLiteMarketLedger(database, trace_level='full')
ledger.connection.execute('PRAGMA wal_autocheckpoint=0')
ledger.record_period_batch(_full_trace_batch(0))
_insert_obsolete_zonal_period(ledger.connection, 0)
boundary = market_ledger_boundary(database, year=2025, committed_period=0)
Path({json.dumps(str(boundary_path))}).write_text(json.dumps(boundary.to_dict()), encoding='utf-8')
for period in (1, 2):
    ledger.record_period_batch(_full_trace_batch(period))
    _insert_obsolete_zonal_period(ledger.connection, period)
os._exit(0)
"""
            process = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            wal = database.with_name(database.name + "-wal")
            self.assertTrue(wal.is_file())
            self.assertGreater(wal.stat().st_size, 0)
            boundary = MarketLedgerBoundary.from_dict(
                json.loads(boundary_path.read_text(encoding="utf-8"))
            )

            with MarketLedgerOwnershipLease.acquire(
                database, role="recovery"
            ) as lease:
                result = recover_v8_market_prefix(
                    database,
                    boundary=boundary,
                    diagnostic_directory=root / "recovery-diagnostics",
                    lease=lease,
                )

            diagnostic = Path(str(result["diagnostic_database"]))
            self.assertEqual(diagnostic.name, "market.sqlite")
            self.assertEqual(diagnostic.parent.name, result["diagnostic_sha256"])
            manifest = json.loads(
                (diagnostic.parent / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["market_sqlite_sha256"], result["diagnostic_sha256"])
            self.assertEqual(
                set(manifest["members"]),
                {"market.sqlite", "market.sqlite-wal", "market.sqlite-shm"},
            )
            self.assertEqual(result["publication"], "sqlite_transaction")
            with closing(sqlite3.connect(diagnostic)) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM period_integrity WHERE year=2025"
                ).fetchone()[0], 3)
            with closing(sqlite3.connect(database)) as connection:
                for table in PERIOD_INDEXED_V8_TABLES:
                    self.assertEqual(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table} "
                            "WHERE year=2025 AND period>0"
                        ).fetchone()[0],
                        0,
                        table,
                    )
                orphaned = connection.execute(
                    "SELECT COUNT(*) FROM clearing_outcomes AS o "
                    "LEFT JOIN clearing_inputs AS i ON i.input_sha256=o.input_sha256 "
                    "WHERE i.input_sha256 IS NULL"
                ).fetchone()[0]
                self.assertEqual(orphaned, 0)
                row = connection.execute(
                    "SELECT period_count, complete FROM year_integrity WHERE year=2025"
                ).fetchone()
                self.assertEqual(tuple(row), (1, 0))

            resumed = SQLiteMarketLedger(database, trace_level="full")
            resumed.record_period_batch(_full_trace_batch(1))
            resumed.record_period_batch(_full_trace_batch(2))
            resumed.close()
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute(
                    "SELECT period_count, complete FROM year_integrity WHERE year=2025"
                ).fetchone(), (3, 1))

    def test_prefix_recovery_rejects_unexpected_annual_reliability_rows(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(_full_trace_batch(0))
            boundary = market_ledger_boundary(database, year=2025, committed_period=0)
            ledger.record_period_batch(_full_trace_batch(1))
            ledger.close_unsealed()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "INSERT INTO reliability_event VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        "unexpected", 2025, 0, 0, 1, 0.5, 1.0, '["GB"]', 1.0,
                        "observed_loss_of_load_chronology_not_statistical_lole",
                    ),
                )
                connection.commit()

            with self.assertRaisesRegex(InvariantError, "reliability_event"):
                with MarketLedgerOwnershipLease.acquire(
                    database, role="recovery"
                ) as lease:
                    recover_v8_market_prefix(
                        database, boundary=boundary,
                        diagnostic_directory=Path(folder) / "recovery-diagnostics",
                        lease=lease,
                    )
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM period_integrity WHERE year=2025"
                ).fetchone()[0], 2)

    def test_prefix_recovery_deletion_failure_leaves_live_ledger_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            boundary_path = root / "boundary.json"
            script = f"""
import json
import os
from pathlib import Path
from gridform_core.market_ledger import SQLiteMarketLedger, market_ledger_boundary
import sys
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_prompt120_market_ledger_v8 import _full_trace_batch
database = Path({json.dumps(str(database))})
ledger = SQLiteMarketLedger(database, trace_level='full')
ledger.connection.execute('PRAGMA wal_autocheckpoint=0')
ledger.record_period_batch(_full_trace_batch(0))
boundary = market_ledger_boundary(database, year=2025, committed_period=0)
Path({json.dumps(str(boundary_path))}).write_text(json.dumps(boundary.to_dict()), encoding='utf-8')
ledger.record_period_batch(_full_trace_batch(1))
os._exit(0)
"""
            process = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            boundary = MarketLedgerBoundary.from_dict(json.loads(
                boundary_path.read_text(encoding="utf-8")
            ))
            before_boundary = boundary_path.read_bytes()
            with closing(sqlite3.connect(database)) as connection:
                before_counts = {
                    table: int(connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0])
                    for table in (*PERIOD_INDEXED_V8_TABLES, "clearing_outcomes")
                }
                before_year = tuple(connection.execute(
                    "SELECT * FROM year_integrity WHERE year=2025"
                ).fetchone())
            original_delete = failure_evidence_module._delete_v8_market_table_tail
            calls = 0

            def fail_after_one_delete(*args, **kwargs):
                nonlocal calls
                result = original_delete(*args, **kwargs)
                calls += 1
                if calls == len(PERIOD_INDEXED_V8_TABLES) + 1:
                    raise RuntimeError("injected deletion failure after mutation")
                return result

            with patch.object(
                failure_evidence_module,
                "_delete_v8_market_table_tail",
                side_effect=fail_after_one_delete,
            ):
                with MarketLedgerOwnershipLease.acquire(
                    database, role="recovery"
                ) as lease:
                    with self.assertRaisesRegex(
                        RuntimeError, "after mutation"
                    ):
                        recover_v8_market_prefix(
                            database, boundary=boundary,
                            diagnostic_directory=root / "recovery-diagnostics",
                            lease=lease,
                        )

            self.assertEqual(calls, len(PERIOD_INDEXED_V8_TABLES) + 1)
            self.assertEqual(boundary_path.read_bytes(), before_boundary)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(
                    {
                        table: int(connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0])
                        for table in (*PERIOD_INDEXED_V8_TABLES, "clearing_outcomes")
                    },
                    before_counts,
                )
                self.assertEqual(
                    tuple(connection.execute(
                        "SELECT * FROM year_integrity WHERE year=2025"
                    ).fetchone()),
                    before_year,
                )

    def test_prefix_recovery_rejects_tampered_diagnostic_race_collision(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(_full_trace_batch(0))
            boundary = market_ledger_boundary(database, year=2025, committed_period=0)
            ledger.record_period_batch(_full_trace_batch(1))
            ledger.close_unsealed()
            real_rename = os.rename

            def collide(source, destination):
                source_path = Path(source)
                destination_path = Path(destination)
                if source_path.name.startswith(".market-recovery-"):
                    __import__("shutil").copytree(source_path, destination_path)
                    manifest_path = destination_path / "manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["selected_boundary"]["science_root"] = "f" * 64
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                    raise FileExistsError(destination_path)
                return real_rename(source, destination)

            before = _sqlite_bytes(database)
            with patch.object(failure_evidence_module.os, "rename", side_effect=collide):
                with MarketLedgerOwnershipLease.acquire(
                    database, role="recovery"
                ) as lease:
                    with self.assertRaisesRegex(ValueError, "manifest"):
                        recover_v8_market_prefix(
                            database, boundary=boundary,
                            diagnostic_directory=root / "recovery-diagnostics",
                            lease=lease,
                        )
            self.assertEqual(_sqlite_bytes(database), before)

    def test_prefix_recovery_rejects_non_regular_diagnostic_member(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(_full_trace_batch(0))
            boundary = market_ledger_boundary(database, year=2025, committed_period=0)
            ledger.record_period_batch(_full_trace_batch(1))
            ledger.close_unsealed()

            with MarketLedgerOwnershipLease.acquire(
                database, role="recovery"
            ) as lease:
                with patch.object(
                    failure_evidence_module,
                    "_delete_v8_market_table_tail",
                    side_effect=RuntimeError("retain diagnostic"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "retain diagnostic"):
                        recover_v8_market_prefix(
                            database, boundary=boundary,
                            diagnostic_directory=root / "recovery-diagnostics",
                            lease=lease,
                        )
            diagnostic = next((root / "recovery-diagnostics").iterdir())
            manifest = diagnostic / "manifest.json"
            manifest.unlink()
            manifest.mkdir()
            with MarketLedgerOwnershipLease.acquire(
                database, role="recovery"
            ) as lease:
                with self.assertRaisesRegex(ValueError, "regular"):
                    recover_v8_market_prefix(
                        database, boundary=boundary,
                        diagnostic_directory=root / "recovery-diagnostics",
                        lease=lease,
                    )

    def test_prefix_recovery_never_replaces_or_unlinks_live_sqlite_files(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            boundary_path = root / "boundary.json"
            script = f"""
import json
import os
import sys
from pathlib import Path
from gridform_core.market_ledger import SQLiteMarketLedger, market_ledger_boundary
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_prompt120_market_ledger_v8 import _full_trace_batch
database = Path({json.dumps(str(database))})
ledger = SQLiteMarketLedger(database, trace_level='full')
ledger.connection.execute('PRAGMA wal_autocheckpoint=0')
ledger.record_period_batch(_full_trace_batch(0))
boundary = market_ledger_boundary(database, year=2025, committed_period=0)
Path({json.dumps(str(boundary_path))}).write_text(json.dumps(boundary.to_dict()), encoding='utf-8')
ledger.record_period_batch(_full_trace_batch(1))
os._exit(0)
"""
            process = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            boundary = MarketLedgerBoundary.from_dict(json.loads(
                boundary_path.read_text(encoding="utf-8")
            ))
            real_replace = os.replace
            real_unlink = Path.unlink

            def reject_live_replace(source, destination):
                if Path(destination).resolve() == database.resolve():
                    raise AssertionError("live database replacement is forbidden")
                return real_replace(source, destination)

            def reject_live_sidecar_unlink(path, *args, **kwargs):
                if Path(path) in {
                    database.with_name(database.name + "-wal"),
                    database.with_name(database.name + "-shm"),
                }:
                    raise AssertionError("live sidecar unlink is forbidden")
                return real_unlink(path, *args, **kwargs)

            with patch.object(
                failure_evidence_module.os, "replace", side_effect=reject_live_replace
            ), patch.object(Path, "unlink", new=reject_live_sidecar_unlink):
                with MarketLedgerOwnershipLease.acquire(
                    database, role="recovery"
                ) as lease:
                    result = recover_v8_market_prefix(
                        database, boundary=boundary,
                        diagnostic_directory=root / "recovery-diagnostics",
                        lease=lease,
                    )

            self.assertEqual(result["publication"], "sqlite_transaction")
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM period_integrity WHERE year=2025"
                ).fetchone()[0], 1)

    def test_prefix_recovery_temp_close_failure_leaves_no_created_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period_batch(_full_trace_batch(0))
            boundary = market_ledger_boundary(database, year=2025, committed_period=0)
            ledger.record_period_batch(_full_trace_batch(1))
            ledger.close_unsealed()
            real_close = os.close
            calls = 0

            def close_then_fail_once(descriptor):
                nonlocal calls
                calls += 1
                real_close(descriptor)
                if calls == 1:
                    raise OSError("injected temp close failure")

            with MarketLedgerOwnershipLease.acquire(
                database, role="recovery"
            ) as lease, patch.object(
                failure_evidence_module.os,
                "close",
                side_effect=close_then_fail_once,
            ):
                with self.assertRaisesRegex(OSError, "temp close failure"):
                    recover_v8_market_prefix(
                        database, boundary=boundary,
                        diagnostic_directory=root / "recovery-diagnostics",
                        lease=lease,
                    )

            self.assertEqual(
                list(root.glob(".market.sqlite-*-recovery-*.tmp")), []
            )

    def test_broken_corridor_writes_complete_bundle_for_every_trace_profile(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for trace_profile in ("off", "summary", "full"):
                with self.subTest(trace_profile=trace_profile):
                    run_context, year_context = _contexts(trace_profile)
                    module_root = root / trace_profile
                    module = ZonalRedispatchBalancing(evidence_root=module_root)
                    module._run_context = run_context
                    module._year_context = year_context
                    error = ZonalRedispatchSolveError(
                        "broken corridor constraint",
                        {
                            "completed_phase_optima": [
                                {"phase": "primary_bid_cost", "objective": 4.0}
                            ],
                            "maximum_corridor_residual_mwh": 2.5,
                            "raw_status": 2,
                        },
                    )

                    module._failure(_period_input(), error, stage="lexicographic_solve")

                    destination = module_root / "market" / "failures" / "first-failure"
                    self.assertTrue(destination.is_dir())
                    manifest = json.loads(
                        (destination / "manifest.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(manifest["schema_version"], "value.failure-bundle/v1")
                    self.assertEqual(manifest["trace_profile"], trace_profile)
                    self.assertEqual(manifest["stage"], "lexicographic_solve")
                    self.assertIs(manifest["fallback_used"], False)
                    self.assertEqual(
                        set(manifest["members"]),
                        {
                            "error.json",
                            "period-input.json",
                            "residuals.json",
                            "run-context.json",
                            "solver.json",
                            "year-context.json",
                        },
                    )
                    for name, member in manifest["members"].items():
                        path = destination / name
                        self.assertEqual(member["sha256"], _sha256(path))
                        self.assertEqual(member["size_bytes"], path.stat().st_size)
                    period_payload = json.loads(
                        (destination / "period-input.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(period_payload, _period_input().to_dict())
                    self.assertEqual(period_payload["bids"][0]["bid_id"], "bid-1")
                    solver = json.loads(
                        (destination / "solver.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        solver["completed_phases"][0]["phase"], "primary_bid_cost"
                    )
                    self.assertFalse(any("copperplate" in path.name for path in destination.iterdir()))

    def test_first_failure_wins_secondary_failure_and_publish_race(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "first-failure"
            run_context, year_context = _contexts()

            def publish(stage: str):
                return write_first_failure_bundle(
                    FailureEvidenceRequest(
                        run_context,
                        year_context,
                        _period_input(),
                        stage,
                        RuntimeError(stage),
                        _solver_evidence(),
                        {"maximum_residual_mwh": 1.0},
                    ),
                    destination,
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                references = list(executor.map(publish, ("first", "secondary")))

            self.assertEqual(references[0].checksum_sha256, references[1].checksum_sha256)
            first_manifest = (destination / "manifest.json").read_bytes()
            publish("later")
            self.assertEqual((destination / "manifest.json").read_bytes(), first_manifest)
            self.assertEqual(len([p for p in destination.parent.iterdir() if p.is_dir()]), 1)

    def test_publication_failure_leaves_no_canonical_or_partial_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / "first-failure"
            run_context, year_context = _contexts()
            request = FailureEvidenceRequest(
                run_context,
                year_context,
                _period_input(),
                "solve",
                RuntimeError("solver failed"),
                _solver_evidence(),
                {"maximum_residual_mwh": 1.0},
            )
            with patch("gridform_core.failure_evidence.os.rename", side_effect=OSError("disk")):
                with self.assertRaises(FailureBundlePublicationError) as raised:
                    write_first_failure_bundle(request, destination)
            self.assertFalse(destination.exists())
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual(raised.exception.diagnostics["exception_type"], "OSError")
            self.assertIn("disk", raised.exception.diagnostics["exception_message"])

    def test_cancellation_is_observed_only_after_second_period_commit(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            events: list[tuple[int, str]] = []

            def cancellation_check(year: int, boundary: str) -> bool:
                events.append((year, boundary))
                with closing(sqlite3.connect(database)) as connection:
                    committed = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM period_integrity WHERE year=?", (year,)
                        ).fetchone()[0]
                    )
                return committed == 2

            def boundary(year: int, period: int) -> None:
                request_period_boundary_cancel(
                    cancellation_check, year=year, period=period
                )

            _record_period_batch_at_boundary(ledger, _batch(2026, 0, SHA_B))
            boundary(2026, 0)
            with self.assertRaisesRegex(CancellationRequested, "period 1"):
                _record_period_batch_at_boundary(ledger, _batch(2026, 1, SHA_B))
                boundary(2026, 1)

            with closing(sqlite3.connect(database)) as connection:
                periods = connection.execute(
                    "SELECT period FROM period_integrity WHERE year=2026 ORDER BY period"
                ).fetchall()
                complete = connection.execute(
                    "SELECT complete FROM year_integrity WHERE year=2026"
                ).fetchone()[0]
            self.assertEqual(periods, [(0,), (1,)])
            self.assertEqual(complete, 0)
            self.assertEqual(
                events,
                [(2026, "after_period_commit"), (2026, "after_period_commit")],
            )
            ledger.close_unsealed()

    def test_annual_resume_verifies_hash_cleans_only_incomplete_year_and_recomputes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            complete_year_hash = "c" * 64
            incomplete_year_hash = "d" * 64
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(2025, 0, complete_year_hash))
            ledger.close()
            with closing(sqlite3.connect(database)) as connection:
                prior = connection.execute(
                    "SELECT * FROM year_integrity WHERE year=2025"
                ).fetchone()

            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(2026, 0, incomplete_year_hash))
            ledger.record_period_batch(_batch(2026, 1, incomplete_year_hash))
            ledger.close_unsealed()

            with self.assertRaisesRegex(ValueError, "opening YearContext"):
                cleanup_incomplete_v8_year(
                    database,
                    year=2026,
                    expected_committed_period=1,
                    expected_run_context_sha256=SHA_A,
                    expected_year_context_sha256="e" * 64,
                )
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM period_integrity WHERE year=2026"
                    ).fetchone()[0],
                    2,
                )

            result = recover_incomplete_v8_year(
                database,
                year=2026,
                expected_committed_period=1,
                expected_run_context_sha256=SHA_A,
                expected_year_context_sha256=incomplete_year_hash,
                diagnostic_directory=Path(folder) / "recovery",
            )
            self.assertEqual(result["year"], 2026)
            self.assertEqual(result["deleted_periods"], 2)
            diagnostic = Path(str(result["diagnostic_database"]))
            self.assertTrue(diagnostic.is_file())
            with closing(sqlite3.connect(diagnostic)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM period_integrity WHERE year=2026"
                    ).fetchone()[0],
                    2,
                )
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT * FROM year_integrity WHERE year=2025"
                    ).fetchone(),
                    prior,
                )
                for table in (
                    "period_summary",
                    "dispatch_summary",
                    "storage_summary",
                    "redispatch_summary",
                    "period_integrity",
                    "year_integrity",
                ):
                    self.assertEqual(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE year=2026"
                        ).fetchone()[0],
                        0,
                        table,
                    )

            resumed = SQLiteMarketLedger(database, trace_level="summary")
            resumed.record_period_batch(_batch(2026, 0, incomplete_year_hash))
            resumed.record_period_batch(_batch(2026, 1, incomplete_year_hash))
            resumed.close()
            with closing(sqlite3.connect(database)) as connection:
                recomputed = connection.execute(
                    "SELECT year_context_sha256, period_count, complete "
                    "FROM year_integrity WHERE year=2026"
                ).fetchone()
                self.assertEqual(recomputed, (incomplete_year_hash, 2, 1))
                self.assertEqual(
                    connection.execute(
                        "SELECT * FROM year_integrity WHERE year=2025"
                    ).fetchone(),
                    prior,
                )

    def test_application_requires_cancel_status_context_and_checkpoint_identity(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder) / "run" / "model-output"
            context_dir = output_dir / "market" / "context"
            context_dir.mkdir(parents=True)
            run_context, year_context = _contexts()
            (context_dir / "year-2025.json").write_text(
                json.dumps(year_context.to_dict()), encoding="utf-8"
            )
            status_path = output_dir.parent / "status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "id": run_context.run_id,
                        "status": "running",
                        "execution_status": "running",
                    }
                ),
                encoding="utf-8",
            )
            authorization = {
                "schema_version": RECOVERY_AUTHORIZATION_SCHEMA_VERSION,
                "run_id": run_context.run_id,
                "incomplete_year": 2025,
                "committed_period": 1,
                "checkpoint_state_sha256": SHA_B,
                "run_context_sha256": canonical_context_sha256(run_context),
                "year_context_sha256": canonical_context_sha256(year_context),
                "source": "period_boundary_cancellation",
                "issuance_nonce": "c" * 32,
                "state": "presented",
            }
            authorization["authorization_id"] = recovery_authorization_id(authorization)
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["recovery_authorization"] = authorization
            status_path.write_text(json.dumps(status), encoding="utf-8")

            runtime_context = replace(
                run_context,
                runtime_controls={
                    **dict(run_context.runtime_controls),
                    "runtime.monthly_checkpoint_enabled": True,
                },
            )
            self.assertNotEqual(
                canonical_context_sha256(runtime_context),
                canonical_context_sha256(run_context),
            )
            loaded = _load_authorized_incomplete_year_context(
                output_dir=output_dir,
                run_context=runtime_context,
                run_id=run_context.run_id,
                year=2025,
                checkpoint_state_sha256=SHA_B,
            )
            self.assertEqual(loaded, year_context)
            consumed = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(consumed["recovery_authorization"]["state"], "consumed")
            consumed["recovery_authorization"]["state"] = "presented"
            status_path.write_text(json.dumps(consumed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "boundary"):
                _load_authorized_incomplete_year_context(
                    output_dir=output_dir,
                    run_context=run_context,
                    run_id=run_context.run_id,
                    year=2025,
                    checkpoint_state_sha256="f" * 64,
                )
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["id"] = "another-run"
            status_path.write_text(json.dumps(status), encoding="utf-8")
            self.assertIsNone(
                _load_authorized_incomplete_year_context(
                    output_dir=output_dir,
                    run_context=run_context,
                    run_id=run_context.run_id,
                    year=2025,
                    checkpoint_state_sha256=SHA_B,
                )
            )

    def test_cancelled_status_declares_incomplete_year_and_annual_resume_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            status_path = Path(folder) / "status.json"
            status_path.write_text(
                json.dumps({"id": "run", "project_id": "project"}),
                encoding="utf-8",
            )
            run_context, year_context = _contexts()
            context_dir = Path(folder) / "model-output" / "market" / "context"
            context_dir.mkdir(parents=True)
            (context_dir / "run-context.json").write_text(json.dumps(run_context.to_dict()), encoding="utf-8")
            (context_dir / "year-2025.json").write_text(json.dumps(year_context.to_dict()), encoding="utf-8")
            checkpoint_dir = Path(folder) / "model-output" / "checkpoints-v2"
            checkpoint_dir.mkdir(parents=True)
            (checkpoint_dir / "state-2025.json").write_text(json.dumps({"state_sha256": SHA_B}), encoding="utf-8")
            status = record_run_cancelled(
                status_path,
                run_id=run_context.run_id,
                project_id="project",
                mode="full",
                message="Cancellation accepted after committed model year 2025 period 1",
            )
            self.assertEqual(status["cancellation_boundary"], "after_committed_period")
            self.assertIs(status["current_model_year_complete"], False)
            self.assertEqual(status["resume_boundary"], "prior_annual_checkpoint")
            self.assertEqual(status["resume_mode"], "recompute_full_incomplete_year")
            authorization = status["recovery_authorization"]
            self.assertEqual(authorization["incomplete_year"], 2025)
            self.assertEqual(authorization["committed_period"], 1)
            self.assertEqual(authorization["state"], "issued")
            self.assertEqual(authorization["authorization_id"], recovery_authorization_id(authorization))
            presented = _present_recovery_authorization(status)
            self.assertIsNotNone(presented)
            running = {**status, "status": "running", "execution_status": "running"}
            running["recovery_authorization"] = presented
            status_path.write_text(json.dumps(running), encoding="utf-8")
            self.assertEqual(
                _load_authorized_incomplete_year_context(
                    output_dir=Path(folder) / "model-output",
                    run_context=run_context,
                    run_id=run_context.run_id,
                    year=2025,
                    checkpoint_state_sha256=SHA_B,
                ),
                year_context,
            )
            failed = record_run_failure(
                status_path, run_id=run_context.run_id, project_id="project",
                mode="full", error=RuntimeError("recovery solve failed"),
            )
            self.assertNotIn("recovery_authorization", failed)
            self.assertIsNone(_present_recovery_authorization(failed))

    def test_recovery_authorization_has_one_winner_across_concurrent_consumers(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder) / "run" / "model-output"
            context_dir = output_dir / "market" / "context"
            context_dir.mkdir(parents=True)
            run_context, year_context = _contexts()
            (context_dir / "year-2025.json").write_text(
                json.dumps(year_context.to_dict()), encoding="utf-8"
            )
            authorization = {
                "schema_version": RECOVERY_AUTHORIZATION_SCHEMA_VERSION,
                "run_id": run_context.run_id,
                "incomplete_year": 2025,
                "committed_period": 1,
                "checkpoint_state_sha256": SHA_B,
                "run_context_sha256": canonical_context_sha256(run_context),
                "year_context_sha256": canonical_context_sha256(year_context),
                "source": "period_boundary_cancellation",
                "issuance_nonce": "d" * 32,
                "state": "presented",
            }
            authorization["authorization_id"] = recovery_authorization_id(authorization)
            status_path = output_dir.parent / "status.json"
            status_path.write_text(json.dumps({
                "id": run_context.run_id,
                "status": "running",
                "execution_status": "running",
                "recovery_authorization": authorization,
            }), encoding="utf-8")
            barrier = Barrier(2)
            write_lock = Lock()
            from gridform_core import application as application_module
            real_atomic = application_module._atomic_json_artifact

            def synchronized_atomic(path: Path, payload: object):
                if path == status_path:
                    try:
                        barrier.wait(timeout=1.0)
                    except BrokenBarrierError:
                        pass
                with write_lock:
                    return real_atomic(path, payload)

            def consume() -> bool:
                try:
                    _load_authorized_incomplete_year_context(
                        output_dir=output_dir,
                        run_context=run_context,
                        run_id=run_context.run_id,
                        year=2025,
                        checkpoint_state_sha256=SHA_B,
                    )
                    return True
                except ValueError:
                    return False

            with patch("gridform_core.application._atomic_json_artifact", side_effect=synchronized_atomic):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(lambda _: consume(), range(2)))
            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), 1)

    def test_same_boundary_recancellation_issues_a_new_grant_without_reusing_old_claim(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder) / "model-output"
            context_dir = output_dir / "market" / "context"
            context_dir.mkdir(parents=True)
            run_context, year_context = _contexts()
            (context_dir / "run-context.json").write_text(
                json.dumps(run_context.to_dict()), encoding="utf-8"
            )
            (context_dir / "year-2025.json").write_text(
                json.dumps(year_context.to_dict()), encoding="utf-8"
            )
            checkpoint_dir = output_dir / "checkpoints-v2"
            checkpoint_dir.mkdir(parents=True)
            (checkpoint_dir / "state-2025.json").write_text(
                json.dumps({"state_sha256": SHA_B}), encoding="utf-8"
            )
            status_path = Path(folder) / "status.json"
            status_path.write_text(json.dumps({
                "id": run_context.run_id, "project_id": "project",
            }), encoding="utf-8")
            message = "Cancellation accepted after committed model year 2025 period 1"

            with patch(
                "backend.model_runner._issuance_nonce",
                side_effect=("a" * 32, "b" * 32),
                create=True,
            ):
                first_status = record_run_cancelled(
                    status_path, run_id=run_context.run_id, project_id="project",
                    mode="full", message=message,
                )
                first = dict(first_status["recovery_authorization"])
                running = {
                    **first_status,
                    "status": "running",
                    "execution_status": "running",
                    "recovery_authorization": _present_recovery_authorization(first_status),
                }
                status_path.write_text(json.dumps(running), encoding="utf-8")
                self.assertEqual(
                    _load_authorized_incomplete_year_context(
                        output_dir=output_dir, run_context=run_context,
                        run_id=run_context.run_id, year=2025,
                        checkpoint_state_sha256=SHA_B,
                    ),
                    year_context,
                )
                record_run_failure(
                    status_path, run_id=run_context.run_id, project_id="project",
                    mode="full", error=RuntimeError("first recovery failed"),
                )
                # P0-3 S2: failed -> cancelled is refused; a re-cancellation
                # happens only after the failed run was resumed and is running.
                resumed = json.loads(status_path.read_text(encoding="utf-8"))
                status_path.write_text(json.dumps({
                    **resumed, "status": "running", "execution_status": "running",
                }), encoding="utf-8")
                second_status = record_run_cancelled(
                    status_path, run_id=run_context.run_id, project_id="project",
                    mode="full", message=message,
                )
            second = dict(second_status["recovery_authorization"])
            self.assertNotEqual(first["authorization_id"], second["authorization_id"])

            stale = {
                **second_status, "status": "running", "execution_status": "running",
                "recovery_authorization": {**first, "state": "presented"},
            }
            status_path.write_text(json.dumps(stale), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already been claimed"):
                _load_authorized_incomplete_year_context(
                    output_dir=output_dir, run_context=run_context,
                    run_id=run_context.run_id, year=2025,
                    checkpoint_state_sha256=SHA_B,
                )

            fresh = {
                **second_status, "status": "running", "execution_status": "running",
                "recovery_authorization": _present_recovery_authorization(second_status),
            }
            status_path.write_text(json.dumps(fresh), encoding="utf-8")
            self.assertEqual(
                _load_authorized_incomplete_year_context(
                    output_dir=output_dir, run_context=run_context,
                    run_id=run_context.run_id, year=2025,
                    checkpoint_state_sha256=SHA_B,
                ),
                year_context,
            )

    def test_canonical_bundle_requires_exact_members_and_owned_invalid_publish_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_context, year_context = _contexts()
            request = FailureEvidenceRequest(
                run_context, year_context, _period_input(), "zonal_redispatch",
                RuntimeError("solver failed"), _solver_evidence(), {"balance": 0.0},
            )
            destination = Path(folder) / "first-failure"
            write_first_failure_bundle(request, destination)
            (destination / "extra.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(FailureBundlePublicationError):
                write_first_failure_bundle(request, destination)
            (destination / "extra.json").unlink()
            manifest_path = destination / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.pop("context_hashes")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(FailureBundlePublicationError):
                write_first_failure_bundle(request, destination)

        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "first-failure"
            real_hash = _sha256
            def corrupt_after_publish(path: Path) -> str:
                value = real_hash(path)
                if path.parent == destination and path.name == "period-input.json":
                    return "0" * 64
                return value
            with patch("gridform_core.failure_evidence._sha256_file", side_effect=corrupt_after_publish):
                with self.assertRaises(FailureBundlePublicationError):
                    write_first_failure_bundle(request, destination)
            self.assertFalse(destination.exists())

    def test_bundle_rejects_extra_directory_empty_solver_and_missing_exception_identity(self) -> None:
        def publish(root: Path) -> tuple[FailureEvidenceRequest, Path]:
            run_context, year_context = _contexts()
            request = FailureEvidenceRequest(
                run_context, year_context, _period_input(), "solve",
                RuntimeError("solver failed"), _solver_evidence(), {"balance": 0.0},
            )
            destination = root / "first-failure"
            write_first_failure_bundle(request, destination)
            return request, destination

        def rewrite_member(destination: Path, name: str, payload: object) -> None:
            path = destination / name
            encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
            path.write_bytes(encoded)
            manifest_path = destination / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["members"][name] = {
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "size_bytes": len(encoded),
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with tempfile.TemporaryDirectory() as folder:
            request, destination = publish(Path(folder))
            extra = destination / "unhashed-extra"
            extra.mkdir()
            (extra / "payload.bin").write_bytes(b"unhashed")
            with self.assertRaises(FailureBundlePublicationError):
                write_first_failure_bundle(request, destination)
        with tempfile.TemporaryDirectory() as folder:
            request, destination = publish(Path(folder))
            rewrite_member(destination, "solver.json", {})
            with self.assertRaises(FailureBundlePublicationError):
                write_first_failure_bundle(request, destination)
        with tempfile.TemporaryDirectory() as folder:
            request, destination = publish(Path(folder))
            error = json.loads((destination / "error.json").read_text(encoding="utf-8"))
            error.pop("exception_qualname")
            rewrite_member(destination, "error.json", error)
            with self.assertRaises(FailureBundlePublicationError):
                write_first_failure_bundle(request, destination)

    def test_recovery_rejects_run_hash_mismatch_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(2026, 0, SHA_B))
            ledger.close_unsealed()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE context_registry SET sha256=? WHERE context_scope='run' AND year=-1",
                    ("f" * 64,),
                )
                connection.commit()
            with self.assertRaisesRegex(ValueError, "RunContext registry"):
                cleanup_incomplete_v8_year(
                    database, year=2026, expected_run_context_sha256=SHA_A,
                    expected_committed_period=0,
                    expected_year_context_sha256=SHA_B,
                )
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM period_integrity WHERE year=2026"
                ).fetchone()[0], 1)
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(2026, 0, SHA_B))
            ledger.close_unsealed()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE year_integrity SET run_context_sha256=? WHERE year=2026",
                    ("f" * 64,),
                )
                connection.commit()
            with self.assertRaisesRegex(ValueError, "RunContext SHA-256"):
                cleanup_incomplete_v8_year(
                    database, year=2026, expected_run_context_sha256=SHA_A,
                    expected_committed_period=0,
                    expected_year_context_sha256=SHA_B,
                )
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM period_integrity WHERE year=2026"
                ).fetchone()[0], 1)

    def test_each_distinct_interruption_gets_a_content_addressed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            recovery_dir = Path(folder) / "recovery"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(2026, 0, SHA_B))
            ledger.close_unsealed()
            first = recover_incomplete_v8_year(
                database, year=2026, expected_run_context_sha256=SHA_A,
                expected_committed_period=0,
                expected_year_context_sha256=SHA_B, diagnostic_directory=recovery_dir,
            )
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.record_period_batch(_batch(2026, 0, SHA_B))
            ledger.record_period_batch(_batch(2026, 1, SHA_B))
            ledger.close_unsealed()
            second = recover_incomplete_v8_year(
                database, year=2026, expected_run_context_sha256=SHA_A,
                expected_committed_period=1,
                expected_year_context_sha256=SHA_B, diagnostic_directory=recovery_dir,
            )
            self.assertNotEqual(first["diagnostic_sha256"], second["diagnostic_sha256"])
            self.assertNotEqual(first["diagnostic_database"], second["diagnostic_database"])
            with closing(sqlite3.connect(second["diagnostic_database"])) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM period_integrity WHERE year=2026"
                ).fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
