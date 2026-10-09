import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { railLink } from "./workspace-nav";

test("desktop and narrow layouts preserve navigation and readable zoom", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Workspace" })).toBeVisible();
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await expect(railLink(page, "Studies")).toBeVisible();
  await railLink(page, "Modules").focus();
  await expect(railLink(page, "Modules")).toBeFocused();
  await railLink(page, "Modules").click();
  const installerHeading = page.getByRole("heading", { name: "Install a model module" });
  await installerHeading.scrollIntoViewIfNeeded();
  await expect(installerHeading).toBeVisible();
  await expect(page.getByText(/executable Python code/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Install and validate module" })).toBeDisabled();
  const accessibility = await new AxeBuilder({ page }).include(".module-installer").analyze();
  expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
});
