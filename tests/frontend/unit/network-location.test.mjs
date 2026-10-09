import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { DEFAULT_NETWORK_LOCATION, networkQueryValues, networkYear, readNetworkLocation } from "../../../app/features/network/networkLocation.ts";

// W6 (P1 spec 0.3, 5.1): the network page keeps its model year, tab and period
// window in the URL, so a reload, a copied link or Back opens the same view.

test("a network URL names the year, tab, first period and window", () => {
  assert.deepEqual(readNetworkLocation("?year=2026&tab=reliability&from=96&window=336"), { year: 2026, tab: "reliability", from: 96, window: 336 });
});

test("a URL without page state opens the defaults", () => {
  assert.deepEqual(readNetworkLocation(""), DEFAULT_NETWORK_LOCATION);
  assert.deepEqual(readNetworkLocation("?study=s&run=r"), DEFAULT_NETWORK_LOCATION);
});

test("unknown or malformed values fall back to the defaults", () => {
  assert.deepEqual(readNetworkLocation("?year=20x6&tab=settlement&from=-4&window=100"), DEFAULT_NETWORK_LOCATION);
  assert.equal(readNetworkLocation("?year=12345").year, null);
  assert.equal(readNetworkLocation("?from=1234567").from, 0);
});

test("the linked year is used only when the Run has it; otherwise the first published year", () => {
  assert.equal(networkYear([2025, 2026], 2026, 2025), 2026);
  assert.equal(networkYear([2025], 2026, 2025), 2025);
  assert.equal(networkYear([2025, 2026], null, 2025), 2025);
  assert.equal(networkYear([], 2026, null), null);
});

test("defaults are left out of the URL; the year is always written", () => {
  assert.deepEqual(networkQueryValues({ year: 2025, tab: "overview", from: 0, window: 48 }), { year: 2025, tab: null, from: null, window: null });
  assert.deepEqual(networkQueryValues({ year: 2026, tab: "evidence", from: 336, window: 336 }), { year: 2026, tab: "evidence", from: 336, window: 336 });
});

test("written values read back as the same view", () => {
  const state = { year: 2026, tab: "period", from: 48, window: 336 };
  const query = new URLSearchParams(Object.entries(networkQueryValues(state)).filter(([, value]) => value != null).map(([key, value]) => [key, String(value)]));
  assert.deepEqual(readNetworkLocation(`?${query}`), state);
});

test("the network route reads the URL once and the page writes its state back (source wiring)", async () => {
  const route = await readFile(new URL("../../../app/runs/[runId]/network/NetworkView.tsx", import.meta.url), "utf8");
  assert.match(route, /useState\(\(\) => readNetworkLocation\(search\)\)/);
  assert.match(route, /linked=\{linked\} onLocationChange=\{writeLocation\}/);
  assert.match(route, /replacePageQuery\(values\)/);
  const view = await readFile(new URL("../../../app/features/network/NetworkRedispatchView.tsx", import.meta.url), "utf8");
  assert.match(view, /useState<Tab>\(linked\.tab\)/);
  assert.match(view, /onLocationChange\?\.\(networkQueryValues\(\{ year, tab, from: periodFrom, window: periodWindow \}\)\)/);
});
