import importlib
import json
import os
import unittest
from pathlib import Path

from gridform_core.asset_economics import build_asset_economic_extensions
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import (
    SchemeCPlanningPipelineDefinition,
    SchemeCStateTransitionDefinition,
)
from gridform_core.canonical_psm_data import build_chronology, native_initial_state
from gridform_core.data_method import run_policy
from gridform_core.spatialization import allocations_for_state
from gridform_core.v2.contracts import (
    AssetStateV2,
    InvestmentDecision,
    PlanningAdmissionResult,
    OperatingState,
    ResolvedRun,
    YearState,
)
from gridform_core.zonal_contracts import ZonalAssetMapping


OPEN_VALUE_UK_PACK = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "VALUE"
    / "state"
    / "data-packs"
    / "value-uk-open-data-pack-v1"
)


class ValueUkNuclearPolicyTests(unittest.TestCase):
    def test_policy_applies_to_value_uk_open_pack_not_doctoral_reproduction(self):
        policy_module = importlib.import_module("gridform_core.nuclear_policy")

        self.assertTrue(
            policy_module.applies_to_data_pack({"id": "value-uk-open-data-pack-v1"})
        )
        self.assertFalse(
            policy_module.applies_to_data_pack(
                {"id": "value-uk-1000twh-reproduction"}
            )
        )

    def test_edf_station_capacities_sum_to_5958_mw_without_rescaling(self):
        policy_module = importlib.import_module("gridform_core.nuclear_policy")

        policy = policy_module.load_value_uk_nuclear_policy()
        capacities = {
            row["station_id"]: row["capacity_mw"]
            for row in policy["existing_stations"]
        }

        self.assertEqual(
            capacities,
            {
                "heysham-1": 1155.0,
                "hartlepool": 1185.0,
                "heysham-2": 1230.0,
                "torness": 1190.0,
                "sizewell-b": 1198.0,
            },
        )
        self.assertEqual(sum(capacities.values()), 5958.0)
        self.assertEqual(policy["declared_existing_capacity_mw"], 5958.0)

    def test_declared_retirements_and_nuclear_pipeline_are_explicit(self):
        policy_module = importlib.import_module("gridform_core.nuclear_policy")
        policy = policy_module.load_value_uk_nuclear_policy()

        unavailable = {
            row["station_id"]: row["model_unavailable_from_year"]
            for row in policy["existing_stations"]
        }
        planned = {
            row["project_id"]: (
                row["capacity_mw"],
                row["expected_first_generation_year"],
                row["model_first_full_operating_year"],
            )
            for row in policy["planned_projects"]
        }

        self.assertEqual(
            unavailable,
            {
                "heysham-1": 2031,
                "hartlepool": 2031,
                "heysham-2": 2031,
                "torness": 2031,
                "sizewell-b": 2056,
            },
        )
        self.assertEqual(
            planned,
            {
                "hinkley-point-c-unit-1": (1630.0, 2030, 2031),
                "hinkley-point-c-unit-2": (1630.0, 2031, 2032),
                "sizewell-c": (3200.0, None, 2035),
            },
        )
        self.assertFalse(policy["endogenous_investment_allowed"])

    def test_sizewell_c_stays_in_pipeline_without_commissioning_by_2034(self):
        policy_module = importlib.import_module("gridform_core.nuclear_policy")
        policy = policy_module.load_value_uk_nuclear_policy()
        declared = {
            row["project_id"]: row for row in policy["planned_projects"]
        }

        self.assertIn("sizewell-c", declared)
        self.assertEqual(declared["sizewell-c"]["capacity_mw"], 3200.0)
        self.assertEqual(
            declared["sizewell-c"]["model_treatment"],
            "retain_in_pipeline_beyond_model_horizon",
        )
        projects = policy_module.build_value_uk_nuclear_projects(
            start_year=2025,
            end_year=2034,
            capital_discount_rate=0.05,
        )
        sizewell = next(row for row in projects if row.project_id == "sizewell-c")
        run = ResolvedRun("run", "project", "scenario", "pack", 2025, 2034, {}, {}, {})

        at_horizon = SchemeCPlanningPipelineDefinition().advance_year(
            run,
            YearState(2034, (), (sizewell,)),
        ).operating_state

        self.assertEqual(sizewell.expected_completion_year, 2035)
        self.assertEqual(sizewell.capacity_mw, 3200.0)
        self.assertFalse(sizewell.extensions["investment_eligible"])
        self.assertEqual(at_horizon.assets, ())
        self.assertEqual(
            [row.project_id for row in at_horizon.active_planning_projects],
            ["sizewell-c"],
        )

    def test_asset_specs_follow_station_retirement_schedule(self):
        policy_module = importlib.import_module("gridform_core.nuclear_policy")

        initial = policy_module.existing_nuclear_asset_specs(2025)
        after_agr_retirement = policy_module.existing_nuclear_asset_specs(2031)

        self.assertEqual(
            {row["asset_id"] for row in initial},
            {
                "nuclear:heysham-1",
                "nuclear:hartlepool",
                "nuclear:heysham-2",
                "nuclear:torness",
                "nuclear:sizewell-b",
            },
        )
        self.assertEqual(sum(row["capacity_mw"] for row in initial), 5958.0)
        self.assertEqual(
            [(row["asset_id"], row["capacity_mw"]) for row in after_agr_retirement],
            [("nuclear:sizewell-b", 1198.0)],
        )

    def test_declared_nuclear_projects_are_exogenous_with_separate_cost_evidence(self):
        policy_module = importlib.import_module("gridform_core.nuclear_policy")

        projects = policy_module.build_value_uk_nuclear_projects(
            start_year=2025,
            end_year=2034,
            capital_discount_rate=0.05,
        )

        self.assertEqual(
            [(row.project_id, row.expected_completion_year, row.capacity_mw) for row in projects],
            [
                ("hinkley-point-c-unit-1", 2031, 1630.0),
                ("hinkley-point-c-unit-2", 2032, 1630.0),
                ("sizewell-c", 2035, 3200.0),
            ],
        )
        for project in projects:
            self.assertEqual(project.source, "declared_external_nuclear_plan")
            self.assertFalse(project.extensions["investment_eligible"])
            self.assertFalse(project.extensions["primary_cost_ledger_included"])
        by_id = {row.project_id: row for row in projects}
        self.assertEqual(by_id["hinkley-point-c-unit-1"].extensions["cost_price_year"], 2015)
        self.assertEqual(
            by_id["hinkley-point-c-unit-1"].extensions["total_capex_gbp"],
            17_500_000_000.0,
        )
        self.assertEqual(by_id["sizewell-c"].extensions["cost_price_year"], 2024)
        self.assertEqual(
            by_id["sizewell-c"].extensions["total_capex_gbp"],
            38_000_000_000.0,
        )

    @unittest.skipUnless(
        (OPEN_VALUE_UK_PACK / "manifest.json").is_file(),
        "installed VALUE-UK open data pack is required",
    )
    def test_canonical_value_uk_state_consumes_station_fleet_and_declared_pipeline(self):
        state = native_initial_state(OPEN_VALUE_UK_PACK, 2025)

        nuclear_assets = [row for row in state.assets if row.technology == "Nuclear"]
        nuclear_projects = [
            row for row in state.planning_projects if row.technology == "Nuclear"
        ]

        self.assertEqual(len(nuclear_assets), 5)
        self.assertEqual(sum(row.capacity_mw for row in nuclear_assets), 5958.0)
        self.assertEqual(
            {row.asset_id for row in nuclear_assets},
            {
                "nuclear:heysham-1",
                "nuclear:hartlepool",
                "nuclear:heysham-2",
                "nuclear:torness",
                "nuclear:sizewell-b",
            },
        )
        self.assertEqual(
            {row.project_id for row in nuclear_projects},
            {"hinkley-point-c-unit-1", "hinkley-point-c-unit-2", "sizewell-c"},
        )
        self.assertTrue(
            all(
                row.extensions["spatial_mapping_asset_id"] == "Nuclear"
                for row in (*nuclear_assets, *nuclear_projects)
            )
        )
        sizewell = next(
            row for row in state.planning_projects if row.project_id == "sizewell-c"
        )
        self.assertEqual(sizewell.expected_completion_year, 2035)
        self.assertEqual(sizewell.extensions["model_treatment"], "retain_in_pipeline_beyond_model_horizon")
        self.assertEqual(
            state.extensions["nuclear_policy"],
            {
                "schema_version": "value.uk-nuclear-policy/v1",
                "policy_id": "value-uk-nuclear-exogenous-fleet-v1",
                "version": "2026.08.31",
                "declared_existing_capacity_mw": 5958.0,
                "endogenous_investment_allowed": False,
            },
        )

    def test_transition_applies_only_the_declared_nuclear_retirement_boundary(self):
        def nuclear_asset(asset_id, capacity_mw, unavailable_from_year):
            extensions = build_asset_economic_extensions(
                "Nuclear",
                capacity_mw,
                energy_capacity_mwh=None,
                capital_costs_per_mw={"Nuclear": 80_000.0},
                lifetimes={"Nuclear": 40.0},
                discount_rate=0.05,
                source_record_id=asset_id,
            )
            extensions["model_unavailable_from_year"] = unavailable_from_year
            return AssetStateV2(
                asset_id,
                "Nuclear",
                capacity_mw,
                region="GB",
                extensions=extensions,
            )

        agr = nuclear_asset("nuclear:heysham-1", 1155.0, 2031)
        pwr = nuclear_asset("nuclear:sizewell-b", 1198.0, 2056)
        run = ResolvedRun("run", "project", "scenario", "pack", 2025, 2034, {}, {}, {})
        planning = PlanningAdmissionResult(2030, (), (), (), ())
        investment = InvestmentDecision("decision", 2030, "agent-investment", (), {})

        next_state = SchemeCStateTransitionDefinition().apply(
            run,
            YearState(2030, (agr, pwr), ()),
            planning,
            investment,
        )
        by_id = {row.asset_id: row for row in next_state.assets}

        self.assertEqual(by_id["nuclear:heysham-1"].capacity_mw, 0.0)
        self.assertEqual(by_id["nuclear:heysham-1"].status, "retired")
        self.assertEqual(
            by_id["nuclear:heysham-1"].extensions["retired_effective_year"],
            2031,
        )
        self.assertEqual(by_id["nuclear:sizewell-b"].capacity_mw, 1198.0)
        self.assertEqual(by_id["nuclear:sizewell-b"].status, "operating")

    @unittest.skipUnless(
        (OPEN_VALUE_UK_PACK / "manifest.json").is_file(),
        "installed VALUE-UK open data pack is required",
    )
    def test_dispatch_omits_retired_nuclear_but_keeps_operating_nuclear(self):
        retired = AssetStateV2(
            "nuclear:heysham-1",
            "Nuclear",
            0.0,
            region="GB",
            status="retired",
            extensions={"spatial_mapping_asset_id": "Nuclear"},
        )
        operating = AssetStateV2(
            "nuclear:sizewell-b",
            "Nuclear",
            1198.0,
            region="GB",
            status="operating",
            extensions={"spatial_mapping_asset_id": "Nuclear"},
        )
        manifest = json.loads(
            (OPEN_VALUE_UK_PACK / "manifest.json").read_text(encoding="utf-8")
        )

        chronology = build_chronology(
            OPEN_VALUE_UK_PACK,
            manifest,
            OperatingState(2031, (retired, operating), ()),
            periods=1,
            period_hours=0.5,
            data_policy=run_policy(manifest),
            terminal_soc_rule="free",
        )

        resources = {resource.asset_id: resource for resource in chronology.resources}
        self.assertNotIn("nuclear:heysham-1", resources)
        self.assertIn("nuclear:sizewell-b", resources)
        self.assertEqual(
            resources["nuclear:sizewell-b"].extensions[
                "dispatch_template_asset_id"
            ],
            "Nuclear",
        )

    def test_primary_costs_exclude_only_unnormalised_exogenous_project_evidence(self):
        economics_module = importlib.import_module("gridform_core.asset_economics")
        policy_module = importlib.import_module("gridform_core.nuclear_policy")
        project = policy_module.build_value_uk_nuclear_projects(
            start_year=2025,
            end_year=2034,
            capital_discount_rate=0.05,
        )[0]
        run = ResolvedRun("run", "project", "scenario", "pack", 2025, 2034, {}, {}, {})
        commissioned = SchemeCPlanningPipelineDefinition().advance_year(
            run,
            YearState(2031, (), (project,)),
        ).operating_state.assets[0]
        ordinary_extensions = build_asset_economic_extensions(
            "Nuclear",
            100.0,
            energy_capacity_mwh=None,
            capital_costs_per_mw={"Nuclear": 80_000.0},
            lifetimes={"Nuclear": 40.0},
            discount_rate=0.05,
            source_record_id="ordinary",
        )
        ordinary = AssetStateV2(
            "ordinary",
            "Nuclear",
            100.0,
            extensions=ordinary_extensions,
        )

        self.assertEqual(economics_module.primary_annual_asset_costs(commissioned), (0.0, 0.0))
        self.assertEqual(
            economics_module.primary_annual_asset_costs(ordinary),
            (
                ordinary.extensions["annualized_capital_cost_gbp"],
                ordinary.extensions["annual_fixed_opex_gbp"],
            ),
        )

    def test_capacity_ledger_reconciles_annual_commissioning_and_retirement(self):
        policy_module = importlib.import_module("gridform_core.nuclear_policy")

        ledger = policy_module.nuclear_capacity_trajectory(2025, 2034)

        self.assertEqual(
            [
                (
                    row["model_year"],
                    row["annual_commissioning_mw"],
                    row["annual_retirements_mw"],
                    row["total_nuclear_capacity_mw"],
                )
                for row in ledger
            ],
            [
                (2025, 0.0, 0.0, 5958.0),
                (2026, 0.0, 0.0, 5958.0),
                (2027, 0.0, 0.0, 5958.0),
                (2028, 0.0, 0.0, 5958.0),
                (2029, 0.0, 0.0, 5958.0),
                (2030, 0.0, 0.0, 5958.0),
                (2031, 1630.0, 4760.0, 2828.0),
                (2032, 1630.0, 0.0, 4458.0),
                (2033, 0.0, 0.0, 4458.0),
                (2034, 0.0, 0.0, 4458.0),
            ],
        )
        self.assertEqual(ledger[-1]["cumulative_commissioning_mw"], 3260.0)
        self.assertEqual(ledger[-1]["cumulative_retirements_mw"], 4760.0)
        self.assertEqual(ledger[-1]["net_change_from_2025_mw"], -1500.0)

    def test_spatial_mapping_override_preserves_aggregate_nuclear_zonal_key(self):
        asset = AssetStateV2(
            "nuclear:heysham-1",
            "Nuclear",
            1155.0,
            region="GB",
            extensions={
                "investment_eligible": False,
                "spatial_mapping_asset_id": "Nuclear",
            },
        )

        rows = allocations_for_state(
            YearState(2025, (asset,), ()),
            (
                ZonalAssetMapping(
                    "Nuclear",
                    "ENGLAND_FALLBACK",
                    "generator",
                    "nuclear",
                    1.0,
                    "unlocated_england_fallback",
                ),
            ),
            pack_revision="network-revision",
        )

        self.assertEqual(
            [(row.source_id, row.zone_id, row.capacity_mw) for row in rows],
            [("nuclear:heysham-1", "ENGLAND_FALLBACK", 1155.0)],
        )
        self.assertEqual(rows[0].provenance["mapping_identity"], "Nuclear")


if __name__ == "__main__":
    unittest.main()
