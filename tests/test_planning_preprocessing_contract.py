import json
import math
import unittest
from pathlib import Path

from gridform_core.parameters import PARAMETERS, resolve_scheme_c_parameters
from gridform_core.canonical_psm_data import native_initial_state


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction"
CONTRACT = ROOT / "gridform_core" / "data" / "cem" / "planning_preprocessing_contract.json"
MANIFEST = ROOT / "gridform_core" / "manifests" / "planning-pipeline.json"


class PlanningPreprocessingContractTests(unittest.TestCase):
    def test_contract_and_pipeline_jointly_own_every_planning_parameter(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        adapter_parameters = set(contract["parameters"])
        annual_parameters = set(contract["annual_pipeline_parameters"])
        registry_parameters = {
            row.id for row in PARAMETERS
            if row.id.startswith("planning.") or row.id == "fleet.repd_initial_snapshot"
        }
        self.assertEqual(adapter_parameters | annual_parameters, registry_parameters)
        self.assertFalse(adapter_parameters & annual_parameters)
        self.assertEqual(set(manifest["parameters"]), annual_parameters)
        owners = {row.id: row.module_owner for row in PARAMETERS}
        for parameter in adapter_parameters:
            self.assertEqual(owners[parameter], contract["adapter_id"])
        for parameter in annual_parameters:
            self.assertEqual(owners[parameter], "planning-pipeline")

    @unittest.skipUnless((PACK / "manifest.json").is_file(), "verified local pack is required")
    def test_resolved_settings_change_the_actual_native_prepared_state(self):
        baseline = resolve_scheme_c_parameters(
            PACK,
            {
                "planning.include_uncertain_projects": True,
                "planning.zombie_filter_enabled": False,
                "planning.defer_spread_years": 0,
            },
        )
        strict = resolve_scheme_c_parameters(
            PACK,
            {
                "planning.include_uncertain_projects": False,
                "planning.zombie_filter_enabled": True,
                "planning.minimum_project_size_mw": 1000.0,
                "planning.max_completion_year": 2028,
                "planning.defer_spread_years": 0,
            },
        )
        baseline_state = native_initial_state(
            PACK, 2025, scientific_parameters=baseline.scientific.values
        )
        strict_state = native_initial_state(
            PACK, 2025, scientific_parameters=strict.scientific.values
        )
        self.assertLess(len(strict_state.planning_projects), len(baseline_state.planning_projects))
        evidence = strict_state.extensions["planning_preprocessing"]
        self.assertEqual(evidence["contract_id"], "force-canonical-planning-input-v1")
        self.assertGreater(sum(evidence["counts"].values()), 0)
        self.assertEqual(
            evidence["parameters"]["planning.minimum_project_size_mw"], 1000.0
        )

    @unittest.skipUnless((PACK / "manifest.json").is_file(), "verified local pack is required")
    def test_mean_and_median_timeline_choices_reach_project_dates(self):
        common = {
            "planning.include_uncertain_projects": True,
            "planning.zombie_filter_enabled": False,
            "planning.defer_spread_years": 0,
        }
        median = resolve_scheme_c_parameters(
            PACK, {**common, "planning.timeline_statistic": "median"}
        )
        mean = resolve_scheme_c_parameters(
            PACK, {**common, "planning.timeline_statistic": "mean"}
        )
        median_state = native_initial_state(
            PACK, 2025, scientific_parameters=median.scientific.values
        )
        mean_state = native_initial_state(
            PACK, 2025, scientific_parameters=mean.scientific.values
        )
        median_years = {row.project_id: row.expected_completion_year for row in median_state.planning_projects}
        mean_years = {row.project_id: row.expected_completion_year for row in mean_state.planning_projects}
        common_ids = set(median_years) & set(mean_years)
        self.assertTrue(any(mean_years[key] != median_years[key] for key in common_ids))

    @unittest.skipUnless((PACK / "manifest.json").is_file(), "verified local pack is required")
    def test_untyped_repd_battery_is_typed_and_expected_economics_scale_once(self):
        resolved = resolve_scheme_c_parameters(PACK, {})
        state = native_initial_state(
            PACK, 2025, scientific_parameters=resolved.scientific.values
        )
        groups = {}
        for project in state.planning_projects:
            if project.extensions.get("repd_source_technology") != "battery":
                continue
            groups.setdefault(project.extensions["physical_project_id"], []).append(project)
        self.assertTrue(groups)
        components = next(iter(groups.values()))
        self.assertEqual(
            {row.technology for row in components},
            {"1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"},
        )
        source_declared = float(components[0].extensions["source_declared_capacity_mw"])
        probability = float(components[0].success_probability)
        self.assertTrue(math.isclose(
            sum(row.original_capacity_mw for row in components),
            source_declared,
            abs_tol=1e-9,
        ))
        self.assertTrue(math.isclose(
            sum(row.capacity_mw for row in components),
            source_declared * probability,
            abs_tol=1e-9,
        ))
        for row in components:
            duration = float(row.extensions["declared_duration_hours"])
            self.assertTrue(math.isclose(
                float(row.extensions["energy_capacity_mwh"]),
                row.capacity_mw * duration,
                abs_tol=1e-9,
            ))
            self.assertTrue(math.isclose(
                float(row.extensions["expected_economics_capacity_mw"]),
                row.capacity_mw,
                abs_tol=1e-9,
            ))
            expected_capex = (
                row.capacity_mw * float(row.extensions["capital_cost_per_mw"])
                + float(row.extensions["energy_capacity_mwh"])
                * float(row.extensions["capital_cost_per_mwh"])
            )
            self.assertTrue(math.isclose(
                float(row.extensions["total_capex_gbp"]),
                expected_capex,
                abs_tol=1e-6,
            ))

    @unittest.skipUnless((PACK / "manifest.json").is_file(), "verified local pack is required")
    def test_repd_reapplication_replacement_removes_superseded_active_row(self):
        resolved = resolve_scheme_c_parameters(PACK, {})
        state = native_initial_state(
            PACK, 2025, scientific_parameters=resolved.scientific.values
        )
        physical_ids = {
            str(project.extensions.get("physical_project_id") or project.project_id)
            for project in state.planning_projects
        }
        self.assertIn("15883", physical_ids)
        self.assertNotIn("15573", physical_ids)
        evidence = state.extensions["planning_preprocessing"]
        self.assertGreater(evidence["counts"]["excluded_superseded_reapplication"], 0)

    @unittest.skipUnless((PACK / "manifest.json").is_file(), "verified local pack is required")
    def test_seeded_storage_components_share_one_physical_project_draw(self):
        resolved = resolve_scheme_c_parameters(
            PACK, {"planning.success_mode": "seeded_stochastic", "planning.random_seed": 17}
        )
        state = native_initial_state(
            PACK, 2025, scientific_parameters=resolved.scientific.values
        )
        groups = {}
        for project in state.planning_projects:
            if project.extensions.get("repd_source_technology") == "battery":
                groups.setdefault(project.extensions["physical_project_id"], []).append(project)
        components = next(iter(groups.values()))
        self.assertEqual(len({row.random_draw for row in components}), 1)
        self.assertEqual(len({row.outcome for row in components}), 1)


if __name__ == "__main__":
    unittest.main()
