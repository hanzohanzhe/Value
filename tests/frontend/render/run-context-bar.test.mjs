import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// X0 S12 + P0-9 S11 (spec 2.1–2.3) rendered offline: the methodology pill, the
// Energy balance and Stress events fields, one prioritised notice and the
// identity rows of the Run context bar, for the three profiles and an older backend.
const BAR = "app/features/workspace/RunContextBar.tsx";
const RESULTS = "app/features/runs/RunResults.tsx";

const run = {
  id: "run-a", project_id: "study-a", project_name: "Release R2 new forecast", mode: "value_101_day", status: "completed",
  execution_status: "passed", contract_validation_status: "passed", scientific_validation_status: "not_evaluated",
  input_snapshot_id: "snapshot-a", diagnostic: { total_periods: 48, years: [2025] },
};
const frozen = {
  runId: "run-a", status: "ready",
  project: { id: "study-a", name: "Release R2 new forecast", data_pack_id: "value-101-baseline-v1", revision_number: 1, revision_sha256: "rev" },
  snapshot: { state: "ready", snapshot_id: "snapshot-a", pack_manifest_sha256: "pack" },
};
const corrected = { status: "recorded", profile_id: "value-corrected", catalogue_sha256: "catalogue-sha" };
const doctoral = { status: "recorded", profile_id: "doctoral-lineage-0.6.0a2", catalogue_sha256: "catalogue-sha" };
const render = (overrides, actions = { onOpenInspect: () => {}, onShowStressEvents: () => {} }) =>
  renderTsx(BAR, "default", { run: { ...run, ...overrides }, frozen, actions });

test("corrected Run: info pill, passed balance in teal, no stress, no notice, identity rows", async () => {
  const html = await render({ methodology: corrected, energy_balance_status: "passed", stress: { stress_periods: 0, shortfall_mwh: 0 } });
  const text = textOf(html);
  assert.match(html, /<span class="value-pill info" title="Current default methodology with review fixes of 2026-10\. Profile value-corrected\.">Corrected methodology \(default\)<\/span>/);
  assert.match(html, /class="run-context-check ok"[^>]*><i aria-hidden="true">● <\/i>Passed<\/b>/);
  assert.match(text, /Stress events None/);
  assert.doesNotMatch(html, /run-context-check ok[^>]*>None/, "None is never green");
  assert.doesNotMatch(html, /value-callout/);
  assert.match(text, /Methodology profile id value-corrected/);
  assert.match(text, /Profile catalogue SHA-256 catalogue-sha/);
  assert.match(text, /Scientific validation not evaluated/, "the existing field is kept");
});

test("corrected Run with a failed balance: one danger Callout with the residual action, others behind +N more", async () => {
  const html = await render({
    methodology: corrected, energy_balance_status: "failed",
    energy_balance: { envelope_lower_violations: 3, envelope_upper_violations: 1, maximum_envelope_violation_mwh: 12.5 },
    stress: { stress_periods: 48, shortfall_mwh: 570.546171074, shortfall_basis: "lower_bound" },
  });
  const text = textOf(html);
  assert.equal((html.match(/class="value-callout /g) ?? []).length, 1);
  assert.match(html, /class="value-callout danger" role="alert"/);
  assert.match(text, /Energy balance check failed The independent ledger check found 4 periods where supply and use do not reconcile \(largest residual 12\.5 MWh\)\. Treat results from this Run as unverified\./);
  assert.match(text, /Open residuals in Inspect/);
  assert.match(text, /\+1 more notice/);
  assert.match(html, /class="run-context-check danger"[^>]*><i aria-hidden="true">● <\/i>Failed/);
  // F-P04-1: a lower-bound shortfall carries "≥".
  assert.match(text, /Stress events ● 48 periods · ≥ 571 MWh/);
});

test("doctoral Run withheld under Q14: caution pill and the withheld Callout with Inspect and ledger export", async () => {
  const html = await render({
    methodology: doctoral, energy_balance_status: "reproduction_with_declared_deviations", stress: { stress_periods: 0 },
    result_publication: { status: "withheld", reason_code: "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED" },
  });
  const text = textOf(html);
  assert.match(html, /<span class="value-pill caution" title="Reproduces the thesis behaviour as implemented in VALUE 0\.6\.0-alpha\.2, including declared deviations\. Not an exact reproduction of the 2026-07-18 retained trajectory\.">Doctoral reproduction \(as implemented in VALUE 0\.6\.0-alpha\.2\)<\/span>/);
  assert.match(text, /Energy balance ● Declared deviations/);
  // Spec 11.3 (R-D1): without recorded failures the notice says what is known, never a generic energy-balance claim.
  assert.match(text, /Annual results withheld for this reproduction run Annual results withheld: a raw invariant failed\. No declared deviation explains it\. The full ledger remains available\./);
  assert.match(text, /Raw invariants ● Failed/);
  assert.match(text, /Open in Inspect Export ledger/);
  assert.match(html, /class="value-callout caution" role="alert"/);
});

test("pre-fix Run: not-recorded pill, superseded (amber) instead of a green passed, advisories action with count", async () => {
  const html = await render({
    methodology: { status: "not_recorded", profile_id: null },
    contract_validation_status: "superseded_pre_fix", scientific_validation_status: "superseded_pre_fix",
    recorded_scientific_validation_status: "passed", energy_balance_status: "not_evaluated",
    advisories: [{ id: "VALUE-ADV-2026-10-04-REVIEW", severity: "high", title: "Produced before the review", summary: "Read the review.", affected_metrics: ["total_system_cost_gbp"] }],
  });
  const text = textOf(html);
  assert.match(html, /<span class="value-pill muted" title="This Run was produced before methodology profiles existed\. See advisories\.">Methodology not recorded \(pre-2026-10 run\)<\/span>/);
  assert.match(text, /Contract check ● Superseded Scientific validation ● Superseded/);
  assert.doesNotMatch(html, /run-context-check ok/);
  assert.match(text, /Produced before the 2026-10 review fixes This Run's original validation status was "passed"\./);
  assert.match(html, /aria-expanded="false"[^>]*>View advisories \(1\)<\/button>/);
  assert.match(text, /Energy balance Not evaluated/);
});

test("older backend: no methodology or validation fields degrade to not-recorded words and no notice", async () => {
  const html = await renderTsx(BAR, "default", { run, frozen });
  const text = textOf(html);
  assert.match(text, /Methodology not recorded Execution/);
  assert.match(text, /Energy balance Not recorded Stress events Not recorded/);
  assert.doesNotMatch(html, /value-callout/);
  assert.match(text, /Methodology profile id Not recorded/);
});

test("without action handlers the notice still states the problem but offers no dead button", async () => {
  const html = await renderTsx(BAR, "default", { run: { ...run, methodology: corrected, stress: { stress_periods: 2, shortfall_mwh: 1.5 } }, frozen });
  assert.match(textOf(html), /Supply fell short of demand in 2 periods Total shortfall 1\.5 MWh\./);
  assert.doesNotMatch(html, /Show stress events/);
});

test("annual results of a withheld reproduction Run show the Withheld pill, never totals or 'No annual results yet'", async () => {
  const html = await renderTsx(RESULTS, "AnnualResults", {
    runId: "r", results: [], coverage: null, onOpenInspect: () => {}, onExportLedger: () => {},
    publication: { status: "withheld", reason_code: "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED", message: "Doctoral reproduction runs publish annual results only when every raw invariant passes." },
    withheldYearCount: 2,
  });
  const text = textOf(html);
  assert.match(html, /class="value-pill caution"[^>]*>Withheld<\/span>/);
  assert.match(text, /Annual results are not published on result pages for this reproduction run \(2 computed years\)\. The full ledger remains available\./);
  assert.match(text, /Open in Inspect Export ledger/);
  assert.doesNotMatch(text, /No annual results yet|£/);
});

// Designer rulings F-P04-1..5 (2026-10-06).
test("F-P04-1: a lower-bound shortfall reads '≥ x' with the upper bound on hover; exact has no qualifier", async () => {
  const lower = await render({ methodology: corrected, energy_balance_status: "passed", stress: { stress_periods: 48, shortfall_mwh: 570.5, shortfall_basis: "lower_bound", shortfall_upper_mwh: 1015.5 } });
  assert.match(textOf(lower), /Stress events ● 48 periods · ≥ 571 MWh/);
  assert.match(lower, /title="Lower bound: this Run predates exact stress accounting \(upper bound 1,015\.5 MWh\)"/);
  assert.match(textOf(lower), /Total shortfall ≥ 571 MWh/);
  const exact = await render({ methodology: corrected, energy_balance_status: "passed", stress: { stress_periods: 48, shortfall_mwh: 570.5, shortfall_basis: "exact" } });
  assert.doesNotMatch(textOf(exact), /≥/);
});

test("F-P04-2: reproduction_conformant is a teal ● Conformant with the ledger-closes tooltip", async () => {
  const html = await render({ methodology: doctoral, energy_balance_status: "reproduction_conformant", result_publication: { status: "published" } });
  assert.match(html, /class="run-context-check ok" title="The doctoral reproduction ledger closes\. This does not certify the method as physically validated\."><i aria-hidden="true">● <\/i>Conformant<\/b>/);
});

test("F-P04-3: any failed gate raises the danger Callout naming the gates; energy balance alone keeps its wording", async () => {
  const storage = await render({ methodology: corrected, energy_balance_status: "passed", storage_invariant_status: "failed",
    validation_gate: { policy: "production", status: "failed", gates: { run_invariants: "passed", energy_balance: "passed", storage_invariants: "failed" } } });
  const text = textOf(storage);
  assert.match(storage, /value-callout danger/);
  assert.match(text, /Validation gate failed: Storage limits/);
  assert.match(text, /Storage limits Storage exceeded its rated power/);
  assert.match(text, /Open residuals in Inspect/);
  const two = textOf(await render({ methodology: corrected, validation_gate: { policy: "production", status: "failed", gates: { run_invariants: "failed", energy_balance: "passed", storage_invariants: "failed" } } }));
  assert.match(two, /Validation gate failed: Run invariants, Storage limits/);
  const balance = textOf(await render({ methodology: corrected, energy_balance_status: "failed",
    energy_balance: { balance_account: { open_periods: 3, unexplained_open_periods: 3, max_abs_closing_residual_mwh: 2.5 } },
    validation_gate: { policy: "production", status: "failed", gates: { run_invariants: "passed", energy_balance: "failed", storage_invariants: "passed" } } }));
  assert.match(balance, /Energy balance check failed/);
  assert.match(balance, /found 3 periods where supply and use do not reconcile \(largest residual 2\.5 MWh\)/);
  assert.doesNotMatch(balance, /Validation gate failed/);
});

test("F-P04-4: a gate-blocked corrected Run shows 'Annual results not published' and no totals", async () => {
  const validation = { methodology: corrected, publication_blocked: { reason_code: "GF_VALIDATION_GATE_FAILED" },
    validation_gate: { policy: "production", status: "failed", gates: { run_invariants: "passed", energy_balance: "passed", storage_invariants: "failed" } } };
  const html = await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: [], validation, onOpenInspect: () => {}, onExportLedger: () => {} });
  const text = textOf(html);
  assert.match(html, /value-callout danger/);
  assert.match(text, /Annual results not published/);
  assert.match(text, /This Run failed 1 validation gate: Storage limits\. Results are withheld until the cause is fixed\. The full ledger remains available\./);
  assert.match(text, /Open in Inspect/);
  assert.match(text, /Export ledger/);
  assert.doesNotMatch(text, /No annual results yet/);
});

test("F-P04-5: Inspect's residual panel lists boundary, raw status, max residual and periods", async () => {
  const html = await renderTsx("app/features/evidence/ResidualPanel.tsx", "default", { balance: { boundary_id: "native_corrected_full_node_v1", raw_boundary_status: "failed", maximum_absolute_boundary_residual_mwh: 23.25, periods: 48 } });
  const text = textOf(html);
  assert.match(text, /Boundary Raw status Max residual Periods/);
  assert.match(text, /native_corrected_full_node_v1 failed 23\.25 MWh 48/);
  assert.match(textOf(await renderTsx("app/features/evidence/ResidualPanel.tsx", "default", { balance: null })), /did not record an energy-balance report/);
});

// Spec 11.3 (R-D1): the four-role report's doctoral day. The energy balance is
// conformant; storage single direction failed in 10 rows (DEV-STO-01).
const storageFailure = {
  gate: "storage_invariants", check: "storage.single_direction", name: "Storage single direction", count: 10, unit: "rows",
  deviation_ids: ["DEV-STO-01"],
  deviations: [{ id: "DEV-STO-01", summary: "The doctoral default PSM resets a store's power limit in every clearing stage and can discharge and charge the same store in one period." }],
};

test("doctoral withheld Run names the failed raw invariant and its declared deviation", async () => {
  const html = await render({
    methodology: doctoral, energy_balance_status: "reproduction_conformant", stress: { stress_periods: 0 },
    raw_invariants: { status: "failed" }, raw_invariant_failures: [storageFailure],
    result_publication: { status: "withheld", reason_code: "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED", raw_invariants_status: "failed" },
  });
  const text = textOf(html);
  assert.match(text, /Annual results withheld: raw invariant "Storage single direction" failed \(10 rows\)\. Matches declared deviation DEV-STO-01: The doctoral default PSM resets a store's power limit in every clearing stage and can discharge and charge the same store in one period\. The full ledger remains available\./);
  assert.doesNotMatch(text, /physical energy-balance check/);
  // Energy balance stays as it was; the new field sits beside it, amber with the names on hover.
  assert.match(text, /Energy balance ● Conformant Raw invariants ● 1 failed/);
  assert.match(html, /class="run-context-check caution" title="Storage single direction"><i aria-hidden="true">● <\/i>1 failed<\/b>/);
  assert.match(html, /class="run-context-check ok" title="The doctoral reproduction ledger closes\. This does not certify the method as physically validated\."><i aria-hidden="true">● <\/i>Conformant/);
});

test("an unexplained raw-invariant failure says no declared deviation explains it", async () => {
  const html = await render({
    methodology: doctoral, energy_balance_status: "reproduction_conformant", stress: { stress_periods: 0 },
    raw_invariant_failures: [{ name: "Storage state-of-charge bounds", count: 3, unit: "rows", deviation_ids: [], deviations: [] }],
    result_publication: { status: "withheld", raw_invariants_status: "failed" },
  });
  assert.match(textOf(html), /raw invariant "Storage state-of-charge bounds" failed \(3 rows\)\. No declared deviation explains it\./);
});

test("Raw invariants appears only for the doctoral profile; passed is teal", async () => {
  const passed = await render({ methodology: doctoral, energy_balance_status: "reproduction_conformant", stress: { stress_periods: 0 }, raw_invariants: { status: "passed" }, raw_invariant_failures: [], result_publication: { status: "published", raw_invariants_status: "passed" } });
  assert.match(passed, /<small>Raw invariants<\/small><b class="run-context-check ok"[^>]*><i aria-hidden="true">● <\/i>Passed/);
  const correctedHtml = await render({ methodology: corrected, energy_balance_status: "passed", stress: { stress_periods: 0 }, raw_invariant_failures: [storageFailure] });
  assert.doesNotMatch(correctedHtml, /Raw invariants/);
});
