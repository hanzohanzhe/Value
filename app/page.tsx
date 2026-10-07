"use client";

import ModuleAuthorWorkbench from "./features/modules/ModuleAuthorWorkbench";
import ExtensionAuthorWorkbench from "./features/extensions/ExtensionAuthorWorkbench";
import StudyComposer from "./features/studies/StudyComposer";
import StudyMigrationDialog from "./features/studies/StudyMigrationDialog";
import { applyProfileChoice, isMethodologyCatalogue, selectedProfileId, type MethodologyCatalogue } from "./features/studies/methodologyChoice.ts";
import { migrationFromResponse, openingMigration, type RevisionMigration } from "./features/studies/studyMigration.ts";
import AdvancedSettings from "./features/studies/AdvancedSettings";
import { alignZonalSolverContract } from "./features/studies/solverContract";
import RunWorkspace from "./features/runs/RunWorkspace";
import AuditView, { type AuditTab } from "./features/evidence/AuditView";
import { Badge, formatBytes, formatNumber, modelDisplayName, withUnit } from "./features/shared/presentation";
import { API_BASE, OFFLINE_AFTER_FAILURES, classifyRefreshFailure, getJson, pollDelay, serviceState } from "./features/shared/api";
import "./features/shared/service-status.css";
import ModuleQuarantinePanel, { type QuarantineRow } from "./features/modules/ModuleQuarantinePanel";
import { isPendingRunsRefusal, pendingRunsQuestion } from "./features/modules/module-quarantine.mjs";
import DisabledEntriesPanel, { type EntryError } from "./features/modules/DisabledEntriesPanel";
import DataPackValidationPanel from "./features/data/DataPackValidationPanel";
import { inputsPresentSuffix, validationLayers, worstStatus, type DataPackValidationReport } from "./features/data/dataPackValidation.ts";
import { disabledEntries, extensionSourceChangeNote, installedModuleCard, lifecyclePath, moduleUsageNote, type DisabledEntry } from "./features/modules/disabledEntries.ts";
import { baseInputsPill } from "./features/shared/headerPill.ts";
import { formatEnergy, formatEnergyGroup, formatQuantity } from "./features/shared/format.ts";
import { modelClockSuffix, modelTimeText } from "./features/shared/modelClock.ts";
import { seriesShapes, vreEventGroups, vreKpis, vreLabels, vreYearCoverage } from "./features/market/vreView.ts";
import type { AuctionView, DispatchTimeline, MarketCapability, StoragePeriodRow, VreSummary } from "./features/market/marketTypes.ts";
import { EMPTY_DISPATCH_MESSAGES, bucketPrice, emptyDispatchReason, stackSupply, stackedTechnologies, stressBuckets } from "./features/market/dispatchView.ts";
import { acceptedCell, storageLedgerNote } from "./features/market/auctionOffers.ts";
import { StatusPill, ValueState } from "./features/shared/Callout";
import "./features/market/market-replay.css";
import OpenFromLauncher from "./features/shared/OpenFromLauncher";
import { PUBLIC_CAPABILITY_DOMAINS, domainLabel } from "./features/shared/domainConstants";
import type { PageResult } from "./features/shared/pagination";
import type { View } from "./features/shared/navigation";
import type { Workspace } from "./features/shared/workspaceTypes";
import type { ModuleInstallation, Extension, ExtensionInstallation, DomainPreset, DraftResolution, StudyForm, DataPack, Project, StudyTrashEntry, ParameterDefinition } from "./features/studies/types";
import type { RunMode, ModelRun, PreflightReport, ResourceReadiness, FrozenInputSnapshot } from "./features/runs/types";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CommunityHome, CommunityPathPicker, type CommunityPath } from "./features/workspace/CommunityPaths";
import ReadMePanel from "./features/workspace/ReadMePanel";
import ResearchJourney from "./features/workspace/ResearchJourney";
import JourneyDataEditor from "./features/workspace/JourneyDataEditor";
import ResultQueryPanel from "./features/results/ResultQueryPanel";
import { ALL_RUN_MODES, runModesForStudy, selectedRunScope } from "./features/workspace/runScope";
import { preflightKey, preflightMatches } from "./features/workspace/preflightIdentity";
import RunContextBar from "./features/workspace/RunContextBar";
import { annualResultsWithheld, shortfallDisplay, VRE_WITHHELD_TEXT } from "./features/workspace/runValidation.ts";
import { resolveRunContext } from "./features/workspace/runContext";
import { journeyFromLocation, readWorkspaceLocation, writeWorkspaceLocation, selectWorkspaceRun, type WorkspaceLocation } from "./features/workspace/workspaceLocation";
import "./features/workspace/workspace-shell.css";
import "./features/shared/narrow-layout.css";
import Value101Learn from "./features/learn/Value101Learn";
import DataWorkbench from "./features/data-workbench/DataWorkbench";
import {
  describeResearchSuiteInstallation,
  researchSuiteApiUrl,
} from "./features/data/research-suite-api.mjs";
import NetworkRedispatchView from "./features/network/NetworkRedispatchView";
import ReplayExportPanel from "./features/market/ReplayExportPanel";
import StressEventList from "./features/market/StressEventList";
import { isResultCoverage } from "./features/shared/coverageView.ts";
import { defaultDraftPackId } from "./features/studies/draftPack.ts";
import { preparationProgressText, startedRunNoticeText, startedRunNoticeVisible, type StartedRunNotice } from "./features/runs/runHistoryView.ts";
import TraceCoverageNotice, { type TraceProfile } from "./features/market/TraceCoverageNotice";
import {
  copyDefaultZonalSolverContract,
} from "./features/network/networkRedispatch";
import {
  VALUE_101_FALLBACK,
  type Value101TutorialDescriptor,
} from "./features/learn/value101";
import {
  buildStudyTrashConfirmation,
  sourceStudyAllowsDerivedRun,
} from "./features/learn/studyLifecycle";

// Same-origin API (P0-1): the UI gateway forwards /api/* with the session it
// holds; the page never knows an API origin, port or token.
const API = API_BASE;
const VALUE_NAME = "Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution";

type DataPreview = { schema_version: string; role: string; status: string; format?: string; bytes?: number; source_sha256?: string; filename?: string; unit?: string; definition?: string; capability?: string; time_semantics?: string; columns?: string[]; sampled_rows?: number; duplicate_sample_identities?: number; timestamp_sample?: { first?: string | null; last?: string | null }; numeric_ranges?: Record<string, { minimum: number; maximum: number }>; top_level_keys?: string[]; array_counts?: Record<string, number>; sample?: unknown; reason?: string };
type ResearchSuiteInstallation = {
  suite_id: string; suite_sha256: string; suite_bytes: number;
  component_pack_ids: string[]; component_bundle_sha256: string[];
  study_ids: string[]; rights_files: string[]; installation_boundary: string;
  idempotent: boolean;
};
type ResearchSuiteSummary = {
  suiteId: string; suiteSha256: string;
  components: { id: string; sha256: string }[];
  studyIds: string[]; idempotent: boolean; runStarted: false;
};
type DomainCapability = { status: "supported" | "experimental" | "unsupported" | "not_evaluated"; years?: number[]; claim?: string; reason?: string | null };
type DomainCapabilitiesPayload = { schema_version: string; identity: Record<string, unknown>; capabilities: Record<string, DomainCapability> };
type ResultMetric = { value: number | string | null; unit: string; definition_id: string; source_artifact_sha256?: string };
type NetworkSummaryPayload = { year: number; identity: Record<string, unknown>; source_artifacts: Record<string, string>; metrics: Record<string, ResultMetric>; topology: { buses: Record<string, unknown>[]; branches: Record<string, unknown>[]; reference_buses: string[]; placement: string }; branch_summary: { branch_id: string; from_bus?: string; to_bus?: string; rating_mw?: number | null; maximum_absolute_flow_mw: number; maximum_utilisation_fraction?: number | null }[]; storage_soc: { endpoint: string; reason: string } };
type NetworkPeriodPayload = { year: number; total: number; limit: number; offset: number; source_artifact_sha256: string; definitions: Record<string, string>; units: Record<string, string>; items: { period_id: string; injection_mwh: number; withdrawal_mwh: number; blackout_mwh: number; mean_nodal_price: number; buses: { bus_id: string; injection_mwh: number; withdrawal_mwh: number; blackout_mwh: number; angle_rad: number; price_gbp_per_mwh: number }[] }[] };
type NetworkBranchPayload = { total: number; limit: number; offset: number; source_artifact_sha256: string; items: { period_id: string; branch_id: string; from_bus?: string; to_bus?: string; flow_mw: number; rating_mw?: number | null; utilisation_fraction?: number | null; utilisation_status: string }[] };
type ExpansionSummaryPayload = { status: string; source_artifact_sha256: string; lineage: string; counterfactual_claim: string; years: { year: number; proposals: number; admitted: number; commissioned: number; failed: number; retired: number }[] };
type ExpansionEventPayload = { total: number; source_artifact_sha256: string; items: { year: number; event_id: string; event_type: string; candidate_id: string; project_id?: string; asset_id?: string; corridor_id: string; from_bus: string; to_bus: string; circuits: number; rating_mw: number; reason_code: string }[] };

const emptyWorkspace: Workspace = {
  architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [], data_packs: [],
  module_installations: [], extension_installations: [], projects: [], study_trash: [], runs: [], runtime: { python: "", compatible: false },
};
const views: { id: View; index: string; label: string; note: string }[] = [
  { id: "journey", index: "01A", label: "Research guide", note: "Reproduce or change data" },
  { id: "learn", index: "00", label: "Learn", note: "VALUE 101" },
  { id: "overview", index: "01", label: "Home", note: "Study status" },
  { id: "data", index: "02", label: "Data", note: "Inputs and mappings" },
  { id: "models", index: "03", label: "Modules", note: "PSM and CEM" },
  { id: "projects", index: "04", label: "Studies", note: "Scenarios and settings" },
  { id: "run", index: "05", label: "Runs", note: "Launch and compare" },
  { id: "marketReplay", index: "06", label: "Market replay", note: "Bids and dispatch" },
  { id: "curtailment", index: "07", label: "VRE & curtailment", note: "Unused renewable energy" },
  { id: "networkRedispatch", index: "08", label: "Network & redispatch", note: "Congestion and balancing" },
  { id: "systems", index: "09", label: "Network & water", note: "Optional-domain results" },
  { id: "audit", index: "10", label: "Inspect", note: "Ledgers and planning" },
  { id: "extend", index: "11", label: "Add data", note: "Adapter guide" },
];

const technologyColours: Record<string, string> = {
  offshore_wind: "#0c8e82", onshore_wind: "#35a89b", solar: "#e9b949",
  nuclear: "#6e70c7", ccgt: "#d26d4f", ocgt: "#e59b76", biomass_and_waste: "#758c43",
  natural_flow_hydro: "#3c7fb1", reservoir_hydro: "#285d8f", boundary_import: "#8892a6",
  battery_storage: "#2455d6", hydrogen_storage: "#5c75c8", pumped_hydro: "#173ca5", unmapped: "#b3bac6",
};

function ChartLegend({ technologies }: { technologies: string[] }) {
  return <div className="chart-legend">{technologies.map((technology) => <span key={technology}><i style={{ background: technologyColours[technology] ?? technologyColours.unmapped }} />{technology.replaceAll("_", " ")}</span>)}</div>;
}

function DispatchChart({ timeline, selectedPeriod, onSelect }: { timeline: DispatchTimeline; selectedPeriod: number; onSelect: (period: number) => void }) {
  const width = 920; const height = 300; const left = 56; const right = 18; const top = 18; const bottom = 42;
  const items = timeline.items;
  // R3-02: only flows whose role is supply are stacked, summed by technology across zones.
  const stacks = items.map((item) => stackSupply(item));
  const technologies = stackedTechnologies(items);
  const stressed = new Set(stressBuckets(items));
  const totals = stacks.map((stack) => stack.reduce((sum, segment) => sum + segment.energy_mwh, 0));
  const maximum = Math.max(1, ...totals, ...items.map((item) => item.real_demand_mwh));
  const plotWidth = width - left - right; const plotHeight = height - top - bottom;
  const x = (index: number) => left + index / Math.max(items.length, 1) * plotWidth;
  const y = (value: number) => top + plotHeight - value / maximum * plotHeight;
  const barWidth = Math.max(.6, plotWidth / Math.max(items.length, 1) - .35);
  const demandPoints = items.map((item, index) => `${x(index) + barWidth / 2},${y(item.real_demand_mwh)}`).join(" ");
  return <div className="evidence-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Chronological generation mix and demand">
    {[0, .25, .5, .75, 1].map((fraction) => <g key={fraction}><line x1={left} x2={width - right} y1={y(maximum * fraction)} y2={y(maximum * fraction)} className="grid-line" /><text x={left - 8} y={y(maximum * fraction) + 4} textAnchor="end">{formatQuantity(maximum * fraction, 3)}</text></g>)}
    {items.map((item, index) => { let cumulative = 0; const periodSelected = item.period_start <= selectedPeriod && selectedPeriod <= item.period_end; return <g key={`${item.period_start}-${item.period_end}`} className={periodSelected ? "selected-bucket" : ""} onClick={() => onSelect(item.period_start)}>
      <rect x={x(index)} y={top} width={Math.max(barWidth, 2)} height={plotHeight} fill="transparent" />
      {stacks[index].map((segment) => { const start = cumulative; cumulative += segment.energy_mwh; return <rect key={segment.technology} className="dispatch-segment" x={x(index)} y={y(cumulative)} width={barWidth} height={Math.max(y(start) - y(cumulative), 0)} fill={technologyColours[segment.technology] ?? technologyColours.unmapped} />; })}
      {stressed.has(index) && <rect className="stress-band" x={x(index)} y={top - 6} width={Math.max(barWidth, 2)} height={4}><title>{`Stress event: ${item.stress_periods} period(s), shortfall ${withUnit(formatNumber(item.shortfall_mwh), "MWh")}`}</title></rect>}
      {periodSelected && <line x1={x(index)} x2={x(index)} y1={top} y2={top + plotHeight} className="selection-line" />}
    </g>; })}
    <polyline points={demandPoints} className="demand-line" />
    <text x={left} y={height - 10}>{items[0]?.timestamp_start.slice(0, 10)}</text><text x={width - right} y={height - 10} textAnchor="end">{items.at(-1)?.timestamp_end.slice(0, 10)}</text>
    <text transform={`translate(14 ${top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Energy (MWh)</text>
  </svg><ChartLegend technologies={technologies} /><span className="line-key"><i />Demand</span>{stressed.size > 0 && <span className="stress-key"><i />Stress event (shortfall)</span>}</div>;
}

/** Spec 3.4 / M-D1: accepted MWh of one offer; a storage tranche reads its own row of the storage offer ledger. */
function AcceptedOfferCell({ offer }: { offer: AuctionView["offers"][number] }) {
  const cell = acceptedCell(offer);
  return <td title={cell.title}>{cell.mwh == null ? "Not separately recorded" : `${withUnit(formatNumber(cell.mwh), "MWh")}${cell.suffix}`}</td>;
}

function MeritOrderChart({ auction }: { auction: AuctionView }) {
  const width = 760; const height = 250; const left = 54; const right = 18; const top = 18; const bottom = 42;
  const total = Math.max(1, auction.offers.reduce((sum, offer) => sum + offer.offered_mwh, 0), auction.requirement_mwh);
  const maximumPrice = Math.max(1, ...auction.offers.map((offer) => offer.offer_price_gbp_per_mwh));
  const plotWidth = width - left - right; const plotHeight = height - top - bottom;
  const x = (value: number) => left + value / total * plotWidth; const y = (value: number) => top + plotHeight - value / maximumPrice * plotHeight;
  const positionedOffers = auction.offers.map((offer, index) => ({
    offer,
    start: auction.offers.slice(0, index).reduce((sum, item) => sum + item.offered_mwh, 0),
  }));
  return <div className="merit-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${auction.stage} merit order`}>
    {[0, .5, 1].map((fraction) => <g key={fraction}><line x1={left} x2={width - right} y1={y(maximumPrice * fraction)} y2={y(maximumPrice * fraction)} className="grid-line" /><text x={left - 7} y={y(maximumPrice * fraction) + 4} textAnchor="end">{formatQuantity(maximumPrice * fraction, 3)}</text></g>)}
    {positionedOffers.map(({ offer, start }) => <rect key={offer.offer_id ?? `${offer.asset_id}-${offer.execution_order}`} x={x(start)} y={y(offer.offer_price_gbp_per_mwh)} width={Math.max(x(start + offer.offered_mwh) - x(start), 1)} height={top + plotHeight - y(offer.offer_price_gbp_per_mwh)} fill={technologyColours[offer.technology] ?? technologyColours.unmapped} opacity={.84} />)}
    <line x1={x(auction.requirement_mwh)} x2={x(auction.requirement_mwh)} y1={top} y2={top + plotHeight} className="requirement-line" />
    {auction.marginal_offer_price_gbp_per_mwh != null && <line x1={left} x2={width - right} y1={y(auction.marginal_offer_price_gbp_per_mwh)} y2={y(auction.marginal_offer_price_gbp_per_mwh)} className="price-line" />}
    <text x={left} y={height - 10}>0</text><text x={width - right} y={height - 10} textAnchor="end">{withUnit(formatNumber(total), "MWh")} offered</text><text transform={`translate(14 ${top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Offer price (£/MWh)</text>
  </svg></div>;
}

/** Spec 3.1: the selected window as recorded. Shortfall comes from the backend (A2); it is never derived here. */
function WindowSummary({ bucket, timeline }: { bucket: DispatchTimeline["items"][number]; timeline: DispatchTimeline }) {
  const price = bucketPrice(bucket, timeline);
  const shortfall = bucket.shortfall_mwh;
  const stressPeriods = bucket.stress_periods;
  // F-P04-1: a lower-bound shortfall reads "≥ x MWh", with the upper bound on hover.
  const shortfallShown = shortfallDisplay(shortfall, bucket.shortfall_basis, bucket.shortfall_upper_mwh);
  const mwh = (value: number | null | undefined) => value == null ? <ValueState state="not_recorded" /> : `${withUnit(formatNumber(value), "MWh")}`;
  return <div className="selected-period-strip window-summary">
    <span className="window-summary-wide"><small>Window</small><b>{modelTimeText(bucket.timestamp_start)} → {modelTimeText(bucket.timestamp_end)}{modelClockSuffix(timeline.timezone)}</b>{timeline.clock_note && <em className="window-clock-note">{timeline.clock_note}</em>}</span>
    <span><small>Demand</small><b>{mwh(bucket.real_demand_mwh)}</b></span>
    <span><small>Accepted supply</small><b>{mwh(bucket.accepted_supply_mwh)}</b></span>
    <span className={typeof shortfall === "number" && shortfall > 0 ? "shortfall-positive" : ""}><small>Shortfall</small><b title={shortfallShown?.title}>{shortfallShown == null ? <ValueState state="not_recorded" title="This ledger does not record stress events (supply below demand)." /> : shortfallShown.text}</b>{typeof stressPeriods === "number" && stressPeriods > 0 && <StatusPill tone="caution">● {stressPeriods} stress {stressPeriods === 1 ? "period" : "periods"}</StatusPill>}</span>
    <span><small>Storage charge</small><b>{mwh(bucket.storage_charge_mwh)}</b></span>
    <span><small>Storage discharge</small><b>{mwh(bucket.storage_discharge_mwh)}</b></span>
    <span className="window-summary-wide"><small title={price.title}>{price.label}</small><b title={price.title}>{price.value ?? <ValueState state="not_recorded" />}</b></span>
  </div>;
}

/** A window to open Market replay at (a Replay jump from the network reliability list, spec 4.4). */
type ReplayTarget = { runId: string; year: number; periodFrom: number; nonce: number };

function MarketReplayView({ run, onCreateFullReplayRevision, initialWindow, focusStressEvents, onStressEventsFocused }: { run?: ModelRun; onCreateFullReplayRevision: () => void; initialWindow?: ReplayTarget | null; focusStressEvents?: boolean; onStressEventsFocused?: () => void }) {
  const [capabilities, setCapabilities] = useState<MarketCapability | null>(null);
  const [timeline, setTimeline] = useState<DispatchTimeline | null>(null);
  const [auction, setAuction] = useState<AuctionView | null>(null);
  const [storageRows, setStorageRows] = useState<StoragePeriodRow[]>([]);
  const [year, setYear] = useState(0); const [period, setPeriod] = useState(0);
  const [stage, setStage] = useState("ahead"); const [resolution, setResolution] = useState("daily");
  const [windowKind, setWindowKind] = useState<"24_hours" | "168_hours">("24_hours");
  const target = initialWindow && run && initialWindow.runId === run.id ? initialWindow : null;
  const [periodFrom, setPeriodFrom] = useState(target?.periodFrom ?? 0);
  const [timelineOffset, setTimelineOffset] = useState(0);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(Boolean(run));
  const windowPeriods = windowKind === "24_hours" ? 48 : 336;
  const periodTo = periodFrom + windowPeriods - 1;
  const bidReplayAvailable = capabilities?.bid_replay_available ?? capabilities?.auction_replay ?? false;
  useEffect(() => { if (!run) return; let active = true; void getJson<MarketCapability>(`${API}/runs/${run.id}/market/capabilities`).then((payload) => { if (!active) return; setCapabilities(payload); setYear(target && payload.years.includes(target.year) ? target.year : payload.years[0] ?? 0); setStage(payload.auction_stages?.[0]?.stage ?? "ahead"); setPeriodFrom(target && payload.years.includes(target.year) ? target.periodFrom : 0); setTimelineOffset(0); setError(""); }).catch((reason: Error) => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [run, target]);
  useEffect(() => { if (!run || !year) return; let active = true; const query = new URLSearchParams({ year: String(year), resolution, period_from: String(periodFrom), period_to: String(periodTo), limit: "96", offset: String(timelineOffset) }); void getJson<DispatchTimeline>(`${API}/runs/${run.id}/market/dispatch?${query}`).then((payload) => { if (!active) return; setTimeline(payload); setPeriod(payload.items[0]?.period_start ?? periodFrom); }).catch((reason: Error) => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [periodFrom, periodTo, resolution, run, timelineOffset, year]);
  useEffect(() => { if (!run || !year || !bidReplayAvailable || !stage) return; let active = true; void getJson<AuctionView>(`${API}/runs/${run.id}/market/auction?year=${year}&period=${period}&stage=${stage}`).then((payload) => { if (active) setAuction(payload); }).catch(() => { if (active) setAuction(null); }); return () => { active = false; }; }, [bidReplayAvailable, period, run, stage, year]);
  useEffect(() => { if (!run || !year || !capabilities?.storage_state) return; let active = true; void getJson<PageResult<StoragePeriodRow>>(`${API}/runs/${run.id}/market/storage?year=${year}&period=${period}&limit=100`).then((payload) => { if (active) setStorageRows(payload.items); }).catch(() => { if (active) setStorageRows([]); }); return () => { active = false; }; }, [capabilities?.storage_state, period, run, year]);
  if (!run) return <div className="page"><div className="empty-run"><b>No run selected</b><p>Select a run in Runs before opening market replay.</p></div></div>;
  const selected = timeline?.items.find((item) => item.period_start <= period && period <= item.period_end);
  const dispatchEmpty = timeline ? emptyDispatchReason(timeline, capabilities) : null;
  return <div className="page evidence-page"><div className="page-title"><div><span>Physical market evidence</span><h2>Replay bids, then follow the dispatched system</h2><p>The upper chart is final physical dispatch after all clearing stages. Select a bounded bucket to inspect its recorded evidence. Settlement transfers are never drawn as generation.</p></div><Badge tone={bidReplayAvailable ? "good" : "blue"}>{capabilities?.trace_level ?? "loading"} trace</Badge></div>
    {loading && <p className="loading">Loading the bounded market view…</p>}{error && <div className="error-box">{error}</div>}
    {capabilities && !capabilities.period_summary && <div className="info-box">{capabilities.missing_reason}</div>}
    {capabilities && <TraceCoverageNotice traceLevel={capabilities.trace_level} bidReplayAvailable={bidReplayAvailable} onCreateFullReplayRevision={onCreateFullReplayRevision} />}
    {capabilities?.period_summary && <><section className="panel evidence-panel"><div className="evidence-controls"><label><span>Model year</span><select value={year} onChange={(event) => { setYear(Number(event.target.value)); setPeriodFrom(0); setTimelineOffset(0); }}>{capabilities.years.map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Window</span><select value={windowKind} onChange={(event) => { setWindowKind(event.target.value as "24_hours" | "168_hours"); setTimelineOffset(0); }}><option value="24_hours">24 hours</option><option value="168_hours">168 hours</option></select></label><label><span>First period</span><input type="number" min={0} value={periodFrom} onChange={(event) => { setPeriodFrom(Math.max(0, Number(event.target.value))); setTimelineOffset(0); }} /></label><label><span>Timeline resolution</span><select value={resolution} onChange={(event) => { setResolution(event.target.value); setTimelineOffset(0); }}><option value="daily">Daily overview</option><option value="weekly">Weekly overview</option><option value="half_hour">Half-hour detail</option></select></label><label><span>Selected period</span><input type="number" min={periodFrom} max={periodTo} value={period} onChange={(event) => setPeriod(Number(event.target.value))} /></label></div>
      <div className="bounded-window-controls"><button className="secondary" disabled={periodFrom === 0} onClick={() => { setPeriodFrom(Math.max(0, periodFrom - windowPeriods)); setTimelineOffset(0); }}>Previous window</button><span>Periods {periodFrom}–{periodTo} · page offset {timelineOffset}</span><button className="secondary" onClick={() => { setPeriodFrom(periodFrom + windowPeriods); setTimelineOffset(0); }}>Next window</button></div>
      {timeline && dispatchEmpty && <div className="info-box dispatch-empty" role="status"><b>No supply flows recorded for this window</b><br />{EMPTY_DISPATCH_MESSAGES[dispatchEmpty]} <code>{dispatchEmpty}</code></div>}
      {timeline && !dispatchEmpty && <><DispatchChart timeline={timeline} selectedPeriod={period} onSelect={setPeriod} /><div className="bounded-page-controls"><button className="text-button" disabled={timelineOffset === 0} onClick={() => setTimelineOffset(Math.max(0, timelineOffset - timeline.limit))}>Previous page</button><span>{timeline.items.length} of {timeline.total} buckets in this selected window</span><button className="text-button" disabled={timelineOffset + timeline.items.length >= timeline.total} onClick={() => setTimelineOffset(timelineOffset + timeline.limit)}>Next page</button></div></>}
      {selected && timeline && <WindowSummary bucket={selected} timeline={timeline} />}
    </section>
    {year > 0 && <StressEventList key={`${run.id}-${year}`} runId={run.id} year={year} coverage={isResultCoverage(run.result_coverage) ? run.result_coverage : null} computedPeriods={run.diagnostic?.periods_per_year ?? run.run_policy?.periods_per_year ?? null} focus={focusStressEvents} onFocused={onStressEventsFocused} onReplay={(eventYear, from) => { setYear(eventYear); setPeriodFrom(from); setTimelineOffset(0); if (typeof window !== "undefined") window.scrollTo({ top: 0 }); }} />}
    <section className="panel evidence-panel"><div className="panel-head"><div><span>Declared auction input</span><h3>Selected-period merit order</h3></div>{bidReplayAvailable ? <label className="inline-select"><span>Stage</span><select value={stage} onChange={(event) => setStage(event.target.value)}>{capabilities.auction_stages.map((item) => <option value={item.stage} key={item.stage}>{item.stage} · {item.order_detail.replaceAll("_", " ")}</option>)}</select></label> : <Badge tone="warn">No bid-level replay</Badge>}</div>
      {!bidReplayAvailable ? <div className="info-box">Bid detail is unavailable under the recorded trace profile. The summary above remains scientific evidence; this panel does not render missing bids as zero.</div> : !auction ? <div className="info-box">No exact {stage} auction is recorded for period {period}. If a daily or weekly bucket is selected, enter any half-hour period inside that window.</div> : <><div className="auction-layout"><MeritOrderChart auction={auction} /><div className="auction-facts"><span><small>Requirement</small><b>{withUnit(formatNumber(auction.requirement_mwh), "MWh")}</b></span><span><small>Marginal accepted offer</small><b>{auction.marginal_offer_price_gbp_per_mwh == null ? "Not separately defined" : `${withUnit(formatNumber(auction.marginal_offer_price_gbp_per_mwh), "/MWh", "", "£")}`}</b></span><span><small>Information available</small><b>{auction.information_scope}</b></span><span><small>Acceptance detail</small><b>{auction.offer_acceptance_coverage.replaceAll("_", " ")}</b></span></div></div><div className="table-scroll"><table><thead><tr><th>Order</th><th>Asset</th><th>Technology</th><th>Offer</th><th>Offered</th><th>Accepted</th><th>Evidence</th></tr></thead><tbody>{auction.offers.map((offer) => <tr key={offer.offer_id ?? `${offer.asset_id}-${offer.execution_order}`}><td>{offer.execution_order + 1}</td><td><b>{offer.asset_id}</b></td><td title={offer.asset_type ? `Model class: ${offer.asset_type}` : undefined}>{offer.technology.replaceAll("_", " ")}</td><td>{withUnit(formatNumber(offer.offer_price_gbp_per_mwh), "/MWh", "", "£")}</td><td>{withUnit(formatNumber(offer.offered_mwh), "MWh")}</td><AcceptedOfferCell offer={offer} /><td>{offer.acceptance_granularity.replaceAll("_", " ")}</td></tr>)}</tbody></table></div>{storageLedgerNote(auction.offers) ? <p className="storage-ledger-note">{storageLedgerNote(auction.offers)}</p> : null}<p className="provenance-line">Input hash {auction.input_sha256} · source ledger {auction.source_artifact_sha256 ?? "hash unavailable"}</p></>}
      {capabilities.storage_state && <div className="storage-period-panel"><header><div><small>Storage state at period {period}</small><b>{capabilities.storage_cost_module_id ?? "Cost policy not recorded"}</b></div><Badge>{storageRows.length} assets</Badge></header>{storageRows.length ? <div>{storageRows.map((row) => <span key={row.asset_id}><b>{row.asset_id}</b><small>SOC {formatNumber(row.state_of_charge_mwh)} / {withUnit(formatNumber(row.energy_capacity_mwh), "MWh")}</small><em>charge {formatNumber(row.charge_mwh)} · discharge {withUnit(formatNumber(row.discharge_mwh), "MWh")} · {withUnit(formatNumber(row.power_capacity_mw), "MW")}</em></span>)}</div> : <p>No storage state is recorded for this selected period.</p>}</div>}
    </section><ReplayExportPanel key={`${run.id}-${year}-${period}`} runId={run.id} years={capabilities.years} selectedYear={year} selectedPeriod={period} /></>}
  </div>;
}

function VreTimelineChart({ timeline, excessLabel = "Pre-balancing excess" }: { timeline: DispatchTimeline; excessLabel?: string }) {
  const width = 920; const height = 280; const left = 56; const right = 18; const top = 18; const bottom = 42; const items = timeline.items;
  const maximum = Math.max(1, ...items.flatMap((item) => [item.vre_available_mwh, item.vre_accepted_mwh, item.excess_mwh]).filter((value) => typeof value === "number" && Number.isFinite(value)));
  const plotWidth = width - left - right; const plotHeight = height - top - bottom;
  const x = (index: number) => left + index / Math.max(items.length - 1, 1) * plotWidth; const y = (value: number) => top + plotHeight - value / maximum * plotHeight;
  // Designer ruling 4: an isolated recorded value (or a one-bucket view) is a 2.5px dot in the series colour.
  const segments = (key: "vre_available_mwh" | "vre_accepted_mwh" | "excess_mwh" | "neutral_unused_vre_mwh", className: string) => { const shapes = seriesShapes(items, key, x, y); return <>{shapes.lines.map((points, index) => <polyline key={`${key}-${index}`} points={points} className={className} />)}{shapes.dots.map((dot, index) => <circle key={`${key}-dot-${index}`} cx={dot.x} cy={dot.y} r={1.25} className={`${className} series-dot`} />)}</>; };
  return <div className="evidence-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Available, accepted and unused renewable energy timeline">{[0, .5, 1].map((fraction) => <g key={fraction}><line x1={left} x2={width - right} y1={y(maximum * fraction)} y2={y(maximum * fraction)} className="grid-line" /><text x={left - 8} y={y(maximum * fraction) + 4} textAnchor="end">{formatQuantity(maximum * fraction, 3)}</text></g>)}{segments("vre_available_mwh", "vre-available-line")}{segments("vre_accepted_mwh", "vre-accepted-line")}{segments("neutral_unused_vre_mwh", "vre-unused-line")}{segments("excess_mwh", "vre-excess-line")}<text x={left} y={height - 10}>{items[0]?.timestamp_start.slice(0, 10)}</text><text x={width - right} y={height - 10} textAnchor="end">{items.at(-1)?.timestamp_end.slice(0, 10)}</text><text transform={`translate(14 ${top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Energy (MWh)</text></svg><div className="line-legend"><span className="available">Available VRE</span><span className="accepted">Accepted VRE</span><span className="unused">Unused VRE</span><span className="excess">{excessLabel}</span></div></div>;
}

function CurtailmentView({ run }: { run?: ModelRun }) {
  const [summary, setSummary] = useState<VreSummary | null>(null); const [timeline, setTimeline] = useState<DispatchTimeline | null>(null);
  const [year, setYear] = useState(0); const [resolution, setResolution] = useState("daily"); const [error, setError] = useState("");
  // R4 R-低10: a Run whose annual results Q14 withholds is not asked for its
  // annual VRE summary (the server answers 409, which the browser logs as an error).
  const vreWithheld = annualResultsWithheld(run);
  useEffect(() => { if (!run || vreWithheld) return; let active = true; void getJson<VreSummary>(`${API}/runs/${run.id}/market/vre-summary`).then((payload) => { if (!active) return; setSummary(payload); setYear(payload.years[0]?.year ?? 0); setError(""); }).catch((reason: Error) => { if (active) setError(reason.message); }); return () => { active = false; }; }, [run, vreWithheld]);
  useEffect(() => { if (!run || !year) return; let active = true; void getJson<DispatchTimeline>(`${API}/runs/${run.id}/market/vre-timeline?year=${year}&resolution=${resolution}&limit=500`).then((payload) => { if (active) setTimeline(payload); }).catch((reason: Error) => { if (active) setError(reason.message); }); return () => { active = false; }; }, [resolution, run, year]);
  if (!run) return <div className="page"><div className="empty-run"><b>No run selected</b><p>Select a run in Runs before reviewing renewable-energy outcomes.</p></div></div>;
  if (vreWithheld) return <div className="page evidence-page"><div className="page-title"><div><span>Renewable-energy evidence</span><h2>See how much VRE was available, used and left unused</h2></div><StatusPill tone="caution" title={run.result_publication?.message ?? undefined}>Withheld</StatusPill></div><div className="info-box value-new-control"><b>Annual VRE results withheld</b><br />{VRE_WITHHELD_TEXT}</div></div>;
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
  return <div className="page evidence-page"><div className="page-title"><div><span>Renewable-energy evidence</span><h2>See how much VRE was available, used and left unused</h2><p>VALUE keeps the physical VRE identity separate from the retained VALUE market stages. Pre-balancing excess may include other inflexible low-cost generation; it is therefore displayed alongside, not silently renamed as VRE curtailment.</p></div><Badge tone={yearCoverage?.tone ?? "warn"}>{yearCoverage?.badge ?? "Diagnostic chronology"}</Badge></div>{error && <div className="error-box">{error}</div>}
    {summary && <><section className="panel evidence-panel"><div className="panel-head"><div><span>Across model years</span><h3>Annual VRE disposition</h3></div><Badge tone="blue">available = accepted + unused</Badge></div><div className="annual-vre-chart">{summary.years.map((item) => <button key={item.year} className={item.year === year ? "selected" : ""} onClick={() => setYear(item.year)}><span className="annual-bar"><i className="accepted" style={{ height: `${item.accepted_vre_mwh / maximum * 100}%` }} /><i className="unused" style={{ height: `${item.neutral_unused_vre_mwh / maximum * 100}%` }} /></span><b>{item.year}</b><small>{item.average_unused_vre_fraction == null ? "No VRE available" : `${withUnit(formatNumber(item.average_unused_vre_fraction * 100, 1), "%", "")} unused`}</small>{item.pre_balancing_excess_mwh != null && <em>{annualEnergy.format(item.pre_balancing_excess_mwh)} {labels.excess.toLowerCase()}</em>}</button>)}</div><div className="chart-legend"><span><i style={{ background: "#087e73" }} />Accepted VRE</span><span><i style={{ background: "#ef9a55" }} />Unused VRE</span></div></section>
      {selected && <section className="panel evidence-panel"><div className="panel-head"><div><span>{selected.year} evidence</span><h3>{yearCoverage?.heading}</h3></div><div className="evidence-controls compact"><label><span>Year</span><select value={year} onChange={(event) => setYear(Number(event.target.value))}>{summary.years.map((item) => <option key={item.year}>{item.year}</option>)}</select></label><label><span>Timeline</span><select value={resolution} onChange={(event) => setResolution(event.target.value)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="half_hour">Half-hour (first 500)</option></select></label></div></div>
        <div className="curtailment-kpis vre-kpis-grouped">{(["available", "accepted", "unused", "excess", "curtailment"] as const).map((key) => { const item = kpi(key)!; const unseparated = (key === "excess" || key === "curtailment") && item.exactMwh == null; return <span key={key}><small>{item.label}</small><b title={item.exactMwh == null ? undefined : `${item.exactMwh} MWh`}>{unseparated ? "Not separately identified" : item.value ?? "—"}</b>{key === "unused" && <em>{selected.average_unused_vre_fraction == null ? "No VRE available" : `${withUnit(formatNumber(selected.average_unused_vre_fraction * 100, 2), "%", "")} of available`}</em>}{key === "excess" && <em>{selected.pre_balancing_excess_scope.replaceAll("_", " ")}</em>}<i className="kpi-coverage">{coverageLine}</i></span>; })}</div>
        <div className="destination-strip"><div><small>{kpi("storage")!.label}</small><b>{kpi("storage")!.value ?? "—"}</b><i className="kpi-coverage">{coverageLine}</i></div><div><small>{kpi("export")!.label}</small><b>{kpi("export")!.value ?? "—"}</b><i className="kpi-coverage">{coverageLine}</i></div><div><small>{kpi("flexible")!.label}</small><b>{kpi("flexible")!.value ?? "—"}</b><i className="kpi-coverage">{coverageLine}</i></div><p>These are simultaneous system flows. The ledger does not claim that every charged, exported or flexible-load MWh came from VRE unless a source-linked flow is explicitly recorded.</p></div>
        {timeline && <VreTimelineChart timeline={timeline} excessLabel={labels.excess} />}
        {vreEventGroups(selected).map((group) => <section key={group.key} className="vre-event-group value-new-control" aria-label={`${group.title} events`}><h4>{group.title}</h4><p className="vre-event-basis">{group.basisNote}</p>{group.noEvents ? <p className="vre-event-basis">No events recorded</p> : group.events ? <div className="event-summary"><span><small>Affected periods</small><b>{group.events.affected_periods}</b></span><span><small>Longest continuous event</small><b>{withUnit(formatNumber(group.events.longest_event_hours), "hours")}</b></span><span><small>Peak event</small><b>{group.events.peak_event_mwh == null ? "Not evaluated" : formatEnergy(group.events.peak_event_mwh)}</b><em>{group.events.peak_event_timestamp ? `${modelTimeText(group.events.peak_event_timestamp)} UTC` : null}</em></span></div> : <p className="vre-event-basis">Not separately identified in this ledger.</p>}</section>)}<div className="event-summary"><span><small>VRE identity residual</small><b>{withUnit(formatNumber(selected.vre_identity_residual_mwh, 6), "MWh")}</b></span></div>
        <details className="definition-panel"><summary>Definitions and limits</summary><dl><div><dt>Unused VRE</dt><dd>Available renewable energy minus accepted renewable dispatch at the PSM boundary.</dd></div><div><dt>{labels.excess}</dt><dd>{labels.excessDefinition} Scope: {selected.pre_balancing_excess_scope.replaceAll("_", " ")}.</dd></div><div><dt>{labels.curtailment}</dt><dd>{labels.curtailmentDefinition}</dd></div><div><dt>Marginal curtailment</dt><dd>{selected.marginal_curtailment_reason}</dd></div></dl></details><p className="provenance-line">Coverage {selected.coverage_status.replaceAll("_", " ")} · source ledger {summary.source_artifact_sha256 ?? "hash unavailable"}</p>
      </section>}</>}
  </div>;
}

type OptionalResultDomain = "network_dc" | "network_expansion";
const PUBLIC_RESULT_DOMAINS: OptionalResultDomain[] = ["network_dc", "network_expansion"];


function metricValue(metric?: ResultMetric) {
  if (!metric || metric.value == null) return "Not evaluated";
  const value = typeof metric.value === "number" ? formatNumber(metric.value, 5) : String(metric.value);
  return `${value}${metric.unit ? ` ${metric.unit}` : ""}`;
}

function DomainMetricCards({ metrics }: { metrics: Record<string, ResultMetric> }) {
  return <div className="domain-result-metrics">{Object.entries(metrics).map(([key, metric]) => <article key={key}>
    <small>{key.replaceAll("_", " ")}</small><b>{metricValue(metric)}</b>
    <em>{metric.definition_id}</em>
  </article>)}</div>;
}

function TopologySchematic({ summary }: { summary: NetworkSummaryPayload }) {
  const buses = summary.topology.buses;
  const width = 720; const height = 330; const cx = width / 2; const cy = height / 2; const radius = Math.min(width, height) * .34;
  const positions = new Map(buses.map((bus, index) => {
    const angle = (Math.PI * 2 * index / Math.max(1, buses.length)) - Math.PI / 2;
    return [String(bus.bus_id ?? `bus-${index + 1}`), { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }] as const;
  }));
  return <div className="topology-schematic"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Electrical topology schematic; positions are not geographic">
    {summary.topology.branches.map((branch, index) => { const from = positions.get(String(branch.from_bus)); const to = positions.get(String(branch.to_bus)); if (!from || !to) return null; return <g key={String(branch.branch_id ?? index)}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} /><text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 6}>{String(branch.branch_id ?? "branch")}</text></g>; })}
    {buses.map((bus, index) => { const id = String(bus.bus_id ?? `bus-${index + 1}`); const point = positions.get(id)!; const reference = summary.topology.reference_buses.includes(id); return <g key={id} className={reference ? "reference-bus" : ""}><circle cx={point.x} cy={point.y} r={reference ? 18 : 15} /><text x={point.x} y={point.y + 4} textAnchor="middle">{id}</text></g>; })}
  </svg><p>Electrical schematic only — node positions do not represent geography. A ring layout is used because no coordinate claim is made by this result artifact.</p></div>;
}

function SystemResultsView({ run, onOpenMarket, onOpenNetwork }: { run?: ModelRun; onOpenMarket: () => void; onOpenNetwork: () => void }) {
  const [capabilities, setCapabilities] = useState<DomainCapabilitiesPayload | null>(null);
  const [domain, setDomain] = useState<OptionalResultDomain | null>(null);
  const [year, setYear] = useState(0); const [selectedPeriod, setSelectedPeriod] = useState("");
  const [network, setNetwork] = useState<NetworkSummaryPayload | null>(null);
  const [periods, setPeriods] = useState<NetworkPeriodPayload | null>(null);
  const [branches, setBranches] = useState<NetworkBranchPayload | null>(null);
  const [expansion, setExpansion] = useState<ExpansionSummaryPayload | null>(null);
  const [events, setEvents] = useState<ExpansionEventPayload | null>(null);
  const [error, setError] = useState("");

  const availableDomains = useMemo(() => {
    if (!capabilities) return [] as OptionalResultDomain[];
    return PUBLIC_RESULT_DOMAINS
      .filter((item) => ["supported", "experimental"].includes(capabilities.capabilities[item]?.status));
  }, [capabilities]);

  useEffect(() => {
    if (!run) return;
    let active = true;
    void getJson<DomainCapabilitiesPayload>(`${API}/runs/${run.id}/domains/capabilities`).then((payload) => {
      if (!active) return;
      const available = PUBLIC_RESULT_DOMAINS
        .filter((item) => ["supported", "experimental"].includes(payload.capabilities[item]?.status));
      const first = available[0] ?? null;
      setCapabilities(payload); setDomain(first); setYear(first ? payload.capabilities[first].years?.[0] ?? 0 : 0); setError("");
    }).catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [run]);

  useEffect(() => {
    if (!run || !domain) return;
    let active = true;
    if (domain === "network_dc" && year) {
      void Promise.all([
        getJson<NetworkSummaryPayload>(`${API}/runs/${run.id}/domains/network/summary?year=${year}`),
        getJson<NetworkPeriodPayload>(`${API}/runs/${run.id}/domains/network/periods?year=${year}&limit=24`),
      ]).then(([summary, page]) => { if (!active) return; setNetwork(summary); setPeriods(page); setSelectedPeriod(page.items[0]?.period_id ?? ""); setError(""); }).catch((reason: Error) => { if (active) setError(reason.message); });
    } else if (domain === "network_expansion") {
      void Promise.all([
        getJson<ExpansionSummaryPayload>(`${API}/runs/${run.id}/domains/expansion/summary`),
        getJson<ExpansionEventPayload>(`${API}/runs/${run.id}/domains/expansion/events?limit=100`),
      ]).then(([summary, page]) => { if (active) { setExpansion(summary); setEvents(page); setError(""); } }).catch((reason: Error) => { if (active) setError(reason.message); });
    }
    return () => { active = false; };
  }, [domain, run, year]);

  useEffect(() => {
    if (!run || domain !== "network_dc" || !year || !selectedPeriod) return;
    let active = true;
    void getJson<NetworkBranchPayload>(`${API}/runs/${run.id}/domains/network/branches?year=${year}&period_id=${encodeURIComponent(selectedPeriod)}&limit=100`)
      .then((payload) => { if (active) setBranches(payload); }).catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [domain, run, selectedPeriod, year]);

  if (!run) return <div className="page"><div className="empty-run"><b>No run selected</b><p>Select a completed run before opening optional-domain results.</p></div></div>;
  const labels: Record<OptionalResultDomain, string> = { network_dc: "DC network", network_expansion: "Transmission expansion" };
  const selectedCapability = domain ? capabilities?.capabilities[domain] : null;
  const selectedBusPeriod = periods?.items.find((item) => item.period_id === selectedPeriod);
  return <div className="page evidence-page"><div className="page-title"><div><span>Optional-domain evidence</span><h2>Network, water and expansion results</h2><p>Tabs are indexed from this completed run&apos;s frozen graph and artifacts. VALUE does not infer missing domains or turn “not evaluated” into zero.</p></div><Badge tone={run.status === "completed" || run.status === "archived" ? "good" : "warn"}>{run.status}</Badge></div>
    {error && <div className="error-box">{error}</div>}
    {capabilities && <section className="domain-capability-strip" aria-label="Optional-domain capability status">{PUBLIC_CAPABILITY_DOMAINS.map((key) => [key, capabilities.capabilities[key]] as const).filter((entry): entry is readonly [string, DomainCapability] => Boolean(entry[1])).map(([key, item]) => <article key={key}><span>{domainLabel(key)}</span><Badge tone={item.status === "supported" ? "good" : item.status === "experimental" ? "warn" : "neutral"}>{item.status.replaceAll("_", " ")}</Badge><small>{item.claim ?? item.reason ?? "Artifact-backed result available."}</small></article>)}</section>}
    {capabilities && !availableDomains.length && (["supported", "experimental"].includes(capabilities.capabilities.zonal_redispatch?.status ?? "")
      ? <div className="empty-run"><b>Zonal network results are on their own page</b><p>This Run uses the zonal network model. Its congestion, redispatch and lost-load results are under Network &amp; redispatch; no DC network, hydrology or expansion artifact is attached.</p><button type="button" className="secondary" onClick={onOpenNetwork}>Open Network &amp; redispatch →</button></div>
      : <div className="empty-run"><b>No optional-domain result artifact is attached to this Run</b><p>{run.modules?.balancing === "value-copperplate-balancing" || !run.modules?.balancing ? "This Run uses the national market without internal network constraints (copperplate)." : "The selected modules recorded no network, hydrology or expansion artifact."} No network, hydrology or expansion quantities are reconstructed. Market results are in Market replay.</p><button type="button" className="secondary" onClick={onOpenMarket}>Open Market replay →</button></div>)}
    {!!availableDomains.length && <><div className="audit-tabs domain-result-tabs" role="tablist" aria-label="Optional-domain result tabs">{availableDomains.map((item) => <button key={item} role="tab" aria-selected={domain === item} className={domain === item ? "active" : ""} onClick={() => { setDomain(item); setYear(capabilities?.capabilities[item].years?.[0] ?? 0); }}>{labels[item]}</button>)}</div>
      {selectedCapability?.years?.length ? <label className="inline-select domain-year"><span>Model year</span><select value={year} onChange={(event) => setYear(Number(event.target.value))}>{selectedCapability.years.map((item) => <option key={item}>{item}</option>)}</select></label> : null}
    </>}
    {domain === "network_dc" && network && <div className="domain-result-stack"><section className="panel"><div className="panel-head"><div><span>DC network · {network.year}</span><h3>Nodal balance and constrained transfers</h3></div><Badge tone="good">integrity checked</Badge></div><DomainMetricCards metrics={network.metrics} /><div className="network-result-layout"><TopologySchematic summary={network} /><div><h4>Annual branch envelope</h4><div className="table-scroll compact-table"><table><thead><tr><th>Branch</th><th>Endpoints</th><th>Rating</th><th>Maximum flow</th><th>Peak utilisation</th></tr></thead><tbody>{network.branch_summary.map((item) => <tr key={item.branch_id}><td>{item.branch_id}</td><td>{item.from_bus} → {item.to_bus}</td><td>{item.rating_mw == null ? "Not evaluated" : `${withUnit(formatNumber(item.rating_mw), "MW")}`}</td><td>{withUnit(formatNumber(item.maximum_absolute_flow_mw), "MW")}</td><td>{item.maximum_utilisation_fraction == null ? "Not evaluated" : `${withUnit(formatNumber(item.maximum_utilisation_fraction * 100, 1), "%", "")}`}</td></tr>)}</tbody></table></div></div></div><button className="audit-link" onClick={onOpenMarket}>Open storage SOC in the authoritative Market replay ledger</button><p className="provenance-line">Declared input {network.source_artifacts.declared_input_sha256} · period index {network.source_artifacts.period_index_sha256}</p></section>
      {periods && <section className="panel"><div className="panel-head"><div><span>Bounded period query</span><h3>Angles, nodal LP duals and branch flows</h3></div><Badge tone="blue">{periods.items.length} of {periods.total} periods loaded</Badge></div><div className="period-chip-list" role="list" aria-label="Loaded network periods">{periods.items.map((item) => <button key={item.period_id} className={selectedPeriod === item.period_id ? "selected" : ""} onClick={() => setSelectedPeriod(item.period_id)}>{item.period_id}</button>)}</div>{selectedBusPeriod && <><div className="table-scroll"><table><thead><tr><th>Bus</th><th>Injection</th><th>Withdrawal</th><th>Load shed</th><th>Angle</th><th>Nodal LP dual</th></tr></thead><tbody>{selectedBusPeriod.buses.map((item) => <tr key={item.bus_id}><td>{item.bus_id}</td><td>{withUnit(formatNumber(item.injection_mwh), "MWh")}</td><td>{withUnit(formatNumber(item.withdrawal_mwh), "MWh")}</td><td>{withUnit(formatNumber(item.blackout_mwh), "MWh")}</td><td>{formatNumber(item.angle_rad, 6)} rad</td><td>{withUnit(formatNumber(item.price_gbp_per_mwh), "/MWh", "", "£")}</td></tr>)}</tbody></table></div>{branches && <div className="table-scroll"><table><thead><tr><th>Branch</th><th>Endpoints</th><th>Flow</th><th>Rating</th><th>Utilisation</th></tr></thead><tbody>{branches.items.map((item) => <tr key={`${item.period_id}-${item.branch_id}`}><td>{item.branch_id}</td><td>{item.from_bus} → {item.to_bus}</td><td>{withUnit(formatNumber(item.flow_mw), "MW")}</td><td>{item.rating_mw == null ? "Not evaluated" : `${withUnit(formatNumber(item.rating_mw), "MW")}`}</td><td>{item.utilisation_fraction == null ? item.utilisation_status.replaceAll("_", " ") : `${withUnit(formatNumber(item.utilisation_fraction * 100, 1), "%", "")}`}</td></tr>)}</tbody></table></div>}</>}</section>}
    </div>}
    {domain === "network_expansion" && expansion && <div className="domain-result-stack"><section className="panel"><div className="panel-head"><div><span>Experimental transmission lifecycle</span><h3>{expansion.lineage}</h3></div><Badge tone="warn">{expansion.status}</Badge></div><div className="expansion-year-grid">{expansion.years.map((item) => <article key={item.year}><b>{item.year}</b><span>{item.proposals} proposed</span><span>{item.admitted} admitted</span><span>{item.commissioned} commissioned</span><span>{item.failed} failed · {item.retired} retired</span></article>)}</div><p className="audit-note">Before/after values are temporal descriptions only. Counterfactual effect: {expansion.counterfactual_claim.replaceAll("_", " ")}.</p></section>{events && <section className="panel"><div className="panel-head"><div><span>Candidate lineage events</span><h3>{events.total} indexed events</h3></div><Badge tone="blue">first {events.items.length}</Badge></div><div className="table-scroll"><table><thead><tr><th>Year / event</th><th>Candidate</th><th>Project / asset</th><th>Corridor</th><th>Build</th><th>Reason</th></tr></thead><tbody>{events.items.map((item) => <tr key={item.event_id}><td><b>{item.year}</b><small>{item.event_type}</small></td><td>{item.candidate_id}</td><td><small>{item.project_id ?? "No project yet"}</small><small>{item.asset_id ?? "No commissioned asset"}</small></td><td>{item.corridor_id}<small>{item.from_bus} → {item.to_bus}</small></td><td>{item.circuits} × {withUnit(formatNumber(item.rating_mw), "MW")}</td><td>{item.reason_code}</td></tr>)}</tbody></table></div><p className="provenance-line">Source artifact {events.source_artifact_sha256}</p></section>}</div>}
    {capabilities?.capabilities.hydrology && <section className="panel unavailable-domain"><div><span>Natural-flow hydrology</span><h3>{capabilities.capabilities.hydrology.status.replaceAll("_", " ")}</h3><p>{capabilities.capabilities.hydrology.reason ?? "A typed hydrology result index is available."}</p></div><Badge tone={capabilities.capabilities.hydrology.status === "experimental" ? "warn" : "neutral"}>{capabilities.capabilities.hydrology.status.replaceAll("_", " ")}</Badge></section>}
    {capabilities && <p className="provenance-line">Run {String(capabilities.identity.run_id ?? run.id)} · project revision {String(capabilities.identity.project_revision_sha256 ?? "not recorded")} · graph {String(capabilities.identity.graph_sha256 ?? "not recorded")}</p>}
  </div>;
}

/** An Enable/Remove refusal with its backend code (spec 11.4). */
class EntryLifecycleError extends Error {
  constructor(message: string, readonly code?: string) { super(message); }
}

export default function Home() {
  const [view, setView] = useState<View>("overview");
  // S-D10: the page a launch started from; a Run that finishes starting does not pull the user back.
  const viewRef = useRef<View>("overview");
  useEffect(() => { viewRef.current = view; }, [view]);
  const [activePath, setActivePath] = useState<CommunityPath | null>(null);
  const [readMeOpen, setReadMeOpen] = useState(false);
  const [locationReady, setLocationReady] = useState(false);
  const pendingLocation = useRef<WorkspaceLocation | null>(null);
  const replaceLocation = useRef(true);
  const [workspace, setWorkspace] = useState<Workspace>(emptyWorkspace);
  const [definitions, setDefinitions] = useState<ParameterDefinition[]>([]);
  const [online, setOnline] = useState(false);
  const [launcherRequired, setLauncherRequired] = useState(false);
  // P0-3 S8: the rail shows degraded after a failure or a degraded health
  // status, and offline only after OFFLINE_AFTER_FAILURES consecutive failures.
  const [refreshFailures, setRefreshFailures] = useState(0);
  const [workspaceLoaded, setWorkspaceLoaded] = useState(false);
  const [health, setHealth] = useState<{ status: string; version?: string; degraded_reasons?: { code: string; count: number }[] } | null>(null);
  const [pollTick, setPollTick] = useState(0);
  const connectionState = serviceState(refreshFailures, health?.status, workspaceLoaded);
  const [selectedPackId, setSelectedPackId] = useState("value-uk-1000twh-reproduction");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedRunDetail, setSelectedRunDetail] = useState<ModelRun | null>(null);
  const [uploading, setUploading] = useState("");
  const [dataBundle, setDataBundle] = useState<File | null>(null);
  const [dataRights, setDataRights] = useState(false);
  const [dataInstalling, setDataInstalling] = useState(false);
  const [dataInstallProgress, setDataInstallProgress] = useState(0);
  const [dataInstallPhase, setDataInstallPhase] = useState<"idle" | "uploading" | "verifying">("idle");
  const dataInstallRequest = useRef<XMLHttpRequest | null>(null);
  const [researchSuiteBundle, setResearchSuiteBundle] = useState<File | null>(null);
  const [researchSuiteRights, setResearchSuiteRights] = useState(false);
  const [researchSuiteInstalling, setResearchSuiteInstalling] = useState(false);
  const [researchSuiteInstallProgress, setResearchSuiteInstallProgress] = useState(0);
  const [researchSuiteInstallPhase, setResearchSuiteInstallPhase] = useState<"idle" | "uploading" | "verifying">("idle");
  const [researchSuiteSummary, setResearchSuiteSummary] = useState<ResearchSuiteSummary | null>(null);
  const researchSuiteInstallRequest = useRef<XMLHttpRequest | null>(null);
  const [moduleBundle, setModuleBundle] = useState<File | null>(null);
  // M-D9 / F-D6 (round R1-5): a successful install also clears the native file input.
  const [bundleInputGeneration, setBundleInputGeneration] = useState(0);
  const [moduleTrust, setModuleTrust] = useState(false);
  const [moduleInstalling, setModuleInstalling] = useState(false);
  const [moduleLifecycle, setModuleLifecycle] = useState("");
  const [extensionBundle, setExtensionBundle] = useState<File | null>(null);
  const [extensionTrust, setExtensionTrust] = useState(false);
  const [extensionInstalling, setExtensionInstalling] = useState(false);
  const [extensionLifecycle, setExtensionLifecycle] = useState("");
  const [launching, setLaunching] = useState("");
  const [replayTarget, setReplayTarget] = useState<ReplayTarget | null>(null);
  // "Show stress events" (spec 2.3 notice 4): open Market replay at the full-year stress-event list (spec 4.4).
  const [stressEventsFocus, setStressEventsFocus] = useState(0);
  const [inspectTarget, setInspectTarget] = useState<{ tab: AuditTab; nonce: number } | null>(null);
  // R3-N3 (round R2): a requested Inspect tab is used once; ordinary navigation opens Inspect on its own default tab.
  const openView = (next: View) => { setInspectTarget(null); setView(next); };
  // Spec 7 / X0 S12: methodology catalogue for the Study composer, and the pending migration confirmation.
  const [methodologyCatalogue, setMethodologyCatalogue] = useState<MethodologyCatalogue | null>(null);
  const [methodologyError, setMethodologyError] = useState("");
  const [migrationPrompt, setMigrationPrompt] = useState<{ projectId: string; studyName?: string; migration: RevisionMigration; nonce: number } | null>(null);
  // S-D12: null until the user picks a scope; until then "Check for" follows the selected Run.
  const [preflightMode, setPreflightMode] = useState<RunMode | null>(null);
  const [storedPreflight, setPreflight] = useState<PreflightReport | null>(null);
  const [pendingPreflightKey, setPendingPreflightKey] = useState<string | null>(null);
  const preflightRequest = useRef(0);
  const [notice, setNotice] = useState("");
  // S-D12 / M2-N1: the start notice follows its Run to completion or failure.
  const [startedRun, setStartedRun] = useState<StartedRunNotice | null>(null);
  const [parameterValues, setParameterValues] = useState<Record<string, unknown>>({});
  const [runtimeValues, setRuntimeValues] = useState<Record<string, unknown>>({ "runtime.market_trace_level": "summary" });
  const [resolvedSources, setResolvedSources] = useState<Record<string, { source?: string }>>({});
  const [draftResolution, setDraftResolution] = useState<DraftResolution | null>(null);
  const [draftResolving, setDraftResolving] = useState(false);
  const [draftResolutionError, setDraftResolutionError] = useState("");
  const [composerInitialStep, setComposerInitialStep] = useState(1);
  const [draftPackCopyName, setDraftPackCopyName] = useState("");
  const [copyingDraftPack, setCopyingDraftPack] = useState(false);
  const [dataContextId, setDataContextId] = useState("draft");
  const [journeyTargetPackId, setJourneyTargetPackId] = useState("");
  const [journeyData, setJourneyData] = useState<{ sourceStudyId: string; sourceRevisionSha256: string; targetPackId: string } | null>(null);
  const dataPreviewRequest = useRef(0);
  const [savedDataResolution, setSavedDataResolution] = useState<{ project: Project; manifestSha256?: string; resolution: DraftResolution } | null>(null);
  const [dataPreviewResult, setDataPreview] = useState<{ contextId: string; packId: string; manifestSha256?: string; preview: DataPreview } | null>(null);
  const [dataPreviewLoading, setDataPreviewLoading] = useState("");
  const [domainExtensionIds, setDomainExtensionIds] = useState<string[]>([]);
  const [editingBaseRevision, setEditingBaseRevision] = useState<string | undefined>();
  const [editingProjectId, setEditingProjectId] = useState<string | undefined>();
  const [frozenRunReadiness, setFrozenRunReadiness] = useState<ResourceReadiness | null>(null);
  const [frozenRunProject, setFrozenRunProject] = useState<Project | null>(null);
  const [frozenInputSnapshot, setFrozenInputSnapshot] = useState<FrozenInputSnapshot | null>(null);
  const [frozenRunSelectionId, setFrozenRunSelectionId] = useState("");
  const [value101Tutorial, setValue101Tutorial] = useState<Value101TutorialDescriptor>(VALUE_101_FALLBACK);
  const [value101Loading, setValue101Loading] = useState(true);
  const [value101Error, setValue101Error] = useState("");
  const [projectForm, setProjectForm] = useState<StudyForm>({
    name: "VALUE UK transition", purpose: "", start_year: 2025, end_year: 2034,
    modules: { psm: "value-bid-at-cost-psm", investment: "agent-investment", pipeline: "planning-pipeline", vre_cap: "vre-expansion-cap", storage_cap: "value-storage-expansion-policy", transition: "value-annual-state-transition", storage_cost: "dynamic-annual-storage-cost" } as Record<string, string>,
    selected_extensions: [], extension_parameters: {}, maturity_acknowledgements: {},
    market_configuration: {},
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const location = readWorkspaceLocation(window.location.search);
      pendingLocation.current = location;
      setView(location.view);
      setActivePath(location.path);
      setSelectedProjectId(location.studyId);
      setSelectedRunId(location.runId);
      setDataContextId(location.dataContextId);
      // N-5 (round R1-5): a reload of the journey Data page restores its source revision and target pack.
      const journey = journeyFromLocation(location);
      if (journey) { setJourneyData(journey); setJourneyTargetPackId(journey.targetPackId); }
      setLocationReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const next = await getJson<Workspace>(`${API}/workspace`);
      setWorkspace({
        ...next,
        module_installations: next.module_installations ?? [],
        extension_installations: next.extension_installations ?? [],
        study_trash: next.study_trash ?? [],
        module_slots: next.module_slots ?? [],
        extensions: (next.extensions ?? []).map((extension) => ({ ...extension, name: modelDisplayName(extension.name) })),
        data_packs: next.data_packs.map((pack) => ({ ...pack, name: modelDisplayName(pack.name) })),
        modules: next.modules.map((module) => ({ ...module, name: modelDisplayName(module.name), description: modelDisplayName(module.description) })),
        projects: next.projects.map((project) => ({ ...project, name: modelDisplayName(project.name) })),
        runs: next.runs.map((run) => ({ ...run, project_name: modelDisplayName(run.project_name) })),
      });
      setOnline(true);
      setWorkspaceLoaded(true);
      setRefreshFailures(0);
      void getJson<{ status: string; version?: string; degraded_reasons?: { code: string; count: number }[] }>(`${API}/health`).then(setHealth).catch(() => setHealth(null));
      // R4 R-低6: a recovered or overlay pack is never the default selection.
      setSelectedPackId((current) => defaultDraftPackId(next.data_packs, current));
      const requestedRunId = pendingLocation.current?.runId;
      const requestedRun = next.runs.find((run) => run.id === requestedRunId);
      // Keep explicit identities, even when unavailable. Never silently replace a shared Run link.
      setSelectedProjectId((current) => current || requestedRun?.project_id || next.projects[0]?.id || "");
      pendingLocation.current = null;
      return next;
    } catch (error) {
      if (classifyRefreshFailure(error) === "launcher") { setLauncherRequired(true); return null; }
      // The last workspace stays on screen (readable); actions that need the
      // service are disabled while it is not online.
      setOnline(false); setRefreshFailures((current) => current + 1); return null;
    }
  }, []);
  const refreshValue101Tutorial = useCallback(async () => {
    setValue101Loading(true);
    setValue101Error("");
    try {
      setValue101Tutorial(await getJson<Value101TutorialDescriptor>(`${API}/tutorials/value-101`));
    } catch (reason) {
      setValue101Tutorial(VALUE_101_FALLBACK);
      setValue101Error(reason instanceof Error ? reason.message : "The local tutorial descriptor is unavailable.");
    } finally {
      setValue101Loading(false);
    }
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
      void refreshValue101Tutorial();
      void getJson<{ parameters: ParameterDefinition[] }>(`${API}/parameters`)
        .then((payload) => setDefinitions(payload.parameters)).catch(() => undefined);
      void getJson<unknown>(`${API}/methodology/profiles`)
        .then((payload) => { if (isMethodologyCatalogue(payload)) { setMethodologyCatalogue(payload); setMethodologyError(""); } else setMethodologyError("unexpected catalogue format"); })
        .catch((reason: unknown) => setMethodologyError(reason instanceof Error ? reason.message : "catalogue unavailable"));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh, refreshValue101Tutorial]);
  const projectRuns = useMemo(
    () => workspace.runs.filter((run) => run.project_id === selectedProjectId),
    [selectedProjectId, workspace.runs],
  );
  const selectedRunSummary = selectWorkspaceRun(workspace.runs, selectedProjectId, selectedRunId);
  useEffect(() => {
    if (!selectedRunSummary) return;
    let current = true;
    void getJson<ModelRun>(`${API}/runs/${selectedRunSummary.id}`)
      .then((run) => { if (current) setSelectedRunDetail({ ...run, project_name: modelDisplayName(run.project_name) }); })
      .catch(() => { if (current) setSelectedRunDetail(null); });
    return () => { current = false; };
  }, [selectedRunSummary]);
  // R-D6 / S-D11: the input snapshot is read once per Run, after the Run has
  // left queued/snapshotting (not on every workspace poll), and the optional
  // resource-readiness file only when the snapshot records it.
  const frozenRunId = selectedRunSummary?.id ?? "";
  const frozenSnapshotWritten = Boolean(selectedRunSummary) && !["queued", "snapshotting"].includes(selectedRunSummary?.status ?? "");
  useEffect(() => {
    if (!frozenRunId || !frozenSnapshotWritten) return;
    let active = true;
    const artifact = `${API}/runs/${frozenRunId}/artifacts/input-snapshot`;
    void Promise.all([
      getJson<Project>(`${artifact}/project.json`).catch(() => null),
      getJson<FrozenInputSnapshot>(`${artifact}/snapshot.json`).catch(() => null),
    ]).then(async ([project, snapshot]) => {
      const readiness = snapshot?.resource_readiness_path === "resource-readiness.json"
        ? await getJson<ResourceReadiness>(`${artifact}/resource-readiness.json`).catch(() => null) : null;
      if (!active) return;
      setFrozenRunReadiness(readiness); setFrozenRunProject(project); setFrozenInputSnapshot(snapshot); setFrozenRunSelectionId(frozenRunId);
    });
    return () => { active = false; };
  }, [frozenRunId, frozenSnapshotWritten]);
  const hasActiveRun = workspace.runs.some((run) => ["queued", "snapshotting", "running", "cancel_requested"].includes(run.status));
  const activeRunCount = workspace.runs.filter((run) => ["queued", "snapshotting", "running", "cancel_requested"].includes(run.status)).length;
  // Poll while a Run is active or the service is failing: every 2 s, doubling
  // after each consecutive failure up to 30 s (P0-3 S8).
  useEffect(() => {
    if (!hasActiveRun && refreshFailures === 0) return;
    const timer = window.setTimeout(() => { void refresh().finally(() => setPollTick((tick) => tick + 1)); }, pollDelay(refreshFailures));
    return () => window.clearTimeout(timer);
  }, [hasActiveRun, pollTick, refresh, refreshFailures]);

  const selectedPack = useMemo(() => workspace.data_packs.find((pack) => pack.id === selectedPackId) ?? workspace.data_packs.find((pack) => pack.id === defaultDraftPackId(workspace.data_packs, selectedPackId)), [selectedPackId, workspace.data_packs]);
  const selectedProject = workspace.projects.find((project) => project.id === selectedProjectId);
  const selectedProjectPack = workspace.data_packs.find((pack) => pack.id === selectedProject?.data_pack_id);
  const allowedStudyModes = runModesForStudy(selectedProject, selectedProjectPack);
  const canRunMode = (mode: RunMode) => allowedStudyModes.includes(mode);
  const effectivePreflightMode = selectedRunScope(preflightMode ?? selectedRunSummary?.mode ?? "smoke", allowedStudyModes);
  const currentPreflightKey = effectivePreflightMode ? preflightKey(selectedProject, effectivePreflightMode) : null;
  const checkingPreflight = Boolean(currentPreflightKey && pendingPreflightKey === currentPreflightKey);
  const preflight = effectivePreflightMode && preflightMatches(storedPreflight, selectedProject, effectivePreflightMode) ? storedPreflight : null;
  function selectRunProject(projectId: string) {
    const nextProject = workspace.projects.find((project) => project.id === projectId);
    const nextPack = workspace.data_packs.find((pack) => pack.id === nextProject?.data_pack_id);
    setSelectedProjectId(projectId);
    setSelectedRunId("");
    setPreflight(null);
    const nextModes = runModesForStudy(nextProject, nextPack);
    if (preflightMode && !nextModes.includes(preflightMode) && nextModes.length) {
      setPreflightMode(selectedRunScope(preflightMode, nextModes)!);
    }
  }
  const zonalPreflight = preflight?.checks?.domain_readiness?.sections.zonal_network;
  const selectedRun = selectedRunDetail && selectedRunDetail.id === selectedRunSummary?.id ? selectedRunDetail : selectedRunSummary;
  const selectedRunSourceMutable = sourceStudyAllowsDerivedRun(selectedRun?.source_study_status);
  const isRunView = ["run", "marketReplay", "curtailment", "networkRedispatch", "systems", "audit"].includes(view);
  const selectedRunContext = resolveRunContext({ run: selectedRun, frozen: {
    runId: frozenRunSelectionId,
    status: frozenRunSelectionId === selectedRun?.id ? frozenRunProject ? "ready" : "unavailable" : "loading",
    project: frozenRunProject, snapshot: frozenInputSnapshot,
  } });

  useEffect(() => {
    const restoreLocation = () => {
      const location = readWorkspaceLocation(window.location.search);
      const linkedRun = workspace.runs.find((run) => run.id === location.runId);
      replaceLocation.current = true;
      setView(location.view);
      setActivePath(location.path);
      setSelectedProjectId(location.studyId || linkedRun?.project_id || "");
      setSelectedRunId(location.runId);
      setDataContextId(location.dataContextId);
      const journey = journeyFromLocation(location);
      if (journey) { setJourneyData(journey); setJourneyTargetPackId(journey.targetPackId); }
      setReadMeOpen(false);
    };
    window.addEventListener("popstate", restoreLocation);
    return () => window.removeEventListener("popstate", restoreLocation);
  }, [workspace.runs]);

  useEffect(() => {
    if (!locationReady || connectionState === "loading") return;
    const search = writeWorkspaceLocation(window.location.search, {
      view, path: activePath, studyId: selectedProjectId, dataContextId,
      runId: selectedRunId || selectedRunSummary?.id || "",
      journey: journeyData ? { sourceRevisionSha256: journeyData.sourceRevisionSha256, targetPackId: journeyData.targetPackId } : undefined,
    });
    if (search !== window.location.search) {
      const url = `${window.location.pathname}${search}${window.location.hash}`;
      if (replaceLocation.current) window.history.replaceState(null, "", url);
      else window.history.pushState(null, "", url);
    }
    replaceLocation.current = false;
  }, [activePath, connectionState, dataContextId, journeyData, locationReady, selectedProjectId, selectedRunId, selectedRunSummary?.id, view]);

  function chooseCommunityPath(path: CommunityPath) {
    setActivePath(path);
    if (path === "reproduce" || path === "data") setView("journey");
    else setView("models");
  }

  useEffect(() => {
    if (view !== "models" || (activePath !== "module" && activePath !== "function")) return;
    document.getElementById(activePath === "module" ? "module-author-workbench" : "extension-author-workbench")?.scrollIntoView({ block: "start" });
  }, [activePath, view]);
  const value101Project = workspace.projects.find((project) => project.id === "value-101-baseline");
  const value101Trash = workspace.study_trash.find((entry) => entry.study_id === "value-101-baseline");
  const value101DayRun = workspace.runs.find((run) => run.project_id === value101Project?.id && run.mode === "value_101_day");
  const value101AnnualRun = workspace.runs.find((run) => run.project_id === value101Project?.id && run.mode === "two_year");
  // A24-5 / L-4: Learn shows the preparation of its lesson Runs (stage and elapsed time).
  const value101Preparations = workspace.runs
    .filter((run) => run.project_id === value101Project?.id || run.project_id === "value-101-network-copperplate" || run.project_id === "value-101-network-constrained")
    .flatMap((run) => {
      const text = preparationProgressText(run);
      if (!text) return [];
      const label = run.project_id === "value-101-network-copperplate" ? "Copperplate Run" : run.project_id === "value-101-network-constrained" ? "Constrained Run" : run.mode === "value_101_day" ? "One-day Run" : run.mode === "two_year" ? "Two-year Run" : "Lesson Run";
      return [{ id: run.id, label, text }];
    });
  const teachingProject = Boolean(selectedProject?.extensions?.value_101);
  const readyModules = workspace.modules.filter((module) => module.status === "ready").length;

  const draftPackManifest = selectedPack?.manifest_sha256;
  useEffect(() => {
    if (!selectedPackId || !online) return;
    setDraftResolution(null); setDraftResolving(true);
    let active = true;
    const timer = window.setTimeout(() => {
      setDraftResolving(true); setDraftResolutionError("");
      void fetch(`${API}/projects/resolve-draft`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          schema_version: "value.study-draft/v1", ...projectForm,
          data_pack_id: selectedPackId, parameters: parameterValues,
          runtime_options: runtimeValues,
        }),
      }).then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Draft resolution failed");
        if (active) setDraftResolution(payload as DraftResolution);
      }).catch((reason: Error) => {
        if (active) { setDraftResolutionError(reason.message); setDraftResolution(null); }
      }).finally(() => { if (active) setDraftResolving(false); });
    }, 220);
    return () => { active = false; window.clearTimeout(timer); };
  }, [online, parameterValues, projectForm, runtimeValues, selectedPackId, draftPackManifest]);

  const journeySource = workspace.projects.find((project) => project.id === journeyData?.sourceStudyId);
  const journeySourceCurrent = Boolean(journeySource && journeySource.revision_sha256 === journeyData?.sourceRevisionSha256);
  const journeySourcePack = workspace.data_packs.find((pack) => pack.id === journeySource?.data_pack_id);
  const isJourneyData = dataContextId === "journey";
  const dataContextProject = useMemo(() => isJourneyData
    ? journeySourceCurrent && journeySource && journeyData?.targetPackId
      ? { ...journeySource, data_pack_id: journeyData.targetPackId } : undefined
    : dataContextId === "draft" ? undefined : workspace.projects.find((item) => item.id === dataContextId),
  [dataContextId, isJourneyData, journeyData, journeySource, journeySourceCurrent, workspace.projects]);
  const dataContextPackId = isJourneyData ? journeyData?.targetPackId ?? ""
    : dataContextId === "draft" ? selectedPackId : dataContextProject?.data_pack_id ?? "";
  const dataContextPack = workspace.data_packs.find((item) => item.id === dataContextPackId);
  const dataManifestSha256 = dataContextPack?.manifest_sha256;
  const journeyNetworkPackId = journeySource?.market_configuration?.network_pack_id;
  const journeyReadOnlyReason = !online ? "本地服务未连接，暂不能更改数据。"
    : !journeyData ? "引导上下文已失效，请返回研究引导重新选择基线和目标数据包。"
    : !journeySourceCurrent ? "基线已改变或不可用，请返回研究引导核对保存版本。"
    : !dataContextPack ? "先在研究引导复制或选择一个独立的目标数据包。"
    : dataContextPack.id === journeySource?.data_pack_id ? "不能改写基线数据包，请先创建独立副本。"
    : dataContextPack.data_pack_type === "network_overlay" ? "此页只编辑基础输入；网络覆盖包请在 Data Workbench 管理。"
    : workspace.projects.some((project) => project.data_pack_id === dataContextPack.id)
      ? "该数据包已被保存的 Study 引用。请再次复制后编辑，保留已有研究的输入。"
    : !dataManifestSha256 ? "未取得目标数据包版本，请刷新工作区后重试。" : "";

  useEffect(() => {
    if (!dataContextProject) return;
    let active = true;
    void fetch(`${API}/projects/resolve-draft`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dataContextProject),
    }).then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Study data resolution failed");
      if (active) setSavedDataResolution({ project: dataContextProject, manifestSha256: dataManifestSha256, resolution: payload as DraftResolution });
    }).catch((reason: Error) => { if (active) { setSavedDataResolution(null); setNotice(reason.message); } });
    return () => { active = false; };
  }, [dataContextProject, dataManifestSha256]);

  const dataContextResolution = dataContextId === "draft" ? draftResolution
    : savedDataResolution?.project === dataContextProject && savedDataResolution?.manifestSha256 === dataManifestSha256 ? savedDataResolution?.resolution : null;
  const activeDataSlots = dataContextResolution?.active_dataset_slots ?? workspace.dataset_slots;
  const dataGroups = [...new Set(activeDataSlots.map((slot) => slot.group))];
  const dataContextExtensions = dataContextId === "draft" ? projectForm.selected_extensions
    : dataContextProject?.selected_extensions ?? [];
  const dataPreview = dataPreviewResult?.contextId === dataContextId && dataPreviewResult.packId === dataContextPackId
    && dataPreviewResult.manifestSha256 === dataManifestSha256 ? dataPreviewResult.preview : null;
  // Spec 11.2 (S-D2): the three validation layers of the data pack in context.
  const [packValidationResult, setPackValidationResult] = useState<{ key: string; report: DataPackValidationReport | null; error: string } | null>(null);
  const [packValidationNonce, setPackValidationNonce] = useState(0);
  const packValidationPackId = view === "data" && dataContextPack?.manifest_sha256 ? dataContextPack.id : "";
  const packValidationExtensions = dataContextExtensions.join(",");
  const packValidationKey = packValidationPackId ? JSON.stringify([packValidationPackId, dataContextPack?.manifest_sha256, packValidationExtensions, packValidationNonce]) : "";
  const packValidationCurrent = packValidationResult?.key === packValidationKey ? packValidationResult : null;
  const packValidationLayers = validationLayers(packValidationCurrent?.report, dataContextPack?.plausibility_status);
  useEffect(() => {
    if (!packValidationKey) return;
    const controller = new AbortController();
    fetch(`${API}/data-packs/${encodeURIComponent(packValidationPackId)}/validation?extensions=${encodeURIComponent(packValidationExtensions)}`, { signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json() as DataPackValidationReport & { error?: string };
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        setPackValidationResult({ key: packValidationKey, report: payload, error: "" });
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setPackValidationResult({ key: packValidationKey, report: null, error: reason instanceof Error ? reason.message : "Validation failed" }); });
    return () => controller.abort();
  }, [packValidationKey, packValidationPackId, packValidationExtensions]);

  async function previewDataRole(role: string) {
    const packId = dataContextPackId;
    const request = ++dataPreviewRequest.current;
    setDataPreviewLoading(role); setDataPreview(null);
    try {
      const preview = await getJson<DataPreview>(`${API}/data-packs/${encodeURIComponent(packId)}/preview?role=${encodeURIComponent(role)}`);
      if (request === dataPreviewRequest.current) setDataPreview({ contextId: dataContextId, packId, manifestSha256: dataManifestSha256, preview });
    } catch (reason) { if (request === dataPreviewRequest.current) setNotice(reason instanceof Error ? reason.message : "Preview failed"); }
    finally { if (request === dataPreviewRequest.current) setDataPreviewLoading(""); }
  }

  function chooseDomain(preset: DomainPreset) {
    setProjectForm((current) => {
      const optional = current.selected_extensions.filter((id) => !domainExtensionIds.includes(id));
      const modules = { ...current.modules, ...preset.recommended_modules };
      const zonal = modules.balancing === "value-zonal-redispatch-balancing";
      return alignZonalSolverContract({
        ...current,
        selected_extensions: [...new Set([...optional, ...preset.required_extensions])],
        market_configuration: {
          ...current.market_configuration,
          zonal_demand_mode: zonal
            ? (current.market_configuration.zonal_demand_mode || "scenario_scaled_zonal_shares")
            : "",
        },
      }, modules);
    });
    setDomainExtensionIds(preset.required_extensions);
  }

  function toggleExtension(extension: Extension, enabled: boolean) {
    setProjectForm((current) => {
      const selected_extensions = enabled
        ? [...new Set([...current.selected_extensions, extension.id])]
        : current.selected_extensions.filter((id) => id !== extension.id);
      const modules = { ...current.modules };
      if (enabled) {
        for (const moduleId of extension.composed_module_ids) {
          const selectedModule = workspace.modules.find((item) => item.id === moduleId);
          if (selectedModule) modules[selectedModule.slot] = selectedModule.id;
        }
      } else {
        for (const moduleId of extension.composed_module_ids) {
          const selectedModule = workspace.modules.find((item) => item.id === moduleId);
          if (selectedModule && modules[selectedModule.slot] === selectedModule.id) delete modules[selectedModule.slot];
        }
      }
      const zonal = modules.balancing === "value-zonal-redispatch-balancing";
      return alignZonalSolverContract({
        ...current,
        selected_extensions,
        market_configuration: {
          ...current.market_configuration,
          zonal_demand_mode: zonal
            ? (current.market_configuration.zonal_demand_mode || "scenario_scaled_zonal_shares")
            : "",
        },
      }, modules);
    });
  }

  function chooseMethodology(profileId: string) {
    if (!methodologyCatalogue) return;
    const next = applyProfileChoice({ parameters: parameterValues, modules: projectForm.modules }, profileId, methodologyCatalogue);
    setParameterValues(next.parameters);
    setProjectForm((current) => ({ ...current, modules: next.modules }));
  }
  /** Spec 7: a method or data change of the saved Study opens the confirmation dialog; nothing runs until it is confirmed. */
  async function promptMigration(project: Project, migration: RevisionMigration) {
    const opening = await openingMigration(API, project.id, migration);
    setMigrationPrompt({ projectId: project.id, studyName: project.name, migration: opening, nonce: Date.now() });
  }
  function selectStudyModule(slot: string, moduleId: string) {
    setProjectForm((current) => {
      const modules = { ...current.modules };
      if (moduleId) modules[slot] = moduleId; else delete modules[slot];
      if (slot === "psm") {
        const psm = workspace.modules.find((module) => module.id === moduleId);
        if (psm?.provides_capabilities?.includes("storage.central-cooptimization")) delete modules.storage_cost;
        else if (!modules.storage_cost) modules.storage_cost = "dynamic-annual-storage-cost";
      }
      const zonal = modules.balancing === "value-zonal-redispatch-balancing";
      return alignZonalSolverContract({
        ...current,
        market_configuration: {
          ...current.market_configuration,
          zonal_demand_mode: zonal
            ? (current.market_configuration.zonal_demand_mode || "scenario_scaled_zonal_shares")
            : "",
        },
      }, modules);
    });
  }

  function loadProjectRevision(project: Project) {
    if (project.extensions?.frozen_recovery) { selectRunProject(project.id); setView("run"); setNotice("冻结输入 Study 的科学配置与范围已锁定。请在 Runs 核对来源和 readiness；不能将其加载为可编辑科学草稿。"); return; }
    setSelectedPackId(project.data_pack_id);
    setProjectForm({
      name: project.name,
      purpose: project.purpose ?? "",
      start_year: project.start_year,
      end_year: project.end_year,
      modules: { ...project.modules },
      selected_extensions: [...(project.selected_extensions ?? [])],
      extension_parameters: { ...(project.extension_parameters ?? {}) },
      maturity_acknowledgements: { ...(project.maturity_acknowledgements ?? {}) },
      market_configuration: { ...(project.market_configuration ?? {}) },
      solver_contract: project.solver_contract ? {
        ...project.solver_contract,
        validated_ceilings: { ...project.solver_contract.validated_ceilings },
        absolute_ceilings: { ...project.solver_contract.absolute_ceilings },
      } : project.modules.balancing === "value-zonal-redispatch-balancing"
        ? copyDefaultZonalSolverContract()
        : undefined,
    });
    setParameterValues({ ...(project.parameters ?? {}) });
    setRuntimeValues({ "runtime.market_trace_level": "summary", ...(project.runtime_options ?? {}) });
    setEditingBaseRevision(project.revision_sha256);
    setEditingProjectId(project.id);
    setPreflight(null);
    setSelectedProjectId(project.id);
    setSelectedRunId("");
    setNotice(`Loaded revision ${project.revision_number ?? 0}. Saving a scientific change will create a new immutable revision.`);
  }

  function createFullReplayRevision() {
    const source = ["ready", "partial"].includes(selectedRunContext.kind) ? frozenRunProject : null;
    if (!source) {
      setNotice("This Run's frozen Study is loading, unavailable or inconsistent. Wait for its identity or inspect the source evidence before creating a Full market replay revision.");
      setView("run");
      return;
    }
    loadProjectRevision(source);
    setRuntimeValues((current) => ({ ...current, "runtime.market_trace_level": "full" }));
    setView("projects");
    setNotice("Full market replay is selected in a new editable Study revision. Review and save it when ready; no Run has started.");
  }

  async function createValue101BaselineStudy() {
    setLaunching("create-value-101-baseline");
    setNotice("");
    try {
      const response = await fetch(`${API}/tutorials/value-101/studies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const payload = await response.json() as { error?: string; project?: Project; run_started?: boolean };
      if (!response.ok || !payload.project) throw new Error(payload.error || "Unable to create the VALUE 101 baseline Study");
      setSelectedProjectId(payload.project.id);
      setSelectedRunId("");
      await refresh();
      setNotice(`Created Study revision ${payload.project.revision_number ?? 1}. Run started: ${payload.run_started === true ? "yes" : "no"}. Start the baseline separately when you are ready.`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "VALUE 101 Study creation failed");
    } finally {
      setLaunching("");
    }
  }

  async function moveStudyToTrash(project: Project, linkedRunCount: number) {
    const confirmation = buildStudyTrashConfirmation(project, linkedRunCount);
    const confirmed = confirmation.requiresExactName
      ? window.prompt(confirmation.message) === confirmation.expected
      : window.confirm(confirmation.message);
    if (!confirmed) { setNotice("Study move cancelled."); return; }
    const reason = window.prompt("Optional reason for moving this Study to trash:", "") ?? "";
    setLaunching("trash-study"); setNotice("");
    try {
      const response = await fetch(`${API}/projects/${project.id}/trash`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, confirm_name: confirmation.requiresExactName ? confirmation.expected : undefined, reason }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to move Study to trash");
      if (selectedProjectId === project.id) {
        setSelectedProjectId(""); setSelectedRunId(""); setSelectedRunDetail(null);
        setEditingBaseRevision(undefined); setEditingProjectId(undefined); setPreflight(null);
      }
      await refresh();
      if (selectedProjectId === project.id) setSelectedProjectId("");
      setView("projects");
      setNotice(`Moved ${project.name} and all immutable revisions to recoverable trash.`);
    } catch (reasonValue) {
      setNotice(reasonValue instanceof Error ? reasonValue.message : "Study move failed");
    } finally { setLaunching(""); }
  }

  async function restoreStudyEntry(entry: StudyTrashEntry) {
    const previousSelection = selectedProjectId;
    setLaunching("restore-study"); setNotice("");
    try {
      const response = await fetch(`${API}/study-trash/${entry.trash_id}/restore`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to restore Study");
      await refresh();
      setSelectedProjectId(previousSelection);
      setNotice(payload.needs_attention
        ? `Restored ${entry.study_name}. Its saved dependencies need attention before another Run.`
        : `Restored ${entry.study_name}. Historical Runs are linked again.`);
    } catch (reasonValue) {
      setNotice(reasonValue instanceof Error ? reasonValue.message : "Study restore failed");
    } finally { setLaunching(""); }
  }

  function finishDataInstall() {
    dataInstallRequest.current = null;
    setDataInstalling(false);
    setDataInstallPhase("idle");
  }

  function cancelDataInstall() {
    if (dataInstallPhase !== "uploading") return;
    dataInstallRequest.current?.abort();
  }

  function installDataPack() {
    if (!dataBundle) { setNotice("Choose a VALUE data-bundle ZIP first."); return; }
    if (!dataRights) { setNotice("Acknowledge the bundle licence and attribution before installation."); return; }
    setDataInstalling(true); setDataInstallProgress(0); setDataInstallPhase("uploading"); setNotice("");
    const request = new XMLHttpRequest();
    dataInstallRequest.current = request;
    request.open("POST", `${API}/data-packs/install`);
    request.setRequestHeader("Content-Type", "application/zip");
    request.setRequestHeader("X-Filename", encodeURIComponent(dataBundle.name));
    request.setRequestHeader("X-VALUE-Data-Rights", "acknowledged");
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percentage = Math.min(100, event.loaded / event.total * 100);
      setDataInstallProgress(percentage);
      if (percentage >= 100) setDataInstallPhase("verifying");
    };
    request.onload = () => {
      let payload: { error_code?: string; error?: string; installation?: { pack_id: string; name: string; validation: { passed: number } } } = {};
      try { payload = JSON.parse(request.responseText); } catch { /* The status remains the authoritative failure. */ }
      if (request.status < 200 || request.status >= 300 || !payload.installation) {
        setNotice(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || `Data-pack installation failed (HTTP ${request.status})`}`);
        finishDataInstall();
        return;
      }
      setSelectedPackId(payload.installation.pack_id);
      setNotice(`${payload.installation.name} passed all ${payload.installation.validation.passed} data-interface checks and was installed atomically.`);
      setDataBundle(null); setDataRights(false); setDataInstallProgress(100);
      void refresh().finally(finishDataInstall);
    };
    request.onerror = () => { setNotice("The local service could not receive the data bundle. No pack was promoted."); finishDataInstall(); };
    request.onabort = () => { setNotice("Data-pack upload cancelled before promotion. No installed pack was changed."); finishDataInstall(); };
    request.send(dataBundle);
  }

  function finishResearchSuiteInstall() {
    researchSuiteInstallRequest.current = null;
    setResearchSuiteInstalling(false);
    setResearchSuiteInstallPhase("idle");
  }

  function cancelResearchSuiteInstall() {
    if (researchSuiteInstallPhase !== "uploading") return;
    researchSuiteInstallRequest.current?.abort();
  }

  function installResearchSuite() {
    if (!researchSuiteBundle) { setNotice("Choose the VALUE-UK research-suite ZIP first."); return; }
    if (!researchSuiteRights) { setNotice("Review and acknowledge the suite rights and attribution before installation."); return; }
    setResearchSuiteInstalling(true); setResearchSuiteInstallProgress(0); setResearchSuiteInstallPhase("uploading"); setResearchSuiteSummary(null); setNotice("");
    const request = new XMLHttpRequest();
    researchSuiteInstallRequest.current = request;
    request.open("POST", researchSuiteApiUrl());
    request.setRequestHeader("Content-Type", "application/zip");
    request.setRequestHeader("X-Filename", encodeURIComponent(researchSuiteBundle.name));
    request.setRequestHeader("X-VALUE-Data-Rights", "acknowledged");
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percentage = Math.min(100, event.loaded / event.total * 100);
      setResearchSuiteInstallProgress(percentage);
      if (percentage >= 100) setResearchSuiteInstallPhase("verifying");
    };
    request.onload = async () => {
      let payload: { error_code?: string; error?: string; installation?: ResearchSuiteInstallation } = {};
      try { payload = JSON.parse(request.responseText); } catch { /* HTTP status remains authoritative. */ }
      if (request.status < 200 || request.status >= 300 || !payload.installation) {
        setNotice(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || `Research-suite installation failed (HTTP ${request.status})`}`);
        finishResearchSuiteInstall();
        return;
      }
      const summary = describeResearchSuiteInstallation(payload.installation) as ResearchSuiteSummary;
      setResearchSuiteSummary(summary);
      setResearchSuiteBundle(null); setResearchSuiteRights(false); setResearchSuiteInstallProgress(100);
      await refresh();
      setSelectedPackId(summary.components[0]?.id ?? selectedPackId);
      setNotice(`${summary.idempotent ? "Verified the existing" : "Installed"} ${summary.suiteId}. Two saved VALUE Studies are ready for review. No Run has started.`);
      finishResearchSuiteInstall();
    };
    request.onerror = () => { setNotice("The local service could not receive the research suite. No component was promoted."); finishResearchSuiteInstall(); };
    request.onabort = () => { setNotice("Research-suite upload cancelled before promotion. No installed component was changed."); finishResearchSuiteInstall(); };
    request.send(researchSuiteBundle);
  }

  function openResearchSuiteStudy(studyId: string) {
    setSelectedProjectId(studyId);
    setSelectedRunId("");
    setEditingBaseRevision(undefined); setEditingProjectId(undefined);
    setPreflight(null);
    setView("projects");
  }

  /** POST a module/extension lifecycle change; when Runs are pending (P0-2, 409
   * GF_MODULE_LIFECYCLE_RUNS_PENDING) ask, then resend with the confirmation. */
  async function lifecycleRequest(url: string, init: RequestInit, jsonBody?: Record<string, unknown>): Promise<{ response: Response; payload: Record<string, unknown> & { error?: string; error_code?: string } }> {
    const send = async (confirmed: boolean) => {
      const headers = new Headers(init.headers);
      let body = init.body;
      if (confirmed) {
        if (jsonBody !== undefined) body = JSON.stringify({ ...jsonBody, confirm_pending_runs: true });
        else headers.set("X-VALUE-Confirm-Pending-Runs", "acknowledged");
      }
      const response = await fetch(url, { ...init, headers, body });
      let payload: Record<string, unknown> & { error?: string; error_code?: string } = {};
      try { payload = await response.json(); } catch { /* the status is authoritative */ }
      return { response, payload };
    };
    const first = await send(false);
    if (!isPendingRunsRefusal(first.response.status, first.payload.error_code)) return first;
    if (!window.confirm(pendingRunsQuestion(first.payload.error))) return first;
    return send(true);
  }

  const [quarantineBusy, setQuarantineBusy] = useState("");
  // Spec 11.4 (M-D4): the error of the last Enable attempt per entry; a Rescan clears them.
  const [entryErrors, setEntryErrors] = useState<Record<string, EntryError>>({});
  async function disableQuarantined(row: QuarantineRow) {
    if (!row.disablePath) return;
    setQuarantineBusy(row.key); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}${row.disablePath.replace(/^\/api/, "")}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, {});
      if (!response.ok) throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || `Disabling ${row.id} failed`}`);
      setNotice(`${row.id} is disabled. Studies that used it need another module before they can run.`); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Disable failed"); }
    finally { setQuarantineBusy(""); }
  }
  async function rescanModules() {
    setQuarantineBusy("rescan"); setNotice("");
    try {
      const response = await fetch(`${API}/modules/rescan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await response.json() as { status?: string; error?: string; error_code?: string };
      if (!response.ok) throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || "Rescan failed"}`);
      setNotice(payload.status === "ok" ? "Rescan complete: no module is quarantined." : "Rescan complete: some modules are still quarantined; see the panel."); setEntryErrors({}); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Rescan failed"); }
    finally { setQuarantineBusy(""); }
  }

  function recordEntryError(key: string, error: EntryError | null) {
    setEntryErrors((current) => error ? { ...current, [key]: error } : Object.fromEntries(Object.entries(current).filter(([item]) => item !== key)));
  }
  /** Spec 11.4: Enable from the Disabled and quarantined area; a failure stays on its row with Rescan. */
  async function enableEntry(entry: DisabledEntry) {
    setQuarantineBusy(`enable:${entry.key}`); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}${lifecyclePath(entry, "enable")}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, {});
      if (!response.ok) throw new EntryLifecycleError(payload.error || `Enabling ${entry.id} failed`, payload.error_code);
      recordEntryError(entry.key, null);
      setNotice(`${entry.id} is enabled. Check readiness again before running a Study that uses it.`); setPreflight(null); await refresh();
    } catch (reason) { recordEntryError(entry.key, { code: reason instanceof EntryLifecycleError ? reason.code : undefined, message: reason instanceof Error ? reason.message : "Enable failed" }); }
    finally { setQuarantineBusy(""); }
  }
  /** Spec 11.4: Remove (confirmed in the panel) moves the entry's files out of the scanned folders. */
  async function removeEntry(entry: DisabledEntry) {
    setQuarantineBusy(`remove:${entry.key}`); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}${lifecyclePath(entry, "remove")}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, {}) as { response: Response; payload: { error?: string; error_code?: string; dependents?: Record<string, string[]>; removed?: { destination?: string } } };
      if (!response.ok) {
        const dependents = Object.values(payload.dependents ?? {}).flat();
        throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || `Removing ${entry.id} failed`}${dependents.length ? ` — ${dependents.join(", ")}` : ""}`);
      }
      recordEntryError(entry.key, null);
      setNotice(`${entry.id} was removed from VALUE. Its files are kept in modules/${payload.removed?.destination ?? "disabled-manifests/removed"}.`); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Remove failed"); }
    finally { setQuarantineBusy(""); }
  }

  async function installModule() {
    if (!moduleBundle) { setNotice("Choose a VALUE module ZIP first."); return; }
    if (!moduleTrust) { setNotice("Confirm that you trust the executable Python in this bundle."); return; }
    setModuleInstalling(true); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}/modules/install`, {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Filename": encodeURIComponent(moduleBundle.name),
          "X-VALUE-Executable-Trust": "acknowledged",
        },
        body: moduleBundle,
      }) as { response: Response; payload: { error?: string; error_code?: string; installation: { name: string; module_version: string } } };
      if (!response.ok) throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || "Module installation failed"}`);
      setNotice(`${payload.installation.name} ${payload.installation.module_version} passed structural conformance. Run a wiring test before research use.`);
      setModuleBundle(null); setModuleTrust(false); setBundleInputGeneration((generation) => generation + 1); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Module installation failed"); }
    finally { setModuleInstalling(false); }
  }

  async function changeModuleState(installation: ModuleInstallation, enabled: boolean) {
    setModuleLifecycle(installation.module_id); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}/modules/${encodeURIComponent(installation.module_id)}/${enabled ? "enable" : "disable"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      }, {}) as { response: Response; payload: { error?: string; error_code?: string; dependents?: { projects?: string[] } } };
      if (!response.ok) {
        const projects = payload.dependents?.projects?.join(", ");
        throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error}${projects ? `: ${projects}` : ""}`);
      }
      setNotice(`${installation.name} is now ${enabled ? "enabled and selectable" : "disabled"}.`); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Module state change failed"); }
    finally { setModuleLifecycle(""); }
  }

  async function installExtension() {
    if (!extensionBundle) { setNotice("Choose a value.extension-bundle/v1 ZIP first."); return; }
    if (!extensionTrust) { setNotice("Acknowledge the in-process trusted-code boundary before installation."); return; }
    setExtensionInstalling(true); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}/extensions/install`, {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Filename": encodeURIComponent(extensionBundle.name),
          "X-VALUE-Executable-Trust": "acknowledged",
        },
        body: extensionBundle,
      }) as { response: Response; payload: { error?: string; error_code?: string; installation: { extension_id: string; version: string } } };
      if (!response.ok) throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || "Extension installation failed"}`);
      setNotice(`${payload.installation.extension_id} ${payload.installation.version} passed structural extension validation. Its declared scientific maturity has not changed.`);
      setExtensionBundle(null); setExtensionTrust(false); setBundleInputGeneration((generation) => generation + 1); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Extension installation failed"); }
    finally { setExtensionInstalling(false); }
  }

  async function changeExtensionState(installation: ExtensionInstallation, enabled: boolean) {
    setExtensionLifecycle(installation.extension_id); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}/extensions/${encodeURIComponent(installation.extension_id)}/${enabled ? "enable" : "disable"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      }, {}) as { response: Response; payload: { error?: string; error_code?: string; dependents?: { projects?: string[]; runs_and_retained_history?: string[] } } };
      if (!response.ok) {
        const dependents = [...(payload.dependents?.projects ?? []), ...(payload.dependents?.runs_and_retained_history ?? [])];
        throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error}${dependents.length ? ` — ${dependents.join(", ")}` : ""}`);
      }
      setNotice(`${installation.extension_id} is now ${enabled ? "enabled" : "disabled"}.`); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Extension lifecycle change failed"); }
    finally { setExtensionLifecycle(""); }
  }

  async function copyDraftDataPack() {
    const source = dataContextPack;
    if (!source?.manifest_sha256 || copyingDraftPack || !draftPackCopyName.trim() || source.data_pack_type === "network_overlay") return;
    setCopyingDraftPack(true); setNotice("");
    try {
      const response = await fetch(`${API}/data-packs/${encodeURIComponent(source.id)}/clone`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schema_version: "value.data-pack-clone-request/v1", name: draftPackCopyName.trim(), source_manifest_sha256: source.manifest_sha256 }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.data_pack?.id || payload.data_pack.id === source.id) throw new Error(payload.error || "Unable to create an independent data pack.");
      await refresh();
      setSelectedPackId(payload.data_pack.id); setDataContextId("draft");
      setDraftResolution(null); setPreflight(null); setSavedDataResolution(null); setDataPreview(null);
      setDraftPackCopyName("");
      setNotice("Independent data pack selected for the current Study draft. Bind the extension roles below, then return to Studies → Review. Draft methods and extensions are preserved.");
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Data pack copy failed"); }
    finally { setCopyingDraftPack(false); }
  }

  async function upload(role: string, file?: File) {
    if (!file || !dataContextPack || uploading) return;
    if (isJourneyData && (journeyReadOnlyReason || !dataContextResolution || (journeyNetworkPackId && role.startsWith("value.zonal.")))) {
      setNotice(journeyReadOnlyReason || "请等待输入契约解析；网络覆盖角色不能在基础数据副本中替换。"); return;
    }
    if (workspace.projects.some((project) => project.data_pack_id === dataContextPack.id)) {
      setNotice("This pack belongs to a saved Study. Copy data pack for this draft before adding files."); return;
    }
    const target = dataContextPack;
    ++dataPreviewRequest.current; setDataPreview(null); setDataPreviewLoading("");
    setUploading(role); setNotice(""); setPreflight(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) };
      if (target.manifest_sha256) headers["X-Expected-Pack-Revision"] = target.manifest_sha256;
      const response = await fetch(`${API}/data-packs/${encodeURIComponent(target.id)}/files/${encodeURIComponent(role)}`, { method: "POST", headers, body: file });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.error || "Import failed");
      setNotice(`${file.name} 已通过该角色的格式校验并绑定到 ${target.name}；运行前仍需检查完整研究。`);
      setSavedDataResolution(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Import failed"); }
    finally { setUploading(""); }
  }
  async function previewParameters() {
    if (!selectedPack) return;
    try {
      const response = await fetch(`${API}/parameters/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data_pack_id: selectedPack.id, parameters: parameterValues, runtime_options: runtimeValues }) });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.error || "Preview failed");
      setResolvedSources(payload.sources ?? {}); setNotice("Effective parameters validated. Data Pack-derived and overridden sources are shown below.");
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Preview failed"); }
  }
  async function saveProject() {
    if (!selectedPack) return;
    if (draftResolving || !draftResolution?.valid) { setNotice("Resolve the listed Study issues before saving."); return; }
    const response = await fetch(`${API}/projects`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...projectForm, id: editingProjectId, extension_parameters: { ...draftResolution.effective_extension_parameters, ...projectForm.extension_parameters }, data_pack_id: selectedPack.id, parameters: parameterValues, runtime_options: runtimeValues, base_revision_sha256: editingBaseRevision }) });
    const payload = await response.json();
    if (!response.ok) { setNotice(payload.error || "Save failed"); return; }
    setResolvedSources(payload.validation?.resolved_parameters?.sources ?? {}); setSelectedProjectId(payload.project.id); setSelectedRunId(""); setEditingBaseRevision(payload.project.revision_sha256); setEditingProjectId(payload.project.id); setPreflight(null); setNotice(payload.validation?.errors?.[0] || "Project saved and contracts validated."); await refresh(); setView("run");
  }
  async function onRecoveredStudyCreated(projectId: string, mode: string) {
    const next = await refresh();
    if (!next?.projects.some(project => project.id === projectId)) throw new Error("Created Study is not yet available in the refreshed workspace.");
    if (!ALL_RUN_MODES.includes(mode as RunMode)) throw new Error("Recorded scope is unsupported by this frontend.");
    preflightRequest.current += 1; setPendingPreflightKey(null);
    setSelectedProjectId(projectId); setSelectedRunId(""); setSelectedRunDetail(null);
    setPreflight(null); setPreflightMode(mode as RunMode); setView("run");
    setNotice("已保存独立 Study，尚未启动。核对锁定范围，Check readiness 后再明确运行。");
  }
  async function checkPreflight(mode = effectivePreflightMode) {
    if (!mode || !canRunMode(mode)) { setNotice("此 Study 的锁定范围与数据包允许范围不相容，不能执行 readiness 或启动。"); return; }
    if (!selectedProject) { setNotice("Save and select a research project first."); return; }
    const requestId = ++preflightRequest.current;
    const target = selectedProject;
    setPendingPreflightKey(preflightKey(target, mode)); setPreflight(null); setNotice("");
    try {
      const response = await fetch(`${API}/projects/${encodeURIComponent(target.id)}/preflight`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
      const payload = await response.json();
      if (requestId !== preflightRequest.current) return;
      if (!response.ok) throw new Error(payload.error || "Preflight failed");
      // Spec 7: a method or data change is reported against the declared revision; it opens the confirmation dialog.
      const migration = migrationFromResponse(payload);
      if (migration && payload.project_id === target.id && migration.declared_sha256 === target.revision_sha256) {
        setNotice("The installed VALUE computes this Study differently from its saved revision. Review the changes before it runs.");
        void promptMigration(target, migration);
        return;
      }
      if (!preflightMatches(payload, target, mode)) throw new Error("Preflight identity changed. Refresh the saved Study and check it again.");
      // Rendering also matches the current selection, so an old Study response cannot appear on a new one.
      setPreflight(payload);
    } catch (reason) { if (requestId === preflightRequest.current) setNotice(reason instanceof Error ? reason.message : "Preflight failed"); }
    finally { if (requestId === preflightRequest.current) setPendingPreflightKey(null); }
  }
  async function startRun(mode: RunMode, projectOverride?: Project) {
    const targetProject = projectOverride ?? selectedProject;
    const targetPack = workspace.data_packs.find(pack => pack.id === targetProject?.data_pack_id);
    if (!runModesForStudy(targetProject, targetPack).includes(mode)) { setNotice("此运行范围不属于 Study 锁定范围与数据包允许范围的交集。"); return; }
    if (!targetProject) { setNotice("Save and select a research project first."); setView("projects"); return; }
    setSelectedProjectId(targetProject.id);
    setLaunching(mode); setNotice(""); setStartedRun(null);
    const launchView = viewRef.current;
    try {
      const response = await fetch(`${API}/projects/${targetProject.id}/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
      const payload = await response.json(); if (!response.ok) { if (preflightMatches(payload.preflight, targetProject, mode)) { setPreflight(payload.preflight); } const migration = migrationFromResponse(payload); if (migration && migration.declared_sha256 === targetProject.revision_sha256) void promptMigration(targetProject, migration); throw new Error(payload.error || "Unable to start the model"); }
      const noticeView = viewRef.current === launchView ? "run" : viewRef.current;
      if (viewRef.current === launchView) { setSelectedRunId(payload.run.id); setView("run"); }
      setStartedRun({ runId: payload.run.id, mode, studyId: targetProject.id, view: noticeView, text: mode === "smoke" ? "The two-period wiring verification has started." : mode === "two_year_smoke" ? "The two-year smoke verification has started." : mode === "value_101_day" ? "The one-day VALUE 101 PSM lesson has started." : mode === "two_year" ? "The complete two-year model has started." : "The complete annual model run has started." });
      await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Launch failed"); } finally { setLaunching(""); }
  }
  async function resumeRun(run: ModelRun) {
    setLaunching("resume"); setNotice("");
    try {
      const response = await fetch(`${API}/runs/${run.id}/resume`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.error || "Unable to resume the run");
      setNotice("The failed run is resuming from its last identity-verified annual checkpoint."); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Resume failed"); }
    finally { setLaunching(""); }
  }
  async function markRunLost(run: ModelRun) {
    // Spec 5 / P0-3 S4: a second, explicit confirmation in which the user types the exact run ID (as Delete does); only that ID is sent to the API's confirmation gate.
    const confirmation = window.prompt(`Mark Run ${run.id} as lost?\n\nVALUE cannot reach its worker. The Run will be recorded as failed and can then be resumed from its last annual checkpoint. A worker that is still running somewhere would be ignored.\n\nType the exact run ID to confirm:\n${run.id}`);
    if (confirmation !== run.id) { setNotice("The Run was not marked lost because the exact ID was not entered."); return; }
    setLaunching("mark-lost"); setNotice("");
    try {
      const response = await fetch(`${API}/runs/${encodeURIComponent(run.id)}/mark-lost`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm_run_id: confirmation }) });
      const payload = await response.json() as { error?: string; error_code?: string };
      if (!response.ok) throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || "The Run could not be marked lost"}`);
      setNotice("The Run was marked lost and recorded as failed. Resume it from its last annual checkpoint when ready."); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Mark as lost failed"); }
    finally { setLaunching(""); }
  }
  async function rerunAsCopperplate(run: ModelRun) {
    setLaunching("rerun-copperplate"); setNotice("");
    try {
      const response = await fetch(`${API}/runs/${run.id}/rerun-copperplate`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to create the copperplate rerun");
      setSelectedRunId(payload.run.id);
      setNotice(`Created new copperplate run ${payload.run.id}. The failed zonal run remains immutable.`);
      await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Copperplate rerun failed"); }
    finally { setLaunching(""); }
  }
  async function cloneStoragePolicy(moduleId: string, projectOverride?: Project) {
    const targetProject = projectOverride ?? selectedProject;
    if (!targetProject) return;
    setLaunching(`clone-${moduleId}`); setNotice("");
    try {
      const response = await fetch(`${API}/projects/${targetProject.id}/clone-storage-policy`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ storage_cost_module_id: moduleId }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to clone the storage-policy study");
      await refresh();
      loadProjectRevision(payload.project as Project);
      setView("projects");
      setNotice(`Created a controlled ${moduleId} Study. Data, years and non-storage settings were preserved.`);
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Storage-policy clone failed"); }
    finally { setLaunching(""); }
  }
  async function lifecycleAction(run: ModelRun, action: "cancel" | "archive" | "restore" | "export" | "delete") {
    setLaunching(action); setNotice("");
    try {
      let body: Record<string, string> = action === "export" ? { profile: "complete_audit" } : {};
      if (action === "delete") {
        const confirmation = window.prompt(`Move this run to recoverable trash? Type the exact run ID:\n${run.id}`);
        if (confirmation !== run.id) { setNotice("Run deletion was cancelled because the exact ID was not entered."); return; }
        body = { confirm_run_id: run.id };
      }
      const response = await fetch(`${API}/runs/${run.id}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.error || `${action} failed`);
      setNotice(action === "cancel" ? "Cancellation requested. The run will stop at the next guaranteed safe boundary." : action === "export" ? "The audit bundle was verified and is ready in the artifact list." : action === "delete" ? "The run was moved to recoverable local trash." : `Run ${action} completed.`); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : `${action} failed`); }
    finally { setLaunching(""); }
  }

  if (launcherRequired) return <OpenFromLauncher />;
  return <main className="workbench"><aside className="rail"><div className="logo"><span>VA</span><div><b>VALUE</b><small>Power-system evolution</small></div></div>
    <nav aria-label="Workspace">{[
      { label: "Start", ids: ["overview", "journey", "learn"] },
      { label: "Research", ids: ["projects", "data", "models", "run"] },
      { label: "Results", ids: ["marketReplay", "curtailment", "networkRedispatch", "systems", "audit"] },
      { label: "Guides", ids: ["extend"] },
    ].map((group) => <div className="workspace-nav-group" key={group.label}><p>{group.label}</p>{group.ids.map((id) => views.find((item) => item.id === id)!).map((item) => <button type="button" aria-label={`${item.label}: ${item.note}`} aria-current={view === item.id ? "page" : undefined} key={item.id} className={view === item.id ? "active" : ""} onClick={() => openView(item.id)}><i>{item.index}</i><span><b>{item.label}</b><small>{item.note}</small></span></button>)}</div>)}</nav>
    <div className="rail-foot"><div className={`service ${connectionState === "online" && workspace.runtime.compatible ? "online" : connectionState === "degraded" ? "degraded" : connectionState === "offline" ? "offline" : ""}`} role="status"><i /><span><b>{connectionState === "loading" ? "Connecting to model service…" : connectionState === "online" ? `Python ${workspace.runtime.python}` : connectionState === "degraded" ? "● Backend degraded" : "● Backend offline"}</b><small>{connectionState === "loading" ? "Checking the local API" : connectionState === "online" ? (workspace.runtime.compatible ? `${workspace.runtime.selected_capability ?? "value-native"} ready` : "VALUE native runtime unavailable") : connectionState === "degraded" ? (refreshFailures ? `The last ${refreshFailures === 1 ? "request" : `${refreshFailures} requests`} failed; retrying in ${Math.round(pollDelay(refreshFailures) / 1000)} s` : `Running with reduced capability: ${(health?.degraded_reasons ?? []).map((reason) => reason.code).join(", ") || "see Modules"}`) : `No answer after ${OFFLINE_AFTER_FAILURES} attempts. Start VALUE from its launcher, then retry`}</small></span>{(connectionState === "offline" || (connectionState === "degraded" && refreshFailures > 0)) && <button onClick={() => void refresh()}>Retry</button>}</div><small>Contract {workspace.architecture_version.replace("value.contracts/", "")}</small></div></aside>
    <section className="surface"><header className="topbar"><div><small>VALUE / {views.find((item) => item.id === view)?.index}</small><h1>{views.find((item) => item.id === view)?.label}</h1></div><div className="top-meta">
      {!isRunView && view !== "journey" && !(view === "data" && isJourneyData) && <><label><span>Draft data pack</span><select aria-label="Selected data pack" value={selectedPack?.id ?? ""} onChange={(event) => setSelectedPackId(event.target.value)} disabled={!online}>{workspace.data_packs.map((pack) => <option value={pack.id} key={pack.id}>{modelDisplayName(pack.name)}</option>)}</select></label><span title="Required base roles of this data pack. A Study's extension roles are counted in the Data page's input contract.">{/* F2-N3 (round R1-5): this count is the pack's base roles only. */}<Badge tone={baseInputsPill(online, selectedPack).tone}>{baseInputsPill(online, selectedPack).text}</Badge></span></>}
      {activeRunCount > 0 && <button type="button" className="background-runs value-new-control" onClick={() => setView("run")}>● {activeRunCount} {activeRunCount === 1 ? "Run" : "Runs"} running in background</button>}
      <button type="button" className="secondary workspace-readme-trigger" onClick={() => setReadMeOpen(true)} aria-haspopup="dialog">Read me</button>
    </div></header>
    <ReadMePanel open={readMeOpen} onClose={() => setReadMeOpen(false)} />
    {view !== "overview" && <CommunityPathPicker activePath={activePath} onSelect={chooseCommunityPath} />}
    {isRunView ? <RunContextBar run={selectedRun} frozen={{ runId: frozenRunSelectionId, status: frozenRunSelectionId === selectedRun?.id ? frozenRunProject ? "ready" : "unavailable" : "loading", project: frozenRunProject, snapshot: frozenInputSnapshot }} actions={{ onOpenInspect: (tab) => { setInspectTarget(tab ? { tab, nonce: Date.now() } : null); setView("audit"); }, onShowStressEvents: () => { setReplayTarget(null); setStressEventsFocus(Date.now()); setView("marketReplay"); } }} /> : view === "projects" && !editingProjectId ? <div className="workspace-study-context"><span>Independent Study draft</span><b>{projectForm.name}</b><small>Review and save to create a new Study.</small></div> : selectedProject && <div className="workspace-study-context"><span>Selected saved Study</span><b>{selectedProject.name}</b><span>revision {selectedProject.revision_number ?? "not recorded"}</span><small>Editing is saved as a new revision.</small></div>}
    {online && selectedRunId && isRunView && !selectedRun && <div className="notice" role="status">The requested Run is unavailable or belongs to another Study. Choose a Study and Run from Runs; no substitute result has been opened.</div>}
    {notice && <div className="notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")}>Close</button></div>}
    {!notice && startedRun && startedRunNoticeVisible(startedRun, { view, studyId: selectedProjectId }) && <div className="notice" role="status"><span>{startedRunNoticeText(startedRun, workspace.runs.find((run) => run.id === startedRun.runId))}</span><button onClick={() => setStartedRun(null)}>Close</button></div>}
    {migrationPrompt && <StudyMigrationDialog key={migrationPrompt.nonce} projectId={migrationPrompt.projectId} studyName={migrationPrompt.studyName} migration={migrationPrompt.migration} version={health?.version} apiBase={API}
      onCancel={() => { setMigrationPrompt(null); setNotice("The Study was not changed. It cannot run until the listed changes are confirmed."); }}
      onSaved={(revisionNumber) => { setMigrationPrompt(null); setPreflight(null); setNotice(`Saved as a new revision${revisionNumber ? ` (revision ${revisionNumber})` : ""}. Check readiness again, then start the Run.`); void refresh(); }} />}

    <div hidden={view !== "journey"} className="page">
      <ResearchJourney intent={activePath === "data" ? "data" : "reproduce"} studies={workspace.projects} packs={workspace.data_packs}
        initialStudyId={selectedProjectId} online={online}
        targetPackId={journeyTargetPackId} onTargetPackChange={setJourneyTargetPackId}
        onPackCreated={async () => { if (!await refresh()) throw new Error("工作区列表刷新失败，请恢复服务连接后重新加载。"); }}
        onCreated={async (studyId) => {
          await refresh(); setSelectedProjectId(studyId); setSelectedRunId(""); setPreflight(null); setView("run");
          setNotice("新的独立 Study 已保存。请选择运行范围并检查条件；尚未启动 Run。");
        }}
        onOpenData={(context) => {
          setJourneyData(context); setJourneyTargetPackId(context.targetPackId);
          setSelectedProjectId(context.sourceStudyId); setSelectedRunId(""); setDataContextId("journey");
          setSavedDataResolution(null); setDataPreview(null); setView("data");
        }}
        onOpenLearn={() => setView("learn")}
        onReviewSource={(studyId) => {
          const source = workspace.projects.find((project) => project.id === studyId);
          if (source) { loadProjectRevision(source); setView("projects"); }
        }}
        onOpenRuns={(studyId) => { selectRunProject(studyId); setView("run"); }} />
    </div>
    {view === "learn" && <Value101Learn
      descriptor={value101Tutorial}
      modules={workspace.modules}
      loading={value101Loading}
      error={value101Error}
      onRetry={() => void refreshValue101Tutorial()}
      onOpenView={setView}
      baselineSaved={Boolean(value101Project)}
      baselineInTrash={Boolean(value101Trash)}
      dayRunStatus={value101DayRun?.status}
      annualRunStatus={value101AnnualRun?.status}
      launching={Boolean(launching)}
      onCreateBaselineStudy={() => void createValue101BaselineStudy()}
      onRestoreBaselineStudy={() => { if (value101Trash) void restoreStudyEntry(value101Trash); }}
      onRunOneDay={() => { if (value101Project) void startRun("value_101_day", value101Project); }}
      onRunFullTwoYear={() => { if (value101Project) void startRun("two_year", value101Project); }}
      onOpenDayRun={() => { if (value101Project && value101DayRun) { setSelectedProjectId(value101Project.id); setSelectedRunId(value101DayRun.id); setView("run"); } }}
      onOpenAnnualRun={() => { if (value101Project && value101AnnualRun) { selectRunProject(value101Project.id); setSelectedRunId(value101AnnualRun.id); setView("run"); } }}
      networkStudies={workspace.projects.filter((project) => project.id === "value-101-network-copperplate" || project.id === "value-101-network-constrained")}
      networkRuns={workspace.runs.filter((run) => run.project_id === "value-101-network-copperplate" || run.project_id === "value-101-network-constrained")}
      preparations={value101Preparations}
      onNetworkStudiesCreated={(studies) => { setSelectedProjectId(studies[0]?.id ?? ""); setSelectedRunId(""); setNotice("Created the matched copperplate and fixed-network Studies. No Run has started."); void refresh(); }}
      onRunNetworkStudy={(study) => {
        const saved = workspace.projects.find((project) => project.id === study.id);
        if (saved) void startRun("two_year", saved);
        else { setNotice("The saved Study is still loading. Refresh the workspace, then retry."); void refresh(); }
      }}
      onOpenNetworkRun={(runId) => { const run = workspace.runs.find((item) => item.id === runId); if (run) selectRunProject(run.project_id); setSelectedRunId(runId); setView(run?.project_id === "value-101-network-constrained" && ["completed", "archived"].includes(run.status) ? "networkRedispatch" : "run"); }}
    />}

    {view === "overview" && <div className="page overview">
      <CommunityHome activePath={activePath} onSelect={chooseCommunityPath} />
      <section className="workspace-quick-start" aria-label="Quick start">
        <div className="hero-actions first-use-actions"><button className="primary" onClick={() => { setActivePath("reproduce"); setView("learn"); }}>Start VALUE 101</button><button className="secondary" onClick={() => { setSelectedProjectId(""); setSelectedRunId(""); setEditingBaseRevision(undefined); setEditingProjectId(undefined); setView("projects"); }}>Build a Study</button><button className="secondary" onClick={() => setView(workspace.projects.length ? "projects" : "learn")}>Open a saved Study</button></div>
        <small className="hero-scope">VALUE 101 · Synthetic teaching diagnostic, followed by the ordinary research workbench</small>
      </section>
      {workspace.projects.length > 0 && <section className="workspace-recent" aria-label="Recent studies"><h2>Continue a Study</h2><div>{[...workspace.projects].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 4).map((project) => <button className="secondary" type="button" key={project.id} onClick={() => { selectRunProject(project.id); setView("run"); }}><b>{project.name}</b><small>revision {project.revision_number ?? "not recorded"} · {workspace.runs.filter((run) => run.project_id === project.id).length} Runs</small></button>)}</div></section>}
      <section className="workspace-status">
        <article><span>Data</span><b>{selectedPack ? modelDisplayName(selectedPack.name) : "No data pack"}</b><small>{selectedPack?.complete ? "All required interfaces validated" : "Input work remains"}</small></article>
        <article><span>Model</span><b>{readyModules} executable modules</b><small>Selected per study, resolved at run time</small></article>
        <article><span>Runtime</span><b>{online && workspace.runtime.compatible ? "VALUE native" : "Not ready"}</b><small>{online && workspace.runtime.compatible ? `Python ${workspace.runtime.python} · reference ${workspace.runtime.capabilities?.["doctoral-reproduction"]?.available ? "available" : "not installed"}` : "Start the local model service"}</small></article>
      </section>
      <details className="workspace-about"><summary>About VALUE and model scope</summary><p><b>{VALUE_NAME}</b></p><p>Allocate variable electricity. Use renewable excess. Follow the system forward. VALUE links power-system operation (PSM) with capacity expansion and investment evolution (CEM).</p>
      <section className="annual-cycle"><header><span className="kicker">One model year</span><h3>Operation informs investment. Investment changes the next operation.</h3></header><div className="annual-flow lifecycle-flow">{["Advance planning", "Clear the PSM", "Apply expansion caps", "Agents invest", "Admit projects", "Carry state forward"].map((label, index) => <div className={index === 1 ? "model-node psm" : "model-node cem"} key={label}><span>{String(index + 1).padStart(2, "0")}</span><b>{label}</b><small>{index === 0 ? "Commission projects that are due" : index === 1 ? "Run the selected clearing module" : index === 4 ? "Record success, delay or failure" : "Versioned module call"}</small></div>)}</div></section>
      <div className="overview-grid"><section className="panel scope-panel"><div className="panel-head"><div><span>Model scope</span><h3>What this release represents</h3></div></div><ul className="scope-list"><li><i className="yes" /><span><b>Accepted single-node baseline retained</b><small>Existing VALUE studies remain reproducible and can select the bid-at-cost or perfect-foresight single-node PSM.</small></span></li><li><i className="yes" /><span><b>Fixed zonal transport and redispatch</b><small>The optional lossless corridor method records congestion, redispatch, curtailment and load shedding after the national ahead market.</small></span></li><li><i className="limit" /><span><b>Transmission expansion is an interface</b><small>No selectable transmission-expansion implementation is included in the ordinary product.</small></span></li><li><i className="yes" /><span><b>Linked PSM-CEM evolution</b><small>Selected operation, investment and planning modules pass through the same versioned annual lifecycle and audit contracts.</small></span></li></ul></section><section className="panel pack-panel"><div className="panel-head"><div><span>Selected inputs</span><h3>{selectedPack ? modelDisplayName(selectedPack.name) : "No pack selected"}</h3></div><Badge tone={selectedPack?.complete ? "good" : "warn"}>{selectedPack?.complete ? "Ready" : "Incomplete"}</Badge></div><div className="pack-score"><strong>{selectedPack?.valid_required_count ?? 0}</strong><span> / {selectedPack?.required_count ?? 0}</span></div><p>Each file is assigned a semantic role and checked before a run begins. Source hashes are retained with the study record.</p><button className="secondary" onClick={() => setView("data")}>Review data pack</button></section></div>
      </details>
    </div>}

    {view === "data" && <div className="page">
      <div className="page-title"><div><span>Study-aware data</span><h2>{dataContextPack ? modelDisplayName(dataContextPack.name) : "Choose a data pack"}</h2><p>The active roles come from the selected Study graph. Uploading a file changes the mutable pack binding; saved run snapshots remain immutable.</p></div><div className="pack-id"><span>Pack ID</span><code>{dataContextPack?.id}</code><small>{dataContextPack?.country} · {dataContextPack?.timezone} · {formatBytes(Object.values(dataContextPack?.bindings ?? {}).reduce((sum, item) => sum + item.bytes, 0))}</small></div></div>
      {activePath === "data" && <section className="panel journey-return"><div><b>为新研究准备独立数据包</b><p>安装并校验新数据包后返回引导。此路径中，已被保存 Study 引用的数据包保持只读。</p></div><button className="secondary" onClick={() => setView("journey")}>继续换数据流程</button></section>}
      {isJourneyData && <JourneyDataEditor
        sourceName={journeySource?.name ?? "基线不可用"} sourcePackName={journeySourcePack?.name ?? ""}
        targetPack={dataContextPack} sourceBindings={journeySourcePack?.bindings ?? {}}
        slots={activeDataSlots.filter((slot) => !journeyNetworkPackId || !slot.role.startsWith("value.zonal."))}
        networkPackId={journeyNetworkPackId} modelStartYear={journeySource?.start_year}
        readOnlyReason={journeyReadOnlyReason || (!dataContextResolution ? "正在解析基线方法所需的数据角色…" : "")}
        busy={Boolean(uploading)} onUpload={(role, file) => void upload(role, file)}
        onMapped={async () => { setPreflight(null); setSavedDataResolution(null); await refresh(); }}
        onPreview={(role) => void previewDataRole(role)} onReturn={() => setView("journey")} />}
      <DataWorkbench onWorkspaceChanged={async () => { setPreflight(null); setSavedDataResolution(null); await refresh(); }} />
      <section className="panel data-context">
        <div><span>Input contract for</span><select aria-label="Data input context" value={dataContextId} onChange={(event) => { setDataContextId(event.target.value); setSavedDataResolution(null); setDataPreview(null); }}>
          {isJourneyData && <option value="journey">引导中的独立数据包 · {dataContextPack?.name ?? "尚未选择"}</option>}
          <option value="draft">Current unsaved Study draft</option>
          {dataContextId !== "draft" && !isJourneyData && !dataContextProject && <option value={dataContextId}>Study unavailable · {dataContextId}</option>}
          {workspace.projects.map((project) => <option value={project.id} key={project.id}>{project.name} · revision {project.revision_number ?? 0}</option>)}
        </select></div>
        <div><strong>{dataContextResolution ? `${dataContextResolution.data_readiness.available}/${dataContextResolution.data_readiness.required}` : "Not evaluated"}</strong><span>{inputsPresentSuffix(worstStatus(packValidationLayers))}</span></div>
        {dataContextPackId && <a className="secondary" href={`${API}/data-packs/${encodeURIComponent(dataContextPackId)}/missing-checklist?extensions=${encodeURIComponent(dataContextExtensions.join(","))}&format=json`}>Download missing-input checklist</a>}
      </section>
      {dataContextPack && <DataPackValidationPanel key={dataContextPack.id} packId={dataContextPack.id} report={packValidationCurrent?.report} cached={dataContextPack.plausibility_status} loading={Boolean(packValidationKey) && !packValidationCurrent} error={packValidationCurrent?.error} onRetry={() => setPackValidationNonce((value) => value + 1)} />}
      {dataContextId === "draft" && <section className="panel data-context">
        <div><strong>Data pack for this draft</strong><select aria-label="Draft data pack" value={selectedPackId} disabled={copyingDraftPack} onChange={(event) => { setSelectedPackId(event.target.value); setDraftResolution(null); setPreflight(null); setDataPreview(null); }}>
          {workspace.data_packs.filter((pack) => pack.data_pack_type !== "network_overlay").map((pack) => <option key={pack.id} value={pack.id}>{pack.name} · {pack.id}</option>)}
        </select><small>Copy before adding files. The current draft retains its selected methods and extensions.</small></div>
        <label>Independent data pack name<input value={draftPackCopyName} disabled={copyingDraftPack} onChange={(event) => setDraftPackCopyName(event.target.value)} placeholder="My extension inputs" /></label>
        <button type="button" className="secondary" disabled={!online || copyingDraftPack || !dataContextPack?.manifest_sha256 || !draftPackCopyName.trim()} onClick={() => void copyDraftDataPack()}>{copyingDraftPack ? "Copying…" : "Copy data pack for this draft"}</button>
        <button type="button" className="secondary" onClick={() => { setComposerInitialStep(5); setView("projects"); }}>Return to Study Review</button>
        {draftResolving && <p role="status">Rechecking the draft against its latest data pack…</p>}
      </section>}
      {dataContextId !== "draft" && !isJourneyData && !dataContextProject && <p className="info-box" role="status">The linked Study is unavailable. Choose another input context to inspect or change data.</p>}
      <section className="panel module-installer data-bundle-installer">
        <div className="module-installer-copy"><span>Install complete inputs</span><h3>Install a VALUE data pack</h3><p>A modeller or data steward can provide one non-executable <code>value.data-bundle/v1</code> ZIP. VALUE streams it to local staging, verifies every SHA-256 and all required interfaces, then promotes it atomically.</p><small>The <code>value.*</code> prefix is a retained compatibility identifier. The ZIP contains data and rights records only.</small></div>
        <div className="module-installer-form">
          <label className="module-file"><span>Data bundle · .zip · up to 2 GiB</span><input type="file" accept=".zip,application/zip" disabled={dataInstalling} onChange={(event) => setDataBundle(event.target.files?.[0] ?? null)} /><b>{dataBundle?.name ?? "Choose a VALUE data bundle"}</b>{dataBundle && <small>{formatBytes(dataBundle.size)} selected · installation also needs the expanded size plus 1 GiB free</small>}</label>
          <label className="trust-check"><input type="checkbox" checked={dataRights} onChange={(event) => setDataRights(event.target.checked)} /><span>I have reviewed this bundle&apos;s licence and attribution records and agree to install its data locally.</span></label>
          {dataInstalling && <div className="bundle-progress" role="progressbar" aria-label="Data-pack upload" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(dataInstallProgress)}><span><b>{dataInstallPhase === "uploading" ? "Uploading to local staging" : "Verifying hashes, rights and 25 interfaces"}</b><small>{dataInstallPhase === "uploading" ? `${Math.round(dataInstallProgress)}%` : "Upload complete"}</small></span><i><em style={{ width: `${dataInstallProgress}%` }} /></i></div>}
          <div className="bundle-actions"><button className="primary" disabled={!dataBundle || !dataRights || dataInstalling} onClick={installDataPack}>{dataInstalling ? dataInstallPhase === "uploading" ? "Uploading…" : "Verifying and installing…" : "Install and validate data pack"}</button>{dataInstalling && dataInstallPhase === "uploading" && <button className="secondary" onClick={cancelDataInstall}>Cancel upload</button>}</div>
          <details><summary>For data-pack builders</summary><code>py -3.10 scripts\build_data_bundle.py --pack-root my-pack --output my-pack.zip</code></details>
        </div>
      </section>
      <section className="panel module-installer data-bundle-installer research-suite-installer">
        <div className="module-installer-copy"><span>VALUE-UK research inputs</span><h3>Install the VALUE-UK research suite</h3><p>Install one data-only ZIP containing the 25-role UK base pack, the fixed-zonal network overlay and two declarative 2025–2034 Study templates. VALUE validates every component and either promotes all of them or none of them.</p><small>This package contains no executable code. Installation creates saved, unrun Studies; it does not start a model.</small></div>
        <div className="module-installer-form">
          <label className="module-file"><span>Research suite · .zip · up to 2 GiB</span><input type="file" accept=".zip,application/zip" disabled={researchSuiteInstalling} onChange={(event) => setResearchSuiteBundle(event.target.files?.[0] ?? null)} /><b>{researchSuiteBundle?.name ?? "Choose VALUE-UK-Research-Suite.bundle.zip"}</b>{researchSuiteBundle && <small>{formatBytes(researchSuiteBundle.size)} selected · installed only on this computer</small>}</label>
          <label className="trust-check"><input type="checkbox" checked={researchSuiteRights} onChange={(event) => setResearchSuiteRights(event.target.checked)} /><span>I have reviewed the suite&apos;s source, licence and attribution records and agree to install both data components locally.</span></label>
          {researchSuiteInstalling && <div className="bundle-progress" role="progressbar" aria-label="Research-suite upload" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(researchSuiteInstallProgress)}><span><b>{researchSuiteInstallPhase === "uploading" ? "Uploading to local staging" : "Verifying two packs and two Study revisions"}</b><small>{researchSuiteInstallPhase === "uploading" ? `${Math.round(researchSuiteInstallProgress)}%` : "Upload complete"}</small></span><i><em style={{ width: `${researchSuiteInstallProgress}%` }} /></i></div>}
          <div className="bundle-actions"><button className="primary" disabled={!researchSuiteBundle || !researchSuiteRights || researchSuiteInstalling} onClick={installResearchSuite}>{researchSuiteInstalling ? researchSuiteInstallPhase === "uploading" ? "Uploading…" : "Installing atomically…" : "Install data and create two Studies"}</button>{researchSuiteInstalling && researchSuiteInstallPhase === "uploading" && <button className="secondary" onClick={cancelResearchSuiteInstall}>Cancel upload</button>}</div>
        </div>
      </section>
      {researchSuiteSummary && <section className="panel research-suite-result"><div className="panel-head"><div><span>Installed locally</span><h3>{researchSuiteSummary.suiteId}</h3></div><Badge tone="good">Verified</Badge></div><p><b>No Run has started.</b> Review either saved Study, run Check readiness, then choose when to launch it.</p><div className="dataset-table">{researchSuiteSummary.components.map((component) => <div className="dataset-row" key={component.id}><span className="slot-state bound">✓</span><span className="slot-name"><b>{component.id}</b><small>Installed component</small></span><span className="slot-file"><small>Bundle SHA-256</small><code>{component.sha256}</code></span></div>)}</div><small>Suite SHA-256: <code>{researchSuiteSummary.suiteSha256}</code></small><div className="bundle-actions"><button className="secondary" onClick={() => openResearchSuiteStudy(researchSuiteSummary.studyIds[0])}>Open copperplate Study</button><button className="secondary" onClick={() => openResearchSuiteStudy(researchSuiteSummary.studyIds[1])}>Open zonal Study</button></div></section>}
      {dataContextPack?.installation && <div className="reference-strip"><div><span>Installed bundle</span><b>Verified local data</b><small>{formatBytes(dataContextPack.installation.bundle_bytes)} · SHA-256 {dataContextPack.installation.bundle_sha256.slice(0, 16)}… · installed {dataContextPack.installation.installed_at}</small></div><div><span>Execution boundary</span><b>No executable content</b><small>{dataContextPack.installation.installation_boundary.replaceAll("_", " ")}</small></div></div>}
      <div className="reference-strip"><div><span>Versioned accounting library</span><b>Carbon factors</b><small>Native annual runs pin one factor scenario and write a reconciled or explicitly not-evaluated carbon ledger.</small></div><div><span>Optional network inputs</span><b>Transmission factors</b><small>Used only when a selected network or expansion module declares the required physical quantities and methodology.</small></div></div>
      <div className="domain-boundaries"><div><b>Hydro boundary</b><span>Run-of-river and conventional reservoirs use Hydrology roles. Pumped hydro remains electrical storage and must not be uploaded as natural-flow hydro.</span></div><div><b>Network boundary</b><span>Interconnectors remain external boundary offers. Internal AC lines, DC links and transformers belong in the Network branch contract.</span></div></div>
      {!isJourneyData && <div className="data-groups">{dataGroups.map((group) => <section className="panel" key={group}><div className="panel-head"><div><span>{group} inputs</span><h3>{group === "PSM" ? "Base market and system data" : group === "CEM" ? "Base investment and planning data" : `${group} conditional contract`}</h3></div><Badge tone="blue">{activeDataSlots.filter((slot) => slot.group === group).length} interfaces</Badge></div><div className="dataset-table expanded-dataset-table">{activeDataSlots.filter((slot) => slot.group === group).map((slot) => { const binding = dataContextPack?.bindings[slot.role]; const validation = binding?.validation; const supported = slot.supported_formats?.length ? slot.supported_formats : slot.formats; return <div className="dataset-row" key={slot.role}><span className={`slot-state ${binding ? "bound" : ""}`}>{binding ? "✓" : "·"}</span><span className="slot-name"><b>{modelDisplayName(slot.label)}</b><code>{slot.role}</code><small>{slot.source === "extension" ? `${slot.owner_extension ?? "Extension"} · ${slot.capability ?? "declared capability"}` : "Base contract"}</small></span><span className="slot-format"><small>{slot.required ? "Required" : "Optional"} · runtime parser: {supported.join(" / ")}</small>{supported.join("/") !== slot.formats.join("/") && <em>Manifest accepts {slot.formats.join(" / ")}; formats without a shipped parser remain unavailable.</em>}<b>{slot.unit || "unit declared by source contract"}</b>{slot.time_semantics && <em>{slot.time_semantics}</em>}</span><span className="slot-file">{binding ? <><b>{binding.filename}</b><small>{formatBytes(binding.bytes)} · SHA {binding.sha256.slice(0, 12)}…</small><small>revision {(binding.binding_revision ?? binding.sha256).slice(0, 12)} · {validation?.status ?? "validated at preflight"}</small>{binding.licence && <small>{binding.licence}</small>}</> : <><b>No file connected</b><small>{slot.template_available ? "Choose a canonical file or start from the template." : "Connect a file in a runtime-supported format."}</small></>}</span><div className="dataset-actions">{slot.template_available && <a className="text-button" href={`${API}/data-contracts/${encodeURIComponent(slot.role)}/template`}>Template</a>}{binding && <button className="text-button" disabled={dataPreviewLoading === slot.role} onClick={() => void previewDataRole(slot.role)}>{dataPreviewLoading === slot.role ? "Reading…" : "Preview"}</button>}<label className={`upload ${uploading === slot.role ? "busy" : ""}`}><input type="file" accept={supported.map((format) => `.${format}`).join(",")} onChange={(event) => void upload(slot.role, event.target.files?.[0])} disabled={Boolean(uploading) || !dataContextPack || workspace.projects.some((project) => project.data_pack_id === dataContextPackId)} />{uploading === slot.role ? "Importing" : binding ? "Replace" : "Choose file"}</label></div></div>; })}</div></section>)}</div>}
      {dataPreview && <section className="panel data-preview"><div className="panel-head"><div><span>Bounded server preview</span><h3>{dataPreview.definition ?? dataPreview.role}</h3></div><button className="text-button" onClick={() => setDataPreview(null)}>Close</button></div><div className="preview-facts"><span><small>Status</small><b>{dataPreview.status.replaceAll("_", " ")}</b></span><span><small>Format</small><b>{dataPreview.format ?? "not bound"}</b></span><span><small>Sampled rows</small><b>{dataPreview.sampled_rows ?? "metadata only"}</b></span><span><small>Duplicate sampled identities</small><b>{dataPreview.duplicate_sample_identities ?? "not evaluated"}</b></span></div>{dataPreview.columns && <p><b>Columns:</b> {dataPreview.columns.join(", ")}</p>}{dataPreview.timestamp_sample && <p><b>Timestamp sample:</b> {dataPreview.timestamp_sample.first ?? "none"} → {dataPreview.timestamp_sample.last ?? "none"}</p>}<pre>{JSON.stringify({ array_counts: dataPreview.array_counts, numeric_ranges: dataPreview.numeric_ranges, sample: dataPreview.sample, source_sha256: dataPreview.source_sha256 }, null, 2)}</pre><small>This bounded preview is for diagnosis. Full validation and canonical adaptation run on the server during preflight and snapshotting.</small></section>}
    </div>}

    {view === "models" && <div className="page">
      <div className="page-title"><div><span>VALUE module registry</span><h2>The model is assembled here</h2><p>Each card resolves to one executable Python implementation. Install a reviewed local bundle to replace one part of the model without editing VALUE.</p></div><div className="modules-title-actions"><Badge tone="good">{readyModules} of {workspace.modules.length} ready</Badge><button type="button" className="secondary modules-rescan value-new-control" disabled={Boolean(quarantineBusy)} onClick={() => void rescanModules()}>{quarantineBusy === "rescan" ? "Rescanning…" : "Rescan modules"}</button></div></div>
      <ModuleQuarantinePanel report={workspace.module_quarantine} busy={quarantineBusy} onDisable={(row) => void disableQuarantined(row)} onRescan={() => void rescanModules()} />
      <div><ModuleAuthorWorkbench modules={workspace.modules} projects={workspace.projects}
        onInstallRequest={() => document.getElementById("module-installer")?.scrollIntoView({ block: "start", behavior: "smooth" })}
        onCreated={async ({ id }) => {
          const refreshed = await refresh();
          setSelectedProjectId(id); setSelectedRunId(""); setPreflight(null); setView("run");
          setNotice(refreshed ? "Method-comparison Study saved. Data and all other settings are unchanged; no Run has started." : "Method-comparison Study saved, but the workspace did not refresh. Continue in Runs once the connection is back; no Run has started.");
        }} /></div>
      <section className="panel module-installer" id="module-installer">
        <div className="module-installer-copy"><span>Local extension</span><h3>Install a model module</h3><p>A modeller prepares one signed-off ZIP containing a manifest, licence and self-contained Python source. VALUE verifies its inventory, public contract and callable shape before it enters the registry.</p><small>Structural conformance is not scientific validation. Installed Python runs inside the local VALUE process.</small></div>
        <div className="module-installer-form">
          <label className="module-file"><span>Module bundle · .zip · up to 25 MiB</span><input key={`module-bundle-${bundleInputGeneration}`} type="file" accept=".zip,application/zip" onChange={(event) => setModuleBundle(event.target.files?.[0] ?? null)} /><b>{moduleBundle?.name ?? "Choose a VALUE module bundle"}</b></label>
          <label className="trust-check"><input type="checkbox" checked={moduleTrust} onChange={(event) => setModuleTrust(event.target.checked)} /><span>I trust the source of this bundle and understand that it contains executable Python code.</span></label>
          <button className="primary" disabled={!moduleBundle || !moduleTrust || moduleInstalling} onClick={() => void installModule()}>{moduleInstalling ? "Validating and installing…" : "Install and validate module"}</button>
          <details><summary>For module developers</summary><code>py -3.10 scripts\build_module_bundle.py --manifest value-module.json --source-root src --license LICENSE --output my-module.zip</code></details>
        </div>
      </section>
      {workspace.module_installations.length > 0 && <section className="installed-modules">
        <header><div><span>Installed locally</span><h3>External module packages</h3></div><Badge>{workspace.module_installations.length}</Badge></header>
        <div>{workspace.module_installations.map((installation) => {
          const projectReferences = workspace.projects.filter((project) => Object.values(project.modules).includes(installation.module_id));
          const card = installedModuleCard(installation, workspace.module_quarantine, workspace.module_source_changes);
          return <article key={installation.module_id} data-state={card.state}><div><b>{installation.name}</b><small>{installation.module_id} · {installation.slot.replaceAll("_", " ")} · {installation.module_version}</small></div><span><small>Contract</small><code>{installation.contract_version}</code></span><span><small>Source SHA-256 at install</small><code>{installation.source_sha256?.slice(0, 16) ?? "not recorded"}…</code>{card.sourceChange && <em className="installed-module-note caution value-new-control">{card.sourceChange}</em>}</span><span><small>Conformance at install</small><b>{installation.conformance.status}</b></span><span><small>State</small><b className={`installed-module-state ${card.state} value-new-control`}>{card.stateText}</b></span>{card.offerToggle ? <button className="text-button" disabled={moduleLifecycle === installation.module_id || (installation.enabled && projectReferences.length > 0)} title={projectReferences.length ? `Used by ${projectReferences.map((project) => project.name).join(", ")}` : ""} onClick={() => void changeModuleState(installation, !installation.enabled)}>{moduleLifecycle === installation.module_id ? "Updating…" : "Disable"}</button> : <button type="button" className="text-button" onClick={() => document.getElementById("disabled-entries-title")?.scrollIntoView({ block: "start", behavior: "smooth" })}>Open Disabled and quarantined</button>}{moduleUsageNote(card.state, projectReferences.length) && <p>{moduleUsageNote(card.state, projectReferences.length)}</p>}</article>;
        })}</div>
      </section>}
      <ExtensionAuthorWorkbench extensions={workspace.extensions} modules={workspace.modules}
        onInstallRequest={() => document.getElementById("extension-installer")?.scrollIntoView({ block: "start", behavior: "smooth" })}
        onOpenStudies={() => {
          setEditingProjectId(undefined); setEditingBaseRevision(undefined); setDataContextId("draft");
          setProjectForm(current => ({ ...current, name: `${current.name || "New"} · extension study`, maturity_acknowledgements: {} }));
          setPreflight(null); setView("projects");
          setNotice("Independent Study draft opened. Choose the installed extension and an independent data pack, bind its inputs in Data, then review and save. No Run has started.");
        }} />
      <section className="panel extension-installer" id="extension-installer">
        <div className="module-installer-copy"><span>Capability package</span><h3>Install a model extension</h3><p>An extension adds data roles, parameters, lifecycle hooks or a new model domain through <code>value.extension-bundle/v1</code>. It does not silently replace a module.</p><small>Three levels are supported: data-only contracts, replacement modules installed separately, and new domains composed from both. The browser never runs pip or downloads dependencies.</small></div>
        <div className="module-installer-form"><label className="module-file"><span>Extension bundle · .zip · up to 25 MiB</span><input key={`extension-bundle-${bundleInputGeneration}`} type="file" accept=".zip,application/zip" onChange={(event) => setExtensionBundle(event.target.files?.[0] ?? null)} /><b>{extensionBundle?.name ?? "Choose an extension bundle"}</b></label><label className="trust-check"><input type="checkbox" checked={extensionTrust} onChange={(event) => setExtensionTrust(event.target.checked)} /><span>I trust the bundle source and understand that extension hooks and composed modules execute as trusted Python in the local process. No OS sandbox is claimed.</span></label><button className="primary" disabled={!extensionBundle || !extensionTrust || extensionInstalling} onClick={() => void installExtension()}>{extensionInstalling ? "Checking inventory and dependencies…" : "Install and validate extension"}</button></div>
      </section>
      <section className="extension-catalogue"><header><div><span>One workspace registry</span><h3>Installed and built-in extensions</h3></div><Badge>{workspace.extensions.length}</Badge></header><div>{workspace.extensions.map((extension) => { const installation = workspace.extension_installations.find((item) => item.extension_id === extension.id && item.version === extension.version); const projectReferences = workspace.projects.filter((project) => project.selected_extensions?.includes(extension.id)); return <article key={extension.id}><header><div><b>{extension.name}</b><small>{extension.id} · {extension.version} · {extension.namespace}</small></div><Badge tone={extension.maturity === "ready" ? "good" : "warn"}>{extension.maturity.replaceAll("_", " ")}</Badge></header><p><strong>Provides</strong> {extension.provided_capabilities.join(" · ") || "No capability declared"}</p><p><strong>Requires</strong> {extension.required_capabilities.join(" · ") || "No additional capability"}</p><div><span><small>Conditional data</small><b>{extension.data_roles.filter((role) => role.required).length} required · {extension.data_roles.filter((role) => !role.required).length} optional</b></span><span><small>Composed modules</small><b>{extension.composed_module_ids.join(", ") || "none"}</b></span><span><small>Licence / manifest</small><b>{extension.licence} · {extension.manifest_sha256.slice(0, 12)}…</b></span><span><small>Origin</small><b>{extension.origin.replaceAll("_", " ")} · {extension.enabled ? "enabled" : "disabled"}</b></span></div>{installation && extensionSourceChangeNote(extension.id, workspace.extension_source_changes) && <em className="installed-module-note caution value-new-control">{extensionSourceChangeNote(extension.id, workspace.extension_source_changes)}</em>}{installation && <footer><code>{installation.installation_boundary} · {installation.bundle_sha256.slice(0, 16)}…</code><button className="text-button" disabled={extensionLifecycle === extension.id || (installation.enabled && projectReferences.length > 0)} title={projectReferences.length ? `Used by ${projectReferences.map((project) => project.name).join(", ")}` : ""} onClick={() => void changeExtensionState(installation, !installation.enabled)}>{extensionLifecycle === extension.id ? "Updating…" : installation.enabled ? "Disable" : "Enable"}</button></footer>}{projectReferences.length > 0 && <em>Referenced by {projectReferences.length} saved {projectReferences.length === 1 ? "Study" : "Studies"}; disabling is blocked.</em>}</article>; })}</div></section>
      <div className="module-list">{workspace.modules.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0)).map((module, index) => <article className="module-card" key={module.id}><header><div className={`module-mark ${module.kind}`}>{String(index + 1).padStart(2, "0")}</div><div><span>{module.kind.toUpperCase()} · {module.slot.replaceAll("_", " ")} · {module.version}</span><h3>{modelDisplayName(module.name)}</h3></div><Badge tone={module.status === "ready" ? "good" : "warn"}>{module.origin === "local_bundle" ? `local · ${module.status}` : module.status}</Badge></header><p>{modelDisplayName(module.description)}</p><div className="module-id"><span>Implementation</span><code>{module.id}</code><small>Contract {module.contract_version ?? "not recorded"}</small></div>{module.id === "value-bid-at-cost-psm" && <div className="compatibility-note">Live module · bid-at-cost clearing through the v2 orchestrator</div>}<details className="io"><summary>Inputs and outputs</summary><div><span>Inputs</span>{module.inputs.map((input) => <code key={input}>{input}</code>)}</div><i>→</i><div><span>Outputs</span>{module.outputs.map((output) => <code key={output}>{output}</code>)}</div></details></article>)}</div>
      <DisabledEntriesPanel entries={disabledEntries({ modules: workspace.module_installations, extensions: workspace.extension_installations, quarantine: workspace.module_quarantine })} busy={quarantineBusy} errors={entryErrors} onEnable={(entry) => void enableEntry(entry)} onRescan={() => void rescanModules()} onRemove={(entry) => void removeEntry(entry)} />
    </div>}

    {view === "projects" && <div className="page project-page"><div className="page-title"><div><span>Study setup</span><h2>Define the scientific question, then resolve the model</h2><p>The composer connects one data pack, physical domain, optional extensions, model chain and assumptions. Saving creates an immutable revision of exactly the graph shown in Review.</p></div><Badge tone={draftResolution?.valid ? "good" : "warn"}>{draftResolving ? "Resolving" : draftResolution?.valid ? "Draft ready" : "Draft incomplete"}</Badge></div><StudyComposer initialStep={composerInitialStep} workspace={workspace} form={projectForm} selectedPackId={selectedPack?.id ?? selectedPackId} resolution={draftResolution} resolving={draftResolving} resolutionError={draftResolutionError} savedProjects={workspace.projects} studyTrash={workspace.study_trash} selectedProjectId={selectedProjectId} assumptions={<><AdvancedSettings definitions={definitions} values={{ ...parameterValues, ...runtimeValues }} resolvedSources={resolvedSources} onChange={(id, value, runtime) => runtime ? setRuntimeValues((current) => ({ ...current, [id]: value })) : setParameterValues((current) => ({ ...current, [id]: value }))} /><button className="text-button full" onClick={() => void previewParameters()}>Check effective base values</button></>} onForm={(update) => setProjectForm(update)} onPack={setSelectedPackId} onDomain={chooseDomain} onExtension={toggleExtension} onModule={selectStudyModule} onExtensionParameter={(name, value) => setProjectForm((current) => ({ ...current, extension_parameters: { ...current.extension_parameters, [name]: value } }))} onAcknowledgement={(key, value, checked) => setProjectForm((current) => { const maturity_acknowledgements = { ...current.maturity_acknowledgements }; if (checked) maturity_acknowledgements[key] = value; else delete maturity_acknowledgements[key]; return { ...current, maturity_acknowledgements }; })} onSave={() => void saveProject()} onLoad={loadProjectRevision} onOpenRun={(project) => { selectRunProject(project.id); setView("run"); }} onTrash={(project, linkedRunCount) => void moveStudyToTrash(project, linkedRunCount)} onRestore={(entry) => void restoreStudyEntry(entry)} onOpenTrashRuns={(entry) => { const run = workspace.runs.find((item) => item.project_id === entry.study_id); setSelectedProjectId(entry.study_id); setSelectedRunId(run?.id ?? ""); setSelectedRunDetail(null); setView("run"); if (!run) setNotice("No indexed Run is available for this trashed Study; restore it to inspect non-indexed legacy evidence."); }} onOpenData={() => { setDataContextId("draft"); setView("data"); }} traceLevel={(runtimeValues["runtime.market_trace_level"] as TraceProfile | undefined) ?? "summary"} onTraceLevel={(trace) => setRuntimeValues((current) => ({ ...current, "runtime.market_trace_level": trace }))} methodology={{ catalogue: methodologyCatalogue, profileId: selectedProfileId(parameterValues, methodologyCatalogue), error: methodologyError }} editingStudyName={editingProjectId ? workspace.projects.find((project) => project.id === editingProjectId)?.name ?? editingProjectId : undefined} onMethodology={chooseMethodology} /></div>}

    {view === "run" && <RunWorkspace workspace={workspace} selectedProjectId={selectedProjectId} selectedProject={selectedProject} selectedProjectPack={selectedProjectPack} selectedRun={selectedRun} projectRuns={projectRuns} preflight={preflight} effectivePreflightMode={effectivePreflightMode} checkingPreflight={checkingPreflight} zonalPreflight={zonalPreflight} teachingProject={teachingProject} launching={launching} selectedRunSourceMutable={selectedRunSourceMutable} canRunMode={canRunMode} frozen={{ contextKind: selectedRunContext.kind, runId: frozenRunSelectionId, readiness: frozenRunReadiness, project: frozenRunProject, snapshot: frozenInputSnapshot }} actions={{ selectRunProject, onSelectRun: setSelectedRunId, onMode: (mode) => { setPreflightMode(mode); setPreflight(null); }, onNavigate: openView, cloneStoragePolicy, checkPreflight, startRun, resumeRun, rerunAsCopperplate, lifecycleAction, onRecoveredStudyCreated, markLost: markRunLost, openInspect: (tab) => { setInspectTarget({ tab, nonce: Date.now() }); setView("audit"); } }} />}

    {view === "marketReplay" && <MarketReplayView key={`${selectedRun?.id ?? "no-run"}:${replayTarget?.nonce ?? 0}`} run={selectedRun} onCreateFullReplayRevision={createFullReplayRevision} initialWindow={replayTarget} focusStressEvents={stressEventsFocus > 0} onStressEventsFocused={() => setStressEventsFocus(0)} />}

    {view === "curtailment" && <><ResultQueryPanel key={`query-${selectedRun?.id ?? "no-run"}`} run={selectedRun} /><CurtailmentView key={`physical-${selectedRun?.id ?? "no-run"}`} run={selectedRun} /></>}

    {view === "networkRedispatch" && <NetworkRedispatchView key={selectedRun?.id ?? "no-run"} run={selectedRun} sourceStudyMutable={selectedRunSourceMutable} onReplay={(year, periodFrom) => { if (selectedRun) { setReplayTarget({ runId: selectedRun.id, year, periodFrom, nonce: Date.now() }); setView("marketReplay"); } }} onOpenInspect={() => openView("audit")} onOpenMarket={() => setView("marketReplay")} onCreateFullReplayRevision={createFullReplayRevision} onOpenRun={() => setView("run")} onRerun={() => selectedRun ? rerunAsCopperplate(selectedRun) : Promise.resolve()} />}

    {view === "systems" && <SystemResultsView run={selectedRun} onOpenMarket={() => setView("marketReplay")} onOpenNetwork={() => setView("networkRedispatch")} />}

    {view === "audit" && <AuditView run={selectedRun} onCreateFullReplayRevision={createFullReplayRevision} initialTab={inspectTarget} />}

    {view === "extend" && <div className="page"><div className="page-title"><div><span>Data adapters</span><h2>Bring another dataset into VALUE</h2><p>Map local tables to stable model roles once. The PSM and CEM can then read the new source without source-specific code entering the model modules.</p></div></div><div className="adapter-steps">{[["01", "Describe the pack", "Record its country, timezone, licence and source versions."], ["02", "Map each role", "Connect local tables and columns to the PSM and CEM input contracts."], ["03", "Align units and time", "Convert power, energy, currency and timestamps at the adapter boundary."], ["04", "Check the contract", "Confirm every selected module receives the expected fields and units."]].map(([number, title, copy]) => <article key={number}><i>{number}</i><h3>{title}</h3><p>{copy}</p></article>)}</div><section className="panel contract-example"><div><span>Minimal adapter output</span><h3>A manifest and a mapping</h3><p>VALUE recognises semantic roles. File formats, column names and API details remain inside the adapter.</p></div><pre>{`data_pack: my-country-2030\ncountry: XX\ntimezone: Region/City\nbindings:\n  demand.real:\n    source: demand.csv\n    column: observed_mwh\n    unit: MWh/period\n  projects.repd:\n    source: projects.parquet\n    mapping:\n      capacity_mw: size_mw\n      technology: tech_code`}</pre></section></div>}
    </section></main>;
}
