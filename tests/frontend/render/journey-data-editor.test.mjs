import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// N-6 (four-role report, round R1-5): a mapped binding's role card shows the
// timestamp column it declared (S-D4), not only its hashes.
const EDITOR = "app/features/workspace/JourneyDataEditor.tsx";
const slot = { role: "value.demand.half_hourly", label: "Demand", required: true, formats: ["csv"], unit: "MW" };
const mapped = { filename: "demand.csv", sha256: "b".repeat(64), mapping_provenance: { source_sha256: "s".repeat(64), spec_sha256: "p".repeat(64), normalized_sha256: "b".repeat(64) },
  timestamp_column: "settlement_time", timestamp_time_zone: "Europe/London", timestamp_check: { status: "passed", rows_checked: 17520 } };
const props = (binding) => ({ sourceName: "VALUE 101 baseline", sourcePackName: "VALUE 101 baseline", targetPack: { id: "my-pack", name: "My pack", bindings: { [slot.role]: binding } },
  sourceBindings: {}, slots: [slot], busy: false, onUpload() {}, onPreview() {}, onReturn() {} });

test("the role card names the declared timestamp column, time zone and check", async () => {
  const text = textOf(await renderTsx(EDITOR, "default", props(mapped)));
  assert.match(text, /时间戳列 settlement_time · Europe\/London · 已核对 17520 行/);
});

test("a binding without a timestamp declaration shows none", async () => {
  const plain = { filename: mapped.filename, sha256: mapped.sha256, mapping_provenance: mapped.mapping_provenance };
  assert.doesNotMatch(textOf(await renderTsx(EDITOR, "default", props(plain))), /时间戳列/);
});
