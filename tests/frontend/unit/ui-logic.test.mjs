import assert from "node:assert/strict";
import test from "node:test";
import { checkNumber, numberText } from "../../../app/ui/numberField.ts";
import { nextTabIndex } from "../../../app/ui/tabKeys.ts";
import { shortHash } from "../../../app/ui/hashText.ts";
import { stableRowKeys } from "../../../app/ui/rowKeys.ts";
import { readSearchParam, writeSearchParam } from "../../../app/ui/useSearchParamState.ts";

// P1 spec 2: pure logic behind the shared components (W1).

test("NumberField parsing: empty is null (not 0), range and step are checked at once", () => {
  assert.deepEqual(checkNumber(""), { value: null, valid: true, message: null });
  assert.deepEqual(checkNumber("  ", { required: true }), { value: null, valid: false, message: "Enter a number" });
  assert.deepEqual(checkNumber("0"), { value: 0, valid: true, message: null });
  assert.deepEqual(checkNumber("-2.5e3"), { value: -2500, valid: true, message: null });
  assert.equal(checkNumber("1.").value, 1);
  assert.deepEqual(checkNumber("abc"), { value: null, valid: false, message: "Not a number" });
  assert.deepEqual(checkNumber("1,5"), { value: null, valid: false, message: "Not a number" });
  assert.deepEqual(checkNumber("1.5", { min: 0, max: 1 }), { value: 1.5, valid: false, message: "Must be at most 1" });
  assert.deepEqual(checkNumber("-1", { min: 0 }), { value: -1, valid: false, message: "Must be at least 0" });
  assert.equal(checkNumber("0.3", { step: 0.1 }).valid, true, "float steps tolerate rounding");
  assert.deepEqual(checkNumber("0.25", { step: 0.1 }), { value: 0.25, valid: false, message: "Must be a multiple of 0.1" });
  assert.equal(numberText(null), "");
  assert.equal(numberText(undefined), "");
  assert.equal(numberText(Number.NaN), "");
  assert.equal(numberText(0), "0");
});

test("Tabs keyboard: arrows wrap, Home/End jump, disabled tabs are skipped", () => {
  const tabs = [{ id: "a" }, { id: "b", disabled: true }, { id: "c" }, { id: "d" }];
  assert.equal(nextTabIndex(tabs, 0, "ArrowRight"), 2);
  assert.equal(nextTabIndex(tabs, 3, "ArrowRight"), 0);
  assert.equal(nextTabIndex(tabs, 0, "ArrowLeft"), 3);
  assert.equal(nextTabIndex(tabs, 2, "Home"), 0);
  assert.equal(nextTabIndex(tabs, 0, "End"), 3);
  assert.equal(nextTabIndex(tabs, 0, "Enter"), null);
  assert.equal(nextTabIndex([{ id: "x", disabled: true }], 0, "ArrowRight"), null);
});

test("Hash shows the first 12 characters and keeps an algorithm prefix", () => {
  assert.equal(shortHash("0123456789abcdef0123"), "0123456789ab…");
  assert.equal(shortHash("sha256:0123456789abcdef"), "sha256:0123456789ab…");
  assert.equal(shortHash("short"), "short");
  assert.equal(shortHash("0123456789ab"), "0123456789ab");
});

test("DataTable row keys: stable IDs; a repeated key is reported and never merges rows", () => {
  const rows = [{ id: "a" }, { id: "b" }, { id: "a" }, { id: "a" }];
  assert.deepEqual(stableRowKeys(rows, (row) => row.id), { keys: ["a", "b", "a#2", "a#3"], duplicates: ["a"] });
  assert.deepEqual(stableRowKeys([{ id: "x" }], (row) => row.id), { keys: ["x"], duplicates: [] });
});

test("URL state: read with fallback and allow-list; write drops the default", () => {
  assert.equal(readSearchParam("?tab=events&q=x", "tab", "items"), "events");
  assert.equal(readSearchParam("?tab=bogus", "tab", "items", ["items", "events"]), "items");
  assert.equal(readSearchParam("", "tab", "items"), "items");
  assert.equal(writeSearchParam("?q=x", "tab", "events", "items"), "?q=x&tab=events");
  assert.equal(writeSearchParam("?tab=events&q=x", "tab", "items", "items"), "?q=x");
  assert.equal(writeSearchParam("?tab=events", "tab", "items", "items"), "");
});
