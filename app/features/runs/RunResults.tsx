"use client";

import { useEffect, useState } from "react";
import type { ModelRun, RunResult, PlanningYear } from "./types";
import { formatOptionalNetworkNumber } from "../network/networkRedispatch";
import { Badge, formatNumber, formatMoney, withUnit } from "../shared/presentation";
import { getJson } from "../shared/api";
import { StatusPill, ValueState } from "../shared/Callout";
import { coverageReasonText, yearCoveragePill, yearTotalsPublishable, type ResultCoverage } from "../shared/coverageView.ts";
import { costComposition } from "./resultMetrics.ts";
import "./run-results.css";

/** A recorded annual metric, or null when the Run did not record it (never 0 for missing). */
function metricNumber(result: RunResult, key: string): number | null {
  const value = result.metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function perMwhServed(value: number | null): string {
  return value == null ? "Not evaluated" : `${withUnit(formatNumber(value), "/MWh", "", "£")} served`;
}
function energyMwh(value: number | null): string {
  return value == null ? "Not evaluated" : `${withUnit(formatNumber(value), "MWh")}`;
}
function optionalRunMetric(result: RunResult, key: string, digits = 2): string | null {
  const value = result.metrics[key];
  return formatOptionalNetworkNumber(
    typeof value === "number" && Number.isFinite(value) ? value : null,
    digits,
  );
}
function unavailableCurtailmentReason(result: RunResult): string {
  const reason = result.metrics.vre_curtailment_attribution_reason_code;
  return typeof reason === "string" && reason
    ? reason.replaceAll("_", " ")
    : "attribution evidence unavailable";
}
export function SmokeDiagnostics({ run }: { run: ModelRun }) {
  const crossYear = run.mode === "two_year_smoke";
  const tutorial = run.mode === "value_101_day";
  return <div className="smoke-diagnostic">
    <Badge tone={run.status === "completed" ? "good" : "blue"}>Diagnostic</Badge>
    <h3>{tutorial ? "One-day market lesson" : crossYear ? "Two-year hand-off check" : "Two-period wiring check"}</h3>
    <p>{tutorial ? "This lesson is configured to clear 48 synthetic half-hour periods through the selected production PSM, without a CEM stage. It does not produce annual economics." : crossYear ? "This check is configured for two half-hour periods in each year to exercise the PSM, investment, planning and next-year state hand-offs. The figures from this check are not annual results." : "This short run checks that data and modules connect correctly. Two half-hour periods cannot support annual cost conclusions, so VALUE does not publish them as model results."}</p>
    <small>Actual completion is shown by the execution status and recorded evidence below.</small>
    {run.diagnostic?.years && <small>{run.diagnostic.years.join(" to ")} · {run.diagnostic.total_periods} periods · annual economics withheld</small>}
    {run.diagnostic?.warning && <small>{run.diagnostic.warning}</small>}
    <div className="smoke-modules">{Object.entries(run.modules ?? {}).map(([slot, moduleId]) => {
      const evidence = run.module_evidence?.[moduleId];
      return <span key={slot}><small>{slot.replaceAll("_", " ")}</small><b>{moduleId}</b><em>{evidence ? `${evidence.actions} recorded calls` : "Evidence pending"}</em></span>;
    })}</div>
  </div>;
}

function PlanningPipelinePanel({ runId, year, apiOrigin }: { runId: string; year: number; apiOrigin: string }) {
  const [opened, setOpened] = useState(false);
  const requestKey = JSON.stringify([apiOrigin, runId, year]);
  const [record, setRecord] = useState<{ key: string; summary: PlanningYear | null; error: string } | null>(null);
  const summary = record?.key === requestKey ? record.summary : null;
  const error = record?.key === requestKey ? record.error : "";
  useEffect(() => {
    if (!opened) return;
    const controller = new AbortController();
    void getJson<{ years: PlanningYear[] }>(`${apiOrigin}/api/runs/${runId}/planning/summary`, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        const summary = payload.years.find((item) => item.year === year) ?? null;
        setRecord({ key: requestKey, summary, error: summary ? "" : "Planning evidence is not recorded for this year." });
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setRecord({ key: requestKey, summary: null, error: reason instanceof Error ? reason.message : "Planning evidence unavailable" });
      });
    return () => controller.abort();
  }, [apiOrigin, opened, requestKey, runId, year]);
  const outcome = summary?.breakdowns.outcome ?? {};
  const kpis = summary?.kpis ?? {};
  const completions = summary?.breakdowns.expected_completion_year ?? {};
  return <details className="planning-panel" onToggle={(event) => setOpened(event.currentTarget.open)}>
    <summary>Planning pipeline</summary>
    {!opened ? null : error ? <p className="inline-error">{error}</p> : !summary ? <p className="loading">Loading planning evidence...</p> : <>
      <div className="pipeline-kpis">{["active", "commissioned", "failed", "filtered", "deferred"].map((key) => <span key={key}>
        <small>{key.replaceAll("_", " ")}</small><b>{kpis[key]?.projects ?? outcome[key]?.projects ?? "—"} projects</b><em>{withUnit(formatNumber(kpis[key]?.capacity_mw ?? outcome[key]?.capacity_mw), "MW")}</em>
      </span>)}</div>
      <div className="breakdown-row"><div><b>Next completions</b>{Object.entries(completions).map(([key, value]) => <small key={key}>{key}: {value.projects} projects / {withUnit(formatNumber(value.capacity_mw), "MW")}</small>)}</div><div><b>Technology</b>{Object.entries(summary.breakdowns.technology ?? {}).slice(0, 5).map(([key, value]) => <small key={key}>{key}: {value.projects} / {withUnit(formatNumber(value.capacity_mw), "MW")}</small>)}</div><div><b>Region</b>{Object.entries(summary.breakdowns.region ?? {}).slice(0, 5).map(([key, value]) => <small key={key}>{key}: {value.projects} / {withUnit(formatNumber(value.capacity_mw), "MW")}</small>)}</div></div>
      <div className="breakdown-row"><div><b>Why projects changed</b>{Object.entries(summary.cause_breakdowns?.reason_code ?? {}).slice(0, 8).map(([key, value]) => <small key={key}>{key.replaceAll("_", " ")}: {value.projects} / {withUnit(formatNumber(value.capacity_mw), "MW")}</small>)}</div><div><b>Lifecycle events</b>{Object.entries(summary.cause_breakdowns?.event_type ?? {}).slice(0, 8).map(([key, value]) => <small key={key}>{key.replaceAll("_", " ")}: {value.projects} / {withUnit(formatNumber(value.capacity_mw), "MW")}</small>)}</div></div>
    </>}
  </details>;
}

/** Spec 4.3: composition by the recorded cost definition; the bar adds up to the headline. */
export function CostComposition({ result }: { result: RunResult }) {
  const composition = costComposition(result.metrics);
  return <div className="cost-composition value-new-control">
    <div className="cost-composition-head"><b>Cost composition</b><StatusPill tone="muted">{composition.vollNote}</StatusPill></div>
    {composition.segments.length > 0 ? <div className="cost-stack" role="img" aria-label={`Cost components for ${result.year}: ${composition.segments.map((segment) => `${segment.label} ${withUnit(formatNumber(segment.share * 100, 1), "%", "")}`).join(", ")}`}>{composition.segments.map((segment) => <i key={segment.key} className={segment.className} style={{ width: `${segment.share * 100}%`, background: segment.colour }} title={`${segment.label}: ${formatMoney(segment.amount)} (${withUnit(formatNumber(segment.share * 100, 1), "%", "")})`} />)}</div>
      : <p className="cost-composition-note">{composition.headline == null ? "The headline system cost was not recorded." : "The recorded components exceed the headline; no bar is drawn. See the table."}</p>}
    <table className="cost-composition-table"><tbody>{composition.rows.map((row) => { const segment = composition.segments.find((item) => item.key === row.key); return <tr key={row.key}><th scope="row">{segment ? <span className="cost-legend-swatch" style={{ background: segment.colour }} aria-hidden="true" /> : <span className="cost-legend-swatch empty" aria-hidden="true" />}{row.label}</th><td>{row.state ? <ValueState state={row.state} title={row.state === "not_modelled" ? "This method does not model this mechanism; it is not part of the headline." : "Not recorded by this Run."} /> : formatMoney(row.amount)}</td><td>{segment ? `${withUnit(formatNumber(segment.share * 100, 1), "%", "")}` : row.note === "excluded" ? "excluded" : ""}</td></tr>; })}</tbody></table>
  </div>;
}

export function AnnualResults({ runId, results, apiOrigin, coverage, onOpenInspect }: { runId: string; results: RunResult[]; apiOrigin: string; coverage?: ResultCoverage | null; onOpenInspect?: () => void }) {
  if (!results.length) return <div className="empty-run"><b>No annual results yet</b><p>Results appear after a full model year completes.</p></div>;
  const sorted = [...results].sort((a, b) => a.year - b.year);
  const latest = sorted.at(-1)!;
  const published = (year: number) => yearTotalsPublishable(coverage, year);
  const maxCost = Math.max(...sorted.filter((item) => published(item.year)).map((item) => metricNumber(item, "total_system_cost_gbp") ?? 0), 1);
  const withheldNote = (year: number) => <div className="annual-withheld value-new-control"><ValueState state={coverage?.annual_status === "non_annual" ? "non_annual" : "withheld"} /> <span>{coverageReasonText(coverage)} Annual totals are not shown for {year}.</span>{onOpenInspect && <button type="button" className="value-action-link" onClick={onOpenInspect}>Open in Inspect</button>}</div>;
  const latestPill = yearCoveragePill(coverage, latest.year);
  return <div className="results-cockpit">
    <section className="latest-result">
      <div><small>Latest completed year</small><strong>{latest.year}</strong><StatusPill tone={latestPill.tone} title={latestPill.title}>{latestPill.text}</StatusPill>{published(latest.year) ? <span>{formatMoney(metricNumber(latest, "total_system_cost_gbp"))} total system cost</span> : withheldNote(latest.year)}</div>
      {published(latest.year) && <div className="metric-grid">
        <span><small>Average system cost</small><b>{perMwhServed(metricNumber(latest, "cost_per_mwh_gbp"))}</b></span>
        <span><small>Annualised capital</small><b>{formatMoney(metricNumber(latest, "total_levelized_capital_cost_gbp"))}</b></span>
        <span><small>Operating cost</small><b>{formatMoney(metricNumber(latest, "total_operational_cost_gbp"))}</b></span>
        <span><small>Unserved demand</small><b>{energyMwh(metricNumber(latest, "blackout_mwh"))}</b></span>
      </div>}
    </section>
    {sorted.length > 1 && <section className="cost-trend" aria-label="Annual system cost trend">
      <header><div><small>Across the study</small><h4>Annual system cost</h4></div><span>Relative scale</span></header>
      <div>{sorted.map((result) => { const cost = metricNumber(result, "total_system_cost_gbp"); const show = published(result.year) && cost != null; return <span key={result.year}>{show ? <i style={{ height: `${Math.max(8, cost / maxCost * 100)}%` }} /> : <i className="not-recorded" />}<b>{result.year}</b><small>{show ? formatMoney(cost) : yearCoveragePill(coverage, result.year).text}</small></span>; })}</div>
    </section>}
    <div className="year-records">{[...sorted].reverse().map((result, index) => {
      const pill = yearCoveragePill(coverage, result.year);
      const yearPublished = published(result.year);
      const finalCurtailment = optionalRunMetric(result, "vre_curtailment_mwh");
      const curtailmentRate = typeof result.metrics.vre_curtailment_rate === "number" && Number.isFinite(result.metrics.vre_curtailment_rate)
        ? formatOptionalNetworkNumber(result.metrics.vre_curtailment_rate * 100)
        : null;
      const redispatchNetValue = result.metrics.redispatch_net_impact_mwh;
      const redispatchNet = typeof redispatchNetValue === "number" && Number.isFinite(redispatchNetValue)
        ? formatOptionalNetworkNumber(Math.abs(redispatchNetValue))
        : null;
      const missingCurtailmentReason = unavailableCurtailmentReason(result);
      return <details className="year-record" key={result.year} open={index === 0}>
        <summary><span><b>{result.year}</b><StatusPill tone={pill.tone} title={pill.title}>{pill.text}</StatusPill><small>{yearPublished ? `${formatMoney(metricNumber(result, "total_system_cost_gbp"))} · ${perMwhServed(metricNumber(result, "cost_per_mwh_gbp"))}` : "Annual totals withheld"}</small></span><em>View year</em></summary>
        {!yearPublished ? withheldNote(result.year) : <>
        <CostComposition result={result} />
        <div className="result-domain-grid"><span><small>Imports</small><b>{result.metrics.imports_mwh == null ? "Not evaluated" : energyMwh(metricNumber(result, "imports_mwh"))}</b></span><span><small>Storage charge / discharge</small><b>{result.metrics.storage_charge_mwh == null ? "Not evaluated" : `${formatNumber(metricNumber(result, "storage_charge_mwh"))} / ${energyMwh(metricNumber(result, "storage_discharge_mwh"))}`}</b></span><span><small>Final VRE curtailment</small><b>{finalCurtailment == null ? `Unavailable — ${missingCurtailmentReason}` : `${finalCurtailment} MWh`}</b></span><span><small>VRE curtailment rate</small><b>{curtailmentRate == null ? `Unavailable — ${missingCurtailmentReason}` : `${curtailmentRate}%`}</b></span><span><small>Redispatch net impact</small><b>{redispatchNet == null || typeof redispatchNetValue !== "number" ? `Unavailable — ${missingCurtailmentReason}` : `${redispatchNetValue < 0 ? "−" : redispatchNetValue > 0 ? "+" : ""}${redispatchNet} MWh`}</b></span><span><small>Total carbon</small><b>{result.metrics.total_carbon_emissions_tco2e == null ? "Not evaluated" : `${withUnit(formatNumber(metricNumber(result, "total_carbon_emissions_tco2e")), "tCO₂e")}`}</b><em>{String(result.metrics.carbon_status ?? "not_evaluated").replaceAll("_", " ")}</em></span></div>
        </>}
        {result.planning && <div className="planning-compact"><b>Planning evolution</b><span>Active: {String(result.planning.active ?? "not evaluated")}</span><span>Commissioned: {String(result.planning.commissioned ?? "not evaluated")}</span><span>Failed: {String(result.planning.failed ?? "not applicable")}</span><span>Deferred: {String(result.planning.deferred ?? "not evaluated")}</span></div>}
        <PlanningPipelinePanel key={`${runId}|${result.year}`} runId={runId} year={result.year} apiOrigin={apiOrigin} />
        {result.capacity_mw && <details className="capacity-panel"><summary>Capacity used by the PSM</summary><div className="capacity-grid">{Object.entries(result.capacity_mw).map(([tech, value]) => <span key={tech}><small>{tech}</small><b>{withUnit(formatNumber(value), "MW")}</b></span>)}{result.capacity_mwh?.storage != null && <span><small>Storage energy</small><b>{withUnit(formatNumber(result.capacity_mwh.storage), "MWh")}</b></span>}</div></details>}
      </details>;
    })}</div>
  </div>;
}
