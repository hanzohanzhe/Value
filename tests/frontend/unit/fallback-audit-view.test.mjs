import assert from "node:assert/strict";
import test from "node:test";
import { fallbackAuditSentences } from "../../../app/features/network/fallbackAuditView.ts";

// Spec 4.6 / F-P08-1: the run-time fallback audit Callout text.
test("each flagged technology-year reads as the spec sentence; no flag, no notice", () => {
  const audit = { schema_version: "value.zonal-runtime-fallback-summary/v1", years: [], spatially_indicative: true,
    spatially_indicative_technologies: [{ year: 2025, technology: "offshore_wind", fallback_fraction: 0.4213, fallback_mw: 842.6, fallback_zone_ids: ["Z1"] }] };
  assert.deepEqual(fallbackAuditSentences(audit), ["Spatially indicative: 42.1% of offshore wind capacity fell back to Z1."]);
  const two = { ...audit, spatially_indicative_technologies: [...audit.spatially_indicative_technologies, { year: 2026, technology: "solar", fallback_fraction: 0.25, fallback_mw: 10, fallback_zone_ids: ["Z1", "Z2"] }] };
  assert.deepEqual(fallbackAuditSentences(two), ["Spatially indicative: 42.1% of offshore wind capacity fell back to Z1 (2025).", "Spatially indicative: 25% of solar capacity fell back to Z1, Z2 (2026)."]);
  assert.deepEqual(fallbackAuditSentences({ ...audit, spatially_indicative: false, spatially_indicative_technologies: [] }), []);
  assert.deepEqual(fallbackAuditSentences(null), []);
  assert.deepEqual(fallbackAuditSentences({ status: "invalid", error: "bad file" }), []);
});
