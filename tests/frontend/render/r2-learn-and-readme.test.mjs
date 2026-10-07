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
  assert.doesNotMatch(textOf(idle), /freezing the Study's inputs/);
  const html = await renderTsx("app/features/learn/Value101Learn.tsx", "default", learnProps({ launching: true }));
  assert.match(html, /<p class="run-launch-note value-new-control" role="status">Starting the Run: VALUE is freezing the Study&#x27;s inputs/);
  assert.match(html, /<button class="secondary" disabled="">Run one market day<\/button>/);
});

test("the closed Read me has no standing status line (R3M-7)", async () => {
  const html = await renderTsx("app/features/workspace/ReadMePanel.tsx", "ReadMePanel", { open: false, onClose() {} });
  assert.doesNotMatch(html, /role="status"/);
  assert.doesNotMatch(html, /正在读取使用说明/);
});
