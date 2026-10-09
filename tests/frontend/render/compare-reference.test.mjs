import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// EM-低1 (W4c, P1 spec 6.6): Compare names its reference Run at the top and
// offers a selector; the default is the earliest-created baseline Run.
const WORKSPACE = "app/features/results/ComparisonWorkspace.tsx";
const run = (id, project, created) => ({ id, project_id: project, project_name: project === "base" ? "Baseline" : "Derived", mode: "two_year", status: "completed", created_at: created, updated_at: created });
const runs = [run("derived-r", "derived", "2026-10-08T12:00:00+01:00"), run("base-r", "base", "2026-10-08T13:00:00+01:00"), run("other-r", "derived", "2026-10-08T11:00:00+01:00")];
const studies = [{ id: "derived", derivation: { source_study_id: "base" } }, { id: "base" }];

test("two ticked Runs show the reference selector, defaulting to the baseline Study's Run", async () => {
  const html = await renderTsx(WORKSPACE, "default", { runs, studies, initialRuns: ["derived-r", "base-r"] });
  assert.match(html, /<label><span>Reference Run<\/span><select><option value="derived-r">Derived · Two full model years · r<\/option><option value="base-r" selected="">Baseline · Two full model years · r<\/option><\/select><\/label>/);
  assert.match(html, /<b>Reference Run: Baseline \(base-r\)\. Every delta \(\+ and %\) is measured against it\.<\/b>/);
});

test("a reference named by the URL wins while it is ticked; fewer than two Runs show no selector", async () => {
  const chosen = await renderTsx(WORKSPACE, "default", { runs, studies, initialRuns: ["derived-r", "base-r"], initialReference: "derived-r" });
  assert.match(chosen, /<option value="derived-r" selected="">/);
  assert.match(chosen, /Reference Run: Derived \(derived-r\)/);
  const one = await renderTsx(WORKSPACE, "default", { runs, studies, initialRuns: ["derived-r"] });
  assert.doesNotMatch(one, /Reference Run/);
  assert.match(one, /Choose at least two completed runs of the same scope\./);
});
