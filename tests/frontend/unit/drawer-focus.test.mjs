import assert from "node:assert/strict";
import test from "node:test";
import { DRAWER_FOCUSABLE, drawerWrapTarget } from "../../../app/features/shell/drawerFocus.ts";

// W6 (P1 spec 7, D-W3-10): while the < 900 px drawer is open, Tab and
// Shift+Tab stay inside the sidebar instead of reaching controls under the backdrop.

const items = ["toggle", "home", "learn", "english", "chinese"];

test("Tab from the last sidebar control wraps to the first (the menu button)", () => {
  assert.equal(drawerWrapTarget(items, "chinese", false), "toggle");
});

test("Shift+Tab from the first sidebar control wraps to the last", () => {
  assert.equal(drawerWrapTarget(items, "toggle", true), "chinese");
});

test("inside the sidebar the browser's own next stop is kept", () => {
  assert.equal(drawerWrapTarget(items, "home", false), null);
  assert.equal(drawerWrapTarget(items, "learn", true), null);
  assert.equal(drawerWrapTarget(items, "toggle", false), null);
  assert.equal(drawerWrapTarget(items, "chinese", true), null);
});

test("focus outside the sidebar is brought back into it", () => {
  assert.equal(drawerWrapTarget(items, null, false), "toggle");
  assert.equal(drawerWrapTarget(items, null, true), "chinese");
});

test("an empty sidebar leaves focus to the browser", () => {
  assert.equal(drawerWrapTarget([], null, false), null);
});

test("the focusable selector covers links, enabled controls and positive tab stops only", () => {
  for (const part of ["a[href]", "button:not([disabled])", "select:not([disabled])", "[tabindex]:not([tabindex=\"-1\"])"]) assert.ok(DRAWER_FOCUSABLE.includes(part), part);
  assert.ok(!/(^|, )button(,|$)/.test(DRAWER_FOCUSABLE), "disabled buttons are not tab stops");
});
