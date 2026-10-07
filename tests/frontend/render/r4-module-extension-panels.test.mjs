import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// R4 M-低4 (DECISIONS A27): duplicate-ID quarantine rows show their manifest file; the
// panel sentence is plural for several entries.
const PANEL = "app/features/modules/ModuleQuarantinePanel.tsx";
const report = { status: "degraded", entries: [
  { kind: "module", id: "hx-flat", version: "1.1.0", manifest_file: "hx-flat.json", error_code: "GF_MODULE_ID_DUPLICATE", message: "Module ID hx-flat is declared by 2 local manifests" },
  { kind: "module", id: "hx-flat", version: "1.1.0", manifest_file: "hx-flat-copy.json", error_code: "GF_MODULE_ID_DUPLICATE", message: "Module ID hx-flat is declared by 2 local manifests" },
] };

test("duplicate-ID rows name their manifest files and the sentence is plural", async () => {
  const text = textOf(await renderTsx(PANEL, "default", { report, busy: "", onDisable() {}, onRescan() {} }));
  assert.match(text, /2 external modules quarantined/);
  assert.match(text, /VALUE started without them\./);
  assert.match(text, /Manifest file: modules\/hx-flat\.json · another manifest uses the same ID; keep one and Rescan/);
  assert.match(text, /Manifest file: modules\/hx-flat-copy\.json/);
});
