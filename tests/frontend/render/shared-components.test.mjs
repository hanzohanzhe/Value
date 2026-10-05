import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// Spec 1.3: Callout and StatusPill; spec 1.1: state words instead of numbers.
const CALLOUT = "app/features/shared/Callout.tsx";

test("a danger or caution Callout is an alert with title, body and actions", async () => {
  const html = await renderTsx(CALLOUT, "Callout", { tone: "danger", title: "Energy balance check failed", children: "Treat results as unverified.", actions: "Open residuals in Inspect" });
  assert.match(html, /class="value-callout danger"/);
  assert.match(html, /role="alert"/);
  assert.match(html, /<h4 class="value-callout-title">Energy balance check failed<\/h4>/);
  assert.equal(textOf(html), "! Energy balance check failed Treat results as unverified. Open residuals in Inspect");
  assert.match(await renderTsx(CALLOUT, "Callout", { tone: "caution", title: "t" }), /role="alert"/);
});

test("ok and info Callouts are polite status regions", async () => {
  assert.match(await renderTsx(CALLOUT, "Callout", { tone: "ok", title: "Passed" }), /role="status"/);
  assert.match(await renderTsx(CALLOUT, "Callout", { tone: "info", title: "Note" }), /role="status"/);
});

test("StatusPill and ValueState render the tone class and the state text", async () => {
  assert.equal(await renderTsx(CALLOUT, "StatusPill", { tone: "caution", children: "Partial year · 16.6%" }), '<span class="value-pill caution">Partial year · 16.6%</span>');
  assert.equal(await renderTsx(CALLOUT, "ValueState", { state: "not_modelled", title: "native path" }), '<span class="value-state" title="native path">Not modelled</span>');
  assert.equal(textOf(await renderTsx(CALLOUT, "ValueState", { state: "partial_year", coveragePercent: 16.6 })), "Partial year · 16.6%");
  assert.match(await renderTsx(CALLOUT, "ValueState", { state: "invalid" }), /value-state red/);
  assert.equal(textOf(await renderTsx(CALLOUT, "ValueOr", { value: null, state: "not_recorded" })), "Not recorded");
  assert.equal(textOf(await renderTsx(CALLOUT, "ValueOr", { value: "£55/MWh" })), "£55/MWh");
});
