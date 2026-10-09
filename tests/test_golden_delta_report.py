"""Golden delta report (plan X0 S13): revision-0 and dual-profile deltas,
attribution of every row to a correction id, committed report up to date."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from gridform_validation import golden

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location("golden_delta_report", ROOT / "scripts" / "golden" / "delta_report.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


delta_report = _load_script()


def _digest(columns: dict[str, tuple[str, str]]) -> dict:
    return {
        "schema_version": golden.SCHEMA_VERSION,
        "platform": {},
        "columns": {
            key: {"zone": zone, "count": 1, "sha256": value, "sha256_9g": value} for key, (zone, value) in columns.items()
        },
    }


BASE = {
    "market/market.sqlite::period_summary.clearing_price_gbp_per_mwh": ("trajectory", "p0"),
    "market/market.sqlite::period_summary.energy_balance_residual_mwh": ("accounting", "r0"),
    "year-results-v2.json::market.module_version": ("identity", "v0"),
}
PRICE = "market/market.sqlite::period_summary.clearing_price_gbp_per_mwh"
RESIDUAL = "market/market.sqlite::period_summary.energy_balance_residual_mwh"
VERSION = "year-results-v2.json::market.module_version"


def _changed(base: dict, **values: str) -> dict:
    columns = dict(base)
    mapping = {"price": PRICE, "residual": RESIDUAL, "version": VERSION}
    for name, value in values.items():
        key = mapping[name]
        columns[key] = (columns[key][0], value)
    return columns


class RevisionZeroDeltaTests(unittest.TestCase):
    def test_only_revision_zero_gives_an_empty_delta(self) -> None:
        case = golden.new_golden("corrected", "C9", _digest(BASE), "35aadb3", "M0 capture")
        self.assertEqual(delta_report.revision_zero_delta(case), [])
        twin = golden.new_golden("doctoral", "D9", _digest(BASE), "35aadb3", "M0 capture")
        self.assertEqual(delta_report.dual_profile_delta(twin, case), [])

    def test_every_changed_column_carries_the_ids_of_the_revisions_that_changed_it(self) -> None:
        case = golden.new_golden("corrected", "C9", _digest(BASE), "35aadb3", "M0 capture")
        first = _changed(BASE, residual="r1", version="v1")
        golden.append_revision(case, _digest(first), base_commit="a", reason="ledger", correction_ids=["p04.example-ledger"])
        second = _changed(first, residual="r2", price="p2")
        golden.append_revision(case, _digest(second), base_commit="b", reason="clearing", correction_ids=["p06.example-clearing"])
        rows = {row.key: row for row in delta_report.revision_zero_delta(case)}
        self.assertEqual(set(rows), {PRICE, RESIDUAL, VERSION})
        self.assertEqual(rows[PRICE].correction_ids, ["p06.example-clearing"])
        self.assertEqual(rows[RESIDUAL].correction_ids, ["p04.example-ledger", "p06.example-clearing"])
        self.assertEqual(rows[RESIDUAL].revisions, {"self": [1, 2]})
        self.assertEqual(rows[VERSION].zone, "identity")
        self.assertTrue(all(row.unattributed_reason is None for row in rows.values()))
        summary = delta_report._summarise(rows.values())
        self.assertEqual(summary["by_zone"], {"trajectory": 1, "accounting": 1, "identity": 1})
        self.assertEqual(summary["by_correction"]["p06.example-clearing"], {"trajectory": 1, "accounting": 1, "identity": 0})

    def test_a_column_changed_and_changed_back_is_not_a_row(self) -> None:
        case = golden.new_golden("corrected", "C9", _digest(BASE), "35aadb3", "M0 capture")
        golden.append_revision(case, _digest(_changed(BASE, price="p1")), base_commit="a", reason="x", correction_ids=["p06.a"])
        golden.append_revision(case, _digest(BASE), base_commit="b", reason="y", correction_ids=["p06.b"])
        self.assertEqual(delta_report.revision_zero_delta(case), [])

    def test_a_revision_without_a_correction_id_leaves_its_rows_unattributed(self) -> None:
        case = golden.new_golden("corrected", "C9", _digest(BASE), "35aadb3", "M0 capture")
        golden.append_revision(case, _digest(_changed(BASE, residual="r1")), base_commit="a", reason="x", correction_ids=[], findings=["P7-01"])
        rows = delta_report.revision_zero_delta(case)
        self.assertEqual(len(rows), 1)
        self.assertIn("no correction id", rows[0].unattributed_reason)

    def test_a_column_no_revision_recorded_is_unattributed(self) -> None:
        case = golden.new_golden("corrected", "C9", _digest(BASE), "35aadb3", "M0 capture")
        golden.append_revision(case, _digest(_changed(BASE, residual="r1")), base_commit="a", reason="x", correction_ids=["p04.a"])
        case["revisions"][1]["delta"]["differences"] = []  # a tampered revision record
        rows = delta_report.revision_zero_delta(case)
        self.assertEqual(rows[0].unattributed_reason, "no revision recorded a change of this column")
        report = {
            "cases": {"C9": {"rows": [row.to_dict() for row in rows]}},
            "profile_pairs": [],
            "unknown_correction_ids": [],
        }
        self.assertEqual(len(delta_report.attribution_errors(report)), 1)


class DualProfileDeltaTests(unittest.TestCase):
    def test_rows_are_attributed_to_the_configuration_and_to_each_side(self) -> None:
        doctoral_base = _changed(BASE, residual="r-doctoral")  # differs at revision 0 (Q3 configuration)
        doctoral = golden.new_golden("doctoral", "D9", _digest(doctoral_base), "35aadb3", "M0")
        corrected = golden.new_golden("corrected", "C9", _digest(BASE), "35aadb3", "M0")
        golden.append_revision(corrected, _digest(_changed(BASE, price="p1")), base_commit="a", reason="gated", correction_ids=["p06.gated"])
        golden.append_revision(
            doctoral, _digest(_changed(doctoral_base, version="v1")), base_commit="b", reason="universal", correction_ids=["p04.universal"]
        )
        rows = {row.key: row for row in delta_report.dual_profile_delta(doctoral, corrected)}
        self.assertEqual(rows[RESIDUAL].correction_ids, [delta_report.REFERENCE_CONFIGURATION_ID])
        self.assertEqual(rows[PRICE].correction_ids, ["p06.gated"])
        self.assertEqual(rows[PRICE].revisions, {"corrected": [1]})
        self.assertEqual(rows[VERSION].correction_ids, ["p04.universal"])
        self.assertTrue(all(row.unattributed_reason is None for row in rows.values()))

    def test_a_universal_correction_applied_to_both_sides_leaves_no_row(self) -> None:
        doctoral = golden.new_golden("doctoral", "D9", _digest(BASE), "35aadb3", "M0")
        corrected = golden.new_golden("corrected", "C9", _digest(BASE), "35aadb3", "M0")
        for case in (doctoral, corrected):
            golden.append_revision(case, _digest(_changed(BASE, residual="r1")), base_commit="a", reason="u", correction_ids=["p04.universal"])
        self.assertEqual(delta_report.dual_profile_delta(doctoral, corrected), [])

    def test_pairs_use_the_same_pack_and_mode_and_the_closest_configuration(self) -> None:
        cases = delta_report.load_cases(ROOT)
        pairs = dict(delta_report.profile_pairs(cases))
        self.assertEqual(pairs, {"D1": "C4", "D2": "C2", "D3": "C3", "D4": "C5"})
        difference = delta_report.configuration_difference(cases["D1"], cases["C4"])
        self.assertEqual(set(difference), {"parameters"})
        self.assertEqual(set(difference["parameters"]), {"carbon.factor_scenario", "methodology.profile"})


class RepositoryReportTests(unittest.TestCase):
    """The committed golden files: every row attributed, report up to date."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = delta_report.build_report(ROOT)

    def test_every_row_maps_to_a_correction_id(self) -> None:
        self.assertEqual(delta_report.attribution_errors(self.report), [])
        self.assertEqual(self.report["unattributed_rows"], 0)
        self.assertEqual(self.report["missing_golden_files"], [])

    def test_doctoral_trajectory_changes_only_under_approved_findings(self) -> None:
        allowlist = json.loads((ROOT / "tests" / "golden" / "doctoral_trajectory_rebaselines.json").read_text(encoding="utf-8"))
        approved = set(allowlist["findings"])
        for case_id, case in self.report["cases"].items():
            if case["family"] != "doctoral" or not case["summary"]["by_zone"]["trajectory"]:
                continue
            payload = json.loads((ROOT / "tests" / "golden" / "doctoral" / f"{case_id}.json").read_text(encoding="utf-8"))
            trajectory_revisions = {
                revision
                for row in case["rows"]
                if row["zone"] == "trajectory"
                for revision in row["revisions"].get("self", [])
            }
            for index in trajectory_revisions:
                findings = set(payload["revisions"][index].get("findings") or [])
                self.assertTrue(findings & approved, f"{case_id} r{index}")
                self.assertTrue((ROOT / "tests" / "golden" / "reports" / f"{case_id}-r{index}.json").is_file())

    def test_committed_report_is_up_to_date(self) -> None:
        committed = (ROOT / delta_report.REPORT_PATH).read_text(encoding="utf-8")
        self.assertEqual(
            committed,
            delta_report.render_markdown(self.report),
            "run scripts/golden/delta_report.py --write after revising a golden file",
        )

    def test_json_output_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "delta.json"
            self.assertEqual(delta_report.main(["--json", str(target)]), 0)
            payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], delta_report.SCHEMA_VERSION)
        for case in payload["cases"].values():
            self.assertEqual(len(case["rows"]), case["summary"]["count"])
        self.assertEqual(payload["unattributed_rows"], 0)


if __name__ == "__main__":
    unittest.main()
