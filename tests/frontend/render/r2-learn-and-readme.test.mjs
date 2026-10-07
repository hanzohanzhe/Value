import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";
import { VALUE_101_FALLBACK } from "../../../app/features/learn/value101.ts";

// Round R2 (four-role report 10.7): L-4 and R3M-7 rendered offline.
const learnProps = (extra = {}) => ({
  descriptor: VALUE_101_FALLBACK, modules: [], loading: false, error: "", onRetry() {}, onOpenView() {},
  baselineSaved: true, baselineInTrash: false, launching: false,
  onCreateBaselineStudy() {}, onRestoreBaselineStudy() {}, onRunOneDay() {}, onRunFullTwoYear() {}, onOpenDayRun() {}, onOpenAnnualRun() {},
  networkStudies: [], networkRuns: [], onNetworkStudiesCreated() {}, onRunNetworkStudy() {}, onOpenNetworkRun() {}, ...extra,
});

test("while a Run starts from Learn, the page says why its buttons are disabled (L-4)", async () => {
  const idle = await renderTsx("app/features/learn/Value101Learn.tsx", "default", learnProps());
  assert.doesNotMatch(textOf(idle), /Starting the Run|Preparing ·/);
  const html = await renderTsx("app/features/learn/Value101Learn.tsx", "default", learnProps({ launching: true }));
  assert.match(html, /<p class="run-launch-note value-new-control" role="status">Starting the Run: VALUE checks the Study&#x27;s readiness and lists the Run, then freezes its inputs in the background\./);
  assert.match(html, /<button class="secondary" disabled="">Run one market day<\/button>/);
});

test("Learn shows the stage and elapsed time of a lesson Run being prepared (A24-5, L-4)", async () => {
  const html = await renderTsx("app/features/learn/Value101Learn.tsx", "default", learnProps({
    preparations: [{ id: "r1", label: "One-day Run", text: "Preparing · step 1 of 4: Recording and archiving the execution environment · 2 min 10 s elapsed" }],
  }));
  assert.match(html, /<div class="learn-run-preparation" role="status"><p class="run-preparation-progress value-new-control">One-day Run: Preparing · step 1 of 4: Recording and archiving the execution environment · 2 min 10 s elapsed<\/p>/);
  assert.match(html, /archives the Python runtime once \(about 3 minutes\)/);
});

test("the closed Read me has no standing status line (R3M-7)", async () => {
  const html = await renderTsx("app/features/workspace/ReadMePanel.tsx", "ReadMePanel", { open: false, onClose() {} });
  assert.doesNotMatch(html, /role="status"/);
  assert.doesNotMatch(html, /正在读取使用说明/);
});
