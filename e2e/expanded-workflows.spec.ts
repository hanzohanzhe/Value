import fs from "node:fs";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const hash = (letter: string) => letter.repeat(64);
// Browser-test screenshots are ephemeral.  The reviewed Prompt 84 evidence in
// publication/ is immutable and must not be rewritten by a normal test run.
const screenshotRoot = "test-results/prompt84-browser-screenshots";

const run = {
  id: "domain-demo", project_id: "domain-project", project_name: "Bounded network fixture", mode: "full",
  status: "completed", current_stage: "Run completed", completed_years: 2, total_years: 2,
  updated_at: "2026-08-20T00:00:00+01:00", results: [], modules: { psm: "value-reference-dc-network" },
};

const modules = [
  { id: "value-bid-at-cost-psm", name: "VALUE bid-at-cost PSM", kind: "psm", slot: "psm", version: "5.1.0", status: "ready", inputs: [], outputs: [], provides_capabilities: ["domain.single-node"] },
  { id: "value-reference-dc-network", name: "Reference chronological DC network PSM", kind: "psm", slot: "psm", version: "1.0.0", status: "ready", inputs: [], outputs: [], provides_capabilities: ["domain.network.dc"] },
  { id: "value-reference-ac-feasibility", name: "Experimental AC feasibility", kind: "psm", slot: "psm", version: "0.1.0", status: "experimental", inputs: [], outputs: [], provides_capabilities: ["domain.network.ac"] },
  { id: "value-copperplate-balancing", name: "Copperplate balancing", kind: "system", slot: "balancing", version: "1.0.0", status: "ready", inputs: [], outputs: [], provides_capabilities: [] },
  { id: "value-zonal-redispatch-balancing", name: "Zonal redispatch balancing", kind: "system", slot: "balancing", version: "2.0.0", status: "experimental", inputs: [], outputs: [], provides_capabilities: ["network.zonal-redispatch-result/v1"] },
];

const psmOptions = modules.filter((item) => item.slot === "psm").map((item) => ({ ...item, compatible: true }));
const balancingOptions = modules.filter((item) => item.slot === "balancing").map((item) => ({ ...item, compatible: true }));

const networkSlots = [
  ["value.network.buses", "Network buses", "CSV"], ["value.network.branches", "Network branches", "CSV"],
  ["value.network.asset-map", "Asset to bus map", "CSV"], ["value.network.nodal-demand", "Nodal demand", "CSV"],
].map(([role, label, format]) => ({ role, label, group: "Network", formats: [format.toLowerCase()], supported_formats: [format.toLowerCase()], required: true, source: "extension", owner_extension: "value-network-contract-extension", template_available: true }));

const extension = {
  id: "value-network-contract-extension", name: "Network contract", version: "1.0.0", licence: "Apache-2.0", namespace: "value.network",
  maturity: "ready", enabled: true, origin: "built_in", provided_capabilities: ["domain.network.dc"], required_capabilities: [],
  composed_module_ids: ["value-reference-dc-network"], data_roles: networkSlots, parameters: [], artifacts: [], hooks: [], manifest_sha256: hash("e"),
};

function resolution(request?: Record<string, unknown>) {
  const selectedModules = (request?.modules as Record<string, string> | undefined) ?? { psm: "value-bid-at-cost-psm" };
  const dc = selectedModules.psm === "value-reference-dc-network";
  return {
    schema_version: "value.frontend-study-resolution/v1", frontend_contract_version: "value.frontend-contract/v1",
    valid: true, errors: [], warnings: [],
    module_slots: [
      { slot: "psm", required: true, contract_version: "value.psm/v2", order: 1, options: psmOptions },
      { slot: "balancing", required: false, contract_version: "value.balancing/v2", order: 2, options: balancingOptions },
    ],
    compatible_modules: { psm: psmOptions, balancing: balancingOptions },
    system_domains: [
      { id: "domain.single-node", title: "Single-node market", claim: "No internal transmission constraints.", psm_module_id: "value-bid-at-cost-psm", psm_name: "VALUE bid-at-cost PSM", description: "Base", maturity: "ready", recommended_modules: { psm: "value-bid-at-cost-psm" }, required_extensions: [], available: true },
      { id: "domain.network.dc", title: "Chronological DC network", claim: "Nodal balance, angles and branch ratings.", psm_module_id: "value-reference-dc-network", psm_name: "Reference chronological DC network PSM", description: "DC", maturity: "ready", recommended_modules: { psm: "value-reference-dc-network" }, required_extensions: ["value-network-contract-extension"], available: true },
      { id: "domain.network.ac-feasibility", title: "Experimental AC feasibility", claim: "Checks a declared schedule; not AC OPF.", psm_module_id: "value-reference-ac-feasibility", psm_name: "Experimental AC feasibility", description: "AC", maturity: "experimental", recommended_modules: { psm: "value-reference-ac-feasibility" }, required_extensions: ["value-network-contract-extension"], available: true },
    ],
    active_dataset_slots: dc ? networkSlots : [], data_readiness: { required: dc ? 4 : 0, available: dc ? 4 : 0, missing_roles: [] },
    effective_extension_parameters: {}, maturity: { acknowledgement_contract: "value.maturity-ack/v1", acknowledgements_required: [] },
    graph_preview: { graph_sha256: hash("g"), modules: Object.fromEntries(Object.entries(selectedModules).map(([slot, module_id]) => [slot, { module_id, module_version: "1.0.0", contract_version: "v2" }])), extension_graph: { extensions: dc ? [{ id: extension.id, version: extension.version }] : [], parameters: {} } },
    graph_sha256: hash("g"),
  };
}

test.beforeEach(async ({ page }) => {
  fs.mkdirSync(screenshotRoot, { recursive: true });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown;
    if (path === "/api/workspace") body = {
      architecture_version: "value.contracts/v2", frontend_contract_version: "value.frontend-contract/v1",
      modules, module_slots: resolution().module_slots, extensions: [extension], dataset_slots: [], module_installations: [], extension_installations: [],
      data_packs: [{ id: "fixture", name: "Synthetic network fixture", country: "GB", timezone: "Europe/London", bindings: Object.fromEntries(networkSlots.map((item) => [item.role, { filename: `${item.role}.csv`, bytes: 100, sha256: hash("d"), imported_at: "2026-08-20", validation: { status: "passed" } }])), required_count: 0, bound_required_count: 0, valid_required_count: 0, binding_issues: {}, complete: true }],
      projects: [], runs: [run], runtime: { python: "3.10.11", compatible: true, selected_capability: "value-native" },
    };
    else if (path === "/api/parameters") body = { parameters: [] };
    else if (path === "/api/projects/resolve-draft") body = resolution(route.request().postDataJSON());
    else if (path === "/api/projects" && route.request().method() === "POST") {
      const submitted = route.request().postDataJSON();
      body = {
        ok: true,
        project: { ...submitted, id: "custom-zonal", revision_number: 2, revision_sha256: hash("r"), updated_at: "2026-08-23T00:00:00+01:00" },
        validation: { errors: [], resolved_parameters: { sources: {} } },
      };
    }
    else if (path === "/api/runs/domain-demo") body = run;
    else if (path.endsWith("/domains/capabilities")) body = { schema_version: "value.domain-result-capabilities/v1", identity: { run_id: run.id, project_revision_sha256: hash("p"), graph_sha256: hash("g") }, capabilities: {
      network_dc: { status: "supported", years: [2025] }, ac_feasibility: { status: "experimental", years: [2025], claim: "Local feasibility of a declared schedule; not AC OPF." },
      hydrology: { status: "not_evaluated", reason: "The ordinary annual application emitted no natural-flow hydrology result artifact; no water quantity is reconstructed." },
      network_expansion: { status: "experimental", reason: null },
    } };
    else if (path.endsWith("/domains/network/summary")) body = { year: 2025, identity: {}, source_artifacts: { declared_input_sha256: hash("i"), period_index_sha256: hash("n"), typed_result_sha256: hash("t") }, metrics: {
      periods: { value: 168, unit: "periods", definition_id: "value.network.period-count/v1" }, blackout_mwh: { value: 0, unit: "MWh", definition_id: "value.network.nodal-blackout-sum/v1" },
      congestion_branch_periods: { value: 24, unit: "branch-periods", definition_id: "value.network.rating-binding-count/v1" }, indexed_nodal_balance_residual: { value: 1e-10, unit: "MWh", definition_id: "value.network.indexed-nodal-balance-audit/v1" },
    }, topology: { buses: [{ bus_id: "North" }, { bus_id: "South" }], branches: [{ branch_id: "NS", from_bus: "North", to_bus: "South", rating_mw: 4 }], reference_buses: ["North"], placement: "schematic_not_geographic" }, branch_summary: [{ branch_id: "NS", from_bus: "North", to_bus: "South", rating_mw: 4, maximum_absolute_flow_mw: 4, maximum_utilisation_fraction: 1 }], storage_soc: { endpoint: "/market/storage", reason: "Linked" } };
    else if (path.endsWith("/domains/network/periods")) body = { year: 2025, total: 168, limit: 24, offset: 0, source_artifact_sha256: hash("n"), definitions: {}, units: {}, items: [{ period_id: "2025:0", injection_mwh: 10, withdrawal_mwh: 10, blackout_mwh: 0, mean_nodal_price: 50, buses: [{ bus_id: "North", injection_mwh: 10, withdrawal_mwh: 0, blackout_mwh: 0, angle_rad: 0, price_gbp_per_mwh: 1 }, { bus_id: "South", injection_mwh: 0, withdrawal_mwh: 10, blackout_mwh: 0, angle_rad: -.04, price_gbp_per_mwh: 100 }] }] };
    else if (path.endsWith("/domains/network/branches")) body = { total: 1, limit: 100, offset: 0, source_artifact_sha256: hash("n"), items: [{ period_id: "2025:0", branch_id: "NS", from_bus: "North", to_bus: "South", flow_mw: 4, rating_mw: 4, utilisation_fraction: 1, utilisation_status: "available" }] };
    else if (path.endsWith("/domains/ac/results")) body = { claim: "Local feasibility of a declared active schedule; not AC OPF.", year: 2025, total: 1, source_artifact_sha256: hash("a"), summary: { solver_status: "optimal", convergence_class: "LOCAL_SOLUTION_VALIDATED", maximum_active_residual_mw: 1e-9, branch_rating_utilisation: { status: "not_evaluated" } }, items: [{ period_id: "2025:0", status: "LOCAL_SOLUTION_VALIDATED", minimum_voltage_pu: .99, maximum_voltage_pu: 1.01, active_loss_mw: .1, branch_mva: { NS: 4.2 }, residuals: { active_mw: 1e-9 }, violations: {} }] };
    else if (path.endsWith("/domains/expansion/summary")) body = { status: "experimental", source_artifact_sha256: hash("x"), lineage: "candidate → proposal → planning → commissioned / failed / retired", counterfactual_claim: "not_claimed_without_a_controlled_comparison_study", years: [{ year: 2025, proposals: 1, admitted: 1, commissioned: 0, failed: 0, retired: 0 }, { year: 2026, proposals: 0, admitted: 0, commissioned: 1, failed: 0, retired: 0 }] };
    else if (path.endsWith("/domains/expansion/events")) body = { total: 1, source_artifact_sha256: hash("x"), items: [{ year: 2026, event_id: "commissioned:NS2", event_type: "commissioned", candidate_id: "NS2", project_id: "project:NS2", asset_id: "line:NS2", corridor_id: "North-South", from_bus: "North", to_bus: "South", circuits: 1, rating_mw: 4, reason_code: "planning_complete" }] };
    else body = { error: `Unmocked API ${path}` };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
});

test("expanded composer and conditional Data stay capability-driven", async ({ page }) => {
  await page.goto("/");
  await page.screenshot({ path: `${screenshotRoot}/01-home.png`, fullPage: true });
  await page.getByRole("button", { name: /Studies/ }).click();
  await page.getByRole("button", { name: /System domain/ }).click();
  await expect(page.getByRole("button", { name: /Chronological DC network/ })).toBeVisible();
  await expect(page.getByText("not AC OPF", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: /Chronological DC network/ }).click();
  await page.screenshot({ path: `${screenshotRoot}/02-study-composer.png`, fullPage: true });
  await page.getByRole("button", { name: /Data:/ }).click();
  await expect(page.getByText("Network buses")).toBeVisible();
  await expect(page.getByText("value.network.nodal-demand", { exact: true })).toBeVisible();
  await page.screenshot({ path: `${screenshotRoot}/03-conditional-data.png`, fullPage: true });
});

test("zonal solver settings require valid ranges and one revision acknowledgement", async ({ page }) => {
  const projectPosts: Record<string, unknown>[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/projects" && request.method() === "POST") {
      projectPosts.push(request.postDataJSON());
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Studies/ }).click();
  await page.getByRole("button", { name: "Review" }).click();
  await expect(page.getByRole("region", { name: "Advanced solver settings" })).toHaveCount(0);

  await page.getByRole("button", { name: "Model chain" }).click();
  await page.getByRole("button", { name: "Advanced", exact: true }).click();
  const balancing = page.locator(".chain-slot").filter({ hasText: "Balancing" });
  await balancing.getByRole("combobox").selectOption("value-zonal-redispatch-balancing");
  await page.getByRole("button", { name: "Review" }).click();

  const editor = page.getByRole("region", { name: "Advanced solver settings" });
  await expect(editor.getByText("Built-in default settings", { exact: true })).toBeVisible();
  await expect(editor.getByLabel("Solver method")).toBeDisabled();
  await expect(editor.getByLabel("Primal feasibility tolerance")).toBeDisabled();
  await editor.getByLabel("Use custom solver settings").check();
  await expect(editor.getByLabel("Solver method")).toBeEnabled();

  const boundedInputs = [
    ["Primal feasibility tolerance", "1e-10", "1e-7"],
    ["Dual feasibility tolerance", "1e-10", "1e-7"],
    ["IPM optimality tolerance", "1e-12", "1e-7"],
    ["Numerical warning threshold", "0", "1"],
    ["Redispatch bid cost validated ceiling", "0", "0.1"],
    ["Schedule deviation validated ceiling", "0", "0.01"],
    ["Physical throughput validated ceiling", "0", "0.01"],
  ] as const;
  for (const [label, minimum, maximum] of boundedInputs) {
    const input = editor.getByLabel(label);
    await expect(input).toHaveAttribute("min", minimum);
    await expect(input).toHaveAttribute("max", maximum);
  }

  const save = page.getByRole("button", { name: "Save this exact Study revision" });
  await editor.getByLabel("Primal feasibility tolerance").fill("0.000001");
  await expect(editor.getByRole("alert")).toContainText("Primal feasibility tolerance must be between 1e-10 and 1e-7");
  await expect(save).toBeDisabled();
  await editor.getByLabel("Primal feasibility tolerance").fill("0.00000001");
  await expect(editor.getByRole("alert")).toHaveCount(0);
  await expect(save).toBeDisabled();

  const acknowledgement = editor.getByLabel(/Saving custom solver settings creates a new study revision/);
  await editor.getByLabel("Physical throughput validated ceiling").focus();
  await page.keyboard.press("Tab");
  await expect(acknowledgement).toBeFocused();
  await page.keyboard.press("Space");
  await expect(save).toBeEnabled();
  const accessibility = await new AxeBuilder({ page }).include(".solver-settings-editor").analyze();
  expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
  await save.click();
  await expect.poll(() => projectPosts.length).toBe(1);
  expect(projectPosts[0].solver_contract).toMatchObject({
    method: "highs-ds",
    primal_feasibility_tolerance: 1e-8,
    is_builtin_default: false,
    requires_acknowledgement: true,
  });
  expect(projectPosts[0].maturity_acknowledgements).toEqual(expect.objectContaining({
    "solver-contract:value-zonal-redispatch-balancing@2.0.0": "value.solver-contract-ack/v1",
  }));
});

test("optional-domain results expose evidence and non-evaluated states", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Network & water/ }).click();
  await expect(page.getByRole("heading", { name: "Nodal balance and constrained transfers" })).toBeVisible();
  await expect(page.getByText("Electrical schematic only", { exact: false })).toBeVisible();
  await expect(page.getByText("168 periods", { exact: true })).toBeVisible();
  await expect(page.getByText("not evaluated", { exact: true }).last()).toBeVisible();
  await page.screenshot({ path: `${screenshotRoot}/04-dc-results.png`, fullPage: true });

  await page.getByRole("tab", { name: "AC feasibility" }).click();
  await expect(page.getByText("Not AC OPF", { exact: true })).toBeVisible();
  await expect(page.getByText("0.1 MW")).toBeVisible();
  await page.screenshot({ path: `${screenshotRoot}/05-ac-feasibility.png`, fullPage: true });

  await page.getByRole("tab", { name: "Transmission expansion" }).click();
  await expect(page.getByText("candidate → proposal → planning → commissioned / failed / retired")).toBeVisible();
  await expect(page.getByText("line:NS2")).toBeVisible();
  await page.screenshot({ path: `${screenshotRoot}/06-transmission-expansion.png`, fullPage: true });

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
});
