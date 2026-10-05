"""M2-P0-8a third-round review minors, resolved in P0-8b (M6).

1. The capabilities builder degrades on a malformed runtime-fallback audit.
2. A primary shed in (0, TOLERANCE] gets the Q5 total-cap row (no hard failure).
3. An interconnector envelope below the ahead schedule is a forced part.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.zonal_results import zonal_workspace_capabilities
from gridform_validation.zonal_case_generator import bind_production_input, production_solution
from gridform_validation.zonal_oracle import compare_zonal_solutions, solve_zonal_oracle
from tests.network_toys import zonal_bid, zonal_declaration
from tests.test_prompt102_zonal_results_api import _write_fixture


def envelope_below_schedule_declaration(import_class: str) -> dict[str, object]:
    bids = (
        zonal_bid("imp-down", "imp", "gb", "down", 100.0, 0.0, baseline_mwh=100.0, resource_class=import_class),
        zonal_bid("gas-down", "gas", "gb", "down", 100.0, 0.0, baseline_mwh=100.0, resource_class="thermal"),
        zonal_bid("peak-up", "peak", "gb", "up", 100.0, 300.0, resource_class="thermal"),
    )
    declaration = zonal_declaration(
        {"gb": 200.0}, {"imp": 100.0, "gas": 100.0, "peak": 0.0},
        {"imp": "gb", "gas": "gb", "peak": "gb"}, bids,
        availability_mwh={"imp": 1000.0, "gas": 1000.0, "peak": 1000.0},
        classes={"imp": import_class, "gas": "thermal", "peak": "thermal"},
    )
    # The real-time interconnector envelope allows only 50 MWh of import.
    declaration["domain_payload"]["interconnector_envelope_mwh_by_asset"] = {
        "imp": {"maximum_mwh": 50.0, "minimum_mwh": 0.0}
    }
    return declaration


class CapabilitiesFallbackAuditGuardTests(unittest.TestCase):
    def test_corrupt_audit_file_degrades_to_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "market.sqlite"
            _write_fixture(database, "full")
            (database.parent / "runtime-fallback-audit-2025.json").write_text("{not json", encoding="utf-8")
            capabilities = zonal_workspace_capabilities(database)
            self.assertEqual(capabilities["runtime_fallback_audit"]["status"], "invalid")
            self.assertTrue(capabilities["runtime_fallback_audit"]["error"])
            (database.parent / "runtime-fallback-audit-2025.json").write_text(
                json.dumps({"schema_version": "other/v9"}), encoding="utf-8"
            )
            capabilities = zonal_workspace_capabilities(database)
        self.assertEqual(capabilities["runtime_fallback_audit"]["status"], "invalid")
        self.assertEqual(capabilities["network_pack_id"], "gb-zones-v1")


class TinyPrimaryShedTests(unittest.TestCase):
    def test_sub_tolerance_shortfall_uses_the_total_cap_row(self) -> None:
        for gap in (5e-9, 2e-8, 1e-3):
            with self.subTest(gap=gap):
                bids = (zonal_bid("gas-up", "gas", "gb", "up", 50.0, 60.0, baseline_mwh=100.0),)
                declaration = zonal_declaration(
                    {"gb": 150.0 + gap}, {"gas": 100.0}, {"gas": "gb"}, bids,
                    availability_mwh={"gas": 150.0},
                )
                model_input, module = bind_production_input(declaration)
                result = module.clear(model_input)
                lock = result.extensions["solver"]["phases"]["primary_shed_lock"]
                self.assertEqual(lock["mode"], "total_cap")
                self.assertGreater(lock["rhs_mwh"], 0.0)
                if gap < 1e-8:
                    self.assertEqual(result.blackout_mwh, 0.0)
                else:
                    self.assertAlmostEqual(result.blackout_mwh, gap, delta=1e-9)

    def test_no_primary_shed_still_fixes_every_shed_at_zero(self) -> None:
        bids = (zonal_bid("gas-up", "gas", "gb", "up", 60.0, 60.0, baseline_mwh=100.0),)
        declaration = zonal_declaration(
            {"gb": 150.0}, {"gas": 100.0}, {"gas": "gb"}, bids, availability_mwh={"gas": 200.0},
        )
        model_input, module = bind_production_input(declaration)
        result = module.clear(model_input)
        self.assertEqual(result.extensions["solver"]["phases"]["primary_shed_lock"]["mode"], "fixed_zero")
        self.assertEqual(result.blackout_mwh, 0.0)


class EnvelopeForcedPartTests(unittest.TestCase):
    def test_envelope_excess_is_forced_and_matches_the_oracle(self) -> None:
        for import_class in ("interconnector", "thermal"):
            with self.subTest(import_class=import_class):
                declaration = envelope_below_schedule_declaration(import_class)
                production = production_solution(declaration)
                oracle = solve_zonal_oracle(declaration)
                comparison = compare_zonal_solutions(declaration, production, oracle)
                self.assertTrue(comparison["passed"], comparison)
                self.assertEqual(comparison["classification"], "independent_match")
                for dispatch in (
                    production["final_dispatch_mwh_by_asset"],
                    oracle["final_dispatch_mwh_by_asset"],
                ):
                    self.assertAlmostEqual(dispatch["imp"], 50.0, places=6)
                    self.assertAlmostEqual(dispatch["gas"], 100.0, places=6)
                    self.assertAlmostEqual(dispatch["peak"], 50.0, places=6)
                self.assertAlmostEqual(oracle["primary_objective_gbp"], 15_000.0, places=4)


if __name__ == "__main__":
    unittest.main()
