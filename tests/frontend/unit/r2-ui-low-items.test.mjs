import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { baseInputsPill } from "../../../app/features/shared/headerPill.ts";
import { studyNameTaken } from "../../../app/features/workspace/studyNames.ts";
import { LEARN_RUN_FREEZE_NOTE } from "../../../app/features/runs/runHistoryView.ts";

// Round R2 (DECISIONS A23, four-role report 10.7 "顺带修").
const root = path.resolve(import.meta.dirname, "../../..");

// R3M-2: a degraded /api/health (one quarantined module) does not hide the pack's inputs.
test("the header pill says 'Inputs not loaded' only when the workspace could not be read", () => {
  const pack = { complete: true, valid_required_count: 25, required_count: 25 };
  assert.deepEqual(baseInputsPill(true, pack), { text: "25 of 25 base inputs ready", tone: "good" });
  assert.deepEqual(baseInputsPill(true, { ...pack, complete: false, valid_required_count: 24 }), { text: "24 of 25 base inputs ready", tone: "warn" });
  assert.deepEqual(baseInputsPill(false, pack), { text: "Inputs not loaded", tone: "warn" });
  assert.deepEqual(baseInputsPill(true, null), { text: "No data pack", tone: "warn" });
});

// R3-N4: a second Study with the same name is flagged (names may repeat).
test("a Study name already in use is recognised regardless of case and spaces", () => {
  const studies = [{ name: "Repro corrected R3" }, { name: "VALUE 101 baseline" }];
  assert.equal(studyNameTaken(studies, "Repro corrected R3"), true);
  assert.equal(studyNameTaken(studies, "  repro CORRECTED r3 "), true);
  assert.equal(studyNameTaken(studies, "Repro corrected R4"), false);
  assert.equal(studyNameTaken(studies, "   "), false);
});

// L-4: Learn explains the wait itself instead of only disabling its buttons.
test("the Learn launch note explains the freeze and where the Run opens", () => {
  // A24-5: the start no longer waits for the freeze; the note says so.
  assert.match(LEARN_RUN_FREEZE_NOTE, /freezes its inputs in the background/);
  assert.match(LEARN_RUN_FREEZE_NOTE, /If you stay on this page, the Run opens when it is listed;/);
});

// R3-N3 and R3M-7 (page wiring, since P1 W3 split over the workbench state,
// the shell and the route views): the Callout's "Open in Inspect" no longer
// forces the Planning tab, ordinary navigation clears a requested tab, and the
// method-comparison notice is English.
test("page wiring: Inspect target, navigation and the method-comparison notice", async () => {
  const read = (file) => readFile(path.join(root, file), "utf8");
  const [state, shell, rail, runs, network] = await Promise.all([
    read("app/features/shell/useWorkbenchState.ts"), read("app/features/shell/Workbench.tsx"), read("app/features/shell/WorkspaceRail.tsx"),
    read("app/runs/RunsView.tsx"), read("app/runs/[runId]/network/NetworkView.tsx"),
  ]);
  const source = [state, shell, runs, network].join("\n");
  assert.doesNotMatch(source, /tab \?\? "planning"/);
  assert.match(shell, /setInspectTarget\(tab \? \{ tab, nonce: Date\.now\(\) \} : null\)/);
  assert.match(state, /const openView = \(next: View\) => \{ setInspectTarget\(null\); setView\(next\); \};/);
  // The sidebar (and the Run section bar) navigate through openView, which clears a requested Inspect tab.
  assert.match(shell, /<WorkspaceRail view=\{view\} onNavigate=\{openView\}/);
  assert.match(shell, /<RunSectionNav view=\{view\} [^\n]*?onNavigate=\{openView\} \/>/);
  // P1 W3: the entries are links to their routes; a plain click stays in the workbench.
  assert.match(rail, /href=\{viewHref\(item\.id\)\}/);
  assert.match(rail, /event\.preventDefault\(\); setOpen\(false\); onNavigate\(item\.id\);/);
  assert.match(runs, /onNavigate: openView,/);
  assert.match(network, /onOpenInspect=\{\(\) => openView\("audit"\)\}/);
  assert.doesNotMatch(source, /方法对照 Study 已保存/);
  // The pill takes the workspace state (not health) and the translate function;
  // since W3 (R3-04) the pack is the selected Study's outside a draft.
  assert.match(shell, /baseInputsPill\(online, headerPack, t\)/);
  assert.match(shell, /const headerPack = draftContext \? selectedPack : selectedProjectPack;/);
  assert.doesNotMatch(source, /connectionState !== "online" \? "Inputs not loaded"/);
});
