import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { I18N_ALLOWLIST } from "../../../app/i18n/allowlist.ts";

// P1 spec 3: no hard-coded user-visible string in JSX text or in title /
// aria-label / placeholder / alt attributes; units and symbols in
// app/i18n/allowlist.ts are allowed.
//
// W5: strict for every TSX file under app/ (W2 to W4 ran it strict only for
// the files already translated and reported the rest).
const root = path.resolve(import.meta.dirname, "../../..");

async function tsxFiles(directory, found = []) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) await tsxFiles(full, found);
    else if (entry.name.endsWith(".tsx")) found.push(full);
  }
  return found;
}

const allow = [...I18N_ALLOWLIST].sort((a, b) => b.length - a.length);
const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const allowPattern = new RegExp(allow.map((item) => /^\w/.test(item) ? `\\b${escape(item)}\\b` : escape(item)).join("|"), "g");

/** True when text still has words after removing allow-listed names, units and symbols. */
export function isWording(text) {
  const rest = text.replace(/&[a-z]+;|&#\d+;/g, " ").replace(allowPattern, " ").replace(/\d+/g, " ");
  return /[A-Za-z]{2,}|[一-鿿]/.test(rest);
}

/** Comments removed, line structure kept. */
function stripComments(source) {
  return source
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, (match) => match.replace(/[^\n]/g, " "))
    .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/[^\n]*/g, (match, lead) => lead + " ".repeat(match.length - lead.length));
}

// Code, not wording: operators and keywords; the middle of a multi-line
// ternary (": a ?", "? b"); TypeScript generics read between "<" and ">"
// (": Pick", "export type X = Omit"); a comparison read as a tag
// ("item.period_count <= 1": a snake_case property, "??" or a template).
const CODE = /=>|&&|\|\||;|\breturn\b|\bconst\b|\btypeof\b|===|!==|\(|\)|^[:?]|\?$|\bexport (?:type|const|function|default)\b|\?\?|`|\b[a-z]\w*\.[a-z]+_[a-z_]+\b/;

/** Hard-coded strings of one TSX source: [{ line, kind, text }]. */
export function scanSource(source) {
  const clean = stripComments(source);
  const lineOf = (index) => clean.slice(0, index).split("\n").length;
  const hits = [];
  for (const match of clean.matchAll(/>([^<>{}]+)(?=<|\{)|\}([^<>{}]+)(?=<)/g)) {
    const text = (match[1] ?? match[2]).replace(/\s+/g, " ").trim();
    if (!text || CODE.test(text) || !isWording(text)) continue;
    // The content of <code> is a technical code (a folder name, a flag), never translated (spec 3).
    if (match[1] !== undefined && /<code(?:\s[^<>]*)?>$/.test(clean.slice(0, match.index + 1))) continue;
    hits.push({ line: lineOf(match.index), kind: "text", text });
  }
  for (const match of clean.matchAll(/\b(title|aria-label|placeholder|alt)=(?:"([^"]*)"|\{"([^"]*)"\}|\{`([^`]*)`\})/g)) {
    const text = (match[2] ?? match[3] ?? match[4]).replace(/\$\{[^}]*\}/g, " ").trim();
    if (!text || !isWording(text)) continue;
    hits.push({ line: lineOf(match.index), kind: match[1], text });
  }
  return hits;
}

test("the scanner finds JSX text and attribute wording, and ignores units, symbols and expressions", () => {
  const sample = [
    "<p>Hello world</p>",
    '<button title="Open the Run" aria-label={t("x")}>{t("y")}</button>',
    "<span>{value} MWh</span>",
    "<i>·</i><b>{name}</b>",
    "{/* <b>Commented out</b> */}",
    "<em>{count} periods</em>",
    '<input placeholder={`Search ${kind}`} />',
    "<p>中文界面文字</p>",
  ].join("\n");
  const hits = scanSource(sample).map(({ kind, text }) => `${kind}:${text}`);
  assert.deepEqual(hits, ["text:Hello world", "text:periods", "text:中文界面文字", "title:Open the Run", "placeholder:Search"]);
});

test("the scanner reads code as code: generics, multi-line ternaries, comparisons and <code> contents (W5)", () => {
  const sample = [
    "type Props = FieldFrame & Omit<Input, \"value\">;",
    "export type IconButtonProps = Omit<ButtonProps, \"children\">;",
    "{items.length ? <List />",
    "  : !selected ? <Empty />",
    "  : <Rows />}",
    "const ok = rows.every((item) => item.period_count <= 1);",
    "<td>{row.id ?? `${row.a}`}</td>",
    "<p>Run <code>--acknowledge-code</code> once</p>",
  ].join("\n");
  const hits = scanSource(sample).map(({ kind, text }) => `${kind}:${text}`);
  // "Run" and "once" are still wording; the flag inside <code> is not.
  assert.deepEqual(hits, ["text:Run", "text:once"]);
});

test("no TSX file under app/ has a hard-coded interface string (strict, W5)", async () => {
  const files = await tsxFiles(path.join(root, "app"));
  assert.ok(files.length > 50, "the scan reads the app's TSX files");
  const hits = [];
  for (const file of files) {
    const relative = path.relative(root, file).split(path.sep).join("/");
    hits.push(...scanSource(await readFile(file, "utf8")).map((hit) => `${relative}:${hit.line} [${hit.kind}] ${hit.text.slice(0, 80)}`));
  }
  assert.deepEqual(hits, [], hits.join("\n"));
});
