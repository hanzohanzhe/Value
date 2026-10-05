import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

// Source guards for the P0 frontend rules (spec 1.2, 1.3, 9; plan P0-9 S1).
const root = path.resolve(import.meta.dirname, "../../..");

async function sources(directory = path.join(root, "app"), pattern = /\.(tsx?|mjs)$/) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) found.push(...await sources(full, pattern));
    else if (pattern.test(entry.name)) found.push(full);
  }
  return found;
}

async function lines() {
  const result = [];
  for (const file of await sources()) {
    const relative = path.relative(root, file).split(path.sep).join("/");
    (await readFile(file, "utf8")).split("\n").forEach((text, index) => result.push({ file: relative, line: index + 1, text }));
  }
  return result;
}

const where = (hits) => hits.map(({ file, line, text }) => `${file}:${line}: ${text.trim().slice(0, 160)}`).join("\n");

test("no formatting call turns a missing value into 0 with ?? 0", async () => {
  // format*( … ?? 0) or format*( … ?? 0, digits): a missing value would be shown as a real 0.
  const call = /\bformat[A-Za-z]*\((?:[^()]|\([^()]*\))*\?\?\s*0\s*[),]/;
  const hits = (await lines()).filter(({ text }) => call.test(text));
  assert.deepEqual(hits, [], where(hits));
});

test("no energy is hard-wired to TWh by dividing by 1e6", async () => {
  const hits = (await lines()).filter(({ text }) => /\/\s*1e6/.test(text) && /TWh/.test(text));
  assert.deepEqual(hits, [], where(hits));
});

test("Intl.NumberFormat lives only in the shared formatting layer", async () => {
  const hits = (await lines()).filter(({ file, text }) => /Intl\.NumberFormat/.test(text) && file !== "app/features/shared/format.ts");
  assert.deepEqual(hits, [], where(hits));
});

test("toLocaleString is used only for whole-number counts in the allow-list", async () => {
  // Integer period counts; they cannot hide a missing value as 0.
  const allowed = new Set(["app/features/workspace/RunContextBar.tsx", "app/features/learn/Value101Learn.tsx"]);
  const hits = (await lines()).filter(({ file, text }) => /toLocaleString\(/.test(text) && !allowed.has(file));
  assert.deepEqual(hits, [], where(hits));
});

test("the frontend never derives a shortfall by subtracting supply from demand", async () => {
  // Spec 3.1 / 9.9: shortfall_mwh comes from the backend; missing is "Not recorded".
  const subtraction = /real_demand_mwh\s*-\s*[\w.?]*accepted_supply_mwh|accepted_supply_mwh\s*-\s*[\w.?]*real_demand_mwh/;
  const hits = (await lines()).filter(({ text }) => subtraction.test(text));
  assert.deepEqual(hits, [], where(hits));
});

test("spec 9.1 phrases are gone from the result views", async () => {
  // "valid single-node" (R3-16), a bare "Clearing price" label (R3-01/Q6), "Result invalid" for missing evidence (G1-07).
  const forbidden = /valid single-node|["'>]Clearing price|Result invalid|Compact annual read model/;
  const hits = (await lines()).filter(({ text }) => forbidden.test(text));
  assert.deepEqual(hits, [], where(hits));
});

test("FORBIDDEN_PUBLIC_AC: no public AC domain label", async () => {
  const { DOMAIN_LABELS, PUBLIC_CAPABILITY_DOMAINS } = await import("../../../app/features/shared/domainConstants.ts");
  assert.equal(Object.keys(DOMAIN_LABELS).some((key) => /(^|_)ac(_|$)/.test(key)), false);
  assert.equal(PUBLIC_CAPABILITY_DOMAINS.some((key) => /(^|_)ac(_|$)/.test(key)), false);
});

// Stylesheets added in this round (spec 1.3): no text below 12px, no new colours.
export const NEW_STYLESHEETS = [
  "app/features/shared/callout.css",
  "app/features/market/market-replay.css",
  "app/features/network/network-coverage.css",
  "app/features/runs/run-results.css",
  "app/features/shared/service-status.css",
  "app/features/modules/module-quarantine.css",
];

test("new stylesheets use no font size below 12px and only existing colour tokens", async () => {
  for (const relative of NEW_STYLESHEETS) {
    const css = await readFile(path.join(root, relative), "utf8");
    for (const match of css.matchAll(/font-size:\s*([\d.]+)px/g)) {
      assert.ok(Number(match[1]) >= 12, `${relative}: font-size ${match[1]}px is below 12px`);
    }
    const literal = css.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(/g) ?? [];
    assert.deepEqual(literal, [], `${relative}: colours must come from :root tokens`);
  }
});
