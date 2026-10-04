import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("Castle 101 loads the ordinary Study editor without silently saving", async ({ page }) => {
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
  const capabilities = await page.request.get(`http://127.0.0.1:18766/api/runs/${runId}/market/capabilities`);
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
    const response = await page.request.get(`http://127.0.0.1:18766/api/runs/${variantRunId}`);
    return response.ok() ? (await response.json()).status : "missing";
  }, { timeout: 45_000 }).toBe("completed");
  await expect(page.getByLabel("Selected run")).toHaveValue(variantRunId);
  await expect(page.getByText("Run completed")).toBeVisible();

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
