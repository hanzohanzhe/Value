import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { legacyRedirect, matchRoute, readRouteLocation, routePathname, routeUrl, samePathname, searchFromRecord, viewHref } from "../../../app/features/shell/routes.ts";
import { NAV_GROUPS, RUN_PAGE_VIEWS, RUN_SECTION_NAV, railView, runSectionEntry } from "../../../app/features/shared/navigation.ts";
import { WORKSPACE_VIEWS } from "../../../app/features/workspace/workspaceLocation.ts";
import { linkedReplayWindow } from "../../../app/features/market/replayLocation.ts";

// P1 spec 5.1 (W3): the route table, old ?view= links, and the URL as state.
// W4c: /runs is the Run centre ("runCentre"); /runs/[runId] one Run's annual results ("run").

const ROUTES = [
  ["/", "overview"], ["/learn", "learn"], ["/journey", "journey"], ["/studies", "projects"], ["/data", "data"],
  ["/modules", "models"], ["/extensions", "extend"], ["/runs", "runCentre"], ["/compare", "compare"], ["/inspect", "audit"],
];

test("every page of the route table has its path, and the path names its page", () => {
  for (const [path, view] of ROUTES) {
    assert.deepEqual(matchRoute(path), { view, runId: "", studyId: "" }, path);
    assert.equal(viewHref(view), path, view);
    assert.equal(routePathname({ view, runId: "" }), path, view);
  }
  const run = "value-101-basel-20261008-124521-79b241da";
  for (const [suffix, view] of [["", "run"], ["/replay", "marketReplay"], ["/vre", "curtailment"], ["/network", "networkRedispatch"], ["/systems", "systems"]]) {
    assert.deepEqual(matchRoute(`/runs/${run}${suffix}`), { view, runId: run, studyId: "" }, suffix);
    assert.equal(routePathname({ view, runId: run }), `/runs/${run}${suffix}`);
    // A Run page without a Run is the Run centre.
    assert.equal(routePathname({ view, runId: "" }), "/runs");
    assert.equal(viewHref(view), "/runs");
  }
  assert.deepEqual(matchRoute("/studies/my-study"), { view: "projects", runId: "", studyId: "my-study" });
  assert.equal(routePathname({ view: "projects", runId: "", editingStudyId: "my study" }), "/studies/my%20study");
  assert.deepEqual(matchRoute("/runs/a%20b/vre"), { view: "curtailment", runId: "a b", studyId: "" });
  for (const unknown of ["/nope", "/runs/x/unknown", "/runs/x/vre/more", "/studies/a/b", "/data/x", `/runs/${"x".repeat(300)}`, "/runs/%00bad"]) {
    assert.equal(matchRoute(unknown), null, unknown);
  }
  assert.ok(samePathname("/runs/a%20b", "/runs/a b"));
  assert.ok(samePathname("/data/", "/data"));
  assert.ok(!samePathname("/data", "/studies"));
});

test("the sidebar has three groups; a Run page marks Runs as current", () => {
  assert.deepEqual(NAV_GROUPS.map((group) => [group.label, [...group.ids]]), [
    ["nav.group.start", ["overview", "learn", "journey"]],
    ["nav.group.work", ["projects", "data", "models", "extend"]],
    ["nav.group.results", ["runCentre", "compare", "audit"]],
  ]);
  for (const view of RUN_PAGE_VIEWS) assert.equal(railView(view), "runCentre");
  // R3-16 (W4c): one network entry in the Run section bar; the optional-domain page belongs to it.
  assert.deepEqual([...RUN_SECTION_NAV], ["run", "marketReplay", "curtailment", "networkRedispatch"]);
  assert.equal(runSectionEntry("systems"), "networkRedispatch");
  assert.equal(runSectionEntry("marketReplay"), "marketReplay");
  assert.equal(railView("runCentre"), "runCentre");
  assert.equal(railView("audit"), "audit");
});

test("a URL restores the page from its path and the selection from its query", () => {
  const revision = "a".repeat(64);
  assert.deepEqual(readRouteLocation("/runs/r1/replay", "?study=s1&path=data&year=2025"), {
    view: "marketReplay", path: "data", studyId: "s1", runId: "r1", dataContextId: "draft", editingStudyId: "",
  });
  // Inspect and the other pages keep the Run in the query.
  assert.equal(readRouteLocation("/inspect", "?run=r2&tab=market").runId, "r2");
  assert.deepEqual(readRouteLocation("/studies/s9", "").studyId, "s9");
  assert.equal(readRouteLocation("/studies/s9", "").editingStudyId, "s9");
  assert.equal(readRouteLocation("/studies/s9", "?study=other").studyId, "other");
  // N-5: the journey data context survives a reload of /data.
  assert.deepEqual(readRouteLocation("/data", `?dataContext=journey&study=s&journeyRevision=${revision}&journeyPack=p`).journey, { sourceRevisionSha256: revision, targetPackId: "p" });
  // An unknown path is Home; ?view= is not read outside the root forwarder.
  assert.equal(readRouteLocation("/nope", "?view=data").view, "overview");
});

test("the URL of a workspace state: the Run in the path, the Study only when not implied, page keys kept on the same page", () => {
  const base = { path: null, dataContextId: "draft" };
  assert.equal(routeUrl({ ...base, view: "marketReplay", studyId: "s1", runId: "r1", runStudyId: "s1" }, "?year=2025&period=4", true), "/runs/r1/replay?year=2025&period=4");
  // A new page starts without the old page's keys.
  assert.equal(routeUrl({ ...base, view: "curtailment", studyId: "s1", runId: "r1", runStudyId: "s1" }, "?year=2025&period=4", false), "/runs/r1/vre");
  // A Run that is not the Study's keeps the Study, so the mismatch stays visible (never a substitute result).
  assert.equal(routeUrl({ ...base, view: "run", studyId: "s2", runId: "r1", runStudyId: undefined }, "", false), "/runs/r1?study=s2");
  assert.equal(routeUrl({ ...base, view: "data", studyId: "s1", runId: "r1", path: "data", dataContextId: "journey", journey: { sourceRevisionSha256: "b".repeat(64), targetPackId: "p" } }, "?view=data&stale=1", false),
    // P1-polish R-12: Data with the journey context reads neither the Study nor the Run from the URL.
    `/data?path=data&dataContext=journey&journeyRevision=${"b".repeat(64)}&journeyPack=p`);
  assert.equal(routeUrl({ ...base, view: "projects", studyId: "s1", runId: "", editingStudyId: "s1" }, "", false), "/studies/s1");
  assert.equal(routeUrl({ ...base, view: "audit", studyId: "s1", runId: "r1", runStudyId: "s1" }, "?tab=market", true), "/inspect?tab=market&study=s1&run=r1");
  assert.equal(routeUrl({ ...base, view: "overview", studyId: "", runId: "" }, "?view=run&study=old", true), "/");
});

test("all 13 old ?view= values redirect to their route and keep the other parameters", () => {
  const revision = "c".repeat(64);
  // Outside the Run pages the Run stays in the query (as before the routes).
  const kept = "study=s&run=r&path=data";
  const expected = {
    overview: `/?${kept}`, learn: `/learn?${kept}`, journey: `/journey?${kept}`,
    projects: `/studies?${kept}`, data: `/data?${kept}`, models: `/modules?${kept}`,
    extend: `/extensions?${kept}`, run: "/runs/r?study=s&path=data", marketReplay: "/runs/r/replay?study=s&path=data",
    curtailment: "/runs/r/vre?study=s&path=data", networkRedispatch: "/runs/r/network?study=s&path=data",
    systems: "/runs/r/systems?study=s&path=data", audit: `/inspect?${kept}`,
  };
  assert.equal(WORKSPACE_VIEWS.length, 13);
  for (const view of WORKSPACE_VIEWS) {
    assert.equal(legacyRedirect(`?view=${view}&study=s&run=r&path=data`), expected[view], view);
  }
  // Without a Run, a Run page is the Run centre; the journey context is kept.
  assert.equal(legacyRedirect("?view=marketReplay&study=s"), "/runs?study=s");
  assert.equal(legacyRedirect(`?view=data&dataContext=journey&study=s&journeyRevision=${revision}&journeyPack=p`), `/data?dataContext=journey&study=s&journeyRevision=${revision}&journeyPack=p`);
  assert.equal(legacyRedirect("?view=unknown"), "/");
  assert.equal(legacyRedirect("?study=s"), null);
  assert.equal(legacyRedirect(""), null);
  assert.equal(searchFromRecord({ view: "run", run: ["a", "b"], none: undefined }), "?view=run&run=a&run=b");
});

test("the replay window of a link", () => {
  assert.deepEqual(linkedReplayWindow("?year=2025&period=96&stage=balancing"), { year: 2025, period: 96, from: 96, stage: "balancing" });
  assert.deepEqual(linkedReplayWindow("?year=2025&period=100&from=96"), { year: 2025, period: 100, from: 96, stage: "" });
  for (const bad of ["", "?period=4", "?year=x", "?year=0", "?year=2025.5"]) assert.equal(linkedReplayWindow(bad), null, bad);
  assert.equal(linkedReplayWindow("?year=2025&period=-3").period, 0);
});

test("the root page is only Home and the forwarder; the routes render their pages on the server", async () => {
  const read = (file) => readFile(new URL(`../../../${file}`, import.meta.url), "utf8");
  const page = await read("app/page.tsx");
  assert.doesNotMatch(page, /"use client"/);
  assert.match(page, /const target = legacyRedirect\(searchFromRecord\(await searchParams\)\);\n  if \(target\) redirect\(target\);/);
  assert.ok(page.split("\n").length < 30, "app/page.tsx stays a forwarder");
  const layout = await read("app/layout.tsx");
  assert.match(layout, /<LocaleProvider initialLocale=\{locale\}><Workbench>\{children\}<\/Workbench><\/LocaleProvider>/);
  for (const [file, view] of [["app/learn/page.tsx", "LearnView"], ["app/journey/page.tsx", "JourneyView"], ["app/studies/page.tsx", "StudiesView"], ["app/studies/[studyId]/page.tsx", "StudiesView"], ["app/data/page.tsx", "DataView"], ["app/modules/page.tsx", "ModulesView"], ["app/extensions/page.tsx", "ExtensionsView"], ["app/runs/page.tsx", "RunsView"], ["app/runs/[runId]/page.tsx", "RunResultsView"], ["app/runs/[runId]/replay/page.tsx", "ReplayView"], ["app/runs/[runId]/vre/page.tsx", "VreView"], ["app/runs/[runId]/network/page.tsx", "NetworkView"], ["app/runs/[runId]/systems/page.tsx", "SystemsView"], ["app/compare/page.tsx", "CompareView"], ["app/inspect/page.tsx", "InspectView"]]) {
    assert.match(await read(file), new RegExp(`return <${view} />;`), file);
  }
  // The shell: skip link first, then header, nav (sidebar) and main; the sidebar is not inside main (F2-04).
  const shell = await read("app/features/shell/Workbench.tsx");
  const order = ["<a className=\"skip-link\" href=\"#main-content\">", "<header className=\"topbar\">", "<WorkspaceRail ", "<main id=\"main-content\""].map((item) => shell.indexOf(item));
  assert.ok(order.every((index) => index > 0), String(order));
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  assert.ok(shell.indexOf("<WorkspaceRail ") < shell.indexOf("<main id=\"main-content\""));
  // R3-07: the research-task switch only on the research guide (P1 W4a: /journey is an
  // ordinary route page, D-W3-2), with the guide's current task selected.
  assert.doesNotMatch(shell, /CommunityPathPicker|ResearchJourney/);
  const journey = await read("app/journey/JourneyView.tsx");
  assert.match(journey, /const intent = activePath === "data" \? "data" : "reproduce";\n  return <div className="page journey-page">\n    <CommunityPathPicker activePath=\{intent\}/);
  assert.match(journey, /<ResearchJourney intent=\{intent\}/);
  // W4c: the Run section bar also on the Run centre when a Run is selected.
  assert.match(shell, /\{\(isRunSectionView\(view\) \|\| view === "runCentre"\) && runId && <RunSectionNav /);
  // Spec 5.2: the Run context bar on the pages of one Run (and Inspect, D-W3-3).
  assert.match(shell, /const runRoute = \(isRunSectionView\(view\) && Boolean\(runId\)\) \|\| view === "audit";/);
});
