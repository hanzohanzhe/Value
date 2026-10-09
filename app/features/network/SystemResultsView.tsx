"use client";

// Optional-domain results (moved verbatim from app/page.tsx in P1 W3; route /runs/[runId]/systems).
import { statusWord } from "../shared/labels.ts";
import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, getJson } from "../../lib/api.ts";
import { Badge, formatNumber, withUnit } from "../shared/presentation";
import { PUBLIC_CAPABILITY_DOMAINS, domainLabel } from "../shared/domainConstants";
import { useStableRun } from "../shared/stableRun.ts";
import type { ModelRun } from "../runs/types";
import { PageHeader } from "../../ui/PageHeader.tsx";
import { Tabs } from "../../ui/Tabs.tsx";
import { systemsQueryValues, systemsTab, systemsYear, type SystemsLocation } from "./systemsLocation.ts";
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey, Translate } from "../../i18n/index.ts";
import { periodIdLabel } from "../shared/modelClock.ts";

const API = API_BASE;

type DomainCapability = { status: "supported" | "experimental" | "unsupported" | "not_evaluated"; years?: number[]; claim?: string; reason?: string | null };
type DomainCapabilitiesPayload = { schema_version: string; identity: Record<string, unknown>; capabilities: Record<string, DomainCapability> };
type ResultMetric = { value: number | string | null; unit: string; definition_id: string; source_artifact_sha256?: string };
type NetworkSummaryPayload = { year: number; identity: Record<string, unknown>; source_artifacts: Record<string, string>; metrics: Record<string, ResultMetric>; topology: { buses: Record<string, unknown>[]; branches: Record<string, unknown>[]; reference_buses: string[]; placement: string }; branch_summary: { branch_id: string; from_bus?: string; to_bus?: string; rating_mw?: number | null; maximum_absolute_flow_mw: number; maximum_utilisation_fraction?: number | null }[]; storage_soc: { endpoint: string; reason: string } };
type NetworkPeriodPayload = { year: number; total: number; limit: number; offset: number; source_artifact_sha256: string; definitions: Record<string, string>; units: Record<string, string>; items: { period_id: string; injection_mwh: number; withdrawal_mwh: number; blackout_mwh: number; mean_nodal_price: number; buses: { bus_id: string; injection_mwh: number; withdrawal_mwh: number; blackout_mwh: number; angle_rad: number; price_gbp_per_mwh: number }[] }[] };
type NetworkBranchPayload = { total: number; limit: number; offset: number; source_artifact_sha256: string; items: { period_id: string; branch_id: string; from_bus?: string; to_bus?: string; flow_mw: number; rating_mw?: number | null; utilisation_fraction?: number | null; utilisation_status: string }[] };
type ExpansionSummaryPayload = { status: string; source_artifact_sha256: string; lineage: string; counterfactual_claim: string; years: { year: number; proposals: number; admitted: number; commissioned: number; failed: number; retired: number }[] };
type ExpansionEventPayload = { total: number; source_artifact_sha256: string; items: { year: number; event_id: string; event_type: string; candidate_id: string; project_id?: string; asset_id?: string; corridor_id: string; from_bus: string; to_bus: string; circuits: number; rating_mw: number; reason_code: string }[] };

type OptionalResultDomain = "network_dc" | "network_expansion";
const PUBLIC_RESULT_DOMAINS: OptionalResultDomain[] = ["network_dc", "network_expansion"];


function metricValue(t: Translate, metric?: ResultMetric) {
  if (!metric || metric.value == null) return t("systems.value.notEvaluated");
  const value = typeof metric.value === "number" ? formatNumber(metric.value, 5) : String(metric.value);
  return `${value}${metric.unit ? ` ${metric.unit}` : ""}`;
}

function DomainMetricCards({ metrics }: { metrics: Record<string, ResultMetric> }) {
  const t = useT();
  return <div className="domain-result-metrics">{Object.entries(metrics).map(([key, metric]) => <article key={key}>
    <small>{key.replaceAll("_", " ")}</small><b>{metricValue(t, metric)}</b>
    <em>{metric.definition_id}</em>
  </article>)}</div>;
}

function TopologySchematic({ summary }: { summary: NetworkSummaryPayload }) {
  const t = useT();
  const buses = summary.topology.buses;
  const width = 720; const height = 330; const cx = width / 2; const cy = height / 2; const radius = Math.min(width, height) * .34;
  const positions = new Map(buses.map((bus, index) => {
    const angle = (Math.PI * 2 * index / Math.max(1, buses.length)) - Math.PI / 2;
    return [String(bus.bus_id ?? `bus-${index + 1}`), { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }] as const;
  }));
  return <div className="topology-schematic"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t("systems.topology.label")}>
    {summary.topology.branches.map((branch, index) => { const from = positions.get(String(branch.from_bus)); const to = positions.get(String(branch.to_bus)); if (!from || !to) return null; return <g key={String(branch.branch_id ?? index)}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} /><text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 6}>{String(branch.branch_id ?? "branch")}</text></g>; })}
    {buses.map((bus, index) => { const id = String(bus.bus_id ?? `bus-${index + 1}`); const point = positions.get(id)!; const reference = summary.topology.reference_buses.includes(id); return <g key={id} className={reference ? "reference-bus" : ""}><circle cx={point.x} cy={point.y} r={reference ? 18 : 15} /><text x={point.x} y={point.y + 4} textAnchor="middle">{id}</text></g>; })}
  </svg><p>{t("systems.topology.note")}</p></div>;
}

export default function SystemResultsView({ run: liveRun, onOpenMarket, onOpenNetwork, linked = { tab: null, year: null }, onLocationChange }: {
  run?: ModelRun; onOpenMarket: () => void; onOpenNetwork: () => void;
  /** R-10 (P1-polish): the domain and year the URL names, read once when the page opens. */
  linked?: SystemsLocation;
  /** Writes the page's query (tab, year) whenever they change. */
  onLocationChange?: (values: Record<string, string | number | null>) => void;
}) {
  const run = useStableRun(liveRun);
  const t = useT();
  const [capabilities, setCapabilities] = useState<DomainCapabilitiesPayload | null>(null);
  const [domain, setDomain] = useState<OptionalResultDomain | null>(null);
  const [year, setYear] = useState(0); const [selectedPeriod, setSelectedPeriod] = useState("");
  const [network, setNetwork] = useState<NetworkSummaryPayload | null>(null);
  const [periods, setPeriods] = useState<NetworkPeriodPayload | null>(null);
  const [branches, setBranches] = useState<NetworkBranchPayload | null>(null);
  const [expansion, setExpansion] = useState<ExpansionSummaryPayload | null>(null);
  const [events, setEvents] = useState<ExpansionEventPayload | null>(null);
  const [error, setError] = useState("");
  const shown = useRef<{ domain: OptionalResultDomain | null; year: number }>({ domain: null, year: 0 });

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
      // R-10: the linked domain and year when this Run has them (and the domain on screen after a status change).
      setCapabilities(payload);
      const chosen = systemsTab(available, shown.current.domain ?? linked.tab);
      setDomain(chosen); setYear(chosen ? systemsYear(payload.capabilities[chosen].years, (chosen === shown.current.domain ? shown.current.year : 0) || linked.year) : 0);
      setError("");
    }).catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [run, linked.tab, linked.year]);
  useEffect(() => { shown.current = { domain, year }; }, [domain, year]);
  const firstDomain = availableDomains[0] ?? null;
  useEffect(() => { if (domain) onLocationChange?.(systemsQueryValues({ tab: domain, year }, firstDomain)); }, [domain, firstDomain, onLocationChange, year]);

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

  if (!run) return <div className="page"><div className="empty-run"><b>{t("systems.noRun.title")}</b><p>{t("systems.noRun.body")}</p></div></div>;
  const labels: Record<OptionalResultDomain, MessageKey> = { network_dc: "systems.domain.dc", network_expansion: "systems.domain.expansion" };
  const selectedCapability = domain ? capabilities?.capabilities[domain] : null;
  const selectedBusPeriod = periods?.items.find((item) => item.period_id === selectedPeriod);
  return <div className="page evidence-page"><PageHeader title={t("systems.title")} description={t("systems.description")} actions={<Badge tone={run.status === "completed" || run.status === "archived" ? "good" : "warn"} title={run.status}>{statusWord(run.status)}</Badge>} />
    {error && <div className="error-box">{error}</div>}
    {capabilities && <section className="domain-capability-strip" aria-label={t("systems.capability.label")}>{PUBLIC_CAPABILITY_DOMAINS.map((key) => [key, capabilities.capabilities[key]] as const).filter((entry): entry is readonly [string, DomainCapability] => Boolean(entry[1])).map(([key, item]) => <article key={key}><span>{domainLabel(key)}</span><Badge tone={item.status === "supported" ? "good" : item.status === "experimental" ? "warn" : "neutral"} title={item.status}>{statusWord(item.status)}</Badge><small>{item.claim ?? item.reason ?? t("systems.capability.available")}</small></article>)}</section>}
    {capabilities && !availableDomains.length && (["supported", "experimental"].includes(capabilities.capabilities.zonal_redispatch?.status ?? "")
      ? <div className="empty-run"><b>{t("systems.zonal.title")}</b><p>{t("systems.zonal.body")}</p><button type="button" className="secondary" onClick={onOpenNetwork}>{t("systems.zonal.open")}</button></div>
      : <div className="empty-run"><b>{t("systems.none.title")}</b><p>{t(run.modules?.balancing === "value-copperplate-balancing" || !run.modules?.balancing ? "systems.none.copperplate" : "systems.none.modules")} {t("systems.none.body")}</p><button type="button" className="secondary" onClick={onOpenMarket}>{t("systems.none.openReplay")}</button></div>)}
    {/* R-10 (P1-polish): WAI-ARIA tabs (app/ui/Tabs); the domain and year are in the URL (?tab=&year=). */}
    {!!availableDomains.length && <Tabs className="domain-result-tabs" label={t("systems.tabs.label")} tabs={availableDomains.map((item) => ({ id: item, label: t(labels[item]) }))} value={domain ?? availableDomains[0]} onChange={(id) => { const next = id as OptionalResultDomain; setDomain(next); setYear(capabilities?.capabilities[next].years?.[0] ?? 0); }}>
      {selectedCapability?.years?.length ? <label className="inline-select domain-year"><span>{t("systems.year")}</span><select value={year} onChange={(event) => setYear(Number(event.target.value))}>{selectedCapability.years.map((item) => <option key={item}>{item}</option>)}</select></label> : null}
    {domain === "network_dc" && network && <div className="domain-result-stack"><section className="panel"><div className="panel-head"><div><span>{t("systems.dc.kicker", { year: network.year })}</span><h3>{t("systems.dc.title")}</h3></div><Badge tone="good">{t("systems.dc.integrity")}</Badge></div><DomainMetricCards metrics={network.metrics} /><div className="network-result-layout"><TopologySchematic summary={network} /><div><h4>{t("systems.dc.envelope")}</h4><div className="table-scroll compact-table"><table><thead><tr><th>{t("systems.col.branch")}</th><th>{t("systems.col.endpoints")}</th><th>{t("systems.col.rating")}</th><th>{t("systems.col.maxFlow")}</th><th>{t("systems.col.peakUse")}</th></tr></thead><tbody>{network.branch_summary.map((item) => <tr key={item.branch_id}><td>{item.branch_id}</td><td>{item.from_bus} → {item.to_bus}</td><td>{item.rating_mw == null ? t("systems.value.notEvaluated") : `${withUnit(formatNumber(item.rating_mw), "MW")}`}</td><td>{withUnit(formatNumber(item.maximum_absolute_flow_mw), "MW")}</td><td>{item.maximum_utilisation_fraction == null ? t("systems.value.notEvaluated") : `${withUnit(formatNumber(item.maximum_utilisation_fraction * 100, 1), "%", "")}`}</td></tr>)}</tbody></table></div></div></div><button className="audit-link" onClick={onOpenMarket}>{t("systems.dc.openSoc")}</button><p className="provenance-line">{t("systems.dc.provenance", { declared: network.source_artifacts.declared_input_sha256, periodIndex: network.source_artifacts.period_index_sha256 })}</p></section>
      {periods && <section className="panel"><div className="panel-head"><div><span>{t("systems.periods.kicker")}</span><h3>{t("systems.periods.title")}</h3></div><Badge tone="blue">{t("systems.periods.loaded", { shown: periods.items.length, total: periods.total })}</Badge></div><div className="period-chip-list" role="group" aria-label={t("systems.periods.label")}>{periods.items.map((item) => <button type="button" key={item.period_id} className={selectedPeriod === item.period_id ? "selected" : ""} aria-pressed={selectedPeriod === item.period_id} title={item.period_id} onClick={() => setSelectedPeriod(item.period_id)}>{periodIdLabel(item.period_id)}</button>)}</div>{selectedBusPeriod && <><div className="table-scroll"><table><thead><tr><th>{t("systems.col.bus")}</th><th>{t("systems.col.injection")}</th><th>{t("systems.col.withdrawal")}</th><th>{t("systems.col.loadShed")}</th><th>{t("systems.col.angle")}</th><th>{t("systems.col.nodalDual")}</th></tr></thead><tbody>{selectedBusPeriod.buses.map((item) => <tr key={item.bus_id}><td>{item.bus_id}</td><td>{withUnit(formatNumber(item.injection_mwh), "MWh")}</td><td>{withUnit(formatNumber(item.withdrawal_mwh), "MWh")}</td><td>{withUnit(formatNumber(item.blackout_mwh), "MWh")}</td><td>{withUnit(formatNumber(item.angle_rad, 6), "rad")}</td><td>{withUnit(formatNumber(item.price_gbp_per_mwh), "/MWh", "", "£")}</td></tr>)}</tbody></table></div>{branches && <div className="table-scroll"><table><thead><tr><th>{t("systems.col.branch")}</th><th>{t("systems.col.endpoints")}</th><th>{t("systems.col.flow")}</th><th>{t("systems.col.rating")}</th><th>{t("systems.col.utilisation")}</th></tr></thead><tbody>{branches.items.map((item) => <tr key={`${item.period_id}-${item.branch_id}`}><td>{item.branch_id}</td><td>{item.from_bus} → {item.to_bus}</td><td>{withUnit(formatNumber(item.flow_mw), "MW")}</td><td>{item.rating_mw == null ? t("systems.value.notEvaluated") : `${withUnit(formatNumber(item.rating_mw), "MW")}`}</td><td>{item.utilisation_fraction == null ? item.utilisation_status.replaceAll("_", " ") : `${withUnit(formatNumber(item.utilisation_fraction * 100, 1), "%", "")}`}</td></tr>)}</tbody></table></div>}</>}</section>}
    </div>}
    {domain === "network_expansion" && expansion && <div className="domain-result-stack"><section className="panel"><div className="panel-head"><div><span>{t("systems.expansion.kicker")}</span><h3>{expansion.lineage}</h3></div><Badge tone="warn">{expansion.status}</Badge></div><div className="expansion-year-grid">{expansion.years.map((item) => <article key={item.year}><b>{item.year}</b><span>{t("systems.expansion.proposed", { count: item.proposals })}</span><span>{t("systems.expansion.admitted", { count: item.admitted })}</span><span>{t("systems.expansion.commissioned", { count: item.commissioned })}</span><span>{t("systems.expansion.failedRetired", { failed: item.failed, retired: item.retired })}</span></article>)}</div><p className="audit-note">{t("systems.expansion.note", { claim: expansion.counterfactual_claim.replaceAll("_", " ") })}</p></section>{events && <section className="panel"><div className="panel-head"><div><span>{t("systems.events.kicker")}</span><h3>{t("systems.events.title", { count: events.total })}</h3></div><Badge tone="blue">{t("systems.events.first", { count: events.items.length })}</Badge></div><div className="table-scroll"><table><thead><tr><th>{t("systems.col.yearEvent")}</th><th>{t("systems.col.candidate")}</th><th>{t("systems.col.projectAsset")}</th><th>{t("systems.col.corridor")}</th><th>{t("systems.col.build")}</th><th>{t("systems.col.reason")}</th></tr></thead><tbody>{events.items.map((item) => <tr key={item.event_id}><td><b>{item.year}</b><small>{item.event_type}</small></td><td>{item.candidate_id}</td><td><small>{item.project_id ?? t("systems.events.noProject")}</small><small>{item.asset_id ?? t("systems.events.noAsset")}</small></td><td>{item.corridor_id}<small>{item.from_bus} → {item.to_bus}</small></td><td>{item.circuits} × {withUnit(formatNumber(item.rating_mw), "MW")}</td><td>{item.reason_code}</td></tr>)}</tbody></table></div><p className="provenance-line">{t("systems.events.source", { sha: events.source_artifact_sha256 })}</p></section>}</div>}
    </Tabs>}
    {capabilities?.capabilities.hydrology && <section className="panel unavailable-domain"><div><span>{t("systems.hydrology.kicker")}</span><h3>{capabilities.capabilities.hydrology.status.replaceAll("_", " ")}</h3><p>{capabilities.capabilities.hydrology.reason ?? t("systems.hydrology.available")}</p></div><Badge tone={capabilities.capabilities.hydrology.status === "experimental" ? "warn" : "neutral"}>{capabilities.capabilities.hydrology.status.replaceAll("_", " ")}</Badge></section>}
    {capabilities && <p className="provenance-line">{t("systems.identity", { run: String(capabilities.identity.run_id ?? run.id), revision: String(capabilities.identity.project_revision_sha256 ?? t("systems.identity.notRecorded")), graph: String(capabilities.identity.graph_sha256 ?? t("systems.identity.notRecorded")) })}</p>}
  </div>;
}
