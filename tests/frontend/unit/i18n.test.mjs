import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { en } from "../../../app/i18n/en.ts";
import { zh } from "../../../app/i18n/zh.ts";
import {
  DEFAULT_LOCALE, LOCALE_COOKIE, errorExplanation, formatMessage, htmlLang, intlLocale, localeCookie, localeFromCookieHeader, parseLocale, translate,
} from "../../../app/i18n/index.ts";
import { NAV_GROUPS, NAV_VIEWS, RUN_PAGE_VIEWS } from "../../../app/features/shared/navigation.ts";
import { UI_STRINGS } from "../../../app/ui/strings.ts";
import { baseInputsPill } from "../../../app/features/shared/headerPill.ts";
import { formatModelInstant, formatNumber, formatSystemTime, getFormatLocale, setFormatLocale } from "../../../app/features/shared/format.ts";

// P1 spec 3 (W2): dictionaries, language choice and locale-aware formatting.
const root = path.resolve(import.meta.dirname, "../../..");

/** {name} placeholders and {name, plural, …} selectors of a message. */
function placeholders(message) {
  const names = new Set();
  for (const match of message.matchAll(/\{(\w+)\}/g)) names.add(match[1]);
  for (const match of message.matchAll(/\{(\w+),\s*plural\s*,/g)) names.add(match[1]);
  return [...names].sort();
}

test("en and zh have exactly the same keys", () => {
  const english = Object.keys(en).sort();
  const chinese = Object.keys(zh).sort();
  assert.deepEqual(chinese.filter((key) => !(key in en)), [], "keys only in zh");
  assert.deepEqual(english.filter((key) => !(key in zh)), [], "keys missing from zh");
});

test("every message is non-empty text and both languages use the same placeholders", () => {
  for (const [key, message] of Object.entries(en)) {
    assert.equal(typeof message, "string", key);
    assert.ok(message.trim(), `en ${key} is empty`);
    assert.ok(zh[key].trim(), `zh ${key} is empty`);
    assert.deepEqual(placeholders(zh[key]), placeholders(message), `placeholders of ${key}`);
  }
});

test("keys are namespaced (feature.name)", () => {
  const bad = Object.keys(en).filter((key) => !/^[a-z][A-Za-z0-9]*(\.[A-Za-z0-9_]+)+$/.test(key));
  assert.deepEqual(bad, []);
});

test("the Chinese dictionary lists the methodology terms it follows", async () => {
  const source = await readFile(path.join(root, "app/i18n/zh.ts"), "utf8");
  for (const term of ["修正口径", "论文复现口径", "口径受控修正", "stress", "未利用的 VRE", "METHODOLOGY_EDITOR_HANDOFF.md"]) assert.ok(source.includes(term), term);
});

test("translate fills values, chooses plural forms and falls back to English, then to the key", () => {
  assert.equal(translate("en", "shell.contract", { version: "v2" }), "Contract v2");
  assert.equal(translate("en", "header.backgroundRuns", { count: 1 }), "● 1 Run running in background");
  assert.equal(translate("en", "header.backgroundRuns", { count: 3 }), "● 3 Runs running in background");
  assert.equal(translate("zh", "header.backgroundRuns", { count: 3 }), "● 3 个 Run 正在后台运行");
  assert.equal(translate("en", "service.degraded.failed", { count: 1, seconds: 4 }), "The last request failed; retrying in 4 s");
  assert.equal(translate("en", "service.degraded.failed", { count: 2, seconds: 8 }), "The last 2 requests failed; retrying in 8 s");
  assert.equal(translate("zh", "service.degraded.failed", { count: 2, seconds: 8 }), "最近 2 次请求失败；8 秒后重试");
  assert.equal(translate("zh", "no.such.key"), "no.such.key");
  assert.equal(formatMessage("en", "{n, plural, =0 {none} one {# item} other {# items}}", { n: 0 }), "none");
  assert.equal(formatMessage("en", "Hello {name}", {}), "Hello {name}", "a missing value stays visible, never blank");
  assert.equal(formatMessage("en", "{n, plural, other {# of {total}}}", { n: 2, total: 5 }), "2 of 5");
});

test("language choice: English by default, Chinese only when chosen; html lang and cookie", () => {
  assert.equal(DEFAULT_LOCALE, "en");
  assert.equal(LOCALE_COOKIE, "value_locale");
  assert.equal(parseLocale(undefined), "en");
  assert.equal(parseLocale("fr"), "en");
  assert.equal(parseLocale("zh"), "zh");
  assert.equal(parseLocale("zh-Hans"), "zh");
  assert.equal(htmlLang("en"), "en-GB");
  assert.equal(htmlLang("zh"), "zh-Hans");
  assert.equal(intlLocale("zh"), "zh-CN");
  assert.equal(localeCookie("zh"), "value_locale=zh; Path=/; Max-Age=31536000; SameSite=Lax");
  assert.equal(localeFromCookieHeader("a=1; value_locale=zh; b=2"), "zh");
  assert.equal(localeFromCookieHeader("a=1"), "en");
  assert.equal(localeFromCookieHeader(null), "en");
});

test("error codes are explained in the interface language; the code itself is not translated", () => {
  assert.match(errorExplanation("zh", "GF_REQUEST_TIMEOUT"), /本地服务/);
  assert.match(errorExplanation("en", "GF_REQUEST_TIMEOUT"), /did not answer in time/);
  assert.equal(errorExplanation("en", "GF_UNKNOWN_CODE"), null);
  assert.equal(errorExplanation("en", null), null);
});

test("every sidebar entry and group has both dictionary entries", () => {
  for (const item of NAV_VIEWS) {
    assert.ok(item.label in en && item.note in en, item.id);
  }
  for (const group of NAV_GROUPS) assert.ok(group.label in en, group.label);
  // P1 W3 (spec 5.2): three groups; the pages of one Run are reached from Runs
  // (the Run section bar), so every page is either in exactly one group or a Run page.
  // W4c: Runs in the sidebar is the Run centre (runCentre); "run" (annual results) is a Run page.
  const grouped = NAV_GROUPS.flatMap((group) => group.ids);
  assert.equal(new Set(grouped).size, grouped.length, "no page is in two groups");
  assert.deepEqual(NAV_GROUPS.map((group) => group.label), ["nav.group.start", "nav.group.work", "nav.group.results"]);
  for (const item of NAV_VIEWS) assert.ok(grouped.includes(item.id) !== RUN_PAGE_VIEWS.includes(item.id), `${item.id}: in a group or a Run page, not both`);
  // The English labels the release documents and older tests name.
  for (const label of ["Market replay", "VRE & curtailment", "Network & redispatch", "Research guide", "Inspect"]) assert.ok(Object.values(en).includes(label), label);
});

test("the shared components' wording (app/ui/strings.ts) is mirrored by the ui.* keys", () => {
  for (const [key, value] of Object.entries(UI_STRINGS)) assert.equal(en[`ui.${key}`], value, key);
  assert.deepEqual(Object.keys(en).filter((key) => key.startsWith("ui.")).map((key) => key.slice(3)).sort(), Object.keys(UI_STRINGS).sort());
});

test("the header pill reads from the dictionaries (English by default)", () => {
  const pack = { complete: false, valid_required_count: 24, required_count: 25 };
  assert.deepEqual(baseInputsPill(true, pack), { text: "24 of 25 base inputs ready", tone: "warn" });
  assert.deepEqual(baseInputsPill(true, pack, (key, values) => translate("zh", key, values)), { text: "基础输入就绪 24/25", tone: "warn" });
});

test("numbers follow the interface language; model time stays UTC; system time is the reader's", (t) => {
  t.after(() => setFormatLocale("en-GB"));
  assert.equal(getFormatLocale(), "en-GB");
  assert.equal(formatNumber(1234567.891, 2), "1,234,567.89");
  setFormatLocale("zh-CN");
  assert.equal(formatNumber(1234567.891, 2), "1,234,567.89", "zh-CN groups digits like en-GB");
  assert.equal(formatNumber(null), null, "missing stays missing in every language");
  assert.equal(formatModelInstant("2025-05-17T13:30:00Z"), "2025-05-17 13:30 UTC");
  assert.equal(formatModelInstant(Date.UTC(2025, 0, 1, 0, 0)), "2025-01-01 00:00 UTC");
  assert.equal(formatModelInstant("not a time"), null);
  assert.match(formatSystemTime("2026-10-08T09:15:00Z"), /2026/);
  assert.equal(formatSystemTime(null), null);
});

async function sources(directory, found = []) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) await sources(full, found);
    else if (/\.(tsx?|mjs)$/.test(entry.name)) found.push(full);
  }
  return found;
}

test("every t(\"…\") key used in app/ exists in the dictionaries", async () => {
  const missing = [];
  for (const file of await sources(path.join(root, "app"))) {
    const text = await readFile(file, "utf8");
    for (const match of text.matchAll(/(?<![\w.])t\(\s*"([^"]+)"/g)) if (!(match[1] in en)) missing.push(`${path.relative(root, file)}: ${match[1]}`);
  }
  assert.deepEqual(missing, []);
});

test("the root layout reads the value_locale cookie on the server and sets <html lang> (no browser-language switch)", async () => {
  const layout = await readFile(path.join(root, "app/layout.tsx"), "utf8");
  assert.match(layout, /cookies\(\)\)\.get\(LOCALE_COOKIE\)/);
  assert.match(layout, /<html lang=\{htmlLang\(locale\)\}>/);
  assert.match(layout, /<LocaleProvider initialLocale=\{locale\}>/);
  const app = (await Promise.all((await sources(path.join(root, "app"))).map((file) => readFile(file, "utf8")))).join("\n");
  assert.doesNotMatch(app, /navigator\.languages?\b|accept-language/i);
});
