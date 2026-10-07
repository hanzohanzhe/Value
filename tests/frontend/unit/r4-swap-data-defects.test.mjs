import assert from "node:assert/strict";
import test from "node:test";
import { MODEL_CLOCK_LABEL, modelClockSuffix, modelTimeText, modelTimestamp } from "../../../app/features/shared/modelClock.ts";
import { modelTimestamp as reliabilityTimestamp } from "../../../app/features/network/reliabilityView.ts";
import { stressEventRow } from "../../../app/features/market/stressEventsView.ts";

// R4 (DECISIONS A27), four-role report S-中1: model times are UTC on a fixed
// 365-day year, labelled "UTC model time" (gridform_core/model_clock.py).
test("model clock: UTC, 365-day year, no 29 February", () => {
  assert.equal(modelTimestamp(2025, 8720), "2025-07-01 16:00");
  assert.equal(modelTimestamp(2028, 59 * 48), "2028-03-01 00:00");
  assert.equal(modelTimestamp(2028, 17_519), "2028-12-31 23:30");
  assert.equal(modelTimestamp(2025, 25, 1), "2025-01-02 01:00");
  // One rule: the network and stress lists use the same function.
  assert.equal(reliabilityTimestamp, modelTimestamp);
  assert.equal(stressEventRow({ year: 2028, event_index: 1, start_period: 59 * 48, last_period: 59 * 48, periods: 1, shortfall_mwh: 1 }).start, "2028-03-01 00:00");
});

test("model clock labels and backend timestamps", () => {
  assert.equal(MODEL_CLOCK_LABEL, "UTC model time");
  assert.equal(modelClockSuffix("UTC"), " (UTC model time)");
  assert.equal(modelClockSuffix(""), "");
  assert.equal(modelClockSuffix(undefined), "");
  assert.equal(modelTimeText("2025-07-01T16:00:00Z"), "2025-07-01 16:00");
  assert.equal(modelTimeText("2025-07-01T16:00:00"), "2025-07-01 16:00");
  assert.equal(modelTimeText(null), "");
});
