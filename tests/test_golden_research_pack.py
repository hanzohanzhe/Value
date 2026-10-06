"""The GBP1 doctoral golden case D5 (decision A12) and its research-pack plumbing.

D5 runs the released GBP1 public1 pack, which is not in the repository:
``scripts/golden/run_case.py`` takes it from ``VALUE_P0_5_PACKS`` and only
when the manifest sha256 is the pinned one; without it ``capture.py check``
reports D5 as unavailable (or fails under
``VALUE_GOLDEN_REQUIRE_RESEARCH_PACKS=1``).  The model run itself is the
golden_full gate step (about six minutes); the tests here need no model run.
GBP1-input checks run only when ``VALUE_P0_5_PACKS`` supplies the pack.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
COMMIT_35AADB3 = "35aadb34a526f3093a221bb460bdebef3d6767bf"
A3_A5_A4 = ["P4-01-thermal", "P6-02", "P6-03", "P6-04", "P6-24"]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RUN_CASE = _load("golden_run_case_rp", ROOT / "scripts" / "golden" / "run_case.py")
CAPTURE = _load("golden_capture_rp", ROOT / "scripts" / "golden" / "capture.py")
BASELINE = _load("capture_p0_5_baseline_rp", ROOT / "scripts" / "capture_p0_5_baseline.py")
COMPARE = _load("gbp1_doctoral_before_after", ROOT / "scripts" / "gbp1_doctoral_before_after.py")


def _gbp1_root() -> Path | None:
    case = dict(CAPTURE.load_cases()["D5"], id="D5")
    try:
        return RUN_CASE.resolve_pack_root(case)
    except RUN_CASE.ResearchPackUnavailable:
        return None


class ResearchPackResolutionTests(unittest.TestCase):
    def test_repository_pack_is_a_path_below_the_repository(self):
        case = dict(CAPTURE.load_cases()["D1"], id="D1")
        self.assertEqual(RUN_CASE.resolve_pack_root(case), (ROOT / "data-packs" / "value-101-baseline-v1").resolve())

    def test_only_the_pinned_manifest_is_accepted(self):
        with tempfile.TemporaryDirectory() as scratch:
            wrong, right = Path(scratch) / "wrong", Path(scratch) / "right"
            for directory, text in ((wrong, '{"id": "x", "revision": 2}'), (right, '{"id": "x", "revision": 1}')):
                directory.mkdir()
                (directory / "manifest.json").write_text(text, encoding="utf-8")
            pinned = hashlib.sha256((right / "manifest.json").read_bytes()).hexdigest()
            case = {"id": "T", "research_pack": {"label": "toy", "manifest_sha256": pinned}}
            with mock.patch.dict(os.environ, {"VALUE_P0_5_PACKS": str(wrong)}):
                with self.assertRaises(RUN_CASE.ResearchPackUnavailable):
                    RUN_CASE.resolve_pack_root(case)
            with mock.patch.dict(os.environ, {"VALUE_P0_5_PACKS": os.pathsep.join([str(wrong), str(right)])}):
                self.assertEqual(RUN_CASE.resolve_pack_root(case), right.resolve())
            with mock.patch.dict(os.environ, {"VALUE_P0_5_PACKS": ""}):
                with self.assertRaises(RUN_CASE.ResearchPackUnavailable):
                    RUN_CASE.resolve_pack_root(case)

    def test_check_lists_a_missing_research_pack_as_unavailable(self):
        with tempfile.TemporaryDirectory() as scratch:
            report_path = Path(scratch) / "check.json"
            environment = {"VALUE_P0_5_PACKS": "", "VALUE_GOLDEN_REQUIRE_RESEARCH_PACKS": "0"}
            with mock.patch.dict(os.environ, environment), mock.patch("builtins.print"):
                code = CAPTURE.main(["check", "--cases", "D5", "--json-output", str(report_path)])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertTrue(report["passed"])
            self.assertIn("D5", report["unavailable"])
            self.assertIn("gbp1-public1", report["unavailable"]["D5"])
            environment["VALUE_GOLDEN_REQUIRE_RESEARCH_PACKS"] = "1"
            with mock.patch.dict(os.environ, environment), mock.patch("builtins.print"):
                code = CAPTURE.main(["check", "--cases", "D5", "--json-output", str(report_path)])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertFalse(report["passed"])

    def test_from_output_digests_exactly_one_case(self):
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaises(SystemExit) as raised:
                CAPTURE.main(["revise", "--cases", "D1", "D2", "--reason", "x", "--correction-id", "x.y",
                              "--from-output", scratch])
            self.assertIn("exactly one case", str(raised.exception))
            with self.assertRaises(SystemExit) as raised:
                CAPTURE.main(["init", "--cases", "D1", "--from-output", scratch])
            self.assertIn("immutable", str(raised.exception))


class D5DefinitionTests(unittest.TestCase):
    def setUp(self):
        self.cases = CAPTURE.load_cases()
        self.case = self.cases["D5"]
        self.project = json.loads((GOLDEN / "projects" / "D5.json").read_text(encoding="utf-8"))
        self.golden = json.loads((GOLDEN / "doctoral" / "D5.json").read_text(encoding="utf-8"))

    def test_case_pins_the_released_gbp1_public1_manifest(self):
        self.assertEqual(self.case["family"], "doctoral")
        self.assertEqual(self.case["mode"], "full")
        self.assertNotIn("pack", self.case)
        released = BASELINE.RESEARCH_PACKS["gbp1-public1"]
        self.assertEqual(self.case["research_pack"], {"label": "gbp1-public1", "manifest_sha256": released["manifest_sha256"]})
        self.assertEqual(self.project["data_pack_id"], released["pack_id"])

    def test_project_is_the_doctoral_reference_configuration_for_one_year(self):
        d4 = json.loads((GOLDEN / "projects" / "D4.json").read_text(encoding="utf-8"))
        self.assertEqual(self.project["modules"], d4["modules"])
        self.assertEqual((self.project["start_year"], self.project["end_year"]), (2025, 2025))
        self.assertEqual(self.case["parameters"]["methodology.profile"], "doctoral-lineage-0.6.0a2")
        self.assertEqual(self.case["parameters"]["carbon.factor_scenario"], "doctoral_reproduction_2026_07_18")
        self.assertEqual(self.case["modules"], {"storage_cost": "value-legacy-storage-tariff"})
        # 35aadb3 had no methodology.profile parameter: revision 0 ran the frozen project as is.
        self.assertNotIn("methodology.profile", self.project["parameters"])

    def test_revision_0_is_35aadb3_and_revision_1_uses_the_universal_allowlist(self):
        revisions = self.golden["revisions"]
        self.assertEqual(revisions[0]["base_commit"], COMMIT_35AADB3)
        self.assertGreaterEqual(len(revisions), 2)
        # Later revisions are accounting/identity only (e.g. FX5 fx5.voll-17000):
        # the trajectory rebaseline of D5 happens once, in revision 1.
        for later in revisions[2:]:
            self.assertEqual(later["delta"]["by_zone"].get("trajectory", 0), 0, later["revision"])
        allowlist = json.loads((GOLDEN / "doctoral_trajectory_rebaselines.json").read_text(encoding="utf-8"))["findings"]
        trajectory_findings = sorted(set(revisions[1]["findings"]) & set(allowlist))
        self.assertEqual(trajectory_findings, A3_A5_A4)
        self.assertGreater(revisions[1]["delta"]["by_zone"]["trajectory"], 0)
        report = json.loads((GOLDEN / "reports" / "D5-r1.json").read_text(encoding="utf-8"))
        self.assertEqual(report["parent_commit"], COMMIT_35AADB3)
        self.assertEqual(report["revision"], 1)

    def test_bookkeeping_of_d5_is_valid(self):
        errors = [error for error in CAPTURE.validate_all() if "D5" in error]
        self.assertEqual(errors, [])


class BoundaryInputTests(unittest.TestCase):
    def test_head_feeds_match_the_p0_5_baseline_record(self):
        self.assertEqual(COMPARE.HEAD_CONNECTION_FEEDS, BASELINE.HEAD_KERNEL_CONNECTION_FEEDS)

    def test_stretched_clock_serves_each_row_twice(self):
        flow = [10.0, -20.0, 30.0, -40.0]
        price = [1.0, 2.0, 3.0, 4.0]
        stretched = COMPARE._feed_stats(flow, price, 4, "stretched")
        period = COMPARE._feed_stats(flow, price, 4, "period")
        self.assertEqual(stretched["import_limit_mwh"], 10.0)   # rows 0, 0, 1, 1
        self.assertEqual(stretched["export_limit_mwh"], 20.0)
        self.assertEqual(period["import_limit_mwh"], 20.0)      # rows 0..3, x 0.5 h
        self.assertEqual(period["export_limit_mwh"], 30.0)
        self.assertEqual(stretched["mean_price_gbp_per_mwh"], 1.5)
        self.assertEqual(period["mean_price_gbp_per_mwh"], 2.5)

    @unittest.skipUnless(_gbp1_root(), "set VALUE_P0_5_PACKS to the GBP1 public1 pack")
    def test_gbp1_netherlands_connection_was_fed_a_zero_price_at_35aadb3(self):
        inputs = COMPARE.boundary_inputs(_gbp1_root())["connections"]
        netherlands = inputs["Interconnect_Netherland"]
        self.assertEqual(netherlands["head_35aadb3"]["feed"], "belgium")
        self.assertEqual(netherlands["head_35aadb3"]["zero_price_periods"], 17_520)
        self.assertEqual(netherlands["universal_reading"]["feed"], "netherlands")
        self.assertGreater(netherlands["universal_reading"]["mean_price_gbp_per_mwh"], 100.0)
        # P6-02: the Belgium connection now carries the EUR price at 1.1 EUR/GBP (R029 value).
        self.assertAlmostEqual(inputs["Interconnect_Beligum"]["universal_reading"]["mean_price_gbp_per_mwh"], 222.2926, places=3)


if __name__ == "__main__":
    unittest.main()
