from __future__ import annotations

import gzip
import hashlib
import json
import random
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.optimize import linprog

import gridform_core.zonal_redispatch as zonal_redispatch

from gridform_core.staged_market_contracts import (
    AcceptedAdjustment,
    AheadMarketResult,
    BalancingInput,
    BalancingResult,
    FlexibilityBid,
    ZonalRedispatchDomainV2,
    ZonalRedispatchPeriodSlice,
    contract_sha256,
)
from gridform_core.module_context import (
    ImmutableContextResolver,
    RunContextRef,
    RunStaticContext,
    YearContext,
    YearContextRef,
    canonical_context_sha256,
)
from gridform_core.zonal_contracts import (
    CutsetMember,
    ETYSBoundary,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZonalDemand,
    ZonalNetworkPack,
)
from gridform_core.vre_curtailment_attribution import (
    CurtailmentAttributionError,
    VRECounterfactualRow,
    VRECounterfactualSnapshot,
    attribute_vre_curtailment,
)
from gridform_core.zonal_redispatch import (
    TOLERANCE,
    SinglePeriodSolution,
    ZonalRedispatchBalancing,
    ZonalRedispatchInputError,
    ZonalRedispatchSolveError,
    build_single_period_problem,
    solve_primary,
    solve_secondary,
    validate_solution,
)
from gridform_core.zonal_solver_contract import (
    DEFAULT_ZONAL_SOLVER_SETTINGS,
    validate_solver_settings,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "zonal_solver_failures"


def fixture_payload(path: Path) -> dict[str, object]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


_BOUND_CONTEXTS: dict[
    tuple[str, str], tuple[RunStaticContext, YearContext, ZonalNetworkPack]
] = {}


def _bind_module(
    module: ZonalRedispatchBalancing,
    model_input: BalancingInput,
) -> None:
    domain = ZonalRedispatchDomainV2.from_dict(model_input.domain_payload)
    key = (domain.run_context_ref.sha256, domain.year_context_ref.sha256)
    run_context, year_context, _pack_value = _BOUND_CONTEXTS[key]
    resolver = ImmutableContextResolver(
        run_contexts=(run_context,),
        year_contexts=(year_context,),
        modules_by_slot={"balancing": module},
    )
    module.configure(run_context, resolver)
    module.start_year(year_context)


def _problem(model_input: BalancingInput):
    domain = ZonalRedispatchDomainV2.from_dict(model_input.domain_payload)
    key = (domain.run_context_ref.sha256, domain.year_context_ref.sha256)
    run_context, year_context, pack = _BOUND_CONTEXTS[key]
    return build_single_period_problem(
        model_input,
        network_pack=pack,
        run_context_ref=domain.run_context_ref,
        year_context_ref=domain.year_context_ref,
        annual_metadata=year_context.operating_state,
        demand_mode=str(
            run_context.market_configuration["zonal_demand_mode"]
        ),
        network_period_index={
            str(period_id): index
            for index, period_id in enumerate(pack.zonal_demand.period_ids)
        }[model_input.period_id],
    )


def balancing_input_from_fixture(
    path: Path,
) -> tuple[BalancingInput, ZonalRedispatchBalancing]:
    fixture = fixture_payload(path)
    return _balancing_input_from_legacy_payload(dict(fixture["declared_input"]))


def _balancing_input_from_legacy_payload(
    payload: dict[str, object],
) -> tuple[BalancingInput, ZonalRedispatchBalancing]:
    legacy_domain = dict(payload["domain_payload"])
    payload["bids"] = tuple(
        FlexibilityBid(**{
            **dict(item),
            "schema_version": "value.flexibility-bid/v1",
        })
        for item in payload["bids"]
    )
    ahead_payload = {
        **dict(legacy_domain["ahead_result"]),
        "schema_version": "value.ahead-market-result/v1",
    }
    ahead = AheadMarketResult.from_dict(ahead_payload)
    pack = ZonalNetworkPack.from_dict(legacy_domain["network_pack"])
    model_input, module = _runtime_input(
        ahead=ahead,
        pack=pack,
        payload=payload,
        real_demand=dict(legacy_domain["real_demand_mwh_by_zone"]),
        zones=dict(legacy_domain["asset_zone_id_by_asset"]),
        classes=dict(legacy_domain.get("resource_class_by_asset") or {}),
        costs=dict(legacy_domain.get("resource_cost_gbp_per_mwh_by_asset") or {}),
        storage=dict(legacy_domain.get("storage") or {}),
        envelopes=dict(
            legacy_domain.get("interconnector_envelope_mwh_by_asset") or {}
        ),
        corridor_limits=dict(legacy_domain.get("corridor_limits_mw_by_id") or {}),
        demand_mode=str(
            legacy_domain.get("zonal_demand_mode")
            or "network_pack_absolute_demand"
        ),
    )
    return model_input, module


def solver_diagnostic(result: object, phase_id: str) -> dict[str, object]:
    rows = result.extensions["network_solver_diagnostics"]
    return next(row for row in rows if row["phase_id"] == phase_id)


def _pack(
    demand: dict[str, float],
    *,
    forward_limit_mw: float | None = None,
    reverse_limit_mw: float | None = None,
) -> ZonalNetworkPack:
    zones = tuple(
        NetworkZone(zone, zone.title(), "fixture DSO", "England")
        for zone in demand
    )
    corridors = ()
    cutsets = ()
    if len(zones) == 2:
        corridors = (
            TransportCorridor(
                "north-south", zones[0].zone_id, zones[1].zone_id,
                "from_to_positive",
            ),
        )
        if forward_limit_mw is not None:
            cutsets = (
                ETYSBoundary(
                    "B_TEST",
                    "Fixture boundary",
                    (CutsetMember("north-south", 1),),
                    forward_limit_mw,
                    reverse_limit_mw if reverse_limit_mw is not None else forward_limit_mw,
                    reverse_limit_method=(
                        "independent_source"
                        if reverse_limit_mw is not None
                        else "assumed_symmetric_from_forward"
                    ),
                ),
            )
    model = ZonalNetworkPack(
        "fixture-zonal-v1",
        "",
        zones,
        corridors,
        cutsets,
        (),
        ZonalDemand(
            ("p0",),
            {zone: (value,) for zone, value in demand.items()},
            (sum(demand.values()),),
        ),
        (),
        (),
        SpatialAudit((), {}, {}, 1e-9),
        "lossless_v1",
    )
    return replace(model, scientific_sha256=model.compute_scientific_sha256())


def _bid(
    bid_id: str,
    asset_id: str,
    zone_id: str,
    direction: str,
    volume_mwh: float,
    price: float,
    *,
    resource_class: str = "thermal",
    network_effect_id: str | None = None,
    baseline_mw: float = 0.0,
    curtailment_class: str = "",
) -> FlexibilityBid:
    return FlexibilityBid(
        bid_id,
        asset_id,
        asset_id,
        resource_class,
        zone_id,
        "p0",
        direction,
        volume_mwh,
        price,
        baseline_mw,
        price,
        network_effect_id or f"{zone_id}:injection",
        {
            "resource_class": resource_class,
            "curtailment_class": curtailment_class,
        },
        extensions={"available_mwh": volume_mwh},
    )


def _input(
    demand: dict[str, float],
    schedule: dict[str, float],
    zones: dict[str, str],
    bids: tuple[FlexibilityBid, ...] = (),
    *,
    pack: ZonalNetworkPack | None = None,
    availability_mw: dict[str, float] | None = None,
    resource_class: dict[str, str] | None = None,
    resource_cost: dict[str, float] | None = None,
    storage: dict[str, dict[str, object]] | None = None,
    initial_soc: dict[str, float] | None = None,
    interconnector_envelopes: dict[str, dict[str, float]] | None = None,
    corridor_limits: dict[str, dict[str, float]] | None = None,
    evidence_root: Path | None = None,
    zonal_demand_mode: str = "network_pack_absolute_demand",
) -> tuple[BalancingInput, ZonalRedispatchBalancing]:
    pack = pack or _pack(demand)
    ahead = AheadMarketResult(
        "run-zonal",
        2025,
        0,
        "p0",
        "forecast_only",
        schedule,
        50.0,
        sum(max(value, 0.0) for value in schedule.values()),
        schedule,
        {},
        "a" * 64,
    )
    all_assets = set(schedule) | {bid.asset_id for bid in bids}
    available = availability_mw or {asset: 1_000.0 for asset in all_assets}
    classes = resource_class or {asset: "thermal" for asset in all_assets}
    costs = resource_cost or {asset: 0.0 for asset in all_assets}
    payload = BalancingInput(
        "run-zonal", 2025, 0, "p0", contract_sha256(ahead),
        sum(demand.values()), available, initial_soc or {}, bids, 1.0, 17_000.0,
        domain_payload={},
    ).to_dict()
    return _runtime_input(
        ahead=ahead,
        pack=pack,
        payload=payload,
        real_demand=demand,
        zones=zones,
        classes=classes,
        costs=costs,
        storage=storage or {},
        envelopes=interconnector_envelopes or {},
        corridor_limits=corridor_limits or {},
        demand_mode=zonal_demand_mode,
        module=ZonalRedispatchBalancing(evidence_root=evidence_root),
    )


def _runtime_input(
    *,
    ahead: AheadMarketResult,
    pack: ZonalNetworkPack,
    payload: dict[str, object],
    real_demand: dict[str, float],
    zones: dict[str, str],
    classes: dict[str, str],
    costs: dict[str, float],
    storage: dict[str, dict[str, object]],
    envelopes: dict[str, dict[str, float]],
    corridor_limits: dict[str, dict[str, float]],
    demand_mode: str,
    module: ZonalRedispatchBalancing | None = None,
) -> tuple[BalancingInput, ZonalRedispatchBalancing]:
    period_id = str(payload["period_id"])
    period_hours = float(payload["period_hours"])
    index_by_id = {
        str(value): index
        for index, value in enumerate(pack.zonal_demand.period_ids)
    }
    period_index = index_by_id[period_id]
    profiles = {profile.profile_id: profile for profile in pack.rating_profiles}
    forward_capacity: dict[str, float] = {}
    reverse_capacity: dict[str, float] = {}
    for boundary in pack.cutsets:
        multiplier = 1.0
        if boundary.rating_profile_id:
            multiplier = profiles[boundary.rating_profile_id].multipliers[period_index]
        forward_capacity[boundary.boundary_id] = (
            boundary.forward_limit_mw * period_hours * multiplier
        )
        reverse_capacity[boundary.boundary_id] = (
            boundary.reverse_limit_mw * period_hours * multiplier
        )
    for corridor_id, limits in corridor_limits.items():
        forward_capacity[corridor_id] = (
            float(limits["forward_limit_mw"]) * period_hours
        )
        reverse_capacity[corridor_id] = (
            float(limits["reverse_limit_mw"]) * period_hours
        )
    run_context = RunStaticContext(
        run_id=str(payload["run_id"]),
        study_revision_sha256="a" * 64,
        start_year=int(payload["year"]),
        end_year=int(payload["year"]),
        period_hours=period_hours,
        data_pack={"data_pack_id": "fixture", "manifest_sha256": "b" * 64},
        module_graph={"graph_sha256": "c" * 64},
        scientific_parameters={"clock.period_hours": period_hours},
        runtime_controls={},
        trace_profile="summary",
        solver_contract={},
        market_configuration={"zonal_demand_mode": demand_mode},
        network_pack=pack.to_dict(),
    )
    year_context = YearContext(
        run_id=str(payload["run_id"]),
        year=int(payload["year"]),
        run_context_sha256=canonical_context_sha256(run_context),
        operating_state={
            "schema_version": "value.operating-state/v2",
            "assets": [],
            "active_planning_projects": [],
            "asset_zone_id_by_asset": zones,
            "resource_class_by_asset": classes,
            "resource_cost_gbp_per_mwh_by_asset": costs,
            "storage": storage,
        },
        frozen_zone_shares={asset: {zone: 1.0} for asset, zone in zones.items()},
        opening_soc_mwh_by_asset=dict(payload.get("initial_soc_mwh_by_asset") or {}),
        transition_lineage={"fixture": True},
    )
    run_reference = RunContextRef(canonical_context_sha256(run_context))
    year_reference = YearContextRef(
        year_context.year, canonical_context_sha256(year_context)
    )
    directional_envelopes = {}
    for asset_id, envelope in envelopes.items():
        if "import_capacity_mwh" in envelope:
            directional_envelopes[asset_id] = dict(envelope)
        else:
            directional_envelopes[asset_id] = {
                "import_capacity_mwh": max(
                    float(envelope.get("maximum_mwh", 0.0)), 0.0
                ),
                "export_capacity_mwh": max(
                    -float(envelope.get("minimum_mwh", 0.0)), 0.0
                ),
            }
    domain = ZonalRedispatchDomainV2(
        run_reference,
        year_reference,
        ZonalRedispatchPeriodSlice(
            period_id=period_id,
            ahead_result=ahead,
            zonal_real_demand_mwh=real_demand,
            zonal_forecast_demand_mwh=real_demand,
            forward_boundary_capacity_mwh=forward_capacity,
            reverse_boundary_capacity_mwh=reverse_capacity,
            interconnector_envelopes=directional_envelopes,
        ),
    )
    payload = {
        **payload,
        "schema_version": "value.balancing-input/v1",
        "ahead_result_sha256": contract_sha256(ahead),
        "domain_payload": domain.to_dict(),
    }
    payload["bids"] = tuple(
        item if isinstance(item, FlexibilityBid) else FlexibilityBid.from_dict(item)
        for item in payload["bids"]
    )
    model_input = BalancingInput(**payload)
    _BOUND_CONTEXTS[(run_reference.sha256, year_reference.sha256)] = (
        run_context, year_context, pack
    )
    bound_module = module or ZonalRedispatchBalancing()
    _bind_module(bound_module, model_input)
    return model_input, bound_module


class ZonalRedispatchSolverContractTests(unittest.TestCase):
    def test_cross_year_network_clock_keeps_year_local_runtime_indices(self) -> None:
        pack = _pack({"gb": 5.0})
        pack = replace(pack, zonal_demand=ZonalDemand(
            ("2025-p0", "2026-p0"), {"gb": (5.0, 5.0)}, (5.0, 5.0)
        ))
        pack = replace(pack, scientific_sha256=pack.compute_scientific_sha256())
        module = ZonalRedispatchBalancing()
        for global_index, year in enumerate((2025, 2026)):
            period_id = f"{year}-p0"
            ahead = AheadMarketResult(
                "cross-year", year, 0, period_id, "forecast_only",
                {"thermal": 5.0}, 50.0, 5.0, {"thermal": 5.0}, {}, "a" * 64,
            )
            payload = BalancingInput(
                "cross-year", year, 0, period_id, contract_sha256(ahead),
                5.0, {"thermal": 5.0}, {}, (), 1.0, 17_000.0,
            ).to_dict()
            model_input, module = _runtime_input(
                ahead=ahead, pack=pack, payload=payload,
                real_demand={"gb": 5.0}, zones={"thermal": "gb"},
                classes={"thermal": "thermal"}, costs={"thermal": 50.0},
                storage={}, envelopes={}, corridor_limits={},
                demand_mode="network_pack_absolute_demand", module=module,
            )
            self.assertEqual(module._period_index_by_id[period_id], global_index)
            module.clear(model_input)
            exported = json.loads(json.dumps(module.export_runtime_state()))
            self.assertEqual(exported["next_period_index"], 1)
            self.assertEqual(exported["consumed_inputs"], [
                {"period_index": 0, "input_sha256": contract_sha256(model_input)}
            ])
            restored = ZonalRedispatchBalancing()
            _bind_module(restored, model_input)
            restored.restore_runtime_state(exported)
            self.assertEqual(restored.export_runtime_state(), exported)
            with self.assertRaisesRegex(ZonalRedispatchInputError, "already been balanced"):
                restored.clear(model_input)
            # A non-local or skipped period is not silently renumbered by count.
            invalid = {**exported, "next_period_index": 2, "consumed_inputs": [
                {"period_index": 1, "input_sha256": contract_sha256(model_input)}
            ]}
            with self.assertRaisesRegex(ValueError, "ordered sequence"):
                restored.restore_runtime_state(invalid)

    def test_runtime_state_round_trip_preserves_consumed_input_hashes(self) -> None:
        module = ZonalRedispatchBalancing()
        payload = {
            "schema_version": "value.zonal-redispatch-runtime-state/v1",
            "next_period_index": 2,
            "consumed_inputs": [
                {"period_index": 0, "input_sha256": "a" * 64},
                {"period_index": 1, "input_sha256": "b" * 64},
            ],
        }

        module.restore_runtime_state(json.loads(json.dumps(payload)))

        self.assertEqual(module.export_runtime_state(), payload)
        for invalid in (
            {**payload, "consumed_inputs": [{"period_index": 0, "input_sha256": "A" * 64}]},
            {**payload, "consumed_inputs": [{"period_index": 2, "input_sha256": "a" * 64}]},
            {
                **payload,
                "consumed_inputs": [
                    {"period_index": 1, "input_sha256": "b" * 64}
                ],
            },
            {
                **payload,
                "consumed_inputs": [
                    {"period_index": 0, "input_sha256": "a" * 64},
                    {"period_index": 0, "input_sha256": "b" * 64},
                ],
            },
            {
                **payload,
                "consumed_inputs": list(reversed(payload["consumed_inputs"])),
            },
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    module.restore_runtime_state(invalid)

    def test_retained_fixtures_are_content_addressed_and_deterministic(self) -> None:
        retained = FIXTURE_ROOT / "period-2025-14.json.gz"
        compressed = retained.read_bytes()
        self.assertEqual(int.from_bytes(compressed[4:8], "little"), 0)
        self.assertEqual(compressed[3] & 0x08, 0)
        for path in (retained, FIXTURE_ROOT / "period-bound-noise.json"):
            with self.subTest(path=path.name):
                fixture = fixture_payload(path)
                self.assertEqual(
                    contract_sha256(fixture["declared_input"]),
                    fixture["source_sha256"],
                )
        self.assertEqual(
            fixture_payload(retained)["source_sha256"],
            "88d613706bd1400bd16cc0210526a864c0ea93acd6d4262ffa058811dd77068a",
        )
        self.assertEqual(
            hashlib.sha256(compressed).hexdigest(),
            "1e0f453ec01427d90ce3801eae62ccb67f9d8be375f26e00896131dc90f995bd",
        )

    def test_later_phases_use_one_sided_caps_and_fixed_method(self) -> None:
        model_input, _module = _input(
            {"north": 0.0, "south": 10.0},
            {"cheap": 10.0, "local": 0.0},
            {"cheap": "north", "local": "south"},
            (
                _bid(
                    "cheap-down", "cheap", "north", "down", 10.0, 0.0,
                    baseline_mw=10.0,
                ),
                _bid("local-up", "local", "south", "up", 10.0, 100.0),
            ),
            pack=_pack({"north": 0.0, "south": 10.0}, forward_limit_mw=4.0),
        )
        problem = _problem(model_input)
        solver = getattr(zonal_redispatch, "solve_lexicographic", None)
        self.assertIsNotNone(solver)
        with patch("scipy.optimize.linprog", wraps=linprog) as wrapped:
            solution = solver(problem, DEFAULT_ZONAL_SOLVER_SETTINGS)
        calls = wrapped.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0].kwargs["method"], "highs-ds")
        self.assertEqual(calls[0].kwargs["options"], {
            "presolve": True,
            "primal_feasibility_tolerance": 1e-9,
            "dual_feasibility_tolerance": 1e-9,
        })
        base_rows = len(problem.inequality_matrix)
        self.assertEqual(
            [len(call.kwargs["A_ub"]) for call in calls],
            [base_rows, base_rows + 1, base_rows + 2, base_rows + 3],
        )
        self.assertEqual(
            [len(call.kwargs["A_eq"]) for call in calls],
            [len(problem.equality_matrix)] * 4,
        )
        self.assertIs(solution.diagnostics["automatic_copperplate_fallback"], False)

    def test_final_solution_recomputes_all_locked_objectives(self) -> None:
        model_input, _module = balancing_input_from_fixture(
            FIXTURE_ROOT / "period-2025-14.json.gz"
        )
        problem = _problem(model_input)
        solver = getattr(zonal_redispatch, "solve_lexicographic", None)
        self.assertIsNotNone(solver)
        result = solver(problem, DEFAULT_ZONAL_SOLVER_SETTINGS)
        self.assertEqual(len(result.network_solver_diagnostics), 3)
        self.assertTrue(all(
            row.degradation <= row.computed_tolerance
            for row in result.network_solver_diagnostics
        ))
        self.assertAlmostEqual(
            result.primary_objective_gbp,
            float(problem.primary_objective @ result.values),
        )
        self.assertAlmostEqual(
            result.secondary_objective_mwh,
            float(problem.secondary_objective @ result.values),
        )

    def test_cap_reserves_declared_reconstruction_allowance_at_tau_boundary(self) -> None:
        from test_prompt103_zonal_validation import (
            _prompt107_three_case_declaration,
        )

        model_input, _module = _balancing_input_from_legacy_payload(
            _prompt107_three_case_declaration(step=2, seed=101)
        )
        problem = _problem(model_input)
        try:
            result = zonal_redispatch.solve_lexicographic(
                problem, DEFAULT_ZONAL_SOLVER_SETTINGS
            )
        except ZonalRedispatchSolveError as exc:
            self.fail(f"declared reconstruction allowance was not reserved: {exc}")

        primary = result.network_solver_diagnostics[0]
        self.assertEqual(primary.optimum, 64.18999999999998)
        self.assertEqual(primary.absolute_term_scale, 64.18999999999998)
        # v4: the bid-cost lock carries only the non-zero bid terms (the
        # thermal up bid; the zero-price wind bid and VOLL x shedding drop
        # out) and its numerical tolerance (P0-8 S4).
        self.assertEqual(primary.nonzero_terms, 1)
        self.assertEqual(
            primary.computed_tolerance,
            max(1e-8, 1e-9 * primary.absolute_term_scale, 70.0 * 1e-9),
        )
        self.assertLessEqual(primary.degradation, primary.computed_tolerance)
        epsilon = float(np.finfo(float).eps)
        gamma_n = 1 * epsilon / (1.0 - 1 * epsilon)
        expected_rhs = np.nextafter(
            primary.optimum
            + primary.computed_tolerance
            - gamma_n * primary.absolute_term_scale,
            -np.inf,
        )
        stable_primary_cap = result.diagnostics["phases"]["stable"][
            "completed_phase_optima"
        ][0]
        self.assertEqual(
            stable_primary_cap["reconstruction_allowance"],
            gamma_n * primary.absolute_term_scale,
        )
        self.assertEqual(stable_primary_cap["rhs"], expected_rhs)

    def test_gbp1_policy_changes_only_primary_lock_allowance(self) -> None:
        coefficients = np.array([2.0, -3.0], dtype=float)
        optimum = np.array([4.0, 5.0], dtype=float)

        primary = zonal_redispatch._objective_cap(
            coefficients,
            optimum,
            DEFAULT_ZONAL_SOLVER_SETTINGS,
            "primary_bid_cost_gbp",
        )
        secondary = zonal_redispatch._objective_cap(
            coefficients,
            optimum,
            DEFAULT_ZONAL_SOLVER_SETTINGS,
            "secondary_schedule_deviation_mwh",
        )
        physical = zonal_redispatch._objective_cap(
            coefficients,
            optimum,
            DEFAULT_ZONAL_SOLVER_SETTINGS,
            "physical_throughput_mwh",
        )

        expected_mwh = zonal_redispatch.compute_lock_tolerance(
            coefficients, optimum, 1e-9, 1e-8
        ).tolerance
        # v4 (P0-8): GBP 1 is no longer the lock allowance; the bid-cost lock
        # uses the declared solver tolerance (1e-9) and its 1e-8 GBP floor.
        expected_gbp = zonal_redispatch.compute_lock_tolerance(
            coefficients, optimum, 1e-8, 1e-9
        ).tolerance
        self.assertEqual(primary.computed_tolerance, expected_gbp)
        self.assertLess(primary.computed_tolerance, 1e-6)
        self.assertEqual(secondary.computed_tolerance, expected_mwh)
        self.assertEqual(physical.computed_tolerance, expected_mwh)

    def test_failed_lock_gets_targeted_tighter_cap_without_relaxing_tolerance(self) -> None:
        coefficients = np.array([55.07, 0.0, -12.0], dtype=float)
        lock = zonal_redispatch._ObjectiveCap(
            coefficients,
            "primary_bid_cost_gbp",
            "primary_bid_cost",
            "GBP",
            1597.0300000004008,
            1597.0341466994173,
            0.00414669908709319,
            2,
            1597.0300000004008,
        )
        diagnostics = {
            "objective_key": "primary_bid_cost_gbp",
            "excess_degradation": 2.8745516045605712e-09,
        }

        repaired = zonal_redispatch._tighten_violated_objective_cap(
            (lock,), diagnostics, DEFAULT_ZONAL_SOLVER_SETTINGS
        )[0]

        expected_guard = 8e-9 * lock.rhs
        self.assertEqual(repaired.computed_tolerance, lock.computed_tolerance)
        self.assertEqual(repaired.optimum, lock.optimum)
        self.assertLessEqual(
            repaired.rhs,
            lock.rhs - diagnostics["excess_degradation"] - expected_guard,
        )

    def test_lock_violation_diagnostics_name_objective_and_values(self) -> None:
        model_input, _module = _input(
            {"gb": 1.0},
            {"asset": 0.0},
            {"asset": "gb"},
            (_bid("up", "asset", "gb", "up", 2.0, 1.0),),
        )
        problem = _problem(model_input)
        coefficients = np.zeros(len(problem.variable_names), dtype=float)
        coefficients[problem.bid_index["up"]] = 1.0
        lock = zonal_redispatch._ObjectiveCap(
            coefficients,
            "primary_bid_cost_gbp",
            "primary_bid_cost",
            "GBP",
            0.0,
            1e-6,
            1e-6,
            1,
            0.0,
        )
        final_values = np.zeros(len(problem.variable_names), dtype=float)
        final_values[problem.bid_index["up"]] = 1e-4

        with self.assertRaises(ZonalRedispatchSolveError) as raised:
            zonal_redispatch._finalise_lexicographic_solution(
                problem,
                final_values,
                {},
                (lock,),
                DEFAULT_ZONAL_SOLVER_SETTINGS,
            )

        diagnostics = raised.exception.diagnostics
        self.assertEqual(diagnostics["objective_key"], "primary_bid_cost_gbp")
        self.assertEqual(diagnostics["phase_id"], "primary_bid_cost")
        self.assertEqual(diagnostics["achieved_final_value"], 1e-4)
        self.assertEqual(diagnostics["degradation"], 1e-4)
        self.assertEqual(diagnostics["computed_tolerance"], 1e-6)
        self.assertAlmostEqual(diagnostics["excess_degradation"], 9.9e-5)

    def test_non_lock_finalisation_error_is_not_retried(self) -> None:
        model_input, _module = _input(
            {"gb": 1.0}, {"asset": 0.0}, {"asset": "gb"},
            (_bid("up", "asset", "gb", "up", 2.0, 1.0),),
        )
        problem = _problem(model_input)
        error = ZonalRedispatchSolveError(
            "bound failure", {"error_code": "GF_ZONAL_SOLUTION_BOUND_VIOLATION"}
        )
        with patch.object(
            zonal_redispatch, "_finalise_lexicographic_solution", side_effect=error
        ), patch.object(zonal_redispatch, "_run_highs") as rerun:
            with self.assertRaisesRegex(ZonalRedispatchSolveError, "bound failure"):
                zonal_redispatch._finalise_with_lock_repair(
                    problem,
                    np.zeros(len(problem.variable_names)),
                    {},
                    (),
                    DEFAULT_ZONAL_SOLVER_SETTINGS,
                )
        rerun.assert_not_called()

    def test_lock_repair_exhaustion_remains_a_hard_failure(self) -> None:
        model_input, _module = _input(
            {"gb": 1.0}, {"asset": 0.0}, {"asset": "gb"},
            (_bid("up", "asset", "gb", "up", 2.0, 1.0),),
        )
        problem = _problem(model_input)
        coefficients = np.zeros(len(problem.variable_names), dtype=float)
        coefficients[problem.bid_index["up"]] = 1.0
        lock = zonal_redispatch._ObjectiveCap(
            coefficients, "primary_bid_cost_gbp", "primary_bid_cost", "GBP",
            0.0, 1.0, 1e-6, 1, 0.0,
        )
        error = ZonalRedispatchSolveError("still outside lock", {
            "error_code": "GF_ZONAL_OBJECTIVE_LOCK_VIOLATION",
            "objective_key": lock.objective_key,
            "achieved_final_value": 2e-6,
            "degradation": 2e-6,
            "computed_tolerance": 1e-6,
            "excess_degradation": 1e-6,
        })
        with patch.object(
            zonal_redispatch,
            "_finalise_lexicographic_solution",
            side_effect=error,
        ) as finalise, patch.object(
            zonal_redispatch,
            "_run_highs",
            return_value=(np.zeros(len(problem.variable_names)), {}),
        ) as rerun:
            with self.assertRaisesRegex(
                ZonalRedispatchSolveError, "still outside lock"
            ):
                zonal_redispatch._finalise_with_lock_repair(
                    problem,
                    np.zeros(len(problem.variable_names)),
                    {},
                    (lock,),
                    DEFAULT_ZONAL_SOLVER_SETTINGS,
                )
        self.assertEqual(finalise.call_count, 4)
        self.assertEqual(rerun.call_count, 3)

    def test_module_v40_exposes_shed_lock_solver_contract(self) -> None:
        from gridform_core.v2.module_manifest import ModuleManifest, workspace_registry

        manifest = workspace_registry(ROOT / "missing-modules").manifest(
            "value-zonal-redispatch-balancing"
        )
        self.assertEqual(manifest.version, "4.0.0")
        self.assertEqual(
            manifest.scientific_version,
            "value-lossless-zonal-redispatch-shed-lock-candidate-2026.10.05",
        )
        self.assertEqual(
            manifest.solver_contract["schema_path"],
            "gridform_core/data/contracts/network-solver-contract-v4.schema.json",
        )
        self.assertIn("evidence.network-solver-diagnostics/v7", manifest.outputs)
        self.assertEqual(
            manifest.solver_contract["defaults"],
            DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
        )
        self.assertEqual(
            ModuleManifest.from_dict(manifest.to_dict()).solver_contract,
            manifest.solver_contract,
        )

    def test_cancelling_cost_terms_use_absolute_scale(self) -> None:
        demand = {"north": 0.0, "south": 10.0}
        model_input, _module = _input(
            demand,
            {"cheap": 10.0, "local": 0.0},
            {"cheap": "north", "local": "south"},
            (
                _bid(
                    "cheap-down", "cheap", "north", "down", 6.0, 100.0,
                    baseline_mw=10.0,
                ),
                _bid("local-up", "local", "south", "up", 6.0, 100.0),
            ),
            pack=_pack(demand, forward_limit_mw=4.0),
        )
        result = zonal_redispatch.solve_lexicographic(
            _problem(model_input),
            DEFAULT_ZONAL_SOLVER_SETTINGS,
        )
        primary = result.network_solver_diagnostics[0]
        self.assertAlmostEqual(primary.optimum, 0.0)
        self.assertAlmostEqual(primary.absolute_term_scale, 1200.0)
        self.assertGreater(primary.computed_tolerance, 1e-8)

    def test_seeded_random_convex_cases_clear_with_locked_objectives(self) -> None:
        generator = random.Random(81723)
        for case in range(8):
            demand = generator.uniform(1.0, 9.0)
            cheap_capacity = demand + generator.uniform(0.1, 3.0)
            cheap_price = generator.uniform(5.0, 30.0)
            dear_price = cheap_price + generator.uniform(1.0, 50.0)
            model_input, module = _input(
                {"gb": demand},
                {"cheap": 0.0, "dear": 0.0},
                {"cheap": "gb", "dear": "gb"},
                (
                    _bid(
                        f"cheap-{case}", "cheap", "gb", "up",
                        cheap_capacity, cheap_price,
                    ),
                    _bid(
                        f"dear-{case}", "dear", "gb", "up",
                        demand + 1.0, dear_price,
                    ),
                ),
            )
            with self.subTest(case=case):
                result = module.clear(model_input)
                self.assertAlmostEqual(
                    result.final_dispatch_mwh_by_asset["cheap"], demand
                )
                self.assertAlmostEqual(result.final_dispatch_mwh_by_asset["dear"], 0.0)
                self.assertTrue(all(
                    row["degradation"] <= row["computed_tolerance"]
                    for row in result.extensions["network_solver_diagnostics"]
                ))

    def test_high_scale_primary_is_classified_against_the_gbp1_ceiling(self) -> None:
        demand = {"north": 0.0, "south": 10.0}
        model_input, _module = _input(
            demand,
            {"cheap": 10.0, "local": 0.0},
            {"cheap": "north", "local": "south"},
            (
                _bid(
                    "cheap-down", "cheap", "north", "down", 10.0, 0.0,
                    baseline_mw=10.0,
                ),
                _bid("local-up", "local", "south", "up", 10.0, 100.0),
            ),
            pack=_pack(demand, forward_limit_mw=4.0),
        )
        problem = _problem(model_input)
        # v4 (P0-8): the numerical bid-cost tolerance grows with scale and
        # GBP 1 only classifies it: GO below 10% of the ceiling, completed
        # with a numerical warning (not solver-validated) above GBP 1.
        for scale, expected in (
            (50_000.0, "GO"),
            (2_000_000.0, "COMPLETED_WITH_NUMERICAL_WARNING"),
        ):
            with self.subTest(scale=scale):
                high_scale = replace(
                    problem,
                    primary_objective=problem.primary_objective * scale,
                )
                result = zonal_redispatch.solve_lexicographic(
                    high_scale, DEFAULT_ZONAL_SOLVER_SETTINGS
                )
                primary = result.network_solver_diagnostics[0]
                self.assertAlmostEqual(
                    primary.computed_tolerance,
                    1e-9 * primary.absolute_term_scale,
                    delta=1e-12 * primary.absolute_term_scale,
                )
                self.assertEqual(primary.validation_class, expected)
                self.assertLessEqual(primary.degradation, primary.computed_tolerance)

    def test_primary_secondary_and_physical_degradation_are_each_rejected(self) -> None:
        demand = {"north": 0.0, "south": 10.0}
        model_input, _module = _input(
            demand,
            {"cheap": 10.0, "local": 0.0},
            {"cheap": "north", "local": "south"},
            (
                _bid(
                    "cheap-down", "cheap", "north", "down", 10.0, 0.0,
                    baseline_mw=10.0,
                ),
                _bid("local-up", "local", "south", "up", 10.0, 100.0),
            ),
            pack=_pack(demand, forward_limit_mw=4.0),
        )
        problem = _problem(model_input)
        indices = (
            problem.bid_index["cheap-down"],
            problem.bid_index["local-up"],
            problem.flow_absolute_index["north-south"],
        )
        keys = (
            ("primary_bid_cost_gbp", "primary_bid_cost", "GBP"),
            (
                "secondary_schedule_deviation_mwh",
                "secondary_schedule_deviation",
                "MWh",
            ),
            ("physical_throughput_mwh", "physical_throughput", "MWh"),
        )
        for target, index in enumerate(indices):
            locks = []
            for lock_index, (objective_key, phase_id, unit) in enumerate(keys):
                coefficients = np.zeros(len(problem.variable_names), dtype=float)
                coefficients[indices[lock_index]] = 1.0
                locks.append(zonal_redispatch._ObjectiveCap(
                    coefficients,
                    objective_key,
                    phase_id,
                    unit,
                    0.0,
                    1e-6,
                    1e-6,
                    1,
                    0.0,
                ))
            final_values = np.zeros(len(problem.variable_names), dtype=float)
            final_values[index] = 1e-4
            with self.subTest(phase=keys[target][1]), self.assertRaisesRegex(
                ZonalRedispatchSolveError, "OBJECTIVE_LOCK_VIOLATION"
            ):
                zonal_redispatch._finalise_lexicographic_solution(
                    problem,
                    final_values,
                    {},
                    tuple(locks),
                    DEFAULT_ZONAL_SOLVER_SETTINGS,
                )

    def test_large_computed_tolerances_complete_unvalidated_without_fallback(self) -> None:
        demand = {"north": 0.0, "south": 10.0}
        mutations = (
            ("primary_objective", 200_000.0),
            ("secondary_objective", 1_000_000.0),
            ("physical_tie_objective", 3_000_000.0),
        )
        for attribute, factor in mutations:
            with self.subTest(attribute=attribute), tempfile.TemporaryDirectory() as folder:
                model_input, module = _input(
                    demand,
                    {"cheap": 10.0, "local": 0.0},
                    {"cheap": "north", "local": "south"},
                    (
                        _bid(
                            "cheap-down", "cheap", "north", "down", 10.0, 0.0,
                            baseline_mw=10.0,
                        ),
                        _bid("local-up", "local", "south", "up", 10.0, 100.0),
                    ),
                    pack=_pack(demand, forward_limit_mw=4.0),
                    evidence_root=Path(folder),
                )
                problem = _problem(model_input)
                mutated = replace(
                    problem,
                    **{attribute: getattr(problem, attribute) * factor},
                )
                with patch(
                    "gridform_core.zonal_redispatch.build_single_period_problem",
                    return_value=mutated,
                ):
                    result = module.clear(model_input)
                diagnostics = result.extensions["network_solver_diagnostics"]
                self.assertTrue(attribute == "primary_objective" or any(
                    row["computed_tolerance"] > row["absolute_ceiling"]
                    and row["validation_class"]
                    == "COMPLETED_WITH_NUMERICAL_WARNING"
                    for row in diagnostics
                ))
                self.assertTrue(all(
                    row["degradation"] <= row["computed_tolerance"]
                    for row in diagnostics
                ))
                self.assertFalse(list(
                    (Path(folder) / "market" / "failures").glob("*.json")
                ))
                self.assertIs(
                    result.extensions["automatic_copperplate_fallback"], False
                )

    def test_deliberate_final_degradation_fails_and_preserves_evidence(self) -> None:
        demand = {"north": 0.0, "south": 10.0}
        with tempfile.TemporaryDirectory() as folder:
            model_input, module = _input(
                demand,
                {"cheap": 10.0, "local": 0.0},
                {"cheap": "north", "local": "south"},
                (
                    _bid(
                        "cheap-down", "cheap", "north", "down", 10.0, 0.0,
                        baseline_mw=10.0,
                    ),
                    _bid("local-up", "local", "south", "up", 10.0, 100.0),
                ),
                pack=_pack(demand, forward_limit_mw=4.0),
                evidence_root=Path(folder),
            )
            problem = _problem(model_input)
            real_run_highs = zonal_redispatch._run_highs

            def corrupted_final(*args: object, **kwargs: object):
                values, diagnostics = real_run_highs(*args, **kwargs)
                if kwargs["phase"] == "stable_key":
                    values = values.copy()
                    delta = 0.5
                    values[problem.bid_index["cheap-down"]] += delta
                    values[problem.bid_index["local-up"]] += delta
                    values[problem.flow_index["north-south"]] -= delta
                    values[problem.flow_absolute_index["north-south"]] -= delta
                return values, diagnostics

            with (
                patch(
                    "gridform_core.zonal_redispatch._run_highs",
                    side_effect=corrupted_final,
                ),
                self.assertRaisesRegex(
                    ZonalRedispatchSolveError, "OBJECTIVE_LOCK_VIOLATION"
                ),
            ):
                module.clear(model_input)
            failure_root = (
                Path(folder) / "market" / "failures" / "first-failure"
            )
            manifest = json.loads(
                (failure_root / "manifest.json").read_text(encoding="utf-8")
            )
            failure = json.loads(
                (failure_root / "error.json").read_text(encoding="utf-8")
            )
            solver = json.loads(
                (failure_root / "solver.json").read_text(encoding="utf-8")
            )
            declared_input = json.loads(
                (failure_root / "period-input.json").read_text(encoding="utf-8")
            )
            self.assertEqual(declared_input, model_input.to_dict())
            self.assertEqual(
                failure["diagnostics"]["error_code"],
                "GF_ZONAL_OBJECTIVE_LOCK_VIOLATION",
            )
            self.assertEqual(
                solver["diagnostics"]["phases"]["stable"]["status"], 0
            )
            self.assertTrue(
                solver["diagnostics"]["phases"]["stable"]["message"]
            )
            self.assertIs(manifest["fallback_used"], False)

    def test_shuffled_inputs_produce_identical_stable_dispatch(self) -> None:
        demand = {"north": 0.0, "south": 10.0}
        pack = _pack(demand, forward_limit_mw=4.0)
        bids = (
            _bid(
                "cheap-down", "cheap", "north", "down", 10.0, 0.0,
                baseline_mw=10.0,
            ),
            _bid("local-up", "local", "south", "up", 10.0, 100.0),
        )
        first_input, first_module = _input(
            demand,
            {"cheap": 10.0, "local": 0.0},
            {"cheap": "north", "local": "south"},
            bids,
            pack=pack,
        )
        second_input, second_module = _input(
            demand,
            {"local": 0.0, "cheap": 10.0},
            {"local": "south", "cheap": "north"},
            tuple(reversed(bids)),
            pack=pack,
        )
        first = first_module.clear(first_input)
        second = second_module.clear(second_input)
        self.assertEqual(
            dict(first.final_dispatch_mwh_by_asset),
            dict(second.final_dispatch_mwh_by_asset),
        )
        payload_builder = getattr(
            zonal_redispatch, "normalized_zonal_scientific_result_payload", None
        )
        payload_hash = getattr(
            zonal_redispatch, "normalized_zonal_scientific_result_sha256", None
        )
        self.assertIsNotNone(payload_builder)
        self.assertIsNotNone(payload_hash)
        first_scientific = payload_builder(first)
        second_scientific = payload_builder(second)
        self.assertEqual(first_scientific, second_scientific)
        self.assertEqual(
            payload_hash(first),
            payload_hash(second),
        )
        self.assertNotEqual(contract_sha256(first), contract_sha256(second))

    def test_normalized_scientific_result_payload_covers_every_output(self) -> None:
        result = BalancingResult(
            run_id="run-zonal",
            year=2025,
            period=0,
            period_id="p0",
            ahead_result_sha256="a" * 64,
            source_input_sha256="b" * 64,
            accepted_adjustments=(
                AcceptedAdjustment(
                    "z-bid", "z-agent", "z-asset", "z-zone", 2.0, 10.0, 20.0,
                    "zonal_redispatch_up", {"resource_class": "thermal"},
                ),
                AcceptedAdjustment(
                    "a-bid", "a-agent", "a-asset", "a-zone", -1.0, 5.0, -5.0,
                    "zonal_redispatch_down", {"resource_class": "vre"},
                ),
            ),
            final_dispatch_mwh_by_asset={"z-asset": 2.0, "a-asset": -1.0},
            final_soc_mwh_by_asset={"battery": 3.0},
            curtailment_mwh_by_class={"network": 1.0},
            blackout_mwh=0.25,
            settlement_cashflow_gbp_by_agent={"z-agent": 20.0, "a-agent": -5.0},
            resource_cost_gbp_by_class={"thermal": 12.0, "load_shedding": 4_250.0},
            energy_balance_residual_mwh=0.0,
            extensions={
                "corridor_flow_mwh_by_id": {"z-corridor": 2.0, "a-corridor": -1.0},
                "boundary_transfer_mwh_by_id": {"z-boundary": 2.0, "a-boundary": -1.0},
                "load_shedding_mwh_by_zone": {"z-zone": 0.25, "a-zone": 0.0},
                "storage_dispatch_mwh_by_asset": {
                    "battery": {
                        "charge_mwh": 1.0,
                        "discharge_mwh": 2.0,
                        "net_injection_mwh": 1.0,
                    }
                },
                "primary_objective_gbp": 15.0,
                "secondary_objective_mwh": 3.0,
                "physical_tie_objective": 4.0,
                "stable_tie_objective": 5.0,
                "solver": {"provenance_only": "excluded"},
                "validation": {"artifact_location": "excluded"},
            },
        )
        payload_builder = getattr(
            zonal_redispatch, "normalized_zonal_scientific_result_payload", None
        )
        payload_hash = getattr(
            zonal_redispatch, "normalized_zonal_scientific_result_sha256", None
        )
        self.assertIsNotNone(payload_builder)
        self.assertIsNotNone(payload_hash)
        expected = {
            "schema_version": "value.zonal-scientific-result/v1",
            "accepted_adjustments": [
                result.accepted_adjustments[1].to_dict(),
                result.accepted_adjustments[0].to_dict(),
            ],
            "final_dispatch_mwh_by_asset": {"a-asset": -1.0, "z-asset": 2.0},
            "final_soc_mwh_by_asset": {"battery": 3.0},
            "curtailment_mwh_by_class": {"network": 1.0},
            "blackout_mwh": 0.25,
            "settlement_cashflow_gbp_by_agent": {"a-agent": -5.0, "z-agent": 20.0},
            "resource_cost_gbp_by_class": {"load_shedding": 4_250.0, "thermal": 12.0},
            "energy_balance_residual_mwh": 0.0,
            "corridor_flow_mwh_by_id": {"a-corridor": -1.0, "z-corridor": 2.0},
            "boundary_transfer_mwh_by_id": {"a-boundary": -1.0, "z-boundary": 2.0},
            "load_shedding_mwh_by_zone": {"a-zone": 0.0, "z-zone": 0.25},
            "storage_dispatch_mwh_by_asset": {
                "battery": {
                    "charge_mwh": 1.0,
                    "discharge_mwh": 2.0,
                    "net_injection_mwh": 1.0,
                }
            },
            "objectives": {
                "primary_objective_gbp": 15.0,
                "secondary_objective_mwh": 3.0,
                "physical_tie_objective": 4.0,
                "stable_tie_objective": 5.0,
            },
        }
        self.assertEqual(payload_builder(result), expected)
        self.assertEqual(payload_hash(result), contract_sha256(expected))
        self.assertNotIn("source_input_sha256", expected)
        self.assertNotIn("artifacts", expected)

    def test_mapping_insertion_order_cannot_change_scientific_identity(self) -> None:
        demand = {"gb": 1.0}
        zones = {"large": "gb", "unit": "gb", "negative": "gb"}
        classes = {asset: "export" for asset in zones}
        first_input, first_module = _input(
            demand,
            {"large": 1e16, "negative": -1e16, "unit": 1.0},
            zones,
            resource_class=classes,
        )
        second_input, second_module = _input(
            demand,
            {"large": 1e16, "unit": 1.0, "negative": -1e16},
            zones,
            resource_class=classes,
        )
        first = first_module.clear(first_input)
        second = second_module.clear(second_input)
        payload_builder = getattr(
            zonal_redispatch, "normalized_zonal_scientific_result_payload", None
        )
        payload_hash = getattr(
            zonal_redispatch, "normalized_zonal_scientific_result_sha256", None
        )
        self.assertIsNotNone(payload_builder)
        self.assertIsNotNone(payload_hash)
        self.assertEqual(payload_builder(first), payload_builder(second))
        self.assertEqual(payload_hash(first), payload_hash(second))


class Prompt99AnalyticalRedispatchTests(unittest.TestCase):
    def test_period_bid_physical_cost_overrides_stale_annual_cost_for_accounting(self) -> None:
        model_input, module = _input(
            {"gb": 5.0},
            {"import:fr": 0.0},
            {"import:fr": "gb"},
            (
                _bid(
                    "import-up",
                    "import:fr",
                    "gb",
                    "up",
                    5.0,
                    50.0,
                    resource_class="import",
                ),
            ),
            availability_mw={"import:fr": 5.0},
            resource_class={"import:fr": "import"},
            resource_cost={"import:fr": 100.0},
        )

        result = module.clear(model_input)

        self.assertAlmostEqual(result.resource_cost_gbp_by_class["import"], 250.0)

    def test_unconstrained_and_infinite_limit_reproduce_copperplate_dispatch(self) -> None:
        demand = {"north": 0.0, "south": 10.0}
        for limit in (None, 1_000_000.0):
            pack = _pack(
                demand,
                forward_limit_mw=limit,
                reverse_limit_mw=limit,
            )
            model_input, module = _input(
                demand,
                {"cheap": 0.0, "local": 0.0},
                {"cheap": "north", "local": "south"},
                (
                    _bid("cheap-up", "cheap", "north", "up", 10.0, 10.0),
                    _bid("local-up", "local", "south", "up", 10.0, 50.0),
                ),
                pack=pack,
                resource_class={"cheap": "thermal", "local": "thermal"},
                resource_cost={"cheap": 10.0, "local": 50.0},
            )
            result = module.clear(model_input)
            # Solver contract v4 (P0-8): the bid-cost lock is numerical, so
            # tie-breaking can no longer spend GBP 1 by moving 1/40 MWh
            # (v3 delta 0.026) onto the expensive local unit.
            self.assertAlmostEqual(
                result.final_dispatch_mwh_by_asset["cheap"], 10.0, delta=1e-6
            )
            self.assertAlmostEqual(
                result.final_dispatch_mwh_by_asset["local"], 0.0, delta=1e-6
            )
            self.assertAlmostEqual(
                result.extensions["corridor_flow_mwh_by_id"]["north-south"],
                10.0,
                delta=1e-6,
            )
            primary = solver_diagnostic(result, "primary_bid_cost")
            self.assertLessEqual(primary["degradation"], primary["computed_tolerance"])
            self.assertLess(primary["computed_tolerance"], 1e-6)
            self.assertEqual(primary["validation_class"], "GO")
            self.assertAlmostEqual(
                sum(result.final_dispatch_mwh_by_asset.values()), 10.0,
                delta=1e-7,
            )
            self.assertAlmostEqual(result.blackout_mwh, 0.0)
            self.assertAlmostEqual(result.energy_balance_residual_mwh, 0.0)

    def test_realised_unit_availability_caps_a_larger_flexibility_bid(self) -> None:
        model_input, module = _input(
            {"gb": 5.0},
            {"thermal": 0.0},
            {"thermal": "gb"},
            (_bid("thermal-up", "thermal", "gb", "up", 10.0, 40.0),),
            availability_mw={"thermal": 2.0},
            resource_class={"thermal": "thermal"},
        )
        result = module.clear(model_input)
        self.assertAlmostEqual(result.final_dispatch_mwh_by_asset["thermal"], 2.0)
        self.assertAlmostEqual(result.blackout_mwh, 3.0)

    def test_binding_cutset_uses_local_thermal_and_records_redispatch(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "zonal_redispatch" / "binding-cut.json").read_text(
                encoding="utf-8"
            )
        )
        expected = fixture["expected"]
        demand = {"north": 0.0, "south": 10.0}
        pack = _pack(demand, forward_limit_mw=4.0, reverse_limit_mw=2.0)
        bids = (
            _bid("down-cheap", "cheap", "north", "down", 10.0, 0.0, baseline_mw=10.0),
            _bid("up-local", "local", "south", "up", 10.0, 100.0),
        )
        model_input, module = _input(
            demand,
            {"cheap": 10.0, "local": 0.0},
            {"cheap": "north", "local": "south"},
            bids,
            pack=pack,
            resource_class={"cheap": "thermal", "local": "thermal"},
            resource_cost={"cheap": 10.0, "local": 100.0},
        )
        result = module.clear(model_input)
        self.assertAlmostEqual(
            result.final_dispatch_mwh_by_asset["cheap"],
            expected["cheap_final_mwh"],
            delta=1e-5,
        )
        self.assertAlmostEqual(
            result.final_dispatch_mwh_by_asset["local"],
            expected["local_final_mwh"],
            delta=1e-5,
        )
        self.assertAlmostEqual(
            result.extensions["boundary_transfer_mwh_by_id"]["B_TEST"],
            expected["boundary_transfer_mwh"],
            delta=1e-5,
        )
        primary = solver_diagnostic(result, "primary_bid_cost")
        self.assertLessEqual(
            abs(result.extensions["primary_objective_gbp"] - expected["primary_objective_gbp"]),
            primary["computed_tolerance"],
        )
        accepted = {
            row.bid_id: row.accepted_delta_mwh for row in result.accepted_adjustments
        }
        self.assertAlmostEqual(accepted["down-cheap"], -6.0, delta=1e-5)
        self.assertAlmostEqual(accepted["up-local"], 6.0, delta=1e-5)

    def test_reverse_and_individual_corridor_limits_are_directional(self) -> None:
        demand = {"north": 5.0, "south": 0.0}
        pack = _pack(demand, forward_limit_mw=9.0, reverse_limit_mw=3.0)
        bids = (
            _bid("down-south", "south-gen", "south", "down", 5.0, 0.0, baseline_mw=5.0),
            _bid("up-north", "north-gen", "north", "up", 5.0, 80.0),
        )
        model_input, module = _input(
            demand,
            {"south-gen": 5.0, "north-gen": 0.0},
            {"south-gen": "south", "north-gen": "north"},
            bids,
            pack=pack,
            corridor_limits={
                "north-south": {"forward_limit_mw": 8.0, "reverse_limit_mw": 2.0}
            },
        )
        result = module.clear(model_input)
        self.assertAlmostEqual(result.extensions["corridor_flow_mwh_by_id"]["north-south"], -2.0)
        self.assertAlmostEqual(result.final_dispatch_mwh_by_asset["south-gen"], 2.0)
        self.assertAlmostEqual(result.final_dispatch_mwh_by_asset["north-gen"], 3.0)

    def test_signed_import_and_export_envelopes_are_enforced(self) -> None:
        import_input, import_module = _input(
            {"gb": 5.0},
            {"import:fr": 2.0},
            {"import:fr": "gb"},
            (_bid(
                "import-up", "import:fr", "gb", "up", 10.0, 30.0,
                resource_class="import", baseline_mw=2.0,
            ),),
            interconnector_envelopes={
                "import:fr": {"minimum_mwh": 0.0, "maximum_mwh": 5.0}
            },
            resource_class={"import:fr": "import"},
        )
        imported = import_module.clear(import_input)
        self.assertAlmostEqual(imported.final_dispatch_mwh_by_asset["import:fr"], 5.0)

        export_input, export_module = _input(
            {"north": 0.0, "south": 0.0},
            {"wind": 4.0, "export:fr": 0.0},
            {"wind": "north", "export:fr": "south"},
            (_bid("export-down", "export:fr", "south", "down", 10.0, 20.0, resource_class="export"),),
            interconnector_envelopes={
                "export:fr": {"minimum_mwh": -4.0, "maximum_mwh": 0.0}
            },
            resource_class={"wind": "vre", "export:fr": "export"},
        )
        exported = export_module.clear(export_input)
        self.assertAlmostEqual(exported.final_dispatch_mwh_by_asset["export:fr"], -4.0)
        self.assertAlmostEqual(exported.extensions["corridor_flow_mwh_by_id"]["north-south"], 4.0)

    def test_zero_interconnector_envelope_remains_a_declared_physical_asset(self) -> None:
        model_input, module = _input(
            {"gb": 0.0},
            {},
            {"import:fr": "gb"},
            availability_mw={"import:fr": 0.0},
            resource_class={"import:fr": "import"},
            resource_cost={"import:fr": 30.0},
            interconnector_envelopes={
                "import:fr": {"minimum_mwh": 0.0, "maximum_mwh": 0.0}
            },
        )

        result = module.clear(model_input)

        self.assertAlmostEqual(result.blackout_mwh, 0.0)
        self.assertAlmostEqual(result.energy_balance_residual_mwh, 0.0)

    def test_vre_thermal_dsr_and_voll_compete_in_one_congested_solve(self) -> None:
        demand = {"north": 0.0, "south": 10.0}
        bids = (
            _bid(
                "wind-down", "wind", "north", "down", 10.0, 0.0,
                resource_class="vre", baseline_mw=10.0,
                curtailment_class="network_redispatch_vre",
            ),
            _bid("thermal-up", "thermal", "south", "up", 2.0, 100.0),
            _bid("dsr-up", "dsr", "south", "up", 1.0, 500.0, resource_class="dsr"),
        )
        model_input, module = _input(
            demand,
            {"wind": 10.0, "thermal": 0.0, "dsr": 0.0},
            {"wind": "north", "thermal": "south", "dsr": "south"},
            bids,
            pack=_pack(demand, forward_limit_mw=4.0, reverse_limit_mw=4.0),
            availability_mw={"wind": 10.0, "thermal": 2.0},
            resource_class={"wind": "vre", "thermal": "thermal", "dsr": "dsr"},
        )
        result = module.clear(model_input)
        self.assertAlmostEqual(result.final_dispatch_mwh_by_asset["wind"], 4.0, delta=1e-6)
        self.assertAlmostEqual(result.final_dispatch_mwh_by_asset["thermal"], 2.0)
        self.assertAlmostEqual(result.final_dispatch_mwh_by_asset["dsr"], 1.0)
        self.assertAlmostEqual(result.blackout_mwh, 3.0, delta=1e-6)
        self.assertAlmostEqual(result.curtailment_mwh_by_class["network_redispatch_vre"], 6.0, delta=1e-6)
        primary = solver_diagnostic(result, "primary_bid_cost")
        self.assertLessEqual(
            abs(result.resource_cost_gbp_by_class["load_shedding"] - 51_000.0),
            primary["computed_tolerance"],
        )


class Prompt99StorageTieAndFailureTests(unittest.TestCase):
    def test_mutated_vre_availability_bound_fails_attribution_gate(self) -> None:
        snapshot = VRECounterfactualSnapshot(
            run_id="prompt107-availability-mutation",
            year=2025,
            period=0,
            period_id="p0",
            realised_input_sha256="8" * 64,
            rows=(VRECounterfactualRow(
                asset_id="wind",
                owner_id="owner-wind",
                canonical_technology="Onshore wind",
                zone_id="gb",
                bid_tranche_id="zero-cost",
                realised_available_vre_mwh=10.0,
                perfect_forecast_copperplate_dispatch_mwh=8.0,
                realised_copperplate_dispatch_mwh=8.0,
                zonal_final_dispatch_mwh=10.0001,
            ),),
        )
        with self.assertRaises(CurtailmentAttributionError) as caught:
            attribute_vre_curtailment(snapshot)
        self.assertEqual(
            caught.exception.code, "GF_VRE_DISPATCH_EXCEEDS_AVAILABILITY"
        )

    def test_scaled_mode_rejects_zonal_demand_that_does_not_follow_signed_pack_shares(self) -> None:
        model_input, module = _input(
            {"north": 10.0, "south": 0.0},
            {"generator": 10.0},
            {"generator": "north"},
            (),
            pack=_pack({"north": 2.0, "south": 6.0}),
            zonal_demand_mode="scenario_scaled_zonal_shares",
        )

        with self.assertRaisesRegex(
            ValueError, "does not match the declared signed-pack demand mode"
        ):
            module.clear(model_input)

    def test_storage_soc_efficiency_power_and_energy_limits_handoff(self) -> None:
        specification = {
            "battery": {
                "charge_power_mw": 4.0,
                "discharge_power_mw": 4.0,
                "energy_capacity_mwh": 5.0,
                "charge_efficiency": 0.9,
                "discharge_efficiency": 0.8,
                "bid_contract": "convex_net_power_v1",
            }
        }
        discharge_input, discharge_module = _input(
            {"gb": 3.0},
            {"battery": 0.0},
            {"battery": "gb"},
            (_bid("battery-up", "battery", "gb", "up", 10.0, 20.0, resource_class="storage"),),
            storage=specification,
            initial_soc={"battery": 2.0},
            resource_class={"battery": "storage"},
        )
        discharged = discharge_module.clear(discharge_input)
        self.assertAlmostEqual(discharged.final_dispatch_mwh_by_asset["battery"], 1.6, delta=1e-4)
        self.assertGreaterEqual(discharged.final_soc_mwh_by_asset["battery"], 0.0)
        self.assertLess(discharged.final_soc_mwh_by_asset["battery"], 1e-4)
        self.assertAlmostEqual(discharged.blackout_mwh, 1.4, delta=1e-4)
        self.assertAlmostEqual(discharged.energy_balance_residual_mwh, 0.0)
        self.assertLessEqual(
            solver_diagnostic(discharged, "primary_bid_cost")["degradation"], 1.0
        )
        self.assertAlmostEqual(
            sum(discharged.settlement_cashflow_gbp_by_agent.values()),
            sum(row.cashflow_to_agent_gbp for row in discharged.accepted_adjustments),
        )
        charge_input, charge_module = _input(
            {"gb": 0.0},
            {"wind": 4.0, "battery": 0.0},
            {"wind": "gb", "battery": "gb"},
            (_bid("battery-down", "battery", "gb", "down", 4.0, 0.0, resource_class="storage"),),
            storage=specification,
            initial_soc={"battery": discharged.final_soc_mwh_by_asset["battery"]},
            resource_class={"wind": "vre", "battery": "storage"},
        )
        charged = charge_module.clear(charge_input)
        self.assertAlmostEqual(charged.final_dispatch_mwh_by_asset["battery"], -4.0, delta=1e-4)
        self.assertAlmostEqual(charged.final_soc_mwh_by_asset["battery"], 3.6, delta=1e-4)
        storage_dispatch = charged.extensions["storage_dispatch_mwh_by_asset"]["battery"]
        self.assertAlmostEqual(storage_dispatch["charge_mwh"], 4.0, delta=1e-4)
        self.assertAlmostEqual(storage_dispatch["discharge_mwh"], 0.0)
        self.assertAlmostEqual(charged.energy_balance_residual_mwh, 0.0)
        self.assertAlmostEqual(
            charged.final_soc_mwh_by_asset["battery"],
            discharged.final_soc_mwh_by_asset["battery"]
            + storage_dispatch["charge_mwh"] * specification["battery"]["charge_efficiency"]
            - storage_dispatch["discharge_mwh"]
            / specification["battery"]["discharge_efficiency"],
        )
        self.assertAlmostEqual(
            sum(charged.settlement_cashflow_gbp_by_agent.values()),
            sum(row.cashflow_to_agent_gbp for row in charged.accepted_adjustments),
        )

    def test_solver_bound_noise_is_canonicalized_before_storage_contracts(self) -> None:
        model_input, module = balancing_input_from_fixture(
            FIXTURE_ROOT / "period-bound-noise.json"
        )
        problem = _problem(model_input)
        values = np.zeros(len(problem.variable_names), dtype=float)
        values[problem.storage_discharge_index["battery"]] = -TOLERANCE / 2.0
        solution = SinglePeriodSolution(values, 0.0, 0.0, 0.0, 0.0, {})

        with (
            patch("gridform_core.zonal_redispatch.solve_lexicographic", return_value=solution),
        ):
            result = module.clear(model_input)

        storage = result.extensions["storage_dispatch_mwh_by_asset"]["battery"]
        self.assertEqual(storage["charge_mwh"], 0.0)
        self.assertEqual(storage["discharge_mwh"], 0.0)
        self.assertEqual(storage["net_injection_mwh"], 0.0)
        self.assertEqual(result.final_dispatch_mwh_by_asset["battery"], 0.0)
        self.assertEqual(result.final_soc_mwh_by_asset["battery"], 0.0)
        self.assertEqual(result.energy_balance_residual_mwh, 0.0)

    def test_solver_bound_violation_beyond_tolerance_still_fails(self) -> None:
        specification = {
            "battery": {
                "charge_power_mw": 4.0,
                "discharge_power_mw": 4.0,
                "energy_capacity_mwh": 5.0,
                "charge_efficiency": 0.9,
                "discharge_efficiency": 0.8,
                "bid_contract": "convex_net_power_v1",
            }
        }
        model_input, module = _input(
            {"gb": 0.0},
            {"battery": 0.0},
            {"battery": "gb"},
            storage=specification,
            initial_soc={"battery": 0.0},
            resource_class={"battery": "storage"},
        )
        problem = _problem(model_input)
        values = np.zeros(len(problem.variable_names), dtype=float)
        values[problem.storage_discharge_index["battery"]] = -2.0 * TOLERANCE
        solution = SinglePeriodSolution(values, 0.0, 0.0, 0.0, 0.0, {})

        with (
            patch("gridform_core.zonal_redispatch.solve_lexicographic", return_value=solution),
            self.assertRaisesRegex(ZonalRedispatchSolveError, "declared bound"),
        ):
            module.clear(model_input)

    def test_custom_tolerance_bound_failure_preserves_all_four_phase_diagnostics(self) -> None:
        model_input, _module = balancing_input_from_fixture(
            FIXTURE_ROOT / "period-bound-noise.json"
        )
        settings_payload = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
        settings_payload.update({
            "primal_feasibility_tolerance": 1e-7,
            "dual_feasibility_tolerance": 1e-7,
            "is_builtin_default": False,
            "requires_acknowledgement": True,
        })
        settings = validate_solver_settings(settings_payload)
        real_run_highs = zonal_redispatch._run_highs

        def inject_permitted_solver_noise(*args: object, **kwargs: object):
            values, diagnostics = real_run_highs(*args, **kwargs)
            if kwargs["phase"] == "stable_key":
                problem = args[0]
                values = values.copy()
                values[problem.storage_discharge_index["battery"]] = -5e-8
            return values, diagnostics

        with tempfile.TemporaryDirectory() as folder:
            module = ZonalRedispatchBalancing(settings, evidence_root=Path(folder))
            _bind_module(module, model_input)
            with (
                patch(
                    "gridform_core.zonal_redispatch._run_highs",
                    side_effect=inject_permitted_solver_noise,
                ),
                self.assertRaisesRegex(ZonalRedispatchSolveError, "declared bound"),
            ):
                module.clear(model_input)

            failure_root = (
                Path(folder) / "market" / "failures" / "first-failure"
            )
            manifest = json.loads(
                (failure_root / "manifest.json").read_text(encoding="utf-8")
            )
            failure = json.loads(
                (failure_root / "error.json").read_text(encoding="utf-8")
            )
            solver = json.loads(
                (failure_root / "solver.json").read_text(encoding="utf-8")
            )
            declared_input = json.loads(
                (failure_root / "period-input.json").read_text(encoding="utf-8")
            )
            self.assertEqual(declared_input, model_input.to_dict())
            self.assertEqual(
                manifest["period_input_sha256"], contract_sha256(model_input)
            )
            self.assertEqual(
                failure["diagnostics"]["error_code"],
                "GF_ZONAL_SOLUTION_BOUND_VIOLATION",
            )
            self.assertEqual(len(failure["diagnostics"]["completed_phase_optima"]), 3)
            self.assertEqual(
                [
                    row["phase_id"]
                    for row in failure["diagnostics"]["completed_phase_optima"]
                ],
                [
                    "primary_bid_cost",
                    "secondary_schedule_deviation",
                    "physical_throughput",
                ],
            )
            phases = dict(solver["diagnostics"]["phases"])
            # v4 records the shed lock between the primary and later phases.
            self.assertEqual(phases.pop("primary_shed_lock")["mode"], "fixed_zero")
            self.assertEqual(set(phases), {"primary", "secondary", "physical", "stable"})
            for phase in phases.values():
                self.assertEqual(phase["status"], 0)
                self.assertTrue(phase["message"])
                self.assertTrue(np.isfinite(phase["objective_value"]))
            self.assertEqual(
                solver["diagnostics"]["solver_settings"], settings.to_dict()
            )
            self.assertIs(manifest["fallback_used"], False)

    def test_nonconvex_storage_bid_that_can_self_cycle_is_rejected(self) -> None:
        bids = (
            _bid("battery-up", "battery", "gb", "up", 5.0, 0.0, resource_class="storage"),
            _bid("battery-down", "battery", "gb", "down", 5.0, 10.0, resource_class="storage"),
        )
        model_input, _module = _input(
            {"gb": 0.0},
            {"battery": 0.0},
            {"battery": "gb"},
            bids,
            storage={
                "battery": {
                    "charge_power_mw": 5.0,
                    "discharge_power_mw": 5.0,
                    "energy_capacity_mwh": 10.0,
                    "charge_efficiency": 0.9,
                    "discharge_efficiency": 0.9,
                    "bid_contract": "convex_net_power_v1",
                }
            },
            initial_soc={"battery": 5.0},
            resource_class={"battery": "storage"},
        )
        with self.assertRaisesRegex(ZonalRedispatchInputError, "convex|self-cycle"):
            _problem(model_input)

    def test_equal_bid_equal_network_effect_is_pro_rata_and_byte_stable(self) -> None:
        bids = (
            _bid("a", "a", "gb", "up", 4.0, 50.0, network_effect_id="gb:injection"),
            _bid("b", "b", "gb", "up", 6.0, 50.0, network_effect_id="gb:injection"),
        )
        model_input, first_module = _input(
            {"gb": 5.0}, {"a": 0.0, "b": 0.0}, {"a": "gb", "b": "gb"}, bids
        )
        first = first_module.clear(model_input)
        _, second_module = _input(
            {"gb": 5.0}, {"a": 0.0, "b": 0.0}, {"a": "gb", "b": "gb"}, bids
        )
        second = second_module.clear(model_input)
        accepted = {row.bid_id: row.accepted_delta_mwh for row in first.accepted_adjustments}
        self.assertAlmostEqual(accepted["a"], 2.0)
        self.assertAlmostEqual(accepted["b"], 3.0)
        self.assertEqual(contract_sha256(first), contract_sha256(second))

    def test_public_pure_solver_functions_reconcile_the_solution(self) -> None:
        model_input, _module = _input(
            {"gb": 2.0},
            {"g": 0.0},
            {"g": "gb"},
            (_bid("g-up", "g", "gb", "up", 5.0, 40.0),),
        )
        problem = _problem(model_input)
        primary = solve_primary(problem)
        final = solve_secondary(problem, primary)
        validation = validate_solution(problem, final)
        self.assertLessEqual(validation["maximum_residual"], 1e-8)
        self.assertAlmostEqual(final.primary_objective_gbp, 80.0)

    def test_public_solver_compatibility_path_replays_retained_period_with_one_sided_locks(self) -> None:
        model_input, _module = balancing_input_from_fixture(
            FIXTURE_ROOT / "period-2025-14.json.gz"
        )
        problem = _problem(model_input)

        with patch("scipy.optimize.linprog", wraps=linprog) as wrapped:
            primary = solve_primary(problem)
            final = solve_secondary(problem, primary)

        calls = wrapped.call_args_list
        base_inequalities = len(problem.inequality_matrix)
        base_equalities = len(problem.equality_matrix)
        self.assertEqual(len(calls), 4)
        self.assertEqual(
            [len(call.kwargs["A_ub"]) for call in calls],
            [base_inequalities, base_inequalities + 1,
             base_inequalities + 2, base_inequalities + 3],
        )
        self.assertEqual(
            [len(call.kwargs["A_eq"]) for call in calls],
            [base_equalities] * 4,
        )
        self.assertEqual(len(final.network_solver_diagnostics), 3)
        self.assertTrue(all(
            row.degradation <= row.computed_tolerance
            for row in final.network_solver_diagnostics
        ))

    def test_changed_run_context_identity_is_rejected_before_solve(self) -> None:
        model_input, module = _input(
            {"gb": 1.0},
            {"g": 0.0},
            {"g": "gb"},
            (_bid("g-up", "g", "gb", "up", 1.0, 40.0),),
        )
        payload = model_input.to_dict()
        payload["domain_payload"]["run_context_ref"]["sha256"] = "0" * 64
        corrupted = BalancingInput.from_dict(payload)
        with self.assertRaisesRegex(ZonalRedispatchInputError, "Run context reference"):
            module.clear(corrupted)

    def test_success_avoids_period_diagnostics_and_input_is_committed_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            model_input, module = _input(
                {"gb": 1.0},
                {"g": 0.0},
                {"g": "gb"},
                (_bid("g-up", "g", "gb", "up", 1.0, 40.0),),
                evidence_root=Path(temporary),
            )
            result = module.clear(model_input)
            self.assertEqual(result.artifacts, ())
            self.assertFalse((Path(temporary) / "market" / "zonal-redispatch").exists())
            with self.assertRaisesRegex(ZonalRedispatchInputError, "already been balanced"):
                module.clear(model_input)

    def test_infeasible_run_preserves_declared_input_and_never_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            model_input, module = _input(
                {"gb": 0.0},
                {"must-run": 5.0},
                {"must-run": "gb"},
                (),
                availability_mw={"must-run": 5.0},
                evidence_root=evidence,
            )
            with self.assertRaisesRegex(ZonalRedispatchSolveError, "infeasible"):
                module.clear(model_input)
            failure_root = evidence / "market" / "failures" / "first-failure"
            manifest = json.loads(
                (failure_root / "manifest.json").read_text(encoding="utf-8")
            )
            failure = json.loads(
                (failure_root / "error.json").read_text(encoding="utf-8")
            )
            solver = json.loads(
                (failure_root / "solver.json").read_text(encoding="utf-8")
            )
            declared_input = json.loads(
                (failure_root / "period-input.json").read_text(encoding="utf-8")
            )
            self.assertEqual(declared_input, model_input.to_dict())
            self.assertEqual(manifest["fallback_used"], False)
            self.assertEqual(solver["method"], "highs-ds")
            self.assertEqual(failure["stage"], "lexicographic_solve")

    def test_manifest_registers_only_the_zonal_balancing_capability(self) -> None:
        from gridform_core.v2.module_manifest import workspace_registry

        manifest = workspace_registry(ROOT / "missing-modules").manifest(
            "value-zonal-redispatch-balancing"
        )
        self.assertEqual(manifest.slot, "balancing")
        self.assertIn("domain.network.zonal_redispatch", manifest.provides_capabilities)
        self.assertNotIn("domain.network.dc", manifest.provides_capabilities)
        self.assertNotIn("domain.network.ac", manifest.provides_capabilities)


if __name__ == "__main__":
    unittest.main()
