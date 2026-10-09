import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("Data page composes the focused Data Workbench feature", async () => {
  const [page, shell, installed, sources, build, candidates, client, types, dictionary] = await Promise.all([
    // P1 W3: the Data page is the /data route.
    readFile(new URL("../app/data/DataView.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/DataWorkbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/InstalledPacks.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/OfficialSources.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/BuildBenchmark.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/CandidateReview.tsx", import.meta.url), "utf8"),
    // P1 W5: the client's own error wording is in the dictionary (workbenchClient.*).
    Promise.all(["../app/features/data-workbench/client.ts", "../app/i18n/messages/viewModels.en.ts"].map((file) => readFile(new URL(file, import.meta.url), "utf8"))).then((parts) => parts.join("\n")),
    readFile(new URL("../app/features/data-workbench/types.ts", import.meta.url), "utf8"),
    // P1 W4b: the feature's wording is its dictionary (dataWorkbench.*); the components use the keys.
    readFile(new URL("../app/i18n/pages/dataWorkbench.en.ts", import.meta.url), "utf8"),
  ]);
  const feature = [shell, installed, sources, build, candidates, dictionary].join("\n");

  assert.match(page, /<DataWorkbench/);
  assert.match(feature, /Installed packs/);
  assert.match(feature, /Official sources/);
  assert.match(feature, /Build benchmark/);
  assert.match(feature, /Candidates & review/);
  assert.match(feature, /Mechanical gate failure/);
  assert.match(client, /accepted_waivers/);
  assert.match(feature, /reviewer/);
  assert.match(feature, /version/);
  assert.match(feature, /experimental candidate/i);
  assert.match(client, /apiUrl\("data-workbench\/v1"\)/);
  assert.match(client, /Unexpected Data Workbench schema/);
  assert.match(client, /Unknown Data Workbench job status/);
  assert.match(client, /value\.data-sources\/v1/);
  assert.match(types, /value\.data-validation-report\/v1/);
});

test("React feature displays backend values and contains no scientific reconstruction", async () => {
  const [shell, installed, sources, build, candidates, types, dictionary] = await Promise.all([
    readFile(new URL("../app/features/data-workbench/DataWorkbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/InstalledPacks.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/OfficialSources.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/BuildBenchmark.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/CandidateReview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/types.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/i18n/pages/dataWorkbench.en.ts", import.meta.url), "utf8"),
  ]);
  const feature = [shell, installed, sources, build, candidates, dictionary].join("\n");

  assert.doesNotMatch(feature, /intersection|pointInPolygon|capacity_weighted|residual\s*=|sha256/i);
  assert.match(feature, /gate_results/);
  assert.match(types, /blocking_reasons/);
  assert.match(feature, /required_actions/);
  assert.match(feature, /audit_map_svg/);
  assert.match(feature, /data:image\/svg\+xml/);
});
