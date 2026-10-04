-- gridform.market-ledger/v6: separate cost/reliability from VRE attribution.
CREATE TABLE IF NOT EXISTS zonal_period_accounting(
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
    blackout_mwh REAL NOT NULL,
    counterfactual_realised_input_sha256 TEXT NOT NULL,
    accounting_status TEXT NOT NULL,
    PRIMARY KEY(year, period)
);

CREATE TABLE IF NOT EXISTS vre_curtailment_period(
    year INTEGER NOT NULL, period INTEGER NOT NULL, period_id TEXT NOT NULL,
    realised_available_vre_mwh REAL NOT NULL,
    perfect_reference_dispatch_mwh REAL NOT NULL,
    copperplate_reference_dispatch_mwh REAL NOT NULL,
    zonal_final_dispatch_mwh REAL NOT NULL,
    economic_curtailment_mwh REAL NOT NULL,
    forecast_added_curtailment_mwh REAL NOT NULL,
    forecast_avoided_curtailment_mwh REAL NOT NULL,
    redispatch_added_curtailment_mwh REAL NOT NULL,
    redispatch_avoided_curtailment_mwh REAL NOT NULL,
    redispatch_net_impact_mwh REAL NOT NULL,
    total_curtailment_mwh REAL NOT NULL,
    curtailment_rate REAL NOT NULL,
    identity_residual_mwh REAL NOT NULL,
    validation_tolerance_mwh REAL NOT NULL,
    accounting_status TEXT NOT NULL,
    counterfactual_realised_input_sha256 TEXT NOT NULL,
    attribution_method_id TEXT NOT NULL,
    PRIMARY KEY(year, period)
);

CREATE TABLE IF NOT EXISTS vre_curtailment_detail(
    year INTEGER NOT NULL, period INTEGER NOT NULL, period_id TEXT NOT NULL,
    asset_id TEXT NOT NULL, owner_id TEXT NOT NULL, zone_id TEXT NOT NULL,
    technology TEXT NOT NULL, bid_tranche_id TEXT NOT NULL,
    realised_available_vre_mwh REAL NOT NULL,
    perfect_reference_dispatch_mwh REAL NOT NULL,
    copperplate_reference_dispatch_mwh REAL NOT NULL,
    zonal_final_dispatch_mwh REAL NOT NULL,
    economic_curtailment_mwh REAL NOT NULL,
    forecast_added_curtailment_mwh REAL NOT NULL,
    forecast_avoided_curtailment_mwh REAL NOT NULL,
    redispatch_added_curtailment_mwh REAL NOT NULL,
    redispatch_avoided_curtailment_mwh REAL NOT NULL,
    redispatch_net_impact_mwh REAL NOT NULL,
    total_curtailment_mwh REAL NOT NULL,
    evidence_level TEXT NOT NULL,
    PRIMARY KEY(year, period, asset_id, bid_tranche_id)
);

CREATE INDEX IF NOT EXISTS zonal_period_accounting_year_period
    ON zonal_period_accounting(year, period);
CREATE INDEX IF NOT EXISTS vre_curtailment_period_year_period
    ON vre_curtailment_period(year, period);
CREATE INDEX IF NOT EXISTS vre_curtailment_detail_period
    ON vre_curtailment_detail(year, period);
CREATE INDEX IF NOT EXISTS vre_curtailment_detail_zone_technology_year
    ON vre_curtailment_detail(zone_id, technology, year);
CREATE INDEX IF NOT EXISTS vre_curtailment_detail_asset_year_period
    ON vre_curtailment_detail(asset_id, year, period);
