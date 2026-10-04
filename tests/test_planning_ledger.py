import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gridform_core.planning_ledger import (
    PlanningLedger,
    ensure_project_id,
    query_events,
    query_projects,
)
from gridform_core.v2.contracts import PlanningEventType, PlanningReasonCode


def project(name, source="external", capacity=10.0, region="Scotland", **extra):
    value = {
        "name": name,
        "source": source,
        "technology_type": "solar",
        "capacity": capacity,
        "original_capacity": capacity,
        "region": region,
        "development_status": "Application Submitted",
        "completion_year": 2027,
    }
    value.update(extra)
    return value


class PlanningLedgerTests(unittest.TestCase):
    def test_every_event_and_reason_code_is_serialisable_and_unique(self):
        event_values = [item.value for item in PlanningEventType]
        reason_values = [item.value for item in PlanningReasonCode]
        self.assertEqual(len(event_values), len(set(event_values)))
        self.assertEqual(len(reason_values), len(set(reason_values)))
        for item in PlanningEventType:
            with self.subTest(event=item.value):
                self.assertEqual(PlanningEventType(item.value), item)
                json.dumps(item.value)
        for item in PlanningReasonCode:
            with self.subTest(reason=item.value):
                self.assertEqual(PlanningReasonCode(item.value), item)
                json.dumps(item.value)

    def test_reconciliation_location_and_paginated_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            planning_dir = Path(folder) / "planning"
            ledger = PlanningLedger(planning_dir, batch_size=2)
            active = project("Active", latitude=56.0, longitude=-3.0, repd_id="A")
            filtered = project("Filtered", region="Unknown", repd_id="B")
            missing_location = project("No coordinates", repd_id="C")

            ledger.record_imports([active, missing_location], year=2025)
            ledger.record_source_import(filtered, year=2025)
            ledger.record_source_filter(
                filtered,
                year=2025,
                event_type=PlanningEventType.FILTERED_STATUS_ZOMBIE,
                reason_code=PlanningReasonCode.STATUS_STAGNANT,
            )
            summary = ledger.complete_year(2025, [active, missing_location])
            ledger.close()

            self.assertTrue(summary["reconciled"])
            self.assertEqual(summary["introduced_projects"], 3)
            self.assertEqual(summary["kpis"]["active"]["projects"], 2)
            self.assertEqual(summary["kpis"]["filtered"]["projects"], 1)
            self.assertIn(
                PlanningReasonCode.STATUS_STAGNANT.value,
                summary["cause_breakdowns"]["reason_code"],
            )
            self.assertTrue(any(
                row["event_type"] == PlanningEventType.FILTERED_STATUS_ZOMBIE.value
                for row in summary["causal_flows"]
            ))
            page = query_projects(planning_dir / "pipeline.sqlite", limit=2)
            self.assertEqual(page["total"], 3)
            self.assertEqual(len(page["items"]), 2)
            located = query_projects(
                planning_dir / "pipeline.sqlite", region="Scotland", limit=10
            )
            by_name = {item["name"]: item for item in located["items"]}
            self.assertEqual(by_name["Active"]["latitude"], 56.0)
            self.assertIsNone(by_name["No coordinates"]["latitude"])
            searched = query_projects(
                planning_dir / "pipeline.sqlite", search="active", limit=10
            )
            self.assertEqual(searched["total"], 1)
            self.assertEqual(searched["items"][0]["name"], "Active")
            events = query_events(
                planning_dir / "pipeline.sqlite",
                event_type=PlanningEventType.FILTERED_STATUS_ZOMBIE.value,
            )
            self.assertEqual(events["total"], 1)
            persisted = json.loads((planning_dir / "summary.json").read_text("utf-8"))
            self.assertTrue(persisted["years"][0]["reconciled"])

    def test_reconciliation_rejects_an_unclassified_disappearance(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = PlanningLedger(Path(folder))
            lost = project("Lost", repd_id="lost")
            ledger.record_imports([lost], year=2025)
            with self.assertRaisesRegex(RuntimeError, "unclassified"):
                ledger.complete_year(2025, [])
            ledger.close()

    def test_project_ids_are_stable_and_distinguish_source_rows(self):
        first = project("Same", source_row_number="repd.csv:1")
        second = project("Same", source_row_number="repd.csv:2")
        self.assertEqual(ensure_project_id(first.copy()), ensure_project_id(first.copy()))
        self.assertNotEqual(ensure_project_id(first), ensure_project_id(second))

    def test_summary_merges_case_only_labels_for_cross_platform_json_readers(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = PlanningLedger(Path(folder))
            upper = project(
                "Upper biomass", repd_id="upper",
                technology_type="Biomass (Dedicated)",
            )
            lower = project(
                "Lower biomass", repd_id="lower",
                technology_type="Biomass (dedicated) ",
            )
            ledger.record_imports([upper, lower], year=2025)
            summary = ledger.complete_year(2025, [upper, lower])
            ledger.close()

        technologies = summary["breakdowns"]["technology"]
        matching = [
            value for key, value in technologies.items()
            if key.casefold() == "biomass (dedicated)"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["projects"], 2)
        self.assertEqual(matching[0]["capacity_mw"], 20.0)

    def test_expected_and_seeded_stochastic_modes_remain_distinct(self):
        from gridform_core.builtin.scheme_c_1000twh.compat.modular_investment_support import (
            _resolve_model_success_capacity,
        )

        args = dict(
            original_capacity=100.0,
            success_rate=0.4,
            project_key="agent-1:solar:2025",
            region="Scotland",
            success_tech="Solar Photovoltaics",
        )
        with patch.dict(os.environ, {"MODEL_SUCCESS_MODE": "expected"}):
            expected = _resolve_model_success_capacity(**args)
        with patch.dict(os.environ, {"MODEL_SUCCESS_MODE": "lottery"}):
            first = _resolve_model_success_capacity(**args)
            second = _resolve_model_success_capacity(**args)
        self.assertEqual(expected, (40.0, True, None, "active"))
        self.assertEqual(first, second)
        self.assertIsNotNone(first[2])
        self.assertIn(first[0], (0.0, 100.0))


if __name__ == "__main__":
    unittest.main()
