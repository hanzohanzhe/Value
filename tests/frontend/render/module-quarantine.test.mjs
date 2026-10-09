import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

const PANEL = "app/features/modules/ModuleQuarantinePanel.tsx";
const report = { status: "degraded", entries: [{ kind: "module", id: "my-storage-module", version: "1.2.0", error_code: "GF_MODULE_IMPORT_FAILED", message: "Import failed: ModuleNotFoundError: x\nTraceback /home/alice/secret.py" }] };

test("the quarantine panel names the module, its error and the two actions", async () => {
  const html = await renderTsx(PANEL, "default", { report, busy: "", onDisable() {}, onRescan() {} });
  const text = textOf(html);
  assert.match(text, /1 external module quarantined/);
  assert.match(text, /VALUE started without it\. Runs that need it cannot start until it is fixed or disabled\./);
  assert.match(text, /my-storage-module 1\.2\.0 Import failed: ModuleNotFoundError: x GF_MODULE_IMPORT_FAILED/);
  assert.match(text, /Disable Rescan/);
  assert.doesNotMatch(html, /\/home\//);
  assert.match(html, /role="alert"/);
});

test("nothing is rendered when nothing is quarantined", async () => {
  assert.equal(await renderTsx(PANEL, "default", { report: { status: "ok", entries: [] }, busy: "", onDisable() {}, onRescan() {} }), "");
});
