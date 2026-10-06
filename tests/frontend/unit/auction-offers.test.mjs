import assert from "node:assert/strict";
import test from "node:test";
import { STORAGE_LEDGER_GRANULARITY, acceptedCell, storageLedgerNote } from "../../../app/features/market/auctionOffers.ts";

// Spec 3.4 / four-role M-D1: each storage offer shows its own accepted MWh from the storage offer ledger.
const base = { asset_id: "battery-a", technology: "battery storage", offer_price_gbp_per_mwh: 18.5, offered_mwh: 1.25, execution_order: 0, cumulative_offered_mwh: 1.25 };
const tranche = (accepted, status, reason) => ({ ...base, accepted_mwh: accepted, asset_accepted_mwh: 2.5, acceptance_granularity: STORAGE_LEDGER_GRANULARITY, offer_status: status, offer_reason_code: reason });

test("a battery tranche shows its own ledger MWh, not the asset total, with the ledger status on hover", () => {
  assert.deepEqual(acceptedCell(tranche(0.75, "accepted", "cleared")), { mwh: 0.75, suffix: "", title: "Storage offer ledger: accepted (cleared)" });
  assert.deepEqual(acceptedCell(tranche(0, "rejected", "merit_order_not_reached")), { mwh: 0, suffix: "", title: "Storage offer ledger: rejected (merit order not reached)" });
});

test("without the ledger the old evidence rules stay: exact single offer, asset total, or not recorded", () => {
  assert.deepEqual(acceptedCell({ ...base, accepted_mwh: 4, asset_accepted_mwh: 4, acceptance_granularity: "offer" }), { mwh: 4, suffix: "" });
  assert.deepEqual(acceptedCell({ ...base, accepted_mwh: null, asset_accepted_mwh: 2.5, acceptance_granularity: "asset_aggregate" }), { mwh: 2.5, suffix: " (asset total)" });
  assert.deepEqual(acceptedCell({ ...base, accepted_mwh: null, asset_accepted_mwh: null, acceptance_granularity: "stage_summary" }), { mwh: null, suffix: "" });
});

test("the gross-acceptance note appears only when a storage offer reads the ledger", () => {
  assert.match(storageLedgerNote([tranche(0.75, "accepted", "cleared")]), /storage offer ledger, gross/);
  assert.equal(storageLedgerNote([{ ...base, accepted_mwh: 4, asset_accepted_mwh: 4, acceptance_granularity: "offer" }]), null);
});
