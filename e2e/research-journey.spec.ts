import { expect, test, type Page } from "@playwright/test";
// P1 W4a (A30): the research guide reads in English by default; its labels below are the en dictionary's (journey.*).
import { VALUE_101_FALLBACK } from "../app/features/learn/value101";
import { railLink } from "./workspace-nav";

const baseline = {
  id: "fixture-study", name: "Journey baseline", data_pack_id: "baseline-pack",
  revision_number: 9, revision_sha256: "9".repeat(64), start_year: 2025, end_year: 2034,
  modules: { psm: "fixture-psm", investment: "fixture-investment" }, parameters: { "fixture.assumption": 23 },
  selected_extensions: [], extension_parameters: {}, maturity_acknowledgements: {},
  market_configuration: {}, updated_at: "2026-10-01T00:00:00Z",
};
const secondStudy = { ...baseline, id: "fixture-study-b", name: "Study B", revision_sha256: "b".repeat(64) };

function pack(id: string) {
  return { id, name: id, country: "SYNTHETIC", timezone: "UTC", bindings: {}, required_count: 1,
    bound_required_count: 1, valid_required_count: 1, binding_issues: {}, complete: true };
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

type DeriveInput = { intent: "reproduce" | "data"; name: string; source_revision_sha256: string; data_pack_id: string };

async function mockWorkspace(page: Page, options: {
  derivedRefresh?: Promise<void>;
  delayedPreflight?: { requested: () => void; ready: Promise<void> };
} = {}) {
  const projects: Array<typeof baseline> = [structuredClone(baseline), structuredClone(secondStudy)];
  const derived: Array<typeof baseline> = [];
  const derivations: DeriveInput[] = [];
  const unexpectedWrites: string[] = [];
  const runWrites: string[] = [];
  const pageErrors: string[] = [];
  const preflights: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    let status = 200;
    let body: unknown;
    const deriveMatch = path.match(/^\/api\/projects\/([^/]+)\/derive$/);
    const preflightMatch = path.match(/^\/api\/projects\/([^/]+)\/preflight$/);
    if (method === "POST" && /\/runs(?:\/|$)/.test(path)) {
      runWrites.push(path);
      status = 405;
      body = { error: "This journey regression must never start a Run." };
    } else if (method === "GET" && path === "/api/workspace") {
      if (derived.length && options.derivedRefresh) await options.derivedRefresh;
      body = {
        architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [],
        projects, runs: [], data_packs: [pack("baseline-pack"), pack("new-data-pack")],
        module_installations: [], extension_installations: [], study_trash: [],
        runtime: { python: "3.11", compatible: true, selected_capability: "value-native", capabilities: {} },
      };
    } else if (method === "GET" && path === "/api/parameters") body = { parameters: [] };
    else if (method === "GET" && path === "/api/tutorials/value-101") body = VALUE_101_FALLBACK;
    else if (method === "POST" && path === "/api/projects/resolve-draft") body = {
      schema_version: "value.study-draft-resolution/v1", frontend_contract_version: "value.frontend/v1",
      valid: true, errors: [], warnings: [], module_slots: [], compatible_modules: {}, system_domains: [],
      active_dataset_slots: [], data_readiness: { required: 0, available: 0, missing_roles: [] },
      effective_extension_parameters: {}, maturity: { acknowledgement_contract: "test", acknowledgements_required: [] },
    };
    else if (method === "POST" && deriveMatch) {
      const source = projects.find((project) => project.id === decodeURIComponent(deriveMatch[1]));
      const input = request.postDataJSON() as DeriveInput;
      derivations.push(input);
      if (!source || source.revision_sha256 !== input.source_revision_sha256
        || (input.intent === "data" && source.data_pack_id === input.data_pack_id)) {
        status = 409;
        body = { error: "Fixture rejected an invalid derivation." };
      } else {
        // The mock saves configuration only. It produces no scientific result or Run.
        const project = { ...structuredClone(source), id: `derived-${input.intent}`, name: input.name,
          data_pack_id: input.data_pack_id, revision_number: 1, revision_sha256: "d".repeat(64),
          derivation: { intent: input.intent, source_study_id: source.id, source_revision_sha256: input.source_revision_sha256 } };
        projects.push(project);
        derived.push(project);
        body = { project, run_started: false };
      }
    } else if (method === "POST" && preflightMatch) {
      const studyId = decodeURIComponent(preflightMatch[1]);
      preflights.push(studyId);
      if (studyId === baseline.id && options.delayedPreflight) {
        options.delayedPreflight.requested();
        await options.delayedPreflight.ready;
      }
      body = {
        project_id: studyId,
        project_revision_sha256: projects.find((project) => project.id === studyId)?.revision_sha256,
        data_pack_id: projects.find((project) => project.id === studyId)?.data_pack_id,
        accepted: true, mode: request.postDataJSON().mode, errors: [],
        warnings: [{ code: "fixture-evidence", message: studyId === baseline.id ? "A-only preflight evidence" : "B-only preflight evidence", corrective_action: "Browser fixture only." }],
        estimates: { periods: 2, disk_bytes: 1024, peak_memory_bytes: 2048, runtime_seconds: 1 },
      };
    } else if (method === "GET" && /^\/api\/data-workbench\/v1\/(sources|revisions|candidates|bundles)$/.test(path)) {
      const collection = path.split("/").at(-1)!;
      body = { schema_version: `value.data-${collection === "bundles" ? "installed-bundles" : collection}/v1`, [collection]: [] };
    } else {
      if (method !== "GET") unexpectedWrites.push(`${method} ${path}`);
      status = 404;
      body = { error: "No journey fixture for this request." };
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  return {
    derivations, derived, preflights,
    assertClean() { expect(runWrites).toEqual([]); expect(unexpectedWrites).toEqual([]); expect(pageErrors).toEqual([]); },
  };
}

async function openWorkspace(page: Page, url = "/") {
  await page.goto(url);
  await expect(page.locator(".rail .service")).toContainText("value-native ready");
}

async function expectNoPageOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)
    - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
}

test("reproduce saves the selected revision and pack, then opens Runs without launching", async ({ page }) => {
  const refreshGate = deferred();
  const fixture = await mockWorkspace(page, { derivedRefresh: refreshGate.promise });
  await openWorkspace(page);
  await page.getByRole("button", { name: "Reproduce from existing data", exact: true }).click();
  await expect(page).toHaveURL(/\/journey(?:\?|$)/);
  const journey = page.locator(".research-journey:visible");
  await expect(journey.getByRole("heading", { name: "Reproduce from existing data", exact: true })).toBeVisible();
  await journey.getByRole("combobox", { name: "Existing Study", exact: true }).selectOption(baseline.id);
  await journey.getByRole("textbox", { name: "Name of the new Study", exact: true }).fill("My reproduction");
  await expect(journey.locator("details.research-journey-modules")).not.toHaveAttribute("open");
  await journey.getByRole("button", { name: "Create the reproduction Study", exact: true }).click();
  try {
    await expect.poll(() => fixture.derivations.length).toBe(1);
    await expect(journey.getByRole("button", { name: "Creating the Study…", exact: true })).toBeDisabled();
    await journey.locator("form").evaluate((form) => (form as HTMLFormElement).requestSubmit());
    expect(fixture.derivations).toEqual([{
      intent: "reproduce", name: "My reproduction", source_revision_sha256: baseline.revision_sha256, data_pack_id: baseline.data_pack_id,
    }]);
  } finally { refreshGate.resolve(); }
  await expect(page).toHaveURL(/\/runs(?:\/|\?|$)/);
  await expect(page.locator(".run-control").getByRole("combobox", { name: "Study", exact: true })).toHaveValue("derived-reproduce");
  expect(fixture.derived[0].modules).toEqual(baseline.modules);
  fixture.assertClean();
});

test("data requires another pack, retains choices after Data and fits a 390px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const fixture = await mockWorkspace(page);
  await openWorkspace(page);
  await page.getByRole("button", { name: "Add your new data", exact: true }).click();
  await expect(page).toHaveURL(/\/journey(?:\?|$)/);
  const journey = page.locator(".research-journey:visible");
  const source = journey.getByRole("combobox", { name: "Existing Study", exact: true });
  const name = journey.getByRole("textbox", { name: "Name of the new Study", exact: true });
  const target = journey.getByRole("combobox", { name: "Installed data pack", exact: true });
  await source.selectOption(baseline.id);
  await name.fill("My new-data comparison");
  await expect(journey.getByRole("button", { name: "Create the new-data Study", exact: true })).toBeDisabled();
  await expect(target.locator(`option[value="${baseline.data_pack_id}"]`)).toHaveCount(0);
  await target.selectOption("new-data-pack");
  await expect(journey).toContainText("Complete files do not mean the Study passes its checks");
  await expectNoPageOverflow(page);
  await journey.locator("summary").filter({ hasText: "Show the modules that are kept" }).click();
  await expect(journey.getByRole("region", { name: "Modules kept", exact: true })).toBeVisible();
  await expectNoPageOverflow(page);
  await journey.getByRole("button", { name: "Open Data to install / validate", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Data Workbench", exact: true })).toBeVisible();
  await expect(page.locator(".data-workbench")).not.toContainText("Unexpected Data Workbench schema");
  await expectNoPageOverflow(page);
  // R-6 (P1-polish): below 900 px the sidebar is a drawer opened from its menu button.
  await page.getByRole("button", { name: "Open navigation" }).click();
  await railLink(page, "Research guide").click();
  await expect(name).toHaveValue("My new-data comparison");
  await expect(source).toHaveValue(baseline.id);
  await expect(target).toHaveValue("new-data-pack");
  await journey.getByRole("button", { name: "Create the new-data Study", exact: true }).click();
  await expect(page).toHaveURL(/\/runs(?:\/|\?|$)/);
  await expect(page.locator(".run-control").getByRole("combobox", { name: "Study", exact: true })).toHaveValue("derived-data");
  expect(fixture.derivations).toEqual([{
    intent: "data", name: "My new-data comparison", source_revision_sha256: baseline.revision_sha256, data_pack_id: "new-data-pack",
  }]);
  expect(fixture.derived[0]).toMatchObject({ modules: baseline.modules, parameters: baseline.parameters,
    start_year: baseline.start_year, end_year: baseline.end_year, data_pack_id: "new-data-pack" });
  await expectNoPageOverflow(page);
  fixture.assertClean();
});

test("a late Study A preflight stays hidden after switching to B, and B can check itself", async ({ page }) => {
  const requested = deferred();
  const responseGate = deferred();
  const fixture = await mockWorkspace(page, { delayedPreflight: { requested: requested.resolve, ready: responseGate.promise } });
  await openWorkspace(page, "/?view=run&study=fixture-study");
  const study = page.locator(".run-control").getByRole("combobox", { name: "Study", exact: true });
  const readiness = page.locator(".preflight-card");
  await page.getByRole("button", { name: "Check readiness", exact: true }).click();
  await requested.promise;
  const oldResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/projects/fixture-study/preflight");
  await study.selectOption(secondStudy.id);
  await expect(study).toHaveValue(secondStudy.id);
  responseGate.resolve();
  await (await oldResponse).finished();
  // Allow the resolved fetch and React rendering to finish before checking absence.
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(readiness.locator("section.accepted")).toHaveCount(0);
  await expect(readiness).not.toContainText("A-only preflight evidence");
  await page.getByRole("button", { name: "Check readiness", exact: true }).click();
  // Readiness groups (R4/W4c) fold their warnings; open them before reading the evidence.
  await readiness.locator("section.accepted").getByRole("button", { name: /^Show \d+$/ }).click();
  await expect(readiness.locator("section.accepted")).toContainText("B-only preflight evidence");
  await expect(readiness).not.toContainText("A-only preflight evidence");
  expect(fixture.preflights).toEqual([baseline.id, secondStudy.id]);
  fixture.assertClean();
});
