from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

import gridform_core.market_ledger as market_ledger
from gridform_core.market_ledger import (
    BoundaryPeriodLedgerRow,
    RedispatchSettlementRow,
    ReliabilityEventRow,
    SolverDeclarationLinkRow,
    SQLiteMarketLedger,
    ZonePeriodLedgerRow,
    ZonalAccountingLedgerRow,
    ZonalResourceDispatchRow,
    market_ledger_capabilities,
    query_market_table,
    validate_market_ledger_file,
)
from gridform_core.errors import InvariantError
from gridform_core.zonal_results import (
    build_reliability_events,
    build_zonal_period_accounting,
    export_zonal_results,
    query_zonal_results,
)
from gridform_core.cost_ledger import build_cem_cost_ledger
from gridform_core.v2.contracts import MarketYearResult


def _accounting(*, zonal_cost: float = 145.0):
    return build_zonal_period_accounting(
        year=2025,
        period=4,
        period_id="2025:4",
        realised_input_sha256="a" * 64,
        perfect_forecast_resource_cost_gbp=100.0,
        realised_copperplate_resource_cost_gbp=120.0,
        zonal_resource_cost_gbp=zonal_cost,
        ahead_settlement_mwh_by_asset={"wind": 8.0, "gas": 2.0},
        national_clearing_price_gbp_per_mwh=50.0,
        redispatch_cashflow_gbp_by_agent={"wind-owner": -5.0, "gas-owner": 35.0},
        policy_transfer_gbp=7.0,
        boundary_shadow_value_gbp_per_mwh={"B1": 12.0},
        blackout_mwh=0.0,
    )


class Prompt100ZonalLedgerTests(unittest.TestCase):
    def test_demand_alignment_round_trips_as_period_evidence(self):
        row_type = getattr(market_ledger, "ZonalDemandAlignmentLedgerRow")
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(
                database,
                trace_level="summary",
                semantic_metadata={
                    "run_id": "run-zonal",
                    "run_parent_id": "",
                    "data_pack_id": "research-v1",
                    "network_pack_id": "network-v1",
                    "module_ids": ["ahead-v1", "zonal-v1"],
                },
            )
            ledger.record_zonal_demand_alignment((row_type(
                2025,
                0,
                "p0",
                "scenario_scaled_zonal_shares",
                120.0,
                108.0,
                100.0,
                1.2,
                120.0,
                0.0,
            ),))
            metadata = ledger.close()
            queried = query_market_table(
                database, "zonal_demand_alignment", year=2025, period=0
            )

        self.assertEqual(metadata["rows"]["zonal_demand_alignment"], 1)
        self.assertEqual(queried["total"], 1)
        self.assertEqual(queried["items"][0], {
            "year": 2025,
            "period": 0,
            "period_id": "p0",
            "demand_mode": "scenario_scaled_zonal_shares",
            "research_real_demand_mwh": 120.0,
            "research_forecast_demand_mwh": 108.0,
            "network_national_demand_mwh": 100.0,
            "scale_factor": 1.2,
            "aligned_zonal_total_mwh": 120.0,
            "conservation_residual_mwh": 0.0,
        })

    def test_six_accounts_and_three_counterfactuals_reconcile(self):
        result = _accounting()
        self.assertEqual(result.system_resource_cost_gbp, 145.0)
        self.assertEqual(result.transmission_constraint_resource_cost_gbp, 25.0)
        self.assertEqual(result.national_settlement_gbp, 500.0)
        self.assertEqual(result.redispatch_settlement_gbp, 30.0)
        self.assertEqual(result.policy_transfer_gbp, 7.0)
        self.assertEqual(result.boundary_shadow_value_gbp_per_mwh, {"B1": 12.0})
        self.assertEqual(result.forecast_error_cost_gbp, 20.0)
        self.assertEqual(result.total_deviation_cost_gbp, 45.0)
        self.assertEqual(result.accounting_status, "reconciled")
        self.assertFalse(hasattr(result, "economic_ahead_unused_vre_mwh"))
        self.assertFalse(hasattr(result, "total_curtailment_vre_mwh"))
        self.assertEqual(result.counterfactual_realised_input_sha256, "a" * 64)
        self.assertEqual(
            result.boundary_shadow_value_semantics,
            market_ledger.BOUNDARY_SHADOW_SEMANTICS_V2,  # P0-8 S10 primary-stage dual
        )

    def test_bad_counterfactual_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_zonal_period_accounting(
                year=2025,
                period=0,
                period_id="2025:0",
                realised_input_sha256="not-a-sha",
                perfect_forecast_resource_cost_gbp=1.0,
                realised_copperplate_resource_cost_gbp=2.0,
                zonal_resource_cost_gbp=3.0,
                ahead_settlement_mwh_by_asset={},
                national_clearing_price_gbp_per_mwh=0.0,
                redispatch_cashflow_gbp_by_agent={},
                policy_transfer_gbp=0.0,
                boundary_shadow_value_gbp_per_mwh={},
                blackout_mwh=0.0,
            )

    def _write(self, database: Path, trace_level: str) -> dict[str, object]:
        ledger = SQLiteMarketLedger(
            database,
            trace_level=trace_level,
            batch_size=2,
            semantic_metadata={
                "run_id": "run-zonal",
                "run_parent_id": "run-parent",
                "data_pack_id": "data-v1",
                "network_pack_id": "network-v1",
                "module_ids": ["ahead-v1", "zonal-v1"],
                "period_hours": 0.5,
            },
        )
        account = _accounting()
        ledger.record_zonal_accounting(
            (ZonalAccountingLedgerRow.from_accounting(account),)
        )
        ledger.record_zones((
            ZonePeriodLedgerRow(2025, 4, "north", 6.0, 8.0, 7.0, -1.0, 0.0, 1.0),
            ZonePeriodLedgerRow(2025, 4, "south", 4.0, 2.0, 3.0, 1.0, 0.0, -1.0),
        ))
        ledger.record_boundaries((BoundaryPeriodLedgerRow(
            2025, 4, "B1", 1.0, 2.0, 3.0, 0.5, 12.0,
            "diagnostic_marginal_value_in_accepted_bid_objective_not_zonal_price_or_cash_cost",
        ),))
        ledger.record_zonal_resources((ZonalResourceDispatchRow(
            2025, 4, "gas", "gas-owner", "south", "ccgt", 2.0, 3.0, 1.0,
            0.0, 0.0, 0.0, 40.0,
        ),))
        ledger.record_redispatch_settlements((
            RedispatchSettlementRow(
                "bid-gas-up", 2025, 4, "gas-owner", "gas", "south", "ccgt", "up",
                2.0, 1.0, 35.0, 35.0, "accepted", "zonal_redispatch_up",
            ),
            RedispatchSettlementRow(
                "bid-gas-extra", 2025, 4, "gas-owner", "gas", "south", "ccgt", "up",
                1.0, 0.0, 35.0, 0.0, "rejected", "not_required_at_optimum",
            ),
        ))
        ledger.record_reliability_events((ReliabilityEventRow(
            "event-1", 2025, 4, 5, 2, 1.0, 3.0, '["north"]', 2.0,
            "observed_loss_of_load_chronology_not_statistical_lole",
        ),))
        ledger.record_solver_links((SolverDeclarationLinkRow(
            2025, 4, "c" * 64, "market/declared-input.json",
            "market/solver-diagnostics.json", None, "optimal",
        ),))
        return ledger.close()

    def test_v7_round_trip_queries_indexes_and_full_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "market.sqlite"
            metadata = self._write(database, "full")
            period = query_market_table(
                database, "zonal_period_accounting", year=2025
            )
            zones = query_zonal_results(database, {"view": "zone", "zone_id": "north"})
            boundaries = query_zonal_results(database, {"view": "boundary", "boundary_id": "B1"})
            agents = query_zonal_results(database, {"view": "agent", "agent_id": "gas-owner", "status": "accepted"})
            reliability = query_zonal_results(database, {"view": "reliability"})
            export = export_zonal_results(
                database,
                {"view": "boundary", "boundary_id": "B1"},
                root / "boundary.jsonl",
            )
            with closing(sqlite3.connect(database)) as connection:
                version = connection.execute(
                    "SELECT value FROM metadata WHERE key='schema_version'"
                ).fetchone()[0]
                indexes = {row[1] for row in connection.execute("PRAGMA index_list(zone_period_summary)")}
            self.assertEqual(version, "value.market-ledger/v7")
            self.assertEqual(
                period["items"][0]["network_constraint_cost_gbp"], 25.0
            )
            self.assertEqual(zones["total"], 1)
            self.assertEqual(boundaries["items"][0]["shadow_value_semantics"].split("_")[0], "diagnostic")
            self.assertEqual(agents["items"][0]["cashflow_to_agent_gbp"], 35.0)
            self.assertEqual(reliability["items"][0]["event_duration_hours"], 1.0)
            self.assertEqual(export["rows"], 1)
            self.assertIn("zone_period_year_zone", indexes)
            self.assertEqual(metadata["rows"]["redispatch_settlement"], 2)
            dictionary = json.loads((root / "field-dictionary.json").read_text("utf-8"))
            self.assertEqual(dictionary["schema_version"], "value.market-ledger-field-dictionary/v1")
            self.assertEqual(
                dictionary["presentation"]["authoritative_values"],
                "value.market-ledger/v7",
            )
            self.assertIn("network_solver_diagnostics", dictionary["tables"])

    def test_summary_and_full_modes_have_identical_scientific_totals(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = self._write(root / "summary.sqlite", "summary")
            full = self._write(root / "full.sqlite", "full")
            summary_result = query_market_table(
                root / "summary.sqlite", "zonal_period_accounting"
            )
            full_result = query_market_table(
                root / "full.sqlite", "zonal_period_accounting"
            )
            self.assertEqual(summary_result["items"], full_result["items"])
            self.assertEqual(summary["rows"]["redispatch_settlement"], 0)
            self.assertEqual(full["rows"]["redispatch_settlement"], 2)

    def test_cem_headline_keeps_zonal_settlements_out_of_resource_cost(self):
        market = MarketYearResult(
            result_id="zonal:2025", year=2025, module_id="staged", module_version="1",
            generation_mwh_by_asset={"gas": 10.0}, market_income_gbp_by_agent={},
            total_system_cost_gbp=999.0, total_operational_cost_gbp=40.0,
            total_levelized_capital_cost_gbp=60.0, total_demand_mwh=10.0,
            total_generation_mwh=10.0, total_blackout_mwh=0.0, total_excess_mwh=0.0,
            extensions={"market_settlement_gbp": 480.0, "policy_transfer_gbp": 7.0, "zonal_accounting_gbp": {
                "system_resource_cost_gbp": 100.0,
                "transmission_constraint_resource_cost_gbp": 15.0,
                "national_settlement_gbp": 500.0,
                "redispatch_settlement_gbp": -20.0,
                "policy_transfer_gbp": 7.0,
                "boundary_shadow_value_gbp": 12.0,
            }},
        )
        ledger = build_cem_cost_ledger(market)
        self.assertEqual(ledger.cem_system_cost_gbp, 100.0)
        self.assertEqual(sum(
            line.amount_gbp or 0.0 for line in ledger.lines
            if line.included_in_cem_system_cost
        ), 100.0)
        redispatch = next(line for line in ledger.lines if line.view == "redispatch_settlement")
        self.assertEqual(redispatch.amount_gbp, -20.0)
        self.assertFalse(redispatch.included_in_cem_system_cost)
        self.assertEqual(sum(line.view == "policy_transfer" for line in ledger.lines), 1)
        self.assertFalse(any(line.id == "market_settlement_gbp" for line in ledger.lines))

    def test_v4_database_is_read_only_and_keeps_historical_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript("""
                    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    INSERT INTO metadata VALUES('schema_version', 'value.market-ledger/v4');
                    CREATE TABLE period_summary(year INTEGER, period INTEGER, stage TEXT);
                    INSERT INTO period_summary VALUES(2024, 7, 'final_dispatch');
                """)
                connection.commit()
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            capabilities = market_ledger_capabilities(database)
            validation = validate_market_ledger_file(database)
            with self.assertRaisesRegex(
                InvariantError, "GF_LEDGER_SCHEMA_RESUME_MISMATCH"
            ):
                SQLiteMarketLedger(database, trace_level="summary")
            after = hashlib.sha256(database.read_bytes()).hexdigest()
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM period_summary").fetchone()[0], 1)
            self.assertEqual(before, after)
            self.assertTrue(validation["valid"])
            self.assertEqual(capabilities["attribution_status"], "legacy_partial")
            self.assertFalse(
                capabilities["redispatch_avoided_curtailment_available"]
            )

    def test_interrupted_batch_is_recoverable_and_malformed_rows_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            first = SQLiteMarketLedger(database, trace_level="summary", batch_size=1)
            first.record_zones((ZonePeriodLedgerRow(2025, 0, "north", 1, 1, 1, 0, 0, 0),))
            first.connection.close()  # simulate an interrupted process after the committed batch
            second = SQLiteMarketLedger(database, trace_level="summary")
            second.record_zones((ZonePeriodLedgerRow(2025, 1, "north", 1, 1, 1, 0, 0, 0),))
            second.close()
            self.assertEqual(query_zonal_results(database, {"view": "zone"})["total"], 2)
            with self.assertRaisesRegex(ValueError, "finite"):
                ZonePeriodLedgerRow(2025, 2, "north", float("nan"), 1, 1, 0, 0, 0)

    def test_zonal_rows_require_run_pack_module_and_parent_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = SQLiteMarketLedger(
                Path(folder) / "market.sqlite", trace_level="summary"
            )
            with self.assertRaisesRegex(ValueError, "immutable run identities"):
                ledger.record_zonal_accounting(
                    (ZonalAccountingLedgerRow.from_accounting(_accounting()),)
                )
            ledger.close()

    def test_observed_reliability_events_use_chronology_not_lole_claim(self):
        events = build_reliability_events([
            {"year": 2025, "period": 0, "load_shedding_mwh_by_zone": {"north": 1.0}},
            {"year": 2025, "period": 1, "load_shedding_mwh_by_zone": {"north": 2.0, "south": 0.5}},
            {"year": 2025, "period": 2, "load_shedding_mwh_by_zone": {}},
            {"year": 2025, "period": 3, "load_shedding_mwh_by_zone": {"south": 1.5}},
        ], period_hours=0.5)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_duration_hours, 1.0)
        self.assertEqual(events[0].unserved_mwh, 3.5)
        self.assertEqual(json.loads(events[0].affected_zones_json), ["north", "south"])
        self.assertNotIn("lole", events[0].metric_semantics.split("not_")[0])

    def test_indexed_query_latency_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary", batch_size=1000)
            ledger.record_zones(
                ZonePeriodLedgerRow(2025, period, zone, 1, 1, 1, 0, 0, 0)
                for period in range(2000)
                for zone in ("north", "south")
            )
            ledger.close()
            started = time.perf_counter()
            page = query_zonal_results(database, {"view": "zone", "zone_id": "south", "limit": 50})
            elapsed = time.perf_counter() - started
            self.assertEqual(page["total"], 2000)
            self.assertLess(elapsed, 0.5)

    def test_generic_query_api_accepts_new_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            self._write(database, "full")
            page = query_market_table(database, "boundary_period_summary", boundary_id="B1")
            self.assertEqual(page["total"], 1)


if __name__ == "__main__":
    unittest.main()
