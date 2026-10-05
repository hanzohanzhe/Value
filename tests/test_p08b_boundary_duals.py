"""P0-8 S10: boundary marginal values are primary-stage duals (P2-06, F3-05).

HEAD wrote a hard-coded 0.0 for every boundary, also at its limit; the value
is now -d(primary objective)/d(limit), signed in the forward direction, and
every pre-P0-8b row reads as not computed.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core.market_ledger import (
    BOUNDARY_SHADOW_SEMANTICS_V1,
    boundary_shadow_semantics,
    boundary_shadow_status,
    public_boundary_row,
)
from gridform_core.zonal_contracts import CutsetMember, ETYSBoundary, TransportCorridor
from gridform_core.zonal_results import query_zonal_annual_brief, query_zonal_results, zonal_workspace_capabilities
from gridform_validation.zonal_case_generator import bind_production_input
from tests.network_toys import zonal_bid, zonal_declaration, zonal_pack
from tests.test_p08b_network_counterfactual import generator, pack, psm_input, staged_zonal_run


def two_zone(limits: dict[str, float], *, reverse: bool = False):
    """Cheap upward energy (GBP 10) on one side, local GBP 76.5 next to the demand."""

    cheap_zone, demand_zone = ("south", "north") if reverse else ("north", "south")
    demand = {"north": 0.0, "south": 0.0, demand_zone: 10.0}
    corridor = TransportCorridor("north-south", "north", "south", "from_to_positive")
    cutsets = tuple(
        ETYSBoundary(boundary_id, boundary_id, (CutsetMember("north-south", 1),), limit, limit,
                     reverse_limit_method="assumed_symmetric_from_forward")
        for boundary_id, limit in limits.items()
    )
    return zonal_declaration(
        demand, {"cheap": 0.0, "local": 0.0}, {"cheap": cheap_zone, "local": demand_zone},
        (
            zonal_bid("cheap-up", "cheap", cheap_zone, "up", 10.0, 10.0),
            zonal_bid("local-up", "local", demand_zone, "up", 10.0, 76.5),
        ),
        pack=zonal_pack(demand, corridors=(corridor,), cutsets=cutsets),
    )


def solve(limits, *, reverse=False):
    model_input, module = bind_production_input(two_zone(limits, reverse=reverse))
    result = module.clear(model_input)
    return (
        result.extensions["boundary_marginal_value_gbp_per_mwh_by_id"],
        result.extensions["boundary_marginal_value_status_by_id"],
        float(result.extensions["primary_objective_gbp"]),
    )


class PrimaryDualTests(unittest.TestCase):
    def test_binding_boundary_value_is_the_finite_difference(self) -> None:
        values, statuses, objective = solve({"B": 4.0})
        self.assertAlmostEqual(values["B"], 66.5, places=6)
        self.assertEqual(statuses["B"], "computed")
        _values, _statuses, relaxed = solve({"B": 4.5})
        self.assertAlmostEqual((objective - relaxed) / 0.5, 66.5, places=6)

    def test_slack_boundary_is_zero(self) -> None:
        values, statuses, _objective = solve({"B": 100.0})
        self.assertEqual(values["B"], 0.0)
        self.assertEqual(statuses["B"], "computed")

    def test_reverse_binding_is_negative(self) -> None:
        values, _statuses, _objective = solve({"B": 4.0}, reverse=True)
        self.assertAlmostEqual(values["B"], -66.5, places=6)

    def test_shared_member_value_lies_between_one_sided_derivatives(self) -> None:
        values, statuses, objective = solve({"B1": 4.0, "B2": 4.0})
        self.assertEqual(statuses["B1"], "shared_member")
        self.assertEqual(statuses["B2"], "shared_member")
        # Raising one limit alone helps nothing (the other binds): right
        # derivative 0; lowering it costs 66.5 per MWh: left derivative 66.5.
        _v, _s, up = solve({"B1": 4.5, "B2": 4.0})
        _v, _s, down = solve({"B1": 3.5, "B2": 4.0})
        right = (objective - up) / 0.5
        left = (down - objective) / 0.5
        for boundary_id in ("B1", "B2"):
            self.assertGreaterEqual(values[boundary_id], min(right, left) - 1e-6)
            self.assertLessEqual(values[boundary_id], max(right, left) + 1e-6)
        self.assertAlmostEqual(values["B1"] + values["B2"], 66.5, places=6)


class LedgerReadModelTests(unittest.TestCase):
    def test_staged_ledger_stores_the_dual_and_the_annual_rent(self) -> None:
        resources = (generator("wind", "onshore", "vre", 10.0, 0.0), generator("ccgt", "CCGT", "thermal", 10.0, 100.0))
        model_input = psm_input(resources, (10.0,))
        network = pack(("a", "b"), {"wind": "a", "ccgt": "b"}, model_input.chronology.period_ids,
                       {"a": (0.0,), "b": (10.0,)}, 4.0)
        with tempfile.TemporaryDirectory() as folder:
            result, _accounting, _resources, _curtailment = staged_zonal_run(model_input, network, Path(folder))
            database = Path(folder) / "market" / "market.sqlite"
            page = query_zonal_results(database, {"view": "boundary"})
            brief = query_zonal_annual_brief(database)
            capabilities = zonal_workspace_capabilities(database)
        row = page["items"][0]
        # Wind's dec is worth GBP 0 and the southern CCGT costs GBP 100.
        self.assertAlmostEqual(row["boundary_shadow_value_gbp_per_mwh"], 100.0, places=6)
        self.assertEqual(row["shadow_value_status"], "computed")
        rent = result.extensions["zonal_accounting_gbp"]["boundary_congestion_rent_diagnostic_gbp"]
        self.assertAlmostEqual(rent, 400.0, places=4)
        self.assertNotIn("boundary_shadow_value_gbp", result.extensions["zonal_accounting_gbp"])
        self.assertAlmostEqual(brief["years"][0]["boundary_congestion_rent_diagnostic_gbp"], 400.0, places=4)
        self.assertTrue(capabilities["boundary_shadow_value_available"])
        self.assertNotIn("p08.boundary-shadow-not-computed",
                         {item["defect_id"] for item in capabilities["known_defects"]})

    def test_legacy_rows_read_as_not_computed(self) -> None:
        legacy = {"boundary_id": "B", "boundary_shadow_value_gbp_per_mwh": 0.0,
                  "shadow_value_semantics": BOUNDARY_SHADOW_SEMANTICS_V1}
        shown = public_boundary_row(legacy)
        self.assertIsNone(shown["boundary_shadow_value_gbp_per_mwh"])
        self.assertEqual(shown["shadow_value_status"], "not_computed")
        self.assertEqual(boundary_shadow_status(boundary_shadow_semantics("degenerate_dual")), "degenerate_dual")
        self.assertIn("not_zonal_price_or_cash_cost", boundary_shadow_semantics("computed"))

    def test_legacy_ledger_views_show_not_computed(self) -> None:
        from tests.test_prompt102_zonal_results_api import _write_fixture

        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            _write_fixture(database, "full")
            with closing(sqlite3.connect(database)) as connection:
                stored = connection.execute(
                    "SELECT COUNT(*) FROM boundary_period_summary").fetchone()[0]
            page = query_zonal_results(database, {"view": "boundary"})
            brief = query_zonal_annual_brief(database)
            capabilities = zonal_workspace_capabilities(database)
        self.assertGreater(stored, 0)
        self.assertTrue(all(item["boundary_shadow_value_gbp_per_mwh"] is None for item in page["items"]))
        self.assertTrue(all(item["shadow_value_status"] == "not_computed" for item in page["items"]))
        self.assertIsNone(brief["years"][0]["boundary_congestion_rent_diagnostic_gbp"])
        self.assertFalse(capabilities["boundary_shadow_value_available"])
        self.assertIn("p08.boundary-shadow-not-computed",
                      {item["defect_id"] for item in capabilities["known_defects"]})


if __name__ == "__main__":
    unittest.main()
