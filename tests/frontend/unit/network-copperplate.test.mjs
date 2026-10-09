import assert from "node:assert/strict";
import test from "node:test";
import { copperplateBalancing, zonalLedgerRecorded } from "../../../app/features/network/networkRedispatch.ts";

// R-D5 (four-role report, round R1-5): a Run that cleared one national market
// is copperplate whether or not it named the copperplate module, and a ledger
// with zonal tables but no zonal rows is not "pending" network evidence.
test("copperplate kind: the built-in module, a Run without a balancing module, or not copperplate", () => {
  assert.equal(copperplateBalancing({ psm: "value-bid-at-cost-psm", balancing: "value-copperplate-balancing" }), "module");
  assert.equal(copperplateBalancing({ psm: "value-bid-at-cost-psm", storage_cost: "value-legacy-storage-tariff" }), "national");
  assert.equal(copperplateBalancing({ psm: "value-bid-at-cost-psm", balancing: "value-zonal-redispatch-balancing" }), null);
  assert.equal(copperplateBalancing({ balancing: "external-unknown-balancing" }), null);
  assert.equal(copperplateBalancing(undefined), null, "an unrecorded module set is not assumed copperplate");
});

test("a zonal ledger is recorded only with years or zonal rows", () => {
  const empty = { years: [], row_counts: { zonal_period_summary: 0, reliability_event: 0 } };
  assert.equal(zonalLedgerRecorded(empty), false);
  assert.equal(zonalLedgerRecorded({ years: [2025], row_counts: {} }), true);
  assert.equal(zonalLedgerRecorded({ years: [], row_counts: { zonal_period_summary: 2 } }), true);
});
