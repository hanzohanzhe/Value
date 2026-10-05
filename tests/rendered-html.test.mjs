import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const request = new Request("http://localhost/", { headers: { accept: "text/html" } });
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

test("uses the shared application service and on-demand audit contracts", async () => {
  const [page, server, runner, application, orchestrator, learn, network, waterfall, replayExport, traceCoverage] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../backend/server.py", import.meta.url), "utf8"),
    readFile(new URL("../backend/model_runner.py", import.meta.url), "utf8"),
    readFile(new URL("../gridform_core/application.py", import.meta.url), "utf8"),
    readFile(new URL("../gridform_core/orchestrator.py", import.meta.url), "utf8"),
    readFile(new URL("../app/features/learn/Value101Learn.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/network/NetworkRedispatchView.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/network/CurtailmentWaterfall.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/market/ReplayExportPanel.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/market/TraceCoverageNotice.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(page, /data-packs/);
  assert.match(page, /Allocate variable electricity/i);
  assert.match(page, /startRun/);
  assert.match(page, /startRun\("value_101_day"/);
  const runWorkspace = await readFile(new URL("../app/features/runs/RunWorkspace.tsx", import.meta.url), "utf8");
  assert.match(runWorkspace, /Run selected scope/);
  assert.match(runWorkspace, /startRun\(effectivePreflightMode\)/);
  assert.match(runWorkspace, /checkPreflight\(effectivePreflightMode/);
  assert.match(page, /two_year_smoke/);
  assert.match(page, /Advanced assumptions/);
  assert.match(page, /Planning pipeline/);
  assert.match(page, /onCreateFullReplayRevision=\{createFullReplayRevision\}/);
  assert.doesNotMatch(page, /Re-run with <code>runtime\.market_trace_level = full<\/code>/);
  assert.match(traceCoverage, /Create a new Study revision with Full market replay/);
  assert.match(page, /Artifacts & provenance/);
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
  assert.match(page, /VRE & curtailment/);
  assert.match(page, /Network & redispatch/);
  assert.match(page, /Install a model module/);
  assert.match(page, /executable Python code/);
  assert.match(page, /Install a VALUE data pack/);
  assert.match(page, /value\.data-bundle\/v1/);
  assert.match(page, /role="progressbar"/);
  assert.match(page, /Cancel upload/);
  assert.match(page, /Replay bids, then follow the dispatched system/);
  assert.match(page, /available = accepted \+ unused/i);
  assert.match(page, /Scientific scenario/);
  assert.match(page, /Reproduction gate/);
  assert.match(page, /retained VALUE numerical difference is expected/);
  assert.match(page, /Recovery: annual boundaries/);
  assert.match(page, /id: "learn"/);
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
  assert.match(page, /Built-in default settings/);
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
