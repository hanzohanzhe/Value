// Interface language for the VALUE frontend (P1 spec 3, A30).
//
//   * English by default; Chinese when the reader chooses it in the sidebar.
//     The choice is the cookie `value_locale`; the browser language is never
//     used, so screenshots and tutorials match.
//   * Messages live in en.ts and zh.ts with identical keys (tested).
//   * `{name}` inserts a value; `{count, plural, one {# Run} other {# Runs}}`
//     chooses a form by Intl.PluralRules (`=0 {…}` matches an exact number;
//     `#` is the number).
//   * Not translated: data values, IDs, hashes, file and module names,
//     technical codes and error codes.  Backend error messages are shown as
//     sent, after a translated explanation of their error code when one exists.
//
// Pure module: no React (LocaleProvider.tsx holds the context and hooks).
import { en, type MessageKey } from "./en.ts";
import { zh } from "./zh.ts";

export type { MessageKey } from "./en.ts";

export const LOCALES = ["en", "zh"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "value_locale";

export const DICTIONARIES: Record<Locale, Record<MessageKey, string>> = { en, zh };

/** A cookie value (or anything else) as a supported locale; English unless it is clearly Chinese. */
export function parseLocale(value: unknown): Locale {
  if (typeof value !== "string") return DEFAULT_LOCALE;
  const normal = value.trim().toLowerCase();
  return normal === "zh" || normal.startsWith("zh-") ? "zh" : DEFAULT_LOCALE;
}

/** The `<html lang>` value (spec 3). */
export function htmlLang(locale: Locale): string {
  return locale === "zh" ? "zh-Hans" : "en-GB";
}

/** The BCP 47 tag used for Intl number and date formatting. */
export function intlLocale(locale: Locale): string {
  return locale === "zh" ? "zh-CN" : "en-GB";
}

/** The Set-Cookie / document.cookie text that stores a choice for a year. */
export function localeCookie(locale: Locale): string {
  return `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`;
}

/** The locale stored in a Cookie header or document.cookie string. */
export function localeFromCookieHeader(header: string | null | undefined): Locale {
  if (!header) return DEFAULT_LOCALE;
  for (const part of header.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === LOCALE_COOKIE) return parseLocale(decodeURIComponent(rest.join("=")));
  }
  return DEFAULT_LOCALE;
}

export type MessageValues = Record<string, string | number | null | undefined>;

const pluralRules = new Map<string, Intl.PluralRules>();

function pluralCategory(locale: Locale, count: number): string {
  const tag = intlLocale(locale);
  let rules = pluralRules.get(tag);
  if (!rules) { rules = new Intl.PluralRules(tag); pluralRules.set(tag, rules); }
  return rules.select(count);
}

/** Index of the brace that closes the one at `open`, or -1. */
function closingBrace(text: string, open: number): number {
  let depth = 0;
  for (let index = open; index < text.length; index += 1) {
    if (text[index] === "{") depth += 1;
    else if (text[index] === "}") { depth -= 1; if (depth === 0) return index; }
  }
  return -1;
}

function pluralForm(locale: Locale, body: string, count: number): string {
  // body: "one {…} other {…}" (also "=0 {…}").
  const forms = new Map<string, string>();
  let index = 0;
  while (index < body.length) {
    const open = body.indexOf("{", index);
    if (open < 0) break;
    const selector = body.slice(index, open).trim();
    const close = closingBrace(body, open);
    if (close < 0) break;
    forms.set(selector, body.slice(open + 1, close));
    index = close + 1;
  }
  const chosen = forms.get(`=${count}`) ?? forms.get(pluralCategory(locale, count)) ?? forms.get("other") ?? "";
  return chosen.replaceAll("#", String(count));
}

/** Fill `{name}` and plural blocks of one message. */
export function formatMessage(locale: Locale, template: string, values: MessageValues = {}): string {
  let result = "";
  let index = 0;
  while (index < template.length) {
    const open = template.indexOf("{", index);
    if (open < 0) { result += template.slice(index); break; }
    result += template.slice(index, open);
    const close = closingBrace(template, open);
    if (close < 0) { result += template.slice(open); break; }
    const inner = template.slice(open + 1, close);
    const plural = /^\s*(\w+)\s*,\s*plural\s*,([\s\S]*)$/.exec(inner);
    if (plural) {
      const count = Number(values[plural[1]]);
      result += formatMessage(locale, pluralForm(locale, plural[2], Number.isFinite(count) ? count : 0), values);
    } else {
      const name = inner.trim();
      const value = values[name];
      result += value === undefined || value === null ? `{${name}}` : String(value);
    }
    index = close + 1;
  }
  return result;
}

/** One message in `locale`; English when the locale lacks it; the key itself when no dictionary has it. */
export function translate(locale: Locale, key: MessageKey | string, values?: MessageValues): string {
  const dictionary = DICTIONARIES[locale] as Record<string, string>;
  const template = dictionary[key] ?? (en as Record<string, string>)[key];
  return template === undefined ? key : formatMessage(locale, template, values);
}

export type Translate = (key: MessageKey, values?: MessageValues) => string;

// The interface language of pure view code (P1 W5). Status words, coverage
// pills and Run notices are computed by plain functions outside React; they
// read the language LocaleProvider set before its children render (as
// format.ts reads the number locale). English until a provider sets it.
let activeLocale: Locale = DEFAULT_LOCALE;

/** Set by LocaleProvider on every render; tests may set it directly. */
export function setActiveLocale(locale: Locale): void {
  activeLocale = locale;
}

export function getActiveLocale(): Locale {
  return activeLocale;
}

/** One message in the active interface language (for pure view code). */
export function tr(key: MessageKey, values?: MessageValues): string {
  return translate(activeLocale, key, values);
}

/**
 * A read-only code → label table whose values follow the active language:
 * `TABLE[code]`, `Object.hasOwn`, `Object.keys` and `Object.entries` work as on
 * a plain object, and each read is translated when it happens.
 */
export function localizedTable<K extends string>(keys: Record<K, MessageKey>): Readonly<Record<K, string>> {
  const table = {} as Record<K, string>;
  for (const [name, key] of Object.entries(keys) as [K, MessageKey][]) {
    Object.defineProperty(table, name, { enumerable: true, get: () => tr(key) });
  }
  return Object.freeze(table);
}

/** A translate function bound to one locale (for pure view code and tests). */
export function translator(locale: Locale): Translate {
  return (key, values) => translate(locale, key, values);
}

/** The translated explanation of a known error code, or null (spec 3: the code itself is never translated). */
export function errorExplanation(locale: Locale, code: string | null | undefined): string | null {
  if (!code) return null;
  const key = `errors.${code}`;
  return key in en ? translate(locale, key) : null;
}

/**
 * The prefix of a refused request's notice (spec 3): the translated explanation
 * of a known error code, then the code itself, as in "Explanation CODE: " - the
 * backend's message follows as sent. "" without a code; "CODE: " for a code the
 * dictionaries do not explain.
 */
export function errorPrefix(t: Translate, code: string | null | undefined, message = ""): string {
  if (!code) return "";
  const key = `errors.${code}`;
  if (!(key in en)) return `${code}: `;
  const explanation = t(key as MessageKey);
  // Not repeated when the backend's own message already says the same (English).
  return message.includes(explanation) ? `${code}: ` : `${explanation} ${code}: `;
}
