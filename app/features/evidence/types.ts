export type PlanningProject = {
  project_id: string; name: string; source: string; technology: string; capacity_mw: number;
  region: string; latitude?: number; longitude?: number; development_stage: string; status: string;
  expected_completion_year?: number; outcome: string; failure_reason_code?: string;
  /** R4 R-低1: the model year of a project-index row (one row per project and year). */
  year?: number | null;
};
export type PlanningEvent = {
  sequence: number; project_id: string; year: number; event_type: string; reason_code?: string;
  from_stage?: string; to_stage?: string; capacity_mw?: number; region?: string;
};
export type MarketPeriod = {
  year: number; period: number; stage: string; real_demand_mwh: number; accepted_supply_mwh: number;
  storage_charge_mwh: number; storage_discharge_mwh: number; curtailed_mwh: number; import_mwh: number;
  clearing_price_gbp_per_mwh: number; blackout_mwh: number; energy_balance_residual_mwh: number;
  raw_energy_balance_residual_mwh?: number; compatibility_adjustment_mwh?: number;
};
export type MarketOrder = {
  order_id: string; asset_id: string; asset_type: string; side: string; offer_price_gbp_per_mwh: number;
  offered_mwh: number; accepted_mwh: number; status: string; reason_code: string;
};
export type Artifact = { id: string; name: string; bytes: number; media_type: string; download_url: string };
