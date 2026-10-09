"""R7-1 (DECISIONS A33, finding P4-05): endogenous investments enter the
planning pipeline with the pack's development timelines and success rates.

Oracles:

* ``SourceRuleParityTests`` runs the original Scheme C pipeline entry
  (``runtime_compat/modular_investment_support.append_model_investment_to_pipeline``)
  on the same tables and compares completion year, success rate, label and
  region for a grid of owners, technologies, decision years and statistics;
* ``HandOracleTests`` uses toy tables whose results are computed by hand
  (MD5 dispersion re-derived independently with ``hashlib``);
* ``Public2TableTests`` pins the GBP1/R029 public2 tables (fixture bytes equal
  the sha256 of both release manifests) and lists the completion years and
  probabilities of decisions taken in 2025;
* admission, freezing, fail-closed, decide() integration (both decide paths)
  and catalogue/identity (Q13) tests.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from gridform_core import revision_migration
from gridform_core.asset_economics import build_asset_economic_extensions
from gridform_core.builtin.scheme_c_1000twh import endogenous_planning as rule
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import (
    SchemeCAgentInvestmentDefinition,
    SchemeCPlanningPipelineDefinition,
)
from gridform_core.v2.contracts import (
    AssetStateV2,
    ExpansionHeadroom,
    InvestmentProposal,
    MarketYearResult,
    OperatingState,
    ResolvedRun,
    YearState,
)
from tests.r71_planning_fixtures import planning_parameters, with_planning

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "r71"
PUBLIC2_TIMELINES = FIXTURES / "public2_planning_timelines.json"
PUBLIC2_SUCCESS = FIXTURES / "public2_regional_technology_success_rates.csv"
# sha256 pinned by the GBP1 public2 (8d73e08c...) and R029 public2 (d9876d98...)
# manifests for planning.timelines and planning.success_rates (identical files).
PUBLIC2_TIMELINES_SHA256 = "960ef7cdb23f643a388c516013908efb5fd8346cafc65ee104c5f9c09aa0b152"
PUBLIC2_SUCCESS_SHA256 = "bd6f5ac68e8f619d196ffe2e4123601a6a56e162a89ef7e45a33a81abc951673"
VALUE_101 = ROOT / "data-packs" / "value-101-baseline-v1"
SYNTHETIC = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"
CORRECTION_ID = "r71.endogenous-planning-timelines"
DOCTORAL_PROFILE = "doctoral-lineage-0.6.0a2"
CORRECTED_PROFILE = "value-corrected"


def md5_jitter(owner: str) -> int:
    """Independent re-derivation of the original dispersion (-6..+6 months)."""
    return int(hashlib.md5(f"Model Decision: {owner}".encode("utf-8")).hexdigest()[:16], 16) % 13 - 6


def pack_file(pack: Path, role: str) -> Path:
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    return pack / manifest["bindings"][role]["uri"]


def frozen(timelines: Path, success: Path, statistic: str = "median") -> dict:
    return rule.freeze_planning_parameters(
        json.loads(timelines.read_text(encoding="utf-8")), success, timeline_statistic=statistic)


def public2(statistic: str = "median") -> dict:
    return frozen(PUBLIC2_TIMELINES, PUBLIC2_SUCCESS, statistic)


def source_success_table(path: Path) -> dict:
    """The original load_regional_technology_success_rates (raw labels, stripped regions)."""
    import pandas as pd

    nested: dict = {}
    for _, row in pd.read_csv(path).iterrows():
        nested.setdefault(row["Technology"], {})[str(row["Region"]).strip()] = row["Success_Rate"]
    return nested


def source_entry(owner, technology, decision_year, timelines_payload, success_nested, statistic="median"):
    from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_investment_support as source

    pipeline: list = []
    environment = {"PLANNING_USE_MEDIAN": "1" if statistic == "median" else "0", "MODEL_SUCCESS_MODE": "expected"}
    with mock.patch.object(source.config, "development_stage_timelines",
                           timelines_payload["development_stage_timelines"]), \
            mock.patch.object(source.config, "repd_status_to_timeline",
                              timelines_payload.get("repd_status_to_timeline") or {}), \
            mock.patch.dict(os.environ, environment):
        source.append_model_investment_to_pipeline(
            pipeline, name=f"Model Decision: {owner}", technology_type=technology, capacity=100.0,
            decision_year=decision_year, target_asset_name=owner, success_rates=success_nested,
            assigned_generator=owner)
    return pipeline[0]


OWNERS = (
    ("offshore1", "offshore"), ("offshore10", "offshore"), ("offshore13", "offshore"),
    ("onshore_Portsmouth", "onshore"), ("onshore_Birmingham", "onshore"), ("onshore_Edinburgh", "onshore"),
    ("solar_Portsmouth", "solar"), ("solar_Cardiff", "solar"), ("solar_Nottingham", "solar"),
    ("1c_battery", "1c_battery"), ("0.5c_battery", "0.5c_battery"), ("0.25c_battery", "0.25c_battery"),
    ("hydrogen_battery", "hydrogen_battery"), ("CCGT", "CCGT"), ("OCGT", "OCGT"),
    ("bio_and_waste", "bio_and_waste"), ("gas-owner", "gas"), ("owner-z", "solar"),
)


class SourceRuleParityTests(unittest.TestCase):
    """The rule equals the original pipeline entry on the same tables."""

    def assert_parity(self, timelines: Path, success: Path, *, statistic: str, normalised_labels: bool):
        payload = json.loads(timelines.read_text(encoding="utf-8"))
        nested = source_success_table(success)
        parameters = frozen(timelines, success, statistic)
        for owner, technology in OWNERS:
            for year in (2025, 2026, 2030, 2034):
                with self.subTest(owner=owner, year=year, statistic=statistic):
                    source = source_entry(owner, technology, year, payload, nested, statistic)
                    terms = rule.endogenous_planning_terms(
                        parameters, technology=technology, owner=owner, decision_year=year)
                    self.assertEqual(terms["source_completion_year"], source["completion_year"])
                    self.assertEqual(terms["completion_year"], max(source["completion_year"], year + 1))
                    self.assertEqual(terms["completion_floor_applied"], source["completion_year"] <= year)
                    self.assertEqual(terms["success_technology"], source["success_technology"])
                    self.assertEqual(terms["success_region"], source["success_region"])
                    self.assertEqual(terms["development_status"], source["development_status"])
                    if not normalised_labels:
                        self.assertEqual(terms["success_rate"], float(source["success_rate"]))
                        self.assertEqual(100.0 * terms["success_rate"], source["capacity"])

    def test_public2_tables_median_and_mean(self):
        for statistic in ("median", "mean"):
            self.assert_parity(PUBLIC2_TIMELINES, PUBLIC2_SUCCESS, statistic=statistic, normalised_labels=False)

    def test_value_101_and_synthetic_timelines(self):
        for pack in (VALUE_101, SYNTHETIC):
            with self.subTest(pack=pack.name):
                self.assert_parity(pack_file(pack, "planning.timelines"), pack_file(pack, "planning.success_rates"),
                                   statistic="median", normalised_labels=True)

    def test_compact_success_labels_are_normalised_explicit_choice(self):
        """VALUE 101 writes solar/onshore/offshore/battery: the original would miss them (0.75)."""
        success = pack_file(VALUE_101, "planning.success_rates")
        payload = json.loads(pack_file(VALUE_101, "planning.timelines").read_text(encoding="utf-8"))
        source = source_entry("solar_Portsmouth", "solar", 2025, payload, source_success_table(success))
        self.assertEqual(source["success_rate"], 0.75)
        terms = rule.endogenous_planning_terms(frozen(pack_file(VALUE_101, "planning.timelines"), success),
                                               technology="solar", owner="solar_Portsmouth", decision_year=2025)
        self.assertEqual((terms["success_rate"], terms["success_rate_source"]), (1.0, "pack_technology_mean"))


class HandOracleTests(unittest.TestCase):
    def test_md5_dispersion_of_the_owners_used_below(self):
        self.assertEqual([md5_jitter(owner) for owner in
                          ("offshore1", "offshore10", "onshore_Portsmouth", "solar_Cardiff", "CCGT", "owner-z")],
                         [6, -3, -4, -2, 1, 5])

    def terms(self, owner, technology, year=2025, **tables):
        return rule.endogenous_planning_terms(planning_parameters(**tables), technology=technology,
                                              owner=owner, decision_year=year)

    def test_offshore_110_months(self):
        # 110.1 + 6 = 116.1 -> 116 months = 9 years 8 months -> 2034;
        # 110.1 - 3 = 107.1 -> 107 months = 8 years 11 months -> 2033.
        first = self.terms("offshore1", "offshore", months=110.1)
        self.assertEqual((first["timeline_months_applied"], first["completion_year"]), (116, 2034))
        second = self.terms("offshore10", "offshore", months=110.1)
        self.assertEqual((second["timeline_months_applied"], second["completion_year"]), (107, 2033))
        self.assertEqual(second["timeline_months"], 110.1)
        self.assertFalse(second["completion_floor_applied"])

    def test_round_half_to_even_as_the_original(self):
        # 62.5 - 4 = 58.5 -> round() = 58 -> 4 years -> 2029 (Python's round, as the source).
        terms = self.terms("onshore_Portsmouth", "onshore", months=62.5)
        self.assertEqual((terms["timeline_months_applied"], terms["completion_year"]), (58, 2029))

    def test_completion_in_the_decision_year_is_floored_to_the_next_year(self):
        # 6 - 2 = 4 months -> source completion 2025 (never commissioned by the
        # original's equality check) -> explicit floor 2026.
        terms = self.terms("solar_Cardiff", "solar", months=6.0)
        self.assertEqual((terms["source_completion_year"], terms["completion_year"]), (2025, 2026))
        self.assertTrue(terms["completion_floor_applied"])
        # A zero-month table: 0 + 6 = 6 months, still the next year.
        self.assertEqual(self.terms("offshore1", "offshore", months=0.0)["completion_year"], 2026)

    def test_at_least_one_month_before_rounding(self):
        terms = self.terms("solar_Cardiff", "solar", months=0.0)  # max(1, 0 - 2) = 1
        self.assertEqual(terms["timeline_months_applied"], 1)

    def test_statistic_and_timeline_type(self):
        tables = {"solar": {"total_median": 24.0, "total_mean": 36.0,
                            "pre_construction_median": 10.0, "construction_median": 5.0,
                            "pre_construction_mean": 20.0, "construction_mean": 7.0}}
        median = rule.endogenous_planning_terms(planning_parameters(stage_timelines=tables), technology="solar",
                                                owner="owner-z", decision_year=2025)
        self.assertEqual((median["timeline_months"], median["completion_year"]), (24.0, 2027))  # 24 + 5 = 29 months
        mean = rule.endogenous_planning_terms(planning_parameters(stage_timelines=tables, statistic="mean"),
                                              technology="solar", owner="owner-z", decision_year=2025)
        self.assertEqual((mean["timeline_type"], mean["timeline_months"], mean["completion_year"]),
                         ("total_mean", 36.0, 2028))  # 36 + 5 = 41 months
        parameters = planning_parameters(stage_timelines=tables)
        parameters["repd_status_to_timeline"] = {"Application Submitted": {"timeline_type": "pre_construction_median"}}
        staged = rule.endogenous_planning_terms(parameters, technology="solar", owner="owner-z", decision_year=2025)
        self.assertEqual(staged["timeline_months"], 15.0)  # pre-construction + construction
        parameters["repd_status_to_timeline"] = {}
        self.assertEqual(rule.endogenous_planning_terms(parameters, technology="solar", owner="owner-z",
                                                        decision_year=2025)["timeline_type"], "total_median")

    def test_missing_technology_uses_the_solar_entry_and_missing_solar_fails(self):
        tables = {"solar": {"total_median": 30.0}}
        terms = rule.endogenous_planning_terms(planning_parameters(stage_timelines=tables), technology="offshore",
                                               owner="offshore10", decision_year=2025)
        self.assertEqual((terms["timeline_technology"], terms["timeline_months"]), ("solar", 30.0))
        with self.assertRaisesRegex(ValueError, "no 'offshore' entry and no 'solar' entry"):
            rule.endogenous_planning_terms(planning_parameters(stage_timelines={"onshore": {"total_median": 1.0}}),
                                           technology="offshore", owner="offshore10", decision_year=2025)

    def test_success_rate_lookup_order(self):
        rates = {"Wind Onshore": {"South East": 0.4, "Scotland": 0.6, "Wales": 0.8},
                 "Battery": {}}
        parameters = planning_parameters(success_rates=rates)

        def rate(owner, technology):
            terms = rule.endogenous_planning_terms(parameters, technology=technology, owner=owner, decision_year=2025)
            return terms["success_region"], terms["success_rate"], terms["success_rate_source"]

        self.assertEqual(rate("onshore_Portsmouth", "onshore"), ("South East", 0.4, "pack_region"))
        self.assertEqual(rate("onshore_Edinburgh", "onshore"), ("Scotland", 0.6, "pack_region"))
        # Thermal owners use the Wind Onshore label in England: not listed -> mean.
        region, value, source = rate("CCGT", "CCGT")
        self.assertEqual((region, source), ("England", "pack_technology_mean"))
        self.assertAlmostEqual(value, (0.4 + 0.6 + 0.8) / 3, places=15)
        self.assertEqual(rate("1c_battery", "1c_battery"), ("England", 0.75, "source_default_0.75"))
        self.assertEqual(rate("offshore10", "offshore"), ("All Offshore", 0.75, "source_default_0.75"))

    def test_labels_and_regions_of_the_source(self):
        self.assertEqual([rule.success_label(item) for item in
                          ("solar", "onshore", "offshore", "0.25c_battery", "electrolyzer", "gas", "OCGT",
                           "bio_and_waste", "hydrogen_battery", "unknown")],
                         ["Solar Photovoltaics", "Wind Onshore", "Wind Offshore", "Battery", "Battery",
                          "Wind Onshore", "Wind Onshore", "Wind Onshore", "Solar Photovoltaics",
                          "Solar Photovoltaics"])
        self.assertEqual([rule.source_success_region(name) for name in
                          ("solar_Nottingham", "onshore_Sheffield", "solar_Leeds", "offshore7", "1c_battery",
                           "CCGT", "owner-z")],
                         ["East Midlands", "Yorkshire and Humber", "England", "All Offshore", "England",
                          "England", "England"])


class Public2TableTests(unittest.TestCase):
    """GBP1/R029 public2 tables: decisions of 2025."""

    def test_fixture_bytes_are_the_released_tables(self):
        self.assertEqual(hashlib.sha256(PUBLIC2_TIMELINES.read_bytes()).hexdigest(), PUBLIC2_TIMELINES_SHA256)
        self.assertEqual(hashlib.sha256(PUBLIC2_SUCCESS.read_bytes()).hexdigest(), PUBLIC2_SUCCESS_SHA256)
        for item in os.environ.get("VALUE_P0_5_PACKS", "").split(os.pathsep):
            manifest = Path(item) / "manifest.json"
            if item.strip() and manifest.is_file():
                bindings = json.loads(manifest.read_text(encoding="utf-8")).get("bindings", {})
                if bindings.get("planning.timelines", {}).get("sha256") == PUBLIC2_TIMELINES_SHA256:
                    self.assertEqual(bindings["planning.success_rates"]["sha256"], PUBLIC2_SUCCESS_SHA256)

    @staticmethod
    def label_mean(label: str) -> float:
        with PUBLIC2_SUCCESS.open(encoding="utf-8", newline="") as handle:
            values = [float(row["Success_Rate"]) for row in csv.DictReader(handle) if row["Technology"] == label]
        return sum(values) / len(values)

    def test_completion_years_and_probabilities(self):
        parameters = public2()
        # (owner, technology) -> (median months, applied months, completion year, probability, source)
        expected = {
            ("offshore1", "offshore"): (110.1, 116, 2034, 0.9166666666666666, "pack_region"),
            ("offshore10", "offshore"): (110.1, 107, 2033, 0.9166666666666666, "pack_region"),
            ("onshore_Portsmouth", "onshore"): (62.5, 58, 2029, 0.35714285714285715, "pack_region"),
            ("onshore_Birmingham", "onshore"): (62.5, 58, 2029, 0.21739130434782608, "pack_region"),
            ("onshore_Edinburgh", "onshore"): (62.5, 64, 2030, 0.5367483296213809, "pack_region"),
            ("solar_Portsmouth", "solar"): (27.8, 29, 2027, 0.8687898089171975, "pack_region"),
            ("solar_Cardiff", "solar"): (27.8, 26, 2027, 0.8426966292134831, "pack_region"),
            ("1c_battery", "1c_battery"): (31.3, 31, 2027, self.label_mean("Battery"), "pack_technology_mean"),
            ("0.25c_battery", "0.25c_battery"): (31.3, 32, 2027, self.label_mean("Battery"), "pack_technology_mean"),
            ("CCGT", "CCGT"): (62.5, 64, 2030, self.label_mean("Wind Onshore"), "pack_technology_mean"),
            ("OCGT", "OCGT"): (62.5, 62, 2030, self.label_mean("Wind Onshore"), "pack_technology_mean"),
            ("bio_and_waste", "bio_and_waste"): (62.5, 66, 2030, self.label_mean("Wind Onshore"),
                                                 "pack_technology_mean"),
            # Source quirk kept (the original label default): Solar PV, England row.
            ("hydrogen_battery", "hydrogen_battery"): (27.8, 32, 2027, 0.9230769230769231, "pack_region"),
        }
        for (owner, technology), values in expected.items():
            with self.subTest(owner=owner):
                terms = rule.endogenous_planning_terms(parameters, technology=technology, owner=owner,
                                                       decision_year=2025)
                self.assertEqual((terms["timeline_months"], terms["timeline_months_applied"],
                                  terms["completion_year"], terms["success_rate_source"]),
                                 (values[0], values[1], values[2], values[4]))
                # pandas parses the CSV decimals (as the original loader did); they
                # may differ from Python's float() in the last place.
                self.assertAlmostEqual(terms["success_rate"], values[3], places=15)
        self.assertAlmostEqual(self.label_mean("Battery"), 0.87278592342, places=11)  # 15 rows
        self.assertAlmostEqual(self.label_mean("Wind Onshore"), 0.54686506214, places=11)  # 13 rows


def solar_asset(asset_id, owner, capacity=100.0, technology="solar", region="GB"):
    extensions = build_asset_economic_extensions(
        technology, capacity, energy_capacity_mwh=None, capital_costs_per_mw={technology: 1_000_000.0},
        lifetimes={technology: 25.0}, discount_rate=0.05, source_record_id=asset_id)
    extensions.update(investment_owner_id=owner, preferred_rate=0.08, target_payback_years=25.0)
    return AssetStateV2(asset_id, technology, capacity, region=region, extensions=extensions)


def market_for(income):
    return MarketYearResult("m", 2025, "psm", "1", {}, income, 1, 1, 1, 1, 1, 0, 0)


def run_for(mode="expected_capacity", seed=0):
    return ResolvedRun("r71", "p", "basic", "fixture", 2025, 2030, {},
                       {"planning.success_mode": mode, "planning.random_seed": seed}, {})


class DecideAndAdmissionTests(unittest.TestCase):
    def decide(self, state, income, caps):
        return SchemeCAgentInvestmentDefinition().decide(
            run_for(), state, market_for(income),
            (ExpansionHeadroom("h", 2025, "vre-expansion-cap", caps),))

    def test_decide_records_the_terms_on_the_proposal(self):
        state = with_planning(OperatingState(2025, (
            solar_asset("offshore10", "offshore10", technology="offshore"),
            solar_asset("onshore_Portsmouth", "onshore_Portsmouth", technology="onshore", region="Portsmouth"),
        ), ()), public2())
        decision = self.decide(state, {"offshore10": 20_000_000.0, "onshore_Portsmouth": 20_000_000.0},
                               {"offshore": 1000.0, "onshore": 1000.0})
        by_owner = {proposal.agent_id: proposal for proposal in decision.proposals}
        offshore, onshore = by_owner["offshore10"], by_owner["onshore_Portsmouth"]
        self.assertEqual(offshore.expected_completion_year, 2033)
        self.assertAlmostEqual(offshore.extensions["success_probability"], 66 / 72, places=15)
        self.assertEqual(offshore.extensions["timeline_months"], 110.1)
        self.assertEqual(offshore.extensions["success_rate_source"], "pack_region")
        self.assertNotIn("development_years", offshore.extensions)
        self.assertEqual(offshore.extensions["endogenous_planning_terms"]["correction_id"], CORRECTION_ID)
        self.assertEqual(onshore.expected_completion_year, 2029)
        self.assertAlmostEqual(onshore.extensions["success_probability"], 10 / 28, places=15)

        admitted = SchemeCPlanningPipelineDefinition().admit_projects(run_for(), state, decision.proposals)
        projects = {project.extensions["investment_owner_id"]: project for project in admitted.admitted_projects}
        probability = onshore.extensions["success_probability"]
        self.assertEqual(projects["onshore_Portsmouth"].capacity_mw, onshore.capacity_mw * probability)
        self.assertEqual(projects["onshore_Portsmouth"].expected_completion_year, 2029)
        self.assertEqual(projects["onshore_Portsmouth"].success_probability, probability)
        self.assertEqual(projects["offshore10"].expected_completion_year, 2033)

    def test_member_asset_extensions_no_longer_set_the_terms(self):
        asset = solar_asset("solar_Portsmouth", "solar_Portsmouth", region="Portsmouth")
        asset = replace(asset, extensions={**asset.extensions, "development_years": 9.0, "success_probability": 0.1})
        state = with_planning(OperatingState(2025, (asset,), ()), public2())
        proposal = self.decide(state, {"solar_Portsmouth": 20_000_000.0}, {"solar": 1000.0}).proposals[0]
        self.assertEqual(proposal.expected_completion_year, 2027)
        self.assertAlmostEqual(proposal.extensions["success_probability"], 682 / 785, places=15)

    def test_doctoral_decide_path_uses_the_same_rule(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_policy import decide_doctoral_investment
        from tests.test_doctoral_investment_alignment import typed_inputs

        run, state, market, headroom, accounts = typed_inputs()
        state = with_planning(state, public2())
        decision = decide_doctoral_investment(run, state, market, headroom, accounts)
        self.assertTrue(decision.proposals)
        for proposal in decision.proposals:
            terms = rule.endogenous_planning_terms(public2(), technology="solar", owner=proposal.agent_id,
                                                   decision_year=2025)
            self.assertEqual(proposal.expected_completion_year, terms["completion_year"])
            self.assertAlmostEqual(proposal.extensions["success_probability"], 12 / 13, places=15)  # Solar PV, England
            self.assertNotIn("development_years", proposal.extensions)

    def test_missing_frozen_tables_fail_closed_when_a_proposal_is_made(self):
        state = OperatingState(2025, (solar_asset("solar_Portsmouth", "solar_Portsmouth"),), ())
        with self.assertRaisesRegex(ValueError, "no frozen planning parameters"):
            self.decide(state, {"solar_Portsmouth": 20_000_000.0}, {"solar": 1000.0})
        # No proposal, no planning lookup.
        self.assertEqual(self.decide(state, {"solar_Portsmouth": 0.0}, {"solar": 1000.0}).proposals, ())

    def proposals(self, count, probability):
        return tuple(InvestmentProposal(f"p:{index}", 2025, f"owner-{index}", "solar", 10.0, "GB", 2027,
                                        extensions={"success_probability": probability})
                     for index in range(count))

    def test_expected_capacity_multiplies_by_p_and_stochastic_draws_follow_the_seed(self):
        state = OperatingState(2025, (), ())
        expected = SchemeCPlanningPipelineDefinition().admit_projects(run_for(), state, self.proposals(3, 0.4))
        self.assertEqual([project.capacity_mw for project in expected.admitted_projects], [4.0, 4.0, 4.0])
        self.assertEqual(expected.rejected_proposals, ())
        rejected = {}
        for seed in (0, 7, 12345):
            result = SchemeCPlanningPipelineDefinition().admit_projects(
                run_for("seeded_stochastic", seed), state, self.proposals(40, 0.5))
            rejected[seed] = {proposal.proposal_id for proposal in result.rejected_proposals}
            self.assertTrue(0 < len(rejected[seed]) < 40)
            self.assertTrue(all(project.capacity_mw == 10.0 for project in result.admitted_projects))
        self.assertEqual(len({frozenset(value) for value in rejected.values()}), 3)

    def test_commissioning_waits_for_the_completion_year(self):
        state = OperatingState(2025, (), ())
        proposal = InvestmentProposal(
            "p:1", 2025, "owner", "solar", 10.0, "GB", 2029,
            extensions={**build_asset_economic_extensions(
                "solar", 10.0, energy_capacity_mwh=None, capital_costs_per_mw={"solar": 1.0},
                lifetimes={"solar": 25.0}, discount_rate=0.05, source_record_id="p:1"),
                "success_probability": 1.0, "investment_owner_id": "owner"})
        pipeline = SchemeCPlanningPipelineDefinition()
        admitted = pipeline.admit_projects(run_for(), state, (proposal,))
        projects = admitted.next_pipeline
        for year in (2026, 2027, 2028):
            advanced = pipeline.advance_year(run_for(), YearState(year, (), projects))
            self.assertEqual((len(advanced.commissioned_projects), len(advanced.active_projects)), (0, 1), year)
            projects = advanced.active_projects
        advanced = pipeline.advance_year(run_for(), YearState(2029, (), projects))
        self.assertEqual(len(advanced.commissioned_projects), 1)


class FreezeTests(unittest.TestCase):
    def test_initial_state_freezes_the_pack_tables(self):
        from gridform_core.canonical_psm_data import native_initial_state

        state = native_initial_state(VALUE_101, 2025, scientific_parameters={})
        parameters = state.extensions["planning_parameters"]
        timelines = json.loads(pack_file(VALUE_101, "planning.timelines").read_text(encoding="utf-8"))
        self.assertEqual(parameters["schema_version"], rule.PARAMETERS_SCHEMA)
        self.assertEqual(parameters["timeline_statistic"], "median")
        self.assertEqual(parameters["development_stage_timelines"], timelines["development_stage_timelines"])
        self.assertEqual(parameters["repd_status_to_timeline"], timelines["repd_status_to_timeline"])
        self.assertEqual(parameters["success_rates"], {label: {"GB": 1.0} for label in (
            "Solar Photovoltaics", "Wind Onshore", "Wind Offshore", "Battery")})
        restored = YearState.from_dict(json.loads(json.dumps(state.to_dict())))
        self.assertEqual(restored.extensions["planning_parameters"], parameters)
        mean = native_initial_state(VALUE_101, 2025, scientific_parameters={"planning.timeline_statistic": "mean"})
        self.assertEqual(mean.extensions["planning_parameters"]["timeline_statistic"], "mean")

    def test_doctoral_initial_state_freezes_the_same_tables(self):
        from gridform_core.canonical_psm_data import native_initial_state

        corrected = native_initial_state(VALUE_101, 2025, scientific_parameters={})
        doctoral = native_initial_state(VALUE_101, 2025, scientific_parameters={}, doctoral_alignment=True)
        self.assertEqual(doctoral.extensions["planning_parameters"], corrected.extensions["planning_parameters"])

    def test_invalid_success_rows_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            for text, message in (("Technology,Region,Success_Rate\nsolar,GB,1.2\n", "not a probability"),
                                  ("Technology,Region,Success_Rate\nsolar,GB,high\n", "not a number")):
                path = Path(folder) / "success.csv"
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                    rule.freeze_planning_parameters({}, path, timeline_statistic="median")


class CatalogueAndIdentityTests(unittest.TestCase):
    def test_universal_in_both_profiles(self):
        from gridform_core import methodology

        correction = methodology.load_catalogue().corrections[CORRECTION_ID]
        self.assertEqual(correction.track, "universal")
        self.assertEqual(correction.applies_when["modules_any"], ("agent-investment",))
        for profile in (DOCTORAL_PROFILE, CORRECTED_PROFILE):
            resolved = methodology.resolve_methodology(profile)
            self.assertTrue(resolved.enabled(CORRECTION_ID), profile)
            before = [item for item in resolved.applied_correction_records() if item["id"] != CORRECTION_ID]
            self.assertNotEqual(methodology._sha256_json(before), resolved.applied_corrections_sha256, profile)

    def test_agent_investment_bump_needs_confirmation(self):
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        entry = ledger["modules"]["agent-investment"]
        bump = next(item for item in entry["bumps"] if item["package"] == "R7-1")
        self.assertEqual((bump["from"], bump["to"]), ("3.0.0", "3.1.0"))
        self.assertEqual(bump["correction_ids"], [CORRECTION_ID])
        self.assertTrue(bump["requires_user_opt_in"])
        manifest = json.loads((ROOT / "gridform_core" / "manifests" / "agent-investment.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], entry["current_version"])
        self.assertEqual(SchemeCAgentInvestmentDefinition.version, entry["current_version"])
        kind, _ = revision_migration._module_change_kind("agent-investment", "3.0.0", "3.1.0")
        self.assertEqual(kind, "method_upgrade_required")

    def test_cem_identity_names_the_rule(self):
        from gridform_core.cem_identity import load_cem_identity

        identity = load_cem_identity()
        self.assertEqual(identity["version"], "2026.10.09")
        stage = next(item for item in identity["decision_stages"] if item["stage"] == "planning_success")
        self.assertIn(CORRECTION_ID, stage["typed_rule"])


if __name__ == "__main__":
    unittest.main()
