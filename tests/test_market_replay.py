from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from gridform_core.clearing_inputs import ClearingInputRow, ClearingOutcomeRow
from gridform_core.market_ledger import (
    PeriodLedgerRow,
    PhysicalDispatchRow,
    SQLiteMarketLedger,
    create_market_ledger,
)
from gridform_core.market_replay import (
    canonical_technology,
    market_replay_capabilities,
    query_auction_view,
    query_dispatch_timeline,
    query_vre_curtailment_summary,
    query_vre_curtailment_timeline,
)


def _period(index: int, *, curtailment: float = 0.0, excess: float = 0.0) -> PeriodLedgerRow:
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
        vre_available_mwh=8.0,
        vre_accepted_mwh=8.0 - curtailment,
        curtailed_mwh=curtailment,
        import_mwh=0.0,
        clearing_price_gbp_per_mwh=40.0,
        physical_resource_cost_gbp=400.0,
        market_payment_gbp=200.0,
        policy_transfer_gbp=0.0,
        blackout_mwh=0.0,
        excess_mwh=excess,
        energy_balance_residual_mwh=0.0,
    )


class MarketReplayTests(unittest.TestCase):
    def _ledger(self, root: Path) -> Path:
        database = root / "market.sqlite"
        ledger = create_market_ledger(
            database,
            "full",
            semantic_metadata={
                "period_hours": 0.5,
                "timezone": "Europe/London",
                "calendar": "fixed_365_day_local_periods",
                "excess_scope": "inflexible_mixed",
                "excess_relationship": "separate_prebalancing",
            },
        )
        for period in range(4):
            ledger.record_period(_period(
                period,
                curtailment=1.0 if period in {1, 2} else 0.0,
                excess=2.0 if period == 2 else 0.0,
            ))
            ledger.record_physical_dispatch((
                PhysicalDispatchRow(2025, period, "solar-a", "solar", "generation", 4.0, 4.0, "physical_asset", "final_dispatch"),
                PhysicalDispatchRow(2025, period, "gas-a", "ccgt", "generation", 6.0, 6.0, "physical_asset", "final_dispatch"),
            ))
        declared = ClearingInputRow.create(
            year=2025,
            period=0,
            stage="ahead",
            information_scope="forecast only",
            payload={
                "period_hours": 0.5,
                "target_power_mw": 10.0,
                "offers": [
                    {"offer_id": "high", "asset_id": "gas-a", "asset_type": "CCGTGenerator", "resource_kind": "thermal", "offer_price_gbp_per_mwh": 50.0, "maximum_power_mw": 8.0},
                    {"offer_id": "low", "asset_id": "solar-a", "asset_type": "SolarGenerator", "resource_kind": "vre", "offer_price_gbp_per_mwh": 0.0, "maximum_power_mw": 8.0},
                    {"offer_id": "battery-1", "asset_id": "battery-a", "asset_type": "Battery", "resource_kind": "storage_discharge", "offer_price_gbp_per_mwh": 20.0, "maximum_power_mw": 2.0},
                    {"offer_id": "battery-2", "asset_id": "battery-a", "asset_type": "Battery", "resource_kind": "storage_discharge", "offer_price_gbp_per_mwh": 30.0, "maximum_power_mw": 2.0},
                ],
            },
        )
        ledger.record_clearing_input(declared)
        ledger.record_clearing_outcome(ClearingOutcomeRow.create(
            declared.input_sha256,
            {
                "accepted": [
                    {"asset_id": "solar-a", "accepted_power_mw": 8.0, "offer_price_gbp_per_mwh": 0.0},
                    {"asset_id": "battery-a", "accepted_power_mw": 1.0, "offer_price_gbp_per_mwh": 20.0},
                    {"asset_id": "gas-a", "accepted_power_mw": 1.0, "offer_price_gbp_per_mwh": 50.0},
                ]
            },
        ))
        curtailment = ClearingInputRow.create(
            year=2025, period=0, stage="curtailment",
            information_scope="realised demand and post-ahead schedule",
            payload={
                "period_hours": 0.5,
                "surplus_target_power_mw": 2.0,
                "actions": [{
                    "offer_id": "charge", "asset_id": "battery-a",
                    "asset_type": "Battery", "resource_kind": "storage_charge",
                    "offer_price_gbp_per_mwh": 1.0, "maximum_power_mw": 2.0,
                }],
            },
        )
        ledger.record_clearing_input(curtailment)
        ledger.record_clearing_outcome(ClearingOutcomeRow.create(
            curtailment.input_sha256,
            {"storage_charge_power_mw": 1.0, "remaining_excess_power_mw": 1.0},
        ))
        ledger.close()
        return database

    def test_capabilities_and_price_ordered_auction_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self._ledger(Path(folder))
            capabilities = market_replay_capabilities(database)
            auction = query_auction_view(database, year=2025, period=0, stage="ahead")
        self.assertTrue(capabilities["auction_replay"])
        self.assertTrue(capabilities["physical_dispatch"])
        self.assertEqual(
            capabilities["ledger_schema_version"], "value.market-ledger/v7"
        )
        self.assertEqual([row["offer_id"] for row in auction["offers"]], [
            "low", "battery-1", "battery-2", "high"
        ])
        self.assertEqual(auction["offers"][0]["input_order"], 1)
        self.assertEqual(auction["offers"][1]["acceptance_granularity"], "asset_aggregate")
        self.assertEqual(auction["offer_acceptance_coverage"], "asset_aggregate_for_multi_tranche_resources")
        self.assertEqual(auction["marginal_offer_price_gbp_per_mwh"], 50.0)

    def test_stage_summary_does_not_invent_per_action_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self._ledger(Path(folder))
            auction = query_auction_view(
                database, year=2025, period=0, stage="curtailment"
            )
        self.assertEqual(auction["offer_acceptance_coverage"], "stage_summary_only")
        self.assertIsNone(auction["offers"][0]["accepted_mwh"])
        self.assertIsNone(auction["offers"][0]["asset_accepted_mwh"])
        self.assertIsNone(auction["marginal_offer_price_gbp_per_mwh"])

    def test_timeline_is_bounded_and_dispatch_is_not_double_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self._ledger(Path(folder))
            half_hours = query_dispatch_timeline(
                database,
                year=2025,
                resolution="half_hour",
                period_from=1,
                period_to=3,
                limit=2,
            )
            daily = query_dispatch_timeline(database, year=2025, resolution="daily")
            with self.assertRaisesRegex(ValueError, "between 1 and 1000"):
                query_dispatch_timeline(
                    database, year=2025, resolution="half_hour", limit=1001
                )
        self.assertEqual(half_hours["total"], 3)
        self.assertEqual(len(half_hours["items"]), 2)
        self.assertEqual(half_hours["items"][0]["period_start"], 1)
        self.assertEqual(sum(flow["energy_mwh"] for flow in daily["items"][0]["flows"]), 40.0)
        self.assertEqual(daily["items"][0]["period_count"], 4)

    def test_v8_timeline_never_falls_back_to_full_physical_detail(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_period(_period(0))
            ledger.record_physical_dispatch((
                PhysicalDispatchRow(
                    2025, 0, "gas-a", "ccgt", "generation", 10.0, 10.0,
                    "physical_asset", "final_dispatch",
                ),
            ))
            ledger.close()

            timeline = query_dispatch_timeline(
                database, year=2025, resolution="half_hour", limit=1,
            )
            capabilities = market_replay_capabilities(database)
        self.assertEqual(timeline["items"][0]["flows"], [])
        self.assertEqual(timeline["dispatch_source"], "dispatch_summary")
        self.assertFalse(capabilities["dispatch_summary_available"])

    def test_sparse_legacy_timeline_pages_actual_distinct_buckets(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = create_market_ledger(database, "summary")
            ledger.record_period(_period(0))
            ledger.record_period(_period(100))
            ledger.close()

            page = query_dispatch_timeline(
                database,
                year=2025,
                resolution="daily",
                period_from=0,
                period_to=100,
                limit=1,
                offset=1,
            )
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["period_start"], 100)

    def test_vre_identity_and_distinct_excess_semantics(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self._ledger(Path(folder))
            summary = query_vre_curtailment_summary(database)["years"][0]
            timeline = query_vre_curtailment_timeline(
                database, year=2025, resolution="half_hour"
            )
        self.assertAlmostEqual(summary["available_vre_mwh"], 32.0)
        self.assertAlmostEqual(summary["accepted_vre_mwh"], 30.0)
        self.assertAlmostEqual(summary["neutral_unused_vre_mwh"], 2.0)
        self.assertAlmostEqual(summary["pre_balancing_excess_mwh"], 2.0)
        self.assertAlmostEqual(summary["balancing_curtailment_mwh"], 2.0)
        self.assertAlmostEqual(summary["vre_identity_residual_mwh"], 0.0)
        self.assertEqual(summary["affected_periods"], 2)
        self.assertEqual(summary["longest_event_periods"], 2)
        self.assertEqual(timeline["items"][1]["neutral_unused_vre_mwh"], 1.0)

    def test_backend_technology_mapping_keeps_unknowns_visible(self):
        self.assertEqual(canonical_technology("North Sea Offshore Wind"), "offshore_wind")
        self.assertEqual(canonical_technology("connector-1"), "boundary_import")
        self.assertEqual(canonical_technology("novel-resource"), "unmapped")

    def test_historical_unknown_semantics_do_not_publish_false_split_zeros(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self._ledger(Path(folder))
            metadata = database.parent / "metadata.json"
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            payload["semantic_metadata"] = {}
            metadata.write_text(json.dumps(payload), encoding="utf-8")
            summary = query_vre_curtailment_summary(database)["years"][0]
        self.assertIsNone(summary["pre_balancing_excess_mwh"])
        self.assertIsNone(summary["balancing_curtailment_mwh"])
        self.assertEqual(summary["coverage_status"], "partial_semantic_attribution")


if __name__ == "__main__":
    unittest.main()
