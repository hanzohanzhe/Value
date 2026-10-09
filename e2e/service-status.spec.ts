import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { openRunSection, railLink } from "./workspace-nav";

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
    else if (url.endsWith("/api/health")) body = { ok: true, frontend_contract_version: "value.expanded-frontend/v1", status: "degraded", degraded_reasons: [{ code: "GF_MODULE_QUARANTINED", count: 1 }] };
    else if (url.endsWith(`/api/runs/${run.id}`)) body = run;
    else status = 404;
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/?view=run&study=demo&run=bg-run");
  await expect(page.locator(".rail .service")).toContainText("Backend degraded");
  await expect(page.locator(".rail .service")).toContainText("GF_MODULE_QUARANTINED");
  await expect(page.getByRole("button", { name: /1 Run running in background/ })).toBeVisible();
  await expect(page.getByText("VALUE lost contact with this Run's worker", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark as lost" })).toBeEnabled();
  // Spec 9.7: the new components pass axe critical/serious checks.
  const scan = await new AxeBuilder({ page }).include(".run-lifecycle-callout").include(".background-runs").include(".service").analyze();
  expect(scan.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
  await openRunSection(page, "Market replay");
  await expect(page.getByRole("heading", { level: 1, name: "Market replay" })).toBeVisible();
});

test("failed refreshes show degraded with a retry, and the last workspace stays readable", async ({ page }) => {
  let failing = false;
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/api/workspace") && failing) { await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "boom", error_code: "GF_INTERNAL" }) }); return; }
    const body = url.endsWith("/api/workspace") ? workspace : url.endsWith("/api/health") ? { ok: true, frontend_contract_version: "value.expanded-frontend/v1", status: "ok", degraded_reasons: [] } : url.endsWith(`/api/runs/${run.id}`) ? run : { error: "unmocked" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/?view=run&study=demo&run=bg-run");
  await expect(page.locator(".rail .service")).toContainText("Python 3.10.11");
  failing = true;
  // The active Run makes the page poll; the failed poll turns the rail amber.
  await expect(page.locator(".rail .service")).toContainText("Backend degraded", { timeout: 10_000 });
  await expect(page.locator(".rail .service").getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(railLink(page, "Runs")).toBeEnabled();
  await expect(page.getByText("Background fixture").first()).toBeVisible();
});

// P0-2 S9 / spec 6: a quarantined module is named on the Modules page and can be
// disabled after two confirmations (the module and the still-running Run).
test("the quarantine panel disables a module after confirming pending Runs", async ({ page }) => {
  const quarantine = { schema_version: "value.module-quarantine/v1", status: "degraded", entries: [{ kind: "module", id: "my-storage-module", version: "1.2.0", manifest_file: "installed/my-storage-module/value-module.json", error_code: "GF_MODULE_IMPORT_FAILED", error_type: "ModuleNotFoundError", message: "Import failed: ModuleNotFoundError: No module named 'scipy_extra'\nTraceback: /home/alice/x.py", corrective_action: "Disable module my-storage-module in Modules" }] };
  const disableBodies: string[] = [];
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/api/modules/my-storage-module/disable")) {
      const body = route.request().postData() ?? "";
      disableBodies.push(body);
      if (!body.includes("confirm_pending_runs")) {
        await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "Runs have not finished: 1 run(s) already running (bg-run) keep their code but could not be resumed after the change. Confirm to change installed modules anyway.", error_code: "GF_MODULE_LIFECYCLE_RUNS_PENDING" }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, installation: { module_id: "my-storage-module", enabled: false } }) });
      return;
    }
    const body = url.endsWith("/api/workspace") ? { ...workspace, module_quarantine: quarantine } : url.endsWith("/api/health") ? { ok: true, frontend_contract_version: "value.expanded-frontend/v1", status: "degraded", degraded_reasons: [{ code: "GF_MODULE_IMPORT_FAILED", count: 1 }] } : url.endsWith(`/api/runs/${run.id}`) ? run : { error: "unmocked" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  const dialogs: string[] = [];
  page.on("dialog", (dialog) => { dialogs.push(dialog.message()); void dialog.accept(); });
  await page.goto("/?view=models");
  const panel = page.locator(".module-quarantine-panel");
  await expect(panel).toContainText("1 external module quarantined");
  await expect(panel).toContainText("my-storage-module 1.2.0");
  await expect(panel).toContainText("GF_MODULE_IMPORT_FAILED");
  await expect(panel).not.toContainText("/home/");
  await panel.getByRole("button", { name: "Disable" }).click();
  await expect(page.getByRole("status").filter({ hasText: "my-storage-module is disabled" })).toBeVisible();
  expect(dialogs[0]).toBe("Disable my-storage-module? Studies that use it will need another module before they can run.");
  expect(dialogs[1]).toContain("Runs have not finished");
  expect(disableBodies).toHaveLength(2);
  expect(JSON.parse(disableBodies[1]).confirm_pending_runs).toBe(true);
  const scan = await new AxeBuilder({ page }).include(".module-quarantine-panel").analyze();
  expect(scan.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
  // Spec 9.8: at 375 px the new panel fits its own width (no horizontal scroll inside it).
  await page.setViewportSize({ width: 375, height: 800 });
  const overflow = await panel.evaluate((element) => element.scrollWidth - element.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

// Review response (P0-3 S4, spec 5): Mark as lost asks for the exact run ID, as
// Delete does, and sends only what the user typed to the API's confirmation gate.
test("Mark as lost sends nothing until the exact run ID is typed", async ({ page }) => {
  const markLostBodies: string[] = [];
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith(`/api/runs/${run.id}/mark-lost`)) {
      markLostBodies.push(route.request().postData() ?? "");
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
      return;
    }
    const body = url.endsWith("/api/workspace") ? workspace : url.endsWith("/api/health") ? { ok: true, frontend_contract_version: "value.expanded-frontend/v1", status: "ok", degraded_reasons: [] } : url.endsWith(`/api/runs/${run.id}`) ? run : { error: "unmocked" };
    await route.fulfill({ status: url.endsWith("/api/workspace") || url.endsWith("/api/health") || url.endsWith(`/api/runs/${run.id}`) ? 200 : 404, contentType: "application/json", body: JSON.stringify(body) });
  });
  const answers = ["bg-ru", run.id];
  const prompts: string[] = [];
  page.on("dialog", (dialog) => { prompts.push(`${dialog.type()}: ${dialog.message()}`); void dialog.accept(answers.shift() ?? ""); });
  await page.goto("/?view=run&study=demo&run=bg-run");
  const markLost = page.getByRole("button", { name: "Mark as lost" });
  await markLost.click();
  await expect(page.getByText("The Run was not marked lost because the exact ID was not entered.")).toBeVisible();
  expect(markLostBodies).toEqual([]);
  await markLost.click();
  await expect(page.getByText("The Run was marked lost and recorded as failed.", { exact: false })).toBeVisible();
  expect(markLostBodies.map((body) => JSON.parse(body))).toEqual([{ confirm_run_id: "bg-run" }]);
  expect(prompts[0]).toMatch(/^prompt: Mark Run bg-run as lost\?/);
  expect(prompts[0]).toContain("Type the exact run ID to confirm");
});
