import assert from "node:assert/strict";
import test from "node:test";

import {
  buildStudyTrashConfirmation,
  networkPackReadinessLabel,
  sourceStudyAllowsDerivedRun,
} from "../app/features/learn/studyLifecycle.ts";

test("historical Study evidence requires its exact human-readable name", () => {
  const result = buildStudyTrashConfirmation(
    { id: "study-a", name: "Study A" },
    3,
  );
  assert.deepEqual(result, {
    requiresExactName: true,
    expected: "Study A",
    message: "This Study has 3 historical Runs. Type its exact name to move it to recoverable trash:\nStudy A",
  });
});

test("a Study without Runs uses ordinary confirmation", () => {
  const result = buildStudyTrashConfirmation(
    { id: "study-a", name: "Study A" },
    0,
  );
  assert.deepEqual(result, {
    requiresExactName: false,
    expected: "Study A",
    message: "Move Study A and all of its immutable revisions to recoverable trash?",
  });
});

test("only an active source Study can create a derived Run", () => {
  assert.equal(sourceStudyAllowsDerivedRun("active"), true);
  assert.equal(sourceStudyAllowsDerivedRun("trash"), false);
  assert.equal(sourceStudyAllowsDerivedRun("missing"), false);
  assert.equal(sourceStudyAllowsDerivedRun(undefined), true);
});

test("network-pack wording distinguishes unresolved from verified identity", () => {
  assert.equal(networkPackReadinessLabel(undefined), "Check readiness to confirm");
  assert.equal(
    networkPackReadinessLabel({ status: "data_ready", network_pack_id: "value-101-network-v1" }),
    "value-101-network-v1 · verified",
  );
  assert.equal(
    networkPackReadinessLabel({ status: "blocked", network_pack_id: "wrong-pack" }),
    "Check readiness failed — review the missing or incompatible role below",
  );
});
