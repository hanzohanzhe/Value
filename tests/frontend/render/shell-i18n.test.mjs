import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// P1 spec 3, 4, 5.2 (W2): the sidebar and its footer in both languages, the
// service states with Retry, and the blocking contract-version notice.
const FIXTURES = "tests/frontend/helpers/locale-fixtures.tsx";
const service = (overrides = {}) => ({
  state: "online", failures: 0, health: { status: "ok", version: "0.7.0-alpha.1", frontend_contract_version: "value.expanded-frontend/v1", degraded_reasons: [] },
  runtime: { python: "3.10.14", compatible: true, selected_capability: "value-native" }, architectureVersion: "value.contracts/v2", ...overrides,
});
const rail = (locale, overrides = {}, view = "run") => renderTsx(FIXTURES, "RailIn", { locale, view, onNavigate() {}, onRetry() {}, service: service(overrides) });

test("English sidebar: groups, entries, current page, service, language switch and version", async () => {
  const html = await rail("en");
  const text = textOf(html);
  // P1 W3 (spec 5.2): Start, Work, Results; the pages of one Run are reached from Runs.
  for (const label of ["Start", "Work", "Results", "Home", "Research guide", "Learn", "Studies", "Data", "Modules", "Extensions", "Runs", "Compare", "Inspect"]) {
    assert.ok(text.includes(label), label);
  }
  for (const label of ["Market replay", "Network & water", "Guides", "Add data"]) assert.ok(!text.includes(label), `${label} is not a sidebar entry`);
  // W4c: the sidebar entry is the Run centre (/runs): launch and history; results are on each Run's page.
  assert.match(html, /<nav aria-label="Workspace">/);
  assert.match(html, /<a href="\/runs" aria-label="Runs: Launch and history" title="Runs" aria-current="page"/);
  for (const [href, label] of [["/", "Home"], ["/learn", "Learn"], ["/journey", "Research guide"], ["/studies", "Studies"], ["/data", "Data"], ["/modules", "Modules"], ["/extensions", "Extensions"], ["/compare", "Compare"], ["/inspect", "Inspect"]]) {
    assert.match(html, new RegExp(`<a href="${href.replace("/", "\\/")}" aria-label="${label}: [^"]+" title="${label}"`), href);
  }
  // A Run page marks Runs as the current entry.
  assert.match(await rail("en", {}, "marketReplay"), /aria-label="Runs: Launch and history" title="Runs" aria-current="page"/);
  // The drawer's menu button (below 900 px) names its action and the panel it controls.
  assert.match(html, /<button type="button" class="rail-toggle" aria-expanded="false" aria-controls="[^"]+" aria-label="Open navigation">/);
  assert.match(text, /Python 3\.10\.14 value-native ready/);
  assert.match(html, /role="group" aria-label="Language"/);
  assert.match(html, /aria-pressed="true"[^>]*>English<\/button>/);
  assert.match(html, /aria-pressed="false"[^>]*>中文<\/button>/);
  assert.match(text, /Contract v2 · VALUE 0\.7\.0-alpha\.1/);
  assert.doesNotMatch(html, />Retry</);
});

test("Chinese sidebar uses the dictionary; IDs, versions and codes stay as they are", async () => {
  const html = await rail("zh");
  const text = textOf(html);
  for (const label of ["开始", "工作", "结果", "首页", "研究路径", "学习", "数据", "模块", "扩展", "比较", "检查"]) assert.ok(text.includes(label), label);
  assert.match(html, /<nav aria-label="工作区">/);
  assert.match(html, /aria-label="Run：启动与历史" title="Run" aria-current="page"/);
  assert.match(html, /aria-label="打开导航"/);
  assert.match(text, /Python 3\.10\.14 value-native 已就绪/);
  assert.match(html, /aria-pressed="true"[^>]*>中文<\/button>/);
  assert.match(text, /契约 v2 · VALUE 0\.7\.0-alpha\.1/);
});

test("degraded after failures shows the retry delay and Retry; offline names the launcher; degraded health lists the codes", async () => {
  const failing = textOf(await rail("en", { state: "degraded", failures: 2 }));
  assert.match(failing, /● Backend degraded The last 2 requests failed; retrying in 8 s Retry/);
  const one = textOf(await rail("en", { state: "degraded", failures: 1 }));
  assert.match(one, /The last request failed; retrying in 4 s/);
  const offline = textOf(await rail("en", { state: "offline", failures: 3 }));
  assert.match(offline, /● Backend offline No answer after 3 attempts\. Start VALUE from its launcher, then retry Retry/);
  const reduced = await rail("en", { state: "degraded", failures: 0, health: { status: "degraded", degraded_reasons: [{ code: "GF_MODULE_QUARANTINED", count: 1 }] } });
  assert.match(textOf(reduced), /Running with reduced capability: GF_MODULE_QUARANTINED/);
  assert.doesNotMatch(reduced, />Retry</, "nothing to retry when the service answers");
  const zhOffline = textOf(await rail("zh", { state: "offline", failures: 3 }));
  assert.match(zhOffline, /● 后端离线 尝试 3 次均无应答。请从启动器启动 VALUE，然后重试 重试/);
  assert.match(textOf(await rail("en", { state: "loading", health: null })), /Connecting to model service… Checking the local API/);
});

test("contract mismatch is one blocking notice that says what to do, in the chosen language", async () => {
  const english = await renderTsx(FIXTURES, "ContractMismatchIn", { locale: "en", serviceContract: undefined });
  assert.match(english, /role="alert"/);
  assert.match(textOf(english), /The interface and the local service are different versions\. Restart VALUE\. Interface contract value\.expanded-frontend\/v1; local service contract not reported\. Reload the page/);
  const chinese = textOf(await renderTsx(FIXTURES, "ContractMismatchIn", { locale: "zh", serviceContract: "value.expanded-frontend/v2" }));
  assert.match(chinese, /界面与本地服务的版本不一致。请重启 VALUE。 界面契约 value\.expanded-frontend\/v1；本地服务契约 value\.expanded-frontend\/v2。/);
});

test("shared components take their default wording from the interface language", async () => {
  assert.match(await renderTsx(FIXTURES, "DialogIn", { locale: "en" }), /aria-label="Close"/);
  assert.match(await renderTsx(FIXTURES, "DialogIn", { locale: "zh" }), /aria-label="关闭"/);
});
