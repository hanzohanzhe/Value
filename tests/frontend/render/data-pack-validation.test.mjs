import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// Spec 11.2 (S-D2) rendered offline.
const PANEL = "app/features/data/DataPackValidationPanel.tsx";
const report = {
  valid: true, errors: [], warnings: [],
  layers: { chronology: { findings: [{ code: "GF_DATA_TIMESTAMPS", role: "demand.real", message: "real.csv:time 2 gap(s)" }] }, plausibility: { findings: [] } },
  profile_eligibility: { "value-corrected": { eligible: true, blocking_codes: [], warning_codes: ["GF_DATA_TIMESTAMPS"] }, "doctoral-lineage-0.6.0a2": { eligible: false, blocking_codes: ["GF_DATA_TIMESTAMPS"] } },
};

test("the two rows show each layer and each profile; details stay folded", async () => {
  const html = await renderTsx(PANEL, "default", { packId: "my-pack", report });
  const text = textOf(html);
  assert.match(text, /Validation Structural ● Passed Chronology ● Failed Plausibility ● Passed/);
  assert.match(text, /Methodology use Corrected ● Eligible Doctoral reproduction ● Not eligible — blocked by GF_DATA_TIMESTAMPS/);
  assert.match(html, /<span class="value-pill danger" title="1 finding; blocks Doctoral reproduction">/);
  assert.match(html, /aria-expanded="false"[^>]*>Show details ▾</);
  assert.doesNotMatch(html, /2 gap\(s\)/);
});

test("without any validation the panel says Not evaluated in muted grey", async () => {
  const html = await renderTsx(PANEL, "default", { packId: "empty", report: null, cached: { status: "not_evaluated" }, loading: true });
  assert.equal((html.match(/value-pill muted">Not evaluated</g) ?? []).length, 5);
  assert.match(html, /Validating the pack…/);
  assert.doesNotMatch(html, /Show details/);
});
