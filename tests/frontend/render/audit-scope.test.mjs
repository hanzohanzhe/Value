import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// R-D6 (four-role report, round R1-5): the one-day lesson has no planning
// ledger, so Inspect opens on Market and the Planning tab explains instead of
// requesting planning/projects and planning/events (which answer 404).
const AUDIT = "app/features/evidence/AuditView.tsx";
const run = (mode) => ({ id: "run-a", project_id: "study-a", project_name: "Study A", mode, status: "completed", current_stage: "Completed", completed_years: 1, total_years: 1, updated_at: "", results: [] });

test("a one-day lesson Run opens Inspect on the Market tab", async () => {
  const html = await renderTsx(AUDIT, "default", { run: run("value_101_day"), onCreateFullReplayRevision() {} });
  assert.match(html, /<button role="tab" aria-selected="true" class="active">market<\/button>/);
  assert.match(html, /<button role="tab" aria-selected="false" class="">planning<\/button>/);
});

test("its Planning tab says there is no planning record in this scope", async () => {
  const html = await renderTsx(AUDIT, "default", { run: run("value_101_day"), onCreateFullReplayRevision() {}, initialTab: { tab: "planning", nonce: 1 } });
  assert.match(html, /No planning record in this scope/);
  assert.doesNotMatch(html, /durable project records/);
});

test("annual scopes keep Planning as the first tab", async () => {
  const html = await renderTsx(AUDIT, "default", { run: run("two_year"), onCreateFullReplayRevision() {} });
  assert.match(html, /<button role="tab" aria-selected="true" class="active">planning<\/button>/);
  assert.match(html, /durable project records/);
});
