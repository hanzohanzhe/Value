"use client";

import { useEffect, useMemo, useState } from "react";
import CurtailmentWaterfall from "./CurtailmentWaterfall";
import NetworkZoneMap from "./NetworkZoneMap";
import ReplayExportPanel from "../market/ReplayExportPanel";
import TraceCoverageNotice from "../market/TraceCoverageNotice";
import {
  type AnnualBrief,
  type ResultPage,
  type SolverValidationSummary,
  type VRECurtailmentAnnual,
  type VRECurtailmentDetailRow,
  type VRECurtailmentValues,
  type ZonalCapabilities,
  type ZonalRun,
  type ZonalSolverContract,
  boundedPeriodQuery,
  fetchNetworkJson,
  formatNetworkMoney,
  formatNetworkNumber,
  formatOptionalNetworkNumber,
  isBuiltinZonalSolverContract,
  isSolverValidationSummary,
  isZonalSolverContract,
  numberValue,
  scaled,
  toNumber,
} from "./networkRedispatch";
import { RELIABILITY_PAGE_SIZE, reliabilityQuery, reliabilityRow, replayWindowStart, type ReliabilityEvent } from "./reliabilityView.ts";
import { Callout, StatusPill } from "../shared/Callout";
import { reasonMessage } from "../shared/reasonCodes.ts";
import { annualTotalsPublishable, coveragePill, coverageReasonText, isResultCoverage, reliabilityEmptyText } from "../shared/coverageView.ts";
import "./network-coverage.css";

type Row = Record<string, unknown>;
type Tab = "overview" | "period" | "reliability" | "evidence";
const technologyOptions = ["", "Solar", "Onshore wind", "Offshore wind"] as const;
const curtailmentDetailLimit = 250;
const solverDiagnosticLimit = 100;

type FrozenSolverContractState = {
  selection: string;
  status: "success" | "error";
  contract?: ZonalSolverContract;
};

type SolverDisplay = {
  badge: string;
  tone: "good" | "warn" | "blue";
  stackValidated: boolean;
};

function successfulTerminalRun(run: ZonalRun): boolean {
  return run.status === "completed"
    || (run.status === "archived" && run.archived_from_status === "completed");
}

function solverDisplay(
  run: ZonalRun,
  frozenContractStatus: "loading" | "success" | "error",
  frozenContract: ZonalSolverContract | undefined,
  summaryStatus: "missing" | "invalid" | "valid",
  summary: SolverValidationSummary | null | undefined,
): SolverDisplay {
  if (!successfulTerminalRun(run)) return { badge: "Run not successfully completed", tone: "warn", stackValidated: false };
  if (frozenContractStatus === "loading") return { badge: "Loading frozen solver contract", tone: "blue", stackValidated: false };
  if (frozenContractStatus === "error" || !frozenContract) return { badge: "Frozen contract unavailable", tone: "warn", stackValidated: false };
  if (summaryStatus === "invalid") return { badge: "Solver validation status unavailable", tone: "warn", stackValidated: false };
  if (summaryStatus === "missing" || !summary) return { badge: "Solver evidence not recorded", tone: "blue", stackValidated: false };
  const evidenceErrors = summary.evidence_errors;
  if (
    summary.evidence_status === "invalid"
    || evidenceErrors.length > 0
    || summary.study_status === "solver_evidence_invalid"
  ) return { badge: "Solver evidence invalid", tone: "warn", stackValidated: false };
  if (summary.evidence_status === "not_recorded"
    || summary.annual_status === "NOT_RECORDED"
    || summary.study_status === "NOT_RECORDED") {
    return { badge: "Solver evidence not recorded", tone: "blue", stackValidated: false };
  }
  if (!isBuiltinZonalSolverContract(frozenContract)) return { badge: "Custom solver contract", tone: "warn", stackValidated: false };
  const supportedStackStatus = (summary.annual_status === "GO" && summary.study_status === "GO")
    || (summary.annual_status === "GO_WITH_NUMERICAL_WARNING" && summary.study_status === "GO_WITH_NUMERICAL_WARNING");
  const stackValidated = supportedStackStatus
    && summary.method === frozenContract.method
    && summary.solver_contract_version === frozenContract.contract_version
    && summary.solver_stack_validation_status === "builtin_validated_baseline"
    && summary.solver_validated === true
    && summary.row_count > 0
    && summary.unvalidated_periods === 0
    && summary.inherited_unvalidated === false;
  if (summary.annual_status === "COMPLETED_WITH_NUMERICAL_WARNING"
    || summary.study_status === "COMPLETED_WITH_NUMERICAL_WARNING"
    || summary.unvalidated_periods > 0) {
    return { badge: "Completed with numerical warning", tone: "warn", stackValidated: false };
  }
  if (summary.annual_status === "GO_WITH_NUMERICAL_WARNING"
    || summary.study_status === "GO_WITH_NUMERICAL_WARNING"
    || summary.warning_periods > 0) {
    return {
      badge: stackValidated
        ? "Validated with numerical warning"
        : "Numerical warning — not solver validated",
      tone: "warn",
      stackValidated,
    };
  }
  if (summary.solver_stack_validation_status === "solver_stack_not_yet_validated"
    || !summary.solver_validated
    || summary.inherited_unvalidated) {
    return { badge: "Validation pending", tone: "blue", stackValidated: false };
  }
  const validated = stackValidated
    && summary.evidence_status === "valid"
    && evidenceErrors.length === 0
    && summary.annual_status === "GO"
    && summary.study_status === "GO"
    && summary.warning_periods === 0
    && summary.unvalidated_periods === 0;
  return validated
    ? { badge: "Validated evidence", tone: "good", stackValidated: true }
    : { badge: "Solver validation status unavailable", tone: "warn", stackValidated: false };
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <article><small>{label}</small><b>{value}</b>{note && <span>{note}</span>}</article>;
}

function BadgeLike({ children, tone }: { children: React.ReactNode; tone: "good" | "warn" | "blue" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="network-empty">{children}</div>;
}

function optionalMwh(value: number | null | undefined): string {
  const formatted = formatOptionalNetworkNumber(value);
  return formatted == null ? "Unavailable" : `${formatted} MWh`;
}

function signedMwh(value: number | null | undefined): string {
  const formatted = formatOptionalNetworkNumber(value == null ? value : Math.abs(value));
  if (formatted == null) return "Unavailable";
  if (value === 0) return "0 MWh";
  return `${value! < 0 ? "−" : "+"}${formatted} MWh`;
}

function directionalMwh(value: number | null | undefined, direction: "addition" | "avoidance"): string {
  const formatted = formatOptionalNetworkNumber(value);
  return formatted == null ? "Unavailable" : `${direction === "avoidance" ? "−" : "+"}${formatted} MWh`;
}

function curtailmentAvailabilityMessage(attribution: VRECurtailmentAnnual): string {
  if (attribution.attribution_status === "legacy_partial") {
    return "Legacy result — avoided curtailment was not calculated";
  }
  const messages: Record<string, string> = {
    module_does_not_provide_counterfactual_snapshot:
      "Attribution unavailable — the selected PSM does not provide matched VRE counterfactual snapshots.",
    selected_balancing_does_not_provide_final_zonal_dispatch:
      "Attribution unavailable — the selected balancing module does not provide final zonal dispatch evidence.",
    attribution_evidence_not_recorded:
      "Attribution unavailable — this run did not record v2 curtailment evidence.",
    attribution_period_set_incomplete:
      "Attribution unavailable — the recorded accounting and attribution period sets do not match.",
    attribution_period_status_invalid:
      "Attribution unavailable — the recorded period evidence did not pass reconciliation.",
  };
  return messages[attribution.reason_code ?? ""]
    ?? `Attribution unavailable — ${String(attribution.reason_code ?? attribution.attribution_status).replaceAll("_", " ")}.`;
}

function DataTable({ rows, columns }: { rows: Row[]; columns: [string, string, (value: unknown, row: Row) => string][] }) {
  return <div className="table-scroll network-table"><table><thead><tr>{columns.map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={`${String(row.year)}-${String(row.period)}-${String(row.zone_id ?? row.boundary_id ?? row.asset_id ?? row.event_id ?? index)}`}>{columns.map(([key, , render]) => <td key={key}>{render(row[key], row)}</td>)}</tr>)}</tbody></table></div>;
}

export default function NetworkRedispatchView({
  run,
  apiOrigin,
  onOpenMarket,
  onCreateFullReplayRevision,
  onOpenRun,
  onRerun,
  sourceStudyMutable,
  onReplay,
  onOpenInspect,
}: {
  run?: ZonalRun;
  apiOrigin: string;
  /** Open Market replay at a stress / lost-load event (spec 4.4). */
  onReplay?: (year: number, periodFrom: number) => void;
  onOpenInspect?: () => void;
  onOpenMarket: () => void;
  onCreateFullReplayRevision: () => void;
  onOpenRun: () => void;
  onRerun: () => Promise<void>;
  sourceStudyMutable: boolean;
}) {
  const runId = run?.id ?? "";
  const base = run ? `${apiOrigin}/api/runs/${run.id}/network-redispatch` : "";
  const isKnownCopperplate = run?.modules?.balancing === "value-copperplate-balancing";
  const [capabilities, setCapabilities] = useState<ZonalCapabilities | null>(null);
  const [annual, setAnnual] = useState<AnnualBrief | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [year, setYear] = useState<number | null>(null);
  const [period, setPeriod] = useState<number | null>(null);
  const [periods, setPeriods] = useState<Row[]>([]);
  const [periodWindow, setPeriodWindow] = useState<48 | 336>(48);
  const [periodFrom, setPeriodFrom] = useState(0);
  const [periodOffset, setPeriodOffset] = useState(0);
  const [periodPage, setPeriodPage] = useState({ total: 0, hasMore: false });
  const [zones, setZones] = useState<Row[]>([]);
  const [boundaries, setBoundaries] = useState<Row[]>([]);
  const [resources, setResources] = useState<Row[]>([]);
  const [settlements, setSettlements] = useState<Row[]>([]);
  const [reliabilityOffset, setReliabilityOffset] = useState(0);
  const [reliabilityPage, setReliabilityPage] = useState<{ selection: string; status: "success" | "error"; items: ReliabilityEvent[]; total: number; hasMore: boolean; error: string }>({ selection: "", status: "success", items: [], total: 0, hasMore: false, error: "" });
  const [solver, setSolver] = useState<Row[]>([]);
  const [solverDiagnosticOffset, setSolverDiagnosticOffset] = useState(0);
  const [solverDiagnostics, setSolverDiagnostics] = useState<{
    selection: string;
    status: "success" | "error";
    items: Row[];
    total: number;
    hasMore: boolean;
    error: string;
  }>({ selection: "", status: "success", items: [], total: 0, hasMore: false, error: "" });
  const [frozenSolverContract, setFrozenSolverContract] = useState<FrozenSolverContractState>({
    selection: "",
    status: "error",
  });
  const [technology, setTechnology] = useState<(typeof technologyOptions)[number]>("");
  const [curtailmentDetailOffset, setCurtailmentDetailOffset] = useState(0);
  const [curtailmentDetailPage, setCurtailmentDetailPage] = useState<{
    selection: string;
    status: "success" | "error";
    items: VRECurtailmentDetailRow[];
    total: number;
    hasMore: boolean;
    error: string;
  }>({ selection: "", status: "success", items: [], total: 0, hasMore: false, error: "" });
  const [loading, setLoading] = useState(Boolean(run));
  const [probeError, setProbeError] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) return;
    let active = true;
    void fetchNetworkJson<unknown>(`${apiOrigin}/api/runs/${runId}/artifacts/input-snapshot/project.json`)
      .then((project) => {
        if (!active) return;
        const contract = typeof project === "object" && project !== null
          ? (project as Record<string, unknown>).solver_contract
          : undefined;
        if (!isZonalSolverContract(contract)) {
          setFrozenSolverContract({ selection: runId, status: "error" });
          return;
        }
        setFrozenSolverContract({ selection: runId, status: "success", contract });
      })
      .catch(() => {
        if (active) setFrozenSolverContract({ selection: runId, status: "error" });
      });
    return () => { active = false; };
  }, [apiOrigin, runId]);

  useEffect(() => {
    if (!run) return;
    Promise.all([
      fetchNetworkJson<ZonalCapabilities>(`${base}/capabilities`),
      fetchNetworkJson<AnnualBrief>(`${base}/annual`),
    ]).then(([nextCapabilities, nextAnnual]) => {
      setCapabilities(nextCapabilities);
      setAnnual(nextAnnual);
      setYear(nextAnnual.years[0]?.year ?? nextCapabilities.years[0] ?? null);
      setProbeError("");
    }).catch((reason: Error) => setProbeError(reason.message)).finally(() => setLoading(false));
  }, [base, run]);

  useEffect(() => {
    if (!base || year == null || !capabilities) return;
    const periodTo = periodFrom + periodWindow - 1;
    const periodQuery = boundedPeriodQuery({ year, periodFrom, periodTo, limit: 48, offset: periodOffset });
    Promise.all([
      fetchNetworkJson<ResultPage>(`${base}/periods?${periodQuery}`),
    ]).then(([periodPage]) => {
      setPeriods(periodPage.items);
      setPeriodPage({ total: periodPage.total, hasMore: periodPage.has_more });
      setPeriod(Number(periodPage.items[0]?.period ?? periodFrom));
    }).catch((reason: Error) => setError(reason.message));
  }, [base, year, capabilities, periodFrom, periodOffset, periodWindow]);

  // F3-07: the reliability list covers the whole year (no period window), one
  // page at a time; a newer request aborts the older one.
  useEffect(() => {
    if (tab !== "reliability" || !base || year == null || !capabilities) return;
    const selection = `${base}:${year}:${reliabilityOffset}`;
    const controller = new AbortController();
    void fetch(`${base}/reliability?${reliabilityQuery(year, reliabilityOffset)}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Reliability events unavailable");
        return payload as ResultPage<ReliabilityEvent>;
      })
      .then((page) => { if (!controller.signal.aborted) setReliabilityPage({ selection, status: "success", items: page.items, total: page.total, hasMore: page.has_more, error: "" }); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setReliabilityPage({ selection, status: "error", items: [], total: 0, hasMore: false, error: reason.message }); });
    return () => controller.abort();
  }, [base, capabilities, reliabilityOffset, tab, year]);

  useEffect(() => {
    if (!base || year == null || period == null || !capabilities) return;
    const suffix = `year=${year}&period=${period}&limit=1000`;
    Promise.all([
      fetchNetworkJson<ResultPage>(`${base}/zones?${suffix}`),
      fetchNetworkJson<ResultPage>(`${base}/boundaries?${suffix}`),
      fetchNetworkJson<ResultPage>(`${base}/resources?${suffix}`),
      fetchNetworkJson<ResultPage>(`${base}/solver?${suffix}`),
      capabilities.bid_replay_available
        ? fetchNetworkJson<ResultPage>(`${base}/settlements?${suffix}`)
        : Promise.resolve({ items: [] } as unknown as ResultPage),
    ]).then(([zonePage, boundaryPage, resourcePage, solverPage, settlementPage]) => {
      setZones(zonePage.items); setBoundaries(boundaryPage.items);
      setResources(resourcePage.items); setSolver(solverPage.items);
      setSettlements(settlementPage.items);
    }).catch((reason: Error) => setError(reason.message));
  }, [base, year, period, capabilities]);

  useEffect(() => {
    if (tab !== "evidence" || !base || year == null || !capabilities?.available_views.includes("solver-diagnostics")) return;
    const query = new URLSearchParams({
      year: String(year),
      limit: String(solverDiagnosticLimit),
      offset: String(solverDiagnosticOffset),
    });
    const selection = `${base}:${year}:${solverDiagnosticOffset}`;
    let active = true;
    void fetchNetworkJson<ResultPage>(`${base}/solver-diagnostics?${query}`)
      .then((page) => {
        if (!active) return;
        setSolverDiagnostics({
          selection,
          status: "success",
          items: page.items,
          total: page.total,
          hasMore: page.has_more,
          error: "",
        });
      })
      .catch((reason: Error) => {
        if (!active) return;
        setSolverDiagnostics({ selection, status: "error", items: [], total: 0, hasMore: false, error: reason.message });
      });
    return () => { active = false; };
  }, [base, capabilities, solverDiagnosticOffset, tab, year]);

  useEffect(() => {
    const attribution = annual?.years.find((item) => item.year === year)?.vre_curtailment;
    if (!base || year == null || attribution?.attribution_status !== "reconciled") return;
    const selection = `${year}:${technology || "Total VRE"}:${curtailmentDetailOffset}`;
    const query = new URLSearchParams({
      year: String(year),
      limit: String(curtailmentDetailLimit),
      offset: String(curtailmentDetailOffset),
    });
    if (technology) query.set("technology", technology);
    let active = true;
    void fetchNetworkJson<ResultPage<VRECurtailmentDetailRow>>(`${base}/curtailment-detail?${query}`)
      .then((page) => {
        if (!active) return;
        setCurtailmentDetailPage({
          selection,
          status: "success",
          items: page.items,
          total: page.total,
          hasMore: page.has_more,
          error: "",
        });
      })
      .catch((reason: Error) => {
        if (!active) return;
        setCurtailmentDetailPage({
          selection,
          status: "error",
          items: [],
          total: 0,
          hasMore: false,
          error: reason.message,
        });
      });
    return () => { active = false; };
  }, [annual, base, curtailmentDetailOffset, technology, year]);

  const annualRow = annual?.years.find((item) => item.year === year);
  const coverage = isResultCoverage(annual?.coverage) ? annual?.coverage : null;
  const coverageBadge = coveragePill(coverage);
  const annualPublished = annualTotalsPublishable(coverage);
  const reliabilitySelection = year == null ? "" : `${base}:${year}:${reliabilityOffset}`;
  const reliabilityState = reliabilityPage.selection === reliabilitySelection
    ? reliabilityPage
    : { status: "loading" as const, items: [] as ReliabilityEvent[], total: 0, hasMore: false, error: "" };
  const attribution = annualRow?.vre_curtailment;
  const selectedAttribution: VRECurtailmentValues | undefined = technology
    ? attribution?.by_technology.find((item) => item.technology === technology)
    : attribution;
  const selectedZoneAttribution = attribution?.by_zone_technology.filter(
    (item) => !technology || item.technology === technology,
  ) ?? [];
  const curtailmentDetailSelection = year == null
    ? ""
    : `${year}:${technology || "Total VRE"}:${curtailmentDetailOffset}`;
  const curtailmentDetailState = curtailmentDetailPage.selection === curtailmentDetailSelection
    ? curtailmentDetailPage
    : { status: "loading" as const, items: [], total: 0, hasMore: false, error: "" };
  const selectedPeriod = periods.find((item) => Number(item.period) === period);
  const storageRows = useMemo(() => resources.filter((row) => Boolean(numberValue(row, "final_soc_mwh") || numberValue(row, "charge_mwh") || numberValue(row, "discharge_mwh"))), [resources]);
  const rawSolverSummary = annual?.solver_validation_summary ?? capabilities?.solver_validation_summary;
  const solverSummary = isSolverValidationSummary(rawSolverSummary) ? rawSolverSummary : undefined;
  const solverSummaryStatus = rawSolverSummary == null ? "missing" : solverSummary ? "valid" : "invalid";
  const frozenContractState = frozenSolverContract.selection === runId
    ? frozenSolverContract
    : { selection: runId, status: "loading" as const, contract: undefined };
  const display = run
    ? solverDisplay(run, frozenContractState.status, frozenContractState.contract, solverSummaryStatus, solverSummary)
    : { badge: "Solver evidence not recorded", tone: "blue" as const, stackValidated: false };
  const customSolverContract = frozenContractState.status === "success"
    && Boolean(frozenContractState.contract)
    && !isBuiltinZonalSolverContract(frozenContractState.contract);
  const solverStatusLabel = frozenContractState.status === "loading"
    ? "Loading frozen solver contract — not solver validated"
    : frozenContractState.status === "error" || !frozenContractState.contract
      ? "Frozen solver contract unavailable — not solver validated"
      : customSolverContract
        ? "Custom contract — not yet solver validated"
        : display.stackValidated
          ? "Built-in validated baseline"
          : "Solver stack not yet validated";
  const completedWithNumericalWarning = solverSummary?.study_status === "COMPLETED_WITH_NUMERICAL_WARNING"
    || solverSummary?.annual_status === "COMPLETED_WITH_NUMERICAL_WARNING"
    || (solverSummary?.unvalidated_periods ?? 0) > 0;
  const hasNumericalWarning = completedWithNumericalWarning
    || solverSummary?.study_status === "GO_WITH_NUMERICAL_WARNING"
    || solverSummary?.annual_status === "GO_WITH_NUMERICAL_WARNING"
    || (solverSummary?.warning_periods ?? 0) > 0;
  const solverDiagnosticSelection = year == null ? "" : `${base}:${year}:${solverDiagnosticOffset}`;
  const solverDiagnosticState = solverDiagnostics.selection === solverDiagnosticSelection
    ? solverDiagnostics
    : { selection: solverDiagnosticSelection, status: "loading" as const, items: [], total: 0, hasMore: false, error: "" };

  if (!run) return <div className="page"><Empty><b>No run selected</b><p>Select a completed zonal Study in Runs.</p></Empty></div>;
  if (loading) return <div className="page"><Empty><b>Loading network results…</b></Empty></div>;
  if (!capabilities) return <div className="page"><div className="page-title"><div><span>Network results</span><h2>Network &amp; redispatch</h2><p>{isKnownCopperplate ? "This run used copperplate balancing. It has no zonal congestion or redispatch ledger." : "No zonal network evidence is available for this run."}</p></div></div><Empty><b>{isKnownCopperplate ? "Copperplate run" : "Zonal evidence unavailable"}</b><p>{isKnownCopperplate ? "The network evidence probe found no zonal ledger, as expected for the built-in copperplate balancing module." : `The selected balancing module did not expose a readable zonal ledger${probeError ? `: ${probeError}` : "."}`}</p></Empty></div>;

  return <div className="page network-workspace">
    <div className="page-title"><div><span>Physical delivery after the GB market</span><h2>Network &amp; redispatch</h2><p>Follow the national ahead schedule into final zonal dispatch, congestion, curtailment, storage movement and observed supply shortfalls.</p></div><div className="network-run-id"><small>Run</small><code>{run.id}</code><span>{capabilities?.network_pack_id || "network evidence pending"}</span></div></div>

    {capabilities && <section className="network-coverage-banner value-new-control" aria-label="Annual coverage"><StatusPill tone={coverageBadge.tone} title={coverageBadge.title}>{coverageBadge.text}</StatusPill><span>{coverageReasonText(coverage)}</span></section>}
    {error && <div className="error-box"><b>Network evidence unavailable: </b>{error}</div>}
    {run.status === "failed" && <section className="panel network-failure"><div><span>Immutable failed run</span><h3>{run.error_code ?? "Solver evidence retained"}</h3><p>{run.error ?? "The declared input and failure artefacts remain attached to this run."}</p><small>{sourceStudyMutable ? "A copperplate fallback is a new run, never a continuation under different physics." : "Restore the source Study before creating a copperplate fallback Run."}</small></div><div><button className="secondary" onClick={onOpenRun}>Open evidence &amp; audit export</button><button className="secondary" disabled={!sourceStudyMutable} onClick={() => void onRerun()}>Rerun as copperplate<br /><small>重新以铜板模式运行</small></button></div></section>}

    {capabilities && <>
      <section className="network-method-strip">
        <article><span>01</span><b>National ahead market</b><small>One GB bid-at-cost schedule and national settlement.</small></article>
        <i>→</i>
        <article><span>02</span><b>Final physical redispatch</b><small>Pay-as-bid adjustments satisfy zonal balances and computational corridors.</small></article>
        <aside><b>Scope boundary</b><span>Lossless transport representation; not a security analysis.</span></aside>
      </section>

      <section className={`solver-validation-summary ${display.tone === "warn" ? "warning" : ""}`} aria-label="Solver validation summary">
        <header><div><span>Numerical solver evidence</span><h3>Solver validation summary</h3></div><BadgeLike tone={display.tone}>{display.badge}</BadgeLike></header>
        <div className="solver-summary-grid">
          <article><small>Contract status</small><b>{solverStatusLabel}</b></article>
          <article><small>Method</small><b>{solverSummary?.method ?? "not recorded"}</b></article>
          <article><small>Contract version</small><b>{solverSummary?.solver_contract_version ?? "not recorded"}</b></article>
          <article><small>Maximum validated-ceiling use</small><b>{solverSummary ? `${formatNetworkNumber(solverSummary.maximum_validated_ceiling_use * 100, 1)}%` : "not recorded"}</b></article>
          <article><small>Warning count</small><b>{solverSummary ? `${solverSummary.warning_periods} warning ${solverSummary.warning_periods === 1 ? "period" : "periods"}` : "not recorded"}</b></article>
          <article><small>Unvalidated count</small><b>{solverSummary ? `${solverSummary.unvalidated_periods} unvalidated ${solverSummary.unvalidated_periods === 1 ? "period" : "periods"}` : "not recorded"}</b></article>
        </div>
        {hasNumericalWarning && display.badge !== "Completed with numerical warning" && <p className="solver-settings-error">{completedWithNumericalWarning ? "Completed with numerical warning" : "Numerical warning recorded"}</p>}
        {capabilities.available_views.includes("solver-diagnostics") && <a className="secondary solver-diagnostic-export" href={`${base}/export?view=solver-diagnostics&format=jsonl&limit=1000&offset=0`}>Export solver diagnostics</a>}
      </section>

      <div className="network-controls"><label><span>Model year</span><select value={year ?? ""} onChange={(event) => { setYear(Number(event.target.value)); setPeriodFrom(0); setPeriodOffset(0); setCurtailmentDetailOffset(0); setSolverDiagnosticOffset(0); setReliabilityOffset(0); }}>{capabilities.years.map((item) => <option key={item}>{item}</option>)}</select></label><label><span>Period window</span><select value={periodWindow} onChange={(event) => { setPeriodWindow(Number(event.target.value) as 48 | 336); setPeriodOffset(0); }}><option value={48}>24 hours</option><option value={336}>168 hours</option></select></label><label><span>First period</span><input type="number" min={0} value={periodFrom} onChange={(event) => { setPeriodFrom(Math.max(0, Number(event.target.value))); setPeriodOffset(0); }} /></label><div className="network-tabs" role="tablist">{(["overview", "period", "reliability", "evidence"] as Tab[]).map((item) => <button role="tab" aria-selected={tab === item} className={tab === item ? "active" : ""} onClick={() => setTab(item)} key={item}>{item === "period" ? "Period replay" : item === "evidence" ? "Inspect" : item[0].toUpperCase() + item.slice(1)}</button>)}</div></div>
      <TraceCoverageNotice traceLevel={capabilities.trace_level} bidReplayAvailable={capabilities.bid_replay_available} onCreateFullReplayRevision={onCreateFullReplayRevision} />
      <ReplayExportPanel key={`${run.id}-${year}-${period}`} apiOrigin={apiOrigin} runId={run.id} years={capabilities.years} selectedYear={year} selectedPeriod={period} />

      {tab === "overview" && annualRow && !annualPublished && <Callout tone="caution" title={`Annual totals not shown · ${coverageBadge.text}`} actions={<><button type="button" className="value-action-primary" onClick={() => onOpenInspect?.()}>Open in Inspect</button><button type="button" className="value-action-link" onClick={() => setTab("period")}>Show selected-period totals</button></>}><p>{coverageReasonText(coverage)} Totals over part of a year are not annual values, so they are not shown here.</p></Callout>}
      {tab === "overview" && annualRow && annualPublished && <div className="network-overview">
        <section className="network-kpis"><Metric label="Final physical resource cost" value={formatNetworkMoney(annualRow.system_resource_cost_gbp)} note="Settlement transfers excluded" /><Metric label="Constraint resource cost" value={formatNetworkMoney(annualRow.network_constraint_cost_gbp)} note="Zonal minus matched copperplate" /><Metric label="Congested boundary-periods" value={formatNetworkNumber(annualRow.congested_boundary_periods, 0)} /><Metric label="Observed unserved energy" value={`${formatNetworkNumber(annualRow.unserved_energy_mwh)} MWh`} note="Observed chronology, not statistical LOLE" /></section>
        <div className="network-two-column"><section className="panel"><div className="panel-head"><div><span>Resource-cost counterfactuals</span><h3>What changed the physical cost</h3></div></div><dl className="network-ledger"><div><dt>Final zonal resource cost</dt><dd>{formatNetworkMoney(annualRow.system_resource_cost_gbp)}</dd></div><div><dt>Forecast error component</dt><dd>{formatNetworkMoney(annualRow.forecast_error_cost_gbp)}</dd></div><div><dt>Network constraint component</dt><dd>{formatNetworkMoney(annualRow.network_constraint_cost_gbp)}</dd></div><div><dt>Total deviation from perfect forecast</dt><dd>{formatNetworkMoney(annualRow.total_deviation_cost_gbp)}</dd></div></dl></section><section className="panel"><div className="panel-head"><div><span>Payments kept separate</span><h3>Market and policy transfers</h3></div></div><dl className="network-ledger"><div><dt>National settlement</dt><dd>{formatNetworkMoney(annualRow.national_settlement_gbp)}</dd></div><div><dt>Redispatch settlement</dt><dd>{formatNetworkMoney(annualRow.redispatch_settlement_gbp)}</dd></div><div><dt>Policy transfers</dt><dd>{formatNetworkMoney(annualRow.policy_transfer_gbp)}</dd></div></dl></section></div>
        <section className="panel curtailment-attribution" aria-label="VRE curtailment attribution"><div className="panel-head"><div><span>Matched VRE counterfactuals</span><h3>VRE curtailment attribution</h3></div><label className="inline-select"><span>Technology</span><select aria-label="Technology" value={technology} onChange={(event) => { setTechnology(event.target.value as (typeof technologyOptions)[number]); setCurtailmentDetailOffset(0); }}>{technologyOptions.map((item) => <option value={item} key={item || "total"}>{item || "Total VRE"}</option>)}</select></label></div>
          {!attribution ? <Empty><b>Attribution unavailable</b><p>No annual VRE curtailment result was returned for this year.</p></Empty>
            : attribution.attribution_status === "invalid" ? <div className="error-box" role="alert"><b>Attribution invalid — {reasonMessage(attribution.reason_code)}</b><p>The recorded evidence contradicts itself; treat these curtailment figures as unverified and inspect the ledger.</p></div>
            : attribution.attribution_status !== "reconciled" ? <div className="curtailment-unavailable"><b>{curtailmentAvailabilityMessage(attribution)}</b><p>Missing scientific quantities remain unavailable; they are not displayed as zero.</p></div>
              : !selectedAttribution ? <div className="curtailment-unavailable"><b>No reconciled {technology} attribution row</b><p>The selected technology is not present in this year&apos;s annual totals.</p></div>
                : <>
                  <div className="network-kpis compact curtailment-summary-kpis"><Metric label="Realised available VRE" value={optionalMwh(selectedAttribution.available_mwh)} /><Metric label="Redispatch net impact" value={signedMwh(selectedAttribution.redispatch_net_mwh)} note="Added minus avoided curtailment" /><Metric label="Final VRE curtailment" value={optionalMwh(selectedAttribution.total_mwh)} /></div>
                  <CurtailmentWaterfall values={selectedAttribution} />
                  <section className="curtailment-detail-region" aria-label="Zone and technology summary"><div className="curtailment-detail-head"><div><span>Annual totals (complete year)</span><h4>Zone and technology summary</h4></div><small>{selectedZoneAttribution.length} annual rows</small></div>
                    {selectedZoneAttribution.length ? <div className="table-scroll network-table curtailment-detail-table"><table><thead><tr><th>Zone</th><th>Technology</th><th>Available</th><th>Economic</th><th>Forecast + / −</th><th>Redispatch + / −</th><th>Redispatch net</th><th>Final</th></tr></thead><tbody>{selectedZoneAttribution.map((row) => <tr key={`${row.year}-${row.zone_id}-${row.technology}`}><td>{row.zone_id}</td><td>{row.technology}</td><td>{optionalMwh(row.available_mwh)}</td><td>{directionalMwh(row.economic_mwh, "addition")}</td><td>{directionalMwh(row.forecast_added_mwh, "addition")} / {directionalMwh(row.forecast_avoided_mwh, "avoidance")}</td><td>{directionalMwh(row.redispatch_added_mwh, "addition")} / {directionalMwh(row.redispatch_avoided_mwh, "avoidance")}</td><td>{signedMwh(row.redispatch_net_mwh)}</td><td>{optionalMwh(row.total_mwh)}</td></tr>)}</tbody></table></div> : <p className="audit-note">No annual zone/technology rows match this technology selection.</p>}
                  </section>
                  <section className="curtailment-detail-region" aria-label="Object and tranche evidence"><div className="curtailment-detail-head"><div><span>Bounded ledger query</span><h4>Object and tranche evidence</h4></div><small>{curtailmentDetailState.status === "success" ? `${curtailmentDetailState.items.length} of ${curtailmentDetailState.total} object/tranche rows` : curtailmentDetailState.status === "loading" ? "Loading bounded rows…" : "Bounded query unavailable"}</small></div>
                    {curtailmentDetailState.status === "loading" ? <p className="audit-note" role="status">Loading object/tranche evidence…</p>
                      : curtailmentDetailState.status === "error" ? <div className="error-box" role="alert"><b>Object/tranche evidence unavailable: </b>{curtailmentDetailState.error}</div>
                        : curtailmentDetailState.items.length ? <div className="table-scroll network-table curtailment-detail-table"><table><thead><tr><th>Period</th><th>Zone</th><th>Technology</th><th>Asset / tranche</th><th>Economic</th><th>Forecast + / −</th><th>Redispatch + / −</th><th>Redispatch net</th><th>Final</th></tr></thead><tbody>{curtailmentDetailState.items.map((row) => <tr key={`${row.year}-${row.period}-${row.asset_id}-${row.bid_tranche_id}`}><td>{row.period_id}</td><td>{row.zone_id}</td><td>{row.technology}</td><td><b>{row.asset_id}</b><small>{row.bid_tranche_id}</small></td><td>+{formatNetworkNumber(row.economic_curtailment_mwh)} MWh</td><td>+{formatNetworkNumber(row.forecast_added_curtailment_mwh)} / −{formatNetworkNumber(row.forecast_avoided_curtailment_mwh)} MWh</td><td>+{formatNetworkNumber(row.redispatch_added_curtailment_mwh)} / −{formatNetworkNumber(row.redispatch_avoided_curtailment_mwh)} MWh</td><td>{signedMwh(row.redispatch_net_impact_mwh)}</td><td>{formatNetworkNumber(row.total_curtailment_mwh)} MWh</td></tr>)}</tbody></table></div> : <p className="audit-note">No object/tranche rows match this bounded year and technology selection.</p>}
                    {curtailmentDetailState.status === "success" && <div className="curtailment-pagination"><button className="secondary" aria-label="Previous object evidence page" disabled={curtailmentDetailOffset === 0} onClick={() => setCurtailmentDetailOffset(Math.max(0, curtailmentDetailOffset - curtailmentDetailLimit))}>Previous</button><span>Offset {curtailmentDetailOffset}</span><button className="secondary" aria-label="Next object evidence page" disabled={!curtailmentDetailState.hasMore} onClick={() => setCurtailmentDetailOffset(curtailmentDetailOffset + curtailmentDetailLimit)}>Next</button></div>}
                  </section>
                </>}
        </section>
      </div>}

      {tab === "period" && <div className="network-period-workspace">
        <section className="panel"><div className="panel-head"><div><span>Bounded period query</span><h3>Select a half-hour</h3></div><small>{periods.length} of {periodPage.total} rows in periods {periodFrom}–{periodFrom + periodWindow - 1}</small></div><div className="period-chip-list">{periods.map((row) => <button className={Number(row.period) === period ? "selected" : ""} key={String(row.period_id)} onClick={() => setPeriod(Number(row.period))}>{String(row.period_id)}</button>)}</div><div className="bounded-page-controls"><button className="secondary" aria-label="Previous period page" disabled={periodOffset === 0} onClick={() => setPeriodOffset(Math.max(0, periodOffset - 48))}>Previous period page</button><span>Offset {periodOffset}</span><button className="secondary" aria-label="Next period page" disabled={!periodPage.hasMore} onClick={() => setPeriodOffset(periodOffset + 48)}>Next period page</button></div>{selectedPeriod && <div className="network-kpis compact"><Metric label="System resource cost" value={formatNetworkMoney(numberValue(selectedPeriod, "system_resource_cost_gbp"))} /><Metric label="Network constraint cost" value={formatNetworkMoney(numberValue(selectedPeriod, "network_constraint_cost_gbp"))} /><Metric label="Redispatch settlement" value={formatNetworkMoney(numberValue(selectedPeriod, "redispatch_settlement_gbp"))} /><Metric label="Unserved energy" value={`${formatNetworkNumber(numberValue(selectedPeriod, "blackout_mwh"))} MWh`} /></div>}</section>
        <div className="network-two-column"><NetworkZoneMap zones={zones} boundaries={boundaries} /><section className="panel"><div className="panel-head"><div><span>Boundary use</span><h3>Computational corridors</h3></div></div><DataTable rows={boundaries} columns={[["boundary_id", "Boundary", (value) => String(value)], ["transfer_mwh", "Transfer", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["forward_capacity_mwh", "Forward limit", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["reverse_capacity_mwh", "Reverse limit", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["utilisation_fraction", "Use", (value) => `${formatNetworkNumber(scaled(toNumber(value), 100), 1)}%`], ["boundary_shadow_value_gbp_per_mwh", "Diagnostic marginal value", (value) => toNumber(value) == null ? "Not computed" : `£${formatNetworkNumber(toNumber(value))}/MWh`]]} /></section></div>
        <section className="panel"><div className="panel-head"><div><span>Final resources</span><h3>Ahead schedule and redispatch by asset</h3></div><button className="text-button" onClick={onOpenMarket}>Open full market replay</button></div><DataTable rows={resources} columns={[["asset_id", "Asset", (value) => String(value)], ["zone_id", "Zone", (value) => String(value)], ["technology", "Technology", (value) => String(value)], ["ahead_dispatch_mwh", "Ahead", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["signed_adjustment_mwh", "Adjustment", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["final_dispatch_mwh", "Final", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["physical_resource_cost_gbp", "Physical cost", (value) => formatNetworkMoney(toNumber(value))]]} />{storageRows.length > 0 && <><h4>Storage state after redispatch</h4><DataTable rows={storageRows} columns={[["asset_id", "Storage asset", (value) => String(value)], ["final_soc_mwh", "Final SOC", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["charge_mwh", "Charge", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["discharge_mwh", "Discharge", (value) => `${formatNetworkNumber(toNumber(value))} MWh`]]} /></>}</section>
        <section className="panel"><div className="panel-head"><div><span>Pay-as-bid adjustments</span><h3>Accepted redispatch bids</h3></div><span>{capabilities.bid_replay_available ? `${settlements.length} loaded` : "Summary trace"}</span></div>{capabilities.bid_replay_available ? <DataTable rows={settlements} columns={[["agent_id", "Agent", (value) => String(value)], ["zone_id", "Zone", (value) => String(value)], ["direction", "Direction", (value) => String(value)], ["accepted_delta_mwh", "Accepted delta", (value) => `${formatNetworkNumber(toNumber(value))} MWh`], ["bid_price_gbp_per_mwh", "Bid", (value) => `£${formatNetworkNumber(toNumber(value))}/MWh`], ["cashflow_to_agent_gbp", "Cashflow", (value) => formatNetworkMoney(toNumber(value))]]} /> : <Empty><b>Bid rows were not retained</b><p>Annual scientific totals remain available. Create a new Study revision with Full market replay to enable detailed bid replay.</p></Empty>}</section>
      </div>}

      {tab === "reliability" && year != null && <section className="panel reliability-list value-new-control" aria-label="Stress events and lost load"><div className="panel-head"><div><span>Observed physical shortfalls</span><h3>Stress events and lost load — full year {year}</h3></div><strong>{reliabilityState.status === "success" ? `${reliabilityState.total} ${reliabilityState.total === 1 ? "event" : "events"}` : "—"}{annualRow && annualPublished ? ` · ${formatNetworkNumber(annualRow.observed_loss_of_load_hours)} h` : ""}</strong></div><div className="info-box"><b>Observed chronology, not statistical LOLE.</b> These hours are counted in the simulated chronology and are not a probabilistic adequacy estimate.</div>
        {reliabilityState.status === "loading" ? <p className="audit-note" role="status">Loading the year&apos;s events…</p>
          : reliabilityState.status === "error" ? <div className="error-box" role="alert"><b>Reliability events unavailable: </b>{reliabilityState.error}</div>
            : reliabilityState.items.length ? <div className="table-scroll network-table"><table><thead><tr><th>Start (model date &amp; time)</th><th>Periods</th><th>Shortfall</th><th>Type</th><th>Zones</th><th><span className="visually-hidden">Replay</span></th></tr></thead><tbody>{reliabilityState.items.map((event) => { const row = reliabilityRow(event); return <tr key={row.key}><td><b>{row.start}</b><small>period {row.startPeriod}</small></td><td>{row.periods}</td><td>{row.shortfall ?? "Not recorded"}</td><td>{row.type}</td><td>{row.zones}</td><td><button type="button" className="text-button" onClick={() => onReplay?.(event.year, replayWindowStart(event.start_period))} aria-label={`Replay the event starting at period ${event.start_period}`}>Replay →</button></td></tr>; })}</tbody></table></div>
              : <Empty><b>{reliabilityEmptyText(coverage, year)}</b></Empty>}
        {reliabilityState.status === "success" && reliabilityState.total > RELIABILITY_PAGE_SIZE && <div className="bounded-page-controls"><button type="button" className="secondary" disabled={reliabilityOffset === 0} onClick={() => setReliabilityOffset(Math.max(0, reliabilityOffset - RELIABILITY_PAGE_SIZE))}>Previous events</button><span>Events {reliabilityOffset + 1}–{reliabilityOffset + reliabilityState.items.length} of {reliabilityState.total}</span><button type="button" className="secondary" disabled={!reliabilityState.hasMore} onClick={() => setReliabilityOffset(reliabilityOffset + RELIABILITY_PAGE_SIZE)}>Next events</button></div>}
      </section>}

      {tab === "evidence" && <div className="network-inspect">
        <div className="network-two-column"><section className="panel"><div className="panel-head"><div><span>Method and limits</span><h3>Interpret this workspace correctly</h3></div></div><dl className="network-ledger"><div><dt>Network pack</dt><dd>{capabilities.network_pack_id}</dd></div><div><dt>Ledger trace</dt><dd>{capabilities.trace_level}</dd></div><div><dt>Network representation</dt><dd>{capabilities.network_semantics.replaceAll("_", " ")}</dd></div><div><dt>Security scope</dt><dd>Not a security analysis</dd></div></dl>{capabilities.demand_alignment && <><h4>Demand authority</h4><dl className="network-ledger"><div><dt>Mode</dt><dd>{capabilities.demand_alignment.mode === "scenario_scaled_zonal_shares" ? "Scenario national demand × signed zonal shares" : capabilities.demand_alignment.mode === "network_pack_absolute_demand" ? "Independent network-pack demand" : "Mixed mode — invalid evidence"}</dd></div><div><dt>Periods audited</dt><dd>{formatNetworkNumber(capabilities.demand_alignment.period_count, 0)}</dd></div><div><dt>Scale range</dt><dd>{formatNetworkNumber(capabilities.demand_alignment.scale_factor_min, 5)}–{formatNetworkNumber(capabilities.demand_alignment.scale_factor_max, 5)}</dd></div><div><dt>Maximum conservation residual</dt><dd>{formatNetworkNumber(capabilities.demand_alignment.maximum_absolute_conservation_residual_mwh, 9)} MWh</dd></div></dl><p className="audit-note">Detailed period evidence remains in {capabilities.demand_alignment.detail_location}; it is not expanded into the main run screen.</p>{capabilities.demand_alignment.mode === "network_pack_absolute_demand" && <div className="info-box">Independent zonal-demand study. National demand is supplied by the network pack. Network-cost attribution against a scenario-demand copperplate run is disabled.</div>}</>}<details><summary>中文方法说明</summary><p>全国日前市场先形成统一的竞价结果；随后分区再调度在固定边界容量下调整火电、可再生能源、储能、进口和必要时的负荷损失。这里的边界是计算走廊，不是逐条输电线路，也不开展 N-1 或电压安全分析。</p></details></section><section className="panel"><div className="panel-head"><div><span>Solver linkage</span><h3>Declared input and diagnostics</h3></div></div>{solver.length ? <DataTable rows={solver} columns={[["declared_input_sha256", "Declared input SHA-256", (value) => String(value)], ["solver_status", "Status", (value) => String(value)], ["declaration_artifact_id", "Declaration", (value) => String(value)], ["solver_artifact_id", "Solver evidence", (value) => String(value ?? "not written")], ["failure_artifact_id", "Failure evidence", (value) => String(value ?? "none")]]} /> : <Empty><b>No selected-period solver link</b></Empty>}<p className="audit-note">A diagnostic boundary marginal value is not a local market price or a cash payment.</p></section></div>
        <section className="panel solver-diagnostic-details" aria-label="Solver diagnostic details"><div className="panel-head"><div><span>Bounded v7 evidence</span><h3>Locked-objective diagnostics</h3></div><small>{solverDiagnosticState.total} rows · {solverDiagnosticLimit} maximum per page</small></div>
          {!capabilities.available_views.includes("solver-diagnostics") ? <Empty><b>No v7 solver diagnostics</b><p>This run predates the normalized locked-objective evidence table.</p></Empty>
            : solverDiagnosticState.status === "loading" ? <Empty><b>Loading solver diagnostics…</b></Empty>
              : solverDiagnosticState.status === "error" ? <div className="error-box" role="alert">{solverDiagnosticState.error}</div>
                : solverDiagnosticState.items.length ? <><DataTable rows={solverDiagnosticState.items} columns={[["period_id", "Period", (value) => String(value)], ["phase_id", "Locked phase", (value) => String(value)], ["objective_unit", "Unit", (value) => String(value)], ["computed_tolerance", "Tolerance", (value) => formatNetworkNumber(toNumber(value), 10)], ["degradation", "Degradation", (value) => formatNetworkNumber(toNumber(value), 10)], ["validated_ceiling", "Validated ceiling", (value) => formatNetworkNumber(toNumber(value), 10)], ["validation_class", "Class", (value) => String(value)]]} /><div className="solver-diagnostic-pagination"><button className="secondary" aria-label="Previous solver diagnostics page" disabled={solverDiagnosticOffset === 0} onClick={() => setSolverDiagnosticOffset(Math.max(0, solverDiagnosticOffset - solverDiagnosticLimit))}>Previous</button><span>{solverDiagnosticOffset + 1}–{Math.min(solverDiagnosticState.total, solverDiagnosticOffset + solverDiagnosticState.items.length)} of {solverDiagnosticState.total}</span><button className="secondary" aria-label="Next solver diagnostics page" disabled={!solverDiagnosticState.hasMore} onClick={() => setSolverDiagnosticOffset(solverDiagnosticOffset + solverDiagnosticLimit)}>Next</button></div></>
                  : <Empty><b>No solver rows in this bounded selection</b></Empty>}
        </section>
      </div>}
    </>}
  </div>;
}
