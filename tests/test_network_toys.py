"""P0-8 S1: the shared network fixtures and the bound oracle adapter."""

from __future__ import annotations

import unittest

from gridform_core.staged_market_contracts import ZonalRedispatchDomainV2
from gridform_core.zonal_contracts import (
    ETYSBoundary,
    NetworkZone,
    TransportCorridor,
)
from gridform_core.zonal_redispatch import _run_highs, build_single_period_problem
from gridform_validation.zonal_case_generator import (
    bind_production_input,
    production_solution,
)
from gridform_validation.zonal_oracle import solve_zonal_oracle

from tests.network_toys import (
    GB_CHAIN_ZONES,
    eleven_zone_topology,
    gb_chain_declaration,
    three_bus_dc_case,
    two_zone_declaration,
)


def primary_shed_mwh(declaration: dict[str, object]) -> float:
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
    return float(sum(values[index] for index in problem.shedding_index.values()))


class NetworkToyFixtureTests(unittest.TestCase):
    def test_oracle_declarations_bind_to_the_v2_production_contexts(self) -> None:
        declaration = two_zone_declaration()
        model_input, module = bind_production_input(declaration)
        domain = ZonalRedispatchDomainV2.from_dict(model_input.domain_payload)
        self.assertEqual(domain.period_slice.period_id, "p0")
        self.assertEqual(module._zonal_demand_mode, "network_pack_absolute_demand")
        production = production_solution(declaration)
        oracle = solve_zonal_oracle(declaration)
        self.assertAlmostEqual(
            sum(production["final_dispatch_mwh_by_asset"].values()),
            sum(oracle["final_dispatch_mwh_by_asset"].values()),
            places=6,
        )

    def test_gb_chain_is_deterministic_23_zone_and_scarce_only_when_asked(self) -> None:
        first = gb_chain_declaration(3, scarce=True)
        self.assertEqual(first, gb_chain_declaration(3, scarce=True))
        pack = first["domain_payload"]["network_pack"]
        self.assertEqual(
            tuple(zone["zone_id"] for zone in pack["zones"]), GB_CHAIN_ZONES
        )
        self.assertEqual(len(pack["corridors"]), 22)
        self.assertGreater(first["real_demand_mwh"], 14_000.0)
        for seed in range(3):
            with self.subTest(seed=seed):
                self.assertEqual(
                    primary_shed_mwh(gb_chain_declaration(seed, scarce=False)), 0.0
                )
                self.assertGreater(
                    primary_shed_mwh(gb_chain_declaration(seed, scarce=True)), 1_000.0
                )

    def test_eleven_zone_copy_and_three_bus_case_are_well_formed(self) -> None:
        topology = eleven_zone_topology()
        zones = [NetworkZone.from_dict(item) for item in topology["zones"]]
        corridors = [TransportCorridor.from_dict(item) for item in topology["corridors"]]
        cutsets = [ETYSBoundary.from_dict(item) for item in topology["cutsets"]]
        self.assertEqual(len(zones), 11)
        self.assertEqual(len(corridors), 14)
        self.assertEqual(len(cutsets), 17)
        declared = [
            row for row in topology["cutsets"] if "positive_side_zone_ids" in row
        ]
        self.assertEqual(len(declared), 8)
        network, _wrapped = three_bus_dc_case(split=False)
        network.validate()


if __name__ == "__main__":
    unittest.main()
