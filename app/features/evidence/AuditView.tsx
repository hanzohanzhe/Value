"use client";

import { useEffect, useState } from "react";
import type { ModelRun } from "../runs/types";
import type { PlanningProject, PlanningEvent, MarketPeriod, MarketOrder, Artifact } from "./types";
import type { PageResult } from "../shared/pagination";
import { Badge, formatNumber, formatBytes, withUnit } from "../shared/presentation";
import { API_BASE, getJson } from "../shared/api";
import Pager from "../shared/Pager";
import { formatPrice, type PriceBasis } from "../shared/format.ts";
import TraceCoverageNotice from "../market/TraceCoverageNotice";
import ExtensionResultsPanel from "../extensions/ExtensionResultsPanel";

export type AuditTab = "planning" | "market" | "artifacts";
/** initialTab opens Inspect on one tab (Run context notices, spec 2.3); a new nonce reopens it there. */
type AuditProps = { run?: ModelRun; onCreateFullReplayRevision: () => void; initialTab?: { tab: AuditTab; nonce: number } | null };
type PeriodPage = PageResult<MarketPeriod> & { price_basis?: PriceBasis };
type AuditPayload = { planning?: PageResult<PlanningProject>; events?: PageResult<PlanningEvent>; periods?: PeriodPage; artifacts?: Artifact[]; provenance?: Record<string, unknown> };
type AuditRequest = { key: string; loading: boolean; error: string; data?: AuditPayload };
const emptyPage = <T,>(limit: number): PageResult<T> => ({ total: 0, limit, offset: 0, items: [] });

export default function AuditView({ run, onCreateFullReplayRevision, initialTab }: AuditProps) {
  if (!run) return <div className="page"><div className="empty-run"><b>No run selected</b><p>Complete or select a run in the Run centre first.</p></div></div>;
  return <RunAudit key={`${run.id}|${run.input_snapshot_id ?? "unrecorded"}|${initialTab?.nonce ?? 0}`} run={run} onCreateFullReplayRevision={onCreateFullReplayRevision} initialTab={initialTab} />;
}

function RunAudit({ run, onCreateFullReplayRevision, initialTab }: AuditProps & { run: ModelRun }) {
  const API = API_BASE;
  const [tab, setTab] = useState<AuditTab>(initialTab?.tab ?? "planning");
  const [search, setSearch] = useState("");
  const [outcome, setOutcome] = useState("");
  const [planningOffset, setPlanningOffset] = useState(0);
  const [periodOffset, setPeriodOffset] = useState(0);
  const [orderOffset, setOrderOffset] = useState(0);
  const [requestVersion, setRequestVersion] = useState(0);
  const [request, setRequest] = useState<AuditRequest | null>(null);
  const [periodSelection, setPeriodSelection] = useState<{ key: string; value: MarketPeriod | null } | null>(null);
  const [orderRequest, setOrderRequest] = useState<{ key: string; loading: boolean; error: string; page?: PageResult<MarketOrder> } | null>(null);
  const mainKey = JSON.stringify([API, run.id, tab, tab === "planning" ? [search, outcome, planningOffset] : tab === "market" ? periodOffset : null, requestVersion]);
  const payload = request?.key === mainKey ? request.data : undefined;
  const planning = payload?.planning ?? emptyPage<PlanningProject>(25);
  const events = payload?.events ?? emptyPage<PlanningEvent>(25);
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
  const loadMarketPeriods = (offset = 0) => { setPeriodOffset(offset); setOrderOffset(0); setRequestVersion((current) => current + 1); };

  useEffect(() => {
    const controller = new AbortController();
    const isCurrent = () => !controller.signal.aborted;
    const load = async (): Promise<AuditPayload> => {
      if (tab === "planning") {
        const query = new URLSearchParams({ limit: "25", offset: String(planningOffset) });
        if (search) query.set("search", search);
        if (outcome) query.set("outcome", outcome);
        const [projectsPage, eventPage] = await Promise.all([
          getJson<PageResult<PlanningProject>>(`${API}/runs/${run.id}/planning/projects?${query}`, controller.signal),
          getJson<PageResult<PlanningEvent>>(`${API}/runs/${run.id}/planning/events?limit=25&offset=${planningOffset}`, controller.signal),
        ]);
        return { planning: projectsPage, events: eventPage };
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
      if (isCurrent()) setRequest({ key: mainKey, loading: false, error: reason instanceof Error ? reason.message : "Run evidence unavailable" });
    });
    return () => controller.abort();
  }, [API, mainKey, outcome, periodOffset, planningOffset, run.id, search, tab]);

  useEffect(() => {
    if (tab !== "market" || !selectedPeriod || periods.trace_level !== "full") return;
    const controller = new AbortController();
    const isCurrent = () => !controller.signal.aborted;
    void getJson<PageResult<MarketOrder>>(`${API}/runs/${run.id}/market/orders?limit=50&offset=${orderOffset}&year=${selectedPeriod.year}&period=${selectedPeriod.period}`, controller.signal)
      .then((page) => { if (isCurrent()) setOrderRequest({ key: orderKey, loading: false, error: "", page }); })
      .catch((reason: unknown) => { if (isCurrent()) setOrderRequest({ key: orderKey, loading: false, error: reason instanceof Error ? reason.message : "Order evidence unavailable" }); });
    return () => controller.abort();
  }, [API, orderKey, orderOffset, periods.trace_level, run.id, selectedPeriod, tab]);

  return <div className="page"><div className="page-title"><div><span>Run evidence</span><h2>See what changed and why</h2><p>Open the planning record, market periods or output files for this run. Detailed ledgers are loaded only when requested.</p></div><Badge tone={run.status === "completed" ? "good" : "blue"}>{run.status}</Badge></div>
    <div className="audit-tabs" role="tablist">{(["planning", "market", "artifacts"] as const).map((item) => <button role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => { setTab(item); setPlanningOffset(0); setPeriodOffset(0); setOrderOffset(0); }} key={item}>{item === "artifacts" ? "Artifacts & provenance" : item}</button>)}</div>
    {loading && <p className="loading">Loading evidence...</p>}{error && <div className="error-box">{error}</div>}
    {tab === "planning" && <div className="audit-stack"><section className="panel"><div className="panel-head"><div><span>PLANNING PROJECTS</span><h3>{planning.total} durable project records</h3></div></div><form className="filters" onSubmit={(event) => { event.preventDefault(); void loadPlanning(0); }}><label><span>Search name, ID, technology or region</span><input value={search} onChange={(event) => setSearch(event.target.value)} /></label><label><span>Outcome</span><select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option value="">All outcomes</option><option value="active">Active</option><option value="commissioned">Commissioned</option><option value="failed_planning">Failed planning</option><option value="filtered">Filtered</option><option value="outside_scope">Outside scope</option></select></label><button className="primary" type="submit">Apply filters</button></form><div className="table-scroll"><table><thead><tr><th>Project</th><th>Technology</th><th>Stage</th><th>Region</th><th>Capacity</th><th>Completion</th><th>Outcome / reason</th></tr></thead><tbody>{planning.items.map((item) => <tr key={item.project_id}><td><b>{item.name}</b><small>{item.project_id}</small></td><td>{item.technology}</td><td>{item.development_stage}</td><td>{item.region}</td><td>{withUnit(formatNumber(item.capacity_mw), "MW")}</td><td>{item.expected_completion_year ?? "-"}</td><td><Badge tone={item.outcome.includes("failed") || item.outcome === "filtered" ? "warn" : "good"}>{item.outcome}</Badge><small>{item.failure_reason_code || "No exclusion reason"}</small></td></tr>)}</tbody></table></div><Pager page={planning} onPage={(offset) => void loadPlanning(offset)} /></section>
    <section className="panel"><div className="panel-head"><div><span>LIFECYCLE EVENTS</span><h3>How projects changed</h3></div></div><div className="table-scroll"><table><thead><tr><th>Sequence</th><th>Year</th><th>Project</th><th>Event</th><th>Transition</th><th>Reason</th></tr></thead><tbody>{events.items.map((item) => <tr key={item.sequence}><td>{item.sequence}</td><td>{item.year}</td><td><code>{item.project_id}</code></td><td>{item.event_type}</td><td>{item.from_stage || "-"} -&gt; {item.to_stage || "-"}</td><td>{item.reason_code || "-"}</td></tr>)}</tbody></table></div></section></div>}
    {tab === "market" && <div className="audit-stack"><section className="panel"><div className="panel-head"><div><span>PERIOD SUMMARY</span><h3>{periods.total} recorded clearing periods</h3></div><Badge tone={periods.trace_level === "full" ? "good" : "blue"}>{periods.trace_level || "unknown"} trace</Badge></div>{!periods.items.length ? <p className="empty-copy">No period ledger is available for this run.</p> : <><div className="market-grid"><div className="period-list">{periods.items.map((item) => <button className={selectedPeriod?.year === item.year && selectedPeriod?.period === item.period && selectedPeriod?.stage === item.stage ? "selected" : ""} key={`${item.year}-${item.period}-${item.stage}`} onClick={() => { setOrderOffset(0); setSelectedPeriod(item); }}><span>{item.year} / period {item.period}</span><b>{item.stage}</b></button>)}</div>{selectedPeriod && <div className="period-card"><h3>{selectedPeriod.year}, period {selectedPeriod.period}</h3><div className="pipeline-kpis"><span><small>Demand</small><b>{withUnit(formatNumber(selectedPeriod.real_demand_mwh), "MWh")}</b></span><span><small>Accepted supply</small><b>{withUnit(formatNumber(selectedPeriod.accepted_supply_mwh), "MWh")}</b></span><span><small title={selectedPrice?.title}>{selectedPrice?.label}</small><b title={selectedPrice?.title}>{selectedPrice?.value ?? "Not recorded"}</b></span><span><small>Balance residual</small><b>{withUnit(formatNumber(selectedPeriod.energy_balance_residual_mwh, 5), "MWh")}</b></span>{Math.abs(selectedPeriod.compatibility_adjustment_mwh ?? 0) > 1e-9 && <><span><small>Raw VALUE residual</small><b>{withUnit(formatNumber(selectedPeriod.raw_energy_balance_residual_mwh, 5), "MWh")}</b></span><span><small>Compatibility adjustment</small><b>{withUnit(formatNumber(selectedPeriod.compatibility_adjustment_mwh, 5), "MWh")}</b></span></>}</div>{Math.abs(selectedPeriod.compatibility_adjustment_mwh ?? 0) > 1e-9 && <p className="audit-note">The copied VALUE settlement does not expose every secondary allocation as an asset dispatch row in this period. The raw gap is preserved above and is not relabelled as generation or blackout.</p>}</div>}</div><Pager page={{ ...periods, offset: periodOffset }} onPage={(offset) => void loadMarketPeriods(offset)} /></>}</section>
    <section className="panel"><div className="panel-head"><div><span>BID / ORDER EVIDENCE</span><h3>Selected-period orders</h3></div></div>{periods.trace_level !== "full" ? <TraceCoverageNotice traceLevel={periods.trace_level ?? "summary"} bidReplayAvailable={false} onCreateFullReplayRevision={onCreateFullReplayRevision} /> : ordersLoading ? <p className="loading">Loading selected-period orders...</p> : !orders.items.length ? <p className="empty-copy">No orders match the selected period.</p> : <><div className="table-scroll"><table><thead><tr><th>Asset</th><th>Type</th><th>Side</th><th>Offer price</th><th>Offered</th><th>Accepted</th><th>Status</th><th>Reason</th></tr></thead><tbody>{orders.items.map((item) => <tr key={item.order_id}><td>{item.asset_id}</td><td>{item.asset_type}</td><td>{item.side}</td><td>{withUnit(formatNumber(item.offer_price_gbp_per_mwh), "/MWh", "", "£")}</td><td>{withUnit(formatNumber(item.offered_mwh), "MWh")}</td><td>{withUnit(formatNumber(item.accepted_mwh), "MWh")}</td><td>{item.status}</td><td>{item.reason_code}</td></tr>)}</tbody></table></div><Pager page={orders} onPage={setOrderOffset} /></>}</section></div>}
    {tab === "artifacts" && <ExtensionResultsPanel runId={run.id} />}
    {tab === "artifacts" && <div className="artifact-grid"><section className="panel"><div className="panel-head"><div><span>RUN ARTIFACTS</span><h3>Downloadable local evidence</h3></div><Badge>{artifacts.length}</Badge></div><div className="artifact-list">{artifacts.map((item) => <a key={item.id} href={item.download_url}><span><b>{item.name}</b><small>{item.id}</small></span><em>{formatBytes(item.bytes)}</em></a>)}</div></section><section className="panel"><div className="panel-head"><div><span>PROVENANCE</span><h3>Resolved execution identity</h3></div></div>{provenance ? <dl className="provenance">{Object.entries(provenance).filter(([key]) => key !== "data_pack" && key !== "scientific_parameters" && key !== "runtime_options" && key !== "parameter_sources").map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value ?? "-")}</dd></div>)}</dl> : <p className="empty-copy">No provenance record is available.</p>}</section></div>}
  </div>;
}

