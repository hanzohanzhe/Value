import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// Four-role report M2-N3 and S-D13 (round R1-5), rendered offline.
const readiness = {
  schema_version: "value.domain-readiness/v1", status: "ready", ready: true, preview_periods: 48, requested_periods: 48, bounded: false,
  sections: { electricity: { status: "ready", claim: "Demand and supply inputs present", metrics: {} } }, issues: [],
};

test("M2-N3: ready physical inputs read 'Run blocked' while the readiness check has errors", async () => {
  const blocked = await renderTsx("app/features/runs/DomainReadinessPanel.tsx", "default", { readiness, onNavigate() {}, runBlocked: true });
  assert.match(blocked, /<span class="domain-readiness-blocked" title="The physical inputs are ready, but the readiness check above found errors; the Run cannot start until they are fixed\."><span class="badge warn">inputs ready · Run blocked<\/span><\/span>/);
  assert.doesNotMatch(blocked, /badge good">ready</);
  const accepted = await renderTsx("app/features/runs/DomainReadinessPanel.tsx", "default", { readiness, onNavigate() {} });
  assert.match(accepted, /<span class="badge good">ready<\/span>/);
  const notReady = await renderTsx("app/features/runs/DomainReadinessPanel.tsx", "default", { readiness: { ...readiness, ready: false, status: "blocked" }, onNavigate() {}, runBlocked: true });
  assert.match(notReady, /<span class="badge warn">blocked<\/span>/);
});

test("S-D13: the Run's manifest SHA-256 is labelled as the frozen manifest and its difference explained", async () => {
  const html = await renderTsx("app/features/workspace/RunContextBar.tsx", "default", {
    run: { id: "run-a", project_id: "study-a", project_name: "Study A", mode: "value_101_day", status: "completed", input_snapshot_id: "snapshot-a" },
    frozen: { runId: "run-a", status: "ready", project: { id: "study-a", name: "Study A", data_pack_id: "pack-a", revision_number: 1, revision_sha256: "rev" }, snapshot: { state: "ready", snapshot_id: "snapshot-a", pack_manifest_sha256: "frozen-sha" } },
  });
  const text = textOf(html);
  assert.match(text, /Frozen data pack manifest SHA-256 frozen-sha/);
  assert.doesNotMatch(text, /(^|[^n] )Data pack manifest SHA-256/);
  assert.match(text, /differs from the source manifest SHA-256 shown on the Data page; compare files by their per-role SHA-256\./);
});
