import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// Review response (plan 6.9; F3-06, spec principle 1): a missing network value
// renders "—" on its own, never "— MWh", "£—/MWh" or £0.
const VIEW = "app/features/network/NetworkRedispatchView.tsx";
const MAP = "app/features/network/NetworkZoneMap.tsx";

function assertNoUnitOnDash(text) {
  assert.doesNotMatch(text, /— ?(?:MWh|MW|%|h\b)/);
  assert.doesNotMatch(text, /£—/);
  assert.doesNotMatch(text, /£0(?![.\d])/);
}

test("the zone map shows — for a missing demand, net position, transfer and use", async () => {
  const text = textOf(await renderTsx(MAP, "default", {
    zones: [{ zone_id: "Z1", demand_mwh: 1250.5 }, { zone_id: "Z2" }],
    boundaries: [{ boundary_id: "B6", transfer_mwh: null, utilisation_fraction: null }],
  }));
  assert.match(text, /Z1 1,250.5 MWh demand — net position — load shed/);
  assert.match(text, /Z2 — demand — net position/);
  assert.match(text, /B6 — transfer — used/);
  assertNoUnitOnDash(text);
});

test("network tables render missing rows as — and keep units on recorded values", async () => {
  const boundary = textOf(await renderTsx(VIEW, "BoundaryUseTable", { rows: [{ boundary_id: "B6", transfer_mwh: 10, forward_capacity_mwh: null, utilisation_fraction: 0.5 }] }));
  // W4c (F3-13): the transfer carries its direction arrow; limits are in MW.
  assert.match(boundary, /B6 → 10 MWh — — 50% Not computed/);
  const resources = textOf(await renderTsx(VIEW, "ResourceDispatchTable", { rows: [{ asset_id: "ccgt-1", zone_id: "Z1", technology: "gas", ahead_dispatch_mwh: null, signed_adjustment_mwh: -2, final_dispatch_mwh: null, physical_resource_cost_gbp: null }] }));
  assert.match(resources, /ccgt-1 Z1 gas — -2 MWh — —$/);
  const storage = textOf(await renderTsx(VIEW, "StorageStateTable", { rows: [{ asset_id: "bess-1", final_soc_mwh: null, charge_mwh: 0, discharge_mwh: null }] }));
  assert.match(storage, /bess-1 — 0 MWh —$/);
  const settlements = textOf(await renderTsx(VIEW, "SettlementTable", { rows: [{ agent_id: "a", zone_id: "Z1", direction: "up", accepted_delta_mwh: null, bid_price_gbp_per_mwh: null, cashflow_to_agent_gbp: null }] }));
  assert.match(settlements, /a Z1 up — — —$/);
  for (const text of [boundary, resources, storage, settlements]) assertNoUnitOnDash(text);
});

test("the preflight card says when no runtime estimate exists (R3-03)", async () => {
  const RUNS = "app/features/runs/RunWorkspace.tsx";
  const missing = textOf(await renderTsx(RUNS, "PreflightEstimates", { estimates: { periods: 17520, disk_bytes: 2 * 1024 ** 3, peak_memory_bytes: 512 * 1024 ** 2 } }));
  assert.equal(missing, "17,520 periods · about 2.00 GB disk · about 512.0 MB peak memory · Runtime estimate not available");
  const estimated = textOf(await renderTsx(RUNS, "PreflightEstimates", { estimates: { periods: 48, disk_bytes: 1024, peak_memory_bytes: 1024, runtime_seconds: 5400 } }));
  assert.match(estimated, /estimated about 1\.5 hours$/);
  assert.doesNotMatch(textOf(await renderTsx(RUNS, "PreflightEstimates", { estimates: {} })), /— periods|0 hours/);
});

// F3-13 (display part, W4c): limits per period are shown as MW, the transfer
// with its direction, and the map names the sign conventions.
test("boundary limits are shown in MW and transfers with their direction; the map has a sign legend", async () => {
  const boundary = textOf(await renderTsx(VIEW, "BoundaryUseTable", { periodHours: 0.5, rows: [{ boundary_id: "B6", transfer_mwh: -1.07, forward_capacity_mwh: 5, reverse_capacity_mwh: 2.5, utilisation_fraction: 0.428, boundary_shadow_value_gbp_per_mwh: null }] }));
  assert.match(boundary, /Transfer \(→ forward \/ ← reverse\) Forward limit \(MW\) Reverse limit \(MW\)/);
  assert.match(boundary, /B6 ← 1\.07 MWh 10 MW 5 MW 42\.8% Not computed/);
  const hourly = textOf(await renderTsx(VIEW, "BoundaryUseTable", { periodHours: 1, rows: [{ boundary_id: "B7", transfer_mwh: 3, forward_capacity_mwh: 5, reverse_capacity_mwh: 5, utilisation_fraction: 0.6 }] }));
  assert.match(hourly, /B7 → 3 MWh 5 MW 5 MW 60%/);
  const map = textOf(await renderTsx(MAP, "default", { zones: [{ zone_id: "Z1", demand_mwh: 5, net_position_mwh: -1, load_shedding_mwh: 0.5 }], boundaries: [{ boundary_id: "B6", transfer_mwh: 2, utilisation_fraction: 1 }] }));
  assert.match(map, /→ forward · ← reverse/);
  assert.match(map, /positive exports on net, negative imports on net/);
  assert.match(map, /Z1 5 MWh demand -1 MWh net position 0\.5 MWh load shed/);
  assert.match(map, /B6 → 2 MWh transfer 100% used/);
});
