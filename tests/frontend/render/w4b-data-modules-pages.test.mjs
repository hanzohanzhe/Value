import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// P1 W4b (spec 6.3, 6.4): the Data, Modules and Extensions components in both
// interface languages, with app/ui building blocks.
const FIXTURES = "tests/frontend/helpers/pages-b-fixtures.tsx";
const render = (name, props) => renderTsx(FIXTURES, name, props);
const quarantine = { status: "degraded", entries: [{ kind: "module", id: "my-storage-module", version: "1.2.0", error_code: "GF_MODULE_IMPORT_FAILED", message: "Import failed" }] };

test("the quarantine panel is an amber alert with Buttons; Chinese keeps the R4/R6 meaning", async () => {
  const english = await render("ModuleQuarantinePanelIn", { locale: "en", report: quarantine, busy: "", onDisable() {}, onRescan() {} });
  assert.match(english, /class="v-callout v-callout--attention module-quarantine-panel" role="alert"/);
  assert.match(english, /class="v-btn v-btn--primary v-btn--sm"><span class="v-btn__label">Disable<\/span>/);
  const chinese = textOf(await render("ModuleQuarantinePanelIn", { locale: "zh", report: quarantine, busy: "", onDisable() {}, onRescan() {} }));
  assert.match(chinese, /1 个外部模块已隔离/);
  assert.match(chinese, /VALUE 启动时未加载它。需要它的 Run 在修复或停用之前不能启动。/);
  assert.match(chinese, /停用 重新扫描/);
  assert.match(chinese, /GF_MODULE_IMPORT_FAILED/, "the error code is never translated");
});

test("the Disabled and quarantined area in Chinese", async () => {
  const entries = [{ key: "module:m", kind: "module", id: "m", label: "m 1.0.0", state: "disabled", canEnable: true, canRemove: true, manifestFiles: ["m.json"] }];
  const text = textOf(await render("DisabledEntriesPanelIn", { locale: "zh", entries, busy: "", errors: {}, onEnable() {}, onRescan() {}, onRemove() {} }));
  assert.match(text, /已停用与已隔离/);
  assert.match(text, /模块 · 已停用/);
  assert.match(text, /manifest 文件（1 个）: modules\/m\.json/);
  assert.match(text, /启用 重新扫描 移除/);
});

test("the validation panel follows the language and keeps its English markers", async () => {
  const report = { valid: true, errors: [], warnings: [], layers: {}, profile_eligibility: { "value-corrected": { eligible: true } } };
  const english = textOf(await render("DataPackValidationPanelIn", { locale: "en", packId: "p", report }));
  assert.match(english, /Validation Structural ● Passed Chronology ● Passed Plausibility ● Passed/);
  const chinese = textOf(await render("DataPackValidationPanelIn", { locale: "zh", packId: "p", report }));
  assert.match(chinese, /校验 结构 ● 通过 时间轴 ● 通过 合理性 ● 通过/);
  assert.match(chinese, /方法学口径可用性 修正口径 ● 可用/);
});

test("the data preview shows tables, and JSON only inside Technical details", async () => {
  const preview = { schema_version: "v", role: "demand.real", status: "bound", format: "csv", sampled_rows: 2, columns: ["time", "mw"],
    numeric_ranges: { mw: { minimum: 10, maximum: 20 } }, array_counts: {}, sample: [{ time: "2025-01-01T00:00Z", mw: 10 }, { time: "2025-01-01T00:30Z", mw: 20 }], source_sha256: "a".repeat(64) };
  const html = await render("DataPreviewPanelIn", { locale: "en", preview, onClose() {} });
  assert.match(html, /<caption>Numeric ranges<\/caption>/);
  assert.match(html, /<caption>Sample rows<\/caption>/);
  assert.match(html, /<th scope="row">mw<\/th><td class="v-num">10<\/td><td class="v-num">20<\/td>/);
  const outside = html.replace(/<details[\s\S]*?<\/details>/g, "");
  assert.doesNotMatch(outside, /<pre>/, "no raw JSON outside the disclosure");
  assert.match(html, /<details class="v-disclosure"><summary>[\s\S]*Technical details \(raw preview\)/);
  assert.match(textOf(await render("DataPreviewPanelIn", { locale: "zh", preview, onClose() {} })), /服务端限量预览 .* 数值范围/);
});

test("the adapter guide is on /data, collapsed, in both languages", async () => {
  const html = await render("AdapterGuideIn", { locale: "en" });
  assert.match(textOf(html), /Bring another dataset into VALUE/);
  assert.match(html, /<details class="v-disclosure">/);
  assert.doesNotMatch(html, /<details class="v-disclosure" open/);
  assert.match(textOf(await render("AdapterGuideIn", { locale: "zh" })), /把其他数据集接入 VALUE/);
});

test("an empty Workbench list says why it is empty (EmptyState)", async () => {
  const html = await render("InstalledPacksIn", { locale: "en", bundles: [] });
  assert.match(html, /class="v-empty data-workbench-empty"/);
  assert.match(textOf(html), /No promoted Workbench bundle/);
  assert.match(textOf(await render("InstalledPacksIn", { locale: "zh", bundles: [] })), /没有已晋升的 Workbench 数据包/);
});

test("the in-page navigation is a labelled nav of fragment links; the first section is current", async () => {
  const html = await render("SectionNavIn", { locale: "en", label: "Sections of the Modules page", sections: [{ id: "modules-catalog", label: "Catalog", count: 19 }, { id: "modules-disabled", label: "Disabled & quarantined", count: 0 }, { id: "modules-author", label: "Author a module" }] });
  assert.match(html, /<nav class="section-nav" aria-label="Sections of the Modules page">/);
  assert.match(html, /<a href="#modules-catalog" aria-current="location">Catalog<span class="section-nav-count">19<\/span><\/a>/);
  assert.match(html, /<a href="#modules-author">Author a module<\/a>/);
  assert.equal((html.match(/aria-current/g) ?? []).length, 1);
});
