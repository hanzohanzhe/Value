"use client";

// VRE & curtailment (moved verbatim from app/page.tsx in P1 W3; route /runs/[runId]/vre).
import { useEffect, useState } from "react";
import { API_BASE, getJson } from "../../lib/api.ts";
import { Badge, formatNumber, withUnit } from "../shared/presentation";
import { formatEnergy, formatEnergyGroup, formatQuantity } from "../shared/format.ts";
import { modelTimeLabel, modelTimeText } from "../shared/modelClock.ts";
import { useT } from "../../i18n/LocaleProvider";
import { ChartFrame, type LegendItem } from "../../ui/ChartFrame.tsx";
import { type DataColumn } from "../../ui/DataTable.tsx";
import { PageHeader } from "../../ui/PageHeader.tsx";
import { linearScale, niceTicks } from "../../ui/chartScale.ts";
import { axisLabelIndices } from "./dispatchView.ts";
import { StatusPill } from "../shared/Callout";
import { runPreparing, useStableRun } from "../shared/stableRun.ts";
import type { ModelRun } from "../runs/types";
import { annualResultsWithheld, publicationPending, vrePendingText, vreWithheldText } from "../workspace/runValidation.ts";
import type { DispatchTimeline, VreSummary } from "./marketTypes.ts";
import { seriesShapes, vreEventGroups, vreKpis, vreLabels, vreYearCoverage } from "./vreView.ts";
import { DEFAULT_VRE_LOCATION, vreQueryValues, vreYear, type VreLocation } from "./vreLocation.ts";
import "./market-replay.css";

const API = API_BASE;

type VreRow = { key: string; time: string; available: number | null; accepted: number | null; unused: number | null; excess: number | null };
const vreNumber = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;

/**
 * Spec 2.1 (W4c): the VRE timeline in a ChartFrame - pixel SVG with 12 px
 * text, an HTML legend (colour and line style) and the same series as a table.
 * Designer ruling 4 is kept: an isolated recorded value is a 2.5 px dot.
 */
export function VreTimelineChart({ timeline, excessLabel: excessLabelProp, width: fixedWidth }: { timeline: DispatchTimeline; excessLabel?: string; width?: number }) {
  const t = useT();
  const excessLabel = excessLabelProp ?? t("vre.chart.excessDefault");
  const items = timeline.items;
  const maximum = Math.max(1, ...items.flatMap((item) => [item.vre_available_mwh, item.vre_accepted_mwh, item.excess_mwh]).filter((value) => typeof value === "number" && Number.isFinite(value)));
  const ticks = niceTicks(0, maximum, 4);
  const top = Math.max(maximum, ticks.at(-1) ?? maximum);
  const legend: LegendItem[] = [
    { key: "available", label: t("vre.chart.available"), color: "var(--blue)", line: "solid" },
    { key: "accepted", label: t("vre.chart.accepted"), color: "var(--teal)", line: "solid" },
    { key: "unused", label: t("vre.chart.unused"), color: "var(--tech-unused-vre)", line: "solid" },
    { key: "excess", label: excessLabel, color: "var(--red)", line: "dashed" },
  ];
  const rows: VreRow[] = items.map((item) => ({ key: `${item.period_start}-${item.period_end}`, time: modelTimeLabel(item.timestamp_start), available: vreNumber(item.vre_available_mwh), accepted: vreNumber(item.vre_accepted_mwh), unused: vreNumber(item.neutral_unused_vre_mwh), excess: vreNumber(item.excess_mwh) }));
  const cell = (value: number | null) => value == null ? "—" : withUnit(formatNumber(value), "MWh");
  const columns: DataColumn<VreRow>[] = [
    { key: "time", header: t("vre.chart.col.start"), rowHeader: true, render: (row) => row.time },
    { key: "available", header: t("vre.chart.available"), numeric: true, render: (row) => cell(row.available) },
    { key: "accepted", header: t("vre.chart.accepted"), numeric: true, render: (row) => cell(row.accepted) },
    { key: "unused", header: t("vre.chart.unused"), numeric: true, render: (row) => cell(row.unused) },
    { key: "excess", header: excessLabel, numeric: true, render: (row) => cell(row.excess) },
  ];
  const first = items[0] ? modelTimeLabel(items[0].timestamp_start) : "";
  const last = items.at(-1) ? modelTimeLabel(items.at(-1)!.timestamp_end) : "";
  return <ChartFrame width={fixedWidth} className="evidence-chart vre-timeline-chart" title={t("vre.chart.title")} summary={t("vre.chart.summary", { count: items.length, first, last })} legend={legend} table={{ caption: t("vre.chart.caption"), columns, rows, rowKey: (row) => row.key }}>
    {({ width, height }) => {
      const left = 60; const right = 12; const topPad = 14; const bottom = 30;
      const plotWidth = Math.max(1, width - left - right); const plotHeight = Math.max(1, height - topPad - bottom);
      const x = (index: number) => left + index / Math.max(items.length - 1, 1) * plotWidth;
      const y = linearScale([0, top], [topPad + plotHeight, topPad]);
      // Designer ruling 4: an isolated recorded value (or a one-bucket view) is a 2.5px dot in the series colour.
      const segments = (key: "vre_available_mwh" | "vre_accepted_mwh" | "excess_mwh" | "neutral_unused_vre_mwh", className: string) => { const shapes = seriesShapes(items, key, x, y); return <>{shapes.lines.map((points, index) => <polyline key={`${key}-${index}`} points={points} className={className} />)}{shapes.dots.map((dot, index) => <circle key={`${key}-dot-${index}`} cx={dot.x} cy={dot.y} r={1.25} className={`${className} series-dot`} />)}</>; };
      const daily = items.some((item) => item.period_count > 1);
      return <g>
        {ticks.map((tick) => <g key={tick}><line className="v-chart__grid" x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} /><text x={left - 8} y={y(tick) + 4} textAnchor="end">{formatQuantity(tick, 3)}</text></g>)}
        {segments("vre_available_mwh", "vre-available-line")}{segments("vre_accepted_mwh", "vre-accepted-line")}{segments("neutral_unused_vre_mwh", "vre-unused-line")}{segments("excess_mwh", "vre-excess-line")}
        {axisLabelIndices(items.length, Math.floor(plotWidth / 80)).map((index) => { const text = modelTimeText(items[index].timestamp_start); return <text key={index} x={x(index)} y={height - 10} textAnchor={index === 0 ? "start" : index === items.length - 1 ? "end" : "middle"}>{daily ? text.slice(5, 10) : text.slice(5, 16)}</text>; })}
        <text transform={`translate(14 ${topPad + plotHeight / 2}) rotate(-90)`} textAnchor="middle">{t("replay.chart.axis")}</text>
      </g>;
    }}
  </ChartFrame>;
}

export default function CurtailmentView({ run: liveRun, linked = DEFAULT_VRE_LOCATION, onLocationChange }: {
  run?: ModelRun;
  /** R-10 (P1-polish): the year and resolution the URL names, read once when the page opens. */
  linked?: VreLocation;
  /** Writes the page's query (year, resolution) whenever they change. */
  onLocationChange?: (values: Record<string, string | number | null>) => void;
}) {
  const run = useStableRun(liveRun);
  const t = useT();
  const [summary, setSummary] = useState<VreSummary | null>(null); const [timeline, setTimeline] = useState<DispatchTimeline | null>(null);
  const [year, setYear] = useState(0); const [resolution, setResolution] = useState<string>(linked.resolution); const [error, setError] = useState("");
  // R4 R-低10: a Run whose annual results Q14 withholds is not asked for its
  // annual VRE summary (the server answers 409, which the browser logs as an error).
  const vreWithheld = annualResultsWithheld(run);
  useEffect(() => { if (!run || vreWithheld || runPreparing(run)) return; let active = true; void getJson<VreSummary>(`${API}/runs/${run.id}/market/vre-summary`).then((payload) => { if (!active) return; setSummary(payload); setYear((current) => vreYear(payload.years.map((item) => item.year), current || linked.year)); setError(""); }).catch((reason: Error) => { if (active) setError(reason.message); }); return () => { active = false; }; }, [run, vreWithheld, linked.year]);
  useEffect(() => { if (year) onLocationChange?.(vreQueryValues({ year, resolution })); }, [onLocationChange, resolution, year]);
  useEffect(() => { if (!run || !year) return; let active = true; void getJson<DispatchTimeline>(`${API}/runs/${run.id}/market/vre-timeline?year=${year}&resolution=${resolution}&limit=500`).then((payload) => { if (active) setTimeline(payload); }).catch((reason: Error) => { if (active) setError(reason.message); }); return () => { active = false; }; }, [resolution, run, year]);
  if (!run) return <div className="page"><div className="empty-run"><b>{t("vre.noRun.title")}</b><p>{t("vre.noRun.body")}</p></div></div>;
  if (vreWithheld) { const pending = publicationPending(run.result_publication); return <div className="page evidence-page"><PageHeader title={t("vre.title")} actions={<StatusPill tone={pending ? "muted" : "caution"} title={run.result_publication?.message ?? undefined}>{t(pending ? "vre.state.pending" : "vre.state.withheld")}</StatusPill>} /><div className="info-box value-new-control"><b>{t(pending ? "vre.pending.title" : "vre.withheld.title")}</b><br />{pending ? vrePendingText() : vreWithheldText()}</div></div>; }
  const selected = summary?.years.find((item) => item.year === year);
  const maximum = Math.max(1, ...(summary?.years.map((item) => Math.max(item.available_vre_mwh, item.accepted_vre_mwh + (item.pre_balancing_excess_mwh ?? 0))) ?? [1]));
  // R3-21: one unit per KPI group, chosen from the group's largest magnitude.
  const annualEnergy = formatEnergyGroup(summary?.years.map((item) => item.pre_balancing_excess_mwh) ?? []);
  const kpiGroup = selected ? vreKpis(selected, summary) : null;
  // C20: the corrected rule set's column semantics (non-VRE spill, VRE curtailment).
  const labels = vreLabels(summary);
  const kpi = (key: string) => kpiGroup?.kpis.find((item) => item.key === key);
  // Review response (S8): the badge, heading and KPI coverage line follow the backend coverage verdict; "non-annual" only for a non-annual Run.
  const yearCoverage = selected ? vreYearCoverage(selected, summary?.coverage) : null;
  const coverageLine = yearCoverage?.line ?? "";
  return <div className="page evidence-page"><PageHeader title={t("vre.title")} description={t("vre.description")} actions={<Badge tone={yearCoverage?.tone ?? "warn"}>{yearCoverage?.badge ?? t("vre.badge.diagnostic")}</Badge>} />{error && <div className="error-box">{error}</div>}
    {summary && <><section className="panel evidence-panel"><div className="panel-head"><div><span>{t("vre.annual.kicker")}</span><h3>{t("vre.annual.title")}</h3></div><Badge tone="blue">{t("vre.annual.identity")}</Badge></div><div className="annual-vre-chart">{summary.years.map((item) => <button key={item.year} className={item.year === year ? "selected" : ""} onClick={() => setYear(item.year)}><span className="annual-bar"><i className="accepted" style={{ height: `${item.accepted_vre_mwh / maximum * 100}%` }} /><i className="unused" style={{ height: `${item.neutral_unused_vre_mwh / maximum * 100}%` }} /></span><b>{item.year}</b><small>{item.average_unused_vre_fraction == null ? t("vre.annual.noVre") : t("vre.annual.unusedShare", { share: withUnit(formatNumber(item.average_unused_vre_fraction * 100, 1), "%", "") })}</small>{item.pre_balancing_excess_mwh != null && <em>{t("vre.annual.excess", { energy: annualEnergy.format(item.pre_balancing_excess_mwh), label: labels.excess.toLowerCase() })}</em>}</button>)}</div><div className="chart-legend"><span><i style={{ background: "var(--teal)" }} />{t("vre.legend.accepted")}</span><span><i style={{ background: "var(--tech-unused-vre)" }} />{t("vre.legend.unused")}</span></div></section>
      {selected && <section className="panel evidence-panel"><div className="panel-head"><div><span>{t("vre.year.kicker", { year: selected.year })}</span><h3>{yearCoverage?.heading}</h3></div><div className="evidence-controls compact"><label><span>{t("vre.control.year")}</span><select value={year} onChange={(event) => setYear(Number(event.target.value))}>{summary.years.map((item) => <option key={item.year}>{item.year}</option>)}</select></label><label><span>{t("vre.control.timeline")}</span><select value={resolution} onChange={(event) => setResolution(event.target.value)}><option value="daily">{t("vre.control.daily")}</option><option value="weekly">{t("vre.control.weekly")}</option><option value="half_hour">{t("vre.control.halfHour")}</option></select></label></div></div>
        <div className="curtailment-kpis vre-kpis-grouped">{(["available", "accepted", "unused", "excess", "curtailment"] as const).map((key) => { const item = kpi(key)!; const unseparated = (key === "excess" || key === "curtailment") && item.exactMwh == null; return <span key={key}><small>{item.label}</small><b title={item.exactMwh == null ? undefined : `${item.exactMwh} MWh`}>{unseparated ? t("vre.kpi.notSeparate") : item.value ?? "—"}</b>{key === "unused" && <em>{selected.average_unused_vre_fraction == null ? t("vre.annual.noVre") : t("vre.kpi.ofAvailable", { share: withUnit(formatNumber(selected.average_unused_vre_fraction * 100, 2), "%", "") })}</em>}{key === "excess" && <em>{selected.pre_balancing_excess_scope.replaceAll("_", " ")}</em>}<i className="kpi-coverage">{coverageLine}</i></span>; })}</div>
        <div className="destination-strip"><div><small>{kpi("storage")!.label}</small><b>{kpi("storage")!.value ?? "—"}</b><i className="kpi-coverage">{coverageLine}</i></div><div><small>{kpi("export")!.label}</small><b>{kpi("export")!.value ?? "—"}</b><i className="kpi-coverage">{coverageLine}</i></div><div><small>{kpi("flexible")!.label}</small><b>{kpi("flexible")!.value ?? "—"}</b><i className="kpi-coverage">{coverageLine}</i></div><p>{t("vre.destinations.note")}</p></div>
        {timeline && <VreTimelineChart timeline={timeline} excessLabel={labels.excess} />}
        {vreEventGroups(selected).map((group) => <section key={group.key} className="vre-event-group value-new-control" aria-label={t("vre.events.label", { title: group.title })}><h4>{group.title}</h4><p className="vre-event-basis">{group.basisNote}</p>{group.noEvents ? <p className="vre-event-basis">{t("vre.events.none")}</p> : group.events ? <div className="event-summary"><span><small>{t("vre.events.affected")}</small><b>{group.events.affected_periods}</b></span><span><small>{t("vre.events.longest")}</small><b>{formatNumber(group.events.longest_event_hours) === "—" ? "—" : t("vre.events.hours", { value: formatNumber(group.events.longest_event_hours) })}</b></span><span><small>{t("vre.events.peak")}</small><b>{group.events.peak_event_mwh == null ? t("vre.events.notEvaluated") : formatEnergy(group.events.peak_event_mwh)}</b><em>{group.events.peak_event_timestamp ? t("vre.events.peakTime", { time: modelTimeText(group.events.peak_event_timestamp) }) : null}</em></span></div> : <p className="vre-event-basis">{t("vre.events.notSeparate")}</p>}</section>)}<div className="event-summary"><span><small>{t("vre.residual")}</small><b>{withUnit(formatNumber(selected.vre_identity_residual_mwh, 6), "MWh")}</b></span></div>
        <details className="definition-panel"><summary>{t("vre.definitions.title")}</summary><dl><div><dt>{t("vre.definitions.unused")}</dt><dd>{t("vre.definitions.unusedBody")}</dd></div><div><dt>{labels.excess}</dt><dd>{labels.excessDefinition} {t("vre.definitions.scope", { scope: selected.pre_balancing_excess_scope.replaceAll("_", " ") })}</dd></div><div><dt>{labels.curtailment}</dt><dd>{labels.curtailmentDefinition}</dd></div><div><dt>{t("vre.definitions.marginal")}</dt><dd>{selected.marginal_curtailment_reason}</dd></div></dl></details><p className="provenance-line">{t("vre.provenance", { coverage: selected.coverage_status.replaceAll("_", " "), source: summary.source_artifact_sha256 ?? t("vre.hashUnavailable") })}</p>
      </section>}</>}
  </div>;
}
