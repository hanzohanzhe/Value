import assert from "node:assert/strict";
import test from "node:test";
import { createWorkspaceStore, selectFrom, selectRuns, selectWorkspace, shallowEqualArray } from "../../../app/lib/workspaceStore.ts";

// P1 spec 4 (W2): one workspace store; pages subscribe to slices; polls are
// merged by structural sharing so unchanged Studies and Runs keep their
// identity (F1-01: selections are not reset by polling).
const empty = { architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [], data_packs: [], module_installations: [], extension_installations: [], projects: [], study_trash: [], runs: [], runtime: { python: "", compatible: false } };
const answer = (runs) => ({ ...empty, projects: [{ id: "s1", name: "Study" }], runs });

test("a new answer marks the service online and loaded; an equal answer changes nothing and notifies no one", () => {
  const store = createWorkspaceStore(empty);
  let notified = 0;
  store.subscribe(() => { notified += 1; });
  store.update({ failures: 2, online: false });
  assert.equal(notified, 1);
  store.receiveWorkspace(answer([{ id: "r1", status: "running" }]));
  assert.equal(notified, 2);
  const snapshot = store.getSnapshot();
  assert.equal(snapshot.loaded, true);
  assert.equal(snapshot.online, true);
  assert.equal(snapshot.failures, 0);
  store.receiveWorkspace(answer([{ id: "r1", status: "running" }]));
  assert.equal(notified, 2, "an identical poll does not notify");
  assert.equal(store.getSnapshot(), snapshot);
});

test("a poll that changes one Run keeps the identity of the Study list and of the other Runs", () => {
  const store = createWorkspaceStore(empty);
  store.receiveWorkspace(answer([{ id: "r1", status: "running" }, { id: "r2", status: "completed" }]));
  const before = store.getSnapshot().workspace;
  store.receiveWorkspace(answer([{ id: "r1", status: "completed" }, { id: "r2", status: "completed" }]));
  const after = store.getSnapshot().workspace;
  assert.notEqual(after, before);
  assert.equal(after.projects, before.projects);
  assert.equal(after.runs[1], before.runs[1]);
  assert.notEqual(after.runs[0], before.runs[0]);
});

test("a slice selector returns the same value while its slice is unchanged", () => {
  const store = createWorkspaceStore(empty);
  store.receiveWorkspace(answer([{ id: "r1", status: "running" }]));
  const runs = selectFrom(store, selectRuns);
  const first = runs();
  store.update({ health: { status: "ok", degraded_reasons: [] } });
  assert.equal(runs(), first, "a health change does not change the Run slice");
  const filtered = selectFrom(store, (snapshot) => snapshot.workspace.runs.filter((run) => run.status === "running"), shallowEqualArray);
  const active = filtered();
  store.update({ failures: 1 });
  assert.equal(filtered(), active, "an equal filtered list is the previous array");
  assert.equal(selectFrom(store, selectWorkspace)(), store.getSnapshot().workspace);
});

test("health answers are shared too: an equal health payload does not notify", () => {
  const store = createWorkspaceStore(empty);
  let notified = 0;
  store.update({ health: { status: "ok", degraded_reasons: [] } });
  store.subscribe(() => { notified += 1; });
  store.update({ health: { status: "ok", degraded_reasons: [] } });
  assert.equal(notified, 0);
  store.update({ health: null });
  assert.equal(notified, 1);
});
