from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.cost_ledger import build_cem_cost_ledger
from gridform_core.network_contracts import (
    AssetBusMapping,
    NetworkBranch,
    NetworkBus,
    NetworkPSMInput,
    NetworkTopology,
)
from gridform_core.network_dc import ReferenceDCNetworkPSM
from gridform_core.network_expansion import (
    STATE_KEY,
    STATE_SCHEMA,
    NetworkAsset,
    NetworkCandidate,
    ReferenceTransmissionExpansion,
    adjust_carbon_ledger_for_network,
    apply_commissioned_network_assets,
    load_network_expansion_state,
    write_network_expansion_artifacts,
)
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    ExpansionHeadroom,
    InvestmentDecision,
    MarketYearResult,
    ModuleSelection,
    OperatingState,
    PSMInput,
    PlanningAdmissionResult,
    PlanningAdvanceResult,
    ResolvedRun,
    YearState,
)
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.v2.orchestrator import AnnualModelOrchestratorV2


ROOT = Path(__file__).resolve().parents[1]


def candidate(candidate_id="parallel-ab", **changes):
    values = dict(
        candidate_id=candidate_id,
        corridor_id="A-B",
        from_bus="A",
        to_bus="B",
        technology="ac_line",
        circuits_per_build=1,
        max_build_circuits=1,
        thermal_rating_mw_per_circuit=6.0,
        apparent_power_rating_mva_per_circuit=6.0,
        resistance_pu=0.01,
        reactance_pu=0.06666666666666667,
        charging_susceptance_pu=0.0,
        tap_ratio=None,
        phase_shift_degrees=0.0,
        owner_id="regulated-owner",
        planner_id="central-planner",
        total_capex_gbp_per_build=100.0,
        annual_fixed_opex_gbp_per_build=10.0,
        construction_life_years=1.0,
        economic_life_years=10.0,
        discount_rate=0.05,
        lead_time_years=1,
        success_probability=1.0,
        budget_group="GB-transmission",
        trigger_branch_ids=("AB",),
        trigger_branch_rating_mw=4.0,
        minimum_trigger_utilisation=0.9,
        declared_annual_benefit_gbp=100.0,
        minimum_benefit_cost_ratio=1.0,
        earliest_decision_year=2025,
        embodied_carbon_factor_tco2e_per_mw=2.0,
        embodied_carbon_allocation="commissioning_year_once",
        embodied_carbon_source={"record_id": "fixture-network-factor", "source": "test"},
        provenance={"fixture": "prompt70"},
    )
    values.update(changes)
    return NetworkCandidate(**values)


def state_with_candidates(*candidates, year=2025, assets=(), projects=()):
    return YearState(
        year, (), (),
        extensions={STATE_KEY: {
            "owner": "value-network-expansion-extension",
            "schema_version": STATE_SCHEMA,
            "candidates": [item.to_dict() for item in candidates],
            "assets": [item.to_dict() for item in assets],
            "projects": [item.to_dict() for item in projects],
            "events": [],
        }},
    )


def resolved_run(end_year=2026, *, budget=1000.0):
    selected = {
        "pipeline": ("pipeline-spy", "1.0", "value.planning/v2"),
        "psm": ("value-reference-dc-network", "1.0.0", "value.psm/v2"),
        "vre_cap": ("vre-spy", "1.0", "value.expansion-policy/v2"),
        "storage_cap": ("storage-spy", "1.0", "value.expansion-policy/v2"),
        "investment": ("investment-spy", "1.0", "value.investment/v2"),
        "transition": ("transition-spy", "1.0", "value.state-transition/v2"),
        "network_expansion": (
            "reference-transmission-expansion", "1.0.0",
            "value.network-expansion/v1",
        ),
    }
    return ResolvedRun(
        "prompt70", "prompt70-project", "network-test", "network-fixture",
        2025, end_year,
        {
            slot: ModuleSelection(slot, module, version, contract)
            for slot, (module, version, contract) in selected.items()
        },
        {
            "clock.period_hours": 1.0,
            "network.expansion.annual_budget_gbp": budget,
            "network.expansion.group_budget_gbp": budget,
            "network.expansion.random_seed": 0,
        },
        {},
    )


class Pipeline:
    id, version = "pipeline-spy", "1.0"

    def advance_year(self, run, state):
        operating = OperatingState(
            state.year, state.assets, state.planning_projects,
            extensions=dict(state.extensions),
        )
        return PlanningAdvanceResult(state.year, operating, (), (), (), (), ())

    def admit_projects(self, run, state, proposals):
        return PlanningAdmissionResult(state.year, (), (), (), ())


class Cap:
    version = "1.0"

    def __init__(self, slot):
        self.id = f"{slot.split('_')[0]}-spy"

    def evaluate(self, run, state, market):
        return ExpansionHeadroom(f"{self.id}:{state.year}", state.year, self.id, {})


class Investment:
    id, version = "investment-spy", "1.0"

    def decide(self, run, state, market, headroom):
        return InvestmentDecision(f"investment:{state.year}", state.year, self.id, (), {})


class Transition:
    id, version = "transition-spy", "1.0"

    def apply(self, run, current_state, planning, investment):
        return YearState(
            current_state.year + 1,
            current_state.assets,
            planning.next_pipeline,
            extensions=dict(current_state.extensions),
        )


def network_input(state: OperatingState, seen: dict[int, tuple[str, ...]]):
    chronology = ChronologicalPSMData(
        (f"{state.year}:p0",), (10.0,),
        (
            DispatchResource("cheap", "ccgt", "thermal", 20.0, 10.0, (1.0,)),
            DispatchResource("local", "ocgt", "thermal", 20.0, 100.0, (1.0,)),
        ),
        (), 10_000.0,
    )
    topology = NetworkTopology(
        (
            NetworkBus("A", 400.0, "A", reference_eligible=True, is_reference=True),
            NetworkBus("B", 400.0, "B"),
        ),
        (NetworkBranch("AB", "A", "B", "ac_line", True, 4.0, reactance_pu=0.1),),
        (
            AssetBusMapping("cheap", "A", "generator"),
            AssetBusMapping("local", "B", "generator"),
        ),
        100.0,
    )
    network = NetworkPSMInput(
        "prompt70", state.year, 1.0, chronology, topology,
        {"A": (0.0,), "B": (10.0,)},
        "domain.network.dc", "chronological_perfect_foresight",
    )
    network = apply_commissioned_network_assets(network, state)
    seen[state.year] = tuple(item.branch_id for item in network.topology.branches)
    return PSMInput(
        "prompt70", state.year, "network-fixture", state, 1.0, {},
        chronology=chronology, extensions={"network_input": network.to_dict()},
    )


def run_two_years(initial, *, budget=1000.0):
    seen = {}
    expansion = ReferenceTransmissionExpansion()
    orchestrator = AnnualModelOrchestratorV2(
        ReferenceDCNetworkPSM(),
        {"vre_cap": Cap("vre_cap"), "storage_cap": Cap("storage_cap")},
        Investment(), Pipeline(), Transition(),
        psm_input_factory=lambda run, state: network_input(state, seen),
        network_expansion=expansion,
    )
    return orchestrator.run(resolved_run(budget=budget), initial), seen


class Prompt70NetworkExpansionTests(unittest.TestCase):
    def test_causal_two_year_commissioning_changes_actual_dc_clearing(self):
        results, seen = run_two_years(state_with_candidates(candidate()))
        self.assertEqual(seen[2025], ("AB",))
        self.assertEqual(len(seen[2026]), 2)
        new_branch = next(item for item in seen[2026] if item != "AB")
        self.assertTrue(new_branch.startswith("network:network-project:"))
        self.assertAlmostEqual(results[0].market.generation_mwh_by_asset["cheap"], 4.0)
        self.assertAlmostEqual(results[0].market.generation_mwh_by_asset["local"], 6.0)
        self.assertAlmostEqual(results[1].market.generation_mwh_by_asset["cheap"], 10.0)
        self.assertAlmostEqual(results[1].market.generation_mwh_by_asset["local"], 0.0)
        first = results[0].extensions["network_expansion"]
        second = results[1].extensions["network_expansion"]
        self.assertEqual(len(first["decision"]["proposals"]), 1)
        self.assertEqual(len(first["admission"]["admitted_projects"]), 1)
        self.assertEqual(len(second["advance"]["commissioned_assets"]), 1)
        period = results[1].market.extensions["network"]["periods"][0]
        self.assertIn(new_branch, period["branch_flow_mw"])

    def test_economic_identity_cost_and_carbon_reconcile(self):
        results, _ = run_two_years(state_with_candidates(candidate()))
        asset = NetworkAsset.from_dict(
            results[1].planning_advance.operating_state.extensions[STATE_KEY]["assets"][0]
        )
        self.assertEqual(asset.total_capex_gbp, 100.0)
        self.assertEqual(asset.annual_fixed_opex_gbp, 10.0)
        self.assertEqual(asset.economic_life_years, 10.0)
        self.assertEqual(asset.owner_id, "regulated-owner")
        self.assertGreater(asset.annualized_capex_gbp, 0.0)
        ledger = build_cem_cost_ledger(results[1].market)
        network_lines = {
            line.id: line.amount_gbp for line in ledger.lines if line.id.startswith("network.")
        }
        self.assertAlmostEqual(
            network_lines["network.commissioned_assets.annualised_capex"],
            asset.annualized_capex_gbp,
        )
        self.assertAlmostEqual(network_lines["network.commissioned_assets.fixed_opex"], 10.0)
        self.assertAlmostEqual(ledger.physical_reconciliation_residual_gbp, 0.0)
        base = {
            "status": "reconciled", "total_carbon_emissions_tco2e": 100.0,
            "components_tco2e": {}, "unresolved_activities": [], "lines": [],
            "intensities": {"denominator_mwh": 10.0, "overall_kgco2e_per_mwh": 10_000.0},
        }
        carbon = adjust_carbon_ledger_for_network(
            base, year=2026, state=results[1].planning_advance.operating_state
        )
        self.assertAlmostEqual(carbon["components_tco2e"]["network_construction_embodied"], 12.0)
        self.assertAlmostEqual(carbon["total_carbon_emissions_tco2e"], 112.0)

    def test_failure_delay_budget_endpoint_duplicate_and_retirement_gates(self):
        failed, seen = run_two_years(
            state_with_candidates(candidate(success_probability=0.0))
        )
        self.assertEqual(seen[2026], ("AB",))
        self.assertEqual(len(failed[0].extensions["network_expansion"]["admission"]["failed_proposals"]), 1)
        delayed = candidate(delay_years=1)
        results, seen = run_two_years(state_with_candidates(delayed))
        self.assertEqual(seen[2026], ("AB",))
        over_budget, _ = run_two_years(state_with_candidates(candidate()), budget=50.0)
        self.assertEqual(over_budget[0].extensions["network_expansion"]["decision"]["proposals"], [])
        bad = candidate(to_bus="C")
        with self.assertRaisesRegex(ValueError, "invalid endpoint"):
            run_two_years(state_with_candidates(bad))
        commissioned = NetworkAsset.from_dict(
            run_two_years(state_with_candidates(candidate()))[0][1]
            .planning_advance.operating_state.extensions[STATE_KEY]["assets"][0]
        )
        duplicate_state = OperatingState(
            2026, (), (),
            extensions={STATE_KEY: {
                "owner": "value-network-expansion-extension",
                "schema_version": STATE_SCHEMA, "candidates": [],
                "projects": [], "events": [],
                "assets": [commissioned.to_dict(), commissioned.to_dict()],
            }},
        )
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            network_input(duplicate_state, {})
        retired = replace(commissioned, retirement_year=2026)
        advance = ReferenceTransmissionExpansion().advance_year(
            resolved_run(), state_with_candidates(candidate(), year=2026, assets=(retired,))
        )
        retired_asset = NetworkAsset.from_dict(advance.state.extensions[STATE_KEY]["assets"][0])
        self.assertEqual(retired_asset.status, "retired")
        self.assertEqual(ReferenceTransmissionExpansion().annual_resource_costs(advance.state)["annualized_capex_gbp"], 0.0)

    def test_shared_budget_not_multiplied_and_artifacts_are_queryable(self):
        second = candidate(
            "parallel-ab-2", corridor_id="A-B-2", total_capex_gbp_per_build=60.0,
            annual_fixed_opex_gbp_per_build=5.0,
        )
        first = candidate(total_capex_gbp_per_build=60.0)
        results, _ = run_two_years(state_with_candidates(first, second), budget=100.0)
        decision = results[0].extensions["network_expansion"]["decision"]
        self.assertEqual(len(decision["proposals"]), 1)
        self.assertAlmostEqual(decision["committed_budget_gbp"], 60.0)
        with tempfile.TemporaryDirectory(prefix="force-p70-ledger-") as temporary:
            json_path, sqlite_path = write_network_expansion_artifacts(Path(temporary), results)
            self.assertTrue(json_path.is_file())
            self.assertTrue(sqlite_path.is_file())

    def test_pack_adapter_and_registry_are_real_not_catalog_only(self):
        with tempfile.TemporaryDirectory(prefix="force-p70-pack-") as temporary:
            root = Path(temporary)
            (root / "candidates.json").write_text(
                json.dumps({"candidates": [candidate().to_dict()]}), encoding="utf-8"
            )
            manifest = {"bindings": {
                "value.network.expansion.candidates": {"uri": "candidates.json"}
            }}
            state = load_network_expansion_state(root, manifest, YearState(2025, (), ()))
            self.assertEqual(len(state.extensions[STATE_KEY]["candidates"]), 1)
        registry = workspace_registry(ROOT / "missing-local-modules")
        modules = {
            "psm": "value-reference-dc-network",
            "network_expansion": "reference-transmission-expansion",
            "investment": "agent-investment", "pipeline": "planning-pipeline",
            "vre_cap": "vre-expansion-cap", "storage_cap": "value-storage-expansion-policy",
            "transition": "value-annual-state-transition",
        }
        roles = (
            "value.network.buses", "value.network.branches", "value.network.asset-map",
            "value.network.nodal-demand", "value.network.expansion.candidates",
        )
        graph = registry.resolve_selection(
            modules,
            selected_extensions=(
                "value-network-contract-extension", "value-network-expansion-extension",
            ),
            available_data_roles=roles,
        )
        self.assertIsInstance(
            graph.implementation("network_expansion"), ReferenceTransmissionExpansion
        )


if __name__ == "__main__":
    unittest.main()
