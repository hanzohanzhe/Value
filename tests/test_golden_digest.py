"""Unit tests for gridform_validation.golden (table x column digests, zones, revisions)."""

from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gridform_validation import golden

ROOT = Path(__file__).resolve().parents[1]
ZONES = golden.ZoneRules(
    (
        ("*::*module_version*", "identity"),
        ("market/market.sqlite::period_summary.energy_balance_residual_mwh", "accounting"),
        ("ledgers/*", "accounting"),
    )
)


def _write_run(root: Path, *, price: float = 42.5, residual: float = 0.0, extra_column: bool = False, version: str = "5.1.0") -> Path:
    (root / "market").mkdir(parents=True, exist_ok=True)
    (root / "ledgers").mkdir(exist_ok=True)
    database = root / "market" / "market.sqlite"
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    columns = "year INTEGER, period INTEGER, clearing_price_gbp_per_mwh REAL, energy_balance_residual_mwh REAL"
    if extra_column:
        columns += ", shortfall_mwh REAL"
    connection.execute(f"CREATE TABLE period_summary ({columns})")
    for period in range(3):
        values = [2025, period, price + period, residual]
        if extra_column:
            values.append(0.0)
        connection.execute(f"INSERT INTO period_summary VALUES ({','.join('?' * len(values))})", values)
    connection.commit()
    connection.close()
    (root / "ledgers" / "annual-cost-ledger.json").write_text(
        json.dumps({"years": [{"year": 2025, "cost_gbp": 10.0, "writer_seconds": 0.123, "uri": str(root)}]}),
        encoding="utf-8",
    )
    (root / "year-results-v2.json").write_text(
        json.dumps([{"year": 2025, "market": {"module_version": version, "by_period": {"2025:0": 1.0, "2025:1": 2.0}}}]),
        encoding="utf-8",
    )
    (root / "provenance.json").write_text(json.dumps({"anything": str(root)}), encoding="utf-8")
    return root


class GoldenDigestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)

    def test_digest_is_per_column_zoned_and_independent_of_output_location(self) -> None:
        first = golden.digest_run(_write_run(self.root / "a"), ZONES)
        second = golden.digest_run(_write_run(self.root / "elsewhere" / "b"), ZONES)
        self.assertEqual(golden.compare_digests(first, second), [])
        columns = first["columns"]
        self.assertIn("market/market.sqlite::period_summary.clearing_price_gbp_per_mwh", columns)
        self.assertIn("market/market.sqlite::period_summary.#rows", columns)
        self.assertEqual(columns["market/market.sqlite::period_summary.clearing_price_gbp_per_mwh"]["zone"], "trajectory")
        self.assertEqual(columns["market/market.sqlite::period_summary.energy_balance_residual_mwh"]["zone"], "accounting")
        self.assertEqual(columns["year-results-v2.json::market.module_version"]["zone"], "identity")
        # Period-id dict keys fold into one column; volatile keys and excluded artifacts vanish.
        self.assertIn("year-results-v2.json::market.by_period.{}", columns)
        self.assertFalse(any("writer_seconds" in key or "uri" in key for key in columns))
        self.assertFalse(any(key.startswith("provenance.json") for key in columns))
        self.assertEqual(golden.section_of("market/market.sqlite::orders.accepted_mwh"), "dispatch")
        self.assertEqual(golden.section_of("ledgers/annual-cost-ledger.json::years"), "economics")
        self.assertEqual(golden.section_of("validation/scientific-validation.json::passed"), "reporting")

    def test_changes_are_reported_by_zone_and_kind(self) -> None:
        base = golden.digest_run(_write_run(self.root / "a"), ZONES)
        changed = golden.digest_run(_write_run(self.root / "b", price=43.0, residual=0.5, extra_column=True, version="5.2.0"), ZONES)
        differences = {row.key: row for row in golden.compare_digests(base, changed)}
        self.assertEqual(differences["market/market.sqlite::period_summary.clearing_price_gbp_per_mwh"].zone, "trajectory")
        self.assertEqual(differences["market/market.sqlite::period_summary.energy_balance_residual_mwh"].zone, "accounting")
        self.assertEqual(differences["market/market.sqlite::period_summary.shortfall_mwh"].kind, "added")
        self.assertEqual(differences["year-results-v2.json::market.module_version"].zone, "identity")

    def test_tolerance_mode_ignores_last_bit_float_noise(self) -> None:
        base = golden.digest_run(_write_run(self.root / "a", price=42.5), ZONES)
        noisy = golden.digest_run(_write_run(self.root / "b", price=42.5 + 1e-13), ZONES)
        self.assertTrue(golden.compare_digests(base, noisy, "exact"))
        self.assertEqual(golden.compare_digests(base, noisy, "tolerance"), [])

    def test_zone_rules_file_is_valid_and_first_match_wins(self) -> None:
        rules = golden.ZoneRules.load(ROOT / "tests" / "golden" / "zones.json")
        self.assertEqual(rules.zone("market/market.sqlite::orders.accepted_mwh"), "trajectory")
        self.assertEqual(rules.zone("market/market.sqlite::period_summary.raw_energy_balance_residual_mwh"), "accounting")
        self.assertEqual(rules.zone("market/market.sqlite::period_integrity.science_hash"), "identity")
        self.assertEqual(rules.zone("ledgers/annual-cost-ledger.json::years.lines"), "accounting")
        self.assertEqual(rules.zone("ledgers/annual-cost-ledger.json::schema_version"), "identity")
        self.assertEqual(rules.zone("market/market.sqlite::storage_state.state_of_charge_mwh"), "trajectory")
        self.assertEqual(rules.zone("year-results-v2.json::investment.proposals"), "trajectory")
        self.assertEqual(rules.zone("year-results-v2.json::next_state.assets.capacity_mw"), "trajectory")
        with self.assertRaises(ValueError):
            golden.ZoneRules.load(self._zones_file([{"pattern": "*", "zone": "bogus"}]))

    def _zones_file(self, rules) -> Path:
        path = self.root / "zones.json"
        path.write_text(json.dumps({"rules": rules}), encoding="utf-8")
        return path

    def _golden(self, family: str) -> dict:
        digest = golden.digest_run(_write_run(self.root / "base"), ZONES)
        return golden.new_golden(family, "X1", digest, "abc", "revision 0")

    def test_revisions_need_reason_and_correction_and_record_delta(self) -> None:
        record = self._golden("corrected")
        accounting = golden.digest_run(_write_run(self.root / "acc", residual=0.25), ZONES)
        with self.assertRaises(ValueError):
            golden.append_revision(copy.deepcopy(record), accounting, base_commit="def", reason="", correction_ids=["p0-4.x"])
        with self.assertRaises(ValueError):
            golden.append_revision(copy.deepcopy(record), accounting, base_commit="def", reason="why", correction_ids=[])
        with self.assertRaises(ValueError):
            golden.append_revision(copy.deepcopy(record), golden.latest_digest(record), base_commit="def", reason="why", correction_ids=["a.b"])
        revision = golden.append_revision(record, accounting, base_commit="def", reason="residual fix", correction_ids=["p0-4.residual"])
        self.assertEqual(revision["revision"], 1)
        self.assertEqual(revision["delta"]["by_zone"], {"accounting": 1})
        self.assertEqual(golden.validate_golden_file(record, {"findings": {}}), [])

    def test_doctoral_trajectory_change_needs_an_approved_finding_once(self) -> None:
        allowlist = {"findings": {"P6-24": "approved universal correction"}}
        record = self._golden("doctoral")
        moved = golden.digest_run(_write_run(self.root / "moved", price=50.0), ZONES)
        unapproved = copy.deepcopy(record)
        golden.append_revision(unapproved, moved, base_commit="d", reason="kernel change", correction_ids=["p0-6.bid"])
        self.assertTrue(any("trajectory" in error for error in golden.validate_golden_file(unapproved, allowlist)))

        approved = copy.deepcopy(record)
        golden.append_revision(approved, moved, base_commit="d", reason="interconnector clock", correction_ids=["p0-5.ic"], findings=["P6-24"])
        self.assertEqual(golden.validate_golden_file(approved, allowlist), [])
        moved_again = golden.digest_run(_write_run(self.root / "again", price=60.0), ZONES)
        golden.append_revision(approved, moved_again, base_commit="e", reason="again", correction_ids=["p0-5.ic"], findings=["P6-24"])
        self.assertTrue(any("again" in error for error in golden.validate_golden_file(approved, allowlist)))

        accounting_only = copy.deepcopy(record)
        golden.append_revision(
            accounting_only,
            golden.digest_run(_write_run(self.root / "acc", residual=1.0), ZONES),
            base_commit="d",
            reason="ledger correction",
            correction_ids=["p0-4.ledger"],
        )
        self.assertEqual(golden.validate_golden_file(accounting_only, allowlist), [])

    def test_tampered_delta_is_detected(self) -> None:
        record = self._golden("corrected")
        golden.append_revision(
            record,
            golden.digest_run(_write_run(self.root / "acc", residual=0.25), ZONES),
            base_commit="d",
            reason="x",
            correction_ids=["a.b"],
        )
        record["revisions"][1]["delta"]["differences"] = []
        self.assertTrue(any("delta" in error for error in golden.validate_golden_file(record, {"findings": {}})))


if __name__ == "__main__":
    unittest.main()
