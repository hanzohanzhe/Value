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

// P0-9 S4 (R3-02): stack by backend role.
import { EMPTY_DISPATCH_MESSAGES, emptyDispatchReason, isSupplyFlow, stackSupply, stackedTechnologies, stressBuckets } from "../../../app/features/market/dispatchView.ts";
import { fixture, fixtureNames } from "../helpers/fixtures.mjs";

test("v8 daily bucket stacks canonical ccgt 32 + onshore wind 8 = accepted supply 40", () => {
  const timeline = payload("toy-v8.dispatch-daily");
  const stack = Object.fromEntries(stackSupply(timeline.items[0]).map((segment) => [segment.technology, segment.energy_mwh]));
  assert.deepEqual(stack, { ccgt: 32, onshore_wind: 8 });
  assert.equal(timeline.items[0].accepted_supply_mwh, 40);
  assert.deepEqual(stackedTechnologies(timeline.items), ["ccgt", "onshore_wind"]);
  assert.equal(emptyDispatchReason(timeline, payload("toy-v8.capabilities")), null);
});

test("every dispatch fixture: the stacked supply equals accepted supply in every bucket", () => {
  for (const name of fixtureNames().filter((item) => /\.dispatch-/.test(item))) {
    for (const item of fixture(name).payload.items) {
      const stacked = stackSupply(item).reduce((sum, segment) => sum + segment.energy_mwh, 0);
      assert.ok(Math.abs(stacked - item.accepted_supply_mwh) < 1e-6, `${name} bucket ${item.period_start}: ${stacked} != ${item.accepted_supply_mwh}`);
    }
  }
});

test("v7 context flows (storage charge, curtailment, excess) are never stacked", () => {
  const timeline = payload("toy-v7.dispatch-half-hour");
  const roles = new Set(timeline.items.flatMap((item) => item.flows.map((flow) => flow.role)));
  assert.ok(roles.has("storage_charge") && roles.has("curtailment") && roles.has("excess"));
  for (const item of timeline.items) for (const flow of item.flows) assert.equal(isSupplyFlow(flow), flow.role === "supply");
});

test("an older backend without roles falls back to flow types (v7) and final-dispatch summaries (v8)", () => {
  const legacy = [
    { technology: "ccgt", flow_type: "generation", evidence_scope: "physical_asset", energy_mwh: 6, balance_component_mwh: 6 },
    { technology: "battery_storage", flow_type: "storage_charge", evidence_scope: "x", energy_mwh: 1, balance_component_mwh: -1 },
    { technology: "CCGT", flow_type: "accepted_dispatch", evidence_scope: "zone:north;stage:final_dispatch", energy_mwh: 3, balance_component_mwh: 3 },
    { technology: "CCGT", flow_type: "accepted_dispatch", evidence_scope: "zone:north;stage:ahead", energy_mwh: 9, balance_component_mwh: 9 },
  ];
  assert.deepEqual(legacy.map(isSupplyFlow), [true, false, true, false]);
});

test("an empty chart says why instead of drawing nothing", () => {
  assert.equal(emptyDispatchReason({ items: [] }, null), "no_buckets_in_window");
  const bucket = { flows: [{ technology: "ccgt", flow_type: "generation", role: "context", evidence_scope: "x", energy_mwh: 1, balance_component_mwh: 0 }] };
  assert.equal(emptyDispatchReason({ items: [bucket] }, { physical_dispatch: true }), "supply_flows_not_recorded");
  assert.equal(emptyDispatchReason({ items: [bucket] }, { physical_dispatch: false, dispatch_summary_available: false }), "dispatch_detail_not_recorded");
  assert.match(EMPTY_DISPATCH_MESSAGES.supply_flows_not_recorded, /no supply flows/);
});

test("stress bands come only from recorded stress periods", () => {
  const items = [{ stress_periods: 0 }, { stress_periods: 3, shortfall_mwh: 5 }, {}, { stress_periods: null }];
  assert.deepEqual(stressBuckets(items), [1]);
});
