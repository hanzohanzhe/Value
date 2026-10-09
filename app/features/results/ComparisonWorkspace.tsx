"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useState } from "react";
import { useT } from "../../i18n/LocaleProvider";
import { formatSystemTime } from "../shared/format.ts";
import { runIdSuffix } from "../runs/runHistoryView.ts";
import { RUN_SCOPE_LABELS } from "../workspace/runScope";
import type { RunMode } from "../runs/types";
import { MAX_COMPARED_RUNS, csvWithReference, effectiveReference, referenceFirst, type CompareStudy } from "./compareSelection.ts";
import { formatNumber, withUnit } from "../shared/presentation";
import { Callout } from "../shared/Callout";
import { PageHeader } from "../../ui/PageHeader.tsx";
import { codePhrase } from "../shared/labels.ts";
import { profileBadge, type MethodologyRecord } from "../workspace/runValidation.ts";
import { annualWithholdingNotice, type AnnualWithholdingReason, changedDimensionRows, deltaReferenceText, dimensionPathsText, metricDeltaShown, metricDeltaWithheldText, metricLabel, missingMetricValueText, reviewReasonText, withheldDeltaSummary, type DimensionDetail, type MetricDeltaGate, type ReviewReason } from "./comparisonReview.ts";
import "./comparison-workspace.css";
import "./comparison-details.css";
import type { MessageKey } from "../../i18n/index.ts";

type ComparisonRun = { id: string; project_id?: string; project_name: string; mode: string; status: string; created_at?: string | null; updated_at?: string; methodology?: MethodologyRecord | null };
type Dimension = { status: "same" | "changed" | "unknown"; values: unknown[] };
type Review = { schema_version: "value.comparison-review/v1"; status: "verified" | "unknown"; evidence_complete: boolean; isolated_change_allowed: boolean; dimensions: Record<string, Dimension>; changed_dimensions: string[]; unknown_dimensions: string[]; warning: string | null };
type ComparisonMetricValue = { run_id: string; value: number | null; unit?: string; definition_id?: string; denominator?: string | null; delta_from_base?: number | null; percentage_delta_from_base?: number | null };
type RunComparison = {
  comparison_review?: Review;
  /** X0 S10b / P0-4 S3: an advisory, a failed check, a withheld Run or different methodologies forbid causal conclusions. */
  attribution_status?: "needs_review" | "reviewable";
  attribution_review_reasons?: ReviewReason[];
  schema_version: string; run_ids: string[]; changed_dimensions: Record<string, unknown[]>;
  /** R-D7 / S-D9: label and differing paths per changed identity dimension. */
  changed_dimension_details?: Record<string, DimensionDetail>;
  metric_deltas_allowed: boolean; clean_storage_policy_comparison: boolean;
  /** AF3-1 (DECISIONS A23): per-metric delta gates and the withheld metric ids. */
  metric_delta_gates?: Record<string, MetricDeltaGate>; withheld_metric_deltas?: string[];
  comparison_scope: "annual_scientific" | "annual_publication_withheld" | "teaching_diagnostic" | "mixed_tutorial_and_annual";
  annual_metrics_withheld: boolean; storage_pricing_interpretation: string;
  /** R4 R-中2: why annual deltas are withheld (teaching run, Q14 publication), one row per cause. */
  annual_withholding?: AnnualWithholdingReason[];
  causal_claim_allowed: boolean; warning?: string;
  network_cost_attribution_allowed: boolean;
  network_comparison: { reason_code: string; demand_authority_modes: string[]; matched_input_identity_sha256?: string | null };
  annual_comparison: { year: number; metrics: Record<string, ComparisonMetricValue[]> }[];
};

/** RR-1 (4): the identity check is one level below the comparison's own title: h3 under the page header (h2), h4 under the card title (h3). */
export function ComparisonReview({ review, details, headingLevel = 4 }: { review?: Review; details?: Record<string, DimensionDetail>; headingLevel?: 3 | 4 }) {
  // R3M-7 / AF3-2 (round R2): English like the rest of Compare; the method
  // label says that the extension selection belongs to it, the config label
  // that only parameters and extension settings do.
  const t = useT();
  const labels: Record<string, MessageKey> = { data: "comparison.dim.data", method: "comparison.dim.method", config: "comparison.dim.config", years: "comparison.dim.years", scope: "comparison.dim.scope" };
  return <section className="comparison-review" aria-label={t("comparison.identity.title")}>
    {headingLevel === 3 ? <h3>{t("comparison.identity.title")}</h3> : <h4>{t("comparison.identity.title")}</h4>}
    <p>{t(review?.evidence_complete ? "comparison.identity.complete" : "comparison.identity.incomplete")}</p>
    <div className="comparison-dimensions">{Object.entries(labels).map(([id, label]) => {
      const dimension = review?.dimensions[id]; const status = dimension?.status ?? "unknown";
      const paths = status === "changed" ? dimensionPathsText(details, id) : null;
      return <details key={id} data-state={status}><summary><b>{t(label)}</b><span>{t(status === "same" ? "comparison.state.same" : status === "changed" ? "comparison.state.changed" : "comparison.state.unknown")}</span></summary>{paths && <p className="comparison-dimension-paths">{t("comparison.differsAt", { paths })}</p>}<details className="comparison-raw"><summary>{t("comparison.rawValues")}</summary><pre>{JSON.stringify(dimension?.values ?? null, null, 2)}</pre></details></details>;
    })}</div>
    {review?.warning && <p>{review.warning}</p>}
  </section>;
}
function isComparison(value: unknown, ids: string[]): value is RunComparison {
  if (!value || typeof value !== "object") return false;
  const item = value as RunComparison;
  return item.schema_version === "value.run-comparison/v1" && Array.isArray(item.run_ids)
    && JSON.stringify(item.run_ids) === JSON.stringify(ids)
    && !!item.changed_dimensions && typeof item.changed_dimensions === "object"
    && Object.values(item.changed_dimensions).every(Array.isArray)
    && Array.isArray(item.annual_comparison) && !!item.network_comparison
    && item.comparison_review?.schema_version === "value.comparison-review/v1"
    && !!item.comparison_review.dimensions
    && ["data", "method", "config", "years", "scope"].every((dimension) => {
      const entry = item.comparison_review?.dimensions[dimension];
      return !!entry && ["same", "changed", "unknown"].includes(entry.status) && Array.isArray(entry.values) && entry.values.length === ids.length;
    })
    && typeof item.storage_pricing_interpretation === "string";
}
/**
 * Spec 6.6 (EM-低1, W4c): the selected Runs and the reference Run. Every delta
 * is measured against the reference (the backend measures against the first
 * Run of the request, so the reference is sent first); by default the
 * earliest-created baseline Run. `initialRuns`/`initialReference` come from
 * the page URL (/compare?runs=a,b&ref=a) and `onSelectionChange` writes it back.
 */
export default function ComparisonWorkspace({ runs, studies = [], initialRuns = [], initialReference = "", onSelectionChange, title, description }: { runs: ComparisonRun[]; studies?: readonly CompareStudy[]; initialRuns?: readonly string[]; initialReference?: string; onSelectionChange?: (runs: string[], reference: string) => void; /** R-4: the page title and sentence; the page header then carries the export actions. */ title?: string; description?: string }) {
  const t = useT();
  const [picked, setSelected] = useState<string[]>(() => [...initialRuns]);
  const [requestedReference, setRequestedReference] = useState(initialReference);
  const selected = picked.filter((id) => runs.some((run) => run.id === id && run.status === "completed" && ["full", "two_year", "value_101_day"].includes(run.mode)));
  const reference = selected.length ? effectiveReference(requestedReference, selected, runs, studies) : "";
  const requestIds = referenceFirst(selected, reference);
  const [response, setResponse] = useState<{key:string; value?:RunComparison; error?:string} | null>(null);
  const [exportError, setExportError] = useState("");
  const idsKey = JSON.stringify(requestIds);
  // The page's URL follows the ticked Runs and the reference in use (spec 0.3);
  // nothing is written before the workspace has listed its Runs.
  const loaded = runs.length > 0;
  const urlKey = JSON.stringify([picked, selected.length >= 2 ? reference : ""]);
  useEffect(() => {
    if (!loaded) return;
    const [runIds, chosen] = JSON.parse(urlKey) as [string[], string];
    onSelectionChange?.(runIds, chosen);
  }, [loaded, onSelectionChange, urlKey]);
  const key = JSON.stringify([requestIds]);
  const comparison = response?.key === key ? response.value ?? null : null;
  const error = response?.key === key ? response.error ?? "" : "";
  const loading = selected.length >= 2 && response?.key !== key;
  useEffect(() => {
    const ids: string[] = JSON.parse(idsKey);
    if (ids.length < 2) return;
    const controller = new AbortController();
    void apiFetch(apiUrl(`comparisons?runs=${encodeURIComponent(ids.join(","))}`), { cache: "no-store", signal: controller.signal })
      .then(async (res) => { const payload: unknown = await res.json(); if (!res.ok) throw new Error((payload as {error?:string}).error || t("comparison.error.unavailable")); if (!isComparison(payload, ids)) throw new Error(t("comparison.error.mismatch")); return payload; })
      .then((value) => { if (!controller.signal.aborted) setResponse({key, value}); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setResponse({key, error:reason.message}); });
    return () => controller.abort();
  }, [idsKey, key, t]);
  function onToggle(runId: string) {
    setResponse(null);
    setSelected((current) => current.includes(runId) ? current.filter((id) => id !== runId) : [...current, runId].slice(0, MAX_COMPARED_RUNS));
  }
  function download(content: BlobPart, type: string, name: string) {
    const link = document.createElement("a"); const url = URL.createObjectURL(new Blob([content], { type }));
    link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url);
  }
  async function onExport(format: "json" | "csv") {
    if (!comparison) return;
    setExportError("");
    if (format === "csv") {
      // Spec 6.6: the exported CSV names the reference Run (reference_run_id row after schema_version).
      try {
        const res = await apiFetch(apiUrl(`comparisons?runs=${encodeURIComponent(comparison.run_ids.join(","))}&format=csv`), { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        download(`\uFEFF${csvWithReference(await res.text(), comparison.run_ids[0])}`, "text/csv;charset=utf-8", "value-run-comparison.csv");
      } catch (reason) { setExportError(`${t("compare.export.failed")} ${reason instanceof Error ? reason.message : ""}`.trim()); }
      return;
    }
    download(JSON.stringify({ ...comparison, reference_run_id: comparison.run_ids[0] }, null, 2), "application/json", "value-comparison.json");
  }
  const selectedRuns = selected.map((id) => runs.find((run) => run.id === id)).filter((run): run is ComparisonRun => Boolean(run));
  const referenceRun = runs.find((run) => run.id === reference);
  const referenceName = referenceRun ? `${referenceRun.project_name} (${referenceRun.id})` : reference;
  const withholdingNotice = comparison ? annualWithholdingNotice(comparison) : null;
  const selectedClass = selectedRuns.length ? (selectedRuns[0].mode === "value_101_day" ? "tutorial" : "annual") : null;
  const eligible = runs.filter((run) => run.status === "completed" && ["full", "two_year", "value_101_day"].includes(run.mode) && (!selectedClass || (run.mode === "value_101_day" ? "tutorial" : "annual") === selectedClass));
  // R-4 (P1-polish): one page header (the page title and one sentence) with the
  // export actions; no second card title or repeated introduction.
  const exportActions = <div className="comparison-actions"><button className="secondary" disabled={!comparison} onClick={() => void onExport("csv")}>{t("comparison.exportCsv")}</button><button className="secondary" disabled={!comparison} onClick={() => void onExport("json")}>{t("comparison.exportJson")}</button></div>;
  // RR-1 (4): the sections below the picker sit one level under the comparison's title (page header h2 or card h3).
  const sectionHeading: 3 | 4 = title != null ? 3 : 4;
  const tutorialOffered = selectedClass === "tutorial" || (!selectedClass && eligible.some((run) => run.mode === "value_101_day"));
  return <>{title != null && <PageHeader title={title} description={description} actions={exportActions} />}<section className="comparison-workspace" aria-label={title ?? t("comparison.title")}>
    {title == null && <div className="comparison-heading"><div><small>{t("comparison.kicker")}</small><h3>{t("comparison.title")}</h3><p>{t("comparison.intro")}</p></div>{exportActions}</div>}
    <div className="comparison-picker">{eligible.map((run) => <label key={run.id}><input type="checkbox" checked={selected.includes(run.id)} disabled={!selected.includes(run.id) && selected.length >= 6} onChange={() => onToggle(run.id)} /><span><b>{run.project_name}</b><small>{RUN_SCOPE_LABELS[run.mode as RunMode] ?? run.mode} ·{formatSystemTime(run.updated_at) ?? t("comparison.timestampPending")} · {profileBadge(run.methodology).text}</small><code>{run.id}</code></span></label>)}</div>
    {tutorialOffered && <p className="comparison-tutorial-note">{t("comparison.tutorialNote")}</p>}
    {selected.length >= 2 && <div className="comparison-reference-choice value-new-control">
      <label><span>{t("compare.reference.label")}</span><select value={reference} onChange={(event) => { setResponse(null); setRequestedReference(event.target.value); }}>{selectedRuns.map((run) => <option key={run.id} value={run.id}>{t("compare.reference.option", { study: run.project_name, scope: RUN_SCOPE_LABELS[run.mode as RunMode] ?? run.mode, suffix: runIdSuffix(run.id) })}</option>)}</select></label>
      <p role="status"><b>{t("compare.reference.statement", { run: referenceName })}</b> {t("compare.reference.default")}</p>
    </div>}
    {error && <div className="error-box">{error}</div>}{exportError && <div className="error-box" role="alert">{exportError}</div>}{loading && <p role="status">{t("comparison.checking")}</p>}
    {selected.length < 2 && <div className="comparison-empty">{t("comparison.chooseTwo")}</div>}
    {comparison && <>
      {comparison.attribution_status === "needs_review" && <Callout tone="caution" className="value-new-control" headingLevel={sectionHeading} title={t("comparison.review.title")}>
        <p>{comparison.warning ?? t("comparison.review.default")}</p>
        {Boolean(comparison.attribution_review_reasons?.length) && <ul className="comparison-review-reasons">{comparison.attribution_review_reasons?.map((reason, index) => <li key={`${reason.reason}-${reason.run_id ?? ""}-${index}`}>{reviewReasonText(reason)}</li>)}</ul>}
      </Callout>}
      <ComparisonReview review={comparison.comparison_review} details={comparison.changed_dimension_details} headingLevel={sectionHeading} />
      <div className={`comparison-gate ${comparison.clean_storage_policy_comparison || comparison.network_cost_attribution_allowed ? "clean" : "changed"}`}><b>{comparison.network_cost_attribution_allowed ? t("comparison.gate.network") : comparison.comparison_scope === "teaching_diagnostic" && comparison.clean_storage_policy_comparison ? t("comparison.gate.teaching") : comparison.clean_storage_policy_comparison ? t("comparison.gate.storage") : codePhrase(comparison.storage_pricing_interpretation)}</b><small>{comparison.network_cost_attribution_allowed ? t("comparison.gate.networkNote") : comparison.warning ?? t("comparison.gate.controlled")}</small></div>
      {!comparison.network_cost_attribution_allowed && comparison.network_comparison.reason_code !== "comparison_eligibility_artifact_missing" && <div className="info-box"><b>{t("comparison.networkBlocked.title")}</b><br />{t("comparison.networkBlocked.body", { reason: comparison.network_comparison.reason_code.replaceAll("_", " ") })}</div>}
      <div className="module-differences"><b>{t("comparison.changed.title")}</b>{Object.keys(comparison.changed_dimensions).length ? changedDimensionRows(comparison.changed_dimensions, comparison.changed_dimension_details).map((row) => <span key={row.key} title={row.key}><code>{row.label}</code><small>{row.detail}</small>{row.raw && <details className="comparison-raw"><summary>{t("comparison.rawValues")}</summary><pre>{row.raw}</pre></details>}</span>) : <small>{t("comparison.changed.none")}</small>}</div>
      {withholdingNotice && <div className="info-box comparison-annual-withheld"><b>{withholdingNotice.title}</b>{withholdingNotice.lines.map((line) => <span key={line}><br />{line}</span>)}</div>}
      {withheldDeltaSummary(comparison) && <div className="info-box comparison-withheld-summary value-new-control"><b>{t("comparison.withheld.title")}</b><br />{withheldDeltaSummary(comparison)}</div>}
      {!comparison.annual_metrics_withheld && comparison.run_ids[0] && <p className="comparison-reference value-new-control">{deltaReferenceText(comparison.run_ids[0], runs.find((run) => run.id === comparison.run_ids[0])?.project_name)}</p>}
      {!comparison.annual_metrics_withheld && <div className="comparison-years">{comparison.annual_comparison.map((year) => <details key={year.year}><summary>{year.year}</summary><div className="comparison-metrics">{Object.entries(year.metrics).map(([metricId, values]) => <article key={metricId}><header><b>{metricLabel(metricId)}</b><code>{values[0]?.definition_id ?? t("comparison.definitionMissing")}</code></header>{values.map((value) => <span key={value.run_id}><small>{value.run_id}</small><b>{value.value == null ? missingMetricValueText(metricId) : `${formatNumber(value.value)} ${value.unit ?? ""}`}</b>{metricDeltaShown(comparison, metricId) && value.delta_from_base != null && <em>{value.delta_from_base >= 0 ? "+" : ""}{formatNumber(value.delta_from_base)} · {value.percentage_delta_from_base == null ? t("comparison.notApplicable") : `${withUnit(formatNumber(value.percentage_delta_from_base), "%", "")}`}</em>}</span>)}{metricDeltaWithheldText(comparison, metricId) && <p className="comparison-metric-withheld value-new-control">{metricDeltaWithheldText(comparison, metricId)}</p>}</article>)}</div></details>)}</div>}
    </>}
  </section></>;
}

