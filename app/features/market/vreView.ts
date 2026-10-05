// Pure view logic of the VRE & curtailment page (P0-9 S8; spec 4.1, 4.5; R3-21, G1-08).
import { formatEnergyGroup, formatNumber } from "../shared/format.ts";
import type { DispatchBucket, VreEventStatistics, VreYear } from "./marketTypes.ts";

export type VreKpi = { key: string; label: string; value: string | null; exactMwh: number | null; note?: string };

/** The eight KPIs of one year in one unit (the group's largest magnitude). */
export function vreKpis(year: VreYear): { unit: string; kpis: VreKpi[] } {
  const values = [
    ["available", "Available VRE", year.available_vre_mwh],
    ["accepted", "Accepted VRE", year.accepted_vre_mwh],
    ["unused", "Unused VRE", year.neutral_unused_vre_mwh],
    ["excess", "Pre-balancing excess", year.pre_balancing_excess_mwh],
    ["curtailment", "Balancing curtailment", year.balancing_curtailment_mwh],
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

/** Spec 4.1: the coverage line under each KPI: the year, or "{n} periods · non-annual". */
export function kpiCoverageLine(year: Pick<VreYear, "year" | "period_count" | "full_chronology">): string {
  return year.full_chronology ? String(year.year) : `${formatNumber(year.period_count, 0)} periods · non-annual`;
}

export type VreEventGroup = { key: "unused_vre" | "excess_curtailment"; title: string; basisNote: string; events: VreEventStatistics | null };

/** Spec 4.5 / G1-08: unused VRE and excess + curtailment are two event groups, never merged. */
export function vreEventGroups(year: VreYear): VreEventGroup[] {
  const groups: VreEventGroup[] = [{
    key: "unused_vre", title: "Unused VRE",
    basisNote: "Periods where available renewable energy exceeded accepted renewable dispatch.",
    events: year.unused_vre_events ?? null,
  }];
  if (year.excess_curtailment_events !== undefined) {
    groups.push({
      key: "excess_curtailment", title: "Excess + curtailment",
      basisNote: "Pre-balancing excess (may include nuclear or natural-flow hydro) plus balancing-stage curtailment; not all of it is VRE.",
      events: year.excess_curtailment_events,
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
