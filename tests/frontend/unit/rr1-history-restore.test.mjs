import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { readRouteLocation, restoredSelection, routeUrl, workbenchUrlKey } from "../../../app/features/shell/routes.ts";

// RR-1 (1), D-P1P-6: Back/Forward restore the Study, Run and data context from
// the router's URL (a popstate listener never ran on a real traversal).

test("the workbench URL key keeps the path and the workbench query keys in one spelling", () => {
  assert.equal(workbenchUrlKey("/runs?study=s1&run=r1"), workbenchUrlKey("/runs/?run=r1&study=s1"));
  assert.equal(workbenchUrlKey("/runs/a%20b/vre"), workbenchUrlKey("/runs/a b/vre"));
  // Page keys (year, tab, runs/ref of Compare) are not the workbench's: a tab change is no traversal.
  assert.equal(workbenchUrlKey("/runs/r1/vre?year=2026&resolution=day"), workbenchUrlKey("/runs/r1/vre"));
  assert.equal(workbenchUrlKey("/compare?runs=a,b&ref=a"), workbenchUrlKey("/compare"));
  assert.notEqual(workbenchUrlKey("/runs?study=s1"), workbenchUrlKey("/runs?study=s2"));
  assert.notEqual(workbenchUrlKey("/data"), workbenchUrlKey("/data?dataContext=s1"));
  assert.notEqual(workbenchUrlKey("/data?study=s1"), workbenchUrlKey("/studies/s1"));
  // What the workbench writes (routeUrl) has the key the router later reports.
  const written = routeUrl({ view: "runCentre", path: null, studyId: "s 1", runId: "r/1", dataContextId: "draft" }, "", false);
  assert.equal(workbenchUrlKey(written), workbenchUrlKey(`/runs?${new URLSearchParams(written.split("?")[1]).toString()}`));
});

const runs = [{ id: "r1", project_id: "s1" }, { id: "r2", project_id: "s2" }];
const current = { studyId: "s2", runId: "r2", dataContextId: "draft" };
const restore = (url) => {
  const [path, search = ""] = url.split("?");
  return restoredSelection(readRouteLocation(path, `?${search}`), current, runs);
};

test("a traversed URL restores what its route carries", () => {
  assert.deepEqual(restore("/runs?study=s1&run=r1"), { studyId: "s1", runId: "r1", dataContextId: "draft" });
  // The Run centre without ?run= has no Run selected; the Run page's path names its Run (and its Study).
  assert.deepEqual(restore("/runs?study=s1"), { studyId: "s1", runId: "", dataContextId: "draft" });
  assert.deepEqual(restore("/runs/r1/replay"), { studyId: "s1", runId: "r1", dataContextId: "draft" });
  assert.deepEqual(restore("/data?study=s1&dataContext=s1"), { studyId: "s1", runId: "r2", dataContextId: "s1" });
  assert.deepEqual(restore("/studies/s1"), { studyId: "s1", runId: "r2", dataContextId: "draft" });
  assert.deepEqual(restore("/inspect?study=s1&run=r1"), { studyId: "s1", runId: "r1", dataContextId: "draft" });
});

test("a route that leaves ?study= and ?run= out keeps the current selection (R-12)", () => {
  for (const url of ["/compare", "/modules", "/learn", "/", "/data"]) {
    assert.deepEqual(restore(url), current, url);
  }
  // The data context is written on every route, so its absence means the draft.
  assert.equal(restore("/modules?dataContext=s1").dataContextId, "s1");
  // An explicit ?study= is applied wherever it appears.
  assert.equal(restore("/compare?study=s1").studyId, "s1");
});

test("the shell restores from the router's URL, not from a popstate listener", async () => {
  const state = await readFile(new URL("../../../app/features/shell/useWorkbenchState.ts", import.meta.url), "utf8");
  assert.doesNotMatch(state, /addEventListener\("popstate"/);
  assert.match(state, /const urlKey = workbenchUrlKey\(`\$\{pathname\}\?\$\{routerSearch\}`\);/);
  assert.match(state, /if \(own >= 0\) \{ ownUrlWrites\.current = ownUrlWrites\.current\.slice\(own \+ 1\); return; \}/);
  assert.match(state, /restoreRef\.current\(readRouteLocation\(pathname, `\?\$\{routerSearch\}`\)\);\n\s+\}, \[pathname, routerSearch, urlKey\]\);/);
  // Every URL the workbench writes is recorded before it is written; the write after a restoration is skipped.
  assert.match(state, /ownUrlWrites\.current = \[\.\.\.ownUrlWrites\.current, workbenchUrlKey\(target\)\]\.slice\(-8\);\n\s+if \(pageChanges\) \{/);
  assert.match(state, /const restoring = restoringLocation\.current;\n\s+restoringLocation\.current = false;/);
  assert.match(state, /if \(restoring\) return;/);
  // The restoration effect runs before the URL effect of the same commit.
  assert.ok(state.indexOf("restoreRef.current(readRouteLocation(") < state.indexOf("const restoring = restoringLocation.current;"));
});

test("a research path scrolls to its author tools after the router's scroll to the top (RR-1 3)", async () => {
  const state = await readFile(new URL("../../../app/features/shell/useWorkbenchState.ts", import.meta.url), "utf8");
  assert.match(state, /const frame = window\.requestAnimationFrame\(\(\) => document\.getElementById\(target\)\?\.scrollIntoView\(\{ block: "start" \}\)\);\n\s+return \(\) => window\.cancelAnimationFrame\(frame\);/);
});
