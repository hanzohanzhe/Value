import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { studyIdFromName, uniqueStudyName } from "../../../app/features/studies/draftName.ts";
import { disableConfirmation } from "../../../app/features/modules/module-quarantine.mjs";

// R5-4 (A28): add-feature defects of the R4 final four-role report (build c204aac).

test("F-中2: the draft Study ID mirrors the server slug", () => {
  assert.equal(studyIdFromName("VALUE 101 baseline · extension study"), "value-101-baseline-extension-study");
  assert.equal(studyIdFromName("  --  "), "project");
  assert.equal(studyIdFromName("x".repeat(80)).length, 64);
});

test("F-中2: a second extension draft from the same baseline gets a free name", () => {
  const name = "VALUE 101 baseline · extension study";
  assert.equal(uniqueStudyName(name, [{ id: "value-101-baseline" }]), name);
  const taken = [{ id: "value-101-baseline-extension-study" }];
  assert.equal(uniqueStudyName(name, taken), `${name} 2`);
  assert.equal(uniqueStudyName(name, [...taken, { id: "value-101-baseline-extension-study-2" }]), `${name} 3`);
});

test("F-中2: a long name keeps its number inside the 64-character ID", () => {
  const name = `${"Long baseline ".repeat(6)}· extension study`;
  const candidate = uniqueStudyName(name, [{ id: studyIdFromName(name) }]);
  assert.notEqual(studyIdFromName(candidate), studyIdFromName(name));
  assert.ok(studyIdFromName(candidate).endsWith("-2"));
});

test("F-中2: the extension draft uses the unique name", async () => {
  // P1 W3: the extension author workbench and its draft handler are on /extensions.
  const page = await readFile(new URL("../../../app/extensions/ExtensionsView.tsx", import.meta.url), "utf8");
  assert.match(page, /uniqueStudyName\(`\$\{base\.name\} · extension study`, workspace\.projects\)/);
});

test("F-低1: disabling an extension talks about deselecting it, not another module", () => {
  assert.equal(disableConfirmation("my-storage-module"), "Disable my-storage-module? Studies that use it will need another module before they can run.");
  const text = disableConfirmation("fin-af-observer", "extension");
  assert.match(text, /deselect it \(saved as a new revision\)/);
  assert.doesNotMatch(text, /module/);
});

test("F-低4: the Data page names an unsaved draft as a draft", async () => {
  // P1 W3: the Study context line is drawn by the workbench shell.
  // P1 W4a: its wording is the dictionary entry studies.context.draft (English unchanged).
  const page = await readFile(new URL("../../../app/features/shell/Workbench.tsx", import.meta.url), "utf8");
  // P1-polish R-6: the line is built once (shown in main, or in the narrow top bar's Study disclosure).
  assert.match(page, /const draftStudyContext = \(view === "projects" \|\| \(view === "data" && dataContextId === "draft"\)\) && !editingProjectId;/);
  assert.match(page, /draftStudyContext \? <div className="workspace-study-context"><span>\{t\("studies\.context\.draft"\)\}<\/span>/);
  const { en } = await import("../../../app/i18n/en.ts");
  assert.equal(en["studies.context.draft"], "Independent Study draft");
});
