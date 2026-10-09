"""P0-8 S12: capacity placed in fallback zones is audited per year and technology."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh.staged_psm import (
    SPATIALLY_INDICATIVE_FALLBACK_FRACTION,
    StagedBidAtCostPSM,
    runtime_fallback_audit,
)
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
    StorageDispatchResource,
)
from gridform_core.zonal_contracts import (
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZonalAssetMapping,
    ZonalDemand,
    ZonalNetworkPack,
    pack_fallback_assets,
)
from gridform_core.zonal_results import query_runtime_fallback_audit


def fallback_pack() -> ZonalNetworkPack:
    zones = (
        NetworkZone("north", "North", "DSO", "Scotland"),
        NetworkZone("south", "South", "DSO", "England"),
        NetworkZone("FALLBACK", "Unlocated", "none", "England", is_unconstrained_fallback=True),
    )
    pack = ZonalNetworkPack(
        "fallback-toy", "", zones,
        (
            TransportCorridor("north-south", "north", "south", "from_to_positive"),
            TransportCorridor("fallback-south", "FALLBACK", "south", "from_to_positive"),
        ),
        (),
        (
            ZonalAssetMapping("wind-n", "north", "generator", "wind", 1.0, "source_coordinate"),
            ZonalAssetMapping("ccgt-u", "FALLBACK", "generator", "ccgt", 1.0, "unlocated_england_fallback"),
            ZonalAssetMapping("ccgt-s", "south", "generator", "ccgt", 1.0, "source_coordinate"),
            ZonalAssetMapping("battery-u", "FALLBACK", "storage", "battery", 1.0, "unlocated_england_fallback"),
        ),
        ZonalDemand(("p0",), {"north": (1.0,), "south": (1.0,), "FALLBACK": (0.0,)}, (2.0,)),
        (), (), SpatialAudit((), {}, {}, 1e-9), "lossless_v1",
    )
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


def model_input() -> PSMInput:
    chronology = ChronologicalPSMData(
        ("p0",), (2.0,),
        (
            DispatchResource("wind-n", "wind", "vre", 100.0, 0.0, (1.0,)),
            DispatchResource("ccgt-u", "ccgt", "thermal", 300.0, 80.0, (1.0,)),
            DispatchResource("ccgt-s", "ccgt", "thermal", 500.0, 80.0, (1.0,)),
            # A new entrant with no allocation anywhere: run-time fallback.
            DispatchResource("nuclear-new", "nuclear", "thermal", 50.0, 10.0, (1.0,)),
        ),
        (StorageDispatchResource("battery-u", "battery", 20.0, 20.0, 40.0, 0.9, 0.9, 0.0),),
        17_000.0,
    )
    return PSMInput("fallback-run", 2030, "pack", OperatingState(2030, (), ()), 0.5, {}, chronology=chronology)


def spatialise(psm: StagedBidAtCostPSM) -> dict[str, object]:
    psm._network_pack = fallback_pack()
    psm._spatialized_input(model_input())
    return psm._runtime_fallback_audits[2030]


class RuntimeFallbackAuditTests(unittest.TestCase):
    def test_pure_audit_totals_and_threshold(self) -> None:
        audit = runtime_fallback_audit(
            year=2030, fallback_zone_ids=["F"],
            allocations=[
                {"asset_id": "a", "technology": "ccgt", "capacity_mw": 900.0, "shares": {"S": 1.0}, "allocation_source": "pack_mapping"},
                {"asset_id": "b", "technology": "ccgt", "capacity_mw": 100.0, "shares": {"F": 1.0}, "allocation_source": "pack_mapping"},
                {"asset_id": "c", "technology": "nuclear", "capacity_mw": 50.0, "shares": {"F": 0.5, "S": 0.5}, "allocation_source": "frozen_zone_shares"},
            ],
        )
        rows = {row["technology"]: row for row in audit["by_technology"]}
        self.assertAlmostEqual(rows["ccgt"]["fallback_fraction"], 0.1)
        self.assertFalse(rows["ccgt"]["spatially_indicative"])  # not above 10 %
        self.assertAlmostEqual(rows["nuclear"]["fallback_mw"], 25.0)
        self.assertTrue(rows["nuclear"]["spatially_indicative"])
        self.assertEqual([row["asset_id"] for row in audit["assets"]], ["b", "c"])
        self.assertEqual(SPATIALLY_INDICATIVE_FALLBACK_FRACTION, 0.10)

    def test_staged_psm_lists_fallback_assets_and_matches_preflight(self) -> None:
        audit = spatialise(StagedBidAtCostPSM())
        by_asset = {row["asset_id"]: row for row in audit["assets"]}
        self.assertEqual(set(by_asset), {"ccgt-u", "battery-u", "nuclear-new"})
        self.assertEqual(by_asset["nuclear-new"]["allocation_source"], "runtime_fallback")
        rows = {row["technology"]: row for row in audit["by_technology"]}
        self.assertAlmostEqual(rows["ccgt"]["fallback_fraction"], 300.0 / 800.0)
        self.assertTrue(rows["ccgt"]["spatially_indicative"])
        self.assertEqual(rows["nuclear"]["runtime_unallocated_mw"], 50.0)
        self.assertEqual(rows["wind"]["fallback_mw"], 0.0)
        preflight = pack_fallback_assets(fallback_pack())
        self.assertEqual(preflight["fallback_zone_ids"], ["FALLBACK"])
        self.assertEqual(
            sorted(row["asset_id"] for row in preflight["assets"]),
            sorted(asset for asset, row in by_asset.items() if row["allocation_source"] == "pack_mapping"),
        )

    def test_the_same_input_reproduces_the_same_audit(self) -> None:
        self.assertEqual(spatialise(StagedBidAtCostPSM()), spatialise(StagedBidAtCostPSM()))

    def test_a_subannual_restore_rewrites_the_same_audit_file(self) -> None:
        """Restore through the staged PSM's real subannual checkpoint protocol.

        A run stopped after January (no audit file is written before the
        year ends) and restored into a fresh PSM instance writes the same
        yearly audit file as an uninterrupted run.
        """

        from gridform_core.v2.orchestrator import CancellationRequested
        from tests.test_zonal_subannual_resume import _configured_psm

        def audit_file(output_dir: Path) -> dict[str, object]:
            path = output_dir / "market" / f"runtime-fallback-audit-{year}.json"
            return json.loads(path.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "same-run"
            continuous, _balancing, continuous_input = _configured_psm(output_dir)
            year = int(continuous_input.year)
            continuous.run(continuous_input)
            expected = audit_file(output_dir)
            shutil.rmtree(output_dir)

            stopped, _balancing, stopped_input = _configured_psm(output_dir)
            captured: list[dict[str, object]] = []
            stopped.configure_subannual_checkpoint_sink(
                lambda _boundary, checkpoint, _ledger: captured.append(copy.deepcopy(checkpoint))
            )

            def stop_after_january(stop_year: int, period: int) -> None:
                if (stop_year, period) == (year, 1):
                    raise CancellationRequested("stop after January")

            stopped.configure_period_boundary_cancellation(stop_after_january)
            with self.assertRaises(CancellationRequested):
                stopped.run(stopped_input)
            self.assertEqual(len(captured), 1)
            audit_path = output_dir / "market" / f"runtime-fallback-audit-{year}.json"
            self.assertFalse(audit_path.exists())

            resumed, _balancing, resumed_input = _configured_psm(output_dir)
            # As in the orchestrator, the resuming process prepares the year
            # context again (that is where the audit is computed), then
            # restores the runtime checkpoint and runs the remaining periods.
            resumed.restore_runtime_checkpoint(captured[0])
            resumed.run(resumed_input)
            restored = audit_file(output_dir)

        self.assertEqual(restored, expected)
        self.assertEqual(restored["year"], year)
        self.assertEqual(len(restored["by_technology"]), 3)

    def test_read_model_flags_spatially_indicative_technologies(self) -> None:
        audit = spatialise(StagedBidAtCostPSM())
        with tempfile.TemporaryDirectory() as folder:
            market = Path(folder)
            self.assertIsNone(query_runtime_fallback_audit(market))
            (market / "runtime-fallback-audit-2030.json").write_text(json.dumps(audit), encoding="utf-8")
            summary = query_runtime_fallback_audit(market)
        self.assertTrue(summary["spatially_indicative"])
        technologies = {row["technology"] for row in summary["spatially_indicative_technologies"]}
        self.assertEqual(technologies, {"ccgt", "battery", "nuclear"})


if __name__ == "__main__":
    unittest.main()
