import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { translator } from "../../../app/i18n/index.ts";
import { headerParts, suggestSourceColumns, unitToken } from "../../../app/features/data/csvMappingSuggest.ts";
import { ACTIVE_JOB_STORAGE_KEY, MAX_POLL_FAILURES, elapsedSeconds, isActiveJob, pollDelay, progressPercent, readTrackedJob, writeTrackedJob } from "../../../app/features/data-workbench/jobTracking.ts";
import { EXTENSIONS_PAGE_SECTIONS, MODULES_PAGE_SECTIONS } from "../../../app/features/modules/modulesPage.ts";
import { DATA_PAGE_SECTIONS, previewCell, previewSampleTable } from "../../../app/features/data/dataPage.ts";
import { disableConfirmation, pendingRunsQuestion, quarantineIntro, quarantineTitle, stoppedRunsNotice } from "../../../app/features/modules/module-quarantine.mjs";
import { enableFailureHint, installedModuleCard, moduleUsageNote, removeConfirmation } from "../../../app/features/modules/disabledEntries.ts";
import { inputsPresentSuffix, methodologyUse, validationLayers } from "../../../app/features/data/dataPackValidation.ts";
import { fxCaption, fxErrors, reviewExpiryText, timestampCoverageText } from "../../../app/features/data/csvMappingFx.ts";
import { derivationNotes } from "../../../app/features/modules/derivationNotes.ts";

// P1 W4b (spec 6.3, 6.4): Data, Modules and Extensions pages.
const en = translator("en");
const zh = translator("zh");

test("F4-13: a same-name source column is suggested; case, separators and a matching unit do not matter", () => {
  assert.deepEqual(headerParts("Demand (MW)"), { full: "demandmw", stem: "demand", units: ["mw"] });
  assert.deepEqual(headerParts("demand_mw"), { full: "demandmw", stem: "demand", units: ["mw"] });
  assert.deepEqual(headerParts("Timestamp (UTC)"), { full: "timestamputc", stem: "timestamp", units: ["?"] });
  assert.equal(unitToken("GBP/MWh"), "gbp/mwh");
  assert.equal(unitToken("MWh/period"), "mwh/period");
  assert.equal(unitToken(null), null);
  assert.deepEqual(suggestSourceColumns(["value"], ["load", "other"]), [""], "no match, no suggestion");
  assert.deepEqual(suggestSourceColumns(["demand_mw", "timestamp"], ["Timestamp", "Demand (MW)", "notes"]), ["Demand (MW)", "Timestamp"]);
  assert.deepEqual(suggestSourceColumns(["timestamp"], ["Timestamp (UTC)"], [null]), ["Timestamp (UTC)"], "a non-unit annotation on a unitless column");
  assert.deepEqual(suggestSourceColumns(["price"], ["price", "PRICE"]), [""], "two candidates are ambiguous: the user chooses");
  assert.deepEqual(suggestSourceColumns(["value", "value_mw"], ["value"]), ["", ""], "one source is never suggested for two targets");
  assert.deepEqual(suggestSourceColumns(["value"], ["Value"], ["MW"]), ["Value"], "a header without a unit is suggested; the hint names the unit");
  assert.deepEqual(suggestSourceColumns(["Installed Capacity (MWelec)"], ["installed capacity (MWelec)"], ["MW"]), ["installed capacity (MWelec)"]);
});

test("F4-13 (review W4b): a header that states a different unit is never suggested", () => {
  // The editor sets source_unit = target_unit for a suggestion, so a different unit would enter unconverted (1000x / 2x).
  assert.deepEqual(suggestSourceColumns(["demand_mwh", "capacity_mw"], ["demand_mw", "capacity_kw"]), ["", ""]);
  assert.deepEqual(suggestSourceColumns(["demand_mwh", "capacity_mw"], ["demand_mw", "capacity_kw"], ["MWh", "MW"]), ["", ""]);
  assert.deepEqual(suggestSourceColumns(["capacity_mw"], ["Capacity (kW)"], ["MW"]), [""]);
  assert.deepEqual(suggestSourceColumns(["capacity_mw"], ["capacity [GW]"], ["MW"]), [""]);
  assert.deepEqual(suggestSourceColumns(["value"], ["value_kw"], ["MW"]), [""], "the contract unit decides when the target name has none");
  assert.deepEqual(suggestSourceColumns(["value"], ["value (MWh/period)"], ["MW"]), [""], "per-period energy is not MW");
  assert.deepEqual(suggestSourceColumns(["value"], ["value_eur_per_mwh"], ["GBP/MWh"]), [""], "a EUR price is not a GBP price");
  assert.deepEqual(suggestSourceColumns(["value"], ["value (MW, half-hourly)"], ["MW"]), [""], "an unreadable unit annotation is left to the user");
  assert.deepEqual(suggestSourceColumns(["value"], ["value_mw"], [null]), [""], "a unit on a column without a unit contract is left to the user");
  assert.deepEqual(suggestSourceColumns(["capacity_mw", "demand_mwh"], ["capacity_kw", "Capacity (MW)", "demand_mwh"], ["MW", "MWh"]), ["Capacity (MW)", "demand_mwh"], "the same-unit header is chosen over the other unit");
  assert.deepEqual(suggestSourceColumns(["value"], ["value_gbp_per_mwh"], ["GBP/MWh"]), ["value_gbp_per_mwh"]);
  // The hint names the unit the suggestion assumes, in both languages.
  assert.match(en("mapping.autoMatchedUnit", { unit: "MW" }), /set to MW/);
  assert.match(zh("mapping.autoMatchedUnit", { unit: "MW" }), /原始单位设为 MW/);
});

test("F4-05: job polling backs off after failures and gives up after five; progress and elapsed time", () => {
  assert.equal(pollDelay(0), 650);
  assert.deepEqual([1, 2, 3, 4, 5].map(pollDelay), [1300, 2600, 5200, 10000, 10000]);
  assert.equal(MAX_POLL_FAILURES, 5);
  assert.equal(isActiveJob({ status: "running" }), true);
  assert.equal(isActiveJob({ status: "cancel_requested" }), true);
  for (const status of ["completed", "failed", "cancelled"]) assert.equal(isActiveJob({ status }), false, status);
  assert.equal(isActiveJob(null), false);
  assert.equal(progressPercent(0.01), 1);
  assert.equal(progressPercent(0.426), 43);
  assert.equal(progressPercent(7), 100);
  assert.equal(progressPercent(undefined), 0);
  const start = "2026-10-08T10:00:00Z";
  assert.equal(elapsedSeconds({ status: "running", created_at: start, updated_at: start }, Date.parse("2026-10-08T10:01:05Z")), 65);
  assert.equal(elapsedSeconds({ status: "completed", created_at: start, updated_at: "2026-10-08T10:00:30Z" }, Date.parse("2026-10-08T11:00:00Z")), 30, "a finished job stops the clock");
  assert.equal(elapsedSeconds({ status: "running" }, Date.now()), null);
});

test("F4-05: the followed job survives a reload through storage; blocked storage never breaks the page", () => {
  const store = new Map();
  const storage = { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => store.set(key, value), removeItem: (key) => store.delete(key) };
  assert.equal(readTrackedJob(storage), null);
  writeTrackedJob(storage, "job-123");
  assert.equal(store.get(ACTIVE_JOB_STORAGE_KEY), "job-123");
  assert.equal(readTrackedJob(storage), "job-123");
  writeTrackedJob(storage, null);
  assert.equal(readTrackedJob(storage), null);
  store.set(ACTIVE_JOB_STORAGE_KEY, "not an id <script>");
  assert.equal(readTrackedJob(storage), null, "only an id-shaped value is used");
  const throwing = { getItem() { throw new Error("SecurityError"); }, setItem() { throw new Error("SecurityError"); }, removeItem() { throw new Error("SecurityError"); } };
  assert.equal(readTrackedJob(throwing), null);
  assert.doesNotThrow(() => writeTrackedJob(throwing, "job-1"));
  assert.equal(readTrackedJob(null), null);
});

test("R3-22: Modules lists the catalogue first and the author tools last; Extensions and Data likewise", () => {
  assert.deepEqual(MODULES_PAGE_SECTIONS.map((section) => section.id), ["modules-catalog", "modules-disabled", "modules-author"]);
  assert.deepEqual(MODULES_PAGE_SECTIONS.map((section) => en(section.label)), ["Catalog", "Disabled & quarantined", "Author a module"]);
  assert.deepEqual(EXTENSIONS_PAGE_SECTIONS.map((section) => section.id), ["extensions-catalogue", "extensions-install", "extensions-author"]);
  assert.deepEqual(DATA_PAGE_SECTIONS.map((section) => section.id), ["data-inputs", "data-install", "data-workbench-section", "data-adapters"]);
  for (const section of [...MODULES_PAGE_SECTIONS, ...EXTENSIONS_PAGE_SECTIONS, ...DATA_PAGE_SECTIONS]) assert.notEqual(zh(section.label), section.label, section.label);
});

test("the bounded data preview is a table of its sample, not JSON on the page", () => {
  assert.equal(previewSampleTable(null), null);
  assert.equal(previewSampleTable([1, 2]), null);
  const table = previewSampleTable([{ time: "2025-01-01T00:00Z", mw: 12.5 }, { time: "2025-01-01T00:30Z", mw: null, note: { a: 1 } }]);
  assert.deepEqual(table.columns, ["time", "mw", "note"]);
  assert.deepEqual(table.rows.map((row) => row.cells), [{ time: "2025-01-01T00:00Z", mw: "12.5", note: "—" }, { time: "2025-01-01T00:30Z", mw: "—", note: "{\"a\":1}" }]);
  assert.equal(previewCell(0), "0", "zero stays zero; only a missing value is a dash");
});

test("R4/R5/R6 confirmations and notices keep their English wording and have Chinese entries", () => {
  assert.equal(quarantineTitle(1, [{ kind: "module" }]), "1 external module quarantined");
  assert.equal(quarantineTitle(2, [{ kind: "extension" }]), "2 external extensions quarantined");
  assert.equal(quarantineTitle(2, [{ kind: "module" }, { kind: "extension" }]), "2 external modules and extensions quarantined");
  assert.equal(quarantineTitle(1, [{ kind: "module" }], zh), "1 个外部模块已隔离");
  assert.equal(quarantineIntro(2, zh), "VALUE 启动时未加载它们。需要它们的 Run 在修复或停用之前不能启动。");
  assert.equal(disableConfirmation("x", "module", zh), "停用 x？使用它的 Study 需要改选其他模块才能运行。");
  assert.match(disableConfirmation("obs", "extension", zh), /取消选择（保存为新修订）/);
  assert.equal(pendingRunsQuestion("2 Runs are queued.", "extensions"), "2 Runs are queued.\n\nChange the installed extensions anyway?");
  assert.equal(pendingRunsQuestion("", "modules", zh), "还有 Run 没有结束。\n\n仍要更改已安装的模块吗？");
  assert.equal(stoppedRunsNotice({ stopped_unstarted_runs: ["r1"] }), " 1 Run that had not started was stopped because the installed code changed (GF_RUN_EXECUTION_IDENTITY_CHANGED): r1. Resubmit it with the current code from the Runs page.");
  assert.equal(stoppedRunsNotice({ stopped_unstarted_runs: ["r1", "r2"] }), " 2 Runs that had not started were stopped because the installed code changed (GF_RUN_EXECUTION_IDENTITY_CHANGED): r1, r2. Resubmit them with the current code from the Runs page.");
  assert.match(stoppedRunsNotice({ stopped_unstarted_runs: ["r1", "r2"] }, zh), /2 个尚未开始的 Run 已停止（GF_RUN_EXECUTION_IDENTITY_CHANGED）：r1, r2/);
  assert.equal(removeConfirmation({ kind: "module", id: "m" }), "Remove module m? VALUE moves its installed files out of the scanned folders (to modules/disabled-manifests/removed/); they are not deleted. Install it again to use it.");
  assert.match(removeConfirmation({ kind: "extension", id: "e" }, zh), /^移除扩展 e？/);
  assert.match(enableFailureHint({ canEnable: true }, zh), /再次点“启用”/);
  assert.equal(moduleUsageNote("enabled", 2), "Used by 2 saved Studies; disable is blocked until those configurations are migrated.");
  assert.equal(moduleUsageNote("disabled", 1), "Used by 1 saved Study; it cannot run until this module is enabled again, or it selects another module.");
  assert.equal(installedModuleCard({ module_id: "m", enabled: true }, null, null, zh).stateText, "已启用");
  assert.deepEqual(derivationNotes({ source_migration: { revision_reason: "source-reidentify" } }), ["The source Study was first re-identified (installed local code was edited in place)."]);
  assert.match(derivationNotes({ source_migration: { revision_number: 4 } }, zh)[0], /重新标识为修订 4（仅代码变更，无需确认）/);
});

test("data validation, mapping and FX wording follow the interface language; codes stay untranslated", () => {
  const report = { valid: true, errors: [], warnings: [], layers: { chronology: { findings: [{ code: "GF_DATA_TIMESTAMPS", message: "gap" }] } }, profile_eligibility: { "doctoral-lineage-0.6.0a2": { eligible: false, blocking_codes: ["GF_DATA_TIMESTAMPS"] }, "value-corrected": { eligible: true } } };
  const layers = validationLayers(report, null, zh);
  assert.deepEqual(layers.map((layer) => layer.label), ["结构", "时间轴", "合理性"]);
  assert.equal(layers[1].pill.title, "1 项发现；阻断论文复现口径");
  assert.equal(validationLayers(report)[1].pill.title, "1 finding; blocks Doctoral reproduction");
  assert.deepEqual(methodologyUse(report, null, zh).map((use) => `${use.label}: ${use.pill.text}`), ["论文复现口径: 不可用 — 被 GF_DATA_TIMESTAMPS 阻断", "修正口径: 可用"]);
  assert.equal(inputsPresentSuffix("warnings"), "inputs present · validation passed with warnings");
  assert.equal(inputsPresentSuffix("passed", zh), "项输入已就位 · 校验通过");
  const errors = fxErrors({ currency: "EUR", eurPerGbp: "", fxBasis: "", priceYear: "" }, zh);
  assert.equal(errors.eurPerGbp, "GF_MAPPING_FX：EUR per GBP 必须是大于 0 的数，最多 4 位小数。");
  assert.equal(fxErrors({ currency: "EUR", eurPerGbp: "", fxBasis: "", priceYear: "1" }).priceYear, "GF_MAPPING_FX: the price year must be a whole number from 1990 to 2100.");
  assert.equal(fxCaption({ eur_per_gbp: 1.1, fx_basis: "fixed rate" }), "converted at 1.1 EUR/GBP (fixed rate)");
  assert.equal(fxCaption({ eur_per_gbp: 1.1, fx_basis: "fixed rate", price_year: 2022 }, zh), "按 1.1 EUR/GBP 换算（fixed rate, 2022）");
  assert.equal(timestampCoverageText({ coverage: { span_days: 365, data_years: [2025] } }, zh), "覆盖 365 天 · 数据年份 2025");
  assert.match(reviewExpiryText("2026-10-07T22:05:00Z", zh), /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}（本地时间）$/);
});

test("the pages read their wording from the dictionaries (no English or Chinese sentence left in the views)", async () => {
  const root = new URL("../../../", import.meta.url);
  for (const file of ["app/data/DataView.tsx", "app/modules/ModulesView.tsx", "app/extensions/ExtensionsView.tsx", "app/features/workspace/JourneyDataEditor.tsx", "app/features/data/CsvMappingEditor.tsx"]) {
    const source = await readFile(new URL(file, root), "utf8");
    assert.doesNotMatch(source.replace(/\/\/[^\n]*|\/\*[\s\S]*?\*\//g, ""), /[一-鿿]/, `${file}: Chinese text belongs in app/i18n/pages/*.zh.ts`);
    assert.match(source, /useT\(\)/, file);
  }
});
