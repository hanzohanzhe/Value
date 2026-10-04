import tempfile
import time
import unittest
from pathlib import Path

from gridform_core.market_ledger import OrderLedgerRow, PeriodLedgerRow, SQLiteMarketLedger


def period(index):
    return PeriodLedgerRow(
        2025, index, "final_dispatch", 50.0, 49.0, 50.0,
        1.0, 2.0, 0.0, 0.0, 20.0, 19.0, 1.0, 2.0,
        80.0, 1000.0, 4000.0, 0.0, 0.0, 0.0, 0.0,
    )


class MarketLedgerBenchmarkTests(unittest.TestCase):
    def test_two_thousand_period_fifty_order_benchmark(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            started = time.perf_counter()
            full = SQLiteMarketLedger(root / "full.sqlite", trace_level="full", batch_size=1000)
            for index in range(2_000):
                full.record_period(period(index))
                full.record_orders(
                    OrderLedgerRow(
                        f"{index}:{order}", 2025, index, "ahead_offer",
                        f"asset-{order}", "fixture", "supply", float(order), 1.0,
                        1.0 if order < 10 else 0.0,
                        "accepted" if order < 10 else "rejected", "benchmark",
                        float(order), float(order),
                    )
                    for order in range(50)
                )
            metadata = full.close()
            full_seconds = time.perf_counter() - started
            self.assertEqual(metadata["rows"]["period_summary"], 2_000)
            self.assertEqual(metadata["rows"]["orders"], 100_000)
            self.assertLess(full_seconds, 30.0)

            started = time.perf_counter()
            summary = SQLiteMarketLedger(root / "summary.sqlite", trace_level="summary", batch_size=1000)
            for index in range(2_000):
                summary.record_period(period(index))
                summary.record_orders(())
            summary_metadata = summary.close()
            summary_seconds = time.perf_counter() - started
            self.assertEqual(summary_metadata["rows"]["period_summary"], 2_000)
            self.assertLess(summary_seconds, 10.0)
            self.assertLess(summary_metadata["bytes"], 10 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
