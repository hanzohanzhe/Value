// Pure view logic of Market replay (P0-9 S3/S4; spec 3). No React here, so
// node --test checks it against the generated UI contract fixtures.
import { formatPrice, type FormattedPrice } from "../shared/format.ts";
import type { DispatchBucket, DispatchFlow, DispatchTimeline, MarketCapability } from "./marketTypes.ts";
import { techSeries, type SeriesStyle } from "../../ui/chartPalette.ts";
import { localizedTable, tr } from "../../i18n/index.ts";

/** Price of one bucket, labelled by the ledger's price basis (Q6). A multi-period bucket is a demand-weighted mean. */
export function bucketPrice(bucket: Pick<DispatchBucket, "price_gbp_per_mwh" | "period_count">, timeline: Pick<DispatchTimeline, "price_basis">): FormattedPrice {
  return formatPrice(bucket.price_gbp_per_mwh, timeline.price_basis, { aggregated: bucket.period_count > 1 });
}

/**
 * R5 R-低10: what "Accepted supply" covers. The corrected PSM records supply at
 * the full node; the doctoral PSM at its source-classified node, where storage
 * charged from pre-balancing surplus is outside accepted supply. The two
 * figures are therefore not the same quantity across methodologies.
 */
export function acceptedSupplyNote(timeline: Pick<DispatchTimeline, "accepted_supply_boundary">): string {
  const id = timeline.accepted_supply_boundary?.boundary_id ?? "";
  if (id === "native_corrected_full_node_v1" || id === "full_node_v1") return tr("dispatch.boundary.full");
  if (id === "default_psm_surplus_node_v1") return tr("dispatch.boundary.sourceClassified");
  return tr("dispatch.boundary.notRecorded");
}

// ---------------------------------------------------------------- dispatch stack (S4)

/** Fallback for a backend without flow roles (dispatch timeline v1): the v4-v7
 * physical-dispatch supply types, and v8 summary rows of the final dispatch stage. */
export const LEGACY_SUPPLY_FLOW_TYPES: ReadonlySet<string> = new Set(["generation", "import", "storage_discharge"]);

export function isSupplyFlow(flow: DispatchFlow): boolean {
  if (flow.role) return flow.role === "supply";
  if (flow.flow_type === "accepted_dispatch") return /;stage:final_dispatch$/.test(flow.evidence_scope) && flow.energy_mwh > 0;
  return LEGACY_SUPPLY_FLOW_TYPES.has(flow.flow_type);
}

export type StackSegment = { technology: string; energy_mwh: number };

/** Supply of one bucket by technology (zones summed), in a stable order. */
export function stackSupply(bucket: Pick<DispatchBucket, "flows">): StackSegment[] {
  const totals = new Map<string, number>();
  for (const flow of bucket.flows) {
    if (!isSupplyFlow(flow)) continue;
    totals.set(flow.technology, (totals.get(flow.technology) ?? 0) + flow.energy_mwh);
  }
  return [...totals.entries()].map(([technology, energy_mwh]) => ({ technology, energy_mwh }));
}

export function stackedTechnologies(items: readonly Pick<DispatchBucket, "flows">[]): string[] {
  return [...new Set(items.flatMap((item) => stackSupply(item).map((segment) => segment.technology)))];
}

/** Buckets with recorded stress periods (A2). Absent fields mean "not recorded", never "no stress". */
export function stressBuckets(items: readonly DispatchBucket[]): number[] {
  return items.flatMap((item, index) => typeof item.stress_periods === "number" && item.stress_periods > 0 ? [index] : []);
}

export type EmptyDispatchReason = "no_buckets_in_window" | "dispatch_detail_not_recorded" | "supply_flows_not_recorded";

/** Why the chart has nothing to stack, or null when it has supply to draw. */
export function emptyDispatchReason(timeline: Pick<DispatchTimeline, "items">, capabilities?: Pick<MarketCapability, "physical_dispatch" | "dispatch_summary_available"> | null): EmptyDispatchReason | null {
  if (!timeline.items.length) return "no_buckets_in_window";
  if (capabilities && !capabilities.physical_dispatch && !capabilities.dispatch_summary_available) return "dispatch_detail_not_recorded";
  return timeline.items.some((item) => stackSupply(item).length > 0) ? null : "supply_flows_not_recorded";
}

// P1 W5: dictionary messages (dispatch.empty.*) in the interface language.
export const EMPTY_DISPATCH_MESSAGES: Readonly<Record<EmptyDispatchReason, string>> = localizedTable<EmptyDispatchReason>({
  no_buckets_in_window: "dispatch.empty.no_buckets_in_window",
  dispatch_detail_not_recorded: "dispatch.empty.dispatch_detail_not_recorded",
  supply_flows_not_recorded: "dispatch.empty.supply_flows_not_recorded",
});

// ---------------------------------------------------------------- chart series (W4c, spec 1.2 / 2.1)

/** Replay technologies that share a palette colour with another series get their own pattern. */
const REPLAY_SERIES: Readonly<Record<string, SeriesStyle>> = {
  reservoir_hydro: { color: "var(--tech-hydro)", pattern: "dots" },
  hydrogen_storage: { color: "var(--tech-storage)", pattern: "hatch" },
  unmapped: { color: "var(--ink-muted)", pattern: "solid" },
};

/** The colour and pattern of a technology in the replay charts (the --tech-* palette; never a raw hex). */
export function replaySeriesStyle(technology: string): SeriesStyle {
  return REPLAY_SERIES[technology] ?? techSeries(technology) ?? { color: "var(--ink-muted)", pattern: "dots" };
}

/** A technology id as the charts and tables name it ("offshore_wind" → "offshore wind"). */
export function technologyLabel(technology: string): string {
  return technology.replaceAll("_", " ");
}

/** Spec 2.1 / R3-10: the default timeline resolution of a window (24 hours at half-hour detail, never one daily bar). */
export function defaultResolution(windowKind: "24_hours" | "168_hours"): "half_hour" | "daily" {
  return windowKind === "24_hours" ? "half_hour" : "daily";
}

/** Indices of at most `count` evenly spaced axis labels over `length` buckets (first and last included). */
export function axisLabelIndices(length: number, count: number): number[] {
  if (length <= 0) return [];
  const slots = Math.max(1, Math.min(length, Math.floor(count)));
  if (slots === 1) return [0];
  const step = (length - 1) / (slots - 1);
  return [...new Set(Array.from({ length: slots }, (_, index) => Math.round(index * step)))];
}
