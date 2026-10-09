import assert from "node:assert/strict";
import test from "node:test";
import { navGroupLabel } from "../../../app/features/shared/navigation.ts";
import { translator } from "../../../app/i18n/index.ts";

// P1-polish: the designer rulings R-1..R-18 of 2026-10-09 (docs/dev/P1_FRONTEND_DEVIATIONS.md).
const en = translator("en");
const zh = translator("zh");

test("R-2: the four research paths are named in sentence case, in both interface languages", () => {
  const names = ["Reproduce from existing data", "Add your new data", "Edit a module", "Add a new function to VALUE"];
  for (const t of [en, zh]) {
    assert.deepEqual(["reproduce", "data", "module", "function"].map((path) => t(`home.path.${path}.label`)), names);
  }
});

test("R-3: the top bar's breadcrumb names the sidebar group, not the page number", () => {
  assert.equal(navGroupLabel("overview"), "nav.group.start");
  assert.equal(navGroupLabel("journey"), "nav.group.start");
  assert.equal(navGroupLabel("projects"), "nav.group.work");
  assert.equal(navGroupLabel("extend"), "nav.group.work");
  assert.equal(navGroupLabel("runCentre"), "nav.group.results");
  assert.equal(navGroupLabel("marketReplay"), "nav.group.results");
  assert.equal(navGroupLabel("systems"), "nav.group.results");
  assert.equal(navGroupLabel("audit"), "nav.group.results");
  assert.equal(en("header.breadcrumb", { group: en(navGroupLabel("data")) }), "VALUE / Work");
  assert.equal(zh("header.breadcrumb", { group: zh(navGroupLabel("compare")) }), "VALUE / 结果");
});

test("R-8: a disabled save button names its reason; a pressable one has none", async () => {
  const { saveDisabledReason } = await import("../../../app/features/studies/studySave.ts");
  const base = { saving: false, resolving: false, blockedReason: "", resolution: { valid: true, errors: [] }, solverContractReady: true };
  assert.equal(saveDisabledReason(base, en), "");
  assert.equal(saveDisabledReason({ ...base, saving: true }, en), "");
  assert.equal(saveDisabledReason({ ...base, blockedReason: "Correct the model years in step 1 before saving." }, en), "Correct the model years in step 1 before saving.");
  assert.equal(saveDisabledReason({ ...base, resolving: true }, en), "Saving is possible once the draft has been checked.");
  assert.equal(saveDisabledReason({ ...base, resolution: null }, en), "Saving is possible once the local service has checked the draft.");
  assert.equal(saveDisabledReason({ ...base, resolution: { valid: false, errors: [{ code: "GF_EXPERIMENTAL_ACK_REQUIRED", message: "ack" }] } }, en), "Tick the experimental acknowledgement above before saving.");
  assert.equal(saveDisabledReason({ ...base, resolution: { valid: false, errors: [{ code: "GF_X", message: "Bad slot" }, { code: "GF_Y" }] } }, en), "Fix the 2 issues listed above before saving (first: GF_X: Bad slot).");
  assert.equal(saveDisabledReason({ ...base, solverContractReady: false }, zh), "请先填好分区求解器设置并勾选相应确认，再保存。");
});

test("R-10: the VRE page keeps its year and timeline resolution in the URL", async () => {
  const { DEFAULT_VRE_LOCATION, readVreLocation, vreQueryValues, vreYear } = await import("../../../app/features/market/vreLocation.ts");
  assert.deepEqual(readVreLocation("?year=2026&resolution=half_hour"), { year: 2026, resolution: "half_hour" });
  assert.deepEqual(readVreLocation("?year=abc&resolution=hourly&study=s"), DEFAULT_VRE_LOCATION);
  assert.equal(vreYear([2025, 2026], 2026), 2026);
  assert.equal(vreYear([2025, 2026], 2030), 2025, "a year the Run did not publish falls back to the first");
  assert.equal(vreYear([], 2026), 0);
  assert.deepEqual(vreQueryValues({ year: 2026, resolution: "daily" }), { year: 2026, resolution: null });
  assert.deepEqual(vreQueryValues({ year: 2025, resolution: "weekly" }), { year: 2025, resolution: "weekly" });
  assert.deepEqual(vreQueryValues({ year: 0, resolution: "daily" }), { year: null, resolution: null });
});

test("R-10: the Systems page keeps its result domain and year in the URL", async () => {
  const { readSystemsLocation, systemsQueryValues, systemsTab, systemsYear } = await import("../../../app/features/network/systemsLocation.ts");
  assert.deepEqual(readSystemsLocation("?tab=network_expansion&year=2026"), { tab: "network_expansion", year: 2026 });
  assert.deepEqual(readSystemsLocation("?tab=hydrology&year=x"), { tab: null, year: null });
  assert.equal(systemsTab(["network_dc", "network_expansion"], "network_expansion"), "network_expansion");
  assert.equal(systemsTab(["network_dc"], "network_expansion"), "network_dc", "a domain the Run lacks falls back to the first");
  assert.equal(systemsTab([], "network_dc"), null);
  assert.equal(systemsYear([2025, 2026], 2026), 2026);
  assert.equal(systemsYear([2025, 2026], 2031), 2025);
  assert.equal(systemsYear(undefined, 2026), 0);
  assert.deepEqual(systemsQueryValues({ tab: "network_dc", year: 2025 }, "network_dc"), { tab: null, year: 2025 });
  assert.deepEqual(systemsQueryValues({ tab: "network_expansion", year: 0 }, "network_dc"), { tab: "network_expansion", year: null });
});

test("R-10: the VRE and Systems routes read their URL once and write it back; network and Systems tab strips are app/ui Tabs", async () => {
  const { readFile } = await import("node:fs/promises");
  const read = (file) => readFile(new URL(`../../../${file}`, import.meta.url), "utf8");
  const vre = await read("app/runs/[runId]/vre/VreView.tsx");
  assert.match(vre, /const \[linked\] = useState\(\(\) => readVreLocation\(search\)\);/);
  assert.match(vre, /linked=\{linked\} onLocationChange=\{writeLocation\}/);
  const systems = await read("app/runs/[runId]/systems/SystemsView.tsx");
  assert.match(systems, /const \[linked\] = useState\(\(\) => readSystemsLocation\(search\)\);/);
  assert.match(systems, /linked=\{linked\} onLocationChange=\{writeLocation\}/);
  for (const file of ["app/features/network/NetworkRedispatchView.tsx", "app/features/network/SystemResultsView.tsx"]) {
    const source = await read(file);
    assert.match(source, /import \{ Tabs \} from "\.\.\/\.\.\/ui\/Tabs\.tsx";/, file);
    assert.match(source, /<Tabs className="[^"]+" label=\{t\("[^"]+"\)\}/, file);
    assert.doesNotMatch(source, /role="tablist"/, file);
  }
});

test("R-12: ?study= and ?run= are written only on the pages that read them", async () => {
  const { routeUrl, legacyRedirect } = await import("../../../app/features/shell/routes.ts");
  const state = (view, extra = {}) => ({ view, path: null, studyId: "s1", runId: "r1", runStudyId: "s1", dataContextId: "draft", ...extra });
  // Pages that do not use the selection: no study, no run.
  for (const [view, path] of [["overview", "/"], ["learn", "/learn"], ["models", "/modules"], ["compare", "/compare"], ["data", "/data"]]) {
    assert.equal(routeUrl(state(view), "", false), path, view);
  }
  assert.equal(routeUrl(state("compare"), "?runs=a,b&ref=a&study=old&run=old", true), "/compare?runs=a%2Cb&ref=a");
  // Pages that read the Study (and the Run centre and Inspect the Run).
  assert.equal(routeUrl(state("journey"), "", false), "/journey?study=s1");
  assert.equal(routeUrl(state("projects"), "", false), "/studies?study=s1");
  assert.equal(routeUrl(state("extend"), "", false), "/extensions?study=s1");
  assert.equal(routeUrl(state("runCentre"), "", false), "/runs?study=s1&run=r1");
  assert.equal(routeUrl(state("audit"), "", false), "/inspect?study=s1&run=r1");
  // Data for a saved Study's data context keeps the Study; the draft and journey contexts do not.
  assert.equal(routeUrl(state("data", { dataContextId: "s1" }), "", false), "/data?study=s1&dataContext=s1");
  // A Run page: the Run in the path, the Study only when it is not the Run's own.
  assert.equal(routeUrl(state("marketReplay"), "", false), "/runs/r1/replay");
  assert.equal(routeUrl(state("run", { studyId: "s2", runStudyId: "s1" }), "", false), "/runs/r1?study=s2");
  // An old /?view= link hands its whole selection on; the page then writes only what it reads.
  assert.equal(legacyRedirect("?view=data&study=s&run=r&path=data"), "/data?study=s&run=r&path=data");
});

test("R-15: Back from /studies/[id] to /studies leaves the edit; the edit header links back to Studies", async () => {
  const { readFile } = await import("node:fs/promises");
  const state = await readFile(new URL("../../../app/features/shell/useWorkbenchState.ts", import.meta.url), "utf8");
  // The router's Back is followed in the URL effect (a popstate listener is not reached on a real traversal).
  assert.match(state, /const routerLeftEdit = routed\?\.view === "projects" && !routed\.studyId && Boolean\(editing\)\n\s+&& samePathname\(lastRoutedPath\.current, `\/studies\/\$\{encodeURIComponent\(editing\)\}`\);/);
  assert.match(state, /const routerOpenedEdit = routed\?\.view === "projects" && Boolean\(routed\.studyId\) && routed\.studyId !== editing\n\s+&& !samePathname\(lastRoutedPath\.current, pathname\) && workspace\.projects\.some\(\(project\) => project\.id === routed\.studyId\);/);
  assert.match(state, /if \(routerLeftEdit\) \{ leaveStudyEditRef\.current\(\); return; \}\n\s+if \(routerOpenedEdit\) \{ pendingStudyEdit\.current = routed\?\.studyId \?\? ""; return; \}/);
  assert.match(state, /useEffect\(\(\) => \{ leaveStudyEditRef\.current = leaveStudyEdit; \}\);/);
  const view = await readFile(new URL("../../../app/studies/StudiesView.tsx", import.meta.url), "utf8");
  assert.match(view, /\{editingProjectId && <a className="studies-back" href=\{viewHref\("projects"\)\} onClick=\{\(event\) => \{ if \(!plainClick\(event\)\) return; event\.preventDefault\(\); leaveStudyEdit\(\); \}\}>\{t\("studies\.header\.back"\)\}<\/a>\}/);
  assert.equal(en("studies.header.back"), "← Back to Studies");
});
