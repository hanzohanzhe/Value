"""Prompt 118 contract evidence for immutable VALUE module contexts."""

from __future__ import annotations

from dataclasses import dataclass, replace
import unittest

from gridform_core.module_context import (
    ImmutableContextResolver,
    RunContextRef,
    RunStaticContext,
    YearContext,
    YearContextRef,
)
from gridform_core.staged_market_contracts import (
    AheadMarketResult,
    ZonalRedispatchDomainV2,
    ZonalRedispatchPeriodSlice,
    contract_sha256,
)
from gridform_core.v2.module_manifest import builtin_registry


SHA_A = "a" * 64
SHA_B = "b" * 64


@dataclass(frozen=True)
class _ForgedAheadResult:
    period_id: str
    network_pack: object


class Prompt118ValueContextContractsTests(unittest.TestCase):
    def _run_context(self) -> RunStaticContext:
        return RunStaticContext(
            run_id="prompt118-run",
            study_revision_sha256=SHA_A,
            start_year=2025,
            end_year=2025,
            period_hours=0.5,
            data_pack={"id": "minimal-pack", "manifest_sha256": SHA_B},
            module_graph={"slots": ["psm"], "psm": {"id": "value-staged-bid-at-cost-psm"}},
            scientific_parameters={"voll_gbp_per_mwh": 10_000.0},
            runtime_controls={"market_trace_level": "summary"},
            trace_profile="summary",
            solver_contract={"method": "highs-ds", "presolve": True},
            market_configuration={"demand_authority": "zonal"},
            network_pack={"pack_id": "minimal-zonal-pack", "zones": {"z1": {}}},
        )

    def _year_context(self, run_context: RunStaticContext) -> YearContext:
        return YearContext(
            run_id=run_context.run_id,
            year=2025,
            run_context_sha256=contract_sha256(run_context),
            operating_state={"assets": {"battery-1": {"zone": "z1"}}},
            frozen_zone_shares={"battery-1": {"z1": 1.0}},
            opening_soc_mwh_by_asset={"battery-1": 12.0},
            transition_lineage={"opening": "frozen"},
        )

    def _ahead_result(self) -> AheadMarketResult:
        return AheadMarketResult(
            run_id="prompt118-run",
            year=2025,
            period=0,
            period_id="2025-0000",
            information_scope="forecast_only",
            schedule_mwh_by_asset={"generator-1": 15.0},
            clearing_price_gbp_per_mwh=50.0,
            accepted_volume_mwh=15.0,
            settlement_mwh_by_asset={"generator-1": 15.0},
            storage_scheduled_action_mwh_by_asset={"battery-1": 0.0},
            source_input_sha256=SHA_A,
        )

    def _period_slice(self) -> ZonalRedispatchPeriodSlice:
        return ZonalRedispatchPeriodSlice(
            period_id="2025-0000",
            ahead_result=self._ahead_result(),
            zonal_real_demand_mwh={"z1": 15.0},
            zonal_forecast_demand_mwh={"z1": 15.0},
            forward_boundary_capacity_mwh={"z1-z2": 10.0},
            reverse_boundary_capacity_mwh={"z1-z2": 10.0},
            interconnector_envelopes={"ic-1": {"import_mwh": 2.0, "export_mwh": 2.0}},
        )

    def test_context_refs_and_period_slice_are_canonical_and_compact(self) -> None:
        run_context = self._run_context()
        year_context = self._year_context(run_context)
        period_slice = self._period_slice()
        resolver = ImmutableContextResolver(
            run_contexts=(run_context,),
            year_contexts=(year_context,),
            modules_by_slot={"psm": object(), "balancing": object()},
        )
        domain = ZonalRedispatchDomainV2(
            run_context_ref=RunContextRef(sha256=contract_sha256(run_context)),
            year_context_ref=YearContextRef(
                year=2025, sha256=contract_sha256(year_context)
            ),
            period_slice=period_slice,
        )

        self.assertEqual(run_context.schema_version, "value.run-static-context/v1")
        self.assertEqual(year_context.schema_version, "value.year-context/v1")
        self.assertEqual(domain.schema_version, "value.zonal-redispatch-domain/v2")
        self.assertEqual(resolver.resolve_run(domain.run_context_ref), run_context)
        self.assertEqual(resolver.resolve_year(domain.year_context_ref), year_context)
        self.assertNotIn("network_pack", domain.to_dict())
        self.assertNotIn("zonal_demand", domain.to_dict())
        self.assertIn("ahead_result", domain.period_slice.to_dict())
        self.assertEqual(contract_sha256(run_context), domain.run_context_ref.sha256)

    def test_contexts_recursively_freeze_and_reject_invalid_identity_values(self) -> None:
        run_context = self._run_context()
        year_context = self._year_context(run_context)

        with self.assertRaises(TypeError):
            run_context.data_pack["id"] = "changed"  # type: ignore[index]
        with self.assertRaises(TypeError):
            run_context.network_pack["zones"]["z2"] = {}  # type: ignore[index,union-attr]
        with self.assertRaises(TypeError):
            run_context.module_graph["slots"][0] = "balancing"  # type: ignore[index]
        with self.assertRaises(TypeError):
            year_context.operating_state["assets"]["battery-2"] = {}  # type: ignore[index]
        with self.assertRaises(ValueError):
            RunContextRef(sha256="A" * 64)
        with self.assertRaises(ValueError):
            YearContextRef(year=True, sha256=SHA_A)
        with self.assertRaises(ValueError):
            replace(run_context, trace_profile="verbose")
        with self.assertRaises(ValueError):
            replace(run_context, period_hours=True)
        with self.assertRaises(ValueError):
            replace(year_context, year=2024, run_context_sha256="not-a-hash")
        with self.assertRaises(ValueError):
            replace(run_context, data_pack={"ids": {"mutable-set"}})
        with self.assertRaises(ValueError):
            replace(run_context, data_pack={"opaque": object()})

    def test_period_slice_rejects_annual_arrays_and_invalid_schema(self) -> None:
        period_slice = self._period_slice()
        with self.assertRaises(ValueError):
            replace(period_slice, zonal_real_demand_mwh={"z1": [1.0, 2.0]})
        with self.assertRaises(ValueError):
            replace(period_slice, schema_version="value.zonal-redispatch-domain/v1")
        with self.assertRaises(ValueError):
            ZonalRedispatchDomainV2(
                run_context_ref=RunContextRef(sha256=SHA_A),
                year_context_ref=YearContextRef(year=2025, sha256=SHA_B),
                period_slice=period_slice,
                schema_version="value.zonal-redispatch-domain/v1",
            )

    def test_period_slice_rejects_forged_ahead_result_payloads(self) -> None:
        forged = _ForgedAheadResult(
            period_id="2025-0000",
            network_pack={"annual": [1.0, 2.0]},
        )
        with self.assertRaises(ValueError):
            ZonalRedispatchPeriodSlice(
                period_id="2025-0000",
                ahead_result=forged,  # type: ignore[arg-type]
                zonal_real_demand_mwh={"z1": 15.0},
                zonal_forecast_demand_mwh={"z1": 15.0},
                forward_boundary_capacity_mwh={"z1-z2": 10.0},
                reverse_boundary_capacity_mwh={"z1-z2": 10.0},
                interconnector_envelopes={"ic-1": {"import_mwh": 2.0, "export_mwh": 2.0}},
            )
        with self.assertRaises(ValueError):
            ZonalRedispatchPeriodSlice(
                period_id="2025-0000",
                ahead_result={  # type: ignore[arg-type]
                    "period_id": "2025-0000",
                    "network_pack": {"annual": [1.0, 2.0]},
                },
                zonal_real_demand_mwh={"z1": 15.0},
                zonal_forecast_demand_mwh={"z1": 15.0},
                forward_boundary_capacity_mwh={"z1-z2": 10.0},
                reverse_boundary_capacity_mwh={"z1-z2": 10.0},
                interconnector_envelopes={"ic-1": {"import_mwh": 2.0, "export_mwh": 2.0}},
            )

    def test_domain_rejects_untyped_or_injected_child_contracts(self) -> None:
        period_slice = self._period_slice()
        with self.assertRaises(ValueError):
            ZonalRedispatchDomainV2(
                run_context_ref={
                    "schema_version": "value.run-static-context/v1",
                    "sha256": SHA_A,
                    "network_pack": {"annual": [1.0, 2.0]},
                },
                year_context_ref=YearContextRef(year=2025, sha256=SHA_B),
                period_slice=period_slice,
            )
        with self.assertRaises(ValueError):
            ZonalRedispatchDomainV2(
                run_context_ref=RunContextRef(sha256=SHA_A),
                year_context_ref={
                    "schema_version": "value.year-context/v0",
                    "year": 2025,
                    "sha256": SHA_B,
                },
                period_slice=period_slice,
            )
        with self.assertRaises(ValueError):
            ZonalRedispatchDomainV2(
                run_context_ref=RunContextRef(sha256=SHA_A),
                year_context_ref=YearContextRef(year=2025, sha256=SHA_B),
                period_slice={
                    "period_id": "2025-0000",
                    "network_pack": {"annual": [1.0, 2.0]},
                },
            )

    def test_resolver_fails_closed_for_wrong_references_and_duplicates(self) -> None:
        run_context = self._run_context()
        year_context = self._year_context(run_context)
        with self.assertRaisesRegex(ValueError, "Duplicate run context"):
            ImmutableContextResolver(
                run_contexts=(run_context, run_context), year_contexts=(), modules_by_slot={}
            )
        with self.assertRaisesRegex(ValueError, "Duplicate year context"):
            ImmutableContextResolver(
                run_contexts=(run_context,),
                year_contexts=(year_context, year_context),
                modules_by_slot={},
            )
        with self.assertRaisesRegex(ValueError, "Duplicate module slot"):
            ImmutableContextResolver(
                run_contexts=(run_context,),
                year_contexts=(year_context,),
                modules_by_slot=(("psm", object()), ("psm", object())),
            )

        resolver = ImmutableContextResolver(
            run_contexts=(run_context,), year_contexts=(year_context,), modules_by_slot={"psm": object()}
        )
        with self.assertRaises(ValueError):
            resolver.resolve_run(RunContextRef(sha256=SHA_B))
        with self.assertRaises(ValueError):
            resolver.resolve_year(YearContextRef(year=2026, sha256=contract_sha256(year_context)))
        with self.assertRaises(ValueError):
            resolver.resolve_year(YearContextRef(year=2025, sha256=SHA_B))
        with self.assertRaises(ValueError):
            resolver.resolve_module("balancing")

    def test_manifest_selection_requires_declared_context_capabilities(self) -> None:
        registry = builtin_registry()
        psm = registry.manifest("value-staged-bid-at-cost-psm")
        zonal = registry.manifest("value-zonal-redispatch-balancing")
        self.assertIn("value.module-context-lifecycle/v1", psm.provides_capabilities)
        self.assertIn("value.module-context-lifecycle/v1", zonal.provides_capabilities)
        self.assertIn("value.zonal-redispatch-domain/v2", zonal.provides_capabilities)

        missing_psm_lifecycle = replace(
            psm,
            id="psm-without-lifecycle",
            requires_capabilities=(),
            provides_capabilities=tuple(
                item for item in psm.provides_capabilities
                if item != "value.module-context-lifecycle/v1"
            ),
        )
        zonal_without_lifecycle = replace(
            zonal,
            id="zonal-without-lifecycle",
            provides_capabilities=tuple(
                item for item in zonal.provides_capabilities
                if item != "value.module-context-lifecycle/v1"
            ),
        )
        from gridform_core.v2.module_manifest import ModuleRegistryV2

        psm_registry = ModuleRegistryV2((missing_psm_lifecycle, zonal))
        with self.assertRaisesRegex(ValueError, "incompatible capabilities"):
            psm_registry.validate_selection(
                {"psm": "psm-without-lifecycle", "balancing": zonal.id}
            )
        zonal_lifecycle_registry = ModuleRegistryV2(
            (replace(psm, requires_capabilities=()), zonal_without_lifecycle)
        )
        with self.assertRaisesRegex(ValueError, "incompatible capabilities"):
            zonal_lifecycle_registry.validate_selection(
                {"psm": psm.id, "balancing": "zonal-without-lifecycle"}
            )
        zonal_without_domain = replace(
            zonal,
            id="zonal-without-domain",
            provides_capabilities=tuple(
                item for item in zonal.provides_capabilities
                if item != "value.zonal-redispatch-domain/v2"
            ),
        )
        domain_registry = ModuleRegistryV2((replace(psm, requires_capabilities=()), zonal_without_domain))
        with self.assertRaisesRegex(ValueError, "value.zonal-redispatch-domain/v2"):
            domain_registry.validate_selection(
                {"psm": psm.id, "balancing": "zonal-without-domain"}
            )


if __name__ == "__main__":
    unittest.main()
