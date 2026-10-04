from __future__ import annotations

import json
import random
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from gridform_core.module_context import (
    RunStaticContext,
    YearContext,
    canonical_context_sha256,
)
from gridform_core.preflight_resources import (
    ResourceCalibrationKey,
    ResourceEstimate,
    ResourceHeadroomBounds,
    build_frozen_resource_contexts,
    estimate_run_resources,
    evaluate_resource_gate,
    selected_staged_zonal_calibration_runner,
    resource_readiness_from_snapshot,
)
from gridform_core.project_revision import attach_revision_identity
from gridform_core.run_snapshot import (
    SnapshotError,
    create_run_input_snapshot,
    verify_run_input_snapshot,
)
from gridform_core.value_101 import value_101_study
from gridform_core.value_101_lifecycle import build_value_101_network_pair
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection
from gridform_core.run_input_snapshot import (
    ResourceSnapshotMismatch,
    freeze_resource_readiness,
    verify_frozen_resource_readiness,
)
from gridform_core.run_quota import RunQuotaPolicy, reserve_run_space


GIB = 1024**3
ROOT = Path(__file__).resolve().parents[1]
VALUE_101_NETWORK = ROOT / "data-packs" / "value-101-network-v1"


def _contexts(*, zones: int, boundaries: int, assets: int, storage: int, trace: str):
    zone_ids = [f"z{index}" for index in range(zones)]
    boundary_rows = [
        {"boundary_id": f"b{index}", "from_zone": zone_ids[index % zones],
         "to_zone": zone_ids[(index + 1) % zones]}
        for index in range(boundaries)
    ]
    asset_rows = {
        f"g{index}": {
            "asset_id": f"g{index}",
            "technology": "CCGT" if index % 2 == 0 else "wind",
            "zone": zone_ids[index % zones],
        }
        for index in range(assets)
    }
    storage_rows = {
        f"s{index}": {
            "asset_id": f"s{index}", "technology": "battery",
            "zone": zone_ids[index % zones],
        }
        for index in range(storage)
    }
    run_context = RunStaticContext(
        run_id="prompt122-run",
        study_revision_sha256="a" * 64,
        start_year=2025,
        end_year=2026,
        period_hours=0.5,
        data_pack={"data_pack_id": "pack", "manifest_sha256": "b" * 64},
        module_graph={
            "graph_sha256": "c" * 64,
            "slots": {
                "psm": {"id": "value-staged-bid-at-cost-psm", "sha256": "d" * 64},
                "balancing": {"id": "value-zonal-redispatch-balancing", "sha256": "e" * 64},
            },
        },
        scientific_parameters={"clock.period_hours": 0.5},
        runtime_controls={"runtime.market_trace_level": trace},
        trace_profile=trace,
        solver_contract={"method": "highs", "version": "fixture"},
        market_configuration={"zonal_demand_mode": "network_pack_absolute_demand"},
        network_pack={
            "network_pack_id": "network",
            "scientific_sha256": "f" * 64,
            "zones": zone_ids,
            "boundaries": boundary_rows,
        },
    )
    year_context = YearContext(
        run_id=run_context.run_id,
        year=2025,
        run_context_sha256=canonical_context_sha256(run_context),
        operating_state={
            "assets": asset_rows,
            "storage": storage_rows,
            "resource_class_by_asset": {
                **{key: value["technology"] for key, value in asset_rows.items()},
                **{key: "storage" for key in storage_rows},
            },
        },
        frozen_zone_shares={
            **{key: {value["zone"]: 1.0} for key, value in asset_rows.items()},
            **{key: {value["zone"]: 1.0} for key, value in storage_rows.items()},
        },
        opening_soc_mwh_by_asset={key: 1.0 for key in storage_rows},
        transition_lineage={"opening": "fixture"},
    )
    return run_context, year_context


def _project(trace: str):
    return {
        "id": "study",
        "modules": {
            "psm": "value-staged-bid-at-cost-psm",
            "balancing": "value-zonal-redispatch-balancing",
        },
        "runtime_options": {"runtime.market_trace_level": trace},
    }


def _headroom(*, assets_per_year: int = 0, storage_per_year: int = 0, years: int = 2):
    return ResourceHeadroomBounds(
        source_modules=("vre-expansion-cap", "value-storage-expansion-policy"),
        annual_asset_additions=tuple(assets_per_year for _ in range(years)),
        annual_storage_additions=tuple(storage_per_year for _ in range(years)),
    )


def _write_cache(root: Path, key: ResourceCalibrationKey, *, bytes_per_period=4096):
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "value.resource-calibration/v1",
        "calibration_key": key.to_dict(),
        "periods": 48,
        "persisted_bytes_per_period": bytes_per_period,
        "temporary_bytes_per_period": 1024,
        "seconds_per_period": 0.25,
    }
    (root / key.cache_filename).write_text(json.dumps(payload), encoding="utf-8")


class Prompt122PreflightResourceGateTests(unittest.TestCase):
    def test_free_space_reserve_does_not_consume_the_per_run_output_quota(self):
        estimate = ResourceEstimate(
            persisted_bytes=2 * GIB,
            temporary_bytes=1 * GIB,
            reserve_bytes=80 * GIB,
            runtime_seconds=1.0,
            trace_profile="summary",
            calibration_basis={},
            row_cardinality={},
        )

        decision = evaluate_resource_gate(
            estimate,
            free_bytes=700 * GIB,
            quota_policy=RunQuotaPolicy(
                global_quota_bytes=100 * GIB,
                per_run_quota_bytes=20 * GIB,
                minimum_free_bytes=2 * GIB,
            ),
        )

        self.assertTrue(decision["accepted"])
        self.assertEqual(decision["estimated_output_bytes"], 3 * GIB)
        self.assertEqual(decision["required_free_bytes"], 83 * GIB)

    def _snapshot_value_101(self, root: Path):
        registry = workspace_registry(root / "no-local-modules")
        pair, _identity = build_value_101_network_pair(
            value_101_study(), network_pack_id="value-101-network-v1"
        )
        project = pair["constrained"]
        selection = resolve_zonal_pack_selection(
            project,
            base_pack_root=VALUE_101_NETWORK,
            explicit_network_pack_root=VALUE_101_NETWORK,
        )
        project = attach_revision_identity(
            project, registry, selection.revision_manifest
        )
        run_dir = root / "runs" / "value-101-resource"
        run_dir.mkdir(parents=True)
        create_run_input_snapshot(
            run_dir=run_dir,
            project=project,
            pack_root=VALUE_101_NETWORK,
            network_pack_root=VALUE_101_NETWORK,
            registry=registry,
            selected=dict(project["modules"]),
            object_root=root / "objects",
        )
        return project, registry, run_dir / "input-snapshot"

    def test_real_value_101_snapshot_normalization_is_accepted_but_tampering_is_rejected(self):
        policy = {"total_periods": 96, "years": 2, "periods_per_year": 48}

        def calibration(request):
            return {
                "periods": request["periods"],
                "persisted_bytes": 48_000,
                "temporary_bytes": 12_000,
                "runtime_seconds": 1.0,
            }

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project, registry, snapshot_root = self._snapshot_value_101(root)
            estimate, decision, evidence = resource_readiness_from_snapshot(
                project=project,
                policy=policy,
                run_id="value-101-resource",
                snapshot_root=snapshot_root,
                registry=registry,
                calibration_root=root / "calibration",
                selected_output_root=root / "runs",
                free_bytes=200 * GIB,
                target_volume_bytes=400 * GIB,
                quota_policy=RunQuotaPolicy(
                    minimum_free_bytes=0,
                    per_run_quota_bytes=100 * GIB,
                    global_quota_bytes=500 * GIB,
                ),
                calibration_runner=calibration,
            )
            self.assertTrue(decision["accepted"])
            self.assertGreater(estimate.required_bytes, 0)
            freeze_resource_readiness(snapshot_root, evidence)
            actual_run, actual_year, actual_headroom = build_frozen_resource_contexts(
                project=project,
                policy=policy,
                run_id="value-101-resource",
                pack_root=snapshot_root / "pack",
                network_pack_root=snapshot_root / "network-pack",
                registry=registry,
            )
            actual_key = ResourceCalibrationKey.from_inputs(
                project=project, policy=policy, run_context=actual_run,
                trace_profile=actual_run.trace_profile,
                headroom_bounds=actual_headroom,
            )
            verify_frozen_resource_readiness(
                snapshot_root,
                project=project,
                selected_output_root=root / "runs",
                actual_run_context=actual_run,
                actual_year_context=actual_year,
                actual_calibration_key=actual_key.to_dict(),
            )
            manifest_path = snapshot_root / "pack" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["snapshot_frozen"] = False
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SnapshotError):
                verify_run_input_snapshot(snapshot_root, registry)

    def test_real_value_101_uncapped_investment_group_changes_bound_key_and_bytes(self):
        policy = {"total_periods": 96, "years": 2, "periods_per_year": 48}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project, registry, snapshot_root = self._snapshot_value_101(root)
            run_context, year_context, bounds = build_frozen_resource_contexts(
                project=project, policy=policy, run_id="value-101-resource",
                pack_root=snapshot_root / "pack",
                network_pack_root=snapshot_root / "network-pack",
                registry=registry,
            )
            undercount = ResourceHeadroomBounds(
                source_modules=bounds.source_modules,
                annual_asset_additions=(3, 3),
                annual_storage_additions=(1, 1),
            )
            correct = estimate_run_resources(
                project=project, policy=policy, run_context=run_context,
                year_context=year_context, headroom_bounds=bounds,
                calibration_root=root / "correct", free_bytes=200 * GIB,
                quota_policy=RunQuotaPolicy(minimum_free_bytes=0),
            )
            low = estimate_run_resources(
                project=project, policy=policy, run_context=run_context,
                year_context=year_context, headroom_bounds=undercount,
                calibration_root=root / "low", free_bytes=200 * GIB,
                quota_policy=RunQuotaPolicy(minimum_free_bytes=0),
            )

        self.assertEqual(bounds.annual_asset_additions, (4, 4))
        self.assertEqual(bounds.annual_storage_additions, (1, 1))
        self.assertNotEqual(
            correct.calibration_basis["calibration_key"],
            low.calibration_basis["calibration_key"],
        )
        self.assertGreater(correct.persisted_bytes, low.persisted_bytes)
        self.assertGreater(correct.temporary_bytes, low.temporary_bytes)

    def test_summary_selected_graph_counts_exact_context_once_and_uses_multiplier(self):
        run_context, year_context = _contexts(
            zones=3, boundaries=2, assets=4, storage=1, trace="summary"
        )
        policy = {"total_periods": 96, "years": 2, "periods_per_year": 48}
        quota = RunQuotaPolicy(
            global_quota_bytes=500 * GIB,
            per_run_quota_bytes=100 * GIB,
            minimum_free_bytes=0,
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = ResourceCalibrationKey.from_inputs(
                project=_project("summary"), policy=policy,
                run_context=run_context, trace_profile="summary",
            )
            _write_cache(root, key)
            estimate = estimate_run_resources(
                project=_project("summary"), policy=policy,
                run_context=run_context, year_context=year_context,
                calibration_root=root, free_bytes=200 * GIB,
                quota_policy=quota, target_volume_bytes=400 * GIB,
            )

        self.assertEqual(estimate.trace_profile, "summary")
        self.assertEqual(estimate.calibration_basis["context_copies"], 1)
        self.assertGreaterEqual(estimate.calibration_basis["persisted_safety_multiplier"], 1.5)
        self.assertEqual(estimate.row_cardinality["zones"], 3)
        self.assertEqual(estimate.row_cardinality["boundaries"], 2)
        self.assertEqual(estimate.row_cardinality["assets"], 4)
        self.assertEqual(estimate.row_cardinality["storage_assets"], 1)
        self.assertEqual(estimate.row_cardinality["orders"], 0)
        self.assertEqual(estimate.reserve_bytes, 20 * GIB)

    def test_larger_full_graph_changes_exact_cardinalities_without_magic_pack_sizes(self):
        small_run, small_year = _contexts(
            zones=3, boundaries=2, assets=4, storage=1, trace="full"
        )
        large_run, large_year = _contexts(
            zones=7, boundaries=9, assets=11, storage=3, trace="full"
        )
        policy = {"total_periods": 48, "years": 1, "periods_per_year": 48}
        quota = RunQuotaPolicy(minimum_free_bytes=0, per_run_quota_bytes=100 * GIB)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for context in (small_run, large_run):
                _write_cache(
                    root,
                    ResourceCalibrationKey.from_inputs(
                        project=_project("full"), policy=policy,
                        run_context=context, trace_profile="full",
                    ),
                )
            small = estimate_run_resources(
                project=_project("full"), policy=policy, run_context=small_run,
                year_context=small_year, calibration_root=root,
                free_bytes=200 * GIB, quota_policy=quota,
            )
            large = estimate_run_resources(
                project=_project("full"), policy=policy, run_context=large_run,
                year_context=large_year, calibration_root=root,
                free_bytes=200 * GIB, quota_policy=quota,
            )

        self.assertEqual(large.row_cardinality["zone_period_summary"] - small.row_cardinality["zone_period_summary"], 4 * 48)
        self.assertEqual(large.row_cardinality["boundary_period_summary"] - small.row_cardinality["boundary_period_summary"], 7 * 48)
        self.assertEqual(large.row_cardinality["physical_dispatch"] - small.row_cardinality["physical_dispatch"], 7 * 48 * 2)
        self.assertGreater(large.row_cardinality["orders"], small.row_cardinality["orders"])

    def test_headroom_growth_changes_cache_identity_and_required_bytes(self):
        run_context, year_context = _contexts(
            zones=3, boundaries=2, assets=4, storage=1, trace="full"
        )
        project = _project("full")
        policy = {"total_periods": 96, "years": 2, "periods_per_year": 48}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            calls = []

            def calibration(request):
                calls.append(request["calibration_key"])
                return {
                    "periods": request["periods"],
                    "persisted_bytes": 48_000,
                    "temporary_bytes": 12_000,
                    "runtime_seconds": 1.0,
                }

            small = estimate_run_resources(
                project=project, policy=policy, run_context=run_context,
                year_context=year_context, calibration_root=root,
                free_bytes=200 * GIB,
                quota_policy=RunQuotaPolicy(minimum_free_bytes=0),
                headroom_bounds=_headroom(assets_per_year=1, years=2),
                calibration_runner=calibration,
            )
            large = estimate_run_resources(
                project=project, policy=policy, run_context=run_context,
                year_context=year_context, calibration_root=root,
                free_bytes=200 * GIB,
                quota_policy=RunQuotaPolicy(minimum_free_bytes=0),
                headroom_bounds=_headroom(
                    assets_per_year=250, storage_per_year=100, years=2
                ),
                calibration_runner=calibration,
            )

        self.assertEqual(len(calls), 2)
        self.assertNotEqual(
            small.calibration_basis["calibration_key"],
            large.calibration_basis["calibration_key"],
        )
        self.assertGreater(large.persisted_bytes, small.persisted_bytes)
        self.assertGreater(large.temporary_bytes, small.temporary_bytes)
        self.assertGreater(large.required_bytes, small.required_bytes)
        self.assertEqual(large.row_cardinality["current_assets"], 4)
        self.assertEqual(large.row_cardinality["assets"], 504)
        self.assertEqual(large.row_cardinality["storage_assets"], 201)
        self.assertGreater(
            large.calibration_basis["headroom_persisted_delta_bytes"], 0
        )
        self.assertGreater(
            large.calibration_basis["headroom_temporary_delta_bytes"], 0
        )

    def test_context_byte_counts_match_actual_production_publication_and_grow_by_year(self):
        from gridform_core.application import _atomic_json_artifact
        from gridform_core.module_context import ImmutableContextResolver
        from gridform_core.v2.orchestrator import publish_year_context

        run_context, year_context = _contexts(
            zones=3, boundaries=2, assets=4, storage=1, trace="summary"
        )
        policy = {"total_periods": 96, "years": 2, "periods_per_year": 48}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            estimate = estimate_run_resources(
                project=_project("summary"), policy=policy,
                run_context=run_context, year_context=year_context,
                calibration_root=root / "cache", free_bytes=200 * GIB,
                quota_policy=RunQuotaPolicy(minimum_free_bytes=0),
                headroom_bounds=_headroom(
                    assets_per_year=3, storage_per_year=1, years=2
                ),
            )
            run_path = _atomic_json_artifact(
                root / "published" / "run-context.json", run_context.to_dict()
            )
            resolver = ImmutableContextResolver(
                run_contexts=(run_context,), year_contexts=(), modules_by_slot={}
            )
            publish_year_context(
                resolver, run_context, year_context, root / "published"
            )
            actual_run_bytes = len(run_path.read_bytes())
            actual_year_bytes = len(
                (root / "published" / "year-2025.json").read_bytes()
            )

        self.assertEqual(
            estimate.calibration_basis["run_context_bytes"], actual_run_bytes
        )
        self.assertEqual(
            estimate.calibration_basis["year_context_bytes_by_year"][0],
            actual_year_bytes,
        )
        self.assertGreater(
            estimate.calibration_basis["year_context_bytes_by_year"][1],
            actual_year_bytes,
        )

    def test_cache_miss_calibrates_at_most_48_periods_in_isolation(self):
        run_context, year_context = _contexts(
            zones=3, boundaries=2, assets=4, storage=1, trace="full"
        )
        project = _project("full")
        official_state = year_context.to_dict()
        official_rng = random.Random(122)
        expected_rng = random.Random(122).random()
        seen = {}

        def calibration(request):
            seen.update(request)
            request["opening_state"]["operating_state"]["assets"].clear()
            request["ledger_path"].write_bytes(b"isolated-ledger")
            return {
                "periods": request["periods"],
                "persisted_bytes": 48_000,
                "temporary_bytes": 12_000,
                "runtime_seconds": 4.8,
            }

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            selected_output = root / "selected-output"
            selected_output.mkdir()
            project["selected_output_root"] = str(selected_output)
            estimate = estimate_run_resources(
                project=project,
                policy={"total_periods": 96, "years": 2, "periods_per_year": 48},
                run_context=run_context, year_context=year_context,
                calibration_root=root / "cache", free_bytes=200 * GIB,
                quota_policy=RunQuotaPolicy(minimum_free_bytes=0),
                calibration_runner=calibration,
                official_rng=official_rng,
            )
            cache_files = list((root / "cache").glob("*.json"))
            selected_output_entries = list(selected_output.iterdir())

        self.assertEqual(seen["periods"], 48)
        self.assertEqual(year_context.to_dict(), official_state)
        self.assertEqual(official_rng.random(), expected_rng)
        self.assertFalse(any(path.name == "market.sqlite" for path in selected_output_entries))
        self.assertFalse(any(path.name.lower().startswith("run") for path in selected_output_entries))
        self.assertEqual(len(cache_files), 1)
        self.assertEqual(estimate.calibration_basis["source"], "isolated_calibration")

    def test_production_calibration_boundary_consumes_clone_private_rng_and_denies_writers(self):
        _run_context, year_context = _contexts(
            zones=3, boundaries=2, assets=4, storage=1, trace="full"
        )
        official_rng = random.getstate()
        original = year_context.to_dict()
        calls = []

        def executor(**request):
            calls.append(request)
            request["opening_state"]["operating_state"]["assets"].clear()
            self.assertIsInstance(request["private_rng"], random.Random)
            return {
                "periods": request["periods"],
                "persisted_bytes": 100,
                "temporary_bytes": 50,
                "runtime_seconds": 0.01,
            }

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            selected_output = root / "official-output"
            selected_output.mkdir()
            sentinel = selected_output / "sentinel.bin"
            sentinel.write_bytes(b"official-byte-identical")
            project = _project("full")
            project["selected_output_root"] = str(selected_output)
            callback = selected_staged_zonal_calibration_runner(
                project=project, pack_root=Path("C:/frozen-pack"),
                network_pack_root=Path("C:/frozen-network"), registry=object(),
                isolation_executor=executor,
            )
            request = {
                "calibration_key": {"trace_profile": "full"},
                "periods": 48,
                "opening_state": original,
                "rng": random.Random(122),
                "isolated_root": root,
                "publish_run": False,
                "create_checkpoint": False,
                "advance_cem": False,
            }
            callback(request)
            self.assertEqual(request["opening_state"], original)
            for forbidden in ("publish_run", "create_checkpoint", "advance_cem"):
                denied = dict(request)
                denied[forbidden] = True
                with self.assertRaises(ValueError):
                    callback(denied)
            self.assertEqual(sentinel.read_bytes(), b"official-byte-identical")
            self.assertEqual(list(selected_output.iterdir()), [sentinel])
            self.assertFalse(any(root.rglob("checkpoints-v2")))
            self.assertFalse(any(root.rglob("partial-year-results")))

        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]["publish_run"])
        self.assertFalse(calls[0]["create_checkpoint"])
        self.assertFalse(calls[0]["advance_cem"])
        self.assertEqual(random.getstate(), official_rng)

    def test_cache_key_mismatch_recalibrates_and_disk_refusal_preserves_full_trace(self):
        run_context, year_context = _contexts(
            zones=3, boundaries=2, assets=4, storage=1, trace="full"
        )
        project = _project("full")
        calls = []

        def calibration(request):
            calls.append(request["calibration_key"])
            return {
                "periods": request["periods"],
                "persisted_bytes": 96_000,
                "temporary_bytes": 24_000,
                "runtime_seconds": 9.6,
            }

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wrong = ResourceCalibrationKey.from_inputs(
                project=_project("summary"),
                policy={"total_periods": 48, "years": 1, "periods_per_year": 48},
                run_context=run_context, trace_profile="summary",
            )
            _write_cache(root, wrong)
            estimate = estimate_run_resources(
                project=project,
                policy={"total_periods": 48, "years": 1, "periods_per_year": 48},
                run_context=run_context, year_context=year_context,
                calibration_root=root, free_bytes=1,
                quota_policy=RunQuotaPolicy(minimum_free_bytes=0),
                calibration_runner=calibration,
            )
        decision = evaluate_resource_gate(
            estimate, free_bytes=1,
            quota_policy=RunQuotaPolicy(minimum_free_bytes=0),
        )

        self.assertEqual(len(calls), 1)
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["errors"][0]["code"], "VALUE_PREFLIGHT_DISK_SPACE")
        self.assertEqual(
            decision["errors"][0]["corrective_actions"],
            ["Choose Summary", "Move output root", "Free space"],
        )
        self.assertEqual(project["runtime_options"]["runtime.market_trace_level"], "full")

    def test_reservation_race_allows_only_one_competing_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            barrier = Barrier(8)
            policy = RunQuotaPolicy(
                global_quota_bytes=100,
                per_run_quota_bytes=100,
                minimum_free_bytes=0,
            )

            def claim(index):
                barrier.wait()
                return reserve_run_space(root, f"run-{index}", 75, policy=policy)

            with patch("gridform_core.run_quota.shutil.disk_usage") as disk_usage:
                disk_usage.return_value.free = 10_000
                with ThreadPoolExecutor(max_workers=8) as executor:
                    reports = list(executor.map(claim, range(8)))

        self.assertEqual(sum(bool(row["accepted"]) for row in reports), 1)
        self.assertTrue(all(
            row["accepted"] or "global_quota_exceeded" in row["reason_codes"]
            for row in reports
        ))

    def test_frozen_snapshot_rejects_trace_context_and_output_root_mismatch(self):
        run_context, year_context = _contexts(
            zones=3, boundaries=2, assets=4, storage=1, trace="summary"
        )
        evidence = {
            "trace_profile": "summary",
            "run_context_sha256": canonical_context_sha256(run_context),
            "year_context_sha256": canonical_context_sha256(year_context),
            "calibration_key": {"schema_version": "value.resource-calibration-key/v1"},
            "calibration_basis": {"source": "cache"},
            "free_space_observation": {"free_bytes": 50 * GIB},
            "quota_decision": {"accepted": True},
            "selected_output_root": "C:/value/runs",
        }
        project = {"runtime_options": {"runtime.market_trace_level": "summary"}}
        with tempfile.TemporaryDirectory() as folder:
            snapshot_root = Path(folder)
            (snapshot_root / "snapshot.json").write_text(
                json.dumps({"snapshot_id": "base", "input_tree_sha256": "0" * 64}),
                encoding="utf-8",
            )
            freeze_resource_readiness(snapshot_root, evidence)
            verified = verify_frozen_resource_readiness(
                snapshot_root, project=project, selected_output_root=Path("C:/value/runs"),
                actual_run_context=run_context,
                actual_year_context=year_context,
                actual_calibration_key={"schema_version": "value.resource-calibration-key/v1"},
            )
            self.assertEqual(verified["trace_profile"], "summary")
            with self.assertRaises(ResourceSnapshotMismatch):
                verify_frozen_resource_readiness(
                    snapshot_root,
                    project={"runtime_options": {"runtime.market_trace_level": "full"}},
                    selected_output_root=Path("C:/value/runs"),
                    actual_run_context=run_context,
                    actual_year_context=year_context,
                    actual_calibration_key={"schema_version": "value.resource-calibration-key/v1"},
                )
            actual_payload = run_context.to_dict()
            mutations = (
                {"study_revision_sha256": "9" * 64},
                {"data_pack": {**dict(actual_payload["data_pack"]), "bindings": {"x": "y"}}},
                {"module_graph": {**dict(actual_payload["module_graph"]), "graph_sha256": "8" * 64}},
                {"solver_contract": {"method": "tampered-solver"}},
                {"period_hours": 1.0},
            )
            protected_output = snapshot_root / "must-not-be-created"
            for mutation in mutations:
                actual = RunStaticContext.from_dict({**actual_payload, **mutation})
                with self.assertRaises(ResourceSnapshotMismatch):
                    verify_frozen_resource_readiness(
                        snapshot_root, project=project,
                        selected_output_root=Path("C:/value/runs"),
                        actual_run_context=actual,
                        actual_year_context=year_context,
                        actual_calibration_key={"schema_version": "value.resource-calibration-key/v1"},
                    )
                self.assertFalse(protected_output.exists())
            with self.assertRaises(ResourceSnapshotMismatch):
                verify_frozen_resource_readiness(
                    snapshot_root, project=project,
                    selected_output_root=Path("C:/value/runs"),
                    actual_run_context=run_context,
                    actual_year_context=year_context,
                    actual_calibration_key={"schema_version": "tampered-key"},
                )
            with self.assertRaises(ResourceSnapshotMismatch):
                verify_frozen_resource_readiness(
                    snapshot_root, project=project,
                    selected_output_root=Path("C:/other"),
                    actual_run_context=run_context,
                    actual_year_context=year_context,
                    actual_calibration_key={"schema_version": "value.resource-calibration-key/v1"},
                )
            tampered = YearContext.from_dict({
                **year_context.to_dict(),
                "transition_lineage": {"opening": "tampered-actual-builder"},
            })
            with self.assertRaises(ResourceSnapshotMismatch):
                verify_frozen_resource_readiness(
                    snapshot_root, project=project,
                    selected_output_root=Path("C:/value/runs"),
                    actual_run_context=run_context,
                    actual_year_context=tampered,
                    actual_calibration_key={"schema_version": "value.resource-calibration-key/v1"},
                )


if __name__ == "__main__":
    unittest.main()
