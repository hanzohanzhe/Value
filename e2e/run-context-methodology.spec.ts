import { test, expect, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// X0 S12 + P0-9 S11 (spec 2, 7): the methodology pill, validation fields and
// prioritised notices of the Run context bar; the Study composer's
// Methodology choice; the method-change confirmation <dialog>. Every /api
// route is mocked (VALUE_E2E_UI_ONLY).
const study = { id: "demo", name: "Release R2 new forecast", data_pack_id: "value-101-baseline-v1", start_year: 2025, end_year: 2025, modules: { psm: "value-bid-at-cost-psm", storage_cost: "dynamic-annual-storage-cost" }, updated_at: "2026-10-05T00:00:00+01:00", revision_number: 1, revision_sha256: "rev-1" };
const base = { project_id: study.id, project_name: study.name, status: "completed", completed_years: 1, total_years: 1, updated_at: study.updated_at, modules: {}, execution_status: "passed" };
const preFix = {
  ...base, id: "r2-run", mode: "value_101_day", results: [],
  methodology: { status: "not_recorded", profile_id: null },
  contract_validation_status: "superseded_pre_fix", scientific_validation_status: "superseded_pre_fix",
  recorded_scientific_validation_status: "passed",
  energy_balance_status: "failed",
  energy_balance: { status: "failed", envelope_lower_violations: 48, envelope_upper_violations: 0, maximum_envelope_violation_mwh: 23.4 },
  stress: { stress_periods: 48, shortfall_mwh: 570.546171074, shortfall_basis: "lower_bound" },
  advisories: [{ id: "VALUE-ADV-2026-10-04-REVIEW", severity: "high", title: "Produced before the 2026-10 review", summary: "Results may be affected by findings of the 2026-10 review.", affected_metrics: ["total_system_cost_gbp"] }],
  advisory_summary: { count: 1, max_severity: "high", needs_review: true },
};
const reproduction = {
  ...base, id: "doctoral-run", mode: "two_year", results: [], withheld_result_year_count: 2,
  methodology: { status: "recorded", profile_id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", catalogue_sha256: "catalogue" },
  contract_validation_status: "passed", scientific_validation_status: "not_evaluated",
  energy_balance_status: "not_evaluated", stress: { stress_periods: 0, shortfall_mwh: 0 },
  result_publication: { status: "withheld", rule: "raw_invariants_must_pass", reason_code: "GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED", message: "Doctoral reproduction runs publish annual results only when every raw invariant passes; the results remain available in Inspect and exports." },
  advisories: [], advisory_summary: { count: 0 },
};
const catalogue = {
  schema_version: "value.methodology-catalogue/v1", default_profile_id: "value-corrected",
  profiles: [
    { id: "value-corrected", label: "Corrected methodology (default)", frozen: false, default: true, supported_data_packs: "*", supported_extensions: "*", reference_configuration: { modules: {}, parameters: {} } },
    { id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", frozen: true, default: false, supported_extensions: [],
      supported_data_packs: [{ id: "value-101-baseline-v1", label: "VALUE 101 baseline", pack_class: "teaching" }],
      reference_configuration: { modules: { storage_cost: "value-legacy-storage-tariff" }, parameters: { "carbon.factor_scenario": "doctoral_reproduction_2026_07_18" } } },
  ],
};
const pack = (id: string, name: string) => ({ id, name, country: "GB", timezone: "Europe/London", bindings: {}, required_count: 0, bound_required_count: 0, valid_required_count: 0, binding_issues: {}, complete: true, allowed_run_modes: ["smoke", "value_101_day"] });
const workspace = {
  architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [], module_installations: [], extension_installations: [], study_trash: [],
  projects: [study], data_packs: [pack("value-101-baseline-v1", "VALUE 101 baseline"), pack("my-pack", "My own pack")],
  runs: [preFix, reproduction], runtime: { python: "3.10.11", compatible: true, selected_capability: "value-native" },
};
const migration = (profile: string, diff: string) => ({
  schema_version: "value.revision-classification/v1", classification: "method_upgrade_required", automatic: false, confirmable: true,
  error_code: "GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED", diff_sha256: diff, selected_profile_id: profile, declared_sha256: "rev-1", calculated_sha256: "rev-2",
  differences: [
    { dimension: "methodology", key: "profile_id", old: null, new: profile, classification: "method_upgrade_required", effect: "The Study predates methodology profiles; confirming records the selected methodology explicitly (Q13).", hint: "matches_reference_preset", matches_reference_preset: ["doctoral-lineage-0.6.0a2"] },
    { dimension: "module", key: "psm:value-bid-at-cost-psm", old: "5.1.0", new: "5.2.0", classification: "method_upgrade_required", effect: "Upgrade that requires user opt-in (VERSION_LEDGER)." },
  ],
  profile_choices: [
    { profile_id: "value-corrected", label: "Corrected methodology (default)", default: true, frozen: false, supported: true, unsupported_reasons: [], matches_reference_preset: false },
    { profile_id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", default: false, frozen: true, supported: true, unsupported_reasons: [], matches_reference_preset: true },
  ],
});

type Recorded = { method: string; path: string; body: string };
async function mockApi(page: Page, recorded: Recorded[] = []) {
  await page.route("**/api/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    recorded.push({ method: request.method(), path: `${url.pathname}${url.search}`, body: request.postData() ?? "" });
    let body: unknown = { error: "Not recorded in fixture" };
    let status = 404;
    const ok = (value: unknown) => { body = value; status = 200; };
    if (url.pathname === "/api/workspace") ok(workspace);
    else if (url.pathname === "/api/health") ok({ ok: true, status: "ok", version: "0.7.0a1", degraded_reasons: [] });
    else if (url.pathname === "/api/parameters") ok({ parameters: [] });
    else if (url.pathname === "/api/methodology/profiles") ok(catalogue);
    else if (url.pathname === `/api/runs/${preFix.id}`) ok(preFix);
    else if (url.pathname === `/api/runs/${reproduction.id}`) ok(reproduction);
    else if (url.pathname === "/api/projects/resolve-draft") ok({ schema_version: "value.study-draft-resolution/v1", frontend_contract_version: "x", valid: false, errors: [], warnings: [], module_slots: [], compatible_modules: {}, system_domains: [], active_dataset_slots: [], data_readiness: { required: 0, available: 0, missing_roles: [] }, effective_extension_parameters: {}, maturity: { acknowledgement_contract: "x", acknowledgements_required: [] } });
    else if (url.pathname === `/api/projects/${study.id}/preflight`) ok({ project_id: study.id, project_revision_sha256: "rev-2", data_pack_id: study.data_pack_id, accepted: false, mode: JSON.parse(request.postData() ?? "{}").mode, errors: [{ code: "GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED", severity: "error", scope: "project", message: "The installed VALUE computes this Study differently from its saved revision.", corrective_action: "Confirm." }], warnings: [], estimates: {}, checks: { project_revision: { passed: false, classification: migration("value-corrected", "diff-corrected") } } });
    else if (url.pathname === `/api/projects/${study.id}/revision-migration` && request.method() === "GET") {
      const profile = url.searchParams.get("profile_id") ?? "value-corrected";
      ok({ revision_migration: migration(profile, `diff-${profile}`) });
    } else if (url.pathname === `/api/projects/${study.id}/revision-migration` && request.method() === "POST") ok({ ok: true, project: { ...study, revision_number: 2 }, revision_migration: migration("doctoral-lineage-0.6.0a2", "diff-doctoral-lineage-0.6.0a2") });
    else if (url.pathname === "/api/tutorials/value-101") { status = 404; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
}

test("a pre-fix Run shows the failed balance first, never a green passed, and opens residuals in Inspect", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?view=run&study=${study.id}&run=${preFix.id}`);
  const bar = page.getByRole("region", { name: "Selected Run context", exact: true });
  await expect(bar).toContainText("Methodology not recorded (pre-2026-10 run)");
  await expect(bar.locator(".run-context-statuses")).toContainText("Energy balance● Failed");
  await expect(bar.locator(".run-context-statuses")).toContainText("Stress events● 48 periods · 571 MWh");
  await expect(bar.locator(".run-context-statuses")).toContainText("Scientific validation● Superseded");
  await expect(bar.locator(".run-context-check.ok")).toHaveCount(0);
  await expect(bar.locator(".value-callout")).toHaveCount(1);
  await expect(bar.locator(".value-callout.danger")).toContainText("The independent ledger check found 48 periods where supply and use do not reconcile (largest residual 23.4 MWh).");
  await bar.getByRole("button", { name: "+2 more notices" }).click();
  await expect(bar.locator(".value-callout")).toHaveCount(3);
  await bar.getByRole("button", { name: "View advisories (1)" }).click();
  await expect(bar).toContainText("Produced before the 2026-10 review");
  await expect(bar).toContainText("Affected: total system cost gbp");
  // Spec 9.7: the new components pass axe critical/serious checks.
  const scan = await new AxeBuilder({ page }).include(".run-context-profile").include(".run-context-notices").include(".run-context-statuses").analyze();
  expect(scan.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
  await bar.getByRole("button", { name: "Open residuals in Inspect" }).click();
  await expect(page.getByRole("heading", { name: "See what changed and why" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "market" })).toHaveAttribute("aria-selected", "true");
});

test("a withheld doctoral reproduction shows the caution pill, the withheld notice and no annual totals", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?view=run&study=${study.id}&run=${reproduction.id}`);
  const bar = page.getByRole("region", { name: "Selected Run context", exact: true });
  await expect(bar.locator(".value-pill.caution")).toHaveText("Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)");
  await expect(bar.locator(".run-context-statuses")).toContainText("Stress eventsNone");
  await expect(bar.locator(".value-callout.caution")).toContainText("Annual results withheld for this reproduction run");
  await expect(page.locator(".annual-results-withheld")).toContainText("Withheld");
  await expect(page.locator(".annual-results-withheld")).toContainText("(2 computed years)");
  await expect(page.getByText("No annual results yet")).toHaveCount(0);
  await bar.getByRole("button", { name: "Export ledger" }).click();
  await expect(page.getByRole("tab", { name: "Artifacts & provenance" })).toHaveAttribute("aria-selected", "true");
  // Spec 9.8: at 375 px the context bar fits its own width (no horizontal scroll inside it).
  await page.getByRole("button", { name: /Runs: Launch and compare/ }).click();
  await page.setViewportSize({ width: 375, height: 800 });
  await expect(bar.locator(".value-pill.caution")).toBeVisible();
  const overflow = await bar.evaluate((element) => element.scrollWidth - element.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("the composer's Doctoral choice writes the reference preset and disables packs outside the whitelist", async ({ page }) => {
  const recorded: Recorded[] = [];
  await mockApi(page, recorded);
  await page.goto("/?view=projects");
  const methodology = page.getByRole("group", { name: "Methodology" });
  await expect(methodology.getByRole("radio", { name: /Corrected \(default\)/ })).toBeChecked();
  await methodology.getByRole("radio", { name: /Doctoral reproduction/ }).check();
  await expect(page.getByRole("option", { name: /My own pack · not available with this methodology/ })).toHaveAttribute("disabled", "");
  await expect.poll(() => recorded.filter((item) => item.path === "/api/projects/resolve-draft").map((item) => JSON.parse(item.body)).some((body) =>
    body.parameters?.["methodology.profile"] === "doctoral-lineage-0.6.0a2"
    && body.parameters?.["carbon.factor_scenario"] === "doctoral_reproduction_2026_07_18"
    && body.modules?.storage_cost === "value-legacy-storage-tariff")).toBe(true);
  const scan = await new AxeBuilder({ page }).include(".methodology-selector").analyze();
  expect(scan.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
});

test("a method change opens the confirmation dialog; Esc cancels and confirming saves the reviewed diff", async ({ page }) => {
  const recorded: Recorded[] = [];
  await mockApi(page, recorded);
  await page.goto(`/?view=run&study=${study.id}`);
  await page.getByRole("button", { name: "Check readiness" }).click();
  const dialog = page.getByRole("dialog", { name: "This Study needs your confirmation before it runs" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "This Study needs your confirmation before it runs" })).toBeFocused();
  await expect(dialog).toContainText("VALUE 0.7.0a1 changes how this Study is computed:");
  // F-X0-2: the Study matches the doctoral reference preset, so that profile's diff is loaded first.
  await expect(dialog.getByRole("radio", { name: /Doctoral reproduction/ })).toBeChecked();
  await expect(dialog).toContainText("5.1.0 → 5.2.0");
  const scan = await new AxeBuilder({ page }).include(".study-migration-dialog").analyze();
  expect(scan.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("The Study was not changed. It cannot run until the listed changes are confirmed.")).toBeVisible();
  expect(recorded.filter((item) => item.method === "POST" && item.path.endsWith("/revision-migration"))).toEqual([]);
  expect(recorded.filter((item) => item.path.endsWith("/runs") && item.method === "POST")).toEqual([]);
  await page.getByRole("button", { name: "Check readiness" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("radio", { name: /Corrected \(default\)/ }).check();
  await expect(dialog.getByRole("radio", { name: /Corrected \(default\)/ })).toBeChecked();
  await dialog.getByRole("button", { name: "Review and save as new revision" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("Saved as a new revision (revision 2). Check readiness again, then start the Run.")).toBeVisible();
  const posts = recorded.filter((item) => item.method === "POST" && item.path.endsWith("/revision-migration")).map((item) => JSON.parse(item.body));
  expect(posts).toEqual([{ diff_sha256: "diff-value-corrected", profile_id: "value-corrected" }]);
  expect(recorded.some((item) => item.path === `/api/projects/${study.id}/revision-migration?profile_id=doctoral-lineage-0.6.0a2`)).toBe(true);
  expect(recorded.filter((item) => item.path.endsWith("/runs") && item.method === "POST")).toEqual([]);
});
