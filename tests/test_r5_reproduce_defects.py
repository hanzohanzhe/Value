"""R5 (DECISIONS A28): the reproduce-role defects of the final acceptance report (c204aac).

Each test names the defect it covers (R-中n / R-低n).
"""

from __future__ import annotations

import csv
import dataclasses
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core import result_advisories
from gridform_core.market_ledger import create_market_ledger
from gridform_core.market_replay import query_dispatch_timeline
from gridform_core.result_advisories import (
    WITHHELD_NOT_EVALUATED,
    WITHHELD_PENDING,
    evaluate_advisories,
    run_result_publication,
)

from tests.test_market_replay import _period

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "runs"


def _ledger(folder: Path, *, boundary: str | None = None, short_period: int | None = None,
            unused: float = 0.0) -> Path:
    """Four half-hours; period ``short_period`` is 3 MWh short of demand."""

    database = folder / "model-output" / "market" / "market.sqlite"
    semantic = {"period_hours": 0.5}
    if boundary:
        semantic["energy_balance_boundary"] = boundary
    ledger = create_market_ledger(database, "full", semantic_metadata=semantic)
    for period in range(4):
        row = _period(period, curtailment=unused)
        if period == short_period:
            row = dataclasses.replace(row, accepted_supply_mwh=7.0)
        ledger.record_period(row)
    ledger.close()
    return database


class PendingPublicationTests(unittest.TestCase):
    """R-低2: an unfinished doctoral Run is pending its raw-invariant check, not "not evaluated"."""

    def _run(self, state: str) -> tuple[Path, dict]:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        root = folder / "doctoral"
        shutil.copytree(FIXTURES / "doctoral-no-invariants", root)
        status = json.loads((root / "status.json").read_text(encoding="utf-8"))
        status["status"] = state
        (root / "status.json").write_text(json.dumps(status), encoding="utf-8")
        return root, status

    def test_running_run_is_pending(self):
        root, status = self._run("running")
        publication = run_result_publication(root, status)
        self.assertEqual(publication["status"], "withheld")  # annual resources stay gated
        self.assertEqual(publication["raw_invariants_status"], "pending")
        self.assertEqual(publication["reason_code"], WITHHELD_PENDING)
        self.assertIn("still running", publication["message"])

    def test_completed_run_without_evidence_is_not_evaluated(self):
        root, status = self._run("completed")
        publication = run_result_publication(root, status)
        self.assertEqual(publication["raw_invariants_status"], "not_evaluated")
        self.assertEqual(publication["reason_code"], WITHHELD_NOT_EVALUATED)

    def test_comparison_reason_says_still_running(self):
        from gridform_core.results_summary import annual_withholding_reasons

        summary = {"run": {"run_id": "d", "mode": "two_year"}, "result_publication": {
            "status": "withheld", "raw_invariants_status": "pending", "reason_code": WITHHELD_PENDING}}
        reasons = annual_withholding_reasons([summary], ["two_year"])
        self.assertIn("still running", reasons[0]["text"])


class CompatibilityCapitalAdvisoryTests(unittest.TestCase):
    """R-低5: the run-of-river compatibility-capital advisory needs natural-flow hydro in the fleet."""

    ADVISORY = "p07.compatibility-capital-out-of-headline"

    def setUp(self) -> None:
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        self.run_root = Path(folder) / "run"
        shutil.copytree(FIXTURES / "pre-fix-dynamic-full", self.run_root)
        self.status = json.loads((self.run_root / "status.json").read_text(encoding="utf-8"))
        result_advisories._ASSET_CACHE.clear()

    def _freeze_fleet(self, *generators: str) -> None:
        pack = self.run_root / "input-snapshot" / "pack"
        (pack / "files").mkdir(parents=True, exist_ok=True)
        fleet = {"generators": {name: {"name": name} for name in generators}, "batteries": {}, "connections": {}}
        (pack / "files" / "fleet.json").write_text(json.dumps(fleet), encoding="utf-8")
        manifest = {"id": "value-101-baseline-v1", "bindings": {"fleet.generators": {"uri": "files/fleet.json"}}}
        (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _ids(self) -> set[str]:
        return {row["id"] for row in evaluate_advisories(self.status, self.run_root)}

    def test_fleet_without_run_of_river_hydro(self):
        self._freeze_fleet("CCGT", "onshore_London", "solar_London")
        self.assertNotIn(self.ADVISORY, self._ids())

    def test_fleet_with_run_of_river_hydro(self):
        self._freeze_fleet("CCGT", "Hydro_natural_flow")
        self.assertIn(self.ADVISORY, self._ids())

    def test_unreadable_fleet_keeps_the_advisory(self):
        self.assertIn(self.ADVISORY, self._ids())

    def test_applies_when_is_presentation_only(self):
        # Editing applies_when must not change any method identity (Q13).
        from gridform_core.methodology import load_catalogue

        correction = load_catalogue().corrections[self.ADVISORY]
        self.assertEqual(dict(correction.applies_when), {"assets_any": ("natural_flow_hydro",)})
        self.assertNotIn("applies_when", correction.semantic_identity())


class UnusedVreComparisonTests(unittest.TestCase):
    """R-中2: the comparison and the Runs card carry the physical unused VRE of the VRE page."""

    def test_annual_unused_vre_matches_the_vre_page(self):
        from gridform_core.market_replay import query_vre_curtailment_summary
        from gridform_core.results_summary import annual_unused_vre

        with tempfile.TemporaryDirectory() as folder:
            database = _ledger(Path(folder), unused=1.5)
            annual = annual_unused_vre(database)
            page = query_vre_curtailment_summary(database)["years"][0]
        self.assertEqual(annual[2025]["unused_vre_mwh"], 6.0)
        self.assertAlmostEqual(annual[2025]["unused_vre_mwh"], page["neutral_unused_vre_mwh"])
        self.assertAlmostEqual(annual[2025]["available_vre_mwh"], page["available_vre_mwh"])
        self.assertEqual(annual_unused_vre(Path(folder) / "missing.sqlite"), {})

    def test_run_summary_and_comparison_carry_unused_vre(self):
        from gridform_core.results_summary import build_run_summary, compare_run_summaries, metric_delta_gate

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "run"
            shutil.copytree(FIXTURES / "pre-fix-dynamic-full", root)
            _ledger(root, unused=2.0)
            ledgers = root / "model-output" / "ledgers"
            ledgers.mkdir(parents=True, exist_ok=True)
            (ledgers / "annual-cost-ledger.json").write_text(json.dumps(
                {"years": [{"year": 2025, "cem_system_cost_gbp": 1.0, "lines": []}]}), encoding="utf-8")
            summary = build_run_summary(root)
        metrics = summary["annual"][0]["metrics"]
        self.assertEqual(metrics["unused_vre_mwh"]["value"], 8.0)
        self.assertEqual(metrics["unused_vre_mwh"]["definition_id"], "value.unused-vre/v1")
        self.assertAlmostEqual(metrics["unused_vre_share_percent"]["value"], 25.0)
        # The v2 attribution metrics stay unavailable on a copperplate Run.
        self.assertIsNone(metrics["vre_curtailment_mwh"]["value"])
        # Unused VRE is not gated by the curtailment-attribution evidence.
        gate = metric_delta_gate("unused_vre_mwh", [], {"metric_deltas_allowed": False})
        self.assertTrue(gate["allowed"])
        other = json.loads(json.dumps(summary))
        other["run"]["run_id"] = "other"
        other["annual"][0]["metrics"]["unused_vre_mwh"]["value"] = 4.0
        comparison = compare_run_summaries([summary, other])
        values = comparison["annual_comparison"][0]["metrics"]["unused_vre_mwh"]
        self.assertEqual(values[1]["delta_from_base"], -4.0)

    def test_runner_records_unused_vre_in_the_run_results(self):
        source = (ROOT / "backend" / "model_runner.py").read_text(encoding="utf-8")
        self.assertIn('"unused_vre_mwh": ((unused_vre_by_year', source)
        self.assertIn("unused_vre_by_year=annual_unused_vre(", source)


def _semantic_ledger(folder: Path, semantic_extra: dict, *, unused: float, excess: float) -> Path:
    """A four-half-hour ledger with the given VRE semantic metadata."""

    from tests.test_market_replay import _period as period_row

    database = folder / "model-output" / "market" / "market.sqlite"
    ledger = create_market_ledger(database, "full", semantic_metadata={"period_hours": 0.5, **semantic_extra})
    for period in range(4):
        ledger.record_period(period_row(period, curtailment=unused, excess=excess))
    ledger.close()
    return database


DOCTORAL_SEMANTIC = {
    "excess_scope": "inflexible_mixed", "excess_relationship": "separate_prebalancing",
    "curtailment_semantics": "balancing_stage_down_regulation_after_storage_export_and_flexible_demand",
}
CORRECTED_SEMANTIC = {
    "excess_scope": "non_vre", "excess_relationship": "separate_prebalancing",
    "curtailment_semantics": "vre_available_minus_gross_output",
}


class UnusedVreBoundaryTests(unittest.TestCase):
    """R5-2 review (major): unused VRE at different PSM boundaries is not compared as one quantity."""

    def _summary(self, folder: Path, semantic: dict, run_id: str, *, unused: float, excess: float) -> dict:
        from gridform_core.results_summary import build_run_summary

        root = folder / run_id
        shutil.copytree(FIXTURES / "pre-fix-dynamic-full", root)
        _semantic_ledger(root, semantic, unused=unused, excess=excess)
        ledgers = root / "model-output" / "ledgers"
        ledgers.mkdir(parents=True, exist_ok=True)
        (ledgers / "annual-cost-ledger.json").write_text(json.dumps(
            {"years": [{"year": 2025, "cem_system_cost_gbp": 1.0, "lines": []}]}), encoding="utf-8")
        summary = build_run_summary(root)
        summary["run"]["run_id"] = run_id
        return summary

    def test_boundary_and_pre_balancing_excess_are_recorded(self):
        from gridform_core.results_summary import annual_unused_vre

        with tempfile.TemporaryDirectory() as folder:
            doctoral = annual_unused_vre(_semantic_ledger(Path(folder) / "d", DOCTORAL_SEMANTIC, unused=0.5, excess=2.0))
            corrected = annual_unused_vre(_semantic_ledger(Path(folder) / "c", CORRECTED_SEMANTIC, unused=1.0, excess=2.0))
        self.assertEqual(doctoral[2025]["vre_boundary"], "after_separate_prebalancing_excess")
        self.assertEqual(doctoral[2025]["pre_balancing_excess_mwh"], 8.0)
        self.assertEqual(corrected[2025]["vre_boundary"], "full_node_gross_vre_output")
        # Under the corrected rules ``excess`` is non-VRE spill, not pre-balancing excess.
        self.assertIsNone(corrected[2025]["pre_balancing_excess_mwh"])

    def test_cross_boundary_delta_is_withheld_in_compare_and_csv(self):
        from gridform_core.results_summary import compare_run_summaries, comparison_csv

        with tempfile.TemporaryDirectory() as folder:
            doctoral = self._summary(Path(folder), DOCTORAL_SEMANTIC, "doctoral", unused=0.5, excess=2.0)
            corrected = self._summary(Path(folder), CORRECTED_SEMANTIC, "corrected", unused=1.0, excess=2.0)
        metrics = doctoral["annual"][0]["metrics"]
        self.assertEqual(metrics["unused_vre_mwh"]["vre_boundary"], "after_separate_prebalancing_excess")
        self.assertEqual(metrics["pre_balancing_excess_mwh"]["value"], 8.0)
        self.assertEqual(corrected["annual"][0]["metrics"]["pre_balancing_excess_mwh"]["status"], "not_applicable")
        comparison = compare_run_summaries([doctoral, corrected])
        for metric_id in ("unused_vre_mwh", "unused_vre_share_percent", "pre_balancing_excess_mwh"):
            gate = comparison["metric_delta_gates"][metric_id]
            self.assertFalse(gate["allowed"], metric_id)
            self.assertEqual(gate["reason_code"], "unused_vre_boundary_differs")
            self.assertIn("pre-balancing excess is reported separately", gate["reason"])
        values = comparison["annual_comparison"][0]["metrics"]["unused_vre_mwh"]
        self.assertEqual([item["value"] for item in values], [2.0, 4.0])  # per-Run figures stay
        self.assertTrue(all(item.get("delta_from_base") is None for item in values))
        self.assertEqual(values[1]["vre_boundary"], "full_node_gross_vre_output")
        # A metric unrelated to the VRE boundary keeps its delta.
        self.assertTrue(comparison["metric_delta_gates"]["cem_system_cost_gbp"]["allowed"])
        rows = list(csv.reader(comparison_csv(comparison).splitlines()))
        header = next(row for row in rows if row[:3] == ["run_id", "year", "metric_id"])
        records = [dict(zip(header, row)) for row in rows[rows.index(header) + 1:]]
        unused_rows = [row for row in records if row["metric_id"] == "unused_vre_mwh"]
        self.assertEqual({row["delta_shown"] for row in unused_rows}, {"false"})
        self.assertIn("different PSM boundaries", unused_rows[0]["delta_withheld_reason"])

    def test_same_boundary_keeps_its_delta(self):
        from gridform_core.results_summary import compare_run_summaries

        with tempfile.TemporaryDirectory() as folder:
            first = self._summary(Path(folder), CORRECTED_SEMANTIC, "first", unused=1.0, excess=0.0)
            second = self._summary(Path(folder), CORRECTED_SEMANTIC, "second", unused=0.5, excess=0.0)
        comparison = compare_run_summaries([first, second])
        self.assertTrue(comparison["metric_delta_gates"]["unused_vre_mwh"]["allowed"])
        values = comparison["annual_comparison"][0]["metrics"]["unused_vre_mwh"]
        self.assertEqual(values[1]["delta_from_base"], -2.0)


class ComparisonCsvReasonTests(unittest.TestCase):
    """R-低12: the comparison CSV says why a value is empty or a delta is withheld."""

    def test_reason_columns(self):
        from gridform_core.results_summary import build_run_summary, compare_run_summaries, comparison_csv

        first = build_run_summary(FIXTURES / "pre-fix-dynamic-full")
        first["annual"] = [{"year": 2025, "metrics": {
            "cem_system_cost_gbp": {"value": 10.0, "unit": "GBP", "definition_id": "d", "denominator": None, "source": "s"},
            "vre_curtailment_mwh": {"value": None, "unit": "MWh", "definition_id": "v2", "denominator": None, "source": "s",
                                    "status": "unavailable", "reason_code": "module_does_not_provide_counterfactual_snapshot"},
        }}]
        second = json.loads(json.dumps(first))
        second["run"]["run_id"] = "second"
        comparison = compare_run_summaries([first, second])
        rows = list(csv.reader(comparison_csv(comparison).splitlines()))
        header = next(row for row in rows if row[:3] == ["run_id", "year", "metric_id"])
        self.assertEqual(header[-4:], ["value_status", "value_reason_code", "delta_shown", "delta_withheld_reason"])
        records = [dict(zip(header, row)) for row in rows[rows.index(header) + 1:]]
        curtailment = next(row for row in records if row["metric_id"] == "vre_curtailment_mwh")
        self.assertEqual(curtailment["value"], "")
        self.assertEqual(curtailment["value_status"], "unavailable")
        self.assertEqual(curtailment["value_reason_code"], "module_does_not_provide_counterfactual_snapshot")
        self.assertEqual(curtailment["delta_shown"], "false")
        self.assertIn("curtailment-attribution", curtailment["delta_withheld_reason"])
        cost = next(row for row in records if row["metric_id"] == "cem_system_cost_gbp")
        self.assertEqual((cost["value_status"], cost["delta_shown"], cost["delta_withheld_reason"]), ("recorded", "true", ""))


class ReplayExportStressColumnsTests(unittest.TestCase):
    """R-低9: flat replay exports carry the stress columns and the price basis."""

    def test_flat_export_has_shortfall_stress_and_price_basis(self):
        from gridform_core.replay_export import _write_flat

        with tempfile.TemporaryDirectory() as folder:
            database = _ledger(Path(folder), boundary="full_node_v1", short_period=2)
            target = Path(folder) / "export.csv"
            _write_flat(database, target, "csv", " WHERE year=?", (2025,))
            with target.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            timeline = query_dispatch_timeline(database, year=2025, resolution="half_hour", limit=4)
        self.assertEqual(list(rows[0])[-1], "period_start_utc")
        for column in ("clearing_price_basis", "period_shortfall_mwh", "period_stress", "shortfall_basis"):
            self.assertIn(column, rows[0])
        self.assertEqual({row["clearing_price_basis"] for row in rows}, {timeline["price_basis"]})
        self.assertEqual([row["period_stress"] for row in rows], ["0", "0", "1", "0"])
        self.assertAlmostEqual(float(rows[2]["period_shortfall_mwh"]), 3.0)
        # The same numbers as the replay API's half-hour buckets.
        self.assertEqual([float(row["period_shortfall_mwh"]) for row in rows],
                         [float(item["shortfall_mwh"]) for item in timeline["items"]])


class AcceptedSupplyBoundaryTests(unittest.TestCase):
    """R-低10: the dispatch timeline states the boundary "Accepted supply" is recorded at."""

    def test_boundary_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            corrected = query_dispatch_timeline(
                _ledger(Path(folder) / "a", boundary="native_corrected_full_node_v1"), year=2025, resolution="half_hour", limit=4)
            doctoral = query_dispatch_timeline(
                _ledger(Path(folder) / "b", boundary="default_psm_surplus_node_v1"), year=2025, resolution="half_hour", limit=4)
            unknown = query_dispatch_timeline(_ledger(Path(folder) / "c"), year=2025, resolution="half_hour", limit=4)
        self.assertEqual(corrected["accepted_supply_boundary"]["boundary_id"], "native_corrected_full_node_v1")
        self.assertIn("XS", corrected["accepted_supply_boundary"]["formula"])
        self.assertEqual(doctoral["accepted_supply_boundary"]["boundary_id"], "default_psm_surplus_node_v1")
        self.assertEqual(unknown["accepted_supply_boundary"]["boundary_id"], "unknown")
        self.assertIsNone(unknown["accepted_supply_boundary"]["formula"])


class ExtensionResultsWithoutExtensionsTests(unittest.TestCase):
    """R-低7: a Run that selected no extension says so and keeps its module-graph identity."""

    def _run(self, folder: Path, selected: list[str]) -> Path:
        root = folder / "run"
        (root / "model-output").mkdir(parents=True)
        (root / "status.json").write_text(json.dumps({"id": "run", "status": "completed", "mode": "two_year"}), encoding="utf-8")
        (root / "model-output" / "module-resolution.json").write_text(json.dumps({
            "schema_version": "value.module-resolution/v1", "graph_sha256": "a" * 64, "modules": {}}), encoding="utf-8")
        (root / "project-snapshot.json").write_text(json.dumps({"selected_extensions": selected}), encoding="utf-8")
        return root

    def test_no_extensions_selected(self):
        from backend.extension_results import query_extension_artifacts

        with tempfile.TemporaryDirectory() as folder:
            result = query_extension_artifacts(self._run(Path(folder), []), {})
        self.assertEqual(result["reason_code"], "no_extensions_selected")
        self.assertEqual(result["identity"]["frozen_module_graph_sha256"], "a" * 64)

    def test_selected_extension_without_graph_is_still_a_gap(self):
        from backend.extension_results import query_extension_artifacts

        with tempfile.TemporaryDirectory() as folder:
            result = query_extension_artifacts(self._run(Path(folder), ["x"]), {})
        self.assertEqual(result["reason_code"], "frozen_extension_graph_missing")


if __name__ == "__main__":
    unittest.main()
