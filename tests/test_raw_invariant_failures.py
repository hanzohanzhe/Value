"""Spec 11.3 (R-D1): the withheld notice and status bar name the raw invariant that failed."""

from __future__ import annotations

import unittest

from gridform_core.result_advisories import compact_validation_fields, raw_invariant_failures

# The four-role report's doctoral VALUE 101 day (before R4-1): the energy
# balance is conformant; storage single direction failed in 10 rows, explained
# by DEV-STO-01, which R4-1 (A26) corrected and withdrew.
DOCTORAL_DAY = {
    "run_invariant_status": "passed",
    "energy_balance_status": "reproduction_conformant",
    "energy_balance": {"gate_failed_checks": [], "balance_account": {"open_periods": 0}},
    "storage_invariant_status": "reproduction_with_declared_deviations",
    "storage_invariants": {
        "failed_checks": ["storage.single_direction"],
        "checks": [
            {"id": "storage.rated_power", "status": "passed", "count": 0},
            {"id": "storage.single_direction", "status": "failed", "count": 10},
        ],
    },
    "declared_deviations": {
        "matched": [{"check": "storage.single_direction", "matcher": "stage_power_reset", "deviation_ids": ["DEV-STO-01"], "rows": 10}],
        "unexplained_checks": [],
    },
    "raw_invariants": {"status": "failed"},
}


class RawInvariantFailureTests(unittest.TestCase):
    def test_declared_storage_failure_names_the_check_rows_and_deviation(self):
        failures = raw_invariant_failures(DOCTORAL_DAY)
        self.assertEqual(len(failures), 1)
        failure = failures[0]
        self.assertEqual((failure["gate"], failure["check"], failure["name"]), ("storage_invariants", "storage.single_direction", "Storage single direction"))
        self.assertEqual((failure["count"], failure["unit"]), (10, "rows"))
        self.assertEqual(failure["deviation_ids"], ["DEV-STO-01"])
        summary = failure["deviations"][0]["summary"]
        # R4-1 (A26): the withdrawn entry keeps the evidence of earlier Runs readable.
        self.assertTrue(summary.startswith("Before R4-1 the doctoral default PSM reset a store's power limit"), summary)
        self.assertTrue(summary.endswith("."))
        self.assertNotIn("Corrected in both profiles", summary)  # one sentence only

    def test_unexplained_failure_has_no_deviation(self):
        evidence = {
            **DOCTORAL_DAY,
            "storage_invariant_status": "failed",
            "storage_invariants": {"failed_checks": ["storage.soc_bounds"], "checks": [{"id": "storage.soc_bounds", "status": "failed", "count": 3}]},
            "declared_deviations": {"matched": [], "unexplained_checks": ["storage.soc_bounds"]},
        }
        [failure] = raw_invariant_failures(evidence)
        self.assertEqual((failure["name"], failure["count"], failure["deviation_ids"]), ("Storage state-of-charge bounds", 3, []))

    def test_energy_balance_account_counts_periods_and_gates_without_detail_use_their_name(self):
        evidence = {
            "run_invariant_status": "failed", "run_invariants": {},
            "energy_balance_status": "reproduction_with_declared_deviations",
            "energy_balance": {"gate_failed_checks": ["period.balance_account"], "balance_account": {"open_periods": 4}},
            "declared_deviations": {"matched": [{"check": "period.balance_account", "deviation_ids": ["DEV-BAL-04"], "periods": 4}]},
        }
        failures = raw_invariant_failures(evidence)
        self.assertEqual([(row["name"], row["count"], row["unit"]) for row in failures],
                         [("Run invariants", None, None), ("Energy balance account", 4, "periods")])
        self.assertEqual(failures[1]["deviation_ids"], ["DEV-BAL-04"])

    def test_passing_or_unevaluated_evidence_lists_nothing(self):
        self.assertEqual(raw_invariant_failures({"run_invariant_status": "passed", "energy_balance_status": "reproduction_conformant", "storage_invariant_status": "reproduction_conformant"}), [])
        self.assertEqual(raw_invariant_failures({"energy_balance_status": "not_evaluated"}), [])

    def test_the_listing_row_keeps_the_failures(self):
        row = compact_validation_fields({"raw_invariant_failures": raw_invariant_failures(DOCTORAL_DAY) * 12, "declared_deviations": {}})
        self.assertEqual(len(row["raw_invariant_failures"]), 10)
        self.assertNotIn("declared_deviations", row)


if __name__ == "__main__":
    unittest.main()
