import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// P1 W5 (spec 3): the views translated in W5 read in English by default and in
// Chinese when chosen; missing values keep their state words, never 0.
const FIXTURES = "tests/frontend/helpers/w5-fixtures.tsx";

test("result views translated in W5: English by default, Chinese when chosen", async () => {
  const english = textOf(await renderTsx(FIXTURES, "W5ViewsIn", { locale: "en" }));
  for (const text of ["Bid-level replay was not recorded.", "Create a new Study revision with Full market replay", "Computational corridors", "Net position", "Boundary transfers and limits", "Forward limit (MW)", "11-20 of 30", "Open VALUE from its launcher"]) {
    assert.ok(english.includes(text), text);
  }
  const chinese = textOf(await renderTsx(FIXTURES, "W5ViewsIn", { locale: "zh" }));
  for (const text of ["没有记录逐笔报价回放。", "新建一个启用“完整市场回放”的 Study 修订", "计算走廊", "净头寸", "正向限值（MW）", "边界边际值（£/MWh）", "11-20，共 30", "请从启动器打开 VALUE"]) {
    assert.ok(chinese.includes(text), text);
  }
  for (const text of ["Bid-level replay", "Computational corridors", "Net position", "Previous", "Open VALUE from its launcher"]) {
    assert.ok(!chinese.includes(text), `untranslated: ${text}`);
  }
  // A missing limit stays "—" in both languages (missing is not zero, no unit on a dash).
  assert.doesNotMatch(chinese, /— ?MW\b/);
});

test("a known error code is explained before the code and the backend message, in the chosen language", async () => {
  const chinese = await renderTsx(FIXTURES, "RunErrorIn", { locale: "zh", code: "GF_WORKER_EXITED", error: "The model worker exited before recording a final state." });
  assert.match(chinese, /<p class="run-error-explanation">模型工作进程在记录最终状态之前停止了。[^<]*<\/p><p class="run-error-headline"><b>GF_WORKER_EXITED: <\/b>The model worker exited before recording a final state\.<\/p>/);
  const english = await renderTsx(FIXTURES, "RunErrorIn", { locale: "en", code: "GF_WORKER_EXITED", error: "The model worker exited before recording a final state." });
  assert.match(english, /<p class="run-error-explanation">The model worker stopped before it recorded a final state\./);
  // The English explanation is not repeated when the backend message already says it.
  const same = await renderTsx(FIXTURES, "RunErrorIn", { locale: "en", code: "GF_RUN_EXECUTION_IDENTITY_CHANGED", error: "The installed modules, extensions or VALUE code changed after this Run was queued, so it did not start. Resubmit it to run with the current code." });
  assert.doesNotMatch(same, /run-error-explanation/);
  const unknown = await renderTsx(FIXTURES, "RunErrorIn", { locale: "zh", code: "GF_X", error: "Stopped" });
  assert.doesNotMatch(unknown, /run-error-explanation/);
  assert.match(unknown, /<b>GF_X: <\/b>Stopped/);
});

test("the closed Read me has no status line in either language (R3M-7)", async () => {
  for (const locale of ["en", "zh"]) {
    const html = await renderTsx(FIXTURES, "ReadMeIn", { locale });
    assert.doesNotMatch(html, /role="status"/, locale);
    assert.doesNotMatch(html, /正在读取使用说明|Reading the Read me/, locale);
  }
  assert.match(await renderTsx(FIXTURES, "ReadMeIn", { locale: "zh" }), /aria-label="关闭 Read me">关闭<\/button>/);
  assert.match(await renderTsx(FIXTURES, "ReadMeIn", { locale: "en" }), /aria-label="Close Read me">Close<\/button>/);
});

test("the physical-system preview reads in Chinese and keeps its blocked-run warning (M2-N3)", async () => {
  const readiness = { schema_version: "x", status: "ready", ready: true, preview_periods: 48, requested_periods: 17520, bounded: true, sections: {}, issues: [] };
  const html = await renderTsx(FIXTURES, "DomainReadinessIn", { locale: "zh", readiness });
  assert.match(html, /已从请求的 17520 个时段中检查 48 个规范时段/);
  assert.match(html, /title="物理输入已就绪，但上方的就绪检查发现错误；修正之前 Run 不能启动。"/);
  assert.match(textOf(html), /输入就绪 · Run 受阻/);
});
