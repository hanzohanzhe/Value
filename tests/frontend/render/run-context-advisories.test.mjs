import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// R-D11 (four-role report, round R1-5): a doctoral Run's advisories (6 high in
// the tests) were visible only on the Compare page. The Run context bar now
// lists them in a disclosure whenever the pre-fix notice does not.
const BAR = "app/features/workspace/RunContextBar.tsx";
const advisories = [
  { id: "ADV-A", severity: "high", title: "Storage dispatch differs from the thesis", summary: "Declared deviation DEV-STO-01." },
  { id: "ADV-B", severity: "medium", title: "Legacy storage tariff", summary: "Thesis-era tariff." },
  { id: "ADV-C", severity: "high", title: "Nuclear started the year off", summary: "Start-up cost paid to enter." },
];
const run = { id: "run-d", project_id: "study-d", project_name: "Doctoral", mode: "value_101_day", status: "completed", execution_status: "passed", methodology: { status: "recorded", profile_id: "doctoral-lineage-0.6.0a2", catalogue_sha256: "c" } };
const render = (overrides) => renderTsx(BAR, "default", { run: { ...run, ...overrides }, frozen: null, actions: {} });

test("a doctoral Run lists its advisories with a severity summary", async () => {
  const html = await render({ advisories });
  const text = textOf(html);
  assert.match(html, /<details class="run-context-advisory-details value-new-control"><summary>3 advisories apply to this Run · 2 high, 1 medium<\/summary>/);
  assert.match(text, /Storage dispatch differs from the thesis · high/);
  assert.match(text, /Nuclear started the year off · high Start-up cost paid to enter\./);
});

test("the listing count shows while the Run detail loads; no advisory, no disclosure", async () => {
  assert.match(await render({ advisory_summary: { count: 11, max_severity: "high" } }), /<summary>11 advisories apply to this Run<\/summary>[\s\S]*The advisory details are loading/);
  assert.doesNotMatch(await render({}), /run-context-advisory-details/);
  assert.match(await render({ advisories: [advisories[1]] }), /<summary>1 advisory applies to this Run · 1 medium<\/summary>/);
});

test("a pre-fix Run keeps its own 'View advisories' notice and gets no second list", async () => {
  const html = await render({ methodology: null, scientific_validation_status: "superseded_pre_fix", advisories });
  assert.match(html, /View advisories \(3\)/);
  assert.doesNotMatch(html, /run-context-advisory-details/);
});
