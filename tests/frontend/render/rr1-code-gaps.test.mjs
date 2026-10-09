import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// RR-1 (4): on /compare the page header is the h2, so the identity check (and
// the "needs review" callout above it) must be h3, not h4 (no skipped level
// after ticking Runs).  The card form without a page title keeps h3 -> h4.
const WORKSPACE = "app/features/results/ComparisonWorkspace.tsx";
const review = {
  schema_version: "value.comparison-review/v1", status: "verified", evidence_complete: true, isolated_change_allowed: true,
  dimensions: Object.fromEntries(["data", "method", "config", "years", "scope"].map((id) => [id, { status: "same", values: [1, 1] }])),
  changed_dimensions: [], unknown_dimensions: [], warning: null,
};

test("the identity check is h3 under a page header and h4 inside the titled card", async () => {
  const underPage = await renderTsx(WORKSPACE, "ComparisonReview", { review, headingLevel: 3 });
  assert.match(underPage, /<h3>Identity check before comparison<\/h3>/);
  assert.doesNotMatch(underPage, /<h4>/);
  const inCard = await renderTsx(WORKSPACE, "ComparisonReview", { review });
  assert.match(inCard, /<h4>Identity check before comparison<\/h4>/);
});

test("a callout can carry an h3 title; the default stays h4", async () => {
  const h3 = await renderTsx("app/features/shared/Callout.tsx", "Callout", { tone: "caution", title: "Review", headingLevel: 3 });
  assert.match(h3, /<h3 class="value-callout-title">Review<\/h3>/);
  const h4 = await renderTsx("app/features/shared/Callout.tsx", "Callout", { tone: "caution", title: "Review" });
  assert.match(h4, /<h4 class="value-callout-title">Review<\/h4>/);
});

test("Compare passes the page-level heading to the identity check and the review callout", async () => {
  const source = await readFile(new URL(`../../../${WORKSPACE}`, import.meta.url), "utf8");
  assert.match(source, /const sectionHeading: 3 \| 4 = title != null \? 3 : 4;/);
  assert.match(source, /<Callout tone="caution" className="value-new-control" headingLevel=\{sectionHeading\}/);
  assert.match(source, /<ComparisonReview review=\{comparison\.comparison_review\} details=\{comparison\.changed_dimension_details\} headingLevel=\{sectionHeading\} \/>/);
});
