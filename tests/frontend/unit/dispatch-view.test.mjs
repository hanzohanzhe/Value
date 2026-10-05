import assert from "node:assert/strict";
import test from "node:test";
import { bucketPrice } from "../../../app/features/market/dispatchView.ts";
import { payload } from "../helpers/fixtures.mjs";

// P0-9 S3 (R3-01, Q6) on the generated contract fixtures (real read models).
test("v7 default-PSM prices are an average period cost, never a clearing price", () => {
  const timeline = payload("toy-v7.dispatch-half-hour");
  assert.equal(timeline.price_basis, "average_period_cost");
  const price = bucketPrice(timeline.items[0], timeline);
  assert.equal(price.value, "£61.25/MWh");
  assert.match(price.label, /Average period cost/);
  assert.doesNotMatch(price.label, /clearing/i);
  // A legitimate 0.0 price is shown as £0/MWh, not hidden.
  assert.equal(bucketPrice(timeline.items[2], timeline).value, "£0/MWh");
});

test("v8 daily bucket shows the demand-weighted national ahead price of £55/MWh", () => {
  const timeline = payload("toy-v8.dispatch-daily");
  assert.equal(timeline.price_basis, "national_ahead_clearing_price");
  const price = bucketPrice(timeline.items[0], timeline);
  assert.equal(price.value, "£55/MWh");
  assert.equal(price.label, "Demand-weighted national ahead clearing price");
});

test("the real VALUE 101 day is labelled as an average period cost", () => {
  const timeline = payload("value-101-day.dispatch-daily");
  const price = bucketPrice(timeline.items[0], timeline);
  assert.match(price.label, /^Demand-weighted average period cost/);
  assert.notEqual(price.value, null);
});

test("a ledger without a declared basis says so and a missing price is null", () => {
  const price = bucketPrice({ price_gbp_per_mwh: null, period_count: 1 }, {});
  assert.equal(price.value, null);
  assert.equal(price.label, "Price (basis not recorded)");
});
