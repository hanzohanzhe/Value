import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("VALUE-UK research suites target the local atomic installation route", async () => {
  const { researchSuiteApiUrl } = await import("../app/features/data/research-suite-api.mjs");

  assert.equal(
    researchSuiteApiUrl("http://127.0.0.1:9901/"),
    "http://127.0.0.1:9901/api/research-suites/install",
  );
});

test("the installed-suite summary keeps component hashes and unrun Study identities", async () => {
  const { describeResearchSuiteInstallation } = await import("../app/features/data/research-suite-api.mjs");
  const summary = describeResearchSuiteInstallation({
    suite_id: "value-uk-research-suite-v1",
    suite_sha256: "a".repeat(64),
    component_pack_ids: ["value-uk-open-data-pack-v1", "value-gb-zonal-network-v1"],
    component_bundle_sha256: ["b".repeat(64), "c".repeat(64)],
    study_ids: ["value-uk-copperplate-2025-2034", "value-uk-zonal-2025-2034"],
    idempotent: false,
  });

  assert.equal(summary.components.length, 2);
  assert.equal(summary.components[1].sha256, "c".repeat(64));
  assert.deepEqual(summary.studyIds, [
    "value-uk-copperplate-2025-2034",
    "value-uk-zonal-2025-2034",
  ]);
  assert.equal(summary.runStarted, false);
});

test("the Data page exposes research-suite installation without starting a Run", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(page, /Install the VALUE-UK research suite/);
  assert.match(page, /Install data and create two Studies/);
  assert.match(page, /No Run has started/);
  assert.match(page, /Open copperplate Study/);
  assert.match(page, /Open zonal Study/);
  assert.match(page, /X-VALUE-Data-Rights/);
});
