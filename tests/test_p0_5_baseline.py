"""P0-5 S0: the captured data-reading baseline describes the code as it is.

Plan 4.5 step S0 (no behaviour change).  ``tests/golden/p0_5_baseline.json``
and ``tests/golden/p0_5_declaration_coverage.json`` were written once by
``scripts/capture_p0_5_baseline.py capture``.  These tests prove that

* the teaching packs (always) and the released GBP1/R029 public1 research
  packs (when ``VALUE_P0_5_PACKS`` points at them) still read exactly as
  captured, including what the real retained kernel receives;
* the kernel-input oracle in the capture script equals the real retained
  kernel on a non-constant toy pack, so the stored oracle entries describe
  what the kernel really receives (the shipped 101 market series are constant
  and cannot show a clock stretch or a mis-wiring);
* the HEAD behaviours named by the review (P6-01/02/03/05/07/24) are visible
  in the baseline.

A later P0-5 step that changes reading behaviour updates the affected entries
and their ``expected_change`` reasoning, never silently.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests.p0_5_fixtures import (
    GBP1_PUBLIC1,
    R029_PUBLIC1,
    TOY_COUNTRY_INDEX,
    KernelBoundaryRecorder,
    capture_module,
    nonconstant_boundary_pack,
    research_pack_roots,
    run_value_101_day,
    toy_price,
    toy_profile,
)

DECISION_IDS = ("Q1", "Q9", "A1", "A3", "A5", "Q15", "plan 4.5")
PROFILES = {"doctoral-lineage-0.6.0a2", "value-corrected"}


class P05BaselineFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = capture_module()
        cls.baseline = cls.capture.load_baseline()
        cls.coverage = json.loads(cls.capture.COVERAGE_PATH.read_text(encoding="utf-8"))

    def test_schema_size_and_packs(self) -> None:
        self.assertEqual(self.baseline["schema_version"], "value.p0-5-reading-baseline/v1")
        self.assertEqual(self.coverage["schema_version"], "value.p0-5-declaration-coverage/v1")
        self.assertLess(self.capture.BASELINE_PATH.stat().st_size, 50 * 1024)
        self.assertEqual(
            set(self.baseline["packs"]),
            {"value-101-baseline-v1", "value-101-network-v1", GBP1_PUBLIC1, R029_PUBLIC1},
        )
        self.assertEqual(set(self.coverage["packs"]), set(self.baseline["packs"]))
        self.assertEqual(self.baseline["packs"]["value-101-network-v1"]["same_reading_as"], "value-101-baseline-v1")
        self.assertEqual(self.baseline["windows"], [17520, 336, 48])
        self.assertEqual(self.baseline["kernel_recorded_window"], 48)
        self.assertEqual(self.baseline["head_rules"]["kernel_connection_feeds"], self.capture.HEAD_KERNEL_CONNECTION_FEEDS)
        # The research entries are the released public1 revisions.
        self.assertEqual(self.baseline["research_packs"], self.capture.RESEARCH_PACKS)
        for label, entry in self.capture.RESEARCH_PACKS.items():
            stored = self.baseline["packs"][label]
            self.assertEqual((stored["pack_id"], stored["manifest_sha256"]), (entry["pack_id"], entry["manifest_sha256"]))
        release = json.loads((self.capture.ROOT / "docs" / "release" / "public-data-assets.json").read_text(encoding="utf-8"))
        assets = {asset["name"]: asset["sha256"] for asset in release["assets"]}
        for entry in self.capture.RESEARCH_PACKS.values():
            self.assertEqual(assets[entry["release_asset"]], entry["release_asset_sha256"])
        # Captured on reader code identical to the pre-P0 commit.
        self.assertIs(self.baseline["captured_with"]["reader_sources_identical_to_35aadb3"], True)
        text = self.capture.BASELINE_PATH.read_text(encoding="utf-8") + self.capture.COVERAGE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/tmp/", text)

    def test_expected_change_cites_decisions_and_known_packs(self) -> None:
        known = set(self.baseline["packs"]) | {"*"}
        for entry in self.baseline["expected_change"]:
            with self.subTest(finding=entry["finding"]):
                self.assertTrue(any(item in entry["decision"] for item in DECISION_IDS), entry["decision"])
                self.assertTrue(set(entry["packs"]) <= known)
                self.assertTrue(set(entry["profiles"]) <= PROFILES and entry["profiles"])
                self.assertTrue(entry["entries"])
                for pattern in entry["entries"]:
                    self.assertIn(pattern.split(".")[0], self.baseline["packs"]["value-101-baseline-v1"], pattern)
        by_finding = {entry["finding"]: entry for entry in self.baseline["expected_change"]}
        # DECISIONS: P6-24 (Q9/A3) and P6-02/03/04 (A5) are universal; P6-07 is profile-gated (Q1).
        for finding in ("P6-24", "P6-02", "P6-03", "P6-04", "P6-01"):
            self.assertEqual(set(by_finding[finding]["profiles"]), PROFILES, finding)
        for finding in ("P6-07", "P6-05", "P6-06/P6-08", "boundary-raw-price"):
            self.assertEqual(by_finding[finding]["profiles"], ["value-corrected"], finding)
        # Plan S0 acceptance: R029 and the 101 short windows are marked.
        self.assertIn(R029_PUBLIC1, by_finding["P6-01"]["packs"])
        self.assertIn("value-101-baseline-v1", by_finding["P6-07"]["packs"])
        self.assertTrue(all(".336." in item or ".48." in item for item in by_finding["P6-07"]["entries"]))

    def test_head_findings_are_visible_in_the_baseline(self) -> None:
        r029 = self.baseline["packs"][R029_PUBLIC1]
        gbp1 = self.baseline["packs"][GBP1_PUBLIC1]
        teaching = self.baseline["packs"]["value-101-baseline-v1"]
        feeds = {feed: name for name, feed in self.capture.HEAD_KERNEL_CONNECTION_FEEDS.items()}
        for country in TOY_COUNTRY_INDEX:
            for kind in ("profile", "price"):
                role = f"market.{country}.{kind}"
                # P6-01: R029 declares csv_column, the adapter reads the period index.
                self.assertEqual(r029["canonical_reader"][role]["label"], "period", role)
                self.assertTrue(r029["canonical_reader"][role]["index_like"], role)
                declared = self.coverage["packs"][R029_PUBLIC1]["roles"][role]
                self.assertFalse(declared["csv_column_honoured"], role)
            # P6-01 in the kernel: the flattened 7-column frame reaches the kernel as objects.
            entry = r029["kernel_boundary_oracle"]["17520"]["connections"][feeds[country]]["transfer_constraint"]
            self.assertEqual(entry[0], "object")
            self.assertTrue(entry[2].startswith("obj:"))
        # ... and the real kernel stops on it (review: TypeError in the retained kernel).
        stopped = r029["kernel_recorded"]["48"]
        self.assertTrue(stopped["error"].startswith("TypeError"), stopped["error"])
        self.assertLess(stopped["periods_reached"], 48)
        # P6-02: GBP1 Belgium price is the hourly EUR column, wrapped onto the year.
        belgium = gbp1["canonical_reader"]["market.belgium.price"]
        self.assertEqual((belgium["label"], belgium["n"], belgium["col"]), ("Price (EUR/MWhe)", 15312, 3))
        self.assertEqual(gbp1["canonical_clock"]["17520"]["market.belgium.price"][0], "resize_wrap:15312")
        # P6-02 in the kernel: iloc[:, 0] is the Country column, every price is 0.
        zeros = self.capture.digest(np.zeros(48))
        self.assertEqual(gbp1["kernel_recorded"]["48"]["connections"][feeds["belgium"]]["external_price"], zeros)
        # P6-03: the Belgium role carries BritNed (GB-NL), the Netherlands role Nemo (GB-BE).
        self.assertEqual(gbp1["canonical_reader"]["market.belgium.profile"]["label"], "BRITNED_FLOW")
        self.assertEqual(gbp1["canonical_reader"]["market.netherlands.profile"]["label"], "NEMO_FLOW")
        # P6-05: the headerless forecast loses its first value to header=0.
        forecast = gbp1["canonical_reader"]["demand.forecast"]
        self.assertEqual((forecast["label"], forecast["n"]), ("21560", 26203))
        # P6-04 precondition: GBP1 demand is row-ordered local time, the pack declares Europe/London.
        self.assertEqual(gbp1["timezone"], "Europe/London")
        # P6-07: short windows repeat hourly-length CSV profiles; the full year does not stretch 17520 rows.
        for role in ("profiles.vre_solar", "profiles.vre_onshore", "profiles.vre_offshore"):
            self.assertEqual(teaching["canonical_clock"]["48"][role][0], "hourly_repeat:17520")
            self.assertEqual(teaching["canonical_clock"]["336"][role][0], "hourly_repeat:17520")
            self.assertEqual(teaching["canonical_clock"]["17520"][role], "exact:17520")
        # P6-24: on the non-constant GBP1 series the kernel (p // 2) and the
        # doctoral-national canonical path (p) disagree.
        france_kernel = gbp1["kernel_recorded"]["48"]["connections"]["Interconnect_France"]["external_price"]
        france_canonical = gbp1["chronology"]["doctoral-national"]["48"]["imports"]["france"]["price"]
        self.assertNotEqual(france_kernel, france_canonical)

    def test_recorded_kernel_agrees_with_the_stored_oracle(self) -> None:
        for label in ("value-101-baseline-v1", GBP1_PUBLIC1):
            recorded = self.baseline["packs"][label]["kernel_recorded"]["48"]
            oracle = self.baseline["packs"][label]["kernel_boundary_oracle"]["48"]
            with self.subTest(pack=label):
                self.assertNotIn("error", recorded)
                self.assertEqual(recorded["periods_reached"], 48)
                self.assertEqual(set(recorded["connections"]), set(oracle["connections"]))
                for name, entry in recorded["connections"].items():
                    self.assertEqual(entry["transfer_constraint"], oracle["connections"][name]["transfer_constraint"][2], name)
                    self.assertEqual(entry["external_price"], oracle["connections"][name]["external_price"][2], name)
                self.assertEqual(recorded["demand"]["forecast"], oracle["demand"]["forecast"])
                self.assertEqual(recorded["demand"]["real"], oracle["demand"]["real"])
                self.assertEqual(recorded["demand"]["forecast_per_period"], oracle["demand"]["forecast"])
                self.assertEqual(recorded["vre_unit_limit"]["sites"], 43)
                # Sites with a zero capacity multiplier in the D3 project carry raw (zero) limits.
                raw = recorded["vre_unit_limit"]["raw_sites"]
                self.assertTrue(set(raw) < set(self.baseline["head_rules"]["vre_site_order"]), raw)

    def test_reader_sites_never_mention_the_column_declarations(self) -> None:
        mentioned = self.coverage["mentioned_by_reader_site"]
        for key in ("csv_column", "csv_header", "eur_per_gbp", "chronology_contract", "flow_sign", "time_convention"):
            self.assertEqual(mentioned[key], [], key)


class P05BaselineReplayTests(unittest.TestCase):
    """Re-capture the packs that are available and compare with the stored baseline."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = capture_module()
        cls.baseline = cls.capture.load_baseline()
        cls.coverage = json.loads(cls.capture.COVERAGE_PATH.read_text(encoding="utf-8"))

    def _replay(self, roots: list[Path], *, kernel: bool = True) -> None:
        report = self.capture.check(roots, self.baseline, kernel=kernel)
        self.assertEqual(report["differences"], {})
        for root in roots:
            label, reason = self.capture.stored_label(self.baseline, root)
            self.assertIsNotNone(label, reason)
            self.assertIn(label, report["checked"])
            capture = self.capture.stored_capture(self.baseline, label)
            manifest = self.capture.load_manifest(root)
            self.assertEqual(self.capture.declaration_coverage(manifest, capture), self.coverage["packs"][label])

    def test_teaching_packs_read_as_captured(self) -> None:
        baseline_pack, network_pack = (self.capture.ROOT / relative for relative in self.capture.REPOSITORY_PACKS)
        # The real kernel once (the network pack shares the baseline pack's reading).
        self._replay([baseline_pack])
        self._replay([network_pack], kernel=False)

    def test_research_packs_read_as_captured(self) -> None:
        roots = research_pack_roots()
        missing = sorted({GBP1_PUBLIC1, R029_PUBLIC1} - set(roots))
        if missing:
            self.skipTest(
                f"set {self.capture.PACKS_ENVIRONMENT} to the installed released pack directories of: {', '.join(missing)}"
            )
        self._replay([roots[GBP1_PUBLIC1], roots[R029_PUBLIC1]])

    def test_other_revision_of_a_research_pack_is_a_difference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "pack"
            root.mkdir()
            (root / "manifest.json").write_text(
                json.dumps({"id": self.capture.RESEARCH_PACKS[GBP1_PUBLIC1]["pack_id"], "bindings": {}}), encoding="utf-8"
            )
            report = self.capture.check([root], self.baseline)
            self.assertEqual(list(report["differences"]), [self.capture.RESEARCH_PACKS[GBP1_PUBLIC1]["pack_id"]])
            with self.assertRaises(ValueError):
                self.capture.pack_label(self.capture.file_sha256(root / "manifest.json"),
                                        self.capture.RESEARCH_PACKS[GBP1_PUBLIC1]["pack_id"])

    def test_declaration_scan_matches(self) -> None:
        self.assertEqual(self.capture.declaration_consumers(), self.coverage["mentioned_by_reader_site"])


class P05KernelBoundaryTests(unittest.TestCase):
    """The real retained kernel receives what the oracle (and so the baseline) says."""

    def test_iterlimit_new_serves_each_source_row_twice_then_wraps(self) -> None:
        values = [float(value) for value in capture_module().kernel_clock(np.array([10.0, 11.0, 12.0]), 8)]
        self.assertEqual(values, [10.0, 10.0, 11.0, 11.0, 12.0, 12.0, 10.0, 10.0])

    def test_head_kernel_stretches_and_miswires_a_nonconstant_boundary(self) -> None:
        capture = capture_module()
        with tempfile.TemporaryDirectory() as directory:
            pack = nonconstant_boundary_pack(Path(directory))
            recorder = KernelBoundaryRecorder()
            run_value_101_day(pack, recorder)
            manifest = capture.load_manifest(pack)
            oracle = capture.kernel_boundary_oracle(pack, manifest, 48)
            chronology = capture.chronology_capture(pack, manifest, 48, doctoral=False)
        self.assertEqual(recorder.periods, list(range(48)))
        self.assertEqual(set(recorder.connections), set(capture.HEAD_KERNEL_CONNECTION_FEEDS))
        for connection, feed in capture.HEAD_KERNEL_CONNECTION_FEEDS.items():
            observed = recorder.connections[connection]
            with self.subTest(connection=connection, feed=feed):
                # HEAD (P6-24): period p receives source row p // 2 ...
                self.assertEqual([float(value) for value in observed["transfer_constraint"]],
                                 [toy_profile(feed, period // 2) for period in range(48)])
                self.assertEqual([float(value) for value in observed["external_price"]],
                                 [toy_price(feed, period // 2) for period in range(48)])
                # ... and the oracle stored for GBP1/R029 is this kernel.
                self.assertEqual(capture.digest(observed["transfer_constraint"]),
                                 oracle["connections"][connection]["transfer_constraint"][2])
                self.assertEqual(capture.digest(observed["external_price"]),
                                 oracle["connections"][connection]["external_price"][2])
        # HEAD mis-wiring: three connections are fed another country's files.
        miswired = {name for name, feed in capture.HEAD_KERNEL_CONNECTION_FEEDS.items()
                    if name.removeprefix("Interconnect_").lower() not in feed}
        self.assertEqual(miswired, {"Interconnect_Netherland", "Interconnect_Ireland", "Interconnect_Beligum"})
        self.assertEqual(capture.digest(recorder.forecast_demands), oracle["demand"]["forecast"])
        self.assertEqual(capture.digest(recorder.real_demands), oracle["demand"]["real"])
        # The canonical adapter reads the same toy period by period: the two
        # doctoral paths disagree at HEAD (P6-24 note in the review).
        expected_price = capture.digest([toy_price("france", period) for period in range(48)])
        self.assertEqual(chronology["imports"]["france"]["price"], expected_price)


if __name__ == "__main__":
    unittest.main()
