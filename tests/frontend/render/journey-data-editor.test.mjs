import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// N-6 (four-role report, round R1-5): a mapped binding's role card shows the
// timestamp column it declared (S-D4), not only its hashes.
const EDITOR = "app/features/workspace/JourneyDataEditor.tsx";
// P1 W4b: the R2 Chinese wording is the zh dictionary; these checks render in Chinese (same meaning), and the English default is checked below.
const FIXTURES = "tests/frontend/helpers/pages-b-fixtures.tsx";
const zh = (props) => renderTsx(FIXTURES, "JourneyDataEditorIn", { locale: "zh", ...props });
const slot = { role: "value.demand.half_hourly", label: "Demand", required: true, formats: ["csv"], unit: "MW" };
const mapped = { filename: "demand.csv", sha256: "b".repeat(64), mapping_provenance: { source_sha256: "s".repeat(64), spec_sha256: "p".repeat(64), normalized_sha256: "b".repeat(64) },
  timestamp_column: "settlement_time", timestamp_time_zone: "Europe/London", timestamp_check: { status: "passed", rows_checked: 17520 } };
const props = (binding) => ({ sourceName: "VALUE 101 baseline", sourcePackName: "VALUE 101 baseline", targetPack: { id: "my-pack", name: "My pack", bindings: { [slot.role]: binding } },
  sourceBindings: {}, slots: [slot], busy: false, onUpload() {}, onPreview() {}, onReturn() {} });

test("the role card names the declared timestamp column, time zone and check", async () => {
  const text = textOf(await zh(props(mapped)));
  assert.match(text, /时间戳列 settlement_time · Europe\/London · 已核对 17520 行/);
  assert.match(textOf(await renderTsx(EDITOR, "default", props(mapped))), /Timestamp column settlement_time · Europe\/London · checked 17520 rows/);
});

test("a binding without a timestamp declaration shows none", async () => {
  const plain = { filename: mapped.filename, sha256: mapped.sha256, mapping_provenance: mapped.mapping_provenance };
  assert.doesNotMatch(textOf(await zh(props(plain))), /时间戳列/);
  assert.doesNotMatch(textOf(await renderTsx(EDITOR, "default", props(plain))), /Timestamp column/);
});

// S-低5 (R4, A27): the role card shows the EUR conversion of a mapped price,
// and a read-only pack still lets the user browse its roles.
test("the role card names the FX declaration and the role list stays browsable when read-only", async () => {
  const price = { role: "market.france.price", label: "France price", required: false, formats: ["csv"], unit: "GBP/MWh" };
  const binding = { filename: "price.csv", sha256: "c".repeat(64), mapping_provenance: mapped.mapping_provenance,
    source_currency: "EUR", eur_per_gbp: 1.17, fx_basis: "annual average", price_year: 2025,
    timestamp_column: "time", timestamp_time_zone: "UTC", timestamp_date_order: "day_first", timestamp_check: { status: "passed", rows_checked: 17520 } };
  const html = await zh({ ...props(binding), slots: [price, slot], targetPack: { id: "my-pack", name: "My pack", bindings: { [price.role]: binding } },
    readOnlyReason: "此数据包已被 Study 引用，只读。" });
  const text = textOf(html);
  assert.match(text, /原币种 EUR · 汇率 1\.17 EUR\/GBP · 汇率口径 annual average · 价格年份 2025/);
  assert.match(text, /时间戳列 time · UTC · DD\/MM\/YYYY · 已核对 17520 行/);
  const select = /<select id="[^"]*-role"[^>]*>/.exec(html)?.[0] ?? "";
  assert.ok(select, "role select rendered");
  assert.doesNotMatch(select, /disabled/);
});

test("P1 W4b: the editor speaks English by default and Chinese when chosen", async () => {
  const english = textOf(await renderTsx(EDITOR, "default", props(mapped)));
  assert.match(english, /Connect my files to an independent BASE pack/);
  assert.match(english, /Baseline Study: VALUE 101 baseline · original BASE pack: VALUE 101 baseline/);
  assert.match(english, /1\. Choose the semantic role of the file/);
  assert.match(english, /Keep the target pack and return to the research guide/);
  assert.doesNotMatch(english, /[一-鿿]/, "no Chinese in the English interface");
  const chinese = textOf(await zh(props(mapped)));
  assert.match(chinese, /将我的文件连接到独立 BASE 包/);
  assert.match(chinese, /保留目标包并返回研究引导/);
});
