"""Deterministic relative benchmark for off/summary/full market trace levels."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.market_ledger import OrderLedgerRow, PeriodLedgerRow, StorageStateRow, create_market_ledger


def run(level: str, periods: int, orders_per_period: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "market.sqlite"
        ledger = create_market_ledger(path, level, batch_size=500)
        started = time.perf_counter()
        for period in range(periods):
            ledger.record_period(PeriodLedgerRow(2025, period, "final_dispatch", 50, 50, 50, 0, 0, 0, 0, 20, 20, 0, 0, 80, 1000, 4000, 0, 0, 0, 0))
            ledger.record_orders(
                OrderLedgerRow(f"{period}:{index}", 2025, period, "ahead_offer", f"asset-{index}", "test", "supply", index, 1, 1, "accepted", "cleared", index, 50)
                for index in range(orders_per_period)
            )
            ledger.record_storage((StorageStateRow(2025, period, "battery", 1, 0, 0, 1, 4),))
        metadata = ledger.close()
        wall = time.perf_counter() - started
        metadata.pop("uri", None)
        return {"trace_level": level, "wall_seconds": wall, **metadata}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--periods", type=int, default=2000)
    parser.add_argument("--orders", type=int, default=50)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = [run(level, args.periods, args.orders) for level in ("off", "summary", "full")]
    baseline = float(results[0]["wall_seconds"])
    for row in results:
        row["wall_overhead_seconds_vs_off"] = float(row["wall_seconds"]) - baseline
    report = {
        "runtime": platform.platform(),
        "python": platform.python_version(),
        "fixture": {"periods": args.periods, "orders_per_period": args.orders},
        "results": results,
    }
    encoded = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
