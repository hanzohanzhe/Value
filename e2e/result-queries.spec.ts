import { expect, test, type Page } from "@playwright/test";
import { VALUE_101_FALLBACK } from "../app/features/learn/value101";

const run = { id: "query-fixture", project_id: "query-study", project_name: "Query fixture", status: "completed",
  mode: "full", results: [], modules: {}, completed_years: 1, total_years: 1, current_stage: "Completed" };

function queryResponse(url: URL, totalMwh = 7) {
  const resolution = url.searchParams.get("resolution") ?? "annual";
  const requested = url.searchParams.get("source") ?? "auto";
  const kind = requested === "sqlite" ? "sqlite" : "compact";
  const year = url.searchParams.get("year");
  return {
    schema_version: "value.result-query/v1", family: "vre-curtailment", contract_version: "value.vre-curtailment-attribution/v2",
    status: "reconciled", reason_code: null,
    identity: { run_id: run.id, requested_run_id: run.id, recorded_run_id: run.id, study_id: run.project_id,
      study_revision: "r".repeat(64), input_snapshot_id: "query-frozen-snapshot", data_pack_id: "pack",
      network_pack_id: null, initial_state_sha256: null, module_resolution_graph_sha256: "g".repeat(64), module_identities: {} },
    source: { kind, requested, artifact_path: "model-output/query.json", artifact_sha256: "a".repeat(64),
      original_schema_version: "fixture/v1", trace_level: null },
    scope: { resolution, year: year ? Number(year) : null, period_from: null, period_to: null },
    capabilities: { available_resolutions: kind === "sqlite" ? ["annual", "half_hour"] : ["annual"],
      available_dimensions: kind === "sqlite" ? ["year", "period_window"] : ["year"],
      unavailable_dimensions: kind === "compact" ? ["period_window", "zone", "technology"] : ["zone", "technology"] },
    total: 1, limit: 48, offset: Number(url.searchParams.get("offset") ?? 0), count: 1, has_more: false,
    items: [{ year: 2025, period_count: 17520, available_mwh: 100, economic_mwh: 5,
      forecast_added_mwh: 3, forecast_avoided_mwh: 1, redispatch_added_mwh: 2, redispatch_avoided_mwh: 2,
      redispatch_net_mwh: 0, total_mwh: totalMwh, rate: totalMwh / 100,
      identity_residual_mwh: 0, aggregate_tolerance_mwh: 0.0001 }],
  };
}

async function fixture(page: Page, delaySqlite?: { requested: () => void; ready: Promise<void> }) {
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    let body: unknown = {};
    if (request.method() !== "GET" && path !== "/api/projects/resolve-draft") writes.push(path);
    if (path === "/api/workspace") body = {
      architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [],
      module_installations: [], extension_installations: [], study_trash: [], data_packs: [],
      projects: [{ id: run.project_id, name: "Query fixture", data_pack_id: "pack", modules: {}, start_year: 2025, end_year: 2025 }],
      runs: [run], runtime: { python: "3.11", compatible: true },
    };
    else if (path === `/api/runs/${run.id}`) body = run;
    else if (path.endsWith("/results/vre-curtailment")) {
      if (url.searchParams.get("source") === "sqlite" && delaySqlite) {
        delaySqlite.requested(); await delaySqlite.ready;
        body = queryResponse(url, 999);
      } else body = queryResponse(url);
    } else if (path === "/api/tutorials/value-101") body = VALUE_101_FALLBACK;
    else if (path === "/api/parameters") body = { parameters: [] };
    // P1 W2/W3: the interface checks the service contract on /api/health.
    else if (path === "/api/health") body = { ok: true, frontend_contract_version: "value.expanded-frontend/v1", status: "ok", degraded_reasons: [] };
    else if (path.endsWith("/market/vre-summary")) body = { years: [], excess_relationship: "not_recorded", excess_scope: "not_recorded" };
    else if (path.endsWith("/market/capabilities")) body = { years: [], period_summary: false };
    else if (path === "/api/projects/resolve-draft") body = { valid: false, errors: [], warnings: [],
      module_slots: [], compatible_modules: {}, system_domains: [], active_dataset_slots: [],
      data_readiness: { required: 0, available: 0, missing_roles: [] }, maturity: { acknowledgements_required: [] } };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }).catch(() => {});
  });
  await page.goto(`/?view=curtailment&study=${run.project_id}&run=${run.id}`);
  return { writes, errors, panel: page.locator(".result-query:visible") };
}

test("compact annual result keeps provenance and disables unrecorded dimensions", async ({ page }) => {
  const { panel, writes, errors } = await fixture(page);
  await expect(panel).toHaveCount(1);
  await expect(panel.getByRole("heading", { name: "Final VRE curtailment · v2" })).toBeVisible();
  await expect(panel.getByRole("table")).toContainText("7%");
  await expect(panel).toContainText("query-frozen-snapshot");
  await expect(panel).toContainText("g".repeat(64));
  await expect(panel).toContainText("a".repeat(64));
  await expect(panel.getByRole("combobox", { name: "Result resolution" }).locator('option[value="half_hour"]')).toHaveAttribute("disabled", "");
  await expect(panel).toContainText("Unavailable dimensions: period_window, zone, technology");
  await expect(panel.getByRole("columnheader", { name: "Forecast avoided", exact: true })).toBeVisible();
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});

test("late ledger response cannot replace compact selection and missing metrics stay unavailable", async ({ page }) => {
  let release!: () => void, requested!: () => void;
  const ready = new Promise<void>(resolve => { release = resolve; });
  const received = new Promise<void>(resolve => { requested = resolve; });
  const { panel, writes, errors } = await fixture(page, { ready, requested });
  await expect(panel.getByRole("table")).toBeVisible();
  await panel.getByRole("combobox", { name: "Result source" }).selectOption("sqlite");
  await received;
  await panel.getByRole("combobox", { name: "Result source" }).selectOption("compact");
  await expect(panel.getByRole("table")).toContainText("7%");
  release();
  await expect(panel.getByRole("combobox", { name: "Result source" })).toHaveValue("compact");
  await expect(panel.getByRole("table")).not.toContainText("999");
  await page.route("**/results/vre-curtailment?**", async route => {
    const body = queryResponse(new URL(route.request().url()));
    await route.fulfill({ json: { ...body, status: "unavailable", reason_code: "result_artifact_missing", total: 0, count: 0, items: [] } });
  });
  await panel.getByRole("combobox", { name: "Result source" }).selectOption("auto");
  // P0-9 S7 (G1-07): "unavailable" is explained, not shown as an error; red is only for invalid.
  await expect(panel.getByRole("status").filter({ hasText: "result_artifact_missing" })).toContainText("Unavailable");
  await expect(panel).toContainText("result_artifact_missing");
  await expect(panel.locator(".result-query-message.error")).toHaveCount(0);
  await expect(panel.getByRole("table")).toHaveCount(0);
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});
