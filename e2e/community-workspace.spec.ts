import { expect, test, type Page } from "@playwright/test";
import { VALUE_101_FALLBACK } from "../app/features/learn/value101";
import { railLink } from "./workspace-nav";

// RR-1 (3): migrated to the routes of P1 W3 (D-W3-13 ④: the page is the URL
// path, the sidebar entries are links, the Run centre has no context bar) and
// to the state words of R-16.  Every /api route is mocked.

const PATHS = [
  { label: "Reproduce from existing data", path: "reproduce", route: "/journey", heading: "Reproduce from existing data" },
  { label: "Add your new data", path: "data", route: "/journey", heading: "Add your new data" },
  // P1 W4b (R3-22): the path opens the author tools, which are the last section of /modules and /extensions.
  { label: "Edit a module", path: "module", route: "/modules", heading: "Install a model module", target: "module-author-workbench" },
  { label: "Add a new function to VALUE", path: "function", route: "/extensions", heading: "Install a model extension", target: "extension-author-workbench" },
] as const;

const mutableStudy = {
  id: "fixture-study", name: "Workspace Study revision nine", data_pack_id: "mutable-workspace-pack",
  revision_number: 9, revision_sha256: "9".repeat(64), start_year: 2025, end_year: 2034,
  modules: {}, selected_extensions: [], extension_parameters: {}, maturity_acknowledgements: {},
  market_configuration: {}, updated_at: "2026-10-01T00:00:00Z",
};

function pack(id: string) {
  return { id, name: id, country: "SYNTHETIC", timezone: "UTC", bindings: {}, required_count: 0,
    bound_required_count: 0, valid_required_count: 0, binding_issues: {}, complete: true };
}

function run(id: string, identity: string) {
  return {
    id, project_id: mutableStudy.id, project_name: `Recorded ${id}`, mode: "smoke", status: "completed",
    current_stage: "Run completed", completed_years: 1, total_years: 1, updated_at: "2026-10-01T00:00:00Z",
    results: [], modules: {}, input_snapshot_id: identity.repeat(64), input_tree_sha256: identity.repeat(64),
    execution_status: "passed", contract_validation_status: "passed", scientific_validation_status: "not_evaluated",
    diagnostic: { total_periods: 2, years: [2025], annual_economics_published: false },
    run_policy: { label: "Two-period wiring check", total_periods: 2 },
  };
}

const runs = [run("fixture-old-run", "a"), run("fixture-new-run", "b")];
const workspace = {
  architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [],
  projects: [mutableStudy], runs, data_packs: [pack("mutable-workspace-pack"), pack("another-draft-pack")],
  module_installations: [], extension_installations: [], study_trash: [],
  runtime: { python: "3.11", compatible: true, selected_capability: "value-native", capabilities: {} },
};

const resolution = {
  schema_version: "value.study-draft-resolution/v1", frontend_contract_version: "value.frontend/v1",
  valid: true, errors: [], warnings: [], module_slots: [], compatible_modules: {}, system_domains: [],
  active_dataset_slots: [], data_readiness: { required: 0, available: 0, missing_roles: [] },
  effective_extension_parameters: {}, maturity: { acknowledgement_contract: "test", acknowledgements_required: [] },
};

async function mockWorkspace(page: Page, delayedRun?: { id: string; ready: Promise<void> }) {
  const unexpectedWrites: string[] = [];
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body: unknown;
    let status = 200;
    if (request.method() !== "GET" && path !== "/api/projects/resolve-draft") {
      unexpectedWrites.push(`${request.method()} ${path}`);
      status = 405; body = { error: "This browser regression must never start or mutate a model." };
    } else if (path === "/api/workspace") body = workspace;
    else if (path === "/api/parameters") body = { parameters: [] };
    else if (path === "/api/tutorials/value-101") body = VALUE_101_FALLBACK;
    else if (path === "/api/projects/resolve-draft") body = resolution;
    else if (/\/api\/data-workbench\/v1\/(sources|revisions|candidates|bundles)$/.test(path)) {
      const collection = path.split("/").at(-1)!;
      body = { schema_version: `value.data-${collection === "bundles" ? "installed-bundles" : collection}/v1`, [collection]: [] };
    } else {
      const match = path.match(/^\/api\/runs\/([^/]+)(?:\/artifacts\/input-snapshot\/(.+))?$/);
      const selected = runs.find((item) => item.id === match?.[1]);
      if (!selected) { status = 404; body = { error: "No fixture for this read-only request." }; }
      else if (!match?.[2]) body = selected;
      else if (match[2] === "resource-readiness.json") { status = 404; body = { error: "Not recorded." }; }
      else {
        if (delayedRun?.id === selected.id) await delayedRun.ready;
        const old = selected.id === "fixture-old-run";
        if (match[2] === "project.json") body = {
          ...mutableStudy, name: `Frozen ${selected.id}`, data_pack_id: old ? "frozen-old-data-pack" : "frozen-new-data-pack",
          revision_number: old ? 1 : 2, revision_sha256: (old ? "1" : "2").repeat(64),
          market_configuration: { network_pack_id: "frozen-network-overlay" },
        };
        else if (match[2] === "snapshot.json") body = {
          state: "ready", snapshot_id: selected.input_snapshot_id, input_tree_sha256: selected.input_tree_sha256,
          pack_manifest_sha256: (old ? "c" : "d").repeat(64), network_pack_id: "frozen-network-overlay",
          network_pack_manifest_sha256: "e".repeat(64),
        };
        else { status = 404; body = { error: "Unknown frozen artifact." }; }
      }
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  return () => { expect(unexpectedWrites).toEqual([]); expect(pageErrors).toEqual([]); };
}

async function openWorkspace(page: Page, url = "/") {
  await page.goto(url);
  await expect(page.locator(".rail .service")).toContainText("value-native ready");
}

async function expectNoPageOverflow(page: Page) {
  try {
    await expect.poll(() => page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)
      - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  } catch (error) {
    const overflow = await page.evaluate(() => Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => element.getClientRects().length > 0)
      .map((element) => ({ element: `${element.tagName.toLowerCase()}#${element.id}.${String(element.className)}`,
        right: Math.round(element.getBoundingClientRect().right + window.scrollX),
        width: Math.round(element.getBoundingClientRect().width),
        overflowX: getComputedStyle(element).overflowX,
        text: element.innerText?.trim().slice(0, 90),
      }))
      .filter((element) => element.right > document.documentElement.clientWidth + 1)
      .sort((a, b) => b.right - a.right).slice(0, 20));
    await test.info().attach("page-overflow-elements", { body: JSON.stringify({ url: page.url(), overflow }, null, 2), contentType: "application/json" });
    throw error;
  }
}

for (const path of PATHS) {
  test(`community entry ${path.label} opens its working feature`, async ({ page }) => {
    const assertClean = await mockWorkspace(page);
    await openWorkspace(page);
    await expect(page.getByRole("button", { name: path.label, exact: true })).toBeVisible();
    await page.getByRole("button", { name: path.label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`[?&]path=${path.path}(?:&|$)`));
    expect(new URL(page.url()).pathname).toBe(path.route);
    await expect(page.getByRole("heading", { name: path.heading, exact: true })).toBeVisible();
    if ("target" in path) await expect(page.locator(`#${path.target}`)).toBeInViewport();
    // The chosen path stays marked on Home.
    await railLink(page, "Home").click();
    await expect(page.getByRole("button", { name: path.label, exact: true })).toHaveAttribute("aria-pressed", "true");
    assertClean();
  });
}

test("Read me loads the public document, traps keyboard focus and returns focus after close and Escape", async ({ page }) => {
  const assertClean = await mockWorkspace(page);
  await openWorkspace(page);
  const trigger = page.getByRole("button", { name: "Read me", exact: true });
  const dialog = page.getByRole("dialog", { name: "Read me", exact: true });
  await trigger.click();
  await expect(dialog.getByRole("heading", { name: "VALUE Read me", exact: true })).toBeVisible();
  for (const path of PATHS) await expect(dialog.getByRole("cell", { name: path.label, exact: true })).toBeVisible();
  const close = dialog.getByRole("button", { name: "Close Read me", exact: true });
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Tab");
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await close.click();
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.press("Enter");
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  assertClean();
});

test("a Run keeps its frozen revision after draft changes and hides the previous Run during a delayed switch", async ({ page }) => {
  let releaseNewRun!: () => void;
  const ready = new Promise<void>((resolve) => { releaseNewRun = resolve; });
  const assertClean = await mockWorkspace(page, { id: "fixture-new-run", ready });
  await openWorkspace(page, "/?view=run&study=fixture-study&run=fixture-old-run");
  const context = page.getByRole("region", { name: "Selected Run context", exact: true });
  await expect(context).toContainText("frozen-old-data-pack");
  await expect(context.locator(".run-context-sources > span").filter({ hasText: "Frozen Study revision" }).locator("b")).toHaveText("1");
  await expect(context).not.toContainText("mutable-workspace-pack");
  await expect(context).toContainText("2 periods configured");
  await expect(context.locator(".run-context-statuses > span").filter({ hasText: "Scientific validation" })).toContainText("Not evaluated");
  // The draft's data pack is chosen in the top bar of Studies (the draft context).
  await railLink(page, "Studies").click();
  await page.getByRole("combobox", { name: "Selected data pack", exact: true }).selectOption("another-draft-pack");
  // The Run centre lists the Runs; the Run's own page carries the context bar.
  const runPage = () => page.getByRole("navigation", { name: "Pages of this Run" }).getByRole("link", { name: "Annual results", exact: true }).click();
  await railLink(page, "Runs").click();
  await runPage();
  await expect(context).toContainText("frozen-old-data-pack");
  await expect(context).not.toContainText("another-draft-pack");
  await railLink(page, "Runs").click();
  await page.getByRole("combobox", { name: "Selected run", exact: true }).selectOption("fixture-new-run");
  await runPage();
  try {
    await expect(context).toContainText("fixture-new-run");
    await expect(context).toHaveAttribute("aria-busy", "true");
    await expect(context).not.toContainText("frozen-old-data-pack");
  } finally { releaseNewRun(); }
  await expect(context).toContainText("frozen-new-data-pack");
  await expect(context).toHaveAttribute("aria-busy", "false");
  await expect(context.locator(".run-context-sources > span").filter({ hasText: "Frozen Study revision" }).locator("b")).toHaveText("2");
  assertClean();
});

test("an explicitly unavailable Run URL preserves its identity without substituting an existing result", async ({ page }) => {
  const assertClean = await mockWorkspace(page);
  await openWorkspace(page, "/?view=run&study=fixture-study&run=missing-run");
  await expect(page.getByRole("status").filter({ hasText: "no substitute result has been opened" })).toBeVisible();
  const context = page.getByRole("region", { name: "Selected Run context", exact: true });
  await expect(context).toContainText("No Run selected");
  await expect(context).not.toContainText("fixture-old-run");
  await expect(context).not.toContainText("frozen-old-data-pack");
  // The old link is forwarded to the Run's own path, which keeps the unavailable Run.
  expect(new URL(page.url()).pathname).toBe("/runs/missing-run");
  assertClean();
});

test("Data retains the saved Study and an intentional draft choice through reload and browser Back", async ({ page }) => {
  const assertClean = await mockWorkspace(page);
  await openWorkspace(page);
  await railLink(page, "Data").click();
  const dataContext = page.getByRole("combobox", { name: "Data input context", exact: true });
  await dataContext.selectOption("fixture-study");
  await expect(dataContext).toHaveValue("fixture-study");
  await expect(page).toHaveURL(/[?&]dataContext=fixture-study(?:&|$)/);
  await page.reload();
  await expect(dataContext).toHaveValue("fixture-study");
  await railLink(page, "Modules").click();
  await expect(page).toHaveURL(/\/modules(?:\?|$)/);
  await page.goBack();
  await expect(dataContext).toHaveValue("fixture-study");

  await dataContext.selectOption("draft");
  await expect(dataContext).toHaveValue("draft");
  await expect.poll(() => new URL(page.url()).searchParams.has("dataContext")).toBe(false);
  // Moving away waits for the committed URL and exercises restoration independently of reload.
  await railLink(page, "Modules").click();
  await expect(page).toHaveURL(/\/modules(?:\?|$)/);
  await page.goBack();
  await expect(dataContext).toHaveValue("draft");
  await page.reload();
  await expect(dataContext).toHaveValue("draft");
  assertClean();
});

test("an unavailable Data context stays explicit and offers no checklist for the draft pack", async ({ page }) => {
  const assertClean = await mockWorkspace(page);
  await openWorkspace(page, "/?view=data&study=fixture-study&dataContext=missing-data-study");
  await expect(page.getByRole("combobox", { name: "Data input context", exact: true })).toHaveValue("missing-data-study");
  await expect(page.getByRole("status").filter({ hasText: "The linked Study is unavailable" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose a data pack", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download missing-input checklist", exact: true })).toHaveCount(0);
  expect(new URL(page.url()).searchParams.get("dataContext")).toBe("missing-data-study");
  assertClean();
});

for (const width of [320, 390]) {
  test(`${width}px viewport keeps community pages and Read me within the page width`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const assertClean = await mockWorkspace(page);
    await openWorkspace(page);
    await expectNoPageOverflow(page);
    await page.screenshot({ path: test.info().outputPath(`${width}-home.png`), fullPage: true });
    for (const path of PATHS) {
      // Below 900 px the sidebar is a drawer; each path starts from Home.
      await openWorkspace(page);
      await page.getByRole("button", { name: path.label, exact: true }).click();
      await expect(page.getByRole("heading", { name: path.heading, exact: true })).toBeVisible();
      await expectNoPageOverflow(page);
      if (path.path === "data") await page.screenshot({ path: test.info().outputPath(`${width}-data.png`), fullPage: true });
    }
    await page.goto("/runs/fixture-old-run");
    await expect(page.getByRole("region", { name: "Selected Run context", exact: true })).toContainText("frozen-old-data-pack");
    await expectNoPageOverflow(page);
    await page.screenshot({ path: test.info().outputPath(`${width}-runs.png`), fullPage: true });
    await page.getByRole("button", { name: "Read me", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Read me", exact: true });
    await expect(dialog.getByRole("heading", { name: "VALUE Read me", exact: true })).toBeVisible();
    await expectNoPageOverflow(page);
    expect(await dialog.evaluate((element) => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
    await page.screenshot({ path: test.info().outputPath(`${width}-readme.png`) });
    assertClean();
  });
}
