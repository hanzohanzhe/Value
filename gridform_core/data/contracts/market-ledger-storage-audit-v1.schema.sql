-- value.market-ledger/v7 optional tables (P0-4 S4; P3-14, P5-11): per-asset
-- storage energy audit of the default PSM.  Created on first write.
CREATE TABLE IF NOT EXISTS storage_energy_audit(
    year INTEGER NOT NULL,
    period INTEGER NOT NULL,
    asset_id TEXT NOT NULL,
    soc_start_mwh REAL NOT NULL,
    charge_input_mwh REAL NOT NULL,
    charge_stored_mwh REAL NOT NULL,
    discharge_output_mwh REAL NOT NULL,
    discharge_withdrawn_mwh REAL NOT NULL,
    self_discharge_mwh REAL NOT NULL,
    tail_writeoff_mwh REAL NOT NULL,
    soc_end_mwh REAL NOT NULL,
    identity_residual_mwh REAL NOT NULL,
    PRIMARY KEY(year, period, asset_id)
);
CREATE TABLE IF NOT EXISTS storage_year_boundary(
    year INTEGER NOT NULL,
    asset_id TEXT NOT NULL,
    opening_soc_mwh REAL NOT NULL,
    closing_soc_mwh REAL NOT NULL,
    carried_forward_mwh REAL NOT NULL,
    discarded_mwh REAL NOT NULL,
    carry_policy TEXT NOT NULL,
    PRIMARY KEY(year, asset_id)
);
