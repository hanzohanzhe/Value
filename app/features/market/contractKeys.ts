// Contract guard (P0-9 S2): the required keys of each market type, listed once.
// tsc proves each list is exhaustive (every required key of the type is listed,
// nothing else); tests/frontend/unit/ui-contract-keys.test.mjs proves that the
// generated fixtures (the real read models) send every listed key.
import type { DispatchBucket, DispatchTimeline, MarketCapability, VreYear } from "./marketTypes.ts";

type RequiredKeys<T> = { [K in keyof T]-?: object extends Pick<T, K> ? never : K }[keyof T];
type Exhaustive<T, List extends readonly unknown[]> =
  [Exclude<RequiredKeys<T>, List[number]>] extends [never]
    ? [Exclude<List[number], RequiredKeys<T>>] extends [never] ? true : "lists a key that is not a required key"
    : "misses a required key";

export const DISPATCH_BUCKET_KEYS = [
  "period_start", "period_end", "period_count", "timestamp_start", "timestamp_end", "real_demand_mwh",
  "accepted_supply_mwh", "price_gbp_per_mwh", "storage_charge_mwh", "storage_discharge_mwh", "curtailed_mwh",
  "excess_mwh", "vre_available_mwh", "vre_accepted_mwh", "blackout_mwh", "compatibility_adjustment_mwh", "flows",
] as const;
export const DISPATCH_TIMELINE_KEYS = ["year", "resolution", "total", "limit", "offset", "items"] as const;
export const MARKET_CAPABILITY_KEYS = [
  "years", "trace_level", "period_summary", "physical_dispatch", "auction_replay", "storage_state", "auction_stages",
] as const;
export const VRE_YEAR_KEYS = [
  "year", "period_count", "full_chronology", "available_vre_mwh", "accepted_vre_mwh", "neutral_unused_vre_mwh",
  "pre_balancing_excess_mwh", "pre_balancing_excess_scope", "balancing_curtailment_mwh", "vre_utilisation_fraction",
  "average_unused_vre_fraction", "affected_periods", "longest_event_hours", "peak_event_mwh", "peak_event_timestamp",
  "storage_charge_mwh", "export_mwh", "flexible_demand_mwh", "vre_identity_residual_mwh", "coverage_status",
  "marginal_curtailment_status", "marginal_curtailment_reason",
] as const;

export const CONTRACT_KEYS_EXHAUSTIVE: [
  Exhaustive<DispatchBucket, typeof DISPATCH_BUCKET_KEYS>,
  Exhaustive<DispatchTimeline, typeof DISPATCH_TIMELINE_KEYS>,
  Exhaustive<MarketCapability, typeof MARKET_CAPABILITY_KEYS>,
  Exhaustive<VreYear, typeof VRE_YEAR_KEYS>,
] = [true, true, true, true];
