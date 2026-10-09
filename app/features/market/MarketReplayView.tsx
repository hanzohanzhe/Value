"use client";

// Market replay (moved verbatim from app/page.tsx in P1 W3; route /runs/[runId]/replay).
import { useEffect, useRef, useState } from "react";
import { API_BASE, getJson } from "../../lib/api.ts";
import { Badge, formatNumber, withUnit } from "../shared/presentation";
import { formatQuantity } from "../shared/format.ts";
import { modelClockSuffix, modelPeriodLabel, modelTimeLabel, modelTimeText } from "../shared/modelClock.ts";
import { useT } from "../../i18n/LocaleProvider";
import { ChartFrame, type LegendItem } from "../../ui/ChartFrame.tsx";
import { DataTable, type DataColumn } from "../../ui/DataTable.tsx";
import { PageHeader } from "../../ui/PageHeader.tsx";
import { linearScale, niceTicks } from "../../ui/chartScale.ts";
import { StatusPill, ValueState } from "../shared/Callout";
import { runPreparing, useStableRun } from "../shared/stableRun.ts";
import { isResultCoverage } from "../shared/coverageView.ts";
import type { PageResult } from "../shared/pagination";
import type { ModelRun } from "../runs/types";
import { shortfallDisplay } from "../workspace/runValidation.ts";
import type { AuctionView, DispatchTimeline, MarketCapability, StoragePeriodRow } from "./marketTypes.ts";
import { EMPTY_DISPATCH_MESSAGES, acceptedSupplyNote, axisLabelIndices, bucketPrice, defaultResolution, emptyDispatchReason, replaySeriesStyle, stackSupply, stackedTechnologies, stressBuckets, technologyLabel } from "./dispatchView.ts";
import { acceptedCell, storageLedgerNote } from "./auctionOffers.ts";
import ReplayExportPanel from "./ReplayExportPanel";
import StressEventList from "./StressEventList";
import TraceCoverageNotice from "./TraceCoverageNotice";
import { replacePageQuery } from "../shell/routes.ts";
import { linkedReplayWindow } from "./replayLocation.ts";
import "./market-replay.css";

const API = API_BASE;

/** The legend of a set of technologies (spec 1.2: palette colours, a pattern where colours repeat). */
function technologyLegend(technologies: readonly string[]): LegendItem[] {
  return technologies.map((technology) => ({ key: technology, label: technologyLabel(technology), ...replaySeriesStyle(technology) }));
}

type DispatchRow = { key: string; time: string; demand: number; supply: number; stress: number | null | undefined; byTechnology: Map<string, number> };

/**
 * Spec 2.1 (W4c): final physical dispatch of the window as stacked bars in a
 * ChartFrame - pixel coordinates (12 px text at any width), the technology
 * palette with patterns, an HTML legend and the same data as a table. The
 * demand line, the stress band (A2) and the selected bucket are drawn as before.
 */
export function DispatchChart({ timeline, selectedPeriod, onSelect, width: fixedWidth }: { timeline: DispatchTimeline; selectedPeriod: number; onSelect: (period: number) => void; width?: number }) {
  const t = useT();
  const items = timeline.items;
  // R3-02: only flows whose role is supply are stacked, summed by technology across zones.
  const stacks = items.map((item) => stackSupply(item));
  const technologies = stackedTechnologies(items);
  const stressed = new Set(stressBuckets(items));
  const totals = stacks.map((stack) => stack.reduce((sum, segment) => sum + segment.energy_mwh, 0));
  const maximum = Math.max(1, ...totals, ...items.map((item) => item.real_demand_mwh));
  const ticks = niceTicks(0, maximum, 4);
  const top = Math.max(maximum, ticks.at(-1) ?? maximum);
  const halfHourly = items.every((item) => item.period_count <= 1);
  const tickText = (stamp: string) => { const text = modelTimeText(stamp); return halfHourly ? text.slice(11, 16) : text.slice(5, 10); };
  const legend: LegendItem[] = [
    ...technologyLegend(technologies),
    { key: "demand", label: t("replay.chart.demand"), color: "var(--ink)", line: "solid" },
    ...(stressed.size ? [{ key: "stress", label: t("replay.chart.stress"), color: "var(--amber)" }] : []),
  ];
  const rows: DispatchRow[] = items.map((item, index) => ({ key: `${item.period_start}-${item.period_end}`, time: modelTimeLabel(item.timestamp_start), demand: item.real_demand_mwh, supply: totals[index], stress: item.stress_periods, byTechnology: new Map(stacks[index].map((segment) => [segment.technology, segment.energy_mwh])) }));
  const columns: DataColumn<DispatchRow>[] = [
    { key: "time", header: t("replay.chart.col.start"), rowHeader: true, render: (row) => row.time },
    { key: "demand", header: t("replay.chart.col.demand"), numeric: true, render: (row) => withUnit(formatNumber(row.demand), "MWh") },
    { key: "supply", header: t("replay.chart.col.supply"), numeric: true, render: (row) => withUnit(formatNumber(row.supply), "MWh") },
    ...technologies.map((technology) => ({ key: `tech-${technology}`, header: technologyLabel(technology), numeric: true, render: (row: DispatchRow) => row.byTechnology.has(technology) ? withUnit(formatNumber(row.byTechnology.get(technology)), "MWh") : "—" })),
    { key: "stress", header: t("replay.chart.col.stress"), numeric: true, render: (row) => typeof row.stress === "number" ? row.stress : <ValueState state="not_recorded" /> },
  ];
  const first = items[0] ? modelTimeLabel(items[0].timestamp_start) : "";
  const last = items.at(-1) ? modelTimeLabel(items.at(-1)!.timestamp_end) : "";
  return <ChartFrame width={fixedWidth} className="evidence-chart dispatch-chart" title={t("replay.chart.title")} summary={t("replay.chart.summary", { count: items.length, first, last })} legend={legend} table={{ caption: t("replay.chart.caption"), columns, rows, rowKey: (row) => row.key }}>
    {({ width, height, fill }) => {
      const left = 60; const right = 12; const topPad = 14; const bottom = 30;
      const plotWidth = Math.max(1, width - left - right); const plotHeight = Math.max(1, height - topPad - bottom);
      const y = linearScale([0, top], [topPad + plotHeight, topPad]);
      const band = plotWidth / Math.max(items.length, 1);
      const barWidth = Math.max(1, band - Math.min(2, band * 0.15));
      const x = (index: number) => left + index * band;
      const demandPoints = items.map((item, index) => `${x(index) + barWidth / 2},${y(item.real_demand_mwh)}`).join(" ");
      return <g>
        {ticks.map((tick) => <g key={tick}><line className="v-chart__grid" x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} /><text x={left - 8} y={y(tick) + 4} textAnchor="end">{formatQuantity(tick, 3)}</text></g>)}
        <text transform={`translate(14 ${topPad + plotHeight / 2}) rotate(-90)`} textAnchor="middle">{t("replay.chart.axis")}</text>
        {items.map((item, index) => {
          let cumulative = 0;
          const periodSelected = item.period_start <= selectedPeriod && selectedPeriod <= item.period_end;
          return <g key={`${item.period_start}-${item.period_end}`} className={periodSelected ? "selected-bucket" : "dispatch-bucket"} onClick={() => onSelect(item.period_start)}>
            <title>{`${modelTimeLabel(item.timestamp_start)} · ${withUnit(formatNumber(item.real_demand_mwh), "MWh")}`}</title>
            <rect x={x(index)} y={topPad} width={Math.max(barWidth, 2)} height={plotHeight} fill="transparent" />
            {stacks[index].map((segment) => { const start = cumulative; cumulative += segment.energy_mwh; return <rect key={segment.technology} className="dispatch-segment" x={x(index)} y={y(cumulative)} width={barWidth} height={Math.max(y(start) - y(cumulative), 0)} fill={fill(segment.technology)} />; })}
            {stressed.has(index) && <rect className="stress-band" x={x(index)} y={topPad - 6} width={Math.max(barWidth, 2)} height={4}><title>{t("replay.chart.stressTitle", { count: item.stress_periods, shortfall: withUnit(formatNumber(item.shortfall_mwh), "MWh") })}</title></rect>}
            {periodSelected && <line x1={x(index)} x2={x(index)} y1={topPad} y2={topPad + plotHeight} className="selection-line" />}
          </g>;
        })}
        <polyline points={demandPoints} className="demand-line" />
        {axisLabelIndices(items.length, Math.floor(plotWidth / 72)).map((index) => <text key={index} x={x(index) + barWidth / 2} y={height - 10} textAnchor="middle">{tickText(items[index].timestamp_start)}</text>)}
      </g>;
    }}
  </ChartFrame>;
}

/** Spec 3.4 / M-D1: accepted MWh of one offer; a storage tranche reads its own row of the storage offer ledger. */
function AcceptedOfferCell({ offer }: { offer: AuctionView["offers"][number] }) {
  const t = useT();
  const cell = acceptedCell(offer);
  return <span title={cell.title}>{cell.mwh == null ? t("replay.offers.notSeparate") : `${withUnit(formatNumber(cell.mwh), "MWh")}${cell.suffix}`}</span>;
}

type MeritRow = { key: string; order: number; asset: string; start: number; end: number; price: number };

/** Spec 2.1 (W4c): the selected period's merit order in a ChartFrame (offer blocks by technology, requirement and marginal price lines, the curve as a table). */
export function MeritOrderChart({ auction, width: fixedWidth }: { auction: AuctionView; width?: number }) {
  const t = useT();
  const total = Math.max(1, auction.offers.reduce((sum, offer) => sum + offer.offered_mwh, 0), auction.requirement_mwh);
  const maximumPrice = Math.max(1, ...auction.offers.map((offer) => offer.offer_price_gbp_per_mwh));
  const priceTicks = niceTicks(0, maximumPrice, 3);
  const topPrice = Math.max(maximumPrice, priceTicks.at(-1) ?? maximumPrice);
  const positioned = auction.offers.map((offer, index) => ({ offer, start: auction.offers.slice(0, index).reduce((sum, item) => sum + item.offered_mwh, 0) }));
  const technologies = [...new Set(auction.offers.map((offer) => offer.technology))];
  const legend: LegendItem[] = [
    ...technologyLegend(technologies),
    { key: "requirement", label: t("replay.merit.requirement"), color: "var(--ink)", line: "dashed" },
    ...(auction.marginal_offer_price_gbp_per_mwh != null ? [{ key: "marginal", label: t("replay.merit.marginal"), color: "var(--red)", line: "dashed" as const }] : []),
  ];
  const rows: MeritRow[] = positioned.map(({ offer, start }) => ({ key: offer.offer_id ?? `${offer.asset_id}-${offer.execution_order}`, order: offer.execution_order + 1, asset: offer.asset_id, start, end: start + offer.offered_mwh, price: offer.offer_price_gbp_per_mwh }));
  const columns: DataColumn<MeritRow>[] = [
    { key: "order", header: t("replay.merit.col.order"), numeric: true, render: (row) => row.order },
    { key: "asset", header: t("replay.merit.col.asset"), rowHeader: true, render: (row) => row.asset },
    { key: "from", header: t("replay.merit.col.from"), numeric: true, render: (row) => withUnit(formatNumber(row.start), "MWh") },
    { key: "to", header: t("replay.merit.col.to"), numeric: true, render: (row) => withUnit(formatNumber(row.end), "MWh") },
    { key: "price", header: t("replay.merit.col.price"), numeric: true, render: (row) => withUnit(formatNumber(row.price), "/MWh", "", "£") },
  ];
  return <ChartFrame width={fixedWidth} className="merit-chart" title={t("replay.merit.title", { stage: auction.stage })} summary={t("replay.merit.summary", { stage: auction.stage, count: auction.offers.length, requirement: withUnit(formatNumber(auction.requirement_mwh), "MWh") })} legend={legend} table={{ caption: t("replay.merit.caption"), columns, rows, rowKey: (row) => row.key }}>
    {({ width, height, fill }) => {
      const left = 60; const right = 12; const topPad = 14; const bottom = 30;
      const plotWidth = Math.max(1, width - left - right); const plotHeight = Math.max(1, height - topPad - bottom);
      const x = linearScale([0, total], [left, left + plotWidth]);
      const y = linearScale([0, topPrice], [topPad + plotHeight, topPad]);
      return <g>
        {priceTicks.map((tick) => <g key={tick}><line className="v-chart__grid" x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} /><text x={left - 8} y={y(tick) + 4} textAnchor="end">{formatQuantity(tick, 3)}</text></g>)}
        {positioned.map(({ offer, start }) => <rect key={offer.offer_id ?? `${offer.asset_id}-${offer.execution_order}`} className="merit-offer" x={x(start)} y={y(offer.offer_price_gbp_per_mwh)} width={Math.max(x(start + offer.offered_mwh) - x(start), 1)} height={Math.max(topPad + plotHeight - y(offer.offer_price_gbp_per_mwh), 0)} fill={fill(offer.technology)}><title>{t("replay.merit.offeredTitle", { asset: offer.asset_id, energy: withUnit(formatNumber(offer.offered_mwh), "MWh") })}</title></rect>)}
        <line x1={x(auction.requirement_mwh)} x2={x(auction.requirement_mwh)} y1={topPad} y2={topPad + plotHeight} className="requirement-line" />
        {auction.marginal_offer_price_gbp_per_mwh != null && <line x1={left} x2={left + plotWidth} y1={y(auction.marginal_offer_price_gbp_per_mwh)} y2={y(auction.marginal_offer_price_gbp_per_mwh)} className="price-line" />}
        <text x={left} y={height - 10}>0</text><text x={left + plotWidth} y={height - 10} textAnchor="end">{t("replay.merit.offeredAxis", { energy: withUnit(formatNumber(total), "MWh") })}</text>
        <text transform={`translate(14 ${topPad + plotHeight / 2}) rotate(-90)`} textAnchor="middle">{t("replay.merit.axis")}</text>
      </g>;
    }}
  </ChartFrame>;
}

/** The merit-order table (spec 2: DataTable; numeric columns right-aligned). */
function offerColumns(t: ReturnType<typeof useT>): DataColumn<AuctionView["offers"][number]>[] {
  return [
    { key: "order", header: t("replay.offers.col.order"), numeric: true, render: (offer) => offer.execution_order + 1 },
    { key: "asset", header: t("replay.offers.col.asset"), rowHeader: true, render: (offer) => <b>{offer.asset_id}</b> },
    { key: "technology", header: t("replay.offers.col.technology"), render: (offer) => <span title={offer.asset_type ? t("replay.offers.modelClass", { type: offer.asset_type }) : undefined}>{technologyLabel(offer.technology)}</span> },
    { key: "offer", header: t("replay.offers.col.offer"), numeric: true, render: (offer) => withUnit(formatNumber(offer.offer_price_gbp_per_mwh), "/MWh", "", "£") },
    { key: "offered", header: t("replay.offers.col.offered"), numeric: true, render: (offer) => withUnit(formatNumber(offer.offered_mwh), "MWh") },
    { key: "accepted", header: t("replay.offers.col.accepted"), numeric: true, render: (offer) => <AcceptedOfferCell offer={offer} /> },
    { key: "evidence", header: t("replay.offers.col.evidence"), render: (offer) => offer.acceptance_granularity.replaceAll("_", " ") },
  ];
}

/** Spec 3.1: the selected window as recorded. Shortfall comes from the backend (A2); it is never derived here. */
function WindowSummary({ bucket, timeline }: { bucket: DispatchTimeline["items"][number]; timeline: DispatchTimeline }) {
  const t = useT();
  const price = bucketPrice(bucket, timeline);
  const shortfall = bucket.shortfall_mwh;
  const stressPeriods = bucket.stress_periods;
  // F-P04-1: a lower-bound shortfall reads "≥ x MWh", with the upper bound on hover.
  const shortfallShown = shortfallDisplay(shortfall, bucket.shortfall_basis, bucket.shortfall_upper_mwh);
  const mwh = (value: number | null | undefined) => value == null ? <ValueState state="not_recorded" /> : `${withUnit(formatNumber(value), "MWh")}`;
  return <div className="selected-period-strip window-summary">
    <span className="window-summary-wide"><small>{t("replay.summary.window")}</small><b>{modelTimeText(bucket.timestamp_start)} → {modelTimeText(bucket.timestamp_end)}{modelClockSuffix(timeline.timezone)}</b>{timeline.clock_note && <em className="window-clock-note">{timeline.clock_note}</em>}</span>
    <span><small>{t("replay.summary.demand")}</small><b>{mwh(bucket.real_demand_mwh)}</b></span>
    <span><small>{t("replay.summary.acceptedSupply")}</small><b>{mwh(bucket.accepted_supply_mwh)}</b><em className="window-clock-note" title={timeline.accepted_supply_boundary?.formula ?? undefined}>{acceptedSupplyNote(timeline)}</em></span>
    <span className={typeof shortfall === "number" && shortfall > 0 ? "shortfall-positive" : ""}><small>{t("replay.summary.shortfall")}</small><b title={shortfallShown?.title}>{shortfallShown == null ? <ValueState state="not_recorded" title={t("replay.summary.noStressLedger")} /> : shortfallShown.text}</b>{typeof stressPeriods === "number" && stressPeriods > 0 && <StatusPill tone="caution">{t("replay.summary.stressPeriods", { count: stressPeriods })}</StatusPill>}</span>
    <span><small>{t("replay.summary.storageCharge")}</small><b>{mwh(bucket.storage_charge_mwh)}</b></span>
    <span><small>{t("replay.summary.storageDischarge")}</small><b>{mwh(bucket.storage_discharge_mwh)}</b></span>
    <span className="window-summary-wide"><small title={price.title}>{price.label}</small><b title={price.title}>{price.value ?? <ValueState state="not_recorded" />}</b></span>
  </div>;
}

/** A window to open Market replay at (a Replay jump from the network reliability list, spec 4.4). */
export type ReplayTarget = { runId: string; year: number; periodFrom: number; nonce: number };


export default function MarketReplayView({ run: liveRun, onCreateFullReplayRevision, initialWindow, focusStressEvents, onStressEventsFocused }: { run?: ModelRun; onCreateFullReplayRevision: () => void; initialWindow?: ReplayTarget | null; focusStressEvents?: boolean; onStressEventsFocused?: () => void }) {
  // R5 R-低1: reload on the Run's identity, status or years, not on every poll.
  const run = useStableRun(liveRun);
  const preparing = runPreparing(run);
  const t = useT();
  const [capabilities, setCapabilities] = useState<MarketCapability | null>(null);
  const [timeline, setTimeline] = useState<DispatchTimeline | null>(null);
  const [auction, setAuction] = useState<AuctionView | null>(null);
  const [storageRows, setStorageRows] = useState<StoragePeriodRow[]>([]);
  const [year, setYear] = useState(0); const [period, setPeriod] = useState(0);
  const [stage, setStage] = useState("ahead");
  // Spec 2.1 / R3-10: a 24-hour window opens at half-hour detail, never as one daily bar.
  const [resolution, setResolution] = useState<string>(defaultResolution("24_hours"));
  const [windowKind, setWindowKind] = useState<"24_hours" | "168_hours">("24_hours");
  const target = initialWindow && run && initialWindow.runId === run.id ? initialWindow : null;
  const [periodFrom, setPeriodFrom] = useState(target?.periodFrom ?? 0);
  const [timelineOffset, setTimelineOffset] = useState(0);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(Boolean(run));
  const windowPeriods = windowKind === "24_hours" ? 48 : 336;
  const periodTo = periodFrom + windowPeriods - 1;
  const bidReplayAvailable = capabilities?.bid_replay_available ?? capabilities?.auction_replay ?? false;
  // P1 W3: a period named by the URL is selected once its window has loaded.
  const linkedPeriod = useRef<number | null>(null);
  useEffect(() => { if (!run || preparing) return; let active = true; void getJson<MarketCapability>(`${API}/runs/${run.id}/market/capabilities`).then((payload) => { if (!active) return; const linked = target ? null : linkedReplayWindow(window.location.search); const opened = target ? { year: target.year, from: target.periodFrom } : linked; const known = Boolean(opened && payload.years.includes(opened.year)); linkedPeriod.current = known && linked ? linked.period : null; setCapabilities(payload); setYear(known && opened ? opened.year : payload.years[0] ?? 0); setStage(linked && payload.auction_stages?.some((item) => item.stage === linked.stage) ? linked.stage : payload.auction_stages?.[0]?.stage ?? "ahead"); setPeriodFrom(known && opened ? opened.from : 0); setTimelineOffset(0); setError(""); }).catch((reason: Error) => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [preparing, run, target]);
  useEffect(() => { if (!run || !year) return; let active = true; const query = new URLSearchParams({ year: String(year), resolution, period_from: String(periodFrom), period_to: String(periodTo), limit: "96", offset: String(timelineOffset) }); void getJson<DispatchTimeline>(`${API}/runs/${run.id}/market/dispatch?${query}`).then((payload) => { if (!active) return; setTimeline(payload); const wanted = linkedPeriod.current; linkedPeriod.current = null; setPeriod(wanted != null && wanted >= periodFrom && wanted <= periodTo ? wanted : payload.items[0]?.period_start ?? periodFrom); }).catch((reason: Error) => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [periodFrom, periodTo, resolution, run, timelineOffset, year]);
  // P1 W3 (spec 5.1, principle 0.3): the replayed year, period and stage are in the URL.
  useEffect(() => { if (run && year > 0 && timeline) replacePageQuery({ year, period, from: periodFrom === period ? null : periodFrom, stage: bidReplayAvailable ? stage : null }); }, [bidReplayAvailable, period, periodFrom, run, stage, timeline, year]);
  useEffect(() => { if (!run || !year || !bidReplayAvailable || !stage) return; let active = true; void getJson<AuctionView>(`${API}/runs/${run.id}/market/auction?year=${year}&period=${period}&stage=${stage}`).then((payload) => { if (active) setAuction(payload); }).catch(() => { if (active) setAuction(null); }); return () => { active = false; }; }, [bidReplayAvailable, period, run, stage, year]);
  useEffect(() => { if (!run || !year || !capabilities?.storage_state) return; let active = true; void getJson<PageResult<StoragePeriodRow>>(`${API}/runs/${run.id}/market/storage?year=${year}&period=${period}&limit=100`).then((payload) => { if (active) setStorageRows(payload.items); }).catch(() => { if (active) setStorageRows([]); }); return () => { active = false; }; }, [capabilities?.storage_state, period, run, year]);
  if (!run) return <div className="page"><div className="empty-run"><b>{t("replay.noRun.title")}</b><p>{t("replay.noRun.body")}</p></div></div>;
  if (preparing) return <div className="page"><div className="empty-run"><b>{t("replay.preparing.title")}</b><p>{t("replay.preparing.body")}</p></div></div>;
  const selected = timeline?.items.find((item) => item.period_start <= period && period <= item.period_end);
  const dispatchEmpty = timeline ? emptyDispatchReason(timeline, capabilities) : null;
  // F3-18 (spec 6.5): a period reads as its UTC model time, the ordinal stays beside it.
  const periodHours = timeline?.period_hours && timeline.period_hours > 0 ? timeline.period_hours : 0.5;
  const at = (value: number) => modelPeriodLabel(year, value, periodHours) ?? String(value);
  return <div className="page evidence-page replay-page"><PageHeader title={t("replay.title")} description={t("replay.description")} actions={<Badge tone={bidReplayAvailable ? "good" : "blue"}>{t("replay.trace", { level: capabilities?.trace_level ?? t("replay.trace.loading") })}</Badge>} />
    {loading && <p className="loading">{t("replay.loading")}</p>}{error && <div className="error-box">{error}</div>}
    {capabilities && !capabilities.period_summary && <div className="info-box">{capabilities.missing_reason}</div>}
    {capabilities && <TraceCoverageNotice traceLevel={capabilities.trace_level} bidReplayAvailable={bidReplayAvailable} onCreateFullReplayRevision={onCreateFullReplayRevision} />}
    {capabilities?.period_summary && <><section className="panel evidence-panel"><div className="evidence-controls"><label><span>{t("replay.control.year")}</span><select value={year} onChange={(event) => { setYear(Number(event.target.value)); setPeriodFrom(0); setTimelineOffset(0); }}>{capabilities.years.map((value) => <option key={value}>{value}</option>)}</select></label><label><span>{t("replay.control.window")}</span><select value={windowKind} onChange={(event) => { const kind = event.target.value as "24_hours" | "168_hours"; setWindowKind(kind); setResolution(defaultResolution(kind)); setTimelineOffset(0); }}><option value="24_hours">{t("replay.control.hours24")}</option><option value="168_hours">{t("replay.control.hours168")}</option></select></label><label><span>{t("replay.control.firstPeriod")}</span><input type="number" min={0} step={1} value={periodFrom} aria-describedby="replay-first-period-time" onChange={(event) => { setPeriodFrom(Math.max(0, Number(event.target.value))); setTimelineOffset(0); }} /><small id="replay-first-period-time" className="period-time">{at(periodFrom)}</small></label><label><span>{t("replay.control.resolution")}</span><select value={resolution} onChange={(event) => { setResolution(event.target.value); setTimelineOffset(0); }}><option value="daily">{t("replay.control.daily")}</option><option value="weekly">{t("replay.control.weekly")}</option><option value="half_hour">{t("replay.control.halfHour")}</option></select></label><label><span>{t("replay.control.selectedPeriod")}</span><input type="number" min={periodFrom} max={periodTo} step={1} value={period} aria-describedby="replay-selected-period-time" onChange={(event) => setPeriod(Number(event.target.value))} /><small id="replay-selected-period-time" className="period-time">{at(period)}</small></label></div>
      <div className="bounded-window-controls"><button className="secondary" disabled={periodFrom === 0} onClick={() => { setPeriodFrom(Math.max(0, periodFrom - windowPeriods)); setTimelineOffset(0); }}>{t("replay.window.previous")}</button><span>{t("replay.window.range", { from: at(periodFrom), to: at(periodTo), first: periodFrom, last: periodTo, offset: timelineOffset })}</span><button className="secondary" onClick={() => { setPeriodFrom(periodFrom + windowPeriods); setTimelineOffset(0); }}>{t("replay.window.next")}</button></div>
      {timeline && dispatchEmpty && <div className="info-box dispatch-empty" role="status"><b>{t("replay.empty.title")}</b><br />{EMPTY_DISPATCH_MESSAGES[dispatchEmpty]} <code>{dispatchEmpty}</code></div>}
      {timeline && !dispatchEmpty && <><DispatchChart timeline={timeline} selectedPeriod={period} onSelect={setPeriod} /><div className="bounded-page-controls"><button className="text-button" disabled={timelineOffset === 0} onClick={() => setTimelineOffset(Math.max(0, timelineOffset - timeline.limit))}>{t("replay.page.previous")}</button><span>{t("replay.page.buckets", { shown: timeline.items.length, total: timeline.total })}</span><button className="text-button" disabled={timelineOffset + timeline.items.length >= timeline.total} onClick={() => setTimelineOffset(timelineOffset + timeline.limit)}>{t("replay.page.next")}</button></div></>}
      {selected && timeline && <WindowSummary bucket={selected} timeline={timeline} />}
    </section>
    {year > 0 && <StressEventList key={`${run.id}-${year}`} runId={run.id} year={year} coverage={isResultCoverage(run.result_coverage) ? run.result_coverage : null} computedPeriods={run.diagnostic?.periods_per_year ?? run.run_policy?.periods_per_year ?? null} focus={focusStressEvents} onFocused={onStressEventsFocused} onReplay={(eventYear, from) => { setYear(eventYear); setPeriodFrom(from); setTimelineOffset(0); if (typeof window !== "undefined") window.scrollTo({ top: 0 }); }} />}
    <section className="panel evidence-panel"><div className="panel-head"><div><span>{t("replay.auction.kicker")}</span><h3>{t("replay.auction.title")}</h3></div>{bidReplayAvailable ? <label className="inline-select"><span>{t("replay.auction.stage")}</span><select value={stage} onChange={(event) => setStage(event.target.value)}>{capabilities.auction_stages.map((item) => <option value={item.stage} key={item.stage}>{item.stage} · {item.order_detail.replaceAll("_", " ")}</option>)}</select></label> : <Badge tone="warn">{t("replay.auction.noBidReplay")}</Badge>}</div>
      {!bidReplayAvailable ? <div className="info-box">{t("replay.auction.noBidDetail")}</div> : !auction ? <div className="info-box">{t("replay.auction.noAuction", { stage, time: at(period), period })}</div> : <><div className="auction-layout"><MeritOrderChart auction={auction} /><div className="auction-facts"><span><small>{t("replay.auction.requirement")}</small><b>{withUnit(formatNumber(auction.requirement_mwh), "MWh")}</b></span><span><small>{t("replay.auction.marginal")}</small><b>{auction.marginal_offer_price_gbp_per_mwh == null ? t("replay.auction.notDefined") : `${withUnit(formatNumber(auction.marginal_offer_price_gbp_per_mwh), "/MWh", "", "£")}`}</b></span><span><small>{t("replay.auction.information")}</small><b>{auction.information_scope}</b></span><span><small>{t("replay.auction.acceptance")}</small><b>{auction.offer_acceptance_coverage.replaceAll("_", " ")}</b></span></div></div><DataTable caption={t("replay.offers.caption", { stage: auction.stage, time: at(period) })} columns={offerColumns(t)} rows={auction.offers} rowKey={(offer) => offer.offer_id ?? `${offer.asset_id}-${offer.execution_order}`} />{storageLedgerNote(auction.offers) ? <p className="storage-ledger-note">{storageLedgerNote(auction.offers)}</p> : null}<p className="provenance-line">{t("replay.auction.provenance", { input: auction.input_sha256, source: auction.source_artifact_sha256 ?? t("replay.auction.hashUnavailable") })}</p></>}
      {capabilities.storage_state && <div className="storage-period-panel"><header><div><small>{t("replay.storage.title", { time: at(period), period })}</small><b>{capabilities.storage_cost_module_id ?? t("replay.storage.noPolicy")}</b></div><Badge>{t("replay.storage.assets", { count: storageRows.length })}</Badge></header>{storageRows.length ? <div>{storageRows.map((row) => <span key={row.asset_id}><b>{row.asset_id}</b><small>{t("replay.storage.soc", { soc: formatNumber(row.state_of_charge_mwh), capacity: withUnit(formatNumber(row.energy_capacity_mwh), "MWh") })}</small><em>{t("replay.storage.flows", { charge: formatNumber(row.charge_mwh), discharge: withUnit(formatNumber(row.discharge_mwh), "MWh"), power: withUnit(formatNumber(row.power_capacity_mw), "MW") })}</em></span>)}</div> : <p>{t("replay.storage.none")}</p>}</div>}
    </section><ReplayExportPanel key={`${run.id}-${year}-${period}`} runId={run.id} years={capabilities.years} selectedYear={year} selectedPeriod={period} /></>}
  </div>;
}
