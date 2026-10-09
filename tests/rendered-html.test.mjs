import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render(headers = {}, path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const request = new Request(`http://localhost${path}`, { headers: { accept: "text/html", ...headers }, redirect: "manual" });
  const environment = { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } };
  const executionContext = { waitUntil() {}, passThroughOnException() {} };

  // Vinext 0.0.50 can emit either its request handler directly or a
  // Cloudflare-style worker object, depending on the resolved build path.
  // Exercise the generated server without tying the release gate to one
  // wrapper shape.
  if (typeof worker === "function") return worker(request, environment);
  return worker.fetch(request, environment, executionContext);
}

test("server-renders the modular modelling workbench", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /VALUE/);
  assert.match(html, /VALUE 101/);
  assert.match(html, /Synthetic teaching diagnostic/);
  assert.match(html, /Learn/);
  assert.match(html, /Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation/);
  assert.match(html, /Runs/);
  assert.match(html, /PSM/);
  assert.match(html, /CEM/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
});

// P1 spec 3 (A30): English unless the reader chose Chinese; the server reads
// the value_locale cookie, so the first paint and <html lang> already match.
test("server-renders English by default and Chinese when value_locale=zh", async () => {
  const english = await (await render()).text();
  assert.match(english, /<html lang="en-GB"/);
  assert.match(english, /Research guide/);
  const chinese = await (await render({ cookie: "value_locale=zh" })).text();
  assert.match(chinese, /<html lang="zh-Hans"/);
  assert.match(chinese, /研究路径/);
  assert.match(chinese, /aria-pressed="true"[^>]*>中文/);
});

// P1 W5 (spec 3): the English dictionaries of the views translated in W5.
const W5_WORDING_FILES = ["../app/i18n/messages/network.en.ts", "../app/i18n/messages/market.en.ts", "../app/i18n/messages/runViews.en.ts", "../app/i18n/messages/evidence.en.ts", "../app/i18n/messages/workspace.en.ts"];
const WORKBENCH_FILES = [
  "../app/page.tsx", "../app/HomeView.tsx", "../app/features/shell/useWorkbenchState.ts", "../app/features/shell/Workbench.tsx",
  "../app/learn/LearnView.tsx", "../app/studies/StudiesView.tsx", "../app/data/DataView.tsx", "../app/modules/ModulesView.tsx",
  "../app/extensions/ExtensionsView.tsx", "../app/runs/RunsView.tsx", "../app/runs/[runId]/RunResultsView.tsx", "../app/runs/[runId]/replay/ReplayView.tsx",
  "../app/runs/[runId]/vre/VreView.tsx", "../app/runs/[runId]/network/NetworkView.tsx", "../app/runs/[runId]/systems/SystemsView.tsx",
  "../app/inspect/InspectView.tsx", "../app/compare/CompareView.tsx",
  "../app/features/market/MarketReplayView.tsx", "../app/features/market/CurtailmentView.tsx", "../app/features/network/SystemResultsView.tsx",
  // The pages' composed parts that hold the asserted wording (some since before W3).
  "../app/features/shared/navigation.ts", "../app/features/studies/AdvancedSettings.tsx", "../app/features/studies/SolverSettingsEditor.tsx",
  "../app/features/runs/RunWorkspace.tsx", "../app/features/runs/RunStatusPanel.tsx", "../app/features/runs/RunResultsPage.tsx", "../app/features/runs/RunResults.tsx", "../app/features/evidence/AuditView.tsx", "../app/features/evidence/ReadinessEvidence.tsx",
  // P1 W4a: the wording of Home, Learn, the research guide and Studies is in their dictionaries.
  "../app/i18n/en/home.ts", "../app/i18n/en/learn.ts", "../app/i18n/en/journey.ts", "../app/i18n/en/studies.ts",
  // P1 W5: the remaining result views' wording is in their dictionaries.
  ...W5_WORDING_FILES,
];

// P1 spec 5.1 (W3, F1-09): every route is rendered on the server as its own
// page (no Home first); an old /?view= link is redirected to its route.
test("server-renders each route's own page and forwards old ?view= links", async () => {
  for (const [path, title] of [["/", "Home"], ["/learn", "Learn"], ["/journey", "Research guide"], ["/studies", "Studies"], ["/studies/s1", "Studies"], ["/data", "Data"], ["/modules", "Modules"], ["/extensions", "Extensions"], ["/runs", "Runs"], ["/runs/r1", "Runs"], ["/runs/r1/replay", "Market replay"], ["/runs/r1/vre", "VRE &amp; curtailment"], ["/runs/r1/network", "Network &amp; redispatch"], ["/runs/r1/systems", "Network &amp; water"], ["/compare", "Compare"], ["/inspect", "Inspect"]]) {
    const response = await render({}, path);
    assert.equal(response.status, 200, path);
    const html = await response.text();
    assert.match(html, new RegExp(`<h1 tabindex="-1">${title}</h1>`), path);
    assert.match(html, /<a class="skip-link" href="#main-content">Skip to main content<\/a>/, path);
    assert.match(html, /<main id="main-content"/, path);
  }
  const forwarded = await render({}, "/?view=marketReplay&study=s1&run=r1&path=data");
  assert.ok([302, 303, 307, 308].includes(forwarded.status), String(forwarded.status));
  assert.match(forwarded.headers.get("location") ?? "", /\/runs\/r1\/replay\?study=s1&path=data$/);
});

// Every script the RSC asset manifest lists for preloading exists in the client
// build (a style-only shared chunk once listed an empty, unwritten script).
test("every chunk the asset manifest lists is in the client build", async () => {
  const { existsSync } = await import("node:fs");
  const manifest = await readFile(new URL("../dist/server/__vite_rsc_assets_manifest.js", import.meta.url), "utf8");
  const assets = [...new Set([...manifest.matchAll(/"(\/_next\/static\/[^"]+)"/g)].map((match) => match[1]))];
  assert.ok(assets.length > 10);
  const missing = assets.filter((asset) => !existsSync(new URL(`../dist/client${asset}`, import.meta.url)));
  assert.deepEqual(missing, []);
});

test("uses the shared application service and on-demand audit contracts", async () => {
  const [page, server, runner, application, orchestrator, learn, network, waterfall, replayExport, traceCoverage] = await Promise.all([
    // P1 W3: app/page.tsx became the workbench state, the shell and one route per page.
    Promise.all(WORKBENCH_FILES.map((file) => readFile(new URL(file, import.meta.url), "utf8"))).then((parts) => parts.join("\n")),
    readFile(new URL("../backend/server.py", import.meta.url), "utf8"),
    readFile(new URL("../backend/model_runner.py", import.meta.url), "utf8"),
    readFile(new URL("../gridform_core/application.py", import.meta.url), "utf8"),
    readFile(new URL("../gridform_core/orchestrator.py", import.meta.url), "utf8"),
    // P1 W4a: Learn's wording is in its dictionary.
    Promise.all(["../app/features/learn/Value101Learn.tsx", "../app/i18n/en/learn.ts"].map((file) => readFile(new URL(file, import.meta.url), "utf8"))).then((parts) => parts.join("\n")),
    // P1 W5: the network page's and the waterfall's wording is in their dictionaries (en and zh).
    Promise.all(["../app/features/network/NetworkRedispatchView.tsx", "../app/i18n/messages/network.en.ts", "../app/i18n/messages/network.zh.ts"].map((file) => readFile(new URL(file, import.meta.url), "utf8"))).then((parts) => parts.join("\n")),
    Promise.all(["../app/features/network/CurtailmentWaterfall.tsx", "../app/i18n/messages/network.en.ts"].map((file) => readFile(new URL(file, import.meta.url), "utf8"))).then((parts) => parts.join("\n")),
    readFile(new URL("../app/features/market/ReplayExportPanel.tsx", import.meta.url), "utf8"),
    Promise.all(["../app/features/market/TraceCoverageNotice.tsx", "../app/i18n/messages/market.en.ts"].map((file) => readFile(new URL(file, import.meta.url), "utf8"))).then((parts) => parts.join("\n")),
  ]);
  assert.match(page, /data-packs/);
  assert.match(page, /Allocate variable electricity/i);
  assert.match(page, /startRun/);
  assert.match(page, /startRun\("value_101_day"/);
  // P1 W5: the Run centre's wording is in its dictionary.
  const runWorkspace = (await Promise.all(["../app/features/runs/RunWorkspace.tsx", "../app/i18n/messages/runViews.en.ts"].map((file) => readFile(new URL(file, import.meta.url), "utf8")))).join("\n");
  assert.match(runWorkspace, /Run selected scope/);
  assert.match(runWorkspace, /startRun\(effectivePreflightMode\)/);
  assert.match(runWorkspace, /checkPreflight\(effectivePreflightMode/);
  assert.match(page, /two_year_smoke/);
  assert.match(page, /Advanced assumptions/);
  assert.match(page, /Planning pipeline/);
  assert.match(page, /onCreateFullReplayRevision=\{createFullReplayRevision\}/);
  assert.doesNotMatch(page, /Re-run with <code>runtime\.market_trace_level = full<\/code>/);
  assert.match(traceCoverage, /Create a new Study revision with Full market replay/);
  // W4c: the Inspect tab labels moved to the dictionaries (app/i18n/messages/resultPages.en.ts).
  assert.match(await readFile(new URL("../app/i18n/messages/resultPages.en.ts", import.meta.url), "utf8"), /"inspect\.tab\.artifacts": "Artifacts & provenance"/);
  assert.match(page, /Raw VALUE residual/);
  assert.match(page, /Compatibility adjustment/);
  assert.match(page, /Market replay/);
  assert.match(page, /runtime\.market_trace_level/);
  assert.match(page, /Estimated persisted output/);
  assert.match(page, /Free-space reserve/);
  assert.match(replayExport, /\/replay-exports/);
  assert.match(replayExport, /status_url/);
  assert.match(traceCoverage, /Bid-level replay was not recorded/);
  assert.match(traceCoverage, /Create a new Study revision/);
  // P1 W2: the sidebar labels moved to the dictionaries (app/i18n/en.ts).
  const dictionary = await readFile(new URL("../app/i18n/en.ts", import.meta.url), "utf8");
  assert.match(dictionary, /VRE & curtailment/);
  assert.match(dictionary, /Network & redispatch/);
  // P1 W4b: the Data, Modules and Extensions wording moved to app/i18n/pages/*.en.ts;
  // W4c: the result pages' wording (market replay title) to app/i18n/messages/resultPages.en.ts.
  const pageWording = [page, ...(await Promise.all(["../app/i18n/pages/modules.en.ts", "../app/i18n/pages/data.en.ts", "../app/i18n/messages/resultPages.en.ts"].map((file) => readFile(new URL(file, import.meta.url), "utf8"))))].join("\n");
  assert.match(pageWording, /Install a model module/);
  assert.match(pageWording, /executable Python code/);
  assert.match(pageWording, /Install a VALUE data pack/);
  assert.match(page, /value\.data-bundle\/v1/);
  assert.match(page, /role="progressbar"/);
  assert.match(pageWording, /Cancel upload/);
  assert.match(pageWording, /Replay bids, then follow the dispatched system/);
  assert.match(page, /available = accepted \+ unused/i);
  assert.match(page, /Scientific scenario/);
  assert.match(page, /Reproduction gate/);
  assert.match(page, /retained VALUE numerical difference is expected/);
  assert.match(page, /Recovery: annual boundaries/);
  assert.match(page, /(?:id: |navView\()"learn"/);
  assert.match(learn, /descriptor\.scientific_boundary\.label/);
  assert.match(learn, /Replace the data/);
  assert.match(learn, /Replace modules/);
  assert.match(page, /peak memory/);
  assert.match(server, /gridform_core\.catalog/);
  assert.match(server, /sha256/);
  assert.match(server, /safe_run_artifact/);
  assert.match(server, /query_market_table/);
  assert.match(server, /query_dispatch_timeline/);
  assert.match(server, /query_auction_view/);
  assert.match(server, /query_vre_curtailment_summary/);
  assert.match(server, /query_zonal_annual_brief/);
  assert.match(server, /export_zonal_results/);
  assert.match(server, /install_module_bundle/);
  assert.match(server, /X-VALUE-Executable-Trust/);
  assert.match(server, /install_data_bundle/);
  assert.match(server, /X-VALUE-Data-Rights/);
  assert.doesNotMatch(server, /Desktop|discover_model|legacy_runner/);
  assert.doesNotMatch(server, /scheme-c-authoritative-exact\/v1|scheme-c-project-composed\/v1/);
  assert.match(runner, /run_project_application/);
  assert.match(application, /resolution_graph\.implementations_by_slot/);
  assert.match(application, /registry\.resolve_selection\(\s*selected,/);
  assert.match(application, /selected_extensions=selected_extensions/);
  assert.match(application, /extension_parameters=dict\(project\.get\("extension_parameters"\)/);
  assert.match(application, /available_data_roles=pack_selection\.available_data_roles/);
  assert.doesNotMatch(application, /scheme_c_1000twh\.modular_run|SchemeCReplayData/);
  assert.match(orchestrator, /self\.psm\.run/);
  assert.match(orchestrator, /module\.decide/);
  assert.match(network, /National ahead market/);
  assert.match(network, /Final physical redispatch/);
  assert.match(network, /computational corridors/i);
  assert.match(network, /not a security analysis/i);
  assert.match(network, /Observed chronology, not statistical LOLE/i);
  assert.match(network, /Rerun as copperplate/);
  assert.match(network, /Demand authority/);
  assert.match(network, /VRE curtailment attribution/);
  assert.match(network, /curtailment-detail/);
  assert.match(waterfall, /Forecast added/);
  assert.match(waterfall, /Forecast avoided/);
  assert.match(waterfall, /Redispatch added/);
  assert.match(waterfall, /Redispatch avoided/);
  assert.match(waterfall, /Final VRE curtailment/);
  assert.match(page, /vre_curtailment_mwh/);
  assert.match(page, /vre_curtailment_rate/);
  assert.match(page, /redispatch_net_impact_mwh/);
  assert.match(page, /network_pack_absolute_demand/);
  assert.match(page, /Advanced solver settings/);
  // RR-1 (2), D-W3-13: the built-in solver badge reads "Built-in v4 default settings" (studies.solver.builtin) since the v4 policy.
  assert.match(page, /"studies\.solver\.builtin": "Built-in v4 default settings"/);
  assert.match(page, /t\("studies\.solver\.builtin"\)/);
  assert.match(page, /Use custom solver settings/);
  assert.match(page, /Saving custom solver settings creates a new study revision and removes the built-in solver-validated label until the selected stack passes the validation gates\./);
  assert.match(page, /Immutable platform execution ceilings/);
  assert.match(network, /Solver validation summary/);
  assert.match(network, /Built-in validated baseline/);
  assert.match(network, /Solver stack not yet validated/);
  assert.match(network, /Custom contract — not yet solver validated/);
  assert.match(network, /Export solver diagnostics/);
  assert.match(network, /Completed with numerical warning/);
  assert.match(network, /重新以铜板模式运行/);
  assert.doesNotMatch(network, /zonal price/i);
});

test("launcher removes only identified stale listeners and binds IPv4", async () => {
  const launcher = await readFile(new URL("../scripts/start-local.ps1", import.meta.url), "utf8");
  assert.match(launcher, /Stop-StaleVALUEListener/);
  assert.match(launcher, /backend\\\.server\.\*--port/);
  assert.match(launcher, /serve-value-ui\.mjs/);
  assert.match(launcher, /"--host", "127\.0\.0\.1", "--port"/);
  // P0-1 S4: the gateway learns the API origin after --port; the launcher never handles the session token.
  assert.match(launcher, /"--port", \$frontendPort, "--api-origin", "http:\/\/127\.0\.0\.1:8766"/);
  assert.doesNotMatch(launcher, /X-VALUE-Session|api-session-/i);
});
