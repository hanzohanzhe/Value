from __future__ import annotations

import copy
import inspect
import unittest
from dataclasses import replace
from pathlib import Path

import pulp

from gridform_validation.cbc import cbc_path

from gridform_core.builtin.scheme_c_1000twh.staged_psm import (
    _validate_vre_counterfactual_cases,
)
from gridform_core.staged_market_contracts import BalancingInput
from gridform_core.staged_market_contracts import (
    AheadMarketResult,
    FlexibilityBid,
    contract_sha256,
)
from gridform_core.vre_curtailment_attribution import (
    CurtailmentAttributionError,
    VRECounterfactualRow,
    VRECounterfactualSnapshot,
    attribute_vre_curtailment,
)
from gridform_core.zonal_contracts import (
    TransportCorridor,
    NetworkZone,
    SpatialAudit,
    ZonalDemand,
    ZonalNetworkPack,
)
from gridform_validation.zonal_case_generator import (
    analytical_cases,
    production_solution,
    random_convex_case,
)
from gridform_validation.zonal_oracle import (
    audit_zonal_candidate,
    compare_zonal_solutions,
    solve_zonal_oracle,
)


ROOT = Path(__file__).resolve().parents[1]
TOLERANCES = {
    "energy_mwh": 1e-6,
    "cost_gbp": 1e-5,
    "objective_relative": 1e-8,
}


def _prompt107_three_case_declaration(*, step: int, seed: int) -> dict[str, object]:
    """Declare forecast error and binding two-zone congestion for one period."""

    period_id = f"p{step:04d}"
    period_hours = 0.5
    # Deterministic seed variation prevents a single hand-picked numeric case while
    # retaining strict inequalities between the three VRE dispatches.
    phase = ((seed * 37 + step * 17) % 101) / 100.0
    total_demand = round(3.8 + 0.4 * phase, 6)
    north_demand = round(0.45 + 0.1 * phase, 6)
    south_demand = round(total_demand - north_demand, 6)
    forecast_wind = round(1.7 + 0.2 * phase, 6)
    realised_wind_available = round(total_demand + 0.3, 6)
    forward_limit_mwh = round(0.35 + 0.05 * phase, 6)
    thermal_schedule = round(total_demand - forecast_wind, 6)
    run_id = f"prompt107-three-case-{seed}"
    corridor = TransportCorridor(
        "north-south", "north", "south", "from_to_positive"
    )
    pack = ZonalNetworkPack(
        network_pack_id="prompt107-two-zone-forecast-error",
        scientific_sha256="",
        zones=(
            NetworkZone("north", "North", "fixture DSO", "England"),
            NetworkZone("south", "South", "fixture DSO", "England"),
        ),
        corridors=(corridor,),
        cutsets=(),
        asset_mappings=(),
        zonal_demand=ZonalDemand(
            (period_id,),
            {"north": (north_demand,), "south": (south_demand,)},
            (total_demand,),
        ),
        rating_profiles=(),
        interconnector_landings=(),
        spatial_audit=SpatialAudit((), {}, {}, 1e-9),
        loss_capability_absent_reason="lossless_v1",
        provenance={"information_scope": "current_period_only"},
    )
    pack = replace(pack, scientific_sha256=pack.compute_scientific_sha256())
    ahead = AheadMarketResult(
        run_id=run_id,
        year=2025,
        period=step,
        period_id=period_id,
        information_scope="forecast_only",
        schedule_mwh_by_asset={
            "wind-north": forecast_wind,
            "thermal-south": thermal_schedule,
        },
        clearing_price_gbp_per_mwh=70.0,
        accepted_volume_mwh=total_demand,
        settlement_mwh_by_asset={
            "wind-north": forecast_wind,
            "thermal-south": thermal_schedule,
        },
        storage_scheduled_action_mwh_by_asset={},
        source_input_sha256="b" * 64,
        extensions={
            "forecast_wind_available_mwh": forecast_wind,
            "forecast_error_mwh": realised_wind_available - forecast_wind,
        },
    )

    def bid(
        bid_id: str,
        asset: str,
        zone: str,
        direction: str,
        available_mwh: float,
        price: float,
        resource_class: str,
        baseline_mwh: float,
    ) -> FlexibilityBid:
        return FlexibilityBid(
            bid_id=bid_id,
            agent_id=asset,
            asset_id=asset,
            technology=resource_class,
            zone_id=zone,
            period_id=period_id,
            direction=direction,
            available_mw=available_mwh / period_hours,
            price_gbp_per_mwh=price,
            baseline_mw=baseline_mwh / period_hours,
            physical_cost_gbp_per_mwh=price,
            network_effect_id=f"{zone}:injection",
            provenance={"resource_class": resource_class},
            extensions={"available_mwh": available_mwh},
        )

    bids = (
        bid(
            "wind-down", "wind-north", "north", "down",
            forecast_wind, 0.0, "vre", forecast_wind,
        ),
        bid(
            "thermal-up", "thermal-south", "south", "up",
            total_demand, 70.0, "thermal", thermal_schedule,
        ),
    )
    model_input = BalancingInput(
        run_id=run_id,
        year=2025,
        period=step,
        period_id=period_id,
        ahead_result_sha256=contract_sha256(ahead),
        real_demand_mwh=total_demand,
        realised_availability_mw_by_asset={
            "wind-north": realised_wind_available / period_hours,
            "thermal-south": total_demand / period_hours,
        },
        initial_soc_mwh_by_asset={},
        bids=bids,
        period_hours=period_hours,
        voll_gbp_per_mwh=17_000.0,
        domain_payload={
            "schema_version": "value.zonal-redispatch-domain/v1",
            "zonal_demand_mode": "network_pack_absolute_demand",
            "ahead_result": ahead.to_dict(),
            "network_pack": pack.to_dict(),
            "real_demand_mwh_by_zone": {
                "north": north_demand,
                "south": south_demand,
            },
            "asset_zone_id_by_asset": {
                "wind-north": "north",
                "thermal-south": "south",
            },
            "resource_class_by_asset": {
                "wind-north": "vre",
                "thermal-south": "thermal",
            },
            "resource_cost_gbp_per_mwh_by_asset": {
                "wind-north": 0.0,
                "thermal-south": 70.0,
            },
            "storage": {},
            "interconnector_envelope_mwh_by_asset": {},
            "corridor_limits_mw_by_id": {
                "north-south": {
                    "forward_limit_mw": forward_limit_mwh / period_hours,
                    "reverse_limit_mw": forward_limit_mwh / period_hours,
                }
            },
            "chronology_contract": {
                "information_scope": "current_period_only",
                "future_period_data_supplied": False,
                "forecast_error_mwh": realised_wind_available - forecast_wind,
                "binding_forward_limit_mwh": forward_limit_mwh,
            },
        },
    )
    return model_input.to_dict()


def _solve_prompt107_three_case_lp(
    declaration: dict[str, object],
) -> dict[str, dict[str, float]]:
    """Solve all three independent counterfactual clears in one CBC process."""

    model_input = BalancingInput.from_dict(declaration)
    domain = dict(model_input.domain_payload)
    ahead = dict(domain["ahead_result"])
    schedule = {
        str(asset): float(value)
        for asset, value in dict(ahead["schedule_mwh_by_asset"]).items()
    }
    zones = {str(key): str(value) for key, value in dict(
        domain["asset_zone_id_by_asset"]
    ).items()}
    demand_by_zone = {
        str(key): float(value)
        for key, value in dict(domain["real_demand_mwh_by_zone"]).items()
    }
    costs = {
        str(key): float(value)
        for key, value in dict(domain["resource_cost_gbp_per_mwh_by_asset"]).items()
    }
    availability = {
        asset: float(value) * model_input.period_hours
        for asset, value in model_input.realised_availability_mw_by_asset.items()
    }
    problem = pulp.LpProblem("prompt107_combined_three_case", pulp.LpMinimize)

    perfect = {
        asset: pulp.LpVariable(
            f"perfect__{asset}", lowBound=0.0, upBound=availability[asset]
        )
        for asset in schedule
    }
    perfect_shed = pulp.LpVariable("perfect__load_shedding", lowBound=0.0)
    problem += (
        pulp.lpSum(perfect.values()) + perfect_shed
        == float(model_input.real_demand_mwh)
    ), "perfect__national_balance"

    scheduled_supply = sum(schedule.values())
    gap = float(model_input.real_demand_mwh) - scheduled_supply
    realised_accept = {}
    for bid in model_input.bids:
        direction_allowed = (
            (gap > 1e-9 and bid.direction == "up")
            or (gap < -1e-9 and bid.direction == "down")
        )
        realised_accept[bid.bid_id] = pulp.LpVariable(
            f"realised__{bid.bid_id}",
            lowBound=0.0,
            upBound=(float(bid.extensions["available_mwh"]) if direction_allowed else 0.0),
        )
    realised = {
        asset: float(schedule[asset]) + pulp.lpSum(
            (1.0 if bid.direction == "up" else -1.0)
            * realised_accept[bid.bid_id]
            for bid in model_input.bids if bid.asset_id == asset
        )
        for asset in schedule
    }
    realised_shed = pulp.LpVariable("realised__load_shedding", lowBound=0.0)
    problem += (
        pulp.lpSum(realised.values()) + realised_shed
        == float(model_input.real_demand_mwh)
    ), "realised__national_balance"
    for asset, dispatch in realised.items():
        problem += dispatch >= 0.0, f"realised__minimum__{asset}"
        problem += dispatch <= availability[asset], f"realised__maximum__{asset}"

    zonal_accept = {
        bid.bid_id: pulp.LpVariable(
            f"zonal__{bid.bid_id}",
            lowBound=0.0,
            upBound=float(bid.extensions["available_mwh"]),
        )
        for bid in model_input.bids
    }
    zonal = {
        asset: float(schedule[asset]) + pulp.lpSum(
            (1.0 if bid.direction == "up" else -1.0) * zonal_accept[bid.bid_id]
            for bid in model_input.bids if bid.asset_id == asset
        )
        for asset in schedule
    }
    for asset, dispatch in zonal.items():
        problem += dispatch >= 0.0, f"zonal__minimum__{asset}"
        problem += dispatch <= availability[asset], f"zonal__maximum__{asset}"
    network = dict(domain["network_pack"])
    raw_limits = dict(domain["corridor_limits_mw_by_id"])
    flows = {}
    corridor_ends = {}
    for raw_corridor in network["corridors"]:
        corridor = dict(raw_corridor)
        corridor_id = str(corridor["corridor_id"])
        limit = dict(raw_limits[corridor_id])
        flows[corridor_id] = pulp.LpVariable(
            f"zonal__flow__{corridor_id}",
            lowBound=-float(limit["reverse_limit_mw"]) * model_input.period_hours,
            upBound=float(limit["forward_limit_mw"]) * model_input.period_hours,
        )
        corridor_ends[corridor_id] = (
            str(corridor["from_zone_id"]), str(corridor["to_zone_id"])
        )
    zonal_shed = {
        zone: pulp.LpVariable(f"zonal__load_shedding__{zone}", lowBound=0.0)
        for zone in demand_by_zone
    }
    for zone, demand in demand_by_zone.items():
        exports = pulp.lpSum(
            flow for corridor_id, flow in flows.items()
            if corridor_ends[corridor_id][0] == zone
        )
        imports = pulp.lpSum(
            flow for corridor_id, flow in flows.items()
            if corridor_ends[corridor_id][1] == zone
        )
        problem += (
            pulp.lpSum(dispatch for asset, dispatch in zonal.items() if zones[asset] == zone)
            + zonal_shed[zone] + imports - exports == demand
        ), f"zonal__balance__{zone}"

    bid_cost = lambda bid, accepted: (
        (float(bid.price_gbp_per_mwh) if bid.direction == "up"
         else -float(bid.price_gbp_per_mwh)) * accepted[bid.bid_id]
    )
    problem += (
        pulp.lpSum(costs[asset] * dispatch for asset, dispatch in perfect.items())
        + model_input.voll_gbp_per_mwh * perfect_shed
        + pulp.lpSum(bid_cost(bid, realised_accept) for bid in model_input.bids)
        + model_input.voll_gbp_per_mwh * realised_shed
        + pulp.lpSum(bid_cost(bid, zonal_accept) for bid in model_input.bids)
        + model_input.voll_gbp_per_mwh * pulp.lpSum(zonal_shed.values())
    )
    status = problem.solve(pulp.COIN_CMD(msg=False, path=cbc_path()))
    if status != pulp.LpStatusOptimal:
        raise RuntimeError(
            f"Prompt 107 combined CBC was {pulp.LpStatus[status]}"
        )

    def values(mapping):
        return {
            asset: (0.0 if abs(float(pulp.value(value) or 0.0)) <= 1e-10
                    else float(pulp.value(value)))
            for asset, value in mapping.items()
        }

    return {
        "perfect_forecast_copperplate": values(perfect),
        "realised_copperplate": values(realised),
        "zonal_final": values(zonal),
    }


def _assert_vre_attribution_matches_independent_lp(
    test: unittest.TestCase,
    declaration: dict[str, object],
    production: dict[str, object],
    cases: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Compare production attribution with literal quantities from PuLP/CBC."""

    model_input = BalancingInput.from_dict(declaration)
    domain = dict(model_input.domain_payload)
    classes = dict(domain["resource_class_by_asset"])
    zones = dict(domain["asset_zone_id_by_asset"])
    vre_assets = tuple(sorted(
        asset for asset, resource_class in classes.items()
        if resource_class == "vre"
    ))
    available = {
        asset: float(model_input.realised_availability_mw_by_asset[asset])
        * float(model_input.period_hours)
        for asset in vre_assets
    }
    perfect = {
        asset: float(cases["perfect_forecast_copperplate"].get(asset, 0.0))
        for asset in vre_assets
    }
    realised = {
        asset: float(cases["realised_copperplate"].get(asset, 0.0))
        for asset in vre_assets
    }
    final = {
        asset: float(cases["zonal_final"].get(asset, 0.0))
        for asset in vre_assets
    }
    snapshot = VRECounterfactualSnapshot(
        run_id=str(model_input.run_id),
        year=int(model_input.year),
        period=int(model_input.period),
        period_id=str(model_input.period_id),
        realised_input_sha256="9" * 64,
        rows=tuple(
            VRECounterfactualRow(
                asset_id=asset,
                owner_id=f"owner-{asset}",
                canonical_technology="Onshore wind",
                zone_id=str(zones[asset]),
                bid_tranche_id="independent-zero-cost",
                realised_available_vre_mwh=available[asset],
                perfect_forecast_copperplate_dispatch_mwh=perfect[asset],
                realised_copperplate_dispatch_mwh=realised[asset],
                zonal_final_dispatch_mwh=float(
                    production["final_dispatch_mwh_by_asset"].get(asset, 0.0)
                ),
            )
            for asset in vre_assets
        ),
    )
    attribution_result = attribute_vre_curtailment(snapshot)
    attributed = attribution_result.period
    for asset in vre_assets:
        test.assertAlmostEqual(
            float(production["final_dispatch_mwh_by_asset"].get(asset, 0.0)),
            final[asset], places=6, msg=f"{asset} production zonal final",
        )
    available_total = sum(available.values())
    perfect_total = sum(perfect.values())
    realised_total = sum(realised.values())
    final_total = sum(final.values())
    forecast_delta = perfect_total - realised_total
    redispatch_delta = realised_total - final_total
    expected = {
        "zonal_final_dispatch_mwh": final_total,
        "economic_curtailment_mwh": available_total - perfect_total,
        "forecast_added_curtailment_mwh": max(forecast_delta, 0.0),
        "forecast_avoided_curtailment_mwh": max(-forecast_delta, 0.0),
        "redispatch_added_curtailment_mwh": max(redispatch_delta, 0.0),
        "redispatch_avoided_curtailment_mwh": max(-redispatch_delta, 0.0),
        "total_curtailment_mwh": available_total - final_total,
    }
    for field, value in expected.items():
        test.assertAlmostEqual(getattr(attributed, field), value, places=6, msg=field)
    detail_by_asset = {detail.asset_id: detail for detail in attribution_result.details}
    for asset in vre_assets:
        detail = detail_by_asset[asset]
        test.assertAlmostEqual(
            detail.perfect_reference_dispatch_mwh,
            perfect[asset], places=6,
        )
        test.assertAlmostEqual(
            detail.copperplate_reference_dispatch_mwh,
            realised[asset], places=6,
        )
        test.assertAlmostEqual(detail.zonal_final_dispatch_mwh, final[asset], places=6)
    return {
        "maximum_residual_mwh": abs(float(attributed.identity_residual_mwh)),
        "forecast_net_impact_mwh": (
            expected["forecast_added_curtailment_mwh"]
            - expected["forecast_avoided_curtailment_mwh"]
        ),
        "redispatch_net_impact_mwh": (
            expected["redispatch_added_curtailment_mwh"]
            - expected["redispatch_avoided_curtailment_mwh"]
        ),
    }


class Prompt103IndependenceAndAnalyticalTests(unittest.TestCase):
    def test_oracle_has_no_production_solver_or_matrix_import(self) -> None:
        source = inspect.getsource(__import__(
            "gridform_validation.zonal_oracle", fromlist=["*"]
        ))
        forbidden = (
            "gridform_core.zonal_redispatch",
            "build_single_period_problem",
            "solve_primary",
            "solve_secondary",
            "scipy.optimize",
            "numpy",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn("pulp.COIN_CMD", source)
        three_case_source = inspect.getsource(_solve_prompt107_three_case_lp)
        for token in (
            "production_solution",
            "solve_zonal_oracle",
            "attribute_vre_curtailment",
            "gridform_core.zonal_redispatch",
        ):
            self.assertNotIn(token, three_case_source)
        self.assertEqual(three_case_source.count("problem.solve(pulp.COIN_CMD"), 1)

    # P0-8 S1: the production v3 contract lets later phases spend the GBP 1
    # primary allowance (P2-01), so the exact-lock CBC oracle differs by
    # about GBP 1 per period.  Solver contract v4 (P0-8 S4) removes the
    # expected failure.
    @unittest.expectedFailure
    def test_hand_solvable_cases_match_independent_oracle(self) -> None:
        for name, declaration in analytical_cases().items():
            with self.subTest(case=name):
                production = production_solution(declaration)
                oracle = solve_zonal_oracle(declaration)
                comparison = compare_zonal_solutions(
                    declaration, production, oracle, tolerances=TOLERANCES
                )
                self.assertTrue(comparison["passed"], comparison)

    # P0-8 S1: the production v3 contract lets later phases spend the GBP 1
    # primary allowance (P2-01), so the exact-lock CBC oracle differs by
    # about GBP 1 per period.  Solver contract v4 (P0-8 S4) removes the
    # expected failure.
    @unittest.expectedFailure
    def test_seeded_random_convex_cases_match(self) -> None:
        maximum_residual = 0.0
        forecast_impacts = []
        redispatch_impacts = []
        for step, seed in enumerate((7, 19, 101, 2026)):
            with self.subTest(seed=seed):
                declaration = random_convex_case(seed)
                production = production_solution(declaration)
                oracle = solve_zonal_oracle(declaration)
                comparison = compare_zonal_solutions(
                    declaration, production, oracle, tolerances=TOLERANCES
                )
                self.assertTrue(comparison["passed"], comparison)
                attribution_declaration = _prompt107_three_case_declaration(
                    step=step, seed=seed
                )
                attribution_production = production_solution(
                    attribution_declaration
                )
                cases = _solve_prompt107_three_case_lp(attribution_declaration)
                full_oracle = solve_zonal_oracle(attribution_declaration)
                self.assertAlmostEqual(
                    full_oracle["final_dispatch_mwh_by_asset"]["wind-north"],
                    cases["zonal_final"]["wind-north"],
                    places=6,
                )
                attribution = _assert_vre_attribution_matches_independent_lp(
                    self, attribution_declaration, attribution_production, cases
                )
                maximum_residual = max(
                    maximum_residual, attribution["maximum_residual_mwh"]
                )
                forecast_impacts.append(attribution["forecast_net_impact_mwh"])
                redispatch_impacts.append(attribution["redispatch_net_impact_mwh"])
        self.assertTrue(any(abs(value) > 1e-6 for value in forecast_impacts))
        self.assertTrue(any(abs(value) > 1e-6 for value in redispatch_impacts))
        print(f"PROMPT107_MAX_IDENTITY_RESIDUAL_MWH={maximum_residual:.17g}")

    def test_24_and_168_hour_sequences_match_without_future_information(self) -> None:
        for hours, seed in ((24, 24), (168, 168)):
            with self.subTest(hours=hours):
                maximum_residual = 0.0
                forecast_impacts = []
                redispatch_impacts = []
                for step in range(hours * 2):
                    declaration = _prompt107_three_case_declaration(
                        step=step, seed=seed
                    )
                    production = production_solution(declaration)
                    cases = _solve_prompt107_three_case_lp(declaration)
                    audit = audit_zonal_candidate(declaration, production)
                    self.assertTrue(audit["passed"], audit)
                    self.assertAlmostEqual(
                        production["final_dispatch_mwh_by_asset"]["wind-north"],
                        cases["zonal_final"]["wind-north"], places=6,
                    )
                    if step in {0, 1, hours * 2 - 1}:
                        full_oracle = solve_zonal_oracle(declaration)
                        self.assertAlmostEqual(
                            full_oracle["final_dispatch_mwh_by_asset"]["wind-north"],
                            cases["zonal_final"]["wind-north"], places=6,
                        )
                    attribution = _assert_vre_attribution_matches_independent_lp(
                        self, declaration, production, cases
                    )
                    maximum_residual = max(
                        maximum_residual, attribution["maximum_residual_mwh"]
                    )
                    forecast_impacts.append(
                        attribution["forecast_net_impact_mwh"]
                    )
                    redispatch_impacts.append(
                        attribution["redispatch_net_impact_mwh"]
                    )
                    chronology = declaration["domain_payload"]["chronology_contract"]
                    self.assertEqual(chronology["information_scope"], "current_period_only")
                    self.assertFalse(chronology["future_period_data_supplied"])
                    self.assertGreater(chronology["forecast_error_mwh"], 0.0)
                    network = declaration["domain_payload"]["network_pack"]
                    self.assertEqual(len(network["zones"]), 2)
                    self.assertEqual(len(network["corridors"]), 1)
                self.assertEqual(step + 1, hours * 2)
                self.assertTrue(
                    any(abs(value) > 1e-6 for value in forecast_impacts)
                )
                self.assertTrue(
                    any(abs(value) > 1e-6 for value in redispatch_impacts)
                )
                print(
                    "PROMPT107_MAX_IDENTITY_RESIDUAL_MWH="
                    f"{maximum_residual:.17g}"
                )


class Prompt103MutationAndFailureTests(unittest.TestCase):
    def test_counterfactual_object_id_mutation_fails_with_set_mismatch(self) -> None:
        cases = {
            "perfect_forecast_copperplate": {"wind": 1.0},
            "realised_copperplate": {"wind": 1.0},
            "zonal_final": {"renamed-wind": 1.0},
        }
        identities = {name: "a" * 64 for name in cases}
        modules = {name: f"module-{name}@1.0.0" for name in cases}
        with self.assertRaises(CurtailmentAttributionError) as caught:
            _validate_vre_counterfactual_cases(
                expected_keys={("wind", "zero-cost")},
                canonical_key_by_asset={
                    "wind": ("wind", "zero-cost"),
                    "renamed-wind": ("renamed-wind", "zero-cost"),
                },
                dispatch_by_case=cases,
                realised_input_sha256_by_case=identities,
                module_identities=modules,
            )
        self.assertEqual(
            caught.exception.code, "GF_VRE_COUNTERFACTUAL_SET_MISMATCH"
        )

    def test_each_declared_constraint_mutation_fails_its_gate(self) -> None:
        declaration = random_convex_case(41)
        valid = solve_zonal_oracle(declaration)
        self.assertTrue(audit_zonal_candidate(declaration, valid)["passed"])
        mutations = {
            "zonal_balance": ("final_dispatch_mwh_by_asset", "thermal-south", 1.0),
            "forward_limit": ("corridor_flow_mwh_by_id", "north-mid", 100.0),
            "reverse_limit": ("corridor_flow_mwh_by_id", "north-mid", -100.0),
            "cutset_incidence": ("boundary_transfer_mwh_by_id", "B_NORTH", 100.0),
            "storage_efficiency": ("final_soc_mwh_by_asset", "battery", 0.321),
            "storage_power": ("storage_discharge_mwh_by_asset", "battery", 100.0),
            "storage_energy": ("final_soc_mwh_by_asset", "battery", 100.0),
            "interconnector_sign": ("final_dispatch_mwh_by_asset", "import-fr", 100.0),
            "realised_availability": ("final_dispatch_mwh_by_asset", "thermal-south", 100.0),
            "voll": ("primary_objective_gbp", None, -1.0),
            "secondary_tie_breaking": ("secondary_objective_mwh", None, 1e6),
        }
        detected = {}
        for name, (field, key, value) in mutations.items():
            candidate = copy.deepcopy(valid)
            if key is None:
                candidate[field] = value
            else:
                candidate[field][key] = value
            report = audit_zonal_candidate(declaration, candidate)
            detected[name] = not report["passed"]
        self.assertEqual(set(detected), set(mutations))
        self.assertTrue(all(detected.values()), detected)

    def test_malformed_impossible_and_infeasible_inputs_are_rejected(self) -> None:
        declaration = random_convex_case(9)
        malformed = copy.deepcopy(declaration)
        malformed["domain_payload"]["schema_version"] = "wrong"
        with self.assertRaises(ValueError):
            solve_zonal_oracle(malformed)

        impossible_soc = copy.deepcopy(declaration)
        impossible_soc["initial_soc_mwh_by_asset"]["battery"] = 1e6
        with self.assertRaises(ValueError):
            solve_zonal_oracle(impossible_soc)

        isolated = copy.deepcopy(declaration)
        isolated["domain_payload"]["network_pack"]["corridors"] = []
        isolated["domain_payload"]["network_pack"]["cutsets"] = []
        with self.assertRaises(ValueError):
            solve_zonal_oracle(isolated)

        zero_flex = copy.deepcopy(analytical_cases()["signed-import"])
        zero_flex["bids"] = []
        zero_flex_result = solve_zonal_oracle(zero_flex)
        self.assertGreaterEqual(zero_flex_result["blackout_mwh"], 0.0)
        self.assertTrue(audit_zonal_candidate(zero_flex, zero_flex_result)["passed"])

        infeasible = copy.deepcopy(analytical_cases()["signed-import"])
        infeasible["bids"] = []
        infeasible["real_demand_mwh"] = 0.0
        infeasible["domain_payload"]["real_demand_mwh_by_zone"] = {"gb": 0.0}
        infeasible["domain_payload"]["network_pack"]["zonal_demand"]["demand_mwh_by_zone"] = {"gb": [0.0]}
        infeasible["domain_payload"]["network_pack"]["zonal_demand"]["national_demand_mwh"] = [0.0]
        network = infeasible["domain_payload"]["network_pack"]
        network["scientific_sha256"] = ""
        import hashlib
        import json
        network["scientific_sha256"] = hashlib.sha256(json.dumps(
            network, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        with self.assertRaises(RuntimeError):
            solve_zonal_oracle(infeasible)


if __name__ == "__main__":
    unittest.main()
