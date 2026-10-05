"use client";

import ModuleAuthorWorkbench from "./features/modules/ModuleAuthorWorkbench";
import ExtensionAuthorWorkbench from "./features/extensions/ExtensionAuthorWorkbench";
import StudyComposer from "./features/studies/StudyComposer";
import AdvancedSettings from "./features/studies/AdvancedSettings";
import { alignZonalSolverContract } from "./features/studies/solverContract";
import RunWorkspace from "./features/runs/RunWorkspace";
import AuditView from "./features/evidence/AuditView";
import { Badge, formatBytes, formatNumber, modelDisplayName } from "./features/shared/presentation";
import { API_BASE, LauncherAccessError, getJson } from "./features/shared/api";
import { formatEnergyGroup, formatQuantity } from "./features/shared/format.ts";
import OpenFromLauncher from "./features/shared/OpenFromLauncher";
import { PUBLIC_CAPABILITY_DOMAINS } from "./features/shared/domainConstants";
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
import { resolveRunContext } from "./features/workspace/runContext";
import { readWorkspaceLocation, writeWorkspaceLocation, selectWorkspaceRun, type WorkspaceLocation } from "./features/workspace/workspaceLocation";
import "./features/workspace/workspace-shell.css";
import Value101Learn from "./features/learn/Value101Learn";
import DataWorkbench from "./features/data-workbench/DataWorkbench";
import {
  describeResearchSuiteInstallation,
  researchSuiteApiUrl,
} from "./features/data/research-suite-api.mjs";
import NetworkRedispatchView from "./features/network/NetworkRedispatchView";
import ReplayExportPanel from "./features/market/ReplayExportPanel";
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
// holds.  API_ORIGIN stays an empty string until the apiOrigin prop chain is
// removed (P0-1 S9), so every `${apiOrigin}/api/...` is a relative path.
const API_ORIGIN = "";
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
type MarketCapability = {
  years: number[]; trace_level: string; period_summary: boolean; physical_dispatch: boolean;
  auction_replay: boolean; storage_state: boolean; storage_cost_module_id?: string; missing_reason?: string | null; source_artifact_sha256?: string | null;
  bid_replay_available?: boolean; bid_replay_missing_reason?: string | null; missing_detail?: string[];
  auction_stages: { stage: string; declared_periods: number; outcome_periods: number; order_detail: string }[];
  semantic_metadata?: Record<string, unknown>;
};
type DispatchFlow = { technology: string; flow_type: string; evidence_scope: string; energy_mwh: number; balance_component_mwh: number };
type DispatchBucket = {
  period_start: number; period_end: number; period_count: number; timestamp_start: string; timestamp_end: string;
  real_demand_mwh: number; accepted_supply_mwh: number; clearing_price_gbp_per_mwh: number;
  storage_charge_mwh: number; storage_discharge_mwh: number; curtailed_mwh: number; excess_mwh: number;
  vre_available_mwh: number; vre_accepted_mwh: number; neutral_unused_vre_mwh?: number;
  blackout_mwh: number; compatibility_adjustment_mwh: number; flows: DispatchFlow[];
};
type DispatchTimeline = { year: number; resolution: string; total: number; limit: number; offset: number; source_artifact_sha256?: string | null; items: DispatchBucket[] };
type AuctionOffer = {
  offer_id?: string; asset_id: string; asset_type?: string; resource_kind?: string; technology: string;
  offer_price_gbp_per_mwh: number; offered_mwh: number; accepted_mwh: number | null;
  asset_accepted_mwh: number | null; acceptance_granularity: string; execution_order: number;
  cumulative_offered_mwh: number;
};
type AuctionView = {
  year: number; period: number; stage: string; information_scope: string; requirement_mwh: number;
  offers: AuctionOffer[]; marginal_offer_price_gbp_per_mwh: number | null; marginal_offer_status: string;
  offer_acceptance_coverage: string; pricing_rule: string; input_sha256: string; source_artifact_sha256?: string | null;
};
type StoragePeriodRow = { asset_id: string; state_of_charge_mwh: number; charge_mwh: number; discharge_mwh: number; power_capacity_mw: number; energy_capacity_mwh: number };
type VreYear = {
  year: number; period_count: number; full_chronology: boolean; available_vre_mwh: number; accepted_vre_mwh: number;
  neutral_unused_vre_mwh: number; pre_balancing_excess_mwh: number | null; pre_balancing_excess_scope: string;
  balancing_curtailment_mwh: number | null; vre_utilisation_fraction: number | null; average_unused_vre_fraction: number | null;
  affected_periods: number; longest_event_hours: number; peak_event_mwh: number | null; peak_event_timestamp: string | null;
  storage_charge_mwh: number; export_mwh: number; flexible_demand_mwh: number; vre_identity_residual_mwh: number;
  coverage_status: string; marginal_curtailment_status: string; marginal_curtailment_reason: string;
};
type VreSummary = { years: VreYear[]; excess_relationship: string; excess_scope: string; source_artifact_sha256?: string | null };
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
  const technologies = Array.from(new Set(items.flatMap((item) => item.flows.filter((flow) => ["generation", "import", "storage_discharge"].includes(flow.flow_type)).map((flow) => flow.technology))));
  const totals = items.map((item) => item.flows.filter((flow) => ["generation", "import", "storage_discharge"].includes(flow.flow_type)).reduce((sum, flow) => sum + flow.energy_mwh, 0));
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
      {item.flows.filter((flow) => ["generation", "import", "storage_discharge"].includes(flow.flow_type)).map((flow) => { const start = cumulative; cumulative += flow.energy_mwh; return <rect key={`${flow.flow_type}-${flow.technology}`} x={x(index)} y={y(cumulative)} width={barWidth} height={Math.max(y(start) - y(cumulative), 0)} fill={technologyColours[flow.technology] ?? technologyColours.unmapped} />; })}
      {periodSelected && <line x1={x(index)} x2={x(index)} y1={top} y2={top + plotHeight} className="selection-line" />}
    </g>; })}
    <polyline points={demandPoints} className="demand-line" />
    <text x={left} y={height - 10}>{items[0]?.timestamp_start.slice(0, 10)}</text><text x={width - right} y={height - 10} textAnchor="end">{items.at(-1)?.timestamp_end.slice(0, 10)}</text>
    <text transform={`translate(14 ${top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Energy (MWh)</text>
  </svg><ChartLegend technologies={technologies} /><span className="line-key"><i />Demand</span></div>;
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
    <text x={left} y={height - 10}>0</text><text x={width - right} y={height - 10} textAnchor="end">{formatNumber(total)} MWh offered</text><text transform={`translate(14 ${top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Offer price (£/MWh)</text>
  </svg></div>;
}

function MarketReplayView({ run, onCreateFullReplayRevision }: { run?: ModelRun; onCreateFullReplayRevision: () => void }) {
  const [capabilities, setCapabilities] = useState<MarketCapability | null>(null);
  const [timeline, setTimeline] = useState<DispatchTimeline | null>(null);
  const [auction, setAuction] = useState<AuctionView | null>(null);
  const [storageRows, setStorageRows] = useState<StoragePeriodRow[]>([]);
  const [year, setYear] = useState(0); const [period, setPeriod] = useState(0);
  const [stage, setStage] = useState("ahead"); const [resolution, setResolution] = useState("daily");
  const [windowKind, setWindowKind] = useState<"24_hours" | "168_hours">("24_hours");
  const [periodFrom, setPeriodFrom] = useState(0);
  const [timelineOffset, setTimelineOffset] = useState(0);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(Boolean(run));
  const windowPeriods = windowKind === "24_hours" ? 48 : 336;
  const periodTo = periodFrom + windowPeriods - 1;
  const bidReplayAvailable = capabilities?.bid_replay_available ?? capabilities?.auction_replay ?? false;
  useEffect(() => { if (!run) return; let active = true; void getJson<MarketCapability>(`${API}/runs/${run.id}/market/capabilities`).then((payload) => { if (!active) return; setCapabilities(payload); setYear(payload.years[0] ?? 0); setStage(payload.auction_stages[0]?.stage ?? "ahead"); setPeriodFrom(0); setTimelineOffset(0); setError(""); }).catch((reason: Error) => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [run]);
  useEffect(() => { if (!run || !year) return; let active = true; const query = new URLSearchParams({ year: String(year), resolution, period_from: String(periodFrom), period_to: String(periodTo), limit: "96", offset: String(timelineOffset) }); void getJson<DispatchTimeline>(`${API}/runs/${run.id}/market/dispatch?${query}`).then((payload) => { if (!active) return; setTimeline(payload); setPeriod(payload.items[0]?.period_start ?? periodFrom); }).catch((reason: Error) => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [periodFrom, periodTo, resolution, run, timelineOffset, year]);
  useEffect(() => { if (!run || !year || !bidReplayAvailable || !stage) return; let active = true; void getJson<AuctionView>(`${API}/runs/${run.id}/market/auction?year=${year}&period=${period}&stage=${stage}`).then((payload) => { if (active) setAuction(payload); }).catch(() => { if (active) setAuction(null); }); return () => { active = false; }; }, [bidReplayAvailable, period, run, stage, year]);
  useEffect(() => { if (!run || !year || !capabilities?.storage_state) return; let active = true; void getJson<PageResult<StoragePeriodRow>>(`${API}/runs/${run.id}/market/storage?year=${year}&period=${period}&limit=100`).then((payload) => { if (active) setStorageRows(payload.items); }).catch(() => { if (active) setStorageRows([]); }); return () => { active = false; }; }, [capabilities?.storage_state, period, run, year]);
  if (!run) return <div className="page"><div className="empty-run"><b>No run selected</b><p>Select a run in Runs before opening market replay.</p></div></div>;
  const selected = timeline?.items.find((item) => item.period_start <= period && period <= item.period_end);
  return <div className="page evidence-page"><div className="page-title"><div><span>Physical market evidence</span><h2>Replay bids, then follow the dispatched system</h2><p>The upper chart is final physical dispatch after all clearing stages. Select a bounded bucket to inspect its recorded evidence. Settlement transfers are never drawn as generation.</p></div><Badge tone={bidReplayAvailable ? "good" : "blue"}>{capabilities?.trace_level ?? "loading"} trace</Badge></div>
    {loading && <p className="loading">Loading the bounded market view…</p>}{error && <div className="error-box">{error}</div>}
    {capabilities && !capabilities.period_summary && <div className="info-box">{capabilities.missing_reason}</div>}
    {capabilities && <TraceCoverageNotice traceLevel={capabilities.trace_level} bidReplayAvailable={bidReplayAvailable} onCreateFullReplayRevision={onCreateFullReplayRevision} />}
    {capabilities?.period_summary && <><section className="panel evidence-panel"><div className="evidence-controls"><label><span>Model year</span><select value={year} onChange={(event) => { setYear(Number(event.target.value)); setPeriodFrom(0); setTimelineOffset(0); }}>{capabilities.years.map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Window</span><select value={windowKind} onChange={(event) => { setWindowKind(event.target.value as "24_hours" | "168_hours"); setTimelineOffset(0); }}><option value="24_hours">24 hours</option><option value="168_hours">168 hours</option></select></label><label><span>First period</span><input type="number" min={0} value={periodFrom} onChange={(event) => { setPeriodFrom(Math.max(0, Number(event.target.value))); setTimelineOffset(0); }} /></label><label><span>Timeline resolution</span><select value={resolution} onChange={(event) => { setResolution(event.target.value); setTimelineOffset(0); }}><option value="daily">Daily overview</option><option value="weekly">Weekly overview</option><option value="half_hour">Half-hour detail</option></select></label><label><span>Selected period</span><input type="number" min={periodFrom} max={periodTo} value={period} onChange={(event) => setPeriod(Number(event.target.value))} /></label></div>
      <div className="bounded-window-controls"><button className="secondary" disabled={periodFrom === 0} onClick={() => { setPeriodFrom(Math.max(0, periodFrom - windowPeriods)); setTimelineOffset(0); }}>Previous window</button><span>Periods {periodFrom}–{periodTo} · page offset {timelineOffset}</span><button className="secondary" onClick={() => { setPeriodFrom(periodFrom + windowPeriods); setTimelineOffset(0); }}>Next window</button></div>
      {!capabilities.physical_dispatch && <div className="info-box">This historical run has period summaries but no final technology-level physical dispatch. VALUE will not reconstruct generation by summing staged accepted orders.</div>}
      {timeline && capabilities.physical_dispatch && <><DispatchChart timeline={timeline} selectedPeriod={period} onSelect={setPeriod} /><div className="bounded-page-controls"><button className="text-button" disabled={timelineOffset === 0} onClick={() => setTimelineOffset(Math.max(0, timelineOffset - timeline.limit))}>Previous page</button><span>{timeline.items.length} of {timeline.total} buckets in this selected window</span><button className="text-button" disabled={timelineOffset + timeline.items.length >= timeline.total} onClick={() => setTimelineOffset(timelineOffset + timeline.limit)}>Next page</button></div></>}
      {selected && <div className="selected-period-strip"><span><small>Window</small><b>{selected.timestamp_start.replace("T", " ")} to {selected.timestamp_end.replace("T", " ")}</b></span><span><small>Demand</small><b>{formatNumber(selected.real_demand_mwh)} MWh</b></span><span><small>Physical supply</small><b>{formatNumber(selected.accepted_supply_mwh)} MWh</b></span><span><small>Storage charge</small><b>{formatNumber(selected.storage_charge_mwh)} MWh</b></span><span><small>Price</small><b>£{formatNumber(selected.clearing_price_gbp_per_mwh)}/MWh</b></span></div>}
    </section>
    <section className="panel evidence-panel"><div className="panel-head"><div><span>Declared auction input</span><h3>Selected-period merit order</h3></div>{bidReplayAvailable ? <label className="inline-select"><span>Stage</span><select value={stage} onChange={(event) => setStage(event.target.value)}>{capabilities.auction_stages.map((item) => <option value={item.stage} key={item.stage}>{item.stage} · {item.order_detail.replaceAll("_", " ")}</option>)}</select></label> : <Badge tone="warn">No bid-level replay</Badge>}</div>
      {!bidReplayAvailable ? <div className="info-box">Bid detail is unavailable under the recorded trace profile. The summary above remains scientific evidence; this panel does not render missing bids as zero.</div> : !auction ? <div className="info-box">No exact {stage} auction is recorded for period {period}. If a daily or weekly bucket is selected, enter any half-hour period inside that window.</div> : <><div className="auction-layout"><MeritOrderChart auction={auction} /><div className="auction-facts"><span><small>Requirement</small><b>{formatNumber(auction.requirement_mwh)} MWh</b></span><span><small>Marginal accepted offer</small><b>{auction.marginal_offer_price_gbp_per_mwh == null ? "Not separately defined" : `£${formatNumber(auction.marginal_offer_price_gbp_per_mwh)}/MWh`}</b></span><span><small>Information available</small><b>{auction.information_scope}</b></span><span><small>Acceptance detail</small><b>{auction.offer_acceptance_coverage.replaceAll("_", " ")}</b></span></div></div><div className="table-scroll"><table><thead><tr><th>Order</th><th>Asset</th><th>Technology</th><th>Offer</th><th>Offered</th><th>Accepted</th><th>Evidence</th></tr></thead><tbody>{auction.offers.map((offer) => <tr key={offer.offer_id ?? `${offer.asset_id}-${offer.execution_order}`}><td>{offer.execution_order + 1}</td><td><b>{offer.asset_id}</b><small>{offer.asset_type}</small></td><td>{offer.technology.replaceAll("_", " ")}</td><td>£{formatNumber(offer.offer_price_gbp_per_mwh)}/MWh</td><td>{formatNumber(offer.offered_mwh)} MWh</td><td>{offer.accepted_mwh != null ? `${formatNumber(offer.accepted_mwh)} MWh` : offer.asset_accepted_mwh != null ? `${formatNumber(offer.asset_accepted_mwh)} MWh (asset total)` : "Not separately recorded"}</td><td>{offer.acceptance_granularity.replaceAll("_", " ")}</td></tr>)}</tbody></table></div><p className="provenance-line">Input hash {auction.input_sha256} · source ledger {auction.source_artifact_sha256 ?? "hash unavailable"}</p></>}
      {capabilities.storage_state && <div className="storage-period-panel"><header><div><small>Storage state at period {period}</small><b>{capabilities.storage_cost_module_id ?? "Cost policy not recorded"}</b></div><Badge>{storageRows.length} assets</Badge></header>{storageRows.length ? <div>{storageRows.map((row) => <span key={row.asset_id}><b>{row.asset_id}</b><small>SOC {formatNumber(row.state_of_charge_mwh)} / {formatNumber(row.energy_capacity_mwh)} MWh</small><em>charge {formatNumber(row.charge_mwh)} · discharge {formatNumber(row.discharge_mwh)} MWh · {formatNumber(row.power_capacity_mw)} MW</em></span>)}</div> : <p>No storage state is recorded for this selected period.</p>}</div>}
    </section><ReplayExportPanel key={`${run.id}-${year}-${period}`} apiOrigin={API_ORIGIN} runId={run.id} years={capabilities.years} selectedYear={year} selectedPeriod={period} /></>}
  </div>;
}

function VreTimelineChart({ timeline }: { timeline: DispatchTimeline }) {
  const width = 920; const height = 280; const left = 56; const right = 18; const top = 18; const bottom = 42; const items = timeline.items;
  const maximum = Math.max(1, ...items.flatMap((item) => [item.vre_available_mwh, item.vre_accepted_mwh, item.excess_mwh]));
  const plotWidth = width - left - right; const plotHeight = height - top - bottom;
  const x = (index: number) => left + index / Math.max(items.length - 1, 1) * plotWidth; const y = (value: number) => top + plotHeight - value / maximum * plotHeight;
  const points = (key: "vre_available_mwh" | "vre_accepted_mwh" | "excess_mwh" | "neutral_unused_vre_mwh") => items.map((item, index) => `${x(index)},${y(Number(item[key] ?? 0))}`).join(" ");
  return <div className="evidence-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Available, accepted and unused renewable energy timeline">{[0, .5, 1].map((fraction) => <g key={fraction}><line x1={left} x2={width - right} y1={y(maximum * fraction)} y2={y(maximum * fraction)} className="grid-line" /><text x={left - 8} y={y(maximum * fraction) + 4} textAnchor="end">{formatQuantity(maximum * fraction, 3)}</text></g>)}<polyline points={points("vre_available_mwh")} className="vre-available-line" /><polyline points={points("vre_accepted_mwh")} className="vre-accepted-line" /><polyline points={points("neutral_unused_vre_mwh")} className="vre-unused-line" /><polyline points={points("excess_mwh")} className="vre-excess-line" /><text x={left} y={height - 10}>{items[0]?.timestamp_start.slice(0, 10)}</text><text x={width - right} y={height - 10} textAnchor="end">{items.at(-1)?.timestamp_end.slice(0, 10)}</text><text transform={`translate(14 ${top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Energy (MWh)</text></svg><div className="line-legend"><span className="available">Available VRE</span><span className="accepted">Accepted VRE</span><span className="unused">Unused VRE</span><span className="excess">Pre-balancing excess</span></div></div>;
}

function CurtailmentView({ run }: { run?: ModelRun }) {
  const [summary, setSummary] = useState<VreSummary | null>(null); const [timeline, setTimeline] = useState<DispatchTimeline | null>(null);
  const [year, setYear] = useState(0); const [resolution, setResolution] = useState("daily"); const [error, setError] = useState("");
  useEffect(() => { if (!run) return; let active = true; void getJson<VreSummary>(`${API}/runs/${run.id}/market/vre-summary`).then((payload) => { if (!active) return; setSummary(payload); setYear(payload.years[0]?.year ?? 0); setError(""); }).catch((reason: Error) => { if (active) setError(reason.message); }); return () => { active = false; }; }, [run]);
  useEffect(() => { if (!run || !year) return; let active = true; void getJson<DispatchTimeline>(`${API}/runs/${run.id}/market/vre-timeline?year=${year}&resolution=${resolution}&limit=500`).then((payload) => { if (active) setTimeline(payload); }).catch((reason: Error) => { if (active) setError(reason.message); }); return () => { active = false; }; }, [resolution, run, year]);
  if (!run) return <div className="page"><div className="empty-run"><b>No run selected</b><p>Select a run in Runs before reviewing renewable-energy outcomes.</p></div></div>;
  const selected = summary?.years.find((item) => item.year === year);
  const maximum = Math.max(1, ...(summary?.years.map((item) => Math.max(item.available_vre_mwh, item.accepted_vre_mwh + (item.pre_balancing_excess_mwh ?? 0))) ?? [1]));
  // R3-21: one unit per KPI group, chosen from the group's largest magnitude.
  const annualEnergy = formatEnergyGroup(summary?.years.map((item) => item.pre_balancing_excess_mwh) ?? []);
  const kpiEnergy = formatEnergyGroup(selected ? [selected.available_vre_mwh, selected.accepted_vre_mwh, selected.neutral_unused_vre_mwh, selected.pre_balancing_excess_mwh, selected.balancing_curtailment_mwh, selected.storage_charge_mwh, selected.export_mwh, selected.flexible_demand_mwh] : []);
  return <div className="page evidence-page"><div className="page-title"><div><span>Renewable-energy evidence</span><h2>See how much VRE was available, used and left unused</h2><p>VALUE keeps the physical VRE identity separate from the retained VALUE market stages. Pre-balancing excess may include other inflexible low-cost generation; it is therefore displayed alongside, not silently renamed as VRE curtailment.</p></div><Badge tone={selected?.full_chronology ? "good" : "warn"}>{selected?.full_chronology ? "Full chronology" : "Diagnostic chronology"}</Badge></div>{error && <div className="error-box">{error}</div>}
    {summary && <><section className="panel evidence-panel"><div className="panel-head"><div><span>Across model years</span><h3>Annual VRE disposition</h3></div><Badge tone="blue">available = accepted + unused</Badge></div><div className="annual-vre-chart">{summary.years.map((item) => <button key={item.year} className={item.year === year ? "selected" : ""} onClick={() => setYear(item.year)}><span className="annual-bar"><i className="accepted" style={{ height: `${item.accepted_vre_mwh / maximum * 100}%` }} /><i className="unused" style={{ height: `${item.neutral_unused_vre_mwh / maximum * 100}%` }} /></span><b>{item.year}</b><small>{item.average_unused_vre_fraction == null ? "No VRE available" : `${formatNumber(item.average_unused_vre_fraction * 100, 1)}% unused`}</small>{item.pre_balancing_excess_mwh != null && <em>{annualEnergy.format(item.pre_balancing_excess_mwh)} excess</em>}</button>)}</div><div className="chart-legend"><span><i style={{ background: "#087e73" }} />Accepted VRE</span><span><i style={{ background: "#ef9a55" }} />Unused VRE</span></div></section>
      {selected && <section className="panel evidence-panel"><div className="panel-head"><div><span>{selected.year} evidence</span><h3>{selected.full_chronology ? "Annual accounting" : `${selected.period_count}-period diagnostic — not an annual result`}</h3></div><div className="evidence-controls compact"><label><span>Year</span><select value={year} onChange={(event) => setYear(Number(event.target.value))}>{summary.years.map((item) => <option key={item.year}>{item.year}</option>)}</select></label><label><span>Timeline</span><select value={resolution} onChange={(event) => setResolution(event.target.value)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="half_hour">Half-hour (first 500)</option></select></label></div></div>
        <div className="curtailment-kpis"><span><small>Available VRE</small><b title={`${selected.available_vre_mwh} MWh`}>{kpiEnergy.format(selected.available_vre_mwh) ?? "—"}</b></span><span><small>Accepted VRE</small><b title={`${selected.accepted_vre_mwh} MWh`}>{kpiEnergy.format(selected.accepted_vre_mwh) ?? "—"}</b></span><span><small>Unused VRE</small><b title={`${selected.neutral_unused_vre_mwh} MWh`}>{kpiEnergy.format(selected.neutral_unused_vre_mwh) ?? "—"}</b><em>{selected.average_unused_vre_fraction == null ? "No VRE available" : `${formatNumber(selected.average_unused_vre_fraction * 100, 2)}% of available`}</em></span><span><small>Pre-balancing excess</small><b>{selected.pre_balancing_excess_mwh == null ? "Not separately identified" : kpiEnergy.format(selected.pre_balancing_excess_mwh)}</b><em>{selected.pre_balancing_excess_scope.replaceAll("_", " ")}</em></span><span><small>Balancing curtailment</small><b>{selected.balancing_curtailment_mwh == null ? "Not separately identified" : kpiEnergy.format(selected.balancing_curtailment_mwh)}</b></span></div>
        <div className="destination-strip"><div><small>Simultaneous storage charging</small><b>{kpiEnergy.format(selected.storage_charge_mwh) ?? "—"}</b></div><div><small>Boundary exports</small><b>{kpiEnergy.format(selected.export_mwh) ?? "—"}</b></div><div><small>Flexible demand</small><b>{kpiEnergy.format(selected.flexible_demand_mwh) ?? "—"}</b></div><p>These are simultaneous system flows. The ledger does not claim that every charged, exported or flexible-load MWh came from VRE unless a source-linked flow is explicitly recorded.</p></div>
        {timeline && <VreTimelineChart timeline={timeline} />}
        <div className="event-summary"><span><small>Affected periods</small><b>{selected.affected_periods}</b></span><span><small>Longest continuous event</small><b>{formatNumber(selected.longest_event_hours)} hours</b></span><span><small>Peak event</small><b>{selected.peak_event_mwh == null ? "Not evaluated" : `${formatNumber(selected.peak_event_mwh)} MWh`}</b><em>{selected.peak_event_timestamp?.replace("T", " ")}</em></span><span><small>VRE identity residual</small><b>{formatNumber(selected.vre_identity_residual_mwh, 6)} MWh</b></span></div>
        <details className="definition-panel"><summary>Definitions and limits</summary><dl><div><dt>Unused VRE</dt><dd>Available renewable energy minus accepted renewable dispatch at the PSM boundary.</dd></div><div><dt>Pre-balancing excess</dt><dd>The retained VALUE ahead-stage surplus. Its scope is {selected.pre_balancing_excess_scope.replaceAll("_", " ")}; it is not assumed to be entirely renewable.</dd></div><div><dt>Balancing curtailment</dt><dd>Energy removed in the real-time balancing waterfall after forecast error, storage, export and flexible demand are considered.</dd></div><div><dt>Marginal curtailment</dt><dd>{selected.marginal_curtailment_reason}</dd></div></dl></details><p className="provenance-line">Coverage {selected.coverage_status.replaceAll("_", " ")} · source ledger {summary.source_artifact_sha256 ?? "hash unavailable"}</p>
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

function SystemResultsView({ run, onOpenMarket }: { run?: ModelRun; onOpenMarket: () => void }) {
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
    {capabilities && <section className="domain-capability-strip" aria-label="Optional-domain capability status">{PUBLIC_CAPABILITY_DOMAINS.map((key) => [key, capabilities.capabilities[key]] as const).filter((entry): entry is readonly [string, DomainCapability] => Boolean(entry[1])).map(([key, item]) => <article key={key}><span>{key.replaceAll("_", " ")}</span><Badge tone={item.status === "supported" ? "good" : item.status === "experimental" ? "warn" : "neutral"}>{item.status.replaceAll("_", " ")}</Badge><small>{item.claim ?? item.reason ?? "Artifact-backed result available."}</small></article>)}</section>}
    {capabilities && !availableDomains.length && <div className="empty-run"><b>No optional-domain result artifact is available</b><p>This is a valid single-node or diagnostic run. No network, hydrology or expansion quantities are reconstructed.</p></div>}
    {!!availableDomains.length && <><div className="audit-tabs domain-result-tabs" role="tablist" aria-label="Optional-domain result tabs">{availableDomains.map((item) => <button key={item} role="tab" aria-selected={domain === item} className={domain === item ? "active" : ""} onClick={() => { setDomain(item); setYear(capabilities?.capabilities[item].years?.[0] ?? 0); }}>{labels[item]}</button>)}</div>
      {selectedCapability?.years?.length ? <label className="inline-select domain-year"><span>Model year</span><select value={year} onChange={(event) => setYear(Number(event.target.value))}>{selectedCapability.years.map((item) => <option key={item}>{item}</option>)}</select></label> : null}
    </>}
    {domain === "network_dc" && network && <div className="domain-result-stack"><section className="panel"><div className="panel-head"><div><span>DC network · {network.year}</span><h3>Nodal balance and constrained transfers</h3></div><Badge tone="good">integrity checked</Badge></div><DomainMetricCards metrics={network.metrics} /><div className="network-result-layout"><TopologySchematic summary={network} /><div><h4>Annual branch envelope</h4><div className="table-scroll compact-table"><table><thead><tr><th>Branch</th><th>Endpoints</th><th>Rating</th><th>Maximum flow</th><th>Peak utilisation</th></tr></thead><tbody>{network.branch_summary.map((item) => <tr key={item.branch_id}><td>{item.branch_id}</td><td>{item.from_bus} → {item.to_bus}</td><td>{item.rating_mw == null ? "Not evaluated" : `${formatNumber(item.rating_mw)} MW`}</td><td>{formatNumber(item.maximum_absolute_flow_mw)} MW</td><td>{item.maximum_utilisation_fraction == null ? "Not evaluated" : `${formatNumber(item.maximum_utilisation_fraction * 100, 1)}%`}</td></tr>)}</tbody></table></div></div></div><button className="audit-link" onClick={onOpenMarket}>Open storage SOC in the authoritative Market replay ledger</button><p className="provenance-line">Declared input {network.source_artifacts.declared_input_sha256} · period index {network.source_artifacts.period_index_sha256}</p></section>
      {periods && <section className="panel"><div className="panel-head"><div><span>Bounded period query</span><h3>Angles, nodal LP duals and branch flows</h3></div><Badge tone="blue">{periods.items.length} of {periods.total} periods loaded</Badge></div><div className="period-chip-list" role="list" aria-label="Loaded network periods">{periods.items.map((item) => <button key={item.period_id} className={selectedPeriod === item.period_id ? "selected" : ""} onClick={() => setSelectedPeriod(item.period_id)}>{item.period_id}</button>)}</div>{selectedBusPeriod && <><div className="table-scroll"><table><thead><tr><th>Bus</th><th>Injection</th><th>Withdrawal</th><th>Load shed</th><th>Angle</th><th>Nodal LP dual</th></tr></thead><tbody>{selectedBusPeriod.buses.map((item) => <tr key={item.bus_id}><td>{item.bus_id}</td><td>{formatNumber(item.injection_mwh)} MWh</td><td>{formatNumber(item.withdrawal_mwh)} MWh</td><td>{formatNumber(item.blackout_mwh)} MWh</td><td>{formatNumber(item.angle_rad, 6)} rad</td><td>£{formatNumber(item.price_gbp_per_mwh)}/MWh</td></tr>)}</tbody></table></div>{branches && <div className="table-scroll"><table><thead><tr><th>Branch</th><th>Endpoints</th><th>Flow</th><th>Rating</th><th>Utilisation</th></tr></thead><tbody>{branches.items.map((item) => <tr key={`${item.period_id}-${item.branch_id}`}><td>{item.branch_id}</td><td>{item.from_bus} → {item.to_bus}</td><td>{formatNumber(item.flow_mw)} MW</td><td>{item.rating_mw == null ? "Not evaluated" : `${formatNumber(item.rating_mw)} MW`}</td><td>{item.utilisation_fraction == null ? item.utilisation_status.replaceAll("_", " ") : `${formatNumber(item.utilisation_fraction * 100, 1)}%`}</td></tr>)}</tbody></table></div>}</>}</section>}
    </div>}
    {domain === "network_expansion" && expansion && <div className="domain-result-stack"><section className="panel"><div className="panel-head"><div><span>Experimental transmission lifecycle</span><h3>{expansion.lineage}</h3></div><Badge tone="warn">{expansion.status}</Badge></div><div className="expansion-year-grid">{expansion.years.map((item) => <article key={item.year}><b>{item.year}</b><span>{item.proposals} proposed</span><span>{item.admitted} admitted</span><span>{item.commissioned} commissioned</span><span>{item.failed} failed · {item.retired} retired</span></article>)}</div><p className="audit-note">Before/after values are temporal descriptions only. Counterfactual effect: {expansion.counterfactual_claim.replaceAll("_", " ")}.</p></section>{events && <section className="panel"><div className="panel-head"><div><span>Candidate lineage events</span><h3>{events.total} indexed events</h3></div><Badge tone="blue">first {events.items.length}</Badge></div><div className="table-scroll"><table><thead><tr><th>Year / event</th><th>Candidate</th><th>Project / asset</th><th>Corridor</th><th>Build</th><th>Reason</th></tr></thead><tbody>{events.items.map((item) => <tr key={item.event_id}><td><b>{item.year}</b><small>{item.event_type}</small></td><td>{item.candidate_id}</td><td><small>{item.project_id ?? "No project yet"}</small><small>{item.asset_id ?? "No commissioned asset"}</small></td><td>{item.corridor_id}<small>{item.from_bus} → {item.to_bus}</small></td><td>{item.circuits} × {formatNumber(item.rating_mw)} MW</td><td>{item.reason_code}</td></tr>)}</tbody></table></div><p className="provenance-line">Source artifact {events.source_artifact_sha256}</p></section>}</div>}
    {capabilities?.capabilities.hydrology && <section className="panel unavailable-domain"><div><span>Natural-flow hydrology</span><h3>{capabilities.capabilities.hydrology.status.replaceAll("_", " ")}</h3><p>{capabilities.capabilities.hydrology.reason ?? "A typed hydrology result index is available."}</p></div><Badge tone={capabilities.capabilities.hydrology.status === "experimental" ? "warn" : "neutral"}>{capabilities.capabilities.hydrology.status.replaceAll("_", " ")}</Badge></section>}
    {capabilities && <p className="provenance-line">Run {String(capabilities.identity.run_id ?? run.id)} · project revision {String(capabilities.identity.project_revision_sha256 ?? "not recorded")} · graph {String(capabilities.identity.graph_sha256 ?? "not recorded")}</p>}
  </div>;
}

export default function Home() {
  const [view, setView] = useState<View>("overview");
  const [activePath, setActivePath] = useState<CommunityPath | null>(null);
  const [readMeOpen, setReadMeOpen] = useState(false);
  const [locationReady, setLocationReady] = useState(false);
  const pendingLocation = useRef<WorkspaceLocation | null>(null);
  const replaceLocation = useRef(true);
  const [workspace, setWorkspace] = useState<Workspace>(emptyWorkspace);
  const [definitions, setDefinitions] = useState<ParameterDefinition[]>([]);
  const [online, setOnline] = useState(false);
  const [launcherRequired, setLauncherRequired] = useState(false);
  const [connectionState, setConnectionState] = useState<"loading" | "online" | "offline">("loading");
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
  const [moduleTrust, setModuleTrust] = useState(false);
  const [moduleInstalling, setModuleInstalling] = useState(false);
  const [moduleLifecycle, setModuleLifecycle] = useState("");
  const [extensionBundle, setExtensionBundle] = useState<File | null>(null);
  const [extensionTrust, setExtensionTrust] = useState(false);
  const [extensionInstalling, setExtensionInstalling] = useState(false);
  const [extensionLifecycle, setExtensionLifecycle] = useState("");
  const [launching, setLaunching] = useState("");
  const [preflightMode, setPreflightMode] = useState<RunMode>("smoke");
  const [storedPreflight, setPreflight] = useState<PreflightReport | null>(null);
  const [pendingPreflightKey, setPendingPreflightKey] = useState<string | null>(null);
  const preflightRequest = useRef(0);
  const [notice, setNotice] = useState("");
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
      setConnectionState("online");
      setSelectedPackId((current) => next.data_packs.some((item) => item.id === current) ? current : (next.data_packs.find((item) => item.complete)?.id ?? next.data_packs[0]?.id ?? ""));
      const requestedRunId = pendingLocation.current?.runId;
      const requestedRun = next.runs.find((run) => run.id === requestedRunId);
      // Keep explicit identities, even when unavailable. Never silently replace a shared Run link.
      setSelectedProjectId((current) => current || requestedRun?.project_id || next.projects[0]?.id || "");
      pendingLocation.current = null;
      return next;
    } catch (error) {
      if (error instanceof LauncherAccessError) setLauncherRequired(true);
      setOnline(false); setConnectionState("offline"); return null;
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
  useEffect(() => {
    if (!selectedRunSummary) return;
    let active = true;
    const artifact = `${API}/runs/${selectedRunSummary.id}/artifacts/input-snapshot`;
    void Promise.all([
      getJson<ResourceReadiness>(`${artifact}/resource-readiness.json`).catch(() => null),
      getJson<Project>(`${artifact}/project.json`).catch(() => null),
      getJson<FrozenInputSnapshot>(`${artifact}/snapshot.json`).catch(() => null),
    ]).then(([readiness, project, snapshot]) => {
      if (!active) return;
      setFrozenRunReadiness(readiness); setFrozenRunProject(project); setFrozenInputSnapshot(snapshot); setFrozenRunSelectionId(selectedRunSummary.id);
    });
    return () => { active = false; };
  }, [selectedRunSummary]);
  const hasActiveRun = workspace.runs.some((run) => ["queued", "snapshotting", "running", "cancel_requested"].includes(run.status));
  useEffect(() => { if (!hasActiveRun) return; const timer = window.setInterval(() => void refresh(), 2000); return () => window.clearInterval(timer); }, [hasActiveRun, refresh]);

  const selectedPack = useMemo(() => workspace.data_packs.find((pack) => pack.id === selectedPackId) ?? workspace.data_packs[0], [selectedPackId, workspace.data_packs]);
  const selectedProject = workspace.projects.find((project) => project.id === selectedProjectId);
  const selectedProjectPack = workspace.data_packs.find((pack) => pack.id === selectedProject?.data_pack_id);
  const allowedStudyModes = runModesForStudy(selectedProject, selectedProjectPack);
  const canRunMode = (mode: RunMode) => allowedStudyModes.includes(mode);
  const effectivePreflightMode = selectedRunScope(preflightMode, allowedStudyModes);
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
    if (!nextModes.includes(preflightMode) && nextModes.length) {
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
    });
    if (search !== window.location.search) {
      const url = `${window.location.pathname}${search}${window.location.hash}`;
      if (replaceLocation.current) window.history.replaceState(null, "", url);
      else window.history.pushState(null, "", url);
    }
    replaceLocation.current = false;
  }, [activePath, connectionState, dataContextId, locationReady, selectedProjectId, selectedRunId, selectedRunSummary?.id, view]);

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
    request.open("POST", researchSuiteApiUrl(API_ORIGIN));
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

  async function installModule() {
    if (!moduleBundle) { setNotice("Choose a VALUE module ZIP first."); return; }
    if (!moduleTrust) { setNotice("Confirm that you trust the executable Python in this bundle."); return; }
    setModuleInstalling(true); setNotice("");
    try {
      const response = await fetch(`${API}/modules/install`, {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Filename": encodeURIComponent(moduleBundle.name),
          "X-VALUE-Executable-Trust": "acknowledged",
        },
        body: moduleBundle,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || "Module installation failed"}`);
      setNotice(`${payload.installation.name} ${payload.installation.module_version} passed structural conformance. Run a wiring test before research use.`);
      setModuleBundle(null); setModuleTrust(false); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Module installation failed"); }
    finally { setModuleInstalling(false); }
  }

  async function changeModuleState(installation: ModuleInstallation, enabled: boolean) {
    setModuleLifecycle(installation.module_id); setNotice("");
    try {
      const response = await fetch(`${API}/modules/${encodeURIComponent(installation.module_id)}/${enabled ? "enable" : "disable"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const payload = await response.json();
      if (!response.ok) {
        const projects = payload.dependents?.projects?.join(", ");
        throw new Error(`${payload.error}${projects ? `: ${projects}` : ""}`);
      }
      setNotice(`${installation.name} is now ${enabled ? "enabled and selectable" : "disabled"}.`); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Module state change failed"); }
    finally { setModuleLifecycle(""); }
  }

  async function installExtension() {
    if (!extensionBundle) { setNotice("Choose a value.extension-bundle/v1 ZIP first."); return; }
    if (!extensionTrust) { setNotice("Acknowledge the in-process trusted-code boundary before installation."); return; }
    setExtensionInstalling(true); setNotice("");
    try {
      const response = await fetch(`${API}/extensions/install`, {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Filename": encodeURIComponent(extensionBundle.name),
          "X-VALUE-Executable-Trust": "acknowledged",
        },
        body: extensionBundle,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error || "Extension installation failed"}`);
      setNotice(`${payload.installation.extension_id} ${payload.installation.version} passed structural extension validation. Its declared scientific maturity has not changed.`);
      setExtensionBundle(null); setExtensionTrust(false); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Extension installation failed"); }
    finally { setExtensionInstalling(false); }
  }

  async function changeExtensionState(installation: ExtensionInstallation, enabled: boolean) {
    setExtensionLifecycle(installation.extension_id); setNotice("");
    try {
      const response = await fetch(`${API}/extensions/${encodeURIComponent(installation.extension_id)}/${enabled ? "enable" : "disable"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const payload = await response.json();
      if (!response.ok) {
        const dependents = [...(payload.dependents?.projects ?? []), ...(payload.dependents?.runs_and_retained_history ?? [])];
        throw new Error(`${payload.error_code ? `${payload.error_code}: ` : ""}${payload.error}${dependents.length ? ` — ${dependents.join(", ")}` : ""}`);
      }
      setNotice(`${installation.extension_id} is now ${enabled ? "enabled" : "disabled"}.`); await refresh();
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
    setLaunching(mode); setNotice("");
    try {
      const response = await fetch(`${API}/projects/${targetProject.id}/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
      const payload = await response.json(); if (!response.ok) { if (preflightMatches(payload.preflight, targetProject, mode)) { setPreflight(payload.preflight); } throw new Error(payload.error || "Unable to start the model"); }
      setSelectedRunId(payload.run.id);
      setView("run");
      setNotice(mode === "smoke" ? "The two-period wiring verification has started." : mode === "two_year_smoke" ? "The two-year smoke verification has started." : mode === "value_101_day" ? "The one-day VALUE 101 PSM lesson has started." : mode === "two_year" ? "The complete two-year model has started." : "The complete annual model run has started.");
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
    ].map((group) => <div className="workspace-nav-group" key={group.label}><p>{group.label}</p>{group.ids.map((id) => views.find((item) => item.id === id)!).map((item) => <button type="button" aria-label={`${item.label}: ${item.note}`} aria-current={view === item.id ? "page" : undefined} key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}><i>{item.index}</i><span><b>{item.label}</b><small>{item.note}</small></span></button>)}</div>)}</nav>
    <div className="rail-foot"><div className={`service ${connectionState === "online" && workspace.runtime.compatible ? "online" : ""}`}><i /><span><b>{connectionState === "loading" ? "Connecting to model service…" : connectionState === "online" ? `Python ${workspace.runtime.python}` : "Model service offline"}</b><small>{connectionState === "loading" ? "Checking the local API" : connectionState === "online" ? (workspace.runtime.compatible ? `${workspace.runtime.selected_capability ?? "value-native"} ready` : "VALUE native runtime unavailable") : "Start VALUE locally, then retry"}</small></span>{connectionState === "offline" && <button onClick={() => void refresh()}>Retry</button>}</div><small>Contract {workspace.architecture_version.replace("value.contracts/", "")}</small></div></aside>
    <section className="surface"><header className="topbar"><div><small>VALUE / {views.find((item) => item.id === view)?.index}</small><h1>{views.find((item) => item.id === view)?.label}</h1></div><div className="top-meta">
      {!isRunView && view !== "journey" && !(view === "data" && isJourneyData) && <><label><span>Draft data pack</span><select aria-label="Selected data pack" value={selectedPack?.id ?? ""} onChange={(event) => setSelectedPackId(event.target.value)} disabled={!online}>{workspace.data_packs.map((pack) => <option value={pack.id} key={pack.id}>{modelDisplayName(pack.name)}</option>)}</select></label><Badge tone={online && selectedPack?.complete ? "good" : "warn"}>{connectionState !== "online" ? "Inputs not loaded" : selectedPack ? `${selectedPack.valid_required_count} of ${selectedPack.required_count} inputs ready` : "No data pack"}</Badge></>}
      <button type="button" className="secondary workspace-readme-trigger" onClick={() => setReadMeOpen(true)} aria-haspopup="dialog">Read me</button>
    </div></header>
    <ReadMePanel open={readMeOpen} onClose={() => setReadMeOpen(false)} />
    {view !== "overview" && <CommunityPathPicker activePath={activePath} onSelect={chooseCommunityPath} />}
    {isRunView ? <RunContextBar run={selectedRun} frozen={{ runId: frozenRunSelectionId, status: frozenRunSelectionId === selectedRun?.id ? frozenRunProject ? "ready" : "unavailable" : "loading", project: frozenRunProject, snapshot: frozenInputSnapshot }} /> : view === "projects" && !editingProjectId ? <div className="workspace-study-context"><span>Independent Study draft</span><b>{projectForm.name}</b><small>Review and save to create a new Study.</small></div> : selectedProject && <div className="workspace-study-context"><span>Selected saved Study</span><b>{selectedProject.name}</b><span>revision {selectedProject.revision_number ?? "not recorded"}</span><small>Editing is saved as a new revision.</small></div>}
    {online && selectedRunId && isRunView && !selectedRun && <div className="notice" role="status">The requested Run is unavailable or belongs to another Study. Choose a Study and Run from Runs; no substitute result has been opened.</div>}
    {notice && <div className="notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")}>Close</button></div>}

    <div hidden={view !== "journey"} className="page">
      <ResearchJourney intent={activePath === "data" ? "data" : "reproduce"} studies={workspace.projects} packs={workspace.data_packs}
        initialStudyId={selectedProjectId} apiOrigin={API_ORIGIN} online={online}
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
        apiOrigin={API_ORIGIN} networkPackId={journeyNetworkPackId}
        readOnlyReason={journeyReadOnlyReason || (!dataContextResolution ? "正在解析基线方法所需的数据角色…" : "")}
        busy={Boolean(uploading)} onUpload={(role, file) => void upload(role, file)}
        onMapped={async () => { setPreflight(null); setSavedDataResolution(null); await refresh(); }}
        onPreview={(role) => void previewDataRole(role)} onReturn={() => setView("journey")} />}
      <DataWorkbench apiOrigin={API_ORIGIN} onWorkspaceChanged={async () => { setPreflight(null); setSavedDataResolution(null); await refresh(); }} />
      <section className="panel data-context">
        <div><span>Input contract for</span><select aria-label="Data input context" value={dataContextId} onChange={(event) => { setDataContextId(event.target.value); setSavedDataResolution(null); setDataPreview(null); }}>
          {isJourneyData && <option value="journey">引导中的独立数据包 · {dataContextPack?.name ?? "尚未选择"}</option>}
          <option value="draft">Current unsaved Study draft</option>
          {dataContextId !== "draft" && !isJourneyData && !dataContextProject && <option value={dataContextId}>Study unavailable · {dataContextId}</option>}
          {workspace.projects.map((project) => <option value={project.id} key={project.id}>{project.name} · revision {project.revision_number ?? 0}</option>)}
        </select></div>
        <div><strong>{dataContextResolution ? `${dataContextResolution.data_readiness.available}/${dataContextResolution.data_readiness.required}` : "Not evaluated"}</strong><span>required inputs ready</span></div>
        {dataContextPackId && <a className="secondary" href={`${API}/data-packs/${encodeURIComponent(dataContextPackId)}/missing-checklist?extensions=${encodeURIComponent(dataContextExtensions.join(","))}&format=json`}>Download missing-input checklist</a>}
      </section>
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
      <div className="page-title"><div><span>VALUE module registry</span><h2>The model is assembled here</h2><p>Each card resolves to one executable Python implementation. Install a reviewed local bundle to replace one part of the model without editing VALUE.</p></div><Badge tone="good">{readyModules} of {workspace.modules.length} ready</Badge></div>
      <div><ModuleAuthorWorkbench apiOrigin={API_ORIGIN} modules={workspace.modules} projects={workspace.projects}
        onInstallRequest={() => document.getElementById("module-installer")?.scrollIntoView({ block: "start", behavior: "smooth" })}
        onCreated={async ({ id }) => {
          const refreshed = await refresh();
          setSelectedProjectId(id); setSelectedRunId(""); setPreflight(null); setView("run");
          setNotice(refreshed ? "方法对照 Study 已保存。数据与其他配置保持不变，尚未启动 Run。" : "方法对照 Study 已保存，但工作区刷新失败。恢复连接后可在 Runs 继续；尚未启动 Run。");
        }} /></div>
      <section className="panel module-installer" id="module-installer">
        <div className="module-installer-copy"><span>Local extension</span><h3>Install a model module</h3><p>A modeller prepares one signed-off ZIP containing a manifest, licence and self-contained Python source. VALUE verifies its inventory, public contract and callable shape before it enters the registry.</p><small>Structural conformance is not scientific validation. Installed Python runs inside the local VALUE process.</small></div>
        <div className="module-installer-form">
          <label className="module-file"><span>Module bundle · .zip · up to 25 MiB</span><input type="file" accept=".zip,application/zip" onChange={(event) => setModuleBundle(event.target.files?.[0] ?? null)} /><b>{moduleBundle?.name ?? "Choose a VALUE module bundle"}</b></label>
          <label className="trust-check"><input type="checkbox" checked={moduleTrust} onChange={(event) => setModuleTrust(event.target.checked)} /><span>I trust the source of this bundle and understand that it contains executable Python code.</span></label>
          <button className="primary" disabled={!moduleBundle || !moduleTrust || moduleInstalling} onClick={() => void installModule()}>{moduleInstalling ? "Validating and installing…" : "Install and validate module"}</button>
          <details><summary>For module developers</summary><code>py -3.10 scripts\build_module_bundle.py --manifest value-module.json --source-root src --license LICENSE --output my-module.zip</code></details>
        </div>
      </section>
      {workspace.module_installations.length > 0 && <section className="installed-modules">
        <header><div><span>Installed locally</span><h3>External module packages</h3></div><Badge>{workspace.module_installations.length}</Badge></header>
        <div>{workspace.module_installations.map((installation) => {
          const projectReferences = workspace.projects.filter((project) => Object.values(project.modules).includes(installation.module_id));
          return <article key={installation.module_id}><div><b>{installation.name}</b><small>{installation.module_id} · {installation.slot.replaceAll("_", " ")} · {installation.module_version}</small></div><span><small>Contract</small><code>{installation.contract_version}</code></span><span><small>Source SHA-256</small><code>{installation.source_sha256?.slice(0, 16) ?? "not recorded"}…</code></span><span><small>Conformance</small><b>{installation.conformance.status}</b></span><button className="text-button" disabled={moduleLifecycle === installation.module_id || (installation.enabled && projectReferences.length > 0)} title={projectReferences.length ? `Used by ${projectReferences.map((project) => project.name).join(", ")}` : ""} onClick={() => void changeModuleState(installation, !installation.enabled)}>{moduleLifecycle === installation.module_id ? "Updating…" : installation.enabled ? "Disable" : "Enable"}</button>{projectReferences.length > 0 && <p>Used by {projectReferences.length} saved {projectReferences.length === 1 ? "Study" : "Studies"}; disable is blocked until those configurations are migrated.</p>}</article>;
        })}</div>
      </section>}
      <ExtensionAuthorWorkbench apiOrigin={API_ORIGIN} extensions={workspace.extensions} modules={workspace.modules}
        onInstallRequest={() => document.getElementById("extension-installer")?.scrollIntoView({ block: "start", behavior: "smooth" })}
        onOpenStudies={() => {
          setEditingProjectId(undefined); setEditingBaseRevision(undefined); setDataContextId("draft");
          setProjectForm(current => ({ ...current, name: `${current.name || "New"} · extension study`, maturity_acknowledgements: {} }));
          setPreflight(null); setView("projects");
          setNotice("Independent Study draft opened. Choose the installed extension and an independent data pack, bind its inputs in Data, then review and save. No Run has started.");
        }} />
      <section className="panel extension-installer" id="extension-installer">
        <div className="module-installer-copy"><span>Capability package</span><h3>Install a model extension</h3><p>An extension adds data roles, parameters, lifecycle hooks or a new model domain through <code>value.extension-bundle/v1</code>. It does not silently replace a module.</p><small>Three levels are supported: data-only contracts, replacement modules installed separately, and new domains composed from both. The browser never runs pip or downloads dependencies.</small></div>
        <div className="module-installer-form"><label className="module-file"><span>Extension bundle · .zip · up to 25 MiB</span><input type="file" accept=".zip,application/zip" onChange={(event) => setExtensionBundle(event.target.files?.[0] ?? null)} /><b>{extensionBundle?.name ?? "Choose an extension bundle"}</b></label><label className="trust-check"><input type="checkbox" checked={extensionTrust} onChange={(event) => setExtensionTrust(event.target.checked)} /><span>I trust the bundle source and understand that extension hooks and composed modules execute as trusted Python in the local process. No OS sandbox is claimed.</span></label><button className="primary" disabled={!extensionBundle || !extensionTrust || extensionInstalling} onClick={() => void installExtension()}>{extensionInstalling ? "Checking inventory and dependencies…" : "Install and validate extension"}</button></div>
      </section>
      <section className="extension-catalogue"><header><div><span>One workspace registry</span><h3>Installed and built-in extensions</h3></div><Badge>{workspace.extensions.length}</Badge></header><div>{workspace.extensions.map((extension) => { const installation = workspace.extension_installations.find((item) => item.extension_id === extension.id && item.version === extension.version); const projectReferences = workspace.projects.filter((project) => project.selected_extensions?.includes(extension.id)); return <article key={extension.id}><header><div><b>{extension.name}</b><small>{extension.id} · {extension.version} · {extension.namespace}</small></div><Badge tone={extension.maturity === "ready" ? "good" : "warn"}>{extension.maturity.replaceAll("_", " ")}</Badge></header><p><strong>Provides</strong> {extension.provided_capabilities.join(" · ") || "No capability declared"}</p><p><strong>Requires</strong> {extension.required_capabilities.join(" · ") || "No additional capability"}</p><div><span><small>Conditional data</small><b>{extension.data_roles.filter((role) => role.required).length} required · {extension.data_roles.filter((role) => !role.required).length} optional</b></span><span><small>Composed modules</small><b>{extension.composed_module_ids.join(", ") || "none"}</b></span><span><small>Licence / manifest</small><b>{extension.licence} · {extension.manifest_sha256.slice(0, 12)}…</b></span><span><small>Origin</small><b>{extension.origin.replaceAll("_", " ")} · {extension.enabled ? "enabled" : "disabled"}</b></span></div>{installation && <footer><code>{installation.installation_boundary} · {installation.bundle_sha256.slice(0, 16)}…</code><button className="text-button" disabled={extensionLifecycle === extension.id || (installation.enabled && projectReferences.length > 0)} title={projectReferences.length ? `Used by ${projectReferences.map((project) => project.name).join(", ")}` : ""} onClick={() => void changeExtensionState(installation, !installation.enabled)}>{extensionLifecycle === extension.id ? "Updating…" : installation.enabled ? "Disable" : "Enable"}</button></footer>}{projectReferences.length > 0 && <em>Referenced by {projectReferences.length} saved {projectReferences.length === 1 ? "Study" : "Studies"}; disabling is blocked.</em>}</article>; })}</div></section>
      <div className="module-list">{workspace.modules.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0)).map((module, index) => <article className="module-card" key={module.id}><header><div className={`module-mark ${module.kind}`}>{String(index + 1).padStart(2, "0")}</div><div><span>{module.kind.toUpperCase()} · {module.slot.replaceAll("_", " ")} · {module.version}</span><h3>{modelDisplayName(module.name)}</h3></div><Badge tone={module.status === "ready" ? "good" : "warn"}>{module.origin === "local_bundle" ? `local · ${module.status}` : module.status}</Badge></header><p>{modelDisplayName(module.description)}</p><div className="module-id"><span>Implementation</span><code>{module.id}</code><small>Contract {module.contract_version ?? "not recorded"}</small></div>{module.id === "value-bid-at-cost-psm" && <div className="compatibility-note">Live module · bid-at-cost clearing through the v2 orchestrator</div>}<details className="io"><summary>Inputs and outputs</summary><div><span>Inputs</span>{module.inputs.map((input) => <code key={input}>{input}</code>)}</div><i>→</i><div><span>Outputs</span>{module.outputs.map((output) => <code key={output}>{output}</code>)}</div></details></article>)}</div>
    </div>}

    {view === "projects" && <div className="page project-page"><div className="page-title"><div><span>Study setup</span><h2>Define the scientific question, then resolve the model</h2><p>The composer connects one data pack, physical domain, optional extensions, model chain and assumptions. Saving creates an immutable revision of exactly the graph shown in Review.</p></div><Badge tone={draftResolution?.valid ? "good" : "warn"}>{draftResolving ? "Resolving" : draftResolution?.valid ? "Draft ready" : "Draft incomplete"}</Badge></div><StudyComposer initialStep={composerInitialStep} apiOrigin={API_ORIGIN} workspace={workspace} form={projectForm} selectedPackId={selectedPack?.id ?? selectedPackId} resolution={draftResolution} resolving={draftResolving} resolutionError={draftResolutionError} savedProjects={workspace.projects} studyTrash={workspace.study_trash} selectedProjectId={selectedProjectId} assumptions={<><AdvancedSettings definitions={definitions} values={{ ...parameterValues, ...runtimeValues }} resolvedSources={resolvedSources} onChange={(id, value, runtime) => runtime ? setRuntimeValues((current) => ({ ...current, [id]: value })) : setParameterValues((current) => ({ ...current, [id]: value }))} /><button className="text-button full" onClick={() => void previewParameters()}>Check effective base values</button></>} onForm={(update) => setProjectForm(update)} onPack={setSelectedPackId} onDomain={chooseDomain} onExtension={toggleExtension} onModule={selectStudyModule} onExtensionParameter={(name, value) => setProjectForm((current) => ({ ...current, extension_parameters: { ...current.extension_parameters, [name]: value } }))} onAcknowledgement={(key, value, checked) => setProjectForm((current) => { const maturity_acknowledgements = { ...current.maturity_acknowledgements }; if (checked) maturity_acknowledgements[key] = value; else delete maturity_acknowledgements[key]; return { ...current, maturity_acknowledgements }; })} onSave={() => void saveProject()} onLoad={loadProjectRevision} onOpenRun={(project) => { selectRunProject(project.id); setView("run"); }} onTrash={(project, linkedRunCount) => void moveStudyToTrash(project, linkedRunCount)} onRestore={(entry) => void restoreStudyEntry(entry)} onOpenTrashRuns={(entry) => { const run = workspace.runs.find((item) => item.project_id === entry.study_id); setSelectedProjectId(entry.study_id); setSelectedRunId(run?.id ?? ""); setSelectedRunDetail(null); setView("run"); if (!run) setNotice("No indexed Run is available for this trashed Study; restore it to inspect non-indexed legacy evidence."); }} onOpenData={() => { setDataContextId("draft"); setView("data"); }} traceLevel={(runtimeValues["runtime.market_trace_level"] as TraceProfile | undefined) ?? "summary"} onTraceLevel={(trace) => setRuntimeValues((current) => ({ ...current, "runtime.market_trace_level": trace }))} /></div>}

    {view === "run" && <RunWorkspace apiOrigin={API_ORIGIN} workspace={workspace} selectedProjectId={selectedProjectId} selectedProject={selectedProject} selectedProjectPack={selectedProjectPack} selectedRun={selectedRun} projectRuns={projectRuns} preflight={preflight} effectivePreflightMode={effectivePreflightMode} checkingPreflight={checkingPreflight} zonalPreflight={zonalPreflight} teachingProject={teachingProject} launching={launching} selectedRunSourceMutable={selectedRunSourceMutable} canRunMode={canRunMode} frozen={{ contextKind: selectedRunContext.kind, runId: frozenRunSelectionId, readiness: frozenRunReadiness, project: frozenRunProject, snapshot: frozenInputSnapshot }} actions={{ selectRunProject, onSelectRun: setSelectedRunId, onMode: (mode) => { setPreflightMode(mode); setPreflight(null); }, onNavigate: setView, cloneStoragePolicy, checkPreflight, startRun, resumeRun, rerunAsCopperplate, lifecycleAction, onRecoveredStudyCreated }} />}

    {view === "marketReplay" && <MarketReplayView run={selectedRun} onCreateFullReplayRevision={createFullReplayRevision} />}

    {view === "curtailment" && <><ResultQueryPanel key={`query-${selectedRun?.id ?? "no-run"}`} run={selectedRun} apiOrigin={API_ORIGIN} /><CurtailmentView key={`physical-${selectedRun?.id ?? "no-run"}`} run={selectedRun} /></>}

    {view === "networkRedispatch" && <NetworkRedispatchView key={selectedRun?.id ?? "no-run"} run={selectedRun} apiOrigin={API_ORIGIN} sourceStudyMutable={selectedRunSourceMutable} onOpenMarket={() => setView("marketReplay")} onCreateFullReplayRevision={createFullReplayRevision} onOpenRun={() => setView("run")} onRerun={() => selectedRun ? rerunAsCopperplate(selectedRun) : Promise.resolve()} />}

    {view === "systems" && <SystemResultsView run={selectedRun} onOpenMarket={() => setView("marketReplay")} />}

    {view === "audit" && <AuditView run={selectedRun} apiOrigin={API_ORIGIN} onCreateFullReplayRevision={createFullReplayRevision} />}

    {view === "extend" && <div className="page"><div className="page-title"><div><span>Data adapters</span><h2>Bring another dataset into VALUE</h2><p>Map local tables to stable model roles once. The PSM and CEM can then read the new source without source-specific code entering the model modules.</p></div></div><div className="adapter-steps">{[["01", "Describe the pack", "Record its country, timezone, licence and source versions."], ["02", "Map each role", "Connect local tables and columns to the PSM and CEM input contracts."], ["03", "Align units and time", "Convert power, energy, currency and timestamps at the adapter boundary."], ["04", "Check the contract", "Confirm every selected module receives the expected fields and units."]].map(([number, title, copy]) => <article key={number}><i>{number}</i><h3>{title}</h3><p>{copy}</p></article>)}</div><section className="panel contract-example"><div><span>Minimal adapter output</span><h3>A manifest and a mapping</h3><p>VALUE recognises semantic roles. File formats, column names and API details remain inside the adapter.</p></div><pre>{`data_pack: my-country-2030\ncountry: XX\ntimezone: Region/City\nbindings:\n  demand.real:\n    source: demand.csv\n    column: observed_mwh\n    unit: MWh/period\n  projects.repd:\n    source: projects.parquet\n    mapping:\n      capacity_mw: size_mw\n      technology: tech_code`}</pre></section></div>}
    </section></main>;
}
