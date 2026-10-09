import { expect, test } from "@playwright/test";
import { VALUE_101_FALLBACK } from "../app/features/learn/value101";

test("a delayed comparison cannot replace the newly selected pair or restore a controlled claim", async ({ page }) => {
  const errors: string[] = []; const writes: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let releaseOld!: () => void; let oldStarted!: () => void;
  const started = new Promise<void>((resolve) => { oldStarted = resolve; });
  const delayed = new Promise<void>((resolve) => { releaseOld = resolve; });
  const runs = ["A", "B", "C"].map((id) => ({ id, project_id: "study", project_name: `Run ${id}`, mode: "full", status: "completed", results: [], completed_years: 1, total_years: 1, modules: {}, run_policy: { start_year: 2030, end_year: 2030, periods_per_year: 17520 } }));
  const comparison = (ids: string[]) => ({ schema_version: "value.run-comparison/v1", run_ids: ids, changed_dimensions: {}, metric_deltas_allowed: false, clean_storage_policy_comparison: false, comparison_scope: "annual_scientific", annual_metrics_withheld: false, storage_pricing_interpretation: "recorded_identity_unknown", causal_claim_allowed: false, warning: `Evidence for ${ids.join("+")}`, network_cost_attribution_allowed: false, network_comparison: { reason_code: "comparison_eligibility_artifact_missing", demand_authority_modes: [] }, annual_comparison: [], comparison_review: { schema_version: "value.comparison-review/v1", status: "unknown", evidence_complete: false, isolated_change_allowed: false, dimensions: Object.fromEntries(["data", "method", "config", "years", "scope"].map((name) => [name, { status: "unknown", values: ids.map(() => null) }])), changed_dimensions: [], unknown_dimensions: ["data", "method", "config", "years", "scope"], warning: "Missing frozen identity" } });
  await page.route("**/api/**", async (route) => {
    const request = route.request(); const url = new URL(request.url()); let body: unknown = {}; let status = 200;
    if (request.method() !== "GET") { writes.push(url.pathname); status = 404; }
    else if (url.pathname === "/api/workspace") body = { architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [], projects: [], runs, data_packs: [], module_installations: [], extension_installations: [], study_trash: [], runtime: { python: "3.10", compatible: true, capabilities: {} } };
    else if (url.pathname === "/api/parameters") body = { parameters: [] };
    else if (url.pathname === "/api/tutorials/value-101") body = VALUE_101_FALLBACK;
    else if (url.pathname === "/api/comparisons") {
      const ids = (url.searchParams.get("runs") ?? "").split(",");
      if (ids.join(",") === "A,B") { oldStarted(); await delayed; }
      body = comparison(ids);
    } else { status = 404; body = { error: "Not recorded in fixture" }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }).catch(() => {});
  });
  // W4c (spec 5.1/6.6): the comparison has its own page; the Run centre no longer embeds it.
  await page.goto("/compare");
  const panel = page.locator(".comparison-workspace");
  await panel.getByRole("checkbox", { name: /Run A/ }).check();
  await panel.getByRole("checkbox", { name: /Run B/ }).check();
  await started;
  await panel.getByRole("checkbox", { name: /Run B/ }).uncheck();
  await panel.getByRole("checkbox", { name: /Run C/ }).check();
  await expect(panel).toContainText("Evidence for A+C");
  releaseOld();
  await expect(panel).not.toContainText("Evidence for A+B");
  await expect(panel.getByLabel("Identity check before comparison")).toContainText("cannot confirm that everything else is the same");
  await panel.getByRole("checkbox", { name: /Run C/ }).uncheck();
  // R-4 (P1-polish): the export actions sit in the page header, outside the comparison panel.
  await expect(page.getByRole("button", { name: "Export JSON" })).toBeDisabled();
  expect(errors).toEqual([]); expect(writes).toEqual([]);
});

// AF3-1 (DECISIONS A23): deltas are gated per metric; a withheld metric states its reason.
test("annual deltas are shown per metric and a withheld metric states its reason", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const runs = ["A", "B"].map((id) => ({ id, project_id: "study", project_name: `Run ${id}`, mode: "two_year", status: "completed", results: [], completed_years: 2, total_years: 2, modules: {}, run_policy: { start_year: 2025, end_year: 2026, periods_per_year: 17520 } }));
  const same = (value: unknown) => ({ status: "same", values: [value, value] });
  const metric = (id: string, unit: string, base: number, other: number, shown: boolean) => [
    { run_id: "A", value: base, unit, definition_id: `def.${id}`, delta_from_base: shown ? 0 : null, percentage_delta_from_base: shown ? 0 : null },
    { run_id: "B", value: other, unit, definition_id: `def.${id}`, delta_from_base: shown ? other - base : null, percentage_delta_from_base: shown ? (other - base) / base * 100 : null },
  ];
  const curtailmentReason = "VRE-curtailment differences need matching, reconciled curtailment-attribution evidence in every Run (module does not provide counterfactual snapshot).";
  const body = {
    schema_version: "value.run-comparison/v1", run_ids: ["A", "B"], changed_dimensions: {}, changed_dimension_details: {},
    metric_deltas_allowed: false, clean_storage_policy_comparison: true, comparison_scope: "annual_scientific", annual_metrics_withheld: false,
    storage_pricing_interpretation: "controlled", causal_claim_allowed: true, network_cost_attribution_allowed: false,
    network_comparison: { reason_code: "comparison_eligibility_artifact_missing", demand_authority_modes: [] },
    metric_delta_gates: {
      cem_system_cost_gbp: { allowed: true, reason_code: null, definitions: [], reason: null },
      vre_curtailment_mwh: { allowed: false, reason_code: "module_does_not_provide_counterfactual_snapshot", definitions: [], reason: curtailmentReason },
    },
    withheld_metric_deltas: ["vre_curtailment_mwh"],
    annual_comparison: [{ year: 2026, metrics: { cem_system_cost_gbp: metric("cost", "GBP", 1000, 1100, true), vre_curtailment_mwh: metric("curtailment", "MWh", 50, 60, false) } }],
    comparison_review: { schema_version: "value.comparison-review/v1", status: "verified", evidence_complete: true, isolated_change_allowed: true, dimensions: Object.fromEntries(["data", "method", "config", "years", "scope"].map((name) => [name, same(name)])), changed_dimensions: [], unknown_dimensions: [], warning: null },
  };
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url()); let payload: unknown = {}; let status = 200;
    if (url.pathname === "/api/workspace") payload = { architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [], projects: [], runs, data_packs: [], module_installations: [], extension_installations: [], study_trash: [], runtime: { python: "3.10", compatible: true, capabilities: {} } };
    else if (url.pathname === "/api/parameters") payload = { parameters: [] };
    else if (url.pathname === "/api/tutorials/value-101") payload = VALUE_101_FALLBACK;
    else if (url.pathname === "/api/comparisons") payload = body;
    else { status = 404; payload = { error: "Not recorded in fixture" }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) }).catch(() => {});
  });
  // W4c (spec 5.1/6.6): the comparison has its own page; the Run centre no longer embeds it.
  await page.goto("/compare");
  const panel = page.locator(".comparison-workspace");
  await panel.getByRole("checkbox", { name: /Run A/ }).check();
  await panel.getByRole("checkbox", { name: /Run B/ }).check();
  await expect(panel.locator(".comparison-withheld-summary")).toContainText("Deltas are withheld for 1 of 2 metrics (VRE curtailment (MWh))");
  await panel.locator(".comparison-years summary", { hasText: "2026" }).click();
  const cost = panel.locator(".comparison-metrics article", { hasText: "CEM system cost (GBP)" });
  await expect(cost.locator("em")).toHaveCount(2);
  await expect(cost).not.toContainText("Delta withheld");
  const curtailment = panel.locator(".comparison-metrics article", { hasText: "VRE curtailment (MWh)" });
  await expect(curtailment.locator("em")).toHaveCount(0);
  await expect(curtailment.locator(".comparison-metric-withheld")).toHaveText(`Delta withheld: ${curtailmentReason}`);
  await expect(panel).not.toContainText("所需的定义");
  expect(errors).toEqual([]);
});

// EM-低1 (W4c, spec 6.6): the reference Run is chosen in a selector (default:
// the earliest-created Run here), is sent first so every delta is measured
// against it, is kept in the URL (?runs=&ref=) and is named in the CSV.
test("the reference Run is chosen, sent first, kept in the URL and named in the CSV export", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const runs = [["A", "2026-10-02T10:00:00+01:00"], ["B", "2026-10-01T10:00:00+01:00"]].map(([id, created]) => ({ id, project_id: "study", project_name: `Run ${id}`, mode: "full", status: "completed", created_at: created, results: [], completed_years: 1, total_years: 1, modules: {}, run_policy: { start_year: 2030, end_year: 2030, periods_per_year: 17520 } }));
  const requested: string[] = [];
  const comparison = (ids: string[]) => ({ schema_version: "value.run-comparison/v1", run_ids: ids, changed_dimensions: {}, metric_deltas_allowed: true, clean_storage_policy_comparison: false, comparison_scope: "annual_scientific", annual_metrics_withheld: false, storage_pricing_interpretation: "recorded_identity_unknown", causal_claim_allowed: false, network_cost_attribution_allowed: false, network_comparison: { reason_code: "comparison_eligibility_artifact_missing", demand_authority_modes: [] }, annual_comparison: [], comparison_review: { schema_version: "value.comparison-review/v1", status: "unknown", evidence_complete: false, isolated_change_allowed: false, dimensions: Object.fromEntries(["data", "method", "config", "years", "scope"].map((name) => [name, { status: "unknown", values: ids.map(() => null) }])), changed_dimensions: [], unknown_dimensions: [], warning: null } });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url()); let payload: unknown = {}; let status = 200;
    if (url.pathname === "/api/workspace") payload = { architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [], projects: [], runs, data_packs: [], module_installations: [], extension_installations: [], study_trash: [], runtime: { python: "3.10", compatible: true, capabilities: {} } };
    else if (url.pathname === "/api/parameters") payload = { parameters: [] };
    else if (url.pathname === "/api/tutorials/value-101") payload = VALUE_101_FALLBACK;
    else if (url.pathname === "/api/comparisons" && url.searchParams.get("format") === "csv") {
      await route.fulfill({ status: 200, contentType: "text/csv", body: "\uFEFFschema_version,value.run-comparison/v1\r\ncomparison_scope,annual_scientific\r\nrun_id,year,metric_id,value\r\n" }).catch(() => {});
      return;
    } else if (url.pathname === "/api/comparisons") { const ids = (url.searchParams.get("runs") ?? "").split(","); requested.push(ids.join(",")); payload = comparison(ids); }
    else { status = 404; payload = { error: "Not recorded in fixture" }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) }).catch(() => {});
  });
  await page.goto("/compare");
  const panel = page.locator(".comparison-workspace");
  await panel.getByRole("checkbox", { name: /Run A/ }).check();
  await panel.getByRole("checkbox", { name: /Run B/ }).check();
  const reference = panel.getByRole("combobox", { name: "Reference Run" });
  // Default: the earliest-created Run (B), sent first.
  await expect(reference).toHaveValue("B");
  await expect(panel).toContainText("Reference Run: Run B (B). Every delta (+ and %) is measured against it.");
  await expect.poll(() => requested.at(-1)).toBe("B,A");
  await expect(page).toHaveURL(/\/compare\?(?:.*&)?runs=A%2CB&ref=B(?:&|$)/);
  await reference.selectOption("A");
  await expect.poll(() => requested.at(-1)).toBe("A,B");
  await expect(page).toHaveURL(/\/compare\?(?:.*&)?runs=A%2CB&ref=A(?:&|$)/);
  await expect(panel.locator(".comparison-reference")).toContainText("measured against Run A (A), the reference Run");
  await page.reload();
  await expect(panel.getByRole("combobox", { name: "Reference Run" })).toHaveValue("A");
  await expect(panel.getByRole("checkbox", { name: /Run A/ })).toBeChecked();
  await expect.poll(() => requested.at(-1)).toBe("A,B");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("value-run-comparison.csv");
  const text = await (await import("node:fs/promises")).readFile(await file.path(), "utf8");
  expect(text).toContain("schema_version,value.run-comparison/v1\r\nreference_run_id,A\r\ncomparison_scope");
  expect(errors).toEqual([]);
});
