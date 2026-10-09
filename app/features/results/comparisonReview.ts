// Review reasons of a comparison (X0 S10b comparison gate, P0-4 S3; P0-9 S11).
// gridform_core/results_summary.compare_run_summaries decides them; this module
// only states each one in a sentence. An unknown reason is shown by its code.
import { profileBadge } from "../workspace/runValidation.ts";
import { metricLabel as sharedMetricLabel } from "../shared/labels.ts";
import { tr } from "../../i18n/index.ts";

export type ReviewReason = {
  reason: string;
  run_id?: string | null;
  advisory_id?: string | null;
  severity?: string | null;
  profile_ids?: (string | null)[];
  differing_fields?: string[];
};

function runPrefix(reason: ReviewReason): string {
  return reason.run_id ? tr("review.runPrefix", { run: reason.run_id }) : "";
}

export function reviewReasonText(reason: ReviewReason): string {
  switch (reason.reason) {
    case "advisory":
      return reason.severity
        ? tr("review.advisorySeverity", { prefix: runPrefix(reason), id: reason.advisory_id ?? tr("review.unnamed"), severity: reason.severity })
        : tr("review.advisory", { prefix: runPrefix(reason), id: reason.advisory_id ?? tr("review.unnamed") });
    case "validation_failed":
      return tr("review.validationFailed", { prefix: runPrefix(reason) });
    case "energy_balance_failed":
      return tr("review.energyBalanceFailed", { prefix: runPrefix(reason) });
    case "run_invariants_failed":
      return tr("review.runInvariantsFailed", { prefix: runPrefix(reason) });
    case "annual_results_withheld":
      return tr("review.withheld", { prefix: runPrefix(reason) });
    case "methodology_differs": {
      const profiles = (reason.profile_ids ?? []).map((id) => id ? profileBadge({ status: "recorded", profile_id: id }).text : tr("review.methodologyNotRecorded"));
      const unique = [...new Set(profiles)];
      return unique.length > 1
        ? tr("review.methodologies", { profiles: unique.join("; ") })
        : tr("review.methodologyIdentities", { fields: (reason.differing_fields ?? []).map((field) => field.replaceAll("_", " ")).join(", ") || tr("review.identity") });
    }
    default:
      return tr("review.other", { prefix: runPrefix(reason), reason: reason.reason.replaceAll("_", " ") });
  }
}

/** Per changed identity dimension (gridform_core/results_summary.changed_dimension_details). */
export type DimensionDetail = { label: string; name?: string; paths: string[]; more_paths: number };
export type ChangedDimensionRow = { key: string; label: string; detail: string; raw: string | null };

function pathsText(detail: DimensionDetail): string {
  const listed = detail.paths.join(", ");
  return detail.more_paths > 0 ? tr("review.pathsMore", { paths: listed, count: detail.more_paths }) : listed;
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
    if (identity && identity.paths.length) return { key, label: identity.label, detail: tr("review.differsAt", { paths: pathsText(identity) }), raw };
    if (key.startsWith("module.")) {
      const slot = key.slice("module.".length).replaceAll("_", " ");
      const selections = values.map(moduleSelectionText);
      const named = scalar || selections.every((value) => value !== null);
      return { key, label: tr("review.module", { slot }), detail: named ? values.map((value, index) => selections[index] ?? String(value ?? tr("review.notRecorded"))).join(" → ") : tr("review.valuesDiffer"), raw };
    }
    return { key, label: identity?.label ?? key.replaceAll("_", " "), detail: scalar ? values.map((value) => String(value ?? tr("review.notRecorded"))).join(" → ") : tr("review.valuesDiffer"), raw };
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

/** A metric id as a heading from the shared label table (R4 R-低5): "vre_curtailment_mwh" → "VRE curtailment (MWh)". */
export function metricLabel(id: string): string {
  return sharedMetricLabel(id);
}

/** S-F-低5 (R5), EM-低1 (W4c, spec 6.6): which Run the annual deltas are measured against: the reference Run. */
export function deltaReferenceText(runId: string, name?: string | null): string {
  return tr("review.reference", { run: name ? tr("review.referenceNamed", { name, run: runId }) : runId });
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

/**
 * S-低7(b) (R4, A27): the word for a missing value, the same as on the Runs page.
 * The three metrics built from VRE-curtailment evidence read "Unavailable" there
 * (RunResults), so they do here; other missing values stay "Not evaluated".
 */
export const CURTAILMENT_EVIDENCE_METRICS: readonly string[] = ["vre_curtailment_mwh", "vre_curtailment_rate", "redispatch_net_impact_mwh"];
export function missingMetricValueText(metricId: string): string {
  // R5-2 review: only a ledger with a separate pre-balancing stage (doctoral rules) records this.
  if (metricId === "pre_balancing_excess_mwh") return tr("review.notApplicable");
  return tr(CURTAILMENT_EVIDENCE_METRICS.includes(metricId) ? "review.unavailable" : "review.notEvaluated");
}

/** Why one metric's delta is withheld, in a sentence; null when it is shown. */
export function metricDeltaWithheldText(comparison: MetricDeltaFields, metricId: string): string | null {
  if (comparison.annual_metrics_withheld || metricDeltaShown(comparison, metricId)) return null;
  const gate = comparison.metric_delta_gates?.[metricId];
  if (!gate) return tr("review.deltaIncomplete");
  if (gate.reason) return tr("review.deltaReason", { reason: gate.reason });
  return tr("review.deltaCode", { code: (gate.reason_code ?? tr("review.reasonNotRecorded")).replaceAll("_", " ") });
}

/** One sentence above the annual tables; null when every delta is shown or the teaching boundary applies. */
export function withheldDeltaSummary(comparison: MetricDeltaFields): string | null {
  if (comparison.annual_metrics_withheld) return null;
  const gates = comparison.metric_delta_gates;
  if (!gates || !Object.keys(gates).length) {
    return comparison.metric_deltas_allowed ? null : tr("review.summaryIncomplete");
  }
  const ids = Object.keys(gates);
  const withheld = comparison.withheld_metric_deltas?.length ? comparison.withheld_metric_deltas.filter((id) => id in gates) : ids.filter((id) => !gates[id].allowed);
  if (!withheld.length) return null;
  if (withheld.length === ids.length) return tr("review.summaryAll");
  return tr("review.summarySome", { withheld: withheld.length, total: ids.length, metrics: withheld.map(metricLabel).join(", ") });
}

/** One cause of withheld annual deltas (gridform_core/results_summary.annual_withholding_reasons). */
export type AnnualWithholdingReason = { reason_code: string; run_ids?: (string | null)[]; text?: string | null };
export type AnnualWithholdingFields = {
  annual_metrics_withheld: boolean;
  comparison_scope?: string;
  annual_withholding?: AnnualWithholdingReason[] | null;
  run_ids?: string[];
};


/**
 * R4 R-中2 (four-role report): the box above the annual tables names the
 * actual reason annual deltas are withheld - the VALUE 101 teaching boundary,
 * or a reproduction Run whose annual results Q14 withholds - instead of
 * always the teaching text. Null when annual deltas are not withheld.
 */
export function annualWithholdingNotice(comparison: AnnualWithholdingFields): { title: string; lines: string[] } | null {
  if (!comparison.annual_metrics_withheld) return null;
  const reasons = comparison.annual_withholding ?? [];
  const teaching = reasons.some((reason) => reason.reason_code === "teaching_run")
    || (!reasons.length && ["teaching_diagnostic", "mixed_tutorial_and_annual"].includes(comparison.comparison_scope ?? ""));
  const publication = reasons.filter((reason) => reason.reason_code === "result_publication_withheld");
  if (teaching && !publication.length) return { title: tr("review.teachingTitle"), lines: [tr("review.teaching")] };
  if (!publication.length) {
    return { title: tr("review.deltasWithheldTitle"), lines: [reasons.length ? reasons.map((reason) => `${(reason.run_ids ?? []).filter(Boolean).join(", ")} ${reason.text ?? reason.reason_code.replaceAll("_", " ")}.`.trim()).join(" ") : tr("review.deltasWithheldDefault")] };
  }
  const withheldIds = new Set(publication.flatMap((reason) => reason.run_ids ?? []).filter(Boolean));
  const lines = publication.map((reason) => tr("review.q14Line", { runs: (reason.run_ids ?? []).filter(Boolean).join(", "), text: reason.text ?? tr("review.q14Default") }));
  if (teaching) lines.push(tr("review.alsoTeaching"));
  const published = (comparison.run_ids ?? []).filter((id) => !withheldIds.has(id));
  lines.push(teaching || !published.length
    ? tr("review.noDeltas")
    : tr("review.noDeltasPublished", { runs: published.join(", ") }));
  return { title: tr("review.resultsWithheldTitle"), lines };
}
