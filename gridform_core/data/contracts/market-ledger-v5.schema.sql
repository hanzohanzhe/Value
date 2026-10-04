-- gridform.market-ledger/v5: additive migration from the retained v4 ledger.
CREATE TABLE IF NOT EXISTS zonal_period_summary(
    year INTEGER NOT NULL, period INTEGER NOT NULL, period_id TEXT NOT NULL,
    system_resource_cost_gbp REAL NOT NULL,
    network_constraint_cost_gbp REAL NOT NULL,
    national_settlement_gbp REAL NOT NULL,
    redispatch_settlement_gbp REAL NOT NULL,
    policy_transfer_gbp REAL NOT NULL,
    perfect_forecast_resource_cost_gbp REAL NOT NULL,
    realised_copperplate_resource_cost_gbp REAL NOT NULL,
    zonal_resource_cost_gbp REAL NOT NULL,
    forecast_error_cost_gbp REAL NOT NULL,
    total_deviation_cost_gbp REAL NOT NULL,
    economic_ahead_unused_vre_mwh REAL NOT NULL,
    realised_availability_change_vre_mwh REAL NOT NULL,
    network_added_curtailment_vre_mwh REAL NOT NULL,
    total_curtailment_vre_mwh REAL NOT NULL,
    curtailment_identity_residual_mwh REAL NOT NULL,
    blackout_mwh REAL NOT NULL,
    counterfactual_realised_input_sha256 TEXT NOT NULL,
    accounting_status TEXT NOT NULL,
    PRIMARY KEY(year, period)
);
CREATE TABLE IF NOT EXISTS zonal_demand_alignment(
    year INTEGER NOT NULL, period INTEGER NOT NULL, period_id TEXT NOT NULL,
    demand_mode TEXT NOT NULL,
    research_real_demand_mwh REAL NOT NULL,
    research_forecast_demand_mwh REAL NOT NULL,
    network_national_demand_mwh REAL NOT NULL,
    scale_factor REAL NOT NULL,
    aligned_zonal_total_mwh REAL NOT NULL,
    conservation_residual_mwh REAL NOT NULL,
    PRIMARY KEY(year, period)
);
CREATE TABLE IF NOT EXISTS zone_period_summary(
    year INTEGER NOT NULL, period INTEGER NOT NULL, zone_id TEXT NOT NULL,
    demand_mwh REAL NOT NULL, ahead_injection_mwh REAL NOT NULL,
    final_injection_mwh REAL NOT NULL, signed_adjustment_mwh REAL NOT NULL,
    load_shedding_mwh REAL NOT NULL, net_position_mwh REAL NOT NULL,
    PRIMARY KEY(year, period, zone_id)
);
CREATE TABLE IF NOT EXISTS boundary_period_summary(
    year INTEGER NOT NULL, period INTEGER NOT NULL, boundary_id TEXT NOT NULL,
    transfer_mwh REAL NOT NULL, forward_capacity_mwh REAL NOT NULL,
    reverse_capacity_mwh REAL NOT NULL, utilisation_fraction REAL NOT NULL,
    boundary_shadow_value_gbp_per_mwh REAL NOT NULL,
    shadow_value_semantics TEXT NOT NULL,
    PRIMARY KEY(year, period, boundary_id)
);
CREATE TABLE IF NOT EXISTS zonal_resource_dispatch(
    year INTEGER NOT NULL, period INTEGER NOT NULL, asset_id TEXT NOT NULL,
    agent_id TEXT NOT NULL, zone_id TEXT NOT NULL, technology TEXT NOT NULL,
    ahead_dispatch_mwh REAL NOT NULL, final_dispatch_mwh REAL NOT NULL,
    signed_adjustment_mwh REAL NOT NULL, final_soc_mwh REAL NOT NULL,
    charge_mwh REAL NOT NULL, discharge_mwh REAL NOT NULL,
    physical_resource_cost_gbp REAL NOT NULL,
    PRIMARY KEY(year, period, asset_id)
);
CREATE TABLE IF NOT EXISTS redispatch_settlement(
    bid_id TEXT NOT NULL, year INTEGER NOT NULL, period INTEGER NOT NULL,
    agent_id TEXT NOT NULL, asset_id TEXT NOT NULL, zone_id TEXT NOT NULL,
    technology TEXT NOT NULL, direction TEXT NOT NULL, offered_mwh REAL NOT NULL,
    accepted_delta_mwh REAL NOT NULL, bid_price_gbp_per_mwh REAL NOT NULL,
    cashflow_to_agent_gbp REAL NOT NULL, status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    PRIMARY KEY(year, period, bid_id)
);
CREATE TABLE IF NOT EXISTS reliability_event(
    event_id TEXT PRIMARY KEY, year INTEGER NOT NULL,
    start_period INTEGER NOT NULL, end_period INTEGER NOT NULL,
    observed_half_hours INTEGER NOT NULL, event_duration_hours REAL NOT NULL,
    unserved_mwh REAL NOT NULL, affected_zones_json TEXT NOT NULL,
    maximum_deficit_mwh REAL NOT NULL, metric_semantics TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS solver_declaration_link(
    year INTEGER NOT NULL, period INTEGER NOT NULL,
    declared_input_sha256 TEXT NOT NULL, declaration_artifact_id TEXT NOT NULL,
    solver_artifact_id TEXT, failure_artifact_id TEXT, solver_status TEXT NOT NULL,
    PRIMARY KEY(year, period)
);
CREATE INDEX IF NOT EXISTS zonal_period_year ON zonal_period_summary(year, period);
CREATE INDEX IF NOT EXISTS zonal_demand_alignment_year ON zonal_demand_alignment(year, period);
CREATE INDEX IF NOT EXISTS zone_period_year_zone ON zone_period_summary(year, zone_id, period);
CREATE INDEX IF NOT EXISTS boundary_period_year_boundary ON boundary_period_summary(year, boundary_id, period);
CREATE INDEX IF NOT EXISTS zonal_resource_agent ON zonal_resource_dispatch(agent_id, year, period);
CREATE INDEX IF NOT EXISTS zonal_resource_zone ON zonal_resource_dispatch(zone_id, year, period);
CREATE INDEX IF NOT EXISTS redispatch_agent ON redispatch_settlement(agent_id, year, period);
CREATE INDEX IF NOT EXISTS redispatch_period ON redispatch_settlement(year, period);
CREATE INDEX IF NOT EXISTS reliability_year_period ON reliability_event(year, start_period);
CREATE INDEX IF NOT EXISTS solver_link_period ON solver_declaration_link(year, period);
