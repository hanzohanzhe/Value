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

// X0 S12 / P0-9 S11 (spec 2.2, 2.3): methodology pill, validation fields and notices.
const corrected = { status: "recorded", profile_id: "value-corrected", profile_version: "2026.10", label: "Corrected methodology (default)", catalogue_sha256: "catalogue-identity" };
const doctoral = { status: "recorded", profile_id: "doctoral-lineage-0.6.0a2", profile_version: "2026.10", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)" };

test("three profiles: corrected is info, doctoral is caution with the fixed note, pre-profile is muted", () => {
  const ready = resolveRunContext({ run: { ...run, methodology: corrected }, frozen });
  assert.deepEqual([ready.profile.kind, ready.profile.tone, ready.profile.text], ["corrected", "info", "Corrected methodology (default)"]);
  assert.match(ready.profile.title, /Profile value-corrected\./);
  assert.equal(ready.methodologyProfileId, "value-corrected");
  assert.equal(ready.profileCatalogueSha, "catalogue-identity");
  const reproduction = resolveRunContext({ run: { ...run, methodology: doctoral }, frozen });
  assert.deepEqual([reproduction.profile.kind, reproduction.profile.tone], ["doctoral", "caution"]);
  assert.equal(reproduction.profile.text, "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)");
  assert.match(reproduction.profile.title, /Not an exact reproduction of the 2026-07-18 retained trajectory/);
  const legacy = resolveRunContext({ run: { ...run, methodology: { status: "not_recorded", profile_id: null } }, frozen });
  assert.deepEqual([legacy.profile.kind, legacy.profile.tone, legacy.profile.text], ["pre_profile", "muted", "Methodology not recorded (pre-2026-10 run)"]);
  assert.equal(legacy.methodologyProfileId, undefined);
});

test("a versioned corrected id is still the corrected profile; an unresolved or unknown id is never guessed", () => {
  assert.equal(resolveRunContext({ run: { ...run, methodology: { ...corrected, profile_id: "value-corrected-2027" } }, frozen }).profile.kind, "corrected");
  const unresolved = resolveRunContext({ run: { ...run, methodology: { status: "unresolved", profile_id: null } }, frozen });
  assert.deepEqual([unresolved.profile.kind, unresolved.profile.text, unresolved.profile.tone], ["unresolved", "Methodology not recorded", "muted"]);
  const other = resolveRunContext({ run: { ...run, methodology: { status: "recorded", profile_id: "thesis-source", label: "Thesis source rules" } }, frozen });
  assert.deepEqual([other.profile.kind, other.profile.text, other.profile.tone], ["other", "Thesis source rules", "muted"]);
});

test("degradation: an older backend without validation fields shows not-recorded states and no notice", () => {
  const result = resolveRunContext({ run, frozen });
  assert.deepEqual([result.profile.kind, result.profile.text, result.profile.tone], ["unreported", "Methodology not recorded", "muted"]);
  assert.deepEqual([result.energyBalance.text, result.energyBalance.tone, result.energyBalance.dot], ["Not recorded", "muted", false]);
  assert.deepEqual([result.stress.text, result.stress.tone], ["Not recorded", "muted"]);
  assert.deepEqual(result.notices, []);
  assert.equal(result.contractField, null);
  assert.equal(result.methodologyProfileId, undefined);
  assert.equal(result.profileCatalogueSha, undefined);
});

test("energy balance vocabulary maps to the spec words and tones", () => {
  const field = (energy_balance_status, enforcement) => resolveRunContext({ run: { ...run, energy_balance_status, energy_balance: enforcement ? { enforcement } : undefined }, frozen }).energyBalance;
  assert.deepEqual([field("passed").text, field("passed").tone], ["Passed", "ok"]);
  assert.deepEqual([field("failed").text, field("failed").tone], ["Failed", "danger"]);
  assert.deepEqual([field("report_only").text, field("report_only").tone, field("report_only").title], ["Reported", "caution", "Residuals are reported, not yet enforced"]);
  assert.deepEqual([field("reproduction_with_declared_deviations").text, field("reproduction_with_declared_deviations").tone], ["Declared deviations", "caution"]);
  assert.deepEqual([field("not_evaluated").text, field("not_evaluated").tone, field("not_evaluated").dot], ["Not evaluated", "muted", false]);
  assert.deepEqual([field("superseded_pre_fix").text, field("superseded_pre_fix").tone], ["Superseded", "caution"]);
  assert.equal(field("passed", "report_only_until_p0_4_s7").title, "Residuals are reported, not yet enforced");
});

test("stress events: none is muted (never green), a count is amber with the backend shortfall, missing is not recorded", () => {
  const field = (stress) => resolveRunContext({ run: { ...run, stress }, frozen }).stress;
  assert.deepEqual([field({ stress_periods: 0, shortfall_mwh: 0 }).text, field({ stress_periods: 0 }).tone], ["None", "muted"]);
  const r2 = field({ stress_periods: 48, shortfall_mwh: 570.546171074, shortfall_basis: "lower_bound" });
  assert.deepEqual([r2.text, r2.tone, r2.dot], ["48 periods · 571 MWh", "caution", true]);
  assert.match(r2.title, /lower bound/);
  assert.equal(field({ stress_periods: 1, shortfall_mwh: null }).text, "1 period");
  assert.equal(field({ shortfall_mwh: 5 }).text, "Not recorded");
  assert.equal(field(null).text, "Not recorded");
});

test("notices follow the spec priority: failed balance, withheld reproduction, pre-fix, stress", () => {
  const r2 = {
    ...run, methodology: { status: "not_recorded", profile_id: null },
    contract_validation_status: "superseded_pre_fix", scientific_validation_status: "superseded_pre_fix",
    recorded_scientific_validation_status: "passed", recorded_validation_statuses: { contract_validation_status: "passed", scientific_validation_status: "passed" },
    energy_balance_status: "failed",
    energy_balance: { envelope_lower_violations: 48, envelope_upper_violations: 0, maximum_envelope_violation_mwh: 23.4 },
    stress: { stress_periods: 48, shortfall_mwh: 570.546171074 },
    advisories: [{ id: "VALUE-ADV-2026-10-04-REVIEW", severity: "high", title: "Review", summary: "s", affected_metrics: ["total_system_cost_gbp"] }],
  };
  const notices = resolveRunContext({ run: r2, frozen }).notices;
  assert.deepEqual(notices.map((item) => item.id), ["energy_balance_failed", "pre_fix", "stress_events"]);
  assert.equal(notices[0].tone, "danger");
  assert.equal(notices[0].body, "The independent ledger check found 48 periods where supply and use do not reconcile (largest residual 23.4 MWh). Treat results from this Run as unverified.");
  assert.equal(notices[1].body, `This Run's original validation status was "passed". It was produced by a version with known issues; see the advisories that apply to it.`);
  assert.equal(notices[1].advisoryCount, 1);
  assert.equal(notices[2].title, "Supply fell short of demand in 48 periods");
  assert.match(notices[2].body, /^Total shortfall 571 MWh\. These are stress events/);
  const context = resolveRunContext({ run: r2, frozen });
  assert.deepEqual([context.contractField.text, context.scientificField.text], ["Superseded", "Superseded"]);
  assert.match(context.scientificField.title, /Recorded as "passed"/);
});

test("a doctoral Run that fails its raw invariants is withheld, not flagged as a corrected failure", () => {
  const reproduction = {
    ...run, methodology: doctoral, energy_balance_status: "failed", stress: { stress_periods: 0 },
    result_publication: { status: "withheld", reason_code: "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED" },
  };
  const notices = resolveRunContext({ run: reproduction, frozen }).notices;
  assert.deepEqual(notices.map((item) => item.id), ["results_withheld"]);
  assert.deepEqual(notices[0].actions, ["open_inspect", "export_ledger"]);
  assert.equal(notices[0].title, "Annual results withheld for this reproduction run");
});

test("a corrected failure without envelope counts never claims a number of periods", () => {
  const notices = resolveRunContext({ run: { ...run, methodology: corrected, energy_balance_status: "failed", energy_balance: { envelope_lower_violations: 0, envelope_upper_violations: 0 } }, frozen }).notices;
  assert.equal(notices[0].body, "The independent ledger check found periods where supply and use do not reconcile. Treat results from this Run as unverified.");
  assert.equal(resolveRunContext({ run: { ...run, methodology: corrected, energy_balance_status: "passed", stress: { stress_periods: 0 } }, frozen }).notices.length, 0);
});

test("a listing row carries only the advisory count; the detail carries the advisories", () => {
  const listing = { ...run, methodology: { status: "not_recorded", profile_id: null }, advisory_summary: { count: 3 } };
  const result = resolveRunContext({ run: listing, frozen });
  assert.equal(result.notices[0].advisoryCount, 3);
  assert.deepEqual(result.advisories, []);
  assert.equal(result.notices[0].body.includes('"not evaluated"'), true);
});
