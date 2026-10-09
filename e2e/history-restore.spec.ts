import { expect, test, type Page, type Route } from "@playwright/test";
import { railLink } from "./workspace-nav";

// RR-1 (1), D-P1P-6: Back and Forward restore the selection of each history
// entry.  The shell's popstate listener was never called on a real traversal,
// so Back from /runs?study=s1&run=r1b to ...&run=r1a kept the later Run on
// screen, and Back across pages wrote the later Study over the restored URL.
// The traversals here are real browser history moves (page.goBack/goForward)
// across /studies/[id], /runs?study=&run= and /data?dataContext=.  Every /api
// route is mocked (VALUE_E2E_UI_ONLY); nothing is written.
const study = (id: string, name: string) => ({
  id, name, data_pack_id: "history-pack", start_year: 2025, end_year: 2026, revision_number: 1,
  revision_sha256: id.repeat(64).slice(0, 64), modules: {}, selected_extensions: [], extension_parameters: {},
  maturity_acknowledgements: {}, market_configuration: {}, updated_at: "2026-10-01T00:00:00Z",
});
const studies = [study("s1", "History study one"), study("s2", "History study two")];
const run = (id: string, projectId: string, updated: string) => ({
  id, project_id: projectId, project_name: studies.find((item) => item.id === projectId)!.name, mode: "two_year",
  status: "completed", current_stage: "Run completed", completed_years: 2, total_years: 2, updated_at: updated,
  results: [], modules: {}, input_snapshot_id: "a".repeat(64), input_tree_sha256: "b".repeat(64),
  execution_status: "passed", contract_validation_status: "passed", scientific_validation_status: "not_evaluated",
});
const runs = [run("r1a", "s1", "2026-10-03T00:00:00Z"), run("r1b", "s1", "2026-10-02T00:00:00Z"), run("r2", "s2", "2026-10-01T00:00:00Z")];
const workspace = {
  architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [],
  projects: studies, runs, module_installations: [], extension_installations: [], study_trash: [],
  data_packs: [{ id: "history-pack", name: "History pack", country: "SYNTHETIC", timezone: "UTC", bindings: {}, required_count: 0,
    bound_required_count: 0, valid_required_count: 0, binding_issues: {}, complete: true }],
  runtime: { python: "3.10", compatible: true, selected_capability: "value-native", capabilities: {} },
};
const resolution = {
  schema_version: "value.study-draft-resolution/v1", frontend_contract_version: "value.frontend/v1",
  valid: true, errors: [], warnings: [], module_slots: [], compatible_modules: {}, system_domains: [],
  active_dataset_slots: [], data_readiness: { required: 0, available: 0, missing_roles: [] },
  effective_extension_parameters: {}, maturity: { acknowledgement_contract: "test", acknowledgements_required: [] },
};

async function mockApi(page: Page) {
  const writes: string[] = [];
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route("**/api/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let status = 200;
    let body: unknown = { error: "Not recorded in fixture" };
    const runMatch = path.match(/^\/api\/runs\/([^/]+)$/);
    if (request.method() !== "GET" && path !== "/api/projects/resolve-draft") { writes.push(`${request.method()} ${path}`); status = 405; }
    else if (path === "/api/workspace") body = workspace;
    else if (path === "/api/health") body = { ok: true, frontend_contract_version: "value.expanded-frontend/v1", status: "ok", version: "0.7.0a1", degraded_reasons: [] };
    else if (path === "/api/parameters") body = { parameters: [] };
    else if (path === "/api/projects/resolve-draft") body = resolution;
    else if (runMatch && runs.some((item) => item.id === runMatch[1])) body = runs.find((item) => item.id === runMatch[1]);
    else status = 404;
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  return () => { expect(writes).toEqual([]); expect(pageErrors).toEqual([]); };
}

type Entry = { path: string; query: Record<string, string | null>; check: (page: Page) => Promise<void> };

/** The URL of the entry (path and the workbench's own keys), stable after the page settled. */
async function expectEntry(page: Page, entry: Entry) {
  const matches = () => {
    const url = new URL(page.url());
    return url.pathname === entry.path && Object.entries(entry.query).every(([key, value]) => url.searchParams.get(key) === value);
  };
  await expect.poll(matches, { message: `${entry.path} ${JSON.stringify(entry.query)} (now ${page.url()})` }).toBe(true);
  await entry.check(page);
  // The restored selection is shown, and the URL is not rewritten with the previous entry's.
  await page.waitForTimeout(400);
  expect(matches(), `URL rewritten to ${page.url()}`).toBe(true);
  await entry.check(page);
}

test("Back and Forward restore the Study, Run and data context of each history entry", async ({ page }) => {
  const assertClean = await mockApi(page);
  const studySelect = page.getByRole("combobox", { name: "Study", exact: true });
  const runSelect = page.getByRole("combobox", { name: "Selected run", exact: true });
  const dataContext = page.getByRole("combobox", { name: "Data input context", exact: true });
  const runCentre = (studyId: string, runId: string): Entry => ({
    path: "/runs", query: { study: studyId, run: runId },
    check: async (current) => {
      await expect(studySelect).toHaveValue(studyId);
      await expect(runSelect).toHaveValue(runId);
      // The Run status panel and the Run section bar follow the restored Run.
      await expect(current.locator(".run-status")).toContainText(`/ ${runId}`);
      await expect(current.getByRole("navigation", { name: "Pages of this Run" }).getByRole("link", { name: "Annual results", exact: true })).toHaveAttribute("href", `/runs/${runId}`);
    },
  });
  const edit: Entry = {
    path: "/studies/s1", query: {},
    check: async (current) => { await expect(current.getByRole("link", { name: "← Back to Studies", exact: true })).toBeVisible(); },
  };
  const dataDraft: Entry = { path: "/data", query: { dataContext: null }, check: async () => { await expect(dataContext).toHaveValue("draft"); } };
  const dataStudy: Entry = { path: "/data", query: { dataContext: "s1" }, check: async () => { await expect(dataContext).toHaveValue("s1"); } };

  await page.goto("/studies/s1");
  await expectEntry(page, edit);
  await railLink(page, "Runs").click();
  await expectEntry(page, runCentre("s1", "r1a"));
  await runSelect.selectOption("r1b");
  await expectEntry(page, runCentre("s1", "r1b"));
  await studySelect.selectOption("s2");
  await expectEntry(page, runCentre("s2", "r2"));
  await railLink(page, "Data").click();
  await expectEntry(page, dataDraft);
  await dataContext.selectOption("s1");
  await expectEntry(page, dataStudy);

  const entries = [edit, runCentre("s1", "r1a"), runCentre("s1", "r1b"), runCentre("s2", "r2"), dataDraft, dataStudy];
  for (let index = entries.length - 2; index >= 0; index -= 1) {
    await page.goBack();
    await expectEntry(page, entries[index]);
  }
  for (let index = 1; index < entries.length; index += 1) {
    await page.goForward();
    await expectEntry(page, entries[index]);
  }
  assertClean();
});
