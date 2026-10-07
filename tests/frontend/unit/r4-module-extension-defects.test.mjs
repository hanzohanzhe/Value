import assert from "node:assert/strict";
import test from "node:test";
import { extensionSourceChangeNote } from "../../../app/features/modules/disabledEntries.ts";
import { codeIdentityUpdate } from "../../../app/features/studies/studyMigration.ts";
import { derivationNotes } from "../../../app/features/modules/derivationNotes.ts";
import { environmentBlockers, preflightMatches } from "../../../app/features/workspace/preflightIdentity.ts";
import { moduleEvidenceText } from "../../../app/features/runs/runHistoryView.ts";

// R4 (DECISIONS A27), four-role report sections 4.3 and 5.3: edit-module and
// add-feature defects (M-*, F-*).

test("M-中2 / F-中1: a REIDENTIFY report names the saved revision and is shown", () => {
  const study = { id: "s", revision_sha256: "a".repeat(64), data_pack_id: "p" };
  // The backend reports the saved (declared) revision it evaluated; the hash
  // the installed code computes is a separate field.
  const report = { project_id: "s", project_revision_sha256: "a".repeat(64), calculated_project_revision_sha256: "b".repeat(64), data_pack_id: "p", mode: "smoke", accepted: true, errors: [] };
  assert.equal(preflightMatches(report, study, "smoke"), true);
  // A report for another saved revision is still refused.
  assert.equal(preflightMatches({ ...report, project_revision_sha256: "c".repeat(64) }, study, "smoke"), false);
});

test("F-中2: an extension edited in place says so on its card", () => {
  const changes = [{ extension_id: "obs", implementation: "pkg.hooks", installed_sha256: "1234567890".repeat(6) + "abcd", current_sha256: "abcdef0123".repeat(6) + "abcd" }];
  assert.equal(extensionSourceChangeNote("other", changes), null);
  assert.equal(extensionSourceChangeNote("obs", undefined), null);
  const note = extensionSourceChangeNote("obs", changes);
  assert.match(note, /^Source changed since install \(pkg\.hooks 12345678… → abcdef01…\)\./);
  assert.match(note, /Results may change; Runs record the new source hash\./);
});

test("F-中2: a source-reidentify revision is not described as 'no change expected'", () => {
  const text = codeIdentityUpdate({ revision_reason: "source-reidentify", revision_sha256: "0123456789abcdef0123" });
  assert.equal(text, "Updated to code identity 0123456789ab (installed local code was edited in place; results may differ)");
  assert.match(codeIdentityUpdate({ revision_reason: "code-identity-upgrade", revision_sha256: "0123456789abcdef0123" }), /no change to methods or results expected/);
});

test("M-中3: a derivation says when it re-identified the source or started from a newer module graph", () => {
  assert.deepEqual(derivationNotes({ ok: true, project: { id: "x" } }), []);
  assert.deepEqual(derivationNotes(null), []);
  const notes = derivationNotes({
    source_migration: { revision_number: 3, revision_reason: "code-identity-upgrade" },
    source_graph_drift: { differences: [{ slot: "storage_cost", module_id: "hx-flat", field: "source_sha256" }, { slot: "storage_cost", module_id: "hx-flat", field: "module_version" }] },
  });
  assert.equal(notes[0], "The source Study was first re-identified as revision 3 (code-only change, no confirmation needed).");
  assert.equal(notes[1], "The source's module code changed since its revision was saved (storage_cost hx-flat). For a one-change comparison, compare with a new Run of the source Study.");
  assert.match(derivationNotes({ source_migration: { revision_reason: "source-reidentify" } })[0], /installed local code was edited in place/);
});

test("M-中1: the storage-cost slot reads the market-ledger evidence, not 'Not called'", () => {
  const lesson = { mode: "value_101_day", status: "completed" };
  const ledger = { version: null, actions: null, years: [2025], source: "market_ledger", storage_asset_periods: 17520 };
  assert.equal(moduleEvidenceText(lesson, "storage_cost", ledger.actions, ledger), "Called inside the PSM: the market ledger records its storage offers (17,520 storage asset-periods)");
  assert.equal(moduleEvidenceText({ mode: "smoke", status: "completed" }, "storage_cost", null, { ...ledger, storage_asset_periods: null }), "Called inside the PSM: the market ledger records its storage offers");
  // Without evidence the old wording stays; stage events still count calls.
  assert.equal(moduleEvidenceText(lesson, "storage_cost", undefined), "Not called in this scope");
  assert.equal(moduleEvidenceText(lesson, "psm", 1, { version: "6.7.0", actions: 1, years: [2025] }), "1 recorded calls");
});

test("M-低2: installation errors are found so the method confirmation waits for them", () => {
  assert.deepEqual(environmentBlockers(null), []);
  assert.deepEqual(environmentBlockers({ errors: [
    { scope: "project", code: "GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED" },
    { scope: "environment", code: "GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED" },
  ] }), ["GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED"]);
  assert.deepEqual(environmentBlockers({ errors: [{ scope: "modules", code: "GF_PREFLIGHT_MODULE_QUARANTINED" }] }), []);
});
