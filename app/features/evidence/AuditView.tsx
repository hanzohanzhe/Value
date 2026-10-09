"use client";

import { useEffect, useState } from "react";
import type { ModelRun } from "../runs/types";
import type { PlanningProject, PlanningEvent, MarketPeriod, MarketOrder, Artifact } from "./types";
import type { PageResult } from "../shared/pagination";
import { Badge, formatNumber, formatBytes, withUnit } from "../shared/presentation";
import { API_BASE, getJson } from "../../lib/api.ts";
import Pager from "../shared/Pager";
import { formatPrice, type PriceBasis } from "../shared/format.ts";
import TraceCoverageNotice from "../market/TraceCoverageNotice";
import { stageLabel, statusWord } from "../shared/labels.ts";
import { planningProjectYearNote, planningRecordsTitle, planningRowsPerYear } from "../runs/planningView.ts";
import ExtensionResultsPanel from "../extensions/ExtensionResultsPanel";
import ResidualPanel from "./ResidualPanel";
import { runPreparing } from "../shared/stableRun.ts";
import { useT } from "../../i18n/LocaleProvider";
import { PageHeader } from "../../ui/PageHeader.tsx";
import { Tabs } from "../../ui/Tabs.tsx";
import { DataTable, type DataColumn } from "../../ui/DataTable.tsx";
import { modelPeriodLabel } from "../shared/modelClock.ts";
import { appliedSearch } from "./inspectQuery.ts";

export type AuditTab = "planning" | "market" | "artifacts";
/** initialTab opens Inspect on one tab (Run context notices, spec 2.3); a new nonce reopens it there. */
/** onTabChange (P1 W3): Inspect writes the open tab to its URL (?tab=). */
/** initialSearch / onSearchChange (W4c, F3-19): the applied planning search is in the URL (?q=). */
type AuditProps = { run?: ModelRun; onCreateFullReplayRevision: () => void; initialTab?: { tab: AuditTab; nonce: number } | null; onTabChange?: (tab: AuditTab) => void; initialSearch?: string; onSearchChange?: (search: string) => void };
type PeriodPage = PageResult<MarketPeriod> & { price_basis?: PriceBasis };
type AuditPayload = { planning?: PageResult<PlanningProject>; events?: PageResult<PlanningEvent>; periods?: PeriodPage; artifacts?: Artifact[]; provenance?: Record<string, unknown> };
type AuditRequest = { key: string; loading: boolean; error: string; data?: AuditPayload };
const emptyPage = <T,>(limit: number): PageResult<T> => ({ total: 0, limit, offset: 0, items: [] });

export default function AuditView({ run, onCreateFullReplayRevision, initialTab, onTabChange, initialSearch, onSearchChange }: AuditProps) {
  const t = useT();
  if (!run) return <div className="page"><div className="empty-run"><b>{t("audit.noRun.title")}</b><p>{t("audit.noRun.body")}</p></div></div>;
  return <RunAudit key={`${run.id}|${run.input_snapshot_id ?? "unrecorded"}|${initialTab?.nonce ?? 0}`} run={run} onCreateFullReplayRevision={onCreateFullReplayRevision} initialTab={initialTab} onTabChange={onTabChange} initialSearch={initialSearch} onSearchChange={onSearchChange} />;
}

/** R-D6 (round R1-5): the one-day lesson clears the market only and records no planning ledger. */
export function auditHasPlanning(run: Pick<ModelRun, "mode">): boolean {
  return run.mode !== "value_101_day";
}

function RunAudit({ run, onCreateFullReplayRevision, initialTab, onTabChange, initialSearch = "", onSearchChange }: AuditProps & { run: ModelRun }) {
  const API = API_BASE;
  const t = useT();
  const hasPlanning = auditHasPlanning(run);
  const [tab, setTab] = useState<AuditTab>(initialTab?.tab ?? (hasPlanning ? "planning" : "market"));
  useEffect(() => { onTabChange?.(tab); }, [onTabChange, tab]);
  // F3-19 (spec 6.6): the search box and the outcome are drafts; only the
  // applied filter (Enter or Apply) is requested and written to the URL.
  const [searchDraft, setSearchDraft] = useState(initialSearch);
  const [outcomeDraft, setOutcomeDraft] = useState("");
  const [search, setSearch] = useState(appliedSearch(initialSearch));
  const [outcome, setOutcome] = useState("");
  useEffect(() => { onSearchChange?.(search); }, [onSearchChange, search]);
  const [planningOffset, setPlanningOffset] = useState(0);
  // F3-19: lifecycle events page on their own offset, not the project table's.
  const [eventOffset, setEventOffset] = useState(0);
  const [eventRequest, setEventRequest] = useState<{ key: string; error: string; page?: PageResult<PlanningEvent> } | null>(null);
  const [periodOffset, setPeriodOffset] = useState(0);
  const [orderOffset, setOrderOffset] = useState(0);
  const [requestVersion, setRequestVersion] = useState(0);
  const [request, setRequest] = useState<AuditRequest | null>(null);
  const [periodSelection, setPeriodSelection] = useState<{ key: string; value: MarketPeriod | null } | null>(null);
  const [orderRequest, setOrderRequest] = useState<{ key: string; loading: boolean; error: string; page?: PageResult<MarketOrder> } | null>(null);
  // R5 R-低1: a Run that is still freezing its inputs has no planning or market ledger yet.
  const preparing = runPreparing(run);
  // The planning project index is written when the Run finishes (application.materialize_planning_index).
  const planningPending = ["queued", "snapshotting", "running", "cancel_requested"].includes(run.status);
  const mainKey = JSON.stringify([API, run.id, preparing, planningPending, tab, tab === "planning" ? [search, outcome, planningOffset] : tab === "market" ? periodOffset : null, requestVersion]);
  const payload = request?.key === mainKey ? request.data : undefined;
  const planning: PageResult<PlanningProject> & { record_unit?: string } = payload?.planning ?? emptyPage<PlanningProject>(25);
  const planningPerYear = planningRowsPerYear(planning);
  const eventKey = JSON.stringify([API, run.id, tab === "planning" && hasPlanning && !planningPending, eventOffset]);
  const events = eventRequest?.key === eventKey ? eventRequest.page ?? emptyPage<PlanningEvent>(25) : emptyPage<PlanningEvent>(25);
  // R5 R-低6: the v2 project index records events without stage transitions; the column is shown only when one is recorded.
  const eventTransitions = events.items.some((item) => Boolean(item.from_stage || item.to_stage));
  const periods: PeriodPage = payload?.periods ?? emptyPage<MarketPeriod>(50);
  const artifacts = payload?.artifacts ?? [];
  const provenance = payload?.provenance ?? null;
  const selectedPeriod = periodSelection?.key === mainKey ? periodSelection.value : null;
  // Q6: the period price is labelled by the ledger's declared basis, never as a clearing price by default.
  const selectedPrice = selectedPeriod ? formatPrice(selectedPeriod.clearing_price_gbp_per_mwh, periods.price_basis) : null;
  const orderKey = JSON.stringify([mainKey, selectedPeriod?.year, selectedPeriod?.period, selectedPeriod?.stage, orderOffset]);
  const orders = orderRequest?.key === orderKey ? orderRequest.page ?? emptyPage<MarketOrder>(50) : emptyPage<MarketOrder>(50);
  const ordersLoading = Boolean(selectedPeriod && periods.trace_level === "full" && (orderRequest?.key !== orderKey || orderRequest.loading));
  const loading = request?.key !== mainKey || request.loading;
  const error = (request?.key === mainKey ? request.error : "") || (orderRequest?.key === orderKey ? orderRequest.error : "");
  const setSelectedPeriod = (value: MarketPeriod | null) => setPeriodSelection({ key: mainKey, value });
  const loadPlanning = (offset = 0) => { setPlanningOffset(offset); setRequestVersion((current) => current + 1); };
  const applyFilters = () => { setSearch(appliedSearch(searchDraft)); setOutcome(outcomeDraft); loadPlanning(0); };
  const loadMarketPeriods = (offset = 0) => { setPeriodOffset(offset); setOrderOffset(0); setRequestVersion((current) => current + 1); };

  useEffect(() => {
    const controller = new AbortController();
    const isCurrent = () => !controller.signal.aborted;
    const load = async (): Promise<AuditPayload> => {
      if (tab === "planning" && (!hasPlanning || planningPending)) return { planning: emptyPage<PlanningProject>(25) };
      if (tab === "market" && preparing) return { periods: emptyPage<MarketPeriod>(50) };
      if (tab === "planning") {
        const query = new URLSearchParams({ limit: "25", offset: String(planningOffset) });
        if (search) query.set("search", search);
        if (outcome) query.set("outcome", outcome);
        const projectsPage = await getJson<PageResult<PlanningProject>>(`${API}/runs/${run.id}/planning/projects?${query}`, controller.signal);
        return { planning: projectsPage };
      }
      if (tab === "market") {
        const page = await getJson<PeriodPage>(`${API}/runs/${run.id}/market/periods?limit=50&offset=${periodOffset}`, controller.signal);
        return { periods: page };
      }
      const [files, record] = await Promise.all([
        getJson<{ items: Artifact[] }>(`${API}/runs/${run.id}/artifacts`, controller.signal),
        getJson<Record<string, unknown>>(`${API}/runs/${run.id}/provenance`, controller.signal),
      ]);
      return { artifacts: files.items, provenance: record };
    };
    void load().then((data) => {
      if (!isCurrent()) return;
      setRequest({ key: mainKey, loading: false, error: "", data });
      if (tab === "market") {
        setOrderOffset(0);
        setPeriodSelection({ key: mainKey, value: data.periods?.items[0] ?? null });
      }
    }).catch((reason: unknown) => {
      if (isCurrent()) setRequest({ key: mainKey, loading: false, error: reason instanceof Error ? reason.message : t("audit.error.evidence") });
    });
    return () => controller.abort();
  }, [API, hasPlanning, mainKey, outcome, periodOffset, planningOffset, planningPending, preparing, run.id, search, t, tab]);

  useEffect(() => {
    const [, , active, offset] = JSON.parse(eventKey) as [string, string, boolean, number];
    if (!active) return;
    const controller = new AbortController();
    void getJson<PageResult<PlanningEvent>>(`${API}/runs/${run.id}/planning/events?limit=25&offset=${offset}`, controller.signal)
      .then((page) => { if (!controller.signal.aborted) setEventRequest({ key: eventKey, error: "", page }); })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setEventRequest({ key: eventKey, error: reason instanceof Error ? reason.message : t("audit.error.events") }); });
    return () => controller.abort();
  }, [API, eventKey, run.id, t]);

  useEffect(() => {
    if (tab !== "market" || !selectedPeriod || periods.trace_level !== "full") return;
    const controller = new AbortController();
    const isCurrent = () => !controller.signal.aborted;
    void getJson<PageResult<MarketOrder>>(`${API}/runs/${run.id}/market/orders?limit=50&offset=${orderOffset}&year=${selectedPeriod.year}&period=${selectedPeriod.period}`, controller.signal)
      .then((page) => { if (isCurrent()) setOrderRequest({ key: orderKey, loading: false, error: "", page }); })
      .catch((reason: unknown) => { if (isCurrent()) setOrderRequest({ key: orderKey, loading: false, error: reason instanceof Error ? reason.message : t("audit.error.orders") }); });
    return () => controller.abort();
  }, [API, orderKey, orderOffset, periods.trace_level, run.id, selectedPeriod, t, tab]);

  const tabs = [
    { id: "planning", label: t("inspect.tab.planning") },
    { id: "market", label: t("inspect.tab.market") },
    { id: "artifacts", label: t("inspect.tab.artifacts") },
  ];
  const planningColumns: DataColumn<PlanningProject>[] = [
    ...(planningPerYear ? [{ key: "year", header: t("inspect.col.year"), numeric: true, render: (item: PlanningProject) => item.year ?? "-" }] : []),
    { key: "project", header: t("inspect.col.project"), rowHeader: true, render: (item) => <><b>{item.name}</b>{item.name !== item.project_id && <small>{item.project_id}</small>}</> },
    { key: "technology", header: t("inspect.col.technology"), render: (item) => item.technology },
    { key: "stage", header: t("inspect.col.stage"), render: (item) => stageLabel(item.development_stage) },
    { key: "region", header: t("inspect.col.region"), render: (item) => item.region },
    { key: "capacity", header: t("inspect.col.capacity"), numeric: true, render: (item) => withUnit(formatNumber(item.capacity_mw), "MW") },
    { key: "completion", header: t("inspect.col.completion"), numeric: true, render: (item) => item.expected_completion_year ?? "-" },
    { key: "outcome", header: t("inspect.col.outcome"), render: (item) => <><Badge tone={item.outcome.includes("failed") || item.outcome === "filtered" ? "warn" : "good"}>{stageLabel(item.outcome)}</Badge><small>{item.failure_reason_code || t("audit.noExclusion")}</small></> },
  ];
  const eventColumns: DataColumn<PlanningEvent>[] = [
    { key: "sequence", header: t("inspect.col.sequence"), numeric: true, render: (item) => item.sequence },
    { key: "year", header: t("inspect.col.year"), numeric: true, render: (item) => item.year },
    { key: "project", header: t("inspect.col.project"), render: (item) => <code>{item.project_id}</code> },
    { key: "event", header: t("inspect.col.event"), render: (item) => stageLabel(item.event_type) },
    ...(eventTransitions ? [{ key: "transition", header: t("inspect.col.transition"), render: (item: PlanningEvent) => <>{item.from_stage ? stageLabel(item.from_stage) : "-"} -&gt; {item.to_stage ? stageLabel(item.to_stage) : "-"}</> }] : []),
    { key: "reason", header: t("inspect.col.reason"), render: (item) => item.reason_code || "-" },
  ];
  const orderColumns: DataColumn<MarketOrder>[] = [
    { key: "asset", header: t("inspect.col.asset"), rowHeader: true, render: (item) => item.asset_id },
    { key: "type", header: t("inspect.col.type"), render: (item) => item.asset_type },
    { key: "side", header: t("inspect.col.side"), render: (item) => item.side },
    { key: "price", header: t("inspect.col.offerPrice"), numeric: true, render: (item) => withUnit(formatNumber(item.offer_price_gbp_per_mwh), "/MWh", "", "£") },
    { key: "offered", header: t("inspect.col.offered"), numeric: true, render: (item) => withUnit(formatNumber(item.offered_mwh), "MWh") },
    { key: "accepted", header: t("inspect.col.accepted"), numeric: true, render: (item) => withUnit(formatNumber(item.accepted_mwh), "MWh") },
    { key: "status", header: t("inspect.col.status"), render: (item) => item.status },
    { key: "reason", header: t("inspect.col.reason"), render: (item) => item.reason_code },
  ];
  const periodText = (item: { year: number; period: number }) => modelPeriodLabel(item.year, item.period) ?? t("audit.periodFallback", { year: item.year, period: item.period });
  const eventsError = eventRequest?.key === eventKey ? eventRequest.error : "";
  return <div className="page inspect-page">
    <PageHeader title={t("inspect.title")} description={t("inspect.description")} actions={<Badge tone={run.status === "completed" ? "good" : "blue"} title={run.status}>{statusWord(run.status)}</Badge>} />
    <Tabs className="inspect-tabs" label={t("inspect.tabs")} tabs={tabs} value={tab} onChange={(item) => { setTab(item as AuditTab); setPlanningOffset(0); setEventOffset(0); setPeriodOffset(0); setOrderOffset(0); }}>
    {loading && <p className="loading">{t("audit.loading")}</p>}{error && <div className="error-box">{error}</div>}
    {preparing && tab !== "artifacts" && <div className="info-box" role="status"><b>{t("audit.preparing.title")}</b><br />{t("audit.preparing.body")}</div>}
    {!preparing && planningPending && tab === "planning" && <div className="info-box" role="status"><b>{t("audit.planningPending.title")}</b><br />{t("audit.planningPending.body")}</div>}
    {tab === "planning" && !hasPlanning && <div className="info-box audit-no-planning" role="status"><b>{t("audit.noPlanning.title")}</b><br />{t("audit.noPlanning.body")}</div>}
    {tab === "planning" && hasPlanning && <div className="audit-stack"><section className="panel"><div className="panel-head"><div><span>{t("audit.planning.kicker")}</span><h3>{planningRecordsTitle(planning)}</h3>{planningPerYear && <p>{planningProjectYearNote()}</p>}</div></div>
      <form className="filters" onSubmit={(event) => { event.preventDefault(); applyFilters(); }}><label><span>{t("audit.filter.search")}</span><input value={searchDraft} maxLength={200} onChange={(event) => setSearchDraft(event.target.value)} /></label><label><span>{t("audit.filter.outcome")}</span><select value={outcomeDraft} onChange={(event) => setOutcomeDraft(event.target.value)}><option value="">{t("audit.filter.all")}</option><option value="active">{t("audit.filter.active")}</option><option value="commissioned">{t("audit.filter.commissioned")}</option><option value="failed_planning">{t("audit.filter.failed")}</option><option value="filtered">{t("audit.filter.filtered")}</option><option value="outside_scope">{t("audit.filter.outside")}</option></select></label><button className="primary" type="submit">{t("audit.filter.apply")}</button></form>
      {(searchDraft.trim() !== search || outcomeDraft !== outcome) && <p className="inspect-filter-pending" role="status">{t("inspect.filter.pending")}</p>}
      <DataTable caption={t("inspect.planning.caption")} captionHidden columns={planningColumns} rows={planning.items} rowKey={(item) => `${item.project_id}:${item.year ?? ""}`} />
      <Pager page={planning} onPage={(offset) => void loadPlanning(offset)} /></section>
    <section className="panel"><div className="panel-head"><div><span>{t("audit.events.kicker")}</span><h3>{t("audit.events.title")}</h3><p>{t("inspect.events.total", { count: events.total })}</p></div></div>
      {eventsError && <div className="error-box">{eventsError}</div>}
      <DataTable caption={t("inspect.events.caption")} captionHidden columns={eventColumns} rows={events.items} rowKey={(item) => String(item.sequence)} />
      <Pager page={{ ...events, offset: eventOffset }} onPage={setEventOffset} /></section></div>}
    {tab === "market" && <div className="audit-stack"><ResidualPanel balance={run.energy_balance} /><section className="panel"><div className="panel-head"><div><span>{t("audit.periods.kicker")}</span><h3>{t("audit.periods.title", { count: periods.total })}</h3></div><Badge tone={periods.trace_level === "full" ? "good" : "blue"}>{t("audit.periods.trace", { level: periods.trace_level || t("audit.periods.unknown") })}</Badge></div>{!periods.items.length ? <p className="empty-copy">{t("audit.periods.none")}</p> : <><div className="market-grid"><div className="period-list">{periods.items.map((item) => <button type="button" className={selectedPeriod?.year === item.year && selectedPeriod?.period === item.period && selectedPeriod?.stage === item.stage ? "selected" : ""} key={`${item.year}-${item.period}-${item.stage}`} aria-pressed={selectedPeriod?.year === item.year && selectedPeriod?.period === item.period && selectedPeriod?.stage === item.stage} onClick={() => { setOrderOffset(0); setSelectedPeriod(item); }}><span>{periodText(item)}</span><b>{item.stage}</b><small>{t("inspect.period.ordinal", { year: item.year, period: item.period })}</small></button>)}</div>{selectedPeriod && <div className="period-card"><h3>{periodText(selectedPeriod)}</h3><div className="pipeline-kpis"><span><small>{t("audit.period.demand")}</small><b>{withUnit(formatNumber(selectedPeriod.real_demand_mwh), "MWh")}</b></span><span><small>{t("audit.period.supply")}</small><b>{withUnit(formatNumber(selectedPeriod.accepted_supply_mwh), "MWh")}</b></span><span><small title={selectedPrice?.title}>{selectedPrice?.label}</small><b title={selectedPrice?.title}>{selectedPrice?.value ?? t("audit.period.notRecorded")}</b></span><span><small>{t("audit.period.residual")}</small><b>{withUnit(formatNumber(selectedPeriod.energy_balance_residual_mwh, 5), "MWh")}</b></span>{Math.abs(selectedPeriod.compatibility_adjustment_mwh ?? 0) > 1e-9 && <><span><small>{t("audit.period.rawResidual")}</small><b>{withUnit(formatNumber(selectedPeriod.raw_energy_balance_residual_mwh, 5), "MWh")}</b></span><span><small>{t("audit.period.adjustment")}</small><b>{withUnit(formatNumber(selectedPeriod.compatibility_adjustment_mwh, 5), "MWh")}</b></span></>}</div>{Math.abs(selectedPeriod.compatibility_adjustment_mwh ?? 0) > 1e-9 && <p className="audit-note">{t("audit.period.adjustmentNote")}</p>}</div>}</div><Pager page={{ ...periods, offset: periodOffset }} onPage={(offset) => void loadMarketPeriods(offset)} /></>}</section>
    <section className="panel"><div className="panel-head"><div><span>{t("audit.orders.kicker")}</span><h3>{t("audit.orders.title")}</h3></div></div>{periods.trace_level !== "full" ? <TraceCoverageNotice traceLevel={periods.trace_level ?? "summary"} bidReplayAvailable={false} onCreateFullReplayRevision={onCreateFullReplayRevision} /> : ordersLoading ? <p className="loading">{t("audit.orders.loading")}</p> : !orders.items.length ? <p className="empty-copy">{t("audit.orders.none")}</p> : <><DataTable caption={t("inspect.orders.caption")} captionHidden columns={orderColumns} rows={orders.items} rowKey={(item) => item.order_id} /><Pager page={orders} onPage={setOrderOffset} /></>}</section></div>}
    {tab === "artifacts" && <ExtensionResultsPanel runId={run.id} />}
    {tab === "artifacts" && <div className="artifact-grid"><section className="panel"><div className="panel-head"><div><span>{t("audit.artifacts.kicker")}</span><h3>{t("audit.artifacts.title")}</h3></div><Badge>{artifacts.length}</Badge></div><div className="artifact-list">{artifacts.map((item) => <a key={item.id} href={item.download_url}><span><b>{item.name}</b><small>{item.id}</small></span><em>{formatBytes(item.bytes)}</em></a>)}</div></section><section className="panel"><div className="panel-head"><div><span>{t("audit.provenance.kicker")}</span><h3>{t("audit.provenance.title")}</h3></div></div>{provenance ? <dl className="provenance">{Object.entries(provenance).filter(([key]) => key !== "data_pack" && key !== "scientific_parameters" && key !== "runtime_options" && key !== "parameter_sources").map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value ?? "-")}</dd></div>)}</dl> : <p className="empty-copy">{t("audit.provenance.none")}</p>}</section></div>}
    </Tabs>
  </div>;
}
