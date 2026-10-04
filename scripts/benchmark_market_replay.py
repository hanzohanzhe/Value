"""Measure bounded VALUE replay writes and read-model queries."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.clearing_inputs import ClearingInputRow, ClearingOutcomeRow
from gridform_core.market_ledger import (
    OrderLedgerRow,
    PeriodLedgerRow,
    PhysicalDispatchRow,
    SQLiteMarketLedger,
)
from gridform_core.market_replay import (
    query_auction_view,
    query_dispatch_timeline,
    query_vre_curtailment_summary,
)


def benchmark(periods: int, trace_level: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "market.sqlite"
        started = time.perf_counter()
        ledger = SQLiteMarketLedger(
            database,
            trace_level=trace_level,
            batch_size=1000,
            semantic_metadata={
                "period_hours": .5,
                "timezone": "Europe/London",
                "calendar": "fixed_365_day_local_periods",
                "excess_scope": "inflexible_mixed",
                "excess_relationship": "separate_prebalancing",
            },
        )
        for period in range(periods):
            ledger.record_period(PeriodLedgerRow(
                2025, period, "final_dispatch", 100.0, 100.0, 100.0,
                0.0, 0.0, 0.0, 0.0, 60.0, 50.0, 10.0, 0.0,
                70.0, 5000.0, 7000.0, 0.0, 0.0, 0.0, 0.0,
            ))
            ledger.record_physical_dispatch((
                PhysicalDispatchRow(2025, period, "solar", "solar", "generation", 50.0, 50.0, "physical_asset"),
                PhysicalDispatchRow(2025, period, "ccgt", "ccgt", "generation", 50.0, 50.0, "physical_asset"),
                PhysicalDispatchRow(2025, period, "unused-vre", "solar", "balancing_curtailment", 10.0, 0.0, "vre_aggregate"),
            ))
            if trace_level == "full":
                declared = ClearingInputRow.create(
                    year=2025, period=period, stage="ahead",
                    information_scope="forecast only",
                    payload={"period_hours": .5, "target_power_mw": 200.0, "offers": [
                        {"offer_id": f"solar-{period}", "asset_id": "solar", "asset_type": "SolarGenerator", "resource_kind": "vre", "offer_price_gbp_per_mwh": 0.0, "maximum_power_mw": 100.0},
                        {"offer_id": f"ccgt-{period}", "asset_id": "ccgt", "asset_type": "GasGenerator", "resource_kind": "thermal", "offer_price_gbp_per_mwh": 70.0, "maximum_power_mw": 100.0},
                    ]},
                )
                ledger.record_clearing_input(declared)
                ledger.record_clearing_outcome(ClearingOutcomeRow.create(
                    declared.input_sha256,
                    {"accepted": [
                        {"asset_id": "solar", "accepted_power_mw": 100.0, "offer_price_gbp_per_mwh": 0.0},
                        {"asset_id": "ccgt", "accepted_power_mw": 100.0, "offer_price_gbp_per_mwh": 70.0},
                    ]},
                ))
                ledger.record_orders((
                    OrderLedgerRow(f"solar-{period}", 2025, period, "ahead", "solar", "vre", "supply", 0.0, 50.0, 50.0, "accepted", "cleared", 0.0, 0.0),
                    OrderLedgerRow(f"ccgt-{period}", 2025, period, "ahead", "ccgt", "thermal", "supply", 70.0, 50.0, 50.0, "accepted", "cleared", 3500.0, 3500.0),
                ))
        metadata = ledger.close()
        build_seconds = time.perf_counter() - started

        query_started = time.perf_counter()
        daily = query_dispatch_timeline(database, year=2025, resolution="daily", limit=500)
        daily_seconds = time.perf_counter() - query_started
        query_started = time.perf_counter()
        weekly = query_dispatch_timeline(database, year=2025, resolution="weekly", limit=500)
        weekly_seconds = time.perf_counter() - query_started
        query_started = time.perf_counter()
        vre = query_vre_curtailment_summary(database)
        vre_seconds = time.perf_counter() - query_started
        auction_seconds = None
        if trace_level == "full":
            query_started = time.perf_counter()
            query_auction_view(database, year=2025, period=min(periods - 1, 1), stage="ahead")
            auction_seconds = time.perf_counter() - query_started
        return {
            "periods": periods,
            "trace_level": trace_level,
            "database_bytes": metadata["bytes"],
            "rows": metadata["rows"],
            "wall_seconds": build_seconds,
            "sqlite_writer_seconds": metadata["writer_seconds"],
            "daily_query_seconds": daily_seconds,
            "daily_payload_bytes": len(json.dumps(daily, separators=(",", ":")).encode("utf-8")),
            "weekly_query_seconds": weekly_seconds,
            "weekly_payload_bytes": len(json.dumps(weekly, separators=(",", ":")).encode("utf-8")),
            "vre_summary_query_seconds": vre_seconds,
            "vre_summary_payload_bytes": len(json.dumps(vre, separators=(",", ":")).encode("utf-8")),
            "auction_query_seconds": auction_seconds,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "schema_version": "value.market-replay-benchmark/v1",
        "scope": "synthetic writer and bounded read-model benchmark; not PSM runtime",
        "cases": [benchmark(48, "full"), benchmark(336, "full"), benchmark(17_520, "summary")],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
