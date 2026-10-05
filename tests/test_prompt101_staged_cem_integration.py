from __future__ import annotations

import tempfile
import unittest
import sqlite3
import json
from gridform_core import agent_cashflow
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh.staged_psm import (
    StagedBidAtCostPSM,
    _validate_vre_counterfactual_cases,
)
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import (
    SchemeCAgentInvestmentDefinition,
)
from gridform_core.catalog import MODULES, MODULE_REGISTRY
from gridform_core.cost_ledger import build_cem_cost_ledger
from gridform_core.errors import InvariantError
from gridform_core.frontend_contract import module_slot_catalog
from gridform_core.cem_market_adapter import (
    adapt_market_for_investment,
    inherit_frozen_zone_shares,
)
from gridform_core.run_lineage import copperplate_rerun_project
from gridform_core.market_ledger import PeriodLedgerRow, SQLiteMarketLedger
from gridform_core.module_context import (
    ImmutableContextResolver,
    RunStaticContext,
    canonical_context_sha256,
)
from gridform_core.study_market_config import resolve_market_configuration
from gridform_core.subannual_checkpoint import PSMSubannualCheckpointEngine
from gridform_core.v2.contracts import (
    AssetStateV2,
    ChronologicalPSMData,
    DispatchResource,
    ExpansionHeadroom,
    MarketYearResult,
    ModuleSelection,
    OperatingState,
    PSMInput,
    ResolvedRun,
    StorageDispatchResource,
)
from gridform_core.v2.projects import migrate_project_v1, parse_project
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
from gridform_core.vre_curtailment_attribution import CurtailmentAttributionError
from gridform_core.v2.orchestrator import build_year_context


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data-packs" / "value-101-baseline-v1"


class _FlatStorageCost:
    def __init__(self) -> None:
        self.sold = 0.0

    def prepare_year(self, year: int, **_kwargs: object) -> None:
        self.year = year

    def bid_price_gbp_per_mwh(self, _dwell_periods: float) -> float:
        return 20.0

    def record_sale(self, delivered_mwh: float, _dwell_periods: float) -> None:
        self.sold += float(delivered_mwh)

    def report(self) -> dict[str, object]:
        return {"method": "fixture", "current_year_sold_mwh": self.sold}


class _FlatStorageCostDefinition:
    id = "fixture-storage"
    version = "1.0.0"

    @staticmethod
    def create(**_kwargs: object) -> _FlatStorageCost:
        return _FlatStorageCost()


class _PriorityStorageCost(_FlatStorageCost):
    def bid_price_gbp_per_mwh(self, _dwell_periods: float) -> float:
        return -1.0


class _PriorityStorageCostDefinition:
    id = "fixture-priority-storage"
    version = "1.0.0"

    @staticmethod
    def create(**_kwargs: object) -> _PriorityStorageCost:
        return _PriorityStorageCost()


class _MissingVREKeyBalancing(ZonalRedispatchBalancing):
    def clear(self, model_input):
        result = super().clear(model_input)
        dispatch = dict(result.final_dispatch_mwh_by_asset)
        dispatch.pop("offshore", None)
        return replace(result, final_dispatch_mwh_by_asset=dispatch)


class _NegativeVREDispatchBalancing(ZonalRedispatchBalancing):
    def clear(self, model_input):
        result = super().clear(model_input)
        dispatch = dict(result.final_dispatch_mwh_by_asset)
        dispatch["offshore"] = -1.0
        return replace(result, final_dispatch_mwh_by_asset=dispatch)


class _InjectedUnvalidatedBalancing(ZonalRedispatchBalancing):
    """Keep the physical solution intact while injecting a valid warning class."""

    def clear(self, model_input):
        result = super().clear(model_input)
        extensions = dict(result.extensions)
        rows = [dict(row) for row in extensions["network_solver_diagnostics"]]
        target = next(
            row for row in rows
            if row["phase_id"] == "secondary_schedule_deviation"
        )
        target["computed_tolerance"] = 0.002
        target["validation_class"] = "COMPLETED_WITH_NUMERICAL_WARNING"
        extensions["network_solver_diagnostics"] = rows
        return replace(result, extensions=extensions)


def _economics(owner: str) -> dict[str, object]:
    return {
        "capital_cost_per_mw": 1_000.0,
        "capital_cost_per_mwh": 0.0,
        "total_capex_gbp": 10_000.0,
        "annual_fixed_opex_gbp": 0.0,
        "economic_lifetime_years": 25.0,
        "capital_discount_rate": 0.0,
        "annualized_capital_cost_gbp": 400.0,
        "fixed_om_basis": "fixture",
        "asset_economics_schema_version": "value.asset-economics/v1",
        "investment_owner_id": owner,
        "investment_eligible": True,
    }


def _network_pack() -> ZonalNetworkPack:
    pack = ZonalNetworkPack(
        "fixture-network",
        "",
        (
            NetworkZone("north", "North", "Fixture DSO", "England"),
            NetworkZone("south", "South", "Fixture DSO", "England"),
        ),
        (TransportCorridor("north-south", "north", "south", "from_to_positive"),),
        (
            ETYSBoundary(
                "B_TEST",
                "Fixture boundary",
                (CutsetMember("north-south", 1),),
                4.0,
                4.0,
                reverse_limit_method="source_declared_symmetric",
            ),
        ),
        (
            ZonalAssetMapping("wind", "north", "generator", "onshore", 1.0, "fixture"),
            ZonalAssetMapping("battery", "south", "storage", "1c_battery", 1.0, "fixture"),
            ZonalAssetMapping("ccgt", "south", "generator", "CCGT", 1.0, "fixture"),
        ),
        ZonalDemand(("p0",), {"north": (0.0,), "south": (10.0,)}, (10.0,)),
        (),
        (),
        SpatialAudit((), {}, {}, 1e-9),
        "lossless_v1",
    )
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


def _zonal_input() -> PSMInput:
    assets = (
        AssetStateV2("wind", "onshore", 10.0, region="north", extensions=_economics("wind-owner")),
        AssetStateV2("battery", "1c_battery", 2.0, 2.0, "south", extensions=_economics("storage-owner")),
        AssetStateV2("ccgt", "CCGT", 10.0, region="south", extensions=_economics("thermal-owner")),
    )
    chronology = ChronologicalPSMData(
        ("p0",),
        (10.0,),
        (
            DispatchResource(
                "wind", "onshore", "vre", 10.0, 0.0, (1.0,),
                extensions={"agent_id": "wind-owner"},
            ),
            DispatchResource(
                "ccgt", "CCGT", "thermal", 10.0, 100.0, (1.0,),
                extensions={"agent_id": "thermal-owner"},
            ),
        ),
        (
            StorageDispatchResource(
                "battery", "1c", 2.0, 2.0, 2.0, 1.0, 1.0, 2.0, 1.0,
                extensions={"agent_id": "storage-owner", "base_asset_id": "battery"},
            ),
        ),
        17_000.0,
        terminal_soc_rule="free",
        extensions={"forecast_demand_mwh": (10.0,)},
    )
    return PSMInput(
        "prompt101-zonal",
        2025,
        "fixture-pack",
        OperatingState(2025, assets, ()),
        1.0,
        {"market.bid_multiplier": 1.0},
        chronology=chronology,
    )


def _redispatch_avoids_curtailment_input() -> PSMInput:
    assets = (
        AssetStateV2(
            "onshore",
            "onshore",
            5.0,
            region="north",
            extensions=_economics("onshore-owner"),
        ),
        AssetStateV2(
            "offshore",
            "offshore",
            5.0,
            region="north",
            extensions=_economics("offshore-owner"),
        ),
        AssetStateV2(
            "battery",
            "1c_battery",
            3.0,
            3.0,
            "south",
            extensions=_economics("storage-owner"),
        ),
    )
    chronology = ChronologicalPSMData(
        ("p0",),
        (10.0,),
        (
            DispatchResource(
                "onshore",
                "onshore",
                "vre",
                5.0,
                0.0,
                (1.0,),
                extensions={"agent_id": "onshore-owner"},
            ),
            DispatchResource(
                "offshore",
                "offshore",
                "vre",
                5.0,
                0.0,
                (1.0,),
                extensions={"agent_id": "offshore-owner"},
            ),
        ),
        (
            StorageDispatchResource(
                "battery",
                "1c",
                3.0,
                3.0,
                3.0,
                1.0,
                1.0,
                3.0,
                0.0,
                extensions={
                    "agent_id": "storage-owner",
                    "base_asset_id": "battery",
                },
            ),
        ),
        17_000.0,
        terminal_soc_rule="free",
        extensions={"forecast_demand_mwh": (10.0,)},
    )
    return PSMInput(
        "prompt101-avoided-curtailment",
        2025,
        "fixture-pack",
        OperatingState(2025, assets, ()),
        1.0,
        {"market.bid_multiplier": 1.0},
        chronology=chronology,
    )


def _redispatch_avoids_curtailment_network() -> ZonalNetworkPack:
    pack = _network_pack()
    pack = replace(
        pack,
        cutsets=(
            replace(
                pack.cutsets[0],
                forward_limit_mw=0.0,
                reverse_limit_mw=0.0,
            ),
        ),
        zonal_demand=ZonalDemand(
            ("p0",),
            {"north": (10.0,), "south": (0.0,)},
            (10.0,),
        ),
        asset_mappings=(
            ZonalAssetMapping(
                "onshore", "north", "generator", "onshore", 1.0, "fixture"
            ),
            ZonalAssetMapping(
                "offshore", "north", "generator", "offshore", 1.0, "fixture"
            ),
            ZonalAssetMapping(
                "battery", "south", "storage", "1c_battery", 1.0, "fixture"
            ),
        ),
        scientific_sha256="",
    )
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


def _resolved_run() -> ResolvedRun:
    ids = {
        slot: ModuleSelection(slot, module_id, "1.0.0", "fixture/v1")
        for slot, module_id in {
            "psm": "value-staged-bid-at-cost-psm",
            "balancing": "value-zonal-redispatch-balancing",
            "investment": "agent-investment",
        }.items()
    }
    return ResolvedRun(
        "prompt101-zonal", "fixture", "fixture", "fixture-pack", 2025, 2026,
        ids, {}, {},
    )


def _run_contextual(
    psm: StagedBidAtCostPSM,
    balancing: ZonalRedispatchBalancing,
    model_input: PSMInput,
):
    network = psm._network_pack
    if network is None:
        return psm.run(model_input)
    run_context = RunStaticContext(
        run_id=model_input.run_id,
        study_revision_sha256="a" * 64,
        start_year=model_input.year,
        end_year=model_input.year,
        period_hours=model_input.period_hours,
        data_pack={"data_pack_id": model_input.data_pack_id, "manifest_sha256": "b" * 64},
        module_graph={"graph_sha256": "c" * 64},
        scientific_parameters={"clock.period_hours": model_input.period_hours},
        runtime_controls={},
        trace_profile="summary",
        solver_contract={},
        market_configuration={"zonal_demand_mode": psm._zonal_demand_mode},
        network_pack=network.to_dict(),
    )
    prepared, metadata = psm.prepare_year_context(model_input)
    year_context = build_year_context(
        run_context=run_context,
        model_input=prepared,
        transition_lineage={"fixture": True},
        annual_metadata=metadata,
    )
    resolver = ImmutableContextResolver(
        run_contexts=(run_context,),
        year_contexts=(year_context,),
        modules_by_slot={"psm": psm, "balancing": balancing},
    )
    psm.configure(run_context, resolver)
    psm.start_year(year_context)
    self_check = canonical_context_sha256(year_context)
    if len(self_check) != 64:
        raise AssertionError("Fixture year context is not content addressed")
    return psm.run(prepared)


class Prompt101LiveIntegrationTests(unittest.TestCase):
    def test_staged_psm_exposes_optional_subannual_checkpoint_protocol(self) -> None:
        self.assertIsInstance(StagedBidAtCostPSM(), PSMSubannualCheckpointEngine)

    def test_counterfactual_preflight_requires_exact_three_case_names_per_input(self) -> None:
        required = {
            "perfect_forecast_copperplate",
            "realised_copperplate",
            "zonal_final",
        }
        base_dispatch = {case: {"wind": 0.0} for case in required}
        base_hashes = {case: "a" * 64 for case in required}
        base_identities = {case: f"{case}@1.0.0" for case in required}

        for input_name in (
            "dispatch_by_case",
            "realised_input_sha256_by_case",
            "module_identities",
        ):
            with self.subTest(input_name=input_name):
                dispatch = dict(base_dispatch)
                hashes = dict(base_hashes)
                identities = dict(base_identities)
                selected = {
                    "dispatch_by_case": dispatch,
                    "realised_input_sha256_by_case": hashes,
                    "module_identities": identities,
                }[input_name]
                selected.pop("zonal_final")
                selected["unexpected_case"] = (
                    {"wind": 0.0}
                    if input_name == "dispatch_by_case"
                    else (
                        "a" * 64
                        if input_name == "realised_input_sha256_by_case"
                        else "unexpected@1.0.0"
                    )
                )

                with self.assertRaises(CurtailmentAttributionError) as caught:
                    _validate_vre_counterfactual_cases(
                        expected_keys={("wind", "tranche")},
                        canonical_key_by_asset={"wind": ("wind", "tranche")},
                        dispatch_by_case=dispatch,
                        realised_input_sha256_by_case=hashes,
                        module_identities=identities,
                    )

                self.assertEqual(
                    caught.exception.code,
                    "GF_VRE_COUNTERFACTUAL_SET_MISMATCH",
                )
                self.assertEqual(
                    caught.exception.evidence["missing_case_names_by_input"][
                        input_name
                    ],
                    ["zonal_final"],
                )
                self.assertEqual(
                    caught.exception.evidence["extra_case_names_by_input"][
                        input_name
                    ],
                    ["unexpected_case"],
                )

    def test_counterfactual_preflight_distinguishes_explicit_zero_from_missing_key(self) -> None:
        cases = (
            "perfect_forecast_copperplate",
            "realised_copperplate",
            "zonal_final",
        )
        hashes = {case: "a" * 64 for case in cases}
        identities = {case: f"{case}@1.0.0" for case in cases}
        explicit_zero = {case: {"wind": 0.0} for case in cases}

        self.assertEqual(
            _validate_vre_counterfactual_cases(
                expected_keys={("wind", "tranche")},
                canonical_key_by_asset={"wind": ("wind", "tranche")},
                dispatch_by_case=explicit_zero,
                realised_input_sha256_by_case=hashes,
                module_identities=identities,
            ),
            "a" * 64,
        )

        missing = {case: dict(values) for case, values in explicit_zero.items()}
        missing["zonal_final"].pop("wind")
        with self.assertRaises(CurtailmentAttributionError) as caught:
            _validate_vre_counterfactual_cases(
                expected_keys={("wind", "tranche")},
                canonical_key_by_asset={"wind": ("wind", "tranche")},
                dispatch_by_case=missing,
                realised_input_sha256_by_case=hashes,
                module_identities=identities,
            )
        self.assertEqual(
            caught.exception.evidence["missing_keys_by_case"]["zonal_final"],
            [{"asset_id": "wind", "bid_tranche_id": "tranche"}],
        )

    def test_counterfactual_preflight_rejects_mismatched_realised_input_hashes(self) -> None:
        case_dispatch = {
            "perfect_forecast_copperplate": {"wind": 0.0},
            "realised_copperplate": {"wind": 0.0},
            "zonal_final": {"wind": 0.0},
        }
        with self.assertRaises(CurtailmentAttributionError) as caught:
            _validate_vre_counterfactual_cases(
                expected_keys={("wind", "tranche")},
                canonical_key_by_asset={"wind": ("wind", "tranche")},
                dispatch_by_case=case_dispatch,
                realised_input_sha256_by_case={
                    "perfect_forecast_copperplate": "a" * 64,
                    "realised_copperplate": "a" * 64,
                    "zonal_final": "b" * 64,
                },
                module_identities={
                    "perfect_forecast_copperplate": "value-copperplate-balancing@1.0.0",
                    "realised_copperplate": "value-copperplate-balancing@1.0.0",
                    "zonal_final": "value-zonal-redispatch-balancing@1.0.0",
                },
            )

        self.assertEqual(caught.exception.code, "GF_VRE_COUNTERFACTUAL_SET_MISMATCH")
        self.assertEqual(
            caught.exception.evidence["realised_input_sha256_by_case"]["zonal_final"],
            "b" * 64,
        )

    def test_live_zonal_path_saves_raw_evidence_when_a_vre_key_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            psm = StagedBidAtCostPSM()
            balancing = _MissingVREKeyBalancing()
            psm.configure_run(
                output_dir=Path(temporary),
                storage_cost=_PriorityStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=_redispatch_avoids_curtailment_network(),
                zonal_demand_mode="scenario_scaled_zonal_shares",
            )
            with self.assertRaises(CurtailmentAttributionError) as caught:
                _run_contextual(
                    psm, balancing, _redispatch_avoids_curtailment_input()
                )
            failures = sorted(
                (Path(temporary) / "market" / "failures").glob(
                    "vre-curtailment-attribution-*.json"
                )
            )
            self.assertEqual(len(failures), 1)
            payload = json.loads(failures[0].read_text(encoding="utf-8"))

        self.assertEqual(caught.exception.code, "GF_VRE_COUNTERFACTUAL_SET_MISMATCH")
        self.assertEqual(payload["error_code"], caught.exception.code)
        diagnostics = payload["raw_case_diagnostics"]
        missing = diagnostics["missing_keys_by_case"]["zonal_final"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["asset_id"], "offshore")
        self.assertIn(missing[0], diagnostics["canonical_vre_keys"])
        self.assertEqual(
            set(payload["module_identities"]),
            {
                "perfect_forecast_copperplate",
                "realised_copperplate",
                "zonal_final",
            },
        )

    def test_live_zonal_path_rejects_negative_raw_vre_dispatch_with_atomic_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            psm = StagedBidAtCostPSM()
            balancing = _NegativeVREDispatchBalancing()
            psm.configure_run(
                output_dir=Path(temporary),
                storage_cost=_PriorityStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=_redispatch_avoids_curtailment_network(),
                zonal_demand_mode="scenario_scaled_zonal_shares",
            )
            with self.assertRaises(CurtailmentAttributionError) as caught:
                _run_contextual(
                    psm, balancing, _redispatch_avoids_curtailment_input()
                )
            failures = sorted(
                (Path(temporary) / "market" / "failures").glob(
                    "vre-curtailment-attribution-*.json"
                )
            )
            self.assertEqual(len(failures), 1)
            payload = json.loads(failures[0].read_text(encoding="utf-8"))
            self.assertEqual(
                list((Path(temporary) / "market" / "failures").glob(".*.tmp")),
                [],
            )
            with closing(
                sqlite3.connect(Path(temporary) / "market" / "market.sqlite")
            ) as connection:
                diagnostic_rows = connection.execute(
                    "SELECT COUNT(*) FROM network_solver_diagnostics"
                ).fetchone()[0]

        self.assertEqual(
            caught.exception.code,
            "GF_VRE_DISPATCH_EXCEEDS_AVAILABILITY",
        )
        self.assertEqual(payload["error_code"], caught.exception.code)
        self.assertEqual(diagnostic_rows, 0)
        offshore = next(
            row for row in payload["raw_snapshot"]["rows"]
            if row["asset_id"] == "offshore"
        )
        self.assertEqual(offshore["zonal_final_dispatch_mwh"], -1.0)

    def test_live_zonal_path_records_redispatch_avoided_vre_curtailment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            psm = StagedBidAtCostPSM()
            balancing = ZonalRedispatchBalancing()
            psm.configure_run(
                output_dir=Path(temporary),
                storage_cost=_PriorityStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=_redispatch_avoids_curtailment_network(),
                zonal_demand_mode="scenario_scaled_zonal_shares",
                ledger_detail="full",
            )
            _run_contextual(
                psm, balancing, _redispatch_avoids_curtailment_input()
            )
            with closing(
                sqlite3.connect(Path(temporary) / "market" / "market.sqlite")
            ) as connection:
                connection.row_factory = sqlite3.Row
                period = dict(connection.execute(
                    "SELECT * FROM vre_curtailment_period"
                ).fetchone())
                technologies = {
                    row[0]
                    for row in connection.execute(
                        "SELECT technology FROM vre_curtailment_detail"
                    )
                }

        self.assertEqual(period["realised_available_vre_mwh"], 10.0)
        self.assertEqual(period["copperplate_reference_dispatch_mwh"], 7.0)
        self.assertEqual(period["zonal_final_dispatch_mwh"], 10.0)
        self.assertEqual(period["redispatch_added_curtailment_mwh"], 0.0)
        self.assertEqual(period["redispatch_avoided_curtailment_mwh"], 3.0)
        self.assertEqual(period["redispatch_net_impact_mwh"], -3.0)
        self.assertEqual(period["total_curtailment_mwh"], 0.0)
        self.assertEqual(technologies, {"Onshore wind", "Offshore wind"})

    def test_live_zonal_path_scales_network_shares_to_research_demand(self) -> None:
        network = replace(
            _network_pack(),
            zonal_demand=ZonalDemand(
                ("p0",), {"north": (2.0,), "south": (6.0,)}, (8.0,)
            ),
        )
        network = replace(
            network, scientific_sha256=network.compute_scientific_sha256()
        )
        with tempfile.TemporaryDirectory() as temporary:
            psm = StagedBidAtCostPSM()
            balancing = ZonalRedispatchBalancing()
            psm.configure_run(
                output_dir=Path(temporary),
                storage_cost=_FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=network,
                zonal_demand_mode="scenario_scaled_zonal_shares",
            )
            result = _run_contextual(psm, balancing, _zonal_input())
            with closing(
                sqlite3.connect(Path(temporary) / "market" / "market.sqlite")
            ) as connection:
                zonal_total = connection.execute(
                    "SELECT SUM(demand_mwh) FROM zone_period_summary"
                ).fetchone()[0]
                alignment = connection.execute(
                    "SELECT demand_mode, research_real_demand_mwh, "
                    "network_national_demand_mwh, scale_factor, "
                    "aligned_zonal_total_mwh, conservation_residual_mwh "
                    "FROM zonal_demand_alignment"
                ).fetchone()

        self.assertAlmostEqual(zonal_total, 10.0)
        self.assertEqual(alignment[0], "scenario_scaled_zonal_shares")
        self.assertEqual(tuple(alignment[1:]), (10.0, 8.0, 1.25, 10.0, 0.0))
        self.assertEqual(
            result.extensions["zonal_demand_alignment"]["mode"],
            "scenario_scaled_zonal_shares",
        )
        comparison = result.extensions["comparison_input_evidence"]
        self.assertEqual(comparison["year"], 2025)
        self.assertEqual(comparison["period_count"], 1)
        self.assertEqual(comparison["real_demand_mwh"], 10.0)
        self.assertEqual(comparison["forecast_demand_mwh"], 10.0)
        self.assertEqual(len(comparison["input_identity_sha256"]), 64)

    def test_live_zonal_path_commits_final_dispatch_soc_and_owner_cashflow_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            psm = StagedBidAtCostPSM()
            balancing = ZonalRedispatchBalancing()
            psm.configure_run(
                output_dir=Path(temporary),
                storage_cost=_FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=_network_pack(),
                zonal_demand_mode="scenario_scaled_zonal_shares",
                ledger_detail="full",
            )
            result = _run_contextual(psm, balancing, _zonal_input())
            ledger_path = Path(temporary) / "market" / "market.sqlite"
            self.assertTrue(ledger_path.is_file())
            with closing(sqlite3.connect(ledger_path)) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM zonal_period_summary").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM zonal_period_accounting").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM vre_curtailment_period").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM zonal_resource_dispatch").fetchone()[0],
                    3,
                )
                accounts = connection.execute(
                    "SELECT national_settlement_gbp, redispatch_settlement_gbp, "
                    "system_resource_cost_gbp FROM zonal_period_accounting"
                ).fetchone()
                primary_diagnostic = connection.execute(
                    "SELECT optimum, achieved_final_value, degradation, "
                    "computed_tolerance, validated_ceiling "
                    "FROM network_solver_diagnostics "
                    "WHERE phase_id='primary_bid_cost'"
                ).fetchone()
                quantity_tolerances = dict(connection.execute(
                    "SELECT phase_id, validated_ceiling "
                    "FROM network_solver_diagnostics "
                    "WHERE phase_id IN "
                    "('secondary_schedule_deviation', 'physical_throughput')"
                ))
                self.assertEqual(accounts[1], primary_diagnostic[1])
                self.assertLessEqual(
                    primary_diagnostic[2], primary_diagnostic[3]
                )
                self.assertAlmostEqual(accounts[0], 0.0)
                self.assertAlmostEqual(
                    accounts[1], 440.0, delta=primary_diagnostic[3]
                )
                self.assertAlmostEqual(
                    accounts[2], 402.0, delta=primary_diagnostic[4]
                )

        self.assertAlmostEqual(
            result.generation_mwh_by_asset["wind"],
            4.0,
            delta=quantity_tolerances["secondary_schedule_deviation"],
        )
        self.assertAlmostEqual(
            result.generation_mwh_by_asset["ccgt"],
            4.0,
            delta=quantity_tolerances["secondary_schedule_deviation"],
        )
        self.assertAlmostEqual(
            result.extensions["final_storage_soc_mwh_by_asset"]["battery"],
            0.0,
            delta=quantity_tolerances["physical_throughput"],
        )
        self.assertAlmostEqual(
            result.extensions["actual_storage_discharge_mwh_by_asset"]["battery"],
            2.0,
            delta=quantity_tolerances["physical_throughput"],
        )
        self.assertAlmostEqual(
            result.market_income_gbp_by_agent["storage-owner"],
            40.0,
            delta=primary_diagnostic[4],
        )
        self.assertAlmostEqual(
            result.market_income_gbp_by_agent["thermal-owner"],
            400.0,
            delta=primary_diagnostic[4],
        )
        self.assertEqual(
            sum(result.market_income_gbp_by_agent.values()), accounts[1]
        )
        self.assertNotIn("battery", result.market_income_gbp_by_agent)
        self.assertEqual(result.extensions["network_pack"]["network_pack_id"], "fixture-network")
        annual_ledger = build_cem_cost_ledger(result)
        self.assertEqual(annual_ledger.status, "reconciled")
        self.assertEqual(
            next(
                row.amount_gbp for row in annual_ledger.lines
                if row.view == "redispatch_settlement"
            ),
            accounts[1],
        )

    def test_cem_reads_owner_cashflow_once_instead_of_duplicate_physical_children(self) -> None:
        model_input = _zonal_input()
        with tempfile.TemporaryDirectory() as temporary:
            psm = StagedBidAtCostPSM()
            balancing = ZonalRedispatchBalancing()
            psm.configure_run(
                output_dir=Path(temporary), storage_cost=_FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=_network_pack(),
                zonal_demand_mode="scenario_scaled_zonal_shares",
            )
            market = _run_contextual(psm, balancing, model_input)
        decision = SchemeCAgentInvestmentDefinition().decide(
            _resolved_run(), model_input.operating_state,
            adapt_market_for_investment(market, model_input.operating_state),
            (ExpansionHeadroom("h", 2025, "cap", {"CCGT": 100.0, "1c_battery": 100.0, "onshore": 100.0}),),
        )
        self.assertEqual(decision.extensions["grouped_investment_owners"], 3)
        # P0-7 S4 (A4, p07.thermal-net-revenue): the thermal owner's income and
        # running cost are each read once (4 MWh at 100 GBP/MWh, not twice for
        # the physical zone children); the CCGT is paid exactly its marginal
        # cost, so its net revenue is 0 and it proposes nothing (HEAD: one
        # proposal on gross revenue).
        thermal_cost = decision.extensions["a4_net_revenue"]["thermal_operating_cost_gbp_by_group"]
        self.assertEqual(list(thermal_cost), ["thermal-owner|CCGT|south"])
        self.assertAlmostEqual(thermal_cost["thermal-owner|CCGT|south"], 400.0, places=4)
        self.assertEqual(
            sum(1 for proposal in decision.proposals if proposal.agent_id == "thermal-owner"),
            0,
        )

    def test_unvalidated_solver_year_continues_cem_and_is_inherited_without_relaxing_balance(self) -> None:
        first_input = _zonal_input()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            psm = StagedBidAtCostPSM()
            balancing = _InjectedUnvalidatedBalancing()
            psm.configure_run(
                output_dir=root / "2025",
                storage_cost=_FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=_network_pack(),
                zonal_demand_mode="scenario_scaled_zonal_shares",
            )
            first_market = _run_contextual(psm, balancing, first_input)
            first_summary = first_market.extensions["solver_validation_summary"]

            decision = SchemeCAgentInvestmentDefinition().decide(
                _resolved_run(),
                first_input.operating_state,
                adapt_market_for_investment(
                    first_market, first_input.operating_state
                ),
                (ExpansionHeadroom(
                    "h", 2025, "cap",
                    {"CCGT": 100.0, "1c_battery": 100.0, "onshore": 100.0},
                ),),
            )

            inherited_state = replace(
                first_input.operating_state,
                year=2026,
                extensions={"solver_validation_state": first_summary},
            )
            second_input = replace(
                first_input,
                year=2026,
                operating_state=inherited_state,
            )
            second_psm = StagedBidAtCostPSM()
            second_balancing = ZonalRedispatchBalancing()
            second_psm.configure_run(
                output_dir=root / "2026",
                storage_cost=_FlatStorageCostDefinition(),
                balancing=second_balancing,
                expected_balancing_identity=(
                    second_balancing.id, second_balancing.version
                ),
                network_pack=_network_pack(),
                zonal_demand_mode="scenario_scaled_zonal_shares",
            )
            second_market = _run_contextual(
                second_psm, second_balancing, second_input
            )
            second_summary = second_market.extensions["solver_validation_summary"]

            strict_ledger = SQLiteMarketLedger(
                root / "strict.sqlite", trace_level="summary"
            )
            with self.assertRaisesRegex(InvariantError, "energy balance"):
                strict_ledger.record_period(PeriodLedgerRow(
                    2026, 0, "final_dispatch", 10.0, 10.0, 9.0,
                    0.0, 0.0, 0.0, 0.0, 5.0, 5.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0,
                ))
            strict_ledger.close()

        self.assertIs(first_summary["solver_validated"], False)
        self.assertEqual(
            first_summary["annual_status"],
            "COMPLETED_WITH_NUMERICAL_WARNING",
        )
        self.assertTrue(decision.decision_id)
        self.assertIs(second_summary["solver_validated"], False)
        self.assertIs(second_summary["inherited_unvalidated"], True)
        self.assertEqual(
            second_summary["first_causal_period"],
            first_summary["first_causal_period"],
        )

    def test_new_abstract_capacity_inherits_owner_weighted_frozen_zone_shares(self) -> None:
        first = AssetStateV2(
            "owner-north", "CCGT", 20.0, region="GB",
            extensions={**_economics("one-owner"), "frozen_zone_shares": {"north": 1.0}, "spatial_pack_revision": "pack-r1"},
        )
        second = AssetStateV2(
            "owner-south", "CCGT", 10.0, region="GB",
            extensions={**_economics("one-owner"), "frozen_zone_shares": {"south": 1.0}, "spatial_pack_revision": "pack-r1"},
        )
        annual = MarketYearResult(
            "market", 2025, "fixture", "1", {}, {"one-owner": 1_000_000.0},
            0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0,
            extensions={
                "market_income_identity": "economic_owner",
                # P0-7 S4 (A4): the CEM needs the thermal running cost; none here.
                agent_cashflow.EXTENSION_KEY: agent_cashflow.extension({
                    asset_id: agent_cashflow.cashflow_row("CCGT", 0.0, {
                        "generation_cost_gbp_per_mwh": 50.0, "fuel_cost_gbp_per_mwh": 0.0,
                        "carbon_cost_gbp_per_mwh": 0.0, "unit_time_cost_gbp_per_mwh": 0.0,
                    }, cost_basis="fixture")
                    for asset_id in ("owner-north", "owner-south")
                }, psm_module_id="fixture", cost_basis="fixture"),
            },
        )
        state = OperatingState(2025, (first, second), ())
        decision = SchemeCAgentInvestmentDefinition().decide(
            _resolved_run(), state, adapt_market_for_investment(annual, state),
            (ExpansionHeadroom("h", 2025, "cap", {"CCGT": 100.0}),),
        )
        decision = inherit_frozen_zone_shares(decision, state)
        self.assertEqual(len(decision.proposals), 1)
        shares = decision.proposals[0].extensions["frozen_zone_shares"]
        self.assertAlmostEqual(shares["north"], 2.0 / 3.0)
        self.assertAlmostEqual(shares["south"], 1.0 / 3.0)
        self.assertEqual(decision.proposals[0].extensions["spatial_pack_revision"], "pack-r1")

    def test_commissioned_child_is_a_real_next_year_physical_resource(self) -> None:
        from gridform_core.canonical_psm_data import build_chronology
        from gridform_core.data_method import run_policy

        child = AssetStateV2(
            "commissioned:model:ccgt-1",
            "CCGT",
            10.0,
            region="GB",
            extensions={
                **_economics("thermal-owner"),
                "source_project_id": "model:ccgt-1",
                "frozen_zone_shares": {"south": 1.0},
                "spatial_pack_revision": "fixture-network",
            },
        )
        state = OperatingState(2026, (child,), ())
        manifest = json.loads((BASELINE / "manifest.json").read_text(encoding="utf-8"))
        raw = build_chronology(
            BASELINE,
            manifest,
            state,
            periods=1,
            period_hours=1.0,
            data_policy=run_policy(manifest),
            terminal_soc_rule="free",
            voll_gbp_per_mwh=17_000.0,
        )
        child_resource = next(
            resource for resource in raw.resources if resource.asset_id == child.asset_id
        )
        chronology = replace(
            raw,
            period_ids=("p0",),
            demand_mwh=(10.0,),
            resources=(child_resource,),
            storage=(),
            extensions={**dict(raw.extensions), "forecast_demand_mwh": (10.0,)},
        )
        psm = StagedBidAtCostPSM()
        balancing = ZonalRedispatchBalancing()
        with tempfile.TemporaryDirectory() as temporary:
            psm.configure_run(
                output_dir=Path(temporary),
                storage_cost=_FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=_network_pack(),
                zonal_demand_mode="scenario_scaled_zonal_shares",
            )
            result = _run_contextual(psm, balancing, PSMInput(
                "prompt101-next-year",
                2026,
                "value-101-baseline-v1",
                state,
                1.0,
                {"market.bid_multiplier": 1.0},
                chronology=chronology,
            ))
            with closing(
                sqlite3.connect(Path(temporary) / "market" / "market.sqlite")
            ) as connection:
                vre_period = connection.execute(
                    "SELECT realised_available_vre_mwh, "
                    "perfect_reference_dispatch_mwh, "
                    "copperplate_reference_dispatch_mwh, "
                    "zonal_final_dispatch_mwh, total_curtailment_mwh, "
                    "identity_residual_mwh FROM vre_curtailment_period"
                ).fetchall()
        self.assertAlmostEqual(result.generation_mwh_by_asset[child.asset_id], 10.0)
        self.assertIn("thermal-owner", result.market_income_gbp_by_agent)
        self.assertEqual(
            result.extensions["final_dispatch_mwh_by_physical_asset"][child.asset_id],
            10.0,
        )
        self.assertEqual(vre_period, [(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)])


class Prompt101StudyAndReleaseContractTests(unittest.TestCase):
    def test_zonal_study_requires_one_explicit_supported_demand_mode(self) -> None:
        modules = {
            "psm": "value-staged-bid-at-cost-psm",
            "balancing": "value-zonal-redispatch-balancing",
        }
        with self.assertRaisesRegex(ValueError, "zonal_demand_mode"):
            resolve_market_configuration(modules, {}, {}, {"network_pack_id": "signed"})

        for mode in (
            "scenario_scaled_zonal_shares",
            "network_pack_absolute_demand",
        ):
            with self.subTest(mode=mode):
                resolved = resolve_market_configuration(
                    modules,
                    {},
                    {},
                    {"network_pack_id": "signed", "zonal_demand_mode": mode},
                )
                self.assertEqual(resolved["zonal_demand_mode"], mode)

        copperplate = resolve_market_configuration(
            {**modules, "balancing": "value-copperplate-balancing"}, {}, {}, {}
        )
        self.assertEqual(copperplate["zonal_demand_mode"], "")

    def test_v1_migration_adds_explicit_market_fields_without_changing_module_semantics(self) -> None:
        old = {
            "schema_version": "value.project/v1",
            "id": "legacy",
            "name": "Legacy",
            "data_pack_id": "pack",
            "modules": {
                "psm": "value-staged-bid-at-cost-psm",
                "balancing": "value-copperplate-balancing",
            },
            "parameters": {"market.voll_gbp_per_mwh": 17_000.0},
            "runtime_options": {"runtime.market_trace_level": "full"},
        }
        migrated = migrate_project_v1(old)
        fields = migrated["market_configuration"]
        self.assertEqual(fields["ahead_market_module_id"], old["modules"]["psm"])
        self.assertEqual(fields["balancing_module_id"], old["modules"]["balancing"])
        self.assertEqual(fields["voll_gbp_per_mwh"], 17_000.0)
        self.assertEqual(fields["ledger_detail"], "full")

    def test_v1_migration_preserves_explicit_zonal_demand_authority(self) -> None:
        old = {
            "schema_version": "value.project/v1",
            "id": "zonal-v1",
            "name": "Zonal v1",
            "data_pack_id": "pack",
            "modules": {
                "psm": "value-staged-bid-at-cost-psm",
                "balancing": "value-zonal-redispatch-balancing",
            },
            "market_configuration": {
                "ahead_market_module_id": "value-staged-bid-at-cost-psm",
                "balancing_module_id": "value-zonal-redispatch-balancing",
                "network_pack_id": "signed-network",
                "zonal_demand_mode": "scenario_scaled_zonal_shares",
                "weather_spatialisation_module_id": "",
                "ledger_detail": "summary",
                "voll_gbp_per_mwh": 10_000.0,
            },
        }
        migrated = migrate_project_v1(old)
        self.assertEqual(
            migrated["market_configuration"]["zonal_demand_mode"],
            "scenario_scaled_zonal_shares",
        )
        self.assertEqual(
            migrated["market_configuration"]["network_pack_id"],
            "signed-network",
        )

    def test_explicit_market_fields_must_match_authoritative_module_selection(self) -> None:
        payload = migrate_project_v1({
            "schema_version": "value.project/v1", "id": "legacy", "name": "Legacy",
            "data_pack_id": "pack", "modules": {"psm": "value-staged-bid-at-cost-psm", "balancing": "value-copperplate-balancing"},
        })
        payload["market_configuration"]["balancing_module_id"] = "value-zonal-redispatch-balancing"
        with self.assertRaisesRegex(ValueError, "market configuration.*balancing"):
            parse_project(payload, MODULE_REGISTRY)

    def test_transmission_expansion_implementation_is_not_user_selectable(self) -> None:
        slots = module_slot_catalog(MODULE_REGISTRY, MODULES)
        self.assertNotIn("network_expansion", {row["slot"] for row in slots})
        self.assertTrue((Path(__file__).resolve().parents[1] / "gridform_core" / "network_expansion.py").is_file())

    def test_copperplate_rerun_is_a_new_immutable_lineage_not_a_fallback(self) -> None:
        source = {
            "schema_version": "value.project/v2",
            "id": "zonal",
            "modules": {
                "psm": "value-staged-bid-at-cost-psm",
                "balancing": "value-zonal-redispatch-balancing",
            },
            "market_configuration": {
                "ahead_market_module_id": "value-staged-bid-at-cost-psm",
                "balancing_module_id": "value-zonal-redispatch-balancing",
                "network_pack_id": "signed-pack",
                "zonal_demand_mode": "scenario_scaled_zonal_shares",
            },
            "revision_sha256": "f" * 64,
        }
        rerun, lineage = copperplate_rerun_project(source, parent_run_id="failed-zonal")
        self.assertEqual(source["modules"]["balancing"], "value-zonal-redispatch-balancing")
        self.assertEqual(rerun["modules"]["balancing"], "value-copperplate-balancing")
        self.assertEqual(rerun["market_configuration"]["zonal_demand_mode"], "")
        self.assertNotIn("revision_sha256", rerun)
        self.assertEqual(lineage["comparison_parent_run_id"], "failed-zonal")
        self.assertFalse(lineage["automatic_fallback_used"])


if __name__ == "__main__":
    unittest.main()
