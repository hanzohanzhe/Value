// Pure view logic of Market replay (P0-9 S3/S4; spec 3). No React here, so
// node --test checks it against the generated UI contract fixtures.
import { formatPrice, type FormattedPrice } from "../shared/format.ts";
import type { DispatchBucket, DispatchFlow, DispatchTimeline, MarketCapability } from "./marketTypes.ts";

/** Price of one bucket, labelled by the ledger's price basis (Q6). A multi-period bucket is a demand-weighted mean. */
export function bucketPrice(bucket: Pick<DispatchBucket, "price_gbp_per_mwh" | "period_count">, timeline: Pick<DispatchTimeline, "price_basis">): FormattedPrice {
  return formatPrice(bucket.price_gbp_per_mwh, timeline.price_basis, { aggregated: bucket.period_count > 1 });
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

export const EMPTY_DISPATCH_MESSAGES: Record<EmptyDispatchReason, string> = {
  no_buckets_in_window: "The ledger has no periods in this window.",
  dispatch_detail_not_recorded: "This Run recorded period summaries but no technology-level dispatch (physical dispatch or a dispatch summary).",
  supply_flows_not_recorded: "The periods in this window carry no supply flows; VALUE does not reconstruct them from staged orders.",
};
