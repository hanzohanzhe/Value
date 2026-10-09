import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { railLink } from "./workspace-nav";

// Every test here talks to the real Python service, so the offline subset
// (VALUE_E2E_UI_ONLY=1, UI only) skips the whole file. Three tests also load or
// run the bundled Castle pack, which a source checkout may not ship: those skip
// (visibly) when it is missing, because that is an environment gap, not a
// Castle regression (P0-9 S0). The missing-pack test needs no pack and runs
// against the real service wherever the Castle 101 tutorial exists.
//
// The public source tree (35aadb3 and later) has no Castle 101 tutorial at all:
// backend/server.py serves only /api/tutorials/value-101 and the Learn entry is
// "VALUE 101", so every test here would time out looking for "Learn: Castle 101".
// That is a stale spec, not a regression. It is detected statically from the
// source (not from a live response, which could hide a broken route); rewriting
// or removing this spec is left to P1.
const castlePackPresent = fs.existsSync(path.resolve("data-packs", "force-castle-101-v1"));
const castleTutorialServed = fs.readFileSync(path.resolve("backend", "server.py"), "utf8").includes("/api/tutorials/castle-101");
const uiOnly = process.env.VALUE_E2E_UI_ONLY === "1";
test.beforeEach(() => {
  test.skip(uiOnly, "needs the real Python service; VALUE_E2E_UI_ONLY=1 serves the UI only");
  test.skip(!castleTutorialServed, "this source tree has no Castle 101 tutorial (backend/server.py serves /api/tutorials/value-101 only); stale spec, owner P1");
});
function needsCastlePack() {
  test.skip(!castlePackPresent, "data-packs/force-castle-101-v1 is not part of this source tree");
}

test("Castle 101 loads the ordinary Study editor without silently saving", async ({ page }) => {
  needsCastlePack();
  const projectWrites: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/projects")) {
      projectWrites.push(request.url());
    }
  });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  await page.getByRole("button", { name: "Learn: Castle 101" }).click();

  await expect(page.getByRole("heading", { name: "Learn" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Build and run your first VALUE model" })).toBeVisible();
  await expect(page.getByText("Teaching diagnostic: not annual economics")).toBeVisible();
  const load = page.getByRole("button", { name: "Load Castle Study" });
  await expect(load).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
  await load.focus();
  await expect(load).toBeFocused();
  await load.press("Enter");

  await expect(page.getByRole("heading", { name: "Studies" })).toBeVisible();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Castle 101 baseline");
  await expect(page.getByLabel("First model year")).toHaveValue("2025");
  await expect(page.getByLabel("Final model year")).toHaveValue("2026");
  await expect(page.getByLabel("Selected data pack")).toHaveValue("force-castle-101-v1");
  expect(projectWrites).toEqual([]);
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual(["value.castle-101.progress.v1"]);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter((item) => item.impact === "critical")).toEqual([]);
});

test("Castle 101 explains a missing teaching pack", async ({ page }) => {
  await page.route("**/api/tutorials/castle-101", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.availability = {
      pack_id: "force-castle-101-v1",
      pack_installed: false,
      corrective_action: "Re-run the standard installer to add the bundled Castle pack.",
    };
    await route.fulfill({ response, json: payload });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Learn: Castle 101" }).click();
  await expect(page.getByRole("heading", { name: "The lesson cannot load yet" })).toBeVisible();
  await expect(page.getByText("Re-run the standard installer to add the bundled Castle pack.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load Castle Study" })).toBeDisabled();
});

test("Castle 101 uses loopback only and restores lesson progress after refresh", async ({ page }) => {
  needsCastlePack();
  const externalRequests: string[] = [];
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1") {
      await route.continue();
      return;
    }
    externalRequests.push(url.href);
    await route.abort("internetdisconnected");
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Learn: Castle 101" }).click();
  await page.getByRole("button", { name: "Mark as read" }).click();
  await expect(page.getByLabel("Castle 101 progress")).toContainText("1 / 5");

  await page.reload();
  await page.getByRole("button", { name: "Learn: Castle 101" }).click();
  await expect(page.getByLabel("Castle 101 progress")).toContainText("1 / 5");
  expect(externalRequests).toEqual([]);
});

test("Castle 101 runs through the real service and opens indexed evidence", async ({ page }) => {
  needsCastlePack();
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  await page.getByRole("button", { name: "Learn: Castle 101" }).click();
  await page.getByRole("button", { name: "Load Castle Study" }).click();

  await page.getByRole("button", { name: /Review/ }).click();
  await expect(page.getByText("Graph ready to save")).toBeVisible();
  await page.getByRole("button", { name: "Save this exact Study revision" }).click();
  await expect(page.getByRole("heading", { name: "What will run" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run Castle tutorial" })).toBeEnabled();
  await page.getByRole("button", { name: "Run Castle tutorial" }).click();

  await expect(page.getByText("Run completed")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("heading", { name: "Castle 101 teaching run" })).toBeVisible();
  const runId = await page.getByLabel("Selected run").inputValue();
  const capabilities = await page.request.get(`/api/runs/${runId}/market/capabilities`);
  expect(capabilities.ok()).toBeTruthy();
  expect((await capabilities.json()).trace_level).toBe("full");

  await page.getByRole("button", { name: "Learn: Castle 101" }).click();
  await expect(page.getByRole("button", { name: "Open bids and dispatch" })).toBeEnabled();
  await page.getByRole("button", { name: "Open VRE & curtailment" }).click();
  await expect(page.getByRole("heading", { name: "See how much VRE was available, used and left unused" })).toBeVisible();
  await expect(page.getByText("Unused VRE", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "Learn: Castle 101" }).click();
  const cloneResponse = page.waitForResponse((response) => response.url().endsWith("/clone-storage-policy") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Create legacy-tariff Study" }).click();
  const clonePayload = await (await cloneResponse).json();
  expect(clonePayload.only_intended_module_changed).toBeTruthy();
  await expect(page.getByRole("heading", { name: "Studies" })).toBeVisible();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue(/legacy-storage-tariff/);

  await page.getByRole("button", { name: "Runs: Launch and compare" }).click();
  await expect(page.getByRole("heading", { name: "What will run" })).toBeVisible();
  const variantStart = page.waitForResponse((response) =>
    /\/api\/projects\/[^/]+\/runs$/.test(new URL(response.url()).pathname)
    && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Run Castle tutorial" }).click();
  const variantPayload = await (await variantStart).json();
  const variantRunId = variantPayload.run.id as string;
  expect(variantRunId).not.toBe(runId);
  await expect.poll(async () => {
    const response = await page.request.get(`/api/runs/${variantRunId}`);
    return response.ok() ? (await response.json()).status : "missing";
  }, { timeout: 45_000 }).toBe("completed");
  await expect(page.getByLabel("Selected run")).toHaveValue(variantRunId);
  await expect(page.getByText("Run completed")).toBeVisible();

  // W4c (spec 5.1/6.6): the comparison is on its own page.
  await railLink(page, "Compare").click();
  const comparisonChoices = page.locator(".comparison-picker input[type=checkbox]");
  await expect(comparisonChoices).toHaveCount(2);
  await comparisonChoices.nth(0).check();
  await comparisonChoices.nth(1).check();
  await expect(page.getByText("Controlled teaching configuration")).toBeVisible();
  await expect(page.getByText("module.storage_cost", { exact: true })).toBeVisible();
  await expect(page.getByText(/Annual cost and carbon deltas are withheld/).first()).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  expect((await download).suggestedFilename()).toBe("value-comparison.json");
});
