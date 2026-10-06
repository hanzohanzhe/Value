import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// F-D2 (spec 11.5) rendered offline: the Run page's scope dropdown annotates
// the one-day lesson when the selected Study has extensions.
const WORKSPACE = "app/features/runs/RunWorkspace.tsx";
const pack = { id: "value-101-baseline-v1", allowed_run_modes: ["smoke", "two_year_smoke", "value_101_day", "two_year"], teaching_only: true };
const study = (selected_extensions) => ({
  id: "study-a", name: "Lesson with audit", data_pack_id: pack.id, start_year: 2025, end_year: 2026,
  modules: { psm: "value-bid-at-cost-psm" }, selected_extensions, extensions: { value_101: {} },
});
const noop = async () => {};
const render = (project) => renderTsx(WORKSPACE, "default", {
  workspace: { projects: [project], runs: [], modules: [], runtime: { compatible: true } },
  selectedProjectId: project.id, selectedProject: project, selectedProjectPack: pack, selectedRun: undefined, projectRuns: [],
  preflight: null, effectivePreflightMode: "value_101_day", checkingPreflight: false, teachingProject: true, launching: "",
  selectedRunSourceMutable: false, canRunMode: () => true,
  frozen: { contextKind: "", runId: "", readiness: null, project: null, snapshot: null },
  actions: { onRecoveredStudyCreated: noop, selectRunProject() {}, onSelectRun() {}, onMode() {}, onNavigate() {}, cloneStoragePolicy: noop,
    checkPreflight: noop, startRun: noop, resumeRun: noop, rerunAsCopperplate: noop, lifecycleAction: noop },
});

test("a Study with extensions sees '(extensions do not run)' after the one-day option", async () => {
  const html = await render(study(["value-toy-audit-extension"]));
  assert.match(html, /<option value="value_101_day"[^>]*>One-day market lesson \(extensions do not run\)<\/option>/);
  assert.match(html, /<option value="smoke"[^>]*>Two-period wiring check<\/option>/);
  assert.equal((html.match(/extensions do not run/g) ?? []).length, 1);
});

test("a Study without extensions sees the plain one-day option", async () => {
  const html = await render(study([]));
  assert.match(html, /<option value="value_101_day"[^>]*>One-day market lesson<\/option>/);
  assert.doesNotMatch(html, /extensions do not run/);
});
