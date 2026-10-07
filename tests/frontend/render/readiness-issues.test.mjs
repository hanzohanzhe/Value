import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// Spec 11.1 (S-D1) rendered offline: with 14 issues the last one (a
// plausibility finding) is visible, and folded groups say how many they hold.
const issue = (code, severity, scope, message, extra = {}) => ({ code, severity, scope, message, corrective_action: "Review it.", ...extra });
const warnings = [
  issue("GF_PREFLIGHT_UNSAVED_REVISION", "warning", "project", "This legacy project has no saved immutable revision identity."),
  ...Array.from({ length: 10 }, (_, index) => issue("GF_PREFLIGHT_DATA_WARNING", "warning", "data", `market.role${index}.price: unit is not declared; canonical role expects GBP/MWh`)),
  issue("GF_PREFLIGHT_DATA_WARNING", "warning", "data", "demand.real: Legacy demand label MWh/period is interpreted as raw MW."),
  issue("GF_DATA_PLAUSIBILITY_PRICE", "warning", "data", "market.france.price: france price range [82, 6087] outside [-500, 5000] GBP/MWh", { layer: "plausibility" }),
  issue("GF_DATA_PLAUSIBILITY_FLOW", "warning", "data", "market.france.profile: france |flow| 500 MW exceeds 58.62 MW", { layer: "plausibility" }),
];

test("the last of 14 issues is visible and every group has a header", async () => {
  const html = await renderTsx("app/features/runs/ReadinessIssues.tsx", "default", { errors: [], warnings });
  assert.equal(warnings.length, 14);
  assert.match(html, /france \|flow\| 500 MW exceeds 58\.62 MW/);
  assert.match(html, /france price range \[82, 6087\]/);
  assert.match(html, /Data plausibility · 2/);
  assert.match(html, /Adapter: unit not declared · 10/);
  assert.match(html, /Other data warnings · 1/);
  assert.match(html, /Environment and setup · 1/);
  assert.match(html, />Show 10</);
  assert.match(html, />Show 1</);
  // Folded groups do not render their rows; the plausibility group is open.
  assert.doesNotMatch(html, /unit is not declared/);
  assert.match(html, /aria-expanded="true"[^>]*>Hide</);
});

test("errors are listed open without a toggle, in red", async () => {
  const html = await renderTsx("app/features/runs/ReadinessIssues.tsx", "default", {
    errors: [issue("GF_PREFLIGHT_MODULE_QUARANTINED", "error", "modules", "The Study selects quarantined local code: module demo (GF_MODULE_IMPORT_FAILED)")],
    warnings: [issue("GF_PREFLIGHT_DATA_WARNING", "warning", "data", "demand.real: unit is not declared; canonical role expects MW"), issue("GF_PREFLIGHT_DATA_WARNING", "warning", "data", "demand.forecast: unit is not declared; canonical role expects MW")],
  });
  assert.match(html, /value-pill danger">Errors · 1</);
  assert.match(html, /The Study selects quarantined local code/);
  assert.equal((html.match(/readiness-toggle/g) ?? []).length, 1);
  assert.match(html, /Adapter: unit not declared · 2/);
});

test("no issues renders nothing", async () => {
  const html = await renderTsx("app/features/runs/ReadinessIssues.tsx", "default", { errors: [], warnings: [] });
  assert.equal(html, "");
});

test("an in-place module source edit is an amber notice above the groups (spec 11.7)", async () => {
  const message = "Module my-storage-cost source changed since install (bdfb9ab4… → 836d9086…). Results will record the new source hash.";
  const html = await renderTsx("app/features/runs/ReadinessIssues.tsx", "default", {
    errors: [], warnings: [issue("GF_PREFLIGHT_MODULE_SOURCE_CHANGED", "warning", "modules", message)],
  });
  assert.match(html, /value-callout caution readiness-source-changed" role="alert"/);
  assert.match(html, /Module source changed since install/);
  assert.ok(html.includes(message));
  // R3M-5 (round R2): shown once, in the notice; it is not counted again in a group.
  assert.doesNotMatch(html, /Environment and setup/);
  assert.equal(html.split(message).length - 1, 1);
});

test("a source-change notice leaves the other warnings in their groups (R3M-5)", async () => {
  const message = "Module my-storage-cost source changed since install (bdfb9ab4… → 836d9086…). It is quarantined, so no Run can start; once it is repaired, results record the new source hash.";
  const html = await renderTsx("app/features/runs/ReadinessIssues.tsx", "default", {
    errors: [issue("GF_PREFLIGHT_MODULE_QUARANTINED", "error", "modules", "Module my-storage-cost is quarantined.")],
    warnings: [issue("GF_PREFLIGHT_MODULE_SOURCE_CHANGED", "warning", "modules", message), issue("GF_PREFLIGHT_SOLVER_NOTE", "warning", "runtime", "Solver note.")],
  });
  assert.match(html, /Module source changed since install/);
  assert.match(html, /Errors · 1/);
  assert.match(html, /Environment and setup · 1/);
  assert.equal(html.split(message).length - 1, 1);
});
