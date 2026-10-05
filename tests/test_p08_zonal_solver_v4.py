"""P0-8 S4: zonal solver contract v4 (shed lock, then numerical bid lock; Q5)."""

from __future__ import annotations

import copy
import unittest

from gridform_core.zonal_redispatch import (
    ZonalRedispatchBalancing,
    _run_highs,
    bid_cost_coefficients,
    build_single_period_problem,
)
from gridform_core.zonal_solver_contract import (
    DEFAULT_ZONAL_SOLVER_SETTINGS,
    SOLVER_CONTRACT_VERSION,
    SOLVER_SCHEMA_VERSION,
    V3_SOLVER_CONTRACT_VERSION,
    V3_SOLVER_SCHEMA_VERSION,
    ZonalSolverContractError,
    compute_lock_tolerance,
    gbp1_stored_policy_matches,
    solver_contract_generation,
    validate_recorded_solver_settings,
    validate_solver_settings,
)
from gridform_validation.zonal_case_generator import bind_production_input
from gridform_validation.zonal_oracle import compare_zonal_solutions, solve_zonal_oracle
from gridform_validation.zonal_case_generator import production_solution

from tests.network_toys import (
    gb_chain_declaration,
    scarce_two_zone_declaration,
    three_zone_remote_upward_declaration,
    zonal_bid,
    zonal_declaration,
)


def clear(declaration):
    model_input, module = bind_production_input(declaration)
    return module.clear(model_input)


def primary(result):
    return next(
        row for row in result.extensions["network_solver_diagnostics"]
        if row["phase_id"] == "primary_bid_cost"
    )


class ShedLockTests(unittest.TestCase):
    def test_remote_upward_energy_sheds_exactly_zero(self) -> None:
        # v3: the physical phase shed 1/(VOLL-p) MWh in the south (P2-01).
        result = clear(three_zone_remote_upward_declaration())
        self.assertEqual(result.blackout_mwh, 0.0)
        self.assertEqual(
            set(result.extensions["load_shedding_mwh_by_zone"].values()), {0.0}
        )
        self.assertEqual(result.final_dispatch_mwh_by_asset["remote"], 2.0)
        self.assertEqual(
            result.extensions["solver"]["phases"]["primary_shed_lock"]["mode"],
            "fixed_zero",
        )
        row = primary(result)
        self.assertEqual(row["validation_class"], "GO")
        self.assertLess(row["computed_tolerance"], 1e-6)

    def test_scarcity_keeps_the_primary_shed_total(self) -> None:
        result = clear(scarce_two_zone_declaration())
        self.assertAlmostEqual(result.blackout_mwh, 9.0, places=9)
        self.assertAlmostEqual(
            result.extensions["boundary_transfer_mwh_by_id"]["B_TEST"], 1.0, places=9
        )
        lock = result.extensions["solver"]["phases"]["primary_shed_lock"]
        self.assertEqual(lock["mode"], "total_cap")
        self.assertAlmostEqual(lock["rhs_mwh"], 9.0, places=9)
        self.assertEqual(primary(result)["validation_class"], "GO")

    def test_voll_changes_neither_dispatch_nor_shedding_when_not_scarce(self) -> None:
        high = clear(three_zone_remote_upward_declaration(voll=10_000.0))
        low = clear(three_zone_remote_upward_declaration(voll=1_000.0))
        self.assertEqual(high.final_dispatch_mwh_by_asset, low.final_dispatch_mwh_by_asset)
        self.assertEqual(
            high.extensions["load_shedding_mwh_by_zone"],
            low.extensions["load_shedding_mwh_by_zone"],
        )
        self.assertEqual(high.blackout_mwh, 0.0)


class BidLockTests(unittest.TestCase):
    def _near_tie(self, delta: float, *, swap: bool) -> dict[str, float]:
        names = ("a-unit", "b-unit") if not swap else ("b-unit", "a-unit")
        demand = {"gb": 100.0}
        bids = (
            zonal_bid(f"{names[0]}-up", names[0], "gb", "up", 100.0, 50.0 + delta),
            zonal_bid(f"{names[1]}-up", names[1], "gb", "up", 100.0, 50.0),
        )
        result = clear(zonal_declaration(
            demand, {names[0]: 0.0, names[1]: 0.0},
            {names[0]: "gb", names[1]: "gb"}, bids,
        ))
        return dict(result.final_dispatch_mwh_by_asset), primary(result)

    def test_near_equal_prices_shift_at_most_tolerance_over_price_gap(self) -> None:
        for delta in (1.0, 0.1, 0.01):
            for swap in (False, True):
                with self.subTest(delta=delta, swap=swap):
                    dispatch, row = self._near_tie(delta, swap=swap)
                    expensive = "a-unit" if not swap else "b-unit"
                    # v3 moved up to 1/delta MWh (100 MWh at delta=0.01).
                    self.assertLessEqual(
                        dispatch[expensive], row["computed_tolerance"] / delta + 1e-9
                    )
                    self.assertLess(dispatch[expensive], 1e-3)

    def test_equal_price_bids_share_pro_rata_across_resource_classes(self) -> None:
        demand = {"gb": 30.0}
        bids = (
            zonal_bid("gas-up", "gas", "gb", "up", 20.0, 60.0, resource_class="thermal"),
            zonal_bid("dsr-up", "dsr", "gb", "up", 40.0, 60.0, resource_class="dsr"),
        )
        declaration = zonal_declaration(
            demand, {"gas": 0.0, "dsr": 0.0}, {"gas": "gb", "dsr": "gb"}, bids,
            classes={"gas": "thermal", "dsr": "dsr"},
        )
        first = clear(declaration).final_dispatch_mwh_by_asset
        self.assertAlmostEqual(first["gas"], 10.0, places=6)
        self.assertAlmostEqual(first["dsr"], 20.0, places=6)

    def test_lock_uses_bid_terms_only_and_the_declared_solver_tolerance(self) -> None:
        declaration = gb_chain_declaration(0, scarce=True)
        model_input, module = bind_production_input(declaration)
        problem = build_single_period_problem(
            model_input,
            network_pack=module._network_pack,
            run_context_ref=module._run_context_ref,
            year_context_ref=module._year_context_ref,
            annual_metadata=module._annual_metadata,
            demand_mode=module._zonal_demand_mode,
            network_period_index=0,
        )
        values, _ = _run_highs(problem, problem.primary_objective, phase="primary")
        full = compute_lock_tolerance(problem.primary_objective, values, 1e-8, 1e-9)
        bid = compute_lock_tolerance(bid_cost_coefficients(problem), values, 1e-8, 1e-9)
        # VOLL x shed dominates the full-objective tolerance at GB scale.
        self.assertGreater(full.tolerance, 0.1)
        self.assertLess(bid.tolerance, 0.01)
        result = module.clear(model_input)
        self.assertAlmostEqual(primary(result)["computed_tolerance"], bid.tolerance, delta=1e-15)


class ZonalLockScaleTests(unittest.TestCase):
    def test_zonal_lock_scale(self) -> None:
        """23-zone GB chain: 6 scarce and 8 normal seeds; primary always GO."""

        for scarce, seeds in ((True, range(6)), (False, range(8))):
            for seed in seeds:
                with self.subTest(scarce=scarce, seed=seed):
                    result = clear(gb_chain_declaration(seed, scarce=scarce))
                    row = primary(result)
                    self.assertEqual(row["validation_class"], "GO")
                    self.assertLess(row["computed_tolerance"], 0.1)
                    self.assertLessEqual(row["degradation"], row["computed_tolerance"])
                    shedding = result.extensions["load_shedding_mwh_by_zone"]
                    if scarce:
                        self.assertGreater(result.blackout_mwh, 1_000.0)
                    else:
                        self.assertEqual(set(shedding.values()), {0.0})
                        self.assertEqual(result.blackout_mwh, 0.0)


class OracleAgreementTests(unittest.TestCase):
    def test_small_cases_match_the_exact_lock_cbc_oracle(self) -> None:
        for declaration in (
            three_zone_remote_upward_declaration(),
            scarce_two_zone_declaration(),
        ):
            production = production_solution(declaration)
            oracle = solve_zonal_oracle(declaration)
            comparison = compare_zonal_solutions(declaration, production, oracle)
            self.assertTrue(comparison["passed"], comparison)


class ContractIdentityTests(unittest.TestCase):
    def test_v4_is_the_only_executable_contract(self) -> None:
        settings = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
        self.assertEqual(settings["schema_version"], SOLVER_SCHEMA_VERSION)
        self.assertEqual(settings["contract_version"], SOLVER_CONTRACT_VERSION)
        self.assertEqual(settings["validated_ceilings"]["primary_bid_cost_gbp"], 1.0)
        self.assertEqual(ZonalRedispatchBalancing.version, "4.0.0")
        historical = dict(
            settings,
            schema_version=V3_SOLVER_SCHEMA_VERSION,
            contract_version=V3_SOLVER_CONTRACT_VERSION,
        )
        with self.assertRaises(ZonalSolverContractError) as caught:
            validate_solver_settings(historical)
        self.assertEqual(caught.exception.code, "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED")

    def test_recorded_v2_v3_v4_contracts_stay_readable(self) -> None:
        current = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
        v3 = dict(current, schema_version=V3_SOLVER_SCHEMA_VERSION,
                  contract_version=V3_SOLVER_CONTRACT_VERSION)
        v2 = dict(current, schema_version="value.network-solver-contract/v2",
                  contract_version="value.zonal-lexicographic/v2",
                  validated_ceilings={**current["validated_ceilings"], "primary_bid_cost_gbp": 0.05},
                  absolute_ceilings={**current["absolute_ceilings"], "primary_bid_cost_gbp": 0.1})
        self.assertEqual(validate_recorded_solver_settings(v3), v3)
        self.assertEqual(validate_recorded_solver_settings(v2), v2)
        self.assertEqual(validate_recorded_solver_settings(current), current)
        self.assertEqual(
            [solver_contract_generation(item) for item in (v2, v3, current, None)],
            ["v2", "v3", "v4", "unknown"],
        )
        mismatched = dict(v3, contract_version="value.zonal-lexicographic/v2")
        with self.assertRaises(ValueError):
            validate_recorded_solver_settings(mismatched)

    def test_stored_primary_policy_checks_v3_by_name_and_v4_ceilings(self) -> None:
        v3_row = {
            "solver_contract_version": V3_SOLVER_CONTRACT_VERSION,
            "phase_id": "primary_bid_cost",
            "computed_tolerance": 1.0, "validated_ceiling": 1.0, "absolute_ceiling": 1.0,
        }
        self.assertTrue(gbp1_stored_policy_matches(v3_row))
        self.assertFalse(gbp1_stored_policy_matches(dict(v3_row, computed_tolerance=1e-6)))
        v4_row = dict(v3_row, solver_contract_version=SOLVER_CONTRACT_VERSION,
                      computed_tolerance=3e-6)
        self.assertTrue(gbp1_stored_policy_matches(v4_row))
        self.assertFalse(gbp1_stored_policy_matches(dict(v4_row, validated_ceiling=0.5)))
        legacy = dict(v3_row, solver_contract_version="value.zonal-lexicographic/v2",
                      computed_tolerance=1e-8, validated_ceiling=0.05, absolute_ceiling=0.1)
        self.assertTrue(gbp1_stored_policy_matches(legacy))


if __name__ == "__main__":
    unittest.main()
