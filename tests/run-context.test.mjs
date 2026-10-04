import assert from "node:assert/strict";
import test from "node:test";
import { resolveRunContext } from "../app/features/workspace/runContext.ts";

const run = {
  id: "run-old", project_id: "study-a", project_name: "Original study", mode: "smoke", status: "completed",
  input_snapshot_id: "snapshot-identity", input_tree_sha256: "tree-identity",
  execution_status: "passed", contract_validation_status: "passed", scientific_validation_status: "not_evaluated",
  run_policy: { label: "Two-period verification", total_periods: 2 }, diagnostic: { total_periods: 2, years: [2025] },
};
const project = {
  id: "study-a", name: "Frozen study name", data_pack_id: "frozen-pack", revision_number: 1,
  revision_sha256: "revision-identity", start_year: 2025, end_year: 2026,
  market_configuration: { network_pack_id: "network-overlay" },
};
const snapshot = {
  state: "ready", snapshot_id: "snapshot-identity", input_tree_sha256: "tree-identity",
  project_sha256: "different-project-content-identity", pack_manifest_sha256: "pack-identity",
  network_pack_id: "network-overlay", network_pack_manifest_sha256: "network-identity",
};
const frozen = { runId: run.id, status: "ready", project, snapshot };

test("no selected Run cannot expose previously loaded source identities", () => {
  const result = resolveRunContext({ frozen });
  assert.equal(result.kind, "empty");
  assert.equal(result.dataPackId, undefined);
  assert.equal(result.runId, undefined);
});

test("historical identity comes only from the frozen revision, keeping base and overlay separate", () => {
  const mutableStudy = { ...project, revision_number: 2, data_pack_id: "new-workspace-pack" };
  const result = resolveRunContext({ run, frozen, selectedProject: mutableStudy, selectedPack: { id: "third-pack" } });
  assert.equal(result.kind, "ready");
  assert.equal(result.dataPackId, "frozen-pack");
  assert.equal(result.networkPackId, "network-overlay");
  assert.equal(result.revisionNumber, 1);
  assert.equal(result.studyName, "Frozen study name");
  assert.equal(result.revisionSha, "revision-identity");
  assert.equal(result.snapshotId, "snapshot-identity");
  assert.equal(result.inputTreeSha, "tree-identity");
});

test("switching Runs with a late old response never displays the old source", () => {
  const result = resolveRunContext({ run: { ...run, id: "run-new" }, frozen });
  assert.equal(result.kind, "loading");
  assert.equal(result.runId, "run-new");
  assert.equal(result.dataPackId, undefined);
  assert.equal(result.revisionNumber, undefined);
});

test("a loading envelope cannot leak data from a previous payload", () => {
  const result = resolveRunContext({ run, frozen: { ...frozen, status: "loading" } });
  assert.equal(result.kind, "loading");
  assert.equal(result.dataPackId, undefined);
});

test("unavailable project does not fall back to a current Study or data pack", () => {
  for (const value of [{ ...frozen, status: "unavailable" }, { ...frozen, project: null }, { ...frozen, project: {} }]) {
    const result = resolveRunContext({ run, frozen: value, selectedProject: project });
    assert.equal(result.kind, "unavailable");
    assert.equal(result.dataPackId, undefined);
    assert.equal(result.studyId, run.project_id);
  }
});

test("mismatched Study, snapshot, tree or network identities are withheld", () => {
  const candidates = [
    { ...frozen, project: { ...project, id: "another-study" } },
    { ...frozen, snapshot: { ...snapshot, snapshot_id: "another-snapshot" } },
    { ...frozen, snapshot: { ...snapshot, input_tree_sha256: "another-tree" } },
    { ...frozen, snapshot: { ...snapshot, network_pack_id: "another-overlay" } },
  ];
  for (const candidate of candidates) {
    const result = resolveRunContext({ run, frozen: candidate });
    assert.equal(result.kind, "mismatch");
    assert.equal(result.dataPackId, undefined);
    assert.equal(result.networkPackId, undefined);
    assert.ok(result.issue);
  }
});

test("a partial snapshot can show known source fields without manufacturing hashes", () => {
  const result = resolveRunContext({ run, frozen: { ...frozen, snapshot: null } });
  assert.equal(result.kind, "partial");
  assert.equal(result.dataPackId, "frozen-pack");
  assert.equal(result.networkPackId, "network-overlay");
  assert.equal(result.dataPackSha, undefined);
  assert.equal(result.snapshotId, undefined);
});

test("a non-ready input snapshot cannot be presented as a frozen source", () => {
  const result = resolveRunContext({ run, frozen: { ...frozen, snapshot: { ...snapshot, state: "staging" } } });
  assert.equal(result.kind, "unavailable");
  assert.equal(result.dataPackId, undefined);
});

test("legacy snapshots without optional identities remain readable but partial", () => {
  const result = resolveRunContext({ run, frozen: { ...frozen, project: { id: "study-a", data_pack_id: "legacy-pack" }, snapshot: {} } });
  assert.equal(result.kind, "partial");
  assert.equal(result.dataPackId, "legacy-pack");
  assert.equal(result.revisionNumber, undefined);
  assert.equal(result.networkPackId, undefined);
});

test("archival and missing or trashed source Studies do not erase frozen evidence", () => {
  for (const source_study_status of ["trash", "missing"]) {
    const result = resolveRunContext({ run: { ...run, status: "archived", source_study_status }, frozen });
    assert.equal(result.kind, "ready");
    assert.equal(result.dataPackId, "frozen-pack");
    assert.equal(result.sourceStudyStatus, source_study_status);
  }
});

test("short Run scope does not inherit configured Study years or scientific approval", () => {
  const result = resolveRunContext({ run, frozen });
  assert.deepEqual(result.scope, { mode: "smoke", label: "Two-period verification", configuredPeriods: 2, years: [2025] });
  assert.equal(result.executionStatus, "passed");
  assert.equal(result.contractStatus, "passed");
  assert.equal(result.scientificStatus, "not_evaluated");
});

test("missing scientific status never becomes passed because execution completed", () => {
  const result = resolveRunContext({ run: { id: "run-old", project_id: "study-a", mode: "full", status: "completed" }, frozen });
  assert.equal(result.scientificStatus, "not_evaluated");
  assert.equal(result.scope.configuredPeriods, undefined);
  assert.equal(result.scope.years, undefined);
});

test("invalid scope counts and revision numbers are omitted rather than displayed as facts", () => {
  const result = resolveRunContext({
    run: { ...run, diagnostic: { total_periods: NaN, years: [2025, -1] }, run_policy: { total_periods: -2 } },
    frozen: { ...frozen, project: { ...project, revision_number: -1 } },
  });
  assert.equal(result.scope.configuredPeriods, undefined);
  assert.equal(result.scope.years, undefined);
  assert.equal(result.revisionNumber, undefined);
});
