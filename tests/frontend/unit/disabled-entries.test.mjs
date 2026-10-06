import assert from "node:assert/strict";
import test from "node:test";
import { currentExtensionRecords, disabledEntries, lifecyclePath, removeConfirmation } from "../../../app/features/modules/disabledEntries.ts";

// Spec 11.4 (M-D4, F-D3): every disabled or quarantined local entry stays reachable.
const modules = [
  { module_id: "my-storage-cost", name: "My storage cost", module_version: "1.0.0", enabled: false },
  { module_id: "working-module", name: "Working", module_version: "2.0.0", enabled: true },
];
const extensions = [
  { extension_id: "audit-extension", name: "Audit", version: "0.1.0", enabled: true },
  { extension_id: "audit-extension", name: "Audit", version: "0.10.0", enabled: false },
  { extension_id: "on-extension", name: "On", version: "1.0.0", enabled: true },
];
const quarantine = { status: "degraded", entries: [
  { kind: "module", id: "broken-psm", version: "1.0.0", error_code: "GF_MODULE_IMPORT_FAILED", message: "SyntaxError: invalid syntax\nTraceback /home/alice/x.py" },
  { kind: "module", id: null, manifest_file: "orphan.json", error_code: "GF_MODULE_MANIFEST_INVALID", message: "unreadable" },
] };

test("disabled modules, the current disabled extension version and quarantined entries are listed", () => {
  const rows = disabledEntries({ modules, extensions, quarantine });
  assert.deepEqual(rows.map((row) => [row.key, row.state, row.canEnable]), [
    ["extension:audit-extension", "disabled", true],
    ["module:broken-psm", "quarantined", false],
    ["module:my-storage-cost", "disabled", true],
  ]);
  const broken = rows.find((row) => row.id === "broken-psm");
  assert.equal(broken.errorCode, "GF_MODULE_IMPORT_FAILED");
  assert.equal(broken.message, "SyntaxError: invalid syntax");
  assert.ok(rows.every((row) => row.canRemove));
});

test("the highest extension version is the current record (1.10 > 1.9)", () => {
  const current = currentExtensionRecords([{ extension_id: "x", version: "1.9.0", enabled: true }, { extension_id: "x", version: "1.10.0", enabled: false }]);
  assert.deepEqual(current.map((row) => row.version), ["1.10.0"]);
  assert.deepEqual(disabledEntries({ extensions: [{ extension_id: "x", version: "1.9.0", enabled: false }, { extension_id: "x", version: "1.10.0", enabled: true }] }), []);
});

test("nothing disabled or quarantined lists nothing", () => {
  assert.deepEqual(disabledEntries({ modules: [modules[1]], extensions: [extensions[2]], quarantine: { status: "ok", entries: [] } }), []);
  assert.deepEqual(disabledEntries({}), []);
});

test("paths and the Remove confirmation", () => {
  assert.equal(lifecyclePath({ kind: "module", id: "my storage" }, "enable"), "/modules/my%20storage/enable");
  assert.equal(lifecyclePath({ kind: "extension", id: "audit-extension" }, "remove"), "/extensions/audit-extension/remove");
  assert.match(removeConfirmation({ kind: "module", id: "my-storage-cost" }), /^Remove module my-storage-cost\? .*not deleted/);
});
