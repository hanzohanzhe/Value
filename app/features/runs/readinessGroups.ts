// Readiness card grouping (spec 11.1, S-D1). Pure logic: the preflight report's
// errors and warnings are shown in full, grouped by priority, with repeated
// issues folded into one row. The backend decides severity; this module only
// orders and folds what it returned. Nothing is dropped.
import type { PreflightIssue } from "./types.ts";

export type ReadinessGroupId = "errors" | "plausibility" | "chronology" | "data" | "adapter_unit" | "environment";
/** An issue as the preflight returns it; `layer` is set on data-layer findings (P0-5a S9). */
export type ReadinessIssue = PreflightIssue & { layer?: string };
export type ReadinessRow = {
  key: string;
  code: string;
  severity: "error" | "warning";
  /** The message without its object prefix ("market.france.price: …" → "…"). */
  text: string;
  correctiveAction: string;
  /** Every object (role, entry) this row stands for; the hover lists them. */
  objects: string[];
  count: number;
};
export type ReadinessGroup = {
  id: ReadinessGroupId;
  label: string;
  tone: "danger" | "caution";
  /** Issues in the group before folding (the header's n). */
  count: number;
  rows: ReadinessRow[];
  /** Errors are always open (no toggle); plausibility starts open; the rest start folded. */
  collapsible: boolean;
  defaultOpen: boolean;
};

export const READINESS_GROUP_LABELS: Readonly<Record<ReadinessGroupId, string>> = {
  errors: "Errors",
  plausibility: "Data plausibility",
  chronology: "Chronology",
  data: "Other data warnings",
  adapter_unit: "Adapter: unit not declared",
  environment: "Environment and setup",
};
const ORDER: readonly ReadinessGroupId[] = ["errors", "plausibility", "chronology", "data", "adapter_unit", "environment"];

// Chronology-layer codes (gridform_core/data_validation_layers.py) for reports
// that predate the `layer` field.
const CHRONOLOGY_CODES = new Set([
  "GF_DATA_TIMESTAMPS", "GF_DATA_BOUNDARY_IDENTITY", "GF_DATA_PRICE_CURRENCY", "GF_DATA_LOCAL_TIME_WITHOUT_TIMESTAMPS",
  "GF_DATA_FORECAST_LAG", "GF_DATA_DST_ROW_ORDER",
]);
const UNIT_NOT_DECLARED = /unit is not declared/i;
// "<object>: <text>" where the object is a role or entry id (no spaces).
const OBJECT_PREFIX = /^([A-Za-z0-9_.\-/]+):\s+([\s\S]+)$/;

export function splitObject(message: string): { object: string | null; text: string } {
  const match = OBJECT_PREFIX.exec(message.trim());
  return match ? { object: match[1], text: match[2] } : { object: null, text: message.trim() };
}

export function issueGroup(issue: ReadinessIssue): ReadinessGroupId {
  if (issue.severity === "error") return "errors";
  const code = issue.code ?? "";
  if (issue.layer === "plausibility" || code.startsWith("GF_DATA_PLAUSIBILITY")) return "plausibility";
  if (issue.layer === "chronology" || CHRONOLOGY_CODES.has(code)) return "chronology";
  if (issue.scope === "data" && UNIT_NOT_DECLARED.test(issue.message ?? "")) return "adapter_unit";
  if (issue.scope === "data" || code.startsWith("GF_DATA_")) return "data";
  return "environment";
}

/**
 * Fold the issues of one group: one row per code and message text (the object
 * prefix removed), with ×n and the objects it covers. Rows keep the order in
 * which the backend reported their first issue.
 */
export function foldIssues(issues: readonly ReadinessIssue[]): ReadinessRow[] {
  const rows = new Map<string, ReadinessRow>();
  for (const issue of issues) {
    const { object, text } = splitObject(String(issue.message ?? ""));
    const key = `${issue.code}\u0000${text}`;
    const row = rows.get(key);
    if (row) {
      row.count += 1;
      if (object && !row.objects.includes(object)) row.objects.push(object);
    } else {
      rows.set(key, {
        key, code: issue.code, severity: issue.severity === "error" ? "error" : "warning", text,
        correctiveAction: String(issue.corrective_action ?? ""), objects: object ? [object] : [], count: 1,
      });
    }
  }
  return [...rows.values()];
}

/**
 * Spec 11.1: every error and warning of a preflight, grouped by priority; empty
 * groups are left out. `shownElsewhere` names warning codes the caller already
 * shows in full in its own notice (R3M-5: the module source-change Callout), so
 * they are not counted a second time; errors are never left out.
 */
export function readinessGroups(report: { errors?: readonly ReadinessIssue[] | null; warnings?: readonly ReadinessIssue[] | null } | null | undefined, shownElsewhere: ReadonlySet<string> = new Set()): ReadinessGroup[] {
  if (!report) return [];
  const buckets = new Map<ReadinessGroupId, ReadinessIssue[]>();
  for (const issue of [...(report.errors ?? []), ...(report.warnings ?? [])]) {
    if (!issue || typeof issue !== "object") continue;
    if (issue.severity !== "error" && shownElsewhere.has(String(issue.code ?? ""))) continue;
    const id = issueGroup(issue);
    buckets.set(id, [...(buckets.get(id) ?? []), issue]);
  }
  return ORDER.filter((id) => buckets.has(id)).map((id) => {
    const issues = buckets.get(id)!;
    return {
      id, label: READINESS_GROUP_LABELS[id], tone: id === "errors" ? "danger" : "caution", count: issues.length,
      rows: foldIssues(issues), collapsible: id !== "errors", defaultOpen: id === "errors" || id === "plausibility",
    };
  });
}

/** The row's hover text: every object it covers, one per line. */
export function rowTitle(row: ReadinessRow): string | undefined {
  return row.objects.length ? row.objects.join("\n") : undefined;
}

/** Spec 11.7 (M-D2): installed modules whose source was edited in place; shown as an amber notice above the groups. */
export const MODULE_SOURCE_CHANGED = "GF_PREFLIGHT_MODULE_SOURCE_CHANGED";
export function sourceChangeWarnings(warnings: readonly ReadinessIssue[] | null | undefined): ReadinessIssue[] {
  return (warnings ?? []).filter((issue) => issue && issue.code === MODULE_SOURCE_CHANGED);
}
