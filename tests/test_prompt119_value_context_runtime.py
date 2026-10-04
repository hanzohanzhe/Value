from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import patch

from gridform_core.builtin.scheme_c_1000twh.staged_psm import StagedBidAtCostPSM
from gridform_core.module_context import (
    ImmutableContextResolver,
    RunContextRef,
    RunStaticContext,
    YearContext,
    YearContextRef,
    canonical_context_sha256,
)
from gridform_core.staged_market_contracts import (
    AheadMarketResult,
    BalancingInput,
    ZonalRedispatchDomainV2,
    contract_sha256,
)
from gridform_core.v2.contracts import (
    AssetStateV2,
    ChronologicalPSMData,
    ExpansionHeadroom,
    InvestmentDecision,
    MarketYearResult,
    ModuleSelection,
    OperatingState,
    PlanningAdmissionResult,
    PlanningAdvanceResult,
    PSMInput,
    ResolvedRun,
    DispatchResource,
    YearState,
)
from gridform_core.v2 import orchestrator as orchestrator_module
from gridform_core.v2.orchestrator import AnnualModelOrchestratorV2
from gridform_core.zonal_contracts import (
    NetworkZone,
    SpatialAudit,
    ZonalAssetMapping,
    ZonalDemand,
    ZonalNetworkPack,
)
from gridform_core.zonal_redispatch import (
    ZonalRedispatchBalancing,
    ZonalRedispatchInputError,
)


class _FlatStorageCost:
    def prepare_year(self, _year: int, **_kwargs: object) -> None:
        pass

    def bid_price_gbp_per_mwh(self, _dwell_periods: float) -> float:
        return 0.0

    def record_sale(self, _delivered_mwh: float, _dwell_periods: float) -> None:
        pass

    def report(self) -> dict[str, object]:
        return {"method": "fixture"}


class _FlatStorageCostDefinition:
    id = "fixture-storage-cost"
    version = "1.0.0"

    @staticmethod
    def create(**_kwargs: object) -> _FlatStorageCost:
        return _FlatStorageCost()


class _CapturingZonalBalancing(ZonalRedispatchBalancing):
    def __init__(self) -> None:
        super().__init__()
        self.captured: list[BalancingInput] = []

    def clear(self, model_input: BalancingInput):
        self.captured.append(model_input)
        return super().clear(model_input)


def _network_pack(period_count: int = 48) -> ZonalNetworkPack:
    period_ids = tuple(f"p{index}" for index in range(period_count))
    pack = ZonalNetworkPack(
        "prompt119-network",
        "",
        (NetworkZone("gb", "GB", "Fixture DSO", "England"),),
        (),
        (),
        (ZonalAssetMapping("generator", "gb", "generator", "CCGT", 1.0, "fixture"),),
        ZonalDemand(
            period_ids,
            {"gb": tuple(1.0 for _ in period_ids)},
            tuple(1.0 for _ in period_ids),
        ),
        (),
        (),
        SpatialAudit((), {}, {}, 1e-9),
        "lossless_v1",
    )
    return replace(pack, scientific_sha256=pack.compute_scientific_sha256())


def _psm_input(
    period_count: int = 48,
    *,
    run_id: str = "prompt119-run",
    year: int = 2025,
) -> PSMInput:
    period_ids = tuple(f"p{index}" for index in range(period_count))
    asset = AssetStateV2(
        "generator",
        "CCGT",
        1.0,
        region="gb",
        extensions={
            "capital_cost_per_mw": 0.0,
            "capital_cost_per_mwh": 0.0,
            "total_capex_gbp": 0.0,
            "annual_fixed_opex_gbp": 0.0,
            "economic_lifetime_years": 25.0,
            "capital_discount_rate": 0.0,
            "annualized_capital_cost_gbp": 0.0,
            "fixed_om_basis": "fixture",
            "asset_economics_schema_version": "value.asset-economics/v1",
        },
    )
    chronology = ChronologicalPSMData(
        period_ids,
        tuple(1.0 for _ in period_ids),
        (
            DispatchResource(
                "generator",
                "CCGT",
                "thermal",
                1.0,
                10.0,
                tuple(1.0 for _ in period_ids),
                extensions={"agent_id": "generator-owner"},
            ),
        ),
        (),
        17_000.0,
        terminal_soc_rule="free",
        extensions={"forecast_demand_mwh": tuple(1.0 for _ in period_ids)},
    )
    return PSMInput(
        run_id,
        year,
        "fixture-data-pack",
        OperatingState(year, (asset,), ()),
        1.0,
        {"market.bid_multiplier": 1.0},
        chronology=chronology,
    )


def _run_context(pack: ZonalNetworkPack, *, end_year: int = 2025) -> RunStaticContext:
    return RunStaticContext(
        run_id="prompt119-run",
        study_revision_sha256="a" * 64,
        start_year=2025,
        end_year=end_year,
        period_hours=1.0,
        data_pack={"data_pack_id": "fixture-data-pack", "manifest_sha256": "b" * 64},
        module_graph={"graph_sha256": "c" * 64},
        scientific_parameters={"clock.period_hours": 1.0},
        runtime_controls={"runtime.market_trace_level": "summary"},
        trace_profile="summary",
        solver_contract={},
        market_configuration={"zonal_demand_mode": "network_pack_absolute_demand"},
        network_pack=pack.to_dict(),
    )


def _year_context(run_context: RunStaticContext, model_input: PSMInput) -> YearContext:
    return YearContext(
        run_id=model_input.run_id,
        year=model_input.year,
        run_context_sha256=canonical_context_sha256(run_context),
        operating_state={
            **model_input.operating_state.to_dict(),
            "asset_zone_id_by_asset": {"generator": "gb"},
            "resource_class_by_asset": {"generator": "thermal"},
            "resource_cost_gbp_per_mwh_by_asset": {"generator": 10.0},
            "storage": {},
        },
        frozen_zone_shares={"generator": {"gb": 1.0}},
        opening_soc_mwh_by_asset={},
        transition_lineage={"source_state_sha256": "d" * 64},
    )


def _configure_context_lifecycle(
    psm: StagedBidAtCostPSM,
    balancing: ZonalRedispatchBalancing,
    run_context: RunStaticContext,
    year_context: YearContext,
) -> None:
    configure = getattr(psm, "configure", None)
    start_year = getattr(psm, "start_year", None)
    if not callable(configure) or not callable(start_year):
        return
    resolver = ImmutableContextResolver(
        run_contexts=(run_context,),
        year_contexts=(year_context,),
        modules_by_slot={
            "psm": psm,
            "balancing": balancing,
            "storage_cost": _FlatStorageCostDefinition(),
        },
    )
    configure(run_context, resolver)
    start_year(year_context)


def _with_balancing_identity(
    declared: BalancingInput,
    *,
    run_id: str | None = None,
    year: int | None = None,
) -> BalancingInput:
    payload = declared.to_dict()
    ahead = payload["domain_payload"]["period_slice"]["ahead_result"]
    if run_id is not None:
        payload["run_id"] = run_id
        ahead["run_id"] = run_id
    if year is not None:
        payload["year"] = year
        ahead["year"] = year
    payload["ahead_result_sha256"] = contract_sha256(ahead)
    return BalancingInput.from_dict(payload)


class Prompt119ContextRuntimeTests(unittest.TestCase):
    def test_48_period_zonal_run_binds_pack_once_and_passes_compact_v2_slices(self) -> None:
        pack = _network_pack()
        model_input = _psm_input()
        run_context = _run_context(pack)
        year_context = _year_context(run_context, model_input)
        psm = StagedBidAtCostPSM()
        balancing = _CapturingZonalBalancing()

        with patch.object(
            ZonalNetworkPack,
            "validate",
            autospec=True,
            wraps=ZonalNetworkPack.validate,
        ) as validate:
            pack.validate()
            psm.configure_run(
                output_dir=None,
                storage_cost=_FlatStorageCostDefinition(),
                balancing=balancing,
                expected_balancing_identity=(balancing.id, balancing.version),
                network_pack=pack,
                zonal_demand_mode="network_pack_absolute_demand",
            )
            _configure_context_lifecycle(psm, balancing, run_context, year_context)
            psm.run(model_input)

        self.assertEqual(validate.call_count, 1)
        self.assertEqual(len(balancing.captured), 48)
        for row in balancing.captured:
            self.assertEqual(row.schema_version, "value.balancing-input/v1")
            payload = row.to_dict()["domain_payload"]
            self.assertEqual(payload["schema_version"], "value.zonal-redispatch-domain/v2")
            serialized = json.dumps(payload, sort_keys=True)
            self.assertNotIn("network_pack", serialized)
            self.assertLess(len(serialized.encode("utf-8")), 250_000)
            domain = ZonalRedispatchDomainV2.from_dict(payload)
            self.assertIsInstance(domain.period_slice.ahead_result, AheadMarketResult)

    def test_two_year_contexts_follow_transition_and_preserve_prior_bytes(self) -> None:
        run = _orchestrator_run()
        run_context = _run_context(_network_pack(2), end_year=2026)
        calls: list[tuple[int, str]] = []
        with tempfile.TemporaryDirectory() as folder:
            context_dir = Path(folder) / "market" / "context"
            psm = _ContextPSM(calls, context_dir)
            resolver = ImmutableContextResolver(
                run_contexts=(run_context,),
                year_contexts=(),
                modules_by_slot={"psm": psm},
            )
            orchestrator = AnnualModelOrchestratorV2(
                psm,
                {"vre_cap": _Cap("vre_cap"), "storage_cap": _Cap("storage_cap")},
                _Investment(),
                _Pipeline(),
                _CommissioningTransition(),
                run_context=run_context,
                context_resolver=resolver,
                context_directory=context_dir,
            )
            orchestrator.run(
                run,
                YearState(2025, (AssetStateV2("existing", "CCGT", 1.0),), ()),
            )
            after_transition = (context_dir / "year-2025.json").read_bytes()

        self.assertEqual([context.year for context in psm.contexts], [2025, 2026])
        self.assertNotEqual(
            canonical_context_sha256(psm.contexts[0]),
            canonical_context_sha256(psm.contexts[1]),
        )
        self.assertEqual(after_transition, psm.first_year_bytes)
        assets_2026 = {
            row["asset_id"] for row in psm.contexts[1].operating_state["assets"]
        }
        self.assertIn("commissioned:project-2025", assets_2026)
        self.assertIn("commissioned:project-2025", psm.psm_assets_by_year[2026])
        for context in psm.contexts:
            reference = YearContextRef(context.year, canonical_context_sha256(context))
            self.assertEqual(resolver.resolve_year(reference), context)

    def test_authorized_resume_lineage_does_not_alias_run_context_content(self) -> None:
        pack = _network_pack(1)
        model_input = _psm_input(1)
        runtime_context = _run_context(pack)
        historical_run_context_sha256 = "e" * 64
        year_context = YearContext(
            run_id=model_input.run_id,
            year=model_input.year,
            run_context_sha256=historical_run_context_sha256,
            operating_state={
                **model_input.operating_state.to_dict(),
                "asset_zone_id_by_asset": {"generator": "gb"},
                "resource_class_by_asset": {"generator": "thermal"},
                "resource_cost_gbp_per_mwh_by_asset": {"generator": 10.0},
                "storage": {},
            },
            frozen_zone_shares={"generator": {"gb": 1.0}},
            opening_soc_mwh_by_asset={},
            transition_lineage={"source_state_sha256": "d" * 64},
        )
        psm = StagedBidAtCostPSM()
        balancing = _CapturingZonalBalancing()
        psm.configure_run(
            output_dir=None,
            storage_cost=_FlatStorageCostDefinition(),
            balancing=balancing,
            expected_balancing_identity=(balancing.id, balancing.version),
            network_pack=pack,
            zonal_demand_mode="network_pack_absolute_demand",
        )
        resolver = ImmutableContextResolver(
            run_contexts=(runtime_context,),
            year_contexts=(),
            modules_by_slot={"psm": psm, "balancing": balancing},
            authorized_year_run_context_sha256=(historical_run_context_sha256,),
        )
        psm.configure(runtime_context, resolver)
        psm.bind_resume_run_context(historical_run_context_sha256)
        with tempfile.TemporaryDirectory() as folder:
            orchestrator_module.publish_year_context(
                resolver,
                runtime_context,
                year_context,
                Path(folder),
                run_context_sha256=historical_run_context_sha256,
            )
        psm.start_year(year_context)

        self.assertEqual(
            resolver.resolve_year(
                YearContextRef(
                    year_context.year,
                    canonical_context_sha256(year_context),
                )
            ),
            year_context,
        )
        with self.assertRaisesRegex(ValueError, "not bound"):
            resolver.resolve_run(RunContextRef(historical_run_context_sha256))

    def test_zonal_clear_fails_closed_for_wrong_or_unbound_context_refs(self) -> None:
        pack = _network_pack(1)
        model_input = _psm_input(1)
        run_context = _run_context(pack)
        year_context = _year_context(run_context, model_input)
        psm = StagedBidAtCostPSM()
        balancing = _CapturingZonalBalancing()
        pack.validate()
        psm.configure_run(
            output_dir=None,
            storage_cost=_FlatStorageCostDefinition(),
            balancing=balancing,
            expected_balancing_identity=(balancing.id, balancing.version),
            network_pack=pack,
            zonal_demand_mode="network_pack_absolute_demand",
        )
        _configure_context_lifecycle(psm, balancing, run_context, year_context)
        psm.run(model_input)
        declared = balancing.captured[0]
        payload = declared.to_dict()
        payload["domain_payload"]["run_context_ref"]["sha256"] = "0" * 64
        wrong_run = BalancingInput.from_dict(payload)
        with self.assertRaises(ZonalRedispatchInputError):
            balancing.clear(wrong_run)

        payload = declared.to_dict()
        payload["domain_payload"]["year_context_ref"]["sha256"] = "0" * 64
        wrong_year = BalancingInput.from_dict(payload)
        with self.assertRaises(ZonalRedispatchInputError):
            balancing.clear(wrong_year)

        with self.assertRaises(ZonalRedispatchInputError):
            ZonalRedispatchBalancing().clear(declared)

    def test_zonal_clear_cross_checks_resolved_context_run_and_year_identity(self) -> None:
        pack = _network_pack(1)
        input_2025 = _psm_input(1)
        input_2026 = _psm_input(1, year=2026)
        run_context = _run_context(pack, end_year=2026)
        context_2025 = _year_context(run_context, input_2025)
        context_2026 = _year_context(run_context, input_2026)
        psm = StagedBidAtCostPSM()
        balancing = _CapturingZonalBalancing()
        pack.validate()
        psm.configure_run(
            output_dir=None,
            storage_cost=_FlatStorageCostDefinition(),
            balancing=balancing,
            expected_balancing_identity=(balancing.id, balancing.version),
            network_pack=pack,
            zonal_demand_mode="network_pack_absolute_demand",
        )
        resolver = ImmutableContextResolver(
            run_contexts=(run_context,),
            year_contexts=(context_2025, context_2026),
            modules_by_slot={
                "psm": psm,
                "balancing": balancing,
                "storage_cost": _FlatStorageCostDefinition(),
            },
        )
        psm.configure(run_context, resolver)
        psm.start_year(context_2025)
        psm.run(input_2025)
        declared_2025 = balancing.captured[-1]

        for label, changed in (
            ("different run", _with_balancing_identity(
                declared_2025, run_id="different-run"
            )),
            ("different year", _with_balancing_identity(declared_2025, year=2026)),
        ):
            with self.subTest(label=label):
                with self.assertRaises(ZonalRedispatchInputError):
                    balancing.clear(changed)

        psm.start_year(context_2026)
        psm.run(input_2026)
        stale_payload = balancing.captured[-1].to_dict()
        stale_payload["domain_payload"]["year_context_ref"] = YearContextRef(
            2025, canonical_context_sha256(context_2025)
        ).to_dict()
        with self.assertRaises(ZonalRedispatchInputError):
            balancing.clear(BalancingInput.from_dict(stale_payload))

    def test_resolver_bind_year_is_idempotent_and_rejects_identity_conflicts(self) -> None:
        run_context = _run_context(_network_pack(1))
        year_context = _year_context(run_context, _psm_input(1))
        conflicting = replace(
            year_context,
            transition_lineage={"source_state_sha256": "e" * 64},
        )
        resolver = ImmutableContextResolver(
            run_contexts=(run_context,), year_contexts=(), modules_by_slot={}
        )
        bind_year = getattr(resolver, "bind_year", None)
        self.assertTrue(callable(bind_year), "resolver must expose public bind_year")

        expected = YearContextRef(2025, canonical_context_sha256(year_context))
        self.assertEqual(bind_year(year_context), expected)
        self.assertEqual(bind_year(year_context), expected)
        with self.assertRaisesRegex(ValueError, "different content"):
            bind_year(conflicting)
        with self.assertRaises(ValueError):
            resolver.resolve_year(
                YearContextRef(2025, canonical_context_sha256(conflicting))
            )

    def test_concurrent_year_bind_allows_exactly_one_digest_per_run_year(self) -> None:
        run_context = _run_context(_network_pack(1))
        first = _year_context(run_context, _psm_input(1))
        second = replace(
            first,
            transition_lineage={"source_state_sha256": "f" * 64},
        )
        resolver = ImmutableContextResolver(
            run_contexts=(run_context,), year_contexts=(), modules_by_slot={}
        )
        bind_year = getattr(resolver, "bind_year", None)
        self.assertTrue(callable(bind_year), "resolver must expose public bind_year")

        def bind(context: YearContext) -> object:
            try:
                return bind_year(context)
            except ValueError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = tuple(pool.map(bind, (first, second)))

        self.assertEqual(sum(isinstance(row, YearContextRef) for row in outcomes), 1)
        self.assertEqual(sum(isinstance(row, ValueError) for row in outcomes), 1)

    def test_year_context_publication_is_idempotent_and_preserves_conflicts(self) -> None:
        run_context = _run_context(_network_pack(1))
        year_context = _year_context(run_context, _psm_input(1))
        conflicting = replace(
            year_context,
            transition_lineage={"source_state_sha256": "e" * 64},
        )
        publish = getattr(orchestrator_module, "publish_year_context", None)
        self.assertTrue(callable(publish), "orchestrator must expose safe publication")

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            first_resolver = ImmutableContextResolver(
                run_contexts=(run_context,), year_contexts=(), modules_by_slot={}
            )
            expected = YearContextRef(2025, canonical_context_sha256(year_context))
            self.assertEqual(
                publish(first_resolver, run_context, year_context, directory), expected
            )
            destination = directory / "year-2025.json"
            original = destination.read_bytes()

            retry_resolver = ImmutableContextResolver(
                run_contexts=(run_context,), year_contexts=(), modules_by_slot={}
            )
            self.assertEqual(
                publish(retry_resolver, run_context, year_context, directory), expected
            )
            self.assertEqual(destination.read_bytes(), original)

            conflict_resolver = ImmutableContextResolver(
                run_contexts=(run_context,), year_contexts=(), modules_by_slot={}
            )
            with self.assertRaisesRegex(ValueError, "different content"):
                publish(conflict_resolver, run_context, conflicting, directory)
            self.assertEqual(destination.read_bytes(), original)
            with self.assertRaises(ValueError):
                conflict_resolver.resolve_year(
                    YearContextRef(2025, canonical_context_sha256(conflicting))
                )
            self.assertEqual(tuple(directory.glob("*.tmp")), ())

    def test_failed_first_year_context_publish_leaves_no_bound_reference(self) -> None:
        run_context = _run_context(_network_pack(1))
        year_context = _year_context(run_context, _psm_input(1))
        resolver = ImmutableContextResolver(
            run_contexts=(run_context,), year_contexts=(), modules_by_slot={}
        )
        reference = YearContextRef(2025, canonical_context_sha256(year_context))

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            with patch.object(
                os, "link", side_effect=OSError("simulated publish failure")
            ):
                with self.assertRaisesRegex(OSError, "simulated publish failure"):
                    orchestrator_module.publish_year_context(
                        resolver, run_context, year_context, directory
                    )

            with self.assertRaises(ValueError):
                resolver.resolve_year(reference)
            self.assertFalse((directory / "year-2025.json").exists())
            self.assertEqual(tuple(directory.glob("*.tmp")), ())

    def test_independent_resolvers_publish_one_digest_to_shared_year_path(self) -> None:
        run_context = _run_context(_network_pack(1))
        first = _year_context(run_context, _psm_input(1))
        second = replace(
            first,
            transition_lineage={"source_state_sha256": "f" * 64},
        )
        resolvers = tuple(
            ImmutableContextResolver(
                run_contexts=(run_context,), year_contexts=(), modules_by_slot={}
            )
            for _ in range(2)
        )

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            destination = directory / "year-2025.json"
            rendezvous = Barrier(2)
            replace_lock = Lock()
            real_exists = Path.exists
            real_replace = Path.replace

            def simultaneous_absence(path: Path) -> bool:
                exists = real_exists(path)
                if path == destination:
                    rendezvous.wait(timeout=5.0)
                return exists

            def serialized_overwrite(path: Path, target: Path) -> Path:
                with replace_lock:
                    return real_replace(path, target)

            def publish(index: int) -> object:
                try:
                    return orchestrator_module.publish_year_context(
                        resolvers[index],
                        run_context,
                        (first, second)[index],
                        directory,
                    )
                except ValueError as exc:
                    return exc

            with patch.object(
                Path, "exists", new=simultaneous_absence
            ), patch.object(Path, "replace", new=serialized_overwrite):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    outcomes = tuple(pool.map(publish, (0, 1)))

            winners = [
                index
                for index, outcome in enumerate(outcomes)
                if isinstance(outcome, YearContextRef)
            ]
            self.assertEqual(len(winners), 1)
            self.assertEqual(sum(isinstance(row, ValueError) for row in outcomes), 1)
            winner = winners[0]
            loser = 1 - winner
            winner_context = (first, second)[winner]
            loser_context = (first, second)[loser]
            self.assertEqual(
                YearContext.from_dict(json.loads(destination.read_text(encoding="utf-8"))),
                winner_context,
            )
            winner_ref = YearContextRef(
                2025, canonical_context_sha256(winner_context)
            )
            self.assertEqual(resolvers[winner].resolve_year(winner_ref), winner_context)
            with self.assertRaises(ValueError):
                resolvers[loser].resolve_year(
                    YearContextRef(2025, canonical_context_sha256(loser_context))
                )
            self.assertEqual(tuple(directory.glob("*.tmp")), ())


_VERSIONS = {
    "pipeline": ("prompt119-pipeline", "1.0"),
    "psm": ("prompt119-psm", "1.0"),
    "storage_cap": ("prompt119-storage", "1.0"),
    "vre_cap": ("prompt119-vre", "1.0"),
    "investment": ("prompt119-investment", "1.0"),
    "transition": ("prompt119-transition", "1.0"),
}


def _orchestrator_run() -> ResolvedRun:
    return ResolvedRun(
        "prompt119-run",
        "fixture-project",
        "fixture-scenario",
        "fixture-data-pack",
        2025,
        2026,
        {
            slot: ModuleSelection(slot, module_id, version, f"value.{slot}/v2")
            for slot, (module_id, version) in _VERSIONS.items()
        },
        {"clock.period_hours": 1.0},
        {},
    )


class _Pipeline:
    id, version = _VERSIONS["pipeline"]

    def advance_year(self, _run: ResolvedRun, state: YearState) -> PlanningAdvanceResult:
        operating = OperatingState(state.year, state.assets, state.planning_projects)
        return PlanningAdvanceResult(
            state.year, operating, state.planning_projects, (), (), (), ()
        )

    def admit_projects(
        self, _run: ResolvedRun, state: OperatingState, _proposals: object
    ) -> PlanningAdmissionResult:
        return PlanningAdmissionResult(state.year, (), (), (), ())


class _ContextPSM:
    id, version = _VERSIONS["psm"]

    def __init__(self, calls: list[tuple[int, str]], context_dir: Path) -> None:
        self.calls = calls
        self.context_dir = context_dir
        self.contexts: list[YearContext] = []
        self.psm_assets_by_year: dict[int, set[str]] = {}
        self.first_year_bytes = b""

    def start_year(self, context: YearContext) -> None:
        self.contexts.append(context)
        if context.year == 2025:
            self.first_year_bytes = (self.context_dir / "year-2025.json").read_bytes()

    def run(self, model_input: PSMInput) -> MarketYearResult:
        self.calls.append((model_input.year, "psm"))
        self.psm_assets_by_year[model_input.year] = {
            asset.asset_id for asset in model_input.operating_state.assets
        }
        return MarketYearResult(
            f"market:{model_input.year}",
            model_input.year,
            self.id,
            self.version,
            {},
            {},
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        )


class _Cap:
    version = "1.0"

    def __init__(self, slot: str) -> None:
        self.id = _VERSIONS[slot][0]

    def evaluate(
        self, _run: ResolvedRun, state: OperatingState, _market: MarketYearResult
    ) -> ExpansionHeadroom:
        return ExpansionHeadroom(
            f"{self.id}:{state.year}", state.year, self.id, {}
        )


class _Investment:
    id, version = _VERSIONS["investment"]

    def decide(
        self,
        _run: ResolvedRun,
        state: OperatingState,
        _market: MarketYearResult,
        _headroom: object,
    ) -> InvestmentDecision:
        return InvestmentDecision(
            f"decision:{state.year}", state.year, self.id, (), {}
        )


class _CommissioningTransition:
    id, version = _VERSIONS["transition"]

    def apply(
        self,
        _run: ResolvedRun,
        current_state: YearState,
        _planning: PlanningAdmissionResult,
        _investment: InvestmentDecision,
    ) -> YearState:
        assets = tuple(current_state.assets)
        if current_state.year == 2025:
            assets = (*assets, AssetStateV2(
                "commissioned:project-2025",
                "solar",
                2.0,
                extensions={"source_project_id": "project-2025"},
            ))
        return YearState(current_state.year + 1, assets, ())


if __name__ == "__main__":
    unittest.main()
