import assert from "node:assert/strict";
import test from "node:test";
import { createPoller, pollDelay, replaceEqualDeep } from "../../../app/lib/poll.ts";

// P1 spec 4 (W2): polling with one request in flight, visibility pause,
// backoff, and structural sharing (F1-01).

test("structural sharing: an equal answer is the previous object itself", () => {
  const previous = { runs: [{ id: "a", status: "running", years: [2025] }], packs: [{ id: "p" }], version: 2 };
  const next = JSON.parse(JSON.stringify(previous));
  assert.equal(replaceEqualDeep(previous, next), previous);
});

test("structural sharing: unchanged items keep their identity, changed ones and their parents are new", () => {
  const runA = { id: "a", status: "running", progress: { year: 2025 } };
  const runB = { id: "b", status: "completed", progress: { year: 2030 } };
  const packs = [{ id: "p", name: "Pack" }];
  const previous = { runs: [runA, runB], packs };
  const next = { runs: [{ id: "a", status: "completed", progress: { year: 2025 } }, { id: "b", status: "completed", progress: { year: 2030 } }], packs: [{ id: "p", name: "Pack" }] };
  const shared = replaceEqualDeep(previous, next);
  assert.notEqual(shared, previous);
  assert.notEqual(shared.runs, previous.runs);
  assert.notEqual(shared.runs[0], runA, "changed Run is a new object");
  assert.equal(shared.runs[0].progress, runA.progress, "its unchanged part is shared");
  assert.equal(shared.runs[1], runB, "unchanged Run keeps its identity");
  assert.equal(shared.packs, packs, "unchanged list keeps its identity");
});

test("structural sharing matches array items by ID, not by position", () => {
  const a = { id: "a", n: 1 };
  const b = { id: "b", n: 2 };
  const shared = replaceEqualDeep([a, b], [{ id: "c", n: 3 }, { id: "b", n: 2 }, { id: "a", n: 1 }]);
  assert.equal(shared[1], b);
  assert.equal(shared[2], a);
  assert.deepEqual(shared[0], { id: "c", n: 3 });
});

test("structural sharing: duplicate IDs fall back to position; removed keys and nulls are changes", () => {
  const first = { id: "x", n: 1 };
  const shared = replaceEqualDeep([first, { id: "x", n: 2 }], [{ id: "x", n: 1 }, { id: "x", n: 3 }]);
  assert.equal(shared[0], first);
  assert.equal(shared[1].n, 3);
  const withKey = { a: 1, b: 2 };
  assert.deepEqual(replaceEqualDeep(withKey, { a: 1 }), { a: 1 });
  assert.equal(replaceEqualDeep({ a: { b: 1 } }, { a: null }).a, null);
  assert.equal(replaceEqualDeep(null, { a: 1 }).a, 1);
});

function harness() {
  const timers = [];
  const listeners = new Map();
  const documentRef = {
    hidden: false,
    addEventListener: (name, listener) => listeners.set(name, listener),
    removeEventListener: (name) => listeners.delete(name),
  };
  return {
    timers,
    documentRef,
    setTimer: (callback, ms) => { const handle = { callback, ms, cleared: false }; timers.push(handle); return handle; },
    clearTimer: (handle) => { handle.cleared = true; },
    pending: () => timers.filter((timer) => !timer.cleared && !timer.fired),
    fire: async () => { const timer = timers.find((item) => !item.cleared && !item.fired); timer.fired = true; timer.callback(); await new Promise((resolve) => setImmediate(resolve)); },
    visibility: (hidden) => { documentRef.hidden = hidden; listeners.get("visibilitychange")?.(); },
  };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test("one read in flight: a refresh during a read waits for it and then reads again", async () => {
  const h = harness();
  const resolvers = [];
  let reads = 0;
  const poller = createPoller({
    read: () => { reads += 1; return new Promise((resolve) => resolvers.push(resolve)); },
    onData: () => {}, shouldPoll: () => false, setTimer: h.setTimer, clearTimer: h.clearTimer, documentRef: h.documentRef,
  });
  poller.start();
  const first = poller.refresh();
  const second = poller.refresh();
  const third = poller.refresh();
  assert.equal(reads, 1, "no second request while one is in flight");
  assert.equal(second, third, "concurrent refreshes share the queued read");
  resolvers[0]("one");
  assert.equal(await first, "one");
  await settle();
  assert.equal(reads, 2, "the queued read starts after the first answer");
  resolvers[1]("two");
  assert.equal(await second, "two");
  poller.stop();
});

test("backoff after failures doubles from 2 s (4, 8, 16, then 30 s); success resets it; polling stops when idle", async () => {
  const h = harness();
  let fail = true;
  const failures = [];
  const poller = createPoller({
    read: async () => { if (fail) throw new TypeError("Failed to fetch"); return "ok"; },
    onData: () => {}, onError: (_error, count) => failures.push(count), shouldPoll: () => false,
    setTimer: h.setTimer, clearTimer: h.clearTimer, documentRef: h.documentRef,
  });
  poller.start();
  assert.equal(h.pending().length, 0, "idle and healthy: no timer");
  await poller.refresh();
  await settle();
  const delays = [];
  for (let index = 0; index < 5; index += 1) {
    const [timer] = h.pending();
    delays.push(timer.ms);
    await h.fire();
    await settle();
  }
  // 2 s is the normal interval while a Run is active; each failure doubles it (P0-3 S8).
  assert.deepEqual(delays, [4000, 8000, 16000, 30000, 30000]);
  assert.deepEqual(failures, [1, 2, 3, 4, 5, 6]);
  assert.equal(h.pending()[0].ms, pollDelay(6));
  fail = false;
  await h.fire();
  await settle();
  assert.equal(poller.state().failures, 0);
  assert.equal(h.pending().length, 0, "healthy and idle again: polling stops");
  poller.stop();
});

test("while a Run is active the poller reads every 2 s; hidden pauses, visible refreshes at once", async () => {
  const h = harness();
  let reads = 0;
  const poller = createPoller({
    read: async () => { reads += 1; return reads; },
    onData: () => {}, shouldPoll: () => true, setTimer: h.setTimer, clearTimer: h.clearTimer, documentRef: h.documentRef,
  });
  poller.start();
  assert.equal(h.pending()[0].ms, 2000);
  await h.fire();
  assert.equal(reads, 1);
  await settle();
  assert.equal(h.pending().length, 1);
  h.visibility(true);
  assert.equal(h.pending().length, 0, "hidden: no timer");
  h.visibility(false);
  await settle();
  assert.equal(reads, 2, "shown again: one read at once");
  await settle();
  assert.equal(h.pending().length, 1, "and polling resumes");
  poller.stop();
  assert.equal(h.pending().length, 0);
});

test("a fatal error (launcher) stops polling and is not counted as a failure", async () => {
  const h = harness();
  const errors = [];
  class Fatal extends Error {}
  const poller = createPoller({
    read: async () => { throw new Fatal("launcher"); },
    onData: () => {}, onError: (error, count) => errors.push([error.constructor.name, count]),
    fatal: (error) => error instanceof Fatal, shouldPoll: () => true,
    setTimer: h.setTimer, clearTimer: h.clearTimer, documentRef: h.documentRef,
  });
  poller.start();
  assert.equal(await poller.refresh(), null);
  await settle();
  assert.deepEqual(errors, [["Fatal", 0]]);
  assert.equal(poller.state().failures, 0);
  assert.equal(h.pending().length, 0);
});

test("reschedule starts polling when a Run becomes active", async () => {
  const h = harness();
  let active = false;
  const poller = createPoller({
    read: async () => "ok", onData: () => {}, shouldPoll: () => active,
    setTimer: h.setTimer, clearTimer: h.clearTimer, documentRef: h.documentRef,
  });
  poller.start();
  assert.equal(h.pending().length, 0);
  active = true;
  poller.reschedule();
  assert.equal(h.pending().length, 1);
  poller.stop();
});

// P1-polish R-9: the in-page job pollers (replay export, Data Workbench build)
// use this poller with their own cadence, so they pause while the page is
// hidden and read again at once when it is shown.
test("a poller with its own interval keeps that cadence, pauses while hidden and reads at once when shown", async () => {
  const h = harness();
  let reads = 0;
  const poller = createPoller({
    read: async () => { reads += 1; return reads; }, onData: () => {}, interval: (failures) => (failures ? 650 * 2 ** failures : 1500),
    setTimer: h.setTimer, clearTimer: h.clearTimer, documentRef: h.documentRef,
  });
  poller.start();
  assert.deepEqual(h.pending().map((timer) => timer.ms), [1500]);
  await h.fire();
  assert.equal(reads, 1);
  assert.deepEqual(h.pending().map((timer) => timer.ms), [1500]);
  h.visibility(true);
  assert.equal(h.pending().length, 0, "nothing is scheduled while the page is hidden");
  h.visibility(false);
  await settle();
  assert.equal(reads, 2, "shown again: one read at once");
  assert.deepEqual(h.pending().map((timer) => timer.ms), [1500]);
  poller.stop();
  assert.equal(h.pending().length, 0);
});

test("a poller's own interval also sets the wait after a failure", async () => {
  const h = harness();
  const poller = createPoller({
    read: async () => { throw new Error("down"); }, onData: () => {}, interval: (failures) => (failures ? 650 * 2 ** failures : 650),
    setTimer: h.setTimer, clearTimer: h.clearTimer, documentRef: h.documentRef,
  });
  poller.start();
  await h.fire();
  assert.deepEqual(h.pending().map((timer) => timer.ms), [1300]);
  poller.stop();
});

test("the replay export and Data Workbench job pollers go through lib/poll.ts, not their own timers", async () => {
  const { readFile } = await import("node:fs/promises");
  for (const file of ["app/features/market/ReplayExportPanel.tsx", "app/features/data-workbench/DataWorkbench.tsx"]) {
    const source = await readFile(new URL(`../../../${file}`, import.meta.url), "utf8");
    assert.match(source, /import \{ createPoller \} from "\.\.\/\.\.\/lib\/poll\.ts";/, file);
    assert.match(source, /createPoller(<[^>]+>)?\(\{/, file);
    assert.doesNotMatch(source, /setInterval\(/, file);
  }
  const workbench = await readFile(new URL("../../../app/features/data-workbench/DataWorkbench.tsx", import.meta.url), "utf8");
  assert.match(workbench, /interval: pollDelay,/);
  assert.match(workbench, /if \(count >= MAX_POLL_FAILURES\) poller\.stop\(\);/);
});
