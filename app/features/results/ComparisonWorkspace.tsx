"use client";

import { useEffect, useState } from "react";
import { formatNumber, withUnit } from "../shared/presentation";
import { Callout } from "../shared/Callout";
import { profileBadge, type MethodologyRecord } from "../workspace/runValidation.ts";
import { reviewReasonText, type ReviewReason } from "./comparisonReview.ts";
import "./comparison-workspace.css";

type ComparisonRun = { id: string; project_name: string; mode: string; status: string; updated_at?: string; methodology?: MethodologyRecord | null };
type Dimension = { status: "same" | "changed" | "unknown"; values: unknown[] };
type Review = { schema_version: "value.comparison-review/v1"; status: "verified" | "unknown"; evidence_complete: boolean; isolated_change_allowed: boolean; dimensions: Record<string, Dimension>; changed_dimensions: string[]; unknown_dimensions: string[]; warning: string | null };
type ComparisonMetricValue = { run_id: string; value: number | null; unit?: string; definition_id?: string; denominator?: string | null; delta_from_base?: number | null; percentage_delta_from_base?: number | null };
type RunComparison = {
  comparison_review?: Review;
  /** X0 S10b / P0-4 S3: an advisory, a failed check, a withheld Run or different methodologies forbid causal conclusions. */
  attribution_status?: "needs_review" | "reviewable";
  attribution_review_reasons?: ReviewReason[];
  schema_version: string; run_ids: string[]; changed_dimensions: Record<string, unknown[]>;
  metric_deltas_allowed: boolean; clean_storage_policy_comparison: boolean;
  comparison_scope: "annual_scientific" | "teaching_diagnostic" | "mixed_tutorial_and_annual";
  annual_metrics_withheld: boolean; storage_pricing_interpretation: string;
  causal_claim_allowed: boolean; warning?: string;
  network_cost_attribution_allowed: boolean;
  network_comparison: { reason_code: string; demand_authority_modes: string[]; matched_input_identity_sha256?: string | null };
  annual_comparison: { year: number; metrics: Record<string, ComparisonMetricValue[]> }[];
};

function labelFor(id: string) { return id.split(".").at(-1)?.replaceAll("_", " ").replace(/\b\w/g, (value) => value.toUpperCase()) ?? id; }
function ComparisonReview({ review }: { review?: Review }) {
  const labels: Record<string, string> = { data: "基础与网络数据", method: "模块方法", config: "参数与扩展配置", years: "执行年份", scope: "运行范围" };
  return <section className="comparison-review" aria-label="比较前身份核对">
    <h4>比较前身份核对</h4>
    <p>{review?.evidence_complete ? "以下差异来自保存的 Run 输入与执行记录。差异描述不自动构成因果归因。" : "冻结身份记录不完整，无法确认其他条件相同；结果只能并列查看。"}</p>
    <div className="comparison-dimensions">{Object.entries(labels).map(([id, label]) => {
      const dimension = review?.dimensions[id]; const status = dimension?.status ?? "unknown";
      return <details key={id} data-state={status}><summary><b>{label}</b><span>{status === "same" ? "一致" : status === "changed" ? "已改变" : "无法核实"}</span></summary><pre>{JSON.stringify(dimension?.values ?? null, null, 2)}</pre></details>;
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
export default function ComparisonWorkspace({ runs, apiOrigin }: { runs: ComparisonRun[]; apiOrigin: string }) {
  const [picked, setSelected] = useState<string[]>([]);
  const selected = picked.filter((id) => runs.some((run) => run.id === id && run.status === "completed" && ["full", "two_year", "value_101_day"].includes(run.mode)));
  const [response, setResponse] = useState<{key:string; value?:RunComparison; error?:string} | null>(null);
  const idsKey = JSON.stringify(selected);
  const key = JSON.stringify([apiOrigin, selected]);
  const comparison = response?.key === key ? response.value ?? null : null;
  const error = response?.key === key ? response.error ?? "" : "";
  const loading = selected.length >= 2 && response?.key !== key;
  useEffect(() => {
    const ids: string[] = JSON.parse(idsKey);
    if (ids.length < 2) return;
    const controller = new AbortController();
    void fetch(`${apiOrigin}/api/comparisons?runs=${encodeURIComponent(ids.join(","))}`, { cache: "no-store", signal: controller.signal })
      .then(async (res) => { const payload: unknown = await res.json(); if (!res.ok) throw new Error((payload as {error?:string}).error || "Comparison unavailable"); if (!isComparison(payload, ids)) throw new Error("比较响应与所选 Run 身份不一致，请重新选择。"); return payload; })
      .then((value) => { if (!controller.signal.aborted) setResponse({key, value}); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setResponse({key, error:reason.message}); });
    return () => controller.abort();
  }, [apiOrigin, idsKey, key]);
  function onToggle(runId: string) {
    setResponse(null);
    setSelected((current) => current.includes(runId) ? current.filter((id) => id !== runId) : [...current, runId].slice(0, 6));
  }
  function onExport(format: "json" | "csv") {
    if (!comparison) return;
    if (format === "csv") { window.open(`${apiOrigin}/api/comparisons?runs=${encodeURIComponent(comparison.run_ids.join(","))}&format=csv`, "_blank", "noopener,noreferrer"); return; }
    const link = document.createElement("a"); const url = URL.createObjectURL(new Blob([JSON.stringify(comparison, null, 2)], {type:"application/json"}));
    link.href = url; link.download = "value-comparison.json"; link.click(); URL.revokeObjectURL(url);
  }
  const selectedRuns = runs.filter((run) => selected.includes(run.id));
  const selectedClass = selectedRuns.length ? (selectedRuns[0].mode === "value_101_day" ? "tutorial" : "annual") : null;
  const eligible = runs.filter((run) => run.status === "completed" && ["full", "two_year", "value_101_day"].includes(run.mode) && (!selectedClass || (run.mode === "value_101_day" ? "tutorial" : "annual") === selectedClass));
  return <section className="comparison-workspace" aria-labelledby="comparison-title">
    <div className="comparison-heading"><div><small>Scenario comparison</small><h3 id="comparison-title">Compare completed runs</h3><p>Select two to six annual runs, or two VALUE 101 teaching runs. Tutorial pairs compare model identity; their annual cost and carbon deltas are withheld.</p></div><div className="comparison-actions"><button className="secondary" disabled={!comparison} onClick={() => onExport("csv")}>Export CSV</button><button className="secondary" disabled={!comparison} onClick={() => onExport("json")}>Export JSON</button></div></div>
    <div className="comparison-picker">{eligible.map((run) => <label key={run.id}><input type="checkbox" checked={selected.includes(run.id)} disabled={!selected.includes(run.id) && selected.length >= 6} onChange={() => onToggle(run.id)} /><span><b>{run.project_name}</b><small>{run.mode} · {run.updated_at ?? "timestamp pending"} · {profileBadge(run.methodology).text}</small><code>{run.id}</code></span></label>)}</div>
    {error && <div className="error-box">{error}</div>}{loading && <p role="status">正在核对所选 Runs 的冻结身份…</p>}
    {selected.length < 2 && <div className="comparison-empty">Choose at least two completed runs of the same scope.</div>}
    {comparison && <>
      {comparison.attribution_status === "needs_review" && <Callout tone="caution" className="value-new-control" title="This comparison needs review">
        <p>{comparison.warning ?? "An advisory, a failed validation or a methodology difference rules out causal conclusions."}</p>
        {Boolean(comparison.attribution_review_reasons?.length) && <ul className="comparison-review-reasons">{comparison.attribution_review_reasons?.map((reason, index) => <li key={`${reason.reason}-${reason.run_id ?? ""}-${index}`}>{reviewReasonText(reason)}</li>)}</ul>}
      </Callout>}
      <ComparisonReview review={comparison.comparison_review} />
      <div className={`comparison-gate ${comparison.clean_storage_policy_comparison || comparison.network_cost_attribution_allowed ? "clean" : "changed"}`}><b>{comparison.network_cost_attribution_allowed ? "Controlled copperplate–zonal network comparison" : comparison.comparison_scope === "teaching_diagnostic" && comparison.clean_storage_policy_comparison ? "Controlled teaching configuration" : comparison.clean_storage_policy_comparison ? "Controlled storage-policy comparison" : comparison.storage_pricing_interpretation.replaceAll("_", " ")}</b><small>{comparison.network_cost_attribution_allowed ? "Demand, initial state, weather availability, years and non-network modules have matching machine-readable identities." : comparison.warning ?? "Data, years, non-storage modules and scientific definitions are controlled."}</small></div>
      {!comparison.network_cost_attribution_allowed && comparison.network_comparison.reason_code !== "comparison_eligibility_artifact_missing" && <div className="info-box"><b>Network-cost attribution blocked</b><br />{comparison.network_comparison.reason_code.replaceAll("_", " ")}. Side-by-side results remain available, but the difference is not labelled as a network effect.</div>}
      <div className="module-differences"><b>Changed dimensions</b>{Object.keys(comparison.changed_dimensions).length ? Object.entries(comparison.changed_dimensions).map(([key, values]) => <span key={key}><code>{key}</code><small>{values.map((value) => typeof value === "object" && value !== null ? JSON.stringify(value) : String(value ?? "not recorded")).join(" → ")}</small></span>) : <small>No differences found in available records; check unknown dimensions above.</small>}</div>
      {comparison.annual_metrics_withheld && <div className="info-box"><b>Teaching boundary</b><br />Annual cost and carbon deltas are withheld because these runs contain one 48-period market day. The export contains identities and changed dimensions, not annual metrics.</div>}
      {!comparison.metric_deltas_allowed && !comparison.annual_metrics_withheld && <div className="error-box">所需的定义、范围或归因证据不完整。VALUE 暂不展示未获支持的差值。</div>}
      {!comparison.annual_metrics_withheld && <div className="comparison-years">{comparison.annual_comparison.map((year) => <details key={year.year}><summary>{year.year}</summary><div className="comparison-metrics">{Object.entries(year.metrics).map(([metricId, values]) => <article key={metricId}><header><b>{labelFor(metricId)}</b><code>{values[0]?.definition_id ?? "definition not evaluated"}</code></header>{values.map((value) => <span key={value.run_id}><small>{value.run_id}</small><b>{value.value == null ? "Not evaluated" : `${formatNumber(value.value)} ${value.unit ?? ""}`}</b>{comparison.metric_deltas_allowed && value.delta_from_base != null && <em>{value.delta_from_base >= 0 ? "+" : ""}{formatNumber(value.delta_from_base)} · {value.percentage_delta_from_base == null ? "n/a" : `${withUnit(formatNumber(value.percentage_delta_from_base), "%", "")}`}</em>}</span>)}</article>)}</div></details>)}</div>}
    </>}
  </section>;
}

