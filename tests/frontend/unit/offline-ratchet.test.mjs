import assert from "node:assert/strict";
import test from "node:test";
import { describeEvaluation, evaluateOffline, flattenReport } from "../../../e2e/offline-ratchet.mjs";

const result = (status, messages = []) => ({ status, errors: messages.map((message) => ({ message })) });
const spec = (file, title, status, messages = [], project = "desktop-chromium") => ({
  title, file, tests: [{ projectName: project, status: status === "passed" ? "expected" : status === "skipped" ? "skipped" : "unexpected", results: [result(status, messages)] }],
});
const report = (specs) => ({ suites: [{ title: "a.spec.ts", file: "a.spec.ts", specs: specs.filter((s) => s.file === "a.spec.ts"), suites: [
  { title: "group", file: "a.spec.ts", specs: [], suites: [] },
] }, { title: "b.spec.ts", file: "b.spec.ts", specs: specs.filter((s) => s.file === "b.spec.ts") }] });
const subset = {
  specs: ["e2e/a.spec.ts", "e2e/b.spec.ts"],
  min_passed: { "e2e/a.spec.ts": 1 },
  known_failures: [{ id: "b.spec.ts > known bad", reason: "r", owner: "o" }],
};

test("flattenReport keys tests by file and title path, not by line", () => {
  const rows = flattenReport({ suites: [{ title: "a.spec.ts", file: "a.spec.ts", specs: [], suites: [{ title: "group", file: "a.spec.ts", specs: [spec("a.spec.ts", "inner", "passed")], suites: [] }] }] });
  assert.deepEqual(rows.map((row) => [row.id, row.status]), [["a.spec.ts > group > inner", "passed"]]);
});

test("registered failures with everything else passing is the accepted state", () => {
  const outcome = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("b.spec.ts", "known bad", "failed"), spec("b.spec.ts", "fine", "passed")]), subset);
  assert.equal(outcome.ok, true);
  assert.deepEqual(outcome.totals, { passed: 2, failed: 1, skipped: 0, known_failures: 1 });
});

test("an unregistered failure fails the ratchet", () => {
  const outcome = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("a.spec.ts", "new break", "failed"), spec("b.spec.ts", "known bad", "failed")]), subset);
  assert.equal(outcome.ok, false);
  assert.deepEqual(outcome.newFailures, ["a.spec.ts > new break"]);
  assert.match(describeEvaluation(outcome), /NEW FAILURE a\.spec\.ts > new break/);
});

test("a registered failure that passes again must be removed from the registry", () => {
  const outcome = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("b.spec.ts", "known bad", "passed")]), subset);
  assert.equal(outcome.ok, false);
  assert.deepEqual(outcome.fixedButListed, ["b.spec.ts > known bad"]);
});

test("a spec that produced nothing, a vanished registered test and a short pass count all fail", () => {
  assert.deepEqual(evaluateOffline(report([spec("a.spec.ts", "ok", "passed")]), subset).specsNotRun, ["b.spec.ts"]);
  const renamed = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("b.spec.ts", "renamed", "passed")]), subset);
  assert.deepEqual(renamed.knownMissing, ["b.spec.ts > known bad"]);
  const short = evaluateOffline(report([spec("a.spec.ts", "ok", "skipped"), spec("b.spec.ts", "known bad", "failed")]), subset);
  assert.equal(short.ok, false);
  assert.match(short.minimums[0], /a\.spec\.ts: 0 passed < required 1/);
});

test("a registered failure pinned to one assertion fails the ratchet when it breaks differently", () => {
  const pinned = { ...subset, known_failures: [{ id: "b.spec.ts > known bad", reason: "r", owner: "o", error_must_match: "price-strip[\\s\\S]*61\\.25" }] };
  const expected = "\u001b[31mError: expect(locator).toContainText(expected) failed\u001b[39m\n\nLocator: locator('.price-strip')\nExpected substring: \"£61.25/MWh\"";
  const same = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("b.spec.ts", "known bad", "failed", [expected])]), pinned);
  assert.equal(same.ok, true);
  const second = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("b.spec.ts", "known bad", "failed", [expected, "Error: heading not visible"])]), pinned);
  assert.equal(second.ok, false);
  assert.deepEqual(second.unexpectedErrors, ["b.spec.ts > known bad: Error: heading not visible"]);
  assert.match(describeEvaluation(second), /REGISTERED FAILURE BROKE DIFFERENTLY/);
  const silent = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("b.spec.ts", "known bad", "failed")]), pinned);
  assert.equal(silent.ok, false, "a pinned failure without any recorded error is not the pinned failure");
});

test("skipped tests are reported but never counted as passes", () => {
  const outcome = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("a.spec.ts", "gated", "skipped"), spec("b.spec.ts", "known bad", "failed")]), subset);
  assert.equal(outcome.ok, true);
  assert.equal(outcome.totals.skipped, 1);
  assert.equal(outcome.perSpec["a.spec.ts"].passed, 1);
});

test("a registered failure that is now skipped did not run and fails the ratchet", () => {
  const outcome = evaluateOffline(report([spec("a.spec.ts", "ok", "passed"), spec("b.spec.ts", "known bad", "skipped")]), subset);
  assert.equal(outcome.ok, false);
  assert.deepEqual(outcome.skippedKnown, ["b.spec.ts > known bad"]);
  assert.deepEqual(outcome.newFailures, []);
  assert.deepEqual(outcome.fixedButListed, []);
  assert.match(describeEvaluation(outcome), /REGISTERED TEST WAS SKIPPED b\.spec\.ts > known bad/);
});

test("R3-01 is fixed (P0-9 S3): market-visibility has no registered failure and must pass", async () => {
  const { readFile } = await import("node:fs/promises");
  const committed = JSON.parse(await readFile(new URL("../../../e2e/offline-subset.json", import.meta.url), "utf8"));
  assert.equal(committed.known_failures.some((item) => item.id.startsWith("market-visibility.spec.ts > ")), false);
  assert.equal(committed.min_passed["e2e/market-visibility.spec.ts"], 1);
});

test("the committed offline subset only names specs and registered tests that exist", async () => {
  const { readFile, access } = await import("node:fs/promises");
  const committed = JSON.parse(await readFile(new URL("../../../e2e/offline-subset.json", import.meta.url), "utf8"));
  for (const name of committed.specs) await access(new URL(`../../../${name}`, import.meta.url));
  for (const entry of committed.known_failures) {
    assert.ok(entry.reason && entry.owner, `${entry.id} needs a reason and an owner`);
    assert.ok(committed.specs.some((name) => entry.id.startsWith(`${name.replace(/^e2e\//, "")} > `)), `${entry.id} is outside the subset`);
    if (entry.error_must_match !== undefined) assert.doesNotThrow(() => new RegExp(entry.error_must_match), `${entry.id} has an invalid error_must_match`);
  }
  for (const name of Object.keys(committed.min_passed)) assert.ok(committed.specs.includes(name), `${name} has a minimum but is not in the subset`);
});
