-- value.market-ledger/v7 optional tables (P0-4 S6; decisions Q7, A2): the
-- energy-balance account of the default PSM on the boundary its market rule
-- set declares (metadata energy_balance_boundary).  Created on first write.
-- shortfall_mwh (demand and boundary loads the accepted supply did not meet)
-- is booked as unserved energy in place of the recorded blackout:
-- closing_residual = raw_residual - recorded_unserved + shortfall.
CREATE TABLE IF NOT EXISTS balance_boundary_period(
    year INTEGER NOT NULL,
    period INTEGER NOT NULL,
    stage TEXT NOT NULL,
    boundary_id TEXT NOT NULL,
    supply_mwh REAL NOT NULL,
    demand_mwh REAL NOT NULL,
    storage_charge_mwh REAL NOT NULL,
    export_mwh REAL NOT NULL,
    flexible_demand_mwh REAL NOT NULL,
    u_out_mwh REAL NOT NULL,
    non_vre_spill_mwh REAL NOT NULL,
    non_vre_double_counted_mwh REAL NOT NULL,
    in_dispatch_unrealised_mwh REAL NOT NULL,
    recorded_unserved_mwh REAL NOT NULL,
    raw_residual_mwh REAL NOT NULL,
    compatibility_adjustment_mwh REAL NOT NULL,
    shortfall_mwh REAL NOT NULL,
    hidden_unserved_mwh REAL NOT NULL,
    closing_residual_mwh REAL NOT NULL,
    stress_flag INTEGER NOT NULL CHECK(stress_flag IN (0, 1)),
    PRIMARY KEY(year, period, stage)
);
-- A2 stress events: contiguous stress periods of one year.
CREATE TABLE IF NOT EXISTS stress_event(
    year INTEGER NOT NULL,
    event_index INTEGER NOT NULL,
    first_period INTEGER NOT NULL,
    last_period INTEGER NOT NULL,
    periods INTEGER NOT NULL,
    shortfall_mwh REAL NOT NULL,
    recorded_unserved_mwh REAL NOT NULL,
    hidden_unserved_mwh REAL NOT NULL,
    boundary_id TEXT NOT NULL,
    PRIMARY KEY(year, event_index)
);
