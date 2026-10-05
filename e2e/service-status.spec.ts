import { test, expect } from "@playwright/test";

// P0-3 S8 / spec 5: a degraded backend is shown in the rail, the page stays
// usable, and Runs still running in the background are announced.
const run = {
  id: "bg-run", project_id: "demo", project_name: "Background fixture", mode: "full", status: "running",
  current_stage: "Computing year 2026 (period-level progress not reported by this model)", completed_years: 1, total_years: 2,
  updated_at: "2026-10-05T00:00:00+01:00", results: [], worker_liveness: "lost",
};
const workspace = {
  architecture_version: "value.contracts/v2", modules: [], dataset_slots: [],
  projects: [{ id: run.project_id, name: run.project_name, data_pack_id: "fixture", start_year: 2025, end_year: 2026, modules: {}, updated_at: run.updated_at }],
  data_packs: [{ id: "fixture", name: "Fixture", country: "GB", timezone: "Europe/London", bindings: {}, required_count: 0, bound_required_count: 0, valid_required_count: 0, binding_issues: {}, complete: true }],
  runs: [run], runtime: { python: "3.10.11", compatible: true, selected_capability: "value-native" },
};

test("a degraded health status and a lost worker are explained without hiding the page", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    let body: unknown = { error: "unmocked API" };
    let status = 200;
    if (url.endsWith("/api/workspace")) body = workspace;
    else if (url.endsWith("/api/health")) body = { ok: true, status: "degraded", degraded_reasons: [{ code: "GF_MODULE_QUARANTINED", count: 1 }] };
    else if (url.endsWith(`/api/runs/${run.id}`)) body = run;
    else status = 404;
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/?view=run&study=demo&run=bg-run");
  await expect(page.locator(".service")).toContainText("Backend degraded");
  await expect(page.locator(".service")).toContainText("GF_MODULE_QUARANTINED");
  await expect(page.getByRole("button", { name: /1 Run running in background/ })).toBeVisible();
  await expect(page.getByText("VALUE lost contact with this Run's worker", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark as lost" })).toBeEnabled();
  await page.getByRole("button", { name: /Market replay/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Market replay" })).toBeVisible();
});

test("failed refreshes show degraded with a retry, and the last workspace stays readable", async ({ page }) => {
  let failing = false;
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/api/workspace") && failing) { await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "boom", error_code: "GF_INTERNAL" }) }); return; }
    const body = url.endsWith("/api/workspace") ? workspace : url.endsWith("/api/health") ? { ok: true, status: "ok", degraded_reasons: [] } : url.endsWith(`/api/runs/${run.id}`) ? run : { error: "unmocked" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/?view=run&study=demo&run=bg-run");
  await expect(page.locator(".service")).toContainText("Python 3.10.11");
  failing = true;
  // The active Run makes the page poll; the failed poll turns the rail amber.
  await expect(page.locator(".service")).toContainText("Backend degraded", { timeout: 10_000 });
  await expect(page.locator(".service").getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Runs: Launch and compare/ })).toBeEnabled();
  await expect(page.getByText("Background fixture").first()).toBeVisible();
});
