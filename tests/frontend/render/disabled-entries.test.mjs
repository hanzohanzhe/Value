import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// Spec 11.4 (M-D4, F-D3) rendered offline: the Disabled and quarantined area.
const PANEL = "app/features/modules/DisabledEntriesPanel.tsx";
const entries = [
  { key: "extension:audit-extension", kind: "extension", id: "audit-extension", label: "Audit 0.1.0", state: "disabled", canEnable: true, canRemove: true },
  { key: "module:broken-psm", kind: "module", id: "broken-psm", label: "broken-psm 1.0.0", state: "quarantined", errorCode: "GF_MODULE_IMPORT_FAILED", message: "SyntaxError: invalid syntax", canEnable: false, canRemove: true },
];
const props = (extra = {}) => ({ entries, busy: "", errors: {}, onEnable() {}, onRescan() {}, onRemove() {}, ...extra });

test("each entry has Enable, Rescan and Remove; a quarantined one says to fix and Rescan", async () => {
  const html = await renderTsx(PANEL, "default", props());
  const text = textOf(html);
  assert.match(text, /Disabled and quarantined/);
  assert.equal((html.match(/>Enable</g) ?? []).length, 2);
  assert.equal((html.match(/>Rescan</g) ?? []).length, 2);
  assert.equal((html.match(/>Remove</g) ?? []).length, 2);
  assert.match(text, /Extension · Disabled/);
  assert.match(text, /Module · Quarantined GF_MODULE_IMPORT_FAILED SyntaxError: invalid syntax Fix the source, then Rescan/);
  assert.match(html, /<button type="button" class="value-action-primary" disabled="" title="Quarantined entries are already enabled/);
});

test("an Enable failure shows that attempt's error with Rescan beside it", async () => {
  const html = await renderTsx(PANEL, "default", props({ errors: { "extension:audit-extension": { code: "GF_EXTENSION_SOURCE_CHANGED", message: "Installed hook source no longer matches its retained identity" } } }));
  assert.match(html, /class="disabled-entry-error" role="alert"><code>GF_EXTENSION_SOURCE_CHANGED<\/code> Installed hook source no longer matches/);
  assert.match(textOf(html), /This is the result of the Enable attempt just made\. Fix the cause, then Rescan\./);
});

test("no entries renders nothing", async () => {
  assert.equal(await renderTsx(PANEL, "default", props({ entries: [] })), "");
});
