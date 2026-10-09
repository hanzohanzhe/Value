"use client";

import { useEffect, useState } from "react";
import type { ModelRun, RunResult, PlanningYear } from "./types";
import { formatOptionalNetworkNumber } from "../network/networkRedispatch";
import { Badge, formatNumber, formatMoney, withUnit } from "../shared/presentation";
import { apiUrl, getJson } from "../../lib/api.ts";
import { Callout, StatusPill, ValueState } from "../shared/Callout";
import { coverageReasonText, coverageStateKey, yearCoveragePercent, yearCoveragePill, yearTotalsPublishable, type ResultCoverage } from "../shared/coverageView.ts";
import { costComposition, unitCostText, unservedDemandText, unusedVreText } from "./resultMetrics.ts";
import { moduleEvidenceText } from "./runHistoryView.ts";
import { planningYearFromPayload } from "./planningView.ts";
import { codePhrase, stageLabel, statusLabel } from "../shared/labels.ts";
import { reasonMessage } from "../shared/reasonCodes.ts";
import { useT } from "../../i18n/LocaleProvider";
import type { Translate } from "../../i18n/index.ts";
import { ChartFrame } from "../../ui/ChartFrame.tsx";
import { DataTable, type DataColumn } from "../../ui/DataTable.tsx";
import { Metric } from "../../ui/Metric.tsx";
import { linearScale, niceTicks } from "../../ui/chartScale.ts";

/** R4 R-低5: a planning count, or its recorded state word ("Not applicable"), never the raw code. */
function planningCount(value: unknown, missing = "not_evaluated"): string {
  if (typeof value === "number") return formatNumber(value, 0);
  return statusLabel(typeof value === "string" ? value : missing);
}
import { gateBlockedPublication, gateBlockedText, publicationPending, type ResultPublication, type RunValidationFields } from "../workspace/runValidation.ts";
import "./run-results.css";

/** A recorded annual metric, or null when the Run did not record it (never 0 for missing). */
function metricNumber(result: RunResult, key: string): number | null {
  const value = result.metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function energyMwh(t: Translate, value: number | null): string {
  return value == null ? t("annual.notEvaluated") : `${withUnit(formatNumber(value), "MWh")}`;
}
function optionalRunMetric(result: RunResult, key: string, digits = 2): string | null {
  const value = result.metrics[key];
  return formatOptionalNetworkNumber(
    typeof value === "number" && Number.isFinite(value) ? value : null,
    digits,
  );
}
function unavailableCurtailmentReason(t: Translate, result: RunResult): string {
  const reason = result.metrics.vre_curtailment_attribution_reason_code;
  return typeof reason === "string" && reason
    ? reasonMessage(reason)
    : t("annual.attributionUnavailable");
}
export function SmokeDiagnostics({ run }: { run: ModelRun }) {
  const t = useT();
  const crossYear = run.mode === "two_year_smoke";
  const tutorial = run.mode === "value_101_day";
  return <div className="smoke-diagnostic">
    <Badge tone={run.status === "completed" ? "good" : "blue"}>{t("annual.smoke.badge")}</Badge>
    <h3>{t(tutorial ? "annual.smoke.lessonTitle" : crossYear ? "annual.smoke.crossYearTitle" : "annual.smoke.wiringTitle")}</h3>
    <p>{t(tutorial ? "annual.smoke.lessonBody" : crossYear ? "annual.smoke.crossYearBody" : "annual.smoke.wiringBody")}</p>
    <small>{t("annual.smoke.completion")}</small>
    {run.diagnostic?.years && <small>{t("annual.smoke.scope", { years: run.diagnostic.years.join(t("annual.smoke.yearJoin")), periods: run.diagnostic.total_periods })}</small>}
    {run.diagnostic?.warning && <small>{run.diagnostic.warning}</small>}
    <div className="smoke-modules">{Object.entries(run.modules ?? {}).map(([slot, moduleId]) => {
      const evidence = run.module_evidence?.[moduleId];
      return <span key={slot}><small>{slot.replaceAll("_", " ")}</small><b>{moduleId}</b><em>{moduleEvidenceText(run, slot, evidence?.actions, evidence, moduleId)}</em></span>;
    })}</div>
  </div>;
}

function PlanningPipelinePanel({ runId, year }: { runId: string; year: number }) {
  const t = useT();
  const [opened, setOpened] = useState(false);
  const requestKey = JSON.stringify([runId, year]);
  const [record, setRecord] = useState<{ key: string; summary: PlanningYear | null; error: string } | null>(null);
  const summary = record?.key === requestKey ? record.summary : null;
  const error = record?.key === requestKey ? record.error : "";
  useEffect(() => {
    if (!opened) return;
    const controller = new AbortController();
    void getJson<unknown>(apiUrl(`runs/${runId}/planning/summary`), controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        // R4 R-中1: a summary without years[] reads "not recorded", not a JS error.
        const { summary, error } = planningYearFromPayload(payload, year);
        setRecord({ key: requestKey, summary, error });
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setRecord({ key: requestKey, summary: null, error: reason instanceof Error ? reason.message : t("annual.pipeline.unavailable") });
      });
    return () => controller.abort();
  }, [opened, requestKey, runId, t, year]);
  const outcome = summary?.breakdowns.outcome ?? {};
  const kpis = summary?.kpis ?? {};
  const completions = summary?.breakdowns.expected_completion_year ?? {};
  return <details className="planning-panel" onToggle={(event) => setOpened(event.currentTarget.open)}>
    <summary>{t("annual.pipeline.title")}</summary>
    {!opened ? null : error ? <p className="inline-error">{error}</p> : !summary ? <p className="loading">{t("annual.pipeline.loading")}</p> : <>
      <div className="pipeline-kpis">{["active", "commissioned", "failed", "filtered", "deferred"].map((key) => <span key={key}>
        <small>{stageLabel(key)}</small><b>{t("annual.pipeline.projects", { count: kpis[key]?.projects ?? outcome[key]?.projects ?? "—" })}</b><em>{withUnit(formatNumber(kpis[key]?.capacity_mw ?? outcome[key]?.capacity_mw), "MW")}</em>
      </span>)}</div>
      <div className="breakdown-row"><div><b>{t("annual.pipeline.next")}</b>{Object.entries(completions).map(([key, value]) => <small key={key}>{t("annual.pipeline.nextRow", { key, count: value.projects, capacity: withUnit(formatNumber(value.capacity_mw), "MW") })}</small>)}</div><div><b>{t("annual.pipeline.technology")}</b>{Object.entries(summary.breakdowns.technology ?? {}).slice(0, 5).map(([key, value]) => <small key={key}>{t("annual.pipeline.row", { key, count: value.projects, capacity: withUnit(formatNumber(value.capacity_mw), "MW") })}</small>)}</div><div><b>{t("annual.pipeline.region")}</b>{Object.entries(summary.breakdowns.region ?? {}).slice(0, 5).map(([key, value]) => <small key={key}>{t("annual.pipeline.row", { key, count: value.projects, capacity: withUnit(formatNumber(value.capacity_mw), "MW") })}</small>)}</div></div>
      <div className="breakdown-row"><div><b>{t("annual.pipeline.why")}</b>{Object.entries(summary.cause_breakdowns?.reason_code ?? {}).slice(0, 8).map(([key, value]) => <small key={key}>{t("annual.pipeline.row", { key: codePhrase(key), count: value.projects, capacity: withUnit(formatNumber(value.capacity_mw), "MW") })}</small>)}</div><div><b>{t("annual.pipeline.events")}</b>{Object.entries(summary.cause_breakdowns?.event_type ?? {}).slice(0, 8).map(([key, value]) => <small key={key}>{t("annual.pipeline.row", { key: stageLabel(key), count: value.projects, capacity: withUnit(formatNumber(value.capacity_mw), "MW") })}</small>)}</div></div>
    </>}
  </details>;
}

/** Spec 4.3: composition by the recorded cost definition; the bar adds up to the headline. */
export function CostComposition({ result }: { result: RunResult }) {
  const t = useT();
  const composition = costComposition(result.metrics);
  return <div className="cost-composition value-new-control">
    <div className="cost-composition-head"><b>{t("annual.cost.title")}</b><StatusPill tone="muted" title={composition.vollTitle}>{composition.vollNote}</StatusPill></div>
    {composition.segments.length > 0 ? <div className="cost-stack" role="img" aria-label={t("annual.cost.aria", { year: result.year, parts: composition.segments.map((segment) => `${segment.label} ${withUnit(formatNumber(segment.share * 100, 1), "%", "")}`).join(", ") })}>{composition.segments.map((segment) => <i key={segment.key} className={segment.className} style={{ width: `${segment.share * 100}%`, background: segment.colour }} title={`${segment.label}: ${formatMoney(segment.amount)} (${withUnit(formatNumber(segment.share * 100, 1), "%", "")})`} />)}</div>
      : <p className="cost-composition-note">{t(composition.headline == null ? "annual.cost.noHeadline" : "annual.cost.exceeds")}</p>}
    <table className="cost-composition-table"><tbody>{composition.rows.map((row) => { const segment = composition.segments.find((item) => item.key === row.key); return <tr key={row.key}><th scope="row">{segment ? <span className="cost-legend-swatch" style={{ background: segment.colour }} aria-hidden="true" /> : <span className="cost-legend-swatch empty" aria-hidden="true" />}{row.label}</th><td>{row.state ? <ValueState state={row.state} title={t(row.state === "not_modelled" ? "annual.cost.notModelled" : "annual.cost.notRecorded")} /> : formatMoney(row.amount)}</td><td>{segment ? `${withUnit(formatNumber(segment.share * 100, 1), "%", "")}` : row.note === "excluded" ? t("annual.cost.excluded") : ""}</td></tr>; })}</tbody></table>
  </div>;
}

/** Q14 / spec 4.2: a withheld reproduction Run shows the state word, one line and the way to the full ledger, never totals. */
export function WithheldAnnualResults({ publication, withheldYearCount, onOpenInspect, onExportLedger }: { publication: ResultPublication; withheldYearCount?: number | null; onOpenInspect?: () => void; onExportLedger?: () => void }) {
  const t = useT();
  const years = typeof withheldYearCount === "number" && withheldYearCount > 0 ? withheldYearCount : null;
  // R5 R-低2: an unfinished reproduction Run is pending, not withheld.
  if (publicationPending(publication)) return <div className="results-cockpit">
    <section className="latest-result annual-results-withheld value-new-control">
      <div><small>{t("annual.label")}</small><StatusPill tone="muted" title={publication.message}>{t("annual.pending")}</StatusPill>
        <div className="annual-withheld"><ValueState state="in_progress" title={publication.reason_code} /> <span>{t("annual.pending.body")}</span></div>
      </div>
    </section>
  </div>;
  return <div className="results-cockpit">
    <section className="latest-result annual-results-withheld value-new-control">
      <div><small>{t("annual.label")}</small><StatusPill tone="caution" title={publication.message}>{t("annual.withheld")}</StatusPill>
        <div className="annual-withheld"><ValueState state="withheld" title={publication.reason_code} /> <span>{years ? t("annual.withheld.bodyYears", { count: years }) : t("annual.withheld.body")}</span>
          {onOpenInspect && <button type="button" className="value-action-link" onClick={onOpenInspect}>{t("annual.openInspect")}</button>}
          {onExportLedger && <button type="button" className="value-action-link" onClick={onExportLedger}>{t("annual.openLedger")}</button>}
        </div>
      </div>
    </section>
  </div>;
}

/** F-P04-4: a corrected (production-policy) Run whose validation gate failed publishes no annual totals. */
export function GateBlockedAnnualResults({ validation, onOpenInspect, onExportLedger }: { validation: RunValidationFields; onOpenInspect?: () => void; onExportLedger?: () => void }) {
  const t = useT();
  const actions = [
    onOpenInspect && <button key="inspect" type="button" className="value-action-primary" onClick={onOpenInspect}>{t("annual.openInspect")}</button>,
    onExportLedger && <button key="export" type="button" className="value-action-link" onClick={onExportLedger}>{t("annual.openLedger")}</button>,
  ].filter(Boolean);
  return <div className="results-cockpit value-new-control">
    <Callout tone="danger" title={t("annual.gate.title")} actions={actions.length ? actions : undefined}><p>{gateBlockedText(validation)}</p></Callout>
  </div>;
}

// R5 R-低4: the annual card counts the planning step (projects still active
// after it, before this year's admissions) and the admissions separately;
// Inspect lists project-year records at year end, where active = both. The
// note is the dictionary message "annual.planning.note" (P1 W5).

/** Spec 2.1 / 6.5: the recorded total system cost of every model year as bars;
 * a year whose totals are not published is an empty outline, never a bar of 0. */
export function CostTrendChart({ results, coverage, selectedYear, onSelect, width }: { results: RunResult[]; coverage?: ResultCoverage | null; selectedYear?: number | null; onSelect?: (year: number) => void; width?: number }) {
  const t = useT();
  const rows = results.map((result) => {
    const cost = metricNumber(result, "total_system_cost_gbp");
    const shown = yearTotalsPublishable(coverage, result.year) && cost != null;
    return { year: result.year, cost: shown ? cost : null, pill: yearCoveragePill(coverage, result.year) };
  });
  const maximum = Math.max(1, ...rows.map((row) => row.cost ?? 0));
  const ticks = niceTicks(0, maximum, 4);
  const top = ticks.at(-1) ?? maximum;
  const columns: DataColumn<(typeof rows)[number]>[] = [
    { key: "year", header: t("runs.trend.col.year"), rowHeader: true, render: (row) => row.year },
    { key: "coverage", header: t("runs.trend.col.coverage"), render: (row) => row.pill.text },
    { key: "cost", header: t("runs.trend.col.cost"), numeric: true, render: (row) => row.cost == null ? <ValueState state="not_recorded" title={row.pill.title} /> : formatMoney(row.cost) },
  ];
  return <section className="cost-trend" aria-label={t("runs.trend.title")}>
    {/* R-18 (P1-polish): the title, then "Across the study" as its subtitle. */}
    <ChartFrame title={<><span className="cost-trend-title">{t("runs.trend.title")}</span> <small className="cost-trend-kicker">{t("runs.trend.kicker")}</small></>} summary={t("runs.trend.summary")} width={width}
      legend={[{ key: "cost", label: t("runs.trend.col.cost"), color: "var(--blue)" }]}
      table={{ caption: t("runs.trend.caption"), columns, rows, rowKey: (row) => String(row.year) }}>
      {({ width: plotWidth, height }) => {
        const left = 64; const right = 12; const topPad = 12; const bottom = 28;
        const innerWidth = Math.max(1, plotWidth - left - right); const innerHeight = Math.max(1, height - topPad - bottom);
        const y = linearScale([0, top], [topPad + innerHeight, topPad]);
        const band = innerWidth / Math.max(1, rows.length);
        // R-18: bars min(64 px, 60 % of the band).
        const barWidth = Math.max(4, Math.min(64, band * 0.6));
        return <g>
          {ticks.map((tick) => <g key={tick}><line className="v-chart__grid" x1={left} x2={left + innerWidth} y1={y(tick)} y2={y(tick)} /><text x={left - 8} y={y(tick) + 4} textAnchor="end">{formatMoney(tick)}</text></g>)}
          <line className="v-chart__axis" x1={left} x2={left + innerWidth} y1={topPad + innerHeight} y2={topPad + innerHeight} />
          {rows.map((row, index) => {
            const x = left + band * index + (band - barWidth) / 2;
            const selected = row.year === selectedYear;
            const select = onSelect ? () => onSelect(row.year) : undefined;
            return <g key={row.year} className={`cost-trend-bar${selected ? " is-selected" : ""}`} onClick={select}>
              <title>{`${row.year}: ${row.cost == null ? row.pill.text : formatMoney(row.cost)}`}</title>
              {row.cost == null
                ? <rect className="cost-trend-bar__missing" x={x} y={topPad + innerHeight - 8} width={barWidth} height={8} />
                : <rect className="cost-trend-bar__value" x={x} y={y(row.cost)} width={barWidth} height={Math.max(1, topPad + innerHeight - y(row.cost))} />}
              <text x={x + barWidth / 2} y={height - 8} textAnchor="middle">{row.year}</text>
            </g>;
          })}
        </g>;
      }}
    </ChartFrame>
  </section>;
}

/** The headline figures of one year (spec 6.5: Metric; a missing value shows its state word, never 0). */
function YearKpis({ result }: { result: RunResult }) {
  const t = useT();
  const unserved = unservedDemandText(result.metrics);
  const unservedValue = metricNumber(result, "unserved_energy_a2_mwh") ?? metricNumber(result, "blackout_mwh");
  return <div className="result-kpis">
    <Metric label={t("runs.kpi.unitCost")} value={metricNumber(result, "cost_per_mwh_gbp")} formatted={unitCostText(result.metrics)} missingState="not_evaluated" />
    <Metric label={t("runs.kpi.capital")} value={metricNumber(result, "total_levelized_capital_cost_gbp")} formatted={formatMoney(metricNumber(result, "total_levelized_capital_cost_gbp"))} missingState="missing" />
    <Metric label={t("runs.kpi.operating")} value={metricNumber(result, "total_operational_cost_gbp")} formatted={formatMoney(metricNumber(result, "total_operational_cost_gbp"))} missingState="missing" />
    <Metric label={t("runs.kpi.unserved")} value={unservedValue} formatted={unserved.value} missingState="not_evaluated" basis={unserved.note ?? undefined} />
  </div>;
}

/** The physical and carbon figures of one published year (Metric; the reason is named when a value is unavailable). */
function YearDomainMetrics({ result }: { result: RunResult }) {
  const t = useT();
  const finalCurtailment = optionalRunMetric(result, "vre_curtailment_mwh");
  const rate = metricNumber(result, "vre_curtailment_rate");
  const curtailmentRate = rate == null ? null : formatOptionalNetworkNumber(rate * 100);
  const redispatchNetValue = metricNumber(result, "redispatch_net_impact_mwh");
  const redispatchNet = redispatchNetValue == null ? null : formatOptionalNetworkNumber(Math.abs(redispatchNetValue));
  const missingCurtailmentReason = unavailableCurtailmentReason(t, result);
  const charge = result.metrics.storage_charge_mwh == null ? null : metricNumber(result, "storage_charge_mwh");
  return <div className="result-domain-metrics">
    <Metric label={t("runs.domain.imports")} value={result.metrics.imports_mwh == null ? null : metricNumber(result, "imports_mwh")} formatted={energyMwh(t, metricNumber(result, "imports_mwh"))} missingState="not_evaluated" />
    <Metric label={t("runs.domain.storage")} value={charge} formatted={`${formatNumber(charge)} / ${energyMwh(t, metricNumber(result, "storage_discharge_mwh"))}`} missingState="not_evaluated" />
    <Metric label={t("runs.domain.unusedVre")} value={metricNumber(result, "unused_vre_mwh")} formatted={unusedVreText(result.metrics)} missingState="not_recorded" />
    <Metric label={t("runs.domain.finalCurtailment")} value={finalCurtailment == null ? null : metricNumber(result, "vre_curtailment_mwh")} formatted={`${finalCurtailment} MWh`} missingState="unavailable" basis={finalCurtailment == null ? missingCurtailmentReason : undefined} />
    <Metric label={t("runs.domain.curtailmentRate")} value={curtailmentRate == null ? null : rate} formatted={`${curtailmentRate}%`} missingState="unavailable" basis={curtailmentRate == null ? missingCurtailmentReason : undefined} />
    <Metric label={t("runs.domain.redispatchNet")} value={redispatchNet == null ? null : redispatchNetValue} formatted={`${redispatchNetValue != null && redispatchNetValue < 0 ? "−" : redispatchNetValue != null && redispatchNetValue > 0 ? "+" : ""}${redispatchNet} MWh`} missingState="unavailable" basis={redispatchNet == null ? missingCurtailmentReason : undefined} />
    <Metric label={t("runs.domain.carbon")} value={result.metrics.total_carbon_emissions_tco2e == null ? null : metricNumber(result, "total_carbon_emissions_tco2e")} formatted={withUnit(formatNumber(metricNumber(result, "total_carbon_emissions_tco2e")), "tCO₂e")} missingState="not_evaluated" basis={<span className="result-carbon-status">{String(result.metrics.carbon_status ?? "not_evaluated").replaceAll("_", " ")}</span>} />
  </div>;
}

/** The capacity the PSM used in one year (spec 6.5: DataTable). */
function CapacityTable({ result }: { result: RunResult }) {
  const t = useT();
  if (!result.capacity_mw) return null;
  const rows: { id: string; label: string; text: string }[] = Object.entries(result.capacity_mw).map(([technology, value]) => ({ id: technology, label: technology, text: withUnit(formatNumber(value), "MW") }));
  if (result.capacity_mwh?.storage != null) rows.push({ id: "storage-energy", label: t("runs.capacity.storageEnergy"), text: withUnit(formatNumber(result.capacity_mwh.storage), "MWh") });
  const columns: DataColumn<(typeof rows)[number]>[] = [
    { key: "technology", header: t("runs.capacity.col.technology"), rowHeader: true, render: (row) => row.label },
    { key: "capacity", header: t("runs.capacity.col.capacity"), numeric: true, render: (row) => row.text },
  ];
  return <details className="capacity-panel"><summary>{t("runs.capacity.title")}</summary><DataTable caption={t("runs.capacity.title")} captionHidden columns={columns} rows={rows} rowKey={(row) => row.id} /></details>;
}

/**
 * Spec 6.5 (W4c): the annual results of one Run, one model year at a time.
 * `year` (the page's ?year=) chooses the year; the latest when absent or not
 * recorded. Every year stays one click away (year buttons and the cost chart).
 */
export function AnnualResults({ runId, results, coverage, onOpenInspect, publication, withheldYearCount, onExportLedger, validation, year, onYearChange }: { runId: string; results: RunResult[]; coverage?: ResultCoverage | null; onOpenInspect?: () => void; publication?: ResultPublication | null; withheldYearCount?: number | null; onExportLedger?: () => void; validation?: RunValidationFields | null; year?: number | null; onYearChange?: (year: number) => void }) {
  const t = useT();
  const [ownYear, setOwnYear] = useState<number | null>(null);
  if (publication?.status === "withheld") return <WithheldAnnualResults publication={publication} withheldYearCount={withheldYearCount} onOpenInspect={onOpenInspect} onExportLedger={onExportLedger} />;
  if (validation && gateBlockedPublication(validation)) return <GateBlockedAnnualResults validation={validation} onOpenInspect={onOpenInspect} onExportLedger={onExportLedger} />;
  if (!results.length) return <div className="empty-run"><b>{t("annual.empty.title")}</b><p>{t("annual.empty.body")}</p></div>;
  const sorted = [...results].sort((a, b) => a.year - b.year);
  const latest = sorted.at(-1)!;
  const wanted = year ?? ownYear;
  const selected = sorted.find((item) => item.year === wanted) ?? latest;
  const choose = (value: number) => { setOwnYear(value); onYearChange?.(value); };
  const published = yearTotalsPublishable(coverage, selected.year);
  // Designer ruling 2: the coverage word (Partial year · n%, Running, Stopped · n%); "Withheld" is only Q14.
  const withheldNote = (value: number) => <div className="annual-withheld value-new-control"><ValueState state={coverageStateKey(coverage)} coveragePercent={yearCoveragePercent(coverage, value)} /> <span>{t("annual.notShown", { reason: coverageReasonText(coverage), year: value })}</span>{onOpenInspect && <button type="button" className="value-action-link" onClick={onOpenInspect}>{t("annual.openInspect")}</button>}</div>;
  const pill = yearCoveragePill(coverage, selected.year);
  return <div className="results-cockpit">
    {sorted.length > 1 && <div className="result-year-chips" role="group" aria-label={t("runs.results.years")}>{sorted.map((result) => {
      const yearPill = yearCoveragePill(coverage, result.year);
      return <button type="button" key={result.year} aria-pressed={result.year === selected.year} className={result.year === selected.year ? "is-selected" : undefined} onClick={() => choose(result.year)}><b>{result.year}</b><small>{yearPill.text}</small></button>;
    })}</div>}
    <section className="latest-result">
      <div><small>{selected.year === latest.year ? t("runs.results.latestYear") : t("runs.results.selectedYear")}</small><strong>{selected.year}</strong><StatusPill tone={pill.tone} title={pill.title}>{pill.text}</StatusPill>{published ? <span>{t("annual.totalCost", { money: formatMoney(metricNumber(selected, "total_system_cost_gbp")) })}</span> : withheldNote(selected.year)}</div>
      {published && <YearKpis result={selected} />}
    </section>
    {sorted.length > 1 && <CostTrendChart results={sorted} coverage={coverage} selectedYear={selected.year} onSelect={choose} />}
    <section className="year-record" aria-label={`${t("runs.results.selectedYear")} ${selected.year}`}>
      {published && <><CostComposition result={selected} /><YearDomainMetrics result={selected} /></>}
      {selected.planning && <div className="planning-compact" title={t("annual.planning.note")}><b>{t("annual.planning.title")}</b><span>{t("annual.planning.active", { count: planningCount(selected.planning.active) })}</span>{selected.planning.admitted != null && <span>{t("annual.planning.admitted", { count: planningCount(selected.planning.admitted) })}</span>}<span>{t("annual.planning.commissioned", { count: planningCount(selected.planning.commissioned) })}</span><span>{t("annual.planning.failed", { count: planningCount(selected.planning.failed, "not_applicable") })}</span><span>{t("annual.planning.deferred", { count: planningCount(selected.planning.deferred) })}</span></div>}
      <PlanningPipelinePanel key={`${runId}|${selected.year}`} runId={runId} year={selected.year} />
      <CapacityTable result={selected} />
    </section>
  </div>;
}
