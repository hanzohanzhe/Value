import assert from "node:assert/strict";
import test from "node:test";
import {
  DISPATCH_BUCKET_KEYS, DISPATCH_TIMELINE_KEYS, MARKET_CAPABILITY_KEYS, VRE_YEAR_KEYS,
} from "../../../app/features/market/contractKeys.ts";
import { fixture, fixtureNames } from "../helpers/fixtures.mjs";

// P0-9 S2: every key the frontend types require is sent by the real read models.
// contractKeys.ts is checked by tsc to list exactly the required keys of each type.
const missing = (object, keys) => keys.filter((key) => !Object.hasOwn(object, key));

for (const name of fixtureNames()) {
  const document = fixture(name);
  const path = document.request.path;
  if (path.endsWith("/market/dispatch") || path.endsWith("/market/vre-timeline")) {
    test(`${name}: dispatch timeline and buckets carry every typed key`, () => {
      assert.deepEqual(missing(document.payload, DISPATCH_TIMELINE_KEYS), []);
      for (const item of document.payload.items) {
        assert.deepEqual(missing(item, DISPATCH_BUCKET_KEYS), [], `bucket ${item.period_start}`);
        assert.equal(Object.hasOwn(item, "clearing_price_gbp_per_mwh"), false, "R3-01: the bucket price key is price_gbp_per_mwh");
      }
    });
  } else if (path.endsWith("/market/capabilities")) {
    test(`${name}: capabilities carry every typed key and a price basis`, () => {
      assert.deepEqual(missing(document.payload, MARKET_CAPABILITY_KEYS), []);
      assert.ok(document.payload.price_basis);
    });
  } else if (path.endsWith("/market/vre-summary")) {
    test(`${name}: VRE years carry every typed key`, () => {
      for (const year of document.payload.years) assert.deepEqual(missing(year, VRE_YEAR_KEYS), []);
    });
  }
}
