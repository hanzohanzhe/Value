from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core.clearing_inputs import ClearingInputRow, ClearingOutcomeRow
from gridform_core.market_ledger import (
    DispatchSummaryRow,
    OrderLedgerRow,
    PeriodLedgerRow,
    SQLiteMarketLedger,
    build_market_period_batch,
    create_market_ledger,
    query_market_table,
)
from gridform_core.market_replay import (
    query_legacy_staged_market_jsonl,
    market_replay_capabilities,
    query_dispatch_timeline,
)
from gridform_core.module_context import canonical_context_sha256
from gridform_core.replay_export import ReplayExportRequest, create_replay_export
from gridform_core.run_policy import resolve_run_policy
from gridform_core.run_snapshot import create_run_input_snapshot
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.zonal_contracts import ZonalNetworkPack, load_zonal_network_pack


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _period(index: int) -> PeriodLedgerRow:
    return PeriodLedgerRow(
        year=2025,
        period=index,
        stage="final_dispatch",
        forecast_demand_mwh=10.0,
        real_demand_mwh=10.0,
        accepted_supply_mwh=10.0,
        storage_charge_mwh=0.0,
        storage_discharge_mwh=0.0,
        flexible_demand_mwh=0.0,
        export_mwh=0.0,
        vre_available_mwh=4.0,
        vre_accepted_mwh=4.0,
        curtailed_mwh=0.0,
        import_mwh=0.0,
        clearing_price_gbp_per_mwh=50.0,
        physical_resource_cost_gbp=500.0,
        market_payment_gbp=500.0,
        policy_transfer_gbp=0.0,
        blackout_mwh=0.0,
        excess_mwh=0.0,
        energy_balance_residual_mwh=0.0,
    )


def _write_snapshot(
    run_root: Path, *, restricted: bool, trace_level: str,
    rights_case: str = "declared", include_network: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    source = run_root / "snapshot-source" / "pack"
    data = source / "files" / "demand.csv"
    data.parent.mkdir(parents=True)
    source_bytes = b"RESTRICTED-SOURCE-BYTES" if restricted else b"redistributable-source"
    data.write_bytes(source_bytes)
    policy = "local-use-only" if restricted else "redistributable"
    binding = {
        "uri": "files/demand.csv",
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "redistribution_policy": policy,
    }
    bindings: dict[str, object] = {"demand.real": binding}
    if rights_case == "unknown":
        binding["redistribution_policy"] = "redistributable_future_unknown"
    manifest = {
        "schema_version": "value.data-pack/v1",
        "id": "pack-123",
        "bindings": bindings,
    }
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    selected = {
        "psm": "value-staged-bid-at-cost-psm",
        "balancing": "value-copperplate-balancing",
        "investment": "agent-investment",
        "pipeline": "planning-pipeline",
        "vre_cap": "vre-expansion-cap",
        "storage_cap": "value-storage-expansion-policy",
        "storage_cost": "dynamic-annual-storage-cost",
    }
    project = {
        "schema_version": "value.project/v1",
        "id": "study-123",
        "revision": 7,
        "revision_sha256": "1" * 64,
        "start_year": 2025,
        "end_year": 2025,
        "data_pack_id": "pack-123",
        "modules": selected,
        "runtime_options": {"runtime.market_trace_level": trace_level},
    }
    network_source = None
    if include_network:
        network_source = run_root / "snapshot-source" / "network-pack"
        shutil.copytree(
            Path(__file__).resolve().parents[1] / "examples" / "zonal-network-pack",
            network_source,
        )
        network_manifest_path = network_source / "manifest.json"
        network_manifest = json.loads(network_manifest_path.read_text(encoding="utf-8"))
        network_manifest["data_pack_type"] = "network_overlay"
        payload_by_role: dict[str, object] = {}
        for role, raw_binding in network_manifest["bindings"].items():
            binding = dict(raw_binding)
            network_file = network_source / binding["uri"]
            binding["sha256"] = _sha256(network_file)
            network_manifest["bindings"][role] = binding
            payload_by_role[role] = json.loads(network_file.read_text(encoding="utf-8"))
        spatial_audit = dict(payload_by_role["value.zonal.spatial-audit"])
        spatial_audit["source_sha256_by_role"] = {
            role: binding["sha256"]
            for role, binding in network_manifest["bindings"].items()
        }
        identity = dict(network_manifest["zonal_network_pack"])
        canonical_network = ZonalNetworkPack.from_dict({
            "network_pack_id": identity["network_pack_id"],
            "scientific_sha256": "",
            "zones": payload_by_role["value.zonal.zones"]["zones"],
            "corridors": payload_by_role["value.zonal.corridors"]["corridors"],
            "cutsets": payload_by_role["value.zonal.cutsets"]["cutsets"],
            "asset_mappings": payload_by_role["value.zonal.asset-map"]["asset_mappings"],
            "zonal_demand": payload_by_role["value.zonal.demand"]["zonal_demand"],
            "rating_profiles": payload_by_role["value.zonal.ratings"]["rating_profiles"],
            "interconnector_landings": payload_by_role[
                "value.zonal.interconnector-landings"
            ]["interconnector_landings"],
            "spatial_audit": spatial_audit,
            "loss_capability_absent_reason": identity["loss_capability_absent_reason"],
            "geometry_artifact": identity.get("geometry_artifact"),
            "provenance": identity.get("provenance", {}),
        })
        identity["scientific_sha256"] = canonical_network.compute_scientific_sha256()
        network_manifest["zonal_network_pack"] = identity
        network_manifest_path.write_text(json.dumps(network_manifest), encoding="utf-8")
        project["market_configuration"] = {
            "network_pack_id": network_manifest["id"],
        }
    registry = workspace_registry(run_root / "no-local-modules")
    snapshot = create_run_input_snapshot(
        run_dir=run_root,
        project=project,
        pack_root=source,
        registry=registry,
        selected=selected,
        object_root=run_root / "snapshot-objects",
        network_pack_root=network_source,
    )
    if rights_case in {"empty", "incomplete"}:
        frozen_manifest_path = run_root / "input-snapshot" / "pack" / "manifest.json"
        frozen_manifest = json.loads(frozen_manifest_path.read_text(encoding="utf-8"))
        if rights_case == "empty":
            frozen_manifest["bindings"] = {}
            frozen_manifest["source_bytes"] = "RESTRICTED-SOURCE-BYTES"
        else:
            frozen_manifest["bindings"] = {
                "demand.real": {"redistribution_policy": "redistributable"},
            }
        frozen_manifest_path.write_text(
            json.dumps(frozen_manifest, indent=2), encoding="utf-8",
        )
        snapshot["pack_manifest_sha256"] = _canonical_sha256(frozen_manifest)
        snapshot["module_resolution_graph"] = registry.resolve_selection(
            selected,
            available_data_roles=tuple(sorted(frozen_manifest["bindings"])),
        ).to_dict()
        identity_keys = (
            "project_sha256", "pack_manifest_sha256", "objects", "modules",
            "network_pack_id", "network_pack_manifest_sha256", "extension_graph",
        )
        identity = {key: snapshot[key] for key in identity_keys if key in snapshot}
        snapshot["snapshot_id"] = _canonical_sha256(identity)
        snapshot["input_tree_sha256"] = snapshot["snapshot_id"]
        (run_root / "input-snapshot" / "snapshot.json").write_text(
            json.dumps(snapshot, indent=2), encoding="utf-8",
        )
    return project, snapshot


def _write_v8_run(
    run_root: Path, *, trace_level: str, periods: int = 48,
    restricted: bool = False, rights_case: str = "declared",
    include_network: bool = False, tamper_network_context: bool = False,
) -> Path:
    market = run_root / "model-output" / "market"
    context = market / "context"
    context.mkdir(parents=True)
    project, snapshot = _write_snapshot(
        run_root, restricted=restricted, trace_level=trace_level,
        rights_case=rights_case, include_network=include_network,
    )
    pack_manifest = json.loads(
        (run_root / "input-snapshot" / "pack" / "manifest.json").read_text("utf-8")
    )
    balancing = workspace_registry(run_root / "no-local-modules").manifest(
        "value-copperplate-balancing", expected_slot="balancing"
    )
    network_context = None
    if include_network:
        frozen_network = run_root / "input-snapshot" / "network-pack"
        network_context = load_zonal_network_pack(frozen_network, topology_policy="audit").to_dict()
        if tamper_network_context:
            network_context["scientific_sha256"] = "f" * 64
    run_context = {
        "schema_version": "value.run-static-context/v1",
        "run_id": "run-123",
        "study_revision_sha256": "1" * 64,
        "start_year": 2025,
        "end_year": 2025,
        "period_hours": 0.5,
        "data_pack": {
            "data_pack_id": "pack-123",
            "manifest_sha256": snapshot["pack_manifest_sha256"],
            "scientific_sha256": pack_manifest.get("scientific_sha256"),
            "bindings": pack_manifest["bindings"],
        },
        "module_graph": snapshot["module_resolution_graph"],
        "scientific_parameters": {},
        "runtime_controls": {},
        "trace_profile": trace_level,
        "solver_contract": dict(balancing.solver_contract),
        "market_configuration": {},
        "network_pack": network_context,
    }
    run_context_sha256 = canonical_context_sha256(run_context)
    year_context = {
        "schema_version": "value.year-context/v1",
        "run_id": "run-123",
        "year": 2025,
        "run_context_sha256": run_context_sha256,
        "operating_state": {},
        "frozen_zone_shares": {},
        "opening_soc_mwh_by_asset": {},
        "transition_lineage": {},
    }
    year_context_sha256 = canonical_context_sha256(year_context)
    (context / "run-context.json").write_text(json.dumps(run_context), encoding="utf-8")
    (context / "year-2025.json").write_text(json.dumps(year_context), encoding="utf-8")
    (run_root / "status.json").write_text(
        json.dumps({
            "id": "run-123",
            "status": "completed",
            "execution_status": "passed",
            "mode": "validation_24h",
            "run_policy": resolve_run_policy("validation_24h").to_dict(project),
            "input_snapshot_id": snapshot["snapshot_id"],
            "input_tree_sha256": snapshot["input_tree_sha256"],
        }),
        encoding="utf-8",
    )
    database = market / "market.sqlite"
    ledger = SQLiteMarketLedger(
        database,
        trace_level=trace_level,
        semantic_metadata={
            "run_id": "run-123",
            "period_hours": 0.5,
            "run_context_artifact_path": "market/context/run-context.json",
            "year_context_artifact_path": "market/context/year-2025.json",
        },
    )
    for index in range(periods):
        full_rows: dict[str, tuple[object, ...]] = {}
        if trace_level == "full":
            declared = ClearingInputRow.create(
                year=2025,
                period=index,
                stage="ahead",
                information_scope="forecast only",
                payload={
                    "period_id": f"2025:{index}",
                    "period_hours": 0.5,
                    "offers": [{
                        "offer_id": f"offer-{index}",
                        "asset_id": "gas-a",
                        "offer_price_gbp_per_mwh": 50.0,
                        "maximum_power_mw": 20.0,
                    }],
                },
            )
            outcome = ClearingOutcomeRow.create(
                declared.input_sha256,
                {"accepted": [{"asset_id": "gas-a", "accepted_power_mw": 20.0}]},
            )
            order = OrderLedgerRow(
                f"order-{index}", 2025, index, "ahead", "gas-a", "thermal",
                "supply", 50.0, 10.0, 10.0, "accepted", "cleared", 500.0, 500.0,
            )
            full_rows = {
                "clearing_inputs": (declared,),
                "clearing_outcomes": (outcome,),
                "orders": (order,),
            }
        ledger.record_period_batch(build_market_period_batch(
            period=_period(index),
            dispatch_summary=(
                DispatchSummaryRow(2025, index, "final_dispatch", "GB", "ccgt", 10.0),
            ),
            full_rows=full_rows,
            run_context_sha256=run_context_sha256,
            year_context_sha256=year_context_sha256,
        ))
    ledger.close()
    return database


class Prompt123BoundedReplayExportTests(unittest.TestCase):
    def test_frozen_snapshot_module_pack_and_network_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="full", periods=1)
            snapshot_path = run_root / "input-snapshot" / "snapshot.json"
            original_snapshot = snapshot_path.read_text(encoding="utf-8")
            snapshot = json.loads(original_snapshot)
            snapshot["modules"][0]["module_id"] = "tampered-module"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frozen snapshot identity"):
                create_replay_export(
                    database,
                    ReplayExportRequest("period", 2025, 0, 0, "zip"),
                    run_root / "model-output" / "exports" / "module-tamper.zip",
                )

            snapshot_path.write_text(original_snapshot, encoding="utf-8")
            pack_path = run_root / "input-snapshot" / "pack" / "manifest.json"
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            pack["id"] = "tampered-pack"
            pack_path.write_text(json.dumps(pack), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frozen snapshot identity"):
                create_replay_export(
                    database,
                    ReplayExportRequest("period", 2025, 0, 0, "zip"),
                    run_root / "model-output" / "exports" / "pack-tamper.zip",
                )

            network_root = Path(folder) / "network-run"
            network_database = _write_v8_run(
                network_root,
                trace_level="full",
                periods=1,
                include_network=True,
                tamper_network_context=True,
            )
            with self.assertRaisesRegex(ValueError, "network-pack identity"):
                create_replay_export(
                    network_database,
                    ReplayExportRequest("period", 2025, 0, 0, "zip"),
                    network_root / "model-output" / "exports" / "network-tamper.zip",
                )

    def test_modified_v8_rows_or_roots_fail_integrity_before_export(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="full", periods=1)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE period_summary SET accepted_supply_mwh=999 "
                    "WHERE year=2025 AND period=0"
                )
                connection.execute(
                    "UPDATE year_integrity SET science_root=? WHERE year=2025",
                    ("f" * 64,),
                )
                connection.commit()
            with self.assertRaisesRegex(ValueError, "ledger integrity"):
                create_replay_export(
                    database,
                    ReplayExportRequest("period", 2025, 0, 0, "zip"),
                    run_root / "model-output" / "exports" / "tampered-ledger.zip",
                )

    def test_complete_export_uses_frozen_policy_expected_period_count(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="full", periods=1)
            with self.assertRaisesRegex(ValueError, "expected 48 periods"):
                create_replay_export(
                    database,
                    ReplayExportRequest("complete", None, None, None, "zip"),
                    run_root / "model-output" / "exports" / "pseudo-complete.zip",
                )

    def test_complete_export_requires_completed_run_full_plan_and_closed_year(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="full", periods=48)
            destination = run_root / "model-output" / "exports" / "complete.zip"
            status_path = run_root / "status.json"
            project_path = run_root / "input-snapshot" / "project.json"

            status_path.write_text(json.dumps({"status": "running"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "completed Run"):
                create_replay_export(
                    database, ReplayExportRequest("complete", None, None, None, "zip"), destination,
                )

            status_path.write_text(
                json.dumps({"status": "completed", "execution_status": "running"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "completed Run"):
                create_replay_export(
                    database, ReplayExportRequest("complete", None, None, None, "zip"), destination,
                )

            status_path.write_text(
                json.dumps({"status": "completed", "execution_status": "passed"}),
                encoding="utf-8",
            )
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project["end_year"] = 2026
            project_path.write_text(json.dumps(project), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "planned years"):
                create_replay_export(
                    database, ReplayExportRequest("complete", None, None, None, "zip"), destination,
                )

            project["end_year"] = 2025
            project_path.write_text(json.dumps(project), encoding="utf-8")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("UPDATE year_integrity SET period_count=49 WHERE year=2025")
                connection.commit()
            with self.assertRaisesRegex(ValueError, "period closure"):
                create_replay_export(
                    database, ReplayExportRequest("complete", None, None, None, "zip"), destination,
                )

    def test_context_registry_tampering_fails_closed_before_export(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="full", periods=1)
            context = run_root / "model-output" / "market" / "context" / "run-context.json"
            payload = json.loads(context.read_text(encoding="utf-8"))
            payload["run_id"] = "tampered"
            context.write_text(json.dumps(payload), encoding="utf-8")
            destination = run_root / "model-output" / "exports" / "tampered.zip"

            with self.assertRaisesRegex(ValueError, "context identity|ledger integrity"):
                create_replay_export(
                    database, ReplayExportRequest("period", 2025, 0, 0, "zip"), destination,
                )
            self.assertFalse(destination.exists())

            payload["run_id"] = "run-123"
            context.write_text(json.dumps(payload), encoding="utf-8")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE year_integrity SET run_context_sha256=? WHERE year=2025",
                    ("f" * 64,),
                )
                connection.commit()
            with self.assertRaisesRegex(ValueError, "context identity|ledger integrity"):
                create_replay_export(
                    database, ReplayExportRequest("period", 2025, 0, 0, "zip"), destination,
                )

    def test_empty_or_unknown_rights_are_reference_only_and_manifest_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for rights_case in ("empty", "unknown", "incomplete"):
                with self.subTest(rights_case=rights_case):
                    run_root = Path(folder) / rights_case
                    database = _write_v8_run(
                        run_root, trace_level="full", periods=1,
                        rights_case=rights_case,
                    )
                    destination = (
                        run_root / "model-output" / "exports" / "rights.zip"
                    )
                    result = create_replay_export(
                        database,
                        ReplayExportRequest("period", 2025, 0, 0, "zip"),
                        destination,
                    )
                    with zipfile.ZipFile(destination) as archive:
                        archive_bytes = b"".join(
                            archive.read(name) for name in archive.namelist()
                        )
                    self.assertEqual(
                        result["portability"], "reference_only_not_portable"
                    )
                    self.assertNotIn(b"RESTRICTED-SOURCE-BYTES", archive_bytes)

    def test_completed_legacy_jsonl_reader_is_bounded_exact_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "legacy-run"
            market = run_root / "model-output" / "market"
            market.mkdir(parents=True)
            source = market / "staged-market.jsonl"
            rows = [
                {"contract_type": "AheadMarketResult", "payload": {"year": 2025, "period": 0}},
                {"contract_type": "AheadMarketResult", "payload": {"year": 2025, "period": 100}},
            ]
            source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            legacy_adapter = create_market_ledger(market / "market.sqlite", "summary")
            legacy_adapter.record_period(_period(0))
            legacy_adapter.record_period(_period(100))
            legacy_adapter.close()
            with closing(sqlite3.connect(market / "market.sqlite")) as connection:
                connection.execute(
                    "UPDATE metadata SET value='gridform.market-ledger/v7' "
                    "WHERE key='schema_version'"
                )
                connection.commit()
            (run_root / "status.json").write_text(
                json.dumps({"status": "completed", "execution_status": "passed"}), encoding="utf-8",
            )
            before = _sha256(source)

            page = query_legacy_staged_market_jsonl(
                run_root, year=2025, period_from=0, period_to=100, limit=1, offset=1,
            )
            self.assertEqual(page["total"], 2)
            self.assertEqual(page["items"][0]["payload"]["period"], 100)
            self.assertEqual(_sha256(source), before)
            timeline = query_dispatch_timeline(
                market / "market.sqlite",
                year=2025,
                resolution="daily",
                period_from=0,
                period_to=100,
                limit=1,
                offset=1,
            )
            self.assertEqual(timeline["total"], 2)
            self.assertEqual(timeline["items"][0]["period_start"], 100)

            (run_root / "status.json").write_text(json.dumps({"status": "running"}), encoding="utf-8")
            with self.assertRaisesRegex(LookupError, "completed legacy Run"):
                query_legacy_staged_market_jsonl(
                    run_root, year=2025, period_from=0, period_to=100, limit=1, offset=0,
                )

    def test_v8_query_is_stable_exact_bounded_and_summary_is_truthful(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = _write_v8_run(Path(folder) / "run", trace_level="summary", periods=12)
            before = _sha256(database)
            page = query_market_table(
                database,
                "period_summary",
                year=2025,
                period_from=3,
                period_to=8,
                limit=2,
                offset=1,
            )
            timeline = query_dispatch_timeline(
                database,
                year=2025,
                resolution="half_hour",
                period_from=3,
                period_to=5,
                limit=2,
                offset=0,
            )
            capabilities = market_replay_capabilities(database)

            self.assertEqual(page["total"], 6)
            self.assertEqual([row["period"] for row in page["items"]], [4, 5])
            self.assertEqual([row["period_start"] for row in timeline["items"]], [3, 4])
            self.assertEqual(timeline["total"], 3)
            self.assertEqual(timeline["items"][0]["flows"], [{
                "technology": "ccgt",
                "raw_technology": "ccgt",
                "flow_type": "accepted_dispatch",
                "role": "supply",
                "stage": "final_dispatch",
                "zone_id": "GB",
                "evidence_scope": "zone:GB;stage:final_dispatch",
                "energy_mwh": 10.0,
                "balance_component_mwh": 10.0,
            }])
            self.assertFalse(capabilities["bid_replay_available"])
            self.assertIn("Bid-level detail was not recorded", capabilities["bid_replay_missing_reason"])
            self.assertEqual(_sha256(database), before)
            with self.assertRaisesRegex(ValueError, "between 1 and 1000"):
                query_market_table(database, "period_summary", limit=1001)

    def test_v7_fallback_is_read_only_and_accepts_the_same_range_contract(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = create_market_ledger(database, "summary")
            for index in range(5):
                ledger.record_period(_period(index))
            ledger.close()
            before = _sha256(database)
            page = query_market_table(
                database,
                "period_summary",
                year=2025,
                period_from=1,
                period_to=3,
                limit=2,
                offset=1,
            )
            self.assertEqual(page["total"], 3)
            self.assertEqual([row["period"] for row in page["items"]], [2, 3])
            self.assertEqual(_sha256(database), before)

    def test_full_24_hour_zip_is_self_describing_and_preserves_the_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="full")
            destination = run_root / "model-output" / "exports" / "day.zip"
            before = _sha256(database)
            result = create_replay_export(
                database,
                ReplayExportRequest("24_hours", 2025, 0, None, "zip"),
                destination,
            )
            with zipfile.ZipFile(destination) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))

            self.assertEqual(result["period_count"], 48)
            self.assertEqual(manifest["portability"], "portable")
            self.assertIn("contexts/run-context.json", names)
            self.assertIn("contexts/year-2025.json", names)
            self.assertIn("study/project.json", names)
            self.assertIn("study/input-snapshot.json", names)
            self.assertIn("identity/module-solver.json", names)
            self.assertIn("integrity/roots.json", names)
            self.assertEqual(len([name for name in names if name.endswith("/input.json")]), 48)
            self.assertEqual(len([name for name in names if name.endswith("/outcome.json")]), 48)
            self.assertEqual(set(manifest["members"]), names - {"manifest.json"})
            self.assertTrue(all(len(row["sha256"]) == 64 for row in manifest["members"].values()))
            self.assertEqual(_sha256(database), before)
            self.assertFalse(any(destination.parent.glob(".day.zip.*.tmp")))

    def test_restricted_pack_is_reference_only_and_never_copies_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="full", restricted=True)
            destination = run_root / "model-output" / "exports" / "restricted.zip"
            result = create_replay_export(
                database,
                ReplayExportRequest("period", 2025, 0, 0, "zip"),
                destination,
            )
            with zipfile.ZipFile(destination) as archive:
                names = archive.namelist()
                manifest = json.loads(archive.read("manifest.json"))
                archive_bytes = b"".join(archive.read(name) for name in names)
            self.assertEqual(result["portability"], "reference_only_not_portable")
            self.assertEqual(manifest["portability"], "reference_only_not_portable")
            self.assertNotIn(b"RESTRICTED-SOURCE-BYTES", archive_bytes)
            self.assertFalse(any(name.startswith("input-snapshot/pack/files/") for name in names))

    def test_jsonl_requires_an_explicit_bounded_range_and_confined_destination(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="summary", periods=3)
            export_root = run_root / "model-output" / "exports"
            destination = export_root / "period.jsonl"
            before = _sha256(database)
            result = create_replay_export(
                database,
                ReplayExportRequest("period", 2025, 1, 1, "jsonl"),
                destination,
            )
            rows = [json.loads(line) for line in destination.read_text("utf-8").splitlines()]

            self.assertEqual(result["period_count"], 1)
            self.assertEqual([row["period"] for row in rows], [1])
            self.assertEqual(_sha256(database), before)
            with self.assertRaisesRegex(ValueError, "only as a replay ZIP"):
                create_replay_export(
                    database,
                    ReplayExportRequest("complete", None, None, None, "jsonl"),
                    export_root / "whole-run.jsonl",
                )
            with self.assertRaisesRegex(ValueError, "inside the run export root"):
                create_replay_export(
                    database,
                    ReplayExportRequest("period", 2025, 0, 0, "jsonl"),
                    run_root / "escaped.jsonl",
                )
            with self.assertRaisesRegex(ValueError, "new file"):
                create_replay_export(
                    database,
                    ReplayExportRequest("period", 2025, 1, 1, "jsonl"),
                    destination,
                )

    def test_background_job_returns_before_export_and_publishes_job_record(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_root = Path(folder) / "run"
            database = _write_v8_run(run_root, trace_level="full", periods=1)
            started = threading.Event()
            release = threading.Event()

            def delayed_export(db: Path, request: ReplayExportRequest, destination: Path):
                self.assertEqual(db, database)
                started.set()
                release.wait(5)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"export")
                return {"schema_version": "value.replay-export/v1", "bytes": 6}

            with patch.object(server, "create_replay_export", side_effect=delayed_export):
                job = server.create_replay_export_job(
                    run_root,
                    ReplayExportRequest("period", 2025, 0, 0, "zip"),
                )
                self.assertTrue(started.wait(2))
                live = server.read_replay_export_job(run_root, str(job["job_id"]))
                self.assertIn(live["status"], {"queued", "running"})
                release.set()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    live = server.read_replay_export_job(run_root, str(job["job_id"]))
                    if live["status"] == "completed":
                        break
                    time.sleep(0.01)

            self.assertEqual(live["status"], "completed")
            self.assertTrue(Path(str(live["artifact_path"])).is_file())
            self.assertTrue((run_root / "model-output" / "exports" / "jobs" / f"{job['job_id']}.json").is_file())


if __name__ == "__main__":
    unittest.main()
