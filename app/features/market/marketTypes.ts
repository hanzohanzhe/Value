// Types of the market read models as the API sends them (gridform_core/market_replay.py).
// tests/frontend/unit/ui-contract-keys.test.mjs checks them against the generated
// contract fixtures in tests/fixtures/ui-contract (P0-9 S2).
import type { PriceBasis } from "../shared/format.ts";
import type { ResultCoverage } from "../shared/coverageView.ts";

export type PriceBasisSource = "declared" | "semantics" | "inferred_from_writer" | "not_declared";

export type MarketCapability = {
  years: number[]; trace_level: string; period_summary: boolean; physical_dispatch: boolean;
  dispatch_summary_available?: boolean;
  auction_replay: boolean; storage_state: boolean; storage_cost_module_id?: string; missing_reason?: string | null; source_artifact_sha256?: string | null;
  bid_replay_available?: boolean; bid_replay_missing_reason?: string | null; missing_detail?: string[];
  auction_stages: { stage: string; declared_periods: number; outcome_periods: number; order_detail: string }[];
  semantic_metadata?: Record<string, unknown>;
  ledger_schema_version?: string;
  price_basis?: PriceBasis; price_basis_source?: PriceBasisSource;
};

/** Role of a dispatch flow in the energy balance (dispatch timeline v2). Only `supply` is stacked. */
export type FlowRole = "supply" | "demand" | "storage_charge" | "curtailment" | "excess" | "unserved" | "context";

export type DispatchFlow = {
  technology: string; flow_type: string; evidence_scope: string; energy_mwh: number; balance_component_mwh: number;
  role?: FlowRole; raw_technology?: string; stage?: string; zone_id?: string;
};

export type DispatchBucket = {
  period_start: number; period_end: number; period_count: number; timestamp_start: string; timestamp_end: string;
  real_demand_mwh: number; accepted_supply_mwh: number;
  /** Demand-weighted mean of the recorded period price; its meaning is the timeline's `price_basis`. */
  price_gbp_per_mwh: number | null;
  storage_charge_mwh: number; storage_discharge_mwh: number; curtailed_mwh: number; excess_mwh: number;
  vre_available_mwh: number; vre_accepted_mwh: number; neutral_unused_vre_mwh?: number;
  blackout_mwh: number; compatibility_adjustment_mwh: number; flows: DispatchFlow[];
  /** A2 stress events (recorded by the backend; absent before the M4 backend). */
  shortfall_mwh?: number | null; stress_periods?: number | null;
  /** exact, or lower_bound for a Run that predates exact stress accounting (F-P04-1). */
  shortfall_basis?: string | null; shortfall_upper_mwh?: number | null; possible_stress_periods?: number | null;
};

export type DispatchTimeline = {
  schema_version?: string;
  year: number; resolution: string; total: number; limit: number; offset: number; source_artifact_sha256?: string | null;
  period_hours?: number; timezone?: string; calendar?: string; clock_label_corrected?: boolean; clock_note?: string; price_aggregation?: string; dispatch_source?: string; dispatch_summary_available?: boolean;
  price_basis?: PriceBasis; price_basis_source?: PriceBasisSource;
  /** R5 R-低10: the energy-balance boundary accepted_supply_mwh is recorded at. */
  accepted_supply_boundary?: { boundary_id?: string | null; formula?: string | null; description?: string | null } | null;
  items: DispatchBucket[];
};

export type AuctionOffer = {
  offer_id?: string; asset_id: string; asset_type?: string; resource_kind?: string; technology: string;
  offer_price_gbp_per_mwh: number; offered_mwh: number; accepted_mwh: number | null;
  asset_accepted_mwh: number | null; acceptance_granularity: string; execution_order: number;
  cumulative_offered_mwh: number;
  /** M-D1: storage offer ledger status / reason of a storage offer; null otherwise. */
  offer_status?: string | null; offer_reason_code?: string | null;
};

export type AuctionView = {
  year: number; period: number; stage: string; information_scope: string; requirement_mwh: number;
  offers: AuctionOffer[]; marginal_offer_price_gbp_per_mwh: number | null; marginal_offer_status: string;
  offer_acceptance_coverage: string; pricing_rule: string; input_sha256: string; source_artifact_sha256?: string | null;
};

export type StoragePeriodRow = { asset_id: string; state_of_charge_mwh: number; charge_mwh: number; discharge_mwh: number; power_capacity_mw: number; energy_capacity_mwh: number };

export type VreYear = {
  year: number; period_count: number; full_chronology: boolean; available_vre_mwh: number; accepted_vre_mwh: number;
  neutral_unused_vre_mwh: number; pre_balancing_excess_mwh: number | null; pre_balancing_excess_scope: string;
  balancing_curtailment_mwh: number | null; vre_utilisation_fraction: number | null; average_unused_vre_fraction: number | null;
  affected_periods: number; longest_event_hours: number; peak_event_mwh: number | null; peak_event_timestamp: string | null;
  storage_charge_mwh: number; export_mwh: number; flexible_demand_mwh: number; vre_identity_residual_mwh: number;
  coverage_status: string; marginal_curtailment_status: string; marginal_curtailment_reason: string;
  first_period?: number | null; last_period?: number | null;
  /** G1-08: the basis of the legacy event fields above. */
  event_basis?: "unused_vre" | "excess_plus_balancing_curtailment" | "corrected_unused_vre";
  unused_vre_events?: VreEventStatistics;
  /** null when the ledger does not separate pre-balancing excess (alias semantics). */
  excess_curtailment_events?: VreEventStatistics | null;
};

export type VreEventStatistics = {
  basis: string; affected_periods: number; longest_event_periods: number; longest_event_hours: number;
  peak_event_mwh: number | null; peak_event_period: number | null; peak_event_timestamp: string | null;
};

export type VreSummary = {
  years: VreYear[]; excess_relationship: string; excess_scope: string; source_artifact_sha256?: string | null; coverage?: ResultCoverage | null;
  /** C20: the declared meaning of the ledger's curtailed column (absent from older backends). */
  curtailment_semantics?: string;
};
