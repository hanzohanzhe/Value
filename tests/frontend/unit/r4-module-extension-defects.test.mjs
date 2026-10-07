import assert from "node:assert/strict";
import test from "node:test";
import { extensionSourceChangeNote } from "../../../app/features/modules/disabledEntries.ts";
import { codeIdentityUpdate } from "../../../app/features/studies/studyMigration.ts";
import { preflightMatches } from "../../../app/features/workspace/preflightIdentity.ts";

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
