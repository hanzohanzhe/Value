import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import path from "node:path";

const run = {
  id: "market-demo", project_id: "demo", project_name: "Market evidence fixture", mode: "full",
  status: "completed", current_stage: "Run completed", completed_years: 1, total_years: 1,
  updated_at: "2026-08-12T00:00:00+01:00", execution_engine: "gridform-annual-orchestrator/v2",
  results: [], diagnostic: { periods_per_year: 4, total_periods: 4, years: [2025], annual_economics_published: false },
};
const flows = [
  { technology: "offshore_wind", flow_type: "generation", evidence_scope: "physical_asset", energy_mwh: 4, balance_component_mwh: 4 },
  { technology: "ccgt", flow_type: "generation", evidence_scope: "physical_asset", energy_mwh: 6, balance_component_mwh: 6 },
];
// The dispatch read model (gridform_core/market_replay.py query_dispatch_timeline)
// returns the bucket price as `price_gbp_per_mwh` with a declared aggregation.
// The price (61.25 + period) deliberately differs from every offer price below
// so that an assertion on it cannot be satisfied by the merit-order table.
const timeline = {
  year: 2025, resolution: "daily", total: 4, limit: 500, offset: 0, source_artifact_sha256: "a".repeat(64),
  period_hours: 0.5, price_aggregation: "demand_weighted_mean_gbp_per_mwh",
  // P0-9 S3: the read model states what the price is (default PSM: total period cost / demand).
  price_basis: "average_period_cost", price_basis_source: "semantics",
  items: Array.from({ length: 4 }, (_, period) => ({
    period_start: period, period_end: period, period_count: 1,
    timestamp_start: `2025-01-01T0${period}:00:00`, timestamp_end: `2025-01-01T0${period}:30:00`,
    real_demand_mwh: 10, accepted_supply_mwh: 10, price_gbp_per_mwh: 61.25 + period,
    storage_charge_mwh: period === 1 ? 1 : 0, storage_discharge_mwh: 0,
    curtailed_mwh: period === 2 ? 1 : 0, excess_mwh: period === 2 ? 2 : 0,
    vre_available_mwh: 5, vre_accepted_mwh: period === 2 ? 4 : 5,
    neutral_unused_vre_mwh: period === 2 ? 1 : 0, blackout_mwh: 0,
    compatibility_adjustment_mwh: 0, flows,
  })),
};

test("market replay and VRE evidence render from versioned bounded APIs", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    let body: unknown;
    if (url.endsWith("/api/workspace")) body = {
      architecture_version: "value.contracts/v2", modules: [], dataset_slots: [],
      // A Study must exist for its Run to be selected: the workspace opens the
      // Run only when run.project_id matches the selected Study.
      projects: [{ id: run.project_id, name: run.project_name, data_pack_id: "fixture", start_year: 2025, end_year: 2025, modules: {}, updated_at: run.updated_at }],
      data_packs: [{ id: "fixture", name: "Fixture", country: "GB", timezone: "Europe/London", bindings: {}, required_count: 0, bound_required_count: 0, valid_required_count: 0, binding_issues: {}, complete: true }],
      runs: [run], runtime: { python: "3.10.11", compatible: true, selected_capability: "value-native" },
    };
    else if (url.endsWith("/api/runs/market-demo")) body = run;
    else if (url.includes("/market/capabilities")) body = {
      years: [2025], trace_level: "full", period_summary: true, physical_dispatch: true, auction_replay: true,
      source_artifact_sha256: "a".repeat(64), auction_stages: [{ stage: "ahead", declared_periods: 4, outcome_periods: 4, order_detail: "complete" }],
    };
    else if (url.includes("/market/auction")) body = {
      year: 2025, period: 0, stage: "ahead", information_scope: "forecast demand and eligible offers", requirement_mwh: 10,
      offers: [
        { offer_id: "wind", asset_id: "wind", asset_type: "VRE", technology: "offshore_wind", offer_price_gbp_per_mwh: 0, offered_mwh: 5, accepted_mwh: 5, asset_accepted_mwh: 5, acceptance_granularity: "offer", execution_order: 0, cumulative_offered_mwh: 5 },
        { offer_id: "gas", asset_id: "gas", asset_type: "GasGenerator", technology: "ccgt", offer_price_gbp_per_mwh: 50, offered_mwh: 8, accepted_mwh: 5, asset_accepted_mwh: 5, acceptance_granularity: "offer", execution_order: 1, cumulative_offered_mwh: 13 },
      ],
      marginal_offer_price_gbp_per_mwh: 50, marginal_offer_status: "defined_from_accepted_outcome_prices",
      offer_acceptance_coverage: "complete", pricing_rule: "fixture", input_sha256: "b".repeat(64), source_artifact_sha256: "a".repeat(64),
    };
    else if (url.includes("/market/vre-summary")) body = {
      years: [{ year: 2025, period_count: 4, full_chronology: false, available_vre_mwh: 20, accepted_vre_mwh: 19, neutral_unused_vre_mwh: 1,
        pre_balancing_excess_mwh: 2, pre_balancing_excess_scope: "inflexible_mixed", balancing_curtailment_mwh: 1,
        vre_utilisation_fraction: .95, average_unused_vre_fraction: .05, affected_periods: 1, longest_event_hours: .5,
        peak_event_mwh: 3, peak_event_timestamp: "2025-01-01T01:00:00", storage_charge_mwh: 1, export_mwh: 0,
        flexible_demand_mwh: 0, vre_identity_residual_mwh: 0, coverage_status: "complete_vre_boundary_with_separate_inflexible_excess",
        marginal_curtailment_status: "not_evaluated", marginal_curtailment_reason: "No marginal-capacity experiment artifact is attached." }],
      excess_relationship: "separate_prebalancing", excess_scope: "inflexible_mixed", source_artifact_sha256: "a".repeat(64),
    };
    else if (url.includes("/market/vre-timeline")) body = timeline;
    else if (url.includes("/market/dispatch")) body = timeline;
    else body = { error: "unmocked API" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Market replay/ }).click();
  await expect(page.getByRole("heading", { name: "Replay bids, then follow the dispatched system" })).toBeVisible();
  await expect(page.getByRole("table").getByText("offshore wind")).toBeVisible();
  await expect(page.getByText("£50/MWh").first()).toBeVisible();
  // R3-01 / Q6: the selected-period strip shows the recorded bucket price under
  // its basis label; an average period cost is never called a clearing price.
  const strip = page.locator(".selected-period-strip");
  await expect(strip).toContainText("£61.25/MWh");
  await expect(strip).toContainText("Average period cost (£/MWh demand)");
  await expect(strip).toContainText("Accepted supply");
  await expect(strip).toContainText("Shortfall");
  await expect(strip).not.toContainText("Clearing price");
  await expect(strip).not.toContainText("£0/MWh"); // a zero offer in the merit-order table is legitimate
  await page.screenshot({ path: test.info().outputPath("prompt56-market-replay.png"), fullPage: true });

  await page.getByRole("button", { name: /VRE & curtailment/ }).click();
  await expect(page.getByRole("heading", { name: "See how much VRE was available, used and left unused" })).toBeVisible();
  await expect(page.getByText("5% unused")).toBeVisible();
  // P0-9 S8 (R3-21): a 20 MWh year is shown in MWh, never as 0 TWh.
  await expect(page.locator(".curtailment-kpis").getByText("20 MWh", { exact: true })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("0 TWh");
  await expect(page.getByText("inflexible mixed", { exact: true })).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
  await page.screenshot({ path: test.info().outputPath("prompt57-vre-curtailment.png"), fullPage: true });
});

// P0-9 S4 (R3-02): a staged (v8) summary-trace Run has no physical_dispatch
// rows but a dispatch summary; the chart stacks its final-dispatch supply.
// The payloads are the generated contract fixtures (real read models).
const contract = (name: string) => JSON.parse(readFileSync(path.join(process.cwd(), "tests", "fixtures", "ui-contract", `${name}.json`), "utf8")).payload;

test("a v8 summary-trace Run draws its final-dispatch supply stack", async ({ page }) => {
  const capabilities = contract("toy-v8.capabilities");
  const daily = contract("toy-v8.dispatch-daily");
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    let body: unknown;
    if (url.endsWith("/api/workspace")) body = {
      architecture_version: "value.contracts/v2", modules: [], dataset_slots: [],
      projects: [{ id: run.project_id, name: run.project_name, data_pack_id: "fixture", start_year: 2025, end_year: 2025, modules: {}, updated_at: run.updated_at }],
      data_packs: [{ id: "fixture", name: "Fixture", country: "GB", timezone: "Europe/London", bindings: {}, required_count: 0, bound_required_count: 0, valid_required_count: 0, binding_issues: {}, complete: true }],
      runs: [run], runtime: { python: "3.10.11", compatible: true, selected_capability: "value-native" },
    };
    else if (url.endsWith("/api/runs/market-demo")) body = run;
    else if (url.includes("/market/capabilities")) body = capabilities;
    else if (url.includes("/market/dispatch")) body = daily;
    else body = { error: "unmocked API" };
    await route.fulfill({ status: url.includes("/market/") || url.endsWith("/api/workspace") || url.endsWith("/api/runs/market-demo") ? 200 : 404, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Market replay/ }).click();
  await expect(page.getByRole("heading", { name: "Replay bids, then follow the dispatched system" })).toBeVisible();
  expect(capabilities.physical_dispatch).toBe(false);
  await expect(page.locator(".evidence-chart rect.dispatch-segment").first()).toBeVisible();
  expect(await page.locator(".evidence-chart rect.dispatch-segment").count()).toBeGreaterThanOrEqual(1);
  await expect(page.locator(".chart-legend")).toContainText("onshore wind");
  await expect(page.locator(".selected-period-strip")).toContainText("Demand-weighted national ahead clearing price");
  await expect(page.locator(".selected-period-strip")).toContainText("£55/MWh");
  await expect(page.getByText("No supply flows recorded for this window")).toHaveCount(0);
});
