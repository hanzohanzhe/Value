"use client";

import { apiFetch, apiUrl, getJson } from "../../lib/api.ts";
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

  formatNetworkMoney,
  formatNetworkNumber,
  formatOptionalNetworkNumber,
  isBuiltinZonalSolverContract,
  isSolverValidationSummary,
  isZonalSolverContract,
  solverEvidenceNotRecordedByTraceProfile,
  numberValue,
  scaled,
  toNumber,
  copperplateBalancing,
  zonalLedgerRecorded,
} from "./networkRedispatch";
import { RELIABILITY_PAGE_SIZE, reliabilityQuery, reliabilityRow, replayWindowStart, type ReliabilityEvent } from "./reliabilityView.ts";
import { Callout, StatusPill } from "../shared/Callout";
import { reasonMessage } from "../shared/reasonCodes.ts";
import { annualTotalsPublishable, coveragePill, coverageReasonText, isResultCoverage, reliabilityEmptyText, yearCoveragePill, yearTotalsPublishable } from "../shared/coverageView.ts";
import { withUnit } from "../shared/format.ts";
import { fallbackAuditSentences } from "./fallbackAuditView.ts";
import "./network-coverage.css";
import { useStableRun } from "../shared/stableRun.ts";
import { DataTable as UiDataTable, type DataColumn } from "../../ui/DataTable.tsx";
import { PageHeader } from "../../ui/PageHeader.tsx";
import { Tabs } from "../../ui/Tabs.tsx";
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey, Translate } from "../../i18n/index.ts";
import { modelPeriodLabel, periodIdLabel } from "../shared/modelClock.ts";
import { FLOW_ARROWS, flowDirection, limitMw } from "./boundaryView.ts";
import { DEFAULT_NETWORK_LOCATION, NETWORK_TABS, networkQueryValues, networkYear, type NetworkLocation, type NetworkTab } from "./networkLocation.ts";

type Row = Record<string, unknown>;
type Tab = NetworkTab;
const TAB_LABELS: Record<Tab, MessageKey> = { overview: "network.tab.overview", period: "network.tab.period", reliability: "network.tab.reliability", evidence: "network.tab.evidence" };
const technologyOptions = ["", "Solar", "Onshore wind", "Offshore wind"] as const;
const curtailmentDetailLimit = 250;
const solverDiagnosticLimit = 100;

type FrozenSolverContractState = {
  selection: string;
  status: "success" | "error";
  contract?: ZonalSolverContract;
};

export type SolverDisplay = {
  badge: MessageKey;
  tone: "good" | "warn" | "blue";
  stackValidated: boolean;
  /** R7-5: one line saying why the state word applies (shown under the summary). */
  reason?: MessageKey;
};

function successfulTerminalRun(run: ZonalRun): boolean {
  return run.status === "completed"
    || (run.status === "archived" && run.archived_from_status === "completed");
}

export function solverDisplay(
  run: ZonalRun,
  frozenContractStatus: "loading" | "success" | "error",
  frozenContract: ZonalSolverContract | undefined,
  summaryStatus: "missing" | "invalid" | "valid",
  summary: SolverValidationSummary | null | undefined,
): SolverDisplay {
  if (!successfulTerminalRun(run)) return { badge: "network.solver.badge.notCompleted", tone: "warn", stackValidated: false };
  if (frozenContractStatus === "loading") return { badge: "network.solver.badge.loadingContract", tone: "blue", stackValidated: false };
  if (frozenContractStatus === "error" || !frozenContract) return { badge: "network.solver.badge.contractUnavailable", tone: "warn", stackValidated: false };
  if (summaryStatus === "invalid") return { badge: "network.solver.badge.statusUnavailable", tone: "warn", stackValidated: false };
  if (summaryStatus === "missing" || !summary) return { badge: "network.solver.badge.notRecorded", tone: "blue", stackValidated: false };
  const evidenceErrors = summary.evidence_errors;
  if (
    summary.evidence_status === "invalid"
    || evidenceErrors.length > 0
    || summary.study_status === "solver_evidence_invalid"
  ) return { badge: "network.solver.badge.invalid", tone: "warn", stackValidated: false };
  // R7-5: a summary-trace Run keeps no per-period solver diagnostics by design: a neutral state word, not "invalid".
  if (solverEvidenceNotRecordedByTraceProfile(summary)) {
    return { badge: "network.solver.badge.notRecordedTraceProfile", tone: "blue", stackValidated: false, reason: "network.solver.reason.traceProfile" };
  }
  if (summary.evidence_status === "not_recorded"
    || summary.annual_status === "NOT_RECORDED"
    || summary.study_status === "NOT_RECORDED") {
    return { badge: "network.solver.badge.notRecorded", tone: "blue", stackValidated: false };
  }
  if (!isBuiltinZonalSolverContract(frozenContract)) return { badge: "network.solver.badge.customContract", tone: "warn", stackValidated: false };
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
    return { badge: "network.solver.badge.completedWithWarning", tone: "warn", stackValidated: false };
  }
  if (summary.annual_status === "GO_WITH_NUMERICAL_WARNING"
    || summary.study_status === "GO_WITH_NUMERICAL_WARNING"
    || summary.warning_periods > 0) {
    return {
      badge: stackValidated
        ? "network.solver.badge.validatedWithWarning"
        : "network.solver.badge.warningNotValidated",
      tone: "warn",
      stackValidated,
    };
  }
  if (summary.solver_stack_validation_status === "solver_stack_not_yet_validated"
    || !summary.solver_validated
    || summary.inherited_unvalidated) {
    return { badge: "network.solver.badge.pending", tone: "blue", stackValidated: false };
  }
  const validated = stackValidated
    && summary.evidence_status === "valid"
    && evidenceErrors.length === 0
    && summary.annual_status === "GO"
    && summary.study_status === "GO"
    && summary.warning_periods === 0
    && summary.unvalidated_periods === 0;
  return validated
    ? { badge: "network.solver.badge.validated", tone: "good", stackValidated: true }
    : { badge: "network.solver.badge.statusUnavailable", tone: "warn", stackValidated: false };
}

/** R7-5: the solver state word and, when one applies, its one-line reason. */
export function SolverEvidenceState({ display }: { display: SolverDisplay }) {
  const t = useT();
  return <BadgeLike tone={display.tone}>{t(display.badge)}</BadgeLike>;
}

export function SolverEvidenceReason({ display }: { display: SolverDisplay }) {
  const t = useT();
  return display.reason ? <p className="solver-evidence-reason">{t(display.reason)}</p> : null;
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

function optionalMwh(t: Translate, value: number | null | undefined): string {
  const formatted = formatOptionalNetworkNumber(value);
  return formatted == null ? t("network.value.unavailable") : `${formatted} MWh`;
}

function signedMwh(t: Translate, value: number | null | undefined): string {
  const formatted = formatOptionalNetworkNumber(value == null ? value : Math.abs(value));
  if (formatted == null) return t("network.value.unavailable");
  if (value === 0) return "0 MWh";
  return `${value! < 0 ? "−" : "+"}${formatted} MWh`;
}

function directionalMwh(t: Translate, value: number | null | undefined, direction: "addition" | "avoidance"): string {
  const formatted = formatOptionalNetworkNumber(value);
  return formatted == null ? t("network.value.unavailable") : `${direction === "avoidance" ? "−" : "+"}${formatted} MWh`;
}

function curtailmentAvailabilityMessage(t: Translate, attribution: VRECurtailmentAnnual): string {
  if (attribution.attribution_status === "legacy_partial") {
    return t("network.attribution.legacy");
  }
  const messages: Record<string, MessageKey> = {
    module_does_not_provide_counterfactual_snapshot: "network.attribution.noSnapshot",
    selected_balancing_does_not_provide_final_zonal_dispatch: "network.attribution.noFinalDispatch",
    attribution_evidence_not_recorded: "network.attribution.notRecorded",
    attribution_period_set_incomplete: "network.attribution.periodSetIncomplete",
    attribution_period_status_invalid: "network.attribution.periodStatusInvalid",
  };
  const key = messages[attribution.reason_code ?? ""];
  // R-7 (P1-polish): a code the dictionary explains reads as its explanation; only an unknown code shows as a phrase.
  return key ? t(key) : t("network.attribution.otherReason", { reason: reasonMessage(String(attribution.reason_code ?? attribution.attribution_status)).replace(/[.。]$/u, "") });
}

type Column = [string, string, (value: unknown, row: Row) => string, boolean?];

/** The network tables (spec 2, W4c): the shared DataTable - caption, scoped headers, sticky header, numeric columns right-aligned, a labelled scroll container. The fourth column entry marks a numeric column. */
export function DataTable({ rows, columns, caption }: { rows: Row[]; columns: Column[]; caption?: string }) {
  const t = useT();
  const tableColumns: DataColumn<Row>[] = columns.map(([key, label, render, numeric]) => ({ key, header: label, numeric: Boolean(numeric), render: (row: Row) => render(row[key], row) }));
  return <UiDataTable className="network-table" caption={caption ?? t("network.table.defaultCaption")} captionHidden columns={tableColumns} rows={rows} rowKey={(row) => `${String(row.year)}-${String(row.period)}-${String(row.zone_id ?? row.boundary_id ?? row.asset_id ?? row.agent_id ?? row.event_id ?? row.phase_id ?? "")}`} />;
}

/** F3-13 (display part): a signed corridor transfer as "→ 2 MWh" (forward) or "← 1.07 MWh" (reverse); "—" when missing. */
export function transferText(value: unknown): string {
  const transfer = toNumber(value);
  const direction = flowDirection(transfer);
  if (transfer == null || direction == null) return withUnit(formatNetworkNumber(null), "MWh");
  return `${FLOW_ARROWS[direction]} ${withUnit(formatNetworkNumber(Math.abs(transfer)), "MWh")}`;
}

// Review response (S6, F3-06): the network tables are named so a render test can check that a
// missing value is "—" on its own (never "— MWh" or £0).
// F3-13 (display part, W4c): the ledger records a corridor limit as energy per period
// (limit MW x period hours x rating multiplier); the table shows it in MW.
const boundaryColumns = (t: Translate, periodHours: number | null | undefined): Column[] => [["boundary_id", t("network.col.boundary"), (value) => String(value)], ["transfer_mwh", t("network.col.transfer"), (value) => transferText(value), true], ["forward_capacity_mwh", t("network.col.forwardLimit"), (value) => `${withUnit(formatNetworkNumber(limitMw(toNumber(value), periodHours)), "MW")}`, true], ["reverse_capacity_mwh", t("network.col.reverseLimit"), (value) => `${withUnit(formatNetworkNumber(limitMw(toNumber(value), periodHours)), "MW")}`, true], ["utilisation_fraction", t("network.col.use"), (value) => `${withUnit(formatNetworkNumber(scaled(toNumber(value), 100), 1), "%", "")}`, true], ["boundary_shadow_value_gbp_per_mwh", t("network.col.boundaryValue"), (value) => toNumber(value) == null ? t("network.value.notComputed") : `${withUnit(formatNetworkNumber(toNumber(value)), "/MWh", "", "£")}`, true]];
export function BoundaryUseTable({ rows, periodHours = 0.5 }: { rows: Row[]; periodHours?: number | null }) { const t = useT(); return <DataTable caption={t("network.boundary.caption")} rows={rows} columns={boundaryColumns(t, periodHours)} />; }
const resourceColumns = (t: Translate): Column[] => [["asset_id", t("network.col.asset"), (value) => String(value)], ["zone_id", t("network.col.zone"), (value) => String(value)], ["technology", t("network.col.technology"), (value) => String(value)], ["ahead_dispatch_mwh", t("network.col.ahead"), (value) => `${withUnit(formatNetworkNumber(toNumber(value)), "MWh")}`], ["signed_adjustment_mwh", t("network.col.adjustment"), (value) => `${withUnit(formatNetworkNumber(toNumber(value)), "MWh")}`], ["final_dispatch_mwh", t("network.col.final"), (value) => `${withUnit(formatNetworkNumber(toNumber(value)), "MWh")}`], ["physical_resource_cost_gbp", t("network.col.physicalCost"), (value) => formatNetworkMoney(toNumber(value))]];
export function ResourceDispatchTable({ rows }: { rows: Row[] }) { const t = useT(); return <DataTable caption={t("network.resource.caption")} rows={rows} columns={resourceColumns(t)} />; }
const storageColumns = (t: Translate): Column[] => [["asset_id", t("network.col.storageAsset"), (value) => String(value)], ["final_soc_mwh", t("network.col.finalSoc"), (value) => `${withUnit(formatNetworkNumber(toNumber(value)), "MWh")}`], ["charge_mwh", t("network.col.charge"), (value) => `${withUnit(formatNetworkNumber(toNumber(value)), "MWh")}`], ["discharge_mwh", t("network.col.discharge"), (value) => `${withUnit(formatNetworkNumber(toNumber(value)), "MWh")}`]];
export function StorageStateTable({ rows }: { rows: Row[] }) { const t = useT(); return <DataTable caption={t("network.storage.caption")} rows={rows} columns={storageColumns(t)} />; }
const settlementColumns = (t: Translate): Column[] => [["agent_id", t("network.col.agent"), (value) => String(value)], ["zone_id", t("network.col.zone"), (value) => String(value)], ["direction", t("network.col.direction"), (value) => String(value)], ["accepted_delta_mwh", t("network.col.acceptedDelta"), (value) => `${withUnit(formatNetworkNumber(toNumber(value)), "MWh")}`], ["bid_price_gbp_per_mwh", t("network.col.bid"), (value) => `${withUnit(formatNetworkNumber(toNumber(value)), "/MWh", "", "£")}`], ["cashflow_to_agent_gbp", t("network.col.cashflow"), (value) => formatNetworkMoney(toNumber(value))]];
export function SettlementTable({ rows }: { rows: Row[] }) { const t = useT(); return <DataTable caption={t("network.settlement.caption")} rows={rows} columns={settlementColumns(t)} />; }

export default function NetworkRedispatchView({
  run: liveRun,
  onOpenMarket,
  onCreateFullReplayRevision,
  onOpenRun,
  onRerun,
  sourceStudyMutable,
  onReplay,
  onOpenInspect,
  linked = DEFAULT_NETWORK_LOCATION,
  onLocationChange,
}: {
  run?: ZonalRun;
  /** W6 (spec 0.3): the year, tab and period window the page's URL names (read once, when the page opens). */
  linked?: NetworkLocation;
  /** Called with the page's query values whenever the year, tab or window changes (the route writes them to the URL). */
  onLocationChange?: (values: Record<string, string | number | null>) => void;
  /** Open Market replay at a stress / lost-load event (spec 4.4). */
  onReplay?: (year: number, periodFrom: number) => void;
  onOpenInspect?: () => void;
  onOpenMarket: () => void;
  onCreateFullReplayRevision: () => void;
  onOpenRun: () => void;
  onRerun: () => Promise<void>;
  sourceStudyMutable: boolean;
}) {
  // R5 R-低1: reload on the Run's identity, status or years, not on every poll.
  const run = useStableRun(liveRun);
  const t = useT();
  const runId = run?.id ?? "";
  const base = run ? apiUrl(`runs/${run.id}/network-redispatch`) : "";
  // R-D5 (round R1-5): a Run without a balancing module cleared one national market (copperplate).
  const copperplateKind = copperplateBalancing(run?.modules);
  const isKnownCopperplate = copperplateKind !== null;
  const [capabilities, setCapabilities] = useState<ZonalCapabilities | null>(null);
  const [annual, setAnnual] = useState<AnnualBrief | null>(null);
  const [tab, setTab] = useState<Tab>(linked.tab);
  const [year, setYear] = useState<number | null>(null);
  const [period, setPeriod] = useState<number | null>(null);
  const [periods, setPeriods] = useState<Row[]>([]);
  const [periodWindow, setPeriodWindow] = useState<48 | 336>(linked.window);
  const [periodFrom, setPeriodFrom] = useState(linked.from);
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
  // R-D5: the ledger has the zonal tables but no zonal rows (a national-only Run).
  const [noZonalRows, setNoZonalRows] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) return;
    let active = true;
    void getJson<unknown>(apiUrl(`runs/${runId}/artifacts/input-snapshot/project.json`))
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
  }, [runId]);

  useEffect(() => {
    if (!run) return;
    // R-D5: the annual brief is requested only when the ledger holds zonal rows,
    // so a withheld national Run no longer reports two reasons in one sentence.
    getJson<ZonalCapabilities>(`${base}/capabilities`).then(async (nextCapabilities) => {
      if (!zonalLedgerRecorded(nextCapabilities)) { setNoZonalRows(true); setProbeError(""); return; }
      const nextAnnual = await getJson<AnnualBrief>(`${base}/annual`);
      setCapabilities(nextCapabilities);
      setAnnual(nextAnnual);
      // W6: keep the year on screen, else the one the URL names, when the Run has it.
      setYear((current) => networkYear(nextCapabilities.years, current ?? linked.year, nextAnnual.years[0]?.year ?? nextCapabilities.years[0] ?? null));
      setProbeError("");
    }).catch((reason: Error) => setProbeError(reason.message)).finally(() => setLoading(false));
  }, [base, run, linked.year]);

  // W6 (spec 0.3): the year, tab and period window are in the URL, so a reload or a link opens the same view.
  useEffect(() => {
    if (year != null) onLocationChange?.(networkQueryValues({ year, tab, from: periodFrom, window: periodWindow }));
  }, [onLocationChange, periodFrom, periodWindow, tab, year]);

  useEffect(() => {
    if (!base || year == null || !capabilities) return;
    const periodTo = periodFrom + periodWindow - 1;
    const periodQuery = boundedPeriodQuery({ year, periodFrom, periodTo, limit: 48, offset: periodOffset });
    Promise.all([
      getJson<ResultPage>(`${base}/periods?${periodQuery}`),
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
    void apiFetch(`${base}/reliability?${reliabilityQuery(year, reliabilityOffset)}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || t("network.reliability.requestFailed"));
        return payload as ResultPage<ReliabilityEvent>;
      })
      .then((page) => { if (!controller.signal.aborted) setReliabilityPage({ selection, status: "success", items: page.items, total: page.total, hasMore: page.has_more, error: "" }); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setReliabilityPage({ selection, status: "error", items: [], total: 0, hasMore: false, error: reason.message }); });
    return () => controller.abort();
  }, [base, capabilities, reliabilityOffset, t, tab, year]);

  useEffect(() => {
    if (!base || year == null || period == null || !capabilities) return;
    const suffix = `year=${year}&period=${period}&limit=1000`;
    Promise.all([
      getJson<ResultPage>(`${base}/zones?${suffix}`),
      getJson<ResultPage>(`${base}/boundaries?${suffix}`),
      getJson<ResultPage>(`${base}/resources?${suffix}`),
      getJson<ResultPage>(`${base}/solver?${suffix}`),
      capabilities.bid_replay_available
        ? getJson<ResultPage>(`${base}/settlements?${suffix}`)
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
    void getJson<ResultPage>(`${base}/solver-diagnostics?${query}`)
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
    void getJson<ResultPage<VRECurtailmentDetailRow>>(`${base}/curtailment-detail?${query}`)
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
  // Review response (S6): the selected year is published by the same per-year rule as the Runs page.
  const yearBadge = year == null ? coverageBadge : yearCoveragePill(coverage, year);
  const annualPublished = year == null ? annualTotalsPublishable(coverage) : yearTotalsPublishable(coverage, year);
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
  // R7-5: a summary that records no diagnostics by trace profile has no figures to show (state word, never 0).
  const solverFigures = solverSummary && !solverEvidenceNotRecordedByTraceProfile(solverSummary) ? solverSummary : undefined;
  const solverSummaryStatus = rawSolverSummary == null ? "missing" : solverSummary ? "valid" : "invalid";
  const frozenContractState = frozenSolverContract.selection === runId
    ? frozenSolverContract
    : { selection: runId, status: "loading" as const, contract: undefined };
  const display = run
    ? solverDisplay(run, frozenContractState.status, frozenContractState.contract, solverSummaryStatus, solverSummary)
    : { badge: "network.solver.badge.notRecorded" as const, tone: "blue" as const, stackValidated: false };
  const customSolverContract = frozenContractState.status === "success"
    && Boolean(frozenContractState.contract)
    && !isBuiltinZonalSolverContract(frozenContractState.contract);
  const solverStatusLabel = t(frozenContractState.status === "loading"
    ? "network.solver.status.loading"
    : frozenContractState.status === "error" || !frozenContractState.contract
      ? "network.solver.status.unavailable"
      : customSolverContract
        ? "network.solver.status.custom"
        : display.stackValidated
          ? "network.solver.status.builtin"
          : "network.solver.status.notValidated");
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

  if (!run) return <div className="page"><Empty><b>{t("network.noRun.title")}</b><p>{t("network.noRun.body")}</p></Empty></div>;
  if (loading) return <div className="page"><Empty><b>{t("network.loading")}</b></Empty></div>;
  if (!capabilities) return <div className="page"><PageHeader title={t("network.title")} description={<>{t(copperplateKind === "module" ? "network.copperplate.moduleDescription" : copperplateKind === "national" ? "network.copperplate.nationalDescription" : "network.copperplate.noEvidenceDescription")}</>} /><Empty><b>{t(isKnownCopperplate ? "network.copperplate.title" : "network.copperplate.unavailableTitle")}</b><p>{copperplateKind === "module" ? t("network.copperplate.moduleBody") : copperplateKind === "national" ? <>{t("network.copperplate.nationalBody")} <button type="button" className="text-button" onClick={onOpenMarket}>{t("network.copperplate.openReplay")}</button></> : noZonalRows ? t("network.copperplate.noZonalRows") : probeError ? t("network.copperplate.unreadableReason", { reason: probeError }) : t("network.copperplate.unreadable")}</p></Empty></div>;

  return <div className="page network-workspace">
    <PageHeader title={t("network.title")} description={t("network.description")} actions={<div className="network-run-id"><small>{t("network.header.run")}</small><code>{run.id}</code><span>{capabilities?.network_pack_id || t(["queued", "snapshotting", "running", "cancel_requested"].includes(run.status) ? "network.header.evidencePending" : "network.header.packNotRecorded")}</span></div>} />

    {capabilities && <section className="network-coverage-banner value-new-control" aria-label={t("network.coverage.label")}><StatusPill tone={coverageBadge.tone} title={coverageBadge.title}>{coverageBadge.text}</StatusPill><span>{coverageReasonText(coverage)}</span></section>}
    {capabilities && fallbackAuditSentences(capabilities.runtime_fallback_audit).length > 0 && <div className="network-fallback-audit value-new-control"><Callout tone="caution" title={t("network.fallback.title")} actions={onOpenInspect ? <button type="button" className="value-action-primary" onClick={() => onOpenInspect()}>{t("network.openInspect")}</button> : undefined}><ul>{fallbackAuditSentences(capabilities.runtime_fallback_audit).map((sentence) => <li key={sentence}>{sentence}</li>)}</ul><p>{t("network.fallback.body")}</p></Callout></div>}
    {error && <div className="error-box"><b>{t("network.error.unavailable")} </b>{error}</div>}
    {run.status === "failed" && <section className="panel network-failure"><div><span>{t("network.failure.kicker")}</span><h3>{run.error_code ?? t("network.failure.evidenceRetained")}</h3><p>{run.error ?? t("network.failure.artefactsRemain")}</p><small>{t(sourceStudyMutable ? "network.failure.newRun" : "network.failure.restoreFirst")}</small></div><div><button className="secondary" onClick={onOpenRun}>{t("network.failure.openEvidence")}</button><button className="secondary" disabled={!sourceStudyMutable} onClick={() => void onRerun()}>{t("network.failure.rerun")}</button></div></section>}

    {capabilities && <>
      <section className="network-method-strip">
        <article><span>01</span><b>{t("network.method.aheadTitle")}</b><small>{t("network.method.aheadBody")}</small></article>
        <i>→</i>
        <article><span>02</span><b>{t("network.method.redispatchTitle")}</b><small>{t("network.method.redispatchBody")}</small></article>
        <aside><b>{t("network.method.scopeTitle")}</b><span>{t("network.method.scopeBody")}</span></aside>
      </section>

      <section className={`solver-validation-summary ${display.tone === "warn" ? "warning" : ""}`} aria-label={t("network.solver.title")}>
        <header><div><span>{t("network.solver.kicker")}</span><h3>{t("network.solver.title")}</h3></div><SolverEvidenceState display={display} /></header>
        <div className="solver-summary-grid">
          <article><small>{t("network.solver.contractStatus")}</small><b>{solverStatusLabel}</b></article>
          <article><small>{t("network.solver.method")}</small><b>{solverSummary?.method ?? t("network.solver.notRecorded")}</b></article>
          <article><small>{t("network.solver.contractVersion")}</small><b>{solverSummary?.solver_contract_version ?? t("network.solver.notRecorded")}</b></article>
          <article><small>{t("network.solver.ceilingUse")}</small><b>{solverFigures ? `${withUnit(formatNetworkNumber(solverFigures.maximum_validated_ceiling_use * 100, 1), "%", "")}` : t("network.solver.notRecorded")}</b></article>
          <article><small>{t("network.solver.warningCount")}</small><b>{solverFigures ? t("network.solver.warningPeriods", { count: solverFigures.warning_periods }) : t("network.solver.notRecorded")}</b></article>
          <article><small>{t("network.solver.unvalidatedCount")}</small><b>{solverFigures ? t("network.solver.unvalidatedPeriods", { count: solverFigures.unvalidated_periods }) : t("network.solver.notRecorded")}</b></article>
        </div>
        <SolverEvidenceReason display={display} />
        {hasNumericalWarning && display.badge !== "network.solver.badge.completedWithWarning" && <p className="solver-settings-error">{t(completedWithNumericalWarning ? "network.solver.badge.completedWithWarning" : "network.solver.warningRecorded")}</p>}
        {capabilities.available_views.includes("solver-diagnostics") && <a className="secondary solver-diagnostic-export" href={`${base}/export?view=solver-diagnostics&format=jsonl&limit=1000&offset=0`}>{t("network.solver.export")}</a>}
      </section>

      <div className="network-controls"><label><span>{t("network.control.year")}</span><select value={year ?? ""} onChange={(event) => { setYear(Number(event.target.value)); setPeriodFrom(0); setPeriodOffset(0); setCurtailmentDetailOffset(0); setSolverDiagnosticOffset(0); setReliabilityOffset(0); }}>{capabilities.years.map((item) => <option key={item}>{item}</option>)}</select></label><label><span>{t("network.control.window")}</span><select value={periodWindow} onChange={(event) => { setPeriodWindow(Number(event.target.value) as 48 | 336); setPeriodOffset(0); }}><option value={48}>{t("network.control.window24")}</option><option value={336}>{t("network.control.window168")}</option></select></label><label><span>{t("network.control.firstPeriod")}</span><input type="number" min={0} step={1} value={periodFrom} aria-describedby="network-first-period-time" onChange={(event) => { setPeriodFrom(Math.max(0, Number(event.target.value))); setPeriodOffset(0); }} /><small id="network-first-period-time" className="period-time">{modelPeriodLabel(year, periodFrom, capabilities.period_hours ?? 0.5)}</small></label></div>
      <TraceCoverageNotice traceLevel={capabilities.trace_level} bidReplayAvailable={capabilities.bid_replay_available} onCreateFullReplayRevision={onCreateFullReplayRevision} />
      {/* R-10 (P1-polish): WAI-ARIA tabs (app/ui/Tabs) - arrow keys, panel linked to its tab; the tab is in the URL (W6). */}
      <Tabs className="network-tab-strip" label={t("network.tabs.label")} tabs={NETWORK_TABS.map((item) => ({ id: item, label: t(TAB_LABELS[item]) }))} value={tab} onChange={(id) => setTab(id as Tab)}>

      {tab === "overview" && annualRow && !annualPublished && <Callout tone="caution" title={t("network.overview.notShownTitle", { badge: yearBadge.text })} actions={<><button type="button" className="value-action-primary" onClick={() => onOpenInspect?.()}>{t("network.openInspect")}</button><button type="button" className="value-action-link" onClick={() => setTab("period")}>{t("network.overview.showPeriodTotals")}</button></>}><p>{t("network.overview.notShownBody", { reason: coverageReasonText(coverage) })}</p></Callout>}
      {tab === "overview" && annualRow && annualPublished && <div className="network-overview">
        <section className="network-kpis"><Metric label={t("network.kpi.finalCost")} value={formatNetworkMoney(annualRow.system_resource_cost_gbp)} note={t("network.kpi.finalCostNote")} /><Metric label={t("network.kpi.constraintCost")} value={formatNetworkMoney(annualRow.network_constraint_cost_gbp)} note={t("network.kpi.constraintCostNote")} /><Metric label={t("network.kpi.congested")} value={formatNetworkNumber(annualRow.congested_boundary_periods, 0)} /><Metric label={t("network.kpi.unserved")} value={`${withUnit(formatNetworkNumber(annualRow.unserved_energy_mwh), "MWh")}`} note={t("network.kpi.unservedNote")} /></section>
        <div className="network-two-column"><section className="panel"><div className="panel-head"><div><span>{t("network.cost.kicker")}</span><h3>{t("network.cost.title")}</h3></div></div><dl className="network-ledger"><div><dt>{t("network.cost.final")}</dt><dd>{formatNetworkMoney(annualRow.system_resource_cost_gbp)}</dd></div><div><dt>{t("network.cost.forecast")}</dt><dd>{formatNetworkMoney(annualRow.forecast_error_cost_gbp)}</dd></div><div><dt>{t("network.cost.constraint")}</dt><dd>{formatNetworkMoney(annualRow.network_constraint_cost_gbp)}</dd></div><div><dt>{t("network.cost.deviation")}</dt><dd>{formatNetworkMoney(annualRow.total_deviation_cost_gbp)}</dd></div></dl></section><section className="panel"><div className="panel-head"><div><span>{t("network.transfers.kicker")}</span><h3>{t("network.transfers.title")}</h3></div></div><dl className="network-ledger"><div><dt>{t("network.transfers.national")}</dt><dd>{formatNetworkMoney(annualRow.national_settlement_gbp)}</dd></div><div><dt>{t("network.transfers.redispatch")}</dt><dd>{formatNetworkMoney(annualRow.redispatch_settlement_gbp)}</dd></div><div><dt>{t("network.transfers.policy")}</dt><dd>{formatNetworkMoney(annualRow.policy_transfer_gbp)}</dd></div></dl></section></div>
        <section className="panel curtailment-attribution" aria-label={t("network.curtailment.label")}><div className="panel-head"><div><span>{t("network.curtailment.kicker")}</span><h3>{t("network.curtailment.label")}</h3></div><label className="inline-select"><span>{t("network.curtailment.technology")}</span><select aria-label={t("network.curtailment.technology")} value={technology} onChange={(event) => { setTechnology(event.target.value as (typeof technologyOptions)[number]); setCurtailmentDetailOffset(0); }}>{technologyOptions.map((item) => <option value={item} key={item || "total"}>{item || t("network.curtailment.totalVre")}</option>)}</select></label></div>
          {!attribution ? <Empty><b>{t("network.curtailment.unavailableTitle")}</b><p>{t("network.curtailment.unavailableBody")}</p></Empty>
            : attribution.attribution_status === "invalid" ? <div className="error-box" role="alert"><b>{t("network.curtailment.invalidTitle", { reason: reasonMessage(attribution.reason_code) })}</b><p>{t("network.curtailment.invalidBody")}</p></div>
            : attribution.attribution_status !== "reconciled" ? <div className="curtailment-unavailable"><b>{curtailmentAvailabilityMessage(t, attribution)}</b><p>{t("network.curtailment.missingNotZero")}</p></div>
              : !selectedAttribution ? <div className="curtailment-unavailable"><b>{t("network.curtailment.noRow", { technology })}</b><p>{t("network.curtailment.noRowBody")}</p></div>
                : <>
                  <div className="network-kpis compact curtailment-summary-kpis"><Metric label={t("network.curtailment.available")} value={optionalMwh(t, selectedAttribution.available_mwh)} /><Metric label={t("network.curtailment.redispatchNet")} value={signedMwh(t, selectedAttribution.redispatch_net_mwh)} note={t("network.curtailment.redispatchNetNote")} /><Metric label={t("network.curtailment.final")} value={optionalMwh(t, selectedAttribution.total_mwh)} /></div>
                  <CurtailmentWaterfall values={selectedAttribution} />
                  <section className="curtailment-detail-region" aria-label={t("network.zoneSummary.label")}><div className="curtailment-detail-head"><div><span>{t("network.zoneSummary.kicker")}</span><h4>{t("network.zoneSummary.label")}</h4></div><small>{t("network.zoneSummary.rows", { count: selectedZoneAttribution.length })}</small></div>
                    {selectedZoneAttribution.length ? <div className="table-scroll network-table curtailment-detail-table"><table><thead><tr><th>{t("network.col.zone")}</th><th>{t("network.col.technology")}</th><th>{t("network.col.available")}</th><th>{t("network.col.economic")}</th><th>{t("network.col.forecastPlusMinus")}</th><th>{t("network.col.redispatchPlusMinus")}</th><th>{t("network.col.redispatchNet")}</th><th>{t("network.col.final")}</th></tr></thead><tbody>{selectedZoneAttribution.map((row) => <tr key={`${row.year}-${row.zone_id}-${row.technology}`}><td>{row.zone_id}</td><td>{row.technology}</td><td>{optionalMwh(t, row.available_mwh)}</td><td>{directionalMwh(t, row.economic_mwh, "addition")}</td><td>{directionalMwh(t, row.forecast_added_mwh, "addition")} / {directionalMwh(t, row.forecast_avoided_mwh, "avoidance")}</td><td>{directionalMwh(t, row.redispatch_added_mwh, "addition")} / {directionalMwh(t, row.redispatch_avoided_mwh, "avoidance")}</td><td>{signedMwh(t, row.redispatch_net_mwh)}</td><td>{optionalMwh(t, row.total_mwh)}</td></tr>)}</tbody></table></div> : <p className="audit-note">{t("network.zoneSummary.none")}</p>}
                  </section>
                  <section className="curtailment-detail-region" aria-label={t("network.objects.label")}><div className="curtailment-detail-head"><div><span>{t("network.objects.kicker")}</span><h4>{t("network.objects.label")}</h4></div><small>{curtailmentDetailState.status === "success" ? t("network.objects.rows", { shown: curtailmentDetailState.items.length, total: curtailmentDetailState.total }) : t(curtailmentDetailState.status === "loading" ? "network.objects.loadingRows" : "network.objects.queryUnavailable")}</small></div>
                    {curtailmentDetailState.status === "loading" ? <p className="audit-note" role="status">{t("network.objects.loading")}</p>
                      : curtailmentDetailState.status === "error" ? <div className="error-box" role="alert"><b>{t("network.objects.error")} </b>{curtailmentDetailState.error}</div>
                        : curtailmentDetailState.items.length ? <div className="table-scroll network-table curtailment-detail-table"><table><thead><tr><th>{t("network.col.period")}</th><th>{t("network.col.zone")}</th><th>{t("network.col.technology")}</th><th>{t("network.col.assetTranche")}</th><th>{t("network.col.economic")}</th><th>{t("network.col.forecastPlusMinus")}</th><th>{t("network.col.redispatchPlusMinus")}</th><th>{t("network.col.redispatchNet")}</th><th>{t("network.col.final")}</th></tr></thead><tbody>{curtailmentDetailState.items.map((row) => <tr key={`${row.year}-${row.period}-${row.asset_id}-${row.bid_tranche_id}`}><td title={String(row.period_id)}>{periodIdLabel(row.period_id, capabilities.period_hours ?? 0.5)}</td><td>{row.zone_id}</td><td>{row.technology}</td><td><b>{row.asset_id}</b><small>{row.bid_tranche_id}</small></td><td>{withUnit(formatNetworkNumber(row.economic_curtailment_mwh), "MWh", " ", "+")}</td><td>{withUnit(formatNetworkNumber(row.forecast_added_curtailment_mwh), "", "", "+")} / {withUnit(formatNetworkNumber(row.forecast_avoided_curtailment_mwh), "MWh", " ", "−")}</td><td>{withUnit(formatNetworkNumber(row.redispatch_added_curtailment_mwh), "", "", "+")} / {withUnit(formatNetworkNumber(row.redispatch_avoided_curtailment_mwh), "MWh", " ", "−")}</td><td>{signedMwh(t, row.redispatch_net_impact_mwh)}</td><td>{withUnit(formatNetworkNumber(row.total_curtailment_mwh), "MWh")}</td></tr>)}</tbody></table></div> : <p className="audit-note">{t("network.objects.none")}</p>}
                    {curtailmentDetailState.status === "success" && <div className="curtailment-pagination"><button className="secondary" aria-label={t("network.objects.previousLabel")} disabled={curtailmentDetailOffset === 0} onClick={() => setCurtailmentDetailOffset(Math.max(0, curtailmentDetailOffset - curtailmentDetailLimit))}>{t("network.page.previous")}</button><span>{t("network.page.offset", { offset: curtailmentDetailOffset })}</span><button className="secondary" aria-label={t("network.objects.nextLabel")} disabled={!curtailmentDetailState.hasMore} onClick={() => setCurtailmentDetailOffset(curtailmentDetailOffset + curtailmentDetailLimit)}>{t("network.page.next")}</button></div>}
                  </section>
                </>}
        </section>
      </div>}

      {tab === "period" && <div className="network-period-workspace">
        <section className="panel"><div className="panel-head"><div><span>{t("network.period.kicker")}</span><h3>{t("network.period.title")}</h3></div><small>{t("network.period.rows", { shown: periods.length, total: periodPage.total, start: modelPeriodLabel(year, periodFrom, capabilities.period_hours ?? 0.5) ?? periodFrom, first: periodFrom, last: periodFrom + periodWindow - 1 })}</small></div><div className="period-chip-list">{periods.map((row) => <button type="button" className={Number(row.period) === period ? "selected" : ""} aria-pressed={Number(row.period) === period} title={String(row.period_id)} key={String(row.period_id)} onClick={() => setPeriod(Number(row.period))}>{periodIdLabel(row.period_id, capabilities.period_hours ?? 0.5)}</button>)}</div><div className="bounded-page-controls"><button className="secondary" aria-label={t("network.period.previous")} disabled={periodOffset === 0} onClick={() => setPeriodOffset(Math.max(0, periodOffset - 48))}>{t("network.period.previous")}</button><span>{t("network.page.offset", { offset: periodOffset })}</span><button className="secondary" aria-label={t("network.period.next")} disabled={!periodPage.hasMore} onClick={() => setPeriodOffset(periodOffset + 48)}>{t("network.period.next")}</button></div>{selectedPeriod && <div className="network-kpis compact"><Metric label={t("network.period.systemCost")} value={formatNetworkMoney(numberValue(selectedPeriod, "system_resource_cost_gbp"))} /><Metric label={t("network.period.constraintCost")} value={formatNetworkMoney(numberValue(selectedPeriod, "network_constraint_cost_gbp"))} /><Metric label={t("network.period.redispatch")} value={formatNetworkMoney(numberValue(selectedPeriod, "redispatch_settlement_gbp"))} /><Metric label={t("network.period.unserved")} value={`${withUnit(formatNetworkNumber(numberValue(selectedPeriod, "blackout_mwh")), "MWh")}`} /></div>}</section>
        <div className="network-two-column"><NetworkZoneMap zones={zones} boundaries={boundaries} /><section className="panel"><div className="panel-head"><div><span>{t("network.boundaries.kicker")}</span><h3>{t("network.boundaries.title")}</h3></div></div><BoundaryUseTable rows={boundaries} periodHours={capabilities.period_hours} /></section></div>
        <section className="panel"><div className="panel-head"><div><span>{t("network.resources.kicker")}</span><h3>{t("network.resources.title")}</h3></div><button className="text-button" onClick={onOpenMarket}>{t("network.resources.openReplay")}</button></div><ResourceDispatchTable rows={resources} />{storageRows.length > 0 && <><h4>{t("network.resources.storageTitle")}</h4><StorageStateTable rows={storageRows} /></>}</section>
        <section className="panel"><div className="panel-head"><div><span>{t("network.bids.kicker")}</span><h3>{t("network.bids.title")}</h3></div><span>{capabilities.bid_replay_available ? t("network.bids.loaded", { count: settlements.length }) : t("network.bids.summaryTrace")}</span></div>{capabilities.bid_replay_available ? <SettlementTable rows={settlements} /> : <Empty><b>{t("network.bids.notRetained")}</b><p>{t("network.bids.notRetainedBody")}</p></Empty>}</section>
      </div>}

      {tab === "reliability" && year != null && <section className="panel reliability-list value-new-control" aria-label={t("network.reliability.label")}><div className="panel-head"><div><span>{t("network.reliability.kicker")}</span><h3>{t("network.reliability.title", { year })}</h3></div><strong>{reliabilityState.status === "success" ? t("network.reliability.events", { count: reliabilityState.total }) : "—"}{annualRow && annualPublished ? ` · ${withUnit(formatNetworkNumber(annualRow.observed_loss_of_load_hours), "h")}` : ""}</strong></div><div className="info-box"><b>{t("network.reliability.chronologyLead")}</b> {t("network.reliability.chronologyBody")}</div><p className="reliability-stress-pointer">{t("network.reliability.pointer")} <button type="button" className="text-button" onClick={onOpenMarket}>{t("network.reliability.openStress")}</button></p>
        {reliabilityState.status === "loading" ? <p className="audit-note" role="status">{t("network.reliability.loading")}</p>
          : reliabilityState.status === "error" ? <div className="error-box" role="alert"><b>{t("network.reliability.error")} </b>{reliabilityState.error}</div>
            : reliabilityState.items.length ? <div className="table-scroll network-table"><table><thead><tr><th>{t("network.col.startUtc")}</th><th>{t("network.col.periods")}</th><th>{t("network.col.shortfall")}</th><th>{t("network.col.type")}</th><th>{t("network.col.zones")}</th><th><span className="visually-hidden">{t("network.col.replay")}</span></th></tr></thead><tbody>{reliabilityState.items.map((event) => { const row = reliabilityRow(event); return <tr key={row.key}><td><b>{row.start}</b><small>{t("network.reliability.periodNumber", { period: row.startPeriod })}</small></td><td>{row.periods}</td><td>{row.shortfall ?? t("network.value.notRecorded")}</td><td>{row.type}</td><td>{row.zones}</td><td><button type="button" className="text-button" onClick={() => onReplay?.(event.year, replayWindowStart(event.start_period))} aria-label={t("network.reliability.replayLabel", { period: event.start_period })}>{t("network.reliability.replay")}</button></td></tr>; })}</tbody></table></div>
              : <Empty><b>{reliabilityEmptyText(coverage, year)}</b></Empty>}
        {reliabilityState.status === "success" && reliabilityState.total > RELIABILITY_PAGE_SIZE && <div className="bounded-page-controls"><button type="button" className="secondary" disabled={reliabilityOffset === 0} onClick={() => setReliabilityOffset(Math.max(0, reliabilityOffset - RELIABILITY_PAGE_SIZE))}>{t("network.reliability.previous")}</button><span>{t("network.reliability.range", { first: reliabilityOffset + 1, last: reliabilityOffset + reliabilityState.items.length, total: reliabilityState.total })}</span><button type="button" className="secondary" disabled={!reliabilityState.hasMore} onClick={() => setReliabilityOffset(reliabilityOffset + RELIABILITY_PAGE_SIZE)}>{t("network.reliability.next")}</button></div>}
      </section>}

      {tab === "evidence" && <div className="network-inspect">
        <div className="network-two-column"><section className="panel"><div className="panel-head"><div><span>{t("network.method.kicker")}</span><h3>{t("network.method.title")}</h3></div></div><dl className="network-ledger"><div><dt>{t("network.method.pack")}</dt><dd>{capabilities.network_pack_id}</dd></div><div><dt>{t("network.method.trace")}</dt><dd>{capabilities.trace_level}</dd></div><div><dt>{t("network.method.representation")}</dt><dd>{capabilities.network_semantics.replaceAll("_", " ")}</dd></div><div><dt>{t("network.method.security")}</dt><dd>{t("network.method.notSecurity")}</dd></div></dl>{capabilities.demand_alignment && <><h4>{t("network.demand.title")}</h4><dl className="network-ledger"><div><dt>{t("network.demand.mode")}</dt><dd>{t(capabilities.demand_alignment.mode === "scenario_scaled_zonal_shares" ? "network.demand.scaled" : capabilities.demand_alignment.mode === "network_pack_absolute_demand" ? "network.demand.absolute" : "network.demand.mixed")}</dd></div><div><dt>{t("network.demand.periods")}</dt><dd>{formatNetworkNumber(capabilities.demand_alignment.period_count, 0)}</dd></div><div><dt>{t("network.demand.scaleRange")}</dt><dd>{formatNetworkNumber(capabilities.demand_alignment.scale_factor_min, 5)}–{formatNetworkNumber(capabilities.demand_alignment.scale_factor_max, 5)}</dd></div><div><dt>{t("network.demand.residual")}</dt><dd>{withUnit(formatNetworkNumber(capabilities.demand_alignment.maximum_absolute_conservation_residual_mwh, 9), "MWh")}</dd></div></dl><p className="audit-note">{t("network.demand.detail", { location: capabilities.demand_alignment.detail_location })}</p>{capabilities.demand_alignment.mode === "network_pack_absolute_demand" && <div className="info-box">{t("network.demand.independent")}</div>}</>}<details><summary>{t("network.method.noteSummary")}</summary><p>{t("network.method.noteBody")}</p></details></section><section className="panel"><div className="panel-head"><div><span>{t("network.solverLink.kicker")}</span><h3>{t("network.solverLink.title")}</h3></div></div>{solver.length ? <DataTable rows={solver} columns={[["declared_input_sha256", t("network.col.declaredInput"), (value) => String(value)], ["solver_status", t("network.col.status"), (value) => String(value)], ["declaration_artifact_id", t("network.col.declaration"), (value) => String(value)], ["solver_artifact_id", t("network.col.solverEvidence"), (value) => String(value ?? t("network.solverLink.notWritten"))], ["failure_artifact_id", t("network.col.failureEvidence"), (value) => String(value ?? t("network.solverLink.none"))]]} /> : <Empty><b>{t("network.solverLink.empty")}</b></Empty>}<p className="audit-note">{t("network.solverLink.note")}</p></section></div>
        <section className="panel solver-diagnostic-details" aria-label={t("network.diagnostics.label")}><div className="panel-head"><div><span>{t("network.diagnostics.kicker")}</span><h3>{t("network.diagnostics.title")}</h3></div><small>{t("network.diagnostics.rows", { total: solverDiagnosticState.total, limit: solverDiagnosticLimit })}</small></div>
          {!capabilities.available_views.includes("solver-diagnostics") ? <Empty><b>{t("network.diagnostics.noneTitle")}</b><p>{t("network.diagnostics.noneBody")}</p></Empty>
            : solverDiagnosticState.status === "loading" ? <Empty><b>{t("network.diagnostics.loading")}</b></Empty>
              : solverDiagnosticState.status === "error" ? <div className="error-box" role="alert">{solverDiagnosticState.error}</div>
                : solverDiagnosticState.items.length ? <><DataTable caption={t("network.diagnostics.caption")} rows={solverDiagnosticState.items} columns={[["period_id", t("network.col.period"), (value) => periodIdLabel(value, capabilities.period_hours ?? 0.5)], ["phase_id", t("network.col.lockedPhase"), (value) => String(value)], ["objective_unit", t("network.col.unit"), (value) => String(value)], ["computed_tolerance", t("network.col.tolerance"), (value) => formatNetworkNumber(toNumber(value), 10)], ["degradation", t("network.col.degradation"), (value) => formatNetworkNumber(toNumber(value), 10)], ["validated_ceiling", t("network.col.validatedCeiling"), (value) => formatNetworkNumber(toNumber(value), 10)], ["validation_class", t("network.col.class"), (value) => String(value)]]} /><div className="solver-diagnostic-pagination"><button className="secondary" aria-label={t("network.diagnostics.previousLabel")} disabled={solverDiagnosticOffset === 0} onClick={() => setSolverDiagnosticOffset(Math.max(0, solverDiagnosticOffset - solverDiagnosticLimit))}>{t("network.page.previous")}</button><span>{t("network.diagnostics.range", { first: solverDiagnosticOffset + 1, last: Math.min(solverDiagnosticState.total, solverDiagnosticOffset + solverDiagnosticState.items.length), total: solverDiagnosticState.total })}</span><button className="secondary" aria-label={t("network.diagnostics.nextLabel")} disabled={!solverDiagnosticState.hasMore} onClick={() => setSolverDiagnosticOffset(solverDiagnosticOffset + solverDiagnosticLimit)}>{t("network.page.next")}</button></div></>
                  : <Empty><b>{t("network.diagnostics.empty")}</b></Empty>}
        </section>
      </div>}
      </Tabs>
      <ReplayExportPanel key={`${run.id}-${year}-${period}`} runId={run.id} years={capabilities.years} selectedYear={year} selectedPeriod={period} />
    </>}
  </div>;
}
