-- value.market-ledger/v7 optional table (P0-4 S5; decision Q7): pre-balancing
-- surplus routing of the default PSM by source class.  Created on first write.
-- available = to_storage + to_export + to_flexible + to_dispatch + curtailed
--             + spilled + unrealised.  The in_dispatch spilled_mwh is W_in
-- (non_vre_spill); out_of_dispatch storage/export/flexible is U_out.
CREATE TABLE IF NOT EXISTS surplus_routing(
    year INTEGER NOT NULL,
    period INTEGER NOT NULL,
    source_class TEXT NOT NULL CHECK(source_class IN ('in_dispatch', 'out_of_dispatch')),
    available_mwh REAL NOT NULL,
    to_storage_mwh REAL NOT NULL,
    to_export_mwh REAL NOT NULL,
    to_flexible_mwh REAL NOT NULL,
    spilled_mwh REAL NOT NULL,
    to_dispatch_mwh REAL NOT NULL,
    curtailed_mwh REAL NOT NULL,
    unrealised_mwh REAL NOT NULL,
    PRIMARY KEY(year, period, source_class)
);
