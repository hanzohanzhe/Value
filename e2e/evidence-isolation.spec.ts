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
    // F3-19 (W4c, spec 6.6): the search is requested on Enter or Apply, not while typing.
    await search.press("Enter");
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
    await expect(page.locator(".inspect-tabs [role=tab][aria-selected=true]")).toHaveText("Planning");
    await expect(page).toHaveURL(/[?&]q=current(?:&|$)/);
    expect(writes).toEqual([]);
    expect(errors).toEqual([]);
  } finally {
    releaseOld();
  }
});

// F3-19 (W4c, spec 6.6): typing requests nothing; Enter applies the search
// (also written to ?q=); lifecycle events page on their own offset.
test("Inspect searches on Enter only and pages lifecycle events separately", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const run = { id: "audit-fixture", project_id: "audit-study", project_name: "Audit fixture", mode: "full", status: "completed", current_stage: "Completed", results: [], modules: {}, completed_years: 1, total_years: 1, updated_at: "2026-10-02T00:00:00Z" };
  const projects: string[] = [], events: string[] = [];
  const event = (sequence: number) => ({ sequence, project_id: `p-${sequence}`, year: 2025, event_type: "admitted", reason_code: "" });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url()); let body: unknown = {}; let status = 200;
    if (url.pathname === "/api/workspace") body = { architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [], projects: [], data_packs: [], module_installations: [], extension_installations: [], study_trash: [], runs: [run], runtime: { python: "3.10", compatible: true, capabilities: {} } };
    else if (url.pathname === "/api/parameters") body = { parameters: [] };
    else if (url.pathname === "/api/tutorials/value-101") body = VALUE_101_FALLBACK;
    else if (url.pathname === `/api/runs/${run.id}`) body = run;
    else if (url.pathname === `/api/runs/${run.id}/planning/projects`) { projects.push(url.search); body = { total: 1, limit: 25, offset: 0, items: [{ project_id: "x", name: "Project X", source: "f", technology: "wind", capacity_mw: 1, region: "GB", development_stage: "construction", status: "active", outcome: "active" }] }; }
    else if (url.pathname === `/api/runs/${run.id}/planning/events`) { events.push(url.searchParams.get("offset") ?? ""); const offset = Number(url.searchParams.get("offset") ?? 0); body = { total: 30, limit: 25, offset, items: Array.from({ length: offset ? 5 : 25 }, (_, index) => event(offset + index + 1)) }; }
    else { status = 404; body = { error: "Evidence not recorded in fixture" }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }).catch(() => {});
  });
  await page.goto(`/inspect?study=${run.project_id}&run=${run.id}`);
  await expect(page.getByText("30 recorded events")).toBeVisible();
  await expect.poll(() => projects.length).toBe(1);
  const search = page.getByRole("textbox", { name: "Search name, ID, technology or region", exact: true });
  await search.pressSequentially("wind", { delay: 30 });
  await page.waitForTimeout(400);
  expect(projects.length).toBe(1);
  await search.press("Enter");
  await expect.poll(() => projects.at(-1)).toContain("search=wind");
  await expect(page).toHaveURL(/[?&]q=wind(?:&|$)/);
  // The events' Next page moves only the event offset.
  const eventsPanel = page.locator("section.panel", { hasText: "How projects changed" });
  await eventsPanel.getByRole("button", { name: "Next" }).click();
  await expect.poll(() => events.at(-1)).toBe("25");
  await expect(eventsPanel.getByRole("cell", { name: "p-26" })).toBeVisible();
  expect(projects.every((query) => !query.includes("offset=25"))).toBe(true);
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Search name, ID, technology or region", exact: true })).toHaveValue("wind");
  await expect.poll(() => projects.at(-1)).toContain("search=wind");
  expect(errors).toEqual([]);
});
