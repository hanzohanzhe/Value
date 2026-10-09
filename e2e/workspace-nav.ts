import type { Page } from "@playwright/test";

// P1 W3 (spec 5.1/5.2): the sidebar entries are links to their routes, and the
// pages of one Run (Market replay, VRE, Network, Systems) are reached from
// Runs through the Run section bar, no longer from the sidebar.

/** A sidebar entry by its label ("Studies", "Runs", …). */
export function railLink(page: Page, label: string) {
  return page.getByRole("navigation", { name: "Workspace" }).getByRole("link", { name: new RegExp(`^${label.replace(/[&]/g, "\\$&")}:`) });
}

/** Open one page of the selected Run: Runs, then that page in the Run section bar. */
export async function openRunSection(page: Page, label: string) {
  await railLink(page, "Runs").click();
  await page.getByRole("navigation", { name: "Pages of this Run" }).getByRole("link", { name: label, exact: true }).click();
}
