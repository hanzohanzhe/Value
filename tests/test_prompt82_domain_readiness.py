from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.domain_readiness import (
    build_domain_readiness,
    summarise_expansion_input,
    summarise_hydrology_input,
    summarise_network_input,
)
from gridform_core.hydrology import load_hydrology_inputs_from_pack
from gridform_core.network_contracts import (
    AssetBusMapping,
    NetworkBranch,
    NetworkBus,
    NetworkPSMInput,
    NetworkTopology,
)
from gridform_core.network_expansion import NetworkCandidate
from gridform_core.v2.contracts import ChronologicalPSMData, DispatchResource
from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"


def network_input() -> NetworkPSMInput:
    chronology = ChronologicalPSMData(
        ("2025:0", "2025:1"), (10.0, 12.0),
        (DispatchResource("g", "ccgt", "thermal", 20.0, 10.0, (1.0,)),),
        (), 10_000.0,
    )
    topology = NetworkTopology(
        (
            NetworkBus("A", 400.0, "A", True, True),
            NetworkBus("B", 275.0, "B"),
        ),
        (NetworkBranch("AB", "A", "B", "ac_line", True, 20.0, reactance_pu=0.1),),
        (
            AssetBusMapping("g", "A", "generator"),
            AssetBusMapping("demand:B", "B", "demand"),
        ),
        100.0,
    )
    return NetworkPSMInput(
        "p82", 2025, 1.0, chronology, topology,
        {"A": (0.0, 0.0), "B": (10.0, 12.0)},
        "domain.network.dc", "chronological_perfect_foresight",
    )


def candidate(**changes) -> NetworkCandidate:
    values = {
        "candidate_id": "AB-2", "corridor_id": "A-B", "from_bus": "A", "to_bus": "B",
        "technology": "ac_line", "circuits_per_build": 1, "max_build_circuits": 2,
        "thermal_rating_mw_per_circuit": 20.0, "apparent_power_rating_mva_per_circuit": 20.0,
        "resistance_pu": 0.01, "reactance_pu": 0.1, "charging_susceptance_pu": 0.0,
        "tap_ratio": None, "phase_shift_degrees": 0.0, "owner_id": "owner", "planner_id": "planner",
        "total_capex_gbp_per_build": 100.0, "annual_fixed_opex_gbp_per_build": 5.0,
        "construction_life_years": 1.0, "economic_life_years": 40.0, "discount_rate": 0.05,
        "lead_time_years": 2, "success_probability": 0.8, "budget_group": "GB",
        "trigger_branch_ids": ("AB",), "trigger_branch_rating_mw": 20.0,
        "minimum_trigger_utilisation": 0.9, "declared_annual_benefit_gbp": 20.0,
        "minimum_benefit_cost_ratio": 1.0, "earliest_decision_year": 2025,
    }
    values.update(changes)
    return NetworkCandidate(**values)


class Prompt82DomainReadinessTests(unittest.TestCase):
    def test_network_preview_uses_validated_canonical_topology_and_reconciliation(self):
        model = network_input()
        summary = summarise_network_input(model, source_sha256={"fixture": "a" * 64})
        self.assertEqual(summary["metrics"]["buses"]["value"], 2)
        self.assertEqual(summary["metrics"]["islands"]["value"], 1)
        self.assertEqual(summary["metrics"]["maximum_nodal_demand_reconciliation_residual_mwh"]["value"], 0.0)
        self.assertEqual(summary["asset_mappings"]["generator"], 1)
        broken = replace(model, demand_mwh_by_bus={"A": (0.0, 0.0), "B": (9.0, 12.0)})
        with self.assertRaisesRegex(ValueError, "Nodal demand mismatch"):
            summarise_network_input(broken, source_sha256={})
        islanded = replace(model, topology=replace(model.topology, branches=()))
        with self.assertRaisesRegex(ValueError, "exactly one declared reference"):
            summarise_network_input(islanded, source_sha256={})

    def test_hydrology_loader_separates_ror_reservoir_and_rejects_pumped_hydro(self):
        with tempfile.TemporaryDirectory(prefix="value-p82-hydro-") as temporary:
            root = Path(temporary)
            files = {
                "sites.csv": "site_id,technology_class,bus_id,capacity_mw,turbine_efficiency,conversion_mwh_per_water_unit,source,licence\nror,run_of_river,A,10,0.9,,fixture,CC0-1.0\nres,reservoir,B,4,0.9,1,fixture,CC0-1.0\n",
                "map.csv": "asset_id,site_id,share\nhydro-ror,ror,1\nhydro-res,res,1\n",
                "ror.csv": "timestamp,site_id,value,unit,interval_hours,timezone\n2025-01-01T00:00:00+00:00,ror,0.5,p.u.,0.5,UTC\n2025-01-01T00:30:00+00:00,ror,0.6,p.u.,0.5,UTC\n",
                "reservoir.csv": "timestamp,site_id,value,unit,interval_hours,timezone\n2025-01-01T00:00:00+00:00,res,1,water_unit/period,0.5,UTC\n2025-01-01T00:30:00+00:00,res,1,water_unit/period,0.5,UTC\n",
                "params.json": json.dumps({"reservoirs": [{
                    "site_id": "res", "min_volume": 0, "max_volume": 10,
                    "initial_volume": 5, "terminal_volume": 5,
                    "max_turbine_release_per_period": 2,
                    "max_total_release_per_period": 3,
                    "minimum_environmental_release_per_period": 0.1,
                    "conversion_mwh_per_water_unit": 1, "turbine_efficiency": 0.9,
                    "turbine_capacity_mw": 4, "information_structure": "perfect_foresight",
                }]}),
            }
            bindings = {}
            role_files = {
                "value.hydrology.site-catalogue": "sites.csv",
                "value.hydrology.asset-site-map": "map.csv",
                "value.hydrology.run-of-river-inflow": "ror.csv",
                "value.hydrology.reservoir-inflow": "reservoir.csv",
                "value.hydrology.reservoir-parameters": "params.json",
            }
            for role, name in role_files.items():
                path = root / name
                path.write_text(files[name], encoding="utf-8")
                bindings[role] = {"uri": name, "format": path.suffix[1:], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            manifest = {"id": "hydro", "timezone": "UTC", "bindings": bindings}
            bundle = load_hydrology_inputs_from_pack(root, manifest)
            summary = summarise_hydrology_input(bundle)
            self.assertEqual(summary["metrics"]["run_of_river_sites"]["value"], 1)
            self.assertEqual(summary["metrics"]["reservoir_sites"]["value"], 1)
            self.assertFalse(summary["pumped_hydro_included"])
            (root / "sites.csv").write_text(files["sites.csv"].replace("run_of_river", "pumped_hydro", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown hydrology technology"):
                load_hydrology_inputs_from_pack(root, manifest)

    def test_expansion_preview_reports_endpoints_and_zero_budget(self):
        summary, issues = summarise_expansion_input(
            (candidate(),), source_sha256="b" * 64,
            annual_budget_gbp=0.0, group_budget_gbp=1000.0,
            topology_bus_ids=("A", "B"),
        )
        self.assertEqual(summary["metrics"]["candidates"]["value"], 1)
        self.assertIn("GF_DOMAIN_EXPANSION_ZERO_BUDGET", {item["code"] for item in issues})
        _summary, bad = summarise_expansion_input(
            (candidate(to_bus="C"),), source_sha256="b" * 64,
            annual_budget_gbp=1000.0, group_budget_gbp=1000.0,
            topology_bus_ids=("A", "B"),
        )
        self.assertIn("GF_DOMAIN_EXPANSION_ENDPOINT", {item["code"] for item in bad})

    def test_single_node_study_gets_no_network_or_hydrology_warning(self):
        project = {
            "id": "p82-single", "data_pack_id": "value-synthetic-contract-pack-v1",
            "start_year": 2025, "end_year": 2025,
            "modules": {
                "psm": "value-perfect-foresight-lp", "investment": "agent-investment",
                "pipeline": "planning-pipeline", "vre_cap": "vre-expansion-cap",
                "storage_cap": "value-storage-expansion-policy", "transition": "value-annual-state-transition",
            },
        }
        manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
        result = build_domain_readiness(
            project, pack_root=PACK, pack_manifest=manifest,
            registry=workspace_registry(ROOT / "missing-modules"), requested_periods=2,
        )
        self.assertTrue(result["ready"], result["issues"])
        self.assertEqual(set(result["sections"]), {"system"})


if __name__ == "__main__":
    unittest.main()
