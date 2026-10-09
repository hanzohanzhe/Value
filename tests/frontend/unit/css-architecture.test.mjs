import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

// P1 frontend overhaul spec 1 (W1): cascade layers, tokens only, type floor,
// spacing/radius scales, no !important. Every stylesheet under app/ is checked,
// so a renamed or new file can never escape the rules.
const root = path.resolve(import.meta.dirname, "../../..");
const LAYERS = "@layer reset, tokens, base, components, features, utilities;";

async function stylesheets(directory = path.join(root, "app")) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) found.push(...await stylesheets(full));
    else if (entry.name.endsWith(".css")) found.push(full);
  }
  return found.sort();
}

const rel = (file) => path.relative(root, file).split(path.sep).join("/");
const stripComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, " "));

/** Declarations as { prop, value, selector, line } (a small parser: enough for our flat files). */
function declarations(css) {
  const clean = stripComments(css);
  const out = [];
  const stack = [];
  let buffer = "";
  let line = 1;
  let startLine = 1;
  for (const char of clean) {
    if (char === "\n") line += 1;
    if (char === "{") { stack.push(buffer.trim()); buffer = ""; startLine = line; continue; }
    if (char === ";" || char === "}") {
      const text = buffer.trim();
      const colon = text.indexOf(":");
      if (colon > 0 && !text.startsWith("@")) out.push({ prop: text.slice(0, colon).trim(), value: text.slice(colon + 1).trim(), selector: stack[stack.length - 1] ?? "", line: startLine });
      buffer = "";
      if (char === "}") stack.pop();
      continue;
    }
    buffer += char;
  }
  return out;
}

function selectors(css) {
  const clean = stripComments(css);
  return [...clean.matchAll(/(?:^|[{};])\s*([^{};@][^{};]*)\{/g)].map((match) => match[1].trim()).filter((selector) => !/^(from|to|\d+%)$/.test(selector));
}

/** Split on a separator outside parentheses (commas in :is(), spaces in clamp()). */
function splitTop(text, separator) {
  const parts = [];
  let depth = 0;
  let current = "";
  for (const char of text) {
    if (char === "(") depth += 1;
    if (char === ")") depth -= 1;
    if (depth === 0 && separator.test(char)) { if (current.trim()) parts.push(current.trim()); current = ""; continue; }
    current += char;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

const files = await stylesheets();
const sources = new Map(await Promise.all(files.map(async (file) => [rel(file), await readFile(file, "utf8")])));

test("every stylesheet declares the layer order first and puts its rules in its own layer", () => {
  for (const [file, css] of sources) {
    const first = stripComments(css).trim().split("\n")[0].trim();
    assert.equal(first, LAYERS, `${file}: first statement must be the layer order`);
    if (file === "app/globals.css") continue;
    const expected = file.startsWith("app/ui/") ? "components"
      : file === "app/styles/reset.css" ? "reset"
      : file === "app/styles/base.css" ? "base"
      : file === "app/styles/utilities.css" ? "utilities"
      : "features";
    const blocks = [...stripComments(css).matchAll(/@layer\s+([a-z-]+)\s*\{/g)].map((match) => match[1]);
    assert.deepEqual(blocks, [expected], `${file}: rules belong in one @layer ${expected} block`);
  }
});

test("globals.css holds only the layer order and the tokens", () => {
  const css = stripComments(sources.get("app/globals.css"));
  for (const { prop, selector } of declarations(css)) {
    assert.ok(prop.startsWith("--"), `globals.css: ${selector} { ${prop} } is not a token`);
    assert.equal(selector, ":root");
  }
  for (const token of ["--ink", "--ink-muted", "--line", "--line-soft", "--paper", "--panel", "--navy", "--navy-soft", "--blue", "--blue-dark", "--blue-soft",
    "--red", "--red-soft", "--amber", "--amber-soft", "--teal", "--teal-soft",
    "--tech-wind", "--tech-solar", "--tech-unused-vre", "--tech-nuclear", "--tech-gas", "--tech-biomass", "--tech-hydro", "--tech-storage", "--tech-import", "--tech-shortfall",
    "--fs-2xs", "--fs-xs", "--fs-sm", "--fs-md", "--fs-lg", "--fs-xl", "--fs-2xl", "--fs-3xl",
    "--sp-1", "--sp-2", "--sp-3", "--sp-4", "--sp-5", "--sp-6", "--sp-7", "--sp-8", "--r-sm", "--r-md", "--r-lg", "--shadow-1", "--shadow-2",
    "--bp-sm", "--bp-md", "--bp-lg", "--bp-xl"]) {
    assert.match(css, new RegExp(`\\${token}:`), `token ${token} is defined`);
  }
  assert.match(css, /--ink-muted: #4f5869;/);
  assert.match(css, /--tech-unused-vre: #CC79A7;/);
});

test("no raw colour outside the tokens", () => {
  const hits = [];
  for (const [file, css] of sources) {
    if (file === "app/globals.css") continue;
    for (const { prop, value, selector, line } of declarations(css)) {
      if (/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/.test(value)) hits.push(`${file}:${line} ${selector} { ${prop}: ${value} }`);
    }
  }
  assert.deepEqual(hits, []);
});

test("no !important except in v-visually-hidden", () => {
  const hits = [];
  for (const [file, css] of sources) {
    for (const { prop, value, selector, line } of declarations(css)) {
      if (/!important/.test(value) && !(file === "app/styles/utilities.css" && /\.v-visually-hidden/.test(selector))) hits.push(`${file}:${line} ${selector} { ${prop} }`);
    }
  }
  assert.deepEqual(hits, []);
});

test("font sizes come from the type scale; 11px only for monospace", () => {
  const hits = [];
  for (const [file, css] of sources) {
    if (file === "app/globals.css") continue;
    for (const { prop, value, selector, line } of declarations(css)) {
      if (prop === "font-size" && !/^(var\(--fs-[a-z0-9]+\)|inherit|1em|100%)$/.test(value)) hits.push(`${file}:${line} ${selector} { font-size: ${value} }`);
      if (prop === "font" && !/^(inherit|(?:(?:normal|italic|\d00|bold)\s+)*var\(--fs-[a-z0-9]+\)(?:\/[\d.]+)?\s+var\(--font-(?:sans|mono)\))$/.test(value)) hits.push(`${file}:${line} ${selector} { font: ${value} }`);
      if (/var\(--fs-2xs\)/.test(value)) {
        const mono = prop === "font" ? /var\(--font-mono\)/.test(value) : /\b(code|kbd|samp|pre)\b|hash|-id\b|mono/.test(selector) || declarations(css).some((other) => other.selector === selector && /font-family|font$/.test(other.prop) && /--font-mono/.test(other.value));
        if (!mono) hits.push(`${file}:${line} ${selector}: 11px is for monospace IDs and hashes only`);
      }
    }
  }
  assert.deepEqual(hits, []);
});

test("spacing uses the 4-64px scale and radii the three steps", () => {
  const spacing = /^(margin|padding)(-(top|right|bottom|left|block|inline)(-(start|end))?)?$|^(gap|row-gap|column-gap)$/;
  const allowedSpace = /^(0|auto|1px|-1px|var\(--sp-[1-8]\)|calc\(-1 \* var\(--sp-[1-8]\)\)|clamp\(var\(--sp-[1-8]\), [\d.]+vw, var\(--sp-[1-8]\)\)|[\d.]+%)$/;
  const allowedRadius = /^(0|50%|inherit|var\(--r-(sm|md|lg|pill)\))$/;
  const hits = [];
  for (const [file, css] of sources) {
    if (file === "app/globals.css") continue;
    for (const { prop, value, selector, line } of declarations(css)) {
      if (/\.v-visually-hidden/.test(selector)) continue;
      if (spacing.test(prop)) {
        for (const part of splitTop(value, /\s/)) if (!allowedSpace.test(part)) hits.push(`${file}:${line} ${selector} { ${prop}: ${value} }`);
      }
      if (/^border(-(top|bottom)-(left|right))?-radius$/.test(prop)) {
        for (const part of value.split(/\s+/)) if (!allowedRadius.test(part)) hits.push(`${file}:${line} ${selector} { ${prop}: ${value} }`);
      }
    }
  }
  assert.deepEqual(hits, []);
});

test("component and feature rules start from a class, never a bare element", () => {
  const hits = [];
  for (const [file, css] of sources) {
    if (!file.startsWith("app/ui/") && !file.startsWith("app/features/") && file !== "app/styles/workbench.css") continue;
    for (const selector of selectors(css)) {
      for (const part of splitTop(selector, /,/)) {
        if (/^(@|from|to)/.test(part)) continue;
        if (!/^(\.|:root:lang\(|\[|#|[a-z][a-z0-9]*\.)/.test(part)) hits.push(`${file}: ${part}`);
      }
    }
  }
  assert.deepEqual(hits, []);
});

test("component class names carry the v- prefix", () => {
  const hits = [];
  for (const [file, css] of sources) {
    if (!file.startsWith("app/ui/")) continue;
    for (const selector of selectors(css)) {
      for (const match of selector.matchAll(/\.([a-zA-Z][\w-]*)/g)) {
        if (!/^(v-|is-)/.test(match[1])) hits.push(`${file}: .${match[1]}`);
      }
    }
  }
  assert.deepEqual(hits, []);
});

test("the root layout imports the layer files in order", async () => {
  const layout = await readFile(path.join(root, "app/layout.tsx"), "utf8");
  const order = ["./globals.css", "./styles/reset.css", "./styles/base.css", "./styles/workbench.css", "./styles/utilities.css"].map((name) => layout.indexOf(`import "${name}";`));
  assert.ok(order.every((index) => index >= 0), "all layer files are imported");
  assert.deepEqual([...order].sort((a, b) => a - b), order, "in layer order");
});

test("base never styles inputs, tables or buttons globally (only the scoped legacy block)", () => {
  const base = stripComments(sources.get("app/styles/base.css"));
  for (const selector of selectors(base)) {
    for (const part of splitTop(selector, /,/)) {
      if (/(^|[\s>+~(])(input|select|textarea|button|table|th|td)\b/.test(part)) assert.match(part, /^:where\(\.workbench\)/, `base.css: ${part} must be scoped to the legacy workbench`);
    }
  }
});
