import assert from "node:assert/strict";
import test from "node:test";
import {
  INSTALL_RECORD_INVALID, disableConfirmation, isPendingRunsRefusal, pendingRunsQuestion, quarantineRows, quarantineTitle, sanitizeMessage, stoppedRunsNotice,
} from "../../../app/features/modules/module-quarantine.mjs";

// P0-2 S9 (spec 6).
const report = {
  schema_version: "value.module-quarantine/v1", status: "degraded",
  entries: [
    { kind: "module", id: "my-storage-module", version: "1.2.0", manifest_file: "installed/my-storage-module/value-module.json", error_code: "GF_MODULE_IMPORT_FAILED", error_type: "ModuleNotFoundError",
      message: "Import failed: ModuleNotFoundError: No module named 'scipy_extra'\nTraceback (most recent call last):\n  File \"/home/alice/.value/modules/my_storage/__init__.py\", line 3", corrective_action: "Disable module my-storage-module in Modules" },
    { kind: "extension", id: "flex-demand", version: "0.3.0", error_code: "GF_EXTENSION_HOOK_IMPORT", message: "Hook import failed" },
    { kind: "module", id: "broken-record", version: "2.0.0", error_code: INSTALL_RECORD_INVALID, message: "installation record is missing", corrective_action: "Move the damaged installation aside offline: module_recovery park-installation module broken-record 2.0.0" },
  ],
};

test("rows show the first line, fold the rest, and never show an absolute path", () => {
  const rows = quarantineRows(report);
  assert.equal(rows.length, 3);
  assert.equal(rows[0].label, "my-storage-module 1.2.0");
  assert.equal(rows[0].firstLine, "Import failed: ModuleNotFoundError: No module named 'scipy_extra'");
  assert.match(rows[0].details, /Traceback/);
  for (const row of rows) assert.doesNotMatch(JSON.stringify(row), /\/home\//);
  assert.equal(rows[0].disablePath, "/api/modules/my-storage-module/disable");
  assert.equal(rows[1].disablePath, "/api/extensions/flex-demand/disable");
});

test("a damaged installation record cannot be disabled on the page and points to the offline command", () => {
  const row = quarantineRows(report)[2];
  assert.equal(row.canDisable, false);
  assert.equal(row.disablePath, null);
  assert.match(row.correctiveAction, /park-installation/);
});

test("texts follow spec 6 and the pending-runs refusal is recognised", () => {
  assert.equal(quarantineTitle(1), "1 external module quarantined");
  assert.equal(quarantineTitle(2), "2 external modules quarantined");
  assert.equal(disableConfirmation("my-storage-module"), "Disable my-storage-module? Studies that use it will need another module before they can run.");
  assert.equal(isPendingRunsRefusal(409, "GF_MODULE_LIFECYCLE_RUNS_PENDING"), true);
  assert.equal(isPendingRunsRefusal(409, "GF_MODULE_IN_USE"), false);
  assert.match(pendingRunsQuestion("Runs have not finished: 1 run(s) already running"), /already running[\s\S]*anyway\?$/);
  assert.equal(sanitizeMessage("C:\\Users\\bob\\x.py and /Users/bob/y.py"), "<path> and <path>");
  assert.deepEqual(quarantineRows(null), []);
});

// R6-1 (EM-中1): the success notice names the queued Runs the change stopped.
test("stopped unstarted runs are named in the lifecycle notice", () => {
  assert.equal(stoppedRunsNotice({}), "");
  assert.equal(stoppedRunsNotice({ stopped_unstarted_runs: [] }), "");
  assert.match(stoppedRunsNotice({ stopped_unstarted_runs: ["run-a"] }), /^ 1 Run that had not started was stopped .*GF_RUN_EXECUTION_IDENTITY_CHANGED.*run-a\. Resubmit it /);
  assert.match(stoppedRunsNotice({ stopped_unstarted_runs: ["a", "b"] }), /2 Runs that had not started were stopped.*a, b\. Resubmit them /);
});
