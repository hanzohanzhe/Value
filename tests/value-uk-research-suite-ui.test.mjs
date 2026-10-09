import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("VALUE-UK research suites target the local atomic installation route", async () => {
  const { researchSuiteApiUrl } = await import("../app/features/data/research-suite-api.mjs");

  // P0-1 S9: same-origin only; the UI has no API origin to prepend.
  assert.equal(researchSuiteApiUrl(), "/api/research-suites/install");
  assert.equal(researchSuiteApiUrl.length, 0);
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
  // P1 W3: the installer is on the /data route; its upload (with the rights header) is a workbench action.
  // P1 W4b: the page's wording is the dictionary app/i18n/pages/data.en.ts (data.suite.*).
  const page = (await Promise.all(["../app/data/DataView.tsx", "../app/features/shell/useWorkbenchState.ts", "../app/i18n/pages/data.en.ts"]
    .map((file) => readFile(new URL(file, import.meta.url), "utf8")))).join("\n");

  assert.match(page, /Install the VALUE-UK research suite/);
  assert.match(page, /Install data and create two Studies/);
  assert.match(page, /No Run has started/);
  assert.match(page, /Open copperplate Study/);
  assert.match(page, /Open zonal Study/);
  assert.match(page, /X-VALUE-Data-Rights/);
});
