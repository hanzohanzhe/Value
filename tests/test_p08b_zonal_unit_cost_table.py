"""P0-8 S8: the zonal problem/result split and the explicit unit-cost table.

The table changes costs only when it is declared; without it the period slice
serialises exactly as before (contract hashes unchanged).
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from gridform_core.staged_market_contracts import (
    ZonalRedispatchDomainV2,
    ZonalRedispatchPeriodSlice,
    contract_sha256,
)
from gridform_core.zonal_redispatch import ZonalRedispatchInputError
from gridform_validation.zonal_case_generator import bind_production_input
from tests.network_toys import zonal_bid, zonal_declaration


def gas_up_declaration() -> dict[str, object]:
    bids = (zonal_bid("gas-up", "gas", "gb", "up", 50.0, 60.0, baseline_mwh=100.0),)
    return zonal_declaration(
        {"gb": 120.0}, {"gas": 100.0}, {"gas": "gb"}, bids, availability_mwh={"gas": 150.0},
    )


def with_table(model_input, table):
    domain = ZonalRedispatchDomainV2.from_dict(model_input.domain_payload)
    slice_ = replace(domain.period_slice, resource_cost_gbp_per_mwh_by_asset=table)
    return replace(model_input, domain_payload=replace(domain, period_slice=slice_).to_dict())


class UnitCostTableTests(unittest.TestCase):
    def test_absent_table_is_not_serialised(self) -> None:
        model_input, _module = bind_production_input(gas_up_declaration())
        domain = ZonalRedispatchDomainV2.from_dict(model_input.domain_payload)
        self.assertIsNone(domain.period_slice.resource_cost_gbp_per_mwh_by_asset)
        self.assertNotIn("resource_cost_gbp_per_mwh_by_asset", domain.to_dict()["period_slice"])
        self.assertEqual(domain.to_dict(), dict(model_input.domain_payload))
        self.assertEqual(
            contract_sha256(domain.period_slice),
            contract_sha256(ZonalRedispatchPeriodSlice.from_dict(domain.period_slice.to_dict())),
        )

    def test_declared_table_is_the_only_cost_source(self) -> None:
        model_input, module = bind_production_input(gas_up_declaration())
        baseline = module.clear(model_input)
        self.assertAlmostEqual(baseline.resource_cost_gbp_by_class["thermal"], 120.0 * 60.0)

        model_input, module = bind_production_input(gas_up_declaration())
        priced = module.clear(with_table(model_input, {"gas": 70.0}))
        self.assertEqual(priced.final_dispatch_mwh_by_asset, baseline.final_dispatch_mwh_by_asset)
        self.assertAlmostEqual(priced.resource_cost_gbp_by_class["thermal"], 120.0 * 70.0)

    def test_table_must_cover_every_asset(self) -> None:
        model_input, module = bind_production_input(gas_up_declaration())
        with self.assertRaises(ZonalRedispatchInputError):
            module.clear(with_table(model_input, {"other": 1.0}))


if __name__ == "__main__":
    unittest.main()
