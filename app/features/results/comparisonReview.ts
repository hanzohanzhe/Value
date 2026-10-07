// Review reasons of a comparison (X0 S10b comparison gate, P0-4 S3; P0-9 S11).
// gridform_core/results_summary.compare_run_summaries decides them; this module
// only states each one in a sentence. An unknown reason is shown by its code.
import { profileBadge } from "../workspace/runValidation.ts";

export type ReviewReason = {
  reason: string;
  run_id?: string | null;
  advisory_id?: string | null;
  severity?: string | null;
  profile_ids?: (string | null)[];
  differing_fields?: string[];
};

function runPrefix(reason: ReviewReason): string {
  return reason.run_id ? `${reason.run_id}: ` : "";
}

export function reviewReasonText(reason: ReviewReason): string {
  switch (reason.reason) {
    case "advisory":
      return `${runPrefix(reason)}advisory ${reason.advisory_id ?? "(unnamed)"}${reason.severity ? ` (${reason.severity})` : ""} applies.`;
    case "validation_failed":
      return `${runPrefix(reason)}scientific validation failed.`;
    case "energy_balance_failed":
      return `${runPrefix(reason)}the energy balance check failed.`;
    case "run_invariants_failed":
      return `${runPrefix(reason)}the run invariants failed.`;
    case "annual_results_withheld":
      return `${runPrefix(reason)}annual results are withheld (reproduction run).`;
    case "methodology_differs": {
      const profiles = (reason.profile_ids ?? []).map((id) => id ? profileBadge({ status: "recorded", profile_id: id }).text : "methodology not recorded");
      const unique = [...new Set(profiles)];
      return unique.length > 1
        ? `The Runs use different methodologies: ${unique.join("; ")}.`
        : `The Runs record different methodology identities (${(reason.differing_fields ?? []).map((field) => field.replaceAll("_", " ")).join(", ") || "identity"}).`;
    }
    default:
      return `${runPrefix(reason)}${reason.reason.replaceAll("_", " ")}.`;
  }
}

/** Per changed identity dimension (gridform_core/results_summary.changed_dimension_details). */
export type DimensionDetail = { label: string; name?: string; paths: string[]; more_paths: number };
export type ChangedDimensionRow = { key: string; label: string; detail: string; raw: string | null };

function pathsText(detail: DimensionDetail): string {
  const listed = detail.paths.join(", ");
  return detail.more_paths > 0 ? `${listed} and ${detail.more_paths} more` : listed;
}

/**
 * R-D7 / S-D9 / F-D5 (four-role report, round R1-5): each changed dimension as
 * a label and the differing paths the backend names, instead of thousands of
 * characters of raw JSON. Scalar module changes read "old → new"; the raw
 * recorded values stay available on request (`raw`).
 */
export function changedDimensionRows(changed: Record<string, unknown[]>, details?: Record<string, DimensionDetail> | null): ChangedDimensionRow[] {
  return Object.entries(changed).map(([key, values]) => {
    const scalar = values.every((value) => value === null || value === undefined || typeof value !== "object");
    const raw = scalar ? null : JSON.stringify(values, null, 2);
    const identity = key.startsWith("identity.") ? details?.[key.slice("identity.".length)] : undefined;
    if (identity && identity.paths.length) return { key, label: identity.label, detail: `differs at ${pathsText(identity)}`, raw };
    if (key.startsWith("module.")) {
      const slot = key.slice("module.".length).replaceAll("_", " ");
      const selections = values.map(moduleSelectionText);
      const named = scalar || selections.every((value) => value !== null);
      return { key, label: `module · ${slot}`, detail: named ? values.map((value, index) => selections[index] ?? String(value ?? "not recorded")).join(" → ") : "recorded values differ", raw };
    }
    return { key, label: identity?.label ?? key.replaceAll("_", " "), detail: scalar ? values.map((value) => String(value ?? "not recorded")).join(" → ") : "recorded values differ", raw };
  });
}

/** A recorded module selection ({module_id, module_version, ...}) as "id version"; null for anything else. */
function moduleSelectionText(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const record = value as { module_id?: unknown; module_version?: unknown };
  if (typeof record.module_id !== "string" || !record.module_id) return null;
  return typeof record.module_version === "string" && record.module_version ? `${record.module_id} ${record.module_version}` : record.module_id;
}

/** The differing paths of one review dimension, or null when the backend names none. */
export function dimensionPathsText(details: Record<string, DimensionDetail> | null | undefined, dimension: string): string | null {
  const detail = details?.[dimension];
  return detail && detail.paths.length ? pathsText(detail) : null;
}

/** A metric id as a heading: "vre_curtailment_mwh" → "Vre Curtailment Mwh". */
export function metricLabel(id: string): string {
  return id.split(".").at(-1)?.replaceAll("_", " ").replace(/\b\w/g, (value) => value.toUpperCase()) ?? id;
}

/** One metric's delta gate (gridform_core/results_summary.metric_delta_gate). */
export type MetricDeltaGate = { allowed: boolean; reason_code?: string | null; definitions?: string[]; reason?: string | null };
export type MetricDeltaFields = {
  metric_deltas_allowed: boolean;
  annual_metrics_withheld: boolean;
  metric_delta_gates?: Record<string, MetricDeltaGate> | null;
  withheld_metric_deltas?: string[] | null;
};

/**
 * AF3-1 (DECISIONS A23): annual deltas are gated per metric. A response
 * without per-metric gates keeps the earlier all-or-nothing flag.
 */
export function metricDeltaShown(comparison: MetricDeltaFields, metricId: string): boolean {
  if (comparison.annual_metrics_withheld) return false;
  const gate = comparison.metric_delta_gates?.[metricId];
  return gate ? gate.allowed === true : comparison.metric_deltas_allowed;
}

/** Why one metric's delta is withheld, in a sentence; null when it is shown. */
export function metricDeltaWithheldText(comparison: MetricDeltaFields, metricId: string): string | null {
  if (comparison.annual_metrics_withheld || metricDeltaShown(comparison, metricId)) return null;
  const gate = comparison.metric_delta_gates?.[metricId];
  if (!gate) return "Delta withheld: the required definitions, scope or attribution evidence are incomplete.";
  if (gate.reason) return `Delta withheld: ${gate.reason}`;
  return `Delta withheld (${(gate.reason_code ?? "reason not recorded").replaceAll("_", " ")}).`;
}

/** One sentence above the annual tables; null when every delta is shown or the teaching boundary applies. */
export function withheldDeltaSummary(comparison: MetricDeltaFields): string | null {
  if (comparison.annual_metrics_withheld) return null;
  const gates = comparison.metric_delta_gates;
  if (!gates || !Object.keys(gates).length) {
    return comparison.metric_deltas_allowed ? null : "Annual deltas are withheld: the required definitions, scope or attribution evidence are incomplete.";
  }
  const ids = Object.keys(gates);
  const withheld = comparison.withheld_metric_deltas?.length ? comparison.withheld_metric_deltas.filter((id) => id in gates) : ids.filter((id) => !gates[id].allowed);
  if (!withheld.length) return null;
  if (withheld.length === ids.length) return "Annual deltas are withheld for every metric; each metric states its reason below.";
  return `Deltas are withheld for ${withheld.length} of ${ids.length} metrics (${withheld.map(metricLabel).join(", ")}); each states its reason below. The other metrics show their deltas.`;
}
