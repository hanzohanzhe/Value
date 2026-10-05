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

    def test_planned_stress_and_boundary_outputs_are_preregistered_accounting(self) -> None:
        rules = golden.ZoneRules.load(ROOT / "tests" / "golden" / "zones.json")
        for key in (
            "market/market.sqlite::period_summary.shortfall_mwh",  # A2
            "market/market.sqlite::period_summary.stress_flag",  # A2
            "market/market.sqlite::stress_event.event_id",  # A2
            "year-results-v2.json::market.stress_summary.total_shortfall_mwh",  # A2
            "year-results-v2.json::market.stress_summary.stress_periods",  # A2
            "market/market.sqlite::energy_balance_ledger.unserved_mwh",  # A2
            "market/market.sqlite::period_summary.non_vre_spill_mwh",  # Q7
            "market/metadata.json::semantic_metadata.energy_balance_boundary",  # Q7
        ):
            with self.subTest(key=key):
                self.assertEqual(rules.zone(key), "accounting")

    def test_committed_zone_rules_never_weaken_a_pinned_golden_column(self) -> None:
        rules = golden.ZoneRules.load(ROOT / "tests" / "golden" / "zones.json")
        for path in sorted((ROOT / "tests" / "golden").glob("*/*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            pinned = golden.pinned_zones(record)
            current = {"columns": {key: {"zone": rules.zone(key)} for key in pinned}}
            with self.subTest(golden=path.name):
                self.assertEqual(golden.zone_weakenings(pinned, current), [])

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
        # an approved trajectory re-baseline still needs its numeric before/after report
        missing = golden.validate_golden_file(approved, allowlist)
        self.assertTrue(any("numeric before/after report" in error for error in missing), missing)
        report = golden.build_numeric_report(self.root / "base", self.root / "moved", ZONES, family="doctoral", case="X1",
                                             revision=1, parent_commit="c", child_commit="d")
        self.assertEqual(golden.validate_golden_file(approved, allowlist, {1: report}.get), [])
        moved_again = golden.digest_run(_write_run(self.root / "again", price=60.0), ZONES)
        golden.append_revision(approved, moved_again, base_commit="e", reason="again", correction_ids=["p0-5.ic"], findings=["P6-24"])
        self.assertTrue(any("again" in error for error in golden.validate_golden_file(approved, allowlist, {1: report}.get)))

        accounting_only = copy.deepcopy(record)
        golden.append_revision(
            accounting_only,
            golden.digest_run(_write_run(self.root / "acc", residual=1.0), ZONES),
            base_commit="d",
            reason="ledger correction",
            correction_ids=["p0-4.ledger"],
        )
        self.assertEqual(golden.validate_golden_file(accounting_only, allowlist), [])

    def test_numeric_report_records_magnitudes_and_is_bound_to_the_revision(self) -> None:
        record = self._golden("doctoral")
        moved_dir = _write_run(self.root / "moved", price=50.0)
        golden.append_revision(record, golden.digest_run(moved_dir, ZONES), base_commit="d", reason="ic clock",
                               correction_ids=["p0-5.ic"], findings=["P6-24"])
        report = golden.build_numeric_report(self.root / "base", moved_dir, ZONES, family="doctoral", case="X1",
                                             revision=1, parent_commit="c", child_commit="d")
        price = report["columns"]["market/market.sqlite::period_summary.clearing_price_gbp_per_mwh"]
        self.assertEqual(price["zone"], "trajectory")
        self.assertEqual(price["changed_values"], 3)
        self.assertAlmostEqual(price["max_abs_delta"], 7.5)
        self.assertAlmostEqual(price["max_rel_delta"], 7.5 / 42.5)
        self.assertAlmostEqual(price["sum_before"], 42.5 * 3 + 3)
        self.assertAlmostEqual(price["sum_after"], 50.0 * 3 + 3)
        self.assertEqual(price["annual_totals"], {"2025": [price["sum_before"], price["sum_after"]]})
        self.assertEqual(set(report["columns"]), {row["key"] for row in record["revisions"][1]["delta"]["differences"]})
        allowlist = {"findings": {"P6-24": "approved"}}
        self.assertEqual(golden.validate_golden_file(record, allowlist, {1: report}.get), [])
        for field, value in (("revision", 2), ("case", "X2"), ("digest_sha256", "0" * 64)):
            with self.subTest(field=field):
                forged = dict(report, **{field: value})
                errors = golden.validate_golden_file(record, allowlist, {1: forged}.get)
                self.assertTrue(any(field in error for error in errors), errors)
        trimmed = dict(report, columns={})
        self.assertTrue(golden.validate_golden_file(record, allowlist, {1: trimmed}.get))

    def _orders_run(self, name: str, *, insert: bool, storage_bid: float) -> Path:
        """A market log whose order ids are sequence numbers (as in the kernel)."""

        root = self.root / name
        (root / "market").mkdir(parents=True)
        connection = sqlite3.connect(root / "market" / "market.sqlite")
        connection.execute(
            "CREATE TABLE orders (order_id TEXT, year INTEGER, period INTEGER, stage TEXT, asset_id TEXT, "
            "asset_type TEXT, side TEXT, offer_price_gbp_per_mwh REAL, offered_mwh REAL)"
        )
        connection.execute("CREATE TABLE event_log (sequence INTEGER, note TEXT, energy_mwh REAL)")
        assets = [("ccgt", "Thermal", 60.0), ("battery", "Storage", storage_bid), ("wind", "Renewable", 0.0)]
        if insert:
            assets.insert(1, ("ocgt", "Thermal", 90.0))  # a new order in the middle of every period
        for period in range(2):
            for index, (asset, asset_type, price) in enumerate(assets):
                connection.execute(
                    "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"2025:{period}:ahead:{index}", 2025, period, "ahead_offer", asset, asset_type, "supply", price, 10.0 + period),
                )
            for index, (asset, _, _) in enumerate(assets):
                connection.execute("INSERT INTO event_log VALUES (?,?,?)", (period * 10 + index, asset, 1.0 + index))
        connection.commit()
        connection.close()
        return root

    def test_numeric_report_aligns_rows_on_natural_keys_when_a_row_is_inserted(self) -> None:
        before = self._orders_run("orders-before", insert=False, storage_bid=5.0)
        after = self._orders_run("orders-after", insert=True, storage_bid=12.0)  # +7 GBP/MWh on storage
        report = golden.build_numeric_report(before, after, golden.ZoneRules(()), family="doctoral", case="X1",
                                             revision=1, parent_commit="c", child_commit="d")
        self.assertEqual(report["schema_version"], "value.golden-numeric-report/v2")
        columns = report["columns"]
        price = columns["market/market.sqlite::orders.offer_price_gbp_per_mwh"]
        self.assertEqual(price["alignment"], "keyed (year, period, stage, asset_id, side)")
        self.assertTrue(price["comparable"])
        self.assertEqual(price["changed_values"], 2)  # the storage offer in each period, not the shifted rows
        self.assertAlmostEqual(price["max_abs_delta"], 7.0)
        self.assertAlmostEqual(price["max_rel_delta"], 7.0 / 5.0)
        self.assertEqual((price["rows_only_before"], price["rows_only_after"]), (0, 2))
        self.assertAlmostEqual(price["sum_after"] - price["sum_before"], 2 * 7.0 + 2 * 90.0)
        self.assertEqual(price["annual_totals"], {"2025": [price["sum_before"], price["sum_after"]]})
        self.assertEqual(price["totals_by_asset_type"]["Storage"], [10.0, 24.0])
        self.assertEqual(price["totals_by_asset_type"]["Thermal"], [120.0, 300.0])
        self.assertEqual(price["period_totals"]["groups"], 2)
        self.assertEqual(price["period_totals"]["groups_changed"], 2)
        # sequence ids shift for every row after the insertion: counted, never summed
        order_id = columns["market/market.sqlite::orders.order_id"]
        self.assertTrue(order_id["identifier"])
        self.assertEqual(order_id["changed_values"], 4)  # battery and wind moved from :1/:2 to :2/:3
        self.assertNotIn("sum_before", order_id)
        self.assertNotIn("max_abs_delta", order_id)
        self.assertNotIn("annual_totals", columns["market/market.sqlite::orders.period"])
        self.assertNotIn("sum_before", columns["market/market.sqlite::orders.period"])
        rows = columns["market/market.sqlite::orders.#rows"]
        self.assertEqual((rows["rows_before"], rows["rows_after"]), (6, 8))
        self.assertNotIn("sum_before", rows)
        # a table without a natural key cannot be aligned after an insertion
        energy = columns["market/market.sqlite::event_log.energy_mwh"]
        self.assertEqual(energy["alignment"], "not comparable (rows shifted)")
        self.assertEqual(energy["per_value"], "not comparable (rows shifted)")
        self.assertFalse(energy["comparable"])
        self.assertNotIn("max_abs_delta", energy)
        self.assertNotIn("changed_values", energy)
        self.assertEqual((energy["sum_before"], energy["sum_after"]), (12.0, 20.0))
        self.assertNotIn("sum_before", columns["market/market.sqlite::event_log.sequence"])
        self.assertGreaterEqual(report["summary"]["not_comparable_columns"], 3)

    def test_numeric_report_marks_shifted_json_lists_not_comparable(self) -> None:
        def run(name: str, rows: list) -> Path:
            root = self.root / name
            root.mkdir()
            (root / "investment.json").write_text(json.dumps({"proposals": rows}), encoding="utf-8")
            return root

        before = run("json-before", [{"asset_id": "a", "capacity_mw": 10.0}, {"asset_id": "b", "capacity_mw": 20.0}])
        after = run("json-after", [{"asset_id": "n", "capacity_mw": 5.0}, {"asset_id": "a", "capacity_mw": 10.0},
                                   {"asset_id": "b", "capacity_mw": 20.0}])
        report = golden.build_numeric_report(before, after, golden.ZoneRules(()), family="doctoral", case="X1",
                                             revision=1, parent_commit="c", child_commit="d")
        capacity = report["columns"]["investment.json::proposals.capacity_mw"]
        self.assertEqual(capacity["per_value"], "not comparable (rows shifted)")
        self.assertEqual((capacity["sum_before"], capacity["sum_after"]), (30.0, 35.0))
        self.assertTrue(report["columns"]["investment.json::proposals.asset_id"]["identifier"])

    def test_capture_validate_reads_reports_and_refuses_orphans(self) -> None:
        import contextlib
        import importlib.util
        import io
        from unittest import mock

        spec = importlib.util.spec_from_file_location("golden_capture_reports", ROOT / "scripts" / "golden" / "capture.py")
        capture = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(capture)
        self.assertEqual(capture.validate_all(), [])
        reports = self.root / "reports"
        reports.mkdir()
        (reports / "D1-r1.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(capture, "REPORT_DIR", reports):
            self.assertTrue(any("D1-r1.json" in error for error in capture.validate_all()))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            capture.main(["numeric-report", "--case", "D1"])  # D1 has only revision 0

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

    def test_zone_relabel_cannot_unfreeze_a_doctoral_trajectory_column(self) -> None:
        """Relabelling via zones.json and changing the price under an accounting id is refused."""

        allowlist = {"findings": {"P6-24": "approved"}}
        price = "market/market.sqlite::period_summary.clearing_price_gbp_per_mwh"
        relabel = golden.ZoneRules(((price.replace("clearing", "*clearing"), "accounting"),) + ZONES.rules)
        record = self._golden("doctoral")
        moved = golden.digest_run(_write_run(self.root / "moved", price=50.0), relabel)
        self.assertEqual(moved["columns"][price]["zone"], "accounting")
        golden.append_revision(record, moved, base_commit="d", reason="relabel", correction_ids=["p04.ledger"])
        self.assertEqual(record["revisions"][1]["delta"]["by_zone"], {"trajectory": 1})
        errors = golden.validate_golden_file(record, allowlist)
        self.assertTrue(any("weaker zone" in error for error in errors), errors)
        self.assertTrue(any("trajectory column" in error for error in errors), errors)
        # the same relabel without any value change is still refused
        unchanged = golden.digest_run(_write_run(self.root / "same", residual=0.5), relabel)
        quiet = self._golden("doctoral")
        golden.append_revision(quiet, unchanged, base_commit="d", reason="relabel", correction_ids=["p04.ledger"])
        self.assertTrue(any("weaker zone" in error for error in golden.validate_golden_file(quiet, allowlist)))
        # a hand-written delta that books the change under accounting is caught too
        forged = copy.deepcopy(record)
        for row in forged["revisions"][1]["delta"]["differences"]:
            row["zone"] = "accounting"
        self.assertTrue(any("pinned" in error for error in golden.validate_golden_file(forged, allowlist)))
        # making a column stricter is allowed
        stricter = golden.ZoneRules((("market/market.sqlite::period_summary.energy_balance_residual_mwh", "trajectory"),))
        tightened = self._golden("corrected")
        golden.append_revision(
            tightened,
            golden.digest_run(_write_run(self.root / "tight", residual=0.5), stricter),
            base_commit="d", reason="x", correction_ids=["a.b"],
        )
        self.assertEqual(golden.validate_golden_file(tightened, allowlist), [])

    def test_relabel_on_the_committed_d1_golden_is_refused(self) -> None:
        record = json.loads((ROOT / "tests" / "golden" / "doctoral" / "D1.json").read_text(encoding="utf-8"))
        price = "market/market.sqlite::period_summary.clearing_price_gbp_per_mwh"
        self.assertEqual(record["revisions"][0]["digest"]["columns"][price]["zone"], "trajectory")
        digest = copy.deepcopy(golden.latest_digest(record))
        digest["columns"][price]["zone"] = "accounting"
        digest["columns"][price]["sha256"] = "0" * golden.HASH_CHARS
        golden.append_revision(record, digest, base_commit="x", reason="relabel", correction_ids=["p04.ledger"])
        allowlist = json.loads((ROOT / "tests" / "golden" / "doctoral_trajectory_rebaselines.json").read_text(encoding="utf-8"))
        errors = golden.validate_golden_file(record, allowlist)
        self.assertTrue(any("weaker zone" in error for error in errors), errors)
        self.assertTrue(any("without an approved universal finding" in error for error in errors), errors)

    def test_doctoral_trajectory_exceptions_are_exactly_the_approved_decisions(self) -> None:
        """Only the author-approved universal corrections may move doctoral trajectory.

        P0_DECISIONS: Q9/A3 (P6-24 interconnector clock), A5 (P6-02/03/04 GBP1
        reading), A4 (thermal net revenue).  Adding a finding here also needs
        an integrator move of p0_gate.APPEND_ONLY_BASE (append_only refuses it).
        """

        allowlist = json.loads((ROOT / "tests" / "golden" / "doctoral_trajectory_rebaselines.json").read_text(encoding="utf-8"))
        self.assertEqual(set(allowlist["findings"]), {"P6-24", "P6-02", "P6-03", "P6-04", "P4-01-thermal"})
        for finding, decision in (("P6-24", "A3"), ("P6-02", "A5"), ("P6-03", "A5"), ("P6-04", "A5"), ("P4-01-thermal", "A4")):
            self.assertIn(decision, allowlist["findings"][finding])

    def test_cited_decisions_exist_in_the_construction_record(self) -> None:
        # docs/dev/ is excluded from the public source release
        # (tests/baselines/release-exclusions.txt); the cross-check runs only
        # in a construction checkout.
        decisions_path = ROOT / "docs" / "dev" / "P0_DECISIONS.md"
        if not decisions_path.is_file():
            self.skipTest("docs/dev/P0_DECISIONS.md is not part of this tree (public source release)")
        decisions = decisions_path.read_text(encoding="utf-8")
        for decision in ("| Q9 |", "| A3 |", "| A4 |", "| A5 |"):
            self.assertIn(decision, decisions)

    def test_pinned_zones_follow_first_record_and_only_tighten(self) -> None:
        def revision(zone: str) -> dict:
            return {"digest": {"columns": {"t::c": {"zone": zone}}}}

        record = {"revisions": [revision("accounting"), revision("trajectory"), revision("identity")]}
        self.assertEqual(golden.pinned_zones(record, 1), {"t::c": "accounting"})
        self.assertEqual(golden.pinned_zones(record), {"t::c": "trajectory"})
        self.assertEqual(
            golden.zone_weakenings(golden.pinned_zones(record, 2), record["revisions"][2]["digest"]),
            [("t::c", "trajectory", "identity")],
        )


class GoldenInitTests(unittest.TestCase):
    def setUp(self) -> None:
        import contextlib
        import importlib.util
        import io

        spec = importlib.util.spec_from_file_location("golden_capture_init", ROOT / "scripts" / "golden" / "capture.py")
        self.capture = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.capture)
        self._quiet = contextlib.redirect_stderr(io.StringIO())

    def test_revision_zero_cannot_be_rewritten(self) -> None:
        from unittest import mock

        with mock.patch.object(self.capture, "run_cases", side_effect=AssertionError("must not run")):
            with self._quiet, self.assertRaises(SystemExit) as raised:
                self.capture.main(["init", "--cases", "D1", "--force-reinit"])
            self.assertEqual(raised.exception.code, 2)  # the flag no longer exists
            with self.assertRaises(SystemExit) as raised:
                self.capture.main(["init", "--cases", "D1"])
            self.assertIn("immutable", str(raised.exception.code))


PRICE = "market/market.sqlite::period_summary.clearing_price_gbp_per_mwh"
RESIDUAL = "market/market.sqlite::period_summary.energy_balance_residual_mwh"


class GoldenReviseWorkflowTests(unittest.TestCase):
    """``capture.py revise`` -> ``numeric-report`` -> ``validate`` through
    ``capture.main`` (model runs mocked), on a scratch copy of the golden files."""

    def setUp(self) -> None:
        import contextlib
        import importlib.util
        import io
        import shutil
        from unittest import mock

        spec = importlib.util.spec_from_file_location("golden_capture_revise", ROOT / "scripts" / "golden" / "capture.py")
        self.capture = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.capture)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.golden_dir = Path(temporary.name) / "golden"
        for family in ("doctoral", "corrected"):
            shutil.copytree(ROOT / "tests" / "golden" / family, self.golden_dir / family)
        self.reports = self.golden_dir / "reports"
        for name, value in (("GOLDEN_DIR", self.golden_dir), ("REPORT_DIR", self.reports)):
            patcher = mock.patch.object(self.capture, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.assertEqual(self.capture.validate_all(), [])
        self._stdout = io.StringIO
        self._redirect = contextlib.redirect_stdout

    def _record(self, family: str, case: str) -> dict:
        return json.loads((self.golden_dir / family / f"{case}.json").read_text(encoding="utf-8"))

    def _changed(self, family: str, case: str, key: str) -> dict:
        digest = copy.deepcopy(dict(golden.latest_digest(self._record(family, case))))
        digest["columns"][key] = dict(digest["columns"][key], sha256="1" * golden.HASH_CHARS, sha256_9g="1" * golden.HASH_CHARS)
        return {**digest, "case": case, "seconds": 1.5}

    def _revise(self, case: str, digest: dict, *arguments: str) -> tuple[int, str]:
        from unittest import mock

        output = self._stdout()
        with mock.patch.object(self.capture, "run_cases", return_value={case: digest}), self._redirect(output):
            code = self.capture.main(["revise", "--cases", case, "--reason", "test re-baseline", *arguments])
        return code, output.getvalue()

    def _report_for(self, family: str, case: str, index: int, keys: set[str]) -> dict:
        record = self._record(family, case)
        return {
            "schema_version": golden.NUMERIC_REPORT_SCHEMA, "family": family, "case": case, "revision": index,
            "parent_commit": "p", "child_commit": "c",
            "digest_sha256": golden.digest_fingerprint(record["revisions"][index]["digest"]),
            "summary": {}, "columns": {key: {"zone": "trajectory"} for key in keys},
        }

    def _write_report(self, name: str, payload: object) -> None:
        self.reports.mkdir(exist_ok=True)
        (self.reports / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_doctoral_trajectory_revise_then_report_then_validate(self) -> None:
        # The committed D3 may already carry accounting-only revisions (e.g.
        # p04.validation-v2); the new revision is the next index k.
        k = len(self._record("doctoral", "D3")["revisions"])
        code, output = self._revise("D3", self._changed("doctoral", "D3", PRICE),
                                    "--correction-id", "p05.ic", "--finding", "P6-24")
        self.assertEqual(code, 0, output)
        record = self._record("doctoral", "D3")
        self.assertEqual(len(record["revisions"]), k + 1)
        self.assertEqual(record["revisions"][k]["delta"]["by_zone"], {"trajectory": 1})
        self.assertIn("numeric-report --case D3", output)
        # the revision is written; the commit is refused until its report exists
        errors = self.capture.validate_all()
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(f"doctoral/D3: revision {k} changes doctoral trajectory without a numeric before/after report", errors[0])
        report = f"D3-r{k}.json"
        self._write_report(report, self._report_for("doctoral", "D3", k, {PRICE}))
        self.assertEqual(self.capture.validate_all(), [])
        # a forged report is validated, not just checked for existence
        self._write_report(report, dict(self._report_for("doctoral", "D3", k, {PRICE}), digest_sha256="0" * 64))
        self.assertTrue(any("digest_sha256" in error for error in self.capture.validate_all()))
        self._write_report(report, [])
        self.assertTrue(any(report in error for error in self.capture.validate_all()))
        self._write_report(report, self._report_for("doctoral", "D3", k, {PRICE}))

        # the next revise checks the committed report of r(k) and leaves r(k+1) pending
        code, output = self._revise("D3", self._changed("doctoral", "D3", "market/market.sqlite::period_summary.accepted_supply_mwh"),
                                    "--correction-id", "p05.gbp1", "--finding", "P6-02")
        self.assertEqual(code, 0, output)
        self.assertTrue(any(f"revision {k + 1}" in error and "numeric before/after report" in error
                            for error in self.capture.validate_all()))

    def test_revise_still_refuses_an_unapproved_doctoral_trajectory_change(self) -> None:
        before = (self.golden_dir / "doctoral" / "D3.json").read_text(encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            self._revise("D3", self._changed("doctoral", "D3", PRICE), "--correction-id", "p06.bid")
        self.assertIn("without an approved universal finding", str(raised.exception.code))
        self.assertEqual((self.golden_dir / "doctoral" / "D3.json").read_text(encoding="utf-8"), before)

    def test_reports_only_document_doctoral_trajectory_revisions(self) -> None:
        c = len(self._record("corrected", "C3")["revisions"])
        d = len(self._record("doctoral", "D3")["revisions"])
        code, _ = self._revise("C3", self._changed("corrected", "C3", PRICE), "--correction-id", "p06.bid")
        self.assertEqual(code, 0)
        code, _ = self._revise("D3", self._changed("doctoral", "D3", RESIDUAL), "--correction-id", "p04.ledger")
        self.assertEqual(code, 0)
        self.assertEqual(self.capture.validate_all(), [])  # neither revision needs a report
        corrected_report, doctoral_report = f"C3-r{c}.json", f"D3-r{d}.json"
        self._write_report(corrected_report, self._report_for("corrected", "C3", c, {PRICE}))
        self._write_report(doctoral_report, self._report_for("doctoral", "D3", d, {RESIDUAL}))
        errors = self.capture.validate_all()
        for name in (corrected_report, doctoral_report):
            self.assertTrue(any(name in error and "changes no doctoral trajectory" in error for error in errors), errors)
        (self.reports / corrected_report).unlink()
        (self.reports / doctoral_report).unlink()
        for name in (f"D3-r{d + 1}.json", "D3-r01.json", "D9-r1.json", "notes.txt"):
            with self.subTest(report=name):
                self._write_report(name, {})
                self.assertTrue(any(name in error for error in self.capture.validate_all()))
                (self.reports / name).unlink()
        self.assertEqual(self.capture.validate_all(), [])


class GoldenProjectSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("golden_run_case_test", ROOT / "scripts" / "golden" / "run_case.py")
        self.run_case = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.run_case)
        self.cases = self.run_case.load_cases()

    def test_cases_run_from_frozen_projects_not_the_live_template(self) -> None:
        from unittest import mock

        import gridform_core.value_101 as template
        import gridform_core.value_101_lifecycle as lifecycle

        with mock.patch.object(template, "value_101_study", side_effect=AssertionError("live template used")), \
                mock.patch.object(lifecycle, "build_value_101_network_pair", side_effect=AssertionError("live template used")):
            for case_id, case in self.cases.items():
                with self.subTest(case=case_id):
                    project = self.run_case.build_project(dict(case, id=case_id))
                    frozen = json.loads(self.run_case.project_path(dict(case, id=case_id)).read_text(encoding="utf-8"))
                    # The one intended override (P0_CONVENTIONS section 2, X0
                    # S8): every doctoral case is pinned to the frozen profile,
                    # which the 35aadb3 snapshots predate, and corrected cases
                    # run under the default.  The two documented run-time
                    # re-derivations (registered maturity keys; current
                    # built-in solver contract) are covered by their own tests
                    # below.  Nothing else may differ.
                    pinned = dict(project.get("parameters") or {}).pop("methodology.profile", None)
                    if case["family"] == "doctoral":
                        from gridform_core.methodology import REFERENCE_PROFILE_ID

                        self.assertEqual(pinned, REFERENCE_PROFILE_ID)
                        project = dict(project, parameters={
                            key: value for key, value in project["parameters"].items() if key != "methodology.profile"
                        })
                    else:
                        self.assertIsNone(pinned)
                    rederived = ("maturity_acknowledgements", "solver_contract")
                    self.assertEqual(
                        {key: value for key, value in project.items() if key not in rederived},
                        {key: value for key, value in frozen.items() if key not in rederived},
                        "overrides in cases.json must be no-ops on the frozen project",
                    )
                    self.assertEqual(project["id"], "golden-study")

    def test_frozen_projects_carry_the_case_configuration(self) -> None:
        for case_id, case in self.cases.items():
            with self.subTest(case=case_id):
                project = self.run_case.build_project(dict(case, id=case_id))
                for section in ("modules", "parameters", "runtime_options"):
                    for key, value in (case.get(section) or {}).items():
                        self.assertEqual(project[section][key], value)
                if case["family"] == "doctoral":
                    self.assertEqual(project["modules"]["storage_cost"], "value-legacy-storage-tariff")
                    self.assertEqual(project["parameters"]["carbon.factor_scenario"], "doctoral_reproduction_2026_07_18")

    def test_golden_projects_survive_a_module_version_bump(self) -> None:
        """P0-8 bumped value-zonal-redispatch-balancing 3.0.0 -> 4.0.0 (VERSION_LEDGER);
        C8's immutable snapshot acknowledges @3.0.0 and must still validate.
        A further simulated bump (5.0.0) must also be absorbed."""

        import dataclasses

        from gridform_core.frontend_contract import validate_maturity_acknowledgements
        from gridform_core.v2.module_manifest import builtin_registry

        registry = builtin_registry()
        module_id = "value-zonal-redispatch-balancing"
        current = registry.manifest(module_id)
        self.assertEqual(current.version, "4.0.0")
        case = dict(self.cases["C8"], id="C8")
        frozen = json.loads(self.run_case.project_path(case).read_text(encoding="utf-8"))
        self.assertIn(f"module:{module_id}@3.0.0", frozen["maturity_acknowledgements"])
        with self.assertRaisesRegex(ValueError, "Experimental acknowledgement required"):
            validate_maturity_acknowledgements(registry, frozen["modules"], frozen["selected_extensions"],
                                               frozen["maturity_acknowledgements"])
        project = self.run_case.build_project(case, registry)
        self.assertIn(f"module:{module_id}@4.0.0", project["maturity_acknowledgements"])
        self.assertNotIn(f"module:{module_id}@3.0.0", project["maturity_acknowledgements"])
        validate_maturity_acknowledgements(registry, project["modules"], project["selected_extensions"],
                                           project["maturity_acknowledgements"])
        registry._manifests[module_id] = dataclasses.replace(current, version="5.0.0")
        project = self.run_case.build_project(case, registry)
        self.assertIn(f"module:{module_id}@5.0.0", project["maturity_acknowledgements"])
        validate_maturity_acknowledgements(registry, project["modules"], project["selected_extensions"],
                                           project["maturity_acknowledgements"])
        for case_id, definition in self.cases.items():
            with self.subTest(case=case_id):
                built = self.run_case.build_project(dict(definition, id=case_id), registry)
                validate_maturity_acknowledgements(registry, built["modules"], built.get("selected_extensions") or [],
                                                   built["maturity_acknowledgements"])

    def test_frozen_builtin_solver_contract_runs_as_the_current_default(self) -> None:
        """C8 froze the v3 built-in default; it runs as the v4 built-in default.
        A custom (non-default) historical contract is never rewritten."""

        from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS

        case = dict(self.cases["C8"], id="C8")
        frozen = json.loads(self.run_case.project_path(case).read_text(encoding="utf-8"))
        self.assertEqual(frozen["solver_contract"]["schema_version"], "value.network-solver-contract/v3")
        project = self.run_case.build_project(case)
        self.assertEqual(project["solver_contract"], DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        custom = dict(frozen["solver_contract"], is_builtin_default=False, requires_acknowledgement=True)
        self.assertEqual(self.run_case.derived_solver_contract({"solver_contract": custom}), custom)

    def test_freeze_projects_never_overwrites(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("golden_capture_freeze", ROOT / "scripts" / "golden" / "capture.py")
        capture = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(capture)
        with self.assertRaises(SystemExit) as raised:
            capture.main(["freeze-projects", "--cases", "D1"])
        self.assertIn("immutable", str(raised.exception.code))


if __name__ == "__main__":
    unittest.main()
