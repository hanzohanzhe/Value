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
  await page.goto("/?view=run");
  const panel = page.locator(".comparison-workspace");
  await panel.getByRole("checkbox", { name: /Run A/ }).check();
  await panel.getByRole("checkbox", { name: /Run B/ }).check();
  await started;
  await panel.getByRole("checkbox", { name: /Run B/ }).uncheck();
  await panel.getByRole("checkbox", { name: /Run C/ }).check();
  await expect(panel).toContainText("Evidence for A+C");
  releaseOld();
  await expect(panel).not.toContainText("Evidence for A+B");
  await expect(panel.getByLabel("比较前身份核对")).toContainText("无法确认其他条件相同");
  await panel.getByRole("checkbox", { name: /Run C/ }).uncheck();
  await expect(panel.getByRole("button", { name: "Export JSON" })).toBeDisabled();
  expect(errors).toEqual([]); expect(writes).toEqual([]);
});
