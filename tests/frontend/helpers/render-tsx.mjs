// Offline server-side rendering of a TSX component for node --test (P0-9 S0).
//
//   const html = await renderTsx("app/features/shared/presentation.tsx", "Badge", { tone: "good", children: "ok" });
//
// The component and everything it imports (React included) is bundled with
// esbuild into one throw-away ESM file outside the repository and rendered with
// react-dom/server's renderToStaticMarkup. No browser, no network, no dev
// server: the output is exactly the markup a reader's browser would first see,
// so view tests can assert on text ("—", "Not modelled") instead of on source.
//
// Props are passed in-process, so callbacks and non-JSON values are allowed.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { build } from "esbuild";

export const repositoryRoot = path.resolve(import.meta.dirname, "../../..");

const cache = new Map();
let scratch;

// One throw-away directory per test process, outside the repository; removed
// synchronously when the process exits.
function scratchDirectory() {
  scratch ??= mkdtempSync(path.join(tmpdir(), "value-render-tsx-"));
  return scratch;
}

async function load(entry, exportName) {
  const absolute = path.resolve(repositoryRoot, entry);
  const key = `${absolute}#${exportName}`;
  if (!cache.has(key)) {
    cache.set(key, (async () => {
      const directory = scratchDirectory();
      const outfile = path.join(directory, `${cache.size}-${path.basename(entry)}.mjs`);
      await build({
        stdin: {
          contents: [
            `import React from "react";`,
            `import { renderToStaticMarkup } from "react-dom/server";`,
            `import * as target from ${JSON.stringify(absolute)};`,
            `export function render(props) {`,
            `  const component = target[${JSON.stringify(exportName)}];`,
            `  if (typeof component !== "function") throw new Error("${path.basename(entry)} has no function export ${exportName}");`,
            `  return renderToStaticMarkup(React.createElement(component, props));`,
            `}`,
          ].join("\n"),
          resolveDir: repositoryRoot,
          loader: "js",
        },
        bundle: true,
        platform: "node",
        format: "esm",
        jsx: "automatic",
        target: "node22",
        outfile,
        logLevel: "silent",
        define: { "process.env.NODE_ENV": '"production"' },
        // CommonJS packages bundled into ESM still call require().
        banner: { js: 'import { createRequire as __createRequire } from "node:module"; const require = __createRequire(import.meta.url);' },
      });
      return (await import(pathToFileURL(outfile).href)).render;
    })());
  }
  return cache.get(key);
}

export async function renderTsx(entry, exportName = "default", props = {}) {
  return (await load(entry, exportName))(props);
}

/** Visible text of rendered markup: tags removed, entities decoded, whitespace collapsed. */
export function textOf(html) {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

process.once("exit", () => {
  if (scratch) rmSync(scratch, { recursive: true, force: true });
});
