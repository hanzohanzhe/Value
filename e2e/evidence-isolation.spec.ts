import { expect, test } from "@playwright/test";
import { VALUE_101_FALLBACK } from "../app/features/learn/value101";

test("late planning evidence cannot replace the current Run filter", async ({ page }) => {
  const writes: string[] = [], errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let releaseOld!: () => void, oldStarted!: () => void, oldFinished!: () => void;
  const delayed = new Promise<void>((resolve) => { releaseOld = resolve; });
  const started = new Promise<void>((resolve) => { oldStarted = resolve; });
  const finished = new Promise<void>((resolve) => { oldFinished = resolve; });
  const run = { id: "audit-fixture", project_id: "audit-study", project_name: "Audit fixture",
    mode: "full", status: "completed", current_stage: "Completed", results: [], modules: {},
    completed_years: 1, total_years: 1, updated_at: "2026-10-02T00:00:00Z" };
  const project = (name: string) => ({ project_id: name, name, source: "fixture", technology: "wind",
    capacity_mw: 10, region: "GB", development_stage: "construction", status: "active",
    expected_completion_year: 2025, outcome: "active" });
  const planningPage = (name: string) => ({ total: 1, limit: 25, offset: 0, items: [project(name)] });

  await page.route("**/api/**", async (route) => {
    const request = route.request(), url = new URL(request.url());
    let status = 200, body: unknown = {};
    if (request.method() !== "GET") {
      // No write is forwarded to the real service, including a model launch.
      writes.push(url.pathname);
      await route.fulfill({ status: 405, json: { error: "Read-only fixture" } });
      return;
    }
    if (url.pathname === "/api/workspace") body = {
      architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [],
      projects: [], data_packs: [], module_installations: [], extension_installations: [], study_trash: [],
      runs: [run], runtime: { python: "3.10", compatible: true, capabilities: {} },
    };
    else if (url.pathname === "/api/parameters") body = { parameters: [] };
    else if (url.pathname === "/api/tutorials/value-101") body = VALUE_101_FALLBACK;
    else if (url.pathname === `/api/runs/${run.id}`) body = run;
    else if (url.pathname === `/api/runs/${run.id}/planning/projects`) {
      if (!url.searchParams.get("search")) {
        oldStarted();
        await delayed;
        await route.fulfill({ status: 200, json: planningPage("Old planning response") }).catch(() => {});
        oldFinished();
        return;
      }
      body = planningPage("Current filtered evidence");
    }
    else if (url.pathname === `/api/runs/${run.id}/planning/events`) body = { total: 0, limit: 25, offset: 0, items: [] };
    else { status = 404; body = { error: "Evidence not recorded in fixture" }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }).catch(() => {});
  });

  try {
    await page.goto(`/?view=audit&study=${run.project_id}&run=${run.id}`);
    await started;
    const heading = page.getByRole("heading", { name: "See what changed and why", exact: true });
    await expect(heading).toBeVisible();
    const search = page.getByRole("textbox", { name: "Search name, ID, technology or region", exact: true });
    await search.fill("current");
    const planning = page.locator(".audit-stack table").first();
    await expect(planning).toContainText("Current filtered evidence");
    await expect(planning).not.toContainText("Old planning response");

    releaseOld();
    await finished;
    // Let the released handler and the next rendering turn finish before the
    // final assertion. An aborted old response must never restore old rows.
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await expect(search).toHaveValue("current");
    await expect(planning).toContainText("Current filtered evidence");
    await expect(planning).not.toContainText("Old planning response");
    await expect(page.locator(".audit-tabs [role=tab][aria-selected=true]")).toHaveText("planning");
    expect(writes).toEqual([]);
    expect(errors).toEqual([]);
  } finally {
    releaseOld();
  }
});
