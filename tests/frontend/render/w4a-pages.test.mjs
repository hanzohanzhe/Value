import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// P1 W4a (spec 6.1, 6.2) rendered offline in both interface languages.
const FIXTURES = "tests/frontend/helpers/w4a-fixtures.tsx";
const noop = () => {};
const workspace = {
  architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [],
  data_packs: [{ id: "my-pack", name: "My pack", manifest_sha256: "m".repeat(64) }],
  module_installations: [], extension_installations: [], projects: [], study_trash: [], runs: [], runtime: { python: "3.10", compatible: true },
};
const form = (extra = {}) => ({ name: "VALUE UK transition", purpose: "", start_year: 2025, end_year: 2034, modules: { psm: "value-bid-at-cost-psm" }, selected_extensions: [], extension_parameters: {}, maturity_acknowledgements: {}, market_configuration: {}, ...extra });
const resolution = { valid: true, errors: [], warnings: [], module_slots: [], compatible_modules: {}, system_domains: [], active_dataset_slots: [], data_readiness: { required: 2, available: 2, missing_roles: [] }, effective_extension_parameters: {}, maturity: { acknowledgement_contract: "x", acknowledgements_required: [] }, graph_sha256: "g".repeat(64) };
const composer = (locale, extra = {}) => renderTsx(FIXTURES, "ComposerIn", {
  locale, workspace, form: form(), selectedPackId: "my-pack", resolution, resolving: false, resolutionError: "",
  savedProjects: [], studyTrash: [], selectedProjectId: "", assumptions: null,
  onForm: noop, onPack: noop, onDomain: noop, onExtension: noop, onModule: noop, onExtensionParameter: noop, onAcknowledgement: noop,
  onSave: noop, onLoad: noop, onOpenRun: noop, onTrash: noop, onRestore: noop, onOpenTrashRuns: noop, onOpenData: noop,
  traceLevel: "summary", onTraceLevel: noop, methodology: { catalogue: null, profileId: null }, ...extra,
});

test("F4-02: model years are NumberFields (text boxes with bounds), never number inputs that turn empty into 0", async () => {
  const html = await composer("en");
  assert.match(html, /<label class="v-field__label" for="([^"]+)">First model year<span class="v-field__required" aria-hidden="true"> \*<\/span><\/label><span class="v-number"><input id="\1" class="v-input v-number__input" type="text" inputMode="decimal" autoComplete="off" required="" value="2025"/);
  assert.match(html, />Final model year</);
  assert.doesNotMatch(html, /type="number"[^>]*value="2025"/);
  const reversed = textOf(await composer("en", { form: form({ start_year: 2030, end_year: 2026 }) }));
  assert.match(reversed, /The final model year must not be before the first model year\./);
});

test("F4-03: a new Study's name that maps to a saved ID is flagged while typed and blocks saving; saving shows progress", async () => {
  const savedProjects = [{ id: "value-uk-transition", name: "VALUE UK transition", data_pack_id: "my-pack", start_year: 2025, end_year: 2026, modules: {}, updated_at: "" }];
  const html = await composer("en", { savedProjects });
  assert.match(html, /<input aria-invalid="true" aria-describedby="study-name-clash" value="VALUE UK transition"\/>/);
  assert.match(textOf(html), /A saved Study already has the ID value-uk-transition, which this name maps to; saving would be refused\. Use another name, for example “VALUE UK transition 2”/);
  const review = await composer("en", { savedProjects, initialStep: 5 });
  assert.match(review, /<p class="study-save-blocked" role="alert">This name maps to an ID that is already used\./);
  // P1-polish R-8: the disabled button names its reason in its title (the alert above says it once).
  assert.match(review, /<button type="button" class="primary full" disabled="" title="This name maps to an ID that is already used\.[^"]*">Save this exact Study revision<\/button>/);
  assert.doesNotMatch(review, /study-save-reason/);
  // Editing a saved Study is not a new name: no clash.
  assert.doesNotMatch(await composer("en", { savedProjects, editingStudyName: "VALUE UK transition", newStudy: false }), /study-name-clash/);
  const saving = await composer("en", { initialStep: 5, saving: true });
  assert.match(saving, /<button type="button" class="primary full" disabled="" aria-busy="true">Saving…<\/button>/);
  const ready = await composer("en", { initialStep: 5 });
  assert.match(ready, /<button type="button" class="primary full">Save this exact Study revision<\/button>/);
});

test("F4-04: Review names the data pack manifest hash and labels the graph hash as modules only", async () => {
  const text = textOf(await composer("en", { initialStep: 5 }));
  assert.match(text, /Model years 2025–2034/);
  assert.match(text, /Data pack manifest SHA-256 m{12}…/);
  assert.match(text, /Model graph SHA-256 \(modules and extensions only\) g{12}…/);
  assert.match(text, /The saved revision's SHA-256 covers the data pack, model years, parameters and model graph/);
});

test("the composer in Chinese: steps, years, methodology terms and buttons from the dictionary", async () => {
  const text = textOf(await composer("zh", { methodology: { catalogue: { default_profile_id: "c", profiles: [{ id: "c", label: "C", frozen: false, default: true }, { id: "d", label: "D", frozen: true, default: false }] }, profileId: "c" } }));
  for (const word of ["基本信息", "系统领域", "首个模型年", "最后模型年", "方法学口径", "修正口径（默认）", "论文复现口径", "上一步", "下一步", "第 1 步，共 5 步"]) assert.ok(text.includes(word), word);
  assert.doesNotMatch(text, /First model year|Continue|Study identity/);
});

test("F4-02: integer and float assumptions use NumberField with the registry's bounds", async () => {
  const definitions = [
    { id: "planning.delay_years", group: "Planning", value_type: "integer", default: 2, category: "scientific", visibility: "basic", scientific_effect: "Delay.", module_owner: "m", allowed_values: [], minimum: 0, maximum: 10 },
    { id: "expansion.vre_cap_fraction", group: "Expansion", value_type: "float", default: 0.5, category: "scientific", visibility: "basic", scientific_effect: "Cap.", module_owner: "m", allowed_values: [], minimum: 0, maximum: 1, unit: "share" },
  ];
  const html = await renderTsx(FIXTURES, "AdvancedIn", { locale: "en", definitions, values: {}, resolvedSources: {}, onChange: noop });
  assert.equal((html.match(/class="v-input v-number__input" type="text"/g) ?? []).length, 2);
  assert.doesNotMatch(html, /type="number"/);
  assert.match(textOf(html), /Unit: share · Default: 0\.5 · range 0 to 1/);
  assert.match(textOf(await renderTsx(FIXTURES, "AdvancedIn", { locale: "zh", definitions, values: {}, resolvedSources: {}, onChange: noop })), /高级假设.*默认：2 · 范围 0 至 10.*模块默认值/);
});

test("Home's four task paths in both languages; the path names stay as written", async () => {
  const english = textOf(await renderTsx(FIXTURES, "PathsIn", { locale: "en", activePath: "data", onSelect: noop }));
  for (const label of ["Reproduce from existing data", "Add your new data", "Edit a module", "Add a new function to VALUE", "Supported now"]) assert.ok(english.includes(label), label);
  const html = await renderTsx(FIXTURES, "PathsIn", { locale: "zh", activePath: "data", onSelect: noop });
  assert.match(html, /aria-label="Add your new data" aria-describedby="[^"]+" aria-pressed="true"/);
  assert.match(textOf(html), /当前支持/);
  assert.match(textOf(html), /导入并校验自己的数据，保留方法，比较变化。/);
});

const journeyProps = (locale, extra = {}) => ({
  locale, intent: "data", studies: [{ id: "base", name: "Baseline", revision_sha256: "r".repeat(64), revision_number: 1, data_pack_id: "base-pack", start_year: 2025, end_year: 2026, modules: { psm: "m" } }],
  packs: [{ id: "base-pack", name: "Base pack", complete: true, valid_required_count: 25, required_count: 25, manifest_sha256: "x" }],
  initialStudyId: "base", online: true, onCreated: noop, targetPackId: "", onTargetPackChange: noop, onPackCreated: async () => {}, onOpenData: noop, onOpenLearn: noop, onOpenRuns: noop, onReviewSource: noop, ...extra,
});

test("the research guide: English by default, the original Chinese wording in Chinese, and a step bar with the current step", async () => {
  const english = await renderTsx(FIXTURES, "JourneyIn", journeyProps("en"));
  assert.match(textOf(english), /Choose a baseline Study .* Prepare an independent BASE data pack .* Check the new Study/);
  assert.match(english, /<nav class="v-stepper" aria-label="Steps of the research path">/);
  assert.match(english, /<li class="v-stepper__step is-done">.*?Choose a baseline Study/);
  assert.match(english, /<li class="v-stepper__step is-current" aria-current="step">.*?Prepare an independent BASE data pack/);
  assert.match(english, /<h2 id="[^"]+" lang="en">Add your new data<\/h2>/);
  const chinese = textOf(await renderTsx(FIXTURES, "JourneyIn", journeyProps("zh")));
  for (const word of ["已有研究", "复制基线 BASE 包并加入我的文件", "已安装的数据包", "新 Study 名称", "创建换数据 Study", "查看沿用的模块"]) assert.ok(chinese.includes(word), word);
});

test("F4-07: the network lesson opens the newest Run of each case and names no platform", async () => {
  const savedStudies = [{ id: "value-101-network-copperplate", name: "C" }, { id: "value-101-network-constrained", name: "N" }];
  const runs = [
    { id: "value-101-network-constrained-20261001-090000-aaaa", project_id: "value-101-network-constrained", status: "failed" },
    { id: "value-101-network-constrained-20261005-090000-bbbb", project_id: "value-101-network-constrained", status: "completed" },
    { id: "value-101-network-copperplate-20261002-090000-cccc", project_id: "value-101-network-copperplate", status: "running" },
  ];
  const html = await renderTsx(FIXTURES, "NetworkIn", { locale: "en", baselineStudyId: "value-101-baseline", installed: false, savedStudies, runs, launching: false, onStudiesCreated: noop, onRunStudy: noop, onOpenRun: noop });
  const text = textOf(html);
  assert.match(text, /Open constrained · completed/, "the newest constrained Run, not the first listed");
  assert.match(text, /Open copperplate · running/);
  assert.match(text, /Open network results/);
  assert.match(text, /Run the VALUE installer again with the VALUE 101 teaching packs selected/);
  assert.doesNotMatch(text, /Windows/);
  const { value101NetworkPairPath } = await import("../../../app/features/learn/value101-api.mjs");
  assert.equal(value101NetworkPairPath("a b/c"), "tutorials/value-101/studies/a%20b%2Fc/network-pair");
});

test("P1-polish R-8: a save button disabled by the review names its reason in its title and on a line beside it", async () => {
  const blocked = { ...resolution, valid: false, errors: [{ code: "GF_EXPERIMENTAL_ACK_REQUIRED", message: "Acknowledge the experimental extension." }] };
  for (const [locale, reason] of [["en", "Tick the experimental acknowledgement above before saving."], ["zh", "请先勾选上方的实验性确认，再保存。"]]) {
    const html = await composer(locale, { initialStep: 5, resolution: blocked });
    assert.match(html, new RegExp(`disabled="" title="${reason}" aria-describedby="study-save-reason">`), locale);
    assert.match(html, new RegExp(`<p id="study-save-reason" class="study-save-reason" role="status">${reason}</p>`), locale);
  }
});

test("P1-polish R-17: the composer's methodology options; Chinese adds the English name and profile id in small type", async () => {
  const catalogue = { default_profile_id: "value-corrected", profiles: [
    { id: "value-corrected", label: "Corrected", frozen: false, default: true },
    { id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", frozen: true, default: false },
  ] };
  const methodology = { catalogue, profileId: "value-corrected" };
  const english = textOf(await composer("en", { methodology, onMethodology: noop }));
  assert.match(english, /Methodology Corrected methodology \(default\) Doctoral reproduction Locks thesis-era/);
  assert.doesNotMatch(english, /value-corrected ·|· value-corrected/);
  const chinese = await composer("zh", { methodology, onMethodology: noop });
  assert.match(chinese, /<b>修正口径（默认）<\/b><small class="methodology-profile-id" lang="en">Corrected methodology \(default\) · <code>value-corrected<\/code><\/small>/);
  assert.match(chinese, /<b>论文复现口径<\/b><small class="methodology-profile-id" lang="en">Doctoral reproduction · <code>doctoral-lineage-0\.6\.0a2<\/code><\/small>/);
});
