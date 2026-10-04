import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("Data page composes the focused Data Workbench feature", async () => {
  const [page, shell, installed, sources, build, candidates, client, types] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/DataWorkbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/InstalledPacks.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/OfficialSources.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/BuildBenchmark.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/CandidateReview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/client.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/types.ts", import.meta.url), "utf8"),
  ]);
  const feature = [shell, installed, sources, build, candidates].join("\n");

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
  assert.match(client, /\/api\/data-workbench\/v1/);
  assert.match(client, /Unexpected Data Workbench schema/);
  assert.match(client, /Unknown Data Workbench job status/);
  assert.match(client, /value\.data-sources\/v1/);
  assert.match(types, /value\.data-validation-report\/v1/);
});

test("React feature displays backend values and contains no scientific reconstruction", async () => {
  const [shell, installed, sources, build, candidates, types] = await Promise.all([
    readFile(new URL("../app/features/data-workbench/DataWorkbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/InstalledPacks.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/OfficialSources.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/BuildBenchmark.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/CandidateReview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/features/data-workbench/types.ts", import.meta.url), "utf8"),
  ]);
  const feature = [shell, installed, sources, build, candidates].join("\n");

  assert.doesNotMatch(feature, /intersection|pointInPolygon|capacity_weighted|residual\s*=|sha256/i);
  assert.match(feature, /gate_results/);
  assert.match(types, /blocking_reasons/);
  assert.match(feature, /required_actions/);
  assert.match(feature, /audit_map_svg/);
  assert.match(feature, /data:image\/svg\+xml/);
});
