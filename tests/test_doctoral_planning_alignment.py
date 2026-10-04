"""Source-isolated REPD regressions; never import the doctoral main program."""
from __future__ import annotations

import ast
import builtins
import contextlib
import copy
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import random
from types import SimpleNamespace
import unittest

from dateutil.relativedelta import relativedelta
import pandas as pd

from gridform_core.builtin.scheme_c_1000twh import doctoral_planning as candidate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/doctoral_alignment/planning.json").read_text(encoding="utf-8"))


def context(**overrides):
    result = copy.deepcopy(FIXTURE["context"])
    result.update(overrides)
    return result


def source_reference(settings=None, rows=None):
    """Compile the selected original functions; top-level imports/main never run.

    Only file reading and the location-module import are redirected to frozen
    inputs and an independently compiled original location function. No math,
    branching, success, timeline, or filtering statements are rewritten.
    """
    settings = context() if settings is None else settings
    source_root = Path(FIXTURE["source_root"])
    if not source_root.is_dir():
        raise unittest.SkipTest("Frozen original source is unavailable; source oracle not evaluated")
    for name, sha256 in FIXTURE["source_sha256"].items():
        actual = hashlib.sha256((source_root / name).read_bytes()).hexdigest()
        if actual != sha256:
            raise AssertionError(f"Original source identity changed: {name}")
    config_tree = ast.parse((source_root / "config.py").read_text(encoding="utf-8-sig"))
    config = {}
    for node in config_tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {"repd_filtering", "repd_status_to_timeline", "development_stage_timelines"}:
            config[node.targets[0].id] = ast.literal_eval(node.value)
    for key in ("repd_status_to_timeline", "development_stage_timelines"):
        if settings[key] != config[key]:
            raise AssertionError(f"Fixture changed the source's frozen table: {key}")
    config["repd_filtering"].update({
        "apply_zombie_filter": settings["zombie_filter_enabled"],
        "include_uncertain_projects": settings["include_uncertain_projects"],
        "minimum_project_size_mw": settings["minimum_project_size_mw"],
        "max_completion_year": settings["max_completion_year"],
    })
    environment = {
        "START_YEAR": str(settings["start_year"]),
        "PLANNING_USE_MEDIAN": "1" if settings["timeline_statistic"] == "median" else "0",
        "APPLY_REPD_INITIAL_SNAPSHOT": "1" if settings["apply_repd_initial_snapshot"] else "0",
        "REPD_ZOMBIE_STATUS_STALE_YEAR": str(settings["zombie_status_stale_year"]),
        "REPD_ZOMBIE_SNAPSHOT_YEAR": str(settings["zombie_snapshot_year"]),
        "REPD_ZOMBIE_CONSTRUCTION_GRACE_YEARS": str(settings["construction_grace_years"]),
        "PIPELINE_DEFER_SPREAD_YEARS": str(settings["defer_spread_years"]),
        "MODEL_SUCCESS_MODE": "lottery" if settings["success_mode"] == "seeded_stochastic" else "expected",
    }
    location_namespace = {"pd": pd}
    location_tree = ast.parse((source_root / "map_projects_to_generators_by_location.py").read_text(encoding="utf-8-sig"))
    location_def = next(node for node in location_tree.body if isinstance(node, ast.FunctionDef) and node.name == "extract_location_from_repd")
    exec(compile(ast.Module(body=[location_def], type_ignores=[]), "isolated-original-location", "exec"), location_namespace)
    location_module = SimpleNamespace(extract_location_from_repd=location_namespace["extract_location_from_repd"])

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "map_projects_to_generators_by_location":
            return location_module
        if name == "re":
            return builtins.__import__(name, globals, locals, fromlist, level)
        raise AssertionError(f"Unexpected source-oracle import: {name}")

    def frozen_csv(path, **kwargs):
        if path != "repd-q2-jul-2025.csv" or rows is None:
            raise AssertionError("Unexpected source-oracle data read")
        return pd.DataFrame(copy.deepcopy(rows))

    namespace = {"hashlib": hashlib, "datetime": datetime, "relativedelta": relativedelta,
                 "random": random.Random(42), "os": SimpleNamespace(getenv=lambda name, default="": environment.get(name, default)),
                 "config": SimpleNamespace(**config), "pd": SimpleNamespace(read_csv=frozen_csv, to_datetime=pd.to_datetime, isna=pd.isna, notna=pd.notna, to_numeric=pd.to_numeric),
                 "__builtins__": dict(vars(builtins), __import__=guarded_import)}
    names = {"_stable_int_hash", "get_asset_type_from_repd", "_planning_use_median", "_map_repd_tech_type", "_timeline_months_for_type", "completion_year_from_months", "deterministic_success_draw", "_model_success_mode", "_lookup_regional_success_rate", "_tech_label_for_success_rate", "_resolve_model_success_capacity", "calculate_development_timeline", "_pipeline_earliest_completion_year", "_estimate_repd_historical_completion_year", "estimate_repd_completion_year", "_repd_zombie_status_stale_year", "_repd_zombie_snapshot_year", "_repd_last_status_progress_year", "_repd_row_is_operational", "is_status_stagnant_repd_zombie", "_repd_zombie_schedule_deadline_year", "is_schedule_overdue_repd_zombie", "_parse_repd_year", "defer_start_year_external_pipeline_completions", "load_external_projects", "apply_success_rates_to_repd_projects"}
    tree = ast.parse((source_root / "run_investment_analysis.py").read_text(encoding="utf-8-sig"))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    selected += [node for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_REPD_STATUS_PROGRESS_COLUMNS"]
    if len(selected) != len(names) + 1:
        raise AssertionError("Incomplete original planning function closure")
    exec(compile(ast.Module(body=selected, type_ignores=[]), "isolated-original-planning", "exec"), namespace)
    return namespace


class PlanningProbabilityTests(unittest.TestCase):
    def test_granted_capacity_is_not_reduced_by_uncertain_success_rate(self):
        row = FIXTURE["rows"][0]
        result = candidate.preprocess_doctoral_projects([row], context())
        self.assertEqual(result[0].capacity_mw, 100.0)
        self.assertFalse(result[0].extensions["success_rate_applied"])

    def test_missing_region_uses_technology_mean(self):
        row = copy.deepcopy(FIXTURE["rows"][1])
        row["Region"] = "Wales"
        result = candidate.preprocess_doctoral_projects([row], context())
        self.assertEqual(result[0].capacity_mw, 50.0)

    def test_submitted_capacity_and_missing_technology_fallback(self):
        row = copy.deepcopy(FIXTURE["rows"][1])
        self.assertEqual(candidate.preprocess_doctoral_projects([row], context())[0].capacity_mw, 60.0)
        row["Technology Type"] = "Wind Onshore"
        self.assertEqual(candidate.preprocess_doctoral_projects([row], context())[0].capacity_mw, 75.0)

    def test_canonical_rate_keys_use_mean_including_gb_not_gb_override(self):
        rates = {("solar", "england"): 0.2, ("solar", "scotland"): 0.6, ("solar", "gb"): 1.0}
        self.assertAlmostEqual(candidate.lookup_regional_success_rate(rates, "solar", "Wales"), 0.6)

    def test_status_switch_comes_from_frozen_table(self):
        settings = context()
        settings["repd_status_to_timeline"]["Planning Permission Granted"]["apply_success_rate"] = True
        self.assertEqual(candidate.preprocess_doctoral_projects([FIXTURE["rows"][0]], settings)[0].capacity_mw, 60.0)

    def test_zero_success_retains_failed_record_without_positive_capacity(self):
        settings = context(success_rates={"Solar Photovoltaics": {"England": 0.0}})
        result = candidate.preprocess_doctoral_projects([FIXTURE["rows"][1]], settings)[0]
        self.assertEqual((result.capacity_mw, result.status, result.outcome), (0.0, "failed", "failed_planning"))

    def test_invalid_success_rate_fails_before_silent_clamping(self):
        with self.assertRaisesRegex(ValueError, "Invalid REPD success rate"):
            candidate.preprocess_doctoral_projects([FIXTURE["rows"][1]], context(success_rates={"Solar Photovoltaics": {"England": 2.0}}))

    def test_lottery_matches_actual_source_and_ignores_unrelated_seed(self):
        settings = context(success_mode="seeded_stochastic")
        reference = source_reference(settings)
        before_rng = random.getstate()
        got = candidate.preprocess_doctoral_projects(FIXTURE["rows"], settings)
        raw = [{"name": row["Site Name"], "technology_type": "solar", "region": row["Region"], "development_status": row["Development Status (short)"], "capacity": 100.0} for row in FIXTURE["rows"]]
        expected = reference["apply_success_rates_to_repd_projects"](raw, settings["success_rates"])
        for project, original in zip(got, expected):
            self.assertEqual(project.capacity_mw, original["capacity"])
            self.assertEqual(project.random_draw, original.get("random_draw"))
        self.assertEqual(random.getstate(), before_rng)
        reversed_result = candidate.preprocess_doctoral_projects(list(reversed(FIXTURE["rows"])), dict(settings, random_seed=999))
        self.assertEqual({p.project_id: (p.capacity_mw, p.random_draw) for p in got}, {p.project_id: (p.capacity_mw, p.random_draw) for p in reversed_result})


class PlanningTimelineTests(unittest.TestCase):
    def test_granted_timeline_includes_preconstruction_and_construction(self):
        self.assertAlmostEqual(candidate.timeline_months("Solar Photovoltaics", "Planning Permission Granted", context()), 19.7)
        self.assertAlmostEqual(candidate.timeline_months("Solar Photovoltaics", "Planning Permission Granted", context(timeline_statistic="mean")), 24.4)

    def test_month_arithmetic_uses_calendar_not_ceiling(self):
        self.assertEqual(candidate.completion_year_from_months(2025, 4.9), 2025)
        self.assertEqual(candidate.completion_year_from_months(2025, 12), 2026)
        self.assertEqual(candidate.completion_year_from_months(2025, 23.4), 2026)

    def test_milestones_and_hash_jitter_match_original_for_all_stages(self):
        row = copy.deepcopy(FIXTURE["rows"][0])
        row.update({"Planning Application Submitted": "15/06/2025", "Planning Permission  Granted": "01/02/2026", "Operational": "01/01/2039", "Under Construction": "01/01/2038"})
        for statistic in ("median", "mean"):
            settings = context(timeline_statistic=statistic)
            reference = source_reference(settings)
            for technology in ("Solar Photovoltaics", "Wind Onshore", "Wind Offshore", "Battery"):
                row["Technology Type"] = technology
                for status in settings["repd_status_to_timeline"]:
                    with self.subTest(technology=technology, status=status, statistic=statistic):
                        self.assertEqual(candidate.estimate_repd_completion_year(row, status, settings), reference["estimate_repd_completion_year"](row, status, 2025))
                        self.assertEqual(candidate.estimate_repd_completion_year(row, status, settings, historical=True), reference["_estimate_repd_historical_completion_year"](row, status, 2025))

    def test_operational_forecast_does_not_schedule_completion(self):
        row = copy.deepcopy(FIXTURE["rows"][0])
        original = candidate.estimate_repd_completion_year(row, row["Development Status (short)"], context())
        row["Operational"] = "01/01/2039"
        row["Under Construction"] = "01/01/2038"
        self.assertEqual(candidate.estimate_repd_completion_year(row, row["Development Status (short)"], context()), original)

    def test_recent_application_applies_full_pipeline_lower_bound(self):
        row = copy.deepcopy(FIXTURE["rows"][0])
        row["Development Status (short)"] = "Under Construction"
        row["Planning Permission Granted"] = "01/01/2025"
        row["Planning Application Submitted"] = "01/01/2026"
        completion = candidate.estimate_repd_completion_year(row, "Under Construction", context())
        self.assertGreaterEqual(completion, 2027)

    def test_only_start_year_external_projects_are_deferred(self):
        rows = [{"source": "external", "name": "A", "completion_year": 2025}, {"source": "external", "name": "B", "completion_year": 2026}, {"source": "model", "name": "C", "completion_year": 2025}]
        untouched = copy.deepcopy(rows)
        got = candidate.defer_start_year_external_pipeline_completions(rows, context())
        expected, count = source_reference()["defer_start_year_external_pipeline_completions"](rows, start_year=2025)
        self.assertEqual(got, tuple(expected))
        self.assertEqual(count, 1)
        self.assertEqual(rows, untouched)
        self.assertEqual(got[1:], tuple(rows[1:]))
        self.assertEqual(candidate.defer_start_year_external_pipeline_completions(rows, context(apply_repd_initial_snapshot=False)), tuple(rows))


class PlanningFilteringTests(unittest.TestCase):
    def test_old_granted_projects_are_stagnant(self):
        row = dict(FIXTURE["rows"][0], **{"Planning Permission Granted": "01/01/2010"})
        record = candidate.preprocess_doctoral_project_records([row], context())[0]
        self.assertFalse(record["retained"])
        self.assertEqual(record["reason"], "excluded_status_stagnant")

    def test_appeal_and_secretary_progress_are_included(self):
        row = dict(FIXTURE["rows"][0], **{"Planning Permission Granted": "01/01/2010", "Secretary of State - Granted": "01/01/2024"})
        stagnant, overdue = candidate.repd_zombie_flags(row, context())
        self.assertFalse(stagnant)
        self.assertTrue(overdue)

    def test_historical_past_completion_filter_survives_zombie_switch(self):
        row = dict(FIXTURE["rows"][0], **{"Planning Permission Granted": "01/01/2010"})
        record = candidate.preprocess_doctoral_project_records([row], context(zombie_filter_enabled=False))[0]
        self.assertEqual(record["reason"], "excluded_past_completion")

    def test_uncertainty_is_explicit_and_independent_of_status_success(self):
        rows = candidate.preprocess_doctoral_project_records(FIXTURE["rows"], context(include_uncertain_projects=False))
        self.assertEqual([row["reason"] for row in rows], ["included", "excluded_uncertain_status"])
        settings = context()
        del settings["include_uncertain_projects"]
        with self.assertRaisesRegex(ValueError, "Missing frozen REPD context"):
            candidate.preprocess_doctoral_projects(FIXTURE["rows"], settings)

    def test_nuclear_and_pumped_storage_do_not_enter_general_pipeline(self):
        rows = [dict(FIXTURE["rows"][0], **{"Technology Type": technology}) for technology in ("Nuclear", "Pumped Storage Hydroelectricity")]
        records = candidate.preprocess_doctoral_project_records(rows, context())
        self.assertEqual([record["reason"] for record in records], ["excluded_nuclear_policy_managed", "excluded_unsupported_technology"])
        self.assertEqual(candidate.preprocess_doctoral_projects(rows, context()), ())

    def test_invalid_capacity_and_original_rows_are_preserved_in_diagnostics(self):
        row = dict(FIXTURE["rows"][0], **{"Installed Capacity (MWelec)": "bad"})
        untouched = copy.deepcopy(row)
        record = candidate.preprocess_doctoral_project_records([row], context())[0]
        self.assertEqual(record["reason"], "excluded_invalid_capacity")
        self.assertEqual(record["source_row"], untouched)
        self.assertEqual(row, untouched)

    def test_raw_loader_decisions_match_unmodified_source_functions(self):
        base = FIXTURE["rows"][0]
        rows = copy.deepcopy(FIXTURE["rows"]) + [
            dict(base, **{"Site Name": "old", "Planning Permission Granted": "01/01/2010"}),
            dict(base, **{"Site Name": "past", "Planning Permission Granted": "01/01/2022"}),
            dict(base, **{"Site Name": "operational", "Operational": "01/01/2024"}),
            dict(base, **{"Site Name": "refused", "Development Status (short)": "Application Refused"}),
            dict(base, **{"Site Name": "unknown", "Development Status (short)": "Unrecognized"}),
            dict(base, **{"Site Name": "tiny", "Installed Capacity (MWelec)": 0.5}),
            dict(base, **{"Site Name": "far", "Planning Application Submitted": "01/01/2040"}),
            dict(base, **{"Site Name": "nuclear", "Technology Type": "Nuclear"}),
            dict(base, **{"Site Name": "pumped", "Technology Type": "Pumped Storage Hydroelectricity"}),
        ]
        for uncertain in (False, True):
            for zombies in (False, True):
                with self.subTest(uncertain=uncertain, zombies=zombies):
                    settings = context(include_uncertain_projects=uncertain, zombie_filter_enabled=zombies)
                    reference = source_reference(settings, rows)
                    with contextlib.redirect_stdout(io.StringIO()):
                        raw = reference["load_external_projects"](include_uncertain_projects=uncertain, zombie_filter=zombies)
                    expected = reference["apply_success_rates_to_repd_projects"](raw, settings["success_rates"])
                    got = candidate.preprocess_doctoral_project_records(rows, settings)
                    self.assertEqual([(r["name"], r["technology"], r["capacity_mw"], r["completion_year"], r["development_status"]) for r in got if r["retained"]], [(r["name"], r["technology_type"], r["capacity"], r["completion_year"], r["development_status"]) for r in expected])


if __name__ == "__main__":
    unittest.main()
