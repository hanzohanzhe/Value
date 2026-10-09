import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { en } from "../../../app/i18n/en.ts";
import { zh } from "../../../app/i18n/zh.ts";
import { errorExplanation, errorPrefix, translator } from "../../../app/i18n/index.ts";

// P1 W5 (spec 3): the dictionaries are complete, consistent and free of
// silently overridden keys; known error codes are explained in both languages.
const root = path.resolve(import.meta.dirname, "../../..");

async function files(directory, keep, found = []) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) await files(full, keep, found);
    else if (keep(full)) found.push(full);
  }
  return found;
}

/** Dictionary source files of one language (the spread parts and the main file). */
async function dictionarySources(language) {
  const directory = path.join(root, "app/i18n");
  const other = language === "en" ? "zh" : "en";
  return (await files(directory, (file) => file.endsWith(".ts")))
    .filter((file) => {
      const relative = path.relative(directory, file).split(path.sep).join("/");
      if (relative === `${language}.ts`) return true;
      if (relative.startsWith(`${language}/`)) return true;
      return relative.endsWith(`.${language}.ts`) && !relative.endsWith(`.${other}.ts`);
    });
}

for (const language of ["en", "zh"]) {
  test(`no ${language} key is defined twice across the dictionary files (a spread would hide one)`, async () => {
    const seen = new Map();
    const duplicates = [];
    for (const file of await dictionarySources(language)) {
      const source = await readFile(file, "utf8");
      for (const match of source.matchAll(/^\s*"([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9_]+)+)":/gm)) {
        const where = path.relative(root, file);
        if (seen.has(match[1])) duplicates.push(`${match[1]}: ${seen.get(match[1])} and ${where}`);
        else seen.set(match[1], where);
      }
    }
    assert.deepEqual(duplicates, []);
    assert.equal(seen.size, Object.keys(language === "en" ? en : zh).length, "every key is found in the sources");
  });
}

test("every Chinese message is translated: no English sentence is left in zh", () => {
  // Product names, codes and units stay in English (zh.ts, interface conventions);
  // a whole English sentence of three or more lower-case words does not.
  const sentence = /\b[A-Za-z]+ [a-z]+ [a-z]+ [a-z]+\b/;
  const allowed = new Set([
    // quoted ledger type names and command-line text shown as written
    "frozen.archive.p2b",
    // W4a: the four research paths keep their English names (lang="en"), as the Read me and tutorials do
    "home.path.reproduce.label", "home.path.data.label", "home.path.function.label",
  ]);
  const left = Object.entries(zh).filter(([key, value]) => !allowed.has(key) && sentence.test(value.replace(/\{[^{}]*\}/g, " ")));
  assert.deepEqual(left.map(([key, value]) => `${key}: ${value}`), []);
});

test("the Chinese wording follows the glossary and the interface conventions (W5 review)", () => {
  const rules = [
    [/doctoral 口径/, "论文复现口径"],
    [/未用 VRE|未使用的 VRE/, "未利用的 VRE"],
    [/压力事件|应力事件/, "stress 事件"],
    [/Check readiness|\breadiness\b/, "检查就绪情况 / 就绪情况"],
    [/在 Runs|到 Runs|Studies →|打开 Modules|Data 页|Modules 页|Market replay|在 Inspect/, "the Chinese page names"],
    [/拥塞/, "阻塞"],
    [/扣留/, "暂不发布"],
  ];
  const problems = [];
  for (const [key, value] of Object.entries(zh)) {
    for (const [pattern, wanted] of rules) if (pattern.test(value)) problems.push(`${key}: "${value}" (use ${wanted})`);
  }
  assert.deepEqual(problems, []);
});

test("the zh header lists the glossary it follows, with the W5 interface conventions", async () => {
  const source = await readFile(path.join(root, "app/i18n/zh.ts"), "utf8");
  for (const term of ["修正口径", "论文复现口径", "口径受控修正", "stress 事件", "未利用的 VRE", "缺电量（记账）", "边界边际值", "阻塞", "就绪情况", "暂不发布", "METHODOLOGY_EDITOR_HANDOFF.md"]) {
    assert.ok(source.includes(term), term);
  }
});

test("every explained error code is a code the backend or the interface really uses", async () => {
  const sources = (await Promise.all([
    ...(await files(path.join(root, "backend"), (file) => file.endsWith(".py"))),
    ...(await files(path.join(root, "gridform_core"), (file) => file.endsWith(".py"))),
    ...(await files(path.join(root, "app/lib"), (file) => file.endsWith(".ts"))),
  ].map((file) => readFile(file, "utf8")))).join("\n");
  const codes = Object.keys(en).filter((key) => key.startsWith("errors.")).map((key) => key.slice("errors.".length));
  assert.ok(codes.length >= 40, `${codes.length} explained codes`);
  for (const code of codes) assert.match(code, /^GF_[A-Z0-9_]+$/);
  assert.deepEqual(codes.filter((code) => !sources.includes(`"${code}"`)), []);
});

test("a known code is explained before the code and the backend message; an unknown code is shown as sent", () => {
  const tEn = translator("en");
  const tZh = translator("zh");
  assert.equal(errorExplanation("zh", "GF_WORKER_EXITED"), zh["errors.GF_WORKER_EXITED"]);
  assert.equal(errorExplanation("en", "GF_NOT_A_CODE"), null);
  assert.equal(errorExplanation("zh", ""), null);
  assert.equal(errorPrefix(tZh, "GF_MODULE_IN_USE"), `${zh["errors.GF_MODULE_IN_USE"]} GF_MODULE_IN_USE: `);
  assert.equal(errorPrefix(tEn, "GF_UNKNOWN_THING"), "GF_UNKNOWN_THING: ");
  assert.equal(errorPrefix(tEn, null), "");
  // The English explanation is not repeated when the backend already says it.
  assert.equal(errorPrefix(tEn, "GF_RUN_EXECUTION_IDENTITY_CHANGED", en["errors.GF_RUN_EXECUTION_IDENTITY_CHANGED"]), "GF_RUN_EXECUTION_IDENTITY_CHANGED: ");
  assert.match(errorPrefix(tZh, "GF_RUN_EXECUTION_IDENTITY_CHANGED", en["errors.GF_RUN_EXECUTION_IDENTITY_CHANGED"]), /^此 Run 排队之后/);
});

// Pure view code (state words, labels, coverage, Run notices) reads the active
// interface language that LocaleProvider sets (P1 W5).
test("pure view code follows the active interface language and keeps its English text", async () => {
  const { setActiveLocale, getActiveLocale } = await import("../../../app/i18n/index.ts");
  const { VALUE_STATES, valueStateText } = await import("../../../app/features/shared/valueStates.ts");
  const { RUN_SCOPE_LABELS, runScopeOptionLabel } = await import("../../../app/features/workspace/runScope.ts");
  const { statusLabel, STAGE_LABELS } = await import("../../../app/features/shared/labels.ts");
  const { coveragePill } = await import("../../../app/features/shared/coverageView.ts");
  const { runNotices, NOTICE_ACTION_LABELS, GATE_TEXT } = await import("../../../app/features/workspace/runValidation.ts");
  const { formatPrice } = await import("../../../app/features/shared/format.ts");
  const { statusWord } = await import("../../../app/features/shared/labels.ts");
  assert.equal(getActiveLocale(), "en");
  // The English messages are the English state words.
  for (const [key, state] of Object.entries(VALUE_STATES)) assert.equal(en[`state.${key}`], state.text, key);
  const stress = { stress: { stress_periods: 3, shortfall_mwh: 1200 } };
  const partial = { annual_status: "partial", reason_code: "run_failed_before_full_coverage", coverage_fraction: 0.5, coverage_percent: 50 };
  assert.equal(valueStateText("not_recorded"), "Not recorded");
  assert.equal(RUN_SCOPE_LABELS.two_year, "Two full model years");
  assert.equal(runNotices(stress)[0].title, "Supply fell short of demand in 3 periods");
  try {
    setActiveLocale("zh");
    assert.equal(valueStateText("not_recorded"), "未记录");
    assert.equal(valueStateText("partial_year", 12.34), "不完整年份 · 12.3%");
    assert.equal(RUN_SCOPE_LABELS.two_year, "两个完整模型年");
    assert.ok(Object.hasOwn(RUN_SCOPE_LABELS, "smoke"));
    assert.equal(runScopeOptionLabel("value_101_day", { selected_extensions: ["x"] }), "一天市场课程（扩展不运行）");
    assert.equal(statusLabel("passed"), "通过");
    assert.equal(statusLabel(null), "未评估");
    assert.equal(STAGE_LABELS.commissioned, "已投运");
    assert.deepEqual(coveragePill(partial), { tone: "caution", text: "已停止 · 50%", title: zh["coverage.reason.run_failed_before_full_coverage"] });
    const notice = runNotices(stress)[0];
    assert.equal(notice.title, "有 3 个时段供给低于需求");
    assert.match(notice.body, /^缺口合计 1\.2 GWh。这些是 stress 事件/);
    assert.equal(NOTICE_ACTION_LABELS.show_stress_events, "显示 stress 事件");
    assert.equal(GATE_TEXT.storage_invariants.name, "储能限值");
    assert.equal(formatPrice(42, "average_period_cost").label, "时段平均成本（£/MWh 需求）");
    assert.equal(statusWord("completed"), "已完成");
    assert.equal(statusWord("not_evaluated"), "未评估");
    assert.equal(statusWord("some_new_state"), "Some new state");
  } finally {
    setActiveLocale("en");
  }
  assert.equal(valueStateText("not_recorded"), "Not recorded");
  assert.equal(NOTICE_ACTION_LABELS.show_stress_events, "Show stress events");
  // P1-polish R-16 (ruling on D-W5-3): English shows the state word too; the page puts the code in a title.
  assert.equal(statusWord("not_evaluated"), "Not evaluated");
  assert.equal(statusWord("completed"), "Completed");
});
