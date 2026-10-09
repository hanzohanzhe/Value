import assert from "node:assert/strict";
import test from "node:test";
import { foldIssues, issueGroup, readinessGroups, rowTitle, splitObject } from "../../../app/features/runs/readinessGroups.ts";

// Spec 11.1 (S-D1): the readiness card shows every issue, grouped by priority.
const issue = (code, severity, scope, message, extra = {}) => ({ code, severity, scope, message, corrective_action: `Fix ${code}`, ...extra });
const unit = (role, expects) => issue("GF_PREFLIGHT_DATA_WARNING", "warning", "data", `${role}: unit is not declared; canonical role expects ${expects}`);

// The re-check report 4.3: two environment errors, the VALUE 101 adapter
// warnings, then the two plausibility findings at the end.
const ERRORS = [
  issue("GF_PREFLIGHT_OUTPUT_PERMISSION", "error", "output", "The output directory is not writable."),
  issue("GF_PREFLIGHT_DISK_SPACE", "error", "output", "Not enough free disk space."),
];
const WARNINGS = [
  issue("GF_PREFLIGHT_UNSAVED_REVISION", "warning", "project", "This legacy project has no saved immutable revision identity."),
  issue("GF_PREFLIGHT_DATA_WARNING", "warning", "data", "demand.forecast: Legacy demand label MWh/period is interpreted as raw MW, as in historical VALUE runs."),
  issue("GF_PREFLIGHT_DATA_WARNING", "warning", "data", "demand.real: Legacy demand label MWh/period is interpreted as raw MW, as in historical VALUE runs."),
  ...["france", "belgium", "netherlands", "norway", "ireland"].flatMap((country) => [unit(`market.${country}.profile`, "MW"), unit(`market.${country}.price`, "GBP/MWh")]),
  issue("GF_DATA_PLAUSIBILITY_PRICE", "warning", "data", "market.france.price: france price range [82, 6087] outside [-500, 5000] GBP/MWh", { layer: "plausibility" }),
  issue("GF_DATA_PLAUSIBILITY_FLOW", "warning", "data", "market.france.profile: france |flow| 500 MW exceeds 58.62 MW", { layer: "plausibility" }),
];

test("issues fall into the six groups in priority order; nothing is dropped", () => {
  const groups = readinessGroups({ errors: ERRORS, warnings: WARNINGS });
  assert.deepEqual(groups.map((group) => group.id), ["errors", "plausibility", "data", "adapter_unit", "environment"]);
  assert.equal(groups.reduce((sum, group) => sum + group.count, 0), ERRORS.length + WARNINGS.length);
  const plausibility = groups.find((group) => group.id === "plausibility");
  assert.equal(plausibility.label, "Data plausibility");
  assert.equal(plausibility.count, 2);
  assert.deepEqual(plausibility.rows.map((row) => row.code), ["GF_DATA_PLAUSIBILITY_PRICE", "GF_DATA_PLAUSIBILITY_FLOW"]);
});

test("errors are always open, plausibility starts open, the rest start folded", () => {
  const groups = Object.fromEntries(readinessGroups({ errors: ERRORS, warnings: WARNINGS }).map((group) => [group.id, group]));
  assert.equal(groups.errors.collapsible, false);
  assert.equal(groups.errors.tone, "danger");
  assert.equal(groups.plausibility.defaultOpen, true);
  for (const id of ["data", "adapter_unit", "environment"]) {
    assert.equal(groups[id].collapsible, true, id);
    assert.equal(groups[id].defaultOpen, false, id);
    assert.equal(groups[id].tone, "caution", id);
  }
});

test("a repeated issue is one row with ×n and the objects it covers", () => {
  const groups = Object.fromEntries(readinessGroups({ errors: [], warnings: WARNINGS }).map((group) => [group.id, group]));
  const units = groups.adapter_unit.rows;
  assert.equal(groups.adapter_unit.count, 10);
  assert.equal(units.length, 2);
  assert.equal(units[0].text, "unit is not declared; canonical role expects MW");
  assert.equal(units[0].count, 5);
  assert.deepEqual(units[0].objects, ["market.france.profile", "market.belgium.profile", "market.netherlands.profile", "market.norway.profile", "market.ireland.profile"]);
  assert.equal(rowTitle(units[0]), units[0].objects.join("\n"));
  const legacy = groups.data.rows;
  assert.equal(legacy.length, 1);
  assert.equal(legacy[0].count, 2);
  assert.deepEqual(legacy[0].objects, ["demand.forecast", "demand.real"]);
});

test("chronology findings group by layer, and by code for an older report", () => {
  assert.equal(issueGroup(issue("GF_DATA_TIMESTAMPS", "warning", "data", "x: gap", { layer: "chronology" })), "chronology");
  assert.equal(issueGroup(issue("GF_DATA_PRICE_CURRENCY", "warning", "data", "x: EUR")), "chronology");
  assert.equal(issueGroup(issue("GF_DATA_PLAUSIBILITY_DEMAND", "warning", "data", "x: high")), "plausibility");
  assert.equal(issueGroup(issue("GF_DATA_PRICE_CURRENCY", "error", "data", "x: EUR")), "errors");
  assert.equal(issueGroup(issue("GF_PREFLIGHT_STAGED_DWELL", "warning", "modules", "dwell")), "environment");
});

test("the object prefix is split only when it is an identifier", () => {
  assert.deepEqual(splitObject("market.france.price: unit is not declared"), { object: "market.france.price", text: "unit is not declared" });
  assert.deepEqual(splitObject("Runs have not finished: 2 runs"), { object: null, text: "Runs have not finished: 2 runs" });
  assert.equal(foldIssues([]).length, 0);
  assert.deepEqual(readinessGroups(null), []);
});

// R3M-5 (round R2): a warning the page already shows in its own notice is not
// counted again; an error with that code would still be listed.
test("warnings shown elsewhere are left out of the groups; errors never are", () => {
  const change = issue("GF_PREFLIGHT_MODULE_SOURCE_CHANGED", "warning", "modules", "Module m source changed since install (a → b).");
  const other = issue("GF_PREFLIGHT_SOLVER_NOTE", "warning", "runtime", "Solver note.");
  const shown = new Set(["GF_PREFLIGHT_MODULE_SOURCE_CHANGED"]);
  assert.deepEqual(readinessGroups({ errors: [], warnings: [change, other] }, shown).map((group) => [group.id, group.count]), [["environment", 1]]);
  assert.deepEqual(readinessGroups({ errors: [], warnings: [change, other] }).map((group) => [group.id, group.count]), [["environment", 2]]);
  const asError = { ...change, severity: "error" };
  assert.deepEqual(readinessGroups({ errors: [asError], warnings: [] }, shown).map((group) => [group.id, group.count]), [["errors", 1]]);
});
