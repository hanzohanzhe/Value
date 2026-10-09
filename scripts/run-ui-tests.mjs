/** Run one named group of frontend node tests (P0-9 S0).
 *
 *   node scripts/run-ui-tests.mjs <group> [extra node --test arguments]
 *
 * Groups (the npm scripts of the same names call this file):
 *   unit             tests/frontend/unit/*.test.mjs       pure view logic, no React, no browser
 *   render           tests/frontend/render/*.test.mjs     esbuild + renderToStaticMarkup, no browser
 *   harness          tests/frontend/*.test.mjs            real component in headless Chromium
 *                    (set VALUE_E2E_CHROMIUM=<executable> when Playwright's own browser is absent)
 *   source-contracts tests/*.test.mjs                     source and read-model contract scans
 *                    (rendered-html.test.mjs needs `vinext build` and is run by `npm test`)
 *
 * Node 22's `node --test <directory>` treats the directory as a file, and shell
 * globs are not portable to Windows, so the file list is resolved here. An empty
 * group is an error: a typo must never turn a gate green.
 */
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const root = path.resolve(import.meta.dirname, "..");
export const GROUPS = {
  unit: { directory: "tests/frontend/unit" },
  render: { directory: "tests/frontend/render" },
  harness: { directory: "tests/frontend" },
  "source-contracts": { directory: "tests", exclude: new Set(["rendered-html.test.mjs"]) },
};

export function groupFiles(group, base = root) {
  const spec = GROUPS[group];
  if (!spec) throw new Error(`unknown UI test group "${group}" (choose ${Object.keys(GROUPS).join(", ")})`);
  return readdirSync(path.join(base, spec.directory), { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".test.mjs") && !spec.exclude?.has(entry.name))
    .map((entry) => `${spec.directory}/${entry.name}`)
    .sort();
}

if (process.argv[1] === import.meta.filename) {
  const [group, ...rest] = process.argv.slice(2);
  let files;
  try {
    files = groupFiles(group ?? "");
  } catch (error) {
    console.error(error.message);
    process.exit(2);
  }
  if (!files.length) {
    console.error(`UI test group "${group}" matched no test files`);
    process.exit(2);
  }
  const result = spawnSync(process.execPath, ["--test", ...rest, ...files], { cwd: root, stdio: "inherit", env: process.env });
  process.exit(result.status ?? 1);
}
