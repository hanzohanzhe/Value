from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from gridform_core.domain_results import (
    DomainResultError,
    domain_result_capabilities,
    query_ac_results,
    query_expansion_events,
    query_expansion_summary,
    query_network_branches,
    query_network_periods,
    query_network_summary,
)
from gridform_core.domain_results import _declared_asset_bus_shares
from gridform_core.network_contracts import (
    AssetBusMapping,
    NetworkBranch,
    NetworkBus,
    NetworkPSMInput,
    NetworkTopology,
)
from gridform_core.network_dc import ReferenceDCNetworkPSM
from gridform_core.network_expansion import write_network_expansion_artifacts
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
)


def completed_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "status.json").write_text(
        json.dumps({"id": root.name, "status": "completed"}), encoding="utf-8"
    )
    model = root / "model-output"
    model.mkdir()
    (model / "module-resolution.json").write_text(
        json.dumps({
            "graph_sha256": "a" * 64,
            "modules": {"psm": {"module_id": "value-reference-dc-network", "module_version": "1.0.0"}},
            "extension_graph": {"extensions": [{"id": "value-network-contract-extension", "version": "1.0.0"}]},
        }), encoding="utf-8",
    )
    return root


def run_dc(root: Path, periods: int = 24, *, split_cheap: bool = False) -> None:
    period_ids = tuple(f"2025:{index}" for index in range(periods))
    chronology = ChronologicalPSMData(
        period_ids, tuple(10.0 for _ in period_ids),
        (
            DispatchResource("cheap", "ccgt", "thermal", 20.0, 1.0, (1.0,)),
            DispatchResource("local", "ocgt", "thermal", 20.0, 100.0, (1.0,)),
        ), (), 10_000.0,
    )
    topology = NetworkTopology(
        (
            NetworkBus("A", 400.0, "A", True, True),
            NetworkBus("B", 400.0, "B"),
        ),
        (NetworkBranch("AB", "A", "B", "ac_line", True, 4.0, reactance_pu=0.1),),
        (
            (
                AssetBusMapping("cheap", "A", "generator", 0.5),
                AssetBusMapping("cheap", "B", "generator", 0.5),
            ) if split_cheap else (AssetBusMapping("cheap", "A", "generator"),)
        ) + (AssetBusMapping("local", "B", "generator"),), 100.0,
    )
    network = NetworkPSMInput(
        root.name, 2025, 1.0, chronology, topology,
        {"A": tuple(0.0 for _ in period_ids), "B": tuple(10.0 for _ in period_ids)},
        "domain.network.dc", "chronological_perfect_foresight",
    )
    wrapped = PSMInput(
        root.name, 2025, "fixture", OperatingState(2025, (), ()), 1.0, {},
        chronology=chronology,
        extensions={
            "network_input": network.to_dict(),
            "artifact_directory": str(root / "model-output" / "solver"),
        },
    )
    ReferenceDCNetworkPSM().run(wrapped)


def write_ac(root: Path, *, missing_losses: bool = False) -> None:
    path = root / "model-output" / "solver" / "ac"
    path.mkdir(parents=True, exist_ok=True)
    period = {
        "period_id": "2025:0", "status": "LOCAL_SOLUTION_VALIDATED",
        "voltage_magnitude_pu": {"A": 1.0, "B": 0.99},
        "voltage_angle_radians": {"A": 0.0, "B": -0.01},
        "active_generation_mw_by_asset": {"g": 10.1},
        "reactive_generation_mvar_by_bus": {"A": 2.0, "B": 0.0},
        "branch_from_active_mw": {"AB": 10.1},
        "branch_from_reactive_mvar": {"AB": 2.0},
        "branch_to_active_mw": {"AB": -10.0},
        "branch_to_reactive_mvar": {"AB": -1.8},
        "active_loss_mw_by_branch": {"AB": 0.1},
        "residuals": {"active_mw": 1e-9, "reactive_mvar": 1e-9},
        "violations": {}, "solver_metadata": {"method": "fixture"},
    }
    if missing_losses:
        del period["active_loss_mw_by_branch"]
    payload = {
        "schema_version": "value.ac-feasibility-output/v1", "run_id": root.name,
        "year": 2025, "module_id": "value-reference-ac-feasibility", "module_version": "0.1.0",
        "formulation_id": "value.ac-feasibility-polar-power-flow/v1", "solver_status": "optimal",
        "convergence_class": "LOCAL_SOLUTION_VALIDATED", "periods": [period],
        "capabilities": ["domain.network.ac"], "unsupported": {"ac_opf": "NOT_EVALUATED"},
        "maximum_active_residual_mw": 1e-9, "maximum_reactive_residual_mvar": 1e-9,
        "maximum_equipment_violation": 0.0,
    }
    (path / "ac-feasibility-2025.json").write_text(json.dumps(payload), encoding="utf-8")


def write_expansion(root: Path) -> None:
    event = {
        "event_id": "commissioned:line", "event_type": "commissioned", "candidate_id": "AB-2",
        "project_id": "project:AB-2", "asset_id": "line:AB-2", "corridor_id": "A-B",
        "from_bus": "A", "to_bus": "B", "circuits": 1, "rating_mw": 4.0,
        "reason_code": "planning_complete",
    }
    result = SimpleNamespace(
        year=2026,
        extensions={"network_expansion": {
            "decision": {"proposals": [{}]},
            "admission": {"admitted_projects": [{}], "failed_proposals": [], "events": []},
            "advance": {"commissioned_assets": [{}], "retired_assets": [], "events": [event]},
        }},
    )
    write_network_expansion_artifacts(root / "model-output" / "network", (result,))


class Prompt83DomainResultTests(unittest.TestCase):
    def test_dc_queries_are_bounded_reconciled_and_provenanced(self):
        with tempfile.TemporaryDirectory(prefix="value-p83-dc-") as temporary:
            root = completed_root(Path(temporary) / "run-dc")
            run_dc(root, periods=168)
            started = time.perf_counter()
            summary = query_network_summary(root, year=2025)
            page = query_network_periods(root, year=2025, limit=24)
            branches = query_network_branches(root, year=2025, limit=20)
            elapsed = time.perf_counter() - started
            self.assertEqual(summary["metrics"]["periods"]["value"], 168)
            self.assertEqual(summary["metrics"]["congestion_branch_periods"]["value"], 168)
            self.assertEqual(page["total"], 168)
            self.assertEqual(len(page["items"]), 24)
            self.assertEqual({item["bus_id"] for item in page["items"][0]["buses"]}, {"A", "B"})
            self.assertIn("angle_rad", page["items"][0]["buses"][0])
            self.assertEqual(len(branches["items"]), 20)
            self.assertAlmostEqual(branches["items"][0]["utilisation_fraction"], 1.0)
            self.assertEqual(len(summary["source_artifacts"]["period_index_sha256"]), 64)
            self.assertLess(elapsed, 5.0)

    def test_dc_topology_read_model_keeps_split_assets(self):
        """Review M2-P0-8a: a split asset is absent from asset_to_bus (DC 1.1.0)."""

        with tempfile.TemporaryDirectory(prefix="value-p83-dc-split-") as temporary:
            root = completed_root(Path(temporary) / "run-dc-split")
            run_dc(root, periods=4, split_cheap=True)
            summary = query_network_summary(root, year=2025)
            self.assertEqual(
                summary["topology"]["asset_bus_shares"],
                {"cheap": [["A", 0.5], ["B", 0.5]], "local": [["B", 1.0]]},
            )
        # A clearing-input row written before DC 1.1.0 has no share list.
        self.assertEqual(
            _declared_asset_bus_shares({"asset_to_bus": {"g": "A", "h": "B"}}),
            {"g": [["A", 1.0]], "h": [["B", 1.0]]},
        )

    def test_swapped_branch_sign_and_rating_breach_fail_integrity_gate(self):
        with tempfile.TemporaryDirectory(prefix="value-p83-mutant-") as temporary:
            root = completed_root(Path(temporary) / "run-mutant")
            run_dc(root, periods=2)
            database = root / "model-output" / "solver" / "network" / "dc-network-2025.sqlite"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("UPDATE period_branch SET flow_mw=-flow_mw WHERE rowid=1")
                connection.commit()
            with self.assertRaisesRegex(DomainResultError, "nodal balance"):
                query_network_summary(root, year=2025)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("UPDATE period_branch SET flow_mw=99")
                connection.commit()
            with self.assertRaisesRegex(DomainResultError, "branch rating"):
                query_network_summary(root, year=2025)

    def test_ac_query_labels_not_opf_and_missing_losses_fail(self):
        with tempfile.TemporaryDirectory(prefix="value-p83-ac-") as temporary:
            root = completed_root(Path(temporary) / "run-ac")
            write_ac(root)
            result = query_ac_results(root, year=2025)
            self.assertIn("not AC OPF", result["claim"])
            self.assertAlmostEqual(result["items"][0]["active_loss_mw"], 0.1)
            write_ac(root, missing_losses=True)
            with self.assertRaisesRegex(DomainResultError, "active_loss_mw_by_branch"):
                query_ac_results(root, year=2025)

    def test_expansion_lineage_and_missing_hydrology_are_not_fabricated(self):
        with tempfile.TemporaryDirectory(prefix="value-p83-expansion-") as temporary:
            root = completed_root(Path(temporary) / "run-expansion")
            write_expansion(root)
            summary = query_expansion_summary(root)
            events = query_expansion_events(root)
            capabilities = domain_result_capabilities(root)
            self.assertEqual(summary["years"][0]["commissioned"], 1)
            self.assertEqual(events["items"][0]["asset_id"], "line:AB-2")
            self.assertEqual(capabilities["capabilities"]["hydrology"]["status"], "not_evaluated")
            self.assertIsNotNone(capabilities["capabilities"]["hydrology"]["reason"])

    def test_zonal_ledger_is_a_supported_domain_found_without_count(self):
        # P0-9 S10 (R3-16): a v6+ zonal ledger keeps its periods in
        # zonal_period_accounting; both capability views must see it.
        import inspect
        import gridform_core.domain_results as domain_results
        from gridform_core.market_replay import market_replay_capabilities
        from tests.test_prompt102_zonal_results_api import _write_fixture

        with tempfile.TemporaryDirectory(prefix="value-p83-zonal-") as temporary:
            root = completed_root(Path(temporary) / "run-zonal")
            database = root / "model-output" / "market" / "market.sqlite"
            _write_fixture(database, "summary")
            zonal = domain_result_capabilities(root)["capabilities"]["zonal_redispatch"]
            market = market_replay_capabilities(database)
            empty_root = completed_root(Path(temporary) / "run-single-node")
            single = domain_result_capabilities(empty_root)["capabilities"]["zonal_redispatch"]
        self.assertEqual(zonal["status"], "supported")
        self.assertEqual(zonal["years"], [2025])
        self.assertTrue(market["zonal_redispatch"])
        self.assertEqual(single["status"], "unsupported")
        self.assertNotIn("valid", str(single["reason"]).lower())
        self.assertNotIn("COUNT(", inspect.getsource(domain_results._zonal_redispatch_capability))


if __name__ == "__main__":
    unittest.main()
