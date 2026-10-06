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
// N-5 (four-role report, round R1-5): the journey Data context survives a reload.
test("the journey data context carries its source revision and target pack through the URL", async () => {
  const { journeyFromLocation } = await import("../app/features/workspace/workspaceLocation.ts");
  const target = { view: "data", path: "data", studyId: "value-101-baseline", runId: "", dataContextId: "journey", journey: { sourceRevisionSha256: "a".repeat(64), targetPackId: "my-pack" } };
  const search = writeWorkspaceLocation("", target);
  assert.equal(new URLSearchParams(search).get("journeyPack"), "my-pack");
  assert.deepEqual(readWorkspaceLocation(search), target);
  assert.deepEqual(journeyFromLocation(readWorkspaceLocation(search)), { sourceStudyId: "value-101-baseline", sourceRevisionSha256: "a".repeat(64), targetPackId: "my-pack" });
});
test("journey parameters are dropped outside the journey context and when malformed", async () => {
  const { journeyFromLocation } = await import("../app/features/workspace/workspaceLocation.ts");
  assert.equal(writeWorkspaceLocation("?journeyRevision=x&journeyPack=p", { view: "data", path: null, studyId: "s", runId: "", dataContextId: "draft", journey: { sourceRevisionSha256: "a".repeat(64), targetPackId: "p" } }), "?view=data&study=s");
  assert.equal(readWorkspaceLocation(`?dataContext=journey&study=s&journeyRevision=not-a-sha&journeyPack=p`).journey, undefined);
  assert.equal(readWorkspaceLocation(`?dataContext=draft&study=s&journeyRevision=${"a".repeat(64)}&journeyPack=p`).journey, undefined);
  assert.equal(journeyFromLocation(readWorkspaceLocation(`?dataContext=journey&journeyRevision=${"a".repeat(64)}&journeyPack=p`)), null, "no source Study, no context");
});
