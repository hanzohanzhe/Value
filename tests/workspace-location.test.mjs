import assert from "node:assert/strict";
import test from "node:test";
import { readWorkspaceLocation, writeWorkspaceLocation, selectWorkspaceRun } from "../app/features/workspace/workspaceLocation.ts";

test("workspace links preserve a selected Run and unrelated URL parameters", () => {
  const target = { view: "networkRedispatch", path: "reproduce", studyId: "研究 / A", runId: "run+1", dataContextId: "研究 / A" };
  const search = writeWorkspaceLocation("?external=keep", target);
  assert.equal(new URLSearchParams(search).get("external"), "keep");
  assert.deepEqual(readWorkspaceLocation(search), target);
});
test("unknown views and paths fall back safely and malformed identifiers are ignored", () => {
  assert.deepEqual(readWorkspaceLocation("?view=unknown&path=admin&study=%00bad&run=" + "x".repeat(257)), { view: "overview", path: null, studyId: "", runId: "", dataContextId: "draft" });
});
test("a cleared selection removes old identities from the URL", () => {
  assert.equal(writeWorkspaceLocation("?study=old&run=old&path=module&dataContext=old", { view: "overview", path: null, studyId: "", runId: "", dataContextId: "draft" }), "?view=overview");
});
test("an explicit missing or mismatched run does not fall back to another result", () => {
  const runs = [{ id: "a1", project_id: "a" }, { id: "b1", project_id: "b" }];
  assert.equal(selectWorkspaceRun(runs, "a", "missing"), undefined);
  assert.equal(selectWorkspaceRun(runs, "a", "b1"), undefined);
  assert.equal(selectWorkspaceRun(runs, "a", ""), runs[0]);
  // Frozen runs remain accessible when their source Study no longer appears in the workspace.
  assert.equal(selectWorkspaceRun(runs, "b", "b1"), runs[1]);
});
