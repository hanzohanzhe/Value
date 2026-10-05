from __future__ import annotations

import ast
import sys
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
    FLOW_ROLE_BY_TYPE,
    FLOW_ROLES,
    canonical_technology,
    market_price_basis,
    market_replay_capabilities,
    period_price_basis,
    query_auction_view,
    query_dispatch_timeline,
    query_vre_curtailment_summary,
    query_vre_curtailment_timeline,
)


ROOT = Path(__file__).resolve().parents[1]


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

    def test_period_price_basis_mapping(self):
        # P0-9 S3 / Q6: the read model states what the period price is.
        cases = (
            ({"period_price_semantics": "demand_normalised_total_period_cost; not a stage clearing-price proof"},
             "value.market-ledger/v7", ("average_period_cost", "semantics")),
            ({"pricing_rule": "lp_balance_dual",
              "period_price_semantics": "objective derivative with respect to the demand-balance right-hand side"},
             "value.market-ledger/v7", ("balance_shadow_price", "semantics")),
            ({"period_price_basis": "ahead_generator_settlement_only_not_all_stage_storage_arbitrage"},
             "value.market-ledger/v7", ("ahead_settlement_price", "semantics")),
            ({"psm_module_id": "value-staged-bid-at-cost-psm"},
             "value.market-ledger/v8", ("national_ahead_clearing_price", "inferred_from_writer")),
            ({}, "value.market-ledger/v7", ("not_declared", "not_declared")),
        )
        for semantic, version, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(period_price_basis(semantic, version), expected)
        self.assertEqual(period_price_basis({"price_basis": "balance_shadow_price"}, "value.market-ledger/v8"),
                         ("balance_shadow_price", "declared"))
        self.assertEqual(period_price_basis({"price_basis": "made_up"}, None), ("not_declared", "not_declared"))

    def test_price_basis_travels_with_capabilities_and_timeline(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self._ledger(Path(folder))
            capabilities = market_replay_capabilities(database)
            timeline = query_dispatch_timeline(database, year=2025, resolution="daily")
            basis = market_price_basis(database)
        # The test ledger declares no price semantics: the UI must say so.
        self.assertEqual(capabilities["price_basis"], "not_declared")
        self.assertEqual(timeline["price_basis"], "not_declared")
        self.assertEqual(basis, {"price_basis": "not_declared", "price_basis_source": "not_declared"})
        self.assertEqual(timeline["items"][0]["price_gbp_per_mwh"], 40.0)
        self.assertNotIn("clearing_price_gbp_per_mwh", timeline["items"][0])

    def test_v7_flows_carry_their_balance_role(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self._ledger(Path(folder))
            timeline = query_dispatch_timeline(database, year=2025, resolution="half_hour", limit=1)
        self.assertEqual(timeline["schema_version"], "value.dispatch-timeline/v2")
        self.assertEqual({flow["role"] for flow in timeline["items"][0]["flows"]}, {"supply"})

    def test_v8_summary_flows_are_canonical_supply(self):
        sys.path.insert(0, str(ROOT / "tests"))
        try:
            import ui_contract_fixtures as fixtures
        finally:
            sys.path.remove(str(ROOT / "tests"))
        with tempfile.TemporaryDirectory() as folder:
            database = fixtures.build_toy_v8(Path(folder))
            daily = query_dispatch_timeline(database, year=2025, resolution="daily", period_from=0, period_to=47)
        bucket = daily["items"][0]
        stacked: dict[str, float] = {}
        for flow in bucket["flows"]:
            if flow["role"] == "supply":
                stacked[flow["technology"]] = stacked.get(flow["technology"], 0.0) + flow["energy_mwh"]
        self.assertEqual(stacked, {"ccgt": 32.0, "onshore_wind": 8.0})
        self.assertEqual(sum(stacked.values()), bucket["accepted_supply_mwh"])
        self.assertEqual({flow["raw_technology"] for flow in bucket["flows"]}, {"CCGT", "onshore"})
        self.assertAlmostEqual(bucket["price_gbp_per_mwh"], 55.0)

    def test_v8_earlier_stages_are_context_only(self):
        from gridform_core.market_replay import v8_summary_flow_role

        self.assertEqual(v8_summary_flow_role("final_dispatch", 4.0), "supply")
        self.assertEqual(v8_summary_flow_role("ahead", 4.0), "context")
        self.assertEqual(v8_summary_flow_role("final_dispatch", -1.0), "context")

    def test_every_written_flow_type_has_a_role(self):
        # The three physical-dispatch writers; every flow_type literal they can
        # record must be classified (an unclassified one would silently be
        # context and vanish from the stacked chart).
        writers = (
            ROOT / "gridform_core" / "builtin" / "scheme_c_1000twh" / "scheme_c_native_psm.py",
            ROOT / "gridform_core" / "perfect_foresight_psm.py",
            ROOT / "gridform_core" / "builtin" / "scheme_c_1000twh" / "staged_psm.py",
        )
        found: set[str] = set()

        def literals(node: ast.AST) -> set[str]:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return {node.value}
            if isinstance(node, ast.IfExp):
                return literals(node.body) | literals(node.orelse)
            return set()

        for path in writers:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "PhysicalDispatchRow" and len(node.args) >= 5:
                    found |= literals(node.args[4])
                elif isinstance(node, ast.Assign) and any(getattr(target, "id", None) == "flow_type" for target in node.targets):
                    found |= literals(node.value)
                elif isinstance(node, ast.Tuple) and len(node.elts) == 6 and isinstance(node.elts[0], ast.Constant) \
                        and str(node.elts[0].value).startswith("__"):
                    found |= literals(node.elts[2])  # scheme_c_native_psm context flows
        self.assertGreaterEqual(found, {"generation", "import", "storage_discharge", "storage_charge", "blackout"})
        self.assertEqual(sorted(found - set(FLOW_ROLE_BY_TYPE)), [])
        self.assertLessEqual(set(FLOW_ROLE_BY_TYPE.values()), set(FLOW_ROLES))

    def test_event_bases_are_separated(self):
        # P0-9 S8 (G1-08): three periods; curtailment in period 0, excess in
        # period 1, nothing in period 2.  Unused VRE (available - accepted) is
        # positive only in period 0.  The legacy event fields count the
        # excess+curtailment basis (2 periods) and keep their values.
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = create_market_ledger(database, "summary", semantic_metadata={
                "period_hours": 0.5, "excess_scope": "inflexible_mixed", "excess_relationship": "separate_prebalancing",
            })
            ledger.record_period(_period(0, curtailment=1.0))
            ledger.record_period(_period(1, excess=3.0))
            ledger.record_period(_period(2))
            ledger.close()
            year = query_vre_curtailment_summary(database)["years"][0]
        self.assertEqual(year["affected_periods"], 2)
        self.assertEqual(year["event_basis"], "excess_plus_balancing_curtailment")
        self.assertEqual(year["excess_curtailment_events"]["affected_periods"], 2)
        self.assertEqual(year["excess_curtailment_events"]["peak_event_period"], 1)
        self.assertEqual(year["unused_vre_events"]["affected_periods"], 1)
        self.assertEqual(year["unused_vre_events"]["peak_event_period"], 0)
        self.assertEqual(year["unused_vre_events"]["peak_event_mwh"], 1.0)
        self.assertEqual(year["peak_event_mwh"], 3.0, "legacy field unchanged")


if __name__ == "__main__":
    unittest.main()
