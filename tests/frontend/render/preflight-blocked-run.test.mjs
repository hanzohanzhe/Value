import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// Spec 11.4 (M-D3) rendered offline: a preflight that names a quarantined
// module is shown with its errors, and the Run button is disabled with a reason.
const pack = { id: "value-101-baseline-v1", allowed_run_modes: ["smoke", "value_101_day"], teaching_only: true };
const study = { id: "study-q", name: "Quarantined module study", data_pack_id: pack.id, revision_sha256: "a".repeat(64), start_year: 2025, end_year: 2026, modules: { psm: "my-broken-psm" }, selected_extensions: [] };
const noop = async () => {};
const render = (preflight) => renderTsx("app/features/runs/RunWorkspace.tsx", "default", {
  workspace: { projects: [study], runs: [], modules: [], runtime: { compatible: true } },
  selectedProjectId: study.id, selectedProject: study, selectedProjectPack: pack, selectedRun: undefined, projectRuns: [],
  preflight, effectivePreflightMode: "smoke", checkingPreflight: false, teachingProject: true, launching: "",
  selectedRunSourceMutable: false, canRunMode: () => true,
  frozen: { contextKind: "", runId: "", readiness: null, project: null, snapshot: null },
  actions: { onRecoveredStudyCreated: noop, selectRunProject() {}, onSelectRun() {}, onMode() {}, onNavigate() {}, cloneStoragePolicy: noop,
    checkPreflight: noop, startRun: noop, resumeRun: noop, rerunAsCopperplate: noop, lifecycleAction: noop },
});
const quarantined = { code: "GF_PREFLIGHT_MODULE_QUARANTINED", severity: "error", scope: "modules", message: "The Study selects quarantined local code: module my-broken-psm (GF_MODULE_IMPORT_FAILED)", corrective_action: "Open Modules: disable or repair the quarantined entry, then select a working module." };

test("a blocked preflight without a revision shows its errors and disables the Run", async () => {
  const html = await render({ project_id: study.id, project_revision_sha256: null, data_pack_id: pack.id, mode: "smoke", accepted: false, errors: [quarantined], warnings: [], estimates: { periods: 2 } });
  assert.match(html, /Needs attention/);
  assert.match(html, /The Study selects quarantined local code: module my-broken-psm/);
  assert.match(html, /Open Modules: disable or repair the quarantined entry/);
  assert.match(html, /<button type="button" class="primary full" disabled=""[^>]*aria-describedby="run-blocked-reason"/);
  assert.match(html, /id="run-blocked-reason"[^>]*>Readiness found 1 error\. Fix it, then check readiness again\.</);
});

test("an accepted preflight leaves the Run button enabled", async () => {
  const html = await render({ project_id: study.id, project_revision_sha256: study.revision_sha256, data_pack_id: pack.id, mode: "smoke", accepted: true, errors: [], warnings: [], estimates: { periods: 2 } });
  assert.doesNotMatch(html, /run-blocked-reason/);
  assert.match(html, /<button type="button" class="primary full">Run selected scope/);
});
