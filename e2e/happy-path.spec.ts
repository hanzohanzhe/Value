import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("non-programmer synthetic study executes the selected external module", async ({ page }, testInfo) => {
  let workspaceBytes = 0;
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("requestfailed", (request) => browserErrors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText}`));
  page.on("response", async (response) => {
    if (response.url().endsWith("/api/workspace")) workspaceBytes = (await response.body()).byteLength;
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  await expect(page.getByText(/Backend (degraded|offline)/)).toHaveCount(0);
  await expect(page.getByText(/Python 3\.10/).first(), browserErrors.join("\n")).toBeVisible();

  await page.getByRole("button", { name: /Studies/ }).click();
  const name = `Browser external proof ${testInfo.project.name}`;
  await page.getByLabel("Name", { exact: true }).fill(name);
  await page.getByLabel("First model year").fill("2025");
  await page.getByLabel("Final model year").fill("2026");
  await page.getByRole("button", { name: "Advanced" }).click();
  await page.getByRole("button", { name: /Model chain/ }).click();
  await page.locator(".chain-slot").filter({ hasText: "National ahead market / PSM" }).locator("select").selectOption("example-marked-perfect-foresight-psm");
  await page.getByRole("button", { name: /Review/ }).click();
  await expect(page.getByText("Graph ready to save")).toBeVisible();
  await page.getByRole("button", { name: "Save this exact Study revision" }).click();
  await expect(page.getByRole("heading", { name: "What will run" })).toBeVisible();

  await page.getByLabel("Check for").selectOption("two_year_smoke");
  await page.getByRole("button", { name: "Run selected scope · Two-year hand-off check" }).click();
  await expect(page.getByText("Run completed")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("example-marked-perfect-foresight-psm")).toBeVisible();
  await expect(page.getByText(/recorded calls/).first()).toBeVisible();

  const runId = await page.getByLabel("Selected run").inputValue();
  // Direct API calls go through the UI gateway (P0-1): it adds the session.
  const run = await page.request.get(`/api/runs/${runId}`);
  expect(run.ok()).toBeTruthy();
  const artifacts = await page.request.get(`/api/runs/${runId}/artifacts`);
  expect(artifacts.ok()).toBeTruthy();
  expect((await artifacts.json()).items.length).toBeGreaterThan(3);
  const exportResponse = await page.request.post(`/api/runs/${runId}/export`, { data: { profile: "compact_results" }, headers: { origin: "http://127.0.0.1:18800" } });
  expect(exportResponse.status()).toBe(201);
  expect((await exportResponse.json()).validation.valid).toBeTruthy();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter((item) => item.impact === "critical")).toEqual([]);
  expect(workspaceBytes).toBeGreaterThan(0);
  expect(workspaceBytes).toBeLessThan(512 * 1024);
});

test("incompatible study and offline recovery are visible failures", async ({ page }) => {
  await page.goto("/");
  const invalid = await page.request.post("/api/projects", { headers: { origin: "http://127.0.0.1:18800" }, data: {
    name: "Incompatible", data_pack_id: "value-synthetic-contract-pack-v1", start_year: 2025, end_year: 2026,
    modules: { psm: "value-perfect-foresight-lp", storage_cost: "dynamic-annual-storage-cost" },
  }});
  expect(invalid.status()).toBe(400);
  expect((await invalid.json()).error).toMatch(/Select a module for pipeline|Missing required module.*pipeline/i);

  await page.route("**/api/workspace", (route) => route.abort("failed"));
  await page.reload();
  // P0-3 S8: a failed load shows the service as degraded (offline after three failures); the page stays readable.
  await expect(page.locator(".service")).toContainText(/Backend (degraded|offline)/);
  await page.unroute("**/api/workspace");
  await page.locator(".service").getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText(/Python 3\.10/).first()).toBeVisible();
});
