from __future__ import annotations

import io
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from gridform_core.application import run_project_application
from gridform_core.errors import InvariantError
from gridform_core.market_ledger import (
    LEGACY_WRITER_SCHEMA_VERSION,
    SQLiteMarketLedger,
)
from gridform_core.market_ownership import MarketLedgerOwnershipLease
from gridform_core.v2.contracts import ResolvedRun, YearState
from gridform_core.v2.orchestrator import (
    CancellationRequested,
    json_checkpoint_writer,
)


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"


class NativeCheckpointResumeTests(unittest.TestCase):
    def test_annual_supersession_callback_requires_successful_write_and_reload(self):
        run = ResolvedRun(
            "annual-writer",
            "project",
            "scenario",
            "pack",
            2025,
            2025,
            {},
            {"clock.period_hours": 0.5},
            {},
        )
        state = YearState(2026, (), ())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "checkpoints-v2"
            superseded: list[tuple[int, str]] = []
            writer = json_checkpoint_writer(
                directory,
                run,
                on_verified=lambda verified_state, digest: superseded.append(
                    (verified_state.year, digest)
                ),
            )
            writer(state)
            annual = directory / "state-2026.json"
            self.assertEqual(superseded, [(2026, hashlib.sha256(annual.read_bytes()).hexdigest())])

            superseded.clear()
            with patch(
                "gridform_core.v2.orchestrator.load_json_checkpoint",
                side_effect=ValueError("reload failed"),
            ):
                with self.assertRaisesRegex(ValueError, "reload failed"):
                    writer(state)
            self.assertEqual(superseded, [])

    def _project(self) -> dict[str, object]:
        project = json.loads(
            (ROOT / "tests" / "fixtures" / "prompt08_audit_project.json")
            .read_text(encoding="utf-8")
        )
        project.update({"id": "native-resume", "data_pack_id": PACK.name})
        project["modules"] = dict(project["modules"])
        project["modules"]["psm"] = "value-perfect-foresight-lp"
        project["modules"]["transition"] = "value-annual-state-transition"
        project["modules"].pop("storage_cost", None)
        return project

    def test_mismatched_legacy_schema_fails_closed_without_retaining_writer_lease(self):
        with tempfile.TemporaryDirectory(prefix="legacy-ledger-mismatch-") as temporary:
            database = Path(temporary) / "market.sqlite"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                    ("value.market-ledger/v6",),
                )
                connection.commit()

            ledger = SQLiteMarketLedger.__new__(SQLiteMarketLedger)
            with self.assertRaisesRegex(
                InvariantError, "GF_LEDGER_SCHEMA_RESUME_MISMATCH"
            ):
                ledger.__init__(
                    database,
                    trace_level="summary",
                    _schema_version=LEGACY_WRITER_SCHEMA_VERSION,
                )

            self.assertFalse(ledger._ownership_lease.is_live)
            with MarketLedgerOwnershipLease.acquire(database, role="recovery"):
                pass

    def test_cancel_after_year_then_resume_matches_uninterrupted_results(self):
        with tempfile.TemporaryDirectory(prefix="force-resume-") as temporary:
            root = Path(temporary)
            output = root / "resumed" / "model-output"
            quiet = io.StringIO()
            calls = iter((False, True))
            with patch(
                "gridform_core.application.cancellation_requested",
                side_effect=lambda _path: next(calls),
            ), redirect_stdout(quiet), redirect_stderr(quiet):
                with self.assertRaises(CancellationRequested):
                    run_project_application(
                        self._project(), run_id="resume-proof", pack_root=PACK,
                        output_dir=output, mode="two_year_smoke",
                    )
            self.assertTrue((output / "checkpoints-v2" / "state-2026.json").is_file())
            self.assertTrue((output / "partial-year-results" / "year-2025.json").is_file())

            with patch(
                "gridform_core.application.cancellation_requested", return_value=False
            ), redirect_stdout(quiet), redirect_stderr(quiet):
                resumed = run_project_application(
                    self._project(), run_id="resume-proof", pack_root=PACK,
                    output_dir=output, mode="two_year_smoke",
                    resume_checkpoint_id=None,
                )
                uninterrupted = run_project_application(
                    self._project(), run_id="uninterrupted-proof", pack_root=PACK,
                    output_dir=root / "uninterrupted", mode="two_year_smoke",
                )
            self.assertEqual(
                [row["year"] for row in resumed["orchestrator_results"]],
                [2025, 2026],
            )
            # Run IDs differ, so compare the scientific market results rather
            # than identity-bearing envelopes.
            resumed_markets = [dict(row["market"]) for row in resumed["orchestrator_results"]]
            uninterrupted_markets = [dict(row["market"]) for row in uninterrupted["orchestrator_results"]]
            for row in [*resumed_markets, *uninterrupted_markets]:
                row.pop("result_id", None)
                # Runtime artefacts are expected to differ between a resumed
                # run and a separately executed control run.  Their paths,
                # compressed-file hashes and SQLite writer timings are not
                # scientific model outputs; generation, prices, costs,
                # storage/SOC summaries and solver diagnostics remain under
                # exact comparison below.
                row.pop("artifacts", None)
                extensions = dict(row.get("extensions") or {})
                extensions.pop("market_ledger", None)
                row["extensions"] = extensions
            self.assertEqual(resumed_markets, uninterrupted_markets)
            self.assertEqual(resumed["cem_cost_ledgers"], uninterrupted["cem_cost_ledgers"])


if __name__ == "__main__":
    unittest.main()
