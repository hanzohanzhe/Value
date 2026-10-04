-- value.market-ledger/v8: compact science projection and rolling integrity.
CREATE TABLE IF NOT EXISTS dispatch_summary(
    year INTEGER NOT NULL,
    period INTEGER NOT NULL,
    stage TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    technology TEXT NOT NULL,
    accepted_dispatch_mwh REAL NOT NULL,
    PRIMARY KEY(year, period, stage, zone_id, technology)
);

CREATE TABLE IF NOT EXISTS storage_summary(
    year INTEGER NOT NULL,
    period INTEGER NOT NULL,
    zone_id TEXT NOT NULL,
    technology TEXT NOT NULL,
    charge_mwh REAL NOT NULL,
    discharge_mwh REAL NOT NULL,
    closing_soc_mwh REAL NOT NULL,
    PRIMARY KEY(year, period, zone_id, technology)
);

CREATE TABLE IF NOT EXISTS redispatch_summary(
    year INTEGER NOT NULL,
    period INTEGER NOT NULL,
    zone_id TEXT NOT NULL,
    technology TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('up', 'down')),
    accepted_delta_mwh REAL NOT NULL,
    resource_cost_gbp REAL NOT NULL,
    PRIMARY KEY(year, period, zone_id, technology, direction)
);

CREATE TABLE IF NOT EXISTS context_registry(
    context_scope TEXT NOT NULL CHECK(context_scope IN ('run', 'year')),
    year INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
    artifact_path TEXT NOT NULL,
    PRIMARY KEY(context_scope, year)
);

CREATE TABLE IF NOT EXISTS period_integrity(
    year INTEGER NOT NULL,
    period INTEGER NOT NULL,
    previous_science_hash TEXT NOT NULL CHECK(length(previous_science_hash) = 64),
    science_hash TEXT NOT NULL CHECK(length(science_hash) = 64),
    previous_evidence_hash TEXT NOT NULL CHECK(length(previous_evidence_hash) = 64),
    evidence_hash TEXT NOT NULL CHECK(length(evidence_hash) = 64),
    common_projection_sha256 TEXT NOT NULL CHECK(length(common_projection_sha256) = 64),
    stored_rows_sha256 TEXT NOT NULL CHECK(length(stored_rows_sha256) = 64),
    PRIMARY KEY(year, period)
);

CREATE TABLE IF NOT EXISTS year_integrity(
    year INTEGER PRIMARY KEY,
    run_context_sha256 TEXT NOT NULL CHECK(length(run_context_sha256) = 64),
    year_context_sha256 TEXT NOT NULL CHECK(length(year_context_sha256) = 64),
    science_root TEXT NOT NULL CHECK(length(science_root) = 64),
    evidence_root TEXT NOT NULL CHECK(length(evidence_root) = 64),
    period_count INTEGER NOT NULL CHECK(period_count >= 0),
    row_counts_json TEXT NOT NULL,
    trace_coverage_json TEXT NOT NULL,
    complete INTEGER NOT NULL CHECK(complete IN (0, 1))
);

CREATE INDEX IF NOT EXISTS dispatch_summary_period
    ON dispatch_summary(year, period);
CREATE INDEX IF NOT EXISTS storage_summary_period
    ON storage_summary(year, period);
CREATE INDEX IF NOT EXISTS redispatch_summary_period
    ON redispatch_summary(year, period);
CREATE INDEX IF NOT EXISTS period_integrity_year_period
    ON period_integrity(year, period);
