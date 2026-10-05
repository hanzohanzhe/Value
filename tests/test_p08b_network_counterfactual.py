"""P0-8 S9: the network cost is zonal minus a network-free LP counterfactual.

Findings P2-02 (VOLL only on the zonal side), P2-03 (static vs period unit
prices) and P2-04 (export arbitrage only in the zonal LP): the three cases now
share one engine, one unit-cost table and one VOLL, so a run whose network is
never binding has a network cost of exactly zero in every period.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh.copperplate_balancing import CopperplateBalancing
from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import (
    DynamicStorageCostDefinition,
)
from gridform_core.builtin.scheme_c_1000twh.staged_psm import StagedBidAtCostPSM
from gridform_core.module_context import ImmutableContextResolver, RunStaticContext
from gridform_core.staged_market_contracts import (
    AheadMarketResult,
    BalancingInput,
    ZonalRedispatchDomainV2,
    contract_sha256,
)
from gridform_core.v2.contracts import (
    AssetStateV2,
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
)
from gridform_core.v2.orchestrator import build_year_context
from gridform_core.zonal_contracts import (
    CutsetMember,
    ETYSBoundary,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZonalAssetMapping,
    ZonalDemand,
    ZonalNetworkPack,
)
from gridform_core.zonal_redispatch import ZonalRedispatchBalancing
from gridform_core.zonal_results import build_zonal_period_accounting, zonal_workspace_capabilities
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS
from gridform_validation.zonal_case_generator import bind_production_input, production_solution
from gridform_validation.zonal_oracle import compare_zonal_solutions, solve_zonal_oracle
from tests.network_toys import zonal_bid, zonal_declaration
from tests.test_prompt101_staged_cem_integration import _economics

VOLL = 17_000.0


def pack(zones: tuple[str, ...], mappings: dict[str, str], periods: tuple[str, ...],
         demand_by_zone: dict[str, tuple[float, ...]], limit: float | None) -> ZonalNetworkPack:
    corridors = ()
    cutsets = ()
    if len(zones) == 2:
        corridors = (TransportCorridor("a-b", zones[0], zones[1], "from_to_positive"),)
        cutsets = (ETYSBoundary("B_AB", "fixture", (CutsetMember("a-b", 1),), limit, limit,
                                reverse_limit_method="source_declared_symmetric"),)
    national = tuple(sum(values[index] for values in demand_by_zone.values()) for index in range(len(periods)))
    result = ZonalNetworkPack(
        "cf-fixture", "",
        tuple(NetworkZone(zone, zone, "DSO", "England") for zone in zones),
        corridors, cutsets,
        tuple(ZonalAssetMapping(asset, zone, "generator", "x", 1.0, "fixture") for asset, zone in mappings.items()),
        ZonalDemand(periods, demand_by_zone, national),
        (), (), SpatialAudit((), {}, {}, 1e-9), "lossless_v1",
    )
    return replace(result, scientific_sha256=result.compute_scientific_sha256())


def staged_zonal_run(model_input: PSMInput, network: ZonalNetworkPack, output_dir: Path):
    psm = StagedBidAtCostPSM()
    balancing = ZonalRedispatchBalancing()
    psm.configure_run(
        output_dir=output_dir, storage_cost=DynamicStorageCostDefinition(), balancing=balancing,
        expected_balancing_identity=(balancing.id, balancing.version), network_pack=network,
        zonal_demand_mode="network_pack_absolute_demand", ledger_detail="full",
    )
    run_context = RunStaticContext(
        run_id=model_input.run_id, study_revision_sha256="a" * 64,
        start_year=model_input.year, end_year=model_input.year, period_hours=model_input.period_hours,
        data_pack={"data_pack_id": model_input.data_pack_id, "manifest_sha256": "b" * 64},
        module_graph={"graph_sha256": "c" * 64},
        scientific_parameters={"clock.period_hours": model_input.period_hours},
        runtime_controls={}, trace_profile="full",
        solver_contract=DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
        market_configuration={"zonal_demand_mode": "network_pack_absolute_demand"},
        network_pack=network.to_dict(),
    )
    prepared, metadata = psm.prepare_year_context(model_input)
    year_context = build_year_context(
        run_context=run_context, model_input=prepared,
        transition_lineage={"fixture": True}, annual_metadata=metadata,
    )
    resolver = ImmutableContextResolver(
        run_contexts=(run_context,), year_contexts=(year_context,),
        modules_by_slot={"psm": psm, "balancing": balancing},
    )
    psm.configure(run_context, resolver)
    psm.start_year(year_context)
    result = psm.run(prepared)
    with closing(sqlite3.connect(output_dir / "market" / "market.sqlite")) as connection:
        connection.row_factory = sqlite3.Row
        accounting = [dict(row) for row in connection.execute(
            "SELECT * FROM zonal_period_accounting ORDER BY period")]
        resources = [dict(row) for row in connection.execute(
            "SELECT * FROM zonal_resource_dispatch ORDER BY period, asset_id")]
        curtailment = [dict(row) for row in connection.execute(
            "SELECT * FROM vre_curtailment_period ORDER BY period")]
    return result, accounting, resources, curtailment


def psm_input(resources, demand, *, forecast=None, extensions=None) -> PSMInput:
    periods = tuple(f"2025-01-01:{index + 1:02d}" for index in range(len(demand)))
    assets = tuple(AssetStateV2(row.asset_id, row.technology, row.capacity_mw,
                                extensions=_economics(row.asset_id)) for row in resources)
    chronology = ChronologicalPSMData(
        periods, tuple(demand), tuple(resources), (), VOLL, terminal_soc_rule="free",
        extensions={"forecast_demand_mwh": tuple(forecast or demand), **(extensions or {})},
    )
    return PSMInput("cf-run", 2025, "fixture-pack", OperatingState(2025, assets, ()), 1.0,
                    {"market.bid_multiplier": 1.0}, chronology=chronology)


def generator(asset, technology, kind, capacity, cost, profile=None, availability=(1.0,)):
    return DispatchResource(asset, technology, kind, capacity, cost, availability,
                            marginal_cost_profile_gbp_per_mwh=tuple(profile or ()),
                            extensions={"agent_id": asset})


class NetworkFreeCounterfactualTests(unittest.TestCase):
    def test_single_zone_national_shortfall_is_not_network_cost(self) -> None:
        """P2-02: HEAD booked VOLL x 1 MWh = 17000 as network constraint cost."""

        model_input = psm_input((generator("ccgt", "CCGT", "thermal", 10.0, 50.0),), (11.0,))
        network = pack(("gb",), {"ccgt": "gb"}, model_input.chronology.period_ids, {"gb": (11.0,)}, None)
        with tempfile.TemporaryDirectory() as folder:
            result, accounting, _resources, _curtailment = staged_zonal_run(model_input, network, Path(folder))
        row = accounting[0]
        self.assertAlmostEqual(row["blackout_mwh"], 1.0, places=6)
        self.assertEqual(row["network_constraint_cost_gbp"], 0.0)
        self.assertAlmostEqual(row["zonal_resource_cost_gbp"], 500.0 + VOLL, places=4)
        self.assertAlmostEqual(row["realised_copperplate_resource_cost_gbp"], 500.0 + VOLL, places=4)
        self.assertEqual(result.extensions["zonal_accounting_gbp"]["network_constraint_bid_objective_gbp"], 0.0)

    def test_period_import_prices_give_zero_network_cost_and_one_input_identity(self) -> None:
        """P2-03: a time-varying import price must not create network cost."""

        prices = (30.0, 70.0, 40.0, 60.0, 50.0, 50.0)
        demand = (8.0, 9.0, 10.0, 9.0, 8.0, 7.0)
        resources = (
            generator("ccgt", "CCGT", "thermal", 10.0, 45.0),
            generator("import:fr", "interconnector_import", "import", 5.0, 50.0, prices),
        )
        model_input = psm_input(resources, demand, forecast=tuple(value - 1.0 for value in demand))
        network = pack(("a", "b"), {"ccgt": "a", "import:fr": "b"}, model_input.chronology.period_ids,
                       {"a": tuple(value * 0.5 for value in demand), "b": tuple(value * 0.5 for value in demand)},
                       1e5)
        with tempfile.TemporaryDirectory() as folder:
            _result, accounting, resources_rows, _curtailment = staged_zonal_run(model_input, network, Path(folder))
        self.assertEqual(len(accounting), 6)
        for row in accounting:
            self.assertAlmostEqual(row["network_constraint_cost_gbp"], 0.0, places=6)
            self.assertEqual(row["accounting_status"], "reconciled")
            period_cost = sum(item["physical_resource_cost_gbp"] for item in resources_rows
                              if item["period"] == row["period"])
            self.assertAlmostEqual(period_cost + row["blackout_mwh"] * VOLL, row["zonal_resource_cost_gbp"], places=6)
        imported = [item for item in resources_rows if item["asset_id"] == "import:fr"]
        self.assertTrue(any(item["final_dispatch_mwh"] > 0 for item in imported))
        for item in imported:
            self.assertAlmostEqual(item["physical_resource_cost_gbp"],
                                   max(item["final_dispatch_mwh"], 0.0) * prices[item["period"]], places=9)

    def test_export_arbitrage_is_in_both_cases(self) -> None:
        """P2-04: CCGT GBP 50 and an export at GBP 80 on an unconstrained network."""

        resources = (
            generator("ccgt", "CCGT", "thermal", 20.0, 50.0),
            generator("wind", "onshore", "vre", 15.0, 0.0),
        )
        extensions = {
            "boundary_export_envelope_mwh_by_asset": {"export:fr": (5.0,)},
            "boundary_export_price_gbp_per_mwh_by_asset": {"export:fr": (80.0,)},
        }
        model_input = psm_input(resources, (10.0,), extensions=extensions)
        network = pack(("a", "b"), {"ccgt": "a", "wind": "a", "export:fr": "b"},
                       model_input.chronology.period_ids, {"a": (5.0,), "b": (5.0,)}, 1e6)
        with tempfile.TemporaryDirectory() as folder:
            _result, accounting, _resources, curtailment = staged_zonal_run(model_input, network, Path(folder))
        self.assertAlmostEqual(accounting[0]["network_constraint_cost_gbp"], 0.0, places=6)
        self.assertAlmostEqual(curtailment[0]["redispatch_avoided_curtailment_mwh"], 0.0, places=6)
        self.assertAlmostEqual(curtailment[0]["redispatch_added_curtailment_mwh"], 0.0, places=6)

    def test_binding_boundary_has_positive_bid_objective_network_cost(self) -> None:
        resources = (
            generator("wind", "onshore", "vre", 10.0, 0.0),
            generator("ccgt", "CCGT", "thermal", 10.0, 100.0),
        )
        model_input = psm_input(resources, (10.0,))
        network = pack(("a", "b"), {"wind": "a", "ccgt": "b"}, model_input.chronology.period_ids,
                       {"a": (0.0,), "b": (10.0,)}, 4.0)
        with tempfile.TemporaryDirectory() as folder:
            result, accounting, _resources, _curtailment = staged_zonal_run(model_input, network, Path(folder))
        # Wind can send only 4 of 10 MWh south; CCGT makes up 6 at GBP 100.
        self.assertAlmostEqual(accounting[0]["network_constraint_cost_gbp"], 600.0, places=4)
        self.assertGreater(result.extensions["zonal_accounting_gbp"]["network_constraint_bid_objective_gbp"], 0.0)


class KnownDefectTests(unittest.TestCase):
    def test_pre_p08b_ledgers_carry_the_dec_and_counterfactual_defects(self) -> None:
        from tests.test_prompt102_zonal_results_api import _write_fixture

        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            _write_fixture(database, "full")
            defects = {row["defect_id"] for row in zonal_workspace_capabilities(database)["known_defects"]}
        self.assertIn("p08.staged-dec-zero-pricing", defects)
        self.assertIn("p08.copperplate-counterfactual-mismatch", defects)

    def test_new_ledgers_do_not(self) -> None:
        resources = (generator("ccgt", "CCGT", "thermal", 10.0, 50.0),)
        model_input = psm_input(resources, (5.0,))
        network = pack(("gb",), {"ccgt": "gb"}, model_input.chronology.period_ids, {"gb": (5.0,)}, None)
        with tempfile.TemporaryDirectory() as folder:
            staged_zonal_run(model_input, network, Path(folder))
            capabilities = zonal_workspace_capabilities(Path(folder) / "market" / "market.sqlite")
        defects = {row["defect_id"] for row in capabilities["known_defects"]}
        self.assertNotIn("p08.staged-dec-zero-pricing", defects)
        self.assertNotIn("p08.copperplate-counterfactual-mismatch", defects)


class AccountingAlgebraTests(unittest.TestCase):
    def test_forecast_error_shortfall_is_valued_at_voll_in_every_case(self) -> None:
        """P2-02 second experiment: blackout 0 / 2 / 2 MWh, resource cost -100."""

        accounting = build_zonal_period_accounting(
            year=2025, period=0, period_id="p0", realised_input_sha256="a" * 64,
            perfect_forecast_resource_cost_gbp=1_000.0,
            realised_copperplate_resource_cost_gbp=900.0 + 2.0 * VOLL,
            zonal_resource_cost_gbp=900.0 + 2.0 * VOLL,
            ahead_settlement_mwh_by_asset={}, national_clearing_price_gbp_per_mwh=0.0,
            redispatch_cashflow_gbp_by_agent={}, policy_transfer_gbp=0.0,
            boundary_shadow_value_gbp_per_mwh={}, blackout_mwh=2.0,
        )
        self.assertAlmostEqual(accounting.forecast_error_cost_gbp, 33_900.0)
        self.assertAlmostEqual(accounting.transmission_constraint_resource_cost_gbp, 0.0)

    def test_negative_case_costs_are_allowed(self) -> None:
        accounting = build_zonal_period_accounting(
            year=2025, period=0, period_id="p0", realised_input_sha256="a" * 64,
            perfect_forecast_resource_cost_gbp=-50.0, realised_copperplate_resource_cost_gbp=-40.0,
            zonal_resource_cost_gbp=-10.0, ahead_settlement_mwh_by_asset={},
            national_clearing_price_gbp_per_mwh=0.0, redispatch_cashflow_gbp_by_agent={},
            policy_transfer_gbp=0.0, boundary_shadow_value_gbp_per_mwh={}, blackout_mwh=0.0,
        )
        self.assertAlmostEqual(accounting.transmission_constraint_resource_cost_gbp, 30.0)


class CollapsedProblemTests(unittest.TestCase):
    def two_zone_declaration(self, zones):
        bids = (
            zonal_bid("wind-down", "wind", zones["wind"], "down", 10.0, 0.0, baseline_mwh=10.0, resource_class="vre"),
            zonal_bid("gas-up", "gas", zones["gas"], "up", 10.0, 100.0),
            zonal_bid("peak-up", "peak", zones["peak"], "up", 10.0, 300.0),
        )
        demand = {zone: 0.0 for zone in set(zones.values())}
        demand[zones["gas"]] = 12.0
        return zonal_declaration(
            demand, {"wind": 10.0}, zones, bids,
            classes={"wind": "vre", "gas": "thermal", "peak": "thermal"},
        )

    def test_network_free_case_equals_the_single_zone_lp_and_the_cbc_oracle(self) -> None:
        constrained = self.two_zone_declaration({"wind": "a", "gas": "b", "peak": "b"})
        model_input, module = bind_production_input(constrained)
        network_free = module.network_free_counterfactual(model_input)
        folded = self.two_zone_declaration({"wind": "gb", "gas": "gb", "peak": "gb"})
        production = production_solution(folded)
        oracle = solve_zonal_oracle(folded)
        self.assertTrue(compare_zonal_solutions(folded, production, oracle)["passed"])
        for asset in ("wind", "gas", "peak"):
            self.assertAlmostEqual(
                network_free.final_dispatch_mwh_by_asset.get(asset, 0.0),
                oracle["final_dispatch_mwh_by_asset"].get(asset, 0.0), places=6,
            )
        self.assertAlmostEqual(network_free.extensions["primary_objective_gbp"],
                               oracle["primary_objective_gbp"], places=4)
        self.assertEqual(network_free.extensions["method"], "value.network-free-lp/v1")
        # A counterfactual never consumes the one-use input history.
        module.clear(model_input)

    def test_without_ties_or_exports_the_lp_matches_greedy_copperplate(self) -> None:
        declaration = self.two_zone_declaration({"wind": "a", "gas": "b", "peak": "b"})
        model_input, module = bind_production_input(declaration)
        network_free = module.network_free_counterfactual(model_input)
        domain = ZonalRedispatchDomainV2.from_dict(model_input.domain_payload)
        ahead: AheadMarketResult = domain.period_slice.ahead_result
        greedy_input = BalancingInput(
            model_input.run_id, model_input.year, model_input.period, model_input.period_id,
            contract_sha256(ahead), model_input.real_demand_mwh,
            model_input.realised_availability_mw_by_asset, {}, model_input.bids,
            model_input.period_hours, model_input.voll_gbp_per_mwh,
            domain_payload={
                "schema_version": "force.copperplate-balancing-domain/v1",
                "ahead_result": ahead.to_dict(),
                "resource_cost_gbp_per_mwh_by_asset": {"wind": 0.0, "gas": 100.0, "peak": 300.0},
                "resource_class_by_asset": {"wind": "vre", "gas": "thermal", "peak": "thermal"},
                "storage": {},
            },
        )
        greedy = CopperplateBalancing().clear(greedy_input)
        for asset in ("wind", "gas", "peak"):
            self.assertAlmostEqual(network_free.final_dispatch_mwh_by_asset.get(asset, 0.0),
                                   greedy.final_dispatch_mwh_by_asset.get(asset, 0.0), places=6)


if __name__ == "__main__":
    unittest.main()
