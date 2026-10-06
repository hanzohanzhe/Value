import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// Four-role report R-D2 / S-D12 (round R1-5), rendered offline: the Run history
// selector tells two Runs of one Study apart, keeps "No runs yet" only for a
// Study without Runs, and the empty panel does not claim there are none.
const pack = { id: "value-101-baseline-v1", allowed_run_modes: ["smoke", "value_101_day"], teaching_only: true };
const study = { id: "value-101-baseline", name: "VALUE 101 baseline", data_pack_id: pack.id, revision_sha256: "a".repeat(64), start_year: 2025, end_year: 2026, modules: { psm: "value-bid-at-cost-psm" }, selected_extensions: [], extensions: { value_101: {} } };
const run = (id, created) => ({ id, project_id: study.id, project_name: study.name, mode: "value_101_day", status: "completed", created_at: created, current_stage: "Completed", completed_years: 1, total_years: 1, updated_at: created, results: [], modules: { psm: "value-bid-at-cost-psm", investment: "agent-investment" }, module_evidence: { "value-bid-at-cost-psm": { version: "6.4.0", actions: 48, years: [2025] } } });
const runs = [run("value-101-basel-20261006-231703-fc41b4c7", "2026-10-06T23:17:04+01:00"), run("value-101-basel-20261006-231240-c11e26f1", "2026-10-06T23:12:41+01:00")];
const noop = async () => {};
const render = (props) => renderTsx("app/features/runs/RunWorkspace.tsx", "default", {
  workspace: { projects: [study], runs: props.projectRuns, modules: [], runtime: { compatible: true } },
  selectedProjectId: study.id, selectedProject: study, selectedProjectPack: pack,
  preflight: null, effectivePreflightMode: "value_101_day", checkingPreflight: false, teachingProject: true, launching: "",
  selectedRunSourceMutable: true, canRunMode: () => true,
  frozen: { contextKind: "", runId: "", readiness: null, project: null, snapshot: null },
  actions: { onRecoveredStudyCreated: noop, selectRunProject() {}, onSelectRun() {}, onMode() {}, onNavigate() {}, cloneStoragePolicy: noop,
    checkPreflight: noop, startRun: noop, resumeRun: noop, rerunAsCopperplate: noop, lifecycleAction: noop },
  ...props,
});

test("two Runs of one Study have distinct labels and the placeholder is not 'No runs yet'", async () => {
  const html = await render({ projectRuns: runs, selectedRun: undefined });
  assert.match(html, /One-day market lesson · completed · 2026-10-06 23:17 · fc41b4c7/);
  assert.match(html, /One-day market lesson · completed · 2026-10-06 23:12 · c11e26f1/);
  assert.doesNotMatch(html, /No runs yet/);
  assert.match(html, /<option value="" disabled=""[^>]*>Choose a Run \(2\)<\/option>/);
  assert.match(html, /<b>2 Runs for this Study<\/b>/);
});

test("with a Run selected there is no placeholder option; uncalled slots of the lesson are named", async () => {
  const html = await render({ projectRuns: runs, selectedRun: runs[0] });
  assert.doesNotMatch(html, /Choose a Run|No runs yet/);
  assert.match(html, /48 recorded calls/);
  assert.match(html, /Not called in this scope/);
  assert.doesNotMatch(html, /Evidence pending/);
});

test("a Study without Runs keeps 'No runs yet'; a launch in progress says the Run is starting", async () => {
  assert.match(await render({ projectRuns: [], selectedRun: undefined }), /No runs yet for this Study[\s\S]*<b>No runs yet<\/b>/);
  const starting = await render({ projectRuns: [], selectedRun: undefined, launching: "value_101_day" });
  assert.match(starting, /<b>Starting the Run…<\/b>/);
});
