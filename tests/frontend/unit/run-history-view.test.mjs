import assert from "node:assert/strict";
import test from "node:test";
import { isActiveRunStatus, moduleEvidenceText, runHistoryEmpty, runIdSuffix, runOptionLabel, runSelectPlaceholder, runStartedText, startedRunNoticeText } from "../../../app/features/runs/runHistoryView.ts";

// Four-role report R-D2, S-D12, M2-N1, R-D12 (round R1-5): the Run history
// tells Runs of one Study apart and never keeps a stale placeholder or notice.
const first = { id: "value-101-basel-20261006-231240-c11e26f1", mode: "value_101_day", status: "completed", created_at: "2026-10-06T23:12:41+01:00" };
const second = { id: "value-101-basel-20261006-231703-fc41b4c7", mode: "value_101_day", status: "completed", created_at: "2026-10-06T23:17:04+01:00" };

test("two Runs of the same Study and scope get different labels (start time and ID suffix)", () => {
  assert.equal(runOptionLabel(first), "One-day market lesson · completed · 2026-10-06 23:12 · c11e26f1");
  assert.equal(runOptionLabel(second), "One-day market lesson · completed · 2026-10-06 23:17 · fc41b4c7");
  assert.notEqual(runOptionLabel(first), runOptionLabel(second));
});

test("the start time is the recorded local clock text, else the timestamp inside the Run ID", () => {
  assert.equal(runStartedText(first), "2026-10-06 23:12");
  assert.equal(runStartedText({ id: first.id }), "2026-10-06 23:12");
  assert.equal(runStartedText({ id: "legacy-run" }), null);
  assert.equal(runOptionLabel({ id: "legacy-run", mode: "smoke", status: "failed" }), "Two-period wiring check · failed · run");
  assert.equal(runIdSuffix("abc"), "abc");
});

test("'No runs yet' only when the Study has no Run; a launch says it is starting", () => {
  assert.equal(runSelectPlaceholder(0), "No runs yet for this Study");
  assert.equal(runSelectPlaceholder(2), "Choose a Run (2)");
  assert.equal(runHistoryEmpty(0, false).title, "No runs yet");
  assert.equal(runHistoryEmpty(2, false).title, "2 Runs for this Study");
  assert.equal(runHistoryEmpty(1, false).title, "1 Run for this Study");
  assert.equal(runHistoryEmpty(0, true).title, "Starting the Run…");
});

test("the start notice follows its Run: kept while active, replaced when it completes or fails", () => {
  const started = { runId: first.id, mode: "value_101_day", text: "The one-day VALUE 101 PSM lesson has started." };
  assert.equal(startedRunNoticeText(started, undefined), started.text);
  assert.equal(startedRunNoticeText(started, { ...first, status: "running" }), started.text);
  assert.equal(startedRunNoticeText(started, first), "The One-day market lesson Run c11e26f1 has completed. Its results are under Run history.");
  assert.equal(startedRunNoticeText(started, { ...first, status: "failed", error_code: "GF_COMPATIBILITY_001" }), "The One-day market lesson Run c11e26f1 failed (GF_COMPATIBILITY_001). The reason is shown under Run history.");
  assert.equal(startedRunNoticeText(started, { ...first, status: "cancelled" }), "The One-day market lesson Run c11e26f1 was cancelled.");
  assert.equal(isActiveRunStatus("snapshotting"), true);
  assert.equal(isActiveRunStatus("archived"), false);
});

test("module evidence: pending only while the Run is active; the one-day lesson names uncalled slots", () => {
  const done = { mode: "value_101_day", status: "completed" };
  assert.equal(moduleEvidenceText(done, "psm", 48), "48 recorded calls");
  assert.equal(moduleEvidenceText(done, "investment", undefined), "Not called in this scope");
  assert.equal(moduleEvidenceText(done, "psm", undefined), "No calls recorded");
  assert.equal(moduleEvidenceText({ mode: "smoke", status: "completed" }, "investment", undefined), "No calls recorded");
  assert.equal(moduleEvidenceText({ mode: "value_101_day", status: "running" }, "investment", undefined), "Evidence pending");
});
