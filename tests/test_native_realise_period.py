"""P0-6 S3: realise_period refactor and the corrected node identity (C19)."""

from __future__ import annotations

import unittest
from unittest import mock

from gridform_core import energy_balance_contract as contract
from gridform_core.builtin.scheme_c_1000twh.native_realisation import (
    BALANCING_BRANCH,
    CURTAILMENT_BRANCH,
    RealisationLog,
    active_realisation_log,
)

from tests import native_reproduction_harness as harness


class CorrectedNodeIdentityTests(unittest.TestCase):
    """Hand calculations of native_corrected_full_node_v1 (plan P0-6 S3 tests)."""

    def test_export_consumes_vre_surplus(self):
        # Wind available 100: 50 accepted for demand 50, 20 of the surplus is
        # exported, 30 curtailed.  Gross wind output is 70.
        flows = contract.native_node_flows(
            2030, 0, gross_generation_mwh=70.0, import_mwh=0.0, storage_discharge_mwh=0.0,
            shortfall_mwh=0.0, demand_mwh=50.0, storage_charge_mwh=0.0, export_mwh=20.0,
            flexible_demand_mwh=0.0, non_vre_spill_mwh=0.0,
        )
        self.assertEqual(contract.boundary_residual(contract.NATIVE_CORRECTED_FULL_NODE_V1, flows), 0.0)
        self.assertEqual(contract.vre_source_residual(100.0, 50.0, 20.0, 30.0), 0.0)
        # The doctoral ledger records only the accepted 50 (VRE surplus outside
        # S): under the corrected identity the exported 20 has no source.
        doctoral_style = contract.native_node_flows(
            2030, 0, gross_generation_mwh=50.0, import_mwh=0.0, storage_discharge_mwh=0.0,
            shortfall_mwh=0.0, demand_mwh=50.0, storage_charge_mwh=0.0, export_mwh=20.0,
            flexible_demand_mwh=0.0, non_vre_spill_mwh=0.0,
        )
        self.assertEqual(contract.native_corrected_residual(doctoral_style), -20.0)

    def test_nuclear_spill(self):
        # Nuclear must run at 140 for demand 90: 50 is generated and spilled.
        flows = contract.native_node_flows(
            2030, 1, gross_generation_mwh=140.0, import_mwh=0.0, storage_discharge_mwh=0.0,
            shortfall_mwh=0.0, demand_mwh=90.0, storage_charge_mwh=0.0, export_mwh=0.0,
            flexible_demand_mwh=0.0, non_vre_spill_mwh=50.0,
        )
        self.assertEqual(contract.native_corrected_residual(flows), 0.0)
        self.assertEqual(contract.full_node_residual(flows), 50.0)
        self.assertEqual(
            contract.envelope_bounds(contract.NATIVE_CORRECTED_FULL_NODE_V1, flows), (50.0, 50.0)
        )
        self.assertFalse(
            contract.check_envelope(contract.NATIVE_CORRECTED_FULL_NODE_V1, flows, contract.EXACT_ARITHMETIC).violated
        )

    def test_charge_by_source(self):
        # Demand 50 served by nuclear 30 + wind 20; wind available 50, so 30
        # wind surplus: 25 charges storage, 5 is curtailed.  A second store
        # discharges 10 for an import-free period with 10 exported.
        flows = contract.native_node_flows(
            2030, 2, gross_generation_mwh=30.0 + 45.0, import_mwh=0.0, storage_discharge_mwh=10.0,
            shortfall_mwh=0.0, demand_mwh=50.0, storage_charge_mwh=25.0, export_mwh=10.0,
            flexible_demand_mwh=0.0, non_vre_spill_mwh=0.0,
        )
        self.assertEqual(contract.native_corrected_residual(flows), 0.0)
        self.assertEqual(contract.vre_source_residual(50.0, 20.0, 25.0, 5.0), 0.0)
        # Shortfall closes the node from the supply side.
        short = contract.native_node_flows(
            2030, 3, gross_generation_mwh=40.0, import_mwh=5.0, storage_discharge_mwh=0.0,
            shortfall_mwh=5.0, demand_mwh=50.0, storage_charge_mwh=0.0, export_mwh=0.0,
            flexible_demand_mwh=0.0, non_vre_spill_mwh=0.0,
        )
        self.assertEqual(contract.native_corrected_residual(short), 0.0)

    def test_registry_keys_the_corrected_boundary_by_rule_set(self):
        from gridform_core.builtin.scheme_c_1000twh.native_market_rules import CORRECTED

        entry = contract.registry_lookup("value-bid-at-cost-psm", "6.0.0", CORRECTED.rule_set_id)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.boundary_id, contract.NATIVE_CORRECTED_FULL_NODE_V1)
        self.assertIsNone(contract.registry_lookup("value-bid-at-cost-psm", "5.1.0", CORRECTED.rule_set_id))
        doctoral = contract.registry_lookup("value-bid-at-cost-psm", "5.1.0", None)
        self.assertEqual(doctoral.boundary_id, contract.DEFAULT_PSM_SURPLUS_NODE_V1)
        self.assertTrue(contract.BOUNDARIES[contract.NATIVE_CORRECTED_FULL_NODE_V1].verdict_basis)


class RealisePeriodTests(unittest.TestCase):
    def test_live_loop_realises_every_period_once_and_logs_the_flows(self):
        kernel = harness.kernel_module()
        original = kernel.realise_period
        calls = []

        def spy(*arguments, **keywords):
            result = original(*arguments, **keywords)
            calls.append((arguments[0], result.branch, arguments[-1]))
            return result

        log = RealisationLog()
        scenario = harness.build_scenario()
        with mock.patch.object(kernel, "realise_period", spy):
            run = harness.run_case("dynamic", scenario, loop="live", runtime_attributes={"realisation_log": log})
        raw = run["raw"]
        self.assertEqual([period for period, _, _ in calls], list(range(harness.PERIODS)))
        # Doctoral rules reach realise_period (harness default runtime).
        from gridform_core.builtin.scheme_c_1000twh.native_market_rules import DOCTORAL

        self.assertTrue(all(rules is DOCTORAL for _, _, rules in calls))
        self.assertTrue(log.recorded.all())
        for period in range(harness.PERIODS):
            expected = (
                CURTAILMENT_BRANCH if scenario["real_mw"][period] < scenario["forecast_mw"][period]
                else BALANCING_BRANCH
            )
            self.assertEqual(int(log.branch[period]), expected, period)
            self.assertEqual(calls[period][1], expected)
            self.assertEqual(log.storage_charge_mw[period], float(raw["store_electricity"][period] or 0.0))
            self.assertEqual(log.curtailed_mw[period], float(raw["curtailed_electricity"][period] or 0.0))
            self.assertEqual(log.excess_mw[period], float(raw["excess_electricity"][period] or 0.0))
            self.assertEqual(log.blackout_mw[period], float(raw["blackout_periods"][period] or 0.0))
            self.assertEqual(log.real_demand_mw[period], float(scenario["real_mw"][period]))
        self.assertIn(CURTAILMENT_BRANCH, set(log.branch.tolist()))
        self.assertIn(BALANCING_BRANCH, set(log.branch.tolist()))
        # HEAD types survive the refactor: the curtailment branch appends int 0.
        for period in range(harness.PERIODS):
            if log.branch[period] == CURTAILMENT_BRANCH:
                self.assertIs(type(raw["blackout_periods"][period]), int)
                self.assertIs(type(raw["purchase_fees"][period]), int)
            else:
                self.assertIs(type(raw["curtailed_electricity"][period]), int)
        # The log holds no object references.
        for value in log.as_dict().values():
            self.assertTrue(all(isinstance(item, (int, float)) for item in value))

    def test_active_realisation_log(self):
        from types import SimpleNamespace

        private = active_realisation_log(None, 3)
        self.assertEqual(private.periods, 3)
        shared = RealisationLog(1)
        self.assertIs(active_realisation_log(SimpleNamespace(realisation_log=shared), 4), shared)
        self.assertEqual(shared.periods, 4)
        self.assertFalse(shared.recorded.any())
        self.assertIsNot(active_realisation_log(SimpleNamespace(storage_cost=None), 2), shared)
        with self.assertRaises(TypeError):
            active_realisation_log(SimpleNamespace(realisation_log=[]), 2)


if __name__ == "__main__":
    unittest.main()
