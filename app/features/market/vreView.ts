// Pure view logic of the VRE & curtailment page (P0-9 S8; spec 4.1, 4.5; R3-21, G1-08).
import { formatEnergyGroup, formatNumber, withUnit } from "../shared/format.ts";
import { yearCoveragePill, type ResultCoverage } from "../shared/coverageView.ts";
import { valueStateText } from "../shared/valueStates.ts";
import type { PillTone } from "../shared/Callout.tsx";
import type { DispatchBucket, VreEventStatistics, VreYear } from "./marketTypes.ts";

export type VreKpi = { key: string; label: string; value: string | null; exactMwh: number | null; note?: string };

/** C20: the column semantics the ledger declares (vre-summary top level). */
export type VreSemantics = { excess_scope?: string; curtailment_semantics?: string };

/** The corrected rule set's declared curtailed column (gridform_core/market_replay.CORRECTED_CURTAILMENT_SEMANTICS). */
export const CORRECTED_CURTAILMENT_SEMANTICS = "vre_available_minus_gross_output";

export type VreLabels = { accepted: string; excess: string; curtailment: string; excessDefinition: string; curtailmentDefinition: string };

/**
 * C20 (P0-6 column semantics; P0-9 M7): under the corrected rule set the
 * excess column is the non-VRE spill and the curtailed column is VRE
 * availability minus gross VRE output; the labels say so instead of reusing
 * the doctoral "pre-balancing excess" and "balancing curtailment" words.
 */
export function vreLabels(semantics?: VreSemantics | null): VreLabels {
  const corrected = semantics?.curtailment_semantics === CORRECTED_CURTAILMENT_SEMANTICS;
  const spill = semantics?.excess_scope === "non_vre_spill";
  return {
    accepted: corrected ? "Accepted VRE (gross output)" : "Accepted VRE",
    excess: spill ? "Non-VRE spill" : "Pre-balancing excess",
    curtailment: corrected ? "VRE curtailment" : "Balancing curtailment",
    excessDefinition: spill
      ? "Surplus from non-VRE generation (for example nuclear or natural-flow hydro) that was finally spilled. It is not renewable energy."
      : "The retained VALUE ahead-stage surplus. It is not assumed to be entirely renewable.",
    curtailmentDefinition: corrected
      ? "Available VRE minus gross VRE output, where surplus absorbed by storage, export or flexible demand counts as output."
      : "Energy removed in the real-time balancing waterfall after forecast error, storage, export and flexible demand are considered.",
  };
}

/** The eight KPIs of one year in one unit (the group's largest magnitude). */
export function vreKpis(year: VreYear, semantics?: VreSemantics | null): { unit: string; kpis: VreKpi[] } {
  const labels = vreLabels(semantics);
  const values = [
    ["available", "Available VRE", year.available_vre_mwh],
    ["accepted", labels.accepted, year.accepted_vre_mwh],
    ["unused", "Unused VRE", year.neutral_unused_vre_mwh],
    ["excess", labels.excess, year.pre_balancing_excess_mwh],
    ["curtailment", labels.curtailment, year.balancing_curtailment_mwh],
    ["storage", "Simultaneous storage charging", year.storage_charge_mwh],
    ["export", "Boundary exports", year.export_mwh],
    ["flexible", "Flexible demand", year.flexible_demand_mwh],
  ] as const;
  const group = formatEnergyGroup(values.map(([, , value]) => value));
  return {
    unit: group.unit,
    kpis: values.map(([key, label, value]) => ({ key, label, value: group.format(value), exactMwh: value ?? null })),
  };
}

type CoverageYear = Pick<VreYear, "year" | "period_count" | "full_chronology">;

export type VreYearCoverage = {
  /** Spec 4.1: the line under each KPI. */
  line: string;
  /** The page badge and its tone. */
  badge: string;
  tone: "good" | "warn" | "blue" | "neutral";
  /** The heading of the year panel. */
  heading: string;
};

const BADGE_TONE: Record<PillTone, VreYearCoverage["tone"]> = { ok: "good", caution: "warn", danger: "warn", info: "blue", muted: "neutral" };

/**
 * Coverage of one VRE year (spec 4.1, 4.2). With the backend's coverage verdict
 * (vre-summary `coverage`), a partial year of an annual Run is "Partial year · n%",
 * and "non-annual" is said only of a non-annual Run; without it (older backend)
 * the label falls back to the year's own full_chronology flag.
 */
export function vreYearCoverage(year: CoverageYear, coverage?: ResultCoverage | null): VreYearCoverage {
  const periods = withUnit(formatNumber(year.period_count, 0), "periods");
  const nonAnnual: VreYearCoverage = { line: `${periods} · non-annual`, badge: valueStateText("non_annual"), tone: "warn", heading: `${year.period_count}-period diagnostic — not an annual result` };
  if (!coverage) {
    return year.full_chronology
      ? { line: String(year.year), badge: "Full chronology", tone: "good", heading: "Annual accounting" }
      : { ...nonAnnual, badge: "Diagnostic chronology" };
  }
  if (coverage.annual_status === "non_annual") return nonAnnual;
  const pill = yearCoveragePill(coverage, year.year);
  if (pill.tone === "ok") return { line: String(year.year), badge: pill.text, tone: "good", heading: "Annual accounting" };
  return { line: `${year.year} · ${pill.text}`, badge: pill.text, tone: BADGE_TONE[pill.tone], heading: `${pill.text} — not an annual result` };
}

/** Spec 4.1: the coverage line under each KPI: the year, "{year} · Partial year · n%", or "{n} periods · non-annual". */
export function kpiCoverageLine(year: CoverageYear, coverage?: ResultCoverage | null): string {
  return vreYearCoverage(year, coverage).line;
}

export type VreEventGroup = {
  key: "unused_vre" | "excess_curtailment"; title: string; basisNote: string; events: VreEventStatistics | null;
  /** Designer ruling 5: a group with no affected period says "No events recorded", never "Peak event 0 MWh". */
  noEvents: boolean;
};

function hasNoEvents(events: VreEventStatistics | null | undefined): boolean {
  return Boolean(events) && events!.affected_periods === 0;
}

/** Spec 4.5 / G1-08: unused VRE and excess + curtailment are two event groups, never merged. */
export function vreEventGroups(year: VreYear): VreEventGroup[] {
  const corrected = year.event_basis === "corrected_unused_vre" || year.unused_vre_events?.basis === "corrected_unused_vre";
  const groups: VreEventGroup[] = [{
    key: "unused_vre", title: "Unused VRE",
    basisNote: corrected
      // C20: the third event basis (corrected rule set); excess + curtailment is not a VRE basis there.
      ? "Periods where available renewable energy exceeded gross renewable output (corrected rule set: surplus absorbed by storage, export or flexible demand counts as output). Non-VRE spill is not included."
      : "Periods where available renewable energy exceeded accepted renewable dispatch.",
    events: year.unused_vre_events ?? null,
    noEvents: hasNoEvents(year.unused_vre_events),
  }];
  if (year.excess_curtailment_events !== undefined && !corrected) {
    groups.push({
      key: "excess_curtailment", title: "Excess + curtailment",
      basisNote: "Pre-balancing excess (may include nuclear or natural-flow hydro) plus balancing-stage curtailment; not all of it is VRE.",
      events: year.excess_curtailment_events,
      noEvents: hasNoEvents(year.excess_curtailment_events),
    });
  }
  return groups;
}

type SeriesKey = "vre_available_mwh" | "vre_accepted_mwh" | "excess_mwh" | "neutral_unused_vre_mwh";

/** Polyline point lists of one series; a missing value ends a segment instead of dropping to 0. */
export function seriesSegments(items: readonly Partial<DispatchBucket>[], key: SeriesKey, x: (index: number) => number, y: (value: number) => number): string[] {
  const segments: string[][] = [];
  let current: string[] = [];
  items.forEach((item, index) => {
    const value = item[key];
    if (typeof value === "number" && Number.isFinite(value)) current.push(`${x(index)},${y(value)}`);
    else if (current.length) { segments.push(current); current = []; }
  });
  if (current.length) segments.push(current);
  return segments.map((points) => points.join(" "));
}

export type SeriesShapes = {
  /** Point lists of segments with two or more recorded values. */
  lines: string[];
  /** Designer ruling 4: an isolated value (missing on both sides, or a one-bucket view) is drawn as a dot, never as a zero-length line. */
  dots: { x: number; y: number }[];
};

/** seriesSegments split into polylines and isolated dots. */
export function seriesShapes(items: readonly Partial<DispatchBucket>[], key: SeriesKey, x: (index: number) => number, y: (value: number) => number): SeriesShapes {
  const lines: string[] = [];
  const dots: { x: number; y: number }[] = [];
  let current: { x: number; y: number }[] = [];
  const flush = () => {
    if (current.length === 1) dots.push(current[0]);
    else if (current.length > 1) lines.push(current.map((point) => `${point.x},${point.y}`).join(" "));
    current = [];
  };
  items.forEach((item, index) => {
    const value = item[key];
    if (typeof value === "number" && Number.isFinite(value)) current.push({ x: x(index), y: y(value) });
    else flush();
  });
  flush();
  return { lines, dots };
}
