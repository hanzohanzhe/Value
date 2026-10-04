import json
import unittest

from gridform_core.v2.contracts import (
    ArtifactReference,
    AssetStateV2,
    ExpansionHeadroom,
    InvestmentDecision,
    InvestmentProposal,
    MarketYearResult,
    ModuleSelection,
    OperatingState,
    PeriodSummary,
    PlanningAdmissionResult,
    PlanningAdvanceResult,
    PlanningEvent,
    PlanningEventType,
    PlanningProject,
    ResolvedRun,
    YearResult,
    YearState,
)


class ContractV2RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.asset = AssetStateV2("asset-1", "solar", 10.0, region="GB")
        self.project = PlanningProject(
            project_id="repd:1", name="One", source="external_repd",
            technology="solar", capacity_mw=5.0, original_capacity_mw=5.0,
            region="Scotland", development_stage="planning", status="active",
            decision_year=2024, expected_completion_year=2027,
            success_mode="expected", success_probability=0.7,
        )
        self.event = PlanningEvent(
            "event-1", "repd:1", 2025, PlanningEventType.STAGE_ADVANCED, 1
        )
        self.operating = OperatingState(2025, (self.asset,), (self.project,))
        self.period = PeriodSummary(
            "2025:0:day_ahead", 2025, 0, "day_ahead", 50.0, 50.0, 50.0,
            0.0, 0.0, 20.0, 20.0, 0.0, 2.0, 70.0, 1000.0, 3500.0,
            0.0, 0.0,
        )

    def test_resolved_run_round_trip(self):
        value = ResolvedRun(
            "run-1", "project-1", "scenario-1", "pack-1", 2025, 2026,
            {"psm": ModuleSelection("psm", "value-bid-at-cost-psm", "2.0.0", "value.psm/v2")},
            {"planning.success_mode": "expected"}, {"market_trace_level": "summary"},
        )
        payload = json.loads(json.dumps(value.to_dict()))
        self.assertEqual(ResolvedRun.from_dict(payload), value)

    def test_complete_year_result_round_trip(self):
        artifact = ArtifactReference("market-db", "market-ledger", "market/market.sqlite", "application/vnd.sqlite3")
        advance = PlanningAdvanceResult(
            2025, self.operating, (self.project,), (), (), (), (self.event,), artifacts=(artifact,)
        )
        market = MarketYearResult(
            "market-2025", 2025, "value-bid-at-cost-psm", "2.0.0", {"asset-1": 100.0},
            {"agent-1": 1000.0}, 2000.0, 1000.0, 1000.0, 100.0, 100.0,
            0.0, 0.0, period_summaries=(self.period,), artifacts=(artifact,),
        )
        headroom = ExpansionHeadroom("vre-2025", 2025, "vre-expansion-cap", {"solar": 5.0})
        proposal = InvestmentProposal("proposal-1", 2025, "agent-1", "solar", 5.0, "Scotland", 2027)
        investment = InvestmentDecision("decision-1", 2025, "agent-investment", (proposal,), {})
        admission = PlanningAdmissionResult(2025, (self.project,), (), (self.project,), (self.event,))
        next_state = YearState(2026, (self.asset,), (self.project,))
        value = YearResult(
            "year-2025", 2025, advance, market, (headroom,), investment,
            admission, next_state, artifacts=(artifact,),
        )
        payload = json.loads(json.dumps(value.to_dict()))
        self.assertEqual(YearResult.from_dict(payload), value)

    def test_extension_data_is_namespaced(self):
        value = ArtifactReference(
            "x", "test", "x.json", "application/json", extensions={"researcher": {"note": "ok"}}
        )
        self.assertEqual(value.to_dict()["extensions"], {"researcher": {"note": "ok"}})


if __name__ == "__main__":
    unittest.main()
