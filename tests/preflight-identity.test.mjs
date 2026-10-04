import assert from "node:assert/strict";
import test from "node:test";
import { preflightMatches } from "../app/features/workspace/preflightIdentity.ts";

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
