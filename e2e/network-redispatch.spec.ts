import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const baseRun = {
  id: "zonal-demo", project_id: "demo", project_name: "Zonal evidence fixture", mode: "full",
  status: "completed", current_stage: "Run completed", completed_years: 1, total_years: 1,
  updated_at: "2026-08-21T00:00:00+01:00", results: [{
    year: 2025,
    metrics: {
      total_system_cost_gbp: 240,
      cost_per_mwh_gbp: 24,
      total_levelized_capital_cost_gbp: 100,
      total_operational_cost_gbp: 140,
      cm_mechanism_cost_gbp: 0,
      decarbonization_mechanism_cost_gbp: 0,
      blackout_mwh: 0,
      imports_mwh: 0,
      storage_charge_mwh: 0,
      storage_discharge_mwh: 0,
      total_carbon_emissions_tco2e: 0,
      carbon_status: "reconciled",
      vre_curtailment_mwh: 4,
      vre_curtailment_rate: 0.2,
      redispatch_net_impact_mwh: -2,
      vre_curtailment_attribution_status: "reconciled",
      vre_curtailment_attribution_reason_code: null,
    },
  }],
  modules: { psm: "value-staged-bid-at-cost-psm", balancing: "value-zonal-redispatch-balancing" },
};

const defaultSolverContract = {
  schema_version: "value.network-solver-contract/v2",
  contract_version: "value.zonal-lexicographic/v2",
  method: "highs-ds",
  presolve: true,
  primal_feasibility_tolerance: 1e-9,
  dual_feasibility_tolerance: 1e-9,
  ipm_optimality_tolerance: 1e-9,
  warning_fraction: 0.1,
  validated_ceilings: {
    primary_bid_cost_gbp: 0.01,
    secondary_schedule_deviation_mwh: 0.001,
    physical_throughput_mwh: 0.001,
  },
  absolute_ceilings: {
    primary_bid_cost_gbp: 0.1,
    secondary_schedule_deviation_mwh: 0.01,
    physical_throughput_mwh: 0.01,
  },
  is_builtin_default: true,
  requires_acknowledgement: false,
} as const;

const candidateSolverSummary = {
  schema_version: "value.solver-validation-summary/v1",
  annual_status: "GO",
  study_status: "solver_stack_not_yet_validated",
  solver_validated: false,
  solver_stack_validation_status: "solver_stack_not_yet_validated",
  inherited_unvalidated: false,
  first_causal_period: {
    year: 2025, period: 0, period_id: "2025:0", phase_id: "primary_bid_cost",
    validation_class: "solver_stack_not_yet_validated",
  },
  row_count: 6,
  warning_periods: 1,
  unvalidated_periods: 0,
  maximum_validated_ceiling_use: 0.08,
  method: "highs-ds",
  solver_contract_version: "value.zonal-lexicographic/v2",
  scipy_version: "1.8.1",
  highs_identity: `scipy-embedded-highs:${"b".repeat(64)}`,
  phases: {},
  detail_view: "solver-diagnostics",
  evidence_status: "valid",
  evidence_errors: [],
};

type CurtailmentFixture = {
  attribution_status: string;
  reason_code: string | null;
  available_mwh: number | null;
  economic_mwh: number | null;
  forecast_added_mwh: number | null;
  forecast_avoided_mwh: number | null;
  redispatch_added_mwh: number | null;
  redispatch_avoided_mwh: number | null;
  redispatch_net_mwh: number | null;
  total_mwh: number | null;
  rate: number | null;
  by_technology: Array<Record<string, string | number>>;
  by_zone_technology: Array<Record<string, string | number>>;
};

const reconciledCurtailment: CurtailmentFixture = {
  attribution_status: "reconciled",
  reason_code: null,
  available_mwh: 20,
  economic_mwh: 5,
  forecast_added_mwh: 1,
  forecast_avoided_mwh: 0,
  redispatch_added_mwh: 2,
  redispatch_avoided_mwh: 4,
  redispatch_net_mwh: -2,
  total_mwh: 4,
  rate: 0.2,
  by_technology: [{
    year: 2025, technology: "Onshore wind", available_mwh: 20, economic_mwh: 5,
    forecast_added_mwh: 1, forecast_avoided_mwh: 0, redispatch_added_mwh: 2,
    redispatch_avoided_mwh: 4, redispatch_net_mwh: -2, total_mwh: 4,
  }],
  by_zone_technology: [{
    year: 2025, zone_id: "north", technology: "Onshore wind", available_mwh: 12,
    economic_mwh: 2, forecast_added_mwh: 1, forecast_avoided_mwh: 0,
    redispatch_added_mwh: 2, redispatch_avoided_mwh: 0, redispatch_net_mwh: 2,
    total_mwh: 5,
  }, {
    year: 2025, zone_id: "south", technology: "Solar", available_mwh: 8,
    economic_mwh: 3, forecast_added_mwh: 0, forecast_avoided_mwh: 0,
    redispatch_added_mwh: 0, redispatch_avoided_mwh: 4, redispatch_net_mwh: -4,
    total_mwh: 0,
  }],
};

type DetailResponse = {
  status?: number;
  body: unknown;
};

type MockNetworkOptions = {
  detailResponse?: (url: URL) => DetailResponse;
  evidenceProbeError?: string;
  /** R-D5: a national-only ledger (zonal tables, no rows) whose annual brief is withheld (Q14). */
  nationalWithheldLedger?: boolean;
  frozenProjectResponse?: DetailResponse;
  frozenSolverContract?: unknown;
  onCapabilitiesRequest?: () => void;
  onAnnualRequest?: () => void;
  onSolverDiagnosticsRequest?: () => void;
  solverDiagnosticsResponse?: (url: URL) => DetailResponse | Promise<DetailResponse>;
  solverSummary?: Record<string, unknown>;
  solverContract?: Record<string, unknown>;
  annualCoverage?: Record<string, unknown>;
  reliabilityEvents?: Record<string, unknown>[];
  /** Generate this many reliability events and page them by the request's offset. */
  reliabilityTotal?: number;
  onReliabilityRequest?: (url: URL) => void;
};

function detailRow(index: number, technology = "Onshore wind") {
  return {
    year: 2025, period: index, period_id: `2025:${index}`, asset_id: `wind-${index.toString().padStart(3, "0")}`,
    owner_id: "wind-owner", bid_tranche_id: "zero-cost", zone_id: index % 2 ? "south" : "north", technology,
    realised_available_vre_mwh: 10, perfect_reference_dispatch_mwh: 8,
    copperplate_reference_dispatch_mwh: 7, zonal_final_dispatch_mwh: 5,
    economic_curtailment_mwh: 2, forecast_added_curtailment_mwh: 1,
    forecast_avoided_curtailment_mwh: 0, redispatch_added_curtailment_mwh: 2,
    redispatch_avoided_curtailment_mwh: 0, redispatch_net_impact_mwh: 2,
    total_curtailment_mwh: 5, evidence_level: "object_tranche",
  };
}

function detailPage(items = [detailRow(0), detailRow(1)], total = items.length, offset = 0): DetailResponse {
  return {
    body: {
      schema_version: "value.zonal-results-page/v1", view: "curtailment-detail",
      total, count: items.length, limit: 250, offset,
      has_more: offset + items.length < total, items,
    },
  };
}

const workspace = (run: typeof baseRun, solverContract: Record<string, unknown> = defaultSolverContract) => ({
  architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [],
  extension_installations: [], module_installations: [], dataset_slots: [], projects: [{
    id: run.project_id, name: run.project_name, data_pack_id: "fixture", start_year: 2025, end_year: 2025,
    modules: run.modules, updated_at: run.updated_at, solver_contract: solverContract,
  }],
  data_packs: [{ id: "fixture", name: "Fixture", country: "GB", timezone: "Europe/London", bindings: {}, required_count: 0, bound_required_count: 0, valid_required_count: 0, binding_issues: {}, complete: true }],
  runs: [run], runtime: { python: "3.10.11", compatible: true, selected_capability: "value-native" },
});

async function mockNetwork(
  page: import("@playwright/test").Page,
  run = baseRun,
  traceLevel: "summary" | "full" = "full",
  curtailment: CurtailmentFixture = reconciledCurtailment,
  options: MockNetworkOptions = {},
) {
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    let body: unknown = { error: "unmocked API" };
    let status = 200;
    const solverSummary = options.solverSummary ?? candidateSolverSummary;
    if (url.endsWith("/api/workspace")) body = workspace(run, options.solverContract);
    else if (url.endsWith(`/api/runs/${run.id}`)) body = run;
    else if (url.endsWith(`/api/runs/${run.id}/artifacts/input-snapshot/project.json`)) {
      const response = options.frozenProjectResponse ?? {
        body: {
          id: run.project_id,
          solver_contract: options.frozenSolverContract ?? options.solverContract ?? defaultSolverContract,
        },
      };
      status = response.status ?? 200;
      body = response.body;
    }
    else if (url.includes("/network-redispatch/capabilities")) {
      options.onCapabilitiesRequest?.();
      if (options.evidenceProbeError) {
        status = 404;
        body = { error: options.evidenceProbeError, error_code: "GF_ZONAL_RESULTS_UNAVAILABLE" };
      } else if (options.nationalWithheldLedger) body = {
        trace_level: traceLevel, years: [], network_pack_id: "", data_pack_id: "", available_views: ["period", "reliability"],
        row_counts: { zonal_period_summary: 0, reliability_event: 0 }, bid_replay_available: false,
      };
      else body = {
      trace_level: traceLevel, years: [2025], network_pack_id: "gb-zones-v1", data_pack_id: "fixture",
      available_views: ["period", "zone", "boundary", "resource", "agent", "reliability", "solver", "solver-diagnostics"],
      row_counts: { zonal_period_summary: 2, network_solver_diagnostics: 6 }, bid_replay_available: traceLevel === "full",
      solver_validation_summary: solverSummary,
      network_semantics: "lossless_computational_transport_with_etys_cutsets",
      boundary_value_semantics: "diagnostic_marginal_value_not_market_price", reliability_semantics: "observed_chronology_not_statistical_lole",
      security_scope: "not_a_security_analysis", unsupported_scope: ["N-1", "voltage_security"],
      };
    }
    else if (url.includes("/network-redispatch/annual")) {
      if (options.nationalWithheldLedger) {
        options.onAnnualRequest?.();
        status = 409;
        body = { status: "withheld", error: "Doctoral reproduction runs publish annual results only when every raw invariant passes; the results remain available in Inspect and exports.", error_code: "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED" };
      } else if (options.evidenceProbeError) {
        status = 404;
        body = { error: options.evidenceProbeError, error_code: "GF_ZONAL_RESULTS_UNAVAILABLE" };
      } else body = { years: [{
      year: 2025, period_count: 2, system_resource_cost_gbp: 240, network_constraint_cost_gbp: 40,
      national_settlement_gbp: 500, redispatch_settlement_gbp: 40, policy_transfer_gbp: 6,
      forecast_error_cost_gbp: 20, total_deviation_cost_gbp: 60,
      vre_curtailment: curtailment,
      unserved_energy_mwh: 1, congested_boundary_periods: 1, maximum_boundary_utilisation_fraction: 1,
      observed_loss_of_load_hours: .5, observed_loss_of_load_events: 1, affected_load_shedding_zones: 1,
      }], solver_validation_summary: solverSummary, reliability_semantics: "observed_chronology_not_statistical_lole", security_scope: "not_a_security_analysis", ...(options.annualCoverage ? { coverage: options.annualCoverage } : {}) };
    }
    else if (url.includes("/network-redispatch/curtailment-detail")) {
      const response = options.detailResponse?.(new URL(url)) ?? detailPage();
      status = response.status ?? 200;
      body = response.body;
    }
    else if (url.includes("/network-redispatch/periods")) body = { view: "period", total: 2, limit: 96, offset: 0, items: [
      { year: 2025, period: 0, period_id: "2025:0", system_resource_cost_gbp: 120, network_constraint_cost_gbp: 20, redispatch_settlement_gbp: 20, blackout_mwh: 0 },
      { year: 2025, period: 1, period_id: "2025:1", system_resource_cost_gbp: 120, network_constraint_cost_gbp: 20, redispatch_settlement_gbp: 20, blackout_mwh: 1 },
    ] };
    else if (url.includes("/network-redispatch/zones")) body = { view: "zone", total: 2, limit: 1000, offset: 0, items: [
      { year: 2025, period: 0, zone_id: "north", demand_mwh: 5, ahead_injection_mwh: 7, final_injection_mwh: 6, signed_adjustment_mwh: -1, load_shedding_mwh: 0, net_position_mwh: 1 },
      { year: 2025, period: 0, zone_id: "south", demand_mwh: 5, ahead_injection_mwh: 3, final_injection_mwh: 4, signed_adjustment_mwh: 1, load_shedding_mwh: 0, net_position_mwh: -1 },
    ] };
    else if (url.includes("/network-redispatch/boundaries")) body = { view: "boundary", total: 1, limit: 1000, offset: 0, items: [{ year: 2025, period: 0, boundary_id: "B1", transfer_mwh: 2, forward_capacity_mwh: 2, reverse_capacity_mwh: 3, utilisation_fraction: 1, boundary_shadow_value_gbp_per_mwh: 4 }] };
    else if (url.includes("/network-redispatch/resources")) body = { view: "resource", total: 1, limit: 1000, offset: 0, items: [{ year: 2025, period: 0, asset_id: "battery", agent_id: "storage-owner", zone_id: "south", technology: "battery", ahead_dispatch_mwh: 0, signed_adjustment_mwh: 1, final_dispatch_mwh: 1, final_soc_mwh: 3, charge_mwh: 0, discharge_mwh: 1, physical_resource_cost_gbp: 20 }] };
    else if (url.includes("/network-redispatch/settlements")) body = { view: "agent", total: 1, limit: 1000, offset: 0, items: [{ year: 2025, period: 0, agent_id: "storage-owner", zone_id: "south", direction: "up", accepted_delta_mwh: 1, bid_price_gbp_per_mwh: 20, cashflow_to_agent_gbp: 20 }] };
    else if (url.includes("/network-redispatch/reliability")) {
      const requested = new URL(url);
      options.onReliabilityRequest?.(requested);
      if (options.reliabilityTotal != null) {
        const total = options.reliabilityTotal;
        const offset = Number(requested.searchParams.get("offset") ?? 0);
        const items = Array.from({ length: Math.max(0, Math.min(50, total - offset)) }, (_, index) => {
          const start = (offset + index) * 10;
          return { event_id: `observed-2025-${start}`, year: 2025, start_period: start, end_period: start, event_duration_hours: .5, unserved_mwh: 1, affected_zones_json: "[\"south\"]" };
        });
        body = { view: "reliability", total, count: items.length, limit: 50, offset, has_more: offset + items.length < total, items };
      } else {
        const items = options.reliabilityEvents ?? [{ event_id: "observed-1", year: 2025, start_period: 1, end_period: 1, event_duration_hours: .5, unserved_mwh: 1, affected_zones_json: "[\"south\"]" }];
        body = { view: "reliability", total: items.length, count: items.length, limit: 50, offset: 0, has_more: false, items };
      }
    }
    else if (url.includes("/market/capabilities")) body = { years: [2025], trace_level: "summary", period_summary: true, physical_dispatch: true, auction_replay: false, storage_state: false, auction_stages: [], price_basis: "national_ahead_clearing_price" };
    else if (url.includes("/market/dispatch")) body = { year: 2025, resolution: "daily", total: 0, limit: 96, offset: 0, items: [] };
    else if (url.includes("/network-redispatch/solver-diagnostics")) {
      options.onSolverDiagnosticsRequest?.();
      const response = options.solverDiagnosticsResponse
        ? await options.solverDiagnosticsResponse(new URL(url))
        : { body: { view: "solver-diagnostics", total: 2, count: 2, limit: 100, offset: 0, has_more: false, items: [
          { year: 2025, period: 0, period_id: "2025:0", phase_id: "primary_bid_cost", objective_unit: "GBP", computed_tolerance: 1e-8, degradation: 0, validated_ceiling: 0.01, validation_class: "GO" },
          { year: 2025, period: 0, period_id: "2025:0", phase_id: "secondary_schedule_deviation", objective_unit: "MWh", computed_tolerance: 1e-9, degradation: 0, validated_ceiling: 0.001, validation_class: "GO" },
        ] } };
      status = response.status ?? 200;
      body = response.body;
    }
    else if (url.includes("/network-redispatch/solver")) body = { view: "solver", total: 1, limit: 1000, offset: 0, items: [{ year: 2025, period: 0, declared_input_sha256: "a".repeat(64), solver_status: "optimal", declaration_artifact_id: "declared.json", solver_artifact_id: "diagnostics.json", failure_artifact_id: null }] };
    else if (url.endsWith("/rerun-copperplate") && route.request().method() === "POST") body = { ok: true, run: { ...run, id: "copperplate-new", status: "queued", modules: { ...run.modules, balancing: "value-copperplate-balancing" } } };
    else status = 404;
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
}

test("compact solver evidence keeps candidate status truthful and loads rows only in Inspect", async ({ page }) => {
  let diagnosticsRequests = 0;
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    onSolverDiagnosticsRequest: () => { diagnosticsRequests += 1; },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const summary = page.getByRole("region", { name: "Solver validation summary" });
  await expect(summary.getByText("Solver stack not yet validated", { exact: true })).toBeVisible();
  await expect(summary.getByText("highs-ds", { exact: true })).toBeVisible();
  await expect(summary.getByText("value.zonal-lexicographic/v2", { exact: true })).toBeVisible();
  await expect(summary.getByText("8%", { exact: true })).toBeVisible();
  await expect(summary.getByText("1 warning period", { exact: true })).toBeVisible();
  await expect(summary.getByRole("link", { name: "Export solver diagnostics" })).toHaveAttribute("href", /view=solver-diagnostics/);
  expect(diagnosticsRequests).toBe(0);
  await expect(page.getByRole("cell", { name: "primary_bid_cost" })).toHaveCount(0);

  await page.getByRole("tab", { name: "Inspect" }).click();
  await expect(page.getByRole("cell", { name: "primary_bid_cost" })).toBeVisible();
  await expect.poll(() => diagnosticsRequests).toBe(1);
});

test("validated, custom and numerically warned solver states remain distinct", async ({ page }) => {
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    solverSummary: {
      ...candidateSolverSummary,
      study_status: "GO",
      solver_validated: true,
      solver_stack_validation_status: "builtin_validated_baseline",
      warning_periods: 0,
      first_causal_period: null,
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await expect(page.getByText("Built-in validated baseline", { exact: true })).toBeVisible();

  await page.unroute("**/api/**");
  const customContract = {
    ...defaultSolverContract,
    method: "highs-ipm" as const,
    is_builtin_default: false as const,
    requires_acknowledgement: true as const,
  };
  await mockNetwork(page, { ...baseRun, id: "custom-warning" }, "full", reconciledCurtailment, {
    solverContract: customContract,
    solverSummary: {
      ...candidateSolverSummary,
      method: "highs-ipm",
      annual_status: "COMPLETED_WITH_NUMERICAL_WARNING",
      study_status: "COMPLETED_WITH_NUMERICAL_WARNING",
      unvalidated_periods: 1,
      maximum_validated_ceiling_use: 1.2,
    },
  });
  await page.reload();
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  const customSummary = page.getByRole("region", { name: "Solver validation summary" });
  await expect(customSummary.getByText("Custom contract — not yet solver validated", { exact: true }).first()).toBeVisible();
  await expect(customSummary.getByText("Completed with numerical warning", { exact: true })).toBeVisible();
  await expect(customSummary.getByText("completed", { exact: true })).toHaveCount(0);
});

test("validated GO-with-warning keeps the built-in stack identity without turning green", async ({ page }) => {
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    solverSummary: {
      ...candidateSolverSummary,
      annual_status: "GO_WITH_NUMERICAL_WARNING",
      study_status: "GO_WITH_NUMERICAL_WARNING",
      solver_validated: true,
      solver_stack_validation_status: "builtin_validated_baseline",
      warning_periods: 1,
      unvalidated_periods: 0,
      inherited_unvalidated: false,
      first_causal_period: null,
    },
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const summary = page.getByRole("region", { name: "Solver validation summary" });
  await expect(summary.getByText("Validated with numerical warning", { exact: true })).toBeVisible();
  await expect(summary.getByText("Built-in validated baseline", { exact: true })).toBeVisible();
  await expect(summary.getByText("Validated evidence", { exact: true })).toHaveCount(0);
});

test("historical result uses its frozen solver contract instead of the current project revision", async ({ page }) => {
  const currentCustomRevision = {
    ...defaultSolverContract,
    method: "highs-ipm",
    is_builtin_default: false,
    requires_acknowledgement: true,
  };
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    solverContract: currentCustomRevision,
    frozenSolverContract: defaultSolverContract,
    solverSummary: {
      ...candidateSolverSummary,
      annual_status: "GO",
      study_status: "GO",
      solver_validated: true,
      solver_stack_validation_status: "builtin_validated_baseline",
      warning_periods: 0,
      first_causal_period: null,
    },
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const summary = page.getByRole("region", { name: "Solver validation summary" });
  await expect(summary.getByText("Built-in validated baseline", { exact: true })).toBeVisible();
  await expect(summary.getByText("Custom contract — not yet solver validated", { exact: true })).toHaveCount(0);
});

for (const malformed of [
  { name: "unavailable", response: { status: 404, body: { error: "snapshot unavailable" } } },
  { name: "malformed", response: { body: { id: baseRun.project_id, solver_contract: { method: "highs-ds" } } } },
  { name: "with unknown top-level field", response: { body: { id: baseRun.project_id, solver_contract: { ...defaultSolverContract, unexpected: true } } } },
]) {
  test(`frozen solver contract ${malformed.name} fails closed`, async ({ page }) => {
    await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
      frozenProjectResponse: malformed.response,
      solverSummary: {
        ...candidateSolverSummary,
        annual_status: "GO",
        study_status: "GO",
        solver_validated: true,
        solver_stack_validation_status: "builtin_validated_baseline",
        warning_periods: 0,
        first_causal_period: null,
      },
    });

    await page.goto("/");
    await page.getByRole("button", { name: /Network & redispatch/ }).click();

    const summary = page.getByRole("region", { name: "Solver validation summary" });
    await expect(summary.getByText("Frozen solver contract unavailable — not solver validated", { exact: true })).toBeVisible();
    await expect(summary.getByText("Validated evidence", { exact: true })).toHaveCount(0);
    await expect(summary.getByText("Built-in validated baseline", { exact: true })).toHaveCount(0);
  });
}

test("unsafe solver evidence states never render as green validation", async ({ page }) => {
  const customContract = {
    ...defaultSolverContract,
    method: "highs-ipm",
    is_builtin_default: false,
    requires_acknowledgement: true,
  };
  const greenSummary = {
    ...candidateSolverSummary,
    annual_status: "GO",
    study_status: "GO",
    solver_validated: true,
    solver_stack_validation_status: "builtin_validated_baseline",
    warning_periods: 0,
    unvalidated_periods: 0,
    inherited_unvalidated: false,
    first_causal_period: null,
  };
  const cases = [
    {
      id: "failed-run", run: { ...baseRun, status: "failed" }, summary: greenSummary,
      contract: defaultSolverContract, label: "Run not successfully completed",
    },
    {
      id: "invalid-evidence", run: baseRun, summary: { ...greenSummary, evidence_status: "invalid", evidence_errors: ["broken group"] },
      contract: defaultSolverContract, label: "Solver evidence invalid",
    },
    {
      id: "not-recorded", run: baseRun, summary: { ...greenSummary, annual_status: "NOT_RECORDED", study_status: "NOT_RECORDED", evidence_status: "not_recorded" },
      contract: defaultSolverContract, label: "Solver evidence not recorded",
    },
    {
      id: "custom-contract", run: baseRun, summary: greenSummary,
      contract: customContract, label: "Custom solver contract",
    },
    {
      id: "completed-warning", run: baseRun, summary: { ...greenSummary, annual_status: "COMPLETED_WITH_NUMERICAL_WARNING", study_status: "COMPLETED_WITH_NUMERICAL_WARNING", unvalidated_periods: 1 },
      contract: defaultSolverContract, label: "Completed with numerical warning",
    },
    {
      id: "go-warning", run: baseRun, summary: { ...greenSummary, annual_status: "GO_WITH_NUMERICAL_WARNING", study_status: "GO_WITH_NUMERICAL_WARNING", warning_periods: 1 },
      contract: defaultSolverContract, label: "Validated with numerical warning",
    },
    {
      id: "stack-pending", run: baseRun, summary: { ...greenSummary, study_status: "solver_stack_not_yet_validated", solver_validated: false, solver_stack_validation_status: "solver_stack_not_yet_validated", inherited_unvalidated: true },
      contract: defaultSolverContract, label: "Validation pending",
    },
    {
      id: "unknown-status", run: baseRun, summary: { ...greenSummary, annual_status: "UNKNOWN", study_status: "UNKNOWN", evidence_status: "unknown", solver_stack_validation_status: "unknown" },
      contract: defaultSolverContract, label: "Solver validation status unavailable",
    },
    {
      id: "malformed-errors", run: baseRun, summary: { ...greenSummary, evidence_errors: undefined },
      contract: defaultSolverContract, label: "Solver validation status unavailable",
    },
    {
      id: "malformed-row-count", run: baseRun, summary: { ...greenSummary, row_count: "1" },
      contract: defaultSolverContract, label: "Solver validation status unavailable",
    },
    {
      id: "wrong-summary-schema", run: baseRun, summary: { ...greenSummary, schema_version: "value.solver-validation-summary/v2" },
      contract: defaultSolverContract, label: "Solver validation status unavailable",
    },
    {
      id: "missing-summary-method", run: baseRun, summary: { ...greenSummary, method: undefined },
      contract: defaultSolverContract, label: "Solver validation status unavailable",
    },
    {
      id: "wrong-summary-contract-version", run: baseRun, summary: { ...greenSummary, solver_contract_version: "value.zonal-lexicographic/v2" },
      contract: defaultSolverContract, label: "Solver validation status unavailable",
    },
    {
      id: "non-finite-ceiling-use", run: baseRun, summary: { ...greenSummary, maximum_validated_ceiling_use: "not-a-number" },
      contract: defaultSolverContract, label: "Solver validation status unavailable",
    },
  ];

  for (const [index, item] of cases.entries()) {
    if (index) await page.unroute("**/api/**");
    const run = { ...item.run, id: item.id };
    await mockNetwork(page, run, "full", reconciledCurtailment, {
      frozenSolverContract: item.contract,
      solverSummary: item.summary,
    });
    await page.goto("/");
    await page.getByRole("button", { name: /Network & redispatch/ }).click();
    const summary = page.getByRole("region", { name: "Solver validation summary" });
    await expect(summary.getByText(item.label, { exact: true })).toBeVisible();
    await expect(summary.getByText("Validated evidence", { exact: true })).toHaveCount(0);
    await expect(summary.getByText("NaN%", { exact: true })).toHaveCount(0);
  }
});

test("solver diagnostic pagination clears stale rows while the next bounded page loads", async ({ page }) => {
  let resolveSecondPage!: (response: DetailResponse) => void;
  const secondPage = new Promise<DetailResponse>((resolve) => { resolveSecondPage = resolve; });
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    solverDiagnosticsResponse: (url) => Number(url.searchParams.get("offset")) === 0
      ? { body: {
        view: "solver-diagnostics", total: 101, count: 1, limit: 100, offset: 0, has_more: true,
        items: [{ year: 2025, period: 0, period_id: "2025:0", phase_id: "primary_bid_cost", objective_unit: "GBP", computed_tolerance: 1e-8, degradation: 0, validated_ceiling: 0.01, validation_class: "GO" }],
      } }
      : secondPage,
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await page.getByRole("tab", { name: "Inspect" }).click();
  await expect(page.getByRole("cell", { name: "primary_bid_cost" })).toBeVisible();
  await page.getByRole("button", { name: "Next solver diagnostics page" }).click();
  try {
    await expect(page.getByRole("cell", { name: "primary_bid_cost" })).toHaveCount(0);
    await expect(page.getByText("Loading solver diagnostics…", { exact: true })).toBeVisible();
  } finally {
    resolveSecondPage({ body: {
      view: "solver-diagnostics", total: 101, count: 1, limit: 100, offset: 100, has_more: false,
      items: [{ year: 2025, period: 100, period_id: "2025:100", phase_id: "physical_throughput", objective_unit: "MWh", computed_tolerance: 1e-9, degradation: 0, validated_ceiling: 0.001, validation_class: "GO" }],
    } });
  }
  await expect(page.getByRole("cell", { name: "physical_throughput" })).toBeVisible();
});

test("network workspace separates physical redispatch, settlements and reliability", async ({ page }) => {
  await mockNetwork(page);
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await expect(page.getByRole("heading", { name: "Network & redispatch", level: 2 })).toBeVisible();
  await expect(page.getByText("National ahead market", { exact: true })).toBeVisible();
  await expect(page.getByText("£240", { exact: true }).first()).toBeVisible();
  await page.getByRole("tab", { name: "Period replay" }).click();
  await expect(page.getByRole("cell", { name: "B1", exact: true })).toBeVisible();
  await expect(page.getByText("battery", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Storage state after redispatch")).toBeVisible();
  await page.getByRole("tab", { name: "Reliability" }).click();
  await expect(page.getByText("Observed chronology, not statistical LOLE.")).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
});

test("curtailment attribution shows signed steps, annual zone summary and object evidence", async ({ page }) => {
  await mockNetwork(page);
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const attribution = page.getByRole("region", { name: "VRE curtailment attribution" });
  await expect(attribution.getByText("Economic curtailment", { exact: true })).toBeVisible();
  await expect(attribution.getByText("Forecast added", { exact: true })).toBeVisible();
  await expect(attribution.getByText("Forecast avoided", { exact: true })).toBeVisible();
  await expect(attribution.getByText("Redispatch added", { exact: true })).toBeVisible();
  await expect(attribution.getByText("Redispatch avoided", { exact: true })).toBeVisible();
  const waterfall = attribution.getByLabel("Five signed VRE curtailment attribution steps");
  await expect(waterfall.getByText("−4 MWh", { exact: true })).toBeVisible();
  await expect(attribution.getByText("Redispatch net impact", { exact: true })).toBeVisible();
  await expect(attribution.getByText("−2 MWh", { exact: true })).toBeVisible();
  await expect(attribution.getByText("Final VRE curtailment", { exact: true }).last()).toBeVisible();

  await attribution.getByRole("combobox", { name: "Technology" }).selectOption("Onshore wind");
  const zoneSummary = attribution.getByRole("region", { name: "Zone and technology summary" });
  await expect(zoneSummary.getByRole("row", { name: /north Onshore wind/ })).toBeVisible();
  await expect(zoneSummary.getByRole("row", { name: /south Solar/ })).toHaveCount(0);
  const objectEvidence = attribution.getByRole("region", { name: "Object and tranche evidence" });
  await expect(objectEvidence.getByRole("cell", { name: /wind-000/ })).toBeVisible();
  await expect(objectEvidence.getByText("2 of 2 object/tranche rows", { exact: true })).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
});

test("legacy curtailment explains unavailable avoided values without zero placeholders", async ({ page }) => {
  const legacyCurtailment: CurtailmentFixture = {
    attribution_status: "legacy_partial",
    reason_code: "legacy_contract_did_not_measure_avoided_curtailment",
    available_mwh: null,
    economic_mwh: null,
    forecast_added_mwh: null,
    forecast_avoided_mwh: null,
    redispatch_added_mwh: null,
    redispatch_avoided_mwh: null,
    redispatch_net_mwh: null,
    total_mwh: 6,
    rate: null,
    by_technology: [],
    by_zone_technology: [],
  };
  await mockNetwork(page, baseRun, "full", legacyCurtailment);
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const attribution = page.getByRole("region", { name: "VRE curtailment attribution" });
  await expect(attribution.getByText("Legacy result — avoided curtailment was not calculated", { exact: true })).toBeVisible();
  await expect(attribution.getByText("0 MWh", { exact: true })).toHaveCount(0);
});

test("run without recorded attribution explains the production annual reason", async ({ page }) => {
  const unavailableCurtailment: CurtailmentFixture = {
    attribution_status: "not_recorded",
    reason_code: "attribution_evidence_not_recorded",
    available_mwh: null,
    economic_mwh: null,
    forecast_added_mwh: null,
    forecast_avoided_mwh: null,
    redispatch_added_mwh: null,
    redispatch_avoided_mwh: null,
    redispatch_net_mwh: null,
    total_mwh: null,
    rate: null,
    by_technology: [],
    by_zone_technology: [],
  };
  await mockNetwork(page, baseRun, "full", unavailableCurtailment);
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const attribution = page.getByRole("region", { name: "VRE curtailment attribution" });
  await expect(attribution.getByText("Attribution unavailable — this run did not record v2 curtailment evidence.", { exact: true })).toBeVisible();
  await expect(attribution.getByText("0 MWh", { exact: true })).toHaveCount(0);
});

test("object and tranche evidence reaches rows after the first bounded page", async ({ page }) => {
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    detailResponse: (url) => {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return offset === 250
        ? detailPage([detailRow(250)], 251, 250)
        : detailPage(Array.from({ length: 250 }, (_, index) => detailRow(index)), 251, 0);
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const evidence = page.getByRole("region", { name: "Object and tranche evidence" });
  await expect(evidence.getByRole("cell", { name: /wind-000 zero-cost/ })).toBeVisible();
  await evidence.getByRole("button", { name: "Next object evidence page" }).click();
  await expect(evidence.getByRole("cell", { name: /wind-250 zero-cost/ })).toBeVisible();
  await expect(evidence.getByRole("button", { name: "Previous object evidence page" })).toBeEnabled();
  await expect(evidence.getByRole("button", { name: "Next object evidence page" })).toBeDisabled();
});

test("object evidence failure is not reported as an empty scientific result", async ({ page }) => {
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    detailResponse: () => ({ status: 500, body: { error: "object evidence query failed" } }),
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const evidence = page.getByRole("region", { name: "Object and tranche evidence" });
  await expect(evidence.getByRole("alert")).toContainText("object evidence query failed");
  await expect(evidence.getByText("No object/tranche rows match", { exact: false })).toHaveCount(0);
});

test("successful object evidence selection clears its prior scoped error", async ({ page }) => {
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    detailResponse: (url) => url.searchParams.get("technology") === "Onshore wind"
      ? detailPage([detailRow(0)], 1)
      : { status: 500, body: { error: "total detail unavailable" } },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  const attribution = page.getByRole("region", { name: "VRE curtailment attribution" });
  const evidence = attribution.getByRole("region", { name: "Object and tranche evidence" });
  await expect(evidence.getByRole("alert")).toContainText("total detail unavailable");
  await attribution.getByRole("combobox", { name: "Technology" }).selectOption("Onshore wind");
  await expect(evidence.getByRole("cell", { name: /wind-000 zero-cost/ })).toBeVisible();
  await expect(evidence.getByRole("alert")).toHaveCount(0);
});

test("conforming third-party balancing module displays its zonal ledger", async ({ page }) => {
  const thirdParty = { ...baseRun, id: "third-party-zonal", modules: { ...baseRun.modules, balancing: "external-zonal-balancing" } };
  await mockNetwork(page, thirdParty);
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  await expect(page.getByRole("heading", { name: "Network & redispatch", level: 2 })).toBeVisible();
  await expect(page.getByText("National ahead market", { exact: true })).toBeVisible();
  await expect(page.getByText("Copperplate run", { exact: true })).toHaveCount(0);
});

test("unknown balancing module with no zonal evidence is not labelled copperplate", async ({ page }) => {
  const unknown = { ...baseRun, id: "unknown-balancing", modules: { ...baseRun.modules, balancing: "external-unknown-balancing" } };
  await mockNetwork(page, unknown, "full", reconciledCurtailment, { evidenceProbeError: "network redispatch ledger is not available" });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();

  await expect(page.getByText("No zonal network evidence is available for this run.", { exact: true })).toBeVisible();
  await expect(page.getByText("Copperplate run", { exact: true })).toHaveCount(0);
});

test("run page keeps only compact v2 curtailment attribution metrics", async ({ page }) => {
  await mockNetwork(page);
  await page.goto("/");
  // The Study card for the fixture is itself a button whose text contains
  // "Runs"; target the sidebar navigation entry by its exact accessible name.
  await page.getByRole("button", { name: "Runs: Launch and compare" }).click();

  await expect(page.getByText("Final VRE curtailment", { exact: true })).toBeVisible();
  await expect(page.getByText("VRE curtailment rate", { exact: true })).toBeVisible();
  await expect(page.getByText("Redispatch net impact", { exact: true })).toBeVisible();
  await expect(page.getByText("20%", { exact: true })).toBeVisible();
  await expect(page.getByText("Economic curtailment", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Redispatch avoided", { exact: true })).toHaveCount(0);
});

test("failed zonal run creates a separate copperplate run", async ({ page }) => {
  const failedRun = { ...baseRun, status: "failed" as const, error_code: "GF_ZONAL_SOLVER", error: "Infeasible declared input" };
  await mockNetwork(page, failedRun);
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await page.getByRole("button", { name: /Rerun as copperplate/ }).click();
  await expect(page.getByRole("status")).toContainText("Created new copperplate run copperplate-new");
});

test("summary trace keeps annual evidence but explains missing bid rows", async ({ page }) => {
  await mockNetwork(page, baseRun, "summary");
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await page.getByRole("tab", { name: "Period replay" }).click();
  await expect(page.getByText("Bid rows were not retained")).toBeVisible();
  await expect(page.getByText("Annual scientific totals remain available.", { exact: false })).toBeVisible();
});

// R-D5 (four-role report, round R1-5): a Run that selected no balancing module
// cleared one national market; its ledger has the zonal tables but no rows.
// It is labelled copperplate, the annual brief is not requested, and the
// withheld reason is not glued to a "no zonal ledger" sentence.
test("national-only withheld run is copperplate with one reason", async ({ page }) => {
  const national = { ...baseRun, id: "national-doctoral", modules: { psm: "value-bid-at-cost-psm" } };
  let annualRequested = false;
  await mockNetwork(page, national, "full", reconciledCurtailment, { nationalWithheldLedger: true, onAnnualRequest: () => { annualRequested = true; } });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await expect(page.getByText("Copperplate run", { exact: true })).toBeVisible();
  await expect(page.getByText("selected no network balancing module", { exact: false })).toBeVisible();
  await expect(page.getByText("Doctoral reproduction runs publish", { exact: false })).toHaveCount(0);
  await expect(page.getByText("network evidence pending", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open Market replay →" })).toBeVisible();
  expect(annualRequested).toBe(false);
});

test("copperplate run shows a truthful empty network workspace", async ({ page }) => {
  const copperplate = { ...baseRun, id: "copperplate-demo", modules: { ...baseRun.modules, balancing: "value-copperplate-balancing" } };
  let capabilitiesRequested = false;
  await mockNetwork(page, copperplate, "full", reconciledCurtailment, {
    evidenceProbeError: "this run has no zonal redispatch results",
    onCapabilitiesRequest: () => { capabilitiesRequested = true; },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await expect.poll(() => capabilitiesRequested).toBe(true);
  await expect(page.getByText("This run used copperplate balancing.", { exact: false })).toBeVisible();
  await expect(page.getByText("Copperplate run", { exact: true })).toBeVisible();
});

// P0-9 S5/S6 (F3-02, F3-07): a cancelled full-year Run at 16.6 % is not an
// annual result; its reliability list covers the whole year and each event
// opens Market replay at its own window.
test("partial-year coverage withholds annual totals and full-year events replay at their window", async ({ page }) => {
  const reliabilityQueries: URL[] = [];
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    annualCoverage: {
      schema_version: "value.result-coverage/v1", annual_status: "partial", reason_code: "run_cancelled_before_full_coverage",
      coverage_fraction: 2908 / 17520, coverage_percent: 16.6, expected_years: [2025], observed_years: [2025],
      years: [{ year: 2025, first_period: 0, last_period: 2907, period_count: 2908, coverage_fraction: 2908 / 17520, complete: false }],
    },
    reliabilityEvents: [{ event_id: "observed-2025-5000-5001", year: 2025, start_period: 5000, end_period: 5001, observed_half_hours: 2, event_duration_hours: 1, unserved_mwh: 7, affected_zones_json: "[\"north\"]" }],
    onReliabilityRequest: (url) => reliabilityQueries.push(url),
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await expect(page.getByRole("region", { name: "Annual coverage" })).toContainText("Stopped · 16.6%");
  await expect(page.getByText("Compact annual read model")).toHaveCount(0);
  await expect(page.getByRole("alert").filter({ hasText: "Annual totals not shown" })).toBeVisible();
  await page.getByRole("tab", { name: "Reliability" }).click();
  const list = page.getByRole("region", { name: "Stress events and lost load" });
  await expect(list.getByRole("heading", { name: "Stress events and lost load — full year 2025" })).toBeVisible();
  await expect(list.getByText("period 5000")).toBeVisible();
  expect(reliabilityQueries.at(-1)?.searchParams.get("period_from")).toBeNull();
  await list.getByRole("button", { name: "Replay the event starting at period 5000" }).click();
  await expect(page.getByRole("heading", { name: "Replay bids, then follow the dispatched system" })).toBeVisible();
  await expect(page.getByLabel("First period")).toHaveValue("4996");
});

// Review response (plan 6.9, S6): paging the year's reliability list makes one
// request per page change and never repeats a request on its own.
test("paging the reliability list requests each page once", async ({ page }) => {
  const reliabilityQueries: URL[] = [];
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, { reliabilityTotal: 120, onReliabilityRequest: (url) => reliabilityQueries.push(url) });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await page.getByRole("tab", { name: "Reliability" }).click();
  const list = page.getByRole("region", { name: "Stress events and lost load" });
  await expect(list.getByText("period 490", { exact: true })).toBeVisible();
  await list.getByRole("button", { name: "Next events" }).click();
  await expect(list.getByText("period 500", { exact: true })).toBeVisible();
  await list.getByRole("button", { name: "Previous events" }).click();
  await expect(list.getByText("period 0", { exact: true })).toBeVisible();
  await page.waitForTimeout(1_000);
  expect(reliabilityQueries.map((url) => url.searchParams.get("offset"))).toEqual(["0", "50", "0"]);
});

// Review response (S6): the network page publishes the selected year by the
// same per-year rule as the Runs page; a complete year inside a cancelled Run
// keeps its annual totals.
test("a complete year of a cancelled Run shows its annual totals on the network page", async ({ page }) => {
  await mockNetwork(page, baseRun, "full", reconciledCurtailment, {
    annualCoverage: {
      schema_version: "value.result-coverage/v1", annual_status: "partial", reason_code: "run_cancelled_before_full_coverage",
      coverage_fraction: 0.583, coverage_percent: 58.3, expected_years: [2025, 2026], observed_years: [2025, 2026],
      years: [
        { year: 2025, first_period: 0, last_period: 17519, period_count: 17520, coverage_fraction: 1, complete: true },
        { year: 2026, first_period: 0, last_period: 2907, period_count: 2908, coverage_fraction: 2908 / 17520, complete: false },
      ],
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Network & redispatch/ }).click();
  await expect(page.getByRole("region", { name: "Annual coverage" })).toContainText("Stopped · 58.3%");
  await expect(page.getByText("Final physical resource cost").first()).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "Annual totals not shown" })).toHaveCount(0);
});
