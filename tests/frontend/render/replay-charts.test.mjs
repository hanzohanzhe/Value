import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// W4c (P1 spec 2.1, 6.5): Market replay's charts are ChartFrames - pixel SVG
// with 12 px text, the technology palette (patterns where colours repeat), an
// HTML legend and a "Show data table" toggle; bucket times read as UTC.
const VIEW = "app/features/market/MarketReplayView.tsx";
const flows = [
  { technology: "offshore_wind", flow_type: "generation", evidence_scope: "physical_asset", energy_mwh: 4, role: "supply" },
  { technology: "ccgt", flow_type: "generation", evidence_scope: "physical_asset", energy_mwh: 6, role: "supply" },
];
const timeline = {
  year: 2025, resolution: "half_hour", total: 2, limit: 96, offset: 0, period_hours: 0.5, timezone: "UTC",
  items: [0, 1].map((period) => ({ period_start: period, period_end: period, period_count: 1, timestamp_start: `2025-01-01T0${period}:00:00Z`, timestamp_end: `2025-01-01T0${period}:30:00Z`, real_demand_mwh: 10, accepted_supply_mwh: 10, price_gbp_per_mwh: 50, storage_charge_mwh: 0, storage_discharge_mwh: 0, curtailed_mwh: 0, excess_mwh: 0, vre_available_mwh: 4, vre_accepted_mwh: 4, blackout_mwh: 0, compatibility_adjustment_mwh: 0, flows, stress_periods: period, shortfall_mwh: period ? 1 : 0 })),
};

test("the dispatch chart draws pixel bars in the palette with an HTML legend and a table toggle", async () => {
  const html = await renderTsx(VIEW, "DispatchChart", { timeline, selectedPeriod: 1, onSelect() {}, width: 640 });
  assert.match(html, /<figure class="v-chart evidence-chart dispatch-chart">/);
  assert.match(html, /<svg class="v-chart__svg" width="640" height="300" role="img" aria-label="Stacked supply by technology and the demand line for 2 buckets from 2025-01-01 00:00 UTC to 2025-01-01 01:30 UTC\.">/);
  assert.doesNotMatch(html, /viewBox/);
  assert.match(html, /<li><span class="v-swatch v-swatch--hatch" style="--swatch:var\(--tech-wind\)" aria-hidden="true"><\/span><span>offshore wind<\/span><\/li>/);
  assert.match(html, /<span>ccgt<\/span>/);
  assert.match(html, /<span>Stress event \(shortfall\)<\/span>/);
  assert.match(html, /class="dispatch-segment"[^>]*fill="url\(#v-chart-[^)]*-offshore_wind\)"/);
  assert.match(html, /class="dispatch-segment"[^>]*fill="var\(--tech-gas\)"/);
  assert.match(html, /aria-expanded="false"[^>]*>Show data table<\/button>/);
  assert.match(html, /<text[^>]*>00:00<\/text>/);
  assert.doesNotMatch(html, /#[0-9a-f]{6}/i, "no raw hex colour");
});

test("the merit-order chart is a ChartFrame with requirement and marginal-price lines", async () => {
  const auction = { year: 2025, period: 0, stage: "ahead", information_scope: "x", requirement_mwh: 10, marginal_offer_price_gbp_per_mwh: 50, marginal_offer_status: "x", offer_acceptance_coverage: "complete", pricing_rule: "x", input_sha256: "b",
    offers: [{ offer_id: "w", asset_id: "wind", technology: "offshore_wind", offer_price_gbp_per_mwh: 0, offered_mwh: 5, accepted_mwh: 5, acceptance_granularity: "offer", execution_order: 0 }, { offer_id: "g", asset_id: "gas", technology: "ccgt", offer_price_gbp_per_mwh: 50, offered_mwh: 8, accepted_mwh: 5, acceptance_granularity: "offer", execution_order: 1 }] };
  const html = await renderTsx(VIEW, "MeritOrderChart", { auction, width: 500 });
  assert.match(html, /<figure class="v-chart merit-chart">/);
  assert.match(html, /<span class="v-chart__title">ahead merit order<\/span>/);
  assert.match(html, /class="requirement-line"/);
  assert.match(html, /class="price-line"/);
  assert.match(html, /v-swatch--line v-swatch--dashed[^>]*><\/span><span>Requirement<\/span>/);
  assert.match(html, /height="220"/, "below 600 px the chart is 220 px high");
});
