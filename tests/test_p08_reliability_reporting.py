"""P0-8 S6: one load-shedding reporting threshold; v3 ledgers are annotated."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import closing

from gridform_core.zonal_results import (
    LOAD_SHEDDING_REPORTING_THRESHOLD_MWH,
    V3_LOCK_DEFECT,
    build_reliability_events,
    is_reportable_shedding,
    ledger_known_defects,
)
from gridform_core.zonal_solver_contract import (
    SOLVER_CONTRACT_VERSION,
    V3_SOLVER_CONTRACT_VERSION,
)


def period(index: int, shedding: dict[str, float]) -> dict[str, object]:
    return {"year": 2025, "period": index, "load_shedding_mwh_by_zone": shedding}


class ReliabilityThresholdTests(unittest.TestCase):
    def test_numerical_residue_is_not_an_event(self) -> None:
        self.assertEqual(LOAD_SHEDDING_REPORTING_THRESHOLD_MWH, 1e-6)
        self.assertFalse(is_reportable_shedding(5e-7))
        self.assertTrue(is_reportable_shedding(0.4))
        events = build_reliability_events(
            [period(0, {"south": 5e-7}), period(1, {"south": 5e-7, "north": 0.0})],
            period_hours=0.5,
        )
        self.assertEqual(events, ())

    def test_real_shedding_is_an_event_and_residue_does_not_join_it(self) -> None:
        events = build_reliability_events(
            [
                period(0, {"south": 0.4, "north": 5e-7}),
                period(1, {"south": 5e-7}),
                period(2, {"south": 0.2}),
            ],
            period_hours=0.5,
        )
        self.assertEqual(len(events), 2)
        first, second = events
        self.assertEqual((first.start_period, first.end_period), (0, 0))
        self.assertEqual(first.affected_zones_json, '["south"]')
        self.assertAlmostEqual(first.unserved_mwh, 0.4)
        self.assertEqual(first.event_duration_hours, 0.5)
        self.assertEqual((second.start_period, second.end_period), (2, 2))


class KnownDefectTests(unittest.TestCase):
    def ledger(self, contract: str) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE network_solver_diagnostics (solver_contract_version TEXT)"
        )
        connection.executemany(
            "INSERT INTO network_solver_diagnostics VALUES (?)", [(contract,)] * 3
        )
        return connection

    def test_v3_ledger_is_annotated_without_rewriting_rows(self) -> None:
        with closing(self.ledger(V3_SOLVER_CONTRACT_VERSION)) as connection:
            before = connection.execute(
                "SELECT * FROM network_solver_diagnostics"
            ).fetchall()
            defects = ledger_known_defects(connection, {"network_solver_diagnostics"})
            after = connection.execute(
                "SELECT * FROM network_solver_diagnostics"
            ).fetchall()
        self.assertEqual(before, after)
        self.assertEqual([row["defect_id"] for row in defects], [V3_LOCK_DEFECT["defect_id"]])
        self.assertEqual(defects[0]["evidence_rows"], 3)
        self.assertIn("P2-01", defects[0]["finding_ids"])

    def test_v4_and_empty_ledgers_have_no_v3_defect(self) -> None:
        with closing(self.ledger(SOLVER_CONTRACT_VERSION)) as connection:
            self.assertEqual(ledger_known_defects(connection, {"network_solver_diagnostics"}), [])
        with closing(sqlite3.connect(":memory:")) as connection:
            self.assertEqual(ledger_known_defects(connection, set()), [])


if __name__ == "__main__":
    unittest.main()
