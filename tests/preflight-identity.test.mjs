import assert from "node:assert/strict";
import test from "node:test";
import { isUnidentifiedBlockedReport, preflightMatches, preflightRunBlockedReason } from "../app/features/workspace/preflightIdentity.ts";

test("preflight evidence belongs to one saved revision, pack and requested scope", () => {
  const project = { id: "study-a", revision_sha256: "revision-a", data_pack_id: "pack-a" };
  const report = { project_id: project.id, project_revision_sha256: project.revision_sha256, data_pack_id: project.data_pack_id, mode: "smoke" };
  assert.equal(preflightMatches(report, project, "smoke"), true);
  for (const change of [{ id: "study-b" }, { revision_sha256: "revision-b" }, { data_pack_id: "pack-b" }]) {
    assert.equal(preflightMatches(report, { ...project, ...change }, "smoke"), false);
  }
  assert.equal(preflightMatches(report, project, "two_year"), false);
});

test("missing identity is never presented as a matching preflight", () => {
  const project = { id: "study-a", data_pack_id: "pack-a" };
  assert.equal(preflightMatches({ project_id: "study-a", data_pack_id: "pack-a", mode: "smoke" }, project, "smoke"), false);
  assert.equal(preflightMatches(null, { ...project, revision_sha256: "a" }, "smoke"), false);
});

test("a blocked report without a computed revision is still shown (spec 11.4, M-D3)", () => {
  const project = { id: "study-a", revision_sha256: "revision-a", data_pack_id: "pack-a" };
  const quarantined = { code: "GF_PREFLIGHT_MODULE_QUARANTINED", severity: "error", message: "The Study selects quarantined local code" };
  const blocked = { project_id: project.id, project_revision_sha256: null, data_pack_id: project.data_pack_id, mode: "smoke", accepted: false, errors: [quarantined] };
  assert.equal(isUnidentifiedBlockedReport(blocked), true);
  assert.equal(preflightMatches(blocked, project, "smoke"), true);
  assert.equal(preflightMatches(blocked, project, "two_year"), false);
  assert.equal(preflightMatches(blocked, { ...project, id: "study-b" }, "smoke"), false);
  // An accepted report, or one without errors, still needs the exact revision.
  assert.equal(preflightMatches({ ...blocked, accepted: true }, project, "smoke"), false);
  assert.equal(preflightMatches({ ...blocked, errors: [] }, project, "smoke"), false);
  assert.equal(preflightRunBlockedReason(blocked), "Readiness found 1 error. Fix it, then check readiness again.");
  assert.equal(preflightRunBlockedReason({ accepted: false, errors: [quarantined, quarantined] }), "Readiness found 2 errors. Fix them, then check readiness again.");
  assert.equal(preflightRunBlockedReason({ accepted: true, errors: [] }), null);
  assert.equal(preflightRunBlockedReason(null), null);
});
