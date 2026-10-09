import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { en } from "../../../app/i18n/en.ts";
import { zh } from "../../../app/i18n/zh.ts";
import { translator } from "../../../app/i18n/index.ts";
import { latestRunFor, newestRuns, runCreatedTime } from "../../../app/features/shared/latestRun.ts";
import {
  DEFAULT_STUDY_NAME, INITIAL_DRAFT_PACK_ID, STUDY_DRAFT_SCHEMA, defaultStudyForm, parseStoredDraft, readStoredDraft, removeStoredDraft,
  sameDraft, savedStudySnapshot, stableJson, studyDraftKey, studyFormFromProject, writeStoredDraft,
} from "../../../app/features/studies/studyDraft.ts";
import { newStudyNameClash, saveFailureNotice } from "../../../app/features/studies/studySave.ts";
import { domainBadgeText, profileOptionLabel, studyMethodologyText } from "../../../app/features/studies/methodologyChoice.ts";
import { buildStudyTrashConfirmation } from "../../../app/features/learn/studyLifecycle.ts";

// P1 W4a (spec 6.1, 6.2): Home, Learn, the research guide and Studies.
const root = path.resolve(import.meta.dirname, "../../..");
const t = translator("en");
const tz = translator("zh");

test("F4-07: the latest Run is the one created last, not the last or first in the update-ordered list", () => {
  // The workspace lists Runs by updated_at, newest first: an old Run touched recently comes first.
  const runs = [
    { id: "study-a-20261001-090000-aaaa1111", project_id: "a", mode: "two_year", status: "archived" },
    { id: "study-a-20261003-120000-bbbb2222", project_id: "a", mode: "two_year", status: "completed", created_at: "2026-10-03T12:00:00+00:00" },
    { id: "study-b-20261004-080000-cccc3333", project_id: "b", mode: "two_year", status: "failed" },
    { id: "study-a-20260930-070000-dddd4444", project_id: "a", mode: "value_101_day", status: "completed" },
  ];
  assert.equal(runs.filter((run) => run.project_id === "a").at(-1).id, "study-a-20260930-070000-dddd4444", "the old rule picked the oldest");
  assert.equal(latestRunFor(runs, "a").id, "study-a-20261003-120000-bbbb2222");
  assert.equal(latestRunFor(runs, "a", "value_101_day").id, "study-a-20260930-070000-dddd4444");
  assert.equal(latestRunFor(runs, "missing"), undefined);
  assert.equal(latestRunFor(runs, undefined), undefined);
  assert.deepEqual(newestRuns(runs, 3).map((run) => run.id.slice(-8)), ["cccc3333", "bbbb2222", "aaaa1111"]);
  assert.equal(runCreatedTime({ id: "no-timestamp" }), null);
  // Undated Runs keep their list order after the dated ones.
  assert.deepEqual(newestRuns([{ id: "x" }, { id: "s-20260101-000000-ab" }, { id: "y" }]).map((run) => run.id), ["s-20260101-000000-ab", "x", "y"]);
});

test("AF-低2: drafts are stored under a key with the Study ID and compare by content", () => {
  assert.equal(studyDraftKey(), "value.study-draft.v1:new");
  assert.equal(studyDraftKey("value-101-baseline"), "value.study-draft.v1:value-101-baseline");
  assert.equal(stableJson({ b: 1, a: { d: [1, { y: 2, x: undefined }], c: 3 } }), '{"a":{"c":3,"d":[1,{"y":2}]},"b":1}');
  const form = defaultStudyForm();
  assert.equal(form.name, DEFAULT_STUDY_NAME);
  assert.equal(INITIAL_DRAFT_PACK_ID, "value-uk-1000twh-reproduction");
  const snapshot = { form, parameters: {}, runtime: { "runtime.market_trace_level": "summary" }, packId: "p" };
  const reordered = { packId: "p", runtime: { "runtime.market_trace_level": "summary" }, parameters: {}, form: { ...form, modules: Object.fromEntries(Object.entries(form.modules).reverse()) } };
  assert.ok(sameDraft(snapshot, reordered), "key order does not make a draft unsaved");
  assert.ok(!sameDraft(snapshot, { ...snapshot, form: { ...form, start_year: 2030 } }));
  assert.ok(!sameDraft(snapshot, null));
});

test("AF-低2: a saved Study's editable form keeps its data pack identity and defaults", () => {
  const project = { id: "s", name: "S", data_pack_id: "pack", start_year: 2025, end_year: 2026, modules: { psm: "m" }, parameters: { a: 1 }, runtime_options: { "runtime.market_trace_level": "full" }, updated_at: "" };
  const result = studyFormFromProject(project, "Copy of S");
  assert.equal(result.form.name, "Copy of S");
  assert.deepEqual(result.form.modules, { psm: "m" });
  assert.notEqual(result.form.modules, project.modules, "the draft does not share objects with the saved Study");
  assert.deepEqual(result.parameters, { a: 1 });
  assert.deepEqual(result.runtime, { "runtime.market_trace_level": "full" });
  assert.equal(result.form.solver_contract, undefined);
  assert.ok(studyFormFromProject({ ...project, modules: { balancing: "value-zonal-redispatch-balancing" } }).form.solver_contract, "a zonal Study gets the default solver contract");
});

test("AF-低2: stored drafts are validated and storage failures never throw", () => {
  const draft = { schema: STUDY_DRAFT_SCHEMA, studyId: null, baseRevision: null, savedAt: "2026-10-08T10:00:00Z", snapshot: { form: defaultStudyForm("Mine"), parameters: {}, runtime: {}, packId: "p" } };
  const memory = new Map();
  const storage = { getItem: (key) => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value), removeItem: (key) => memory.delete(key) };
  assert.equal(writeStoredDraft(storage, studyDraftKey(), draft), true);
  assert.equal(readStoredDraft(storage, studyDraftKey()).snapshot.form.name, "Mine");
  removeStoredDraft(storage, studyDraftKey());
  assert.equal(readStoredDraft(storage, studyDraftKey()), null);
  for (const text of [null, "", "not json", "[]", JSON.stringify({ ...draft, schema: "other" }), JSON.stringify({ ...draft, snapshot: { ...draft.snapshot, form: { name: 1 } } })]) {
    assert.equal(parseStoredDraft(text), null, String(text));
  }
  const broken = { getItem() { throw new Error("SecurityError"); }, setItem() { throw new Error("QuotaExceededError"); }, removeItem() { throw new Error("SecurityError"); } };
  assert.equal(readStoredDraft(broken, "k"), null);
  assert.equal(writeStoredDraft(broken, "k", draft), false);
  assert.doesNotThrow(() => removeStoredDraft(broken, "k"));
  assert.equal(writeStoredDraft(null, "k", draft), false);
});

test("F4-03: a new Study's name that maps to a used ID is flagged with a free suggestion", () => {
  const projects = [{ id: "value-uk-transition" }];
  const trash = [{ study_id: "old-study" }];
  assert.deepEqual(newStudyNameClash("VALUE UK transition", projects, trash), { kind: "saved", id: "value-uk-transition", suggestion: "VALUE UK transition 2" });
  assert.deepEqual(newStudyNameClash("Old study!", projects, trash), { kind: "trash", id: "old-study", suggestion: "Old study! 2" });
  assert.equal(newStudyNameClash("A fresh name", projects, trash), null);
  assert.equal(newStudyNameClash("   ", projects, trash), null);
});

test("F4-03: a refused or unreachable save says why, with the service's message after a translated explanation", () => {
  const projects = [{ id: "value-uk-transition" }];
  const exists = saveFailureNotice({ kind: "refused", status: 409, code: "GF_STUDY_ID_EXISTS", error: "A Study with ID value-uk-transition already exists (VALUE UK transition).", studyId: "value-uk-transition" }, t, "VALUE UK transition", projects);
  assert.match(exists, /^A Study with the ID value-uk-transition already exists\. Give this Study another name \(for example “VALUE UK transition 2”\)/);
  assert.match(exists, /GF_STUDY_ID_EXISTS: A Study with ID value-uk-transition already exists \(VALUE UK transition\)\.$/);
  assert.match(saveFailureNotice({ kind: "refused", status: 409, code: "GF_STUDY_ID_EXISTS", error: "sent", studyId: "x" }, tz, "x", projects), /^已有 ID 为 x 的 Study。.*GF_STUDY_ID_EXISTS: sent$/);
  assert.match(saveFailureNotice({ kind: "network" }, t, "x", projects), /could not be reached, so the Study was not saved\. The draft is kept/);
  assert.equal(saveFailureNotice({ kind: "refused", status: 500 }, t, "x", projects), "The Study was not saved. Save failed (HTTP 500).");
  assert.equal(saveFailureNotice({ kind: "refused", status: 409, error: "Project revision conflict" }, t, "x", projects), "The Study was not saved. Project revision conflict");
});

test("methodology wording follows the interface language; English stays the default", () => {
  const corrected = { id: "c", label: "C", frozen: false, default: true };
  const doctoral = { id: "d", label: "D", frozen: true, default: false };
  assert.equal(profileOptionLabel(corrected), "Corrected methodology (default)");
  assert.equal(profileOptionLabel(doctoral, tz), "论文复现口径");
  assert.equal(profileOptionLabel(corrected, tz), "修正口径（默认）");
  assert.equal(domainBadgeText("ready", false, tz), "此方法学口径下不可用");
  assert.equal(studyMethodologyText({}, null, tz).label, "默认方法学口径");
  assert.equal(buildStudyTrashConfirmation({ id: "a", name: "A" }, 0, tz).message, "把 A 及其全部不可变修订移入可恢复的回收站？");
});

test("every dictionary key the W4a pages build at run time exists in both languages", async () => {
  const computed = [
    ...["reproduce", "data", "module", "function"].flatMap((id) => ["label", "description", "capability"].map((part) => `home.path.${id}.${part}`)),
    ...["queued", "snapshotting", "running", "cancel_requested", "cancelled", "completed", "failed", "archived", "deleting"].map((status) => `home.run.status.${status}`),
    ...["buildingBlocks", "baseline", "marketDay", "marketEvidence", "annualRun", "annualEvidence", "researchModel", "network"].flatMap((key) => ["title", "time", "copy"].map((part) => `learn.step.${key}.${part}`)),
    ...["pipeline", "storage_cost", "psm", "vre_cap", "storage_cap", "investment", "transition"].map((slot) => `learn.module.${slot}`),
  ];
  for (const key of computed) assert.ok(key in en && key in zh, key);
  // Literal keys in the W4a sources (t("…") and "…" as MessageKey) exist too.
  const files = ["app/HomeView.tsx", "app/learn/LearnView.tsx", "app/journey/JourneyView.tsx", "app/studies/StudiesView.tsx", "app/features/workspace/CommunityPaths.tsx",
    "app/features/workspace/ResearchJourney.tsx", "app/features/learn/Value101Learn.tsx", "app/features/learn/Value101NetworkExercise.tsx", "app/features/learn/ModuleChainCard.tsx",
    "app/features/studies/StudyComposer.tsx", "app/features/studies/AdvancedSettings.tsx", "app/features/studies/SolverSettingsEditor.tsx", "app/features/studies/NetworkOverlaySelector.tsx",
    "app/features/studies/studySave.ts", "app/features/studies/methodologyChoice.ts", "app/features/shell/useWorkbenchState.ts"];
  for (const file of files) {
    const source = await readFile(path.join(root, file), "utf8");
    for (const match of source.matchAll(/"((?:home|learn|journey|studies|errors)\.[A-Za-z0-9_.]*[A-Za-z0-9_])"/g)) assert.ok(match[1] in en, `${file}: ${match[1]}`);
  }
});

test("Linux and Windows readers get the same install hint (F4-07)", () => {
  assert.doesNotMatch(en["learn.network.notInstalled"], /Windows/);
  assert.doesNotMatch(zh["learn.network.notInstalled"], /Windows/);
});

test("W4a review (AF-低2): after a save, or when an edit is left, the workbench puts a matching form in the composer", async () => {
  const project = { id: "s", name: "S", data_pack_id: "pack", start_year: 2025, end_year: 2026, modules: { psm: "m" }, parameters: {}, runtime_options: {}, updated_at: "", revision_sha256: "r",
    market_configuration: { ahead_market_module_id: "m", ledger_detail: "summary", voll_gbp_per_mwh: 17000 }, extension_parameters: { "x.y": 1 } };
  const snapshot = savedStudySnapshot(project);
  assert.equal(snapshot.packId, "pack");
  assert.deepEqual(snapshot.form.market_configuration, project.market_configuration, "the backend's normalised market configuration is kept");
  assert.ok(sameDraft(snapshot, savedStudySnapshot(structuredClone(project))), "the saved revision is its own baseline");
  assert.ok(!sameDraft({ ...snapshot, form: { ...snapshot.form, market_configuration: {} } }, snapshot), "the as-typed form differs from the saved one");
  const source = await readFile(path.join(root, "app/features/shell/useWorkbenchState.ts"), "utf8");
  const body = (name) => source.slice(source.indexOf(`function ${name}(`), source.indexOf("\n  }\n", source.indexOf(`function ${name}(`)));
  assert.match(body("saveProject"), /studyDraft\.forget\(draftKeyId\);\s*\/\/[^\n]*\n\s*applyStudySnapshot\(savedStudySnapshot\(payload\.project\)\);/);
  assert.match(body("leaveStudyEdit"), /if \(editingProjectId\) studyDraft\.reset\(\);/);
  assert.match(body("openResearchSuiteStudy"), /leaveStudyEdit\(\);/);
  assert.match(body("moveStudyToTrash"), /if \(editingProjectId === project\.id\) \{ leaveStudyEdit\(\);/);
  // Only leaveStudyEdit clears the editing context inside the workbench state.
  assert.equal(source.match(/setEditingProjectId\(undefined\)/g)?.length, 1);
});
