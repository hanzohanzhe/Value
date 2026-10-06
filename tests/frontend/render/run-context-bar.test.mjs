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
  assert.match(text, /Stress events ● 48 periods · 571 MWh/);
});

test("doctoral Run withheld under Q14: caution pill and the withheld Callout with Inspect and ledger export", async () => {
  const html = await render({
    methodology: doctoral, energy_balance_status: "reproduction_with_declared_deviations", stress: { stress_periods: 0 },
    result_publication: { status: "withheld", reason_code: "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED" },
  });
  const text = textOf(html);
  assert.match(html, /<span class="value-pill caution" title="Reproduces the thesis behaviour as implemented in VALUE 0\.6\.0-alpha\.2, including declared deviations\. Not an exact reproduction of the 2026-07-18 retained trajectory\.">Doctoral reproduction \(as implemented in VALUE 0\.6\.0-alpha\.2\)<\/span>/);
  assert.match(text, /Energy balance ● Declared deviations/);
  assert.match(text, /Annual results withheld for this reproduction run Doctoral reproduction runs keep the thesis behaviour/);
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
