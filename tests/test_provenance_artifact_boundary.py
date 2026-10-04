from __future__ import annotations

import tempfile
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core.provenance import _artifact_index, _is_external_launcher_log
from gridform_core.market_ledger import SQLiteMarketLedger


class ProvenanceArtifactBoundaryTests(unittest.TestCase):
    def test_sqlite_wal_and_shared_memory_sidecars_are_never_sealed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("market.sqlite", "market.sqlite-wal", "market.sqlite-shm"):
                (root / name).write_bytes(name.encode("ascii"))
            with self.assertRaisesRegex(RuntimeError, "live SQLite sidecars"):
                _artifact_index(root, root)

    def test_market_ledger_close_produces_one_immutable_sqlite_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.close()
            self.assertTrue(database.is_file())
            self.assertFalse(database.with_name("market.sqlite-wal").exists())
            self.assertFalse(database.with_name("market.sqlite-shm").exists())
            with closing(sqlite3.connect(
                database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
            )) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
                self.assertEqual(
                    connection.execute("PRAGMA journal_mode").fetchone()[0], "delete"
                )

    def test_external_launcher_logs_are_not_scientific_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "year-results-v2.json").write_text(
                '{"schema_version":"value.year-results/v2"}', encoding="utf-8"
            )
            for name in (
                "background-stdout.log",
                "background-resume2-stderr.log",
                "background_stdout.log",
                "launcher-stderr.log",
                "launcher_stdout.log",
                "model.log",
            ):
                (root / name).write_text("external supervisor output", encoding="utf-8")

            indexed = {row["artifact_id"] for row in _artifact_index(root, root)}

            self.assertIn("year-results-v2.json", indexed)
            self.assertFalse(any(name.endswith(".log") for name in indexed))
            self.assertTrue(_is_external_launcher_log(root / "background-resume2-stdout.log"))
            self.assertFalse(_is_external_launcher_log(root / "market.log.json"))


if __name__ == "__main__":
    unittest.main()
