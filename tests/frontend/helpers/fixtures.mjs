// Read a generated UI contract fixture (tests/fixtures/ui-contract, P0-9 S2).
import { readFileSync } from "node:fs";
import path from "node:path";

const directory = path.resolve(import.meta.dirname, "../../fixtures/ui-contract");

export function fixture(name) {
  return JSON.parse(readFileSync(path.join(directory, `${name}.json`), "utf8"));
}

export function payload(name) {
  return fixture(name).payload;
}

export function fixtureNames() {
  return JSON.parse(readFileSync(path.join(directory, "index.json"), "utf8")).fixtures.map((item) => item.file.replace(/\.json$/, ""));
}
