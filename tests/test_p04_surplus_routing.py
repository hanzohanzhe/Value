"""P0-4 S5: source-classified surplus routing terms of the default PSM (Q7)."""

from __future__ import annotations

import unittest

from gridform_core import energy_balance_contract as contract
from gridform_core.builtin.scheme_c_1000twh import native_balance_audit as audit
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel


class SurplusTraceTests(unittest.TestCase):
    def test_source_class_of_the_ahead_excess(self):
        nuclear = kernel.NuclearGenerator.__new__(kernel.NuclearGenerator)
        wind = kernel.ExpensiverenewableGenerator.__new__(kernel.ExpensiverenewableGenerator)
        classify = lambda items: audit.excess_source_class(items, kernel.NuclearGenerator, kernel.ExpensiverenewableGenerator)
        self.assertEqual(classify([[nuclear, 2.0]]), ("in_dispatch", ("in_dispatch",)))
        self.assertEqual(classify([[wind, 2.0], [wind, 1.0]]), ("out_of_dispatch", ("out_of_dispatch",)))
        self.assertEqual(classify([]), (None, ()))

    def test_vre_excess_routed_to_storage_is_u_out(self):
        trace = audit.SurplusTrace()
        trace.begin(0, 10.0, "out_of_dispatch")         # 10 MW VRE not accepted
        trace.excess("to_storage", 10.0, 6.0)            # 4 MW charge
        trace.add("out_of_dispatch", "claimed_spill", 6.0)
        # S = D = 20 MWh, C = 2 MWh: full node -2, U_out +2 -> 0.
        terms, rows = audit.node_terms(trace, 0.5, supply_mwh=20.0, blackout_mwh=0.0, demand_mwh=20.0, loads_mwh=2.0)
        self.assertEqual((terms.u_out_mwh, terms.w_in_mwh), (2.0, 0.0))
        (row,) = rows
        self.assertEqual(row["source_class"], "out_of_dispatch")
        self.assertEqual((row["available_mwh"], row["to_storage_mwh"], row["spilled_mwh"]), (5.0, 2.0, 3.0))
        routed = contract.SurplusRoutingRow(0, 0, row["source_class"], *(row[key] for key in (
            "available_mwh", "to_storage_mwh", "to_export_mwh", "to_flexible_mwh", "spilled_mwh",
            "to_dispatch_mwh", "curtailed_mwh", "unrealised_mwh")))
        self.assertEqual(routed.conservation_gap_mwh(), 0.0)

    def test_claimed_in_dispatch_spill_is_capped_by_the_unused_supply(self):
        # Curtailment branch, F - R = 10 MW claimed surplus; storage takes 2 MW,
        # down-regulation is booked for 8 MW but only 3 MW leave S.
        trace = audit.SurplusTrace()
        trace.begin(0, 0.0, None)
        trace.add("in_dispatch", "available", 10.0)
        trace.add("in_dispatch", "to_storage", 2.0)
        trace.add("in_dispatch", "curtailed", 3.0)
        trace.add("in_dispatch", "claimed_spill", 5.0)
        # (a) must-run output really stayed in S: S = D + C + 2.5 MWh unused.
        terms, (row,) = audit.node_terms(trace, 0.5, supply_mwh=23.5, blackout_mwh=0.0, demand_mwh=20.0, loads_mwh=1.0)
        self.assertEqual((terms.w_in_mwh, row["spilled_mwh"], row["unrealised_mwh"]), (2.5, 2.5, 0.0))
        # (b) the surplus never existed (ahead shortage, P3-01): nothing is
        # spilled, the claim is unrealised and the residual stays negative.
        terms, (row,) = audit.node_terms(trace, 0.5, supply_mwh=15.0, blackout_mwh=0.0, demand_mwh=20.0, loads_mwh=1.0)
        self.assertEqual((terms.w_in_mwh, row["unrealised_mwh"]), (0.0, 2.5))
        flows = contract.PeriodFlows(0, 0, 15.0, 0.0, 20.0, 1.0, 0.0, 0.0, u_out_mwh=terms.u_out_mwh, w_in_mwh=terms.w_in_mwh)
        self.assertEqual(contract.surplus_node_residual(flows), -6.0)
        self.assertEqual(contract.period_shortfall(flows).shortfall_mwh, 6.0)
        routed = contract.SurplusRoutingRow(0, 0, "in_dispatch", *(row[key] for key in (
            "available_mwh", "to_storage_mwh", "to_export_mwh", "to_flexible_mwh", "spilled_mwh",
            "to_dispatch_mwh", "curtailed_mwh", "unrealised_mwh")))
        self.assertEqual(routed.conservation_gap_mwh(), 0.0)

    def test_in_dispatch_redispatch_is_not_a_double_count(self):
        # R4-1 (A26, DEV-BAL-04): in-dispatch surplus re-dispatched to the
        # balancing requirement is output already in S; the kernel no longer
        # adds it again, so the double-count column records only what the
        # trace says was counted twice (nothing).  Before R4-1 this toy
        # (pack_nucbal) reported 3.0 MWh.
        trace = audit.SurplusTrace()
        trace.begin(0, 7.342, "in_dispatch")
        trace.excess("to_dispatch", 7.342, 1.342)
        trace.add("in_dispatch", "to_storage", 1.342)
        terms, rows = audit.node_terms(trace, 0.5, supply_mwh=14.5, blackout_mwh=0.0, demand_mwh=13.829, loads_mwh=0.671)
        self.assertEqual(terms.non_vre_double_counted_mwh, 0.0)
        self.assertEqual(terms.w_in_mwh, 0.0)
        self.assertAlmostEqual(rows[0]["to_dispatch_mwh"], 3.0, places=12)
        trace.double_counted_mw = 6.0
        terms, _ = audit.node_terms(trace, 0.5, supply_mwh=17.5, blackout_mwh=0.0, demand_mwh=13.829, loads_mwh=0.671)
        self.assertEqual(terms.non_vre_double_counted_mwh, 3.0)

    def test_routing_rows_without_new_columns_still_conserve(self):
        legacy = contract.SurplusRoutingRow(2025, 0, "in_dispatch", 1.0, 0.4, 0.0, 0.0, 0.6)
        self.assertEqual(legacy.conservation_gap_mwh(), 0.0)
        self.assertEqual(contract.surplus_terms([legacy]), (0.0, 0.6))


if __name__ == "__main__":
    unittest.main()
