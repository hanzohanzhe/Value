-- value.market-ledger/v7 optional table (four-role finding M-D1; decision Q12,
-- accounting zone): every storage discharge offer of the default PSM, accepted
-- or not, at its real offer price.  Written at the full trace level, next to
-- `orders`; created on first write.
--
-- The kernel offers each stored charge tranche of a battery (the battery's
-- rated power is shared across its tranches) in the ahead stage and, in
-- balancing periods, in the balancing stage (minimum dwell 2 periods).
--   offer_price_gbp_per_mwh = storage cost module bid price for dwell_periods
--                             x bidding_factor (the bid multiplier)
--   clearing_offer_id       = offer_id of the same offer in clearing_inputs
--   accepted_mwh            = energy the offer delivered (grid side)
--   accepted_offer_value_gbp = offer_price_gbp_per_mwh x accepted_mwh, the
--                             storage fee the kernel books for the offer
-- status / reason_code: accepted / cleared; partially_accepted / demand_filled;
-- rejected / no_energy_delivered (reached, nothing delivered) or
-- rejected / merit_order_not_reached (the stage was filled before the offer).
-- The battery's `orders` row (stage final_dispatch, offer price 0.0, reason
-- accepted_non_generator_offer) is the frozen net-dispatch record and is not
-- an offer; read the offers here.  In the doctoral profile the accepted MWh
-- of a battery and period sum to that row; in the corrected profile the row
-- is net of same-period buy-back.  Observation only: dispatch is unchanged.
CREATE TABLE IF NOT EXISTS storage_orders(
    order_id TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    period INTEGER NOT NULL,
    stage TEXT NOT NULL CHECK(stage IN ('ahead_offer', 'balancing_offer')),
    clearing_offer_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    side TEXT NOT NULL,
    charge_period INTEGER NOT NULL,
    dwell_periods INTEGER NOT NULL,
    bidding_factor REAL NOT NULL,
    offer_price_gbp_per_mwh REAL NOT NULL,
    offered_mwh REAL NOT NULL,
    accepted_mwh REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('accepted', 'partially_accepted', 'rejected')),
    reason_code TEXT NOT NULL,
    accepted_offer_value_gbp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS storage_orders_period ON storage_orders(year, period, stage);
CREATE INDEX IF NOT EXISTS storage_orders_asset ON storage_orders(asset_id, year, period);
